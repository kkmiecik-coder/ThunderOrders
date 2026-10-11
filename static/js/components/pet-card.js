/**
 * PetCard — karta pupila: pełna na /client/pupile, mini w widgecie dashboardu (etap 5).
 *
 * API (kontrakt — nazwy 1:1 z planem etapu 4):
 *   PetCard.render(container, petDict, opts) -> card
 *     opts: { mini: bool, species: {slug: {name, …}}, onAction(pet, action, count) -> Promise,
 *             onRename(pet, name) -> Promise (opcjonalny; tylko pełna karta),
 *             now: 'ISO z api/stan', night: {start, end} }
 *     card.update(petDict[, {now, night}]) · card.el · card.rig · card.destroy()
 *
 * Zachowanie:
 *   - akcje (feed/play/wash/heal/wake): przyciski zablokowane do rozstrzygnięcia Promise z onAction;
 *     animacja rigu dopiero po sukcesie (odpowiedź {ok: true}) — 409 nie udaje, że pupil zjadł;
 *     błędy obsługuje wołający (toast/odświeżenie), karta tylko wraca do stanu z danych;
 *   - pat pat (klik / Enter / spacja na scenie): animacja i wibracja od razu, klepnięcia zbierane
 *     w paczki — debounce 2 s, max 50 w paczce → onAction(pet, 'pat', n); przyrost przychodzi
 *     z odpowiedzią (update). Niewysłana paczka leci przy schowaniu karty i przy destroy();
 *   - paski ekstrapolowane co 1 s z rates_per_hour (klamra 0–100); can/reasons stoją do update;
 *   - powód niedostępności akcji tekstem POD przyciskiem (nie `title` — dotyk go nie pokaże);
 *   - imię: klik → edycja w miejscu; błąd {error: 'bad_name', message} przy polu, edycja zostaje.
 * Bezpieczeństwo: imiona wyłącznie przez textContent / setAttribute; zero inline onclick —
 * delegacja zdarzeń z data-card-action.
 */
(function () {
    'use strict';

    var PAT_DEBOUNCE_MS = 2000;
    var PAT_MAX = 50;
    var NAME_MAX = 20;

    var MOOD_LABEL = {
        szczesliwy: 'Szczęśliwy', glodny: 'Głodny', znudzony: 'Znudzony', brudny: 'Brudny',
        smutny: 'Smutny', chory: 'Chory', krytyczny: 'W stanie krytycznym'
    };
    var STAGE_LABEL = { maluch: 'Maluch', dziecko: 'Dziecko', dorosly: 'Dorosły' };
    var BARS = [
        { key: 'hunger', label: 'Sytość', low: 30, mid: 50 },
        { key: 'fun', label: 'Radość', low: 30, mid: 50 },
        { key: 'clean', label: 'Czystość', low: 30, mid: 50 },
        { key: 'health', label: 'Zdrowie', low: 25, mid: 75 }
    ];
    var ACTION_LABEL = { feed: 'Nakarm', play: 'Pobaw się', wash: 'Umyj', heal: 'Wylecz', wake: 'Obudź' };

    var ICONS = {
        feed: '<path d="M3 11h18a9 9 0 0 1-18 0z"/><path d="M8.5 7.5c0-1.4 1-1.9 1-3.3M12 7.5c0-1.4 1-1.9 1-3.3M15.5 7.5c0-1.4 1-1.9 1-3.3"/>',
        play: '<circle cx="12" cy="12" r="9"/><path d="M3.6 9.4c5 1.6 11.8 1.6 16.8 0M3.6 14.6c5-1.6 11.8-1.6 16.8 0"/>',
        wash: '<circle cx="8.5" cy="14.5" r="4.5"/><circle cx="16.5" cy="8" r="3"/><circle cx="17.5" cy="16.5" r="2"/>',
        heal: '<path d="M12 20.5s-7.5-4.6-9.2-9.4A4.9 4.9 0 0 1 12 7.6a4.9 4.9 0 0 1 9.2 3.5c-1.7 4.8-9.2 9.4-9.2 9.4z"/><path d="M12 10.5v6M9 13.5h6"/>',
        wake: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4"/>',
        pencil: '<path d="M4 20h4L19.5 8.5a2.1 2.1 0 0 0-3-3L5 17v3z"/><path d="M14.5 7.5l3 3"/>',
        check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
        close: '<path d="M6 6l12 12M18 6L6 18"/>'
    };

    function svg(name, cls) {
        return '<svg class="' + (cls || 'pet-btn__icon') + '" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" ' +
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + ICONS[name] + '</svg>';
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text;
        return node;
    }

    function parseLocal(iso) {
        if (!iso) return NaN;
        var m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(iso);
        if (!m) return NaN;
        return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0)).getTime();
    }

    function formatDuration(sec) {
        sec = Math.max(0, Math.round(sec));
        var d = Math.floor(sec / 86400), h = Math.floor(sec % 86400 / 3600);
        var m = Math.floor(sec % 3600 / 60), s = sec % 60;
        if (d > 0) return d + ' d ' + h + ' h';
        if (h > 0) return h + ' h ' + m + ' min';
        if (m > 0) return m + ' min ' + s + ' s';
        return s + ' s';
    }

    function capitalize(text) {
        text = String(text || '');
        return text.charAt(0).toUpperCase() + text.slice(1);
    }

    function daysLabel(n) {
        n = Math.max(0, parseInt(n, 10) || 0);
        return n + ' ' + (n === 1 ? 'dzień' : 'dni');
    }

    function clamp(v) {
        return Math.max(0, Math.min(100, v));
    }

    function hhmm(iso) {
        var m = /T(\d{2}):(\d{2})/.exec(iso || '');
        return m ? (+m[1]) + ':' + m[2] : '';
    }

    /** Imię po stronie klienta jak w serwisie: zbite białe znaki, 1–20 znaków (code pointów). */
    function cleanName(raw) {
        return String(raw || '').split(/\s+/).filter(Boolean).join(' ');
    }

    // Wspólny zegar dla wszystkich kart (ekstrapolacja pasków, odliczanie leku)
    var live = [];
    var ticker = 0;

    function startTicker() {
        if (ticker) return;
        ticker = setInterval(function () {
            live.slice().forEach(function (card) { card._tick(); });
        }, 1000);
    }

    function stopTickerIfIdle() {
        if (!live.length && ticker) {
            clearInterval(ticker);
            ticker = 0;
        }
    }

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') live.slice().forEach(function (card) { card._flushPats(); });
    });

    function render(container, petDict, opts) {
        opts = opts || {};
        var mini = !!opts.mini;
        var pet = null;
        var ctx = { now: opts.now || null, night: opts.night || null };
        var base = { at: Date.now(), bars: {}, rates: {} };
        var clockOffset = 0;
        var busy = false;
        var pendingPats = 0;
        var patTimer = 0;
        var destroyed = false;
        var editing = false;
        var actionsSig = '';

        var root = el('article', 'pet-card' + (mini ? ' pet-card--mini' : ''));
        var scene = el('div', 'pet-card__scene');
        scene.setAttribute('role', 'button');
        scene.tabIndex = 0;
        var rigBox = el('div', 'pet-card__rig');
        scene.appendChild(rigBox);
        var patHint = mini ? null : el('span', 'pet-card__pat-hint', 'Kliknij, by pogłaskać');
        if (patHint) scene.appendChild(patHint);

        var body = el('div', 'pet-card__body');
        var head = el('div', 'pet-card__head');
        var nameBtn = el('button', 'pet-card__name');
        nameBtn.type = 'button';
        var nameText = el('span', 'pet-card__name-text');
        nameBtn.appendChild(nameText);
        if (!mini && opts.onRename) {
            nameBtn.dataset.cardAction = 'rename';
            nameBtn.insertAdjacentHTML('beforeend', svg('pencil', 'pet-card__name-icon'));
        } else {
            nameBtn.disabled = true;
            nameBtn.classList.add('is-static');
        }
        var nameWrap = el('h3', 'pet-card__title');
        nameWrap.appendChild(nameBtn);
        head.appendChild(nameWrap);

        var renameForm = null, renameInput = null, renameError = null;
        if (!mini && opts.onRename) {
            renameForm = el('form', 'pet-card__rename');
            renameForm.hidden = true;
            renameForm.noValidate = true;
            renameInput = el('input', 'pet-card__rename-input');
            renameInput.type = 'text';
            renameInput.autocomplete = 'off';
            renameInput.setAttribute('maxlength', '40');
            renameInput.setAttribute('aria-label', 'Nowe imię pupila');
            var save = el('button', 'pet-btn pet-btn--primary pet-card__rename-btn');
            save.type = 'submit';
            save.setAttribute('aria-label', 'Zapisz imię');
            save.innerHTML = svg('check');
            var cancel = el('button', 'pet-btn pet-card__rename-btn');
            cancel.type = 'button';
            cancel.dataset.cardAction = 'rename-cancel';
            cancel.setAttribute('aria-label', 'Anuluj zmianę imienia');
            cancel.innerHTML = svg('close');
            var row = el('div', 'pet-card__rename-row');
            row.appendChild(renameInput);
            row.appendChild(save);
            row.appendChild(cancel);
            renameError = el('p', 'pet-card__rename-error');
            renameError.setAttribute('role', 'alert');
            renameError.hidden = true;
            renameForm.appendChild(row);
            renameForm.appendChild(renameError);
            head.appendChild(renameForm);
        }

        var meta = el('p', 'pet-card__meta');
        var mood = el('p', 'pet-card__mood');
        head.appendChild(meta);
        head.appendChild(mood);

        var barsBox = el('div', 'pet-card__bars');
        var barEls = {};
        BARS.forEach(function (b) {
            var row = el('div', 'pet-bar pet-bar--' + b.key);
            var top = el('div', 'pet-bar__top');
            top.appendChild(el('span', 'pet-bar__label', b.label));
            var value = el('span', 'pet-bar__value');
            top.appendChild(value);
            var track = el('div', 'pet-bar__track');
            track.setAttribute('role', 'progressbar');
            track.setAttribute('aria-label', b.label);
            track.setAttribute('aria-valuemin', '0');
            track.setAttribute('aria-valuemax', '100');
            var fill = el('div', 'pet-bar__fill');
            track.appendChild(fill);
            row.appendChild(top);
            row.appendChild(track);
            barsBox.appendChild(row);
            barEls[b.key] = { row: row, value: value, track: track, fill: fill, def: b };
        });

        var actionsBox = el('div', 'pet-card__actions');
        var hint = el('p', 'pet-card__hint');
        hint.hidden = true;

        body.appendChild(head);
        body.appendChild(barsBox);
        body.appendChild(actionsBox);
        body.appendChild(hint);
        root.appendChild(scene);
        root.appendChild(body);

        var rig = window.PetRig ? window.PetRig.mount(rigBox, {
            species: petDict.species, stage: petDict.stage, stars: petDict.stars, mood: petDict.mood,
            asleep: petDict.asleep, size: mini ? 'mini' : 'card', idle: true
        }) : null;

        var card = { el: root, rig: rig };

        // --- render -------------------------------------------------------------------------

        function visibleActions() {
            if (pet.asleep) return ['wake'];
            var list = ['feed', 'play', 'wash'];
            // „Wylecz" tylko u chorego — u zdrowego byłby wiecznie szary przycisk z „zdrowy"
            if (pet.reasons && pet.reasons.heal !== 'zdrowy') list.push('heal');
            return list;
        }

        function reasonText(action) {
            var reason = pet.reasons && pet.reasons[action];
            if (!reason || (pet.can && pet.can[action])) return '';
            if (action === 'heal' && pet.heal_available_at) {
                var left = (parseLocal(pet.heal_available_at) - (Date.now() + clockOffset)) / 1000;
                if (left > 0) return capitalize(reason) + ' — kolejny za ' + formatDuration(left);
            }
            return capitalize(reason);
        }

        function renderActions(force) {
            var list = visibleActions();
            var sig = list.join(',') + '|' + JSON.stringify(pet.can || {}) + '|' + JSON.stringify(pet.reasons || {}) + '|' + busy;
            if (!force && sig === actionsSig) {
                tickReasons();
                return;
            }
            actionsSig = sig;
            actionsBox.innerHTML = '';
            actionsBox.classList.toggle('is-single', list.length === 1);
            list.forEach(function (action) {
                var wrap = el('div', 'pet-action');
                var btn = el('button', 'pet-btn pet-action__btn' + (action === 'wake' ? ' pet-btn--primary' : ''));
                btn.type = 'button';
                btn.dataset.cardAction = action;
                btn.innerHTML = svg(action) + '<span class="pet-btn__label"></span>';
                btn.querySelector('.pet-btn__label').textContent = ACTION_LABEL[action];
                btn.disabled = busy || !(pet.can && pet.can[action]);
                var reason = el('p', 'pet-action__reason');
                reason.dataset.reasonFor = action;
                reason.textContent = reasonText(action);
                wrap.appendChild(btn);
                wrap.appendChild(reason);
                actionsBox.appendChild(wrap);
            });
        }

        function tickReasons() {
            if (!pet.heal_available_at) return;
            var r = actionsBox.querySelector('[data-reason-for="heal"]');
            if (r) r.textContent = reasonText('heal');
        }

        function renderHint() {
            var text = '';
            if (pet.asleep) {
                text = 'Śpi' + (ctx.night ? ' do ' + ctx.night.end + ':00' : '') +
                    ' — potrzeby rosną teraz 4× wolniej. Obudzenie kosztuje 10 punktów radości i czystości.';
            } else if (pet.awake_until) {
                text = 'Obudzony do ' + hhmm(pet.awake_until) + ' — każda opieka przedłuża czuwanie.';
            }
            hint.textContent = text;
            hint.hidden = !text;
        }

        function tickBars() {
            var hours = (Date.now() - base.at) / 3600000;
            BARS.forEach(function (b) {
                var refs = barEls[b.key];
                if (refs.row.hidden) return;
                var v = clamp((base.bars[b.key] || 0) + (base.rates[b.key] || 0) * hours);
                var shown = Math.round(v);
                refs.value.textContent = shown + '%';
                refs.fill.style.width = v.toFixed(1) + '%';
                refs.track.setAttribute('aria-valuenow', String(shown));
                refs.row.classList.toggle('is-low', v < b.low);
                refs.row.classList.toggle('is-mid', v >= b.low && v < b.mid);
            });
        }

        function apply(next, nextCtx) {
            var prevStars = pet ? pet.stars : null;
            pet = next;
            if (nextCtx) {
                if (nextCtx.now != null) ctx.now = nextCtx.now;
                if (nextCtx.night != null) ctx.night = nextCtx.night;
            }
            var t = parseLocal(ctx.now);
            clockOffset = isNaN(t) ? 0 : t - Date.now();
            base = { at: Date.now(), bars: pet.bars || {}, rates: pet.rates_per_hour || {} };

            root.dataset.petId = String(pet.id);
            root.dataset.mood = pet.mood || '';
            root.classList.toggle('is-asleep', !!pet.asleep);
            root.classList.toggle('is-critical', pet.mood === 'krytyczny');
            nameText.textContent = pet.name || '';
            if (!nameBtn.disabled) nameBtn.setAttribute('aria-label', 'Zmień imię: ' + (pet.name || ''));
            scene.setAttribute('aria-label', pet.asleep ? (pet.name || 'Pupil') + ' śpi' : 'Pogłaszcz: ' + (pet.name || 'pupila'));
            scene.setAttribute('aria-disabled', pet.can && pet.can.pat ? 'false' : 'true');

            var stars = Math.max(0, parseInt(pet.stars, 10) || 0);
            meta.textContent = (STAGE_LABEL[pet.stage] || '') + ' · ' + daysLabel(pet.age_days) +
                (!mini ? ' · ' + daysLabel(pet.care_days) + ' opieki' : '');
            if (stars > 0) {
                var starEl = el('span', 'pet-card__stars', '★'.repeat(stars));
                starEl.setAttribute('aria-label', stars + ' ' + (stars === 1 ? 'gwiazdka' : stars < 5 ? 'gwiazdki' : 'gwiazdek'));
                meta.appendChild(document.createTextNode(' '));
                meta.appendChild(starEl);
            }
            mood.textContent = (MOOD_LABEL[pet.mood] || '') + (pet.asleep ? ' · śpi' : '');
            mood.className = 'pet-card__mood pet-card__mood--' + (pet.mood || 'szczesliwy');

            barEls.health.row.hidden = !(pet.bars && pet.bars.health < 100);
            tickBars();
            renderActions();
            renderHint();

            if (rig) {
                rig.update({ species: pet.species, stage: pet.stage, stars: stars, mood: pet.mood, asleep: pet.asleep });
                if (prevStars != null && stars > prevStars) {
                    rig.playAction('celebrate');
                    root.classList.remove('is-starred');
                    void root.offsetWidth;
                    root.classList.add('is-starred');
                }
            }
        }

        // --- akcje --------------------------------------------------------------------------

        function runAction(action) {
            if (busy || destroyed || !(pet.can && pet.can[action])) return;
            busy = true;
            renderActions(true);
            var btn = actionsBox.querySelector('[data-card-action="' + action + '"]');
            if (btn) {
                btn.classList.add('is-busy');
                btn.setAttribute('aria-busy', 'true');
            }
            var promise;
            try {
                promise = opts.onAction ? opts.onAction(pet, action, 1) : null;
            } catch (e) {
                promise = Promise.reject(e);
            }
            Promise.resolve(promise).then(function (resp) {
                if (destroyed) return;
                if (resp && resp.ok && rig) rig.playAction(action);
            }, function () { /* błąd obsłużył wołający */ }).then(function () {
                busy = false;
                if (!destroyed) renderActions(true);
            });
        }

        function flushPats() {
            clearTimeout(patTimer);
            patTimer = 0;
            if (!pendingPats || !pet) return;
            var n = pendingPats;
            pendingPats = 0;
            if (!opts.onAction) return;
            try {
                Promise.resolve(opts.onAction(pet, 'pat', n)).catch(function () { /* jw. */ });
            } catch (e) { /* jw. */ }
        }

        function pat() {
            if (destroyed || !(pet.can && pet.can.pat)) return;
            if (rig) rig.playAction('pat');
            if (window.Haptics) window.Haptics.tap();
            if (patHint) patHint.classList.add('is-used');
            pendingPats += 1;
            clearTimeout(patTimer);
            if (pendingPats >= PAT_MAX) flushPats();
            else patTimer = setTimeout(flushPats, PAT_DEBOUNCE_MS);
        }

        // --- zmiana imienia -----------------------------------------------------------------

        function openRename() {
            if (!renameForm || editing) return;
            editing = true;
            renameInput.value = pet.name || '';
            renameError.hidden = true;
            renameError.textContent = '';
            nameWrap.hidden = true;
            renameForm.hidden = false;
            renameInput.focus();
            renameInput.select();
        }

        function closeRename(focusName) {
            if (!renameForm || !editing) return;
            editing = false;
            renameForm.hidden = true;
            nameWrap.hidden = false;
            setRenameDisabled(false);
            if (focusName) nameBtn.focus();
        }

        function setRenameDisabled(on) {
            Array.prototype.forEach.call(renameForm.querySelectorAll('input, button'), function (x) { x.disabled = on; });
        }

        function showRenameError(message) {
            renameError.textContent = message;
            renameError.hidden = false;
            renameInput.setAttribute('aria-invalid', 'true');
            renameInput.focus();
        }

        function submitRename() {
            var name = cleanName(renameInput.value);
            var len = Array.from(name).length;
            renameInput.removeAttribute('aria-invalid');
            if (len < 1 || len > NAME_MAX) {
                showRenameError('Imię ma mieć od 1 do ' + NAME_MAX + ' znaków.');
                return;
            }
            if (name === pet.name) {
                closeRename(true);
                return;
            }
            setRenameDisabled(true);
            var promise;
            try {
                promise = opts.onRename(pet, name);
            } catch (e) {
                promise = Promise.reject(e);
            }
            Promise.resolve(promise).then(function () {
                closeRename(true);
            }, function (err) {
                setRenameDisabled(false);
                if (err && err.error === 'bad_name') showRenameError(err.message || 'Nieprawidłowe imię.');
                else renameInput.focus();
            });
        }

        // --- zdarzenia (delegacja) -----------------------------------------------------------

        root.addEventListener('click', function (e) {
            var target = e.target.closest('[data-card-action]');
            if (target && root.contains(target) && !target.disabled) {
                var action = target.dataset.cardAction;
                if (action === 'rename') openRename();
                else if (action === 'rename-cancel') closeRename(true);
                else if (ACTION_LABEL[action]) runAction(action);
                return;
            }
            if (e.target.closest('.pet-card__scene') === scene) pat();
        });

        scene.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                pat();
            }
        });

        if (renameForm) {
            renameForm.addEventListener('submit', function (e) {
                e.preventDefault();
                submitRename();
            });
            renameInput.addEventListener('keydown', function (e) {
                if (e.key === 'Escape') {
                    e.preventDefault();
                    e.stopPropagation();
                    closeRename(true);
                }
            });
        }

        // --- API karty ----------------------------------------------------------------------

        card.update = function (next, nextCtx) {
            if (destroyed || !next) return card;
            apply(next, nextCtx);
            return card;
        };

        card.destroy = function () {
            if (destroyed) return;
            flushPats();
            destroyed = true;
            live = live.filter(function (c) { return c !== card; });
            stopTickerIfIdle();
            if (rig) rig.destroy();
            if (root.parentNode) root.parentNode.removeChild(root);
        };

        card._tick = function () {
            if (destroyed || !pet) return;
            tickBars();
            tickReasons();
        };
        card._flushPats = flushPats;

        apply(petDict, null);
        container.appendChild(root);
        live.push(card);
        startTicker();
        return card;
    }

    window.PetCard = { render: render };
})();
