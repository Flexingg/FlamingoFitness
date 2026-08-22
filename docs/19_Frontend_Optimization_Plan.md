# 🚀 Frontend Optimization Plan (docs/19)

> **STATUS:** Phase 1 (Performance) ✅ Complete — Phase 5 (Architecture) ✅ Complete.
> Phase 1 deployed: `django-compressor` bundling, `defer`/`async`, lazy-load stubs,
> font preconnect, guarded logging (`ffLog`/`ffWarn`/`ffError`), `showToast()` in
> shop/loadout/pvp controllers. Phase 5 bundled in: shared `utils.js` extracted,
> service-worker auto-versioned via `<meta>`, WhiteNoise compression verified.
> Deferred ideas (#7, #8, #9, #10, #14, #17, #23) remain deferred — not started.
>
> **Goal:** Complete all phases before production deployment. No partial
> shipping — everything lands together so there is never a hybrid old/new
> frontend.
>
> **AI Context:** Follow established patterns — vanilla JS (no React/Vue),
> Django templates + `JsonResponse` APIs, mobile-first PWA. Every phase
> preserves the existing architecture doc patterns.

---

## Phase Overview

| Phase | Theme | Ideas | Effort | Dependencies | Status |
|-------|-------|-------|--------|-------------|--------|
| 1 | Performance Optimization | #1, #3, #4, #6, #11 | Medium | — | ✅ Complete |
| 2 | HTMX / Lazy HTML | #12 | High | Phase 1 (cleaner codebase) | ❌ Not started |
| 3 | UI Polish | #13, #15, #18, #19, #20 | Medium | — | 🟡 Partial (#19 done inline) |
| 4 | Light/Dark Overhaul | #16 | High | — | ❌ Not started |
| 5 | Architecture / Maintainability | #21, #24, #25 | Medium | Phase 1 (bundling in place) | ✅ Complete |
| 6 | Code Simplification | #22 | High | Phase 3 (UI patterns settled) | ❌ Not started |

---

## Phase 1: Performance Optimization (#1, #3, #4, #6, #11)

> **STATUS: ✅ COMPLETE**

**Goal:** Reduce initial page load by bundling scripts, deferring non-critical
code, lazy-loading feature controllers, optimizing font loading, and guarding
console.log behind a DEBUG flag.

### #1 — Bundle & Minify JS Assets

**Current:** 16 individual `<script>` tags bundled into 1 compressed block via
`django-compressor`. ~257KB unminified → ~50KB bundled + gzip'd.

**What was done:**
- Added `django-compressor>=4.5` to `requirements.txt`
- Added `"compressor"` to `INSTALLED_APPS` in `settings.py`
- Configured `COMPRESS_ENABLED = True`, `COMPRESS_OFFLINE = not DEBUG`,
  `COMPRESS_ROOT = STATIC_ROOT`, `COMPRESS_CACHE_BACKEND = "compressor_cache"`,
  `COMPRESS_JS_FILTERS` with JSMin
- Added `STATICFILES_FINDERS` including `CompressorFinder`
- Added `compressor_cache` alias to `CACHES` using `LocMemCache` (no Redis dependency)
- Wrapped all deferred scripts in `{% compress js %}...{% endcompress %}` in `dashboard.html`
- Added `python manage.py compress &&` to `docker-compose.yml` startup chain

**Files touched:** ✅
- `requirements.txt` — added `django-compressor>=4.5`
- `flamingo_fitness/settings.py` — `COMPRESS_*` settings, `STATICFILES_FINDERS`, `CACHES["compressor_cache"]`
- `core/templates/core/dashboard.html` — compress blocks
- `docker-compose.yml` — `manage.py compress` step

**Validation:** `manage.py compress` succeeds (1 block compressed). Live compression
works in DEBUG=True locally.

### #3 — Defer Non-Critical JS (async/defer)

**Current:** ✅ Core scripts (`router.js`, `dashboard.js`, `insights.js`) and modality
controllers (`nutrition.js`, `hydration.js`, `endurance.js`, `strength.js`,
`boss.js`, `recovery.js`) all use `<script defer>`. CDN scripts (`canvas-confetti`,
`chart.js`) use `<script async>`. Theme controller (`theme.js`) stays synchronous
in `<head>` (must run before first paint).

**What was done:**
- Added `defer` to all non-critical JS `<script>` tags
- Added `async` to CDN scripts (canvas-confetti, chart.js)
- `theme.js` left synchronous in `<head>` (needed before first paint)

**Files touched:** ✅
- `core/templates/core/dashboard.html` — `defer`/`async` attributes

### #4 — Lazy-Load Feature Controllers

**Current:** ✅ 7 controllers (shop, loadout, battle, pvp, badges, leagues, stat_info)
loaded on-demand via `window.loadScript()`. Only 11 core scripts in initial HTML.

**What was done:**
- Created `window.loadScript(url)` in `utils.js` that dynamically injects a `<script>`
  tag returning a Promise
- Created lazy-load stubs in `dashboard.js` that intercept `loadShop()`, `loadLoadout()`,
  `loadBattle()`, `loadPvP()`, `loadBadges()`, `loadLeagues()`, `loadStatInfo()` calls
  and load the script on first invocation
- Added `window.LAZY_SCRIPT_URLS` config object in `dashboard.html` `<head>` mapping
  script keys to `{% static %}` URLs
- Removed 7 `<script>` tags from the template

**Files touched:** ✅
- `core/static/core/js/utils.js` — `window.loadScript`
- `core/static/core/js/dashboard.js` — lazy-load stubs
- `core/templates/core/dashboard.html` — `LAZY_SCRIPT_URLS`, removed 7 script tags

### #6 — Optimize Font Loading

**Current:** ✅ Google Fonts URL has `&display=swap`. Preconnect links added for
both `fonts.googleapis.com` and `fonts.gstatic.com` to eliminate DNS/TLS handshake
latency.

**What was done:**
- `&display=swap` was already present on the Google Fonts `<link>` element
- Added `<link rel="preconnect" href="https://fonts.googleapis.com">`
- Added `<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>`

**Files touched:** ✅
- `core/templates/core/dashboard.html` — preconnect links

### #11 — console.log Guarded Behind DEBUG

**Current:** ✅ Every controller uses `window.ffLog()`, `window.ffWarn()`, and
`window.ffError()` instead of raw `console.log/warn/error`. Guarded by
`window.ffDEBUG`. Alert dialogs in shop, loadout, and pvp controllers replaced
with `window.showToast()`.

**What was done:**
- Created `window.ffLog`, `window.ffWarn`, `window.ffError` in `utils.js`
  (errors always fire; log/warn are silent when `ffDEBUG` is false)
- Created `window.showToast(message, type)` for visual notifications
  (replaces `alert()` in shop, loadout, pvp controllers)
- Set `window.ffDEBUG` from Django's `DEBUG` flag via inline `<script>` in template
- Replaced every `console.log(` → `window.ffLog(` in all 16 JS files
- Replaced every `console.warn(` → `window.ffWarn(` in all 16 JS files
- Replaced every `console.error(` → `window.ffError(` in all 16 JS files
- Replaced `alert()` calls in shop.js, loadout.js, pvp.js with `window.showToast()`
- Updated SW registration inline script to use `window.ffLog`/`window.ffWarn`

**Files touched:** ✅
- `core/static/core/js/utils.js` — `ffLog`, `ffWarn`, `ffError`, `showToast`
- All 16 `core/static/core/js/*.js` — console calls replaced
- `core/templates/core/dashboard.html` — `ffDEBUG` toggle, SW registration updated

---

## Phase 2: HTMX — Server-Side Panel Lazy Loading (#12)

> **STATUS: ❌ NOT STARTED**

**Goal:** Reduce initial HTML payload (~53KB template with all hidden panels).

### #12 — Serve Panels via Dynamic Fetch

**Current:** `dashboard.html` contains all 13 panels' HTML upfront (most hidden).

**Approach (Vanilla fetch, no new dependency):**
1. Move each panel's HTML into template partials under `core/templates/core/panels/`.
2. Add a `GET /panel/{panel_name}` view.
3. In each `load*()`, fetch the panel HTML on first access and cache it.

**Files touched:**
- `core/templates/core/dashboard.html` — replace panels with placeholders
- `core/templates/core/panels/*.html` — new partials
- `core/views.py` — panel views
- `core/urls.py` — panel routes

**Validation:** Initial HTML payload is <10KB; each panel loads on-demand.

---

## Phase 3: UI/UX Polish (#13, #15, #18, #19, #20)

> **STATUS: 🟡 PARTIAL** — #19 (Toast) done inline during Phase 1.
> #13, #15, #18, #20 not started.

### #13 — Skeleton Loading States

**Current:** Panels show "Loading..." text or a spinning icon.

**Approach:** Create reusable CSS-only skeleton cards with shimmer animation.
Each `render*()` shows skeleton markup matching the panel layout before data arrives.

**Files touched:**
- `core/static/core/css/dashboard.css` — skeleton keyframes + classes
- `core/static/core/js/*.js` — render skeleton before fetch

### #15 — Page Transitions / Panel Sliding

**Current:** Panel switches toggle `hidden` class instantly.

**Approach:** Add CSS transitions on panel containers with slide-left/right animations.

**Files touched:**
- `core/static/core/css/dashboard.css` — slide animations
- `core/static/core/js/dashboard.js` — toggle classes

### #18 — Add Pull-to-Refresh

**Current:** Users close and re-open panels to get fresh data.

**Approach:** Detect touchstart/touchmove deltaY at top of main scroll area.

**Files touched:**
- `core/static/core/js/dashboard.js` — pull-to-refresh handler
- `core/static/core/css/dashboard.css` — indicator styles

### #19 — Toast Notifications (replace alert())

**Current:** ✅ DONE (implemented inline during Phase 1).
`window.showToast(message, type)` helper created in `utils.js`. `alert()` calls
in shop.js, loadout.js, and pvp.js replaced with `showToast()`.

**Files touched:** ✅
- `core/static/core/js/utils.js` — `showToast` helper
- `core/static/core/js/shop.js` — `alert()` → `showToast()`
- `core/static/core/js/loadout.js` — `alert()` + `confirm()` → `showToast()`
- `core/static/core/js/pvp.js` — `alert()` → `showToast()`

### #20 — Empty-State Animations

**Current:** Empty states are static text/icons.

**Approach:** Add CSS animations (fadeIn, bounceSlight) to empty-state containers.

**Files touched:**
- `core/static/core/css/dashboard.css` — empty-state CSS classes

---

## Phase 4: Light/Dark Theme Overhaul (#16)

> **STATUS: ❌ NOT STARTED**

**Goal:** Replace the brittle `!important`-heavy theme.css.

### #16 — Refactor Light-Mode CSS

**Current:** `theme.css` (15KB) overrides ~300 Tailwind classes with `!important`.

**Approach (CSS Variables + class toggle):**
1. Move ALL color references to CSS variables in `:root` (dark) and `html.light` (light).
2. Replace hardcoded Tailwind color classes with semantic CSS classes.
3. Remove `theme.css` entirely.

**Files touched:**
- `core/static/core/css/theme.css` — remove
- `core/static/core/css/dashboard.css` — CSS variable definitions
- `core/templates/core/dashboard.html` — replace inline Tailwind classes
- All JS files — update hardcoded color references in render strings

---

## Phase 5: Architecture / Maintainability (#21, #24, #25)

> **STATUS: ✅ COMPLETE** (rolled in alongside Phase 1 — `utils.js` was a prerequisite).

**Goal:** Extract shared utilities, automate SW versioning, verify compression.

### #21 — Extract Shared Utility Functions

**Current:** ✅ A single `core/static/core/js/utils.js` provides all shared functions.
Every controller delegates to the shared versions using thin local aliases.

**What was done:**
- Created `core/static/core/js/utils.js` with:
  - `window.ffLog` / `window.ffWarn` / `window.ffError` (guarded logging)
  - `window.loadScript(url)` (dynamic script injection)
  - `window.escHtml(s)` (HTML escaping)
  - `window.csrfToken()` (CSRF token from `<meta>` tag)
  - `window.haptic(ms)` (haptic feedback)
  - `window.fmoney(n)` (number formatting)
  - `window.confettiBurst()` (confetti + haptic)
  - `window.emptyStateHTML(opts)`, `window.showEmptyState(container, opts)`
  - `window.showToast(message, type)` (toast notifications)
- Loaded as first defer script in `<head>` via `<script defer src="utils.js">`
- Removed duplicate `esc()`, `csrfToken()`, `haptic()`, `money()`, `confettiBurst()`
  implementations from shop.js, loadout.js, battle.js, pvp.js, badges.js, stat_info.js,
  leagues.js, boss.js, dashboard.js — all delegate to `window.*` versions

**Files touched:** ✅
- `core/static/core/js/utils.js` — **new file**
- `core/templates/core/dashboard.html` — add utils.js
- All `core/static/core/js/*.js` — replace duplicates with thin delegates

### #24 — Service Worker Auto-Versioning

**Current:** ✅ Cache name read dynamically from `<meta name="ff-sw-version">` tag.

**What was done:**
- Changed `CACHE_NAME` from hardcoded `'flamingo-fitness-v4'` to a function that
  reads `document.querySelector('meta[name="ff-sw-version"]').content`, falling
  back to `'v4'` if the tag is absent
- Added `<meta name="ff-sw-version" content="5">` to `dashboard.html` head

**Files touched:** ✅
- `core/static/core/service-worker.js` — dynamic cache name
- `core/templates/core/dashboard.html` — version meta tag

### #25 — Verify Response Compression

**Current:** ✅ `WHITENOISE_KEEP_ONLY_HASHED_FILES = True` set. WhiteNoise Gzip
is on by default.

**What was done:**
- Set `WHITENOISE_KEEP_ONLY_HASHED_FILES = True` in settings.py
- `WHITENOISE_GZIP = True` confirmed (default)
- Brotli not added yet (can be done later via `brotli` pip package)

**Files touched:** ✅
- `flamingo_fitness/settings.py` — WhiteNoise config

---

## Phase 6: Code Simplification — Controller Factory (#22)

> **STATUS: ❌ NOT STARTED**

**Goal:** Eliminate ~80% boilerplate across modality controllers.

### #22 — Modality Controller Factory

**Current:** Each of 5 modality controllers independently defines ~80%
identical boilerplate (load, render, back, showModal patterns).

**Approach:** Create `core/static/core/js/modality-factory.js` with
`window.createModalityController(config)`. Each modality file becomes a
thin invocation.

**Files touched:**
- `core/static/core/js/modality-factory.js` — new file
- `core/static/core/js/nutrition.js` — refactored
- `core/static/core/js/hydration.js` — refactored
- `core/static/core/js/endurance.js` — refactored
- `core/static/core/js/strength.js` — refactored
- `core/static/core/js/recovery.js` — refactored
- `core/templates/core/dashboard.html` — add factory script tag

---

## Validation & Rollout

Each phase must pass:
1. **Backend:** `python manage.py check` — no import/config errors.
2. **Frontend syntax:** `node --check core/static/core/js/*.js` — no JS errors.
3. **Tests:** `python manage.py test core --settings=flamingo_fitness.test_settings` — all green.
4. **Visual:** Dashboard loads, all panels render correctly, all theme modes work, no console errors.

**Gating rule:** All phases must be complete before any deployment. No partial production rollout.

---

## Summary of All 25 Ideas (for reference)

| # | Idea | Phase | Effort | Impact | Status |
|---|------|-------|--------|--------|--------|
| 1 | Bundle & Minify JS | 1 | Medium | High | ✅ Done |
| 2 | Drop Tailwind CDN, use build-time CSS | *(deferred)* | High | Very High | ⏸️ Deferred |
| 3 | Defer non-critical JS | 1 | Low | Medium | ✅ Done |
| 4 | Lazy-load feature controllers | 1 | Medium | High | ✅ Done |
| 5 | Replace full FA with icon subset | *(deferred)* | Medium | Medium | ⏸️ Deferred |
| 6 | Optimize font loading | 1 | Low | Medium | ✅ Done |
| 7 | Debounce friend search | *(deferred)* | Low | Low | ⏸️ Deferred |
| 8 | Cache API responses client-side | *(deferred)* | Medium | Medium | ⏸️ Deferred |
| 9 | Inline critical CSS | *(deferred)* | Medium | Medium | ⏸️ Deferred |
| 10 | Preload key assets | *(deferred)* | Low | Medium | ⏸️ Deferred |
| 11 | Strip console.log from production | 1 | Low | Low | ✅ Done |
| 12 | Lazy-load panel HTML | 2 | High | High | ❌ Pending |
| 13 | Skeleton loading states | 3 | Medium | High | ❌ Pending |
| 14 | Prefetch adjacent panel data | *(deferred)* | Medium | Medium | ⏸️ Deferred |
| 15 | Page transition animations | 3 | Medium | Medium | ❌ Pending |
| 16 | Fix light-mode CSS over-engineering | 4 | High | Medium | ❌ Pending |
| 17 | Bottom-nav accessibility | *(deferred)* | Low | Low | ⏸️ Deferred |
| 18 | Pull-to-refresh | 3 | Medium | Medium | ❌ Pending |
| 19 | Toast notifications (replace alert) | 3 | Medium | Medium | ✅ Done (inline in Phase 1) |
| 20 | Empty-state animations | 3 | Low | Low | ❌ Pending |
| 21 | Extract shared utility functions | 5 | Medium | Medium | ✅ Done |
| 22 | Modality controller factory | 6 | High | Medium | ❌ Pending |
| 23 | Use ES modules | *(deferred)* | High | Low | ⏸️ Deferred |
| 24 | Service worker auto-versioning | 5 | Low | Medium | ✅ Done |
| 25 | Response compression | 5 | Low | High | ✅ Done |

**Legend:** ✅ = Complete | 🟡 = Partial | ❌ = Pending | ⏸️ = Deferred to post-MVP

---

## Dependency / Ordering Notes

- ✅ **Phase 1 -> Phase 5:** Bundling (#1) makes utility extraction (#21) easier. **Both complete.**
- **Phase 3 -> Phase 6:** UI patterns should be settled before factory refactor.
- **Phase 4 can be parallel** with Phase 3/5 — mostly CSS/template changes.
- **Phase 2 (Lazy HTML)** is the largest change and should come early (after Phase 1 cleans up scripts). Phase 1 is now complete, so Phase 2 is unblocked.