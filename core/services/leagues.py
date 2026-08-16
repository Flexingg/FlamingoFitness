"""League service (Phase 8, docs/13 §5.1).

Turns the rolling weekly XP leaderboard into a persisted, calendar-week
league (completes the parked Step 8b, docs/07): each Monday-anchored week is
a ``LeagueWeek`` row; when the week closes the ranks / tiers are snapshotted
into ``LeagueResult`` rows and the top-3 rewards are paid into the existing
base-building sinks (time speedups + materials).

Tiers are a *pure function* of weekly Effort XP (no stored movement) - the
promotion/relegation state machine is deliberately a future slice.

Entry points used by views / tasks:

  * ``ensure_current_week(now=None)`` - lazy open/close of weeks.
  * ``close_league_week(week, now=None)`` - snapshot + rewards (idempotent).
  * ``league_state(user, now=None)`` - payload for ``GET /api/v1/leagues/``.
"""

import logging
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from ..models import LeagueResult, LeagueTier, LeagueWeek, XPLedger
from .game_config import GAMEPLAY

logger = logging.getLogger(__name__)

# Tier thresholds by weekly Effort XP (docs/13 §3.1), ordered highest first.
# Sourced from config/gameplay.json -> league -> tiers.
_LEAGUE_CFG = GAMEPLAY["league"]
LEAGUE_TIERS = [
    {
        "tier": LeagueTier(row["tier"]),
        "label": row["label"],
        "min_xp": int(row["min_xp"]),
    }
    for row in _LEAGUE_CFG["tiers"]
]

# Rewards paid when a week closes (docs/15 §3.1) - converted to Tokens from
# the Phase 8 time_speedups + materials payouts (1 token / 10 speedups,
# 1 token / 20 materials). Additive to the token economy.
WEEKLY_REWARDS = {int(k): v for k, v in _LEAGUE_CFG["weekly_rewards"].items()}
LEAGUE_TOP_N_REWARDED = int(_LEAGUE_CFG["top_n_rewarded"])


def week_start_for(on_date):
    """Monday (local) of the week containing ``on_date``."""
    return on_date - timedelta(days=on_date.weekday())


def _aware_midnight(on_date):
    return timezone.make_aware(datetime.combine(on_date, time.min))


def tier_for_xp(xp):
    """Tier key for a weekly XP total (always returns a valid tier)."""
    for row in LEAGUE_TIERS:
        if xp >= row["min_xp"]:
            return row["tier"]
    return LeagueTier.BRONZE


def weekly_xp_rows(since, until=None):
    """Aggregate Effort XP per user for a window as sorted dicts (desc).

    ``since``/``until`` are aware datetimes; ``until`` is exclusive. Rows
    with a non-positive total are dropped (corrections can't buy rank).
    """
    qs = XPLedger.objects.filter(created_at__gte=since)
    if until is not None:
        qs = qs.filter(created_at__lt=until)
    rows = (
        qs.values("user_id", "user__username", "user__avatar")
        .annotate(xp=Sum("amount"))
        .order_by("-xp")
    )
    return [dict(row) for row in rows if (row["xp"] or 0) > 0]


def weekly_xp_map(now=None):
    """{user_id: xp} for the *current* open week (used by the Flock tab)."""
    now = now or timezone.now()
    start = week_start_for(timezone.localdate(now))
    return {
        row["user_id"]: row["xp"]
        for row in weekly_xp_rows(_aware_midnight(start), now)
    }


def close_league_week(week, now=None):
    """Snapshot ranks/tiers for ``week`` and pay top-3 rewards.

    Idempotent: already-closed weeks are left untouched. Returns the list of
    created ``LeagueResult`` rows.
    """
    from .combat import award_tokens  # local import: avoid cycles

    now = now or timezone.now()
    if week.status == LeagueWeek.Status.CLOSED:
        return []

    since = _aware_midnight(week.week_start)
    until = since + timedelta(days=7)

    with transaction.atomic():
        week = LeagueWeek.objects.select_for_update().get(pk=week.pk)
        if week.status == LeagueWeek.Status.CLOSED:
            return []
        results = []
        for index, row in enumerate(weekly_xp_rows(since, until)):
            rank = index + 1
            reward = dict(WEEKLY_REWARDS.get(rank, {}))
            user = get_user_model().objects.get(pk=row["user_id"])
            if reward:
                award_tokens(user, reward.get("tokens", 0))
            results.append(
                LeagueResult.objects.create(
                    week=week,
                    user=user,
                    xp=row["xp"],
                    rank=rank,
                    tier=tier_for_xp(row["xp"]),
                    reward=reward,
                )
            )
        week.status = LeagueWeek.Status.CLOSED
        week.closed_at = now
        week.save(update_fields=["status", "closed_at"])
    logger.info(
        "Closed league week %s with %d ranked player(s).",
        week.week_start,
        len(results),
    )
    return results


def ensure_current_week(now=None):
    """Return the open LeagueWeek for the current Monday.

    Lazily closes any stale open weeks first, so a beat outage never loses a
    snapshot (docs/13 §9).
    """
    now = now or timezone.now()
    current_monday = week_start_for(timezone.localdate(now))
    stale = LeagueWeek.objects.filter(
        status=LeagueWeek.Status.OPEN, week_start__lt=current_monday
    ).order_by("week_start")
    for week in stale:
        close_league_week(week, now=now)
    week, _ = LeagueWeek.objects.get_or_create(week_start=current_monday)
    return week


def league_state(user, now=None):
    """Payload for ``GET /api/v1/leagues/`` (docs/13 §6.1)."""
    now = now or timezone.now()
    week = ensure_current_week(now=now)
    today = timezone.localdate(now)

    rows = weekly_xp_rows(_aware_midnight(week.week_start), now)
    leaderboard = []
    my_rank = None
    my_xp = 0
    for index, row in enumerate(rows):
        rank = index + 1
        is_you = row["user_id"] == user.pk
        if is_you:
            my_rank = rank
            my_xp = row["xp"]
        leaderboard.append(
            {
                "rank": rank,
                "username": row["user__username"],
                "avatar": row["user__avatar"],
                "xp": row["xp"],
                "tier": tier_for_xp(row["xp"]),
                "is_you": is_you,
            }
        )
    if my_rank is None:
        # The panel always shows "you", even at 0 XP this week.
        leaderboard.append(
            {
                "rank": len(leaderboard) + 1,
                "username": user.username,
                "avatar": user.avatar,
                "xp": 0,
                "tier": LeagueTier.BRONZE,
                "is_you": True,
            }
        )

    history = [
        {
            "week_start": result.week.week_start.isoformat(),
            "rank": result.rank,
            "xp": result.xp,
            "tier": result.tier,
            "reward": result.reward or {},
        }
        for result in LeagueResult.objects.filter(user=user)
        .select_related("week")
        .order_by("-week__week_start")[:8]
    ]

    return {
        "week": {
            "week_start": week.week_start.isoformat(),
            "week_end": week.week_end.isoformat(),
            "status": week.status,
            "days_left": max(0, (week.week_end - today).days),
        },
        "tiers": LEAGUE_TIERS,
        "my_tier": tier_for_xp(my_xp),
        "my_rank": my_rank,
        "leaderboard": leaderboard,
        "history": history,
    }
