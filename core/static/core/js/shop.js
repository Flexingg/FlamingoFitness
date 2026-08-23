/* Gacha Shop panel controller (Phase 9, docs/15 §7).
 * Opens from the "Shop" bottom-nav tab.
 * Consumes GET /api/v1/shop/state, POST /api/v1/shop/open, POST /api/v1/shop/consume.
 * Payload keys mirror core/views.py shop_state / shop_open / shop_consume.
 */
(function () {
    'use strict';

    var STATE_URL = '/api/v1/shop/state';
    var OPEN_URL = '/api/v1/shop/open';
    var CONSUME_URL = '/api/v1/shop/consume';
    var SCRAP_RECYCLE_URL = '/api/v1/scrap/recycle';
    var SCRAP_BUY_URL = '/api/v1/scrap/shop/buy';

    var RARITY_COLOR = {
        common: '#94a3b8',
        rare: '#38bdf8',
        epic: '#a78bfa',
        legendary: '#f59e0b'
    };

    function esc(s) { return window.escHtml(s); }

    function getCsrfToken() {
        var m = document.querySelector('meta[name="csrf-token"]');
        if (m && m.content && m.content !== 'NOTPROVIDED' && m.content !== '') return m.content;
        var match = document.cookie.match(/(?:^|;\s*)(?:csrftoken|__Secure-csrftoken)=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function haptic(ms) { return window.haptic(ms); }

    function confettiBurst() { return window.confettiBurst(); }

    window.backToShopPlan = function () {
        if (window.goBack) { window.goBack(); return; }
        var view = document.getElementById('shop-view');
        if (view) view.classList.add('hidden');
        window.ensureSinglePanelVisible('skill-tree');
    };

    function money(n) {
        return String(Number(n) || 0).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    window.loadShop = function () {
        if (window.closeModal) window.closeModal();

        var runLoad = function () {
            var view = document.getElementById('shop-view');
            var content = document.getElementById('shop-content');
            if (!view) { window.ffWarn('[shop] shop-view not found'); return; }
            window.ensureSinglePanelVisible('shop-view');
            if (window.setActiveNav) window.setActiveNav('nav-shop');
            if (content) content.innerHTML = '<p class="text-slate-400">Opening the shop…</p>';
            fetch(STATE_URL, { credentials: 'same-origin' })
                .then(function (res) {
                    if (res.status === 401 || res.status === 403) throw new Error('not-authenticated');
                    return res.ok ? res.json() : Promise.reject(res.status);
                })
                .then(function (data) { window.renderShop(data); })
                .catch(function (err) {
                    if (content) content.innerHTML = '<p class="text-slate-400">Could not load the shop (error ' + esc(err) + ').</p>';
                });
        };

        if (typeof window.ensurePanelLoaded === 'function') {
            return window.ensurePanelLoaded('shop-view').then(runLoad);
        } else {
            return runLoad();
        }
    };
    var BULK_TIERS = [1, 3, 5, 10];
    var BULK_DISCOUNT = { 1: 0, 3: 10, 5: 15, 10: 20 };

    function bulkCost(price, qty) {
        var pct = BULK_DISCOUNT[qty] || 0;
        return { cost: Math.round(price * (1 - pct / 100) * qty), pct: pct };
    }

    var SHOP_TABS = [
        { key: 'all', label: 'All', icon: 'fa-shop' },
        { key: 'strength', label: 'Strength', icon: 'fa-dumbbell' },
        { key: 'cardio', label: 'Cardio', icon: 'fa-heart-pulse' },
        { key: 'nutrition', label: 'Nutrition', icon: 'fa-utensils' },
        { key: 'hydration', label: 'Hydration', icon: 'fa-droplet' },
        { key: 'sleep', label: 'Sleep', icon: 'fa-moon' }
    ];
    var DOMAIN_META = {
        strength: { label: 'Strength', icon: 'fa-dumbbell', color: '#f87171' },
        cardio: { label: 'Cardio', icon: 'fa-heart-pulse', color: '#34d399' },
        nutrition: { label: 'Nutrition', icon: 'fa-utensils', color: '#c084fc' },
        hydration: { label: 'Hydration', icon: 'fa-droplet', color: '#38bdf8' },
        sleep: { label: 'Sleep', icon: 'fa-moon', color: '#a5b4fc' }
    };
    var currentTab = 'all';
    var lastShopData = null;

    function renderPackCard(p) {
        var opts = '';
        BULK_TIERS.forEach(function (q) {
            var bc = bulkCost(p.price_tokens, q);
            opts += '<option value="' + q + '" data-cost="' + bc.cost + '" data-pct="' + bc.pct + '">' +
                q + ' &times; ' + money(bc.cost) + (bc.pct ? ' (-' + bc.pct + '%)' : '') + '</option>';
        });
        var domainTag = '';
        if (p.domains && p.domains.length) {
            var m = DOMAIN_META[p.domains[0]] || {};
            var c = m.color || '#94a3b8';
            domainTag = '<span class="text-[10px] uppercase tracking-wide font-bold px-2 py-0.5 rounded-full" style="color:' + c + ';border:1px solid ' + c + '">' + (m.label || p.domains[0]) + '</span>';
        } else {
            domainTag = '<span class="text-[10px] uppercase tracking-wide font-bold px-2 py-0.5 rounded-full text-slate-400 border border-slate-600">Crate</span>';
        }
        var rarityTag = '<span class="text-[10px] uppercase tracking-wide font-bold px-2 py-0.5 rounded-full text-slate-400 border border-slate-600">min ' + esc(p.guaranteed_min_rarity) + '</span>';
        return '<div class="shop-card border border-slate-600 rounded-2xl p-3.5 shadow-lg">' +
            '<div class="flex items-start gap-3">' +
            '<div class="w-12 h-12 rounded-xl bg-slate-700 flex items-center justify-center text-xl shrink-0"><i class="fa-solid ' + esc(p.icon || 'fa-box-open') + ' text-yellow-400"></i></div>' +
            '<div class="flex-1 min-w-0">' +
            '<h4 class="font-black text-white truncate">' + esc(p.name) + '</h4>' +
            '<p class="text-xs text-slate-400 font-semibold truncate">' + esc(p.draws) + ' draw' + (p.draws > 1 ? 's' : '') + ' &middot; ' + money(p.price_tokens) + ' each</p>' +
            '<div class="flex gap-1.5 mt-1 flex-wrap">' + domainTag + rarityTag + '</div>' +
            '</div>' +
            '</div>' +
            '<p class="text-xs text-slate-500 mt-2 leading-relaxed">' + esc(p.description) + '</p>' +
            '<div class="mt-3 flex items-center gap-2">' +
            '<select class="flex-1 min-w-0 bg-slate-900 border border-slate-600 rounded-xl px-2 py-2 text-sm text-white font-semibold" data-slug="' + esc(p.slug) + '">' + opts + '</select>' +
            '<button class="bg-amber-500 text-slate-900 font-black px-3.5 py-2 rounded-xl border-b-4 border-amber-700 active:scale-95 transition-all whitespace-nowrap" data-buy="' + esc(p.slug) + '" data-cost="">Buy</button>' +
            '</div>' +
            '</div>';
    }

    function renderConsumableRow(i) {
        return '<div class="shop-card border border-slate-600 rounded-2xl p-3.5 flex items-center gap-3 shadow-lg">' +
            '<div class="w-11 h-11 rounded-xl bg-slate-700 flex items-center justify-center text-xl shrink-0"><i class="fa-solid ' + esc(i.icon || 'fa-flask') + ' text-lime-400"></i></div>' +
            '<div class="flex-1 min-w-0"><h4 class="font-black text-white truncate">' + esc(i.name) + '</h4>' +
            '<p class="text-xs text-slate-400 font-semibold">' + esc(i.effect_type.replace(/_/g, ' ')) + ' &middot; x' + esc(i.quantity) + ' owned</p></div>' +
            '<button class="bg-lime-500 text-slate-900 font-black px-3 py-2 rounded-xl border-b-4 border-lime-700 active:scale-95 transition-all" data-consume="' + esc(i.id) + '">Use</button>' +
            '</div>';
    }

    window.renderShop = function (data) {
        lastShopData = data;
        var content = document.getElementById('shop-content');
        if (!content) return;
        if (!SHOP_TABS.some(function (t) { return t.key === currentTab; })) currentTab = 'all';

        var packs = (data.packs || []).filter(function (p) {
            if (currentTab === 'all') return true;
            return (p.domains || []).indexOf(currentTab) !== -1;
        });

        var html = '<p class="text-xs text-slate-400 font-semibold mb-3">Pull themed gear packs and generic crates. Buying 3+ at once knocks 10&ndash;20% off.</p>';

        html += '<div class="flex gap-2 overflow-x-auto pb-1 mb-4 px-0.5" id="shop-tabs" role="tablist" aria-label="Shop categories">';
        SHOP_TABS.forEach(function (t) {
            var active = t.key === currentTab
                ? ' bg-amber-500 text-slate-900 border-amber-600 shadow'
                : ' bg-slate-800 text-slate-300 border-slate-600';
            html += '<button type="button" class="shop-tab whitespace-nowrap px-3.5 py-2 rounded-xl border font-bold text-sm transition-all active:scale-95' + active + '" role="tab" data-tab="' + t.key + '"' +
                (t.key === currentTab ? ' aria-selected="true"' : '') + '>' +
                '<i class="fa-solid ' + t.icon + ' mr-1.5"></i>' + t.label + '</button>';
        });
        html += '</div>';

        var meta = DOMAIN_META[currentTab] || {};
        var all = currentTab === 'all';
        var heading = all ? 'All Packs' : ((meta.label || currentTab) + ' Packs');
        var headIcon = all ? 'fa-box-open' : (meta.icon || 'fa-box-open');
        var headColor = all ? '#facc15' : (meta.color || '#facc15');
        html += '<h3 class="text-white font-black mb-2 flex items-center gap-1.5"><i class="fa-solid ' + headIcon + '" style="color:' + headColor + '"></i>' + heading +
            '<span class="text-xs font-semibold text-slate-400">(' + packs.length + ')</span></h3>';

        if (packs.length) {
            html += '<div class="grid grid-cols-1 sm:grid-cols-2 gap-3" id="shop-pack-grid">';
            packs.forEach(function (p) { html += renderPackCard(p); });
            html += '</div>';
        } else {
            html += window.emptyStateHTML({
                icon: 'fa-box-open',
                title: 'No packs in this category yet',
                desc: 'Open packs to pull gear that boosts your damage and stats.',
                hint: 'Pack line-ups rotate regularly - check back soon.',
                secondary: true
            });
        }

        var owned = data.owned || {};
        var consumables = (owned['consumable'] || []);
        if (consumables.length) {
            html += '<h3 class="text-white font-black mt-6 mb-2 flex items-center gap-1.5"><i class="fa-solid fa-flask text-lime-400"></i>Consumables' +
                '<span class="text-xs font-semibold text-slate-400">(' + consumables.length + ')</span></h3>';
            html += '<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">';
            consumables.forEach(function (i) { html += renderConsumableRow(i); });
            html += '</div>';
        }

        // ---- Recycle: turn unneeded gear into scraps (docs/16) ----
        var recyclable = data.recyclable || [];
        if (recyclable.length) {
            html += '<h3 class="text-white font-black mt-6 mb-2 flex items-center gap-1.5"><i class="fa-solid fa-recycle text-slate-300"></i>Recycle for Scraps' +
                '<span class="text-xs font-semibold text-slate-400">(' + recyclable.length + ')</span></h3>';
            html += '<p class="text-xs text-slate-500 font-semibold mb-3">Turn unequipped gear into the Scrap Shop\'s currency. Scrap value scales with rarity (Common 5 &middot; Rare 15 &middot; Epic 40 &middot; Legendary 100).</p>';
            html += '<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">';
            recyclable.forEach(function (it) { html += renderRecycleRow(it); });
            html += '</div>';
        }

        // ---- Scrap Shop: rotating, weekday-gated deals (docs/16) ----
        var scrapShop = data.scrap_shop || {};
        var offering = scrapShop.offering || [];
        if (offering.length) {
            html += '<h3 class="text-white font-black mt-6 mb-2 flex items-center gap-1.5"><i class="fa-solid fa-wrench text-purple-400"></i>Scrap Shop' +
                '<span class="text-xs font-semibold text-slate-400">' + (scrapShop.weekday || '').toUpperCase() + ' special</span></h3>';
            html += '<p class="text-xs text-slate-500 font-semibold mb-3">Spend scraps on rotating deals. The offering changes by day of the week - check back tomorrow for new drops.</p>';
            html += '<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">';
            offering.forEach(function (it) { html += renderScrapShopRow(it); });
            html += '</div>';
        }

        content.innerHTML = html;
        bindShopEvents(content);
    };

    function bindShopEvents(content) {
        content.querySelectorAll('.shop-tab').forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (window.closeModal) window.closeModal();
                currentTab = btn.getAttribute('data-tab');
                if (lastShopData) window.renderShop(lastShopData);
            });
        });

        function updateBuyLabel(sel) {
            var opt = sel.options[sel.selectedIndex];
            var card = sel.closest('.shop-card');
            var btn = card ? card.querySelector('button[data-buy="' + sel.getAttribute('data-slug') + '"]') : null;
            if (!btn) return;
            var cost = opt.getAttribute('data-cost');
            var pct = opt.getAttribute('data-pct');
            btn.setAttribute('data-cost', cost);
            btn.innerHTML = money(cost) + ' <i class="fa-solid fa-coins"></i>' +
                (Number(pct) > 0 ? ' (-' + pct + '%)' : '');
        }

        content.querySelectorAll('select[data-slug]').forEach(function (sel) {
            updateBuyLabel(sel);
            sel.addEventListener('change', function () { updateBuyLabel(sel); });
        });
        content.querySelectorAll('button[data-buy][data-cost]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var sel = content.querySelector('select[data-slug="' + btn.getAttribute('data-buy') + '"]');
                var qty = sel ? parseInt(sel.value, 10) : 1;
                openPack(btn.getAttribute('data-buy'), qty);
            });
        });
        content.querySelectorAll('button[data-consume]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                consumeItem(btn.getAttribute('data-consume'));
            });
        });
        content.querySelectorAll('button[data-recycle]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                recycleItem(btn.getAttribute('data-recycle'));
            });
        });
        content.querySelectorAll('button[data-scrap-buy]').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                buyScrapItem(btn.getAttribute('data-scrap-buy'));
            });
        });
    }


    function openPack(slug, quantity) {
        haptic(30);
        if (window.playGachaRoll) window.playGachaRoll();
        fetch(OPEN_URL, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ pack_slug: slug, quantity: quantity || 1 })
        })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
            .then(function (res) {
                if (!res.body.ok) {
                    window.showToast(res.body.error || 'Could not open pack.');
                    return;
                }
                renderManifest(res.body);
                if (window.refreshDashboardState) window.refreshDashboardState();
                window.loadShop();
            })
            .catch(function () { window.showToast('Network error while opening the pack.'); });
    }

    function renderManifest(payload) {
        haptic([40, 30, 40, 30, 60]);
        var manifest = (payload && payload.manifest) || [];
        var anyEpic = manifest.some(function (m) { return m.rarity === 'epic' || m.rarity === 'legendary'; });
        if (anyEpic) {
            confettiBurst();
            if (window.playBadgeFanfare) window.playBadgeFanfare();
        } else {
            if (window.playXpChime) window.playXpChime();
        }
        var modal = document.getElementById('shop-manifest');
        if (!modal) return;
        var html = manifest.map(function (m) {
            return '<div class="flex items-center gap-3 p-2 rounded-xl" style="border:1px solid ' + (RARITY_COLOR[m.rarity] || '#334155') + '">' +
                '<div class="w-10 h-10 rounded-xl bg-slate-700 flex items-center justify-center"><i class="fa-solid ' + esc(m.icon || 'fa-shield') + '"></i></div>' +
                '<div class="flex-1"><div class="font-black" style="color:' + (RARITY_COLOR[m.rarity] || '#f8fafc') + '">' + esc(m.name) + '</div>' +
                '<div class="text-xs text-slate-400 font-semibold">' + esc(m.rarity).toUpperCase() + (m.is_new ? ' &middot; NEW' : ' &middot; x' + m.quantity) + '</div></div>' +
                '</div>';
        }).join('');
        var qty = payload && payload.quantity;
        var cost = payload && payload.cost;
        var pct = payload && payload.discount_pct;
        var subtitle = qty ? ('<p class="text-center text-xs text-slate-400 font-semibold mb-3">' + qty + ' pull' +
            (qty > 1 ? 's' : '') + ' &middot; ' + money(cost) + ' tokens' +
            (Number(pct) > 0 ? ' (' + pct + '% off)' : '') + '</p>') : '';
        modal.innerHTML = '<div class="modal-overlay show-modal" id="shop-manifest-overlay" role="dialog" aria-modal="true">' +
            '<div class="modal-content stat-modal-content rounded-[2rem] p-6 border border-slate-600 shadow-2xl w-[90%] max-w-sm m-auto">' +
            '<h2 class="text-2xl font-black text-white text-center mb-1">Pull Results</h2>' +
            subtitle +
            '<div class="flex flex-col gap-2">' + html + '</div>' +
            '<button class="w-full bg-flamingo text-white font-bold py-3.5 rounded-2xl border-b-4 border-flamingo-dark hover:brightness-110 active:border-b-0 active:translate-y-1 transition-all shadow-lg mt-4" type="button">Got it!</button>' +
            '</div></div>';
        modal.querySelector('button').addEventListener('click', function () {
            modal.innerHTML = '';
        });
    }

    function consumeItem(gearId) {
        haptic(30);
        fetch(CONSUME_URL, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ gear_id: gearId })
        })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
            .then(function (res) {
                if (!res.body.ok) { window.showToast(res.body.error || 'Could not use the item.'); return; }
                if (window.refreshDashboardState) window.refreshDashboardState();
                window.loadShop();
            })
            .catch(function () { window.showToast('Network error.'); });
    }

    function renderRecycleRow(it) {
        return '<div class="shop-card border border-slate-600 rounded-2xl p-3.5 flex items-center gap-3 shadow-lg">' +
            '<div class="w-11 h-11 rounded-xl bg-slate-700 flex items-center justify-center text-lg shrink-0"><i class="fa-solid ' + esc(it.icon || 'fa-shield') + ' text-slate-300"></i></div>' +
            '<div class="flex-1 min-w-0"><h4 class="font-black text-white truncate">' + esc(it.name) + '</h4>' +
            '<p class="text-xs text-slate-400 font-semibold">' + esc(it.rarity).toUpperCase() + ' &middot; x' + esc(it.quantity) + ' &middot; +' + money(it.total_scraps) + ' scraps</p></div>' +
            '<button class="bg-slate-500 text-white font-black px-3 py-2 rounded-xl border-b-4 border-slate-700 active:scale-95 transition-all" data-recycle="' + esc(it.id) + '">Recycle</button>' +
            '</div>';
    }

    function rewardLabel(it) {
        if (it.reward_type === 'tokens') return '+ ' + money(it.reward_value) + ' tokens';
        if (it.reward_type === 'stamina') return '+ ' + it.reward_value + ' stamina';
        if (it.reward_type === 'pack') return '1 &times; ' + esc(it.pack || 'crate');
        return esc(it.reward_type || '');
    }

    function renderScrapShopRow(it) {
        return '<div class="shop-card border rounded-2xl p-3.5 flex items-center gap-3 shadow-lg" style="border-color:#7c3aed">' +
            '<div class="w-11 h-11 rounded-xl bg-slate-700 flex items-center justify-center text-lg shrink-0"><i class="fa-solid ' + esc(it.icon || 'fa-box-open') + ' text-purple-400"></i></div>' +
            '<div class="flex-1 min-w-0"><h4 class="font-black text-white truncate">' + esc(it.name) + '</h4>' +
            '<p class="text-xs text-slate-400 font-semibold">' + rewardLabel(it) + '</p></div>' +
            '<button class="bg-purple-500 text-white font-black px-3 py-2 rounded-xl border-b-4 border-purple-700 active:scale-95 transition-all whitespace-nowrap" data-scrap-buy="' + esc(it.slug) + '">' + money(it.cost_scraps) + ' <i class="fa-solid fa-wrench"></i></button>' +
            '</div>';
    }

    function recycleItem(gearId) {
        haptic(30);
        fetch(SCRAP_RECYCLE_URL, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ gear_id: gearId, quantity: 1 })
        })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
            .then(function (res) {
                if (!res.body.ok) { window.showToast(res.body.error || 'Could not recycle that item.'); return; }
                if (window.refreshDashboardState) window.refreshDashboardState();
                window.loadShop();
            })
            .catch(function () { window.showToast('Network error.'); });
    }

    function buyScrapItem(slug) {
        haptic(30);
        fetch(SCRAP_BUY_URL, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ item_slug: slug })
        })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
            .then(function (res) {
                if (!res.body.ok) { window.showToast(res.body.error || 'Could not buy that item.'); return; }
                var body = res.body;
                if (body.manifest && body.manifest.length) {
                    renderManifest(body);
                } else if (body.tokens) {
                    if (window.closeModal) window.closeModal();
                    window.showToast('Purchased + ' + money(body.tokens) + ' tokens!');
                } else if (body.stamina) {
                    if (window.closeModal) window.closeModal();
                    window.showToast('Purchased + ' + body.stamina + ' stamina!');
                } else {
                    if (window.closeModal) window.closeModal();
                }
                if (window.refreshDashboardState) window.refreshDashboardState();
                window.loadShop();
            })
            .catch(function () { window.showToast('Network error.'); });
    }

    // Attach a reusable modal container on first use.
    if (!document.getElementById('shop-manifest')) {
        var container = document.createElement('div');
        container.id = 'shop-manifest';
        document.body.appendChild(container);
    }
})();





