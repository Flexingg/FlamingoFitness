"""Local test settings: force the SQLite fallback so `manage.py test` works
without the Docker stack (the repo `.env` points Postgres at the `db`
container host, which only resolves inside Docker).

Usage:
    python manage.py test core --settings=flamingo_fitness.test_settings
"""

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

# Fast password hashing so the suite (which creates many users) runs in
# seconds instead of minutes. Test-only - production keeps the real hashers.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
