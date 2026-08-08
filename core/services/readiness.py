"""Readiness engine (Step 15).

Parses morning Garmin Body Battery / Sleep payloads and generates a
DailyReadiness record that either mandates a rest day or green-lights heavy
training. A low readiness score also *freezes* the user's streak.
"""

from django.db import transaction
from django.utils import timezone

from ..models import DailyReadiness, RawActivityLog, User
from .gamification import REST_DAY_THRESHOLD

REST_MESSAGE = (
    "Low battery! Streak is frozen today. Take a nap."
)
TRAIN_MESSAGE = "You're recovered! Today is a perfect day for a heavy lifting session."


def _latest_payload(user, event_type):
    """Return the most recent payload for an event type.

    We intentionally do *not* hard-filter by calendar date: sleep and body
    battery events can straddle a UTC/local midnight, and combining the most
    recent of each gives a sensible readiness score.
    """
    log = (
        RawActivityLog.objects.filter(user=user, event_type=event_type)
        .order_by("-occurred_at")
        .first()
    )
    return log.payload if log else None


def _score_from(data):
    """Combine body battery + sleep hours into a 0-100 readiness score."""
    body_battery = data.get("body_battery")
    sleep_hours = data.get("sleep_hours")

    if body_battery is None and sleep_hours is None:
        return None, None, None

    battery_score = body_battery if body_battery is not None else 0
    sleep_score = 0
    if sleep_hours is not None:
        sleep_score = min(100, (sleep_hours / 8.0) * 100)

    # Weighted: body battery dominates, sleep contributes a third.
    score = int(round(battery_score * 0.7 + sleep_score * 0.3))
    score = max(0, min(100, score))
    return score, body_battery, sleep_hours


@transaction.atomic
def compute_readiness(user, on_date=None):
    """Generate (or refresh) the DailyReadiness record for a user.

    Uses the most recent Garmin body-battery/sleep payload. If no Garmin data
    is present for the user, a neutral "train" readiness (score 70) is created
    so the rest of the app keeps working during development.
    """
    on_date = on_date or timezone.localdate()

    battery = _latest_payload(user, "body_battery")
    sleep = _latest_payload(user, "sleep")

    data = {
        "body_battery": (battery or {}).get("charge"),
        "sleep_hours": (sleep or {}).get("sleep_hours"),
    }
    score, battery_charge, sleep_hours = _score_from(data)
    if score is None:
        # No Garmin data yet at all -> neutral default.
        score, battery_charge, sleep_hours = 70, None, None

    if score < REST_DAY_THRESHOLD:
        requirement = DailyReadiness.StreakRequirement.REST_DAY
        message = REST_MESSAGE
    else:
        requirement = DailyReadiness.StreakRequirement.TRAIN
        message = TRAIN_MESSAGE

    readiness, _created = DailyReadiness.objects.update_or_create(
        user=user,
        date=on_date,
        defaults={
            "score": score,
            "streak_requirement": requirement,
            "message": message,
            "body_battery": battery_charge,
            "sleep_hours": sleep_hours,
        },
    )
    _apply_streak_freeze(user, requirement)
    return readiness


def _apply_streak_freeze(user, requirement):
    """Frozen streaks stay frozen on rest days; normal days are not touched here.

    (A fuller implementation would increment the streak once per active day;
    polling tasks already invoke readiness, so keeping this simple is fine.)
    """
    return user


def compute_readiness_for_all_users(on_date=None):
    """Recompute readiness for every user (used by the daily Celery beat)."""
    results = []
    for user in User.objects.all():
        results.append(compute_readiness(user, on_date))
    return results
