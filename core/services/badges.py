"""Achievement badge service (Roadmap idea #5).

A lightweight, *read-only* layer over data we already store - no new
ingestion. Every badge's earn condition is a small declarative ``rule`` dict
stored on ``BadgeDef`` and evaluated by :func:`evaluate_rule`, so brand-new
badges can be created entirely from the Django admin (see the README
"Achievement badges" section) - no code changes required.

Grants are persisted in ``UserBadge`` and are idempotent: re-running
``check_badges`` never double-awards a badge.

Entry points used by the API / admin:

  * ``sync_badge_defs()`` - seed the built-in catalog into ``BadgeDef`` rows.
  * ``check_badges(user)`` - evaluate every active badge, persist new grants,
    and return the keys newly awarded.
  * ``badges_state(user)`` - full payload for ``GET /api/v1/badges/``
    (runs a lazy grant check, then serializes the catalog with points,
    awarded timestamps and live progress).
"""

import json
import logging
from datetime import timedelta
from pathlib import Path

from django.utils import timezone

from ..models import (
    BadgeDef,
    Modality,
    RawActivityLog,
    SkillTree,
    UserBadge,
    PlayerProfile,
    UserGear,
    BattleLog,
    LeagueResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Derived-data helpers (pure reads over existing models).
# ---------------------------------------------------------------------------
def _activity_count(user):
    return RawActivityLog.objects.filter(user=user).count()


def _logged_days_in_last(user, days):
    """Number of the last ``days`` local calendar days with >= 1 activity."""
    today = timezone.localdate()
    count = 0
    for offset in range(days):
        day = today - timedelta(days=offset)
        if RawActivityLog.objects.filter(user=user, occurred_at__date=day).exists():
            count += 1
    return count


def _modality_levels(user):
    return {tree.modality: tree.level for tree in SkillTree.objects.filter(user=user)}


def _logs_in_window(user, before_hour=None, after_hour=None):
    """Number of activity logs whose local hour falls in the window."""
    count = 0
    for log in RawActivityLog.objects.filter(user=user).only("occurred_at"):
        hour = timezone.localtime(log.occurred_at).hour
        if before_hour is not None and hour < int(before_hour):
            count += 1
        elif after_hour is not None and hour >= int(after_hour):
            count += 1
    return count


HOT_INTENSITY = ("hiit", "zone4", "zone5", "high")


def _is_hot(intensity):
    return any(k in str(intensity).lower() for k in HOT_INTENSITY)


def _cardio_stats(user):
    """(total minutes, total calories, HIIT sessions) over cardio + endurance."""
    minutes = 0.0
    calories = 0.0
    hiit = 0
    logs = RawActivityLog.objects.filter(
        user=user, event_type__in=("cardio", "endurance")
    ).only("payload", "event_type")
    for log in logs:
        p = log.payload or {}
        try:
            if log.event_type == "cardio":
                minutes += float(p.get("minutes", 0) or 0)
                calories += float(p.get("calories", 0) or 0)
                if _is_hot(p.get("intensity")):
                    hiit += 1
            else:  # SparkyFitness exercise summaries
                minutes += float(p.get("total_duration_minutes", 0) or 0)
                calories += float(p.get("total_calories_burned", 0) or 0)
        except (TypeError, ValueError):
            continue
    return minutes, calories, hiit


def _strength_stats(user):
    """(session count, total volume in lbs) over strength logs."""
    sessions = 0
    volume = 0.0
    logs = RawActivityLog.objects.filter(
        user=user, event_type="strength"
    ).only("payload")
    for log in logs:
        sessions += 1
        p = log.payload or {}
        try:
            volume += float(p.get("total_volume_lbs", p.get("volume_lbs", 0)) or 0)
        except (TypeError, ValueError):
            continue
    return sessions, volume


def _sleep_hours(user):
    """All parsed sleep_hours values (floats)."""
    hours = []
    logs = RawActivityLog.objects.filter(
        user=user, event_type="sleep"
    ).only("payload")
    for log in logs:
        try:
            hours.append(float((log.payload or {}).get("sleep_hours", 0) or 0))
        except (TypeError, ValueError):
            continue
    return hours


def _nutrition_day_flags(payload):
    """(protein_hit, under_calorie, perfect) for one nutrition payload."""
    entries = payload.get("food_entries") or []
    goals = payload.get("goals") or {}
    try:
        total_pro = sum(float(e.get("protein", 0) or 0) for e in entries)
        total_cals = sum(float(e.get("calories", 0) or 0) for e in entries)
    except (TypeError, ValueError):
        return False, False, False
    pro_goal = goals.get("protein")
    cal_goal = goals.get("calories")
    protein_hit = pro_goal is not None and total_pro >= float(pro_goal)
    under_cal = cal_goal is not None and total_cals <= float(cal_goal)
    return bool(protein_hit), bool(under_cal), bool(protein_hit and under_cal)


def _nutrition_counts(user):
    """(logged days, protein-hit days, deficit days, perfect-macro days)."""
    days = 0
    protein = 0
    deficit = 0
    perfect = 0
    logs = RawActivityLog.objects.filter(
        user=user, event_type__in=("nutrition", "macro")
    ).only("payload", "event_type")
    for log in logs:
        days += 1
        p = log.payload or {}
        if log.event_type == "macro":
            hit = bool(p.get("protein_hit"))
            under = bool(p.get("under_calorie"))
        else:
            hit, under, _ = _nutrition_day_flags(p)
        protein += int(hit)
        deficit += int(under)
        perfect += int(hit and under)
    return days, protein, deficit, perfect


def _weight_readings(user):
    """Chronological list of numeric body-weight readings."""
    readings = []
    logs = RawActivityLog.objects.filter(user=user).only(
        "payload", "occurred_at"
    )
    logs = logs.order_by("occurred_at", "id")
    for log in logs:
        try:
            w = float((log.payload or {}).get("weight"))
        except (TypeError, ValueError):
            continue
        if w > 0:
            readings.append(w)
    return readings


def _profile_field(user, field, default=0):
    """Numeric field from the user's PlayerProfile (0 when none exists)."""
    try:
        profile = user.combat_profile
    except Exception:  # noqa: BLE001 - no profile yet is a normal early state
        return default
    return int(getattr(profile, field, default) or 0)


def _siege_damage(user):
    """Total siege damage dealt across every battle (lifetime)."""
    total = 0
    for dmg in BattleLog.objects.filter(user=user).values_list(
        "total_damage", flat=True
    ):
        total += int(dmg or 0)
    return total


def _gear_count(user, rarity=None):
    """Total owned gear items (sum of stack quantities), optionally by rarity."""
    qs = UserGear.objects.filter(user=user)
    if rarity:
        qs = qs.filter(rarity=rarity)
    return sum(int(q or 0) for q in qs.values_list("quantity", flat=True))


LEAGUE_TIER_INDEX = {
    "bronze": 1,
    "silver": 2,
    "gold": 3,
    "diamond": 4,
    "flamingo_legend": 5,
}


def _best_league_tier_index(user):
    """Highest league tier index reached (0 when there are no results)."""
    tiers = LeagueResult.objects.filter(user=user).values_list("tier", flat=True)
    return max((LEAGUE_TIER_INDEX.get(t, 1) for t in tiers), default=0)


def _league_results_count(user, top=None):
    """Number of closed league weeks on record (optionally rank <= top)."""
    qs = LeagueResult.objects.filter(user=user)
    if top is not None:
        qs = qs.filter(rank__lte=top)
    return qs.count()


def _tier_label(index):
    for tier, idx in LEAGUE_TIER_INDEX.items():
        if idx == index:
            return tier
    return "none"


# ---------------------------------------------------------------------------
# Rule engine. A rule is a small JSON dict stored on BadgeDef.rule, e.g.
# {"type": "streak", "minimum": 30}. evaluate_rule() returns
# (earned, current_value, target) so the frontend can render progress.
# ---------------------------------------------------------------------------
def evaluate_rule(user, rule):
    if not isinstance(rule, dict):
        return False, 0, 0
    rtype = rule.get("type")
    try:
        if rtype == "streak":
            target = int(rule.get("minimum", 1))
            value = int(user.streak or 0)
        elif rtype == "activity_logs":
            target = int(rule.get("minimum", 1))
            value = _activity_count(user)
        elif rtype == "perfect_days":
            target = int(rule.get("days", 7))
            value = _logged_days_in_last(user, target)
        elif rtype == "skill_level":
            target = int(rule.get("minimum", 2))
            value = _modality_levels(user).get(str(rule.get("modality", "")), 1)
        elif rtype == "all_modalities":
            target = len(Modality.values)
            minimum = int(rule.get("minimum", 3))
            levels = _modality_levels(user)
            value = sum(1 for m in Modality.values if levels.get(m, 1) >= minimum)
        elif rtype == "total_xp":
            target = int(rule.get("minimum", 100))
            value = int(user.total_xp or 0)
        elif rtype == "time_window":
            target = 1
            value = _logs_in_window(
                user,
                before_hour=rule.get("before_hour"),
                after_hour=rule.get("after_hour"),
            )
        elif rtype == "calories_burned":
            target = int(rule.get("minimum", 1000))
            _, calories, _ = _cardio_stats(user)
            value = int(calories)
        elif rtype == "cardio_minutes":
            target = int(rule.get("minimum", 100))
            minutes, _, _ = _cardio_stats(user)
            value = int(minutes)
        elif rtype == "hiit_sessions":
            target = int(rule.get("minimum", 10))
            _, _, value = _cardio_stats(user)
        elif rtype == "strength_sessions":
            target = int(rule.get("minimum", 10))
            value, _ = _strength_stats(user)
        elif rtype == "strength_volume":
            target = int(rule.get("minimum", 100000))
            _, volume = _strength_stats(user)
            value = int(volume)
        elif rtype == "nutrition_days":
            target = int(rule.get("minimum", 1))
            value, _, _, _ = _nutrition_counts(user)
        elif rtype == "protein_days":
            target = int(rule.get("minimum", 5))
            _, value, _, _ = _nutrition_counts(user)
        elif rtype == "deficit_days":
            target = int(rule.get("minimum", 5))
            _, _, value, _ = _nutrition_counts(user)
        elif rtype == "perfect_macro_days":
            target = int(rule.get("minimum", 1))
            _, _, _, value = _nutrition_counts(user)
        elif rtype == "sleep_nights":
            threshold = float(rule.get("hours", 8))
            target = int(rule.get("minimum", 1))
            value = sum(1 for h in _sleep_hours(user) if h >= threshold)
        elif rtype == "sleep_total":
            target = int(rule.get("minimum", 50))
            value = int(sum(_sleep_hours(user)))
        elif rtype == "sleep_best":
            target = float(rule.get("minimum", 9))
            hours = _sleep_hours(user)
            value = max(hours) if hours else 0.0
        elif rtype == "weigh_ins":
            target = int(rule.get("minimum", 1))
            value = len(_weight_readings(user))
        elif rtype == "weight_lost":
            target = float(rule.get("minimum", 5))
            readings = _weight_readings(user)
            value = round(readings[0] - readings[-1], 1) if len(readings) >= 2 else 0.0
        elif rtype == "conquests":
            target = int(rule.get("minimum", 1))
            value = _profile_field(user, "total_conquests")
        elif rtype == "siege_damage":
            target = int(rule.get("minimum", 1))
            value = _siege_damage(user)
        elif rtype == "pvp_wins":
            target = int(rule.get("minimum", 1))
            value = _profile_field(user, "pvp_wins")
        elif rtype == "gear_owned":
            target = int(rule.get("minimum", 1))
            value = _gear_count(user, rule.get("rarity"))
        elif rtype == "league_results":
            target = int(rule.get("minimum", 1))
            value = _league_results_count(user)
        elif rtype == "league_top3":
            target = int(rule.get("minimum", 1))
            value = _league_results_count(user, top=3)
        elif rtype == "league_tier":
            target = LEAGUE_TIER_INDEX.get(str(rule.get("tier", "gold")), 1)
            value = _best_league_tier_index(user)
        else:
            return False, 0, 0
    except Exception:  # noqa: BLE001 - one broken rule must not break badges
        logger.exception("Badge rule evaluation failed: %r", rule)
        return False, 0, 0
    return bool(target) and value >= target, value, target


def progress_text(rule, value, target):
    """Human-friendly 'what is left' copy for a locked badge."""
    if not isinstance(rule, dict):
        return ""
    rtype = rule.get("type")
    if rtype == "streak":
        return "Current streak: %d of %d days." % (value, target)
    if rtype == "activity_logs":
        return "%d of %d activities logged." % (value, target)
    if rtype == "perfect_days":
        return "Logged on %d of the last %d days." % (value, target)
    if rtype == "skill_level":
        try:
            label = Modality(str(rule.get("modality", ""))).label
        except ValueError:
            label = str(rule.get("modality", ""))
        return "%s at level %d of %d." % (label, value, target)
    if rtype == "all_modalities":
        return "%d of %d skill trees at level %s+." % (
            value, target, rule.get("minimum", 3),
        )
    if rtype == "total_xp":
        return "%d of %d lifetime XP." % (value, target)
    if rtype == "time_window":
        if rule.get("before_hour") is not None:
            return "Log an activity before %s:00." % rule.get("before_hour")
        return "Log an activity at or after %s:00." % rule.get("after_hour")
    if rtype == "calories_burned":
        return "{:,} of {:,} calories burned.".format(int(value), int(target))
    if rtype == "cardio_minutes":
        return "{:,} of {:,} cardio minutes logged.".format(int(value), int(target))
    if rtype == "hiit_sessions":
        return "%d of %d high-intensity sessions." % (value, target)
    if rtype == "strength_sessions":
        return "%d of %d strength sessions." % (value, target)
    if rtype == "strength_volume":
        return "{:,} of {:,} lbs lifted.".format(int(value), int(target))
    if rtype == "nutrition_days":
        return "Nutrition logged on %d of %d days." % (value, target)
    if rtype == "protein_days":
        return "Protein goal hit on %d of %d days." % (value, target)
    if rtype == "deficit_days":
        return "Under the calorie goal on %d of %d days." % (value, target)
    if rtype == "perfect_macro_days":
        return "%d of %d perfect macro days." % (value, target)
    if rtype == "sleep_nights":
        return "%d of %d nights with %s+ hours of sleep." % (
            value, target, rule.get("hours", 8),
        )
    if rtype == "sleep_total":
        return "%d of %d total hours of sleep tracked." % (int(value), int(target))
    if rtype == "sleep_best":
        return "Best night so far: %.1f of %.0f hours." % (float(value), float(target))
    if rtype == "weigh_ins":
        return "%d of %d weigh-ins logged." % (value, target)
    if rtype == "weight_lost":
        return "%.1f of %.0f lbs dropped from your starting weight." % (
            float(value), float(target),
        )
    if rtype == "conquests":
        return "%d of %d campaign bosses conquered." % (value, target)
    if rtype == "siege_damage":
        return "{:,} of {:,} total siege damage dealt.".format(int(value), int(target))
    if rtype == "pvp_wins":
        return "%d of %d gym battles won." % (value, target)
    if rtype == "gear_owned":
        rarity = rule.get("rarity")
        what = "%s items" % rarity if rarity else "gear items"
        return "%d of %d %s owned." % (value, target, what)
    if rtype == "league_results":
        return "%d of %d ranked league weeks." % (value, target)
    if rtype == "league_top3":
        return "%d of %d top-3 league finishes." % (value, target)
    if rtype == "league_tier":
        return "Best league tier: %s (need %s or higher)." % (
            _tier_label(value), rule.get("tier", "gold"),
        )
    return "%d of %d." % (value, target)

# ---------------------------------------------------------------------------
# Built-in badge catalog. All entries are rule-driven; sync_badge_defs()
# seeds them as ordinary BadgeDef rows an admin can then edit or deactivate.
# Points scale with difficulty (5 trivial -> 100 very hard).
# ---------------------------------------------------------------------------
# The built-in catalog lives as plain JSON in config/seeds/badges.json so an
# instance owner can edit points/rules/icons without code changes.
SEED_DIR = Path(__file__).resolve().parents[2] / "config" / "seeds"
with (SEED_DIR / "badges.json").open("r", encoding="utf-8") as _catalog_fh:
    BADGE_CATALOG = json.load(_catalog_fh)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def sync_badge_defs():
    """Seed the built-in catalog into ``BadgeDef`` rows.

    Idempotent and safe to call often. Existing rows are left untouched
    (admins may rename/re-point them); rows created before the rule engine
    existed are backfilled with their catalog rule + points once.
    Returns the number of rows newly created.
    """
    created = 0
    for item in BADGE_CATALOG:
        badge_def, was_created = BadgeDef.objects.get_or_create(
            key=item["key"],
            defaults={
                "name": item["name"],
                "description": item["description"],
                "icon": item["icon"],
                "category": item["category"],
                "sort_order": item["sort_order"],
                "points": item["points"],
                "rule": item["rule"],
            },
        )
        if was_created:
            created += 1
        elif not badge_def.rule:
            badge_def.rule = item["rule"]
            badge_def.points = item["points"]
            badge_def.save(update_fields=["rule", "points"])
    return created


def check_badges(user):
    """Evaluate every active badge for ``user`` and persist new grants.

    Covers both built-in catalog badges and badges created in the admin -
    anything with a non-empty ``rule``. Idempotent: a badge already present
    in ``UserBadge`` is never granted twice. Returns the list of badge
    ``key`` strings newly awarded (empty if none).
    """
    sync_badge_defs()
    newly = []
    granted_ids = set(
        UserBadge.objects.filter(user=user).values_list("badge_id", flat=True)
    )
    for badge_def in BadgeDef.objects.filter(is_active=True):
        if badge_def.id in granted_ids or not badge_def.rule:
            continue
        earned, _, _ = evaluate_rule(user, badge_def.rule)
        if earned:
            UserBadge.objects.create(user=user, badge=badge_def)
            newly.append(badge_def.key)
    return newly


def badges_state(user):
    """Full badge state for ``GET /api/v1/badges/`` (+ lazy grant check)."""
    newly = check_badges(user)
    grants = {
        ub.badge_id: ub.awarded_at for ub in UserBadge.objects.filter(user=user)
    }
    badges = []
    earned = 0
    earned_points = 0
    total_points = 0
    for bd in BadgeDef.objects.filter(is_active=True).order_by("sort_order", "id"):
        total_points += bd.points
        granted = bd.id in grants
        entry = {
            "key": bd.key,
            "name": bd.name,
            "description": bd.description,
            "icon": bd.icon,
            "category": bd.category,
            "points": bd.points,
            "granted": granted,
            "awarded_at": grants[bd.id].isoformat() if granted else None,
        }
        if granted:
            earned += 1
            earned_points += bd.points
            entry["progress"] = {
                "pct": 100,
                "value": None,
                "target": None,
                "text": "Completed!",
            }
        else:
            _, value, target = evaluate_rule(user, bd.rule or {})
            pct = int(min(100, round(value * 100.0 / target))) if target else 0
            entry["progress"] = {
                "pct": pct,
                "value": value,
                "target": target,
                "text": progress_text(bd.rule or {}, value, target)
                if bd.rule
                else "No earn rule configured for this badge yet.",
            }
        badges.append(entry)
    return {
        "total": len(badges),
        "earned": earned,
        "total_points": total_points,
        "earned_points": earned_points,
        "newly_awarded": newly,
        "badges": badges,
    }
