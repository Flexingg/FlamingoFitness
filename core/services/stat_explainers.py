"""Top-nav stat explainer service (Phase 9, docs/15).

Builds the "what is this stat + how did I earn it" payloads behind
``GET /api/v1/stats/<stat>/`` (clicking the streak / tokens / stamina badges in
the dashboard's top nav). Pure derivation over data we already store.
"""

from datetime import timedelta

from django.utils import timezone

from ..models import DailyReadiness
from .game_config import GAMEPLAY

# Valid stat keys accepted by GET /api/v1/stats/<stat>/.
STAT_KEYS = ("streak", "tokens", "stamina")

HISTORY_WINDOW_DAYS = int(GAMEPLAY["explainers"]["history_window_days"])
HISTORY_LIMIT = int(GAMEPLAY["explainers"]["history_limit"])
STREAK_HISTORY_DAYS = int(GAMEPLAY["explainers"]["streak_history_days"])


def _today():
    return timezone.localdate()


# ---------------------------------------------------------------------------
# Streak
# ---------------------------------------------------------------------------
def _streak_info(user, profile_obj):
    """Streak = consecutive active days, protected by readiness rest days."""
    from .combat import streak_multiplier

    multiplier = streak_multiplier(user.streak)
    facts = [
        {"label": "Token dividend multiplier", "value": f"{multiplier:.2f}x"},
        {"label": "Max bonus", "value": "1.50x at a 10-day streak"},
        {"label": "Gacha odds", "value": "Longer streaks boost Epic/Legendary odds"},
    ]
    how_to_earn = [
        "Show up on training days - your readiness card green-lights them.",
        "Low readiness mandates a rest day: your streak is frozen, never broken.",
        "A longer streak multiplies your daily Token dividend and improves Gacha odds.",
    ]
    history = []
    since = _today() - timedelta(days=STREAK_HISTORY_DAYS)
    records = DailyReadiness.objects.filter(user=user, date__gte=since).order_by(
        "-date"
    )[:STREAK_HISTORY_DAYS]
    for record in records:
        rest = record.streak_requirement == DailyReadiness.StreakRequirement.REST_DAY
        history.append({
            "date": record.date.isoformat(),
            "label": "Rest day" if rest else "Training day",
            "detail": (
                f"Readiness {record.score}% - streak protected (+2 stamina!)"
                if rest
                else f"Readiness {record.score}% - counts toward your streak."
            ),
        })
    return {
        "stat": "streak",
        "name": "Streak",
        "icon": "fa-fire",
        "value": user.streak,
        "value_note": "day streak",
        "description": "Your consecutive-day streak. Never broken by readiness rest days.",
        "facts": facts,
        "how_to_earn": how_to_earn,
        "history": history,
        "empty_hint": "No readiness records yet - your streak grows as you train.",
    }
# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
def _tokens_info(user, profile_obj):
    """Tokens = premium currency earned daily, spent on Gacha packs."""
    from .combat import XP_TO_TOKENS

    facts = [
        {"label": "Daily dividend", "value": f"1 Token per {XP_TO_TOKENS} XP"},
        {"label": "Perfect macros", "value": "+25 Tokens"},
        {"label": "Perfect hydration", "value": "+10 Tokens"},
        {"label": "Boss conquered", "value": "+150 Tokens"},
        {"label": "Hold a Gym", "value": "+20 Tokens/day"},
    ]
    how_to_earn = [
        f"Earn XP; each morning {XP_TO_TOKENS} XP mints 1 Token (x streak).",
        "Hit perfect macros or perfect hydration for bonus Tokens.",
        "Conquer PvE bosses and hold PvP Gyms for bigger payouts.",
    ]
    history = []
    since = _today() - timedelta(days=HISTORY_WINDOW_DAYS)
    rest = DailyReadiness.objects.filter(
        user=user, date__gte=since,
        streak_requirement=DailyReadiness.StreakRequirement.REST_DAY,
    ).order_by("-date")[:HISTORY_LIMIT]
    for record in rest:
        history.append({
            "date": record.date.isoformat(),
            "label": "Rest-day grant",
            "detail": f"Readiness {record.score}% - rest-day reward.",
            "amount": "+0",
        })
    return {
        "stat": "tokens",
        "name": "Tokens",
        "icon": "fa-coins",
        "value": profile_obj.tokens,
        "value_note": "Tokens",
        "description": "Premium currency for the Gacha Shop. Earned from consistent tracking, streak-fueled dividends, perfect lessons, boss conquests and Gym territory.",
        "facts": facts,
        "how_to_earn": how_to_earn,
        "history": history,
        "empty_hint": "No token history yet - keep tracking to earn your daily dividend.",
    }


# ---------------------------------------------------------------------------
# Stamina
# ---------------------------------------------------------------------------
def _stamina_info(user, profile_obj):
    """Stamina = daily siege-attack budget (refills each morning)."""
    from .combat import REST_DAY_STAMINA_BONUS, STAMINA_PER_DAY

    facts = [
        {"label": "Attacks per day", "value": f"{STAMINA_PER_DAY}"},
        {"label": "Rest-day bonus", "value": f"+{REST_DAY_STAMINA_BONUS}"},
    ]
    how_to_earn = [
        f"Stamina refills to {STAMINA_PER_DAY} every morning.",
        f"On a readiness rest day you get +{REST_DAY_STAMINA_BONUS} extra attacks.",
        "Spend stamina on PvE boss sieges - it never carries over to next day.",
    ]
    return {
        "stat": "stamina",
        "name": "Stamina",
        "icon": "fa-bolt",
        "value": profile_obj.stamina,
        "value_note": f"of {STAMINA_PER_DAY}",
        "description": "Your daily siege-attack budget.",
        "facts": facts,
        "how_to_earn": how_to_earn,
        "history": [],
        "empty_hint": "Nothing to show yet - stamina resets each morning.",
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def explain_stat(user, stat):
    """Build the explainer payload for one top-nav stat."""
    from .combat import profile as _profile

    profile_obj = _profile(user)
    if stat == "streak":
        return _streak_info(user, profile_obj)
    if stat == "tokens":
        return _tokens_info(user, profile_obj)
    if stat == "stamina":
        return _stamina_info(user, profile_obj)
    raise ValueError(f"Unknown stat: {stat}")

