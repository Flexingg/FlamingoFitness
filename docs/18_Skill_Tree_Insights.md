# 📊 Skill-Tree Insights: Charts + Raw Data (docs/18)

The five skill-tree panels (Hydration, Nutrition, Endurance, Strength,
Recovery) gain **two extra views** on top of their existing overview list:

- **Graph** — an interactive Chart.js (v4, UMD via jsDelivr) bar/line chart of
  that modality's history over a user-selectable **range** (`1W · 2W · 1M ·
  3M · All`), with per-day **summary chips**, goal dashboard-lines, and
  "on-target vs. needs-work" tinting.
- **Raw data** — a scrollable per-day metric table plus an expandable JSON
  dump per day, and a **Download JSON** export of the current range.

Everything is additive; the existing overview list, day cards, and detail
modals are untouched.

---

## Backend

The five `core/views.py` state views — `nutrition_state`, `hydration_state`,
`endurance_state`, `strength_state`, `recovery_state` — accept two optional
query params (both opt-in, so default responses are unchanged):

| Param | Behaviour |
|-------|-----------|
| `?days=N`   | Bounds `history` to RawActivityLogs with `occurred_at` in the newest `N` days (`_bounded_logs`). Invalid / non-positive values are ignored → all history. |
| `?raw=1`    | Adds each day's original `raw_payload` (`_raw_requested`) so the Raw view can show the true ingested JSON. |

Helpers: `_bounded_logs(request, queryset)` and `_raw_requested(request)`.

## Front-end

New shared module `core/static/core/js/insights.js` exposes
`window.FFInsights.createInsights(container, modality, data)`. It is called
from each controller's `render*` (guarded by `if (window.FFInsights)`).

- Per-modality config (`CFG`) holds the neon accent, metric/goal series,
  summary chips, raw columns, and a `goodDay` predicate.
- Ranges filter the **already-fetched** history client-side → instant switching,
  offline-friendly, no refetches.
- Chart.js builds the canvas; a goal series is drawn as a dashed line
  (`goalKey` per-day, or a constant `goalValue` like the 8h sleep target).

CSS lives in `core/static/core/css/dashboard.css` under the `insights-*` /
`raw-*` classes and is theme-aware via the existing `:root` / dark-palette
variables (Nunito font, rounded Duolingo pills, neon accents).

### Wiring

`dashboard.html` loads, in order:
1. `https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js`
2. `{% static 'core/js/insights.js' %}` (after `dashboard.js`)

Each controller (`nutrition.js`, `hydration.js`, `endurance.js`,
`strength.js`, `recovery.js`) calls `FFInsights.createInsights(content,
'<modality>', data)` at the end of its `render*`.

## API examples

```
GET /api/v1/hydration/?days=7          # last 7 days of hydration history
GET /api/v1/hydration/?days=30&raw=1   # + original payload per day (Raw view)
```

## Tests

`core/tests.py` → `InsightsAPITests` covers: the bound itself, the no-param
(all) default, invalid-`days` ignoring, `raw` payload inclusion, and that
`nutrition` / `recovery` honor `days` too.

Validate with the repo's standard commands:

```
python manage.py test core --settings=flamingo_fitness.test_settings
node --check core/static/core/js/insights.js
```
