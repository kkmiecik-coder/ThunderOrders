/**
 * Towarzysz — pupil na stronach panelu klienta i ofert (spec §4.4, plan etapu 5 Task 4).
 *
 * Szkielet: templates/components/pet_companion.html
 *   #petCompanion[hidden][data-user-id][data-api][data-home-url][data-house-url][data-hospital-url]
 *                [data-ward-url][data-mode="walk|sit"][data-celebrate="0|1"]
 *   #petCompanionHit (przycisk ≥ 44 px nad sceną) · #petCompanionScene (rig) · #petCompanionBubble (dymek)
 *
 * Wymaga: window.PetRig (pet-rig.js), window.PetsState/PetsApi (pets-core.js). window.Haptics opcjonalnie.
 *
 * Zasady:
 *  - SSR nie pyta bazy: stan lite z localStorage (pets-core, klucz z user_id) albo z sieci w wolnej chwili;
 *    na stronach ofert dopiero po `load` + 4 s + idle (live drop ma pierwszeństwo).
 *  - walk (panel): chodzi po CAŁYM obszarze treści (bez topbara i sidebara; na telefonie nad dolnym paskiem
 *    PWA) — losowy cel, przejście w poziomie i pionie (patrzy w stronę ruchu), postój, czasem siada albo
 *    robi gest. sit (oferty): siedzi w prawym dolnym rogu jak dawniej.
 *  - Wszędzie da się go chwycić i przenieść: mysz — przeciągnięcie (> 6 px), dotyk — przytrzymanie
 *    (350 ms; wcześniejszy ruch palca = zwykłe przewijanie strony). Trzymany jest „podniesiony" (większy,
 *    macha łapkami, cień pod nim). Upuszczony zostaje: w walk po chwili rusza dalej od tego miejsca,
 *    w sit zostaje tam (zapis na sesję karty). Klik bez ruchu = pat pat; przeciągnięcie pat nie wysyła.
 *  - Noc / sen (`pet.asleep`): śpi w miejscu, nie chodzi, klik nie robi pat, tylko dymek „Śpi… zzz";
 *    przenieść go można.
 *  - Klik = pat pat paczkowany (debounce 2 s, max 50). Towarzysz nigdy nie pokazuje toastów błędów.
 *  - prefers-reduced-motion: bez spaceru (siedzi tam, gdzie był, albo w prawym dolnym rogu), bez wibracji;
 *    przenoszenie działa (bez animacji).
 *  - Nie zasłania stałych pasków przy dolnej krawędzi (CTA oferty, pasek produktu, pasek PWA) — podnosi się
 *    nad nie; chowa się, gdy na stronie oferty otwarty jest mobilny panel koszyka.
 *  - Pamięć pozycji (spec v3 §8): sessionStorage['pets_companion_pos_<user_id>'] = {x_ratio, y_ratio, facing, t}
 *    (y_ratio od wersji „cały ekran"; zapis bez y_ratio = przy dolnej krawędzi) zapisywane przy każdym kroku
 *    spaceru, po upuszczeniu i na pagehide; przy starcie w trybie walk zapis < 30 min stawia towarzysza dokładnie
 *    tam (bez przejścia CSS), potem spacer dalej. Tryb sit ignoruje ten zapis (nie kasuje); miejsce, w którym
 *    upuszczono go na stronie oferty, trzyma osobno: sessionStorage['pets_companion_sit_<user_id>'].
 *  - Pupil w szpitalu nigdy nie jest towarzyszem (stan: companion.pet_id wskazuje kogoś spoza szpitala albo
 *    null) — tu tylko obrona: null / pupil z `hospital` = towarzysz ukryty.
 *  - Dymek jest mały, sam znika po 7 s i ma × (cel 44 px). Zamknięty (× albo klik w dymek) nie wraca w tej samej
 *    sprawie do końca sesji karty: sessionStorage['pets_bubble_closed_<user_id>'] = lista spraw (np. „glodny:12”,
 *    „jajko-gotowe”). Tryb sit (strony ofert) nie pokazuje dymków opieki ani „Śpi…” sam z siebie — tylko małą
 *    plakietkę „!” na pupilu, bez linku wyprowadzającego z zakupów (dymek po kliknięciu w śpiącego i podziękowanie
 *    na stronie po zamówieniu zostają — bez linków).
 */
(function () {
    'use strict';

    var el = document.getElementById('petCompanion');
    if (!el || el.getAttribute('data-ready') === '1') return;
    el.setAttribute('data-ready', '1');

    // Adres własnego pliku — z niego wyliczamy ścieżkę do pet-rig.css (ładowany leniwie, patrz ensureRigCss)
    var SELF_SRC = (document.currentScript && document.currentScript.src) || '';

    var WALK_SPEED = 40;               // px/s
    var RUN_SPEED = 170;               // px/s — bieg na 4 łapach (spec v3.2 §3)
    var RUN_CHANCE = 0.2;              // szansa, że dłuższy krok to bieg
    var RUN_MIN_DIST = 200;            // krótsze przejścia zawsze marszem
    var EDGE = 8;                      // margines obszaru spaceru od boków i od górnego paska
    var BOTTOM_EDGE = 16;              // odstęp od dolnej krawędzi okna (jak `bottom: 16px` w CSS)
    var STEP_MIN = 60, STEP_MAX = 420; // długość jednego przejścia (px)
    var PAUSE_MIN = 4000, PAUSE_MAX = 9000;
    var SIT_PAUSE_MIN = 8000, SIT_PAUSE_MAX = 16000;
    var GESTURE_CHANCE = 0.3, SIT_CHANCE = 0.35;
    var STAND_UP_MS = 450;             // wstaje (przejście pozy w rigu), zanim ruszy
    var DROP_PAUSE_MIN = 2500, DROP_PAUSE_MAX = 5000;
    var DRAG_PX = 6;                   // mysz: ruch > 6 px = przeciąganie, mniejszy = klik (pat)
    var HOLD_MS = 350;                 // dotyk: przytrzymanie podnosi pupila
    var TOUCH_SLOP = 10;               // dotyk: ruch palca przed przytrzymaniem = przewijanie strony
    var FACE_PX = 12;                  // trzymany odwraca się po tylu px ruchu w drugą stronę
    var CLICK_GUARD_MS = 450;          // „klik" kończący przeciąganie nie jest pat
    var PAT_DEBOUNCE_MS = 2000, PAT_MAX = 50;
    var SIT_DELAY_MS = 4000;
    var BUBBLE_CARE_MS = 7000, BUBBLE_SLEEP_MS = 4000, BUBBLE_CELEBRATE_MS = 6000;
    var BUBBLE_REPEAT_MS = 10 * 60 * 1000;
    var BUBBLE_GAP = 10, BUBBLE_MARGIN = 8;
    var LIFT_GAP = 8;
    var POS_TTL_MS = 30 * 60 * 1000;   // spec v3 §8: zapis pozycji ważny 30 min

    // Stałe elementy przy dolnej krawędzi, których towarzysz nie może zasłaniać (podnosi się nad nie)
    // (.cart-footer: stopka przyklejonego koszyka oferty na desktopie — przy długim koszyku schodzi w róg)
    var OBSTACLES = '.checkout-bottom-bar, .product-sticky-bar, .mute-btn, .floating-actions, .cart-sidebar .cart-footer';
    // Dla swobodnej pozycji także dolny pasek PWA (widoczny tylko w trybie standalone)
    var FLOOR_OBSTACLES = OBSTACLES + ', .pwa-bottom-bar';
    // Stałe paski u góry okna (desktop / telefon) — spacer i dymek pod nimi
    var TOP_BARS = '.topbar, .mobile-navbar';
    // Otwarte panele, przy których towarzysz się chowa (leżą pod nim w kolejności nakładek)
    var TUCK_WHEN = '.cart-sidebar.mobile-open, .cart-mobile-overlay.active';

    var hit = document.getElementById('petCompanionHit');
    var scene = document.getElementById('petCompanionScene');
    var bubble = document.getElementById('petCompanionBubble');
    var userId = el.getAttribute('data-user-id');
    var mode = el.getAttribute('data-mode') === 'sit' ? 'sit' : 'walk';
    var homeUrl = el.getAttribute('data-home-url') || '/client/pupile';
    var houseUrl = el.getAttribute('data-house-url') || homeUrl + '/domek';
    var hospitalUrl = el.getAttribute('data-hospital-url') || homeUrl + '/szpital';
    var wardUrl = el.getAttribute('data-ward-url') || hospitalUrl + '/izba-przyjec';
    var celebratePending = el.getAttribute('data-celebrate') === '1';
    var bubbleKey = 'pets_bubble_shown_' + userId;
    var closedKey = 'pets_bubble_closed_' + userId;
    var posKey = 'pets_companion_pos_' + userId;
    var sitKey = 'pets_companion_sit_' + userId;

    var rig = null;
    var pet = null;                    // pet_dict towarzysza (ostatni znany)
    var lastState = null;
    var cssReady = false, cssLoading = false, cssFailed = false;
    var started = false;               // stan już był wczytany — od teraz reagujemy na pets:state
    var firstShow = true;
    var pos = null;                    // swobodna pozycja {x, y} (lewy górny róg, px w oknie); w marszu = cel
    var walking = false;
    var running = false;               // walk: bieg na 4 łapach (poza `run` w rigu)
    var claim = null;                  // zajęty przez żart: {onBreak} (spec v3.2 §4)
    var arriveHook = null;             // runTo: wołany po dotarciu (true) albo przerwaniu (false)
    var sitting = false;               // walk: odpoczywa na siedząco
    var curPose = 'stand';
    var held = false;                  // trzymany (przeciąganie)
    var scrollCheckTimer = 0;          // po przewinięciu: czy pupil nie stoi na kontrolce
    var drag = null;                   // gest wskaźnika na pupilu (patrz „chwytanie")
    var clickGuardUntil = 0;
    var timers = { walk: 0, arrive: 0, pat: 0, bubble: 0, bubbleFade: 0 };
    var patCount = 0, patPetId = null;
    var liftRaf = 0;
    var bubbleTopic = null;            // sprawa bieżącego dymka (zamknięcie → nie wraca do końca sesji)
    var badge = null;                  // tryb sit: plakietka „!” zamiast dymka opieki

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
            // Pupil w szpitalu nie towarzyszy (stan już to zapewnia — to tylko obrona przed starym cache)
            if (list[i].id === comp.pet_id) return list[i].hospital ? null : list[i];
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

    function clamp01(v) { return Math.min(1, Math.max(0, v)); }

    function round4(v) { return Math.round(clamp01(v) * 10000) / 10000; }

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
        breakClaim();
        cancelDrag();
        stopWalk();
        clearTimeout(timers.pat);
        patCount = 0;
        hideBubble(true);
        if (badge) badge.hidden = true;
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
        if (claim && (!samePet || p.asleep)) breakClaim();   // inny towarzysz albo zasnął — żart się kończy
        pet = p;
        if (samePet) {
            rig.update(rigOpts(p));
        } else {
            if (rig) rig.destroy();
            scene.innerHTML = '';
            rig = window.PetRig.mount(scene, rigOpts(p));
            curPose = 'stand';             // świeży rig stoi
        }
        el.classList.toggle('pet-companion--asleep', !!p.asleep);
        hit.setAttribute('aria-label', p.asleep ? 'Pupil śpi' : 'Pogłaszcz pupila');
        if (el.hidden) {
            el.hidden = false;     // najpierw widoczny — pomiary szerokości i położenia wymagają layoutu
            placeInitial();
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
                    showBubble('Hura! Dziękuję za zamówienie 🎉', { ms: BUBBLE_CELEBRATE_MS, topic: 'dziekuje' });
                    return;
                }
            }
            // Na stronie oferty sam z siebie nic nie mówi (zakupy mają pierwszeństwo)
            if (pet.asleep) {
                if (mode !== 'sit' && bubbleAllowed() && !topicClosed('sen')) {
                    markBubble();
                    showBubble('Śpi… zzz', { ms: BUBBLE_SLEEP_MS, topic: 'sen' });
                }
                return;
            }
        }
        maybeCareBubble(state);
    }

    // --- obszar i pozycja -----------------------------------------------------------------------
    // Swobodna pozycja (klasa --free): lewy górny róg w px okna (inline left/top). Tryb walk zawsze;
    // tryb sit dopiero po przeniesieniu — wcześniej róg z CSS (right/bottom + omijanie pasków).

    function viewport() {
        var de = document.documentElement;
        // clientWidth bez paska przewijania — pupil nie wejdzie pod scrollbar
        return { w: (de && de.clientWidth) || window.innerWidth, h: window.innerHeight };
    }

    // env(safe-area-inset-*) czyta się z CSS przez scroll-margin elementu (pet-companion.css) — JS nie ma
    // do nich bezpośredniego dostępu, a scroll-margin nie wpływa na układ
    function safeInsets() {
        var cs = window.getComputedStyle(el);
        return { top: parseFloat(cs.scrollMarginTop) || 0, bottom: parseFloat(cs.scrollMarginBottom) || 0 };
    }

    /**
     * Dozwolony obszar lewego górnego rogu pupila: minX..maxX, minY..maxYAt(x).
     * walk: tylko nad obszarem treści (.main-wrapper — bez sidebara), pod górnym paskiem;
     * oba tryby: nad stałymi paskami przy dolnej krawędzi, które nachodzą na pupila w poziomie.
     */
    function area() {
        var vp = viewport();
        var w = el.offsetWidth || 72, h = el.offsetHeight || 72;
        var minX = 0, maxX = vp.w, minY = 0;
        if (mode === 'walk') {
            var wrap = document.querySelector('.main-wrapper');
            if (wrap) {
                var wr = wrap.getBoundingClientRect();
                if (wr.width > 0) { minX = Math.max(0, wr.left); maxX = Math.min(vp.w, wr.right); }
            }
        }
        var bars = document.querySelectorAll(TOP_BARS);
        for (var i = 0; i < bars.length; i++) {
            if (!isVisible(bars[i])) continue;
            var br = bars[i].getBoundingClientRect();
            if (br.top <= 1 && br.bottom < vp.h / 2) minY = Math.max(minY, br.bottom);
        }
        var safe = safeInsets();
        minY = Math.max(minY, safe.top);
        var obs = [];
        var nodes = document.querySelectorAll(FLOOR_OBSTACLES);
        for (var j = 0; j < nodes.length; j++) {
            if (!isVisible(nodes[j])) continue;
            var o = nodes[j].getBoundingClientRect();
            if (o.top < vp.h / 2 || o.top >= vp.h) continue;    // tylko paski w dolnej połowie widoku
            obs.push({ left: o.left, right: o.right, top: o.top - LIFT_GAP });
        }
        var a = {
            w: w, h: h, obs: obs,
            minX: Math.round(minX + EDGE), maxX: Math.round(maxX - w - EDGE),
            minY: Math.round(minY + EDGE),
            floor: vp.h - Math.max(BOTTOM_EDGE, safe.bottom + EDGE)
        };
        if (a.maxX < a.minX) a.maxX = a.minX;
        return a;
    }

    /** Najniższe dozwolone `top` dla pupila stojącego na `x` (nad paskami, które nachodzą w poziomie). */
    function maxYAt(a, x) {
        var f = a.floor;
        for (var i = 0; i < a.obs.length; i++) {
            var o = a.obs[i];
            if (o.right <= x || o.left >= x + a.w) continue;
            f = Math.min(f, o.top);
        }
        return Math.max(a.minY, Math.round(f - a.h));
    }

    function clampTo(a, p) {
        var x = Math.round(Math.min(a.maxX, Math.max(a.minX, p.x)));
        return { x: x, y: Math.round(Math.min(maxYAt(a, x), Math.max(a.minY, p.y))) };
    }

    function isFree() { return el.classList.contains('pet-companion--free'); }

    function setFree(on) {
        el.classList.toggle('pet-companion--free', on);
        if (!on) {
            el.style.left = '';
            el.style.top = '';
            pos = null;
        } else {
            el.style.removeProperty('--pet-companion-lift');
        }
    }

    function setPos(px, py, animate) {
        if (!animate) {
            el.style.transition = 'none';
            el.style.left = px + 'px';
            el.style.top = py + 'px';
            void el.offsetWidth;   // reflow — kolejna zmiana pozycji znów animuje
            el.style.transition = '';
        } else {
            el.style.left = px + 'px';
            el.style.top = py + 'px';
        }
        pos = { x: px, y: py };
    }

    /** Bieżąca pozycja — w trakcie marszu z położenia na ekranie (przejście CSS jest w połowie). */
    function currentPos() {
        if (walking) {
            var r = el.getBoundingClientRect();
            return { x: r.left, y: r.top };
        }
        return pos;
    }

    // --- pamięć pozycji między stronami (spec v3 §8) ----------------------------------------------

    function savePos() {
        if (el.hidden || !isFree()) return;
        var p = currentPos();
        if (!p || isNaN(p.x) || isNaN(p.y)) return;
        var a = area();
        var spanX = a.maxX - a.minX, spanY = maxYAt(a, Math.round(p.x)) - a.minY;
        var rec = {
            x_ratio: round4(spanX > 0 ? (p.x - a.minX) / spanX : 0),
            y_ratio: round4(spanY > 0 ? (p.y - a.minY) / spanY : 1),
            t: Date.now()
        };
        if (mode === 'walk') rec.facing = el.classList.contains('pet-companion--flipped') ? 'left' : 'right';
        try { sessionStorage.setItem(mode === 'walk' ? posKey : sitKey, JSON.stringify(rec)); } catch (e) { /* prywatne okno / pełny storage */ }
    }

    /** Zapis < 30 min albo null. Tylko odczyt — tryb sit i ruch ograniczony nie kasują zapisu spaceru. */
    function loadPos(key) {
        var rec = null;
        try { rec = JSON.parse(sessionStorage.getItem(key) || 'null'); } catch (e) { return null; }
        if (!rec || typeof rec !== 'object') return null;
        var rx = Number(rec.x_ratio), t = Number(rec.t), age = Date.now() - t;
        if (!isFinite(rx) || !isFinite(t) || age < -60000 || age >= POS_TTL_MS) return null;
        // Zapis sprzed spaceru po całym ekranie nie ma y_ratio — wtedy przy dolnej krawędzi, jak dawniej
        var ry = rec.y_ratio == null ? 1 : Number(rec.y_ratio);
        if (!isFinite(ry)) ry = 1;
        return { x: clamp01(rx), y: clamp01(ry), left: rec.facing === 'left' };
    }

    function placeInitial() {
        var saved = loadPos(mode === 'walk' ? posKey : sitKey);
        if (mode === 'sit' && !saved) { setFree(false); return; }   // prawy dolny róg (CSS), jak dawniej
        setFree(true);
        var a = area(), p;
        if (saved) {
            var x0 = Math.round(a.minX + saved.x * (a.maxX - a.minX));
            p = { x: x0, y: Math.round(a.minY + saved.y * (maxYAt(a, x0) - a.minY)) };
            if (mode === 'walk') el.classList.toggle('pet-companion--flipped', saved.left);
        } else if (reducedMotion()) {
            p = { x: a.maxX, y: maxYAt(a, a.maxX) };        // ograniczony ruch: prawy dolny róg, jak dawniej
        } else {
            var x1 = Math.round(a.minX + Math.random() * (a.maxX - a.minX));
            p = { x: x1, y: maxYAt(a, x1) };                // pierwsze wejście: przy dolnej krawędzi
        }
        // Staje dokładnie tam, gdzie był na poprzedniej stronie — pierwsza klatka bez żadnego przejścia
        // (ani pozycji, ani opacity), żeby nie było „wjazdu”; potem spacer rusza normalnie (updateWalk)
        el.classList.add('pet-companion--restored');
        setPos(p.x, p.y, false);
        requestAnimationFrame(function () {
            requestAnimationFrame(function () { el.classList.remove('pet-companion--restored'); });
        });
    }

    /** Swobodna pozycja z powrotem w obszarze (zmiana okna, nowy pasek przy dole, zwinięty sidebar). */
    function keepInArea() {
        if (!isFree() || held || claim || el.hidden || !pos) return;
        var a = area();
        var cur = currentPos();
        var c = clampTo(a, cur);
        var curOk = Math.abs(c.x - cur.x) < 1 && Math.abs(c.y - cur.y) < 1;
        if (walking) {
            var t = clampTo(a, pos);
            if (curOk && t.x === pos.x && t.y === pos.y) return;   // marsz mieści się w obszarze — bez przerywania
            stopWalk();
        } else if (curOk) {
            return;
        }
        setPos(c.x, c.y, false);
        updateWalk();
    }

    // --- spacer ---------------------------------------------------------------------------------

    function walkAllowed() {
        return mode === 'walk' && !!pet && !pet.asleep && !reducedMotion() && !el.hidden && !held && !claim &&
            document.visibilityState !== 'hidden';
    }

    /** Poza rigu w trybie walk: siedzi na postoju i przy ograniczonym ruchu; śpi i wisi w powietrzu stojąc. */
    function syncPose() {
        if (mode !== 'walk' || !rig || typeof rig.setPose !== 'function') return;
        var want = pet && !pet.asleep && !held && (sitting || reducedMotion()) ? 'sit' : 'stand';
        if (want === 'stand' && running) want = 'run';
        if (want === curPose) return;
        curPose = want;
        rig.setPose(want);
    }

    function updateWalk() {
        if (mode !== 'walk' || el.hidden) return;
        syncPose();
        if (claim) return;                 // zajęty przez żart — ruchem steruje claim
        if (!walkAllowed()) { stopWalk(); return; }
        if (!walking && !timers.walk) scheduleWalk(1000 + Math.random() * 2000);
    }

    function scheduleWalk(delay) {
        clearTimeout(timers.walk);
        timers.walk = setTimeout(walkStep, delay);
    }

    function rand(min, max) { return min + Math.random() * (max - min); }

    // Kontrolki strony — pupil nie staje na nich, bo klik w przycisk/pole trafiałby w pupila (pat zamiast akcji)
    var CONTROLS = 'a[href], button, input, select, textarea, label, summary, [role="button"], [role="link"], ' +
        '[role="checkbox"], [role="tab"], [contenteditable="true"], [tabindex]:not([tabindex="-1"])';

    /** Czy pupil stojący lewym-górnym rogiem w (x, y) zasłoniłby kontrolkę strony (próbka 5 punktów). */
    function coversControl(x, y) {
        if (!document.elementsFromPoint) return false;
        var w = el.offsetWidth || 72, h = el.offsetHeight || 72;
        var pts = [[0.5, 0.5], [0.2, 0.25], [0.8, 0.25], [0.2, 0.8], [0.8, 0.8]];
        for (var i = 0; i < pts.length; i++) {
            var px = x + w * pts[i][0], py = y + h * pts[i][1];
            if (px < 0 || py < 0 || px >= window.innerWidth || py >= window.innerHeight) continue;
            var list = document.elementsFromPoint(px, py);
            for (var j = 0; j < list.length; j++) {
                if (el.contains(list[j])) continue;            // sam pupil (i jego dymek)
                if (list[j].closest && list[j].closest(CONTROLS)) return true;
                break;                                         // pierwszy element pod pupilem nie jest kontrolką
            }
        }
        return false;
    }

    /** Losowy cel w obszarze, w zasięgu STEP_MIN..STEP_MAX od `cur`, nie na kontrolce (null = brak miejsca). */
    function pickTarget(a, cur) {
        for (var i = 0; i < 12; i++) {
            var tx = rand(a.minX, a.maxX);
            var ty = rand(a.minY, maxYAt(a, Math.round(tx)));
            var dx = tx - cur.x, dy = ty - cur.y, d = Math.sqrt(dx * dx + dy * dy);
            if (d < STEP_MIN) continue;
            if (d > STEP_MAX) {
                var k = rand(STEP_MIN, STEP_MAX) / d;
                tx = cur.x + dx * k;
                ty = cur.y + dy * k;
            }
            var t = clampTo(a, { x: tx, y: ty });
            if (coversControl(t.x, t.y)) continue;
            return t;
        }
        return null;
    }

    /** Po przewinięciu/starcie: stojący pupil nie może zostać na kontrolce — idzie dalej (śpiący przeskakuje). */
    function checkStandingSpot() {
        scrollCheckTimer = 0;
        if (mode !== 'walk' || el.hidden || held || claim || walking || !pos || !pet) return;
        if (!coversControl(pos.x, pos.y)) return;
        if (walkAllowed()) { scheduleWalk(300); return; }
        var t = pickTarget(area(), pos);
        if (t) { setPos(t.x, t.y, false); savePos(); }
    }

    function walkStep() {
        timers.walk = 0;
        if (!walkAllowed()) return;
        if (!bubble.hidden) { scheduleWalk(1500); return; }   // mówi — stoi (link w dymku nie ucieka)
        if (sitting) {                                          // najpierw wstaje
            sitting = false;
            syncPose();
            scheduleWalk(STAND_UP_MS);
            return;
        }
        var a = area();
        if (!pos) pos = clampTo(a, { x: a.minX, y: a.minY });
        savePos();                          // krok spaceru: punkt startu (pagehide dopisze miejsce w pół drogi)
        var target = pickTarget(a, pos);
        if (!target) {                      // brak miejsca (małe okno) — postój i kolejna próba
            scheduleWalk(rand(PAUSE_MIN, PAUSE_MAX));
            return;
        }
        startMove(target, runsThisStep(Math.sqrt(Math.pow(target.x - pos.x, 2) + Math.pow(target.y - pos.y, 2))));
    }

    /** Czy ten krok to bieg: dłuższy dystans, pupil nie jest chory ani krytyczny, los poniżej RUN_CHANCE. */
    function runsThisStep(dist) {
        if (dist < RUN_MIN_DIST || !pet || pet.mood === 'chory' || pet.mood === 'krytyczny') return false;
        return Math.random() < RUN_CHANCE;
    }

    /** Rusza do `target` marszem albo biegiem: zwrot, czas z prędkości, klasy ruchu, cel z przejściem CSS. */
    function startMove(target, run) {
        var dx = target.x - pos.x, dy = target.y - pos.y;
        var secs = Math.sqrt(dx * dx + dy * dy) / (run ? RUN_SPEED : WALK_SPEED);
        // rAF w ukrytej karcie nie rusza — klasa odtworzenia nie może zablokować przejścia marszu
        el.classList.remove('pet-companion--restored');
        if (Math.abs(dx) > 4) el.classList.toggle('pet-companion--flipped', dx < 0);   // patrzy w stronę ruchu
        el.style.setProperty('--pet-companion-walk', secs.toFixed(2) + 's');
        el.classList.add('pet-companion--walking');
        el.classList.toggle('pet-companion--running', run);
        running = run;
        syncPose();
        walking = true;
        setPos(target.x, target.y, true);
        clearTimeout(timers.arrive);
        timers.arrive = setTimeout(arrived, secs * 1000 + 60);
    }

    /** Koniec biegu: zdejmuje klasę i wraca do pozy stojącej. */
    function endRun() {
        if (!running) return;
        running = false;
        el.classList.remove('pet-companion--running');
        syncPose();
    }

    function arrived() {
        timers.arrive = 0;
        walking = false;
        endRun();
        el.classList.remove('pet-companion--walking');
        el.style.removeProperty('--pet-companion-walk');
        savePos();
        var hook = arriveHook;               // runTo: cel żartu osiągnięty — dalszy ciąg w module żartów
        arriveHook = null;
        if (hook) { hook(true); return; }
        if (!walkAllowed()) return;
        var roll = Math.random();
        var pause = rand(PAUSE_MIN, PAUSE_MAX);
        if (rig && roll < GESTURE_CHANCE) {
            var list = (pet.gestures || ['jump', 'sway']).filter(function (n) { return n !== 'blink'; });
            if (list.length) rig.gesture(list[Math.floor(Math.random() * list.length)]);   // false = niedostępny, trudno
        } else if (roll < GESTURE_CHANCE + SIT_CHANCE) {
            sitting = true;                 // dłuższy postój na siedząco
            syncPose();
            pause = rand(SIT_PAUSE_MIN, SIT_PAUSE_MAX);
        }
        scheduleWalk(pause);
    }

    // Zatrzymuje w bieżącym miejscu (np. klik w idącego pupila, chwycenie)
    function stopWalk() {
        clearTimeout(timers.walk);
        clearTimeout(timers.arrive);
        timers.walk = timers.arrive = 0;
        if (walking) {
            var r = el.getBoundingClientRect();
            setPos(Math.round(r.left), Math.round(r.top), false);
        }
        walking = false;
        endRun();
        el.classList.remove('pet-companion--walking');
        el.style.removeProperty('--pet-companion-walk');
        var hook = arriveHook;               // przerwany marsz/bieg: runTo kończy się false
        arriveHook = null;
        if (hook) hook(false);
    }

    // --- API dla żartów (spec v3.2 §4) ----------------------------------------------------------
    // Moduł żartów (pet-jokes.js) „zajmuje” towarzysza: spacer i dymki stoją, ruchem steruje runTo.

    function setClaimed(on) { el.classList.toggle('pet-companion--claimed', on); }

    function apiReady() {
        return mode === 'walk' && !claim && !!pet && !!rig && !pet.asleep && !held && !el.hidden &&
            bubble.hidden && document.visibilityState !== 'hidden' && !reducedMotion();
    }

    function rectNow() {
        var r = el.getBoundingClientRect();
        return { x: r.left, y: r.top, w: r.width, h: r.height };
    }

    function faceDir(dir) { el.classList.toggle('pet-companion--flipped', dir === 'left'); }

    /** Zajmuje pupila (null, gdy zajęty albo nie pora); zwraca release(). onBreak: chwycenie, sen, ukrycie. */
    function claimPet(onBreak) {
        if (!apiReady()) return null;
        var c = { onBreak: onBreak || null };
        claim = c;
        setClaimed(true);
        stopWalk();
        clearTimeout(timers.walk);
        timers.walk = 0;
        sitting = false;
        syncPose();
        return function release() {
            if (claim !== c) return;
            claim = null;
            setClaimed(false);
            stopWalk();
            if (walkAllowed()) scheduleWalk(rand(PAUSE_MIN, PAUSE_MAX));
        };
    }

    /** Przerwanie przez towarzysza (sen, ukrycie, inny pupil, karta w tle): runTo kończy się false, onBreak woła się raz. */
    function breakClaim() {
        if (!claim) return;
        var c = claim;
        claim = null;
        setClaimed(false);
        stopWalk();
        if (c.onBreak) {
            try { c.onBreak(); } catch (e) { /* żart sprząta po sobie sam */ }
        }
        updateWalk();
    }

    /** Biegnie do (x, y) — tylko podczas claim. allowOutside zdejmuje ograniczenie do obszaru spaceru. */
    function runTo(x, y, opts) {
        if (!claim || !pos || el.hidden) return Promise.resolve(false);
        opts = opts || {};
        stopWalk();
        var target = opts.allowOutside ? { x: Math.round(x), y: Math.round(y) } : clampTo(area(), { x: x, y: y });
        var dist = Math.sqrt(Math.pow(target.x - pos.x, 2) + Math.pow(target.y - pos.y, 2));
        if (dist < 2) {
            if (opts.face) faceDir(opts.face);
            return Promise.resolve(true);
        }
        return new Promise(function (resolve) {
            arriveHook = function (ok) {
                if (ok && opts.face) faceDir(opts.face);
                resolve(ok);
            };
            startMove(target, true);
        });
    }

    // --- nie zasłaniaj CTA ----------------------------------------------------------------------

    function updateLift() {
        if (el.hidden) return;
        // Mobilny panel koszyka oferty leży pod towarzyszem — na czas otwarcia chowamy się
        var tucked = false;
        var tuckNodes = document.querySelectorAll(TUCK_WHEN);
        for (var t = 0; t < tuckNodes.length; t++) if (isVisible(tuckNodes[t])) { tucked = true; break; }
        el.classList.toggle('pet-companion--tucked', tucked);

        // Swobodna pozycja omija paski przez obszar (area/maxYAt); róg trybu sit — przez podniesienie
        if (isFree()) { keepInArea(); return; }

        var cur = parseFloat(el.style.getPropertyValue('--pet-companion-lift')) || 0;
        var r = el.getBoundingClientRect();
        var vh = window.innerHeight;
        var baseBottom = vh - r.bottom - cur;          // odstęp od dołu bez podniesienia
        var bottomY = vh - baseBottom, topY = bottomY - r.height;
        var need = 0;
        var nodes = document.querySelectorAll(OBSTACLES);
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            if (!isVisible(n)) continue;
            var o = n.getBoundingClientRect();
            if (o.right <= r.left || o.left >= r.right) continue;  // nie nachodzi w poziomie
            if (o.top >= bottomY || o.bottom <= topY) continue;    // nie nachodzi w pionie
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
        var nodes = document.querySelectorAll(OBSTACLES + ', ' + TUCK_WHEN + ', .cart-sidebar, .cart-mobile-overlay');
        // klasy/style: pokazanie paska, otwarcie koszyka; rozmiar: koszyk rośnie po dodaniu produktów
        var mo = window.MutationObserver ? new MutationObserver(scheduleLift) : null;
        var ro = window.ResizeObserver ? new ResizeObserver(scheduleLift) : null;
        for (var i = 0; i < nodes.length; i++) {
            if (mo) mo.observe(nodes[i], { attributes: true, attributeFilter: ['class', 'style', 'hidden'] });
            if (ro) ro.observe(nodes[i]);
        }
        // Zwinięcie/rozwinięcie sidebara zmienia szerokość obszaru treści — spacerujący zostaje nad treścią
        var wrap = document.querySelector('.main-wrapper');
        if (ro && wrap && mode === 'walk') ro.observe(wrap);
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

    // Sprawy zamkniętych dymków (do końca sesji karty) — prywatne okno: lista w pamięci strony
    var closedMem = [];

    function closedTopics() {
        try {
            var list = JSON.parse(sessionStorage.getItem(closedKey) || '[]');
            return Array.isArray(list) ? list : [];
        } catch (e) { return closedMem; }
    }

    function topicClosed(topic) {
        return !!topic && closedTopics().indexOf(topic) >= 0;
    }

    function closeTopic(topic) {
        if (!topic || topicClosed(topic)) return;
        var list = closedTopics().concat([topic]).slice(-30);
        closedMem = list;
        try { sessionStorage.setItem(closedKey, JSON.stringify(list)); } catch (e) { /* prywatne okno / pełny storage */ }
    }

    // Dymek opieki: tekst + cel linku wg potrzeby (spec v3 §3.1: dymek towarzysza → miejsce właściwe dla
    // potrzeby): głód / smutek / brud / nuda → domek z panelem pupila; choroba → Izba przyjęć (spec v3.1 §5);
    // jajka → hol szpitala (recepcja; pielęgniarka wskaże salę). `topic` = sprawa (zamknięcie wycisza tylko ją).
    function careBubble(state) {
        var m = pet && pet.mood;
        var house = { href: houseUrl + '?pupil=' + encodeURIComponent(pet.id), label: 'Do domku' };
        var hospital = { href: hospitalUrl, label: 'Do szpitala' };
        var ward = { href: wardUrl, label: 'Do szpitala' };
        if (m === 'krytyczny' || m === 'chory') return { text: 'Źle się czuję…', link: ward, topic: 'chory:' + pet.id };
        if (m === 'glodny') return { text: 'Jestem głodny!', link: house, topic: 'glodny:' + pet.id };
        if (m === 'smutny' || m === 'znudzony') return { text: 'Pobaw się ze mną!', link: house, topic: 'zabawa:' + pet.id };
        if (m === 'brudny') return { text: 'Umyj mnie!', link: house, topic: 'brudny:' + pet.id };
        var eggs = state.eggs || [];
        for (var i = 0; i < eggs.length; i++) if (eggs[i].ready) return { text: 'Jajko gotowe!', link: hospital, topic: 'jajko-gotowe' };
        if (state.eggs_available && state.eggs_available.length) return { text: 'Czeka na Ciebie jajko!', link: hospital, topic: 'jajko-recepcja' };
        return null;   // opieki potrzebuje inny pupil — kropka w nawigacji to pokazuje, towarzysz nie mówi za niego
    }

    function maybeCareBubble(state) {
        var care = pet && !pet.asleep && state && state.needs_care ? careBubble(state) : null;
        if (mode === 'sit') {
            // Strona oferty: bez dymka z linkiem — tylko plakietka „!” (sprawa zamknięta wcześniej → bez niej)
            setBadge(!!care && !topicClosed(care.topic));
            return;
        }
        if (!care || !bubble.hidden || held) return;
        if (topicClosed(care.topic) || !bubbleAllowed()) return;
        markBubble();
        showBubble(care.text, { ms: BUBBLE_CARE_MS, link: care.link, topic: care.topic });
    }

    /** Tryb sit: mała plakietka na pupilu („potrzebuje opieki”), bez linku i bez klikania. */
    function setBadge(on) {
        if (on && !badge) {
            badge = document.createElement('span');
            badge.className = 'pet-companion__badge';
            badge.setAttribute('aria-hidden', 'true');
            badge.textContent = '!';
            el.appendChild(badge);
        }
        if (badge) badge.hidden = !on;
        if (hit && pet) hit.setAttribute('aria-label', pet.asleep ? 'Pupil śpi' : on ? 'Pogłaszcz pupila (potrzebuje opieki)' : 'Pogłaszcz pupila');
    }

    function showBubble(text, opts) {
        if (claim) return;                   // żart trwa — dymki czekają
        clearTimeout(timers.bubble);
        clearTimeout(timers.bubbleFade);
        bubbleTopic = opts.topic || null;
        bubble.innerHTML = '';
        var span = document.createElement('span');
        span.className = 'pet-companion__bubble-text';
        span.textContent = text;
        bubble.appendChild(span);
        if (opts.link) {
            // {href, label} z careBubble; true = mapa świata (cel bez konkretnej potrzeby)
            var target = opts.link === true ? { href: homeUrl, label: 'Do świata' } : opts.link;
            var a = document.createElement('a');
            a.className = 'pet-companion__bubble-link';
            a.href = target.href;
            a.textContent = target.label;
            bubble.appendChild(a);
        }
        // × — cel 44 px (widoczne kółko mniejsze); zamknięcie wycisza tę sprawę do końca sesji
        var x = document.createElement('button');
        x.type = 'button';
        x.className = 'pet-companion__bubble-close';
        x.setAttribute('aria-label', 'Zamknij dymek');
        bubble.appendChild(x);
        // Mówiąc stoi: dymek (i link w nim) nie odjeżdża razem z pupilem; spacer wraca po dymku
        if (walking) {
            stopWalk();
            scheduleWalk(opts.ms + 1000);
        }
        bubble.hidden = false;
        placeBubble();
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

    /**
     * Dymek nad pupilem (pod nim, gdy u góry brakuje miejsca), otwarty w stronę środka ekranu i przesunięty
     * tak, żeby cały mieścił się w oknie; ogonek celuje w pupila (--pet-companion-tail).
     */
    function placeBubble() {
        if (bubble.hidden || el.hidden) return;
        var vp = viewport();
        var r = el.getBoundingClientRect();
        var bw = bubble.offsetWidth, bh = bubble.offsetHeight;
        var cx = r.left + r.width / 2;
        var toLeft = (mode === 'sit' && !isFree()) || cx > vp.w / 2;
        var left = toLeft ? r.right - bw : r.left;
        left = Math.max(BUBBLE_MARGIN, Math.min(vp.w - BUBBLE_MARGIN - bw, left));
        var a = area();
        var minTop = Math.max(BUBBLE_MARGIN, a.minY - EDGE + BUBBLE_MARGIN);
        var top = r.top - BUBBLE_GAP - bh;
        var below = top < minTop && r.bottom + BUBBLE_GAP + bh <= vp.h - BUBBLE_MARGIN;
        if (below) top = r.bottom + BUBBLE_GAP;
        bubble.style.left = Math.round(left - r.left) + 'px';
        bubble.style.bottom = Math.round(r.bottom - (top + bh)) + 'px';
        var tail = Math.max(12, Math.min(bw - 22, cx - left - 5));
        bubble.style.setProperty('--pet-companion-tail', Math.round(tail) + 'px');
        el.classList.toggle('pet-companion--bubble-below', below);
    }

    // Klik w dymek (poza linkiem) albo × = zamknięcie: ta sprawa nie wraca do końca sesji
    bubble.addEventListener('click', function (e) {
        if (e.target && e.target.closest && e.target.closest('.pet-companion__bubble-link')) return;
        closeTopic(bubbleTopic);
        hideBubble(false);
    });

    // --- chwytanie i przenoszenie ---------------------------------------------------------------
    // Pointer Events dla myszy, dotyku i pióra. Mysz: przeciągnięcie > DRAG_PX. Dotyk: przytrzymanie HOLD_MS
    // (wcześniejszy ruch palca oddaje gest przeglądarce — przewijanie strony działa normalnie); od podniesienia
    // touchmove ma preventDefault, więc strona nie jedzie pod palcem. Zdarzenia tylko na #petCompanionHit.

    hit.addEventListener('pointerdown', function (e) {
        if (!pet || !rig || drag) return;
        if (e.pointerType === 'mouse' && e.button !== 0) return;
        // ox/oy: miejsce chwytu na pupilu — po podniesieniu ten punkt zostaje pod kursorem/palcem
        var r = el.getBoundingClientRect();
        drag = { id: e.pointerId, type: e.pointerType, sx: e.clientX, sy: e.clientY, lx: e.clientX, ly: e.clientY,
                 ox: e.clientX - r.left, oy: e.clientY - r.top, active: false, hold: 0, a: null, fx: 0 };
        try { hit.setPointerCapture(e.pointerId); } catch (err) { /* stary silnik — działa bez przechwycenia */ }
        if (e.pointerType === 'mouse') {
            e.preventDefault();          // bez zaznaczania tekstu w trakcie przeciągania (click i tak przychodzi)
        } else {
            drag.hold = setTimeout(function () { if (drag && !drag.active) beginDrag(); }, HOLD_MS);
        }
    });

    hit.addEventListener('pointermove', function (e) {
        if (!drag || e.pointerId !== drag.id) return;
        drag.lx = e.clientX;
        drag.ly = e.clientY;
        if (!drag.active) {
            var dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
            var d = Math.sqrt(dx * dx + dy * dy);
            if (drag.type === 'mouse') {
                if (d <= DRAG_PX) return;
                beginDrag();
            } else {
                if (d > TOUCH_SLOP) cancelDrag();   // palec ruszył przed przytrzymaniem — to przewijanie
                return;
            }
        }
        moveDrag(e.clientX, e.clientY);
    });

    hit.addEventListener('pointerup', function (e) {
        if (drag && e.pointerId === drag.id) endDrag();
    });

    hit.addEventListener('pointercancel', function (e) {
        if (drag && e.pointerId === drag.id) endDrag();   // podniesiony zostaje tam, gdzie był; inaczej — przewijanie
    });

    // Przechwycenie zgubione bez pointerup (np. element przemalowany) — gest się kończy, nic nie wisi
    hit.addEventListener('lostpointercapture', function (e) {
        if (drag && e.pointerId === drag.id) cancelDrag();
    });

    // Od podniesienia palec przesuwa pupila, nie stronę (listener nie-pasywny tylko na pupilu)
    hit.addEventListener('touchmove', function (e) {
        if (drag && drag.active && e.cancelable) e.preventDefault();
    }, { passive: false });

    // Długie przytrzymanie na Androidzie otwiera menu kontekstowe — przy chwytaniu dotykiem go nie chcemy
    hit.addEventListener('contextmenu', function (e) {
        if ((drag && drag.type !== 'mouse') || held) e.preventDefault();
    });

    function beginDrag() {
        clearTimeout(drag.hold);
        drag.hold = 0;
        drag.active = true;
        held = true;
        clickGuardUntil = Infinity;        // do upuszczenia żaden „klik" nie jest pat
        stopWalk();
        clearTimeout(timers.walk);
        timers.walk = 0;
        hideBubble(true);
        var r = el.getBoundingClientRect();
        if (!isFree()) {                   // róg trybu sit → swobodna pozycja w tym samym miejscu
            setFree(true);
            setPos(Math.round(r.left), Math.round(r.top), false);
        }
        drag.a = area();
        drag.fx = pos ? pos.x : r.left;
        el.classList.add('pet-companion--held');
        syncPose();
        if (drag.type !== 'mouse') haptic();
        // Od razu pod kursor/palec: szybki ruch myszy przekracza próg o więcej niż 6 px, a idący pupil
        // mógł się przesunąć w trakcie przytrzymania
        moveDrag(drag.lx, drag.ly);
    }

    function moveDrag(cx, cy) {
        var p = clampTo(drag.a, { x: cx - drag.ox, y: cy - drag.oy });
        var dxf = p.x - drag.fx;           // patrzy w stronę przenoszenia (z progiem — bez migotania)
        if (dxf > FACE_PX) { el.classList.remove('pet-companion--flipped'); drag.fx = p.x; }
        else if (dxf < -FACE_PX) { el.classList.add('pet-companion--flipped'); drag.fx = p.x; }
        el.style.left = p.x + 'px';
        el.style.top = p.y + 'px';
        pos = p;
    }

    /** Puszczenie: tap/klik bez podniesienia przechodzi dalej do `click` (pat); po przeniesieniu — zostaje. */
    function endDrag() {
        var d = drag;
        drag = null;
        if (!d) return;
        clearTimeout(d.hold);
        if (!d.active) return;
        try {
            if (hit.hasPointerCapture && hit.hasPointerCapture(d.id)) hit.releasePointerCapture(d.id);
        } catch (e) { /* ignoruj */ }
        held = false;
        el.classList.remove('pet-companion--held');
        clickGuardUntil = Date.now() + CLICK_GUARD_MS;
        savePos();
        if (mode === 'walk') {
            sitting = false;
            syncPose();
            if (walkAllowed()) scheduleWalk(rand(DROP_PAUSE_MIN, DROP_PAUSE_MAX));   // po chwili rusza stąd
        }
    }

    /** Przerwanie bez upuszczania (ukrycie pupila, karta w tle, przewijanie zamiast przytrzymania). */
    function cancelDrag() {
        if (!drag) return;
        if (drag.active) { endDrag(); return; }
        clearTimeout(drag.hold);
        drag = null;
    }

    // --- pat pat --------------------------------------------------------------------------------

    function flushPat() {
        clearTimeout(timers.pat);
        var count = patCount, id = patPetId;
        patCount = 0;
        disarmLeave();
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

    // Wyjście ze strony w trakcie paczkowania — wyślij resztę z keepalive (żądanie przeżyje rozładowanie strony)
    function flushPatOnExit() {
        disarmLeave();
        if (!patCount || patPetId == null) return;
        var count = patCount, id = patPetId;
        patCount = 0;
        clearTimeout(timers.pat);
        try {
            window.PetsApi.post('/' + id + '/akcja', { action: 'pat', count: count }, { keepalive: true }).then(noop, noop);
        } catch (e) { /* ignoruj */ }
        window.PetsState.invalidate(userId);       // odpowiedź nie wróci — następna strona pobierze świeży stan
    }

    // beforeunload tylko, gdy paczka czeka: żądanie startuje przed ładowaniem nowej strony (pagehide
    // bywa za późno), a stały nasłuch psułby bfcache w Firefoksie
    var leaveArmed = false;

    function armLeave() {
        if (leaveArmed) return;
        leaveArmed = true;
        window.addEventListener('beforeunload', flushPatOnExit);
    }

    function disarmLeave() {
        if (!leaveArmed) return;
        leaveArmed = false;
        window.removeEventListener('beforeunload', flushPatOnExit);
    }

    hit.addEventListener('click', function () {
        if (!pet || !rig) return;
        if (held || Date.now() < clickGuardUntil) return;   // koniec przeciągania — to nie pat
        if (pet.asleep) {
            showBubble('Śpi… zzz', { ms: BUBBLE_SLEEP_MS });
            return;
        }
        haptic();
        // spec v3 §5: pat pat z dłonią (rig.pat); starszy rig — dawna animacja
        (typeof rig.pat === 'function' ? rig.pat() : rig.playAction('pat')).then(noop, noop);
        if (walking) {
            stopWalk();
            scheduleWalk(rand(PAUSE_MIN, PAUSE_MAX));
        }
        if (patPetId !== pet.id) { flushPat(); patPetId = pet.id; }
        patCount++;
        armLeave();
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
        // Na stronie domku wszystkie pupile są na wierzchu — towarzysz z linkiem „Do świata" byłby dublem
        if (document.getElementById('petsApp')) return;
        if (mode === 'walk') {
            window.PetCompanionApi = { ready: apiReady, rect: rectNow, claim: claimPet, runTo: runTo, face: faceDir };
        }
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
                updateLift();              // swobodna pozycja: z powrotem w obszarze; róg: omijanie pasków
                placeBubble();
            });
        });
        window.addEventListener('scroll', scheduleLift, { passive: true });
        window.addEventListener('scroll', function () {
            clearTimeout(scrollCheckTimer);
            scrollCheckTimer = setTimeout(checkStandingSpot, 250);
        }, { passive: true });
        watchObstacles();
        setTimeout(checkStandingSpot, 1500);   // pozycja odtworzona z poprzedniej strony mogła wypaść na przycisku

        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'hidden') {
                breakClaim();
                cancelDrag();
                flushPatOnExit();
                savePos();
                stopWalk();
            } else if (started) {
                fetchState();    // długo otwarta karta: cache wygasł → świeży stan (sen, dymek)
                updateWalk();
            }
        });
        window.addEventListener('pagehide', function () {
            savePos();               // przed flushem — miejsce w pół drogi, zanim cokolwiek zatrzyma spacer
            flushPatOnExit();
        });

        // Zmiana ustawienia ruchu w trakcie (system / DevTools): ograniczony — siada i stoi w miejscu
        if (window.matchMedia) {
            var mq = window.matchMedia('(prefers-reduced-motion: reduce)');
            var onMq = function () { if (pet) updateWalk(); };
            if (mq.addEventListener) mq.addEventListener('change', onMq);
            else if (mq.addListener) mq.addListener(onMq);
        }
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else boot();
})();
