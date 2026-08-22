/* Strength detail panel controller (loaded after dashboard.js).
 * Opens from the purple Strength node (#node-strength) on the skill-tree plan.
 * Consumes GET /api/v1/strength/ (core/views.py strength_state).
 * Data comes from Liftosaur volume / duration / PR tracking (docs/11).
 */
(function () {
    'use strict';

    var STRENGTH_URL = '/api/v1/strength/';

    // Return to the skill-tree plan from the strength panel.
    window.backToStrengthPlan = function () {
        var view = document.getElementById('strength-view');
        if (view) view.classList.add('hidden');
        // Use ensureSinglePanelVisible to hide all other panels first,
        // then show only the skill tree (prevents stacking)
        window.ensureSinglePanelVisible('skill-tree');
    };

    // Fetch + render the strength panel.
    window.loadStrength = function () {
        window.ffLog('[strength] loadStrength start');
        if (window.closeModal) window.closeModal();
        var view = document.getElementById('strength-view');
        var content = document.getElementById('strength-content');
        var empty = document.getElementById('strength-empty');
        var tree = document.getElementById('skill-tree');
        if (!view) {
            window.ffWarn('[strength] strength-view not found, aborting');
            return;
        }
        // Single-panel navigation: hide ALL panels, then show only this panel.
        window.ensureSinglePanelVisible('strength-view');
        content.classList.add('hidden');
        empty.classList.add('hidden');
        fetch(STRENGTH_URL, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401 || res.status === 403) {
                    throw new Error('not-authenticated');
                }
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(function (data) {
                window.ffLog('[strength] data.linked=', data.linked, 'today=', !!data.today, 'history=', !!(data.history && data.history.length));
                window.renderStrength(data);
            })
            .catch(function (err) {
                window.ffError('[strength] fetch failed:', err);
                content.classList.remove('hidden');
                if (err && err.message === 'not-authenticated') {
                    content.innerHTML = '<p class="error-hint">Please log in to view strength.</p>';
                } else {
                    content.innerHTML = '<p class="error-hint">Could not load strength data (error ' + err + ').</p>';
                }
            });
    };
// Render the strength panel from the /api/v1/strength/ payload.
    window.renderStrength = function (data) {
        var content = document.getElementById('strength-content');
        var empty = document.getElementById('strength-empty');
        if (!content) return;

        if (!data.linked) {
            content.classList.add('hidden');
            window.showEmptyState(empty, {
                icon: 'fa-dumbbell',
                title: 'Link Liftosaur',
                desc: 'No strength data yet. Connect Liftosaur to track your lifting volume.',
                hint: 'Lifting volume, sets and reps earn Strength XP.',
                ctaText: 'Link Liftosaur',
                ctaHref: '/profile/'
            });
            empty.classList.remove('hidden');
            return;
        }
        if (!data.today && !(data.history && data.history.length)) {
            content.classList.add('hidden');
            window.showEmptyState(empty, {
                icon: 'fa-sync-alt',
                title: 'Linked to Liftosaur, waiting for workouts',
                desc: 'Once your Liftosaur workouts sync, your volume and XP will appear here. PRs live in the PR Boss panel.',
                hint: 'Log a session in Liftosaur, then come back to claim your XP.',
                secondary: true
            });
            empty.classList.remove('hidden');
            return;
        }

        empty.classList.add('hidden');
        content.classList.remove('hidden');
        content.innerHTML = '';

        // Strength skill tree progress section.
        var st = data.skill_tree || {};
        var skillSection = document.createElement('div');
        skillSection.className = 'nutrition-skill-section';
        var skillHeader = document.createElement('div');
        skillHeader.className = 'nutrition-skill-header';
        skillHeader.innerHTML = '<i class="fa-solid fa-dumbbell"></i> Strength Skill Tree';
        skillSection.appendChild(skillHeader);

        var skillInfo = document.createElement('div');
        skillInfo.className = 'nutrition-skill-info';
        skillInfo.innerHTML = 'Lv ' + (st.level || 1) + ' &bull; ' + (st.total_xp || 0) + ' Total XP';
        skillSection.appendChild(skillInfo);

        // XP progress bar.
        var xpBarWrap = document.createElement('div');
        xpBarWrap.className = 'nutrition-xp-bar-wrap';
        var xpBar = document.createElement('div');
        xpBar.className = 'nutrition-xp-bar';
        var xpFill = document.createElement('div');
        xpFill.className = 'nutrition-xp-fill';
        var progressPct = Math.min(100, Math.max(0, st.progress_pct || 0));
        xpFill.style.width = progressPct + '%';
        xpBar.appendChild(xpFill);
        xpBarWrap.appendChild(xpBar);
        skillSection.appendChild(xpBarWrap);

        var xpToNext = document.createElement('div');
        xpToNext.className = 'nutrition-xp-to-next';
        xpToNext.textContent = (st.xp || 0) + ' / 100 XP to next level';
        skillSection.appendChild(xpToNext);

        var guidance = document.createElement('div');
        guidance.className = 'nutrition-guidance';
        guidance.innerHTML = '<strong>How to earn XP:</strong> +1 XP per 1,000 lbs moved, +20 XP for finishing a program day, and +1 XP per 30 minutes in the gym.';
        skillSection.appendChild(guidance);

        content.appendChild(skillSection);

        // Today / most-recent workout.
        if (data.today) {
            content.appendChild(buildStrengthCard(data.today, 'Today, ' + data.today.date));
        }

        // History list.
        if (data.history && data.history.length) {
            var wrap = document.createElement('div');
            var title = document.createElement('div');
            title.className = 'history-title';
            title.innerHTML = '<i class="fa-solid fa-list"></i> History';
            wrap.appendChild(title);
            var ul = document.createElement('ul');
            ul.className = 'history-list';
            data.history.forEach(function (day) {
                var li = document.createElement('li');
                li.className = 'history-item' + (day.materials ? ' perfect' : '');
                li.style.cursor = 'pointer';
                li.addEventListener('click', function () { showStrengthDayDetailModal(day); });
                var left = document.createElement('span');
                left.className = 'hist-macros';
                left.textContent = day.date + '  ' + Math.round(day.total_volume_lbs || 0) + ' lbs';
                li.appendChild(left);
                var right = document.createElement('span');
                right.className = 'hist-reward';
                right.textContent = (day.xp ? '+' + day.xp + ' XP' : '') + (day.materials ? ', ' + day.materials + ' mats' : '');
                li.appendChild(right);
                ul.appendChild(li);
            });
            wrap.appendChild(ul);
            content.appendChild(wrap);
        }

        // Interactive Charts + Raw data views (FFInsights / Chart.js).
        if (window.FFInsights) {
            window.FFInsights.createInsights(content, 'strength', data);
        }
    };
// Build a single workout day card (the today card).
    function buildStrengthCard(day, title) {
        var card = document.createElement('div');
        card.className = 'nutrition-day-card';

        var head = document.createElement('div');
        head.className = 'day-card-head';
        var date = document.createElement('div');
        date.className = 'day-date';
        date.textContent = title;
        head.appendChild(date);
        card.appendChild(head);

        if (day.program || day.day_name) {
            var prog = document.createElement('div');
            prog.style.fontSize = '0.85rem';
            prog.style.color = 'var(--text-muted)';
            prog.style.fontWeight = '700';
            prog.textContent = (day.program || '') + (day.day_name ? ' \u00b7 ' + day.day_name : '');
            card.appendChild(prog);
        }

        // Rewards row.
        if (day.xp || day.materials) {
            var rewards = document.createElement('div');
            rewards.className = 'reward-row';
            if (day.xp) {
                var xp = document.createElement('span');
                xp.className = 'reward xp';
                xp.textContent = '+' + day.xp + ' XP';
                rewards.appendChild(xp);
            }
            if (day.materials) {
                var mat = document.createElement('span');
                mat.className = 'reward mat';
                mat.textContent = '+' + day.materials + ' mats';
                rewards.appendChild(mat);
            }
            card.appendChild(rewards);
        }

        // Stats summary.
        var statsRow = document.createElement('div');
        statsRow.className = 'macro-row';
        statsRow.style.flexDirection = 'column';
        statsRow.style.alignItems = 'flex-start';
        statsRow.style.gap = '6px';

        var vol = document.createElement('div');
        vol.style.fontWeight = '700';
        vol.innerHTML = 'Volume Moved: <span style="color: var(--primary-purple);">' +
            Math.round(day.total_volume_lbs || 0) + ' lbs</span>';
        statsRow.appendChild(vol);

        if (day.duration_minutes) {
            var dur = document.createElement('div');
            dur.style.fontWeight = '700';
            dur.innerHTML = 'Time Lifting: <span style="color: var(--text-main);">' +
                Math.round(day.duration_minutes) + ' mins</span>';
            statsRow.appendChild(dur);
        }
        if (day.total_sets) {
            var sets = document.createElement('div');
            sets.style.fontWeight = '700';
            sets.innerHTML = 'Sets: <span style="color: var(--text-main);">' + day.total_sets + '</span>';
            statsRow.appendChild(sets);
        }
        card.appendChild(statsRow);

        // Exercise list.
        if (day.exercises && day.exercises.length) {
            var exList = document.createElement('div');
            exList.style.marginTop = '10px';
            exList.style.borderTop = '2px dashed var(--border-color)';
            exList.style.paddingTop = '10px';

            var exT = document.createElement('div');
            exT.style.fontWeight = '800';
            exT.style.fontSize = '0.8rem';
            exT.style.color = 'var(--text-muted)';
            exT.style.textTransform = 'uppercase';
            exT.style.marginBottom = '8px';
            exT.textContent = 'Exercises';
            exList.appendChild(exT);

            day.exercises.forEach(function (e) {
                var row = document.createElement('div');
                row.style.display = 'flex';
                row.style.justifyContent = 'space-between';
                row.style.padding = '4px 0';
                row.style.borderBottom = '1px solid var(--border-color)';
                row.style.fontWeight = '700';
                row.style.fontSize = '0.9rem';

                var left = document.createElement('span');
                left.style.color = 'var(--text-main)';
                left.textContent = e.name + ' (' + (e.sets || 0) + 's)';
                row.appendChild(left);

                var right = document.createElement('span');
                right.style.color = 'var(--primary-purple)';
                right.textContent = (e.weight || 0) + (e.unit || 'lb') + ' x ' + (e.reps || 0);
                row.appendChild(right);

                exList.appendChild(row);
            });
            card.appendChild(exList);
        }

        return card;
    }
// Show a detailed day view in a modal for historical days.
    window.showStrengthDayDetailModal = function (day) {
        if (window.closeModal) window.closeModal();

        var modalTitle = document.getElementById('modal-title');
        var modalDesc = document.getElementById('modal-desc');
        var modalAction = document.getElementById('modal-action');
        var modalIcon = document.querySelector('.modal-icon i');

        if (modalTitle) modalTitle.textContent = 'Strength Detail';
        if (modalIcon) modalIcon.className = 'fa-solid fa-dumbbell';
        if (modalAction) {
            modalAction.textContent = 'Close';
            modalAction.onclick = function () { if (window.closeModal) window.closeModal(); };
        }

        var detailHtml = '<div style="text-align: left;">';
        detailHtml += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">';
        detailHtml += '<span style="font-weight: 800; font-size: 1.1rem; color: var(--text-main);">' + day.date + '</span>';
        detailHtml += (day.materials ? '<span class="reward mat">+' + day.materials + ' mats</span>' : '');
        detailHtml += '</div>';

        if (day.program || day.day_name) {
            detailHtml += '<div style="margin-bottom: 8px; color: var(--text-muted); font-weight: 700;">' +
                (day.program || '') + (day.day_name ? ' \u00b7 ' + day.day_name : '') + '</div>';
        }

        if (day.xp) detailHtml += '<div style="margin-bottom: 8px;"><span class="reward xp">+' + day.xp + ' XP</span></div>';

        detailHtml += '<div style="margin-bottom: 8px;"><strong>Volume:</strong> ' + Math.round(day.total_volume_lbs || 0) + ' lbs</div>';
        if (day.duration_minutes) detailHtml += '<div style="margin-bottom: 8px;"><strong>Duration:</strong> ' + Math.round(day.duration_minutes) + ' mins</div>';
        detailHtml += '<div style="margin-bottom: 8px;"><strong>Sets:</strong> ' + (day.total_sets || 0) + '</div>';

        if (day.exercises && day.exercises.length) {
            detailHtml += '<div style="margin-top: 12px; border-top: 2px dashed var(--border-color); padding-top: 10px;">';
            detailHtml += '<div style="font-weight: 800; font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">Workout Details</div>';
            day.exercises.forEach(function (e) {
                detailHtml += '<div style="display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid var(--border-color); font-weight: 700; font-size: 0.9rem;">';
                detailHtml += '<span style="color: var(--text-main);">' + e.name + ' (' + (e.sets || 0) + ' sets)</span>';
                detailHtml += '<span style="color: var(--primary-purple);">' + (e.weight || 0) + (e.unit || 'lb') + ' x ' + (e.reps || 0) + ' &middot; est RM ' + (e.est_1rm || 0) + '</span>';
                detailHtml += '</div>';
            });
            detailHtml += '</div>';
        }

        detailHtml += '</div>';

        if (modalDesc) modalDesc.innerHTML = detailHtml;
        if (window.openModal) window.openModal();
    };

    // Bind the purple Strength node on the skill-tree plan.
    var strNode = document.getElementById('node-strength');
    if (strNode) {
        strNode.addEventListener('click', function () { window.loadStrength(); });
    } else {
        window.ffWarn('[strength] node-strength NOT found in DOM');
    }
})();
