/* Nutrition detail panel controller (Phase 6, docs/19 #22).
 * Uses window.createModalityController() factory.
 */
(function () {
    'use strict';

    function formatMacro(value, goal) {
        return Math.round(value || 0) + (goal !== undefined ? '/' + Math.round(goal || 0) : '');
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

    function buildMacroDonut(protein, calories) {
        var p = Math.max(0, protein || 0);
        var c = Math.max(0, calories || 0);
        var pCal = p * 4;
        var total = Math.max(c, pCal) || 1;
        var pPct = Math.min(100, Math.round((pCal / total) * 100));

        var pOffset = 251.2 * (1 - pPct / 100);

        var wrap = document.createElement('div');
        wrap.className = 'macro-donut-wrap flex items-center justify-between my-3 p-3 bg-slate-800/60 rounded-xl border border-slate-700/50';
        wrap.innerHTML = '<div class="relative w-16 h-16 flex items-center justify-center">' +
            '<svg class="w-16 h-16 -rotate-90" viewBox="0 0 100 100">' +
            '<circle cx="50" cy="50" r="40" fill="none" stroke="rgba(244, 63, 94, 0.4)" stroke-width="12" />' +
            '<circle cx="50" cy="50" r="40" fill="none" stroke="#9333ea" stroke-width="12" stroke-dasharray="251.2" stroke-dashoffset="' + pOffset + '" stroke-linecap="round" />' +
            '</svg>' +
            '<span class="absolute text-[11px] font-black text-slate-200">' + pPct + '%</span>' +
            '</div>' +
            '<div class="flex-1 pl-4 text-xs font-bold">' +
            '<div class="flex items-center gap-1.5 text-purple-400 mb-1"><span class="w-2.5 h-2.5 rounded-full bg-purple-500 inline-block"></span> Protein: ' + Math.round(p) + 'g (' + pCal + ' kcal)</div>' +
            '<div class="flex items-center gap-1.5 text-rose-400"><span class="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block"></span> Total: ' + Math.round(c) + ' kcal</div>' +
            '</div>';
        return wrap;
    }

    function getStatusBadge(day) {
        if (day.perfect) {
            return { cls: 'perfect-badge', text: 'PERFECT' };
        }
        if (day.status === 'close' || (day.xp >= 35)) {
            return { cls: 'close-badge', text: 'NEAR GOAL' };
        }
        if (day.status === 'partial' || (day.xp > 0)) {
            return { cls: 'partial-badge', text: 'PROGRESS' };
        }
        return { cls: 'imperfect-badge', text: 'Needs work' };
    }

    function buildDayCard(day, title) {
        var card = document.createElement('div');
        card.className = 'nutrition-day-card';

        var head = document.createElement('div');
        head.className = 'day-card-head';
        var date = document.createElement('div');
        date.className = 'day-date';
        date.textContent = title;
        head.appendChild(date);
        var badgeInfo = getStatusBadge(day);
        var badge = document.createElement('span');
        badge.className = badgeInfo.cls;
        badge.textContent = badgeInfo.text;
        head.appendChild(badge);
        card.appendChild(head);

        var rewardTokens = day.tokens !== undefined ? day.tokens : day.materials;
        if (day.xp || rewardTokens) {
            var rewards = document.createElement('div');
            rewards.className = 'reward-row';
            if (day.xp) {
                var xp = document.createElement('span');
                xp.className = 'reward xp';
                xp.textContent = '+' + day.xp + ' XP';
                rewards.appendChild(xp);
            }
            if (rewardTokens) {
                var mat = document.createElement('span');
                mat.className = 'reward mat';
                mat.textContent = '+' + rewardTokens + ' tokens';
                rewards.appendChild(mat);
            }
            card.appendChild(rewards);
        }

        // Macro Mini-Donut distribution
        card.appendChild(buildMacroDonut(day.protein, day.calories));

        card.appendChild(buildMacroBar('Protein', day.protein_pct || 0, Math.round(day.protein || 0) + '/' + Math.round(day.protein_goal || 0), 'var(--primary-purple)'));
        card.appendChild(buildMacroBar('Calories', day.calorie_pct || 0, Math.round(day.calories || 0) + '/' + Math.round(day.calorie_goal || 0), 'var(--primary-red)'));

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
        
        var badgeInfo = getStatusBadge(day);
        var detailHtml = '<div style="text-align: left;">';
        detailHtml += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">';
        detailHtml += '<span style="font-weight: 800; font-size: 1.1rem; color: var(--text-main);">' + day.date + '</span>';
        detailHtml += '<span class="' + badgeInfo.cls + '" style="font-size: 0.8rem;">' + badgeInfo.text + '</span>';
        detailHtml += '</div>';
        
        var rewardTokens = day.tokens !== undefined ? day.tokens : day.materials;
        if (day.xp || rewardTokens) {
            detailHtml += '<div style="display: flex; gap: 14px; margin-bottom: 12px; flex-wrap: wrap;">';
            if (day.xp) {
                detailHtml += '<span class="reward xp" style="display: inline-flex; align-items: center; gap: 6px; font-weight: 800;"><i class="fa-solid fa-star"></i> +' + day.xp + ' XP</span>';
            }
            if (rewardTokens) {
                detailHtml += '<span class="reward mat" style="display: inline-flex; align-items: center; gap: 6px; font-weight: 800;"><i class="fa-solid fa-gem"></i> +' + rewardTokens + ' tokens</span>';
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

    window.createModalityController({
        name: 'nutrition',
        title: 'Nutrition',
        icon: 'fa-apple-whole',
        apiUrl: '/api/v1/nutrition/',
        guidanceText: 'Hit your protein goal and calorie budget for max XP (+50) & tokens (+25). Being close or hitting individual goals earns tiered rewards!',
        emptyState: {
            icon: 'fa-apple-whole',
            title: 'No nutrition data yet',
            desc: 'Link SparkyFitness to start tracking your macros and hitting your protein goals.',
            hint: 'Nutrition XP flows in once your food syncs.',
            ctaText: 'Link SparkyFitness',
            ctaHref: '/profile/'
        },
        renderCustomContent: function (content, data) {
            // 1. Today's Summary Card
            if (data.today) {
                content.appendChild(buildDayCard(data.today, 'Today, ' + data.today.date));
            }

            // 2. Trends & Insights
            if (window.FFInsights) {
                window.FFInsights.createInsights(content, 'nutrition', data);
            }

            // 3. History List (at the very bottom)
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
                        window.showDayDetailModal(day);
                    });
                    var left = document.createElement('span');
                    left.className = 'hist-macros';
                    left.textContent = day.date + '  ' + formatMacro(day.protein, day.protein_goal) + '  ' + formatMacro(day.calories, day.calorie_goal);
                    li.appendChild(left);
                    var right = document.createElement('span');
                    right.className = 'hist-reward';
                    var badgeInfo = getStatusBadge(day);
                    var tok = day.tokens !== undefined ? day.tokens : day.materials;
                    right.textContent = badgeInfo.text + ' ' + (day.xp ? '+' + day.xp + ' XP' : '') + (tok ? ', ' + tok + ' tok' : '');
                    li.appendChild(right);
                    ul.appendChild(li);
                });
                wrap.appendChild(ul);
                content.appendChild(wrap);
            }
        }
    });

    var nutNode = document.getElementById('node-nutrition');
    if (nutNode) {
        nutNode.addEventListener('click', function () {
            window.loadNutrition();
        });
    }
})();
