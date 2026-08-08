"""Mock API clients (Step 10).

During development these return realistic dummy JSON payloads representing
what Garmin, Peloton and Liftosaur would actually send. Swap the bodies of
`fetch()` for real HTTP calls (using the `requests` lib and the credentials
stored on `UserIntegration`) once real API keys are available.
"""

from datetime import timedelta

from django.utils import timezone

# Human-readable provider keys (must match core.models.Provider values).
GARMIN = "garmin"
PELOTON = "peloton"
LIFTO_SAUR = "liftosaur"


class MockAPIClient:
    """Base class. Subclasses return a list of log tuples.

    Each tuple is: (provider, event_type, payload, occurred_at)
    """

    provider = None

    def fetch(self, integration):
        raise NotImplementedError


class GarminClient(MockAPIClient):
    """Simulates Garmin Connect sleep + body battery payloads."""

    provider = GARMIN

    def fetch(self, integration):
        now = timezone.now()
        last_night = now - timedelta(hours=8)
        return [
            (
                GARMIN,
                "sleep",
                {
                    "sleep_hours": 7.2,
                    "deep_pct": 22,
                    "rem_pct": 18,
                    "restlessness": 12,
                },
                last_night,
            ),
            (
                GARMIN,
                "body_battery",
                {
                    "charge": 62,  # points recovered overnight
                    "level": "high",
                    "stress_avg": 38,
                },
                now,
            ),
        ]


class PelotonClient(MockAPIClient):
    """Simulates a Peloton class summary (cardio endurance payload)."""

    provider = PELOTON

    def fetch(self, integration):
        return [
            (
                PELOTON,
                "cardio",
                {
                    "class": "45 Min Pop Ride",
                    "minutes": 45,
                    "intensity": "zone4",  # -> 1.5x multiplier
                    "output_kj": 612,
                    "calories": 487,
                },
                timezone.now(),
            )
        ]


class LiftosaurClient(MockAPIClient):
    """Simulates a programmed strength workout (volume payload)."""

    provider = LIFTO_SAUR

    def fetch(self, integration):
        return [
            (
                LIFTO_SAUR,
                "strength",
                {
                    "program": "5/3/1 Squat",
                    "volume_lbs": 15000,
                    "sets": 15,
                    "completed": True,
                    "pr": False,  # flip to True to trigger a boss-fight bonus
                },
                timezone.now(),
            )
        ]


_CLIENTS = {
    GARMIN: GarminClient,
    PELOTON: PelotonClient,
    LIFTO_SAUR: LiftosaurClient,
}


def get_client(provider):
    """Return an instantiated client for the given provider string."""
    cls = _CLIENTS.get(provider)
    if cls is None:
        raise ValueError(f"No client registered for provider: {provider}")
    return cls()
