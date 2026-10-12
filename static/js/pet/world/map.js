/**
 * Świat pupili — scena „mapa” (spec v3 §3.2): plansza z lotu ptaka (szkic „A. Mapa-plansza”).
 *
 * Ilustracja to kodowane SVG w dwóch wariantach (poziomy i pionowy — przełącza CSS wg proporcji sceny),
 * a miejsca to zwykłe linki <a data-scene-link> nałożone na ilustrację (cel dotyku ≥ 44 px, fokus,
 * aria-label ze stanem). Znaczki nad miejscami liczone z JSON-u stanu; noc z `state.night.is_night`.
 * Pełny ekran (spec v3.1 §3.5): plansza mieści się w scenie właściwej (proporcje zachowane), a niebo,
 * horyzont i trawa wychodzą poza viewBox (overflow: visible) aż do krawędzi sceny.
 * Pupil w oknie domku (feedback Konrada): co jakiś czas w jednym z okien wychyla się towarzysz i macha
 * (maluch jeszcze nie umie — kołysze się); śpiący drzemie chwilę w oświetlonym oknie. Klik = domek z jego panelem.
 * Rejestruje się w window.PetsWorld.scenes.mapa — router (pets.js) woła create/enter/leave/render.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.mapa) return;

    var PLACES = [
        { scene: 'szpital', label: 'Szpital' },
        { scene: 'domek', label: 'Domek' },
        { scene: 'warsztat', label: 'Warsztat' },
        { scene: 'ogrod', label: 'Ogród wspomnień' }
    ];
    var NEEDY_MOODS = ['glodny', 'smutny', 'brudny', 'znudzony'];

    // Pupil w oknie domku — rytm w ms (losowo z przedziałów); OUT = czas chowania z CSS (transition) z zapasem
    var PEEK = {
        first: [3000, 6000],        // pierwsze pojawienie po wejściu na mapę (i po powrocie do karty)
        gap: [12000, 30000],        // kolejne
        gapSleep: [20000, 40000],   // śpiący zagląda rzadziej
        stay: 3600,
        staySleep: 5200,
        waves: [650, 2050],         // dwa machnięcia (gest trwa 1,2 s)
        out: 1300
    };

    var BADGE_ICON = {
        cross: '<path d="M9.5 4h5v5.5H20v5h-5.5V20h-5v-5.5H4v-5h5.5z"/>',
        alert: '<path d="M12 4.5v9.5"/><circle cx="12" cy="19" r="1.4"/>',
        heart: '<path d="M12 20s-7.5-4.6-9.2-9.4A4.9 4.9 0 0 1 12 7.1a4.9 4.9 0 0 1 9.2 3.5C19.5 15.4 12 20 12 20z"/>',
        candle: '<path class="b-flame" d="M12 2c2.2 2.6 3.4 4.2 3.4 5.9a3.4 3.4 0 0 1-6.8 0C8.6 6.2 9.8 4.6 12 2z"/><rect x="8.6" y="12.5" width="6.8" height="9.5" rx="1.4"/>'
    };

    // --- ilustracja ------------------------------------------------------------------------

    // Elementy wspólne obu wariantów (współrzędne lokalne ze szkicu; każdy wariant skaluje je sam)
    var HOSPITAL =
        '<rect x="0" y="16" width="62" height="40" rx="4" fill="#ffffff" stroke="#c9d6e8"/>' +
        '<path d="M-4 18 L31 0 L66 18 Z" fill="#7fb3ea"/>' +
        '<rect x="28" y="20" width="6" height="20" rx="1" fill="#ff6b7d"/><rect x="21" y="27" width="20" height="6" rx="1" fill="#ff6b7d"/>' +
        '<rect x="26" y="42" width="10" height="14" rx="2" fill="#9cc3ee"/>' +
        '<rect x="6" y="38" width="10" height="9" rx="1.5" class="map-win" fill="#e3f0ff" stroke="#c9d6e8"/>' +
        '<rect x="46" y="38" width="10" height="9" rx="1.5" class="map-win" fill="#e3f0ff" stroke="#c9d6e8"/>';
    var HOUSE =
        '<ellipse cx="35" cy="81" rx="44" ry="5" fill="#000" opacity=".08"/>' +
        '<rect x="0" y="30" width="70" height="50" rx="4" fill="#ffd9e6" stroke="#f3b6cb"/>' +
        '<path d="M-8 32 L35 2 L78 32 Z" fill="#ff8fab"/>' +
        '<rect x="52" y="6" width="8" height="16" fill="#c4708a"/>' +
        '<rect x="28" y="54" width="14" height="26" rx="6" fill="#c98b5c"/><circle cx="38" cy="68" r="1.3" fill="#7a4a2a"/>' +
        // Okna 18×15 (dawniej 14×12): wygląda z nich pupil — wnętrza muszą się zgadzać z .pets-map__peek w CSS
        '<rect x="5" y="39" width="18" height="15" rx="2.5" class="map-win" fill="#fff6c9" stroke="#e8c96b"/>' +
        '<rect x="47" y="39" width="18" height="15" rx="2.5" class="map-win" fill="#fff6c9" stroke="#e8c96b"/>' +
        '<g class="map-glow"><circle cx="14" cy="46.5" r="13" fill="#ffd36b" opacity=".35"/><circle cx="56" cy="46.5" r="13" fill="#ffd36b" opacity=".35"/></g>';
    var WORKSHOP =
        '<rect x="0" y="14" width="56" height="38" rx="3" fill="#c99a6b" stroke="#a87b4f"/>' +
        '<path d="M-4 16 L28 0 L60 16 Z" fill="#8a5a3b"/>' +
        '<circle cx="28" cy="32" r="9" fill="none" stroke="#f3e2c3" stroke-width="3"/><circle cx="28" cy="32" r="3" fill="#f3e2c3"/>' +
        '<path d="M28 20v3M28 41v3M16 32h3M37 32h3" stroke="#f3e2c3" stroke-width="2.4" stroke-linecap="round"/>';
    var GARDEN =
        '<rect x="0" y="22" width="84" height="4" fill="#d9b38a"/>' +
        '<g fill="#d9b38a"><rect x="4" y="12" width="4" height="16"/><rect x="24" y="12" width="4" height="16"/><rect x="56" y="12" width="4" height="16"/><rect x="76" y="12" width="4" height="16"/></g>' +
        '<path d="M36 22 v-10 a6 6 0 0 1 12 0 v10 Z" fill="#cfd4dc" stroke="#aab2bf" stroke-width=".8"/>' +
        '<circle cx="14" cy="8" r="4" fill="#ff9ec4"/><circle cx="66" cy="8" r="4" fill="#ffd36b"/><circle cx="20" cy="4" r="3" fill="#b99cff"/>' +
        '<circle cx="62" cy="3" r="2.6" fill="#ff9ec4"/>';

    function tree(x, y, r, c) {
        return '<g><rect x="' + (x - r * 0.12) + '" y="' + (y + r * 0.6) + '" width="' + (r * 0.24) + '" height="' + (r * 0.6) + '" fill="#9b7653"/>' +
            '<circle cx="' + x + '" cy="' + y + '" r="' + r + '" fill="' + (c || '#5fb85a') + '"/>' +
            '<circle cx="' + (x - r * 0.3) + '" cy="' + (y - r * 0.3) + '" r="' + (r * 0.35) + '" fill="#ffffff" opacity=".18"/></g>';
    }

    function flowers(list) {
        var colors = ['#ff9ec4', '#ffd36b', '#b99cff', '#ffffff'];
        return list.map(function (p, i) {
            return '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="' + (p[2] || 3) + '" fill="' + colors[i % colors.length] + '"/>';
        }).join('');
    }

    function stars(list) {
        return list.map(function (p, i) {
            return '<circle class="map-star map-star--' + (i % 3) + '" cx="' + p[0] + '" cy="' + p[1] + '" r="' + (p[2] || 1.4) + '" fill="#fff8d6"/>';
        }).join('');
    }

    function sky(w, h, id) {
        return '<g class="map-sky">' +
            '<rect width="' + w + '" height="' + h + '" fill="url(#mapSkyDay' + id + ')" class="map-day"/>' +
            '<rect width="' + w + '" height="' + h + '" fill="url(#mapSkyNight' + id + ')" class="map-night"/>' +
            '<g class="map-day"><g class="map-sun"><circle cx="' + (w - 54) + '" cy="30" r="17" fill="#ffe27a"/><circle cx="' + (w - 54) + '" cy="30" r="25" fill="#ffe27a" opacity=".25"/></g>' +
            '<ellipse class="map-cloud" cx="72" cy="30" rx="30" ry="9" fill="#ffffff"/><ellipse class="map-cloud" cx="92" cy="25" rx="18" ry="8" fill="#ffffff"/>' +
            '<ellipse class="map-cloud" cx="' + (w * 0.55) + '" cy="22" rx="22" ry="7" fill="#ffffff" opacity=".9"/></g>' +
            '<g class="map-night"><circle cx="' + (w - 54) + '" cy="30" r="15" fill="#fff4c2"/><circle cx="' + (w - 47) + '" cy="25" r="13" fill="#1d2550"/>' +
            stars([[30, 18], [70, 36, 1.8], [118, 14], [160, 40], [210, 22, 1.8], [260, 12], [w * 0.62, 34], [w * 0.7, 14, 1.8], [w - 110, 44], [w - 20, 18]]) +
            '</g></g>';
    }

    // Osobne id gradientów per wariant: gradient z <svg> ukrytego przez display:none nie maluje się w drugim.
    // Warianty „X” w układzie użytkownika: te same przejścia na tej samej wysokości, a poza planszą kolor brzegu.
    function defs(id, grassEnd) {
        return '<defs>' +
            '<linearGradient id="mapGrass' + id + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#bfe8a6"/><stop offset="1" stop-color="#8fd27a"/></linearGradient>' +
            '<linearGradient id="mapSkyDay' + id + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#bfe3ff"/><stop offset="1" stop-color="#e6f5ff"/></linearGradient>' +
            '<linearGradient id="mapSkyNight' + id + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#121a3d"/><stop offset="1" stop-color="#2b3470"/></linearGradient>' +
            '<linearGradient id="mapGrassX' + id + '" gradientUnits="userSpaceOnUse" x1="0" y1="40" x2="0" y2="' + grassEnd + '"><stop offset="0" stop-color="#bfe8a6"/><stop offset="1" stop-color="#8fd27a"/></linearGradient>' +
            '<linearGradient id="mapSkyDayX' + id + '" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="60"><stop offset="0" stop-color="#bfe3ff"/><stop offset="1" stop-color="#e6f5ff"/></linearGradient>' +
            '<linearGradient id="mapSkyNightX' + id + '" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="60"><stop offset="0" stop-color="#121a3d"/><stop offset="1" stop-color="#2b3470"/></linearGradient>' +
            '</defs>';
    }

    // Tło poza viewBoxem (widoczne dzięki overflow: visible) — niebo, pas horyzontu i trawa do krawędzi sceny.
    // yL / yR: wysokość horyzontu na lewym i prawym brzegu planszy (z jej ścieżki wzgórz).
    var BLEED = 4000;
    function bleed(w, h, id, yL, yR) {
        return '<g class="map-bleed">' +
            '<rect x="' + (-BLEED) + '" y="40" width="' + (w + 2 * BLEED) + '" height="' + (h - 40 + BLEED) + '" fill="url(#mapGrassX' + id + ')"/>' +
            '<rect x="' + (-BLEED) + '" y="' + (-BLEED) + '" width="' + (w + 2 * BLEED) + '" height="' + (BLEED + 60) + '" fill="url(#mapSkyDayX' + id + ')" class="map-day"/>' +
            '<rect x="' + (-BLEED) + '" y="' + (-BLEED) + '" width="' + (w + 2 * BLEED) + '" height="' + (BLEED + 60) + '" fill="url(#mapSkyNightX' + id + ')" class="map-night"/>' +
            '<rect x="' + (-BLEED) + '" y="' + yL + '" width="' + BLEED + '" height="' + (70 - yL) + '" fill="#a9de8f"/>' +
            '<rect x="' + w + '" y="' + yR + '" width="' + BLEED + '" height="' + (70 - yR) + '" fill="#a9de8f"/>' +
            '</g>';
    }

    // Pora dnia (ciemny motyw = wieczór, noc w grze = noc): cień na ziemi od linii wzgórz w dół (niebo ma własne
    // kolory), mnożony w CSS (mix-blend-mode), żeby zieleń i budynki ciemniały bez szarego welonu. Kontur = ścieżka
    // wzgórz wariantu (od x=0, y=yL do x=w, y=yR), poza planszą poziomo jak pas horyzontu w bleed(); drugi kontur
    // (od y=60, dołu pasa nieba) łapie trawę widoczną w dolinkach wzgórz. Jedna ścieżka = każdy piksel raz.
    function nightTint(w, h, yL, yR, hills) {
        return '<path class="map-night-tint" d="M' + (-BLEED) + ' ' + yL + ' H0 ' + hills + ' H' + (w + BLEED) +
            ' V' + (h + BLEED) + ' H' + (-BLEED) + ' Z M' + (-BLEED) + ' 60 H' + (w + BLEED) + ' V' + (h + BLEED) +
            ' H' + (-BLEED) + ' Z"/>';
    }

    // Zapalone okna nad cieniem (wieczór i noc): te same okna co w HOSPITAL / HOUSE, z ciepłą poświatą.
    // `house` / `hospital` = przekształcenie budynku w układzie planszy (jak jego <g> w wariancie).
    var HOUSE_LIGHTS =
        '<circle cx="14" cy="46.5" r="13" class="map-lamp-glow"/><circle cx="56" cy="46.5" r="13" class="map-lamp-glow"/>' +
        '<rect x="5" y="39" width="18" height="15" rx="2.5" class="map-lit" stroke="#e8c96b"/>' +
        '<rect x="47" y="39" width="18" height="15" rx="2.5" class="map-lit" stroke="#e8c96b"/>';
    var HOSPITAL_LIGHTS =
        '<circle cx="11" cy="42.5" r="8" class="map-lamp-glow"/><circle cx="51" cy="42.5" r="8" class="map-lamp-glow"/>' +
        '<rect x="6" y="38" width="10" height="9" rx="1.5" class="map-lit" stroke="#d9b45a"/>' +
        '<rect x="46" y="38" width="10" height="9" rx="1.5" class="map-lit" stroke="#d9b45a"/>';
    function lights(house, hospital) {
        return '<g class="map-lights"><g transform="' + hospital + '">' + HOSPITAL_LIGHTS + '</g>' +
            '<g transform="' + house + '">' + HOUSE_LIGHTS + '</g></g>';
    }

    // Wariant poziomy 640×460: ilustracja ze szkicu ×2 pod pasem nieba
    var LANDSCAPE =
        '<svg class="pets-map__art pets-map__art--wide" viewBox="0 0 640 460" preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">' + defs('W', 460) +
        bleed(640, 460, 'W', 60, 48) +
        '<rect y="40" width="640" height="420" fill="url(#mapGrassW)"/>' +
        '<g transform="translate(0,20) scale(2)">' +
        '<path d="M60 120 C110 100, 120 140, 160 125 S 230 95, 265 120 M160 125 C 160 150, 150 170, 160 195" stroke="#f1dfb4" stroke-width="14" fill="none" stroke-linecap="round"/>' +
        '<path d="M60 120 C110 100, 120 140, 160 125 S 230 95, 265 120 M160 125 C 160 150, 150 170, 160 195" stroke="#e6cf9b" stroke-width="1" stroke-dasharray="2 6" fill="none"/>' +
        tree(22, 46, 16) + tree(300, 190, 14) + tree(296, 40, 12, '#6cc466') + tree(30, 196, 12, '#6cc466') + tree(108, 196, 9, '#58ad53') + tree(226, 34, 8, '#58ad53') +
        flowers([[90, 60], [96, 66, 2.4], [240, 160], [246, 166, 2.4], [70, 170], [214, 196], [276, 74, 2.4], [130, 34, 2.4]]) +
        '<g transform="translate(28,70)">' + HOSPITAL + '</g>' +
        '<g transform="translate(126,42)">' + HOUSE + '</g>' +
        '<g transform="translate(236,72)">' + WORKSHOP + '</g>' +
        '<g transform="translate(118,160)">' + GARDEN + '</g>' +
        '</g>' +
        sky(640, 60, 'W') +
        '<path d="M0 60 Q80 40 160 56 T320 50 T480 58 T640 48 V70 H0 Z" fill="#a9de8f"/>' +
        nightTint(640, 460, 60, 48, 'Q80 40 160 56 T320 50 T480 58 T640 48') +
        lights('translate(252,104) scale(2)', 'translate(56,160) scale(2)') +
        '</svg>';

    // Wariant pionowy 360×640 (telefon): miejsca jedno pod drugim przy krętej ścieżce
    var PORTRAIT =
        '<svg class="pets-map__art pets-map__art--tall" viewBox="0 0 360 640" preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">' + defs('T', 640) +
        bleed(360, 640, 'T', 60, 56) +
        '<rect y="40" width="360" height="600" fill="url(#mapGrassT)"/>' +
        '<path d="M180 236 C 180 300, 90 300, 92 360 C 94 420, 266 400, 266 450 C 266 500, 180 500, 180 560" stroke="#f1dfb4" stroke-width="26" fill="none" stroke-linecap="round"/>' +
        '<path d="M180 236 C 180 300, 90 300, 92 360 C 94 420, 266 400, 266 450 C 266 500, 180 500, 180 560" stroke="#e6cf9b" stroke-width="2" stroke-dasharray="4 12" fill="none"/>' +
        tree(34, 120, 22) + tree(326, 140, 20, '#6cc466') + tree(320, 290, 16) + tree(36, 470, 18, '#6cc466') + tree(326, 590, 20) + tree(40, 610, 14, '#58ad53') +
        flowers([[60, 200], [66, 208, 2.6], [300, 220], [150, 300], [230, 330, 2.6], [40, 400], [320, 520], [120, 500, 2.6], [250, 610]]) +
        '<g transform="translate(110,72) scale(2)">' + HOUSE + '</g>' +
        '<g transform="translate(30,286) scale(1.8)">' + HOSPITAL + '</g>' +
        '<g transform="translate(212,380) scale(1.8)">' + WORKSHOP + '</g>' +
        '<g transform="translate(105,540) scale(1.8)">' + GARDEN + '</g>' +
        sky(360, 60, 'T') +
        '<path d="M0 60 Q60 42 120 56 T240 50 T360 56 V70 H0 Z" fill="#a9de8f"/>' +
        nightTint(360, 640, 60, 56, 'Q60 42 120 56 T240 50 T360 56') +
        lights('translate(110,72) scale(2)', 'translate(30,286) scale(1.8)') +
        '</svg>';

    // --- pupil w oknie domku ------------------------------------------------------------------

    function rand(range) {
        return range[0] + Math.random() * (range[1] - range[0]);
    }

    /** Towarzysz (state.companion.pet_id — backend pomija szpital), a bez niego pierwszy żywy poza szpitalem. */
    function peekPetOf(state) {
        var pets = ((state && state.pets) || []).filter(function (p) { return !p.hospital; });
        var id = state && state.companion && state.companion.pet_id;
        for (var i = 0; i < pets.length; i++) if (pets[i].id === id) return pets[i];
        return pets[0] || null;
    }

    /**
     * Okno domku z pupilem: <a> nad wnętrzem okna (lewego albo prawego, losowo), w nim przycinające okienko
     * i jeden rig. Rig powstaje przy pierwszym pojawieniu i ginie w leave() i przy schowaniu karty (z nim jego
     * timery mrugania);
     * między pojawieniami element jest ukryty (display: none — animacje rigu nie liczą się w tle).
     * Karta przeglądarki w tle = pauza (bez timerów); powrót = pojawienie po kilku sekundach.
     */
    function createPeek(ctx, board) {
        var u = ctx.u;
        var link = u.el('a', 'pets-map__peek');
        var win = u.el('span', 'pets-map__peek-win');
        var holder = u.el('span', 'pets-map__peek-pet');
        // Łapka rigu chowa się w małym oknie za głową — machająca łapka mapy leży nad pupilem (kolory z rigu)
        var paw = u.el('span', 'pets-map__peek-paw');
        paw.innerHTML = '<svg viewBox="0 0 40 70" aria-hidden="true" focusable="false">' +
            '<ellipse class="paw-arm" cx="20" cy="42" rx="12.5" ry="28"/><ellipse class="paw-pad" cx="20" cy="23" rx="6.5" ry="5.5"/></svg>';
        // Skrót myszą/dotykiem do panelu pupila — dostępna droga to link „Domek” (pupil znika po 3–5 s)
        link.setAttribute('aria-hidden', 'true');
        link.setAttribute('tabindex', '-1');
        link.dataset.sceneLink = 'domek';
        link.hidden = true;
        win.appendChild(holder);
        win.appendChild(paw);
        link.appendChild(win);
        board.appendChild(link);

        var rig = null, petId = null, shown = false, hover = false, active = false, lastState = null;
        var timers = { next: 0, hide: 0, out: 0, wave0: 0, wave1: 0, unwave: 0 };

        function clear(keys) {
            (keys || Object.keys(timers)).forEach(function (k) {
                clearTimeout(timers[k]);
                timers[k] = 0;
            });
        }

        function schedule(range) {
            clear(['next']);
            if (!active || document.visibilityState === 'hidden') return;
            timers.next = setTimeout(show, rand(range));
        }

        // Maluch jeszcze nie umie machać (gesty stadiów, spec §2.7) — kołysze się. Gest odmawia sam przy
        // ograniczonym ruchu i w stanie innym niż spokojny (smutek, choroba) — wtedy łapka też się nie pokazuje.
        function wave(stage) {
            if (!rig || !shown) return;
            var list = (window.PetRig.GESTURES || {})[stage] || [];
            if (list.indexOf('wave') < 0) {
                rig.gesture('sway');
                return;
            }
            if (!rig.gesture('wave')) return;
            link.classList.remove('is-waving');
            void link.offsetWidth;
            link.classList.add('is-waving');
            clearTimeout(timers.unwave);
            timers.unwave = setTimeout(function () {
                timers.unwave = 0;
                link.classList.remove('is-waving');
            }, 1250);
        }

        function syncPaw() {
            ['--rig-base', '--rig-light', '--rig-line'].forEach(function (v) {
                win.style.setProperty(v, rig.el.style.getPropertyValue(v));
            });
        }

        function show() {
            timers.next = 0;
            var pet = window.PetRig ? peekPetOf(lastState) : null;
            if (!pet) {   // brak żywych pupili poza szpitalem: nic się nie pojawia, sprawdzamy dalej
                schedule(PEEK.gap);
                return;
            }
            var need = window.PetRig.needOf(pet);
            var sleepy = need === 'sleep';
            var opts = { species: pet.species, stage: pet.stage, stars: 0, need: need, pose: 'stand', size: 'mini', idle: false };
            clear(['out']);
            link.hidden = false;
            if (rig) rig.update(opts);
            else rig = window.PetRig.mount(holder, opts);
            syncPaw();
            petId = pet.id;
            link.href = ctx.href('domek', { pupil: pet.id });
            link.dataset.pupil = pet.id;
            link.dataset.stage = pet.stage;
            link.classList.toggle('pets-map__peek--r', Math.random() < 0.5);
            link.classList.toggle('is-sleepy', sleepy);
            void link.offsetWidth;   // start przejścia ze stanu ukrytego (świeżo odkryty element)
            link.classList.add('is-shown');
            shown = true;
            if (!sleepy) {
                timers.wave0 = setTimeout(function () { wave(pet.stage); }, PEEK.waves[0]);
                timers.wave1 = setTimeout(function () { wave(pet.stage); }, PEEK.waves[1]);
            }
            timers.hide = setTimeout(hideLater, sleepy ? PEEK.staySleep : PEEK.stay);
        }

        // Kursor nad pupilem = zostaje, póki go nie zabierzesz (cel nie ucieka spod myszy)
        function hideLater() {
            timers.hide = 0;
            if (hover) {
                timers.hide = setTimeout(hideLater, 800);
                return;
            }
            var sleepy = link.classList.contains('is-sleepy');
            hide(false);
            schedule(sleepy ? PEEK.gapSleep : PEEK.gap);
        }

        function hide(instant) {
            clear(['hide', 'wave0', 'wave1', 'unwave', 'out']);
            shown = false;
            hover = false;
            link.classList.remove('is-shown', 'is-waving');
            if (instant) {
                link.hidden = true;
                return;
            }
            timers.out = setTimeout(function () {
                timers.out = 0;
                link.hidden = true;
            }, PEEK.out);
        }

        // Rig z własnym timerem mrugania żyje tylko, gdy mapa jest widoczna (wyjście ze sceny, karta w tle)
        function dropRig() {
            if (rig) rig.destroy();
            rig = null;
            petId = null;
        }

        function onVisibility() {
            if (document.visibilityState === 'hidden') {
                clear();
                hide(true);
                dropRig();
            } else if (active && !timers.next && !shown) {
                schedule(PEEK.first);
            }
        }

        link.addEventListener('mouseenter', function () { if (shown) hover = true; });
        link.addEventListener('mouseleave', function () { hover = false; });

        return {
            enter: function () {
                clear();
                hide(true);
                active = true;
                document.addEventListener('visibilitychange', onVisibility);
                schedule(PEEK.first);
            },
            leave: function () {
                active = false;
                document.removeEventListener('visibilitychange', onVisibility);
                clear();
                hide(true);
                dropRig();
            },
            render: function (state) {
                lastState = state;
                // Pokazany pupil przestał się nadawać (szpital, zmiana towarzysza) — chowa się od razu
                if (!shown) return;
                var pet = peekPetOf(state);
                if (!pet || pet.id !== petId) {
                    hide(false);
                    schedule(PEEK.gap);
                }
            }
        };
    }

    // --- scena -----------------------------------------------------------------------------

    function create(ctx, host) {
        var u = ctx.u;
        var stage = u.el('div', 'pets-stage pets-map__stage');
        var wrap = u.el('div', 'pets-map');
        var board = u.el('div', 'pets-map__board');
        board.innerHTML = LANDSCAPE + PORTRAIT;
        var places = {};
        PLACES.forEach(function (p) {
            var a = u.el('a', 'pets-map__place pets-map__place--' + p.scene);
            a.href = ctx.href(p.scene);
            a.dataset.sceneLink = p.scene;
            var badges = u.el('span', 'pets-map__badges');
            badges.setAttribute('aria-hidden', 'true');
            var label = u.el('span', 'pets-map__label', p.label);
            a.appendChild(badges);
            a.appendChild(label);
            board.appendChild(a);
            places[p.scene] = { a: a, badges: badges, label: p.label, sig: null };
        });
        var peek = createPeek(ctx, board);   // po miejscach: pokazany pupil leży nad linkiem domku
        wrap.appendChild(board);
        stage.appendChild(wrap);
        host.appendChild(stage);

        function badge(kind, title) {
            var b = u.el('span', 'pets-map__badge pets-map__badge--' + kind);
            b.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + BADGE_ICON[kind] + '</svg>';
            b.title = title;
            return b;
        }

        function setPlace(scene, list) {
            var place = places[scene];
            var sig = list.map(function (x) { return x[0]; }).join(',');
            if (sig !== place.sig) {
                place.sig = sig;
                place.badges.innerHTML = '';
                list.forEach(function (x) { place.badges.appendChild(badge(x[0], x[1])); });
                place.a.classList.toggle('has-badge', list.length > 0);
            }
            var text = place.label + (list.length ? ' — ' + list.map(function (x) { return x[1]; }).join('; ') : '');
            if (place.a.getAttribute('aria-label') !== text) place.a.setAttribute('aria-label', text);
        }

        function render(state) {
            var pets = state.pets || [];
            var eggs = state.eggs || [];
            var night = !!(state.night && state.night.is_night);
            wrap.classList.toggle('is-night', night);

            var hospital = [];
            if (pets.some(function (p) { return p.hospital || p.mood === 'chory' || p.mood === 'krytyczny'; })) {
                hospital.push(['cross', 'ktoś choruje albo leczy się w szpitalu']);
            }
            if (eggs.some(function (e) { return e.ready; }) || (state.eggs_available || []).length ||
                pets.some(function (p) { return p.hospital && p.hospital.ready; })) {
                hospital.push(['alert', 'coś czeka na Ciebie']);
            }
            setPlace('szpital', hospital);

            var home = [];
            if (pets.some(function (p) { return !p.hospital && NEEDY_MOODS.indexOf(p.mood) >= 0; })) {
                home.push(['heart', 'ktoś potrzebuje opieki']);
            }
            setPlace('domek', home);
            setPlace('warsztat', []);

            var garden = [];
            if ((state.album || []).some(function (a) { return a.status === 'memorial' && a.can_light; })) {
                garden.push(['candle', 'możesz dziś zapalić światełko']);
            }
            setPlace('ogrod', garden);
            peek.render(state);
        }

        return {
            enter: function () {
                wrap.classList.remove('is-zooming');
                wrap.style.removeProperty('--zoom-x');
                wrap.style.removeProperty('--zoom-y');
                peek.enter();
            },
            leave: function () {
                wrap.classList.remove('is-zooming');
                peek.leave();
            },
            render: render,
            /** Zoom w stronę miejsca przed przejściem (300–400 ms, CSS); router wstrzymuje przejście. */
            zoomTo: function (scene) {
                var place = places[scene];
                if (!place) return;
                var b = board.getBoundingClientRect(), r = place.a.getBoundingClientRect();
                if (b.width && b.height) {
                    wrap.style.setProperty('--zoom-x', ((r.left + r.width / 2 - b.left) / b.width * 100).toFixed(1) + '%');
                    wrap.style.setProperty('--zoom-y', ((r.top + r.height / 2 - b.top) / b.height * 100).toFixed(1) + '%');
                }
                wrap.classList.add('is-zooming');
            }
        };
    }

    W.scenes.mapa = {
        title: 'Moje pupile',
        create: create
    };
})();
