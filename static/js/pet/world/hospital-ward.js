/**
 * Świat pupili — scena „izba” = Izba przyjęć (spec v3.1 §4.4).
 *
 * - Sala z łóżkami: pupil w pozie `bed` (rig: łóżeczko z kołderką), przy leczonych kroplówka, tabliczka
 *   „Burek · jeszcze ~3 h”. Wyzdrowiały: łóżko jaśniejsze, pupil szczęśliwy (need: happy) z serduszkami,
 *   zielona tabliczka „Zdrowy! Odbierz” + „tęskni za domem”. Wolne łóżka zaścielone i przygaszone.
 * - Miejsc max(3, liczba pupili w szpitalu), a gdy w domku ktoś choruje — o jedno wolne więcej (inaczej przy
 *   pełnej sali nie byłoby gdzie go przyjąć); pupil zostaje w swoim łóżku, przyjęty z wolnego łóżka trafia
 *   właśnie do niego. Siatka (CSS): ≥ 1024 px do 4 w rzędzie, 600–1023 px po 3, < 600 px po 2.
 * - Klik w łóżko z pupilem = okno sceny (fokus zostaje na łóżku): imię, pasek leczenia, czas / tęsknota,
 *   „Odbierz” (wyzdrowiały) albo „Zabierz wcześniej” z potwierdzeniem („Tak, zabieram” / „Zostaw
 *   w szpitalu”) — teksty jak dawniej. Klik w pupila przy jego otwartym oknie = pat pat (paczki w pets.js).
 *   Po odbiorze → domek z panelem pupila.
 * - Wolne łóżko przy chorych w domku: pulsujący „+”; klik = okno „Kogo przyjąć?” (mini rig, imię, nastrój,
 *   „wyzdrowieje w najwyżej N h” z config.hospital_hours, „Przyjmij” → POST /<id>/szpital → pupil w tym
 *   łóżku, okno pokazuje jego). Bez chorych: okno „Wolne łóżko”.
 * - `?pupil=ID` otwiera okno pupila w szpitalu; pupil spoza szpitala / nieistniejący → sala bez okna.
 * - Zmiana stanu przy otwartym oknie: pupil leży → treść odświeżona; zniknął (odebrany w innej karcie,
 *   odszedł) → okno się zamyka, fokus na scenie.
 * Rejestruje się w window.PetsWorld.scenes.izba.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.izba) return;

    var MIN_SLOTS = 3;

    // Kroplówka: stojak na kółkach, worek z płynem, kapiąca kropla, wężyk do łóżka (viewBox 40×160)
    var DRIP_SVG =
        '<svg viewBox="0 0 40 160" aria-hidden="true" focusable="false">' +
        '<path class="drip-pole" d="M24 10v140"/>' +
        '<path class="drip-hook" d="M15 12h18"/>' +
        '<path class="drip-feet" d="M10 156l14-8 14 8"/>' +
        '<rect class="drip-bag" x="11" y="14" width="22" height="32" rx="7"/>' +
        '<path class="drip-liquid" d="M13 30h18v8a5 5 0 0 1-5 5h-8a5 5 0 0 1-5-5z"/>' +
        '<rect class="drip-chamber" x="18" y="48" width="6" height="11" rx="2"/>' +
        '<circle class="drip-drop" cx="21" cy="52" r="1.6"/>' +
        '<path class="drip-tube" d="M21 59c0 22-6 34-30 44"/>' +
        '</svg>';

    // Puste łóżko — ta sama bryła co łóżeczko rigu (pose 'bed'), kołderka zaścielona na płasko
    var EMPTY_BED_SVG =
        '<svg class="pets-bed__empty" viewBox="0 0 200 200" aria-hidden="true" focusable="false">' +
        '<rect class="eb-post" x="27" y="62" width="10" height="132" rx="5"/><rect class="eb-post" x="163" y="62" width="10" height="132" rx="5"/>' +
        '<rect class="eb-board" x="34" y="72" width="132" height="84" rx="16"/>' +
        '<path class="eb-cross" d="M45 82h6v6h6v6h-6v6h-6v-6h-6v-6h6z"/>' +
        '<path class="eb-pillow" d="M50 142c0-13 20-19 50-19s50 6 50 19-20 17-50 17-50-4-50-17z"/>' +
        '<rect class="eb-mattress" x="24" y="176" width="152" height="12" rx="6"/>' +
        '<path class="eb-quilt" d="M28 162q36-5 72-3q36-2 72 3v18q0 8-8 8H36q-8 0-8-8z"/>' +
        '<path class="eb-fold" d="M30 166q35-5 70-3q35-2 70 3"/>' +
        '<circle class="eb-wheel" cx="32" cy="196" r="4"/><circle class="eb-wheel" cx="168" cy="196" r="4"/>' +
        '</svg>';

    var HEART = 'M0 4.5C0 2 2-.2 4.2.6 5.3 1 6 2 6 2s.7-1 1.8-1.4C10-.2 12 2 12 4.5 12 8.4 6 12 6 12S0 8.4 0 4.5z';
    var HEARTS_SVG =
        '<svg viewBox="0 0 60 40" aria-hidden="true" focusable="false">' +
        '<path transform="translate(6 20)" d="' + HEART + '"/>' +
        '<path transform="translate(26 6) scale(1.3)" d="' + HEART + '"/>' +
        '<path transform="translate(44 18) scale(.9)" d="' + HEART + '"/>' +
        '</svg>';

    var PLUS_SVG =
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="3" ' +
        'stroke-linecap="round"><path d="M12 6v12M6 12h12"/></svg>';

    var WINDOW_SVG =
        '<svg viewBox="0 0 120 90" aria-hidden="true" focusable="false">' +
        '<rect class="ww-frame" x="2" y="2" width="116" height="86" rx="8"/>' +
        '<rect class="ww-sky" x="9" y="9" width="102" height="72" rx="4"/>' +
        '<circle class="ww-sun" cx="88" cy="28" r="9"/>' +
        '<ellipse class="ww-cloud" cx="38" cy="30" rx="16" ry="6"/><ellipse class="ww-cloud" cx="50" cy="26" rx="10" ry="6"/>' +
        '<path class="ww-hill" d="M9 70q26-16 52-6t50-4v21H9z"/>' +
        '<path class="ww-bar" d="M60 9v72M9 45h102"/>' +
        '</svg>';

    var MOOD_TEXT = { chory: 'Chory', krytyczny: 'W stanie krytycznym' };

    function create(ctx, host) {
        var H = window.PetsHospital;
        var u = ctx.u;
        var el = u.el;
        var R = function () { return window.PetRig; };

        var lastState = null;
        var slots = [];              // id pupila albo null (wolne łóżko) — stałe miejsca
        var views = [];
        var prefer = {};             // id przyjmowanego pupila → łóżko, z którego go przyjęto
        var open = null;             // {type: 'bed', id} | {type: 'free', slot}
        var openSig = null;
        var refs = null;             // elementy okna pupila odświeżane co sekundę
        var confirm = false;         // „Zabierz wcześniej” czeka na potwierdzenie
        var winRigs = [];            // mini rigi w oknie „Kogo przyjąć?”
        var pending = null;
        var admitting = null;
        var discharging = null;

        // --- szkielet -------------------------------------------------------------------------
        var stage = el('div', 'pets-stage pets-ward');
        var floor = el('div', 'pets-ward__floor');
        floor.setAttribute('aria-hidden', 'true');
        var wallWindow = el('div', 'pets-ward__window');
        wallWindow.setAttribute('aria-hidden', 'true');
        wallWindow.innerHTML = WINDOW_SVG;
        var scroll = el('div', 'pets-scroll pets-ward__scroll');
        scroll.setAttribute('data-window-backdrop', '');
        var row = el('div', 'pets-ward__row');
        scroll.appendChild(row);
        stage.appendChild(floor);
        stage.appendChild(wallWindow);
        stage.appendChild(scroll);
        host.appendChild(stage);

        var win = window.PetsSceneWindow ? window.PetsSceneWindow.attach(host) : null;

        function findHosp(state, id) {
            var list = H.inBed(state);
            for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
            return null;
        }

        function setText(node, text) {
            if (node.textContent !== text) node.textContent = text;
        }

        // --- łóżka ----------------------------------------------------------------------------
        function bedView(i) {
            var b = el('button', 'pets-bed');
            b.type = 'button';
            b.dataset.bedSlot = String(i);
            var scene = el('span', 'pets-bed__scene');
            scene.setAttribute('aria-hidden', 'true');
            var glow = el('span', 'pets-bed__glow');
            var drip = el('span', 'pets-bed__drip');
            drip.innerHTML = DRIP_SVG;
            var art = el('span', 'pets-bed__art');
            var hearts = el('span', 'pets-bed__hearts');
            hearts.innerHTML = HEARTS_SVG;
            var plus = el('span', 'pets-bed__plus');
            plus.innerHTML = PLUS_SVG;
            [glow, drip, art, hearts, plus].forEach(function (n) { scene.appendChild(n); });
            var plate = el('span', 'pets-bed__plate');
            plate.setAttribute('aria-hidden', 'true');
            var main = el('span', 'pets-bed__plate-main');
            var sub = el('span', 'pets-bed__plate-sub');
            plate.appendChild(main);
            plate.appendChild(sub);
            b.appendChild(scene);
            b.appendChild(plate);
            return { el: b, art: art, main: main, sub: sub, rig: null, petId: undefined, pet: null };
        }

        function destroyView(view) {
            if (view.rig) view.rig.destroy();
            if (view.el.parentNode) view.el.parentNode.removeChild(view.el);
        }

        function tickBed(view) {
            var pet = view.pet;
            var b = view.el;
            var label;
            if (!pet) {
                var canAdmit = H.sickAtHome(lastState).length > 0;
                b.classList.add('is-free');
                b.classList.remove('is-ready', 'is-healing');
                b.classList.toggle('can-admit', canAdmit);
                setText(view.main, 'wolne łóżko');
                setText(view.sub, canAdmit ? 'przyjmij chorego' : '');
                label = 'Wolne łóżko' + (canAdmit ? ' — możesz przyjąć chorego pupila' : '');
            } else {
                var st = H.healStatus(pet, u);
                var name = H.petName(pet, u);
                b.classList.remove('is-free', 'can-admit');
                b.classList.toggle('is-ready', st.ready);
                b.classList.toggle('is-healing', !st.ready);
                if (st.ready) {
                    setText(view.main, 'Zdrowy! Odbierz');
                    setText(view.sub, name + ' tęskni za domem');
                    label = 'Łóżko: ' + name + ', zdrowy — czeka na odbiór, tęskni za domem';
                } else {
                    setText(view.main, name + ' · jeszcze ' + st.left);
                    setText(view.sub, '');
                    label = 'Łóżko: ' + name + ', wraca do zdrowia, jeszcze ' + st.left;
                }
            }
            view.sub.hidden = !view.sub.textContent;
            if (b.getAttribute('aria-label') !== label) b.setAttribute('aria-label', label);
        }

        function updateBed(view, pet) {
            var id = pet ? pet.id : null;
            if (view.petId !== id) {
                if (view.rig) view.rig.destroy();
                view.rig = null;
                view.art.innerHTML = '';
                view.petId = id;
                if (pet && R()) {
                    view.rig = R().mount(view.art, {
                        species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: false,
                        size: 'mini', need: R().needOf ? R().needOf(pet) : 'sick', pose: 'bed'
                    });
                } else if (!pet) {
                    view.art.innerHTML = EMPTY_BED_SVG;
                }
            } else if (pet && view.rig) {
                view.rig.update({ species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: false });
                if (typeof view.rig.setNeed === 'function' && R().needOf) view.rig.setNeed(R().needOf(pet));
            }
            view.pet = pet;
            if (pet) view.el.dataset.petId = String(pet.id);
            else delete view.el.dataset.petId;
            tickBed(view);
        }

        function syncViews(state) {
            while (views.length < slots.length) {
                var v = bedView(views.length);
                views.push(v);
                row.appendChild(v.el);
            }
            while (views.length > slots.length) destroyView(views.pop());
            slots.forEach(function (id, i) { updateBed(views[i], id == null ? null : findHosp(state, id)); });
        }

        function slotOf(id) {
            var i = slots.indexOf(id);
            return i >= 0 ? views[i] : null;
        }

        function markSelected(view) {
            views.forEach(function (v) { v.el.classList.toggle('is-selected', v === view); });
        }

        // --- okno pupila w łóżku -----------------------------------------------------------------
        function bedSig(pet) {
            return [pet.id, pet.name, !!pet.hospital.ready, confirm].join('|');
        }

        function fillBed(r) {
            var st = H.healStatus(r.pet, u);
            r.bar.set(st.pct);
            setText(r.pct, Math.round(st.pct) + '%');
            setText(r.status, st.status);
            setText(r.note, st.note);
        }

        function bedContent(pet) {
            var name = H.petName(pet, u);
            var box = el('div', 'pets-hosp-win pets-hosp-win--bed');
            var title = el('h2', 'pets-window__title', name);
            title.id = 'petsWardWinTitle';
            box.appendChild(title);
            var meter = el('div', 'pets-hosp-win__meter');
            var bar = H.progress(u, 'Leczenie: ' + name, true);
            var pct = el('span', 'pets-hosp-win__pct');
            pct.setAttribute('aria-hidden', 'true');
            meter.appendChild(bar.el);
            meter.appendChild(pct);
            box.appendChild(meter);
            var status = el('p', 'pets-window__text pets-hosp-win__status');
            var note = el('p', 'pets-window__text');
            box.appendChild(status);
            box.appendChild(note);
            var actions = el('div', 'pets-window__actions');
            var btn;
            if (pet.hospital.ready) {
                btn = u.button('Odbierz', 'home', 'primary', { wardAction: 'discharge', petId: String(pet.id) });
                btn.setAttribute('data-window-key', 'discharge');
                actions.appendChild(btn);
            } else if (confirm) {
                var health = Math.round((pet.bars && pet.bars.health) || 0);
                var q = el('p', 'pets-hosp-win__confirm', 'Pupil ' + (pet.name || '') + ' wróci z obecnym zdrowiem (' + health + '%). Zabrać go już teraz?');
                q.setAttribute('role', 'status');
                actions.appendChild(q);
                btn = u.button('Tak, zabieram', 'home', null, { wardAction: 'discharge', petId: String(pet.id) });
                btn.setAttribute('data-window-key', 'early');
                actions.appendChild(btn);
                var keep = u.button('Zostaw w szpitalu', null, 'ghost', { wardAction: 'confirm-cancel', petId: String(pet.id) });
                keep.setAttribute('data-window-key', 'keep');
                actions.appendChild(keep);
            } else {
                btn = u.button('Zabierz wcześniej', null, 'ghost', { wardAction: 'early', petId: String(pet.id) });
                btn.setAttribute('data-window-key', 'early');
                actions.appendChild(btn);
            }
            box.appendChild(actions);
            box.appendChild(el('p', 'pets-hosp-win__tip', 'Kliknij pupila w łóżku, żeby go pogłaskać.'));
            refs = { pet: pet, bar: bar, pct: pct, status: status, note: note };
            fillBed(refs);
            return box;
        }

        // --- okno wolnego łóżka: „Kogo przyjąć?” albo informacja ----------------------------------------
        function dropWinRigs() {
            winRigs.forEach(function (r) { if (r) r.destroy(); });
            winRigs = [];
        }

        function freeSig(state) {
            return 'free|' + H.sickAtHome(state).map(function (p) {
                return [p.id, p.name, p.mood, !!(p.can && p.can.admit), Math.round((p.bars && p.bars.health) || 0)].join(':');
            }).join(',');
        }

        function admitRow(pet, hours) {
            var li = el('li', 'pets-hosp-win__row');
            var art = el('span', 'pets-hosp-win__mini');
            art.setAttribute('aria-hidden', 'true');
            if (R()) {
                winRigs.push(R().mount(art, {
                    species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: pet.asleep,
                    size: 'mini', need: R().needOf ? R().needOf(pet) : 'sick', pose: 'lie'
                }));
            }
            var info = el('div', 'pets-hosp-win__who');
            info.appendChild(el('span', 'pets-hosp-win__name', H.petName(pet, u)));
            var health = Math.round((pet.bars && pet.bars.health) || 0);
            info.appendChild(el('span', 'pets-hosp-win__mood', (MOOD_TEXT[pet.mood] || 'Chory') + ' · zdrowie ' + health + '%'));
            if (hours > 0) info.appendChild(el('span', 'pets-hosp-win__hint', 'Wyzdrowieje w najwyżej ' + hours + ' h'));
            var action = el('div', 'pets-hosp-win__act');
            var btn = u.button('Przyjmij', 'cross', 'primary', { wardAction: 'admit', petId: String(pet.id) });
            btn.setAttribute('data-window-key', 'admit-' + pet.id);
            action.appendChild(btn);
            var ok = !!(pet.can && pet.can.admit);
            if (!ok) {
                btn.setAttribute('aria-disabled', 'true');
                var why = pet.reasons && pet.reasons.admit ? pet.reasons.admit.charAt(0).toUpperCase() + pet.reasons.admit.slice(1) : '';
                if (why) {
                    var reason = el('p', 'pets-hosp-win__reason', why);
                    reason.id = 'petsWardReason' + pet.id;
                    btn.setAttribute('aria-describedby', reason.id);
                    action.appendChild(reason);
                }
            }
            li.appendChild(art);
            li.appendChild(info);
            li.appendChild(action);
            return li;
        }

        function freeContent(state) {
            var sick = H.sickAtHome(state);
            var box = el('div', 'pets-hosp-win pets-hosp-win--free');
            var title = el('h2', 'pets-window__title', sick.length ? 'Kogo przyjąć?' : 'Wolne łóżko');
            title.id = 'petsWardWinTitle';
            box.appendChild(title);
            refs = null;
            if (!sick.length) {
                box.appendChild(el('p', 'pets-window__text', 'Chorego pupila przyjmiesz tu albo z domku.'));
                var actions = el('div', 'pets-window__actions');
                var link = el('a', 'pet-btn');
                link.href = ctx.href('domek');
                link.dataset.sceneLink = 'domek';
                link.innerHTML = u.icon('home') + '<span class="pet-btn__label"></span>';
                link.querySelector('.pet-btn__label').textContent = 'Do domku';
                link.setAttribute('data-window-key', 'house');
                actions.appendChild(link);
                box.appendChild(actions);
                return box;
            }
            box.appendChild(el('p', 'pets-window__text', 'W szpitalu chory pupil wraca do zdrowia, a jego potrzeby nie rosną.'));
            var hours = parseInt(state.config && state.config.hospital_hours, 10) || 0;
            var list = el('ul', 'pets-hosp-win__list');
            sick.forEach(function (pet) { list.appendChild(admitRow(pet, hours)); });
            box.appendChild(list);
            return box;
        }

        // --- otwieranie / podmiana / zamykanie ------------------------------------------------------------
        function onWindowClosed() {
            open = null;
            openSig = null;
            refs = null;
            confirm = false;
            dropWinRigs();
            markSelected(null);
            ctx.flushPats();
            if (ctx.isActive('izba')) ctx.setQuery({});
        }

        function swap(content) {
            var old = winRigs;
            winRigs = [];
            var node = content();
            win.replace(node);
            old.forEach(function (r) { if (r) r.destroy(); });
        }

        function openBed(id, o) {
            o = o || {};
            var pet = findHosp(lastState, id);
            var view = slotOf(id);
            if (!win || !pet || !view) return false;
            confirm = false;
            var old = winRigs;
            winRigs = [];
            open = { type: 'bed', id: id };
            openSig = bedSig(pet);
            ctx.flushPats();
            // Fokus zostaje na łóżku (Enter jeszcze raz = pat pat); z adresu albo po przyjęciu — na łóżko
            win.open({
                content: bedContent(pet), labelledBy: 'petsWardWinTitle', returnFocus: view.el,
                onClose: onWindowClosed, closeLabel: 'Zamknij okno pupila', focus: false
            });
            old.forEach(function (r) { if (r) r.destroy(); });
            if (o.focusBed) H.focus(view.el);
            markSelected(view);
            ctx.setQuery({ pupil: id });
            H.reveal(host, scroll, view.el);
            return true;
        }

        function openFree(slot) {
            var view = views[slot];
            if (!win || !view) return;
            var old = winRigs;
            winRigs = [];
            open = { type: 'free', slot: slot };
            openSig = freeSig(lastState);
            confirm = false;
            win.open({
                content: freeContent(lastState), labelledBy: 'petsWardWinTitle', returnFocus: view.el,
                onClose: onWindowClosed, closeLabel: 'Zamknij okno łóżka'
            });
            old.forEach(function (r) { if (r) r.destroy(); });
            markSelected(view);
            ctx.setQuery({});
            H.reveal(host, scroll, view.el);
        }

        function replaceBed(pet, focusKey) {
            openSig = bedSig(pet);
            swap(function () { return bedContent(pet); });
            if (focusKey) {
                var target = win.body.querySelector('[data-window-key="' + focusKey + '"]');
                if (target) H.focus(target);
            }
        }

        /** Stan zmienił się przy otwartym oknie (odświeżenie, druga karta, własna akcja). */
        function refreshWindow(state) {
            if (!open || !win || !win.isOpen()) return;
            if (open.type === 'free') {
                if (admitting != null) return;          // po przyjęciu okno pokaże przyjętego pupila
                var taken = slots[open.slot];
                if (taken != null) {
                    // Wolne łóżko zajął pupil przyjęty w innej karcie — okno pokazuje jego
                    var pet0 = findHosp(state, taken);
                    open = { type: 'bed', id: taken };
                    confirm = false;
                    replaceBed(pet0);
                    markSelected(slotOf(taken));
                    ctx.setQuery({ pupil: taken });
                } else if (freeSig(state) !== openSig) {
                    openSig = freeSig(state);
                    swap(function () { return freeContent(state); });
                }
                return;
            }
            var pet = findHosp(state, open.id);
            if (!pet) {
                if (discharging === open.id) return;    // odbiór w toku — zaraz przejście do domku
                H.closeGone(win, host);
                return;
            }
            if (pet.hospital.ready) confirm = false;
            if (bedSig(pet) !== openSig) replaceBed(pet);
            else if (refs) {
                refs.pet = pet;
                fillBed(refs);
            }
        }

        // --- akcje ----------------------------------------------------------------------------------
        function patBed(id) {
            var view = slotOf(id);
            if (!view || !view.rig || !ctx.pat(id)) return;
            if (typeof view.rig.pat === 'function') view.rig.pat();
            else view.rig.playAction('pat');
        }

        function onBedClick(slot) {
            var id = slots[slot];
            if (id == null) {
                openFree(slot);
                return;
            }
            if (open && open.type === 'bed' && open.id === id && win.isOpen()) {
                patBed(id);
                return;
            }
            openBed(id);
        }

        function discharge(btn) {
            var id = parseInt(btn.dataset.petId, 10);
            var pet = ctx.findPet(id);
            if (!pet || discharging != null) return;
            discharging = id;
            u.setBusy(btn, true);
            H.discharge(ctx, pet).then(function () {
                discharging = null;
                if (ctx.isActive('izba')) ctx.go('domek', { pupil: id });
                else if (lastState) render(lastState);
            }, function () {
                discharging = null;
                if (btn.isConnected) u.setBusy(btn, false);
                if (lastState) render(lastState);
            });
        }

        function admit(btn) {
            var id = parseInt(btn.dataset.petId, 10);
            var pet = ctx.findPet(id);
            if (!pet || admitting != null) return;
            admitting = id;
            if (open && open.type === 'free') prefer[id] = open.slot;
            u.setBusy(btn, true);
            H.admit(ctx, pet).then(function () {
                admitting = null;
                // Render już położył pupila w łóżku (to, z którego go przyjęto) — okno pokazuje jego
                if (!openBed(id, { focusBed: true }) && lastState) render(lastState);
            }, function () {
                admitting = null;
                delete prefer[id];
                if (btn.isConnected) u.setBusy(btn, false);
                if (lastState) render(lastState);
            });
        }

        host.addEventListener('click', function (e) {
            var bed = e.target.closest('[data-bed-slot]');
            if (bed && host.contains(bed)) {
                onBedClick(parseInt(bed.dataset.bedSlot, 10));
                return;
            }
            var btn = e.target.closest('[data-ward-action]');
            if (!btn || !host.contains(btn) || btn.disabled || btn.getAttribute('aria-disabled') === 'true') return;
            var action = btn.dataset.wardAction;
            if (action === 'discharge') {
                discharge(btn);
            } else if (action === 'early' || action === 'confirm-cancel') {
                var pet = open && open.type === 'bed' ? findHosp(lastState, open.id) : null;
                if (!pet) return;
                confirm = action === 'early';
                // „Zabierz wcześniej” → „Tak, zabieram” (jak dawniej); „Zostaw” → z powrotem „Zabierz wcześniej”
                replaceBed(pet, 'early');
            } else if (action === 'admit') {
                admit(btn);
            }
        });

        // --- parametry z adresu (?pupil=ID) ----------------------------------------------------------
        function applyParams(params, state) {
            pending = null;
            var id = params && params.pupil;
            if (!id) {
                if (open && open.type === 'bed' && win && win.isOpen()) win.close({ restoreFocus: false });
                return;
            }
            if (!findHosp(state, id)) {
                // W domku, odszedł, cudzy albo nieistniejący: sala bez okna, adres bez parametru
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                ctx.setQuery({});
                return;
            }
            if (open && open.type === 'bed' && open.id === id && win.isOpen()) return;
            openBed(id, { focusBed: true });
        }

        // --- render ----------------------------------------------------------------------------------
        function render(state) {
            lastState = state;
            var ids = H.inBed(state).map(function (p) { return p.id; });
            // max(3, n) łóżek — i zawsze jedno wolne, gdy w domku ktoś choruje (pielęgniarka kieruje tu z przyjęciem)
            var min = Math.max(MIN_SLOTS, ids.length + (H.sickAtHome(state).length ? 1 : 0));
            slots = H.syncSlots(slots, ids, min, prefer);
            slots.forEach(function (id) { if (id != null) delete prefer[id]; });
            syncViews(state);
            row.style.setProperty('--n', String(slots.length));     // kolumn najwyżej tyle, ile łóżek (CSS)
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
                admitting = null;
                discharging = null;
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                // Ukryta scena nie trzyma żywych rigów (timery mrugania i gestów) — render zbuduje je od nowa
                while (views.length) destroyView(views.pop());
                slots = [];
                prefer = {};
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
                views.forEach(tickBed);
                if (refs && open && open.type === 'bed') fillBed(refs);
            }
        };
    }

    W.scenes.izba = {
        title: 'Izba przyjęć',
        create: create
    };
})();
