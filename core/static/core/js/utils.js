/* ============================================================
   Flamingo Fitness - Shared Utility Library (utils.js)
   ------------------------------------------------------------
   Architecture Overview:
   - Primary utility runtime loaded FIRST before all view controllers.
   - Provides safe logging, dynamic script injection (`loadScript`),
     XSS-safe HTML escaping (`escHtml`), and unified CSRF extraction (`csrfToken`).
   - Native device haptic bridge with web vibration fallback (`haptic`).
   - Gamified celebration modals with sound and particle effects:
     `celebrateLevelUp`, `celebrateBadge`, `confettiBurst`.
   - Toast notification system (`showToast`).
   - Standardized empty-state and skeleton rendering (`emptyStateHTML`, `renderSkeleton`).
   ============================================================ */
(function () {
    'use strict';

    // ------------------------------------------------------------------
    // Guarded logging — silent in production unless ffDEBUG is true.
    // The Django template sets window.ffDEBUG from the DEBUG flag.
    // ------------------------------------------------------------------
    window.ffDEBUG = window.ffDEBUG || false;

    /** Safe debug logging (suppressed in production unless ffDEBUG=true). */
    window.ffLog = function () {
        if (window.ffDEBUG) {
            Function.prototype.apply.call(console.log, console, arguments);
        }
    };

    /** Safe warning logging (suppressed in production unless ffDEBUG=true). */
    window.ffWarn = function () {
        if (window.ffDEBUG) {
            Function.prototype.apply.call(console.warn, console, arguments);
        }
    };

    /** Unconditional error logging to browser console. */
    window.ffError = function () {
        Function.prototype.apply.call(console.error, console, arguments);
    };

    /**
     * Lazy script loader — dynamically injects a <script> tag.
     * Returns a Promise that resolves when the script loads or rejects on error.
     * @param {string} url - Static script URL to inject
     * @returns {Promise<void>}
     */
    window.loadScript = function (url) {
        return new Promise(function (resolve, reject) {
            var s = document.createElement('script');
            s.src = url;
            s.onload = function () { resolve(); };
            s.onerror = function () { reject(new Error('Failed to load ' + url)); };
            document.body.appendChild(s);
        });
    };

    // ------------------------------------------------------------------
    // HTML escaping (replaces per-controller esc/escHtml)
    // ------------------------------------------------------------------
    window.escHtml = function (s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    };

    // ------------------------------------------------------------------
    // CSRF token from <meta name="csrf-token"> with cookie fallback
    // ------------------------------------------------------------------
    window.csrfToken = function () {
        var m = document.querySelector('meta[name="csrf-token"]');
        if (m && m.content && m.content !== 'NOTPROVIDED' && m.content !== '') return m.content;
        var match = document.cookie.match(/(?:^|;\s*)(?:csrftoken|__Secure-csrftoken)=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    };

    // ------------------------------------------------------------------
    // Haptic feedback (vibration)
    // ------------------------------------------------------------------
    window.haptic = function (ms) {
        if (navigator.vibrate) {
            try {
                navigator.vibrate(ms || 50);
            } catch (e) {
                // Ignore
            }
        }
    };

    // ------------------------------------------------------------------
    // Number formatting with commas (replaces per-controller money())
    // ------------------------------------------------------------------
    window.fmoney = function (n) {
        var v = Number(n == null ? 0 : n);
        return Math.round(v).toLocaleString();
    };

    // ------------------------------------------------------------------
    // Confetti burst (requires canvas-confetti CDN)
    // ------------------------------------------------------------------
    window.confettiBurst = function () {
        if (typeof confetti === 'function') {
            confetti({ particleCount: 120, spread: 70, origin: { y: 0.6 } });
        }
        window.haptic([100, 50, 100]);
    };

    // ------------------------------------------------------------------
    // Gamified Level-Up & Badge Unlock Celebrations (Roadmap item #8)
    // ------------------------------------------------------------------
    window.celebrateLevelUp = function (modality, level, bonusTokens) {
        var modal = document.getElementById('celebrationModal');
        if (!modal) return;
        var tag = document.getElementById('celebration-tag');
        var title = document.getElementById('celebration-title');
        var desc = document.getElementById('celebration-desc');
        var icon = document.getElementById('celebration-icon');
        var tokensEl = document.getElementById('celebration-reward-tokens');

        if (tag) tag.textContent = '🌟 LEVEL UP!';
        if (title) title.textContent = (modality ? modality.toUpperCase() : 'SKILL') + ' LEVEL ' + (level || 2);
        if (desc) desc.textContent = 'Awesome effort! Your avatar gained combat multipliers and unlocked bonus tokens.';
        if (icon) icon.innerHTML = '<i class="fa-solid fa-arrow-trend-up"></i>';
        if (tokensEl) tokensEl.innerHTML = '<i class="fa-solid fa-coins"></i> <span>+' + (bonusTokens || 25) + ' Tokens</span>';

        modal.classList.add('show-modal');
        window.confettiBurst();
        window.haptic([80, 40, 120]);
        if (window.playLevelUpFanfare) window.playLevelUpFanfare();
    };

    window.celebrateBadge = function (badge) {
        if (!badge) return;
        var modal = document.getElementById('celebrationModal');
        if (!modal) return;
        var tag = document.getElementById('celebration-tag');
        var title = document.getElementById('celebration-title');
        var desc = document.getElementById('celebration-desc');
        var icon = document.getElementById('celebration-icon');
        var tokensEl = document.getElementById('celebration-reward-tokens');

        if (tag) tag.textContent = '🏆 BADGE UNLOCKED!';
        if (title) title.textContent = badge.name || 'New Badge';
        if (desc) desc.textContent = badge.description || 'You unlocked a new fitness achievement!';
        if (icon) icon.innerHTML = '<i class="fa-solid ' + (badge.icon || 'fa-trophy') + '"></i>';
        if (tokensEl) {
            var rewardTxt = '';
            if (badge.token_reward) rewardTxt += '+' + badge.token_reward + ' Tokens ';
            if (badge.scrap_reward) rewardTxt += '+' + badge.scrap_reward + ' Scraps';
            tokensEl.innerHTML = '<i class="fa-solid fa-gift"></i> <span>' + (rewardTxt || '+50 XP Bonus') + '</span>';
        }

        modal.classList.add('show-modal');
        window.confettiBurst();
        window.haptic([100, 50, 150]);
        if (window.playBadgeFanfare) window.playBadgeFanfare();
    };

    window.closeCelebrationModal = function () {
        if (window.playButtonTap) window.playButtonTap();
        var modal = document.getElementById('celebrationModal');
        if (modal) modal.classList.remove('show-modal');
    };


    // ------------------------------------------------------------------
    // Empty-state HTML generator (used by every modality controller)
    // ------------------------------------------------------------------
    window.emptyStateHTML = function (opts) {
        opts = opts || {};
        var icon = opts.icon || 'fa-circle-info';
        var title = opts.title || '';
        var desc = opts.desc || '';
        var hint = opts.hint || '';
        var ctaText = opts.ctaText || '';
        var ctaHref = opts.ctaHref || '';
        var secondary = opts.secondary || false;
        return '<div class="empty-state flex flex-col items-center text-center p-6">' +
            '<div class="empty-state-icon"><i class="fa-solid ' + icon + '"></i></div>' +
            '<div class="empty-state-title">' + window.escHtml(title) + '</div>' +
            '<div class="empty-state-desc">' + window.escHtml(desc) + '</div>' +
            (hint ? '<div class="empty-state-hint">' + window.escHtml(hint) + '</div>' : '') +
            (ctaText && ctaHref ? '<a href="' + window.escHtml(ctaHref) + '" class="empty-state-cta' +
                (secondary ? ' secondary' : '') + '">' + window.escHtml(ctaText) + '</a>' : '') +
            (ctaText && !ctaHref ? '<button class="empty-state-cta' +
                (secondary ? ' secondary' : '') + '">' + window.escHtml(ctaText) + '</button>' : '') +
            '</div>';
    };

    // ------------------------------------------------------------------
    // Render empty state into a container
    // ------------------------------------------------------------------
    window.showEmptyState = function (container, opts) {
        if (!container) return;
        container.innerHTML = window.emptyStateHTML(opts);
        container.classList.remove('hidden');
    };

    // ------------------------------------------------------------------
    // Toast notification (replaces alert() calls, Phase 1, docs/19 #19)
    // ------------------------------------------------------------------
    window.showToast = function (message, type) {
        type = type || 'info';
        if (!message) return;
        var existing = document.getElementById('ff-toast');
        if (existing) existing.remove();

        var toast = document.createElement('div');
        toast.id = 'ff-toast';
        var bg = type === 'error' ? '#ef4444' :
                 type === 'success' ? '#22c55e' :
                 type === 'warning' ? '#f59e0b' : '#334155';
        var iconMap = {
            error: 'fa-circle-exclamation',
            success: 'fa-circle-check',
            warning: 'fa-triangle-exclamation',
            info: 'fa-circle-info'
        };
        toast.innerHTML = '<i class="fa-solid ' + (iconMap[type] || iconMap.info) + '"></i> ' +
            window.escHtml(message);
        toast.style.cssText = 'position:fixed;bottom:100px;left:50%;transform:translateX(-50%);' +
            'background:' + bg + ';color:#fff;font-weight:800;font-size:0.85rem;' +
            'padding:12px 20px;border-radius:14px;box-shadow:0 6px 20px rgba(0,0,0,0.25);' +
            'z-index:9999;max-width:85%;text-align:center;display:flex;align-items:center;gap:8px;' +
            'animation:toast-in 0.2s ease-out;';
        document.body.appendChild(toast);
        setTimeout(function () { toast.remove(); }, 3500);
    };

    // ------------------------------------------------------------------
    // Panel lazy-loading (Phase 2, docs/19 #12)
    // Fetches server-side HTML partial for a panel and injects it into <main>
    // ------------------------------------------------------------------
    window._panelCache = window._panelCache || {};
    window.ensurePanelLoaded = function (panelId) {
        var cleanName = panelId.replace('-view', '');
        var targetId = cleanName + '-view';
        var el = document.getElementById(targetId);
        if (el) {
            return Promise.resolve(el);
        }
        if (window._panelCache[cleanName]) {
            var main = document.querySelector('main');
            if (main) {
                var temp = document.createElement('div');
                temp.innerHTML = window._panelCache[cleanName];
                var node = temp.firstElementChild;
                if (node) main.appendChild(node);
                return Promise.resolve(node || document.getElementById(targetId));
            }
        }
        return fetch('/panel/' + encodeURIComponent(cleanName) + '/', { credentials: 'same-origin' })
            .then(function (res) {
                if (!res.ok) throw new Error('Panel fetch failed: ' + res.status);
                return res.text();
            })
            .then(function (html) {
                window._panelCache[cleanName] = html;
                var main = document.querySelector('main');
                if (main) {
                    var temp = document.createElement('div');
                    temp.innerHTML = html;
                    var node = temp.firstElementChild;
                    if (node) {
                        main.appendChild(node);
                        return node;
                    }
                }
                return document.getElementById(targetId);
            });
    };

    // ------------------------------------------------------------------
    // Skeleton loading state generator (Phase 3, docs/19 #13)
    // ------------------------------------------------------------------
    window.skeletonCardHTML = function () {
        return '<div class="skeleton-card p-4 rounded-2xl mb-4">' +
            '<div class="flex items-center gap-3 mb-3">' +
            '<div class="skeleton-circle w-10 h-10 rounded-full"></div>' +
            '<div class="flex-1">' +
            '<div class="skeleton-bar h-4 w-3/4 rounded mb-2"></div>' +
            '<div class="skeleton-bar h-3 w-1/2 rounded"></div>' +
            '</div>' +
            '</div>' +
            '<div class="skeleton-bar h-20 w-full rounded-xl mb-3"></div>' +
            '<div class="skeleton-bar h-8 w-full rounded-xl"></div>' +
            '</div>';
    };

    window.renderSkeleton = function (container, count) {
        if (!container) return;
        var n = count || 2;
        var html = '<div class="skeleton-wrapper py-2">';
        for (var i = 0; i < n; i++) {
            html += window.skeletonCardHTML();
        }
        html += '</div>';
        container.innerHTML = html;
        container.classList.remove('hidden');
    };

    // ------------------------------------------------------------------
    // Animated number roll-up helper
    // ------------------------------------------------------------------
    window.animateNumber = function (el, startVal, endVal, duration) {
        if (!el) return;
        var start = Number(startVal) || 0;
        var end = Number(endVal) || 0;
        if (start === end) {
            el.textContent = end;
            return;
        }
        var startTime = null;
        var dur = duration || 400;

        function step(timestamp) {
            if (!startTime) startTime = timestamp;
            var progress = Math.min((timestamp - startTime) / dur, 1);
            var ease = 1 - Math.pow(1 - progress, 3); // cubic ease-out
            var current = Math.round(start + (end - start) * ease);
            el.textContent = current;
            if (progress < 1) {
                window.requestAnimationFrame(step);
            } else {
                el.textContent = end;
            }
        }
        window.requestAnimationFrame(step);
    };

})();
