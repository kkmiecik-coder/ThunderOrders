/**
 * PetCard — treść panelu pupila w domku (spec v3 §6.2). Pupil jest widoczny w pokoju nad panelem,
 * więc karta nie ma już własnej sceny z rigiem ani pat pat (klik w pupila w pokoju → domek → paczki
 * pat w pets.js); wariant `mini` (stary widget) usunięty.
 *
 * API:
 *   PetCard.render(container, petDict, opts) -> card
 *     opts: { onAction(pet, action, variant) -> Promise<odpowiedź API>,
 *             onPlay(pet, action, variant) -> Promise (animacja w pokoju; do jej końca przyciski nieaktywne),
 *             onRename(pet, name) -> Promise, onAdmit(pet) -> Promise, onStars(pet) (przybyła gwiazdka),
 *             now: 'ISO z api/stan', night: {start, end}, config: state.config }
 *     card.update(petDict[, {now, night, config}]) · card.el · card.focus() · card.destroy()
 *
 * Zachowanie (przeniesione z karty etapu 4 + fix passu B):
 *   - Nakarm / Pobaw się / Umyj rozwijają 3 kafelki wariantów (PetRig.VARIANTS); wybór → onAction →
 *     przy sukcesie onPlay; Obudź gdy śpi; „Zabierz do szpitala” gdy chory (can.admit / reasons.admit);
 *   - powód niedostępności tekstem POD przyciskiem (nie `title` — dotyk go nie pokaże); niedostępny
 *     przycisk ma aria-disabled (nie `disabled`), żeby fokus klawiatury nie uciekał na <body>;
 *     przyciski aktualizowane w miejscu, struktura tylko przy zmianie listy akcji;
 *   - błędy obsługuje wołający (toast/odświeżenie), karta tylko wraca do stanu z danych;
 *   - paski ekstrapolowane co 1 s z rates_per_hour (klamra 0–100);
 *   - liczby w podpowiedziach (noc, kara za obudzenie, czuwanie, szpital) z `config` stanu;
 *   - imię: klik → edycja w miejscu; błąd {error: 'bad_name', message} przy polu, edycja zostaje.
 * Bezpieczeństwo: imiona wyłącznie przez textContent / setAttribute; zero inline onclick —
 * delegacja zdarzeń z data-card-action.
 */
(function () {
    'use strict';

    if (window.PetCard) return;   // guard idempotencji
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
    var ACTION_LABEL = { feed: 'Nakarm', play: 'Pobaw się', wash: 'Umyj', wake: 'Obudź', admit: 'Zabierz do szpitala' };
    // Kolejność i nazwy wariantów jak w backendzie (spec v3 §5); fallback, gdy rig jeszcze ich nie wystawia
    var VARIANTS_FALLBACK = { feed: ['miska', 'jablko', 'ciastko'], play: ['pilka', 'wloczka', 'banki'], wash: ['kapiel', 'prysznic', 'gabka'] };
    var VARIANT_LABEL = {
        miska: 'Miska karmy', jablko: 'Jabłko', ciastko: 'Ciasteczko',
        pilka: 'Piłka', wloczka: 'Kłębek włóczki', banki: 'Bańki',
        kapiel: 'Kąpiel', prysznic: 'Prysznic', gabka: 'Gąbka'
    };

    var ICONS = {
        feed: '<path d="M3 11h18a9 9 0 0 1-18 0z"/><path d="M8.5 7.5c0-1.4 1-1.9 1-3.3M12 7.5c0-1.4 1-1.9 1-3.3M15.5 7.5c0-1.4 1-1.9 1-3.3"/>',
        play: '<circle cx="12" cy="12" r="9"/><path d="M3.6 9.4c5 1.6 11.8 1.6 16.8 0M3.6 14.6c5-1.6 11.8-1.6 16.8 0"/>',
        wash: '<circle cx="8.5" cy="14.5" r="4.5"/><circle cx="16.5" cy="8" r="3"/><circle cx="17.5" cy="16.5" r="2"/>',
        wake: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4"/>',
        admit: '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M12 8v8M8 12h8"/>',
        pencil: '<path d="M4 20h4L19.5 8.5a2.1 2.1 0 0 0-3-3L5 17v3z"/><path d="M14.5 7.5l3 3"/>',
        check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
        close: '<path d="M6 6l12 12M18 6L6 18"/>',
        miska: '<path d="M3 12h18a9 9 0 0 1-18 0z"/><circle cx="9" cy="9.5" r="1.2"/><circle cx="13" cy="8.5" r="1.2"/><circle cx="15.5" cy="10" r="1"/>',
        jablko: '<path d="M12 7.5c-2-1.6-6.2-1.3-7 2.6-.8 4 1.8 10.4 4.6 10.4 1.1 0 1.6-.6 2.4-.6s1.3.6 2.4.6c2.8 0 5.4-6.4 4.6-10.4-.8-3.9-5-4.2-7-2.6z"/><path d="M12 7.5c0-2 .8-3.6 2.8-4.5"/>',
        ciastko: '<circle cx="12" cy="12" r="8.5"/><circle cx="9" cy="9.5" r=".9"/><circle cx="14.5" cy="9" r=".9"/><circle cx="13.5" cy="14.5" r=".9"/><circle cx="8.8" cy="14.5" r=".9"/>',
        pilka: '<circle cx="12" cy="12" r="9"/><path d="M3.6 9.4c5 1.6 11.8 1.6 16.8 0M3.6 14.6c5-1.6 11.8-1.6 16.8 0"/>',
        wloczka: '<circle cx="11" cy="12" r="7.5"/><path d="M4.5 9.5c4 0 9 2.5 12 7M6 16.5c2.5-3.5 6-6 10.4-6.4M8.2 5.2c1 3.5 4.5 9 9.6 10.2"/><path d="M17.5 17.5c1.5 1.3 3 1.6 4 .6"/>',
        banki: '<circle cx="9" cy="14" r="5"/><circle cx="16.5" cy="7.5" r="3"/><circle cx="18.5" cy="15.5" r="2"/><path d="M6.6 12.4a2.6 2.6 0 0 1 2.2-1.6"/>',
        kapiel: '<path d="M3 12h18v1.5a5.5 5.5 0 0 1-5.5 5.5h-7A5.5 5.5 0 0 1 3 13.5z"/><path d="M6 12V6.5a2.2 2.2 0 0 1 4-1.2"/><path d="M7 19l-1 2M17 19l1 2"/>',
        prysznic: '<path d="M5 21V8.5a4.5 4.5 0 0 1 9 0"/><path d="M10.5 9.5h7l-1.2 3h-4.6z"/><path d="M12 15.5v1.5M15 15.5v1.5M13.5 18.5V20"/>',
        gabka: '<rect x="4" y="7" width="16" height="11" rx="3.5"/><circle cx="9" cy="11" r="1"/><circle cx="14" cy="13.5" r="1.2"/><circle cx="16.4" cy="10" r=".8"/><circle cx="8.4" cy="15" r=".8"/>'
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

    function variantsOf(action) {
        var R = window.PetRig;
        return (R && R.VARIANTS && R.VARIANTS[action]) || VARIANTS_FALLBACK[action] || [];
    }

    // Wspólny zegar dla wszystkich kart (ekstrapolacja pasków)
    var live = [];
    var cardSeq = 0;
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

    /** „4× wolniej" z night_factor (0.25); bez configu — bez liczby; bez spowolnienia — nic. */
    function nightSlowdown(config) {
        var f = config && config.night_factor != null ? Number(config.night_factor) : NaN;
        if (f === 0) return 'potrzeby teraz nie rosną';
        if (f > 0 && f < 1) return 'potrzeby rosną teraz ' + Math.round(1 / f) + '× wolniej';
        return f >= 1 ? '' : 'potrzeby rosną teraz wolniej';
    }

    function pointsLabel(n) {
        var n10 = n % 10, n100 = n % 100;
        if (n === 1) return 'punkt';
        if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return 'punkty';
        return 'punktów';
    }

    function render(container, petDict, opts) {
        opts = opts || {};
        var pet = null;
        var ctx = { now: opts.now || null, night: opts.night || null, config: opts.config || null };
        var base = { at: Date.now(), bars: {}, rates: {} };
        var busy = false;
        var destroyed = false;
        var editing = false;
        var expanded = null;         // akcja z rozwiniętymi wariantami
        var actionsKey = '';
        var actionEls = {};          // akcja → {btn, reason}
        var uid = ++cardSeq;

        var root = el('article', 'pet-card');
        root.tabIndex = -1;

        var head = el('div', 'pet-card__head');
        var nameBtn = el('button', 'pet-card__name');
        nameBtn.type = 'button';
        var nameText = el('span', 'pet-card__name-text');
        nameBtn.appendChild(nameText);
        if (opts.onRename) {
            nameBtn.dataset.cardAction = 'rename';
            nameBtn.insertAdjacentHTML('beforeend', svg('pencil', 'pet-card__name-icon'));
        } else {
            nameBtn.disabled = true;
            nameBtn.classList.add('is-static');
        }
        var nameWrap = el('h2', 'pet-card__title');
        nameWrap.id = 'petCard' + uid + '-title';
        nameWrap.appendChild(nameBtn);
        head.appendChild(nameWrap);
        root.setAttribute('aria-labelledby', nameWrap.id);

        var renameForm = null, renameInput = null, renameError = null;
        if (opts.onRename) {
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
        var variantsBox = el('div', 'pet-card__variants');
        variantsBox.id = 'petCard' + uid + '-variants';
        variantsBox.setAttribute('role', 'group');
        variantsBox.hidden = true;
        var hint = el('p', 'pet-card__hint');
        hint.hidden = true;

        root.appendChild(head);
        root.appendChild(barsBox);
        root.appendChild(actionsBox);
        root.appendChild(variantsBox);
        root.appendChild(hint);

        var card = { el: root };

        // --- render -------------------------------------------------------------------------

        function isSick() {
            return !!(pet.reasons && pet.reasons.admit !== 'zdrowy' && pet.can && 'admit' in pet.can);
        }

        function visibleActions() {
            if (pet.asleep) return ['wake'];
            var list = ['feed', 'play', 'wash'];
            // „Zabierz do szpitala" tylko u chorego — u zdrowego byłby wiecznie szary przycisk
            if (isSick()) list.push('admit');
            return list;
        }

        function reasonText(action) {
            var reason = pet.reasons && pet.reasons[action];
            if (!reason || (pet.can && pet.can[action])) return '';
            return capitalize(reason);
        }

        function isAvailable(action) {
            return !busy && !!(pet.can && pet.can[action]);
        }

        function focusCard() {
            try { root.focus({ preventScroll: true }); } catch (e) { root.focus(); }
        }

        /** Struktura przycisków tylko przy zmianie listy akcji; stan (dostępność, powód) w miejscu. */
        function renderActions() {
            var list = visibleActions();
            var key = list.join(',');
            if (key !== actionsKey) {
                var active = document.activeElement;
                var hadFocus = !!(active && (actionsBox.contains(active) || variantsBox.contains(active)));
                var focusedAction = hadFocus ? active.getAttribute('data-card-action') : null;
                actionsKey = key;
                actionEls = {};
                actionsBox.innerHTML = '';
                actionsBox.classList.toggle('is-single', list.length === 1);
                list.forEach(function (action) {
                    var wrap = el('div', 'pet-action pet-action--' + action);
                    var primary = action === 'wake' || action === 'admit';
                    var btn = el('button', 'pet-btn pet-action__btn' + (primary ? ' pet-btn--primary' : ''));
                    btn.type = 'button';
                    btn.dataset.cardAction = action;
                    btn.innerHTML = svg(action) + '<span class="pet-btn__label"></span>';
                    btn.querySelector('.pet-btn__label').textContent = ACTION_LABEL[action];
                    if (VARIANTS_FALLBACK[action]) {
                        btn.setAttribute('aria-expanded', 'false');
                        btn.setAttribute('aria-controls', variantsBox.id);
                    }
                    var reason = el('p', 'pet-action__reason');
                    reason.dataset.reasonFor = action;
                    reason.id = 'petCard' + uid + '-' + action + '-reason';
                    btn.setAttribute('aria-describedby', reason.id);
                    wrap.appendChild(btn);
                    wrap.appendChild(reason);
                    actionsBox.appendChild(wrap);
                    actionEls[action] = { btn: btn, reason: reason };
                });
                if (expanded && !actionEls[expanded]) collapse(false);
                // Fokus był na przebudowanym przycisku — wróć na tę samą akcję, a gdy jej już nie ma
                // (np. „Obudź" po obudzeniu) — na kartę
                if (hadFocus) {
                    if (focusedAction && actionEls[focusedAction]) actionEls[focusedAction].btn.focus();
                    else focusCard();
                }
            }
            list.forEach(function (action) {
                var refs = actionEls[action];
                if (isAvailable(action)) refs.btn.removeAttribute('aria-disabled');
                else refs.btn.setAttribute('aria-disabled', 'true');
                var text = reasonText(action);
                if (refs.reason.textContent !== text) refs.reason.textContent = text;
            });
            if (expanded && !isAvailable(expanded) && !busy) collapse(false);
            Array.prototype.forEach.call(variantsBox.querySelectorAll('[data-variant]'), function (tile) {
                if (busy) tile.setAttribute('aria-disabled', 'true');
                else tile.removeAttribute('aria-disabled');
            });
        }

        function expand(action) {
            if (expanded === action) {
                collapse(true);
                return;
            }
            if (expanded && actionEls[expanded]) actionEls[expanded].btn.setAttribute('aria-expanded', 'false');
            expanded = action;
            variantsBox.innerHTML = '';
            variantsBox.setAttribute('aria-label', ACTION_LABEL[action] + ' — wybierz');
            variantsBox.dataset.action = action;
            variantsOf(action).forEach(function (variant) {
                var tile = el('button', 'pet-variant');
                tile.type = 'button';
                tile.dataset.cardAction = 'variant';
                tile.dataset.variant = variant;
                tile.innerHTML = svg(ICONS[variant] ? variant : action, 'pet-variant__icon') + '<span class="pet-variant__label"></span>';
                tile.querySelector('.pet-variant__label').textContent = VARIANT_LABEL[variant] || variant;
                variantsBox.appendChild(tile);
            });
            variantsBox.hidden = false;
            actionEls[action].btn.setAttribute('aria-expanded', 'true');
            var first = variantsBox.querySelector('.pet-variant');
            if (first) first.focus();
        }

        function collapse(returnFocus) {
            if (!expanded) return;
            var action = expanded;
            expanded = null;
            variantsBox.hidden = true;
            variantsBox.innerHTML = '';
            if (actionEls[action]) {
                actionEls[action].btn.setAttribute('aria-expanded', 'false');
                if (returnFocus) actionEls[action].btn.focus();
            }
        }

        function renderHint() {
            var text = '';
            var cfg = ctx.config || {};
            var penalty = parseInt(cfg.wake_penalty, 10);
            var awake = parseInt(cfg.awake_minutes, 10);
            var hours = parseInt(cfg.hospital_hours, 10);
            if (pet.asleep) {
                var slower = nightSlowdown(ctx.config);
                text = 'Śpi' + (ctx.night ? ' do ' + ctx.night.end + ':00' : '') + (slower ? ' — ' + slower : '') + '. ' +
                    (penalty > 0
                        ? 'Obudzenie kosztuje ' + penalty + ' ' + pointsLabel(penalty) + ' radości i czystości'
                        : 'Obudzenie obniża radość i czystość') +
                    (awake > 0 ? ', a pupil czuwa potem ' + awake + ' min.' : '.');
            } else if (isSick()) {
                text = 'Pupil ' + (pet.name || '') + ' jest chory — opieka w domku go nie wyleczy. W szpitalu wyzdrowieje' +
                    (hours > 0 ? ' w najwyżej ' + hours + ' h' : '') + ', a jego potrzeby nie będą tam rosły.';
            } else if (pet.awake_until) {
                text = 'Obudzony do ' + hhmm(pet.awake_until) + ' — każda opieka przedłuża czuwanie' +
                    (awake > 0 ? ' o ' + awake + ' min' : '') + '.';
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
                if (nextCtx.night !== undefined) ctx.night = nextCtx.night;
                if (nextCtx.config != null) ctx.config = nextCtx.config;
            }
            base = { at: Date.now(), bars: pet.bars || {}, rates: pet.rates_per_hour || {} };

            root.dataset.petId = String(pet.id);
            root.dataset.mood = pet.mood || '';
            root.classList.toggle('is-asleep', !!pet.asleep);
            root.classList.toggle('is-critical', pet.mood === 'krytyczny');
            nameText.textContent = pet.name || '';
            if (!nameBtn.disabled) nameBtn.setAttribute('aria-label', 'Zmień imię: ' + (pet.name || ''));

            var stars = Math.max(0, parseInt(pet.stars, 10) || 0);
            meta.textContent = (STAGE_LABEL[pet.stage] || '') + ' · ' + daysLabel(pet.age_days) + ' · ' +
                daysLabel(pet.care_days) + ' opieki';
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

            if (prevStars != null && stars > prevStars) {
                root.classList.remove('is-starred');
                void root.offsetWidth;
                root.classList.add('is-starred');
                if (typeof opts.onStars === 'function') opts.onStars(pet);
            }
        }

        // --- akcje --------------------------------------------------------------------------

        function runAction(action, variant) {
            if (busy || destroyed || !(pet.can && pet.can[action])) return;
            busy = true;
            var btn = actionEls[action] && actionEls[action].btn;
            if (btn) {
                btn.classList.add('is-busy');
                btn.setAttribute('aria-busy', 'true');
            }
            renderActions();
            var current = pet;
            var promise;
            try {
                if (action === 'admit') promise = opts.onAdmit ? opts.onAdmit(current) : null;
                else promise = opts.onAction ? opts.onAction(current, action, variant || null) : null;
            } catch (e) {
                promise = Promise.reject(e);
            }
            Promise.resolve(promise).then(function (resp) {
                if (destroyed || action === 'admit') return null;
                if (resp && resp.ok && typeof opts.onPlay === 'function') return opts.onPlay(current, action, variant || null);
                return null;
            }).then(null, function () { /* błąd obsłużył wołający */ }).then(function () {
                busy = false;
                if (destroyed) return;
                var b = actionEls[action] && actionEls[action].btn;
                if (b) {
                    b.classList.remove('is-busy');
                    b.removeAttribute('aria-busy');
                }
                renderActions();
            });
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
            if (!target || !root.contains(target) || target.disabled || target.getAttribute('aria-disabled') === 'true') return;
            var action = target.dataset.cardAction;
            if (action === 'rename') openRename();
            else if (action === 'rename-cancel') closeRename(true);
            else if (action === 'variant') {
                var parent = expanded;
                collapse(false);
                if (parent && actionEls[parent]) actionEls[parent].btn.focus();
                runAction(parent, target.dataset.variant);
            } else if (VARIANTS_FALLBACK[action]) expand(action);
            else if (ACTION_LABEL[action]) runAction(action);
        });

        root.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && expanded) {
                e.preventDefault();
                e.stopPropagation();
                collapse(true);
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

        card.focus = function () {
            if (!destroyed) focusCard();
            return card;
        };

        card.destroy = function () {
            if (destroyed) return;
            destroyed = true;
            live = live.filter(function (c) { return c !== card; });
            stopTickerIfIdle();
            if (root.parentNode) root.parentNode.removeChild(root);
        };

        card._tick = function () {
            if (destroyed || !pet) return;
            tickBars();
        };

        apply(petDict, null);
        container.appendChild(root);
        live.push(card);
        startTicker();
        return card;
    }

    window.PetCard = { render: render };
})();
