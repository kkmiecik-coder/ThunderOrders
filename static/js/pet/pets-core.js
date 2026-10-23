/**
 * Pupile — wspólna warstwa dla domku, widgetu na dashboardzie i towarzysza (spec §4.3–4.4).
 *
 *  window.PetsApi   — fetch do /client/pupile/api z CSRF; każdy błąd (HTTP, nie-JSON, przekierowanie
 *                     do logowania) to odrzucenie z {error, message, status}.
 *  window.PetsState — bieżący stan + nasłuch, cache w localStorage per użytkownik (klucz z user_id,
 *                     TTL 5 min liczony od odpowiedzi SERWERA: set() zapisuje, ale odczyt z cache
 *                     idzie przez set(s, {persist: false}) i nie przesuwa znacznika czasu; każda
 *                     niepewność invalidate()), kropki „pupil potrzebuje opieki" w nawigacji,
 *                     zdarzenie document:'pets:state'; PetsState.eggForecast(egg, state, elapsedSec) —
 *                     prognoza wyklucia (widget + inkubatornia).
 *
 * Plik ładuje się na kilku stronach (także dwa razy na dashboardzie: include towarzysza + skrypty
 * widgetu) — stąd guard idempotencji na początku.
 */
(function () {
    'use strict';
    if (window.PetsApi && window.PetsState) return;

    var DEFAULT_BASE = '/client/pupile/api';
    var CACHE_PREFIX = 'pets_state_v1_';
    var CACHE_TTL_MS = 5 * 60 * 1000;

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    // Tylko kontenery pupili — na stronie mogą być inne [data-api] / [data-user-id] (np. listy w panelu)
    var HOSTS = ['#petsApp', '#petsWidget', '#petCompanion'];

    function hostWith(attr) {
        return document.querySelector(HOSTS.map(function (h) { return h + '[' + attr + ']'; }).join(', '));
    }

    function apiBase() {
        var el = hostWith('data-api');
        return (el && el.getAttribute('data-api')) || DEFAULT_BASE;
    }

    function blad(error, message, status) {
        return { error: error, message: message, status: status };
    }

    var GENERIC_ERROR = 'Coś poszło nie tak, spróbuj za chwilę.';

    function parse(r) {
        // login_required robi 302 na /auth/login — fetch idzie za przekierowaniem i dostaje HTML
        if (r.redirected || r.status === 401 || /\/auth\/login/.test(r.url || '')) {
            throw blad('session_expired', 'Sesja wygasła — zaloguj się ponownie.', r.status);
        }
        var type = r.headers.get('Content-Type') || '';
        if (type.indexOf('application/json') === -1) {
            if (r.status === 429) throw blad('rate_limited', 'Za dużo żądań — odczekaj chwilę.', 429);
            throw blad('bad_response', GENERIC_ERROR, r.status);
        }
        return r.json().then(function (data) {
            if (!r.ok || !data || data.ok === false) {
                throw blad((data && data.error) || ('http_' + r.status), (data && data.message) || GENERIC_ERROR, r.status);
            }
            return data;
        }, function () {
            throw blad('bad_response', GENERIC_ERROR, r.status);
        });
    }

    function request(method, path, body, opts) {
        var init = {
            method: method,
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
        };
        if (method !== 'GET') {
            init.headers['Content-Type'] = 'application/json';
            init.headers['X-CSRFToken'] = csrfToken();
            init.body = JSON.stringify(body || {});
            init.keepalive = !!(opts && opts.keepalive);   // paczka pat pat może lecieć przy zamykaniu karty
        }
        return fetch(apiBase() + path, init).then(parse, function () {
            throw blad('network', 'Brak połączenia — spróbuj za chwilę.', 0);
        });
    }

    var PetsApi = {
        get base() { return apiBase(); },
        get: function (path) { return request('GET', path); },
        /** post(path, body[, {keepalive}]) */
        post: function (path, body, opts) { return request('POST', path, body, opts); }
    };

    // --- stan ---

    var listeners = [];

    function cacheKey(userId) { return CACHE_PREFIX + String(userId); }

    function detectUserId() {
        var el = hostWith('data-user-id');
        return el ? el.getAttribute('data-user-id') : null;
    }

    /** Rekord {t, s} z cache, jeśli świeży (t = chwila odpowiedzi serwera, nie odczytu). */
    function loadRecord(userId) {
        try {
            var raw = localStorage.getItem(cacheKey(userId));
            if (!raw) return null;
            var rec = JSON.parse(raw);
            if (!rec || typeof rec.t !== 'number' || !rec.s || Date.now() - rec.t > CACHE_TTL_MS) return null;
            return rec;
        } catch (e) { return null; }
    }

    function load(userId) {
        var rec = loadRecord(userId);
        return rec ? rec.s : null;
    }

    function save(userId, state) {
        if (userId == null || !state) return;
        try { localStorage.setItem(cacheKey(userId), JSON.stringify({ t: Date.now(), s: state })); } catch (e) { /* prywatne okno / limit */ }
    }

    function invalidate(userId) {
        try { localStorage.removeItem(cacheKey(userId == null ? PetsState.userId : userId)); } catch (e) { /* ignoruj */ }
    }

    function setNavDots(state) {
        var needs = !!(state && state.needs_care);
        var dot = document.getElementById('petsNavDot');
        if (dot) dot.hidden = !needs;
        var sheetDots = document.querySelectorAll('#pwaSheetPetsDot');
        for (var i = 0; i < sheetDots.length; i++) sheetDots[i].style.display = needs ? '' : 'none';
        // Arkusz „więcej" dolnego paska jest klonowany z <template> przy każdym otwarciu — ustaw też wzorzec
        var tpl = document.getElementById('pwaSheetClientMore');
        if (tpl && tpl.content) {
            var inTpl = tpl.content.querySelector('#pwaSheetPetsDot');
            if (inTpl) inTpl.style.display = needs ? '' : 'none';
        }
    }

    function emit(state) {
        var ev;
        try {
            ev = new CustomEvent('pets:state', { detail: state });
        } catch (e) {
            ev = document.createEvent('CustomEvent');
            ev.initCustomEvent('pets:state', false, false, state);
        }
        document.dispatchEvent(ev);
    }

    // --- prognoza jajka (widget na dashboardzie + inkubatornia w szpitalu) ---

    var DEFAULT_BOOST = 2;   // spec §2.2: ogrzanie = tempo ×2 — tylko gdy stan nie niesie config

    /** Chwila z API w UTC ("2026-10-11T19:15:00Z") → ms; Date.parse honoruje `Z`/offset. */
    function parseLocal(iso) {
        return iso ? Date.parse(iso) : NaN;
    }

    /** Mnożnik ogrzania z config stanu (ten sam, którym liczy serwer). */
    function boostFactor(state) {
        var f = state && state.config && Number(state.config.boost_factor);
        return f > 0 ? f : DEFAULT_BOOST;
    }

    /**
     * Postęp i czas do wyklucia w chwili `elapsedSec` od odebrania stanu (spec §2.2: ogrzanie przyspiesza
     * tempo ×config.boost_factor do `boost_until`) → {pct, leftSec, boosted}.
     */
    function eggForecast(egg, state, elapsedSec) {
        var boost = boostFactor(state);
        var total = Math.max(1, (Number(egg.egg_hours) || 0) * 3600);
        var remaining = total * (1 - Math.min(100, Math.max(0, Number(egg.progress_pct) || 0)) / 100);
        var boostLeft = 0;
        if (egg.boost_until) {
            var b = (parseLocal(egg.boost_until) - parseLocal(state && state.now)) / 1000;
            if (b > 0) boostLeft = b;
        }
        // Czas ścienny do wyklucia od chwili odebrania stanu
        var wall = remaining <= boost * boostLeft
            ? remaining / boost
            : boostLeft + (remaining - boost * boostLeft);
        var e = Math.max(0, Number(elapsedSec) || 0);
        var gained = e <= boostLeft ? e * boost : boostLeft * boost + (e - boostLeft);
        return {
            pct: egg.ready ? 100 : Math.min(100, (total - remaining + gained) / total * 100),
            leftSec: egg.ready ? 0 : Math.max(0, wall - e),
            boosted: !egg.ready && boostLeft - e > 0
        };
    }

    var PetsState = {
        current: null,
        receivedAt: 0,
        userId: detectUserId(),
        /**
         * set(state[, {persist: false, receivedAt}]) — domyślnie zapisuje do cache z nowym znacznikiem
         * czasu (stan prosto od serwera). Stan odczytany z cache MUSI iść z persist: false — inaczej
         * każda nawigacja przedłużałaby TTL i strony bez widgetu nigdy nie pobrałyby świeżego stanu.
         */
        set: function (state, opts) {
            if (!state || typeof state !== 'object') return;
            var persist = !(opts && opts.persist === false);
            PetsState.current = state;
            PetsState.receivedAt = (opts && typeof opts.receivedAt === 'number') ? opts.receivedAt : Date.now();
            if (PetsState.userId == null) PetsState.userId = detectUserId();
            if (persist) save(PetsState.userId, state);
            setNavDots(state);
            for (var i = 0; i < listeners.length; i++) {
                try { listeners[i](state); } catch (e) { if (window.console) console.error(e); }
            }
            emit(state);
        },
        onChange: function (cb) {
            if (typeof cb === 'function') listeners.push(cb);
            return function () {
                var idx = listeners.indexOf(cb);
                if (idx !== -1) listeners.splice(idx, 1);
            };
        },
        needsCare: function () { return !!(PetsState.current && PetsState.current.needs_care); },
        /** Sekundy od odebrania bieżącego stanu (zegar przeglądarki). */
        elapsedSec: function () { return Math.max(0, (Date.now() - PetsState.receivedAt) / 1000); },
        eggForecast: eggForecast,
        boostFactor: boostFactor,
        load: load,
        save: save,
        invalidate: invalidate,
        setNavDots: setNavDots,
        /** Stan lite z cache (TTL 5 min) albo z sieci; `{force: true}` pomija cache. */
        fetchLite: function (userId, opts) {
            if (userId != null) PetsState.userId = userId;
            var rec = (opts && opts.force) ? null : loadRecord(PetsState.userId);
            if (rec) {
                PetsState.set(rec.s, { persist: false, receivedAt: rec.t });   // bez zapisu: TTL biegnie dalej
                return Promise.resolve(rec.s);
            }
            return PetsApi.get('/stan?lite=1').then(function (state) {
                PetsState.set(state);
                return state;
            });
        }
    };

    window.PetsApi = PetsApi;
    window.PetsState = PetsState;
})();
