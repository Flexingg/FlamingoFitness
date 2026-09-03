"""Gamification, Effort XP Calculation & Skill-Tree Progression Service.

Architecture & Core Responsibilities:
1. **Activity Processing Pipeline**:
   - `process_payload`: Ingests sensor/health activity payloads from Apple HealthKit,
     Android Health Connect, or manual web entries.
   - Converts raw biometric data (steps, cardio minutes, tonnage lifted, water consumed,
     sleep duration/scores) into normalized "Effort XP".
2. **Modality XP Algorithms**:
   - `endurance_xp`: Zone 2/3 (1.0x/min), Zone 4/5 HIIT (1.5x/min).
   - `strength_xp`: Calculated from volume load / tonnage with RPE effort scaling.
   - `nutrition_xp`: Macro adherence within target thresholds (protein & calories).
   - `hydration_xp`: Milestones for meeting daily fluid requirements (ml).
   - `recovery_xp`: Sleep duration and readiness scores above threshold.
3. **Skill Tree & Leveling Engine**:
   - `apply_to_skill_tree`: Distributes earned XP to corresponding modality trees.
   - Handles level-up triggers (100 XP per level) and bonus token payouts.
"""

import logging

from django.db import transaction
from django.utils import timezone

from ..models import (
    Modality,
    Provider,
    RawActivityLog,
    SkillTree,
    XPLedger,
)
from .combat import (
    TOKEN_BOSS_PR,
    TOKEN_PERFECT_HYDRATION,
    TOKEN_PERFECT_MACRO,
    award_tokens,
)
from .game_config import GAMEPLAY

logger = logging.getLogger(__name__)

# One level of a skill tree = 100 XP (config/gameplay.json).
XP_PER_LEVEL = int(GAMEPLAY["progression"]["xp_per_level"])

# Readiness threshold below which a rest day is mandated (Step 15).
REST_DAY_THRESHOLD = int(GAMEPLAY["progression"]["rest_day_threshold"])


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
    """Tiered Sleep Recovery XP:
    8.0h+ = 50 XP (optimal recovery)
    7.0-7.9h = 35 XP (close to 8h goal)
    6.0-6.9h = 25 XP (moderate rest)
    5.0-5.9h = 15 XP (light rest)
    <5.0h = 0 XP (below recovery threshold)
    """
    try:
        h = float(hours or 0)
    except (TypeError, ValueError):
        return 0
    if h >= 8.0:
        return 50
    if h >= 7.0:
        return 35
    if h >= 6.0:
        return 25
    if h >= 5.0:
        return 15
    return 0


def body_battery_xp(charge):
    """+1 XP per point of body battery charge recovered overnight."""
    return int(round(float(charge or 0)))


def protein_xp(protein, protein_goal):
    """XP for protein adherence (up to 25 XP):
    >= 100% of goal = 25 XP
    80% - 99% of goal = 15 XP
    60% - 79% of goal = 10 XP
    < 60% = 0 XP
    """
    if protein_goal is None or float(protein_goal) <= 0:
        return 25 if float(protein or 0) > 0 else 0
    ratio = float(protein or 0) / float(protein_goal)
    if ratio >= 1.0:
        return 25
    if ratio >= 0.80:
        return 15
    if ratio >= 0.60:
        return 10
    return 0


def calorie_xp(calories, calorie_goal):
    """XP for calorie budget adherence (up to 25 XP):
    <= 100% of goal = 25 XP
    101% - 110% of goal (<= 10% over) = 15 XP
    111% - 120% of goal (<= 20% over) = 10 XP
    > 120% = 0 XP
    """
    if calorie_goal is None or float(calorie_goal) <= 0:
        return 25 if float(calories or 0) > 0 else 0
    cals = float(calories or 0)
    goal = float(calorie_goal)
    ratio = cals / goal
    if ratio <= 1.0:
        return 25
    if ratio <= 1.10:
        return 15
    if ratio <= 1.20:
        return 10
    return 0


def nutrition_xp(protein_or_perfect, calories=None, protein_goal=None, calorie_goal=None):
    """Calculate Nutrition XP (up to 50 XP total).
    Supports either:
      - nutrition_xp(perfect_macros: bool) -> 50 if True, 0 if False (legacy / binary)
      - nutrition_xp(protein, calories, protein_goal, calorie_goal) -> tiered sum of protein & calorie XP
    """
    if isinstance(protein_or_perfect, bool):
        return 50 if protein_or_perfect else 0
    if calories is None and protein_goal is None and calorie_goal is None:
        if isinstance(protein_or_perfect, (int, float)):
            return int(protein_or_perfect)
        return 50 if bool(protein_or_perfect) else 0

    p_xp = protein_xp(protein_or_perfect, protein_goal)
    c_xp = calorie_xp(calories, calorie_goal)
    return p_xp + c_xp


def nutrition_tokens(protein, calories, protein_goal, calorie_goal):
    """Calculate token reward for nutrition:
    - Perfection (>= 100% protein AND <= 100% calories) = 25 tokens (TOKEN_PERFECT_MACRO)
    - Strong effort / close (XP >= 35, e.g. both close or one hit + one close) = 10 tokens
    - Single milestone hit / partial (XP >= 20, e.g. hit protein or hit calories) = 5 tokens
    - Otherwise = 0 tokens
    """
    if protein_goal is None or calorie_goal is None:
        return 0
    pro_hit = float(protein or 0) >= float(protein_goal)
    cal_hit = float(calories or 0) <= float(calorie_goal)
    if pro_hit and cal_hit:
        return TOKEN_PERFECT_MACRO
    xp = nutrition_xp(protein, calories, protein_goal, calorie_goal)
    if xp >= 35:
        return 10
    if xp >= 20:
        return 5
    return 0


def hydration_xp(water, water_goal):
    """Tiered Hydration XP (up to 30 XP):
    >= 100% of goal = 30 XP
    80% - 99% of goal = 20 XP
    60% - 79% of goal = 10 XP
    < 60% = 0 XP
    """
    if water_goal is None or float(water_goal) <= 0:
        return 30 if float(water or 0) > 0 else 0
    ratio = float(water or 0) / float(water_goal)
    if ratio >= 1.0:
        return 30
    if ratio >= 0.80:
        return 20
    if ratio >= 0.60:
        return 10
    return 0


def hydration_tokens(water, water_goal):
    """Calculate token reward for hydration:
    >= 100% of goal = 10 tokens (TOKEN_PERFECT_HYDRATION)
    80% - 99% of goal = 5 tokens
    < 80% = 0 tokens
    """
    if water_goal is None or float(water_goal) <= 0:
        return 0
    ratio = float(water or 0) / float(water_goal)
    if ratio >= 1.0:
        return TOKEN_PERFECT_HYDRATION
    if ratio >= 0.80:
        return 5
    return 0


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
    # Persist EVERY grant (level-up or not) - previously the save lived only
    # inside the while loop, so any sub-100 XP entry was mutated in memory but
    # never written and the skill tree silently showed 0 XP.
    tree.save(update_fields=["level", "xp", "total_xp"])
    return tree


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

    # 1 XP per 10 calories burned, minimum 10 XP
    xp = max(10, int(total_calories / 10))

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
        award_tokens(raw_log.user, TOKEN_BOSS_PR)
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
    payload = raw_log.payload or {}
    pro_hit = bool(payload.get("protein_hit"))
    cal_hit = bool(payload.get("under_calorie"))

    if pro_hit and cal_hit:
        xp = 50
        tokens = TOKEN_PERFECT_MACRO
        desc = "Perfect macros: protein goal + under calories"
    elif pro_hit:
        xp = 25
        tokens = 5
        desc = "Protein goal hit"
    elif cal_hit:
        xp = 25
        tokens = 5
        desc = "Calorie target met"
    else:
        return []

    if tokens > 0:
        award_tokens(raw_log.user, tokens)
    return [
        XPLedger(
            user=raw_log.user,
            modality=Modality.NUTRITION,
            amount=xp,
            description=desc,
        )
    ]


@_register("hydration")
def _handle_hydration(raw_log):
    """SparkyFitness hydration log (water intake).

    Payload: {"date": ..., "water_intake_entries": [{"time": ..., "amount": ...}...],
              "water_goal": ...}.
    Tiered Hydration: 100%+ = 30 XP (+10 tokens), 80-99% = 20 XP (+5 tokens), 60-79% = 10 XP.
    """
    payload = raw_log.payload or {}
    entries = payload.get("water_intake_entries") or []
    water_goal = (
        payload.get("water_goal")
        or payload.get("water_goal_oz")
        or (payload.get("goals") or {}).get("water")
    )

    if entries:
        total_water = sum(float(item.get("amount", 0) or 0) for item in entries)
    else:
        direct_w = payload.get("water") or payload.get("water_oz") or payload.get("amount")
        if direct_w is None and payload.get("water_ml"):
            direct_w = float(payload.get("water_ml", 0) or 0) / 29.5735
        total_water = float(direct_w or 0)

    if water_goal is None:
        water_goal = 80.0

    xp = hydration_xp(total_water, water_goal)
    if xp <= 0:
        return []

    tokens = hydration_tokens(total_water, water_goal)
    if tokens > 0:
        award_tokens(raw_log.user, tokens)

    perfect = float(total_water) >= float(water_goal)
    desc_prefix = "Perfect hydration" if perfect else "Hydration progress"
    src_label = "Health Connect" if raw_log.source == Provider.HEALTH_CONNECT else ("HealthKit" if raw_log.source == Provider.HEALTHKIT else "SparkyFitness")
    return [
        XPLedger(
            user=raw_log.user,
            modality=Modality.HYDRATION,
            amount=xp,
            description=(
                f"{desc_prefix}: {int(total_water)} oz "
                f"goal {int(water_goal)} oz - {src_label}"
            ),
        )
    ]


def summarize_hydration(raw_log):
    """Build a UI-ready hydration summary for one RawActivityLog (SparkyFitness / Health Connect).

    Returns water intake vs goal, percentage, status badges,
    and the XP / tokens that the rulebook grants for it.
    """
    payload = raw_log.payload or {}
    entries = payload.get("water_intake_entries") or []
    water_goal = (
        payload.get("water_goal")
        or payload.get("water_goal_oz")
        or (payload.get("goals") or {}).get("water")
    )

    if entries:
        total_water = sum(float(e.get("amount", 0) or 0) for e in entries)
    else:
        # Direct water amount keys on payload
        direct_w = payload.get("water") or payload.get("water_oz") or payload.get("amount")
        if direct_w is None and payload.get("water_ml"):
            direct_w = float(payload.get("water_ml", 0) or 0) / 29.5735
        total_water = float(direct_w or 0)

    water_goal_f = float(water_goal) if water_goal is not None else None

    perfect = bool(water_goal_f is not None and total_water >= water_goal_f)
    xp = hydration_xp(total_water, water_goal_f)
    tokens = hydration_tokens(total_water, water_goal_f)

    date_str = payload.get("date") or raw_log.occurred_at.date().isoformat()

    water_pct = int(round((total_water / water_goal_f) * 100)) if water_goal_f else 0

    if perfect:
        status = "perfect"
        status_label = "ON TARGET"
    elif water_pct >= 80:
        status = "close"
        status_label = "CLOSE"
    elif water_pct >= 60:
        status = "partial"
        status_label = "PARTIAL"
    else:
        status = "needs_work"
        status_label = "Needs work"

    return {
        "date": date_str,
        "water": round(total_water, 1),
        "water_goal": round(water_goal_f, 1) if water_goal_f is not None else None,
        "water_pct": water_pct,
        "perfect": perfect,
        "status": status,
        "status_label": status_label,
        "xp": xp,
        "tokens": tokens,
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
    
    # Check direct total_calories_burned, total_calories, calories, calories_burned, or sum entries
    total_calories = float(
        payload.get("total_calories_burned")
        or payload.get("total_calories")
        or payload.get("calories")
        or payload.get("calories_burned")
        or sum(float(e.get("calories_burned", e.get("calories", 0)) or 0) for e in entries)
        or 0
    )
    total_minutes = float(
        payload.get("total_duration_minutes")
        or payload.get("duration_minutes")
        or payload.get("minutes")
        or sum(float(e.get("duration_minutes", e.get("minutes", 0)) or 0) for e in entries)
        or 0
    )
    date_str = payload.get("date") or raw_log.occurred_at.date().isoformat()

    # XP from the rulebook: 1 XP per 10 cal, min 10 XP
    xp = max(10, int(total_calories / 10)) if total_calories > 0 else 0

    return {
        "date": date_str,
        "total_calories_burned": round(total_calories, 1),
        "total_duration_minutes": round(total_minutes, 1),
        "exercise_count": len(entries),
        "xp": xp,
        "tokens": 0,
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
    
    calc_volume = sum(float(e.get("volume_lbs", (float(e.get("weight", 0) or 0) * float(e.get("reps", 0) or 0) * max(1, int(e.get("sets", 1) or 1)))) or 0) for e in exercises)
    volume = float(payload.get("total_volume_lbs") or payload.get("volume_lbs") or payload.get("volume") or calc_volume or 0)
    
    calc_sets = sum(int(e.get("sets", 1) or 1) for e in exercises)
    total_sets = int(payload.get("total_sets") or payload.get("sets") or calc_sets or 0)
    
    duration = float(payload.get("duration_minutes") or payload.get("minutes") or 0)
    date_str = payload.get("date") or raw_log.occurred_at.date().isoformat()

    xp = strength_xp(volume, payload.get("completed", False))
    xp += session_time_xp(duration)
    pr = bool(payload.get("pr"))
    tokens = TOKEN_BOSS_PR if pr else 0

    return {
        "date": date_str,
        "program": payload.get("program", "Workout"),
        "day_name": payload.get("day_name", ""),
        "duration_minutes": round(duration, 1),
        "total_volume_lbs": round(volume, 1),
        "total_sets": total_sets,
        "exercise_count": len(exercises),
        "xp": xp,
        "tokens": tokens,
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

    Returns hours slept, deep/REM percentages, status, and the Recovery XP the rulebook
    grants for it (8h+ = 50 XP, 7h+ = 35 XP, 6h+ = 25 XP, 5h+ = 15 XP).
    """
    payload = raw_log.payload or {}
    hours = float(payload.get("sleep_hours") or payload.get("hours") or payload.get("duration_hours") or 0)
    date_str = payload.get("date") or raw_log.occurred_at.date().isoformat()
    xp = sleep_xp(hours)

    if hours >= 8.0:
        status = "perfect"
        status_label = "OPTIMAL"
    elif hours >= 7.0:
        status = "close"
        status_label = "GOOD"
    elif hours >= 6.0:
        status = "partial"
        status_label = "MODERATE"
    elif hours >= 5.0:
        status = "light"
        status_label = "LIGHT"
    else:
        status = "needs_work"
        status_label = "LOW"

    return {
        "date": date_str,
        "sleep_hours": round(hours, 1),
        "deep_pct": int(payload.get("deep_pct", 0) or 0),
        "rem_pct": int(payload.get("rem_pct", 0) or 0),
        "xp": xp,
        "status": status,
        "status_label": status_label,
    }


@_register("nutrition")
def _handle_nutrition(raw_log):
    """SparkyFitness nutrition log (docs/10).

    Payload: {"date": ..., "food_entries": [{protein, calories}...],
              "goals": {"protein": ..., "calories": ...}}.
    Tiered rewards for protein adherence + calorie budget management.
    """
    payload = raw_log.payload or {}
    entries = payload.get("food_entries") or []
    goals = payload.get("goals") or {}

    if entries:
        total_pro = sum(float(item.get("protein", 0) or 0) for item in entries)
        total_cals = sum(float(item.get("calories", 0) or 0) for item in entries)
    else:
        total_pro = float(payload.get("protein", 0) or 0)
        total_cals = float(payload.get("calories", 0) or 0)

    pro_goal = goals.get("protein") or payload.get("protein_goal")
    cal_goal = goals.get("calories") or payload.get("calorie_goal")
    if pro_goal is None or cal_goal is None:
        return []

    xp = nutrition_xp(total_pro, total_cals, pro_goal, cal_goal)
    if xp <= 0:
        return []

    tokens = nutrition_tokens(total_pro, total_cals, pro_goal, cal_goal)
    if tokens > 0:
        award_tokens(raw_log.user, tokens)

    perfect = total_pro >= float(pro_goal) and total_cals <= float(cal_goal)
    desc_prefix = "Perfect macros" if perfect else "Nutrition progress"
    return [
        XPLedger(
            user=raw_log.user,
            modality=Modality.NUTRITION,
            amount=xp,
            description=(
                f"{desc_prefix}: {int(total_pro)}g protein "
                f"({int(total_cals)} kcal) - SparkyFitness"
            ),
        )
    ]

def summarize_nutrition(raw_log):
    """Build a UI-ready nutrition summary for one RawActivityLog (SparkyFitness).

    Returns protein/calories vs goals, macro percentages, status flags,
    and the XP / tokens that the rulebook grants for it.
    """
    payload = raw_log.payload or {}
    entries = payload.get("food_entries") or []
    goals = payload.get("goals") or {}

    if entries:
        total_pro = sum(float(e.get("protein", 0) or 0) for e in entries)
        total_cals = sum(float(e.get("calories", 0) or 0) for e in entries)
    else:
        total_pro = float(payload.get("protein", 0) or 0)
        total_cals = float(payload.get("calories", 0) or 0)

    pro_goal = goals.get("protein") or payload.get("protein_goal")
    cal_goal = goals.get("calories") or payload.get("calorie_goal")
    pro_goal_f = float(pro_goal) if pro_goal is not None else None
    cal_goal_f = float(cal_goal) if cal_goal is not None else None

    perfect = bool(
        pro_goal_f is not None
        and cal_goal_f is not None
        and total_pro >= pro_goal_f
        and total_cals <= cal_goal_f
    )
    xp = nutrition_xp(total_pro, total_cals, pro_goal_f, cal_goal_f)
    tokens = nutrition_tokens(total_pro, total_cals, pro_goal_f, cal_goal_f)

    date_str = payload.get("date") or raw_log.occurred_at.date().isoformat()

    protein_pct = int(round((total_pro / pro_goal_f) * 100)) if pro_goal_f else 0
    calorie_pct = int(round((total_cals / cal_goal_f) * 100)) if cal_goal_f else 0

    if perfect:
        status = "perfect"
        status_label = "PERFECT"
    elif xp >= 35:
        status = "close"
        status_label = "CLOSE"
    elif xp >= 15:
        status = "partial"
        status_label = "PARTIAL"
    else:
        status = "needs_work"
        status_label = "Needs work"

    return {
        "date": date_str,
        "protein": round(total_pro, 1),
        "protein_goal": round(pro_goal_f, 1) if pro_goal_f is not None else None,
        "calories": int(round(total_cals)),
        "calorie_goal": int(round(cal_goal_f)) if cal_goal_f is not None else None,
        "protein_pct": protein_pct,
        "calorie_pct": calorie_pct,
        "perfect": perfect,
        "status": status,
        "status_label": status_label,
        "xp": xp,
        "tokens": tokens,
        "food_entries": [
            {
                "id": str(e.get("id") or e.get("sparky_id") or f"entry-{idx}"),
                "sparky_id": e.get("sparky_id") or (e.get("id") if (isinstance(e.get("id"), str) and len(e.get("id")) > 20) else None),
                "name": e.get("food_name") or e.get("name", "") or "Food",
                "food_name": e.get("food_name") or e.get("name", "") or "Food",
                "protein": round(float(e.get("protein", 0) or 0), 1),
                "calories": int(round(float(e.get("calories", 0) or 0))),
                "carbs": round(float(e.get("carbs", 0) or 0), 1),
                "fat": round(float(e.get("fat", 0) or 0), 1),
                "quantity": float(e.get("quantity", 1.0) or 1.0),
                "unit": str(e.get("unit") or e.get("serving") or "serving"),
                "serving": str(e.get("serving") or e.get("unit") or "serving"),
                "meal_type": str(e.get("meal_type") or "Lunch").capitalize(),
                "brand": str(e.get("brand_name") or e.get("brand") or ""),
                "brand_name": str(e.get("brand_name") or e.get("brand") or ""),
                "food_id": e.get("food_id"),
                "variant_id": e.get("variant_id"),
                "base_calories": float(e.get("base_calories") or e.get("calories") or 0),
                "base_protein": float(e.get("base_protein") or e.get("protein") or 0),
                "base_carbs": float(e.get("base_carbs") or e.get("carbs") or 0),
                "base_fat": float(e.get("base_fat") or e.get("fat") or 0),
            }
            for idx, e in enumerate(entries)
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

    # Record which raw log produced each entry.
    for entry in entries:
        entry.raw_log = holder

    created = XPLedger.objects.bulk_create(entries)
    for entry in created:
        apply_to_skill_tree(entry.user, entry.modality, entry.amount)

    if raw_log is not None:
        raw_log.processed = True
        raw_log.save(update_fields=["processed"])

    # Auto-evaluate any active fitness bounties/duels for this user
    try:
        from .bounties import evaluate_user_bounties
        evaluate_user_bounties(user)
    except Exception:  # noqa: BLE001
        pass

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

