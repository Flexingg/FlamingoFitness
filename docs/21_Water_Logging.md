# 💧 Manual Water Logging (Custom Bottle Sizes + Add/Remove)

Manual water logging lets a user log water against their **primary hydration
source** (Health Connect / HealthKit / SparkyFitness) with **custom bottle
sizes**, and add/remove water from today's total.

## Models

- `core.WaterBottle` — `user`, `name`, `capacity_oz`, `sort_order`. A default
  `24 oz` bottle is seeded on first hydration state load (`ensure_default_bottles`).
  Migration `0018_waterbottle`.

## Primary source

`PlayerProfile.source_preferences["hydration"]` selects the primary source
(managed under `/profile/sources/`). If unset, defaults to `sparkyfitness` when
SparkyFitness is linked, else `health_connect`.

## API

| Method | Path | Body / Notes |
|---|---|---|
| GET | `/api/v1/hydration/` | Now also returns `bottles` + `primary_source`; `history` is aggregated per day |
| POST | `/api/v1/hydration/water/add` | `{amount_oz, bottle_id?, source?}` — logs water; pushes to Sparky if primary source is SparkyFitness (linked) |
| POST | `/api/v1/hydration/water/remove` | `{amount_oz, source?}` — subtracts water (local adjustment) |
| POST | `/api/v1/hydration/bottles/` | `{bottles: [{id?, name, capacity_oz}]}` — upserts the full list (drops removed ones) |
| DELETE | `/api/v1/hydration/bottles/{id}/delete` | remove one bottle |

## Storage & gamification

- Each add/remove is a `RawActivityLog` hydration entry with a signed
  `water_intake_entries` amount; `processed=True`.
- `core.services.hydration.build_hydration_history` groups hydration logs by
  date and aggregates water. If a date has an auto-synced Sparky log, that
  log's total is authoritative (it already includes pushed water), so manual
  logs pushed to Sparky are skipped to avoid double-counting.
- XP/tokens are awarded at the **day** level (`award_day_hydration`) — idempotent
  via `XPLedger` (the day's earned XP is the delta vs what's already awarded;
  tokens are minted once per day when the day first earns a reward).

## Frontend

`core/static/core/js/hydration.js` — `buildWaterLogger()` renders a "Quick Log
Water" card (today progress, per-bottle quick-add buttons, custom add/remove,
and an expandable bottle manager) at the top of the hydration panel.

## Tests

`core/tests.py::WaterLoggingTests` — state shape, add/remove totals, day XP,
bottle upsert/delete, and validation.
