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
        // Use ensureSinglePanelVisible to hide all other panels first,
        // then show only the skill tree (prevents stacking)
        window.ensureSinglePanelVisible('skill-tree');
    };

    // Fetch + render the boss panel.
    window.loadBoss = function () {
        window.ffLog('[boss] loadBoss start');
        if (window.closeModal) window.closeModal();

        var runLoad = function () {
            var view = document.getElementById('boss-view');
            var content = document.getElementById('boss-content');
            var empty = document.getElementById('boss-empty');
            if (!view) {
                window.ffWarn('[boss] boss-view not found, aborting');
                return;
            }
            window.ensureSinglePanelVisible('boss-view');
            if (content) content.classList.add('hidden');
            if (empty) empty.classList.add('hidden');
            fetch(BOSS_URL, { credentials: 'same-origin' })
                .then(function (res) {
                    if (res.status === 401 || res.status === 403) {
                        throw new Error('not-authenticated');
                    }
                    return res.ok ? res.json() : Promise.reject(res.status);
                })
                .then(function (data) {
                    window.ffLog('[boss] data.bodyweight=', data.bodyweight, 'bosses=', data.bosses && data.bosses.length);
                    window.renderBoss(data);
                })
                .catch(function (err) {
                    window.ffError('[boss] fetch failed:', err);
                    if (content) {
                        content.classList.remove('hidden');
                        if (err && err.message === 'not-authenticated') {
                            content.innerHTML = '<p class="error-hint">Please log in to view the PR Boss.</p>';
                        } else {
                            content.innerHTML = '<p class="error-hint">Could not load boss data (error ' + err + ').</p>';
                        }
                    }
                });
        };

        if (typeof window.ensurePanelLoaded === 'function') {
            return window.ensurePanelLoaded('boss-view').then(runLoad);
        } else {
            return runLoad();
        }
    };
// Render the boss panel from the /api/v1/boss/ payload.
    window.renderBoss = function (data) {
        var content = document.getElementById('boss-content');
        var empty = document.getElementById('boss-empty');
        if (!content) return;

        if (!data.linked_liftosaur) {
            content.classList.add('hidden');
            window.showEmptyState(empty, {
                icon: 'fa-crown',
                title: 'Link Liftosaur',
                desc: 'Challenge the PR Bosses once you link Liftosaur and track your lifts.',
                hint: 'PR bosses compare your best lift to a bodyweight benchmark.',
                ctaText: 'Link Liftosaur',
                ctaHref: '/profile/'
            });
            empty.classList.remove('hidden');
            return;
        }
        if (!data.bodyweight) {
            content.classList.add('hidden');
            window.showEmptyState(empty, {
                icon: 'fa-weight-scale',
                title: 'Linked to Liftosaur, but no bodyweight yet',
                desc: 'Boss goals are based on your bodyweight. Track it in SparkyFitness and it will show up here.',
                hint: 'Your best lift is compared against a multiple of your weight.',
                ctaText: 'Link SparkyFitness',
                ctaHref: '/profile/'
            });
            empty.classList.remove('hidden');
            return;
        }

        empty.classList.add('hidden');
        content.classList.remove('hidden');
        content.innerHTML = '';

        // Intro card: bodyweight.
        var intro = document.createElement('div');
        intro.className = 'modality-skill-section boss-skill-section';
        intro.innerHTML = 
            '<div class="skill-card-head">' +
                '<div class="skill-card-title">' +
                    '<span class="skill-icon-wrap boss-icon-wrap"><i class="fa-solid fa-crown"></i></span>' +
                    '<div>' +
                        '<div class="skill-card-name">PR Boss Challenge</div>' +
                        '<div class="skill-card-sub">Bodyweight Multipliers & Benchmarks</div>' +
                    '</div>' +
                '</div>' +
                '<div class="skill-level-badge boss-level-badge">' + (data.bodyweight ? Math.round(data.bodyweight) + ' lbs' : 'PR') + '</div>' +
            '</div>' +
            '<div class="skill-guidance-box boss-guidance">' +
                '<i class="fa-solid fa-trophy"></i>' +
                '<span>Beat a bodyweight-based lift benchmark to earn bonus XP and Time Speed-ups for your base!</span>' +
            '</div>';
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
            none.innerHTML = window.emptyStateHTML({
                icon: 'fa-flag-checkered',
                title: 'No PR bosses configured yet',
                desc: 'An admin can add PR Boss benchmarks in the Django admin.',
                secondary: true
            });
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
        window.ffWarn('[boss] node-boss NOT found in DOM');
    }
})();

