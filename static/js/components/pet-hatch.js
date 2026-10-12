/**
 * PetHatch — pełnoekranowa scena wyklucia pupila (spec v3 §6.3).
 *
 * Wymaga: pet-rig.js (window.PetRig) + species.js + style „Pet hatch overlay (v3)" w modals.css.
 *
 *   PetHatch.run({skin, hatch, onName, prevPets?}) -> Promise<{result, pet_id, starred_pet_id,
 *                                                             new_achievements, name, response}>
 *     skin     — skórka jajka (0–4 albo nazwa z PetRig.EGG_SKINS),
 *     hatch()  — funkcja zwracająca Promise odpowiedzi API /jajka/<id>/wykluj; wołana NA STARCIE animacji,
 *     onName(name) -> Promise — zapis imienia (tylko wynik „new"); odrzucenie = komunikat przy polu
 *                (err.message), nakładka zostaje otwarta; toast powitalny należy do wołającego,
 *     prevPets — opcjonalnie lista pupili sprzed wyklucia (dokładna liczba gwiazdek „przed" przy duplikacie).
 *   Błąd hatch() → nakładka się zamyka, Promise odrzuca ten błąd (toast pokazuje wołający).
 *   Drugie run() w trakcie → odrzucenie {error: 'hatch_busy'} (guard podwójnego kliknięcia).
 *   PetHatch.isOpen() -> bool
 *
 * Scena: nocne niebo (zmierzch w jasnym motywie) z gwiazdkami, poświatą i księżycem; duża karta z pupilem.
 * Do odsłonięcia teksty są neutralne dla obu wyników (bez spoilera); wynik (plakietka, tytuł, opis)
 * pojawia się dopiero, gdy pupil już wyskoczył ze skorupki.
 * „new" (~4,1 s do pola imienia): kołysanie → pęknięcia → ciepłe światło → skorupka odskakuje → maluch
 *   wyskakuje → plakietka „Nowy gatunek!", promienie, konfetti (wybuch + deszcz) → serduszka i gwiazdki → pole imienia.
 * „dupe" (~3,5 s): te same pęknięcia → istniejący pupil, duża gwiazdka, złote konfetti (mniej),
 *   plakietka „+1 gwiazdka", „Znowu {gatunek}!" — spokojniej niż nowy gatunek.
 * Ograniczony ruch: bez kołysania, konfetti i długich animacji — po odpowiedzi od razu odsłonięcie.
 * ESC / klik w tło nie zamykają w trakcie animacji i żądań; focus trap; fokus wraca na wywołujący element.
 */
(function () {
    'use strict';

    if (window.PetHatch) return;

    var ov = null;      // korzeń nakładki (budowany raz, przy pierwszym run)
    var ui = null;      // referencje do elementów
    var active = null;  // bieżąca sesja wyklucia

    var HEART = 'M12 21c-1-1-9-6-9-12a5 5 0 0 1 9-3a5 5 0 0 1 9 3c0 6-8 11-9 12z';
    var STAR = 'M12 2l2.9 6.3 6.9.8-5.1 4.7 1.4 6.8L12 17.3 5.9 20.6l1.4-6.8L2.2 9.1l6.9-.8z';
    var SPARKLE = 'M12 1.5c.7 6 3.5 8.8 9.5 10.5-6 1.7-8.8 4.5-9.5 10.5-.7-6-3.5-8.8-9.5-10.5 6-1.7 8.8-4.5 9.5-10.5z';

    // Konfetti: lekkie, bez bibliotek — ≤ 60 elementów, animowane tylko transform/opacity, sprzątane po końcu.
    // Nowy gatunek: wybuch z jajka + deszcz z góry ekranu; duplikat: mały złoty wybuch.
    var CONFETTI = {
        'new': { burst: 40, rain: 16, colors: [0, 1, 2, 3, 4, 5], spread: 80, reach: [0.22, 0.32] },
        dupe: { burst: 16, rain: 0, colors: [2, 6, 7], spread: 55, reach: [0.12, 0.14] }
    };
    var SHAPES = ['rect', 'strip', 'dot'];

    function reducedMotion() {
        if (window.PetRig && window.PetRig.reducedMotion) return window.PetRig.reducedMotion();
        return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

    function el(tag, cls, attrs) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (attrs) Object.keys(attrs).forEach(function (k) { n.setAttribute(k, attrs[k]); });
        return n;
    }

    function svgIcon(path, cls) {
        return '<svg class="' + cls + '" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="' + path + '"/></svg>';
    }

    function restartClass(node, cls) {
        node.classList.remove(cls);
        void node.offsetWidth;
        node.classList.add(cls);
    }

    function build() {
        ov = el('div', 'pet-hatch-ov', { hidden: '', 'aria-hidden': 'true' });
        var party = '';
        for (var i = 0; i < 10; i++) party += svgIcon(i % 2 ? STAR : HEART, 'pet-hatch-bit ' + (i % 2 ? 'pet-hatch-bit--star' : 'pet-hatch-bit--heart'));
        var sparkles = '';
        for (var j = 0; j < 6; j++) sparkles += svgIcon(SPARKLE, 'pet-hatch-sparkle');
        ov.innerHTML =
            '<div class="pet-hatch-sky" aria-hidden="true"><div class="pet-hatch-moon"></div>' + sparkles + '</div>' +
            '<div class="pet-hatch-dialog" role="dialog" aria-modal="true" aria-labelledby="petHatchOvTitle" aria-describedby="petHatchOvText" tabindex="-1">' +
            '<div class="pet-hatch-stage">' +
            '<div class="pet-hatch-halo" aria-hidden="true"></div>' +
            '<div class="pet-hatch-rays" aria-hidden="true"></div><div class="pet-hatch-glow" aria-hidden="true"></div>' +
            '<div class="pet-hatch-ground" aria-hidden="true"></div>' +
            '<div class="pet-hatch-slot"></div>' + svgIcon(STAR, 'pet-hatch-bigstar') +
            '<div class="pet-hatch-party" aria-hidden="true">' + party + '</div>' +
            '</div>' +
            '<p class="pet-hatch-badge"><span class="pet-hatch-badge-in">' + svgIcon(STAR, 'pet-hatch-badge-ico') +
            '<span class="pet-hatch-badge-txt"></span>' + svgIcon(STAR, 'pet-hatch-badge-ico') + '</span></p>' +
            '<h2 class="pet-hatch-title" id="petHatchOvTitle"></h2>' +
            '<p class="pet-hatch-text" id="petHatchOvText" aria-live="polite"></p>' +
            '<form class="pet-hatch-form" hidden novalidate>' +
            '<label class="pet-hatch-label" for="petHatchOvName">Imię pupila (1–20 znaków)</label>' +
            '<input class="pet-hatch-input" id="petHatchOvName" name="name" type="text" maxlength="40" autocomplete="off" aria-describedby="petHatchOvError">' +
            '<p class="pet-hatch-error" id="petHatchOvError" role="alert" hidden></p>' +
            '<div class="pet-hatch-buttons">' +
            '<button type="submit" class="pet-hatch-btn pet-hatch-btn--primary">Zapisz imię</button>' +
            '<button type="button" class="pet-hatch-btn pet-hatch-btn--ghost" data-hatch-later>Później</button>' +
            '</div></form>' +
            '<div class="pet-hatch-buttons pet-hatch-done" hidden>' +
            '<button type="button" class="pet-hatch-btn pet-hatch-btn--primary" data-hatch-ok>Super!</button></div>' +
            '</div>' +
            '<div class="pet-hatch-confetti" aria-hidden="true"></div>';
        document.body.appendChild(ov);
        ui = {
            dialog: ov.querySelector('.pet-hatch-dialog'),
            stage: ov.querySelector('.pet-hatch-stage'),
            slot: ov.querySelector('.pet-hatch-slot'),
            badge: ov.querySelector('.pet-hatch-badge'),
            badgeText: ov.querySelector('.pet-hatch-badge-txt'),
            title: ov.querySelector('.pet-hatch-title'),
            text: ov.querySelector('.pet-hatch-text'),
            form: ov.querySelector('.pet-hatch-form'),
            input: ov.querySelector('.pet-hatch-input'),
            error: ov.querySelector('.pet-hatch-error'),
            done: ov.querySelector('.pet-hatch-done'),
            ok: ov.querySelector('[data-hatch-ok]'),
            confetti: ov.querySelector('.pet-hatch-confetti')
        };

        ui.form.addEventListener('submit', onSubmit);
        ov.addEventListener('click', function (e) {
            if (!active) return;
            if (e.target.closest('[data-hatch-later]') || e.target.closest('[data-hatch-ok]')) {
                close();
                return;
            }
            // Klik w tło (poza okienkiem) zamyka tylko po odsłonięciu, nigdy w trakcie żądania.
            if (!e.target.closest('.pet-hatch-dialog')) close();
        });
        document.addEventListener('keydown', onKey, true);
    }

    function later(fn, ms) {
        var s = active;
        var t = setTimeout(function () {
            if (active === s) fn();
        }, ms);
        s.timers.push(t);
        return t;
    }

    function setPhase(cls) {
        ui.stage.className = 'pet-hatch-stage' + (cls ? ' ' + cls : '');
    }

    function clearSlot() {
        if (!active) return;
        if (active.egg) { active.egg.destroy(); active.egg = null; }
        if (active.rig) { active.rig.destroy(); active.rig = null; }
        ui.slot.innerHTML = '';
    }

    function clearConfetti() {
        if (ui && ui.confetti) ui.confetti.textContent = '';
    }

    function resetDialog() {
        var d = ui.dialog;
        d.classList.remove('is-result', 'is-flip', 'is-settle');
        d.style.transform = '';
        ui.badge.className = 'pet-hatch-badge';
        ui.badgeText.textContent = '';
    }

    function findPet(list, id) {
        for (var i = 0; i < (list || []).length; i++) if (list[i] && list[i].id === id) return list[i];
        return null;
    }

    function setFormBusy(on) {
        ui.input.disabled = on;
        Array.prototype.forEach.call(ui.form.querySelectorAll('button'), function (b) { b.disabled = on; });
    }

    function showNameError(message) {
        ui.error.textContent = message;
        ui.error.hidden = false;
        ui.input.setAttribute('aria-invalid', 'true');
        ui.input.focus();
    }

    /**
     * Zmiana treści karty bez skoku: karta jest wyśrodkowana, więc gdy rośnie (pole imienia), przesuwa się
     * w górę — przesunięcie odgrywamy płynnie (FLIP: pomiar przed/po, odwrócenie transformem, powrót do zera).
     */
    function relayout(s, fn) {
        var d = ui.dialog;
        if (s.rm) {
            fn();
            return;
        }
        var before = d.getBoundingClientRect().top;
        fn();
        d.classList.remove('is-settle');
        d.classList.add('is-flip');
        d.style.transform = '';
        var delta = before - d.getBoundingClientRect().top;
        if (Math.abs(delta) < 1) {
            d.classList.remove('is-flip');
            return;
        }
        d.style.transform = 'translateY(' + Math.round(delta) + 'px)';
        void d.offsetWidth;
        d.classList.remove('is-flip');
        d.classList.add('is-settle');
        d.style.transform = '';
    }

    function rand(a, b) {
        return a + Math.random() * (b - a);
    }

    function px(n) {
        return n.toFixed(1) + 'px';
    }

    function confettoPiece(kind, i, cfg) {
        var shape = SHAPES[i % SHAPES.length];
        var color = cfg.colors[Math.floor(Math.random() * cfg.colors.length)];
        return el('i', 'pet-hatch-confetto pet-hatch-confetto--' + shape + ' pet-hatch-confetto--c' + color +
            (kind === 'rain' ? ' is-rain' : ''));
    }

    function setVars(p, vars) {
        Object.keys(vars).forEach(function (k) { p.style.setProperty('--' + k, vars[k]); });
    }

    /** Konfetti z jajka (i deszcz z góry dla nowego gatunku). Wartości losowe = dynamiczne zmienne CSS. */
    function confetti(s, kind) {
        if (s.rm || !ui.confetti) return;
        var cfg = CONFETTI[kind];
        var W = window.innerWidth || document.documentElement.clientWidth || 800;
        var H = window.innerHeight || document.documentElement.clientHeight || 600;
        var r = ui.slot.getBoundingClientRect();
        var ox = r.left + r.width / 2;
        var oy = r.top + r.height * 0.55;
        var reach = Math.min(Math.max(W, H), 1100);
        var frag = document.createDocumentFragment();
        var end = 0;
        var i, p, a, d, delay, dur;
        clearConfetti();
        for (i = 0; i < cfg.burst; i++) {
            a = (-90 + rand(-1, 1) * cfg.spread) * Math.PI / 180;
            d = reach * (cfg.reach[0] + Math.random() * cfg.reach[1]);
            delay = rand(0, 0.14);
            dur = (kind === 'new' ? 1.9 : 1.6) + Math.random() * 0.8;
            end = Math.max(end, delay + dur);
            p = confettoPiece('burst', i, cfg);
            setVars(p, {
                px: px(ox), py: px(oy),
                x1: px(Math.cos(a) * d), y1: px(Math.sin(a) * d),
                x2: px(Math.cos(a) * d * 1.35), y2: px(Math.sin(a) * d + H * rand(0.3, 0.55)),
                r: Math.round(rand(-1, 1) * 720) + 'deg', d: delay.toFixed(2) + 's', t: dur.toFixed(2) + 's'
            });
            frag.appendChild(p);
        }
        for (i = 0; i < cfg.rain; i++) {
            delay = rand(0.2, 0.9);
            dur = rand(2.4, 3.4);
            end = Math.max(end, delay + dur);
            p = confettoPiece('rain', i, cfg);
            setVars(p, {
                px: px(rand(0.04, 0.96) * W), py: '-24px',
                x1: px(rand(-40, 40)), y1: px(H * 0.5),
                x2: px(rand(-80, 80)), y2: px(H + 48),
                r: Math.round(rand(-1, 1) * 540) + 'deg', d: delay.toFixed(2) + 's', t: dur.toFixed(2) + 's'
            });
            frag.appendChild(p);
        }
        ui.confetti.appendChild(frag);
        later(clearConfetti, Math.ceil(end * 1000) + 150);
    }

    // --- Sekwencja -----------------------------------------------------------------------

    function run(opts) {
        opts = opts || {};
        if (active) {
            var busy = new Error('Wyklucie już trwa.');
            busy.error = 'hatch_busy';
            return Promise.reject(busy);
        }
        if (!window.PetRig || typeof opts.hatch !== 'function') {
            return Promise.reject(new Error('PetHatch: brak PetRig albo funkcji hatch'));
        }
        if (!ov) build();
        var s = active = {
            opts: opts, phase: 'anim', resp: null, err: null, done: false, timers: [],
            egg: null, rig: null, trigger: document.activeElement, rm: reducedMotion(),
            minUntil: 0, defaultName: ''
        };
        s.promise = new Promise(function (res, rej) { s.resolve = res; s.reject = rej; });

        clearSlot();
        clearConfetti();
        resetDialog();
        ov.classList.toggle('is-rm', s.rm);
        setPhase(s.rm ? 'is-rm' : '');
        ui.title.textContent = 'Coś się dzieje…';
        ui.text.textContent = 'Jajko zaczyna pękać!';
        ui.form.hidden = true;
        ui.done.hidden = true;
        ui.error.hidden = true;
        ui.input.removeAttribute('aria-invalid');
        s.egg = window.PetRig.mountEgg(ui.slot, { pct: 0, size: 'card', skin: opts.skin });

        ov.hidden = false;
        ov.setAttribute('aria-hidden', 'false');
        document.documentElement.classList.add('pet-hatch-open');
        void ov.offsetWidth;
        ov.classList.add('is-open');
        ui.dialog.focus();

        // Żądanie startuje razem z animacją; wynik czeka w s.resp.
        var req;
        try {
            req = Promise.resolve(opts.hatch());
        } catch (e) {
            req = Promise.reject(e);
        }
        req.then(function (resp) {
            if (active !== s) return;
            if (!resp || (resp.result !== 'new' && resp.result !== 'dupe')) {
                var bad = new Error('Nieoczekiwana odpowiedź wyklucia.');
                bad.response = resp;
                fail(s, bad);
                return;
            }
            s.resp = resp;
            if (s.phase === 'wait') crack(s);
        }, function (err) {
            if (active === s) fail(s, err);
        });

        if (s.rm) {
            // Bez kołysania: jajko stoi, odsłonięcie zaraz po odpowiedzi.
            s.phase = 'wait';
            setPhase('is-rm is-wait');
        } else {
            later(function () { setPhase('is-rock'); }, 250);
            later(function () { s.egg.update({ pct: 40 }); }, 450);
            later(function () { s.egg.update({ pct: 70 }); }, 750);
            later(function () {
                s.phase = 'wait';
                setPhase('is-rock is-wait');
                if (s.resp) crack(s);
            }, 900);
        }
        return s.promise;
    }

    function fail(s, err) {
        s.err = err;
        finish(s, err);
    }

    // Po fazie A (≥ 0,9 s) i odpowiedzi: pęknięcie i odsłonięcie. Ten sam przebieg i tekst dla obu wyników —
    // krótsze pękanie albo „Coś znajomego…" zdradzałyby duplikat, zanim pupil się pokaże.
    function crack(s) {
        if (s.phase !== 'wait') return;
        s.phase = 'crack';
        if (s.rm) {
            reveal(s);
            return;
        }
        s.egg.update({ pct: 100 });
        setPhase('is-rock is-glow');
        ui.text.textContent = 'Ciepło, coraz cieplej…';
        later(function () {
            setPhase('is-glow is-shake');
            s.egg.hatch();
            later(function () { reveal(s); }, 950);   // = moment „burst" w egg.hatch()
        }, 700);
    }

    function reveal(s) {
        var resp = s.resp;
        var R = window.PetRig;
        var pets = (resp.state && resp.state.pets) || [];
        var name = resp.species_name || resp.species || 'pupil';
        var dupe = resp.result !== 'new';
        if (window.Haptics && typeof window.Haptics.pattern === 'function') window.Haptics.pattern('hatch');
        if (s.egg) {
            var egg = s.egg;
            s.egg = null;
            // Skorupka odskakuje i blednie jeszcze chwilę; pupil wchodzi, gdy dół skorupki prawie zniknął.
            if (s.rm) egg.destroy();
            else later(function () { egg.destroy(); }, 700);
        }
        s.phase = 'reveal-anim';
        setPhase(s.rm ? 'is-rm is-open-egg' : 'is-open-egg is-glow');

        var starred = {}, stars = 0, prevStars = 0;
        if (!dupe) {
            var pet = findPet(pets, resp.pet_id) || {};
            s.defaultName = pet.name || name;
        } else {
            starred = findPet(pets, resp.starred_pet_id) || {};
            var before = findPet(s.opts.prevPets, resp.starred_pet_id);
            stars = parseInt(starred.stars, 10) || 0;
            prevStars = before ? (parseInt(before.stars, 10) || 0) : Math.max(0, stars - 1);
        }
        var gained = dupe && stars > prevStars;

        // Wynik dopiero po odsłonięciu pupila — w trakcie pękania tytuł i opis zostają neutralne.
        function showResult() {
            relayout(s, function () {
                if (!dupe) {
                    ui.badge.className = 'pet-hatch-badge pet-hatch-badge--new is-shown';
                    ui.badgeText.textContent = 'Nowy gatunek!';
                    ui.title.textContent = 'Odkryto: ' + name + '!';
                    ui.text.textContent = name + ' to Twój nowy pupil. Jak go nazwiesz?';   // gatunek też w regionie live (czytnik ekranu)
                } else {
                    var who = starred.name ? 'Twój pupil ' + starred.name : 'Twój pupil';
                    ui.badge.className = 'pet-hatch-badge pet-hatch-badge--star is-shown';
                    ui.badgeText.textContent = gained ? '+1 gwiazdka' : 'Komplet gwiazdek';
                    // „Znowu …!" — bez rodzaju gramatycznego (jak w v2)
                    ui.title.textContent = 'Znowu ' + name + '!';
                    ui.text.textContent = gained ? who + ' dostaje gwiazdkę ⭐' : who + ' ma już komplet gwiazdek ⭐';
                }
            });
            if (s.rm) ui.dialog.classList.add('is-result');
            else restartClass(ui.dialog, 'is-result');
        }

        function mountPet() {
            if (!dupe) s.rig = R.mount(ui.slot, { species: resp.species, stage: 'maluch', size: 'card' });
            else s.rig = R.mount(ui.slot, { species: resp.species, stage: starred.stage || 'dorosly', stars: prevStars, size: 'card' });
        }

        if (s.rm) {
            mountPet();
            showResult();
            if (dupe) {
                s.rig.setStars(stars);
                setPhase('is-rm is-open-egg is-star');
                showDone(s);
            } else {
                setPhase('is-rm is-open-egg is-new');
                showForm(s);
            }
            return;
        }

        later(function () {
            mountPet();
            var rig = s.rig;
            if (!dupe) {
                setPhase('is-open-egg is-glow is-new');
                rig.playAction('hatch').then(function () {
                    if (active !== s || s.rig !== rig) return;
                    setPhase('is-open-egg is-party is-new');
                    return rig.playAction('wake');   // przeciągnięcie i ziewnięcie „po drzemce w jajku"
                });
                // Maluch wyskoczył (szczyt „hatch-pop" rigu) → plakietka, tytuł i konfetti
                later(function () {
                    showResult();
                    confetti(s, 'new');
                }, 380);
                later(function () { showForm(s); }, 1300);
            } else {
                rig.playAction('hatch');
                later(function () {
                    rig.setStars(stars);
                    setPhase('is-open-egg is-party is-star' + (gained ? ' is-star-gain' : ''));
                    showResult();
                    confetti(s, 'dupe');
                }, 320);
                later(function () { showDone(s); }, 760);
            }
        }, dupe ? 150 : 250);
    }

    function showForm(s) {
        s.phase = 'reveal';
        ui.input.value = s.defaultName;
        ui.input.removeAttribute('aria-invalid');
        ui.error.hidden = true;
        setFormBusy(false);
        relayout(s, function () { ui.form.hidden = false; });
        ui.input.focus();
        try { ui.input.select(); } catch (e) { /* nic */ }
    }

    function showDone(s) {
        s.phase = 'reveal';
        relayout(s, function () { ui.done.hidden = false; });
        ui.ok.focus();
    }

    function onSubmit(e) {
        e.preventDefault();
        var s = active;
        if (!s || s.phase !== 'reveal' || !s.resp || s.resp.result !== 'new') return;
        var name = String(ui.input.value || '').split(/\s+/).filter(Boolean).join(' ');
        var len = Array.from(name).length;
        ui.input.removeAttribute('aria-invalid');
        ui.error.hidden = true;
        if (len < 1 || len > 20) {
            showNameError('Imię ma mieć od 1 do 20 znaków.');
            return;
        }
        if (name === s.defaultName || typeof s.opts.onName !== 'function') {
            close();
            return;
        }
        s.phase = 'saving';
        setFormBusy(true);
        var p;
        try {
            p = Promise.resolve(s.opts.onName(name));
        } catch (err) {
            p = Promise.reject(err);
        }
        p.then(function () {
            if (active !== s) return;
            s.named = name;
            s.phase = 'reveal';
            close();
        }, function (err) {
            if (active !== s) return;
            s.phase = 'reveal';
            setFormBusy(false);
            // Pupil już istnieje — nakładka zostaje, komunikat serwera przy polu (textContent = bez HTML)
            var msg = err && typeof err.message === 'string' && err.message ? err.message : 'Nie udało się zapisać imienia.';
            showNameError(msg);
        });
    }

    function close() {
        var s = active;
        if (!s || s.phase !== 'reveal') return;   // w trakcie animacji / żądań nie zamykamy
        finish(s, null);
    }

    function finish(s, err) {
        s.phase = 'closing';
        s.timers.forEach(clearTimeout);
        s.timers = [];
        ui.dialog.classList.remove('is-flip', 'is-settle');
        ui.dialog.style.transform = '';
        ov.classList.remove('is-open');
        var delay = s.rm ? 0 : 280;
        setTimeout(function () {
            clearSlot();
            clearConfetti();
            resetDialog();
            setPhase('');
            ov.hidden = true;
            ov.setAttribute('aria-hidden', 'true');
            document.documentElement.classList.remove('pet-hatch-open');
            if (active === s) active = null;
            var back = s.trigger;
            if (back && back !== document.body && document.body.contains(back) && !back.disabled && typeof back.focus === 'function') back.focus();
            if (err) {
                s.reject(err);
                return;
            }
            var r = s.resp || {};
            s.resolve({
                result: r.result,
                pet_id: r.pet_id,
                starred_pet_id: r.starred_pet_id != null ? r.starred_pet_id : null,
                new_achievements: r.new_achievements || [],
                name: s.named || null,
                response: r
            });
        }, delay);
    }

    function onKey(e) {
        if (!active || !ov || ov.hidden) return;
        if (e.key === 'Escape') {
            e.preventDefault();
            e.stopPropagation();
            close();
            return;
        }
        if (e.key !== 'Tab') return;
        var items = Array.prototype.filter.call(
            ui.dialog.querySelectorAll('button:not([disabled]), input:not([disabled]), [href]'),
            function (x) { return x.offsetParent !== null; }
        );
        if (!items.length) {
            e.preventDefault();
            ui.dialog.focus();
            return;
        }
        var first = items[0], last = items[items.length - 1];
        if (e.shiftKey && (document.activeElement === first || document.activeElement === ui.dialog)) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && (document.activeElement === last || !ui.dialog.contains(document.activeElement))) {
            e.preventDefault();
            first.focus();
        }
    }

    window.PetHatch = {
        run: run,
        isOpen: function () { return !!active; }
    };
})();
