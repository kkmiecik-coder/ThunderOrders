/**
 * Świat pupili — scena „szpital” (spec v3 §4, §6.3): inkubatornia + sala chorych.
 *
 * Inkubatornia: jajka do odebrania (start / miesięczne / ratunkowe / prezent), jajka w gniazdkach pod
 * lampą (PetRig.mountEgg ze skórką), Ogrzej z odliczaniem ciepła, Wykluj → window.PetHatch.run
 * (nakładka pełnoekranowa; odznaki po jej zamknięciu), odliczanie do jajka miesięcznego.
 * Sala chorych: łóżka (PetRig.mount z pose 'bed'), postęp leczenia, „~N h do wyzdrowienia”, „Odbierz”
 * (wyróżniony, gdy wyleczony) albo „Zabierz wcześniej” z potwierdzeniem w miejscu; klik w pupila na
 * łóżku = pat pat; lista chorych z domku z „Przyjmij”. `?pupil=ID` przewija do łóżka.
 * Rejestruje się w window.PetsWorld.scenes.szpital.
 */
(function () {
    'use strict';

    var W = window.PetsWorld = window.PetsWorld || {};
    W.scenes = W.scenes || {};
    if (W.scenes.szpital) return;

    var EGG_SOURCE = {
        start: 'Jajko startowe', monthly: 'Jajko miesięczne', rescue: 'Jajko ratunkowe', granted: 'Jajko w prezencie'
    };
    var SICK = ['chory', 'krytyczny'];

    function create(ctx, host) {
        var u = ctx.u;
        var el = u.el;
        var R = function () { return window.PetRig; };
        var pending = null;
        var hatching = false;

        // --- szkielet ----------------------------------------------------------------------

        var wrap = el('div', 'pets-hospital');

        var inc = el('section', 'pets-block pets-incubator');
        inc.setAttribute('aria-labelledby', 'petsIncTitle');
        var incTitle = el('h2', 'pets-block__title', 'Inkubatornia');
        incTitle.id = 'petsIncTitle';
        inc.appendChild(incTitle);
        inc.appendChild(el('p', 'pets-block__lead', 'Jajka grzeją się pod ciepłą lampą. Ogrzewaj je przy każdej wizycie, a wyklują się szybciej.'));
        var claimBox = el('div', 'pets-claim');
        var nests = el('div', 'pets-nests');
        var incEmpty = el('p', 'pets-empty', 'Inkubatornia jest teraz pusta.');
        var monthly = el('p', 'pets-incubator__monthly');
        inc.appendChild(claimBox);
        inc.appendChild(nests);
        inc.appendChild(incEmpty);
        inc.appendChild(monthly);

        var ward = el('section', 'pets-block pets-ward');
        ward.setAttribute('aria-labelledby', 'petsWardTitle');
        var wardTitle = el('h2', 'pets-block__title', 'Sala chorych');
        wardTitle.id = 'petsWardTitle';
        ward.appendChild(wardTitle);
        var wardLead = el('p', 'pets-block__lead');
        ward.appendChild(wardLead);
        var beds = el('div', 'pets-beds');
        var wardEmpty = el('p', 'pets-empty', 'Sala jest pusta — wszyscy są zdrowi.');
        var sickBox = el('div', 'pets-sick');
        var sickTitle = el('h3', 'pets-sick__title', 'Chorzy w domku');
        var sickList = el('ul', 'pets-sick__list');
        sickBox.appendChild(sickTitle);
        sickBox.appendChild(sickList);
        ward.appendChild(beds);
        ward.appendChild(wardEmpty);
        ward.appendChild(sickBox);

        wrap.appendChild(inc);
        wrap.appendChild(ward);
        host.appendChild(wrap);

        var claimSig = null;
        var eggViews = {};
        var bedViews = {};
        var sickViews = {};

        // --- inkubatornia ------------------------------------------------------------------

        function claimTile(item) {
            var tile = el('article', 'pets-claim__tile pets-claim__tile--' + item.source);
            var art = el('div', 'pets-claim__art');
            if (R()) R().mountEgg(art, { pct: 0, size: 'mini' });
            var bow = el('span', 'pets-claim__bow');
            bow.setAttribute('aria-hidden', 'true');
            art.appendChild(bow);
            var info = el('div', 'pets-claim__info');
            info.appendChild(el('h3', 'pets-claim__title', EGG_SOURCE[item.source] || 'Jajko'));
            var desc;
            if (item.source === 'start') desc = 'Twoje pierwsze jajko! Odbierz je i ogrzewaj przy każdej wizycie — tak wykluje się szybciej.';
            else if (item.source === 'monthly') desc = 'Nowe jajko czeka na odbiór. Odliczanie do kolejnego ruszy po odebraniu.';
            else if (item.source === 'rescue') {
                desc = item.pet_name
                    ? 'Pupil ' + item.pet_name + ' odszedł do gwiazd. To jajko czeka na Ciebie.'
                    : 'Twój pupil odszedł do gwiazd. To jajko czeka na Ciebie.';
            } else if (item.source === 'granted') {
                var n = Math.max(1, parseInt(item.count, 10) || 1);
                desc = n === 1 ? 'Czeka na Ciebie jajko w prezencie.'
                    : 'Czeka na Ciebie ' + n + ' ' + u.plural(n, 'jajko', 'jajka', 'jajek') + ' w prezencie.';
            } else desc = 'Jajko czeka na odbiór.';
            info.appendChild(el('p', 'pets-claim__desc', desc));
            var data = { hospAction: 'claim', source: item.source };
            if (item.pet_id != null) data.petId = String(item.pet_id);
            tile.appendChild(art);
            tile.appendChild(info);
            tile.appendChild(u.button('Odbierz', 'egg', 'primary', data));
            return tile;
        }

        function eggView(egg) {
            var card = el('article', 'pets-nest');
            card.dataset.eggId = String(egg.id);
            var lamp = el('div', 'pets-nest__lamp');
            lamp.setAttribute('aria-hidden', 'true');
            var art = el('div', 'pets-nest__art');
            var title = el('h3', 'pets-nest__title');
            var track = el('div', 'pets-progress');
            track.setAttribute('role', 'progressbar');
            track.setAttribute('aria-valuemin', '0');
            track.setAttribute('aria-valuemax', '100');
            track.setAttribute('aria-label', 'Postęp inkubacji');
            var fill = el('div', 'pets-progress__fill');
            track.appendChild(fill);
            var status = el('p', 'pets-nest__status');
            var actions = el('div', 'pets-nest__actions');
            card.appendChild(lamp);
            card.appendChild(art);
            card.appendChild(title);
            card.appendChild(track);
            card.appendChild(status);
            card.appendChild(actions);
            var rig = R() ? R().mountEgg(art, {
                pct: egg.progress_pct, boosted: !!egg.boost_until, ready: egg.ready, size: 'card', skin: egg.skin || 0
            }) : null;
            var view = { el: card, rig: rig, title: title, track: track, fill: fill, status: status, actions: actions, egg: null, sig: '' };
            updateEgg(view, egg);
            return view;
        }

        function updateEgg(view, egg) {
            view.egg = egg;
            var pct = Math.max(0, Math.min(100, Number(egg.progress_pct) || 0));
            view.title.textContent = EGG_SOURCE[egg.source] || 'Jajko';
            view.fill.style.width = pct + '%';
            view.track.setAttribute('aria-valuenow', String(Math.round(pct)));
            view.el.classList.toggle('is-ready', !!egg.ready);
            view.el.classList.toggle('is-boosted', !!egg.boost_until && !egg.ready);
            if (view.rig) view.rig.update({ pct: pct, boosted: !!egg.boost_until, ready: !!egg.ready });
            var sig = [egg.ready, egg.can_warm, egg.boost_until].join('|');
            if (sig !== view.sig) {
                var hadFocus = view.actions.contains(document.activeElement);
                view.sig = sig;
                view.actions.innerHTML = '';
                var btn;
                if (egg.ready) {
                    btn = u.button('Wykluj', 'sparkle', 'primary', { hospAction: 'hatch', eggId: String(egg.id) });
                } else {
                    btn = u.button('Ogrzej', 'flame', null, { hospAction: 'warm', eggId: String(egg.id) });
                    btn.disabled = !egg.can_warm;
                }
                view.actions.appendChild(btn);
                if (hadFocus && !btn.disabled) btn.focus();
                else if (hadFocus) {
                    // „Ogrzej” zgasł po ogrzaniu — fokus na gniazdko, nie na <body>
                    view.el.setAttribute('tabindex', '-1');
                    view.el.focus({ preventScroll: true });
                }
            }
            tickEgg(view);
        }

        function tickEgg(view) {
            var egg = view.egg;
            var pct = Math.round(Math.max(0, Math.min(100, Number(egg.progress_pct) || 0)));
            var text;
            if (egg.ready) {
                text = 'Gotowe do wyklucia!';
            } else if (egg.boost_until) {
                var left = u.secondsUntil(egg.boost_until);
                var state = ctx.state() || {};
                var factor = (state.config && state.config.boost_factor) || 2;
                text = pct + '% · ogrzane, ciepło (tempo ×' + factor + ') jeszcze ' + u.formatDuration(left > 0 ? left : 0);
            } else {
                text = pct + '% · ogrzej, żeby przyspieszyć wyklucie';
            }
            if (view.status.textContent !== text) view.status.textContent = text;
        }

        function renderIncubator(state) {
            var available = state.eggs_available || [];
            var sig = JSON.stringify(available);
            if (sig !== claimSig) {
                claimSig = sig;
                claimBox.innerHTML = '';
                available.forEach(function (item) { claimBox.appendChild(claimTile(item)); });
            }
            claimBox.hidden = !available.length;

            var eggs = state.eggs || [];
            var seen = {};
            eggs.forEach(function (egg, i) {
                seen[egg.id] = true;
                var view = eggViews[egg.id];
                if (view) updateEgg(view, egg);
                else view = eggViews[egg.id] = eggView(egg);
                if (nests.children[i] !== view.el) nests.insertBefore(view.el, nests.children[i] || null);
            });
            Object.keys(eggViews).forEach(function (id) {
                if (seen[id]) return;
                var view = eggViews[id];
                if (view.rig) view.rig.destroy();
                if (view.el.parentNode) view.el.parentNode.removeChild(view.el);
                delete eggViews[id];
            });
            nests.hidden = !eggs.length;
            incEmpty.hidden = !!(available.length || eggs.length);
            tickMonthly(state);
        }

        function tickMonthly(state) {
            var waiting = (state.eggs_available || []).some(function (e) { return e.source === 'monthly'; });
            var left = state.next_monthly_at ? u.secondsUntil(state.next_monthly_at) : NaN;
            monthly.hidden = waiting || !(left > 0);
            if (!monthly.hidden) {
                var text = 'Następne jajko miesięczne za ' + u.formatDuration(left) + '.';
                if (monthly.textContent !== text) monthly.textContent = text;
            }
        }

        function hatchEgg(eggId, btn) {
            if (hatching) return;
            var state = ctx.state() || {};
            var egg = (state.eggs || []).filter(function (e) { return e.id === eggId; })[0];
            if (!egg) return;
            if (!window.PetHatch || typeof window.PetHatch.run !== 'function') {
                u.toast('Nie udało się otworzyć wyklucia — odśwież stronę.', 'error');
                return;
            }
            hatching = true;
            u.setBusy(btn, true);
            var petId = null;
            window.PetHatch.run({
                skin: egg.skin || 0,
                // Gwiazdki sprzed duplikatu — odpowiedź API ma już stan po wykluciu
                prevPets: ((ctx.state() || {}).pets || []).slice(),
                hatch: function () {
                    return ctx.send('/jajka/' + eggId + '/wykluj', {}, { deferAchievements: true }).then(function (resp) {
                        petId = resp.pet_id;
                        return resp;
                    });
                },
                onName: function (name) {
                    return ctx.send('/' + petId + '/imie', { name: name }, { quiet: ['bad_name'] }).then(function (resp) {
                        u.toast('Witaj w domku, ' + resp.name + '!', 'success');
                        return resp;
                    });
                }
            }).then(function (res) {
                hatching = false;
                if (res && res.new_achievements && res.new_achievements.length) ctx.showAchievements();
                // Przycisk zniknął razem z jajkiem — fokus na nagłówek inkubatorni
                if (!document.body.contains(btn) || btn.disabled) {
                    incTitle.setAttribute('tabindex', '-1');
                    try { incTitle.focus({ preventScroll: true }); } catch (e) { incTitle.focus(); }
                }
            }, function () {
                // Błąd pokazał już handleError (toast); nakładka zamknęła się sama
                hatching = false;
                u.setBusy(btn, false);
            });
        }

        // --- sala chorych ------------------------------------------------------------------

        function bedView(pet) {
            var card = el('article', 'pets-bed');
            card.dataset.petId = String(pet.id);
            var patBtn = el('button', 'pets-bed__pet');
            patBtn.type = 'button';
            patBtn.dataset.hospAction = 'pat';
            patBtn.dataset.petId = String(pet.id);
            var art = el('span', 'pets-bed__art');
            patBtn.appendChild(art);
            var info = el('div', 'pets-bed__info');
            var name = el('h3', 'pets-bed__name');
            var track = el('div', 'pets-progress pets-progress--heal');
            track.setAttribute('role', 'progressbar');
            track.setAttribute('aria-valuemin', '0');
            track.setAttribute('aria-valuemax', '100');
            var fill = el('div', 'pets-progress__fill');
            track.appendChild(fill);
            var status = el('p', 'pets-bed__status');
            var note = el('p', 'pets-bed__note');
            var actions = el('div', 'pets-bed__actions');
            info.appendChild(name);
            info.appendChild(track);
            info.appendChild(status);
            info.appendChild(note);
            card.appendChild(patBtn);
            card.appendChild(info);
            card.appendChild(actions);
            var need = R() && R().needOf ? R().needOf(pet) : 'sick';
            var rig = R() ? R().mount(art, {
                species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: false,
                size: 'mini', need: need, pose: 'bed'
            }) : null;
            var view = { el: card, pat: patBtn, rig: rig, name: name, track: track, fill: fill, status: status, note: note, actions: actions, pet: null, sig: '', confirm: false };
            updateBed(view, pet);
            return view;
        }

        function healPct(h) {
            var since = u.parseLocal(h.since), healed = u.parseLocal(h.healed_at);
            if (h.ready) return 100;
            if (isNaN(since) || isNaN(healed) || healed <= since) return Number(h.progress_pct) || 0;
            return Math.max(0, Math.min(100, (u.serverNow() - since) / (healed - since) * 100));
        }

        function renderBedActions(view) {
            var pet = view.pet, h = pet.hospital;
            var sig = (h.ready ? 'ready' : 'heal') + (view.confirm ? '|confirm' : '');
            if (sig === view.sig) return;
            var hadFocus = view.actions.contains(document.activeElement);
            view.sig = sig;
            view.actions.innerHTML = '';
            var focusTarget = null;
            if (h.ready) {
                focusTarget = u.button('Odbierz', 'home', 'primary', { hospAction: 'discharge', petId: String(pet.id) });
                view.actions.appendChild(focusTarget);
            } else if (view.confirm) {
                var health = Math.round((pet.bars && pet.bars.health) || 0);
                var q = el('p', 'pets-bed__confirm', 'Pupil ' + (pet.name || '') + ' wróci z obecnym zdrowiem (' + health + '%). Zabrać go już teraz?');
                q.setAttribute('role', 'status');
                view.actions.appendChild(q);
                var row = el('div', 'pets-bed__confirm-row');
                focusTarget = u.button('Tak, zabieram', 'home', null, { hospAction: 'discharge', petId: String(pet.id) });
                row.appendChild(focusTarget);
                row.appendChild(u.button('Zostaw w szpitalu', null, 'ghost', { hospAction: 'confirm-cancel', petId: String(pet.id) }));
                view.actions.appendChild(row);
            } else {
                focusTarget = u.button('Zabierz wcześniej', null, 'ghost', { hospAction: 'early', petId: String(pet.id) });
                view.actions.appendChild(focusTarget);
            }
            if (hadFocus && focusTarget) focusTarget.focus();
        }

        function updateBed(view, pet) {
            view.pet = pet;
            var h = pet.hospital;
            if (h.ready) view.confirm = false;
            view.el.classList.toggle('is-ready', !!h.ready);
            view.name.textContent = pet.name || u.speciesName(pet.species);
            view.pat.setAttribute('aria-label', 'Pogłaszcz: ' + (pet.name || 'pupila'));
            view.track.setAttribute('aria-label', 'Leczenie: ' + (pet.name || 'pupil'));
            if (view.rig) {
                view.rig.update({ species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: false });
                if (typeof view.rig.setNeed === 'function' && R().needOf) view.rig.setNeed(R().needOf(pet));
            }
            renderBedActions(view);
            tickBed(view);
        }

        function tickBed(view) {
            var h = view.pet.hospital;
            var pct = healPct(h);
            view.fill.style.width = pct.toFixed(1) + '%';
            view.track.setAttribute('aria-valuenow', String(Math.round(pct)));
            var status, note;
            if (h.ready) {
                status = 'Gotowy do odbioru!';
                var auto = u.secondsUntil(h.auto_discharge_at);
                note = 'Tęskni za domem — z każdą godziną czekania jest smutniejszy.' +
                    (auto > 0 ? ' Sam wróci za ' + u.roughDuration(auto) + '.' : '');
            } else {
                status = 'Wraca do zdrowia — jeszcze ' + u.roughDuration(u.secondsUntil(h.healed_at)) + ' do wyzdrowienia';
                note = 'Leży pod kołderką. W szpitalu jego potrzeby nie rosną.';
            }
            if (view.status.textContent !== status) view.status.textContent = status;
            if (view.note.textContent !== note) view.note.textContent = note;
        }

        function sickRow(pet) {
            var li = el('li', 'pets-sick__row');
            li.dataset.petId = String(pet.id);
            var art = el('span', 'pets-sick__art');
            art.setAttribute('aria-hidden', 'true');
            var info = el('div', 'pets-sick__info');
            var name = el('span', 'pets-sick__name');
            var meta = el('span', 'pets-sick__meta');
            info.appendChild(name);
            info.appendChild(meta);
            var btnWrap = el('div', 'pets-sick__action');
            var btn = u.button('Przyjmij', 'cross', 'primary', { hospAction: 'admit', petId: String(pet.id) });
            var reason = el('p', 'pets-sick__reason');
            reason.id = 'petsSickReason' + pet.id;
            btn.setAttribute('aria-describedby', reason.id);
            btnWrap.appendChild(btn);
            btnWrap.appendChild(reason);
            li.appendChild(art);
            li.appendChild(info);
            li.appendChild(btnWrap);
            var rig = R() ? R().mount(art, {
                species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: pet.asleep,
                size: 'mini', need: R().needOf ? R().needOf(pet) : 'sick', pose: 'lie'
            }) : null;
            var view = { el: li, rig: rig, name: name, meta: meta, btn: btn, reason: reason };
            updateSick(view, pet);
            return view;
        }

        function updateSick(view, pet) {
            view.name.textContent = pet.name || u.speciesName(pet.species);
            var health = Math.round((pet.bars && pet.bars.health) || 0);
            view.meta.textContent = (pet.mood === 'krytyczny' ? 'W stanie krytycznym' : 'Chory') + ' · zdrowie ' + health + '%';
            var ok = !!(pet.can && pet.can.admit);
            if (ok) view.btn.removeAttribute('aria-disabled');
            else view.btn.setAttribute('aria-disabled', 'true');
            var reason = !ok && pet.reasons && pet.reasons.admit ? pet.reasons.admit.charAt(0).toUpperCase() + pet.reasons.admit.slice(1) : '';
            if (view.reason.textContent !== reason) view.reason.textContent = reason;
            if (view.rig) {
                view.rig.update({ species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: pet.asleep });
                if (typeof view.rig.setNeed === 'function' && R().needOf) view.rig.setNeed(R().needOf(pet));
            }
        }

        function syncList(views, list, box, make, update) {
            var seen = {};
            list.forEach(function (pet, i) {
                seen[pet.id] = true;
                var view = views[pet.id];
                if (view) update(view, pet);
                else view = views[pet.id] = make(pet);
                if (box.children[i] !== view.el) box.insertBefore(view.el, box.children[i] || null);
            });
            Object.keys(views).forEach(function (id) {
                if (seen[id]) return;
                var view = views[id];
                if (view.rig) view.rig.destroy();
                if (view.el.parentNode) view.el.parentNode.removeChild(view.el);
                delete views[id];
            });
        }

        function renderWard(state) {
            var pets = state.pets || [];
            var inBed = pets.filter(function (p) { return p.hospital; });
            var sick = pets.filter(function (p) { return !p.hospital && SICK.indexOf(p.mood) >= 0; });
            syncList(bedViews, inBed, beds, bedView, updateBed);
            syncList(sickViews, sick, sickList, sickRow, updateSick);
            beds.hidden = !inBed.length;
            sickBox.hidden = !sick.length;
            wardEmpty.hidden = !!(inBed.length || sick.length);
            var hours = state.config && state.config.hospital_hours;
            var lead = 'Chory pupil wraca tu do zdrowia' + (hours ? ' (najwyżej ' + hours + ' h)' : '') +
                ' — w tym czasie jego potrzeby nie rosną. Wyleczonego odbierz szybko, bo tęskni za domem.';
            if (wardLead.textContent !== lead) wardLead.textContent = lead;
        }

        // --- akcje (delegacja) -------------------------------------------------------------

        wrap.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-hosp-action]');
            if (!btn || !wrap.contains(btn) || btn.disabled || btn.getAttribute('aria-disabled') === 'true') return;
            var action = btn.dataset.hospAction;
            var petId = btn.dataset.petId ? parseInt(btn.dataset.petId, 10) : null;
            if (action === 'claim') {
                var body = { source: btn.dataset.source };
                if (petId) body.pet_id = petId;
                u.setBusy(btn, true);
                ctx.send('/jajka/odbierz', body).then(function () {
                    if (body.source === 'start') {
                        // Pierwsze jajko = najlepszy moment na prośbę o pushe (push-banner.js sam sprawdza subskrypcję)
                        try { window.dispatchEvent(new Event('push-force-banner')); } catch (err) { /* stare przeglądarki */ }
                    }
                    u.toast('Jajko odebrane! Ogrzewaj je przy każdej wizycie, a szybciej się wykluje.', 'success');
                    if (!document.body.contains(btn)) {
                        incTitle.setAttribute('tabindex', '-1');
                        try { incTitle.focus({ preventScroll: true }); } catch (err) { incTitle.focus(); }
                    }
                }, function () { u.setBusy(btn, false); });
            } else if (action === 'warm') {
                u.setBusy(btn, true);
                ctx.send('/jajka/' + parseInt(btn.dataset.eggId, 10) + '/ogrzej', {}).then(function () {
                    if (window.Haptics) window.Haptics.tap();
                }, function () { u.setBusy(btn, false); });
            } else if (action === 'hatch') {
                hatchEgg(parseInt(btn.dataset.eggId, 10), btn);
            } else if (action === 'pat') {
                var view = bedViews[petId];
                if (view && ctx.pat(petId) && view.rig) {
                    if (typeof view.rig.pat === 'function') view.rig.pat();
                    else view.rig.playAction('pat');
                }
            } else if (action === 'early' || action === 'confirm-cancel') {
                var bed = bedViews[petId];
                if (!bed) return;
                bed.confirm = action === 'early';
                bed.sig = '';
                var keep = document.activeElement;
                renderBedActions(bed);
                if (bed.actions.contains(keep) === false) {
                    var first = bed.actions.querySelector('button');
                    if (first) first.focus();
                }
            } else if (action === 'discharge') {
                var pet = ctx.findPet(petId);
                u.setBusy(btn, true);
                ctx.send('/' + petId + '/wypis', {}).then(function () {
                    u.toast('Pupil ' + ((pet && pet.name) || '') + ' wrócił do domku!', 'success');
                    ctx.go('domek', { pupil: petId });
                }, function () { u.setBusy(btn, false); });
            } else if (action === 'admit') {
                var sickPet = ctx.findPet(petId);
                u.setBusy(btn, true);
                ctx.send('/' + petId + '/szpital', {}).then(function () {
                    u.toast('Pupil ' + ((sickPet && sickPet.name) || '') + ' leży już w łóżku. Wróci zdrowy!', 'success');
                    focusBed(petId, true);
                }, function () { u.setBusy(btn, false); });
            }
        });

        function focusBed(petId, moveFocus) {
            var view = bedViews[petId];
            var target = view ? view.el : (sickViews[petId] && sickViews[petId].el);
            if (!target) return false;
            try {
                target.scrollIntoView({ block: 'center', behavior: u.reducedMotion() ? 'auto' : 'smooth' });
            } catch (e) { target.scrollIntoView(); }
            target.classList.remove('is-highlight');
            void target.offsetWidth;
            target.classList.add('is-highlight');
            if (moveFocus && view) view.pat.focus({ preventScroll: true });
            return true;
        }

        function render(state) {
            renderIncubator(state);
            renderWard(state);
            if (pending) {
                var params = pending;
                pending = null;
                if (params.pupil) focusBed(params.pupil, false);
            }
        }

        return {
            enter: function (params) {
                pending = params || null;
            },
            leave: function () {
                // Ukryta scena nie trzyma żywych rigów (timery mrugania i gestów) — render zbuduje je od nowa
                pending = null;
                syncList(eggViews, [], nests, null, null);
                syncList(bedViews, [], beds, null, null);
                syncList(sickViews, [], sickList, null, null);
                claimSig = null;
                claimBox.innerHTML = '';
            },
            render: render,
            setParams: function (params) {
                if (params && params.pupil) focusBed(params.pupil, false);
            },
            tick: function () {
                var state = ctx.state();
                if (!state) return;
                Object.keys(eggViews).forEach(function (id) { tickEgg(eggViews[id]); });
                Object.keys(bedViews).forEach(function (id) { tickBed(bedViews[id]); });
                tickMonthly(state);
            }
        };
    }

    W.scenes.szpital = {
        title: 'Szpital',
        lead: 'Inkubatornia z jajkami i sala chorych, gdzie pupile wracają do zdrowia.',
        create: create
    };
})();
