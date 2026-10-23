/**
 * Moje pupile — świat (spec v3 §3, §9): router scen i wspólne akcje.
 *
 * Sceny (spec v3.1 §4.1): mapa (/client/pupile), domek, szpital (hol), inkubatorium (/szpital/inkubatorium),
 * izba (/szpital/izba-przyjec), warsztat, ogród. Każda scena to osobny plik w static/js/pet/world/, który
 * rejestruje się w window.PetsWorld.scenes[klucz] =
 * { title, create(ctx, host) -> {enter(params), leave(), render(state), setParams(params)?, tick()?} }.
 * Znany klucz bez zarejestrowanego modułu = pusta scena (bez błędu, bez powrotu na mapę).
 * Ten plik ładuje się PO plikach scen (home.html), buduje wspólny `ctx` i przełącza sceny przez
 * history.pushState / popstate — bez przeładowania strony. Pigułka (h1 + link do rodzica) zamiast nagłówka;
 * okna kontekstowe scen: window.PetsSceneWindow (static/js/pet/world/scene-window.js).
 *
 * Korzysta z window.PetsApi i window.PetsState z static/js/pet/pets-core.js (kontrakt bez zmian).
 *
 * Zasady: jedno źródło prawdy renderowania = JSON stanu (data-state, potem API); dane użytkownika
 * (imiona) wyłącznie przez textContent / escapeHtml; zero inline onclick — delegacja zdarzeń z data-*;
 * window.showToast wstawia HTML, więc każdy komunikat idzie przez escapeHtml (komunikaty serwera
 * zawierają imiona pupili).
 */
(function () {
    'use strict';

    var root = document.getElementById('petsApp');
    if (!root || root.getAttribute('data-ready') === '1') return;

    var PetsApi = window.PetsApi;
    var PetsState = window.PetsState;
    if (!PetsApi || !PetsState) {
        if (window.console) console.error('pets.js: brak pets-core.js (PetsApi/PetsState)');
        return;
    }
    root.setAttribute('data-ready', '1');

    var GENERIC_ERROR = 'Coś poszło nie tak, spróbuj za chwilę.';
    var REFRESH_EVERY_MS = 5 * 60 * 1000;
    var PAT_DEBOUNCE_MS = 2000;
    var PAT_MAX = 50;
    var ZOOM_MS = 340;
    // Spec v3.1 §4.1 / plan „Global Constraints”: klucze scen, adresy (jak trasy Flask), rodzic w pigułce
    var SCENE_ORDER = ['mapa', 'domek', 'szpital', 'inkubatorium', 'izba', 'warsztat', 'ogrod'];
    var SCENE_PATH = {
        mapa: '', domek: '/domek', szpital: '/szpital', inkubatorium: '/szpital/inkubatorium',
        izba: '/szpital/izba-przyjec', warsztat: '/warsztat', ogrod: '/ogrod'
    };
    var SCENE_TITLE = {
        mapa: 'Moje pupile', domek: 'Domek', szpital: 'Szpital', inkubatorium: 'Inkubatorium',
        izba: 'Izba przyjęć', warsztat: 'Warsztat', ogrod: 'Ogród wspomnień'
    };
    var SCENE_PARENT = { domek: 'mapa', szpital: 'mapa', warsztat: 'mapa', ogrod: 'mapa', inkubatorium: 'szpital', izba: 'szpital' };
    var PARENT_LABEL = { mapa: 'Świat', szpital: 'Szpital' };
    var QUERY_PARAMS = ['pupil', 'jajko'];      // głębokie linki: domek/izba ?pupil=ID, inkubatorium ?jajko=ID

    var World = window.PetsWorld = window.PetsWorld || {};
    var SCENES = World.scenes = World.scenes || {};

    // ------------------------------------------------------------------------------------
    // Drobne narzędzia (wspólne dla scen przez ctx.u)
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

    /** Chwila z API w UTC ("2026-10-11T19:15:00Z") → ms; Date.parse honoruje `Z`/offset. */
    function parseLocal(iso) {
        return iso ? Date.parse(iso) : NaN;
    }

    // Zegar polski niezależnie od strefy przeglądarki: noc, godziny i daty w grze są polskie (jak na serwerze)
    var PL_CLOCK = null;
    try {
        PL_CLOCK = new Intl.DateTimeFormat('pl-PL', {
            timeZone: 'Europe/Warsaw', hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric',
            hour: 'numeric', minute: 'numeric', second: 'numeric'
        });
    } catch (e) { /* stara przeglądarka bez stref — niżej zegar lokalny */ }

    /** ms → {year, month (1–12), day, hour, minute, second} wg czasu polskiego (Europe/Warsaw). */
    function plParts(ms) {
        var d = new Date(ms);
        if (PL_CLOCK && PL_CLOCK.formatToParts) {
            var out = {};
            PL_CLOCK.formatToParts(d).forEach(function (p) { if (p.type !== 'literal') out[p.type] = +p.value; });
            if (out.hour === 24) out.hour = 0;   // starsze silniki: północ jako „24”
            return out;
        }
        return { year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(),
            hour: d.getHours(), minute: d.getMinutes(), second: d.getSeconds() };
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

    /** Sekundy → „~3 h", „~40 min", „chwilę" (zaokrąglone, do tekstów typu „~N h do wyzdrowienia"). */
    function roughDuration(sec) {
        if (!(sec > 0)) return 'chwilę';
        if (sec >= 5400) return '~' + Math.round(sec / 3600) + ' h';
        if (sec >= 60) return '~' + Math.max(1, Math.round(sec / 60)) + ' min';
        return 'chwilę';
    }

    /** „2026-10-12” (data polska z API) albo chwila „…T…Z” (UTC) → „12.10.2026” wg czasu polskiego. */
    function formatDate(iso) {
        if (/T/.test(iso || '')) {
            var t = Date.parse(iso);
            if (isNaN(t)) return '?';
            var p = plParts(t);
            return (p.day < 10 ? '0' : '') + p.day + '.' + (p.month < 10 ? '0' : '') + p.month + '.' + p.year;
        }
        var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
        return m ? m[3] + '.' + m[2] + '.' + m[1] : '?';
    }

    function daysText(n) {
        n = Math.max(0, parseInt(n, 10) || 0);
        return n + ' ' + (n === 1 ? 'dzień' : 'dni');
    }

    function setBusy(btn, busy) {
        if (!btn) return;
        btn.classList.toggle('is-busy', !!busy);
        btn.disabled = !!busy;
        if (busy) btn.setAttribute('aria-busy', 'true');
        else btn.removeAttribute('aria-busy');
    }

    var ICONS = {
        egg: '<path d="M12 3c3.6 0 6.5 6 6.5 10.2a6.5 6.5 0 0 1-13 0C5.5 9 8.4 3 12 3z"/>',
        flame: '<path d="M12 3c1.2 3 5 5.2 5 10a5 5 0 0 1-10 0c0-2.2 1-3.7 2.1-4.7 0 2 1 3.2 2.1 3.2 0-3-1.3-5 .8-8.5z"/>',
        sparkle: '<path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9z"/><path d="M19 17v4M17 19h4"/>',
        home: '<path d="M4 11l8-7 8 7"/><path d="M6 9.5V20h12V9.5"/><path d="M10 20v-5h4v5"/>',
        cross: '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M12 8v8M8 12h8"/>',
        back: '<path d="M15 5l-7 7 7 7"/>'
    };

    function icon(name, cls) {
        return '<svg class="' + (cls || 'pet-btn__icon') + '" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" ' +
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

    function reducedMotion() {
        if (window.PetRig && typeof window.PetRig.reducedMotion === 'function') return window.PetRig.reducedMotion();
        return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

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

    function findPet(id, state) {
        var pets = ((state || PetsState.current || {}).pets) || [];
        for (var i = 0; i < pets.length; i++) if (pets[i].id === id) return pets[i];
        return null;
    }

    // ------------------------------------------------------------------------------------
    // Żądania z kolejnością: starsza odpowiedź nie nadpisze nowszego stanu
    // ------------------------------------------------------------------------------------

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
     * Jeden punkt obsługi błędów API:
     * 409 (np. `not_available` po podwójnym kliknięciu, `in_hospital`) → bez toastu, tylko odświeżenie stanu;
     * 410 `pet_gone` → toast z komunikatem + odświeżenie;
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

    function track(name, params) {
        if (typeof window.trackEvent !== 'function') return;
        try { window.trackEvent(name, params); } catch (e) { /* analityka nie może psuć gry */ }
    }

    /** GA4 (docs/GOOGLE_ANALYTICS.md): akcja, wariant, nastrój, krok — bez imion, identyfikatorów i treści. */
    function trackPetEvent(path, body, resp) {
        if (/\/akcja$/.test(path) && body && body.action) {
            var pet = findPet(parseInt(path.split('/')[1], 10), resp.state);
            var params = { action: body.action, mood: pet ? pet.mood : 'unknown' };
            if (resp.variant || body.variant) params.variant = resp.variant || body.variant;
            track('pet_action', params);
        } else if (/\/wykluj$/.test(path) && resp.result) {
            track('pet_hatch', { result: resp.result });
        } else if (/\/szpital$/.test(path)) {
            track('pet_hospital', { step: 'admit' });
        } else if (/\/wypis$/.test(path)) {
            track('pet_hospital', { step: 'discharge' });
        }
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
    // Pat pat — paczki (domek i łóżka szpitala): debounce 2 s, max 50 w paczce, keepalive.
    // Niewysłana paczka leci przy schowaniu karty, przy wyjściu ze strony i przy zmianie sceny.
    // `beforeunload` nasłuchuje tylko, gdy paczka czeka (na stałe psułby bfcache w Firefoksie);
    // `pagehide` jako siatka (mobilne / bfcache).
    // ------------------------------------------------------------------------------------

    var patPending = {}, patTimers = {}, leaveArmed = false;

    function flushPat(id) {
        clearTimeout(patTimers[id]);
        delete patTimers[id];
        var n = patPending[id];
        if (!n) return false;
        delete patPending[id];
        send('/' + id + '/akcja', { action: 'pat', count: n }, { keepalive: true }).catch(function () { /* obsłużone */ });
        disarmLeave();
        return true;
    }

    function flushAllPats() {
        var sent = false;
        Object.keys(patPending).forEach(function (id) { if (flushPat(id)) sent = true; });
        disarmLeave();
        return sent;
    }

    // Wyjście ze strony: odpowiedź może już nie wrócić, więc cache stanu przestaje być wiarygodny
    function flushOnLeave() {
        if (flushAllPats() && typeof PetsState.invalidate === 'function') PetsState.invalidate();
    }

    function armLeave() {
        if (leaveArmed) return;
        leaveArmed = true;
        window.addEventListener('beforeunload', flushOnLeave);
    }

    function disarmLeave() {
        if (!leaveArmed || Object.keys(patPending).length) return;
        leaveArmed = false;
        window.removeEventListener('beforeunload', flushOnLeave);
    }

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') flushAllPats();
    });
    window.addEventListener('pagehide', flushOnLeave);

    /** Klepnięcie pupila: true, gdy przyjęte (pupil żyje i może być głaskany) — animację robi wołający. */
    function pat(petId) {
        var pet = findPet(petId);
        if (!pet || !(pet.can && pet.can.pat)) return false;
        if (window.Haptics) window.Haptics.tap();
        patPending[petId] = (patPending[petId] || 0) + 1;
        armLeave();
        clearTimeout(patTimers[petId]);
        if (patPending[petId] >= PAT_MAX) flushPat(petId);
        else patTimers[petId] = setTimeout(function () { flushPat(petId); }, PAT_DEBOUNCE_MS);
        return true;
    }

    // ------------------------------------------------------------------------------------
    // Router scen
    // ------------------------------------------------------------------------------------

    var base = (PetsApi.base || '/client/pupile/api').replace(/\/api\/?$/, '') || '/client/pupile';
    var header = {
        bar: root.querySelector('[data-scene-bar]'),
        back: root.querySelector('[data-scene-back]'),
        backLabel: root.querySelector('[data-scene-back-label]'),
        title: root.querySelector('[data-scene-title]'),
        night: root.querySelector('[data-pets-night]')
    };
    var instances = {};
    var current = { name: null, params: {} };
    var navigating = false;
    var baseTitle = document.title;

    function hostOf(name) {
        return SCENE_ORDER.indexOf(name) >= 0 ? root.querySelector('[data-scene-view="' + name + '"]') : null;
    }

    function href(name, params) {
        var url = base + (SCENE_PATH[name] || '');
        var query = [];
        QUERY_PARAMS.forEach(function (key) {
            if (params && params[key] != null) query.push(key + '=' + encodeURIComponent(params[key]));
        });
        return query.length ? url + '?' + query.join('&') : url;
    }

    /** Adres → {name, params}; ścieżka spoza znanych = mapa, parametr spoza liczb dodatnich = brak parametru. */
    function parseLocation() {
        var path = location.pathname.replace(/\/+$/, '');
        var name = 'mapa';
        if (path.indexOf(base) === 0) {
            var rest = path.slice(base.length);
            SCENE_ORDER.forEach(function (key) { if (SCENE_PATH[key] === rest) name = key; });
        }
        var params = {};
        try {
            var search = new URLSearchParams(location.search);
            QUERY_PARAMS.forEach(function (key) {
                var raw = search.get(key);
                var id = /^\d+$/.test(raw || '') ? parseInt(raw, 10) : 0;
                if (id > 0) params[key] = id;
            });
        } catch (e) { /* stare przeglądarki — bez parametrów */ }
        return { name: name, params: params };
    }

    /**
     * Zgodność wstecz (spec v3.1 §4.1): stare `/szpital?pupil=ID` (wysłane pushe, stare karty) to dziś
     * Izba przyjęć — adres podmieniany przez replaceState, bez nowego wpisu historii.
     */
    function canonical(loc) {
        if (loc.name === 'szpital' && loc.params.pupil) {
            loc = { name: 'izba', params: { pupil: loc.params.pupil } };
            try { history.replaceState({ petsScene: loc.name }, '', href(loc.name, loc.params)); } catch (e) { /* bez historii */ }
        }
        return loc;
    }

    function instance(name) {
        if (instances[name]) return instances[name];
        var def = SCENES[name];
        var host = hostOf(name);
        if (!def || !host) return null;
        instances[name] = { def: def, host: host, scene: def.create(ctx, host) };
        return instances[name];
    }

    function titleOf(name) {
        var def = SCENES[name];
        return (def && def.title) || SCENE_TITLE[name] || SCENE_TITLE.mapa;
    }

    /** Pigułka: link powrotu do rodzica (poziom 1 → mapa „Świat”, sale → hol „Szpital”) + nazwa miejsca (h1). */
    function updateHeader(name) {
        var parent = SCENE_PARENT[name] || null;
        if (header.back) {
            header.back.hidden = !parent;
            if (parent) {
                header.back.href = href(parent);
                header.back.setAttribute('data-scene-link', parent);
                if (header.backLabel) header.backLabel.textContent = PARENT_LABEL[parent] || titleOf(parent);
                header.back.setAttribute('aria-label', 'Wróć: ' + (PARENT_LABEL[parent] || titleOf(parent)));
            }
        }
        if (header.title) header.title.textContent = titleOf(name);
        root.setAttribute('data-scene', name);
        document.title = name === 'mapa' ? baseTitle : titleOf(name) + ' · ' + baseTitle;
    }

    function show(name, params, opts) {
        opts = opts || {};
        // Znany klucz bez modułu sceny (np. sale szpitala przed ich paczką) = pusta scena, nie mapa
        if (!hostOf(name)) name = 'mapa';
        params = params || {};
        if (current.name === name) {
            current.params = params;
            var same = instances[name];
            if (same && same.scene.setParams) same.scene.setParams(params);
            return;
        }
        flushAllPats();
        var prevName = current.name;
        var prev = prevName ? instances[prevName] : null;
        // Najpierw nowa scena jako bieżąca: leave() starej nie może już ruszać adresu (setQuery)
        current = { name: name, params: params };
        if (prev && prev.scene.leave) prev.scene.leave();
        var prevHost = prevName ? hostOf(prevName) : null;
        if (prevHost) {
            prevHost.hidden = true;
            prevHost.classList.remove('is-entering');
        }
        var host = hostOf(name);
        var inst = instance(name);
        updateHeader(name);
        host.hidden = false;
        if (!reducedMotion() && opts.animate !== false) {
            host.classList.remove('is-entering');
            void host.offsetWidth;
            host.classList.add('is-entering');
        }
        if (opts.scroll !== false) window.scrollTo(0, 0);
        if (!inst) {
            if (opts.focus && header.title) focusTitle();
            return;
        }
        inst.scene.enter(params);
        // enter/render mogą same przekierować na inną scenę (np. pupil w szpitalu) — wtedy koniec
        if (current.name !== name) return;
        if (PetsState.current) inst.scene.render(PetsState.current);
        if (current.name !== name) return;
        // Fokus na nagłówek sceny — chyba że scena sama go już ustawiła (np. otwarte okno pupila)
        if (opts.focus && header.title && !inst.host.contains(document.activeElement)) focusTitle();
    }

    function focusTitle() {
        try { header.title.focus({ preventScroll: true }); } catch (e) { header.title.focus(); }
    }

    /** Przejście do sceny: pushState (albo replaceState) + przełączenie; z mapy krótki zoom w stronę miejsca. */
    function go(name, params, opts) {
        opts = opts || {};
        if (navigating) return;
        var url = href(name, params);
        var commit = function () {
            navigating = false;
            var st = { petsScene: name };
            if (opts.replace) history.replaceState(st, '', url);
            else history.pushState(st, '', url);
            show(name, params || {}, { focus: true });
        };
        var map = instances.mapa;
        if (current.name === 'mapa' && name !== 'mapa' && map && map.scene.zoomTo && !reducedMotion()) {
            navigating = true;
            map.scene.zoomTo(name);
            setTimeout(commit, ZOOM_MS);
        } else {
            commit();
        }
    }

    /** Zmiana parametrów bieżącej sceny bez nowego wpisu historii (np. otwarty panel pupila). */
    function setQuery(params) {
        var url = href(current.name, params);
        current.params = params || {};
        if (location.pathname + location.search !== url) history.replaceState({ petsScene: current.name }, '', url);
    }

    root.addEventListener('click', function (e) {
        var link = e.target.closest('a[data-scene-link]');
        if (!link || !root.contains(link) || e.defaultPrevented) return;
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        var params = {};
        QUERY_PARAMS.forEach(function (key) {
            var id = parseInt(link.dataset[key], 10);
            if (id > 0) params[key] = id;
        });
        go(link.dataset.sceneLink, params);
    });

    window.addEventListener('popstate', function () {
        var loc = canonical(parseLocation());
        show(loc.name, loc.params, { focus: true, scroll: false });
    });

    // ------------------------------------------------------------------------------------
    // Kontekst dla scen
    // ------------------------------------------------------------------------------------

    var ctx = {
        root: root,
        base: base,
        u: {
            el: el, escapeHtml: escapeHtml, toast: toast, setBusy: setBusy, button: button, icon: icon,
            plural: plural, formatDuration: formatDuration, roughDuration: roughDuration, formatDate: formatDate,
            daysText: daysText, parseLocal: parseLocal, secondsUntil: secondsUntil, serverNow: serverNow, plParts: plParts,
            speciesName: speciesName, reducedMotion: reducedMotion
        },
        species: speciesInfo,
        state: function () { return PetsState.current; },
        findPet: findPet,
        send: send,
        refresh: refresh,
        handleError: handleError,
        showAchievements: showAchievements,
        track: track,
        pat: pat,
        flushPats: flushAllPats,
        go: go,
        href: href,
        setQuery: setQuery,
        params: function () { return current.params; },
        isActive: function (name) { return current.name === name; }
    };

    // ------------------------------------------------------------------------------------
    // Pigułka nocy (spec v3.1 §3.3): krótko „Noc — pupile śpią do 7:00”, szczegóły w podpowiedzi
    // ------------------------------------------------------------------------------------

    function renderNight(state) {
        if (!header.night) return;
        var night = state.night || {};
        header.night.hidden = !night.is_night;
        // Pigułka nocy zajmuje miejsce u góry sceny — sceny zsuwają w dół podpowiedzi i tabliczki (CSS)
        root.classList.toggle('pets-page--night', !!night.is_night);
        if (night.is_night) {
            var factor = state.config && state.config.night_factor;
            var slower = factor > 0 && factor < 1 ? Math.round(1 / factor) + '× wolniej' : 'wolniej';
            var text = 'Noc — pupile śpią do ' + night.end + ':00';
            var more = 'Noc trwa od ' + night.start + ':00 do ' + night.end + ':00 — pupile śpią, a ich potrzeby rosną ' +
                slower + '. Głodny albo chory pupil nie zaśnie, dopóki się nim nie zajmiesz.';
            // role="status": każde przypisanie (co odświeżenie stanu) czytnik ogłosiłby od nowa
            if (header.night.textContent !== text) header.night.textContent = text;
            if (header.night.title !== more) header.night.title = more;
        }
    }

    // ------------------------------------------------------------------------------------
    // Render, zegar, odświeżanie
    // ------------------------------------------------------------------------------------

    function render(state) {
        var t = parseLocal(state.now);
        if (!isNaN(t)) clockOffset = t - Date.now();
        renderNight(state);
        var inst = current.name && instances[current.name];
        if (inst) inst.scene.render(state);
        scheduleEventRefresh(state);
    }

    // Odświeżenie dokładnie wtedy, gdy coś się zmienia z czasu (koniec ogrzewania, wyzdrowienie, auto-wypis,
    // okno obudzenia, miesięczne jajko) — interwał 5 min łapie resztę (np. pasek spada poniżej 80).
    var eventTimer = 0;
    function scheduleEventRefresh(state) {
        clearTimeout(eventTimer);
        var times = [];
        (state.eggs || []).forEach(function (egg) { if (egg.boost_until) times.push(egg.boost_until); });
        (state.pets || []).forEach(function (pet) {
            if (pet.awake_until) times.push(pet.awake_until);
            if (pet.hospital) {
                if (!pet.hospital.ready) times.push(pet.hospital.healed_at);
                times.push(pet.hospital.auto_discharge_at);
            }
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
        var inst = current.name && instances[current.name];
        if (inst && inst.scene.tick && PetsState.current) inst.scene.tick();
    }, 1000);

    setInterval(function () {
        if (document.visibilityState === 'hidden') return;
        refresh();
    }, REFRESH_EVERY_MS);

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible' && Date.now() - lastRefreshAt > 60 * 1000) refresh();
    });

    // ------------------------------------------------------------------------------------
    // Start
    // ------------------------------------------------------------------------------------

    var initial = safeParse(root.dataset.state);
    lastRefreshAt = Date.now();
    if (initial) PetsState.set(initial);
    else refresh();

    var start = parseLocation();
    var serverScene = root.dataset.scene;
    if (SCENE_ORDER.indexOf(serverScene) >= 0 && serverScene !== start.name) start.name = serverScene;
    try { history.replaceState({ petsScene: start.name }, '', location.href); } catch (e) { /* bez historii */ }
    start = canonical(start);
    show(start.name, start.params, { animate: false, scroll: false });
})();
