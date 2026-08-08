"""Views for Flamingo Fitness (Steps 16-19).

API endpoints (docs/02_api_contracts.md):
  * GET  /api/v1/dashboard/state       -> dashboard JSON state
  * GET  /api/v1/leaderboard/weekly    -> asymmetric XP leaderboard
  * POST /api/v1/webhooks/home-assistant -> inbound smart-home data

And the dashboard page view (Step 19) served at "/".
"""

import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .forms import SignupForm, SparkyLinkForm
from .models import (
    BaseResource,
    Modality,
    Provider,
    RawActivityLog,
    SkillTree,
    User,
    UserIntegration,
    XPLedger,
)
from .services import compute_readiness, process_log


def _json_error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def signup(request):
    """Account creation page (GET/POST)."""
    if request.user.is_authenticated:
        return redirect("profile")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            messages.success(request, "Welcome to Flamingo Fitness!")
            # Send new users to link their SparkyFitness account next.
            return redirect("profile")
    else:
        form = SignupForm()
    return render(request, "core/signup.html", {"form": form})


@login_required
def profile(request):
    """Account profile: shows linked providers + SparkyFitness linking."""
    integrations = UserIntegration.objects.filter(user=request.user)
    sparky = integrations.filter(provider=Provider.SPARKYFITNESS).first()

    if request.method == "POST":
        form = SparkyLinkForm(request.POST)
        if form.is_valid():
            integration = form.save(request.user)
            messages.success(request, "SparkyFitness linked successfully!")
            # Kick off an immediate sync so the user sees data right away.
            try:
                from .tasks import poll_sparkyfitness

                poll_sparkyfitness()
            except Exception:  # noqa: BLE001 - never fail the link over a poll
                messages.warning(
                    request,
                    "SparkyFitness linked, but the first sync failed. "
                    "The scheduled poller will retry.",
                )
            return redirect("profile")
    else:
        initial = {"api_key": (sparky.credentials or {}).get("api_key", "") if sparky else ""}
        form = SparkyLinkForm(initial=initial)

    return render(
        request,
        "core/link_sparky.html",
        {"form": form, "integrations": integrations, "sparky": sparky},
    )


@login_required
def dashboard_page(request):
    """Serve the vanilla JS dashboard template (Step 19)."""
    return render(request, "core/dashboard.html")


@login_required
def nutrition_state(request):
    """GET /api/v1/nutrition/

    Returns today's nutrition summary, the full nutrition history, the
    nutrition skill-tree state, and whether SparkyFitness is linked (so the
    frontend can show a "Link SparkyFitness" CTA when there's no data yet).
    """
    from .services import summarize_nutrition
    from .models import SkillTree

    logs = (
        RawActivityLog.objects.filter(user=request.user, event_type="nutrition")
        .order_by("-occurred_at")
    )
    history = [summarize_nutrition(log) for log in logs]

    today_str = timezone.localdate().isoformat()
    today = next((h for h in history if h["date"] == today_str), None)
    if today is None and history:
        # Fall back to the most recent entry if nothing logged for today yet.
        today = history[0]

    st, _ = SkillTree.objects.get_or_create(
        user=request.user,
        modality=Modality.NUTRITION,
        defaults={"level": 1, "xp": 0, "total_xp": 0},
    )

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    has_key = bool((sparky.credentials or {}).get("api_key")) if sparky else False

    return JsonResponse(
        {
            "linked": sparky is not None,
            "demo": sparky is not None and not has_key,
            "today": today,
            "history": history,
            "skill_tree": {
                "level": st.level,
                "xp": st.xp,
                "total_xp": st.total_xp,
                "progress_pct": st.progress_pct,
            },
        }
    )


@login_required
def hydration_state(request):
    """GET /api/v1/hydration/

    Returns today's hydration summary, the full hydration history, the
    hydration skill-tree state, and whether SparkyFitness is linked.
    """
    from .services import summarize_hydration
    from .models import SkillTree

    logs = (
        RawActivityLog.objects.filter(user=request.user, event_type="hydration")
        .order_by("-occurred_at")
    )
    history = [summarize_hydration(log) for log in logs]
    
    # Debug logging to help diagnose hydration data issues
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[hydration] User {request.user.username}: found {logs.count()} hydration logs, history length {len(history)}")

    today_str = timezone.localdate().isoformat()
    today = next((h for h in history if h["date"] == today_str), None)
    if today is None and history:
        today = history[0]

    st, _ = SkillTree.objects.get_or_create(
        user=request.user,
        modality=Modality.HYDRATION,
        defaults={"level": 1, "xp": 0, "total_xp": 0},
    )

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    has_key = bool((sparky.credentials or {}).get("api_key")) if sparky else False

    return JsonResponse(
        {
            "linked": sparky is not None,
            "demo": sparky is not None and not has_key,
            "today": today,
            "history": history,
            "skill_tree": {
                "level": st.level,
                "xp": st.xp,
                "total_xp": st.total_xp,
                "progress_pct": st.progress_pct,
            },
        }
    )


@login_required
def dashboard_state(request):
    """GET /api/v1/dashboard/state (Step 16)."""
    user = request.user

    resources, _ = BaseResource.objects.get_or_create(user=user)

    # Readiness for today. Always recompute so a fresh value is shown even if
    # the daily Celery beat hasn't run yet (compute is idempotent + cheap).
    today = timezone.localdate()
    readiness = compute_readiness(user, on_date=today)

    skill_trees = {}
    for tree in SkillTree.objects.filter(user=user):
        skill_trees[tree.modality] = {
            "level": tree.level,
            "progress_pct": tree.progress_pct,
            "xp": tree.xp,
            "total_xp": tree.total_xp,
        }

    return JsonResponse(
        {
            "user": {"username": user.username, "streak": user.streak},
            "resources": {
                "materials": resources.materials,
                "energy": resources.energy,
                "time_speedups": resources.time_speedups,
            },
            "readiness": {
                "score": readiness.score,
                "streak_requirement": readiness.streak_requirement,
                "message": readiness.message,
            },
            "skill_trees": skill_trees,
        }
    )


def leaderboard_weekly(request):
    """GET /api/v1/leaderboard/weekly (Step 17).

    Aggregates XPLedger over the rolling 7-day window per user.
    """
    since = timezone.now() - timedelta(days=7)
    rows = (
        XPLedger.objects.filter(created_at__gte=since)
        .values("user__username", "user__avatar")
        .annotate(total_xp=Sum("amount"))
        .order_by("-total_xp")
    )
    leaderboard = [
        {
            "username": row["user__username"],
            "avatar": row["user__avatar"],
            "total_xp": row["total_xp"],
        }
        for row in rows
    ]
    return JsonResponse({"leaderboard": leaderboard, "window_days": 7})


@csrf_exempt
def home_assistant_webhook(request):
    """POST /api/v1/webhooks/home-assistant (Step 18).

    Accepts inbound events from Home Assistant (docs/06_home_assistant_spec.md),
    e.g. smart scale readings, NFC workout-start taps, or sleep-pad events.
    """
    if request.method != "POST":
        return _json_error("Method not allowed", 405)

    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    entity_id = data.get("entity_id", "")
    state = str(data.get("state", ""))
    attributes = data.get("attributes") or {}

    # Map HA entities to our event types.
    entity_lower = entity_id.lower()
    if "scale" in entity_lower or "weight" in entity_lower:
        event_type = "scale"
        payload = {"weight": state, "unit": attributes.get("unit", "kg"), **data}
    elif "nfc" in entity_lower:
        event_type = "workout_started"
        payload = {"entity_id": entity_id, **data}
    elif "sleep" in entity_lower:
        event_type = "sleep"
        payload = {
            "sleep_hours": attributes.get("sleep_hours") or state,
            **data,
        }
    else:
        event_type = "home_assistant"
        payload = data

    # Determine the target user (default: the first active user).
    username = data.get("username")
    user = User.objects.filter(username=username).first() if username else None
    if user is None:
        user = User.objects.order_by("id").first()
    if user is None:
        return _json_error("No user available to attribute this event", 400)

    raw_log = RawActivityLog.objects.create(
        user=user,
        source=Provider.HOME_ASSISTANT,
        event_type=event_type,
        payload=payload,
    )

    # If the event maps to a gamified event type, award XP immediately.
    xp_created = process_log(raw_log)

    return JsonResponse(
        {
            "accepted": True,
            "raw_log_id": raw_log.pk,
            "event_type": event_type,
            "xp_entries": len(xp_created),
        },
        status=201,
    )
