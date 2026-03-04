/**
 * Push Notifications Module
 * Exposes window.PushNotifications API
 */
(function () {
    'use strict';

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

    var vapidPublicKey = null;

    // Read VAPID key from meta tag
    var vapidMeta = document.querySelector('meta[name="vapid-public-key"]');
    if (vapidMeta) {
        vapidPublicKey = vapidMeta.getAttribute('content');
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
                        device_name: deviceName || navigator.userAgent.split('(')[1]?.split(')')[0] || ''
                    })
                }).then(function (res) { return res.json(); });
            });
        },

        /**
         * Unsubscribe from push notifications
         */
        unsubscribe: function () {
            if (!this.isSupported()) return Promise.resolve();

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
        }
    };
})();
