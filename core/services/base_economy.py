"""Base-building meta-game economy service (Phase 7 / Step 22).

All resource math lives here and nowhere else (docs/09 §3 & §5). Every
time-sensitive function accepts ``now=None`` (defaults to ``timezone.now()``)
so tests can freeze time. Wallet mutations are wrapped in
``transaction.atomic`` + ``select_for_update``, and saves use
``update_fields``.

Rulebook constants are named at the top of this module so they can be tuned
without hunting literals. Every helper used from views/tasks/admin is
re-exported from ``core/services/__init__.py`` (docs/08 endurance 500 lesson).
"""

import logging
import math
import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from ..models import (
    BaseBuilding,
    BaseBuildingDef,
    BaseResource,
    DailyReadiness,
    User,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants (docs/09 §3.1)
# ---------------------------------------------------------------------------
ENERGY_CAP = 100
ENERGY_PER_HOUR = 5
REST_DAY_ENERGY_BONUS = 25
XP_TO_MATERIALS = 20
MAX_XP_BONUS_PCT = 25
STREAK_CAP_DAYS = 10
STREAK_STEP = 0.05
CRIT_CHANCE = 0.05
STAFF_BONUS = 1.10
MODALITY_BUFF = 1.20
MODALITY_BUFF_HOURS = 24
BLUEPRINT_DROP_CHANCE = 0.10
BLUEPRINT_DROP_NAME = "golden_flamingo"

# Synergy rule table: name -> {building_slug: minimum_level}. One line per
# synergy keeps the table trivial to extend (docs/09 §5.8).
SYNERGY_RULES = {
    "poolside_chill": {"pool_deck": 2, "cabana": 2},
}
POOLSIDE_ENERGY_BONUS = 1.05  # +5% passive energy generation globally.


# ---------------------------------------------------------------------------
# Pure math helpers
# ---------------------------------------------------------------------------
def streak_multiplier(streak_days):
    """1 + (min(streak_days, STREAK_CAP_DAYS) * STREAK_STEP); saturates at 1.5x.

    0-day streak = 1.0x, 10-day streak = 1.5x. Applied to building production
    only (never to wallet spends).
    """
    days = max(0, int(streak_days or 0))
    return 1 + min(days, STREAK_CAP_DAYS) * STREAK_STEP


def xp_dividend(xp_today):
    """Daily dividend: 1 material per XP_TO_MATERIALS XP earned that day."""
    return max(0, int(xp_today or 0)) // XP_TO_MATERIALS


def _local_date(now):
    return timezone.localdate(now or timezone.now())


# ---------------------------------------------------------------------------
# Energy (overflow-safe passive regen)
# ---------------------------------------------------------------------------
def refresh_energy(resources, now=None, synergies=None):
    """Accrue passive energy up to ENERGY_CAP, overflow-safe.

    A wallet already above the cap (e.g. 115/100 after a rest day) is NEVER
    reduced - regen simply no-ops until the wallet is back under the cap.
    The refill is float-correct: elapsed * rate is applied before int()
    truncation. First call (no ``energy_updated_at``) only stamps the
    timestamp - no jump.
    """
    now = now or timezone.now()
    if resources.energy_updated_at:
        elapsed_h = (now - resources.energy_updated_at).total_seconds() / 3600
        rate = ENERGY_PER_HOUR
        if synergies and "poolside_chill" in synergies:
            rate = POOLSIDE_ENERGY_BONUS * ENERGY_PER_HOUR
        if resources.energy < ENERGY_CAP:
            resources.energy = min(
                ENERGY_CAP, int(resources.energy + elapsed_h * rate)
            )
        resources.energy_updated_at = now
        resources.save(update_fields=["energy", "energy_updated_at"])
    else:
        resources.energy_updated_at = now
        resources.save(update_fields=["energy_updated_at"])
    return resources


@transaction.atomic
def apply_rest_day_bonus(resources, user, on_date=None):
    """Grant the uncapped rest-day energy spike, once per calendar day.

    Bonus = REST_DAY_ENERGY_BONUS + each owned built Recovery Pool's
    ``rest_day_bonus_add``. The cap is NOT applied (spec §3.2). Idempotent via
    ``resources.last_rest_bonus_date``. Returns the bonus granted (or 0).
    """
    on_date = on_date or _local_date(None)
    if getattr(resources, "last_rest_bonus_date", None) == on_date:
        return 0

    ready = (
        DailyReadiness.objects.filter(user=user, date=on_date)
        .order_by("-created_at")
        .first()
    )
    if ready is not None and ready.streak_requirement == DailyReadiness.StreakRequirement.REST_DAY:
        bonus = REST_DAY_ENERGY_BONUS + sum(
            b.building_def.rest_day_bonus_add
            for b in BaseBuilding.objects.filter(user=user)
            if b.level > 0
        )
        resources.energy += bonus  # no min() clamp - overflow allowed
        resources.last_rest_bonus_date = on_date
        resources.save(update_fields=["energy", "last_rest_bonus_date"])
        return bonus
    return 0


@transaction.atomic
def daily_harvest(resources, user, on_date=None):
    """Mint XP earned since local midnight into materials, once per day.

    ``xp_today // XP_TO_MATERIALS`` materials are created. Idempotent via
    ``resources.last_daily_harvest``. Returns the minted amount (or 0).
    """
    from ..models import XPLedger  # local import avoids a model-graph cycle

    on_date = on_date or _local_date(None)
    if getattr(resources, "last_daily_harvest", None) == on_date:
        return 0

    xp_today = (
        XPLedger.objects.filter(user=user, created_at__date=on_date).aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )
    minted = xp_dividend(xp_today)
    if minted:
        resources.materials += minted
    resources.last_daily_harvest = on_date
    resources.save(update_fields=["materials", "last_daily_harvest"])
    return minted


# ---------------------------------------------------------------------------
# Production & collection
# ---------------------------------------------------------------------------
def modality_buff_active(building_def, active_buffs, now=None):
    """True when a building's modality affinity matches an unexpired buff.

    e.g. ``def.modality_affinity="cardio"`` + ``active_buffs["cardio_buff_expiry"]``
    still in the future -> 1.2x production.
    """
    affinity = building_def.modality_affinity
    if not affinity:
        return False
    expiry = (active_buffs or {}).get(f"{affinity}_buff_expiry")
    if not expiry:
        return False
    now = now or timezone.now()
    try:
        return now < timezone.datetime.fromisoformat(str(expiry))
    except (TypeError, ValueError):
        return False


def production_plan(building, streak_days, active_buffs, synergies=None, now=None):
    """Idle material accrual since ``last_produced_at`` (whole days, floored).

    ``base = (elapsed_days // 1) * def.materials_per_day * building.level``,
    multiplied by the streak multiplier (1.0..1.5), STAFF_BONUS (1.1) when a
    friend is staffed, and MODALITY_BUFF (1.2) while a matching modality buff
    is unexpired. Never negative. Returns rounded float, NOT yet collected.
    """
    now = now or timezone.now()
    started = building.last_produced_at or now
    elapsed_days = max(0, (now - started).total_seconds() / 86400)
    base = (elapsed_days // 1) * building.building_def.materials_per_day * building.level
    mult = streak_multiplier(streak_days)
    if building.staff_friend_id:
        mult *= STAFF_BONUS
    if modality_buff_active(building.building_def, active_buffs, now):
        mult *= MODALITY_BUFF
    return round(base * mult, 2)


@transaction.atomic
def collect_building(instance, now=None, rng=None):
    """Claim a building's accrued materials into the wallet.

    Rolls a CRIT_CHANCE double-yield on manual collect. No-op when level == 0
    or still constructing. Resets ``last_produced_at`` so accrual restarts.
    Returns ``(collected, was_crit)``.
    """
    now = now or timezone.now()
    if instance.level <= 0 or instance.is_constructing(now):
        return 0, False

    resources, _ = BaseResource.objects.select_for_update().get_or_create(
        user=instance.user
    )
    refresh_energy(resources, now=now, synergies=evaluate_synergies(instance.user))

    accrued = production_plan(
        instance,
        instance.user.streak,
        resources.active_buffs or {},
        synergies=evaluate_synergies(instance.user),
        now=now,
    )
    rng = rng or random.random
    was_crit = rng() < CRIT_CHANCE
    collected = int(accrued * 2) if was_crit else int(accrued)
    if collected:
        resources.materials += collected
        resources.save(update_fields=["materials"])
    instance.last_produced_at = now
    instance.save(update_fields=["last_produced_at"])
    return collected, was_crit


@transaction.atomic
def evolve_building(instance, chosen_slug, now=None):
    """Level-3 branch swap: keep level, swap def, restart production.

    Returns ``(ok, error)``. ``chosen_slug`` must be one of the VALUES in the
    current def's ``branch_choices`` (e.g. ``"cabana_mat"``), and the target
    def must exist and be active.
    """
    now = now or timezone.now()
    if instance.level < 3:
        return False, "Buildings must be level 3 to evolve."
    branch_values = list((instance.building_def.branch_choices or {}).values())
    if chosen_slug not in branch_values:
        return False, "Invalid branch choice."
    target_def = BaseBuildingDef.objects.filter(
        slug=chosen_slug, is_active=True
    ).first()
    if target_def is None:
        return False, "Branch building not found or inactive."
    instance.building_def = target_def
    instance.last_produced_at = now
    instance.save(update_fields=["building_def", "last_produced_at"])
    return True, ""


# ---------------------------------------------------------------------------
# Modality buffs, synergies & XP bonus
# ---------------------------------------------------------------------------
@transaction.atomic
def log_modality_workout(resources, modality, now=None):
    """Write a 24h production buff for a just-logged workout modality.

    ``"strength"`` workout handler -> ``"strength"``; ``cardio``/``endurance``
    handlers -> ``"cardio"``. Called by the gamification hook, not views.
    """
    now = now or timezone.now()
    key = f"{modality}_buff_expiry"
    active_buffs = dict(resources.active_buffs or {})
    active_buffs[key] = (now + timedelta(hours=MODALITY_BUFF_HOURS)).isoformat()
    resources.active_buffs = active_buffs
    resources.save(update_fields=["active_buffs"])


def evaluate_synergies(user):
    """Active layout synergies granted by BUILT building levels (Lv2+)."""
    levels = {}
    for building in BaseBuilding.objects.filter(user=user):
        if building.level >= 2:
            levels[building.building_def.slug] = max(
                levels.get(building.building_def.slug, 0), building.level
            )
    active = []
    for name, requirements in SYNERGY_RULES.items():
        if all(
            levels.get(slug, 0) >= min_level
            for slug, min_level in requirements.items()
        ):
            active.append(name)
    return active


def base_xp_bonus_pct(user):
    """Combined building XP bonus %, capped at MAX_XP_BONUS_PCT."""
    total = sum(
        building.building_def.xp_bonus_pct * building.level
        for building in BaseBuilding.objects.filter(user=user)
    )
    return min(MAX_XP_BONUS_PCT, total)


def base_level(user):
    """Base level = sum of built instance levels (unlock gates / milestones)."""
    return sum(
        b.level for b in BaseBuilding.objects.filter(user=user).only("level")
    )


def clear_expired_buffs(resources, now=None):
    """Drop ``*_buff_expiry`` keys whose ISO date is in the past."""
    now = now or timezone.now()
    active_buffs = dict(resources.active_buffs or {})
    changed = False
    for key in list(active_buffs):
        if not key.endswith("_buff_expiry"):
            continue
        try:
            if timezone.datetime.fromisoformat(str(active_buffs[key])) < now:
                del active_buffs[key]
                changed = True
        except (TypeError, ValueError):
            del active_buffs[key]
            changed = True
    if changed:
        resources.active_buffs = active_buffs
        resources.save(update_fields=["active_buffs"])
    return resources


def refresh_resources(resources, user, now=None):
    """The single entry point views/tasks use before every read/mutation.

    Order: energy -> expired buffs -> rest-day bonus -> daily harvest.
    Safe to call repeatedly (every step is idempotent by stored date/timestamp).
    """
    now = now or timezone.now()
    synergies = evaluate_synergies(user)
    refresh_energy(resources, now=now, synergies=synergies)
    clear_expired_buffs(resources, now=now)
    apply_rest_day_bonus(resources, user, on_date=_local_date(now))
    daily_harvest(resources, user, on_date=_local_date(now))
    return resources


def resource_dump(resources):
    """Wallet state shared by /dashboard/state and /base/ (badge parity)."""
    return {
        "materials": resources.materials,
        "energy": resources.energy,
        "time_speedups": resources.time_speedups,
        "blueprints": dict(resources.blueprints or {}),
        "energy_cap": ENERGY_CAP,
        "energy_per_hour": ENERGY_PER_HOUR,
    }


# ---------------------------------------------------------------------------
# Construction lifecycle
# ---------------------------------------------------------------------------
def complete_or_pending(instance, now=None):
    """Lazily complete a finished construction (reads stay mutation-free).

    Returns ``"completed"`` when the timer had expired (level now applied),
    otherwise ``"pending"`` (or ``"idle"`` when nothing is constructing).
    """
    now = now or timezone.now()
    if not instance.construction_started_at:
        return "idle"
    if instance.is_constructing(now):
        return "pending"
    instance.level = instance.target_level
    instance.target_level = 0
    instance.construction_started_at = None
    instance.construction_duration_hours = 0
    instance.last_produced_at = now
    instance.save(
        update_fields=[
            "level",
            "target_level",
            "construction_started_at",
            "construction_duration_hours",
            "last_produced_at",
        ]
    )
    return "completed"


@transaction.atomic
def start_construction(user, slug, now=None):
    """Start building/upgrading ``slug``; returns ``(ok, error)``.

    Validates def active, base-level + blueprint unlock, not already
    constructing, max level, and funds. Micro-builds (``base_duration_hours
    == 0``) complete immediately in the same call.
    """
    now = now or timezone.now()
    building_def = BaseBuildingDef.objects.filter(slug=slug, is_active=True).first()
    if building_def is None:
        return False, "Building not found or inactive."

    current_level = base_level(user)
    if current_level < building_def.requires_base_level:
        return (
            False,
            f"Base level {building_def.requires_base_level} required.",
        )
    if building_def.requires_blueprint:
        resources, _ = BaseResource.objects.select_for_update().get_or_create(
            user=user
        )
        owned = int((resources.blueprints or {}).get(building_def.requires_blueprint, 0))
        if owned <= 0:
            return False, "Requires a blueprint to build."

    instance = BaseBuilding.objects.filter(user=user, building_def=building_def).first()
    if instance is not None and instance.is_constructing(now):
        return False, "Already constructing this building."

    target_level = (instance.level if instance is not None else 0) + 1
    if instance is not None and instance.level >= building_def.max_level:
        return False, "This building is already at max level."

    cost_materials, cost_energy = building_def.cost_for_level(target_level)
    resources, _ = BaseResource.objects.select_for_update().get_or_create(user=user)
    refresh_energy(resources, now=now, synergies=evaluate_synergies(user))
    if resources.materials < cost_materials:
        return False, "Not enough materials."
    if resources.energy < cost_energy:
        return False, "Not enough energy."
    resources.materials -= cost_materials
    resources.energy -= cost_energy
    resources.save(update_fields=["materials", "energy"])

    duration_hours = building_def.duration_for_level(target_level)
    is_micro = building_def.base_duration_hours == 0
    if instance is None:
        BaseBuilding.objects.create(
            user=user,
            building_def=building_def,
            level=target_level if is_micro else 0,
            target_level=0 if is_micro else target_level,
            construction_started_at=None if is_micro else now,
            construction_duration_hours=0 if is_micro else duration_hours,
            last_produced_at=now if is_micro else None,
        )
    else:
        instance.target_level = target_level
        instance.construction_started_at = None if is_micro else now
        instance.construction_duration_hours = 0 if is_micro else duration_hours
        if is_micro:
            instance.level = target_level
            instance.last_produced_at = now
        instance.save(
            update_fields=[
                "level",
                "target_level",
                "construction_started_at",
                "construction_duration_hours",
                "last_produced_at",
            ]
        )
    return True, ""


@transaction.atomic
def spend_speedups(instance, hours, now=None):
    """Spend time-speedups to skip construction; refunds overshoot.

    Returns ``(ok, spent, error, completed)``. ``spent`` is capped at the hours
    actually needed, and any overshoot request is refunded into the wallet.
    """
    now = now or timezone.now()
    if not instance.is_constructing(now):
        return False, 0, "Nothing is under construction.", False

    resources, _ = BaseResource.objects.select_for_update().get_or_create(
        user=instance.user
    )
    refresh_energy(resources, now=now, synergies=evaluate_synergies(instance.user))

    remaining_h = max(
        0.0,
        (
            instance.construction_started_at
            + timedelta(hours=instance.construction_duration_hours)
            - now
        ).total_seconds()
        / 3600,
    )
    needed = math.ceil(remaining_h)
    requested = min(max(1, int(hours or 1)), needed)
    if resources.time_speedups < requested:
        return (
            False,
            0,
            "Not enough time speedups - conquer a PR Boss to earn more.",
            False,
        )
    resources.time_speedups -= requested
    resources.save(update_fields=["time_speedups"])

    remaining_h_after = remaining_h - requested
    if remaining_h_after <= 0:
        refund = max(0, int(hours or 0) - needed)
        if refund:
            resources.time_speedups += refund
            resources.save(update_fields=["time_speedups"])
        instance.level = instance.target_level
        instance.target_level = 0
        instance.construction_started_at = None
        instance.construction_duration_hours = 0
        instance.last_produced_at = now
        instance.save(
            update_fields=[
                "level",
                "target_level",
                "construction_started_at",
                "construction_duration_hours",
                "last_produced_at",
            ]
        )
        return True, requested, "", True
    return True, requested, "", False


def maybe_drop_blueprint(user, rng=None):
    """Roll a BLUEPRINT_DROP_CHANCE boss-PR blueprint drop.

    Returns True when a blueprint was granted. ``rng`` is injectable for tests.
    """
    rng = rng or random.random
    if rng() >= BLUEPRINT_DROP_CHANCE:
        return False
    resources, _ = BaseResource.objects.get_or_create(user=user)
    blueprints = dict(resources.blueprints or {})
    blueprints[BLUEPRINT_DROP_NAME] = blueprints.get(BLUEPRINT_DROP_NAME, 0) + 1
    resources.blueprints = blueprints
    resources.save(update_fields=["blueprints"])
    return True


def tick_base_economy(now=None):
    """Daily (or on-demand) economy maintenance for every base-owning user.

    Idempotent: refreshes energy/harvest/buffs, lazily completes finished
    constructions, and auto-collects whole-day production (no crits in the
    background - crits stay a manual-collect thrill).
    """
    now = now or timezone.now()
    user_ids = list(
        BaseResource.objects.filter(user__is_active=True).values_list(
            "user_id", flat=True
        )
    )
    stats = {"users": 0, "completed": 0, "collected": 0}
    for user in User.objects.filter(pk__in=user_ids).iterator():
        try:
            resources, _ = BaseResource.objects.select_for_update().get_or_create(
                user=user
            )
            refresh_resources(resources, user, now=now)
            for building in BaseBuilding.objects.filter(user=user):
                if complete_or_pending(building, now=now) == "completed":
                    stats["completed"] += 1
                if building.level > 0 and not building.is_constructing(now):
                    collected, _ = collect_building(building, now=now, rng=lambda: 1.0)
                    stats["collected"] += collected
            stats["users"] += 1
        except Exception:  # noqa: BLE001 - never let one user break the beat
            logger.exception("tick_base_economy failed for user %s", user.username)
    return stats