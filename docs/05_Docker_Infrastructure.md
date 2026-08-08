🐳 Docker Infrastructure

AI Context: Reproduces `docker-compose.yml`. Deployment target is Portainer. `docker compose up --build` brings up the whole stack.

Services

- `db`: postgres:15-alpine
  - Host port `5433:5432` (avoids clashing with a local Postgres on 5432).
  - Volume `postgres_data:/var/lib/postgresql/data`.
  - Healthcheck probes `pg_isready` against the actual app DB.
- `redis`: redis:7-alpine
  - Message broker for Celery + caching.
  - Healthcheck via `redis-cli ping`.
- `web`: Django app under Gunicorn (3 sync workers), port `8000:8000`.
  - Startup command runs (in order): `migrate --noinput`, `collectstatic --noinput`, `create_demo_accounts`, then `gunicorn ...`.
  - Depends on healthy `db` and `redis`.
- `celery_worker`: `celery -A flamingo_fitness worker -l INFO`
- `celery_beat`: `celery -A flamingo_fitness beat -l INFO` (schedules polling tasks)

Managed via `env_file: .env` for every service depending on the app.

Demo Accounts

`python manage.py create_demo_accounts` is idempotent and auto-runs at web startup.

- `admin` / `adminpass123` (superuser)
- `player1` / `playerpass123`

The command also ensures a SparkyFitness `UserIntegration` exists per demo user.

`DEMO` Environment Variable

- `DEMO=True` gates demo data (SparkyFitness mock payloads, demo accounts).
- Defaults to `False` so production surfaces the real "Link SparkyFitness" CTA instead of fabricated data.
- Consumed in `flamingo_fitness/settings.py` and the service layer.

Environment Variables

Referenced from `.env`:

- POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT
- DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS
- REDIS_URL
- DEMO

Local dev note: `settings.py` uses PostgreSQL when `POSTGRES_DB` is set, otherwise falls back to SQLite (`db.sqlite3`) so `manage.py check` / tests work without Docker.
