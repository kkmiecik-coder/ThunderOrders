/**
 * Świat pupili — scena „inkubatorium” (spec v3.1 §4.3).
 *
 * - Rząd inkubatorów: lampa nad szklaną kopułą, w środku jajko z rigu (PetRig.mountEgg ze skórką), na
 *   podstawie tabliczka „36% · ~4 dni” (prognoza z ogrzaniem — PetsState.eggForecast). Stany: wylęgane
 *   (zwykłe światło), ogrzane (mocniejsze, cieplejsze), gotowe (iskry, „Gotowe! Wykluj”), wolny (przygaszony).
 * - Miejsc max(3, liczba jajek); jajko zostaje w swoim inkubatorze, gdy inne się wyklują (stałe miejsca).
 *   Siatka (CSS): ≥ 1024 px do 5 w rzędzie, 600–1023 px po 3, < 600 px po 2; nadmiar przewija wnętrze sceny.
 * - Klik w inkubator z jajkiem = okno sceny: źródło, pasek %, czas do wyklucia, ciepło, „Ogrzej” albo
 *   „Wykluj” (PetHatch: animacja + imię, potem domek z panelem nowego pupila). Klik w wolny = okno
 *   „Wolny inkubator” z linkiem do recepcji. `?jajko=ID` otwiera okno jajka (nieznany ID → bez okna).
 * - Jajka czekają na recepcji → tabliczka „Jajka do odebrania na recepcji →” (link do holu).
 * - Zmiana stanu przy otwartym oknie: jajko jest → treść odświeżona (win.replace przy zmianie przycisków,
 *   inaczej same liczby); zniknęło (wyklute w innej karcie) → okno się zamyka, fokus na scenie.
 * - Wystrój sali (feedback: „smutno i pusto”): girlanda światełek pod sufitem, tapeta w jajka i serduszka,
 *   lamperia, podłoga z dywanem; nad inkubatorami „ściana” (.pets-inc__wall — elastyczny pas w przepływie
 *   między tabliczką a rzędem, więc nigdy nie nachodzi na inkubatory): szyld z pisklęciem w skorupce (bez
 *   napisu — nazwę sali ma pigułka), karuzela-pozytywka, okno z firankami (dzień/noc), termometr (wyżej, gdy
 *   jakieś jajko jest ogrzane), półki z kocykami, butelkami i pluszakami, obrazek i tablica „Wykluło się w tym
 *   miesiącu”. Co się pokaże, decydują zapytania kontenera o wysokość tej ściany (CSS; przy wielu
 *   inkubatorach niska ściana dostaje chociaż małe okno). Po bokach rzędu na podłodze roślina i kosz
 *   z pluszakami — tylko gdy obok inkubatorów jest wolne miejsce, a w niskim i szerokim widoku okno i półki
 *   stają w bocznych kolumnach obok rzędu (mierzone w JS: layoutSides). Lampy wiszą na przewodach od sufitu
 *   (warstwa .pets-inc__cords za wszystkim, położenie z pomiaru inkubatorów — także po przewinięciu).
 *   Dekoracje: aria-hidden, bez zdarzeń (klik w nie = klik w tło sceny); tablica z liczbą jest zwykłym tekstem.
 * Rejestruje się w window.PetsWorld.scenes.inkubatorium.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.inkubatorium) return;

    var MIN_SLOTS = 3;

    // Tył inkubatora: przewód, klosz lampy, cień, podstawa (viewBox 120×190)
    var BACK_SVG =
        '<svg class="pets-incubator__back" viewBox="0 0 120 190" aria-hidden="true" focusable="false">' +
        '<path class="inc-cord" d="M60 0v24"/>' +
        '<path class="inc-shade" d="M42 22h36l13 20H29z"/>' +
        '<ellipse class="inc-bulb" cx="60" cy="44" rx="11" ry="5"/>' +
        '<ellipse class="inc-shadow" cx="60" cy="186" rx="50" ry="4"/>' +
        '</svg>';

    // Przód: szklana kopuła z odblaskiem i podstawa z wywietrznikami
    var FRONT_SVG =
        '<svg class="pets-incubator__front" viewBox="0 0 120 190" aria-hidden="true" focusable="false">' +
        '<path class="inc-dome" d="M22 148v-40a38 38 0 0 1 76 0v40z"/>' +
        '<path class="inc-shine" d="M33 120v-12a27 27 0 0 1 13-23"/>' +
        '<rect class="inc-rim" x="8" y="142" width="104" height="10" rx="5"/>' +
        '<rect class="inc-base" x="13" y="150" width="94" height="34" rx="9"/>' +
        '<g class="inc-vents"><circle cx="24" cy="160" r="2"/><circle cx="96" cy="160" r="2"/></g>' +
        '</svg>';

    function star(x, y, r) {
        var k = r * 0.28;
        return '<path d="M' + x + ' ' + (y - r) + 'L' + (x + k) + ' ' + (y - k) + 'L' + (x + r) + ' ' + y + 'L' + (x + k) + ' ' + (y + k) +
            'L' + x + ' ' + (y + r) + 'L' + (x - k) + ' ' + (y + k) + 'L' + (x - r) + ' ' + y + 'L' + (x - k) + ' ' + (y - k) + 'Z"/>';
    }

    // Iskry gotowego jajka
    var SPARKS_SVG =
        '<svg class="pets-incubator__sparks" viewBox="0 0 120 190" aria-hidden="true" focusable="false">' +
        star(26, 92, 7) + star(97, 100, 6) + star(88, 70, 5) + star(34, 66, 4.5) + '</svg>';

    // Pięcioramienna gwiazdka (karuzela, okno nocą)
    function star5(cx, cy, R, r) {
        var d = '';
        for (var i = 0; i < 10; i++) {
            var a = Math.PI / 5 * i - Math.PI / 2;
            var rad = i % 2 ? r : R;
            d += (i ? 'L' : 'M') + (cx + rad * Math.cos(a)).toFixed(1) + ' ' + (cy + rad * Math.sin(a)).toFixed(1);
        }
        return '<path d="' + d + 'Z"/>';
    }

    // Obrazek na ścianie (jajko i serduszko) — pod półkami, gdy ściana jest wysoka
    var POSTER_SVG =
        '<svg viewBox="0 0 80 96" focusable="false">' +
        '<rect class="poster-frame" x="2" y="2" width="76" height="92" rx="8"/>' +
        '<rect class="poster-paper" x="9" y="9" width="62" height="78" rx="4"/>' +
        '<path class="poster-egg" d="M40 22c9 0 15 14 15 23a15 15 0 0 1-30 0c0-9 6-23 15-23z"/>' +
        '<path class="poster-heart" d="M40 76s-11-6.5-11-13.5a6 6 0 0 1 11-3.3 6 6 0 0 1 11 3.3C51 69.5 40 76 40 76z"/>' +
        '</svg>';

    // Girlanda pod sufitem: jeden odcinek = zwis przewodu i żarówka (kolor żarówki z CSS, nth-child)
    var GARLAND_SEGMENTS = 11;
    var GARLAND_SEG =
        '<svg class="pets-inc__bulb" viewBox="0 0 100 32" preserveAspectRatio="xMidYMin meet" focusable="false">' +
        '<path class="gl-wire" d="M0 2Q50 22 100 2"/>' +
        '<g class="gl-bulb"><circle class="gl-halo" cx="50" cy="21" r="10"/>' +
        '<rect class="gl-cap" x="47" y="9.5" width="6" height="5.5" rx="1.5"/>' +
        '<path class="gl-glass" d="M50 14c3.4 0 5.2 3.6 5.2 6.8a5.2 5.2 0 0 1-10.4 0c0-3.2 1.8-6.8 5.2-6.8z"/>' +
        '<ellipse class="gl-shine" cx="48.4" cy="18.6" rx="1.2" ry="2"/></g>' +
        '</svg>';

    // Okno z firankami: niebo dzienne (słońce, chmurki) albo nocne (księżyc, gwiazdki), parapet z kwiatkiem
    var WINDOW_SVG =
        '<svg class="pets-inc__window-art" viewBox="0 0 160 196" focusable="false">' +
        '<rect class="win-frame" x="20" y="18" width="120" height="146" rx="16"/>' +
        '<rect class="win-sky" x="29" y="27" width="102" height="128" rx="9"/>' +
        '<g class="win-day">' +
        '<circle class="win-sun" cx="104" cy="54" r="12"/>' +
        '<g class="win-cloud"><path d="M42 86a8 8 0 0 1 8-8 12 12 0 0 1 22 2.5 7.5 7.5 0 0 1 1 14.5H50a8 8 0 0 1-8-9z"/></g>' +
        '<g class="win-cloud win-cloud--2"><path d="M84 120a6.5 6.5 0 0 1 6.5-6.5 10 10 0 0 1 18 2 6 6 0 0 1 .5 11.5H90.5A6.5 6.5 0 0 1 84 120z"/></g>' +
        '</g>' +
        '<g class="win-night">' +
        '<path class="win-moon" d="M106 38a16 16 0 1 0 10 28 12.5 12.5 0 1 1-10-28z"/>' +
        '<g class="win-stars">' + star5(52, 52, 4.5, 2) + star5(70, 100, 3.5, 1.5) + star5(112, 112, 4, 1.8) + star5(46, 132, 3, 1.3) + '</g>' +
        '</g>' +
        '<path class="win-bars" d="M80 27v128M29 91h102"/>' +
        '<path class="win-curtain" d="M8 12h40c-2 30-6 58-16 84 7 22 12 44 13 70H8z"/>' +
        '<path class="win-curtain" d="M152 12h-40c2 30 6 58 16 84-7 22-12 44-13 70h37z"/>' +
        '<path class="win-tie" d="M22 92c6-3 12-3 16 2-4 5-10 6-16 3z"/>' +
        '<path class="win-tie" d="M138 92c-6-3-12-3-16 2 4 5 10 6 16 3z"/>' +
        '<path class="win-valance" d="M6 10h148v14q-9 9-18.5 0-9.25 9-18.5 0-9.25 9-18.5 0-9.25 9-18.5 0-9.25 9-18.5 0-9.25 9-18.5 0-9.25 9-18.5 0-9.25 9-18.5 0z"/>' +
        '<rect class="win-rod" x="2" y="6" width="156" height="6" rx="3"/>' +
        '<rect class="win-sill" x="10" y="162" width="140" height="11" rx="5"/>' +
        '<path class="win-leaf" d="M57 149c-9-4-13-12-10-19 8 3 11 11 10 19zM61 149c2-10 8-15 15-14-1 9-7 14-15 14zM59 148c-3-9 0-17 6-21 3 8 0 16-6 21z"/>' +
        '<circle class="win-flower" cx="65" cy="127" r="4"/>' +
        '<path class="win-pot" d="M48 148h22l-3 14H51z"/>' +
        '</svg>';

    // Termometr przy oknie: rtęć wyżej, gdy jakieś jajko jest ogrzane (.has-warm na scenie)
    var THERMO_SVG =
        '<svg viewBox="0 0 32 120" focusable="false">' +
        '<rect class="th-board" x="2" y="2" width="28" height="116" rx="14"/>' +
        '<path class="th-heart" d="M16 15s-5-3-5-6.4a2.7 2.7 0 0 1 5-1.4 2.7 2.7 0 0 1 5 1.4C21 12 16 15 16 15z"/>' +
        '<rect class="th-tube" x="12" y="22" width="8" height="72" rx="4"/>' +
        '<rect class="th-merc" x="14" y="26" width="4" height="72" rx="2"/>' +
        '<circle class="th-bulb" cx="16" cy="100" r="8.5"/>' +
        '<path class="th-ticks" d="M22 32h4M22 44h3M22 56h4M22 68h3M22 80h4"/>' +
        '</svg>';

    // Karuzela-pozytywka: obręcz na sznurku, pięć zawieszek (gwiazdka, księżyc, jajko, serduszko, chmurka), nutki
    var MOBILE_SVG =
        '<svg viewBox="0 0 200 190" focusable="false">' +
        '<g class="mob-notes"><path class="mob-note" d="M28 18v-12l9-2v12"/><circle class="mob-note-head" cx="26" cy="18" r="3"/>' +
        '<circle class="mob-note-head" cx="35" cy="16" r="3"/>' +
        '<path class="mob-note mob-note--2" d="M176 24v-12"/><circle class="mob-note-head mob-note--2" cx="174" cy="24" r="3"/></g>' +
        '<g class="mob-swing">' +
        '<path class="mob-string" d="M100 0v30"/>' +
        '<g class="mob-item mob-item--1"><path class="mob-string" d="M34 40v38"/><g class="mob-star">' + star5(34, 90, 13, 5.6) + '</g></g>' +
        '<g class="mob-item mob-item--2"><path class="mob-string" d="M67 44v62"/><path class="mob-moon" d="M64 106a14 14 0 1 0 15 21 11 11 0 1 1-15-21z"/></g>' +
        '<g class="mob-item mob-item--3"><path class="mob-string" d="M100 45v82"/>' +
        '<path class="mob-egg" d="M100 127c8 0 13.5 11.5 13.5 19a13.5 13.5 0 0 1-27 0c0-7.5 5.5-19 13.5-19z"/>' +
        '<circle class="mob-egg-spot" cx="95" cy="141" r="2.6"/><circle class="mob-egg-spot" cx="105" cy="151" r="2.2"/></g>' +
        '<g class="mob-item mob-item--4"><path class="mob-string" d="M133 44v62"/><path class="mob-heart" d="M133 132s-13-7.5-13-16a6.8 6.8 0 0 1 13-3.4 6.8 6.8 0 0 1 13 3.4c0 8.5-13 16-13 16z"/></g>' +
        '<g class="mob-item mob-item--5"><path class="mob-string" d="M166 40v40"/><path class="mob-cloud" d="M152 92a7 7 0 0 1 6.5-8 9.5 9.5 0 0 1 17.5 1 6.5 6.5 0 0 1 1.5 12.6h-19.5a6.5 6.5 0 0 1-6-5.6z"/></g>' +
        '<ellipse class="mob-ring" cx="100" cy="36" rx="74" ry="9"/>' +
        '<circle class="mob-knob" cx="100" cy="30" r="5.5"/>' +
        '</g></svg>';

    // Półki: kocyki w kostkę, butelki, słoiczek; niżej miś, króliczek i zwinięty kocyk
    var SHELVES_SVG =
        '<svg viewBox="0 0 210 236" focusable="false">' +
        '<path class="sh-bracket" d="M30 104v14l12-14zM180 104v14l-12-14zM30 222v12l12-12zM180 222v12l-12-12z"/>' +
        '<rect class="sh-blanket sh-blanket--3" x="16" y="82" width="70" height="14" rx="6"/>' +
        '<rect class="sh-blanket sh-blanket--2" x="20" y="68" width="64" height="14" rx="6"/>' +
        '<rect class="sh-blanket sh-blanket--1" x="18" y="54" width="66" height="14" rx="6"/>' +
        '<path class="sh-fold" d="M26 61h52M28 75h48M24 89h56"/>' +
        '<path class="sh-nipple" d="M110 44c0-5 3-8 5-8s5 3 5 8z"/><rect class="sh-cap" x="106" y="44" width="18" height="8" rx="3"/>' +
        '<rect class="sh-bottle" x="104" y="52" width="22" height="44" rx="7"/><rect class="sh-milk" x="106" y="70" width="18" height="24" rx="5"/>' +
        '<path class="sh-nipple sh-nipple--2" d="M140 52c0-5 3-8 5-8s5 3 5 8z"/><rect class="sh-cap sh-cap--2" x="136" y="52" width="18" height="8" rx="3"/>' +
        '<rect class="sh-bottle" x="134" y="60" width="22" height="36" rx="7"/><rect class="sh-milk" x="136" y="76" width="18" height="18" rx="5"/>' +
        '<path class="sh-ticks" d="M118 60h5M118 66h5M148 68h5M148 74h5"/>' +
        '<rect class="sh-jar-lid" x="166" y="62" width="28" height="7" rx="3"/><rect class="sh-jar" x="164" y="68" width="32" height="28" rx="8"/>' +
        '<path class="sh-jar-heart" d="M180 88s-6-3.5-6-7.4a3.1 3.1 0 0 1 6-1.6 3.1 3.1 0 0 1 6 1.6c0 3.9-6 7.4-6 7.4z"/>' +
        '<rect class="sh-plank" x="6" y="96" width="198" height="9" rx="4"/>' +
        '<circle class="sh-teddy" cx="34" cy="148" r="9"/><circle class="sh-teddy" cx="66" cy="148" r="9"/>' +
        '<ellipse class="sh-teddy" cx="50" cy="196" rx="27" ry="23"/>' +
        '<circle class="sh-teddy" cx="50" cy="166" r="22"/>' +
        '<circle class="sh-teddy-in" cx="34" cy="148" r="4.5"/><circle class="sh-teddy-in" cx="66" cy="148" r="4.5"/>' +
        '<ellipse class="sh-teddy-in" cx="50" cy="174" rx="9" ry="7"/><ellipse class="sh-teddy-in" cx="50" cy="200" rx="14" ry="12"/>' +
        '<g class="sh-eyes"><circle cx="42" cy="162" r="2.6"/><circle cx="58" cy="162" r="2.6"/><ellipse cx="50" cy="171" rx="3.2" ry="2.4"/></g>' +
        '<path class="sh-bow" d="M50 189l-11-6v12zM50 189l11-6v12z"/><circle class="sh-bow-knot" cx="50" cy="189" r="3"/>' +
        '<path class="sh-bunny" d="M112 160c-4-16-3-32 4-34 6 2 6 18 2 34zM128 160c0-16 4-31 11-32 6 3 3 19-3 33z"/>' +
        '<path class="sh-bunny-in" d="M114 156c-2-11-1-22 2-24 3 2 3 13 1 24zM130 156c1-11 3-21 7-22 3 3 1 13-2 23z"/>' +
        '<ellipse class="sh-bunny" cx="124" cy="200" rx="22" ry="22"/>' +
        '<circle class="sh-bunny" cx="124" cy="172" r="18"/>' +
        '<g class="sh-eyes"><circle cx="117" cy="170" r="2.4"/><circle cx="131" cy="170" r="2.4"/></g>' +
        '<ellipse class="sh-cheek" cx="113" cy="177" rx="3.5" ry="2.4"/><ellipse class="sh-cheek" cx="135" cy="177" rx="3.5" ry="2.4"/>' +
        '<path class="sh-mouth" d="M121 177q3 3 6 0"/>' +
        '<rect class="sh-roll" x="154" y="190" width="44" height="32" rx="16"/>' +
        '<circle class="sh-roll-end" cx="182" cy="206" r="11"/><circle class="sh-roll-end" cx="182" cy="206" r="5"/>' +
        '<rect class="sh-plank" x="6" y="214" width="198" height="9" rx="4"/>' +
        '</svg>';

    // Roślina w doniczce (podłoga, lewa strona)
    var PLANT_SVG =
        '<svg viewBox="0 0 110 180" focusable="false">' +
        '<g class="pl-leaves">' +
        '<path class="pl-leaf pl-leaf--b" d="M55 120C46 92 26 80 8 84c4 20 22 34 47 36z"/>' +
        '<path class="pl-leaf pl-leaf--b" d="M55 120c9-28 29-40 47-36-4 20-22 34-47 36z"/>' +
        '<path class="pl-leaf" d="M55 118C41 96 22 62 24 38c20 12 31 46 31 80z"/>' +
        '<path class="pl-leaf" d="M55 118c14-22 33-56 31-80-20 12-31 46-31 80z"/>' +
        '<path class="pl-leaf pl-leaf--c" d="M55 116C45 84 42 46 55 16c13 30 10 68 0 100z"/>' +
        '<path class="pl-vein" d="M55 112V30M55 116C44 92 33 68 28 46M55 116c11-24 22-48 27-70M53 118C40 104 26 94 14 88M57 118c13-14 27-24 39-30"/>' +
        '</g>' +
        '<path class="pl-pot" d="M26 122h58l-7 54H33z"/>' +
        '<rect class="pl-rim" x="22" y="114" width="66" height="14" rx="7"/>' +
        '<path class="pl-stripe" d="M30 146h50"/>' +
        '<path class="pl-heart" d="M55 166s-6-3.6-6-7.6a3.2 3.2 0 0 1 6-1.6 3.2 3.2 0 0 1 6 1.6c0 4-6 7.6-6 7.6z"/>' +
        '</svg>';

    // Kosz z kocykiem, misiem i kłębkiem włóczki (podłoga, prawa strona)
    var BASKET_SVG =
        '<svg viewBox="0 0 150 120" focusable="false">' +
        '<circle class="bk-teddy" cx="58" cy="30" r="8"/><circle class="bk-teddy" cx="86" cy="30" r="8"/>' +
        '<circle class="bk-teddy-in" cx="58" cy="30" r="4"/><circle class="bk-teddy-in" cx="86" cy="30" r="4"/>' +
        '<circle class="bk-teddy" cx="72" cy="46" r="20"/>' +
        '<ellipse class="bk-teddy-in" cx="72" cy="54" rx="8" ry="6"/>' +
        '<g class="bk-eyes"><circle cx="65" cy="43" r="2.4"/><circle cx="79" cy="43" r="2.4"/><ellipse cx="72" cy="51" rx="3" ry="2.2"/></g>' +
        '<path class="bk-blanket" d="M14 60c18-12 44-8 60-2s38 8 62-2l-4 20H18z"/>' +
        '<path class="bk-blanket-dots" d="M30 62h.1M48 58h.1M100 64h.1M118 60h.1M66 64h.1"/>' +
        '<path class="bk-body" d="M12 66h126l-12 50H24z"/>' +
        '<path class="bk-weave" d="M18 80h114M21 94h108M24 107h102M40 66l-4 50M62 66l-2 50M88 66l2 50M110 66l4 50"/>' +
        '<rect class="bk-rim" x="8" y="62" width="134" height="10" rx="5"/>' +
        '</svg>';

    // Szyld nad karuzelą: pisklę wygląda ze skorupki (zamiast napisu „Inkubatorium” — ten jest w pigułce)
    var CHICK_SVG =
        '<svg class="pets-inc__sign-art" viewBox="0 0 48 30" focusable="false">' +
        '<path class="sg-tuft" d="M22.5 4.5c.4-2 1.4-3 2.8-3.2-.3 1-.2 2 .4 2.8"/>' +
        '<circle class="sg-chick" cx="24" cy="13" r="9"/>' +
        '<ellipse class="sg-cheek" cx="18.6" cy="15.2" rx="1.7" ry="1.1"/><ellipse class="sg-cheek" cx="29.4" cy="15.2" rx="1.7" ry="1.1"/>' +
        '<circle class="sg-eye" cx="20.8" cy="12" r="1.25"/><circle class="sg-eye" cx="27.2" cy="12" r="1.25"/>' +
        '<path class="sg-beak" d="M22.4 14.6h3.2L24 17z"/>' +
        '<path class="sg-shell" d="M11 16.5l3.4 3 3.2-3 3.2 3 3.2-3 3.2 3 3.2-3 3.2 3 3.4-3c0 7.2-5.6 12-13 12s-13-4.8-13-12z"/>' +
        '<path class="sg-spark" d="M5 9l.9 2.1 2.1.9-2.1.9L5 15l-.9-2.1L2 12l2.1-.9zM43 6l.8 1.7 1.7.8-1.7.8L43 11l-.8-1.7-1.7-.8 1.7-.8z"/>' +
        '</svg>';

    // Skorupka po wykluciu (tablica „Wykluło się w tym miesiącu”: jedna na pupila, najwyżej 5)
    var SHELL_SVG =
        '<svg viewBox="0 0 24 20" focusable="false"><path d="M3 9l3-3 3 3 3-3 3 3 3-3 3 3c0 5.5-4 9.5-9 9.5S3 14.5 3 9z"/></svg>';

    var SIDE_GAP = 12;               // min. odstęp rośliny/kosza od inkubatora i krawędzi sceny (px)
    var SIDE_MIN = 48;               // węższa roślina/kosz wyglądałyby jak okruch — wtedy ich nie ma
    // Okno i półki na ścianie nad rzędem: progi jak w CSS (@container inc-wall …) — poniżej boczne kolumny
    var WALL_GROUPS_H = 150;
    var WALL_GROUPS_W = 600;
    var ASIDE_MIN_W = 110;           // boczna kolumna (= @container inc-aside w CSS)
    var ASIDE_MIN_H = 130;

    var ARROW_SVG =
        '<svg class="pets-inc__note-arrow" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" ' +
        'stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg>';

    function create(ctx, host) {
        var H = window.PetsHospital;
        var u = ctx.u;
        var el = u.el;
        var R = function () { return window.PetRig; };

        var lastState = null;
        var slots = [];              // id jajka albo null (wolny) — stałe miejsca
        var views = [];              // widok inkubatora na miejsce
        var open = null;             // {type: 'egg', id} | {type: 'free', slot}
        var openSig = null;
        var refs = null;             // elementy okna jajka odświeżane co sekundę
        var pending = null;          // parametry z adresu czekające na stan
        var hatching = null;         // id jajka w trakcie wyklucia (nakładka PetHatch)

        // --- szkielet -------------------------------------------------------------------------
        /** Dekoracja: bez czytnika ekranu i bez zdarzeń (CSS: pointer-events: none). */
        function decor(tag, className, html) {
            var node = el(tag, className);
            node.setAttribute('aria-hidden', 'true');
            if (html) node.innerHTML = html;
            return node;
        }

        var stage = el('div', 'pets-stage pets-inc');
        // Tło sali (kolejność = warstwy pod inkubatorami): ciepłe światło, przewody lamp, girlanda, podłoga, dywan,
        // boki
        var garlandHtml = '';
        for (var g = 0; g < GARLAND_SEGMENTS; g++) garlandHtml += GARLAND_SEG;
        var glow = decor('div', 'pets-inc__light');
        var cordsLayer = decor('div', 'pets-inc__cords');
        var garland = decor('div', 'pets-inc__garland', garlandHtml);
        var floor = decor('div', 'pets-inc__floor');
        var rug = decor('div', 'pets-inc__rug');
        var sideL = decor('div', 'pets-inc__side pets-inc__side--l', PLANT_SVG);
        var sideR = decor('div', 'pets-inc__side pets-inc__side--r', BASKET_SVG);
        // Boczne kolumny na okno i półki (niski, szeroki widok — patrz layoutSides)
        var asideL = decor('div', 'pets-inc__aside pets-inc__aside--l');
        var asideR = decor('div', 'pets-inc__aside pets-inc__aside--r');
        var pillEl = ctx.root.querySelector('.pets-pill');

        var scroll = el('div', 'pets-scroll pets-inc__scroll');
        scroll.setAttribute('data-window-backdrop', '');
        var note = el('a', 'pets-inc__note');
        note.href = ctx.href('szpital');
        note.dataset.sceneLink = 'szpital';
        note.appendChild(el('span', 'pets-inc__note-text', 'Jajka do odebrania na recepcji'));
        note.insertAdjacentHTML('beforeend', ARROW_SVG);
        note.hidden = true;

        // Ściana nad inkubatorami: elastyczny pas w przepływie (zajmuje tylko wolne miejsce nad rzędem)
        var wall = el('div', 'pets-inc__wall');
        var groupL = el('div', 'pets-inc__group pets-inc__group--l');
        var winBox = decor('div', 'pets-inc__window', WINDOW_SVG);
        winBox.appendChild(decor('span', 'pets-inc__thermo', THERMO_SVG));
        var board = el('div', 'pets-inc__board');
        board.appendChild(decor('span', 'pets-inc__board-pin'));
        board.appendChild(el('span', 'pets-inc__board-title', 'Wykluło się w tym miesiącu'));
        var boardCount = el('span', 'pets-inc__board-count', '0');
        var boardShells = decor('span', 'pets-inc__board-shells');
        var boardEmpty = el('span', 'pets-inc__board-empty', 'Kto będzie pierwszy?');
        board.appendChild(boardCount);
        board.appendChild(boardShells);
        board.appendChild(boardEmpty);
        groupL.appendChild(winBox);
        groupL.appendChild(board);
        var groupC = decor('div', 'pets-inc__group pets-inc__group--c');
        var sign = el('span', 'pets-inc__sign');
        var signArt = el('span', 'pets-inc__sign-text');
        signArt.innerHTML = CHICK_SVG;
        sign.appendChild(signArt);
        groupC.appendChild(sign);
        groupC.appendChild(el('span', 'pets-inc__mobile'));
        groupC.lastChild.innerHTML = MOBILE_SVG;
        var groupR = decor('div', 'pets-inc__group pets-inc__group--r');
        groupR.appendChild(el('span', 'pets-inc__shelves'));
        groupR.lastChild.innerHTML = SHELVES_SVG;
        groupR.appendChild(el('span', 'pets-inc__frame'));
        groupR.lastChild.innerHTML = POSTER_SVG;
        wall.appendChild(groupL);
        wall.appendChild(groupC);
        wall.appendChild(groupR);

        var row = el('div', 'pets-inc__row');
        scroll.appendChild(note);
        scroll.appendChild(wall);
        scroll.appendChild(row);
        [glow, cordsLayer, garland, floor, rug, sideL, sideR, asideL, asideR, scroll].forEach(function (node) { stage.appendChild(node); });
        host.appendChild(stage);

        var win = window.PetsSceneWindow ? window.PetsSceneWindow.attach(host) : null;

        function findEgg(state, id) {
            var list = (state && state.eggs) || [];
            for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
            return null;
        }

        // --- inkubatory -----------------------------------------------------------------------
        function slotView(i) {
            var b = el('button', 'pets-incubator');
            b.type = 'button';
            b.dataset.incSlot = String(i);
            b.innerHTML = BACK_SVG;
            var glow = el('span', 'pets-incubator__glow');
            glow.setAttribute('aria-hidden', 'true');
            var eggBox = el('span', 'pets-incubator__egg');
            eggBox.setAttribute('aria-hidden', 'true');
            b.appendChild(glow);
            b.appendChild(eggBox);
            b.insertAdjacentHTML('beforeend', FRONT_SVG + SPARKS_SVG);
            var plate = el('span', 'pets-incubator__plate');
            plate.setAttribute('aria-hidden', 'true');
            b.appendChild(plate);
            return { el: b, eggBox: eggBox, plate: plate, rig: null, eggId: undefined, egg: null, rigSig: '' };
        }

        function destroyView(view) {
            if (view.rig) view.rig.destroy();
            if (view.el.parentNode) view.el.parentNode.removeChild(view.el);
        }

        function setText(node, text) {
            if (node.textContent !== text) node.textContent = text;
        }

        function eggLabel(egg, st) {
            var name = H.eggTitle(egg.source).toLowerCase();
            if (st.ready) return 'Inkubator: ' + name + ' — gotowe do wyklucia';
            var eta = st.eta ? (st.eta.indexOf('za') === 0 ? st.eta : 'za ' + st.eta) : '';
            return 'Inkubator: ' + name + ', ' + st.pct + '%' + (eta ? ', wykluje się ' + eta : '') + (st.boosted ? ', ogrzane' : '');
        }

        function tickSlot(view, state) {
            var egg = view.egg;
            var b = view.el;
            var label;
            if (!egg) {
                b.classList.add('is-free');
                b.classList.remove('is-ready', 'is-boosted');
                setText(view.plate, 'wolny');
                label = 'Wolny inkubator';
            } else {
                var st = H.eggStatus(egg, state, u);
                b.classList.remove('is-free');
                b.classList.toggle('is-ready', st.ready);
                b.classList.toggle('is-boosted', st.boosted);
                var sig = [st.pct, st.boosted, st.ready].join('|');
                if (view.rig && sig !== view.rigSig) {
                    view.rigSig = sig;
                    view.rig.update({ pct: st.pct, boosted: st.boosted, ready: st.ready });
                }
                setText(view.plate, st.plate);
                label = eggLabel(egg, st);
            }
            if (b.getAttribute('aria-label') !== label) b.setAttribute('aria-label', label);
        }

        function updateSlot(view, egg, state) {
            var id = egg ? egg.id : null;
            if (view.eggId !== id) {
                if (view.rig) view.rig.destroy();
                view.rig = null;
                view.rigSig = '';
                view.eggId = id;
                if (egg && R()) {
                    view.rig = R().mountEgg(view.eggBox, {
                        pct: egg.progress_pct, boosted: !!egg.boost_until, ready: !!egg.ready, size: 'mini', skin: egg.skin || 0
                    });
                }
            } else if (egg && view.rig && view.egg && view.egg.skin !== egg.skin) {
                view.rig.update({ skin: egg.skin || 0 });
            }
            view.egg = egg;
            if (egg) view.el.dataset.eggId = String(egg.id);
            else delete view.el.dataset.eggId;
            tickSlot(view, state);
        }

        function syncViews(state) {
            while (views.length < slots.length) {
                var v = slotView(views.length);
                views.push(v);
                row.appendChild(v.el);
            }
            while (views.length > slots.length) destroyView(views.pop());
            slots.forEach(function (id, i) { updateSlot(views[i], id == null ? null : findEgg(state, id), state); });
        }

        function slotOf(id) {
            var i = slots.indexOf(id);
            return i >= 0 ? views[i] : null;
        }

        function markSelected(view) {
            views.forEach(function (v) { v.el.classList.toggle('is-selected', v === view); });
        }

        // --- wystrój: tablica, termometr, roślina i kosz po bokach -----------------------------------
        /** Ilu żyjących pupili wykluło się w tym miesiącu (polskim, czas serwera; age_days = pełne doby od wyklucia). */
        function hatchedThisMonth(state) {
            var p = u.plParts(u.serverNow());
            var sinceStart = (p.day - 1) * 86400 + p.hour * 3600 + p.minute * 60 + p.second;
            return ((state && state.pets) || []).filter(function (p) {
                var age = Number(p.age_days);
                return age >= 0 && age * 86400 < sinceStart;
            }).length;
        }

        var boardN = -1;
        function updateBoard(state) {
            var n = hatchedThisMonth(state);
            if (n === boardN) return;
            boardN = n;
            boardCount.textContent = String(n);
            board.classList.toggle('is-empty', n === 0);
            var html = '';
            for (var i = 0; i < Math.min(n, 5); i++) html += SHELL_SVG;
            boardShells.innerHTML = html;
        }

        function syncWarm() {
            stage.classList.toggle('has-warm', views.some(function (v) { return v.el.classList.contains('is-boosted'); }));
        }

        /**
         * Boki rzędu (pomiar w px układu — dzielone przez skalę przejścia sceny):
         * - roślina (lewa) i kosz (prawa) stoją na podłodze tylko wtedy, gdy obok skrajnych inkubatorów jest na
         *   nie miejsce — na środku wolnego pasa, na wysokości podstaw inkubatorów (--inc-base);
         * - gdy ściana nad rzędem jest za niska na okno i półki (niski, szeroki widok), a pasy obok rzędu są
         *   szerokie, okno z termometrem i półki przechodzą do bocznych kolumn (placeAside).
         */
        function layoutSides() {
            var box = stage.getBoundingClientRect();
            if (!box.width || !stage.offsetWidth) return;
            var k = box.width / stage.offsetWidth;
            layoutCords(box, k);
            var rects = [];
            var left = Infinity, right = -Infinity, bottom = -Infinity, incH = 0;
            views.forEach(function (v) {
                var r = v.el.getBoundingClientRect();
                if (!r.width) return;
                rects.push(r);
                left = Math.min(left, r.left);
                right = Math.max(right, r.right);
                bottom = Math.max(bottom, r.bottom);
                incH = Math.max(incH, r.height / k);
            });
            if (!rects.length) return;
            // Rząd przewija się (wiele jajek): dywan na stałej wysokości (CSS), bez rośliny i kosza — inkubatory
            // przesuwałyby się po nich
            var overflow = scroll.scrollHeight > scroll.clientHeight + 1;
            var base = !overflow && bottom <= box.bottom ? (box.bottom - bottom) / k : null;
            if (base != null) stage.style.setProperty('--inc-base', Math.round(base) + 'px');
            else stage.style.removeProperty('--inc-base');
            // Na podłodze liczy się dolny rząd (np. 2 + 1 na telefonie: obok samotnego inkubatora jest miejsce)
            var lowL = Infinity, lowR = -Infinity;
            rects.forEach(function (r) {
                if (r.bottom < bottom - 2) return;
                lowL = Math.min(lowL, r.left);
                lowR = Math.max(lowR, r.right);
            });
            placeSide(sideL, overflow ? 0 : (lowL - box.left) / k, rects);
            placeSide(sideR, overflow ? 0 : (box.right - lowR) / k, rects);
            var roomL = (left - box.left) / k;
            var roomR = (box.right - right) / k;
            var floorTop = box.height / k - (base == null ? 0 : base) - incH * 0.3;
            var wallFits = wall.clientHeight >= WALL_GROUPS_H && wall.clientWidth >= WALL_GROUPS_W;
            placeAside(asideL, groupL, groupC, !wallFits && roomL, box, k, floorTop, pillEl);
            placeAside(asideR, groupR, null, !wallFits && roomR, box, k, floorTop, note);
        }

        /**
         * Boczna kolumna (okno albo półki) w pasie `room` obok rzędu: pod przeszkodą u góry (pigułka / tabliczka,
         * gdy zachodzą na ten pas), nad rośliną / koszem (albo nad linią podłogi). Za ciasno → grupa wraca na ścianę.
         */
        function placeAside(aside, group, before, room, box, k, floorTop, above) {
            var w = Math.floor((room || 0) - 2 * SIDE_GAP);
            var top = 76;
            var bottom = floorTop;
            var side = aside === asideL ? sideL : sideR;
            if (w >= ASIDE_MIN_W) {
                var stageX = function (x) { return (x - box.left) / k; };
                var r = above && !above.hidden ? above.getBoundingClientRect() : null;
                if (r && r.width) {
                    var x0 = aside === asideL ? 0 : box.width / k - room;
                    var x1 = aside === asideL ? room : box.width / k;
                    if (stageX(r.right) > x0 && stageX(r.left) < x1) top = Math.max(top, (r.bottom - box.top) / k + 12);
                }
                if (side.classList.contains('is-shown')) bottom = (side.getBoundingClientRect().top - box.top) / k;
                bottom -= 12;
            }
            var on = w >= ASIDE_MIN_W && bottom - top >= ASIDE_MIN_H;
            aside.classList.toggle('is-shown', on);
            if (on) {
                aside.style.setProperty('--aside-x', SIDE_GAP + 'px');
                aside.style.setProperty('--aside-top', Math.round(top) + 'px');
                aside.style.setProperty('--aside-w', w + 'px');
                aside.style.setProperty('--aside-h', Math.floor(bottom - top) + 'px');
                if (group.parentNode !== aside) aside.appendChild(group);
            } else if (group.parentNode !== wall) {
                wall.insertBefore(group, before);
            }
        }

        /**
         * Dekoracja boku: najwyżej tak szeroka, jak wolny pas (bez odstępów); węższa niż SIDE_MIN albo zachodząca
         * na któryś inkubator (wyższy rząd) — nie stoi.
         */
        function placeSide(node, room, rects) {
            var max = Math.floor(room - 2 * SIDE_GAP);
            if (max < SIDE_MIN) {
                node.classList.remove('is-shown');
                return;
            }
            node.style.setProperty('--side-max', max + 'px');
            var w = node.offsetWidth;
            node.style.setProperty('--side-x', Math.round((room - w) / 2) + 'px');
            var r = node.getBoundingClientRect();
            var hit = rects.some(function (q) {
                return r.left < q.right && r.right > q.left && r.top < q.bottom && r.bottom > q.top;
            });
            node.classList.toggle('is-shown', w >= SIDE_MIN && !hit);
        }

        // --- przewody lamp: od sufitu (góra sceny) do klosza każdego inkubatora --------------------------
        // Warstwa za girlandą, ścianą i inkubatorami: przewód inkubatora z dolnego rzędu chowa się za tymi wyżej.
        // Grubość jak przewód w SVG inkubatora (2,5 jedn. viewBoxu 120 px szerokości).
        var cordEls = [];
        var cordsQueued = false;

        function layoutCords(box, k) {
            while (cordEls.length < views.length) {
                var c = decor('span', 'pets-inc__cord');
                cordsLayer.appendChild(c);
                cordEls.push(c);
            }
            while (cordEls.length > views.length) cordsLayer.removeChild(cordEls.pop());
            views.forEach(function (v, i) {
                var cord = cordEls[i];
                var r = v.el.getBoundingClientRect();
                var h = (r.top - box.top) / k + 3;        // +3 px: zakładka z przewodem w SVG inkubatora
                cord.hidden = !r.width || h <= 0;
                if (cord.hidden) return;
                cord.classList.toggle('is-free', v.el.classList.contains('is-free'));
                cord.style.setProperty('--cord-x', ((r.left + r.width / 2 - box.left) / k).toFixed(1) + 'px');
                cord.style.setProperty('--cord-h', h.toFixed(1) + 'px');
                cord.style.setProperty('--cord-w', Math.max(1.5, 2.5 * r.width / k / 120).toFixed(2) + 'px');
            });
        }

        function syncCords() {
            cordsQueued = false;
            var box = stage.getBoundingClientRect();
            if (box.width && stage.offsetWidth) layoutCords(box, box.width / stage.offsetWidth);
        }

        // Przewinięcie wnętrza (dużo jajek) przesuwa inkubatory — przewody za nimi
        scroll.addEventListener('scroll', function () {
            if (cordsQueued) return;
            cordsQueued = true;
            // Ukryta karta nie rysuje klatek — wtedy od razu
            if (document.visibilityState === 'hidden' || !window.requestAnimationFrame) syncCords();
            else window.requestAnimationFrame(syncCords);
        }, { passive: true });

        if (window.ResizeObserver) {
            var sidesObs = new ResizeObserver(function () { layoutSides(); });
            sidesObs.observe(stage);
            sidesObs.observe(row);
        }

        // --- okna -----------------------------------------------------------------------------
        function eggSig(egg) {
            return [egg.id, egg.source, !!egg.ready, egg.can_warm !== false, !!egg.boost_until].join('|');
        }

        function fillEgg(r) {
            var st = H.eggStatus(r.egg, lastState, u);
            r.bar.set(st.pct);
            setText(r.pct, st.pct + '%');
            var eta;
            if (st.ready) eta = 'Gotowe do wyklucia!';
            else if (!st.eta) eta = '';
            else eta = 'Wykluje się ' + (st.eta.indexOf('za') === 0 ? st.eta : 'za ' + st.eta) + '.';
            setText(r.eta, eta);
            r.eta.hidden = !eta;
            var heat = '';
            if (!st.ready) {
                if (st.boosted) heat = st.heat;
                else if (r.egg.can_warm !== false) heat = 'Ogrzej je, żeby wykluło się szybciej.';
            }
            setText(r.heat, heat);
            r.heat.hidden = !heat;
        }

        function eggContent(egg) {
            var box = el('div', 'pets-hosp-win pets-hosp-win--egg');
            var title = el('h2', 'pets-window__title', H.eggTitle(egg.source));
            title.id = 'petsIncWinTitle';
            box.appendChild(title);
            var meter = el('div', 'pets-hosp-win__meter');
            var bar = H.progress(u, 'Postęp inkubacji', false);
            var pct = el('span', 'pets-hosp-win__pct');
            pct.setAttribute('aria-hidden', 'true');
            meter.appendChild(bar.el);
            meter.appendChild(pct);
            box.appendChild(meter);
            var eta = el('p', 'pets-window__text pets-hosp-win__eta');
            var heat = el('p', 'pets-window__text pets-hosp-win__heat');
            heat.id = 'petsIncHeat';
            box.appendChild(eta);
            box.appendChild(heat);
            var actions = el('div', 'pets-window__actions');
            var btn;
            if (egg.ready) {
                btn = u.button('Wykluj', 'sparkle', 'primary', { incAction: 'hatch', eggId: String(egg.id) });
                btn.setAttribute('data-window-key', 'hatch');
            } else {
                btn = u.button('Ogrzej', 'flame', null, { incAction: 'warm', eggId: String(egg.id) });
                btn.setAttribute('data-window-key', 'warm');
                if (egg.can_warm === false) {
                    // Zostaje fokusowalny (aria-disabled), a powód czyta się z linii o cieple
                    btn.setAttribute('aria-disabled', 'true');
                    btn.setAttribute('aria-describedby', heat.id);
                }
            }
            actions.appendChild(btn);
            box.appendChild(actions);
            refs = { egg: egg, bar: bar, pct: pct, eta: eta, heat: heat };
            fillEgg(refs);
            return box;
        }

        function freeContent() {
            var box = el('div', 'pets-hosp-win pets-hosp-win--free');
            var title = el('h2', 'pets-window__title', 'Wolny inkubator');
            title.id = 'petsIncWinTitle';
            box.appendChild(title);
            var waiting = H.eggsToClaimCount(lastState);
            box.appendChild(el('p', 'pets-window__text', 'Nowe jajka odbierzesz na recepcji.' +
                (waiting ? ' Właśnie czeka tam ' + (waiting === 1 ? 'jedno jajko' : waiting + ' ' + u.plural(waiting, 'jajko', 'jajka', 'jajek')) + '!' : '')));
            var actions = el('div', 'pets-window__actions');
            var link = el('a', 'pet-btn' + (waiting ? ' pet-btn--primary' : ''));
            link.href = ctx.href('szpital');
            link.dataset.sceneLink = 'szpital';
            link.innerHTML = u.icon('back') + '<span class="pet-btn__label"></span>';
            link.querySelector('.pet-btn__label').textContent = 'Do recepcji';
            link.setAttribute('data-window-key', 'reception');
            actions.appendChild(link);
            box.appendChild(actions);
            refs = null;
            return box;
        }

        function freeSig() {
            return 'free|' + H.eggsToClaimCount(lastState);
        }

        function onWindowClosed() {
            open = null;
            openSig = null;
            refs = null;
            markSelected(null);
            if (ctx.isActive('inkubatorium')) ctx.setQuery({});
            layoutSides();
        }

        function show(content, returnFocus, focus) {
            win.open({
                content: content, labelledBy: 'petsIncWinTitle', returnFocus: returnFocus || null,
                onClose: onWindowClosed, closeLabel: 'Zamknij okno inkubatora', focus: focus
            });
            layoutSides();       // arkusz (< 1024 px) zmniejsza inkubatory, karta zwęża scenę
        }

        function openEgg(id, focus) {
            var egg = findEgg(lastState, id);
            var view = slotOf(id);
            if (!win || !egg || !view) return false;
            open = { type: 'egg', id: id };
            openSig = eggSig(egg);
            show(eggContent(egg), view.el, focus);
            markSelected(view);
            ctx.setQuery({ jajko: id });
            H.reveal(host, scroll, view.el);
            return true;
        }

        function openFree(slot) {
            var view = views[slot];
            if (!win || !view) return;
            open = { type: 'free', slot: slot };
            openSig = freeSig();
            show(freeContent(), view.el);
            markSelected(view);
            ctx.setQuery({});
            H.reveal(host, scroll, view.el);
        }

        function openSlot(i) {
            var id = slots[i];
            if (id != null) openEgg(id);
            else openFree(i);
        }

        /** Stan zmienił się przy otwartym oknie (odświeżenie, druga karta, własna akcja). */
        function refreshWindow(state) {
            if (!open || !win || !win.isOpen()) return;
            if (open.type === 'free') {
                var taken = slots[open.slot];
                if (taken != null) {
                    // Do wolnego inkubatora trafiło jajko (odebrane w innej karcie) — okno pokazuje to jajko
                    var egg0 = findEgg(state, taken);
                    open = { type: 'egg', id: taken };
                    openSig = eggSig(egg0);
                    win.replace(eggContent(egg0));
                    ctx.setQuery({ jajko: taken });
                } else if (freeSig() !== openSig) {
                    openSig = freeSig();
                    win.replace(freeContent());
                }
                return;
            }
            var egg = findEgg(state, open.id);
            if (!egg) {
                if (hatching === open.id) return;     // nakładka wyklucia jeszcze trwa — okno zamknie się po niej
                H.closeGone(win, host);
                return;
            }
            if (eggSig(egg) !== openSig) {
                openSig = eggSig(egg);
                win.replace(eggContent(egg));
            } else if (refs) {
                refs.egg = egg;
                fillEgg(refs);
            }
        }

        // --- akcje ------------------------------------------------------------------------------
        function flashLamp(id) {
            var view = slotOf(id);
            if (!view || u.reducedMotion()) return;
            view.el.classList.remove('is-warming');
            void view.el.offsetWidth;
            view.el.classList.add('is-warming');
            setTimeout(function () { view.el.classList.remove('is-warming'); }, 1000);
        }

        function warmEgg(btn) {
            var id = parseInt(btn.dataset.eggId, 10);
            u.setBusy(btn, true);
            H.warm(ctx, id).then(function () {
                flashLamp(id);
            }, function () {
                if (btn.isConnected) u.setBusy(btn, false);
            });
        }

        function hatchEgg(btn) {
            if (hatching != null) return;
            var id = parseInt(btn.dataset.eggId, 10);
            var egg = findEgg(lastState, id);
            if (!egg) return;
            hatching = id;
            u.setBusy(btn, true);
            H.hatch(ctx, egg).then(function (res) {
                hatching = null;
                // Nowy pupil mieszka w domku — tam z jego panelem (duplikat: pupil z nową gwiazdką)
                var target = res && (res.result === 'dupe' ? res.starred_pet_id : res.pet_id);
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                if (target && ctx.isActive('inkubatorium')) ctx.go('domek', { pupil: target });
                else if (lastState) render(lastState);
            }, function () {
                // Błąd pokazał ctx.send (toast), nakładka zamknęła się sama
                hatching = null;
                if (btn.isConnected) u.setBusy(btn, false);
                if (lastState) render(lastState);
            });
        }

        host.addEventListener('click', function (e) {
            var slot = e.target.closest('[data-inc-slot]');
            if (slot && host.contains(slot)) {
                openSlot(parseInt(slot.dataset.incSlot, 10));
                return;
            }
            var btn = e.target.closest('[data-inc-action]');
            if (!btn || !host.contains(btn) || btn.disabled || btn.getAttribute('aria-disabled') === 'true') return;
            if (btn.dataset.incAction === 'warm') warmEgg(btn);
            else if (btn.dataset.incAction === 'hatch') hatchEgg(btn);
        });

        // --- parametry z adresu (?jajko=ID) ------------------------------------------------------------
        function applyParams(params, state) {
            pending = null;
            var id = params && params.jajko;
            if (!id) {
                if (open && open.type === 'egg' && win && win.isOpen()) win.close({ restoreFocus: false });
                return;
            }
            if (!findEgg(state, id)) {
                // Wyklute, cudze albo nieistniejące: sala bez okna, adres bez parametru
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                ctx.setQuery({});
                return;
            }
            if (open && open.type === 'egg' && open.id === id && win.isOpen()) return;
            openEgg(id);
        }

        // --- render ----------------------------------------------------------------------------------
        function render(state) {
            lastState = state;
            slots = H.syncSlots(slots, (state.eggs || []).map(function (e) { return e.id; }), MIN_SLOTS, null);
            syncViews(state);
            row.style.setProperty('--n', String(slots.length));     // kolumn najwyżej tyle, ile miejsc (CSS)
            note.hidden = !(state.eggs_available || []).length;
            stage.classList.toggle('has-note', !note.hidden);
            syncWarm();
            updateBoard(state);
            layoutSides();
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
                hatching = null;
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                // Ukryta scena nie trzyma żywych rigów — render zbuduje je od nowa
                while (views.length) destroyView(views.pop());
                slots = [];
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
                views.forEach(function (v) { tickSlot(v, state); });
                syncWarm();
                if (refs && open && open.type === 'egg') fillEgg(refs);
            }
        };
    }

    W.scenes.inkubatorium = {
        title: 'Inkubatorium',
        create: create
    };
})();
