/**
 * Świat pupili — scena „domek” (spec v3 §6.1–6.2): pokój (PetRoom) + panel pupila (PetCard).
 *
 * - Klik w pupila → room.focus(id) + panel (arkusz od dołu < 1024 px, panel z boku ≥ 1024 px);
 *   drugi klik w tego samego pupila przy otwartym panelu = pat pat (dłoń w rigu + paczka w pets.js).
 * - Zamknięcie panelu: przeciągnięcie uchwytu w dół, klik w pokój (poza pupilem), ESC, przycisk ×.
 * - `?pupil=ID` otwiera panel; pupil w szpitalu → przekierowanie sceny na szpital (replaceState);
 *   pupil nieistniejący / odeszły → pokój bez panelu i bez błędu (Review Focus 5). Otwarty panel
 *   aktualizuje adres przez replaceState (bez nowych wpisów historii).
 * Rejestruje się w window.PetsWorld.scenes.domek.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.domek) return;

    var DESKTOP = '(min-width: 1024px)';
    var DRAG_CLOSE_PX = 90;

    function create(ctx, host) {
        var u = ctx.u;
        var room = null;
        var card = null;
        var openId = null;
        var pending = null;          // parametry z adresu czekające na stan
        var lastPets = [];

        var wrap = u.el('div', 'pets-house');
        var stage = u.el('div', 'pets-house__stage');
        var tip = u.el('p', 'pets-house__tip', 'Kliknij pupila, żeby się nim zająć. Kliknij go jeszcze raz, żeby go pogłaskać.');
        var away = u.el('p', 'pets-house__away');
        away.hidden = true;
        var intro = u.el('div', 'pets-house__intro pets-block');
        intro.hidden = true;
        stage.appendChild(tip);

        var sheet = u.el('aside', 'pet-sheet');
        sheet.hidden = true;
        var grip = u.el('div', 'pet-sheet__grip');
        grip.setAttribute('aria-hidden', 'true');
        grip.appendChild(u.el('span', 'pet-sheet__grip-bar'));
        var closeBtn = u.el('button', 'pet-sheet__close');
        closeBtn.type = 'button';
        closeBtn.setAttribute('aria-label', 'Zamknij panel pupila');
        closeBtn.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
        var body = u.el('div', 'pet-sheet__body');
        sheet.appendChild(grip);
        sheet.appendChild(closeBtn);
        sheet.appendChild(body);

        wrap.appendChild(stage);
        wrap.appendChild(sheet);
        wrap.appendChild(away);
        wrap.appendChild(intro);
        host.appendChild(wrap);

        function isDesktop() {
            return !!(window.matchMedia && window.matchMedia(DESKTOP).matches);
        }

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
            room = window.PetRoom.mount(stage, {
                pets: homePets(state),
                night: !!(state && state.night && state.night.is_night),
                compact: false,
                interactive: true,
                onPetClick: onPetClick
            });
            stage.insertBefore(room.el, tip);
            room.el.addEventListener('click', function (e) {
                if (!e.target.closest('.pet-room__pet') && openId != null) closePanel(false);
            });
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
                ctx.go('szpital', { pupil: pet.id });
                return resp;
            });
        }

        function openPanel(id, o) {
            o = o || {};
            var state = ctx.state();
            var pet = ctx.findPet(id, state);
            if (!pet || pet.hospital || !window.PetCard) return false;
            if (card) {
                card.destroy();
                card = null;
            }
            ctx.flushPats();
            openId = id;
            if (room) room.focus(id);
            card = window.PetCard.render(body, pet, {
                onAction: onAction, onPlay: onPlay, onRename: onRename, onAdmit: onAdmit,
                onStars: function (p) { if (room) room.playAction(p.id, 'celebrate'); },
                now: cardCtx(state).now, night: cardCtx(state).night, config: cardCtx(state).config
            });
            sheet.setAttribute('aria-label', 'Panel pupila ' + (pet.name || ''));
            sheet.hidden = false;
            sheet.classList.remove('is-dragging');
            sheet.style.removeProperty('--drag');
            void sheet.offsetWidth;
            sheet.classList.add('is-open');
            wrap.classList.add('has-panel');
            ctx.setQuery({ pupil: id });
            if (!isDesktop() && room) {
                // Arkusz zasłania dół ekranu — pokój z pupilem ma być nad nim
                var top = room.el.getBoundingClientRect().top + window.pageYOffset - 12;
                if (Math.abs(window.pageYOffset - top) > 4) {
                    window.scrollTo({ top: Math.max(0, top), behavior: u.reducedMotion() ? 'auto' : 'smooth' });
                }
            }
            if (o.focusPanel) card.focus();
            return true;
        }

        function closePanel(returnFocus) {
            if (openId == null) return;
            var id = openId;
            openId = null;
            ctx.flushPats();
            if (card) {
                card.destroy();
                card = null;
            }
            sheet.classList.remove('is-open', 'is-dragging');
            sheet.style.removeProperty('--drag');
            wrap.classList.remove('has-panel');
            sheet.hidden = true;
            if (room) room.focus(null);
            if (ctx.isActive('domek')) ctx.setQuery({});
            if (returnFocus && room) {
                var btn = room.petButton(id);
                if (btn) btn.focus();
            }
        }

        closeBtn.addEventListener('click', function () { closePanel(true); });

        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape' || openId == null || !ctx.isActive('domek') || e.defaultPrevented) return;
            e.preventDefault();
            closePanel(true);
        });

        // Przeciągnięcie uchwytu w dół zamyka arkusz (telefon); pointer events = mysz, dotyk i rysik
        var drag = null;
        grip.addEventListener('pointerdown', function (e) {
            if (isDesktop() || openId == null) return;
            drag = { y0: e.clientY, dy: 0, id: e.pointerId };
            try { grip.setPointerCapture(e.pointerId); } catch (err) { /* stare przeglądarki */ }
            sheet.classList.add('is-dragging');
        });
        grip.addEventListener('pointermove', function (e) {
            if (!drag || e.pointerId !== drag.id) return;
            drag.dy = Math.max(0, e.clientY - drag.y0);
            sheet.style.setProperty('--drag', drag.dy + 'px');
        });
        function endDrag(e) {
            if (!drag || (e && e.pointerId !== drag.id)) return;
            var dy = drag.dy;
            drag = null;
            sheet.classList.remove('is-dragging');
            sheet.style.removeProperty('--drag');
            if (dy > DRAG_CLOSE_PX) closePanel(false);
        }
        grip.addEventListener('pointerup', endDrag);
        grip.addEventListener('pointercancel', endDrag);

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
            link.href = ctx.href('szpital');
            link.dataset.sceneLink = 'szpital';
            away.appendChild(link);
        }

        function renderIntro(state, empty) {
            intro.hidden = !empty;
            tip.hidden = empty;
            if (!empty) return;
            var hasEgg = (state.eggs || []).length > 0 || (state.eggs_available || []).length > 0;
            var sig = (hasEgg ? 'egg' : 'none') + '|' + (state.night ? state.night.start + '-' + state.night.end : '');
            if (intro.dataset.sig === sig) return;
            intro.dataset.sig = sig;
            intro.innerHTML = '';
            intro.appendChild(u.el('h2', 'pets-block__title', hasEgg ? 'Domek czeka na pierwszego lokatora' : 'W domku nikogo teraz nie ma'));
            var list = u.el('ul', 'pets-house__rules');
            var night = state.night || {};
            [
                'Jajka odbierasz i wykluwasz w szpitalu (inkubatornia). Ogrzewaj je przy każdej wizycie — tak wyklują się szybciej.',
                'Każde jajko to losowy z ośmiu gatunków. Zbierz wszystkie w albumie w ogrodzie wspomnień!',
                'Karm, baw się i myj pupila. Jedna wizyta dziennie wystarczy, żeby był zdrowy, dwie–trzy — żeby był szczęśliwy.',
                'W nocy (' + (night.start != null && night.start !== night.end ? night.start + ':00–' + night.end + ':00' : '23:00–7:00') +
                    ') pupil śpi. Zaniedbany choruje — wtedy zabierz go do szpitala.'
            ].forEach(function (text) { list.appendChild(u.el('li', null, text)); });
            intro.appendChild(list);
            var go = u.el('a', 'pet-btn pet-btn--primary pets-house__go');
            go.href = ctx.href('szpital');
            go.dataset.sceneLink = 'szpital';
            go.textContent = hasEgg ? 'Do inkubatorni' : 'Do szpitala';
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
                ctx.go('szpital', { pupil: id }, { replace: true });
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
                var pet = ctx.findPet(openId, state);
                if (!pet || pet.hospital) closePanel(false);
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
        lead: 'Tu mieszkają Twoje pupile. Po zachowaniu poznasz, czego im trzeba.',
        create: create
    };
})();
