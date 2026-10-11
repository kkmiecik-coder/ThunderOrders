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

    // Zablokowany do czasu wczytania stanu z serwera — bez tego pokazywałby „włączone" także przy błędzie.
    // Gdy stanu nie da się wczytać, zostaje zablokowany (is-unavailable) — nie wraca do `checked`
    // z szablonu, bo to nie musi być prawda.
    toggle.disabled = true;
    fetch(PREFS_URL, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
        .then(function (r) {
            if (!r.ok || (r.headers.get('Content-Type') || '').indexOf('application/json') === -1) throw new Error('prefs');
            return r.json();
        })
        .then(function (prefs) {
            if (!prefs || !('pet_updates' in prefs)) throw new Error('prefs');
            toggle.checked = !!prefs.pet_updates;
            toggle.disabled = false;
        })
        .catch(function () {
            var label = toggle.closest('.toggle-switch') || toggle;
            label.classList.add('is-unavailable');
            label.title = 'Nie udało się wczytać ustawienia — odśwież stronę.';
            toggle.setAttribute('aria-description', 'Nie udało się wczytać ustawienia — odśwież stronę.');
        });

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
