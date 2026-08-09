/* PR Boss detail panel controller (loaded after dashboard.js).
 * Opens from the gold PR Boss node (#node-boss) on the skill-tree plan.
 * Consumes GET /api/v1/boss/ (core/views.py boss_state).
 * Compares your best lifts against admin-configured bodyweight benchmarks
 * (e.g. Bench Press 1.5x bodyweight).
 */
(function () {
    'use strict';

    var BOSS_URL = '/api/v1/boss/';

    // Return to the skill-tree plan from the boss panel.
    window.backToBossPlan = function () {
        var view = document.getElementById('boss-view');
        if (view) view.classList.add('hidden');
        var tree = document.getElementById('skill-tree');
        if (tree) tree.classList.remove('hidden');
        var hint = document.getElementById('loading-hint');
        if (hint) hint.classList.add('hidden');
    };

    // Fetch + render the boss panel.
    window.loadBoss = function () {
        console.log('[boss] loadBoss start');
        if (window.closeModal) window.closeModal();
        var view = document.getElementById('boss-view');
        var content = document.getElementById('boss-content');
        var empty = document.getElementById('boss-empty');
        var tree = document.getElementById('skill-tree');
        if (!view) {
            console.warn('[boss] boss-view not found, aborting');
            return;
        }
        if (tree) tree.classList.add('hidden');
        view.classList.remove('hidden');
        content.classList.add('hidden');
        empty.classList.add('hidden');
        fetch(BOSS_URL, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401 || res.status === 403) {
                    throw new Error('not-authenticated');
                }
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(function (data) {
                console.log('[boss] data.bodyweight=', data.bodyweight, 'bosses=', data.bosses && data.bosses.length);
                window.renderBoss(data);
            })
            .catch(function (err) {
                console.error('[boss] fetch failed:', err);
                content.classList.remove('hidden');
                if (err && err.message === 'not-authenticated') {
                    content.innerHTML = '<p class="error-hint">Please log in to view the PR Boss.</p>';
                } else {
                    content.innerHTML = '<p class="error-hint">Could not load boss data (error ' + err + ').</p>';
                }
            });
    };
// Render the boss panel from the /api/v1/boss/ payload.
    window.renderBoss = function (data) {
        var content = document.getElementById('boss-content');
        var empty = document.getElementById('boss-empty');
        if (!content) return;

        if (!data.linked_liftosaur) {
            content.classList.add('hidden');
            empty.classList.remove('hidden');
            empty.innerHTML = '<div class="empty-icon"><i class="fa-solid fa-crown"></i></div>' +
                '<p class="empty-title">Link Liftosaur</p>' +
                '<p class="empty-desc">Challenge the PR Bosses once you link Liftosaur and track your lifts.</p>' +
                '<a href="/profile/" class="btn-flamingo">Link Liftosaur</a>';
            return;
        }
        if (!data.bodyweight) {
            content.classList.add('hidden');
            empty.classList.remove('hidden');
            empty.innerHTML = '<div class="empty-icon"><i class="fa-solid fa-weight-scale"></i></div>' +
                '<p class="empty-title">Linked \u2014 no bodyweight yet</p>' +
                '<p class="empty-desc">Boss goals are based on your bodyweight. Track it in SparkyFitness and it will show up here.</p>' +
                '<a href="/profile/" class="btn-flamingo">Link SparkyFitness</a>';
            return;
        }

        empty.classList.add('hidden');
        content.classList.remove('hidden');
        content.innerHTML = '';

        // Intro card: bodyweight.
        var intro = document.createElement('div');
        intro.className = 'nutrition-skill-section';
        var head = document.createElement('div');
        head.className = 'nutrition-skill-header';
        head.innerHTML = '<i class="fa-solid fa-crown"></i> PR Boss';
        intro.appendChild(head);

        var info = document.createElement('div');
        info.className = 'nutrition-skill-info';
        info.textContent = 'Bodyweight: ' + Math.round(data.bodyweight) +
            ' lbs \u2014 earn Boss Fights by lifting a multiple of it!';
        intro.appendChild(info);

        var guidance = document.createElement('div');
        guidance.className = 'nutrition-guidance';
        guidance.innerHTML = '<strong>Boss Fight:</strong> beat a bodyweight-based lift benchmark to earn a 2x XP reward and Time Speed-ups for your base. Configure benchmarks in the admin panel.';
        intro.appendChild(guidance);
        content.appendChild(intro);

        // Personal Records (moved here from the Strength panel).
        if (data.best_lifts && data.best_lifts.length) {
            var prTitle = document.createElement('div');
            prTitle.className = 'history-title';
            prTitle.innerHTML = '<i class="fa-solid fa-medal"></i> Personal Records';
            content.appendChild(prTitle);

            var prList = document.createElement('div');
            prList.style.display = 'flex';
            prList.style.flexDirection = 'column';
            prList.style.gap = '6px';
            prList.style.marginBottom = '14px';

            data.best_lifts.forEach(function (b) {
                var row = document.createElement('div');
                row.className = 'nutrition-day-card';
                row.style.padding = '12px';
                row.style.display = 'flex';
                row.style.justifyContent = 'space-between';
                row.style.alignItems = 'center';

                var left = document.createElement('span');
                left.style.fontWeight = '800';
                left.textContent = b.name;

                var right = document.createElement('span');
                right.style.fontWeight = '700';
                right.style.color = 'var(--primary-orange)';
                right.textContent = (b.weight || 0) + (b.unit || 'lb') +
                    ' x ' + (b.reps || 0) + '  (est 1RM ' + (b.est_1rm || 0) + ')';

                row.appendChild(left);
                row.appendChild(right);
                prList.appendChild(row);
            });
            content.appendChild(prList);
        }

        // Boss list.
        if (!data.bosses || !data.bosses.length) {
            var none = document.createElement('div');
            none.className = 'nutrition-empty';
            none.innerHTML = '<p class="empty-title">No bosses configured yet.</p>' +
                '<p class="empty-desc">An admin can add PR Boss benchmarks in the Django admin.</p>';
            content.appendChild(none);
            return;
        }

        data.bosses.forEach(function (boss) {
            var card = document.createElement('div');
            card.className = 'nutrition-day-card' + (boss.conquered ? ' perfect' : '');

            var cHead = document.createElement('div');
            cHead.className = 'day-card-head';
            var n = document.createElement('div');
            n.className = 'day-date';
            n.textContent = boss.name;
            cHead.appendChild(n);
            var badge = document.createElement('span');
            badge.className = boss.conquered ? 'perfect-badge' : 'imperfect-badge';
            badge.textContent = boss.conquered ? 'CONQUERED' : 'Challenged';
            cHead.appendChild(badge);
            card.appendChild(cHead);

            var stats = document.createElement('div');
            stats.className = 'macro-row';
            stats.style.flexDirection = 'column';
            stats.style.alignItems = 'flex-start';
            stats.style.gap = '4px';

            if (boss.goal) {
                var goal = document.createElement('div');
                goal.innerHTML = '<strong>Goal:</strong> ' + boss.exercise_match +
                    ' \u00d7 ' + boss.multiplier + ' BW = <span style="color: var(--primary-orange);">' +
                    Math.round(boss.goal) + ' lbs</span>';
                stats.appendChild(goal);
            }
            var best = document.createElement('div');
            best.innerHTML = '<strong>Your best:</strong> ' +
                (boss.best_lift ? Math.round(boss.best_lift) + ' lbs' : '\u2014');
            stats.appendChild(best);
            card.appendChild(stats);

            // Progress bar toward the goal.
            var barWrap = document.createElement('div');
            barWrap.className = 'nutrition-xp-bar-wrap';
            var bar = document.createElement('div');
            bar.className = 'nutrition-xp-bar';
            var fill = document.createElement('div');
            fill.className = 'nutrition-xp-fill';
            fill.style.width = Math.min(100, Math.max(0, boss.progress_pct || 0)) + '%';
            fill.style.backgroundColor = 'var(--primary-orange)';
            bar.appendChild(fill);
            barWrap.appendChild(bar);
            var note = document.createElement('div');
            note.className = 'nutrition-xp-to-next';
            note.textContent = (boss.progress_pct || 0) + '% to goal';
            barWrap.appendChild(note);
            card.appendChild(barWrap);

            content.appendChild(card);
        });
    };

    // Bind the gold PR Boss node on the skill-tree plan.
    var bossNode = document.getElementById('node-boss');
    if (bossNode) {
        bossNode.addEventListener('click', function () { window.loadBoss(); });
    } else {
        console.warn('[boss] node-boss NOT found in DOM');
    }
})();