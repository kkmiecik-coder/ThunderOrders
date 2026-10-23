/**
 * Czas polski w przeglądarce — niezależnie od strefy, w której siedzi użytkownik.
 *
 * Serwer podaje chwile jako ISO w UTC z `Z` (np. `2026-10-30T19:00:00Z`), więc
 * `Date.parse(...)` i odliczania są poprawne w każdej strefie. Do pokazania
 * człowiekowi każda chwila idzie przez `formatPlDateTime` (Europe/Warsaw).
 *
 * Pola `datetime-local` w panelu to polski zegar ścienny — porównania
 * „w przeszłości / w przyszłości" robimy na epokach z `plWallToEpoch`, a nie
 * przez `new Date(value)` (to czytałoby wartość w strefie przeglądarki).
 *
 * Bez zależności; ładowany w trzech szablonach bazowych.
 */
(function () {
    'use strict';

    var PL_TZ = 'Europe/Warsaw';

    // Formatter części zegara ściennego w Warszawie (24 h) — do przeliczeń, nie do wyświetlania.
    var czesciFormatter = new Intl.DateTimeFormat('en-US', {
        timeZone: PL_TZ, hourCycle: 'h23',
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit'
    });

    function doDaty(wartosc) {
        if (wartosc === null || wartosc === undefined || wartosc === '') return null;
        var d = wartosc instanceof Date ? wartosc : new Date(wartosc);
        return isNaN(d.getTime()) ? null : d;
    }

    /**
     * Chwila (ISO z `Z`, epoka w ms albo Date) -> tekst w czasie polskim.
     * Bez `opts`: `dd.mm.rrrr gg:mm` — jak `format_datetime('%d.%m.%Y %H:%M')` na serwerze.
     * Z `opts`: `Intl.DateTimeFormat('pl-PL', opts)` (strefy nie da się nadpisać).
     * Pusta / błędna wartość -> ''.
     */
    function formatPlDateTime(wartosc, opts) {
        var d = doDaty(wartosc);
        if (!d) return '';
        if (!opts) {
            var c = plWallParts(d);
            return dwieCyfry(c.day) + '.' + dwieCyfry(c.month) + '.' + c.year + ' ' +
                dwieCyfry(c.hour) + ':' + dwieCyfry(c.minute);
        }
        var opcje = Object.assign({}, opts, { timeZone: PL_TZ });
        return new Intl.DateTimeFormat('pl-PL', opcje).format(d);
    }

    function dwieCyfry(n) {
        return String(n).padStart(2, '0');
    }

    /** Części polskiego zegara ściennego dla chwili: {year, month (1–12), day, hour, minute, second}. */
    function plWallParts(wartosc) {
        var d = doDaty(wartosc);
        if (!d) return null;
        var czesci = {};
        czesciFormatter.formatToParts(d).forEach(function (p) {
            if (p.type !== 'literal') czesci[p.type] = parseInt(p.value, 10);
        });
        return czesci;
    }

    /** Polska data chwili jako `RRRR-MM-DD` (np. „dzisiaj" do porównań z kluczami dni z serwera). */
    function plDateKey(wartosc) {
        var c = plWallParts(wartosc);
        if (!c) return '';
        return c.year + '-' + dwieCyfry(c.month) + '-' + dwieCyfry(c.day);
    }

    // Polski zegar ścienny chwili `ms` zapisany jako epoka „UTC" — różnica z `ms` to offset strefy.
    function zegarJakoUtc(ms) {
        var c = plWallParts(ms);
        return Date.UTC(c.year, c.month - 1, c.day, c.hour, c.minute, c.second);
    }

    function offsetPl(ms) {
        var calaSekunda = Math.floor(ms / 1000) * 1000;
        return zegarJakoUtc(calaSekunda) - calaSekunda;
    }

    /**
     * Polski zegar ścienny `RRRR-MM-DDTGG:MM[:SS]` (np. z `datetime-local`) -> epoka w ms.
     * Jak `pl_input_to_utc` w Pythonie: podwójna godzina jesienią -> pierwsze wystąpienie,
     * nieistniejąca godzina wiosną -> offset sprzed zmiany. Błędny tekst -> NaN.
     */
    function plWallToEpoch(tekst) {
        var m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/.exec(tekst || '');
        if (!m) return NaN;
        var jakoUtc = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
        var DOBA = 86400000;
        var offsetPrzed = offsetPl(jakoUtc - DOBA);
        var offsetPo = offsetPl(jakoUtc + DOBA);
        var kandydaci = [jakoUtc - offsetPrzed, jakoUtc - offsetPo];
        for (var i = 0; i < kandydaci.length; i++) {
            if (zegarJakoUtc(kandydaci[i]) === jakoUtc) return kandydaci[i];
        }
        return jakoUtc - offsetPrzed;  // godzina w „dziurze" wiosennej zmiany czasu
    }

    /**
     * Date, którego LOKALNE pola (getHours(), getDate()…) pokazują polski zegar ścienny.
     * Tylko do wyświetlania i grupowania (np. wykresy Chart.js na osi czasu przeglądarki) —
     * nie porównuj go z prawdziwymi chwilami.
     */
    function plWallClockDate(wartosc) {
        var c = plWallParts(wartosc);
        if (!c) return null;
        return new Date(c.year, c.month - 1, c.day, c.hour, c.minute, c.second);
    }

    window.formatPlDateTime = formatPlDateTime;
    window.plWallParts = plWallParts;
    window.plDateKey = plDateKey;
    window.plWallToEpoch = plWallToEpoch;
    window.plWallClockDate = plWallClockDate;
})();
