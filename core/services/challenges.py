"""Challenge service (Phase 8, docs/13 §5.2).

Rolling community challenges derived live from data we already store - no new
ingestion. The default (and, by rule, only ever ONE active) challenge is
"Calorie Torch": most calories burned in the last 30 days.

Calorie sources (same payloads badges.py reads):

  * ``event_type="endurance"`` -> ``payload.total_calories_burned``
  * ``event_type="cardio"``    -> ``payload.calories``

Entry points:

  * ``calories_burned_in_window(user, days, now=None)`` - the metric itself.
  * ``active_challenge()`` - the single active Challenge row (or None).
  * ``challenge_state(user, now=None)`` - payload for GET /api/v1/challenges/.
"""

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from ..models import Challenge, RawActivityLog

logger = logging.getLogger(__name__)

# Display unit per metric (docs/13 §6.2).
METRIC_UNITS = {Challenge.Metric.CALORIES_BURNED: "kcal"}

# Payload field read per event_type for the calories_burned metric.
_CALORIE_FIELDS = {
    "endurance": "total_calories_burned",
    "cardio": "calories",
}


def calories_burned_in_window(user, days, now=None):
    """Total calories burned over the last ``days`` calendar days (incl. today)."""
    now = now or timezone.now()
    start_date = timezone.localdate(now) - timedelta(days=days - 1)
    logs = RawActivityLog.objects.filter(
        user=user,
        event_type__in=tuple(_CALORIE_FIELDS),
        occurred_at__date__gte=start_date,
    ).only("payload", "event_type")
    total = 0.0
    for log in logs:
        payload = log.payload or {}
        field = _CALORIE_FIELDS.get(log.event_type)
        try:
            total += float(payload.get(field, 0) or 0)
        except (TypeError, ValueError):
            continue
    return int(round(total))


def metric_progress(user, challenge, now=None):
    """Progress value for ``challenge.metric`` (extensible per metric)."""
    if challenge.metric == Challenge.Metric.CALORIES_BURNED:
        return calories_burned_in_window(user, challenge.window_days, now=now)
    return 0


def active_challenge():
    """The single active challenge (the model layer keeps it singular)."""
    return Challenge.objects.filter(is_active=True).order_by("sort_order", "id").first()


def challenge_state(user, now=None):
    """Payload for ``GET /api/v1/challenges/`` (docs/13 §6.2)."""
    challenge = active_challenge()
    if challenge is None:
        return {"challenge": None, "my_progress": 0, "leaderboard": []}

    rows = []
    for candidate in get_user_model().objects.filter(is_active=True):
        progress = metric_progress(candidate, challenge, now=now)
        if progress > 0 or candidate.pk == user.pk:
            rows.append(
                {
                    "username": candidate.username,
                    "avatar": candidate.avatar,
                    "progress": progress,
                    "is_you": candidate.pk == user.pk,
                }
            )
    rows.sort(key=lambda r: (-r["progress"], r["username"]))
    leaderboard = [dict(row, rank=index + 1) for index, row in enumerate(rows)]
    my_progress = next((r["progress"] for r in rows if r["is_you"]), 0)

    return {
        "challenge": {
            "slug": challenge.slug,
            "name": challenge.name,
            "description": challenge.description,
            "icon": challenge.icon,
            "metric": challenge.metric,
            "window_days": challenge.window_days,
            "unit": METRIC_UNITS.get(challenge.metric, ""),
        },
        "my_progress": my_progress,
        "leaderboard": leaderboard,
    }
