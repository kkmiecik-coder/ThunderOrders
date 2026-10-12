/**
 * Świat pupili — scena „warsztat” (spec v3 §6.5): ściana warsztatu z tablicą na narzędzia.
 *
 * - ramka ze zdjęciem = wybór towarzysza (żywi poza szpitalem + „automatycznie”), włącznik i przełącznik
 *   żartów (POST /towarzysz, pola enabled i jokes; opis żartów nie wymienia ich rodzajów — niespodzianka),
 * - dzwonek = przełącznik „Powiadomienia o pupilach” (GET/POST /notifications/preferences {pet_updates}),
 * - książeczka = zasady gry jako kafelki z ikonami (liczby z state.config / state.night, nie na sztywno).
 * Wygląd (feedback: „najmniej growa scena”): karty przypięte pinezkami do perforowanej tablicy (lekko
 * przekrzywione, w rzędzie równej wysokości), obok kart narzędzia na kołkach (młotek, klucz, śrubokręt,
 * zębatka) i półka z puszkami farby; na szerokim ekranie po bokach tablicy zębatki i piła na ścianie.
 * Ozdoby: aria-hidden, bez zdarzeń. Pełny ekran (spec v3.1 §3.5): ściana z desek to tło całej sceny; na
 * niskim ekranie przewija się wnętrze (.pets-scroll), nie strona.
 * Rejestruje się w window.PetsWorld.scenes.warsztat.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.warsztat) return;

    var PREFS_URL = '/notifications/preferences';
    var GENERIC_ERROR = 'Coś poszło nie tak, spróbuj za chwilę.';

    var ART = {
        frame: '<svg viewBox="0 0 64 64" aria-hidden="true" focusable="false">' +
            '<rect x="6" y="8" width="52" height="46" rx="5" fill="#c99a6b" stroke="#a87b4f" stroke-width="2"/>' +
            '<rect x="13" y="15" width="38" height="32" rx="3" fill="#ffe9d6"/>' +
            '<circle cx="32" cy="33" r="9" fill="#f6a65b"/><path d="M24 27l-3-8 8 5zM40 27l3-8-8 5z" fill="#f6a65b"/>' +
            '<circle cx="28.5" cy="32" r="1.6" fill="#3B2A3A"/><circle cx="35.5" cy="32" r="1.6" fill="#3B2A3A"/>' +
            '<path d="M30 36.5q2 1.6 4 0" stroke="#3B2A3A" stroke-width="1.4" fill="none" stroke-linecap="round"/>' +
            '<path d="M26 8l6-5 6 5" stroke="#a87b4f" stroke-width="2" fill="none"/></svg>',
        bell: '<svg viewBox="0 0 64 64" aria-hidden="true" focusable="false">' +
            '<path d="M32 9c-10 0-16 8-16 18v10l-5 7h42l-5-7V27c0-10-6-18-16-18z" fill="#ffd36b" stroke="#e0a93b" stroke-width="2"/>' +
            '<circle cx="32" cy="50" r="5" fill="#e0a93b"/><rect x="29" y="4" width="6" height="6" rx="3" fill="#e0a93b"/>' +
            '<path d="M22 24c1-5 4-8 8-9" stroke="#fff4c2" stroke-width="3" fill="none" stroke-linecap="round"/></svg>',
        book: '<svg viewBox="0 0 64 64" aria-hidden="true" focusable="false">' +
            '<path d="M8 14c8-3 16-3 24 2v38c-8-5-16-5-24-2z" fill="#ff8fab" stroke="#e86b8d" stroke-width="2"/>' +
            '<path d="M56 14c-8-3-16-3-24 2v38c8-5 16-5 24-2z" fill="#b99cff" stroke="#9a7ff0" stroke-width="2"/>' +
            '<path d="M14 24c5-1 9-1 13 1M14 31c5-1 9-1 13 1M37 25c4-2 8-2 13-1M37 32c4-2 8-2 13-1" stroke="#ffffff" stroke-width="2" stroke-linecap="round" opacity=".8"/></svg>'
    };

    var NS = ' aria-hidden="true" focusable="false"';

    function r1(v) { return Math.round(v * 10) / 10; }

    /** Zębatka: `teeth` trapezowych zębów między promieniem rIn a rOut, otwór w środku (evenodd). */
    function gearPath(cx, cy, rOut, rIn, teeth, hole) {
        var d = '';
        var step = Math.PI * 2 / teeth;
        for (var k = 0; k < teeth; k++) {
            var a = k * step;
            [[rIn, a - step * 0.3], [rOut, a - step * 0.17], [rOut, a + step * 0.17], [rIn, a + step * 0.3]].forEach(function (p, i) {
                d += (k === 0 && i === 0 ? 'M' : 'L') + r1(cx + Math.cos(p[1]) * p[0]) + ' ' + r1(cy + Math.sin(p[1]) * p[0]);
            });
            var b = a + step * 0.5;
            d += 'L' + r1(cx + Math.cos(b) * rIn) + ' ' + r1(cy + Math.sin(b) * rIn);
        }
        d += 'Z';
        if (hole) d += 'M' + r1(cx + hole) + ' ' + cy + 'a' + hole + ' ' + hole + ' 0 1 0 ' + (-2 * hole) + ' 0a' + hole + ' ' + hole + ' 0 1 0 ' + (2 * hole) + ' 0Z';
        return d;
    }

    // Narzędzia na kołkach tablicy (młotek, klucz, śrubokręt, zębatka) i półka z puszkami farby
    var RACK_SVG =
        '<svg class="pets-workshop__rack-art" viewBox="0 0 300 236" preserveAspectRatio="xMidYMid meet"' + NS + '>' +
        '<g class="pw-peg"><circle cx="60" cy="16" r="5"/><circle cx="131" cy="16" r="5"/><circle cx="199" cy="16" r="5"/><circle cx="252" cy="16" r="5"/></g>' +
        // młotek
        '<rect class="pw-wood" x="54" y="30" width="12" height="112" rx="5"/>' +
        '<path class="pw-metal" d="M30 22h52a6 6 0 0 1 6 6v12a6 6 0 0 1-6 6H44c-8 0-14-6-14-12z"/>' +
        '<path class="pw-shine" d="M40 28h36"/>' +
        // klucz płaski: otwarty pysk u góry, oczko na dole
        '<path class="pw-metal-line" d="M120 38a13 13 0 1 1 22 0"/>' +
        '<rect class="pw-metal" x="125" y="40" width="12" height="96" rx="6"/>' +
        '<circle class="pw-metal-line pw-metal-line--thin" cx="131" cy="146" r="11"/>' +
        // śrubokręt
        '<rect class="pw-grip" x="190" y="24" width="18" height="50" rx="8"/>' +
        '<path class="pw-grip-line" d="M195 34v30M199 34v30M203 34v30"/>' +
        '<rect class="pw-metal" x="196" y="73" width="6" height="62" rx="2"/>' +
        '<path class="pw-metal" d="M196 134h6l-1 8h-4z"/>' +
        // zębatka na sznurku
        '<path class="pw-string" d="M252 16v40"/>' +
        '<path class="pw-gear" fill-rule="evenodd" d="' + gearPath(252, 88, 32, 24, 9, 9) + '"/>' +
        // półka z puszkami i słoikiem śrubek
        '<path class="pw-bracket" d="M34 202v18l14-18M266 202v18l-14-18"/>' +
        '<rect class="pw-shelf" x="14" y="194" width="272" height="10" rx="4"/>' +
        '<rect class="pw-can pw-can--blue" x="30" y="154" width="42" height="40" rx="5"/><ellipse class="pw-lid" cx="51" cy="155" rx="21" ry="5"/>' +
        '<rect class="pw-label" x="30" y="168" width="42" height="12"/>' +
        '<rect class="pw-can pw-can--pink" x="80" y="164" width="34" height="30" rx="5"/><ellipse class="pw-lid" cx="97" cy="165" rx="17" ry="4.5"/>' +
        '<path class="pw-drip" d="M86 165v9a2.5 2.5 0 0 0 5 0v-9z"/>' +
        '<rect class="pw-can pw-can--yellow" x="124" y="150" width="46" height="44" rx="5"/><ellipse class="pw-lid" cx="147" cy="151" rx="23" ry="5.5"/>' +
        '<path class="pw-wood" d="M152 151l14-38 5 2-12 37z"/><path class="pw-bristle" d="M163 112l8-22 9 4-10 21z"/>' +
        '<rect class="pw-jar" x="190" y="162" width="36" height="32" rx="7"/><rect class="pw-jar-lid" x="188" y="156" width="40" height="8" rx="3"/>' +
        '<path class="pw-screw" d="M198 176l6 6M210 172l5 7M216 184l6-4M200 186l7-2"/>' +
        '<circle class="pw-can pw-can--mint" cx="252" cy="180" r="14"/><circle class="pw-tape" cx="252" cy="180" r="5"/>' +
        '<path class="pw-tape-end" d="M262 190l14 4v-6z"/>' +
        '</svg>';

    // Na szerokim ekranie po bokach tablicy: para zębatek (lewa) i piła z miarką (prawa)
    var SIDE_L_SVG =
        '<svg viewBox="0 0 160 220"' + NS + '>' +
        '<g class="pw-spin"><path class="pw-gear pw-gear--big" fill-rule="evenodd" d="' + gearPath(70, 80, 56, 44, 12, 14) + '"/></g>' +
        '<g class="pw-spin pw-spin--rev"><path class="pw-gear pw-gear--small" fill-rule="evenodd" d="' + gearPath(116, 160, 36, 27, 8, 9) + '"/></g>' +
        '</svg>';

    var SIDE_R_SVG =
        '<svg viewBox="0 0 160 260"' + NS + '>' +
        '<circle class="pw-peg" cx="60" cy="14" r="5"/>' +
        '<path class="pw-saw-blade" d="M48 64h26v150l-26 20z"/>' +
        '<path class="pw-saw-teeth" d="M48 76l-6 6 6 6-6 6 6 6-6 6 6 6-6 6 6 6-6 6 6 6-6 6 6 6-6 6 6 6-6 6 6 6-6 6 6 6-6 6 6 6-6 6 6 6"/>' +
        '<path class="pw-grip" d="M42 20h44a8 8 0 0 1 8 8v30a8 8 0 0 1-8 8H42a8 8 0 0 1-8-8V28a8 8 0 0 1 8-8zM50 32v20h28V32z" fill-rule="evenodd"/>' +
        '<rect class="pw-ruler" x="110" y="30" width="22" height="200" rx="3"/>' +
        '<path class="pw-ruler-marks" d="M110 46h8M110 62h12M110 78h8M110 94h12M110 110h8M110 126h12M110 142h8M110 158h12M110 174h8M110 190h12M110 206h8"/>' +
        '</svg>';

    // Ikony kafelków zasad (24×24, kolory w CSS)
    var RULE_ICON = {
        care: '<path class="ri-fill" d="M12 20s-7.5-4.6-9.2-9.4A4.9 4.9 0 0 1 12 7.1a4.9 4.9 0 0 1 9.2 3.5C19.5 15.4 12 20 12 20z"/>',
        night: '<path class="ri-fill" d="M15.5 3.5a8.5 8.5 0 1 0 5 15.4A7 7 0 0 1 15.5 3.5z"/><circle class="ri-dot" cx="18.5" cy="6" r="1.2"/>',
        hospital: '<path class="ri-fill" d="M9.5 3.5h5v6h6v5h-6v6h-5v-6h-6v-5h6z"/>',
        eggs: '<path class="ri-fill" d="M12 2.8c3.8 0 6.6 6 6.6 10.2a6.6 6.6 0 0 1-13.2 0C5.4 8.8 8.2 2.8 12 2.8z"/><circle class="ri-dot" cx="10" cy="11" r="1.3"/><circle class="ri-dot" cx="14" cy="15" r="1.1"/>',
        stars: '<path class="ri-fill" d="M12 2.8l2.8 5.8 6.3.9-4.6 4.4 1.1 6.3L12 17.2l-5.6 3 1.1-6.3-4.6-4.4 6.3-.9z"/>',
        farewell: '<path class="ri-flame" d="M12 2.5c2.4 2.9 3.6 4.8 3.6 6.5a3.6 3.6 0 0 1-7.2 0c0-1.7 1.2-3.6 3.6-6.5z"/><rect class="ri-fill" x="8.4" y="13" width="7.2" height="8.5" rx="1.5"/>'
    };

    function create(ctx, host) {
        var u = ctx.u;
        var el = u.el;
        var saving = false;
        var petsSig = null;
        var rulesSig = null;
        var notifyLoaded = false;

        var stage = el('div', 'pets-stage pets-workshop__stage');
        var sideL = el('div', 'pets-workshop__side pets-workshop__side--l');
        sideL.setAttribute('aria-hidden', 'true');
        sideL.innerHTML = SIDE_L_SVG;
        var sideR = el('div', 'pets-workshop__side pets-workshop__side--r');
        sideR.setAttribute('aria-hidden', 'true');
        sideR.innerHTML = SIDE_R_SVG;
        var scroll = el('div', 'pets-scroll pets-workshop__scroll');
        var wrap = el('div', 'pets-workshop');
        var table = el('div', 'pets-workshop__table');
        wrap.appendChild(table);
        scroll.appendChild(wrap);
        stage.appendChild(sideL);
        stage.appendChild(sideR);
        stage.appendChild(scroll);
        host.appendChild(stage);

        function tool(kind, title) {
            var box = el('section', 'pets-tool pets-tool--' + kind);
            var head = el('div', 'pets-tool__head');
            var art = el('span', 'pets-tool__art');
            art.innerHTML = ART[kind];
            var h = el('h2', 'pets-tool__title', title);
            h.id = 'petsTool-' + kind;
            box.setAttribute('aria-labelledby', h.id);
            head.appendChild(art);
            head.appendChild(h);
            box.appendChild(head);
            table.appendChild(box);
            return box;
        }

        function switchRow(id, label, hint) {
            var row = el('div', 'pets-setting');
            var text = el('div', 'pets-setting__text');
            var lab = el('label', 'pets-setting__label', label);
            lab.htmlFor = id;
            text.appendChild(lab);
            if (hint) text.appendChild(el('p', 'pets-setting__hint', hint));
            var sw = el('label', 'pets-switch');
            var input = el('input', 'pets-switch__input');
            input.type = 'checkbox';
            input.id = id;
            input.setAttribute('role', 'switch');
            var slider = el('span', 'pets-switch__slider');
            slider.setAttribute('aria-hidden', 'true');
            sw.appendChild(input);
            sw.appendChild(slider);
            row.appendChild(text);
            row.appendChild(sw);
            return { row: row, input: input };
        }

        // --- ramka: towarzysz ----------------------------------------------------------------

        var frame = tool('frame', 'Towarzysz');
        frame.appendChild(el('p', 'pets-tool__lead', 'Pupil, który chodzi z Tobą po stronach panelu klienta.'));
        var pick = el('div', 'pets-setting pets-setting--select');
        var pickText = el('div', 'pets-setting__text');
        var pickLabel = el('label', 'pets-setting__label', 'Kto Ci towarzyszy');
        pickLabel.htmlFor = 'petsCompanionSelect';
        pickText.appendChild(pickLabel);
        var select = el('select', 'pets-select');
        select.id = 'petsCompanionSelect';
        pick.appendChild(pickText);
        pick.appendChild(select);
        var show = switchRow('petsCompanionToggle', 'Pokazuj towarzysza na stronach', null);
        var jokes = switchRow('petsJokesToggle', 'Żarty pupila', 'Pupil czasem lubi coś wywinąć. Wyłącz, jeśli wolisz spokój.');
        var empty = el('p', 'pets-tool__empty', 'Towarzysza wybierzesz, gdy w domku zamieszka pierwszy pupil.');
        frame.appendChild(pick);
        frame.appendChild(show.row);
        frame.appendChild(jokes.row);
        frame.appendChild(empty);

        // --- dzwonek: powiadomienia ------------------------------------------------------------

        var bell = tool('bell', 'Powiadomienia');
        // Twardy łącznik w „e-mail” — etykieta nie łamie się w pół słowa
        var notify = switchRow('petsNotifyToggle', 'Powiadomienia o pupilach (push i e\u2011mail)',
            'Damy znać, gdy pupil będzie głodny albo chory, gdy wyzdrowieje w szpitalu, gdy jajko będzie gotowe do wyklucia i gdy czeka nowe.');
        bell.appendChild(notify.row);

        // Narzędzia na kołkach i półka z puszkami — w rzędzie kart, obok nich (ozdoba)
        var rack = el('div', 'pets-workshop__rack');
        rack.setAttribute('aria-hidden', 'true');
        rack.innerHTML = RACK_SVG;
        table.appendChild(rack);

        // --- książeczka: zasady (kafelki z ikonami) ---------------------------------------------

        var book = tool('book', 'Zasady gry');
        var rules = el('ul', 'pets-tool__rules');
        book.appendChild(rules);

        function renderRules(state) {
            var cfg = state.config || {};
            var night = state.night || {};
            var sig = JSON.stringify([cfg, night.start, night.end]);
            if (sig === rulesSig) return;
            rulesSig = sig;
            var f = Number(cfg.night_factor);
            var slower = f === 0 ? 'potrzeby nie rosną' : (f > 0 && f < 1 ? 'potrzeby rosną ' + Math.round(1 / f) + '× wolniej' : 'potrzeby rosną wolniej');
            var nightText = night.start != null && night.start !== night.end
                ? 'Noc trwa od ' + night.start + ':00 do ' + night.end + ':00 — pupile śpią, a ich ' + slower + '. Obudzony pupil traci trochę radości i czystości.'
                : 'Pupile zasypiają w nocy, a ich potrzeby rosną wtedy wolniej.';
            var hours = parseInt(cfg.hospital_hours, 10);
            var items = [
                ['care', 'Opieka', 'Karm, baw się i myj pupila. Jedna wizyta dziennie wystarczy, żeby był zdrowy, dwie–trzy — żeby był szczęśliwy.'],
                ['night', 'Noc', nightText],
                ['hospital', 'Szpital', 'Zaniedbany pupil choruje. W domku zdrowieje powoli, gdy wszystkie potrzeby są powyżej 50%; w szpitalu wraca do zdrowia' +
                    (hours > 0 ? ' w najwyżej ' + hours + ' h' : '') + ', a jego potrzeby nie rosną. Wyleczonego odbierz szybko — czekając, tęskni i smutnieje.'],
                ['eggs', 'Jajka', 'Co miesiąc czeka nowe jajko. Ogrzewaj je przy każdej wizycie — ciepło przyspiesza wyklucie' +
                    (cfg.boost_factor ? ' ×' + cfg.boost_factor : '') + (cfg.boost_hours ? ' na ' + cfg.boost_hours + ' h' : '') + '.'],
                ['stars', 'Gwiazdki', 'Jeśli z jajka wykluje się gatunek, który już masz, Twój pupil dostaje gwiazdkę (najwyżej 5).'],
                ['farewell', 'Pożegnania', 'Pupil zaniedbany przez kilka dni może odejść do gwiazd. Wtedy czeka na Ciebie jajko ratunkowe, a w ogrodzie wspomnień zapalisz mu światełko.']
            ];
            rules.innerHTML = '';
            items.forEach(function (it) {
                var li = el('li', 'pets-tool__rule pets-tool__rule--' + it[0]);
                var icon = el('span', 'pets-tool__rule-icon');
                icon.innerHTML = '<svg viewBox="0 0 24 24"' + NS + '>' + RULE_ICON[it[0]] + '</svg>';
                var body = el('div', 'pets-tool__rule-body');
                body.appendChild(el('strong', 'pets-tool__rule-title', it[1]));
                body.appendChild(el('p', 'pets-tool__rule-text', it[2]));
                li.appendChild(icon);
                li.appendChild(body);
                rules.appendChild(li);
            });
        }

        // --- logika (jak w etapie 4–6) --------------------------------------------------------

        function renderCompanion(state) {
            if (saving) return;
            var pets = (state.pets || []).filter(function (p) { return !p.hospital; });
            var companion = state.companion || { enabled: true, pet_id: null, auto: true, jokes: true };
            var has = pets.length > 0;
            pick.hidden = !has;
            show.row.hidden = !has;
            jokes.row.hidden = !has;
            empty.hidden = has;
            var sig = pets.map(function (p) { return p.id + ':' + p.name; }).join('|');
            if (sig !== petsSig) {
                petsSig = sig;
                select.innerHTML = '';
                var auto = el('option', null, 'Automatycznie — ten, kto najbardziej potrzebuje opieki');
                auto.value = 'auto';
                select.appendChild(auto);
                pets.forEach(function (p) {
                    var opt = el('option', null, (p.name || u.speciesName(p.species)) + ' (' + u.speciesName(p.species) + ')');
                    opt.value = String(p.id);
                    select.appendChild(opt);
                });
            }
            var chosen = companion.auto || companion.pet_id == null ? 'auto' : String(companion.pet_id);
            select.value = select.querySelector('option[value="' + chosen + '"]') ? chosen : 'auto';
            show.input.checked = !!companion.enabled;
            jokes.input.checked = companion.jokes !== false;
            select.disabled = false;
            show.input.disabled = false;
            jokes.input.disabled = false;
        }

        function saveCompanion() {
            var value = select.value;
            var body = { pet_id: value === 'auto' ? null : parseInt(value, 10), enabled: !!show.input.checked, jokes: !!jokes.input.checked };   // boolean, nie string
            saving = true;
            select.disabled = true;
            show.input.disabled = true;
            jokes.input.disabled = true;
            ctx.send('/towarzysz', body).then(function () {
                u.toast('Zapisano ustawienia towarzysza.', 'success');
            }, function () { /* toast/odświeżenie już były */ }).then(function () {
                saving = false;
                if (ctx.state()) renderCompanion(ctx.state());
            });
        }

        function csrfToken() {
            var meta = document.querySelector('meta[name="csrf-token"]');
            return meta ? meta.getAttribute('content') : '';
        }

        function fail(error, message, status) {
            return { error: error, message: message || GENERIC_ERROR, status: status || 0 };
        }

        function prefsRequest(init) {
            return fetch(PREFS_URL, init).then(function (r) {
                if (r.redirected) throw fail('session_expired', 'Sesja wygasła — zaloguj się ponownie.', r.status);
                var type = r.headers.get('Content-Type') || '';
                if (!r.ok || type.indexOf('application/json') === -1) throw fail('bad_response', GENERIC_ERROR, r.status);
                return r.json();
            }, function () {
                throw fail('network', 'Brak połączenia — spróbuj za chwilę.', 0);
            });
        }

        function loadNotify() {
            notifyLoaded = true;
            var input = notify.input;
            input.disabled = true;   // do wczytania stanu z serwera — inaczej „włączone" kłamałoby przy błędzie
            prefsRequest({ credentials: 'same-origin', headers: { 'Accept': 'application/json' } }).then(function (prefs) {
                if (prefs && 'pet_updates' in prefs) input.checked = !!prefs.pet_updates;
                input.disabled = false;
                notify.row.classList.remove('is-unavailable');
            }, function () {
                notifyLoaded = false;    // spróbujemy przy następnym wejściu do warsztatu
                notify.row.classList.add('is-unavailable');
            });
        }

        function saveNotify() {
            var input = notify.input;
            var on = input.checked;
            input.disabled = true;
            prefsRequest({
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Accept': 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                body: JSON.stringify({ pet_updates: on })
            }).then(function (data) {
                if (!data || !data.success) throw fail('bad_response', GENERIC_ERROR, 0);
                u.toast(on ? 'Powiadomienia o pupilach włączone.' : 'Powiadomienia o pupilach wyłączone.', 'success');
            }).catch(function (err) {
                input.checked = !on;
                u.toast(err && err.error === 'session_expired' ? err.message : 'Nie udało się zapisać ustawienia powiadomień.', 'error');
            }).then(function () { input.disabled = false; });
        }

        select.addEventListener('change', saveCompanion);
        show.input.addEventListener('change', saveCompanion);
        jokes.input.addEventListener('change', saveCompanion);
        notify.input.addEventListener('change', saveNotify);

        return {
            enter: function () {
                if (!notifyLoaded) loadNotify();
            },
            leave: function () {},
            render: function (state) {
                renderCompanion(state);
                renderRules(state);
            }
        };
    }

    W.scenes.warsztat = {
        title: 'Warsztat',
        create: create
    };
})();
