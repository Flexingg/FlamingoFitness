🎨 Frontend Architecture (Vanilla PWA)

AI Context: No React/Vue. Vanilla HTML5, CSS3, JS. Served as Django templates (`core/templates/core/dashboard.html`), but highly API-driven using fetch(). All static assets live under `core/static/core/`.

JavaScript Module Structure

Each skill-tree node gets its own controller file, loaded after `dashboard.js` via `<script>` tags at the bottom of `dashboard.html`. Each file is an IIFE exposing the functions the template calls via `onclick=`.

- `js/dashboard.js` — fetches `/api/v1/dashboard/state`, renders the shell (nav stats, readiness card, leaderboard modal, XP progress bars under each node). Defines `window.openModal`, `window.closeModal`, `window.addModal`.
- `js/nutrition.js` — `window.loadNutrition()`, `window.backToNutritionPlan()`, `window.renderNutrition(data)`, `window.showDayDetailModal(day)`.
- `js/hydration.js` — `window.loadHydration()`, `window.backToHydrationPlan()`, `window.renderHydration(data)`, `window.showHydrationDayDetailModal(day)`.
- `js/endurance.js` — `window.loadEndurance()`, `window.backToEndurancePlan()`, `window.renderEndurance(data)`, `window.showEnduranceDayDetailModal(day)`.

Pattern for a node controller (Endurance is a good reference template):

- `onclick="loadEndurance()"` is set directly on the node button in `dashboard.html` (explicit `onclick` beats fragile DOMContentLoaded binding and works even when child nodes are re-rendered).
- The controller IIFE also binds its node via `addEventListener` as a fallback.
- `load*()` hides the skill tree, shows the detail `<section>`, fetches the endpoint with `{ credentials: 'same-origin' }`, and calls `render*(data)`.
- `render*()` builds the skill-tree progress block (level, total XP, XP progress bar, "how to earn XP" guidance), then the today card, then the clickable history list.
- Each history row opens a day-detail modal via `show*DayDetailModal(day)` which reuses the shared modal (`#modal`) from `dashboard.html`.

IMPORTANT (learned the hard way): do NOT copy another modality's controller and only rename identifiers. Rendering logic (which payload fields are read) must also be ported. E.g. porting `hydration.js` to `endurance.js` left `buildEnduranceCard` reading `water_pct` / `water` / `water_goal` (undefined for endurance), showing a bogus "0/0 oz" bar. Always read the actual API payload keys (`total_calories_burned`, `total_duration_minutes`, `exercise_entries`, ...) and run `node --check` after editing.

CSS Guidelines (Flamingo / Miami / Duolingo Vibe)

The aesthetic is "Miami Vice meets Duolingo." It uses bright neon pastel colors, chunky shapes, heavy font weights, and bouncy animations. Everything should feel tactile and gamified.

Color Palette (CSS Variables in :root):

--primary-pink: #FF5E9A; (Primary actions, Flamingo mascot color)

--dark-pink: #D83A78; (For button bottom borders/shadows)

--primary-orange: #FF9933; (Streaks, Fire icons, warnings)

--primary-blue: #00E5FF; (Endurance nodes, cool accents)

--primary-purple: #9D4EDD; (Strength nodes, Boss Fights)

--primary-cyan: (Hydration nodes, added for the hydration tree)

--bg-light: #FFFFFF; (Card backgrounds)

--bg-app: #FDF4F7; (Slightly warm, pinkish-white background for the whole app)

--text-main: #2B2B2B;

--text-muted: #8E8E8E;

Node colors live in CSS as `.node-strength`, `.node-endurance`, `.node-nutrition`, `.node-hydration`, `.node-recovery` classes with a thick bottom `box-shadow` for the Duolingo-press feel.

Typography:

Use a rounded, heavy sans-serif font like 'Nunito', 'Varela Round', or 'Quicksand'.

Headers should be highly legible, bold, and playful.

Shapes & Structure:

Everything is a card. border-radius: 20px; is the standard.

Heavy use of Flexbox for center alignment.

Buttons (The "Duolingo Pop"):
Buttons must have a 3D tactile feel using thick bottom borders that compress when clicked.

.btn-flamingo {
    background-color: var(--primary-pink);
    color: white;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 16px 24px;
    border: none;
    border-bottom: 5px solid var(--dark-pink);
    border-radius: 16px;
    cursor: pointer;
    transition: transform 0.1s, border-bottom 0.1s;
}
.btn-flamingo:active {
    transform: translateY(5px);
    border-bottom: 0px solid var(--dark-pink);
    margin-bottom: 5px; /* prevents layout shift on click */
}


PWA Requirements

Root must include a valid manifest.json.

A vanilla JS service-worker.js `core/static/core/service-worker.js` is registered to cache static assets (CSS/JS/Icons) for instant mobile loading.

UI must be Mobile-First. Wrap the main view in a container with max-width: 480px; margin: 0 auto; for desktop users to maintain the app feel.
