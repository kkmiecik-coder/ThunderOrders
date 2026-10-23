/**
 * Świat pupili — scena „szpital” = hol z recepcją (spec v3.1 §4.2).
 *
 * - Drzwi Inkubatorium (lewe, ciepłe światło w okienku) i Izby przyjęć (prawe, łóżko w okienku) to linki
 *   <a data-scene-link> z szyldami; znaczek z liczbą spraw (Inkubatorium: jajka gotowe do wyklucia; Izba:
 *   wyzdrowiali czekający na odbiór + chorzy w domku), brak spraw = brak znaczka.
 * - Recepcja pośrodku: pielęgniarka (własna postać SVG — okrągła, czepek z krzyżykiem; mruga), na ladzie
 *   jajko z kokardką na każdą pozycję `eggs_available`. Klik w jajko = okno sceny ze źródłem i „Odbierz”
 *   (POST /jajka/odbierz) → okno znika, jajko „odjeżdża” do drzwi Inkubatorium (≤ 0,8 s; ograniczony
 *   ruch: bez lotu), toast jak dawniej.
 * - Dymek pielęgniarki: jeden komunikat wg priorytetu (spec §4.2: jajka do odebrania → wyzdrowiały →
 *   jajko gotowe → chory w domku → odliczanie do miesięcznego → spokój); link do sali, gdy jej dotyczy.
 * - Układ: ≥ 600 px drzwi po bokach i recepcja pośrodku; < 600 px drzwi obok siebie u góry, recepcja
 *   pod nimi (CSS, zapytania kontenera na scenie właściwej).
 * - Zmiana stanu przy otwartym oknie: jajko nadal na ladzie → treść odświeżona; zniknęło (odebrane w innej
 *   karcie) → okno się zamyka, fokus wraca na scenę.
 * - Wystrój (.pets-hall__decor): okno z niebem i chmurkami (wieczór w ciemnym motywie, noc w grze = księżyc),
 *   lampy wiszące, plakaty, tablica ogłoszeń, dystrybutor wody, rośliny, ławka, dywan; wycieraczki w ramach
 *   drzwi. Same ozdoby (aria-hidden, pointer-events: none) pod drzwiami i recepcją; stałe znaczniki bez
 *   danych użytkownika. Układ wg wysokości sceny i ruch (z wyłączeniem w ograniczonym ruchu) — CSS.
 * Rejestruje się w window.PetsWorld.scenes.szpital.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.szpital) return;

    var FLY_MS = 700;
    var DESKTOP = '(min-width: 1024px)';

    // Pielęgniarka (spec v3.1 §4.2): okrągła głowa, czepek z krzyżykiem, rumieńce; dół chowa się za ladą
    var NURSE_SVG =
        '<svg class="pets-nurse" viewBox="0 0 140 120" aria-hidden="true" focusable="false">' +
        '<path class="nurse-uniform" d="M24 122C24 96 44 82 70 82S116 96 116 122Z"/>' +
        '<path class="nurse-collar" d="M56 84l14 13 14-13"/>' +
        '<path class="nurse-pocket" d="M86 104h14v10H86z"/>' +
        '<circle class="nurse-face" cx="70" cy="54" r="35"/>' +
        '<path class="nurse-hair" d="M35 56c0-22 15-35 35-35s35 13 35 35c-5-9-15-16-24-17-2 6-8 9-14 9s-10-3-12-8c-9 2-16 8-20 16z"/>' +
        '<path class="nurse-cap" d="M41 33c0-16 13-26 29-26s29 10 29 26c-8-4-18-6-29-6s-21 2-29 6z"/>' +
        '<path class="nurse-cross" d="M67 11h6v5h5v6h-5v5h-6v-5h-5v-6h5z"/>' +
        '<g class="nurse-eyes"><ellipse cx="57" cy="58" rx="3.8" ry="4.8"/><ellipse cx="83" cy="58" rx="3.8" ry="4.8"/>' +
        '<circle class="nurse-shine" cx="58.4" cy="56.4" r="1.3"/><circle class="nurse-shine" cx="84.4" cy="56.4" r="1.3"/></g>' +
        '<circle class="nurse-cheek" cx="47" cy="68" r="6"/><circle class="nurse-cheek" cx="93" cy="68" r="6"/>' +
        '<path class="nurse-mouth" d="M63 69q7 7 14 0"/>' +
        '</svg>';

    // Drzwi Inkubatorium: ciepłe światło i jajko w okienku
    var DOOR_INC_SVG =
        '<svg class="pets-hall__door-art" viewBox="0 0 100 170" aria-hidden="true" focusable="false">' +
        '<rect class="door-frame" x="1.5" y="1.5" width="97" height="168" rx="11"/>' +
        '<rect class="door-leaf" x="9" y="9" width="82" height="161" rx="7"/>' +
        '<rect class="door-window" x="20" y="20" width="60" height="50" rx="10"/>' +
        '<ellipse class="door-light" cx="50" cy="47" rx="24" ry="19"/>' +
        '<path class="door-egg" d="M50 31c6 0 10.5 9 10.5 15.5a10.5 10.5 0 0 1-21 0C39.5 40 44 31 50 31z"/>' +
        '<path class="door-egg-spot" d="M46 41a2.2 2.2 0 1 0 .1 0zM54 49a1.8 1.8 0 1 0 .1 0z"/>' +
        '<rect class="door-panel" x="20" y="86" width="60" height="64" rx="7"/>' +
        '<circle class="door-knob" cx="80" cy="104" r="4.6"/>' +
        '</svg>';

    // Drzwi Izby przyjęć: łóżko z pupilem w okienku, krzyżyk na drzwiach
    var DOOR_WARD_SVG =
        '<svg class="pets-hall__door-art" viewBox="0 0 100 170" aria-hidden="true" focusable="false">' +
        '<rect class="door-frame" x="1.5" y="1.5" width="97" height="168" rx="11"/>' +
        '<rect class="door-leaf" x="9" y="9" width="82" height="161" rx="7"/>' +
        '<rect class="door-window" x="20" y="20" width="60" height="50" rx="10"/>' +
        '<rect class="door-bedpost" x="26" y="40" width="5" height="22" rx="2.5"/>' +
        '<circle class="door-pet" cx="40" cy="46" r="7"/>' +
        '<rect class="door-quilt" x="35" y="48" width="38" height="10" rx="4"/>' +
        '<rect class="door-bed" x="27" y="57" width="48" height="5" rx="2.5"/>' +
        '<rect class="door-panel" x="20" y="86" width="60" height="64" rx="7"/>' +
        '<path class="door-cross" d="M46 103h8v8h8v8h-8v8h-8v-8h-8v-8h8z"/>' +
        '<circle class="door-knob" cx="20" cy="104" r="4.6"/>' +
        '</svg>';

    var CLOCK_SVG =
        '<svg viewBox="0 0 60 60" aria-hidden="true" focusable="false">' +
        '<circle class="clock-face" cx="30" cy="30" r="26"/>' +
        '<g class="clock-ticks"><path d="M30 8v5M30 47v5M8 30h5M47 30h5"/></g>' +
        '<path class="clock-hand clock-hand--h" d="M30 30V18"/>' +
        '<path class="clock-hand clock-hand--m" d="M30 30V12"/>' +
        '<circle class="clock-pin" cx="30" cy="30" r="2.6"/>' +
        '</svg>';

    var BELL_SVG =
        '<svg class="pets-hall__bell" viewBox="0 0 32 24" aria-hidden="true" focusable="false">' +
        '<path class="bell-dome" d="M5 19a11 11 0 0 1 22 0z"/><circle class="bell-knob" cx="16" cy="6.5" r="2.4"/>' +
        '<rect class="bell-base" x="2" y="19" width="28" height="4" rx="2"/></svg>';

    // Kokardka na jajku do odebrania (kolor wg źródła — klasa .pets-gift--<source>)
    var BOW_SVG =
        '<svg class="pets-gift__bow" viewBox="0 0 48 28" aria-hidden="true" focusable="false">' +
        '<path class="bow-loop" d="M24 14C16 2 4 2 4 10s12 8 20 4z"/><path class="bow-loop" d="M24 14c8-12 20-12 20-4s-12 8-20 4z"/>' +
        '<path class="bow-tail" d="M24 14l-8 13h4l4-8 4 8h4z"/><circle class="bow-knot" cx="24" cy="14" r="4.5"/></svg>';

    var ARROW_SVG =
        '<svg class="pets-hall__talk-arrow" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" ' +
        'stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg>';

    // --- wystrój holu (same ozdoby: aria-hidden, bez zdarzeń; układ i ruch w pets-hospital-hall.css) -------
    var NS = ' aria-hidden="true" focusable="false"';

    // Lampa wisząca: sznur (wysokość z CSS) + klosz; poświata w ciemnym motywie i nocą
    var LAMP_HTML =
        '<span class="pets-hall__lamp-cord"></span>' +
        '<svg class="pets-hall__lamp-shade" viewBox="0 0 64 46"' + NS + '>' +
        '<rect class="hall-lamp-cap" x="26" y="0" width="12" height="8" rx="2"/>' +
        '<path class="hall-lamp-shade" d="M32 6C17 6 7 18 5 33h54C57 18 47 6 32 6z"/>' +
        '<path class="hall-lamp-shine" d="M19 15c-4 4-6 9-7 14"/>' +
        '<path class="hall-lamp-bulb" d="M24 36h16a8 8 0 0 1-16 0z"/>' +
        '<rect class="hall-lamp-rim" x="2" y="31" width="60" height="6" rx="3"/>' +
        '</svg>' +
        '<span class="pets-hall__lamp-glow"></span>';

    // Kafel chmur (dwa identyczne obok siebie = płynna pętla przesuwu)
    var CLOUD_TILE =
        '<svg class="pets-hall__cloud-tile" viewBox="0 0 200 120" preserveAspectRatio="xMidYMin meet"' + NS + '>' +
        '<g class="hall-cloud"><circle cx="34" cy="38" r="10"/><circle cx="48" cy="31" r="13"/><circle cx="62" cy="39" r="9"/>' +
        '<rect x="25" y="38" width="46" height="11" rx="5.5"/></g>' +
        '<g class="hall-cloud hall-cloud--far"><circle cx="120" cy="20" r="6"/><circle cx="129" cy="15" r="8"/><circle cx="138" cy="20" r="6"/>' +
        '<rect x="114" y="19" width="30" height="7" rx="3.5"/></g>' +
        '<g class="hall-cloud"><circle cx="146" cy="64" r="8"/><circle cx="158" cy="58" r="11"/><circle cx="170" cy="65" r="7.5"/>' +
        '<rect x="139" y="63" width="38" height="9" rx="4.5"/></g>' +
        '</svg>';

    // Okno z niebem: dzień (słońce, chmurki), wieczór w ciemnym motywie i noc w grze (księżyc, gwiazdy)
    var WINDOW_HTML =
        '<div class="pets-hall__window">' +
        '<div class="pets-hall__sky">' +
        '<span class="pets-hall__sun"></span>' +
        '<svg class="pets-hall__night" viewBox="0 0 200 120" preserveAspectRatio="xMidYMin meet"' + NS + '>' +
        '<path class="hall-moon" d="M158 16a15 15 0 1 0 15 21a12 12 0 1 1-15-21z"/>' +
        '<g class="hall-stars hall-stars--a"><circle cx="28" cy="18" r="1.7"/><circle cx="74" cy="10" r="1.3"/>' +
        '<circle cx="112" cy="30" r="1.6"/><circle cx="186" cy="64" r="1.3"/><circle cx="58" cy="50" r="1.1"/></g>' +
        '<g class="hall-stars hall-stars--b"><circle cx="46" cy="34" r="1.3"/><circle cx="96" cy="12" r="1.7"/>' +
        '<circle cx="132" cy="54" r="1.2"/><circle cx="14" cy="52" r="1.4"/><circle cx="138" cy="8" r="1.1"/></g>' +
        '</svg>' +
        '<div class="pets-hall__clouds">' + CLOUD_TILE + CLOUD_TILE + '</div>' +
        '<svg class="pets-hall__hills" viewBox="0 0 200 52" preserveAspectRatio="xMidYMax meet"' + NS + '>' +
        '<path class="hall-hill hall-hill--back" d="M0 32C28 16 58 16 90 28S152 10 200 24V52H0z"/>' +
        '<rect class="hall-trunk" x="149" y="22" width="4" height="12" rx="2"/>' +
        '<circle class="hall-tree" cx="151" cy="19" r="9"/><circle class="hall-tree hall-tree--small" cx="38" cy="26" r="6"/>' +
        '<rect class="hall-trunk" x="36.5" y="27" width="3" height="8" rx="1.5"/>' +
        '<path class="hall-hill hall-hill--front" d="M0 42C40 30 82 32 120 42S182 36 200 38V52H0z"/>' +
        '</svg>' +
        '</div>' +
        '<span class="pets-hall__panes"></span>' +
        '<span class="pets-hall__sill"></span>' +
        '<svg class="pets-hall__sill-pot" viewBox="0 0 40 48"' + NS + '>' +
        '<path class="hall-cactus" d="M20 8c6 0 9 6 9 14v10H11V22c0-8 3-14 9-14z"/>' +
        '<path class="hall-cactus-line" d="M20 12v18M15 16v14M25 16v14"/>' +
        '<circle class="hall-cactus-flower" cx="20" cy="8" r="4"/><circle class="hall-flower-c" cx="20" cy="8" r="1.6"/>' +
        '<path class="hall-pot hall-pot--sill" d="M8 31h24l-3 15H11z"/><rect class="hall-pot-rim hall-pot-rim--sill" x="6" y="29" width="28" height="5" rx="2.5"/>' +
        '</svg>' +
        '</div>';

    // Plakaty o zdrowiu pupili (taśma u góry, krótkie hasło)
    var POSTERS_HTML =
        '<div class="pets-hall__posters">' +
        '<svg class="pets-hall__poster pets-hall__poster--paw" viewBox="0 0 80 100"' + NS + '>' +
        '<rect class="hall-poster-paper" x="2" y="2" width="76" height="96" rx="6"/>' +
        '<rect class="hall-poster-bg hall-poster-bg--pink" x="8" y="8" width="64" height="62" rx="4"/>' +
        '<ellipse class="hall-paw" cx="40" cy="49" rx="12.5" ry="10.5"/>' +
        '<ellipse class="hall-paw" cx="25" cy="35" rx="4.8" ry="6" transform="rotate(-22 25 35)"/>' +
        '<ellipse class="hall-paw" cx="34.5" cy="27" rx="4.8" ry="6" transform="rotate(-7 34.5 27)"/>' +
        '<ellipse class="hall-paw" cx="45.5" cy="27" rx="4.8" ry="6" transform="rotate(7 45.5 27)"/>' +
        '<ellipse class="hall-paw" cx="55" cy="35" rx="4.8" ry="6" transform="rotate(22 55 35)"/>' +
        '<circle class="hall-soap" cx="60" cy="58" r="5"/><circle class="hall-soap" cx="18" cy="58" r="3.6"/>' +
        '<circle class="hall-soap" cx="63" cy="18" r="3.2"/><circle class="hall-soap" cx="16" cy="18" r="2.4"/>' +
        '<text class="hall-poster-text hall-poster-text--pink" x="40" y="87" text-anchor="middle" textLength="58" ' +
        'lengthAdjust="spacingAndGlyphs">MYJ ŁAPKI!</text>' +
        '<rect class="hall-tape" x="29" y="-2" width="22" height="9" rx="1.5" transform="rotate(-5 40 2)"/>' +
        '</svg>' +
        '<svg class="pets-hall__poster pets-hall__poster--food" viewBox="0 0 80 100"' + NS + '>' +
        '<rect class="hall-poster-paper" x="2" y="2" width="76" height="96" rx="6"/>' +
        '<rect class="hall-poster-bg hall-poster-bg--mint" x="8" y="8" width="64" height="62" rx="4"/>' +
        '<circle class="hall-apple" cx="27" cy="46" r="12"/>' +
        '<path class="hall-apple-stem" d="M27 34c0-4 1-7 3-9"/>' +
        '<path class="hall-food-leaf" d="M30 30c3-4 8-5 11-3-3 4-7 5-11 3z"/>' +
        '<path class="hall-carrot" d="M40 62c-2 1-4-1-3-3l12-26c2-4 8-5 11-1s1 8-2 10z"/>' +
        '<path class="hall-carrot-line" d="M46 44l4 2M43 51l4 2M50 37l3 2"/>' +
        '<path class="hall-food-leaf" d="M58 30c0-6 2-11 7-13 0 6-2 10-7 13zM60 33c4-4 9-5 13-3-4 4-8 5-13 3z"/>' +
        '<text class="hall-poster-text hall-poster-text--mint" x="40" y="87" text-anchor="middle" textLength="58" ' +
        'lengthAdjust="spacingAndGlyphs">WITAMINKI</text>' +
        '<rect class="hall-tape" x="29" y="-2" width="22" height="9" rx="1.5" transform="rotate(4 40 2)"/>' +
        '</svg>' +
        '</div>';

    // Tablica ogłoszeń: karteczki, zdjęcie pupila, serduszko, pinezki; pod nią (wysoka scena) plakat o śnie
    var BOARD_HTML =
        '<div class="pets-hall__board">' +
        '<svg class="pets-hall__board-art" viewBox="0 0 160 120"' + NS + '>' +
        '<rect class="hall-board-frame" x="2" y="2" width="156" height="116" rx="10"/>' +
        '<rect class="hall-board-cork" x="10" y="10" width="140" height="100" rx="5"/>' +
        '<g transform="rotate(-5 40 40)"><rect class="hall-note hall-note--yellow" x="18" y="18" width="44" height="42" rx="3"/>' +
        '<path class="hall-note-line" d="M24 32h30M24 40h25M24 48h30"/></g>' +
        '<g transform="rotate(6 100 44)"><rect class="hall-photo" x="76" y="16" width="48" height="56" rx="3"/>' +
        '<rect class="hall-photo-pic" x="81" y="21" width="38" height="36" rx="2"/>' +
        '<path class="hall-photo-pet" d="M90 36l-3-8 7 4zM110 36l3-8-7 4z"/><circle class="hall-photo-pet" cx="100" cy="44" r="11"/>' +
        '<circle class="hall-photo-eye" cx="96" cy="43" r="1.6"/><circle class="hall-photo-eye" cx="104" cy="43" r="1.6"/>' +
        '<path class="hall-photo-mouth" d="M98 48q2 2 4 0"/></g>' +
        '<g transform="rotate(4 45 88)"><rect class="hall-note hall-note--pink" x="22" y="70" width="46" height="32" rx="3"/>' +
        '<path class="hall-note-heart" d="M45 96c-7-5-10-8-10-12a4.5 4.5 0 0 1 10-2.4a4.5 4.5 0 0 1 10 2.4c0 4-3 7-10 12z"/></g>' +
        '<g transform="rotate(-6 118 91)"><rect class="hall-note hall-note--blue" x="97" y="78" width="42" height="28" rx="3"/>' +
        '<path class="hall-note-cross" d="M115 84h6v5h5v6h-5v5h-6v-5h-5v-6h5z"/></g>' +
        '<circle class="hall-pin hall-pin--a" cx="40" cy="20" r="3.6"/><circle class="hall-pin hall-pin--b" cx="100" cy="18" r="3.6"/>' +
        '<circle class="hall-pin hall-pin--c" cx="45" cy="72" r="3.4"/><circle class="hall-pin hall-pin--a" cx="118" cy="80" r="3.4"/>' +
        '</svg>' +
        '<svg class="pets-hall__poster pets-hall__poster--sleep" viewBox="0 0 80 100"' + NS + '>' +
        '<rect class="hall-poster-paper" x="2" y="2" width="76" height="96" rx="6"/>' +
        '<rect class="hall-poster-bg hall-poster-bg--lilac" x="8" y="8" width="64" height="62" rx="4"/>' +
        '<path class="hall-poster-moon" d="M34 20a19 19 0 1 0 24 27a15 15 0 1 1-24-27z"/>' +
        '<path class="hall-zz" d="M50 16h8l-8 9h8M61 29h6l-6 7h6"/>' +
        '<circle class="hall-poster-star" cx="18" cy="20" r="1.9"/><circle class="hall-poster-star" cx="63" cy="60" r="1.6"/>' +
        '<circle class="hall-poster-star" cx="16" cy="58" r="1.4"/>' +
        '<text class="hall-poster-text hall-poster-text--lilac" x="40" y="87" text-anchor="middle" textLength="60" ' +
        'lengthAdjust="spacingAndGlyphs">ŚPIJ ZDROWO</text>' +
        '<rect class="hall-tape" x="29" y="-2" width="22" height="9" rx="1.5" transform="rotate(-3 40 2)"/>' +
        '</svg>' +
        '</div>';

    // Dystrybutor wody: bąbelki w baniaku, mrugająca lampka
    var COOLER_HTML =
        '<div class="pets-hall__cooler">' +
        '<svg viewBox="0 0 70 160"' + NS + '>' +
        '<rect class="hall-cooler-cap" x="27" y="2" width="16" height="8" rx="2.5"/>' +
        '<path class="hall-cooler-bottle" d="M24 9h22v5c9 2 14 8 14 17v27c0 6-4 10-10 10H20c-6 0-10-4-10-10V31c0-9 5-15 14-17z"/>' +
        '<path class="hall-cooler-water" d="M10.5 36h49v22c0 5.5-4 9.5-9.5 9.5H20c-5.5 0-9.5-4-9.5-9.5z"/>' +
        '<path class="hall-cooler-shine" d="M17 32v22"/>' +
        '<circle class="hall-bubble hall-bubble--1" cx="27" cy="62" r="2.3"/><circle class="hall-bubble hall-bubble--2" cx="43" cy="63" r="1.7"/>' +
        '<circle class="hall-bubble hall-bubble--3" cx="35" cy="64" r="1.9"/>' +
        '<rect class="hall-cooler-neck" x="23" y="66" width="24" height="7" rx="2"/>' +
        '<rect class="hall-cooler-body" x="6" y="71" width="58" height="84" rx="9"/>' +
        '<rect class="hall-cooler-panel" x="14" y="81" width="42" height="33" rx="6"/>' +
        '<rect class="hall-tap hall-tap--cold" x="19" y="91" width="9" height="12" rx="2.5"/>' +
        '<rect class="hall-tap hall-tap--hot" x="42" y="91" width="9" height="12" rx="2.5"/>' +
        '<circle class="hall-cooler-led" cx="35" cy="88" r="2.6"/>' +
        '<path class="hall-cooler-cup" d="M30 104h10l-1.5 9h-7z"/>' +
        '<rect class="hall-cooler-tray" x="16" y="113" width="38" height="5" rx="2.5"/>' +
        '<rect class="hall-cooler-foot" x="10" y="153" width="50" height="6" rx="3"/>' +
        '</svg>' +
        '</div>';

    // Roślina w donicy (wysoka) i krzaczek z kwiatkami (niska) — liście się kołyszą
    var PLANT_TALL_HTML =
        '<div class="pets-hall__plant pets-hall__plant--tall">' +
        '<svg viewBox="0 0 100 170"' + NS + '>' +
        '<g class="hall-sway">' +
        '<path class="hall-stem" d="M50 120C48 98 40 80 28 62M50 120c0-28 6-50 20-70M50 120c0-22-2-42-4-62M50 120c2-16 12-28 28-36M50 120c-4-10-9-18-16-24"/>' +
        '<path class="hall-leaf" d="M28 62Q6 52 8 30Q30 36 28 62z"/>' +
        '<path class="hall-leaf hall-leaf--light" d="M70 50Q72 26 96 22Q92 48 70 50z"/>' +
        '<path class="hall-leaf" d="M46 58Q30 34 46 8Q62 34 46 58z"/>' +
        '<path class="hall-leaf hall-leaf--light" d="M78 84Q82 62 98 60Q96 82 78 84z"/>' +
        '<path class="hall-leaf hall-leaf--light" d="M34 96Q18 82 4 88Q16 104 34 96z"/>' +
        '<path class="hall-vein" d="M27 60L11 33M71 48L93 25M46 55V12M79 82L96 62M32 95L8 89"/>' +
        '</g>' +
        '<rect class="hall-pot-rim" x="22" y="116" width="56" height="12" rx="5"/>' +
        '<path class="hall-pot" d="M26 126h48l-6 41H32z"/>' +
        '<path class="hall-pot-band" d="M28 142h44"/>' +
        '</svg>' +
        '</div>';

    var PLANT_SMALL_HTML =
        '<div class="pets-hall__plant pets-hall__plant--small">' +
        '<svg viewBox="0 0 80 100"' + NS + '>' +
        '<g class="hall-sway hall-sway--b">' +
        '<circle class="hall-bush" cx="27" cy="46" r="16"/><circle class="hall-bush" cx="53" cy="45" r="17"/>' +
        '<circle class="hall-bush hall-bush--light" cx="40" cy="30" r="19"/>' +
        '<circle class="hall-flower" cx="30" cy="28" r="3.6"/><circle class="hall-flower" cx="50" cy="22" r="3.6"/>' +
        '<circle class="hall-flower" cx="58" cy="44" r="3.6"/><circle class="hall-flower" cx="22" cy="46" r="3.2"/>' +
        '<circle class="hall-flower" cx="41" cy="40" r="3.2"/>' +
        '<circle class="hall-flower-c" cx="30" cy="28" r="1.4"/><circle class="hall-flower-c" cx="50" cy="22" r="1.4"/>' +
        '<circle class="hall-flower-c" cx="58" cy="44" r="1.4"/><circle class="hall-flower-c" cx="22" cy="46" r="1.2"/>' +
        '<circle class="hall-flower-c" cx="41" cy="40" r="1.2"/>' +
        '</g>' +
        '<path class="hall-pot hall-pot--round" d="M17 60h46l-5 33c0 3-3 5-6 5H28c-3 0-6-2-6-5z"/>' +
        '<rect class="hall-pot-rim hall-pot-rim--round" x="13" y="55" width="54" height="10" rx="5"/>' +
        '</svg>' +
        '</div>';

    // Ławka poczekalni z poduszką-serduszkiem
    var BENCH_HTML =
        '<div class="pets-hall__bench">' +
        '<svg viewBox="0 0 200 100"' + NS + '>' +
        '<rect class="hall-bench-leg" x="24" y="58" width="9" height="38" rx="3"/>' +
        '<rect class="hall-bench-leg" x="167" y="58" width="9" height="38" rx="3"/>' +
        '<rect class="hall-bench-back" x="14" y="8" width="172" height="40" rx="14"/>' +
        '<path class="hall-bench-tuft" d="M72 28h0M100 28h0M128 28h0M156 28h0"/>' +
        '<rect class="hall-bench-seat" x="6" y="44" width="188" height="20" rx="10"/>' +
        '<path class="hall-bench-seam" d="M100 47v14"/>' +
        '<path class="hall-pillow" d="M42 47c-12-8-18-14-18-21a9 9 0 0 1 18-3a9 9 0 0 1 18 3c0 7-6 13-18 21z"/>' +
        '</svg>' +
        '</div>';

    var DECOR_HTML =
        '<span class="pets-hall__rug"></span>' +
        WINDOW_HTML + POSTERS_HTML + BOARD_HTML +
        '<span class="pets-hall__lamp pets-hall__lamp--l">' + LAMP_HTML + '</span>' +
        '<span class="pets-hall__lamp pets-hall__lamp--r">' + LAMP_HTML + '</span>' +
        COOLER_HTML + PLANT_TALL_HTML + PLANT_SMALL_HTML + BENCH_HTML;

    function create(ctx, host) {
        var H = window.PetsHospital;
        var u = ctx.u;
        var el = u.el;
        var R = function () { return window.PetRig; };

        var lastState = null;
        var eggViews = {};           // klucz pozycji eggs_available → widok jajka na ladzie
        var eggOrder = [];
        var claiming = null;         // {key} — jajko w trakcie odbioru zostaje na ladzie do startu lotu
        var openKey = null;          // klucz jajka w otwartym oknie
        var openSig = null;
        var winRigs = [];
        var flight = null;
        var talkSig = null;
        var lift = 0;

        // --- szkielet -------------------------------------------------------------------------
        var stage = el('div', 'pets-stage pets-hall');
        stage.setAttribute('data-window-backdrop', '');
        var floor = el('div', 'pets-hall__floor');
        floor.setAttribute('aria-hidden', 'true');
        var clock = el('div', 'pets-hall__clock');
        clock.setAttribute('aria-hidden', 'true');
        clock.innerHTML = CLOCK_SVG;
        var handH = clock.querySelector('.clock-hand--h');
        var handM = clock.querySelector('.clock-hand--m');

        function makeDoor(scene, label, art, iconName, mod) {
            var a = el('a', 'pets-hall__door pets-hall__door--' + mod);
            a.href = ctx.href(scene);
            a.dataset.sceneLink = scene;
            var sign = el('span', 'pets-hall__sign');
            sign.innerHTML = u.icon(iconName, 'pets-hall__sign-icon');
            sign.appendChild(el('span', 'pets-hall__sign-text', label));
            var frame = el('span', 'pets-hall__frame');
            frame.innerHTML = art;
            // Wycieraczka pod skrzydłem (ozdoba; w ramie, żeby trzymała się drzwi także przy szerszym szyldzie)
            var mat = el('span', 'pets-hall__mat');
            mat.setAttribute('aria-hidden', 'true');
            frame.appendChild(mat);
            var badge = el('span', 'pets-hall__badge');
            badge.setAttribute('aria-hidden', 'true');
            badge.hidden = true;
            frame.appendChild(badge);
            a.appendChild(sign);
            a.appendChild(frame);
            a.setAttribute('aria-label', label);
            return { a: a, frame: frame, badge: badge, label: label };
        }

        var doorInc = makeDoor('inkubatorium', 'Inkubatorium', DOOR_INC_SVG, 'egg', 'inc');
        var doorWard = makeDoor('izba', 'Izba przyjęć', DOOR_WARD_SVG, 'cross', 'ward');

        var desk = el('div', 'pets-hall__desk');
        var talk = el('div', 'pets-hall__talk');
        var nurse = el('div', 'pets-hall__nurse');
        nurse.setAttribute('aria-hidden', 'true');
        nurse.innerHTML = NURSE_SVG;
        var counter = el('div', 'pets-hall__counter');
        var eggsBox = el('div', 'pets-hall__eggs');
        var top = el('div', 'pets-hall__counter-top');
        top.setAttribute('aria-hidden', 'true');
        top.innerHTML = BELL_SVG;
        var front = el('div', 'pets-hall__counter-front');
        front.setAttribute('aria-hidden', 'true');
        front.appendChild(el('span', 'pets-hall__counter-sign', 'Recepcja'));
        counter.appendChild(eggsBox);
        counter.appendChild(top);
        counter.appendChild(front);
        desk.appendChild(talk);
        desk.appendChild(nurse);
        desk.appendChild(counter);

        // Wystrój (okno z niebem, lampy, plakaty, tablica, rośliny, ławka, dystrybutor, dywan) — pod drzwiami
        // i recepcją, bez zdarzeń: klik w ozdobę = klik w tło sceny (zamyka okno sceny jak dotąd)
        var decor = el('div', 'pets-hall__decor');
        decor.setAttribute('aria-hidden', 'true');
        decor.innerHTML = DECOR_HTML;

        [floor, decor, clock, doorInc.a, doorWard.a, desk].forEach(function (n) { stage.appendChild(n); });
        host.appendChild(stage);

        var win = window.PetsSceneWindow ? window.PetsSceneWindow.attach(host) : null;

        function isDesktop() {
            return !!(window.matchMedia && window.matchMedia(DESKTOP).matches);
        }

        // --- drzwi: znaczki ------------------------------------------------------------------------
        function setDoor(door, count, detail) {
            door.badge.hidden = !count;
            var text = count > 9 ? '9+' : String(count);
            if (door.badge.textContent !== text) door.badge.textContent = text;
            door.a.classList.toggle('has-badge', count > 0);
            var label = door.label + (detail ? ' — ' + detail : '');
            if (door.a.getAttribute('aria-label') !== label) door.a.setAttribute('aria-label', label);
        }

        function renderDoors(state) {
            var ready = H.readyEggs(state).length;
            setDoor(doorInc, ready, ready ? 'gotowe do wyklucia: ' + ready : '');
            var healed = H.healedPets(state).length;
            var sick = H.sickAtHome(state).length;
            var parts = [];
            if (healed) parts.push('czeka na odbiór: ' + healed);
            if (sick) parts.push('chorzy w domku: ' + sick);
            setDoor(doorWard, healed + sick, parts.join(', '));
        }

        // --- dymek pielęgniarki (spec v3.1 §4.2: jeden komunikat wg priorytetu) ----------------------
        function monthlyText(state) {
            var left = state.next_monthly_at ? u.secondsUntil(state.next_monthly_at) : NaN;
            if (!(left > 0)) return '';
            // Jak w widgecie dashboardu: pełne dni, poniżej doby godziny
            var hours = Math.max(1, Math.ceil(left / 3600));
            var days = Math.floor(hours / 24);
            return 'Nowe jajko za ' + (days >= 1 ? u.daysText(days) : '~' + hours + ' h') + '.';
        }

        function talkFor(state) {
            var n = H.eggsToClaimCount(state);
            if (n) return { text: n === 1 ? 'Mam dla Ciebie jajko! Leży na ladzie.' : 'Mam dla Ciebie jajka (' + n + ')! Leżą na ladzie.' };
            var healed = H.healedPets(state);
            if (healed.length) {
                var names = healed.map(function (p) { return H.petName(p, u); });
                return {
                    text: healed.length === 1 ? names[0] + ' już zdrowy — czeka w izbie przyjęć.'
                        : healed.length === 2 ? names[0] + ' i ' + names[1] + ' już zdrowi — czekają w izbie przyjęć.'
                        : 'Wyzdrowiałych pupili: ' + healed.length + ' — czekają w izbie przyjęć.',
                    scene: 'izba',
                    params: healed.length === 1 ? { pupil: healed[0].id } : {}
                };
            }
            var ready = H.readyEggs(state);
            if (ready.length) {
                return {
                    text: ready.length === 1 ? 'Jajko jest gotowe do wyklucia — zajrzyj do Inkubatorium!'
                        : 'Jajek gotowych do wyklucia: ' + ready.length + ' — zajrzyj do Inkubatorium!',
                    scene: 'inkubatorium',
                    params: ready.length === 1 ? { jajko: ready[0].id } : {}
                };
            }
            var sick = H.sickAtHome(state);
            if (sick.length) {
                var sickNames = sick.map(function (p) { return H.petName(p, u); });
                return {
                    text: sick.length === 1 ? sickNames[0] + ' źle się czuje — przyjmij go w izbie przyjęć.'
                        : sick.length === 2 ? sickNames[0] + ' i ' + sickNames[1] + ' źle się czują — przyjmij je w izbie przyjęć.'
                        : 'Chorych pupili w domku: ' + sick.length + ' — przyjmij je w izbie przyjęć.',
                    scene: 'izba',
                    params: {}
                };
            }
            var monthly = monthlyText(state);
            if (monthly) return { text: monthly };
            return { text: 'Wszyscy zdrowi!' };
        }

        function renderTalk(state) {
            var t = talkFor(state);
            var sig = t.scene ? t.scene + '|' + (t.params.pupil || '') + '|' + (t.params.jajko || '') : 'text';
            var bubble = talk.firstChild;
            if (sig !== talkSig || !bubble) {
                talkSig = sig;
                talk.innerHTML = '';
                if (t.scene) {
                    bubble = el('a', 'pets-hall__talk-bubble is-link');
                    bubble.href = ctx.href(t.scene, t.params);
                    bubble.dataset.sceneLink = t.scene;
                    if (t.params.pupil) bubble.dataset.pupil = String(t.params.pupil);
                    if (t.params.jajko) bubble.dataset.jajko = String(t.params.jajko);
                    bubble.appendChild(el('span', 'pets-hall__talk-text'));
                    bubble.insertAdjacentHTML('beforeend', ARROW_SVG);
                } else {
                    bubble = el('p', 'pets-hall__talk-bubble');
                    bubble.appendChild(el('span', 'pets-hall__talk-text'));
                }
                talk.appendChild(bubble);
            }
            var textEl = bubble.querySelector('.pets-hall__talk-text');
            if (textEl.textContent !== t.text) textEl.textContent = t.text;
            nurse.classList.toggle('is-calling', H.eggsToClaimCount(state) > 0);
        }

        // --- zegar na ścianie (czas serwera po polsku) --------------------------------------------------
        function renderClock() {
            var d = u.plParts(u.serverNow());
            var m = d.minute;
            var h = d.hour % 12 + m / 60;
            handH.setAttribute('transform', 'rotate(' + (h * 30).toFixed(1) + ' 30 30)');
            handM.setAttribute('transform', 'rotate(' + (m * 6) + ' 30 30)');
        }

        // --- jajka na ladzie ---------------------------------------------------------------------------
        function findClaim(state, key) {
            var list = (state && state.eggs_available) || [];
            for (var i = 0; i < list.length; i++) if (H.claimKey(list[i]) === key) return list[i];
            return null;
        }

        function giftArt(item, cls) {
            var art = el('span', 'pets-gift pets-gift--' + item.source + (cls ? ' ' + cls : ''));
            var rig = R() ? R().mountEgg(art, { pct: 0, size: 'mini' }) : null;
            art.insertAdjacentHTML('beforeend', BOW_SVG);
            return { el: art, rig: rig };
        }

        function eggView(item) {
            var key = H.claimKey(item);
            var btn = el('button', 'pets-hall__egg');
            btn.type = 'button';
            btn.dataset.hallEgg = key;
            var art = giftArt(item);
            var count = el('span', 'pets-hall__egg-count');
            count.setAttribute('aria-hidden', 'true');
            btn.appendChild(art.el);
            btn.appendChild(count);
            var view = { key: key, el: btn, rig: art.rig, count: count, item: null };
            updateEggView(view, item);
            return view;
        }

        function updateEggView(view, item) {
            view.item = item;
            var n = item.source === 'granted' ? H.grantedCount(item) : 1;
            view.count.hidden = n < 2;
            view.count.textContent = '×' + n;
            var label = H.claimLabel(item);
            if (view.el.getAttribute('aria-label') !== label) view.el.setAttribute('aria-label', label);
        }

        function dropEggView(key) {
            var view = eggViews[key];
            if (!view) return;
            if (view.rig) view.rig.destroy();
            if (view.el.parentNode) view.el.parentNode.removeChild(view.el);
            delete eggViews[key];
        }

        function syncEggs(state) {
            var list = ((state && state.eggs_available) || []).slice();
            var keys = list.map(H.claimKey);
            // Jajko w trakcie odbioru zostaje na swoim miejscu, dopóki nie wystartuje lot do drzwi
            if (claiming && keys.indexOf(claiming.key) < 0 && eggViews[claiming.key]) {
                var at = Math.min(eggOrder.indexOf(claiming.key), list.length);
                list.splice(at < 0 ? list.length : at, 0, eggViews[claiming.key].item);
                keys.splice(at < 0 ? keys.length : at, 0, claiming.key);
            }
            list.forEach(function (item, i) {
                var key = keys[i];
                var view = eggViews[key];
                if (view) updateEggView(view, item);
                else view = eggViews[key] = eggView(item);
                if (eggsBox.children[i] !== view.el) eggsBox.insertBefore(view.el, eggsBox.children[i] || null);
            });
            Object.keys(eggViews).forEach(function (key) { if (keys.indexOf(key) < 0) dropEggView(key); });
            eggOrder = keys;
            counter.classList.toggle('has-eggs', keys.length > 0);
        }

        // --- okno jajka --------------------------------------------------------------------------------
        function dropWinRigs() {
            winRigs.forEach(function (r) { if (r) r.destroy(); });
            winRigs = [];
        }

        function claimSig(item) {
            return [H.claimKey(item), item.count, item.pet_name].join('|');
        }

        function claimContent(item) {
            var box = el('div', 'pets-hosp-win pets-hosp-win--claim');
            var hero = el('div', 'pets-hosp-win__hero');
            var art = giftArt(item, 'pets-hosp-win__gift');
            winRigs.push(art.rig);
            hero.appendChild(art.el);
            var head = el('div', 'pets-hosp-win__head');
            var title = el('h2', 'pets-window__title', H.claimTitle(item));
            title.id = 'petsHallWinTitle';
            head.appendChild(title);
            head.appendChild(el('p', 'pets-window__text', H.claimText(item, u)));
            hero.appendChild(head);
            box.appendChild(hero);
            var actions = el('div', 'pets-window__actions');
            var btn = u.button('Odbierz', 'egg', 'primary', { hallAction: 'claim', key: H.claimKey(item) });
            btn.setAttribute('data-window-key', 'claim');
            actions.appendChild(btn);
            box.appendChild(actions);
            return box;
        }

        function markSelected(key) {
            Object.keys(eggViews).forEach(function (k) { eggViews[k].el.classList.toggle('is-selected', k === key); });
        }

        function onWindowClosed() {
            openKey = null;
            openSig = null;
            dropWinRigs();
            markSelected(null);
            setLift(0);
        }

        function openClaim(key, returnFocus) {
            var item = findClaim(lastState, key);
            if (!win || !item || claiming) return;
            var old = winRigs;
            winRigs = [];
            openKey = key;
            openSig = claimSig(item);
            win.open({
                content: claimContent(item), labelledBy: 'petsHallWinTitle', returnFocus: returnFocus || null,
                onClose: onWindowClosed, closeLabel: 'Zamknij okno jajka'
            });
            old.forEach(function (r) { if (r) r.destroy(); });
            markSelected(key);
            liftFor(returnFocus);
        }

        function replaceClaim(item) {
            var old = winRigs;
            winRigs = [];
            openSig = claimSig(item);
            win.replace(claimContent(item));
            old.forEach(function (r) { if (r) r.destroy(); });
        }

        // Arkusz (< 1024 px): „kamera” — hol jedzie w górę tak, żeby wybrane jajko zostało widoczne nad arkuszem,
        // ale górna krawędź drzwi (z szyldem i znaczkiem) zostaje pod pigułką; resztę nadrabia oddalenie (--zoom
        // wokół górnej krawędzi drzwi). Pomiar z offsetTop — bez wpływu obecnego przesunięcia i skali.
        function setLift(px, zoom, originY) {
            lift = Math.max(0, Math.round(px || 0));
            if (lift) host.style.setProperty('--lift', lift + 'px');
            else host.style.removeProperty('--lift');
            if (zoom && zoom < 1) {
                host.style.setProperty('--zoom', zoom.toFixed(3));
                host.style.setProperty('--zoom-y', Math.round(originY) + 'px');
            } else {
                host.style.removeProperty('--zoom');
                host.style.removeProperty('--zoom-y');
            }
        }

        function offsetIn(node, root) {
            var y = 0;
            while (node && node !== root) {
                y += node.offsetTop;
                node = node.offsetParent;
            }
            return node === root ? y : null;
        }

        function liftFor(node) {
            if (!node || !win || !win.isOpen() || isDesktop()) { setLift(0); return; }
            var sheet = parseFloat(host.style.getPropertyValue('--window-h')) || 0;
            var nodeTop = offsetIn(node, stage);
            if (nodeTop == null || !sheet) { setLift(0); return; }
            var limit = host.clientHeight - stage.offsetTop - sheet - 12;     // dół wybranego jajka (układ sceny)
            var bottom = nodeTop + node.offsetHeight;
            var need = bottom - limit;
            if (need <= 0) { setLift(0); return; }
            // Górna granica: pod pigułką (z marginesem); drzwi z szyldem i znaczkiem (−12 px) nie wchodzą wyżej
            var pill = ctx.root.querySelector('.pets-pill');
            var pillBottom = pill ? pill.getBoundingClientRect().bottom - host.getBoundingClientRect().top : 60;
            var ceiling = pillBottom + 8 - stage.offsetTop;
            var doors = [doorInc.a, doorWard.a].map(function (a) { return offsetIn(a, stage); })
                .filter(function (y) { return y != null; });
            var doorTop = doors.length ? Math.min.apply(null, doors) - 12 : ceiling;
            var room = Math.max(0, doorTop - ceiling);
            if (need <= room) { setLift(need); return; }
            // Przesunięcie o `room` stawia drzwi tuż pod pigułką; jajko dochodzi nad arkusz przez oddalenie.
            // Bardzo niski widok (telefon poziomo): oddalenie najwyżej do 0,7 — resztę nadrabia dalsze przesunięcie
            // (jajko nad arkuszem ważniejsze niż szyldy drzwi pod pigułką)
            var span = bottom - doorTop;
            var zoom = span > 0 ? (limit - ceiling) / span : 1;
            var extra = 0;
            if (zoom < 0.7) {
                zoom = 0.7;
                extra = ceiling + zoom * span - limit;
            }
            setLift(room + extra, zoom, doorTop);
        }

        // --- odbiór jajka: lot do drzwi Inkubatorium -------------------------------------------------------
        function stopFlight() {
            if (!flight) return;
            clearTimeout(flight.timer);
            if (flight.anim) { try { flight.anim.cancel(); } catch (e) { /* już skończona */ } }
            if (flight.rig) flight.rig.destroy();
            if (flight.el.parentNode) flight.el.parentNode.removeChild(flight.el);
            flight = null;
        }

        function pulseDoor() {
            if (u.reducedMotion()) return;
            var f = doorInc.frame;
            f.classList.remove('is-receiving');
            void f.offsetWidth;
            f.classList.add('is-receiving');
            setTimeout(function () { f.classList.remove('is-receiving'); }, 800);
        }

        function focusAfterClaim(hadFocus) {
            if (!hadFocus) return;
            var next = eggsBox.querySelector('.pets-hall__egg');
            H.focus(next || doorInc.a);
        }

        function launch(key) {
            var view = eggViews[key];
            var active = document.activeElement;
            var hadFocus = !active || active === document.body || (win && win.el.contains(active)) ||
                (view && view.el.contains(active));
            // Okno znika razem z „odjazdem” jajka; scena wraca na miejsce bez przejścia (pozycje ostateczne)
            host.classList.add('is-snap');
            if (win && win.isOpen()) win.close({ restoreFocus: false });
            var hostBox = host.getBoundingClientRect();
            var start = view && view.el.isConnected ? view.el.getBoundingClientRect() : null;
            var end = doorInc.frame.getBoundingClientRect();
            claiming = null;
            if (lastState) syncEggs(lastState);           // jajko schodzi z lady (prezent z licznikiem zostaje)
            focusAfterClaim(hadFocus);
            requestAnimationFrame(function () { host.classList.remove('is-snap'); });
            stopFlight();
            if (u.reducedMotion() || !start || !start.width || !end.width) {
                pulseDoor();
                return;
            }
            var item = view.item;
            var fly = el('div', 'pets-hall__flyer');
            fly.setAttribute('aria-hidden', 'true');
            fly.style.left = (start.left - hostBox.left) + 'px';
            fly.style.top = (start.top - hostBox.top) + 'px';
            fly.style.width = start.width + 'px';
            fly.style.height = start.height + 'px';
            var art = giftArt(item);
            fly.appendChild(art.el);
            host.appendChild(fly);
            var dx = (end.left + end.width / 2) - (start.left + start.width / 2);
            var dy = (end.top + end.height * 0.42) - (start.top + start.height / 2);
            flight = { el: fly, rig: art.rig, anim: null, timer: 0 };
            var mine = flight;
            function finish() {
                if (flight !== mine) return;
                stopFlight();
                pulseDoor();
            }
            if (typeof fly.animate === 'function') {
                mine.anim = fly.animate([
                    { transform: 'translate(0, 0) scale(1) rotate(0deg)', opacity: 1 },
                    { transform: 'translate(' + (dx * 0.5).toFixed(1) + 'px, ' + (dy * 0.5 - 80).toFixed(1) + 'px) scale(0.9) rotate(-14deg)', opacity: 1, offset: 0.5 },
                    { transform: 'translate(' + dx.toFixed(1) + 'px, ' + dy.toFixed(1) + 'px) scale(0.42) rotate(10deg)', opacity: 0.2 }
                ], { duration: FLY_MS, easing: 'ease-in-out', fill: 'forwards' });
                mine.anim.onfinish = finish;
            }
            // Zapas: ukryta karta wstrzymuje animacje — lot i tak się kończy
            mine.timer = setTimeout(finish, FLY_MS + 300);
        }

        function claimEgg(btn) {
            var key = btn.dataset.key;
            var item = findClaim(lastState, key);
            if (!item || claiming) return;
            claiming = { key: key };
            u.setBusy(btn, true);
            H.claim(ctx, item).then(function () {
                if (!claiming || claiming.key !== key) return;
                launch(key);
            }, function () {
                // Błąd pokazał ctx.send (409 = ciche odświeżenie); jajko wraca do zwykłej synchronizacji
                claiming = null;
                if (btn.isConnected) u.setBusy(btn, false);
                if (lastState) render(lastState);
            });
        }

        // --- zdarzenia (delegacja) ------------------------------------------------------------------------
        host.addEventListener('click', function (e) {
            var egg = e.target.closest('[data-hall-egg]');
            if (egg && host.contains(egg)) {
                openClaim(egg.dataset.hallEgg, egg);
                return;
            }
            var btn = e.target.closest('[data-hall-action]');
            if (!btn || !host.contains(btn) || btn.disabled || btn.getAttribute('aria-disabled') === 'true') return;
            if (btn.dataset.hallAction === 'claim') claimEgg(btn);
        });

        // --- render ---------------------------------------------------------------------------------------
        function render(state) {
            lastState = state;
            syncEggs(state);
            renderDoors(state);
            renderTalk(state);
            renderClock();
            if (openKey != null && win && win.isOpen() && !(claiming && claiming.key === openKey)) {
                var item = findClaim(state, openKey);
                if (!item) H.closeGone(win, host);
                else if (claimSig(item) !== openSig) replaceClaim(item);
            }
        }

        return {
            enter: function () {},
            leave: function () {
                stopFlight();
                claiming = null;
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                setLift(0);
                // Ukryta scena nie trzyma żywych rigów — render zbuduje je od nowa
                Object.keys(eggViews).forEach(dropEggView);
                eggOrder = [];
                talkSig = null;
                talk.innerHTML = '';
            },
            render: render,
            tick: function () {
                var state = ctx.state();
                if (!state) return;
                renderTalk(state);
                renderClock();
            }
        };
    }

    W.scenes.szpital = {
        title: 'Szpital',
        create: create
    };
})();
