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
- `POST /api/v1/webhooks/home-assistant`
- Modality panels: `GET /api/v1/nutrition/`, `/api/v1/hydration/`, `/api/v1/endurance/`, `/api/v1/strength/`, `/api/v1/boss/`

**Phase 6 — Frontend / PWA** (`core/templates`, `core/static`)
- Django template dashboard ported from `example_html/dashboard.html`
- Vanilla JS `fetch()` rendering (`dashboard.js`, `nutrition.js`, `hydration.js`, `endurance.js`, `strength.js`, `boss.js`) + service worker + `manifest.json` + icons

## Testing

```powershell
.venv\Scripts\python manage.py test core
```

The suite covers the XP math (endurance/strength/sleep/body-battery/nutrition),
the gamification flow (PR boss bonuses, level-ups, materials), the readiness
thresholds, and the API endpoints.

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
