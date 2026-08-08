"""Celery background tasks (Step 11).

These iterate over active UserIntegration records, call the mock API clients,
persist the results into RawActivityLog, then run the gamification + readiness
engines so XP and readiness state stay fresh without blocking the web thread.
"""

import logging

from celery import shared_task
from django.utils import timezone

from .models import RawActivityLog, UserIntegration
from .services import (
    GarminClient,
    LiftosaurClient,
    PelotonClient,
    SparkyFitnessClient,
    compute_readiness,
    get_client,
    process_log,
)

logger = logging.getLogger(__name__)


def _poll(provider, client):
    """Shared polling logic for a single provider."""
    integrations = UserIntegration.objects.filter(
        provider=provider, is_active=True
    )
    for integration in integrations:
        try:
            results = client.fetch(integration)
            for source, event_type, payload, occurred_at in results:
                log = RawActivityLog.objects.create(
                    user=integration.user,
                    source=source,
                    event_type=event_type,
                    payload=payload,
                    occurred_at=occurred_at,
                )
                # Convert the fresh payload into XP immediately.
                try:
                    process_log(log)
                except Exception:  # noqa: BLE001 - keep polling resilient
                    logger.exception(
                        "XP processing failed for log %s (user=%s)",
                        log.pk,
                        integration.user.username,
                    )
            integration.last_polled = timezone.now()
            integration.save(update_fields=["last_polled"])
            # Refresh the user's readiness after new Garmin data arrives.
            compute_readiness(integration.user)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Polling failed for %s integration (user=%s)",
                provider,
                integration.user.username,
            )


@shared_task
def poll_garmin():
    """Poll Garmin for sleep + body battery (every 2h via beat)."""
    _poll("garmin", GarminClient())


@shared_task
def poll_peloton():
    """Poll Peloton for cardio classes (every 4h via beat)."""
    _poll("peloton", PelotonClient())


@shared_task
def poll_liftosaur():
    """Poll Liftosaur for strength workouts (every 6h via beat)."""
    _poll("liftosaur", LiftosaurClient())


@shared_task
def poll_sparkyfitness():
    """Poll SparkyFitness for sleep + nutrition (every 4h via beat)."""
    _poll("sparkyfitness", SparkyFitnessClient())


@shared_task
def compute_readiness_for_all():
    """Refresh readiness for every user (daily morning beat task)."""
    from .services import compute_readiness_for_all_users

    compute_readiness_for_all_users()
