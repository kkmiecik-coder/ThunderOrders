/**
 * Towarzysz — pupil na stronach panelu klienta i ofert (spec §4.4, plan etapu 5 Task 4).
 *
 * Szkielet: templates/components/pet_companion.html
 *   #petCompanion[hidden][data-user-id][data-api][data-home-url][data-mode="walk|sit"][data-celebrate="0|1"]
 *   #petCompanionHit (przycisk ≥ 44 px nad sceną) · #petCompanionScene (rig) · #petCompanionBubble (dymek)
 *
 * Wymaga: window.PetRig (pet-rig.js), window.PetsState/PetsApi (pets-core.js). window.Haptics opcjonalnie.
 *
 * Zasady:
 *  - SSR nie pyta bazy: stan lite z localStorage (pets-core, klucz z user_id) albo z sieci w wolnej chwili;
 *    na stronach ofert dopiero po `load` + 4 s + idle (live drop ma pierwszeństwo).
 *  - walk (panel): spaceruje w obrębie obszaru treści; sit (oferty): siedzi w prawym dolnym rogu.
 *  - Noc / sen (`pet.asleep`): śpi w miejscu, klik nie robi pat, tylko dymek „Śpi… zzz".
 *  - Klik = pat pat paczkowany (debounce 2 s, max 50). Towarzysz nigdy nie pokazuje toastów błędów.
 *  - prefers-reduced-motion: bez spaceru, prawy dolny róg, bez wibracji (rig sam wycisza animacje).
 *  - Nie zasłania stałych pasków przy dolnej krawędzi (CTA oferty, pasek produktu) — podnosi się nad nie;
 *    chowa się, gdy na stronie oferty otwarty jest mobilny panel koszyka.
 */
(function () {
    'use strict';

    var el = document.getElementById('petCompanion');
    if (!el || el.getAttribute('data-ready') === '1') return;
    el.setAttribute('data-ready', '1');

    // Adres własnego pliku — z niego wyliczamy ścieżkę do pet-rig.css (ładowany leniwie, patrz ensureRigCss)
    var SELF_SRC = (document.currentScript && document.currentScript.src) || '';

    var WALK_SPEED = 40;               // px/s
    var EDGE = 8;                      // margines spaceru od krawędzi obszaru
    var PAUSE_MIN = 4000, PAUSE_MAX = 9000;
    var GESTURE_CHANCE = 0.3;
    var PAT_DEBOUNCE_MS = 2000, PAT_MAX = 50;
    var SIT_DELAY_MS = 4000;
    var BUBBLE_CARE_MS = 8000, BUBBLE_SLEEP_MS = 4000, BUBBLE_CELEBRATE_MS = 6000;
    var BUBBLE_REPEAT_MS = 10 * 60 * 1000;
    var LIFT_GAP = 8;

    // Stałe elementy przy dolnej krawędzi, których towarzysz nie może zasłaniać (podnosi się nad nie)
    var OBSTACLES = '.checkout-bottom-bar, .product-sticky-bar, .mute-btn, .floating-actions';
    // Otwarte panele, przy których towarzysz się chowa (leżą pod nim w kolejności nakładek)
    var TUCK_WHEN = '.cart-sidebar.mobile-open, .cart-mobile-overlay.active';

    var hit = document.getElementById('petCompanionHit');
    var scene = document.getElementById('petCompanionScene');
    var bubble = document.getElementById('petCompanionBubble');
    var userId = el.getAttribute('data-user-id');
    var mode = el.getAttribute('data-mode') === 'sit' ? 'sit' : 'walk';
    var homeUrl = el.getAttribute('data-home-url') || '/client/pupile';
    var celebratePending = el.getAttribute('data-celebrate') === '1';
    var bubbleKey = 'pets_bubble_shown_' + userId;

    var rig = null;
    var pet = null;                    // pet_dict towarzysza (ostatni znany)
    var lastState = null;
    var cssReady = false, cssLoading = false, cssFailed = false;
    var started = false;               // stan już był wczytany — od teraz reagujemy na pets:state
    var firstShow = true;
    var x = null;                      // pozycja left w trybie walk (px)
    var walking = false;
    var timers = { walk: 0, arrive: 0, pat: 0, bubble: 0, bubbleFade: 0 };
    var patCount = 0, patPetId = null;
    var liftRaf = 0;

    el.classList.add('pet-companion--' + mode);
    bubble.setAttribute('role', 'status');
    bubble.setAttribute('aria-live', 'polite');

    // --- pomocnicze -----------------------------------------------------------------------------

    function noop() {}

    function reducedMotion() {
        return !!(window.PetRig && window.PetRig.reducedMotion && window.PetRig.reducedMotion());
    }

    function whenIdle(fn) {
        if (window.requestIdleCallback) window.requestIdleCallback(fn, { timeout: 3000 });
        else setTimeout(fn, 1500);
    }

    function haptic() {
        if (window.Haptics && window.Haptics.enabled && window.Haptics.enabled()) window.Haptics.tap();
        else if (navigator.vibrate && !reducedMotion()) {
            try { navigator.vibrate(10); } catch (e) { /* ignoruj */ }
        }
    }

    function findPet(state) {
        var comp = (state && state.companion) || {};
        if (!comp.enabled || comp.pet_id == null) return null;
        var list = (state && state.pets) || [];
        for (var i = 0; i < list.length; i++) {
            if (list[i].id === comp.pet_id) return list[i];
        }
        return null;
    }

    function rigOpts(p) {
        return {
            species: p.species, stage: p.stage, stars: p.stars, mood: p.mood,
            asleep: !!p.asleep, size: 'companion',
            idle: mode === 'sit'      // siedząc „żyje" gestami rigu; spacerując gesty wywołujemy sami
        };
    }

    function isVisible(node) {
        if (!node) return false;
        var cs = window.getComputedStyle(node);
        if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
        var r = node.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    }

    // --- CSS rigu (leniwie) ---------------------------------------------------------------------
    // Panel i oferty nie ładują pet-rig.css (32 KB) — towarzysz dociąga go dopiero, gdy ma kogo pokazać.

    function rigCssHref() {
        // data-rig-css = url_for z wersją pliku (?v=mtime); awaryjnie ścieżka obok własnego skryptu
        var fromAttr = el.getAttribute('data-rig-css');
        if (fromAttr) return fromAttr;
        var m = SELF_SRC.match(/^(.*\/)js\/components\/pet-companion\.js/);
        return m ? m[1] + 'css/components/pet-rig.css' : '/static/css/components/pet-rig.css';
    }

    function ensureRigCss(cb) {
        if (cssReady) { cb(); return; }
        if (cssFailed) return;
        if (document.querySelector('link[href*="css/components/pet-rig.css"]')) {
            cssReady = true;
            cb();
            return;
        }
        if (cssLoading) return;
        cssLoading = true;
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = rigCssHref();
        link.onload = function () { cssLoading = false; cssReady = true; cb(); };
        link.onerror = function () { cssLoading = false; cssFailed = true; };   // bez stylów rig wyglądałby źle — zostaje ukryty
        document.head.appendChild(link);
    }

    // --- widoczność -----------------------------------------------------------------------------

    function hide() {
        stopWalk();
        clearTimeout(timers.pat);
        patCount = 0;
        hideBubble(true);
        if (rig) { rig.destroy(); rig = null; }
        pet = null;
        el.hidden = true;
    }

    function apply(state) {
        lastState = state;
        var p = findPet(state);
        if (!p) { hide(); return; }
        if (!cssReady) {
            ensureRigCss(function () { if (lastState) apply(lastState); });
            return;
        }
        var samePet = rig && pet && pet.id === p.id;
        pet = p;
        if (samePet) {
            rig.update(rigOpts(p));
        } else {
            if (rig) rig.destroy();
            scene.innerHTML = '';
            rig = window.PetRig.mount(scene, rigOpts(p));
        }
        el.classList.toggle('pet-companion--asleep', !!p.asleep);
        if (el.hidden) {
            placeInitial();
            el.hidden = false;
        }
        updateLift();
        updateWalk();
        afterApply(state);
    }

    function afterApply(state) {
        if (firstShow) {
            firstShow = false;
            if (celebratePending) {
                celebratePending = false;
                if (!pet.asleep) {
                    rig.playAction('celebrate').then(noop, noop);
                    showBubble('Hura! Dziękuję za zamówienie 🎉', { ms: BUBBLE_CELEBRATE_MS });
                    return;
                }
            }
            if (pet.asleep) {
                if (bubbleAllowed()) {
                    markBubble();
                    showBubble('Śpi… zzz', { ms: BUBBLE_SLEEP_MS });
                }
                return;
            }
        }
        maybeCareBubble(state);
    }

    // --- dymek ----------------------------------------------------------------------------------

    function bubbleAllowed() {
        try {
            var t = parseInt(sessionStorage.getItem(bubbleKey), 10);
            return !(t && Date.now() - t < BUBBLE_REPEAT_MS);
        } catch (e) { return true; }
    }

    function markBubble() {
        try { sessionStorage.setItem(bubbleKey, String(Date.now())); } catch (e) { /* prywatne okno */ }
    }

    function careText(state) {
        var m = pet && pet.mood;
        if (m === 'krytyczny' || m === 'chory') return 'Źle się czuję…';
        if (m === 'glodny') return 'Jestem głodny!';
        if (m === 'smutny' || m === 'znudzony') return 'Pobaw się ze mną!';
        if (m === 'brudny') return 'Umyj mnie!';
        var eggs = state.eggs || [];
        for (var i = 0; i < eggs.length; i++) if (eggs[i].ready) return 'Jajko gotowe!';
        if (state.eggs_available && state.eggs_available.length) return 'Czeka na Ciebie jajko!';
        return null;   // opieki potrzebuje inny pupil — kropka w nawigacji to pokazuje, towarzysz nie mówi za niego
    }

    function maybeCareBubble(state) {
        if (!pet || pet.asleep || !state || !state.needs_care) return;
        if (!bubble.hidden) return;
        var text = careText(state);
        if (!text || !bubbleAllowed()) return;
        markBubble();
        showBubble(text, { ms: BUBBLE_CARE_MS, link: true });
    }

    function showBubble(text, opts) {
        clearTimeout(timers.bubble);
        clearTimeout(timers.bubbleFade);
        bubble.innerHTML = '';
        var span = document.createElement('span');
        span.className = 'pet-companion__bubble-text';
        span.textContent = text;
        bubble.appendChild(span);
        if (opts.link) {
            var a = document.createElement('a');
            a.className = 'pet-companion__bubble-link';
            a.href = homeUrl;
            a.textContent = 'Do domku';
            bubble.appendChild(a);
        }
        sideBubble();
        bubble.hidden = false;
        // klasa po klatce, żeby zadziałało przejście opacity
        requestAnimationFrame(function () { bubble.classList.add('is-visible'); });
        timers.bubble = setTimeout(function () { hideBubble(false); }, opts.ms);
    }

    function hideBubble(now) {
        clearTimeout(timers.bubble);
        clearTimeout(timers.bubbleFade);
        bubble.classList.remove('is-visible');
        if (now || reducedMotion()) { bubble.hidden = true; return; }
        timers.bubbleFade = setTimeout(function () { bubble.hidden = true; }, 220);
    }

    // Dymek otwiera się w stronę środka ekranu, żeby nie wyjechał poza krawędź
    function sideBubble() {
        var r = el.getBoundingClientRect();
        var toLeft = mode === 'sit' || el.classList.contains('pet-companion--corner') ||
            (r.left + r.width / 2 > window.innerWidth / 2);
        el.classList.toggle('pet-companion--bubble-left', toLeft);
    }

    bubble.addEventListener('click', function (e) {
        if (e.target && e.target.closest && e.target.closest('.pet-companion__bubble-link')) return;
        hideBubble(false);
    });

    // --- spacer ---------------------------------------------------------------------------------

    function width() { return el.offsetWidth || 72; }

    function bounds() {
        var min = 0, max = window.innerWidth;
        // Na desktopie stały sidebar zajmuje lewą część — spacer tylko nad obszarem treści
        var wrap = document.querySelector('.main-wrapper');
        if (wrap) {
            var r = wrap.getBoundingClientRect();
            if (r.width > 0) { min = Math.max(0, r.left); max = Math.min(window.innerWidth, r.right); }
        }
        var lo = min + EDGE, hi = max - width() - EDGE;
        if (hi < lo) hi = lo;
        return { min: lo, max: hi };
    }

    function walkAllowed() {
        return mode === 'walk' && !!pet && !pet.asleep && !reducedMotion() && !el.hidden &&
            document.visibilityState !== 'hidden';
    }

    function setLeft(px, animate) {
        if (!animate) {
            el.style.transition = 'none';
            el.style.left = px + 'px';
            void el.offsetWidth;   // reflow — kolejna zmiana left znów animuje
            el.style.transition = '';
        } else {
            el.style.left = px + 'px';
        }
        x = px;
    }

    function placeInitial() {
        if (mode !== 'walk') return;
        if (reducedMotion()) {
            el.classList.add('pet-companion--corner');
            el.style.left = '';
            return;
        }
        el.classList.remove('pet-companion--corner');
        var b = bounds();
        setLeft(Math.round(b.min + Math.random() * (b.max - b.min)), false);
    }

    function updateWalk() {
        if (mode !== 'walk') return;
        var rm = reducedMotion();
        if (rm !== el.classList.contains('pet-companion--corner')) placeInitial();
        if (!walkAllowed()) { stopWalk(); return; }
        if (!walking && !timers.walk) scheduleWalk(1000 + Math.random() * 2000);
    }

    function scheduleWalk(delay) {
        clearTimeout(timers.walk);
        timers.walk = setTimeout(walkStep, delay);
    }

    function walkStep() {
        timers.walk = 0;
        if (!walkAllowed()) return;
        var b = bounds();
        if (x == null) x = b.min;
        var target = Math.round(b.min + Math.random() * (b.max - b.min));
        if (Math.abs(target - x) < 40) {   // za blisko — postój i kolejna próba
            scheduleWalk(PAUSE_MIN + Math.random() * (PAUSE_MAX - PAUSE_MIN));
            return;
        }
        var secs = Math.abs(target - x) / WALK_SPEED;
        el.classList.toggle('pet-companion--flipped', target < x);
        el.style.setProperty('--pet-companion-walk', secs.toFixed(2) + 's');
        el.classList.add('pet-companion--walking');
        walking = true;
        setLeft(target, true);
        clearTimeout(timers.arrive);
        timers.arrive = setTimeout(arrived, secs * 1000 + 60);
    }

    function arrived() {
        timers.arrive = 0;
        walking = false;
        el.classList.remove('pet-companion--walking');
        if (!walkAllowed()) return;
        if (rig && Math.random() < GESTURE_CHANCE) {
            var list = (pet.gestures || ['jump', 'sway']).filter(function (n) { return n !== 'blink'; });
            if (list.length) rig.gesture(list[Math.floor(Math.random() * list.length)]);   // false = niedostępny, trudno
        }
        scheduleWalk(PAUSE_MIN + Math.random() * (PAUSE_MAX - PAUSE_MIN));
    }

    // Zatrzymuje w bieżącym miejscu (np. klik w idącego pupila)
    function stopWalk() {
        clearTimeout(timers.walk);
        clearTimeout(timers.arrive);
        timers.walk = timers.arrive = 0;
        if (walking) {
            var r = el.getBoundingClientRect();
            setLeft(Math.round(r.left), false);
        }
        walking = false;
        el.classList.remove('pet-companion--walking');
    }

    function clampToBounds() {
        if (mode !== 'walk' || el.hidden || x == null || el.classList.contains('pet-companion--corner')) return;
        stopWalk();
        var b = bounds();
        setLeft(Math.min(b.max, Math.max(b.min, x)), false);
        updateWalk();
    }

    // --- nie zasłaniaj CTA ----------------------------------------------------------------------

    function updateLift() {
        if (el.hidden) return;
        // Mobilny panel koszyka oferty leży pod towarzyszem — na czas otwarcia chowamy się
        var tucked = false;
        var tuckNodes = document.querySelectorAll(TUCK_WHEN);
        for (var t = 0; t < tuckNodes.length; t++) if (isVisible(tuckNodes[t])) { tucked = true; break; }
        el.classList.toggle('pet-companion--tucked', tucked);

        var cur = parseFloat(el.style.getPropertyValue('--pet-companion-lift')) || 0;
        var r = el.getBoundingClientRect();
        var vh = window.innerHeight;
        var baseBottom = vh - r.bottom - cur;          // odstęp od dołu bez podniesienia
        var bottomY = vh - baseBottom, topY = bottomY - r.height;
        var left = r.left, right = r.right;
        if (mode === 'walk' && !el.classList.contains('pet-companion--corner')) {
            var b = bounds();                          // spacerujący przechodzi całą szerokość
            left = b.min;
            right = b.max + width();
        }
        var need = 0;
        var nodes = document.querySelectorAll(OBSTACLES);
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            if (!isVisible(n)) continue;
            var o = n.getBoundingClientRect();
            if (o.right <= left || o.left >= right) continue;     // nie nachodzi w poziomie
            if (o.top >= bottomY || o.bottom <= topY) continue;  // nie nachodzi w pionie
            need = Math.max(need, (vh - o.top) + LIFT_GAP - baseBottom);
        }
        need = Math.max(0, Math.round(need));
        if (need !== cur) el.style.setProperty('--pet-companion-lift', need + 'px');
    }

    function scheduleLift() {
        if (liftRaf) return;
        liftRaf = requestAnimationFrame(function () { liftRaf = 0; updateLift(); });
    }

    function watchObstacles() {
        if (!window.MutationObserver) return;
        var mo = new MutationObserver(scheduleLift);
        var nodes = document.querySelectorAll(OBSTACLES + ', ' + TUCK_WHEN + ', .cart-sidebar, .cart-mobile-overlay');
        for (var i = 0; i < nodes.length; i++) {
            mo.observe(nodes[i], { attributes: true, attributeFilter: ['class', 'style', 'hidden'] });
        }
    }

    // --- pat pat --------------------------------------------------------------------------------

    function flushPat() {
        clearTimeout(timers.pat);
        var count = patCount, id = patPetId;
        patCount = 0;
        if (!count || id == null) return;
        window.PetsApi.post('/' + id + '/akcja', { action: 'pat', count: count }).then(function (res) {
            if (res && res.state) window.PetsState.set(res.state);
        }, function (err) {
            var st = err && err.status;
            if (st === 410) {                       // pupil odszedł między odczytami
                window.PetsState.invalidate(userId);
                hide();
            } else if (st === 409 || st === 404) {  // zasnął / niedostępna / nie ma go — stan był nieświeży
                window.PetsState.fetchLite(userId, { force: true }).then(noop, noop);
            }
            // inne błędy: cicho — towarzysz nie przeszkadza toastami
        });
    }

    // Wyjście ze strony w trakcie paczkowania — wyślij resztę z keepalive (PetsApi go nie obsługuje)
    function flushPatOnExit() {
        if (!patCount || patPetId == null) return;
        var count = patCount, id = patPetId;
        patCount = 0;
        clearTimeout(timers.pat);
        var meta = document.querySelector('meta[name="csrf-token"]');
        try {
            fetch((el.getAttribute('data-api') || '/client/pupile/api') + '/' + id + '/akcja', {
                method: 'POST',
                credentials: 'same-origin',
                keepalive: true,
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': meta ? meta.getAttribute('content') : ''
                },
                body: JSON.stringify({ action: 'pat', count: count })
            }).then(noop, noop);
        } catch (e) { /* ignoruj */ }
        window.PetsState.invalidate(userId);       // odpowiedź nie wróci — następna strona pobierze świeży stan
    }

    hit.addEventListener('click', function () {
        if (!pet || !rig) return;
        if (pet.asleep) {
            showBubble('Śpi… zzz', { ms: BUBBLE_SLEEP_MS });
            return;
        }
        haptic();
        rig.playAction('pat').then(noop, noop);
        if (walking) {
            stopWalk();
            scheduleWalk(PAUSE_MIN + Math.random() * (PAUSE_MAX - PAUSE_MIN));
        }
        if (patPetId !== pet.id) { flushPat(); patPetId = pet.id; }
        patCount++;
        clearTimeout(timers.pat);
        if (patCount >= PAT_MAX) flushPat();
        else timers.pat = setTimeout(flushPat, PAT_DEBOUNCE_MS);
    });

    // --- start ----------------------------------------------------------------------------------

    function fetchState() {
        window.PetsState.fetchLite(userId).then(noop, noop);   // wynik trafia przez onChange
    }

    function start() {
        started = true;
        if (window.PetsState.load(userId)) fetchState();       // cache: bez sieci, od razu
        else whenIdle(fetchState);
    }

    function boot() {
        if (!userId || !window.PetsState || !window.PetsApi || !window.PetRig || !hit || !scene || !bubble) return;
        // Na stronie domku wszystkie pupile są na wierzchu — towarzysz z linkiem „Do domku" byłby dublem
        if (document.getElementById('petsApp')) return;
        window.PetsState.onChange(function (state) {
            if (started) apply(state);
        });
        if (mode === 'sit') {
            var go = function () {
                setTimeout(function () { whenIdle(start); }, SIT_DELAY_MS);
            };
            if (document.readyState === 'complete') go();
            else window.addEventListener('load', go);
        } else {
            start();
        }

        var resizeRaf = 0;
        window.addEventListener('resize', function () {
            if (resizeRaf) return;
            resizeRaf = requestAnimationFrame(function () {
                resizeRaf = 0;
                clampToBounds();
                updateLift();
                if (!bubble.hidden) sideBubble();
            });
        });
        window.addEventListener('scroll', scheduleLift, { passive: true });
        watchObstacles();

        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'hidden') {
                flushPatOnExit();
                stopWalk();
            } else if (started) {
                fetchState();    // długo otwarta karta: cache wygasł → świeży stan (sen, dymek)
                updateWalk();
            }
        });
        window.addEventListener('pagehide', flushPatOnExit);

        // Zmiana ustawienia ruchu w trakcie (system / DevTools)
        if (window.matchMedia) {
            var mq = window.matchMedia('(prefers-reduced-motion: reduce)');
            var onMq = function () { if (pet) { placeInitial(); updateWalk(); } };
            if (mq.addEventListener) mq.addEventListener('change', onMq);
            else if (mq.addListener) mq.addListener(onMq);
        }
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else boot();
})();
