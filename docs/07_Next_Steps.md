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

- Recovery (sleep) skill-tree detail panel — the Recovery node exists in the skill tree but has no dedicated state endpoint or detail view yet.
- Formalize the Base-Building meta-game UI (materials/energy already tracked in `BaseResource`).
- Add `GET /api/v1/recovery/` to mirror the Nutrition/Hydration/Endurance/Strength pattern.
- Seed default `BossConfig` entries via a data migration or management command (currently configured in the admin).