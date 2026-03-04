/**
 * Push Notification Settings (profile page)
 */
(function () {
    'use strict';

    var mainToggle = document.getElementById('pushMainToggle');
    var testBtn = document.getElementById('pushTestBtn');
    var categoryToggles = document.querySelectorAll('.push-category-toggle');
    var categoriesSection = document.getElementById('pushCategories');
    var devicesInfo = document.getElementById('pushDevicesInfo');
    var permissionWarning = document.getElementById('pushPermissionWarning');

    if (!mainToggle) return;

    var PN = window.PushNotifications;
    if (!PN || !PN.isSupported()) {
        // Push not supported - hide the section
        var card = document.getElementById('pushNotificationsCard');
        if (card) card.style.display = 'none';
        return;
    }

    // Initialize state
    function init() {
        var permState = PN.getPermissionState();
        if (permState === 'denied') {
            if (permissionWarning) permissionWarning.style.display = 'block';
            mainToggle.disabled = true;
            return;
        }

        PN.isSubscribed().then(function (subscribed) {
            mainToggle.checked = subscribed;
            toggleCategories(subscribed);

            if (subscribed) {
                loadPreferences();
                loadDevices();
            }
        });
    }

    function toggleCategories(show) {
        if (categoriesSection) {
            categoriesSection.style.display = show ? 'block' : 'none';
        }
        if (testBtn) {
            testBtn.style.display = show ? 'inline-flex' : 'none';
        }
        if (devicesInfo) {
            devicesInfo.style.display = show ? 'block' : 'none';
        }
    }

    function loadPreferences() {
        fetch('/notifications/preferences')
            .then(function (r) { return r.json(); })
            .then(function (prefs) {
                categoryToggles.forEach(function (toggle) {
                    var key = toggle.dataset.category;
                    if (key in prefs) {
                        toggle.checked = prefs[key];
                    }
                });
            })
            .catch(function () {});
    }

    function loadDevices() {
        if (!devicesInfo) return;
        fetch('/notifications/subscriptions')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var count = data.subscriptions ? data.subscriptions.length : 0;
                var countEl = devicesInfo.querySelector('.push-devices-count');
                if (countEl) {
                    countEl.textContent = count + ' ' + (count === 1 ? 'urządzenie' : 'urządzeń');
                }
            })
            .catch(function () {});
    }

    function savePreferences() {
        var prefs = {};
        categoryToggles.forEach(function (toggle) {
            prefs[toggle.dataset.category] = toggle.checked;
        });

        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        fetch('/notifications/preferences', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken ? csrfToken.getAttribute('content') : ''
            },
            body: JSON.stringify(prefs)
        }).then(function (r) { return r.json(); })
          .then(function (data) {
              if (data.success && window.showToast) {
                  window.showToast('Preferencje zapisane', 'success');
              }
          })
          .catch(function () {
              if (window.showToast) window.showToast('Błąd zapisu preferencji', 'error');
          });
    }

    // Main toggle handler
    mainToggle.addEventListener('change', function () {
        if (this.checked) {
            PN.subscribe().then(function (result) {
                if (result && result.success) {
                    toggleCategories(true);
                    loadPreferences();
                    loadDevices();
                    if (window.showToast) window.showToast('Powiadomienia push włączone', 'success');
                }
            }).catch(function (err) {
                mainToggle.checked = false;
                if (err.message && err.message.includes('denied')) {
                    if (permissionWarning) permissionWarning.style.display = 'block';
                }
                if (window.showToast) window.showToast('Nie udało się włączyć powiadomień', 'error');
            });
        } else {
            PN.unsubscribe().then(function () {
                toggleCategories(false);
                if (window.showToast) window.showToast('Powiadomienia push wyłączone', 'success');
            });
        }
    });

    // Category toggle handlers
    categoryToggles.forEach(function (toggle) {
        toggle.addEventListener('change', savePreferences);
    });

    // Test button handler
    if (testBtn) {
        testBtn.addEventListener('click', function () {
            testBtn.disabled = true;
            PN.sendTestNotification().then(function (data) {
                if (window.showToast) {
                    window.showToast(data.message || 'Wysłano', data.success ? 'success' : 'error');
                }
            }).catch(function () {
                if (window.showToast) window.showToast('Błąd wysyłania', 'error');
            }).finally(function () {
                testBtn.disabled = false;
            });
        });
    }

    init();
})();
