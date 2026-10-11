/**
 * Świat pupili — scena „warsztat” (spec v3 §6.5): drewniany stół z „narzędziami”.
 *
 * - ramka ze zdjęciem = wybór towarzysza (żywi poza szpitalem + „automatycznie”) i włącznik
 *   (POST /towarzysz — jak dotąd),
 * - dzwonek = przełącznik „Powiadomienia o pupilach” (GET/POST /notifications/preferences {pet_updates}),
 * - książeczka = krótkie zasady gry (liczby z state.config / state.night, nie na sztywno).
 * Pełny ekran (spec v3.1 §3.5): deska stołu to tło całej sceny, karty w scenie właściwej (.pets-stage);
 * na niskim ekranie przewija się wnętrze deski (.pets-scroll), nie strona.
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

    function create(ctx, host) {
        var u = ctx.u;
        var el = u.el;
        var saving = false;
        var petsSig = null;
        var rulesSig = null;
        var notifyLoaded = false;

        var stage = el('div', 'pets-stage');
        var scroll = el('div', 'pets-scroll');
        var wrap = el('div', 'pets-workshop');
        var table = el('div', 'pets-workshop__table');
        wrap.appendChild(table);
        scroll.appendChild(wrap);
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
        var empty = el('p', 'pets-tool__empty', 'Towarzysza wybierzesz, gdy w domku zamieszka pierwszy pupil.');
        frame.appendChild(pick);
        frame.appendChild(show.row);
        frame.appendChild(empty);

        // --- dzwonek: powiadomienia ------------------------------------------------------------

        var bell = tool('bell', 'Powiadomienia');
        var notify = switchRow('petsNotifyToggle', 'Powiadomienia o pupilach (push i e-mail)',
            'Damy znać, gdy pupil będzie głodny albo chory, gdy wyzdrowieje w szpitalu, gdy jajko będzie gotowe do wyklucia i gdy czeka nowe.');
        bell.appendChild(notify.row);

        // --- książeczka: zasady ----------------------------------------------------------------

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
                ['Opieka', 'Karm, baw się i myj pupila. Jedna wizyta dziennie wystarczy, żeby był zdrowy, dwie–trzy — żeby był szczęśliwy.'],
                ['Noc', nightText],
                ['Szpital', 'Zaniedbany pupil choruje. W szpitalu wraca do zdrowia' + (hours > 0 ? ' w najwyżej ' + hours + ' h' : '') +
                    ', a jego potrzeby nie rosną. Wyleczonego odbierz szybko — czekając, tęskni i smutnieje.'],
                ['Jajka', 'Co miesiąc czeka nowe jajko. Ogrzewaj je przy każdej wizycie — ciepło przyspiesza wyklucie' +
                    (cfg.boost_factor ? ' ×' + cfg.boost_factor : '') + (cfg.boost_hours ? ' na ' + cfg.boost_hours + ' h' : '') + '.'],
                ['Gwiazdki', 'Jeśli z jajka wykluje się gatunek, który już masz, Twój pupil dostaje gwiazdkę (najwyżej 5).'],
                ['Pożegnania', 'Pupil zaniedbany przez kilka dni może odejść do gwiazd. Wtedy czeka na Ciebie jajko ratunkowe, a w ogrodzie wspomnień zapalisz mu światełko.']
            ];
            rules.innerHTML = '';
            items.forEach(function (it) {
                var li = el('li', 'pets-tool__rule');
                li.appendChild(el('strong', null, it[0] + ': '));
                li.appendChild(document.createTextNode(it[1]));
                rules.appendChild(li);
            });
        }

        // --- logika (jak w etapie 4–6) --------------------------------------------------------

        function renderCompanion(state) {
            if (saving) return;
            var pets = (state.pets || []).filter(function (p) { return !p.hospital; });
            var companion = state.companion || { enabled: true, pet_id: null, auto: true };
            var has = pets.length > 0;
            pick.hidden = !has;
            show.row.hidden = !has;
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
            select.disabled = false;
            show.input.disabled = false;
        }

        function saveCompanion() {
            var value = select.value;
            var body = { pet_id: value === 'auto' ? null : parseInt(value, 10), enabled: !!show.input.checked };   // boolean, nie string
            saving = true;
            select.disabled = true;
            show.input.disabled = true;
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
