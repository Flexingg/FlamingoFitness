"""Historical Queue service (docs/17 + Roadmap #2).

Scans recent trailing days to detect unlogged food/nutrition and hydration entries,
prompting the user to backfill missing logs and preserve their streaks.
"""

from datetime import timedelta
from django.utils import timezone

from ..models import RawActivityLog


def find_missing_habit_days(user, days=7):
    """Scan trailing ``days`` (excluding today/future) for missing food and hydration logs.

    Returns a list of dicts:
      [
        {
          "date": "2026-08-22",
          "label": "Yesterday",
          "missing": ["hydration", "nutrition"],
          "has_hydration": False,
          "has_nutrition": False,
          "days_ago": 1,
        }
      ]
    """
    today = timezone.localdate()
    start_date = today - timedelta(days=days)

    # Query all raw logs for this user in the window
    logs = RawActivityLog.objects.filter(
        user=user,
        occurred_at__date__gte=start_date,
        occurred_at__date__lte=today,
        event_type__in=["hydration", "macro", "nutrition"],
    ).values_list("occurred_at__date", "event_type")

    logged_by_date = {}
    for log_date, event_type in logs:
        if log_date not in logged_by_date:
            logged_by_date[log_date] = set()
        if event_type == "hydration":
            logged_by_date[log_date].add("hydration")
        elif event_type in ("macro", "nutrition"):
            logged_by_date[log_date].add("nutrition")

    missing_days = []
    for i in range(1, days + 1):
        target_date = today - timedelta(days=i)
        date_str = target_date.isoformat()
        logged_events = logged_by_date.get(target_date, set())

        has_hydration = "hydration" in logged_events
        has_nutrition = "nutrition" in logged_events

        missing = []
        if not has_hydration:
            missing.append("hydration")
        if not has_nutrition:
            missing.append("nutrition")

        if missing:
            if i == 1:
                label = "Yesterday"
            elif i == 2:
                label = "2 days ago"
            else:
                label = target_date.strftime("%A, %b %d")

            missing_days.append({
                "date": date_str,
                "label": label,
                "missing": missing,
                "has_hydration": has_hydration,
                "has_nutrition": has_nutrition,
                "days_ago": i,
            })

    return missing_days
