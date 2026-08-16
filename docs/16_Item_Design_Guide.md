# 🗞️ Item Design & Scrap Economy Guide (docs/16)

This is the design guide for the **gear / item catalog** and the **Scrap economy**
that sits on top of the Phase 9 token/Gacha loop (see `docs/15`). It covers:

1. Every **item type** the engine understands (old + new).
2. The **JSON seed files** the game loads at boot (`config/seeds/*.json`).
3. How to author new items in a **Google Sheet** and export them with
   **`tools/code.gs`**.
4. The **Scrap currency** + rotating **Scrap Shop** (day-of-week offers).

---

## 1. Item types (`GearItemDef.effect_type`)

An item's behaviour is decided by its `effect_type`. Items are either
**equipment** (non-consumable, equipped into a loadout slot) or
**consumables** (`is_consumable=true`, used from the Shop with the **Use**
button).

| `effect_type` | Kind | What it does |
|---|---|---|
| `domain_multiplier` | Equipment | Multiplies that domain's siege/PvP damage by `effect_value` (e.g. `1.3`) |
| `synergy` | Equipment | Like `domain_multiplier`, but only active when last-night sleep efficiency ≥ `requires_sleep_efficiency` |
| `flat_bonus` | Equipment | **Bare stat increase** — adds `effect_value` flat damage points to `effect_domain` every attack |
| `scales_with` | Equipment | **Stat boost from another metric** — adds `effect_value × <metric>` to `effect_domain`; the metric is `effect_params.scales_from` (a campaign domain, or `streak`/`xp`/`tokens`/`stamina`) |
| `stamina_cap` | Equipment | **Additional stamina** — raises the user's daily stamina ceiling by `effect_value` |
| `token_multiplier` | Equipment | **Extra coins** — multiplies the daily token dividend by `effect_value` |
| `double_domain` | Consumable | 2× damage for `effect_domain` for the rest of the day |
| `shield_overage` | Consumable | Prevents the nutrition "over-calories" boss heal for the day |
| `stamina_refund` | Consumable | **Earn back stamina** — instantly restores `effect_value` stamina (up to the cap) |
| `grant_tokens` | Consumable | **Extra coins** — instantly grants `effect_value` tokens |

### Where each field is used

| Field | Meaning |
|---|---|
| `slug` | Unique, URL-safe identifier (the join key everywhere) |
| `name` | Display name |
| `slot` | Equipment slot: `head` `chest` `left_hand` `right_hand` `legs` `feet` `accessory` — leave blank for a consumable |
| `rarity` | `common` `rare` `epic` `legendary` |
| `icon` | A **free** FontAwesome 6 class (no `fa-solid` prefix, no Pro-only names like `fa-helmet-battle`) |
| `effect_type` | One of the table above |
| `effect_domain` | A campaign domain: `cardio` `strength` `nutrition` `hydration` `sleep` (blank for global effects) |
| `effect_value` | Numeric magnitude (multiplier, flat points, stamina, tokens…) |
| `effect_params` | JSON extras, e.g. `{"scales_from":"strength"}` for `scales_with` |
| `requires_sleep_efficiency` | 0–1 gate for `synergy` (and respected by `scales_with`) |
| `pack` | Which `GearPackDef` can drop it (blank = catalog/generic-crate only) |
| `weight` | Relative drop weight inside its pack |
| `is_consumable` | `true` ⇒ uses the Shop **Use** flow, stacks by `max_stack` |
| `max_stack` | Stack cap for consumables (default 9) |
| `description` | What the player sees in the item detail popup |
| `is_active` | `true` to drop / be visible |
| `sort_order` | Ordering in the inventory |

---

## 2. JSON seed files (not built into Python)

The seed data lives in **`config/seeds/`** and is loaded at seeding time by
`core/management/commands/create_demo_accounts.py` (idempotent `get_or_create`):

| File | Model | Loaded as |
|---|---|---|
| `config/seeds/packs.json` | `GearPackDef` | `DEFAULT_PACKS` |
| `config/seeds/gear_items.json` | `GearItemDef` | `DEFAULT_GEAR` |
| `config/seeds/scrap_shop.json` | `ScrapShopItem` | `DEFAULT_SCRAP_SHOP` |
| `config/seeds/campaign_bosses.json` | `CampaignBoss` | `DEFAULT_CAMPAIGN_BOSSES` |
| `config/seeds/boss_configs.json` | `BossConfig` | `DEFAULT_BOSS_CONFIGS` |
| `config/seeds/challenges.json` | `Challenge` | `DEFAULT_CHALLENGES` |
| `config/seeds/badges.json` | `BadgeDef` | `BADGE_CATALOG` (loaded by `core/services/badges.py`) |

> Badges are the one exception to the seeder: they are seeded by
> `core.services.badges.sync_badge_defs()` (invoked from `/api/v1/badges/` and the
> tests), which reads the same `config/seeds/badges.json`, so adding a badge there
> needs no re-run of `create_demo_accounts`.

```powershell
# After editing any config/seeds/*.json, re-build the catalog:
.venv\Scripts\python manage.py create_demo_accounts
```

Because seeding uses `get_or_create(slug=…, defaults=…)`, adding a **new**
slug to a JSON file and re-running is always safe. For an **already-seeded**
slug, `get_or_create` leaves the existing row untouched — so edit it in the
Django admin, or delete the row (or recreate the DB with `docker compose down -v`)
and re-seed (see the main **README → Seeding the config with custom data**).
---

## 3. Authoring items in a Google Sheet + exporting with `tools/code.gs`

### 3.1 Set up the spreadsheet

Create a Google Sheet with **two tabs** named exactly **`GearItems`** and
**`ScrapShop`**. The **first row** of each tab is a header of field names (from
the JSON schema above). Column order is irrelevant — the exporter matches names.

**`GearItems` tab** — one row per item. Recommended columns:

| slug | name | slot | rarity | icon | effect_type | effect_domain | effect_value | effect_params | requires_sleep_efficiency | pack | weight | is_consumable | max_stack | description | is_active | sort_order |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stone_grip_gauntlets | Stone-Grip Gauntlets | left_hand | rare | fa-hand-fist | flat_bonus | strength | 25 | | | iron_roost | 35 | no | | Adds fierce flat Strength damage. | yes | 200 |
| cross_training_band | Cross-Training Band | right_hand | rare | fa-bandage | scales_with | cardio | 0.25 | {"scales_from":"strength"} | | cardio_storm | 30 | no | | Gains 25% of Strength damage for Cardio. | yes | 201 |
| adrenaline_shot | Adrenaline Shot | | rare | fa-syringe | stamina_refund | | 2 | | | alchemist_pack | 30 | yes | 9 | Refills 2 stamina instantly. | yes | 205 |

Notes:
- `effect_params` is a JSON string in the cell, e.g. `{"scales_from":"strength"}`.
- `available_days` (ScrapShop) is a comma list like `0,2,4` (0=Mon … 6=Sun);
  leave blank for **every day**.

**`ScrapShop` tab** — one row per rotating deal. Columns:

| slug | name | icon | description | cost_scraps | available_days | reward_type | reward_value | pack | is_active | sort_order |
|---|---|---|---|---|---|---|---|---|---|---|
| scrap_stam_refill | Adrenaline Canister | fa-bolt | Refills 2 stamina. | 40 | 0,2,4 | stamina | 2 | | yes | 20 |
| scrap_pack_iron | Iron Roost Crate | fa-box | A Strength pack draw. | 120 | 1,3 | pack | 0 | iron_roost | yes | 30 |

`reward_type` is one of `tokens` / `stamina` / `pack`. For `pack`, set the `pack`
cell to the slug of the `GearPackDef` to draw from.

### 3.2 Create the Apps Script and export

1. In the sheet: **Extensions → Apps Script**.
2. Replace the default `Code.gs` with the contents of **`tools/code.gs`** and save.
3. From the script, run **`exportAllJson()`** (or `exportItemsJson()` /
   `exportScrapShopJson()` individually). Grant permissions when prompted.
4. **View → Logs** and copy each printed JSON blob.
   - Paste the **`GearItems`** result into `config/seeds/gear_items.json`.
   - Paste the **`ScrapShop`** result into `config/seeds/scrap_shop.json`.
5. Back in the repo:

```powershell
.venv\Scripts\python manage.py create_demo_accounts
```

The exporter coerces types for you (numbers, booleans, JSON strings, weekday
lists) and skips blank rows / rows without a `slug`. If a header name is
misspelled the field is quietly omitted, so double-check against §1 / §3.1.

---

## 4. Scrap currency & the rotating Scrap Shop

Recycling any owned, **unequipped** item converts it to **scraps**
(`PlayerProfile.scraps`). Scrap value scales with rarity:

| Rarity | Scraps per unit |
|---|---|
| `common` | 5 |
| `rare` | 15 |
| `epic` | 40 |
| `legendary` | 100 |

Where it plugs in:
- **Recycle**: `POST /api/v1/scrap/recycle {"gear_id", "quantity"}` — removes the
  item (or `quantity` of its stack) and credits scraps. Equipped gear must be
  unequipped first.
- **Scrap Shop state**: `GET /api/v1/scrap/shop/state` — returns today's offer.
- **Buy**: `POST /api/v1/scrap/shop/buy {"item_slug"}` — only today's offers can
  be bought; grants tokens, stamina, or a pack draw.

### Day-of-week rotation

Each `ScrapShopItem.available_days` is a JSON list of Python `date.weekday()`
ints (`0`=Mon … `6`=Sun). Only items whose list contains today are offered, so
the shop visibly rotates every day:

```json
{ "available_days": [0, 2, 4] }   // Mon / Wed / Fri only
{ "available_days": [] }          // every day
```

---

## 5. Backend wiring (for developers)

- **Models** — `core/models.py`: `GearItemDef.effect_params`, `PlayerProfile.scraps`,
  and the new `ScrapShopItem`.
- **Combat service** — `core/services/combat.py`:
  - `additive_bonus(...)` (flat + scales), `stamina_cap(...)`,
    `token_dividend_multiplier(...)`, extended `consume_consumable(...)`.
  - `scrap_value()`, `recycle_gear()`, `scrap_shop_state()`, `buy_scrap_item()`.
- **Views / URLs** — `core/views.py` + `core/urls.py` expose
  `/api/v1/scrap/recycle`, `/api/v1/scrap/shop/state`, `/api/v1/scrap/shop/buy`.
- **Front end** — `core/static/core/js/shop.js` renders the Recycle + Scrap Shop
  sections inside the existing Shop panel.
- **Admin** — `ScrapShopItem` and new fields are registered in `core/admin.py`.
- **Migrations** — run `manage.py makemigrations core`, `manage.py migrate`.

Validating a change:

```powershell
.venv\Scripts\python manage.py check
.venv\Scripts\python manage.py test core --settings=flamingo_fitness.test_settings
node --check core/static/core/js/*.js
```

