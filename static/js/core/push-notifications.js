/**
 * Push Notifications Module
 * Exposes window.PushNotifications API
 *
 * Includes automatic subscription health check:
 * - Scenario A: localStorage flag exists but browser subscription expired -> silent re-subscribe
 * - Scenario B: localStorage cleared but backend knows user had subscriptions -> prompt user
 */
(function () {
    'use strict';

    var OPTED_IN_KEY = 'push-opted-in';

    function urlBase64ToUint8Array(base64String) {
        var padding = '='.repeat((4 - base64String.length % 4) % 4);
        var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
        var rawData = atob(base64);
        var outputArray = new Uint8Array(rawData.length);
        for (var i = 0; i < rawData.length; i++) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    function getCSRFToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function getDeviceName() {
        try {
            return navigator.userAgent.split('(')[1].split(')')[0];
        } catch (e) {
            return '';
        }
    }

    var vapidPublicKey = null;

    // Read VAPID key from meta tag
    var vapidMeta = document.querySelector('meta[name="vapid-public-key"]');
    if (vapidMeta) {
        vapidPublicKey = vapidMeta.getAttribute('content');
    }

    /**
     * Register subscription with the backend (shared by subscribe + healthCheck).
     */
    function sendSubscriptionToServer(subscription, deviceName) {
        var subJSON = subscription.toJSON();
        return fetch('/notifications/subscribe', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                endpoint: subJSON.endpoint,
                keys: subJSON.keys,
                device_name: deviceName || getDeviceName()
            })
        }).then(function (res) { return res.json(); });
    }

    window.PushNotifications = {
        /**
         * Check if push is supported
         */
        isSupported: function () {
            return 'serviceWorker' in navigator && 'PushManager' in window;
        },

        /**
         * Get current permission state: 'granted', 'denied', 'default'
         */
        getPermissionState: function () {
            if (!this.isSupported()) return 'unsupported';
            return Notification.permission;
        },

        /**
         * Check if the user has an active push subscription
         */
        isSubscribed: function () {
            if (!this.isSupported()) return Promise.resolve(false);
            return navigator.serviceWorker.ready.then(function (reg) {
                return reg.pushManager.getSubscription().then(function (sub) {
                    return !!sub;
                });
            });
        },

        /**
         * Subscribe to push notifications
         */
        subscribe: function (deviceName) {
            if (!this.isSupported()) {
                return Promise.reject(new Error('Push not supported'));
            }
            if (!vapidPublicKey) {
                return Promise.reject(new Error('VAPID key not available'));
            }

            return navigator.serviceWorker.ready.then(function (reg) {
                return reg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
                });
            }).then(function (subscription) {
                // Mark that user opted in
                try { localStorage.setItem(OPTED_IN_KEY, '1'); } catch (e) {}
                return sendSubscriptionToServer(subscription, deviceName);
            });
        },

        /**
         * Unsubscribe from push notifications
         */
        unsubscribe: function () {
            if (!this.isSupported()) return Promise.resolve();

            // Clear opt-in flag
            try { localStorage.removeItem(OPTED_IN_KEY); } catch (e) {}

            return navigator.serviceWorker.ready.then(function (reg) {
                return reg.pushManager.getSubscription();
            }).then(function (subscription) {
                if (!subscription) return { success: true };
                var endpoint = subscription.endpoint;
                return subscription.unsubscribe().then(function () {
                    return fetch('/notifications/unsubscribe', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCSRFToken()
                        },
                        body: JSON.stringify({ endpoint: endpoint })
                    }).then(function (res) { return res.json(); });
                });
            });
        },

        /**
         * Send a test notification
         */
        sendTestNotification: function () {
            return fetch('/notifications/test', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                }
            }).then(function (res) { return res.json(); });
        },

        /**
         * Health check - automatically recover expired/lost push subscriptions.
         *
         * Scenario A: localStorage has opted-in flag, but browser subscription is gone.
         *   - If permission still granted -> silent re-subscribe
         *   - If permission default (cleared) -> ask permission again, then subscribe
         *
         * Scenario B: localStorage cleared (no flag), but backend knows user had active subs.
         *   - Force-show the push banner to prompt user.
         */
        healthCheck: function () {
            var self = this;
            if (!self.isSupported() || !vapidPublicKey) return;
            if (Notification.permission === 'denied') return;

            navigator.serviceWorker.ready.then(function (reg) {
                return reg.pushManager.getSubscription().then(function (browserSub) {
                    var hasLocalFlag = false;
                    try { hasLocalFlag = localStorage.getItem(OPTED_IN_KEY) === '1'; } catch (e) {}

                    if (browserSub) {
                        // Browser has a valid subscription - ensure localStorage flag is set
                        if (!hasLocalFlag) {
                            try { localStorage.setItem(OPTED_IN_KEY, '1'); } catch (e) {}
                        }
                        // Also re-send to backend to keep it fresh (endpoint may have changed)
                        sendSubscriptionToServer(browserSub).catch(function () {});
                        return;
                    }

                    // Browser has NO subscription

                    if (hasLocalFlag) {
                        // SCENARIO A: User opted in before, subscription expired
                        console.log('[Push] Subscription expired, attempting silent re-subscribe...');

                        if (Notification.permission === 'granted') {
                            // Permission still granted - silent re-subscribe
                            reg.pushManager.subscribe({
                                userVisibleOnly: true,
                                applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
                            }).then(function (newSub) {
                                console.log('[Push] Silent re-subscribe successful');
                                sendSubscriptionToServer(newSub).catch(function () {});
                                window.dispatchEvent(new CustomEvent('push-subscription-changed', {
                                    detail: { subscribed: true }
                                }));
                            }).catch(function (err) {
                                console.warn('[Push] Silent re-subscribe failed:', err);
                            });
                        } else {
                            // Permission was reset (browser data partially cleared)
                            // Need to ask again - trigger the banner
                            console.log('[Push] Permission reset, requesting again...');
                            Notification.requestPermission().then(function (perm) {
                                if (perm === 'granted') {
                                    reg.pushManager.subscribe({
                                        userVisibleOnly: true,
                                        applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
                                    }).then(function (newSub) {
                                        console.log('[Push] Re-subscribe after permission grant successful');
                                        sendSubscriptionToServer(newSub).catch(function () {});
                                        window.dispatchEvent(new CustomEvent('push-subscription-changed', {
                                            detail: { subscribed: true }
                                        }));
                                    }).catch(function (err) {
                                        console.warn('[Push] Re-subscribe failed:', err);
                                    });
                                } else {
                                    // User denied - clear flag
                                    try { localStorage.removeItem(OPTED_IN_KEY); } catch (e) {}
                                }
                            });
                        }
                        return;
                    }

                    // SCENARIO B: No local flag + no browser sub
                    // Check if backend knows this user had active subscriptions
                    fetch('/notifications/has-active', { credentials: 'same-origin' })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (data.has_active) {
                                // Backend says user had subs - force show banner
                                console.log('[Push] Backend has active subs, forcing push banner...');
                                window.dispatchEvent(new CustomEvent('push-force-banner'));
                            }
                        })
                        .catch(function () {});
                });
            });
        }
    };

    // Run health check after page loads
    setTimeout(function () {
        window.PushNotifications.healthCheck();
    }, 3000);
})();
