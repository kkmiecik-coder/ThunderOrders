/**
 * Haptics — wibracje dla pupili (spec §4.5), cienka nakładka na navigator.vibrate.
 *
 * API (kontrakt dla pets.js / pet-card.js / towarzysza z etapu 5):
 *   Haptics.tap()          — krótkie stuknięcie (10 ms) — pat pat, drobne akcje
 *   Haptics.pattern(name)  — nazwany wzór: 'tap' | 'pat' | 'success' | 'hatch' (wyklucie: [30,50,30,50,80])
 *   Haptics.enabled()      — czy wibracje zadziałają (jest API i użytkownik nie prosi o ograniczenie ruchu)
 *
 * Zasady: wyłączone przy prefers-reduced-motion; brak API (iOS Safari) → cicho, bez obietnic w UI.
 * Wzór bazowy z wms-mobile.js:57-61 (tamtego pliku nie ruszamy).
 */
(function () {
    'use strict';

    if (window.Haptics) return;   // plik ładuje się na kilku stronach (dashboard + domek)
    var PATTERNS = {
        tap: 10,
        pat: 10,
        success: [12, 40, 12],
        hatch: [30, 50, 30, 50, 80]
    };

    function reducedMotion() {
        return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

    function enabled() {
        return typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function' && !reducedMotion();
    }

    function vibrate(pattern) {
        if (!enabled()) return false;
        // Chrome bez wcześniejszego gestu użytkownika odmawia i loguje błąd w konsoli — nie próbujemy
        if (navigator.userActivation && !navigator.userActivation.hasBeenActive) return false;
        try {
            return navigator.vibrate(pattern) !== false;
        } catch (e) {
            return false;
        }
    }

    window.Haptics = {
        tap: function () { return vibrate(PATTERNS.tap); },
        pattern: function (name) {
            if (!Object.prototype.hasOwnProperty.call(PATTERNS, name)) return false;
            return vibrate(PATTERNS[name]);
        },
        enabled: enabled
    };
})();
