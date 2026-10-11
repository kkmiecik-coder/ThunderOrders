/* Strona demo rigu (tylko dev): siatka 8 gatunków x 3 stadia, potrzeby x pozy, warianty, dłoń,
   skórki jajek, nakładka wyklucia na atrapie hatch(), jajka, nagrobki, sterowanie.
   Parametry adresu: ?only=<gatunek> &theme=dark &rm=1 &sp=<gatunek> &st=<stadium> &big=1 */
(function () {
    'use strict';
    var slugs = Object.keys(window.PetSpecies);
    var stages = ['maluch', 'dziecko', 'dorosly'];
    var rigs = [], sizeRigs = [], needRigs = [];
    var log = document.getElementById('demoLog');
    var hatchLog = document.getElementById('hatchLog');
    var params = new URLSearchParams(location.search);
    var only = params.get('only');
    var timings = [];   // pomiary czasu Promise (do sprawdzenia w konsoli: demo.timings)

    function cell(parent, label) {
        var c = document.createElement('div');
        c.className = 'demo-cell';
        var holder = document.createElement('div');
        var cap = document.createElement('small');
        cap.textContent = label;
        c.appendChild(holder);
        c.appendChild(cap);
        parent.appendChild(c);
        return { cell: c, holder: holder };
    }

    function measure(label, promise) {
        var t0 = performance.now();
        return promise.then(function () {
            var ms = Math.round(performance.now() - t0);
            timings.push({ label: label, ms: ms });
            log.textContent = label + ': Promise po ' + ms + ' ms';
            return ms;
        });
    }

    // --- Gatunki × stadia ---
    var grid = document.getElementById('demoGrid');
    slugs.forEach(function (slug, i) {
        if (only && only !== slug) return;
        stages.forEach(function (stage) {
            var c = cell(grid, slug + ' · ' + stage);
            var r = PetRig.mount(c.holder, { species: slug, stage: stage, stars: (i % 3), size: 'card' });
            c.cell.addEventListener('click', function () { measure('pat() ' + slug, r.pat()); });
            rigs.push(r);
        });
    });

    // --- Potrzeby × pozy ---
    var needBox = document.getElementById('demoNeeds');
    var spSel = document.getElementById('needSpecies');
    var stSel = document.getElementById('needStage');
    slugs.forEach(function (slug) {
        var opt = document.createElement('option');
        opt.value = slug;
        opt.textContent = window.PetSpecies[slug].name;
        spSel.appendChild(opt);
    });
    if (params.get('sp')) spSel.value = params.get('sp');
    if (params.get('st')) stSel.value = params.get('st');

    function head(text) {
        var h = document.createElement('div');
        h.className = 'demo-head';
        h.textContent = text;
        needBox.appendChild(h);
    }

    function renderNeeds() {
        needRigs.forEach(function (r) { r.destroy(); });
        needRigs = [];
        needBox.innerHTML = '';
        head('');
        PetRig.POSES.forEach(head);
        PetRig.NEEDS.forEach(function (need) {
            head(need);
            PetRig.POSES.forEach(function (pose) {
                var c = cell(needBox, need + ' · ' + pose);
                var r = PetRig.mount(c.holder, { species: spSel.value, stage: stSel.value, need: need, pose: pose, size: 'card', stars: 2 });
                c.cell.addEventListener('click', function () { measure('pat() ' + need + '/' + pose, r.pat()); });
                needRigs.push(r);
            });
        });
    }
    spSel.addEventListener('change', renderNeeds);
    stSel.addEventListener('change', renderNeeds);
    renderNeeds();

    // --- Skórki jajek ---
    var skinBox = document.getElementById('demoSkins');
    PetRig.EGG_SKINS.forEach(function (skin, idx) {
        [[0, false, false], [50, true, false], [100, false, true]].forEach(function (e) {
            var c = cell(skinBox, idx + ' ' + skin + ' · ' + e[0] + '%' + (e[1] ? ' · ogrzane' : '') + (e[2] ? ' · gotowe' : ''));
            var egg = PetRig.mountEgg(c.holder, { pct: e[0], boosted: e[1], ready: e[2], size: 'card', skin: idx });
            c.cell.addEventListener('click', function () {
                measure('egg.hatch() ' + skin, egg.hatch());
            });
        });
    });

    // --- Nakładka wyklucia (atrapa API) ---
    var fakeId = 100;

    function fakeState(species, extra) {
        var pets = [{ id: 1, species: 'kotek', name: 'Mruczek', stage: 'dorosly', stars: 2 }];
        if (extra) pets.push(extra);
        return { pets: pets };
    }

    function fakeHatch(kind) {
        return function () {
            var delay = kind === 'slow' ? 3000 : 600;
            return new Promise(function (res, rej) {
                setTimeout(function () {
                    if (kind === 'error') {
                        var err = new Error('Nie udało się wykluć jajka (atrapa).');
                        err.error = 'server_error';
                        rej(err);
                        return;
                    }
                    if (kind === 'dupe') {
                        res({ result: 'dupe', species: 'kotek', species_name: 'Kotek', pet_id: ++fakeId, starred_pet_id: 1,
                            new_achievements: [], state: { pets: [{ id: 1, species: 'kotek', name: 'Mruczek', stage: 'dorosly', stars: 3 }] } });
                        return;
                    }
                    var sp = slugs[Math.floor(Math.random() * slugs.length)];
                    var id = ++fakeId;
                    var name = window.PetSpecies[sp].name;
                    res({ result: 'new', species: sp, species_name: name, pet_id: id, starred_pet_id: null,
                        new_achievements: [{ slug: 'pierwszy' }], state: fakeState(sp, { id: id, species: sp, name: name, stage: 'maluch', stars: 0 }) });
                }, delay);
            });
        };
    }

    function runHatch(kind) {
        var rejectOnce = kind === 'badname';
        var t0 = performance.now();
        hatchLog.textContent = 'trwa…';
        window.PetHatch.run({
            skin: parseInt(document.getElementById('hatchSkin').value, 10),
            hatch: fakeHatch(kind === 'badname' ? 'new' : kind),
            prevPets: kind === 'dupe' ? [{ id: 1, species: 'kotek', name: 'Mruczek', stage: 'dorosly', stars: 2 }] : undefined,
            onName: function (name) {
                return new Promise(function (res, rej) {
                    setTimeout(function () {
                        if (rejectOnce) {
                            rejectOnce = false;
                            var err = new Error('To imię jest niedozwolone (atrapa serwera).');
                            err.error = 'bad_name';
                            rej(err);
                            return;
                        }
                        res({ ok: true, name: name });
                    }, 500);
                });
            }
        }).then(function (r) {
            var ms = Math.round(performance.now() - t0);
            timings.push({ label: 'PetHatch ' + kind, ms: ms, result: r });
            hatchLog.textContent = 'zamknięte po ' + ms + ' ms: ' + JSON.stringify({ result: r.result, pet_id: r.pet_id, name: r.name, ach: r.new_achievements.length });
        }, function (err) {
            var ms = Math.round(performance.now() - t0);
            timings.push({ label: 'PetHatch ' + kind + ' (błąd)', ms: ms, error: err && (err.error || err.message) });
            hatchLog.textContent = 'odrzucone po ' + ms + ' ms: ' + (err && err.message);
        });
    }

    // --- Jajka (dotychczasowe stany) ---
    var eggBox = document.getElementById('demoEggs');
    [[0, false, false], [33, false, false], [66, true, false], [100, false, true]].forEach(function (e) {
        var c = cell(eggBox, e[0] + '%' + (e[1] ? ' · ogrzane' : '') + (e[2] ? ' · gotowe' : ''));
        var egg = PetRig.mountEgg(c.holder, { pct: e[0], boosted: e[1], ready: e[2], size: 'card' });
        c.cell.addEventListener('click', function () {
            log.textContent = 'hatch…';
            egg.hatch().then(function () {
                log.textContent = 'hatch: Promise rozwiązany';
                egg.destroy();
                var slug = slugs[Math.floor(Math.random() * slugs.length)];
                var r = PetRig.mount(c.holder, { species: slug, stage: 'maluch' });
                r.playAction('hatch').then(function () { return r.playAction('celebrate'); });
            });
        });
    });

    var memBox = document.getElementById('demoMemorial');
    slugs.forEach(function (slug, i) {
        var c = cell(memBox, slug);
        var lit = i % 2 === 0;
        var m = PetRig.mountMemorial(c.holder, { species: slug, size: 'card', lit: lit });
        c.cell.addEventListener('click', function () { lit = !lit; m.update({ lit: lit }); });
    });

    var sizeBox = document.getElementById('demoSizes');
    ['card', 'mini', 'companion'].forEach(function (size) {
        var c = cell(sizeBox, size);
        sizeRigs.push(PetRig.mount(c.holder, { species: 'kotek', stage: 'dziecko', size: size }));
    });

    function all() { return rigs.concat(sizeRigs); }

    document.addEventListener('click', function (e) {
        var b = e.target.closest('button, input');
        if (!b || b.closest('.pet-hatch-ov')) return;
        var d = b.dataset;
        if (d.mood) all().forEach(function (r) { r.update({ mood: d.mood }); });
        if (d.asleep) all().forEach(function (r) { r.update({ asleep: d.asleep === '1' }); });
        if (d.need !== undefined) all().forEach(function (r) { r.setNeed(d.need || null); });
        if (d.pose) all().forEach(function (r) { r.setPose(d.pose); });
        if (d.stars) all().forEach(function (r) { r.setStars(+d.stars); });
        if (d.gesture) {
            var ok = 0;
            all().forEach(function (r) { if (r.gesture(d.gesture)) ok++; });
            log.textContent = 'gest ' + d.gesture + ': zagrany na ' + ok + ' rigach (reszta: stadium/stan nie pozwala)';
        }
        if (d.action) measure('akcja ' + d.action, Promise.all(all().map(function (r) { return r.playAction(d.action); })));
        if (d.variant) {
            var parts = d.variant.split(':');
            measure('wariant ' + parts[1], Promise.all(all().map(function (r) { return r.playAction(parts[0], { variant: parts[1] }); })));
        }
        if (d.hand) {
            var n = +d.hand, first = rigs[0], ps = [];
            for (var i = 0; i < n; i++) {
                (function (k) {
                    setTimeout(function () { ps.push(first.pat()); }, k * 100);
                })(i);
            }
            setTimeout(function () {
                var same = ps.every(function (p) { return p === ps[0]; });
                log.textContent += ' · ' + n + '× pat(): ' + (same ? 'ten sam Promise' : 'RÓŻNE Promise!');
            }, n * 100 + 10);
            measure('dłoń ×' + n + ' (od 1. klepnięcia)', first.pat());
            all().slice(1).forEach(function (r) { r.pat(); });
        }
        if (d.hatch) runHatch(d.hatch);
        if (d.demo === 'theme') {
            var dark = document.documentElement.getAttribute('data-theme') !== 'dark';
            document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
            b.textContent = 'Motyw: ' + (dark ? 'ciemny' : 'jasny');
        }
        if (d.demo === 'rm') {
            var on = document.documentElement.classList.toggle('pet-rig-rm');
            b.textContent = 'Ruch ograniczony: ' + (on ? 'tak' : 'nie');
        }
        if (d.demo === 'idle') rigs.forEach(function (r) { r.update({ idle: b.checked }); });
    });

    document.querySelector('[data-demo="size"]').addEventListener('change', function (e) {
        rigs.forEach(function (r) { r.update({ size: e.target.value }); });
    });

    if (params.get('theme') === 'dark') document.querySelector('[data-demo="theme"]').click();
    if (params.get('big') === '1') document.body.classList.add('demo-big');
    if (params.get('rm') === '1') document.querySelector('[data-demo="rm"]').click();

    window.demo = { rigs: rigs, needRigs: function () { return needRigs; }, timings: timings, runHatch: runHatch, measure: measure };
})();
