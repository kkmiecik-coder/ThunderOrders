/**
 * Przełącznik „Powiadomienia o pupilach" (push + e-mail) na stronie profilu.
 * Niezależny od push-settings.js — tamten kończy działanie, gdy przeglądarka nie
 * obsługuje pusha, a ten przełącznik steruje też mailami.
 */
(function () {
    'use strict';

    var toggle = document.getElementById('petUpdatesToggle');
    if (!toggle) return;

    var csrfMeta = document.querySelector('meta[name="csrf-token"]');
    var PREFS_URL = '/notifications/preferences';

    // Zablokowany do czasu wczytania stanu z serwera — bez tego pokazywałby „włączone" także przy błędzie
    toggle.disabled = true;
    fetch(PREFS_URL)
        .then(function (r) { return r.json(); })
        .then(function (prefs) {
            if (prefs && 'pet_updates' in prefs) toggle.checked = !!prefs.pet_updates;
        })
        .catch(function () {})
        .then(function () { toggle.disabled = false; });

    toggle.addEventListener('change', function () {
        var wlaczone = toggle.checked;
        fetch(PREFS_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfMeta ? csrfMeta.getAttribute('content') : ''
            },
            body: JSON.stringify({ pet_updates: wlaczone })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data && data.success && window.showToast) {
                    window.showToast(wlaczone ? 'Powiadomienia o pupilach włączone' : 'Powiadomienia o pupilach wyłączone', 'success');
                }
            })
            .catch(function () {
                toggle.checked = !wlaczone;
                if (window.showToast) window.showToast('Błąd zapisu preferencji', 'error');
            });
    });
})();
