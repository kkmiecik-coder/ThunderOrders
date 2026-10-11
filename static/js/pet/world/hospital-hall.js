/**
 * Świat pupili — scena „szpital” = hol z recepcją (spec v3.1 §4.2).
 *
 * - Drzwi Inkubatorium (lewe, ciepłe światło w okienku) i Izby przyjęć (prawe, łóżko w okienku) to linki
 *   <a data-scene-link> z szyldami; znaczek z liczbą spraw (Inkubatorium: jajka gotowe do wyklucia; Izba:
 *   wyzdrowiali czekający na odbiór + chorzy w domku), brak spraw = brak znaczka.
 * - Recepcja pośrodku: pielęgniarka (własna postać SVG — okrągła, czepek z krzyżykiem; mruga), na ladzie
 *   jajko z kokardką na każdą pozycję `eggs_available`. Klik w jajko = okno sceny ze źródłem i „Odbierz”
 *   (POST /jajka/odbierz) → okno znika, jajko „odjeżdża” do drzwi Inkubatorium (≤ 0,8 s; ograniczony
 *   ruch: bez lotu), toast jak dawniej.
 * - Dymek pielęgniarki: jeden komunikat wg priorytetu (spec §4.2: jajka do odebrania → wyzdrowiały →
 *   jajko gotowe → chory w domku → odliczanie do miesięcznego → spokój); link do sali, gdy jej dotyczy.
 * - Układ: ≥ 600 px drzwi po bokach i recepcja pośrodku; < 600 px drzwi obok siebie u góry, recepcja
 *   pod nimi (CSS, zapytania kontenera na scenie właściwej).
 * - Zmiana stanu przy otwartym oknie: jajko nadal na ladzie → treść odświeżona; zniknęło (odebrane w innej
 *   karcie) → okno się zamyka, fokus wraca na scenę.
 * Rejestruje się w window.PetsWorld.scenes.szpital.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.szpital) return;

    var FLY_MS = 700;
    var DESKTOP = '(min-width: 1024px)';

    // Pielęgniarka (spec v3.1 §4.2): okrągła głowa, czepek z krzyżykiem, rumieńce; dół chowa się za ladą
    var NURSE_SVG =
        '<svg class="pets-nurse" viewBox="0 0 140 120" aria-hidden="true" focusable="false">' +
        '<path class="nurse-uniform" d="M24 122C24 96 44 82 70 82S116 96 116 122Z"/>' +
        '<path class="nurse-collar" d="M56 84l14 13 14-13"/>' +
        '<path class="nurse-pocket" d="M86 104h14v10H86z"/>' +
        '<circle class="nurse-face" cx="70" cy="54" r="35"/>' +
        '<path class="nurse-hair" d="M35 56c0-22 15-35 35-35s35 13 35 35c-5-9-15-16-24-17-2 6-8 9-14 9s-10-3-12-8c-9 2-16 8-20 16z"/>' +
        '<path class="nurse-cap" d="M41 33c0-16 13-26 29-26s29 10 29 26c-8-4-18-6-29-6s-21 2-29 6z"/>' +
        '<path class="nurse-cross" d="M67 11h6v5h5v6h-5v5h-6v-5h-5v-6h5z"/>' +
        '<g class="nurse-eyes"><ellipse cx="57" cy="58" rx="3.8" ry="4.8"/><ellipse cx="83" cy="58" rx="3.8" ry="4.8"/>' +
        '<circle class="nurse-shine" cx="58.4" cy="56.4" r="1.3"/><circle class="nurse-shine" cx="84.4" cy="56.4" r="1.3"/></g>' +
        '<circle class="nurse-cheek" cx="47" cy="68" r="6"/><circle class="nurse-cheek" cx="93" cy="68" r="6"/>' +
        '<path class="nurse-mouth" d="M63 69q7 7 14 0"/>' +
        '</svg>';

    // Drzwi Inkubatorium: ciepłe światło i jajko w okienku
    var DOOR_INC_SVG =
        '<svg class="pets-hall__door-art" viewBox="0 0 100 170" aria-hidden="true" focusable="false">' +
        '<rect class="door-frame" x="1.5" y="1.5" width="97" height="168" rx="11"/>' +
        '<rect class="door-leaf" x="9" y="9" width="82" height="161" rx="7"/>' +
        '<rect class="door-window" x="20" y="20" width="60" height="50" rx="10"/>' +
        '<ellipse class="door-light" cx="50" cy="47" rx="24" ry="19"/>' +
        '<path class="door-egg" d="M50 31c6 0 10.5 9 10.5 15.5a10.5 10.5 0 0 1-21 0C39.5 40 44 31 50 31z"/>' +
        '<path class="door-egg-spot" d="M46 41a2.2 2.2 0 1 0 .1 0zM54 49a1.8 1.8 0 1 0 .1 0z"/>' +
        '<rect class="door-panel" x="20" y="86" width="60" height="64" rx="7"/>' +
        '<circle class="door-knob" cx="80" cy="104" r="4.6"/>' +
        '</svg>';

    // Drzwi Izby przyjęć: łóżko z pupilem w okienku, krzyżyk na drzwiach
    var DOOR_WARD_SVG =
        '<svg class="pets-hall__door-art" viewBox="0 0 100 170" aria-hidden="true" focusable="false">' +
        '<rect class="door-frame" x="1.5" y="1.5" width="97" height="168" rx="11"/>' +
        '<rect class="door-leaf" x="9" y="9" width="82" height="161" rx="7"/>' +
        '<rect class="door-window" x="20" y="20" width="60" height="50" rx="10"/>' +
        '<rect class="door-bedpost" x="26" y="40" width="5" height="22" rx="2.5"/>' +
        '<circle class="door-pet" cx="40" cy="46" r="7"/>' +
        '<rect class="door-quilt" x="35" y="48" width="38" height="10" rx="4"/>' +
        '<rect class="door-bed" x="27" y="57" width="48" height="5" rx="2.5"/>' +
        '<rect class="door-panel" x="20" y="86" width="60" height="64" rx="7"/>' +
        '<path class="door-cross" d="M46 103h8v8h8v8h-8v8h-8v-8h-8v-8h8z"/>' +
        '<circle class="door-knob" cx="20" cy="104" r="4.6"/>' +
        '</svg>';

    var CLOCK_SVG =
        '<svg viewBox="0 0 60 60" aria-hidden="true" focusable="false">' +
        '<circle class="clock-face" cx="30" cy="30" r="26"/>' +
        '<g class="clock-ticks"><path d="M30 8v5M30 47v5M8 30h5M47 30h5"/></g>' +
        '<path class="clock-hand clock-hand--h" d="M30 30V18"/>' +
        '<path class="clock-hand clock-hand--m" d="M30 30V12"/>' +
        '<circle class="clock-pin" cx="30" cy="30" r="2.6"/>' +
        '</svg>';

    var BELL_SVG =
        '<svg class="pets-hall__bell" viewBox="0 0 32 24" aria-hidden="true" focusable="false">' +
        '<path class="bell-dome" d="M5 19a11 11 0 0 1 22 0z"/><circle class="bell-knob" cx="16" cy="6.5" r="2.4"/>' +
        '<rect class="bell-base" x="2" y="19" width="28" height="4" rx="2"/></svg>';

    // Kokardka na jajku do odebrania (kolor wg źródła — klasa .pets-gift--<source>)
    var BOW_SVG =
        '<svg class="pets-gift__bow" viewBox="0 0 48 28" aria-hidden="true" focusable="false">' +
        '<path class="bow-loop" d="M24 14C16 2 4 2 4 10s12 8 20 4z"/><path class="bow-loop" d="M24 14c8-12 20-12 20-4s-12 8-20 4z"/>' +
        '<path class="bow-tail" d="M24 14l-8 13h4l4-8 4 8h4z"/><circle class="bow-knot" cx="24" cy="14" r="4.5"/></svg>';

    var ARROW_SVG =
        '<svg class="pets-hall__talk-arrow" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" ' +
        'stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h13M13 6l6 6-6 6"/></svg>';

    function create(ctx, host) {
        var H = window.PetsHospital;
        var u = ctx.u;
        var el = u.el;
        var R = function () { return window.PetRig; };

        var lastState = null;
        var eggViews = {};           // klucz pozycji eggs_available → widok jajka na ladzie
        var eggOrder = [];
        var claiming = null;         // {key} — jajko w trakcie odbioru zostaje na ladzie do startu lotu
        var openKey = null;          // klucz jajka w otwartym oknie
        var openSig = null;
        var winRigs = [];
        var flight = null;
        var talkSig = null;
        var lift = 0;

        // --- szkielet -------------------------------------------------------------------------
        var stage = el('div', 'pets-stage pets-hall');
        stage.setAttribute('data-window-backdrop', '');
        var floor = el('div', 'pets-hall__floor');
        floor.setAttribute('aria-hidden', 'true');
        var clock = el('div', 'pets-hall__clock');
        clock.setAttribute('aria-hidden', 'true');
        clock.innerHTML = CLOCK_SVG;
        var handH = clock.querySelector('.clock-hand--h');
        var handM = clock.querySelector('.clock-hand--m');

        function makeDoor(scene, label, art, iconName, mod) {
            var a = el('a', 'pets-hall__door pets-hall__door--' + mod);
            a.href = ctx.href(scene);
            a.dataset.sceneLink = scene;
            var sign = el('span', 'pets-hall__sign');
            sign.innerHTML = u.icon(iconName, 'pets-hall__sign-icon');
            sign.appendChild(el('span', 'pets-hall__sign-text', label));
            var frame = el('span', 'pets-hall__frame');
            frame.innerHTML = art;
            var badge = el('span', 'pets-hall__badge');
            badge.setAttribute('aria-hidden', 'true');
            badge.hidden = true;
            frame.appendChild(badge);
            a.appendChild(sign);
            a.appendChild(frame);
            a.setAttribute('aria-label', label);
            return { a: a, frame: frame, badge: badge, label: label };
        }

        var doorInc = makeDoor('inkubatorium', 'Inkubatorium', DOOR_INC_SVG, 'egg', 'inc');
        var doorWard = makeDoor('izba', 'Izba przyjęć', DOOR_WARD_SVG, 'cross', 'ward');

        var desk = el('div', 'pets-hall__desk');
        var talk = el('div', 'pets-hall__talk');
        var nurse = el('div', 'pets-hall__nurse');
        nurse.setAttribute('aria-hidden', 'true');
        nurse.innerHTML = NURSE_SVG;
        var counter = el('div', 'pets-hall__counter');
        var eggsBox = el('div', 'pets-hall__eggs');
        var top = el('div', 'pets-hall__counter-top');
        top.setAttribute('aria-hidden', 'true');
        top.innerHTML = BELL_SVG;
        var front = el('div', 'pets-hall__counter-front');
        front.setAttribute('aria-hidden', 'true');
        front.appendChild(el('span', 'pets-hall__counter-sign', 'Recepcja'));
        counter.appendChild(eggsBox);
        counter.appendChild(top);
        counter.appendChild(front);
        desk.appendChild(talk);
        desk.appendChild(nurse);
        desk.appendChild(counter);

        [floor, clock, doorInc.a, doorWard.a, desk].forEach(function (n) { stage.appendChild(n); });
        host.appendChild(stage);

        var win = window.PetsSceneWindow ? window.PetsSceneWindow.attach(host) : null;

        function isDesktop() {
            return !!(window.matchMedia && window.matchMedia(DESKTOP).matches);
        }

        // --- drzwi: znaczki ------------------------------------------------------------------------
        function setDoor(door, count, detail) {
            door.badge.hidden = !count;
            var text = count > 9 ? '9+' : String(count);
            if (door.badge.textContent !== text) door.badge.textContent = text;
            door.a.classList.toggle('has-badge', count > 0);
            var label = door.label + (detail ? ' — ' + detail : '');
            if (door.a.getAttribute('aria-label') !== label) door.a.setAttribute('aria-label', label);
        }

        function renderDoors(state) {
            var ready = H.readyEggs(state).length;
            setDoor(doorInc, ready, ready ? 'gotowe do wyklucia: ' + ready : '');
            var healed = H.healedPets(state).length;
            var sick = H.sickAtHome(state).length;
            var parts = [];
            if (healed) parts.push('czeka na odbiór: ' + healed);
            if (sick) parts.push('chorzy w domku: ' + sick);
            setDoor(doorWard, healed + sick, parts.join(', '));
        }

        // --- dymek pielęgniarki (spec v3.1 §4.2: jeden komunikat wg priorytetu) ----------------------
        function monthlyText(state) {
            var left = state.next_monthly_at ? u.secondsUntil(state.next_monthly_at) : NaN;
            if (!(left > 0)) return '';
            // Jak w widgecie dashboardu: pełne dni, poniżej doby godziny
            var hours = Math.max(1, Math.ceil(left / 3600));
            var days = Math.floor(hours / 24);
            return 'Nowe jajko za ' + (days >= 1 ? u.daysText(days) : '~' + hours + ' h') + '.';
        }

        function talkFor(state) {
            var n = H.eggsToClaimCount(state);
            if (n) return { text: n === 1 ? 'Mam dla Ciebie jajko! Leży na ladzie.' : 'Mam dla Ciebie jajka (' + n + ')! Leżą na ladzie.' };
            var healed = H.healedPets(state);
            if (healed.length) {
                var names = healed.map(function (p) { return H.petName(p, u); });
                return {
                    text: healed.length === 1 ? names[0] + ' już zdrowy — czeka w izbie przyjęć.'
                        : healed.length === 2 ? names[0] + ' i ' + names[1] + ' już zdrowi — czekają w izbie przyjęć.'
                        : 'Wyzdrowiałych pupili: ' + healed.length + ' — czekają w izbie przyjęć.',
                    scene: 'izba',
                    params: healed.length === 1 ? { pupil: healed[0].id } : {}
                };
            }
            var ready = H.readyEggs(state);
            if (ready.length) {
                return {
                    text: ready.length === 1 ? 'Jajko jest gotowe do wyklucia — zajrzyj do Inkubatorium!'
                        : 'Jajek gotowych do wyklucia: ' + ready.length + ' — zajrzyj do Inkubatorium!',
                    scene: 'inkubatorium',
                    params: ready.length === 1 ? { jajko: ready[0].id } : {}
                };
            }
            var sick = H.sickAtHome(state);
            if (sick.length) {
                var sickNames = sick.map(function (p) { return H.petName(p, u); });
                return {
                    text: sick.length === 1 ? sickNames[0] + ' źle się czuje — przyjmij go w izbie przyjęć.'
                        : sick.length === 2 ? sickNames[0] + ' i ' + sickNames[1] + ' źle się czują — przyjmij je w izbie przyjęć.'
                        : 'Chorych pupili w domku: ' + sick.length + ' — przyjmij je w izbie przyjęć.',
                    scene: 'izba',
                    params: {}
                };
            }
            var monthly = monthlyText(state);
            if (monthly) return { text: monthly };
            return { text: 'Wszyscy zdrowi!' };
        }

        function renderTalk(state) {
            var t = talkFor(state);
            var sig = t.scene ? t.scene + '|' + (t.params.pupil || '') + '|' + (t.params.jajko || '') : 'text';
            var bubble = talk.firstChild;
            if (sig !== talkSig || !bubble) {
                talkSig = sig;
                talk.innerHTML = '';
                if (t.scene) {
                    bubble = el('a', 'pets-hall__talk-bubble is-link');
                    bubble.href = ctx.href(t.scene, t.params);
                    bubble.dataset.sceneLink = t.scene;
                    if (t.params.pupil) bubble.dataset.pupil = String(t.params.pupil);
                    if (t.params.jajko) bubble.dataset.jajko = String(t.params.jajko);
                    bubble.appendChild(el('span', 'pets-hall__talk-text'));
                    bubble.insertAdjacentHTML('beforeend', ARROW_SVG);
                } else {
                    bubble = el('p', 'pets-hall__talk-bubble');
                    bubble.appendChild(el('span', 'pets-hall__talk-text'));
                }
                talk.appendChild(bubble);
            }
            var textEl = bubble.querySelector('.pets-hall__talk-text');
            if (textEl.textContent !== t.text) textEl.textContent = t.text;
            nurse.classList.toggle('is-calling', H.eggsToClaimCount(state) > 0);
        }

        // --- zegar na ścianie (czas serwera) -----------------------------------------------------------
        function renderClock() {
            var d = new Date(u.serverNow());
            var m = d.getMinutes();
            var h = d.getHours() % 12 + m / 60;
            handH.setAttribute('transform', 'rotate(' + (h * 30).toFixed(1) + ' 30 30)');
            handM.setAttribute('transform', 'rotate(' + (m * 6) + ' 30 30)');
        }

        // --- jajka na ladzie ---------------------------------------------------------------------------
        function findClaim(state, key) {
            var list = (state && state.eggs_available) || [];
            for (var i = 0; i < list.length; i++) if (H.claimKey(list[i]) === key) return list[i];
            return null;
        }

        function giftArt(item, cls) {
            var art = el('span', 'pets-gift pets-gift--' + item.source + (cls ? ' ' + cls : ''));
            var rig = R() ? R().mountEgg(art, { pct: 0, size: 'mini' }) : null;
            art.insertAdjacentHTML('beforeend', BOW_SVG);
            return { el: art, rig: rig };
        }

        function eggView(item) {
            var key = H.claimKey(item);
            var btn = el('button', 'pets-hall__egg');
            btn.type = 'button';
            btn.dataset.hallEgg = key;
            var art = giftArt(item);
            var count = el('span', 'pets-hall__egg-count');
            count.setAttribute('aria-hidden', 'true');
            btn.appendChild(art.el);
            btn.appendChild(count);
            var view = { key: key, el: btn, rig: art.rig, count: count, item: null };
            updateEggView(view, item);
            return view;
        }

        function updateEggView(view, item) {
            view.item = item;
            var n = item.source === 'granted' ? H.grantedCount(item) : 1;
            view.count.hidden = n < 2;
            view.count.textContent = '×' + n;
            var label = H.claimLabel(item);
            if (view.el.getAttribute('aria-label') !== label) view.el.setAttribute('aria-label', label);
        }

        function dropEggView(key) {
            var view = eggViews[key];
            if (!view) return;
            if (view.rig) view.rig.destroy();
            if (view.el.parentNode) view.el.parentNode.removeChild(view.el);
            delete eggViews[key];
        }

        function syncEggs(state) {
            var list = ((state && state.eggs_available) || []).slice();
            var keys = list.map(H.claimKey);
            // Jajko w trakcie odbioru zostaje na swoim miejscu, dopóki nie wystartuje lot do drzwi
            if (claiming && keys.indexOf(claiming.key) < 0 && eggViews[claiming.key]) {
                var at = Math.min(eggOrder.indexOf(claiming.key), list.length);
                list.splice(at < 0 ? list.length : at, 0, eggViews[claiming.key].item);
                keys.splice(at < 0 ? keys.length : at, 0, claiming.key);
            }
            list.forEach(function (item, i) {
                var key = keys[i];
                var view = eggViews[key];
                if (view) updateEggView(view, item);
                else view = eggViews[key] = eggView(item);
                if (eggsBox.children[i] !== view.el) eggsBox.insertBefore(view.el, eggsBox.children[i] || null);
            });
            Object.keys(eggViews).forEach(function (key) { if (keys.indexOf(key) < 0) dropEggView(key); });
            eggOrder = keys;
            counter.classList.toggle('has-eggs', keys.length > 0);
        }

        // --- okno jajka --------------------------------------------------------------------------------
        function dropWinRigs() {
            winRigs.forEach(function (r) { if (r) r.destroy(); });
            winRigs = [];
        }

        function claimSig(item) {
            return [H.claimKey(item), item.count, item.pet_name].join('|');
        }

        function claimContent(item) {
            var box = el('div', 'pets-hosp-win pets-hosp-win--claim');
            var hero = el('div', 'pets-hosp-win__hero');
            var art = giftArt(item, 'pets-hosp-win__gift');
            winRigs.push(art.rig);
            hero.appendChild(art.el);
            var head = el('div', 'pets-hosp-win__head');
            var title = el('h2', 'pets-window__title', H.claimTitle(item));
            title.id = 'petsHallWinTitle';
            head.appendChild(title);
            head.appendChild(el('p', 'pets-window__text', H.claimText(item, u)));
            hero.appendChild(head);
            box.appendChild(hero);
            var actions = el('div', 'pets-window__actions');
            var btn = u.button('Odbierz', 'egg', 'primary', { hallAction: 'claim', key: H.claimKey(item) });
            btn.setAttribute('data-window-key', 'claim');
            actions.appendChild(btn);
            box.appendChild(actions);
            return box;
        }

        function markSelected(key) {
            Object.keys(eggViews).forEach(function (k) { eggViews[k].el.classList.toggle('is-selected', k === key); });
        }

        function onWindowClosed() {
            openKey = null;
            openSig = null;
            dropWinRigs();
            markSelected(null);
            setLift(0);
        }

        function openClaim(key, returnFocus) {
            var item = findClaim(lastState, key);
            if (!win || !item || claiming) return;
            var old = winRigs;
            winRigs = [];
            openKey = key;
            openSig = claimSig(item);
            win.open({
                content: claimContent(item), labelledBy: 'petsHallWinTitle', returnFocus: returnFocus || null,
                onClose: onWindowClosed, closeLabel: 'Zamknij okno jajka'
            });
            old.forEach(function (r) { if (r) r.destroy(); });
            markSelected(key);
            liftFor(returnFocus);
        }

        function replaceClaim(item) {
            var old = winRigs;
            winRigs = [];
            openSig = claimSig(item);
            win.replace(claimContent(item));
            old.forEach(function (r) { if (r) r.destroy(); });
        }

        // Arkusz (< 1024 px): recepcja jedzie w górę tak, żeby wybrane jajko zostało widoczne nad arkuszem
        function setLift(px) {
            lift = Math.max(0, Math.round(px));
            if (lift) host.style.setProperty('--lift', lift + 'px');
            else host.style.removeProperty('--lift');
        }

        function liftFor(node) {
            if (!node || !win || !win.isOpen() || isDesktop()) { setLift(0); return; }
            var sheet = parseFloat(host.style.getPropertyValue('--window-h')) || 0;
            var box = host.getBoundingClientRect();
            var r = node.getBoundingClientRect();
            var bottom = r.bottom + lift;                // pozycja bez obecnego uniesienia
            setLift(Math.min(sheet, Math.max(0, bottom - (box.bottom - sheet - 12))));
        }

        // --- odbiór jajka: lot do drzwi Inkubatorium -------------------------------------------------------
        function stopFlight() {
            if (!flight) return;
            clearTimeout(flight.timer);
            if (flight.anim) { try { flight.anim.cancel(); } catch (e) { /* już skończona */ } }
            if (flight.rig) flight.rig.destroy();
            if (flight.el.parentNode) flight.el.parentNode.removeChild(flight.el);
            flight = null;
        }

        function pulseDoor() {
            if (u.reducedMotion()) return;
            var f = doorInc.frame;
            f.classList.remove('is-receiving');
            void f.offsetWidth;
            f.classList.add('is-receiving');
            setTimeout(function () { f.classList.remove('is-receiving'); }, 800);
        }

        function focusAfterClaim(hadFocus) {
            if (!hadFocus) return;
            var next = eggsBox.querySelector('.pets-hall__egg');
            H.focus(next || doorInc.a);
        }

        function launch(key) {
            var view = eggViews[key];
            var active = document.activeElement;
            var hadFocus = !active || active === document.body || (win && win.el.contains(active)) ||
                (view && view.el.contains(active));
            // Okno znika razem z „odjazdem” jajka; scena wraca na miejsce bez przejścia (pozycje ostateczne)
            host.classList.add('is-snap');
            if (win && win.isOpen()) win.close({ restoreFocus: false });
            var hostBox = host.getBoundingClientRect();
            var start = view && view.el.isConnected ? view.el.getBoundingClientRect() : null;
            var end = doorInc.frame.getBoundingClientRect();
            claiming = null;
            if (lastState) syncEggs(lastState);           // jajko schodzi z lady (prezent z licznikiem zostaje)
            focusAfterClaim(hadFocus);
            requestAnimationFrame(function () { host.classList.remove('is-snap'); });
            stopFlight();
            if (u.reducedMotion() || !start || !start.width || !end.width) {
                pulseDoor();
                return;
            }
            var item = view.item;
            var fly = el('div', 'pets-hall__flyer');
            fly.setAttribute('aria-hidden', 'true');
            fly.style.left = (start.left - hostBox.left) + 'px';
            fly.style.top = (start.top - hostBox.top) + 'px';
            fly.style.width = start.width + 'px';
            fly.style.height = start.height + 'px';
            var art = giftArt(item);
            fly.appendChild(art.el);
            host.appendChild(fly);
            var dx = (end.left + end.width / 2) - (start.left + start.width / 2);
            var dy = (end.top + end.height * 0.42) - (start.top + start.height / 2);
            flight = { el: fly, rig: art.rig, anim: null, timer: 0 };
            var mine = flight;
            function finish() {
                if (flight !== mine) return;
                stopFlight();
                pulseDoor();
            }
            if (typeof fly.animate === 'function') {
                mine.anim = fly.animate([
                    { transform: 'translate(0, 0) scale(1) rotate(0deg)', opacity: 1 },
                    { transform: 'translate(' + (dx * 0.5).toFixed(1) + 'px, ' + (dy * 0.5 - 80).toFixed(1) + 'px) scale(0.9) rotate(-14deg)', opacity: 1, offset: 0.5 },
                    { transform: 'translate(' + dx.toFixed(1) + 'px, ' + dy.toFixed(1) + 'px) scale(0.42) rotate(10deg)', opacity: 0.2 }
                ], { duration: FLY_MS, easing: 'ease-in-out', fill: 'forwards' });
                mine.anim.onfinish = finish;
            }
            // Zapas: ukryta karta wstrzymuje animacje — lot i tak się kończy
            mine.timer = setTimeout(finish, FLY_MS + 300);
        }

        function claimEgg(btn) {
            var key = btn.dataset.key;
            var item = findClaim(lastState, key);
            if (!item || claiming) return;
            claiming = { key: key };
            u.setBusy(btn, true);
            H.claim(ctx, item).then(function () {
                if (!claiming || claiming.key !== key) return;
                launch(key);
            }, function () {
                // Błąd pokazał ctx.send (409 = ciche odświeżenie); jajko wraca do zwykłej synchronizacji
                claiming = null;
                if (btn.isConnected) u.setBusy(btn, false);
                if (lastState) render(lastState);
            });
        }

        // --- zdarzenia (delegacja) ------------------------------------------------------------------------
        host.addEventListener('click', function (e) {
            var egg = e.target.closest('[data-hall-egg]');
            if (egg && host.contains(egg)) {
                openClaim(egg.dataset.hallEgg, egg);
                return;
            }
            var btn = e.target.closest('[data-hall-action]');
            if (!btn || !host.contains(btn) || btn.disabled || btn.getAttribute('aria-disabled') === 'true') return;
            if (btn.dataset.hallAction === 'claim') claimEgg(btn);
        });

        // --- render ---------------------------------------------------------------------------------------
        function render(state) {
            lastState = state;
            syncEggs(state);
            renderDoors(state);
            renderTalk(state);
            renderClock();
            if (openKey != null && win && win.isOpen() && !(claiming && claiming.key === openKey)) {
                var item = findClaim(state, openKey);
                if (!item) H.closeGone(win, host);
                else if (claimSig(item) !== openSig) replaceClaim(item);
            }
        }

        return {
            enter: function () {},
            leave: function () {
                stopFlight();
                claiming = null;
                if (win && win.isOpen()) win.close({ restoreFocus: false });
                setLift(0);
                // Ukryta scena nie trzyma żywych rigów — render zbuduje je od nowa
                Object.keys(eggViews).forEach(dropEggView);
                eggOrder = [];
                talkSig = null;
                talk.innerHTML = '';
            },
            render: render,
            tick: function () {
                var state = ctx.state();
                if (!state) return;
                renderTalk(state);
                renderClock();
            }
        };
    }

    W.scenes.szpital = {
        title: 'Szpital',
        create: create
    };
})();
