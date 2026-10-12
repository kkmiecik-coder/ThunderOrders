/**
 * Admin — Pupile: wyszukiwarka użytkowników + „Przyznaj jajko" (spec §5).
 * Wyniki budowane przez DOM API (textContent) — zero innerHTML z danymi użytkownika.
 * window.showToast wstawia HTML — każdy komunikat (także z serwera) idzie przez escapeHtml.
 */
(function () {
    'use strict';

    var root = document.getElementById('petsAdmin');
    var input = document.getElementById('paSearchInput');
    var results = document.getElementById('paSearchResults');
    if (!root || !input || !results) return;

    var searchUrl = root.dataset.searchUrl;
    var grantUrl = root.dataset.grantUrl;
    var csrfMeta = document.querySelector('meta[name="csrf-token"]');
    var timer = null;
    var seq = 0;

    var GRANT_ERROR = 'Nie udało się przyznać jajka';

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function toast(msg, type) {
        if (typeof window.showToast === 'function') window.showToast(escapeHtml(msg), type || 'info');
    }

    /** Odpowiedź → {ok, data}; nie-JSON (302 na login, 500/429 HTML) to data = null, nie SyntaxError. */
    function readJson(r) {
        var type = r.headers.get('Content-Type') || '';
        if (type.indexOf('application/json') === -1) return Promise.resolve({ ok: false, status: r.status, data: null });
        return r.json().then(function (d) { return { ok: r.ok, status: r.status, data: d }; },
            function () { return { ok: false, status: r.status, data: null }; });
    }

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text != null) n.textContent = text;
        return n;
    }

    var MOOD = { szczesliwy: 'szczęśliwy', glodny: 'głodny', znudzony: 'znudzony', brudny: 'brudny',
                 smutny: 'smutny', chory: 'chory', krytyczny: 'krytyczny' };
    var STAGE = { maluch: 'maluch', dziecko: 'dziecko', dorosly: 'dorosły' };

    function render(users) {
        results.textContent = '';
        if (!users.length) {
            results.appendChild(el('p', 'pa-results__empty', 'Brak wyników.'));
            return;
        }
        users.forEach(function (u) {
            var card = el('article', 'pa-user');
            var info = el('div');
            info.appendChild(el('div', 'pa-user__name', u.name || u.email));
            info.appendChild(el('div', 'pa-user__email', u.email));
            card.appendChild(info);

            var btn = el('button', 'pa-user__grant', 'Przyznaj jajko' + (u.granted_pending ? ' (' + u.granted_pending + ' czeka)' : ''));
            btn.type = 'button';
            btn.dataset.userId = u.id;
            if (!u.has_profile) {
                btn.disabled = true;
                btn.title = 'Użytkownik nie odebrał jeszcze startowego jajka';
            }
            card.appendChild(btn);

            var pets = el('div', 'pa-user__pets');
            if (!u.has_profile) {
                pets.appendChild(el('span', 'pa-pill pa-pill--warn', 'bez profilu (startowe nieodebrane)'));
            } else if (!u.pets.length && !u.eggs) {
                pets.appendChild(el('span', 'pa-pill', 'brak pupili'));
            }
            u.pets.forEach(function (p) {
                var cls = 'pa-pill' + (p.mood === 'krytyczny' || p.mood === 'chory' ? ' pa-pill--bad' : (p.mood !== 'szczesliwy' ? ' pa-pill--warn' : ''));
                pets.appendChild(el('span', cls, p.name + ' · ' + p.species_name + ' · ' + (STAGE[p.stage] || p.stage) + ' · ' + (MOOD[p.mood] || p.mood) + (p.asleep ? ' · śpi' : '')));
            });
            if (u.eggs) pets.appendChild(el('span', 'pa-pill', 'jajka w inkubacji: ' + u.eggs));
            if (u.eggs_available && u.eggs_available.length) pets.appendChild(el('span', 'pa-pill', 'do odebrania: ' + u.eggs_available.join(', ')));
            card.appendChild(pets);
            results.appendChild(card);
        });
    }

    function search() {
        var q = input.value.trim();
        if (q.length < 2) { results.textContent = ''; return; }
        var my = ++seq;
        fetch(searchUrl + '?q=' + encodeURIComponent(q), { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
            .then(function (users) { if (my === seq) render(users); })
            .catch(function () { if (my === seq) toast('Nie udało się wyszukać użytkowników', 'error'); });
    }

    input.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(search, 300);
    });

    results.addEventListener('click', function (ev) {
        var btn = ev.target.closest('.pa-user__grant');
        if (!btn || btn.disabled) return;
        btn.disabled = true;
        fetch(grantUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json',
                       'X-CSRFToken': csrfMeta ? csrfMeta.getAttribute('content') : '' },
            body: JSON.stringify({ user_id: parseInt(btn.dataset.userId, 10) })
        })
            .then(readJson, function () { return { ok: false, status: 0, data: null, network: true }; })
            .then(function (res) {
                if (!res.ok || !res.data || !res.data.ok) {
                    var msg = (res.data && typeof res.data.message === 'string' && res.data.message) ||
                        (res.network ? 'Brak połączenia — spróbuj za chwilę' :
                            res.status === 429 ? 'Za dużo żądań — odczekaj chwilę' : GRANT_ERROR);
                    toast(msg, 'error');
                    return;
                }
                btn.textContent = 'Przyznaj jajko (' + res.data.granted_pending + ' czeka)';
                toast('Jajko przyznane — użytkownik zobaczy je w gniazdku', 'success');
            })
            .catch(function () { toast(GRANT_ERROR, 'error'); })
            .then(function () { btn.disabled = false; });
    });
})();

// Formularze z data-confirm (usuwanie obrazka wychylania): potwierdzenie bez inline JS
(function () {
    'use strict';
    document.addEventListener('submit', function (e) {
        var form = e.target;
        var msg = form && form.getAttribute && form.getAttribute('data-confirm');
        if (msg && !window.confirm(msg)) e.preventDefault();
    });
})();
