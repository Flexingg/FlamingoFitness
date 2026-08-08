"""
Django settings for the Flamingo Fitness project.

Uses environment variables (loaded from .env via python-dotenv) for secrets
and connection details. Falls back to SQLite for local, non-Docker development
so the project can be explored without a running Postgres instance.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from a .env file if present (Docker provides
# them natively via env_file, so this is a no-op there).
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


def env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Security & Core
# ---------------------------------------------------------------------------
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY", "dev-insecure-secret-key-change-me"
)
DEBUG = env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv(
        "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,web,testserver"
    ).split(",")
    if h.strip()
]

# Demo mode (Step 10): when True, SparkyFitness returns realistic demo data for
# integrations that have no API key (local dev / quick try). Off by default so
# production surfaces the real-data "Link SparkyFitness" CTA instead.
DEMO = env_bool("DEMO", False)

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "core",
]

MIDDLEWARE = [
    # WhiteNoise must stay here so Gunicorn can serve /static/ correctly
    # even in production. It must come right after SecurityMiddleware.
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "flamingo_fitness.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "flamingo_fitness.wsgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# Prefer PostgreSQL when the required env vars are present (Docker), otherwise
# fall back to a local SQLite file so `manage.py check` etc. work out of the box.
POSTGRES_DB = os.getenv("POSTGRES_DB")
if POSTGRES_DB:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": POSTGRES_DB,
            "USER": os.getenv("POSTGRES_USER", "flamingo"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "db"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Custom user model (Step 5)
AUTH_USER_MODEL = "core.User"

# Login handling. Users authenticate via a vanilla Django login page.
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files (PWA manifest, service worker, css/js live here)
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise: serve static files through Gunicorn (no nginx needed).
# In production use compressed + hashed filenames (requires collectstatic,
# which the compose web command runs). In development/tests use the plain
# storage so `{% static %}` works without a collected manifest.
if not DEBUG:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
# Cache static assets aggressively in the browser (Safe: hashed filenames).
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 365

# ---------------------------------------------------------------------------
# Redis / Celery
# ---------------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Django cache backed by Redis (used for short-lived data like readiness).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# Celery configuration
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
# Classic file-backed scheduler (no extra django-celery-beat dependency).
CELERY_BEAT_SCHEDULER = "celery.beat:PersistentScheduler"

# ---------------------------------------------------------------------------
# Celery Beat schedule (Step 12)
# ---------------------------------------------------------------------------
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # Poll Garmin/sleep & body battery every 2 hours.
    "poll-garmin-every-2-hours": {
        "task": "core.tasks.poll_garmin",
        "schedule": crontab(minute=0, hour="*/2"),
    },
    # Poll Peloton every 4 hours.
    "poll-peloton-every-4-hours": {
        "task": "core.tasks.poll_peloton",
        "schedule": crontab(minute=0, hour="*/4"),
    },
    # Poll Liftosaur every 6 hours.
    "poll-liftosaur-every-6-hours": {
        "task": "core.tasks.poll_liftosaur",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    # Poll SparkyFitness every 4 hours.
    "poll-sparkyfitness-every-4-hours": {
        "task": "core.tasks.poll_sparkyfitness",
        "schedule": crontab(minute=0, hour="*/4"),
    },
    # Recompute readiness each morning.
    "compute-morning-readiness-daily": {
        "task": "core.tasks.compute_readiness_for_all",
        "schedule": crontab(minute=15, hour=6),
    },
}

