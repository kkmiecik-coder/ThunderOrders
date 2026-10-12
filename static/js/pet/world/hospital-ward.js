/**
 * Świat pupili — scena „izba” = Izba przyjęć (spec v3.1 §4.4).
 *
 * - Sala z łóżkami: pupil w pozie `bed` (rig: łóżeczko z kołderką), przy leczonych kroplówka, tabliczka
 *   „Burek · jeszcze ~3 h”. Wyzdrowiały: łóżko jaśniejsze, pupil szczęśliwy (need: happy) z serduszkami,
 *   zielona tabliczka „Zdrowy! Odbierz” + „tęskni za domem”. Wolne łóżka zaścielone i przygaszone.
 * - Miejsc max(3, liczba pupili w szpitalu), a gdy w domku ktoś choruje — o jedno wolne więcej (inaczej przy
 *   pełnej sali nie byłoby gdzie go przyjąć); pupil zostaje w swoim łóżku, przyjęty z wolnego łóżka trafia
 *   właśnie do niego. Siatka (CSS, wg sceny właściwej): szeroko do 4 w rzędzie, średnio po 3, wąsko albo
 *   w scenie pionowej (tablet pionowo, sala obok karty okna) po 2 — wtedy w dwóch rzędach, za to większe.
 * - Klik w łóżko z pupilem = okno sceny (fokus zostaje na łóżku): imię, pasek leczenia, czas / tęsknota,
 *   „Odbierz” (wyzdrowiały) albo „Zabierz wcześniej” z potwierdzeniem („Tak, zabieram” / „Zostaw
 *   w szpitalu”) — teksty jak dawniej. Klik w pupila przy jego otwartym oknie = pat pat (paczki w pets.js).
 *   Po odbiorze → domek z panelem pupila.
 * - Wolne łóżko przy chorych w domku: pulsujący „+”; klik = okno „Kogo przyjąć?” (mini rig, imię, nastrój,
 *   „wyzdrowieje w najwyżej N h” z config.hospital_hours, „Przyjmij” → POST /<id>/szpital → pupil w tym
 *   łóżku, okno pokazuje jego). Bez chorych: okno „Wolne łóżko”.
 * - `?pupil=ID` otwiera okno pupila w szpitalu; pupil spoza szpitala / nieistniejący → sala bez okna.
 * - Zmiana stanu przy otwartym oknie: pupil leży → treść odświeżona; zniknął (odebrany w innej karcie,
 *   odszedł) → okno się zamyka, fokus na scenie.
 * - Wystrój (same dekoracje: aria-hidden, bez kliknięć): sala to ściana u góry (duże okno z zasłonkami,
 *   parapetem i roślinką, zegar z czasem serwera, plakat, szafka z lekami — rozmiar z miejsca nad łóżkami,
 *   CSS: kontener ward-wall) i rzędy łóżek pod nią. Każde łóżko ma parawan, szafkę nocną z lampką
 *   (świeci nocą i w ciemnym motywie) i drobiazgiem, kroplówkę z monitorem serca (leczony) albo balonik
 *   (wyzdrowiały). Podłoga zaczyna się na wysokości wezgłowi pierwszego rzędu (--ward-floor-y z JS).
 *   Przy otwartej karcie okna (≥ 1024 px) pod kartą, przy prawej krawędzi sceny, stoją roślina i wózek z lekami.
 * Rejestruje się w window.PetsWorld.scenes.izba.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.izba) return;

    var MIN_SLOTS = 3;

    // Kroplówka z monitorem serca: stojak na kółkach, worek, kapiąca kropla, wężyk do łóżka, monitor z linią EKG
    // (viewBox 56×190, stopy przy dole pola)
    var DRIP_SVG =
        '<svg viewBox="0 0 56 190" preserveAspectRatio="xMidYMax meet" aria-hidden="true" focusable="false">' +
        '<path class="drip-pole" d="M28 10v170"/>' +
        '<path class="drip-hook" d="M16 12h24"/>' +
        '<path class="drip-feet" d="M10 188l18-9 18 9"/>' +
        '<rect class="drip-bag" x="17" y="14" width="22" height="32" rx="7"/>' +
        '<path class="drip-liquid" d="M19 30h18v8a5 5 0 0 1-5 5h-8a5 5 0 0 1-5-5z"/>' +
        '<rect class="drip-chamber" x="25" y="48" width="6" height="11" rx="2"/>' +
        '<circle class="drip-drop" cx="28" cy="52" r="1.6"/>' +
        '<path class="drip-tube" d="M28 59c0 30-14 46-46 58"/>' +
        '<path class="mon-clamp" d="M28 101h4"/>' +
        '<rect class="mon-case" x="31" y="90" width="24" height="22" rx="4"/>' +
        '<rect class="mon-screen" x="34" y="93" width="18" height="12" rx="2"/>' +
        '<path class="mon-line" pathLength="30" d="M35 99.5h4l1.6-3.5 2.2 7 2-5.5 1.2 2h5"/>' +
        '<circle class="mon-led" cx="51" cy="108.5" r="1.3"/>' +
        '</svg>';

    // Puste łóżko — ta sama bryła co łóżeczko rigu (pose 'bed'), kołderka zaścielona na płasko
    var EMPTY_BED_SVG =
        '<svg class="pets-bed__empty" viewBox="0 0 200 200" aria-hidden="true" focusable="false">' +
        '<rect class="eb-post" x="27" y="62" width="10" height="132" rx="5"/><rect class="eb-post" x="163" y="62" width="10" height="132" rx="5"/>' +
        '<rect class="eb-board" x="34" y="72" width="132" height="84" rx="16"/>' +
        '<path class="eb-cross" d="M45 82h6v6h6v6h-6v6h-6v-6h-6v-6h6z"/>' +
        '<path class="eb-pillow" d="M50 142c0-13 20-19 50-19s50 6 50 19-20 17-50 17-50-4-50-17z"/>' +
        '<rect class="eb-mattress" x="24" y="176" width="152" height="12" rx="6"/>' +
        '<path class="eb-quilt" d="M28 162q36-5 72-3q36-2 72 3v18q0 8-8 8H36q-8 0-8-8z"/>' +
        '<path class="eb-fold" d="M30 166q35-5 70-3q35-2 70 3"/>' +
        '<circle class="eb-wheel" cx="32" cy="196" r="4"/><circle class="eb-wheel" cx="168" cy="196" r="4"/>' +
        '</svg>';

    var HEART = 'M0 4.5C0 2 2-.2 4.2.6 5.3 1 6 2 6 2s.7-1 1.8-1.4C10-.2 12 2 12 4.5 12 8.4 6 12 6 12S0 8.4 0 4.5z';
    var HEARTS_SVG =
        '<svg viewBox="0 0 60 40" aria-hidden="true" focusable="false">' +
        '<path transform="translate(6 20)" d="' + HEART + '"/>' +
        '<path transform="translate(26 6) scale(1.3)" d="' + HEART + '"/>' +
        '<path transform="translate(44 18) scale(.9)" d="' + HEART + '"/>' +
        '</svg>';

    var PLUS_SVG =
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="3" ' +
        'stroke-linecap="round"><path d="M12 6v12M6 12h12"/></svg>';

    // Parawan za szafką nocną: trzy łukowate skrzydła ustawione w harmonijkę (środkowe jaśniejsze), materiał
    // w groszki (kolor wg miejsca — CSS), nóżki na podłodze
    var DOTS = (function () {
        var d = '';
        [[9, 36], [16, 52], [9, 68], [16, 84], [9, 100], [16, 116], [9, 132]].forEach(function (p) {
            [0, 22, 44].forEach(function (dx) {       // skrzydła co 22 jednostki; środkowe wyżej o 6
                d += 'M' + (p[0] + dx) + ' ' + (p[1] - (dx === 22 ? 6 : 0)) + 'a2 2 0 1 0 4 0a2 2 0 1 0-4 0';
            });
        });
        return d;
    })();
    var SCREEN_SVG =
        '<svg viewBox="0 0 72 170" preserveAspectRatio="xMidYMax meet" aria-hidden="true" focusable="false">' +
        '<path class="sc-foot" d="M6 156v12M22 156v12M50 156v12M66 156v12M29.5 152v16M42.5 152v16"/>' +
        '<path class="sc-frame" d="M2 158V30a12 12 0 0 1 24 0v128z"/>' +
        '<path class="sc-frame" d="M46 158V30a12 12 0 0 1 24 0v128z"/>' +
        '<path class="sc-cloth" d="M6 150V32a8 8 0 0 1 16 0v118z"/>' +
        '<path class="sc-cloth" d="M50 150V32a8 8 0 0 1 16 0v118z"/>' +
        '<path class="sc-frame sc-frame--mid" d="M24 154V24a12 12 0 0 1 24 0v130z"/>' +
        '<path class="sc-cloth sc-cloth--mid" d="M28 146V26a8 8 0 0 1 16 0v120z"/>' +
        '<path class="sc-dots" d="' + DOTS + '"/>' +
        '</svg>';

    // Szafka nocna z lampką (świeci nocą i w ciemnym motywie — CSS) i drobiazgiem zależnym od miejsca
    var TULIP = 'M-3.5 0c-.6-3 .4-5.5 1.6-6.5l1.9 2 1.9-2c1.2 1 2.2 3.5 1.6 6.5-.7 2-6.3 2-7 0z';
    var STAND_ITEMS = [
        // wazon z tulipanami
        '<path class="ns-stem" d="M42 35Q38 30 35 23M42 35Q43 26 44 17M42 35Q47 30 51 25"/>' +
        '<path class="ns-bloom" transform="translate(35 23)" d="' + TULIP + '"/>' +
        '<path class="ns-bloom ns-bloom--b" transform="translate(44 17)" d="' + TULIP + '"/>' +
        '<path class="ns-bloom" transform="translate(51 25) rotate(14)" d="' + TULIP + '"/>' +
        '<path class="ns-vase" d="M36.5 46c-3-4-2-9 1-11h9c3 2 4 7 1 11z"/>',
        // kubek z serduszkiem na książce
        '<rect class="ns-book" x="29" y="40" width="27" height="6" rx="1.5"/>' +
        '<path class="ns-book-line" d="M32 43h21"/>' +
        '<path class="ns-steam" d="M39 25c-2-3 2-4 0-7M43.5 25c-2-3 2-4 0-7"/>' +
        '<path class="ns-mug-handle" d="M46.5 31a3.6 3.6 0 0 1 0 7.2"/>' +
        '<path class="ns-mug" d="M35 28.5h12v9a2.5 2.5 0 0 1-2.5 2.5h-7a2.5 2.5 0 0 1-2.5-2.5z"/>' +
        '<path class="ns-mug-heart" transform="translate(38.5 31) scale(.42)" d="' + HEART + '"/>',
        // laurka z serduszkiem i jabłko
        '<path class="ns-card" d="M31 46l2.5-17h16l-2.5 17z"/>' +
        '<path class="ns-card-heart" transform="translate(36.6 33.2) scale(.62)" d="' + HEART + '"/>' +
        '<circle class="ns-apple" cx="52.5" cy="41.5" r="4.5"/>' +
        '<path class="ns-apple-leaf" d="M52.5 37.2c.6-2 2.4-3.2 4.2-3.2-.6 2-2.2 3.2-4.2 3.2z"/>'
    ];

    function standSvg(kind) {
        return '<svg viewBox="0 0 60 100" preserveAspectRatio="xMidYMax meet" aria-hidden="true" focusable="false">' +
            '<path class="ns-lamp-stem" d="M15 45V27"/>' +
            '<ellipse class="ns-lamp-base" cx="15" cy="45" rx="7" ry="2.6"/>' +
            '<path class="ns-shade" d="M6 28l4-13h10l4 13z"/>' +
            STAND_ITEMS[kind % STAND_ITEMS.length] +
            '<rect class="ns-top" x="1" y="46" width="58" height="7" rx="3.5"/>' +
            '<rect class="ns-body" x="5" y="52" width="50" height="41" rx="5"/>' +
            '<rect class="ns-drawer" x="10" y="57" width="40" height="13" rx="3"/>' +
            '<rect class="ns-drawer" x="10" y="74" width="40" height="14" rx="3"/>' +
            '<circle class="ns-knob" cx="30" cy="63.5" r="2.3"/><circle class="ns-knob" cx="30" cy="81" r="2.3"/>' +
            '<path class="ns-leg" d="M11 93v5M49 93v5"/>' +
            '</svg>';
    }

    // Balonik-serduszko przywiązany do łóżka wyzdrowiałego
    var BALLOON_SVG =
        '<svg viewBox="0 0 40 120" preserveAspectRatio="xMidYMin meet" aria-hidden="true" focusable="false">' +
        '<path class="bl-string" d="M20 50c-5 12 5 22-2 34s-8 22-16 34"/>' +
        '<path class="bl-heart" d="M20 48C8 40 2 31 2 21 2 12 8 6 14 6c3 0 5 2 6 5 1-3 3-5 6-5 6 0 12 6 12 15 0 10-6 19-18 27z"/>' +
        '<path class="bl-shine" d="M9 18c1-4 3-6 6-7"/>' +
        '<path class="bl-knot" d="M17.5 47.5h5l-2.5 4z"/>' +
        '</svg>';

    // --- ściana sali: zegar, plakat, duże okno z zasłonkami i parapetem, szafka z lekami ---------------
    var CLOCK_TICKS = (function () {
        var d = '';
        for (var i = 0; i < 12; i++) {
            var a = i * Math.PI / 6, r1 = i % 3 ? 32 : 28.5, r2 = 35.5;
            var sx = Math.sin(a), cy = -Math.cos(a);
            d += 'M' + (50 + sx * r1).toFixed(1) + ' ' + (50 + cy * r1).toFixed(1) +
                'L' + (50 + sx * r2).toFixed(1) + ' ' + (50 + cy * r2).toFixed(1);
        }
        return d;
    })();

    var CLOCK_SVG =
        '<svg viewBox="0 0 100 100" aria-hidden="true" focusable="false">' +
        '<circle class="wk-rim" cx="50" cy="50" r="47"/>' +
        '<circle class="wk-face" cx="50" cy="50" r="39"/>' +
        '<path class="wk-tick" d="' + CLOCK_TICKS + '"/>' +
        '<path class="wk-hand wk-hand--h" d="M50 54V31"/>' +
        '<path class="wk-hand wk-hand--m" d="M50 55V19"/>' +
        '<circle class="wk-pin" cx="50" cy="50" r="4"/>' +
        '</svg>';

    var SPARK = 'l1.5 3.5 3.5 1.5-3.5 1.5-1.5 3.5-1.5-3.5-3.5-1.5 3.5-1.5z';
    var POSTER_SVG =
        '<svg viewBox="0 0 80 100" aria-hidden="true" focusable="false">' +
        '<rect class="wp-frame" x="3" y="6" width="74" height="91" rx="7"/>' +
        '<rect class="wp-paper" x="9" y="12" width="62" height="79" rx="4"/>' +
        '<path class="wp-heart" d="M40 70C24 60 17 51 17 41c0-8 6-13 12-13 5 0 9 3 11 7 2-4 6-7 11-7 6 0 12 5 12 13 0 10-7 19-23 29z"/>' +
        '<g transform="rotate(-32 40 48)"><rect class="wp-plaster" x="24" y="43" width="32" height="10" rx="5"/>' +
        '<rect class="wp-pad" x="35" y="44.5" width="10" height="7" rx="1.5"/></g>' +
        '<path class="wp-line" d="M24 79h32M29 85h22"/>' +
        '<path class="wp-spark" d="M19 19' + SPARK + 'M61 21' + SPARK + '"/>' +
        '<rect class="wp-tape" x="31" y="2" width="18" height="9" rx="2" transform="rotate(-5 40 6)"/>' +
        '</svg>';

    var CABINET_SVG =
        '<svg viewBox="0 0 100 128" aria-hidden="true" focusable="false">' +
        '<rect class="wcab-body" x="6" y="14" width="88" height="108" rx="9"/>' +
        '<rect class="wcab-crown" x="2" y="9" width="96" height="10" rx="5"/>' +
        '<rect class="wcab-glass" x="13" y="24" width="35" height="64" rx="4"/>' +
        '<rect class="wcab-glass" x="52" y="24" width="35" height="64" rx="4"/>' +
        '<rect class="wcab-b1" x="17" y="33" width="7" height="14" rx="2"/>' +
        '<rect class="wcab-b2" x="27" y="37" width="9" height="10" rx="3"/>' +
        '<rect class="wcab-b3" x="39" y="35" width="5" height="12" rx="2"/>' +
        '<rect class="wcab-b2" x="56" y="34" width="8" height="13" rx="2"/>' +
        '<rect class="wcab-b3" x="67" y="38" width="9" height="9" rx="4"/>' +
        '<rect class="wcab-b1" x="79" y="36" width="5" height="11" rx="2"/>' +
        '<rect class="wcab-b3" x="16" y="59" width="10" height="11" rx="3"/>' +
        '<rect class="wcab-b1" x="29" y="56" width="6" height="14" rx="2"/>' +
        '<rect class="wcab-box" x="38" y="61" width="8" height="9" rx="1.5"/>' +
        '<rect class="wcab-box" x="55" y="60" width="14" height="10" rx="1.5"/>' +
        '<rect class="wcab-b2" x="72" y="57" width="7" height="13" rx="2"/>' +
        '<rect class="wcab-b3" x="81" y="62" width="4" height="8" rx="1.5"/>' +
        '<rect class="wcab-b2" x="17" y="78" width="12" height="10" rx="3"/>' +
        '<rect class="wcab-b1" x="33" y="80" width="10" height="8" rx="4"/>' +
        '<rect class="wcab-box" x="56" y="79" width="12" height="9" rx="1.5"/>' +
        '<rect class="wcab-b3" x="72" y="77" width="6" height="11" rx="2"/>' +
        '<path class="wcab-shelf" d="M13 47h35M52 47h35M13 70h35M52 70h35"/>' +
        '<path class="wcab-shine" d="M16 40l12-14M55 40l12-14"/>' +
        '<circle class="wcab-knob" cx="44.5" cy="56" r="2.2"/><circle class="wcab-knob" cx="55.5" cy="56" r="2.2"/>' +
        '<rect class="wcab-drawer" x="13" y="94" width="74" height="19" rx="4"/>' +
        '<path class="wcab-cross" d="M47.5 97h5v4.5h4.5v5h-4.5v4.5h-5v-4.5H43v-5h4.5z"/>' +
        '</svg>';

    // Widok za oknem: niebo (słońce i chmurki / księżyc i gwiazdy — CSS wg motywu i nocy) przycięte od góry
    // i krajobraz (wzgórza, drzewa) przycięty od dołu — okno może być wysokie albo panoramiczne
    var STAR = 'l1.2 3.3 3.3 1.2-3.3 1.2-1.2 3.3-1.2-3.3-3.3-1.2 3.3-1.2z';
    var SKY_SVG =
        '<svg class="ww-sky" viewBox="0 0 400 300" preserveAspectRatio="xMidYMin slice" aria-hidden="true" focusable="false">' +
        '<g class="wv-day"><circle class="wv-halo" cx="292" cy="70" r="44"/><circle class="wv-sun" cx="292" cy="70" r="25"/></g>' +
        '<g class="wv-night"><path class="wv-moon" d="M118 40a32 32 0 1 0 38 44 26 26 0 1 1-38-44z"/>' +
        '<path class="wv-star" d="M60 34' + STAR + 'M210 28' + STAR + 'M318 52' + STAR + '"/>' +
        '<path class="wv-star wv-star--b" d="M176 82' + STAR + 'M262 104' + STAR + 'M352 24' + STAR + 'M30 96' + STAR + '"/></g>' +
        '<g class="wv-clouds">' +
        '<path class="wv-cloud" d="M52 116a15 15 0 0 1 27-9 19 19 0 0 1 35 4 12 12 0 0 1 2 24H54a10 10 0 0 1-2-19z"/>' +
        '<path class="wv-cloud" d="M214 44a11 11 0 0 1 21-6 14 14 0 0 1 26 4 9 9 0 0 1 1 18h-46a8 8 0 0 1-2-16z"/>' +
        '</g>' +
        '</svg>';

    var LAND_SVG =
        '<svg class="ww-land" viewBox="0 0 400 300" preserveAspectRatio="xMidYMax slice" aria-hidden="true" focusable="false">' +
        '<path class="wv-hill wv-hill--far" d="M0 222c60-30 120-34 190-12s140 10 210-12V300H0z"/>' +
        '<rect class="wv-trunk" x="66" y="196" width="6" height="22" rx="2"/><circle class="wv-crown" cx="69" cy="188" r="18"/>' +
        '<rect class="wv-trunk" x="300" y="184" width="6" height="26" rx="2"/><ellipse class="wv-crown wv-crown--b" cx="303" cy="172" rx="15" ry="22"/>' +
        '<rect class="wv-trunk" x="334" y="190" width="5" height="18" rx="2"/><circle class="wv-crown" cx="336" cy="183" r="13"/>' +
        '<path class="wv-hill wv-hill--near" d="M0 262c80-26 150-26 230-6s120 8 170-6V300H0z"/>' +
        '<rect class="wv-trunk" x="150" y="226" width="7" height="26" rx="2"/><circle class="wv-crown wv-crown--n" cx="153" cy="214" r="22"/>' +
        '<g class="wv-flowers"><circle cx="40" cy="274" r="3"/><circle cx="72" cy="282" r="2.6"/><circle cx="252" cy="270" r="3"/>' +
        '<circle cx="356" cy="276" r="2.6"/><circle cx="214" cy="286" r="2.4"/></g>' +
        '</svg>';

    var CURTAIN_SVG =
        '<svg viewBox="0 0 60 200" preserveAspectRatio="none" aria-hidden="true" focusable="false">' +
        '<path class="wcur-fabric" d="M0 0h60c-4 38-20 78-30 104 6 30 18 64 24 96H0z"/>' +
        '<path class="wcur-fold" d="M14 4c0 40-2 70-4 100 2 32 6 64 8 92M32 4c-2 34-10 66-16 98M24 112c4 28 10 56 14 84"/>' +
        '<rect class="wcur-tie" x="0" y="98" width="34" height="12" rx="6"/>' +
        '</svg>';

    var PLANT_SVG =
        '<svg viewBox="0 0 60 80" preserveAspectRatio="xMidYMax meet" aria-hidden="true" focusable="false">' +
        '<path class="wpl-leaf wpl-leaf--b" d="M30 52C22 46 13 46 5 50c8 7 17 7 25 2z"/>' +
        '<path class="wpl-leaf wpl-leaf--b" d="M30 52c8-6 17-6 25-2-8 7-17 7-25 2z"/>' +
        '<path class="wpl-leaf" d="M30 52C16 48 8 36 10 22c10 4 18 15 20 30z"/>' +
        '<path class="wpl-leaf" d="M30 52c12-6 20-18 18-32-10 4-18 16-18 32z"/>' +
        '<path class="wpl-leaf wpl-leaf--c" d="M30 52c-4-14-2-30 6-44 6 13 4 30-6 44z"/>' +
        '<path class="wpl-pot" d="M16 54h28l-4 24H20z"/>' +
        '<rect class="wpl-rim" x="13" y="51" width="34" height="7" rx="3"/>' +
        '</svg>';

    var CACTUS_SVG =
        '<svg viewBox="0 0 40 60" preserveAspectRatio="xMidYMax meet" aria-hidden="true" focusable="false">' +
        '<path class="wpl-cactus" d="M8 26a3 3 0 0 1 6 0v5h2V18a5 5 0 0 1 10 0v18h1v-7a3 3 0 0 1 6 0v6a7 7 0 0 1-7 7v4H15v-6a7 7 0 0 1-7-7z"/>' +
        '<circle class="wpl-bud" cx="21" cy="12" r="3.6"/>' +
        '<path class="wpl-pot wpl-pot--b" d="M10 44h20l-3 15H13z"/>' +
        '<rect class="wpl-rim wpl-rim--b" x="8" y="41" width="24" height="6" rx="2.5"/>' +
        '</svg>';

    var WALL_HTML =
        '<div class="pets-ward__decor">' +
        '<div class="pets-ward__side pets-ward__side--l">' +
        '<span class="pets-ward__clock">' + CLOCK_SVG + '</span>' +
        '<span class="pets-ward__poster">' + POSTER_SVG + '</span>' +
        '</div>' +
        '<div class="pets-ward__window">' +
        '<span class="ww-rod"></span>' +
        '<span class="ww-frame">' + SKY_SVG + LAND_SVG + '</span>' +
        '<span class="ww-curtain ww-curtain--l">' + CURTAIN_SVG + '</span>' +
        '<span class="ww-curtain ww-curtain--r">' + CURTAIN_SVG + '</span>' +
        '<span class="ww-sill"></span>' +
        '<span class="ww-plant">' + PLANT_SVG + '</span>' +
        '<span class="ww-cactus">' + CACTUS_SVG + '</span>' +
        '</div>' +
        '<div class="pets-ward__side pets-ward__side--r">' +
        '<span class="pets-ward__cabinet">' + CABINET_SVG + '</span>' +
        '</div>' +
        '</div>';

    // Pod kartą okna sceny (≥ 1024 px) sala nie kończy się pustą ścianą: przy prawej krawędzi sceny stoją
    // duża roślina i wózek z lekami (widoczne tylko przy otwartej karcie — CSS)
    var CART_SVG =
        '<svg viewBox="0 0 100 124" preserveAspectRatio="xMidYMax meet" aria-hidden="true" focusable="false">' +
        '<ellipse class="wc-shadow" cx="50" cy="120" rx="44" ry="4"/>' +
        '<path class="wc-handle" d="M86 40V20h8"/>' +
        '<rect class="wc-bottle" x="16" y="13" width="10" height="19" rx="3"/>' +
        '<rect class="wc-cap" x="17.5" y="9" width="7" height="5" rx="1.5"/>' +
        '<rect class="wc-jar" x="30" y="19" width="13" height="13" rx="3.5"/>' +
        '<path class="wc-jar-heart" transform="translate(33 22.4) scale(.58)" d="' + HEART + '"/>' +
        '<rect class="wc-box" x="48" y="22" width="22" height="10" rx="2"/>' +
        '<path class="wc-tissue" d="M54 22c1-5 9-5 10 0z"/>' +
        '<rect class="wc-tray" x="6" y="31" width="84" height="8" rx="4"/>' +
        '<rect class="wc-body" x="12" y="38" width="72" height="62" rx="7"/>' +
        '<rect class="wc-drawer" x="18" y="45" width="60" height="22" rx="4"/>' +
        '<rect class="wc-drawer" x="18" y="71" width="60" height="22" rx="4"/>' +
        '<path class="wc-cross" d="M45.5 49h5v4.5H55v5h-4.5V63h-5v-4.5H41v-5h4.5z"/>' +
        '<rect class="wc-knob" x="42" y="80" width="12" height="4" rx="2"/>' +
        '<path class="wc-leg" d="M20 100v10M76 100v10"/>' +
        '<circle class="wc-wheel" cx="20" cy="113" r="5"/><circle class="wc-wheel" cx="76" cy="113" r="5"/>' +
        '</svg>';

    var MOOD_TEXT = { chory: 'Chory', krytyczny: 'W stanie krytycznym' };

    function create(ctx, host) {
        var H = window.PetsHospital;
        var u = ctx.u;
        var el = u.el;
        var R = function () { return window.PetRig; };

        var lastState = null;
        var slots = [];              // id pupila albo null (wolne łóżko) — stałe miejsca
        var views = [];
        var prefer = {};             // id przyjmowanego pupila → łóżko, z którego go przyjęto
        var open = null;             // {type: 'bed', id} | {type: 'free', slot}
        var openSig = null;
        var refs = null;             // elementy okna pupila odświeżane co sekundę
        var confirm = false;         // „Zabierz wcześniej” czeka na potwierdzenie
        var winRigs = [];            // mini rigi w oknie „Kogo przyjąć?”
        var pending = null;
        var admitting = null;
        var discharging = null;

        // --- szkielet -------------------------------------------------------------------------
        // Scena właściwa: podłoga do krawędzi sceny (pod przewijanym wnętrzem) + wnętrze = ściana z wystrojem
        // (rośnie w wolne miejsce nad łóżkami) i rzędy łóżek
        var stage = el('div', 'pets-stage pets-ward');
        var floor = el('div', 'pets-ward__floor');
        floor.setAttribute('aria-hidden', 'true');
        var scroll = el('div', 'pets-scroll pets-ward__scroll');
        scroll.setAttribute('data-window-backdrop', '');
        var room = el('div', 'pets-ward__room');
        var wall = el('div', 'pets-ward__wall');
        wall.setAttribute('aria-hidden', 'true');
        wall.innerHTML = WALL_HTML;
        var clock = wall.querySelector('.pets-ward__clock');
        var row = el('div', 'pets-ward__row');
        room.appendChild(wall);
        room.appendChild(row);
        scroll.appendChild(room);
        var extras = el('div', 'pets-ward__extras');
        extras.setAttribute('aria-hidden', 'true');
        extras.innerHTML = '<span class="pets-ward__plant">' + PLANT_SVG + '</span><span class="pets-ward__cart">' + CART_SVG + '</span>';
        stage.appendChild(floor);
        stage.appendChild(extras);
        stage.appendChild(scroll);
        host.appendChild(stage);

        var win = window.PetsSceneWindow ? window.PetsSceneWindow.attach(host) : null;

        function findHosp(state, id) {
            var list = H.inBed(state);
            for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
            return null;
        }

        function setText(node, text) {
            if (node.textContent !== text) node.textContent = text;
        }

        // --- podłoga i zegar ----------------------------------------------------------------------
        // Podłoga (tło do krawędzi sceny, poza przewijanym wnętrzem) zaczyna się na styku ściany z wezgłowiami
        // pierwszego rzędu — pozycję czyta ze znacznika w łóżku, także po przewinięciu i zmianie rozmiaru.
        var floorQueued = false;
        var floorSet = '';

        function syncFloor() {
            floorQueued = false;
            var first = views[0];
            var h = stage.offsetHeight;
            if (!first || !h) return;
            var box = stage.getBoundingClientRect();
            var k = box.height / h || 1;            // wejście sceny skaluje ją (0,97) — pozycja w px sceny
            var y = Math.round((first.line.getBoundingClientRect().top - box.top) / k) + 'px';
            var w = Math.round(first.el.offsetWidth) + 'px';
            if (floorSet === y + w) return;
            floorSet = y + w;
            stage.style.setProperty('--ward-floor-y', y);
            stage.style.setProperty('--ward-bed-w', w);
        }

        function queueFloor() {
            if (floorQueued) return;
            floorQueued = true;
            // Ukryta karta nie rysuje klatek — wtedy od razu (inaczej podłoga czekałaby na powrót do karty)
            if (document.visibilityState === 'hidden' || !window.requestAnimationFrame) syncFloor();
            else window.requestAnimationFrame(syncFloor);
        }

        scroll.addEventListener('scroll', queueFloor, { passive: true });
        if (window.ResizeObserver) {
            // scroll = rozmiar sceny (okno ≥ 1024 px, sidebar); rząd z paddingiem (arkusz < 1024 px dokłada go
            // od dołu); ściana kurczy się/rośnie, gdy rząd jedzie w górę/dół bez zmiany własnego rozmiaru
            var floorObs = new ResizeObserver(function () { queueFloor(); });
            floorObs.observe(scroll);
            floorObs.observe(row, { box: 'border-box' });
            floorObs.observe(wall);
        } else {
            window.addEventListener('resize', queueFloor);
        }

        // Zegar na ścianie: czas serwera (ten sam co noc pupili), wskazówki przestawiane co minutę
        var clockMin = -1;

        function tickClock() {
            if (!clock) return;
            var now = new Date(u.serverNow ? u.serverNow() : Date.now());
            var m = now.getHours() * 60 + now.getMinutes();
            if (m === clockMin) return;
            clockMin = m;
            clock.style.setProperty('--wk-h', (m % 720) / 2 + 'deg');
            clock.style.setProperty('--wk-m', now.getMinutes() * 6 + 'deg');
        }

        // --- łóżka ----------------------------------------------------------------------------
        function bedView(i) {
            var b = el('button', 'pets-bed');
            b.type = 'button';
            b.dataset.bedSlot = String(i);
            var scene = el('span', 'pets-bed__scene');
            scene.setAttribute('aria-hidden', 'true');
            var line = el('span', 'pets-bed__line');          // styk podłogi ze ścianą (syncFloor)
            var screen = el('span', 'pets-bed__screen');
            screen.innerHTML = SCREEN_SVG;
            var stand = el('span', 'pets-bed__stand');
            stand.innerHTML = standSvg(i);
            var glow = el('span', 'pets-bed__glow');
            var drip = el('span', 'pets-bed__drip');
            drip.innerHTML = DRIP_SVG;
            var art = el('span', 'pets-bed__art');
            var balloon = el('span', 'pets-bed__balloon');
            balloon.innerHTML = BALLOON_SVG;
            var hearts = el('span', 'pets-bed__hearts');
            hearts.innerHTML = HEARTS_SVG;
            var plus = el('span', 'pets-bed__plus');
            plus.innerHTML = PLUS_SVG;
            [line, screen, stand, glow, drip, art, balloon, hearts, plus].forEach(function (n) { scene.appendChild(n); });
            var plate = el('span', 'pets-bed__plate');
            plate.setAttribute('aria-hidden', 'true');
            var main = el('span', 'pets-bed__plate-main');
            var sub = el('span', 'pets-bed__plate-sub');
            plate.appendChild(main);
            plate.appendChild(sub);
            b.appendChild(scene);
            b.appendChild(plate);
            return { el: b, line: line, art: art, main: main, sub: sub, rig: null, petId: undefined, pet: null };
        }

        function destroyView(view) {
            if (view.rig) view.rig.destroy();
            if (view.el.parentNode) view.el.parentNode.removeChild(view.el);
        }

        function tickBed(view) {
            var pet = view.pet;
            var b = view.el;
            var label;
            if (!pet) {
                var canAdmit = H.sickAtHome(lastState).length > 0;
                b.classList.add('is-free');
                b.classList.remove('is-ready', 'is-healing');
                b.classList.toggle('can-admit', canAdmit);
                setText(view.main, 'wolne łóżko');
                setText(view.sub, canAdmit ? 'przyjmij chorego' : '');
                label = 'Wolne łóżko' + (canAdmit ? ' — możesz przyjąć chorego pupila' : '');
            } else {
                var st = H.healStatus(pet, u);
                var name = H.petName(pet, u);
                b.classList.remove('is-free', 'can-admit');
                b.classList.toggle('is-ready', st.ready);
                b.classList.toggle('is-healing', !st.ready);
                if (st.ready) {
                    setText(view.main, 'Zdrowy! Odbierz');
                    setText(view.sub, name + ' tęskni za domem');
                    label = 'Łóżko: ' + name + ', zdrowy — czeka na odbiór, tęskni za domem';
                } else {
                    setText(view.main, name + ' · jeszcze ' + st.left);
                    setText(view.sub, '');
                    label = 'Łóżko: ' + name + ', wraca do zdrowia, jeszcze ' + st.left;
                }
            }
            view.sub.hidden = !view.sub.textContent;
            if (b.getAttribute('aria-label') !== label) b.setAttribute('aria-label', label);
        }

        function updateBed(view, pet) {
            var id = pet ? pet.id : null;
            if (view.petId !== id) {
                if (view.rig) view.rig.destroy();
                view.rig = null;
                view.art.innerHTML = '';
                view.petId = id;
                if (pet && R()) {
                    view.rig = R().mount(view.art, {
                        species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: false,
                        size: 'mini', need: R().needOf ? R().needOf(pet) : 'sick', pose: 'bed'
                    });
                } else if (!pet) {
                    view.art.innerHTML = EMPTY_BED_SVG;
                }
            } else if (pet && view.rig) {
                view.rig.update({ species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: false });
                if (typeof view.rig.setNeed === 'function' && R().needOf) view.rig.setNeed(R().needOf(pet));
            }
            view.pet = pet;
            if (pet) view.el.dataset.petId = String(pet.id);
            else delete view.el.dataset.petId;
            tickBed(view);
        }

        function syncViews(state) {
            while (views.length < slots.length) {
                var v = bedView(views.length);
                views.push(v);
                row.appendChild(v.el);
            }
            while (views.length > slots.length) destroyView(views.pop());
            slots.forEach(function (id, i) { updateBed(views[i], id == null ? null : findHosp(state, id)); });
        }

        function slotOf(id) {
            var i = slots.indexOf(id);
            return i >= 0 ? views[i] : null;
        }

        function markSelected(view) {
            views.forEach(function (v) { v.el.classList.toggle('is-selected', v === view); });
        }

        // --- okno pupila w łóżku -----------------------------------------------------------------
        function bedSig(pet) {
            return [pet.id, pet.name, !!pet.hospital.ready, confirm].join('|');
        }

        function fillBed(r) {
            var st = H.healStatus(r.pet, u);
            r.bar.set(st.pct);
            setText(r.pct, Math.round(st.pct) + '%');
            setText(r.status, st.status);
            setText(r.note, st.note);
        }

        function bedContent(pet) {
            var name = H.petName(pet, u);
            var box = el('div', 'pets-hosp-win pets-hosp-win--bed');
            var title = el('h2', 'pets-window__title', name);
            title.id = 'petsWardWinTitle';
            box.appendChild(title);
            var meter = el('div', 'pets-hosp-win__meter');
            var bar = H.progress(u, 'Leczenie: ' + name, true);
            var pct = el('span', 'pets-hosp-win__pct');
            pct.setAttribute('aria-hidden', 'true');
            meter.appendChild(bar.el);
            meter.appendChild(pct);
            box.appendChild(meter);
            var status = el('p', 'pets-window__text pets-hosp-win__status');
            var note = el('p', 'pets-window__text');
            box.appendChild(status);
            box.appendChild(note);
            var actions = el('div', 'pets-window__actions');
            var btn;
            if (pet.hospital.ready) {
                btn = u.button('Odbierz', 'home', 'primary', { wardAction: 'discharge', petId: String(pet.id) });
                btn.setAttribute('data-window-key', 'discharge');
                actions.appendChild(btn);
            } else if (confirm) {
                var health = Math.round((pet.bars && pet.bars.health) || 0);
                var q = el('p', 'pets-hosp-win__confirm', 'Pupil ' + (pet.name || '') + ' wróci z obecnym zdrowiem (' + health + '%). Zabrać go już teraz?');
                q.setAttribute('role', 'status');
                actions.appendChild(q);
                btn = u.button('Tak, zabieram', 'home', null, { wardAction: 'discharge', petId: String(pet.id) });
                btn.setAttribute('data-window-key', 'early');
                actions.appendChild(btn);
                var keep = u.button('Zostaw w szpitalu', null, 'ghost', { wardAction: 'confirm-cancel', petId: String(pet.id) });
                keep.setAttribute('data-window-key', 'keep');
                actions.appendChild(keep);
            } else {
                btn = u.button('Zabierz wcześniej', null, 'ghost', { wardAction: 'early', petId: String(pet.id) });
                btn.setAttribute('data-window-key', 'early');
                actions.appendChild(btn);
            }
            box.appendChild(actions);
            box.appendChild(el('p', 'pets-hosp-win__tip', 'Kliknij pupila w łóżku, żeby go pogłaskać.'));
            refs = { pet: pet, bar: bar, pct: pct, status: status, note: note };
            fillBed(refs);
            return box;
        }

        // --- okno wolnego łóżka: „Kogo przyjąć?” albo informacja ----------------------------------------
        function dropWinRigs() {
            winRigs.forEach(function (r) { if (r) r.destroy(); });
            winRigs = [];
        }

        function freeSig(state) {
            return 'free|' + H.sickAtHome(state).map(function (p) {
                return [p.id, p.name, p.mood, !!(p.can && p.can.admit), Math.round((p.bars && p.bars.health) || 0)].join(':');
            }).join(',');
        }

        function admitRow(pet, hours) {
            var li = el('li', 'pets-hosp-win__row');
            var art = el('span', 'pets-hosp-win__mini');
            art.setAttribute('aria-hidden', 'true');
            if (R()) {
                winRigs.push(R().mount(art, {
                    species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: pet.asleep,
                    size: 'mini', need: R().needOf ? R().needOf(pet) : 'sick', pose: 'lie'
                }));
            }
            var info = el('div', 'pets-hosp-win__who');
            info.appendChild(el('span', 'pets-hosp-win__name', H.petName(pet, u)));
            var health = Math.round((pet.bars && pet.bars.health) || 0);
            info.appendChild(el('span', 'pets-hosp-win__mood', (MOOD_TEXT[pet.mood] || 'Chory') + ' · zdrowie ' + health + '%'));
            if (hours > 0) info.appendChild(el('span', 'pets-hosp-win__hint', 'Wyzdrowieje w najwyżej ' + hours + ' h'));
            var action = el('div', 'pets-hosp-win__act');
            var btn = u.button('Przyjmij', 'cross', 'primary', { wardAction: 'admit', petId: String(pet.id) });
            btn.setAttribute('data-window-key', 'admit-' + pet.id);
            action.appendChild(btn);
            var ok = !!(pet.can && pet.can.admit);
            if (!ok) {
                btn.setAttribute('aria-disabled', 'true');
                var why = pet.reasons && pet.reasons.admit ? pet.reasons.admit.charAt(0).toUpperCase() + pet.reasons.admit.slice(1) : '';
                if (why) {
                    var reason = el('p', 'pets-hosp-win__reason', why);
                    reason.id = 'petsWardReason' + pet.id;
                    btn.setAttribute('aria-describedby', reason.id);
                    action.appendChild(reason);
                }
            }
            li.appendChild(art);
            li.appendChild(info);
            li.appendChild(action);
            return li;
        }

        function freeContent(state) {
            var sick = H.sickAtHome(state);
            var box = el('div', 'pets-hosp-win pets-hosp-win--free');
            var title = el('h2', 'pets-window__title', sick.length ? 'Kogo przyjąć?' : 'Wolne łóżko');
            title.id = 'petsWardWinTitle';
            box.appendChild(title);
            refs = null;
            if (!sick.length) {
                box.appendChild(el('p', 'pets-window__text', 'Chorego pupila przyjmiesz tu albo z domku.'));
                var actions = el('div', 'pets-window__actions');
                var link = el('a', 'pet-btn');
                link.href = ctx.href('domek');
                link.dataset.sceneLink = 'domek';
                link.innerHTML = u.icon('home') + '<span class="pet-btn__label"></span>';
                link.querySelector('.pet-btn__label').textContent = 'Do domku';
                link.setAttribute('data-window-key', 'house');
                actions.appendChild(link);
                box.appendChild(actions);
                return box;
            }
            box.appendChild(el('p', 'pets-window__text', 'W szpitalu chory pupil wraca do zdrowia, a jego potrzeby nie rosną.'));
            var hours = parseInt(state.config && state.config.hospital_hours, 10) || 0;
            var list = el('ul', 'pets-hosp-win__list');
            sick.forEach(function (pet) { list.appendChild(admitRow(pet, hours)); });
            box.appendChild(list);
            return box;
        }

        // --- otwieranie / podmiana / zamykanie ------------------------------------------------------------
        function onWindowClosed() {
            open = null;
            openSig = null;
            refs = null;
            confirm = false;
            dropWinRigs();
            markSelected(null);
            ctx.flushPats();
            if (ctx.isActive('izba')) ctx.setQuery({});
        }

        function swap(content) {
            var old = winRigs;
            winRigs = [];
            var node = content();
            win.replace(node);
            old.forEach(function (r) { if (r) r.destroy(); });
        }

        function openBed(id, o) {
            o = o || {};
            var pet = findHosp(lastState, id);
            var view = slotOf(id);
            if (!win || !pet || !view) return false;
            confirm = false;
            var old = winRigs;
            winRigs = [];
            open = { type: 'bed', id: id };
            openSig = bedSig(pet);
            ctx.flushPats();
            // Fokus zostaje na łóżku (Enter jeszcze raz = pat pat); z adresu albo po przyjęciu — na łóżko
            win.open({
                content: bedContent(pet), labelledBy: 'petsWardWinTitle', returnFocus: view.el,
                onClose: onWindowClosed, closeLabel: 'Zamknij okno pupila', focus: false
            });
            old.forEach(function (r) { if (r) r.destroy(); });
            if (o.focusBed) H.focus(view.el);
            markSelected(view);
            ctx.setQuery({ pupil: id });
            H.reveal(host, scroll, view.el);
            return true;
        }

        function openFree(slot) {
            var view = views[slot];
            if (!win || !view) return;
            var old = winRigs;
            winRigs = [];
            open = { type: 'free', slot: slot };
            openSig = freeSig(lastState);
            confirm = false;
            win.open({
                content: freeContent(lastState), labelledBy: 'petsWardWinTitle', returnFocus: view.el,
                onClose: onWindowClosed, closeLabel: 'Zamknij okno łóżka'
            });
            old.forEach(function (r) { if (r) r.destroy(); });
            markSelected(view);
            ctx.setQuery({});
            H.reveal(host, scroll, view.el);
        }

        function replaceBed(pet, focusKey) {
            openSig = bedSig(pet);
            swap(function () { return bedContent(pet); });
            if (focusKey) {
                var target = win.body.querySelector('[data-window-key="' + focusKey + '"]');
                if (target) H.focus(target);
            }
        }

        /** Stan zmienił się przy otwartym oknie (odświeżenie, druga karta, własna akcja). */
        function refreshWindow(state) {
            if (!open || !win || !win.isOpen()) return;
            if (open.type === 'free') {
                if (admitting != null) return;          // po przyjęciu okno pokaże przyjętego pupila
                var taken = slots[open.slot];
                if (taken != null) {
                    // Wolne łóżko zajął pupil przyjęty w innej karcie — okno pokazuje jego
                    var pet0 = findHosp(state, taken);
                    open = { type: 'bed', id: taken };
                    confirm = false;
                    replaceBed(pet0);
                    markSelected(slotOf(taken));
                    ctx.setQuery({ pupil: taken });
                } else if (freeSig(state) !== openSig) {
                    openSig = freeSig(state);
                    swap(function () { return freeContent(state); });
                }
                return;
            }
            var pet = findHosp(state, open.id);
            if (!pet) {
                if (discharging === open.id) return;    // odbiór w toku — zaraz przejście do domku
                H.closeGone(win, host);
                return;
            }
            if (pet.hospital.ready) confirm = false;
            if (bedSig(pet) !== openSig) replaceBed(pet);
            else if (refs) {
                refs.pet = pet;
                fillBed(refs);
            }
        }

        // --- akcje ----------------------------------------------------------------------------------
        function patBed(id) {
            var view = slotOf(id);
            if (!view || !view.rig || !ctx.pat(id)) return;
            if (typeof view.rig.pat === 'function') view.rig.pat();
            else view.rig.playAction('pat');
        }

        function onBedClick(slot) {
            var id = slots[slot];
            if (id == null) {
                openFree(slot);
                return;
            }
            if (open && open.type === 'bed' && open.id === id && win.isOpen()) {
                patBed(id);
                return;
            }
            openBed(id);
        }

        function discharge(btn) {
            var id = parseInt(btn.dataset.petId, 10);
            var pet = ctx.findPet(id);
            if (!pet || discharging != null) return;
            discharging = id;
            u.setBusy(btn, true);
            H.discharge(ctx, pet).then(function () {
                discharging = null;
                if (ctx.isActive('izba')) ctx.go('domek', { pupil: id });
                else if (lastState) render(lastState);
            }, function () {
                discharging = null;
                if (btn.isConnected) u.setBusy(btn, false);
                if (lastState) render(lastState);
            });
        }

        function admit(btn) {
            var id = parseInt(btn.dataset.petId, 10);
            var pet = ctx.findPet(id);
            if (!pet || admitting != null) return;
            admitting = id;
            if (open && open.type === 'free') prefer[id] = open.slot;
            u.setBusy(btn, true);
            H.admit(ctx, pet).then(function () {
                admitting = null;
                // Render już położył pupila w łóżku (to, z którego go przyjęto) — okno pokazuje jego
                if (!openBed(id, { focusBed: true }) && lastState) render(lastState);
            }, function () {
                admitting = null;
                delete prefer[id];
                if (btn.isConnected) u.setBusy(btn, false);
                if (lastState) render(lastState);
            });
        }

        host.addEventListener('click', function (e) {
            var bed = e.target.closest('[data-bed-slot]');
            if (bed && host.contains(bed)) {
                onBedClick(parseInt(bed.dataset.bedSlot, 10));
                return;
            }
            var btn = e.target.closest('[data-ward-action]');
            if (!btn || !host.contains(btn) || btn.disabled || btn.getAttribute('aria-disabled') === 'true') return;
            var action = btn.dataset.wardAction;
            if (action === 'discharge') {
                discharge(btn);
            } else if (action === 'early' || action === 'confirm-cancel') {
                var pet = open && open.type === 'bed' ? findHosp(lastState, open.id) : null;
                if (!pet) return;
                confirm = action === 'early';
                // „Zabierz wcześniej” → „Tak, zabieram” (jak dawniej); „Zostaw” → z powrotem „Zabierz wcześniej”
                replaceBed(pet, 'early');
            } else if (action === 'admit') {
                admit(btn);
            }
        });

        // --- parametry z adresu (?pupil=ID) ----------------------------------------------------------
        function applyParams(params, state) {
            pending = null;
            var id = params && params.pupil;
            if (!id) {
                if (open && open.type === 'bed' && win && win.isOpen()) win.close({ restoreFocus: false });
                return;
            }
            if (!findHosp(state, id)) {
                // W domku, odszedł, cudzy albo nieistniejący: sala bez okna, adres bez parametru
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                ctx.setQuery({});
                return;
            }
            if (open && open.type === 'bed' && open.id === id && win.isOpen()) return;
            openBed(id, { focusBed: true });
        }

        // --- render ----------------------------------------------------------------------------------
        function render(state) {
            lastState = state;
            var ids = H.inBed(state).map(function (p) { return p.id; });
            // max(3, n) łóżek — i zawsze jedno wolne, gdy w domku ktoś choruje (pielęgniarka kieruje tu z przyjęciem)
            var min = Math.max(MIN_SLOTS, ids.length + (H.sickAtHome(state).length ? 1 : 0));
            slots = H.syncSlots(slots, ids, min, prefer);
            slots.forEach(function (id) { if (id != null) delete prefer[id]; });
            syncViews(state);
            // Kolumn najwyżej tyle, ile łóżek; data-n = ile rzędów ma się zmieścić w pionie (CSS)
            room.style.setProperty('--n', String(slots.length));
            room.dataset.n = String(slots.length);
            tickClock();
            queueFloor();
            if (pending) {
                applyParams(pending, state);
                return;
            }
            refreshWindow(state);
        }

        return {
            enter: function (params) {
                pending = params || {};      // router woła render() zaraz po enter()
            },
            leave: function () {
                pending = null;
                admitting = null;
                discharging = null;
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                // Ukryta scena nie trzyma żywych rigów (timery mrugania i gestów) — render zbuduje je od nowa
                while (views.length) destroyView(views.pop());
                slots = [];
                prefer = {};
            },
            render: render,
            setParams: function (params) {
                var state = ctx.state();
                if (state) applyParams(params, state);
                else pending = params;
            },
            tick: function () {
                var state = ctx.state();
                if (!state) return;
                views.forEach(tickBed);
                tickClock();
                if (refs && open && open.type === 'bed') fillBed(refs);
            }
        };
    }

    W.scenes.izba = {
        title: 'Izba przyjęć',
        create: create
    };
})();
