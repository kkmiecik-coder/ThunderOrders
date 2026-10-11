/**
 * Gatunki pupili — lustro modules/pets/species.py (slug, name, palette, extras 1:1).
 *
 * parts = kształty SVG warstw rigu (viewBox 0 0 200 200, układ dorosłego):
 *   głowa: elipsa cx100 cy88 rx51 ry44 (szyja ~ y130), oczy x78/122 y95,
 *   ciało: elipsa cx100 cy153 rx34 ry29, ziemia y182.
 * Pola parts (wszystkie opcjonalne — braki uzupełnia pet-rig.js domyślnymi):
 *   ears, earsFront   — uszy (domyślnie ZA czaszką; earsFront: przed nią, np. opadające)
 *   face, nose        — znaczenia na pyszczku, nos ('' = brak nosa)
 *   fringe            — grzywka / czubek / listek / iskierki (nad oczami)
 *   tail, tailO       — ogon i jego punkt obrotu (merdanie)
 *   bodyExtra         — dodatki na ciele (obroża)
 *   feet, arm         — stopy; LEWA łapka (prawa = lustro)
 *   mouth             — {smile, open, frown} zamiast domyślnej buzi „w"
 *   eye               — {iris, pupil, lid} — kolor tęczówki, źrenica, półprzymknięta powieka
 *   ink, line         — kolor kresek (buzia, zamknięte oczy) i konturu (domyślnie palette.dark)
 * Klasy: f-b/f-l/f-d/f-c = wypełnienie base/light/dark/cheek, f-w biały, f-k tęczówka,
 *   o / o2 = kontur, t-o + t-b = ogon kreską (kontur + kolor), s-k = kreska tuszem.
 * Nowy gatunek = nowy wpis tutaj, zero nowej mechaniki.
 */
(function () {
    'use strict';

    // Lustro względem osi x=100 (uszy, łapki, policzki itp.).
    function sym(s) {
        return s + '<g transform="matrix(-1 0 0 1 200 0)">' + s + '</g>';
    }

    var CAT_EARS = sym(
        '<path class="f-b o" d="M53 76Q50 46 59 31Q63 26 68 30Q81 39 93 51Z"/>' +
        '<path class="f-c" d="M60 66Q58 48 63 38Q73 45 83 53Z"/>'
    );
    var WHISKERS = sym('<path class="wh" d="M61 103L47 100M61 108L46 109"/>');
    var CAT_TAIL = '<path class="t-o" d="M126 171C150 173 161 151 153 133C148 122 154 112 164 114"/>' +
        '<path class="t-b" d="M126 171C150 173 161 151 153 133C148 122 154 112 164 114"/>';

    window.PetSpecies = {
        wiewiorka: {
            name: 'Wiewiórka',
            palette: { base: '#F4A261', light: '#FBE3C9', dark: '#C8732F', cheek: '#F7B7A3' },
            extras: ['stripes', 'bushy_tail'],
            parts: {
                ears: sym(
                    '<path class="f-b o" d="M58 70Q54 44 63 31Q68 28 71 32Q80 44 88 55Z"/>' +
                    '<path class="f-l" d="M63 62Q61 47 66 40Q73 47 79 55Z"/>' +
                    '<path class="f-d" d="M63 32Q63 21 69 17Q69 25 72 33Z"/>'
                ),
                face: '<ellipse class="f-l" cx="100" cy="108" rx="21" ry="12.5"/>' +
                    '<path class="f-w o2" d="M97 109.5h6v4.6a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1z"/>',
                fringe: '<path class="f-d" d="M100 45c-4 0-5.5 6-4.5 13 1 6 8 6 9 0 1-7-.5-13-4.5-13z"/>' +
                    sym('<path class="f-d" d="M81 50c-4 2-4.5 8-1.5 12.5 3 4 8 2 7-3-.8-5-2.5-10.5-5.5-9.5z"/>'),
                tail: '<path class="f-b o" d="M116 174C152 184 182 160 180 126C179 100 162 80 140 84C123 87 119 104 132 112C147 120 153 136 142 150C135 158 125 162 116 162Z"/>' +
                    '<path class="f-l" d="M143 94C160 95 171 114 169 133C167 150 157 162 146 168C156 152 159 135 151 121C145 111 135 103 143 94Z"/>',
                tailO: '120px 168px'
            }
        },
        kroliczek: {
            name: 'Króliczek',
            palette: { base: '#F7B6D2', light: '#FDE4EF', dark: '#E58BB5', cheek: '#F48FB1' },
            extras: ['long_ears', 'sparkles'],
            parts: {
                ears: sym(
                    '<g transform="rotate(-9 84 54)"><path class="f-b o" d="M73 58C61 36 62 6 74 3C88 1 92 30 90 57Z"/>' +
                    '<path class="f-l" d="M77 51C70 34 71 14 76 11C83 10 85 30 85 51Z"/></g>'
                ),
                nose: '<path class="f-c o2" d="M96.8 100.6h6.4c0 1.5-1.8 3.2-3.2 3.2s-3.2-1.7-3.2-3.2z"/>',
                fringe: '<path class="sp" d="M38 54l2 5.5 5.5 2-5.5 2-2 5.5-2-5.5-5.5-2 5.5-2z"/>' +
                    '<path class="sp" d="M163 64l1.6 4.4 4.4 1.6-4.4 1.6-1.6 4.4-1.6-4.4-4.4-1.6 4.4-1.6z"/>' +
                    '<path class="sp" d="M150 26l1.3 3.5 3.5 1.3-3.5 1.3-1.3 3.5-1.3-3.5-3.5-1.3 3.5-1.3z"/>',
                tail: '<circle class="f-l o" cx="133" cy="168" r="10.5"/>',
                tailO: '128px 170px',
                feet: '<ellipse class="f-b o" cx="82" cy="177.5" rx="13" ry="7.5"/><ellipse class="f-b o" cx="118" cy="177.5" rx="13" ry="7.5"/>' +
                    '<ellipse class="f-l" cx="80" cy="178.5" rx="6" ry="3.4"/><ellipse class="f-l" cx="120" cy="178.5" rx="6" ry="3.4"/>'
            }
        },
        szczeniak: {
            name: 'Szczeniak',
            palette: { base: '#F6E3B4', light: '#FFF6DE', dark: '#D9BE7A', cheek: '#F5B5A1' },
            extras: ['floppy_ears', 'fringe'],
            parts: {
                earsFront: true,
                ears: sym('<path class="f-d o" d="M66 52C50 47 38 66 39 92C40 108 50 117 57 109C64 100 69 80 70 61Z"/>'),
                face: '<ellipse class="f-l" cx="100" cy="107.5" rx="17" ry="11"/>',
                nose: '<ellipse class="f-k" cx="100" cy="101" rx="4.2" ry="2.9"/>',
                fringe: '<path class="f-l o" d="M77 54C80 42 92 37 100 44C108 37 120 42 123 54C117 59 110 56 107 52C105 59 95 59 93 52C90 57 82 59 77 54Z"/>' +
                    '<path class="f-b o" d="M95 42C93 33 99 27 106 28C101 32 103 38 109 40C105 45 99 46 95 42Z"/>',
                tail: '<path class="f-b o" d="M127 160C140 157 147 147 146 137C152 144 152 161 132 169Z"/>',
                tailO: '128px 165px'
            }
        },
        piesek: {
            name: 'Piesek',
            palette: { base: '#FFFFFF', light: '#FFFFFF', dark: '#D9D9D9', cheek: '#F8BBD0' },
            extras: ['long_floppy_ears'],
            parts: {
                line: '#ADA8BE',
                earsFront: true,
                ears: sym('<path class="f-b o" d="M60 56C38 56 29 98 35 125C39 141 56 141 60 127C64 109 67 80 66 62Z"/>' +
                    '<path class="f-c ck2" d="M54 72C44 80 41 104 44 120C47 128 53 126 55 118C58 104 59 86 57 74Z"/>'),
                nose: '<ellipse class="f-k" cx="100" cy="101" rx="4.4" ry="3"/>',
                fringe: '<path class="tuft" d="M95 46Q98 38 105 40Q101 42 102 47"/>',
                tail: '<path class="t-o" d="M128 163C143 160 147 147 140 140"/><path class="t-b" d="M128 163C143 160 147 147 140 140"/>',
                tailO: '127px 163px'
            }
        },
        kotek: {
            name: 'Kotek',
            palette: { base: '#C9C3E6', light: '#E8E4F5', dark: '#9D94C9', cheek: '#F3A6C4' },
            extras: ['pointy_ears', 'white_muzzle'],
            parts: {
                ears: CAT_EARS,
                face: '<ellipse class="f-w" cx="100" cy="107" rx="18.5" ry="11.5"/>' + WHISKERS,
                nose: '<path class="f-c o2" d="M96.8 100.6h6.4c0 1.5-1.8 3.2-3.2 3.2s-3.2-1.7-3.2-3.2z"/>',
                tail: CAT_TAIL,
                tailO: '126px 170px'
            }
        },
        kurczaczek: {
            name: 'Kurczaczek',
            palette: { base: '#FDE68A', light: '#FFF4C2', dark: '#E3C44A', cheek: '#F9B27A' },
            extras: ['beak', 'crest'],
            parts: {
                nose: '',
                fringe: '<path class="f-b o" d="M90 50C84 40 88 30 95 33C95 23 105 21 107 30C113 26 119 33 112 46C106 50 96 52 90 50Z"/>',
                mouth: {
                    smile: '<path class="beak" d="M91 101.5Q100 95.5 109 101.5Q100 111 91 101.5Z"/>',
                    open: '<path fill="#7A2E3E" d="M93 101Q100 99 107 101L106 106Q100 109 94 106Z"/>' +
                        '<path class="beak" d="M91 100Q100 93.5 109 100Q100 103.5 91 100Z"/>' +
                        '<path class="beak" d="M93 105Q100 103 107 105Q100 113.5 93 105Z"/>',
                    frown: '<path class="beak" d="M91 103Q100 98 109 103Q100 111 91 103Z"/>'
                },
                arm: '<path class="f-b o" d="M71 138C57 142 54 160 64 165C71 168 77 157 77 145Z"/>',
                feet: sym('<path class="beak" d="M74 180Q76 172 82 172Q88 172 90 180Q87 177 85 180Q82 176 79 180Q77 177 74 180Z"/>'),
                tail: '<path class="f-b o" d="M127 157L147 149L141 160L150 164L130 169Z"/>',
                tailO: '128px 162px'
            }
        },
        'czarny-kotek': {
            name: 'Czarny Kotek',
            palette: { base: '#2B2B2B', light: '#4A4A4A', dark: '#111111', cheek: '#6B4A4A' },
            extras: ['pointy_ears', 'collar_bell'],
            parts: {
                ink: '#EADDE3',
                eye: { iris: '#F2C14E', pupil: true, lid: true },
                ears: CAT_EARS,
                face: '<ellipse class="f-l" cx="100" cy="107" rx="17" ry="10.5"/>' + WHISKERS.replace(/class="wh"/g, 'class="wh wh-l"'),
                nose: '<path class="f-c o2" d="M96.8 100.6h6.4c0 1.5-1.8 3.2-3.2 3.2s-3.2-1.7-3.2-3.2z"/>',
                tail: CAT_TAIL,
                tailO: '126px 170px',
                bodyExtra: '<path fill="#E0464E" stroke="#A82F37" stroke-width="1.6" d="M70 127Q100 143 130 127L131 135Q100 152 69 135Z"/>' +
                    '<circle fill="#F5C542" stroke="#C99A1E" stroke-width="1.6" cx="100" cy="149" r="6.2"/>' +
                    '<path stroke="#9C7413" stroke-width="1.5" stroke-linecap="round" d="M95.5 149h9M100 150v3.5"/>'
            }
        },
        mis: {
            name: 'Miś',
            palette: { base: '#B5835A', light: '#E3C3A0', dark: '#8A5F3C', cheek: '#E9A087' },
            extras: ['round_ears', 'leaf'],
            parts: {
                ears: sym('<circle class="f-b o" cx="62" cy="54" r="15"/><circle class="f-l" cx="62.5" cy="55" r="8"/>'),
                face: '<ellipse class="f-l" cx="100" cy="107" rx="20" ry="13"/>',
                nose: '<ellipse class="f-k" cx="100" cy="100.5" rx="5" ry="3.4"/>',
                fringe: '<g transform="rotate(18 104 46)"><path fill="#7CC47F" stroke="#4E9A55" stroke-width="1.6" stroke-linejoin="round" d="M103 47C94 35 98 22 112 17C117 30 115 41 103 47Z"/>' +
                    '<path fill="none" stroke="#4E9A55" stroke-width="1.4" stroke-linecap="round" d="M103 47C106 37 108 29 111 21"/></g>',
                tail: '<circle class="f-b o" cx="133" cy="170" r="7"/>',
                tailO: '130px 170px'
            }
        }
    };
})();
