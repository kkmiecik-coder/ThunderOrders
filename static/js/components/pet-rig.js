/**
 * PetRig — rig SVG pupila (jedna struktura warstw dla wszystkich gatunków).
 *
 * Wymaga: static/js/pet/species.js (window.PetSpecies) + static/css/components/pet-rig.css.
 *
 * API (kontrakt dla pets.js / pet-card.js / towarzysza):
 *   PetRig.mount(container, {species, stage, stars, mood, asleep, size, idle}) -> rig
 *     rig.update(opts) · rig.gesture(name) · rig.playAction(action) -> Promise
 *     rig.setStars(n) · rig.destroy() · rig.el
 *   PetRig.mountEgg(container, {pct, boosted, ready, size}) -> egg
 *     egg.update(opts) · egg.hatch() -> Promise · egg.destroy() · egg.el
 *   PetRig.mountMemorial(container, {species, size, stage, lit}) -> rig
 *
 * Stany (klasy na roocie): is-idle is-sleep is-sad is-sick is-critical (z nastroju/snu)
 *   oraz is-eat is-play is-wash is-pat is-celebrate is-hatch is-heal is-wake (akcje).
 * Gesty: g-jump g-blink g-sway g-spin g-wave g-dance g-flip (zdejmowane po animationend).
 * Ruch ograniczony: @media (prefers-reduced-motion) albo klasa .pet-rig-rm na <html>.
 */
(function () {
    'use strict';

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
        g('st-stink', '<path d="M44 156q-5-6 0-12t0-12"/><path d="M156 156q5-6 0-12t0-12"/>');

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
            '<g class="rig-accessories"></g>';
        return g('rig-fig', g('rig-fm',
            g('rig-tail', g('rig-tail-in', P.tail || '', origin(P.tailO || '125px 168px'))) +
            g('rig-body', g('rig-bm', (P.body || DEF.body) + DEF.bodyDirt + (P.bodyExtra || ''))) +
            g('rig-paws', g('rig-pm', (P.feet || DEF.feet) +
                g('rig-arm-l', arm) + g('rig-arm-r', '<g transform="matrix(-1 0 0 1 200 0)">' + arm + '</g>'))) +
            g('rig-head', g('rig-hm', head))
        ));
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
            asleep: false, size: 'card', idle: false
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
                g('rig-shadow', '<ellipse cx="100" cy="183" rx="40" ry="6.5"/>') +
                g('rig-fxb', FX_BACK) + buildFigure(sp) + g('rig-fx', FX) +
                '<g class="rig-stars"></g>' + g('rig-status', STATUS) + '</svg>';
            applyPalette(el, sp);
            rig.setStars(o.stars);
        }

        function setClasses() {
            var keep = [];
            el.classList.forEach(function (c) {
                if (c.indexOf('pet-rig') !== 0) keep.push(c);
            });
            el.className = ['pet-rig', 'pet-rig--' + o.species, 'pet-rig--' + o.stage, 'pet-rig--' + o.size].concat(keep).join(' ');
        }

        function baseState() {
            if (o.asleep) return 'is-sleep';
            return 'is-' + (MOOD_STATE[o.mood] || 'idle');
        }

        function applyBase() {
            BASE_STATES.forEach(function (c) { el.classList.remove(c); });
            el.setAttribute('data-mood', o.mood);
            if (!current) el.classList.add(baseState());
        }

        function scheduleBlink() {
            clearTimeout(timers.blink);
            timers.blink = setTimeout(function () {
                if (destroyed) return;
                if (!current && !o.asleep) rig.gesture('blink');
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
                if (o.asleep) return false;
                restartClass(el, 'g-blink');
                setTimeout(function () { el.classList.remove('g-blink'); }, 260);
                return true;
            }
            // Gesty tylko w spokojnym stanie (bez akcji, snu, choroby) i bez ograniczenia ruchu.
            if (current || !el.classList.contains('is-idle') || reducedMotion()) return false;
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
        }

        // Piłka przy zabawie — jedyna sekwencja na requestAnimationFrame (spec §4.5).
        function runBall(duration) {
            var ball = el.querySelector('.fx-ball');
            var inner = el.querySelector('.fx-ball-in');
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
                // Z lewej do prawej i z powrotem, trzy odbicia o malejącej wysokości.
                var x = t < 0.5 ? 26 + t * 2 * 148 : 174 - (t - 0.5) * 2 * 148;
                var ph = (t * 3) % 1;
                var h = 58 * (1 - t * 0.55);
                var y = 172 - 4 * h * ph * (1 - ph);
                ball.setAttribute('transform', 'translate(' + x.toFixed(1) + ' ' + y.toFixed(1) + ')');
                if (inner) inner.setAttribute('transform', 'rotate(' + Math.round(t * 720 * (t < 0.5 ? 1 : -1)) + ')');
                if (t < 1) raf = requestAnimationFrame(step);
                else raf = 0;
            }
            stopBall();
            raf = requestAnimationFrame(step);
        }

        function finish(job) {
            var cls = ACTIONS[job.action][0];
            el.classList.remove(cls, 'is-acting');
            stopBall();
            if (job.action === 'wake') o.asleep = false;
            current = null;
            applyBase();
            job.resolve();
            pump();
        }

        function run(job) {
            var a = ACTIONS[job.action];
            var dur = reducedMotion() ? Math.min(a[1], 900) : a[1];
            current = job;
            endGesture();
            BASE_STATES.forEach(function (c) { el.classList.remove(c); });
            el.classList.add('is-acting');
            restartClass(el, a[0]);
            if (job.action === 'play') runBall(dur);
            clearTimeout(timers.action);
            timers.action = setTimeout(function () { finish(job); }, dur);
        }

        function pump() {
            if (current || destroyed || !queue.length) return;
            run(queue.shift());
        }

        rig.playAction = function (action) {
            if (destroyed) return Promise.resolve();
            if (!ACTIONS[action]) return Promise.reject(new Error('PetRig: nieznana akcja ' + action));
            // Pat pat wielokrotnie = jedna animacja odświeżona (bez kolejki 50 głaskań).
            if (current && current.action === action && action === 'pat') {
                restartClass(el, 'is-pat');
                clearTimeout(timers.action);
                var job0 = current;
                timers.action = setTimeout(function () { finish(job0); }, reducedMotion() ? 600 : ACTIONS.pat[1]);
                return current.promise;
            }
            var last = queue[queue.length - 1];
            if (last && last.action === action) return last.promise;
            var job = { action: action };
            job.promise = new Promise(function (res) { job.resolve = res; });
            queue.push(job);
            pump();
            return job.promise;
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

    function mountEgg(container, opts) {
        var o = { pct: 0, boosted: false, ready: false, size: 'card' };
        var id = 'pr' + (++uidSeq);
        var el = document.createElement('div');
        var timers = [];
        var destroyed = false;
        var hatching = null;
        var egg = { el: el };

        var art = '<path class="egg-shell" d="' + EGG + '"/>' +
            '<g clip-path="url(#' + id + 'c)">' +
            '<path class="egg-band" d="M36 134l12-10 12 10 12-10 12 10 12-10 12 10 12-10 12 10 12-10 12 10"/>' +
            '<circle fill="#FFC9DE" cx="78" cy="64" r="7"/><circle fill="#BFE8D5" cx="126" cy="74" r="9"/>' +
            '<circle fill="#FFE29A" cx="100" cy="46" r="5"/><circle fill="#C9B8F5" cx="66" cy="104" r="6"/>' +
            '<circle fill="#FFC9DE" cx="136" cy="110" r="5.5"/><circle fill="#BFE8D5" cx="84" cy="160" r="7.5"/>' +
            '<circle fill="#FFE29A" cx="124" cy="160" r="6"/></g>' +
            '<ellipse fill="#fff" opacity=".7" cx="72" cy="74" rx="8" ry="15" transform="rotate(22 72 74)"/>';

        el.innerHTML = '<svg viewBox="0 0 200 200" aria-hidden="true" focusable="false"><defs>' +
            '<clipPath id="' + id + 'c"><path d="' + EGG + '"/></clipPath>' +
            '<clipPath id="' + id + 't"><path d="M0 0H200V96L' + ZIG + 'L0 96Z"/></clipPath>' +
            '<clipPath id="' + id + 'b"><path d="M0 200H200V96L' + ZIG + 'L0 96Z"/></clipPath>' +
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

        function sync() {
            var p = Math.max(0, Math.min(100, Number(o.pct) || 0));
            el.className = 'pet-rig pet-rig--egg pet-rig--' + o.size;
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
        }

        egg.update = function (src) {
            if (destroyed) return egg;
            set(src);
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

    window.PetRig = {
        mount: mount,
        mountEgg: mountEgg,
        mountMemorial: mountMemorial,
        GESTURES: GESTURES,
        ACTIONS: Object.keys(ACTIONS),
        STAGES: STAGES,
        reducedMotion: reducedMotion
    };
})();
