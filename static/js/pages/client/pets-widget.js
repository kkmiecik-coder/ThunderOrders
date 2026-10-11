/**
 * Widget pupili na dashboardzie klienta (spec v3 §7, plan „Świat” — Task 8).
 *
 * Szkielet SSR: templates/client/pets/_widget.html — #petsWidget[data-state][data-api][data-user-id]
 * [data-home-url][data-house-url][data-hospital-url] z pustym .pets-widget__body; treść rysuje ten plik.
 *
 * Wymaga (kolejność w dashboard.html): species.js, pet-rig.js, haptics.js, pets-core.js (include towarzysza
 * w base_client), js/pet/world/room.js (window.PetRoom), potem ten plik.
 *
 * Treść — pierwsza pasująca gałąź:
 *   1. żywi pupile poza szpitalem → mini-pokój PetRoom (compact, bez interakcji): towarzysz duży na środku
 *      z dymkiem potrzeby, do 4 pozostałych w tle + „+N”; klik w pupila → domek z otwartym panelem;
 *   2. ktoś w szpitalu            → łóżko (PetRig pose 'bed') + „Wraca do zdrowia — jeszcze ~N h”
 *                                    albo „Gotowy do odbioru”; klik → szpital (?pupil=ID);
 *   3. jajka w inkubacji          → inkubator z jajkami w skórkach + „Wykluje się za ~N h” (mnożnik
 *                                    ogrzania z state.config.boost_factor); klik → szpital;
 *   4. jajko do odebrania         → jajko z kokardką + „Odbierz w szpitalu”; klik → szpital;
 *   5. nic z powyższego           → „Następne jajko: za N dni”.
 * Bez pasków, przycisków akcji i pat pat — opieka jest w świecie pupili.
 *
 * Bezpieczeństwo: imiona i teksty wyłącznie przez textContent / setAttribute; zero inline handlerów.
 */
(function () {
    'use strict';

    var root = document.getElementById('petsWidget');
    if (!root || root.getAttribute('data-widget-ready') === '1') return;
    var body = root.querySelector('.pets-widget__body');
    if (!body) return;
    root.setAttribute('data-widget-ready', '1');

    var Api = window.PetsApi;
    var Store = window.PetsState;
    var homeUrl = root.getAttribute('data-home-url') || '/client/pupile';
    var houseUrl = root.getAttribute('data-house-url') || homeUrl + '/domek';
    var hospitalUrl = root.getAttribute('data-hospital-url') || homeUrl + '/szpital';

    var REFRESH_MS = 5 * 60 * 1000;
    var TICK_MS = 30 * 1000;
    var EARLY_REFRESH_MS = 60 * 1000;   // „na zegarze” już gotowe — dopytaj serwer, ale nie częściej niż co minutę
    var MAX_BEDS = 3;
    var MAX_EGGS = 4;

    // Komunikaty o zmianie treści dla czytnika ekranu (osobny, niewidoczny region)
    var live = el('p', 'pets-widget__sr');
    live.setAttribute('aria-live', 'polite');
    root.appendChild(live);

    var view = { key: null, kind: null, room: null, rigs: [], refs: null };
    var rendered = null;            // ostatnio narysowany stan
    var receivedAt = Date.now();    // kiedy przyszedł `rendered` (zegar przeglądarki)
    var lastRefresh = Date.now();
    var refreshing = null;
    var tickTimer = 0;
    var trustNext = false;          // następny set() pochodzi z naszego żądania do serwera

    // ------------------------------------------------------------------------------------
    // Narzędzia
    // ------------------------------------------------------------------------------------

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text;
        return node;
    }

    /** Czas „ścienny” z API (naiwny, czas polski) → ms; obie strony porównań parsujemy tak samo. */
    function parseLocal(iso) {
        if (!iso) return NaN;
        var m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(iso);
        if (!m) return NaN;
        return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0)).getTime();
    }

    /** Sekundy od odebrania stanu (zegar przeglądarki). */
    function elapsedSec() {
        return Math.max(0, (Date.now() - receivedAt) / 1000);
    }

    function plural(n, one, few, many) {
        if (n === 1) return one;
        var d = n % 10, t = n % 100;
        return d >= 2 && d <= 4 && (t < 12 || t > 14) ? few : many;
    }

    function daysWord(n) {
        return n === 1 ? 'dzień' : 'dni';
    }

    /** „~N h” / „~N dni” / „niecałą godzinę” — do tekstów odliczania. */
    function durationText(sec) {
        var h = sec / 3600;
        if (h < 1) return 'niecałą godzinę';
        if (h < 48) return '~' + Math.ceil(h) + ' h';
        var d = Math.round(h / 24);
        return '~' + d + ' ' + daysWord(d);
    }

    /** Mnożnik ogrzania z config stanu (ten sam, którym liczy serwer) — pets-core.js. */
    function boostFactor(state) {
        return Store.boostFactor(state);
    }

    function announce(text) {
        live.textContent = '';
        if (text) setTimeout(function () { live.textContent = text; }, 50);
    }

    function needOf(pet) {
        return window.PetRig && typeof window.PetRig.needOf === 'function' ? window.PetRig.needOf(pet) : 'happy';
    }

    function earlyRefresh() {
        if (Date.now() - lastRefresh >= EARLY_REFRESH_MS) refresh();
    }

    // ------------------------------------------------------------------------------------
    // Wybór gałęzi
    // ------------------------------------------------------------------------------------

    function pickView(state) {
        var alive = state.pets || [];
        var home = alive.filter(function (p) { return p && !p.hospital; });
        if (home.length && window.PetRoom) return { kind: 'room', key: 'room', pets: home };

        var sick = alive.filter(function (p) { return p && p.hospital; });
        if (sick.length) {
            // Gotowi do odbioru pierwsi, potem ten, kto wyzdrowieje najwcześniej
            sick = sick.slice().sort(function (a, b) {
                if (!!a.hospital.ready !== !!b.hospital.ready) return a.hospital.ready ? -1 : 1;
                return (parseLocal(a.hospital.healed_at) || 0) - (parseLocal(b.hospital.healed_at) || 0);
            });
            return {
                kind: 'hospital',
                key: 'hospital:' + sick.slice(0, MAX_BEDS).map(function (p) { return p.id; }).join(','),
                pets: sick
            };
        }

        var eggs = state.eggs || [];
        if (eggs.length) {
            return {
                kind: 'incubator',
                key: 'incubator:' + eggs.slice(0, MAX_EGGS).map(function (e) { return e.id + '/' + (e.skin || 0); }).join(','),
                eggs: eggs
            };
        }

        var avail = state.eggs_available || [];
        if (avail.length) {
            // Startowe pierwsze (zachęta), potem ratunkowe (ma imię pupila), potem reszta wg kolejności z API
            var bySource = {};
            for (var j = 0; j < avail.length; j++) bySource[avail[j].source] = bySource[avail[j].source] || avail[j];
            var claim = bySource.start || bySource.rescue || avail[0];
            return { kind: 'claim', key: 'claim:' + claim.source + ':' + avail.length, claim: claim, count: avail.length };
        }
        return { kind: 'next', key: 'next' };
    }

    // ------------------------------------------------------------------------------------
    // Rysowanie
    // ------------------------------------------------------------------------------------

    function clearView() {
        if (view.room) view.room.destroy();
        view.rigs.forEach(function (r) { if (r && r.destroy) r.destroy(); });
        clearInterval(tickTimer);
        tickTimer = 0;
        view = { key: null, kind: null, room: null, rigs: [], refs: null };
        body.innerHTML = '';
        root.classList.remove('pets-widget--attention');
    }

    function startTick(fn) {
        clearInterval(tickTimer);
        tickTimer = setInterval(fn, TICK_MS);
    }

    /**
     * Scena stanu bez pokoju: cała jest linkiem (cel dotyku = cały kafelek) albo zwykłym blokiem.
     * Ilustracja po lewej (na telefonie nad tekstem), podpis po prawej.
     */
    function stage(modifier, href, label) {
        var box = el(href ? 'a' : 'div', 'pets-widget__stage pets-widget__stage--' + modifier);
        if (href) {
            box.href = href;
            if (label) box.setAttribute('aria-label', label);
        }
        var art = el('div', 'pets-widget__art');
        art.setAttribute('aria-hidden', 'true');
        var caption = el('div', 'pets-widget__caption');
        box.appendChild(art);
        box.appendChild(caption);
        body.appendChild(box);
        return { box: box, art: art, caption: caption };
    }

    // --- gałąź 1: mini-pokój ---------------------------------------------------------------

    function mainPetId(state) {
        var comp = state.companion || {};
        return comp.pet_id != null ? comp.pet_id : (state.most_in_need_pet_id != null ? state.most_in_need_pet_id : null);
    }

    function isNight(state) {
        return !!(state.night && state.night.is_night);
    }

    function renderRoom(v, state) {
        var opts = { night: isNight(state), mainPetId: mainPetId(state) };
        if (view.key === v.key && view.room) {
            view.room.update(v.pets, opts);
            return;
        }
        clearView();
        view.key = v.key;
        view.kind = 'room';
        var host = el('div', 'pets-widget__room');
        body.appendChild(host);
        view.room = window.PetRoom.mount(host, {
            pets: v.pets,
            night: opts.night,
            mainPetId: opts.mainPetId,
            compact: true,
            interactive: false,
            onPetClick: function (id) {
                if (id == null || isNaN(id)) return;
                location.href = houseUrl + '?pupil=' + encodeURIComponent(id);
            }
        });
    }

    // --- gałąź 2: szpital ------------------------------------------------------------------

    function hospitalLeftSec(pet, state) {
        var h = pet.hospital;
        if (h.ready) return 0;
        var healed = parseLocal(h.healed_at), now = parseLocal(state.now);
        if (isNaN(healed) || isNaN(now)) return NaN;
        return Math.max(0, (healed - now) / 1000 - elapsedSec());
    }

    function petLabel(pet) {
        return 'Pupil ' + (pet.name || '');
    }

    function renderHospital(v, state) {
        var main = v.pets[0];
        if (view.key !== v.key) {
            clearView();
            view.key = v.key;
            view.kind = 'hospital';
            var s = stage('hospital', hospitalUrl + '?pupil=' + encodeURIComponent(main.id));
            var refs = view.refs = { stage: s, beds: {} };
            var beds = el('div', 'pets-widget__beds');
            s.art.appendChild(beds);
            v.pets.slice(0, MAX_BEDS).forEach(function (pet) {
                var bed = el('span', 'pets-widget__bed');
                beds.appendChild(bed);
                if (window.PetRig) {
                    var rig = window.PetRig.mount(bed, {
                        species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: false,
                        size: 'mini', need: needOf(pet), pose: 'bed'
                    });
                    view.rigs.push(rig);
                    refs.beds[pet.id] = rig;
                }
            });
            refs.title = el('p', 'pets-widget__title');
            refs.text = el('p', 'pets-widget__text');
            refs.note = el('p', 'pets-widget__note');
            refs.pill = el('span', 'pets-widget__pill', 'Zajrzyj do szpitala');
            [refs.title, refs.text, refs.note, refs.pill].forEach(function (n) { s.caption.appendChild(n); });
            startTick(tickHospital);
            announce(main.hospital.ready ? petLabel(main) + ' jest gotowy do odbioru ze szpitala.' : petLabel(main) + ' jest w szpitalu.');
        }
        view.refs.pets = v.pets;
        view.refs.state = state;
        view.refs.stage.box.href = hospitalUrl + '?pupil=' + encodeURIComponent(main.id);
        v.pets.slice(0, MAX_BEDS).forEach(function (pet) {
            var rig = view.refs.beds[pet.id];
            if (!rig) return;
            rig.update({ species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: false });
            if (typeof rig.setNeed === 'function') rig.setNeed(needOf(pet));
        });
        tickHospital();
    }

    function tickHospital() {
        var refs = view.refs;
        if (view.kind !== 'hospital' || !refs || !refs.pets) return;
        var main = refs.pets[0];
        var left = hospitalLeftSec(main, refs.state);
        var ready = !!main.hospital.ready || left === 0;
        if (ready && !main.hospital.ready) earlyRefresh();      // wyzdrowiał „na zegarze” — serwer potwierdzi
        refs.title.textContent = petLabel(main);
        refs.text.textContent = ready
            ? 'Gotowy do odbioru'
            : 'Wraca do zdrowia — jeszcze ' + (isNaN(left) ? 'chwilę' : durationText(left));
        refs.pill.textContent = ready ? 'Odbierz w szpitalu' : 'Zajrzyj do szpitala';
        refs.stage.box.classList.toggle('is-ready', ready);
        var others = refs.pets.length - 1;
        refs.note.textContent = others > 0
            ? 'W szpitalu jest jeszcze ' + others + ' ' + plural(others, 'pupil', 'pupile', 'pupili') + '.'
            : '';
        refs.note.hidden = others <= 0;
        refs.stage.box.setAttribute('aria-label', refs.title.textContent + ': ' + refs.text.textContent + '. Przejdź do szpitala');
    }

    // --- gałąź 3: inkubator ----------------------------------------------------------------

    /** Postęp i czas do wyklucia w chwili `elapsed` od odebrania stanu — wspólna logika w pets-core.js. */
    function eggForecast(egg, state, elapsed) {
        return Store.eggForecast(egg, state, elapsed);
    }

    function renderIncubator(v, state) {
        if (view.key !== v.key) {
            clearView();
            view.key = v.key;
            view.kind = 'incubator';
            var s = stage('incubator', hospitalUrl);
            var refs = view.refs = { stage: s, eggs: {} };
            var lamp = el('span', 'pets-widget__lamp');
            var nest = el('div', 'pets-widget__nest');
            s.art.appendChild(lamp);
            s.art.appendChild(nest);
            v.eggs.slice(0, MAX_EGGS).forEach(function (egg) {
                var slot = el('span', 'pets-widget__egg');
                nest.appendChild(slot);
                if (window.PetRig) {
                    var rig = window.PetRig.mountEgg(slot, {
                        pct: egg.progress_pct, boosted: !!egg.boost_until, ready: !!egg.ready, size: 'mini', skin: egg.skin || 0
                    });
                    view.rigs.push(rig);
                    refs.eggs[egg.id] = rig;
                }
            });
            refs.title = el('p', 'pets-widget__title');
            refs.badge = el('span', 'pets-widget__badge');
            refs.text = el('p', 'pets-widget__text');
            refs.note = el('p', 'pets-widget__note');
            refs.pill = el('span', 'pets-widget__pill');
            [refs.title, refs.text, refs.note, refs.pill].forEach(function (n) { s.caption.appendChild(n); });
            startTick(tickIncubator);
            announce(v.eggs.length === 1 ? 'Jajko jest w inkubatorze.' : 'Jajka są w inkubatorze.');
        }
        view.refs.eggList = v.eggs;
        view.refs.state = state;
        tickIncubator();
    }

    function tickIncubator() {
        var refs = view.refs;
        if (view.kind !== 'incubator' || !refs || !refs.eggList) return;
        var state = refs.state;
        var e = elapsedSec();
        var soonest = null, anyReady = false, anyBoosted = false, clockReady = false;
        refs.eggList.forEach(function (egg) {
            var f = eggForecast(egg, state, e);
            var rig = refs.eggs[egg.id];
            if (rig) rig.update({ pct: f.pct, boosted: f.boosted, ready: !!egg.ready });
            if (egg.ready) { anyReady = true; return; }
            if (f.pct >= 100) clockReady = true;
            if (f.boosted) anyBoosted = true;
            if (!soonest || f.leftSec < soonest.leftSec) soonest = { egg: egg, leftSec: f.leftSec, boosted: f.boosted };
        });
        if (clockReady) earlyRefresh();       // wykluło się „na zegarze” — serwer potwierdzi gotowość
        var n = refs.eggList.length;
        var title;
        if (anyReady) title = n === 1 ? 'Jajko jest gotowe!' : 'Jajko jest gotowe do wyklucia!';
        else title = n === 1 ? 'Jajko w inkubatorze' : n + ' ' + plural(n, 'jajko', 'jajka', 'jajek') + ' w inkubatorze';
        refs.title.textContent = title;
        var factor = boostFactor(state);
        refs.badge.textContent = 'ogrzane ×' + String(factor).replace('.', ',');
        if (anyBoosted && !anyReady) {
            refs.title.appendChild(document.createTextNode(' '));
            refs.title.appendChild(refs.badge);
        }
        if (anyReady) {
            refs.text.textContent = 'Wykluj je w szpitalu i poznaj swojego pupila.';
        } else if (soonest) {
            refs.text.textContent = soonest.leftSec <= 0 ? 'Za chwilę będzie gotowe…' : 'Wykluje się za ' + durationText(soonest.leftSec);
        } else {
            refs.text.textContent = '';
        }
        var hint = '';
        if (!anyReady && soonest && !soonest.boosted && soonest.egg.can_warm !== false) hint = 'Ogrzej je w szpitalu, żeby wykluło się szybciej.';
        refs.note.textContent = hint;
        refs.note.hidden = !hint;
        refs.pill.textContent = anyReady ? 'Wykluj w szpitalu' : 'Zajrzyj do inkubatora';
        refs.stage.box.classList.toggle('is-ready', anyReady);
        refs.stage.box.setAttribute('aria-label', refs.title.textContent + '. ' + refs.text.textContent + ' Przejdź do szpitala');
    }

    // --- gałąź 4: jajko do odebrania -------------------------------------------------------

    var BOW_SVG =
        '<svg class="pets-widget__bow" viewBox="0 0 48 28" focusable="false">' +
        '<path d="M24 14 C16 2 4 2 4 10 C4 18 16 18 24 14 Z" fill="#f5576c"/>' +
        '<path d="M24 14 C32 2 44 2 44 10 C44 18 32 18 24 14 Z" fill="#f5576c"/>' +
        '<path d="M24 14 L16 27 L20 27 L24 19 L28 27 L32 27 Z" fill="#e0445a"/>' +
        '<circle cx="24" cy="14" r="4.5" fill="#ff8fa3"/></svg>';

    function claimTitle(claim) {
        if (claim.source === 'start') return 'Twoje pierwsze jajko czeka!';
        if (claim.source === 'rescue') {
            return claim.pet_name ? 'Jajko po pupilu ' + claim.pet_name + ' czeka' : 'Jajko ratunkowe czeka';
        }
        if (claim.source === 'monthly') return 'Comiesięczne jajko czeka!';
        if (claim.source === 'granted') return 'Masz jajko w prezencie!';
        return 'Czeka na Ciebie jajko';
    }

    function renderClaim(v) {
        if (view.key === v.key) return;
        clearView();
        view.key = v.key;
        view.kind = 'claim';
        var start = v.claim.source === 'start';
        var s = stage('claim', hospitalUrl);
        var slot = el('span', 'pets-widget__egg pets-widget__egg--gift');
        s.art.appendChild(slot);
        if (window.PetRig) view.rigs.push(window.PetRig.mountEgg(slot, { pct: 0, size: 'mini' }));
        slot.insertAdjacentHTML('beforeend', BOW_SVG);
        s.caption.appendChild(el('p', 'pets-widget__title', claimTitle(v.claim)));
        s.caption.appendChild(el('p', 'pets-widget__text', start
            ? 'Wykluje się z niego Twój pierwszy pupil.'
            : 'Odbierz je, a zacznie się wykluwać.'));
        if (v.count > 1) s.caption.appendChild(el('p', 'pets-widget__note', 'Jajek do odebrania: ' + v.count + '.'));
        s.caption.appendChild(el('span', 'pets-widget__pill', 'Odbierz w szpitalu'));
        s.box.setAttribute('aria-label', claimTitle(v.claim) + ' Odbierz w szpitalu');
        if (start) waitForPopupsThenAttract();
        announce(start ? 'Możesz odebrać swoje pierwsze jajko.' : 'Czeka na Ciebie jajko do odebrania.');
    }

    // Spec §4.2: na dashboardzie zachęta do startowego jajka dopiero po popupach ogłoszeń.
    // Treść jest od razu (widget nie może być pusty), ale pulsowanie rusza po popups-all-closed.
    var popupsDone = false;
    document.addEventListener('popups-all-closed', function () {
        popupsDone = true;
        if (view.kind === 'claim' && view.key.indexOf('claim:start') === 0) root.classList.add('pets-widget--attention');
    });
    function waitForPopupsThenAttract() {
        if (popupsDone) root.classList.add('pets-widget--attention');
        // System popupów może nie istnieć na stronie / nie odpowiedzieć — jak w onboarding-tour.js
        setTimeout(function () {
            popupsDone = true;
            // Overlay popupu jest usuwany z DOM przy zamknięciu — jego obecność = popup nadal otwarty
            if (view.kind === 'claim' && view.key.indexOf('claim:start') === 0 && !document.getElementById('popupAnnouncementOverlay')) {
                root.classList.add('pets-widget--attention');
            }
        }, 6000);
    }

    // --- gałąź 5: następne jajko -----------------------------------------------------------

    function renderNext(v, state) {
        var title, text;
        var next = parseLocal(state.next_monthly_at);
        var now = parseLocal(state.now);
        if (!isNaN(next) && !isNaN(now)) {
            var hours = Math.max(1, Math.ceil((next - now) / 3600000));
            var days = Math.floor(hours / 24);
            title = 'Następne jajko: za ' + (days >= 1 ? days + ' ' + daysWord(days) : '~' + hours + ' h');
            text = 'Pojawi się do odebrania w szpitalu w świecie pupili.';
        } else {
            title = 'Na razie nie ma jajka do odebrania';
            text = 'Zajrzyj do świata pupili — w ogrodzie czeka album.';
        }
        var key = 'next|' + title;
        if (view.key === key) return;
        clearView();
        view.key = key;
        view.kind = 'next';
        var s = stage('next', null);
        // Łapka jako maska CSS (paw.svg rysuje currentColor — jako <img> byłaby czarna w dark mode)
        s.art.appendChild(el('span', 'pets-widget__paw'));
        s.caption.appendChild(el('p', 'pets-widget__title', title));
        s.caption.appendChild(el('p', 'pets-widget__text', text));
    }

    function render(state) {
        var v = pickView(state);
        if (v.kind === 'room') renderRoom(v, state);
        else if (v.kind === 'hospital') renderHospital(v, state);
        else if (v.kind === 'incubator') renderIncubator(v, state);
        else if (v.kind === 'claim') renderClaim(v);
        else renderNext(v, state);
        root.setAttribute('data-view', v.kind);
    }

    // ------------------------------------------------------------------------------------
    // Stan
    // ------------------------------------------------------------------------------------

    /** Każda zmiana stanu (odświeżenie, towarzysz na tej samej stronie). */
    function onState(state) {
        if (!state || typeof state !== 'object' || state === rendered) return;
        // Starszy stan z zewnątrz (np. lite z cache towarzysza sprzed kilku minut) nie cofa
        // świeższego. Własne odpowiedzi serwera przechodzą zawsze — `now` to naiwny czas polski,
        // który przy zmianie czasu na zimowy cofa się o godzinę.
        var own = trustNext;
        trustNext = false;
        if (!own && rendered && parseLocal(state.now) < parseLocal(rendered.now)) return;
        rendered = state;
        receivedAt = Date.now();
        try {
            render(state);
        } catch (e) {
            if (window.console) console.error('pets-widget: render', e);
        }
    }

    /** Stan prosto z naszej odpowiedzi serwera → wspólny PetsState (cache, kropki, towarzysz). */
    function publish(state) {
        trustNext = true;
        if (Store) Store.set(state);
        else onState(state);
        trustNext = false;
    }

    function refresh() {
        if (refreshing || !Api) return refreshing || Promise.resolve();
        lastRefresh = Date.now();
        refreshing = Api.get('/stan').then(function (state) {
            refreshing = null;
            publish(state);
            return state;
        }, function () {
            refreshing = null;   // kolejna próba przy następnym cyklu; bez toastu w tle
        });
        return refreshing;
    }

    // ------------------------------------------------------------------------------------
    // Start
    // ------------------------------------------------------------------------------------

    var initial = null;
    try {
        initial = JSON.parse(root.getAttribute('data-state') || 'null');
    } catch (e) {
        initial = null;
    }

    if (Store) Store.onChange(onState);

    if (initial && typeof initial === 'object') {
        publish(initial);
    } else {
        refresh();
    }

    setInterval(function () {
        if (document.visibilityState === 'hidden') return;
        refresh();
    }, REFRESH_MS);

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible' && Date.now() - lastRefresh >= REFRESH_MS) refresh();
    });
})();
