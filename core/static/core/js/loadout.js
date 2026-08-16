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

    window.backToLoadoutPlan = function () {
        var view = document.getElementById('loadout-view');
        if (view) view.classList.add('hidden');
        window.ensureSinglePanelVisible('skill-tree');
    };

    window.loadLoadout = function () {
        if (window.closeModal) window.closeModal();
        var view = document.getElementById('loadout-view');
        var content = document.getElementById('loadout-content');
        if (!view) { console.warn('[loadout] loadout-view not found'); return; }
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

    window.renderLoadout = function (data) {
        var content = document.getElementById('loadout-content');
        if (!content) return;
        var equipped = data.equipped || {};
        var owned = data.owned || [];

        // Equipment slots panel.
        var html = '<h3 class="text-white font-black mb-3"><i class="fa-solid fa-vest text-indigo-400"></i> Equipment Slots</h3>';
        html += '<div class="flex flex-col gap-3">';
        SLOT_ORDER.forEach(function (slot) {
            var meta = SLOT_META[slot];
            var item = equipped[slot];
            html += '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 flex items-center gap-4 shadow-lg">' +
                '<div class="w-12 h-12 rounded-2xl bg-slate-700 flex items-center justify-center text-xl"><i class="fa-solid ' + meta.icon + ' text-indigo-300"></i></div>' +
                '<div class="flex-1"><div class="text-xs font-black text-slate-400 uppercase tracking-wide">' + meta.label + '</div>' +
                itemCardLabel(item) +
                (item ? '<button class="mt-2 text-xs font-bold text-slate-400 underline hover:text-slate-200" data-unequip="' + esc(item.id) + '">Unequip</button>' : '') +
                '</div></div>';
        });
        html += '</div>';

        // Full inventory, grouped by slot (everything you own, click to equip).
        var bySlot = {};
        SLOT_ORDER.forEach(function (s) { bySlot[s] = []; });
        (owned || []).forEach(function (o) { if (bySlot[o.slot]) bySlot[o.slot].push(o); });
        var itemCount = (owned || []).length;
        html += '<h3 class="text-white font-black mt-6 mb-2"><i class="fa-solid fa-boxes-stacked text-indigo-400"></i> Inventory (' + itemCount + ')</h3>';
        if (!itemCount) {
            html += '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 text-sm text-slate-300 font-semibold">' +
                '<p class="mb-1"><i class="fa-solid fa-circle-info text-indigo-400"></i> Your inventory is empty.</p>' +
                '<p class="text-slate-400">Head to <b>Shop</b> (the Game button) and pull a pack to haul in new gear, then come back here to equip it.</p></div>';
        } else {
            html += '<div class="flex flex-col gap-3">';
            SLOT_ORDER.forEach(function (slot) {
                var list = bySlot[slot] || [];
                if (!list.length) return;
                list.forEach(function (c) {
                    var meta = SLOT_META[slot];
                    html += '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 flex items-center gap-4 shadow-lg">' +
                        '<div class="w-11 h-11 rounded-2xl bg-slate-700 flex items-center justify-center"><i class="fa-solid ' + esc(c.icon || 'fa-shield') + '"></i></div>' +
                        '<div class="flex-1"><div class="font-black text-white">' + esc(c.name) + '</div>' +
                        '<div class="text-xs font-bold" style="color:' + (RARITY_COLOR[c.rarity] || '#94a3b8') + '">' + esc(c.rarity).toUpperCase() + ' &middot; ' + meta.label + '</div>' +
                        '<div class="text-xs text-slate-500 font-semibold">' + esc(c.effect_type.replace('_', ' ')) +
                        (c.effect_domain ? ' &middot; ' + esc(c.effect_domain) : '') + ' +' + esc(c.effect_value) + 'x</div></div>' +
                        (c.equipped
                            ? '<span class="text-emerald-400 font-black text-xs uppercase">Equipped</span>'
                            : '<button class="bg-indigo-500 text-white font-black px-4 py-2 rounded-xl border-b-4 border-indigo-700 active:scale-95 transition-all" data-equip="' + esc(c.id) + '">Equip</button>') +
                        '</div>';
                });
            });
            html += '</div>';
            html += '<p class="text-xs text-slate-500 font-semibold mt-3">Consumables (potions) are kept and used from the Shop.</p>';
        }

        content.innerHTML = html;

        content.querySelectorAll('button[data-equip]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                equip(btn.getAttribute('data-equip'));
            });
        });
        content.querySelectorAll('button[data-unequip]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                unequip(btn.getAttribute('data-unequip'));
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
                if (!res.body.ok) { alert(res.body.error || 'Could not equip that item.'); return; }
                if (window.refreshDashboardState) window.refreshDashboardState();
                window.loadLoadout();
            })
            .catch(function () { alert('Network error while equipping.'); });
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
                if (!res.body.ok) { alert(res.body.error || 'Could not unequip that item.'); return; }
                if (window.refreshDashboardState) window.refreshDashboardState();
                window.loadLoadout();
            })
            .catch(function () { alert('Network error while unequipping.'); });
    }
})();
