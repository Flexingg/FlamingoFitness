/* ============================================================
   Flamingo Fitness - theme controller (Light / Dark / Device / Time)
   Reads the preference from <html data-theme="..."> and applies the
   matching palette BEFORE first paint (loaded synchronously in <head>).
   'device' follows prefers-color-scheme; 'time' switches to dark
   between 18:00 and 06:00 local time. The preference is saved per
   account on the User model (core/views.py profile endpoint).
   ============================================================ */
(function () {
    'use strict';

    var PREF = document.documentElement.getAttribute('data-theme') || 'device';
    var DARK_START_HOUR = 18; // 6pm
    var DARK_END_HOUR = 6;    // 6am
    var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

    function prefersDark() {
        return mq ? mq.matches : false;
    }

    function isDarkNow() {
        var h = new Date().getHours();
        return h >= DARK_START_HOUR || h < DARK_END_HOUR;
    }

    function shouldBeDark() {
        if (PREF === 'light') return false;
        if (PREF === 'dark') return true;
        if (PREF === 'time') return isDarkNow();
        return prefersDark(); // device (default)
    }

    function applyTheme(forceDark) {
        var dark = typeof forceDark === 'boolean' ? forceDark : shouldBeDark();
        var root = document.documentElement;
        root.classList.toggle('dark', dark);
        root.classList.toggle('light', !dark);
        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta) {
            meta.setAttribute('content', dark ? '#0f172a' : '#f8fafc');
        }
        return dark;
    }

    // Apply immediately so the page never flashes the wrong palette.
    applyTheme();

    // Keep Device / Time modes live without a reload.
    if (PREF === 'device' && mq && mq.addEventListener) {
        mq.addEventListener('change', function () { applyTheme(); });
    } else if (PREF === 'time') {
        // Re-check every minute so it flips at the 6am/6pm boundaries.
        setInterval(function () { applyTheme(); }, 60000);
    }

    // Exposed for the profile page so a choice previews instantly.
    window.ffApplyTheme = function (choice) {
        if (choice === 'light') return applyTheme(false);
        if (choice === 'dark') return applyTheme(true);
        if (choice === 'time') return applyTheme(isDarkNow());
        return applyTheme(prefersDark());
    };
})();
