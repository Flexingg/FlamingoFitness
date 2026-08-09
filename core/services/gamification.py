"""Gamification service layer (Steps 13 & 14).

Implements the "Effort XP" rulebook from docs/03_gamification_math.md.

The main entry points are:

  * ``process_payload(user, source, event_type, payload, raw_log=None)``
    converts a single payload into XP / resources.
  * ``process_log(raw_log)`` wraps the above for a stored RawActivityLog and
    marks it processed.

Skill-tree progression (Step 14) is applied automatically by ``apply_to_skill_tree``
as each XP entry is created.
"""

import logging

from django.db import transaction
from django.utils import timezone

from ..models import (
    BaseResource,
    Modality,
    RawActivityLog,
    SkillTree,
    XPLedger,
)
from .base_economy import (
    base_xp_bonus_pct,
    maybe_drop_blueprint,
    log_modality_workout,
)

logger = logging.getLogger(__name__)

# One level of a skill tree = 100 XP.
XP_PER_LEVEL = 100

# Readiness threshold below which a rest day is mandated (Step 15).
REST_DAY_THRESHOLD = 50

# Resource rewards for certain events.
PERFECT_MACRO_MATERIALS = 10
BOSS_TIME_SPEEDUPS = 5


# ---------------------------------------------------------------------------
# Effort XP math (docs/03_gamification_math.md)
# ---------------------------------------------------------------------------
def endurance_xp(minutes, intensity=""):
    """Zone 2/3 = x1.0/min, Zone 4/5 (HIIT) = x1.5/min."""
    hot = ("hiit", "zone4", "zone5", "high")
    multiplier = 1.5 if any(k in str(intensity).lower() for k in hot) else 1.0
    return int(round(minutes * multiplier))


def strength_xp(volume_lbs, completed=False):
    """1 XP per 1,000 lbs moved, plus +20 completion bonus."""
    xp = volume_lbs // 1000
    if completed:
        xp += 20
    return xp


def session_time_xp(minutes):
    """+1 XP per 30 minutes lifted (supports time-based rewarding)."""
    try:
        return int(float(minutes or 0)) // 30
    except (TypeError, ValueError):
        return 0


def sleep_xp(hours):
    """8h = 50 XP; 5-8h = 20 XP; <5h = 0 XP."""
    if hours >= 8:
        return 50
    if hours >= 5:
        return 20
    return 0


def body_battery_xp(charge):
    """+1 XP per point of body battery charge recovered overnight."""
    return int(round(float(charge or 0)))


def nutrition_xp(perfect_macros):
    """Perfect macros (protein hit + under calorie) = +50 Nutrition XP."""
    return 50 if perfect_macros else 0

# ---------------------------------------------------------------------------
# Resource helpers
# ---------------------------------------------------------------------------
def award_resources(user, materials=0, energy=0, time_speedups=0):
    """Increment the user's base-building resources."""
    resources, _ = BaseResource.objects.get_or_create(user=user)
    resources.materials = max(0, resources.materials + materials)
    resources.energy = max(0, resources.energy + energy)
    resources.time_speedups = max(0, resources.time_speedups + time_speedups)
    resources.save(update_fields=["materials", "energy", "time_speedups"])
    return resources


# ---------------------------------------------------------------------------
# Skill tree progression (Step 14)
# ---------------------------------------------------------------------------
@transaction.atomic
def apply_to_skill_tree(user, modality, amount):
    """Apply XP to a skill tree, handling level-ups and progress thresholds."""
    tree, _ = SkillTree.objects.get_or_create(
        user=user, modality=modality, defaults={"level": 1, "xp": 0, "total_xp": 0}
    )
    tree.total_xp += amount
    tree.xp += amount
    # Handle level-ups (carry-over XP spills into the next level).
    while tree.xp >= XP_PER_LEVEL:
        tree.xp -= XP_PER_LEVEL
        tree.level += 1
        tree.save(update_fields=["level", "xp", "total_xp"])
    return tree


def _apply_modality_buff(user, modality):
    """Phase 7 (docs/09 §5.7): grant a 24h production buff for a logged workout.

    ``"strength"`` handler -> ``"strength"``; ``cardio``/``endurance`` handlers
    -> ``"cardio"``. Non-fatal so an economy error never loses the XP award.
    """
    try:
        resources, _ = BaseResource.objects.get_or_create(user=user)
        log_modality_workout(resources, modality)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to set %s modality buff; XP already awarded.", modality
        )


# ---------------------------------------------------------------------------
# Payload -> XP dispatch
# ---------------------------------------------------------------------------
_HANDLERS = {}


def _register(event_type):
    def deco(fn):
        _HANDLERS[event_type] = fn
        return fn

    return deco


@_register("cardio")
def _handle_cardio(raw_log):
    payload = raw_log.payload
    xp = endurance_xp(payload.get("minutes", 0), payload.get("intensity", ""))
    if xp <= 0:
        return []
    # Phase 7 (docs/09 §5.7): cardio workouts set a 24h cardio production buff.
    _apply_modality_buff(raw_log.user, "cardio")
    return [
        XPLedger(
            user=raw_log.user,
            modality=Modality.ENDURANCE,
            amount=xp,
            description=f"{payload.get('class', 'Cardio')} "
            f"({payload.get('minutes', 0)} min)",
        )
    ]



@_register("endurance")
def _handle_endurance(raw_log):
    """SparkyFitness exercise entries (calories burned)."""

    payload = raw_log.payload
    total_calories = float(payload.get("total_calories_burned", 0) or 0)

    if total_calories <= 0:
        return []

    # Phase 7 (docs/09 section 5.7): exercise (endurance/cardio) sets a 24h cardio buff.
    _apply_modality_buff(raw_log.user, "cardio")

    # 1 XP per 10 calories burned, minimum 10 XP
    xp = max(10, int(total_calories / 10))

    # Bonus materials for high calorie burns (500+ cal = +5 materials)
    materials = 5 if total_calories >= 500 else 0
    if materials:
        award_resources(raw_log.user, materials=materials)

    entry_count = len(payload.get("exercise_entries", []))
    total_min = payload.get("total_duration_minutes", 0)
    return [
        XPLedger(
            user=raw_log.user,
            modality=Modality.ENDURANCE,
            amount=xp,
            description=(f"{total_calories:.0f} cal burned ({total_min:.0f} min, "
                         f"{entry_count} exercise{'s' if entry_count != 1 else ''})"),
        )
    ]


@_register("strength")
def _handle_strength(raw_log):
    payload = raw_log.payload
    volume = payload.get("total_volume_lbs", payload.get("volume_lbs", 0)) or 0
    xp = strength_xp(volume, payload.get("completed", False))
    # Add a modest time-based component: +1 XP per 30 minutes lifted.
    xp += session_time_xp(payload.get("duration_minutes", 0) or 0)

    entries = []
    if xp > 0:
        entries.append(
            XPLedger(
                user=raw_log.user,
                modality=Modality.STRENGTH,
                amount=xp,
                description=f"{payload.get('program', 'Workout')} "
                f"({int(volume):,} lbs)",
            )
        )

    # Boss fight: a new weekly PR doubles that workout's XP (Step 13).
    if payload.get("pr"):
        entries.append(
            XPLedger(
                user=raw_log.user,
                modality=Modality.STRENGTH,
                amount=xp,
                description="Boss fight: weekly PR! (2x multiplier)",
            )
        )
        award_resources(raw_log.user, time_speedups=BOSS_TIME_SPEEDUPS)
        # Phase 7 (docs/09 section 5.7): a PR boss fight rolls a rare blueprint.
        try:
            maybe_drop_blueprint(raw_log.user)
        except Exception:  # noqa: BLE001
            logger.exception('Blueprint drop roll failed; strength XP already awarded.')
    # Phase 7 (docs/09 section 5.7): strength workouts set a 24h strength production buff.
    _apply_modality_buff(raw_log.user, 'strength')
    return entries


@_register("sleep")
def _handle_sleep(raw_log):
    xp = sleep_xp(raw_log.payload.get("sleep_hours", 0) or 0)
    if xp <= 0:
        return []
    return [
        XPLedger(
            user=raw_log.user,
            modality=Modality.RECOVERY,
            amount=xp,
            description=f"Sleep {raw_log.payload.get('sleep_hours', 0)}h",
        )
    ]


@_register("body_battery")
def _handle_body_battery(raw_log):
    xp = body_battery_xp(raw_log.payload.get("charge", 0))
    if xp <= 0:
        return []
    return [
        XPLedger(
            user=raw_log.user,
            modality=Modality.RECOVERY,
            amount=xp,
            description=f"Body battery +{xp} recovered",
        )
    ]


@_register("macro")
def _handle_macro(raw_log):
    payload = raw_log.payload
    perfect = bool(payload.get("protein_hit")) and bool(payload.get("under_calorie"))
    xp = nutrition_xp(perfect)
    if xp <= 0:
        return []
    award_resources(raw_log.user, materials=PERFECT_MACRO_MATERIALS)
    return [
        XPLedger(
            user=raw_log.user,
            modality=Modality.NUTRITION,
            amount=xp,
            description="Perfect macros: protein goal + under calories",
        )
    ]


@_register("hydration")
def _handle_hydration(raw_log):
    """SparkyFitness hydration log (water intake).

    Payload: {"date": ..., "water_intake_entries": [{"time": ..., "amount": ...}...],
              "water_goal": ...}.
    Perfect hydration = total water intake >= water goal.
    """
    payload = raw_log.payload
    entries = payload.get("water_intake_entries") or []
    water_goal = payload.get("water_goal")

    total_water = sum(float(item.get("amount", 0) or 0) for item in entries)

    if water_goal is None:
        return []

    perfect = total_water >= float(water_goal)
    if not perfect:
        return []

    award_resources(raw_log.user, materials=5)
    return [
        XPLedger(
            user=raw_log.user,
            modality=Modality.HYDRATION,
            amount=30,
            description=(
                f"Perfect hydration: {int(total_water)} oz "
                f"goal {int(water_goal)} oz - SparkyFitness"
            ),
        )
    ]


def summarize_hydration(raw_log):
    """Build a UI-ready hydration summary for one RawActivityLog (SparkyFitness).

    Returns water intake vs goal, percentage, the "perfect hydration" flag,
    and the XP / Base Materials that the rulebook grants for it.
    """
    payload = raw_log.payload or {}
    entries = payload.get("water_intake_entries") or []
    water_goal = payload.get("water_goal")

    total_water = sum(float(e.get("amount", 0) or 0) for e in entries)

    water_goal_f = float(water_goal) if water_goal is not None else None

    perfect = bool(water_goal_f is not None and total_water >= water_goal_f)
    xp = 30 if perfect else 0
    materials = 5 if perfect else 0

    date_str = payload.get("date") or raw_log.occurred_at.date().isoformat()

    water_pct = int(round((total_water / water_goal_f) * 100)) if water_goal_f else 0

    return {
        "date": date_str,
        "water": round(total_water, 1),
        "water_goal": round(water_goal_f, 1) if water_goal_f is not None else None,
        "water_pct": water_pct,
        "perfect": perfect,
        "xp": xp,
        "materials": materials,
        "water_intake_entries": [
            {
                "time": e.get("time") or e.get("logged_at") or "",
                "amount": round(float(e.get("amount", 0) or 0), 1),
            }
            for e in entries
        ],
    }




def summarize_endurance(raw_log):
    """Build a UI-ready endurance summary for one RawActivityLog (SparkyFitness)."""
    payload = raw_log.payload or {}
    entries = payload.get("exercise_entries") or []
    total_calories = float(payload.get("total_calories_burned", 0) or 0)
    total_minutes = float(payload.get("total_duration_minutes", 0) or 0)
    date_str = payload.get("date") or raw_log.occurred_at.date().isoformat()

    # XP from the rulebook: 1 XP per 10 cal, min 10 XP
    xp = max(10, int(total_calories / 10)) if total_calories > 0 else 0
    # Materials for 500+ cal burns
    materials = 5 if total_calories >= 500 else 0

    return {
        "date": date_str,
        "total_calories_burned": round(total_calories, 1),
        "total_duration_minutes": round(total_minutes, 1),
        "exercise_count": len(entries),
        "xp": xp,
        "materials": materials,
        "exercise_entries": [
            {
                "name": e.get("name", "Exercise"),
                "calories_burned": round(float(e.get("calories_burned", 0) or 0), 1),
                "duration_minutes": round(float(e.get("duration_minutes", 0) or 0), 1),
                "notes": e.get("notes", ""),
            }
            for e in entries
        ],
    }
def summarize_strength(raw_log):
    """Build a UI-ready strength summary for one RawActivityLog (Liftosaur).

    Returns the workout's volume / duration / sets, the exercises performed
    (with heaviest weight + Epley est. 1RM), and the XP / materials the rulebook
    grants for it.
    """
    payload = raw_log.payload or {}
    exercises = payload.get("exercises") or []
    volume = float(payload.get("total_volume_lbs", payload.get("volume_lbs", 0)) or 0)
    duration = float(payload.get("duration_minutes", 0) or 0)
    date_str = payload.get("date") or raw_log.occurred_at.date().isoformat()

    xp = strength_xp(volume, payload.get("completed", False))
    xp += session_time_xp(duration)
    pr = bool(payload.get("pr"))
    materials = 5 if pr else 0

    return {
        "date": date_str,
        "program": payload.get("program", "Workout"),
        "day_name": payload.get("day_name", ""),
        "duration_minutes": round(duration, 1),
        "total_volume_lbs": round(volume, 1),
        "total_sets": int(payload.get("total_sets", payload.get("sets", 0)) or 0),
        "exercise_count": len(exercises),
        "xp": xp,
        "materials": materials,
        "pr": pr,
        "completed": bool(payload.get("completed", True)),
        "exercises": [
            {
                "name": e.get("name", "Exercise"),
                "sets": int(e.get("sets", 0) or 0),
                "reps": int(e.get("reps", 0) or 0),
                "weight": round(float(e.get("weight", 0) or 0), 1),
                "unit": e.get("unit", "lb"),
                "volume_lbs": round(float(e.get("volume_lbs", 0) or 0), 1),
                "est_1rm": round(float(e.get("est_1rm", 0) or 0), 1),
            }
            for e in exercises
        ],
    }


def summarize_sleep(raw_log):
    """Build a UI-ready sleep summary for one RawActivityLog (SparkyFitness).

    Returns hours slept, deep/REM percentages, and the Recovery XP the rulebook
    (docs/03) grants for it (8h+ = 50 XP, 5-8h = 20 XP).
    """
    payload = raw_log.payload or {}
    hours = float(payload.get("sleep_hours", 0) or 0)
    date_str = payload.get("date") or raw_log.occurred_at.date().isoformat()

    return {
        "date": date_str,
        "sleep_hours": round(hours, 1),
        "deep_pct": int(payload.get("deep_pct", 0) or 0),
        "rem_pct": int(payload.get("rem_pct", 0) or 0),
        "xp": sleep_xp(hours),
    }


@_register("nutrition")
def _handle_nutrition(raw_log):
    """SparkyFitness nutrition log (docs/10).

    Payload: {"date": ..., "food_entries": [{protein, calories}...],
              "goals": {"protein": ..., "calories": ...}}.
    Perfect macros = protein goal met AND under the calorie cap.
    """
    payload = raw_log.payload
    entries = payload.get("food_entries") or []
    goals = payload.get("goals") or {}

    total_pro = sum(float(item.get("protein", 0) or 0) for item in entries)
    total_cals = sum(float(item.get("calories", 0) or 0) for item in entries)

    pro_goal = goals.get("protein")
    cal_goal = goals.get("calories")
    if pro_goal is None or cal_goal is None:
        return []

    perfect = total_pro >= float(pro_goal) and total_cals <= float(cal_goal)
    if not perfect:
        return []

    award_resources(raw_log.user, materials=PERFECT_MACRO_MATERIALS)
    return [
        XPLedger(
            user=raw_log.user,
            modality=Modality.NUTRITION,
            amount=50,
            description=(
                f"Perfect macros: {int(total_pro)}g protein "
                f"({int(total_cals)} kcal) - SparkyFitness"
            ),
        )
    ]

def summarize_nutrition(raw_log):
    """Build a UI-ready nutrition summary for one RawActivityLog (SparkyFitness).

    Returns protein/calories vs goals, macro percentages, the "perfect macros"
    flag, and the XP / Base Materials that the rulebook (docs/03) grants for it.
    """
    payload = raw_log.payload or {}
    entries = payload.get("food_entries") or []
    goals = payload.get("goals") or {}

    total_pro = sum(float(e.get("protein", 0) or 0) for e in entries)
    total_cals = sum(float(e.get("calories", 0) or 0) for e in entries)

    pro_goal = goals.get("protein")
    cal_goal = goals.get("calories")
    pro_goal_f = float(pro_goal) if pro_goal is not None else None
    cal_goal_f = float(cal_goal) if cal_goal is not None else None

    # Perfect macros = protein goal met (at/over) AND under the calorie cap.
    perfect = bool(
        pro_goal_f is not None
        and cal_goal_f is not None
        and total_pro >= pro_goal_f
        and total_cals <= cal_goal_f
    )
    xp = nutrition_xp(perfect)
    materials = PERFECT_MACRO_MATERIALS if perfect else 0

    date_str = payload.get("date") or raw_log.occurred_at.date().isoformat()

    protein_pct = int(round((total_pro / pro_goal_f) * 100)) if pro_goal_f else 0
    calorie_pct = int(round((total_cals / cal_goal_f) * 100)) if cal_goal_f else 0

    return {
        "date": date_str,
        "protein": round(total_pro, 1),
        "protein_goal": round(pro_goal_f, 1) if pro_goal_f is not None else None,
        "calories": int(round(total_cals)),
        "calorie_goal": int(round(cal_goal_f)) if cal_goal_f is not None else None,
        "protein_pct": protein_pct,
        "calorie_pct": calorie_pct,
        "perfect": perfect,
        "xp": xp,
        "materials": materials,
        "food_entries": [
            {
                # The API returns "food_name" (GAS: entry.food_name).
                # Fall back to "name" for any older payload shape.
                "name": e.get("food_name") or e.get("name", "") or "",
                "protein": round(float(e.get("protein", 0) or 0), 1),
                "calories": int(round(float(e.get("calories", 0) or 0))),
            }
            for e in entries
        ],
    }


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------
@transaction.atomic
def process_payload(user, source, event_type, payload, raw_log=None):
    """Convert one payload into XP ledger entries + skill tree updates.

    Returns the list of created XPLedger entries (empty if not applicable).
    ``raw_log`` is optional; if supplied it is marked processed afterwards.
    """
    if raw_log is not None and event_type != raw_log.event_type:
        raise ValueError("event_type does not match raw_log.event_type")

    if event_type not in _HANDLERS:
        return []

    # Reuse the caller's log (with correct payload) so the handler sees it.
    holder = raw_log
    if raw_log is None:
        holder = RawActivityLog(
            user=user,
            source=source,
            event_type=event_type,
            payload=payload,
            occurred_at=timezone.now(),
        )
        holder.save()

    entries = _HANDLERS[event_type](holder)

    # Phase 7 (docs/09 §5.9): buildings that grant XP% boost the effort XP
    # awarded by this log. Scaled before the rows are persisted so skill trees
    # see the same (capped) amount. Non-fatal - a scaling error never loses XP.
    if entries:
        try:
            bonus = base_xp_bonus_pct(entries[0].user)
            if bonus:
                for entry in entries:
                    if entry.amount > 0:
                        entry.amount = max(
                            1, int(round(entry.amount * (1 + bonus / 100.0)))
                        )
        except Exception:  # noqa: BLE001
            logger.exception("base_xp_bonus_pct scaling failed; awarding unscaled XP")

    # Record which raw log produced each entry.
    for entry in entries:
        entry.raw_log = holder

    created = XPLedger.objects.bulk_create(entries)
    for entry in created:
        apply_to_skill_tree(entry.user, entry.modality, entry.amount)

    if raw_log is not None:
        raw_log.processed = True
        raw_log.save(update_fields=["processed"])

    return created


@transaction.atomic
def process_log(raw_log):
    """Process a stored RawActivityLog into XP and mark it processed."""
    if raw_log.processed:
        return []
    user, source, event_type, payload = (
        raw_log.user,
        raw_log.source,
        raw_log.event_type,
        raw_log.payload,
    )
    return process_payload(user, source, event_type, payload, raw_log=raw_log)

