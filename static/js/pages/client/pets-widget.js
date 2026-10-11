/**
 * Widget pupila na dashboardzie klienta (spec §4.3, plan etapu 5 — Task 3).
 *
 * Szkielet SSR: templates/client/pets/_widget.html — #petsWidget[data-state][data-api][data-user-id]
 * [data-home-url] z pustym .pets-widget__body; treść rysuje ten plik.
 *
 * Wymaga (kolejność w dashboard.html): species.js, pet-rig.js, haptics.js, pets-core.js
 * (include towarzysza w base_client), pet-card.js, potem ten plik.
 *
 * Treść — pierwsza pasująca gałąź:
 *   1. żywy pupil (most_in_need_pet_id) → mini-karta PetCard: szybkie akcje, nastrój, „Obudź", pat pat;
 *   2. brak żywych, jajko gotowe        → jajko + „Wykluj w domku";
 *   3. jajko w inkubacji                 → jajko z postępem, „Wykluje się za ~N h" (+ „ogrzane ×2");
 *   4. jajko do odebrania                → zachęta („Odbierz swoje pierwsze jajko" dla startowego);
 *   5. nic z powyższego                  → „Następne jajko: za N dni".
 *
 * Podział pracy z PetCard (kontrakt etapu 4): karta sama ekstrapoluje paski co 1 s, zbiera
 * klepnięcia w paczki (debounce 2 s, max 50) z wibracją i woła onAction(pet, 'pat', n) — widget
 * tylko wysyła żądanie, wpina odpowiedź w PetsState i obsługuje błędy. Gdy karta nie ma własnych
 * przycisków akcji, widget dokłada swoje (ta sama ścieżka onAction).
 *
 * Bezpieczeństwo: imiona i komunikaty wyłącznie przez textContent; showToast wstawia HTML,
 * więc komunikat z serwera (zawiera imię pupila) jest escapowany przed przekazaniem.
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
    var nestUrl = homeUrl + '#petsNest';

    var REFRESH_MS = 5 * 60 * 1000;
    var EGG_TICK_MS = 30 * 1000;
    var STICKY_MS = 60 * 1000;          // tyle po interakcji karta trzyma tego samego pupila
    var BOOST_FACTOR = 2;               // spec §2.2: ogrzanie = tempo ×2 (nadpisywane z state.config.boost_factor)
    var GENERIC_ERROR = 'Coś poszło nie tak, spróbuj za chwilę';
    var OWN_MESSAGE_ERRORS = { session_expired: 1, network: 1, rate_limited: 1 };

    var MOOD_TEXT = {
        szczesliwy: 'Szczęśliwy', glodny: 'Głodny', znudzony: 'Znudzony', brudny: 'Brudny',
        smutny: 'Smutny', chory: 'Chory', krytyczny: 'W stanie krytycznym'
    };
    var ACTION_TEXT = { feed: 'Nakarm', play: 'Pobaw się', wash: 'Umyj', wake: 'Obudź' };
    var CLAIM_TEXT = {
        monthly: 'Comiesięczne jajko już na Ciebie czeka.',
        granted: 'Masz jajko w prezencie — czeka w gniazdku.'
    };

    // aria-live na całym body ogłaszałby co sekundę ekstrapolowane paski karty — czytnik
    // dostaje tylko krótkie komunikaty o zmianie treści widgetu (osobny, niewidoczny region).
    body.removeAttribute('aria-live');
    var live = el('p', 'pets-widget__sr');
    live.setAttribute('aria-live', 'polite');
    root.appendChild(live);

    var view = { key: null, kind: null, petId: null, card: null, egg: null, refs: null };
    var rendered = null;            // ostatnio narysowany stan
    var receivedAt = Date.now();    // kiedy przyszedł `rendered` (zegar przeglądarki)
    var lastInteraction = 0;
    var lastRefresh = Date.now();
    var refreshing = null;
    var seq = 0;
    var appliedSeq = 0;
    var eggTimer = 0;
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

    function escapeForToast(text) {
        return String(text).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function toast(message, type) {
        if (typeof window.showToast === 'function') window.showToast(escapeForToast(message), type || 'info');
    }

    /** Czas „ścienny" z API (naiwny, czas polski) → ms; obie strony porównań parsujemy tak samo. */
    function parseLocal(iso) {
        if (!iso) return NaN;
        var m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(iso);
        if (!m) return NaN;
        return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0)).getTime();
    }

    function daysWord(n) {
        return n === 1 ? 'dzień' : 'dni';
    }

    function cardCtx(state) {
        var night = state.night && state.night.start !== state.night.end ? state.night : null;
        return { now: state.now, night: night };
    }

    function announce(text) {
        live.textContent = '';
        if (text) setTimeout(function () { live.textContent = text; }, 50);
    }

    // ------------------------------------------------------------------------------------
    // Wybór gałęzi
    // ------------------------------------------------------------------------------------

    function findPet(state, id) {
        var pets = state.pets || [];
        for (var i = 0; i < pets.length; i++) if (pets[i].id === id) return pets[i];
        return null;
    }

    function pickPet(state) {
        var pets = state.pets || [];
        if (!pets.length) return null;
        // Po kliknięciu nie przeskakujemy na innego pupila w połowie opieki (nakarmiony A
        // przestaje być „najbardziej potrzebujący", ale użytkownik właśnie się nim zajmuje).
        if (view.kind === 'pet' && Date.now() - lastInteraction < STICKY_MS) {
            var same = findPet(state, view.petId);
            if (same) return same;
        }
        return findPet(state, state.most_in_need_pet_id) || pets[0];
    }

    function pickView(state) {
        var pet = pickPet(state);
        if (pet) return { kind: 'pet', key: 'pet:' + pet.id, pet: pet };
        var eggs = state.eggs || [];
        var ready = null, best = null;
        for (var i = 0; i < eggs.length; i++) {
            if (eggs[i].ready) { ready = ready || eggs[i]; continue; }
            if (!best || eggs[i].progress_pct > best.progress_pct) best = eggs[i];
        }
        if (ready) return { kind: 'egg-ready', key: 'egg-ready', egg: ready, more: eggs.length - 1 };
        if (best) return { kind: 'egg', key: 'egg', egg: best, more: eggs.length - 1 };
        var avail = state.eggs_available || [];
        if (avail.length) {
            // Startowe pierwsze (zachęta), potem ratunkowe (ma imię pupila), potem reszta wg kolejności z API
            var bySource = {};
            for (var j = 0; j < avail.length; j++) bySource[avail[j].source] = bySource[avail[j].source] || avail[j];
            var claim = bySource.start || bySource.rescue || avail[0];
            return { kind: 'claim', key: 'claim:' + claim.source, claim: claim, count: avail.length };
        }
        return { kind: 'next', key: 'next' };
    }

    // ------------------------------------------------------------------------------------
    // Rysowanie
    // ------------------------------------------------------------------------------------

    function clearView() {
        if (view.card) view.card.destroy();
        if (view.egg) view.egg.destroy();
        clearInterval(eggTimer);
        eggTimer = 0;
        view = { key: null, kind: null, petId: null, card: null, egg: null, refs: null };
        body.innerHTML = '';
        root.classList.remove('pets-widget--attention');
    }

    function tile(modifier) {
        var box = el('div', 'pets-widget__tile pets-widget__tile--' + modifier);
        var scene = el('div', 'pets-widget__scene');
        var content = el('div', 'pets-widget__content');
        box.appendChild(scene);
        box.appendChild(content);
        body.appendChild(box);
        return { box: box, scene: scene, content: content };
    }

    function cta(text, href) {
        var a = el('a', 'pets-widget__cta', text);
        a.href = href;
        return a;
    }

    // --- gałąź 1: pupil -----------------------------------------------------------------

    function cardHasActions(card) {
        return !!(card && card.el && card.el.querySelector('[data-action], [data-card-action]'));
    }

    function cardHasMood(card) {
        return !!(card && card.el && card.el.querySelector('.pet-card__mood'));
    }

    function renderPet(v, state) {
        var pet = v.pet;
        var ctx = cardCtx(state);
        if (view.key === v.key) {
            if (view.card) view.card.update(pet, ctx);
            else if (view.refs && view.refs.rig) view.refs.rig.update({ species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: pet.asleep });
            syncFallback(pet);
            return;
        }
        clearView();
        view.key = v.key;
        view.kind = 'pet';
        view.petId = pet.id;
        view.refs = {};
        var wrap = el('div', 'pets-widget__pet');
        body.appendChild(wrap);
        if (window.PetCard && typeof window.PetCard.render === 'function') {
            view.card = window.PetCard.render(wrap, pet, {
                mini: true, species: window.PetSpecies || {}, onAction: onCardAction,
                now: ctx.now, night: ctx.night
            });
        } else {
            // Bez karty (nie powinno się zdarzyć) — rig + imię + przyciski widgetu
            var t = el('div', 'pets-widget__tile pets-widget__tile--pet');
            var scene = el('div', 'pets-widget__scene');
            var content = el('div', 'pets-widget__content');
            t.appendChild(scene);
            t.appendChild(content);
            wrap.appendChild(t);
            view.refs.name = el('p', 'pets-widget__title');
            content.appendChild(view.refs.name);
            view.refs.content = content;
            if (window.PetRig) {
                view.refs.rig = window.PetRig.mount(scene, {
                    species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood,
                    asleep: pet.asleep, size: 'mini', idle: true
                });
            }
        }
        view.refs.wrap = wrap;
        buildFallback(pet);
    }

    /** Nastrój słownie i przyciski — tylko tego, czego karta sama nie narysowała. */
    function buildFallback(pet) {
        var refs = view.refs;
        var host = refs.content || refs.wrap;
        if (!cardHasMood(view.card)) {
            refs.mood = el('p', 'pets-widget__mood');
            host.appendChild(refs.mood);
        }
        if (!cardHasActions(view.card)) {
            refs.actions = el('div', 'pets-widget__actions');
            refs.actions.addEventListener('click', function (e) {
                var btn = e.target.closest('[data-widget-action]');
                if (!btn || btn.disabled || !refs.actions.contains(btn)) return;
                var current = rendered && findPet(rendered, view.petId);
                if (current) runFallbackAction(current, btn.getAttribute('data-widget-action'));
            });
            host.appendChild(refs.actions);
        }
        syncFallback(pet);
    }

    function syncFallback(pet) {
        var refs = view.refs || {};
        if (refs.name) refs.name.textContent = pet.name || '';
        if (refs.mood) refs.mood.textContent = (MOOD_TEXT[pet.mood] || '') + (pet.asleep ? ' · śpi' : '');
        if (!refs.actions || refs.busy) return;
        var list = pet.asleep ? ['wake'] : ['feed', 'play', 'wash'];
        refs.actions.innerHTML = '';
        list.forEach(function (action) {
            var btn = el('button', 'pets-widget__action' + (action === 'wake' ? ' pets-widget__action--primary' : ''), ACTION_TEXT[action]);
            btn.type = 'button';
            btn.setAttribute('data-widget-action', action);
            btn.disabled = !(pet.can && pet.can[action]);
            if (btn.disabled && pet.reasons && pet.reasons[action]) btn.setAttribute('aria-description', pet.reasons[action]);
            refs.actions.appendChild(btn);
        });
    }

    function runFallbackAction(pet, action) {
        var refs = view.refs;
        refs.busy = true;
        Array.prototype.forEach.call(refs.actions.querySelectorAll('button'), function (b) { b.disabled = true; });
        Promise.resolve(onCardAction(pet, action, 1)).then(function (resp) {
            if (resp && resp.ok && refs.rig) refs.rig.playAction(action);
        }, function () { /* obsłużone w onCardAction */ }).then(function () {
            refs.busy = false;
            var current = rendered && findPet(rendered, view.petId);
            if (current && view.refs === refs) syncFallback(current);
        });
    }

    // --- gałęzie 2–3: jajko ---------------------------------------------------------------

    /** Postęp i czas do wyklucia w chwili `elapsedSec` od odebrania stanu (spec §2.2, ogrzanie ×2). */
    function eggForecast(egg, state, elapsedSec) {
        if (state && state.config && state.config.boost_factor > 0) BOOST_FACTOR = Number(state.config.boost_factor);
        var total = Math.max(1, (Number(egg.egg_hours) || 0) * 3600);
        var remaining = total * (1 - Math.min(100, Math.max(0, Number(egg.progress_pct) || 0)) / 100);
        var boostLeft = 0;
        if (egg.boost_until) {
            var b = (parseLocal(egg.boost_until) - parseLocal(state.now)) / 1000;
            if (b > 0) boostLeft = b;
        }
        // Czas ścienny do wyklucia od chwili odebrania stanu
        var wall = remaining <= BOOST_FACTOR * boostLeft
            ? remaining / BOOST_FACTOR
            : boostLeft + (remaining - BOOST_FACTOR * boostLeft);
        var e = Math.max(0, elapsedSec);
        var gained = e <= boostLeft ? e * BOOST_FACTOR : boostLeft * BOOST_FACTOR + (e - boostLeft);
        return {
            pct: Math.min(100, (total - remaining + gained) / total * 100),
            leftSec: Math.max(0, wall - e),
            boosted: boostLeft - e > 0
        };
    }

    function hatchText(leftSec) {
        var h = leftSec / 3600;
        if (h < 1) return 'Wykluje się za mniej niż godzinę';
        if (h < 48) return 'Wykluje się za ~' + Math.ceil(h) + ' h';
        var d = Math.round(h / 24);
        return 'Wykluje się za ~' + d + ' ' + daysWord(d);
    }

    function moreEggsText(n) {
        if (n <= 0) return '';
        return 'W gniazdku ' + (n === 1 ? 'czeka jeszcze jedno jajko.' : 'czekają jeszcze ' + n + ' jajka.');
    }

    function renderEggReady(v) {
        if (view.key === v.key) return;
        clearView();
        view.key = v.key;
        view.kind = v.kind;
        var t = tile('egg');
        if (window.PetRig) view.egg = window.PetRig.mountEgg(t.scene, { pct: 100, ready: true, size: 'mini' });
        t.content.appendChild(el('p', 'pets-widget__title', 'Jajko jest gotowe!'));
        t.content.appendChild(el('p', 'pets-widget__text', 'Kliknij „Wykluj" w domku i poznaj swojego pupila.'));
        var more = moreEggsText(v.more);
        if (more) t.content.appendChild(el('p', 'pets-widget__note', more));
        t.content.appendChild(cta('Wykluj w domku', nestUrl));
        announce('Jajko jest gotowe do wyklucia.');
    }

    function renderEgg(v, state) {
        var egg = v.egg;
        if (view.key !== v.key || !view.refs || view.refs.eggId !== egg.id) {
            clearView();
            view.key = v.key;
            view.kind = v.kind;
            var t = tile('egg');
            var refs = view.refs = { eggId: egg.id };
            if (window.PetRig) view.egg = window.PetRig.mountEgg(t.scene, { pct: egg.progress_pct, boosted: false, size: 'mini' });
            refs.title = el('p', 'pets-widget__title', 'Jajko się wykluwa');
            refs.badge = el('span', 'pets-widget__badge', 'ogrzane ×' + BOOST_FACTOR);
            refs.title.appendChild(document.createTextNode(' '));
            refs.title.appendChild(refs.badge);
            refs.when = el('p', 'pets-widget__text');
            refs.track = el('div', 'pets-widget__progress');
            refs.track.setAttribute('role', 'progressbar');
            refs.track.setAttribute('aria-label', 'Postęp wykluwania');
            refs.track.setAttribute('aria-valuemin', '0');
            refs.track.setAttribute('aria-valuemax', '100');
            refs.fill = el('div', 'pets-widget__progress-fill');
            refs.track.appendChild(refs.fill);
            refs.hint = el('p', 'pets-widget__note');
            refs.more = el('p', 'pets-widget__note');
            refs.cta = cta('Ogrzej w domku', nestUrl);
            [refs.title, refs.when, refs.track, refs.hint, refs.more, refs.cta].forEach(function (n) { t.content.appendChild(n); });
            eggTimer = setInterval(tickEgg, EGG_TICK_MS);
        }
        view.refs.egg = egg;
        view.refs.state = state;
        view.refs.moreCount = v.more;
        tickEgg();
    }

    function tickEgg() {
        var refs = view.refs;
        if (!refs || !refs.egg || view.kind !== 'egg') return;
        var f = eggForecast(refs.egg, refs.state, (Date.now() - receivedAt) / 1000);
        if (f.pct >= 100) {
            // Wykluło się „na zegarze" — serwer potwierdzi gotowość
            refs.when.textContent = 'Za chwilę będzie gotowe…';
            refresh();
            return;
        }
        var pct = Math.floor(f.pct);
        refs.when.textContent = hatchText(f.leftSec);
        refs.fill.style.width = f.pct.toFixed(1) + '%';
        refs.track.setAttribute('aria-valuenow', String(pct));
        refs.track.setAttribute('aria-valuetext', pct + '%');
        refs.badge.hidden = !f.boosted;
        var canWarm = !f.boosted && refs.egg.can_warm !== false;
        refs.cta.hidden = !canWarm;
        refs.hint.textContent = f.boosted
            ? 'Ogrzane jajko wykluwa się dwa razy szybciej.'
            : 'Ogrzej je w domku, żeby przyspieszyć wyklucie.';
        var more = moreEggsText(refs.moreCount);
        refs.more.textContent = more;
        refs.more.hidden = !more;
        if (view.egg) view.egg.update({ pct: f.pct, boosted: f.boosted });
    }

    // --- gałąź 4: jajko do odebrania ------------------------------------------------------

    function claimText(claim) {
        if (claim.source === 'rescue') {
            return claim.pet_name
                ? 'Jajko ratunkowe po ' + claim.pet_name + ' już czeka w gniazdku.'
                : 'Jajko ratunkowe już czeka w gniazdku.';
        }
        return CLAIM_TEXT[claim.source] || 'Odbierz je w domku — wtedy zacznie się wykluwać.';
    }

    function renderClaim(v) {
        if (view.key === v.key && view.refs && view.refs.count === v.count) return;
        clearView();
        view.key = v.key;
        view.kind = v.kind;
        view.refs = { count: v.count };
        var start = v.claim.source === 'start';
        var t = tile('claim');
        if (window.PetRig) view.egg = window.PetRig.mountEgg(t.scene, { pct: 0, size: 'mini' });
        t.content.appendChild(el('p', 'pets-widget__title', start ? 'Odbierz swoje pierwsze jajko' : 'Czeka na Ciebie jajko'));
        t.content.appendChild(el('p', 'pets-widget__text', start
            ? 'Wykluje się z niego pupil, którym zaopiekujesz się na dashboardzie i w domku.'
            : claimText(v.claim)));
        if (v.count > 1) t.content.appendChild(el('p', 'pets-widget__note', 'Jajek do odebrania: ' + v.count + '.'));
        t.content.appendChild(cta(start ? 'Odbierz jajko' : 'Odbierz w domku', nestUrl));
        if (start) waitForPopupsThenAttract();
        announce(start ? 'Możesz odebrać swoje pierwsze jajko.' : 'Czeka na Ciebie jajko do odebrania.');
    }

    // Spec §4.2: na dashboardzie zachęta do startowego jajka dopiero po popupach ogłoszeń.
    // Treść jest od razu (widget nie może być pusty), ale pulsowanie CTA rusza po popups-all-closed.
    var popupsDone = false;
    document.addEventListener('popups-all-closed', function () {
        popupsDone = true;
        if (view.key === 'claim:start') root.classList.add('pets-widget--attention');
    });
    function waitForPopupsThenAttract() {
        if (popupsDone) root.classList.add('pets-widget--attention');
        // System popupów może nie istnieć na stronie / nie odpowiedzieć — jak w onboarding-tour.js
        setTimeout(function () {
            popupsDone = true;
            // Overlay popupu jest usuwany z DOM przy zamknięciu — jego obecność = popup nadal otwarty
            if (view.key === 'claim:start' && !document.getElementById('popupAnnouncementOverlay')) {
                root.classList.add('pets-widget--attention');
            }
        }, 6000);
    }

    // --- gałąź 5: następne jajko ----------------------------------------------------------

    function renderNext(v, state) {
        var title, text;
        var next = parseLocal(state.next_monthly_at);
        var now = parseLocal(state.now);
        if (!isNaN(next) && !isNaN(now)) {
            var hours = Math.max(1, Math.ceil((next - now) / 3600000));
            var days = Math.floor(hours / 24);
            title = 'Następne jajko: za ' + (days >= 1 ? days + ' ' + daysWord(days) : '~' + hours + ' h');
            text = 'Zajrzyj wtedy do gniazdka w domku — jajko trzeba odebrać, żeby zaczęło się wykluwać.';
        } else {
            title = 'Na razie nie ma jajka do odebrania';
            text = 'Zajrzyj do domku, żeby zobaczyć album pupili.';
        }
        var key = 'next|' + title;
        if (view.key === key) return;
        clearView();
        view.key = key;
        view.kind = 'next';
        var t = tile('next');
        // Łapka jako maska CSS (paw.svg rysuje currentColor — jako <img> byłaby czarna w dark mode)
        var icon = el('span', 'pets-widget__paw');
        icon.setAttribute('aria-hidden', 'true');
        t.scene.appendChild(icon);
        t.content.appendChild(el('p', 'pets-widget__title', title));
        t.content.appendChild(el('p', 'pets-widget__text', text));
    }

    function render(state) {
        var v = pickView(state);
        if (v.kind === 'pet') renderPet(v, state);
        else if (v.kind === 'egg-ready') renderEggReady(v);
        else if (v.kind === 'egg') renderEgg(v, state);
        else if (v.kind === 'claim') renderClaim(v);
        else renderNext(v, state);
        root.setAttribute('data-view', v.kind);
    }

    // ------------------------------------------------------------------------------------
    // Stan
    // ------------------------------------------------------------------------------------

    /** Każda zmiana stanu (nasza akcja, odświeżenie, towarzysz na tej samej stronie). */
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

    function showAchievements() {
        try { sessionStorage.removeItem('achievements_last_check'); } catch (e) { /* tryb prywatny */ }
        fetch('/achievements/api/unseen', { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                try { sessionStorage.setItem('achievements_last_check', String(Date.now())); } catch (e) { /* jw. */ }
                if (data && data.success && data.achievements && data.achievements.length && window.AchievementUnlock) {
                    window.AchievementUnlock.show(data.achievements);
                }
            })
            .catch(function () { /* odznaki pokaże checker przy następnym wejściu */ });
    }

    function handleError(err) {
        var status = err && err.status;
        if (status === 409) {
            // not_available / asleep / wrong_status — nasz obraz był nieaktualny; bez toastu
            if (Store) Store.invalidate();
            refresh();
            return;
        }
        if (status === 410) {
            if (Store) Store.invalidate();
            toast((err && err.message) || GENERIC_ERROR, 'info');
            refresh();
            return;
        }
        var own = err && OWN_MESSAGE_ERRORS[err.error] && err.message;
        toast(own || GENERIC_ERROR, 'error');
    }

    /** onAction karty (i przycisków zapasowych): Promise z odpowiedzią {ok, state} albo odrzucenie. */
    function onCardAction(pet, action, count) {
        lastInteraction = Date.now();
        if (!Api) return Promise.reject({ error: 'no_api', message: GENERIC_ERROR, status: 0 });
        var payload = { action: action };
        if (action === 'pat') payload.count = Math.max(1, Math.min(50, parseInt(count, 10) || 1));
        var mySeq = ++seq;
        return Api.post('/' + pet.id + '/akcja', payload).then(function (resp) {
            lastInteraction = Date.now();
            if (mySeq >= appliedSeq && resp && resp.state) {
                appliedSeq = mySeq;
                publish(resp.state);
            }
            if (resp && resp.new_achievements && resp.new_achievements.length) showAchievements();
            return resp;
        }, function (err) {
            handleError(err);
            throw err;
        });
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

    if (Store) {
        Store.onChange(onState);
        document.addEventListener('pets:state', function (e) { onState(e && e.detail); });
    }

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
