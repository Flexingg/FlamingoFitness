/* Loadout panel controller (Phase 9, docs/15 §7).
 * Opens from the "Loadout" bottom-nav tab.
 * Consumes GET /api/v1/loadout/state + POST /api/v1/loadout/equip {gear_id}.
 * Keys mirror core/views.py loadout_state / loadout_equip.
 */
(function () {
    'use strict';

    var STATE_URL = '/api/v1/loadout/state';
    var EQUIP_URL = '/api/v1/loadout/equip';
    var UNEQUIP_URL = '/api/v1/loadout/unequip';
    var SCRAP_RECYCLE_URL = '/api/v1/scrap/recycle';

    var SLOT_ORDER = ['head', 'chest', 'left_hand', 'right_hand', 'legs', 'feet', 'accessory'];

    var SLOT_META = {
        head: { label: 'Head', icon: 'fa-hat-cowboy' },
        chest: { label: 'Chest', icon: 'fa-shirt' },
        left_hand: { label: 'Left Hand', icon: 'fa-hand-fist' },
        right_hand: { label: 'Right Hand', icon: 'fa-hand-back-fist' },
        legs: { label: 'Legs', icon: 'fa-person' },
        feet: { label: 'Feet', icon: 'fa-shoe-prints' },
        accessory: { label: 'Accessory', icon: 'fa-ring' }
    };

    var RARITY_COLOR = {
        common: '#94a3b8', rare: '#38bdf8', epic: '#a78bfa', legendary: '#f59e0b'
    };

    function esc(s) { return window.escHtml(s); }

    function csrfToken() { return window.csrfToken(); }

    function haptic(ms) { return window.haptic(ms); }

    window.backToLoadoutPlan = function () {
        if (window.goBack) { window.goBack(); return; }
        var view = document.getElementById('loadout-view');
        if (view) view.classList.add('hidden');
        window.ensureSinglePanelVisible('skill-tree');
    };

    window.loadLoadout = function () {
        if (window.closeModal) window.closeModal();
        var view = document.getElementById('loadout-view');
        var content = document.getElementById('loadout-content');
        if (!view) { window.ffWarn('[loadout] loadout-view not found'); return; }
        window.ensureSinglePanelVisible('loadout-view');
        if (window.setActiveNav) window.setActiveNav('nav-loadout');
        content.innerHTML = '<p class="text-slate-400">Loading loadout…</p>';
        fetch(STATE_URL, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401 || res.status === 403) throw new Error('not-authenticated');
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(function (data) { window.renderLoadout(data); })
            .catch(function (err) {
                content.innerHTML = '<p class="text-slate-400">Could not load your loadout (error ' + esc(err) + ').</p>';
            });
    };

    function itemCardLabel(item) {
        if (!item) return '<div class="text-slate-500 font-semibold text-sm">Empty slot - equip from below</div>';
        return '<div class="font-black text-white">' + esc(item.name) + '</div>' +
            '<div class="text-xs font-bold" style="color:' + (RARITY_COLOR[item.rarity] || '#94a3b8') + '">' + esc(item.rarity).toUpperCase() + '</div>' +
            '<div class="text-xs text-slate-400 font-semibold mt-1">' + esc(item.effect_type.replace('_', ' ')) +
            (item.effect_domain ? ' &middot; ' + esc(item.effect_domain) : '') + ' +' + esc(item.effect_value) + 'x</div>';
    }
    // ---- Item detail popup ----
    // Any inventory card can be tapped to explain what the item does and when /
    // how it was acquired.
    function normalizeItemDetail(item) {
        if (!item) return null;
        return {
            id: item.id, name: item.name, rarity: item.rarity, icon: item.icon,
            effect_type: (item.effect_type || '').replace(/_/g, ' '),
            effect_domain: item.effect_domain || null,
            effect_value: item.effect_value,
            quantity: item.quantity,
            description: item.description || 'No description on file for this item yet.',
            obtained_at: item.obtained_at || null,
            pack_name: item.pack_name || null,
            equipped: !!item.equipped,
            scrap_value: item.scrap_value,
            total_scraps: item.total_scraps
        };
    }

    window.showItemDetail = function (item) {
        var d = normalizeItemDetail(item);
        if (!d) return;
        haptic(15);
        var color = RARITY_COLOR[d.rarity] || '#94a3b8';
        var when = d.obtained_at ? new Date(d.obtained_at).toLocaleString() : 'Earlier today';
        var how = d.pack_name ? ('Won from the <b>' + esc(d.pack_name) + '</b> pack in the Shop') : 'From the gear catalog / default loadout';
        var badge = d.equipped ? '<span class="text-emerald-400 font-black text-xs uppercase">In Use</span>' : '';
        var overlay = document.getElementById('loadout-item-detail');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'loadout-item-detail';
            document.body.appendChild(overlay);
        }
        overlay.innerHTML = '<div class="modal-overlay show-modal" role="dialog" aria-modal="true">' +
            '<div class="modal-content stat-modal-content rounded-[2rem] p-6 border border-slate-600 shadow-2xl w-[90%] max-w-sm m-auto">' +
            '<div class="w-16 h-16 mx-auto rounded-2xl bg-slate-700 flex items-center justify-center text-3xl mb-3 shadow-inner" style="border:3px solid ' + color + '\"><i class="fa-solid ' + esc(d.icon || 'fa-shield') + '" style="color:' + color + '\"></i></div>' +
            '<h2 class="text-2xl font-black text-white text-center mb-1">' + esc(d.name) + '</h2>' +
            '<div class="flex items-center justify-center gap-2 mb-4">' +
            '<span class="text-center text-sm font-black" style="color:' + color + '\">' + esc(d.rarity).toUpperCase() + '</span>' +
            (badge || '') + '</div>' +
            '<div class="text-sm text-slate-200 font-semibold space-y-3">' +
            '<div><div class="text-indigo-400 font-black text-xs uppercase tracking-wide">What it does</div>' +
            esc(d.effect_type || 'Passive gear bonus') +
            (d.effect_domain ? ' &middot; ' + esc(d.effect_domain) : '') +
            ' +' + esc(d.effect_value) + 'x' +
            (d.quantity ? ' &middot; x' + d.quantity + ' owned' : '') + '</div>' +
            '<div><div class="text-indigo-400 font-black text-xs uppercase tracking-wide">Description</div>' + esc(d.description) + '</div>' +
            '<div><div class="text-indigo-400 font-black text-xs uppercase tracking-wide">How you got it</div>' + how + '</div>' +
            '<div><div class="text-indigo-400 font-black text-xs uppercase tracking-wide">When</div>' + esc(when) + '</div>' +
            (d.scrap_value
                ? '<div><div class="text-indigo-400 font-black text-xs uppercase tracking-wide">Scrap value</div>' +
                  'Recycles for <b class="text-white">' + esc(d.total_scraps != null ? d.total_scraps : d.scrap_value) + ' scraps</b> (unequip it in the loadout first).</div>'
                : '') +
            '</div>' +
            '<button type="button" onclick="window.closeLoadoutItemDetail && window.closeLoadoutItemDetail();" class="w-full bg-flamingo text-white font-bold py-3.5 rounded-2xl border-b-4 border-flamingo-dark hover:brightness-110 active:border-b-0 active:translate-y-1 transition-all shadow-lg mt-4">Got it</button>' +
            '</div></div>';
    };

    window.closeLoadoutItemDetail = function () {
        var overlay = document.getElementById('loadout-item-detail');
        if (overlay) overlay.innerHTML = '';
    };



    window.renderLoadout = function (data) {
        var content = document.getElementById('loadout-content');
        if (!content) return;
        var equipped = data.equipped || {};
        var owned = data.owned || [];

        // Look-up so a tapped card can resolve which item it belongs to.
        var itemById = {};
        (owned || []).forEach(function (o) { itemById[o.id] = o; });
        for (var k in equipped) {
            if (equipped[k]) itemById[equipped[k].id] = equipped[k];
        }

        // Equipment slots panel.
        var html = '<h3 class="text-white font-black mb-3"><i class="fa-solid fa-vest text-indigo-400"></i> Equipment Slots</h3>' +
            '<p class="text-xs text-slate-500 font-semibold mb-3">Tap any item to see what it does and how you got it.</p>';
        html += '<div class="flex flex-col gap-3">';
        SLOT_ORDER.forEach(function (slot) {
            var meta = SLOT_META[slot];
            var item = equipped[slot];
            html += '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 flex items-center gap-4 shadow-lg">' +
                '<div class="w-12 h-12 rounded-2xl bg-slate-700 flex items-center justify-center text-xl"><i class="fa-solid ' + meta.icon + ' text-indigo-300"></i></div>' +
                (item
                    ? '<div class="flex-1 cursor-pointer" data-detail-id="' + esc(item.id) + '" role="button" tabindex="0" aria-label="Item details for ' + esc(item.name) + '">' +
                        '<div class="flex items-center justify-between"><div class="text-xs font-black text-slate-400 uppercase tracking-wide">' + meta.label + '</div>' +
                        '<i class="fa-solid fa-circle-info text-slate-500 text-xs"></i></div>' +
                        itemCardLabel(item) +
                        '<button class="mt-2 text-xs font-bold text-slate-400 underline hover:text-slate-200" data-unequip="' + esc(item.id) + '">Unequip</button>' +
                        '</div>'
                    : '<div class="flex-1"><div class="text-xs font-black text-slate-400 uppercase tracking-wide">' + meta.label + '</div>' +
                        '<div class="text-slate-500 font-semibold text-sm">Empty slot - equip from below</div></div>') +
                '</div>';
        });
        html += '</div>';

        // Full inventory, grouped by slot (everything you own, click to equip).
        var bySlot = {};
        SLOT_ORDER.forEach(function (s) { bySlot[s] = []; });
        (owned || []).forEach(function (o) { if (bySlot[o.slot]) bySlot[o.slot].push(o); });
        var itemCount = (owned || []).length;
        html += '<h3 class="text-white font-black mt-6 mb-2"><i class="fa-solid fa-boxes-stacked text-indigo-400"></i> Inventory (' + itemCount + ')</h3>';
        if (!itemCount) {
            html += window.emptyStateHTML({
                icon: 'fa-box-open',
                title: 'Your inventory is empty',
                desc: 'Pull a pack in the Shop to haul in new gear, then come back here to equip it.',
                hint: 'Tokens buy packs. Packs drop gear.',
                ctaText: 'Open the Shop',
                ctaOnClick: 'window.loadShop && window.loadShop(); return false;'
            });
        } else {
            html += '<div class="flex flex-col gap-3">';
            SLOT_ORDER.forEach(function (slot) {
                var list = bySlot[slot] || [];
                if (!list.length) return;
                list.forEach(function (c) {
                    var meta = SLOT_META[slot];
                    html += '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 flex items-center gap-4 shadow-lg cursor-pointer" data-detail-id="' + esc(c.id) + '" role="button" tabindex="0" aria-label="Item details for ' + esc(c.name) + '">' +
                        '<div class="w-11 h-11 rounded-2xl bg-slate-700 flex items-center justify-center"><i class="fa-solid ' + esc(c.icon || 'fa-shield') + '"></i></div>' +
                        '<div class="flex-1"><div class="flex items-center justify-between"><div class="font-black text-white">' + esc(c.name) + '</div>' +
                        '<i class="fa-solid fa-circle-info text-slate-600 text-xs"></i></div>' +
                        '<div class="text-xs font-bold" style="color:' + (RARITY_COLOR[c.rarity] || '#94a3b8') + '">' + esc(c.rarity).toUpperCase() + ' &middot; ' + meta.label + '</div>' +
                        '<div class="text-xs text-slate-500 font-semibold">' + esc((c.effect_type || '').replace(/_/g, ' ')) +
                        (c.effect_domain ? ' &middot; ' + esc(c.effect_domain) : '') + ' +' + esc(c.effect_value) + 'x</div></div>' +
                        (c.equipped
                            ? '<span class="text-emerald-400 font-black text-xs uppercase">Equipped</span>'
                            : '<div class="flex items-center gap-2 shrink-0">' +
                                '<button class="bg-indigo-500 text-white font-black px-4 py-2 rounded-xl border-b-4 border-indigo-700 active:scale-95 transition-all" data-equip="' + esc(c.id) + '">Equip</button>' +
                                '<button class="bg-slate-600 text-white font-black px-3 py-2 rounded-xl border-b-4 border-slate-800 active:scale-95 transition-all whitespace-nowrap" title="Recycle for scraps" data-recycle="' + esc(c.id) + '" data-scraps="' + esc(c.total_scraps || c.scrap_value || 0) + '">Recycle</button>' +
                              '</div>') +
                        '</div>';
                });
            });
            html += '</div>';
            html += '<p class="text-xs text-slate-500 font-semibold mt-3">Consumables (potions) are kept and used from the <button type="button" onclick="window.loadShop && window.loadShop(); return false;" class="text-indigo-400 font-black underline hover:text-indigo-300">Shop</button>.</p>';
        }

        content.innerHTML = html;

        content.querySelectorAll('button[data-equip]').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                equip(btn.getAttribute('data-equip'));
            });
        });
        content.querySelectorAll('button[data-unequip]').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                unequip(btn.getAttribute('data-unequip'));
            });
        });
        content.querySelectorAll('button[data-recycle]').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.stopPropagation();
                recycleItem(btn.getAttribute('data-recycle'), btn.getAttribute('data-scraps'));
            });
        });
        // Make every item (equipped + inventory) open its detail popup on tap.
        content.querySelectorAll('[data-detail-id]').forEach(function (card) {
            var id = card.getAttribute('data-detail-id');
            if (!id || !itemById[id]) return;
            var openDetail = function () {
                window.showItemDetail(itemById[id]);
            };
            card.addEventListener('click', openDetail);
            card.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openDetail(); }
            });
        });
    };
    function equip(gearId) {
        haptic(30);
        fetch(EQUIP_URL, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ gear_id: gearId })
        })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
            .then(function (res) {
                if (!res.body.ok) { window.showToast(res.body.error || 'Could not equip that item.'); return; }
                if (window.refreshDashboardState) window.refreshDashboardState();
                window.loadLoadout();
            })
            .catch(function () { window.showToast('Network error while equipping.'); });
    }
    function unequip(gearId) {
        haptic(30);
        fetch(UNEQUIP_URL, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ gear_id: gearId })
        })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
            .then(function (res) {
                if (!res.body.ok) { window.showToast(res.body.error || 'Could not unequip that item.'); return; }
                if (window.refreshDashboardState) window.refreshDashboardState();
                window.loadLoadout();
            })
            .catch(function () { window.showToast('Network error while unequipping.'); });
    }
    function recycleItem(gearId, scrapHint) {
        var hint = Number(scrapHint) || 0;
        if (!window.confirm('Recycle this item for ' + hint + ' scraps? This cannot be undone.')) { return; }
        haptic(40);
        fetch(SCRAP_RECYCLE_URL, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ gear_id: gearId })
        })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
            .then(function (res) {
                if (!res.body.ok) { window.showToast(res.body.error || 'Could not recycle that item.'); return; }
                if (window.refreshDashboardState) window.refreshDashboardState();
                window.loadLoadout();
            })
            .catch(function () { window.showToast('Network error while recycling.'); });
    }
})();



