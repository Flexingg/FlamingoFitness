📋 Next Steps: AI Agent Build Sequence

AI Context: This is the build sequence for Flamingo Fitness. Each completed area is marked `[x]` so a future AI knows exactly what already exists and can pick up where things left off. When starting NEW work, re-read the corresponding doc in `docs/`.

Phase 1: Infrastructure & Scaffolding

[x] Step 1: Project Initialization — Base Django project (`flamingo_fitness`) + `core` app created.
[x] Step 2: Docker Compose Setup — `docker-compose.yml` (Postgres, Redis, Web, Celery Worker, Celery Beat). See `05_Docker_Infrastructure.md`.
[x] Step 3: Dependency Management — `requirements.txt` (Django, psycopg2-binary, redis, celery, requests, gunicorn, python-dotenv).
[x] Step 4: Database Configuration — `settings.py` uses PostgreSQL via env vars, falls back to SQLite locally; Redis configured for Celery.

Phase 2: Core Data Models

[x] Step 5: User Models — Custom `User` (AbstractUser) + `UserIntegration`. See `01_Database_Schema.md`.
[x] Step 6: ELT & Ledger Models — `RawActivityLog` (JSONField) + `XPLedger`.
[x] Step 7: Gamification Models — `SkillTree` + `DailyReadiness` (+ `BaseResource`).
[x] Step 8: Django Admin — `admin.py` for all models; initial migrations created.
[ ] Step 8b: Add a `season`/`weekly leaderboard reset` model when weekly competitions are formalized.

Phase 3: Data Ingestion & Async Workers

[x] Step 9: Celery Configuration — `celery.py` + task registration; Redis broker.
[x] Step 10: Mock API Clients — `core/services/api_clients.py` (mock Garmin, Peloton, Liftosaur) + `core/services/sparky_client.py` (real SparkyFitness wrapper).
[x] Step 11: Polling Tasks — `core/tasks.py` (`poll_garmin`, `poll_peloton`, `poll_liftosaur`, `poll_sparkyfitness`, `compute_readiness_for_all`).
[x] Step 12: Celery Beat Schedule — configured in `settings.py`.

Phase 4: Gamification Service Layer

[x] Step 13: XP Calculator Service — `core/services/gamification.py` (endurance, strength, recovery, nutrition, hydration handlers). See `03_Gamification_Math.md`.
[x] Step 14: Skill Tree Progression — `apply_to_skill_tree` advances `SkillTree` on each XPLedger entry.
[x] Step 15: Readiness Engine — `core/services/readiness.py` → `DailyReadiness` (rest day / train).

Phase 5: API Endpoints

[x] Step 16: Dashboard API — `GET /api/v1/dashboard/state`.
[x] Step 17: Leaderboard API — `GET /api/v1/leaderboard/weekly`.
[x] Step 18: Home Assistant Webhook — `POST /api/v1/webhooks/home-assistant`.
[x] Step 16b: Modality state APIs — `GET /api/v1/nutrition/`, `GET /api/v1/hydration/`, `GET /api/v1/endurance/`, `GET /api/v1/strength/`, `GET /api/v1/boss/` (see `02_API_Contracts.md`).

Phase 6: Frontend Integration & PWA

[x] Step 19: Django Templates — dashboard served from `core/templates/core/dashboard.html`; login/signup/profile templates added.
[x] Step 20: Vanilla JS Data Fetching & PWA — `dashboard.js` fetches `/dashboard/state`; `manifest.json` + `service-worker.js` registered (see `04_Frontend_Architecture.md`).
[x] Step 20b: Modality detail views — Nutrition, Hydration, Endurance panels with XP progress bars, today cards, and clickable day-detail modals.

Current Focus / Likely Next Work

- [x] Recovery (sleep) skill-tree detail panel — DONE: the green Recovery node opens a detail view (`js/recovery.js` + `recovery-view` in `dashboard.html`) fed by `GET /api/v1/recovery/` (readiness score, sleep history, Recovery skill tree).
- [x] `GET /api/v1/recovery/` — DONE, mirrors the Nutrition/Hydration/Endurance/Strength pattern.
- DRAFT awaiting review: **Phase 7 Base-Building Meta-Game** plan lives in `docs/09_Base_Building_Meta_Game.md` (Steps 21–28 below). The bottom-nav "Base" tab, `BaseResource` wallet, and energy/time-speedup sinks are the core gaps.
- Seed default `BossConfig` entries via a data migration or management command (currently configured in the admin).

Phase 7: Base-Building Meta-Game ("The Flamingo Club")

Detailed spec: `docs/09_Base_Building_Meta_Game.md` (DRAFT — reformatted, with
a step-by-step coding plan). Checkboxes below are the build order from that doc;
they stay unchecked until the draft is approved.

[ ] Step 21: Models — `BaseBuildingDef` (catalog: costs, duration, affinity,
    blueprint gate, branch_choices, rest-day add) + `BaseBuilding` (instance:
    levels, construction timer, custom_color, staff) + `BaseResource`
    (energy_updated_at, last_daily_harvest, last_rest_bonus_date, blueprints,
    active_buffs, last_milestone_celebrated). `makemigrations core && migrate`.
[ ] Step 22: Economy service — `core/services/base_economy.py`: overflow-safe
    energy refill, rest-day bonus, daily XP→materials harvest, production_plan
    (streak/staff/modality-buff multipliers), 5% crit collect, building evolve,
    synergy evaluation, XP bonus cap; re-exports in `services/__init__.py`.
[ ] Step 23: Gamification hooks — `base_xp_bonus_pct` scaling in
    `process_payload`; strength/cardio workout logs set 24h modality buffs;
    boss-PR strength logs roll a `golden_flamingo` blueprint drop.
[ ] Step 24: Admin + seeding — register both models; seed full catalog
    (Lawn Chairs micro-build, Cabana + branches, Juice Bar, Recovery Pool,
    Pool Deck, VIP Lounge, Gold Statue) and demo instances in
    `create_demo_accounts`.
[ ] Step 25: Base API — `GET /api/v1/base/` + `POST /base/start`, `/base/speedup`,
    `/base/collect` (crit response), `/base/customize`, `/base/staff`,
    `/base/evolve`, `/base/milestone`; wire in `core/urls.py`, auth + CSRF.
[ ] Step 26: Frontend logic — `js/base.js` controller (`loadBase`/render/action
    funcs), haptics (`navigator.vibrate` in the click handler), client-time
    day/night `body` class, Web-Audio pop/cash blips, canvas-confetti +
    milestone ack; CSRF header on every POST.
[ ] Step 27: Frontend UI — dashboard.css day/night vars (`--bg-sky`, neon
    glow), wallet band + energy meter, building cards (progress, color picker,
    staff circle), Level-3 branch modal, milestone toast; base-view section +
    nav-base tab in `dashboard.html`.
[ ] Step 28: Tests & Docs — pure-math + DB + API + gamification tests
    (`manage.py test core`), `node --check base.js`, docs sweep
    (`docs/01/02/03/07/08` + README).