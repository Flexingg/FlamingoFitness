/* Recovery detail panel controller (loaded after dashboard.js).
 * Opens from the green Recovery node (#node-recovery) on the skill-tree plan.
 * Consumes GET /api/v1/recovery/ (core/views.py recovery_state).
 * Shows the readiness score, recent sleep history (SparkyFitness) and the
 * Recovery skill tree (sleep XP: 8h+ = 50 XP, 5-8h = 20 XP).
 */
(function () {
    'use strict';

    var RECOVERY_URL = '/api/v1/recovery/';

    // Return to the skill-tree plan from the recovery panel.
    window.backToRecoveryPlan = function () {
        var view = document.getElementById('recovery-view');
        if (view) view.classList.add('hidden');
        // Use ensureSinglePanelVisible to hide all other panels first,
        // then show only the skill tree (prevents stacking)
        window.ensureSinglePanelVisible('skill-tree');
    };

    // Fetch + render the recovery panel.
    window.loadRecovery = function () {
        console.log('[recovery] loadRecovery start');
        if (window.closeModal) window.closeModal();
        var view = document.getElementById('recovery-view');
        var content = document.getElementById('recovery-content');
        var empty = document.getElementById('recovery-empty');
        var tree = document.getElementById('skill-tree');
        if (!view) {
            console.warn('[recovery] recovery-view not found, aborting');
            return;
        }
        // Single-panel navigation: hide ALL panels, then show only this panel.
        window.ensureSinglePanelVisible('recovery-view');
        content.classList.add('hidden');
        empty.classList.add('hidden');
        fetch(RECOVERY_URL, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401 || res.status === 403) {
                    throw new Error('not-authenticated');
                }
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(function (data) {
                console.log('[recovery] data.linked=', data.linked, 'readiness=', data.readiness && data.readiness.score, 'history=', !!(data.history && data.history.length));
                window.renderRecovery(data);
            })
            .catch(function (err) {
                console.error('[recovery] fetch failed:', err);
                content.classList.remove('hidden');
                if (err && err.message === 'not-authenticated') {
                    content.innerHTML = '<p class="error-hint">Please log in to view recovery.</p>';
                } else {
                    content.innerHTML = '<p class="error-hint">Could not load recovery data (error ' + err + ').</p>';
                }
            });
    };

    // Render the recovery panel from the /api/v1/recovery/ payload.
    window.renderRecovery = function (data) {
        var content = document.getElementById('recovery-content');
        var empty = document.getElementById('recovery-empty');
        if (!content) return;

        if (!data.linked) {
            content.classList.add('hidden');
            empty.classList.remove('hidden');
            empty.innerHTML = '<div class="empty-icon"><i class="fa-solid fa-bed"></i></div>' +
                '<p class="empty-title">Link SparkyFitness</p>' +
                '<p class="empty-desc">No recovery data yet. Connect SparkyFitness to track sleep and readiness.</p>' +
                '<a href="/profile/" class="btn-flamingo">Link SparkyFitness</a>';
            return;
        }

        empty.classList.add('hidden');
        content.classList.remove('hidden');
        content.innerHTML = '';

        // Recovery skill tree progress section (same layout as other panels).
        var st = data.skill_tree || {};
        var skillSection = document.createElement('div');
        skillSection.className = 'nutrition-skill-section';
        var skillHeader = document.createElement('div');
        skillHeader.className = 'nutrition-skill-header';
        skillHeader.innerHTML = '<i class="fa-solid fa-bed"></i> Recovery Skill Tree';
        skillSection.appendChild(skillHeader);

        var skillInfo = document.createElement('div');
        skillInfo.className = 'nutrition-skill-info';
        skillInfo.innerHTML = 'Lv ' + (st.level || 1) + ' &bull; ' + (st.total_xp || 0) + ' Total XP';
        skillSection.appendChild(skillInfo);

        var xpBarWrap = document.createElement('div');
        xpBarWrap.className = 'nutrition-xp-bar-wrap';
        var xpBar = document.createElement('div');
        xpBar.className = 'nutrition-xp-bar';
        var xpFill = document.createElement('div');
        xpFill.className = 'nutrition-xp-fill';
        xpFill.style.width = Math.min(100, Math.max(0, st.progress_pct || 0)) + '%';
        xpFill.style.backgroundColor = 'var(--primary-green)';
        xpBar.appendChild(xpFill);
        xpBarWrap.appendChild(xpBar);
        skillSection.appendChild(xpBarWrap);

        var xpToNext = document.createElement('div');
        xpToNext.className = 'nutrition-xp-to-next';
        xpToNext.textContent = (st.xp || 0) + ' / 100 XP to next level';
        skillSection.appendChild(xpToNext);

        var guidance = document.createElement('div');
        guidance.className = 'nutrition-guidance';
        guidance.innerHTML = '<strong>How to earn XP:</strong> sleep 8+ hours for +50 Recovery XP, or 5-8 hours for +20 XP. Rest days protect your streak!';
        skillSection.appendChild(guidance);

        content.appendChild(skillSection);

        // Readiness card (recovery engine output).
        var r = data.readiness || {};
        var readyCard = document.createElement('div');
        readyCard.className = 'nutrition-day-card';
        readyCard.style.padding = '14px';

        var isRest = r.streak_requirement === 'rest_day';
        var readyHead = document.createElement('div');
        readyHead.className = 'day-card-head';
        var readyTitle = document.createElement('div');
        readyTitle.className = 'day-date';
        readyTitle.innerHTML = '<i class="fa-solid fa-battery-three-quarters"></i> Readiness';
        readyHead.appendChild(readyTitle);
        var readyBadge = document.createElement('span');
        readyBadge.className = isRest ? 'imperfect-badge' : 'perfect-badge';
        readyBadge.textContent = isRest ? 'REST DAY' : 'READY TO TRAIN';
        readyHead.appendChild(readyBadge);
        readyCard.appendChild(readyHead);

        var scoreRow = document.createElement('div');
        scoreRow.className = 'macro-row';
        scoreRow.innerHTML = '<span class="macro-label">Score</span>' +
            '<span class="macro-value">' + (r.score != null ? r.score + '%' : '\u2014') + '</span>';
        readyCard.appendChild(scoreRow);

        if (r.sleep_hours != null) {
            var sleepRow = document.createElement('div');
            sleepRow.className = 'macro-row';
            sleepRow.innerHTML = '<span class="macro-label">Sleep</span>' +
                '<span class="macro-value">' + r.sleep_hours + ' h</span>';
            readyCard.appendChild(sleepRow);
        }
        if (r.body_battery != null) {
            var bbRow = document.createElement('div');
            bbRow.className = 'macro-row';
            bbRow.innerHTML = '<span class="macro-label">Body Battery</span>' +
                '<span class="macro-value">' + r.body_battery + '</span>';
            readyCard.appendChild(bbRow);
        }
        if (r.message) {
            var msg = document.createElement('div');
            msg.className = 'nutrition-guidance';
            msg.textContent = r.message;
            readyCard.appendChild(msg);
        }
        content.appendChild(readyCard);

        // Sleep history list.
        if (!data.history || !data.history.length) {
            var none = document.createElement('div');
            none.className = 'nutrition-empty';
            none.innerHTML = '<p class="empty-title">Linked \u2014 no sleep data yet</p>' +
                '<p class="empty-desc">Once your SparkyFitness sleep syncs, your nights will appear here.</p>';
            content.appendChild(none);
            return;
        }

        var title = document.createElement('div');
        title.className = 'history-title';
        title.innerHTML = '<i class="fa-solid fa-moon"></i> Sleep History';
        content.appendChild(title);

        var list = document.createElement('div');
        list.style.display = 'flex';
        list.style.flexDirection = 'column';
        list.style.gap = '6px';

        data.history.forEach(function (night) {
            var row = document.createElement('div');
            row.className = 'nutrition-day-card';
            row.style.padding = '12px';

            var head = document.createElement('div');
            head.className = 'day-card-head';
            var dayLabel = document.createElement('div');
            dayLabel.className = 'day-date';
            dayLabel.textContent = night.date;
            head.appendChild(dayLabel);
            if (night.xp) {
                var xpBadge = document.createElement('span');
                xpBadge.className = 'reward xp';
                xpBadge.textContent = '+' + night.xp + ' XP';
                head.appendChild(xpBadge);
            }
            row.appendChild(head);

            var stats = document.createElement('div');
            stats.className = 'macro-row';
            stats.innerHTML = '<span class="macro-label">Slept</span>' +
                '<span class="macro-value">' + night.sleep_hours + ' h' +
                ' &bull; Deep ' + (night.deep_pct || 0) + '%' +
                ' &bull; REM ' + (night.rem_pct || 0) + '%</span>';
            row.appendChild(stats);

            list.appendChild(row);
        });
        content.appendChild(list);
    };

    // Bind the green Recovery node on the skill-tree plan.
    var recNode = document.getElementById('node-recovery');
    if (recNode) {
        recNode.addEventListener('click', function () { window.loadRecovery(); });
    } else {
        console.warn('[recovery] node-recovery NOT found in DOM');
    }
})();