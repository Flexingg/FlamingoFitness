/* Recovery detail panel controller (Phase 6, docs/19 #22).
 * Uses window.createModalityController() factory.
 */
(function () {
    'use strict';

    window.createModalityController({
        name: 'recovery',
        title: 'Recovery',
        icon: 'fa-bed',
        apiUrl: '/api/v1/recovery/',
        guidanceText: 'Sleep 8+ hours for optimal recovery (+50 XP). Getting 7h+ (+35 XP), 6h+ (+25 XP), or 5h+ (+15 XP) still earns great XP. Rest days protect your streak!',
        emptyState: {
            icon: 'fa-bed',
            title: 'Link SparkyFitness',
            desc: 'No recovery data yet. Connect SparkyFitness to track sleep and readiness.',
            hint: 'Sleep and readiness feed your Recovery skill tree and daily streak.',
            ctaText: 'Link SparkyFitness',
            ctaHref: '/profile/'
        },
        renderCustomContent: function (content, data) {
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

            var score = r.score != null ? r.score : 75;
            var fillColor = score >= 80 ? '#10b981' : (score >= 50 ? '#f59e0b' : '#ef4444');

            var scoreRow = document.createElement('div');
            scoreRow.className = 'macro-row flex items-center justify-between';
            scoreRow.innerHTML = '<span class="macro-label font-bold text-slate-300">Readiness Score</span>' +
                '<div class="flex items-center gap-2">' +
                '<div class="battery-meter">' +
                '<div class="battery-body"><div class="battery-fill" style="width: ' + score + '%; background-color: ' + fillColor + ';"></div></div>' +
                '<div class="battery-cap"></div>' +
                '</div>' +
                '<span class="macro-value font-black text-slate-100">' + (r.score != null ? r.score + '%' : '\u2014') + '</span>' +
                '</div>';
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

            // 2. Trends & Insights
            if (window.FFInsights) {
                window.FFInsights.createInsights(content, 'recovery', data);
            }

            // 3. Sleep history list (at the very bottom)
            if (!data.history || !data.history.length) {
                var none = document.createElement('div');
                none.className = 'nutrition-empty';
                none.innerHTML = window.emptyStateHTML({
                    icon: 'fa-moon',
                    title: 'Linked to SparkyFitness - no sleep yet',
                    desc: 'Once your SparkyFitness sleep syncs, your nights will appear here with a sleep score and XP.',
                    hint: '8+ hours earns the most Recovery XP.',
                    secondary: true
                });
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
                var badgesWrap = document.createElement('div');
                badgesWrap.style.display = 'flex';
                badgesWrap.style.alignItems = 'center';
                badgesWrap.style.gap = '8px';
                if (night.status_label) {
                    var statusBadge = document.createElement('span');
                    statusBadge.className = night.status === 'perfect' ? 'perfect-badge' : (night.status === 'close' ? 'close-badge' : (night.status === 'partial' || night.status === 'light' ? 'partial-badge' : 'imperfect-badge'));
                    statusBadge.style.fontSize = '0.75rem';
                    statusBadge.textContent = night.status_label;
                    badgesWrap.appendChild(statusBadge);
                }
                if (night.xp) {
                    var xpBadge = document.createElement('span');
                    xpBadge.className = 'reward xp';
                    xpBadge.textContent = '+' + night.xp + ' XP';
                    badgesWrap.appendChild(xpBadge);
                }
                head.appendChild(badgesWrap);
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
        }
    });

    var recNode = document.getElementById('node-recovery');
    if (recNode) {
        recNode.addEventListener('click', function () { window.loadRecovery(); });
    }
})();
