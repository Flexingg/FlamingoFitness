⚡ SparkyFitness Integration Spec

AI Context: This is the *implemented* integration living in `core/services/sparky_client.py`. Follow the ELT pattern (Extract → Load → Transform): the poller dumps raw vendor JSON into `RawActivityLog`, then `core/services/gamification.py` converts it into `XPLedger` entries and advances the matching `SkillTree`.

Base URL: `https://fit.randalls.cc/api` — auth via `x-api-key` header. Live OpenAPI spec: `docs/sparky_fitness_open_api_spec_json.json`.

1. API Client Service (`core/services/sparky_client.py`)

`SparkyFitnessClient(MockAPIClient)` with provider = `"sparkyfitness"`.

`fetch(integration, days=2)` returns a list of `(provider, event_type, payload, occurred_at)` tuples, one per day, ready for the poller. Supported `event_type` values:

- `sleep` — SparkyFitness `/sleep/analytics`. `_sleep_hours()` prioritizes OpenAPI-documented fields `totalSleepDuration` / `timeAsleep` (integers, in **seconds** → divided by 3600). Each log carries the night's own `date` and is anchored to it (`occurred_at` = that date's midnight) — NOT "today" — so re-syncs dedup correctly.
- `nutrition` — SparkyFitness `/food-entries/range/{start}/{end}` (grouped per day).
- `hydration` — SparkyFitness `/measurements/water-intake/range` (grouped per day, water in oz).
- `endurance` — SparkyFitness `/exercise-entries/range/{start}/{end}` (grouped per day into calories + duration).
- `scale` — latest bodyweight. Primary endpoint: `GET /measurements/most-recent/weight` (the spec's purpose-built "latest measurement of a type"); fallback: `GET /measurements/check-in/latest-on-or-before-date?date={today}`. **Units:** SparkyFitness stores check-ins in the account's unit system (`GET /user-preferences` → `unit_system`); metric accounts export **kg**, which the client converts to **lb** (×2.20462) since FlamingoFitness standardizes on lbs. Emits a single `scale` log (`weight` in lb, `entry_date`, `unit`, `_id`) so `views.py _latest_bodyweight()` — used by the PR Boss panel — always has the user's most recent weight regardless of which day they last checked in.

`DEMO` behavior: with `DEMO=True` and no API key, `fetch` returns realistic demo payloads so link → poll → XP can be exercised end-to-end. With `DEMO=False` (default) and no key, it returns nothing so the UI shows the "Link SparkyFitness" CTA.

2. Polling Task (`core/tasks.py`)

`poll_sparkyfitness` runs on Celery Beat every 4 hours. It iterates active `sparkyfitness` integrations, calls `SparkyFitnessClient().fetch(integration)`, persists each tuple to `RawActivityLog` (source=`sparkyfitness`, event_type, payload, occurred_at), and immediately runs `process_log` to award XP.

**Dedup:** `ingest_results` keys rows on `(user, source, event_type, occurred_at)`, so re-syncing the same day (beat poll, manual re-link, Liftosaur re-sync) refreshes the payload instead of inserting duplicates, and XP is only awarded the first time a row is created. This is why every emitted tuple uses a day-anchored `occurred_at` (midnight of the data's own date — including sleep, which is anchored to the night's date, not "today"). Applies to nutrition, hydration, endurance, strength/PRs, sleep, and scale alike. **Self-healing:** rows ingested before dedup landed may hold several legacy duplicates per key (the old code created one per poll — e.g. 18 sleep rows for one date); ingest keeps the newest row, refreshes it, and deletes the stale extras (logged as "Collapsed N legacy duplicate row(s)") instead of raising `MultipleObjectsReturned`. Already-awarded XP is left untouched.

3. Transformation / Gamification Layer (`core/services/gamification.py`)

Registered handlers convert each `event_type`:

- `_handle_macro("macro")` → Nutrition XP (+50) & +10 materials on perfect macros.
- `_handle_hydration("hydration")` → +30 XP & +5 materials when total water >= water goal. Uses `water_intake_entries[]` (`amount`, `time`) + `water_goal`.
- `_handle_endurance("endurance")` → Endurance XP & materials from `exercise_entries[]` (see docs/03). Uses `total_calories_burned`.

4. IMPORTANT Payload Field Mappings (corrected during implementation)

The SparkyFitness OpenAPI `FoodEntry` schema uses the following field names. Match these exactly — this was previously a source of bugs:

- Meal name source is `food_name` (NOT `name`).
- The diary day key is `entry_date` (NOT `date`).
- Exercise entries use `calories_burned`, `duration_minutes`, `entry_date`, `notes`; the exercise name lives on the linked exercise (fall back to `exercise_name` then an index label).

UI-ready summaries (`summarize_nutrition`, `summarize_hydration`, `summarize_endurance`) are re-exported through `core/services/__init__.py` and consumed by the state views below.

5. Modality State Endpoints (see docs/02)

Serve the detail panels for the skill-tree nodes:

- `GET /api/v1/nutrition/` → `nutrition_state`
- `GET /api/v1/hydration/` → `hydration_state`
- `GET /api/v1/endurance/` → `endurance_state`

Each returns `{ linked, demo, today, history, skill_tree }`. To add a new one, register a view in `core/views.py`, a route in `core/urls.py`, and re-export its `summarize_*` from `core/services/__init__.py` (a forgotten re-export caused an `ImportError` → 500 on the endurance endpoint).

