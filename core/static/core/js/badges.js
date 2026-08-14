/* Achievement Badges panel controller (Roadmap idea #5).
 * Opens from the "Badges" bottom-nav tab.
 * Consumes GET /api/v1/badges/ (core/views.py badges_state), which lazily
 * grants any newly-earned badges and serializes the catalog with points,
 * awarded timestamps and live progress. Tiles are clickable: earned badges
 * show their meaning + award date; locked badges show what is left to do.
 */
(function () {
    'use strict';

    var BADGES_URL = '/api/v1/badges/';
    var lastData = null; // cached payload for the detail-view back button

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    window.backToBadgesPlan = function () {
        var view = document.getElementById('badges-view');
        if (view) view.classList.add('hidden');
        var hint = document.getElementById('loading-hint');
        if (hint) hint.classList.add('hidden');
        // Single-panel navigation: hide ALL panels, then show only the skill tree.
        window.ensureSinglePanelVisible('skill-tree');
    };

    window.loadBadges = function () {
        console.log('[badges] loadBadges start');
        if (window.closeModal) window.closeModal();
        var view = document.getElementById('badges-view');
        var content = document.getElementById('badges-content');
        var empty = document.getElementById('badges-empty');
        var tree = document.getElementById('skill-tree');
        if (!view) { console.warn('[badges] badges-view not found, aborting'); return; }
        if (tree) tree.classList.add('hidden');
        view.classList.remove('hidden');
        if (content) content.classList.add('hidden');
        if (empty) empty.classList.add('hidden');
        fetch(BADGES_URL, { credentials: 'same-origin' })
            .then(function (res) {
                if (res.status === 401 || res.status === 403) throw new Error('not-authenticated');
                return res.ok ? res.json() : Promise.reject(res.status);
            })
            .then(function (data) {
                console.log('[badges] earned=', data.earned, 'of', data.total);
                lastData = data;
                window.renderBadges(data);
            })
            .catch(function (err) {
                console.error('[badges] fetch failed:', err);
                if (content) {
                    content.classList.remove('hidden');
                    content.innerHTML = err && err.message === 'not-authenticated'
                        ? '<p class="error-hint">Please log in to view your badges.</p>'
                        : '<p class="error-hint">Could not load badges (error ' + err + ').</p>';
                }
                if (empty) empty.classList.add('hidden');
            });
    };

    // Badge grid. Every tile is clickable -> showBadgeDetail().
    window.renderBadges = function (data) {
        lastData = data;
        var content = document.getElementById('badges-content');
        if (!content) return;
        content.classList.remove('hidden');
        content.innerHTML = '';

        var summary = document.createElement('div');
        summary.className = 'badges-summary';
        summary.innerHTML = 'Earned: <strong>' + (data.earned || 0) + '</strong> / ' + (data.total || 0) +
            ' &middot; <i class="fa-solid fa-star"></i> <strong>' + (data.earned_points || 0) +
            '</strong> / ' + (data.total_points || 0) + ' pts';
        content.appendChild(summary);

        if (data.newly_awarded && data.newly_awarded.length) {
            var banner = document.createElement('div');
            banner.className = 'badges-new';
            banner.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> New badge earned! Tap it for details.';
            content.appendChild(banner);
        }

        var badges = data.badges || [];
        if (!badges.length) {
            content.innerHTML = '<div class="nutrition-empty"><p class="empty-title">No badges configured.</p>' +
                '<p class="empty-desc">An admin can add badges under "Badge defs" in the Django admin.</p></div>';
            return;
        }

        var grid = document.createElement('div');
        grid.className = 'badge-grid';
        badges.forEach(function (b) {
            var tile = document.createElement('div');
            tile.className = 'badge-tile' + (b.granted ? ' earned' : ' locked');
            tile.setAttribute('role', 'button');
            tile.setAttribute('tabindex', '0');
            tile.setAttribute('aria-label', b.name + ' - tap for details');
            tile.innerHTML =
                '<div class="badge-icon"><i class="fa-solid ' + esc(b.icon || 'fa-medal') + '"></i></div>' +
                '<div class="badge-name">' + esc(b.name) + '</div>' +
                '<div class="badge-cat">' + esc(b.category) + '</div>' +
                '<div class="badge-points"><i class="fa-solid fa-star"></i> ' + (b.points || 0) + ' pts</div>' +
                '<div class="badge-state">' + (b.granted
                    ? '<i class="fa-solid fa-check"></i> Earned'
                    : '<i class="fa-solid fa-lock"></i> Locked') + '</div>';
            tile.addEventListener('click', function () { window.showBadgeDetail(b); });
            tile.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    window.showBadgeDetail(b);
                }
            });
            grid.appendChild(tile);
        });
        content.appendChild(grid);
    };

    // Detail view: what the badge means, when it was achieved, or what is
    // left to achieve (progress bar + hint) when it is still locked.
    window.showBadgeDetail = function (b) {
        var content = document.getElementById('badges-content');
        if (!content) return;
        content.classList.remove('hidden');
        content.innerHTML = '';

        var card = document.createElement('div');
        card.className = 'badge-detail' + (b.granted ? ' earned' : ' locked');

        var head = document.createElement('div');
        head.className = 'badge-detail-head';
        head.innerHTML =
            '<div class="badge-detail-icon"><i class="fa-solid ' + esc(b.icon || 'fa-medal') + '"></i></div>' +
            '<div><h3 class="badge-detail-name">' + esc(b.name) + '</h3>' +
            '<div class="badge-detail-meta">' + esc(b.category) +
            ' &middot; <i class="fa-solid fa-star"></i> ' + (b.points || 0) + ' pts</div></div>';
        card.appendChild(head);

        var desc = document.createElement('p');
        desc.className = 'badge-detail-desc';
        desc.textContent = b.description || '';
        card.appendChild(desc);

        var status = document.createElement('div');
        status.className = 'badge-detail-status';
        if (b.granted) {
            var when = '';
            if (b.awarded_at) {
                try {
                    when = new Date(b.awarded_at).toLocaleDateString(undefined, {
                        year: 'numeric', month: 'short', day: 'numeric'
                    });
                } catch (e) { when = ''; }
            }
            status.innerHTML = '<div class="badge-earned-flag">' +
                '<i class="fa-solid fa-circle-check"></i> Earned' +
                (when ? ' on ' + esc(when) : '') + '</div>';
        } else {
            var p = b.progress || {};
            status.innerHTML =
                '<div class="badge-locked-flag"><i class="fa-solid fa-lock"></i> Not earned yet</div>' +
                '<div class="badge-progress-text">' + esc(p.text || '') + '</div>' +
                '<div class="nutrition-xp-bar-wrap"><div class="nutrition-xp-bar">' +
                '<div class="nutrition-xp-fill" style="width:' +
                Math.min(100, Math.max(0, p.pct || 0)) +
                '%;background-color:var(--primary-orange);"></div></div>' +
                '<div class="nutrition-xp-to-next">' + (p.pct || 0) + '% to goal</div></div>';
        }
        card.appendChild(status);

        var back = document.createElement('button');
        back.className = 'btn-flamingo badge-detail-back';
        back.innerHTML = '<i class="fa-solid fa-arrow-left"></i> All badges';
        back.addEventListener('click', function () {
            if (lastData) window.renderBadges(lastData);
        });
        card.appendChild(back);

        content.appendChild(card);
    };
})();
