"""Top-nav stat explainer service.

Builds the "what is this stat + how did I earn it" payloads behind
``GET /api/v1/stats/<stat>/`` (opened by clicking the streak / materials /
energy badges in the dashboard's top nav).

Everything here is a pure derivation over data we already store -
``DailyReadiness``, ``RawActivityLog`` (via the tested ``summarize_*``
helpers), ``XPLedger`` and ``BaseResource`` - so no new ledger tables are
introduced (same philosophy as ``core/services/badges.py``).
"""

from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from ..models import (
    BaseBuilding,
    DailyReadiness,
    RawActivityLog,
    XPLedger,
)
from .base_economy import (
    ENERGY_CAP,
    ENERGY_PER_HOUR,
    POOLSIDE_ENERGY_BONUS,
    REST_DAY_ENERGY_BONUS,
    XP_TO_MATERIALS,
    evaluate_synergies,
    streak_multiplier,
    xp_dividend,
)
from .gamification import (
    summarize_endurance,
    summarize_hydration,
    summarize_nutrition,
    summarize_strength,
)

# Valid stat keys accepted by GET /api/v1/stats/<stat>/.
STAT_KEYS = ("streak", "materials", "energy")

# How far back (and how many rows) the history lists look.
HISTORY_WINDOW_DAYS = 30
HISTORY_LIMIT = 15
HARVEST_WINDOW_DAYS = 7
STREAK_HISTORY_DAYS = 14

# RawActivityLog event types that can grant materials, mapped to the
# summarizer that derives the grant from the stored payload (docs/03
# rulebook) and the human label/detail shown in the history list.
_MATERIAL_SOURCES = {
    "nutrition": (summarize_nutrition, "Perfect macros", "Protein goal met, stayed under calories"),
    "hydration": (summarize_hydration, "Perfect hydration", "Hit your daily water goal"),
    "endurance": (summarize_endurance, "Big burn", "500+ kcal workout"),
    "strength": (summarize_strength, "Strength PR", "Boss fight: new personal record"),
}


def _today():
    return timezone.localdate()


# ---------------------------------------------------------------------------
# Streak
# ---------------------------------------------------------------------------
def _streak_info(user, resources):
    """Streak = consecutive active days, protected (never broken) by readiness."""
    multiplier = streak_multiplier(user.streak)
    facts = [
        {"label": "Building production bonus", "value": f"{multiplier:.2f}x"},
        {"label": "Max bonus", "value": "1.50x at a 10-day streak"},
    ]
    how_to_earn = [
        "Show up on training days - your Garmin readiness card green-lights them.",
        "Low readiness mandates a rest day: your streak is frozen, never broken.",
        "A longer streak multiplies everything your base buildings produce.",
    ]

    history = []
    since = _today() - timedelta(days=STREAK_HISTORY_DAYS)
    records = DailyReadiness.objects.filter(user=user, date__gte=since).order_by(
        "-date"
    )[:STREAK_HISTORY_DAYS]
    for record in records:
        rest = record.streak_requirement == DailyReadiness.StreakRequirement.REST_DAY
        history.append(
            {
                "date": record.date.isoformat(),
                "label": "Rest day" if rest else "Training day",
                "detail": (
                    f"Readiness {record.score}% - streak protected, recover!"
                    if rest
                    else f"Readiness {record.score}% - counts toward your streak."
                ),
                "amount": "frozen" if rest else "+1",
            }
        )

    return {
        "stat": "streak",
        "name": "Streak",
        "icon": "fa-fire",
        "value": user.streak,
        "value_note": "days",
        "description": (
            "Consecutive days of showing up. Rest days freeze your streak - "
            "they never break it."
        ),
        "facts": facts,
        "how_to_earn": how_to_earn,
        "history": history,
        "empty_hint": (
            "No readiness days recorded yet - sync a provider and check in "
            "daily to start your streak."
        ),
    }


# ---------------------------------------------------------------------------
# Materials (the "gem" currency)
# ---------------------------------------------------------------------------
def _materials_info(user, resources):
    """Materials = base-building currency shown with the gem icon."""
    facts = [
        {
            "label": "Daily XP harvest",
            "value": f"1 material per {XP_TO_MATERIALS} XP",
        },
    ]
    producers = (
        BaseBuilding.objects.filter(user=user, level__gt=0)
        .select_related("building_def")
        .order_by("building_def__sort_order", "building_def__id")
    )
    for building in producers:
        rate = building.building_def.materials_per_day * building.level
        if rate:
            facts.append(
                {
                    "label": f"{building.building_def.name} Lv{building.level}",
                    "value": f"+{rate}/day (collect in Base)",
                }
            )

    how_to_earn = [
        f"Daily harvest: 1 material per {XP_TO_MATERIALS} XP you earn in a day.",
        "Collect the daily production of your base buildings in the Flamingo Club.",
        "Perfect macros (protein goal + under calories): +10.",
        "Perfect hydration (hit your water goal): +5.",
        "Burn 500+ kcal in an endurance workout: +5.",
        "Hit a strength PR (Boss fight): +5.",
    ]

    history = []
    since = timezone.now() - timedelta(days=HISTORY_WINDOW_DAYS)
    logs = (
        RawActivityLog.objects.filter(
            user=user,
            event_type__in=list(_MATERIAL_SOURCES),
            occurred_at__gte=since,
        )
        .order_by("-occurred_at")
    )
    for log in logs:
        summarizer, label, detail = _MATERIAL_SOURCES[log.event_type]
        try:
            summary = summarizer(log)
        except Exception:  # noqa: BLE001 - a bad payload never breaks the panel
            continue
        materials = int(summary.get("materials") or 0)
        if materials <= 0:
            continue
        history.append(
            {
                "date": summary.get("date") or log.occurred_at.date().isoformat(),
                "label": label,
                "detail": detail,
                "amount": f"+{materials}",
            }
        )

    # Daily XP -> materials harvest over the last week (XPLedger per day).
    harvest_since = _today() - timedelta(days=HARVEST_WINDOW_DAYS - 1)
    xp_days = (
        XPLedger.objects.filter(user=user, created_at__date__gte=harvest_since)
        .values("created_at__date")
        .annotate(day_xp=Sum("amount"))
        .order_by("-created_at__date")
    )
    for row in xp_days:
        minted = xp_dividend(row["day_xp"])
        if minted <= 0:
            continue
        history.append(
            {
                "date": row["created_at__date"].isoformat(),
                "label": "Daily XP harvest",
                "detail": f"{row['day_xp']} XP earned this day",
                "amount": f"+{minted}",
            }
        )

    history.sort(key=lambda item: item["date"], reverse=True)
    history = history[:HISTORY_LIMIT]

    return {
        "stat": "materials",
        "name": "Materials",
        "icon": "fa-gem",
        "value": resources.materials,
        "value_note": "gems in your wallet",
        "description": (
            "The gem currency of your Flamingo Club base. Earn it from "
            "fitness, spend it on buildings."
        ),
        "facts": facts,
        "how_to_earn": how_to_earn,
        "history": history,
        "empty_hint": (
            "Nothing earned recently - log workouts, hit your macros, or build "
            "up your base to start collecting."
        ),
    }


# ---------------------------------------------------------------------------
# Energy
# ---------------------------------------------------------------------------
def _energy_info(user, resources):
    """Energy = construction fuel with passive regen + rest-day spikes."""
    synergies = evaluate_synergies(user)
    poolside = "poolside_chill" in synergies
    rate = POOLSIDE_ENERGY_BONUS * ENERGY_PER_HOUR if poolside else ENERGY_PER_HOUR

    facts = [
        {"label": "Energy cap", "value": str(ENERGY_CAP)},
        {"label": "Passive regen", "value": f"+{rate:g} per hour"},
        {"label": "Rest-day bonus", "value": f"+{REST_DAY_ENERGY_BONUS} (ignores the cap)"},
    ]
    if getattr(resources, "last_rest_bonus_date", None):
        facts.append(
            {
                "label": "Last rest-day bonus",
                "value": resources.last_rest_bonus_date.isoformat(),
            }
        )
    if poolside:
        facts.append(
            {"label": "Poolside Chill synergy", "value": "+5% regen speed"}
        )

    how_to_earn = [
        f"Passive regen: +{rate:g}/hour, up to the {ENERGY_CAP} cap.",
        f"Rest days (readiness under 50): a one-time +{REST_DAY_ENERGY_BONUS} spike that can exceed the cap.",
        "A built Recovery Pool adds +5 to every rest-day bonus.",
        "Poolside Chill synergy (Pool Deck Lv2 + Cabana Lv2): +5% regen speed.",
        "Spend energy to start construction and upgrades in the Flamingo Club.",
    ]

    history = []
    since = _today() - timedelta(days=HISTORY_WINDOW_DAYS)
    rest_days = DailyReadiness.objects.filter(
        user=user,
        date__gte=since,
        streak_requirement=DailyReadiness.StreakRequirement.REST_DAY,
    ).order_by("-date")[:HISTORY_LIMIT]
    for record in rest_days:
        history.append(
            {
                "date": record.date.isoformat(),
                "label": "Rest-day energy bonus",
                "detail": (
                    f"Readiness {record.score}% - recovery recharge granted "
                    "(Recovery Pool can add more)."
                ),
                "amount": f"+{REST_DAY_ENERGY_BONUS}",
            }
        )

    return {
        "stat": "energy",
        "name": "Energy",
        "icon": "fa-bolt",
        "value": resources.energy,
        "value_note": f"of {ENERGY_CAP} cap",
        "description": (
            "Construction fuel for your Flamingo Club. It refills itself "
            "over time - spend it on buildings, don't let it sit capped."
        ),
        "facts": facts,
        "how_to_earn": how_to_earn,
        "history": history,
        "empty_hint": (
            "No rest-day bonuses recently - energy trickles in automatically "
            "every hour."
        ),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def explain_stat(user, resources, stat):
    """Build the explainer payload for one top-nav stat.

    ``resources`` must be the user's (already refreshed) ``BaseResource``.
    Raises ``ValueError`` for unknown stat keys (views map that to a 404).
    """
    if stat == "streak":
        return _streak_info(user, resources)
    if stat == "materials":
        return _materials_info(user, resources)
    if stat == "energy":
        return _energy_info(user, resources)
    raise ValueError(f"Unknown stat: {stat}")
