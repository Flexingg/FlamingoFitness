/* ============================================================
   Flamingo Fitness - Service Worker (Step 20, Phase 1 docs/19 #24)
   Caches static assets (CSS/JS/icons) for instant, offline loading.

   Cache name is auto-versioned via a <meta name="ff-sw-version"> tag
   set by Django (see dashboard.html). Bump the version in Django
   settings to force a re-cache.

   Network-first for static assets and the app shell (cache fallback when
   offline); the API always hits the network so private data stays fresh.
   ============================================================ */

// Read version from a meta tag set by Django at template render time.
// Falls back to "v4" if the tag is absent (legacy compat).
var CACHE_NAME = (function () {
    var meta = document.querySelector('meta[name="ff-sw-version"]');
    return 'flamingo-fitness-' + (meta ? meta.getAttribute('content') : 'v4');
})();

// Assets to pre-cache on install. Only list files that currently exist so
// cache.addAll() never rejects (the install catch is a soft-fallback anyway).
var PRECACHE_URLS = [
    '/static/core/css/dashboard.css',
    '/static/core/css/auth.css',
    '/static/core/js/utils.js',
    '/static/core/js/theme.js',
    '/static/core/js/router.js',
    '/static/core/js/dashboard.js',
    '/static/core/js/chart.umd.min.js',
    '/static/core/js/insights.js',
    '/static/core/js/modality-factory.js',
    '/static/core/js/nutrition.js',
    '/static/core/js/hydration.js',
    '/static/core/js/endurance.js',
    '/static/core/js/strength.js',
    '/static/core/js/boss.js',
    '/static/core/js/recovery.js',
    '/static/core/js/shop.js',
    '/static/core/js/loadout.js',
    '/static/core/js/battle.js',
    '/static/core/js/pvp.js',
    '/static/core/js/badges.js',
    '/static/core/js/leagues.js',
    '/static/core/js/stat_info.js',
    '/static/core/icons/icon-192.svg',
    '/static/core/manifest.json'
];

self.addEventListener('install', function (event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function (cache) {
            return cache.addAll(PRECACHE_URLS).catch(function () {
                // Individual failures (e.g. an icon) must not kill the update.
            });
        }).then(function () {
            return self.skipWaiting();
        })
    );
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(
                keys.filter(function (key) {
                    return key !== CACHE_NAME;
                }).map(function (key) {
                    return caches.delete(key);
                })
            );
        }).then(function () {
            return self.clients.claim();
        })
    );
});

// Network-first for static assets and the app shell (cache fallback when
// offline); the API always hits the network so private data stays fresh.
self.addEventListener('fetch', function (event) {
    var requestUrl = new URL(event.request.url);

    // Never cache the API (always go to the network).
    if (requestUrl.pathname.indexOf('/api/') === 0) {
        return;
    }
    // Only handle same-origin GETs.
    if (event.request.method !== 'GET' || requestUrl.origin !== location.origin) {
        return;
    }

    // App shell (navigation) -> network-first so the latest page always loads,
    // and the last-good shell is served when offline.
    var isNavigation = event.request.mode === 'navigate';

    event.respondWith(
        fetch(event.request).then(function (response) {
            if (response && response.ok) {
                var clone = response.clone();
                caches.open(CACHE_NAME).then(function (cache) {
                    cache.put(isNavigation ? '/' : event.request, clone);
                });
            }
            return response;
        }).catch(function () {
            // Offline (or network failure): fall back to the cached copy.
            return caches.match(event.request).then(function (cached) {
                if (cached) return cached;
                if (isNavigation) return caches.match('/');
                return Response.error();
            });
        })
    );
});
