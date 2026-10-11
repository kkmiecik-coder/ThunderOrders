# Pupile — etap 5: widget na dashboardzie i towarzysz na stronach — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pupil wychodzi poza stronę domku — mini-karta na dashboardzie klienta z szybkimi akcjami oraz towarzysz spacerujący po panelu klienta (siedzący w rogu na stronach ofert), z kropką „potrzebuje opieki" w nawigacji i pamięcią stanu w `localStorage`.

**Architecture:** Zero nowych zapytań po stronie SSR dla towarzysza — o jego widoczności decyduje JS ze stanu `api/stan?lite=1` trzymanego w `localStorage` (klucz z `user_id`, TTL 5 min, unieważniany po każdej akcji). Dashboard dostaje pełny stan z `service.state_for_user` w kontekście szablonu (jedno wywołanie) i renderuje mini-kartę tym samym `PetCard` co domek. Wspólna warstwa `PetsApi`/`PetsState` z etapu 4 zostaje wyniesiona z `pets.js` do `static/js/pet/pets-core.js`, żeby dashboard i towarzysz nie ładowały całej strony domku.

**Tech Stack:** Flask 3 + Jinja2 (context processor `pets_enabled` z etapu 4), vanilla JS (IIFE, ES5-kompatybilne jak reszta `static/js/components/`), CSS light+dark, `window.PetRig`/`window.PetSpecies` (etap 4 B), `window.PetCard`/`window.PetsApi`/`window.PetsState`/`window.Haptics` (etap 4 C), pytest przez `venv/bin/python -m pytest`.

**Spec:** `docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md` — §4.3 (widget), §4.4 (towarzysz), §4.6 (nawigacja), §4.1 (pliki), §9 pkt 5. Plan etapu 4 (kontrakty `PetCard`/`PetsApi`/`PetsState`/`PetRig`): `docs/superpowers/plans/2026-10-11-pupile-etap-4-domek.md`.

## Global Constraints

- Każdy styl: light + `[data-theme="dark"]` (paleta: tła `rgba(255,255,255,0.05–0.1)`, obramowania `rgba(240,147,251,0.15–0.3)`, akcenty `#f093fb`/`#f5576c`). Zero CSS/JS inline poza `data-*` i wartościami dynamicznymi.
- Elementy dotykowe ≥ 44 px (towarzysz, przyciski szybkich akcji, link w dymku).
- Widget i towarzysz renderują się **tylko** gdy `pets_enabled` (context processor = `pets_feature_for(current_user)`), inaczej link/stan prowadziłby do 404.
- Towarzysz: SSR nie dokłada zapytań; stan z `api/stan?lite=1`; cache `localStorage` klucz `pets_state_v1_<user_id>`, TTL 5 min, unieważnienie po każdej akcji (także z domku i widgetu).
- Strony ofert: fetch stanu odroczony (`window.addEventListener('load')` + 4 s + `requestIdleCallback` z fallbackiem `setTimeout`), towarzysz siedzi w prawym dolnym rogu, nie spaceruje.
- `prefers-reduced-motion`: statyczna poza, bez spaceru, bez wibracji (rig sam wyłącza animacje; towarzysz nie zmienia `transform`).
- Noc (`state.night.is_night` lub `pet.asleep`): towarzysz śpi (`asleep: true` w rigu), klik nie robi pat (409 `asleep` i tak by wrócił), dymek „Śpi… zzz".
- Kolejność nakładek: towarzysz **nad** dolnym paskiem PWA (`z-index: 1000–1002`) i koszykiem (1090–1100), **pod** banerami PWA/push (9998–9999), modalami (10000+) i toastami (10002) → `z-index: 1200`. Na telefonie `bottom: calc(60px + env(safe-area-inset-bottom, 0px) + 8px)` gdy pasek PWA jest widoczny (klasa `body.pwa-mode`? — sprawdź w `static/css/components/bottom-bar.css` media query, w którym pasek się pojawia, i użyj tego samego warunku).
- `static/sw.js`: bump `CACHE_VERSION` o 1 względem wartości zastanej po etapie 4 (C podbiła do `thunderorders-v27` → tu `v28`).
- Repo publiczne: żadnych danych infrastruktury w commitach. Nie pushować (push = auto-deploy).

## Review Focus

1. **Dwóch użytkowników na jednej przeglądarce** (wylogowanie → logowanie na inne konto): cache `localStorage` bez `user_id` w kluczu pokazałby cudzego pupila. Oczekiwanie: klucz zawiera `user_id` z `data-user-id` elementu towarzysza; stan z innego klucza nigdy nie jest czytany. Test (Task 4, w przeglądarce): zaloguj dwóch użytkowników po kolei w podglądzie, sprawdź `Object.keys(localStorage)`.
2. **Pupil odszedł między odczytami** (cache ma go żywego, serwer już nie): klik pat → 410 `pet_gone`. Oczekiwanie: towarzysz znika, cache unieważniony, brak toastu błędu w pętli. Test (Task 3 w przeglądarce + Task 1 pytest: `lite` zwraca krytycznego bez zapisu — już pokryte w `test_lite_nie_zapisuje_odejscia_pelny_zapisuje`).
3. **Live drop na stronie oferty**: fetch towarzysza nie może wystartować przed `load` + 4 s. Oczekiwanie: w `read_network_requests` `api/stan?lite=1` pojawia się po żądaniach strony oferty. Test (Task 3 w przeglądarce na `/offer/<token>` z seeda).
4. **Dashboard bez żywego pupila**: użytkownik ma tylko jajko (albo nic). Oczekiwanie: widget pokazuje jajko (postęp/„Wykluj") albo zachętę „Odbierz swoje pierwsze jajko" — nigdy pustą kartę ani błąd JS. Test (Task 1 pytest: `pets_widget` dla użytkownika bez profilu ma `eggs_available == [{'source': 'start'}]`; Task 2 w przeglądarce).
5. **Pasek PWA na telefonie zasłania towarzysza** albo towarzysz zasłania przycisk „Złóż zamówienie" na stronie oferty. Oczekiwanie: na 375 px towarzysz stoi nad paskiem, na stronie oferty ma `pointer-events` tylko na własnym elemencie i nie nachodzi na sticky CTA (sprawdź `order_page.html` — sticky stopka koszyka; w razie kolizji towarzysz przesuwa się w górę o wysokość stopki przez zmienną `--pet-companion-offset`). Test (Task 4 zrzuty 375 px: dashboard, lista zamówień, strona oferty).

---

### Task 1 (centrala, TDD): backend — `most_in_need_pet_id`, kontekst widgetu, include towarzysza, `data-pet-celebrate`

**Files:**
- Modify: `modules/pets/state.py` (pole `most_in_need_pet_id` w stanie)
- Modify: `modules/client/routes.py:94-145` (`pets_widget` w kontekście dashboardu)
- Create: `templates/client/pets/_widget.html` (szkielet: kontener z `data-state`; treść renderuje JS w Task 2)
- Create: `templates/components/pet_companion.html`
- Modify: `templates/client/base_client.html` (include towarzysza w `body_content` + przeniesienie `pet-companion.css` z `extra_css` do `body_content`), `templates/offers/base_offers.html` (include w bloku `scripts` przed `extra_js`), `templates/client/dashboard.html` (include widgetu pod `_contest_widget.html` + skrypty); strony podziękowania NIE są modyfikowane — celebrację włącza nazwa endpointu (Step 6)
- Test: `tests/test_pets_widget_companion.py`

**Interfaces:**
- Consumes: `service.state_for_user(user)` (etap 2/4), `pets_feature_for` (etap 1), context processor `pets_enabled` (etap 4 A), fixture `strona_sprzedazy` z `tests/conftest.py` (strona oferty `id=1`, token, status `active`).
- Produces: `state['most_in_need_pet_id']` (int | None); zmienna szablonu `pets_widget` (dict stanu | None); `#petsWidget[data-state][data-api]`; `#petCompanion[data-user-id][data-api][data-mode="walk"|"sit"][data-celebrate="0|1"]`; `#petCompanionBubble`; klasa `pet-companion` z CSS w `pet-companion.css`.

- [ ] **Step 1: Testy (RED)** — `tests/test_pets_widget_companion.py`:

```python
"""Etap 5: widget na dashboardzie i towarzysz — kontekst SSR, gating flagą, data-pet-celebrate."""
import json

from tests.pets_helpers import zaloz_profil, zaloz_pupila, zaloz_jajko
from tests.test_pets_routes import _wlacz


def _stan_widgetu(html):
    import re
    m = re.search(r'id="petsWidget"[^>]*data-state=\'([^\']*)\'', html)
    assert m, 'brak #petsWidget z data-state'
    from html import unescape
    return json.loads(unescape(m.group(1)))


def test_most_in_need_pet_id_w_stanie(db, make_user):
    from modules.pets.service import state_for_user
    user = make_user()
    zaloz_profil(user)
    szczesliwy = zaloz_pupila(user, species='kotek')
    glodny = zaloz_pupila(user, species='mis', name='Głodek', hunger=20.0)
    _wlacz(db)
    stan = state_for_user(user)
    assert stan['most_in_need_pet_id'] == glodny.id and glodny.id != szczesliwy.id


def test_most_in_need_none_bez_zywych(db, make_user):
    from modules.pets.service import state_for_user
    user = make_user()
    _wlacz(db)
    assert state_for_user(user)['most_in_need_pet_id'] is None


def test_dashboard_widget_tylko_z_flaga(client, login, make_user, db):
    user = make_user(profile_completed=True)
    login(user)
    r = client.get('/client/dashboard')
    assert r.status_code == 200 and b'id="petsWidget"' not in r.data and b'id="petCompanion"' not in r.data
    _wlacz(db)
    r = client.get('/client/dashboard')
    html = r.data.decode()
    assert r.status_code == 200 and 'id="petsWidget"' in html and 'id="petCompanion"' in html
    stan = _stan_widgetu(html)
    assert stan['eggs_available'] == [{'source': 'start'}] and stan['pets'] == [] and stan['most_in_need_pet_id'] is None
    assert 'js/pet/pets-core.js' in html and 'js/components/pet-card.js' in html and 'js/pages/client/pets-widget.js' in html
    assert 'data-mode="walk"' in html and 'data-user-id="%d"' % user.id in html


def test_dashboard_widget_z_pupilem(client, login, make_user, db):
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    pet = zaloz_pupila(user, species='kroliczek', name='Puszek', fun=10.0)
    html = client.get('/client/dashboard').data.decode()
    stan = _stan_widgetu(html)
    assert stan['most_in_need_pet_id'] == pet.id and stan['pets'][0]['name'] == 'Puszek'


def test_towarzysz_na_stronie_oferty_siedzi_i_tylko_zalogowany(client, login, make_user, db, strona_sprzedazy):
    strona = strona_sprzedazy
    r = client.get(f'/offer/{strona.token}/thank-you')
    assert b'id="petCompanion"' not in r.data            # gość: nic
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    html = client.get(f'/offer/{strona.token}/thank-you').data.decode()
    assert 'id="petCompanion"' in html and 'data-mode="sit"' in html and 'data-celebrate="1"' in html
    assert 'js/pet/pets-core.js' in html and 'js/components/pet-companion.js' in html


def test_towarzysz_bez_celebrate_na_zwyklej_stronie(client, login, make_user, db):
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    html = client.get('/client/dashboard').data.decode()
    assert 'data-celebrate="0"' in html


def test_pet_companion_css_ladowany_na_stronie_bez_super(app, client, login, make_user, db):
    """Recenzja etapu 4 (paczka A): 11 szablonów nadpisuje extra_css bez super() — link musi być poza blokiem."""
    from flask import url_for
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    with app.test_request_context():
        url = url_for('orders.client_list')
    html = client.get(url).data.decode()
    assert 'css/components/pet-companion.css' in html and 'id="petCompanion"' in html
```

- [ ] **Step 2: RED** — `venv/bin/python -m pytest tests/test_pets_widget_companion.py -q -p no:cacheprovider > <scratch>/e5t1_red.txt 2>&1; echo $?` → Expected: 7 failed (KeyError `most_in_need_pet_id`, brak `#petsWidget`, brak `#petCompanion`).

- [ ] **Step 3: `state.py`** — po wyliczeniu `auto = most_in_need(zywe)` dodaj do `stan`:

```python
    stan['most_in_need_pet_id'] = auto['id'] if auto else None
```

(w obu trybach, także `lite` — widget i towarzysz czytają to samo pole).

- [ ] **Step 4: kontekst dashboardu** — w `modules/client/routes.py::dashboard()` przed `render_template`:

```python
    from modules.pets import service as pets_service
    from modules.pets.config import pets_feature_for
    pets_widget = pets_service.state_for_user(_viewer) if pets_feature_for(current_user) else None
```

i `pets_widget=pets_widget` w `render_template`. (`state_for_user` może zapisać wyliczone odejście i commitować — to zamierzone, jak na stronie domku.)

- [ ] **Step 5: `templates/client/pets/_widget.html`** (szkielet; JS z Task 2 wypełnia `.pets-widget__body`):

```html
{% if pets_widget %}
<div class="dashboard-section pets-widget" id="petsWidget"
     data-state='{{ pets_widget | tojson }}'
     data-api="/client/pupile/api"
     data-home-url="{{ url_for('pets.home') }}">
    <div class="widget">
        <div class="widget-header">
            <h2 class="widget-title">🐾 Mój pupil</h2>
            <a href="{{ url_for('pets.home') }}" class="widget-link">Do domku &rarr;</a>
        </div>
        <div class="widget-body pets-widget__body" aria-live="polite"></div>
    </div>
</div>
{% endif %}
```

Filtr `tojson` (Flask) escapuje `<`, `>`, `&`, `'` do sekwencji unicode, więc atrybut w apostrofach jest bezpieczny bez `| e` (które zepsułoby JSON encjami `&#34;`). Test `_stan_widgetu` robi `html.unescape` + `json.loads`, więc przejdzie w obu wariantach.

- [ ] **Step 6: `templates/components/pet_companion.html`**:

```html
{# Towarzysz (spec §4.4): SSR nie pyta bazy — o widoczności decyduje JS ze stanu lite w localStorage #}
{% if current_user.is_authenticated and pets_enabled %}
<div class="pet-companion" id="petCompanion" hidden
     data-user-id="{{ current_user.id }}"
     data-api="/client/pupile/api"
     data-home-url="{{ url_for('pets.home') }}"
     data-mode="{{ companion_mode | default('walk') }}"
     data-celebrate="{{ '1' if pet_celebrate | default(false) else '0' }}"
     aria-label="Twój pupil">
    <button type="button" class="pet-companion__hit" id="petCompanionHit" aria-label="Pogłaszcz pupila"></button>
    <div class="pet-companion__scene" id="petCompanionScene"></div>
    <div class="pet-companion__bubble" id="petCompanionBubble" hidden></div>
</div>
<script src="{{ url_for('static', filename='js/pet/species.js') }}"></script>
<script src="{{ url_for('static', filename='js/components/pet-rig.js') }}"></script>
<script src="{{ url_for('static', filename='js/utils/haptics.js') }}"></script>
<script src="{{ url_for('static', filename='js/pet/pets-core.js') }}"></script>
<script src="{{ url_for('static', filename='js/components/pet-companion.js') }}"></script>
{% endif %}
```

`pet_celebrate` ustawiają strony podziękowania przez `{% set pet_celebrate = true %}` **przed** `{% extends %}`? — w Jinja2 `set` w szablonie potomnym poza blokiem nie jest widoczny w rodzicu. Dlatego: w `base_client.html` i `base_offers.html` include dostaje `with pet_celebrate=(request.endpoint in ('offers.thank_you', 'shop.order_success'))` — jedno źródło prawdy po nazwie endpointu, bez `data-pet-celebrate` w samych stronach. Atrybut `data-pet-celebrate="1"` ze specu §4.1 zastępujemy `data-celebrate` na `#petCompanion` (**Ruling**, zapisz w ledgerze: ten sam efekt, mniej miejsc do pilnowania).

- [ ] **Step 7: include'y** —
  - `templates/client/base_client.html`: w `body_content` po `{% include 'components/bottom_bar_client.html' %}` dodaj `<link rel="stylesheet" href="{{ url_for('static', filename='css/components/pet-companion.css') }}">` i `{% include 'components/pet_companion.html' with context %}` — a z bloku `extra_css` **usuń** link do `pet-companion.css` (naprawa uwagi A). Do include'u przekaż `companion_mode='walk'`, `pet_celebrate=(request.endpoint == 'shop.order_success')` — składnia: `{% with companion_mode='walk', pet_celebrate=(request.endpoint == 'shop.order_success') %}{% include 'components/pet_companion.html' %}{% endwith %}`.
  - `templates/offers/base_offers.html`: w bloku `scripts` **przed** `{% block extra_js %}` dodaj link do `pet-companion.css` (strony ofert nie ładują `client-layout.css`) i ten sam `with`-include z `companion_mode='sit'`, `pet_celebrate=(request.endpoint == 'offers.thank_you')`.
  - `templates/client/dashboard.html`: pod `{% include 'client/_contest_widget.html' %}` dodaj `{% include 'client/pets/_widget.html' %}`; w `extra_css` dodaj `pet-rig.css`, `pet-card.css`, `pet-widget.css`; w `extra_js` dodaj (w tej kolejności) `js/pet/species.js`, `js/components/pet-rig.js`, `js/utils/haptics.js`, `js/pet/pets-core.js`, `js/components/pet-card.js`, `js/pages/client/pets-widget.js` — tylko w `{% if pets_widget %}`. Towarzysz (include w base) ładuje `species.js`/`pet-rig.js`/`haptics.js`/`pets-core.js` ponownie — każdy z tych plików MUSI być idempotentny (`if (window.PetRig) return;` na początku IIFE); sprawdź po etapie 4 i dopisz guard tam, gdzie go brak (dotyczy też `pet-card.js`).
  - **Ruling do ledgera:** podwójne `<script src>` tego samego pliku to jedno pobranie (cache) i drugie wykonanie → guardy idempotencji zamiast skomplikowanej deduplikacji w szablonach.

- [ ] **Step 8: GREEN** — ten sam pytest → Expected: 7 passed. Następnie `venv/bin/python -m pytest tests/test_pets_routes.py tests/test_client_dashboard_privacy.py tests/test_dashboard_overdue_widget.py -q -p no:cacheprovider` → Expected: wszystkie passed (dashboard nadal renderuje).

- [ ] **Step 9: Commit** — `git add modules/pets/state.py modules/client/routes.py templates/client/pets/_widget.html templates/components/pet_companion.html templates/client/base_client.html templates/offers/base_offers.html templates/client/dashboard.html tests/test_pets_widget_companion.py` → `feat(pupile): kontekst widgetu dashboardu, include towarzysza, most_in_need_pet_id`.

---

### Task 2 (centrala): `pets-core.js` — wyniesienie `PetsApi`/`PetsState` z `pets.js` + cache `localStorage` + unieważnianie

**Files:**
- Create: `static/js/pet/pets-core.js`
- Modify: `static/js/pages/client/pets.js` (usunięcie definicji `PetsApi`/`PetsState`, użycie `window.PetsApi`/`window.PetsState`; po odbiorze jajka `start` → `window.dispatchEvent(new Event('push-force-banner'))`), `templates/client/pets/home.html` (`pets-core.js` przed `pet-card.js`)
- Test: `tests/test_pets_routes.py::test_strona_szkielet_z_data_state` (dopisz asercję `'js/pet/pets-core.js' in html`)

**Interfaces:**
- Consumes: aktualny kod `PetsApi`/`PetsState` z etapu 4 C (przenieś 1:1, nie przepisuj).
- Produces: `window.PetsApi = { base, get(path), post(path, body) }` (jak w etapie 4); `window.PetsState = { current, set(state), onChange(cb), needsCare(), load(userId) -> state|null, save(userId, state), invalidate(userId), fetchLite(userId, {force}) -> Promise<state> }`; zdarzenie `document: 'pets:state'` z `detail = state`; funkcja `window.PetsState.setNavDots(state)` ustawiająca `#petsNavDot` (`hidden = !needs_care`) i `#pwaSheetPetsDot` (`style.display`), **także** wewnątrz `template#pwaSheetClientMore` (`template.content.getElementById` nie istnieje — użyj `template.content.querySelector('#pwaSheetPetsDot')`).

- [ ] **Step 1:** Przenieś `PetsApi` i `PetsState` do `pets-core.js` (IIFE z guardem `if (window.PetsState) return;`). Dodaj cache:

```js
    var CACHE_PREFIX = 'pets_state_v1_';
    var CACHE_TTL_MS = 5 * 60 * 1000;
    function cacheKey(userId) { return CACHE_PREFIX + String(userId); }
    function load(userId) {
        try {
            var raw = localStorage.getItem(cacheKey(userId));
            if (!raw) return null;
            var rec = JSON.parse(raw);
            if (!rec || typeof rec.t !== 'number' || Date.now() - rec.t > CACHE_TTL_MS) return null;
            return rec.s || null;
        } catch (e) { return null; }
    }
    function save(userId, state) {
        try { localStorage.setItem(cacheKey(userId), JSON.stringify({ t: Date.now(), s: state })); } catch (e) { /* prywatne okno / limit */ }
    }
    function invalidate(userId) {
        try { localStorage.removeItem(cacheKey(userId)); } catch (e) {}
    }
    function fetchLite(userId, opts) {
        var cached = (opts && opts.force) ? null : load(userId);
        if (cached) { PetsState.set(cached); return Promise.resolve(cached); }
        return PetsApi.get('/stan?lite=1').then(function (state) {
            save(userId, state);
            PetsState.set(state);
            return state;
        });
    }
```

`PetsState.set(state)` ma po zmianie: zapisać cache gdy zna `userId` (ustaw `PetsState.userId` z `data-user-id` towarzysza / `#petsApp`? — na stronie domku `current_user.id` nie jest w DOM: dodaj `data-user-id="{{ current_user.id }}"` do `#petsApp` w `home.html` i do `#petsWidget`), wywołać `setNavDots(state)`, wyemitować `pets:state`. Każda odpowiedź akcji z API zawiera pełny `state` — więc `set()` po akcji = cache zawsze świeży; dodatkowo `invalidate()` w `catch` błędów 410/409 (stan niepewny).

- [ ] **Step 2:** W `pets.js` po udanym `POST /jajka/odbierz` ze `source === 'start'`: `window.dispatchEvent(new Event('push-force-banner'));` (spec §9 pkt 5 — baner pushy po odbiorze pierwszego jajka; `push-banner.js:144` sam sprawdza cooldown/subskrypcję).

- [ ] **Step 3:** `home.html`: dodaj `<script src="{{ url_for('static', filename='js/pet/pets-core.js') }}">` przed `pet-card.js`; dopisz asercję w `test_strona_szkielet_z_data_state` (RED → GREEN).

- [ ] **Step 4:** Podgląd `preview_start {name: "pets-preview"}` → `/dev-login` → domek działa jak przed refaktorem (odbiór, akcja, pat), `localStorage` ma klucz `pets_state_v1_1` po pierwszej akcji; konsola bez błędów. Potem `venv/bin/python -m pytest tests/test_pets_routes.py -q -p no:cacheprovider` → Expected: passed.

- [ ] **Step 5: Commit** — `refactor(pupile): pets-core.js (PetsApi/PetsState + cache localStorage), push-force-banner po odbiorze`.

---

### Task 3 (paczka W — widget, agent Opus 5.5, równolegle z Task 4): `pets-widget.js` + `pet-widget.css`

**Files:**
- Create: `static/js/pages/client/pets-widget.js`, `static/css/components/pet-widget.css`
- Modify (tylko jeśli konieczne): `templates/client/pets/_widget.html` (treść szkieletu z Task 1 zostaje; można dodać `<template>`)

**Interfaces:**
- Consumes: `#petsWidget[data-state][data-api][data-home-url]`, `window.PetCard.render(container, petDict, { mini: true, onAction(pet, action, count), species })` → `card.update(petDict)`, `window.PetsApi`, `window.PetsState` (`set`, `onChange`), `window.PetRig.mountEgg`, `window.Haptics`, `window.showToast`.
- Produces: nic nowego dla innych etapów; klasy `pets-widget__*`.

**Zachowanie (spec §4.3):**
- Boot: `state = JSON.parse(widget.dataset.state)`; `PetsState.set(state)`.
- Wybór treści (w tej kolejności): (1) `state.most_in_need_pet_id` → mini-karta tego pupila (`PetCard.render(..., {mini: true})`) + szybkie akcje karm/baw/myj (karta mini je ma; jeśli karta mini nie renderuje przycisków — dodaj je w widgecie z tą samą delegacją `data-action`), nastrój słownie, „Obudź" gdy `asleep`; (2) brak żywych, ale `state.eggs` z `ready` → kafelek jajka (`PetRig.mountEgg` z `pct: 100, ready: true`) + link „Wykluj w domku"; (3) jajko w inkubacji → `mountEgg` z `progress_pct`, tekst „Wykluje się za ~N h" (z `egg_hours` i `progress_pct`; jeśli `boost_until` w przyszłości dopisz „ogrzane ×2"); (4) `state.eggs_available` niepuste (w tym wirtualne `start`) → zachęta: dla `start` „Odbierz swoje pierwsze jajko" / dla innych „Czeka na Ciebie jajko" + link do domku (odbiór odbywa się w domku — Ruling: jeden przepływ odbioru, mniej stanów w widgecie); (5) nic z powyższego (np. wszyscy odeszli, miesięczne za X dni) → „Następne jajko: za N dni" z `next_monthly_at`.
- Akcja z karty: `PetsApi.post('/' + pet.id + '/akcja', {action, count})` → `PetsState.set(res.state)` → `card.update(nowyPet)`; błędy: 409 `not_available`/`asleep` → odśwież stan (`PetsApi.get('/stan')` → `set`), bez toastu; 410 → toast z `message` + przerysowanie wg nowego stanu; inne → toast „Coś poszło nie tak, spróbuj za chwilę". `Haptics.tap()` przy pat (klik w scenę).
- Odświeżanie: co 5 min `PetsApi.get('/stan')` → `set` → przerysowanie, oraz nasłuch `pets:state` (towarzysz na tej samej stronie może odświeżyć stan).
- Ekstrapolacja pasków co 1 s z `rates_per_hour` (jak na domku) — jeśli `PetCard` robi to sam, nie dubluj.
- CSS: `.pets-widget` dziedziczy `dashboard-section` (tło/obramowanie już ma light/dark); `.pets-widget__body` = układ: scena (rig mini 96 px) po lewej, treść po prawej; na ≤ 480 px pionowo. Szybkie akcje ≥ 44 px. Dark: zgodnie z paletą. Stany pustki (jajko/zachęta) — ten sam układ, scena z jajkiem lub ikoną łapki (`static/img/icons/paw.svg`).

- [ ] **Step 1:** Podgląd (`preview_start {name: "pets-preview-w"}`, wpis dopisze centrala — port 5003, `--no-night`); `/dev-login` → `/client/dashboard` (seed ma pupile, więc gałąź (1)); zweryfikuj boot bez błędów.
- [ ] **Step 2:** Gałąź (1): mini-karta + akcje + pat; 409 bez toastu; po akcji `localStorage.pets_state_v1_1` ma nowy `now`.
- [ ] **Step 3:** Gałęzie (2)–(5): przygotuj stany przez API w konsoli (`PetsApi.post('/jajka/odbierz', {source:'monthly'})` itd.) albo przez ponowne zasianie z flagami — jeśli trzeba, poproś centralę o wariant seeda `--scenario`.
- [ ] **Step 4:** CSS light/dark, 375/768/1280 px, zrzuty; `prefers-reduced-motion`.
- [ ] **Step 5:** Commit per krok `feat(pupile): widget dashboardu …`. Nie commituj launch.json ani plików seeda.

---

### Task 4 (paczka T — towarzysz, agent Opus 5.5, równolegle z Task 3): `pet-companion.js` + `pet-companion.css`

**Files:**
- Create: `static/js/components/pet-companion.js`
- Modify: `static/css/components/pet-companion.css` (rozbudowa pliku z etapu 4 — zachowaj istniejące reguły kropek)

**Interfaces:**
- Consumes: `#petCompanion[hidden][data-user-id][data-api][data-home-url][data-mode][data-celebrate]`, `#petCompanionHit`, `#petCompanionScene`, `#petCompanionBubble`; `window.PetsState.fetchLite(userId)`, `PetsState.onChange`, `PetsState.invalidate`, `PetsApi.post`, `window.PetRig.mount(scene, {species, stage, stars, mood, asleep, size: 'companion'})` → `rig.update/playAction/gesture/destroy`, `window.PetRig.reducedMotion()`, `window.Haptics`.
- Produces: nic dla innych etapów; klasy `pet-companion--walk|--sit|--asleep|--flipped`, zmienna `--pet-companion-offset`.

**Zachowanie (spec §4.4):**
- Start: `userId = el.dataset.userId`; tryb `walk`/`sit`. **Panel (`walk`)**: po `DOMContentLoaded` → `PetsState.fetchLite(userId)` (cache lub sieć; sieć po `requestIdleCallback`, fallback `setTimeout(fn, 1500)`). **Oferty (`sit`)**: po `window load` + 4000 ms + idle.
- Z stanu: `pet = pets.find(id === companion.pet_id)`; jeśli `!companion.enabled || !pet` → `el.hidden = true` i koniec (kropki w nawigacji ustawia `PetsState.setNavDots` niezależnie). W przeciwnym razie `PetRig.mount(scene, {...pet, asleep: pet.asleep, size: 'companion'})`, `el.hidden = false`.
- **Spacer (`walk`)**: pozycja `left` w px w obrębie `[8, innerWidth - szer - 8]`; co 4–9 s losowy cel; ruch przez `transition: left Ns linear` (N = dystans / 40 px/s); przed ruchem `--flipped` wg kierunku (`scaleX(-1)` na scenie); po dojściu: 30 % szans na gest (`rig.gesture('sway')`/`'jump'` zgodnie z dostępnymi dla stadium — `gesture()` zwraca false, gdy niedostępny), potem pauza. Przy `resize` — klamra pozycji. `prefers-reduced-motion` (`PetRig.reducedMotion()`): bez spaceru, stała pozycja w prawym dolnym rogu.
- **Sen**: `pet.asleep` → klasa `--asleep`, rig z `asleep: true`, bez spaceru, dymek „Śpi… zzz" (bez linku) przez 4 s po załadowaniu.
- **Dymek** gdy `state.needs_care`: tekst wg priorytetu: pupil `mood` krytyczny/chory → „Źle się czuję…", głodny → „Jestem głodny!", smutny/znudzony → „Pobaw się ze mną!", brudny → „Umyj mnie!", jajko `ready` → „Jajko gotowe!", `eggs_available` → „Czeka na Ciebie jajko!"; link „Do domku" (`data-home-url`). Dymek znika po 8 s albo po kliknięciu; pokazuje się ponownie najwcześniej po 10 min (`sessionStorage` `pets_bubble_shown_<userId>`).
- **Klik** (`#petCompanionHit`, min 44×44 px, obejmuje scenę): jeśli `asleep` → tylko dymek „Śpi… zzz"; inaczej `Haptics.tap()`, `rig.playAction('pat')`, paczkowanie: licznik + `setTimeout` 2 s (max 50) → `PetsApi.post('/' + pet.id + '/akcja', {action: 'pat', count})` → `PetsState.set(res.state)`; 409 → cicho + `PetsState.fetchLite(userId, {force: true})`; 410 → `el.hidden = true`, `PetsState.invalidate(userId)`; inne → cicho (towarzysz nie robi toastów błędów, żeby nie przeszkadzać).
- **Celebrate**: `data-celebrate="1"` → po `mount` (gdy nie śpi) `rig.playAction('celebrate')` + dymek „Hura! Dziękuję za zamówienie 🎉" (bez haptyki — użytkownik nic nie kliknął).
- **`pets:state`** z innych skryptów (widget/domek): `rig.update(...)` i ponowna ocena dymka.
- CSS: `.pet-companion { position: fixed; left: 16px; bottom: calc(16px + var(--pet-companion-offset, 0px)); z-index: 1200; width: 72px; height: 72px; pointer-events: none; }` (dzieci `pointer-events: auto`), tryb `--sit`: `left: auto; right: 16px`, ≤ 480 px: 56 px i `bottom` nad paskiem PWA — sprawdź, w jakim warunku `bottom-bar.css` pokazuje `.pwa-bottom-bar` (media query / klasa na `html`/`body`) i użyj identycznego warunku do `--pet-companion-offset: calc(60px + env(safe-area-inset-bottom, 0px))`. Dymek: nad sceną, max 220 px, light `#fff`/`#333` + border `#e0e0e0`; dark `rgba(30,27,38,0.95)` + border `rgba(240,147,251,0.3)` + `color: #fff`; ogonek przez `::after`. Przejścia `left` i `opacity`; `@media (prefers-reduced-motion)` wyłącza przejścia.

- [ ] **Step 1:** Podgląd (`preview_start {name: "pets-preview-t"}`, port 5004; centrala dopisze wpis). Panel: `/client/dashboard`, `/client/orders` (szablon bez `super()` — CSS musi się załadować), dark/light, 375 px.
- [ ] **Step 2:** Spacer + flip + gesty + pauzy; reduced-motion (DevTools → Rendering → emulate) = brak ruchu.
- [ ] **Step 3:** Klik → pat paczką (żądanie po 2 s w `read_network_requests`); 410 (ustaw pupila jako `dead` przez `PetsApi.post` nie da się — zasymuluj `pet_id` nieistniejącym przez `localStorage` edycję stanu) → znika i unieważnia cache.
- [ ] **Step 4:** Noc: seed bez `--no-night` (centrala poda port/wpis z nocą) → śpi, zzz, klik bez pat.
- [ ] **Step 5:** Strona oferty (`/offer/<token>` lub `/offer/<token>/thank-you` z seeda — centrala dopisze do seeda aktywną stronę oferty): fetch po `load` + 4 s, siedzi w rogu, celebrate na thank-you.
- [ ] **Step 6:** Commity per krok `feat(pupile): towarzysz …`.

---

### Task 5 (centrala): scalanie, `CACHE_VERSION`, weryfikacja, recenzja

- [ ] **Step 1:** Rozszerz `dev_pets_preview.py` o `--scenario` (`domyslny`, `bez-pupili` = sam profil + jajko w inkubacji, `tylko-start` = brak profilu) i o aktywną stronę oferty (`OfferPage(status='active')` + token wypisany na starcie) dla Task 4 Step 5; wpisy `pets-preview-w` (5003, `--no-night`), `pets-preview-t` (5004, `--no-night`), `pets-preview-noc` (5005) w lokalnym `launch.json`.
- [ ] **Step 2:** Merge W i T (`--no-ff`), `CACHE_VERSION` bump (+1 względem zastanej), pełna suita do pliku, `git status` czysty poza `.claude/launch.json`.
- [ ] **Step 3:** Weryfikacja własna: dashboard (gałąź z pupilem i bez), lista zamówień (towarzysz + CSS), strona oferty (sit + odroczony fetch), thank-you (celebrate), 375 px (towarzysz nad paskiem PWA — zrzut), dark mode, dwóch użytkowników (Review Focus 1: klucze `localStorage`).
- [ ] **Step 4:** Recenzja etapu świeżym Opusem (zakres od `6e622b16`/końca etapu 4), fix pass Critical/Important TDD, ledger `.superpowers/sdd/2026-10-11-pupile-etap-5-widget-towarzysz/progress.md`, ClickUp, pamięć.
