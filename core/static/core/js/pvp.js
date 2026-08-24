/* PvP Gym panel controller (Phase 9, docs/15 §7).
 * Opens from the "PvP" bottom-nav tab.
 * Consumes GET /api/v1/pvp/state, POST /api/v1/pvp/defend {terrain,name},
 * POST /api/v1/pvp/attack {gym_id}. Keys mirror core/views.py pvp_* and
 * core/services/combat.py pvp_state.
 */
(function () {
    'use strict';

    var STATE_URL = '/api/v1/pvp/state';
    var DEFEND_URL = '/api/v1/pvp/defend';
    var ATTACK_URL = '/api/v1/pvp/attack';

    var TERRAINS = ['endurance', 'strength', 'nutrition', 'hydration', 'recovery'];

    var PER_CAMP_ORDER = ['cardio', 'strength', 'nutrition', 'hydration', 'sleep'];
    var PER_CAMP_LABEL = {
        cardio: 'Cardio', strength: 'Strength', nutrition: 'Nutrition',
        hydration: 'Hydration', sleep: 'Sleep'
    };

    function money(n) { return window.fmoney(n); }

    function esc(s) { return window.escHtml(s); }

    function getCsrfToken() {
        var m = document.querySelector('meta[name="csrf-token"]');
        if (m && m.content && m.content !== 'NOTPROVIDED' && m.content !== '') return m.content;
        var match = document.cookie.match(/(?:^|;\s*)(?:csrftoken|__Secure-csrftoken)=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function haptic(ms) { return window.haptic(ms); }

    function when(dt) {
        if (!dt) return '';
        var d = new Date(dt);
        return d.toLocaleString();
    }

    window.currentPvPMode = 'gyms';

    window.backToPvPPlan = function () {
        if (window.goBack) { window.goBack(); return; }
        var view = document.getElementById('pvp-view');
        if (view) view.classList.add('hidden');
        window.ensureSinglePanelVisible('skill-tree');
    };

    window.switchPvPMode = function (mode) {
        window.currentPvPMode = mode || 'gyms';
        var btnGyms = document.getElementById('btn-mode-gyms');
        var btnBounties = document.getElementById('btn-mode-bounties');
        var paneGyms = document.getElementById('pvp-gyms-pane');
        var paneBounties = document.getElementById('pvp-bounties-pane');
        var postBountyBtn = document.getElementById('pvp-post-bounty-btn');
        var titleEl = document.getElementById('pvp-header-title');
        var subEl = document.getElementById('pvp-header-sub');

        if (window.currentPvPMode === 'bounties') {
            if (btnGyms) {
                btnGyms.className = 'pvp-mode-btn flex-1 py-2.5 text-xs font-black text-slate-400 rounded-xl transition-all flex items-center justify-center gap-2 hover:text-slate-200';
            }
            if (btnBounties) {
                btnBounties.className = 'pvp-mode-btn active flex-1 py-2.5 text-xs font-black text-white bg-slate-700 rounded-xl transition-all flex items-center justify-center gap-2 shadow';
            }
            if (paneGyms) paneGyms.classList.add('hidden');
            if (paneBounties) paneBounties.classList.remove('hidden');
            if (postBountyBtn) postBountyBtn.classList.remove('hidden');
            if (titleEl) titleEl.innerHTML = '<i class="fa-solid fa-crosshairs text-pink-500"></i> Bounty Board';
            if (subEl) subEl.textContent = '1v1 Fitness Duels & Contracts';

            // Ensure bounties script is loaded and load state
            var ensureBounties = function () {
                if (typeof window.loadBountiesState === 'function') {
                    window.loadBountiesState();
                } else if (typeof window.loadBounties === 'function') {
                    window.loadBounties();
                }
            };

            if (window.LAZY_SCRIPT_URLS && window.LAZY_SCRIPT_URLS.bounties && typeof window.loadScript === 'function') {
                window.loadScript(window.LAZY_SCRIPT_URLS.bounties).then(ensureBounties);
            } else {
                ensureBounties();
            }
        } else {
            if (btnGyms) {
                btnGyms.className = 'pvp-mode-btn active flex-1 py-2.5 text-xs font-black text-white bg-slate-700 rounded-xl transition-all flex items-center justify-center gap-2 shadow';
            }
            if (btnBounties) {
                btnBounties.className = 'pvp-mode-btn flex-1 py-2.5 text-xs font-black text-slate-400 rounded-xl transition-all flex items-center justify-center gap-2 hover:text-slate-200';
            }
            if (paneGyms) paneGyms.classList.remove('hidden');
            if (paneBounties) paneBounties.classList.add('hidden');
            if (postBountyBtn) postBountyBtn.classList.add('hidden');
            if (titleEl) titleEl.innerHTML = '<i class="fa-solid fa-fist-raised text-rose-500"></i> PvP Arena';
            if (subEl) subEl.textContent = 'Gym Battles & Territory Control';

            window.fetchPvPGyms();
        }
    };

    window.fetchPvPGyms = function () {
        var content = document.getElementById('pvp-content');
        if (content) content.innerHTML = '<div class="text-center py-10 text-slate-400 font-bold text-sm"><i class="fa-solid fa-spinner fa-spin mr-2 text-rose-400"></i> Scouting the arena…</div>';
        fetch(STATE_URL, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401 || res.status === 403) throw new Error('not-authenticated');
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(function (data) { window.renderPvP(data); })
            .catch(function (err) {
                if (content) content.innerHTML = '<p class="text-slate-400 p-4">Could not load PvP (error ' + esc(err) + ').</p>';
            });
    };

    window.loadPvP = function (defaultMode) {
        if (window.closeModal) window.closeModal();

        var runLoad = function () {
            var view = document.getElementById('pvp-view');
            if (!view) { window.ffWarn('[pvp] pvp-view not found'); return; }
            window.ensureSinglePanelVisible('pvp-view');
            if (window.setActiveNav) window.setActiveNav('nav-pvp');
            window.switchPvPMode(defaultMode || 'gyms');
        };

        if (typeof window.ensurePanelLoaded === 'function') {
            return window.ensurePanelLoaded('pvp-view').then(runLoad);
        } else {
            return runLoad();
        }
    };
    window.renderPvP = function (data) {
        var content = document.getElementById('pvp-content');
        if (!content) return;

        var html = '';

        // My power audit: total power, its inputs, and how to grow it.
        var me = data.me || {};
        var perCamp = me.per_campaign || {};
        var activeGear = (me.equipped || []).filter(function (g) { return g.active; });
        html += '<div class="flex items-center justify-between mb-2"><h3 class="text-white font-black"><i class="fa-solid fa-bolt text-yellow-400"></i> My Power</h3>' +
            '<button class="text-xs font-bold text-slate-300 bg-slate-700 border border-slate-600 rounded-2xl px-3 py-1.5 hover:text-white active:scale-95 transition-all" onclick="showPvpHelp(); return false;"><i class="fa-solid fa-circle-question mr-1"></i>How PvP works</button></div>';
        html += '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 mb-4 shadow-lg">' +
            '<div class="flex items-center justify-between">' +
            '<div><div class="text-xs text-slate-400 uppercase font-black">Attack power</div>' +
            '<div class="text-3xl font-black text-yellow-300" id="pvp-my-power">' + money(me.power) + '</div>' +
            '<div class="text-xs text-slate-400 font-semibold mt-1">' + activeGear.length + ' equipped item' + (activeGear.length === 1 ? '' : 's') + ' contributing</div></div>' +
            '<div class="text-right text-xs font-semibold text-slate-400">7-day consistency<br><span class="font-black text-white text-lg">' + money(me.consistency) + '</span></div>' +
            '</div>';
        html += '<div class="mt-3 flex flex-col gap-1.5">';
        PER_CAMP_ORDER.forEach(function (key) {
            if (!(key in perCamp)) return;
            var label = PER_CAMP_LABEL[key] || key;
            html += '<div class="flex items-center justify-between text-xs"><span class="text-slate-400 font-semibold">' + label + '</span>' +
                '<span class="font-black ' + (perCamp[key] > 0 ? 'text-slate-100' : 'text-slate-500') + '">' + money(perCamp[key]) + '</span></div>';
        });
        html += '</div>';
        html += '<p class="text-xs text-slate-400 font-semibold mt-3"><i class="fa-solid fa-lightbulb text-yellow-400"></i> Raise power by logging consistent 7-day weeks and equipping higher-rarity gear in every slot.</p>' +
            '</div>';


        // My gym / defense.
        var gym = data.my_gym;
        html += '<h3 class="text-white font-black mb-2"><i class="fa-solid fa-dumbbell text-green-400"></i> My Gym</h3>';
        if (gym) {
            html += '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 text-sm mb-2 shadow-lg">' +
                '<div class="flex items-center justify-between"><b class="text-white">' + esc(gym.name) + '</b>' +
                '<span class="text-green-300 font-bold uppercase text-xs">' + (gym.defense_set ? 'Defending' : 'No loadout') + '</span></div>' +
                '<div class="text-xs text-slate-400 font-semibold mt-1">Terrain: ' + esc(gym.terrain) + '</div>' +
                '</div>';
        } else {
            html += window.emptyStateHTML({
                icon: 'fa-flag',
                title: 'No gym yet',
                desc: 'Claim one below, then equip gear in your Loadout to defend it.',
                hint: 'Terrain matches the element you defend.',
                secondary: true
            });
        }

        // Rebuild defense form (always shown so players can update terrain/name).
        html += '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 mb-4 shadow-lg">' +
            '<label class="text-xs font-black text-slate-300 uppercase">Gym name</label>' +
            '<input id="pvp-name" class="w-full bg-slate-900 border border-slate-600 rounded-xl px-3 py-2 mt-1 mb-3 text-white" placeholder="Flamingo Arena" value="' + (gym ? esc(gym.name) : '') + '">' +
            '<label class="text-xs font-black text-slate-300 uppercase">Terrain (element you defend)</label>' +
            '<div class="flex flex-wrap gap-2 mt-1 mb-3">';
        TERRAINS.forEach(function (t) {
            html += '<button class="terrain-chip px-3 py-1.5 rounded-xl text-xs font-bold border transition-all ' +
                (gym && gym.terrain === t ? 'bg-green-500 border-green-700 text-slate-900' : 'bg-slate-700 border-slate-600 text-slate-200') +
                '" data-terrain="' + t + '">' + esc(t) + '</button>';
        });
        html += '</div><button class="w-full bg-green-500 text-slate-900 font-black py-3 rounded-2xl border-b-4 border-green-700 active:scale-95 transition-all" id="pvp-defend">Set Defense</button></div>';

        // My turf.
        var turf = data.my_turf;
        if (turf) {
            html += '<h3 class="text-white font-black mb-2"><i class="fa-solid fa-flag text-yellow-400"></i> My Territory</h3>' +
                '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 text-sm mb-4 shadow-lg">' +
                '<div class="flex items-center justify-between"><b class="text-white">' + esc(turf.gym) + '</b>' +
                '<span class="text-emerald-300 font-bold text-xs uppercase">Held</span></div>' +
                '<div class="text-xs text-slate-400 font-semibold mt-1">Held until ' + esc(when(turf.held_until)) + '</div>' +
                '</div>';
        }

        // Attackable gyms.
        html += '<h3 class="text-white font-black mb-2"><i class="fa-solid fa-fire text-red-400"></i> Attackable Gyms</h3>';
        var attackable = data.attackable || [];
        if (!attackable.length) {
            html += window.emptyStateHTML({
                icon: 'fa-fire',
                title: 'No enemy gyms to attack yet',
                desc: 'Gyms you can attack appear here once rivals take turf in your territory.',
                hint: 'Consistency and gear decide every fight.',
                secondary: true
            });
        } else {
            html += '<div class="grid grid-cols-1 gap-3 mb-4">';
            attackable.forEach(function (g) {
                html += '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 flex items-center gap-4 shadow-lg">' +
                    '<div class="w-11 h-11 rounded-2xl bg-slate-700 flex items-center justify-center text-lg"><i class="fa-solid fa-dumbbell text-red-400"></i></div>' +
                    '<div class="flex-1"><div class="font-black text-white">' + esc(g.name) + '</div>' +
                    '<div class="text-xs text-slate-400 font-semibold">' + esc(g.owner) + ' &middot; ' + esc(g.terrain) + ' &middot; power ' + esc(g.defender_power) + '</div></div>' +
                    '<button class="bg-red-500 text-white font-black px-4 py-2 rounded-xl border-b-4 border-red-700 active:scale-95 transition-all" data-gym="' + esc(g.id) + '">Attack</button>' +
                    '</div>';
            });
            html += '</div>';
        }

        // Match history.
        var matches = data.matches || [];
        if (matches.length) {
            html += '<h3 class="text-white font-black mb-2"><i class="fa-solid fa-clock-rotate-left text-slate-400"></i> Recent Matches</h3><div class="flex flex-col gap-2">';
            matches.forEach(function (m) {
                var won = m.did_win;
                html += '<div class="bg-slate-800 border border-slate-600 rounded-2xl px-3 py-2 text-xs flex items-center gap-2">' +
                    '<span class="font-black ' + (won ? 'text-emerald-400' : 'text-red-400') + '">' + (won ? 'W' : 'L') + '</span>' +
                    '<span class="text-slate-300 font-semibold">' + esc(m.defender) + '</span>' +
                    '<span class="text-slate-500">' + esc(m.attacker_power) + ' vs ' + esc(m.defender_power) + '</span>' +
                    '</div>';
            });
            html += '</div>';
        }

        content.innerHTML = html;

        var selectedTerrain = gym ? gym.terrain : 'strength';
        content.querySelectorAll('.terrain-chip').forEach(function (chip) {
            chip.addEventListener('click', function () {
                content.querySelectorAll('.terrain-chip').forEach(function (c) {
                    c.classList.remove('bg-green-500', 'border-green-700', 'text-slate-900');
                    c.classList.add('bg-slate-700', 'border-slate-600', 'text-slate-200');
                });
                chip.classList.add('bg-green-500', 'border-green-700', 'text-slate-900');
                chip.classList.remove('bg-slate-700', 'border-slate-600', 'text-slate-200');
                selectedTerrain = chip.getAttribute('data-terrain');
            });
        });
        document.getElementById('pvp-defend').addEventListener('click', function () {
            defend(selectedTerrain, document.getElementById('pvp-name').value);
        });
        content.querySelectorAll('button[data-gym]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                attackGym(btn.getAttribute('data-gym'));
            });
        });
    };

    function defend(terrain, name) {
        haptic(30);
        fetch(DEFEND_URL, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ terrain: terrain, name: name })
        })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
            .then(function (res) {
                if (!res.body.ok) { window.showToast(res.body.error || 'Could not set defense.'); return; }
                if (window.refreshDashboardState) window.refreshDashboardState();
                window.loadPvP();
            })
            .catch(function () { window.showToast('Network error while setting defense.'); });
    }

    function attackGym(gymId) {
        if (navigator.vibrate) navigator.vibrate([70, 40, 90]);
        fetch(ATTACK_URL, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ gym_id: gymId })
        })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, body: d }; }); })
            .then(function (res) {
                if (!res.body.ok) { window.showToast(res.body.error || 'Attack failed.'); return; }
                var won = res.body.did_win;
                if (won && typeof confetti === 'function') confetti({ particleCount: 120, spread: 80, origin: { y: 0.6 } });
                window.showToast((won ? 'VICTORY!' : 'Defeat.') + ' (your power ' + res.body.attacker_power + ' vs ' + res.body.defender_power + ')');
                if (window.refreshDashboardState) window.refreshDashboardState();
                window.loadPvP();
            })
            .catch(function () { window.showToast('Network error during the gym battle.'); });
    }

    window.showPvpHelp = function () {
        var overlay = document.getElementById('pvp-help');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'pvp-help';
            document.body.appendChild(overlay);
        }
        overlay.innerHTML = '<div class="modal-overlay show-modal" onclick="if (event.target === this) closePvpHelp();">' +
            '<div class="modal-content stat-modal-content rounded-[2rem] p-6 border border-slate-600 shadow-2xl w-[90%] max-w-sm m-auto">' +
            '<h2 class="text-2xl font-black text-white text-center mb-3"><i class="fa-solid fa-dumbbell text-green-400 mr-2"></i>How PvP works</h2>' +
            '<div class="text-sm text-slate-200 font-semibold space-y-3">' +
            '<p><b>Offense power</b> = your 7-day consistency &times; each equipped gear multiplier, summed across all 5 campaigns.</p>' +
            '<p><b>Defense power</b> = the consistency snapshot saved to your Gym when you press <b>Set Defense</b>. Equipped gear does not defend.</p>' +
            '<p><b>Attacking</b> a gym wins when your power &times; the aggressor edge (&gt;1&times;) beats the defender&apos;s power.</p>' +
            '<p><b>Element wheel:</b> if your loadout element is super-effective against a gym&apos;s terrain you get a +10% edge bonus.</p>' +
            '<p><b>Holding territory:</b> a win parks you in that gym until the hold window passes, and pays daily token yields.</p>' +
            '<p><b>Grow faster:</b> log consistent 7-day weeks &middot; equip higher-rarity gear &middot; fill every slot &middot; pop consumable buffs.</p>' +
            '</div>' +
            '<button onclick="closePvpHelp();" class="w-full bg-green-500 text-slate-900 font-bold py-3.5 rounded-2xl border-b-4 border-green-700 hover:brightness-110 active:border-b-0 active:translate-y-1 transition-all shadow-lg mt-4">Got it</button>' +
            '</div></div>';
    };

    window.closePvpHelp = function () {
        var overlay = document.getElementById('pvp-help');
        if (overlay) overlay.innerHTML = '';
    };
})();



