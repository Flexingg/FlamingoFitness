/* ============================================================
   Flamingo Fitness - Service Worker (Step 20)
   Caches static assets (CSS/JS/icons) for instant, offline loading.

   IMPORTANT (Phase 8 fix): bump CACHE_NAME whenever shipped assets change.
   v1 was cache-first, which left visitors with a stale dashboard.css after
   the leagues update (new JS + old CSS = unstyled tabs). v2 switches static
   assets to network-first with a cache fallback so iterations always land,
   while offline support is preserved.
   ============================================================ */

var CACHE_NAME = 'flamingo-fitness-v3';

// Assets to pre-cache on install.
var PRECACHE_URLS = [
    '/static/core/css/dashboard.css',
    '/static/core/css/auth.css',
    '/static/core/js/dashboard.js',
    '/static/core/js/nutrition.js',
    '/static/core/icons/icon-192.svg'
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

// Network-first for static assets (cache fallback when offline);
// the app shell and API always hit the network.
self.addEventListener('fetch', function (event) {
    var requestUrl = new URL(event.request.url);

    // Never cache the API (always go to the network).
    if (requestUrl.pathname.indexOf('/api/') === 0 || requestUrl.pathname === '/') {
        return;
    }
    // Only handle same-origin GETs.
    if (event.request.method !== 'GET' || requestUrl.origin !== location.origin) {
        return;
    }

    event.respondWith(
        fetch(event.request).then(function (response) {
            if (response && response.ok) {
                var clone = response.clone();
                caches.open(CACHE_NAME).then(function (cache) {
                    cache.put(event.request, clone);
                });
            }
            return response;
        }).catch(function () {
            // Offline (or network failure): fall back to the cached copy.
            return caches.match(event.request).then(function (cached) {
                return cached || Response.error();
            });
        })
    );
});
