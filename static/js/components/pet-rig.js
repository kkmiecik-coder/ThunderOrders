/**
 * PetRig — rig SVG pupila (jedna struktura warstw dla wszystkich gatunków).
 *
 * Wymaga: static/js/pet/species.js (window.PetSpecies) + static/css/components/pet-rig.css.
 *
 * API (kontrakt dla pets.js / pet-card.js / towarzysza / świata):
 *   PetRig.mount(container, {species, stage, stars, mood, asleep, size, need, pose, idle}) -> rig
 *     rig.update(opts) · rig.gesture(name) · rig.setStars(n) · rig.destroy() · rig.el
 *     rig.playAction(action, {variant}) -> Promise
 *       - bez variant: dotychczasowe akcje (feed|play|wash|heal|pat|wake|celebrate|hatch, 0,9–2 s),
 *       - z variant (PetRig.VARIANTS): 9 dłuższych sekwencji z własnymi rekwizytami (3,4–3,8 s;
 *         ograniczony ruch: ≤ 0,9 s i statyczne rekwizyty). Nieznany wariant = pierwszy z listy.
 *     rig.setNeed(need) — wygląd potrzeby (PetRig.NEEDS; null = jak dawniej, z mood/asleep)
 *     rig.setPose(pose) — PetRig.POSES: stand | sit | lie | bed (łóżeczko szpitalne z kołderką)
 *     rig.pat() -> Promise — otwarta dłoń wjeżdża z boku i klepie po głowie 3 razy, przy każdym
 *       klepnięciu chmurka „PAT” (~1,5 s); kolejne wywołanie w trakcie
 *       odświeża animację i zwraca TEN SAM Promise.
 *   PetRig.needOf(pet) -> need — z pet_dict (szpital > krytyczny > chory > sen > głód > brud > smutek > nuda)
 *   PetRig.mountEgg(container, {pct, boosted, ready, size, skin}) -> egg
 *     egg.update(opts) · egg.hatch() -> Promise · egg.destroy() · egg.el
 *     skin: indeks 0–4 albo nazwa z PetRig.EGG_SKINS (pęknięcia i światło wspólne)
 *   PetRig.mountMemorial(container, {species, size, stage, lit}) -> rig
 *
 * Stany (klasy na roocie): is-idle is-sleep is-sad is-sick is-critical (z nastroju/snu albo z need)
 *   oraz is-eat is-play is-wash is-pat is-celebrate is-hatch is-heal is-wake (akcje),
 *   is-handpat (dłoń), is-v + is-v-<feed|play|wash> + is-v-<wariant> (warianty),
 *   need-<need>, pose-<pose>, pose-off (poza zawieszona na czas akcji).
 * Gesty: g-jump g-blink g-sway g-spin g-wave g-dance g-flip (zdejmowane po animationend).
 * Ruch ograniczony: @media (prefers-reduced-motion) albo klasa .pet-rig-rm na <html>.
 */
(function () {
    'use strict';

    if (window.PetRig) return;   // plik ładuje się na kilku stronach (include towarzysza + skrypty strony)
    var STAGES = ['maluch', 'dziecko', 'dorosly'];
    var SIZES = ['card', 'mini', 'companion'];
    var MOOD_STATE = {
        szczesliwy: 'idle', glodny: 'idle', znudzony: 'idle', brudny: 'idle',
        smutny: 'sad', chory: 'sick', krytyczny: 'critical'
    };
    var BASE_STATES = ['is-idle', 'is-sleep', 'is-sad', 'is-sick', 'is-critical'];
    // Gesty dostępne w stadium (spec §2.7: maluch 3, dziecko 5, dorosły 7).
    var GESTURES = {
        maluch: ['jump', 'blink', 'sway'],
        dziecko: ['jump', 'blink', 'sway', 'spin', 'wave'],
        dorosly: ['jump', 'blink', 'sway', 'spin', 'wave', 'dance', 'flip']
    };
    // akcja -> [klasa stanu, czas w ms]
    var ACTIONS = {
        feed: ['is-eat', 1800], play: ['is-play', 2000], wash: ['is-wash', 1800],
        heal: ['is-heal', 1600], pat: ['is-pat', 900], wake: ['is-wake', 1400],
        celebrate: ['is-celebrate', 1800], hatch: ['is-hatch', 1400]
    };
    // Potrzeby (wygląd w pokoju, spec v3 §6.1) i pozy — kontrakt dla świata i widgetu.
    var NEEDS = ['happy', 'hungry', 'dirty', 'sad', 'bored', 'sick', 'critical', 'sleep'];
    var POSES = ['stand', 'sit', 'lie', 'bed'];
    // need -> nastrój „wewnętrzny" (steruje istniejącymi stanami is-* i dymkami data-mood)
    var NEED_MOOD = {
        happy: 'szczesliwy', hungry: 'glodny', dirty: 'brudny', sad: 'smutny', bored: 'znudzony',
        sick: 'chory', critical: 'krytyczny', sleep: 'szczesliwy'
    };
    var MOOD_NEED = { glodny: 'hungry', brudny: 'dirty', smutny: 'sad', znudzony: 'bored' };
    // Warianty akcji — identyczne z backendem (modules/pets, spec v3 §5).
    var VARIANTS = {
        feed: ['miska', 'jablko', 'ciastko'],
        play: ['pilka', 'wloczka', 'banki'],
        wash: ['kapiel', 'prysznic', 'gabka']
    };
    var VARIANT_MS = {
        miska: 3400, jablko: 3600, ciastko: 3400,
        pilka: 3600, wloczka: 3600, banki: 3600,
        kapiel: 3800, prysznic: 3600, gabka: 3600
    };
    var HAND_MS = 1500;
    var RM_MS = 800;   // ograniczony ruch: ≤ 0,9 s z zapasem na opóźnienia timerów
    var EGG_SKINS = ['kropki', 'niebo', 'laczka', 'paski', 'laty'];
    var EYE_Y = 95;
    var INK = '#3B2A3A';
    var uidSeq = 0;

    function reducedMotion() {
        if (document.documentElement.classList.contains('pet-rig-rm')) return true;
        return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

    function sym(s) {
        return s + '<g transform="matrix(-1 0 0 1 200 0)">' + s + '</g>';
    }

    function g(cls, inner, extra) {
        return '<g class="' + cls + '"' + (extra || '') + '>' + (inner || '') + '</g>';
    }

    function origin(o) {
        return ' style="transform-origin:' + o + '"';
    }

    // --- Części wspólne (gatunek może nadpisać w parts) -------------------------------------

    var DEF = {
        skull: '<ellipse class="f-b o" cx="100" cy="88" rx="51" ry="44"/>',
        nose: '<ellipse class="f-k" cx="100" cy="101.5" rx="3" ry="2.1"/>',
        body: '<ellipse class="f-b o" cx="100" cy="153" rx="34" ry="29"/>' +
            '<ellipse class="f-l" cx="100" cy="158" rx="21" ry="18"/>',
        feet: '<ellipse class="f-b o" cx="83" cy="178" rx="11" ry="7"/><ellipse class="f-b o" cx="117" cy="178" rx="11" ry="7"/>' +
            '<ellipse class="f-l" cx="82" cy="179" rx="5" ry="3"/><ellipse class="f-l" cx="118" cy="179" rx="5" ry="3"/>',
        arm: '<ellipse class="f-b o" cx="73" cy="152" rx="8" ry="11.5" transform="rotate(24 73 152)"/>',
        mouth: {
            smile: '<path class="s-k" d="M93.5 104.5Q96.8 108.6 100 105Q103.2 108.6 106.5 104.5"/>',
            open: '<path fill="#7A2E3E" stroke="var(--rig-ink)" stroke-width="1.6" stroke-linejoin="round" d="M93.5 104Q100 118 106.5 104Z"/>' +
                '<path fill="#F48FA8" d="M96.2 110.4Q100 107.6 103.8 110.4Q100 115 96.2 110.4Z"/>',
            frown: '<path class="s-k" d="M94 109.5Q100 103.5 106 109.5"/>'
        },
        cheeks: sym('<ellipse class="f-c ck" cx="64" cy="108" rx="8.5" ry="5.2"/>'),
        tear: '<path class="rig-tear" d="M128.5 101q-3.6 5.4 0 7.8q3.6-2.4 0-7.8z"/>',
        pale: '<ellipse class="rig-pale" cx="100" cy="86" rx="49" ry="42"/>',
        shine: '<ellipse class="rig-shine" cx="76" cy="62" rx="13" ry="7" transform="rotate(-28 76 62)"/>',
        headDirt: '<g class="rig-dirt"><ellipse cx="128" cy="68" rx="4.5" ry="3.2"/><circle cx="136" cy="76" r="1.8"/></g>',
        bodyDirt: '<g class="rig-dirt"><ellipse cx="87" cy="161" rx="5.5" ry="3.8"/><ellipse cx="115" cy="150" rx="3.6" ry="2.6"/><circle cx="109" cy="170" r="2.3"/></g>'
    };

    function eye(x, e) {
        var y = EYE_Y;
        e = e || {};
        var s = '<g class="rig-eye"' + origin(x + 'px ' + y + 'px') + '><g class="e-open">' +
            '<ellipse class="f-k" cx="' + x + '" cy="' + y + '" rx="7.2" ry="8.8"/>';
        if (e.pupil) s += '<ellipse fill="#161616" cx="' + x + '" cy="' + (y + 0.6) + '" rx="2.3" ry="6.3"/>';
        var hy = e.lid ? 3.4 : -3.4;
        s += '<circle class="f-w" cx="' + (x + 2.4) + '" cy="' + (y + hy) + '" r="' + (e.lid ? 2 : 2.9) + '"/>' +
            '<circle class="f-w" cx="' + (x - (e.lid ? 3 : 2.6)) + '" cy="' + (y + (e.lid ? 5.6 : 3.7)) + '" r="1.4"/>';
        if (e.lid) {
            // Półprzymknięta powieka = górny wycinek oka w kolorze sierści, zewnętrzny kącik niżej (senność).
            var out = x < 100 ? -1 : 1;
            var yl = y + (out < 0 ? 1 : -1.6), yr = y + (out < 0 ? -1.6 : 1);
            s += '<path class="lid" d="M' + (x - 7.8) + ' ' + yl + 'A7.6 9.2 0 0 1 ' + (x + 7.8) + ' ' + yr +
                'Q' + x + ' ' + (y + 0.8) + ' ' + (x - 7.8) + ' ' + yl + 'Z"/>' +
                '<path class="lid-edge" d="M' + (x - 8.4) + ' ' + (yl + 0.1) + 'Q' + x + ' ' + (y + 0.9) + ' ' + (x + 8.4) + ' ' + (yr + 0.1) + '"/>';
        }
        s += '</g><path class="e-closed s-k" d="M' + (x - 7) + ' ' + (y + 1) + 'Q' + x + ' ' + (y + 6.5) + ' ' + (x + 7) + ' ' + (y + 1) + '"/>' +
            '<path class="e-happy s-k" d="M' + (x - 7) + ' ' + (y + 2.5) + 'Q' + x + ' ' + (y - 6) + ' ' + (x + 7) + ' ' + (y + 2.5) + '"/></g>';
        return s;
    }

    function starPath(cx, cy, r) {
        var pts = [];
        for (var i = 0; i < 10; i++) {
            var a = -Math.PI / 2 + i * Math.PI / 5;
            var rr = i % 2 ? r * 0.46 : r;
            pts.push((cx + Math.cos(a) * rr).toFixed(1) + ' ' + (cy + Math.sin(a) * rr).toFixed(1));
        }
        return 'M' + pts.join('L') + 'Z';
    }

    function sparkle(x, y, r, cls) {
        var k = r * 0.28;
        return '<path class="' + cls + '" d="M' + x + ' ' + (y - r) + 'L' + (x + k) + ' ' + (y - k) + 'L' + (x + r) + ' ' + y +
            'L' + (x + k) + ' ' + (y + k) + 'L' + x + ' ' + (y + r) + 'L' + (x - k) + ' ' + (y + k) + 'L' + (x - r) + ' ' + y +
            'L' + (x - k) + ' ' + (y - k) + 'Z"/>';
    }

    var CONFETTI_COLORS = ['#F093FB', '#F5576C', '#FFD166', '#7BD3EA', '#A0E7A0', '#C9A7FF'];

    function confetti(cx, cy, n) {
        var s = '';
        for (var i = 0; i < n; i++) {
            var a = (i / n) * Math.PI * 2 + (i % 2 ? 0.2 : -0.1);
            var d = 52 + (i % 3) * 16;
            var st = ' style="--x:' + Math.round(Math.cos(a) * d) + 'px;--y:' + Math.round(Math.sin(a) * d - 18) +
                'px;--r:' + (i * 47 % 360) + 'deg;animation-delay:' + (i % 4) * 0.03 + 's" fill="' + CONFETTI_COLORS[i % 6] + '"';
            s += i % 3 === 0
                ? '<circle cx="' + cx + '" cy="' + cy + '" r="2.6"' + st + '/>'
                : '<rect x="' + (cx - 2) + '" y="' + (cy - 3.5) + '" width="4" height="7" rx="1"' + st + '/>';
        }
        return s;
    }

    var HEART = 'c-3-5-11-4-11 2c0 5 6 9 11 13c5-4 11-8 11-13c0-6-8-7-11-2z';
    var SMALL_HEART = 'c-1.4-2.4-5.2-1.9-5.2 1c0 2.4 2.8 4.2 5.2 6.1c2.4-1.9 5.2-3.7 5.2-6.1c0-2.9-3.8-3.4-5.2-1z';

    // Rekwizyty akcji (poza postacią, w układzie sceny).
    var FX_BACK = '<circle class="fx-glow" cx="100" cy="120" r="70"/>';
    var FX =
        g('fx-bowl', '<path fill="#FF9EBF" stroke="#E0688F" stroke-width="2" stroke-linejoin="round" d="M68 176h64c-2 12-13 19-32 19s-30-7-32-19z"/>' +
            '<ellipse cx="100" cy="176" rx="32" ry="5.5" fill="#E0688F"/>' +
            '<g class="fx-kib"><circle cx="89" cy="173" r="4" fill="#B9774B"/><circle cx="100" cy="171" r="4.4" fill="#C98A58"/>' +
            '<circle cx="111" cy="173" r="4" fill="#B9774B"/><circle cx="95" cy="176" r="3.6" fill="#A66A40"/><circle cx="106" cy="176" r="3.6" fill="#C98A58"/></g>' +
            '<g class="fx-crumbs"><circle cx="92" cy="128" r="2" fill="#C98A58"/><circle cx="108" cy="126" r="1.7" fill="#B9774B"/><circle cx="100" cy="124" r="1.5" fill="#C98A58"/></g>') +
        g('fx-ball', '<g class="fx-ball-in"><circle r="10" fill="#FF6B6B" stroke="#D94F5C" stroke-width="1.8"/>' +
            '<path fill="#FFE08A" d="M-10 0a10 10 0 0 0 20 0c-4 3-16 3-20 0z"/><path fill="#fff" d="M-3-9.5a10 10 0 0 1 6 0l-1 19a10 10 0 0 1-4 0z"/></g>', ' transform="translate(-40 170)"') +
        g('fx-bubbles',
            [[62, 150, 7], [140, 146, 9], [78, 120, 5], [128, 116, 6], [100, 136, 4.5], [52, 128, 5.5], [150, 126, 4.5]].map(function (b, i) {
                return '<circle cx="' + b[0] + '" cy="' + b[1] + '" r="' + b[2] + '" style="animation-delay:' + (i * 0.17).toFixed(2) + 's"/>';
            }).join('')) +
        g('fx-plus', [[56, 150], [146, 140], [72, 110], [132, 104], [100, 70]].map(function (p, i) {
            return '<path d="M' + (p[0] - 2) + ' ' + (p[1] - 7) + 'h4v5h5v4h-5v5h-4v-5h-5v-4h5z" style="animation-delay:' + (i * 0.18).toFixed(2) + 's"/>';
        }).join('')) +
        g('fx-spark', sparkle(40, 70, 9, 'sp2') + sparkle(160, 60, 7, 'sp2') + sparkle(30, 140, 6, 'sp2') +
            sparkle(170, 130, 8, 'sp2') + sparkle(100, 22, 7, 'sp2')) +
        g('fx-conf', confetti(100, 96, 16));

    var STATUS =
        g('st-zzz', '<text x="134" y="62">z</text><text x="146" y="47">z</text><text x="159" y="31">Z</text>') +
        g('st-cloud', '<path d="M139 46a8.5 8.5 0 0 1 7-11.5a12 12 0 0 1 22.5 1.5a8 8 0 0 1 4 14.5h-29a7 7 0 0 1-4.5-4.5z"/>' +
            '<g class="st-rain"><path d="M148 55l-2 6"/><path d="M157 55l-2 6"/><path d="M166 55l-2 6"/></g>') +
        g('st-hearts', '<path d="M100 38' + HEART + '"/><path d="M70 52' + HEART + '"/><path d="M132 50' + HEART + '"/>') +
        g('st-think', '<circle cx="134" cy="60" r="2.6"/><circle cx="141" cy="51" r="3.8"/><ellipse cx="160" cy="34" rx="21" ry="15.5"/>' +
            '<g class="st-food"><path fill="#FF9EBF" d="M148 34h24c-1 7-6 10-12 10s-11-3-12-10z"/><circle cx="155" cy="32" r="3" fill="#B9774B"/>' +
            '<circle cx="161" cy="30.5" r="3.2" fill="#C98A58"/><circle cx="167" cy="32" r="3" fill="#B9774B"/></g>' +
            '<g class="st-dots"><circle cx="151" cy="35" r="2.6"/><circle cx="160" cy="35" r="2.6"/><circle cx="169" cy="35" r="2.6"/></g>') +
        g('st-stink', '<path d="M44 156q-5-6 0-12t0-12"/><path d="M156 156q5-6 0-12t0-12"/>') +
        // Potrzeby: muszka krążąca wokół brudnego, „burczenie" brzuszka
        g('nd-fly', '<g class="nd-fly-in"><ellipse class="nd-wing" cx="-2.6" cy="-3.4" rx="3.4" ry="2.2"/>' +
            '<ellipse class="nd-wing nd-wing2" cx="2.6" cy="-3.6" rx="3.4" ry="2.2"/><circle class="nd-fly-body" r="2.8"/></g>') +
        g('nd-rumble', '<path d="M58 146q-4 4 0 8M53 143q-6 7 0 14"/><path d="M142 146q4 4 0 8M147 143q6 7 0 14"/>');

    // Rzeczy na głowie (ruszają się z głową): termometr, pot, piana spod prysznica, splątana włóczka.
    var HEAD_EXTRA =
        g('nd-thermo', '<g transform="rotate(30 100 106)"><rect x="100" y="103.4" width="27" height="5.2" rx="2.6" fill="#fff" stroke="#8C96AB" stroke-width="1.2"/>' +
            '<rect x="101" y="105" width="13" height="2" rx="1" fill="#F05A6E"/>' +
            '<path d="M109 103.8v1.6M113 103.8v1.6M117 103.8v1.6M121 103.8v1.6" stroke="#8C96AB" stroke-width=".8"/></g>' +
            '<circle cx="100.5" cy="106" r="3" fill="#F05A6E" stroke="#C8394C" stroke-width="1"/>') +
        g('nd-sweat', '<path d="M138 64q-3.6 5.2 0 7.6q3.6-2.4 0-7.6z"/>') +
        g('fxv-foam-head', [[80, 52, 8], [94, 45, 9.5], [110, 46, 8.5], [123, 54, 7], [102, 37, 6], [70, 60, 5]].map(function (c) {
            return '<circle cx="' + c[0] + '" cy="' + c[1] + '" r="' + c[2] + '"/>';
        }).join('')) +
        g('fxv-tangle', '<path d="M62 62c8-14 20-2 28-12s18 4 24-6 18 2 22 12c3 6-6 8-10 2s-12-2-16 4-14-2-20 4-14 0-12-6"/>');

    // Rzeczy trzymane w łapkach (warstwa ciała — skalują się ze stadium).
    var APPLE = 'M100 131C96 127.4 85 128 84 138.5C83 148 90.5 156 95.5 156C97.3 156 98.3 155.1 100 155.1C101.7 155.1 102.7 156 104.5 156';
    var BITE_R = 'C108 156 112.5 152 114.6 147.5A4 4 0 0 1 110.5 143.5A4 4 0 0 1 112.5 138A4 4 0 0 1 113.5 132.5C111 129.5 105 128 100 131Z';
    var HOLD =
        g('fxv-apple',
            g('ap ap0', '<path class="ap-red" d="' + APPLE + 'C109.5 156 117 148 116 138.5C115 128 104 127.4 100 131Z"/>' +
                '<ellipse class="ap-shine" cx="90" cy="136" rx="2.6" ry="4.4" transform="rotate(20 90 136)"/>') +
            g('ap ap1', '<path class="ap-red" d="' + APPLE + BITE_R + '"/>' +
                '<path class="ap-flesh" d="M114.6 147.5A4 4 0 0 1 110.5 143.5A4 4 0 0 1 112.5 138A4 4 0 0 1 113.5 132.5"/>') +
            g('ap ap2', '<path class="ap-red" d="M100 131C97 129 89 129.5 86.5 133A4 4 0 0 1 87.5 138.5A4 4 0 0 1 89.5 144A4 4 0 0 1 85.4 147.5' +
                'C87.5 152 91.5 156 95.5 156C97.3 156 98.3 155.1 100 155.1C101.7 155.1 102.7 156 104.5 156' + BITE_R + '"/>' +
                '<path class="ap-flesh" d="M86.5 133A4 4 0 0 1 87.5 138.5A4 4 0 0 1 89.5 144A4 4 0 0 1 85.4 147.5"/>' +
                '<path class="ap-flesh" d="M114.6 147.5A4 4 0 0 1 110.5 143.5A4 4 0 0 1 112.5 138A4 4 0 0 1 113.5 132.5"/>') +
            g('ap ap3', '<path fill="#FFF1C9" stroke="#E2C27A" stroke-width="1.2" d="M95 131q5 2.5 10 0q-3.5 5-3 9.5q.5 5 3.5 9.5q-5.5-2-11 0q3-4.5 3.5-9.5q.5-4.5-3-9.5z"/>' +
                '<path fill="#E8505B" d="M94 131.5q6-4 12 0q-6 2-12 0z"/><path fill="#E8505B" d="M93.5 150q6.5-3 13 0q-6.5 5-13 0z"/>' +
                '<ellipse cx="98.6" cy="140" rx="1" ry="1.8" fill="#6B3F22"/><ellipse cx="101.6" cy="142" rx="1" ry="1.8" fill="#6B3F22"/>') +
            '<path class="ap-stem" d="M100 131q-.5-5 2.5-8"/><path class="ap-leaf" d="M102 125q6-5 10-1q-5 4-10 1z"/>') +
        g('fxv-cookie', g('fxv-cookie-in',
            g('ck ck0', '<circle class="ck-dough" cx="100" cy="141" r="13"/>') +
            g('ck ck1', '<path class="ck-dough" d="M100 128A13 13 0 1 0 113 141A4.2 4.2 0 0 1 108.6 137.6A4.2 4.2 0 0 1 106.6 132A4.2 4.2 0 0 1 100 128Z"/>') +
            g('ck ck2', '<path class="ck-dough" d="M87 141A13 13 0 0 0 113 141A4.3 4.3 0 0 1 106.5 140A4.3 4.3 0 0 1 100 141.5A4.3 4.3 0 0 1 93.5 140A4.3 4.3 0 0 1 87 141Z"/>') +
            '<g class="ck-chips"><circle class="ck-c1" cx="95" cy="135.5" r="1.9"/><circle class="ck-c2" cx="106" cy="134" r="1.7"/>' +
            '<circle class="ck-c3" cx="92" cy="143" r="1.8"/><circle class="ck-c4" cx="101" cy="146.5" r="2"/><circle class="ck-c5" cx="107.5" cy="144" r="1.7"/></g>'));

    // Dłoń do pat pat: otwarta, wierzchem do widza, palce w lewo; rękaw wjeżdża z prawej z góry.
    // (0, 0) = środek spodu dłoni na czubku głowy; nadgarstek ok. (19, -13) to oś klepania.
    function finger(x1, y1, x2, y2, r) {
        var d = 'x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '"';
        return '<line class="hd-fo" ' + d + ' stroke-width="' + (2 * r + 2.8) + '"/>' +
            '<line class="hd-ff" ' + d + ' stroke-width="' + (2 * r) + '"/>';
    }
    var HAND = g('fx-hand', g('fx-hand-in', '<g transform="rotate(-8) scale(1.3)">' +
        '<path class="hd-sleeve" d="M17.2-18.6L42-31L50-15L25.2-2.6z"/>' +
        finger(4, -12.5, -12, -14.5, 2.7) + finger(4, -9.3, -17, -10.6, 2.9) +
        finger(4, -5.9, -17.5, -6.2, 2.9) + finger(4, -2.6, -14, -1.9, 2.8) +
        '<path class="hd-skin" d="M2-15.5Q9-18.5 15.5-16.5L21.5-.5Q12 2.2 2 .8Q-.8-7.4 2-15.5z"/>' +
        finger(9, -.5, 2.5, 3.6, 2.7) +
        '<path class="hd-cuff" d="M12-16L17.6-18.8L25.6-2.6L20 .2z"/></g>'));

    // Chmurki „PAT” przy każdym klepnięciu (środek chmurki w (0, 0); cała grupa skalowana --rig-pat-k z rig.pat).
    var PAT_PUFFS = '<circle cx="-15" cy="3.8" r="8.3"/><circle cx="-6" cy="-3.8" r="10.5"/>' +
        '<circle cx="6.8" cy="-4.5" r="9.8"/><circle cx="15.8" cy="3" r="8.3"/><circle cx="0" cy="6" r="9.8"/>';
    function patCloud(n, x, y, rot) {
        return '<g class="fx-pat-c fx-pat-c' + n + '" transform="translate(' + x + ' ' + y + ') rotate(' + rot + ')">' +
            g('pc-in', g('pc-o', PAT_PUFFS) + g('pc-f', PAT_PUFFS) + '<text class="pc-t" x="0" y="6.5">PAT</text>') + '</g>';
    }
    var PATS = g('fx-pat', patCloud(1, -50, -6, -8) + patCloud(2, -16, -40, 5) + patCloud(3, -60, -34, -4));

    // Rekwizyty 9 wariantów akcji (układ sceny 200×200, ziemia y 182).
    function drops(list) {
        return list.map(function (d) {
            return '<path d="M' + d[0] + ' ' + d[1] + 'q-3 4.6 0 6.6q3-2 0-6.6z"/>';
        }).join('');
    }
    var FXV =
        g('fxv-miska', '<path fill="#FF9EBF" stroke="#E0688F" stroke-width="2" stroke-linejoin="round" d="M68 176h64c-2 12-13 19-32 19s-30-7-32-19z"/>' +
            '<ellipse cx="100" cy="176" rx="32" ry="5.5" fill="#E0688F"/>' +
            '<path fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" opacity=".7" d="M76 182q3 6 9 8"/>' +
            '<g class="fxv-kib"><circle cx="88" cy="173" r="4" fill="#B9774B"/><circle cx="100" cy="171" r="4.4" fill="#C98A58"/>' +
            '<circle cx="112" cy="173" r="4" fill="#B9774B"/><circle cx="94" cy="176" r="3.6" fill="#A66A40"/><circle cx="106" cy="176" r="3.6" fill="#C98A58"/></g>' +
            '<g class="fxv-crumbs"><circle cx="90" cy="150" r="1.8" fill="#C98A58"/><circle cx="109" cy="148" r="1.6" fill="#B9774B"/><circle cx="100" cy="146" r="1.4" fill="#C98A58"/></g>') +
        g('fxv-crumbs2', '<circle cx="90" cy="160" r="1.8"/><circle cx="110" cy="158" r="1.5"/><circle cx="100" cy="156" r="1.3"/><circle cx="105" cy="162" r="1.2"/>') +
        g('fxv-yarn', '<path class="yarn-thread" pathLength="100" d="M54 181C72 176 88 186 106 180S136 176 148 177"/>' +
            '<g class="yarn"><g class="yarn-in"><circle r="11" fill="#FF8FB8" stroke="#E0628F" stroke-width="1.8"/>' +
            '<path d="M-9-5q9 4 18 0M-10 2q10 5 20 0M-6 8q6 2 12 0M-3-10q-3 10 0 20M4-10q4 10 0 20" stroke="#E0628F" stroke-width="1.3" fill="none"/></g></g>') +
        g('fxv-bubbles', [[54, 128, 10], [146, 118, 12], [74, 84, 7.5], [128, 70, 9], [40, 92, 6.5], [162, 150, 7], [100, 34, 8]].map(function (b) {
            return '<g class="bb"><circle class="bb-ball" cx="' + b[0] + '" cy="' + b[1] + '" r="' + b[2] + '"/>' +
                '<path class="bb-hi" d="M' + (b[0] - b[2] * 0.55) + ' ' + (b[1] - b[2] * 0.1) + 'a' + (b[2] * 0.6) + ' ' + (b[2] * 0.6) + ' 0 0 1 ' + (b[2] * 0.5) + ' ' + (-b[2] * 0.48) + '"/></g>';
        }).join('')) +
        g('fxv-tub-front', '<path class="tub-body" d="M34 158h132l-9 28q-2 7-9 7H52q-7 0-9-7z"/>' +
            '<path class="tub-stripe" d="M39 172h122"/>' +
            '<g class="tub-foam"><circle cx="46" cy="156" r="8"/><circle cx="60" cy="152" r="9"/><circle cx="76" cy="155" r="8"/><circle cx="124" cy="155" r="8"/>' +
            '<circle cx="140" cy="152" r="9"/><circle cx="155" cy="156" r="8"/><circle cx="92" cy="158" r="6"/><circle cx="108" cy="158" r="6"/></g>' +
            '<g class="duck"><path fill="#FFD23F" stroke="#E0A800" stroke-width="1.4" d="M142 146c0-6 4-10 9-10s8 4 8 8c4-1 8 1 9 4c1 5-4 9-13 9h-6c-5 0-7-5-7-11z"/>' +
            '<path fill="#FF8C3B" d="M145 139l-6 1.6 6 1.6z"/><circle cx="149" cy="140" r="1.4" fill="#3B2A3A"/></g>' +
            '<g class="splash">' + drops([[40, 140], [56, 130], [146, 128], [162, 138], [100, 126]]) + '</g>') +
        g('fxv-shake', drops([[30, 120], [168, 116], [40, 150], [162, 150], [50, 96], [152, 92]])) +
        g('fxv-shower', '<path class="sh-pipe" d="M168-14V-4q0 6-6 6h-50"/>' +
            '<path class="sh-head" d="M82 0h36l7 13H75z"/><path class="sh-holes" d="M82 13h0M89 13h0M96 13h0M104 13h0M111 13h0M118 13h0"/>' +
            '<g class="sh-water"><path d="M82 18V150"/><path d="M89 18V150"/><path d="M96 18V150"/><path d="M104 18V150"/><path d="M111 18V150"/><path d="M118 18V150"/></g>' +
            '<g class="sh-splash"><path d="M66 180q-6-8-12-4M134 180q6-8 12-4M60 186q-8-4-14 0M140 186q8-4 14 0"/></g>') +
        g('fxv-sponge-foam', [[86, 158, 7], [114, 150, 6], [92, 132, 6.5], [112, 120, 5.5], [88, 78, 6], [114, 70, 6.5], [100, 62, 5]].map(function (c) {
            return '<circle cx="' + c[0] + '" cy="' + c[1] + '" r="' + c[2] + '"/>';
        }).join('')) +
        g('fxv-sponge', g('sponge', '<rect x="-14" y="-9" width="28" height="18" rx="6" fill="#FFD966" stroke="#E0A92E" stroke-width="1.6"/>' +
            '<rect x="-14" y="1" width="28" height="8" rx="4" fill="#7BC67E" stroke="#4E9A55" stroke-width="1.4"/>' +
            '<circle cx="-7" cy="-3.5" r="1.7" fill="#EBB93C"/><circle cx="1" cy="-5" r="1.4" fill="#EBB93C"/><circle cx="7" cy="-2.4" r="1.8" fill="#EBB93C"/>'));

    // Tył miednicy (za postacią) — przód z pianą i kaczuszką jest w FXV.
    var FXV_BACK = g('fxv-tub', '<ellipse class="tub-back" cx="100" cy="158" rx="66" ry="10"/><ellipse class="tub-water" cx="100" cy="159" rx="60" ry="7"/>');

    // Łóżeczko szpitalne (pose 'bed'): zagłówek + poduszka za postacią, kołderka przed nią.
    var BED_BACK = g('rig-bed-back',
        '<rect class="bed-post" x="27" y="62" width="10" height="132" rx="5"/><rect class="bed-post" x="163" y="62" width="10" height="132" rx="5"/>' +
        '<rect class="bed-board" x="34" y="72" width="132" height="84" rx="16"/>' +
        '<path class="bed-cross" d="M45 82h6v6h6v6h-6v6h-6v-6h-6v-6h6z"/>' +
        '<path class="bed-pillow" d="M50 142c0-13 20-19 50-19s50 6 50 19-20 17-50 17-50-4-50-17z"/>');
    var BED_FRONT = g('rig-bed-front',
        '<rect class="bed-mattress" x="24" y="176" width="152" height="12" rx="6"/>' +
        '<path class="bed-quilt" d="M28 154q12-7 26-4q23-9 46-5q23-4 46 5q14-3 26 4v26q0 8-8 8H36q-8 0-8-8z"/>' +
        '<path class="bed-fold" d="M30 158q12-6 25-3q22-8 45-4q23-4 45 4q13-3 25 3"/>' +
        '<g class="bed-dots">' + [[60, 170], [100, 174], [140, 170]].map(function (p) {
            return '<path d="M' + p[0] + ' ' + p[1] + SMALL_HEART + '"/>';
        }).join('') + '</g>' +
        '<ellipse class="f-b o bed-paw" cx="80" cy="153" rx="8" ry="5.6"/><ellipse class="f-b o bed-paw" cx="120" cy="153" rx="8" ry="5.6"/>' +
        '<circle class="bed-wheel" cx="32" cy="196" r="4"/><circle class="bed-wheel" cx="168" cy="196" r="4"/>');

    function buildFigure(sp) {
        var P = sp.parts || {};
        var mouth = P.mouth || DEF.mouth;
        var arm = P.arm || DEF.arm;
        var ears = g('rig-ears', P.ears || '');
        var skull = g('rig-skull', (P.skull || DEF.skull) + (P.face || '') +
            (P.nose != null ? P.nose : DEF.nose) + DEF.shine + DEF.headDirt + DEF.pale);
        var head =
            (P.earsFront ? '' : ears) + skull + (P.earsFront ? ears : '') +
            g('rig-eyes', eye(78, P.eye) + eye(122, P.eye) + DEF.tear) +
            g('rig-cheeks', DEF.cheeks) +
            g('rig-mouth', g('m-smile', mouth.smile) + g('m-open', mouth.open) + g('m-frown', mouth.frown)) +
            g('rig-fringe', P.fringe || '') +
            g('rig-nh', HEAD_EXTRA) +
            '<g class="rig-accessories"></g>';
        // rig-nm = ruch całej postaci wynikający z potrzeby (podskoki), niezależny od gestów na rig-fm
        return g('rig-fig', g('rig-nm', g('rig-fm',
            g('rig-tail', g('rig-tail-in', P.tail || '', origin(P.tailO || '125px 168px'))) +
            g('rig-body', g('rig-bm', (P.body || DEF.body) + DEF.bodyDirt + (P.bodyExtra || ''))) +
            g('rig-paws', g('rig-pm', g('rig-feet', P.feet || DEF.feet) + g('rig-hold', HOLD, ' transform="translate(0 17)"') +
                g('rig-arm-l', arm) + g('rig-arm-r', '<g transform="matrix(-1 0 0 1 200 0)">' + arm + '</g>'))) +
            g('rig-head', g('rig-hm', head))
        )));
    }

    function getSpecies(slug) {
        var all = window.PetSpecies || {};
        if (all[slug]) return all[slug];
        if (window.console) console.warn('PetRig: nieznany gatunek', slug);
        return all.kotek || { palette: { base: '#ccc', light: '#eee', dark: '#999', cheek: '#f9c' }, parts: {} };
    }

    function applyPalette(el, sp) {
        var p = sp.palette, P = sp.parts || {};
        el.style.setProperty('--rig-base', p.base);
        el.style.setProperty('--rig-light', p.light);
        el.style.setProperty('--rig-dark', p.dark);
        el.style.setProperty('--rig-cheek', p.cheek);
        el.style.setProperty('--rig-line', P.line || p.dark);
        el.style.setProperty('--rig-ink', P.ink || INK);
        el.style.setProperty('--rig-iris', (P.eye && P.eye.iris) || INK);
    }

    function pick(list, v, def) {
        return list.indexOf(v) >= 0 ? v : def;
    }

    function restartClass(el, cls) {
        el.classList.remove(cls);
        void el.getBoundingClientRect();
        el.classList.add(cls);
    }

    // --- Rig ---------------------------------------------------------------------------------

    function mount(container, opts) {
        var o = {
            species: 'kotek', stage: 'dorosly', stars: 0, mood: 'szczesliwy',
            asleep: false, size: 'card', idle: false, need: null, pose: 'stand'
        };
        var el = document.createElement('div');
        var timers = { blink: 0, idle: 0, gesture: 0, action: 0 };
        var raf = 0;
        var queue = [];
        var current = null;
        var gestureName = null;
        var destroyed = false;
        var rig = { el: el };

        function render() {
            var sp = getSpecies(o.species);
            el.innerHTML = '<svg viewBox="0 0 200 200" aria-hidden="true" focusable="false">' +
                BED_BACK +
                g('rig-shadow', '<ellipse cx="100" cy="183" rx="40" ry="6.5"/>') +
                g('rig-fxb', FX_BACK + FXV_BACK) + buildFigure(sp) + BED_FRONT + g('rig-fx', FX + FXV + HAND + PATS) +
                '<g class="rig-stars"></g>' + g('rig-status', STATUS) + '</svg>';
            applyPalette(el, sp);
            rig.setStars(o.stars);
        }

        function setClasses() {
            var keep = [];
            el.classList.forEach(function (c) {
                if (c.indexOf('pet-rig') !== 0 && c.indexOf('need-') !== 0 && c.indexOf('pose-') !== 0) keep.push(c);
            });
            var cls = ['pet-rig', 'pet-rig--' + o.species, 'pet-rig--' + o.stage, 'pet-rig--' + o.size];
            if (o.need) cls.push('need-' + o.need);
            cls.push('pose-' + o.pose);
            if (current && current.cls && current.cls.indexOf('pose-off') >= 0) cls.push('pose-off');
            el.className = cls.concat(keep).join(' ');
        }

        // need (świat) ma pierwszeństwo przed mood/asleep (dotychczasowe karty i towarzysz)
        function effAsleep() {
            return o.need ? o.need === 'sleep' : o.asleep;
        }

        function effMood() {
            return o.need ? NEED_MOOD[o.need] : o.mood;
        }

        function baseState() {
            if (effAsleep()) return 'is-sleep';
            return 'is-' + (MOOD_STATE[effMood()] || 'idle');
        }

        function applyBase() {
            BASE_STATES.forEach(function (c) { el.classList.remove(c); });
            el.setAttribute('data-mood', effMood());
            if (!current) el.classList.add(baseState());
        }

        function scheduleBlink() {
            clearTimeout(timers.blink);
            timers.blink = setTimeout(function () {
                if (destroyed) return;
                if (!current && !effAsleep()) rig.gesture('blink');
                scheduleBlink();
            }, 3000 + Math.random() * 3000);
        }

        function scheduleIdle() {
            clearTimeout(timers.idle);
            if (!o.idle) return;
            timers.idle = setTimeout(function () {
                if (destroyed) return;
                var list = (GESTURES[o.stage] || []).filter(function (n) { return n !== 'blink'; });
                rig.gesture(list[Math.floor(Math.random() * list.length)]);
                scheduleIdle();
            }, 7000 + Math.random() * 7000);
        }

        function normalize(src) {
            if (!src) return;
            if (src.species != null) o.species = (window.PetSpecies || {})[src.species] ? src.species : (getSpecies(src.species), 'kotek');
            if (src.stage != null) o.stage = pick(STAGES, src.stage, 'dorosly');
            if (src.size != null) o.size = pick(SIZES, src.size, 'card');
            if (src.mood != null) o.mood = MOOD_STATE[src.mood] ? src.mood : 'szczesliwy';
            if (src.asleep != null) o.asleep = !!src.asleep;
            if (src.stars != null) o.stars = Math.max(0, Math.min(5, parseInt(src.stars, 10) || 0));
            if (src.idle != null) o.idle = !!src.idle;
            if (src.need !== undefined) o.need = src.need == null ? null : pick(NEEDS, src.need, 'happy');
            if (src.pose != null) o.pose = pick(POSES, src.pose, 'stand');
        }

        rig.update = function (src) {
            if (destroyed || !src) return rig;
            var prevSpecies = o.species, prevStars = o.stars, prevIdle = o.idle;
            normalize(src);
            if (o.species !== prevSpecies) render();
            else if (o.stars !== prevStars) rig.setStars(o.stars);
            setClasses();
            applyBase();
            if (o.idle !== prevIdle) scheduleIdle();
            return rig;
        };

        rig.setNeed = function (need) {
            return rig.update({ need: need == null ? null : need });
        };

        rig.setPose = function (pose) {
            return rig.update({ pose: pose || 'stand' });
        };

        rig.setStars = function (n) {
            o.stars = Math.max(0, Math.min(5, parseInt(n, 10) || 0));
            var layer = el.querySelector('.rig-stars');
            if (!layer) return rig;
            var s = '';
            for (var i = 0; i < o.stars; i++) {
                s += '<path style="animation-delay:' + (i * 0.4) + 's" d="' + starPath(100 + (i - (o.stars - 1) / 2) * 15, 193, 5.6) + '"/>';
            }
            layer.innerHTML = s;
            return rig;
        };

        rig.gesture = function (name) {
            if (destroyed) return false;
            var allowed = GESTURES[o.stage] || [];
            if (allowed.indexOf(name) < 0) return false;
            if (name === 'blink') {
                if (effAsleep()) return false;
                restartClass(el, 'g-blink');
                setTimeout(function () { el.classList.remove('g-blink'); }, 260);
                return true;
            }
            // Gesty tylko w spokojnym stanie (bez akcji, snu, choroby, leżenia) i bez ograniczenia ruchu.
            if (current || !el.classList.contains('is-idle') || reducedMotion()) return false;
            if (o.pose === 'lie' || o.pose === 'bed') return false;
            if (gestureName) el.classList.remove('g-' + gestureName);
            gestureName = name;
            restartClass(el, 'g-' + name);
            clearTimeout(timers.gesture);
            timers.gesture = setTimeout(endGesture, 2000);
            return true;
        };

        function endGesture() {
            if (gestureName) el.classList.remove('g-' + gestureName);
            gestureName = null;
            clearTimeout(timers.gesture);
        }

        el.addEventListener('animationend', function (e) {
            if (gestureName && e.animationName === 'rig-g-' + gestureName) endGesture();
        });

        function stopBall() {
            if (raf) cancelAnimationFrame(raf);
            raf = 0;
            var eyes = el.querySelector('.rig-eyes');
            if (eyes) eyes.style.transform = '';
        }

        // Piłka przy zabawie — jedyna sekwencja na requestAnimationFrame (spec §4.5).
        // legs = liczba przelotów lewo↔prawo; track = oczy pupila podążają za piłką (wariant „pilka").
        function runBall(duration, legs, track) {
            var ball = el.querySelector('.fx-ball');
            var inner = el.querySelector('.fx-ball-in');
            var eyes = track ? el.querySelector('.rig-eyes') : null;
            if (!ball) return;
            if (reducedMotion()) {
                ball.setAttribute('transform', 'translate(150 172)');
                return;
            }
            var t0 = null;
            function step(ts) {
                if (destroyed) return;
                if (t0 === null) t0 = ts;
                var t = Math.min(1, (ts - t0) / duration);
                // Odcinki lewo-prawo na przemian, po trzy odbicia na odcinek, coraz niżej.
                var seg = Math.min(legs - 1, Math.floor(t * legs));
                var u = t * legs - seg;
                var x = seg % 2 === 0 ? 26 + u * 148 : 174 - u * 148;
                var ph = (u * 3) % 1;
                var h = 58 * (1 - t * 0.55);
                var y = 172 - 4 * h * ph * (1 - ph);
                ball.setAttribute('transform', 'translate(' + x.toFixed(1) + ' ' + y.toFixed(1) + ')');
                if (inner) inner.setAttribute('transform', 'rotate(' + Math.round(u * 720 * (seg % 2 ? -1 : 1)) + ')');
                if (eyes) eyes.style.transform = 'translate(' + ((x - 100) / 74 * 3).toFixed(2) + 'px,' + ((y - 172) / 58 * 2).toFixed(2) + 'px)';
                if (t < 1) raf = requestAnimationFrame(step);
                else raf = 0;
            }
            stopBall();
            raf = requestAnimationFrame(step);
        }

        // Klasy + czas zadania: dłoń, wariant albo dotychczasowa akcja (ostatnia klasa jest restartowana).
        function jobSpec(job) {
            var rm = reducedMotion();
            if (job.key === 'hand') return { cls: ['is-handpat'], dur: rm ? 600 : HAND_MS };
            if (job.variant) {
                var d = VARIANT_MS[job.variant];
                return { cls: ['pose-off', 'is-v', 'is-v-' + job.action, 'is-v-' + job.variant], dur: rm ? Math.min(d, RM_MS) : d };
            }
            var a = ACTIONS[job.action];
            return { cls: ['pose-off', a[0]], dur: rm ? Math.min(a[1], RM_MS) : a[1] };
        }

        function finish(job) {
            el.classList.remove.apply(el.classList, job.cls.concat(['is-acting', 'hp-heart']));
            stopBall();
            if (job.action === 'wake') {
                o.asleep = false;
                if (o.need === 'sleep') o.need = 'happy';
            }
            current = null;
            setClasses();
            applyBase();
            job.resolve();
            pump();
        }

        function run(job) {
            var spec = jobSpec(job);
            job.cls = spec.cls;
            current = job;
            endGesture();
            BASE_STATES.forEach(function (c) { el.classList.remove(c); });
            el.classList.add('is-acting');
            el.classList.toggle('hp-heart', job.key === 'hand' && Math.random() < 0.6);
            spec.cls.slice(0, -1).forEach(function (c) { el.classList.add(c); });
            restartClass(el, spec.cls[spec.cls.length - 1]);
            if (job.action === 'play' && !job.variant) runBall(spec.dur, 2, false);
            if (job.variant === 'pilka') runBall(spec.dur, 3, true);
            clearTimeout(timers.action);
            timers.action = setTimeout(function () { finish(job); }, spec.dur);
        }

        function pump() {
            if (current || destroyed || !queue.length) return;
            run(queue.shift());
        }

        function enqueue(action, variant, key) {
            var last = queue[queue.length - 1];
            if (last && last.key === key) return last.promise;
            var job = { action: action, variant: variant, key: key };
            job.promise = new Promise(function (res) { job.resolve = res; });
            queue.push(job);
            pump();
            return job.promise;
        }

        rig.playAction = function (action, opts) {
            if (destroyed) return Promise.resolve();
            if (!ACTIONS[action]) return Promise.reject(new Error('PetRig: nieznana akcja ' + action));
            var variant = null;
            if (opts && opts.variant != null && VARIANTS[action]) {
                variant = VARIANTS[action].indexOf(opts.variant) >= 0 ? opts.variant : VARIANTS[action][0];
                if (variant !== opts.variant && window.console) console.warn('PetRig: nieznany wariant', action, opts.variant);
            }
            // Pat pat wielokrotnie = jedna animacja odświeżona (bez kolejki 50 głaskań).
            if (current && current.key === 'pat' && action === 'pat') {
                restartClass(el, 'is-pat');
                clearTimeout(timers.action);
                var job0 = current;
                timers.action = setTimeout(function () { finish(job0); }, reducedMotion() ? 600 : ACTIONS.pat[1]);
                return current.promise;
            }
            return enqueue(action, variant, action + (variant ? ':' + variant : ''));
        };

        // Chmurki „PAT” mają być czytelne także u małego towarzysza (72 px) — skala odwrotna do rozmiaru.
        function setPatScale() {
            var svg = el.querySelector('svg');
            var w = svg ? svg.getBoundingClientRect().width : 0;
            el.style.setProperty('--rig-pat-k', (w ? Math.max(1, Math.min(2, 120 / w)) : 1).toFixed(2));
        }

        // Dłoń: wjeżdża z boku, klepie 3 razy (chmurki „PAT”), pupil mruży oczy, czasem serduszko.
        rig.pat = function () {
            if (destroyed) return Promise.resolve();
            setPatScale();
            if (current && current.key === 'hand') {
                var job0 = current;
                el.classList.toggle('hp-heart', Math.random() < 0.6);
                restartClass(el, 'is-handpat');
                clearTimeout(timers.action);
                timers.action = setTimeout(function () { finish(job0); }, jobSpec(job0).dur);
                return job0.promise;
            }
            return enqueue('pat', null, 'hand');
        };

        rig.destroy = function () {
            if (destroyed) return;
            destroyed = true;
            Object.keys(timers).forEach(function (k) { clearTimeout(timers[k]); });
            stopBall();
            if (current) current.resolve();
            queue.forEach(function (j) { j.resolve(); });
            queue = [];
            current = null;
            if (el.parentNode) el.parentNode.removeChild(el);
        };

        normalize(opts);
        setClasses();
        render();
        applyBase();
        container.appendChild(el);
        scheduleBlink();
        scheduleIdle();
        return rig;
    }

    // --- Jajko -------------------------------------------------------------------------------

    var EGG = 'M100 26C136 26 158 92 158 126C158 160 132 182 100 182C68 182 42 160 42 126C42 92 64 26 100 26Z';
    var ZIG = '172 96 158 87 144 98 130 86 116 98 102 86 88 98 74 86 60 98 46 87 30 96';
    // Wzory ze szkiców (viewBox 80×100, ten sam kształt jajka) → układ 200×200.
    var SKETCH = ' transform="translate(31.8 15.6) scale(1.72)"';

    function skinIndex(skin) {
        if (typeof skin === 'string' && EGG_SKINS.indexOf(skin) >= 0) return EGG_SKINS.indexOf(skin);
        var n = parseInt(skin, 10);
        return n >= 0 && n < EGG_SKINS.length ? n : 0;
    }

    function skinPattern(skin, id) {
        switch (EGG_SKINS[skin]) {
            case 'niebo':
                return '<g' + SKETCH + '><rect width="80" height="100" fill="url(#' + id + 'n)"/>' +
                    '<g fill="#FFE27A"><path d="M30 30l2 5 5 1-4 3 1 5-4-3-4 3 1-5-4-3 5-1z"/><circle cx="54" cy="46" r="2"/>' +
                    '<circle cx="22" cy="60" r="1.6"/><path d="M50 70l1.5 3.5 3.5.6-2.6 2.2.8 3.5-3.2-2-3.2 2 .8-3.5-2.6-2.2 3.5-.6z"/>' +
                    '<circle cx="36" cy="82" r="1.8"/><circle cx="16" cy="42" r="1.2"/><circle cx="64" cy="58" r="1.3"/></g>' +
                    '<path d="M58 20a10 10 0 1 0 6 16a8 8 0 1 1-6-16z" fill="#FFF6C9"/></g>';
            case 'laczka':
                return '<g' + SKETCH + '><g transform="translate(30 42)"><circle r="4" fill="#FFD36B"/><g fill="#FF9EC4">' +
                    '<circle cy="-7" r="4"/><circle cx="7" r="4"/><circle cy="7" r="4"/><circle cx="-7" r="4"/></g><circle r="3.4" fill="#FFD36B"/></g>' +
                    '<g transform="translate(52 66)"><g fill="#B99CFF"><circle cy="-6" r="3.4"/><circle cx="6" r="3.4"/><circle cy="6" r="3.4"/>' +
                    '<circle cx="-6" r="3.4"/></g><circle r="3" fill="#FFD36B"/></g>' +
                    '<g transform="translate(22 66) scale(.6)"><g fill="#FFFFFF"><circle cy="-6" r="3.4"/><circle cx="6" r="3.4"/><circle cy="6" r="3.4"/>' +
                    '<circle cx="-6" r="3.4"/></g><circle r="3" fill="#FFD36B"/></g>' +
                    '<path d="M18 80q6-10 12-2M56 26q6-8 10 0M44 88q4-7 9-2" stroke="#7FC96A" stroke-width="3" fill="none" stroke-linecap="round"/></g>';
            case 'paski':
                return '<g' + SKETCH + '><rect width="80" height="100" fill="#FFE1EC"/><rect y="24" width="80" height="10" fill="#FFD36B"/>' +
                    '<rect y="42" width="80" height="10" fill="#9FE0C8"/><rect y="60" width="80" height="10" fill="#B8D4FF"/>' +
                    '<rect y="78" width="80" height="10" fill="#D9C7FF"/></g>';
            case 'laty':
                return '<g' + SKETCH + '><path d="M22 24q10-6 16 4q-2 12-14 10q-8-6-2-14z" fill="#C98B5C"/>' +
                    '<path d="M50 50q12-4 16 8q-4 12-16 8q-6-8 0-16z" fill="#8A5A3B"/><path d="M18 70q8-4 12 4q-2 8-10 6q-6-4-2-10z" fill="#C98B5C"/>' +
                    '<path d="M40 84q6-3 9 2q-1 5-6 5q-5-2-3-7z" fill="#8A5A3B"/><circle cx="58" cy="28" r="3" fill="#8A5A3B"/></g>';
            default:   // kropki — dotychczasowe jajko
                return '<path class="egg-band" d="M36 134l12-10 12 10 12-10 12 10 12-10 12 10 12-10 12 10 12-10 12 10"/>' +
                    '<circle fill="#FFC9DE" cx="78" cy="64" r="7"/><circle fill="#BFE8D5" cx="126" cy="74" r="9"/>' +
                    '<circle fill="#FFE29A" cx="100" cy="46" r="5"/><circle fill="#C9B8F5" cx="66" cy="104" r="6"/>' +
                    '<circle fill="#FFC9DE" cx="136" cy="110" r="5.5"/><circle fill="#BFE8D5" cx="84" cy="160" r="7.5"/>' +
                    '<circle fill="#FFE29A" cx="124" cy="160" r="6"/>';
        }
    }

    function mountEgg(container, opts) {
        var o = { pct: 0, boosted: false, ready: false, size: 'card', skin: 0 };
        var id = 'pr' + (++uidSeq);
        var el = document.createElement('div');
        var timers = [];
        var destroyed = false;
        var hatching = null;
        var built = -1;
        var egg = { el: el };

        function build() {
            var art = '<path class="egg-shell" d="' + EGG + '"/>' +
                '<g clip-path="url(#' + id + 'c)">' + skinPattern(o.skin, id) + '</g>' +
                '<ellipse class="egg-hi" fill="#fff" cx="72" cy="74" rx="8" ry="15" transform="rotate(22 72 74)"/>' +
                '<path class="egg-rim" d="' + EGG + '"/>';
            el.innerHTML = '<svg viewBox="0 0 200 200" aria-hidden="true" focusable="false"><defs>' +
                '<clipPath id="' + id + 'c"><path d="' + EGG + '"/></clipPath>' +
                '<clipPath id="' + id + 't"><path d="M0 0H200V96L' + ZIG + 'L0 96Z"/></clipPath>' +
                '<clipPath id="' + id + 'b"><path d="M0 200H200V96L' + ZIG + 'L0 96Z"/></clipPath>' +
                '<linearGradient id="' + id + 'n" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3B3D8F"/>' +
                '<stop offset="1" stop-color="#7B5BD6"/></linearGradient>' +
                '<radialGradient id="' + id + 'g"><stop offset="0" stop-color="#FFB26B" stop-opacity=".55"/>' +
                '<stop offset="1" stop-color="#FFB26B" stop-opacity="0"/></radialGradient></defs>' +
                '<ellipse class="egg-shadow" cx="100" cy="184" rx="44" ry="7"/>' +
                '<circle class="egg-glow" cx="100" cy="112" r="88" fill="url(#' + id + 'g)"/>' +
                g('egg-heat', '<path d="M40 70q-5-7 0-14t0-14"/><path d="M160 76q5-7 0-14t0-14"/><path d="M28 120q-4-6 0-12t0-12"/>') +
                g('egg-rock',
                    g('egg-bottom', art, ' clip-path="url(#' + id + 'b)"') +
                    g('egg-top', g('egg-top-in', art), ' clip-path="url(#' + id + 't)"') +
                    g('egg-cracks',
                        '<path class="egg-c1" d="M126 50l-6 9 6 5-7 10"/>' +
                        '<path class="egg-c2" d="M119 74l7 7-5 8M50 118l10 3-3 9 11 3-4 8"/>' +
                        '<path class="egg-c3" d="M' + ZIG + '"/>',
                        ' clip-path="url(#' + id + 'c)"')) +
                g('egg-fx', sparkle(36, 60, 9, 'sp2') + sparkle(166, 54, 7, 'sp2') + sparkle(28, 132, 6, 'sp2') +
                    sparkle(172, 126, 8, 'sp2') + g('fx-conf', confetti(100, 92, 16))) +
                '</svg>';
            built = o.skin;
        }

        function sync() {
            var p = Math.max(0, Math.min(100, Number(o.pct) || 0));
            el.className = 'pet-rig pet-rig--egg pet-rig--' + o.size + ' egg--skin-' + EGG_SKINS[o.skin];
            el.setAttribute('data-skin', EGG_SKINS[o.skin]);
            if (p >= 33) el.classList.add('egg--c1');
            if (p >= 66) el.classList.add('egg--c2');
            if (p >= 100 || o.ready) el.classList.add('egg--c1', 'egg--c2', 'egg--c3', 'egg--ready');
            if (o.boosted && !o.ready) el.classList.add('egg--boosted');
            if (hatching) el.classList.add('egg--c1', 'egg--c2', 'egg--c3', 'egg--hatching');
            if (hatching === 'burst') el.classList.add('egg--burst');
        }

        function set(src) {
            if (!src) return;
            if (src.pct != null) o.pct = src.pct;
            if (src.boosted != null) o.boosted = !!src.boosted;
            if (src.ready != null) o.ready = !!src.ready;
            if (src.size != null) o.size = pick(SIZES, src.size, 'card');
            if (src.skin != null) o.skin = skinIndex(src.skin);
        }

        egg.update = function (src) {
            if (destroyed) return egg;
            set(src);
            if (built !== o.skin && !hatching) build();
            sync();
            return egg;
        };

        egg.hatch = function () {
            if (destroyed) return Promise.resolve();
            if (egg._p) return egg._p;
            var rm = reducedMotion();
            egg._p = new Promise(function (res) {
                hatching = 'shake';
                sync();
                timers.push(setTimeout(function () {
                    hatching = 'burst';
                    sync();
                }, rm ? 300 : 950));
                timers.push(setTimeout(res, rm ? 800 : 1800));
            });
            return egg._p;
        };

        egg.destroy = function () {
            destroyed = true;
            timers.forEach(clearTimeout);
            if (el.parentNode) el.parentNode.removeChild(el);
        };

        set(opts);
        build();
        sync();
        container.appendChild(el);
        return egg;
    }

    // --- Karta pamięci -----------------------------------------------------------------------

    function mountMemorial(container, opts) {
        opts = opts || {};
        var slug = (window.PetSpecies || {})[opts.species] ? opts.species : 'kotek';
        var sp = getSpecies(slug);
        var stage = pick(STAGES, opts.stage, 'dorosly');
        var size = pick(SIZES, opts.size, 'card');
        var id = 'pr' + (++uidSeq);
        var el = document.createElement('div');
        var rig = { el: el };

        el.className = 'pet-rig pet-rig--memorial pet-rig--' + slug + ' pet-rig--' + stage + ' pet-rig--' + size + ' is-memorial';
        el.innerHTML = '<svg viewBox="0 0 200 200" aria-hidden="true" focusable="false"><defs>' +
            '<clipPath id="' + id + 'c"><ellipse cx="100" cy="94" rx="47" ry="55"/></clipPath>' +
            '<filter id="' + id + 'f"><feColorMatrix type="saturate" values="0"/></filter></defs>' +
            '<ellipse class="mem-shadow" cx="100" cy="193" rx="78" ry="6"/>' +
            '<path class="mem-stone" d="M30 192V86C30 20 170 20 170 86V192Z"/>' +
            '<path class="mem-stone-hi" d="M41 182V88C41 58 60 45 86 42"/>' +
            '<ellipse class="mem-frame-bg" cx="100" cy="94" rx="47" ry="55"/>' +
            '<g clip-path="url(#' + id + 'c)"><g filter="url(#' + id + 'f)" transform="translate(42 33) scale(.58)">' +
            buildFigure(sp) + '</g></g>' +
            '<ellipse class="mem-frame" cx="100" cy="94" rx="47" ry="55"/>' +
            '<path class="mem-star" d="' + starPath(100, 170, 8) + '"/>' +
            '<path class="mem-grass" d="M20 194q4-12 8-2q3-10 7-1q4-9 7 3ZM158 194q4-12 8-2q3-10 7-1q4-9 7 3Z"/>' +
            g('mem-candle', '<rect x="146" y="170" width="11" height="20" rx="2.5" fill="#FFF3D6" stroke="#E2C998" stroke-width="1.5"/>' +
                '<path d="M151.5 170v-3" stroke="#6B5A4A" stroke-width="1.4"/>' +
                '<path class="mem-flame" d="M151.5 152c4 5 5.5 8 5.5 10.5a5.5 5.5 0 0 1-11 0c0-2.5 1.5-5.5 5.5-10.5z"/>') +
            '</svg>';
        applyPalette(el, sp);

        rig.update = function (src) {
            if (src && src.lit != null) el.classList.toggle('is-lit', !!src.lit);
            if (src && src.size != null) {
                SIZES.forEach(function (s) { el.classList.remove('pet-rig--' + s); });
                el.classList.add('pet-rig--' + pick(SIZES, src.size, 'card'));
            }
            return rig;
        };
        rig.gesture = function () { return false; };
        rig.playAction = function () { return Promise.resolve(); };
        rig.setStars = function () { return rig; };
        rig.destroy = function () {
            if (el.parentNode) el.parentNode.removeChild(el);
        };

        rig.update({ lit: !!opts.lit });
        container.appendChild(el);
        return rig;
    }

    // Najpilniejsza potrzeba z pet_dict (spec v3 §6.1; szpital: chory do wyleczenia, potem zadowolony).
    function needOf(pet) {
        if (!pet) return 'happy';
        if (pet.hospital) return pet.hospital.ready ? 'happy' : 'sick';
        if (pet.mood === 'krytyczny') return 'critical';
        if (pet.mood === 'chory') return 'sick';
        if (pet.asleep) return 'sleep';
        return MOOD_NEED[pet.mood] || 'happy';
    }

    window.PetRig = {
        mount: mount,
        mountEgg: mountEgg,
        mountMemorial: mountMemorial,
        needOf: needOf,
        GESTURES: GESTURES,
        ACTIONS: Object.keys(ACTIONS),
        STAGES: STAGES,
        NEEDS: NEEDS.slice(),
        POSES: POSES.slice(),
        VARIANTS: { feed: VARIANTS.feed.slice(), play: VARIANTS.play.slice(), wash: VARIANTS.wash.slice() },
        EGG_SKINS: EGG_SKINS.slice(),
        reducedMotion: reducedMotion
    };
})();
