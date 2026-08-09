# 🏝️ Phase 7 Plan: Base-Building Meta-Game ("The Flamingo Club")

> **STATUS: DRAFT** — written for human review. Nothing below is implemented yet.
>
> **AI Context for implementers:** when implementation starts, each step below
> maps to a `[ ]` checkbox in `docs/07_Next_Steps.md` (Phase 7, Steps 21–28).
> Follow the existing codebase patterns: `BossConfig`-style admin catalog,
> vanilla-JS panel controllers (`loadX` / `backToX` / `renderX`), lazy per-panel
> APIs, `core/services/__init__.py` re-exports, and the validation loop
> `python manage.py test core` + `node --check`.

## 1. Overview & Goals

The base-building meta-game turns "Effort XP and macros translate into
resources" into a highly engaging, Duolingo-style progression loop. Phase 7
builds a themed virtual property: **"The Flamingo Club"** (a Miami beach club).
Beyond simple construction timers, the base is a living, breathing economy:

- **Resources** — Materials (build currency), Energy (action stamina),
  Time Speedups, and rare Boss Blueprints.
- **Deep Progression** — micro-builds for instant gratification, branching tech
  trees at Level 3, and synergistic layout bonuses.
- **Fitness Integration** — consistency streaks directly multiply base income;
  specific workout modalities (strength / cardio) buff specific buildings; rest
  days grant massive, overflowable energy spikes via the Recovery Pool.
- **Polish** — local-time day/night cycles, neon customization, haptics, and
  milestone celebrations make the club feel alive.

## 2. The Core Loop

```text
train / eat / hydrate well   -> materials + XP (existing) + Modality Buffs (NEW)
maintain daily streaks       -> global production multiplier goes up (NEW)
conquer a PR Boss            -> time_speedups + chance at rare Blueprints (NEW)
rest day / recovery          -> massive energy spike, may overflow the cap (NEW)
Build / Upgrade              -> spend materials + energy (instant for micro-builds,
                                timers for everything else)
building hits Level 3        -> choose a branch: +XP **or** +Materials (NEW)
Collect                      -> claim materials; 5% chance of a "Crit"
                                double-yield (NEW)
assign a friend / staff      -> +10% yield on that one building (NEW)
base level hits 5, 10, ...   -> confetti milestone celebration (NEW)
```

## 3. Resource Economy Rulebook (NEW math for docs/03)

All tunables live as named constants at the top of
`core/services/base_economy.py` so they can be tuned without hunting literals.

### 3.1 Constants

| Constant                  | Value | Meaning |
|---------------------------|-------|---------|
| `ENERGY_CAP`              | 100   | Passive-regen wallet ceiling |
| `ENERGY_PER_HOUR`         | 5     | Passive refill rate |
| `REST_DAY_ENERGY_BONUS`   | 25    | Rest-day spike; **ignores the cap** |
| `XP_TO_MATERIALS`         | 20    | Daily dividend: 1 material per 20 XP earned that day |
| `MAX_XP_BONUS_PCT`        | 25    | Ceiling on combined building XP bonus |
| `STREAK_CAP_DAYS`         | 10    | Streak multiplier saturates at 10 days |
| `STREAK_STEP`             | 0.05  | Per-streak-day multiplier step |
| `CRIT_CHANCE`             | 0.05  | 5% double-yield on manual collect |
| `STAFF_BONUS`             | 1.10  | +10% per staffed building |
| `MODALITY_BUFF`           | 1.20  | +20% for the buffed-24h modality building |
| `MODALITY_BUFF_HOURS`     | 24    | Buff duration |
| `BLUEPRINT_DROP_CHANCE`   | 0.10  | PR Boss chance to drop a rare blueprint |
| `BLUEPRINT_DROP_NAME`     | "golden_flamingo" | Blueprint granted on a successful drop |

### 3.2 Mechanics

**Energy overflow.** Passive regen accrues up to `ENERGY_CAP` only, and it is
computed so that a wallet already above the cap (e.g. 115/100 after a rest day)
is **never reduced** — regen simply no-ops until the wallet is back under the
cap. `REST_DAY_ENERGY_BONUS` also **ignores the cap** (`min` is NOT applied for
the rest-day grant).

**Streak multiplier.** `1 + (min(streak_days, STREAK_CAP_DAYS) * STREAK_STEP)`.
A 0-day streak = `1.0x`; a 10-day streak = `1.5x`. Applied to building
production only (not to wallet spends).

**Crit collection.** On manual collect, roll `random() < CRIT_CHANCE`. A crit
doubles the accrued materials (`collected = accrued * 2`) and the API returns
`"was_crit": true` so the frontend can animate the pill.

**Modality buffs.** Logging a workout calls `log_modality_workout(resources,
modality)` which writes `active_buffs[f"{modality}_buff_expiry"] = now + 24h`.
A building whose `modality_affinity` matches an **unexpired** buff gets `1.20x`
production. Mapping: the `strength` workout handler → `"strength"`; the
`cardio`/`endurance` handlers → `"cardio"`.

**Synergies.** `evaluate_synergies(user)` inspects *built* building levels.
Owning `pool_deck` Lv2+ **and** `cabana` Lv2+ unlocks `"poolside_chill"` =
+5% passive energy generation globally.

**Daily dividend.** On first read/tick of each day,
`XP earned since local midnight // XP_TO_MATERIALS` is minted into materials.
Idempotent per user+date via `BaseResource.last_daily_harvest`.

**Blueprint drops.** When a strength log carries `pr: true` (boss fight
defeated), roll `BLUEPRINT_DROP_CHANCE`; on success increment
`BaseResource.blueprints[BLUEPRINT_DROP_NAME]`. Blueprints are the unlock key
for prestige defs (`BaseBuildingDef.requires_blueprint`).

## 4. Data Model Changes (`core/models.py` + migration `0004`)

### 4.1 `BaseBuildingDef` (admin-configurable catalog)

```python
class BaseBuildingDef(models.Model):
    slug                = models.SlugField(unique=True)
    name                = models.CharField(max_length=80)
    description         = models.TextField(blank=True)
    icon                = models.CharField(max_length=40, default="fa-umbrella-beach")
    base_cost_materials = models.PositiveIntegerField(default=40)
    base_cost_energy    = models.PositiveIntegerField(default=10)
    base_duration_hours = models.PositiveIntegerField(default=6)  # 0 = instant micro-build
    materials_per_day   = models.PositiveIntegerField(default=0)
    xp_bonus_pct        = models.PositiveIntegerField(default=0)
    max_level           = models.PositiveIntegerField(default=5)
    requires_base_level = models.PositiveIntegerField(default=0)
    # e.g. "golden_flamingo" — must be owned in BaseResource.blueprints to build
    requires_blueprint  = models.CharField(max_length=50, null=True, blank=True)
    # e.g. "strength" / "cardio" — matches an active_buffs key to get 1.2x production
    modality_affinity   = models.CharField(max_length=20, null=True, blank=True)
    # Level-3 evolution menu: {"Materials": "cabana_mat", "XP": "cabana_xp"}
    branch_choices      = models.JSONField(default=dict)
    # Added to REST_DAY_ENERGY_BONUS while this building is owned (Recovery Pool)
    rest_day_bonus_add  = models.PositiveIntegerField(default=0)
    sort_order          = models.IntegerField(default=0)
    is_active           = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def cost_for_level(self, target_level):  # +40% per upgrade, reused for both mats+energy
        scale = 1 + 0.4 * (target_level - 1)
        return round(self.base_cost_materials * scale), round(self.base_cost_energy * scale)

    def duration_for_level(self, target_level):
        return self.base_duration_hours * target_level

    def bonus_pct_for_level(self, target_level):
        return self.xp_bonus_pct * target_level
```

### 4.2 `BaseBuilding` (per-user instances)

```python
class BaseBuilding(models.Model):
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name="base_buildings")
    building_def = models.ForeignKey(BaseBuildingDef, on_delete=models.CASCADE, related_name="instances")
    level        = models.PositiveIntegerField(default=0)   # built level (0 = never built)
    target_level = models.PositiveIntegerField(default=0)   # in-construction target
    construction_started_at     = models.DateTimeField(null=True, blank=True)
    construction_duration_hours = models.PositiveIntegerField(default=0)
    last_produced_at = models.DateTimeField(null=True, blank=True)  # idle-accrual checkpoint
    custom_color    = models.CharField(max_length=7, default="#FF69B4")  # neon customization
    staff_friend_id = models.IntegerField(null=True, blank=True)       # social +10% avatar boost
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "building_def"],
                                               name="unique_user_building_def")]

    @property
    def is_constructing(self, now=None):
        if not self.construction_started_at:
            return False
        return now is None or now < self.construction_started_at + timedelta(
            hours=self.construction_duration_hours
        )
```

### 4.3 `BaseResource` additions

```python
class BaseResource(models.Model):
    # ...existing materials / energy / time_speedups...
    energy_updated_at         = models.DateTimeField(null=True, blank=True)  # passive-regen checkpoint
    last_daily_harvest        = models.DateField(null=True, blank=True)      # XP->materials idempotency
    last_rest_bonus_date      = models.DateField(null=True, blank=True)      # rest-day idempotency
    blueprints                = models.JSONField(default=dict)               # {"golden_flamingo": 1}
    active_buffs              = models.JSONField(default=dict)               # {"strength_buff_expiry": "iso-date"}
    last_milestone_celebrated = models.IntegerField(default=0)               # confetti tracker (5, 10, ...)
```

> **Note (beyond the draft spec):** `last_rest_bonus_date` is added so
> `apply_rest_day_bonus` can be idempotent per calendar day, mirroring
> `last_daily_harvest`. Without it, the +25 spike would fire on every state
> read. All `JSONField(default=...)` values must use the callable `dict` —
> not a mutable dict literal (classic Django gotcha).
## 5. Service Layer: `core/services/base_economy.py`

New module, style-matched to `gamification.py`. Every function below that is
called from views/tasks/admin must be **re-exported from
`core/services/__init__.py`** — the docs/08 endurance `ImportError → 500`
lesson applies here.

**Convention:** every time-sensitive function accepts `now=None` (defaults to
`timezone.now()`) so tests can freeze time. Saves use `update_fields` and
wallet mutations go inside `transaction.atomic` + `select_for_update`.

### 5.1 `refresh_energy(resources, now=None)` → `resources`

```python
def refresh_energy(resources, now=None):
    now = now or timezone.now()
    if resources.energy_updated_at:
        elapsed_h = (now - resources.energy_updated_at).total_seconds() / 3600
        # Overflow-safe: only refill while below the cap; never reduce.
        if resources.energy < ENERGY_CAP:
            resources.energy = min(ENERGY_CAP, resources.energy + int(elapsed_h * ENERGY_PER_HOUR))
        resources.energy_updated_at = now
        resources.save(update_fields=["energy", "energy_updated_at"])
    return resources
```

> **Hint:** make the refill **float-correct** by computing
> `resources.energy + elapsed_h * ENERGY_PER_HOUR` *before* `int()` truncation.
> First call (no `energy_updated_at`) just stamps the timestamp — no jump.

### 5.2 `apply_rest_day_bonus(resources, user, on_date=None)` → int

- If today's `DailyReadiness.streak_requirement == "rest_day"` **and**
  `resources.last_rest_bonus_date != on_date`:
  `bonus = REST_DAY_ENERGY_BONUS + sum(b.building_def.rest_day_bonus_add for b in built)`
  (a built Recovery Pool adds +5), grant **without** `min()` clamping, stamp
  `last_rest_bonus_date = on_date`. Returns the bonus granted (or 0).

### 5.3 `daily_harvest(resources, user, on_date=None)` → int

- If `resources.last_daily_harvest != on_date`: sum
  `XPLedger.objects.filter(user=user, created_at__date=on_date)`, mint
  `xp_today // XP_TO_MATERIALS` into materials, stamp the date. Return minted.

### 5.4 `production_plan(building, streak_days, active_buffs, synergies, now=None)` → float

```python
elapsed_days = ((now or timezone.now()) - (building.last_produced_at or now)).total_seconds() / 86400
base = (elapsed_days // 1) * building.building_def.materials_per_day * building.level   # floor: whole days only
mult = streak_multiplier(streak_days)                       # 1.0 .. 1.5
if building.staff_friend_id:  mult *= STAFF_BONUS           # 1.1
if modality_buff_active(building.building_def, active_buffs, now):  mult *= MODALITY_BUFF  # 1.2
return round(base * mult, 2)
```

- `streak_multiplier(streak_days)` = `1 + min(streak_days, STREAK_CAP_DAYS) * STREAK_STEP`.
- `modality_buff_active(def, active_buffs, now)` — true when
  `def.modality_affinity` is set and `active_buffs.get(f"{affinity}_buff_expiry")`
  parses to a datetime still in the future.

### 5.5 `collect_building(instance, now=None)` → `(collected, was_crit)`

- `accrued = production_plan(...)`; `was_crit = random.random() < CRIT_CHANCE`;
  `collected = int(accrued * 2) if was_crit else int(accrued)`; add to the
  wallet (`select_for_update`), reset `last_produced_at = now`. No-op when
  `level == 0` or still constructing.

### 5.6 `evolve_building(instance, chosen_slug, now=None)` → (ok, error)

- Require `instance.level >= 3`; require `chosen_slug` to be one of the
  **values** in `instance.building_def.branch_choices` (e.g.
  `"cabana_mat"`); the target def must exist + `is_active`. Swap
  `instance.building_def`, keep `level`, reset `last_produced_at = now` so
  production restarts with the branch def's stats.

### 5.7 `log_modality_workout(resources, modality, now=None)`

- `resources.active_buffs[f"{modality}_buff_expiry"] = (now + timedelta(hours=MODALITY_BUFF_HOURS)).isoformat()`
- Called by the gamification hook (Step 23), not by views.

### 5.8 `evaluate_synergies(user)` → list[str]

- Scan built instances (any level, or Lv2+ per spec — spec uses Lv2+):
  owning `pool_deck` **and** `cabana` (each Lv2+) → `["poolside_chill"]`.
- Keep the rule table as module constants so future synergies are one line.

### 5.9 Other helpers

- `base_xp_bonus_pct(user)` → `min(MAX_XP_BONUS_PCT, Σ def.xp_bonus_pct * level)`.
- `clear_expired_buffs(resources, now=None)` — drop `*_buff_expiry` keys whose
  ISO date is in the past (call from `refresh_resources`).
- `refresh_resources(resources, user, now=None)` — `refresh_energy` +
  `clear_expired_buffs` + `apply_rest_day_bonus` + `daily_harvest`; the one
  call views use before every read/mutation.
- `resource_dump(resources)` → `{materials, energy, time_speedups, blueprints, energy_cap, energy_per_hour}` — shared by `/dashboard/state` and `/base/` so the header badge never drifts.
- `start_construction(user, slug, now=None)` / `spend_speedups(instance, amount, now=None)` — ported from the earlier draft: validate (def active, unlocked, not constructing, `requires_blueprint` owned, funds), deduct atomically, set the timer; speedups subtract hours from the remaining time and **refund overshoot**.
## 6. API Contracts (`core/views.py` + `core/urls.py`)

All under `/api/v1/`, session-auth, `@login_required`. POSTs are `@require_POST`
with a JSON body (`json.loads`, same as the HA webhook) and return the standard
`_json_error(message, status)` 400 contract. Every mutation returns a fresh
`resource_dump(...)` and the affected building so the UI can re-render without
a full refetch.

### 6.1 `GET /api/v1/base/` → `views.base_state`

```json
{
  "resources": {
    "materials": 150, "energy": 115, "time_speedups": 5, "blueprints": {},
    "energy_cap": 100, "energy_per_hour": 5
  },
  "base_level": 5,
  "xp_bonus_pct": 4,
  "streak_multiplier": 1.15,
  "active_synergies": ["poolside_chill"],
  "buildings": [
    {
      "id": 1, "slug": "cabana", "name": "Cabana",
      "icon": "fa-umbrella-beach",
      "level": 3, "status": "built",
      "custom_color": "#FF69B4", "staffed": true,
      "staff_friend_id": 42,
      "accrued_materials": 10,
      "construction_ends_at": null, "construct_progress_pct": null,
      "branch_choices": {"Materials": "cabana_mat", "XP": "cabana_xp"}
    }
  ],
  "unlockable": [ { "slug": "gold_flamingo", "name": "Gold Statue",
                    "requires_base_level": 8,
                    "requires_blueprint": "golden_flamingo",
                    "has_blueprint": false } ]
}
```

- `resources` comes straight from `refresh_resources` + `resource_dump`.
- `buildings` = all instances sorted by `def.sort_order`; each `status` is
  `not_started | constructing | built` (lazy-completed with `complete_or_pending`).
  `branch_choices` only present when `level >= 3` **and** choices exist.
- `unlockable` = active defs with no instance yet; include
  `locked_reason` ("Base level", "Requires blueprint") for the UI lock icon.

### 6.2 Mutating endpoints

| Endpoint | Body | Behavior / response extras |
|----------|------|----------------------------|
| `POST /base/start` | `{"slug": "cabana"}` | Starts a build or an upgrade. Micro-builds (`base_duration_hours == 0`) complete **immediately**. Errors: not enough materials/energy, locked (base level / blueprint), constructing, max level. |
| `POST /base/speedup` | `{"id": 1, "hours": 3}` | Spends speedups to skip construction time; refunds overshoot. `{"ok": true, "speedups_spent": 3, "completed": true, "resources": {...}}` |
| `POST /base/collect` | `{"id": 1}` | `{"ok": true, "collected": 20, "was_crit": true, "resources": {...}}` |
| `POST /base/customize` | `{"id": 1, "color": "#00FFFF"}` | Validates a 7-char `#RRGGBB`; saves `custom_color`. |
| `POST /base/staff` | `{"id": 1, "friend_id": 42}` | `friend_id=null` un-staffs. Phase 7 mocks the friend list to a static set. |
| `POST /base/evolve` | `{"id": 1, "chosen_slug": "cabana_xp"}` | Level-3 branch swap; 400 if level < 3, invalid choice, or target inactive. |
| `POST /base/milestone` | `{}` | Marks `last_milestone_celebrated = base_level` when `base_level >= 5 and base_level % 5 == 0`. Returns `{"ok": true, "celebrated": true}`. |

> **Note (beyond the draft spec):** the spec's API list omits `start`,
> `speedup` and `milestone`, but the core loop *requires* them (builds,
> speedup spend, confetti ack). They are re-included here deliberately.

### 6.3 `core/urls.py` additions

```python
path("base/", views.base_state, name="base_state"),
path("base/start", views.base_start, name="base_start"),
path("base/speedup", views.base_speedup, name="base_speedup"),
path("base/collect", views.base_collect, name="base_collect"),
path("base/customize", views.base_customize, name="base_customize"),
path("base/staff", views.base_staff, name="base_staff"),
path("base/evolve", views.base_evolve, name="base_evolve"),
path("base/milestone", views.base_milestone, name="base_milestone"),
```

### 6.4 Shared serialization helpers

- `_base_payload(request.user, now=None)` — builds the whole `GET /base/`
  dict; used by every mutating view to return the post-mutation snapshot.
- `_serialize_building(instance, now)` — one building dict (includes
  `accrued_materials` from `production_plan`).
- `_base_level(user)` — `Σ level` over instances (used for unlock gates,
  milestones, and the `unlockable` list).
## 7. Frontend (Miami / Duolingo Polish)

### 7.1 Files touched

- `core/templates/core/dashboard.html` — CSRF meta tag, `#nav-base` handler,
  new `<section class="base-view hidden" id="base-view">`, `<script>` tags.
- `core/static/core/js/base.js` — **NEW** controller (model on
  `recovery.js`'s `loadX` / `backToX` / `renderX` contract).
- `core/static/core/css/dashboard.css` — day/night vars, neon, building cards.
- `core/static/core/js/dashboard.js` — expose `window.refreshDashboardState()`
  so base.js can refresh the header chips (streak / materials / energy).

### 7.2 Dynamic day/night cycle (CSS + JS)

- `base.js` reads the **client's** local clock: `new Date().getHours()`.
  - 06:00–18:00 → `document.body.classList = 'theme-day'` (default).
  - 18:00–06:00 → `document.body.classList = 'theme-night'`.
- CSS in `:root` / `body.theme-night`:
  - `--bg-sky: #87CEEB` (day) vs `#1A1A2E` (night).
  - Night adds glowing drop-shadows on `--neon-color` (use a per-card accent
    derived from `custom_color`).
- Re-run on `loadBase()` and on a `setInterval` (or on visibilitychange) so the
  sky swaps while the app sits open.

### 7.3 Haptics & audio

- **Haptics:** `navigator.vibrate([50])` on collect; `[100, 50, 100]` +
  a CSS pop animation on the resource pill when `was_crit` is true.
  Guard every call (`if (navigator.vibrate)`) — unsupported browsers must no-op.
  **Gotcha:** `navigator.vibrate` requires a user gesture, so call it inside
  the click handler synchronously before the async fetch resolves.
- **Audio:** `pop.mp3` (collect) and `cash.mp3` (crit). Prefer synthesizing
  short sounds with the **Web Audio API** (`OscillatorNode`) so the repo stays
  free of binary assets and there are no license worries. Wrap every
  `play()` in `try/catch` — autoplay policies can reject audio.

### 7.4 Cosmetics & staff

- Building cards show an `<input type="color">` (visible only when the
  building is fully constructed) → `POST /base/customize` on `change`.
- An empty "Staff" portrait circle on the card; clicking it opens a modal with
  a mocked static friend list for Phase 7 → `POST /base/staff`. Staffed cards
  draw a badge and a "×1.1" hint.

### 7.5 Milestone celebrations

- `renderBase()` compares `base_level` against
  `resources.last_milestone_celebrated`: when `base_level >= 5 &&
  base_level % 5 === 0 && lastMilestone < base_level`:
  1. fire `canvas-confetti` (CDN script tag in `dashboard.html`),
  2. show a "Base Level Up!" toast,
  3. `POST /base/milestone` to ack the tracker (prevents repeat fireworks).

### 7.6 Wiring / CSRF (the "learned the hard way" bit)

- This app has **never done a `fetch` POST** — every controller so far is GET.
  Add `<meta name="csrf-token" content="{{ csrf_token }}">` to `<head>`, then:
  ```js
  function csrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
  }
  fetch(url, { method: 'POST', credentials: 'same-origin',
               headers: { 'Content-Type': 'application/json',
                          'X-CSRFToken': csrfToken() },
               body: JSON.stringify(payload) });
  ```
- `node --check` after every edit; `base.js` must read the **real** keys from
  §6.1 — do not copy `hydration.js`/`endurance.js` and rename identifiers.
## 8. Admin & Seeding (The Updated Catalog)

- `core/admin.py`: register `BaseBuildingDef` and `BaseBuilding`
  (list_display for slug/name/cost/duration/material-per-day/affinity/
  blueprint-required/level/status columns; `is_active` list_filter).
- `create_demo_accounts` seeds the catalog idempotently **by slug**
  (`get_or_create` — copy the existing `BossConfig` pattern) and gives
  `player1` a head start: Lawn Chairs Lv1 + Cabana Lv1 built, 150 materials,
  ~45+ energy, the `golden_flamingo` blueprint, and 5 speedups.

### 8.1 Default catalog (tuning values — all adjustable)

| slug | name | mat | en | dur | mat/day | xp% | max | req | affinity | blueprint | notes |
|------|------|-----|----|-----|---------|-----|-----|-----|----------|-----------|-------|
| `lawn_chairs` | Lawn Chairs | 10 | 5 | 0h (instant) | 1 | 0 | 3 | 0 | — | — | Micro-build — day-one gratification |
| `cabana` | Cabana | 40 | 10 | 6h | 2 | 1 | 5 | 0 | — | — | Base building; offers branches at Lv3 |
| `cabana_mat` | Beach Cabana | 50 | 12 | 8h | 6 | 0 | 5 | 0 | — | — | Branch A (heavy materials) — only via evolve |
| `cabana_xp` | VIP Cabana | 50 | 12 | 8h | 1 | 4 | 5 | 0 | — | — | Branch B (heavy XP) — only via evolve |
| `juice_bar` | Juice Bar | 60 | 15 | 8h | 3 | 2 | 5 | 1 | `cardio` | — | Cardio-buff target |
| `recovery_pool` | Recovery Pool | 70 | 20 | 12h | 0 | 1 | 3 | 2 | — | — | `rest_day_bonus_add = 5` |
| `pool_deck` | Pool Deck | 140 | 30 | 16h | 6 | 4 | 5 | 3 | — | — | Synergy half A (poolside_chill) |
| `vip_lounge` | VIP Lounge | 380 | 70 | 48h | 14 | 9 | 5 | 6 | `strength` | — | Strength-buff target |
| `gold_flamingo` | Gold Statue | 400 | 80 | 72h | 50 | 10 | 3 | 8 | — | `golden_flamingo` | Prestige — requires the blueprint |

> Branch defs (`cabana_mat`, `cabana_xp`) are **not directly buildable** — they
> are only reachable via `POST /base/evolve`, so their `requires_base_level` is
> irrelevant; keep them `is_active=True` but exclude buildable-defs from
> `unlockable` when `requires_blueprint` is set without showing them as
> standalone builds.

## 9. Celery / Beat (optional daily task)

`tick_base_economy()` (in `core/tasks.py`, shared-task style) iterates users
with `BaseResource` and:

1. `refresh_energy` + `daily_harvest` + `clear_expired_buffs`,
2. lazily completes any finished constructions,
3. accrues building production into `materials` via `production_plan`
   (the whole-day floor naturally throttles partial days).

Schedule in `settings.py` `CELERY_BEAT_SCHEDULE`:
`crontab(minute=5, hour=0)` (once daily). Every action is idempotent by stored
date/timestamp, so the task is safe to run twice.

## 10. Tests (`core/tests.py` additions)

**Pure math (SimpleTestCase):**
- energy overflow: refill stops at 100 and never decreases a 115 wallet;
  rest-day bonus pushes 90 → 115 and 110 → 135 uncapped.
- `streak_multiplier`: 0d → 1.0, 5d → 1.25, 10d → 1.5, 20d → 1.5 (saturated).
- crit: with a mocked `random.random()`, collect returns ×2 only under 0.05.
- `production_plan`: floor on partial days, staff ×1.1, modality buff ×1.2.
- XP dividend: `xp_today // 20` boundaries; `base_xp_bonus_pct` caps at 25.

**DB / integration (TestCase):**
- `apply_rest_day_bonus` fires once per date (stamps `last_rest_bonus_date`)
  and includes `rest_day_bonus_add` from an owned Recovery Pool.
- modality buffs: `log_modality_workout` sets the expiry; `production_plan`
  applies the 1.2× while unexpired and drops it after `MODALITY_BUFF_HOURS`.
- `evolve_building` swaps the def (level preserved, production resets); rejects
  level < 3 and slugs outside `branch_choices`.
- blueprints gate: `start_construction` on `gold_flamingo` without the
  blueprint → 400; with it → success; spawn a fake PR log and assert the drop
  roll writes into `blueprints`.
- gamification hook: `_handle_strength` with `pr: true` triggers a blueprint
  roll; `_handle_endurance`/`_handle_cardio` set the `cardio` buff.

**API (TestCase with login client):** `GET /base/` shape + auth; each POST's
happy path + 400 contract; a POST **without** the CSRF token → 403.

**Frontend:** `node --check core/static/core/js/base.js` after every edit.
## 11. Known Gotchas ("learned the hard way")

- **Haptics need a user gesture.** `navigator.vibrate` must be called
  synchronously inside the click handler — it is ignored if deferred behind a
  long `async` fetch. Call it *before* fetching, and animate on the `was_crit`
  response.
- **Timezones.** Day/night must use the **client's** local clock
  (`new Date().getHours()`) — never server time — so the Miami vibe matches the
  user's actual evening. On the backend, always `timezone.now()` /
  `timezone.localdate()`, never `datetime.now()` (existing convention).
- **CSRF.** The frontend has only ever done GETs. Every new `fetch` POST must
  send `X-CSRFToken` from the meta tag or it 403s. Test the 403 explicitly.
- **Mutable defaults.** Every `JSONField(default=dict)` must pass the callable
  `dict` — a shared literal dict would leak state across instances.
- **Concurrency.** Wrap wallet deductions and collection in
  `transaction.atomic` + `select_for_update`, or rapid double-taps double-spend
  / double-claim.
- **Re-exports.** Every `base_economy` helper used outside the module must be
  re-exported from `core/services/__init__.py` (docs/08 endurance 500 lesson).
- **Don't port controllers by renaming.** `base.js` must read the real payload
  keys from §6.1 (id, status, accrued_materials, branch_choices, ...), then run
  `node --check`.
- **Idempotency.** Rest-day bonus, daily harvest, quality buffs, and the
  milestone tracker each need a stored "last date/level" so repeated reads and
  the beat task can't double-fire.
- **Order of hooks in `gamification.py`.** Add buff/blueprint side effects
  **after** XPLedger rows are computed, never before `apply_to_skill_tree`, and
  keep them non-fatal (wrap in try/except) so an economy error never loses XP.
- **Do not change existing reward amounts.** Only ADD. Run the full existing
  suite first so the diff stays clean.

## 12. Detailed Step-by-Step Coding Plan (Steps 21–28)

Each step lists **Goal → Files → Do → Hints → Done-when**. Steps map to the
`docs/07_Next_Steps.md` Phase 7 checkboxes, plus a painted checklist at the end.
Complete steps in order; run `python manage.py test core` and `node --check`
at the end of each step.

### Step 21 — Models (`BaseBuildingDef`, `BaseBuilding`, `BaseResource`)

- **Goal:** schema for the whole meta-game. No views, no UI yet.
- **Files:** `core/models.py`, `core/migrations/0004_auto.py` (generated), `core/admin.py` (later in Step 24 — can register now), `docs/01_Database_Schema.md`.
- **Do:**
  1. Add `BaseBuildingDef` per §4.1 and `BaseBuilding` per §4.2 (import `timedelta` — check it's already imported in models.py).
  2. Extend `BaseResource` per §4.3 (+`last_rest_bonus_date`, see the note).
  3. `python manage.py makemigrations core && python manage.py migrate`.
  4. Register both models in `core/admin.py` immediately so the catalog is editable during development.
- **Hints:**
  - `branch_choices = models.JSONField(default=dict)` — callable, never a literal.
  - Keep `related_name="base_buildings"` on `BaseBuilding.user` and
    `related_name="instances"` on the FK to the def; both are used in
    serializers.
  - `is_constructing` on the model is a property taking an optional `now` — do
    **not** store status in the DB (lazy derivation keeps mutation-free reads).
  - Do not add `import datetime` at module scope with a plain `datetime.now()`;
    use `from django.utils import timezone` + `timedelta` from `datetime`.
  - Migration safety: `PositiveIntegerField` defaults keep existing rows valid
    (the table is empty/new per user, but demo rows already exist for
    `BaseResource` — defaults handle them).
- **Done-when:** `manage.py check` passes; migration applied; existing
  `XPMathTests`/`GamificationFlowTests` still green.

### Step 22 — Economy service (`core/services/base_economy.py`)

- **Goal:** all the math/state helpers with zero view/frontend coupling.
- **Files:** `core/services/base_economy.py` (new), `core/services/__init__.py` (re-export).
- **Do (in this order):**
  1. Constant block (§3.1).
  2. Pure helpers: `streak_multiplier`, `xp_dividend(xp_today)`.
  3. `refresh_energy` (§5.1) — overflow-safe.
  4. `apply_rest_day_bonus` (§5.2) + `daily_harvest` (§5.3).
  5. `production_plan` + `modality_buff_active` + `clear_expired_buffs` (§5.4).
  6. `collect_building` with the crit roll (§5.5).
  7. `evolve_building` (§5.6).
  8. `log_modality_workout` (§5.7), `evaluate_synergies` (§5.8),
     `base_xp_bonus_pct`, `refresh_resources`, `resource_dump` (§5.9).
  9. Re-export every one of these from `core/services/__init__.py`.
- **Hints:**
  - Pass `now` around everywhere; the crit roll uses `random.random()` — make
    it injectable (`rng=random.random`) for tests, or mock it with
    `unittest.mock.patch`.
  - `production_plan` must never turn negative: clamp `elapsed_days // 1` at ≥0.
  - `apply_rest_day_bonus` reads `DailyReadiness` for `on_date`; use
    `timezone.localdate()` as the default date and bolt the idempotency stamp to
    `last_rest_bonus_date`.
  - Keep `refresh_resources` the single entry point for views: energy → buffs →
    rest bonus → harvest → (return wallet via `resource_dump`).
  - No DB writes in the pure helpers; put `save(update_fields=...)` only in the
    mutators, and wrap wallet mutators in `transaction.atomic`.
- **Done-when:** `from core.services import base_xp_bonus_pct` (and friends)
  works; a scratch `manage.py shell` session refills energy and mints a harvest;
  all existing tests green.

### Step 23 — Gamification hooks (`modality buffs`, `blueprint drops`, `XP bonus`)

- **Goal:** workouts feed the base: XP bonus in `process_payload`, modality
  buffs on cardio/strength logs, blueprint drop on boss PRs.
- **Files:** `core/services/gamification.py`, `core/services/__init__.py` (if needed).
- **Do:**
  1. In `process_payload`, after `_HANDLERS` builds the `entries` list (and
     before the `entry.raw_log = holder` loop), scale amounts:
     ```python
     bonus = base_xp_bonus_pct(entries[0].user) if entries else 0
     if bonus:
         for entry in entries:
             entry.amount = int(round(entry.amount * (1 + bonus / 100)))
     ```
  2. In `_handle_strength`: after the PR branch (`payload.get("pr")`), call a
     new helper `maybe_drop_blueprint(user, rng=random.random)`:
     ```python
     if rng() < BLUEPRINT_DROP_CHANCE:
         res, _ = BaseResource.objects.get_or_create(user=user)
         res.blueprints[BLUEPRINT_DROP_NAME] = res.blueprints.get(BLUEPRINT_DROP_NAME, 0) + 1
         res.save(update_fields=["blueprints"])
     ```
  3. In `_handle_strength`: also call
     `log_modality_workout`(resources, "strength").
  4. In `_handle_endurance` **and** `_handle_cardio`: call
     `log_modality_workout`(resources, "cardio").
- **Hints:**
  - Keep side effects **after** the ledger entries are built so a failure can
    be swallowed (`try/except Exception: logger.exception(...)`) without losing
    XP. Never let the base economy break an XP award.
  - `base_xp_bonus_pct` queries buildings — fine for this app's scale; add a
    per-request cache later only if profiling demands it.
  - Do NOT award a buff when `int(round(...))` would be 0 — irrelevant here but
    keep amounts ≥1 for positive entries.
  - The `strength` modifier key must match the building's
    `modality_affinity="strength"` exactly; likewise `cardio` — an off-by-one
    string here silently kills the 1.2× forever.
  - Import `BaseResource` at top of gamification.py (already imported).
- **Done-when:** a strength PR log increases `blueprints` only ~10% of the time
  (mock `rng` to assert both branches); a cardio log sets
  `active_buffs["cardio_buff_expiry"]`; XP entries scale with a built XP
  building; all pre-existing reward tests unchanged.

### Step 24 — Admin & seeding (full catalog)

- **Goal:** catalog is admin-editable and the demo is alive on first boot.
- **Files:** `core/admin.py`, `core/management/commands/create_demo_accounts.py`, `docs/02_API_Contracts.md`.
- **Do:**
  1. `BaseBuildingDefAdmin` — list_display: slug, name, base_cost_materials,
     base_cost_energy, base_duration_hours, materials_per_day, xp_bonus_pct,
     requires_base_level, modality_affinity, is_active, sort_order; filter
     `is_active`.
  2. `BaseBuildingAdmin` — list_display: user, building_def, level,
     target_level, construction_started_at, custom_color, staff_friend_id.
  3. In `create_demo_accounts`, add a `DEFAULT_BUILDINGS` list of dicts (the §8
     table) and `get_or_create(slug=...)` each; then ensure demo instances:
     `lawn_chairs` Lv1 (built, `last_produced_at=now`) and `cabana` Lv1;
     give `player1` `blueprints={"golden_flamingo": 1}`, 150 materials, 45
     energy, 5 time_speedups (keep existing seeds, just extend them).
- **Hints:**
  - Seed defs **before** seeding instances (FK dependency).
  - For branch defs, set `branch_choices={"Materials": "cabana_mat",
    "XP": "cabana_xp"}` on `cabana`; keep branch defs active but they are not
    buildable directly — decide their `requires_base_level` default 0 is fine
    since they are never offered on the build list.
  - Keep the command idempotent: `get_or_create` everywhere, never bulk-delete.
  - Update `docs/01` (schema) + `docs/02` (endpoints) in this same change so
    docs don't drift (Step 30 does the final sweep).
- **Done-when:** `python manage.py create_demo_accounts` twice is idempotent;
  admin shows the 9 catalog entries; `player1` owns two built buildings and a
  blueprint; `GET /base/` (once Step 25 lands) lists them.

### Step 25 — Views & API

- **Goal:** the eight `/base/*` endpoints behind the auth + CSRF guardrails.
- **Files:** `core/views.py`, `core/urls.py`.
- **Do:**
  1. Add helpers in `core/views.py` (near the `_latest_bodyweight` helper):
     `_base_level(user)`, `_serialize_building(instance, now)`,
     `_base_payload(user, now=None)`, and `_load_base_post_body(request)`
     (json.loads wrapper like the HA webhook).
  2. `base_state(request)` — `refresh_resources` → `resource_dump` → payload.
  3. `base_start`, `base_speedup`, `base_collect`, `base_customize`,
     `base_staff`, `base_evolve`, `base_milestone` — each `@login_required`,
     `@require_POST`, validates, mutates inside `transaction.atomic` +
     `select_for_update`, and returns `_base_payload(user)` (or the compact
     `{"ok": true, "collected": ..., "was_crit": ...}` shape for collect).
  4. Register all eight routes (§6.3) in `core/urls.py`.
- **Hint — view skeleton:**

  ```python
  @login_required
  @require_POST
  def base_collect(request):
      data = _load_base_post_body(request)
      instance = BaseBuilding.objects.filter(pk=data.get("id"),
                                             user=request.user).first()
      if instance is None:
          return _json_error("Building not found.", 404)
      with transaction.atomic():
          res, _ = BaseResource.objects.select_for_update().get_or_create(
              user=request.user)
          refresh_resources(res, request.user)
          building = BaseBuilding.objects.select_for_update().get(pk=instance.pk)
          collected, was_crit = collect_building(building, return_tokens=True)
      return JsonResponse({"ok": True, "collected": collected,
                           "was_crit": was_crit,
                           "resources": resource_dump(res)})
  ```

- **Hints:**
  - Only the *owner* can mutate: always filter by `user=request.user` and 404
    otherwise — do not trust an `owner` field in the body.
  - `refresh_resources` before every mutation so the wallet reflects accrued
    energy/harvest before you spend.
  - Micro-builds (`base_duration_hours == 0`): finish them in the same request —
    build, then immediately `complete_or_pending`, so the user sees "Built!"
    not a spurious timer.
  - `customize` must regex-check `^#[0-9a-fA-F]{6}$` (a 6-digit hex) — reject
    anything else with a 400.
  - Empty/absent `friend_id` in `staff` should **un-staff** (set NULL).
  - `base_milestone` is idempotent: only bump `last_milestone_celebrated` when
    `base_level % 5 == 0 and base_level > last_milestone_celebrated`.
- **Done-when:** a `manage.py shell` + `TestClient` walkthrough builds Lawn
  Chairs instantly, starts a Cabana upgrade, fast-forwards it with a speedup,
  collects (with `was_crit` occasionally true), customizes a color, staffs a
  building, evolves Cabana at Lv3, and celebrates a milestone — each with the
  documented 400 error cases returning the exact `{"error": ...}` shape.

### Step 26 — Frontend logic (`core/static/core/js/base.js`)

- **Goal:** the controller + haptics + day/night + confetti wiring.
- **Files:** `core/static/core/js/base.js` (new), `core/templates/core/dashboard.html`.
- **Do:**
  1. Template: `<meta name="csrf-token" content="{{ csrf_token }}">` in
     `<head>`; wire the Bottom nav:
     `<a href="#" class="nav-item" id="nav-base" onclick="loadBase(); return false;">`.
     Add `<section class="base-view hidden" id="base-view">` with the panel
     back-button (`backToResourcePlan()`), a `#base-content` container, and a
     `#base-empty` empty state. Load `base.js` after `dashboard.js` and add the
     `canvas-confetti` CDN script tag above it.
  2. `loadBase()`: hide `#skill-tree`, show `#base-view`, fetch
     `GET /api/v1/base/`, call `renderBase`.
  3. `renderBase(data)`: render wallet pills (materials/energy/speedups +
     blueprints), streak multiplier + base level + synergy chips, then the
     building cards and `unlockable` rows.
  4. Action functions: `startBuild(slug)`, `speedUpBuild(id)`,
     `collectBuild(id)` (**vibrate synchronously first**), `customizeColor(id)`,
     `staffFriend(id)`, `evolveBuild(id, slug)`, `ackMilestone()`.
  5. Day/night: `applyTheme()` using `new Date().getHours()`; call on
     `loadBase`, on `visibilitychange`, and on a 60s interval.
  6. Audio: Web Audio `popSound()` / `cashSound()` helpers (2–3 oscillator
     blips) wrapped in try/catch; fire `popSound()` on collect, `cashSound()`
     when `was_crit`.
  7. Confetti: on celebration condition, `confetti()` +
     `ackMilestone()` POST.
- **Hints:**
  - Model the fetch flow on `recovery.js` (401/403 branch → error hint, else
    render). Handle `!data.linked`? No — the base is always available; instead
    the empty-state is "no buildings yet, here's what to build".
  - Every mutation POST re-fetches `/base/` (or uses the returned snapshot) and
    calls `window.refreshDashboardState()` so the top-nav chips update.
  - `navigator.vibrate` guard: `if (navigator.vibrate) navigator.vibrate([...])`.
  - Keep functions on `window.*` so template `onclick=` works after
    re-renders (docs/04 hardened pattern).
  - `node --check core/static/core/js/base.js` before moving on.
- **Done-when:** clicking the Base tab opens the panel with live data; collect
  vibrates + (on crit) plays cash sound + pill pop; body class flips at 06:00 /
  18:00; confetti fires exactly once per milestone.

### Step 27 — Frontend UI (CSS + template polish)

- **Goal:** the Miami/Duolingo look: day/night sky, neon glow, tactile cards,
  branching modals, color pickers, staff circles, milestone toast.
- **Files:** `core/static/core/css/dashboard.css`, `core/static/core/js/base.js`
  (markup strings), `core/templates/core/dashboard.html`.
- **Do:**
  1. `:root` day vars — `--bg-sky: #87CEEB`, `--neon-color: #FF5E9A`,
     keep the app-shell tokens; add `body.theme-night` overrides (`--bg-sky:
     #1A1A2E`, `--bg-app` darker, `--text-muted` brighter) and a
     `--neon-glow` shadow (`0 0 12px var(--neon-color)`).
  2. `.base-wallet` band with `.base-resource-pill` variants (materials blue,
     energy purple, speedup orange, blueprints gold) and an `.energy-meter`
     using `.bar`/`.bar-fill` (reuse existing classes).
  3. `.building-card` — 20px radius, Duolingo press bottom-border; states
     `.building-built`, `.building-constructing` (progress bar via
     `#construct-progress`), `.building-locked`. `input[type="color"]` styled
     invisibly as a paint-droplet on constructed cards.
  4. `@keyframes crit-pop` (scale+pulse on `.crit-anim`), `@keyframes neon-flicker`
     for night, and a `.milestone-toast` (fixed, centered, auto-dismiss after
     2.5s).
  5. Branch modal: reuse the existing `#actionModal` (dashboard.js's
     `addModal`) plus two buttons rendered by `base.js` (Materials vs XP
     branch).
  6. Keep everything inside the 420px app shell (`max-width: 420px`), mobile-
   first — the base grid uses `display:grid; grid-template-columns: 1fr 1fr;`.
- **Hints:**
  - Night mode must override background on `.app-container`, `body`, and card
    surfaces — test both themes in DevTools by temporarily forcing the class.
  - `custom_color` is applied inline: `el.style.color = c; el.style.textShadow = '0 0 10px ' + c` (night only) — do not bake the color into the CSS file.
  - Don't fight the service worker: it caches static hashes; hard-refresh
    (Ctrl+F5) while iterating on CSS/JS.
  - `node --check` again after any base.js markup edits (string concat bugs).
- **Done-when:** both themes render correctly at 420px; building cards show
  construction progress, color pickers, staff circles; crit has a visible pop
  animation; branch modal appears only at Lv3.

### Step 28 — Tests & Docs (final validation)

- **Goal:** prove the whole loop works + leave the docs suite truthful.
- **Files:** `core/tests.py`, `docs/01`, `docs/02`, `docs/03`, `docs/07`,
  `docs/08`, `README.md`, `flamingo_fitness/settings.py` (beat task §9, optional).
- **Do:**
  1. Implement the §10 test list (`BaseEconomyMathTests`,
     `BaseEconomyFlowTests`, `BaseAPITests`, `BaseGamificationHookTests`).
  2. Add the optional `tick_base_economy` shared task + beat schedule entry.
  3. `python manage.py test core` — all green, including every pre-existing
     test.
  4. `node --check core/static/core/js/base.js`.
  5. Docs sweep: schema additions in `docs/01`, endpoint tables in `docs/02`,
     economy math in `docs/03`; tick the Step 21–28 checkboxes in `docs/07`;
     append the decision log in `docs/08` (energy source + overflow, crit,
     streak multiplier, blueprint drops, the `last_rest_bonus_date` addition,
     the CSRF/POST lesson); update the README phase blurb.
- **Hints:**
  - Order tests smallest-first (pure math → helpers → API) so failures localize.
  - For time travel in tests, pass explicit `now=` to helpers; for the API
    layer, manipulate `construction_started_at` directly (no need for
    `freezegun`).
  - Mock `random.random` with `unittest.mock.patch` to hit both crit branches.
  - The CSRF 403 test: POST without `X-CSRFToken` must return 403 —
    assert it survives the `@require_POST` decorator (token validation happens
    in middleware *before* the view).
- **Done-when:** full suite green locally (SQLite fallback), `node --check`
  passes, `manage.py check` clean, and the docs/07 checkboxes + decision log
  reflect the implemented reality.

### Painted Phase 7 checklist (mirrors `docs/07`)

> All eight steps are **unchecked pending approval** — nothing is implemented yet.

- [ ] **Step 21 — Models:** `BaseBuildingDef`, `BaseBuilding`,
      `BaseResource` additions → migration `0004` applied.
- [ ] **Step 22 — Economy service:** `base_economy.py` (overflow-safe energy,
      rest bonus, daily harvest, production_plan, crit collect, evolve,
      modality buffs, synergies, XP bonus) + re-exports.
- [ ] **Step 23 — Gamification hooks:** XP bonus in `process_payload`,
      buffs from strength/cardio logs, blueprint drops on boss PRs.
- [ ] **Step 24 — Admin & seeding:** catalog registered + seeded incl. Lawn
      Chairs, branches, Gold Statue; demo player pre-built + blueprint.
- [ ] **Step 25 — Views & API:** eight `/base/*` endpoints + URLs + auth/CSRF.
- [ ] **Step 26 — Frontend logic:** `base.js` controller, haptics, Day/Night,
      Web Audio blips, confetti + milestone ack.
- [ ] **Step 27 — Frontend UI:** day/night CSS vars, neon glow, building
      cards/color picker/staff circles, branch modal, milestone toast.
- [ ] **Step 28 — Tests & Docs:** full suite + `node --check` + docs sweep.

### Definition of Done (acceptance view)

1. `python manage.py check` and `python manage.py test core` are green.
2. Log in as `player1` (demo): the **Base** tab opens a live Flamingo Club;
   Lawn Chairs build instantly, Cabana has a timer, energy refills, rest days
   overflow the cap, collections can crit, and building at Lv3 offers a branch.
3. A morning-vs-night load of the dashboard switches the sky and neon glow.
4. Every POST works from the PWA (CSRF token flows) and 400/403 errors render
   friendly hints.
5. `docs/07` Phase 7 checkboxes and the `docs/08` decision log reflect what is
   actually implemented.