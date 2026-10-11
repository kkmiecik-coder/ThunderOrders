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

    function handleResponse(r) {
        // login_required robi 302 na /auth/login — fetch idzie za przekierowaniem i dostaje HTML
        if (r.redirected || /\/auth\/login/.test(r.url || '')) {
            throw fail('session_expired', 'Sesja wygasła — zaloguj się ponownie.', r.status);
        }
        var type = r.headers.get('Content-Type') || '';
        if (type.indexOf('application/json') === -1) {
            if (r.status === 429) throw fail('rate_limited', 'Za dużo żądań — odczekaj chwilę.', 429);
            throw fail('bad_response', GENERIC_ERROR, r.status);
        }
        return r.json().then(function (data) {
            if (!r.ok || !data || data.ok === false) {
                throw fail((data && data.error) || ('http_' + r.status), data && data.message, r.status);
            }
            return data;
        }, function () {
            throw fail('bad_response', GENERIC_ERROR, r.status);
        });
    }

    function request(url, init) {
        return fetch(url, init).then(handleResponse, function () {
            throw fail('network', 'Brak połączenia — spróbuj za chwilę.', 0);
        });
    }

    var PetsApi = {
        base: function () {
            var root = document.getElementById('petsApp');
            return (root && root.dataset.api) || '/client/pupile/api';
        },
        get: function (path) {
            return request(PetsApi.base() + path, {
                credentials: 'same-origin',
                headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
            });
        },
        post: function (path, body, opts) {
            return request(PetsApi.base() + path, {
                method: 'POST',
                credentials: 'same-origin',
                keepalive: !!(opts && opts.keepalive),
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken()
                },
                body: JSON.stringify(body || {})
            });
        }
    };

    // ------------------------------------------------------------------------------------
    // PetsState — bieżący stan + subskrypcje + kropki w nawigacji
    // ------------------------------------------------------------------------------------

    function updateNavDots(on) {
        var dot = document.getElementById('petsNavDot');
        if (dot) dot.hidden = !on;
        var tpl = document.getElementById('pwaSheetClientMore');
        var inTpl = tpl && tpl.content ? tpl.content.querySelector('#pwaSheetPetsDot') : null;
        if (inTpl) inTpl.style.display = on ? '' : 'none';
        var live = document.getElementById('pwaSheetPetsDot');   // arkusz właśnie otwarty
        if (live) live.style.display = on ? '' : 'none';
    }

    var listeners = [];
    var PetsState = {
        current: null,
        receivedAt: 0,
        set: function (state) {
            if (!state || typeof state !== 'object') return;
            PetsState.current = state;
            PetsState.receivedAt = Date.now();
            updateNavDots(!!state.needs_care);
            listeners.slice().forEach(function (cb) {
                try { cb(state); } catch (e) { if (window.console) console.error('PetsState listener', e); }
            });
            var evt;
            try { evt = new CustomEvent('pets:state', { detail: state }); } catch (e) { evt = null; }
            if (evt) document.dispatchEvent(evt);
        },
        onChange: function (cb) {
            listeners.push(cb);
            return function () { listeners = listeners.filter(function (x) { return x !== cb; }); };
        },
        needsCare: function () {
            return !!(PetsState.current && PetsState.current.needs_care);
        }
    };

    window.PetsApi = PetsApi;
    window.PetsState = PetsState;

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

    var seq = 0, appliedSeq = 0, lastRefreshAt = 0, refreshing = null;

    function applyState(state, mySeq) {
        if (!state || mySeq < appliedSeq) return;
        appliedSeq = mySeq;
        PetsState.set(state);
    }

    function refresh() {
        if (refreshing) return refreshing;
        var mySeq = ++seq;
        lastRefreshAt = Date.now();
        refreshing = PetsApi.get('/stan').then(function (state) {
            applyState(state, mySeq);
        }, function (err) {
            // Odświeżenie w tle: bez toastu poza wygasłą sesją (i tak nic nie da się zrobić)
            if (err && err.error === 'session_expired') toast(err.message, 'warning');
        }).then(function () { refreshing = null; });
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

    /** POST z kolejnością stanu i wspólną obsługą błędów; `quiet` = kody obsługiwane przez wołającego. */
    function send(path, body, opts) {
        opts = opts || {};
        var mySeq = ++seq;
        return PetsApi.post(path, body, opts).then(function (resp) {
            applyState(resp.state, mySeq);
            if (resp.new_achievements && resp.new_achievements.length && !opts.deferAchievements) showAchievements();
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
            nightBanner.textContent = 'Jest noc (' + night.start + ':00–' + night.end + ':00) — pupile śpią, a ich ' +
                'potrzeby rosną 4× wolniej. Głodny albo chory pupil nie zaśnie, dopóki się nim nie zajmiesz.';
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
            entry.status.textContent = pct + '% · ogrzane, ciepło (tempo ×2) jeszcze ' + formatDuration(left > 0 ? left : 0);
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
    // Render, zegar, odświeżanie
    // ------------------------------------------------------------------------------------

    function render(state) {
        var t = parseLocal(state.now);
        if (!isNaN(t)) clockOffset = t - Date.now();
        renderNight(state);
        renderNest(state);
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
