"""Water logging + hydration aggregation service (manual water upgrade).

Manual water logging stores each add/remove as a `RawActivityLog` hydration
entry (processed=True, so the per-log gamification handler doesn't under-reward
single bottles). XP/tokens are awarded at the DAY level instead, idempotently,
based on the aggregated day total.
"""
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from ..models import (
    Modality,
    PlayerProfile,
    Provider,
    RawActivityLog,
    WaterBottle,
    XPLedger,
)
from .gamification import (
    apply_to_skill_tree,
    award_tokens,
    hydration_tokens,
    hydration_xp,
)

DEFAULT_GOAL_OZ = 80.0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def log_water_amount(raw_log):
    """Total oz represented by a single hydration log."""
    payload = raw_log.payload or {}
    entries = payload.get("water_intake_entries") or []
    if entries:
        return sum(float(e.get("amount", 0) or 0) for e in entries)
    direct = payload.get("water") or payload.get("water_oz") or payload.get("amount")
    if direct is None and payload.get("water_ml"):
        direct = float(payload.get("water_ml", 0) or 0) / 29.5735
    return float(direct or 0)


def _log_date(raw_log):
    payload = raw_log.payload or {}
    d = payload.get("date")
    if d:
        try:
            return str(d)[:10]
        except (ValueError, TypeError):
            pass
    return raw_log.occurred_at.date().isoformat()


def _log_goal(raw_log):
    payload = raw_log.payload or {}
    return (
        payload.get("water_goal")
        or payload.get("water_goal_oz")
        or (payload.get("goals") or {}).get("water")
    )


def _merge_entries(logs):
    merged = []
    for log in logs:
        entries = (log.payload or {}).get("water_intake_entries") or []
        if entries:
            for e in entries:
                merged.append(
                    {
                        "time": e.get("time") or e.get("logged_at")
                        or log.occurred_at.strftime("%H:%M"),
                        "amount": round(float(e.get("amount", 0) or 0), 1),
                    }
                )
        else:
            merged.append(
                {
                    "time": log.occurred_at.strftime("%H:%M"),
                    "amount": round(log_water_amount(log), 1),
                }
            )
    return merged


# ---------------------------------------------------------------------------
# primary source + bottles
# ---------------------------------------------------------------------------

def primary_hydration_source(profile, sparky_linked):
    pref = (profile.source_preferences or {}).get("hydration")
    if pref:
        return pref
    return "sparkyfitness" if sparky_linked else "health_connect"


def ensure_default_bottles(user):
    if not user.water_bottles.exists():
        WaterBottle.objects.create(
            user=user, name="Bottle", capacity_oz=24.0, sort_order=0
        )
    return list(user.water_bottles.all())


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------

def build_hydration_history(logs, include_raw=False):
    """Group hydration logs by date, aggregating water (Sparky-aware).

    If a date has an auto-synced Sparky log, that log's total is authoritative
    (it already includes water pushed to Sparky), so any manual logs that were
    pushed to Sparky are skipped to avoid double-counting.
    """
    by_date = defaultdict(list)
    for log in logs:
        by_date[_log_date(log)].append(log)

    history = []
    for date in sorted(by_date.keys(), reverse=True):
        day_logs = by_date[date]
        sparky_auto = [
            l for l in day_logs
            if l.source == Provider.SPARKYFITNESS and not (l.payload or {}).get("manual")
        ]
        health_auto = [
            l for l in day_logs
            if l.source in (Provider.HEALTH_CONNECT, Provider.HEALTHKIT) and not (l.payload or {}).get("manual")
        ]

        if sparky_auto:
            base = sum(log_water_amount(l) for l in sparky_auto)
            extras = [
                l for l in day_logs
                if l not in sparky_auto and not (l.payload or {}).get("pushed_to_sparky")
            ]
            total = base + sum(log_water_amount(l) for l in extras)
            merged_entries = _merge_entries(sparky_auto + extras)
        elif health_auto:
            latest_health_log = max(health_auto, key=lambda l: l.occurred_at)
            base = log_water_amount(latest_health_log)
            manual_logs = [l for l in day_logs if (l.payload or {}).get("manual")]
            manual_total = sum(log_water_amount(l) for l in manual_logs)
            total = max(base, manual_total)
            merged_entries = _merge_entries(day_logs)
        else:
            total = sum(log_water_amount(l) for l in day_logs)
            merged_entries = _merge_entries(day_logs)

        goal_f = next(
            (float(g) for g in (_log_goal(l) for l in day_logs) if g is not None),
            None,
        )
        water_pct = int(round((total / goal_f) * 100)) if goal_f else 0
        perfect = bool(goal_f is not None and total >= goal_f)

        if perfect:
            status, status_label = "perfect", "ON TARGET"
        elif water_pct >= 80:
            status, status_label = "close", "CLOSE"
        elif water_pct >= 60:
            status, status_label = "partial", "PARTIAL"
        else:
            status, status_label = "needs_work", "Needs work"

        day = {
            "date": date,
            "water": round(total, 1),
            "water_goal": round(goal_f, 1) if goal_f is not None else None,
            "water_pct": water_pct,
            "perfect": perfect,
            "status": status,
            "status_label": status_label,
            "xp": hydration_xp(total, goal_f),
            "tokens": hydration_tokens(total, goal_f),
            "water_intake_entries": merged_entries,
        }
        if include_raw:
            day["raw_payload"] = [l.payload for l in day_logs]
        history.append(day)
    return history


# ---------------------------------------------------------------------------
# day-level gamification
# ---------------------------------------------------------------------------

def _day_range(date_str):
    d = timezone.datetime.fromisoformat(date_str).date()
    start = timezone.make_aware(
        timezone.datetime.combine(d, timezone.datetime.min.time())
    )
    return start, start + timedelta(days=1)


def award_day_hydration(user, date_str):
    """Idempotently award day-level hydration XP (+ tokens once) for a date."""
    logs = RawActivityLog.objects.filter(
        user=user, event_type="hydration"
    )
    summary = next(
        (h for h in build_hydration_history(logs) if h["date"] == date_str), None
    )
    if not summary or summary["water_goal"] is None:
        return 0

    target_xp = hydration_xp(summary["water"], summary["water_goal"])
    target_tokens = hydration_tokens(summary["water"], summary["water_goal"])
    start, end = _day_range(date_str)

    entries = XPLedger.objects.filter(
        user=user, modality=Modality.HYDRATION,
        created_at__gte=start, created_at__lt=end,
    )
    awarded_xp = sum(e.amount for e in entries if e.amount > 0)
    delta_xp = max(0, int(target_xp) - int(awarded_xp))
    if delta_xp <= 0:
        return 0

    XPLedger.objects.create(
        user=user,
        modality=Modality.HYDRATION,
        amount=delta_xp,
        description=(
            f"Hydration day {date_str} "
            f"({summary['water']}oz/{summary['water_goal']}oz)"
        ),
    )
    apply_to_skill_tree(user, Modality.HYDRATION, delta_xp)

    # Tokens: award once per day, only when the day first earns any reward.
    if target_tokens > 0 and not entries.exists():
        award_tokens(user, target_tokens)

    return delta_xp


# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------

def create_water_log(user, amount_oz, source, pushed_to_sparky=False, goal_oz=None):
    """Record a water add/remove and award day-level hydration rewards."""
    now = timezone.now()
    date = timezone.localdate()
    goal = float(goal_oz) if goal_oz else DEFAULT_GOAL_OZ

    RawActivityLog.objects.create(
        user=user,
        source=source,
        event_type="hydration",
        payload={
            "date": date.isoformat(),
            "water_intake_oz": round(amount_oz, 1),
            "water_intake_entries": [
                {"time": now.strftime("%H:%M"), "amount": round(amount_oz, 1)}
            ],
            "water_goal_oz": float(goal),
            "source": source,
            "manual": True,
            "pushed_to_sparky": pushed_to_sparky,
        },
        occurred_at=now,
        processed=True,  # day-level XP is handled by award_day_hydration
    )
    award_day_hydration(user, date.isoformat())
    return amount_oz
