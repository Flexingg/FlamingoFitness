/* ============================================================
   Leagues / Challenges / Flock controller (Phase 8, docs/13).
   Opens from the "Leagues" bottom-nav tab; three sub-tabs:
   Board (GET /api/v1/leagues/), Challenge (GET /api/v1/challenges/),
   Flock (GET /api/v1/social/). All POSTs send X-CSRFToken from the
   meta tag (docs/08). Model: badges.js controller contract.
   ============================================================ */
(function () {
    'use strict';

    var LEAGUES_URL = '/api/v1/leagues/';
    var CHALLENGES_URL = '/api/v1/challenges/';
    var SOCIAL_URL = '/api/v1/social/';
    var currentTab = 'leaderboard';
    var lastSocial = null;
    var DEFAULT_AVATAR = 'https://api.dicebear.com/7.x/avataaars/svg?seed=Flamingo';

    // Blank/empty avatars fall back to the cartoon default; onerror guards
    // against a broken image leaving an ugly empty circle.
    function srcFor(a) {
        return (a && a.trim()) ? a : DEFAULT_AVATAR;
    }
    function avatarImg(className, a) {
        return '<img class="' + className + '" src="' + esc(srcFor(a)) +
            '" alt="" onerror="this.onerror=null;this.src=\'' + DEFAULT_AVATAR + '\';">';
    }


    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function csrfToken() {
        var m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.getAttribute('content') : '';
    }

    function postJson(url, body) {
        return fetch(url, {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify(body || {})
        }).then(function (res) {
            return res.json().catch(function () { return {}; }).then(function (data) {
                if (!res.ok) {
                    throw { status: res.status, message: (data && data.error) || ('Error ' + res.status) };
                }
                return data;
            });
        });
    }

    function setContent(html) {
        var content = document.getElementById('leagues-content');
        if (content) content.innerHTML = html;
        return content;
    }

    function tabButton(tab) {
        var buttons = document.querySelectorAll('#leagues-tabs .leagues-tab');
        for (var i = 0; i < buttons.length; i++) {
            buttons[i].classList.toggle('active', buttons[i].getAttribute('data-tab') === tab);
        }
    }

    function socialError(err) {
        var msg = (err && err.message) ? err.message : 'Something went wrong.';
        var hint = document.createElement('div');
        hint.className = 'social-toast';
        hint.textContent = msg;
        var view = document.getElementById('leagues-view');
        if (view) {
            view.appendChild(hint);
            setTimeout(function () { hint.remove(); }, 2500);
        }
    }

    // ---- Generic friend picker (also used by flock invites) ----
    window.closeFriendPicker = function () {
        var modal = document.getElementById('friendPickerModal');
        if (modal) modal.classList.remove('show-modal');
    };

    /* opts: { title, friends, allowClear, onPick(friendOrNull) } */
    window.openFriendPicker = function (opts) {
        var modal = document.getElementById('friendPickerModal');
        var title = document.getElementById('friend-picker-title');
        var list = document.getElementById('friend-picker-list');
        if (!modal || !list) return;
        if (title) title.textContent = (opts && opts.title) || 'Pick a friend';
        list.innerHTML = '';
        var friends = (opts && opts.friends) || [];
        if (!friends.length) {
            list.innerHTML = '<p class="empty-desc">No friends yet - find some in the Flock tab!</p>';
        }
        if (opts && opts.allowClear) {
            var clear = document.createElement('button');
            clear.className = 'friend-picker-row friend-picker-clear';
            clear.innerHTML = '<i class="fa-solid fa-user-minus"></i> Un-staff';
            clear.addEventListener('click', function () {
                window.closeFriendPicker();
                if (opts.onPick) opts.onPick(null);
            });
            list.appendChild(clear);
        }
        friends.forEach(function (friend) {
            var row = document.createElement('button');
            row.className = 'friend-picker-row';
            row.innerHTML =
                avatarImg('friend-avatar', friend.avatar) +
                '<span class="friend-name">' + esc(friend.username) + '</span>' +
                (friend.weekly_xp != null ? '<span class="friend-xp">' + friend.weekly_xp + ' XP</span>' : '');
            row.addEventListener('click', function () {
                window.closeFriendPicker();
                if (opts.onPick) opts.onPick(friend);
            });
            list.appendChild(row);
        });
        modal.classList.add('show-modal');
    };


    // ---- Panel open / close / tabs ----
    window.backToLeaguesPlan = function () {
        var view = document.getElementById('leagues-view');
        if (view) view.classList.add('hidden');
        // Single-panel navigation: hide ALL panels, then show only the skill tree.
        window.ensureSinglePanelVisible('skill-tree');
    };

    window.loadLeagues = function () {
        console.log('[leagues] loadLeagues start');
        if (window.closeModal) window.closeModal();
        var view = document.getElementById('leagues-view');
        if (!view) { console.warn('[leagues] leagues-view not found, aborting'); return; }
        // Single-panel navigation: hide ALL panels, then show only leagues.
        window.ensureSinglePanelVisible('leagues-view');
        window.switchLeaguesTab(currentTab || 'leaderboard');
    };

    window.switchLeaguesTab = function (tab) {
        currentTab = tab;
        tabButton(tab);
        if (tab === 'leaderboard') {
            setContent('<p class="loading-hint"><i class="fa-solid fa-spinner fa-spin"></i> Loading league...</p>');
            fetch(LEAGUES_URL, { credentials: 'same-origin' })
                .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
                .then(renderLeaderboard)
                .catch(function (err) {
                    setContent('<p class="error-hint">Could not load leagues (error ' + err + ').</p>');
                });
        } else if (tab === 'challenges') {
            setContent('<p class="loading-hint"><i class="fa-solid fa-spinner fa-spin"></i> Loading challenge...</p>');
            fetch(CHALLENGES_URL, { credentials: 'same-origin' })
                .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
                .then(renderChallenges)
                .catch(function (err) {
                    setContent('<p class="error-hint">Could not load challenges (error ' + err + ').</p>');
                });
        } else if (tab === 'flock') {
            setContent('<p class="loading-hint"><i class="fa-solid fa-spinner fa-spin"></i> Loading flock...</p>');
            fetchSocial();
        }
    };

    function fetchSocial(q) {
        var url = SOCIAL_URL + (q ? '?q=' + encodeURIComponent(q) : '');
        return fetch(url, { credentials: 'same-origin' })
            .then(function (res) { return res.ok ? res.json() : Promise.reject(res.status); })
            .then(function (data) { lastSocial = data; renderFlock(data, q); return data; })
            .catch(function (err) {
                setContent('<p class="error-hint">Could not load your flock (error ' + err + ').</p>');
            });
    }

    // ---- Leaderboard (GET /api/v1/leagues/) ----
    var MEDALS = { 1: '\uD83E\uDD47', 2: '\uD83E\uDD48', 3: '\uD83E\uDD49' };

    function tierChip(tier) {
        return '<span class="tier-chip tier-' + esc(tier) + '">' +
            esc(String(tier).replace('_', ' ')) + '</span>';
    }

    function renderLeaderboard(data) {
        var html = '';
        var week = data.week || {};
        html += '<div class="league-week-card">' +
            '<div class="league-week-title"><i class="fa-solid fa-shield-halved"></i> Weekly League</div>' +
            '<div class="league-week-range">' + esc(week.week_start) + ' \u2192 ' + esc(week.week_end) +
            ' \u00b7 <strong>' + (week.days_left || 0) + ' day(s) left</strong></div>' +
            '<div class="league-week-me">Your tier: ' + tierChip(data.my_tier) +
            (data.my_rank ? ' \u00b7 Rank <strong>#' + data.my_rank + '</strong>' : '') + '</div>' +
            '</div>';

        html += '<div class="league-board">';
        (data.leaderboard || []).forEach(function (row) {
            var medal = MEDALS[row.rank] || ('#' + row.rank);
            html += '<div class="league-row' + (row.is_you ? ' row-you' : '') + '">' +
                '<span class="league-rank">' + medal + '</span>' +
                avatarImg('league-avatar', row.avatar) +
                '<span class="league-name">' + esc(row.username) + (row.is_you ? ' (you)' : '') + '</span>' +
                tierChip(row.tier) +
                '<span class="league-xp">' + row.xp + ' XP</span>' +
                '</div>';
        });
        html += '</div>';

        if (!data.my_rank) {
            html += '<p class="league-empty-hint"><i class="fa-solid fa-bullhorn"></i> ' +
                'No XP yet this week - train to claim a spot on the board!</p>';
        }

        var history = data.history || [];
        if (history.length) {
            html += '<div class="base-section-title">Past weeks</div>';
            history.forEach(function (h) {
                var rewardBits = [];
                if (h.reward && h.reward.tokens) rewardBits.push(h.reward.tokens + ' <i class="fa-solid fa-coins"></i>');
                html += '<div class="league-history-card">' +
                    '<span class="league-history-week">' + esc(h.week_start) + '</span>' +
                    '<span class="league-history-rank">#' + h.rank + '</span>' +
                    tierChip(h.tier) +
                    '<span class="league-history-xp">' + h.xp + ' XP</span>' +
                    (rewardBits.length ? '<span class="league-history-reward">' + rewardBits.join(' ') + '</span>' : '') +
                    '</div>';
            });
        }
        setContent(html);
    }

    // ---- Challenges (GET /api/v1/challenges/) ----
    function renderChallenges(data) {
        if (!data.challenge) {
            setContent(
                '<div class="nutrition-empty">' +
                '<div class="empty-icon"><i class="fa-solid fa-fire-flame-curved"></i></div>' +
                '<p class="empty-title">No active challenge.</p>' +
                '<p class="empty-desc">Check back soon - a new community challenge is on its way.</p>' +
                '</div>');
            return;
        }
        var c = data.challenge;
        var board = data.leaderboard || [];
        var top = board.length ? board[0].progress : 0;
        var my = data.my_progress || 0;
        var myPct = top > 0 ? Math.min(100, Math.round((my / top) * 100)) : 0;

        var html = '<div class="challenge-card">' +
            '<div class="challenge-head">' +
            '<div class="challenge-icon"><i class="fa-solid ' + esc(c.icon) + '"></i></div>' +
            '<div><h3 class="challenge-name">' + esc(c.name) + '</h3>' +
            '<div class="challenge-meta">Rolling ' + esc(c.window_days) + ' days \u00b7 ' +
            esc(c.unit) + '</div></div></div>' +
            '<p class="challenge-desc">' + esc(c.description) + '</p>' +
            '<div class="challenge-my">' +
            '<div class="nutrition-xp-bar-wrap"><div class="nutrition-xp-bar">' +
            '<div class="nutrition-xp-fill" style="width:' + myPct +
            '%;background-color:var(--primary-orange);"></div></div>' +
            '<div class="nutrition-xp-to-next">You: ' + my.toLocaleString() + ' ' + esc(c.unit) +
            (top > my ? ' \u00b7 leader ' + top.toLocaleString() : ' \u00b7 you lead! \uD83C\uDFC6') +
            '</div></div></div></div>';

        html += '<div class="base-section-title">Standings</div><div class="league-board">';
        board.forEach(function (row) {
            var medal = MEDALS[row.rank] || ('#' + row.rank);
            html += '<div class="league-row' + (row.is_you ? ' row-you' : '') + '">' +
                '<span class="league-rank">' + medal + '</span>' +
                avatarImg('league-avatar', row.avatar) +
                '<span class="league-name">' + esc(row.username) + (row.is_you ? ' (you)' : '') + '</span>' +
                '<span class="league-xp">' + row.progress.toLocaleString() + ' ' + esc(c.unit) + '</span>' +
                '</div>';
        });
        html += '</div>';
        setContent(html);
    }

    // ---- Flock / social (GET /api/v1/social/) ----
    function renderFlock(data, q) {
        lastSocial = data;
        var html = '';

        // 1. Find friends (search)
        html += '<div class="flock-card">' +
            '<div class="base-section-title"><i class="fa-solid fa-magnifying-glass"></i> Find friends</div>' +
            '<div class="social-search">' +
            '<input type="text" id="friend-search-input" placeholder="Search players..." ' +
            'value="' + esc(q || '') + '">' +
            '<button class="btn-flamingo btn-sm" onclick="runFriendSearch()">Search</button>' +
            '</div>';
        if (q && !(data.search_results || []).length) {
            html += '<p class="empty-desc">No players match "' + esc(q) + '".</p>';
        }
        (data.search_results || []).forEach(function (r) {
            var action = '';
            if (r.relationship === 'none') {
                action = '<button class="btn-flamingo btn-sm" onclick="sendFriendRequest(\'' +
                    esc(r.username).replace(/'/g, "\\'") + '\')">Add</button>';
            } else if (r.relationship === 'friends') {
                action = '<span class="social-state-tag tag-friends">Friends</span>';
            } else if (r.relationship === 'pending_out') {
                action = '<span class="social-state-tag tag-pending">Pending</span>';
            } else {
                action = '<button class="btn-flamingo btn-sm" onclick="respondFriend(' + r.id +
                    ', \'accept\')">Accept</button>';
            }
            html += '<div class="friend-row">' +
                avatarImg('friend-avatar', r.avatar) +
                '<span class="friend-name">' + esc(r.username) + '</span>' + action + '</div>';
        });
        html += '</div>';

        // 2. Friend requests
        var incoming = data.incoming_requests || [];
        var outgoing = data.outgoing_requests || [];
        if (incoming.length || outgoing.length) {
            html += '<div class="flock-card"><div class="base-section-title">' +
                '<i class="fa-solid fa-user-plus"></i> Requests</div>';
            incoming.forEach(function (r) {
                html += '<div class="friend-row">' +
                    avatarImg('friend-avatar', r.avatar) +
                    '<span class="friend-name">' + esc(r.username) + ' wants to be friends</span>' +
                    '<span class="social-btn-group">' +
                    '<button class="btn-flamingo btn-sm" onclick="respondFriend(' + r.id +
                    ', \'accept\')"><i class="fa-solid fa-check"></i></button>' +
                    '<button class="btn-flamingo btn-sm btn-danger" onclick="respondFriend(' + r.id +
                    ', \'decline\')"><i class="fa-solid fa-xmark"></i></button></span></div>';
            });
            outgoing.forEach(function (r) {
                html += '<div class="friend-row">' +
                    avatarImg('friend-avatar', r.avatar) +
                    '<span class="friend-name">' + esc(r.username) + '</span>' +
                    '<span class="social-state-tag tag-pending">Sent</span></div>';
            });
            html += '</div>';
        }

        // 3. Flock invites
        (data.flock_invites || []).forEach(function (inv) {
            html += '<div class="flock-card flock-invite-card">' +
                '<div class="flock-invite-text"><i class="fa-solid fa-dove"></i> ' +
                '<strong>' + esc(inv.name) + '</strong> (' + inv.member_count + '/8)' +
                ' invited you' + (inv.invited_by ? ' \u00b7 by ' + esc(inv.invited_by) : '') + '</div>' +
                '<span class="social-btn-group">' +
                '<button class="btn-flamingo btn-sm" onclick="respondFlockInvite(' + inv.flock_id +
                ', \'accept\')">Join</button>' +
                '<button class="btn-flamingo btn-sm btn-danger" onclick="respondFlockInvite(' + inv.flock_id +
                ', \'decline\')">No</button></span></div>';
        });
        setContent(html + renderFlockBody(data));
    }

    function renderFlockBody(data) {
        var html = '';
        var flock = data.flock;
        var friends = data.friends || [];

        // 4. Friends list
        html += '<div class="flock-card"><div class="base-section-title">' +
            '<i class="fa-solid fa-user-group"></i> Friends (' + friends.length + ')</div>';
        if (!friends.length) {
            html += '<p class="empty-desc">No friends yet. Search above to find your flock!</p>';
        }
        var flockIsMine = flock && flock.my_role === 'owner';
        friends.forEach(function (f) {
            var actions = '';
            if (flockIsMine && !f.in_flock) {
                actions += '<button class="btn-flamingo btn-sm" onclick="inviteToFlock(' + f.id +
                    ')" title="Invite to flock"><i class="fa-solid fa-dove"></i></button>';
            }
            actions += '<button class="btn-flamingo btn-sm btn-danger" onclick="removeFriend(' + f.id +
                ')" title="Remove friend"><i class="fa-solid fa-user-minus"></i></button>';
            html += '<div class="friend-row">' +
                avatarImg('friend-avatar', f.avatar) +
                '<span class="friend-name">' + esc(f.username) +
                (f.same_flock ? ' <i class="fa-solid fa-dove flock-mate" title="Same flock"></i>' : '') +
                '</span><span class="friend-xp">' + f.weekly_xp + ' XP</span>' +
                '<span class="social-btn-group">' + actions + '</span></div>';
        });
        html += '</div>';

        // 5. Your flock (or create form)
        if (flock) {
            html += '<div class="flock-card">' +
                '<div class="base-section-title"><i class="fa-solid ' + esc(flock.icon) + '"></i> ' +
                esc(flock.name) + ' (' + flock.member_count + '/' + flock.max_members + ')</div>' +
                '<div class="flock-total">Flock XP this week: <strong>' +
                flock.weekly_total_xp + '</strong>' +
                (flock.my_role === 'owner' ? ' \u00b7 you own this flock' : '') + '</div>';
            flock.members.forEach(function (m) {
                html += '<div class="friend-row' + (m.is_you ? ' row-you' : '') + '">' +
                    avatarImg('friend-avatar', m.avatar) +
                    '<span class="friend-name">' + esc(m.username) + (m.is_you ? ' (you)' : '') +
                    (m.role === 'owner' ? ' <i class="fa-solid fa-crown flock-owner" title="Owner"></i>' : '') +
                    '</span><span class="friend-xp">' + m.weekly_xp + ' XP</span></div>';
            });
            html += '<button class="btn-flamingo btn-sm btn-danger flock-leave" onclick="leaveFlock()">' +
                '<i class="fa-solid fa-right-from-bracket"></i> Leave flock</button></div>';
        } else if (!(data.flock_invites || []).length) {
            html += '<div class="flock-card"><div class="base-section-title">' +
                '<i class="fa-solid fa-dove"></i> Start a Flock</div>' +
                '<p class="empty-desc">Flocks are small crews (up to 8) that train together.</p>' +
                '<div class="social-search">' +
                '<input type="text" id="flock-name-input" placeholder="Flock name..." maxlength="80">' +
                '<button class="btn-flamingo btn-sm" onclick="createFlock()">Create</button>' +
                '</div></div>';
        }
        return html;
    }

    window.runFriendSearch = function () {
        var input = document.getElementById('friend-search-input');
        var q = input ? input.value.trim() : '';
        if (!q) { fetchSocial(); return; }
        setContent('<p class="loading-hint"><i class="fa-solid fa-spinner fa-spin"></i> Searching...</p>');
        fetchSocial(q);
    };

    // ---- Social actions (all POSTs return a fresh social snapshot) ----
    window.sendFriendRequest = function (username) {
        postJson('/api/v1/friends/request', { username: username })
            .then(function (data) { renderFlock(data, lastSearchQuery()); })
            .catch(socialError);
    };

    window.respondFriend = function (userId, action) {
        postJson('/api/v1/friends/respond', { user_id: userId, action: action })
            .then(function (data) { renderFlock(data, lastSearchQuery()); })
            .catch(socialError);
    };

    window.removeFriend = function (userId) {
        postJson('/api/v1/friends/remove', { user_id: userId })
            .then(function (data) { renderFlock(data, lastSearchQuery()); })
            .catch(socialError);
    };

    window.createFlock = function () {
        var input = document.getElementById('flock-name-input');
        var name = input ? input.value.trim() : '';
        if (!name) { socialError({ message: 'Give your flock a name first.' }); return; }
        postJson('/api/v1/flocks/create', { name: name })
            .then(function (data) { renderFlock(data); })
            .catch(socialError);
    };

    window.inviteToFlock = function (userId) {
        postJson('/api/v1/flocks/invite', { user_id: userId })
            .then(function (data) { renderFlock(data); })
            .catch(socialError);
    };

    window.respondFlockInvite = function (flockId, action) {
        postJson('/api/v1/flocks/respond', { flock_id: flockId, action: action })
            .then(function (data) { renderFlock(data); })
            .catch(socialError);
    };

    window.leaveFlock = function () {
        postJson('/api/v1/flocks/leave', {})
            .then(function (data) { renderFlock(data); })
            .catch(socialError);
    };

    function lastSearchQuery() {
        var input = document.getElementById('friend-search-input');
        return input ? input.value.trim() : '';
    }
})();


