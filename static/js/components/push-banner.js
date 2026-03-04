/**
 * Push Notifications Banner
 * Shows a bottom banner prompting user to enable push notifications.
 * Appears after PWA install banner is hidden (or if app already installed).
 * 7-day cooldown on dismiss.
 */
(function () {
    'use strict';

    var DISMISS_KEY = 'push-banner-dismissed';
    var COOLDOWN_MS = 7 * 24 * 60 * 60 * 1000; // 7 days
    var CHECK_INTERVAL = 2000; // Check every 2s for PWA banner state

    var banner = document.getElementById('push-notif-banner');
    var enableBtn = document.getElementById('push-notif-enable-btn');
    var dismissBtn = document.getElementById('push-notif-dismiss-btn');

    if (!banner || !enableBtn || !dismissBtn) return;

    var PN = window.PushNotifications;
    if (!PN || !PN.isSupported()) return;

    function isDismissed() {
        var ts = localStorage.getItem(DISMISS_KEY);
        if (!ts) return false;
        return (Date.now() - parseInt(ts, 10)) < COOLDOWN_MS;
    }

    function isInstalled() {
        return window.matchMedia('(display-mode: standalone)').matches ||
               window.navigator.standalone === true;
    }

    function isPwaBannerVisible() {
        var pwaBanner = document.getElementById('pwa-install-banner');
        return pwaBanner && pwaBanner.style.display !== 'none';
    }

    function showBanner() {
        banner.style.display = 'flex';
    }

    function hideBanner() {
        banner.style.display = 'none';
    }

    function tryShow() {
        // Don't show if dismissed recently
        if (isDismissed()) return;

        // Don't show if permission denied
        if (Notification.permission === 'denied') return;

        // Check subscription
        PN.isSubscribed().then(function (subscribed) {
            if (subscribed) return; // Already subscribed

            // If PWA banner is visible, wait for it to hide
            if (isPwaBannerVisible()) {
                waitForPwaBanner();
                return;
            }

            showBanner();
        });
    }

    function waitForPwaBanner() {
        var observer = new MutationObserver(function (mutations) {
            mutations.forEach(function () {
                if (!isPwaBannerVisible()) {
                    observer.disconnect();
                    // Small delay after PWA banner hides
                    setTimeout(function () {
                        if (!isDismissed()) {
                            PN.isSubscribed().then(function (subscribed) {
                                if (!subscribed && Notification.permission !== 'denied') {
                                    showBanner();
                                }
                            });
                        }
                    }, 500);
                }
            });
        });

        var pwaBanner = document.getElementById('pwa-install-banner');
        if (pwaBanner) {
            observer.observe(pwaBanner, { attributes: true, attributeFilter: ['style'] });
        }

        // Fallback: check periodically in case observer misses it
        var checkCount = 0;
        var fallbackInterval = setInterval(function () {
            checkCount++;
            if (!isPwaBannerVisible()) {
                clearInterval(fallbackInterval);
                observer.disconnect();
                if (!isDismissed()) {
                    PN.isSubscribed().then(function (subscribed) {
                        if (!subscribed && Notification.permission !== 'denied') {
                            showBanner();
                        }
                    });
                }
            }
            if (checkCount > 30) { // Stop after 60s
                clearInterval(fallbackInterval);
            }
        }, CHECK_INTERVAL);
    }

    // Enable button
    enableBtn.addEventListener('click', function () {
        enableBtn.disabled = true;
        enableBtn.textContent = '...';

        PN.subscribe().then(function (result) {
            hideBanner();
            if (result && result.success && window.showToast) {
                window.showToast('Powiadomienia push włączone!', 'success');
            }
            // Notify bell icon to update
            window.dispatchEvent(new CustomEvent('push-subscription-changed', { detail: { subscribed: true } }));
        }).catch(function (err) {
            enableBtn.disabled = false;
            enableBtn.textContent = 'Włącz';
            if (err.message && err.message.includes('denied')) {
                hideBanner();
            }
            if (window.showToast) {
                window.showToast('Nie udało się włączyć powiadomień', 'error');
            }
        });
    });

    // Dismiss button
    dismissBtn.addEventListener('click', function () {
        hideBanner();
        localStorage.setItem(DISMISS_KEY, Date.now().toString());
    });

    // Wait a bit for page to load, then try showing
    setTimeout(tryShow, 1500);
})();
