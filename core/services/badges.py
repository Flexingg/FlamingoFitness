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

import logging
from datetime import timedelta

from django.utils import timezone

from ..models import (
    BadgeDef,
    Modality,
    RawActivityLog,
    SkillTree,
    UserBadge,
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
    return "%d of %d." % (value, target)

# ---------------------------------------------------------------------------
# Built-in badge catalog. All entries are rule-driven; sync_badge_defs()
# seeds them as ordinary BadgeDef rows an admin can then edit or deactivate.
# Points scale with difficulty (5 trivial -> 100 very hard).
# ---------------------------------------------------------------------------
BADGE_CATALOG = [
    {
        "key": "first_steps",
        "name": "First Steps",
        "description": "Log your first activity.",
        "icon": "fa-shoe-prints",
        "category": "Milestones",
        "sort_order": 1,
        "points": 5,
        "rule": {"type": "activity_logs", "minimum": 1},
    },
    {
        "key": "ten_day_flame",
        "name": "10-Day Flame",
        "description": "Build a 10-day streak.",
        "icon": "fa-fire",
        "category": "Streaks",
        "sort_order": 2,
        "points": 25,
        "rule": {"type": "streak", "minimum": 10},
    },
    {
        "key": "perfect_week",
        "name": "Perfect Week",
        "description": "Log activity on all 7 days of the past week.",
        "icon": "fa-calendar-check",
        "category": "Streaks",
        "sort_order": 3,
        "points": 50,
        "rule": {"type": "perfect_days", "days": 7},
    },
    {
        "key": "all_modality_master",
        "name": "All-Modality Master",
        "description": "Get every skill tree to level 3.",
        "icon": "fa-medal",
        "category": "Skill",
        "sort_order": 6,
        "points": 75,
        "rule": {"type": "all_modalities", "minimum": 3},
    },
    {
        "key": "early_bird",
        "name": "Early Bird",
        "description": "Log an activity before 6 AM.",
        "icon": "fa-sun",
        "category": "Habits",
        "sort_order": 7,
        "points": 10,
        "rule": {"type": "time_window", "before_hour": 6},
    },
    {
        "key": "night_owl",
        "name": "Night Owl",
        "description": "Log an activity at or after 9 PM.",
        "icon": "fa-moon",
        "category": "Habits",
        "sort_order": 8,
        "points": 10,
        "rule": {"type": "time_window", "after_hour": 21},
    },
    # -----------------------------------------------------------------
    # Nutrition achievements (14)
    # -----------------------------------------------------------------
    {
        "key": "meal_tracker",
        "name": "Meal Tracker",
        "description": "Log your first day of nutrition.",
        "icon": "fa-utensils",
        "category": "Nutrition",
        "sort_order": 101,
        "points": 5,
        "rule": {"type": "nutrition_days", "minimum": 1},
    },
    {
        "key": "meal_tracker_week",
        "name": "Weekly Foodie",
        "description": "Log nutrition on 7 days.",
        "icon": "fa-utensils",
        "category": "Nutrition",
        "sort_order": 102,
        "points": 10,
        "rule": {"type": "nutrition_days", "minimum": 7},
    },
    {
        "key": "meal_tracker_30",
        "name": "Monthly Menu",
        "description": "Log nutrition on 30 days.",
        "icon": "fa-book-open",
        "category": "Nutrition",
        "sort_order": 103,
        "points": 25,
        "rule": {"type": "nutrition_days", "minimum": 30},
    },
    {
        "key": "meal_tracker_100",
        "name": "Food Diary Devotee",
        "description": "Log nutrition on 100 days.",
        "icon": "fa-book-open",
        "category": "Nutrition",
        "sort_order": 104,
        "points": 75,
        "rule": {"type": "nutrition_days", "minimum": 100},
    },
    {
        "key": "protein_5",
        "name": "Protein Starter",
        "description": "Hit your protein goal on 5 days.",
        "icon": "fa-drumstick-bite",
        "category": "Nutrition",
        "sort_order": 105,
        "points": 10,
        "rule": {"type": "protein_days", "minimum": 5},
    },
    {
        "key": "protein_25",
        "name": "Protein Regular",
        "description": "Hit your protein goal on 25 days.",
        "icon": "fa-drumstick-bite",
        "category": "Nutrition",
        "sort_order": 106,
        "points": 25,
        "rule": {"type": "protein_days", "minimum": 25},
    },
    {
        "key": "protein_100",
        "name": "Protein Centurion",
        "description": "Hit your protein goal on 100 days.",
        "icon": "fa-drumstick-bite",
        "category": "Nutrition",
        "sort_order": 107,
        "points": 75,
        "rule": {"type": "protein_days", "minimum": 100},
    },
    {
        "key": "deficit_5",
        "name": "Deficit Debut",
        "description": "Stay under your calorie goal on 5 days.",
        "icon": "fa-arrow-trend-down",
        "category": "Nutrition",
        "sort_order": 108,
        "points": 10,
        "rule": {"type": "deficit_days", "minimum": 5},
    },
    {
        "key": "deficit_25",
        "name": "Consistent Deficit",
        "description": "Stay under your calorie goal on 25 days.",
        "icon": "fa-arrow-trend-down",
        "category": "Nutrition",
        "sort_order": 109,
        "points": 25,
        "rule": {"type": "deficit_days", "minimum": 25},
    },
    {
        "key": "deficit_100",
        "name": "Deficit Master",
        "description": "Stay under your calorie goal on 100 days.",
        "icon": "fa-arrow-trend-down",
        "category": "Nutrition",
        "sort_order": 110,
        "points": 75,
        "rule": {"type": "deficit_days", "minimum": 100},
    },
    {
        "key": "perfect_macros_1",
        "name": "Perfect Plate",
        "description": "Hit your protein goal and stay under calories for a full day.",
        "icon": "fa-star",
        "category": "Nutrition",
        "sort_order": 111,
        "points": 10,
        "rule": {"type": "perfect_macro_days", "minimum": 1},
    },
    {
        "key": "perfect_macros_10",
        "name": "Ten Perfect Days",
        "description": "Achieve perfect macros on 10 days.",
        "icon": "fa-star",
        "category": "Nutrition",
        "sort_order": 112,
        "points": 25,
        "rule": {"type": "perfect_macro_days", "minimum": 10},
    },
    {
        "key": "perfect_macros_50",
        "name": "Macro Maestro",
        "description": "Achieve perfect macros on 50 days.",
        "icon": "fa-trophy",
        "category": "Nutrition",
        "sort_order": 113,
        "points": 75,
        "rule": {"type": "perfect_macro_days", "minimum": 50},
    },
    {
        "key": "nutrition_level_5",
        "name": "Nutrition Scholar",
        "description": "Reach level 5 in the Nutrition skill tree.",
        "icon": "fa-apple-whole",
        "category": "Nutrition",
        "sort_order": 114,
        "points": 50,
        "rule": {"type": "skill_level", "modality": "nutrition", "minimum": 5},
    },
    # -----------------------------------------------------------------
    # Weight-loss achievements (10)
    # -----------------------------------------------------------------
    {
        "key": "first_weigh_in",
        "name": "First Weigh-In",
        "description": "Log your first weight.",
        "icon": "fa-weight-scale",
        "category": "Weight",
        "sort_order": 115,
        "points": 5,
        "rule": {"type": "weigh_ins", "minimum": 1},
    },
    {
        "key": "weigh_ins_5",
        "name": "Scale Watcher",
        "description": "Log 5 weigh-ins.",
        "icon": "fa-weight-scale",
        "category": "Weight",
        "sort_order": 116,
        "points": 10,
        "rule": {"type": "weigh_ins", "minimum": 5},
    },
    {
        "key": "weigh_ins_10",
        "name": "Ten Checkpoints",
        "description": "Log 10 weigh-ins.",
        "icon": "fa-weight-scale",
        "category": "Weight",
        "sort_order": 117,
        "points": 15,
        "rule": {"type": "weigh_ins", "minimum": 10},
    },
    {
        "key": "weigh_ins_30",
        "name": "Monthly Weigh Habit",
        "description": "Log 30 weigh-ins.",
        "icon": "fa-weight-scale",
        "category": "Weight",
        "sort_order": 118,
        "points": 25,
        "rule": {"type": "weigh_ins", "minimum": 30},
    },
    {
        "key": "weigh_ins_52",
        "name": "Year of Weigh-Ins",
        "description": "Log 52 weigh-ins - a full year of weekly check-ins.",
        "icon": "fa-calendar-days",
        "category": "Weight",
        "sort_order": 119,
        "points": 50,
        "rule": {"type": "weigh_ins", "minimum": 52},
    },
    {
        "key": "weigh_ins_100",
        "name": "Century on the Scale",
        "description": "Log 100 weigh-ins.",
        "icon": "fa-weight-scale",
        "category": "Weight",
        "sort_order": 120,
        "points": 75,
        "rule": {"type": "weigh_ins", "minimum": 100},
    },
    {
        "key": "lost_5",
        "name": "Lighter by Five",
        "description": "Drop 5 lbs from your starting weight.",
        "icon": "fa-feather",
        "category": "Weight",
        "sort_order": 121,
        "points": 25,
        "rule": {"type": "weight_lost", "minimum": 5},
    },
    {
        "key": "lost_10",
        "name": "Down Ten",
        "description": "Drop 10 lbs from your starting weight.",
        "icon": "fa-feather-pointed",
        "category": "Weight",
        "sort_order": 122,
        "points": 50,
        "rule": {"type": "weight_lost", "minimum": 10},
    },
    {
        "key": "lost_25",
        "name": "Quarter Quest",
        "description": "Drop 25 lbs from your starting weight.",
        "icon": "fa-fire-flame-curved",
        "category": "Weight",
        "sort_order": 123,
        "points": 75,
        "rule": {"type": "weight_lost", "minimum": 25},
    },
    {
        "key": "lost_50",
        "name": "Half-Century Lighter",
        "description": "Drop 50 lbs from your starting weight.",
        "icon": "fa-trophy",
        "category": "Weight",
        "sort_order": 124,
        "points": 100,
        "rule": {"type": "weight_lost", "minimum": 50},
    },
    # -----------------------------------------------------------------
    # Calories-burned / workout output achievements (14)
    # -----------------------------------------------------------------
    {
        "key": "burn_1k",
        "name": "First Thousand",
        "description": "Burn 1,000 calories across tracked workouts.",
        "icon": "fa-fire",
        "category": "Burn",
        "sort_order": 125,
        "points": 10,
        "rule": {"type": "calories_burned", "minimum": 1000},
    },
    {
        "key": "burn_5k",
        "name": "Five-Figure Furnace",
        "description": "Burn 5,000 calories across tracked workouts.",
        "icon": "fa-fire",
        "category": "Burn",
        "sort_order": 126,
        "points": 25,
        "rule": {"type": "calories_burned", "minimum": 5000},
    },
    {
        "key": "burn_10k",
        "name": "Ten Thousand Torched",
        "description": "Burn 10,000 calories across tracked workouts.",
        "icon": "fa-fire-flame-curved",
        "category": "Burn",
        "sort_order": 127,
        "points": 50,
        "rule": {"type": "calories_burned", "minimum": 10000},
    },
    {
        "key": "burn_25k",
        "name": "Inferno",
        "description": "Burn 25,000 calories across tracked workouts.",
        "icon": "fa-fire-flame-curved",
        "category": "Burn",
        "sort_order": 128,
        "points": 75,
        "rule": {"type": "calories_burned", "minimum": 25000},
    },
    {
        "key": "burn_50k",
        "name": "Human Blast Furnace",
        "description": "Burn 50,000 calories across tracked workouts.",
        "icon": "fa-sun",
        "category": "Burn",
        "sort_order": 129,
        "points": 100,
        "rule": {"type": "calories_burned", "minimum": 50000},
    },
    {
        "key": "cardio_100",
        "name": "Warming Up",
        "description": "Log 100 minutes of cardio.",
        "icon": "fa-person-running",
        "category": "Burn",
        "sort_order": 130,
        "points": 10,
        "rule": {"type": "cardio_minutes", "minimum": 100},
    },
    {
        "key": "cardio_500",
        "name": "Endurance Enthusiast",
        "description": "Log 500 minutes of cardio.",
        "icon": "fa-person-running",
        "category": "Burn",
        "sort_order": 131,
        "points": 25,
        "rule": {"type": "cardio_minutes", "minimum": 500},
    },
    {
        "key": "cardio_1500",
        "name": "Road Warrior",
        "description": "Log 1,500 minutes of cardio.",
        "icon": "fa-person-biking",
        "category": "Burn",
        "sort_order": 132,
        "points": 50,
        "rule": {"type": "cardio_minutes", "minimum": 1500},
    },
    {
        "key": "cardio_3000",
        "name": "Cardio Royalty",
        "description": "Log 3,000 minutes of cardio.",
        "icon": "fa-crown",
        "category": "Burn",
        "sort_order": 133,
        "points": 75,
        "rule": {"type": "cardio_minutes", "minimum": 3000},
    },
    {
        "key": "hiit_10",
        "name": "HIIT Happening",
        "description": "Finish 10 high-intensity (zone 4+) sessions.",
        "icon": "fa-bolt",
        "category": "Burn",
        "sort_order": 134,
        "points": 25,
        "rule": {"type": "hiit_sessions", "minimum": 10},
    },
    {
        "key": "hiit_25",
        "name": "Interval Machine",
        "description": "Finish 25 high-intensity (zone 4+) sessions.",
        "icon": "fa-bolt-lightning",
        "category": "Burn",
        "sort_order": 135,
        "points": 50,
        "rule": {"type": "hiit_sessions", "minimum": 25},
    },
    {
        "key": "iron_100k",
        "name": "100K Club",
        "description": "Lift a total of 100,000 lbs.",
        "icon": "fa-dumbbell",
        "category": "Burn",
        "sort_order": 136,
        "points": 25,
        "rule": {"type": "strength_volume", "minimum": 100000},
    },
    {
        "key": "iron_250k",
        "name": "Quarter Million",
        "description": "Lift a total of 250,000 lbs.",
        "icon": "fa-dumbbell",
        "category": "Burn",
        "sort_order": 137,
        "points": 50,
        "rule": {"type": "strength_volume", "minimum": 250000},
    },
    {
        "key": "iron_1m",
        "name": "Million Pound Club",
        "description": "Lift a total of 1,000,000 lbs.",
        "icon": "fa-dumbbell",
        "category": "Burn",
        "sort_order": 138,
        "points": 100,
        "rule": {"type": "strength_volume", "minimum": 1000000},
    },
    # -----------------------------------------------------------------
    # Sleep achievements (12)
    # -----------------------------------------------------------------
    {
        "key": "sleep_8_first",
        "name": "Full Tank",
        "description": "Sleep 8+ hours in one night.",
        "icon": "fa-bed",
        "category": "Sleep",
        "sort_order": 139,
        "points": 5,
        "rule": {"type": "sleep_nights", "hours": 8, "minimum": 1},
    },
    {
        "key": "sleep_8_week",
        "name": "Seven Solid Nights",
        "description": "Sleep 8+ hours on 7 nights.",
        "icon": "fa-bed",
        "category": "Sleep",
        "sort_order": 140,
        "points": 25,
        "rule": {"type": "sleep_nights", "hours": 8, "minimum": 7},
    },
    {
        "key": "sleep_8_month",
        "name": "Thirty Rested Nights",
        "description": "Sleep 8+ hours on 30 nights.",
        "icon": "fa-moon",
        "category": "Sleep",
        "sort_order": 141,
        "points": 75,
        "rule": {"type": "sleep_nights", "hours": 8, "minimum": 30},
    },
    {
        "key": "sleep_8_60",
        "name": "Sleep Saint",
        "description": "Sleep 8+ hours on 60 nights.",
        "icon": "fa-star-and-crescent",
        "category": "Sleep",
        "sort_order": 142,
        "points": 100,
        "rule": {"type": "sleep_nights", "hours": 8, "minimum": 60},
    },
    {
        "key": "sleep_7_14",
        "name": "Solid Two Weeks",
        "description": "Sleep 7+ hours on 14 nights.",
        "icon": "fa-moon",
        "category": "Sleep",
        "sort_order": 143,
        "points": 25,
        "rule": {"type": "sleep_nights", "hours": 7, "minimum": 14},
    },
    {
        "key": "sleep_7_50",
        "name": "Fifty Good Nights",
        "description": "Sleep 7+ hours on 50 nights.",
        "icon": "fa-moon",
        "category": "Sleep",
        "sort_order": 144,
        "points": 50,
        "rule": {"type": "sleep_nights", "hours": 7, "minimum": 50},
    },
    {
        "key": "sleep_total_50",
        "name": "Recharge Rookie",
        "description": "Track 50 total hours of sleep.",
        "icon": "fa-battery-half",
        "category": "Sleep",
        "sort_order": 145,
        "points": 10,
        "rule": {"type": "sleep_total", "minimum": 50},
    },
    {
        "key": "sleep_total_100",
        "name": "Century Snoozer",
        "description": "Track 100 total hours of sleep.",
        "icon": "fa-battery-full",
        "category": "Sleep",
        "sort_order": 146,
        "points": 25,
        "rule": {"type": "sleep_total", "minimum": 100},
    },
    {
        "key": "sleep_total_250",
        "name": "Deep Sleeper",
        "description": "Track 250 total hours of sleep.",
        "icon": "fa-cloud-moon",
        "category": "Sleep",
        "sort_order": 147,
        "points": 50,
        "rule": {"type": "sleep_total", "minimum": 250},
    },
    {
        "key": "sleep_total_500",
        "name": "Rest Baron",
        "description": "Track 500 total hours of sleep.",
        "icon": "fa-bed",
        "category": "Sleep",
        "sort_order": 148,
        "points": 75,
        "rule": {"type": "sleep_total", "minimum": 500},
    },
    {
        "key": "sleep_best_9",
        "name": "Nine-Hour Nirvana",
        "description": "Sleep 9+ hours in one night.",
        "icon": "fa-bed",
        "category": "Sleep",
        "sort_order": 149,
        "points": 10,
        "rule": {"type": "sleep_best", "minimum": 9},
    },
    {
        "key": "sleep_best_10",
        "name": "Double-Digit Dreams",
        "description": "Sleep 10+ hours in one night.",
        "icon": "fa-bed",
        "category": "Sleep",
        "sort_order": 150,
        "points": 25,
        "rule": {"type": "sleep_best", "minimum": 10},
    },
]


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
