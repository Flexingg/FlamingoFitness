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
        if (window.addModal) {
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

