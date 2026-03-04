/**
 * Push Bell Icon - Desktop dropdown + Mobile sidebar
 * Manages push notification toggle from topbar/sidebar.
 */
(function () {
    'use strict';

    var PN = window.PushNotifications;
    if (!PN || !PN.isSupported()) {
        // Hide bell elements if push not supported
        var bells = document.querySelectorAll('.push-bell-btn, .mobile-push-btn');
        bells.forEach(function (el) { el.style.display = 'none'; });
        return;
    }

    // === Desktop Bell ===
    var bellBtn = document.getElementById('pushBellBtn');
    var bellBadge = document.getElementById('pushBellBadge');
    var bellDropdown = document.getElementById('pushBellDropdown');
    var bellEnableBtn = document.getElementById('pushBellEnableBtn');
    var bellDisableBtn = document.getElementById('pushBellDisableBtn');
    var bellSettingsLink = document.getElementById('pushBellSettingsLink');
    var bellStateOff = document.getElementById('pushBellStateOff');
    var bellStateOn = document.getElementById('pushBellStateOn');

    // === Mobile Bell ===
    var mobileBellBtn = document.getElementById('mobilePushBtn');
    var mobileBellBadge = document.getElementById('mobilePushBadge');
    var mobileBellText = document.getElementById('mobilePushText');

    var isSubscribed = false;

    function updateUI(subscribed) {
        isSubscribed = subscribed;

        // Desktop badge
        if (bellBadge) {
            bellBadge.style.display = subscribed ? 'none' : 'block';
        }

        // Desktop dropdown states
        if (bellStateOff) bellStateOff.style.display = subscribed ? 'none' : 'block';
        if (bellStateOn) bellStateOn.style.display = subscribed ? 'block' : 'none';

        // Desktop bell icon style
        if (bellBtn) {
            bellBtn.classList.toggle('push-bell-active', subscribed);
        }

        // Mobile badge
        if (mobileBellBadge) {
            mobileBellBadge.className = 'mobile-push-badge ' + (subscribed ? 'mobile-push-badge-on' : 'mobile-push-badge-off');
        }

        // Mobile text
        if (mobileBellText) {
            mobileBellText.textContent = subscribed ? 'Powiadomienia ON' : 'Powiadomienia';
        }
    }

    function init() {
        // Check permission first
        if (Notification.permission === 'denied') {
            updateUI(false);
            if (bellEnableBtn) bellEnableBtn.style.display = 'none';
            return;
        }

        PN.isSubscribed().then(function (subscribed) {
            updateUI(subscribed);
        });
    }

    // Desktop: toggle dropdown
    if (bellBtn && bellDropdown) {
        bellBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            bellDropdown.classList.toggle('active');
        });

        // Close on click outside
        document.addEventListener('click', function (e) {
            if (bellDropdown.classList.contains('active') &&
                !bellDropdown.contains(e.target) &&
                !bellBtn.contains(e.target)) {
                bellDropdown.classList.remove('active');
            }
        });
    }

    // Desktop: enable push
    if (bellEnableBtn) {
        bellEnableBtn.addEventListener('click', function () {
            bellEnableBtn.disabled = true;
            bellEnableBtn.textContent = '...';

            PN.subscribe().then(function (result) {
                if (result && result.success) {
                    updateUI(true);
                    bellDropdown.classList.remove('active');
                    if (window.showToast) window.showToast('Powiadomienia push włączone!', 'success');
                    window.dispatchEvent(new CustomEvent('push-subscription-changed', { detail: { subscribed: true } }));
                    // Hide the bottom banner if visible
                    var pushBanner = document.getElementById('push-notif-banner');
                    if (pushBanner) pushBanner.style.display = 'none';
                }
            }).catch(function () {
                if (window.showToast) window.showToast('Nie udało się włączyć powiadomień', 'error');
            }).finally(function () {
                bellEnableBtn.disabled = false;
                bellEnableBtn.textContent = 'Włącz powiadomienia';
            });
        });
    }

    // Desktop: disable push
    if (bellDisableBtn) {
        bellDisableBtn.addEventListener('click', function () {
            bellDisableBtn.disabled = true;

            PN.unsubscribe().then(function () {
                updateUI(false);
                bellDropdown.classList.remove('active');
                if (window.showToast) window.showToast('Powiadomienia push wyłączone', 'success');
                window.dispatchEvent(new CustomEvent('push-subscription-changed', { detail: { subscribed: false } }));
            }).catch(function () {
                if (window.showToast) window.showToast('Błąd podczas wyłączania', 'error');
            }).finally(function () {
                bellDisableBtn.disabled = false;
            });
        });
    }

    // Mobile: push button
    if (mobileBellBtn) {
        mobileBellBtn.addEventListener('click', function () {
            if (isSubscribed) {
                // Navigate to profile push settings
                window.location.href = '/profile/#push';
            } else {
                mobileBellBtn.style.opacity = '0.5';
                mobileBellBtn.style.pointerEvents = 'none';

                PN.subscribe().then(function (result) {
                    if (result && result.success) {
                        updateUI(true);
                        if (window.showToast) window.showToast('Powiadomienia push włączone!', 'success');
                        window.dispatchEvent(new CustomEvent('push-subscription-changed', { detail: { subscribed: true } }));
                        var pushBanner = document.getElementById('push-notif-banner');
                        if (pushBanner) pushBanner.style.display = 'none';
                    }
                }).catch(function () {
                    if (window.showToast) window.showToast('Nie udało się włączyć powiadomień', 'error');
                }).finally(function () {
                    mobileBellBtn.style.opacity = '1';
                    mobileBellBtn.style.pointerEvents = 'auto';
                });
            }
        });
    }

    // Listen for subscription changes from other components (banner, profile)
    window.addEventListener('push-subscription-changed', function (e) {
        if (e.detail) {
            updateUI(e.detail.subscribed);
        }
    });

    init();
})();
