/**
 * PetRoom — pokój pupili (spec v3 §6.1, §7): wspólny dla domku (pełny) i widgetu dashboardu (compact).
 *
 * API (kontrakt planu Task 7 → Task 8):
 *   PetRoom.mount(container, {pets, night, compact, mainPetId, onPetClick(petId), interactive}) -> room
 *     room.update(pets, {night, mainPetId}) · room.focus(petId | null) · room.pat(petId) -> Promise
 *     room.playAction(petId, action, variant) -> Promise · room.destroy() · room.el
 *     (+ room.petButton(petId) — przycisk pupila, np. do oddania fokusu po zamknięciu panelu)
 *
 * Zachowanie:
 *   - pupile w szpitalu (`pet.hospital`) nie pojawiają się w pokoju; do 8 pupili;
 *   - zachowanie wg najpilniejszej potrzeby (PetRig.needOf): chory/krytyczny leży na dywanie, śpiący idzie
 *     do koszyka / na poduszkę / kładzie się na kanapie, głodny siada przy misce, smutny w kącie przy roślinie,
 *     znudzony przy koszu z zabawkami, brudny i szczęśliwy spacerują (jak towarzysz: przerwy 4–9 s, bez
 *     nakładania się); wygląd potrzeby rysuje rig (setNeed/setPose);
 *   - pełny pokój (domek) ma meble: kanapę, stolik z lampką (w nocy i w ciemnym motywie świeci), regał, roślinę
 *     i kosz z zabawkami. Szczęśliwy spacerowicz od czasu do czasu wskakuje na kanapę (siada albo się kładzie)
 *     albo zagląda do zabawek; na kanapie siedzi NA siedzisku (głębia kanapy, wysokość siedziska z jej wymiarów
 *     w DOM). W drodze pupil stoi, pozę miejsca przyjmuje po dojściu;
 *   - focus(id): pupil szybko podbiega na środek (0,5–0,75 s), lekko się powiększa, reszta przygasa;
 *     focus(null) = powrót spacerem;
 *   - compact (widget): mniejsza skala, `mainPetId` duży na środku z dymkiem potrzeby, max 4 pozostałych
 *     w tle + znacznik „+N”, bez spaceru po całej szerokości (lekkie ruchy w miejscu), bez mebli;
 *   - interactive: false — pupile są tylko linkami do domku (klik woła onPetClick), bez fokusu/pat;
 *   - prefers-reduced-motion (lub html.pet-rig-rm): bez spaceru, biegu i skoków — pupile stają od razu na miejscu.
 * Bezpieczeństwo: imiona przez textContent / setAttribute; zero inline onclick (delegacja).
 * Plik ładuje się na kilku stronach (domek + dashboard) — guard idempotencji.
 */
(function () {
    'use strict';

    if (window.PetRoom) return;

    var MAX_PETS = 8;
    var COMPACT_BACK = 4;
    var WALK_SPEED = 46;                 // px/s — spacer
    var RUN_SPEED = 1000;                // px/s — wybrany pupil biegnie na środek…
    var RUN_MIN = 0.5, RUN_MAX = 0.75;   // …w 0,5–0,75 s niezależnie od odległości
    var HOP = 0.4;                       // s — wskok na kanapę / zeskok
    var PAUSE_MIN = 4000, PAUSE_MAX = 9000;
    var NUDGE_MIN = 5000, NUDGE_MAX = 11000;
    var VISIT_CHANCE = 0.3;              // spacerowicz co ~3. krok idzie na kanapę albo do zabawek zamiast spaceru
    var SOFA_VISIT = 0.6;                // …z czego kanapa (reszta: kosz z zabawkami)
    var SOFA_STAY_MIN = 9000, SOFA_STAY_MAX = 17000;
    // Kanapa: środki miejsc (ułamek szerokości kanapy) i linia siedziska (ułamek wysokości kanapy od dołu,
    // z viewBox SOFA_SVG: przednia krawędź poduszek siedziska y≈76 ze 118)
    var SOFA_SEATS = [0.33, 0.67];
    var SOFA_SEAT_H = 0.36;
    var SOFA_FRONT = 0.05;               // podejście / zeskok: tyle przed kanapą (głębia)

    var NEED_LABEL = {
        happy: 'szczęśliwy', hungry: 'głodny', dirty: 'brudny', sad: 'smutny', bored: 'znudzony',
        sick: 'chory', critical: 'w stanie krytycznym', sleep: 'śpi'
    };
    // Dymek nad głównym pupilem w widgecie (spec v3 §7)
    var NEED_BUBBLE = {
        hungry: 'Jestem głodny!', dirty: 'Chcę się umyć!', sad: 'Smutno mi…', bored: 'Nudzę się…',
        sick: 'Źle się czuję…', critical: 'Pomocy!', sleep: 'Zzz…'
    };
    // Potrzeba → miejsce w pokoju i poza (w widgecie liczy się tylko poza)
    var BEHAVIOR = {
        sick: ['rug', 'lie'], critical: ['rug', 'lie'], sleep: ['basket', 'lie'], hungry: ['bowl', 'sit'],
        sad: ['corner', 'sit'], bored: ['toys', 'sit'], dirty: ['wander', 'stand'], happy: ['wander', 'stand']
    };
    // Miejsca: x = środek pupila (ułamek szerokości), y = odległość stóp od dołu (ułamek wysokości pokoju).
    // Pupile na podłodze stoją najdalej na głębokości 0,26 — dalej, pod ścianą, stoją meble (≈ 0,27–0,3).
    var SPOTS = {
        bowl: [[0.24, 0.05], [0.31, 0.11], [0.2, 0.15], [0.36, 0.04]],
        // koszyk, poduszka, (tu dwa miejsca na kanapie — SLEEP_SOFA_AT), dalej podłoga przy koszyku
        basket: [[0.87, 0.08], [0.72, 0.05], [0.79, 0.16], [0.64, 0.12]],
        corner: [[0.07, 0.22], [0.15, 0.24], [0.1, 0.15], [0.22, 0.2]],
        toys: [[0.37, 0.23], [0.56, 0.23], [0.46, 0.17], [0.3, 0.17]],
        rug: [[0.44, 0.09], [0.56, 0.05], [0.5, 0.17], [0.38, 0.15]]
    };
    var SLEEP_SOFA_AT = 2;               // śpiący: po koszyku i poduszce — kanapa, potem podłoga
    // Sloty zajęte → rozsuwanie po podłodze w obszarze miejsca, a gdy i tam ciasno — po całej podłodze
    var AREAS = {
        bowl: { x0: 0.08, x1: 0.46, y0: 0.03, y1: 0.24 },
        basket: { x0: 0.42, x1: 0.92, y0: 0.03, y1: 0.26 },   // koszyk + poduszka; w nocy śpią tu wszyscy
        corner: { x0: 0.06, x1: 0.36, y0: 0.12, y1: 0.26 },
        toys: { x0: 0.3, x1: 0.66, y0: 0.1, y1: 0.26 },
        rug: { x0: 0.3, x1: 0.7, y0: 0.03, y1: 0.22 }
    };
    var FLOOR = { x0: 0.08, x1: 0.92, y0: 0.02, y1: 0.26 };
    var WANDER = { x0: 0.3, x1: 0.7, y0: 0.03, y1: 0.2 };
    var WANDER_WIDE = { x0: 0.12, x1: 0.88, y0: 0.03, y1: 0.24 };   // > 3 pupili: spacer po szerszej podłodze
    var WANDER_TRIES = 24;
    var SEP_X = 0.9, SEP_Y = 0.5;        // próg kolizji: ułamek szerokości / wysokości pupila
    var SEP_PATH = 0.7;                  // po drodze wolno minąć innego bliżej, ale nie przejść przez niego
    var FOCUS_SPOT = [0.5, 0.04];
    var COMPACT_MAIN = [0.5, 0.05];
    var COMPACT_SLOTS = [[0.15, 0.17], [0.85, 0.17], [0.3, 0.27], [0.7, 0.27]];

    function reducedMotion() {
        if (window.PetRig && typeof window.PetRig.reducedMotion === 'function') return window.PetRig.reducedMotion();
        return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

    function rand(a, b) { return a + Math.random() * (b - a); }

    function grid(box, cols, rows) {
        var out = [];
        for (var r = 0; r < rows; r++) {
            for (var c = 0; c < cols; c++) {
                out.push([box.x0 + (box.x1 - box.x0) * c / (cols - 1), box.y0 + (box.y1 - box.y0) * r / (rows - 1)]);
            }
        }
        return out;
    }

    function needOf(pet) {
        var R = window.PetRig;
        if (R && typeof R.needOf === 'function') return R.needOf(pet);
        return 'happy';
    }

    // --- tło pokoju (kodowane SVG, kolory ilustracji stałe; noc = klasa .is-night) -------------

    var WINDOW_SVG =
        '<svg class="pet-room__window" viewBox="0 0 120 90" aria-hidden="true" focusable="false">' +
        '<rect x="3" y="3" width="114" height="84" rx="6" class="pr-sky"/>' +
        '<g class="pr-day"><circle cx="90" cy="24" r="10" fill="#ffe27a"/><ellipse cx="34" cy="30" rx="16" ry="6" fill="#ffffff"/>' +
        '<ellipse cx="44" cy="26" rx="10" ry="5" fill="#ffffff"/><path d="M3 70 Q30 56 60 66 T117 62 V87 H3 Z" fill="#a8dc8f"/></g>' +
        '<g class="pr-night"><circle cx="88" cy="24" r="9" fill="#fff4c2"/><circle cx="93" cy="20" r="8" fill="#1d2550"/>' +
        '<circle cx="24" cy="18" r="1.4" fill="#fff8d6"/><circle cx="46" cy="36" r="1.2" fill="#fff8d6"/><circle cx="66" cy="14" r="1.5" fill="#fff8d6"/>' +
        '<circle cx="104" cy="50" r="1.2" fill="#fff8d6"/><circle cx="16" cy="54" r="1.1" fill="#fff8d6"/></g>' +
        '<rect x="3" y="3" width="114" height="84" rx="6" fill="none" stroke="#ffffff" stroke-width="6"/>' +
        '<line x1="60" y1="3" x2="60" y2="87" stroke="#ffffff" stroke-width="4"/>' +
        '<line x1="3" y1="45" x2="117" y2="45" stroke="#ffffff" stroke-width="3"/>' +
        '<path d="M0 2 Q14 40 4 88" stroke="#ff9ec4" stroke-width="7" fill="none" opacity=".85"/>' +
        '<path d="M120 2 Q106 40 116 88" stroke="#ff9ec4" stroke-width="7" fill="none" opacity=".85"/>' +
        '</svg>';
    var PICTURE_SVG =
        '<svg class="pet-room__picture" viewBox="0 0 40 32" aria-hidden="true" focusable="false">' +
        '<rect x="1" y="1" width="38" height="30" rx="3" fill="#fff6e8" stroke="#d9a877" stroke-width="2"/>' +
        '<path d="M20 25s-8-4.6-8-10a4.2 4.2 0 0 1 8-1.6 4.2 4.2 0 0 1 8 1.6c0 5.4-8 10-8 10z" fill="#ff8fab"/></svg>';
    var BOWLS_SVG =
        '<svg class="pet-room__bowls" viewBox="0 0 100 34" aria-hidden="true" focusable="false">' +
        '<ellipse cx="26" cy="28" rx="24" ry="5" fill="#000" opacity=".1"/><ellipse cx="74" cy="28" rx="24" ry="5" fill="#000" opacity=".1"/>' +
        '<path d="M4 14 H48 L42 28 H10 Z" fill="#7fb3ea"/><ellipse cx="26" cy="14" rx="22" ry="6" fill="#a9cdf3"/>' +
        '<ellipse cx="26" cy="14" rx="15" ry="3.6" fill="#c98b5c"/><circle cx="21" cy="12.5" r="2" fill="#a86f45"/><circle cx="29" cy="13" r="2.2" fill="#a86f45"/>' +
        '<path d="M52 14 H96 L90 28 H58 Z" fill="#ffd36b"/><ellipse cx="74" cy="14" rx="22" ry="6" fill="#ffe7a3"/>' +
        '<ellipse cx="74" cy="14" rx="15" ry="3.6" fill="#9fd3ff"/></svg>';
    var BASKET_SVG =
        '<svg class="pet-room__basket" viewBox="0 0 120 56" aria-hidden="true" focusable="false">' +
        '<ellipse cx="60" cy="50" rx="56" ry="6" fill="#000" opacity=".1"/>' +
        '<path d="M8 24 Q60 -6 112 24 V44 Q60 58 8 44 Z" fill="#c98b5c"/>' +
        '<path d="M14 26 Q60 2 106 26" stroke="#a86f45" stroke-width="3" fill="none"/>' +
        '<g stroke="#a86f45" stroke-width="2" opacity=".6"><path d="M20 30 V44"/><path d="M34 26 V48"/><path d="M48 24 V50"/><path d="M62 24 V50"/><path d="M76 24 V50"/><path d="M90 26 V48"/><path d="M102 30 V44"/></g>' +
        '<ellipse cx="60" cy="30" rx="44" ry="10" fill="#f6b6c9"/><ellipse cx="60" cy="28" rx="38" ry="7" fill="#ffd3e1"/></svg>';
    var CUSHION_SVG =
        '<svg class="pet-room__cushion" viewBox="0 0 80 28" aria-hidden="true" focusable="false">' +
        '<ellipse cx="40" cy="24" rx="36" ry="4" fill="#000" opacity=".08"/>' +
        '<path d="M6 14 Q40 -2 74 14 Q76 24 40 26 Q4 24 6 14 Z" fill="#b99cff"/><path d="M14 13 Q40 4 66 13" stroke="#d6c6ff" stroke-width="2" fill="none"/></svg>';
    var TOYS_SVG =
        '<svg class="pet-room__toys" viewBox="0 0 70 30" aria-hidden="true" focusable="false">' +
        '<ellipse cx="18" cy="26" rx="12" ry="3" fill="#000" opacity=".1"/><circle cx="18" cy="15" r="11" fill="#ff6b7d"/>' +
        '<path d="M8 12 Q18 18 28 12 M9 19 Q18 13 27 19" stroke="#ffffff" stroke-width="2" fill="none"/>' +
        '<ellipse cx="52" cy="27" rx="10" ry="2.6" fill="#000" opacity=".1"/><circle cx="52" cy="19" r="8" fill="#7fd3c4"/>' +
        '<path d="M45 16 Q52 22 59 15 M46 22 Q53 17 59 22" stroke="#4fb5a6" stroke-width="1.6" fill="none"/>' +
        '<path d="M59 21 Q66 26 68 18" stroke="#7fd3c4" stroke-width="1.6" fill="none"/></svg>';

    // Meble pełnego pokoju (domek). Kolory z klas .pf-* (pet-room.css: zmienne --pf-*, wariant wieczorny w ciemnym
    // motywie). Kanapa: siedzisko — przednia krawędź poduszek y≈76 (SOFA_SEAT_H), miejsca w 1/3 i 2/3 szerokości.
    var SOFA_SVG =
        '<svg class="pet-room__sofa" viewBox="0 0 200 118" aria-hidden="true" focusable="false">' +
        '<ellipse class="pf-shadow" cx="100" cy="112" rx="98" ry="6"/>' +
        '<rect class="pf-wood-d" x="22" y="96" width="10" height="17" rx="3"/><rect class="pf-wood-d" x="168" y="96" width="10" height="17" rx="3"/>' +
        '<rect class="pf-sofa" x="14" y="8" width="172" height="74" rx="28"/>' +
        '<rect class="pf-sofa-l" x="27" y="17" width="70" height="52" rx="20"/><rect class="pf-sofa-l" x="103" y="17" width="70" height="52" rx="20"/>' +
        '<path class="pf-sofa-hi" d="M40 26 Q62 20 84 26 M116 26 Q138 20 160 26"/>' +
        '<g transform="rotate(-12 46 50)"><rect class="pf-pillow-a" x="31" y="35" width="31" height="29" rx="11"/>' +
        '<path class="pf-pillow-mark" d="M46.5 56s-6-3.4-6-7.4a3.1 3.1 0 0 1 6-1.2 3.1 3.1 0 0 1 6 1.2c0 4-6 7.4-6 7.4z"/></g>' +
        '<g transform="rotate(11 154 50)"><rect class="pf-pillow-b" x="139" y="36" width="31" height="28" rx="11"/>' +
        '<circle class="pf-pillow-dot" cx="148" cy="45" r="2.2"/><circle class="pf-pillow-dot" cx="160" cy="47" r="2.2"/>' +
        '<circle class="pf-pillow-dot" cx="152" cy="55" r="2.2"/></g>' +
        '<rect class="pf-sofa-d" x="8" y="70" width="184" height="32" rx="13"/>' +
        '<rect class="pf-sofa" x="24" y="58" width="77" height="24" rx="11"/><rect class="pf-sofa" x="99" y="58" width="77" height="24" rx="11"/>' +
        '<path class="pf-sofa-hi" d="M34 63 H90 M110 63 H166"/>' +
        '<rect class="pf-sofa" x="0" y="40" width="33" height="62" rx="16"/><rect class="pf-sofa" x="167" y="40" width="33" height="62" rx="16"/>' +
        '<ellipse class="pf-sofa-l" cx="16.5" cy="45" rx="15" ry="6.5"/><ellipse class="pf-sofa-l" cx="183.5" cy="45" rx="15" ry="6.5"/>' +
        '</svg>';
    // Stolik z lampką — lampka stoi na blacie (nie na podłodze); w nocy świeci (abażur + .pet-room__lamplight)
    var TABLE_SVG =
        '<svg class="pet-room__table" viewBox="0 0 60 132" aria-hidden="true" focusable="false">' +
        '<ellipse class="pr-lamp-glow" cx="30" cy="38" rx="30" ry="28"/>' +
        '<ellipse class="pf-shadow" cx="30" cy="127" rx="24" ry="4"/>' +
        '<rect class="pf-wood-d" x="26.5" y="86" width="7" height="36"/>' +
        '<ellipse class="pf-wood" cx="30" cy="123" rx="15" ry="4.5"/>' +
        '<rect class="pf-wood" x="3" y="79" width="54" height="9" rx="4.5"/><rect class="pf-wood-d" x="6" y="86" width="48" height="2.6" rx="1.3"/>' +
        '<ellipse class="pf-lamp-metal" cx="30" cy="79" rx="9.5" ry="3"/><rect class="pf-lamp-metal" x="28.5" y="46" width="3" height="33"/>' +
        '<path class="pf-shade" d="M15 22 H45 L52 48 H8 Z"/><path class="pf-shade-trim" d="M8.6 46 H51.4"/>' +
        '</svg>';
    var PLANT_SVG =
        '<svg class="pet-room__plant" viewBox="0 0 70 130" aria-hidden="true" focusable="false">' +
        '<ellipse class="pf-shadow" cx="35" cy="125" rx="24" ry="4"/>' +
        '<path class="pf-leaf-d" d="M35 92 C30 70 18 60 6 57 C12 74 22 86 35 92 Z"/>' +
        '<path class="pf-leaf-d" d="M35 92 C40 66 53 54 66 50 C59 71 48 85 35 92 Z"/>' +
        '<path class="pf-leaf" d="M35 90 C25 62 27 34 37 12 C47 36 45 64 35 90 Z"/>' +
        '<path class="pf-leaf" d="M34 92 C22 75 10 72 1 76 C11 89 24 93 34 92 Z"/>' +
        '<path class="pf-leaf" d="M36 92 C48 75 60 72 69 76 C59 89 46 93 36 92 Z"/>' +
        '<path class="pf-vein" d="M36 86 Q34 50 37 18 M33 90 Q20 80 6 77 M37 90 Q50 80 64 77"/>' +
        '<path class="pf-pot" d="M15 92 H55 L50 124 H20 Z"/><rect class="pf-pot-rim" x="11" y="86" width="48" height="10" rx="5"/>' +
        '<path class="pf-pot-mark" d="M35 115s-5-2.9-5-6.2a2.6 2.6 0 0 1 5-1 2.6 2.6 0 0 1 5 1c0 3.3-5 6.2-5 6.2z"/>' +
        '</svg>';
    var SHELF_SVG =
        '<svg class="pet-room__shelf" viewBox="0 0 100 132" aria-hidden="true" focusable="false">' +
        '<ellipse class="pf-shadow" cx="50" cy="128" rx="48" ry="4"/>' +
        '<rect class="pf-wood" x="2" y="4" width="96" height="122" rx="7"/>' +
        '<rect class="pf-shelf-back" x="9" y="11" width="82" height="108" rx="3"/>' +
        // półka górna: książki + pochylona
        '<rect class="pf-book-a" x="13" y="21" width="9" height="25" rx="2"/><rect class="pf-book-b" x="23" y="16" width="8" height="30" rx="2"/>' +
        '<rect class="pf-book-c" x="32" y="23" width="10" height="23" rx="2"/>' +
        '<rect class="pf-book-d" x="45" y="19" width="8" height="27" rx="2" transform="rotate(14 49 46)"/>' +
        '<rect class="pf-book-e" x="70" y="18" width="9" height="28" rx="2"/><rect class="pf-book-a" x="80" y="22" width="8" height="24" rx="2"/>' +
        // półka środkowa: piłka i stos książek
        '<circle class="pf-toy-ball" cx="25" cy="73" r="11"/><path class="pf-toy-line" d="M15 70 Q25 77 35 70"/>' +
        '<rect class="pf-book-c" x="46" y="75" width="40" height="9" rx="2"/><rect class="pf-book-e" x="50" y="66" width="33" height="9" rx="2"/>' +
        '<rect class="pf-book-b" x="54" y="58" width="26" height="8" rx="2"/>' +
        // półka dolna: klocki
        '<rect class="pf-block-a" x="14" y="100" width="19" height="19" rx="3"/><rect class="pf-block-b" x="35" y="100" width="19" height="19" rx="3"/>' +
        '<circle class="pf-block-dot" cx="23.5" cy="109.5" r="3.2"/><path class="pf-block-dot" d="M44.5 104 l4 7 h-8 z"/>' +
        '<rect class="pf-book-d" x="64" y="94" width="9" height="25" rx="2"/><rect class="pf-book-a" x="74" y="98" width="10" height="21" rx="2"/>' +
        '<rect class="pf-wood-d" x="9" y="46" width="82" height="5"/><rect class="pf-wood-d" x="9" y="84" width="82" height="5"/>' +
        '<rect class="pf-wood-d" x="9" y="119" width="82" height="3"/>' +
        '</svg>';
    // Kosz z zabawkami (znudzony siada obok): piłka, kaczuszka i różdżka z gwiazdką wystają nad brzeg
    var TOYBOX_SVG =
        '<svg class="pet-room__toybox" viewBox="0 0 90 72" aria-hidden="true" focusable="false">' +
        '<ellipse class="pf-shadow" cx="45" cy="67" rx="42" ry="4.5"/>' +
        '<path class="pf-wand" d="M47 36 L39 9"/><path class="pf-star" d="M38.5 0.5l2.7 5.5 6 .9-4.4 4.2 1 6-5.3-2.8-5.4 2.8 1-6-4.3-4.2 6-.9z"/>' +
        '<circle class="pf-toy-ball" cx="25" cy="27" r="13"/><path class="pf-toy-line" d="M13 24 Q25 32 37 24"/>' +
        '<ellipse class="pf-duck" cx="64" cy="30" rx="14" ry="9"/><circle class="pf-duck" cx="60" cy="18" r="8"/>' +
        '<path class="pf-beak" d="M52.5 18.5 l-6 2 6 2 z"/><circle class="pf-eye" cx="57.5" cy="16.5" r="1.4"/>' +
        '<path class="pf-wicker" d="M6 33 H84 L78 63 Q45 70 12 63 Z"/>' +
        '<rect class="pf-wicker-d" x="3" y="28" width="84" height="9" rx="4.5"/>' +
        '<path class="pf-weave" d="M10 45 H80 M13 55 H77 M24 38 V65 M38 38 V67 M52 38 V67 M66 38 V65"/>' +
        '</svg>';
    var PAW_PICTURE_SVG =
        '<svg class="pet-room__picture pet-room__picture--paw" viewBox="0 0 40 32" aria-hidden="true" focusable="false">' +
        '<rect class="pf-canvas" x="1" y="1" width="38" height="30" rx="3"/>' +
        '<ellipse class="pf-paw" cx="20" cy="20.5" rx="6.2" ry="5.2"/><circle class="pf-paw" cx="12.2" cy="13.6" r="2.7"/>' +
        '<circle class="pf-paw" cx="17" cy="9.4" r="2.7"/><circle class="pf-paw" cx="23" cy="9.4" r="2.7"/><circle class="pf-paw" cx="27.8" cy="13.6" r="2.7"/>' +
        '</svg>';

    function sceneMarkup(compact) {
        if (compact) {
            // Widget: bez mebli i ozdób (jak przed meblami domku)
            return '<div class="pet-room__scene" aria-hidden="true">' +
                '<div class="pet-room__wall"></div>' + WINDOW_SVG +
                '<div class="pet-room__floor"></div><div class="pet-room__rug"></div>' +
                BOWLS_SVG + BASKET_SVG + TOYS_SVG +
                '<div class="pet-room__dark"></div></div>';
        }
        // Kolejność = warstwy: ściana i ozdoby, podłoga, meble pod ścianą, rzeczy na podłodze, noc, światło lampki
        return '<div class="pet-room__scene" aria-hidden="true">' +
            '<div class="pet-room__wall"></div>' + WINDOW_SVG + PICTURE_SVG + PAW_PICTURE_SVG +
            '<div class="pet-room__floor"></div>' +
            PLANT_SVG + SHELF_SVG + TOYBOX_SVG + SOFA_SVG + TABLE_SVG +
            '<div class="pet-room__rug"></div>' +
            BOWLS_SVG + BASKET_SVG + CUSHION_SVG + TOYS_SVG +
            '<div class="pet-room__dark"></div><div class="pet-room__lamplight"></div></div>';
    }

    // --- pokój -----------------------------------------------------------------------------

    function mount(container, opts) {
        opts = opts || {};
        var compact = !!opts.compact;
        var interactive = opts.interactive !== false;
        var night = !!opts.night;
        var mainId = opts.mainPetId != null ? opts.mainPetId : null;
        var focusedId = null;
        var destroyed = false;
        // id → {pet, el, flip, rig, name, need, pose (poza potrzeby), poseNow (poza rigu), goalPose (poza celu),
        //       x, y (głębia), lift (wysokość nad podłogą), seat (miejsce na kanapie | -1), visit ('sofa' | 'toys' | null),
        //       place, spotFor, walk, acting, timer, arrive}
        var entries = {};
        var order = [];

        var el = document.createElement('div');
        el.className = 'pet-room' + (compact ? ' pet-room--compact' : '') + (interactive ? ' is-interactive' : '');
        el.innerHTML = sceneMarkup(compact);
        var layer = document.createElement('div');
        layer.className = 'pet-room__pets';
        el.appendChild(layer);
        var bubble = document.createElement('span');
        bubble.className = 'pet-room__bubble';
        bubble.hidden = true;
        bubble.setAttribute('aria-hidden', 'true');
        el.appendChild(bubble);
        var more = document.createElement('span');
        more.className = 'pet-room__more';
        more.hidden = true;
        el.appendChild(more);
        var sofa = el.querySelector('.pet-room__sofa');
        var room = { el: el };

        function width() { return el.clientWidth || 600; }
        function height() { return el.clientHeight || 300; }
        // Wąski pokój (≤ 640 px szerokości albo proporcje węższe niż 3:2 — telefon, domek na pełnym ekranie
        // z oknem sceny z boku, prawie kwadratowy monitor) ma wyższą podłogę i większych pupili
        // (.is-narrow w pet-room.css) — głębię spaceru rozciągamy na nią
        var narrow = false;
        var layoutWidth = 0;         // szerokość pokoju przy ostatnim rozstawieniu
        var resizeTimer = 0;
        function yScale() { return narrow ? 1.45 : 1; }
        function checkNarrow() {
            if (destroyed) return;
            var w = width();
            var n = !compact && (w <= 640 || w < el.clientHeight * 1.5);
            if (n !== narrow) {
                narrow = n;
                el.classList.toggle('is-narrow', n);
                // Inna wysokość podłogi i większi pupile — rozstaw od nowa (bez marszu), kolizje z nowymi progami
                if (order.length) layout(true);
                return;
            }
            // Kanapa rośnie i maleje z szerokością pokoju — siedzący na niej zostają na siedzisku
            refreshSeats();
            // Wyraźnie inna szerokość (domek: okno sceny rezerwuje prawe 376 px, zwinięty sidebar, obrót) —
            // pozycje w % zostają, ale pupile są względem pokoju więksi/mniejsi: rozstaw od nowa, spacerem
            if (!compact && order.length && layoutWidth && Math.abs(w - layoutWidth) / layoutWidth > 0.12) {
                clearTimeout(resizeTimer);
                resizeTimer = setTimeout(function () {
                    if (!destroyed) layout(false);
                }, 160);
            }
        }

        function setPose(entry, pose) {
            if (!pose || entry.poseNow === pose) return;
            entry.poseNow = pose;
            if (entry.rig && typeof entry.rig.setPose === 'function') entry.rig.setPose(pose);
        }

        function moving(entry) {
            return !!(entry.walk && entry.walk.until > Date.now());
        }

        /**
         * Jeden ruch pupila do (x, y). o: lift (wysokość nad podłogą — siedzisko kanapy, ułamek wysokości pokoju),
         * run (bieg do fokusu), hop (wskok/zeskok), pose (pełny pokój: poza po dojściu, w drodze „stand”), done.
         */
        function place(entry, x, y, instant, o) {
            o = o || {};
            var lift = o.lift || 0;
            var k = yScale();
            var dist = entry.x == null ? 0 :
                Math.hypot((x - entry.x) * width(), ((y - entry.y) * k + lift - (entry.lift || 0)) * height());
            var move = !instant && !reducedMotion() && entry.x != null && dist > 2;
            var dur = 0;
            if (move) {
                dur = o.hop ? HOP : o.run ? Math.min(RUN_MAX, Math.max(RUN_MIN, dist / RUN_SPEED)) : Math.max(0.5, dist / WALK_SPEED);
            }
            entry.el.classList.toggle('is-walking', move && !o.hop);
            entry.el.classList.toggle('is-running', move && !!o.run);
            entry.el.classList.toggle('is-hopping', move && !!o.hop);
            // Wartości dynamiczne (pozycja, czas ruchu, głębia) — reszta wyglądu w pet-room.css
            entry.el.style.setProperty('--walk', dur.toFixed(2) + 's');
            entry.el.style.setProperty('--depth', (1 - y * 0.7).toFixed(3));
            // Trasa marszu — inni nie wybierają celu ani drogi w poprzek niej, póki pupil idzie
            entry.walk = move ? { x0: entry.x, y0: entry.y, until: Date.now() + dur * 1000 } : null;
            entry.x = x;
            entry.y = y;
            entry.lift = lift;
            entry.el.style.left = (x * 100).toFixed(2) + '%';
            entry.el.style.bottom = ((y * k + lift) * 100).toFixed(2) + '%';
            entry.el.style.zIndex = String(100 - Math.round(y * 100) + (entry.pet.id === focusedId ? 50 : 0));
            clearTimeout(entry.arrive);
            if (!compact && o.pose) setPose(entry, move ? 'stand' : o.pose);
            if (move) {
                entry.arrive = setTimeout(function () {
                    entry.el.classList.remove('is-walking', 'is-running', 'is-hopping');
                    if (!compact && o.pose) setPose(entry, o.pose);
                    if (compact && entry.pet.id === mainId) placeBubble();
                    if (o.done) o.done();
                }, dur * 1000);
            } else if (o.done) {
                o.done();
            }
        }

        // --- kanapa ------------------------------------------------------------------------
        // Wymiary z DOM (pozycja i szerokość kanapy żyją w pet-room.css: szeroki / wąski pokój, okno sceny):
        // głębia pupila na kanapie = głębia jej nóżek, wysokość = linia siedziska nad nimi.
        function seatTarget(i, pose) {
            if (!sofa || i < 0) return null;
            var b = el.getBoundingClientRect();
            var r = sofa.getBoundingClientRect();
            if (!b.width || !b.height || !r.width) return null;
            var feet = (b.bottom - r.bottom) / b.height;
            var seat = (b.bottom - r.bottom + r.height * SOFA_SEAT_H) / b.height;
            return {
                x: (r.left - b.left + r.width * SOFA_SEATS[i]) / b.width,
                y: feet / yScale(), lift: seat - feet, seat: i, pose: pose
            };
        }

        function freeSeat(entry) {
            if (!sofa) return -1;
            for (var i = 0; i < SOFA_SEATS.length; i++) {
                var taken = order.some(function (id) {
                    var o = entries[id];
                    return o && o !== entry && o.seat === i;
                });
                if (!taken) return i;
            }
            return -1;
        }

        /** Po zmianie rozmiaru: siedzący na kanapie przeskakują (bez animacji) na nowe siedzisko. */
        function refreshSeats() {
            if (compact || !sofa) return;
            order.forEach(function (id) {
                var e = entries[id];
                if (!e || e.seat < 0 || e.x == null || moving(e) || id === focusedId) return;
                var t = seatTarget(e.seat, null);
                if (t) place(e, t.x, t.y, true, { lift: t.lift });
            });
        }

        /**
         * Ruch do celu {x, y, lift, seat, pose}: na kanapę — podejście i wskok, z kanapy — zeskok i dalej;
         * o.run = bieg prosto do celu (fokus), o.instant = bez ruchu, o.done = po dojściu.
         */
        function moveTo(entry, t, o) {
            o = o || {};
            clearTimeout(entry.arrive);
            var instant = !!o.instant || entry.x == null || reducedMotion();
            var from = entry.seat;
            entry.goalPose = t.pose || entry.pose;
            entry.seat = t.seat != null && t.seat >= 0 ? t.seat : -1;   // miejsce zarezerwowane od razu
            var steps = [];
            var onSofa = (entry.lift || 0) > 0;
            var sameSeat = onSofa && from >= 0 && from === entry.seat;
            if (!instant && !o.run && !sameSeat) {
                if (onSofa) steps.push({ x: entry.x, y: Math.max(0.02, entry.y - SOFA_FRONT), hop: true });
                if (entry.seat >= 0) {
                    steps.push({ x: t.x, y: Math.max(0.02, t.y - SOFA_FRONT) });
                    steps.push({ seat: entry.seat, pose: t.pose, hop: true });
                }
            }
            if (!steps.length || steps[steps.length - 1].seat == null) {
                steps.push({ x: t.x, y: t.y, lift: t.lift, seat: entry.seat >= 0 ? entry.seat : null, pose: t.pose, run: !!o.run });
            }
            (function next(i) {
                var s = steps[i];
                var last = i === steps.length - 1;
                if (s.seat != null) {
                    // Siedzisko liczone w chwili wskoku (kanapa mogła zmienić rozmiar po drodze)
                    var g = seatTarget(s.seat, s.pose);
                    if (g) { s.x = g.x; s.y = g.y; s.lift = g.lift; }
                    if (s.x == null) { s.x = t.x; s.y = t.y; s.lift = t.lift; }
                }
                place(entry, s.x, s.y, instant, {
                    lift: s.lift, hop: s.hop, run: s.run, pose: last ? s.pose : 'stand',
                    done: last ? o.done : function () { next(i + 1); }
                });
            })(0);
        }

        // --- bez nakładania się ------------------------------------------------------------
        // Odległość liczona w „rozmiarach pupila”: sep ≥ 1 = nie zachodzą na siebie. Progi z realnego
        // rozmiaru pupila względem pokoju (szerokość pudełka, głębia, powiększenie fokusu): poziomo
        // SEP_X szerokości, pionowo SEP_Y wysokości (stopy tylnego o pół pupila wyżej = jego głowa nad przednim).
        function petBox() {
            var sample = entries[order[0]];
            var w = (sample && sample.el.offsetWidth) || 96;
            var h = (sample && sample.el.offsetHeight) || w;
            return { x: w / width(), y: h / (height() * yScale()) };
        }

        function scaleAt(y, id) {
            return (1 - y * 0.7) * (id === focusedId ? 1.3 : 1);
        }

        /** Przeszkody: pozycje (cele) innych pupili + punkty trasy tych, którzy właśnie idą. */
        function obstacles(entry, only) {
            var now = Date.now();
            var out = [];
            order.forEach(function (id) {
                var o = entries[id];
                if (!o || o === entry || o.x == null || (only && !only[id])) return;
                out.push({ x: o.x, y: o.y, id: id });
                if (o.walk && o.walk.until > now && o.walk.x0 != null) {
                    for (var k = 1; k < 6; k++) {
                        var t = k / 6;
                        out.push({ x: o.walk.x0 + (o.x - o.walk.x0) * t, y: o.walk.y0 + (o.y - o.walk.y0) * t, id: id });
                    }
                }
            });
            return out;
        }

        function sepAt(entry, x, y, obs, box) {
            var min = Infinity;
            var sa = scaleAt(y, entry.pet.id);
            for (var i = 0; i < obs.length; i++) {
                var o = obs[i];
                var sb = scaleAt(o.y, o.id);
                var tx = SEP_X * box.x * (sa + sb) / 2;
                var ty = SEP_Y * box.y * (sa + sb) / 2;
                var s = Math.max(Math.abs(o.x - x) / tx, Math.abs(o.y - y) / ty);
                if (s < min) min = s;
            }
            return min;
        }

        function pathSep(entry, x, y, obs, box) {
            if (entry.x == null) return Infinity;
            var min = Infinity;
            for (var k = 1; k < 8; k++) {
                var t = k / 8;
                min = Math.min(min, sepAt(entry, entry.x + (x - entry.x) * t, entry.y + (y - entry.y) * t, obs, box));
            }
            return min;
        }

        function wanderBox() {
            return order.length > 3 ? WANDER_WIDE : WANDER;
        }

        /**
         * Cel spaceru: losowy punkt wolny od innych (sep ≥ 1) i z drogą, która nie przechodzi przez nikogo;
         * gdy takiego nie ma — punkt z największym minimalnym dystansem, a gdy i on nie jest lepszy niż
         * obecne miejsce — null (zostaje, spróbuje przy następnym kroku).
         */
        function freeWanderSpot(entry, only) {
            var box = petBox();
            var obs = obstacles(entry, only);
            var area = wanderBox();
            var ok = [];
            var best = null, bestScore = -1;
            for (var i = 0; i < WANDER_TRIES; i++) {
                var x = rand(area.x0, area.x1), y = rand(area.y0, area.y1);
                var dest = sepAt(entry, x, y, obs, box);
                var path = only ? Infinity : pathSep(entry, x, y, obs, box);   // układ (layout) bez drogi — to zmiana miejsca
                if (dest >= 1 && path >= SEP_PATH) ok.push([x, y]);
                var score = Math.min(dest, path / SEP_PATH);
                if (score > bestScore) { bestScore = score; best = [x, y]; }
            }
            if (ok.length) return ok[Math.floor(Math.random() * ok.length)];
            if (entry.x != null && entry.seat < 0 && sepAt(entry, entry.x, entry.y, obs, box) >= bestScore) return null;
            return best;
        }

        /**
         * Miejsce potrzeby (miska, koszyk, kąt, zabawki, dywan): najpierw sloty SPOTS (śpiący: po koszyku
         * i poduszce — kanapa), potem siatka obszaru miejsca (najbliżej pierwszego slotu), potem cała podłoga;
         * bez wolnego — punkt z największym dystansem. Zwraca cel dla moveTo.
         */
        function freePlaceSpot(entry, placeName, only) {
            var box = petBox();
            var obs = obstacles(entry, only);
            var slots = SPOTS[placeName];
            var anchor = slots[0];
            var area = grid(AREAS[placeName], 11, 7).sort(function (a, b) {
                return Math.hypot(a[0] - anchor[0], a[1] - anchor[1]) - Math.hypot(b[0] - anchor[0], b[1] - anchor[1]);
            });
            var sofaAt = placeName === 'basket' ? SLEEP_SOFA_AT : -1;
            var best = slots[0], bestSep = -1;
            function firstFree(list) {
                for (var i = 0; i < list.length; i++) {
                    var s = sepAt(entry, list[i][0], list[i][1], obs, box);
                    if (s >= 1) return { x: list[i][0], y: list[i][1], pose: entry.pose };
                    if (s > bestSep) { bestSep = s; best = list[i]; }
                }
                return null;
            }
            var found = firstFree(sofaAt >= 0 ? slots.slice(0, sofaAt) : slots);
            if (found) return found;
            if (sofaAt >= 0) {
                // Miejsce na kanapie jest wyłącznie jednego pupila (rezerwacja w entry.seat)
                var seat = entry.seat >= 0 ? entry.seat : freeSeat(entry);
                var onSofa = seat >= 0 ? seatTarget(seat, entry.pose) : null;
                if (onSofa) return onSofa;
                found = firstFree(slots.slice(sofaAt));
                if (found) return found;
            }
            found = firstFree(area.concat(grid(FLOOR, 11, 5)));
            return found || { x: best[0], y: best[1], pose: entry.pose };
        }

        // --- wizyty spacerowiczów: kanapa i kosz z zabawkami ----------------------------------

        function sofaVisit(entry) {
            if (entry.need !== 'happy') return null;        // brudny nie wskakuje na kanapę
            var seat = freeSeat(entry);
            var t = seat >= 0 ? seatTarget(seat, Math.random() < 0.6 ? 'sit' : 'lie') : null;
            if (!t) return null;
            // Podejście przed kanapę nie może przechodzić przez innych
            var box = petBox();
            var obs = obstacles(entry, null);
            if (pathSep(entry, t.x, t.y - SOFA_FRONT, obs, box) < SEP_PATH) return null;
            t.visit = 'sofa';
            return t;
        }

        function toysVisit(entry) {
            var box = petBox();
            var obs = obstacles(entry, null);
            var list = SPOTS.toys.slice().sort(function () { return Math.random() - 0.5; });
            for (var i = 0; i < list.length; i++) {
                if (sepAt(entry, list[i][0], list[i][1], obs, box) >= 1 && pathSep(entry, list[i][0], list[i][1], obs, box) >= SEP_PATH) {
                    return { x: list[i][0], y: list[i][1], pose: 'stand', visit: 'toys' };
                }
            }
            return null;
        }

        function wanderStep(entry) {
            if (!entry.visit && Math.random() < VISIT_CHANCE) {
                var t = Math.random() < SOFA_VISIT ? sofaVisit(entry) || toysVisit(entry) : toysVisit(entry);
                if (t) {
                    entry.visit = t.visit;
                    moveTo(entry, t, {
                        done: t.visit === 'toys' ? function () {
                            // Przy zabawkach: radosny gest (rig sam pomija go w ograniczonym ruchu / w akcji)
                            if (entry.rig && typeof entry.rig.gesture === 'function' && entry.visit === 'toys') {
                                entry.rig.gesture(Math.random() < 0.5 ? 'jump' : 'sway');
                            }
                        } : null
                    });
                    return;
                }
            }
            var spot = freeWanderSpot(entry, null);
            if (!spot) return;                              // ciasno — zostaje (także na kanapie)
            entry.visit = null;
            moveTo(entry, { x: spot[0], y: spot[1], pose: entry.pose });
        }

        function scheduleWander(entry) {
            clearTimeout(entry.timer);
            if (destroyed || reducedMotion()) return;
            if (compact) {
                // Lekkie ruchy w miejscu (widget): krok w lewo/prawo wokół miejsca
                entry.timer = setTimeout(function () {
                    if (destroyed || entry.acting) return scheduleWander(entry);
                    var home = entry.home || [entry.x, entry.y];
                    place(entry, Math.max(0.06, Math.min(0.94, home[0] + rand(-0.035, 0.035))), home[1]);
                    scheduleWander(entry);
                }, rand(NUDGE_MIN, NUDGE_MAX));
                return;
            }
            if (entry.place !== 'wander') return;
            var stay = entry.visit === 'sofa' ? rand(SOFA_STAY_MIN, SOFA_STAY_MAX) : rand(PAUSE_MIN, PAUSE_MAX);
            entry.timer = setTimeout(function () {
                if (destroyed) return;
                if (!entry.acting && focusedId !== entry.pet.id && entry.place === 'wander' && !moving(entry)) wanderStep(entry);
                scheduleWander(entry);
            }, stay);
        }

        /** Rozmieszcza pupili wg potrzeb (albo wg układu widgetu). */
        function layout(instant) {
            layoutWidth = width();
            if (compact) {
                var slot = 0;
                order.forEach(function (id) {
                    var e = entries[id];
                    if (id === mainId) e.home = COMPACT_MAIN;
                    else e.home = COMPACT_SLOTS[slot++] || COMPACT_SLOTS[COMPACT_SLOTS.length - 1];
                    e.el.classList.toggle('is-main', id === mainId);
                    e.el.classList.toggle('is-back', id !== mainId);
                    if (e.x == null || instant) place(e, e.home[0], e.home[1], true);
                    else place(e, e.home[0], e.home[1]);
                    scheduleWander(e);
                });
                placeBubble();
                return;
            }
            // Kolejność rozstawiania: wybrany (fokus) → pupile przy miejscach potrzeb → spacerowicze (najbardziej
            // elastyczni). Kolizje liczone tylko z już rozstawionymi w tym przebiegu (`done`).
            var rank = function (id) { return id === focusedId ? 0 : (entries[id].place === 'wander' ? 2 : 1); };
            var seq = order.slice().sort(function (a, b) { return rank(a) - rank(b) || order.indexOf(a) - order.indexOf(b); });
            var done = {};
            var box = petBox();
            seq.forEach(function (id) {
                var e = entries[id];
                var target;
                if (e.place !== 'wander') e.visit = null;
                // Zostaje na miejscu, jeśli to wciąż to samo zajęcie i nikt z rozstawionych na nim nie stoi
                // (miejsce na kanapie jest jego z rezerwacji)
                var keep = e.x != null && e.spotFor === e.place && id !== focusedId &&
                    (e.seat >= 0 || sepAt(e, e.x, e.y, obstacles(e, done), box) >= 1);
                e.spotFor = id === focusedId ? null : e.place;
                done[id] = true;
                if (keep && !instant && moving(e)) {
                    // W drodze na to samo miejsce — niech dojdzie (pozę ustawi po dojściu)
                    scheduleWander(e);
                    return;
                }
                var pose = e.visit ? e.goalPose || e.pose : e.pose;      // wizyta: poza z kanapy / przy zabawkach
                if (id === focusedId) {
                    e.visit = null;
                    target = { x: FOCUS_SPOT[0], y: FOCUS_SPOT[1], pose: e.pose };
                } else if (keep) {
                    target = (e.seat >= 0 && seatTarget(e.seat, pose)) || { x: e.x, y: e.y, lift: e.lift, seat: e.seat, pose: pose };
                } else if (e.place === 'wander') {
                    e.visit = null;
                    var spot = freeWanderSpot(e, done) || [e.x, e.y];
                    target = { x: spot[0], y: spot[1], pose: e.pose };
                } else {
                    target = freePlaceSpot(e, e.place, done);
                }
                moveTo(e, target, { instant: instant || e.x == null, run: id === focusedId });
                scheduleWander(e);
            });
        }

        function placeBubble() {
            if (!compact) return;
            var main = mainId != null && entries[mainId];
            var text = main ? NEED_BUBBLE[main.need] : '';
            bubble.hidden = !text;
            if (!text) return;
            if (bubble.textContent !== text) bubble.textContent = text;
            bubble.style.left = (main.x * 100).toFixed(2) + '%';
        }

        function labelFor(pet, need) {
            var name = pet.name || 'Pupil';
            var state = NEED_LABEL[need] || '';
            if (!interactive) return name + (state ? ' — ' + state : '') + '. Przejdź do domku';
            return name + (state ? ' — ' + state : '');
        }

        function applyPet(entry, pet) {
            entry.pet = pet;
            var need = needOf(pet);
            var behavior = BEHAVIOR[need] || BEHAVIOR.happy;
            var changed = need !== entry.need;
            entry.need = need;
            entry.place = behavior[0];
            entry.pose = behavior[1];
            entry.el.setAttribute('data-need', need);
            entry.el.setAttribute('aria-label', labelFor(pet, need));
            if (entry.name) entry.name.textContent = pet.name || '';
            if (entry.rig) {
                entry.rig.update({ species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: pet.asleep });
                if (typeof entry.rig.setNeed === 'function') entry.rig.setNeed(need);
                // Widget: poza od razu; pełny pokój: poza miejsca po dojściu (moveTo/place), w drodze stoi
                if (compact && typeof entry.rig.setPose === 'function') entry.rig.setPose(entry.pose);
            }
            return changed;
        }

        function createEntry(pet) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'pet-room__pet';
            btn.setAttribute('data-pet-id', String(pet.id));
            var flip = document.createElement('span');
            flip.className = 'pet-room__body';
            btn.appendChild(flip);
            // Klikalny jest tylko obszar przy stopach (~55% × 80%), nie całe kwadratowe pudełko — inaczej
            // przezroczysty róg pupila z przodu zabiera kliknięcia temu za nim (pet-room.css)
            var hitArea = document.createElement('span');
            hitArea.className = 'pet-room__hit';
            hitArea.setAttribute('aria-hidden', 'true');
            btn.appendChild(hitArea);
            var name = null;
            if (!compact) {
                name = document.createElement('span');
                name.className = 'pet-room__name';
                name.setAttribute('aria-hidden', 'true');
                btn.appendChild(name);
            }
            layer.appendChild(btn);
            var need = needOf(pet);
            var behavior = BEHAVIOR[need] || BEHAVIOR.happy;
            var entry = {
                pet: pet, el: btn, flip: flip, rig: null, name: name, need: null, pose: 'stand', poseNow: behavior[1],
                x: null, y: null, lift: 0, seat: -1, visit: null, place: 'wander', acting: 0, timer: 0, arrive: 0
            };
            if (window.PetRig) {
                entry.rig = window.PetRig.mount(flip, {
                    species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: pet.asleep,
                    size: 'mini', idle: !compact, need: need, pose: behavior[1]
                });
            }
            applyPet(entry, pet);
            return entry;
        }

        function destroyEntry(id) {
            var e = entries[id];
            if (!e) return;
            clearTimeout(e.timer);
            clearTimeout(e.arrive);
            if (e.rig) e.rig.destroy();
            if (e.el.parentNode) e.el.parentNode.removeChild(e.el);
            delete entries[id];
        }

        function visiblePets(pets) {
            var list = (pets || []).filter(function (p) { return p && !p.hospital; });
            if (!compact) return list.slice(0, MAX_PETS);
            // Widget: główny + do 4 pozostałych (kolejność ze stanu)
            var main = list.filter(function (p) { return p.id === mainId; })[0] || null;
            if (!main && list.length) {
                main = list[0];
            }
            var rest = list.filter(function (p) { return p !== main; });
            more.hidden = rest.length <= COMPACT_BACK;
            more.textContent = rest.length > COMPACT_BACK ? '+' + (rest.length - COMPACT_BACK) : '';
            if (!more.hidden) more.setAttribute('aria-label', 'i jeszcze ' + (rest.length - COMPACT_BACK));
            return main ? [main].concat(rest.slice(0, COMPACT_BACK)) : [];
        }

        room.update = function (pets, o) {
            if (destroyed) return room;
            o = o || {};
            var prevMain = mainId;
            if (o.night != null) night = !!o.night;
            if (o.mainPetId !== undefined) mainId = o.mainPetId;
            el.classList.toggle('is-night', night);
            var list = visiblePets(pets);
            if (compact && list.length && (mainId == null || !list.some(function (p) { return p.id === mainId; }))) mainId = list[0].id;
            var seen = {};
            var relayout = false;
            list.forEach(function (pet) {
                seen[pet.id] = true;
                if (entries[pet.id]) {
                    if (applyPet(entries[pet.id], pet)) relayout = true;
                } else {
                    entries[pet.id] = createEntry(pet);
                    relayout = true;
                }
            });
            Object.keys(entries).forEach(function (id) {
                if (!seen[id]) {
                    destroyEntry(id);
                    relayout = true;
                    if (String(focusedId) === id) focusedId = null;
                }
            });
            var nextOrder = list.map(function (p) { return p.id; });
            if (nextOrder.join(',') !== order.join(',')) relayout = true;
            if (compact && mainId !== prevMain) relayout = true;     // nowy główny pupil widgetu
            order = nextOrder;
            el.classList.toggle('has-focus', focusedId != null && !!entries[focusedId]);
            if (relayout) layout(false);
            else if (compact) placeBubble();
            return room;
        };

        room.focus = function (id) {
            if (destroyed) return room;
            focusedId = id != null && entries[id] ? id : null;
            order.forEach(function (pid) {
                var e = entries[pid];
                e.el.classList.toggle('is-focused', pid === focusedId);
                e.el.classList.toggle('is-dimmed', focusedId != null && pid !== focusedId);
                if (pid === focusedId) e.el.setAttribute('aria-pressed', 'true');
                else e.el.removeAttribute('aria-pressed');
            });
            el.classList.toggle('has-focus', focusedId != null);
            layout(false);
            return room;
        };

        function withRig(id, fn) {
            var e = entries[id];
            if (!e || !e.rig || destroyed) return Promise.resolve();
            e.acting += 1;
            var p;
            try { p = Promise.resolve(fn(e.rig)); } catch (err) { p = Promise.resolve(); }
            return p.then(function () { e.acting = Math.max(0, e.acting - 1); }, function () { e.acting = Math.max(0, e.acting - 1); });
        }

        room.pat = function (id) {
            return withRig(id, function (rig) {
                return typeof rig.pat === 'function' ? rig.pat() : rig.playAction('pat');
            });
        };

        room.playAction = function (id, action, variant) {
            return withRig(id, function (rig) {
                return variant ? rig.playAction(action, { variant: variant }) : rig.playAction(action);
            });
        };

        room.petButton = function (id) {
            return entries[id] ? entries[id].el : null;
        };

        room.destroy = function () {
            if (destroyed) return;
            Object.keys(entries).forEach(destroyEntry);
            destroyed = true;
            clearTimeout(resizeTimer);
            if (resizeObs) resizeObs.disconnect();
            else window.removeEventListener('resize', checkNarrow);
            if (el.parentNode) el.parentNode.removeChild(el);
        };

        el.addEventListener('click', function (e) {
            var btn = e.target.closest('.pet-room__pet');
            if (!btn || !el.contains(btn)) return;
            var id = parseInt(btn.getAttribute('data-pet-id'), 10);
            if (typeof opts.onPetClick === 'function') opts.onPetClick(id);
        });

        container.appendChild(el);
        var resizeObs = null;
        if (window.ResizeObserver) {
            resizeObs = new ResizeObserver(checkNarrow);
            resizeObs.observe(el);
        } else {
            window.addEventListener('resize', checkNarrow);
        }
        checkNarrow();
        room.update(opts.pets || [], { night: night, mainPetId: mainId });
        layout(true);
        return room;
    }

    window.PetRoom = { mount: mount };
})();
