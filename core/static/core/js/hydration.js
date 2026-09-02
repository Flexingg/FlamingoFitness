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
        if (window.FlamingoNative && typeof window.FlamingoNative.writeWater === 'function') {
            try {
                window.FlamingoNative.writeWater(oz);
            } catch (e) {
                console.warn('Native water write failed:', e);
            }
        }
        return waterPost(WATER_ADD, { amount_oz: oz }).then(function (res) {
            var dest = (res && res.pushed_to_sparky) ? 'Sparky' : (window.FlamingoNative ? 'Health Connect' : 'Flamingo');
            toast('💧 Logged ' + oz + ' oz → ' + dest);
            haptic(20);
            refreshHydration();
        });
    };

    window.removeWater = function (oz) {
        return waterPost(WATER_REMOVE, { amount_oz: oz }).then(function () {
            toast('Removed ' + oz + ' oz');
            haptic(15);
            refreshHydration();
        });
    };

    window.saveWaterBottles = function (bottles) {
        return waterPost(BOTTLES_URL, { bottles: bottles }).then(function () {
            toast('Custom bottle sizes saved');
            refreshHydration();
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
        var water = Math.round(today.water || 0);
        var goal = Math.round(today.water_goal || 80);
        var bottles = (data.bottles || []).slice();
        var primary = data.primary_source || 'health_connect';
        var pct = goal ? Math.min(100, Math.max(0, Math.round(water / goal * 100))) : 0;
        var srcDisplay = primary === 'sparkyfitness' ? 'SparkyFitness' : (primary === 'healthkit' ? 'Apple Health' : 'Health Connect');

        var card = makeEl('div', 'hydration-hero-card');

        // Top Row: Title & Source Badge
        var top = makeEl('div', 'hydration-hero-top');
        var titleWrap = makeEl('div', 'hydration-hero-title');
        titleWrap.innerHTML = '<i class="fa-solid fa-droplet" style="color:#00f0ff;"></i> Quick Log Water';
        top.appendChild(titleWrap);

        var badgeWrap = makeEl('span', 'hydration-source-badge');
        badgeWrap.innerHTML = '<i class="fa-solid fa-bolt"></i> ' + srcDisplay;
        top.appendChild(badgeWrap);
        card.appendChild(top);

        // Metrics Row: Current oz / Goal oz and Pct
        var metricsRow = makeEl('div', 'hydration-hero-metrics');
        var valEl = makeEl('span', 'hydration-hero-val', water + ' oz');
        metricsRow.appendChild(valEl);
        var goalEl = makeEl('span', 'hydration-hero-goal', '/ ' + goal + ' oz goal');
        metricsRow.appendChild(goalEl);
        var pctEl = makeEl('span', 'hydration-hero-pct', pct + '%');
        metricsRow.appendChild(pctEl);
        card.appendChild(metricsRow);

        // Glowing Progress Track
        var track = makeEl('div', 'hydration-track');
        var fill = makeEl('div', 'hydration-fill');
        fill.style.width = pct + '%';
        track.appendChild(fill);
        card.appendChild(track);

        // Status & Milestone Reward Row
        var milestoneRow = makeEl('div', 'hydration-milestones-row');
        var badgeInfo = getHydrationBadge(today);
        var statusBadge = makeEl('span', badgeInfo.cls, badgeInfo.text);
        milestoneRow.appendChild(statusBadge);

        var rewardText = makeEl('span');
        rewardText.style.cssText = 'color:#7dd3fc;display:flex;align-items:center;gap:6px;';
        if (pct >= 100) {
            rewardText.innerHTML = '<i class="fa-solid fa-trophy" style="color:#fbbf24;"></i> +30 XP & +10 tokens earned!';
        } else if (pct >= 80) {
            rewardText.innerHTML = '<i class="fa-solid fa-star" style="color:#38bdf8;"></i> +20 XP earned • ' + (goal - water) + ' oz to max!';
        } else {
            rewardText.innerHTML = '<i class="fa-solid fa-award" style="color:#94a3b8;"></i> ' + (goal - water) + ' oz left to reach goal';
        }
        milestoneRow.appendChild(rewardText);
        card.appendChild(milestoneRow);

        // Preset Water Cards (Glass, Bottle, Shaker, Flask)
        var presetsGrid = makeEl('div', 'hydration-preset-grid');
        var defaultPresets = [
            { oz: 8, label: 'Glass', icon: '🥛' },
            { oz: 16, label: 'Bottle', icon: '🥤' },
            { oz: 24, label: 'Shaker', icon: '🍶' },
            { oz: 32, label: 'Flask', icon: '🧊' }
        ];

        defaultPresets.forEach(function (p) {
            var btn = makeEl('button', 'water-bottle-btn');
            btn.type = 'button';
            btn.innerHTML = '<span class="water-bottle-icon">' + p.icon + '</span>' +
                '<span class="water-bottle-amount">+' + p.oz + ' oz</span>' +
                '<span class="water-bottle-label">' + p.label + '</span>';
            btn.onclick = function () { window.logWater(p.oz); };
            presetsGrid.appendChild(btn);
        });
        card.appendChild(presetsGrid);

        // Custom User Bottles (if configured)
        if (bottles.length > 0) {
            var customBottlesSection = makeEl('div');
            customBottlesSection.style.cssText = 'margin-bottom:12px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;';
            var customLabel = makeEl('span', '', 'My Bottles:');
            customLabel.style.cssText = 'font-size:0.75rem;font-weight:800;color:var(--text-muted);text-transform:uppercase;';
            customBottlesSection.appendChild(customLabel);

            bottles.forEach(function (b) {
                var btn = makeEl('button', 'quick-log-btn');
                btn.type = 'button';
                btn.style.cssText = 'display:inline-flex;align-items:center;gap:4px;border-color:rgba(56,189,248,0.4);';
                btn.innerHTML = '<i class="fa-solid fa-bottle-water" style="color:#38bdf8;font-size:0.8rem;"></i> +' + Math.round(b.capacity_oz) + ' oz <span style="font-size:0.75rem;opacity:0.75;">(' + (b.name || 'Bottle') + ')</span>';
                btn.onclick = function () { window.logWater(b.capacity_oz); };
                customBottlesSection.appendChild(btn);
            });
            card.appendChild(customBottlesSection);
        }

        // Stepper & Custom Input Row
        var customRow = makeEl('div', 'hydration-custom-row');

        var inputWrap = makeEl('div', 'water-input-wrap');
        var input = document.createElement('input');
        input.type = 'number';
        input.min = '1';
        input.max = '200';
        input.value = '8';
        input.className = 'water-number-input';
        inputWrap.appendChild(input);
        inputWrap.appendChild(makeEl('span', 'water-unit-tag', 'oz'));
        customRow.appendChild(inputWrap);

        // Stepper buttons (-8, -4, +4, +8)
        var stepperGroup = makeEl('div', 'water-stepper-group');
        [-4, 4].forEach(function (delta) {
            var sBtn = makeEl('button', 'water-stepper-btn', (delta > 0 ? '+' : '') + delta);
            sBtn.type = 'button';
            sBtn.onclick = function () {
                var curr = parseFloat(input.value) || 8;
                var next = Math.max(1, Math.min(200, curr + delta));
                input.value = next;
            };
            stepperGroup.appendChild(sBtn);
        });
        customRow.appendChild(stepperGroup);

        var logBtn = makeEl('button', 'water-log-cta');
        logBtn.type = 'button';
        logBtn.innerHTML = '<i class="fa-solid fa-plus"></i> Add Water';
        logBtn.onclick = function () {
            var v = parseFloat(input.value);
            if (v > 0) window.logWater(v);
        };
        customRow.appendChild(logBtn);

        var removeBtn = makeEl('button', 'water-remove-cta', '− Remove');
        removeBtn.type = 'button';
        removeBtn.onclick = function () {
            var v = parseFloat(input.value);
            if (v > 0) window.removeWater(v);
        };
        customRow.appendChild(removeBtn);
        card.appendChild(customRow);

        // Bottle Manager Accordion
        var manageBtn = makeEl('button', 'water-manage-bottles-btn');
        manageBtn.type = 'button';
        manageBtn.innerHTML = '<i class="fa-solid fa-sliders"></i> Customize Bottle Sizes & Presets';

        var manageBox = makeEl('div', 'bottle-editor-panel');
        manageBox.style.display = 'none';

        function renderEditor() {
            manageBox.innerHTML = '';

            var header = makeEl('div');
            header.style.cssText = 'font-weight:800;font-size:0.85rem;color:#e2e8f0;margin-bottom:8px;';
            header.innerHTML = '<i class="fa-solid fa-flask"></i> Custom Water Bottles';
            manageBox.appendChild(header);

            // Quick Preset Templates
            var templatesWrap = makeEl('div', 'bottle-template-chips');
            var templates = [
                { name: 'Can', oz: 12 },
                { name: 'Tumbler', oz: 20 },
                { name: 'Shaker', oz: 24 },
                { name: 'Growler', oz: 32 },
                { name: 'Stanley', oz: 40 }
            ];
            templates.forEach(function (t) {
                var chip = makeEl('button', 'bottle-template-chip', '+ ' + t.oz + ' oz ' + t.name);
                chip.type = 'button';
                chip.onclick = function () {
                    bottles.push({ name: t.name, capacity_oz: t.oz });
                    renderEditor();
                };
                templatesWrap.appendChild(chip);
            });
            manageBox.appendChild(templatesWrap);

            // Bottle Row Editor
            bottles.forEach(function (b) {
                var rowE = makeEl('div', 'bottle-editor-row');
                var n = document.createElement('input');
                n.value = b.name || 'Bottle';
                n.placeholder = 'Bottle Name';
                n.style.cssText = 'flex:1;min-width:0;padding:8px;border-radius:10px;border:1px solid rgba(255,255,255,0.15);background:#1e293b;color:#fff;font-size:0.85rem;';

                var c = document.createElement('input');
                c.type = 'number';
                c.value = b.capacity_oz;
                c.placeholder = 'oz';
                c.style.cssText = 'width:70px;padding:8px;border-radius:10px;border:1px solid rgba(255,255,255,0.15);background:#1e293b;color:#38bdf8;font-weight:800;font-size:0.85rem;';

                var del = makeEl('button', 'btn-danger btn-sm', '✕');
                del.type = 'button';
                del.style.cssText = 'padding:6px 10px;border-radius:8px;';
                del.onclick = function () {
                    bottles = bottles.filter(function (x) { return x !== b; });
                    renderEditor();
                };

                rowE.appendChild(n);
                rowE.appendChild(c);
                rowE.appendChild(del);
                b._nameEl = n;
                b._capEl = c;
                manageBox.appendChild(rowE);
            });

            var actionRow = makeEl('div');
            actionRow.style.cssText = 'display:flex;gap:8px;margin-top:10px;';

            var addRow = makeEl('button', 'btn-sm btn-teal', '+ Add New Bottle');
            addRow.type = 'button';
            addRow.onclick = function () {
                bottles.push({ name: 'My Bottle', capacity_oz: 24 });
                renderEditor();
            };
            actionRow.appendChild(addRow);

            var save = makeEl('button', 'btn-flamingo btn-sm', 'Save All Bottles');
            save.type = 'button';
            save.onclick = function () {
                var out = bottles.map(function (b) {
                    return {
                        id: b.id,
                        name: (b._nameEl ? b._nameEl.value : b.name) || 'Bottle',
                        capacity_oz: parseFloat(b._capEl ? b._capEl.value : b.capacity_oz) || 0
                    };
                }).filter(function (b) { return b.capacity_oz > 0; });
                window.saveWaterBottles(out);
            };
            actionRow.appendChild(save);
            manageBox.appendChild(actionRow);
        }

        manageBtn.onclick = function () {
            var isHidden = manageBox.style.display === 'none';
            manageBox.style.display = isHidden ? 'block' : 'none';
            if (isHidden) renderEditor();
        };

        card.appendChild(manageBtn);
        card.appendChild(manageBox);

        // Today's Intake Entries Timeline (if logged today)
        if (today.water_intake_entries && today.water_intake_entries.length) {
            var timeline = makeEl('div', 'today-intake-timeline');
            var timeHead = makeEl('div', 'today-intake-header');
            timeHead.innerHTML = '<span><i class="fa-solid fa-clock-rotate-left"></i> Today\'s Intake Log</span><span>' + today.water_intake_entries.length + ' entries</span>';
            timeline.appendChild(timeHead);

            today.water_intake_entries.forEach(function (e) {
                var item = makeEl('div', 'today-intake-item');
                item.innerHTML = '<span style="color:#cbd5e1;"><i class="fa-regular fa-clock" style="margin-right:6px;color:#64748b;"></i> ' + (e.time || 'Today') + '</span>' +
                    '<span style="color:#38bdf8;font-weight:800;">+' + Math.round(e.amount || 0) + ' oz</span>';
                timeline.appendChild(item);
            });
            card.appendChild(timeline);
        }

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
            // 0. Hero Quick water logger & Today's Summary
            buildWaterLogger(content, data);

            // 1. Trends & Insights
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
