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

    var RARITY_COLOR = {
        common: '#94a3b8',
        rare: '#38bdf8',
        epic: '#a78bfa',
        legendary: '#f59e0b'
    };

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function csrfToken() {
        var m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.content : '';
    }

    function haptic(ms) {
        if (navigator.vibrate) navigator.vibrate(ms || 50);
    }

    function confettiBurst() {
        if (typeof confetti === 'function') {
            confetti({ particleCount: 120, spread: 70, origin: { y: 0.6 } });
        }
        haptic([100, 50, 100]);
    }

    window.backToShopPlan = function () {
        var view = document.getElementById('shop-view');
        if (view) view.classList.add('hidden');
        window.ensureSinglePanelVisible('skill-tree');
    };

    function money(n) {
        return String(Number(n) || 0).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    window.loadShop = function () {
        if (window.closeModal) window.closeModal();
        var view = document.getElementById('shop-view');
        var content = document.getElementById('shop-content');
        if (!view) { console.warn('[shop] shop-view not found'); return; }
        window.ensureSinglePanelVisible('shop-view');
        if (window.setActiveNav) window.setActiveNav('nav-shop');
        content.innerHTML = '<p class="text-slate-400">Opening the shop…</p>';
        fetch(STATE_URL, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401 || res.status === 403) throw new Error('not-authenticated');
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(function (data) { window.renderShop(data); })
            .catch(function (err) {
                content.innerHTML = '<p class="text-slate-400">Could not load the shop (error ' + esc(err) + ').</p>';
            });
    };
    var BULK_TIERS = [1, 3, 5, 10];
    var BULK_DISCOUNT = { 1: 0, 3: 10, 5: 15, 10: 20 };

    function bulkCost(price, qty) {
        var pct = BULK_DISCOUNT[qty] || 0;
        return { cost: Math.round(price * (1 - pct / 100) * qty), pct: pct };
    }

    window.renderShop = function (data) {
        var content = document.getElementById('shop-content');
        if (!content) return;
        var html = '<p class="text-xs text-slate-400 font-semibold mb-4">Pull themed gear packs and generic wink crates. Buying 3+ at once knocks 10&ndash;20% off.</p>';

        html += '<div class="flex flex-col gap-3">';
        (data.packs || []).forEach(function (p) {
            var opts = '';
            BULK_TIERS.forEach(function (q) {
                var bc = bulkCost(p.price_tokens, q);
                opts += '<option value="' + q + '" data-cost="' + bc.cost + '" data-pct="' + bc.pct + '">' +
                    q + ' &times; <i class="fa-solid fa-coins"></i> ' + money(bc.cost) +
                    (bc.pct ? ' (' + bc.pct + '% off)' : '') + '</option>';
            });
            html += '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 shadow-lg">' +
                '<div class="flex items-center gap-4">' +
                '<div class="w-14 h-14 rounded-2xl bg-slate-700 flex items-center justify-center text-2xl"><i class="fa-solid ' + esc(p.icon || 'fa-box-open') + ' text-yellow-400"></i></div>' +
                '<div class="flex-1">' +
                '<h3 class="text-lg font-black text-white">' + esc(p.name) + '</h3>' +
                '<p class="text-xs text-slate-400 font-semibold">' +
                (p.domains && p.domains.length ? '<i class="fa-solid fa-crosshairs mr-1"></i>' + esc(p.domains.join(', ')) + ' &middot; ' : '') +
                esc(p.draws) + ' draw' + (p.draws > 1 ? 's' : '') + ' &middot; min ' + esc(p.guaranteed_min_rarity) + ' &middot; ' + money(p.price_tokens) + ' each</p>' +
                '<p class="text-xs text-slate-500 mt-1">' + esc(p.description) + '</p>' +
                '</div>' +
                '</div>' +
                '<div class="mt-3 flex items-center gap-2">' +
                '<select class="flex-1 bg-slate-900 border border-slate-600 rounded-xl px-2 py-2.5 text-sm text-white font-semibold" data-slug="' + esc(p.slug) + '">' + opts + '</select>' +
                '<button class="bg-amber-500 text-slate-900 font-black px-4 py-2.5 rounded-2xl border-b-4 border-amber-700 active:scale-95 transition-all whitespace-nowrap" data-slug="' + esc(p.slug) + '" data-cost="">Buy</button>' +
                '</div>' +
                '</div>';
        });
        html += '</div>';

        // Owned consumables (usable right from the shop).
        var owned = data.owned || {};
        var consumables = (owned['consumable'] || []).filter(function (i) {
            return i.effect_type === 'double_domain' || i.effect_type === 'shield_overage';
        });
        if (consumables.length) {
            html += '<h3 class="text-white font-black mt-6 mb-2"><i class="fa-solid fa-flask text-lime-400"></i> Consumables</h3>';
            html += '<div class="flex flex-col gap-3">';
            consumables.forEach(function (i) {
                html += '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 flex items-center gap-4 shadow-lg">' +
                    '<div class="w-12 h-12 rounded-2xl bg-slate-700 flex items-center justify-center text-xl"><i class="fa-solid ' + esc(i.icon || 'fa-flask') + ' text-lime-400"></i></div>' +
                    '<div class="flex-1"><h4 class="font-black text-white">' + esc(i.name) + '</h4>' +
                    '<p class="text-xs text-slate-400 font-semibold">' + esc(i.effect_type.replace('_', ' ')) + ' &middot; x' + esc(i.quantity) + ' owned</p></div>' +
                    '<button class="bg-lime-500 text-slate-900 font-black px-3 py-2 rounded-xl border-b-4 border-lime-700 active:scale-95 transition-all" data-consume="' + esc(i.id) + '">Use</button>' +
                    '</div>';
            });
            html += '</div>';
        }

        content.innerHTML = html;

        function updateBuyLabel(sel) {
            var opt = sel.options[sel.selectedIndex];
            var cost = opt.getAttribute('data-cost');
            var pct = opt.getAttribute('data-pct');
            var card = sel.closest('.bg-slate-800');
            var btn = card.querySelector('button[data-slug="' + sel.getAttribute('data-slug') + '"]');
            btn.setAttribute('data-cost', cost);
            btn.innerHTML = money(cost) + ' <i class="fa-solid fa-coins"></i>' +
                (Number(pct) > 0 ? ' (-' + pct + '%)' : '');
        }

        content.querySelectorAll('select[data-slug]').forEach(function (sel) {
            updateBuyLabel(sel);
            sel.addEventListener('change', function () { updateBuyLabel(sel); });
        });
        content.querySelectorAll('button[data-slug][data-cost]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var sel = content.querySelector('select[data-slug="' + btn.getAttribute('data-slug') + '"]');
                var qty = sel ? parseInt(sel.value, 10) : 1;
                openPack(btn.getAttribute('data-slug'), qty);
            });
        });
        content.querySelectorAll('button[data-consume]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                consumeItem(btn.getAttribute('data-consume'));
            });
        });
    };

    function openPack(slug, quantity) {
        haptic(30);
        fetch(OPEN_URL, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ pack_slug: slug, quantity: quantity || 1 })
        })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
            .then(function (res) {
                if (!res.body.ok) {
                    alert(res.body.error || 'Could not open pack.');
                    return;
                }
                renderManifest(res.body);
                if (window.refreshDashboardState) window.refreshDashboardState();
                window.loadShop();
            })
            .catch(function () { alert('Network error while opening the pack.'); });
    }

    function renderManifest(payload) {
        haptic([40, 30, 40, 30, 60]);
        var manifest = (payload && payload.manifest) || [];
        var anyEpic = manifest.some(function (m) { return m.rarity === 'epic' || m.rarity === 'legendary'; });
        if (anyEpic) confettiBurst();
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
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ gear_id: gearId })
        })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
            .then(function (res) {
                if (!res.body.ok) { alert(res.body.error || 'Could not use the item.'); return; }
                if (window.refreshDashboardState) window.refreshDashboardState();
                window.loadShop();
            })
            .catch(function () { alert('Network error.'); });
    }

    // Attach a reusable modal container on first use.
    if (!document.getElementById('shop-manifest')) {
        var container = document.createElement('div');
        container.id = 'shop-manifest';
        document.body.appendChild(container);
    }
})();
