/* ============================================================
   Flamingo Fitness - Service Worker (Step 20)
   Caches static assets (CSS/JS/icons) for instant, offline loading.
   ============================================================ */

var CACHE_NAME = 'flamingo-fitness-v1';

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
            return cache.addAll(PRECACHE_URLS);
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

// Cache-first for static assets; network-first for the app shell and API.
self.addEventListener('fetch', function (event) {
    var requestUrl = new URL(event.request.url);

    // Never cache the API (always go to the network).
    if (requestUrl.pathname.indexOf('/api/') === 0 || requestUrl.pathname === '/') {
        return;
    }

    event.respondWith(
        caches.match(event.request).then(function (cached) {
            if (cached) {
                return cached;
            }
            return fetch(event.request).then(function (response) {
                // Only cache successful GET responses for our own origin.
                if (response && response.ok && requestUrl.origin === location.origin) {
                    var clone = response.clone();
                    caches.open(CACHE_NAME).then(function (cache) {
                        cache.put(event.request, clone);
                    });
                }
                return response;
            });
        })
    );
});
