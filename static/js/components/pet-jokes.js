/**
 * Żarty towarzysza (spec v3.2 §5) — rzadkie niespodzianki pupila w panelu klienta.
 *
 * Wymaga: window.PetCompanionApi (pet-companion.js, tylko tryb walk), window.PetsState/PetsApi (pets-core.js).
 * Żartów nie wymieniamy w żadnym ekranie użytkownika (element zaskoczenia): jeden przełącznik w warsztacie
 * wyłącza wszystkie (state.companion.jokes); lista żartów żyje tylko tu i w specu.
 *
 * Harmonogram: pierwszy żart najwcześniej 90 s po wejściu, potem co 2–5 min; czas „następnego” w sessionStorage,
 * więc przechodzenie między stronami go nie zeruje. Jeden żart naraz, zawsze na „zajętym” towarzyszu
 * (PetCompanionApi.claim) — chwycenie/sen/ukrycie przerywa żart i sprząta po nim.
 *
 * window.PetJokes: trigger(name, opts) -> Promise<boolean> ('peek' | 'cursor'; opts.edge tylko do testów),
 * active() -> nazwa trwającego żartu albo null, cancel().
 */
(function () {
    'use strict';

    // Towarzysz rejestruje API dopiero w boot() (po DOMContentLoaded), a ten plik wykonuje się w trakcie
    // parsowania strony — start dopiero, gdy API istnieje (zdarzenie pets:companion-api).
    if (window.PetCompanionApi) start();
    else document.addEventListener('pets:companion-api', start, { once: true });

    function start() {
        var host = document.getElementById('petCompanion');
        var api = window.PetCompanionApi;
        if (!host || !api || !window.PetsState || !window.PetsApi || window.PetJokes) return;

        var userId = host.getAttribute('data-user-id');
        var html = document.documentElement;

        var FIRST_MS = 90 * 1000;                        // pierwszy żart najwcześniej po 90 s od wejścia
        var GAP_MIN = 120 * 1000, GAP_MAX = 300 * 1000;  // kolejne co 2–5 min
        var RETRY_MS = 30 * 1000;                        // brak warunków / brak żartu do wyboru — próba za 30 s
        var CHECK_MS = 5000;                             // jak często harmonogram sprawdza, czy czas na żart
        var W_PEEK = 0.7;                                // waga wychylenia (kursor dostaje resztę)
        var PEEK_SHOW_MS = 6000;
        var CLOSED_TTL_MS = 7 * 24 * 3600 * 1000;        // „x”: obrazek nie wraca przez 7 dni
        var LIST_TTL_MS = 5 * 60 * 1000;
        var BLOCKERS = '.modal-overlay.active, .modal-centered.show, .pwa-bottom-sheet.open, .cart-sidebar.mobile-open, ' +
            '.cart-mobile-overlay.active, [role="dialog"][aria-modal="true"], ' +
            '.tour-fullscreen-overlay, .shepherd-modal-is-visible, .shepherd-element';   // wycieczka onboardingowa
        var SHOP_BARS = '.checkout-bottom-bar, .product-sticky-bar, .floating-actions, .cart-sidebar .cart-footer';
        var TEXT_FIELDS = 'input, textarea, select, [contenteditable=""], [contenteditable="true"]';
        var NO_CURSOR = 'pet-jokes--no-cursor';

        var nextKey = 'pets_jokes_next_' + userId;
        var lastPeekKey = 'pets_jokes_lastpeek_' + userId;
        var listKey = 'pets_jokes_list_' + userId;
        var closedPrefix = 'pets_peek_closed_';

        var current = null;                              // trwający żart {name, cancel}
        var listPromise = null, listAt = 0;

        // --- pomocnicze -----------------------------------------------------------------------------

        function rand(min, max) { return min + Math.random() * (max - min); }

        function ssGet(key) { try { return sessionStorage.getItem(key); } catch (e) { return null; } }
        function ssSet(key, v) { try { sessionStorage.setItem(key, v); } catch (e) { /* prywatne okno */ } }
        function lsGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
        function lsSet(key, v) { try { localStorage.setItem(key, v); } catch (e) { /* prywatne okno */ } }

        function reduced() {
            return !!(window.PetRig && window.PetRig.reducedMotion && window.PetRig.reducedMotion());
        }

        function anyShown(selector) {
            var nodes = document.querySelectorAll(selector);
            for (var i = 0; i < nodes.length; i++) if (nodes[i].getClientRects().length > 0) return true;
            return false;
        }

        function vw() { return document.documentElement.clientWidth || window.innerWidth; }

        function jokesFlag() {
            var s = window.PetsState.current;
            return !!(s && s.companion && s.companion.jokes === true);
        }

        /** Pełnoekranowa nakładka nieznanego rodzaju (fixed, pokrywa okno, widoczna, łapie kliknięcia) też blokuje żart. */
        function fullscreenOverlay() {
            var nodes = document.querySelectorAll('[class*="overlay"], [class*="backdrop"], [class*="modal"]');
            var w = window.innerWidth, h = window.innerHeight;
            for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                if (n.getClientRects().length === 0) continue;
                var cs = window.getComputedStyle(n);
                if (cs.position !== 'fixed' || cs.visibility === 'hidden' || cs.pointerEvents === 'none' ||
                    parseFloat(cs.opacity) < 0.05) continue;
                var r = n.getBoundingClientRect();
                // pokrywa okno (nakładki poza ekranem, np. translateX(100%), się nie liczą)
                if (r.left <= w * 0.1 && r.top <= h * 0.1 && r.right >= w * 0.9 && r.bottom >= h * 0.9) return true;
            }
            return false;
        }

        function blocked() {
            if (anyShown(BLOCKERS) || anyShown(SHOP_BARS) || fullscreenOverlay()) return true;
            if (document.body && document.body.style.overflow === 'hidden') return true;   // scroll-lock = otwarta nakładka
            var a = document.activeElement;
            return !!(a && a !== document.body && a.matches && a.matches(TEXT_FIELDS));
        }

        function canStart() {
            return !current && jokesFlag() && !reduced() && document.visibilityState === 'visible' && api.ready() && !blocked();
        }

        // --- harmonogram ----------------------------------------------------------------------------

        function dueAt() {
            var raw = parseInt(ssGet(nextKey), 10);
            if (!raw) {
                raw = Date.now() + FIRST_MS;
                ssSet(nextKey, String(raw));
            }
            return raw;
        }

        function scheduleNext(ms) {
            ssSet(nextKey, String(Date.now() + (ms != null ? ms : rand(GAP_MIN, GAP_MAX))));
        }

        function tick() {
            setTimeout(tick, CHECK_MS);
            if (Date.now() < dueAt() || !canStart()) return;
            scheduleNext(RETRY_MS);          // chroni przed podwójnym startem na czas decyzji; po żarcie nadpisze odstęp
            decide(null, {});
        }

        /** Wybiera i uruchamia żart. forced = 'peek' | 'cursor' | null. Zwraca Promise<boolean> (czy ruszył). */
        function decide(forced, opts) {
            return loadImages().then(function (list) {
                if (!canStart()) return false;                   // sytuacja zmieniła się w trakcie pobierania listy
                var imgs = candidates(list);
                var peekOk = imgs.length > 0;
                var cursorOk = cursorAvailable();
                var kind = null;
                if (forced === 'peek') kind = peekOk ? 'peek' : null;
                else if (forced === 'cursor') kind = cursorOk ? 'cursor' : null;
                else if (peekOk && cursorOk) kind = Math.random() < W_PEEK ? 'peek' : 'cursor';
                else kind = peekOk ? 'peek' : (cursorOk ? 'cursor' : null);
                if (!kind) return false;
                return kind === 'peek' ? startPeek(imgs, opts || {}) : startCursor();
            });
        }

        // --- lista obrazków -------------------------------------------------------------------------

        function loadImages() {
            if (listPromise && Date.now() - listAt < LIST_TTL_MS) return listPromise;
            var cached = null;
            try { cached = JSON.parse(ssGet(listKey) || 'null'); } catch (e) { cached = null; }
            if (cached && Array.isArray(cached.images) && Date.now() - cached.t < LIST_TTL_MS) {
                listAt = cached.t;
                listPromise = Promise.resolve(cached.images);
                return listPromise;
            }
            listAt = Date.now();
            listPromise = window.PetsApi.get('/wychylenia').then(function (res) {
                var images = (res && Array.isArray(res.images)) ? res.images : [];
                ssSet(listKey, JSON.stringify({ t: Date.now(), images: images }));
                return images;
            }, function () { return []; });
            return listPromise;
        }

        function isClosed(id) {
            var t = parseInt(lsGet(closedPrefix + id), 10);
            return !!t && Date.now() - t < CLOSED_TTL_MS;
        }

        function candidates(list) {
            return list.filter(function (i) {
                return i && i.id != null && typeof i.url === 'string' && i.url.indexOf('/static/') === 0 && !isClosed(i.id);
            });
        }

        function pickImage(list) {
            var last = ssGet(lastPeekKey);
            var rest = list.filter(function (i) { return String(i.id) !== last; });
            var pool = rest.length ? rest : list;
            return pool[Math.floor(Math.random() * pool.length)];
        }

        // --- żart: wychylenie z obrazkiem -----------------------------------------------------------

        /** Cel wychylenia (lewy górny róg pupila): lewa — pod sidebar, prawa/dolna — poza okno. */
        function peekGeometry(forcedEdge) {
            var r = api.rect();
            var w = vw(), h = window.innerHeight;
            var wrap = document.querySelector('.main-wrapper');
            var wl = wrap ? Math.max(0, wrap.getBoundingClientRect().left) : 0;
            var edges = ['right', 'bottom'];
            if (wl >= 40) edges.push('left');                    // sidebar widoczny — wychylenie spod niego
            var edge = edges.indexOf(forcedEdge) >= 0 ? forcedEdge : edges[Math.floor(Math.random() * edges.length)];
            var minY = 96, maxY = Math.max(minY, h - r.h - 96);
            var y = Math.round(rand(minY, maxY));
            if (edge === 'left') {
                return { edge: edge, face: 'right', place: 'right', x: Math.round(wl - r.w * 0.4), y: y, back: { x: wl + 140, y: y } };
            }
            if (edge === 'right') {
                return { edge: edge, face: 'left', place: 'left', x: Math.round(w - r.w * 0.6), y: y, back: { x: w - 220, y: y } };
            }
            var bx = Math.round(rand(wl + 60, Math.max(wl + 61, w - r.w - 60)));
            return { edge: edge, face: Math.random() < 0.5 ? 'left' : 'right', place: 'up', x: bx, y: Math.round(h - r.h * 0.65),
                back: { x: bx, y: h - 240 } };
        }

        function buildPeek(image, place) {
            var box = document.createElement('div');
            box.className = 'pet-jokes__peek pet-jokes__peek--' + place;
            var pic = document.createElement('img');
            pic.className = 'pet-jokes__img';
            pic.alt = '';
            pic.draggable = false;
            pic.src = image.url;
            var close = document.createElement('button');
            close.type = 'button';
            close.className = 'pet-jokes__close';
            close.setAttribute('aria-label', 'Zamknij obrazek');
            box.appendChild(pic);
            box.appendChild(close);
            host.appendChild(box);
            return box;
        }

        function startPeek(imgs, opts) {
            var image = pickImage(imgs);
            var geo = peekGeometry(opts.edge);
            var box = null, ended = false, hideTimer = 0, onKey = null, release = null;
            var job = { name: 'peek', cancel: function () { stop(); } };

            function removeBox() {
                if (box && box.parentNode) box.parentNode.removeChild(box);
                box = null;
            }

            function unlistenKey() {
                if (onKey) document.removeEventListener('keydown', onKey, true);
                onKey = null;
            }

            // Idempotentne sprzątanie po żarcie: wołane po spokojnym wyjściu i po każdym przerwaniu
            function stop() {
                if (ended) return;
                ended = true;
                clearTimeout(hideTimer);
                unlistenKey();
                removeBox();
                if (current === job) { current = null; scheduleNext(); }
                if (release) release();
            }

            // Spokojne wyjście: chowa obrazek, wraca w głąb ekranu, dopiero potem oddaje towarzysza
            function leave() {
                if (ended) return;
                clearTimeout(hideTimer);
                unlistenKey();
                removeBox();
                api.runTo(geo.back.x, geo.back.y).then(function () { stop(); });
            }

            function close() {
                lsSet(closedPrefix + image.id, String(Date.now()));
                leave();
            }

            function tryHide() {
                hideTimer = 0;
                if (ended) return;
                if (box && (box.matches(':hover') || box.contains(document.activeElement))) {
                    hideTimer = setTimeout(tryHide, 500);        // fokus/kursor nad obrazkiem — nie znikamy spod ręki
                    return;
                }
                leave();
            }

            release = api.claim(function () { stop(); });        // onBreak: chwycenie, sen, ukrycie
            if (!release) return false;
            current = job;
            ssSet(lastPeekKey, String(image.id));

            api.runTo(geo.x, geo.y, { allowOutside: true, face: geo.face }).then(function (ok) {
                if (!ok || ended) return;                        // przerwane — onBreak już posprzątał
                box = buildPeek(image, geo.place);
                box.querySelector('.pet-jokes__close').addEventListener('click', close);
                onKey = function (e) {
                    if (e.key === 'Escape') { e.stopPropagation(); close(); }
                };
                document.addEventListener('keydown', onKey, true);
                hideTimer = setTimeout(tryHide, PEEK_SHOW_MS);
            });
            return true;
        }

        // --- kradzież kursora (Zadanie 8 zastępuje ten blok) ----------------------------------------
        var mouse = null;
        function cursorAvailable() { return false; }
        function startCursor() { return false; }
        // --- koniec bloku kursora --------------------------------------------------------------------

        // --- start ----------------------------------------------------------------------------------

        function trigger(name, opts) {
            if (name !== 'peek' && name !== 'cursor') return Promise.resolve(false);
            return decide(name, opts || {});
        }

        function cancel() { if (current) current.cancel(); }

        window.PetJokes = {
            trigger: trigger,
            active: function () { return current ? current.name : null; },
            cancel: cancel
        };

        // Wyłączenie żartów (przełącznik/admin) kończy trwający od razu
        window.PetsState.onChange(function () {
            if (current && !jokesFlag()) current.cancel();
        });
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'hidden') cancel();
        });

        setTimeout(tick, CHECK_MS);
    }
})();
