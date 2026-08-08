🐳 Docker Infrastructure

AI Context: Generate a docker-compose.yml suitable for deployment via Portainer.

Services Required

db: postgres:15-alpine

Volumes: postgres_data:/var/lib/postgresql/data

redis: redis:7-alpine

Used as the message broker for Celery and caching.

web: Django Application (Gunicorn)

Build context: .

Ports: 8000:8000

Depends on: db, redis

celery_worker: Executes background API polling tasks.

Command: celery -A flamingo_fitness worker -l INFO

Depends on: db, redis

celery_beat: Scheduler for the polling tasks (e.g., "Poll Garmin every 2 hours").

Command: celery -A flamingo_fitness beat -l INFO

Environment Variables

Ensure a .env file is referenced for: POSTGRES_USER, POSTGRES_PASSWORD, DJANGO_SECRET_KEY, and API keys.