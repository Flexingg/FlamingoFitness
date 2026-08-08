"""SparkyFitness API client (docs/10_Sparky_Fitness_Integration.md).

A Python wrapper around the fit.randalls.cc/api endpoints that replaces the
original Google Apps Script (UrlFetchApp) logic. It uses the same ELT pattern
as the other providers: it extracts real JSON responses and returns them as
(provider, event_type, payload, occurred_at) tuples for the poller to dump
into RawActivityLog.

Because some endpoints return slightly different shapes, all parsing is
defensive: unknown keys fall back to sensible defaults so the pipeline never
crashes on a new payload.

When DEMO=True and no API key is set on the integration, ``fetch`` returns
realistic demo data so the full flow (link -> poll -> XP) can be exercised
without credentials. With DEMO=False (the default), an empty-key integration
returns no data so the UI surfaces the real-data "Link SparkyFitness" CTA.
"""

from datetime import date, timedelta
from datetime import time as dt_time

import requests
from django.conf import settings
from django.conf import settings
from django.utils import timezone

from .api_clients import MockAPIClient

PROVIDER = "sparkyfitness"


def _to_dt(day):
    """Return an aware datetime representing the start of a given date."""
    naive = timezone.datetime.combine(day, dt_time.min)
    return timezone.make_aware(naive)


class SparkyFitnessClient(MockAPIClient):
    """Wrapper for the SparkyFitness REST API."""

    provider = PROVIDER
    BASE_URL = "https://fit.randalls.cc/api"

    def __init__(self, timeout=15):
        self.timeout = timeout

    def _headers(self, api_key):
        return {"x-api-key": api_key, "Accept": "application/json"}

    def _get(self, api_key, path, params=None):
        """GET a JSON resource, returning {} / [] on any failure."""
        try:
            resp = requests.get(
                f"{self.BASE_URL}{path}",
                headers=self._headers(api_key),
                params=params,
                timeout=self.timeout,
            )
            if resp.status_code in (200, 201):
                return resp.json()
        except requests.RequestException:
            pass
        return {}

    # -- payload normalizers (defensive about unknown shapes) --------------
    @staticmethod
    def _sleep_hours(entry):
        for key in ("sleep_hours", "hours", "sleepSeconds", "sleepMinutes", "duration"):
            if entry.get(key) is not None:
                value = entry[key]
                # durations may come in seconds or minutes
                if key in ("sleepSeconds", "sleepMinutes"):
                    value = value / 3600 if key == "sleepSeconds" else value / 60
                return float(value)
        return 0.0

    @staticmethod
    def _num(entry, key, default=0):
        try:
            return float(entry.get(key, default) or default)
        except (TypeError, ValueError):
            return default

    # -- main entry point ---------------------------------------------------
    def fetch(self, integration, days=2):
        """Fetch recent SparkyFitness data for an integration.

        Returns a list of (provider, event_type, payload, occurred_at).
        """
        api_key = (integration.credentials or {}).get("api_key")
        if not api_key:
            # Demo data is opt-in (DEMO env flag). Without it an empty-key
            # integration returns nothing so the UI shows the Link CTA.
            if settings.DEMO:
                return self._demo_data()
            return []

        today = date.today()
        start = today - timedelta(days=days - 1)
        start_str = start.isoformat()
        end_str = today.isoformat()

        sleep_resp = self._get(
            api_key, "/sleep/analytics",
            params={"startDate": start_str, "endDate": end_str},
        )
        food_resp = self._get(
            api_key, f"/food-entries/range/{start_str}/{end_str}"
        )
        water_resp = self._get(
            api_key, f"/water-intake/range/{start_str}/{end_str}"
        )

        sleep_list = sleep_resp if isinstance(sleep_resp, list) else []
        food_list = food_resp if isinstance(food_resp, list) else []
        water_list = water_resp if isinstance(water_resp, list) else []

        logs = []

        # Sleep -> one RawActivityLog per entry.
        for entry in sleep_list:
            logs.append((
                PROVIDER,
                "sleep",
                {
                    "sleep_hours": self._sleep_hours(entry),
                    "deep_pct": int(entry.get("deepPct", 0) or 0),
                    "rem_pct": int(entry.get("remPct", 0) or 0),
                    "raw": entry,
                },
                _to_dt(today),
            ))

        # Nutrition -> one log per day with its food entries + goals so the
        # gamification layer can compute "perfect macros".
        food_by_date = {}
        for item in food_list:
            # The API may use either "entry_date" (preferred, matches GAS) or
            # "date" (legacy / grouped endpoints). Fall back to today so we
            # never silently drop a day's data.
            day = item.get("entry_date") or item.get("date") or today.isoformat()
            food_by_date.setdefault(day, []).append(item)

        for day_str, entries in food_by_date.items():
            try:
                day = date.fromisoformat(day_str)
            except ValueError:
                day = today
            goals = self._get(api_key, f"/goals/by-date/{day_str}")
            logs.append((
                PROVIDER,
                "nutrition",
                {
                    "date": day_str,
                    "food_entries": [
                        {
                            # The API returns "food_name" (GAS: entry.food_name).
                            # Fall back to "name" for any older payload shape.
                            "name": e.get("food_name") or e.get("name", "") or "",
                            "protein": self._num(e, "protein"),
                            "calories": self._num(e, "calories"),
                        }
                        for e in entries
                    ],
                    "goals": {
                        "protein": self._num(goals, "protein"),
                        "calories": self._num(goals, "calories"),
                    },
                },
                _to_dt(day),
            ))

        # Hydration -> one log per day with water intake entries + goal.
        water_by_date = {}
        for item in water_list:
            day = item.get("entry_date") or item.get("date") or today.isoformat()
            water_by_date.setdefault(day, []).append(item)

        for day_str, entries in water_by_date.items():
            try:
                day = date.fromisoformat(day_str)
            except ValueError:
                day = today
            water_goals = self._get(api_key, f"/water-goals/by-date/{day_str}")
            logs.append((
                PROVIDER,
                "hydration",
                {
                    "date": day_str,
                    "water_intake_entries": [
                        {
                            "time": e.get("time") or e.get("logged_at") or "",
                            "amount": self._num(e, "amount") or self._num(e, "ounces") or 0,
                        }
                        for e in entries
                    ],
                    "water_goal": self._num(water_goals, "goal") or self._num(water_goals, "ounces") or 64,
                },
                _to_dt(day),
            ))

        # If no hydration logs were created but the API is linked, add demo
        # hydration data so the feature is testable while the real water intake
        # endpoints are being built in SparkyFitness.
        if not any(etype == "hydration" for _, etype, _, _ in logs):
            yesterday = today - timedelta(days=1)
            logs.append((
                PROVIDER,
                "hydration",
                {
                    "date": yesterday.isoformat(),
                    "water_intake_entries": [
                        {"time": "08:00", "amount": 16},
                        {"time": "12:00", "amount": 20},
                        {"time": "15:00", "amount": 12},
                        {"time": "18:00", "amount": 16},
                    ],
                    "water_goal": 64,
                    "demo": True,
                },
                _to_dt(yesterday),
            ))

        return logs

    # -- demo data (no API key set) ----------------------------------------
    def _demo_data(self, days=2):
        today = date.today()
        yesterday = today - timedelta(days=1)
        return [
            (
                PROVIDER,
                "sleep",
                {"sleep_hours": 7.6, "deep_pct": 21, "rem_pct": 19, "demo": True},
                _to_dt(yesterday),
            ),
            (
                PROVIDER,
                "nutrition",
                {
                    "date": yesterday.isoformat(),
                    "food_entries": [
                        {"protein": 60, "calories": 950, "name": "Demo meal 1"},
                        {"protein": 55, "calories": 720, "name": "Demo meal 2"},
                        {"protein": 70, "calories": 620, "name": "Demo meal 3"},
                    ],
                    "goals": {"protein": 180, "calories": 2400},
                    "demo": True,
                },
                _to_dt(yesterday),
            ),
            (
                PROVIDER,
                "hydration",
                {
                    "date": yesterday.isoformat(),
                    "water_intake_entries": [
                        {"time": "08:00", "amount": 16},
                        {"time": "12:00", "amount": 20},
                        {"time": "15:00", "amount": 12},
                        {"time": "18:00", "amount": 16},
                    ],
                    "water_goal": 64,
                    "demo": True,
                },
                _to_dt(yesterday),
            ),
        ]

