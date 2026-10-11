# Pupile — świat na pełny ekran + szpital jako minigra — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Każda scena świata pupili wypełnia cały wolny ekran z oknami kontekstowymi wewnątrz sceny, a szpital staje się trzema scenami (hol z recepcją, Inkubatorium, Izba przyjęć) z widocznymi inkubatorami i łóżkami.

**Architecture:** Backend (centrala, TDD) dostaje tylko nowe adresy sal szpitala, nowe cele pushy i adresy sal w `data-*` towarzysza/widgetu — API, modele i reguły bez zmian. Frontend to dwie kolejne paczki dla subagentów w worktree: „Rama” (pełny ekran, pigułka nawigacji, wspólne okno sceny, router z nowymi kluczami, dopasowanie istniejących scen) i „Szpital” (hol/Inkubatorium/Izba na wspólnym oknie sceny, linki). Kontrakty między paczkami są zapisane niżej co do nazwy.

**Tech Stack:** Flask 3 + Jinja2, pytest przez `venv/bin/python -m pytest`, vanilla JS (IIFE, bez bundlera), SVG/CSS (light + `[data-theme="dark"]`).

**Spec:** `docs/superpowers/specs/2026-10-11-pupile-pelny-ekran-szpital-design.md` (v3.1; nadrzędny) + `docs/superpowers/specs/2026-10-11-pupile-swiat-design.md` (v3; obowiązuje poza miejscami, które v3.1 zmienia).

## Global Constraints

- Gałąź `feat/pupile`, **bez pusha** (push = auto-deploy). Bez migracji (spec v3.1 §2: zero zmian w modelach).
- Testy: `venv/bin/python -m pytest …` (nigdy gołe `pytest`), wynik do pliku, kod wyjścia z pliku. Znany niezwiązany czerwony test do `--deselect` w pełnej suicie: `tests/test_mobile_api_auth.py::test_logout_stores_expiry_in_local_time_and_purges_expired`.
- Light + dark dla KAŻDEGO stylu (`[data-theme="dark"]`, paleta glassmorphism z CLAUDE.md); style okien/nakładek w `static/css/components/modals.css`; zero inline JS/CSS poza `data-*` i wartościami dynamicznymi; cele dotyku ≥ 44 px; `prefers-reduced-motion` i `.pet-rig-rm` respektowane.
- `window.showToast` (nie `window.Toast`), komunikaty escapowane; zero inline `onclick` (delegacja + `data-*`).
- Adresy i klucze scen (spec v3.1 §4.1), identyczne w Flask i `pets.js`:
  `mapa` = `/client/pupile`, `domek` = `/domek`, `szpital` = `/szpital` (hol), `inkubatorium` = `/szpital/inkubatorium`, `izba` = `/szpital/izba-przyjec`, `warsztat` = `/warsztat`, `ogrod` = `/ogrod`.
  Powrót z pigułki: poziom 1 (`domek`, `szpital`, `warsztat`, `ogrod`) → `mapa` z etykietą „Świat”; poziom 2 (`inkubatorium`, `izba`) → `szpital` z etykietą „Szpital”.
  Nazwy w pigułce (h1): „Moje pupile”, „Domek”, „Szpital”, „Inkubatorium”, „Izba przyjęć”, „Warsztat”, „Ogród wspomnień”.
- Parametry głębokich linków: `domek?pupil=ID`, `izba?pupil=ID`, `inkubatorium?jajko=ID`; stare `/szpital?pupil=ID` → `replaceState` na `/szpital/izba-przyjec?pupil=ID`.
- Wymiary (spec v3.1 §3): scena właściwa `max-width: 1200px`; okno sceny desktop (≥ 1024 px) szer. 360 px, margines 16 px, rezerwa sceny 376 px; mobile arkusz max. 75% wysokości sceny, uchwyt 44 px. Siatki: inkubatory ≥ 1024 px do 5 w rzędzie, 600–1023 po 3, < 600 po 2; łóżka ≥ 1024 do 4, 600–1023 po 3, < 600 po 2. Miejsca: `max(3, n)`.
- `static/sw.js`: bump `CACHE_VERSION` o 1 względem zastanej wartości w zadaniu integracji (`thunderorders-v30` → `v31`).
- Repo publiczne: żadnych danych infrastruktury w commitach. Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Niski widok** (laptop 1366×600, telefon poziomo 812×375, PWA z dolnym paskiem): strona nie przewija się, scena nie wychodzi poza widok, okno sceny mieści się w scenie (przewija się w środku), pigułka nie zasłania obiektów. Weryfikacja w Task 4 krok 6 i Task 5 krok 6.
2. **Dużo obiektów** (6+ jajek w inkubacji, 8 pupili w szpitalu, 4 jajka do odebrania na ladzie): siatki zawijają się bez nachodzenia, przewijanie wewnątrz sceny, lada mieści wszystkie jajka (zawijanie). Weryfikacja w Task 5 krok 6 (seed podglądu z wieloma obiektami).
3. **Zmiana stanu przy otwartym oknie** (odświeżenie co 5 min, akcja w innej karcie: jajko odebrane/wyklute, pupil odebrany/zmarł): okno odświeża treść albo zamyka się z fokusem na scenie; żadnych martwych przycisków wywołujących 409 w pętli. Weryfikacja w Task 4 krok 6 (domek) i Task 5 krok 6 (szpital) przez zmianę stanu z drugiej karty.
4. **Złe głębokie linki** (`izba-przyjec?pupil=999`, `inkubatorium?jajko=abc`, stare `/szpital?pupil=ID` dla pupila w domku, cudzy ID): sala bez otwartego okna, bez błędu w konsoli; pupil w domku ze starego linku → izba bez okna. Weryfikacja w Task 5 krok 6.
5. **Zmiana szerokości przy otwartym oknie** (zwinięcie sidebara 240↔72 px, obrót telefonu, przejście przez 1024 px): okno przełącza tryb arkusz ↔ karta bez utraty treści i fokusu, rezerwa sceny przelicza się. Weryfikacja w Task 4 krok 6.

---

### Task 1: Trasy sal szpitala + adresy sal w `data-*` towarzysza i widgetu

**Files:**
- Modify: `modules/pets/routes.py:111-133` (stała `HOSPITAL_ROOMS`, trasa `hospital_room`)
- Modify: `templates/components/pet_companion.html:10` (nowe `data-ward-url`)
- Modify: `templates/client/pets/_widget.html:9` (nowe `data-ward-url`, `data-incubator-url`)
- Test: `tests/test_pets_swiat_trasy.py`, `tests/test_pets_widget_companion.py`

**Interfaces:**
- Consumes: `_render_scene(scene)`, `feature_required`, `pets_bp` (bez zmian).
- Produces: endpoint `pets.hospital_room` (`url_for('pets.hospital_room', sala='inkubatorium' | 'izba-przyjec')`); `data-scene="inkubatorium"` / `"izba"` w `#petsApp`; atrybuty `data-ward-url="/client/pupile/szpital/izba-przyjec"` (towarzysz, widget) i `data-incubator-url="/client/pupile/szpital/inkubatorium"` (widget). `data-hospital-url` zostaje i dalej wskazuje hol `/client/pupile/szpital`.

- [ ] **Step 1: Write the failing tests**

Dopisz na końcu `tests/test_pets_swiat_trasy.py`:

```python
def test_sale_szpitala_maja_adresy(client, login, make_user, db):
    """Spec v3.1 §4.1: hol ma dwie sale pod własnymi adresami; klucz sceny to nie adres."""
    login(make_user(profile_completed=True))
    _wlacz(db)
    for sciezka, scena in (('/szpital/inkubatorium', 'inkubatorium'), ('/szpital/izba-przyjec', 'izba')):
        r = client.get('/client/pupile' + sciezka)
        assert r.status_code == 200 and _scena(r.data.decode()) == scena, sciezka
    assert client.get('/client/pupile/szpital/kostnica').status_code == 404
    assert client.get('/client/pupile/szpital/izba').status_code == 404


def test_sale_szpitala_za_flaga(client, login, make_user):
    login(make_user(profile_completed=True))
    assert client.get('/client/pupile/szpital/inkubatorium').status_code == 404
    assert client.get('/client/pupile/szpital/izba-przyjec').status_code == 404
```

W `tests/test_pets_widget_companion.py`, w teście `test_towarzysz_podaje_adresy_domku_i_szpitala_dla_dymka`, pod linią z `data-hospital-url` dopisz:

```python
    assert 'data-ward-url="/client/pupile/szpital/izba-przyjec"' in tag
```

i dopisz nowy test na końcu pliku:

```python
def test_widget_podaje_adresy_sal_szpitala(client, login, make_user, db):
    """Spec v3.1 §5: widget prowadzi prosto do sali (pupil w szpitalu → izba, jajka → inkubatorium)."""
    import re
    from tests.pets_helpers import zaloz_profil, zaloz_pupila
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    zaloz_pupila(user)
    html = client.get('/client/dashboard').data.decode()
    m = re.search(r'<div class="dashboard-section pets-widget" id="petsWidget"[^>]*>', html, re.S)
    assert m, 'brak #petsWidget'
    tag = m.group(0)
    assert 'data-hospital-url="/client/pupile/szpital"' in tag
    assert 'data-ward-url="/client/pupile/szpital/izba-przyjec"' in tag
    assert 'data-incubator-url="/client/pupile/szpital/inkubatorium"' in tag
```

(Jeśli `_wlacz` nie jest jeszcze importowany w tym pliku, użyj tego samego importu co istniejące testy pliku: `from tests.test_pets_routes import _wlacz`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_pets_swiat_trasy.py tests/test_pets_widget_companion.py -q -p no:cacheprovider > $SP/t1_red.txt 2>&1; echo "exit=$?"; tail -5 $SP/t1_red.txt`
Expected: FAIL — `test_sale_szpitala_maja_adresy` (404 zamiast 200), test towarzysza i `test_widget_podaje_adresy_sal_szpitala` (brak `data-ward-url`). `test_sale_szpitala_za_flaga` przechodzi już teraz (dwa segmenty → brak trasy → 404) — to test ochronny bramki po dodaniu trasy, zostaje.

- [ ] **Step 3: Implement**

W `modules/pets/routes.py` pod `SCENES = (...)`:

```python
HOSPITAL_ROOMS = {'inkubatorium': 'inkubatorium', 'izba-przyjec': 'izba'}   # spec v3.1 §4.1: adres → klucz sceny
```

i pod trasą `scene`:

```python
@pets_bp.route('/szpital/<sala>')
@feature_required
def hospital_room(sala):
    scena = HOSPITAL_ROOMS.get(sala)
    if scena is None:
        abort(404)
    return _render_scene(scena)
```

W `templates/components/pet_companion.html` pod `data-hospital-url=…`:

```html
     data-ward-url="{{ url_for('pets.hospital_room', sala='izba-przyjec') }}"
```

W `templates/client/pets/_widget.html` zamień linię `data-hospital-url=…">` na:

```html
     data-hospital-url="{{ url_for('pets.scene', scene='szpital') }}"
     data-ward-url="{{ url_for('pets.hospital_room', sala='izba-przyjec') }}"
     data-incubator-url="{{ url_for('pets.hospital_room', sala='inkubatorium') }}">
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_pets_swiat_trasy.py tests/test_pets_widget_companion.py tests/test_pets_routes.py -q -p no:cacheprovider > $SP/t1_green.txt 2>&1; echo "exit=$?"; tail -3 $SP/t1_green.txt`
Expected: PASS, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add modules/pets/routes.py templates/components/pet_companion.html templates/client/pets/_widget.html tests/test_pets_swiat_trasy.py tests/test_pets_widget_companion.py
git commit -m "feat(pupile): sale szpitala pod wlasnymi adresami + adresy sal dla towarzysza i widgetu

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Push prowadzi prosto do sali

**Files:**
- Modify: `modules/pets/notifications.py` (`push_path`)
- Test: `tests/test_pets_cron.py` (`test_tekst_chory_i_sciezki_pushu`, `test_push_przypomnienie_o_ratunkowym_nie_kieruje_do_ogrodu`)

**Interfaces:**
- Consumes: koszyk `dict(user, alerts, deaths, eggs_ready, monthly, rescue_reminders, healed)` (bez zmian).
- Produces: `push_path(basket) -> str` z kolejnością: alert chory/krytyczny → `/szpital/izba-przyjec`; odejście → `/ogrod`; wyzdrowiały → `/szpital/izba-przyjec`; jajko gotowe do wyklucia → `/szpital/inkubatorium`; nowe miesięczne → `/szpital`; reszta → `/domek`.

- [ ] **Step 1: Update the tests to the new contract**

W `tests/test_pets_cron.py` zamień w `test_tekst_chory_i_sciezki_pushu` cztery asercje `push_path` na:

```python
    assert push_path(_koszyk(user, alerts=[(p, LEVEL_CRITICAL)], deaths=[p])) == '/client/pupile/szpital/izba-przyjec'
    assert push_path(_koszyk(user, deaths=[p])) == '/client/pupile/ogrod'
    assert push_path(_koszyk(user, healed=[p])) == '/client/pupile/szpital/izba-przyjec'
    assert push_path(_koszyk(user, eggs_ready=[p])) == '/client/pupile/szpital/inkubatorium'
    assert push_path(_koszyk(user, monthly=True)) == '/client/pupile/szpital'
    assert push_path(_koszyk(user, healed=[p], eggs_ready=[p], monthly=True)) == '/client/pupile/szpital/izba-przyjec'
    assert push_path(_koszyk(user, eggs_ready=[p], monthly=True)) == '/client/pupile/szpital/inkubatorium'
    assert push_path(_koszyk(user, alerts=[(p, LEVEL_SAD)])) == '/client/pupile/domek'
```

W `test_push_przypomnienie_o_ratunkowym_nie_kieruje_do_ogrodu` zamień pierwszą asercję na:

```python
    assert push_path(_koszyk(user, rescue_reminders=[p], eggs_ready=[p])) == '/client/pupile/szpital/inkubatorium'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_pets_cron.py -q -p no:cacheprovider -k "sciezki_pushu or ratunkowym" > $SP/t2_red.txt 2>&1; echo "exit=$?"; tail -5 $SP/t2_red.txt`
Expected: FAIL — `'/client/pupile/szpital' != '/client/pupile/szpital/izba-przyjec'`.

- [ ] **Step 3: Implement**

W `modules/pets/notifications.py` zamień `push_path` na:

```python
def push_path(basket):
    """Gdzie prowadzi zbiorczy push (spec v3.1 §5): prosto do sali, w której da się pomóc."""
    if any(poziom >= LEVEL_SICK for _, poziom in basket['alerts']):
        return PETS_URL_PATH + '/szpital/izba-przyjec'
    if basket['deaths']:                      # przypomnienie o ratunkowym idzie mailem — nie steruje pushem
        return PETS_URL_PATH + '/ogrod'
    if basket['healed']:
        return PETS_URL_PATH + '/szpital/izba-przyjec'
    if basket['eggs_ready']:
        return PETS_URL_PATH + '/szpital/inkubatorium'
    if basket['monthly']:
        return PETS_URL_PATH + '/szpital'
    return PETS_URL_PATH + '/domek'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_pets_cron.py tests/test_pets_szpital.py -q -p no:cacheprovider > $SP/t2_green.txt 2>&1; echo "exit=$?"; tail -3 $SP/t2_green.txt`
Expected: PASS, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add modules/pets/notifications.py tests/test_pets_cron.py
git commit -m "feat(pupile): push prowadzi prosto do sali szpitala (izba / inkubatorium / recepcja)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Szablon świata — pełny ekran, pigułka, kontenery sal (test szablonu)

**Files:**
- Modify: `templates/client/pets/home.html`
- Test: `tests/test_pets_swiat_trasy.py`

**Interfaces:**
- Consumes: Task 1 (`data-scene` dla sal).
- Produces (dla Task 4 i 5): `#petsApp.pets-page.pets-page--full`; pigułka `<nav class="pets-pill" data-scene-bar>` z linkiem `a.pets-pill__back[data-scene-link][data-scene-back]` (tekst w `span[data-scene-back-label]`), `h1.pets-pill__title[data-scene-title][tabindex=-1]` i `p.pets-pill__night[data-pets-night][role=status][hidden]`; sekcje `section.pets-scene.pets-scene--<klucz>[data-scene-view="<klucz>"]` dla wszystkich 7 kluczy (w tym `inkubatorium`, `izba`); **brak** elementu `[data-scene-lead]`; skrypt `js/pet/world/scene-window.js` ładowany przed modułami scen.

- [ ] **Step 1: Write the failing test**

Dopisz na końcu `tests/test_pets_swiat_trasy.py`:

```python
def test_szablon_pelny_ekran_z_pigulka(client, login, make_user, db):
    """Spec v3.1 §3: scena na pełny ekran, nagłówek strony zastąpiony pigułką, kontenery obu sal szpitala."""
    login(make_user(profile_completed=True))
    _wlacz(db)
    html = client.get('/client/pupile/szpital/izba-przyjec').data.decode()
    assert re.search(r'id="petsApp" class="pets-page pets-page--full"', html)
    assert 'class="pets-pill"' in html and 'data-scene-back-label' in html
    assert 'data-scene-lead' not in html
    for klucz in ('mapa', 'domek', 'szpital', 'inkubatorium', 'izba', 'warsztat', 'ogrod'):
        assert f'data-scene-view="{klucz}"' in html, klucz
    assert html.index('js/pet/world/scene-window.js') < html.index('js/pet/world/house.js')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_pets_swiat_trasy.py -q -p no:cacheprovider -k pelny_ekran > $SP/t3_red.txt 2>&1; echo "exit=$?"; tail -5 $SP/t3_red.txt`
Expected: FAIL — brak `pets-page--full`.

- [ ] **Step 3: Implement**

W `templates/client/pets/home.html` zamień blok od `<div id="petsApp"` do zamknięcia `</div>` sekcji `pets-world` na:

```html
{# Spec v3.1 §3: każda scena na cały wolny ekran; pigułka zastępuje nagłówek; okna kontekstowe w scenie #}
<div id="petsApp" class="pets-page pets-page--full" data-scene="{{ scene }}" data-user-id="{{ current_user.id }}"
     data-state='{{ state_json | e }}'
     data-species='{{ species_json | e }}'
     data-api="{{ api_base }}">
    <nav class="pets-pill" data-scene-bar aria-label="Świat pupili">
        <a class="pets-pill__back" href="{{ url_for('pets.home') }}" data-scene-link="mapa" data-scene-back
           {% if scene == 'mapa' %}hidden{% endif %}>
            <svg class="pets-pill__icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>
            <span data-scene-back-label>Świat</span>
        </a>
        <h1 class="pets-pill__title" data-scene-title tabindex="-1">Moje pupile</h1>
        <p class="pets-pill__night" data-pets-night role="status" hidden></p>
    </nav>
    <div class="pets-world">
        <section class="pets-scene pets-scene--mapa" data-scene-view="mapa" aria-label="Mapa świata" hidden></section>
        <section class="pets-scene pets-scene--domek" data-scene-view="domek" aria-label="Domek" hidden></section>
        <section class="pets-scene pets-scene--szpital" data-scene-view="szpital" aria-label="Szpital" hidden></section>
        <section class="pets-scene pets-scene--inkubatorium" data-scene-view="inkubatorium" aria-label="Inkubatorium" hidden></section>
        <section class="pets-scene pets-scene--izba" data-scene-view="izba" aria-label="Izba przyjęć" hidden></section>
        <section class="pets-scene pets-scene--warsztat" data-scene-view="warsztat" aria-label="Warsztat" hidden></section>
        <section class="pets-scene pets-scene--ogrod" data-scene-view="ogrod" aria-label="Ogród wspomnień" hidden></section>
    </div>
    <noscript><p class="pets-noscript">Do opieki nad pupilem potrzebny jest włączony JavaScript.</p></noscript>
</div>
```

i w bloku `extra_js` dodaj `<script src="{{ url_for('static', filename='js/pet/world/scene-window.js') }}"></script>` jako pierwszy skrypt po `pet-hatch.js` (przed `room.js`). Utwórz pusty plik `static/js/pet/world/scene-window.js` z nagłówkiem-komentarzem `/* Okno sceny (spec v3.1 §3.4) — implementacja w Task 4. */`, żeby strona nie dostawała 404 do czasu Task 4.

W `static/js/pages/client/pets.js` (funkcja `updateHeader`, ok. linii 380) zamień `if (header.bar) header.bar.hidden = isMap;` na ukrywanie samego linku powrotu — pigułka z h1 zostaje widoczna także na mapie:

```js
        var back = root.querySelector('[data-scene-back]');
        if (back) back.hidden = isMap;
```

Odczyt `[data-scene-lead]` jest już opcjonalny (`if (header.lead)`), więc brak leadu niczego nie psuje; resztę routera (etykieta powrotu, sale szpitala) robi Task 4.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_pets_swiat_trasy.py tests/test_pets_routes.py -q -p no:cacheprovider > $SP/t3_green.txt 2>&1; echo "exit=$?"; tail -3 $SP/t3_green.txt`
Expected: PASS, `exit=0`.

- [ ] **Step 5: Commit**

```bash
git add templates/client/pets/home.html static/js/pet/world/scene-window.js static/js/pages/client/pets.js tests/test_pets_swiat_trasy.py
git commit -m "feat(pupile): szablon swiata na pelny ekran - pigulka i kontenery sal szpitala

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4 (paczka F1 „Rama” — subagent Opus w worktree, po Task 1–3): pełny ekran, pigułka, okno sceny, router, istniejące sceny

**Files:**
- Modify: `static/css/pages/client/pets.css` (kontener pełnoekranowy, pigułka, warstwy sceny `.pets-stage`), `static/css/components/modals.css` (sekcja „Pet panel sheet (v3)” → „Okno sceny (v3.1)”: tryb karta ≥ 1024 px i arkusz < 1024 px, oba `position: absolute` w `.pets-scene`)
- Create/Modify: `static/js/pet/world/scene-window.js` (implementacja)
- Modify: `static/js/pages/client/pets.js` (router: 7 kluczy, adresy, rodzic i etykieta powrotu, h1 w pigułce, pigułka nocy, brak modułu sceny = pusta scena bez błędu, `/szpital?pupil=ID` → `replaceState` na `/szpital/izba-przyjec?pupil=ID`)
- Modify: `static/js/pet/world/house.js` (panel pupila na `PetsSceneWindow`), `static/js/pet/world/room.js` (spacer po szerokości `.pets-stage`, rezerwa przy otwartym oknie), `static/js/pet/world/garden.js` (szczegóły nagrobka / album jako okno sceny, jeśli dziś są poza sceną)
- Modify: `static/css/pages/client/pets-map.css`, `pets-house.css`, `pets-workshop.css`, `pets-garden.css`, `static/css/components/pet-room.css` (tło na całą scenę, obiekty w `.pets-stage`; usunięcie sticky/`:has` z `pets-house.css`, którego już nie trzeba)
- Test: `tests/test_pets_swiat_trasy.py` (bez nowych testów — kontrakt szablonu przypięty w Task 3; jeśli zmieniasz szablon, testy Task 3 muszą zostać zielone)

**Interfaces:**
- Consumes: Task 3 (znaczniki szablonu: `.pets-page--full`, `.pets-pill`, `[data-scene-back]`, `[data-scene-back-label]`, `[data-scene-title]`, `[data-pets-night]`, 7 × `[data-scene-view]`), rejestr scen `window.PetsWorld.scenes[klucz] = { title, create(ctx, host) -> {enter(params), leave(), render(state), setParams(params)?, tick()?} }` (pole `lead` przestaje być używane), `ctx.go(scene, params, opts)`, `ctx.href(scene, params)`.
- Produces (dla Task 5):
  - `window.PetsSceneWindow.attach(sceneEl) -> win`, gdzie `sceneEl` to `section.pets-scene`:
    - `win.open({ content: HTMLElement, labelledBy: string, returnFocus: HTMLElement | null, onClose: function | null })` — otwiera (albo podmienia, jeśli już otwarte: bez animacji zamknięcia, poprzedni `onClose` NIE jest wołany), ustawia `role="dialog"` + `aria-labelledby`, fokus na pierwszy fokusowalny element treści;
    - `win.replace(content)` — podmiana treści przy otwartym oknie (np. po odświeżeniu stanu);
    - `win.close({ restoreFocus: true })` — zamyka, woła `onClose`, przywraca fokus na `returnFocus` (jeśli nadal w DOM) albo na `sceneEl`;
    - `win.isOpen() -> boolean`, `win.body -> HTMLElement`, `win.destroy()`;
    - zamykanie: przycisk ×, Esc, klik w puste tło sceny (element z `data-window-backdrop` albo sam `sceneEl`, nie obiekt sceny), przeciągnięcie arkusza w dół (< 1024 px);
    - przy otwartym oknie `sceneEl.classList.contains('has-window') === true`; CSS ≥ 1024 px: `.pets-scene.has-window .pets-stage { margin-right: 376px }`.
  - Klasa `.pets-stage` (scena właściwa, wyśrodkowana, `max-width: 1200px`) — każdy moduł sceny buduje w niej obiekty; tło sceny na całym `section.pets-scene`.
  - Router: klucze `inkubatorium` i `izba` w `SCENE_ORDER`, ich adresy, rodzic `szpital`, etykiety z Global Constraints; `ctx.href('izba', {pupil: 5}) === '/client/pupile/szpital/izba-przyjec?pupil=5'`, `ctx.href('inkubatorium', {jajko: 7}) === '/client/pupile/szpital/inkubatorium?jajko=7'`.

**Zachowanie (spec v3.1 §3):**
- `.main-content:has(.pets-page--full)`: wysokość widoku (`100dvh`; w przeglądarce mobilnej `calc(100dvh - 60px)`), `box-sizing: border-box`, kolumna flex; zachowuje swoje pionowe odsunięcia (topbar desktop, PWA safe-area + dolny pasek), zeruje poziome i dodatkowe paddingi; `#petsApp` `flex: 1; min-height: 0; position: relative`; `.pets-world` i aktywna `.pets-scene` wypełniają całość; strona bez przewijania (sprawdź `document.scrollingElement.scrollHeight === clientHeight`).
- Pigułka: absolutnie w lewym górnym rogu sceny (16 px), półprzezroczyste tło w obu motywach, cele ≥ 44 px; na mapie bez linku powrotu; pigułka nocy obok (zawija się pod spód na < 600 px).
- Mapa, domek, warsztat, ogród: tło do krawędzi, obiekty w `.pets-stage`; wygląd jak dziś (bez przerysowywania). Domek: panel pupila = `PetsSceneWindow` (zachowanie panelu jak dziś: `?pupil=`, drugi klik = pat, warianty, Obudź, Zabierz do szpitala — ten ostatni na razie nawiguje do `szpital` jak dziś; Task 5 zmienia cel). Warsztat: deska na całą scenę, przewijanie wewnątrz deski na niskich ekranach.
- Ruch: przejścia między scenami jak dziś (zoom 340 ms; reduced-motion bez).

- [ ] **Step 1:** CSS kontenera pełnoekranowego + pigułka + `.pets-stage`; router: 7 kluczy, adresy, etykiety powrotu, h1, noc w pigułce, tolerancja braku modułu sceny, przekierowanie starego `/szpital?pupil=`.
- [ ] **Step 2:** `scene-window.js` wg kontraktu + style „Okno sceny (v3.1)” w `modals.css` (light + dark, oba tryby, uchwyt 44 px, `prefers-reduced-motion`).
- [ ] **Step 3:** Domek: panel na `PetsSceneWindow`, pokój na całą scenę, spacer po `.pets-stage`, rezerwa przy otwartym oknie; etykieta wybranego pupila nad arkuszem przy 375 px (jak fix F3).
- [ ] **Step 4:** Mapa, warsztat, ogród na pełny ekran; ogród: szczegóły/album w oknie sceny, jeśli dziś są poza sceną.
- [ ] **Step 5:** Uruchom `venv/bin/python -m pytest tests/test_pets_swiat_trasy.py tests/test_pets_widget_companion.py tests/test_pets_routes.py -q -p no:cacheprovider` → zielone; `node --check` na każdym zmienionym pliku JS.
- [ ] **Step 6:** Weryfikacja w przeglądarce (podgląd SQLite: `venv/bin/python docs/dev/dev_pets_preview.py --repo <worktree> --port 5009 --scenario szpital --no-night`, logowanie `/dev-login`, przed sprawdzaniem wyrejestruj SW i wyczyść cache): 1313×1186, 1366×600, 1024, 768, 375×812, 812×375; light/dark; reduced-motion; każda scena bez przewijania strony; okno sceny w granicach sceny w obu trybach; Review Focus 1, 3 (domek: zmień stan z drugiej karty przy otwartym panelu), 5 (zwiń sidebar i przejdź przez 1024 px przy otwartym oknie); konsola bez błędów; brak poziomego scrolla.
- [ ] **Step 7:** Commity per krok (`feat(pupile): pelny ekran - …`), raport z rulingami i pomiarami.

---

### Task 5 (paczka F2 „Szpital” — subagent Opus w worktree, po Task 4): hol z recepcją, Inkubatorium, Izba przyjęć, linki

**Files:**
- Create: `static/js/pet/world/hospital-common.js` (formaty, tabliczki, wysyłka akcji szpitala, wspólne widoki okien), `static/js/pet/world/hospital-hall.js` (scena `szpital`), `static/js/pet/world/hospital-incubator.js` (scena `inkubatorium`), `static/js/pet/world/hospital-ward.js` (scena `izba`)
- Delete: `static/js/pet/world/hospital.js`
- Modify: `static/css/pages/client/pets-hospital.css` (sekcje: wspólne / hol / inkubatorium / izba; light + dark w każdej)
- Modify: `templates/client/pets/home.html` (skrypty: `hospital-common.js`, `hospital-hall.js`, `hospital-incubator.js`, `hospital-ward.js` zamiast `hospital.js`)
- Modify: `static/js/pet/world/house.js` („Zabierz do szpitala” → `ctx.go('izba', {pupil: id})`; linki „Przejdź do szpitala” → `izba`), `static/js/pet/world/map.js` (bez zmian logiki znaczka — tylko jeśli link szpitala wymaga), `static/js/components/pet-companion.js` (dymek „Do szpitala” dla chorego → `data-ward-url`), `static/js/pages/client/pets-widget.js` (pupil w szpitalu → `data-ward-url` + `?pupil=ID`; jajka w inkubacji → `data-incubator-url`; jajko do odebrania → `data-hospital-url`)
- Test: `tests/test_pets_swiat_trasy.py` (zmiana listy w `test_szablon_swiata_linkuje_sceny`)

**Interfaces:**
- Consumes: Task 4 (`PetsSceneWindow.attach`, `.pets-stage`, `.has-window`, klucze `inkubatorium`/`izba` w routerze, `ctx.href`/`ctx.go` z parametrami `pupil`/`jajko`), Task 1 (`data-ward-url`, `data-incubator-url`), istniejące: `PetRig.mount({species, stage, pose: 'bed', need})`, `PetRig.mountEgg({pct, boosted, ready, skin})`, `PetHatch.run({skin, hatch, onName, prevPets})`, `PetsState.eggForecast`, API: `POST /jajka/odbierz {source, pet_id?}`, `POST /jajka/<id>/ogrzej`, `POST /jajka/<id>/wykluj`, `POST /<id>/imie`, `POST /<id>/szpital`, `POST /<id>/wypis`, `POST /<id>/akcja {action:'pat', count}` (paczki pat w `pets.js` jak dziś).
- Produces: rejestracje `window.PetsWorld.scenes.szpital`, `.inkubatorium`, `.izba` (`{title: 'Szpital' | 'Inkubatorium' | 'Izba przyjęć', create(ctx, host)}`).

**Zachowanie (spec v3.1 §4):**
- Hol: drzwi Inkubatorium (lewe) i Izby przyjęć (prawe) jako `<a data-scene-link>` z szyldami; znaczki: Inkubatorium = liczba jajek `ready`; Izba = liczba `pet.hospital.ready` + liczba chorych w domku (`!pet.hospital && mood in ['chory','krytyczny']`); brak spraw = brak znaczka. Układ ≥ 600 px drzwi po bokach + recepcja pośrodku; < 600 px drzwi obok siebie u góry, recepcja pod nimi. Pielęgniarka: własna postać SVG (okrągła, czepek z krzyżykiem), nie gatunek pupila; mruga (reduced-motion: nie). Lada: jajko z kokardką na każdą pozycję `state.eggs_available` (zawijanie przy wielu); klik → okno sceny: źródło (teksty jak dziś: startowe/miesięczne/ratunkowe z imieniem/z prezentu), „Odbierz” → `POST /jajka/odbierz` → jajko leci do drzwi Inkubatorium (≤ 0,8 s; reduced-motion: bez lotu), okno zamyka się, toast jak dziś. Dymek pielęgniarki: jeden komunikat wg priorytetu spec §4.2 (1–6), jako link do właściwej sali, gdy dotyczy sali.
- Inkubatorium: inkubatory wg spec §4.3 (kopuła, lampa, `mountEgg` ze skórką, tabliczka `% · ~czas` z `PetsState.eggForecast`), stany wylęgane/ogrzane/gotowe/wolny, `max(3, n)` miejsc, siatka wg Global Constraints; klik → okno: źródło, pasek %, czas, ciepło, „Ogrzej” / „Wykluj” (→ `PetHatch.run`, po wykluciu przejście do domku z panelem nowego pupila jak dziś); klik w wolny → okno „Wolny inkubator — nowe jajka odbierzesz na recepcji” + link do holu; przy jajkach na ladzie tabliczka „Jajka do odebrania na recepcji →” przy drzwiach; `?jajko=ID` otwiera okno jajka (nieznany ID → bez okna, bez błędu).
- Izba przyjęć: łóżka wg spec §4.4 (`PetRig.mount` z `pose: 'bed'`, kroplówka przy leczonych, tabliczka „Imię · jeszcze ~N h”), wyzdrowiały: jaśniej, `need: 'happy'`, serduszka, zielona tabliczka „Zdrowy! Odbierz”; `max(3, n)` łóżek; klik w łóżko z pupilem → okno: imię, pasek zdrowia, czas / tęsknota, „Odbierz” albo „Zabierz wcześniej” z potwierdzeniem („Tak, zabieram” / „Zostaw w szpitalu”) — teksty jak dziś; klik w pupila przy otwartym oknie = pat (paczka pat jak dziś); wolne łóżko przy chorych w domku: pulsujący „+” (reduced-motion: statyczny), klik → okno „Kogo przyjąć?” (mini rig, imię, nastrój, „wyzdrowieje w najwyżej N h” z `state.config.hospital_hours`, „Przyjmij” → `POST /<id>/szpital` → pupil w łóżku, okno pokazuje jego); bez chorych → okno informacyjne; `?pupil=ID` otwiera okno pupila (pupil spoza szpitala/nieistniejący → bez okna, bez błędu). Po odbiorze → przejście do domku z panelem jak dziś.
- Zmiana stanu przy otwartym oknie (odświeżenie, inna karta): obiekt nadal istnieje → `win.replace` ze świeżą treścią; obiekt zniknął (jajko wyklute/odebrane, pupil odebrany/odszedł) → `win.close()` z fokusem na scenie.
- `aria-label` obiektów wg spec §6; Tab po drzwiach/inkubatorach/łóżkach/jajkach; Enter/Spacja otwiera okno.
- Mobile (< 1024 px): wybrany inkubator/łóżko/jajko zostaje widoczny nad arkuszem (przewinięcie wnętrza sceny do obiektu, jeśli trzeba).
- Błędy jak dziś (409 ciche odświeżenie, 410 toast + odświeżenie); GA4 `pet_hospital`/`pet_hatch` bez zmian.

- [ ] **Step 1: Test szablonu (RED)** — w `tests/test_pets_swiat_trasy.py::test_szablon_swiata_linkuje_sceny` zamień `'js/pet/world/hospital.js'` na cztery pliki `'js/pet/world/hospital-common.js'`, `'js/pet/world/hospital-hall.js'`, `'js/pet/world/hospital-incubator.js'`, `'js/pet/world/hospital-ward.js'` i dopisz `assert 'js/pet/world/hospital.js' not in html`; uruchom → FAIL.
- [ ] **Step 2:** `hospital-common.js` + hol z recepcją (odbiór jajek z lotem do drzwi), szablon linkuje nowe pliki (GREEN dla kroku 1), usunięcie `hospital.js`.
- [ ] **Step 3:** Inkubatorium (inkubatory, okno jajka, ogrzewanie, wyklucie, `?jajko=`).
- [ ] **Step 4:** Izba przyjęć (łóżka, okno pupila, odbiór/wcześniej, pat, przyjęcie z wolnego łóżka, `?pupil=`).
- [ ] **Step 5:** Linki: `house.js` (Zabierz do szpitala → `izba`), towarzysz (`data-ward-url`), widget (`data-ward-url`/`data-incubator-url`/`data-hospital-url`); `venv/bin/python -m pytest tests/test_pets_swiat_trasy.py tests/test_pets_widget_companion.py tests/test_pets_routes.py -q -p no:cacheprovider` → zielone; `node --check` na zmienionych plikach.
- [ ] **Step 6:** Weryfikacja w przeglądarce (podgląd jak w Task 4, `--scenario szpital`; centrala dopisze w seedzie jajka do odebrania i scenariusz z wieloma obiektami przed startem paczki): hol → odbiór każdego rodzaju jajka (lot do drzwi, znaczek), Inkubatorium → Ogrzej, Wykluj (nazwa, przejście do domku), Izba → Odbierz, Zabierz wcześniej (potwierdzenie), pat w łóżku, przyjęcie z wolnego łóżka; Review Focus 1–4 (niski widok, wiele obiektów, zmiana stanu z drugiej karty, złe linki: `izba-przyjec?pupil=999`, `inkubatorium?jajko=abc`, `/szpital?pupil=<pupil w domku>`); Wstecz/Dalej; 1313, 1024, 375, 812×375; light/dark; reduced-motion; konsola czysta; cele ≥ 44 px.
- [ ] **Step 7:** Commity per krok (`feat(pupile): szpital - …`), raport z rulingami i pomiarami.

---

### Task 6 (centrala): integracja, podgląd, recenzja, raport

- [ ] **Step 1 (przed Task 4):** Rozszerz `docs/dev/dev_pets_preview.py` (gitignored): w scenariuszu `szpital` dodaj jajka do odebrania (miesięczne dostępne: ustaw licznik miesięcznego profilu na „już można”, plus 1 jajko z prezentu przez licznik `granted`); nowy scenariusz `tlum`: 6 jajek w inkubacji (różne skórki, jedno gotowe, jedno ogrzane), 7 pupili w szpitalu (różny postęp, 2 wyleczone), 1 chory w domku, 3 jajka do odebrania. Wpisy `pets-preview-*` w lokalnym `.claude/launch.json` dla worktree paczek (nie commitować).
- [ ] **Step 2:** Scal paczki F1 i F2 (`--no-ff`); bump `CACHE_VERSION` w `static/sw.js` (`thunderorders-v30` → `v31`).
- [ ] **Step 3:** Pełna suita: `venv/bin/python -m pytest -q --no-header -p no:cacheprovider --deselect tests/test_mobile_api_auth.py::test_logout_stores_expiry_in_local_time_and_purges_expired > $SP/full.txt 2>&1; echo "exit=$?"; tail -3 $SP/full.txt` → Expected: `exit=0`, 0 failed.
- [ ] **Step 4:** Własna weryfikacja w przeglądarce na scalonym kodzie (scenariusze `szpital` i `tlum`): ścieżka gracza mapa → domek (okno) → szpital (hol, odbiór) → Inkubatorium (Ogrzej, Wykluj) → Izba (przyjęcie, odbiór) → warsztat → ogród; push z `flask pets tick --dry-run` na bazie podglądu prowadzi do właściwej sali; 1313 / 375 / dark / noc.
- [ ] **Step 5:** Świeża recenzja frontendu (Opus) zakresu od commita Task 1; fix pass Critical/Important (repro w przeglądarce, test tam, gdzie się da); minory do raportu.
- [ ] **Step 6:** Pamięć projektu, ClickUp 869ffdb58 (komentarz), raport dla Konrada „Sprawdź i zobacz swoje jajko” (jak włączyć podgląd, co przeklikać, rulingi, odroczone). Bez pusha.
