/**
 * Świat pupili — wspólne klocki szpitala (spec v3.1 §4, §7). Używają ich trzy sceny:
 *   hol z recepcją (hospital-hall.js, klucz `szpital`), Inkubatorium (hospital-incubator.js, `inkubatorium`)
 *   i Izba przyjęć (hospital-ward.js, `izba`).
 *
 * window.PetsHospital:
 *   - teksty i formaty: eggTitle, claimTitle, claimText, claimLabel, claimKey, eggsToClaimCount, eggStatus,
 *     healPct, healStatus, petName;
 *   - wybór z JSON-u stanu: inBed, sickAtHome, readyEggs, healedPets;
 *   - wysyłka akcji (teksty toastów i obsługa błędów jak w dawnym hospital.js — błędy pokazuje ctx.send):
 *     claim, warm, hatch (PetHatch), admit, discharge;
 *   - widoki: progress (pasek postępu), focus, syncSlots (stałe miejsca obiektów w sali), reveal (wybrany
 *     obiekt nad arkuszem okna sceny < 1024 px).
 * Bezpieczeństwo: imiona wyłącznie przez textContent (sceny); ten plik nie wstawia HTML-a z danymi.
 */
(function () {
    'use strict';

    if (window.PetsHospital) return;

    var EGG_SOURCE = {
        start: 'Jajko startowe', monthly: 'Jajko miesięczne', rescue: 'Jajko ratunkowe', granted: 'Jajko w prezencie'
    };
    var SICK = ['chory', 'krytyczny'];

    function eggTitle(source) {
        return EGG_SOURCE[source] || 'Jajko';
    }

    // --- jajka do odebrania (recepcja) --------------------------------------------------------

    function grantedCount(item) {
        return Math.max(1, parseInt(item.count, 10) || 1);
    }

    /** Klucz pozycji listy `eggs_available` (jedno jajko na ladzie na pozycję). */
    function claimKey(item) {
        return item.source + (item.pet_id != null ? ':' + item.pet_id : '');
    }

    function claimTitle(item) {
        if (item.source === 'granted' && grantedCount(item) > 1) return 'Jajka w prezencie';
        return eggTitle(item.source);
    }

    /** Opis źródła — teksty jak w dawnej inkubatorni (spec v3.1 §4.2). */
    function claimText(item, u) {
        if (item.source === 'start') return 'Twoje pierwsze jajko! Odbierz je i ogrzewaj przy każdej wizycie — tak wykluje się szybciej.';
        if (item.source === 'monthly') return 'Nowe jajko czeka na odbiór. Odliczanie do kolejnego ruszy po odebraniu.';
        if (item.source === 'rescue') {
            return item.pet_name
                ? 'Pupil ' + item.pet_name + ' odszedł do gwiazd. To jajko czeka na Ciebie.'
                : 'Twój pupil odszedł do gwiazd. To jajko czeka na Ciebie.';
        }
        if (item.source === 'granted') {
            var n = grantedCount(item);
            return n === 1 ? 'Czeka na Ciebie jajko w prezencie.'
                : 'Czeka na Ciebie ' + n + ' ' + u.plural(n, 'jajko', 'jajka', 'jajek') + ' w prezencie.';
        }
        return 'Jajko czeka na odbiór.';
    }

    /** aria-label jajka na ladzie. */
    function claimLabel(item) {
        if (item.source === 'rescue') {
            return 'Jajko ratunkowe' + (item.pet_name ? ' po pupilu ' + item.pet_name : '') + ' — do odebrania';
        }
        if (item.source === 'granted' && grantedCount(item) > 1) return 'Jajka w prezencie (' + grantedCount(item) + ') — do odebrania';
        return eggTitle(item.source) + ' — do odebrania';
    }

    /** Ile jajek czeka na recepcji (prezent z licznikiem liczy się po sztukach). */
    function eggsToClaimCount(state) {
        return ((state && state.eggs_available) || []).reduce(function (sum, item) {
            return sum + (item.source === 'granted' ? grantedCount(item) : 1);
        }, 0);
    }

    // --- jajka w inkubacji ----------------------------------------------------------------------

    /**
     * Postęp i czas do wyklucia w tej chwili (prognoza z ogrzaniem — pets-core.js eggForecast) →
     * {pct, ready, boosted, eta: '~4 dni' | '~3 h' | 'za chwilę' | '', heat, plate}.
     * Formaty jak dawniej: do 48 h w godzinach, dalej w dniach.
     */
    function eggStatus(egg, state, u) {
        var Store = window.PetsState;
        var f = Store && typeof Store.eggForecast === 'function'
            ? Store.eggForecast(egg, state, Store.elapsedSec())
            : { pct: Number(egg.progress_pct) || 0, leftSec: NaN, boosted: !!egg.boost_until };
        var ready = !!egg.ready;
        var pct = ready ? 100 : Math.round(Math.max(0, Math.min(100, f.pct)));
        var eta = '';
        if (!ready && f.leftSec >= 0) {
            eta = f.leftSec < 60 ? 'za chwilę'
                : f.leftSec >= 48 * 3600 ? '~' + u.daysText(Math.round(f.leftSec / 86400))
                : u.roughDuration(f.leftSec);
        }
        var heat = '';
        if (!ready && f.boosted) {
            var left = u.secondsUntil(egg.boost_until);
            var factor = Store && Store.boostFactor ? Store.boostFactor(state) : 2;
            heat = 'Ciepło (tempo ×' + String(factor).replace('.', ',') + ') jeszcze ' + u.formatDuration(left > 0 ? left : 0) + '.';
        }
        return {
            pct: pct,
            ready: ready,
            boosted: !ready && !!f.boosted,
            eta: eta,
            heat: heat,
            plate: ready ? 'Gotowe! Wykluj' : pct + '%' + (eta ? ' · ' + eta : '')
        };
    }

    // --- pupile w szpitalu ----------------------------------------------------------------------

    function petName(pet, u) {
        return (pet && pet.name) || (pet ? u.speciesName(pet.species) : '');
    }

    function healPct(h, u) {
        if (h.ready) return 100;
        var since = u.parseLocal(h.since), healed = u.parseLocal(h.healed_at);
        if (isNaN(since) || isNaN(healed) || healed <= since) return Number(h.progress_pct) || 0;
        return Math.max(0, Math.min(100, (u.serverNow() - since) / (healed - since) * 100));
    }

    /**
     * Stan leczenia w tej chwili → {pct, ready, left: '~3 h' | '~40 min' | 'chwilę', status, note}.
     * Teksty jak w dawnej sali chorych.
     */
    function healStatus(pet, u) {
        var h = pet.hospital;
        var pct = healPct(h, u);
        if (h.ready) {
            var auto = u.secondsUntil(h.auto_discharge_at);
            return {
                pct: 100, ready: true, left: '',
                status: 'Gotowy do odbioru!',
                note: 'Tęskni za domem — z każdą godziną czekania jest smutniejszy.' +
                    (auto > 0 ? ' Sam wróci za ' + u.roughDuration(auto) + '.' : '')
            };
        }
        var left = u.roughDuration(u.secondsUntil(h.healed_at));
        return {
            pct: pct, ready: false, left: left,
            status: 'Wraca do zdrowia — jeszcze ' + left + ' do wyzdrowienia',
            note: 'Leży pod kołderką. W szpitalu jego potrzeby nie rosną.'
        };
    }

    // --- wybór z JSON-u stanu -----------------------------------------------------------------------

    function inBed(state) {
        return ((state && state.pets) || []).filter(function (p) { return p.hospital; });
    }

    function sickAtHome(state) {
        return ((state && state.pets) || []).filter(function (p) { return !p.hospital && SICK.indexOf(p.mood) >= 0; });
    }

    function readyEggs(state) {
        return ((state && state.eggs) || []).filter(function (e) { return e.ready; });
    }

    function healedPets(state) {
        return inBed(state).filter(function (p) { return p.hospital.ready; });
    }

    // --- akcje (ctx.send: kolejność stanu, toasty błędów, 409 = ciche odświeżenie) -------------------

    function claim(ctx, item) {
        var body = { source: item.source };
        if (item.pet_id != null) body.pet_id = item.pet_id;
        return ctx.send('/jajka/odbierz', body).then(function (resp) {
            if (body.source === 'start') {
                // Pierwsze jajko = najlepszy moment na prośbę o pushe (push-banner.js sam sprawdza subskrypcję)
                try { window.dispatchEvent(new Event('push-force-banner')); } catch (err) { /* stare przeglądarki */ }
            }
            ctx.u.toast('Jajko odebrane! Ogrzewaj je przy każdej wizycie, a szybciej się wykluje.', 'success');
            return resp;
        });
    }

    function warm(ctx, eggId) {
        return ctx.send('/jajka/' + eggId + '/ogrzej', {}).then(function (resp) {
            if (window.Haptics) window.Haptics.tap();
            return resp;
        });
    }

    /**
     * Wyklucie: nakładka PetHatch (animacja + imię). Promise → wynik PetHatch.run (result, pet_id,
     * starred_pet_id…); odrzucenie = błąd pokazany już przez ctx.send albo brak nakładki (toast).
     * Odznaki pokazujemy po zamknięciu nakładki (jak dotąd).
     */
    function hatch(ctx, egg) {
        var u = ctx.u;
        if (!window.PetHatch || typeof window.PetHatch.run !== 'function') {
            u.toast('Nie udało się otworzyć wyklucia — odśwież stronę.', 'error');
            return Promise.reject({ error: 'no_hatch' });
        }
        var petId = null;
        return window.PetHatch.run({
            skin: egg.skin || 0,
            // Gwiazdki sprzed duplikatu — odpowiedź API ma już stan po wykluciu
            prevPets: ((ctx.state() || {}).pets || []).slice(),
            hatch: function () {
                return ctx.send('/jajka/' + egg.id + '/wykluj', {}, { deferAchievements: true }).then(function (resp) {
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
            if (res && res.new_achievements && res.new_achievements.length) ctx.showAchievements();
            return res;
        });
    }

    function admit(ctx, pet) {
        return ctx.send('/' + pet.id + '/szpital', {}).then(function (resp) {
            ctx.u.toast('Pupil ' + (pet.name || '') + ' leży już w łóżku. Wróci zdrowy!', 'success');
            return resp;
        });
    }

    function discharge(ctx, pet) {
        return ctx.send('/' + pet.id + '/wypis', {}).then(function (resp) {
            ctx.u.toast('Pupil ' + (pet.name || '') + ' wrócił do domku!', 'success');
            return resp;
        });
    }

    // --- widoki ----------------------------------------------------------------------------------------

    /** Pasek postępu (styl .pets-progress z pets.css); `set(pct)` przestawia szerokość i aria-valuenow. */
    function progress(u, label, heal) {
        var track = u.el('div', 'pets-progress' + (heal ? ' pets-progress--heal' : ''));
        track.setAttribute('role', 'progressbar');
        track.setAttribute('aria-valuemin', '0');
        track.setAttribute('aria-valuemax', '100');
        track.setAttribute('aria-label', label);
        var fill = u.el('div', 'pets-progress__fill');
        track.appendChild(fill);
        return {
            el: track,
            set: function (pct) {
                var w = Math.max(0, Math.min(100, pct)).toFixed(1) + '%';
                if (fill.style.width !== w) fill.style.width = w;
                var now = String(Math.round(pct));
                if (track.getAttribute('aria-valuenow') !== now) track.setAttribute('aria-valuenow', now);
            }
        };
    }

    function focus(node) {
        if (!node || typeof node.focus !== 'function') return;
        try { node.focus({ preventScroll: true }); } catch (e) { node.focus(); }
    }

    /**
     * Stałe miejsca obiektów w sali (spec v3.1 §4.3–4.4: max(min, n) miejsc): obiekt zostaje w swoim
     * inkubatorze/łóżku, gdy inne znikają; nowy trafia w preferowane wolne miejsce (`prefer[id]`, np. łóżko,
     * z którego przyjęto pupila), inaczej w pierwsze wolne. Zwraca nową tablicę id/null.
     */
    function syncSlots(slots, ids, min, prefer) {
        var out = slots.map(function (id) { return id != null && ids.indexOf(id) >= 0 ? id : null; });
        ids.forEach(function (id) {
            if (out.indexOf(id) >= 0) return;
            var p = prefer ? prefer[id] : null;
            if (p != null && p >= 0 && p < out.length && out[p] == null) { out[p] = id; return; }
            var free = out.indexOf(null);
            if (free >= 0) out[free] = id;
            else out.push(id);
        });
        var n = Math.max(min, ids.length);
        while (out.length > n && out[out.length - 1] == null) out.pop();
        if (out.length > n) {
            // Za dużo wolnych w środku (np. kilku odebranych naraz) — zajęte przesuwają się do przodu
            out = out.filter(function (id) { return id != null; });
        }
        while (out.length < n) out.push(null);
        return out;
    }

    /**
     * Arkusz okna sceny (< 1024 px): wybrany obiekt ma zostać widoczny nad arkuszem — przewija wnętrze
     * sceny (`scroller`). Wysokość arkusza z --window-h (scene-window.js).
     */
    function reveal(host, scroller, node) {
        if (!node || !scroller) return;
        var sheet = parseFloat(host.style.getPropertyValue('--window-h')) || 0;
        var box = host.getBoundingClientRect();
        var r = node.getBoundingClientRect();
        var limit = box.bottom - sheet - 12;
        if (r.bottom > limit) scroller.scrollTop += r.bottom - limit;
        // Nie pod pigułką (u góry sceny), jeśli po przewinięciu w dół obiekt nadal mieści się nad arkuszem
        var top = box.top + 72;
        r = node.getBoundingClientRect();
        if (r.top < top && r.bottom + (top - r.top) <= limit) scroller.scrollTop -= top - r.top;
    }

    window.PetsHospital = {
        EGG_SOURCE: EGG_SOURCE,
        SICK: SICK,
        eggTitle: eggTitle,
        claimKey: claimKey,
        claimTitle: claimTitle,
        claimText: claimText,
        claimLabel: claimLabel,
        grantedCount: grantedCount,
        eggsToClaimCount: eggsToClaimCount,
        eggStatus: eggStatus,
        petName: petName,
        healPct: healPct,
        healStatus: healStatus,
        inBed: inBed,
        sickAtHome: sickAtHome,
        readyEggs: readyEggs,
        healedPets: healedPets,
        claim: claim,
        warm: warm,
        hatch: hatch,
        admit: admit,
        discharge: discharge,
        progress: progress,
        focus: focus,
        syncSlots: syncSlots,
        reveal: reveal
    };
})();
