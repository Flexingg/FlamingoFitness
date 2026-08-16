# 🎇 Phase 9 Plan: Token, Gacha & Battle System (Replacing the Base Meta-Game)

> **STATUS: IN IMPLEMENTATION** — design for replacing the Phase 7 base-building
> meta-game ("The Flamingo Club") with the *Flamingo Fitness Core Game*
> (Tokens → Gacha Shop → Loadout → PvE Boss Sieges → PvP Gym Battles).
>
> **Approved decisions (owner answers, 2026-08-15):**
> - 🔥 **The base game is RIPPED OUT entirely** — no deprecation, no migration
>   backfill. `BaseResource`, `BaseBuildingDef`, `BaseBuilding`, the `/base/*`
>   endpoints, `base.js`, the "Base" nav tab and `tick_base_economy_daily` are
>   deleted. The owner will rebuild the database wholesale (`docker compose
>   down -v`) since they are the only beta user, so no data preservation is
>   needed.
> - 🧮 Because the `materials` / `energy` / `time_speedups` fields are removed,
>   every remaining reward that paid them is **converted to Tokens now** so the
>   build stays green: **1 Token per 10 time_speedups**, **1 Token per 20
>   materials** (per docs/13 league/challenge rewards).
> - 🏋️ The existing **PR Boss (`BossConfig`) stays standalone**. A **"PR
>   Challenge"** button will be added to the dashboard linking to the PR Boss
>   panel (frontend step).
> - 🏟️ **Gyms are defended by a single player** for now; "Flock defense" is a
>   documented future extension (docs/12 idea #3/#4).
> - ⚡ **Energy → Stamina.** The rest-day bonus remains a **+2 stam*** rest-day
>   bonus (preserves the docs/09 "rest day = recharge" fantasy).
>
> **Grounding:** every feature reuses already-shipped Flamingo Fitness systems
> (docs/00–14). The real-world-data → damage pipeline reuses
> `RawActivityLog → XPLedger → SkillTree` (`core/services/gamification.py`);
> the token wallet replaces the base economy (`core/services/combat.py`);
> dynamic gacha odds are driven by `User.streak`; PvP reuses
> `Friendship`/`Flock` and the weekly `XPLedger` aggregation.
>
> **AI Context:** follow the established conventions — models in
> `core/models.py` + numbered migration `0009`; service modules re-exported
> from `core/services/__init__.py` (docs/08 ImportError-500 lesson); lazy
> per-panel GET APIs + CSRF-guarded POSTs behind `@login_required`; seeding
> idempotent in `core/management/commands/create_demo_accounts.py`; validation
> loop `python manage.py test core` + `node --check`.

---

## 1. Overview & Goals

Today the app's money is a passive idle base: `materials` + `energy` +
`time_speedups` feed `BaseBuildingDef`/`BaseBuilding` timers and the `/base/*`
endpoints. This phase replaces that sandbox with a **combat RPG loop** where a
player's loggable real-world health data literally becomes their avatar's
attack power.

**The new core loop (docs/00 "Pull / Equip / Battle"):**

```text
track & game your habits       -> Tokens (daily dividend × streak) + base damage
                                    (your real data, piped through gamification)
spend Tokens in the Shop       -> Gacha pulls on themed Gear Packs
equip 1 item per Slot          -> Head / Body / Accessory loadout; multipliers
                                    & cross-domain synergies
PvE Boss Sieges                -> chip a huge domain boss across many days;
                                    weaknesses/vulnerabilities drive strategy
PvP Gym Battles (async)        -> defend a Gym with your loadout + 7-day
                                    consistency; attack others for their turf
hold a Gym                     -> passive Token generation (territory reward)
```

**What is removed vs. what stays:**

| Removed (Phase 7 base) | Replacement (Phase 9) |
|---|---|
| `BaseResource` (materials/energy/time_speedups/blueprints/active_buffs) | `PlayerProfile` (`tokens` + `stamina` + buffs) |
| `BaseBuildingDef` / `BaseBuilding` | `GearItemDef` / `UserGear` (catalog + owned items) |
| `production_plan` / building synergies | `combat.compute_attack` / gear synergies |
| `/base/*` (8 endpoints) | `/battle/*`, `/shop/*`, `/loadout/*`, `/pvp/*` |
| `base.js` + Base bottom-nav tab | `battle.js` / `shop.js` / `loadout.js` / `pvp.js`; Base tab removed |
| `tick_base_economy_daily` beat | `tick_combat_daily` beat |

**Everything else ships as-is:** the five skill trees, `XPLedger`,
`DailyReadiness`, Leagues, Challenges, Flocks/Friends, Badges, Home Assistant,
and the base-damage pipeline (`process_log` / `summarize_*`).
---

## 2. The Domain-to-Campaign Map

The five PvE campaigns map 1:1 to the existing five modalities (and their
existing summarized data). "Base damage" is defined per domain from data the
app already stores + computes:

| Campaign (spec) | Modality | Base damage source (existing) |
|---|---|---|
| **Cardio** | `endurance` | `summarize_endurance` → `today.total_calories_burned` (kcal) |
| **Weightlifting** | `strength` | `summarize_strength` → `today.total_volume_lbs` |
| **Nutrition** | `nutrition` | protein adherence: `min(1.5, protein/protein_goal)` × `total_protein`; "perfect macro" bonus |
| **Hydration** | `hydration` | `summarize_hydration` → water oz; scaled by `water_goal` |
| **Sleep** | `recovery` | `summarize_sleep` → `sleep_hours` × `sleep_efficiency`% |
| **(PvP consistency)** | all | total XP in `XPLedger` over the last 7 days (`weekly_xp_map` style, docs/13) |

Each campaign's damage is a *numeric* compared against the boss's `hp_total`.
Big-integer hygiene matters: introduce a `BOSS_HP_SCALE` divisor so Cardio /
Nutrition /=10 and Weightlifting /=1000 keep numbers sane.

---

## 3. Rulebook Math (new constants for docs/03)

All tunables live as named constants at the top of the new
`core/services/combat.py` so they can be tuned without hunting literals.

### 3.1 Tokens (replaces materials)

| Constant | Value | Meaning |
|---|---|---|
| `XP_TO_TOKENS` | 10 | Daily dividend: 1 Token per 10 XP earned that day |
| `STREAK_TOKEN_CAP_DAYS` | 10 | Dividend streak multiplier saturates at 10 days |
| `STREAK_TOKEN_STEP` | 0.05 | Per-streak-day dividend multiplier step |
| `TOKEN_PERFECT_MACRO` | 25 | Replaces the old 10-material perfect-macro award |
| `TOKEN_PERFECT_HYDRATION` | 10 | Replaces the old +5-material hydrate award |
| `TOKEN_PVE_CONQUEST` | 150 | One-time reward for defeating a campaign boss |
| `TOKEN_BOSS_PR` | 100 | PR-boss reward |
| `TOKEN_TIME_SPEEDUP_RATE` | 10 | Conversion: 1 token per 10 time_speedups |
| `TOKEN_MATERIAL_RATE` | 20 | Conversion: 1 token per 20 materials |
| `TOKEN_STARTER` | 300 | New-user starting wallet |

**Daily dividend (replaces `xp_dividend` / `daily_harvest`):**
```
token_dividend(xp_today, streak) = int(xp_today / XP_TO_TOKENS) * streak_multiplier(streak)
```
Idempotent per `(user, date)` via `PlayerProfile.last_token_harvest`.
`streak_multiplier` is the existing pure helper (docs/09 §5.4).

### 3.2 Gacha (dynamic odds by streak)

| Constant | Value | Meaning |
|---|---|---|
| `PACK_PRICE_SIMPLE` | 100 | Simple pack cost (Tokens) |
| `PACK_PRICE_DELUXE` | 250 | Deluxe: 3 draws, guaranteed rare |
| `PACK_PRICE_LEGENDARY` | 500 | Legendary: 5 draws, guaranteed epic+ |
| `RARITY_WEIGHTS_BASE` | `{common:60, rare:28, epic:10, legendary:2}` | Base drop table |
| `EPIC_STREAK_STEP` | 0.20 | % points added to epic per logging-streak day past 7 |
| `LEGENDARY_STREAK_STEP` | 0.05 | % points added to legendary per logging-streak day past 7 |
| `STREAK_ODDS_START_DAY` | 7 | Day at which odds scaling begins |

**Dynamic odds:** `rarity_weights(streak)` = base weights shifted by streak;
for each streak day past `STREAK_ODDS_START_DAY`, add `EPIC_STREAK_STEP` to epic
and `LEGENDARY_STREAK_STEP` to legendary, draining the same from common.
Weights are normalized before the pull. Rolls use an injectable `rng` for tests.
A 30-day streak meaningfully shifts legendaries — "consistency pays."

### 3.3 Gear & Loadout

| Constant | Value | Meaning |
|---|---|---|
| `HEAD_SLOT` / `BODY_SLOT` / `ACCESSORY_SLOT` | `"head"`,`"body"`,`"accessory"` | Slot names (one item each) |
| `GEAR_MULT_POOL` | `{common:(1.0,1.2), rare:(1.2,1.5), epic:(1.5,2.0), legendary:(2.0,2.5)}` | Flat multiplier range per rarity |
| `SYNERGY_SLEEP_EFF` | 0.85 | Need ≥85% sleep efficiency for a Sleep-synergy legendary |
| `CONSUMABLE_MAX_STACK` | 9 | Per-consumable stack cap in `UserGear.quantity` |

**Slots:** exactly one piece per slot. `total_gear_multiplier(domain)` = product
of every equipped item whose `effect_type=="domain_multiplier"` and
`effect_domain==domain`, times active cross-domain synergies for that domain,
times active consumable buffs. Multipliers multiply (stacking stays satisfying).

**Synergies (spec: holistic lifestyle):** `effect_type="synergy"` gear has a
`requires_sleep_efficiency` gate; its multiplier applies *only when* last
night's `DailyReadiness`/`summarize_sleep` `sleep_efficiency >=` that gate.
Example legendary: **Gauntlets of Recharge** — 2.5× Weightlifting damage gated
on ≥85% sleep efficiency.

### 3.4 Consumables (temporary buffs)

| Constant | Value | Meaning |
|---|---|---|
| `BUFF_HOURS` | 24 | Consumable buff window (dated key in `PlayerProfile.active_buffs`) |

- **Pre-Workout Nectar** — `effect_type="double_domain"`, `effect_domain="cardio"`: ×2 today's Cardio damage.
- **Macro-Potion** — `effect_type="shield_overage"`: cancels the Nutrition boss's heal-on-overage for today.
- Consumables deduct `quantity` on `POST /shop/consume` and expire by stored date (idempotent cleanup).

### 3.5 PvE damage & boss mechanics

**Attack damage (one siege attack for a domain):**
```
attack_damage(domain) =
  base_damage(domain)               # today's real data, summarized §2
  * total_gear_multiplier(domain)   # loadout + synergies (§3.3)
  * boss_vulnerability(domain)      # ∋ {1.0 neutral, 2.0 weakness, 0.5 resisted}
  * active_buff_multiplier(domain)  # consumables (§3.4)
  - boss_heal_this_attack           # mechanic-driven
  , clamped ≥ 0 and int()ed.
```

| Constant | Value | Meaning |
|---|---|---|
| `BOSS_HP_SCALE` | `{cardio:10, strength:1000, nutrition:10, hydration:10, sleep:8}` | normalize big numbers |
| `STAMINA_PER_DAY` | 3 | Max siege attacks/day (per user) |
| `REST_DAY_STAMINA_BONUS` | 2 | Extra stamina granted on a `rest_day` |
| `BOSS_HEAL_OVERAGE` | 500 | Nutrition boss heal when calories exceed goal |

**Mechanics (from the spec, made concrete):**
- **One battle at a time per campaign**: a user engages exactly one boss per
  campaign (`CampaignProgress`), but can switch campaigns any time.
- **Multi-day sieges**: boss `hp_total` >> one day's damage; progress persists.
- **Front-loaded hydration**: a Hydration boss takes ×2 when ≥50% of the day's
  water was logged before noon (reads `water_intake_entries[].time`).
- **Nutrition boss self-heal**: if today's `nutrition` payload shows
  `calories > calorie_goal`, the boss heals `BOSS_HEAL_OVERAGE` HP — unless a
  *Macro-Potion* buff is active.
- **Conquest**: `damage_dealt >= hp_total` → `conquered` + `TOKEN_PVE_CONQUEST`,
  then auto-engage the next boss (or mark campaign complete).

### 3.6 PvP Gym Battles (async, element wheel)

| Constant | Value | Meaning |
|---|---|---|
| `ELEMENT_WHEEL` | `{"endurance":"strength","strength":"nutrition","nutrition":"hydration","hydration":"recovery","recovery":"endurance"}` | element → element it beats |
| `PVP_AGGRESSOR_WIN_EDGE` | 1.10 | Slight edge to the active attacker |
| `GYM_TOKEN_YIELD_BASE` | 20 | Tokens/day passively earned while holding a Gym |
| `GYM_HOLD_WINDOW_HOURS` | 24 | A conquered gym locks for 24h before re-take |
| `PVP_CONSISTENCY_WINDOW_DAYS` | 7 | Consistency window (weekly `XPLedger`) |

**Attack power:** `attack_power = Σ over domains of (7-day consistency ×
equipped multiplier for that domain)`, then apply the element wheel vs. the
defender Gym's terrain, then `PVP_AGGRESSOR_WIN_EDGE`.

**Defense:** each player sets a defensive loadout (current equipped gear + a
snapshot of their weekly/7-day XP). **Resolution is instant / asynchronous** —
matchup computed on the attacker's `POST`, exactly like the instantaneous
`BossConfig` math (docs/11 §3).

**Territory:** a conquered Gym belongs to the winner for `GYM_HOLD_WINDOW_HOURS`
and yields `GYM_TOKEN_YIELD_BASE`/day (idempotent daily, like the old tick).

---

## 4. Data Model Changes (`core/models.py` + migration `0009`)

The Phase 7 base models (`BaseResource`, `BaseBuildingDef`, `BaseBuilding`)
are **removed entirely** (owner rebuilds the DB).

### 4.1 Enum choices

```python
class Rarity(models.TextChoices):
    COMMON="common"; RARE="rare"; EPIC="epic"; LEGENDARY="legendary"
class GearSlot(models.TextChoices):
    HEAD="head"; BODY="body"; ACCESSORY="accessory"
class Campaign(models.TextChoices):   # maps to the existing 5 modalities
    CARDIO="cardio"; STRENGTH="strength"; NUTRITION="nutrition"
    HYDRATION="hydration"; SLEEP="sleep"     # sleep -> Modality.RECOVERY
class Element(models.TextChoices):    # PvP element wheel
    ENDURANCE="endurance"; STRENGTH="strength"; NUTRITION="nutrition"
    HYDRATION="hydration"; RECOVERY="recovery"
```

### 4.2 `PlayerProfile` (Token + stamina wallet)

```python
class PlayerProfile(models.Model):
    user = OneToOneField(User, CASCADE, related_name="combat_profile")
    tokens = PositiveIntegerField(default=TOKEN_STARTER)
    stamina = PositiveIntegerField(default=STAMINA_PER_DAY)
    stamina_updated_at = DateTimeField(null=True, blank=True)
    last_token_harvest = DateField(null=True, blank=True)
    active_buffs = JSONField(default=dict)  # {"cardio_double_date": "...", "shield_overage_date": "..."}
    total_conquests = PositiveIntegerField(default=0)
    pvp_wins = PositiveIntegerField(default=0)
    pvp_losses = PositiveIntegerField(default=0)
    created_at = DateTimeField(auto_now_add=True)
```

> `JSONField(default=dict)` must use the callable `dict` (docs/09 gotcha).

### 4.3 `GearItemDef` (admin catalog)

```python
class GearItemDef(models.Model):
    slug = SlugField(unique=True)
    name = CharField(80)
    slot = CharField(20, choices=GearSlot.choices, blank=True)
    rarity = CharField(20, choices=Rarity.choices)
    effect_type = CharField(30, default="domain_multiplier")
        # domain_multiplier | synergy | double_domain | shield_overage
    effect_domain = CharField(20, choices=Campaign.choices, null=True, blank=True)
    effect_value = FloatField(default=1.0)
    requires_sleep_efficiency = FloatField(null=True, blank=True)
    pack = FK("GearPackDef", null=True, blank=True, SET_NULL, related_name="items")
    weight = PositiveIntegerField(default=100)
    is_consumable = BooleanField(default=False)
    max_stack = PositiveIntegerField(default=1)
    icon = CharField(60, default="fa-helmet-battle")
    description = TextField(blank=True)
    is_active = BooleanField(default=True)
    sort_order = IntegerField(default=0)
    class Meta: ordering=["sort_order","slug"]
```

### 4.4 `GearPackDef` (themed packs)

```python
class GearPackDef(models.Model):
    slug = SlugField(unique=True)
    name = CharField(80)
    description = TextField(blank=True)
    icon = CharField(60, default="fa-box-open")
    price_tokens = PositiveIntegerField(default=100)
    draws = PositiveIntegerField(default=1)
    domains = JSONField(default=list)                      # targeted Campaign values
    guaranteed_min_rarity = CharField(20, choices=Rarity.choices, default="common")
    is_active = BooleanField(default=True)
    sort_order = IntegerField(default=0)
    class Meta: ordering=["sort_order","slug"]
```

### 4.5 `UserGear` (owned items / consumable stacks)

```python
class UserGear(models.Model):
    user = FK(User, CASCADE, related_name="gear")
    gear_def = FK(GearItemDef, CASCADE, related_name="owned")
    rarity = CharField(20, choices=Rarity.choices)
    quantity = PositiveIntegerField(default=1)
    obtained_at = DateTimeField(auto_now_add=True)
    equipped_slot = CharField(20, choices=GearSlot.choices, null=True, blank=True)
```

### 4.6 `CampaignBoss` (PvE bosses)

```python
class CampaignBoss(models.Model):
    campaign = CharField(20, choices=Campaign.choices)
    slug = SlugField(unique=True)
    name = CharField(80)
    icon = CharField(60, default="fa-dragon")
    hp_total = BigIntegerField(default=100_000)
    element = CharField(20, choices=Element.choices)
    weaknesses = JSONField(default=list)     # Campaign domains dealing 2x
    resistances = JSONField(default=list)    # Campaign domains dealing 0.5x
    mechanics = JSONField(default=dict)
        # {"front_load_water_noon": true, "heal_on_overage": true}
    is_active = BooleanField(default=True)
    sort_order = IntegerField(default=0)
    class Meta: ordering=["campaign","sort_order"]
```

### 4.7 `CampaignProgress` (multi-day siege state — one per user+campaign)

```python
class CampaignProgress(models.Model):
    user = FK(User, CASCADE, related_name="sieges")
    campaign = CharField(20, choices=Campaign.choices)
    boss = FK(CampaignBoss, null=True, blank=True, SET_NULL)
    damage_dealt = BigIntegerField(default=0)
    total_hp = BigIntegerField(default=0)
    conquered = BooleanField(default=False)
    engaged_at = DateTimeField(null=True, blank=True)
    class Meta:
        constraints=[UniqueConstraint(fields=["user","campaign"], name="unique_user_campaign")]
```

### 4.8 `BattleLog` (one attack row)

```python
class BattleLog(models.Model):
    user = FK(User, CASCADE, related_name="battle_logs")
    campaign = CharField(20, choices=Campaign.choices)
    date = DateField()
    base_damage = BigIntegerField(default=0)
    gear_multiplier = FloatField(default=1.0)
    boss_multiplier = FloatField(default=1.0)
    total_damage = BigIntegerField(default=0)
    boss_heal = BigIntegerField(default=0)
    tokens_won = PositiveIntegerField(default=0)
    created_at = DateTimeField(auto_now_add=True)
```

### 4.9 PvP: `Gym`, `GymOccupation`, `PvPMatch`

```python
class Gym(models.Model):
    owner = FK(User, CASCADE, related_name="gyms")
    name = CharField(80)
    terrain = CharField(20, choices=Element.choices, default=Element.STRENGTH)
    defense_snapshot = JSONField(default=dict)
    is_active = BooleanField(default=True)
    created_at = DateTimeField(auto_now_add=True)
    class Meta: constraints=[UniqueConstraint(fields=["owner"], name="unique_gym_owner")]

class GymOccupation(models.Model):
    gym = FK(Gym, CASCADE, related_name="occupations")
    occupant = FK(User, CASCADE, related_name="gym_turf")
    held_until = DateTimeField()
    last_token_paid = DateField(null=True, blank=True)

class PvPMatch(models.Model):
    attacker = FK(User, CASCADE, related_name="pvp_attacks")
    gym = FK(Gym, CASCADE, related_name="matches")
    defender = FK(User, CASCADE, related_name="pvp_defenses")
    attacker_power = FloatField(default=0.0)
    defender_power = FloatField(default=0.0)
    did_win = BooleanField(default=False)
    token_stake = PositiveIntegerField(default=0)
    created_at = DateTimeField(auto_now_add=True)
```

> `defense_snapshot` freezes the values used for instant async resolution so
> later gear changes can't retroactively flip a past match (the docs/13
> snapshot philosophy applied to `LeagueResult`).

---

## 5. Service Layer: `core/services/combat.py`

Mirror the existing module layout — every helper used from views/tasks/admin is
re-exported from `core/services/__init__.py` (docs/08 endurance-500 lesson).
Every time-sensitive function accepts `now=None`; saves use `update_fields`;
wallet mutations are `transaction.atomic` + `select_for_update`.

### 5.1 Wallet (`PlayerProfile`)
- `profile(user)` → get-or-create `PlayerProfile` (starts at `TOKEN_STARTER`).
- `award_tokens(user, amount)` / `spend_tokens(user, amount)` (atomic).
- `refresh_stamina(profile, user, now=None)` — daily refill to
  `STAMINA_PER_DAY` (+`REST_DAY_STAMINA_BONUS` when today is a rest day),
  overflow-safe, stamps `stamina_updated_at` (reuses the docs/09 overflow
  philosophy).
- `daily_token_harvest(user, on_date=None)` — idempotent via
  `last_token_harvest`, weights by `streak_multiplier`.
- `wallet_dump(profile)` → `{tokens, stamina, stamina_cap, ...}` — shared by
  `/dashboard/state` and `/battle/state` so the header badge never drifts.

### 5.2 Gacha
- `rarity_weights(streak)` (§3.2).
- `open_pack(profile, pack, user, rng=None)` — validate/spend tokens, roll
  `draws` items from the pack (weighted by `GearItemDef.weight`, filtered to
  `pack.domains`), honor `guaranteed_min_rarity`, create `UserGear` (consumables
  stack, capped at `max_stack`); return a draw manifest.

### 5.3 Loadout & combat math
- `total_gear_multiplier(profile, user, domain, on_date=None)` (§3.3) — reads
  equipped `UserGear` + synergies + active buffs.
- `base_damage_for(campaign, user, on_date=None)` — thin wrapper over the
  existing `summarize_*` helpers for that campaign's number, normalized by
  `BOSS_HP_SCALE`.
- `compute_attack(profile, user, campaign, boss, on_date=None)` → dict incl.
  `boss_vulnerability`, `boss_heal`, final `total_damage`.
- `clear_expired_buffs(profile, now=None)` — drop past dated buff keys.

### 5.4 PvE sieges
- `engage_boss(profile, user, campaign, on_date=None)` — `get_or_create`
  `CampaignProgress`; if not engaged, pick the current active campaign boss.
- `attack_boss(profile, user, campaign, on_date=None)` — validate stamina,
  deduct, `compute_attack`, persist `BattleLog`, decrement HP, apply heal
  mechanic, handle conquest (`TOKEN_PVE_CONQUEST`) and auto-advance.
- `battle_state(user, now=None)` — campaigns, engaged boss + progress, stamina,
  loadout summary.

### 5.5 PvP gyms
- `set_defense(user, terrain, name, now=None)` — snapshot equipped `UserGear`
  + 7-day XP into `Gym.defense_snapshot`.
- `attack_gym(attacker, gym, now=None)` — attacker power (7-day consistency +
  loadout + `ELEMENT_WHEEL` + edge); compare vs `defense_snapshot`; write
  `PvPMatch`; on win refresh `GymOccupation` (holder + `held_until`).
- `pay_gym_yields(now=None)` — daily idempotent `GYM_TOKEN_YIELD_BASE` per
  occupier while `held_until` is future and not yet paid.
- `pvp_state(user, now=None)` — my gym + defense, my turf, attackable gyms,
  match history.

### 5.6 Gamification hooks (additive, wrapped in try/except)
- In `gamification.py` replace the old material/speedup awards:
  `_handle_macro` → `award_tokens(user, TOKEN_PERFECT_MACRO)`;
  `_handle_hydration` → `award_tokens(user, TOKEN_PERFECT_HYDRATION)`;
  `_handle_strength` `pr:` branch → `award_tokens(user, TOKEN_BOSS_PR)`.
- The `base_xp_bonus_pct` scaling (docs/09 §5.9) is removed with the base game.
- Add `daily_token_harvest` to the new `tick_combat_daily` beat task (§9).

---

## 6. API Contracts (`core/views.py` + `core/urls.py`)

All under `/api/v1/`, session-auth, `@login_required`. POSTs are `@require_POST`
with a JSON body (the existing `_load_base_post_body` pattern); errors via
`_json_error(message, status)`. Every mutation returns a fresh snapshot so the
UI re-renders without a second fetch. `/dashboard/state` now returns
`"resources": {"tokens": ..., "stamina": ...}` instead of materials/energy.

| Endpoint | Body | Behavior |
|---|---|---|
| `GET /battle/state` | — | campaigns, engaged bosses + progress, stamina, loadout summary, active buffs |
| `GET /battle/campaign/{campaign}` | — | boss detail, HP bar, mechanics, today's damage preview |
| `POST /battle/engage` | `{"campaign"}` | engage a boss in that campaign (400 if already engaged) |
| `POST /battle/attack` | `{"campaign"}` | run an attack; returns result + updated HP/stamina; 400 no stamina/no boss |
| `GET /shop/state` | — | packs (price, draws, domains) + owned gear buckets + wallet |
| `POST /shop/open` | `{"pack_slug"}` | gacha pull; 400 insufficient tokens/unknown pack; manifest + wallet |
| `POST /shop/consume` | `{"gear_id"}` | use a consumable; 404 not owned; sets a dated buff |
| `GET /loadout/state` | — | equipped Head/Body/Accessory + candidates |
| `POST /loadout/equip` | `{"gear_id"}` | equip; auto-passes the previous item in that slot |
| `GET /pvp/state` | — | my gym/defense/turf, attackable gyms, match history |
| `POST /pvp/defend` | `{"terrain","name"}` | snapshot defense loadout + consistency |
| `POST /pvp/attack` | `{"gym_id"}` | instant async resolution; winner + token result |

The `/base/*` routes are removed. `core/urls.py`: `battle/state`,
`battle/campaign/<str:campaign>`, `battle/engage`, `battle/attack`,
`shop/state`, `shop/open`, `shop/consume`, `loadout/state`, `loadout/equip`,
`pvp/state`, `pvp/defend`, `pvp/attack`.

---

## 7. Frontend (Vanilla JS, Miami/Duolingo polish)

- `dashboard.html`: replace the `#nav-base` "Base" nav item with **Shop /
  Loadout / Battle / PvP** nav items; add `#shop-view`, `#loadout-view`,
  `#battle-view`, `#pvp-view` sections (back button + content container). Add a
  **"PR Challenge"** button linking to the existing PR Boss panel. CSRF meta
  tag already exists (docs/08).
- `core/static/core/js/shop.js` — **NEW**: `loadShop`/`renderShop`, open pack
  (POST), animate the draw + rarity colors; `node --check` after edits.
- `core/static/core/js/loadout.js` — **NEW**: equip/unequip, per-domain
  multiplier readout, synergy tooltips.
- `core/static/core/js/battle.js` — **NEW**: campaign list → boss detail with HP
  bar, "Attack" button (haptic `navigator.vibrate` synchronously before the
  fetch — docs/09 §11), consume-buff quick actions, mechanic banners.
- `core/static/core/js/pvp.js` — **NEW**: my gym/defense + attackable gyms +
  match results.
- `core/static/core/css/dashboard.css` — shop/loadout/battle/pvp cards, HP bars,
  rarity colors (common/rare/epic/legendary), confetti on conquest (reuse
  canvas-confetti + milestone toast, docs/09 §7.5).
- `core/static/core/js/dashboard.js` — expose `refreshDashboardState()`; header
  stat pills show Tokens + Stamina.
- **Remove** `base.js` script tag, `#nav-base`, `#base-view`; delete `base.js`.

### Patterns (the "learned the hard way" rules)
- Every POST sends `X-CSRFToken` from the meta tag (docs/08); test 403.
- Every controller reads the **real** payload keys from §6 — never copy a past
  controller and rename identifiers (docs/04 Endurance "water 0/0 oz" lesson).
- Haptics need a user gesture — call `navigator.vibrate` synchronously.
- Lazy per-panel fetch + `credentials: 'same-origin'`; surface `body.error`.

---

## 8. Admin, Seeding & Celery

### Admin
`core/admin.py`: register `PlayerProfile` (read-only-ish), `GearItemDef`,
`GearPackDef`, `UserGear`, `CampaignBoss`, `CampaignProgress`, `BattleLog`,
`Gym`, `GymOccupation`, `PvPMatch`. Remove `BaseResource`, `BaseBuildingDef`,
`BaseBuilding` registrations.

### Seeding (`create_demo_accounts.py`, idempotent `get_or_create`)
1. **GearPackDefs:** `starter_pack` (100t/1), `iron_roost` (100t, strength),
   `alchemist_pack` (250t/3, nutrition+hydration, guaranteed rare),
   `cardio_storm` (100t, cardio), `slumber_serum` (100t, sleep),
   `legendary_vault` (500t/5, guaranteed epic+).
2. **GearItemDef catalog:** a starter + rosters per pack; consumables
   **Pre-Workout Nectar** (`double_domain` cardio) and **Macro-Potion**
   (`shield_overage`); legendary synergy **Gauntlets of Recharge**
   (`synergy`, strength, `requires_sleep_efficiency=0.85`).
3. **CampaignBosses** per campaign (≥2 each): e.g. Cardio *The Ghastly
   Recliner*; Weightlifting *Sir Skip-a-Leg*; Nutrition *The Carbo-Hydra*
   (`heal_on_overage`); Hydration *The Dehydrator* (`front_load_water_noon`);
   Sleep *The Restless Wraith*.
4. Give `player1` `TOKEN_STARTER`, a starter loadout + 3 packs, and seed
   `Gym` + `defense_snapshot` for both demo users so PvP is alive on boot.
5. Stop seeding `BaseBuildingDef`/`BaseBuilding` demo instances.

### Celery (`core/tasks.py` + `settings.py` beat)
- **`tick_combat_daily`** (shared_task, `crontab(minute=10, hour=0)`):
  1. per user: `daily_token_harvest`, `refresh_stamina`, `clear_expired_buffs`;
  2. `pay_gym_yields`;
  3. lazily apply dated boss-heal mechanics.
  Idempotent by stored dates. Remove `tick_base_economy_daily` from
  `CELERY_BEAT_SCHEDULE`.
- (Optional) `close_gym_cooldowns` hourly to expire `GymOccupation.held_until`.

---

## 9. Deprecation / Removals Summary

- **Remove:** `BaseResource`, `BaseBuildingDef`, `BaseBuilding` models and
  their migrations' dependent code; `/base/*` endpoints + urls; `base.js`,
  `#base-view`, `#nav-base`; `tick_base_economy_daily`; `material`/`energy`/
  `time_speedup` stat explainers; `materials`/`energy` top-nav badge rewiring.
- **Convert now (build must stay green):** every remaining reward that paid
  `time_speedups`/`materials` → Tokens (`1 token / 10 speedups`,
  `1 token / 20 materials`). This includes league weekly rewards (docs/13
  §3.2) and the PR-boss reward.
- **Keep:** `BossConfig` PR Boss (standalone) + dashboard "PR Challenge"
  button; Leagues/Challenges/Flocks/Badges/Home Assistant; the five skill trees
  and the `summarize_*` pipeline.
- **Follow-ups (docs/08):** Flock-defense Gyms; converting any remaining
  `time_speedups` references found in older `LeagueResult.reward` payloads when
  the DB is rebuilt.

---

## 10. Step-by-Step Coding Plan (Step 37+)

- **Step 37 — Models.** Add §4 models; remove base models; migration `0009`;
  register admin. `manage.py check` + existing suite green (minus the base
  tests that are removed).
- **Step 38 — Services.** `combat.py` (§5) + re-exports; rewires
  `gamification.py` awards to tokens; remove `base_xp_bonus_pct` scaling.
- **Step 39 — Views & API.** §6 endpoints + urls; remove `/base/*`. TestClient
  walkthrough of every happy path + documented 400/404 + CSRF-403.
- **Step 40 — Seeding & Celery.** §8 seeds + `tick_combat_daily` beat; remove
  `tick_base_economy_daily`.
- **Step 41 — Frontend.** `shop.js`/`loadout.js`/`battle.js`/`pvp.js`,
  template nav replacement, remove `base.js`, CSS; add "PR Challenge" button.
- **Step 42 — Tests & docs.** `TokenEconomyTests`, `GachaMathTests`,
  `LoadoutMathTests`, `BattleFlowTests`, `PvPFlowTests`, `CombatAPITests`
  (+CSRF); full suite green; `node --check`; docs sweep
  (`00/01/02/03/07/08/12/13/14` + this file).

### Definition of Done
1. The bottom-nav "Base" tab is gone; **Shop / Loadout / Battle / PvP** tabs
   drive the core loop: track → earn tokens → pull packs → equip 3 slots →
   siege a boss → defend a gym.
2. `player1` (demo) opens with 300 tokens, a starter loadout, three packs, and a
   live gym; a demo siege shows an HP bar that moves on attack.
3. Streak lengths visibly change gacha odds and the daily token dividend;
   sleep-efficiency-gated legendaries explain their gate in the UI.
4. PvP resolves instantly and holding a Gym pays passive tokens once/day,
   idempotently.
5. `docs/07`/`docs/08`/this file reflect reality; no silent reward-value drift.

