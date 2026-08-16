# 🦩 Flamingo Fitness

A Duolingo-style fitness web app that turns health data (sleep, nutrition,
weightlifting, Peloton, Garmin) into gamified behavior: readiness-adjusted
streaks, modality skill trees, a base-building meta-game, and asymmetric
leaderboards.

Built strictly on **Django + PostgreSQL + Redis/Celery** with a **vanilla JS
PWA** frontend (no React/Vue/Node). See `docs/` for the full spec.

---

## Quick Start (Docker)

```powershell
# 1. Configure environment (or copy the sample)
Copy-Item .env.example .env
#    ...edit .env with real secret key / passwords if needed

# 2. Build & start the whole stack
docker compose up --build

# 3. Seed demo users + data (admin/player1) inside the web container
#    Accounts are also auto-created on every web container startup.
docker compose exec web python manage.py seed_demo
```

Then open:

- Dashboard → http://localhost:8000  (log in as `admin` / `adminpass123`
  or `player1` / `playerpass123`; it redirects through `/admin/login/`)
- Admin panel → http://localhost:8000/admin

Services started by compose: `db` (Postgres 15), `redis` (7), `web`
(Gunicorn), `celery_worker`, `celery_beat`.

> Note: `db` is published on host port **5433** (not 5432) to avoid clashing
> with any local Postgres you may already have running.

---

## Accounts & SparkyFitness linking

- **Sign up** at `/signup/` (username + password → auto-login).
- **Log in / out** at `/login/` and `/logout/`.
- **Profile / link providers** at `/profile/` (also linked from the
  dashboard's bottom nav).

To link your **SparkyFitness** account (docs/10):
1. Go to `/profile/`.
2. Paste your `fit.randalls.cc` API key into the form and hit **Link & Sync**.
3. The app immediately polls SparkyFitness and dumps sleep + nutrition into
   `RawActivityLog`, converts them to XP (perfect macros → +50 Nutrition XP
   and +10 Base Materials), and keeps syncing every 4 hours via Celery Beat.

**No API key?** Leave it blank — the client returns realistic demo data only
when the `DEMO` environment variable is set to `true` (off by default). With
`DEMO=False` the dashboard shows the **Link SparkyFitness** CTA instead.

> The SparkyFitness client targets the `fit.randalls.cc/api` endpoints
> (`/sleep/analytics`, `/food-entries/range/...`, `/goals/by-date/...`) with
> defensive parsing, so unknown field shapes degrade gracefully instead of
> crashing a poll.

---

## 🏅 Achievement badges

Badges are lightweight, derived achievements (Roadmap idea #5). Nothing new
is ingested — every badge's earn condition is a small **rule** evaluated
against data the app already stores (streak, activity logs, skill trees, base
level, blueprints, lifetime XP). Grants happen **lazily** whenever the
dashboard calls `GET /api/v1/badges/`, and a badge is never granted twice.

Each badge carries a difficulty-scaled number of **Badge Points** (5 = trivial
→ 100 = very hard); the panel header shows both the badge count and the
points total (`earned / overall`). Badge tiles are **clickable**:

- **Earned badge** → detail view with what the badge means and the date it
  was achieved.
- **Locked badge** → detail view with a progress bar plus a "what is left"
  hint, e.g. *"Current streak: 4 of 10 days."*

### Creating a new badge in the admin console (no code needed)

1. Log in to the admin panel → **Badge defs** → **Add badge def**.
2. Fill in the display fields:
   - **Key** — unique slug used internally, e.g. `marathon_month`.
   - **Name / Description** — the title and the "what it means" text players
     see in the detail view.
   - **Icon** — any FontAwesome 6 class without the `fa-solid` prefix, e.g.
     `fa-person-running`.
   - **Category** — free-form grouping label (Streaks, Base, Skill, Habits…).
   - **Points** — Badge Points for the badge; scale with difficulty
     (5 trivial · 10 easy · 25–50 medium · 75–100 hard).
   - **Sort order / Is active** — panel ordering and an on/off switch.
3. Write the earn condition in the **Rule** field as a single JSON object
   (reference table below), e.g. `{"type": "streak", "minimum": 30}`. The
   admin form lists all supported rule types under the field.
4. **Save** — that's it. No deploy or code change is needed: the badge
   appears in every player's Badges panel on their next dashboard load and is
   granted automatically the first time its rule passes.

> Tip: to hide a badge temporarily, untick **Is active**. Existing grants
> (see **User badges** in the admin) are kept, and owners see the badge again
> once it is re-activated. A badge saved with an empty or unknown rule simply
> stays locked and shows *"No earn rule configured for this badge yet."* in
> its detail view — handy while drafting.

### Rule reference

| `type` | Extra keys | Earned when… | Example |
|---|---|---|---|
| `streak` | `minimum` | streak reaches N days | `{"type": "streak", "minimum": 30}` |
| `activity_logs` | `minimum` | N total activities logged | `{"type": "activity_logs", "minimum": 50}` |
| `perfect_days` | `days` | activity on each of the last N days | `{"type": "perfect_days", "days": 7}` |
| `base_level` | `minimum` | base level (sum of building levels) reaches N | `{"type": "base_level", "minimum": 10}` |
| `blueprints` | `minimum` | N total blueprints owned | `{"type": "blueprints", "minimum": 3}` |
| `skill_level` | `modality`, `minimum` | one skill tree reaches level N | `{"type": "skill_level", "modality": "strength", "minimum": 5}` |
| `all_modalities` | `minimum` | every skill tree reaches level N | `{"type": "all_modalities", "minimum": 3}` |
| `total_xp` | `minimum` | lifetime XP reaches N | `{"type": "total_xp", "minimum": 500}` |
| `time_window` | `before_hour` **or** `after_hour` | any activity logged in that local-time window | `{"type": "time_window", "after_hour": 21}` |

The eight built-in badges (First Steps, 10-Day Flame, Perfect Week, Blueprint
Hunter, Base Tycoon, All-Modality Master, Early Bird, Night Owl) are just rows
in the same `BadgeDef` table — edit, re-point or deactivate them like any
badge you create yourself. (The base-era `base_level` / `blueprints` badge rules
and the *Base Tycoon* / *Blueprint Hunter* badges were **retired** when the base
game was removed in Phase 9.)


---

## Local (no Docker) Development

Any editor/shell from the project root:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
# Fall back to SQLite if no Postgres env is present:
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py seed_demo
.venv\Scripts\python manage.py runserver
```

To run jobs manually (what Celery would do):
```powershell
.venv\Scripts\python manage.py shell -c "from core.tasks import poll_garmin, poll_peloton, poll_liftosaur; poll_garmin(); poll_peloton(); poll_liftosaur()"
```

---

## What's implemented (maps to docs/07_Next_Steps.md)

**Phase 1 — Infrastructure**
- Django project `flamingo_fitness` + `core` app
- `docker-compose.yml` (Postgres, Redis, Web, Celery worker & beat)
- `requirements.txt`, `Dockerfile`, `.env.example`, `.dockerignore`

**Phase 2 — Data models** (`core/models.py`)
- Custom `User`, `UserIntegration`, `RawActivityLog` (JSONB), `XPLedger`,
  `SkillTree`, `DailyReadiness`, `BaseResource`
- Django admin for all models + migrations

**Phase 3 — Ingestion / async** (`core/services`, `core/tasks.py`)
- Celery config + Beat schedule in `settings.py`
- Mock API clients (Garmin / Peloton / Liftosaur) returning realistic payloads
- Polling tasks that save to `RawActivityLog` and process XP

**Phase 4 — Gamification** (`core/services/gamification.py`, `readiness.py`)
- Effort XP math per `docs/03_gamification_math.md`
- Skill-tree progression with level-ups
- Readiness engine (rest-day vs. training mandate)

**Phase 5 — API** (`core/views.py`, `core/urls.py`)
- `GET /api/v1/dashboard/state`
- `GET /api/v1/leaderboard/weekly`
- `GET /api/v1/badges/` — achievement badges: points, awarded dates, live
  progress and lazy granting (see **Achievement badges** below)
- `GET /api/v1/stats/<stat>/` — top-nav stat explainers: clicking the
  streak / tokens / stamina badges shows what the stat means, how to earn it,
  and recent history of earning it (`streak`, `tokens`, `stamina`)
- `POST /api/v1/webhooks/home-assistant`
- Modality panels: `GET /api/v1/nutrition/`, `/api/v1/hydration/`, `/api/v1/endurance/`, `/api/v1/strength/`, `/api/v1/boss/` (incl. personal records), `/api/v1/recovery/`
- **Leagues / Challenges / Flocks (Phase 8)**: `GET /api/v1/leagues/`
  (weekly league board with tiers + history), `GET /api/v1/challenges/`
  (single active challenge — default: calories burned in the last 30 days),
  `GET /api/v1/social/?q=`, `POST /api/v1/friends/request|respond|remove`,
  `POST /api/v1/flocks/create|invite|respond|leave` (see `docs/13`)

**Phase 6 — Frontend / PWA** (`core/templates`, `core/static`)
- Django template dashboard ported from `example_html/dashboard.html`
- Vanilla JS `fetch()` rendering (`dashboard.js`, `nutrition.js`, `hydration.js`, `endurance.js`, `strength.js`, `boss.js`, `recovery.js`, plus Phase 9: `shop.js`, `loadout.js`, `battle.js`, `pvp.js`) + service worker + `manifest.json` + icons

## 🎮 Phase 9 — Tokens, Gacha, Loadout, Battle & PvP (docs/15)

The old "base" meta-game (materials / energy / buildings) is gone, replaced by a
token economy + combat RPG loop: **track your habits → earn Tokens → pull packs
in the Shop → equip a 3-slot Loadout → siege PvE bosses → hold PvP Gyms.** The
player keeps `tokens` / `stamina` in their `PlayerProfile`.

Everything you add lives in four tables you edit in the Django admin
(`/admin/`) or seed from `core/management/commands/create_demo_accounts.py`:

| Model | What it is | Walks the player through… |
|---|---|---|
| `GearPackDef` | A purchasable Shop pack/crate | Spending tokens; winning items |
| `GearItemDef` | A single droppable item/consumable | Being found and equipped |
| `CampaignBoss` | A PvE boss for a domain | Siege HP bar + attack flow |
| `Gym` | Your PvP home turf | Being attacked / holding territory |

### ➕ Adding a Shop pack or crate

1. **Admin:** `Admin → Gear pack defs → Add gear pack def`, set:
   - `slug` (unique, URL-safe), `name`, `price_tokens`, `draws` (items per buy),
     `domains` (JSON list of `cardio|strength|nutrition|hydration|sleep`;
     empty = "no filter"), `guaranteed_min_rarity`, `sort_order`.
   - **Crates:** tick **`is_generic`** so the pack draws from the *entire* active
     gear catalog instead of only its own items (a normal pack only drops gear
     whose `GearItemDef.pack` points at it).
   - **Bulk discount** is automatic: buying `3 → 10%`, `5 → 15%`, `10 → 20%`
     off (`BULK_DISCOUNTS` in `core/services/combat.py`).
2. **Seeding:** add a dict to `config/seeds/packs.json` (loaded at seeding time —
   see **docs/16** for the Google-Sheet workflow).
3. **Coding:** no code needed (the Shop reads `GET /api/v1/shop/state` and
   `POST /api/v1/shop/open {pack_slug, quantity}` automatically).

### ➕ Adding a gear item

1. **Admin:** `Admin → Gear item defs → Add gear item def`, set:
   - `slug`, `name`, `slot` (`head` / `chest` / `left_hand` / `right_hand` /
     `legs` / `feet` / `accessory` — or leave blank for a consumable),
     `rarity`, `icon` (a **free** FontAwesome class, e.g.
     `fa-shirt`, `fa-helmet-safety`, `fa-hand-fist`; avoid Pro-only names like
     `fa-helmet-battle` which render invisible), `effect_type`, `effect_domain`,
     `effect_value`, and `pack` (which pack can drop it).
   - `effect_type` options (see **docs/16** for full details):
     `domain_multiplier` (scales a domain's damage), `synergy` (domain multiplier
     gated by sleep efficiency), **`flat_bonus`** (bare stat increase), **`scales_with`**
     (boost derived from another metric via `effect_params.scales_from`),
     **`stamina_cap`** (more daily stamina), **`token_multiplier`** (more daily
     coins), `double_domain` / `shield_overage` (consumables), and **`stamina_refund`**
     (earn back stamina) / **`grant_tokens`** (earn extra coins) consumables.
   - Consumables: tick `is_consumable`, set `max_stack` (default 9).
2. **Seeding:** add a dict to `config/seeds/gear_items.json` (its `pack` key is the
   pack `slug`). No Python code is required — the seeding command reads the JSON.
3. **Make it discoverable**: attach it to a pack (or make it part of a generic
   crate's catalog). Unpacked gear never drops anywhere.
4. Re-run the seeder (idempotent by `slug`):
   `manage.py create_demo_accounts` (or `manage.py seed_demo` in Docker).

### ➕ Scrap economy (recycle → scraps → rotating Scrap Shop)

- Any owned, **unequipped** item can be **recycled** from the Shop panel
  (`POST /api/v1/scrap/recycle`) into **scraps** — value scales with rarity
  (Common 5 / Rare 15 / Epic 40 / Legendary 100).
- Scraps are spent in the **Scrap Shop** (`GET /api/v1/scrap/shop/state`, buy via
  `POST /api/v1/scrap/shop/buy`). The offering **rotates by day of week**: each
  `ScrapShopItem.available_days` is a list of weekday ints (`0`=Mon … `6`=Sun).
- Seed deals in `config/seeds/scrap_shop.json`; the full design guide lives in
  **docs/16** (including the Google-Sheet authoring + `tools/code.gs` exporter).

### ➕ Adding a PvE campaign boss

1. **Admin:** `Admin → Campaign bosses → Add campaign boss`, set:
   - `campaign` (`cardio`, `strength`, `nutrition`, `hydration`, `sleep`),
     `slug`, `name`, `icon` (free icon), `hp_total`, `element`, `sort_order`.
   - `weaknesses` / `resistances`: JSON lists of domains that deal **2×** /
     **0.5×** damage to it (leave both `[]` for a neutral boss).
   - `mechanics`: JSON dict of optional flags — `{"heal_on_overage": true}`
     (Nutrition heals when calories exceed goal) or
     `{"front_load_water_noon": true}` (Hydration takes 2× when ≥50% of water
     was logged before noon).
2. **Seeding:** add a tuple `(campaign, slug, name, hp, element, weaknesses,
   resistances, mechanics)` to `DEFAULT_CAMPAIGN_BOSSES`. The seeder assigns a
   sequential per-campaign `sort_order` so defeating a boss auto-advances you to
   the next one (the campaign is "built out" with several bosses, e.g. the three
   Strength bosses now seeded: *Sir Skip-a-Leg → Iron Couch King → Deadlift
   Djinn*).

### ➕ Setting up PvP Gyms

- Each user's Gym is created + snapshotted from `POST /api/v1/pvp/defend`
  (`terrain`, `name`). Attack resolution is instant async and reuses the weekly
  `XPLedger` consistency in `Gym.defense_snapshot`.
- To seed a live arena so PvP is populated on boot, the demo command creates a
  `Gym` for both `player1` and `admin` (see `handle()` in
  `create_demo_accounts.py`).

### ⚙️ After any of the above

- Model changes (new field/table): `manage.py makemigrations core` then
  `manage.py migrate`.
- Seeding-only changes: `manage.py create_demo_accounts` is idempotent via
  `get_or_create`, so re-run it (or recreate the DB with `docker compose down -v`
  for a clean slate).
- Validate: `manage.py check`, the test suite (`Testing` below), and
  `node --check core/static/core/js/**/*.js` if frontend JS changed.
- Full design + rulebook math: **`docs/15_Gacha_Battle_Replacing_Base.md`**.

---

## 🧪 Seeding the config with custom data

Every droppable / purchasable entry lives as **plain JSON** in **`config/seeds/`**
and is loaded by the seeder — **no Python changes are needed for normal content
edits**. This is the fastest way to prototype items, packs, and scrap-shop deals:

| File | Model it seeds | One JSON entry… |
|---|---|---|
| `config/seeds/packs.json` | `GearPackDef` | a Shop pack/crate |
| `config/seeds/gear_items.json` | `GearItemDef` | one droppable item/consumable |
| `config/seeds/scrap_shop.json` | `ScrapShopItem` | a rotating Scrap Shop deal |
| `config/seeds/campaign_bosses.json` | `CampaignBoss` | one PvE campaign boss (campaign, HP, element, weaknesses/resistances/mechanics) |
| `config/seeds/boss_configs.json` | `BossConfig` | one PR Boss benchmark (lift name + bodyweight multiplier) |
| `config/seeds/challenges.json` | `Challenge` | a rolling community challenge |
| `config/seeds/badges.json` | `BadgeDef` | a built-in achievement badge (points + rule) — seeded via `sync_badge_defs()` |

### ⚙️ Gameplay tuning (numbers)

Balance knobs — token/stamina economy, gacha odds, combat/PvP numbers, league
tiers & weekly rewards, XP-per-level and the readiness rest-day threshold —
live in **`config/gameplay.json`** (loaded by `core/services/game_config.py`,
bound into the services as module-level constants). Edit a number there and the
running workers pick it up on their next code reload; no DB migration, and no
code editing is needed to retune the game.

> Structural constants that aren't "balance" (ragged slot ids, campaign event
> maps, weekday names) intentionally stay in Python.


### When seeding runs

```powershell
# Local (no Docker)
.venv\Scripts\python manage.py create_demo_accounts

# Inside Docker (also runs on web-container startup; seed_demo wraps it too)
docker compose exec web python manage.py seed_demo
```

### How the seeder merges (get_or_create by `slug`)

The command uses Django's `get_or_create(slug=…, defaults=…)`:

- **New `slug`** → the row is inserted with the JSON's fields, then the demo
  `player1` starter inventory/user records are set up.
- **Existing `slug`** → the row is left untouched (get_or_create does **not**
  update an already-existing row). To change an item that's already seeded,
  either:
  1. Edit it in the Django admin (`/admin/` — `Gear item defs` etc.), or
  2. Delete the row and re-run the seeder, or
  3. Recreate the database from scratch:
     `docker compose down -v` → `docker compose up --build` → `seed_demo`.

So the rule of thumb is: **add new slugs freely and re-seed; for edits, use the
admin or delete-then-re-seed.**

### Example — add a gear item with a new effect type

Append to `config/seeds/gear_items.json` (inside the top-level `[ ]` array):

```json
{
  "slug": "flux_cape",
  "name": "Flux Cape",
  "slot": "chest",
  "rarity": "epic",
  "icon": "fa-cape",
  "effect_type": "scales_with",
  "effect_domain": "cardio",
  "effect_value": 0.5,
  "effect_params": { "scales_from": "strength" },
  "pack": "cardio_storm",
  "weight": 40,
  "description": "Adds 50% of your Strength base damage to Cardio sieges.",
  "is_active": true,
  "sort_order": 210
}
```

`effect_type` / `effect_params` supported values are listed in the **Adding a
gear item** section above and documented in depth in **docs/16**.

### Example — add a Scrap Shop deal

Append to `config/seeds/scrap_shop.json`:

```json
{
  "slug": "scrap_energy_pack",
  "name": "Energy Refill",
  "icon": "fa-bolt",
  "description": "Refills 3 stamina.",
  "cost_scraps": 60,
  "available_days": [0, 2, 4],
  "reward_type": "stamina",
  "reward_value": 3,
  "is_active": true,
  "sort_order": 60
}
```

`available_days` is a list of weekday ints (`0`=Mon … `6`=Sun) — an empty list
means **every day**. `reward_type` is `tokens` / `stamina` / `pack` (for `pack`,
also set the `"pack"` key to a `packs.json` slug).

### Disabling / experimenting

- Set `"is_active": false` to hide an item or deal without deleting it — it stays
  in the catalog but never drops/sells and is filtered from the UI.
- Adjust `weight` to tune drop rates, `rarity` / `effect_value` to tune power, and
  `sort_order` to control inventory ordering.

### Verify after seeding

```powershell
.venv\Scripts\python manage.py check
.venv\Scripts\python manage.py shell -c "from core.models import GearItemDef, GearPackDef, ScrapShopItem; print('gear', GearItemDef.objects.count(), 'packs', GearPackDef.objects.count(), 'scrap deals', ScrapShopItem.objects.count())"
```

Run the suite with `Testing` below. For the **Google Sheet** authoring flow
(where `config/seeds/*.json` come from), see **docs/16** and **`tools/code.gs`**.


---

## Testing

```powershell
.venv\Scripts\python manage.py test core --settings=flamingo_fitness.test_settings
```

The `test_settings` shim forces the SQLite fallback + a fast password hasher
so the suite runs without the Docker stack (the repo `.env` points Postgres /
Redis at container hostnames). Inside Docker, plain `manage.py test core`
works as usual.

The suite covers the XP math (endurance/strength/sleep/body-battery/nutrition),
the gamification flow (PR boss bonuses, level-ups, materials), the readiness
thresholds, the base economy, leagues/challenges/flocks, and the API endpoints.

---

## Demo credentials

| Role      | Username | Password       |
|-----------|----------|----------------|
| Superuser | `admin`  | `adminpass123` |
| Player    | `player1`| `playerpass123`|

## Useful Django commands

```powershell
.venv\Scripts\python manage.py shell               # interactive shell
.venv\Scripts\python manage.py create_demo_accounts # create admin + player (idempotent)
.venv\Scripts\python manage.py seed_demo           # recreate demo data + pollers
.venv\Scripts\python manage.py makemigrations core # after model changes
.venv\Scripts\python manage.py migrate
```
