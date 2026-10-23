/**
 * Podpowiedź z godziną w innych miastach przy wyświetlanych godzinach.
 *
 * Serwer (filtr `pl_time`) wypisuje czas polski w `<time datetime="...Z" class="tz-time">`
 * — to jest główna wartość i bez JS zostaje sama. Lista miast przychodzi raz na stronę
 * w `data-display-timezones` na `<body>` (ustawienia admina, domyślnie Seul); pusta lista
 * = brak atrybutu = brak podpowiedzi.
 *
 * Mysz: najechanie pokazuje, zjechanie chowa. Dotyk: tapnięcie otwiera / zamyka (klik nie
 * idzie dalej, np. do linku wiersza), tapnięcie obok albo Esc zamyka. Słuchacze są
 * delegowane na `document`, więc działają też dla godzin wstawionych później.
 *
 * Bez zależności; ładowany w szablonach bazowych (base.html, offers/base_offers.html).
 */
(function () {
    'use strict';

    var PL_TZ = 'Europe/Warsaw';
    var TIP_ID = 'tz-tooltip';
    var MARGINES = 8;

    var strefy = null;
    var formattery = {};
    var tip = null;
    var aktywny = null;
    var ostatniWskaznik = 'mouse';

    /** Miasta z `<body data-display-timezones>`: [{label, tz}]. Czytane leniwie, raz. */
    function listaStref() {
        if (strefy) return strefy;
        strefy = [];
        var surowe = document.body && document.body.getAttribute('data-display-timezones');
        if (!surowe) return strefy;
        try {
            var dane = JSON.parse(surowe);
            if (Array.isArray(dane)) strefy = dane;
        } catch (e) {
            console.warn('tz-tooltip: nieczytelna lista stref', e);
        }
        return strefy;
    }

    /** Formatter strefy (cache); null, gdy przeglądarka nie zna strefy. */
    function formatter(tz) {
        if (!(tz in formattery)) {
            try {
                formattery[tz] = new Intl.DateTimeFormat('pl-PL', {
                    timeZone: tz, hourCycle: 'h23',
                    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
                });
            } catch (e) {
                formattery[tz] = null;
            }
        }
        return formattery[tz];
    }

    /** Chwila w strefie -> `31.10, 03:00`. */
    function wStrefie(data, tz) {
        var f = formatter(tz);
        if (!f) return null;
        var c = {};
        f.formatToParts(data).forEach(function (p) {
            if (p.type !== 'literal') c[p.type] = p.value;
        });
        return c.day + '.' + c.month + ', ' + c.hour + ':' + c.minute;
    }

    function wiersz(etykieta, wartosc, klasa) {
        var row = document.createElement('div');
        row.className = 'tz-tooltip__row' + (klasa ? ' ' + klasa : '');
        var l = document.createElement('span');
        l.className = 'tz-tooltip__label';
        l.textContent = etykieta;        // etykietę wpisuje admin — tylko textContent
        var v = document.createElement('span');
        v.className = 'tz-tooltip__value';
        v.textContent = wartosc;
        row.append(l, v);
        return row;
    }

    function ustaw(el) {
        var r = el.getBoundingClientRect();
        var w = tip.offsetWidth;
        var h = tip.offsetHeight;
        var top = r.top - h - MARGINES;
        if (top < MARGINES) top = r.bottom + MARGINES;       // brak miejsca nad — pod godziną
        var left = r.left + r.width / 2 - w / 2;
        left = Math.max(MARGINES, Math.min(left, window.innerWidth - w - MARGINES));
        tip.style.top = top + 'px';
        tip.style.left = left + 'px';
    }

    function pokaz(el) {
        var data = new Date(el.getAttribute('datetime'));
        if (isNaN(data.getTime())) return;

        var miasta = [];
        listaStref().forEach(function (s) {
            var t = s && wStrefie(data, s.tz);
            if (t) miasta.push(wiersz(s.label, t));
        });
        if (!miasta.length) return;

        ukryj();
        if (!tip) {
            tip = document.createElement('div');
            tip.id = TIP_ID;
            tip.className = 'tz-tooltip';
            tip.setAttribute('role', 'tooltip');
            document.body.appendChild(tip);
        }
        tip.textContent = '';
        tip.appendChild(wiersz('Polska', wStrefie(data, PL_TZ), 'tz-tooltip__row--pl'));
        miasta.forEach(function (m) { tip.appendChild(m); });
        tip.hidden = false;
        ustaw(el);

        aktywny = el;
        el.classList.add('tz-time--open');
        el.setAttribute('aria-describedby', TIP_ID);
    }

    function ukryj() {
        if (aktywny) {
            aktywny.classList.remove('tz-time--open');
            aktywny.removeAttribute('aria-describedby');
            aktywny = null;
        }
        if (tip) tip.hidden = true;
    }

    function godzina(cel) {
        return cel && cel.closest ? cel.closest('time.tz-time') : null;
    }

    // Rodzaj wskaźnika ostatniej interakcji — klik z dotyku przełącza podpowiedź, klik myszą nie
    document.addEventListener('pointerdown', function (e) {
        ostatniWskaznik = e.pointerType || 'mouse';
    }, true);

    document.addEventListener('pointerover', function (e) {
        if (e.pointerType !== 'mouse') return;
        var el = godzina(e.target);
        if (el && el !== aktywny) pokaz(el);
    });

    document.addEventListener('pointerout', function (e) {
        if (e.pointerType !== 'mouse' || !aktywny) return;
        if (godzina(e.target) === aktywny && !aktywny.contains(e.relatedTarget)) ukryj();
    });

    // Faza przechwytywania: tapnięcie w godzinę nie może uruchomić linku / wiersza pod spodem
    document.addEventListener('click', function (e) {
        var el = godzina(e.target);
        if (el && ostatniWskaznik !== 'mouse' && listaStref().length) {
            e.preventDefault();
            e.stopPropagation();
            if (el === aktywny) ukryj(); else pokaz(el);
            return;
        }
        if (aktywny && el !== aktywny) ukryj();
    }, true);

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') ukryj();
    });

    // Podpowiedź stoi w miejscu (position: fixed) — przy przewinięciu i zmianie rozmiaru znika
    window.addEventListener('scroll', function () { if (aktywny) ukryj(); }, { capture: true, passive: true });
    window.addEventListener('resize', function () { if (aktywny) ukryj(); });
})();
