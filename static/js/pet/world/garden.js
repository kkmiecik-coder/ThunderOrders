/**
 * Świat pupili — scena „ogród wspomnień” (spec v3 §6.6, spec v3.1 §3.5).
 *
 * - Łąka na całą scenę (niebo i trawa do krawędzi), nagrobki w scenie właściwej: pupile, które odeszły
 *   (wpisy albumu `memorial`), PetRig.mountMemorial + tabliczka z imieniem i płomykiem, gdy można dziś
 *   zapalić światełko. Klik w nagrobek = okno sceny ze szczegółami i „Zapal światełko”
 *   (POST /<id>/swiatelko, raz dziennie — jak dotąd).
 * - Tabliczka „Album gatunków n/8” = okno sceny z albumem: 8 gatunków (żywy = mini-rig, odszedł = nagrobek,
 *   nieodkryty = sylwetka bez animacji). Rigi albumu żyją tylko przy otwartym oknie.
 * - Zmiana stanu przy otwartym oknie: nagrobek jest → treść odświeżona (win.replace), zniknął → okno się
 *   zamyka z fokusem na scenie.
 * Rejestruje się w window.PetsWorld.scenes.ogrod.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.ogrod) return;

    var STAGE_LABEL = { maluch: 'Maluch', dziecko: 'Dziecko', dorosly: 'Dorosły' };
    var BOOK_SVG = '<svg class="pets-garden__sign-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" ' +
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M3 5.5c3-1.2 6-1.2 9 .8v13c-3-2-6-2-9-.8z"/><path d="M21 5.5c-3-1.2-6-1.2-9 .8v13c3-2 6-2 9-.8z"/></svg>';

    function create(ctx, host) {
        var u = ctx.u;
        var el = u.el;
        var graveViews = [];
        var slotViews = [];
        var openGraveId = null;      // pet_id nagrobka w otwartym oknie
        var openGraveSig = null;
        var albumOpen = false;
        var lastState = null;

        // --- scena ---------------------------------------------------------------------------
        var stage = el('div', 'pets-stage');
        var sign = el('button', 'pets-garden__sign');
        sign.type = 'button';
        sign.dataset.gardenAction = 'album';
        sign.innerHTML = BOOK_SVG;
        sign.appendChild(el('span', 'pets-garden__sign-text', 'Album gatunków'));
        var signCount = el('span', 'pets-album__count');
        sign.appendChild(signCount);

        var scroll = el('div', 'pets-scroll pets-garden');
        scroll.setAttribute('data-window-backdrop', '');
        var meadow = el('section', 'pets-garden__meadow');
        meadow.setAttribute('aria-labelledby', 'petsGraveTitle');
        var graveTitle = el('h2', 'pets-garden__title', 'Wspomnienia');
        graveTitle.id = 'petsGraveTitle';
        var graves = el('div', 'pets-graves');
        var gravesEmpty = el('p', 'pets-garden__empty', 'Nikt jeszcze nie odszedł do gwiazd. Oby tak zostało!');
        meadow.appendChild(graveTitle);
        meadow.appendChild(graves);
        meadow.appendChild(gravesEmpty);
        scroll.appendChild(meadow);
        stage.appendChild(sign);
        stage.appendChild(scroll);
        host.appendChild(stage);

        var win = window.PetsSceneWindow ? window.PetsSceneWindow.attach(host) : null;

        // --- album (treść okna; budowana raz, rigi tylko przy otwartym oknie) ------------------
        var albumBox = el('div', 'pets-garden__album');
        var albumTitle = el('h2', 'pets-window__title');
        albumTitle.id = 'petsAlbumTitle';
        albumTitle.appendChild(document.createTextNode('Album gatunków '));
        var albumCount = el('span', 'pets-album__count');
        albumTitle.appendChild(albumCount);
        var album = el('div', 'pets-album');
        albumBox.appendChild(albumTitle);
        albumBox.appendChild(el('p', 'pets-window__text', 'Każde jajko to losowy z ośmiu gatunków. Zbierz wszystkie!'));
        albumBox.appendChild(album);

        // --- nagrobki ------------------------------------------------------------------------
        function graveLabel(entry) {
            return 'Nagrobek: ' + (entry.name || u.speciesName(entry.species)) + ', ' + u.speciesName(entry.species) +
                (entry.can_light ? ' — możesz dziś zapalić światełko' : ' — dziś świeci światełko');
        }

        function graveView(entry) {
            var btn = el('button', 'pets-grave');
            btn.type = 'button';
            btn.dataset.gardenAction = 'grave';
            btn.dataset.petId = String(entry.pet_id);
            var art = el('span', 'pets-grave__art');
            btn.appendChild(art);
            var rig = window.PetRig ? window.PetRig.mountMemorial(art, { species: entry.species, size: 'mini', lit: !entry.can_light }) : null;
            btn.appendChild(el('span', 'pets-grave__name', entry.name || u.speciesName(entry.species)));
            var flame = el('span', 'pets-grave__flame');
            flame.setAttribute('aria-hidden', 'true');
            flame.innerHTML = u.icon('flame', 'pets-grave__flame-icon');
            btn.appendChild(flame);
            var view = { el: btn, rig: rig, key: '', flame: flame };
            updateGrave(view, entry);
            return view;
        }

        function updateGrave(view, entry) {
            view.flame.hidden = !entry.can_light;
            view.el.setAttribute('aria-label', graveLabel(entry));
            if (view.rig && typeof view.rig.update === 'function') view.rig.update({ lit: !entry.can_light });
        }

        function graveContent(entry) {
            var box = el('div', 'pets-grave-info');
            var title = el('h2', 'pets-window__title', entry.name || u.speciesName(entry.species));
            title.id = 'petsGraveWindowTitle';
            box.appendChild(title);
            box.appendChild(el('p', 'pets-grave__meta', u.speciesName(entry.species) + ' · ' + u.formatDate(entry.hatched_at) + ' – ' + u.formatDate(entry.died_at)));
            box.appendChild(el('p', 'pets-grave__meta', 'Wiek: ' + u.daysText(entry.age_days) + ' · ' + u.daysText(entry.care_days) + ' opieki'));
            box.appendChild(el('p', 'pets-grave__lights', 'Światełka: ' + (parseInt(entry.lights_count, 10) || 0)));
            var actions = el('div', 'pets-window__actions');
            if (entry.can_light) {
                var light = u.button('Zapal światełko', 'flame', 'primary', { gardenAction: 'light', petId: String(entry.pet_id) });
                light.setAttribute('data-window-key', 'light');
                actions.appendChild(light);
            } else {
                actions.appendChild(el('p', 'pets-grave__lit', 'Dziś już świeci światełko'));
            }
            box.appendChild(actions);
            return box;
        }

        function graveSig(entry) {
            return [entry.pet_id, entry.name, entry.species, entry.lights_count, entry.can_light, entry.age_days, entry.care_days].join('|');
        }

        function memorialById(state, id) {
            var list = (state && state.album) || [];
            for (var i = 0; i < list.length; i++) {
                if (list[i].status === 'memorial' && list[i].pet_id === id) return list[i];
            }
            return null;
        }

        // --- album: karty gatunków ------------------------------------------------------------
        function slotView(entry, pet) {
            var card = el('article', 'pets-album__card pets-album__card--' + entry.status);
            var art = el('div', 'pets-album__art');
            var info = el('div', 'pets-album__info');
            card.appendChild(art);
            card.appendChild(info);
            var R = window.PetRig;
            var rig = null;
            if (entry.status === 'alive' && pet) {
                if (R) {
                    rig = R.mount(art, {
                        species: entry.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: pet.asleep, size: 'mini',
                        need: R.needOf ? R.needOf(pet) : null
                    });
                }
                info.appendChild(el('h3', 'pets-album__name', pet.name || u.speciesName(entry.species)));
                info.appendChild(el('p', 'pets-album__meta', u.speciesName(entry.species) + ' · ' + (STAGE_LABEL[pet.stage] || '') +
                    (pet.hospital ? ' · w szpitalu' : '')));
            } else if (entry.status === 'memorial') {
                if (R) rig = R.mountMemorial(art, { species: entry.species, size: 'mini', lit: !entry.can_light });
                info.appendChild(el('h3', 'pets-album__name', u.speciesName(entry.species)));
                info.appendChild(el('p', 'pets-album__meta', (entry.name ? 'Pupil ' + entry.name : 'Twój pupil') + ' odszedł do gwiazd'));
            } else {
                art.classList.add('pets-album__art--silhouette');
                if (R) rig = R.mount(art, { species: entry.species, stage: 'dorosly', size: 'mini' });
                info.appendChild(el('h3', 'pets-album__name', 'Nieodkryty'));
                info.appendChild(el('p', 'pets-album__meta', 'Wykluj jajko, żeby go poznać'));
            }
            return { el: card, rig: rig, key: '' };
        }

        function sync(list, views, box, keyOf, make, onSame) {
            list.forEach(function (item, i) {
                var key = keyOf(item);
                var view = views[i];
                if (view && view.key === key) {
                    if (onSame) onSame(view, item);
                    return;
                }
                var fresh = make(item);
                fresh.key = key;
                if (view) {
                    if (view.rig) view.rig.destroy();
                    box.replaceChild(fresh.el, view.el);
                } else {
                    box.appendChild(fresh.el);
                }
                views[i] = fresh;
            });
            while (views.length > list.length) {
                var old = views.pop();
                if (old.rig) old.rig.destroy();
                if (old.el.parentNode) old.el.parentNode.removeChild(old.el);
            }
        }

        function syncAlbum(state) {
            var entries = state.album || [];
            var petsById = {};
            (state.pets || []).forEach(function (p) { petsById[p.id] = p; });
            var withPet = entries.map(function (e) { return { e: e, pet: e.status === 'alive' ? petsById[e.pet_id] : null }; });
            sync(withPet, slotViews, album, function (x) {
                var e = x.e, p = x.pet;
                return [e.species, e.status, e.pet_id, e.name, e.can_light, p ? p.name : '', p ? p.stage : '', p && p.hospital ? 'h' : ''].join('|');
            }, function (x) { return slotView(x.e, x.pet); }, function (view, x) {
                if (x.pet && view.rig) {
                    view.rig.update({ stage: x.pet.stage, stars: x.pet.stars, mood: x.pet.mood, asleep: x.pet.asleep });
                    if (typeof view.rig.setNeed === 'function' && window.PetRig.needOf) view.rig.setNeed(window.PetRig.needOf(x.pet));
                }
            });
        }

        // --- okna ----------------------------------------------------------------------------
        function closeAlbumRigs() {
            albumOpen = false;
            sync([], slotViews, album, null, null);
        }

        function onWindowClosed() {
            openGraveId = null;
            openGraveSig = null;
            if (albumOpen) closeAlbumRigs();
        }

        function openAlbum() {
            if (!win || !lastState) return;
            openGraveId = null;
            openGraveSig = null;
            albumOpen = true;
            syncAlbum(lastState);
            win.open({ content: albumBox, labelledBy: albumTitle.id, returnFocus: sign, onClose: onWindowClosed, closeLabel: 'Zamknij album' });
        }

        function openGrave(id, returnFocus) {
            var entry = memorialById(lastState, id);
            if (!win || !entry) return;
            if (albumOpen) closeAlbumRigs();
            openGraveId = id;
            openGraveSig = graveSig(entry);
            win.open({
                content: graveContent(entry), labelledBy: 'petsGraveWindowTitle', returnFocus: returnFocus || null,
                onClose: onWindowClosed, closeLabel: 'Zamknij szczegóły nagrobka'
            });
            reveal(returnFocus);
        }

        /** Arkusz (< 1024 px): wybrany nagrobek ma zostać widoczny nad arkuszem — przewija wnętrze łąki. */
        function reveal(node) {
            if (!node || !win || !win.isOpen()) return;
            var sheet = parseFloat(host.style.getPropertyValue('--window-h')) || 0;
            if (!sheet) return;
            var box = host.getBoundingClientRect();
            var r = node.getBoundingClientRect();
            var limit = box.bottom - sheet - 12;
            if (r.bottom > limit) scroll.scrollTop += r.bottom - limit;
        }

        // --- render --------------------------------------------------------------------------
        function render(state) {
            lastState = state;
            var entries = state.album || [];
            var memorials = entries.filter(function (a) { return a.status === 'memorial'; });
            sync(memorials, graveViews, graves, function (e) {
                return [e.pet_id, e.name, e.species].join('|');
            }, graveView, updateGrave);
            graves.hidden = !memorials.length;
            gravesEmpty.hidden = !!memorials.length;

            var known = entries.filter(function (a) { return a.status !== 'unknown'; }).length;
            var countText = known + '/' + entries.length;
            [signCount, albumCount].forEach(function (c) {
                c.textContent = countText;
                c.setAttribute('aria-label', 'Odkryte gatunki: ' + known + ' z ' + entries.length);
            });
            if (albumOpen) syncAlbum(state);

            if (openGraveId != null && win && win.isOpen()) {
                var entry = memorialById(state, openGraveId);
                if (!entry) {
                    win.close({ restoreFocus: true });
                } else if (graveSig(entry) !== openGraveSig) {
                    openGraveSig = graveSig(entry);
                    win.replace(graveContent(entry));
                }
            }
        }

        host.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-garden-action]');
            if (!btn || !host.contains(btn) || btn.disabled) return;
            var action = btn.dataset.gardenAction;
            if (action === 'album') {
                openAlbum();
            } else if (action === 'grave') {
                openGrave(parseInt(btn.dataset.petId, 10), btn);
            } else if (action === 'light') {
                u.setBusy(btn, true);
                ctx.send('/' + parseInt(btn.dataset.petId, 10) + '/swiatelko', {}).then(function () {
                    if (window.Haptics) window.Haptics.tap();
                }, function () { u.setBusy(btn, false); });
            }
        });

        return {
            enter: function () {},
            // Ukryta scena nie trzyma żywych rigów ani otwartego okna
            leave: function () {
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                sync([], graveViews, graves, null, null);
                closeAlbumRigs();
            },
            render: render
        };
    }

    W.scenes.ogrod = {
        title: 'Ogród wspomnień',
        create: create
    };
})();
