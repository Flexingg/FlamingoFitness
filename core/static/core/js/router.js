/* ============================================================
   Flamingo Fitness - client-side router for panel views.
   Gives each dashboard panel a distinct, shareable URL by
   storing a "#/slug" fragment via the History API, and restores
   the matching panel on popstate (browser back/forward) and on
   initial load / refresh / F5. Keeps the existing single-page
   DOM; no server-side routing changes are required.

   Load order: this file BEFORE dashboard.js.
   ============================================================ */

(function () {
    'use strict';

    // Panel id -> URL slug ("" = the skill-tree home). Pushed as "#/slug".
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
        'leagues-view': 'leagues'
    };

    // Slug -> loader function used to render the panel on restore.
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
        'leagues': 'loadLeagues'
    };

    // Panel id -> bottom-nav item to highlight (setActiveNav remaps combat views).
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
        'leagues-view': 'nav-leagues'
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
        // Record a panel switch in the browser history. Called from
        // dashboard.js' ensureSinglePanelVisible() whenever a panel opens.
        navigate: function (panelId) {
            if (restoring) return;
            var target = SLUG_BY_PANEL[panelId];
            var hash = target ? '#/' + target : '';
            if ((window.location.hash || '') === hash) return;
            history.pushState({ panel: panelId }, '', hash);
        },

        // Go back through app history (used by the in-app back arrows).
        back: function () {
            if (window.history.length > 1) { history.back(); return; }
            // Nothing to walk - land cleanly on the skill tree.
            history.replaceState(null, '', window.location.pathname);
            showHome();
        },

        // Restore whatever panel matches the current URL on first paint and
        // start listening for browser back/forward navigation.
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
