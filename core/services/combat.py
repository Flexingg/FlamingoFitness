"""Combat / Token / Gacha / PvE / PvP service (Phase 9, docs/15 §5).

Replaces the Phase 7 ``core/services/base_economy.py``. Every helper used from
views/tasks/admin is re-exported from ``core/services/__init__.py`` (docs/08
endurance-500 lesson). Time-sensitive functions accept ``now=None``; wallet
mutations are atomic; saves use ``update_fields``.
"""

import logging
import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from ..models import (
    BattleLog,
    Campaign,
    CampaignBoss,
    CampaignProgress,
    DailyReadiness,
    GearItemDef,
    GearPackDef,
    Gym,
    GymOccupation,
    PlayerProfile,
    PvPMatch,
    Rarity,
    RawActivityLog,
    ScrapShopItem,
    UserGear,
    XPLedger,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants (docs/15 §3 - sourced from config/gameplay.json).
# To retune the economy / stamina / gacha / combat without code, edit
# config/gameplay.json (see docs segment in tools/code.gs flow).
# ---------------------------------------------------------------------------
from .game_config import GAMEPLAY  # noqa: E402

XP_TO_TOKENS = int(GAMEPLAY["economy"]["xp_per_token"])
STREAK_TOKEN_CAP_DAYS = int(GAMEPLAY["economy"]["streak_token_cap_days"])
STREAK_TOKEN_STEP = float(GAMEPLAY["economy"]["streak_token_step"])
TOKEN_PERFECT_MACRO = int(GAMEPLAY["economy"]["token_perfect_macro"])
TOKEN_PERFECT_HYDRATION = int(GAMEPLAY["economy"]["token_perfect_hydration"])
TOKEN_PVE_CONQUEST = int(GAMEPLAY["economy"]["token_pve_conquest"])
TOKEN_BOSS_PR = int(GAMEPLAY["economy"]["token_boss_pr"])
TOKEN_TIME_SPEEDUP_RATE = int(GAMEPLAY["economy"]["token_time_speedup_rate"])
TOKEN_MATERIAL_RATE = int(GAMEPLAY["economy"]["token_material_rate"])
TOKEN_STARTER = int(GAMEPLAY["economy"]["token_starter"])

PACK_PRICE_SIMPLE = int(GAMEPLAY["shop"]["pack_price_simple"])
PACK_PRICE_DELUXE = int(GAMEPLAY["shop"]["pack_price_deluxe"])
PACK_PRICE_LEGENDARY = int(GAMEPLAY["shop"]["pack_price_legendary"])

# Bulk-buy discounts (docs/15 §3.2): quantity tiers -> % off the unit price.
BULK_DISCOUNTS = {int(k): float(v) for k, v in GAMEPLAY["gacha"]["bulk_discounts"].items()}
BULK_MAX = int(GAMEPLAY["gacha"]["bulk_max"])
_RARITY_BY_KEY = {
    Rarity.COMMON.value: Rarity.COMMON,
    Rarity.RARE.value: Rarity.RARE,
    Rarity.EPIC.value: Rarity.EPIC,
    Rarity.LEGENDARY.value: Rarity.LEGENDARY,
}
RARITY_WEIGHTS_BASE = {
    _RARITY_BY_KEY[k]: int(v) for k, v in GAMEPLAY["gacha"]["rarity_weights_base"].items()
}
EPIC_STREAK_STEP = float(GAMEPLAY["gacha"]["epic_streak_step"])
LEGENDARY_STREAK_STEP = float(GAMEPLAY["gacha"]["legendary_streak_step"])
STREAK_ODDS_START_DAY = int(GAMEPLAY["gacha"]["streak_odds_start_day"])

HEAD_SLOT = "head"
BODY_SLOT = "body"   # kept for legacy; the UI shows "chest" now
ACCESSORY_SLOT = "accessory"

# Displayed equippable slots, in order (docs/15 cleanup: expanded loadout).
SLOT_ORDER = ("head", "chest", "left_hand", "right_hand", "legs", "feet", "accessory")
GEAR_MULT_POOL = {
    _RARITY_BY_KEY[k]: tuple(v) for k, v in GAMEPLAY["gacha"]["gear_mult_pool"].items()
}
SYNERGY_SLEEP_EFF = float(GAMEPLAY["gacha"]["synergy_sleep_eff"])
CONSUMABLE_MAX_STACK = int(GAMEPLAY["gacha"]["consumable_max_stack"])
BUFF_HOURS = int(GAMEPLAY["gacha"]["buff_hours"])

BOSS_HP_SCALE = {k: int(v) for k, v in GAMEPLAY["combat"]["boss_hp_scale"].items()}
STAMINA_PER_DAY = int(GAMEPLAY["stamina"]["per_day"])
REST_DAY_STAMINA_BONUS = int(GAMEPLAY["stamina"]["rest_day_bonus"])
BOSS_HEAL_OVERAGE = int(GAMEPLAY["combat"]["boss_heal_overage"])

ELEMENT_WHEEL = dict(GAMEPLAY["combat"]["element_wheel"])
PVP_AGGRESSOR_WIN_EDGE = float(GAMEPLAY["pvp"]["aggressor_win_edge"])
GYM_TOKEN_YIELD_BASE = int(GAMEPLAY["pvp"]["gym_token_yield_base"])
GYM_HOLD_WINDOW_HOURS = int(GAMEPLAY["pvp"]["gym_hold_window_hours"])
PVP_CONSISTENCY_WINDOW_DAYS = int(GAMEPLAY["pvp"]["consistency_window_days"])

# Scrap economy (docs/16): recycling gear yields scraps by rarity.
SCRAP_VALUE_BY_RARITY = {
    _RARITY_BY_KEY[k]: int(v) for k, v in GAMEPLAY["scrap"]["value_by_rarity"].items()
}
WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

_CAMPAIGN_EVENT_TYPES = {
    Campaign.CARDIO: ("cardio", "endurance"),
    Campaign.STRENGTH: ("strength",),
    Campaign.NUTRITION: ("nutrition",),
    Campaign.HYDRATION: ("hydration",),
    Campaign.SLEEP: ("sleep",),
}
# ---------------------------------------------------------------------------
# Wallet (PlayerProfile) - docs/15 §5.1
# ---------------------------------------------------------------------------
def profile(user):
    """Get-or-create a user's PlayerProfile (starts at TOKEN_STARTER)."""
    return PlayerProfile.objects.get_or_create(user=user)[0]


def wallet_dump(p):
    """Shared wallet shape for /dashboard/state, /battle/state and /shop/state."""
    return {
        "tokens": p.tokens,
        "scraps": p.scraps,
        "stamina": p.stamina,
        "stamina_cap": stamina_cap(p, p.user),
        "rest_day_bonus": REST_DAY_STAMINA_BONUS,
    }


def streak_multiplier(streak_days):
    """1 + min(streak, STREAK_TOKEN_CAP_DAYS) * STREAK_TOKEN_STEP; caps at 1.5x."""
    days = max(0, int(streak_days or 0))
    return 1 + min(days, STREAK_TOKEN_CAP_DAYS) * STREAK_TOKEN_STEP


def token_dividend(xp_today, streak_days):
    """Daily dividend: int(xp / XP_TO_TOKENS) * streak_multiplier."""
    return max(0, int(xp_today or 0) // XP_TO_TOKENS) * streak_multiplier(streak_days)


@transaction.atomic
def award_tokens(user, amount):
    """Add tokens to a user's wallet (additive)."""
    if not amount:
        return
    p, _ = PlayerProfile.objects.select_for_update().get_or_create(user=user)
    p.tokens += int(amount)
    p.save(update_fields=["tokens"])


@transaction.atomic
def spend_tokens(user, amount):
    """Deduct tokens. Returns (ok, error)."""
    p, _ = PlayerProfile.objects.select_for_update().get_or_create(user=user)
    if p.tokens < amount:
        return False, "Not enough tokens."
    p.tokens -= int(amount)
    p.save(update_fields=["tokens"])
    return True, None


def token_dividend_multiplier(p, user, on_date=None):
    """Product of equipped ``token_multiplier`` gear (extra daily coins)."""
    on_date = on_date or timezone.localdate()
    mult = 1.0
    for ug in UserGear.objects.filter(
        user=user,
        equipped_slot__isnull=False,
        gear_def__is_consumable=False,
        gear_def__effect_type="token_multiplier",
    ):
        mult *= float(ug.gear_def.effect_value or 1.0)
    return mult


def daily_token_harvest(user, on_date=None):
    """Mint the daily token dividend, idempotent per (user, date). Returns minted."""
    on_date = on_date or timezone.localdate()
    p, _ = PlayerProfile.objects.get_or_create(user=user)
    if p.last_token_harvest == on_date:
        return 0
    xp_today = (
        XPLedger.objects.filter(user=user, created_at__date=on_date).aggregate(
            s=Sum("amount")
        )["s"]
        or 0
    )
    minted = int(token_dividend(xp_today, user.streak) * token_dividend_multiplier(p, user))
    p.tokens += minted
    p.last_token_harvest = on_date
    p.save(update_fields=["tokens", "last_token_harvest"])
    return minted


def _is_rest_day(user, on_date=None):
    on_date = on_date or timezone.localdate()
    r = DailyReadiness.objects.filter(user=user, date=on_date).first()
    return bool(r and r.streak_requirement == DailyReadiness.StreakRequirement.REST_DAY)


def stamina_cap(p, user, on_date=None):
    """Daily stamina ceiling: base + rest-day bonus + equipped ``stamina_cap`` gear.

    ``stamina_cap`` items are non-consumable equipment that raise the ceiling, so
    equipped stamina gear lets a player accrue more siege attacks each morning.
    """
    on_date = on_date or timezone.localdate()
    base = STAMINA_PER_DAY + (REST_DAY_STAMINA_BONUS if _is_rest_day(user, on_date) else 0)
    gear_bonus = sum(
        float(ug.gear_def.effect_value or 0)
        for ug in UserGear.objects.filter(
            user=user,
            equipped_slot__isnull=False,
            gear_def__is_consumable=False,
            gear_def__effect_type="stamina_cap",
        )
    )
    return int(base + gear_bonus)


def refresh_stamina(p, user, now=None, on_date=None):
    """Refill daily stamina (overflow-safe; rest day grants REST_DAY_STAMINA_BONUS).

    Uses :func:`stamina_cap` so equipped ``stamina_cap`` gear raises the ceiling a
    player refills toward and can keep above.
    """
    now = now or timezone.now()
    on_date = on_date or timezone.localdate(now)
    if p.stamina_updated_at and p.stamina_updated_at.date() >= on_date:
        return p
    cap = stamina_cap(p, user, on_date=on_date)
    p.stamina = max(p.stamina, cap)  # overflow-safe: never reduces below existing
    p.stamina_updated_at = now
    p.save(update_fields=["stamina", "stamina_updated_at"])
    return p


def clear_expired_buffs(p, now=None):
    """Drop dated combat buff keys whose date is in the past."""
    now = now or timezone.now()
    today = now.date()
    changed = False
    buffs = dict(p.active_buffs or {})
    for key, iso in list(buffs.items()):
        try:
            if iso and iso[:10] < today.isoformat():
                del buffs[key]
                changed = True
        except (TypeError, ValueError):
            del buffs[key]
            changed = True
    if changed:
        p.active_buffs = buffs
        p.save(update_fields=["active_buffs"])
    return p

# ---------------------------------------------------------------------------
# Gacha - docs/15 §5.2
# ---------------------------------------------------------------------------
def rarity_weights(streak_days):
    """Dynamic rarity drop weights, shifted by logging streak (docs/15 §3.2)."""
    weights = dict(RARITY_WEIGHTS_BASE)
    days = max(0, int(streak_days or 0))
    if days > STREAK_ODDS_START_DAY:
        boost = days - STREAK_ODDS_START_DAY
        epic_add = EPIC_STREAK_STEP * boost
        leg_add = LEGENDARY_STREAK_STEP * boost
        drain = epic_add + leg_add
        weights[Rarity.EPIC] = max(0.0, weights[Rarity.EPIC] + epic_add)
        weights[Rarity.LEGENDARY] = max(0.0, weights[Rarity.LEGENDARY] + leg_add)
        weights[Rarity.COMMON] = max(0.0, weights[Rarity.COMMON] - drain)
    return weights


def _pick_rarity(weights, rng):
    items = list(weights.items())
    total = sum(w for _, w in items)
    roll = rng() * total
    acc = 0.0
    for rarity, w in items:
        acc += w
        if roll <= acc:
            return rarity
    return items[-1][0]


def bulk_price(price, quantity):
    """Total cost for ``quantity`` copies of a pack with the bulk discount.

    Returns ``(total_cost, discount_percent)``.
    """
    qty = max(1, int(quantity or 1))
    discount = BULK_DISCOUNTS.get(qty, BULK_DISCOUNTS[BULK_MAX])
    unit = price * (1 - discount)
    return int(round(unit * qty)), round(discount * 100)


def _run_pulls(user, pack, draws, rng):
    """Roll ``draws`` items from a pack and grant them.

    Returns ``(ok, error, manifest)``; the caller is responsible for spending
    (and refunding) tokens.
    """
    qs = GearItemDef.objects.filter(is_active=True)
    if getattr(pack, "is_generic", False):
        # Crate-style packs drop from the ENTIRE active catalog, not just the
        # items linked via the pack FK (a pack FK ties gear to a single pack).
        candidates = list(qs)
    else:
        qs = qs.filter(pack=pack)
        if pack.domains:
            qs = qs.filter(effect_domain__in=pack.domains) | qs.filter(is_consumable=True)
        candidates = list(qs)
    if not candidates:
        return False, "This pack has no items configured yet.", []
    weights = rarity_weights(user.streak)
    manifest = []
    for _ in range(max(1, draws)):
        rarity = _pick_rarity(weights, rng)
        if _rarity_index(rarity) < _rarity_index(pack.guaranteed_min_rarity):
            rarity = pack.guaranteed_min_rarity
        item = _pick_item(candidates, rng)
        own = _grant_item(user, item, rarity)
        manifest.append({
            "gear_slug": item.slug,
            "name": item.name,
            "rarity": rarity,
            "icon": item.icon,
            "is_new": own["is_new"],
            "quantity": own["quantity"],
        })
    return True, None, manifest


def open_pack(user, pack, rng=None):
    """Spend tokens and pull ``pack.draws`` items. Returns (ok, error, manifest)."""
    rng = rng or random.random
    ok, err = spend_tokens(user, pack.price_tokens)
    if not ok:
        return False, err, []
    ok, err, manifest = _run_pulls(user, pack, pack.draws, rng)
    if not ok:
        award_tokens(user, pack.price_tokens)  # refund
    return ok, err, manifest


def open_pack_bulk(user, pack, quantity, rng=None):
    """Buy ``quantity`` copies of a pack (draws x quantity) with the bulk discount.

    Returns ``(ok, err, payload)`` where payload has ``quantity``, ``cost``,
    ``discount_pct`` and ``manifest``.
    """
    rng = rng or random.random
    qty = max(1, min(int(quantity or 1), BULK_MAX))
    cost, discount_pct = bulk_price(pack.price_tokens, qty)
    ok, err = spend_tokens(user, cost)
    if not ok:
        return False, err, None
    ok, err, manifest = _run_pulls(user, pack, pack.draws * qty, rng)
    if not ok:
        award_tokens(user, cost)  # refund
    return ok, err, {
        "quantity": qty,
        "cost": cost,
        "discount_pct": discount_pct,
        "manifest": manifest,
    }


def _rarity_index(rarity):
    return {"common": 0, "rare": 1, "epic": 2, "legendary": 3}.get(rarity, 0)


def _pick_item(candidates, rng):
    total = sum(max(1, it.weight) for it in candidates)
    roll = rng() * total
    acc = 0
    for it in candidates:
        acc += max(1, it.weight)
        if roll <= acc:
            return it
    return candidates[-1]


def _grant_item(user, item, rarity):
    """Create/stack a UserGear row. Returns {is_new, quantity}."""
    existing = UserGear.objects.filter(user=user, gear_def=item, rarity=rarity).first()
    if item.is_consumable and existing:
        existing.quantity = min(item.max_stack, existing.quantity + 1)
        existing.save(update_fields=["quantity"])
        return {"is_new": False, "quantity": existing.quantity}
    UserGear.objects.create(user=user, gear_def=item, rarity=rarity, quantity=1)
    return {"is_new": True, "quantity": 1}

# ---------------------------------------------------------------------------
# Loadout, buffs & base damage - docs/15 §5.3
# ---------------------------------------------------------------------------
def _summarize(name, raw_log):
    """Lazy summarize_* dispatch (avoids a gamification<->combat import cycle)."""
    from .gamification import (  # noqa: PLC0415
        summarize_endurance,
        summarize_hydration,
        summarize_nutrition,
        summarize_sleep,
        summarize_strength,
    )

    fns = {
        "endurance": summarize_endurance,
        "strength": summarize_strength,
        "nutrition": summarize_nutrition,
        "hydration": summarize_hydration,
        "sleep": summarize_sleep,
    }
    return fns[name](raw_log)


def base_damage_for(campaign, user, on_date=None):
    """Base damage for a campaign from today's real tracked data (docs/15 §2)."""
    on_date = on_date or timezone.localdate()
    event_types = _CAMPAIGN_EVENT_TYPES.get(campaign, (campaign,))
    log = (
        RawActivityLog.objects.filter(
            user=user, event_type__in=event_types, occurred_at__date=on_date
        )
        .order_by("-occurred_at")
        .first()
    )
    scale = BOSS_HP_SCALE.get(campaign, 1)
    if campaign == Campaign.CARDIO:
        return int((_summarize("endurance", log)["total_calories_burned"]) / scale) if log else 0
    if campaign == Campaign.STRENGTH:
        return int((_summarize("strength", log)["total_volume_lbs"]) / scale) if log else 0
    if campaign == Campaign.NUTRITION and log:
        s = _summarize("nutrition", log)
        goal = s.get("protein_goal") or 0
        base = int(min(1.5, (s.get("protein", 0) / goal if goal else 1)) * (s.get("protein", 0) / scale))
        return base
    if campaign == Campaign.HYDRATION and log:
        s = _summarize("hydration", log)
        goal = s.get("water_goal") or 96
        water = s.get("water", 0)
        return int((water / scale) * (2 if goal else 1)) if water else 0
    if campaign == Campaign.SLEEP and log:
        s = _summarize("sleep", log)
        hours = s.get("sleep_hours") or 0
        return int((hours * 10) / scale)
    return 0


def _last_night_sleep_hours(user, on_date=None):
    """Most recent sleep log's sleep_hours before/on on_date (for synergy gates)."""
    on_date = on_date or timezone.localdate()
    log = (
        RawActivityLog.objects.filter(
            user=user, event_type="sleep", occurred_at__date__lte=on_date
        )
        .order_by("-occurred_at")
        .first()
    )
    if not log:
        return 0.0
    return _summarize("sleep", log).get("sleep_hours") or 0.0


def _buff_gate_passes(item, user, on_date=None):
    """True when a synergy/consumable gate is satisfied."""
    if item.requires_sleep_efficiency:
        hours = _last_night_sleep_hours(user, on_date)
        eff = min(1.0, hours / 8.0)
        return eff >= item.requires_sleep_efficiency
    return True


def total_gear_multiplier(p, user, domain, on_date=None):
    """Product of equipped item multipliers affecting ``domain`` (docs/15 §3.3)."""
    mult = 1.0
    for ug in UserGear.objects.filter(
        user=user, equipped_slot__isnull=False, gear_def__is_consumable=False
    ).select_related("gear_def"):
        gd = ug.gear_def
        if gd.effect_type == "double_domain":
            continue
        if gd.effect_domain and gd.effect_domain != domain:
            continue
        if gd.effect_type == "synergy" and not _buff_gate_passes(gd, user, on_date):
            continue
        mult *= float(gd.effect_value or 1.0)
    return mult


def _scale_metric(source, user, on_date):
    """Resolve a ``scales_with`` metric to a numeric magnitude (docs/16)."""
    source = str(source or "").strip()
    if source in Campaign.values:
        return float(base_damage_for(source, user, on_date))
    if source == "streak":
        return float(user.streak or 0)
    if source == "xp":
        return float(getattr(user, "total_xp", 0) or 0)
    if source == "tokens":
        return float(profile(user).tokens or 0)
    if source == "stamina":
        return float(profile(user).stamina or 0)
    return 0.0


def _scales_with_contribution(gd, user, on_date):
    """Bonus contributed by an equipped ``scales_with`` item for its target domain."""
    if gd.requires_sleep_efficiency and not _buff_gate_passes(gd, user, on_date):
        return 0.0
    source = (gd.effect_params or {}).get("scales_from") or "strength"
    return float(gd.effect_value or 0) * _scale_metric(source, user, on_date)


def additive_bonus(p, user, domain, on_date=None):
    """Flat damage added to ``domain`` from equipped ``flat_bonus`` / ``scales_with``.

    ``flat_bonus`` adds ``effect_value`` points outright; ``scales_with`` adds
    ``effect_value * <metric>`` points, where the metric comes from
    ``effect_params['scales_from']`` (a campaign domain, or ``streak``/``xp``/
    ``tokens``/``stamina``).
    """
    on_date = on_date or timezone.localdate()
    total = 0.0
    for ug in UserGear.objects.filter(
        user=user,
        equipped_slot__isnull=False,
        gear_def__is_consumable=False,
        gear_def__effect_type__in=["flat_bonus", "scales_with"],
    ).select_related("gear_def"):
        gd = ug.gear_def
        if gd.effect_domain and gd.effect_domain != domain:
            continue
        if gd.effect_type == "flat_bonus":
            total += float(gd.effect_value or 0)
        elif gd.effect_type == "scales_with":
            total += _scales_with_contribution(gd, user, on_date)
    return round(total, 2)


def active_buff_multiplier(p, domain, on_date=None):
    """Consumable buff multiplier for a campaign (docs/15 §3.4)."""
    on_date = on_date or timezone.localdate()
    today = on_date.isoformat()
    buffs = p.active_buffs or {}
    mult = 1.0
    if domain == Campaign.CARDIO and buffs.get("cardio_double_date", "")[:10] == today[:10]:
        mult *= 2.0
    return mult


def has_overage_shield(p, on_date=None):
    on_date = on_date or timezone.localdate()
    return (p.active_buffs or {}).get("shield_overage_date", "")[:10] == on_date.isoformat()[:10]


def consume_consumable(profile_obj, user, gear_id):
    """Use a consumable UserGear. Writes a dated buff or grants stamina/tokens.

    Returns (ok, error).
    """
    ug = UserGear.objects.filter(pk=gear_id, user=user, gear_def__is_consumable=True).first()
    if ug is None:
        return False, "Consumable not found."
    today = timezone.localdate().isoformat()
    etype = ug.gear_def.effect_type
    buffs = dict(profile_obj.active_buffs or {})
    changed_fields = []
    if etype == "double_domain":
        key = f"{ug.gear_def.effect_domain}_double_date"
        buffs[key] = today
        profile_obj.active_buffs = buffs
        changed_fields.append("active_buffs")
    elif etype == "shield_overage":
        buffs["shield_overage_date"] = today
        profile_obj.active_buffs = buffs
        changed_fields.append("active_buffs")
    elif etype == "stamina_refund":
        cap = stamina_cap(profile_obj, user)
        refund = int(ug.gear_def.effect_value or 0)
        profile_obj.stamina = min(cap, profile_obj.stamina + refund)
        changed_fields.append("stamina")
    elif etype == "grant_tokens":
        profile_obj.tokens += int(ug.gear_def.effect_value or 0)
        changed_fields.append("tokens")
    else:
        return False, "Not a usable consumable type."
    profile_obj.save(update_fields=changed_fields)
    ug.quantity = max(0, ug.quantity - 1)
    if ug.quantity <= 0:
        ug.delete()
    else:
        ug.save(update_fields=["quantity"])
    return True, None

# ---------------------------------------------------------------------------
# PvE sieges - docs/15 §5.4
# ---------------------------------------------------------------------------
def boss_vulnerability(boss, campaign):
    """campaign damage multiplier vs a boss: 2.0 weak / 0.5 resisted / 1.0 neutral."""
    if campaign in (boss.weaknesses or []):
        return 2.0
    if campaign in (boss.resistances or []):
        return 0.5
    return 1.0


def _is_over_calories(user, on_date=None):
    on_date = on_date or timezone.localdate()
    log = (
        RawActivityLog.objects.filter(
            user=user, event_type="nutrition", occurred_at__date=on_date
        )
        .order_by("-occurred_at")
        .first()
    )
    if not log:
        return False
    s = _summarize("nutrition", log)
    cal = s.get("calories") or 0
    goal = s.get("calorie_goal")
    return bool(goal and cal > int(goal))


def _first_boss(campaign):
    return CampaignBoss.objects.filter(campaign=campaign, is_active=True).order_by(
        "sort_order", "id"
    ).first()


def engage_boss(user, campaign, on_date=None):
    """Create/refresh the siege for a campaign against its current boss."""
    boss = _first_boss(campaign)
    if boss is None:
        return None, "No boss in this campaign yet."
    prog, _ = CampaignProgress.objects.update_or_create(
        user=user,
        campaign=campaign,
        defaults={"boss": boss, "total_hp": boss.hp_total, "engaged_at": timezone.now()},
    )
    return prog, None


def _resolve_attack(user, campaign, prog, now, on_date):
    p = profile(user)
    boss = prog.boss
    base = float(base_damage_for(campaign, user, on_date)) + additive_bonus(p, user, campaign, on_date=on_date)
    gear_mult = total_gear_multiplier(p, user, campaign, on_date=on_date)
    vuln = boss_vulnerability(boss, campaign)
    buff_mult = active_buff_multiplier(p, campaign, on_date)
    raw = base * gear_mult * vuln * buff_mult
    heal = 0
    if (boss.mechanics or {}).get("heal_on_overage") and _is_over_calories(user, on_date) \
            and not has_overage_shield(p, on_date):
        heal = BOSS_HEAL_OVERAGE
    total = max(0, int(raw) - heal)
    prog.damage_dealt += total
    tokens_won = 0
    conquered = False
    if prog.damage_dealt >= prog.total_hp:
        conquered = True
        tokens_won = TOKEN_PVE_CONQUEST
        award_tokens(user, tokens_won)
        p.total_conquests += 1
        p.save(update_fields=["total_conquests"])
    BattleLog.objects.create(
        user=user, campaign=campaign, date=on_date,
        boss=prog.boss,
        base_damage=int(base), gear_multiplier=round(gear_mult, 2),
        boss_multiplier=round(vuln * buff_mult, 2),
        total_damage=total, boss_heal=heal, tokens_won=tokens_won,
    )
    if conquered:
        nxt = CampaignBoss.objects.filter(
            campaign=campaign, is_active=True, sort_order__gt=boss.sort_order
        ).order_by("sort_order", "id").first()
        if nxt:
            prog.conquered = False
            prog.boss = nxt
            prog.damage_dealt = 0
            prog.total_hp = nxt.hp_total
        else:
            prog.conquered = True
    prog.save()
    return {
        "conquered": conquered,
        "base_damage": int(base),
        "gear_multiplier": round(gear_mult, 2),
        "boss_multiplier": round(vuln * buff_mult, 2),
        "total_damage": total,
        "boss_heal": heal,
        "tokens_won": tokens_won,
        "damage_dealt": prog.damage_dealt,
        "total_hp": prog.total_hp,
    }, None


def attack_boss(user, campaign, on_date=None, now=None):
    """Run one siege attack for a campaign. Returns (result, error)."""
    now = now or timezone.now()
    on_date = on_date or timezone.localdate(now)
    p = profile(user)
    refresh_stamina(p, user, now=now, on_date=on_date)
    if p.stamina <= 0:
        return None, "No stamina left today - it refills each morning."
    prog = CampaignProgress.objects.filter(user=user, campaign=campaign).first()
    if prog is None or prog.boss is None:
        prog, err = engage_boss(user, campaign, on_date=on_date)
        if err:
            return None, err
    if prog.conquered:
        return None, "Campaign conquered - no active boss."
    p.stamina -= 1
    p.save(update_fields=["stamina"])
    result, err = _resolve_attack(user, campaign, prog, now, on_date)
    result["stamina_left"] = p.stamina
    return result, None


def battle_state(user, now=None):
    """Full /battle/state payload."""
    now = now or timezone.now()
    on_date = timezone.localdate(now)
    p = profile(user)
    refresh_stamina(p, user, now=now, on_date=on_date)
    clear_expired_buffs(p, now=now)
    campaigns = []
    for campaign in Campaign.values:
        prog = CampaignProgress.objects.filter(
            user=user, campaign=campaign
        ).select_related("boss").first()
        boss = CampaignBoss.objects.filter(campaign=campaign, is_active=True).order_by(
            "sort_order", "id"
        ).first()
        ref = (prog.boss if prog and prog.boss else boss)
        hp = prog.total_hp if prog else (boss.hp_total if boss else 0)
        base_dmg = base_damage_for(campaign, user, on_date) + additive_bonus(p, user, campaign, on_date=on_date)
        gear_mult = total_gear_multiplier(p, user, campaign, on_date=on_date)
        vuln = boss_vulnerability(ref, campaign) if ref else 1.0
        buff_mult = active_buff_multiplier(p, campaign, on_date)
        est_damage = int(base_dmg * gear_mult * vuln * buff_mult)
        dealt = prog.damage_dealt if prog else 0
        remaining = max(0, hp - dealt)
        conquered = prog.conquered if prog else False
        engaged = bool(prog and prog.boss)
        attacks = None
        if engaged and not conquered and est_damage > 0:
            attacks = (remaining + est_damage - 1) // est_damage
        campaigns.append({
            "campaign": campaign,
            "label": Campaign(campaign).label if campaign else campaign,
            "boss": {
                "slug": ref.slug if ref else None,
                "name": ref.name if ref else None,
                "icon": ref.icon if ref else None,
            },
            "sort_order": int(prog.boss.sort_order) if prog and prog.boss else 0,
            "damage_dealt": dealt,
            "total_hp": hp,
            "remaining_hp": remaining,
            "conquered": conquered,
            "engaged": engaged,
            "today_base_damage": base_dmg,
            "gear_multiplier": round(gear_mult, 2),
            "boss_multiplier": round(buff_mult * vuln, 2),
            "vulnerability": vuln,
            "est_damage_per_attack": est_damage,
            "attacks_to_win": attacks,
        })
    return {
        "wallet": wallet_dump(p),
        "streak": user.streak,
        "campaigns": campaigns,
    }


def _campaign_peers(user):
    """Self + friends + flockmates (docs/17 #33 per-campaign siege scope)."""
    from .social import friends_of, membership_of

    peer_ids = {user.pk}
    for friend in friends_of(user):
        peer_ids.add(friend.pk)
    membership = membership_of(user)
    if membership is not None:
        for m in membership.flock.memberships.select_related("user"):
            peer_ids.add(m.user.pk)
    return peer_ids


def battle_leaderboard(user, campaign, limit=20, now=None):
    """docs/17 #33 - rank siege damage dealt to the *current* boss among
    friends / flock. Uses ``BattleLog.boss`` so only damage that actually hit
    the engaged boss counts.

    Returns a ranked leaderboard (most damage first) scoped to the requester's
    friends + flockmates (+ themselves), ready for the ``leagues.js`` rank-row
    UI, plus the requester's own rank / damage.
    """
    now = now or timezone.now()
    prog = CampaignProgress.objects.filter(user=user, campaign=campaign).first()
    if prog is not None and prog.boss is not None:
        boss = prog.boss
    else:
        boss = CampaignBoss.objects.filter(
            campaign=campaign, is_active=True
        ).order_by("sort_order", "id").first()
    if boss is None:
        return {
            "campaign": campaign,
            "label": Campaign(campaign).label,
            "boss": None,
            "leaderboard": [],
            "my_rank": None,
            "my_damage": 0,
            "peer_count": 0,
        }

    peer_ids = _campaign_peers(user)
    rows = list(
        BattleLog.objects.filter(boss=boss, user_id__in=peer_ids)
        .values("user_id", "user__username", "user__avatar")
        .annotate(damage=Sum("total_damage"))
        .order_by("-damage")
    )

    leaderboard = []
    my_rank = None
    my_damage = 0
    for idx, row in enumerate(rows):
        is_you = row["user_id"] == user.pk
        # Ties share a rank; otherwise rank == position + 1.
        rank = (
            leaderboard[-1]["rank"]
            if leaderboard and leaderboard[-1]["damage"] == row["damage"]
            else idx + 1
        )
        entry = {
            "rank": rank,
            "username": row["user__username"],
            "avatar": row["user__avatar"],
            "damage": row["damage"] or 0,
            "is_you": is_you,
        }
        leaderboard.append(entry)
        if is_you:
            my_rank = rank
            my_damage = entry["damage"]
    leaderboard = leaderboard[:limit]

    return {
        "campaign": campaign,
        "label": Campaign(campaign).label,
        "boss": {
            "slug": boss.slug,
            "name": boss.name,
            "icon": boss.icon,
        },
        "leaderboard": leaderboard,
        "my_rank": my_rank,
        "my_damage": my_damage,
        "peer_count": len(peer_ids),
    }


def battle_history(user, campaign):
    """docs/17 #34 - browsable siege diary: per-boss conquest + halved milestones
    derived from the user's ``BattleLog`` rows for a campaign.

    Each boss the player has actually attacked becomes its own diary group, so a
    "hemi" (50%-crossed) run and a completed conquest are visibly distinguishable
    from ordinary chipping. Bosses are ordered most-recently-active first; attacks
    within a group are chronological.
    """
    logs = (
        BattleLog.objects.filter(user=user, campaign=campaign, boss__isnull=False)
        .select_related("boss")
        .order_by("created_at")
    )
    # Group logs by boss, preserving first-seen insertion order for stable sort.
    by_boss = {}
    for log in logs:
        by_boss.setdefault(log.boss_id, {"boss": log.boss, "logs": []})[
            "logs"
        ].append(log)

    bosses = []
    for boss_id, group in by_boss.items():
        boss = group["boss"]
        entries = []
        total = 0
        halved = False
        conquered = False
        for log in group["logs"]:
            total += log.total_damage
            if not halved and boss and boss.hp_total > 0 and total >= (boss.hp_total * 0.5):
                halved = True
            if log.tokens_won > 0:
                conquered = True
            entries.append(
                {
                    "id": log.pk,
                    "date": log.date.isoformat(),
                    "total_damage": log.total_damage,
                    "boss_heal": log.boss_heal,
                    "tokens_won": log.tokens_won,
                    "created_at": log.created_at.isoformat(),
                }
            )
        last_activity = group["logs"][-1].created_at
        bosses.append(
            {
                "boss_id": boss_id,
                "slug": boss.slug if boss else None,
                "name": boss.name if boss else None,
                "icon": boss.icon if boss else None,
                "hp_total": boss.hp_total if boss else 0,
                "total_damage": total,
                "halved": halved,
                "conquered": conquered,
                "attacks": entries,
                "last_activity": last_activity.isoformat(),
            }
        )

    # Most recently engaged boss first.
    bosses.sort(key=lambda b: b["last_activity"], reverse=True)
    # Trim verbose attack lists unless requested - keep the diary browsable.
    return {
        "campaign": campaign,
        "label": Campaign(campaign).label,
        "bosses": bosses,
    }

# ---------------------------------------------------------------------------
# PvP gyms - docs/15 §5.5
# ---------------------------------------------------------------------------
def _consistency_xp(user, days=PVP_CONSISTENCY_WINDOW_DAYS, now=None):
    now = now or timezone.now()
    since = now - timedelta(days=days)
    return XPLedger.objects.filter(user=user, created_at__gte=since).aggregate(
        s=Sum("amount")
    )["s"] or 0


def attacker_power(user, now=None):
    """Sum over every campaign of (7-day consistency x equipped multiplier)."""
    now = now or timezone.now()
    p = profile(user)
    consistency = _consistency_xp(user, now=now)
    on_date = timezone.localdate(now)
    total = 0.0
    for campaign in Campaign.values:
        total += consistency * total_gear_multiplier(p, user, campaign, on_date=on_date) \
            + additive_bonus(p, user, campaign, on_date=on_date)
    return total


def power_breakdown(user, now=None):
    """Human-readable power audit for the PvP screen.

    Power = 7-day XP consistency x each equipped item's multiplier, summed over
    every campaign. Returns the total plus the inputs so the UI can explain it.
    """
    now = now or timezone.now()
    p = profile(user)
    on_date = timezone.localdate(now)
    consistency = _consistency_xp(user, now=now)
    gear = UserGear.objects.filter(
        user=user, equipped_slot__isnull=False, gear_def__is_consumable=False
    ).select_related("gear_def")
    equipped = []
    for g in gear:
        gd = g.gear_def
        gate = True
        if gd.effect_type == "synergy":
            gate = _buff_gate_passes(gd, user, on_date=on_date)
        equipped.append({
            "name": gd.name,
            "rarity": g.rarity,
            "effect_type": gd.effect_type,
            "effect_domain": gd.effect_domain,
            "effect_value": gd.effect_value,
            "active": gate,
        })
    per_campaign = {}
    total = 0.0
    for campaign in Campaign.values:
        mult = total_gear_multiplier(p, user, campaign, on_date=on_date)
        bonus = additive_bonus(p, user, campaign, on_date=on_date)
        contrib = consistency * mult + bonus
        per_campaign[campaign] = round(contrib, 2)
        total += contrib
    return {
        "power": round(total, 2),
        "consistency": round(consistency, 2),
        "equipped": equipped,
        "per_campaign": per_campaign,
    }


def _element_from_loadout(user):
    """Derive the attacker's element from equipped gear effect_domain."""
    domains = set(
        UserGear.objects.filter(
            user=user, equipped_slot__isnull=False, gear_def__is_consumable=False
        ).values_list("gear_def__effect_domain", flat=True)
    )
    for d in ("endurance", "strength", "nutrition", "hydration", "recovery"):
        if d in domains:
            return d
    return None


def set_defense(user, terrain=None, name=None, now=None):
    """Snapshot a player's defensive loadout + consistency into their Gym."""
    now = now or timezone.now()
    gym, _ = Gym.objects.get_or_create(owner=user)
    if name:
        gym.name = name
    if terrain in ELEMENT_WHEEL:
        gym.terrain = terrain
    snapshot = {"consistency": _consistency_xp(user, now=now), "terrain": gym.terrain}
    gear = UserGear.objects.filter(
        user=user, equipped_slot__isnull=False, gear_def__is_consumable=False
    ).select_related("gear_def")
    snapshot["loadout"] = [g.gear_def.slug for g in gear]
    gym.defense_snapshot = snapshot
    gym.save()
    return gym


def attack_gym(attacker, gym, now=None):
    """Instant async gym battle. Returns (result, error)."""
    now = now or timezone.now()
    snap = gym.defense_snapshot or {}
    a_power = attacker_power(attacker, now=now)
    d_power = float(snap.get("consistency", 0) or 0)
    wheel_bonus = PVP_AGGRESSOR_WIN_EDGE
    attacker_element = _element_from_loadout(attacker)
    if attacker_element and ELEMENT_WHEEL.get(attacker_element) == gym.terrain:
        wheel_bonus *= 1.10
    final_a = a_power * wheel_bonus
    did_win = final_a > d_power
    if did_win:
        GymOccupation.objects.update_or_create(
            gym=gym,
            defaults={
                "occupant": attacker,
                "held_until": now + timedelta(hours=GYM_HOLD_WINDOW_HOURS),
                "last_token_paid": None,
            },
        )
    PvPMatch.objects.create(
        attacker=attacker, gym=gym, defender=gym.owner,
        attacker_power=round(final_a, 2), defender_power=round(d_power, 2),
        did_win=did_win, token_stake=0,
    )
    p = profile(attacker)
    if did_win:
        p.pvp_wins += 1
    else:
        p.pvp_losses += 1
    p.save(update_fields=["pvp_wins", "pvp_losses"])
    return {
        "did_win": did_win,
        "attacker_power": round(final_a, 2),
        "defender_power": round(d_power, 2),
        "winner": attacker.username if did_win else gym.owner.username,
        "stake": 0,
    }, None


def pay_gym_yields(now=None):
    """Daily idempotent passive token yield for current Gym holders."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    paid = 0
    for occ in GymOccupation.objects.filter(held_until__gte=now).select_related("occupant"):
        if occ.last_token_paid == today:
            continue
        award_tokens(occ.occupant, GYM_TOKEN_YIELD_BASE)
        occ.last_token_paid = today
        occ.save(update_fields=["last_token_paid"])
        paid += 1
    return paid


def pvp_state(user, now=None):
    """Full /pvp/state payload."""
    now = now or timezone.now()
    gym = Gym.objects.filter(owner=user).first()
    my_turf = GymOccupation.objects.filter(occupant=user).select_related("gym").first()
    attackable = []
    for g in Gym.objects.filter(is_active=True).exclude(owner=user).select_related("owner"):
        attackable.append({
            "id": g.pk, "name": g.name, "owner": g.owner.username,
            "terrain": g.terrain,
            "defender_power": round(float((g.defense_snapshot or {}).get("consistency", 0) or 0), 2),
        })
    matches = [
        {
            "attacker": m.attacker.username,
            "defender": m.defender.username,
            "did_win": m.did_win,
            "attacker_power": m.attacker_power,
            "defender_power": m.defender_power,
        }
        for m in PvPMatch.objects.filter(attacker=user).select_related("attacker", "defender")[:10]
    ]
    return {
        "me": power_breakdown(user, now=now),
        "my_gym": {
            "id": gym.pk, "name": gym.name, "terrain": gym.terrain,
            "defense_set": bool(gym.defense_snapshot),
            "defense_power": round(float((gym.defense_snapshot or {}).get("consistency", 0) or 0), 2),
        } if gym else None,
        "my_turf": {
            "gym": my_turf.gym.name, "held_until": my_turf.held_until.isoformat(),
        } if my_turf else None,
        "attackable": attackable,
        "matches": matches,
    }

# ---------------------------------------------------------------------------
# Scrap economy (docs/16): recycle gear to scraps, spend in the rotating shop
# ---------------------------------------------------------------------------
def scrap_value(rarity):
    """Scraps yielded per unit of a given rarity."""
    return SCRAP_VALUE_BY_RARITY.get(rarity, SCRAP_VALUE_BY_RARITY[Rarity.COMMON])


def _scrap_shop_weekday(now=None):
    now = now or timezone.now()
    return timezone.localdate(now).weekday()


@transaction.atomic
def recycle_gear(user, gear_id, quantity=None):
    """Recycle a UserGear stack (or part of it) into scraps.

    Returns (ok, error, gain). Removes the recycled quantity and credits
    ``quantity * scrap_value(rarity)`` scraps to the user's wallet.
    """
    p = profile(user)
    ug = UserGear.objects.select_for_update().filter(pk=gear_id, user=user).first()
    if ug is None:
        return False, "Item not found.", 0
    qty = int(quantity or 1)
    if qty < 1 or qty > ug.quantity:
        return False, "Invalid quantity.", 0
    gain = scrap_value(ug.rarity) * qty
    p.scraps += gain
    p.save(update_fields=["scraps"])
    ug.quantity -= qty
    if ug.quantity <= 0:
        ug.delete()
    else:
        ug.save(update_fields=["quantity"])
    return True, None, gain


def scrap_shop_state(now=None):
    """Rotating Scrap Shop offering for today (docs/16).

    Only items whose ``available_days`` mask contains today's weekday are shown.
    """
    now = now or timezone.now()
    weekday = _scrap_shop_weekday(now)
    items = []
    for it in ScrapShopItem.objects.filter(is_active=True).select_related("pack").order_by(
        "sort_order", "slug"
    ):
        days = it.available_days or list(range(7))
        if weekday not in days:
            continue
        items.append({
            "slug": it.slug,
            "name": it.name,
            "icon": it.icon,
            "description": it.description,
            "cost_scraps": it.cost_scraps,
            "reward_type": it.reward_type,
            "reward_value": int(it.reward_value or 0) if it.reward_type != ScrapShopItem.RewardType.PACK else None,
            "pack": it.pack.name if (it.reward_type == ScrapShopItem.RewardType.PACK and it.pack) else None,
            "pack_slug": it.pack.slug if (it.reward_type == ScrapShopItem.RewardType.PACK and it.pack) else None,
        })
    return {
        "weekday": WEEKDAY_NAMES[weekday],
        "offering": items,
    }


@transaction.atomic
def buy_scrap_item(user, slug, now=None):
    """Buy a Scrap Shop item with scraps. Only today's offerings can be bought.

    Returns (result, error) where result describes the granted reward.
    """
    now = now or timezone.now()
    weekday = _scrap_shop_weekday(now)
    item = ScrapShopItem.objects.filter(slug=slug, is_active=True).select_related("pack").first()
    if item is None:
        return None, "Scrap shop item not found."
    days = item.available_days or list(range(7))
    if weekday not in days:
        return None, "This item isn't on offer today."
    p = PlayerProfile.objects.select_for_update().get_or_create(user=user)[0]
    if p.scraps < item.cost_scraps:
        return None, "Not enough scraps."
    p.scraps -= item.cost_scraps
    result = {"cost_scraps": item.cost_scraps, "reward_type": item.reward_type}
    save_fields = ["scraps"]
    if item.reward_type == ScrapShopItem.RewardType.TOKENS:
        amount = int(item.reward_value or 0)
        p.tokens += amount
        save_fields.append("tokens")
        result.update({"tokens": amount})
    elif item.reward_type == ScrapShopItem.RewardType.STAMINA:
        amount = int(item.reward_value or 0)
        p.stamina = min(stamina_cap(p, user), p.stamina + amount)
        save_fields.append("stamina")
        result.update({"stamina": amount})
    elif item.reward_type == ScrapShopItem.RewardType.PACK:
        if item.pack is None:
            return None, "This scrap reward has no pack configured."
        ok, err, manifest = _run_pulls(user, item.pack, item.pack.draws, random.random)
        if not ok:
            return None, err
        result.update({"pack": item.pack.slug, "draws": len(manifest), "manifest": manifest})
    p.save(update_fields=save_fields)
    return result, None


# ---------------------------------------------------------------------------
# Daily tick (replaces tick_base_economy_daily) - docs/15 §9
# ---------------------------------------------------------------------------
def tick_combat_daily(now=None):
    """Daily token harvest + stamina refill + buff cleanup + gym yields."""
    now = now or timezone.now()
    stats = {"users": 0, "minted": 0, "gym_yields": 0}
    for p in PlayerProfile.objects.filter(user__is_active=True).select_related("user"):
        try:
            u = p.user
            stats["minted"] += daily_token_harvest(u, on_date=timezone.localdate(now))
            refresh_stamina(p, u, now=now)
            clear_expired_buffs(p, now=now)
            stats["users"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("tick_combat_daily failed for user %s", p.user.username)
    stats["gym_yields"] = pay_gym_yields(now=now)
    return stats

