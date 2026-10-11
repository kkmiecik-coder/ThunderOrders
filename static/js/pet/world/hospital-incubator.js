/**
 * Świat pupili — scena „inkubatorium” (spec v3.1 §4.3).
 *
 * - Rząd inkubatorów: lampa nad szklaną kopułą, w środku jajko z rigu (PetRig.mountEgg ze skórką), na
 *   podstawie tabliczka „36% · ~4 dni” (prognoza z ogrzaniem — PetsState.eggForecast). Stany: wylęgane
 *   (zwykłe światło), ogrzane (mocniejsze, cieplejsze), gotowe (iskry, „Gotowe! Wykluj”), wolny (przygaszony).
 * - Miejsc max(3, liczba jajek); jajko zostaje w swoim inkubatorze, gdy inne się wyklują (stałe miejsca).
 *   Siatka (CSS): ≥ 1024 px do 5 w rzędzie, 600–1023 px po 3, < 600 px po 2; nadmiar przewija wnętrze sceny.
 * - Klik w inkubator z jajkiem = okno sceny: źródło, pasek %, czas do wyklucia, ciepło, „Ogrzej” albo
 *   „Wykluj” (PetHatch: animacja + imię, potem domek z panelem nowego pupila). Klik w wolny = okno
 *   „Wolny inkubator” z linkiem do recepcji. `?jajko=ID` otwiera okno jajka (nieznany ID → bez okna).
 * - Jajka czekają na recepcji → tabliczka „Jajka do odebrania na recepcji →” (link do holu).
 * - Zmiana stanu przy otwartym oknie: jajko jest → treść odświeżona (win.replace przy zmianie przycisków,
 *   inaczej same liczby); zniknęło (wyklute w innej karcie) → okno się zamyka, fokus na scenie.
 * Rejestruje się w window.PetsWorld.scenes.inkubatorium.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.inkubatorium) return;

    var MIN_SLOTS = 3;

    // Tył inkubatora: przewód, klosz lampy, cień, podstawa (viewBox 120×190)
    var BACK_SVG =
        '<svg class="pets-incubator__back" viewBox="0 0 120 190" aria-hidden="true" focusable="false">' +
        '<path class="inc-cord" d="M60 0v24"/>' +
        '<path class="inc-shade" d="M42 22h36l13 20H29z"/>' +
        '<ellipse class="inc-bulb" cx="60" cy="44" rx="11" ry="5"/>' +
        '<ellipse class="inc-shadow" cx="60" cy="186" rx="50" ry="4"/>' +
        '</svg>';

    // Przód: szklana kopuła z odblaskiem i podstawa z wywietrznikami
    var FRONT_SVG =
        '<svg class="pets-incubator__front" viewBox="0 0 120 190" aria-hidden="true" focusable="false">' +
        '<path class="inc-dome" d="M22 148v-40a38 38 0 0 1 76 0v40z"/>' +
        '<path class="inc-shine" d="M33 120v-12a27 27 0 0 1 13-23"/>' +
        '<rect class="inc-rim" x="8" y="142" width="104" height="10" rx="5"/>' +
        '<rect class="inc-base" x="13" y="150" width="94" height="34" rx="9"/>' +
        '<g class="inc-vents"><circle cx="24" cy="160" r="2"/><circle cx="96" cy="160" r="2"/></g>' +
        '</svg>';

    function star(x, y, r) {
        var k = r * 0.28;
        return '<path d="M' + x + ' ' + (y - r) + 'L' + (x + k) + ' ' + (y - k) + 'L' + (x + r) + ' ' + y + 'L' + (x + k) + ' ' + (y + k) +
            'L' + x + ' ' + (y + r) + 'L' + (x - k) + ' ' + (y + k) + 'L' + (x - r) + ' ' + y + 'L' + (x - k) + ' ' + (y - k) + 'Z"/>';
    }

    // Iskry gotowego jajka
    var SPARKS_SVG =
        '<svg class="pets-incubator__sparks" viewBox="0 0 120 190" aria-hidden="true" focusable="false">' +
        star(26, 92, 7) + star(97, 100, 6) + star(88, 70, 5) + star(34, 66, 4.5) + '</svg>';

    var POSTER_SVG =
        '<svg viewBox="0 0 80 96" aria-hidden="true" focusable="false">' +
        '<rect class="poster-frame" x="2" y="2" width="76" height="92" rx="8"/>' +
        '<rect class="poster-paper" x="9" y="9" width="62" height="78" rx="4"/>' +
        '<path class="poster-egg" d="M40 22c9 0 15 14 15 23a15 15 0 0 1-30 0c0-9 6-23 15-23z"/>' +
        '<path class="poster-heart" d="M40 76s-11-6.5-11-13.5a6 6 0 0 1 11-3.3 6 6 0 0 1 11 3.3C51 69.5 40 76 40 76z"/>' +
        '</svg>';

    var ARROW_SVG =
        '<svg class="pets-inc__note-arrow" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" ' +
        'stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg>';

    function create(ctx, host) {
        var H = window.PetsHospital;
        var u = ctx.u;
        var el = u.el;
        var R = function () { return window.PetRig; };

        var lastState = null;
        var slots = [];              // id jajka albo null (wolny) — stałe miejsca
        var views = [];              // widok inkubatora na miejsce
        var open = null;             // {type: 'egg', id} | {type: 'free', slot}
        var openSig = null;
        var refs = null;             // elementy okna jajka odświeżane co sekundę
        var pending = null;          // parametry z adresu czekające na stan
        var hatching = null;         // id jajka w trakcie wyklucia (nakładka PetHatch)

        // --- szkielet -------------------------------------------------------------------------
        var stage = el('div', 'pets-stage pets-inc');
        var floor = el('div', 'pets-inc__floor');
        floor.setAttribute('aria-hidden', 'true');
        var poster = el('div', 'pets-inc__poster');
        poster.setAttribute('aria-hidden', 'true');
        poster.innerHTML = POSTER_SVG;
        var scroll = el('div', 'pets-scroll pets-inc__scroll');
        scroll.setAttribute('data-window-backdrop', '');
        var note = el('a', 'pets-inc__note');
        note.href = ctx.href('szpital');
        note.dataset.sceneLink = 'szpital';
        note.appendChild(el('span', 'pets-inc__note-text', 'Jajka do odebrania na recepcji'));
        note.insertAdjacentHTML('beforeend', ARROW_SVG);
        note.hidden = true;
        var row = el('div', 'pets-inc__row');
        scroll.appendChild(note);
        scroll.appendChild(row);
        stage.appendChild(floor);
        stage.appendChild(poster);
        stage.appendChild(scroll);
        host.appendChild(stage);

        var win = window.PetsSceneWindow ? window.PetsSceneWindow.attach(host) : null;

        function findEgg(state, id) {
            var list = (state && state.eggs) || [];
            for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
            return null;
        }

        // --- inkubatory -----------------------------------------------------------------------
        function slotView(i) {
            var b = el('button', 'pets-incubator');
            b.type = 'button';
            b.dataset.incSlot = String(i);
            b.innerHTML = BACK_SVG;
            var glow = el('span', 'pets-incubator__glow');
            glow.setAttribute('aria-hidden', 'true');
            var eggBox = el('span', 'pets-incubator__egg');
            eggBox.setAttribute('aria-hidden', 'true');
            b.appendChild(glow);
            b.appendChild(eggBox);
            b.insertAdjacentHTML('beforeend', FRONT_SVG + SPARKS_SVG);
            var plate = el('span', 'pets-incubator__plate');
            plate.setAttribute('aria-hidden', 'true');
            b.appendChild(plate);
            return { el: b, eggBox: eggBox, plate: plate, rig: null, eggId: undefined, egg: null, rigSig: '' };
        }

        function destroyView(view) {
            if (view.rig) view.rig.destroy();
            if (view.el.parentNode) view.el.parentNode.removeChild(view.el);
        }

        function setText(node, text) {
            if (node.textContent !== text) node.textContent = text;
        }

        function eggLabel(egg, st) {
            var name = H.eggTitle(egg.source).toLowerCase();
            if (st.ready) return 'Inkubator: ' + name + ' — gotowe do wyklucia';
            var eta = st.eta ? (st.eta.indexOf('za') === 0 ? st.eta : 'za ' + st.eta) : '';
            return 'Inkubator: ' + name + ', ' + st.pct + '%' + (eta ? ', wykluje się ' + eta : '') + (st.boosted ? ', ogrzane' : '');
        }

        function tickSlot(view, state) {
            var egg = view.egg;
            var b = view.el;
            var label;
            if (!egg) {
                b.classList.add('is-free');
                b.classList.remove('is-ready', 'is-boosted');
                setText(view.plate, 'wolny');
                label = 'Wolny inkubator';
            } else {
                var st = H.eggStatus(egg, state, u);
                b.classList.remove('is-free');
                b.classList.toggle('is-ready', st.ready);
                b.classList.toggle('is-boosted', st.boosted);
                var sig = [st.pct, st.boosted, st.ready].join('|');
                if (view.rig && sig !== view.rigSig) {
                    view.rigSig = sig;
                    view.rig.update({ pct: st.pct, boosted: st.boosted, ready: st.ready });
                }
                setText(view.plate, st.plate);
                label = eggLabel(egg, st);
            }
            if (b.getAttribute('aria-label') !== label) b.setAttribute('aria-label', label);
        }

        function updateSlot(view, egg, state) {
            var id = egg ? egg.id : null;
            if (view.eggId !== id) {
                if (view.rig) view.rig.destroy();
                view.rig = null;
                view.rigSig = '';
                view.eggId = id;
                if (egg && R()) {
                    view.rig = R().mountEgg(view.eggBox, {
                        pct: egg.progress_pct, boosted: !!egg.boost_until, ready: !!egg.ready, size: 'mini', skin: egg.skin || 0
                    });
                }
            } else if (egg && view.rig && view.egg && view.egg.skin !== egg.skin) {
                view.rig.update({ skin: egg.skin || 0 });
            }
            view.egg = egg;
            if (egg) view.el.dataset.eggId = String(egg.id);
            else delete view.el.dataset.eggId;
            tickSlot(view, state);
        }

        function syncViews(state) {
            while (views.length < slots.length) {
                var v = slotView(views.length);
                views.push(v);
                row.appendChild(v.el);
            }
            while (views.length > slots.length) destroyView(views.pop());
            slots.forEach(function (id, i) { updateSlot(views[i], id == null ? null : findEgg(state, id), state); });
        }

        function slotOf(id) {
            var i = slots.indexOf(id);
            return i >= 0 ? views[i] : null;
        }

        function markSelected(view) {
            views.forEach(function (v) { v.el.classList.toggle('is-selected', v === view); });
        }

        // --- okna -----------------------------------------------------------------------------
        function eggSig(egg) {
            return [egg.id, egg.source, !!egg.ready, egg.can_warm !== false, !!egg.boost_until].join('|');
        }

        function fillEgg(r) {
            var st = H.eggStatus(r.egg, lastState, u);
            r.bar.set(st.pct);
            setText(r.pct, st.pct + '%');
            var eta;
            if (st.ready) eta = 'Gotowe do wyklucia!';
            else if (!st.eta) eta = '';
            else eta = 'Wykluje się ' + (st.eta.indexOf('za') === 0 ? st.eta : 'za ' + st.eta) + '.';
            setText(r.eta, eta);
            r.eta.hidden = !eta;
            var heat = '';
            if (!st.ready) {
                if (st.boosted) heat = st.heat;
                else if (r.egg.can_warm !== false) heat = 'Ogrzej je, żeby wykluło się szybciej.';
            }
            setText(r.heat, heat);
            r.heat.hidden = !heat;
        }

        function eggContent(egg) {
            var box = el('div', 'pets-hosp-win pets-hosp-win--egg');
            var title = el('h2', 'pets-window__title', H.eggTitle(egg.source));
            title.id = 'petsIncWinTitle';
            box.appendChild(title);
            var meter = el('div', 'pets-hosp-win__meter');
            var bar = H.progress(u, 'Postęp inkubacji', false);
            var pct = el('span', 'pets-hosp-win__pct');
            pct.setAttribute('aria-hidden', 'true');
            meter.appendChild(bar.el);
            meter.appendChild(pct);
            box.appendChild(meter);
            var eta = el('p', 'pets-window__text pets-hosp-win__eta');
            var heat = el('p', 'pets-window__text pets-hosp-win__heat');
            heat.id = 'petsIncHeat';
            box.appendChild(eta);
            box.appendChild(heat);
            var actions = el('div', 'pets-window__actions');
            var btn;
            if (egg.ready) {
                btn = u.button('Wykluj', 'sparkle', 'primary', { incAction: 'hatch', eggId: String(egg.id) });
                btn.setAttribute('data-window-key', 'hatch');
            } else {
                btn = u.button('Ogrzej', 'flame', null, { incAction: 'warm', eggId: String(egg.id) });
                btn.setAttribute('data-window-key', 'warm');
                if (egg.can_warm === false) {
                    // Zostaje fokusowalny (aria-disabled), a powód czyta się z linii o cieple
                    btn.setAttribute('aria-disabled', 'true');
                    btn.setAttribute('aria-describedby', heat.id);
                }
            }
            actions.appendChild(btn);
            box.appendChild(actions);
            refs = { egg: egg, bar: bar, pct: pct, eta: eta, heat: heat };
            fillEgg(refs);
            return box;
        }

        function freeContent() {
            var box = el('div', 'pets-hosp-win pets-hosp-win--free');
            var title = el('h2', 'pets-window__title', 'Wolny inkubator');
            title.id = 'petsIncWinTitle';
            box.appendChild(title);
            var waiting = H.eggsToClaimCount(lastState);
            box.appendChild(el('p', 'pets-window__text', 'Nowe jajka odbierzesz na recepcji.' +
                (waiting ? ' Właśnie czeka tam ' + (waiting === 1 ? 'jedno jajko' : waiting + ' ' + u.plural(waiting, 'jajko', 'jajka', 'jajek')) + '!' : '')));
            var actions = el('div', 'pets-window__actions');
            var link = el('a', 'pet-btn' + (waiting ? ' pet-btn--primary' : ''));
            link.href = ctx.href('szpital');
            link.dataset.sceneLink = 'szpital';
            link.innerHTML = u.icon('back') + '<span class="pet-btn__label"></span>';
            link.querySelector('.pet-btn__label').textContent = 'Do recepcji';
            link.setAttribute('data-window-key', 'reception');
            actions.appendChild(link);
            box.appendChild(actions);
            refs = null;
            return box;
        }

        function freeSig() {
            return 'free|' + H.eggsToClaimCount(lastState);
        }

        function onWindowClosed() {
            open = null;
            openSig = null;
            refs = null;
            markSelected(null);
            if (ctx.isActive('inkubatorium')) ctx.setQuery({});
        }

        function show(content, returnFocus, focus) {
            win.open({
                content: content, labelledBy: 'petsIncWinTitle', returnFocus: returnFocus || null,
                onClose: onWindowClosed, closeLabel: 'Zamknij okno inkubatora', focus: focus
            });
        }

        function openEgg(id, focus) {
            var egg = findEgg(lastState, id);
            var view = slotOf(id);
            if (!win || !egg || !view) return false;
            open = { type: 'egg', id: id };
            openSig = eggSig(egg);
            show(eggContent(egg), view.el, focus);
            markSelected(view);
            ctx.setQuery({ jajko: id });
            H.reveal(host, scroll, view.el);
            return true;
        }

        function openFree(slot) {
            var view = views[slot];
            if (!win || !view) return;
            open = { type: 'free', slot: slot };
            openSig = freeSig();
            show(freeContent(), view.el);
            markSelected(view);
            ctx.setQuery({});
            H.reveal(host, scroll, view.el);
        }

        function openSlot(i) {
            var id = slots[i];
            if (id != null) openEgg(id);
            else openFree(i);
        }

        /** Stan zmienił się przy otwartym oknie (odświeżenie, druga karta, własna akcja). */
        function refreshWindow(state) {
            if (!open || !win || !win.isOpen()) return;
            if (open.type === 'free') {
                var taken = slots[open.slot];
                if (taken != null) {
                    // Do wolnego inkubatora trafiło jajko (odebrane w innej karcie) — okno pokazuje to jajko
                    var egg0 = findEgg(state, taken);
                    open = { type: 'egg', id: taken };
                    openSig = eggSig(egg0);
                    win.replace(eggContent(egg0));
                    ctx.setQuery({ jajko: taken });
                } else if (freeSig() !== openSig) {
                    openSig = freeSig();
                    win.replace(freeContent());
                }
                return;
            }
            var egg = findEgg(state, open.id);
            if (!egg) {
                if (hatching === open.id) return;     // nakładka wyklucia jeszcze trwa — okno zamknie się po niej
                H.closeGone(win, host);
                return;
            }
            if (eggSig(egg) !== openSig) {
                openSig = eggSig(egg);
                win.replace(eggContent(egg));
            } else if (refs) {
                refs.egg = egg;
                fillEgg(refs);
            }
        }

        // --- akcje ------------------------------------------------------------------------------
        function flashLamp(id) {
            var view = slotOf(id);
            if (!view || u.reducedMotion()) return;
            view.el.classList.remove('is-warming');
            void view.el.offsetWidth;
            view.el.classList.add('is-warming');
            setTimeout(function () { view.el.classList.remove('is-warming'); }, 1000);
        }

        function warmEgg(btn) {
            var id = parseInt(btn.dataset.eggId, 10);
            u.setBusy(btn, true);
            H.warm(ctx, id).then(function () {
                flashLamp(id);
            }, function () {
                if (btn.isConnected) u.setBusy(btn, false);
            });
        }

        function hatchEgg(btn) {
            if (hatching != null) return;
            var id = parseInt(btn.dataset.eggId, 10);
            var egg = findEgg(lastState, id);
            if (!egg) return;
            hatching = id;
            u.setBusy(btn, true);
            H.hatch(ctx, egg).then(function (res) {
                hatching = null;
                // Nowy pupil mieszka w domku — tam z jego panelem (duplikat: pupil z nową gwiazdką)
                var target = res && (res.result === 'dupe' ? res.starred_pet_id : res.pet_id);
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                if (target && ctx.isActive('inkubatorium')) ctx.go('domek', { pupil: target });
                else if (lastState) render(lastState);
            }, function () {
                // Błąd pokazał ctx.send (toast), nakładka zamknęła się sama
                hatching = null;
                if (btn.isConnected) u.setBusy(btn, false);
                if (lastState) render(lastState);
            });
        }

        host.addEventListener('click', function (e) {
            var slot = e.target.closest('[data-inc-slot]');
            if (slot && host.contains(slot)) {
                openSlot(parseInt(slot.dataset.incSlot, 10));
                return;
            }
            var btn = e.target.closest('[data-inc-action]');
            if (!btn || !host.contains(btn) || btn.disabled || btn.getAttribute('aria-disabled') === 'true') return;
            if (btn.dataset.incAction === 'warm') warmEgg(btn);
            else if (btn.dataset.incAction === 'hatch') hatchEgg(btn);
        });

        // --- parametry z adresu (?jajko=ID) ------------------------------------------------------------
        function applyParams(params, state) {
            pending = null;
            var id = params && params.jajko;
            if (!id) {
                if (open && open.type === 'egg' && win && win.isOpen()) win.close({ restoreFocus: false });
                return;
            }
            if (!findEgg(state, id)) {
                // Wyklute, cudze albo nieistniejące: sala bez okna, adres bez parametru
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                ctx.setQuery({});
                return;
            }
            if (open && open.type === 'egg' && open.id === id && win.isOpen()) return;
            openEgg(id);
        }

        // --- render ----------------------------------------------------------------------------------
        function render(state) {
            lastState = state;
            slots = H.syncSlots(slots, (state.eggs || []).map(function (e) { return e.id; }), MIN_SLOTS, null);
            syncViews(state);
            row.style.setProperty('--n', String(slots.length));     // kolumn najwyżej tyle, ile miejsc (CSS)
            note.hidden = !(state.eggs_available || []).length;
            stage.classList.toggle('has-note', !note.hidden);
            if (pending) {
                applyParams(pending, state);
                return;
            }
            refreshWindow(state);
        }

        return {
            enter: function (params) {
                pending = params || {};      // router woła render() zaraz po enter()
            },
            leave: function () {
                pending = null;
                hatching = null;
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                // Ukryta scena nie trzyma żywych rigów — render zbuduje je od nowa
                while (views.length) destroyView(views.pop());
                slots = [];
            },
            render: render,
            setParams: function (params) {
                var state = ctx.state();
                if (state) applyParams(params, state);
                else pending = params;
            },
            tick: function () {
                var state = ctx.state();
                if (!state) return;
                views.forEach(function (v) { tickSlot(v, state); });
                if (refs && open && open.type === 'egg') fillEgg(refs);
            }
        };
    }

    W.scenes.inkubatorium = {
        title: 'Inkubatorium',
        create: create
    };
})();
