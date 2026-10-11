/**
 * Moje pupile — strona /client/pupile (spec §4.2) + wspólne klocki dla etapu 5.
 *
 * Wystawia (kontrakt dla widgetu i towarzysza z etapu 5 — nazwy 1:1 z planem etapu 4):
 *   window.PetsApi   — get(path) / post(path, body[, {keepalive}]) → Promise z odpowiedzią {ok: true, …};
 *                      odrzuca obiektem {error, message, status} — także dla odpowiedzi nie-JSON
 *                      (302 na login po wygaśnięciu sesji, 500 HTML, 429 HTML, brak sieci).
 *   window.PetsState — current, set(state), onChange(cb) → funkcja odpinająca, needsCare();
 *                      po każdej zmianie: zdarzenie `pets:state` na document (detail = stan)
 *                      i kropki „pupil potrzebuje opieki" (#petsNavDot, #pwaSheetPetsDot, także
 *                      w template#pwaSheetClientMore — arkusz PWA klonuje szablon przy otwarciu).
 * Aplikacja strony startuje tylko, gdy w DOM jest #petsApp — plik można dołączyć gdzie indziej
 * dla samego API/stanu.
 *
 * Zasady: jedno źródło prawdy renderowania = JSON stanu (data-state, potem API); dane
 * użytkownika (imiona) wyłącznie przez textContent / escapeHtml; zero inline onclick —
 * delegacja zdarzeń z data-*; window.showToast wstawia HTML, więc każdy komunikat idzie
 * przez escapeHtml (komunikaty serwera zawierają imiona pupili).
 */
(function () {
    'use strict';

    var GENERIC_ERROR = 'Coś poszło nie tak, spróbuj za chwilę.';
    var REFRESH_EVERY_MS = 5 * 60 * 1000;

    // ------------------------------------------------------------------------------------
    // Drobne narzędzia
    // ------------------------------------------------------------------------------------

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function toast(message, type) {
        if (typeof window.showToast === 'function') window.showToast(escapeHtml(message || GENERIC_ERROR), type || 'info');
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text;
        return node;
    }

    function safeParse(json) {
        try { return JSON.parse(json); } catch (e) { return null; }
    }

    /** Naiwny czas lokalny z API ("2026-10-11T21:15:00") → ms. Bez strefy = czas lokalny przeglądarki. */
    function parseLocal(iso) {
        if (!iso) return NaN;
        var m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(iso);
        if (!m) return NaN;
        return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0)).getTime();
    }

    function plural(n, one, few, many) {
        var n10 = n % 10, n100 = n % 100;
        if (n === 1) return one;
        if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return few;
        return many;
    }

    /** Sekundy → „3 d 4 h", „4 h 12 min", „12 min 5 s", „40 s". */
    function formatDuration(sec) {
        sec = Math.max(0, Math.round(sec));
        var d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600);
        var m = Math.floor(sec % 3600 / 60), s = sec % 60;
        if (d > 0) return d + ' d ' + h + ' h';
        if (h > 0) return h + ' h ' + m + ' min';
        if (m > 0) return m + ' min ' + s + ' s';
        return s + ' s';
    }

    function setBusy(button, busy) {
        if (!button) return;
        button.classList.toggle('is-busy', !!busy);
        button.disabled = !!busy;
        if (busy) button.setAttribute('aria-busy', 'true');
        else button.removeAttribute('aria-busy');
    }

    var ICONS = {
        egg: '<path d="M12 3c3.6 0 6.5 6 6.5 10.2a6.5 6.5 0 0 1-13 0C5.5 9 8.4 3 12 3z"/>',
        flame: '<path d="M12 3c1.2 3 5 5.2 5 10a5 5 0 0 1-10 0c0-2.2 1-3.7 2.1-4.7 0 2 1 3.2 2.1 3.2 0-3-1.3-5 .8-8.5z"/>',
        sparkle: '<path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9z"/><path d="M19 17v4M17 19h4"/>'
    };

    function icon(name) {
        return '<svg class="pet-btn__icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" ' +
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + ICONS[name] + '</svg>';
    }

    function button(label, iconName, variant, data) {
        var b = el('button', 'pet-btn' + (variant ? ' pet-btn--' + variant : ''));
        b.type = 'button';
        b.innerHTML = (iconName ? icon(iconName) : '') + '<span class="pet-btn__label"></span>';
        b.querySelector('.pet-btn__label').textContent = label;
        Object.keys(data || {}).forEach(function (k) { b.dataset[k] = data[k]; });
        return b;
    }

    // ------------------------------------------------------------------------------------
    // PetsApi — fetch z CSRF; każda porażka to {error, message, status}
    // ------------------------------------------------------------------------------------

    function fail(error, message, status) {
        return { error: error, message: message || GENERIC_ERROR, status: status || 0 };
    }

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    // PetsApi i PetsState żyją w static/js/pet/pets-core.js (wspólne z widgetem dashboardu i towarzyszem;
    // etap 5) — home.html ładuje core przed tym plikiem.
    var PetsApi = window.PetsApi;
    var PetsState = window.PetsState;
    if (!PetsApi || !PetsState) {
        if (window.console) console.error('pets.js: brak pets-core.js (PetsApi/PetsState)');
        return;
    }

    // ------------------------------------------------------------------------------------
    // Strona
    // ------------------------------------------------------------------------------------

    var root = document.getElementById('petsApp');
    if (!root) return;

    var speciesInfo = safeParse(root.dataset.species) || {};
    var clockOffset = 0;   // czas serwera − czas przeglądarki (ms), z pola `now` stanu

    function serverNow() { return Date.now() + clockOffset; }

    function secondsUntil(iso) {
        var t = parseLocal(iso);
        return isNaN(t) ? NaN : (t - serverNow()) / 1000;
    }

    function speciesName(slug) {
        return (speciesInfo[slug] && speciesInfo[slug].name) ||
            (window.PetSpecies && window.PetSpecies[slug] && window.PetSpecies[slug].name) || slug;
    }

    // --- Żądania z kolejnością: starsza odpowiedź nie nadpisze nowszego stanu -------------

    var seq = 0, appliedSeq = 0, lastRefreshAt = 0, refreshing = null, refreshQueued = false;

    function applyState(state, mySeq) {
        if (!state || mySeq < appliedSeq) return;
        appliedSeq = mySeq;
        PetsState.set(state);
    }

    function refresh() {
        // Odświeżenie w locie mogło wystartować przed zdarzeniem, które je wywołuje (np. 409) —
        // wtedy po nim leci jeszcze jedno, świeże
        if (refreshing) {
            refreshQueued = true;
            return refreshing;
        }
        var mySeq = ++seq;
        lastRefreshAt = Date.now();
        refreshing = PetsApi.get('/stan').then(function (state) {
            applyState(state, mySeq);
        }, function (err) {
            // Odświeżenie w tle: bez toastu poza wygasłą sesją (i tak nic nie da się zrobić)
            if (err && err.error === 'session_expired') toast(err.message, 'warning');
        }).then(function () {
            refreshing = null;
            if (refreshQueued) {
                refreshQueued = false;
                refresh();
            }
        });
        return refreshing;
    }

    /**
     * Jeden punkt obsługi błędów API (Review Focus 2–3):
     * 409 (np. `not_available` po podwójnym kliknięciu) → bez toastu, tylko odświeżenie stanu;
     * 410 `pet_gone` → toast z komunikatem + odświeżenie (karta znika, album pokazuje pamięć);
     * 400 (zły JSON albo wygasły token CSRF — nieodróżnialne), 5xx, nie-JSON, sieć → ogólny toast.
     */
    function handleError(err) {
        var code = err && err.error, status = err && err.status;
        if (status === 409) { refresh(); return; }
        if (status === 410 || code === 'pet_gone') { toast(err.message, 'info'); refresh(); return; }
        if (code === 'session_expired' || code === 'rate_limited') { toast(err.message, 'warning'); return; }
        if (code === 'network') { toast(err.message, 'error'); return; }
        if (status === 403 || status === 404) { toast(err.message, 'error'); refresh(); return; }
        toast(GENERIC_ERROR, 'error');
    }

    /** GA4 (docs/GOOGLE_ANALYTICS.md): tylko nazwa akcji i nastrój — bez imion, identyfikatorów i treści. */
    function trackPetEvent(path, body, resp) {
        if (typeof window.trackEvent !== 'function') return;
        try {
            if (/\/akcja$/.test(path) && body && body.action) {
                var id = parseInt(path.split('/')[1], 10);
                var pet = ((resp.state && resp.state.pets) || []).filter(function (p) { return p.id === id; })[0];
                window.trackEvent('pet_action', { action: body.action, mood: pet ? pet.mood : 'unknown' });
            } else if (/\/wykluj$/.test(path) && resp.result) {
                window.trackEvent('pet_hatch', { result: resp.result });
            }
        } catch (e) { /* analityka nie może psuć gry */ }
    }

    /** POST z kolejnością stanu i wspólną obsługą błędów; `quiet` = kody obsługiwane przez wołającego. */
    function send(path, body, opts) {
        opts = opts || {};
        var mySeq = ++seq;
        return PetsApi.post(path, body, opts).then(function (resp) {
            applyState(resp.state, mySeq);
            if (resp.new_achievements && resp.new_achievements.length && !opts.deferAchievements) showAchievements();
            trackPetEvent(path, body, resp);
            return resp;
        }, function (err) {
            if (!(opts.quiet && opts.quiet.indexOf(err && err.error) >= 0)) handleError(err);
            throw err;
        });
    }

    /** Odznaki od razu (spec §3.8): wyczyść znacznik checkera, pobierz nieobejrzane i pokaż. */
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

    // ------------------------------------------------------------------------------------
    // Nagłówek: noc
    // ------------------------------------------------------------------------------------

    var nightBanner = root.querySelector('[data-pets-night]');

    function renderNight(state) {
        if (!nightBanner) return;
        var night = state.night || {};
        nightBanner.hidden = !night.is_night;
        if (night.is_night) {
            var factor = state.config && state.config.night_factor;
            var slower = factor > 0 && factor < 1 ? Math.round(1 / factor) + '× wolniej' : 'wolniej';
            nightBanner.textContent = 'Jest noc (' + night.start + ':00–' + night.end + ':00) — pupile śpią, a ich ' +
                'potrzeby rosną ' + slower + '. Głodny albo chory pupil nie zaśnie, dopóki się nim nie zajmiesz.';
        }
    }

    // ------------------------------------------------------------------------------------
    // Gniazdko: jajka do odebrania, inkubacja, odliczanie do miesięcznego
    // ------------------------------------------------------------------------------------

    var nestBody = root.querySelector('#petsNest .pets-section__body');
    var nest = { sig: null, eggs: {}, available: null, monthly: null, list: null, empty: null };

    var EGG_SOURCE = {
        start: 'Jajko startowe', monthly: 'Jajko miesięczne', rescue: 'Jajko ratunkowe', granted: 'Jajko w prezencie'
    };

    function buildNest() {
        nest.available = el('div', 'pets-nest__available');
        nest.list = el('div', 'pets-nest__eggs');
        nest.monthly = el('p', 'pets-nest__monthly');
        nest.empty = el('p', 'pets-nest__empty', 'Gniazdko jest teraz puste.');
        nestBody.appendChild(nest.available);
        nestBody.appendChild(nest.list);
        nestBody.appendChild(nest.empty);
        nestBody.appendChild(nest.monthly);
        nestBody.addEventListener('click', onNestClick);
    }

    function availableTile(item) {
        var tile = el('article', 'pets-egg-tile pets-egg-tile--' + item.source);
        var art = el('div', 'pets-egg-tile__art');
        if (window.PetRig) window.PetRig.mountEgg(art, { pct: 0, size: 'mini' });
        var info = el('div', 'pets-egg-tile__info');
        info.appendChild(el('h3', 'pets-egg-tile__title', EGG_SOURCE[item.source] || 'Jajko'));
        var desc;
        if (item.source === 'start') desc = 'Twoje pierwsze jajko! Odbierz je i ogrzewaj przy każdej wizycie — tak wykluje się szybciej.';
        else if (item.source === 'monthly') desc = 'Nowe jajko czeka na odbiór. Kolejne pojawi się za miesiąc od odebrania.';
        else if (item.source === 'rescue') {
            desc = item.pet_name
                ? 'Pupil ' + item.pet_name + ' odszedł do gwiazd. To jajko czeka na Ciebie.'
                : 'Twój pupil odszedł do gwiazd. To jajko czeka na Ciebie.';
        } else if (item.source === 'granted') {
            var n = Math.max(1, parseInt(item.count, 10) || 1);
            desc = n === 1 ? 'Czeka na Ciebie jajko w prezencie.'
                : 'Czeka na Ciebie ' + n + ' ' + plural(n, 'jajko', 'jajka', 'jajek') + ' w prezencie.';
        } else desc = 'Jajko czeka na odbiór.';
        info.appendChild(el('p', 'pets-egg-tile__desc', desc));
        var data = { nestAction: 'claim', source: item.source };
        if (item.pet_id != null) data.petId = String(item.pet_id);
        var btn = button('Odbierz', 'egg', 'primary', data);
        tile.appendChild(art);
        tile.appendChild(info);
        tile.appendChild(btn);
        return tile;
    }

    function eggCard(egg) {
        var card = el('article', 'pets-egg');
        card.dataset.eggId = String(egg.id);
        var art = el('div', 'pets-egg__art');
        var info = el('div', 'pets-egg__info');
        var title = el('h3', 'pets-egg__title');
        var track = el('div', 'pets-progress');
        track.setAttribute('role', 'progressbar');
        track.setAttribute('aria-valuemin', '0');
        track.setAttribute('aria-valuemax', '100');
        track.setAttribute('aria-label', 'Postęp inkubacji');
        var fill = el('div', 'pets-progress__fill');
        track.appendChild(fill);
        var status = el('p', 'pets-egg__status');
        info.appendChild(title);
        info.appendChild(track);
        info.appendChild(status);
        var actions = el('div', 'pets-egg__actions');
        card.appendChild(art);
        card.appendChild(info);
        card.appendChild(actions);
        var rig = window.PetRig ? window.PetRig.mountEgg(art, { pct: egg.progress_pct, boosted: !!egg.boost_until, ready: egg.ready, size: 'card' }) : null;
        var entry = { el: card, rig: rig, title: title, track: track, fill: fill, status: status, actions: actions, egg: null, sig: '' };
        updateEggCard(entry, egg);
        return entry;
    }

    function updateEggCard(entry, egg) {
        entry.egg = egg;
        var pct = Math.max(0, Math.min(100, Number(egg.progress_pct) || 0));
        entry.title.textContent = EGG_SOURCE[egg.source] || 'Jajko';
        entry.fill.style.width = pct + '%';
        entry.track.setAttribute('aria-valuenow', String(Math.round(pct)));
        entry.el.classList.toggle('is-ready', !!egg.ready);
        entry.el.classList.toggle('is-boosted', !!egg.boost_until && !egg.ready);
        if (entry.rig) entry.rig.update({ pct: pct, boosted: !!egg.boost_until, ready: !!egg.ready });
        var sig = [egg.ready, egg.can_warm, egg.boost_until].join('|');
        if (sig !== entry.sig) {
            entry.sig = sig;
            entry.actions.innerHTML = '';
            if (egg.ready) {
                entry.actions.appendChild(button('Wykluj', 'sparkle', 'primary', { nestAction: 'hatch', eggId: String(egg.id) }));
            } else {
                var warm = button('Ogrzej', 'flame', null, { nestAction: 'warm', eggId: String(egg.id) });
                warm.disabled = !egg.can_warm;
                entry.actions.appendChild(warm);
            }
        }
        tickEggCard(entry);
    }

    function tickEggCard(entry) {
        var egg = entry.egg;
        var pct = Math.round(Math.max(0, Math.min(100, Number(egg.progress_pct) || 0)));
        if (egg.ready) {
            entry.status.textContent = 'Gotowe do wyklucia!';
        } else if (egg.boost_until) {
            var left = secondsUntil(egg.boost_until);
            var boostFactor = (PetsState.current && PetsState.current.config && PetsState.current.config.boost_factor) || 2;
            entry.status.textContent = pct + '% · ogrzane, ciepło (tempo ×' + boostFactor + ') jeszcze ' + formatDuration(left > 0 ? left : 0);
        } else {
            entry.status.textContent = pct + '% · ogrzej, żeby przyspieszyć wyklucie';
        }
    }

    function renderNest(state) {
        if (!nestBody) return;
        if (!nest.available) buildNest();
        var available = state.eggs_available || [];
        var sig = JSON.stringify(available);
        if (sig !== nest.sig) {
            nest.sig = sig;
            nest.available.innerHTML = '';
            available.forEach(function (item) { nest.available.appendChild(availableTile(item)); });
        }
        nest.available.hidden = !available.length;

        var eggs = state.eggs || [];
        var seen = {};
        eggs.forEach(function (egg, i) {
            seen[egg.id] = true;
            var entry = nest.eggs[egg.id];
            if (entry) updateEggCard(entry, egg);
            else entry = nest.eggs[egg.id] = eggCard(egg);
            if (nest.list.children[i] !== entry.el) nest.list.insertBefore(entry.el, nest.list.children[i] || null);
        });
        Object.keys(nest.eggs).forEach(function (id) {
            if (seen[id]) return;
            var entry = nest.eggs[id];
            if (entry.rig) entry.rig.destroy();
            if (entry.el.parentNode) entry.el.parentNode.removeChild(entry.el);
            delete nest.eggs[id];
        });
        nest.list.hidden = !eggs.length;
        nest.empty.hidden = !!(available.length || eggs.length);
        tickNest();
    }

    function tickNest() {
        if (!nest.monthly) return;
        var state = PetsState.current || {};
        var monthlyWaiting = (state.eggs_available || []).some(function (e) { return e.source === 'monthly'; });
        var left = state.next_monthly_at ? secondsUntil(state.next_monthly_at) : NaN;
        if (!monthlyWaiting && left > 0) {
            nest.monthly.hidden = false;
            nest.monthly.textContent = 'Następne jajko miesięczne za ' + formatDuration(left) + '.';
        } else {
            nest.monthly.hidden = true;
        }
        Object.keys(nest.eggs).forEach(function (id) { tickEggCard(nest.eggs[id]); });
    }

    function onNestClick(e) {
        var btn = e.target.closest('[data-nest-action]');
        if (!btn || btn.disabled || !nestBody.contains(btn)) return;
        var action = btn.dataset.nestAction;
        if (action === 'claim') {
            var body = { source: btn.dataset.source };
            if (btn.dataset.petId) body.pet_id = parseInt(btn.dataset.petId, 10);
            setBusy(btn, true);
            send('/jajka/odbierz', body).then(function () {
                if (body.source === 'start') {
                    // Pierwsze jajko = najlepszy moment na prośbę o pushe (push-banner.js:144 sam sprawdza
                    // subskrypcję i cooldown)
                    try { window.dispatchEvent(new Event('push-force-banner')); } catch (e) { /* stare przeglądarki */ }
                }
                toast('Jajko odebrane! Ogrzewaj je przy każdej wizycie, a szybciej się wykluje.', 'success');
            }, function () { setBusy(btn, false); });
        } else if (action === 'warm') {
            setBusy(btn, true);
            send('/jajka/' + parseInt(btn.dataset.eggId, 10) + '/ogrzej', {}).then(function () {
                if (window.Haptics) window.Haptics.tap();
            }, function () { setBusy(btn, false); });
        } else if (action === 'hatch' && typeof hatchEgg === 'function') {
            hatchEgg(parseInt(btn.dataset.eggId, 10), btn);
        }
    }

    var hatchEgg = null;   // modal wyklucia (niżej)

    // ------------------------------------------------------------------------------------
    // Domek: siatka kart żywych pupili
    // ------------------------------------------------------------------------------------

    var homeGrid = root.querySelector('#petsHome .pets-grid');
    var cards = {};
    var homeIntro = null;

    function onCardAction(pet, action, count) {
        var body = { action: action };
        if (action === 'pat') body.count = count;
        // Paczka pat pat może lecieć przy zamykaniu karty — keepalive dowiezie ją mimo to
        return send('/' + pet.id + '/akcja', body, action === 'pat' ? { keepalive: true } : null);
    }

    function onCardRename(pet, name) {
        return send('/' + pet.id + '/imie', { name: name }, { quiet: ['bad_name'] });
    }

    function introBlock(state) {
        var box = el('div', 'pets-intro');
        var hasEgg = (state.eggs || []).length > 0;
        box.appendChild(el('h3', 'pets-intro__title', hasEgg ? 'Domek czeka na pierwszego lokatora' : 'Jak to działa?'));
        if (hasEgg) box.appendChild(el('p', 'pets-intro__text', 'Jajko jest już w gniazdku — ogrzewaj je, a gdy będzie gotowe, kliknij „Wykluj".'));
        var list = el('ul', 'pets-intro__list');
        var night = state.night || {};
        [
            'Odbierz jajko w gniazdku i ogrzewaj je przy każdej wizycie — tak wykluje się szybciej.',
            'Każde jajko to losowy z ośmiu gatunków. Zbierz wszystkie w albumie!',
            'Karm, baw się i myj pupila. Jedna wizyta dziennie wystarczy, żeby był zdrowy, dwie–trzy — żeby był szczęśliwy.',
            'W nocy (' + (night.start != null && night.start !== night.end ? night.start + ':00–' + night.end + ':00' : '23:00–7:00') +
                ') pupil śpi. Zaniedbany przez kilka dni choruje, a w końcu może odejść do gwiazd.'
        ].forEach(function (text) { list.appendChild(el('li', null, text)); });
        box.appendChild(list);
        return box;
    }

    function renderHome(state) {
        if (!homeGrid) return;
        var pets = state.pets || [];
        var cardCtx = { now: state.now, night: state.night && state.night.start !== state.night.end ? state.night : null };
        var seen = {};
        pets.forEach(function (pet, i) {
            seen[pet.id] = true;
            var card = cards[pet.id];
            if (card) card.update(pet, cardCtx);
            else {
                card = cards[pet.id] = window.PetCard.render(homeGrid, pet, {
                    mini: false, species: speciesInfo, onAction: onCardAction, onRename: onCardRename,
                    now: cardCtx.now, night: cardCtx.night
                });
            }
            // Przestawiamy tylko, gdy kolejność się zmieniła (przeniesienie węzła restartuje animacje)
            if (homeGrid.children[i] !== card.el) homeGrid.insertBefore(card.el, homeGrid.children[i] || null);
        });
        Object.keys(cards).forEach(function (id) {
            if (seen[id]) return;
            cards[id].destroy();
            delete cards[id];
        });
        if (homeIntro) {
            homeIntro.parentNode.removeChild(homeIntro);
            homeIntro = null;
        }
        if (!pets.length) {
            homeIntro = introBlock(state);
            homeGrid.parentNode.insertBefore(homeIntro, homeGrid);
        }
        homeGrid.hidden = !pets.length;
    }

    // ------------------------------------------------------------------------------------
    // Album: 8 kart — nieodkryty (sylwetka) / żyje / karta pamięci
    // ------------------------------------------------------------------------------------

    var albumBody = root.querySelector('#petsAlbum .pets-album');
    var albumCount = root.querySelector('#petsAlbum .pets-album__count');
    var albumSlots = [];
    var STAGE_LABEL = { maluch: 'Maluch', dziecko: 'Dziecko', dorosly: 'Dorosły' };

    function formatDate(iso) {
        var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
        return m ? m[3] + '.' + m[2] + '.' + m[1] : '?';
    }

    function daysText(n) {
        n = Math.max(0, parseInt(n, 10) || 0);
        return n + ' ' + (n === 1 ? 'dzień' : 'dni');
    }

    function buildAlbumSlot(entry, pet) {
        var card = el('article', 'pets-album__card pets-album__card--' + entry.status);
        var art = el('div', 'pets-album__art');
        var info = el('div', 'pets-album__info');
        card.appendChild(art);
        card.appendChild(info);
        var rig = null;
        var R = window.PetRig;
        if (entry.status === 'alive' && pet) {
            if (R) rig = R.mount(art, { species: entry.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: pet.asleep, size: 'mini' });
            info.appendChild(el('h3', 'pets-album__name', pet.name || speciesName(entry.species)));
            info.appendChild(el('p', 'pets-album__meta', speciesName(entry.species) + ' · ' + (STAGE_LABEL[pet.stage] || '')));
        } else if (entry.status === 'memorial') {
            if (R) rig = R.mountMemorial(art, { species: entry.species, size: 'mini', lit: !entry.can_light });
            info.appendChild(el('h3', 'pets-album__name', speciesName(entry.species)));
            info.appendChild(el('p', 'pets-album__memorial',
                (entry.name ? 'Pupil ' + entry.name : 'Twój pupil') + ' odszedł do gwiazd.'));
            info.appendChild(el('p', 'pets-album__meta', formatDate(entry.hatched_at) + ' – ' + formatDate(entry.died_at)));
            info.appendChild(el('p', 'pets-album__meta', 'Wiek: ' + daysText(entry.age_days) + ' · ' + daysText(entry.care_days) + ' opieki'));
            var lights = parseInt(entry.lights_count, 10) || 0;
            info.appendChild(el('p', 'pets-album__lights', 'Światełka: ' + lights));
            if (entry.can_light) {
                card.appendChild(button('Zapal światełko', 'flame', null, { albumAction: 'light', petId: String(entry.pet_id) }));
            } else {
                card.appendChild(el('p', 'pets-album__lit', 'Dziś już świeci światełko'));
            }
        } else {
            art.classList.add('pets-album__art--silhouette');
            if (R) rig = R.mount(art, { species: entry.species, stage: 'dorosly', size: 'mini' });
            info.appendChild(el('h3', 'pets-album__name', 'Nieodkryty'));
            info.appendChild(el('p', 'pets-album__meta', 'Wykluj jajko, żeby go poznać'));
        }
        return { el: card, rig: rig, key: '' };
    }

    function renderAlbum(state) {
        var album = state.album;
        if (!albumBody || !album) return;   // stan „lite" nie ma albumu
        var petsById = {};
        (state.pets || []).forEach(function (p) { petsById[p.id] = p; });
        var known = album.filter(function (a) { return a.status !== 'unknown'; }).length;
        if (albumCount) {
            albumCount.textContent = known + '/' + album.length;
            albumCount.setAttribute('aria-label', 'Odkryte gatunki: ' + known + ' z ' + album.length);
        }
        album.forEach(function (entry, i) {
            var pet = entry.status === 'alive' ? petsById[entry.pet_id] : null;
            var key = [entry.species, entry.status, entry.pet_id, entry.name, entry.lights_count, entry.can_light,
                pet ? pet.name : '', pet ? pet.stage : ''].join('|');
            var slot = albumSlots[i];
            if (slot && slot.key === key) {
                if (pet && slot.rig) slot.rig.update({ stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: pet.asleep });
                return;
            }
            var fresh = buildAlbumSlot(entry, pet);
            fresh.key = key;
            if (slot) {
                if (slot.rig) slot.rig.destroy();
                albumBody.replaceChild(fresh.el, slot.el);
            } else {
                albumBody.appendChild(fresh.el);
            }
            albumSlots[i] = fresh;
        });
    }

    if (albumBody) {
        albumBody.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-album-action="light"]');
            if (!btn || btn.disabled || !albumBody.contains(btn)) return;
            setBusy(btn, true);
            send('/' + parseInt(btn.dataset.petId, 10) + '/swiatelko', {}).then(function () {
                if (window.Haptics) window.Haptics.tap();
            }, function () { setBusy(btn, false); });
        });
    }

    // ------------------------------------------------------------------------------------
    // Towarzysz i powiadomienia
    // ------------------------------------------------------------------------------------

    var settingsBody = root.querySelector('#petsSettings .pets-section__body');
    var settings = null;

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

    function buildSettings() {
        settings = { petsSig: null, saving: false };
        var pick = el('div', 'pets-setting pets-setting--select');
        var pickText = el('div', 'pets-setting__text');
        var pickLabel = el('label', 'pets-setting__label', 'Kto Ci towarzyszy');
        pickLabel.htmlFor = 'petsCompanionSelect';
        pickText.appendChild(pickLabel);
        pickText.appendChild(el('p', 'pets-setting__hint', 'Pupil, który będzie z Tobą na dole stron panelu klienta.'));
        var select = el('select', 'pets-select');
        select.id = 'petsCompanionSelect';
        pick.appendChild(pickText);
        pick.appendChild(select);

        var show = switchRow('petsCompanionToggle', 'Pokazuj towarzysza na stronach', null);
        var empty = el('p', 'pets-settings__empty', 'Towarzysza wybierzesz, gdy w domku zamieszka pierwszy pupil.');
        var notify = switchRow('petsNotifyToggle', 'Powiadomienia o pupilach (push i e-mail)',
            'Damy znać, gdy pupil będzie głodny albo chory, gdy jajko będzie gotowe do wyklucia i gdy czeka nowe.');

        settingsBody.appendChild(pick);
        settingsBody.appendChild(show.row);
        settingsBody.appendChild(empty);
        settingsBody.appendChild(notify.row);
        settings.pick = pick;
        settings.select = select;
        settings.showRow = show.row;
        settings.show = show.input;
        settings.empty = empty;
        settings.notify = notify.input;

        select.addEventListener('change', saveCompanion);
        show.input.addEventListener('change', saveCompanion);
        notify.input.addEventListener('change', saveNotify);
        loadNotify();
    }

    function renderSettings(state) {
        if (!settingsBody) return;
        if (!settings) buildSettings();
        if (settings.saving) return;
        var pets = state.pets || [];
        var companion = state.companion || { enabled: true, pet_id: null, auto: true };
        var has = pets.length > 0;
        settings.pick.hidden = !has;
        settings.showRow.hidden = !has;
        settings.empty.hidden = has;
        var sig = pets.map(function (p) { return p.id + ':' + p.name; }).join('|');
        if (sig !== settings.petsSig) {
            settings.petsSig = sig;
            settings.select.innerHTML = '';
            var auto = el('option', null, 'Automatycznie — ten, kto najbardziej potrzebuje opieki');
            auto.value = 'auto';
            settings.select.appendChild(auto);
            pets.forEach(function (p) {
                var opt = el('option', null, (p.name || speciesName(p.species)) + ' (' + speciesName(p.species) + ')');
                opt.value = String(p.id);
                settings.select.appendChild(opt);
            });
        }
        settings.select.value = companion.auto || companion.pet_id == null ? 'auto' : String(companion.pet_id);
        settings.show.checked = !!companion.enabled;
        settings.select.disabled = false;
        settings.show.disabled = false;
    }

    function saveCompanion() {
        var value = settings.select.value;
        var body = { pet_id: value === 'auto' ? null : parseInt(value, 10), enabled: !!settings.show.checked };   // boolean, nie string
        settings.saving = true;
        settings.select.disabled = true;
        settings.show.disabled = true;
        send('/towarzysz', body).then(function () {
            toast('Zapisano ustawienia towarzysza.', 'success');
        }, function () { /* toast/odświeżenie już były */ }).then(function () {
            settings.saving = false;
            if (PetsState.current) renderSettings(PetsState.current);
        });
    }

    // Ten sam zapis co przełącznik w profilu (POST /notifications/preferences {pet_updates})
    var PREFS_URL = '/notifications/preferences';

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
        var input = settings.notify;
        input.disabled = true;   // do wczytania stanu z serwera — inaczej „włączone" kłamałoby przy błędzie
        prefsRequest({ credentials: 'same-origin', headers: { 'Accept': 'application/json' } }).then(function (prefs) {
            if (prefs && 'pet_updates' in prefs) input.checked = !!prefs.pet_updates;
            input.disabled = false;
        }, function () {
            settings.notify.closest('.pets-setting').classList.add('is-unavailable');
        });
    }

    function saveNotify() {
        var input = settings.notify;
        var on = input.checked;
        input.disabled = true;
        prefsRequest({
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ pet_updates: on })
        }).then(function (data) {
            if (!data || !data.success) throw fail('bad_response', GENERIC_ERROR, 0);
            toast(on ? 'Powiadomienia o pupilach włączone.' : 'Powiadomienia o pupilach wyłączone.', 'success');
        }).catch(function (err) {
            input.checked = !on;
            toast(err && err.error === 'session_expired' ? err.message : 'Nie udało się zapisać ustawienia powiadomień.', 'error');
        }).then(function () { input.disabled = false; });
    }

    // ------------------------------------------------------------------------------------
    // Modal wyklucia (#petHatchModal): jajko pęka → POST wykluj → nowy gatunek z konfetti
    // ------------------------------------------------------------------------------------

    var modal = document.getElementById('petHatchModal');
    var hatch = { phase: 'idle', egg: null, rig: null, trigger: null, petId: null, defaultName: '', achievements: false };

    function reducedMotion() {
        return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

    if (modal) {
        // Poza <main>: przodkowie z backdrop-filter/transform tworzą kontekst warstw i chowali
        // fixed overlay pod topbar/sidebar (ta sama lekcja co dropdowny statusów)
        if (modal.parentNode !== document.body) document.body.appendChild(modal);
        var hm = {
            content: modal.querySelector('.pet-hatch'),
            title: modal.querySelector('#petHatchTitle'),
            stage: modal.querySelector('[data-hatch-stage]'),
            text: modal.querySelector('[data-hatch-text]'),
            form: modal.querySelector('[data-hatch-form]'),
            input: modal.querySelector('#petHatchName'),
            error: modal.querySelector('[data-hatch-error]'),
            footer: modal.querySelector('.pet-hatch__footer'),
            done: modal.querySelector('[data-hatch-done]'),
            close: modal.querySelector('.modal-close')
        };

        var clearStage = function () {
            if (hatch.egg) { hatch.egg.destroy(); hatch.egg = null; }
            if (hatch.rig) { hatch.rig.destroy(); hatch.rig = null; }
            hm.stage.innerHTML = '';
        };

        var setChrome = function (interactive) {
            hm.footer.hidden = !interactive;
            hm.close.hidden = !interactive;
        };

        var setFormDisabled = function (on) {
            hm.input.disabled = on;
            Array.prototype.forEach.call(hm.form.querySelectorAll('button'), function (b) { b.disabled = on; });
        };

        var showNameError = function (message) {
            hm.error.textContent = message;
            hm.error.hidden = false;
            hm.input.setAttribute('aria-invalid', 'true');
            hm.input.focus();
        };

        var findPet = function (list, id) {
            for (var i = 0; i < (list || []).length; i++) if (list[i].id === id) return list[i];
            return null;
        };

        var reveal = function (resp, prevPets) {
            hatch.phase = 'reveal';
            if (window.Haptics) window.Haptics.pattern('hatch');
            clearStage();
            var pets = (resp.state && resp.state.pets) || [];
            var name = resp.species_name || speciesName(resp.species);
            hatch.achievements = !!(resp.new_achievements && resp.new_achievements.length);
            var R = window.PetRig;
            if (resp.result === 'new') {
                var pet = findPet(pets, resp.pet_id) || {};
                hatch.petId = resp.pet_id;
                hatch.defaultName = pet.name || name;
                if (R) hatch.rig = R.mount(hm.stage, { species: resp.species, stage: pet.stage || 'maluch', size: 'card' });
                if (hatch.rig) hatch.rig.playAction('celebrate');
                hm.title.textContent = 'Masz nowego pupila!';
                hm.text.textContent = 'To ' + name + '! Jak go nazwiesz?';
                hm.input.value = hatch.defaultName;
                hm.input.removeAttribute('aria-invalid');
                hm.error.hidden = true;
                hm.form.hidden = false;
                setFormDisabled(false);
                hm.done.textContent = 'Później';
                hm.done.className = 'pet-btn pet-btn--ghost';
                setChrome(true);
                hm.input.focus();
                hm.input.select();
            } else {
                var starred = findPet(pets, resp.starred_pet_id) || {};
                var before = findPet(prevPets, resp.starred_pet_id);
                var stars = parseInt(starred.stars, 10) || 0;
                var prevStars = before ? (parseInt(before.stars, 10) || 0) : Math.max(0, stars - 1);
                if (R) hatch.rig = R.mount(hm.stage, { species: resp.species, stage: starred.stage || 'dorosly', stars: prevStars, size: 'card' });
                if (hatch.rig) {
                    var rig = hatch.rig;
                    rig.playAction('celebrate').then(function () { if (hatch.rig === rig) rig.setStars(stars); });
                }
                // „Twój pupil {imię}" — bez rodzaju imienia („Twój Iskra" brzmi źle)
                var who = starred.name ? 'Twój pupil ' + starred.name : 'Twój pupil';
                // „Znowu …!" zamiast „To drugi …!" ze specu — bez rodzaju („drugi Wiewiórka" brzmi źle)
                hm.title.textContent = 'Znowu ' + name + '!';
                hm.text.textContent = stars > prevStars ? who + ' dostaje gwiazdkę ⭐' : who + ' ma już komplet gwiazdek ⭐';
                hm.form.hidden = true;
                hm.done.textContent = 'Super!';
                hm.done.className = 'pet-btn pet-btn--primary';
                setChrome(true);
                hm.done.focus();
            }
        };

        var closeHatch = function () {
            if (hatch.phase !== 'reveal') return;   // w trakcie pękania nie zamykamy (żądanie w locie)
            hatch.phase = 'closing';
            modal.classList.add('closing');
            setTimeout(function () {
                modal.classList.remove('active', 'closing');
                modal.setAttribute('aria-hidden', 'true');
                clearStage();
                hatch.phase = 'idle';
                var back = hatch.trigger;
                if (back && document.body.contains(back) && !back.disabled) back.focus();
                else {
                    var title = document.getElementById('petsHomeTitle');
                    if (title) {
                        title.setAttribute('tabindex', '-1');
                        title.focus();
                    }
                }
                if (hatch.achievements) {
                    hatch.achievements = false;
                    showAchievements();
                }
            }, reducedMotion() ? 0 : 350);
        };

        hatchEgg = function (eggId, trigger) {
            if (hatch.phase !== 'idle' || !window.PetRig) return;
            hatch.phase = 'hatching';
            hatch.trigger = trigger || null;
            hatch.petId = null;
            hatch.achievements = false;
            var prevPets = ((PetsState.current && PetsState.current.pets) || []).slice();
            setBusy(trigger, true);
            clearStage();
            hm.title.textContent = 'Coś się dzieje…';
            hm.text.textContent = 'Jajko pęka!';
            hm.form.hidden = true;
            setChrome(false);
            hatch.egg = window.PetRig.mountEgg(hm.stage, { pct: 100, ready: true, size: 'card' });
            modal.classList.remove('closing');
            modal.classList.add('active');
            modal.setAttribute('aria-hidden', 'false');
            hm.content.focus();
            var req = send('/jajka/' + eggId + '/wykluj', {}, { deferAchievements: true });
            Promise.all([hatch.egg.hatch(), req]).then(function (results) {
                reveal(results[1], prevPets);
            }, function () {
                // Błąd pokazał już handleError; zamykamy bez odsłaniania
                hatch.phase = 'reveal';
                setBusy(trigger, false);
                closeHatch();
            });
        };

        hm.form.addEventListener('submit', function (e) {
            e.preventDefault();
            if (hatch.phase !== 'reveal' || !hatch.petId) return;
            var name = String(hm.input.value || '').split(/\s+/).filter(Boolean).join(' ');
            var len = Array.from(name).length;
            hm.input.removeAttribute('aria-invalid');
            hm.error.hidden = true;
            if (len < 1 || len > 20) {
                showNameError('Imię ma mieć od 1 do 20 znaków.');
                return;
            }
            if (name === hatch.defaultName) {
                closeHatch();
                return;
            }
            setFormDisabled(true);
            send('/' + hatch.petId + '/imie', { name: name }, { quiet: ['bad_name'] }).then(function (resp) {
                toast('Witaj w domku, ' + resp.name + '!', 'success');
                closeHatch();
            }, function (err) {
                setFormDisabled(false);
                // Pupil już istnieje — modal zostaje otwarty, komunikat serwera przy polu (Review Focus 4)
                if (err && err.error === 'bad_name') showNameError(err.message || 'Nieprawidłowe imię.');
                else hm.input.focus();
            });
        });

        modal.addEventListener('click', function (e) {
            if (e.target === modal || e.target.closest('[data-hatch-close]')) closeHatch();
        });

        document.addEventListener('keydown', function (e) {
            if (!modal.classList.contains('active')) return;
            if (e.key === 'Escape') {
                e.preventDefault();
                closeHatch();
                return;
            }
            if (e.key !== 'Tab') return;
            var items = Array.prototype.filter.call(
                modal.querySelectorAll('button:not([disabled]), input:not([disabled]), [href]'),
                function (x) { return x.offsetParent !== null; }
            );
            if (!items.length) {
                e.preventDefault();
                hm.content.focus();
                return;
            }
            var first = items[0], last = items[items.length - 1];
            if (e.shiftKey && (document.activeElement === first || document.activeElement === hm.content)) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        });
    }

    // ------------------------------------------------------------------------------------
    // Render, zegar, odświeżanie
    // ------------------------------------------------------------------------------------

    function render(state) {
        var t = parseLocal(state.now);
        if (!isNaN(t)) clockOffset = t - Date.now();
        renderNight(state);
        renderNest(state);
        renderHome(state);
        renderAlbum(state);
        renderSettings(state);
        scheduleEventRefresh(state);
    }

    // Odświeżenie dokładnie wtedy, gdy coś się zmienia z czasu (koniec ogrzewania, lek, okno
    // obudzenia, miesięczne jajko) — interwał 5 min łapie resztę (np. pasek spada poniżej 80).
    var eventTimer = 0;
    function scheduleEventRefresh(state) {
        clearTimeout(eventTimer);
        var times = [];
        (state.eggs || []).forEach(function (egg) { if (egg.boost_until) times.push(egg.boost_until); });
        (state.pets || []).forEach(function (pet) {
            if (pet.heal_available_at) times.push(pet.heal_available_at);
            if (pet.awake_until) times.push(pet.awake_until);
        });
        if (state.next_monthly_at) times.push(state.next_monthly_at);
        var soonest = Infinity;
        times.forEach(function (iso) {
            var s = secondsUntil(iso);
            if (s > 0 && s < soonest) soonest = s;
        });
        if (soonest * 1000 < REFRESH_EVERY_MS) eventTimer = setTimeout(refresh, soonest * 1000 + 1500);
    }

    PetsState.onChange(render);

    setInterval(function () {
        if (!PetsState.current) return;
        tickNest();
    }, 1000);

    setInterval(function () {
        if (document.visibilityState === 'hidden') return;
        refresh();
    }, REFRESH_EVERY_MS);

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible' && Date.now() - lastRefreshAt > 60 * 1000) refresh();
    });

    var initial = safeParse(root.dataset.state);
    lastRefreshAt = Date.now();
    if (initial) PetsState.set(initial);
    else refresh();
})();
