/**
 * Świat pupili — scena „ogród wspomnień” (spec v3 §6.6, spec v3.1 §3.5).
 *
 * - Ogród na całą scenę, w trzech pasach (siatka CSS — pasy rosną z wysokością sceny, więc kompozycja wypełnia
 *   ją na każdym ekranie, a ozdoby z definicji nie wchodzą na nagrobki):
 *     niebo   — złota godzina (słońce nad wzgórzami, chmurki), wieczór w ciemnym motywie, noc w grze (księżyc,
 *               gwiazdy, spadająca gwiazda); wzgórza, wierzba płacząca „drzewo wspomnień” ze wstążkami,
 *               zawieszkami i lampionami, mgiełka i płotek na horyzoncie;
 *     kwatera — nagrobki (główny punkt) na jaśniejszej polanie;
 *     przód   — kamienna ścieżka do nagrobków z latarenkami, ławeczka z bukiecikiem, staw z liliami, polne kwiaty
 *               i niezapominajki, motyle i płatki w dzień, świetliki wieczorem i nocą.
 *   Ozdoby to statyczne SVG/CSS (aria-hidden, bez zdarzeń); ruch tylko w CSS (transform/opacity), wyłączany
 *   przy ograniczonym ruchu. Bez timerów i obserwatorów — scena ukryta (display: none) nie animuje się wcale.
 * - Nagrobki: pupile, które odeszły (wpisy albumu `memorial`), PetRig.mountMemorial + tabliczka z imieniem,
 *   znicz (zapalony = ciepłe światło wokół) i płomyk, gdy można dziś zapalić światełko. Klik w nagrobek = okno
 *   sceny ze szczegółami i „Zapal światełko” (POST /<id>/swiatelko, raz dziennie — jak dotąd).
 * - Tabliczka „Album gatunków n/8” = okno sceny z albumem: 8 gatunków (żywy = mini-rig, odszedł = nagrobek,
 *   nieodkryty = sylwetka bez animacji). Rigi albumu żyją tylko przy otwartym oknie.
 * - Zmiana stanu przy otwartym oknie: nagrobek jest → treść odświeżona (win.replace), zniknął → okno się
 *   zamyka z fokusem na scenie.
 * Style: css/pages/client/pets-garden.css (scena) i components/modals.css „Okna ogrodu (v3.1)” (treść okien).
 * Rejestruje się w window.PetsWorld.scenes.ogrod.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.ogrod) return;

    var STAGE_LABEL = { maluch: 'Maluch', dziecko: 'Dziecko', dorosly: 'Dorosły' };
    var MAX_FLAMES = 7;          // płomyki „Światełka” w oknie nagrobka; więcej = „+N”
    var NS = ' aria-hidden="true" focusable="false"';
    var BOOK_SVG = '<svg class="pets-garden__sign-icon" viewBox="0 0 24 24"' + NS + ' fill="none" ' +
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M3 5.5c3-1.2 6-1.2 9 .8v13c-3-2-6-2-9-.8z"/><path d="M21 5.5c-3-1.2-6-1.2-9 .8v13c3-2 6-2 9-.8z"/></svg>';

    // =====================================================================================
    // Wystrój (same ozdoby — stałe znaczniki bez danych użytkownika; kolory i ruch w pets-garden.css)
    // =====================================================================================

    /** Deterministyczny generator (gwiazdy w tych samych miejscach przy każdym wejściu). */
    function seeded(seed) {
        var s = seed;
        return function () {
            s = (s * 16807) % 2147483647;
            return (s - 1) / 2147483646;
        };
    }

    function n(v) { return Math.round(v * 10) / 10; }

    /** Warstwa gwiazd (trzy warstwy migoczą osobno — animowane całe <svg>, nie elementy w środku). */
    function starLayer(mod, seed, count) {
        var r = seeded(seed);
        var out = '';
        for (var i = 0; i < count; i++) {
            out += '<circle cx="' + n(r() * 1000) + '" cy="' + n(8 + r() * 290) + '" r="' + n(0.9 + r() * 1.4) + '"/>';
        }
        return '<svg class="pg-stars pg-stars--' + mod + '" viewBox="0 0 1000 400" preserveAspectRatio="xMidYMin slice"' + NS + '>' +
            out + '</svg>';
    }

    function sparkle(x, y, s) {
        return '<path d="M' + x + ' ' + (y - s) + 'L' + n(x + s * 0.26) + ' ' + n(y - s * 0.26) + 'L' + (x + s) + ' ' + y +
            'L' + n(x + s * 0.26) + ' ' + n(y + s * 0.26) + 'L' + x + ' ' + (y + s) + 'L' + n(x - s * 0.26) + ' ' + n(y + s * 0.26) +
            'L' + (x - s) + ' ' + y + 'L' + n(x - s * 0.26) + ' ' + n(y - s * 0.26) + 'Z"/>';
    }

    var SPARKLES =
        '<svg class="pg-stars pg-stars--big" viewBox="0 0 1000 400" preserveAspectRatio="xMidYMin slice"' + NS + '>' +
        sparkle(118, 66, 7) + sparkle(402, 34, 6) + sparkle(566, 120, 5) + sparkle(782, 58, 7) + sparkle(930, 150, 5) +
        sparkle(260, 170, 5) + '</svg>';

    var CLOUD_SVG =
        '<svg viewBox="0 0 140 50"' + NS + '>' +
        '<path class="pg-cloud-body" d="M22 44a15 15 0 0 1 4-29 21 21 0 0 1 38-8 17 17 0 0 1 30 5 14 14 0 0 1 21 7 12 12 0 0 1 3 25z"/>' +
        '<path class="pg-cloud-shade" d="M14 40c18 5 82 6 106 0-3 4-7 5-10 5H22c-4 0-7-2-8-5z"/></svg>';

    var MOON_SVG =
        '<svg viewBox="0 0 48 48"' + NS + '><path class="pg-moon-body" d="M30 4a20 20 0 1 0 14 30A16 16 0 1 1 30 4z"/>' +
        '<circle class="pg-moon-dot" cx="16" cy="30" r="2.6"/><circle class="pg-moon-dot" cx="22" cy="40" r="1.6"/></svg>';

    function tree(cx, cy, r) {
        return '<ellipse cx="' + cx + '" cy="' + cy + '" rx="' + r + '" ry="' + n(r * 1.2) + '"/>';
    }

    // Wzgórza z linią drzew (slice: na wąskim ekranie przycięte boki, proporcje zostają)
    var HILLS_SVG =
        '<svg class="pg-hills" viewBox="0 0 1200 140" preserveAspectRatio="xMidYMax slice"' + NS + '>' +
        '<path class="pg-hill-far" d="M0 80C120 50 240 44 360 62C480 80 560 92 680 76C800 60 900 36 1020 42C1100 46 1160 56 1200 60V140H0Z"/>' +
        '<g class="pg-treeline">' + tree(64, 62, 13) + tree(86, 57, 16) + tree(108, 63, 11) + tree(330, 52, 14) + tree(352, 47, 18) +
        tree(376, 54, 12) + tree(940, 40, 13) + tree(964, 34, 17) + tree(990, 41, 12) + tree(1130, 48, 14) + tree(1152, 53, 10) + '</g>' +
        '<path class="pg-hill-near" d="M0 106C140 90 280 86 420 100C560 114 700 116 840 102C980 90 1100 88 1200 98V140H0Z"/>' +
        '</svg>';

    // Płotek na horyzoncie (wzór sztachet; viewBox szeroki, więc nawet monitor 2600 px nie powiększa sztachet)
    var FENCE_SVG =
        '<svg class="pg-fence" viewBox="0 0 2600 30" preserveAspectRatio="xMidYMax slice"' + NS + '>' +
        '<defs><pattern id="pgFencePattern" width="22" height="30" patternUnits="userSpaceOnUse">' +
        '<path class="pg-picket" d="M6 30V9.5L11 4l5 5.5V30z"/></pattern></defs>' +
        '<rect class="pg-rail" x="0" y="12" width="2600" height="3.5" rx="1.75"/>' +
        '<rect class="pg-rail" x="0" y="22" width="2600" height="3.5" rx="1.75"/>' +
        '<rect x="0" y="0" width="2600" height="30" fill="url(#pgFencePattern)"/></svg>';

    /** Gałązka wierzby: zaokrąglona u góry, zwężająca się „zasłona” liści w dół, lekko wygięta na zewnątrz. */
    function drape(x, y0, y1, w, bend) {
        var h = y1 - y0;
        return 'M' + n(x - w / 2) + ' ' + y0 + 'a' + n(w / 2) + ' ' + n(w / 2) + ' 0 0 1 ' + n(w) + ' 0' +
            'C' + n(x + w / 2) + ' ' + n(y0 + h * 0.45) + ' ' + n(x + bend + w * 0.32) + ' ' + n(y1 - h * 0.18) + ' ' + n(x + bend) + ' ' + y1 +
            'C' + n(x + bend - w * 0.32) + ' ' + n(y1 - h * 0.18) + ' ' + n(x - w / 2) + ' ' + n(y0 + h * 0.45) + ' ' + n(x - w / 2) + ' ' + y0 + 'Z';
    }

    /**
     * Warstwa gałązek od x0 do x1 co `step` (bez pasa `gap` wokół pnia): zewnętrzne sięgają niżej (sylwetka
     * dzwonu), długość i szerokość z lekkim, powtarzalnym rozrzutem. Zwraca [ścieżka gałązek, ścieżka listków].
     */
    function drapes(x0, x1, step, gap, y0, y1, w, seed) {
        var r = seeded(seed);
        var d = '', leaves = '';
        for (var x = x0; x <= x1; x += step) {
            var off = Math.abs(x - 160);
            if (off < gap) continue;
            var top = n(y0 + off * off * 0.0012 + r() * 22);
            var end = Math.min(266, n(y1 + off * 0.24 + r() * 20));
            var bend = n((x - 160) * 0.08);
            d += drape(x, top, end, n(w + r() * 3), bend);
            // listki: krótkie owale wzdłuż gałązki, na zmianę w lewo i w prawo
            for (var k = 1; k <= 3; k++) {
                var t = 0.3 + k * 0.17;
                var lx = n(x + bend * t * t + (k % 2 ? -1 : 1) * w * 0.32);
                var ly = n(top + (end - top) * t);
                leaves += '<ellipse cx="' + lx + '" cy="' + ly + '" rx="2.2" ry="5.2" transform="rotate(' + (k % 2 ? 24 : -24) + ' ' + lx + ' ' + ly + ')"/>';
            }
        }
        return [d, leaves];
    }

    var DRAPES_BACK = drapes(24, 296, 14, 0, 70, 230, 14, 3);
    var DRAPES_MID = drapes(32, 288, 15, 30, 78, 214, 12, 7);
    var DRAPES_FRONT = drapes(44, 276, 16, 38, 90, 192, 10, 13);

    function ribbon(x, y, mod) {
        return '<g class="pg-ribbon pg-ribbon--' + mod + '" transform="translate(' + x + ' ' + y + ')">' +
            '<path d="M0 0C-3-5-10-7-10-2S-4 3 0 0ZM0 0C3-5 10-7 10-2S4 3 0 0Z"/>' +
            '<path d="M-1 1L-5 13L-2 12L0 3ZM1 1L5 13L2 12L0 3Z"/><circle r="2.2"/></g>';
    }

    // Wierzba płacząca — „drzewo wspomnień”: kopuła korony, trzy warstwy opadających gałązek (środek odsłania
    // pień), wstążki, zawieszki (serce, gwiazdka) i dwa lampiony
    var WILLOW_SVG =
        '<svg viewBox="0 0 320 270" preserveAspectRatio="xMidYMax meet"' + NS + '>' +
        '<ellipse class="pg-w-shadow" cx="160" cy="265" rx="112" ry="6"/>' +
        '<path class="pg-w-drape pg-w-drape--back" d="' + DRAPES_BACK[0] + '"/>' +
        '<path class="pg-w-trunk" d="M142 270C150 248 153 224 152 198C151 172 148 152 151 130C153 116 156 106 161 98L169 100' +
        'C165 112 163 126 165 142C167 162 170 186 170 210C170 234 172 254 180 270Z"/>' +
        '<path class="pg-w-branch" d="M152 128C138 112 120 102 96 96M166 120C178 104 198 94 224 90M161 100C160 84 163 70 170 58"/>' +
        '<g class="pg-w-crown"><path d="M24 118C18 78 50 36 98 24C126 8 194 8 222 24C270 36 302 78 296 118C258 132 62 132 24 118Z"/>' +
        '<circle cx="62" cy="70" r="26"/><circle cx="94" cy="44" r="30"/><circle cx="132" cy="28" r="30"/><circle cx="174" cy="24" r="32"/>' +
        '<circle cx="214" cy="36" r="30"/><circle cx="252" cy="58" r="28"/><circle cx="278" cy="90" r="22"/><circle cx="40" cy="98" r="20"/></g>' +
        '<g class="pg-w-crown-hi"><ellipse cx="118" cy="30" rx="30" ry="11"/><ellipse cx="176" cy="22" rx="26" ry="9"/>' +
        '<ellipse cx="74" cy="58" rx="18" ry="7"/><ellipse cx="236" cy="44" rx="18" ry="7"/></g>' +
        '<path class="pg-w-drape pg-w-drape--mid" d="' + DRAPES_MID[0] + '"/>' +
        '<g class="pg-w-leaf pg-w-leaf--mid">' + DRAPES_MID[1] + '</g>' +
        '<path class="pg-w-drape pg-w-drape--front" d="' + DRAPES_FRONT[0] + '"/>' +
        '<g class="pg-w-leaf pg-w-leaf--front">' + DRAPES_FRONT[1] + '</g>' +
        '<path class="pg-w-thread" d="M176 112V140M122 114V138M60 108V138M262 106V138"/>' +
        '<path class="pg-w-heart" d="M176 152c-5-3.6-8.5-6.4-8.5-9.6a4.3 4.3 0 0 1 8.5-1.2 4.3 4.3 0 0 1 8.5 1.2c0 3.2-3.5 6-8.5 9.6z"/>' +
        '<path class="pg-w-star" d="M122 136l2.4 5 5.4.6-4 3.7 1.1 5.3-4.9-2.7-4.9 2.7 1.1-5.3-4-3.7 5.4-.6z"/>' +
        '<g class="pg-w-lamp"><rect x="55" y="137" width="10" height="3" rx="1.2"/><ellipse cx="60" cy="150" rx="8.5" ry="10"/>' +
        '<rect x="55" y="159" width="10" height="3" rx="1.2"/><rect x="257" y="137" width="10" height="3" rx="1.2"/>' +
        '<ellipse cx="262" cy="150" rx="8.5" ry="10"/><rect x="257" y="159" width="10" height="3" rx="1.2"/></g>' +
        '<path class="pg-w-lamp-rib" d="M60 140v20M55 143q-3 7 0 14M65 143q3 7 0 14M262 140v20M257 143q-3 7 0 14M267 143q3 7 0 14"/>' +
        ribbon(84, 178, 'pink') + ribbon(112, 160, 'lilac') + ribbon(212, 166, 'blue') + ribbon(240, 190, 'yellow') +
        '<path class="pg-w-grass" d="M112 270q8-14 12-2q4-12 9 0q5-10 8 2zM176 270q6-12 10 0q5-12 9 0q4-9 8 2z"/>' +
        '</svg>' +
        // Poświata lampionów (wieczór, noc) — w % rysunku 320×270
        '<span class="pg-w-glow pg-w-glow--l"></span><span class="pg-w-glow pg-w-glow--r"></span>';

    // Kamienna ścieżka do nagrobków (kamienie maleją w głąb; preserveAspectRatio none — same wypełnienia)
    var STONES = [[100, 278, 46, 16], [84, 236, 38, 13], [108, 198, 32, 11], [92, 164, 27, 9.5], [106, 134, 23, 8],
        [96, 108, 19, 7], [104, 84, 16, 6], [98, 62, 13, 5], [102, 42, 11, 4.3], [99, 24, 9, 3.6], [101, 8, 7.5, 3]];
    var PATH_SVG =
        '<svg class="pg-path" viewBox="0 0 200 300" preserveAspectRatio="none"' + NS + '>' +
        STONES.map(function (s) {
            return '<ellipse class="pg-stone-shade" cx="' + s[0] + '" cy="' + n(s[1] + s[3] * 0.32) + '" rx="' + s[2] + '" ry="' + s[3] + '"/>' +
                '<ellipse class="pg-stone" cx="' + s[0] + '" cy="' + s[1] + '" rx="' + s[2] + '" ry="' + s[3] + '"/>' +
                '<ellipse class="pg-stone-hi" cx="' + n(s[0] - s[2] * 0.3) + '" cy="' + n(s[1] - s[3] * 0.35) + '" rx="' + n(s[2] * 0.35) + '" ry="' + n(s[3] * 0.28) + '"/>';
        }).join('') + '</svg>';

    // Latarenka ogrodowa na haku (przy wejściu na ścieżkę); świeci wieczorem i nocą
    var LANTERN_HTML =
        '<svg viewBox="0 0 50 130"' + NS + '>' +
        '<path class="pg-lt-pole" d="M14 130V22C14 12 20 6 28 6S40 12 40 20V27"/>' +
        '<path class="pg-lt-grass" d="M4 130q4-12 7-1q3-10 6 0q4-9 6 1z"/>' +
        '<path class="pg-lt-roof" d="M30 37h20l-4-6H34z"/><circle class="pg-lt-roof" cx="40" cy="29" r="2.2"/>' +
        '<rect class="pg-lt-glass" x="32" y="37" width="16" height="25" rx="3"/>' +
        '<rect class="pg-lt-candle" x="37.6" y="51" width="4.8" height="9" rx="1.4"/>' +
        '<path class="pg-lt-flame" d="M40 42.5c1.8 2.3 2.6 3.7 2.6 4.8a2.6 2.6 0 0 1-5.2 0c0-1.1.8-2.5 2.6-4.8z"/>' +
        '<path class="pg-lt-frame" d="M32 49.5h16M40 37v3"/>' +
        '<rect class="pg-lt-roof" x="31" y="61" width="18" height="4" rx="2"/>' +
        '</svg><span class="pg-lt-glow"></span>';

    // Ławeczka z bukiecikiem i serduszkiem w oparciu
    var BENCH_SVG =
        '<svg class="pg-bench" viewBox="0 0 130 84"' + NS + '>' +
        '<ellipse class="pg-shadow" cx="65" cy="80" rx="60" ry="4"/>' +
        '<rect class="pg-bn-dark" x="16" y="8" width="7" height="42" rx="2"/><rect class="pg-bn-dark" x="107" y="8" width="7" height="42" rx="2"/>' +
        '<rect class="pg-bn-wood" x="8" y="10" width="114" height="8" rx="4"/><rect class="pg-bn-wood" x="8" y="22" width="114" height="8" rx="4"/>' +
        '<rect class="pg-bn-wood" x="8" y="34" width="114" height="8" rx="4"/>' +
        '<path class="pg-bn-heart" d="M65 31.5c-3-2.2-5-3.8-5-5.7a2.5 2.5 0 0 1 5-.7 2.5 2.5 0 0 1 5 .7c0 1.9-2 3.5-5 5.7z"/>' +
        '<rect class="pg-bn-dark" x="14" y="56" width="7" height="24" rx="2"/><rect class="pg-bn-dark" x="109" y="56" width="7" height="24" rx="2"/>' +
        '<rect class="pg-bn-wood" x="4" y="46" width="122" height="9" rx="4"/><rect class="pg-bn-dark" x="6" y="53" width="118" height="4" rx="2"/>' +
        '<path class="pg-stem" d="M88 46l8-12M92 46l4-14M96 46l0-13"/>' +
        '<circle class="pg-fl-pink" cx="96" cy="33" r="3.6"/><circle class="pg-fl-blue" cx="100" cy="31" r="3.2"/>' +
        '<circle class="pg-fl-yellow" cx="92" cy="31" r="3"/><circle class="pg-fl-c" cx="96" cy="33" r="1.3"/>' +
        '<path class="pg-bq-wrap" d="M84 47l8-9h8l2 9z"/>' +
        '</svg>';

    // Staw z liliami, trzciną i (nocą) odbiciem księżyca
    var POND_SVG =
        '<svg class="pg-pond" viewBox="0 0 240 112"' + NS + '>' +
        '<defs><linearGradient id="pgPondWater" x1="0" y1="0" x2="0" y2="1">' +
        '<stop class="pg-pd-w1" offset="0"/><stop class="pg-pd-w2" offset="1"/></linearGradient></defs>' +
        '<ellipse class="pg-pd-bank" cx="122" cy="74" rx="116" ry="36"/>' +
        '<ellipse cx="122" cy="72" rx="102" ry="28" fill="url(#pgPondWater)"/>' +
        '<path class="pg-pd-hi" d="M70 62q20-6 40 0M150 84q14-4 28 0M182 66q8-2 16 0"/>' +
        '<ellipse class="pg-pd-moon" cx="152" cy="70" rx="13" ry="3.2"/>' +
        '<path class="pg-pd-pad" d="M82 78a15 6.2 0 1 1 6-5.6L82 76z"/><path class="pg-pd-pad" d="M170 64a11 4.8 0 1 1 5-4.2L170 62z"/>' +
        '<path class="pg-pd-pad" d="M146 88a9 4 0 1 1 4-3.4L146 86z"/>' +
        '<g class="pg-pd-lily"><ellipse cx="78" cy="72" rx="2.6" ry="6" transform="rotate(-50 78 72)"/>' +
        '<ellipse cx="86" cy="72" rx="2.6" ry="6" transform="rotate(50 86 72)"/><ellipse cx="82" cy="70" rx="2.8" ry="6.6"/>' +
        '<ellipse cx="76" cy="75" rx="2.2" ry="5" transform="rotate(-80 76 75)"/><ellipse cx="88" cy="75" rx="2.2" ry="5" transform="rotate(80 88 75)"/></g>' +
        '<circle class="pg-pd-lily-c" cx="82" cy="73" r="2.2"/>' +
        '<g class="pg-pd-rock"><ellipse cx="22" cy="80" rx="8" ry="5"/><ellipse cx="34" cy="96" rx="9" ry="5"/>' +
        '<ellipse cx="210" cy="96" rx="9" ry="5"/><ellipse cx="226" cy="76" rx="7" ry="4.5"/></g>' +
        '<path class="pg-pd-reed" d="M28 82C27 64 26 50 24 32M38 84C38 66 40 54 42 38M18 84C17 70 15 60 12 48"/>' +
        '<path class="pg-pd-leaf" d="M30 84C20 70 14 58 8 52C18 60 26 70 34 84ZM36 84C44 72 50 64 58 60C52 68 46 76 42 86Z"/>' +
        '<rect class="pg-pd-cat" x="21.5" y="30" width="5" height="15" rx="2.5"/><rect class="pg-pd-cat" x="39.5" y="36" width="5" height="14" rx="2.5"/>' +
        '</svg>';

    function forgetMeNot(x, y, s) {
        var out = '';
        for (var i = 0; i < 5; i++) {
            var a = (i * 72 - 90) * Math.PI / 180;
            out += '<circle class="pg-fl-blue" cx="' + n(x + Math.cos(a) * s * 0.55) + '" cy="' + n(y + Math.sin(a) * s * 0.55) + '" r="' + n(s * 0.42) + '"/>';
        }
        return out + '<circle class="pg-fl-c" cx="' + x + '" cy="' + y + '" r="' + n(s * 0.26) + '"/>';
    }

    function bloom(x, y, s, cls) {
        var out = '';
        for (var i = 0; i < 5; i++) {
            var a = (i * 72 - 90) * Math.PI / 180;
            out += '<circle class="' + cls + '" cx="' + n(x + Math.cos(a) * s * 0.5) + '" cy="' + n(y + Math.sin(a) * s * 0.5) + '" r="' + n(s * 0.46) + '"/>';
        }
        return out + '<circle class="pg-fl-c" cx="' + x + '" cy="' + y + '" r="' + n(s * 0.3) + '"/>';
    }

    function daisy(x, y, s) {
        var out = '';
        for (var i = 0; i < 8; i++) {
            var deg = i * 45;
            var a = deg * Math.PI / 180;
            var cx = n(x + Math.cos(a) * s * 0.55);
            var cy = n(y + Math.sin(a) * s * 0.55);
            out += '<ellipse class="pg-fl-white" cx="' + cx + '" cy="' + cy + '" rx="' + n(s * 0.42) + '" ry="' + n(s * 0.2) + '" transform="rotate(' + deg + ' ' + cx + ' ' + cy + ')"/>';
        }
        return out + '<circle class="pg-fl-yellow" cx="' + x + '" cy="' + y + '" r="' + n(s * 0.3) + '"/>';
    }

    var LEAVES = '<path class="pg-leaf" d="M10 44C12 32 18 24 26 20C20 30 18 36 18 44ZM54 44C52 34 46 26 38 22C44 32 46 38 46 44Z' +
        'M30 44C29 36 31 30 34 26C35 32 35 38 34 44Z"/>';
    var STEMS = '<path class="pg-stem" d="M14 44V24M28 44V16M42 44V24M22 44V32M50 44V34"/>';
    var FLOWERS = {
        a: LEAVES + STEMS + forgetMeNot(14, 22, 10) + forgetMeNot(28, 14, 11) + forgetMeNot(42, 22, 10) + forgetMeNot(22, 32, 8) + forgetMeNot(50, 34, 8),
        b: LEAVES + STEMS + daisy(16, 22, 12) + bloom(38, 14, 11, 'pg-fl-pink') + daisy(52, 30, 9) + forgetMeNot(28, 32, 8),
        c: LEAVES + STEMS + bloom(12, 26, 9, 'pg-fl-pink') + bloom(28, 16, 10, 'pg-fl-yellow') + forgetMeNot(44, 22, 10) + daisy(54, 34, 7)
    };

    function flowers(kind, mod) {
        return '<svg class="pg-flowers pg-flowers--' + mod + '" viewBox="0 0 64 44"' + NS + '>' + FLOWERS[kind] + '</svg>';
    }

    // Kwitnący krzew (hortensja) i kępki trawy — wypełniają środek łąki między kwaterą a przodem
    function bush(mod) {
        return '<svg class="pg-bush pg-bush--' + mod + '" viewBox="0 0 120 76"' + NS + '>' +
            '<ellipse class="pg-shadow" cx="60" cy="72" rx="54" ry="4"/>' +
            '<g class="pg-bush-leaf"><circle cx="30" cy="48" r="24"/><circle cx="58" cy="34" r="30"/><circle cx="88" cy="46" r="26"/>' +
            '<rect x="10" y="46" width="100" height="26" rx="13"/></g>' +
            '<g class="pg-bush-hi"><circle cx="46" cy="20" r="9"/><circle cx="80" cy="28" r="7"/></g>' +
            bloom(34, 42, 11, 'pg-fl-pink') + bloom(60, 24, 12, 'pg-fl-lilac') + bloom(88, 40, 11, 'pg-fl-blue') +
            bloom(50, 56, 10, 'pg-fl-blue') + bloom(78, 58, 10, 'pg-fl-pink') + bloom(20, 60, 8, 'pg-fl-lilac') + '</svg>';
    }

    var TUFT_SVG = '<path class="pg-tuft-blade" d="M2 16Q6 6 9 0Q9 8 11 16ZM10 16Q14 4 18 2Q15 9 16 16ZM17 16Q22 8 28 6Q22 11 22 16Z"/>';

    function tufts(count) {
        var out = '';
        for (var i = 1; i <= count; i++) out += '<svg class="pg-tuft pg-tuft--' + i + '" viewBox="0 0 30 16"' + NS + '>' + TUFT_SVG + '</svg>';
        return out;
    }

    var BUTTERFLY_SVG =
        '<svg viewBox="0 0 28 22"' + NS + '>' +
        '<g class="pg-bf-wing pg-bf-wing--l"><path d="M13 10C8 1 1 2 2 8C3 12 9 12 13 11Z"/><path d="M13 12C9 13 4 16 6 19C8 21 12 17 13 13Z"/>' +
        '<circle class="pg-bf-spot" cx="6" cy="7" r="1.6"/></g>' +
        '<g class="pg-bf-wing pg-bf-wing--r"><path d="M15 10C20 1 27 2 26 8C25 12 19 12 15 11Z"/><path d="M15 12C19 13 24 16 22 19C20 21 16 17 15 13Z"/>' +
        '<circle class="pg-bf-spot" cx="22" cy="7" r="1.6"/></g>' +
        '<rect class="pg-bf-body" x="13" y="7" width="2" height="10" rx="1"/><path class="pg-bf-ant" d="M13.6 7.4L11 3M14.4 7.4L17 3"/></svg>';

    /** count × <span class="base extra base--i"> (świetliki, płatki, dmuchawce — pozycje i ruch w CSS). */
    function spans(base, extra, count) {
        var out = '';
        for (var i = 1; i <= count; i++) out += '<span class="' + base + (extra ? ' ' + extra : '') + ' ' + base + '--' + i + '"></span>';
        return out;
    }

    var SKY_HTML =
        starLayer('a', 11, 26) + starLayer('b', 23, 22) + starLayer('c', 37, 16) + SPARKLES +
        '<span class="pg-sun"></span>' +
        '<span class="pg-moon">' + MOON_SVG + '</span>' +
        '<span class="pg-shoot"></span>' +
        '<span class="pg-cloud pg-cloud--1">' + CLOUD_SVG + '</span>' +
        '<span class="pg-cloud pg-cloud--2">' + CLOUD_SVG + '</span>' +
        HILLS_SVG +
        '<span class="pg-willow">' + WILLOW_SVG + '</span>' +
        '<span class="pg-mist"></span>' +
        FENCE_SVG +
        spans('pg-fly', 'pg-fly--sky', 5) + spans('pg-seed', '', 3);

    var FORE_HTML =
        bush(1) + bush(2) + tufts(6) +
        '<span class="pg-pathway">' + PATH_SVG + '</span>' +
        '<span class="pg-lantern pg-lantern--l">' + LANTERN_HTML + '</span>' +
        '<span class="pg-lantern pg-lantern--r">' + LANTERN_HTML + '</span>' +
        BENCH_SVG + POND_SVG +
        flowers('a', 1) + flowers('b', 2) + flowers('c', 3) + flowers('a', 4) + flowers('b', 5) + flowers('c', 6) +
        flowers('a', 7) + flowers('b', 8) +
        '<span class="pg-butterfly pg-butterfly--1">' + BUTTERFLY_SVG + '</span>' +
        '<span class="pg-butterfly pg-butterfly--2">' + BUTTERFLY_SVG + '</span>' +
        spans('pg-fly', 'pg-fly--fore', 8) + spans('pg-petal', '', 6);

    // Znicz przy nagrobku: zgaszony (dziś można zapalić) albo zapalony (światełko gracza)
    var ZNICZ_SVG =
        '<svg viewBox="0 0 24 36"' + NS + '>' +
        '<ellipse class="zn-shadow" cx="12" cy="34.4" rx="9" ry="1.6"/>' +
        '<ellipse class="zn-inner" cx="12" cy="22" rx="6" ry="8"/>' +
        '<path class="zn-glass" d="M4.5 14h15l-1.6 17.2a3 3 0 0 1-3 2.8H9.1a3 3 0 0 1-3-2.8z"/>' +
        '<path class="zn-band" d="M5.3 21h13.4l-.25 3H5.55z"/>' +
        '<path class="zn-heart" d="M12 30.6c-1.9-1.4-3.1-2.4-3.1-3.6a1.55 1.55 0 0 1 3.1-.5 1.55 1.55 0 0 1 3.1.5c0 1.2-1.2 2.2-3.1 3.6z"/>' +
        '<path class="zn-shine" d="M7.4 16.5l.9 11.5"/>' +
        '<rect class="zn-rim" x="3.5" y="12" width="17" height="3" rx="1.5"/>' +
        '<path class="zn-wick" d="M12 12V9.4"/>' +
        '<g class="zn-flame-wrap"><g class="zn-flame">' +
        '<path class="zn-flame-out" d="M12 .8c2.6 3.2 3.6 5.2 3.6 6.8a3.6 3.6 0 0 1-7.2 0c0-1.6 1-3.6 3.6-6.8z"/>' +
        '<path class="zn-flame-core" d="M12 4.4c1.2 1.6 1.7 2.6 1.7 3.4a1.7 1.7 0 0 1-3.4 0c0-.8.5-1.8 1.7-3.4z"/></g></g>' +
        '</svg>';

    var SPRIG_SVG =
        '<svg class="pets-garden__empty-icon" viewBox="0 0 40 32"' + NS + '>' +
        '<path class="pg-stem" d="M20 31V14M20 22c-4-1-7-4-8-8M20 19c4-1 7-3 8-7"/>' +
        forgetMeNot(20, 10, 9) + forgetMeNot(10, 12, 7) + forgetMeNot(30, 10, 7) + '</svg>';

    function create(ctx, host) {
        var u = ctx.u;
        var el = u.el;
        var graveViews = [];
        var slotViews = [];
        var openGraveId = null;      // pet_id nagrobka w otwartym oknie
        var openGraveSig = null;
        var albumOpen = false;
        var lastState = null;

        // --- scena ---------------------------------------------------------------------------
        var stage = el('div', 'pets-stage');
        var sign = el('button', 'pets-garden__sign');
        sign.type = 'button';
        sign.dataset.gardenAction = 'album';
        sign.innerHTML = BOOK_SVG;
        sign.appendChild(el('span', 'pets-garden__sign-text', 'Album gatunków'));
        var signCount = el('span', 'pets-album__count');
        sign.appendChild(signCount);

        var scroll = el('div', 'pets-scroll pets-garden');
        scroll.setAttribute('data-window-backdrop', '');
        var meadow = el('section', 'pets-garden__meadow');
        meadow.setAttribute('aria-labelledby', 'petsGraveTitle');
        var graveTitle = el('h2', 'pets-garden__title', 'Wspomnienia');
        graveTitle.id = 'petsGraveTitle';

        // Pas nieba, kwatera z nagrobkami, pas przedni (ozdoby: aria-hidden, bez zdarzeń)
        var sky = el('div', 'pets-garden__sky');
        sky.setAttribute('aria-hidden', 'true');
        sky.innerHTML = SKY_HTML;
        var plot = el('div', 'pets-garden__plot');
        var graves = el('div', 'pets-graves');
        var gravesEmpty = el('p', 'pets-garden__empty');
        gravesEmpty.innerHTML = SPRIG_SVG;
        gravesEmpty.appendChild(el('span', 'pets-garden__empty-text',
            'Tu jest cicho i spokojnie. Nikt jeszcze nie odszedł do gwiazd — oby tak zostało.'));
        plot.appendChild(graves);
        plot.appendChild(gravesEmpty);
        var fore = el('div', 'pets-garden__fore');
        fore.setAttribute('aria-hidden', 'true');
        fore.innerHTML = FORE_HTML;

        meadow.appendChild(graveTitle);
        meadow.appendChild(sky);
        meadow.appendChild(plot);
        meadow.appendChild(fore);
        scroll.appendChild(meadow);
        stage.appendChild(sign);
        stage.appendChild(scroll);
        host.appendChild(stage);

        var win = window.PetsSceneWindow ? window.PetsSceneWindow.attach(host) : null;

        // --- album (treść okna; budowana raz, rigi tylko przy otwartym oknie) ------------------
        var albumBox = el('div', 'pets-garden__album');
        var albumTitle = el('h2', 'pets-window__title');
        albumTitle.id = 'petsAlbumTitle';
        albumTitle.appendChild(document.createTextNode('Album gatunków '));
        var albumCount = el('span', 'pets-album__count');
        albumTitle.appendChild(albumCount);
        var album = el('div', 'pets-album');
        albumBox.appendChild(albumTitle);
        albumBox.appendChild(el('p', 'pets-window__text', 'Każde jajko to losowy z ośmiu gatunków. Zbierz wszystkie!'));
        albumBox.appendChild(album);

        // --- nagrobki ------------------------------------------------------------------------
        function graveLabel(entry) {
            return 'Nagrobek: ' + (entry.name || u.speciesName(entry.species)) + ', ' + u.speciesName(entry.species) +
                (entry.can_light ? ' — możesz dziś zapalić światełko' : ' — dziś świeci światełko');
        }

        function graveView(entry) {
            var btn = el('button', 'pets-grave');
            btn.type = 'button';
            btn.dataset.gardenAction = 'grave';
            btn.dataset.petId = String(entry.pet_id);
            var art = el('span', 'pets-grave__art');
            btn.appendChild(art);
            var rig = window.PetRig ? window.PetRig.mountMemorial(art, { species: entry.species, size: 'mini', lit: !entry.can_light }) : null;
            // Światełko gracza: ciepła poświata + znicz przed nagrobkiem (ozdoby — opis w aria-label przycisku)
            var glow = el('span', 'pets-grave__glow');
            glow.setAttribute('aria-hidden', 'true');
            art.appendChild(glow);
            var znicz = el('span', 'pets-grave__znicz');
            znicz.setAttribute('aria-hidden', 'true');
            znicz.innerHTML = ZNICZ_SVG;
            art.appendChild(znicz);
            btn.appendChild(el('span', 'pets-grave__name', entry.name || u.speciesName(entry.species)));
            var flame = el('span', 'pets-grave__flame');
            flame.setAttribute('aria-hidden', 'true');
            flame.innerHTML = u.icon('flame', 'pets-grave__flame-icon');
            btn.appendChild(flame);
            var view = { el: btn, rig: rig, key: '', flame: flame };
            updateGrave(view, entry);
            return view;
        }

        function updateGrave(view, entry) {
            view.flame.hidden = !entry.can_light;
            view.el.classList.toggle('is-lit', !entry.can_light);
            view.el.setAttribute('aria-label', graveLabel(entry));
            if (view.rig && typeof view.rig.update === 'function') view.rig.update({ lit: !entry.can_light });
        }

        /** Rząd płomyków „Światełka: N” (ozdoba; liczba jest w tekście obok). */
        function flameRow(count) {
            var row = el('span', 'pets-grave__flames');
            row.setAttribute('aria-hidden', 'true');
            var shown = Math.min(count, MAX_FLAMES);
            var html = '';
            for (var i = 0; i < shown; i++) html += u.icon('flame', 'pets-grave__flames-icon');
            row.innerHTML = html;
            if (count > MAX_FLAMES) row.appendChild(el('span', 'pets-grave__flames-more', '+' + (count - MAX_FLAMES)));
            return row;
        }

        function graveContent(entry) {
            var box = el('div', 'pets-grave-info');
            var title = el('h2', 'pets-window__title', entry.name || u.speciesName(entry.species));
            title.id = 'petsGraveWindowTitle';
            box.appendChild(title);
            box.appendChild(el('p', 'pets-grave-info__lead', u.speciesName(entry.species) + ' · odszedł do gwiazd'));
            box.appendChild(el('p', 'pets-grave__meta', u.formatDate(entry.hatched_at) + ' – ' + u.formatDate(entry.died_at)));
            box.appendChild(el('p', 'pets-grave__meta', 'Wiek: ' + u.daysText(entry.age_days) + ' · ' + u.daysText(entry.care_days) + ' opieki'));
            var lights = parseInt(entry.lights_count, 10) || 0;
            var lightsRow = el('p', 'pets-grave__lights');
            lightsRow.appendChild(el('span', 'pets-grave__lights-text', 'Światełka: ' + lights));
            if (lights > 0) lightsRow.appendChild(flameRow(lights));
            box.appendChild(lightsRow);
            var actions = el('div', 'pets-window__actions');
            if (entry.can_light) {
                box.appendChild(el('p', 'pets-grave-info__note', 'Zapal światełko — w ogrodzie zrobi się trochę cieplej.'));
                var light = u.button('Zapal światełko', 'flame', 'primary', { gardenAction: 'light', petId: String(entry.pet_id) });
                light.setAttribute('data-window-key', 'light');
                actions.appendChild(light);
            } else {
                var lit = el('p', 'pets-grave__lit');
                lit.innerHTML = u.icon('flame', 'pets-grave__lit-icon');
                lit.appendChild(el('span', null, 'Dziś już świeci światełko'));
                actions.appendChild(lit);
            }
            box.appendChild(actions);
            return box;
        }

        function graveSig(entry) {
            return [entry.pet_id, entry.name, entry.species, entry.lights_count, entry.can_light, entry.age_days, entry.care_days].join('|');
        }

        function memorialById(state, id) {
            var list = (state && state.album) || [];
            for (var i = 0; i < list.length; i++) {
                if (list[i].status === 'memorial' && list[i].pet_id === id) return list[i];
            }
            return null;
        }

        // --- album: karty gatunków ------------------------------------------------------------
        function slotView(entry, pet) {
            var card = el('article', 'pets-album__card pets-album__card--' + entry.status);
            var art = el('div', 'pets-album__art');
            var info = el('div', 'pets-album__info');
            card.appendChild(art);
            card.appendChild(info);
            var R = window.PetRig;
            var rig = null;
            if (entry.status === 'alive' && pet) {
                if (R) {
                    rig = R.mount(art, {
                        species: entry.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: pet.asleep, size: 'mini',
                        need: R.needOf ? R.needOf(pet) : null
                    });
                }
                info.appendChild(el('h3', 'pets-album__name', pet.name || u.speciesName(entry.species)));
                info.appendChild(el('p', 'pets-album__meta', u.speciesName(entry.species) + ' · ' + (STAGE_LABEL[pet.stage] || '') +
                    (pet.hospital ? ' · w szpitalu' : '')));
            } else if (entry.status === 'memorial') {
                if (R) rig = R.mountMemorial(art, { species: entry.species, size: 'mini', lit: !entry.can_light });
                info.appendChild(el('h3', 'pets-album__name', u.speciesName(entry.species)));
                info.appendChild(el('p', 'pets-album__meta', (entry.name ? 'Pupil ' + entry.name : 'Twój pupil') + ' odszedł do gwiazd'));
            } else {
                art.classList.add('pets-album__art--silhouette');
                if (R) rig = R.mount(art, { species: entry.species, stage: 'dorosly', size: 'mini' });
                info.appendChild(el('h3', 'pets-album__name', 'Nieodkryty'));
                info.appendChild(el('p', 'pets-album__meta', 'Wykluj jajko, żeby go poznać'));
            }
            return { el: card, rig: rig, key: '' };
        }

        function sync(list, views, box, keyOf, make, onSame) {
            list.forEach(function (item, i) {
                var key = keyOf(item);
                var view = views[i];
                if (view && view.key === key) {
                    if (onSame) onSame(view, item);
                    return;
                }
                var fresh = make(item);
                fresh.key = key;
                if (view) {
                    if (view.rig) view.rig.destroy();
                    box.replaceChild(fresh.el, view.el);
                } else {
                    box.appendChild(fresh.el);
                }
                views[i] = fresh;
            });
            while (views.length > list.length) {
                var old = views.pop();
                if (old.rig) old.rig.destroy();
                if (old.el.parentNode) old.el.parentNode.removeChild(old.el);
            }
        }

        function syncAlbum(state) {
            var entries = state.album || [];
            var petsById = {};
            (state.pets || []).forEach(function (p) { petsById[p.id] = p; });
            var withPet = entries.map(function (e) { return { e: e, pet: e.status === 'alive' ? petsById[e.pet_id] : null }; });
            sync(withPet, slotViews, album, function (x) {
                var e = x.e, p = x.pet;
                return [e.species, e.status, e.pet_id, e.name, e.can_light, p ? p.name : '', p ? p.stage : '', p && p.hospital ? 'h' : ''].join('|');
            }, function (x) { return slotView(x.e, x.pet); }, function (view, x) {
                if (x.pet && view.rig) {
                    view.rig.update({ stage: x.pet.stage, stars: x.pet.stars, mood: x.pet.mood, asleep: x.pet.asleep });
                    if (typeof view.rig.setNeed === 'function' && window.PetRig.needOf) view.rig.setNeed(window.PetRig.needOf(x.pet));
                }
            });
        }

        // --- okna ----------------------------------------------------------------------------
        function closeAlbumRigs() {
            albumOpen = false;
            sync([], slotViews, album, null, null);
        }

        function onWindowClosed() {
            openGraveId = null;
            openGraveSig = null;
            if (albumOpen) closeAlbumRigs();
        }

        function openAlbum() {
            if (!win || !lastState) return;
            openGraveId = null;
            openGraveSig = null;
            albumOpen = true;
            syncAlbum(lastState);
            win.open({ content: albumBox, labelledBy: albumTitle.id, returnFocus: sign, onClose: onWindowClosed, closeLabel: 'Zamknij album' });
        }

        function openGrave(id, returnFocus) {
            var entry = memorialById(lastState, id);
            if (!win || !entry) return;
            if (albumOpen) closeAlbumRigs();
            openGraveId = id;
            openGraveSig = graveSig(entry);
            win.open({
                content: graveContent(entry), labelledBy: 'petsGraveWindowTitle', returnFocus: returnFocus || null,
                onClose: onWindowClosed, closeLabel: 'Zamknij szczegóły nagrobka'
            });
            reveal(returnFocus);
        }

        /** Arkusz (< 1024 px): wybrany nagrobek ma zostać widoczny nad arkuszem — przewija wnętrze ogrodu. */
        function reveal(node) {
            if (!node || !win || !win.isOpen()) return;
            var sheet = parseFloat(host.style.getPropertyValue('--window-h')) || 0;
            if (!sheet) return;
            var box = host.getBoundingClientRect();
            var r = node.getBoundingClientRect();
            var limit = box.bottom - sheet - 12;
            if (r.bottom > limit) scroll.scrollTop += r.bottom - limit;
        }

        // --- render --------------------------------------------------------------------------
        function render(state) {
            lastState = state;
            var entries = state.album || [];
            var memorials = entries.filter(function (a) { return a.status === 'memorial'; });
            sync(memorials, graveViews, graves, function (e) {
                return [e.pet_id, e.name, e.species].join('|');
            }, graveView, updateGrave);
            graves.hidden = !memorials.length;
            gravesEmpty.hidden = !!memorials.length;
            meadow.classList.toggle('is-empty', !memorials.length);

            var known = entries.filter(function (a) { return a.status !== 'unknown'; }).length;
            var countText = known + '/' + entries.length;
            [signCount, albumCount].forEach(function (c) {
                c.textContent = countText;
                c.setAttribute('aria-label', 'Odkryte gatunki: ' + known + ' z ' + entries.length);
            });
            if (albumOpen) syncAlbum(state);

            if (openGraveId != null && win && win.isOpen()) {
                var entry = memorialById(state, openGraveId);
                if (!entry) {
                    win.close({ restoreFocus: true });
                } else if (graveSig(entry) !== openGraveSig) {
                    openGraveSig = graveSig(entry);
                    win.replace(graveContent(entry));
                }
            }
        }

        host.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-garden-action]');
            if (!btn || !host.contains(btn) || btn.disabled) return;
            var action = btn.dataset.gardenAction;
            if (action === 'album') {
                openAlbum();
            } else if (action === 'grave') {
                openGrave(parseInt(btn.dataset.petId, 10), btn);
            } else if (action === 'light') {
                u.setBusy(btn, true);
                ctx.send('/' + parseInt(btn.dataset.petId, 10) + '/swiatelko', {}).then(function () {
                    if (window.Haptics) window.Haptics.tap();
                }, function () { u.setBusy(btn, false); });
            }
        });

        return {
            enter: function () {},
            // Ukryta scena nie trzyma żywych rigów ani otwartego okna (wystrój nie ma timerów — tylko CSS)
            leave: function () {
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                sync([], graveViews, graves, null, null);
                closeAlbumRigs();
            },
            render: render
        };
    }

    W.scenes.ogrod = {
        title: 'Ogród wspomnień',
        create: create
    };
})();
