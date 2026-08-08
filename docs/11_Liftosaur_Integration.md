🦖 Liftosaur Integration Spec

Status: IMPLEMENTED. The real API wrapper and parser live in `core/services/liftosaur_client.py`, `poll_liftosaur` in `core/tasks.py` is wired to it, and the Strength skill-tree panel (`GET /api/v1/strength/`) + PR Boss panel (`GET /api/v1/boss/`) consume it. The `BossConfig` model makes PR Boss benchmarks admin-configurable. Users enter their `lftsk_...` API key on the profile page (`GET /profile/`), which persists it to the Liftosaur `UserIntegration.credentials` and queues a **background 30-day sync** via `sync_liftosaur_for_user.delay(request.user.id)` (`core/views.py profile()`). The Celery worker (or eager mode) runs that task, fetches, and writes `RawActivityLog` rows via `core/tasks.py ingest_results`. `poll_liftosaur` runs on the same beat schedule for ongoing sync.

AI Context: This document specifies how Liftosaur data ingestion is implemented in Django Python. Following the ELT pattern, we extract raw workout history from the Liftosaur REST API (Bearer token), load it into the `RawActivityLog` JSONB `payload`, then transform/parse the Liftoscript-Workouts `text` blobs to calculate Strength XP based on volume + time, and surface per-lift PRs.

**Authoritative API reference:** `docs/liftosaur_api_spec.md` (REST API, base URL `https://www.liftosaur.com/api/v1`, Bearer auth, `/history` pagination, Liftoscript Workouts format, error contract).

1. API Client Service (core/services/liftosaur_client.py)

- `LiftosaurClient` extends `MockAPIClient`, sends `Authorization: Bearer <api_key>`.
- `_fetch_history(api_key, start_date_iso)` pages `GET /history?limit=200&startDate=...&cursor=...`, following `hasMore`/`nextCursor`.
- **Every Liftosaur response is wrapped in a `data` envelope** — e.g. `{"data": {"records": [...], "hasMore": false, "nextCursor": 42}}`. `_fetch_history` reads `records`/`hasMore`/`nextCursor` from inside that `data` key (falls back to the top level if there is no envelope). Without this unwrap a live sync silently produces 0 rows.
- `fetch(integration, days=30)` reads `integration.credentials["api_key"]`; if there is no key it returns `_demo_data()` under `settings.DEMO`, else it parses each record's `text`. Non-2xx responses (`_get`) log a warning and return `{}` so 0-row syncs are diagnosable.
- `parse_history_record_text(text)` parses each record. Real records look like:

  ```
  Squat, Barbell / 3x5 185lb, 1x3 185lb / warmup: 1x5 95lb, 1x3 135lb / target: 3x5 185lb 120s
  ```

  Completed working sets come first (comma-separated, may include `@RPE`, `+` AMRAP, `n|n` unilateral splits); named `/`-delimited sections after them (`warmup`, `target`, `sets`, `note`, …) are **excluded** from completed-set and volume totals by `_consume_sections`. Only working sets count toward `sets` / `volume_lbs` / `est_1rm`.

2. Celery Polling Task (core/tasks.py)

- `sync_liftosaur_for_user(user_id)` — one-shot, invoked on profile link. Imports `Provider` (a missing import here previously raised `NameError`, making every "Link & Sync" ingest 0 rows). It looks up the user's active Liftosaur integration, calls `LiftosaurClient().fetch(integration, days=30)`, runs `ingest_results`, and stamps `last_polled`. Returns row count or `-1` on error.
- `poll_liftosaur()` — recurring beat task that iterates all active Liftosaur integrations via the shared `_poll("liftosaur", LiftosaurClient())`.
- `ingest_results(integration, results)` — shared by both; creates one `RawActivityLog` per `(source, event_type, payload, occurred_at)` tuple, then best-effort `process_log` for XP.

3. Transformation / Gamification Layer (core/services/gamification.py)

- `summarize_strength(raw)` converts a `RawActivityLog` strength payload into a summary dict with `total_volume_lbs`, `duration_minutes`, per-exercise rows (name/sets/weight/unit/volume/est_1rm) and `xp` = `strength_xp(...)` = volume XP (`volume // 1000`) + completion bonus + `session_time_xp` (1 XP per 30 min). Rules live in `docs/03_gamification_math.md`.
- PR / Boss logic: `core/views.py GET /api/v1/strength/` aggregates best lifts; `GET /api/v1/boss/` compares the user's best lift against `BossConfig` benchmarks (bodyweight × `bodyweight_multiplier`).

Diagnostics: `_fetch_history` and `fetch` log record counts and a warning when records parse to 0 exercises (record `text` layout drift), and `_get` logs non-2xx statuses — so a blank Strength panel always explains itself in the logs.
