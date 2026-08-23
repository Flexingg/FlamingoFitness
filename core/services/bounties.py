"""Interactive Fitness Bounty Board & 1v1 Duels Service (Roadmap item N8).

Provides:
- Solo fitness contracts (self-commitments with token multipliers)
- Open community bounty board (stake tokens/scraps in escrow for anyone to challenge)
- Direct 1v1 Friend/Flock duels with real-time progress comparisons
- Automated log verification across all 5 habit modalities
- Escrow locking, bonus prize payouts, and Celery expiration tasks
"""

from datetime import timedelta
import logging
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import (
    Bounty,
    BountyParticipant,
    Flock,
    Modality,
    PlayerProfile,
    PushNotificationLog,
    RawActivityLog,
    User,
    XPLedger,
)
from core.services.combat import profile as combat_profile
from core.services.smart_reminders import dispatch_push_notification

logger = logging.getLogger(__name__)

TARGET_TYPE_CONFIG = {
    Bounty.TargetType.STEPS: {
        "label": "Steps",
        "unit": "steps",
        "icon": "fa-shoe-prints",
        "modality": Modality.ENDURANCE,
        "default_val": 10000,
        "min": 1000,
        "max": 50000,
    },
    Bounty.TargetType.CARDIO_MINUTES: {
        "label": "Cardio Duration",
        "unit": "mins",
        "icon": "fa-person-running",
        "modality": Modality.ENDURANCE,
        "default_val": 30,
        "min": 10,
        "max": 180,
    },
    Bounty.TargetType.STRENGTH_VOLUME: {
        "label": "Strength Volume",
        "unit": "lbs",
        "icon": "fa-dumbbell",
        "modality": Modality.STRENGTH,
        "default_val": 15000,
        "min": 1000,
        "max": 100000,
    },
    Bounty.TargetType.WATER_ML: {
        "label": "Hydration Target",
        "unit": "ml",
        "icon": "fa-droplet",
        "modality": Modality.HYDRATION,
        "default_val": 2500,
        "min": 500,
        "max": 6000,
    },
    Bounty.TargetType.PROTEIN_G: {
        "label": "Protein Goal",
        "unit": "g",
        "icon": "fa-egg",
        "modality": Modality.NUTRITION,
        "default_val": 140,
        "min": 30,
        "max": 300,
    },
    Bounty.TargetType.CALORIES_BURNED: {
        "label": "Active Calorie Burn",
        "unit": "kcal",
        "icon": "fa-fire",
        "modality": Modality.ENDURANCE,
        "default_val": 500,
        "min": 100,
        "max": 3000,
    },
    Bounty.TargetType.WORKOUT_COUNT: {
        "label": "Workouts Completed",
        "unit": "sessions",
        "icon": "fa-medal",
        "modality": Modality.STRENGTH,
        "default_val": 1,
        "min": 1,
        "max": 5,
    },
    Bounty.TargetType.SLEEP_HOURS: {
        "label": "Sleep Duration",
        "unit": "hrs",
        "icon": "fa-moon",
        "modality": Modality.RECOVERY,
        "default_val": 8.0,
        "min": 5.0,
        "max": 12.0,
    },
}


def _error_res(msg, code=400):
    return False, {"error": msg, "status": code}


def _success_res(data):
    return True, data


def ensure_daily_system_bounties(now=None):
    """Seed or replenish daily system contracts on the Open Board."""
    now = now or timezone.now()
    system_user, _ = get_user_model().objects.get_or_create(
        username="SirFluffington",
        defaults={"email": "fluffington@flamingofitness.cc", "first_name": "Sir Fluffington"},
    )
    combat_profile(system_user)

    active_count = Bounty.objects.filter(
        creator=system_user,
        bounty_type=Bounty.BountyType.OPEN,
        status__in=[Bounty.Status.OPEN, Bounty.Status.ACTIVE],
        created_at__gte=now - timedelta(days=1),
    ).count()

    if active_count < 3:
        presets = [
            (
                "🦩 Flamingo Hydration Sprint",
                "Hydrate like a champion! Log at least 2,500ml of clean water today.",
                Bounty.TargetType.WATER_ML,
                2500,
                24,
                0,
                0,
                75,
                25,
            ),
            (
                "🏋️ Iron Nest Volume Trial",
                "Hit the gym and push heavy steel! Reach 15,000 lbs of total strength tonnage.",
                Bounty.TargetType.STRENGTH_VOLUME,
                15000,
                24,
                0,
                0,
                100,
                35,
            ),
            (
                "🏃 Lagoon Cardio Rush",
                "Get your wings flapping with 30 minutes of logged cardio or endurance work.",
                Bounty.TargetType.CARDIO_MINUTES,
                30,
                24,
                0,
                0,
                75,
                25,
            ),
            (
                "🥗 Macro Master Protein Quest",
                "Fuel muscle synthesis by crushing 140g of protein today.",
                Bounty.TargetType.PROTEIN_G,
                140,
                24,
                0,
                0,
                80,
                30,
            ),
        ]

        for title, desc, target_type, target_val, duration, w_tok, w_scrap, xp, bonus_tok in presets:
            if not Bounty.objects.filter(
                creator=system_user,
                title=title,
                created_at__gte=now - timedelta(hours=20),
            ).exists():
                Bounty.objects.create(
                    creator=system_user,
                    bounty_type=Bounty.BountyType.OPEN,
                    title=title,
                    description=desc,
                    target_type=target_type,
                    target_value=target_val,
                    duration_hours=duration,
                    wager_tokens=w_tok,
                    wager_scraps=w_scrap,
                    reward_xp=xp,
                    bonus_tokens=bonus_tok,
                    status=Bounty.Status.OPEN,
                )


def get_bounties_state(user, now=None):
    """Retrieve full bounty state partitioned into tabs for the UI."""
    now = now or timezone.now()
    ensure_daily_system_bounties(now)
    evaluate_user_bounties(user, now)

    prof = combat_profile(user)

    my_active_qs = (
        BountyParticipant.objects.filter(
            user=user,
            bounty__status__in=[Bounty.Status.ACTIVE, Bounty.Status.COMPLETED],
            payout_claimed=False,
        )
        .select_related("bounty", "bounty__creator", "bounty__opponent", "bounty__winner")
        .prefetch_related("bounty__participants", "bounty__participants__user")
        .order_by("-bounty__created_at")
    )

    active_list = []
    for part in my_active_qs:
        b = part.bounty
        time_left_sec = 0
        if b.end_time and b.end_time > now:
            time_left_sec = int((b.end_time - now).total_seconds())

        opp_part = None
        if b.bounty_type == Bounty.BountyType.DUEL:
            opp_part = b.participants.exclude(user=user).first()

        active_list.append({
            "id": b.id,
            "participant_id": part.id,
            "type": b.bounty_type,
            "title": b.title,
            "description": b.description,
            "target_type": b.target_type,
            "target_config": TARGET_TYPE_CONFIG.get(b.target_type, {}),
            "target_value": b.target_value,
            "current_value": round(part.current_value, 1),
            "progress_pct": min(100, int((part.current_value / b.target_value) * 100)) if b.target_value > 0 else 0,
            "is_completed": part.is_completed,
            "can_claim": part.is_completed and not part.payout_claimed,
            "payout_claimed": part.payout_claimed,
            "is_winner": b.winner_id == user.id,
            "wager_tokens": b.wager_tokens,
            "wager_scraps": b.wager_scraps,
            "reward_xp": b.reward_xp,
            "bonus_tokens": b.bonus_tokens,
            "total_pot_tokens": (b.wager_tokens * (2 if b.bounty_type == Bounty.BountyType.DUEL else 1)) + b.bonus_tokens,
            "time_left_seconds": time_left_sec,
            "status": b.status,
            "creator": b.creator.username,
            "is_creator": b.creator_id == user.id,
            "opponent": {
                "username": opp_part.user.username,
                "current_value": round(opp_part.current_value, 1),
                "progress_pct": min(100, int((opp_part.current_value / b.target_value) * 100)) if b.target_value > 0 else 0,
                "is_completed": opp_part.is_completed,
            } if opp_part else None,
        })

    open_qs = (
        Bounty.objects.filter(
            status=Bounty.Status.OPEN,
            bounty_type__in=[Bounty.BountyType.OPEN, Bounty.BountyType.FLOCK],
        )
        .exclude(participants__user=user)
        .select_related("creator")
        .order_by("-created_at")[:25]
    )

    open_list = []
    for b in open_qs:
        open_list.append({
            "id": b.id,
            "type": b.bounty_type,
            "title": b.title,
            "description": b.description,
            "target_type": b.target_type,
            "target_config": TARGET_TYPE_CONFIG.get(b.target_type, {}),
            "target_value": b.target_value,
            "duration_hours": b.duration_hours,
            "wager_tokens": b.wager_tokens,
            "wager_scraps": b.wager_scraps,
            "reward_xp": b.reward_xp,
            "bonus_tokens": b.bonus_tokens,
            "creator": b.creator.username,
            "is_system": b.creator.username == "SirFluffington",
            "created_at": b.created_at.isoformat(),
        })

    direct_duels_qs = (
        Bounty.objects.filter(
            bounty_type=Bounty.BountyType.DUEL,
            status=Bounty.Status.OPEN,
        )
        .filter(Q(creator=user) | Q(opponent=user))
        .select_related("creator", "opponent")
        .order_by("-created_at")
    )

    duel_list = []
    for b in direct_duels_qs:
        duel_list.append({
            "id": b.id,
            "title": b.title,
            "description": b.description,
            "target_type": b.target_type,
            "target_config": TARGET_TYPE_CONFIG.get(b.target_type, {}),
            "target_value": b.target_value,
            "duration_hours": b.duration_hours,
            "wager_tokens": b.wager_tokens,
            "wager_scraps": b.wager_scraps,
            "reward_xp": b.reward_xp,
            "bonus_tokens": b.bonus_tokens,
            "creator": b.creator.username,
            "opponent": b.opponent.username if b.opponent else "Anyone",
            "is_sender": b.creator_id == user.id,
            "is_receiver": b.opponent_id == user.id,
            "created_at": b.created_at.isoformat(),
        })

    history_qs = (
        BountyParticipant.objects.filter(
            user=user,
            payout_claimed=True,
        )
        .select_related("bounty", "bounty__winner")
        .order_by("-completed_at")[:20]
    )

    history_list = []
    for part in history_qs:
        b = part.bounty
        history_list.append({
            "id": b.id,
            "title": b.title,
            "type": b.bounty_type,
            "target_type": b.target_type,
            "target_value": b.target_value,
            "current_value": round(part.current_value, 1),
            "is_winner": b.winner_id == user.id,
            "completed_at": part.completed_at.isoformat() if part.completed_at else None,
            "reward_xp": b.reward_xp,
            "tokens_won": (b.wager_tokens * (2 if b.bounty_type == Bounty.BountyType.DUEL else 1)) + b.bonus_tokens if b.winner_id == user.id else 0,
        })

    return {
        "user_balance": {
            "tokens": prof.tokens,
            "scraps": prof.scraps,
        },
        "target_types": {k: v for k, v in TARGET_TYPE_CONFIG.items()},
        "active_bounties": active_list,
        "open_board": open_list,
        "direct_duels": duel_list,
        "history": history_list,
        "stats": {
            "total_won": Bounty.objects.filter(winner=user).count(),
            "total_completed": BountyParticipant.objects.filter(user=user, is_completed=True).count(),
        },
    }


@transaction.atomic
def create_bounty(
    user,
    bounty_type,
    target_type,
    target_value,
    duration_hours=24,
    wager_tokens=0,
    wager_scraps=0,
    title="",
    description="",
    opponent_username=None,
    flock_id=None,
    now=None,
):
    """Create a new solo contract, open board bounty, or 1v1 friend duel with escrow."""
    now = now or timezone.now()
    prof = combat_profile(user)

    wager_tokens = max(0, int(wager_tokens or 0))
    wager_scraps = max(0, int(wager_scraps or 0))
    duration_hours = max(1, min(168, int(duration_hours or 24)))
    target_value = float(target_value or 0)

    if target_type not in TARGET_TYPE_CONFIG:
        return _error_res(f"Invalid target type: {target_type}")

    cfg = TARGET_TYPE_CONFIG[target_type]
    if target_value <= 0:
        target_value = float(cfg["default_val"])

    if wager_tokens > prof.tokens:
        return _error_res(f"Insufficient tokens. You have {prof.tokens} tokens, needed {wager_tokens}.")
    if wager_scraps > prof.scraps:
        return _error_res(f"Insufficient scraps. You have {prof.scraps} scraps, needed {wager_scraps}.")

    opponent = None
    if bounty_type == Bounty.BountyType.DUEL:
        if not opponent_username:
            return _error_res("Opponent username is required for a 1v1 duel.")
        try:
            opponent = get_user_model().objects.get(username=opponent_username.strip())
        except get_user_model().DoesNotExist:
            return _error_res(f"User '{opponent_username}' not found.")
        if opponent.id == user.id:
            return _error_res("You cannot challenge yourself to a 1v1 duel.")

    flock = None
    if flock_id:
        try:
            flock = Flock.objects.get(id=flock_id)
        except Flock.DoesNotExist:
            pass

    if wager_tokens > 0:
        prof.tokens -= wager_tokens
    if wager_scraps > 0:
        prof.scraps -= wager_scraps
    prof.save(update_fields=["tokens", "scraps"])

    if not title:
        verb = "Duel" if bounty_type == Bounty.BountyType.DUEL else "Contract"
        title = f"{cfg['label']} {verb} ({int(target_value)} {cfg['unit']})"

    status = Bounty.Status.OPEN
    start_time = None
    end_time = None

    if bounty_type == Bounty.BountyType.SOLO:
        status = Bounty.Status.ACTIVE
        start_time = now
        end_time = now + timedelta(hours=duration_hours)

    bounty = Bounty.objects.create(
        creator=user,
        opponent=opponent,
        flock=flock,
        bounty_type=bounty_type,
        title=title,
        description=description or f"Complete {target_value} {cfg['unit']} of {cfg['label']} within {duration_hours}h.",
        target_type=target_type,
        target_value=target_value,
        duration_hours=duration_hours,
        wager_tokens=wager_tokens,
        wager_scraps=wager_scraps,
        reward_xp=50 + int(wager_tokens * 0.5),
        bonus_tokens=15 if bounty_type == Bounty.BountyType.SOLO else 25,
        status=status,
        start_time=start_time,
        end_time=end_time,
    )

    BountyParticipant.objects.create(
        bounty=bounty,
        user=user,
        current_value=0.0,
        joined_at=now,
    )

    if opponent and bounty_type == Bounty.BountyType.DUEL:
        dispatch_push_notification(
            opponent,
            PushNotificationLog.Category.BOUNTY,
            f"⚔️ Duel Challenge from @{user.username}!",
            f"{user.username} challenged you to a {duration_hours}h {cfg['label']} duel ({int(target_value)} {cfg['unit']}) for {wager_tokens} Tokens!",
            data={"bounty_id": bounty.id, "type": "duel_challenge"},
            now=now,
        )

    return _success_res({
        "bounty_id": bounty.id,
        "title": bounty.title,
        "status": bounty.status,
        "wager_tokens": bounty.wager_tokens,
        "wager_scraps": bounty.wager_scraps,
    })


@transaction.atomic
def accept_bounty(bounty_id, user, now=None):
    """Accept an open board bounty or direct 1v1 duel challenge."""
    now = now or timezone.now()
    prof = combat_profile(user)

    try:
        bounty = Bounty.objects.select_for_update().get(id=bounty_id)
    except Bounty.DoesNotExist:
        return _error_res("Bounty not found.", 404)

    if bounty.status != Bounty.Status.OPEN:
        return _error_res("This bounty is no longer open for acceptance.")

    if bounty.bounty_type == Bounty.BountyType.DUEL:
        if bounty.opponent_id and bounty.opponent_id != user.id:
            return _error_res("You are not the designated opponent for this duel.")

    if BountyParticipant.objects.filter(bounty=bounty, user=user).exists():
        return _error_res("You are already participating in this bounty.")

    if bounty.wager_tokens > prof.tokens:
        return _error_res(f"Insufficient tokens for wager. Needed {bounty.wager_tokens}, you have {prof.tokens}.")
    if bounty.wager_scraps > prof.scraps:
        return _error_res(f"Insufficient scraps for wager. Needed {bounty.wager_scraps}, you have {prof.scraps}.")

    if bounty.wager_tokens > 0:
        prof.tokens -= bounty.wager_tokens
    if bounty.wager_scraps > 0:
        prof.scraps -= bounty.wager_scraps
    prof.save(update_fields=["tokens", "scraps"])

    bounty.status = Bounty.Status.ACTIVE
    bounty.start_time = now
    bounty.end_time = now + timedelta(hours=bounty.duration_hours)
    if bounty.bounty_type == Bounty.BountyType.DUEL and not bounty.opponent:
        bounty.opponent = user
    bounty.save(update_fields=["status", "start_time", "end_time", "opponent"])

    BountyParticipant.objects.create(
        bounty=bounty,
        user=user,
        current_value=0.0,
        joined_at=now,
    )

    if bounty.creator_id != user.id:
        dispatch_push_notification(
            bounty.creator,
            PushNotificationLog.Category.BOUNTY,
            f"⚔️ Duel Accepted by @{user.username}!",
            f"{user.username} accepted your {bounty.title}! The timer has started ({bounty.duration_hours}h). Go get those reps!",
            data={"bounty_id": bounty.id, "type": "duel_accepted"},
            now=now,
        )

    evaluate_user_bounties(user, now)

    return _success_res({
        "bounty_id": bounty.id,
        "title": bounty.title,
        "status": bounty.status,
        "end_time": bounty.end_time.isoformat(),
    })


@transaction.atomic
def cancel_bounty(bounty_id, user):
    """Cancel an unaccepted open/duel bounty and refund escrowed funds."""
    try:
        bounty = Bounty.objects.select_for_update().get(id=bounty_id)
    except Bounty.DoesNotExist:
        return _error_res("Bounty not found.", 404)

    if bounty.creator_id != user.id:
        return _error_res("Only the creator can cancel this bounty.", 403)

    if bounty.status != Bounty.Status.OPEN:
        return _error_res("Cannot cancel a bounty that has already started or finished.")

    prof = combat_profile(user)
    if bounty.wager_tokens > 0:
        prof.tokens += bounty.wager_tokens
    if bounty.wager_scraps > 0:
        prof.scraps += bounty.wager_scraps
    prof.save(update_fields=["tokens", "scraps"])

    bounty.status = Bounty.Status.CANCELLED
    bounty.save(update_fields=["status"])

    return _success_res({"message": "Bounty cancelled and escrowed funds refunded."})


def evaluate_user_bounties(user, now=None):
    """Check all active bounties for user against recent logs and update progress."""
    now = now or timezone.now()

    active_parts = (
        BountyParticipant.objects.filter(
            user=user,
            bounty__status=Bounty.Status.ACTIVE,
        )
        .select_related("bounty")
    )

    for part in active_parts:
        b = part.bounty
        window_start = b.start_time or b.created_at
        window_end = min(now, b.end_time or (window_start + timedelta(hours=b.duration_hours)))

        total_progress = 0.0

        logs = RawActivityLog.objects.filter(
            user=user,
            occurred_at__gte=window_start,
            occurred_at__lte=window_end,
        )

        for log in logs:
            p = log.payload or {}
            etype = log.event_type

            if b.target_type == Bounty.TargetType.STEPS:
                if etype in ("cardio", "endurance"):
                    total_progress += float(p.get("steps") or 0)

            elif b.target_type == Bounty.TargetType.CARDIO_MINUTES:
                if etype in ("cardio", "endurance"):
                    total_progress += float(p.get("minutes") or p.get("duration_minutes") or p.get("total_duration_minutes") or 0)

            elif b.target_type == Bounty.TargetType.STRENGTH_VOLUME:
                if etype == "strength":
                    total_progress += float(p.get("total_volume_lbs") or p.get("volume_lbs") or 0)

            elif b.target_type == Bounty.TargetType.WATER_ML:
                if etype == "hydration":
                    water_oz = float(p.get("water") or p.get("water_oz") or 0)
                    water_ml = float(p.get("water_ml") or (water_oz * 29.5735))
                    total_progress += water_ml

            elif b.target_type == Bounty.TargetType.PROTEIN_G:
                if etype in ("macro", "nutrition"):
                    total_progress += float(p.get("protein") or p.get("protein_g") or 0)

            elif b.target_type == Bounty.TargetType.CALORIES_BURNED:
                if etype in ("cardio", "endurance", "workout"):
                    total_progress += float(p.get("calories") or p.get("calories_burned") or p.get("total_calories_burned") or 0)

            elif b.target_type == Bounty.TargetType.WORKOUT_COUNT:
                if etype in ("strength", "cardio", "endurance"):
                    total_progress += 1.0

            elif b.target_type == Bounty.TargetType.SLEEP_HOURS:
                if etype == "sleep":
                    total_progress += float(p.get("hours") or (float(p.get("duration_minutes") or 0) / 60.0))

        part.current_value = total_progress

        if total_progress >= b.target_value and not part.is_completed:
            part.is_completed = True
            part.completed_at = now

            if b.bounty_type in (Bounty.BountyType.SOLO, Bounty.BountyType.OPEN, Bounty.BountyType.FLOCK):
                b.status = Bounty.Status.COMPLETED
                b.winner = user
                b.save(update_fields=["status", "winner"])

            elif b.bounty_type == Bounty.BountyType.DUEL:
                b.status = Bounty.Status.COMPLETED
                b.winner = user
                b.save(update_fields=["status", "winner"])

            dispatch_push_notification(
                user,
                PushNotificationLog.Category.BOUNTY,
                "🎯 BOUNTY COMPLETED!",
                f"You conquered '{b.title}'! Tap to claim your Tokens & XP rewards.",
                data={"bounty_id": b.id, "type": "bounty_completed"},
                now=now,
            )

        part.save(update_fields=["current_value", "is_completed", "completed_at"])


@transaction.atomic
def claim_bounty_reward(bounty_id, user, now=None):
    """Claim earned tokens, scraps, and XP from a completed bounty or duel."""
    now = now or timezone.now()
    prof = combat_profile(user)

    try:
        bounty = Bounty.objects.select_for_update().get(id=bounty_id)
    except Bounty.DoesNotExist:
        return _error_res("Bounty not found.", 404)

    try:
        part = BountyParticipant.objects.select_for_update().get(bounty=bounty, user=user)
    except BountyParticipant.DoesNotExist:
        return _error_res("Participant record not found.", 404)

    if part.payout_claimed:
        return _error_res("Reward already claimed.")

    if not part.is_completed and bounty.winner_id != user.id:
        return _error_res("Bounty is not yet completed.")

    tokens_awarded = 0
    scraps_awarded = 0
    xp_awarded = bounty.reward_xp

    if bounty.bounty_type == Bounty.BountyType.SOLO:
        tokens_awarded = bounty.wager_tokens + bounty.bonus_tokens
        scraps_awarded = bounty.wager_scraps

    elif bounty.bounty_type == Bounty.BountyType.DUEL:
        if bounty.winner_id == user.id:
            tokens_awarded = (bounty.wager_tokens * 2) + bounty.bonus_tokens
            scraps_awarded = bounty.wager_scraps * 2
        else:
            xp_awarded = int(bounty.reward_xp * 0.25)

    elif bounty.bounty_type in (Bounty.BountyType.OPEN, Bounty.BountyType.FLOCK):
        tokens_awarded = bounty.wager_tokens + bounty.bonus_tokens
        scraps_awarded = bounty.wager_scraps

    if tokens_awarded > 0:
        prof.tokens += tokens_awarded
    if scraps_awarded > 0:
        prof.scraps += scraps_awarded
    prof.save(update_fields=["tokens", "scraps"])

    if xp_awarded > 0:
        target_modality = TARGET_TYPE_CONFIG.get(bounty.target_type, {}).get("modality", Modality.STRENGTH)
        from core.services.gamification import apply_to_skill_tree
        XPLedger.objects.create(
            user=user,
            modality=target_modality,
            amount=xp_awarded,
            description="bounty",
        )
        apply_to_skill_tree(user, target_modality, xp_awarded)

    part.payout_claimed = True
    part.save(update_fields=["payout_claimed"])

    bounty.is_claimed = True
    bounty.save(update_fields=["is_claimed"])

    from core.services.badges import check_badges
    check_badges(user)

    return _success_res({
        "tokens_awarded": tokens_awarded,
        "scraps_awarded": scraps_awarded,
        "xp_awarded": xp_awarded,
        "new_balance": {
            "tokens": prof.tokens,
            "scraps": prof.scraps,
        },
        "title": bounty.title,
    })


@transaction.atomic
def expire_stale_bounties(now=None):
    """Periodic cleaner for expired bounties."""
    now = now or timezone.now()
    expired_count = 0

    stale_active = Bounty.objects.filter(
        status=Bounty.Status.ACTIVE,
        end_time__lt=now,
    ).select_related("creator", "opponent")

    for b in stale_active:
        if b.bounty_type == Bounty.BountyType.DUEL:
            parts = list(b.participants.all().order_by("-current_value"))
            if parts:
                top_part = parts[0]
                if top_part.current_value > 0:
                    b.status = Bounty.Status.COMPLETED
                    b.winner = top_part.user
                    top_part.is_completed = True
                    top_part.completed_at = now
                    top_part.save(update_fields=["is_completed", "completed_at"])
                else:
                    b.status = Bounty.Status.EXPIRED
            else:
                b.status = Bounty.Status.EXPIRED
        else:
            b.status = Bounty.Status.FAILED

        b.save(update_fields=["status", "winner"])
        expired_count += 1

    stale_open = Bounty.objects.filter(
        status=Bounty.Status.OPEN,
        created_at__lt=now - timedelta(hours=48),
    )
    for b in stale_open:
        prof = combat_profile(b.creator)
        if b.wager_tokens > 0:
            prof.tokens += b.wager_tokens
        if b.wager_scraps > 0:
            prof.scraps += b.wager_scraps
        prof.save(update_fields=["tokens", "scraps"])
        b.status = Bounty.Status.EXPIRED
        b.save(update_fields=["status"])
        expired_count += 1

    return expired_count
