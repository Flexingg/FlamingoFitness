/* Endurance detail panel controller (Phase 6, docs/19 #22).
 * Uses window.createModalityController() factory.
 */
(function () {
    'use strict';

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

    window.createModalityController({
        name: 'endurance',
        title: 'Endurance',
        icon: 'fa-bicycle',
        apiUrl: '/api/v1/endurance/',
        guidanceText: 'Hit your daily workouts to earn +1 XP per 10 calories burned (min 10 XP). 500+ calorie workouts award +5 Base Materials!',
        emptyState: {
            icon: 'fa-bicycle',
            title: 'No endurance data yet',
            desc: 'Link SparkyFitness to start tracking your cardio workouts and minutes.',
            hint: 'Cardio minutes and calories earn Endurance XP.',
            ctaText: 'Link SparkyFitness',
            ctaHref: '/profile/'
        },
        renderCustomContent: function (content, data) {
            // 1. Today's Summary Card
            if (data.today) {
                content.appendChild(buildEnduranceCard(data.today, 'Today, ' + data.today.date));
            }

            // 2. Trends & Insights
            if (window.FFInsights) {
                window.FFInsights.createInsights(content, 'endurance', data);
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
                    li.className = 'history-item' + (day.materials ? ' perfect' : '');
                    li.style.cursor = 'pointer';
                    li.addEventListener('click', function () {
                        window.showEnduranceDayDetailModal(day);
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
        }
    });

    var endNode = document.getElementById('node-endurance');
    if (endNode) {
        endNode.addEventListener('click', function () {
            window.loadEndurance();
        });
    }
})();
