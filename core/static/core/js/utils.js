/* ============================================================
   Flamingo Fitness - shared utility functions (Phase 1, docs/19).
   Loaded FIRST so every controller can use window.ffLog,
   window.ffWarn, window.ffError, window.loadScript,
   window.escHtml, window.csrfToken, window.haptic,
   window.fmoney, window.showToast, window.emptyStateHTML etc.
   ============================================================ */
(function () {
    'use strict';

    // ------------------------------------------------------------------
    // Guarded logging — silent in production unless ffDEBUG is true.
    // The Django template sets window.ffDEBUG from the DEBUG flag.
    // ------------------------------------------------------------------
    window.ffDEBUG = window.ffDEBUG || false;

    window.ffLog = function () {
        if (window.ffDEBUG) {
            Function.prototype.apply.call(console.log, console, arguments);
        }
    };

    window.ffWarn = function () {
        if (window.ffDEBUG) {
            Function.prototype.apply.call(console.warn, console, arguments);
        }
    };

    window.ffError = function () {
        // Errors are always reported even in production
        Function.prototype.apply.call(console.error, console, arguments);
    };

    // ------------------------------------------------------------------
    // Lazy script loading — dynamically injects a <script> tag and
    // returns a Promise that resolves when the script loads.
    // ------------------------------------------------------------------
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
            .replace(/>/g, '&gt;').replace(/\"/g, '&quot;');
    };

    // ------------------------------------------------------------------
    // CSRF token from <meta name="csrf-token">
    // ------------------------------------------------------------------
    window.csrfToken = function () {
        var m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.content : '';
    };

    // ------------------------------------------------------------------
    // Haptic feedback (vibration)
    // ------------------------------------------------------------------
    window.haptic = function (ms) {
        if (navigator.vibrate) navigator.vibrate(ms || 50);
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

})();
