"""Liftosaur API client (docs/11_Liftosaur_Integration.md).

A Python wrapper around the liftosaur.com/api/v1 endpoints (Bearer token auth)
that replaces the Google Apps Script sync tool. It follows the same ELT pattern
as the other providers: `fetch()` returns (provider, event_type, payload,
occurred_at) tuples for the poller to dump into RawActivityLog.

The main work is parsing each history record's `text` blob (the same format the
Apps Script `parseHistoryRecordText` + set-matching regex handled) into
exercises, sets, reps and weight, then aggregating per-workout volume and
estimating 1RMs (Epley: weight * (1 + reps/30)).

Liftosaur REST API Reference:
  - Base URL: https://www.liftosaur.com/api/v1
  - Auth: Authorization: Bearer <api_key>
  - Endpoints:
      - GET /history: Retrieve workout history records.
          - Query Params:
              - startDate: ISO 8601 date string (e.g. "2026-08-01")
              - endDate: ISO 8601 date string (optional)
              - limit: Integer (max 200, default 50)
              - cursor: Pagination cursor string from previous nextCursor response
          - Response JSON:
              - records: List of history objects [{"id": 123, "text": "..."}, ...]
              - hasMore: Boolean
              - nextCursor: String/Integer cursor for next page

Liftohistory Format Syntax Quick Reference:
  Header line:
    2026-08-08 09:14:12 +00:00 / program: "5/3/1" / dayName: "Push Day" / duration: 3350s / exercises: {
  Exercise line:
    Bench Press, Barbell / 3x8 185lb @7, 1x6 185lb / warmup: 1x10 95lb / target: 3x8 185lb 90s
  Set patterns matched:
    - Standard: 3x8 185lb
    - AMRAP: 1x5+ 185lb
    - Unilateral: 3x9|9 65lb
    - With RPE: 3x8 185lb @8+
    - Units: lb or kg
"""

import logging
import re
from datetime import date, timedelta

import requests
from django.conf import settings
from django.utils import timezone

from .api_clients import MockAPIClient

logger = logging.getLogger(__name__)

PROVIDER = "liftosaur"

BASE_URL = "https://www.liftosaur.com/api/v1"

# Conversion constant for volume standardization
KG_TO_LBS = 2.20462

# Major lifts surfaced on the PR / Boss board. exercise_match is matched
# case-insensitively against the parsed exercise name.
MAJOR_LIFTS = [
    "Bench Press",
    "Squat",
    "Deadlift",
    "Overhead Press",
    "Row",
]


def is_major_lift(exercise_name):
    """Check if an exercise matches any major lift case-insensitively.

    Future AI agents: Use this helper to filter or categorize key compound
    lifts when building PR boards, strength analytics, or leaderboards.
    """
    if not exercise_name:
        return False
    name_lower = exercise_name.lower()
    return any(major.lower() in name_lower for major in MAJOR_LIFTS)


def _epley_1rm(weight, reps):
    """Calculate Epley estimated 1RM: weight * (1 + reps / 30).

    Args:
        weight (float or int): Weight lifted in current unit.
        reps (int): Repetitions completed.

    Returns:
        float: Estimated 1RM rounded to 1 decimal place.
    """
    try:
        weight = float(weight)
        reps = int(reps)
    except (TypeError, ValueError):
        return 0.0
    if weight <= 0:
        return 0.0
    if reps <= 1:
        return round(weight, 1)
    return round(weight * (1 + reps / 30), 1)


def parse_history_record_text(text):
    """Parse a single Liftohistory text record into structured data.

    Liftohistory string format example:
      2026-08-08 09:14:12 +00:00 / program: "5/3/1 BBB" / dayName: "Week 2 - Day 4"
      / duration: 3350s / exercises: {
        Overhead Press / 1x3 105lb, 1x3 125lb, 1x3 135lb, 5x10 95lb / warmup: 1x5 50lb / target: ...
        Reverse Lunge, Barbell / 3x9|9 65lb / target: 3x9 65lb
      }

    Returns:
        dict:
            timestamp (str): Raw header timestamp string.
            program (str): Program name if present.
            day_name (str): Day name/identifier if present.
            duration_minutes (int): Workout duration converted from seconds to minutes.
            exercises (list of dict): Parsed completed exercise summaries.
    """
    text = text or ""
    out = {
        "timestamp": "",
        "program": "",
        "day_name": "",
        "duration_minutes": 0,
        "exercises": [],
    }

    # 1. Parse header timestamp (everything before the first slash)
    ts = re.match(r"^([^/]+)", text)
    if ts:
        out["timestamp"] = ts.group(1).strip()

    # 2. Extract program name: program: "..."
    prog = re.search(r'program:\s*"([^"]+)"', text)
    if prog:
        out["program"] = prog.group(1)

    # 3. Extract day name: dayName: "..."
    day = re.search(r'dayName:\s*"([^"]+)"', text)
    if day:
        out["day_name"] = day.group(1)

    # 4. Extract duration in seconds and convert to rounded minutes: duration: Ns
    dur = re.search(r"duration:\s*(\d+)s", text)
    if dur:
        try:
            out["duration_minutes"] = int(round(int(dur.group(1)) / 60))
        except (TypeError, ValueError):
            pass

    # 5. Locate exercises block: exercises: { ... }
    ex_block = re.search(r"exercises:\s*\{([\s\S]*)\}", text)
    if not ex_block:
        return out

    lines = [l.strip() for l in ex_block.group(1).split("\n") if l.strip()]

    # Regex to capture a set (handles "3x8 185lb", "3 x 8 185lb", "1x5+ 185lb",
    # "3x9|9 65lb", "3x8 185lb @8+"):
    #   Group 1: set count    Group 2: reps    Group 3: weight
    #   Group 4: unit (lb/kg)  Group 5: optional RPE
    set_regex = re.compile(
        r"(\d+)\s*x\s*(\d+)(?:\|\d+)?\+?\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?(?:\s*@(\d+(?:\.\d+)?)\+?)?"
    )
    # Exercise header on one line:  "Name / sets..."  OR  "Name: sets..."
    header_re = re.compile(r"^\s*([^/:@]+?)\s*[:/]\s*(.*)$")
    # A lone exercise header line (real-world layout): "Name:"
    bare_header_re = re.compile(r"^\s*([^/:@]+?)\s*:\s*$")
    # Sections that must NOT count toward completed volume:
    skip_sections = ("warmup", "target", "sets", "note", "notes", "rest", "restTime")

    def _consume(ex, group_str):
        """Parse a comma-separated group string of sets into the exercise dict."""
        for group in [g.strip() for g in group_str.split(",") if g.strip()]:
            m = set_regex.match(group)
            if not m:
                continue
            count = int(m.group(1)) or 1
            reps = int(m.group(2))
            weight = float(m.group(3))
            unit = m.group(4) or "lb"
            is_kg = unit.lower() == "kg"
            w_lbs = weight * KG_TO_LBS if is_kg else weight
            ex["sets"] += count
            # Track heaviest weight and its reps for display
            if weight > ex["weight"] or (weight == ex["weight"] and reps > ex["reps"]):
                ex["weight"] = weight
                ex["reps"] = reps
                ex["unit"] = unit
            ex["volume_lbs"] += w_lbs * reps * count
            set_1rm = _epley_1rm(w_lbs, reps)
            if set_1rm > ex["est_1rm"]:
                ex["est_1rm"] = set_1rm

    # A named section prefix like "warmup:" / "target:" / "sets:" / "note:".
    section_label_re = re.compile(r"^([a-zA-Z_ ]+?)\s*:\s*(.*)$")

    def _consume_sections(ex, rest):
        """Consume completed sets from an exercise line, ignoring labelled
        sections (warmup / target / sets / notes / rest) that the real API's
        record text may include after the working sets, e.g.:

            Squat, Barbell / 3x5 185lb, 1x3 185lb / warmup: 1x5 95lb / target: 3x5 185lb

        Completed sets come first and are comma-separated; named sections are
        delimited by '/' and must NOT count toward volume/set totals.
        """
        for part in rest.split("/"):
            part = part.strip()
            if not part:
                continue
            sec = section_label_re.match(part)
            if sec and sec.group(1).strip().lower() in skip_sections:
                continue
            _consume(ex, part)

    def _make_exercise(name):
        return {
            "name": name.strip(),
            "sets": 0,
            "reps": 0,
            "weight": 0.0,
            "unit": "lb",
            "volume_lbs": 0.0,
            "est_1rm": 0.0,
            "is_major_lift": is_major_lift(name),
        }

    current = None  # exercise being assembled (Format B continuation lines)
    for line in lines:
        if line.startswith("//"):
            continue

        # Format B: a lone "Name:" line begins a new exercise.
        bare = bare_header_re.match(line)
        if bare and not set_regex.search(line):
            if current is not None:
                out["exercises"].append(current)
            current = _make_exercise(bare.group(1))
            continue

        # "Name / sets..." or "Name: sets..." both on one line.
        head = header_re.match(line)
        if head:
            name = head.group(1).strip()
            rest = head.group(2).strip()
            if name.lower() in skip_sections:
                continue
            if current is not None:
                out["exercises"].append(current)
            current = _make_exercise(name)
            if rest:
                _consume_sections(current, rest)
            continue

        # Format B continuation: a bare set line (optionally prefixed with "-").
        if current is not None:
            stripped = line.lstrip("-").strip()
            if set_regex.search(stripped):
                _consume(current, stripped)

    if current is not None:
        out["exercises"].append(current)

    return out


class LiftosaurClient(MockAPIClient):
    """Wrapper for the Liftosaur REST API (liftosaur.com/api/v1).

    Uses Bearer Token authentication to fetch workout history records,
    parses Liftohistory formatted text, and converts them into standardized ELT
    RawActivityLog tuples.
    """

    provider = PROVIDER

    def __init__(self, timeout=15):
        self.timeout = timeout
        self.base_url = BASE_URL

    def _headers(self, api_key):
        return {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

    def _get(self, api_key, path, params=None):
        """Execute a GET request against the Liftosaur REST API.

        Returns parsed JSON on 200/201, otherwise ``{}``. Diagnoses failures so
        the polling/sync logs explain WHY a sync produced 0 rows.
        """
        try:
            resp = requests.get(
                f"{self.base_url}{path}",
                headers=self._headers(api_key),
                params=params,
                timeout=self.timeout,
            )
            if resp.status_code in (200, 201):
                return resp.json()
            logger.warning(
                "Liftosaur %s returned HTTP %s (params=%s). "
                "A non-2xx usually means the API key is missing/revoked or not "
                "accepted by the endpoint.",
                path,
                resp.status_code,
                params,
            )
        except requests.RequestException as exc:
            logger.warning(
                "Liftosaur %s request failed: %s. "
                "Check network/DNS/timeout from the worker container.",
                path,
                exc,
            )
        return {}

    def _fetch_history(self, api_key, start_date_iso):
        """Fetch workout history with cursor-based pagination.

        API Endpoint: GET /history
        Query Params:
            - startDate: ISO 8601 string (e.g., "2026-07-09")
            - limit: 200 (max allowed per page)
            - cursor: Next page cursor returned from previous response
        """
        records = []
        cursor = None
        has_more = True

        while has_more:
            params = {"limit": 200, "startDate": start_date_iso}
            if cursor:
                params["cursor"] = cursor

            data = self._get(api_key, "/history", params=params)
            # The Liftosaur API wraps every response in a "data" envelope, e.g.
            # {"data": {"records": [...], "hasMore": false, "nextCursor": 42}}.
            payload = data.get("data") if isinstance(data, dict) else None
            if not isinstance(payload, dict):
                payload = {}
            fetched_records = payload.get("records") or []
            records.extend(fetched_records)

            has_more = bool(payload.get("hasMore"))
            cursor = payload.get("nextCursor")

            # Safeguard against potential infinite loops if endpoint returns empty records
            if not fetched_records and not cursor:
                break

        if not records:
            logger.warning(
                "Liftosaur /history returned 0 records from %s (key may be rejected "
                "or there are no workouts in that window).",
                start_date_iso,
            )
        else:
            logger.info(
                "Liftosaur /history returned %d record(s) from %s.",
                len(records),
                start_date_iso,
            )
        return records

    def fetch(self, integration, days=30):
        """Fetch recent workout history grouped by workout day.

        Args:
            integration: Model instance containing user credentials (api_key).
            days (int): Number of days in the past to look back. Default 30.

        Returns:
            list of tuple: List of (provider, event_type, payload, occurred_at) tuples.
        """
        creds = (integration.credentials or {}) if integration else {}
        api_key = creds.get("api_key", "")

        if not api_key:
            if getattr(settings, "DEMO", False):
                return self._demo_data()
            return []

        start_date = (date.today() - timedelta(days=days)).isoformat()
        records = self._fetch_history(api_key, start_date)

        # Group history records by date string (YYYY-MM-DD extracted from timestamp)
        by_date = {}
        for record in records:
            parsed = parse_history_record_text(record.get("text"))
            ts = parsed["timestamp"]

            # Extract YYYY-MM-DD date part from ISO string or timestamp token
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", ts) if ts else None
            day_str = date_match.group(0) if date_match else date.today().isoformat()

            by_date.setdefault(day_str, []).append(parsed)

        # Diagnostic: if we fetched records but none parsed into exercises, the
        # record.text layout probably doesn't match the parser. Surfacing this
        # avoids a silent "blank" /api/v1/strength/ response.
        parsed_exercise_count = sum(
            1 for s in by_date.values() for sess in s for ex in sess["exercises"]
        )
        if records and parsed_exercise_count == 0:
            logger.warning(
                "Liftosaur: fetched %d record(s) for %s but parsed 0 exercises. "
                "The record 'text' layout may not match parse_history_record_text.",
                len(records),
                integration.user.username,
            )
        elif records:
            logger.info(
                "Liftosaur: %d record(s) -> %d exercise entries for %s.",
                len(records),
                parsed_exercise_count,
                integration.user.username,
            )

        logs = []
        for day_str, sessions in sorted(by_date.items()):
            total_volume = sum(
                ex["volume_lbs"] for s in sessions for ex in s["exercises"]
            )
            total_sets = sum(ex["sets"] for s in sessions for ex in s["exercises"])
            duration = sum(s["duration_minutes"] for s in sessions)

            program = next(
                (s["program"] for s in sessions if s.get("program")), "Workout"
            )
            day_name = next(
                (s["day_name"] for s in sessions if s.get("day_name")), ""
            )

            exercises = [
                {
                    "name": ex["name"],
                    "sets": ex["sets"],
                    "reps": ex["reps"],
                    "weight": ex["weight"],
                    "unit": ex["unit"],
                    "volume_lbs": round(ex["volume_lbs"], 1),
                    "est_1rm": ex["est_1rm"],
                    "is_major_lift": ex["is_major_lift"],
                }
                for s in sessions
                for ex in s["exercises"]
            ]

            has_major_lift = any(ex["is_major_lift"] for ex in exercises)

            logs.append(
                (
                    PROVIDER,
                    "strength",
                    {
                        "date": day_str,
                        "program": program,
                        "day_name": day_name,
                        "duration_minutes": duration,
                        "total_volume_lbs": round(total_volume, 1),
                        "volume_lbs": int(round(total_volume)),  # back-compat
                        "total_sets": total_sets,
                        "sets": total_sets,
                        "completed": True,
                        "pr": False,  # Future AI agents: implement PR comparison against past 1RM records here
                        "has_major_lift": has_major_lift,
                        "exercises": exercises,
                    },
                    _to_dt(day_str),
                )
            )

        return logs

    # -- Demo Data (fallback when no API key is provided and DEMO=True) -------
    def _demo_data(self):
        """Provide mock payload for testing and demonstration mode."""
        yesterday = date.today() - timedelta(days=1)
        return [
            (
                PROVIDER,
                "strength",
                {
                    "date": yesterday.isoformat(),
                    "program": "5/3/1",
                    "day_name": "Squat Day",
                    "duration_minutes": 55,
                    "total_volume_lbs": 15000.0,
                    "volume_lbs": 15000,
                    "total_sets": 15,
                    "sets": 15,
                    "completed": True,
                    "pr": False,
                    "has_major_lift": True,
                    "exercises": [
                        {
                            "name": "Squat",
                            "sets": 5,
                            "reps": 5,
                            "weight": 225.0,
                            "unit": "lb",
                            "volume_lbs": 5625.0,
                            "est_1rm": 262.5,
                            "is_major_lift": True,
                        },
                        {
                            "name": "Bench Press",
                            "sets": 5,
                            "reps": 5,
                            "weight": 185.0,
                            "unit": "lb",
                            "volume_lbs": 4625.0,
                            "est_1rm": 215.8,
                            "is_major_lift": True,
                        },
                        {
                            "name": "Deadlift",
                            "sets": 5,
                            "reps": 3,
                            "weight": 315.0,
                            "unit": "lb",
                            "volume_lbs": 4725.0,
                            "est_1rm": 346.5,
                            "is_major_lift": True,
                        },
                    ],
                    "demo": True,
                },
                _to_dt(yesterday),
            )
        ]


def _to_dt(day_str):
    """Return a timezone-aware datetime for the start of a given date.

    Args:
        day_str (str or datetime.date): ISO date string (YYYY-MM-DD) or date object.

    Returns:
        datetime: Timezone-aware datetime object at midnight.
    """
    if isinstance(day_str, date):
        day = day_str
    else:
        try:
            day = date.fromisoformat(str(day_str))
        except ValueError:
            day = date.today()

    naive = timezone.datetime.combine(day, timezone.datetime.min.time())
    return timezone.make_aware(naive)