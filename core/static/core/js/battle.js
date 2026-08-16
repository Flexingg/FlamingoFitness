/* Battle (PvE sieges) panel controller (Phase 9, docs/15 §7).
 * Opens from the "Battle" bottom-nav tab.
 * Consumes GET /api/v1/battle/state, GET /api/v1/battle/campaign/<campaign>,
 * POST /api/v1/battle/engage, POST /api/v1/battle/attack.
 * Keys mirror core/views.py battle_state / battle_campaign / battle_engage /
 * battle_attack and core/services/combat.py payloads.
 */
(function () {
    'use strict';

    var STATE_URL = '/api/v1/battle/state';
    var CAMPAIGN_URL = '/api/v1/battle/campaign/';
    var ENGAGE_URL = '/api/v1/battle/engage';
    var ATTACK_URL = '/api/v1/battle/attack';

    var CAMPAIGN_ICON = {
        cardio: 'fa-heart-pulse', strength: 'fa-dumbbell', nutrition: 'fa-apple-whole',
        hydration: 'fa-droplet', sleep: 'fa-moon'
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

    function money(n) {
        return String(Number(n) || 0).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    window.backToBattlePlan = function () {
        var view = document.getElementById('battle-view');
        if (view) view.classList.add('hidden');
        window.ensureSinglePanelVisible('skill-tree');
    };

    window.loadBattle = function () {
        if (window.closeModal) window.closeModal();
        var view = document.getElementById('battle-view');
        var content = document.getElementById('battle-content');
        if (!view) { console.warn('[battle] battle-view not found'); return; }
        window.ensureSinglePanelVisible('battle-view');
        if (window.setActiveNav) window.setActiveNav('nav-battle');
        content.innerHTML = '<p class="text-slate-400">Assembling the party…</p>';
        fetch(STATE_URL, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401 || res.status === 403) throw new Error('not-authenticated');
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(function (data) { window.renderBattle(data); })
            .catch(function (err) {
                content.innerHTML = '<p class="text-slate-400">Could not load the battle (error ' + esc(err) + ').</p>';
            });
    };
    function hpPct(damage, total) {
        var t = Number(total) || 1;
        return Math.max(0, Math.min(100, Math.round(((t - Number(damage || 0)) / t) * 100)));
    }

    window.renderBattle = function (data) {
        var content = document.getElementById('battle-content');
        if (!content) return;
        var html = '<p class="text-xs text-slate-400 font-semibold mb-4">Tap a campaign to engage its boss. Buy gear in the Shop and equip it in the Loadout to hit harder.</p>';

        html += '<div class="grid grid-cols-1 gap-3">';
        (data.campaigns || []).forEach(function (c) {
            var ratio = c.total_hp ? Math.round((c.damage_dealt / c.total_hp) * 100) : 0;
            var pct = hpPct(c.damage_dealt, c.total_hp);
            var stateLabel = c.conquered ? 'CONQUERED' : (c.engaged ? 'Sieging' : 'Not engaged');
            var stateColor = c.conquered ? 'text-emerald-400' : (c.engaged ? 'text-red-400' : 'text-slate-500');
            html += '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 shadow-lg" data-campaign="' + esc(c.campaign) + '" role="button" tabindex="0">' +
                '<div class="flex items-center gap-3">' +
                '<div class="w-12 h-12 rounded-2xl bg-slate-700 flex items-center justify-center text-xl"><i class="fa-solid ' + (CAMPAIGN_ICON[c.campaign] || 'fa-dragon') + ' text-red-400"></i></div>' +
                '<div class="flex-1">' +
                '<div class="flex items-center gap-2"><h3 class="font-black text-white">' + esc(c.boss.name || c.label) + '</h3>' +
                '<span class="text-xs font-black ' + stateColor + ' uppercase">' + stateLabel + '</span></div>' +
                '<div class="text-xs text-slate-400 font-semibold">' + esc(c.campaign) + '</div>' +
                '</div>' +
                '<i class="fa-solid fa-chevron-right text-slate-500"></i>' +
                '</div>' +
                '<div class="mt-3 h-3 bg-slate-700 rounded-full overflow-hidden border border-slate-600">' +
                '<div class="h-full rounded-full ' + (c.conquered ? 'bg-emerald-500' : 'bg-red-500') + '" style="width:' + pct + '%"></div></div>' +
                '<div class="flex justify-between text-xs mt-1"><span class="text-slate-400 font-semibold">HP</span>' +
                '<span class="text-slate-300 font-bold">' + money(c.total_hp - c.damage_dealt) + ' / ' + money(c.total_hp) + '</span></div>' +
                '</div>';
        });
        html += '</div>';
        content.innerHTML = html;

        content.querySelectorAll('[data-campaign]').forEach(function (card) {
            card.addEventListener('click', function () {
                openCampaign(card.getAttribute('data-campaign'));
            });
            card.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') openCampaign(card.getAttribute('data-campaign'));
            });
        });
    };

    function openCampaign(campaign) {
        haptic(20);
        var content = document.getElementById('battle-content');
        content.innerHTML = '<p class="text-slate-400">Engaging boss…</p>';
        fetch(CAMPAIGN_URL + campaign + '/', { credentials: 'same-origin' })
            .then(function (res) { return res.json(); })
            .then(function (data) { renderCampaignDetail(data); })
            .catch(function () {
                content.innerHTML = '<p class="text-slate-400">Could not load this campaign.</p>';
            });
    }

    function renderCampaignDetail(data) {
        var content = document.getElementById('battle-content');
        if (!content) return;
        var boss = data.boss || {};
        var pct = hpPct(boss.damage_dealt, boss.hp_total);
        var weaknesses = (boss.weaknesses || []).map(function (w) { return esc(w); }).join(', ');
        var resistances = (boss.resistances || []).map(function (r) { return esc(r); }).join(', ');
        var mech = boss.mechanics || {};
        var mechNote = '';
        if (mech.heal_on_overage) mechNote += '<div class="text-xs text-red-300 font-semibold mt-1"><i class="fa-solid fa-triangle-exclamation mr-1"></i>Self-heals ' + money(500) + ' HP when calories over goal</div>';
        if (mech.front_load_water_noon) mechNote += '<div class="text-xs text-sky-300 font-semibold mt-1"><i class="fa-solid fa-droplet mr-1"></i>Front-loaded hydration deals 2x</div>';

        var html = '<div class="text-center mb-4">' +
            '<div class="w-20 h-20 mx-auto rounded-full bg-slate-800 border-4 border-red-500/40 flex items-center justify-center text-4xl mb-2"><i class="fa-solid ' + esc(boss.icon || 'fa-dragon') + ' text-red-400"></i></div>' +
            '<h3 class="text-2xl font-black text-white">' + esc(boss.name || '???') + '</h3>' +
            '</div>' +
            '<div class="h-4 bg-slate-700 rounded-full overflow-hidden border border-slate-600 mb-1">' +
            '<div class="h-full bg-red-500 rounded-full transition-all" style="width:' + pct + '%"></div></div>' +
            '<div class="flex justify-between text-xs mb-3"><span class="text-slate-400 font-semibold">' + esc(boss.slug || '') + '</span>' +
            '<span class="text-slate-300 font-bold">' + money(Math.max(0, boss.hp_total - boss.damage_dealt)) + ' / ' + money(boss.hp_total) + '</span></div>';

        if (boss.conquered) {
            html += '<div class="bg-emerald-500/10 border border-emerald-500/40 rounded-2xl p-3 text-center text-emerald-300 font-black mb-4"><i class="fa-solid fa-crown mr-1"></i>CONQUERED</div>';
        }
        if (weaknesses) html += '<div class="text-xs text-red-300 font-semibold"><i class="fa-solid fa-bullseye mr-1"></i>Weak: ' + weaknesses + '</div>';
        if (resistances) html += '<div class="text-xs text-slate-400 font-semibold"><i class="fa-solid fa-shield mr-1"></i>Resists: ' + resistances + '</div>';
        html += mechNote;

        html += '<div class="bg-slate-800 border border-slate-600 rounded-2xl p-3 mt-3 text-xs text-slate-300 font-semibold">' +
            'Today\'s damage: <b class="text-white">' + money(data.today_base_damage) + '</b> base &times; <b class="text-white">' + esc(data.gear_multiplier) + '</b> gear</div>';

        html += '<div class="flex flex-col gap-3 mt-4">';
        if (!boss.conquered) {
            if (!boss.slug) {
                html += '<button class="bg-red-500 text-white font-black py-3.5 rounded-2xl border-b-4 border-red-700 active:scale-95 transition-all" id="battle-engage">Engage</button>';
            } else {
                html += '<button class="bg-red-500 text-white font-black py-3.5 rounded-2xl border-b-4 border-red-700 active:scale-95 transition-all" id="battle-attack"><i class="fa-solid fa-bolt mr-1"></i>Attack (1 stamina)</button>';
            }
        }
        html += '<button class="bg-slate-700 text-slate-200 font-black py-3 rounded-2xl border-b-4 border-slate-900 active:scale-95 transition-all" id="battle-back-list"><i class="fa-solid fa-arrow-left mr-1"></i>Back to campaigns</button>';
        html += '</div>';

        content.innerHTML = html;

        var attackBtn = document.getElementById('battle-attack');
        if (attackBtn) attackBtn.addEventListener('click', function () { attack(data.campaign); });

        var engageBtn = document.getElementById('battle-engage');
        if (engageBtn) engageBtn.addEventListener('click', function () { engage(data.campaign); });

        document.getElementById('battle-back-list').addEventListener('click', window.loadBattle);
    }

    // Haptics MUST fire synchronously inside the user gesture handler (docs/09
    // §11). Now that stamina has committed, vibrate before awaiting the fetch.
    function attack(campaign) {
        if (navigator.vibrate) navigator.vibrate([90, 30, 120, 50, 80]);
        fetch(ATTACK_URL, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ campaign: campaign })
        })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
            .then(function (res) {
                if (!res.body.ok) { alert(res.body.error || 'Attack failed.'); return; }
                if (res.body.conquered) {
                    if (typeof confetti === 'function') confetti({ particleCount: 180, spread: 90, origin: { y: 0.5 } });
                    alert('BOSS CONQUERED! +' + (res.body.tokens_won || 150) + ' tokens');
                }
                if (window.refreshDashboardState) window.refreshDashboardState();
                openCampaign(campaign);  // refetch fresh HP + wallet
            })
            .catch(function () { alert('Network error during the attack.'); });
    }

    function engage(campaign) {
        haptic(30);
        fetch(ENGAGE_URL, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ campaign: campaign })
        })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
            .then(function (res) {
                if (!res.body.ok) { alert(res.body.error || 'Could not engage.'); return; }
                if (window.refreshDashboardState) window.refreshDashboardState();
                openCampaign(campaign);
            })
            .catch(function () { alert('Network error while engaging.'); });
    }
})();
