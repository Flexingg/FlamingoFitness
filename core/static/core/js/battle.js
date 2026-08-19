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
var LEADERBOARD_URL = '/api/v1/battle/leaderboard/';
    var HISTORY_URL = '/api/v1/battle/history/';

    var MEDALS = { 1: '\uD83E\uDD47', 2: '\uD83E\uDD48', 3: '\uD83E\uDD49' };
    var DEFAULT_AVATAR = 'https://api.dicebear.com/7.x/avataaars/svg?seed=Flamingo';

    var CAMPAIGN_ICON = {
        cardio: 'fa-heart-pulse', strength: 'fa-dumbbell', nutrition: 'fa-apple-whole',
        hydration: 'fa-droplet', sleep: 'fa-moon'
    };
    var CAMPAIGN_LABEL = {
        cardio: 'Cardio', strength: 'Weightlifting', nutrition: 'Nutrition',
        hydration: 'Hydration', sleep: 'Sleep'
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
function avatarImg(className, a) {
        var src = (a && a.trim()) ? a : DEFAULT_AVATAR;
        return '<img class="' + className + '" src="' + esc(src) +
            '" alt="" onerror="this.onerror=null;this.src=\'' + DEFAULT_AVATAR + '\';">';
    }

    function roundMult(v) {
        var n = Number(v);
        if (!isFinite(n)) return '1';
        return String(+(Math.round(n * 100) / 100));
    }

    // Small color chip reflecting whether this boss is weak / resists its own campaign.
    function vulnChip(c) {
        var v = Number(c.vulnerability) || 1;
        if (v >= 1.99) {
            return '<span class="vuln-chip weak" data-help="This boss is weak to its own campaign right now, so your damage gets an extra 2x multiplier. Strike now while it is vulnerable!" aria-label="Weak to its campaign"><i class="fa-solid fa-bullseye"></i>2&times; weak</span>';
        }
        if (v <= 0.51) {
            return '<span class="vuln-chip resist" data-help="This boss shrugs off its own campaign, cutting your damage in half. It may be smarter to spend stamina on a different campaign for now." aria-label="Resists its campaign"><i class="fa-solid fa-shield"></i>&frac12; resists</span>';
        }
        return '';
    }

    window.backToBattlePlan = function () {
        if (window.goBack) { window.goBack(); return; }
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
        content.innerHTML = '<p class="text-slate-400">Assembling the party...</p>';
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
        var stamina = (data.wallet && data.wallet.stamina != null) ? data.wallet.stamina : '-';
        var cap = (data.wallet && data.wallet.stamina_cap != null) ? data.wallet.stamina_cap : 3;

        var html = '<div class="flex items-center gap-2 mb-3">' +
            '<h2 class="text-xl font-black text-white flex-1">Siege camps</h2>' +
            '<button type="button" class="help-trigger" data-help="Siege camps are how you fight the PvE bosses. Tap a camp to engage its boss, then Attack to deal damage. Each attack costs 1 stamina and stamina refills each morning. Your damage comes from today tracked activity - bigger or more consistent effort deals bigger hits. Fill the boss HP bar to zero to conquer it and earn tokens." aria-label="How siege camps work"><i class="fa-solid fa-circle-question"></i></button>' +
            '</div>' +
            '<div class="flex items-center justify-between mb-4">' +
            '<p class="text-xs text-slate-400 font-semibold">Tap a camp to engage its boss and start fighting.</p>' +
            '<span class="text-xs font-black text-yellow-400 whitespace-nowrap ml-2"><i class="fa-solid fa-bolt mr-1"></i>' + stamina + '/' + cap + '</span>' +
            '</div>';

        html += '<div class="grid grid-cols-1 gap-3">';
        (data.campaigns || []).forEach(function (c) {
            var pct = hpPct(c.damage_dealt, c.total_hp);
            var stateLabel = c.conquered ? 'Conquered' : (c.engaged ? 'In battle' : 'Tap to start');
            var stateIcon = c.conquered ? 'fa-crown' : (c.engaged ? 'fa-bolt' : 'fa-play');
            var stateColor = c.conquered ? 'text-emerald-400' : (c.engaged ? 'text-red-400' : 'text-slate-500');
            var stateHelp = c.conquered
                ? 'This camp is fully conquered. New bosses will be revealed over time.'
                : (c.engaged
                    ? 'This boss is engaged and taking damage. Keep attacking (1 stamina each) until its HP reaches zero to claim the conquest reward.'
                    : 'No boss is engaged here yet. Tap the card to start a siege against the ' + esc(CAMPAIGN_LABEL[c.campaign] || c.campaign) + ' boss.');
            var bossName = (c.boss && c.boss.name) ? c.boss.name : (CAMPAIGN_LABEL[c.campaign] || c.label);
            var chip = vulnChip(c);
            var rightLine = c.conquered
                ? '<span class="text-emerald-300 font-bold"><i class="fa-solid fa-check mr-1"></i>Done</span>'
                : '<span class="text-slate-400 font-semibold">~' + money(c.est_damage_per_attack) + ' dmg/atk</span>';

            html += '<div class="bg-slate-800 border border-slate-600 rounded-[1.5rem] p-4 shadow-lg" data-campaign="' + esc(c.campaign) + '" role="button" tabindex="0" aria-label="' + esc(bossName) + '">' +
                '<div class="flex items-center gap-3">' +
                '<div class="w-12 h-12 rounded-2xl bg-slate-700 flex items-center justify-center text-xl"><i class="fa-solid ' + (CAMPAIGN_ICON[c.campaign] || 'fa-dragon') + ' text-red-400"></i></div>' +
                '<div class="flex-1 min-w-0">' +
                '<div class="flex items-center gap-2"><h3 class="font-black text-white truncate">' + esc(bossName) + '</h3>' +
                '<span class="text-xs font-black ' + stateColor + ' uppercase">' + stateLabel + '</span>' +
                '<button type="button" class="help-trigger" data-help="' + stateHelp + '" aria-label="About this campaign"><i class="fa-solid fa-circle-info"></i></button></div>' +
                '<div class="text-xs text-slate-400 font-semibold">' + esc(CAMPAIGN_LABEL[c.campaign] || c.campaign) + chip + '</div>' +
                '</div>' +
                '<i class="fa-solid ' + stateIcon + ' text-slate-500"></i>' +
                '</div>' +
                '<div class="mt-3 h-3 bg-slate-700 rounded-full overflow-hidden border border-slate-600">' +
                '<div class="h-full rounded-full ' + (c.conquered ? 'bg-emerald-500' : 'bg-red-500') + '" style="width:' + pct + '%"></div></div>' +
                '<div class="flex justify-between items-center text-xs mt-1">' +
                '<span class="text-slate-400 font-semibold">HP</span>' +
                '<span class="text-slate-300 font-bold">' + money(c.remaining_hp != null ? c.remaining_hp : (c.total_hp - c.damage_dealt)) + ' / ' + money(c.total_hp) + '</span>' +
                rightLine +
                '</div>' +
                '</div>';
        });
        html += '<p class="text-xs text-slate-400 font-semibold mt-4">Want to hit harder? <button type="button" onclick="window.loadShop && window.loadShop(); return false;" class="text-indigo-300 underline">Buy gear in the Shop</button> and <button type="button" onclick="window.loadLoadout && window.loadLoadout(); return false;" class="text-indigo-300 underline">equip it in the Loadout</button>.</p>';
        content.innerHTML = html;
        if (window.bindHelp) window.bindHelp(content);

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
        content.innerHTML = '<p class="text-slate-400">Engaging boss...</p>';
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
        var weaknesses = (boss.weaknesses || []).map(function (w) { return esc(CAMPAIGN_LABEL[w] || w); }).join(', ');
        var resistances = (boss.resistances || []).map(function (r) { return esc(CAMPAIGN_LABEL[r] || r); }).join(', ');
        var mech = boss.mechanics || {};
        var stamina = (data.wallet && data.wallet.stamina != null) ? data.wallet.stamina : '-';
        var est = data.est_damage_per_attack || 0;
        var chip = vulnChip({ vulnerability: data.vulnerability });
        var campLabel = CAMPAIGN_LABEL[data.campaign] || data.campaign;

        var mechNote = '';
        if (mech.heal_on_overage) mechNote += '<div class="text-xs text-red-300 font-semibold mt-1" data-help="This boss heals 500 HP when your logged calories go over your goal today. Keep calories at or under goal to stop the healing."><i class="fa-solid fa-triangle-exclamation mr-1"></i>Self-heals when calories over goal</div>';
        if (mech.front_load_water_noon) mechNote += '<div class="text-xs text-sky-300 font-semibold mt-1" data-help="Hydration damage you deal before noon is worth double. Log your water early in the day to hit this boss harder."><i class="fa-solid fa-droplet mr-1"></i>Front-loaded hydration deals 2x</div>';

        var html = '<div class="text-center mb-3">' +
            '<div class="w-20 h-20 mx-auto rounded-full bg-slate-800 border-4 border-red-500/40 flex items-center justify-center text-4xl mb-2"><i class="fa-solid ' + esc(boss.icon || 'fa-dragon') + ' text-red-400"></i></div>' +
            '<h3 class="text-2xl font-black text-white">' + esc(boss.name || '???') + '</h3>' +
            '<div class="text-xs text-slate-400 font-semibold mt-1">' + esc(campLabel) + ' siege boss</div>' +
            '</div>' +
            '<div class="h-4 bg-slate-700 rounded-full overflow-hidden border border-slate-600 mb-1">' +
            '<div class="h-full bg-red-500 rounded-full transition-all" style="width:' + pct + '%"></div></div>' +
            '<div class="flex justify-between items-center text-xs mb-3">' +
            '<span class="text-slate-400 font-semibold">' + esc(boss.slug || '') + chip + '</span>' +
            '<span class="text-slate-300 font-bold">' + money(Math.max(0, boss.hp_total - boss.damage_dealt)) + ' / ' + money(boss.hp_total) + '</span></div>';

        if (boss.conquered) {
            html += '<div class="bg-emerald-500/10 border border-emerald-500/40 rounded-2xl p-3 text-center text-emerald-300 font-black mb-3"><i class="fa-solid fa-crown mr-1"></i>CONQUERED</div>';
        }

        html += '<div class="bg-slate-800 border border-slate-600 rounded-2xl p-3 mb-3 text-xs text-slate-300 font-semibold space-y-2">' +
            '<div class="font-black text-sm text-white flex items-center gap-2"><i class="fa-solid fa-flag-checkered text-red-400"></i> How to win this siege</div>' +
            '<div class="flex items-start gap-2"><span class="badge-step">1</span><span>Build today power: log ' + esc(campLabel) + ' activity. Current base: <b class="text-white">' + money(data.today_base_damage) + '</b>.</span></div>' +
            '<div class="flex items-start gap-2"><span class="badge-step">2</span><span>Attack with stamina (you have <b class="text-white">' + stamina + '</b>). Each attack deals ~<b class="text-white">' + money(est) + '</b> damage.</span></div>' +
            '<div class="flex items-start gap-2"><span class="badge-step">3</span><span>Drop the HP bar to zero to conquer the boss and earn <b class="text-white">+150 tokens</b>.</span></div>' +
            '</div>';

        if (weaknesses) html += '<div class="text-xs text-red-300 font-semibold" data-help="Weak domains take 2x damage. Use this to your advantage."><i class="fa-solid fa-bullseye mr-1"></i>Weak: ' + weaknesses + '</div>';
        if (resistances) html += '<div class="text-xs text-slate-400 font-semibold" data-help="Resisted domains deal half damage. It may be best to spend stamina on another campaign while this persists."><i class="fa-solid fa-shield mr-1"></i>Resists: ' + resistances + '</div>';
        html += mechNote;

        html += '<div class="bg-slate-800 border border-slate-600 rounded-2xl p-3 mt-3 text-xs text-slate-300 font-semibold">' +
            'Attack power today: <b class="text-white">' + money(data.today_base_damage) + '</b> (base) &times; <b class="text-white">' + esc(data.gear_multiplier) + '</b> (gear) &times; <b class="text-white">' + roundMult(data.boss_multiplier) + '</b> (boss) = <b class="text-flamingo">~' + money(est) + '</b> per attack' +
            '<button type="button" class="help-trigger" data-help="Damage for each attack is today tracked base damage, multiplied by your equipped gear, then by any boss weakness or resistance. Log more of this activity and equip stronger gear to deal bigger hits." aria-label="Damage formula"><i class="fa-solid fa-circle-question ml-1"></i></button></div>';

        html += '<div class="flex flex-col gap-3 mt-4">';
        if (!boss.conquered) {
            if (!boss.slug) {
                html += '<button class="bg-red-500 text-white font-black py-3.5 rounded-2xl border-b-4 border-red-700 active:scale-95 transition-all" id="battle-engage">Engage this boss</button>';
            } else {
                html += '<button class="bg-red-500 text-white font-black py-3.5 rounded-2xl border-b-4 border-red-700 active:scale-95 transition-all" id="battle-attack"><i class="fa-solid fa-bolt mr-1"></i>Attack (1 stamina) &middot; ~' + money(est) + ' dmg</button>';
            }
        }
        html += '<button class="bg-slate-700 text-slate-200 font-black py-3 rounded-2xl border-b-4 border-slate-900 active:scale-95 transition-all" id="battle-back-list"><i class="fa-solid fa-arrow-left mr-1"></i>Back to campaigns</button>';
        html += '<div class="grid grid-cols-2 gap-2" id="battle-subnav">' +
            '<button class="bg-slate-800 text-slate-200 font-bold py-2.5 rounded-2xl border border-slate-600 active:scale-95 transition-all" id="battle-leaderboard"><i class="fa-solid fa-ranking-star mr-1"></i>Leaderboard</button>' +
            '<button class="bg-slate-800 text-slate-200 font-bold py-2.5 rounded-2xl border border-slate-600 active:scale-95 transition-all" id="battle-history"><i class="fa-solid fa-book-open mr-1"></i>Siege diary</button>' +
            '</div>';
        html += '</div>';

        content.innerHTML = html;
        if (window.bindHelp) window.bindHelp(content);

        var attackBtn = document.getElementById('battle-attack');
        if (attackBtn) attackBtn.addEventListener('click', function () { attack(data.campaign); });

        var engageBtn = document.getElementById('battle-engage');
        if (engageBtn) engageBtn.addEventListener('click', function () { engage(data.campaign); });

        document.getElementById('battle-back-list').addEventListener('click', window.loadBattle);
        var boardBtn = document.getElementById('battle-leaderboard');
        if (boardBtn) boardBtn.addEventListener('click', function () { openLeaderboard(data.campaign); });
        var diaryBtn = document.getElementById('battle-history');
        if (diaryBtn) diaryBtn.addEventListener('click', function () { openHistory(data.campaign); });
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
                if (window.refreshCampaignFocus) window.refreshCampaignFocus();
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
                if (window.refreshCampaignFocus) window.refreshCampaignFocus();
                openCampaign(campaign);
            })
            .catch(function () { alert('Network error while engaging.'); });
    }

    // ---- docs/17 #33: per-campaign siege leaderboard ----
    function openLeaderboard(campaign) {
        var content = document.getElementById('battle-content');
        if (!content) return;
        content.innerHTML = '<p class="text-slate-400">Loading siege leaderboard...</p>';
        fetch(LEADERBOARD_URL + encodeURIComponent(campaign) + '/', { credentials: 'same-origin' })
            .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
            .then(function (data) { renderLeaderboardSub(data); })
            .catch(function (err) {
                content.innerHTML = '<p class="text-slate-400">Could not load the leaderboard (error ' + esc(err) + ').</p>';
            });
    }

    function renderLeaderboardSub(data) {
        var content = document.getElementById('battle-content');
        if (!content) return;
        var campLabel = CAMPAIGN_LABEL[data.campaign] || data.label;
        var boss = data.boss || {};
        var html = '<div class="flex items-center gap-2 mb-3">' +
            '<h2 class="text-xl font-black text-white flex-1"><i class="fa-solid fa-ranking-star text-red-400 mr-2"></i>Siege leaderboard</h2>' +
            '</div>' +
            '<div class="bg-slate-800 border border-slate-600 rounded-2xl p-3 mb-3">' +
            '<div class="flex items-center gap-2">' +
            '<div class="w-9 h-9 rounded-xl bg-slate-700 flex items-center justify-center text-base"><i class="fa-solid ' + esc(boss.icon || 'fa-dragon') + ' text-red-400"></i></div>' +
            '<div class="flex-1 min-w-0"><div class="text-sm font-black text-white truncate">' + esc(boss.name || campLabel || 'This campaign') + '</div>' +
            '<div class="text-xs text-slate-400 font-semibold">Most boss damage among your friends &amp; flock.</div></div>' +
            '</div>' +
            (data.my_rank ? '<div class="text-xs text-slate-300 font-bold mt-2">You are <b class="text-white">#' + data.my_rank +
                '</b> with <b class="text-white">' + money(data.my_damage) + '</b> dmg dealt.</div>' : '') +
            '</div>';
        html += '<div class="league-board">';
        (data.leaderboard || []).forEach(function (row) {
            var medal = MEDALS[row.rank] || ('#' + row.rank);
            html += '<div class="league-row' + (row.is_you ? ' row-you' : '') + '">' +
                '<span class="league-rank">' + medal + '</span>' +
                avatarImg('league-avatar', row.avatar) +
                '<span class="league-name">' + esc(row.username) + (row.is_you ? ' (you)' : '') + '</span>' +
                '<span class="league-xp">' + money(row.damage) + ' dmg</span>' +
                '</div>';
        });
        html += '</div>';
        if (!(data.leaderboard || []).length) {
            html += '<p class="league-empty-hint"><i class="fa-solid fa-bullhorn"></i> No one has damaged this boss yet - engage it and deal the first hit!</p>';
        }
        html += '<div class="flex flex-col gap-3 mt-4">' +
            '<button class="bg-slate-700 text-slate-200 font-black py-3 rounded-2xl border-b-4 border-slate-900 active:scale-95 transition-all" id="battle-board-back"><i class="fa-solid fa-arrow-left mr-1"></i>Back to siege camp</button>' +
            '</div>';
        content.innerHTML = html;
        if (window.bindHelp) window.bindHelp(content);
        document.getElementById('battle-board-back').addEventListener('click', function () { openCampaign(data.campaign); });
    }

    // ---- docs/17 #34: siege kill timeline / diary ----
    function openHistory(campaign) {
        var content = document.getElementById('battle-content');
        if (!content) return;
        content.innerHTML = '<p class="text-slate-400">Opening the siege diary...</p>';
        fetch(HISTORY_URL + encodeURIComponent(campaign) + '/', { credentials: 'same-origin' })
            .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
            .then(function (data) { renderHistorySub(data); })
            .catch(function (err) {
                content.innerHTML = '<p class="text-slate-400">Could not load the siege diary (error ' + esc(err) + ').</p>';
            });
    }

    function renderHistorySub(data) {
        var content = document.getElementById('battle-content');
        if (!content) return;
        var campLabel = CAMPAIGN_LABEL[data.campaign] || data.label;
        var html = '<div class="flex items-center gap-2 mb-3">' +
            '<h2 class="text-xl font-black text-white flex-1"><i class="fa-solid fa-book-open text-red-400 mr-2"></i>Siege diary</h2>' +
            '</div>' +
            '<div class="text-xs text-slate-400 font-semibold mb-3">Your conquest &amp; halved-boss history for the ' + esc(campLabel) + ' campaign.</div>';
        var bosses = data.bosses || [];
        if (!bosses.length) {
            html += window.emptyStateHTML({
                icon: 'fa-book-open',
                title: 'No sieges yet',
                desc: 'Attack a boss in this campaign and your kill timeline will collect here.',
                hint: 'One stamina per attack in the ' + esc(campLabel) + ' campaign.'
            });
        }
        bosses.forEach(function (b) {
            var chips = '';
            if (b.conquered) {
                chips += '<span class="vuln-chip weak" aria-label="Conquered"><i class="fa-solid fa-crown mr-1"></i>Conquered</span>';
            }
            if (b.halved) {
                chips += '<span class="vuln-chip resist" aria-label="Halved"><i class="fa-solid fa-scissors mr-1"></i>Halved</span>';
            }
            html += '<div class="bg-slate-800 border border-slate-600 rounded-2xl p-3 mb-3">' +
                '<div class="flex items-center gap-2">' +
                '<div class="w-9 h-9 rounded-xl bg-slate-700 flex items-center justify-center text-base"><i class="fa-solid ' + esc(b.icon || 'fa-dragon') + ' text-red-400"></i></div>' +
                '<div class="flex-1 min-w-0"><div class="text-sm font-black text-white truncate">' + esc(b.name || '???') + '</div>' +
                '<div class="text-xs text-slate-400 font-semibold">' + money(b.total_damage) + ' dmg total</div></div>' +
                '<div class="flex flex-col items-end gap-1">' + chips + '</div>' +
                '</div>';
            html += '<div class="mt-2 border-t border-slate-700 pt-2 space-y-1">';
            (b.attacks || []).forEach(function (atk) {
                html += '<div class="flex items-center justify-between text-xs text-slate-300">' +
                    '<span class="font-semibold">' + esc(atk.date) + '</span>' +
                    '<span class="text-slate-400">-' + money(atk.total_damage) + ' dmg' +
                    (atk.tokens_won ? ' &middot; <span class="text-yellow-400">+' + atk.tokens_won + ' <i class="fa-solid fa-coins"></i></span>' : '') +
                    '</span></div>';
            });
            html += '</div></div>';
        });
        html += '<div class="flex flex-col gap-3 mt-4">' +
            '<button class="bg-slate-700 text-slate-200 font-black py-3 rounded-2xl border-b-4 border-slate-900 active:scale-95 transition-all" id="battle-history-back"><i class="fa-solid fa-arrow-left mr-1"></i>Back to siege camp</button>' +
            '</div>';
        content.innerHTML = html;
        if (window.bindHelp) window.bindHelp(content);
        document.getElementById('battle-history-back').addEventListener('click', function () { openCampaign(data.campaign); });
    }
})();
