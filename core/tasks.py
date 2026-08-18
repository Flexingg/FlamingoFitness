"""Celery background tasks (Step 11).

These iterate over active UserIntegration records, call the mock API clients,
persist the results into RawActivityLog, then run the gamification + readiness
engines so XP and readiness state stay fresh without blocking the web thread.
"""

import logging
from datetime import date, timedelta

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

# Profile-settings "Sync history" windows. Kept to 30/365 days: deeper ranges
# mean thousands of per-day API calls for SparkyFitness (hydration/endurance
# are fetched day-by-day) and risk worker timeouts + provider rate limits.
# Garmin/Peloton remain mock-only, so backfill covers SparkyFitness + Liftosaur.
HISTORICAL_LOOKBACK_CHOICES = (30, 365)

# Days each backfill chunk covers. An explicit ``end_date`` is passed to each
# fetch() so a 365-day import drains in several bounded chunks instead of one
# enormous synchronous loop.
BACKFILL_CHUNK_DAYS = 30

# How long a backfill's in-flight lock is held. A 365-day SparkyFitness import
# issues thousands of day-by-day calls and can exceed this; when the lock
# expires a fresh job may start (a safe degradation, never a correctness issue).
BACKFILL_LOCK_TIMEOUT = 60 * 60  # seconds


def backfill_lock_key(user_id, provider):
    return f"backfill:{provider}:{user_id}"


def backfill_in_progress(user_id, provider):
    """True if a backfill for this user+provider is currently running.

    Best-effort: if the cache is unavailable we assume NOT in progress so we
    never block a legitimate import on an incidental cache outage.
    """
    from django.core.cache import cache

    try:
        return bool(cache.get(backfill_lock_key(user_id, provider)))
    except Exception:  # noqa: BLE001
        return False


def ingest_results(integration, results, award_xp=True):
    """Persist fetch() result tuples into RawActivityLog and award XP.

    Shared by the Celery pollers and the profile page's actions so both persist
    RawActivityLog rows exactly the same way. When ``award_xp=False``
    (historical backfill) rows are written but deliberately NOT converted to
    XP/tokens, and they're marked processed so they can never be converted
    retroactively. Returns the number of NEW log rows created.

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
            if award_xp:
                # Convert the fresh payload into XP immediately (best effort).
                try:
                    process_log(log)
                except Exception:  # noqa: BLE001 - keep polling resilient
                    logger.exception(
                        "XP processing failed for %s log (user=%s)",
                        event_type,
                        integration.user.username,
                    )
            else:
                # Historical/backfill import: persist the row but do NOT grant
                # XP, tokens, materials, streaks or badges. Mark it processed so
                # a later poll refresh can never convert it retroactively.
                log.processed = True
                log.save(update_fields=["processed"])
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


def _backfill(provider, user_id, days, task_name):
    """Backfill a user's integration history without awarding XP.

    Walks the most recent ``days`` of history (newest window first) in
    BACKFILL_CHUNK_DAYS chunks by passing an explicit ``end_date`` to each
    client.fetch() - clients otherwise anchor on today, so only this lets us
    reach older data. Rows are ingested with award_xp=False. Returns the number
    of RawActivityLog rows created, or -1 on error / missing integration.

    An in-flight lock (per user+provider) prevents stacking heavy imports when
    a 365-day job is already draining; the lock is best-effort (a cache outage
    must never block a legitimate import).
    """
    from django.core.cache import cache

    lock_key = backfill_lock_key(user_id, provider)
    try:
        acquired = bool(cache.add(lock_key, "1", timeout=BACKFILL_LOCK_TIMEOUT))
    except Exception:  # noqa: BLE001 - best-effort guard
        acquired = True
    if not acquired:
        logger.info("%s(%s): backfill already running, skipping", task_name, user_id)
        return 0

    try:
        from django.contrib.auth import get_user_model

        UserModel = get_user_model()
        user = UserModel.objects.get(pk=user_id)
        integration = UserIntegration.objects.filter(
            user=user, provider=provider, is_active=True
        ).first()
        if integration is None:
            logger.warning(
                "%s: no active %s integration for %s",
                task_name, provider, user.username,
            )
            return -1

        client_factory = {
            Provider.SPARKYFITNESS: SparkyFitnessClient,
            Provider.LIFTOSAUR: LiftosaurClient,
        }.get(provider)
        if client_factory is None:
            logger.warning(
                "%s: no backfill client for provider %s", task_name, provider
            )
            return -1

        end = date.today()
        remaining = max(int(days), 0)
        total = 0
        while remaining > 0:
            size = min(remaining, BACKFILL_CHUNK_DAYS)
            results = client_factory().fetch(integration, days=size, end_date=end)
            total += ingest_results(integration, results, award_xp=False)
            remaining -= size
            end = end - timedelta(days=size)

        integration.last_polled = timezone.now()
        integration.save(update_fields=["last_polled", "updated_at"])
        logger.info(
            "%s(%s): imported %d historical row(s) (no XP awarded)",
            task_name, user.username, total,
        )
        return total
    except Exception:  # noqa: BLE001
        logger.exception("%s(%s) failed", task_name, user_id)
        return -1
    finally:
        try:
            cache.delete(lock_key)
        except Exception:  # noqa: BLE001
            pass


@shared_task
def backfill_sparkyfitness_for_user(user_id, days=30):
    """Backfill up to ``days`` of SparkyFitness history for one user (no XP)."""
    return _backfill(
        Provider.SPARKYFITNESS, user_id, days, "backfill_sparkyfitness_for_user"
    )


@shared_task
def backfill_liftosaur_for_user(user_id, days=30):
    """Backfill up to ``days`` of Liftosaur workout history for one user (no XP)."""
    return _backfill(
        Provider.LIFTOSAUR, user_id, days, "backfill_liftosaur_for_user"
    )


@shared_task
def poll_sparkyfitness():
    """Poll SparkyFitness for sleep + nutrition (every 4h via beat)."""
    _poll("sparkyfitness", SparkyFitnessClient())


@shared_task
def compute_readiness_for_all():
    """Refresh readiness for every user (daily morning beat task)."""
    from .services import compute_readiness_for_all_users

    compute_readiness_for_all_users()


@shared_task
def tick_combat_daily():
    """Daily token economy + PvE/PvP maintenance (docs/15 §9).

    Idempotent (stamped by date/timestamp): mints the daily token dividend,
    refills siege stamina, clears expired buffs, and pays Gym holders their
    passive token yield. Replaces the Phase 7 ``tick_base_economy_daily``.
    """
    from .services import tick_combat_daily as _tick

    return _tick()


@shared_task
def close_league_week_task():
    """Weekly league rollover (Phase 8, docs/13 §9).

    Closes any stale open league week (snapshot ranks/tiers into
    LeagueResult + pay the top-3 rewards), then opens the current week.
    Idempotent by stored status/dates; the leagues view also runs this
    lazily, so a beat outage never loses a snapshot.
    """
    from .services import close_league_week, ensure_current_week, week_start_for
    from .models import LeagueWeek

    now = timezone.now()
    current_monday = week_start_for(timezone.localdate(now))
    closed = 0
    stale = LeagueWeek.objects.filter(
        status="open", week_start__lt=current_monday
    ).order_by("week_start")
    for week in stale:
        if close_league_week(week, now=now):
            closed += 1
    week = ensure_current_week(now=now)
    logger.info(
        "close_league_week_task: closed %d week(s); current week %s",
        closed,
        week.week_start,
    )
    return closed
