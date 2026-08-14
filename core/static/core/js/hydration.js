/* Hydration detail panel controller (loaded after dashboard.js).
 * Opens from the blue Hydration node (#node-hydration) on the skill-tree plan.
 * Consumes GET /api/v1/hydration/ (core/views.py hydration_state).
 */
(function () {
    'use strict';

    var HYDRATION_URL = '/api/v1/hydration/';

    // Return to the skill-tree plan from the hydration panel.
    window.backToHydrationPlan = function () {
        var view = document.getElementById('hydration-view');
        if (view) view.classList.add('hidden');
        // Use ensureSinglePanelVisible to hide all other panels first,
        // then show only the skill tree (prevents stacking)
        window.ensureSinglePanelVisible('skill-tree');
    };

    // Fetch + render the hydration panel.
    window.loadHydration = function () {
        console.log('[hydration] loadHydration start');
        if (window.closeModal) window.closeModal();
        var view = document.getElementById('hydration-view');
        var content = document.getElementById('hydration-content');
        var empty = document.getElementById('hydration-empty');
        var tree = document.getElementById('skill-tree');
        if (!view) {
            console.warn('[hydration] hydration-view not found, aborting');
            return;
        }
        // Single-panel navigation: hide ALL panels, then show only this panel.
        window.ensureSinglePanelVisible('hydration-view');
        content.classList.add('hidden');
        empty.classList.add('hidden');
        fetch(HYDRATION_URL, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401 || res.status === 403) {
                    throw new Error('not-authenticated');
                }
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(function (data) {
                console.log('[hydration] renderHydration data.linked=', data.linked, 'today=', !!data.today, 'history=', !!(data.history && data.history.length));
                window.renderHydration(data);
            })
            .catch(function (err) {
                console.error('[hydration] fetch failed:', err);
                content.classList.remove('hidden');
                if (err && err.message === 'not-authenticated') {
                    content.innerHTML = '<p class="error-hint">Please log in to view hydration.</p>';
                } else {
                    content.innerHTML = '<p class="error-hint">Could not load hydration data (error ' + err + ').</p>';
                }
            });
    };

    // Render the hydration panel from the /api/v1/hydration/ payload.
    window.renderHydration = function (data) {
        var content = document.getElementById('hydration-content');
        var empty = document.getElementById('hydration-empty');
        if (!content) return;

        // Not linked, or no data at all -> show the Link-Sparky CTA.
        if (!data.linked || (!data.today && !(data.history && data.history.length))) {
            content.classList.add('hidden');
            empty.classList.remove('hidden');
            return;
        }

        empty.classList.add('hidden');
        content.classList.remove('hidden');
        content.innerHTML = '';

        // Hydration skill tree progress section.
        var st = data.skill_tree || {};
        var skillSection = document.createElement('div');
        skillSection.className = 'nutrition-skill-section';
        var skillHeader = document.createElement('div');
        skillHeader.className = 'nutrition-skill-header';
        skillHeader.innerHTML = '<i class="fa-solid fa-star"></i> Hydration Skill Tree';
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
        var currentXp = st.xp || 0;
        xpToNext.textContent = currentXp + ' / 100 XP to next level';
        skillSection.appendChild(xpToNext);

        // How to earn XP guidance.
        var guidance = document.createElement('div');
        guidance.className = 'nutrition-guidance';
        guidance.innerHTML = '<strong>How to earn XP:</strong> Hit your daily water intake goal for +30 XP and +5 Materials per day!';
        skillSection.appendChild(guidance);

        content.appendChild(skillSection);

        // Today / most-recent day.
        if (data.today) {
            content.appendChild(buildHydrationCard(data.today, 'Today, ' + data.today.date));
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
                li.className = 'history-item' + (day.perfect ? ' perfect' : '');
                li.style.cursor = 'pointer';
                li.addEventListener('click', function () {
                    showHydrationDayDetailModal(day);
                });
                var left = document.createElement('span');
                left.className = 'hist-macros';
                left.textContent = day.date + '  ' + formatWater(day.water, day.water_goal);
                li.appendChild(left);
                var right = document.createElement('span');
                right.className = 'hist-reward';
                right.textContent = (day.perfect ? 'ON TARGET ' : '') + (day.xp ? '+' + day.xp + ' XP' : '') + (day.materials ? ', ' + day.materials + ' mats' : '');
                li.appendChild(right);
                ul.appendChild(li);
            });
            wrap.appendChild(ul);
            content.appendChild(wrap);
        }

        // Hydration skill summary.
        var st = data.skill_tree || {};
        var skill = document.createElement('div');
        skill.className = 'reward';
        skill.style.marginTop = '18px';
        skill.style.justifyContent = 'center';
        skill.textContent = (st.level ? 'Hydration Lv ' + st.level : 'Hydration') + '  ' + (st.total_xp || 0) + ' XP';
        content.appendChild(skill);
    };

    function formatWater(value, goal) {
        return Math.round(value || 0) + (goal !== undefined ? '/' + Math.round(goal || 0) + ' oz' : '');
    }

    // Build a single day card (the today card).
    function buildHydrationCard(day, title) {
        var card = document.createElement('div');
        card.className = 'nutrition-day-card';

        var head = document.createElement('div');
        head.className = 'day-card-head';
        var date = document.createElement('div');
        date.className = 'day-date';
        date.textContent = title;
        head.appendChild(date);
        var badge = document.createElement('span');
        badge.className = day.perfect ? 'perfect-badge' : 'imperfect-badge';
        badge.textContent = day.perfect ? 'ON TARGET' : 'Needs work';
        head.appendChild(badge);
        card.appendChild(head);

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

        // Water intake bar.
        var waterRow = document.createElement('div');
        waterRow.className = 'macro-row';
        var waterLabel = document.createElement('span');
        waterLabel.className = 'macro-label';
        waterLabel.textContent = 'Water';
        waterRow.appendChild(waterLabel);
        var waterTrack = document.createElement('div');
        waterTrack.className = 'bar';
        var waterFill = document.createElement('div');
        waterFill.className = 'bar-fill';
        waterFill.style.width = Math.min(100, Math.max(0, day.water_pct || 0)) + '%';
        waterFill.style.backgroundColor = 'var(--primary-blue)';
        waterTrack.appendChild(waterFill);
        waterRow.appendChild(waterTrack);
        var waterGoal = document.createElement('span');
        waterGoal.className = 'macro-goal';
        waterGoal.textContent = Math.round(day.water || 0) + ' / ' + Math.round(day.water_goal || 0) + ' oz';
        waterRow.appendChild(waterGoal);
        card.appendChild(waterRow);

        return card;
    }

    // Show a detailed day view in a modal for historical days.
    window.showHydrationDayDetailModal = function (day) {
        if (window.closeModal) window.closeModal();

        var modalTitle = document.getElementById('modal-title');
        var modalDesc = document.getElementById('modal-desc');
        var modalAction = document.getElementById('modal-action');
        var modalIcon = document.querySelector('.modal-icon i');

        if (modalTitle) modalTitle.textContent = 'Hydration Detail';
        if (modalIcon) modalIcon.className = 'fa-solid fa-glass-water';
        if (modalAction) {
            modalAction.textContent = 'Close';
            modalAction.onclick = function () {
                if (window.closeModal) window.closeModal();
            };
        }

        // Build the day detail HTML.
        var detailHtml = '<div style="text-align: left;">';
        detailHtml += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">';
        detailHtml += '<span style="font-weight: 800; font-size: 1.1rem; color: var(--text-main);">' + day.date + '</span>';
        detailHtml += '<span class="' + (day.perfect ? 'perfect-badge' : 'imperfect-badge') + '" style="font-size: 0.8rem;">' + (day.perfect ? 'ON TARGET' : 'Needs work') + '</span>';
        detailHtml += '</div>';

        if (day.xp || day.materials) {
            detailHtml += '<div style="display: flex; gap: 14px; margin-bottom: 12px; flex-wrap: wrap;">';
            if (day.xp) {
                detailHtml += '<span class="reward xp" style="display: inline-flex; align-items: center; gap: 6px; font-weight: 800;"><i class="fa-solid fa-star"></i> +' + day.xp + ' XP</span>';
            }
            if (day.materials) {
                detailHtml += '<span class="reward mat" style="display: inline-flex; align-items: center; gap: 6px; font-weight: 800;"><i class="fa-solid fa-gem"></i> +' + day.materials + ' mats</span>';
            }
            detailHtml += '</div>';
        }

        detailHtml += '<div style="margin-bottom: 8px;"><strong>Water:</strong> ' + Math.round(day.water || 0) + ' oz / ' + Math.round(day.water_goal || 0) + ' oz (' + (day.water_pct || 0) + '%)</div>';

        if (day.water_intake_entries && day.water_intake_entries.length) {
            detailHtml += '<div style="margin-top: 12px; border-top: 2px dashed var(--border-color); padding-top: 10px;">';
            detailHtml += '<div style="font-weight: 800; font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">Intake Log</div>';
            day.water_intake_entries.forEach(function (entry) {
                detailHtml += '<div style="display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid var(--border-color); font-weight: 700; font-size: 0.9rem;">';
                detailHtml += '<span style="color: var(--text-main);">' + (entry.time || 'Unknown') + '</span>';
                detailHtml += '<span style="color: var(--primary-blue);">' + Math.round(entry.amount || 0) + ' oz</span>';
                detailHtml += '</div>';
            });
            detailHtml += '</div>';
        }

        detailHtml += '</div>';

        if (modalDesc) modalDesc.innerHTML = detailHtml;
        if (window.openModal) window.openModal();
    };

    // Bind the blue Hydration node on the skill-tree plan.
    var hydNode = document.getElementById('node-hydration');
    if (hydNode) {
        console.log('[hydration] node-hydration found, binding click');
        hydNode.addEventListener('click', function () {
            console.log('[hydration] node-hydration clicked');
            window.loadHydration();
        });
    } else {
        console.warn('[hydration] node-hydration NOT found in DOM');
    }
})();
