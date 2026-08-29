/* Hydration detail panel controller (Phase 6, docs/19 #22).
 * Uses window.createModalityController() factory.
 */
(function () {
    'use strict';

    var WATER_ADD = '/api/v1/hydration/water/add';
    var WATER_REMOVE = '/api/v1/hydration/water/remove';
    var BOTTLES_URL = '/api/v1/hydration/bottles/';

    function getCsrfToken() {
        var m = document.querySelector('meta[name="csrf-token"]');
        if (m && m.content && m.content !== 'NOTPROVIDED' && m.content !== '') return m.content;
        var match = document.cookie.match(/(?:^|;\s*)(?:csrftoken|__Secure-csrftoken)=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function waterPost(url, data) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify(data)
        }).then(function (r) { return r.json(); });
    }

    function refreshHydration() { if (window.loadHydration) window.loadHydration(); }
    function toast(msg) { if (window.toast) window.toast(msg); }
    function haptic(ms) { if (window.haptic) window.haptic(ms); }

    window.logWater = function (oz) {
        return waterPost(WATER_ADD, { amount_oz: oz }).then(function (res) {
            toast((res && res.pushed_to_sparky ? 'Logged ' + oz + ' oz → Sparky' : 'Logged ' + oz + ' oz'));
            haptic(15); refreshHydration();
        });
    };
    window.removeWater = function (oz) {
        return waterPost(WATER_REMOVE, { amount_oz: oz }).then(function () {
            toast('Removed ' + oz + ' oz'); haptic(15); refreshHydration();
        });
    };
    window.saveWaterBottles = function (bottles) {
        return waterPost(BOTTLES_URL, { bottles: bottles }).then(function () {
            toast('Bottle sizes saved'); refreshHydration();
        });
    };

    function makeEl(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function buildWaterLogger(content, data) {
        var today = data.today || {};
        var water = today.water || 0;
        var goal = today.water_goal || 80;
        var bottles = (data.bottles || []).slice();
        var primary = data.primary_source || 'health_connect';
        var pct = goal ? Math.min(100, Math.max(0, Math.round(water / goal * 100))) : 0;

        var card = makeEl('div', 'nutrition-day-card');
        var head = makeEl('div', 'day-card-head');
        head.appendChild(makeEl('div', 'day-date', '💧 Quick Log Water'));
        head.appendChild(makeEl('span', 'partial-badge', '→ ' + primary));
        card.appendChild(head);

        var row = makeEl('div', 'macro-row');
        row.appendChild(makeEl('span', 'macro-label', 'Today'));
        var track = makeEl('div', 'bar');
        var fill = makeEl('div', 'bar-fill');
        fill.style.width = pct + '%';
        fill.style.backgroundColor = 'var(--primary-blue)';
        track.appendChild(fill);
        row.appendChild(track);
        row.appendChild(makeEl('span', 'macro-goal', Math.round(water) + ' / ' + Math.round(goal) + ' oz'));
        card.appendChild(row);

        var btns = makeEl('div');
        btns.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;margin:10px 0;';
        bottles.forEach(function (b) {
            var btn = makeEl('button', 'quick-log-btn', '+' + Math.round(b.capacity_oz) + ' oz');
            btn.onclick = function () { window.logWater(b.capacity_oz); };
            btns.appendChild(btn);
        });
        card.appendChild(btns);

        var ctrl = makeEl('div');
        ctrl.style.cssText = 'display:flex;gap:8px;align-items:center;flex-wrap:wrap;';
        var input = document.createElement('input');
        input.type = 'number'; input.min = '1'; input.value = '8';
        input.style.cssText = 'width:72px;padding:8px;border-radius:12px;border:1px solid var(--border-color);background:var(--bg-card,#1e293b);color:var(--text-main,#fff);font-weight:700;';
        ctrl.appendChild(input);
        var addBtn = makeEl('button', 'btn-flamingo btn-sm', 'Add');
        addBtn.onclick = function () { var v = parseFloat(input.value); if (v > 0) window.logWater(v); };
        ctrl.appendChild(addBtn);
        var rmBtn = makeEl('button', 'btn-danger btn-sm', '− Remove');
        rmBtn.onclick = function () { var v = parseFloat(input.value); if (v > 0) window.removeWater(v); };
        ctrl.appendChild(rmBtn);
        card.appendChild(ctrl);

        var manageBtn = makeEl('button', 'btn-sm', '⚙ Manage bottles');
        manageBtn.style.cssText = 'margin-top:10px;color:var(--text-muted);text-decoration:underline;background:none;border:none;cursor:pointer;';
        var manageBox = makeEl('div');
        manageBox.style.display = 'none';
        manageBox.style.marginTop = '8px';
        function renderEditor() {
            manageBox.innerHTML = '';
            bottles.forEach(function (b) {
                var rowE = makeEl('div');
                rowE.style.cssText = 'display:flex;gap:6px;align-items:center;margin:4px 0;';
                var n = document.createElement('input');
                n.value = b.name || 'Bottle';
                n.style.cssText = 'flex:1;min-width:0;padding:6px;border-radius:8px;border:1px solid var(--border-color);background:var(--bg-card,#1e293b);color:var(--text-main,#fff);';
                var c = document.createElement('input');
                c.type = 'number'; c.value = b.capacity_oz;
                c.style.cssText = 'width:70px;padding:6px;border-radius:8px;border:1px solid var(--border-color);background:var(--bg-card,#1e293b);color:var(--text-main,#fff);';
                var del = makeEl('button', 'btn-danger btn-sm', '✕');
                del.onclick = function () { bottles = bottles.filter(function (x) { return x !== b; }); renderEditor(); };
                rowE.appendChild(n); rowE.appendChild(c); rowE.appendChild(del);
                b._nameEl = n; b._capEl = c;
                manageBox.appendChild(rowE);
            });
            var addRow = makeEl('button', 'btn-sm btn-teal', '+ Add bottle');
            addRow.onclick = function () { bottles.push({ name: 'Bottle', capacity_oz: 16 }); renderEditor(); };
            manageBox.appendChild(addRow);
            var save = makeEl('button', 'btn-flamingo btn-sm', 'Save bottles');
            save.style.marginLeft = '6px';
            save.onclick = function () {
                var out = bottles.map(function (b) {
                    return { id: b.id, name: b._nameEl.value || 'Bottle', capacity_oz: parseFloat(b._capEl.value) || 0 };
                }).filter(function (b) { return b.capacity_oz > 0; });
                window.saveWaterBottles(out);
            };
            manageBox.appendChild(save);
        }
        manageBtn.onclick = function () {
            manageBox.style.display = manageBox.style.display === 'none' ? 'block' : 'none';
            renderEditor();
        };
        card.appendChild(manageBtn);
        card.appendChild(manageBox);

        content.appendChild(card);
    }

    function formatWater(value, goal) {
        return Math.round(value || 0) + (goal !== undefined ? '/' + Math.round(goal || 0) + ' oz' : '');
    }

    function getHydrationBadge(day) {
        if (day.perfect) {
            return { cls: 'perfect-badge', text: 'ON TARGET' };
        }
        if (day.status === 'close' || (day.water_pct >= 80) || (day.xp >= 20)) {
            return { cls: 'close-badge', text: 'CLOSE' };
        }
        if (day.status === 'partial' || (day.water_pct >= 60) || (day.xp >= 10)) {
            return { cls: 'partial-badge', text: 'PARTIAL' };
        }
        return { cls: 'imperfect-badge', text: 'Needs work' };
    }

    function buildHydrationCard(day, title) {
        var card = document.createElement('div');
        card.className = 'nutrition-day-card';

        var head = document.createElement('div');
        head.className = 'day-card-head';
        var date = document.createElement('div');
        date.className = 'day-date';
        date.textContent = title;
        head.appendChild(date);
        var badgeInfo = getHydrationBadge(day);
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

        var badgeInfo = getHydrationBadge(day);
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

    window.createModalityController({
        name: 'hydration',
        title: 'Hydration',
        icon: 'fa-glass-water',
        apiUrl: '/api/v1/hydration/',
        guidanceText: 'Hit your water goal for max rewards (+30 XP, +10 tokens). 80%+ earns +20 XP & +5 tokens, 60%+ earns +10 XP!',
        emptyState: {
            icon: 'fa-glass-water',
            title: 'No hydration data yet',
            desc: 'Link SparkyFitness to start tracking your water intake and hit your daily goal.',
            hint: 'Every glass you log moves your Hydration skill tree.',
            ctaText: 'Link SparkyFitness',
            ctaHref: '/profile/'
        },
        renderCustomContent: function (content, data) {
            // 0. Quick water logger (custom bottles + add/remove)
            buildWaterLogger(content, data);

            // 1. Today's Summary Card
            if (data.today) {
                content.appendChild(buildHydrationCard(data.today, 'Today, ' + data.today.date));
            }

            // 2. Trends & Insights
            if (window.FFInsights) {
                window.FFInsights.createInsights(content, 'hydration', data);
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
                        window.showHydrationDayDetailModal(day);
                    });
                    var left = document.createElement('span');
                    left.className = 'hist-macros';
                    left.textContent = day.date + '  ' + formatWater(day.water, day.water_goal);
                    li.appendChild(left);
                    var right = document.createElement('span');
                    right.className = 'hist-reward';
                    var badgeInfo = getHydrationBadge(day);
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

    var hydNode = document.getElementById('node-hydration');
    if (hydNode) {
        hydNode.addEventListener('click', function () {
            window.loadHydration();
        });
    }
})();
