"""Intelligent Habit Reminders and Mobile Push Notification Service.

Learns from user historical activity log timing to provide context-aware,
timely habit prompts (food, water, workouts, sleep, streak preservation)
with granular user on/off preference controls.
"""

from collections import defaultdict
from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from ..models import (
    DailyReadiness,
    PlayerProfile,
    PushDevice,
    PushNotificationLog,
    RawActivityLog,
    User,
)
from .combat import profile as combat_profile

DEFAULT_NOTIFICATION_PREFERENCES = {
    "enabled": True,
    "food_reminders": True,
    "hydration_reminders": True,
    "workout_reminders": True,
    "sleep_reminders": True,
    "streak_reminders": True,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00",
}


def get_user_notification_preferences(user):
    """Return user's notification preferences merged with default settings."""
    profile_obj = combat_profile(user)
    saved = profile_obj.notification_preferences or {}
    merged = dict(DEFAULT_NOTIFICATION_PREFERENCES)
    merged.update(saved)
    return merged


def update_user_notification_preferences(user, new_prefs):
    """Validate and persist updated notification preferences."""
    profile_obj = combat_profile(user)
    current = get_user_notification_preferences(user)

    for key, val in (new_prefs or {}).items():
        if key in DEFAULT_NOTIFICATION_PREFERENCES:
            if key in ("quiet_hours_start", "quiet_hours_end"):
                # Validate HH:MM format
                try:
                    datetime.strptime(str(val), "%H:%M")
                    current[key] = str(val)
                except ValueError:
                    pass
            elif isinstance(DEFAULT_NOTIFICATION_PREFERENCES[key], bool):
                current[key] = bool(val)

    profile_obj.notification_preferences = current
    profile_obj.save(update_fields=["notification_preferences"])
    return current


def is_in_quiet_hours(now_time, start_str="22:00", end_str="07:00"):
    """Check if current time falls within user's configured quiet hours."""
    try:
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        start_t = time(sh, sm)
        end_t = time(eh, em)
    except (ValueError, TypeError):
        start_t = time(22, 0)
        end_t = time(7, 0)

    if start_t <= end_t:
        return start_t <= now_time < end_t
    else:  # Overnight range, e.g. 22:00 to 07:00
        return now_time >= start_t or now_time < end_t


def analyze_user_habit_windows(user, days=14):
    """Analyze historical activity logs to extract typical habit times of day."""
    cutoff = timezone.now() - timedelta(days=days)
    logs = (
        RawActivityLog.objects.filter(user=user, occurred_at__gte=cutoff)
        .order_by("occurred_at")
        .values("event_type", "occurred_at", "payload")
    )

    nutrition_hours = []
    hydration_hours = []
    workout_hours = []
    daily_water_totals = defaultdict(float)

    for log in logs:
        local_dt = timezone.localtime(log["occurred_at"])
        etype = log["event_type"]
        h = local_dt.hour
        d_str = local_dt.date().isoformat()

        if etype in ("nutrition", "food", "macro"):
            nutrition_hours.append(h)
        elif etype == "hydration":
            hydration_hours.append(h)
            payload = log.get("payload") or {}
            water_val = float(payload.get("water") or payload.get("water_ml") or payload.get("amount") or 0)
            daily_water_totals[d_str] += water_val
        elif etype in ("strength", "cardio", "endurance", "workout", "active_calories", "steps"):
            workout_hours.append(h)

    # Defaults if no history exists yet
    typical_nutrition = sorted(list(set(nutrition_hours))) if nutrition_hours else [8, 12, 18]
    typical_hydration = sorted(list(set(hydration_hours))) if hydration_hours else [9, 13, 17, 20]
    typical_workout = sorted(list(set(workout_hours))) if workout_hours else [17]
    avg_water = (sum(daily_water_totals.values()) / max(1, len(daily_water_totals))) if daily_water_totals else 64.0

    return {
        "nutrition_hours": typical_nutrition,
        "hydration_hours": typical_hydration,
        "workout_hours": typical_workout,
        "avg_water": round(avg_water, 1),
    }


def evaluate_smart_reminders(user, now=None):
    """Evaluate historical habit timings against today's logs to generate smart prompts."""
    now = now or timezone.now()
    local_now = timezone.localtime(now)
    current_time = local_now.time()
    current_hour = local_now.hour
    today = local_now.date()

    prefs = get_user_notification_preferences(user)
    if not prefs.get("enabled", True):
        return []

    if is_in_quiet_hours(
        current_time,
        prefs.get("quiet_hours_start", "22:00"),
        prefs.get("quiet_hours_end", "07:00"),
    ):
        return []

    # Get today's logs
    today_start = timezone.make_aware(datetime.combine(today, time.min))
    today_logs = list(
        RawActivityLog.objects.filter(user=user, occurred_at__gte=today_start).values(
            "event_type", "occurred_at", "payload"
        )
    )

    logged_events = set()
    total_water_today = 0.0
    for l in today_logs:
        etype = l["event_type"]
        logged_events.add(etype)
        if etype == "hydration":
            payload = l.get("payload") or {}
            total_water_today += float(
                payload.get("water") or payload.get("water_ml") or payload.get("amount") or 0
            )

    # Get recently sent notifications in last 4 hours to avoid spamming
    recent_cutoff = now - timedelta(hours=4)
    recent_sent_categories = set(
        PushNotificationLog.objects.filter(user=user, sent_at__gte=recent_cutoff).values_list(
            "category", flat=True
        )
    )

    habits = analyze_user_habit_windows(user)
    prompts = []

    # 1. Food / Nutrition Reminder
    if prefs.get("food_reminders", True) and "food" not in recent_sent_categories:
        has_food = bool(logged_events.intersection({"nutrition", "food", "macro"}))
        # Check if current time is past lunch (12pm) or dinner (6pm) without meal logs
        if not has_food and current_hour >= 12:
            meal_name = "dinner" if current_hour >= 17 else "lunch"
            prompts.append({
                "category": "food",
                "title": f"🍽️ Time for {meal_name}?",
                "body": f"Keep your nutrition stats strong! Remember to log your {meal_name} to fuel your avatar and earn XP.",
                "data": {"action": "log_meal", "suggested_time": meal_name},
            })

    # 2. Hydration Reminder
    if prefs.get("hydration_reminders", True) and "hydration" not in recent_sent_categories:
        # If past midday and water is under 50% of expected/target
        if total_water_today < 32 and current_hour >= 13:
            prompts.append({
                "category": "hydration",
                "title": "💧 Hydration Check-in",
                "body": f"You've logged {int(total_water_today)} oz so far today. Grab a glass of water to keep your hydration streak alive!",
                "data": {"action": "log_hydration", "current_oz": total_water_today},
            })

    # 3. Workout / Activity Reminder
    if prefs.get("workout_reminders", True) and "workout" not in recent_sent_categories:
        has_workout = bool(logged_events.intersection({"strength", "cardio", "endurance", "workout"}))
        # If user typically works out around this hour and hasn't logged one
        if not has_workout and current_hour in habits["workout_hours"] or (not has_workout and current_hour >= 16):
            prompts.append({
                "category": "workout",
                "title": "⚡ Ready for Today's Workout?",
                "body": "Your training window is open. Crush your cardio or strength session to deal massive damage in PvE sieges!",
                "data": {"action": "log_workout"},
            })

    # 4. Streak Alert
    if prefs.get("streak_reminders", True) and "streak" not in recent_sent_categories:
        has_any_activity = len(logged_events) > 0
        if not has_any_activity and current_hour >= 19 and user.streak > 0:
            prompts.append({
                "category": "streak",
                "title": f"🔥 Protect Your {user.streak}-Day Streak!",
                "body": f"Only a few hours left today! Log your water, meal, or workout to keep your streak multiplier going.",
                "data": {"action": "protect_streak", "streak": user.streak},
            })

    # 5. Sleep & Wind-down Reminder
    if prefs.get("sleep_reminders", True) and "sleep" not in recent_sent_categories:
        if current_hour >= 21:
            prompts.append({
                "category": "sleep",
                "title": "🌙 Evening Wind-down",
                "body": "Prepare for a restorative night of sleep to recharge your Stamina and max out tomorrow's Body Battery readiness.",
                "data": {"action": "log_sleep"},
            })

    return prompts


@transaction.atomic
def dispatch_push_notification(user, category, title, body, data=None, now=None, force=False):
    """Dispatch a push notification to user's registered devices and record log."""
    now = now or timezone.now()
    prefs = get_user_notification_preferences(user)

    if not force:
        if not prefs.get("enabled", True):
            return None, "Push notifications are globally disabled by user."

        category_key = f"{category}_reminders"
        if category_key in prefs and not prefs[category_key]:
            return None, f"Notifications for category '{category}' are disabled in user preferences."

    log_entry = PushNotificationLog.objects.create(
        user=user,
        category=category,
        title=title,
        body=body,
        data=data or {},
    )

    # Deliver to active PushDevice records
    devices = list(PushDevice.objects.filter(user=user, is_active=True))
    # Simulated mobile gateway dispatch / WebPush payload
    for dev in devices:
        dev.last_seen_at = now
        dev.save(update_fields=["last_seen_at"])

    return log_entry, None


def register_push_device(user, token, platform="android", device_name=""):
    """Register or refresh a mobile/web push token for a user."""
    platform = platform.lower()
    if platform not in (PushDevice.Platform.ANDROID, PushDevice.Platform.IOS, PushDevice.Platform.WEB):
        platform = PushDevice.Platform.ANDROID

    device, created = PushDevice.objects.update_or_create(
        token=token,
        defaults={
            "user": user,
            "platform": platform,
            "device_name": device_name,
            "is_active": True,
            "last_seen_at": timezone.now(),
        },
    )
    return device
