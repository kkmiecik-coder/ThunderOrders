/**
 * Service Worker Registration
 */
(function () {
    if (!('serviceWorker' in navigator)) return;

    window.addEventListener('load', function () {
        navigator.serviceWorker.register('/sw.js', { scope: '/' })
            .then(function (registration) {
                console.log('[SW] Registered, scope:', registration.scope);

                // Check for updates every 60 min
                setInterval(function () {
                    registration.update().catch(function () {});
                }, 60 * 60 * 1000);
            })
            .catch(function (err) {
                console.warn('[SW] Registration failed:', err);
            });
    });
})();
