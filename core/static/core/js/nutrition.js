/* Nutrition detail panel controller (loaded after dashboard.js).
 * Opens from the red Nutrition node (#node-nutrition) on the skill-tree plan.
 * Consumes GET /api/v1/nutrition/ (core/views.py nutrition_state, docs/02 + docs/10).
 */
(function () {
    'use strict';

    var NUTRITION_URL = '/api/v1/nutrition/';

    // Return to the skill-tree plan from the nutrition panel.
    window.backToNutritionPlan = function () {
        var view = document.getElementById('nutrition-view');
        if (view) view.classList.add('hidden');
        // Use ensureSinglePanelVisible to hide all other panels first,
        // then show only the skill tree (prevents stacking)
        window.ensureSinglePanelVisible('skill-tree');
    };

    // Fetch + render the nutrition panel.
    window.loadNutrition = function () {
        console.log('[nutrition] loadNutrition start');
        if (window.closeModal) window.closeModal();
        var view = document.getElementById('nutrition-view');
        var content = document.getElementById('nutrition-content');
        var empty = document.getElementById('nutrition-empty');
        var tree = document.getElementById('skill-tree');
        console.log('[nutrition] view=', !!view, 'tree=', !!tree);
        if (!view) {
            console.warn('[nutrition] nutrition-view not found, aborting');
            return;
        }
        // Single-panel navigation: hide ALL panels, then show only this panel.
        window.ensureSinglePanelVisible('nutrition-view');
        content.classList.add('hidden');
        empty.classList.add('hidden');
        console.log('[nutrition] fetching', NUTRITION_URL);
        fetch(NUTRITION_URL, { credentials: 'same-origin' })
            .then(function (res) {
                console.log('[nutrition] fetch response status:', res.status);
                if (res.status === 401 || res.status === 403) {
                    throw new Error('not-authenticated');
                }
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(function (data) {
                console.log('[nutrition] renderNutrition data.linked=', data.linked, 'today=', !!data.today, 'history=', !!(data.history && data.history.length));
                window.renderNutrition(data);
            })
            .catch(function (err) {
                console.error('[nutrition] fetch failed:', err);
                content.classList.remove('hidden');
                if (err && err.message === 'not-authenticated') {
                    content.innerHTML = '<p class="error-hint">Please log in to view nutrition.</p>';
                } else {
                    content.innerHTML = '<p class="error-hint">Could not load nutrition data (error ' + err + ').</p>';
                }
            });
    };

    // Render the nutrition panel from the /api/v1/nutrition/ payload.
    window.renderNutrition = function (data) {
        var content = document.getElementById('nutrition-content');
        var empty = document.getElementById('nutrition-empty');
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

        // Nutrition skill tree progress section.
        var st = data.skill_tree || {};
        var skillSection = document.createElement('div');
        skillSection.className = 'nutrition-skill-section';
        var skillHeader = document.createElement('div');
        skillHeader.className = 'nutrition-skill-header';
        skillHeader.innerHTML = '<i class="fa-solid fa-star"></i> Nutrition Skill Tree';
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
        guidance.innerHTML = '<strong>How to earn XP:</strong> Hit your protein goal and stay under your calorie cap for +50 XP and +10 Materials per day!';
        skillSection.appendChild(guidance);
        
        content.appendChild(skillSection);

        // Today / most-recent day.
        if (data.today) {
            content.appendChild(buildDayCard(data.today, 'Today, ' + data.today.date));
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
                    showDayDetailModal(day);
                });
                var left = document.createElement('span');
                left.className = 'hist-macros';
                left.textContent = day.date + '  ' + formatMacro(day.protein, day.protein_goal) + '  ' + formatMacro(day.calories, day.calorie_goal);
                li.appendChild(left);
                var right = document.createElement('span');
                right.className = 'hist-reward';
                right.textContent = (day.perfect ? 'PERFECT ' : '') + (day.xp ? '+' + day.xp + ' XP' : '') + (day.materials ? ', ' + day.materials + ' mats' : '');
                li.appendChild(right);
                ul.appendChild(li);
            });
            wrap.appendChild(ul);
            content.appendChild(wrap);
        }

        // Nutrition skill summary.
        var st = data.skill_tree || {};
        var skill = document.createElement('div');
        skill.className = 'reward';
        skill.style.marginTop = '18px';
        skill.style.justifyContent = 'center';
        skill.textContent = (st.level ? 'Nutrition Lv ' + st.level : 'Nutrition') + '  ' + (st.total_xp || 0) + ' XP';
        content.appendChild(skill);
    };

    function formatMacro(value, goal) {
        return Math.round(value || 0) + (goal !== undefined ? '/' + Math.round(goal || 0) : '');
        }

    // Build a single day card (the today card).
    function buildDayCard(day, title) {
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
        badge.textContent = day.perfect ? 'PERFECT' : 'Needs work';
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

        // Macro progress bars.
        card.appendChild(buildMacroBar('Protein', day.protein_pct || 0, Math.round(day.protein || 0) + '/' + Math.round(day.protein_goal || 0), 'var(--primary-purple)'));
        card.appendChild(buildMacroBar('Calories', day.calorie_pct || 0, Math.round(day.calories || 0) + '/' + Math.round(day.calorie_goal || 0), 'var(--primary-red)'));

        // Meals.
        if (day.food_entries && day.food_entries.length) {
            var list = document.createElement('div');
            list.className = 'food-list';
            var listTitle = document.createElement('div');
            listTitle.className = 'food-list-title';
            listTitle.textContent = 'Meals';
            list.appendChild(listTitle);
            day.food_entries.forEach(function (f) {
                var item = document.createElement('div');
                item.className = 'food-item';
                var name = document.createElement('span');
                name.className = 'food-name';
                name.textContent = f.name;
                var pro = document.createElement('span');
                pro.className = 'food-pro';
                pro.textContent = Math.round(f.protein || 0) + 'g';
                var cal = document.createElement('span');
                cal.className = 'food-cal';
                cal.textContent = Math.round(f.calories || 0) + ' cal';
                item.appendChild(name);
                item.appendChild(pro);
                item.appendChild(cal);
                list.appendChild(item);
            });
            card.appendChild(list);
        }

        return card;
    }

    function buildMacroBar(label, pct, goal, color) {
        var row = document.createElement('div');
        row.className = 'macro-bar';
        var lbl = document.createElement('span');
        lbl.className = 'macro-label';
        lbl.textContent = label;
        row.appendChild(lbl);
        var track = document.createElement('div');
        track.className = 'bar';
        var fill = document.createElement('div');
        fill.className = 'bar-fill';
        fill.style.width = Math.min(100, Math.max(0, pct || 0)) + '%';
        fill.style.backgroundColor = color;
        track.appendChild(fill);
        row.appendChild(track);
        var g = document.createElement('span');
        g.className = 'macro-goal';
        g.textContent = goal;
        row.appendChild(g);
        return row;
    }

    // Show a detailed day view in a modal for historical days.
    window.showDayDetailModal = function (day) {
        if (window.closeModal) window.closeModal();
        
        var modalTitle = document.getElementById('modal-title');
        var modalDesc = document.getElementById('modal-desc');
        var modalAction = document.getElementById('modal-action');
        var modalIcon = document.querySelector('.modal-icon i');
        
        if (modalTitle) modalTitle.textContent = 'Nutrition Detail';
        if (modalIcon) modalIcon.className = 'fa-solid fa-apple-whole';
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
        detailHtml += '<span class="' + (day.perfect ? 'perfect-badge' : 'imperfect-badge') + '" style="font-size: 0.8rem;">' + (day.perfect ? 'PERFECT' : 'Needs work') + '</span>';
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
        
        detailHtml += '<div style="margin-bottom: 8px;"><strong>Protein:</strong> ' + Math.round(day.protein || 0) + 'g / ' + Math.round(day.protein_goal || 0) + 'g (' + (day.protein_pct || 0) + '%)</div>';
        detailHtml += '<div style="margin-bottom: 8px;"><strong>Calories:</strong> ' + Math.round(day.calories || 0) + ' / ' + Math.round(day.calorie_goal || 0) + ' (' + (day.calorie_pct || 0) + '%)</div>';
        
        if (day.food_entries && day.food_entries.length) {
            detailHtml += '<div style="margin-top: 12px; border-top: 2px dashed var(--border-color); padding-top: 10px;">';
            detailHtml += '<div style="font-weight: 800; font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">Meals</div>';
            day.food_entries.forEach(function (f) {
                detailHtml += '<div style="display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid var(--border-color); font-weight: 700; font-size: 0.9rem;">';
                detailHtml += '<span style="color: var(--text-main);">' + f.name + '</span>';
                detailHtml += '<span style="color: var(--primary-purple);">' + Math.round(f.protein || 0) + 'g</span>';
                detailHtml += '<span style="color: var(--text-muted);">' + Math.round(f.calories || 0) + ' cal</span>';
                detailHtml += '</div>';
            });
            detailHtml += '</div>';
        }
        
        detailHtml += '</div>';
        
        if (modalDesc) modalDesc.innerHTML = detailHtml;
        if (window.openModal) window.openModal();
    };

    // Bind the red Nutrition node on the skill-tree plan.
    var nutNode = document.getElementById('node-nutrition');
    if (nutNode) {
        console.log('[nutrition] node-nutrition found, binding click');
        nutNode.addEventListener('click', function () {
            console.log('[nutrition] node-nutrition clicked');
            window.loadNutrition();
        });
    } else {
        console.warn('[nutrition] node-nutrition NOT found in DOM');
    }
})();
