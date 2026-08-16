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
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import LiftosaurLinkForm, SignupForm, SparkyLinkForm, ThemeForm
from .models import (
    BossConfig,
    CampaignBoss,
    CampaignProgress,
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
    send_friend_request,
    set_defense as combat_set_defense,
    social_state,
    wallet_dump,
)


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
def endurance_state(request):
    """GET /api/v1/endurance/

    Returns today's endurance summary, the full exercise history, the
    endurance skill-tree state, and whether SparkyFitness is linked.
    """
    from .services import summarize_endurance
    from .models import SkillTree

    logs = (
        RawActivityLog.objects.filter(user=request.user, event_type="endurance")
        .order_by("-occurred_at")
    )
    history = [summarize_endurance(log) for log in logs]

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

    logs = (
        RawActivityLog.objects.filter(user=request.user, event_type="strength")
        .order_by("-occurred_at")
    )
    history = [summarize_strength(log) for log in logs]

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

    logs = (
        RawActivityLog.objects.filter(user=user, event_type="sleep")
        .order_by("-occurred_at")
    )
    history = [summarize_sleep(log) for log in logs]

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
    from .services import base_damage_for, total_gear_multiplier

    prog = CampaignProgress.objects.filter(
        user=request.user, campaign=campaign
    ).select_related("boss").first()
    boss = CampaignBoss.objects.filter(campaign=campaign, is_active=True).order_by("sort_order").first()
    profile_obj = combat_profile(request.user)
    base = base_damage_for(campaign, request.user)
    gear_mult = total_gear_multiplier(profile_obj, request.user, campaign)
    ref = (prog.boss if prog and prog.boss else boss)
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
        "gear_multiplier": round(gear_mult, 2),
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
        })
    return JsonResponse({"wallet": wallet_dump(profile_obj), "packs": packs, "owned": owned})


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
        } if ug else None
    owned = [
        {
            "id": ug.pk, "slug": ug.gear_def.slug, "name": ug.gear_def.name,
            "slot": ug.gear_def.slot or "accessory", "rarity": ug.rarity, "icon": ug.gear_def.icon,
            "effect_type": ug.gear_def.effect_type,
            "effect_domain": ug.gear_def.effect_domain,
            "effect_value": ug.gear_def.effect_value,
            "equipped": bool(ug.equipped_slot),
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
            "resources": wallet_dump(profile_obj),
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