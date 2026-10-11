/**
 * Świat pupili — scena „domek” (spec v3 §6.1–6.2, spec v3.1 §3.5): pokój (PetRoom) na całą scenę + panel
 * pupila (PetCard) w oknie sceny (PetsSceneWindow: karta ≥ 1024 px, arkusz od dołu < 1024 px).
 *
 * - Pokój wypełnia scenę: ściana i podłoga sięgają krawędzi, meble i pupile w .pets-stage (max 1200 px);
 *   przy otwartej karcie scena właściwa rezerwuje prawe 376 px, przy arkuszu pokój jedzie w górę o jego
 *   wysokość (--window-h), żeby wybrany pupil i jego imię zostały widoczne nad arkuszem.
 * - Klik w pupila → room.focus(id) + okno (fokus zostaje na pupilu); drugi klik w tego samego pupila
 *   przy otwartym oknie = pat pat (dłoń w rigu + paczka w pets.js).
 * - Zamknięcie okna: ×, Esc, klik w pokój (poza pupilem), przeciągnięcie arkusza w dół — obsługuje okno sceny.
 * - `?pupil=ID` otwiera okno (fokus na kartę); pupil w szpitalu → przekierowanie na Izbę przyjęć z jego
 *   oknem (replaceState); pupil nieistniejący / odeszły → pokój bez okna i bez błędu (Review Focus 5). Otwarte
 *   okno aktualizuje adres przez replaceState (bez nowych wpisów historii).
 * Rejestruje się w window.PetsWorld.scenes.domek.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.domek) return;

    function create(ctx, host) {
        var u = ctx.u;
        var room = null;
        var card = null;
        var openId = null;
        var pending = null;          // parametry z adresu czekające na stan
        var lastPets = [];

        var stage = u.el('div', 'pets-stage');
        var wrap = u.el('div', 'pets-house');
        var notes = u.el('div', 'pets-house__notes');
        var tip = u.el('p', 'pets-house__tip', 'Kliknij pupila, żeby się nim zająć. Kliknij go jeszcze raz, żeby go pogłaskać.');
        var away = u.el('p', 'pets-house__away');
        away.hidden = true;
        var intro = u.el('div', 'pets-house__intro pets-block');
        intro.hidden = true;
        notes.appendChild(away);
        notes.appendChild(tip);
        wrap.appendChild(notes);
        wrap.appendChild(intro);
        stage.appendChild(wrap);
        host.appendChild(stage);

        var win = window.PetsSceneWindow ? window.PetsSceneWindow.attach(host) : null;

        function homePets(state) {
            return ((state && state.pets) || []).filter(function (p) { return !p.hospital; });
        }

        function cardCtx(state) {
            return {
                now: state.now,
                night: state.night && state.night.start !== state.night.end ? state.night : null,
                config: state.config || null
            };
        }

        // --- pokój -------------------------------------------------------------------------

        function onPetClick(id) {
            if (openId === id) {
                if (ctx.pat(id) && room) room.pat(id);
                return;
            }
            openPanel(id, { focusPanel: false });
        }

        function ensureRoom(state) {
            if (room) return;
            room = window.PetRoom.mount(wrap, {
                pets: homePets(state),
                night: !!(state && state.night && state.night.is_night),
                compact: false,
                interactive: true,
                onPetClick: onPetClick
            });
            wrap.insertBefore(room.el, notes);
            // Klik w pokój poza pupilem zamyka okno sceny (pupile to przyciski — okno je pomija)
            room.el.setAttribute('data-window-backdrop', '');
        }

        // --- panel -------------------------------------------------------------------------

        function onAction(pet, action, variant) {
            var payload = { action: action };
            if (variant) payload.variant = variant;
            return ctx.send('/' + pet.id + '/akcja', payload);
        }

        function onPlay(pet, action, variant) {
            return room ? room.playAction(pet.id, action, variant) : null;
        }

        function onRename(pet, name) {
            return ctx.send('/' + pet.id + '/imie', { name: name }, { quiet: ['bad_name'] });
        }

        function onAdmit(pet) {
            return ctx.send('/' + pet.id + '/szpital', {}).then(function (resp) {
                u.toast('Pupil ' + (pet.name || '') + ' trafił do szpitala. Wróci zdrowy!', 'success');
                closePanel(false);
                // Spec v3.1 §4.4: prosto do Izby przyjęć, z otwartym oknem pupila w łóżku
                ctx.go('izba', { pupil: pet.id });
                return resp;
            });
        }

        /** Okno zamknięte (×, Esc, tło, przeciągnięcie albo closePanel) — sprzątanie po panelu. */
        function onWindowClosed() {
            if (openId == null) return;
            openId = null;
            ctx.flushPats();
            if (card) {
                card.destroy();
                card = null;
            }
            if (room) room.focus(null);
            if (ctx.isActive('domek')) ctx.setQuery({});
        }

        function openPanel(id, o) {
            o = o || {};
            var state = ctx.state();
            var pet = ctx.findPet(id, state);
            if (!pet || pet.hospital || !window.PetCard || !win) return false;
            // Inny pupil przy otwartym oknie: okno podmienia treść (bez onClose) — starą kartę sprzątamy sami
            if (card) {
                card.destroy();
                card = null;
            }
            ctx.flushPats();
            openId = id;
            if (room) room.focus(id);
            var box = u.el('div', 'pets-house__panel');
            card = window.PetCard.render(box, pet, {
                onAction: onAction, onPlay: onPlay, onRename: onRename, onAdmit: onAdmit,
                onStars: function (p) { if (room) room.playAction(p.id, 'celebrate'); },
                now: cardCtx(state).now, night: cardCtx(state).night, config: cardCtx(state).config
            });
            var title = box.querySelector('.pet-card__title');
            win.open({
                content: box,
                labelledBy: title ? title.id : null,
                returnFocus: room ? room.petButton(id) : null,
                onClose: onWindowClosed,
                closeLabel: 'Zamknij panel pupila',
                // Klik w pupila: fokus zostaje na nim (Enter jeszcze raz = pat pat); z adresu — na kartę
                focus: o.focusPanel ? card.el : false
            });
            ctx.setQuery({ pupil: id });
            return true;
        }

        /** Zamknięcie z kodu (zmiana stanu, wyjście ze sceny); `restoreFocus` — fokus wraca na pupila/scenę. */
        function closePanel(restoreFocus) {
            if (openId == null) return;
            if (win && win.isOpen()) win.close({ restoreFocus: !!restoreFocus });
            else onWindowClosed();
        }

        // --- treść poza pokojem -------------------------------------------------------------

        function renderAway(state) {
            var inHospital = ((state.pets) || []).filter(function (p) { return p.hospital; });
            away.hidden = !inHospital.length;
            if (!inHospital.length) return;
            var names = inHospital.map(function (p) { return p.name || u.speciesName(p.species); });
            var ready = inHospital.some(function (p) { return p.hospital.ready; });
            var sig = names.join('|') + (ready ? '!' : '');
            if (away.dataset.sig === sig) return;
            away.dataset.sig = sig;
            away.innerHTML = '';
            away.appendChild(document.createTextNode(
                (inHospital.length === 1 ? 'W szpitalu: ' : 'W szpitalu są: ') + names.join(', ') +
                (ready ? ' — ktoś już wyzdrowiał i czeka na odbiór. ' : '. ')));
            var link = u.el('a', 'pets-link', 'Przejdź do szpitala');
            link.href = ctx.href('izba');
            link.dataset.sceneLink = 'izba';
            away.appendChild(link);
        }

        function renderIntro(state, empty) {
            intro.hidden = !empty;
            tip.hidden = empty;
            if (!empty) return;
            var toClaim = (state.eggs_available || []).length > 0;
            var hasEgg = (state.eggs || []).length > 0 || toClaim;
            var sig = (toClaim ? 'claim' : hasEgg ? 'egg' : 'none') + '|' +(state.night ? state.night.start + '-' + state.night.end : '');
            if (intro.dataset.sig === sig) return;
            intro.dataset.sig = sig;
            intro.innerHTML = '';
            intro.appendChild(u.el('h2', 'pets-block__title', hasEgg ? 'Domek czeka na pierwszego lokatora' : 'W domku nikogo teraz nie ma'));
            var list = u.el('ul', 'pets-house__rules');
            var night = state.night || {};
            [
                'Jajka odbierasz na recepcji w szpitalu, a wykluwasz w Inkubatorium. Ogrzewaj je przy każdej wizycie — tak wyklują się szybciej.',
                'Każde jajko to losowy z ośmiu gatunków. Zbierz wszystkie w albumie w ogrodzie wspomnień!',
                'Karm, baw się i myj pupila. Jedna wizyta dziennie wystarczy, żeby był zdrowy, dwie–trzy — żeby był szczęśliwy.',
                'W nocy (' + (night.start != null && night.start !== night.end ? night.start + ':00–' + night.end + ':00' : '23:00–7:00') +
                    ') pupil śpi. Zaniedbany choruje — wtedy zabierz go do szpitala.'
            ].forEach(function (text) { list.appendChild(u.el('li', null, text)); });
            intro.appendChild(list);
            // Jajko do odebrania → recepcja w holu; jajka w inkubacji → Inkubatorium; nic → hol szpitala
            var target = hasEgg && !toClaim ? 'inkubatorium' : 'szpital';
            var go = u.el('a', 'pet-btn pet-btn--primary pets-house__go');
            go.href = ctx.href(target);
            go.dataset.sceneLink = target;
            go.textContent = toClaim ? 'Odbierz jajko na recepcji' : hasEgg ? 'Do Inkubatorium' : 'Do szpitala';
            intro.appendChild(go);
        }

        // --- parametry z adresu (?pupil=ID) --------------------------------------------------

        function applyParams(params, state) {
            pending = null;
            var id = params && params.pupil;
            if (!id) {
                if (openId != null) closePanel(false);
                return;
            }
            var pet = ctx.findPet(id, state);
            if (pet && pet.hospital) {
                ctx.go('izba', { pupil: id }, { replace: true });
                return;
            }
            if (!pet) {
                // Odeszły, cudzy albo nieistniejący: pokój bez panelu, adres bez parametru
                if (openId != null) closePanel(false);
                ctx.setQuery({});
                return;
            }
            openPanel(id, { focusPanel: true });
        }

        function render(state) {
            ensureRoom(state);
            var pets = homePets(state);
            lastPets = pets;
            room.update(pets, { night: !!(state.night && state.night.is_night) });
            renderIntro(state, !pets.length);
            renderAway(state);
            if (pending) {
                applyParams(pending, state);
                return;
            }
            if (openId != null) {
                // Zmiana stanu przy otwartym oknie (odświeżenie, druga karta): pupil jest → karta w miejscu;
                // zniknął (szpital, odejście) → okno zamyka się, fokus z okna wraca na scenę (Review Focus 3)
                var pet = ctx.findPet(openId, state);
                if (!pet || pet.hospital) closePanel(true);
                else if (card) card.update(pet, cardCtx(state));
            }
        }

        return {
            enter: function (params) {
                pending = params || {};    // router woła render() zaraz po enter()
            },
            leave: function () {
                closePanel(false);
                pending = null;
                if (room) {
                    room.destroy();
                    room = null;
                }
            },
            render: render,
            setParams: function (params) {
                var state = ctx.state();
                if (state) applyParams(params, state);
                else pending = params;
            },
            /** Dla testów w konsoli: bieżący pokój. */
            _room: function () { return room; },
            _pets: function () { return lastPets; }
        };
    }

    W.scenes.domek = {
        title: 'Domek',
        create: create
    };
})();
