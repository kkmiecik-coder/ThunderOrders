/**
 * ThunderOrders Service Worker
 * Cache First for static assets, Network Only for API and navigations.
 * UWAGA: NIE przechwytujemy nawigacji (respondWith na request.mode === 'navigate')
 * — Samsung Internet potrafi nie zatwierdzić nawigacji obsłużonej przez SW
 * (serwer odpowiada 200, a ekran się nie zmienia). Przeglądarka obsługuje
 * przejścia między stronami natywnie.
 */

const CACHE_VERSION = 'thunderorders-v10';
const STATIC_CACHE = CACHE_VERSION + '-static';

// Assets to pre-cache on install
const PRECACHE_ASSETS = [
    '/static/css/main.css',
    '/static/js/core/app.js',
    '/static/js/components/toast.js',
    '/static/js/main.js',
    '/static/img/pwa/icon-192x192.png',
    '/static/img/icons/logo_chmurka.svg'
];

// Install - pre-cache critical assets
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then(cache => cache.addAll(PRECACHE_ASSETS))
            .then(() => self.skipWaiting())
    );
});

// Activate - clean old caches
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys
                    .filter(key => key !== STATIC_CACHE)
                    .map(key => caches.delete(key))
            )
        ).then(() => self.clients.claim())
    );
});

// Fetch strategy
self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);

    // Skip non-GET and cross-origin
    if (request.method !== 'GET' || url.origin !== self.location.origin) return;

    // Network Only for API calls
    if (url.pathname.startsWith('/api/')) return;

    // Skip vendor JS/CSS (large files, let browser handle caching)
    if (url.pathname.includes('/vendor/')) return;

    // Cache First for static assets (/static/)
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(request).then(cached => {
                if (cached) return cached;
                return fetch(request).then(response => {
                    if (response.ok) {
                        const clone = response.clone();
                        caches.open(STATIC_CACHE).then(cache => cache.put(request, clone));
                    }
                    return response;
                });
            })
        );
        return;
    }

    // Nawigacje (HTML) celowo NIE są przechwytywane — patrz nagłówek pliku.
});

// Push notification handler
self.addEventListener('push', event => {
    if (!event.data) return;

    let data;
    try {
        data = event.data.json();
    } catch (e) {
        data = { title: 'ThunderOrders', body: event.data.text() };
    }

    const options = {
        body: data.body || '',
        icon: '/static/img/pwa/icon-192x192.png',
        badge: '/static/img/pwa/badge-96x96.png',
        tag: data.tag || 'thunderorders-notification',
        data: { url: data.url || '/' },
        vibrate: [200, 100, 200],
        actions: data.actions || []
    };

    event.waitUntil(
        self.registration.showNotification(data.title || 'ThunderOrders', options)
    );
});

// Notification click handler
self.addEventListener('notificationclick', event => {
    event.notification.close();

    const targetUrl = event.notification.data?.url || '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
            // Focus existing window if found
            for (const client of windowClients) {
                if (client.url.includes(self.location.origin) && 'focus' in client) {
                    client.navigate(targetUrl);
                    return client.focus();
                }
            }
            // Open new window
            return clients.openWindow(targetUrl);
        })
    );
});

// Push subscription change handler - auto-renew when browser rotates subscription
self.addEventListener('pushsubscriptionchange', event => {
    event.waitUntil(
        self.registration.pushManager.subscribe(event.oldSubscription.options)
            .then(newSub => {
                const subJSON = newSub.toJSON();
                return fetch('/notifications/subscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        endpoint: subJSON.endpoint,
                        keys: subJSON.keys,
                        device_name: ''
                    })
                });
            })
            .catch(err => console.warn('[SW] pushsubscriptionchange re-subscribe failed:', err))
    );
});
