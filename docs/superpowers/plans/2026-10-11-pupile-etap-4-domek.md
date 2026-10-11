# Pupile — Etap 4 (strona domku + rig SVG) — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pierwsza rzecz, którą klient zobaczy: strona „Moje pupile" (`/client/pupile`) z gniazdkiem,
domkiem, albumem i ustawieniami towarzysza, JSON API nad gotowym serwisem, modal wyklucia, rig SVG
z ośmioma gatunkami i animacjami, haptyka, nawigacja widoczna tylko dla użytkowników z włączoną
funkcją. Po tym etapie da się grać od jajka startowego do dorosłego pupila — lokalnie, przed
włączeniem flagi na produkcji.

**Architecture:** Trzy paczki o rozłącznych plikach. **A (backend)**: `modules/pets/routes.py`
(strona + API, mapowanie `PetError` → JSON, limiter per użytkownik, 404 gdy funkcja niedostępna),
context processor `pets_enabled`, pozycje w nawigacji, minimalny szkielet `home.html`, testy tras.
**B (rig)**: `static/js/pet/species.js` + `static/js/components/pet-rig.js` + `static/css/components/pet-rig.css`
— jedna struktura warstw SVG, 8 gatunków jako kształty + palety, stadia jako proporcje, animacje
jako klasy CSS, jajko i karta pamięci; strona demo do wizualnej iteracji. **C (UI strony)**:
`pets.js` (render z JSON-a stanu, akcje, ekstrapolacja pasków, paczki pat pat, modal wyklucia,
odznaki od razu, haptyka), `pet-card.js/css` (karta pełna i mini — ta sama dla dashboardu w etapie 5),
`pets.css`, style modalu w `modals.css`, ikona łapki, bump `CACHE_VERSION`. **Integracja (centrala)**:
scalanie, lokalny podgląd na SQLite z zasianymi pupilami, weryfikacja w przeglądarce (light/dark,
telefon), poprawki, recenzja. Jedno źródło prawdy renderowania = JS z `data-state`; serwer daje
JSON (SSR tylko szkielet + `<noscript>`), żeby nie dublować logiki stanu w Jinja i JS.

**Tech Stack:** Flask 3 (blueprint `pets_bp`, `limiter`, `login_required`), Jinja2, vanilla JS
(IIFE, bez bundlera), CSS z `static/css/core/variables.css` + `[data-theme="dark"]`, inline SVG,
pytest (trasy), weryfikacja wizualna w przeglądarce (brak runnera JS).

**Spec:** `docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md` (§3.5, §4.1–4.6, §6, §8).

## Global Constraints

- Gałąź `feat/pupile` (HEAD po etapie 3: `d5db042c` + ewentualne poprawki po recenzji). Paczki B i C
  startują z gałęzi po scaleniu paczki A (szkielet `home.html` i API muszą istnieć).
- Testy: `venv/bin/python -m pytest …` (nigdy gołe `pytest`); wynik z pliku/`$?`, nie `| tail`.
  Znana porażka spoza gałęzi: `test_mobile_api_auth.py::test_logout_stores_expiry_in_local_time_and_purges_expired`.
- **Żadnego CSS/JS inline w szablonach** poza `data-*` i `style="width: X%"` dla wartości dynamicznych.
  CSS w `static/css/pages/client/` i `static/css/components/`, JS w `static/js/pages/client/`,
  `static/js/components/`, `static/js/pet/`, `static/js/utils/`. **Style modalu wyłącznie w
  `static/css/components/modals.css`** (sekcja `/* === Pet hatch modal === */`).
- **Każda reguła CSS ma wariant dark** (`[data-theme="dark"] …`); paleta glass z `CLAUDE.md`
  (tła `rgba(255,255,255,0.05–0.1)`, obramowania `rgba(240,147,251,0.15–0.3)`, akcent `#f093fb`).
  Używaj zmiennych z `static/css/core/variables.css` (`--bg-primary`, `--text-primary`, `--card-bg`,
  `--card-border`, `--radius-lg`, `--shadow-md`, `--space-*`, `--text-*`). Breakpointy jak reszta
  klienta: `max-width` 1024 / 768 / 480.
- **Dotyk ≥ 44 px** dla każdego interaktywnego elementu na mobile. `prefers-reduced-motion: reduce`
  → bez spaceru/podskoków/wibracji (statyczna poza).
- Pułapki z repo: `.btn:disabled { pointer-events: none }` — powód niedostępności akcji pokazuj
  tekstem pod przyciskiem, nie `title`; `window.showToast` wstawia HTML bez escapowania — imiona
  pupili zawsze przez własny `escapeHtml` (textContent → innerHTML) i **nigdy w inline `onclick`**
  (lekcja z pamięci: delegacja zdarzeń + `data-*`); `dashboard.html`/`contest.html` nadpisują
  `extra_css` bez `super()` — `home.html` ma użyć `{{ super() }}`; `popups-all-closed` nie emituje
  przy błędzie → fallback `setTimeout(5000)`; `AchievementUnlock.show()` chce obiektów odznak —
  po wykluciu wyczyść `sessionStorage['achievements_last_check']`, pobierz `/achievements/api/unseen`
  i dopiero pokaż; globalny `#modal-overlay` w `base.html` — modal wyklucia ma własne id.
- Konwencja JSON API pupili: `{ok: true, …}` / `{ok: false, error: '<kod>', message: '<po polsku>'}`
  ze statusem HTTP z `PetError.status` (spec §3.5). Bramka funkcji: `pets_feature_for(current_user)`
  → inaczej **404** (strona i API). Limiter: `120 per minute`, `key_func` = id użytkownika.
- Język: „odszedł do gwiazd" w zdaniach z podmiotem „Pupil {imię}". Komunikaty po polsku.
- Commity ASCII `feat(pupile): …`, `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
  **Nie pushować.**

## Review Focus

1. **Użytkownik bez `profile_completed`** wchodzi na `/client/pupile` — bramka `client_bp` go nie
   obejmuje; strona ma działać normalnie (gra nie wymaga adresu), ale nic nie może się wysypać na
   `None` w imieniu/nazwisku (Task 1 test).
2. **Odpowiedź nie-JSON na wywołanie API** (302 na login po wygaśnięciu sesji, 500 HTML, 429) → front
   pokazuje czytelny toast i nie zostawia przycisku w stanie „ładowanie" (Task 3, weryfikacja ręczna +
   Task 1 test na JSON 429/404 w obrębie `/client/pupile/api/`).
3. **Dwa szybkie kliknięcia „Nakarm"** → drugi dostaje 409 `najedzony` i UI tylko odświeża stan, bez
   podwójnego toastu błędu (Task 3; Task 1 test sekwencyjny 200 → 409).
4. **Imię z emoji/ZWJ albo > 20 znaków** w modalu → 400 z komunikatem przy polu, modal zostaje otwarty,
   pupil już wykluty (Task 1 test; Task 3 obsługa).
5. **Karta w trybie ciemnym na telefonie 375 px**: paski, przyciski (≥ 44 px) i nagrobek czytelne,
   bez poziomego scrolla (Task 4 weryfikacja wizualna z zrzutami).

---

### Task 1 (paczka A — backend, model Opus 5.5): trasy, API, bramka, nawigacja, szkielet strony

**Files:**
- Create: `modules/pets/routes.py`
- Modify: `modules/pets/__init__.py` (import `routes`)
- Modify: `app.py` `register_context_processors` → `inject_globals` (ok. :1915-1930): `pets_enabled`
- Modify: `templates/components/sidebar_client.html` (między Osiągnięciami a Konkursem),
  `templates/components/bottom_bar_client.html` (po Osiągnięciach w arkuszu „więcej")
- Create: `templates/client/pets/home.html` (**szkielet** — paczka C go rozbuduje)
- Create: `static/img/icons/paw.svg`
- Test: `tests/test_pets_routes.py`

**Interfaces:**
- Consumes: `modules.pets.service` (`claim_egg`, `warm_egg`, `hatch_egg`, `perform_action`,
  `light_candle`, `rename_pet`, `set_companion`, `state_for_user`, `PetError`),
  `modules.pets.config.pets_feature_for`, `modules.pets.species.SPECIES_BY_SLUG`,
  `extensions.limiter`.
- Produces (kontrakt dla paczki C):
  - `GET /client/pupile` → `client/pets/home.html` z `state_json` (JSON `state_for_user`),
    `species_json` (JSON `{slug: {name, palette, extras}}`), `api_base='/client/pupile/api'`.
    Szkielet renderuje `<div id="petsApp" data-state="…" data-species="…" data-api="…">`.
  - `GET /client/pupile/api/stan[?lite=1]` → stan (`ok: true` + klucze ze spec §3.5).
  - `POST /client/pupile/api/jajka/odbierz` `{source, pet_id?}` → `{ok, state}`.
  - `POST /client/pupile/api/jajka/<id>/ogrzej` → `{ok, state}`.
  - `POST /client/pupile/api/jajka/<id>/wykluj` → `{ok, result: 'new'|'dupe', species, species_name,
    pet_id, starred_pet_id, new_achievements: [slug…], state}`.
  - `POST /client/pupile/api/<id>/akcja` `{action, count?}` → `{ok, accepted, first_care_today,
    new_achievements, state}`.
  - `POST /client/pupile/api/<id>/swiatelko` → `{ok, lights_count, state}`.
  - `POST /client/pupile/api/<id>/imie` `{name}` → `{ok, name, state}`.
  - `POST /client/pupile/api/towarzysz` `{pet_id|null, enabled}` → `{ok, state}`.
  - Błędy: `{ok: false, error, message}` + status (`PetError.status`; 400 `bad_request` dla złego
    JSON/id; 404 `not_found` dla nieistniejących ścieżek pod `/client/pupile/api/`; 429
    `rate_limited`).
  - Szablony: zmienna globalna `pets_enabled` (bool) w każdym szablonie.

- [ ] **Step 1: Failujące testy**

```python
# tests/test_pets_routes.py
"""Trasy pupili: bramka funkcji (404), strona, API i mapowanie błędów na JSON (spec §3.5, §6)."""
import json
from datetime import timedelta

import pytest
from flask import url_for

from tests.pets_helpers import zaloz_profil, zaloz_pupila, zaloz_zmarlego, zaloz_jajko


def _wlacz(db, pct=100):
    from modules.auth.models import Settings
    from modules.pets.config import reset_feature_cache
    Settings.set_value('pets_enabled', 'true', type='boolean')
    Settings.set_value('pets_rollout_pct', pct, type='integer')
    db.session.commit()
    reset_feature_cache()


def _teraz():
    from modules.auth.models import get_local_now
    return get_local_now()


@pytest.fixture
def gracz(db, make_user, login):
    """Zalogowany klient z włączoną funkcją; bez profilu (startowe jajko wirtualne)."""
    user = make_user()
    login(user)
    _wlacz(db)
    return user


# --- bramka ---

def test_flaga_wylaczona_strona_i_api_404(client, login, make_user):
    user = make_user()
    login(user)
    assert client.get('/client/pupile').status_code == 404
    r = client.get('/client/pupile/api/stan')
    assert r.status_code == 404 and r.get_json()['error'] == 'not_found'


def test_rollout_po_user_id(client, login, make_user, db):
    user = make_user()
    login(user)
    _wlacz(db, pct=0)
    assert client.get('/client/pupile').status_code == 404
    _wlacz(db, pct=100)
    assert client.get('/client/pupile').status_code == 200


def test_niezalogowany_przekierowanie(client, db):
    r = client.get('/client/pupile')
    assert r.status_code == 302 and '/auth/login' in r.headers['Location']


def test_nawigacja_pokazuje_pupile_tylko_z_flaga(app, client, login, make_user, db):
    user = make_user(profile_completed=True)
    login(user)
    with app.test_request_context():
        link = url_for('pets.home').encode()
    r = client.get('/client/dashboard')
    assert r.status_code == 200 and link not in r.data
    _wlacz(db)
    r = client.get('/client/dashboard')
    assert r.status_code == 200 and link in r.data
    assert b'petsNavDot' in r.data and b'paw.svg' in r.data


# --- strona ---

def test_strona_szkielet_z_data_state(client, gracz):
    r = client.get('/client/pupile')
    assert r.status_code == 200
    html = r.data.decode()
    assert 'id="petsApp"' in html and 'data-state=' in html and 'data-species=' in html
    assert 'data-api="/client/pupile/api"' in html
    assert 'css/pages/client/pets.css' in html and 'js/pages/client/pets.js' in html
    assert 'js/pet/species.js' in html and 'js/components/pet-rig.js' in html and 'js/components/pet-card.js' in html
    assert 'css/layouts/client-layout.css' in html     # {{ super() }} w extra_css


def test_strona_bez_profile_completed_dziala(client, db, make_user, login):
    """Review Focus 1: bramka profilu z client_bp nie obejmuje pets_bp — i tak ma działać."""
    user = make_user(profile_completed=False, first_name=None, last_name=None)
    login(user)
    _wlacz(db)
    assert client.get('/client/pupile').status_code == 200


# --- API: stan i jajka ---

def test_api_stan_ksztalt(client, gracz):
    r = client.get('/client/pupile/api/stan')
    assert r.status_code == 200
    s = r.get_json()
    assert s['ok'] is True
    for klucz in ('now', 'night', 'eggs_available', 'next_monthly_at', 'eggs', 'pets', 'album', 'companion', 'needs_care'):
        assert klucz in s, klucz
    assert s['eggs_available'] == [{'source': 'start'}] and len(s['album']) == 8


def test_api_stan_lite_bez_albumu(client, gracz):
    s = client.get('/client/pupile/api/stan?lite=1').get_json()
    assert s['ok'] is True and 'album' not in s


def test_odbierz_startowe_ogrzej_wykluj_imie(client, gracz, db, monkeypatch):
    from modules.pets import eggs as eggs_mod
    from modules.pets.models import Pet
    from tests.pets_helpers import RngStaly
    r = client.post('/client/pupile/api/jajka/odbierz', json={'source': 'start'})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    jajko = Pet.query.filter_by(user_id=gracz.id).one()
    assert jajko.status == 'egg' and jajko.egg_hours == 48
    r = client.post(f'/client/pupile/api/jajka/{jajko.id}/ogrzej', json={})
    assert r.status_code == 200 and r.get_json()['state']['eggs'][0]['can_warm'] is False
    r = client.post(f'/client/pupile/api/jajka/{jajko.id}/ogrzej', json={})
    assert r.status_code == 409 and r.get_json() == {'ok': False, 'error': 'boost_active',
                                                     'message': 'Jajko jest już ogrzane — poczekaj, aż ciepło się skończy.'}
    r = client.post(f'/client/pupile/api/jajka/{jajko.id}/wykluj', json={})
    assert r.status_code == 409 and r.get_json()['error'] == 'egg_not_ready'
    jajko.egg_progress_sec = 48 * 3600
    db.session.commit()
    monkeypatch.setattr(eggs_mod, 'rng_or', lambda rng: RngStaly('mis'))
    r = client.post(f'/client/pupile/api/jajka/{jajko.id}/wykluj', json={})
    dane = r.get_json()
    assert r.status_code == 200 and dane['result'] == 'new' and dane['species'] == 'mis'
    assert dane['species_name'] == 'Miś' and dane['pet_id'] == jajko.id and dane['starred_pet_id'] is None
    assert dane['new_achievements'] == [] and dane['state']['pets'][0]['name'] == 'Miś'
    r = client.post(f'/client/pupile/api/{jajko.id}/imie', json={'name': '  Puchatek '})
    assert r.status_code == 200 and r.get_json()['name'] == 'Puchatek'


def test_imie_zle_400_z_komunikatem(client, gracz, db):
    """Review Focus 4."""
    zaloz_profil(gracz)
    pet = zaloz_pupila(gracz, now=_teraz())
    r = client.post(f'/client/pupile/api/{pet.id}/imie', json={'name': 'a' * 21})
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_name'
    assert 'od 1 do 20' in r.get_json()['message']
    assert client.post(f'/client/pupile/api/{pet.id}/imie', json={'name': '🐱 Kot'}).status_code == 200


# --- API: akcje ---

def test_akcja_nakarm_i_drugi_klik_409(client, gracz, db):
    """Review Focus 3."""
    zaloz_profil(gracz)
    pet = zaloz_pupila(gracz, hunger=20.0, now=_teraz() - timedelta(minutes=1))
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'feed'})
    assert r.status_code == 200
    dane = r.get_json()
    assert dane['ok'] is True and dane['accepted'] == 1 and dane['first_care_today'] is True
    assert dane['state']['pets'][0]['bars']['hunger'] >= 69.9
    client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'feed'})      # druga miseczka → 100
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'feed'})
    assert r.status_code == 409 and r.get_json()['error'] == 'not_available' and r.get_json()['message'] == 'najedzony'


def test_akcja_pat_z_count_i_bez(client, gracz, db):
    zaloz_profil(gracz)
    pet = zaloz_pupila(gracz, fun=10.0, now=_teraz() - timedelta(minutes=1))
    assert client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'pat', 'count': 7}).get_json()['accepted'] == 7
    assert client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'pat'}).get_json()['accepted'] == 1
    assert client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'pat', 'count': 'abc'}).get_json()['accepted'] == 1


def test_akcja_na_cudzym_403_nieznana_400_nieistniejacy_404(client, gracz, db, make_user):
    zaloz_profil(gracz)
    inny = make_user()
    zaloz_profil(inny)
    cudzy = zaloz_pupila(inny, now=_teraz())
    r = client.post(f'/client/pupile/api/{cudzy.id}/akcja', json={'action': 'feed'})
    assert r.status_code == 403 and r.get_json()['error'] == 'forbidden'
    pet = zaloz_pupila(gracz, now=_teraz())
    assert client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'tickle'}).status_code == 400
    assert client.post('/client/pupile/api/999999/akcja', json={'action': 'feed'}).status_code == 404
    r = client.post('/client/pupile/api/abc/akcja', json={'action': 'feed'})
    assert r.status_code == 404 and r.get_json()['error'] == 'not_found'   # zły segment ścieżki pod /api/
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', data='nie-json', content_type='text/plain')
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_request'


def test_akcja_na_odeszlym_410(client, gracz, db):
    zaloz_profil(gracz)
    pet = zaloz_pupila(gracz, hunger=0.0, now=_teraz() - timedelta(hours=80))
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'feed'})
    assert r.status_code == 410 and r.get_json()['error'] == 'pet_gone'
    assert 'odszedł do gwiazd' in r.get_json()['message']


def test_swiatelko_i_towarzysz(client, gracz, db):
    profil = zaloz_profil(gracz)
    zywy = zaloz_pupila(gracz, now=_teraz())
    zmarly = zaloz_zmarlego(gracz, died_at=_teraz() - timedelta(days=1))
    r = client.post(f'/client/pupile/api/{zmarly.id}/swiatelko', json={})
    assert r.status_code == 200 and r.get_json()['lights_count'] == 1
    assert client.post(f'/client/pupile/api/{zmarly.id}/swiatelko', json={}).status_code == 409
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': zywy.id, 'enabled': False})
    assert r.status_code == 200 and r.get_json()['state']['companion'] == {'enabled': False, 'pet_id': zywy.id, 'auto': False}
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': 'x', 'enabled': True})
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_request'


def test_ratunkowe_wymaga_pet_id_int(client, gracz, db):
    zaloz_profil(gracz)
    zmarly = zaloz_zmarlego(gracz, died_at=_teraz() - timedelta(hours=1))
    assert client.post('/client/pupile/api/jajka/odbierz', json={'source': 'rescue', 'pet_id': [1]}).status_code == 400
    r = client.post('/client/pupile/api/jajka/odbierz', json={'source': 'rescue', 'pet_id': str(zmarly.id)})
    assert r.status_code == 200


def test_limiter_120_na_minute_per_uzytkownik(app, client, gracz, db, monkeypatch):
    """Precedens fixture: tests/test_mobile_api_auth.py:469-479 (RATELIMIT_ENABLED w TestingConfig jest False)."""
    from extensions import limiter
    monkeypatch.setitem(app.config, 'RATELIMIT_ENABLED', True)
    limiter.enabled = True
    try:
        limiter.reset()
        zaloz_profil(gracz)
        pet = zaloz_pupila(gracz, fun=0.0, now=_teraz())
        kody = [client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'pat'}).status_code for _ in range(121)]
        assert kody[:120] == [200] * 120 and kody[120] == 429
        r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'pat'})
        assert r.get_json()['error'] == 'rate_limited'
    finally:
        limiter.enabled = False
        limiter.reset()


def test_lite_nie_zapisuje_odejscia_pelny_zapisuje(client, gracz, db):
    zaloz_profil(gracz)
    pet = zaloz_pupila(gracz, hunger=0.0, now=_teraz() - timedelta(hours=80))
    client.get('/client/pupile/api/stan?lite=1')
    db.session.expire_all()
    assert pet.status == 'alive'
    client.get('/client/pupile/api/stan')
    db.session.expire_all()
    assert pet.status == 'dead'
```

- [ ] **Step 2: Uruchom — mają paść**

Run: `venv/bin/python -m pytest tests/test_pets_routes.py -q`
Expected: wszystkie FAIL (404 bez `error` JSON, `BuildError: pets.home`, brak szablonu).

- [ ] **Step 3: `routes.py`**

```python
# modules/pets/routes.py
"""Strona „Moje pupile" i JSON API nad serwisem (spec §3.5, §6).

- bramka: funkcja niedostępna dla użytkownika (flaga/rollout) → 404 — i strona, i API;
- każdy błąd domenowy (PetError) → {ok: false, error, message} ze statusem PetError.status;
- pod /client/pupile/api/ także 400/404/429 są JSON-em (front nie parsuje HTML);
- limiter 120/min per użytkownik (nie per IP — paczki pat pat kilku osób za NAT-em).
"""
import json
from functools import wraps

from flask import abort, jsonify, render_template, request
from flask_limiter.util import get_remote_address
from flask_login import current_user, login_required

from extensions import limiter
from modules.pets import pets_bp, service
from modules.pets.config import pets_feature_for
from modules.pets.errors import PetError
from modules.pets.species import SPECIES

API_PREFIX = '/client/pupile/api'
API_BASE = API_PREFIX


def _klucz_limitera():
    return str(current_user.id) if current_user.is_authenticated else get_remote_address()


def _api_path():
    return request.path.startswith(API_PREFIX)


def _json_err(code, message, status):
    return jsonify({'ok': False, 'error': code, 'message': message}), status


def feature_required(fn):
    """404, gdy pupile nie są dostępne dla tego użytkownika (flaga / rollout)."""
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not pets_feature_for(current_user):
            abort(404)
        return fn(*args, **kwargs)
    return wrapper


@pets_bp.errorhandler(PetError)
def _pet_error(e):
    return _json_err(e.code, e.message, e.status)


@pets_bp.errorhandler(404)
def _not_found(e):
    if _api_path():
        return _json_err('not_found', 'Nie znaleziono.', 404)
    return e   # strona: standardowa 404 aplikacji


@pets_bp.errorhandler(429)
def _rate_limited(e):
    if _api_path():
        return _json_err('rate_limited', 'Za dużo żądań — odczekaj chwilę.', 429)
    return e


@pets_bp.errorhandler(400)
def _bad_request(e):
    if _api_path():
        return _json_err('bad_request', 'Nieprawidłowe dane żądania.', 400)
    return e


def _body():
    dane = request.get_json(silent=True)
    if dane is None:
        if request.data and request.data.strip():
            raise PetError('bad_request', 'Nieprawidłowe dane żądania.', 400)
        return {}
    if not isinstance(dane, dict):
        raise PetError('bad_request', 'Nieprawidłowe dane żądania.', 400)
    return dane


def _int_or_none(value, pole):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise PetError('bad_request', f'Nieprawidłowe pole {pole}.', 400)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise PetError('bad_request', f'Nieprawidłowe pole {pole}.', 400)


def _state(lite=False):
    return service.state_for_user(current_user._get_current_object(), lite=lite)


def _species_json():
    return json.dumps({s.slug: {'name': s.name, 'palette': s.palette, 'extras': list(s.extras)} for s in SPECIES},
                      ensure_ascii=False)


# ---------------------------------------------------------------------------
# Strona
# ---------------------------------------------------------------------------

@pets_bp.route('/')
@feature_required
def home():
    stan = _state()
    return render_template(
        'client/pets/home.html',
        title='Moje pupile',
        state_json=json.dumps(stan, ensure_ascii=False),
        species_json=_species_json(),
        api_base=API_BASE,
    )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pets_bp.route('/api/stan')
@feature_required
def api_state():
    lite = request.args.get('lite') in ('1', 'true', 'yes')
    return jsonify(_state(lite=lite))


@pets_bp.route('/api/jajka/odbierz', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_claim_egg():
    dane = _body()
    source = dane.get('source')
    if not isinstance(source, str):
        raise PetError('bad_request', 'Nieprawidłowe pole source.', 400)
    pet_id = _int_or_none(dane.get('pet_id'), 'pet_id')
    service.claim_egg(current_user._get_current_object(), source, pet_id=pet_id)
    return jsonify({'ok': True, 'state': _state()})


@pets_bp.route('/api/jajka/<int:pet_id>/ogrzej', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_warm_egg(pet_id):
    service.warm_egg(current_user._get_current_object(), pet_id)
    return jsonify({'ok': True, 'state': _state()})


@pets_bp.route('/api/jajka/<int:pet_id>/wykluj', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_hatch_egg(pet_id):
    from modules.pets.species import SPECIES_BY_SLUG
    wynik = service.hatch_egg(current_user._get_current_object(), pet_id)
    gatunek = SPECIES_BY_SLUG.get(wynik['species'])
    return jsonify({
        'ok': True,
        'result': wynik['result'],
        'species': wynik['species'],
        'species_name': gatunek.name if gatunek else wynik['species'],
        'pet_id': wynik['pet'].id,
        'starred_pet_id': wynik['starred_pet'].id if wynik['starred_pet'] is not None else None,
        'new_achievements': wynik['new_achievements'],
        'state': _state(),
    })


@pets_bp.route('/api/<int:pet_id>/akcja', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_action(pet_id):
    dane = _body()
    action = dane.get('action')
    if not isinstance(action, str):
        raise PetError('bad_action', 'Nieznana akcja.', 400)
    wynik = service.perform_action(current_user._get_current_object(), pet_id, action, count=dane.get('count', 1))
    return jsonify({
        'ok': True,
        'accepted': wynik['accepted'],
        'first_care_today': wynik['first_care_today'],
        'new_achievements': wynik['new_achievements'],
        'state': _state(),
    })


@pets_bp.route('/api/<int:pet_id>/swiatelko', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_light_candle(pet_id):
    pet = service.light_candle(current_user._get_current_object(), pet_id)
    return jsonify({'ok': True, 'lights_count': int(pet.lights_count), 'state': _state()})


@pets_bp.route('/api/<int:pet_id>/imie', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_rename(pet_id):
    dane = _body()
    pet = service.rename_pet(current_user._get_current_object(), pet_id, dane.get('name'))
    return jsonify({'ok': True, 'name': pet.name, 'state': _state()})


@pets_bp.route('/api/towarzysz', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_companion():
    dane = _body()
    pet_id = _int_or_none(dane.get('pet_id'), 'pet_id')
    service.set_companion(current_user._get_current_object(), pet_id=pet_id, enabled=bool(dane.get('enabled', True)))
    return jsonify({'ok': True, 'state': _state()})
```

W `modules/pets/__init__.py` po imporcie `models` dodaj `from . import routes  # noqa: E402,F401`.
Uwaga do `_not_found`: Flask przekazuje do `errorhandler(404)` wyjątek `NotFound`; zwrócenie `e`
oddaje go dalej do globalnego handlera 404 (HTML) — sprawdź w teście `test_flaga_wylaczona_strona_i_api_404`,
że strona daje zwykłe 404, a API JSON. Jeśli `return e` nie działa w Twojej wersji Flaska, zwróć
`render_template('errors/404.html'), 404` (szablon istnieje w `templates/errors/`).

- [ ] **Step 4: Context processor, nawigacja, ikona, szkielet strony**

`app.py` — w `inject_globals` (ok. :1915) dołóż klucz:

```python
    def _pets_enabled():
        try:
            from flask_login import current_user
            from modules.pets.config import pets_feature_for
            return pets_feature_for(current_user)
        except Exception:   # noqa: BLE001 — np. render poza żądaniem (maile z CLI)
            return False
    ...
    return {
        ...,
        'pets_enabled': _pets_enabled(),
    }
```

(Jeśli `inject_globals` buduje słownik wprost — dopisz `'pets_enabled': _pets_enabled()` do niego;
funkcję zdefiniuj wewnątrz `register_context_processors`.)

`templates/components/sidebar_client.html` — między pozycją Osiągnięcia a Konkurs:

```jinja
            {% if pets_enabled %}
            <li class="sidebar-item">
                <a href="{{ url_for('pets.home') }}"
                   class="sidebar-link {% if request.endpoint and request.endpoint.startswith('pets.') %}active{% endif %}"
                   data-tooltip="Moje pupile">
                    <img src="{{ url_for('static', filename='img/icons/paw.svg') }}" alt="Moje pupile" class="sidebar-icon">
                    <span class="sidebar-text">Moje pupile</span>
                    <span class="sidebar-dot" id="petsNavDot" hidden aria-label="Pupil potrzebuje opieki"></span>
                </a>
            </li>
            {% endif %}
```

`templates/components/bottom_bar_client.html` — w `<template id="pwaSheetClientMore">` po pozycji Osiągnięcia:

```jinja
        {% if pets_enabled %}
        <li>
            <a href="{{ url_for('pets.home') }}" class="pwa-sheet-item {% if request.endpoint and request.endpoint.startswith('pets.') %}active{% endif %}">
                <img src="{{ url_for('static', filename='img/icons/paw.svg') }}" alt="" class="pwa-sheet-icon">
                <span>Moje pupile</span>
                <span class="pwa-sheet-badge pets-sheet-dot" id="pwaSheetPetsDot" style="display:none;">•</span>
            </a>
        </li>
        {% endif %}
```

`static/img/icons/paw.svg` (styl jak `achievements.svg`: 24×24, stroke `currentColor`):

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="15.5" rx="4.5" ry="3.5"/><circle cx="6" cy="10" r="1.6"/><circle cx="18" cy="10" r="1.6"/><circle cx="9" cy="6" r="1.6"/><circle cx="15" cy="6" r="1.6"/></svg>
```

Styl kropki w sidebarze — **nie dopisuj CSS inline**; dodaj do `static/css/pages/client/pets.css`
(plik tworzy paczka C; w paczce A załóż go z samą regułą kropki, C go rozbuduje):

```css
/* Kropka „pupil potrzebuje opieki" przy pozycji w nawigacji (ustawia JS z api/stan) */
.sidebar-dot { position: absolute; top: 10px; right: 12px; width: 8px; height: 8px; border-radius: 50%; background: #f5576c; box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9); }
.sidebar-dot[hidden] { display: none; }
[data-theme="dark"] .sidebar-dot { box-shadow: 0 0 0 2px rgba(21, 18, 28, 0.9); }
.pets-sheet-dot { background: #f5576c; color: #fff; }
```

i podepnij `pets.css` w `base_client.html`? **Nie** — sidebar jest na każdej stronie klienta, a
`pets.css` ładuje tylko strona pupili. Regułę kropki umieść w `static/css/components/pet-companion.css`
(plik etapu 5 — załóż go teraz z tą jedną regułą) i dołącz go w `templates/client/base_client.html`
w bloku `extra_css` obok `client-layout.css`.

`templates/client/pets/home.html` (szkielet; paczka C rozbuduje sekcje):

```jinja
{% extends "client/base_client.html" %}

{% block extra_css %}
{{ super() }}
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/pet-rig.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/pet-card.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/client/pets.css') }}">
{% endblock %}

{% block content %}
<div id="petsApp" class="pets-page"
     data-state='{{ state_json | e }}'
     data-species='{{ species_json | e }}'
     data-api="{{ api_base }}">
    <header class="pets-page__header">
        <h1 class="pets-page__title">Moje pupile</h1>
    </header>
    <section id="petsNest" class="pets-section pets-section--nest" aria-labelledby="petsNestTitle">
        <h2 id="petsNestTitle" class="pets-section__title">Gniazdko</h2>
        <div class="pets-section__body"></div>
    </section>
    <section id="petsHome" class="pets-section pets-section--home" aria-labelledby="petsHomeTitle">
        <h2 id="petsHomeTitle" class="pets-section__title">Domek</h2>
        <div class="pets-section__body pets-grid"></div>
    </section>
    <section id="petsAlbum" class="pets-section pets-section--album" aria-labelledby="petsAlbumTitle">
        <h2 id="petsAlbumTitle" class="pets-section__title">Album <span class="pets-album__count"></span></h2>
        <div class="pets-section__body pets-album"></div>
    </section>
    <section id="petsSettings" class="pets-section pets-section--settings" aria-labelledby="petsSettingsTitle">
        <h2 id="petsSettingsTitle" class="pets-section__title">Towarzysz i powiadomienia</h2>
        <div class="pets-section__body"></div>
    </section>
    <noscript><p class="pets-noscript">Do opieki nad pupilem potrzebny jest włączony JavaScript.</p></noscript>
</div>
{% endblock %}

{% block extra_js %}
<script src="{{ url_for('static', filename='js/utils/haptics.js') }}"></script>
<script src="{{ url_for('static', filename='js/pet/species.js') }}"></script>
<script src="{{ url_for('static', filename='js/components/pet-rig.js') }}"></script>
<script src="{{ url_for('static', filename='js/components/pet-card.js') }}"></script>
<script src="{{ url_for('static', filename='js/pages/client/pets.js') }}"></script>
{% endblock %}
```

- [ ] **Step 5: Uruchom — mają przejść**

Run: `venv/bin/python -m pytest tests/test_pets_routes.py -q`
Expected: `18 passed`. Pułapki: `url_for('pets.home')` wymaga importu `routes` w `__init__`;
test nawigacji wymaga `profile_completed=True` (dashboard ma bramkę); JSON 404 dla `/api/abc/akcja`
pochodzi z `errorhandler(404)` blueprintu — Flask kieruje 404 z konwertera `<int:>` do handlera
blueprintu tylko gdy trasa dopasowała blueprint; jeśli test pada z HTML, dodaj trasę catch-all
`@pets_bp.route('/api/<path:_reszta>', methods=['GET','POST'])` rzucającą `PetError('not_found', …, 404)`.

- [ ] **Step 6: Suita odznak/konkursów/dashboardu (regresja nawigacji)**

Run: `venv/bin/python -m pytest tests -q -k "contests or dashboard or achievements_routes" --no-header 2>&1 | tail -1`
Expected: wszystkie `passed`.

- [ ] **Step 7: Commit**

```bash
git add modules/pets/routes.py modules/pets/__init__.py app.py templates/components/sidebar_client.html templates/components/bottom_bar_client.html templates/client/base_client.html templates/client/pets/home.html static/img/icons/paw.svg static/css/pages/client/pets.css static/css/components/pet-companion.css tests/test_pets_routes.py
git commit -m "$(cat <<'EOF'
feat(pupile): trasy i JSON API /client/pupile, bramka 404, nawigacja

Strona ze szkieletem (state/species w data-*), API wg specu 3.5 nad fasada
service, PetError -> {ok,error,message}, 400/404/429 JSON pod /api/, limiter
120/min per uzytkownik; pets_enabled w context processorze; pozycja
"Moje pupile" w sidebarze i arkuszu PWA z kropka needs_care; ikona lapki.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2 (paczka B — rig SVG, model Opus 5.5, równolegle z Task 3): `species.js`, `pet-rig.js`, `pet-rig.css`, demo

**Files:**
- Create: `static/js/pet/species.js`, `static/js/components/pet-rig.js`, `static/css/components/pet-rig.css`
- Create: `static/dev/pet-rig-demo.html` (strona demo do wizualnej iteracji; statyczny HTML
  ładujący trzy pliki wyżej względną ścieżką — bez Flaska)
- Create: `.claude/launch.json` wpis `{"name": "rig-demo", "runtimeExecutable": "python3",
  "runtimeArgs": ["-m", "http.server", "8765"], "port": 8765}` (jeśli plik istnieje — dopisz
  konfigurację) i otwórz `http://localhost:8765/static/dev/pet-rig-demo.html` przez `preview_start`.

**Interfaces (kontrakt dla paczki C i etapu 5 — nazwy 1:1):**
- `window.PetSpecies` — obiekt `{ slug: { name, palette: {base, light, dark, cheek}, extras: [...] , parts: {...} } }`
  dla 8 slugów z `modules/pets/species.py` (`wiewiorka`, `kroliczek`, `szczeniak`, `piesek`,
  `kotek`, `kurczaczek`, `czarny-kotek`, `mis`); palety **dokładnie** jak w `species.py`.
- `window.PetRig`:
  - `mount(container, opts) -> rig`; `opts = { species, stage: 'maluch'|'dziecko'|'dorosly',
    stars: 0..5, mood: 'szczesliwy'|'glodny'|'znudzony'|'brudny'|'smutny'|'chory'|'krytyczny',
    asleep: bool, size: 'card'|'mini'|'companion' }`.
  - `rig.update(opts)` (częściowe), `rig.gesture(name)` (`jump|blink|sway|spin|wave|dance|flip` —
    klasa `g-<name>` zdejmowana po `animationend`), `rig.playAction(action)`
    (`feed|play|wash|heal|pat|wake|celebrate` — sekwencja 0,8–2 s, zwraca Promise), `rig.setStars(n)`,
    `rig.destroy()`, `rig.el` (root).
  - `mountEgg(container, { pct: 0..100, boosted: bool, ready: bool, size }) -> egg`;
    `egg.update(opts)`, `egg.hatch() -> Promise` (pękanie 1,5–2 s), `egg.destroy()`.
  - `mountMemorial(container, { species, size }) -> rig` (szarości, zamknięte oczy, owalna ramka nagrobka).
- DOM/CSS: root `<div class="pet-rig pet-rig--{species} pet-rig--{stage} pet-rig--{size}">` z `<svg
  viewBox="0 0 200 200">`; grupy `.rig-shadow .rig-tail .rig-body .rig-paws .rig-head .rig-ears
  .rig-eyes .rig-cheeks .rig-mouth .rig-fringe .rig-accessories (pusta) .rig-stars .rig-status`.
  Stany: `.is-idle .is-sleep .is-sad .is-sick .is-critical .is-eat .is-play .is-wash .is-pat
  .is-celebrate .is-hatch`. Mruganie losowe co 3–6 s przez JS (klasa `g-blink`). `transform-origin`
  ustawione na grupach (głowa: dół szyi; ciało: środek dołu). Stadium = skala grup: maluch głowa 1,3×
  / ciało 0,7×, dziecko 1,15× / 0,85×, dorosły 1:1 — przez zmienne CSS `--rig-head-scale`,
  `--rig-body-scale` na roocie.
- Animacje w `pet-rig.css` jako `@keyframes rig-*` (oddech, podskok, merdanie, zzz unoszące się,
  chmurka choroby, łezka, serduszko przy pat, bąbelki mycia, miseczka przy jedzeniu, piłka przy
  zabawie, konfetti/iskry przy celebrate i hatch, pękanie jajka 0/33/66/100 %). `@media
  (prefers-reduced-motion: reduce)`: tylko mruganie i statyczne pozy.
- Rozmiary: `card` 180×180 px (max-width 100 %), `mini` 96×96, `companion` 72×72 (telefon 56×56).
  Każdy gatunek ≤ 6 KB kształtów; `species.js` ≤ 60 KB.
- Kolory z palety przez zmienne CSS na roocie (`--rig-base`, `--rig-light`, `--rig-dark`, `--rig-cheek`),
  ustawiane przez JS z `PetSpecies[slug].palette` — dark mode nie zmienia postaci (tylko tło sceny,
  którym zarządza karta).

- [ ] **Step 1: Demo HTML (najpierw) z ośmioma rigami w trzech stadiach + jajko + nagrobek + przyciski
  stanów/gestów/akcji**, żeby każdą zmianę widzieć od razu. Uruchom `preview_start {name: "rig-demo"}`
  i zrób zrzut.
- [ ] **Step 2: `species.js`** — zacznij od jednego gatunku (`kotek`) na pełnym rigu, dopnij animacje,
  potem pozostałe 7 jako warianty kształtów. Rodzina kształtów ma być spójna (ten sam „język":
  okrągłe głowy, duże oczy, policzki) — inspiracja referencją ANITEEZ z briefu: wiewiórka pomarańczowa
  z paskami i puszystym ogonem, króliczek różowy z długimi uszami i iskierkami, szczeniak kremowy
  z opadającymi uszami i grzywką, piesek biały z długimi uszami, kotek lawendowy z białym pyszczkiem,
  kurczaczek żółty z dziobkiem i czubkiem, czarny kotek z czerwoną obrożą i dzwoneczkiem,
  miś brązowy z listkiem.
- [ ] **Step 3: `pet-rig.js`** — składanie z części, API jak wyżej, kolejkowanie `playAction`
  (nie nakładać dwóch akcji), sprzątanie timerów w `destroy()`.
- [ ] **Step 4: `pet-rig.css`** — keyframes i stany; sprawdź `prefers-reduced-motion` (DevTools →
  emulacja) i dark mode strony demo (przełącznik `data-theme` w demo).
- [ ] **Step 5: Weryfikacja wizualna** — zrzuty: 8 gatunków × 3 stadia (siatka), stany sleep/sad/
  sick/critical, akcje feed/play/wash/pat, jajko 0/33/66/100 % + hatch, nagrobek. Zapisz zrzuty do
  scratchpadu i wymień w raporcie.
- [ ] **Step 6: Commit** `feat(pupile): rig SVG - 8 gatunkow, stadia, animacje, jajko, karta pamieci`
  (+ demo i launch.json w osobnym commicie `chore(pupile): demo rigu do podgladu`).

---

### Task 3 (paczka C — UI strony, model Opus 5.5, równolegle z Task 2): `pets.js`, `pet-card`, `pets.css`, modal, haptyka

**Files:**
- Modify: `templates/client/pets/home.html` (rozbudowa szkieletu: kontenery modalu, szablony `<template>`)
- Create: `static/js/pages/client/pets.js`, `static/js/components/pet-card.js`,
  `static/js/utils/haptics.js`
- Create/Modify: `static/css/pages/client/pets.css` (plik założony w paczce A — rozbuduj),
  `static/css/components/pet-card.css`, sekcja `/* === Pet hatch modal === */` w
  `static/css/components/modals.css`
- Modify: `static/sw.js` (`CACHE_VERSION` → `thunderorders-v27`)

**Interfaces:**
- Consumes: API z Task 1 (dokładne ścieżki i kształty), `window.PetRig` / `window.PetSpecies`
  z Task 2 (do czasu scalenia B pracuj na **atrapie** `static/dev/pet-rig-stub.js`, która wystawia to
  samo API i rysuje kolorowe koło z napisem gatunku — po scaleniu atrapa znika; nie commituj jej).
- Produces (dla etapu 5): `window.PetCard.render(container, petDict, { mini: bool, onAction(pet, action, count), species })
  -> card` z `card.update(petDict)`, `card.el`, `card.destroy()`; `window.PetsApi` (`get(path)`,
  `post(path, body)` z CSRF, zwracające Promise `{ok, ...}` i rzucające `{error, message, status}`
  także dla odpowiedzi nie-JSON); `window.PetsState` (`current`, `set(state)`, `onChange(cb)`,
  `needsCare()`), `window.Haptics` (`tap()`, `pattern(name)`, `enabled()`); zdarzenie
  `document: 'pets:state'` po każdej zmianie stanu; ustawianie kropek `#petsNavDot` i
  `#pwaSheetPetsDot` (także w `template#pwaSheetClientMore` — bottom-bar klonuje szablon przy
  każdym otwarciu).

**Zachowanie (spec §4.2 + Review Focus 2–4):**
- Boot: `JSON.parse(petsApp.dataset.state)`; render trzech sekcji + ustawień; co **5 min** i po
  każdej akcji `GET api/stan` (pełny); paski ekstrapolowane co 1 s z `rates_per_hour` (klamra 0–100),
  bez zmiany `can/reasons` do czasu odświeżenia.
- Gniazdko: kafelki `eggs_available` (start/monthly/rescue z imieniem/granted z liczbą) z przyciskiem
  „Odbierz"; odliczanie do `next_monthly_at`; jajka w inkubacji: `PetRig.mountEgg` + pasek postępu
  + „Ogrzej" (odliczanie do `boost_until`) lub „Wykluj" gdy `ready`.
- Domek: siatka `PetCard` (1 kolumna ≤ 480 px, 2 ≤ 1024, 3–4 wyżej). Karta: scena z rigiem
  (klik = pat pat: paczki — debounce 2 s, max 50 w żądaniu, animacja i wibracja natychmiast, przyrost
  po odpowiedzi), imię (klik → inline edycja, zapis przez `/imie`), stadium, gwiazdki, 3 paski
  (+ zdrowie gdy < 100), nastrój słownie, przyciski akcji (ikona + etykieta, ≥ 44 px) z `disabled`
  i **tekstem powodu pod przyciskiem** z `reasons`, „Obudź" zamiast akcji gdy `asleep`, przy
  `heal_available_at` odliczanie.
- Album: 8 kart (sylwetka / `PetRig` mini / `mountMemorial` + imię, daty, dni opieki, światełka,
  przycisk „Zapal światełko" gdy `can_light`), licznik `n/8`.
- Ustawienia: wybór towarzysza (`companion.pet_id`, `auto`) + przełącznik włączony; przełącznik
  „Powiadomienia o pupilach" = ten sam `POST /notifications/preferences {pet_updates}` co w profilu
  (GET na starcie).
- Modal wyklucia (`#petHatchModal`, klasy `modal-overlay`/`modal-content` + `active`/`closing`,
  ESC i klik w tło, focus trap jak `grant-badge-modal.js`): `egg.hatch()` → `POST wykluj` →
  odsłonięcie rigu nowego gatunku z konfetti (`celebrate`) → dla `new`: pole imienia (walidacja
  1–20 po stronie klienta + komunikat błędu z serwera **przy polu**, modal zostaje otwarty, pupil już
  istnieje); dla `dupe`: „To drugi {species_name}! Twój {imię} dostaje gwiazdkę ⭐" + `setStars` na
  karcie. Po zamknięciu: jeśli `new_achievements` niepuste → `sessionStorage.removeItem('achievements_last_check')`,
  `fetch('/achievements/api/unseen')`, `window.AchievementUnlock.show(data.achievements)`.
- Odpowiedzi nie-JSON / 302 / 500 → toast „Sesja wygasła — zaloguj się ponownie" (gdy `redirected`)
  albo „Coś poszło nie tak, spróbuj za chwilę"; przyciski wracają do stanu sprzed kliknięcia.
  410 `pet_gone` → toast z `message` i pełne odświeżenie stanu (karta znika, album pokazuje pamięć).
  409 `not_available` → bez toastu błędu, tylko odświeżenie stanu (Review Focus 3).
- Haptyka: `navigator.vibrate(10)` przy pat, `[30,50,30,50,80]` przy wykluciu; wyłączona przy
  `prefers-reduced-motion`; brak API → cicho.
- Escapowanie: wszystkie imiona przez `escapeHtml` (textContent → innerHTML); zero inline `onclick`;
  delegacja zdarzeń z `data-action`/`data-pet-id`.
- CSS: `pets.css` (układ, sekcje, gniazdko, album, ustawienia, responsywność, dark), `pet-card.css`
  (karta i `pet-card--mini`, paski z gradientem i kolorem wg progu < 30 / < 50, dark), modal w
  `modals.css` (dark). Scena karty w dark: `rgba(255,255,255,0.05)` + border `rgba(240,147,251,0.15)`.

- [ ] **Step 1: Atrapa rigu** (`static/dev/pet-rig-stub.js`) i lokalny podgląd strony na SQLite —
  użyj skryptu z Task 4 Step 1 (centrala dostarczy `scripts/dev_pets_preview.py` w scratchpadzie wraz
  z `.claude/launch.json` wpisem `pets-preview`); jeśli jeszcze go nie ma, napisz własny wg
  `reference_xampp_nie_wstaje_apple_silicon` (create_app('testing') z SQLite w pliku, `create_all`,
  `_zasiej_slowniki` z conftest, użytkownik z `profile_completed`, profil + pupile w kilku stanach,
  trasa `/dev-login`).
- [ ] **Step 2: `PetsApi` + `PetsState` + boot + gniazdko** (odbiór startowego działa end-to-end).
- [ ] **Step 3: `PetCard` + akcje + ekstrapolacja + pat pat paczkami** (sprawdź 409 bez toastu).
- [ ] **Step 4: Album + ustawienia + modal wyklucia + odznaki + haptyka.**
- [ ] **Step 5: CSS light/dark, 375 px / 768 px / 1280 px — zrzuty** (DevTools / `resize_window`),
  `prefers-reduced-motion`, brak poziomego scrolla, przyciski ≥ 44 px (zmierz w DevTools).
- [ ] **Step 6: Bump `CACHE_VERSION`; commity** per krok (`feat(pupile): …`).

---

### Task 4 (centrala): scalanie, podgląd lokalny, weryfikacja wizualna, poprawki, recenzja

**Files:**
- Create (scratchpad, poza repo): `scripts/dev_pets_preview.py` — SQLite w pliku, seed: użytkownik
  `test@example.com` z `profile_completed=True`, włączona flaga (`pets_enabled` + `pets_rollout_pct=100`
  w `Settings`), profil, pupile: szczęśliwy maluch, głodne dziecko (sytość 25), chory dorosły
  (zdrowie 60, pasek na zerze), śpiący (jeśli noc), jajko w inkubacji z boostem, jajko gotowe,
  jajko ratunkowe do odebrania (pupil, który odszedł z 3 światełkami), 2 gwiazdki na jednym; trasa
  `/dev-login` logująca tego użytkownika; port 5001.
- Modify: `.claude/launch.json` (wpis `pets-preview` uruchamiający skrypt przez `venv/bin/python`).

- [ ] **Step 1: Scal B i C do `feat/pupile`** (`--no-ff`), usuń atrapę rigu, uruchom
  `tests/test_pets_routes.py` + pełną suitę (wynik z pliku).
- [ ] **Step 2: Podgląd**: `preview_start {name: "pets-preview"}` → `/dev-login` → `/client/pupile`;
  `read_console_messages` (zero błędów), `read_network_requests` (api/stan 200), zrzuty light/dark,
  desktop/375 px; przeklikaj: odbiór → ogrzej → wykluj (modal, imię, konfetti) → nakarm/baw/myj →
  pat pat (paczka w sieci po 2 s) → światełko → towarzysz → sidebar (kropka). Każdy defekt: poprawka
  TDD, gdy dotyczy backendu; dla frontu poprawka + ponowny zrzut.
- [ ] **Step 3: Recenzja całego etapu** świeżym Opusem (zakres od końca etapu 3), fix pass
  Critical/Important, ledger, ClickUp, pamięć.
- [ ] **Step 4: Raport** (bez pusha) — i dalej etap 5.
