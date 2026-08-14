/* ============================================================
   Flamingo Fitness - vanilla JS dashboard controller
   Fetches /api/v1/dashboard/state and renders the shell.
   Reference: docs/02_api_contracts.md, docs/04_frontend_architecture.md
   ============================================================ */

(function () {
    'use strict';

    var MODALITY_META = {
        strength:  { node: 'node-strength',  cls: 'node-strength' },
        endurance: { node: 'node-endurance', cls: 'node-endurance' },
        nutrition: { node: 'node-nutrition', cls: 'node-nutrition' },
        hydration: { node: 'node-hydration', cls: 'node-hydration' },
        recovery:  { node: 'node-recovery',  cls: 'node-recovery' }
    };

    var LEADERBOARD_URL = '/api/v1/leaderboard/weekly';

    // Every panel that can be opened from the bottom nav / skill-tree nodes.
    var PANEL_IDS = ['skill-tree', 'nutrition-view', 'hydration-view',
        'endurance-view', 'strength-view', 'boss-view', 'recovery-view',
        'base-view', 'badges-view', 'leagues-view'];

    // Hide ALL panels so opening a new one REPLACES the current view instead
    // of stacking underneath it (Phase 8 bug-fix).
    window.hideAllPanels = function () {
        PANEL_IDS.forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.classList.add('hidden');
        });
        var hint = document.getElementById('loading-hint');
        if (hint) hint.classList.add('hidden');
        var err = document.getElementById('error-hint');
        if (err) err.classList.add('hidden');
    };

    // Bottom-nav active-tab management.
    window.setActiveNav = function (id) {
        var items = document.querySelectorAll('.bottom-nav .nav-item');
        for (var i = 0; i < items.length; i++) {
            items[i].classList.toggle('active', items[i].id === id);
        }
    };

    // Path tab: return to the skill tree from anywhere.
    window.showPath = function () {
        if (window.closeModal) window.closeModal();
        window.hideAllPanels();
        var tree = document.getElementById('skill-tree');
        if (tree) tree.classList.remove('hidden');
        window.setActiveNav('nav-path');
    };

    // Phase 8: Ensure only one panel is visible at a time when navigating.
    // This replaces the stacking behavior where multiple panels could be visible
    // if back/next navigation doesn't fully clear previous panels.
    window.ensureSinglePanelVisible = function(visiblePanelId) {
        // Hide ALL panels first (this is the key fix - hide everything before showing new one)
        window.hideAllPanels();
        // Then show only the specified panel if it exists
        var panel = document.getElementById(visiblePanelId);
        if (panel) {
            panel.classList.remove('hidden');
        }
    };

    function showError(message) {
        var hint = document.getElementById('loading-hint');
        var err = document.getElementById('error-hint');
        if (hint) hint.classList.add('hidden');
        if (err) {
            err.textContent = message;
            err.classList.remove('hidden');
        }
        var card = document.getElementById('readiness-card');
        if (card) card.classList.add('hidden');
    }

    function renderState(data) {
        // Top nav stats
        document.querySelector('#stat-streak span').textContent = data.user.streak;
        document.querySelector('#stat-materials span').textContent = data.resources.materials;
        document.querySelector('#stat-energy span').textContent = data.resources.energy;
        document.getElementById('avatar-img').src = data.user.avatar || 'https://api.dicebear.com/7.x/avataaars/svg?seed=Flamingo';
        // Add onerror fallback so broken uploaded images revert to the cartoon default.
        document.getElementById('avatar-img').onerror = function () {
            this.onerror = null;
            this.src = 'https://api.dicebear.com/7.x/avataaars/svg?seed=Flamingo';
        };

        // Readiness card
        var card = document.getElementById('readiness-card');
        document.getElementById('readiness-score').textContent = data.readiness.score + '%';
        document.getElementById('readiness-desc').textContent = data.readiness.message;

        var isRest = data.readiness.streak_requirement === 'rest_day';
        card.classList.toggle('rest-day', isRest);
        var action = document.getElementById('readiness-action');
        if (isRest) {
            action.textContent = 'Rest is training. Recover!';
            action.onclick = function () {
                addModal('Recovery Day', data.readiness.message, 'Recover');
            };
        } else {
            action.textContent = 'Start 5/3/1 Workout';
            action.onclick = function () {
                addModal('Heavy Squat Day', 'You\u2019re recovered! Time to tackle your 5/3/1 Squat programming.', 'Log via Liftosaur');
            };
        }

        // Skill tree nodes
        var bossUnlocked = false;
        for (var key in data.skill_trees) {
            if (data.skill_trees.hasOwnProperty(key)) {
                var tree = data.skill_trees[key];
                var meta = MODALITY_META[key];
                var btn = document.getElementById(meta.node);
                if (btn) {
                    btn.classList.add(meta.cls);
                    btn.classList.remove('node-locked');
                    if (tree && tree.level !== undefined) {
                        var badge = document.createElement('span');
                        badge.className = 'node-level';
                        badge.textContent = 'Lv ' + tree.level;
                        btn.appendChild(badge);
                    }
                    // Add XP progress bar under each skill tree node
                    if (tree && tree.xp !== undefined) {
                        var xpWrap = document.createElement('div');
                        xpWrap.className = 'node-xp-wrap';
                        var xpBar = document.createElement('div');
                        xpBar.className = 'node-xp-bar';
                        var xpFill = document.createElement('div');
                        xpFill.className = 'node-xp-fill';
                        xpFill.style.width = Math.min(100, Math.max(0, tree.progress_pct || 0)) + '%';
                        xpBar.appendChild(xpFill);
                        xpWrap.appendChild(xpBar);
                        var xpText = document.createElement('div');
                        xpText.className = 'node-xp-text';
                        xpText.textContent = (tree.xp || 0) + ' / 100 XP';
                        xpWrap.appendChild(xpText);
                        btn.appendChild(xpWrap);
                    }
                    if (tree && tree.progress_pct >= 100 && key === 'strength') {
                        bossUnlocked = true;
                    }
                }
            }
        }
        var boss = document.getElementById('node-boss');
        if (boss && bossUnlocked) {
            boss.classList.add('node-strength');
            boss.classList.remove('node-locked');
        }

        document.getElementById('loading-hint').classList.add('hidden');
        document.getElementById('skill-tree').classList.remove('hidden');

        // Kick off leaderboard fetch in the background
        loadLeaderboard();
    }

    function loadLeaderboard() {
        // Only auto-pop the weekly leagues modal once per 7-day window.
        var lastKey = 'ff_last_league_modal';
        var last = localStorage.getItem(lastKey);
        var now = Date.now();
        var WEEK_MS = 7 * 24 * 60 * 60 * 1000;
        if (last && (now - parseInt(last, 10)) < WEEK_MS) {
            return;
        }

        fetch(LEADERBOARD_URL, { credentials: 'same-origin' })
            .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
            .then(function (data) {
                var board = data.leaderboard || [];
                if (!board.length) return;
                addModal(
                    'Weekly Leagues',
                    board.slice(0, 5).map(function (r, i) {
                        return (i + 1) + '. ' + r.username + ' \u2014 ' + r.total_xp + ' XP';
                    }).join('\n'),
                    'Nice work!'
                );
                localStorage.setItem(lastKey, String(now));
            })
            .catch(function () { /* leaderboard is optional on load */ });
    }

    // ---- Simple modal helpers ----
    function addModal(title, desc, actionText) {
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-desc').textContent = desc;
        document.getElementById('modal-action').textContent = actionText || 'OK';
        openModal();
    }
    window.addModal = addModal;

    function openModal() {
        document.getElementById('actionModal').classList.add('show-modal');
    }
    window.closeModal = function () {
        document.getElementById('actionModal').classList.remove('show-modal');
    };
    window.openModal = openModal;

    document.getElementById('actionModal').addEventListener('click', function (e) {
        if (e.target === this) window.closeModal();
    });
    document.getElementById('modal-action').addEventListener('click', function () {
        var btn = this;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Polling...';
        setTimeout(function () {
            btn.textContent = 'Saved \u2705';
            window.closeModal();
            setTimeout(function () { btn.textContent = 'Log via Liftosaur'; }, 800);
        }, 1200);
    });
    document.getElementById('nav-leagues').addEventListener('click', function (e) {
        // Phase 8 (docs/13): open the full Leagues/Challenges/Flock panel when
        // leagues.js is loaded; fall back to the legacy modal otherwise.
        if (window.loadLeagues) {
            e.preventDefault();
            window.loadLeagues();
        } else if (window.addModal) {
            e.preventDefault();
            loadLeaderboard();
        }
    });

    // ---- Boot: fetch dashboard state on page load ----
    fetch('/api/v1/dashboard/state', { credentials: 'same-origin' })
        .then(function (res) {
            if (res.status === 401 || res.status === 403) {
                throw new Error('not-authenticated');
            }
            return res.ok ? res.json() : Promise.reject(res.status);
        })
        .then(renderState)
        .catch(function (err) {
            if (err && err.message === 'not-authenticated') {
                showError('Please log in via the admin panel to view your dashboard.');
            } else {
                showError('Could not load your dashboard. Is the API running? (Error ' + err + ')');
            }
        });
})();

