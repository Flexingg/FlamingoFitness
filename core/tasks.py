"""Celery background tasks (Step 11).

These iterate over active UserIntegration records, call the mock API clients,
persist the results into RawActivityLog, then run the gamification + readiness
engines so XP and readiness state stay fresh without blocking the web thread.
"""

import logging

from celery import shared_task
from django.utils import timezone

from .models import Provider, RawActivityLog, UserIntegration
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


def ingest_results(integration, results):
    """Persist fetch() result tuples into RawActivityLog and award XP.

    Shared by the Celery pollers and the profile page's Link & Sync action so
    both persist RawActivityLog rows exactly the same way. Returns the number
    of NEW log rows created.

    DEDUP: rows are keyed by (user, source, event_type, occurred_at), so
    syncing the same day twice (beat poll, manual re-link, Liftosaur re-sync)
    refreshes the payload instead of inserting a duplicate. All clients emit
    day-anchored occurred_at values (midnight of the data's own date), which
    is what makes this key stable across polls. XP is only awarded when a row
    is first created - never on refresh - which also keeps nutrition /
    hydration / endurance / strength / sleep / scale XP from being
    double-awarded on repeated syncs.

    SELF-HEALING: databases ingested before dedup landed may hold several
    legacy rows for the same key (the old code created one per poll). A plain
    update_or_create would raise MultipleObjectsReturned and crash the poller,
    so we look the rows up manually: keep the newest one, refresh its payload,
    and delete the stale extras (their XPLedger entries survive via the
    SET_NULL raw_log FK).
    """
    created = 0
    updated = 0
    purged = 0
    for source, event_type, payload, occurred_at in results:
        existing = list(
            RawActivityLog.objects.filter(
                user=integration.user,
                source=source,
                event_type=event_type,
                occurred_at=occurred_at,
            ).order_by("-created_at", "-id")
        )
        if existing:
            log = existing[0]
            log.payload = payload
            log.save(update_fields=["payload"])
            was_created = False
            if len(existing) > 1:
                stale = RawActivityLog.objects.filter(
                    pk__in=[dup.pk for dup in existing[1:]]
                )
                deleted_count, _ = stale.delete()
                purged += deleted_count
                logger.warning(
                    "Collapsed %d legacy duplicate %s row(s) for %s (%s).",
                    deleted_count,
                    event_type,
                    integration.user.username,
                    source,
                )
        else:
            log = RawActivityLog.objects.create(
                user=integration.user,
                source=source,
                event_type=event_type,
                payload=payload,
                occurred_at=occurred_at,
            )
            was_created = True
        if was_created:
            # Convert the fresh payload into XP immediately (best effort).
            try:
                process_log(log)
            except Exception:  # noqa: BLE001 - keep polling resilient
                logger.exception(
                    "XP processing failed for %s log (user=%s)",
                    event_type,
                    integration.user.username,
                )
            created += 1
        else:
            updated += 1

    if updated or purged:
        logger.info(
            "Ingest for %s (%s): %d new row(s), %d existing row(s) refreshed "
            "(duplicates skipped), %d legacy duplicate row(s) collapsed.",
            integration.user.username,
            integration.provider,
            created,
            updated,
            purged,
        )

    integration.last_polled = timezone.now()
    integration.save(update_fields=["last_polled"])
    return created


def _poll(provider, client, days=None):
    """Shared polling logic for a single provider."""
    integrations = UserIntegration.objects.filter(
        provider=provider, is_active=True
    )
    for integration in integrations:
        try:
            results = client.fetch(integration, days=days) if days else client.fetch(integration)
            ingest_results(integration, results)
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
def sync_liftosaur_for_user(user_id):
    """Immediately sync one user's Liftosaur history (last 30 days) in the
    background. Invoked from the profile page's Link & Sync so we don't block a
    Gunicorn worker with a potentially slow network call.

    Returns the number of workout days ingested, or -1 on error.
    """
    from django.contrib.auth import get_user_model

    UserModel = get_user_model()
    try:
        user = UserModel.objects.get(pk=user_id)
        integration = UserIntegration.objects.filter(
            user=user, provider=Provider.LIFTOSAUR, is_active=True
        ).first()
        if integration is None:
            logger.warning("sync_liftosaur_for_user: no active Liftosaur integration for %s", user.username)
            return -1
        results = LiftosaurClient().fetch(integration, days=30)
        count = ingest_results(integration, results)
        integration.last_polled = timezone.now()
        integration.save(update_fields=["last_polled", "updated_at"])
        logger.info(
            "sync_liftosaur_for_user(%s): ingested %d workout day(s)",
            user.username,
            count,
        )
        return count
    except Exception:  # noqa: BLE001
        logger.exception("sync_liftosaur_for_user(%s) failed", user_id)
        return -1


@shared_task
def poll_sparkyfitness():
    """Poll SparkyFitness for sleep + nutrition (every 4h via beat)."""
    _poll("sparkyfitness", SparkyFitnessClient())


@shared_task
def compute_readiness_for_all():
    """Refresh readiness for every user (daily morning beat task)."""
    from .services import compute_readiness_for_all_users

    compute_readiness_for_all_users()
