/* Strona demo rigu (tylko dev): siatka 8 gatunków x 3 stadia, jajka, nagrobki, sterowanie. */
(function () {
    'use strict';
    var slugs = Object.keys(window.PetSpecies);
    var stages = ['maluch', 'dziecko', 'dorosly'];
    var rigs = [], sizeRigs = [];
    var log = document.getElementById('demoLog');
    var params = new URLSearchParams(location.search);
    var only = params.get('only');

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

    var grid = document.getElementById('demoGrid');
    slugs.forEach(function (slug, i) {
        if (only && only !== slug) return;
        stages.forEach(function (stage) {
            var c = cell(grid, slug + ' · ' + stage);
            var r = PetRig.mount(c.holder, { species: slug, stage: stage, stars: (i % 3), size: 'card' });
            c.cell.addEventListener('click', function () { r.playAction('pat'); });
            rigs.push(r);
        });
    });

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
        if (!b) return;
        var d = b.dataset;
        if (d.mood) all().forEach(function (r) { r.update({ mood: d.mood }); });
        if (d.asleep) all().forEach(function (r) { r.update({ asleep: d.asleep === '1' }); });
        if (d.stars) all().forEach(function (r) { r.setStars(+d.stars); });
        if (d.gesture) {
            var ok = 0;
            all().forEach(function (r) { if (r.gesture(d.gesture)) ok++; });
            log.textContent = 'gest ' + d.gesture + ': zagrany na ' + ok + ' rigach (reszta: stadium/stan nie pozwala)';
        }
        if (d.action) {
            var t0 = performance.now();
            Promise.all(all().map(function (r) { return r.playAction(d.action); })).then(function () {
                log.textContent = 'akcja ' + d.action + ': Promise po ' + Math.round(performance.now() - t0) + ' ms';
            });
        }
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
})();
