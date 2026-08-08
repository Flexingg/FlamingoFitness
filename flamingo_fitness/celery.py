"""Celery application configuration (Step 9).

Exposes a `celery` app bound to the `core` package so that
`celery -A flamingo_fitness worker` discovers tasks automatically.
"""

import os

from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "flamingo_fitness.settings")

app = Celery("flamingo_fitness")

# Configure from Django settings namespace CELERY_*.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in installed apps (core.tasks).
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
