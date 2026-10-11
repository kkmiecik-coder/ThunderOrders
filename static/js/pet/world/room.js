/**
 * PetRoom — pokój pupili (spec v3 §6.1, §7): wspólny dla domku (pełny) i widgetu dashboardu (compact).
 *
 * API (kontrakt planu Task 7 → Task 8):
 *   PetRoom.mount(container, {pets, night, compact, mainPetId, onPetClick(petId), interactive}) -> room
 *     room.update(pets, {night, mainPetId}) · room.focus(petId | null) · room.pat(petId) -> Promise
 *     room.playAction(petId, action, variant) -> Promise · room.destroy() · room.el
 *     (+ room.petButton(petId) — przycisk pupila, np. do oddania fokusu po zamknięciu panelu)
 *
 * Zachowanie:
 *   - pupile w szpitalu (`pet.hospital`) nie pojawiają się w pokoju; do 8 pupili;
 *   - zachowanie wg najpilniejszej potrzeby (PetRig.needOf): chory/krytyczny leży na dywanie, śpiący idzie
 *     do koszyka, głodny siada przy misce, smutny/znudzony w kącie, brudny i szczęśliwy spacerują
 *     (jak towarzysz: przerwy 4–9 s, bez nakładania się); wygląd potrzeby rysuje rig (setNeed/setPose);
 *   - focus(id): pupil podchodzi na środek, lekko się powiększa, reszta przygasa; focus(null) = powrót;
 *   - compact (widget): mniejsza skala, `mainPetId` duży na środku z dymkiem potrzeby, max 4 pozostałych
 *     w tle + znacznik „+N”, bez spaceru po całej szerokości (lekkie ruchy w miejscu);
 *   - interactive: false — pupile są tylko linkami do domku (klik woła onPetClick), bez fokusu/pat;
 *   - prefers-reduced-motion (lub html.pet-rig-rm): bez spaceru i przejść — pupile stają od razu na miejscu.
 * Bezpieczeństwo: imiona przez textContent / setAttribute; zero inline onclick (delegacja).
 * Plik ładuje się na kilku stronach (domek + dashboard) — guard idempotencji.
 */
(function () {
    'use strict';

    if (window.PetRoom) return;

    var MAX_PETS = 8;
    var COMPACT_BACK = 4;
    var WALK_SPEED = 46;                 // px/s
    var PAUSE_MIN = 4000, PAUSE_MAX = 9000;
    var NUDGE_MIN = 5000, NUDGE_MAX = 11000;

    var NEED_LABEL = {
        happy: 'szczęśliwy', hungry: 'głodny', dirty: 'brudny', sad: 'smutny', bored: 'znudzony',
        sick: 'chory', critical: 'w stanie krytycznym', sleep: 'śpi'
    };
    // Dymek nad głównym pupilem w widgecie (spec v3 §7)
    var NEED_BUBBLE = {
        hungry: 'Jestem głodny!', dirty: 'Chcę się umyć!', sad: 'Smutno mi…', bored: 'Nudzę się…',
        sick: 'Źle się czuję…', critical: 'Pomocy!', sleep: 'Zzz…'
    };
    // Potrzeba → miejsce w pokoju i poza
    var BEHAVIOR = {
        sick: ['rug', 'lie'], critical: ['rug', 'lie'], sleep: ['basket', 'lie'], hungry: ['bowl', 'sit'],
        sad: ['corner', 'sit'], bored: ['corner', 'sit'], dirty: ['wander', 'stand'], happy: ['wander', 'stand']
    };
    // Miejsca: x = środek pupila (ułamek szerokości), y = odległość stóp od dołu (ułamek wysokości pokoju)
    var SPOTS = {
        bowl: [[0.24, 0.05], [0.31, 0.11], [0.2, 0.15], [0.36, 0.04]],
        basket: [[0.87, 0.08], [0.72, 0.05], [0.79, 0.16], [0.64, 0.12]],
        corner: [[0.07, 0.22], [0.15, 0.25], [0.24, 0.27], [0.1, 0.16]],
        rug: [[0.44, 0.09], [0.56, 0.05], [0.5, 0.17], [0.38, 0.15]]
    };
    var WANDER = { x0: 0.3, x1: 0.7, y0: 0.03, y1: 0.2 };
    var FOCUS_SPOT = [0.5, 0.04];
    var COMPACT_MAIN = [0.5, 0.05];
    var COMPACT_SLOTS = [[0.15, 0.17], [0.85, 0.17], [0.3, 0.27], [0.7, 0.27]];

    function reducedMotion() {
        if (window.PetRig && typeof window.PetRig.reducedMotion === 'function') return window.PetRig.reducedMotion();
        return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

    function rand(a, b) { return a + Math.random() * (b - a); }

    function needOf(pet) {
        var R = window.PetRig;
        if (R && typeof R.needOf === 'function') return R.needOf(pet);
        return 'happy';
    }

    // --- tło pokoju (kodowane SVG, kolory ilustracji stałe; noc = klasa .is-night) -------------

    var WINDOW_SVG =
        '<svg class="pet-room__window" viewBox="0 0 120 90" aria-hidden="true" focusable="false">' +
        '<rect x="3" y="3" width="114" height="84" rx="6" class="pr-sky"/>' +
        '<g class="pr-day"><circle cx="90" cy="24" r="10" fill="#ffe27a"/><ellipse cx="34" cy="30" rx="16" ry="6" fill="#ffffff"/>' +
        '<ellipse cx="44" cy="26" rx="10" ry="5" fill="#ffffff"/><path d="M3 70 Q30 56 60 66 T117 62 V87 H3 Z" fill="#a8dc8f"/></g>' +
        '<g class="pr-night"><circle cx="88" cy="24" r="9" fill="#fff4c2"/><circle cx="93" cy="20" r="8" fill="#1d2550"/>' +
        '<circle cx="24" cy="18" r="1.4" fill="#fff8d6"/><circle cx="46" cy="36" r="1.2" fill="#fff8d6"/><circle cx="66" cy="14" r="1.5" fill="#fff8d6"/>' +
        '<circle cx="104" cy="50" r="1.2" fill="#fff8d6"/><circle cx="16" cy="54" r="1.1" fill="#fff8d6"/></g>' +
        '<rect x="3" y="3" width="114" height="84" rx="6" fill="none" stroke="#ffffff" stroke-width="6"/>' +
        '<line x1="60" y1="3" x2="60" y2="87" stroke="#ffffff" stroke-width="4"/>' +
        '<line x1="3" y1="45" x2="117" y2="45" stroke="#ffffff" stroke-width="3"/>' +
        '<path d="M0 2 Q14 40 4 88" stroke="#ff9ec4" stroke-width="7" fill="none" opacity=".85"/>' +
        '<path d="M120 2 Q106 40 116 88" stroke="#ff9ec4" stroke-width="7" fill="none" opacity=".85"/>' +
        '</svg>';
    var PICTURE_SVG =
        '<svg class="pet-room__picture" viewBox="0 0 40 32" aria-hidden="true" focusable="false">' +
        '<rect x="1" y="1" width="38" height="30" rx="3" fill="#fff6e8" stroke="#d9a877" stroke-width="2"/>' +
        '<path d="M20 25s-8-4.6-8-10a4.2 4.2 0 0 1 8-1.6 4.2 4.2 0 0 1 8 1.6c0 5.4-8 10-8 10z" fill="#ff8fab"/></svg>';
    var LAMP_SVG =
        '<svg class="pet-room__lamp" viewBox="0 0 40 70" aria-hidden="true" focusable="false">' +
        '<ellipse class="pr-lamp-glow" cx="20" cy="22" rx="20" ry="22" fill="#ffd36b"/>' +
        '<path d="M8 6 H32 L36 26 H4 Z" fill="#ffc6d9" stroke="#f3a3be"/><rect x="18.5" y="26" width="3" height="36" fill="#c4925f"/>' +
        '<ellipse cx="20" cy="64" rx="11" ry="4" fill="#c4925f"/></svg>';
    var BOWLS_SVG =
        '<svg class="pet-room__bowls" viewBox="0 0 100 34" aria-hidden="true" focusable="false">' +
        '<ellipse cx="26" cy="28" rx="24" ry="5" fill="#000" opacity=".1"/><ellipse cx="74" cy="28" rx="24" ry="5" fill="#000" opacity=".1"/>' +
        '<path d="M4 14 H48 L42 28 H10 Z" fill="#7fb3ea"/><ellipse cx="26" cy="14" rx="22" ry="6" fill="#a9cdf3"/>' +
        '<ellipse cx="26" cy="14" rx="15" ry="3.6" fill="#c98b5c"/><circle cx="21" cy="12.5" r="2" fill="#a86f45"/><circle cx="29" cy="13" r="2.2" fill="#a86f45"/>' +
        '<path d="M52 14 H96 L90 28 H58 Z" fill="#ffd36b"/><ellipse cx="74" cy="14" rx="22" ry="6" fill="#ffe7a3"/>' +
        '<ellipse cx="74" cy="14" rx="15" ry="3.6" fill="#9fd3ff"/></svg>';
    var BASKET_SVG =
        '<svg class="pet-room__basket" viewBox="0 0 120 56" aria-hidden="true" focusable="false">' +
        '<ellipse cx="60" cy="50" rx="56" ry="6" fill="#000" opacity=".1"/>' +
        '<path d="M8 24 Q60 -6 112 24 V44 Q60 58 8 44 Z" fill="#c98b5c"/>' +
        '<path d="M14 26 Q60 2 106 26" stroke="#a86f45" stroke-width="3" fill="none"/>' +
        '<g stroke="#a86f45" stroke-width="2" opacity=".6"><path d="M20 30 V44"/><path d="M34 26 V48"/><path d="M48 24 V50"/><path d="M62 24 V50"/><path d="M76 24 V50"/><path d="M90 26 V48"/><path d="M102 30 V44"/></g>' +
        '<ellipse cx="60" cy="30" rx="44" ry="10" fill="#f6b6c9"/><ellipse cx="60" cy="28" rx="38" ry="7" fill="#ffd3e1"/></svg>';
    var CUSHION_SVG =
        '<svg class="pet-room__cushion" viewBox="0 0 80 28" aria-hidden="true" focusable="false">' +
        '<ellipse cx="40" cy="24" rx="36" ry="4" fill="#000" opacity=".08"/>' +
        '<path d="M6 14 Q40 -2 74 14 Q76 24 40 26 Q4 24 6 14 Z" fill="#b99cff"/><path d="M14 13 Q40 4 66 13" stroke="#d6c6ff" stroke-width="2" fill="none"/></svg>';
    var TOYS_SVG =
        '<svg class="pet-room__toys" viewBox="0 0 70 30" aria-hidden="true" focusable="false">' +
        '<ellipse cx="18" cy="26" rx="12" ry="3" fill="#000" opacity=".1"/><circle cx="18" cy="15" r="11" fill="#ff6b7d"/>' +
        '<path d="M8 12 Q18 18 28 12 M9 19 Q18 13 27 19" stroke="#ffffff" stroke-width="2" fill="none"/>' +
        '<ellipse cx="52" cy="27" rx="10" ry="2.6" fill="#000" opacity=".1"/><circle cx="52" cy="19" r="8" fill="#7fd3c4"/>' +
        '<path d="M45 16 Q52 22 59 15 M46 22 Q53 17 59 22" stroke="#4fb5a6" stroke-width="1.6" fill="none"/>' +
        '<path d="M59 21 Q66 26 68 18" stroke="#7fd3c4" stroke-width="1.6" fill="none"/></svg>';

    function sceneMarkup(compact) {
        return '<div class="pet-room__scene" aria-hidden="true">' +
            '<div class="pet-room__wall"></div>' + WINDOW_SVG + (compact ? '' : PICTURE_SVG + LAMP_SVG) +
            '<div class="pet-room__floor"></div><div class="pet-room__rug"></div>' +
            BOWLS_SVG + BASKET_SVG + (compact ? '' : CUSHION_SVG) + TOYS_SVG +
            '<div class="pet-room__dark"></div></div>';
    }

    // --- pokój -----------------------------------------------------------------------------

    function mount(container, opts) {
        opts = opts || {};
        var compact = !!opts.compact;
        var interactive = opts.interactive !== false;
        var night = !!opts.night;
        var mainId = opts.mainPetId != null ? opts.mainPetId : null;
        var focusedId = null;
        var destroyed = false;
        var entries = {};           // id → {pet, el, flip, rig, name, need, pose, x, y, place, acting, timer}
        var order = [];

        var el = document.createElement('div');
        el.className = 'pet-room' + (compact ? ' pet-room--compact' : '') + (interactive ? ' is-interactive' : '');
        el.innerHTML = sceneMarkup(compact);
        var layer = document.createElement('div');
        layer.className = 'pet-room__pets';
        el.appendChild(layer);
        var bubble = document.createElement('span');
        bubble.className = 'pet-room__bubble';
        bubble.hidden = true;
        bubble.setAttribute('aria-hidden', 'true');
        el.appendChild(bubble);
        var more = document.createElement('span');
        more.className = 'pet-room__more';
        more.hidden = true;
        el.appendChild(more);
        var room = { el: el };

        function width() { return el.clientWidth || 600; }
        function height() { return el.clientHeight || 300; }

        function place(entry, x, y, instant) {
            var dist = Math.hypot((x - entry.x) * width(), (y - entry.y) * height());
            var moving = !instant && !reducedMotion() && entry.x != null && dist > 2;
            entry.el.classList.toggle('is-walking', moving);
            // Wartości dynamiczne (pozycja, czas marszu, głębia) — reszta wyglądu w pet-room.css
            entry.el.style.setProperty('--walk', moving ? Math.max(0.5, dist / WALK_SPEED).toFixed(2) + 's' : '0s');
            entry.el.style.setProperty('--depth', (1 - y * 0.7).toFixed(3));
            entry.x = x;
            entry.y = y;
            entry.el.style.left = (x * 100).toFixed(2) + '%';
            entry.el.style.bottom = (y * 100).toFixed(2) + '%';
            entry.el.style.zIndex = String(100 - Math.round(y * 100) + (entry.pet.id === focusedId ? 50 : 0));
            clearTimeout(entry.arrive);
            if (moving) {
                entry.arrive = setTimeout(function () {
                    entry.el.classList.remove('is-walking');
                    if (compact && entry.pet.id === mainId) placeBubble();
                }, dist / WALK_SPEED * 1000);
            }
        }

        function tooClose(entry, x, y) {
            return order.some(function (id) {
                var o = entries[id];
                return o && o !== entry && o.x != null && Math.abs(o.x - x) < 0.1 && Math.abs(o.y - y) < 0.08;
            });
        }

        function freeWanderSpot(entry) {
            var best = null;
            for (var i = 0; i < 10; i++) {
                var x = rand(WANDER.x0, WANDER.x1), y = rand(WANDER.y0, WANDER.y1);
                best = [x, y];
                if (!tooClose(entry, x, y)) break;
            }
            return best;
        }

        function scheduleWander(entry) {
            clearTimeout(entry.timer);
            if (destroyed || reducedMotion()) return;
            if (compact) {
                // Lekkie ruchy w miejscu (widget): krok w lewo/prawo wokół miejsca
                entry.timer = setTimeout(function () {
                    if (destroyed || entry.acting) return scheduleWander(entry);
                    var home = entry.home || [entry.x, entry.y];
                    place(entry, Math.max(0.06, Math.min(0.94, home[0] + rand(-0.035, 0.035))), home[1]);
                    scheduleWander(entry);
                }, rand(NUDGE_MIN, NUDGE_MAX));
                return;
            }
            if (entry.place !== 'wander') return;
            entry.timer = setTimeout(function () {
                if (destroyed) return;
                if (!entry.acting && focusedId !== entry.pet.id && entry.place === 'wander') {
                    var spot = freeWanderSpot(entry);
                    place(entry, spot[0], spot[1]);
                }
                scheduleWander(entry);
            }, rand(PAUSE_MIN, PAUSE_MAX));
        }

        /** Rozmieszcza pupili wg potrzeb (albo wg układu widgetu). */
        function layout(instant) {
            var used = { bowl: 0, basket: 0, corner: 0, rug: 0 };
            if (compact) {
                var slot = 0;
                order.forEach(function (id) {
                    var e = entries[id];
                    if (id === mainId) e.home = COMPACT_MAIN;
                    else e.home = COMPACT_SLOTS[slot++] || COMPACT_SLOTS[COMPACT_SLOTS.length - 1];
                    e.el.classList.toggle('is-main', id === mainId);
                    e.el.classList.toggle('is-back', id !== mainId);
                    if (e.x == null || instant) place(e, e.home[0], e.home[1], true);
                    else place(e, e.home[0], e.home[1]);
                    scheduleWander(e);
                });
                placeBubble();
                return;
            }
            order.forEach(function (id) {
                var e = entries[id];
                var target;
                if (id === focusedId) {
                    target = FOCUS_SPOT;
                } else if (e.place === 'wander') {
                    target = (e.x != null && e.wanderOk && !tooClose(e, e.x, e.y)) ? [e.x, e.y] : freeWanderSpot(e);
                    e.wanderOk = true;
                } else {
                    var list = SPOTS[e.place];
                    var n = used[e.place]++;
                    target = list[n % list.length].slice();
                    if (n >= list.length) target[0] = Math.min(0.94, target[0] + 0.05 * Math.floor(n / list.length));
                    e.wanderOk = false;
                }
                place(e, target[0], target[1], instant || e.x == null);
                scheduleWander(e);
            });
        }

        function placeBubble() {
            if (!compact) return;
            var main = mainId != null && entries[mainId];
            var text = main ? NEED_BUBBLE[main.need] : '';
            bubble.hidden = !text;
            if (!text) return;
            if (bubble.textContent !== text) bubble.textContent = text;
            bubble.style.left = (main.x * 100).toFixed(2) + '%';
        }

        function labelFor(pet, need) {
            var name = pet.name || 'Pupil';
            var state = NEED_LABEL[need] || '';
            if (!interactive) return name + (state ? ' — ' + state : '') + '. Przejdź do domku';
            return name + (state ? ' — ' + state : '');
        }

        function applyPet(entry, pet) {
            entry.pet = pet;
            var need = needOf(pet);
            var behavior = BEHAVIOR[need] || BEHAVIOR.happy;
            var changed = need !== entry.need;
            entry.need = need;
            entry.place = behavior[0];
            entry.pose = behavior[1];
            entry.el.setAttribute('data-need', need);
            entry.el.setAttribute('aria-label', labelFor(pet, need));
            if (entry.name) entry.name.textContent = pet.name || '';
            if (entry.rig) {
                entry.rig.update({ species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: pet.asleep });
                if (typeof entry.rig.setNeed === 'function') entry.rig.setNeed(need);
                if (typeof entry.rig.setPose === 'function') entry.rig.setPose(entry.pose);
            }
            return changed;
        }

        function createEntry(pet) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'pet-room__pet';
            btn.setAttribute('data-pet-id', String(pet.id));
            var flip = document.createElement('span');
            flip.className = 'pet-room__body';
            btn.appendChild(flip);
            var name = null;
            if (!compact) {
                name = document.createElement('span');
                name.className = 'pet-room__name';
                name.setAttribute('aria-hidden', 'true');
                btn.appendChild(name);
            }
            layer.appendChild(btn);
            var entry = { pet: pet, el: btn, flip: flip, rig: null, name: name, need: null, pose: 'stand', x: null, y: null, place: 'wander', acting: 0, timer: 0, arrive: 0 };
            var need = needOf(pet);
            var behavior = BEHAVIOR[need] || BEHAVIOR.happy;
            if (window.PetRig) {
                entry.rig = window.PetRig.mount(flip, {
                    species: pet.species, stage: pet.stage, stars: pet.stars, mood: pet.mood, asleep: pet.asleep,
                    size: 'mini', idle: !compact, need: need, pose: behavior[1]
                });
            }
            applyPet(entry, pet);
            return entry;
        }

        function destroyEntry(id) {
            var e = entries[id];
            if (!e) return;
            clearTimeout(e.timer);
            clearTimeout(e.arrive);
            if (e.rig) e.rig.destroy();
            if (e.el.parentNode) e.el.parentNode.removeChild(e.el);
            delete entries[id];
        }

        function visiblePets(pets) {
            var list = (pets || []).filter(function (p) { return p && !p.hospital; });
            if (!compact) return list.slice(0, MAX_PETS);
            // Widget: główny + do 4 pozostałych (kolejność ze stanu)
            var main = list.filter(function (p) { return p.id === mainId; })[0] || null;
            if (!main && list.length) {
                main = list[0];
            }
            var rest = list.filter(function (p) { return p !== main; });
            more.hidden = rest.length <= COMPACT_BACK;
            more.textContent = rest.length > COMPACT_BACK ? '+' + (rest.length - COMPACT_BACK) : '';
            if (!more.hidden) more.setAttribute('aria-label', 'i jeszcze ' + (rest.length - COMPACT_BACK));
            return main ? [main].concat(rest.slice(0, COMPACT_BACK)) : [];
        }

        room.update = function (pets, o) {
            if (destroyed) return room;
            o = o || {};
            if (o.night != null) night = !!o.night;
            if (o.mainPetId !== undefined) mainId = o.mainPetId;
            el.classList.toggle('is-night', night);
            var list = visiblePets(pets);
            if (compact && list.length && (mainId == null || !list.some(function (p) { return p.id === mainId; }))) mainId = list[0].id;
            var seen = {};
            var relayout = false;
            list.forEach(function (pet) {
                seen[pet.id] = true;
                if (entries[pet.id]) {
                    if (applyPet(entries[pet.id], pet)) relayout = true;
                } else {
                    entries[pet.id] = createEntry(pet);
                    relayout = true;
                }
            });
            Object.keys(entries).forEach(function (id) {
                if (!seen[id]) {
                    destroyEntry(id);
                    relayout = true;
                    if (String(focusedId) === id) focusedId = null;
                }
            });
            var nextOrder = list.map(function (p) { return p.id; });
            if (nextOrder.join(',') !== order.join(',')) relayout = true;
            order = nextOrder;
            el.classList.toggle('has-focus', focusedId != null && !!entries[focusedId]);
            if (relayout) layout(false);
            else if (compact) placeBubble();
            return room;
        };

        room.focus = function (id) {
            if (destroyed) return room;
            focusedId = id != null && entries[id] ? id : null;
            order.forEach(function (pid) {
                var e = entries[pid];
                e.el.classList.toggle('is-focused', pid === focusedId);
                e.el.classList.toggle('is-dimmed', focusedId != null && pid !== focusedId);
                if (pid === focusedId) e.el.setAttribute('aria-pressed', 'true');
                else e.el.removeAttribute('aria-pressed');
            });
            el.classList.toggle('has-focus', focusedId != null);
            layout(false);
            return room;
        };

        function withRig(id, fn) {
            var e = entries[id];
            if (!e || !e.rig || destroyed) return Promise.resolve();
            e.acting += 1;
            var p;
            try { p = Promise.resolve(fn(e.rig)); } catch (err) { p = Promise.resolve(); }
            return p.then(function () { e.acting = Math.max(0, e.acting - 1); }, function () { e.acting = Math.max(0, e.acting - 1); });
        }

        room.pat = function (id) {
            return withRig(id, function (rig) {
                return typeof rig.pat === 'function' ? rig.pat() : rig.playAction('pat');
            });
        };

        room.playAction = function (id, action, variant) {
            return withRig(id, function (rig) {
                return variant ? rig.playAction(action, { variant: variant }) : rig.playAction(action);
            });
        };

        room.petButton = function (id) {
            return entries[id] ? entries[id].el : null;
        };

        room.destroy = function () {
            if (destroyed) return;
            Object.keys(entries).forEach(destroyEntry);
            destroyed = true;
            if (el.parentNode) el.parentNode.removeChild(el);
        };

        el.addEventListener('click', function (e) {
            var btn = e.target.closest('.pet-room__pet');
            if (!btn || !el.contains(btn)) return;
            var id = parseInt(btn.getAttribute('data-pet-id'), 10);
            if (typeof opts.onPetClick === 'function') opts.onPetClick(id);
        });

        container.appendChild(el);
        room.update(opts.pets || [], { night: night, mainPetId: mainId });
        layout(true);
        return room;
    }

    window.PetRoom = { mount: mount };
})();
