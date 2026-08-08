/* Endurance detail panel controller (loaded after dashboard.js).
 * Opens from the blue Endurance node (#node-endurance) on the skill-tree plan.
 * Consumes GET /api/v1/endurance/ (core/views.py endurance_state).
 */
(function () {
    'use strict';

    var ENDURANCE_URL = '/api/v1/endurance/';

    // Return to the skill-tree plan from the endurance panel.
    window.backToEndurancePlan = function () {
        var view = document.getElementById('endurance-view');
        if (view) view.classList.add('hidden');
        var tree = document.getElementById('skill-tree');
        if (tree) tree.classList.remove('hidden');
        var hint = document.getElementById('loading-hint');
        if (hint) hint.classList.add('hidden');
    };

    // Fetch + render the endurance panel.
    window.loadEndurance = function () {
        console.log('[endurance] loadEndurance start');
        if (window.closeModal) window.closeModal();
        var view = document.getElementById('endurance-view');
        var content = document.getElementById('endurance-content');
        var empty = document.getElementById('endurance-empty');
        var tree = document.getElementById('skill-tree');
        if (!view) {
            console.warn('[endurance] endurance-view not found, aborting');
            return;
        }
        if (tree) tree.classList.add('hidden');
        view.classList.remove('hidden');
        content.classList.add('hidden');
        empty.classList.add('hidden');
        fetch(ENDURANCE_URL, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401 || res.status === 403) {
                    throw new Error('not-authenticated');
                }
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(function (data) {
                console.log('[endurance] renderEndurance data.linked=', data.linked, 'today=', !!data.today, 'history=', !!(data.history && data.history.length));
                window.renderEndurance(data);
            })
            .catch(function (err) {
                console.error('[endurance] fetch failed:', err);
                content.classList.remove('hidden');
                if (err && err.message === 'not-authenticated') {
                    content.innerHTML = '<p class="error-hint">Please log in to view endurance.</p>';
                } else {
                    content.innerHTML = '<p class="error-hint">Could not load endurance data (error ' + err + ').</p>';
                }
            });
    };

    // Render the endurance panel from the /api/v1/endurance/ payload.
    window.renderEndurance = function (data) {
        var content = document.getElementById('endurance-content');
        var empty = document.getElementById('endurance-empty');
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

        // Endurance skill tree progress section.
        var st = data.skill_tree || {};
        var skillSection = document.createElement('div');
        skillSection.className = 'nutrition-skill-section';
        var skillHeader = document.createElement('div');
        skillHeader.className = 'nutrition-skill-header';
        skillHeader.innerHTML = '<i class="fa-solid fa-star"></i> Endurance Skill Tree';
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
        guidance.innerHTML = '<strong>How to earn XP:</strong> Hit your daily workouts to earn +1 XP per 10 calories burned (min 10 XP). 500+ calorie workouts award +5 Base Materials!';
        skillSection.appendChild(guidance);

        content.appendChild(skillSection);

        // Today / most-recent day.
        if (data.today) {
            content.appendChild(buildEnduranceCard(data.today, 'Today, ' + data.today.date));
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
                li.addEventListener('click', function () {
                    showEnduranceDayDetailModal(day);
                });
                var left = document.createElement('span');
                left.className = 'hist-macros';
                left.textContent = day.date + '  ' + Math.round(day.total_calories_burned || 0) +
                    ' cal (' + Math.round(day.total_duration_minutes || 0) + 'm)';
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

        // Endurance skill summary.
        var st = data.skill_tree || {};
        var skill = document.createElement('div');
        skill.className = 'reward';
        skill.style.marginTop = '18px';
        skill.style.justifyContent = 'center';
        skill.textContent = (st.level ? 'Endurance Lv ' + st.level : 'Endurance') + '  ' + (st.total_xp || 0) + ' XP';
        content.appendChild(skill);
    };

    // Build a single day card (the today card).
    function buildEnduranceCard(day, title) {
        var card = document.createElement('div');
        card.className = 'nutrition-day-card';

        var head = document.createElement('div');
        head.className = 'day-card-head';
        var date = document.createElement('div');
        date.className = 'day-date';
        date.textContent = title;
        head.appendChild(date);

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

        // Totals summary (calories burned + duration).
        var statsRow = document.createElement('div');
        statsRow.className = 'macro-row';
        statsRow.style.flexDirection = 'column';
        statsRow.style.alignItems = 'flex-start';
        statsRow.style.gap = '6px';

        var caloriesLine = document.createElement('div');
        caloriesLine.style.fontWeight = '700';
        caloriesLine.innerHTML = 'Calories Burned: <span style="color: var(--primary-blue);">' +
            Math.round(day.total_calories_burned || 0) + ' kcal</span>';
        statsRow.appendChild(caloriesLine);

        var durationLine = document.createElement('div');
        durationLine.style.fontWeight = '700';
        durationLine.innerHTML = 'Total Duration: <span style="color: var(--text-main);">' +
            Math.round(day.total_duration_minutes || 0) + ' mins</span>';
        statsRow.appendChild(durationLine);

        card.appendChild(statsRow);

        // Individual workouts logged for the day.
        if (day.exercise_entries && day.exercise_entries.length) {
            var exList = document.createElement('div');
            exList.style.marginTop = '10px';
            exList.style.borderTop = '2px dashed var(--border-color)';
            exList.style.paddingTop = '10px';

            var exTitle = document.createElement('div');
            exTitle.className = 'nutrition-skill-info';
            exTitle.style.fontWeight = '800';
            exTitle.style.fontSize = '0.8rem';
            exTitle.style.color = 'var(--text-muted)';
            exTitle.style.textTransform = 'uppercase';
            exTitle.style.marginBottom = '8px';
            exTitle.textContent = 'Workouts Logged';
            exList.appendChild(exTitle);

            day.exercise_entries.forEach(function (entry) {
                var item = document.createElement('div');
                item.style.display = 'flex';
                item.style.justifyContent = 'space-between';
                item.style.padding = '4px 0';
                item.style.borderBottom = '1px solid var(--border-color)';
                item.style.fontWeight = '700';
                item.style.fontSize = '0.9rem';

                var left = document.createElement('span');
                left.style.color = 'var(--text-main)';
                left.textContent = (entry.name || 'Workout') +
                    (entry.duration_minutes ? ' (' + Math.round(entry.duration_minutes) + 'm)' : '');
                item.appendChild(left);

                var right = document.createElement('span');
                right.style.color = 'var(--primary-blue)';
                right.textContent = Math.round(entry.calories_burned || 0) + ' cal';
                item.appendChild(right);

                exList.appendChild(item);
            });
            card.appendChild(exList);
        }

        return card;
    }

    // Show a detailed day view in a modal for historical days.
    window.showEnduranceDayDetailModal = function (day) {
        if (window.closeModal) window.closeModal();

        var modalTitle = document.getElementById('modal-title');
        var modalDesc = document.getElementById('modal-desc');
        var modalAction = document.getElementById('modal-action');
        var modalIcon = document.querySelector('.modal-icon i');

        if (modalTitle) modalTitle.textContent = 'Endurance Detail';
        if (modalIcon) modalIcon.className = 'fa-solid fa-bicycle';
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

        detailHtml += '<div style="margin-bottom: 8px;"><strong>Total Calories:</strong> ' + Math.round(day.total_calories_burned || 0) + ' kcal</div>';
        detailHtml += '<div style="margin-bottom: 8px;"><strong>Total Duration:</strong> ' + Math.round(day.total_duration_minutes || 0) + ' mins</div>';

        if (day.exercise_entries && day.exercise_entries.length) {
            detailHtml += '<div style="margin-top: 12px; border-top: 2px dashed var(--border-color); padding-top: 10px;">';
            detailHtml += '<div style="font-weight: 800; font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">Workouts Logged</div>';
            day.exercise_entries.forEach(function (entry) {
                detailHtml += '<div style="display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid var(--border-color); font-weight: 700; font-size: 0.9rem;">';
                detailHtml += '<span style="color: var(--text-main);">' + (entry.name || 'Workout') + (entry.duration_minutes ? ' (' + Math.round(entry.duration_minutes) + 'm)' : '') + '</span>';
                detailHtml += '<span style="color: var(--primary-blue);">' + Math.round(entry.calories_burned || 0) + ' cal</span>';
                detailHtml += '</div>';
            });
            detailHtml += '</div>';
        }

        detailHtml += '</div>';

        if (modalDesc) modalDesc.innerHTML = detailHtml;
        if (window.openModal) window.openModal();
    };

    // Bind the blue Endurance node on the skill-tree plan.
    var hydNode = document.getElementById('node-endurance');
    if (hydNode) {
        console.log('[endurance] node-endurance found, binding click');
        hydNode.addEventListener('click', function () {
            console.log('[endurance] node-endurance clicked');
            window.loadEndurance();
        });
    } else {
        console.warn('[endurance] node-endurance NOT found in DOM');
    }
})();
