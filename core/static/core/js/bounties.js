/**
 * Bounties & 1v1 Duels Controller (Roadmap Item N8)
 * Handles live rendering, tab switching, wagers, duel progress comparisons,
 * celebratory claims, and native haptic/audio integrations.
 */

let bountiesState = null;
let currentBountiesTab = 'active';

window.loadBountiesState = async function() {
    try {
        const res = await fetch('/bounties/state', { credentials: 'same-origin' });
        if (!res.ok) throw new Error('Failed to load bounties state');
        const json = await res.json();
        if (json.success) {
            bountiesState = json.data;
            renderBounties();
        }
    } catch (err) {
        console.error('Error loading bounties state:', err);
    }
};

window.loadBounties = function() {
    if (window.loadPvP) {
        return window.loadPvP('bounties');
    }

    if (window.closeModal) window.closeModal();
    if (window.AppRouter) window.AppRouter.navigate('pvp-view');

    const runLoad = async function() {
        const view = document.getElementById('pvp-view') || document.getElementById('bounties-view');
        if (!view) return;
        if (window.ensureSinglePanelVisible) {
            window.ensureSinglePanelVisible(view.id);
        } else {
            document.querySelectorAll('section').forEach(s => s.classList.add('hidden'));
            view.classList.remove('hidden');
        }
        if (typeof window.switchPvPMode === 'function') {
            window.switchPvPMode('bounties');
        } else {
            await window.loadBountiesState();
        }
    };

    if (typeof window.ensurePanelLoaded === 'function') {
        return window.ensurePanelLoaded('pvp-view').then(runLoad);
    } else {
        return runLoad();
    }
};

window.backToBountiesPlan = function() {
    if (typeof window.goBack === 'function') {
        window.goBack();
        return;
    }
    const view = document.getElementById('bounties-view') || document.getElementById('pvp-view');
    if (view) view.classList.add('hidden');
    if (window.ensureSinglePanelVisible) {
        window.ensureSinglePanelVisible('skill-tree');
    } else {
        const dash = document.getElementById('skill-tree');
        if (dash) dash.classList.remove('hidden');
    }
};

window.switchBountiesTab = function(tabName) {
    currentBountiesTab = tabName;
    document.querySelectorAll('.bounties-tab').forEach(b => {
        if (b.dataset.tab === tabName) {
            b.classList.add('active', 'text-white');
            b.classList.remove('text-slate-400');
        } else {
            b.classList.remove('active', 'text-white');
            b.classList.add('text-slate-400');
        }
    });
    renderBountiesTabContent();
};

function renderBounties() {
    if (!bountiesState) return;

    // 1. Update wallet ribbons
    const tokEl = document.getElementById('bounty-wallet-tokens');
    const scrEl = document.getElementById('bounty-wallet-scraps');
    const wonEl = document.getElementById('bounty-total-won');

    if (tokEl) tokEl.textContent = (bountiesState.user_balance?.tokens || 0).toLocaleString();
    if (scrEl) scrEl.textContent = (bountiesState.user_balance?.scraps || 0).toLocaleString();
    if (wonEl) wonEl.textContent = (bountiesState.stats?.total_won || 0).toLocaleString();

    // 2. Badges on tabs
    const actBadge = document.getElementById('bounty-badge-active');
    if (actBadge) {
        const count = bountiesState.active_bounties?.length || 0;
        actBadge.textContent = count;
        actBadge.classList.toggle('hidden', count === 0);
    }

    const duelBadge = document.getElementById('bounty-badge-duels');
    if (duelBadge) {
        const pending = bountiesState.direct_duels?.filter(d => d.is_receiver)?.length || 0;
        duelBadge.textContent = pending;
        duelBadge.classList.toggle('hidden', pending === 0);
    }

    renderBountiesTabContent();
}

function renderBountiesTabContent() {
    const container = document.getElementById('bounties-content');
    if (!container || !bountiesState) return;

    if (currentBountiesTab === 'active') {
        renderActiveBounties(container);
    } else if (currentBountiesTab === 'open') {
        renderOpenBoard(container);
    } else if (currentBountiesTab === 'duels') {
        renderDirectDuels(container);
    } else if (currentBountiesTab === 'vault') {
        renderBountiesVault(container);
    }
}

function formatCountdown(seconds) {
    if (seconds <= 0) return 'Expired';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (hrs > 24) {
        const days = Math.floor(hrs / 24);
        return `${days}d ${hrs % 24}h remaining`;
    }
    return `${hrs}h ${mins}m remaining`;
}

function renderActiveBounties(container) {
    const items = bountiesState.active_bounties || [];
    if (items.length === 0) {
        container.innerHTML = `
            <div class="bg-slate-800/60 border border-dashed border-slate-700 rounded-3xl p-8 text-center">
                <div class="w-16 h-16 mx-auto mb-3 rounded-full bg-slate-700/60 flex items-center justify-center text-3xl text-pink-400">
                    <i class="fa-solid fa-crosshairs"></i>
                </div>
                <h4 class="text-base font-black text-white mb-1">No Active Bounties</h4>
                <p class="text-xs font-semibold text-slate-400 mb-4 max-w-xs mx-auto">Pick a contract from the Open Board or challenge a friend to a 1v1 duel!</p>
                <div class="flex gap-2 justify-center">
                    <button class="bg-pink-600 hover:bg-pink-500 text-white font-bold text-xs px-4 py-2.5 rounded-xl transition-all shadow" onclick="switchBountiesTab('open')">
                        Browse Board
                    </button>
                    <button class="bg-slate-700 hover:bg-slate-600 text-white font-bold text-xs px-4 py-2.5 rounded-xl transition-all" onclick="openCreateBountyModal()">
                        Create Solo Contract
                    </button>
                </div>
            </div>
        `;
        return;
    }

    container.innerHTML = items.map(b => {
        const cfg = b.target_config || {};
        const isDuel = b.type === 'duel';
        const isComplete = b.is_completed;
        const canClaim = b.can_claim;
        const timerText = formatCountdown(b.time_left_seconds);

        if (isDuel && b.opponent) {
            // 1v1 Duel VS Card
            const myPct = b.progress_pct;
            const oppPct = b.opponent.progress_pct;
            const leading = b.current_value > b.opponent.current_value;
            const tied = b.current_value === b.opponent.current_value;

            return `
                <div class="bg-slate-800/90 border border-slate-700/90 rounded-3xl p-4 shadow-xl relative overflow-hidden transition-all hover:border-pink-500/50">
                    <div class="flex items-center justify-between gap-2 mb-3">
                        <div class="flex items-center gap-2">
                            <span class="bg-pink-500/20 text-pink-400 border border-pink-500/30 text-[10px] font-black uppercase px-2 py-0.5 rounded-md">
                                ⚔️ 1v1 Duel
                            </span>
                            <span class="text-xs font-bold text-slate-400 flex items-center gap-1">
                                <i class="fa-regular fa-clock"></i> ${timerText}
                            </span>
                        </div>
                        <div class="text-xs font-black text-amber-400 flex items-center gap-1">
                            <i class="fa-solid fa-coins"></i> Pot: ${b.total_pot_tokens} Tokens
                        </div>
                    </div>

                    <h3 class="text-base font-black text-white mb-3">${b.title}</h3>

                    <!-- Head to Head VS Grid -->
                    <div class="grid grid-cols-2 gap-3 bg-slate-900/80 rounded-2xl p-3 border border-slate-800 mb-3">
                        <!-- You -->
                        <div class="text-left border-r border-slate-800 pr-2">
                            <div class="text-[11px] font-black uppercase text-pink-400 flex items-center gap-1">
                                <span>YOU</span> ${leading && !tied ? '👑' : ''}
                            </div>
                            <div class="text-lg font-black text-white leading-tight mt-0.5">
                                ${b.current_value.toLocaleString()} <span class="text-[10px] text-slate-400">${cfg.unit || ''}</span>
                            </div>
                            <div class="text-[10px] font-bold text-slate-400">${myPct}% of goal</div>
                        </div>

                        <!-- Opponent -->
                        <div class="text-right pl-2">
                            <div class="text-[11px] font-black uppercase text-blue-400 flex items-center justify-end gap-1">
                                ${!leading && !tied ? '👑' : ''} <span>@${b.opponent.username}</span>
                            </div>
                            <div class="text-lg font-black text-white leading-tight mt-0.5">
                                ${b.opponent.current_value.toLocaleString()} <span class="text-[10px] text-slate-400">${cfg.unit || ''}</span>
                            </div>
                            <div class="text-[10px] font-bold text-slate-400">${oppPct}% of goal</div>
                        </div>
                    </div>

                    <!-- Duel Progress Bar Comparison -->
                    <div class="space-y-1.5 mb-3">
                        <div class="w-full bg-slate-900 rounded-full h-3.5 p-0.5 border border-slate-700/60 overflow-hidden flex">
                            <div class="bg-gradient-to-r from-pink-500 to-rose-400 h-full rounded-full transition-all duration-500 shadow-[0_0_12px_rgba(244,63,94,0.6)]" style="width: ${Math.min(100, myPct)}%;"></div>
                        </div>
                    </div>

                    <!-- Action buttons -->
                    ${canClaim ? `
                        <button class="w-full bg-gradient-to-r from-yellow-500 to-amber-400 hover:from-yellow-400 hover:to-amber-300 text-slate-950 font-black text-sm py-3 rounded-2xl border-b-4 border-amber-700 active:border-b-0 active:translate-y-1 transition-all shadow-xl flex items-center justify-center gap-2 animate-bounce" onclick="claimBounty(${b.id})">
                            <i class="fa-solid fa-trophy"></i> Claim ${b.total_pot_tokens} Tokens + ${b.reward_xp} XP!
                        </button>
                    ` : `
                        <div class="flex items-center justify-between text-xs font-bold text-slate-400 pt-1">
                            <span>Target: ${b.target_value.toLocaleString()} ${cfg.unit || ''}</span>
                            <span class="text-pink-400">${myPct >= 100 ? '🎯 Goal Met!' : `${(b.target_value - b.current_value).toLocaleString()} ${cfg.unit || ''} to go`}</span>
                        </div>
                    `}
                </div>
            `;
        }

        // Solo or Open Active Contract
        return `
            <div class="bg-slate-800/90 border border-slate-700/90 rounded-3xl p-4 shadow-xl relative overflow-hidden transition-all hover:border-pink-500/50">
                <div class="flex items-center justify-between gap-2 mb-2">
                    <div class="flex items-center gap-2">
                        <span class="bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[10px] font-black uppercase px-2 py-0.5 rounded-md">
                            ${b.type === 'solo' ? '⚡ Solo Contract' : '📜 Board Quest'}
                        </span>
                        <span class="text-xs font-bold text-slate-400 flex items-center gap-1">
                            <i class="fa-regular fa-clock"></i> ${timerText}
                        </span>
                    </div>
                    <div class="text-xs font-black text-amber-400 flex items-center gap-1">
                        <i class="fa-solid fa-coins"></i> +${b.total_pot_tokens} Tokens
                    </div>
                </div>

                <h3 class="text-base font-black text-white mb-1">${b.title}</h3>
                <p class="text-xs font-semibold text-slate-400 mb-3">${b.description || ''}</p>

                <!-- Progress Ring / Bar -->
                <div class="bg-slate-900/80 rounded-2xl p-3 border border-slate-800 mb-3">
                    <div class="flex justify-between items-center text-xs font-black mb-1.5">
                        <span class="text-slate-300">${b.current_value.toLocaleString()} / ${b.target_value.toLocaleString()} ${cfg.unit || ''}</span>
                        <span class="text-pink-400">${b.progress_pct}%</span>
                    </div>
                    <div class="w-full bg-slate-800 rounded-full h-3 p-0.5 border border-slate-700 overflow-hidden">
                        <div class="bg-gradient-to-r from-pink-500 to-rose-400 h-full rounded-full transition-all duration-500 shadow-[0_0_10px_rgba(244,63,94,0.5)]" style="width: ${Math.min(100, b.progress_pct)}%;"></div>
                    </div>
                </div>

                <!-- Claim or Status -->
                ${canClaim ? `
                    <button class="w-full bg-gradient-to-r from-yellow-500 to-amber-400 hover:from-yellow-400 hover:to-amber-300 text-slate-950 font-black text-sm py-3 rounded-2xl border-b-4 border-amber-700 active:border-b-0 active:translate-y-1 transition-all shadow-xl flex items-center justify-center gap-2 animate-bounce" onclick="claimBounty(${b.id})">
                        <i class="fa-solid fa-gift"></i> Claim ${b.total_pot_tokens} Tokens &amp; ${b.reward_xp} XP!
                    </button>
                ` : `
                    <div class="flex items-center justify-between text-xs font-bold text-slate-400">
                        <span class="flex items-center gap-1.5 text-amber-400"><i class="fa-solid fa-star"></i> +${b.reward_xp} XP</span>
                        <span class="text-slate-400">${b.progress_pct >= 100 ? '✅ Target Met!' : 'Keep logging habits!'}</span>
                    </div>
                `}
            </div>
        `;
    }).join('');
}

function renderOpenBoard(container) {
    const items = bountiesState.open_board || [];
    if (items.length === 0) {
        container.innerHTML = `
            <div class="bg-slate-800/60 border border-dashed border-slate-700 rounded-3xl p-8 text-center">
                <div class="w-16 h-16 mx-auto mb-3 rounded-full bg-slate-700/60 flex items-center justify-center text-3xl text-slate-400">
                    <i class="fa-solid fa-scroll"></i>
                </div>
                <h4 class="text-base font-black text-white mb-1">Open Board Empty</h4>
                <p class="text-xs font-semibold text-slate-400 mb-4 max-w-xs mx-auto">No public bounties currently waiting. Be the first to post one!</p>
                <button class="bg-pink-600 hover:bg-pink-500 text-white font-bold text-xs px-4 py-2.5 rounded-xl transition-all shadow" onclick="openCreateBountyModal()">
                    Post a Bounty
                </button>
            </div>
        `;
        return;
    }

    container.innerHTML = items.map(b => {
        const cfg = b.target_config || {};
        const isSystem = b.is_system;

        return `
            <div class="bg-slate-800/90 border border-slate-700/90 rounded-3xl p-4 shadow-xl relative overflow-hidden transition-all hover:border-pink-500/50">
                <div class="flex items-center justify-between gap-2 mb-2">
                    <div class="flex items-center gap-2">
                        <span class="${isSystem ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30' : 'bg-pink-500/20 text-pink-300 border-pink-500/30'} border text-[10px] font-black uppercase px-2 py-0.5 rounded-md">
                            ${isSystem ? '🦩 Daily Guild Quest' : '📜 Community Bounty'}
                        </span>
                        <span class="text-xs font-bold text-slate-400">
                            ⏱️ ${b.duration_hours}h Window
                        </span>
                    </div>
                    <div class="text-xs font-black text-amber-400 flex items-center gap-1">
                        <i class="fa-solid fa-coins"></i> +${b.wager_tokens + b.bonus_tokens} Tokens
                    </div>
                </div>

                <h3 class="text-base font-black text-white mb-1">${b.title}</h3>
                <p class="text-xs font-semibold text-slate-300 mb-3">${b.description || ''}</p>

                <div class="bg-slate-900/80 rounded-2xl p-3 border border-slate-800 flex items-center justify-between mb-3">
                    <div class="text-xs font-bold text-slate-300">
                        Goal: <span class="text-white font-extrabold">${b.target_value.toLocaleString()} ${cfg.unit || ''}</span>
                    </div>
                    <div class="flex items-center gap-2 text-xs font-bold">
                        <span class="text-amber-400"><i class="fa-solid fa-star"></i> +${b.reward_xp} XP</span>
                        ${b.wager_tokens > 0 ? `<span class="text-rose-400">Wager: ${b.wager_tokens}🪙</span>` : '<span class="text-emerald-400">Free Entry</span>'}
                    </div>
                </div>

                <button class="w-full bg-gradient-to-r from-pink-500 to-rose-500 hover:from-pink-400 hover:to-rose-400 text-white font-black text-xs py-3 rounded-2xl border-b-4 border-pink-800 active:border-b-0 active:translate-y-1 transition-all shadow-lg flex items-center justify-center gap-2" onclick="acceptBounty(${b.id})">
                    <i class="fa-solid fa-handshake"></i> Accept Contract
                </button>
            </div>
        `;
    }).join('');
}

function renderDirectDuels(container) {
    const items = bountiesState.direct_duels || [];
    if (items.length === 0) {
        container.innerHTML = `
            <div class="bg-slate-800/60 border border-dashed border-slate-700 rounded-3xl p-8 text-center">
                <div class="w-16 h-16 mx-auto mb-3 rounded-full bg-slate-700/60 flex items-center justify-center text-3xl text-blue-400">
                    <i class="fa-solid fa-handshake-angle"></i>
                </div>
                <h4 class="text-base font-black text-white mb-1">No Pending Duels</h4>
                <p class="text-xs font-semibold text-slate-400 mb-4 max-w-xs mx-auto">Challenge your friends or flock mates to a 1v1 fitness duel with tokens staked in escrow!</p>
                <button class="bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs px-4 py-2.5 rounded-xl transition-all shadow" onclick="openCreateBountyModal('duel')">
                    ⚔️ Challenge a Friend
                </button>
            </div>
        `;
        return;
    }

    container.innerHTML = items.map(d => {
        const cfg = d.target_config || {};

        return `
            <div class="bg-slate-800/90 border border-slate-700/90 rounded-3xl p-4 shadow-xl relative overflow-hidden transition-all">
                <div class="flex items-center justify-between gap-2 mb-2">
                    <span class="bg-blue-500/20 text-blue-300 border border-blue-500/30 text-[10px] font-black uppercase px-2 py-0.5 rounded-md">
                        ⚔️ 1v1 Duel Invite
                    </span>
                    <span class="text-xs font-black text-amber-400 flex items-center gap-1">
                        <i class="fa-solid fa-coins"></i> ${(d.wager_tokens * 2) + d.bonus_tokens} Token Pot
                    </span>
                </div>

                <h3 class="text-base font-black text-white mb-1">${d.title}</h3>
                <p class="text-xs font-semibold text-slate-300 mb-3">${d.description || ''}</p>

                <div class="bg-slate-900/80 rounded-2xl p-3 border border-slate-800 space-y-1 text-xs mb-3">
                    <div class="flex justify-between text-slate-400 font-bold">
                        <span>Challenger: <strong class="text-white">@${d.creator}</strong></span>
                        <span>Opponent: <strong class="text-white">@${d.opponent}</strong></span>
                    </div>
                    <div class="flex justify-between text-slate-400 font-bold pt-1 border-t border-slate-800">
                        <span>Goal: <strong class="text-pink-400">${d.target_value.toLocaleString()} ${cfg.unit || ''}</strong></span>
                        <span>Window: <strong class="text-white">${d.duration_hours}h</strong></span>
                    </div>
                </div>

                ${d.is_receiver ? `
                    <div class="grid grid-cols-2 gap-2">
                        <button class="bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 text-white font-black text-xs py-3 rounded-2xl border-b-4 border-emerald-800 active:border-b-0 active:translate-y-1 transition-all shadow" onclick="acceptBounty(${d.id})">
                            ⚔️ Accept Duel (${d.wager_tokens}🪙)
                        </button>
                        <button class="bg-slate-700 hover:bg-slate-600 text-slate-300 font-bold text-xs py-3 rounded-2xl border-b-4 border-slate-800 active:border-b-0 active:translate-y-1 transition-all" onclick="cancelBounty(${d.id})">
                            Decline
                        </button>
                    </div>
                ` : `
                    <div class="flex items-center justify-between gap-2">
                        <span class="text-xs font-bold text-amber-400">⏳ Waiting for @${d.opponent} to accept...</span>
                        <button class="text-rose-400 hover:text-rose-300 text-xs font-bold px-3 py-1.5 rounded-xl border border-rose-500/30 hover:bg-rose-500/10" onclick="cancelBounty(${d.id})">
                            Cancel &amp; Refund
                        </button>
                    </div>
                `}
            </div>
        `;
    }).join('');
}

function renderBountiesVault(container) {
    const items = bountiesState.history || [];
    if (items.length === 0) {
        container.innerHTML = `
            <div class="bg-slate-800/60 border border-dashed border-slate-700 rounded-3xl p-8 text-center">
                <div class="w-16 h-16 mx-auto mb-3 rounded-full bg-slate-700/60 flex items-center justify-center text-3xl text-slate-400">
                    <i class="fa-solid fa-box-archive"></i>
                </div>
                <h4 class="text-base font-black text-white mb-1">Vault Empty</h4>
                <p class="text-xs font-semibold text-slate-400 max-w-xs mx-auto">Crush bounties and claim your rewards to build up your victory hall of fame!</p>
            </div>
        `;
        return;
    }

    container.innerHTML = items.map(h => {
        return `
            <div class="bg-slate-800/80 border border-slate-700/80 rounded-2xl p-3.5 flex items-center justify-between shadow-sm">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 text-lg">
                        <i class="fa-solid fa-check-circle"></i>
                    </div>
                    <div>
                        <h4 class="text-sm font-black text-white leading-tight">${h.title}</h4>
                        <div class="text-[11px] font-semibold text-slate-400 mt-0.5">
                            Logged: ${h.current_value.toLocaleString()} · ${h.is_winner ? '🏆 Winner' : '✅ Completed'}
                        </div>
                    </div>
                </div>

                <div class="text-right">
                    <div class="text-xs font-black text-amber-400">+${h.tokens_won} Tokens</div>
                    <div class="text-[10px] font-bold text-slate-400">+${h.reward_xp} XP</div>
                </div>
            </div>
        `;
    }).join('');
}

// -------------------------------------------------------------------------
// Action Handlers
// -------------------------------------------------------------------------

window.acceptBounty = async function(bountyId) {
    try {
        if (window.FlamingoAudio) window.FlamingoAudio.playLevelUp();
        if (window.FlamingoNative && window.FlamingoNative.haptic) window.FlamingoNative.haptic('medium');

        const res = await fetch(`/bounties/${bountyId}/accept`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '',
            },
        });
        const json = await res.json();
        if (json.success) {
            await window.loadBounties();
            window.switchBountiesTab('active');
        } else {
            alert(json.error || 'Failed to accept bounty');
        }
    } catch (err) {
        console.error('Error accepting bounty:', err);
    }
};

window.cancelBounty = async function(bountyId) {
    if (!confirm('Are you sure you want to cancel this bounty? Your escrowed wagers will be refunded.')) return;
    try {
        const res = await fetch(`/bounties/${bountyId}/cancel`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '',
            },
        });
        const json = await res.json();
        if (json.success) {
            await window.loadBounties();
        } else {
            alert(json.error || 'Failed to cancel bounty');
        }
    } catch (err) {
        console.error('Error cancelling bounty:', err);
    }
};

window.claimBounty = async function(bountyId) {
    try {
        const res = await fetch(`/bounties/${bountyId}/claim`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '',
            },
        });
        const json = await res.json();
        if (json.success) {
            const reward = json.reward;

            // Trigger sound effects and confetti!
            if (window.FlamingoAudio) window.FlamingoAudio.playBadgeUnlock();
            if (window.FlamingoNative && window.FlamingoNative.haptic) window.FlamingoNative.haptic('heavy');
            if (typeof confetti === 'function') {
                confetti({
                    particleCount: 80,
                    spread: 70,
                    origin: { y: 0.6 }
                });
            }

            // Open celebratory modal
            const cModal = document.getElementById('celebrationModal');
            if (cModal) {
                const tagEl = document.getElementById('celebration-tag');
                const titleEl = document.getElementById('celebration-title');
                const descEl = document.getElementById('celebration-desc');
                const tokEl = document.getElementById('celebration-reward-tokens');

                if (tagEl) tagEl.textContent = '🎯 BOUNTY CRUSHED!';
                if (titleEl) titleEl.textContent = reward.title || 'Victory Achieved!';
                if (descEl) descEl.textContent = `You claimed your reward payout: +${reward.tokens_awarded} Tokens and +${reward.xp_awarded} XP!`;
                if (tokEl) tokEl.innerHTML = `<i class="fa-solid fa-coins"></i> <span>+${reward.tokens_awarded} Tokens &amp; +${reward.xp_awarded} XP</span>`;

                cModal.classList.add('show-modal');
            }

            await window.loadBounties();
        } else {
            alert(json.error || 'Failed to claim reward');
        }
    } catch (err) {
        console.error('Error claiming bounty reward:', err);
    }
};

// -------------------------------------------------------------------------
// Modal & Form Handlers
// -------------------------------------------------------------------------

window.openCreateBountyModal = function(defaultType = 'solo') {
    const modal = document.getElementById('createBountyModal');
    if (modal) {
        modal.classList.add('show-modal');
        selectBountyType(defaultType);
        onTargetTypeChange();
    }
};

window.closeCreateBountyModal = function() {
    const modal = document.getElementById('createBountyModal');
    if (modal) modal.classList.remove('show-modal');
};

window.selectBountyType = function(type) {
    document.querySelectorAll('.bounty-type-btn').forEach(b => {
        if (b.dataset.type === type) {
            b.className = 'bounty-type-btn active bg-pink-600 text-white font-black text-xs py-2.5 rounded-xl border border-pink-500 text-center transition-all shadow';
        } else {
            b.className = 'bounty-type-btn bg-slate-800 text-slate-300 font-black text-xs py-2.5 rounded-xl border border-slate-700 text-center transition-all hover:bg-slate-700';
        }
    });

    const oppWrap = document.getElementById('duel-opponent-wrap');
    if (oppWrap) {
        oppWrap.classList.toggle('hidden', type !== 'duel');
    }
};

window.selectDuration = function(hours) {
    document.getElementById('bounty-duration').value = hours;
    document.querySelectorAll('.duration-btn').forEach(b => {
        if (parseInt(b.dataset.hours, 10) === hours) {
            b.className = 'duration-btn active bg-pink-600 text-white font-bold text-xs py-2 rounded-xl border border-pink-500 shadow';
        } else {
            b.className = 'duration-btn bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs py-2 rounded-xl border border-slate-700';
        }
    });
};

window.onTargetTypeChange = function() {
    const select = document.getElementById('bounty-target-type');
    const unitSpan = document.getElementById('bounty-target-unit');
    const valInput = document.getElementById('bounty-target-value');

    const type = select?.value || 'steps';
    const defaults = {
        steps: { unit: 'steps', val: 10000 },
        strength_volume: { unit: 'lbs volume', val: 15000 },
        cardio_minutes: { unit: 'minutes', val: 30 },
        water_ml: { unit: 'ml water', val: 2500 },
        protein_g: { unit: 'grams protein', val: 140 },
        calories_burned: { unit: 'active kcal', val: 500 },
        sleep_hours: { unit: 'hours sleep', val: 8.0 },
    };

    const d = defaults[type] || { unit: 'units', val: 100 };
    if (unitSpan) unitSpan.textContent = d.unit;
    if (valInput && (!valInput.value || valInput.value === '0')) valInput.value = d.val;
};

window.submitCreateBounty = async function(e) {
    e.preventDefault();
    const activeTypeBtn = document.querySelector('.bounty-type-btn.active');
    const bountyType = activeTypeBtn?.dataset.type || 'solo';
    const targetType = document.getElementById('bounty-target-type')?.value || 'steps';
    const targetValue = parseFloat(document.getElementById('bounty-target-value')?.value || 0);
    const durationHours = parseInt(document.getElementById('bounty-duration')?.value || 24, 10);
    const wagerTokens = parseInt(document.getElementById('bounty-wager-tokens')?.value || 0, 10);
    const wagerScraps = parseInt(document.getElementById('bounty-wager-scraps')?.value || 0, 10);
    const opponentUsername = document.getElementById('bounty-opponent')?.value || '';

    const btn = document.getElementById('bounty-submit-btn');
    if (btn) btn.disabled = true;

    try {
        const res = await fetch('/bounties/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '',
            },
            body: JSON.stringify({
                bounty_type: bountyType,
                target_type: targetType,
                target_value: targetValue,
                duration_hours: durationHours,
                wager_tokens: wagerTokens,
                wager_scraps: wagerScraps,
                opponent_username: opponentUsername,
            }),
        });
        const json = await res.json();
        if (json.success) {
            closeCreateBountyModal();
            if (window.FlamingoAudio) window.FlamingoAudio.playXpGain();
            await window.loadBounties();
            window.switchBountiesTab(bountyType === 'duel' ? 'duels' : 'active');
        } else {
            alert(json.error || 'Failed to create bounty');
        }
    } catch (err) {
        console.error('Error submitting bounty:', err);
    } finally {
        if (btn) btn.disabled = false;
    }
};

// Auto-load if rendered in active panel
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('bounties-view')) {
        window.loadBounties();
    }
});
