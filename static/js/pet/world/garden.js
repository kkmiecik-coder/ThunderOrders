/**
 * Świat pupili — scena „ogród wspomnień” (spec v3 §6.6).
 *
 * - Nagrobki na trawie: pupile, które odeszły (wpisy albumu `memorial`), PetRig.mountMemorial +
 *   „Zapal światełko” (POST /<id>/swiatelko, raz dziennie — jak dotąd).
 * - Tablica albumu: 8 gatunków (żywy = mini-rig, odszedł = nagrobek, nieodkryty = sylwetka bez animacji),
 *   licznik n/8.
 * Rejestruje się w window.PetsWorld.scenes.ogrod.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.ogrod) return;

    var STAGE_LABEL = { maluch: 'Maluch', dziecko: 'Dziecko', dorosly: 'Dorosły' };

    function create(ctx, host) {
        var u = ctx.u;
        var el = u.el;
        var graveViews = [];
        var slotViews = [];

        var wrap = el('div', 'pets-garden');

        var meadow = el('section', 'pets-garden__meadow');
        meadow.setAttribute('aria-labelledby', 'petsGraveTitle');
        var graveTitle = el('h2', 'pets-garden__title', 'Wspomnienia');
        graveTitle.id = 'petsGraveTitle';
        var graves = el('div', 'pets-graves');
        var gravesEmpty = el('p', 'pets-garden__empty', 'Nikt jeszcze nie odszedł do gwiazd. Oby tak zostało!');
        meadow.appendChild(graveTitle);
        meadow.appendChild(graves);
        meadow.appendChild(gravesEmpty);

        var board = el('section', 'pets-block pets-album-board');
        board.setAttribute('aria-labelledby', 'petsAlbumTitle');
        var boardTitle = el('h2', 'pets-block__title');
        boardTitle.id = 'petsAlbumTitle';
        boardTitle.appendChild(document.createTextNode('Album gatunków '));
        var count = el('span', 'pets-album__count');
        boardTitle.appendChild(count);
        board.appendChild(boardTitle);
        board.appendChild(el('p', 'pets-block__lead', 'Każde jajko to losowy z ośmiu gatunków. Zbierz wszystkie!'));
        var album = el('div', 'pets-album');
        board.appendChild(album);

        wrap.appendChild(meadow);
        wrap.appendChild(board);
        host.appendChild(wrap);

        function graveView(entry) {
            var card = el('article', 'pets-grave');
            var art = el('div', 'pets-grave__art');
            card.appendChild(art);
            var rig = window.PetRig ? window.PetRig.mountMemorial(art, { species: entry.species, size: 'mini', lit: !entry.can_light }) : null;
            var info = el('div', 'pets-grave__info');
            info.appendChild(el('h3', 'pets-grave__name', entry.name || u.speciesName(entry.species)));
            info.appendChild(el('p', 'pets-grave__meta', u.speciesName(entry.species) + ' · ' + u.formatDate(entry.hatched_at) + ' – ' + u.formatDate(entry.died_at)));
            info.appendChild(el('p', 'pets-grave__meta', 'Wiek: ' + u.daysText(entry.age_days) + ' · ' + u.daysText(entry.care_days) + ' opieki'));
            var lights = parseInt(entry.lights_count, 10) || 0;
            info.appendChild(el('p', 'pets-grave__lights', 'Światełka: ' + lights));
            card.appendChild(info);
            if (entry.can_light) {
                card.appendChild(u.button('Zapal światełko', 'flame', null, { gardenAction: 'light', petId: String(entry.pet_id) }));
            } else {
                card.appendChild(el('p', 'pets-grave__lit', 'Dziś już świeci światełko'));
            }
            return { el: card, rig: rig, key: '' };
        }

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

        function render(state) {
            var entries = state.album || [];
            var petsById = {};
            (state.pets || []).forEach(function (p) { petsById[p.id] = p; });

            var memorials = entries.filter(function (a) { return a.status === 'memorial'; });
            sync(memorials, graveViews, graves, function (e) {
                return [e.pet_id, e.name, e.lights_count, e.can_light].join('|');
            }, graveView);
            graves.hidden = !memorials.length;
            gravesEmpty.hidden = !!memorials.length;

            var known = entries.filter(function (a) { return a.status !== 'unknown'; }).length;
            count.textContent = known + '/' + entries.length;
            count.setAttribute('aria-label', 'Odkryte gatunki: ' + known + ' z ' + entries.length);
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

        function teardown() {
            sync([], graveViews, graves, null, null);
            sync([], slotViews, album, null, null);
        }

        wrap.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-garden-action="light"]');
            if (!btn || !wrap.contains(btn) || btn.disabled) return;
            u.setBusy(btn, true);
            ctx.send('/' + parseInt(btn.dataset.petId, 10) + '/swiatelko', {}).then(function () {
                if (window.Haptics) window.Haptics.tap();
            }, function () { u.setBusy(btn, false); });
        });

        return {
            enter: function () {},
            leave: teardown,     // ukryta scena nie trzyma żywych rigów
            render: render
        };
    }

    W.scenes.ogrod = {
        title: 'Ogród wspomnień',
        lead: 'Tu pamiętamy pupile, które odeszły do gwiazd, i zbieramy album wszystkich gatunków.',
        create: create
    };
})();
