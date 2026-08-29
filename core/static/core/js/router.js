/* ============================================================
   Flamingo Fitness - Client-Side SPA Router (router.js)
   ------------------------------------------------------------
   Architecture Overview:
   - Manages Single Page Application (SPA) view routing using HTML5
     History API and URL fragments (e.g. `#/nutrition`, `#/shop`).
   - Links client hash changes to lazy-loaded panel partials and
     dynamic DOM section visibility.
   - Synchronizes bottom navigation tab active states via NAV_BY_PANEL.
   - Handles deep links on page load, browser back/forward buttons (popstate),
     and in-app back buttons via `window.AppRouter.back()`.

   Interaction Graph:
   - Loaded BEFORE `dashboard.js` in `core/templates/core/dashboard.html`.
   - Called by `dashboard.js:ensureSinglePanelVisible(panelId)` on panel open.
   - Dispatches calls to global panel loaders (e.g., `window.loadNutrition()`,
     `window.loadShop()`, `window.loadPvP()`, etc.).
   ============================================================ */

(function () {
    'use strict';

    /**
     * Maps DOM panel section IDs to URL hash slugs.
     * Empty string '' maps directly to the root dashboard 'skill-tree' view.
     * @type {Object.<string, string>}
     */
    var SLUG_BY_PANEL = {
        'skill-tree': '',
        'nutrition-view': 'nutrition',
        'hydration-view': 'hydration',
        'endurance-view': 'endurance',
        'strength-view': 'strength',
        'boss-view': 'boss',
        'recovery-view': 'recovery',
        'shop-view': 'shop',
        'loadout-view': 'loadout',
        'battle-view': 'battle',
        'pvp-view': 'pvp',
        'badges-view': 'badges',
        'leagues-view': 'leagues',
        'bounties-view': 'bounties'
    };

    /**
     * Maps URL slugs to global controller load functions.
     * Each function fetches API data and mounts its corresponding view.
     * @type {Object.<string, string>}
     */
    var LOADER_BY_SLUG = {
        'nutrition': 'loadNutrition',
        'hydration': 'loadHydration',
        'endurance': 'loadEndurance',
        'strength': 'loadStrength',
        'boss': 'loadBoss',
        'recovery': 'loadRecovery',
        'shop': 'loadShop',
        'loadout': 'loadLoadout',
        'battle': 'loadBattle',
        'pvp': 'loadPvP',
        'badges': 'loadBadges',
        'leagues': 'loadLeagues',
        'bounties': 'loadBounties'
    };

    /**
     * Maps DOM panel section IDs to bottom navigation bar element IDs.
     * Ensures active tab highlights mirror the active on-screen panel.
     * @type {Object.<string, string>}
     */
    var NAV_BY_PANEL = {
        'skill-tree': 'nav-path',
        'nutrition-view': 'nav-path',
        'hydration-view': 'nav-path',
        'endurance-view': 'nav-path',
        'strength-view': 'nav-path',
        'boss-view': 'nav-path',
        'recovery-view': 'nav-path',
        'shop-view': 'nav-shop',
        'loadout-view': 'nav-loadout',
        'battle-view': 'nav-battle',
        'pvp-view': 'nav-pvp',
        'badges-view': 'nav-badges',
        'leagues-view': 'nav-leagues',
        'bounties-view': 'nav-bounties'
    };

    // True while restoring an existing history entry, so a panel switch during
    // restoration does not push a NEW entry on top of it.
    var restoring = false;

    function currentSlug() {
        var h = window.location.hash || '';
        return h.replace(/^#\/?/, '');
    }

    function panelForSlug(slug) {
        if (!slug) return 'skill-tree';
        for (var panel in SLUG_BY_PANEL) {
            if (SLUG_BY_PANEL.hasOwnProperty(panel) && SLUG_BY_PANEL[panel] === slug) {
                return panel;
            }
        }
        return null;
    }

    function panelVisible(panelId) {
        var el = document.getElementById(panelId);
        return !!el && !el.classList.contains('hidden');
    }

    function setHighlight(panelId) {
        if (window.setActiveNav) {
            window.setActiveNav(NAV_BY_PANEL[panelId] || 'nav-path');
        }
    }

    function showHome() {
        if (window.closeModal) window.closeModal();
        if (window.hideAllPanels) window.hideAllPanels();
        var tree = document.getElementById('skill-tree');
        if (tree) tree.classList.remove('hidden');
        setHighlight('skill-tree');
    }

    // Restore the panel for a given id. If it is already on screen (because the
    // originating load*() already rendered it), just sync the nav highlight
    // instead of re-fetching.
    function restorePanel(panelId) {
        if (panelId === 'skill-tree') { showHome(); return; }
        if (panelVisible(panelId)) { setHighlight(panelId); return; }
        var loader = LOADER_BY_SLUG[SLUG_BY_PANEL[panelId]];
        if (loader && window[loader]) { window[loader](); }
        setHighlight(panelId);
    }

    function restoreFromHash() {
        var panel = panelForSlug(currentSlug());
        if (!panel) { showHome(); return; }
        restorePanel(panel);
    }

    function onPopState() {
        restoring = true;
        try { restoreFromHash(); } finally { restoring = false; }
    }

    // Public API -----------------------------------------------------------
    window.AppRouter = {
        /**
         * Record a panel switch in browser history.
         * Called by `dashboard.js:ensureSinglePanelVisible(panelId)` on every panel opening.
         * @param {string} panelId - DOM ID of the panel being displayed (e.g. 'nutrition-view')
         */
        navigate: function (panelId) {
            if (restoring) return;
            var target = SLUG_BY_PANEL[panelId];
            var hash = target ? '#/' + target : '';
            if ((window.location.hash || '') === hash) return;
            history.pushState({ panel: panelId }, '', hash);
        },

        /**
         * Walk back through client history.
         * Used by in-app back buttons (`window.goBack()`). Falls back to root skill-tree if stack is empty.
         */
        back: function () {
            if (window.history.length > 1) { history.back(); return; }
            // Nothing to walk - land cleanly on the skill tree.
            history.replaceState(null, '', window.location.pathname);
            showHome();
        },

        /**
         * Initialize popstate event listener and restore initial view from current URL hash on startup.
         */
        init: function () {
            window.addEventListener('popstate', onPopState);
            restoring = true;
            try { restoreFromHash(); } finally { restoring = false; }
        }
    };

    // Boot after every script (feature modules included) has loaded, so the
    // window.load*() renderers exist when we restore an initial URL fragment.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { window.AppRouter.init(); });
    } else {
        window.AppRouter.init();
    }
})();
