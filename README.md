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
badge you create yourself.


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
  streak / materials (gems) / energy badges shows what the stat means, how
  to earn it, and recent history of earning it (`streak`, `materials`, `energy`)
- `POST /api/v1/webhooks/home-assistant`
- Modality panels: `GET /api/v1/nutrition/`, `/api/v1/hydration/`, `/api/v1/endurance/`, `/api/v1/strength/`, `/api/v1/boss/` (incl. personal records), `/api/v1/recovery/`
- **Leagues / Challenges / Flocks (Phase 8)**: `GET /api/v1/leagues/`
  (weekly league board with tiers + history), `GET /api/v1/challenges/`
  (single active challenge — default: calories burned in the last 30 days),
  `GET /api/v1/social/?q=`, `POST /api/v1/friends/request|respond|remove`,
  `POST /api/v1/flocks/create|invite|respond|leave` (see `docs/13`)

**Phase 6 — Frontend / PWA** (`core/templates`, `core/static`)
- Django template dashboard ported from `example_html/dashboard.html`
- Vanilla JS `fetch()` rendering (`dashboard.js`, `nutrition.js`, `hydration.js`, `endurance.js`, `strength.js`, `boss.js`, `recovery.js`) + service worker + `manifest.json` + icons

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
