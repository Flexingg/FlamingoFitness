"""Core HTTP Views & REST API Endpoints for Flamingo Fitness.

Architecture & Endpoint Taxonomy:
1. **Core SPA Shell & Lazy Partials**:
   - `GET /` -> Dashboard shell (`core/templates/core/dashboard.html`).
   - `GET /panel/<name>/` (`panel_view`) -> Lazy partial HTML loader for modals/panels.
2. **Player Gamification & Dashboard HUD**:
   - `GET /api/v1/dashboard/state` -> Top HUD stats, streaks, currency, skill tree nodes.
   - `GET /api/v1/badges/` -> Achievement badges catalog, live criteria progress, points.
   - `GET /api/v1/leagues/` -> Weekly tier divisions, promotion/demotion thresholds.
3. **Modality Detail Endpoints**:
   - `GET /api/v1/nutrition/` -> Macro targets, calories, history logs, meal breakdown.
   - `GET /api/v1/hydration/` -> Daily fluid intake, water goal progress.
   - `GET /api/v1/endurance/` -> Zone 2/3 and Zone 4/5 HIIT cardio minutes.
   - `GET /api/v1/strength/` -> Workout sets, reps, tonnage, and 1RM calculations.
   - `GET /api/v1/recovery/` -> Sleep duration, readiness score, and resting heart rate.
4. **Combat & Economy**:
   - `GET /api/v1/shop/state` & `POST /api/v1/shop/buy-pack` -> Gacha loot packs.
   - `GET /api/v1/loadout/state` & `POST /api/v1/loadout/equip` -> Player gear slots.
   - `GET /api/v1/boss/state` & `POST /api/v1/boss/attack` -> PvE Boss encounters.
   - `GET /api/v1/pvp/state` & `POST /api/v1/pvp/attack` -> PvP Gym territory battles.
   - `GET /bounties/state` & `POST /bounties/create` -> 1v1 Duels & Escrow Wagering.
5. **Mobile & Smart-Home Ingestion Webhooks**:
   - `POST /api/v1/health/sync` -> Inbound HealthKit & Health Connect biometric batches.
   - `POST /api/v1/webhooks/home-assistant` -> Smart-home IoT events (scales, water dispensers).
"""

import json
import datetime
import uuid
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponseNotFound, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import LiftosaurLinkForm, SignupForm, SparkyLinkForm, ThemeForm
from .models import (
    BossConfig,
    CampaignBoss,
    CampaignProgress,
    FoodSnapDraft,
    GearItemDef,
    GearPackDef,
    Gym,
    Modality,
    Provider,
    RawActivityLog,
    SkillTree,
    Theme,
    User,
    UserGear,
    UserIntegration,
    XPLedger,
)
from .services import (
    STAT_KEYS,
    attack_boss as combat_attack_boss,
    attack_gym as combat_attack_gym,
    avatar_url,
    battle_history as combat_battle_history,
    battle_leaderboard as combat_battle_leaderboard,
    battle_state as combat_battle_state,
    challenge_state,
    compute_readiness,
    consume_consumable,
    create_flock,
    daily_token_harvest,
    engage_boss as combat_engage_boss,
    explain_stat,
    friends_of,
    invite_to_flock,
    league_state,
    leave_flock,
    open_pack as combat_open_pack,
    open_pack_bulk as combat_open_pack_bulk,
    process_log,
    profile as combat_profile,
    pvp_state as combat_pvp_state,
    remove_friend,
    reset_avatar,
    respond_flock_invite,
    respond_friend_request,
    save_avatar,
    buy_scrap_item as combat_buy_scrap_item,
    recycle_gear as combat_recycle_gear,
    scrap_shop_state as combat_scrap_shop_state,
    scrap_value as combat_scrap_value,
    send_friend_request,
    set_defense as combat_set_defense,
    social_state,
    wallet_dump,
)


def _json_error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def _bounded_logs(request, queryset):
    """Optionally bound a RawActivityLog queryset to the newest N days via ?days=.

    Used by the skill-tree state views so interactive chart / raw-data ranges can
    be resolved server-side for large datasets. A missing / invalid / non-positive
    value leaves the queryset unchanged (existing behaviour: all history).
    """
    days = request.GET.get("days")
    try:
        days = int(days)
    except (TypeError, ValueError):
        return queryset
    if days <= 0:
        return queryset
    cutoff = timezone.now() - timedelta(days=days)
    return queryset.filter(occurred_at__gte=cutoff)


def _raw_requested(request):
    """True when ?raw=1 asks each history day to also carry its original payload."""
    return request.GET.get("raw") == "1"


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
    """Account profile: shows linked providers + SparkyFitness/Liftosaur linking."""
    integrations = UserIntegration.objects.filter(user=request.user)
    sparky = integrations.filter(provider=Provider.SPARKYFITNESS).first()
    liftosaur = integrations.filter(provider=Provider.LIFTOSAUR).first()

    if request.method == "POST":
        # Theme preference update (Appearance card on the profile page). Kept
        # separate from provider linking so the two POST flows stay independent.
        if request.POST.get("action") == "theme":
            theme_form = ThemeForm(request.POST)
            if theme_form.is_valid():
                request.user.theme = theme_form.cleaned_data["theme"]
                request.user.save(update_fields=["theme"])
                messages.success(request, "Appearance updated.")
            return redirect("profile")

        # Historical backfill from a linked provider (profile "Sync history").
        # Validates the provider + lookback window, then hands the actual fetch
        # to a background Celery task so we don't block a Gunicorn worker.
        if request.POST.get("action") == "sync_history":
            from .tasks import (
                HISTORICAL_LOOKBACK_CHOICES,
                backfill_in_progress,
                backfill_liftosaur_for_user,
                backfill_sparkyfitness_for_user,
            )

            provider_raw = request.POST.get("provider", "")
            try:
                days = int(request.POST.get("days") or 0)
            except (TypeError, ValueError):
                days = 0

            backfill_task = {
                "sparkyfitness": backfill_sparkyfitness_for_user,
                "liftosaur": backfill_liftosaur_for_user,
            }.get(provider_raw)
            integration = integrations.filter(
                provider=provider_raw, is_active=True
            ).first()

            if backfill_task is None:
                messages.error(request, "Unknown integration for history sync.")
            elif integration is None:
                messages.error(
                    request, "Link this integration first, then sync its history."
                )
            elif int(days) not in HISTORICAL_LOOKBACK_CHOICES:
                messages.error(request, "Choose a valid history range (30 or 365 days).")
            elif backfill_in_progress(request.user.id, provider_raw):
                messages.info(
                    request,
                    "A history sync for this integration is already running — "
                    "it'll finish in the background. Check back shortly.",
                )
            else:
                try:
                    backfill_task.delay(request.user.id, days)
                    messages.success(
                        request,
                        (
                            "Syncing up to %d days of %s history in the "
                            "background (no XP is awarded for imported data)."
                        )
                        % (days, integration.get_provider_display()),
                    )
                except Exception:  # noqa: BLE001 - task queue may be unavailable
                    import logging

                    logging.getLogger(__name__).exception(
                        "Could not queue %s history sync", provider_raw
                    )
                    messages.error(
                        request, "Could not start the history sync right now. Try again."
                    )
            return redirect("profile")

        provider_key = request.POST.get("provider", "sparkyfitness")
        if provider_key == "liftosaur":
            form = LiftosaurLinkForm(request.POST)
            display = "Liftosaur"
        else:
            form = SparkyLinkForm(request.POST)
            display = "SparkyFitness"

        if form.is_valid():
            form.save(request.user)

            if provider_key == "liftosaur":
                # Queue a background 30-day sync so we don't block a Gunicorn
                # worker on a slow external API call (which caused worker
                # timeouts / OOM). The Celery worker does the fetch + ingest.
                try:
                    from .tasks import sync_liftosaur_for_user

                    sync_liftosaur_for_user.delay(request.user.id)
                    messages.success(
                        request,
                        "Liftosaur linked! Syncing your last 30 days in the background \u2014 "
                        "your strength data will appear shortly.",
                    )
                except Exception:  # noqa: BLE001
                    import logging

                    logging.getLogger(__name__).exception("Could not queue Liftosaur sync")
                    messages.success(request, "Liftosaur linked! The scheduled sync will pick it up.")
            else:
                # SparkyFitness: queue the background sync too.
                try:
                    from .tasks import poll_sparkyfitness

                    poll_sparkyfitness.delay()
                    messages.success(
                        request,
                        "SparkyFitness linked! Syncing your data in the background \u2014 it will appear shortly.",
                    )
                except Exception:  # noqa: BLE001
                    import logging

                    logging.getLogger(__name__).exception("Could not queue SparkyFitness sync")
                    messages.success(request, "SparkyFitness linked! The scheduled sync will pick it up.")
            return redirect("profile")
    else:
        sparky_initial = {"api_key": (sparky.credentials or {}).get("api_key", "") if sparky else ""}
        lift_initial = {"api_key": (liftosaur.credentials or {}).get("api_key", "") if liftosaur else ""}
        form = SparkyLinkForm(initial=sparky_initial)
        lift_form = LiftosaurLinkForm(initial=lift_initial)

    from .models import RawActivityLog

    lift_log_count = (
        RawActivityLog.objects.filter(
            user=request.user, source=Provider.LIFTOSAUR, event_type="strength"
        ).count()
    )
    sparky_log_count = (
        RawActivityLog.objects.filter(
            user=request.user, source=Provider.SPARKYFITNESS
        ).count()
    )

    return render(
        request,
        "core/link_sparky.html",
        {
            "form": form,
            "lift_form": lift_form,
            "integrations": integrations,
            "sparky": sparky,
            "liftosaur": liftosaur,
            "lift_log_count": lift_log_count,
            "sparky_log_count": sparky_log_count,
            "theme_choices": Theme.choices,
        },
    )


@login_required
@require_POST
def avatar_upload(request):
    """POST /api/v1/profile/avatar — upload or reset a profile picture.

    The avatar is stored as a plain URL string (core/services/avatar.py), so
    no model schema change was needed. Multipart FormData with an ``avatar``
    file; or ``{action: "reset"}`` as a form field to revert to the DiceBear
    default. The CSRF token is sent as the ``X-CSRFToken`` header by the
    frontend (docs/08). Returns the fresh avatar URL for an optimistic update.
    """
    if request.POST.get("action") == "reset":
        ok, avatar = reset_avatar(request.user)
        return JsonResponse({"ok": ok, "avatar": avatar})

    upload = request.FILES.get("avatar")
    if not upload:
        return _json_error("No image uploaded.", 400)

    ok, result = save_avatar(request.user, upload)
    if not ok:
        return _json_error(result["message"], result.get("status", 400))
    return JsonResponse({"ok": True, "avatar": result})


@login_required
def dashboard_page(request):
    """Serve the vanilla JS dashboard template (Step 19)."""
    return render(request, "core/dashboard.html")


_VALID_PANELS = {
    "nutrition",
    "hydration",
    "endurance",
    "strength",
    "boss",
    "recovery",
    "shop",
    "loadout",
    "battle",
    "pvp",
    "leagues",
    "badges",
    "bounties",
    "timeline",
}


@login_required
def panel_view(request, name):
    """GET /panel/<name>/ (docs/19 #12)
    Serve a single lazy-loaded panel partial HTML for vanilla JS consumption.
    """
    clean_name = name.strip().lower().replace("-view", "").replace(".html", "")
    if clean_name not in _VALID_PANELS:
        return HttpResponseNotFound("Panel not found")
    return render(request, f"core/panels/{clean_name}.html")


@login_required
def nutrition_state(request):
    """GET /api/v1/nutrition/

    Returns today's nutrition summary, the full nutrition history, the
    nutrition skill-tree state, and whether SparkyFitness is linked (so the
    frontend can show a "Link SparkyFitness" CTA when there's no data yet).
    """
    from .services import summarize_nutrition
    from .models import SkillTree

    logs = _bounded_logs(
        request,
        RawActivityLog.objects.filter(
            user=request.user, event_type="nutrition"
        ).order_by("-occurred_at"),
    )
    _raw = _raw_requested(request)
    history = []
    for _log in logs:
        _item = summarize_nutrition(_log)
        if _raw:
            _item["raw_payload"] = _log.payload
        history.append(_item)

    req_date = request.GET.get("date", "").strip()
    try:
        selected_date = datetime.date.fromisoformat(req_date) if req_date else timezone.localdate()
    except Exception:
        selected_date = timezone.localdate()
    selected_date_str = selected_date.isoformat()
    today_str = timezone.localdate().isoformat()

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    has_key = bool((sparky.credentials or {}).get("api_key")) if sparky else False
    api_key = (sparky.credentials or {}).get("api_key") if has_key else ""

    sparky_cal_goal = None
    sparky_pro_goal = None
    if api_key:
        from .services.sparky_client import SparkyFitnessClient
        client = SparkyFitnessClient()
        s_goals = client.get_goals_by_date(api_key, selected_date_str)
        if s_goals:
            sparky_cal_goal = s_goals.get("calories")
            sparky_pro_goal = s_goals.get("protein")

    active_occurred_at = timezone.make_aware(
        timezone.datetime.combine(selected_date, timezone.datetime.min.time())
    )
    direct_log = RawActivityLog.objects.filter(
        user=request.user,
        event_type="nutrition",
        occurred_at=active_occurred_at,
    ).first()
    if direct_log:
        active_day = summarize_nutrition(direct_log)
        if _raw:
            active_day["raw_payload"] = direct_log.payload
    else:
        active_day = next((h for h in history if h["date"] == selected_date_str), None)

    if active_day:
        if sparky_cal_goal is not None:
            active_day["calorie_goal"] = float(sparky_cal_goal)
            active_day["calorie_pct"] = int(round((active_day["calories"] / float(sparky_cal_goal)) * 100)) if float(sparky_cal_goal) else 0
        if sparky_pro_goal is not None:
            active_day["protein_goal"] = float(sparky_pro_goal)
            active_day["protein_pct"] = int(round((active_day["protein"] / float(sparky_pro_goal)) * 100)) if float(sparky_pro_goal) else 0
    else:
        # Construct fresh day state with Sparky goals
        c_goal = float(sparky_cal_goal) if sparky_cal_goal is not None else 2000.0
        p_goal = float(sparky_pro_goal) if sparky_pro_goal is not None else 150.0
        active_day = {
            "date": selected_date_str,
            "calories": 0.0,
            "protein": 0.0,
            "carbs": 0.0,
            "fat": 0.0,
            "calorie_goal": c_goal,
            "protein_goal": p_goal,
            "calorie_pct": 0,
            "protein_pct": 0,
            "perfect": False,
            "status": "needs_work",
            "status_label": "Needs work",
            "xp": 0,
            "tokens": 0,
            "food_entries": [],
        }

    st, _ = SkillTree.objects.get_or_create(
        user=request.user,
        modality=Modality.NUTRITION,
        defaults={"level": 1, "xp": 0, "total_xp": 0},
    )

    pending_snaps_count = FoodSnapDraft.objects.filter(
        user=request.user,
        status__in=[FoodSnapDraft.Status.PENDING, FoodSnapDraft.Status.ANALYZED]
    ).count()

    return JsonResponse(
        {
            "linked": sparky is not None,
            "demo": sparky is not None and not has_key,
            "today": active_day,
            "active_day": active_day,
            "selected_date": selected_date_str,
            "today_date": today_str,
            "is_today": (selected_date_str == today_str),
            "history": history,
            "pending_snaps_count": pending_snaps_count,
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
    hydration skill-tree state, whether SparkyFitness is linked, the user's
    custom water bottles, and their primary hydration source.
    """
    from .services import (
        build_hydration_history,
        ensure_default_bottles,
        primary_hydration_source,
    )
    from .models import PlayerProfile, SkillTree

    logs = _bounded_logs(
        request,
        RawActivityLog.objects.filter(
            user=request.user, event_type="hydration"
        ).order_by("-occurred_at"),
    )

    history = build_hydration_history(logs, include_raw=_raw_requested(request))

    today_str = timezone.localdate().isoformat()
    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    has_key = bool((sparky.credentials or {}).get("api_key")) if sparky else False
    api_key = (sparky.credentials or {}).get("api_key") if has_key else ""

    sparky_water_goal_oz = None
    if api_key:
        from .services.sparky_client import SparkyFitnessClient
        client = SparkyFitnessClient()
        s_goals = client.get_goals_by_date(api_key, today_str)
        if s_goals and s_goals.get("water_goal_ml"):
            sparky_water_goal_oz = round(float(s_goals["water_goal_ml"]) / 29.5735, 1)

    today = next((h for h in history if h["date"] == today_str), None)
    if today:
        if sparky_water_goal_oz:
            today["water_goal"] = sparky_water_goal_oz
            today["water_pct"] = int(round((today["water"] / sparky_water_goal_oz) * 100)) if sparky_water_goal_oz else 0
    else:
        w_goal = sparky_water_goal_oz or 120.0
        today = {
            "date": today_str,
            "water": 0.0,
            "water_goal": w_goal,
            "water_pct": 0,
            "perfect": False,
            "status": "needs_work",
            "status_label": "Needs work",
            "entries": [],
        }

    st, _ = SkillTree.objects.get_or_create(
        user=request.user,
        modality=Modality.HYDRATION,
        defaults={"level": 1, "xp": 0, "total_xp": 0},
    )

    profile = PlayerProfile.objects.get_or_create(user=request.user)[0]
    bottles = ensure_default_bottles(request.user)
    primary = primary_hydration_source(
        profile, sparky_linked=(sparky is not None and has_key)
    )

    return JsonResponse(
        {
            "linked": sparky is not None,
            "demo": sparky is not None and not has_key,
            "today": today,
            "history": history,
            "bottles": [
                {"id": b.id, "name": b.name, "capacity_oz": b.capacity_oz}
                for b in bottles
            ],
            "primary_source": primary,
            "skill_tree": {
                "level": st.level,
                "xp": st.xp,
                "total_xp": st.total_xp,
                "progress_pct": st.progress_pct,
            },
        }
    )


@login_required
def timeline_state(request):
    """GET /api/v1/timeline/
    Returns chronological activity events grouped by date with daily rollups.
    Query params:
        days: int (default 14, max 90)
        category: 'all' | 'workout' | 'nutrition' | 'hydration' | 'sleep'
    """
    from .services import (
        summarize_endurance,
        summarize_hydration,
        summarize_nutrition,
        summarize_sleep,
        summarize_strength,
    )
    from .models import RawActivityLog, Provider

    try:
        days_param = int(request.GET.get("days", 14))
    except (ValueError, TypeError):
        days_param = 14
    days_param = max(1, min(90, days_param))

    category_filter = request.GET.get("category", "all").strip().lower()

    category_to_types = {
        "workout": ["strength", "cardio", "endurance"],
        "strength": ["strength"],
        "cardio": ["cardio", "endurance"],
        "nutrition": ["nutrition", "macro", "food"],
        "food": ["nutrition", "macro", "food"],
        "hydration": ["hydration", "water"],
        "water": ["hydration", "water"],
        "sleep": ["sleep", "body_battery", "recovery"],
    }

    start_date = timezone.now() - timedelta(days=days_param)
    qs = (
        RawActivityLog.objects.filter(
            user=request.user,
            occurred_at__gte=start_date,
        )
        .prefetch_related("xp_entries")
        .order_by("-occurred_at")
    )

    if category_filter in category_to_types:
        qs = qs.filter(event_type__in=category_to_types[category_filter])

    grouped_days = {}

    for log in qs:
        local_dt = timezone.localtime(log.occurred_at)
        date_str = local_dt.date().isoformat()
        time_min = local_dt.hour * 60 + local_dt.minute

        if date_str not in grouped_days:
            grouped_days[date_str] = {
                "date": date_str,
                "local_date": local_dt.date(),
                "events": [],
                "totals": {
                    "workout_count": 0,
                    "workout_volume_lbs": 0.0,
                    "workout_minutes": 0.0,
                    "calories": 0.0,
                    "protein": 0.0,
                    "carbs": 0.0,
                    "fat": 0.0,
                    "water_oz": 0.0,
                    "sleep_hours": 0.0,
                    "sleep_score": None,
                    "total_xp": 0,
                },
            }

        day_dict = grouped_days[date_str]

        log_xp = sum(xp.amount for xp in log.xp_entries.all())
        day_dict["totals"]["total_xp"] += log_xp

        time_formatted = local_dt.strftime("%I:%M %p").lstrip("0")
        payload = log.payload or {}
        event_type = log.event_type.lower()
        source = log.source
        source_label = dict(Provider.choices).get(source, source.title())

        event_item = {
            "id": log.id,
            "occurred_at": local_dt.isoformat(),
            "time_str": time_formatted,
            "time_min": time_min,
            "value": 60,
            "event_type": event_type,
            "category": "other",
            "source": source,
            "source_label": source_label,
            "title": "",
            "subtitle": "",
            "xp": log_xp,
            "chips": [],
            "metrics": {},
            "details": {},
        }

        if event_type in ("strength", "workout"):
            summary = summarize_strength(log)
            event_item["category"] = "strength"
            event_item["title"] = summary.get("program") or "Strength Workout"
            if summary.get("day_name"):
                event_item["subtitle"] = summary["day_name"]
            vol = float(summary.get("total_volume_lbs", 0) or 0)
            dur = float(summary.get("duration_minutes", 0) or 0)
            ex_count = int(summary.get("exercise_count", 0) or 0)

            day_dict["totals"]["workout_count"] += 1
            day_dict["totals"]["workout_volume_lbs"] += vol
            day_dict["totals"]["workout_minutes"] += dur

            val = min(100, max(60, int(75 + min(25, vol / 600.0))))
            event_item["value"] = val

            chips = []
            if vol > 0:
                chips.append({"label": f"{int(vol):,} lbs", "icon": "fa-dumbbell", "color": "pink"})
            if dur > 0:
                chips.append({"label": f"{int(dur)} min", "icon": "fa-clock", "color": "slate"})
            if ex_count > 0:
                chips.append({"label": f"{ex_count} exercises", "icon": "fa-list-check", "color": "slate"})
            if summary.get("pr"):
                chips.append({"label": "PR Set!", "icon": "fa-trophy", "color": "amber"})

            event_item["chips"] = chips
            event_item["metrics"] = {
                "volume_lbs": round(vol, 1),
                "duration_minutes": round(dur, 1),
                "total_sets": summary.get("total_sets", 0),
            }
            event_item["details"] = {
                "exercises": summary.get("exercises", []),
                "completed": summary.get("completed", True),
                "notes": payload.get("notes", ""),
            }

        elif event_type in ("cardio", "endurance"):
            summary = summarize_endurance(log)
            event_item["category"] = "cardio"
            event_item["title"] = payload.get("workout_title") or payload.get("title") or "Cardio Session"
            dur = float(summary.get("total_duration_minutes", 0) or 0)
            cals = float(summary.get("total_calories_burned", 0) or 0)
            day_dict["totals"]["workout_count"] += 1
            day_dict["totals"]["workout_minutes"] += dur

            val = min(100, max(50, int(65 + min(25, cals / 25.0))))
            event_item["value"] = val

            chips = []
            if dur > 0:
                chips.append({"label": f"{int(dur)} min", "icon": "fa-clock", "color": "blue"})
            if cals > 0:
                chips.append({"label": f"{int(cals)} cal", "icon": "fa-fire", "color": "orange"})

            event_item["chips"] = chips
            event_item["metrics"] = {"duration_minutes": round(dur, 1), "calories_burned": round(cals, 1)}
            event_item["details"] = {"exercises": summary.get("exercise_entries", [])}

        elif event_type in ("nutrition", "macro", "food"):
            summary = summarize_nutrition(log)
            event_item["category"] = "food"
            cals = float(summary.get("calories", 0) or payload.get("calories", 0) or 0)
            pro = float(summary.get("protein", 0) or payload.get("protein", 0) or 0)
            carbs = float(summary.get("carbs", 0) or payload.get("carbs", 0) or 0)
            fat = float(summary.get("fat", 0) or payload.get("fat", 0) or 0)

            day_dict["totals"]["calories"] = max(day_dict["totals"]["calories"], cals)
            day_dict["totals"]["protein"] = max(day_dict["totals"]["protein"], pro)
            day_dict["totals"]["carbs"] = max(day_dict["totals"]["carbs"], carbs)
            day_dict["totals"]["fat"] = max(day_dict["totals"]["fat"], fat)

            val = min(100, max(50, int(65 + min(25, pro / 3.0))))
            event_item["value"] = val

            event_item["title"] = payload.get("meal_name") or payload.get("title") or "Nutrition Log"
            chips = [
                {"label": f"{int(cals)} kcal", "icon": "fa-fire", "color": "emerald"},
                {"label": f"{int(pro)}g P", "color": "emerald"},
                {"label": f"{int(carbs)}g C", "color": "cyan"},
                {"label": f"{int(fat)}g F", "color": "amber"},
            ]
            if summary.get("perfect"):
                chips.append({"label": "Goals Met!", "icon": "fa-check", "color": "emerald"})

            event_item["chips"] = chips
            event_item["metrics"] = {
                "calories": round(cals, 1),
                "protein": round(pro, 1),
                "carbs": round(carbs, 1),
                "fat": round(fat, 1),
                "calorie_goal": summary.get("calorie_goal"),
                "protein_goal": summary.get("protein_goal"),
            }
            event_item["details"] = {
                "food_entries": summary.get("food_entries", []),
                "status_label": summary.get("status_label", ""),
            }

        elif event_type in ("hydration", "water"):
            summary = summarize_hydration(log)
            event_item["category"] = "water"
            water_oz = float(summary.get("water", 0) or payload.get("amount_oz", 0) or 0)
            day_dict["totals"]["water_oz"] = max(day_dict["totals"]["water_oz"], water_oz)

            val = min(100, max(45, int(50 + min(35, water_oz * 1.5))))
            event_item["value"] = val

            event_item["title"] = "Hydration Intake"
            chips = [
                {"label": f"{water_oz:.1f} oz", "icon": "fa-glass-water", "color": "cyan"},
            ]
            if summary.get("water_goal"):
                chips.append({"label": f"Goal: {int(summary['water_goal'])} oz ({summary.get('water_pct', 0)}%)", "color": "slate"})
            if summary.get("perfect"):
                chips.append({"label": "Hydrated!", "icon": "fa-check", "color": "cyan"})

            event_item["chips"] = chips
            event_item["metrics"] = {
                "water_oz": round(water_oz, 1),
                "water_goal": summary.get("water_goal"),
                "water_pct": summary.get("water_pct"),
            }
            event_item["details"] = {
                "water_entries": summary.get("water_intake_entries", []),
            }

        elif event_type in ("sleep", "recovery", "body_battery"):
            summary = summarize_sleep(log)
            event_item["category"] = "sleep"
            hours = float(summary.get("sleep_hours", 0) or 0)
            score = payload.get("sleep_score") or payload.get("score")

            day_dict["totals"]["sleep_hours"] = max(day_dict["totals"]["sleep_hours"], hours)
            if score:
                day_dict["totals"]["sleep_score"] = score

            val = min(100, max(50, int(60 + min(30, hours * 4.0))))
            event_item["value"] = val

            event_item["title"] = "Sleep & Recovery"
            chips = []
            if hours > 0:
                chips.append({"label": f"{hours} hrs", "icon": "fa-moon", "color": "purple"})
            if score:
                chips.append({"label": f"Score: {score}", "icon": "fa-star", "color": "purple"})

            charge = payload.get("charge") or payload.get("body_battery")
            if charge:
                chips.append({"label": f"+{charge} Battery", "icon": "fa-bolt", "color": "emerald"})

            event_item["chips"] = chips
            event_item["metrics"] = {
                "sleep_hours": round(hours, 1),
                "sleep_score": score,
                "charge": charge,
            }
            event_item["details"] = {
                "deep_pct": summary.get("deep_pct") or payload.get("deep_pct"),
                "rem_pct": summary.get("rem_pct") or payload.get("rem_pct"),
                "status_label": summary.get("status_label", ""),
            }

        day_dict["events"].append(event_item)

    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    now_dt = timezone.localtime(timezone.now())
    current_now_min = now_dt.hour * 60 + now_dt.minute

    result_days = []
    for date_str, data in sorted(grouped_days.items(), reverse=True):
        d_obj = data["local_date"]
        if d_obj == today:
            display_title = "Today"
        elif d_obj == yesterday:
            display_title = "Yesterday"
        else:
            display_title = d_obj.strftime("%A, %b %d")

        data["totals"]["workout_volume_lbs"] = round(data["totals"]["workout_volume_lbs"], 1)
        data["totals"]["calories"] = round(data["totals"]["calories"], 1)
        data["totals"]["protein"] = round(data["totals"]["protein"], 1)
        data["totals"]["carbs"] = round(data["totals"]["carbs"], 1)
        data["totals"]["fat"] = round(data["totals"]["fat"], 1)
        data["totals"]["water_oz"] = round(data["totals"]["water_oz"], 1)
        data["totals"]["sleep_hours"] = round(data["totals"]["sleep_hours"], 1)

        result_days.append({
            "date": date_str,
            "display_title": display_title,
            "formatted_date": d_obj.strftime("%B %d, %Y"),
            "totals": data["totals"],
            "events": data["events"],
        })

    return JsonResponse({
        "ok": True,
        "days": result_days,
        "active_filter": category_filter,
        "days_count": days_param,
        "current_now_min": current_now_min,
        "current_now_label": now_dt.strftime("%I:%M %p").lstrip("0"),
    })


@login_required
def water_add(request):
    """POST /api/v1/hydration/water/add  body: {amount_oz, bottle_id?, source?}

    Logs water against the user's primary hydration source. If the primary
    source is SparkyFitness (linked), it pushes to Sparky AND records locally;
    otherwise it records a local log tagged with the primary source.
    """
    import json
    from .services import create_water_log, primary_hydration_source
    from .models import PlayerProfile, UserIntegration, Provider, WaterBottle
    from .services.sparky_client import SparkyFitnessClient

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    try:
        amount_oz = float(body.get("amount_oz") or body.get("amount") or 0)
    except (TypeError, ValueError):
        amount_oz = 0
    if amount_oz <= 0:
        return JsonResponse({"success": False, "error": "amount_oz must be > 0"}, status=400)

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    has_key = bool((sparky.credentials or {}).get("api_key")) if sparky else False
    profile = PlayerProfile.objects.get_or_create(user=request.user)[0]
    source = body.get("source") or primary_hydration_source(
        profile, sparky_linked=(sparky is not None and has_key)
    )

    pushed_to_sparky = False
    if source == "sparkyfitness" and sparky and has_key:
        try:
            SparkyFitnessClient().post_water_intake(
                sparky.credentials["api_key"],
                water_ml=round(amount_oz * 29.5735, 1),
            )
            pushed_to_sparky = True
        except Exception as exc:  # best-effort push; still record locally
            import logging
            logging.getLogger(__name__).warning(
                "water_add: Sparky push failed: %s", exc
            )

    create_water_log(
        request.user,
        amount_oz,
        source=source,
        pushed_to_sparky=pushed_to_sparky,
    )
    return JsonResponse(
        {"success": True, "amount_oz": amount_oz, "source": source,
         "pushed_to_sparky": pushed_to_sparky}
    )


@login_required
def water_remove(request):
    """POST /api/v1/hydration/water/remove  body: {amount_oz, source?}

    Subtracts water from today's total (a negative hydration log). Removals are
    local adjustments (the upstream provider APIs don't support deletions).
    """
    import json
    from .services import create_water_log, primary_hydration_source
    from .models import PlayerProfile, UserIntegration, Provider

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    try:
        amount_oz = float(body.get("amount_oz") or body.get("amount") or 0)
    except (TypeError, ValueError):
        amount_oz = 0
    if amount_oz <= 0:
        return JsonResponse({"success": False, "error": "amount_oz must be > 0"}, status=400)

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    has_key = bool((sparky.credentials or {}).get("api_key")) if sparky else False
    profile = PlayerProfile.objects.get_or_create(user=request.user)[0]
    source = body.get("source") or primary_hydration_source(
        profile, sparky_linked=(sparky is not None and has_key)
    )

    create_water_log(request.user, -amount_oz, source=source, pushed_to_sparky=False)
    return JsonResponse({"success": True, "amount_oz": -amount_oz, "source": source})


@login_required
def water_bottles(request):
    """GET/POST/DELETE /api/v1/hydration/bottles/

    GET returns the user's custom bottle sizes. POST upserts the whole list
    (bottles not present are deleted). Each item: {id?, name, capacity_oz}.
    """
    import json
    from .models import WaterBottle

    if request.method == "GET":
        bottles = request.user.water_bottles.all()
        return JsonResponse(
            {
                "bottles": [
                    {"id": b.id, "name": b.name, "capacity_oz": b.capacity_oz}
                    for b in bottles
                ]
            }
        )

    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

        items = body.get("bottles")
        if not isinstance(items, list):
            return JsonResponse({"success": False, "error": "bottles list required"}, status=400)

        kept_ids = []
        for idx, item in enumerate(items):
            try:
                cap = float(item.get("capacity_oz") or 0)
            except (TypeError, ValueError):
                cap = 0
            if cap <= 0:
                continue
            name = (item.get("name") or "Bottle")[:50]
            if item.get("id"):
                bottle = WaterBottle.objects.filter(
                    id=item["id"], user=request.user
                ).first()
                if bottle:
                    bottle.capacity_oz = cap
                    bottle.name = name
                    bottle.sort_order = idx
                    bottle.save()
                    kept_ids.append(bottle.id)
                    continue
            new = WaterBottle.objects.create(
                user=request.user, name=name, capacity_oz=cap, sort_order=idx
            )
            kept_ids.append(new.id)

        # Remove any bottles the user dropped from the list.
        request.user.water_bottles.exclude(id__in=kept_ids).delete()

        bottles = request.user.water_bottles.all()
        return JsonResponse(
            {
                "success": True,
                "bottles": [
                    {"id": b.id, "name": b.name, "capacity_oz": b.capacity_oz}
                    for b in bottles
                ],
            }
        )

    return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)


@login_required
def water_bottle_delete(request, bottle_id):
    """DELETE /api/v1/hydration/bottles/{id}"""
    from .models import WaterBottle

    if request.method == "DELETE":
        WaterBottle.objects.filter(id=bottle_id, user=request.user).delete()
        return JsonResponse({"success": True})
    return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)



@login_required
def endurance_state(request):
    """GET /api/v1/endurance/

    Returns today's endurance summary, the full exercise history, the
    endurance skill-tree state, and whether SparkyFitness is linked.
    """
    from .services import summarize_endurance
    from .models import SkillTree

    logs = _bounded_logs(
        request,
        RawActivityLog.objects.filter(
            user=request.user, event_type="endurance"
        ).order_by("-occurred_at"),
    )
    _raw = _raw_requested(request)
    history = []
    for _log in logs:
        _item = summarize_endurance(_log)
        if _raw:
            _item["raw_payload"] = _log.payload
        history.append(_item)

    today_str = timezone.localdate().isoformat()
    today = next((h for h in history if h["date"] == today_str), None)
    if today is None and history:
        today = history[0]

    st, _ = SkillTree.objects.get_or_create(
        user=request.user,
        modality=Modality.ENDURANCE,
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
def _best_lifts_from_history(history):
    """Derive the user's all-time best lifts (heaviest set weight + Epley est.
    1RM) per exercise, across a list of summarize_strength() day summaries.

    These personal records are surfaced by the PR Boss panel (GET /api/v1/boss/),
    not the Strength panel.
    """
    best = {}
    for h in history:
        for ex in h["exercises"]:
            key = ex["name"].lower()
            prev = best.get(key)
            if prev is None or (ex["est_1rm"] or 0) > (prev["est_1rm"] or 0):
                best[key] = {
                    "name": ex["name"],
                    "weight": ex["weight"],
                    "reps": ex["reps"],
                    "unit": ex["unit"],
                    "est_1rm": ex["est_1rm"],
                    "date": h["date"],
                }
    return [best[k] for k in sorted(best)]


@login_required
def strength_state(request):
    """GET /api/v1/strength/

    Returns Liftosaur strength summaries (volume / duration), the full strength
    history, the strength skill-tree state, and whether Liftosaur is linked.
    Personal records (best lifts) moved to GET /api/v1/boss/ with the PR Boss.
    """
    from .services import summarize_strength

    logs = _bounded_logs(
        request,
        RawActivityLog.objects.filter(
            user=request.user, event_type="strength"
        ).order_by("-occurred_at"),
    )
    _raw = _raw_requested(request)
    history = []
    for _log in logs:
        _item = summarize_strength(_log)
        if _raw:
            _item["raw_payload"] = _log.payload
        history.append(_item)

    today_str = timezone.localdate().isoformat()
    today = next((h for h in history if h["date"] == today_str), None)
    if today is None and history:
        today = history[0]

    st, _ = SkillTree.objects.get_or_create(
        user=request.user,
        modality=Modality.STRENGTH,
        defaults={"level": 1, "xp": 0, "total_xp": 0},
    )

    liftosaur = UserIntegration.objects.filter(
        user=request.user, provider=Provider.LIFTOSAUR, is_active=True
    ).first()
    has_key = bool((liftosaur.credentials or {}).get("api_key")) if liftosaur else False

    return JsonResponse(
        {
            "linked": liftosaur is not None,
            "demo": liftosaur is not None and not has_key,
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


def _latest_bodyweight(user):
    """Latest SparkyFitness bodyweight reading (from raw check-in/scale logs)."""
    logs = RawActivityLog.objects.filter(
        user=user, source=Provider.SPARKYFITNESS
    ).order_by("-occurred_at")
    seen = set()
    for log in logs:
        weight = (log.payload or {}).get("weight")
        if not weight or str(log.payload.get("_id")) in seen:
            continue
        seen.add(str(log.payload.get("_id")))
        try:
            return float(weight)
        except (TypeError, ValueError):
            continue
    return None


@login_required
def boss_state(request):
    """GET /api/v1/boss/

    Compares the user's best lifts against the admin-configurable PR Boss
    thresholds (BossConfig), which are bodyweight multipliers.
    """
    from .services import summarize_strength

    bosses = BossConfig.objects.filter(is_active=True)

    logs = (
        RawActivityLog.objects.filter(user=request.user, event_type="strength")
        .order_by("-occurred_at")
    )
    summaries = [summarize_strength(log) for log in logs]

    bodyweight = _latest_bodyweight(request.user)

    # Best est. 1RM per exercise across all strength logs.
    best_by_ex = {}
    for s in summaries:
        for ex in s["exercises"]:
            key = ex["name"].lower()
            if (ex["est_1rm"] or 0) > best_by_ex.get(key, 0):
                best_by_ex[key] = ex["est_1rm"] or 0

    result = []
    for boss in bosses:
        name_l = boss.exercise_match.lower()
        best = max(
            (v for k, v in best_by_ex.items() if name_l in k), default=0.0
        )
        goal = round(bodyweight * boss.bodyweight_multiplier, 1) if bodyweight else None
        conquered = bool(goal and best and best >= goal)
        progress = (
            round(min(100.0, (best / goal) * 100)) if goal and best else 0
        )
        result.append(
            {
                "name": boss.name,
                "exercise_match": boss.exercise_match,
                "multiplier": boss.bodyweight_multiplier,
                "goal": goal,
                "best_lift": round(best, 1) or None,
                "conquered": conquered,
                "progress_pct": progress,
            }
        )

    return JsonResponse(
        {
            "bodyweight": bodyweight,
            "linked_liftosaur": UserIntegration.objects.filter(
                user=request.user, provider=Provider.LIFTOSAUR, is_active=True
            ).exists(),
            "bosses": result,
            # Personal records moved here from the Strength panel.
            "best_lifts": _best_lifts_from_history(summaries),
        }
    )


@login_required
def recovery_state(request):
    """GET /api/v1/recovery/

    Recovery detail panel data: today's readiness score (recovery engine),
    recent sleep history (SparkyFitness), and the Recovery skill-tree state.
    Sleep XP (8h+ = 50, 5-8h = 20) is credited to the Recovery tree by the
    gamification layer when sleep logs are ingested.
    """
    from .services import summarize_sleep

    user = request.user
    sparky = UserIntegration.objects.filter(
        user=user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    has_key = bool((sparky.credentials or {}).get("api_key")) if sparky else False

    logs = _bounded_logs(
        request,
        RawActivityLog.objects.filter(
            user=user, event_type="sleep"
        ).order_by("-occurred_at"),
    )
    _raw = _raw_requested(request)
    history = []
    for _log in logs:
        _item = summarize_sleep(_log)
        if _raw:
            _item["raw_payload"] = _log.payload
        history.append(_item)

    today_str = timezone.localdate().isoformat()
    today = next((h for h in history if h["date"] == today_str), None)
    if today is None and history:
        today = history[0]

    readiness = compute_readiness(user, on_date=timezone.localdate())

    st, _ = SkillTree.objects.get_or_create(
        user=user,
        modality=Modality.RECOVERY,
        defaults={"level": 1, "xp": 0, "total_xp": 0},
    )

    return JsonResponse(
        {
            "linked": sparky is not None,
            "demo": sparky is not None and not has_key,
            "readiness": {
                "score": readiness.score,
                "streak_requirement": readiness.streak_requirement,
                "message": readiness.message,
                "body_battery": readiness.body_battery,
                "sleep_hours": readiness.sleep_hours,
            },
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


# ---------------------------------------------------------------------------
# Phase 9 (docs/15): Token, Gacha & Battle
# ---------------------------------------------------------------------------
def _load_combat_post_body(request):
    try:
        return json.loads(request.body or b"{}") or {}
    except json.JSONDecodeError:
        return {}


@login_required
def battle_state(request):
    """GET /battle/state - campaigns, sieges, stamina, loadout summary."""
    return JsonResponse(combat_battle_state(request.user))


@login_required
def battle_campaign(request, campaign):
    """GET /battle/campaign/<campaign> - boss detail + today's damage preview."""
    from .services import (
        active_buff_multiplier,
        additive_bonus,
        base_damage_for,
        boss_vulnerability,
        stat_breakdown_for,
        total_gear_multiplier,
    )

    prog = CampaignProgress.objects.filter(
        user=request.user, campaign=campaign
    ).select_related("boss").first()
    boss = CampaignBoss.objects.filter(campaign=campaign, is_active=True).order_by("sort_order").first()
    profile_obj = combat_profile(request.user)
    flat = additive_bonus(profile_obj, request.user, campaign)
    base = base_damage_for(campaign, request.user) + flat
    gear_mult = total_gear_multiplier(profile_obj, request.user, campaign)
    ref = (prog.boss if prog and prog.boss else boss)
    vuln = boss_vulnerability(ref, campaign) if ref else 1.0
    buff_mult = active_buff_multiplier(profile_obj, campaign)
    est_damage = int(base * gear_mult * vuln * buff_mult)
    stat_info = stat_breakdown_for(campaign, request.user)
    return JsonResponse({
        "campaign": campaign,
        "boss": {
            "slug": ref.slug if ref else None,
            "name": ref.name if ref else None,
            "icon": ref.icon if ref else None,
            "hp_total": (prog.total_hp if prog else (boss.hp_total if boss else 0)),
            "damage_dealt": prog.damage_dealt if prog else 0,
            "conquered": prog.conquered if prog else False,
            "weaknesses": ref.weaknesses if ref else [],
            "resistances": ref.resistances if ref else [],
            "mechanics": ref.mechanics if ref else {},
        },
        "today_base_damage": base,
        "stat_breakdown": stat_info,
        "flat_bonus": flat,
        "gear_multiplier": round(gear_mult, 2),
        "boss_multiplier": round(buff_mult * vuln, 2),
        "vulnerability": vuln,
        "est_damage_per_attack": est_damage,
        "wallet": wallet_dump(profile_obj),
    })


@login_required
@require_POST
def battle_engage(request):
    """POST /battle/engage {"campaign"} - engage a boss in a campaign."""
    data = _load_combat_post_body(request)
    campaign = str(data.get("campaign", "") or "").strip()
    valid = [c for c, _ in CampaignBoss._meta.get_field("campaign").choices]
    if campaign not in valid:
        return _json_error("Invalid campaign.", 400)
    prog, err = combat_engage_boss(request.user, campaign)
    if err:
        return _json_error(err, 400)
    return JsonResponse({"ok": True, "campaign": campaign, "boss": prog.boss.slug if prog.boss else None})


@login_required
@require_POST
def battle_attack(request):
    """POST /battle/attack {"campaign"} - spend 1 stamina on a siege attack."""
    data = _load_combat_post_body(request)
    campaign = str(data.get("campaign", "") or "").strip()
    valid = [c for c, _ in CampaignBoss._meta.get_field("campaign").choices]
    if campaign not in valid:
        return _json_error("Invalid campaign.", 400)
    result, err = combat_attack_boss(request.user, campaign)
    if err:
        return _json_error(err, 400)
    return JsonResponse({"ok": True, **result, "wallet": wallet_dump(combat_profile(request.user))})


@login_required
def battle_leaderboard(request, campaign):
    """GET /battle/leaderboard/<campaign> - docs/17 #33: rank siege damage dealt
    to the current boss among the user's friends / flock."""
    campaign = str(campaign or "").strip()
    valid = [c for c, _ in CampaignBoss._meta.get_field("campaign").choices]
    if campaign not in valid:
        return _json_error("Invalid campaign.", 400)
    return JsonResponse(combat_battle_leaderboard(request.user, campaign))


@login_required
def battle_history(request, campaign):
    """GET /battle/history/<campaign> - docs/17 #34: browsable siege kill
    timeline / diary (conquests + halved bosses) for one campaign."""
    campaign = str(campaign or "").strip()
    valid = [c for c, _ in CampaignBoss._meta.get_field("campaign").choices]
    if campaign not in valid:
        return _json_error("Invalid campaign.", 400)
    return JsonResponse(combat_battle_history(request.user, campaign))


@login_required
def shop_state(request):
    """GET /shop/state - packs + owned gear buckets + wallet."""
    profile_obj = combat_profile(request.user)
    packs = [
        {
            "slug": p.slug, "name": p.name, "description": p.description,
            "icon": p.icon, "price_tokens": p.price_tokens, "draws": p.draws,
            "domains": p.domains, "guaranteed_min_rarity": p.guaranteed_min_rarity,
        }
        for p in GearPackDef.objects.filter(is_active=True)
    ]
    owned = {}
    for ug in UserGear.objects.filter(user=request.user).select_related("gear_def"):
        slot = ug.gear_def.slot or ("consumable" if ug.gear_def.is_consumable else "gear")
        owned.setdefault(slot, []).append({
            "id": ug.pk, "slug": ug.gear_def.slug, "name": ug.gear_def.name,
            "rarity": ug.rarity, "quantity": ug.quantity,
            "icon": ug.gear_def.icon, "equipped_slot": ug.equipped_slot,
            "effect_type": ug.gear_def.effect_type,
            "effect_domain": ug.gear_def.effect_domain,
            "effect_value": ug.gear_def.effect_value,
            "effect_params": ug.gear_def.effect_params or {},
            "is_consumable": ug.gear_def.is_consumable,
        })
    # Items eligible for recycling: anything not currently equipped.
    recyclable = []
    for bucket, items in owned.items():
        for it in items:
            if it.get("equipped_slot"):
                continue
            sv = combat_scrap_value(it["rarity"])
            recyclable.append({
                **it,
                "bucket": bucket,
                "scrap_value": sv,
                "total_scraps": sv * int(it.get("quantity", 0)),
            })
    return JsonResponse({
        "wallet": wallet_dump(profile_obj),
        "packs": packs,
        "owned": owned,
        "recyclable": recyclable,
        "scrap_shop": combat_scrap_shop_state(),
    })


@login_required
@require_POST
def shop_open(request):
    """POST /shop/open {"pack_slug", "quantity"} - spend tokens, pull a pack (or
    several at once; bulk tiers discount the price)."""
    data = _load_combat_post_body(request)
    slug = str(data.get("pack_slug", "") or "").strip()
    pack = GearPackDef.objects.filter(slug=slug, is_active=True).first()
    if pack is None:
        return _json_error("Unknown pack.", 404)
    try:
        quantity = max(1, int(data.get("quantity", 1)))
    except (TypeError, ValueError):
        quantity = 1
    if quantity <= 10:
        ok, err, payload = combat_open_pack_bulk(request.user, pack, quantity)
    else:
        # > 10 copies: just repeat single pulls (keeps the math simple & caps cost).
        ok = True
        err = None
        manifest = []
        for _ in range(quantity):
            ok2, err2, m2 = combat_open_pack(request.user, pack)
            if not ok2:
                ok, err = False, err2
                break
            manifest.extend(m2)
        payload = {"quantity": quantity, "cost": pack.price_tokens * quantity,
                   "discount_pct": 0, "manifest": manifest}
    if not ok:
        return _json_error(err, 400)
    return JsonResponse({
        "ok": True,
        "quantity": payload["quantity"],
        "cost": payload["cost"],
        "discount_pct": payload["discount_pct"],
        "manifest": payload["manifest"],
        "wallet": wallet_dump(combat_profile(request.user)),
    })


@login_required
@require_POST
def shop_consume(request):
    """POST /shop/consume {"gear_id"} - use a consumable."""
    data = _load_combat_post_body(request)
    try:
        gear_id = int(data.get("gear_id"))
    except (TypeError, ValueError):
        return _json_error("gear_id must be an integer.", 400)
    profile_obj = combat_profile(request.user)
    ok, err = consume_consumable(profile_obj, request.user, gear_id)
    if not ok:
        return _json_error(err, 404 if "not found" in err else 400)
    return JsonResponse({"ok": True, "wallet": wallet_dump(profile_obj)})


@login_required
@require_POST
def scrap_recycle(request):
    """POST /scrap/recycle {\"gear_id\", \"quantity\"} - turn gear into scraps.

    Equipped gear cannot be recycled; the item (or ``quantity`` of its stack) is
    removed and the user's scraps wallet is credited.
    """
    data = _load_combat_post_body(request)
    try:
        gear_id = int(data.get("gear_id"))
    except (TypeError, ValueError):
        return _json_error("gear_id must be an integer.", 400)
    try:
        quantity = int(data.get("quantity", "1") or "1")
    except (TypeError, ValueError):
        quantity = 1
    ug = UserGear.objects.filter(pk=gear_id, user=request.user).first()
    if ug is None:
        return _json_error("Item not found.", 404)
    if ug.equipped_slot:
        return _json_error("Unequip an item before recycling it.", 400)
    ok, err, gain = combat_recycle_gear(request.user, gear_id, quantity)
    if not ok:
        return _json_error(err, 400)
    return JsonResponse({"ok": True, "scraps_gained": gain, "wallet": wallet_dump(combat_profile(request.user))})


@login_required
def scrap_shop(request):
    """GET /scrap/shop/state - today's rotating Scrap Shop offering + scraps wallet."""
    profile_obj = combat_profile(request.user)
    return JsonResponse({
        "wallet": wallet_dump(profile_obj),
        "scrap_shop": combat_scrap_shop_state(),
    })


@login_required
@require_POST
def scrap_buy(request):
    """POST /scrap/shop/buy {\"item_slug\"} - buy a Scrap Shop item with scraps."""
    data = _load_combat_post_body(request)
    slug = str(data.get("item_slug", "") or "").strip()
    if not slug:
        return _json_error("item_slug is required.", 400)
    result, err = combat_buy_scrap_item(request.user, slug)
    if err:
        return _json_error(err, 400)
    return JsonResponse({"ok": True, **result, "wallet": wallet_dump(combat_profile(request.user))})




@login_required
def loadout_state(request):
    """GET /loadout/state - equipped slots + the full owned inventory."""
    from core.services import SLOT_ORDER

    profile_obj = combat_profile(request.user)
    equipped = {}
    for slot in SLOT_ORDER:
        ug = UserGear.objects.filter(user=request.user, equipped_slot=slot).select_related("gear_def").first()
        equipped[slot] = {
            "id": ug.pk, "slug": ug.gear_def.slug, "name": ug.gear_def.name,
            "rarity": ug.rarity, "icon": ug.gear_def.icon,
            "effect_type": ug.gear_def.effect_type,
            "effect_domain": ug.gear_def.effect_domain,
            "effect_value": ug.gear_def.effect_value,
            "description": ug.gear_def.description,
            "obtained_at": ug.obtained_at.isoformat(),
            "pack_name": ug.gear_def.pack.name if ug.gear_def.pack else None,
            "quantity": ug.quantity,
        } if ug else None
    owned = [
        {
            "id": ug.pk, "slug": ug.gear_def.slug, "name": ug.gear_def.name,
            "slot": ug.gear_def.slot or "accessory", "rarity": ug.rarity, "icon": ug.gear_def.icon,
            "effect_type": ug.gear_def.effect_type,
            "effect_domain": ug.gear_def.effect_domain,
            "effect_value": ug.gear_def.effect_value,
            "description": ug.gear_def.description,
            "obtained_at": ug.obtained_at.isoformat(),
            "pack_name": ug.gear_def.pack.name if ug.gear_def.pack else None,
            "quantity": ug.quantity,
            "equipped": bool(ug.equipped_slot),
            "scrap_value": combat_scrap_value(ug.rarity),
            "total_scraps": combat_scrap_value(ug.rarity) * ug.quantity,
        }
        for ug in UserGear.objects.filter(
            user=request.user, gear_def__is_consumable=False
        ).select_related("gear_def").order_by("gear_def__sort_order", "gear_def__slug", "-obtained_at")
    ]
    candidates = [o for o in owned if not o["equipped"]]
    return JsonResponse({
        "wallet": wallet_dump(profile_obj),
        "equipped": equipped,
        "candidates": candidates,
        "owned": owned,
    })


@login_required
@require_POST
def loadout_equip(request):
    """POST /loadout/equip {"gear_id"} - equip (replaces the prior item in that slot)."""
    data = _load_combat_post_body(request)
    try:
        gear_id = int(data.get("gear_id"))
    except (TypeError, ValueError):
        return _json_error("gear_id must be an integer.", 400)
    ug = UserGear.objects.filter(pk=gear_id, user=request.user).select_related("gear_def").first()
    if ug is None:
        return _json_error("Item not found.", 404)
    if ug.gear_def.is_consumable:
        return _json_error("Consumables cannot be equipped.", 400)
    slot = ug.gear_def.slot or "accessory"
    with transaction.atomic():
        UserGear.objects.filter(user=request.user, equipped_slot=slot).update(equipped_slot=None)
        ug.equipped_slot = slot
        ug.save(update_fields=["equipped_slot"])
    return JsonResponse({"ok": True, "slot": slot, "wallet": wallet_dump(combat_profile(request.user))})


@login_required
@require_POST
def loadout_unequip(request):
    """POST /loadout/unequip {"gear_id"} - stop using an item (returns it to the
    unequipped candidate pool)."""
    data = _load_combat_post_body(request)
    try:
        gear_id = int(data.get("gear_id"))
    except (TypeError, ValueError):
        return _json_error("gear_id must be an integer.", 400)
    ug = UserGear.objects.filter(pk=gear_id, user=request.user).select_related("gear_def").first()
    if ug is None:
        return _json_error("Item not found.", 404)
    if ug.gear_def.is_consumable:
        return _json_error("Consumables cannot be equipped.", 400)
    if not ug.equipped_slot:
        return _json_error("Item is not equipped.", 400)
    ug.equipped_slot = None
    ug.save(update_fields=["equipped_slot"])
    return JsonResponse({"ok": True, "slot": ug.gear_def.slot, "wallet": wallet_dump(combat_profile(request.user))})


@login_required
def pvp_state(request):
    """GET /pvp/state - my gym/turf, attackable gyms, match history."""
    return JsonResponse(combat_pvp_state(request.user))


@login_required
@require_POST
def pvp_defend(request):
    """POST /pvp/defend {"terrain", "name"} - set defensive loadout snapshot."""
    data = _load_combat_post_body(request)
    terrain = str(data.get("terrain", "") or "").strip()
    name = str(data.get("name", "") or "").strip() or None
    gym = combat_set_defense(request.user, terrain=terrain or None, name=name)
    return JsonResponse({"ok": True, "gym": {"id": gym.pk, "name": gym.name, "terrain": gym.terrain}})


@login_required
@require_POST
def pvp_attack(request):
    """POST /pvp/attack {"gym_id"} - instant async gym battle."""
    data = _load_combat_post_body(request)
    try:
        gym_id = int(data.get("gym_id"))
    except (TypeError, ValueError):
        return _json_error("gym_id must be an integer.", 400)
    gym = Gym.objects.filter(pk=gym_id, is_active=True).first()
    if gym is None:
        return _json_error("Gym not found.", 404)
    if gym.owner == request.user:
        return _json_error("You cannot attack your own Gym.", 400)
    result, err = combat_attack_gym(request.user, gym)
    if err:
        return _json_error(err, 400)
    return JsonResponse({"ok": True, **result, "wallet": wallet_dump(combat_profile(request.user))})


@login_required
def dashboard_state(request):
    """GET /api/v1/dashboard/state (Step 16)."""

    user = request.user

    profile_obj = combat_profile(user)
    daily_token_harvest(user, on_date=timezone.localdate())

    # Readiness for today. Always recompute so a fresh value is shown even if
    # the daily Celery beat hasn't run yet (compute is idempotent + cheap).
    today = timezone.localdate()
    readiness = compute_readiness(user, on_date=today)

    # Calculate today's XP per modality from XPLedger
    today_xp_qs = (
        XPLedger.objects.filter(user=user, created_at__date=today)
        .values("modality")
        .annotate(today_xp=Sum("amount"))
    )
    today_xp_map = {row["modality"]: (row["today_xp"] or 0) for row in today_xp_qs}

    skill_trees = {}
    for tree in SkillTree.objects.filter(user=user):
        skill_trees[tree.modality] = {
            "level": tree.level,
            "progress_pct": tree.progress_pct,
            "xp": tree.xp,
            "total_xp": tree.total_xp,
            "today_xp": today_xp_map.get(tree.modality, 0),
        }

    return JsonResponse(
        {
            "user": {
                "username": user.username,
                "streak": user.streak,
                "avatar": avatar_url(user),
            },
            "onboarded": bool(profile_obj.onboarded),
            "resources": wallet_dump(profile_obj),
            "readiness": {
                "score": readiness.score,
                "streak_requirement": readiness.streak_requirement,
                "message": readiness.message,
            },
            "skill_trees": skill_trees,
        }
    )


@login_required
@require_POST
def complete_onboarding(request):
    """POST /api/v1/onboarded - mark the guided first-flight tour as done.

    Idempotent: setting ``onboarded`` to True is a no-op if it is already set.
    Called from dashboard.js when the user finishes or skips the onboarding
    walkthrough (docs/17 #91).
    """
    profile_obj = combat_profile(request.user)
    if not profile_obj.onboarded:
        profile_obj.onboarded = True
        profile_obj.save(update_fields=["onboarded"])
    return JsonResponse({"ok": True, "onboarded": True})


def leaderboard_weekly(request):
    """GET /api/v1/leaderboard/weekly (Step 17) + like-with-like filter (docs/17 #17).

    Aggregates XPLedger over the rolling 7-day window per user. An optional
    ``?kind=`` query param (a ``Modality`` value, e.g. ``endurance``) restricts
    the board to a single modality so users can compare like-with-like effort
    (only strength, only cardio, only hydration, etc.). An unknown ``kind``
    returns a 400 so a mistyped filter never silently shows the whole board.
    """
    since = timezone.now() - timedelta(days=7)
    qs = XPLedger.objects.filter(created_at__gte=since)

    kinds = [{"value": value, "label": label} for value, label in Modality.choices]
    kind = request.GET.get("kind", "").strip().lower()
    if kind:
        valid = dict(Modality.choices)
        if kind not in valid:
            return JsonResponse(
                {
                    "error": f"Invalid kind '{kind}'. Choose from "
                    f"{[k['value'] for k in kinds]}."
                },
                status=400,
            )
        qs = qs.filter(modality=kind)

    rows = (
        qs.values("user__username", "user__avatar")
        .annotate(total_xp=Sum("amount"))
        .order_by("-total_xp")
    )
    leaderboard = [
        {
            "rank": index,
            "username": row["user__username"],
            "avatar": row["user__avatar"],
            "total_xp": row["total_xp"],
        }
        for index, row in enumerate(rows, start=1)
    ]
    return JsonResponse(
        {
            "leaderboard": leaderboard,
            "window_days": 7,
            "kind": kind or "all",
            "kinds": kinds,
        }
    )


# ---------------------------------------------------------------------------
# Phase 8 (docs/13): Leagues, Challenges & Flocks
# ---------------------------------------------------------------------------
def _social_json(request):
    """Fresh social snapshot - every friend/flock mutation returns this."""
    return JsonResponse({"ok": True, **social_state(request.user)})


@login_required
def leagues_state(request):
    """GET /api/v1/leagues/ (docs/13 §6.1).

    Live weekly league board (ranks + tiers), the caller's rank/tier, and the
    persisted history of closed weeks. ``ensure_current_week`` lazily closes
    stale weeks so a beat outage never loses a snapshot.
    """
    return JsonResponse(league_state(request.user))


@login_required
def challenges_state(request):
    """GET /api/v1/challenges/ (docs/13 §6.2).

    The single active challenge (default: calories burned in the last 30
    days) with a live ranked progress board.
    """
    return JsonResponse(challenge_state(request.user))


@login_required
def social_state_view(request):
    """GET /api/v1/social/ (docs/13 §6.3).

    Friends, requests, the caller's flock + invites, and (with ``?q=``)
    find-friends search results.
    """
    query = request.GET.get("q", "").strip()
    return JsonResponse(social_state(request.user, q=query or None))


@login_required
@require_POST
def friends_request(request):
    """POST /friends/request {"username"} - send (or auto-accept) a request."""
    data = _load_combat_post_body(request)
    ok, result = send_friend_request(request.user, data.get("username"))
    if not ok:
        return _json_error(result["message"], result["status"])
    return _social_json(request)


@login_required
@require_POST
def friends_respond(request):
    """POST /friends/respond {"user_id", "action": accept|decline}."""
    data = _load_combat_post_body(request)
    action = str(data.get("action", "") or "").strip().lower()
    if action not in ("accept", "decline"):
        return _json_error("action must be 'accept' or 'decline'.", 400)
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return _json_error("user_id must be an integer.", 400)
    ok, result = respond_friend_request(request.user, user_id, action == "accept")
    if not ok:
        return _json_error(result["message"], result["status"])
    return _social_json(request)


@login_required
@require_POST
def friends_remove(request):
    """POST /friends/remove {"user_id"} - end a friendship."""
    data = _load_combat_post_body(request)
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return _json_error("user_id must be an integer.", 400)
    ok, result = remove_friend(request.user, user_id)
    if not ok:
        return _json_error(result["message"], result["status"])
    return _social_json(request)


@login_required
@require_POST
def flocks_create(request):
    """POST /flocks/create {"name"} - form a new flock (owner role)."""
    data = _load_combat_post_body(request)
    ok, result = create_flock(request.user, data.get("name"))
    if not ok:
        return _json_error(result["message"], result["status"])
    return _social_json(request)


@login_required
@require_POST
def flocks_invite(request):
    """POST /flocks/invite {"user_id"} - owner invites a flockless friend."""
    data = _load_combat_post_body(request)
    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return _json_error("user_id must be an integer.", 400)
    ok, result = invite_to_flock(request.user, user_id)
    if not ok:
        return _json_error(result["message"], result["status"])
    return _social_json(request)


@login_required
@require_POST
def flocks_respond(request):
    """POST /flocks/respond {"flock_id", "action": accept|decline}."""
    data = _load_combat_post_body(request)
    action = str(data.get("action", "") or "").strip().lower()
    if action not in ("accept", "decline"):
        return _json_error("action must be 'accept' or 'decline'.", 400)
    try:
        flock_id = int(data.get("flock_id"))
    except (TypeError, ValueError):
        return _json_error("flock_id must be an integer.", 400)
    ok, result = respond_flock_invite(request.user, flock_id, action == "accept")
    if not ok:
        return _json_error(result["message"], result["status"])
    return _social_json(request)


@login_required
@require_POST
def flocks_leave(request):
    """POST /flocks/leave {} - leave (last member out deletes the flock)."""
    ok, result = leave_flock(request.user)
    if not ok:
        return _json_error(result["message"], result["status"])
    return _social_json(request)


@login_required
def badges_state(request):
    """GET /api/v1/badges/

    Returns the user's achievement badges (Roadmap idea #5). The badge engine
    is a pure derivation over data we already store - no new ingestion. The
    endpoint lazily runs ``badges_state`` which grants any newly-earned badges
    and serializes the full catalog + current grants.
    """
    from .services.badges import badges_state as _badges_state

    return JsonResponse(_badges_state(request.user))


@login_required
def stat_info(request, stat):
    """GET /api/v1/stats/<stat>/ - explain a top-nav stat + earning history.

    Opened by clicking the streak / tokens / stamina badges in the top nav.
    """
    if stat not in STAT_KEYS:
        return _json_error(f"Unknown stat '{stat}'.", 404)

    return JsonResponse(explain_stat(request.user, stat))


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


@csrf_exempt
def sync_health_data(request):
    """POST /api/v1/sync/health - Ingest device Health Connect / HealthKit metrics."""
    if request.method != "POST":
        return _json_error("Method not allowed", 405)

    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    # Determine user: session user > username in body > default first user
    user = request.user if request.user.is_authenticated else None
    if user is None:
        username = data.get("username")
        if username:
            user = User.objects.filter(username=username).first()
    if user is None:
        user = User.objects.order_by("id").first()
    if user is None:
        return _json_error("No user available to attribute health data", 400)

    provider_name = data.get("provider", "health_connect")
    source = Provider.HEALTH_CONNECT if "health" in provider_name.lower() else Provider.HEALTHKIT

    metrics = data.get("metrics", {})
    created_logs = []
    total_xp = 0

    now = timezone.now()
    today_str = timezone.localdate().isoformat()

    # 1. Steps & Active Calories (Endurance domain)
    steps = int(metrics.get("steps", 0) or 0)
    active_calories = float(metrics.get("active_calories", 0) or metrics.get("calories", 0) or 0)
    distance_meters = float(metrics.get("distance_meters", 0) or 0)

    if steps > 0 or active_calories > 0:
        log = RawActivityLog.objects.create(
            user=user,
            source=source,
            event_type="endurance",
            payload={
                "date": today_str,
                "steps": steps,
                "total_calories_burned": active_calories,
                "total_duration_minutes": max(10, int(steps / 100)),
                "distance_meters": distance_meters,
                "source": "health_connect",
            },
            occurred_at=now,
        )
        xp = process_log(log)
        total_xp += sum(e.amount for e in xp)
        created_logs.append(log.pk)

    # 2. Sleep (Recovery domain)
    sleep_hours = float(metrics.get("sleep_hours", 0) or 0)
    if sleep_hours > 0:
        log = RawActivityLog.objects.create(
            user=user,
            source=source,
            event_type="sleep",
            payload={
                "date": today_str,
                "sleep_hours": round(sleep_hours, 1),
                "deep_sleep_hours": round(float(metrics.get("deep_sleep_hours", 0) or 0), 1),
                "source": "health_connect",
            },
            occurred_at=now,
        )
        xp = process_log(log)
        total_xp += sum(e.amount for e in xp)
        created_logs.append(log.pk)

    # 3. Hydration (Water domain)
    water_ml = float(metrics.get("water_ml", 0) or 0)
    water_oz = float(metrics.get("water_oz", 0) or 0)
    if water_ml > 0 and water_oz <= 0:
        water_oz = round(water_ml / 29.5735, 1)

    if water_oz > 0:
        goal_val = float(metrics.get("water_goal_oz", 80) or metrics.get("water_goal", 80) or 80)
        log = RawActivityLog.objects.create(
            user=user,
            source=source,
            event_type="hydration",
            payload={
                "date": today_str,
                "water_intake_oz": water_oz,
                "water_goal_oz": goal_val,
                "water_goal": goal_val,
                "source": "health_connect" if source == Provider.HEALTH_CONNECT else "healthkit",
                "manual": False,
            },
            occurred_at=now,
        )
        xp = process_log(log)
        total_xp += sum(e.amount for e in xp)
        created_logs.append(log.pk)

    # 4. Body Weight (Scale)
    weight_kg = float(metrics.get("weight_kg", 0) or 0)
    weight_lbs = float(metrics.get("weight_lbs", 0) or 0)
    if weight_kg > 0 and weight_lbs <= 0:
        weight_lbs = round(weight_kg * 2.20462, 1)

    if weight_lbs > 0:
        log = RawActivityLog.objects.create(
            user=user,
            source=source,
            event_type="scale",
            payload={
                "date": today_str,
                "weight_lbs": weight_lbs,
                "unit": "lbs",
                "source": "health_connect",
            },
            occurred_at=now,
        )
        xp = process_log(log)
        total_xp += sum(e.amount for e in xp)
        created_logs.append(log.pk)

    # 5. Workouts & Exercise Sessions
    workouts = metrics.get("workouts", [])
    if isinstance(workouts, list):
        for w in workouts:
            w_type = str(w.get("type", "cardio")).lower()
            event_t = "strength" if "strength" in w_type or "weight" in w_type else "cardio"
            w_payload = {
                "date": today_str,
                "class": w.get("title", w.get("name", "Workout")),
                "minutes": int(w.get("duration_minutes", w.get("minutes", 30)) or 30),
                "intensity": w.get("intensity", "moderate"),
                "total_volume_lbs": float(w.get("total_volume_lbs", 0) or 0),
                "calories": float(w.get("calories", 0) or 0),
                "source": "health_connect",
            }
            log = RawActivityLog.objects.create(
                user=user,
                source=source,
                event_type=event_t,
                payload=w_payload,
                occurred_at=now,
            )
            xp = process_log(log)
            total_xp += sum(e.amount for e in xp)
            created_logs.append(log.pk)

    # Lazily check and award badges
    from .services.badges import check_badges
    newly_badges = check_badges(user)

    return JsonResponse(
        {
            "success": True,
            "user": user.username,
            "provider": source,
            "synced_logs_count": len(created_logs),
            "total_xp_awarded": total_xp,
            "newly_awarded_badges": newly_badges,
            "synced_at": now.isoformat(),
        },
        status=200,
    )


@login_required
@require_POST
def quick_log(request):
    """POST /log/quick/ - Manual quick-logging fallback for all habit modalities.

    Accepts JSON body:
      - category / modality: 'hydration' | 'nutrition' | 'cardio' | 'endurance' | 'strength' | 'sleep' | 'recovery' | 'scale'
      - payload parameters for the given category
    """
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    category = str(data.get("category") or data.get("modality") or "").strip().lower()
    if not category:
        return _json_error("Missing 'category' or 'modality' field", 400)

    custom_date_str = str(data.get("date") or "").strip()
    if custom_date_str:
        try:
            target_date = timezone.datetime.strptime(custom_date_str, "%Y-%m-%d").date()
            today_str = target_date.isoformat()
            now = timezone.make_aware(timezone.datetime.combine(target_date, timezone.datetime.now().time()))
        except ValueError:
            return _json_error("Invalid date format, expected YYYY-MM-DD", 400)
    else:
        now = timezone.now()
        today_str = timezone.localdate().isoformat()

    user = request.user
    created_logs = []
    total_xp = 0
    modality_enum = None
    pre_levels = {
        m: (SkillTree.objects.filter(user=user, modality=m).values_list("level", flat=True).first() or 1)
        for m in Modality.values
    }

    if category in ("hydration", "water"):
        amount_oz = float(data.get("water_oz") or data.get("amount") or 0)
        water_ml = float(data.get("water_ml") or 0)
        if amount_oz <= 0 and water_ml > 0:
            amount_oz = round(water_ml / 29.5735, 1)
        if amount_oz <= 0:
            return _json_error("Positive water amount (oz or ml) is required", 400)

        goal_oz = float(data.get("water_goal") or data.get("goal") or 64)
        log = RawActivityLog.objects.create(
            user=user,
            source=Provider.MANUAL,
            event_type="hydration",
            payload={
                "date": today_str,
                "water": amount_oz,
                "water_goal": goal_oz,
                "source": "manual",
            },
            occurred_at=now,
        )
        entries = process_log(log)
        total_xp += sum(e.amount for e in entries)
        created_logs.append(log.pk)
        modality_enum = Modality.HYDRATION

    elif category in ("nutrition", "food", "macro"):
        calories = float(data.get("calories") or 0)
        protein = float(data.get("protein") or data.get("protein_g") or 0)
        if calories <= 0 and protein <= 0:
            return _json_error("Calories or protein must be greater than 0", 400)

        cal_goal = float(data.get("calorie_goal") or 2500)
        pro_goal = float(data.get("protein_goal") or 100)

        under_calorie = data.get("under_calorie")
        if under_calorie is None:
            under_calorie = calories <= cal_goal if calories > 0 else True
        else:
            under_calorie = bool(under_calorie)

        protein_hit = data.get("protein_hit")
        if protein_hit is None:
            protein_hit = protein >= pro_goal if protein > 0 else False
        else:
            protein_hit = bool(protein_hit)

        food_name = data.get("food_name") or data.get("name") or "Quick Meal"
        log = RawActivityLog.objects.create(
            user=user,
            source=Provider.MANUAL,
            event_type="macro",
            payload={
                "date": today_str,
                "calories": int(calories),
                "protein": round(protein, 1),
                "under_calorie": under_calorie,
                "protein_hit": protein_hit,
                "food_entries": [
                    {
                        "food_name": food_name,
                        "protein": round(protein, 1),
                        "calories": int(calories),
                    }
                ],
                "source": "manual",
            },
            occurred_at=now,
        )
        entries = process_log(log)
        total_xp += sum(e.amount for e in entries)
        created_logs.append(log.pk)
        modality_enum = Modality.NUTRITION

    elif category in ("cardio", "endurance"):
        minutes = int(data.get("minutes") or data.get("duration_minutes") or 0)
        calories_burned = float(data.get("calories_burned") or data.get("calories") or 0)
        intensity = str(data.get("intensity") or "moderate").strip().lower()
        workout_type = data.get("workout_type") or data.get("class") or "Cardio Workout"

        if minutes <= 0 and calories_burned <= 0:
            return _json_error("Minutes or calories burned must be greater than 0", 400)

        if calories_burned > 0:
            log = RawActivityLog.objects.create(
                user=user,
                source=Provider.MANUAL,
                event_type="endurance",
                payload={
                    "date": today_str,
                    "total_calories_burned": calories_burned,
                    "total_duration_minutes": minutes or max(10, int(calories_burned / 10)),
                    "exercise_entries": [
                        {
                            "name": workout_type,
                            "duration": minutes,
                            "calories": calories_burned,
                        }
                    ],
                    "source": "manual",
                },
                occurred_at=now,
            )
        else:
            log = RawActivityLog.objects.create(
                user=user,
                source=Provider.MANUAL,
                event_type="cardio",
                payload={
                    "date": today_str,
                    "minutes": minutes,
                    "intensity": intensity,
                    "class": workout_type,
                    "source": "manual",
                },
                occurred_at=now,
            )
        entries = process_log(log)
        total_xp += sum(e.amount for e in entries)
        created_logs.append(log.pk)
        modality_enum = Modality.ENDURANCE

    elif category in ("strength", "lifting", "weights"):
        volume_lbs = float(data.get("volume_lbs") or data.get("total_volume_lbs") or 0)
        duration_minutes = int(data.get("duration_minutes") or data.get("minutes") or 30)
        program = data.get("program") or data.get("name") or "Strength Session"
        pr = bool(data.get("pr", False))
        completed = bool(data.get("completed", True))

        if volume_lbs <= 0 and duration_minutes <= 0:
            return _json_error("Volume (lbs) or workout duration must be greater than 0", 400)

        log = RawActivityLog.objects.create(
            user=user,
            source=Provider.MANUAL,
            event_type="strength",
            payload={
                "date": today_str,
                "program": program,
                "total_volume_lbs": volume_lbs,
                "duration_minutes": duration_minutes,
                "completed": completed,
                "pr": pr,
                "source": "manual",
            },
            occurred_at=now,
        )
        entries = process_log(log)
        total_xp += sum(e.amount for e in entries)
        created_logs.append(log.pk)
        modality_enum = Modality.STRENGTH

    elif category in ("sleep", "recovery"):
        sleep_hours = float(data.get("sleep_hours") or data.get("hours") or 0)
        if sleep_hours <= 0:
            return _json_error("Sleep hours must be greater than 0", 400)

        log = RawActivityLog.objects.create(
            user=user,
            source=Provider.MANUAL,
            event_type="sleep",
            payload={
                "date": today_str,
                "sleep_hours": round(sleep_hours, 1),
                "source": "manual",
            },
            occurred_at=now,
        )
        entries = process_log(log)
        total_xp += sum(e.amount for e in entries)
        created_logs.append(log.pk)
        modality_enum = Modality.RECOVERY

    elif category in ("scale", "bodyweight", "weight"):
        weight_lbs = float(data.get("weight_lbs") or data.get("weight") or 0)
        weight_kg = float(data.get("weight_kg") or 0)
        if weight_lbs <= 0 and weight_kg > 0:
            weight_lbs = round(weight_kg * 2.20462, 1)
        if weight_lbs <= 0:
            return _json_error("Positive body weight is required", 400)

        body_fat = float(data.get("body_fat") or data.get("body_fat_pct") or 0)
        log = RawActivityLog.objects.create(
            user=user,
            source=Provider.MANUAL,
            event_type="scale",
            payload={
                "date": today_str,
                "weight_lbs": weight_lbs,
                "body_fat": body_fat if body_fat > 0 else None,
                "unit": "lbs",
                "source": "manual",
            },
            occurred_at=now,
        )
        entries = process_log(log)
        total_xp += sum(e.amount for e in entries)
        created_logs.append(log.pk)

    else:
        return _json_error(
            f"Unsupported category '{category}'. Valid categories: hydration, nutrition, cardio, strength, sleep, scale",
            400,
        )

    # Lazily check and award badges
    from .services.badges import check_badges
    newly_badges = check_badges(user)

    level_ups = []
    for m in Modality.values:
        curr_lvl = SkillTree.objects.filter(user=user, modality=m).values_list("level", flat=True).first() or 1
        old_lvl = pre_levels.get(m, 1)
        if curr_lvl > old_lvl:
            tokens_gain = (curr_lvl - old_lvl) * 25
            prof = combat_profile(user)
            prof.tokens += tokens_gain
            prof.save(update_fields=["tokens"])
            level_ups.append({
                "modality": m,
                "old_level": old_lvl,
                "new_level": curr_lvl,
                "bonus_tokens": tokens_gain,
            })

    skill_tree_data = None
    if modality_enum:
        st = SkillTree.objects.filter(user=user, modality=modality_enum).first()
        if st:
            skill_tree_data = {
                "modality": st.modality,
                "level": st.level,
                "xp": st.xp,
                "total_xp": st.total_xp,
                "progress_pct": st.progress_pct,
            }

    return JsonResponse(
        {
            "success": True,
            "category": category,
            "xp_awarded": total_xp,
            "created_log_ids": created_logs,
            "newly_awarded_badges": newly_badges,
            "level_ups": level_ups,
            "skill_tree": skill_tree_data,
            "message": f"Successfully logged {category} (+{total_xp} XP)!",
        },
        status=200,
    )


@login_required
def missing_logs_queue(request):
    """GET /api/v1/queue/missing-logs/ - Returns missing food/hydration days for trailing window."""
    from .services.historical_queue import find_missing_habit_days

    days_str = request.GET.get("days", "7")
    try:
        days = int(days_str)
    except ValueError:
        days = 7
    days = min(30, max(1, days))

    missing = find_missing_habit_days(request.user, days=days)
    return JsonResponse(
        {
            "success": True,
            "missing_days": missing,
            "total_missing_count": len(missing),
            "days_scanned": days,
        },
        status=200,
    )


@login_required
def source_preferences_view(request):
    """GET/POST /profile/sources/ - Manage data provider routing preferences."""
    profile = combat_profile(request.user)

    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return _json_error("Invalid JSON body", 400)

        prefs = profile.source_preferences or {}
        for key in ("hydration", "nutrition", "endurance", "strength", "recovery"):
            if key in body:
                prefs[key] = str(body[key]).strip().lower()

        profile.source_preferences = prefs
        profile.save(update_fields=["source_preferences"])
        return JsonResponse({"success": True, "source_preferences": prefs})

    defaults = {
        "hydration": "sparkyfitness",
        "nutrition": "sparkyfitness",
        "endurance": "health_connect",
        "strength": "liftosaur",
        "recovery": "sparkyfitness",
    }
    current = {**defaults, **(profile.source_preferences or {})}
    return JsonResponse({"success": True, "source_preferences": current})


@login_required
def foods_search(request):
    """GET /foods/search/ - Search food catalog via SparkyFitness API client."""
    return nutrition_search_foods(request)


@login_required
def nutrition_recent_foods(request):
    """GET /api/v1/nutrition/recent-foods/ - User's frequent and recent foods from Sparky."""
    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    api_key = (sparky.credentials.get("api_key") if sparky else None) or ""

    from .services.sparky_client import SparkyFitnessClient

    client = SparkyFitnessClient()
    recent = client.get_recent_foods(api_key, days=30)
    meal_types = client.get_meal_types(api_key)
    return JsonResponse({"success": True, "recent_foods": recent, "meal_types": meal_types})


@login_required
def nutrition_search_foods(request):
    """GET /api/v1/nutrition/search-foods/?q=... - Live food database search with external and AI expansion."""
    query = request.GET.get("q", "")
    expand = request.GET.get("expand", "true").lower() in ("true", "1", "yes")
    use_ai = request.GET.get("use_ai", "false").lower() in ("true", "1", "yes")

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    api_key = (sparky.credentials.get("api_key") if sparky else None) or ""

    from .services.sparky_client import SparkyFitnessClient

    client = SparkyFitnessClient()
    results = client.search_foods(api_key, query, include_external=expand, use_ai_fallback=use_ai)
    return JsonResponse({"success": True, "query": query, "results": results})


@login_required
@require_POST
def nutrition_ai_generate_food(request):
    """POST /api/v1/nutrition/ai-generate-food/ - Generate macro profile using Sparky native AI."""
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    food_name = (data.get("food_name") or data.get("name") or "").strip()
    unit = (data.get("unit") or "serving").strip()
    if not food_name:
        return _json_error("Missing food_name", 400)

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    api_key = (sparky.credentials.get("api_key") if sparky else None) or ""

    from .services.sparky_client import SparkyFitnessClient

    client = SparkyFitnessClient()
    generated = client.generate_food_ai(api_key, food_name, unit=unit)
    if not generated:
        generated = {
            "name": food_name,
            "calories": 350.0,
            "protein": 25.0,
            "carbs": 30.0,
            "fat": 12.0,
            "serving": f"1 {unit}",
            "brand": "Sparky AI",
            "confidence": 0.75,
        }

    return JsonResponse({"success": True, "food": generated})


@login_required
@require_POST
def nutrition_create_food(request):
    """POST /api/v1/nutrition/create-food/ - Persist a custom or AI-generated food in Sparky backend."""
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    name = (data.get("name") or data.get("food_name") or "").strip()
    if not name:
        return _json_error("Missing food name", 400)

    calories = float(data.get("calories") or 0.0)
    protein = float(data.get("protein") or 0.0)
    carbs = float(data.get("carbs") or 0.0)
    fat = float(data.get("fat") or 0.0)
    serving = str(data.get("serving") or data.get("serving_size") or "1 serving")
    brand = str(data.get("brand") or "Custom")

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    api_key = (sparky.credentials.get("api_key") if sparky else None) or ""

    from .services.sparky_client import SparkyFitnessClient

    client = SparkyFitnessClient()
    created = client.create_custom_food(
        api_key=api_key,
        name=name,
        calories=calories,
        protein=protein,
        carbs=carbs,
        fat=fat,
        serving=serving,
        brand=brand,
    )

    created_id = created.get("id") if isinstance(created, dict) else None

    return JsonResponse({
        "success": True,
        "food": {
            "id": str(created_id or f"custom-{abs(hash(name))}"),
            "food_id": str(created_id or ""),
            "name": name,
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "fat": fat,
            "serving": serving,
            "brand": brand,
            "is_custom": True,
            "source": "sparky_db",
        },
        "sparky_response": created,
    })


@login_required
def nutrition_barcode_lookup(request):
    """GET /api/v1/nutrition/barcode/?code=... - Instant barcode scan lookup via Sparky backend."""
    code = (request.GET.get("code") or "").strip()
    if not code:
        return _json_error("Missing barcode", 400)

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    api_key = (sparky.credentials.get("api_key") if sparky else None) or ""

    from .services.sparky_client import SparkyFitnessClient

    client = SparkyFitnessClient()
    food = client.lookup_barcode(api_key, code)
    if not food:
        return JsonResponse({"success": False, "barcode": code, "error": f"Barcode {code} not found."})

    return JsonResponse({"success": True, "barcode": code, "food": food})


@login_required
@require_POST
def nutrition_quick_log(request):
    """POST /api/v1/nutrition/quick-log/ - 1-tap food logging to Sparky & immediate XP award."""
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    food_name = (data.get("food_name") or data.get("name") or "").strip()
    if not food_name:
        return _json_error("Missing food_name", 400)

    quantity = max(float(data.get("quantity") or 1.0), 0.01)
    if "base_calories" in data:
        serving_cal = float(data.get("base_calories") or 0.0)
        serving_pro = float(data.get("base_protein") or 0.0)
        serving_carb = float(data.get("base_carbs") or 0.0)
        serving_fat = float(data.get("base_fat") or 0.0)
        calories = round(serving_cal * quantity, 1)
        protein = round(serving_pro * quantity, 1)
        carbs = round(serving_carb * quantity, 1)
        fat = round(serving_fat * quantity, 1)
    else:
        calories = float(data.get("calories") or 0.0)
        protein = float(data.get("protein") or 0.0)
        carbs = float(data.get("carbs") or 0.0)
        fat = float(data.get("fat") or 0.0)
        serving_cal = round(calories / quantity, 1)
        serving_pro = round(protein / quantity, 1)
        serving_carb = round(carbs / quantity, 1)
        serving_fat = round(fat / quantity, 1)

    meal_type = data.get("meal_type") or "Lunch"
    unit = str(data.get("unit") or "serving")
    food_id = data.get("food_id")
    variant_id = data.get("variant_id")
    brand_name = data.get("brand_name") or ""
    entry_date = data.get("entry_date") or data.get("date") or timezone.localdate().isoformat()
    try:
        target_date = datetime.date.fromisoformat(entry_date)
    except Exception:
        target_date = timezone.localdate()
        entry_date = target_date.isoformat()

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    api_key = (sparky.credentials.get("api_key") if sparky else None) or ""

    from .services.sparky_client import SparkyFitnessClient

    client = SparkyFitnessClient()

    # Always ensure food is created in Sparky DB if missing food_id or created via AI
    if api_key and (not food_id or data.get("create_custom") or data.get("source") in ("sparky_ai", "sparky_ai_created")):
        try:
            created = client.create_custom_food(
                api_key=api_key,
                name=food_name,
                calories=serving_cal,
                protein=serving_pro,
                carbs=serving_carb,
                fat=serving_fat,
                serving=unit,
                brand=brand_name or "Custom",
            )
            if isinstance(created, dict) and created.get("id"):
                food_id = created["id"]
                default_var = created.get("default_variant") or {}
                if default_var.get("id"):
                    variant_id = default_var["id"]
        except Exception:
            pass

    sparky_res = client.post_food_entry(
        api_key=api_key,
        food_name=food_name,
        calories=calories,
        protein=protein,
        carbs=carbs,
        fat=fat,
        entry_date=entry_date,
        meal_type=meal_type,
        quantity=quantity,
        unit=unit,
        food_id=food_id,
        variant_id=variant_id,
        brand_name=brand_name,
    )

    # Update Flamingo activity log & XP
    from .services.gamification import process_log

    occurred_at = timezone.make_aware(
        timezone.datetime.combine(target_date, timezone.datetime.min.time())
    )
    day_log = RawActivityLog.objects.filter(
        user=request.user,
        source=Provider.SPARKYFITNESS,
        event_type="nutrition",
        occurred_at=occurred_at,
    ).first()

    sparky_entry_id = sparky_res.get("id") if (isinstance(sparky_res, dict) and sparky_res.get("id")) else None
    entry_uuid = sparky_entry_id or f"fe-{uuid.uuid4().hex[:10]}"

    current_entries.append({
        "id": entry_uuid,
        "sparky_id": sparky_entry_id,
        "name": food_name,
        "food_name": food_name,
        "calories": calories,
        "protein": protein,
        "carbs": carbs,
        "fat": fat,
        "quantity": quantity,
        "unit": unit,
        "serving": unit,
        "meal_type": str(meal_type).capitalize(),
        "brand_name": brand_name,
        "brand": brand_name,
        "food_id": food_id,
        "variant_id": variant_id,
        "base_calories": serving_cal,
        "base_protein": serving_pro,
        "base_carbs": serving_carb,
        "base_fat": serving_fat,
    })

    tot_cal = sum(float(e.get("calories", 0)) for e in current_entries)
    tot_pro = sum(float(e.get("protein", 0)) for e in current_entries)
    tot_carb = sum(float(e.get("carbs", 0)) for e in current_entries)
    tot_fat = sum(float(e.get("fat", 0)) for e in current_entries)

    # Ensure Sparky goals are pulled and attached to day_log
    sparky_goals = client.get_goals_by_date(api_key, entry_date) if api_key else {}
    cal_goal = sparky_goals.get("calories") or (day_log.payload.get("calorie_goal") if day_log and day_log.payload else 2000.0)
    pro_goal = sparky_goals.get("protein") or (day_log.payload.get("protein_goal") if day_log and day_log.payload else 150.0)

    payload = {
        "date": entry_date,
        "entry_date": entry_date,
        "calories": tot_cal,
        "protein": tot_pro,
        "carbs": tot_carb,
        "fat": tot_fat,
        "food_entries": current_entries,
        "calorie_goal": float(cal_goal),
        "protein_goal": float(pro_goal),
        "goals": {"calories": float(cal_goal), "protein": float(pro_goal)},
    }

    if not day_log:
        day_log = RawActivityLog(
            user=request.user,
            source=Provider.SPARKYFITNESS,
            event_type="nutrition",
            occurred_at=occurred_at,
        )
    day_log.payload = payload
    day_log.save()

    xp_awarded = process_log(day_log)
    xp_amount = sum(getattr(x, "amount", 0) for x in xp_awarded) if isinstance(xp_awarded, list) else int(xp_awarded or 0)

    return JsonResponse({
        "success": True,
        "food_name": food_name,
        "calories": calories,
        "protein": protein,
        "entry_date": entry_date,
        "xp_awarded": xp_amount,
        "sparky_response": sparky_res,
        "entry_id": entry_uuid,
    })


def _recalc_and_save_day_log(day_log, entries, date_str, api_key, client):
    from .services.gamification import process_log

    tot_cal = sum(float(e.get("calories", 0) or 0) for e in entries)
    tot_pro = sum(float(e.get("protein", 0) or 0) for e in entries)
    tot_carb = sum(float(e.get("carbs", 0) or 0) for e in entries)
    tot_fat = sum(float(e.get("fat", 0) or 0) for e in entries)

    sparky_goals = client.get_goals_by_date(api_key, date_str) if api_key else {}
    cal_goal = sparky_goals.get("calories") or (day_log.payload.get("calorie_goal") if day_log and day_log.payload else 2000.0)
    pro_goal = sparky_goals.get("protein") or (day_log.payload.get("protein_goal") if day_log and day_log.payload else 150.0)

    payload = {
        "date": date_str,
        "entry_date": date_str,
        "calories": tot_cal,
        "protein": tot_pro,
        "carbs": tot_carb,
        "fat": tot_fat,
        "food_entries": entries,
        "calorie_goal": float(cal_goal),
        "protein_goal": float(pro_goal),
        "goals": {"calories": float(cal_goal), "protein": float(pro_goal)},
    }
    day_log.payload = payload
    day_log.save()
    process_log(day_log)


@login_required
@require_POST
def nutrition_entry_update(request):
    """POST /api/v1/nutrition/entries/update/
    Update or move a food entry in the user's day log and SparkyFitness.
    """
    try:
        data = json.loads(request.body or b"{}")
    except Exception:
        data = {}

    entry_id = str(data.get("entry_id") or "").strip()
    date_str = str(data.get("date") or data.get("entry_date") or "").strip()
    new_date_str = str(data.get("new_date") or date_str).strip()

    if not date_str:
        date_str = timezone.localdate().isoformat()
    if not new_date_str:
        new_date_str = date_str

    try:
        target_date = datetime.date.fromisoformat(date_str)
    except Exception:
        target_date = timezone.localdate()
        date_str = target_date.isoformat()

    try:
        new_target_date = datetime.date.fromisoformat(new_date_str)
    except Exception:
        new_target_date = target_date
        new_date_str = new_target_date.isoformat()

    occurred_at = timezone.make_aware(
        timezone.datetime.combine(target_date, timezone.datetime.min.time())
    )
    day_log = RawActivityLog.objects.filter(
        user=request.user,
        source=Provider.SPARKYFITNESS,
        event_type="nutrition",
        occurred_at=occurred_at,
    ).first()

    if not day_log or not day_log.payload:
        return JsonResponse({"error": "No activity log found for this date"}, status=404)

    entries = day_log.payload.get("food_entries") or []
    match_idx = -1
    for idx, e in enumerate(entries):
        e_id = str(e.get("id") or e.get("sparky_id") or f"entry-{idx}")
        if e_id == entry_id or (entry_id.isdigit() and int(entry_id) == idx):
            match_idx = idx
            break

    if match_idx == -1 and entries:
        fname = data.get("food_name") or data.get("name")
        for idx, e in enumerate(entries):
            if e.get("food_name") == fname or e.get("name") == fname:
                match_idx = idx
                break

    if match_idx == -1:
        return JsonResponse({"error": "Food entry not found in day log"}, status=404)

    old_entry = entries[match_idx]
    sparky_id = old_entry.get("sparky_id") or (old_entry.get("id") if (isinstance(old_entry.get("id"), str) and len(old_entry.get("id")) > 20) else None)

    # Calculate updated numbers
    quantity = float(data.get("quantity") or old_entry.get("quantity") or 1.0)
    food_name = str(data.get("food_name") or data.get("name") or old_entry.get("food_name") or old_entry.get("name") or "Food")
    meal_type = str(data.get("meal_type") or old_entry.get("meal_type") or "Lunch").capitalize()
    unit = str(data.get("unit") or data.get("serving") or old_entry.get("unit") or old_entry.get("serving") or "serving")

    old_qty = max(float(old_entry.get("quantity") or 1), 0.01)
    base_cal = float(data.get("base_calories") if data.get("base_calories") is not None else (old_entry.get("base_calories") if old_entry.get("base_calories") is not None else (float(old_entry.get("calories") or 0) / old_qty)))
    base_pro = float(data.get("base_protein") if data.get("base_protein") is not None else (old_entry.get("base_protein") if old_entry.get("base_protein") is not None else (float(old_entry.get("protein") or 0) / old_qty)))
    base_carb = float(data.get("base_carbs") if data.get("base_carbs") is not None else (old_entry.get("base_carbs") if old_entry.get("base_carbs") is not None else (float(old_entry.get("carbs") or 0) / old_qty)))
    base_fat = float(data.get("base_fat") if data.get("base_fat") is not None else (old_entry.get("base_fat") if old_entry.get("base_fat") is not None else (float(old_entry.get("fat") or 0) / old_qty)))

    if "calories" in data and "base_calories" not in data:
        calories = float(data["calories"])
    else:
        calories = round(base_cal * quantity, 1)

    if "protein" in data and "base_protein" not in data:
        protein = float(data["protein"])
    else:
        protein = round(base_pro * quantity, 1)

    if "carbs" in data and "base_carbs" not in data:
        carbs = float(data["carbs"])
    else:
        carbs = round(base_carb * quantity, 1)

    if "fat" in data and "base_fat" not in data:
        fat = float(data["fat"])
    else:
        fat = round(base_fat * quantity, 1)

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    api_key = (sparky.credentials.get("api_key") if sparky else None) or ""

    from .services.sparky_client import SparkyFitnessClient
    client = SparkyFitnessClient()

    new_sparky_id = sparky_id
    if api_key:
        if sparky_id:
            try:
                client.delete_food_entry(api_key, sparky_id)
            except Exception:
                pass
        post_res = client.post_food_entry(
            api_key=api_key,
            food_name=food_name,
            calories=calories,
            protein=protein,
            carbs=carbs,
            fat=fat,
            entry_date=new_date_str,
            meal_type=meal_type,
            quantity=quantity,
            unit=unit,
            food_id=old_entry.get("food_id"),
            variant_id=old_entry.get("variant_id"),
            brand_name=old_entry.get("brand_name") or old_entry.get("brand") or "",
        )
        if isinstance(post_res, dict) and post_res.get("id"):
            new_sparky_id = post_res["id"]

    updated_entry = {
        "id": new_sparky_id or old_entry.get("id") or f"fe-{uuid.uuid4().hex[:10]}",
        "sparky_id": new_sparky_id,
        "name": food_name,
        "food_name": food_name,
        "calories": calories,
        "protein": protein,
        "carbs": carbs,
        "fat": fat,
        "quantity": quantity,
        "unit": unit,
        "serving": unit,
        "meal_type": meal_type,
        "brand_name": old_entry.get("brand_name") or old_entry.get("brand") or "",
        "brand": old_entry.get("brand_name") or old_entry.get("brand") or "",
        "food_id": old_entry.get("food_id"),
        "variant_id": old_entry.get("variant_id"),
        "base_calories": base_cal,
        "base_protein": base_pro,
        "base_carbs": base_carb,
        "base_fat": base_fat,
    }

    if new_date_str != date_str:
        entries.pop(match_idx)
        _recalc_and_save_day_log(day_log, entries, date_str, api_key, client)

        new_occurred_at = timezone.make_aware(
            timezone.datetime.combine(new_target_date, timezone.datetime.min.time())
        )
        new_day_log = RawActivityLog.objects.filter(
            user=request.user,
            source=Provider.SPARKYFITNESS,
            event_type="nutrition",
            occurred_at=new_occurred_at,
        ).first()
        if not new_day_log:
            new_day_log = RawActivityLog(
                user=request.user,
                source=Provider.SPARKYFITNESS,
                event_type="nutrition",
                occurred_at=new_occurred_at,
            )
        new_entries = (new_day_log.payload.get("food_entries") if new_day_log.payload else []) or []
        new_entries.append(updated_entry)
        _recalc_and_save_day_log(new_day_log, new_entries, new_date_str, api_key, client)
    else:
        entries[match_idx] = updated_entry
        _recalc_and_save_day_log(day_log, entries, date_str, api_key, client)

    return JsonResponse({
        "success": True,
        "message": "Food entry updated successfully",
        "entry": updated_entry,
        "date": new_date_str,
    })


@login_required
@require_POST
def nutrition_entry_delete(request):
    """POST /api/v1/nutrition/entries/delete/ - Delete an entry from a day's log."""
    try:
        data = json.loads(request.body or b"{}")
    except Exception:
        data = {}

    entry_id = str(data.get("entry_id") or "").strip()
    date_str = str(data.get("date") or data.get("entry_date") or "").strip()
    if not date_str:
        date_str = timezone.localdate().isoformat()

    try:
        target_date = datetime.date.fromisoformat(date_str)
    except Exception:
        target_date = timezone.localdate()
        date_str = target_date.isoformat()

    occurred_at = timezone.make_aware(
        timezone.datetime.combine(target_date, timezone.datetime.min.time())
    )
    day_log = RawActivityLog.objects.filter(
        user=request.user,
        source=Provider.SPARKYFITNESS,
        event_type="nutrition",
        occurred_at=occurred_at,
    ).first()

    if not day_log or not day_log.payload:
        return JsonResponse({"error": "No activity log found for this date"}, status=404)

    entries = day_log.payload.get("food_entries") or []
    match_idx = -1
    for idx, e in enumerate(entries):
        e_id = str(e.get("id") or e.get("sparky_id") or f"entry-{idx}")
        if e_id == entry_id or (entry_id.isdigit() and int(entry_id) == idx):
            match_idx = idx
            break

    if match_idx == -1 and entries:
        fname = data.get("food_name") or data.get("name")
        for idx, e in enumerate(entries):
            if e.get("food_name") == fname or e.get("name") == fname:
                match_idx = idx
                break

    if match_idx == -1:
        return JsonResponse({"error": "Food entry not found in day log"}, status=404)

    deleted_entry = entries.pop(match_idx)
    sparky_id = deleted_entry.get("sparky_id") or (deleted_entry.get("id") if (isinstance(deleted_entry.get("id"), str) and len(deleted_entry.get("id")) > 20) else None)

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    api_key = (sparky.credentials.get("api_key") if sparky else None) or ""

    from .services.sparky_client import SparkyFitnessClient
    client = SparkyFitnessClient()
    if api_key and sparky_id:
        try:
            client.delete_food_entry(api_key, sparky_id)
        except Exception:
            pass

    _recalc_and_save_day_log(day_log, entries, date_str, api_key, client)

    return JsonResponse({
        "success": True,
        "message": "Food entry deleted successfully",
        "date": date_str,
    })


@login_required
@require_POST
def nutrition_entry_copy(request):
    """POST /api/v1/nutrition/entries/copy/ - Copy an entry to another date/meal slot."""
    try:
        data = json.loads(request.body or b"{}")
    except Exception:
        data = {}

    entry_id = str(data.get("entry_id") or "").strip()
    source_date_str = str(data.get("source_date") or data.get("date") or "").strip()
    target_date_str = str(data.get("target_date") or timezone.localdate().isoformat()).strip()
    target_meal_type = data.get("target_meal_type")

    try:
        src_date = datetime.date.fromisoformat(source_date_str)
    except Exception:
        src_date = timezone.localdate()
        source_date_str = src_date.isoformat()

    try:
        tgt_date = datetime.date.fromisoformat(target_date_str)
    except Exception:
        tgt_date = timezone.localdate()
        target_date_str = tgt_date.isoformat()

    src_occurred = timezone.make_aware(
        timezone.datetime.combine(src_date, timezone.datetime.min.time())
    )
    src_log = RawActivityLog.objects.filter(
        user=request.user,
        source=Provider.SPARKYFITNESS,
        event_type="nutrition",
        occurred_at=src_occurred,
    ).first()

    if not src_log or not src_log.payload:
        return JsonResponse({"error": "Source log not found"}, status=404)

    entries = src_log.payload.get("food_entries") or []
    target_item = None
    for idx, e in enumerate(entries):
        e_id = str(e.get("id") or e.get("sparky_id") or f"entry-{idx}")
        if e_id == entry_id or (entry_id.isdigit() and int(entry_id) == idx):
            target_item = e
            break

    if not target_item:
        return JsonResponse({"error": "Source food entry not found"}, status=404)

    meal_type = str(target_meal_type or target_item.get("meal_type") or "Lunch").capitalize()

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    api_key = (sparky.credentials.get("api_key") if sparky else None) or ""

    from .services.sparky_client import SparkyFitnessClient
    client = SparkyFitnessClient()

    new_sparky_id = None
    if api_key:
        post_res = client.post_food_entry(
            api_key=api_key,
            food_name=target_item.get("food_name") or target_item.get("name") or "Food",
            calories=float(target_item.get("calories") or 0),
            protein=float(target_item.get("protein") or 0),
            carbs=float(target_item.get("carbs") or 0),
            fat=float(target_item.get("fat") or 0),
            entry_date=target_date_str,
            meal_type=meal_type,
            quantity=float(target_item.get("quantity") or 1),
            unit=target_item.get("unit") or target_item.get("serving") or "serving",
            food_id=target_item.get("food_id"),
            variant_id=target_item.get("variant_id"),
            brand_name=target_item.get("brand_name") or target_item.get("brand") or "",
        )
        if isinstance(post_res, dict) and post_res.get("id"):
            new_sparky_id = post_res["id"]

    new_entry = dict(target_item)
    new_entry["id"] = new_sparky_id or f"fe-{uuid.uuid4().hex[:10]}"
    new_entry["sparky_id"] = new_sparky_id
    new_entry["meal_type"] = meal_type

    tgt_occurred = timezone.make_aware(
        timezone.datetime.combine(tgt_date, timezone.datetime.min.time())
    )
    tgt_log = RawActivityLog.objects.filter(
        user=request.user,
        source=Provider.SPARKYFITNESS,
        event_type="nutrition",
        occurred_at=tgt_occurred,
    ).first()
    if not tgt_log:
        tgt_log = RawActivityLog(
            user=request.user,
            source=Provider.SPARKYFITNESS,
            event_type="nutrition",
            occurred_at=tgt_occurred,
        )

    tgt_entries = (tgt_log.payload.get("food_entries") if tgt_log.payload else []) or []
    tgt_entries.append(new_entry)
    _recalc_and_save_day_log(tgt_log, tgt_entries, target_date_str, api_key, client)

    return JsonResponse({
        "success": True,
        "message": f"Copied to {target_date_str} ({meal_type})",
        "target_date": target_date_str,
        "entry": new_entry,
    })


@login_required
def nutrition_snaps_list(request):
    """GET /api/v1/nutrition/snaps/ - List pending food snap drafts."""
    drafts = FoodSnapDraft.objects.filter(
        user=request.user,
        status__in=[FoodSnapDraft.Status.PENDING, FoodSnapDraft.Status.ANALYZED],
    ).order_by("-created_at")

    results = []
    for d in drafts:
        results.append({
            "id": d.id,
            "note": d.note,
            "meal_type": d.meal_type,
            "entry_date": d.entry_date.isoformat(),
            "status": d.status,
            "has_image": bool(d.image or d.image_base64),
            "image_url": d.image.url if d.image else (d.image_base64 if d.image_base64 else None),
            "extracted_items": d.extracted_items,
            "created_at": d.created_at.isoformat(),
        })
    return JsonResponse({"success": True, "drafts": results, "count": len(results)})


@login_required
@require_POST
def nutrition_snap_upload(request):
    """POST /api/v1/nutrition/snaps/ - Upload meal photo + note for queue/processing."""
    note = request.POST.get("note", "")
    meal_type = request.POST.get("meal_type", "Lunch")
    image_file = request.FILES.get("image")
    image_b64 = request.POST.get("image_base64", "")

    if not note and not image_file and not image_b64:
        try:
            data = json.loads(request.body or b"{}")
            note = data.get("note", "")
            meal_type = data.get("meal_type", "Lunch")
            image_b64 = data.get("image_base64", "")
        except Exception:
            pass

    draft = FoodSnapDraft.objects.create(
        user=request.user,
        note=note,
        meal_type=meal_type,
        image=image_file if image_file else None,
        image_base64=image_b64 if not image_file else "",
        status=FoodSnapDraft.Status.PENDING,
    )

    # Run smart matching
    from .services.nutrition_matcher import NutritionMatchingService

    matcher = NutritionMatchingService(request.user)
    matched = matcher.match_note_and_image(
        note=draft.note,
        image_base64=draft.image_base64 or ("present" if draft.image else None),
        meal_type=draft.meal_type,
    )
    draft.extracted_items = matched
    draft.status = FoodSnapDraft.Status.ANALYZED
    draft.save(update_fields=["extracted_items", "status"])

    return JsonResponse({
        "success": True,
        "draft": {
            "id": draft.id,
            "note": draft.note,
            "meal_type": draft.meal_type,
            "status": draft.status,
            "extracted_items": draft.extracted_items,
            "image_url": draft.image.url if draft.image else (draft.image_base64 if draft.image_base64 else None),
        },
    })


@login_required
@require_POST
def nutrition_snap_commit(request, draft_id):
    """POST /api/v1/nutrition/snaps/<int:draft_id>/commit/ - Commit items from draft to Sparky & XP."""
    draft = FoodSnapDraft.objects.filter(user=request.user, id=draft_id).first()
    if not draft:
        return _json_error("Draft not found", 404)

    try:
        data = json.loads(request.body or b"{}")
    except Exception:
        data = {}

    items = data.get("items") or draft.extracted_items or []
    meal_type = data.get("meal_type") or draft.meal_type or "Lunch"
    entry_date = data.get("entry_date") or data.get("date") or (draft.entry_date.isoformat() if getattr(draft, "entry_date", None) else timezone.localdate().isoformat())
    try:
        target_date = datetime.date.fromisoformat(entry_date)
    except Exception:
        target_date = timezone.localdate()
        entry_date = target_date.isoformat()

    sparky = UserIntegration.objects.filter(
        user=request.user, provider=Provider.SPARKYFITNESS, is_active=True
    ).first()
    api_key = (sparky.credentials.get("api_key") if sparky else None) or ""

    from .services.sparky_client import SparkyFitnessClient
    from .services.gamification import process_log

    client = SparkyFitnessClient()
    for item in items:
        f_id = item.get("food_id")
        v_id = item.get("variant_id")
        if not f_id and api_key:
            try:
                qty = max(float(item.get("quantity") or 1.0), 0.01)
                created = client.create_custom_food(
                    api_key=api_key,
                    name=item.get("name") or "Logged Food",
                    calories=round(float(item.get("calories") or 0) / qty, 1),
                    protein=round(float(item.get("protein") or 0) / qty, 1),
                    carbs=round(float(item.get("carbs") or 0) / qty, 1),
                    fat=round(float(item.get("fat") or 0) / qty, 1),
                    serving=str(item.get("unit") or "serving"),
                    brand=item.get("brand") or "Sparky AI",
                )
                if isinstance(created, dict) and created.get("id"):
                    f_id = created["id"]
                    default_var = created.get("default_variant") or {}
                    if default_var.get("id"):
                        v_id = default_var["id"]
            except Exception:
                pass

        s_res = client.post_food_entry(
            api_key=api_key,
            food_name=item.get("name") or "Logged Food",
            calories=float(item.get("calories") or 0),
            protein=float(item.get("protein") or 0),
            carbs=float(item.get("carbs") or 0),
            fat=float(item.get("fat") or 0),
            entry_date=entry_date,
            meal_type=meal_type,
            quantity=float(item.get("quantity") or 1),
            unit=str(item.get("unit") or "serving"),
            food_id=f_id,
            variant_id=v_id,
            brand_name=item.get("brand") or "",
        )
        s_id = s_res.get("id") if (isinstance(s_res, dict) and s_res.get("id")) else None
        item["_sparky_id"] = s_id

    # Record in Flamingo activity log
    occurred_at = timezone.make_aware(
        timezone.datetime.combine(target_date, timezone.datetime.min.time())
    )
    day_log = RawActivityLog.objects.filter(
        user=request.user,
        source=Provider.SPARKYFITNESS,
        event_type="nutrition",
        occurred_at=occurred_at,
    ).first()

    current_entries = (day_log.payload.get("food_entries") if day_log else []) or []
    for item in items:
        qty = float(item.get("quantity") or 1)
        s_id = item.get("_sparky_id")
        current_entries.append({
            "id": s_id or f"fe-{uuid.uuid4().hex[:10]}",
            "sparky_id": s_id,
            "name": item.get("name"),
            "food_name": item.get("name"),
            "calories": float(item.get("calories", 0) or 0),
            "protein": float(item.get("protein", 0) or 0),
            "carbs": float(item.get("carbs", 0) or 0),
            "fat": float(item.get("fat", 0) or 0),
            "quantity": qty,
            "unit": item.get("unit", "serving"),
            "serving": item.get("unit", "serving"),
            "meal_type": str(meal_type).capitalize(),
            "food_id": item.get("food_id"),
            "variant_id": item.get("variant_id"),
            "brand": item.get("brand") or "",
            "brand_name": item.get("brand") or "",
            "base_calories": float(item.get("calories", 0) or 0) / max(qty, 0.01),
            "base_protein": float(item.get("protein", 0) or 0) / max(qty, 0.01),
            "base_carbs": float(item.get("carbs", 0) or 0) / max(qty, 0.01),
            "base_fat": float(item.get("fat", 0) or 0) / max(qty, 0.01),
        })

    tot_cal = sum(float(e.get("calories", 0)) for e in current_entries)
    tot_pro = sum(float(e.get("protein", 0)) for e in current_entries)
    tot_carb = sum(float(e.get("carbs", 0)) for e in current_entries)
    tot_fat = sum(float(e.get("fat", 0)) for e in current_entries)

    # Ensure Sparky goals are pulled and attached to day_log
    sparky_goals = client.get_goals_by_date(api_key, entry_date) if api_key else {}
    cal_goal = sparky_goals.get("calories") or (day_log.payload.get("calorie_goal") if day_log and day_log.payload else 2000.0)
    pro_goal = sparky_goals.get("protein") or (day_log.payload.get("protein_goal") if day_log and day_log.payload else 150.0)

    payload = {
        "date": entry_date,
        "entry_date": entry_date,
        "calories": tot_cal,
        "protein": tot_pro,
        "carbs": tot_carb,
        "fat": tot_fat,
        "food_entries": current_entries,
        "calorie_goal": float(cal_goal),
        "protein_goal": float(pro_goal),
        "goals": {"calories": float(cal_goal), "protein": float(pro_goal)},
    }

    if not day_log:
        day_log = RawActivityLog(
            user=request.user,
            source=Provider.SPARKYFITNESS,
            event_type="nutrition",
            occurred_at=occurred_at,
        )
    day_log.payload = payload
    day_log.save()

    xp_awarded = process_log(day_log)
    xp_amount = sum(getattr(x, "amount", 0) for x in xp_awarded) if isinstance(xp_awarded, list) else int(xp_awarded or 0)

    draft.status = FoodSnapDraft.Status.LOGGED
    draft.extracted_items = items
    draft.save(update_fields=["status", "extracted_items"])

    return JsonResponse({
        "success": True,
        "logged_items_count": len(items),
        "entry_date": entry_date,
        "xp_awarded": xp_amount,
        "draft_id": draft.id,
    })


@login_required
@require_POST
def nutrition_snap_delete(request, draft_id):
    """POST /api/v1/nutrition/snaps/<int:draft_id>/delete/ - Delete a draft."""
    draft = FoodSnapDraft.objects.filter(user=request.user, id=draft_id).first()
    if not draft:
        return _json_error("Draft not found", 404)
    draft.delete()
    return JsonResponse({"success": True, "deleted_id": draft_id})


@login_required
def marketplace_state_view(request):
    """GET /marketplace/state - Marketplace listings, inventory, and wallet."""
    from .services.marketplace import get_marketplace_state

    category = request.GET.get("category")
    rarity = request.GET.get("rarity")
    sort = request.GET.get("sort")
    state = get_marketplace_state(
        request.user, category=category, rarity=rarity, sort=sort
    )
    return JsonResponse(state)


@login_required
@require_POST
def marketplace_list_view(request):
    """POST /marketplace/list - List an unequipped gear item for sale."""
    from .services.marketplace import list_gear_item

    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    user_gear_id = data.get("user_gear_id")
    price_type = data.get("price_type", "tokens")
    price_amount = data.get("price_amount", 10)

    if not user_gear_id:
        return _json_error("Missing 'user_gear_id'", 400)

    listing, err = list_gear_item(
        request.user, user_gear_id, price_type, price_amount
    )
    if err:
        return _json_error(err, 400)

    return JsonResponse(
        {
            "success": True,
            "listing_id": listing.id,
            "message": f"Successfully listed {listing.gear_item.name} for {listing.price_amount} {listing.price_type}!",
        }
    )


@login_required
@require_POST
def marketplace_buy_view(request):
    """POST /marketplace/buy - Purchase a gear listing."""
    from .services.marketplace import buy_marketplace_item

    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    listing_id = data.get("listing_id")
    if not listing_id:
        return _json_error("Missing 'listing_id'", 400)

    result, err = buy_marketplace_item(request.user, listing_id)
    if err:
        return _json_error(err, 400)

    return JsonResponse(result)


@login_required
@require_POST
def marketplace_cancel_view(request):
    """POST /marketplace/cancel - Cancel an active marketplace listing."""
    from .services.marketplace import cancel_marketplace_listing

    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    listing_id = data.get("listing_id")
    if not listing_id:
        return _json_error("Missing 'listing_id'", 400)

    listing, err = cancel_marketplace_listing(request.user, listing_id)
    if err:
        return _json_error(err, 400)

    return JsonResponse(
        {"success": True, "message": "Listing cancelled successfully"}
    )


@csrf_exempt
@login_required
def notification_preferences_view(request):
    """GET/POST /notifications/preferences/ - View or update notification toggles."""
    from .services.smart_reminders import (
        get_user_notification_preferences,
        update_user_notification_preferences,
    )

    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return _json_error("Invalid JSON body", 400)
        updated = update_user_notification_preferences(request.user, body)
        return JsonResponse({"success": True, "preferences": updated})

    prefs = get_user_notification_preferences(request.user)
    return JsonResponse({"success": True, "preferences": prefs})


@csrf_exempt
@login_required
@require_POST
def notification_register_device(request):
    """POST /notifications/register/ - Register or refresh a push device token."""
    from .services.smart_reminders import register_push_device

    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _json_error("Invalid JSON body", 400)

    token = data.get("token")
    if not token or not str(token).strip():
        return _json_error("Missing 'token'", 400)

    platform = data.get("platform", "android")
    device_name = data.get("device_name", "")

    device = register_push_device(
        request.user, token.strip(), platform=platform, device_name=device_name
    )
    return JsonResponse(
        {
            "success": True,
            "device_id": device.id,
            "platform": device.platform,
            "is_active": device.is_active,
        }
    )


@login_required
def notification_intelligent_prompt(request):
    """GET /notifications/intelligent-prompt/ - Evaluate and return smart habit prompts."""
    from .services.smart_reminders import evaluate_smart_reminders

    prompts = evaluate_smart_reminders(request.user)
    return JsonResponse(
        {
            "success": True,
            "prompts": prompts,
            "count": len(prompts),
        }
    )


@login_required
def notification_history_view(request):
    """GET /notifications/history/ - List recent notifications sent to user."""
    from .models import PushNotificationLog

    logs = PushNotificationLog.objects.filter(user=request.user).order_by(
        "-sent_at"
    )[:25]
    items = []
    for l in logs:
        items.append({
            "id": l.id,
            "category": l.category,
            "title": l.title,
            "body": l.body,
            "data": l.data,
            "sent_at": l.sent_at.isoformat(),
            "is_read": l.is_read,
        })
    return JsonResponse({"success": True, "notifications": items})


@csrf_exempt
@login_required
@require_POST
def notification_test_send(request):
    """POST /notifications/test/ - Dispatch a test push notification to user."""
    from .services.smart_reminders import dispatch_push_notification

    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        data = {}

    category = data.get("category", "general")
    title = data.get("title", "🦩 Flamingo Fitness Test")
    body = data.get(
        "body", "Push notifications are working! Get ready to level up your habits."
    )

    log_entry, err = dispatch_push_notification(
        request.user, category, title, body, data=data, force=True
    )
    if err:
        return _json_error(err, 400)

    return JsonResponse(
        {
            "success": True,
            "notification_id": log_entry.id,
            "category": log_entry.category,
            "title": log_entry.title,
            "sent_at": log_entry.sent_at.isoformat(),
        }
    )


# -------------------------------------------------------------------------
# Bounties & 1v1 Fitness Duels (Roadmap N8)
# -------------------------------------------------------------------------

@login_required
def bounties_state_view(request):
    """GET /bounties/state/ - Return full bounty and duel state as JSON."""
    from .services.bounties import get_bounties_state
    state = get_bounties_state(request.user)
    return JsonResponse({"success": True, "data": state})


@csrf_exempt
@login_required
@require_POST
def create_bounty_view(request):
    """POST /bounties/create/ - Create a solo contract, open bounty, or 1v1 duel."""
    from .services.bounties import create_bounty
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _json_error("Invalid JSON format", 400)

    bounty_type = data.get("bounty_type", "open")
    target_type = data.get("target_type", "steps")
    target_value = data.get("target_value", 0)
    duration_hours = data.get("duration_hours", 24)
    wager_tokens = data.get("wager_tokens", 0)
    wager_scraps = data.get("wager_scraps", 0)
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    opponent_username = str(data.get("opponent_username") or "").strip()
    flock_id = data.get("flock_id")

    ok, res = create_bounty(
        user=request.user,
        bounty_type=bounty_type,
        target_type=target_type,
        target_value=target_value,
        duration_hours=duration_hours,
        wager_tokens=wager_tokens,
        wager_scraps=wager_scraps,
        title=title,
        description=description,
        opponent_username=opponent_username,
        flock_id=flock_id,
    )
    if not ok:
        return _json_error(res.get("error", "Failed to create bounty"), res.get("status", 400))

    return JsonResponse({"success": True, "bounty": res})


@csrf_exempt
@login_required
@require_POST
def accept_bounty_view(request, bounty_id):
    """POST /bounties/<id>/accept/ - Accept an open bounty or 1v1 duel."""
    from .services.bounties import accept_bounty
    ok, res = accept_bounty(bounty_id=bounty_id, user=request.user)
    if not ok:
        return _json_error(res.get("error", "Failed to accept bounty"), res.get("status", 400))

    return JsonResponse({"success": True, "bounty": res})


@csrf_exempt
@login_required
@require_POST
def cancel_bounty_view(request, bounty_id):
    """POST /bounties/<id>/cancel/ - Cancel an unaccepted bounty and refund escrow."""
    from .services.bounties import cancel_bounty
    ok, res = cancel_bounty(bounty_id=bounty_id, user=request.user)
    if not ok:
        return _json_error(res.get("error", "Failed to cancel bounty"), res.get("status", 400))

    return JsonResponse({"success": True, "message": res.get("message")})


@csrf_exempt
@login_required
@require_POST
def claim_bounty_view(request, bounty_id):
    """POST /bounties/<id>/claim/ - Claim rewards from completed bounty/duel."""
    from .services.bounties import claim_bounty_reward
    ok, res = claim_bounty_reward(bounty_id=bounty_id, user=request.user)
    if not ok:
        return _json_error(res.get("error", "Failed to claim reward"), res.get("status", 400))

    return JsonResponse({"success": True, "reward": res})





