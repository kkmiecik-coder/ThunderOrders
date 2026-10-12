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
        // Strony, na których klient składa zamówienie albo wysyła potwierdzenie płatności — żadnych żartów
        var NO_JOKE_PATHS = /^\/client\/(shop\/checkout|payment-confirmations)/;

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
            if (NO_JOKE_PATHS.test(window.location.pathname)) return true;   // składanie zamówienia / płatności
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
            var floor = api.floor ? api.floor(bx) : h;     // górna krawędź paska PWA albo dół okna: wychylamy się zza paska
            return { edge: edge, face: Math.random() < 0.5 ? 'left' : 'right', place: 'up', x: bx, y: Math.round(floor - r.h * 0.65),
                back: { x: bx, y: floor - 240 } };
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
                if (ended) return;
                if (!ok) { stop(); return; }                     // ruch przerwany (klik, chwyt…) — sprzątamy i oddajemy pupila
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

        // --- żart: kradzież kursora -----------------------------------------------------------------
        // Pupil dobiega do kursora, prawdziwy kursor znika (cursor:none), pupil ciąga narysowany kursor 2–3 s
        // i oddaje go. Klik w tym czasie nie dociera do strony. KAŻDA ścieżka końca idzie przez end() ->
        // sweepCursor(): kursor wraca zawsze.

        var CURSOR_GAP_MS = 10 * 60 * 1000, CURSOR_MAX = 2;   // najwyżej 2 razy na sesję karty, co 10 min
        var MOUSE_FRESH_MS = 3000;                            // mysz musiała się ruszyć w ciągu 3 s
        var CURSOR_HARD_MS = 3000;                            // twardy limit schowania kursora
        var GRAB_MS = 220, DROP_MS = 350;
        var cursorKey = 'pets_jokes_cursor_' + userId;
        var mouse = null;                                     // {x, y, t}

        function finePointer() {
            return !!(window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches);
        }

        /** Usuwa wszystko, co żart kursora dodał do strony (idempotentne, niezależne od domknięć). */
        function sweepCursor() {
            html.classList.remove(NO_CURSOR);
            var stray = document.querySelectorAll('.pet-jokes__shield, .pet-jokes__cursor');
            for (var i = 0; i < stray.length; i++) {
                if (stray[i].parentNode) stray[i].parentNode.removeChild(stray[i]);
            }
        }

        function onMouseMove(e) {
            mouse = { x: e.clientX, y: e.clientY, t: Date.now() };
            // pas i szelki: klasa została po jakimś błędzie, a żadnego żartu kursora już nie ma
            if (html.classList.contains(NO_CURSOR) && !(current && current.name === 'cursor')) sweepCursor();
        }

        if (finePointer()) {
            window.addEventListener('mousemove', onMouseMove, { passive: true });
            html.addEventListener('mouseleave', function () { mouse = null; });
        }

        function readCursorRec() {
            var rec = null;
            try { rec = JSON.parse(ssGet(cursorKey) || 'null'); } catch (e) { rec = null; }
            return rec && typeof rec === 'object' ? { n: rec.n | 0, last: +rec.last || 0 } : { n: 0, last: 0 };
        }

        function cursorAvailable() {
            if (!finePointer() || !mouse || Date.now() - mouse.t > MOUSE_FRESH_MS) return false;
            var rec = readCursorRec();
            if (rec.n >= CURSOR_MAX) return false;
            return !rec.last || Date.now() - rec.last >= CURSOR_GAP_MS;
        }

        function buildCursorSprite() {
            var wrap = document.createElement('div');
            wrap.className = 'pet-jokes__cursor';
            wrap.setAttribute('aria-hidden', 'true');
            wrap.innerHTML = '<svg viewBox="0 0 22 28" xmlns="http://www.w3.org/2000/svg"><path d="M1 1 L1 22 L6.5 17.2 L10.2 26 L13.4 24.6 L9.8 16 L17 16 Z"/></svg>';
            return wrap;
        }

        function startCursor() {
            var m = mouse;
            if (!m) return false;
            var r0 = api.rect();
            var done = false, engaged = false, raf = 0, hardTimer = 0, dropTimer = 0, shield = null, sprite = null, release = null;
            var job = { name: 'cursor', cancel: function () { end(); } };
            var capt = { capture: true, passive: false };

            function swallowNextClick() {
                function eat(e) { e.preventDefault(); e.stopPropagation(); }
                window.addEventListener('click', eat, { capture: true, once: true });
                setTimeout(function () { window.removeEventListener('click', eat, true); }, 400);
            }

            // Przed schwytaniem klik użytkownika działa normalnie (żart tylko się kończy); po schwytaniu jest połykany
            function onPointer(e) {
                if (engaged) {
                    e.preventDefault();
                    e.stopPropagation();
                    swallowNextClick();
                }
                end();
            }
            function onKey() { end(); }                          // klawisza nie połykamy (Tab dalej działa)
            function onHidden() { if (document.visibilityState === 'hidden') end(); }

            function listen() {
                window.addEventListener('keydown', onKey, capt);
                ['pointerdown', 'mousedown', 'touchstart'].forEach(function (t) { window.addEventListener(t, onPointer, capt); });
                window.addEventListener('blur', end);
                window.addEventListener('pagehide', end);
                document.addEventListener('visibilitychange', onHidden);
            }

            function unlisten() {
                window.removeEventListener('keydown', onKey, capt);
                ['pointerdown', 'mousedown', 'touchstart'].forEach(function (t) { window.removeEventListener(t, onPointer, capt); });
                window.removeEventListener('blur', end);
                window.removeEventListener('pagehide', end);
                document.removeEventListener('visibilitychange', onHidden);
            }

            // Idempotentne: WSZYSTKIE ścieżki końca kończą tutaj, a kursor wraca w finally
            function end() {
                if (done) return;
                done = true;
                try {
                    cancelAnimationFrame(raf);
                    clearTimeout(hardTimer);
                    clearTimeout(dropTimer);
                    unlisten();
                } finally {
                    sweepCursor();
                    if (current === job) { current = null; scheduleNext(); }
                    if (release) release();
                }
            }

            function engage() {
                engaged = true;
                var from = mouse || { x: r0.x, y: r0.y };
                html.classList.add(NO_CURSOR);
                shield = document.createElement('div');
                shield.className = 'pet-jokes__shield';
                sprite = buildCursorSprite();
                document.body.appendChild(shield);
                document.body.appendChild(sprite);
                hardTimer = setTimeout(end, CURSOR_HARD_MS);
                var t0 = Date.now();
                (function frame() {
                    if (done) return;
                    var r = api.rect();
                    var right = !host.classList.contains('pet-companion--flipped');
                    var px = r.x + r.w * (right ? 0.92 : 0.08), py = r.y + r.h * 0.72;
                    var k = Math.min(1, (Date.now() - t0) / GRAB_MS);
                    sprite.style.transform = 'translate(' + Math.round(from.x + (px - from.x) * k) + 'px,' +
                        Math.round(from.y + (py - from.y) * k) + 'px)';
                    raf = requestAnimationFrame(frame);
                })();
                // niesie kursor 150–250 px w stronę najbliższej krawędzi i upuszcza
                var r = api.rect();
                var dir = (r.x + r.w / 2) < vw() / 2 ? -1 : 1;
                if ((dir < 0 && r.x < 200) || (dir > 0 && r.x > vw() - 280)) dir = -dir;
                api.runTo(r.x + dir * rand(150, 250), r.y, { face: dir > 0 ? 'right' : 'left' }).then(function (ok) {
                    if (done) return;
                    if (!ok) { end(); return; }
                    sprite.classList.add('is-dropped');
                    dropTimer = setTimeout(end, DROP_MS);
                });
            }

            release = api.claim(function () { end(); });
            if (!release) return false;
            current = job;
            var rec = readCursorRec();
            ssSet(cursorKey, JSON.stringify({ n: rec.n + 1, last: Date.now() }));
            try {
                listen();
                // dobiega do punktu obok kursora (nie na sam kursor), potem schwytanie
                var side = m.x + 28 + r0.w < vw() ? 28 : -(28 + r0.w);
                api.runTo(m.x + side, m.y - r0.h / 2).then(function (ok) {
                    if (done) return;
                    if (!ok) { end(); return; }
                    if (!mouse) { end(); return; }                   // mysz opuściła okno w trakcie dobiegania
                    try { engage(); } catch (e) { end(); }
                });
            } catch (e) {
                end();
                return false;
            }
            return true;
        }
        // --- koniec żartu kursora -------------------------------------------------------------------

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
