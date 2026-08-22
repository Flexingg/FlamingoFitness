# 🚀 Frontend Optimization Plan (docs/19)

> **STATUS:** All Planned Phases (1–6) ✅ COMPLETE.
> - **Phase 1 (Performance):** ✅ Complete (`django-compressor` bundling, `defer`/`async`, lazy-load stubs, font preconnect, guarded logging `ffLog`/`ffWarn`/`ffError`, `showToast()` in controllers).
> - **Phase 2 (Lazy HTML Partials #12):** ✅ Complete (12 panel partials in `core/templates/core/panels/`, dynamic backend endpoint `/panel/<name>/`, cached fetch via `ensurePanelLoaded()`).
> - **Phase 3 (UI Polish #13, #15, #18, #19, #20):** ✅ Complete (Skeleton loading cards with shimmer, panel slide transition animations, mobile pull-to-refresh on `<main>`, animated empty states, toast notifications).
> - **Phase 4 (Light/Dark Overhaul #16):** ✅ Complete (Consolidated CSS variables in `:root` and `html.light` in `dashboard.css`, legacy 15KB `theme.css` deprecated/removed).
> - **Phase 5 (Architecture #21, #24, #25):** ✅ Complete (Shared `utils.js` extracted, service-worker auto-versioned via `<meta>`, WhiteNoise compression verified).
> - **Phase 6 (Code Simplification #22):** ✅ Complete (`core/static/core/js/modality-factory.js` with `window.createModalityController()` refactored across `nutrition.js`, `hydration.js`, `endurance.js`, `strength.js`, `recovery.js`).
> 
> Deferred ideas (#2, #5, #7, #8, #9, #10, #14, #17, #23) remain deferred post-MVP.

---

## Phase Overview

| Phase | Theme | Ideas | Effort | Dependencies | Status |
|-------|-------|-------|--------|-------------|--------|
| 1 | Performance Optimization | #1, #3, #4, #6, #11 | Medium | — | ✅ Complete |
| 2 | HTMX / Lazy HTML | #12 | High | Phase 1 | ✅ Complete |
| 3 | UI Polish | #13, #15, #18, #19, #20 | Medium | — | ✅ Complete |
| 4 | Light/Dark Overhaul | #16 | High | — | ✅ Complete |
| 5 | Architecture / Maintainability | #21, #24, #25 | Medium | Phase 1 | ✅ Complete |
| 6 | Code Simplification | #22 | High | Phase 3 | ✅ Complete |

---

## Phase 1: Performance Optimization (#1, #3, #4, #6, #11)

> **STATUS: ✅ COMPLETE**

**Goal:** Reduce initial page load by bundling scripts, deferring non-critical
code, lazy-loading feature controllers, optimizing font loading, and guarding
console.log behind a DEBUG flag.

### #1 — Bundle & Minify JS Assets
- Added `django-compressor>=4.5` to `requirements.txt`
- Configured compressor in `settings.py`
- Wrapped deferred scripts in `{% compress js %}...{% endcompress %}` in `dashboard.html`

### #3 — Defer Non-Critical JS (async/defer)
- Core and modality scripts use `<script defer>`
- CDN scripts (canvas-confetti, chart.js) use `<script async>`
- `theme.js` stays synchronous in `<head>`

### #4 — Lazy-Load Feature Controllers
- Feature controllers (shop, loadout, battle, pvp, badges, leagues, stat_info) loaded on-demand via `window.loadScript()`
- `window.LAZY_SCRIPT_URLS` configured in `dashboard.html`

### #6 — Optimize Font Loading
- `&display=swap` with Google Fonts preconnect links

### #11 — console.log Guarded Behind DEBUG
- `window.ffLog`, `window.ffWarn`, `window.ffError` in `utils.js`
- `window.showToast()` for toast notifications

---

## Phase 2: Server-Side Panel Lazy Loading (#12)

> **STATUS: ✅ COMPLETE**

**Goal:** Reduce initial HTML payload (~53KB template with all hidden panels down to lean shell).

### #12 — Serve Panels via Dynamic Fetch
- Created 12 panel partial templates in `core/templates/core/panels/*.html` (`nutrition`, `hydration`, `endurance`, `strength`, `boss`, `recovery`, `shop`, `loadout`, `battle`, `pvp`, `leagues`, `badges`).
- Added backend route `path("panel/<str:name>/", views.panel_view, name="panel_view")` and `panel_view` in `core/views.py`.
- Added client-side lazy fetch and in-memory cache `window.ensurePanelLoaded(panelId)` in `utils.js`.
- Cleaned up `dashboard.html` to only render top nav, `<main id="main-scroller">` with `#skill-tree`, bottom nav, and modals.

---

## Phase 3: UI/UX Polish (#13, #15, #18, #19, #20)

> **STATUS: ✅ COMPLETE**

### #13 — Skeleton Loading States
- Added CSS keyframe `@keyframes shimmer` and `.skeleton-card`, `.skeleton-box`, `.skeleton-bar`, `.skeleton-circle` in `dashboard.css`.
- Added helper `window.renderSkeleton(container, count)` in `utils.js` invoked before data arrives in modality and lazy controllers.

### #15 — Page Transitions / Panel Sliding
- Added `.panel-view-enter` and `@keyframes panelSlideIn` in `dashboard.css` (with `prefers-reduced-motion` check).
- `ensureSinglePanelVisible()` in `dashboard.js` automatically applies transition animations.

### #18 — Add Pull-to-Refresh
- Implemented mobile pull-to-refresh in `dashboard.js` (`initPullToRefresh`) on `<main>` with `.ptr-indicator` styling in `dashboard.css` and haptic feedback.

### #19 — Toast Notifications
- `window.showToast(message, type)` in `utils.js` replacing `alert()` and `confirm()` dialogs.

### #20 — Empty-State Animations
- Added smooth `.empty-state` fade-in and `.empty-state-icon i` bounce animations in `dashboard.css`.

---

## Phase 4: Light/Dark Theme Overhaul (#16)

> **STATUS: ✅ COMPLETE**

**Goal:** Replace the brittle `!important`-heavy `theme.css` with clean CSS custom properties.

### #16 — Refactor Light-Mode CSS
- Consolidated all palette definitions into `:root` and `html.light` in `dashboard.css` (`--bg-outer`, `--bg-app`, `--bg-light`, `--text-main`, `--text-muted`, `--border-color`, `--bg-sky`, `--neon-color`, `--neon-glow`).
- Cleaned up `dashboard.html`, `login.html`, `signup.html`, `link_sparky.html` to remove references to `theme.css`.
- Deprecated legacy `theme.css` file.

---

## Phase 5: Architecture / Maintainability (#21, #24, #25)

> **STATUS: ✅ COMPLETE**

### #21 — Extract Shared Utility Functions
- Centralized `ffLog`, `loadScript`, `escHtml`, `csrfToken`, `haptic`, `fmoney`, `confettiBurst`, `showEmptyState`, `showToast`, `ensurePanelLoaded`, and `renderSkeleton` in `core/static/core/js/utils.js`.

### #24 — Service Worker Auto-Versioning
- Auto-versioning via `<meta name="ff-sw-version" content="5">` in `dashboard.html`.

### #25 — Response Compression
- WhiteNoise gzip compression verified and configured.

---

## Phase 6: Code Simplification — Controller Factory (#22)

> **STATUS: ✅ COMPLETE**

**Goal:** Eliminate ~80% boilerplate across modality detail controllers.

### #22 — Modality Controller Factory
- Created `core/static/core/js/modality-factory.js` providing `window.createModalityController(config)`.
- Refactored `nutrition.js`, `hydration.js`, `endurance.js`, `strength.js`, and `recovery.js` to define their specialized cards, charts, and metrics via thin factory configurations while sharing load, error handling, skeleton rendering, and progress bars.

---

## Summary of All 25 Ideas

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
| 12 | Lazy-load panel HTML | 2 | High | High | ✅ Done |
| 13 | Skeleton loading states | 3 | Medium | High | ✅ Done |
| 14 | Prefetch adjacent panel data | *(deferred)* | Medium | Medium | ⏸️ Deferred |
| 15 | Page transition animations | 3 | Medium | Medium | ✅ Done |
| 16 | Fix light-mode CSS over-engineering | 4 | High | Medium | ✅ Done |
| 17 | Bottom-nav accessibility | *(deferred)* | Low | Low | ⏸️ Deferred |
| 18 | Pull-to-refresh | 3 | Medium | Medium | ✅ Done |
| 19 | Toast notifications (replace alert) | 3 | Medium | Medium | ✅ Done |
| 20 | Empty-state animations | 3 | Low | Low | ✅ Done |
| 21 | Extract shared utility functions | 5 | Medium | Medium | ✅ Done |
| 22 | Modality controller factory | 6 | High | Medium | ✅ Done |
| 23 | Use ES modules | *(deferred)* | High | Low | ⏸️ Deferred |
| 24 | Service worker auto-versioning | 5 | Low | Medium | ✅ Done |
| 25 | Response compression | 5 | Low | High | ✅ Done |

**Legend:** ✅ = Complete | ⏸️ = Deferred to post-MVP