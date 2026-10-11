# Pupile „Świat” — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przebudować moduł pupili w ilustrowany świat (mapa → domek / szpital / warsztat / ogród), zamienić „Wylecz” na pobyt w szpitalu, dodać warianty akcji, 5 losowych skórek jajek, dłoń przy pat pat, dłuższe wyklucie, nowy widget i pamięć pozycji towarzysza.

**Architecture:** Backend (Python, TDD, centrala) dostaje szpital jako osobny odcinek symulacji z czasem wyzdrowienia zapisanym przy przyjęciu (`hospital_healed_at`), dwa nowe endpointy, parametr wariantu i skórkę jajka; wszystko inne w regułach zostaje. Frontend (3 paczki dla subagentów w worktree) dostaje router scen w `pets.js`, wspólny moduł pokoju `room.js` (domek + widget), rozszerzony rig i nakładkę wyklucia; kontrakty między paczkami są zapisane niżej co do nazwy.

**Tech Stack:** Flask 3 + SQLAlchemy 2 + Flask-Migrate (MariaDB prod, SQLite testy), pytest przez `venv/bin/python -m pytest`, Jinja2, vanilla JS (IIFE, bez bundlera), SVG/CSS (light + `[data-theme="dark"]`).

**Spec:** `docs/superpowers/specs/2026-10-11-pupile-swiat-design.md` (v3; nadrzędny) + `docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md` (v2; obowiązuje poza miejscami, które v3 zastępuje).

## Global Constraints

- Gałąź `feat/pupile`, **bez pusha** (push = auto-deploy). Funkcja dalej za flagą `pets_enabled` + `pets_rollout_pct`.
- Każda zmiana schematu przez migrację Flask-Migrate (`migrations/versions/`), commit razem z kodem; `down_revision = 'f3e9a1c7b2d4'`.
- Testy: `venv/bin/python -m pytest …` (nigdy gołe `pytest`), wynik do pliku, kod wyjścia sprawdzany z pliku (nie przez `| tail`). Znany niezwiązany czerwony test: `tests/test_mobile_api_auth.py::test_logout_stores_expiry_in_local_time_and_purges_expired` (DST) — `--deselect` w pełnej suicie.
- Light + dark dla KAŻDEGO stylu (`[data-theme="dark"]`, paleta glassmorphism z CLAUDE.md); style modali/nakładek w `static/css/components/modals.css`; zero inline JS/CSS poza `data-*` i wartościami dynamicznymi; cele dotyku ≥ 44 px; `prefers-reduced-motion` respektowane.
- `window.showToast` (nie `window.Toast`); komunikaty z serwera escapowane przed `showToast`; zero inline `onclick` (delegacja + `data-*`).
- Teksty po polsku, podmiot „Pupil {imię}” w komunikatach o pupilu (rodzaj gramatyczny).
- Warianty (identyczne w backendzie i JS): `feed`: `miska`, `jablko`, `ciastko`; `play`: `pilka`, `wloczka`, `banki`; `wash`: `kapiel`, `prysznic`, `gabka`.
- Skórki jajek (indeks = `egg_skin`): `0 kropki`, `1 niebo`, `2 laczka`, `3 paski`, `4 laty`.
- Szpital (domyślne `pets_hospital`): `{"hours": 8, "floor": 60, "wait_hours": 24}`; tęsknota: od `healed_at` radość spada `100 / decay_hours.fun` na h × (1 − 0,1 × gwiazdki), bez nocnego spowolnienia.
- `static/sw.js`: bump `CACHE_VERSION` o 1 względem zastanej wartości (`thunderorders-v28` → `v29`) w zadaniu integracji.
- Repo publiczne: żadnych danych infrastruktury w commitach. Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Akcja lub pat po wyzdrowieniu** (stan zapisany z `state_at = now`, zdrowie 100) nie może przesunąć auto-wypisu ani „odmłodzić” leczenia — czas wypisu liczy się z `hospital_healed_at`, nie ze stanu. Test w Task 3.
2. **Podwójny odbiór** (dwie karty, albo ręczny odbiór po wyliczonym auto-wypisie) — dokładnie jedno zdarzenie `discharge`, drugi odbiór 409 `not_in_hospital`. Test w Task 3.
3. **Towarzysz w szpitalu / wszyscy żywi w szpitalu** — towarzysz spada na automat spoza szpitala albo `pet_id = null`; `needs_care` tylko gdy ktoś w szpitalu jest wyleczony. Test w Task 3.
4. **Zmiana liczb w panelu admina w trakcie pobytu** (checkpoint wszystkich żywych) — pobyt zostaje nietknięty (`hospital_since`, `hospital_healed_at`), zdrowie dalej rośnie do 100 w tym samym momencie. Test w Task 3.
5. **Link `/client/pupile/domek?pupil=ID` dla pupila w szpitalu, odeszłego albo cudzego** — w szpitalu: przekierowanie sceny na `/client/pupile/szpital?pupil=ID`; odeszły/nieistniejący: pokój bez otwartego panelu, bez błędu w konsoli. Weryfikacja w przeglądarce w Task 7.

---

### Task 1: Migracja, model, konfiguracja `pets_hospital`, panel admina

**Files:**
- Create: `migrations/versions/b5d8e2f4a917_pupile_szpital_skorki.py`
- Modify: `modules/pets/models.py` (kolumny + typy zdarzeń + stałe)
- Modify: `modules/pets/config.py` (`_DICT_DEFAULTS['hospital']`, `PetConfig.hospital`, `MAX_DICT`, `_przetworz`, `ADMIN_FIELDS`, `_FLOAT_FIELDS`, `validate_settings`)
- Modify: `tests/test_pets_migration.py` (głowa + parytet z modelami po obu migracjach)
- Modify: `tests/test_pets_admin.py` (`PELNY_FORMULARZ` bez pól heal, z polami szpitala)
- Test: `tests/test_pets_szpital_dane.py`

**Interfaces:**
- Produces: kolumny `Pet.hospital_since` (DateTime NULL), `Pet.hospital_healed_at` (DateTime NULL), `Pet.hospital_ready_notified_at` (DateTime NULL), `Pet.egg_skin` (SmallInteger NOT NULL, default 0); `models.EGG_SKINS = ('kropki', 'niebo', 'laczka', 'paski', 'laty')`; `EVENT_TYPES` zawiera `'admit'`, `'discharge'`; `PetConfig.hospital: dict` z kluczami `hours`, `floor`, `wait_hours`; pola formularza `pets_hospital_hours`, `pets_hospital_floor`, `pets_hospital_wait_hours`.

- [ ] **Step 1: Testy (RED)** — `tests/test_pets_szpital_dane.py`:

```python
"""Spec v3 §4.2–4.3: kolumny szpitala i skórki, konfiguracja pets_hospital, formularz admina."""
import json

from tests.test_pets_admin import PELNY_FORMULARZ, _admin


def test_model_ma_kolumny_szpitala_i_skorki():
    from modules.pets.models import EGG_SKINS, EVENT_TYPES, PRUNABLE_EVENT_TYPES, Pet
    kol = {c.name: c for c in Pet.__table__.columns}
    for nazwa in ('hospital_since', 'hospital_healed_at', 'hospital_ready_notified_at'):
        assert kol[nazwa].nullable is True
    assert kol['egg_skin'].nullable is False
    assert EGG_SKINS == ('kropki', 'niebo', 'laczka', 'paski', 'laty')
    assert {'admit', 'discharge'} <= set(EVENT_TYPES)
    assert not ({'admit', 'discharge'} & set(PRUNABLE_EVENT_TYPES))


def test_konfiguracja_szpitala_domyslna_i_z_settings(db):
    from modules.auth.models import Settings
    from modules.pets.config import PetConfig
    assert PetConfig().hospital == {'hours': 8, 'floor': 60, 'wait_hours': 24}
    Settings.set_value('pets_hospital', json.dumps({'hours': 12, 'wait_hours': 0}), type='json')
    db.session.commit()
    cfg = PetConfig.load(force=True)
    assert cfg.hospital == {'hours': 12, 'floor': 60, 'wait_hours': 0}      # wait_hours 0 legalne
    Settings.set_value('pets_hospital', json.dumps({'hours': 999}), type='json')
    db.session.commit()
    assert PetConfig.load(force=True).hospital['hours'] == 8                  # > 168 → domyślne


def test_formularz_admina_ma_pola_szpitala_bez_leczenia(client, login, make_user, db):
    _admin(make_user, login)
    html = client.get('/admin/pupile').data.decode()
    for pole in ('pets_hospital_hours', 'pets_hospital_floor', 'pets_hospital_wait_hours'):
        assert f'name="{pole}"' in html
    assert 'name="pets_actions_heal"' not in html and 'name="pets_actions_heal_cooldown_h"' not in html


def test_zapis_szpitala_z_formularza_i_limity(client, login, make_user, db):
    from modules.pets.config import PetConfig
    _admin(make_user, login)
    r = client.post('/admin/pupile/ustawienia', data=dict(PELNY_FORMULARZ, pets_hospital_hours='6',
                                                         pets_hospital_floor='70', pets_hospital_wait_hours='0'))
    assert r.status_code == 302
    assert PetConfig.load(force=True).hospital == {'hours': 6, 'floor': 70, 'wait_hours': 0}
    r = client.post('/admin/pupile/ustawienia', data=dict(PELNY_FORMULARZ, pets_hospital_hours='200'))
    assert r.status_code == 400 and 'pets_hospital_hours' in r.data.decode()
    r = client.post('/admin/pupile/ustawienia', data=dict(PELNY_FORMULARZ, pets_hospital_floor='0'))
    assert r.status_code == 400 and 'pets_hospital_floor' in r.data.decode()
```

W `tests/test_pets_admin.py` zamień w `PELNY_FORMULARZ` linie z `pets_actions_heal` i `pets_actions_heal_cooldown_h` na pola szpitala:

```python
    'pets_actions_feed': '50', 'pets_actions_play': '50',
    'pets_actions_allow_below': '80',
    'pets_actions_pat_gain': '0.25', 'pets_actions_pat_per_hour': '60',
    'pets_actions_wake_penalty': '10', 'pets_actions_awake_minutes': '20',
    'pets_hospital_hours': '8', 'pets_hospital_floor': '60', 'pets_hospital_wait_hours': '24',
```

W `tests/test_pets_migration.py`: `REWIZJA` zostaje (`f3e9a1c7b2d4`), dodaj stałe nowej migracji i dociągnij ją w teście parytetu:

```python
REWIZJA_SZPITAL = 'b5d8e2f4a917'
PLIK_SZPITAL = pathlib.Path('migrations/versions') / f'{REWIZJA_SZPITAL}_pupile_szpital_skorki.py'


def _zaladuj(plik, nazwa):
    spec = importlib.util.spec_from_file_location(nazwa, plik)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul
```

`test_migracja_jest_jedyna_glowa` → `assert sd.get_heads() == [REWIZJA_SZPITAL]` oraz `assert sd.get_revision(REWIZJA_SZPITAL).down_revision == REWIZJA` (asercja o `dde1a45a7d87` dla `REWIZJA` zostaje). W `test_upgrade_tworzy_tabele_zgodne_z_modelami` zaraz po `migracja.upgrade()` dodaj `_zaladuj(PLIK_SZPITAL, 'migracja_szpital').upgrade()` (w tym samym `Operations.context`). Dopisz test odwracalności nowej rewizji:

```python
def test_szpital_downgrade_usuwa_kolumny(silnik):
    with silnik.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            _zaladuj_migracje().upgrade()
            nowa = _zaladuj(PLIK_SZPITAL, 'migracja_szpital')
            nowa.upgrade()
            assert {'hospital_since', 'hospital_healed_at', 'hospital_ready_notified_at', 'egg_skin'} <= set(_kolumny(sa.inspect(conn), 'pets'))
            nowa.downgrade()
        assert not ({'hospital_since', 'egg_skin'} & set(_kolumny(sa.inspect(conn), 'pets')))
```

- [ ] **Step 2: RED** — `venv/bin/python -m pytest tests/test_pets_szpital_dane.py tests/test_pets_migration.py tests/test_pets_admin.py -q -p no:cacheprovider > <scratch>/t1_red.txt 2>&1; echo $?` → Expected: failures (brak `EGG_SKINS`, brak `hospital`, brak pliku migracji, pola heal w HTML).

- [ ] **Step 3: Migracja** — `migrations/versions/b5d8e2f4a917_pupile_szpital_skorki.py`:

```python
"""Pupile: pobyt w szpitalu i skórki jajek (spec v3 §4.3)

Revision ID: b5d8e2f4a917
Revises: f3e9a1c7b2d4
"""
from alembic import op
import sqlalchemy as sa

revision = 'b5d8e2f4a917'
down_revision = 'f3e9a1c7b2d4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pets') as batch:
        batch.add_column(sa.Column('hospital_since', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('hospital_healed_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('hospital_ready_notified_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('egg_skin', sa.SmallInteger(), nullable=False, server_default=sa.text('0')))


def downgrade():
    with op.batch_alter_table('pets') as batch:
        batch.drop_column('egg_skin')
        batch.drop_column('hospital_ready_notified_at')
        batch.drop_column('hospital_healed_at')
        batch.drop_column('hospital_since')
```

- [ ] **Step 4: Model** — w `modules/pets/models.py`: po `EGG_SOURCES` dodaj `EGG_SKINS = ('kropki', 'niebo', 'laczka', 'paski', 'laty')   # indeks = Pet.egg_skin (spec v3 §2)`; w `EVENT_TYPES` dopisz `'admit', 'discharge'` (NIE do `PRUNABLE_EVENT_TYPES`). W klasie `Pet` po `egg_ready_notified_at`:

```python
    egg_skin = db.Column(db.SmallInteger, nullable=False, default=0, server_default=db.text('0'))  # EGG_SKINS
```

i po `notify_level`:

```python
    # --- szpital (spec v3 §4): NULL = nie w szpitalu; healed_at ustalone przy przyjęciu ---
    hospital_since = db.Column(db.DateTime, nullable=True)
    hospital_healed_at = db.Column(db.DateTime, nullable=True)
    hospital_ready_notified_at = db.Column(db.DateTime, nullable=True)
```

- [ ] **Step 5: Konfiguracja** — w `modules/pets/config.py`:
  - `_DICT_DEFAULTS['hospital'] = {'hours': 8, 'floor': 60, 'wait_hours': 24}`;
  - pole `hospital: dict = _slownik('hospital')` w `PetConfig` (po `actions`);
  - `MAX_DICT['hospital'] = {'hours': 168, 'floor': 100, 'wait_hours': 168}`;
  - w `_przetworz` (gałąź `dict`) warunek `elif wartosc <= 0:` zamień na
    `elif wartosc <= 0 and not (nazwa == 'hospital' and klucz == 'wait_hours' and wartosc == 0):`;
  - w `ADMIN_FIELDS` z krotki pól `pets_actions` usuń `'heal', 'heal_cooldown_h'` (etykietę skróć o „leczenie / odstęp leczenia (h)”) i dodaj po `pets_actions`:
    `('pets_hospital', 'json', ('hours', 'floor', 'wait_hours'), 'Szpital: leczenie od zera do pełna (h) / próg pasków przy przyjęciu / czekanie na odbiór (h)'),`;
  - `_FLOAT_FIELDS` += `'pets_hospital_hours', 'pets_hospital_wait_hours'`;
  - w `validate_settings` warunek `elif v <= 0:` (gałąź słownikowa) zamień na
    `elif v <= 0 and not (klucz == 'pets_hospital' and pole == 'wait_hours' and v == 0):`.

- [ ] **Step 6: GREEN** — ten sam pytest → Expected: wszystkie passed. Dodatkowo `venv/bin/python -m pytest tests/test_pets_config.py tests/test_pets_fundament.py -q -p no:cacheprovider` → passed (test `test_pets_config` z `cfg.actions == {...heal...}` zostaje — klucze heal dalej są w domyślnych).

- [ ] **Step 7: Commit** — `git add migrations/versions/b5d8e2f4a917_pupile_szpital_skorki.py modules/pets/models.py modules/pets/config.py tests/test_pets_szpital_dane.py tests/test_pets_migration.py tests/test_pets_admin.py` → `feat(pupile): migracja szpitala i skorek jajek, konfiguracja pets_hospital`.

---

### Task 2: Reguły — odcinek szpitalny, dostępność akcji, warianty

**Files:**
- Modify: `modules/pets/rules.py`
- Modify: `tests/test_pets_rules.py` (testy `heal` → `admit`/szpital; `_cfg` z `hospital`)

**Interfaces:**
- Consumes: `cfg.hospital`, `cfg.decay_hours['fun']`, `cfg.max_stars`.
- Produces: `rules.ACTIONS = ('feed', 'play', 'wash', 'pat', 'wake')`; `rules.ACTION_VARIANTS = {'feed': ('miska', 'jablko', 'ciastko'), 'play': ('pilka', 'wloczka', 'banki'), 'wash': ('kapiel', 'prysznic', 'gabka')}`; `rules.SimResult(state, died_at, discharged_at=None)`; `rules.hospital_state(state, cfg, from_dt, to_dt, healed_at) -> PetState`; `rules.hospital_rates(state, cfg, now, healed_at) -> dict` (klucze `hunger, fun, clean, health`); `rules.action_availability(state, now, cfg, in_hospital=False) -> (can, reasons)` z kluczami `feed, play, wash, pat, wake, admit`.

- [ ] **Step 1: Testy (RED)** — w `tests/test_pets_rules.py`: do `_cfg` dodaj `hospital={'hours': 8, 'floor': 60, 'wait_hours': 24}` i usuń z `actions` klucze `heal`, `heal_cooldown_h`. Zastąp testy z `heal` (okolice linii 320–365) tymi:

```python
def test_dostepnosc_zdrowy_bez_admit_i_bez_heal():
    zdrowy = rules.PetState(hunger=90, fun=90, clean=90, health=100)
    can, reasons = rules.action_availability(zdrowy, PON_08, CFG)
    assert can == {'feed': False, 'play': False, 'wash': False, 'pat': True, 'wake': False, 'admit': False}
    assert reasons['admit'] == 'zdrowy'


def test_dostepnosc_chory_moze_do_szpitala():
    chory = rules.PetState(hunger=40, fun=40, clean=40, health=60)
    can, _ = rules.action_availability(chory, PON_08, CFG)
    assert can['admit'] is True and can['feed'] is True


def test_dostepnosc_w_szpitalu_tylko_pat():
    stan = rules.PetState(hunger=60, fun=60, clean=60, health=70)
    can, reasons = rules.action_availability(stan, PON_08, CFG, in_hospital=True)
    assert can == {'feed': False, 'play': False, 'wash': False, 'pat': True, 'wake': False, 'admit': False}
    assert reasons['feed'] == 'w szpitalu' and reasons['admit'] == 'już w szpitalu'


def test_dostepnosc_spiacy_tylko_obudz():
    spiacy = rules.PetState(hunger=90, fun=90, clean=90, health=100)
    can, _ = rules.action_availability(spiacy, PON_23 + timedelta(hours=2), CFG)
    assert can == {'feed': False, 'play': False, 'wash': False, 'pat': False, 'wake': True, 'admit': False}


def test_akcje_i_warianty():
    assert rules.ACTIONS == ('feed', 'play', 'wash', 'pat', 'wake')
    assert rules.ACTION_VARIANTS == {'feed': ('miska', 'jablko', 'ciastko'), 'play': ('pilka', 'wloczka', 'banki'),
                                     'wash': ('kapiel', 'prysznic', 'gabka')}


def test_szpital_zdrowie_liniowo_do_healed_at_paski_stoja():
    stan = rules.PetState(hunger=60, fun=60, clean=60, health=40)
    healed = PON_08 + timedelta(hours=6)
    po3h = rules.hospital_state(stan, CFG, PON_08, PON_08 + timedelta(hours=3), healed)
    assert round(po3h.health, 6) == 70.0 and (po3h.hunger, po3h.fun, po3h.clean) == (60.0, 60.0, 60.0)
    po6h = rules.hospital_state(stan, CFG, PON_08, healed, healed)
    assert po6h.health == 100.0 and po6h.fun == 60.0


def test_szpital_tesknota_po_wyzdrowieniu_bez_nocy():
    stan = rules.PetState(hunger=60, fun=60, clean=60, health=40, stars=0)
    healed = PON_08 + timedelta(hours=6)
    # 15 h po wyzdrowieniu (przez noc — w szpitalu bez spowolnienia): 60 − 15 × 100/30 = 10
    pozniej = rules.hospital_state(stan, CFG, PON_08, healed + timedelta(hours=15), healed)
    assert round(pozniej.fun, 6) == 10.0 and pozniej.health == 100.0 and pozniej.hunger == 60.0
    bardzo = rules.hospital_state(stan, CFG, PON_08, healed + timedelta(hours=40), healed)
    assert bardzo.fun == 0.0 and bardzo.health == 100.0            # w szpitalu zdrowie nie spada


def test_szpital_tesknota_wolniej_z_gwiazdkami():
    stan = rules.PetState(hunger=60, fun=60, clean=60, health=100, stars=2)
    po10h = rules.hospital_state(stan, CFG, PON_08, PON_08 + timedelta(hours=10), PON_08)
    assert round(po10h.fun, 6) == round(60 - 10 * (100 / 30) * 0.8, 6)


def test_szpital_czas_wstecz_bez_zmian():
    stan = rules.PetState(hunger=60, fun=60, clean=60, health=40)
    wynik = rules.hospital_state(stan, CFG, PON_08, PON_08 - timedelta(hours=1), PON_08 + timedelta(hours=6))
    assert wynik == rules.clamp_state(stan)


def test_szpital_tempa():
    stan = rules.PetState(hunger=60, fun=60, clean=60, health=40)
    t = rules.hospital_rates(stan, CFG, PON_08, PON_08 + timedelta(hours=6))
    assert t == {'hunger': 0.0, 'fun': 0.0, 'clean': 0.0, 'health': 10.0}
    po = rules.hospital_rates(rules.PetState(fun=50, health=100), CFG, PON_08 + timedelta(hours=7), PON_08 + timedelta(hours=6))
    assert po['health'] == 0.0 and round(po['fun'], 4) == round(-100 / 30, 4)
```

- [ ] **Step 2: RED** — `venv/bin/python -m pytest tests/test_pets_rules.py -q -p no:cacheprovider > <scratch>/t2_red.txt 2>&1; echo $?` → Expected: failures (`hospital_state` brak, `admit` brak, `ACTIONS` z `heal`).

- [ ] **Step 3: Implementacja** — w `modules/pets/rules.py`:

```python
@dataclass(frozen=True)
class SimResult:
    state: PetState
    died_at: datetime | None
    discharged_at: datetime | None = None   # auto-wypis ze szpitala wyliczony w trakcie symulacji (spec v3 §4.1)
```

```python
# ---------------------------------------------------------------------------
# Szpital (spec v3 §4.1, §4.4) — analitycznie, bez kroków
# ---------------------------------------------------------------------------

def _tesknota_na_h(state, cfg):
    gwiazdki = min(max(int(state.stars or 0), 0), int(cfg.max_stars))
    return (100.0 / float(cfg.decay_hours['fun'])) * (1.0 - 0.1 * gwiazdki)


def hospital_state(state, cfg, from_dt, to_dt, healed_at):
    """Stan w szpitalu w chwili to_dt (wołający pilnuje, by to_dt ≤ auto-wypis).

    Sytość i czystość stoją. Zdrowie rośnie liniowo od stanu w from_dt do 100 w healed_at
    (healed_at ustalone przy przyjęciu, więc zapis stanu w trakcie pobytu niczego nie przesuwa).
    Radość stoi do healed_at, potem spada (tęsknota) bez nocnego spowolnienia. Brak odejścia.
    """
    state = clamp_state(state)
    if to_dt <= from_dt:
        return state
    if to_dt >= healed_at or healed_at <= from_dt:
        zdrowie = 100.0
    else:
        udzial = (to_dt - from_dt).total_seconds() / (healed_at - from_dt).total_seconds()
        zdrowie = state.health + (100.0 - state.health) * udzial
    start_tesknoty = max(from_dt, healed_at)
    radosc = state.fun
    if to_dt > start_tesknoty:
        godziny = (to_dt - start_tesknoty).total_seconds() / 3600.0
        radosc = state.fun - _tesknota_na_h(state, cfg) * godziny
    return replace(state, health=_clamp(zdrowie), fun=_clamp(radosc))


def hospital_rates(state, cfg, now, healed_at):
    """Tempo na godzinę w szpitalu (do ekstrapolacji pasków w JS)."""
    tempo = {'hunger': 0.0, 'fun': 0.0, 'clean': 0.0, 'health': 0.0}
    if now < healed_at and state.health < 100:
        tempo['health'] = (100.0 - state.health) / ((healed_at - now).total_seconds() / 3600.0)
    if now >= healed_at and state.fun > 0:
        tempo['fun'] = -_tesknota_na_h(state, cfg)
    return tempo
```

Zamień `ACTIONS` i `action_availability`:

```python
ACTIONS = ('feed', 'play', 'wash', 'pat', 'wake')
ACTION_VARIANTS = {
    'feed': ('miska', 'jablko', 'ciastko'),
    'play': ('pilka', 'wloczka', 'banki'),
    'wash': ('kapiel', 'prysznic', 'gabka'),
}
```

```python
def action_availability(state, now, cfg, in_hospital=False):
    """`can` + `reasons` (po polsku). Śpiący: tylko „Obudź”. W szpitalu: tylko pat. `admit` = przyjęcie do szpitala."""
    can, reasons = {}, {}

    def ustaw(akcja, ok, powod):
        can[akcja] = ok
        if not ok:
            reasons[akcja] = powod

    if in_hospital:
        for akcja in ('feed', 'play', 'wash'):
            ustaw(akcja, False, 'w szpitalu')
        ustaw('pat', True, '')
        ustaw('wake', False, 'nie śpi')
        ustaw('admit', False, 'już w szpitalu')
        return can, reasons

    if is_asleep(state, now, cfg):
        for akcja in ('feed', 'play', 'wash', 'pat'):
            ustaw(akcja, False, 'śpi')
        ustaw('wake', True, '')
        ustaw('admit', False, 'śpi')
        return can, reasons

    prog = float(cfg.actions['allow_below'])
    ustaw('feed', state.hunger <= prog, 'najedzony')
    ustaw('play', state.fun <= prog, 'nie chce się bawić')
    ustaw('wash', state.clean <= prog, 'czysty')
    ustaw('pat', True, '')
    ustaw('wake', False, 'nie śpi')
    ustaw('admit', state.health < SICK_BELOW, 'zdrowy')
    return can, reasons
```

Popraw komentarz przy `SICK_BELOW` na „chory → budzi się, może iść do szpitala”.

- [ ] **Step 4: GREEN** — ten sam pytest → Expected: passed.

- [ ] **Step 5: Commit** — `feat(pupile): reguly szpitala (zdrowie liniowo, tesknota), dostepnosc admit, warianty akcji`.

---

### Task 3: Serwis — symulacja z wypisem, przyjęcie/odbiór, warianty, skórka, stan

**Files:**
- Modify: `modules/pets/common.py` (`CARE_ACTIONS`, `simulate_pet`, `persist_discharge`, `hospital_dict`, `pet_dict`, `egg_dict`, `checkpoint_alive_pets`)
- Modify: `modules/pets/actions.py` (`perform_action` z `variant`, bez `heal`; `admit_pet`, `discharge_pet`)
- Modify: `modules/pets/eggs.py` (`claim_egg(..., rng=None)` losuje `egg_skin`; `hatch_egg` z `persist_discharge`)
- Modify: `modules/pets/state.py` (wypis przy odczycie, towarzysz/`most_in_need` bez szpitala, `needs_care`, `config.hospital_hours`)
- Modify: `modules/pets/service.py` (eksport `admit_pet`, `discharge_pet`)
- Modify: `tests/test_pets_actions.py` (test `heal` → usunięty; zastąpiony testami szpitala w nowym pliku), `tests/test_pets_common.py:108` (`heal_available_at` → `hospital is None`)
- Test: `tests/test_pets_szpital.py`

**Interfaces:**
- Consumes: Task 1 (kolumny, `EGG_SKINS`, `cfg.hospital`), Task 2 (`hospital_state`, `hospital_rates`, `action_availability(..., in_hospital)`, `SimResult.discharged_at`, `ACTION_VARIANTS`).
- Produces: `common.CARE_ACTIONS = ('feed', 'play', 'wash', 'pat')`; `common.auto_discharge_at(pet, cfg) -> datetime | None`; `common.persist_discharge(pet, sim, now, manual=False) -> bool`; `common.pet_dict(pet, state, now, cfg, discharged=False)` (`discharged=True` = traktuj jak poza szpitalem — odczyt `lite` z wyliczonym, niezapisanym wypisem); `common.hospital_dict(pet, state, now, cfg) -> dict | None` z kluczami `since, healed_at, ready, progress_pct, auto_discharge_at` (ISO / bool / float); `pet_dict` zawiera `hospital` (dict lub `None`), `can`/`reasons` z `admit`, NIE zawiera `heal_available_at`; `egg_dict` zawiera `skin` (int 0–4); `actions.admit_pet(user, pet_id, now=None, cfg=None) -> Pet`; `actions.discharge_pet(user, pet_id, now=None, cfg=None) -> Pet`; `actions.perform_action(user, pet_id, action, count=1, now=None, cfg=None, variant=None) -> dict` z kluczem `variant` (str lub `None`); `eggs.claim_egg(user, source, pet_id=None, now=None, cfg=None, rng=None)`; `state['config']['hospital_hours']` (int).

- [ ] **Step 1: Testy (RED)** — `tests/test_pets_szpital.py`:

```python
"""Spec v3 §4: pobyt w szpitalu end-to-end w serwisie (bez HTTP)."""
import random
from datetime import timedelta

import pytest

from tests.pets_helpers import T0, zaloz_profil, zaloz_pupila


def _cfg(**over):
    from modules.pets.config import PetConfig
    baza = {'enabled': True, 'rollout_pct': 100, 'night': {'start': 0, 'end': 0, 'factor': 0.25}}
    baza.update(over)
    return PetConfig(**baza)


CFG = None


@pytest.fixture(autouse=True)
def _cfg_fixture():
    global CFG
    CFG = _cfg()


def _chory(user, **pola):
    dane = dict(hunger=20.0, fun=40.0, clean=30.0, health=50.0)
    dane.update(pola)
    return zaloz_pupila(user, **dane)


def test_przyjecie_podnosi_paski_do_progu_i_ustala_healed_at(db, make_user):
    from modules.pets.actions import admit_pet
    from modules.pets.models import PetEvent
    user = make_user(); zaloz_profil(user)
    pet = _chory(user)
    admit_pet(user, pet.id, now=T0, cfg=CFG)
    assert pet.hospital_since == T0 and (pet.hunger, pet.fun, pet.clean) == (60.0, 60.0, 60.0)
    assert pet.hospital_healed_at == T0 + timedelta(hours=4)          # (100 − 50) / 100 × 8 h
    assert pet.notify_level == 0 and pet.awake_until is None
    assert PetEvent.query.filter_by(pet_id=pet.id, type='admit').count() == 1


def test_przyjecie_tylko_chorego_i_raz(db, make_user):
    from modules.pets.actions import admit_pet
    from modules.pets.errors import PetError
    user = make_user(); zaloz_profil(user)
    zdrowy = zaloz_pupila(user, species='mis')
    with pytest.raises(PetError) as e:
        admit_pet(user, zdrowy.id, now=T0, cfg=CFG)
    assert e.value.code == 'not_sick' and e.value.status == 409
    chory = _chory(user)
    admit_pet(user, chory.id, now=T0, cfg=CFG)
    with pytest.raises(PetError) as e:
        admit_pet(user, chory.id, now=T0 + timedelta(minutes=5), cfg=CFG)
    assert e.value.code == 'in_hospital'


def test_w_szpitalu_nie_odchodzi_i_tylko_pat(db, make_user):
    from modules.pets.actions import admit_pet, perform_action
    from modules.pets.errors import PetError
    from modules.pets.state import state_for_user
    user = make_user(); zaloz_profil(user)
    pet = _chory(user, health=5.0, hunger=0.0)
    admit_pet(user, pet.id, now=T0, cfg=CFG)
    with pytest.raises(PetError) as e:
        perform_action(user, pet.id, 'feed', now=T0 + timedelta(hours=1), cfg=CFG)
    assert e.value.code == 'not_available' and e.value.message == 'w szpitalu'
    wynik = perform_action(user, pet.id, 'pat', count=4, now=T0 + timedelta(hours=1), cfg=CFG)
    assert wynik['accepted'] == 4 and wynik['first_care_today'] is True
    stan = state_for_user(user, now=T0 + timedelta(hours=2), cfg=CFG)
    p = stan['pets'][0]
    assert p['hospital'] is not None and p['asleep'] is False and p['bars']['hunger'] == 60.0
    assert p['can']['admit'] is False and p['can']['feed'] is False


def test_akcja_po_wyzdrowieniu_nie_przesuwa_wypisu(db, make_user):
    """Review Focus 1."""
    from modules.pets.actions import admit_pet, perform_action
    from modules.pets.common import auto_discharge_at
    user = make_user(); zaloz_profil(user)
    pet = _chory(user)
    admit_pet(user, pet.id, now=T0, cfg=CFG)
    wypis = auto_discharge_at(pet, CFG)
    assert wypis == T0 + timedelta(hours=4 + 24)
    perform_action(user, pet.id, 'pat', now=T0 + timedelta(hours=10), cfg=CFG)
    assert pet.hospital_healed_at == T0 + timedelta(hours=4)
    assert auto_discharge_at(pet, CFG) == wypis and pet.health == 100.0


def test_tesknota_i_auto_wypis_przy_odczycie(db, make_user):
    from modules.pets.actions import admit_pet
    from modules.pets.models import PetEvent
    from modules.pets.state import state_for_user
    user = make_user(); zaloz_profil(user)
    pet = _chory(user)
    admit_pet(user, pet.id, now=T0, cfg=CFG)
    # 4 h leczenia + 24 h czekania → wypis w T0+28h; radość: 60 − 24 × 100/30 = −20 → 0 przy wypisie
    stan = state_for_user(user, now=T0 + timedelta(hours=29), cfg=CFG)
    p = stan['pets'][0]
    assert p['hospital'] is None and p['bars']['fun'] == 0.0
    assert pet.hospital_since is None and pet.hospital_healed_at is None
    ev = PetEvent.query.filter_by(pet_id=pet.id, type='discharge').one()
    assert ev.created_at == T0 + timedelta(hours=28) and ev.value == 0      # 0 = automatyczny


def test_reczny_odbior_i_drugi_409(db, make_user):
    """Review Focus 2."""
    from modules.pets.actions import admit_pet, discharge_pet
    from modules.pets.errors import PetError
    from modules.pets.models import PetEvent
    user = make_user(); zaloz_profil(user)
    pet = _chory(user)
    admit_pet(user, pet.id, now=T0, cfg=CFG)
    discharge_pet(user, pet.id, now=T0 + timedelta(hours=2), cfg=CFG)
    assert pet.hospital_since is None and round(pet.health, 6) == 75.0 and pet.state_at == T0 + timedelta(hours=2)
    with pytest.raises(PetError) as e:
        discharge_pet(user, pet.id, now=T0 + timedelta(hours=3), cfg=CFG)
    assert e.value.code == 'not_in_hospital' and e.value.status == 409
    assert PetEvent.query.filter_by(pet_id=pet.id, type='discharge').count() == 1


def test_reczny_odbior_po_wyliczonym_auto_wypisie_409(db, make_user):
    """Review Focus 2: auto-wypis zapisany w trakcie odbioru → jedno zdarzenie, odbiór 409."""
    from modules.pets.actions import admit_pet, discharge_pet
    from modules.pets.errors import PetError
    from modules.pets.models import PetEvent
    user = make_user(); zaloz_profil(user)
    pet = _chory(user)
    admit_pet(user, pet.id, now=T0, cfg=CFG)
    with pytest.raises(PetError) as e:
        discharge_pet(user, pet.id, now=T0 + timedelta(hours=40), cfg=CFG)
    assert e.value.code == 'not_in_hospital'
    assert PetEvent.query.filter_by(pet_id=pet.id, type='discharge').count() == 1


def test_towarzysz_i_needs_care_przy_szpitalu(db, make_user):
    """Review Focus 3."""
    from modules.pets.actions import admit_pet, set_companion
    from modules.pets.state import state_for_user
    user = make_user(); zaloz_profil(user)
    chory = _chory(user, species='kotek')
    zdrowy = zaloz_pupila(user, species='mis', name='Puszek')
    set_companion(user, pet_id=chory.id, enabled=True)
    admit_pet(user, chory.id, now=T0, cfg=CFG)
    stan = state_for_user(user, now=T0 + timedelta(hours=1), cfg=CFG)
    assert stan['companion']['pet_id'] == zdrowy.id and stan['most_in_need_pet_id'] == zdrowy.id
    assert stan['needs_care'] is False                                  # leczy się, nikt nie czeka
    stan = state_for_user(user, now=T0 + timedelta(hours=5), cfg=CFG)  # wyleczony (4 h) — czeka na odbiór
    assert stan['needs_care'] is True and stan['pets'][0]['hospital']['ready'] is True


def test_wszyscy_w_szpitalu_towarzysz_pusty(db, make_user):
    from modules.pets.actions import admit_pet
    from modules.pets.state import state_for_user
    user = make_user(); zaloz_profil(user)
    pet = _chory(user)
    admit_pet(user, pet.id, now=T0, cfg=CFG)
    stan = state_for_user(user, lite=True, now=T0 + timedelta(hours=1), cfg=CFG)
    assert stan['companion']['pet_id'] is None and stan['most_in_need_pet_id'] is None


def test_checkpoint_admina_nie_rusza_pobytu(db, make_user):
    """Review Focus 4."""
    from modules.pets.actions import admit_pet
    from modules.pets.common import checkpoint_alive_pets
    user = make_user(); zaloz_profil(user)
    pet = _chory(user)
    admit_pet(user, pet.id, now=T0, cfg=CFG)
    checkpoint_alive_pets(T0 + timedelta(hours=2), CFG)
    assert pet.hospital_since == T0 and pet.hospital_healed_at == T0 + timedelta(hours=4)
    assert round(pet.health, 6) == 75.0 and pet.state_at == T0 + timedelta(hours=2)


def test_wariant_akcji(db, make_user):
    from modules.pets.actions import perform_action
    from modules.pets.errors import PetError
    user = make_user(); zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=20.0)
    wynik = perform_action(user, pet.id, 'feed', variant='jablko', now=T0, cfg=CFG)
    assert wynik['variant'] == 'jablko' and pet.hunger == 70.0
    with pytest.raises(PetError) as e:
        perform_action(user, pet.id, 'play', variant='jablko', now=T0, cfg=CFG)
    assert e.value.code == 'bad_variant' and e.value.status == 400
    with pytest.raises(PetError) as e:
        perform_action(user, pet.id, 'heal', now=T0, cfg=CFG)
    assert e.value.code == 'bad_action'
    assert perform_action(user, pet.id, 'pat', now=T0, cfg=CFG)['variant'] is None


def test_skorka_jajka_losowana_przy_odbiorze(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.state import state_for_user
    user = make_user()
    jajko = claim_egg(user, 'start', now=T0, cfg=CFG, rng=random.Random(7))
    assert 0 <= jajko.egg_skin <= 4
    stany = {claim_egg(make_user(), 'start', now=T0, cfg=CFG, rng=random.Random(s)).egg_skin for s in range(40)}
    assert stany == {0, 1, 2, 3, 4}
    assert state_for_user(user, now=T0, cfg=CFG)['eggs'][0]['skin'] == jajko.egg_skin


def test_konfiguracja_w_stanie(db, make_user):
    from modules.pets.state import state_for_user
    assert state_for_user(make_user(), now=T0, cfg=CFG)['config']['hospital_hours'] == 8
```

W `tests/test_pets_actions.py` usuń test(y) wołające `_akcja(user, pet, 'heal', ...)` (linie ~60–78). W `tests/test_pets_common.py:108` zamień `p['heal_available_at'] is None` na `p['hospital'] is None`.

- [ ] **Step 2: RED** — `venv/bin/python -m pytest tests/test_pets_szpital.py tests/test_pets_actions.py tests/test_pets_common.py -q -p no:cacheprovider > <scratch>/t3_red.txt 2>&1; echo $?` → Expected: failures (`admit_pet` brak itd.).

- [ ] **Step 3: `common.py`**:

```python
CARE_ACTIONS = ('feed', 'play', 'wash', 'pat')
```

```python
def auto_discharge_at(pet, cfg):
    if pet.hospital_since is None or pet.hospital_healed_at is None:
        return None
    return pet.hospital_healed_at + timedelta(hours=float(cfg.hospital['wait_hours']))


def simulate_pet(pet, now, cfg):
    """Stan „na teraz”. W szpitalu: odcinek szpitalny do auto-wypisu, potem zwykła symulacja (spec v3 §4.4)."""
    if pet.hospital_since is None:
        return rules.simulate(state_of(pet), cfg, pet.state_at, now)
    wypis = auto_discharge_at(pet, cfg)
    do = min(now, wypis)
    stan = rules.hospital_state(state_of(pet), cfg, pet.state_at, do, pet.hospital_healed_at)
    if now <= wypis:
        return rules.SimResult(stan, None)
    dalej = rules.simulate(stan, cfg, wypis, now)
    return rules.SimResult(dalej.state, dalej.died_at, discharged_at=wypis)


def persist_discharge(pet, sim, now, manual=False):
    """Wypis ze szpitala warunkowym UPDATE (jak persist_death): dwa równoległe wypisy = jedno zdarzenie.

    Zapisuje stan `sim.state` na `now`. Zdarzenie `discharge` ma created_at = chwila wypisu
    (auto: `sim.discharged_at`, ręczny: `now`) i value 1 = ręczny, 0 = automatyczny. Wołający commituje.
    """
    od_kiedy = pet.hospital_since
    if od_kiedy is None:
        return False
    stan = sim.state
    wynik = db.session.execute(
        update(Pet)
        .where(Pet.id == pet.id, Pet.hospital_since == od_kiedy)
        .values(hospital_since=None, hospital_healed_at=None, hospital_ready_notified_at=None,
                hunger=stan.hunger, fun=stan.fun, clean=stan.clean, health=stan.health, state_at=now)
    )
    db.session.expire(pet)
    if wynik.rowcount != 1:
        return False
    chwila = now if manual else (sim.discharged_at or now)
    add_event(pet.user_id, 'discharge', chwila, pet_id=pet.id, value=1 if manual else 0)
    return True
```

W `checkpoint_alive_pets` zamień ciało pętli po pupilach na:

```python
        for pet in alive_pets_lock_query(uid).all():
            sim = simulate_pet(pet, now, cfg)
            if sim.discharged_at is not None:
                persist_discharge(pet, sim, now)
            if sim.died_at is not None:
                persist_death(pet, sim, now)
            elif sim.discharged_at is None:
                apply_state(pet, sim.state, now)     # w szpitalu: hospital_healed_at zostaje (Review Focus 4)
            n += 1
```

Serializacja:

```python
def hospital_dict(pet, state, now, cfg):
    if pet.hospital_since is None:
        return None
    healed = pet.hospital_healed_at
    calosc = max(1.0, (healed - pet.hospital_since).total_seconds())
    postep = 100.0 if now >= healed else 100.0 * max(0.0, (now - pet.hospital_since).total_seconds()) / calosc
    return {
        'since': iso(pet.hospital_since),
        'healed_at': iso(healed),
        'ready': now >= healed,
        'progress_pct': round(min(100.0, postep), 1),
        'auto_discharge_at': iso(auto_discharge_at(pet, cfg)),
    }
```

`egg_dict` — dopisz `'skin': int(pet.egg_skin or 0),`. `pet_dict` — zamień początek i słownik:

```python
def pet_dict(pet, state, now, cfg, discharged=False):
    w_szpitalu = pet.hospital_since is not None and not discharged
    can, reasons = rules.action_availability(state, now, cfg, in_hospital=w_szpitalu)
    stadium = rules.stage(pet.hatched_at, now, cfg)
    tempo = (rules.hospital_rates(state, cfg, now, pet.hospital_healed_at) if w_szpitalu
             else rules.rates_per_hour(state, now, cfg))
    return {
        'id': pet.id,
        'species': pet.species,
        'name': pet.name,
        'stage': stadium,
        'age_days': rules.age_days(pet.hatched_at, now),
        'stars': int(pet.stars),
        'bars': {k: round(getattr(state, k), 1) for k in ('hunger', 'fun', 'clean', 'health')},
        'rates_per_hour': {k: round(v, 2) for k, v in tempo.items()},
        'mood': rules.mood(state),
        'asleep': False if w_szpitalu else rules.is_asleep(state, now, cfg),
        'awake_until': iso(state.awake_until) if state.awake_until and now < state.awake_until else None,
        'can': can,
        'reasons': reasons,
        'hospital': hospital_dict(pet, state, now, cfg) if w_szpitalu else None,
        'care_days': int(pet.care_days),
        'gestures': list(rules.GESTURES_BY_STAGE[stadium]),
    }
```

- [ ] **Step 4: `actions.py`** — w `perform_action` zmień sygnaturę na `(user, pet_id, action, count=1, now=None, cfg=None, variant=None)` i początek:

```python
    if action not in rules.ACTIONS:
        raise PetError('bad_action', 'Nieznana akcja.')
    if variant is not None and variant not in rules.ACTION_VARIANTS.get(action, ()):
        raise PetError('bad_variant', 'Nieznany wariant akcji.', 400)
    if variant is None and action in rules.ACTION_VARIANTS:
        variant = rules.ACTION_VARIANTS[action][0]
    lock_profile(user)
    pet = own_pet(user, pet_id, ('alive',))

    sim = simulate_pet(pet, now, cfg)
    if sim.discharged_at is not None:
        persist_discharge(pet, sim, now)
    if sim.died_at is not None:
        persist_death(pet, sim, now)
        db.session.commit()
        raise PetError('pet_gone', f'Pupil {pet.name} odszedł do gwiazd.', 410)

    stan = sim.state
    can, reasons = rules.action_availability(stan, now, cfg, in_hospital=pet.hospital_since is not None)
```

Usuń gałąź `elif action == 'heal': …`. Na końcu funkcji w zwracanym słowniku dodaj `'variant': variant`. Zaimportuj `persist_discharge` z `common`. Dodaj funkcje:

```python
def admit_pet(user, pet_id, now=None, cfg=None):
    """Przyjęcie chorego do szpitala (spec v3 §4.1). Paski ≥ floor, healed_at ustalone teraz."""
    now, cfg = now_or(now), cfg_or(cfg)
    lock_profile(user)
    pet = own_pet(user, pet_id, ('alive',))
    sim = simulate_pet(pet, now, cfg)
    if sim.discharged_at is not None:
        persist_discharge(pet, sim, now)
    if sim.died_at is not None:
        persist_death(pet, sim, now)
        db.session.commit()
        raise PetError('pet_gone', f'Pupil {pet.name} odszedł do gwiazd.', 410)
    if pet.hospital_since is not None:
        raise PetError('in_hospital', f'Pupil {pet.name} już leży w szpitalu.', 409)
    stan = sim.state
    if stan.health >= rules.SICK_BELOW:
        raise PetError('not_sick', f'Pupil {pet.name} jest zdrowy — szpital nie jest potrzebny.', 409)
    prog = float(cfg.hospital['floor'])
    stan = replace(stan, hunger=max(stan.hunger, prog), fun=max(stan.fun, prog), clean=max(stan.clean, prog),
                   awake_until=None)
    godziny = (100.0 - stan.health) / 100.0 * float(cfg.hospital['hours'])
    pet.hospital_since = now
    pet.hospital_healed_at = now + timedelta(hours=godziny)
    pet.hospital_ready_notified_at = None
    pet.awake_until = None
    pet.notify_level = 0
    apply_state(pet, stan, now)
    add_event(user.id, 'admit', now, pet_id=pet.id)
    db.session.commit()
    return pet


def discharge_pet(user, pet_id, now=None, cfg=None):
    """Odbiór ze szpitala (ręczny, w każdej chwili). Gdy wypis już się wyliczył automatycznie → 409."""
    now, cfg = now_or(now), cfg_or(cfg)
    lock_profile(user)
    pet = own_pet(user, pet_id, ('alive',))
    if pet.hospital_since is None:
        raise PetError('not_in_hospital', f'Pupil {pet.name} nie leży w szpitalu.', 409)
    sim = simulate_pet(pet, now, cfg)
    if sim.discharged_at is not None:
        persist_discharge(pet, sim, now)
        if sim.died_at is not None:
            persist_death(pet, sim, now)
        db.session.commit()
        raise PetError('not_in_hospital', f'Pupil {pet.name} wrócił już do domku.', 409)
    persist_discharge(pet, sim, now, manual=True)
    db.session.commit()
    return pet
```

- [ ] **Step 5: `eggs.py`** — `claim_egg(user, source, pet_id=None, now=None, cfg=None, rng=None)`; `now, cfg, rng = now_or(now), cfg_or(cfg), rng_or(rng)`; przy tworzeniu jajka:

```python
    jajko = Pet(user_id=user.id, status='egg', egg_source=source, egg_hours=godziny,
                egg_skin=rng.randrange(len(EGG_SKINS)),
                egg_progress_sec=0, egg_progress_at=now, state_at=now, created_at=now)
```

(import `EGG_SKINS` z `modules.pets.models`, `rng_or` z `common`). W `hatch_egg` w pętli żywych przed `if sim.died_at`:

```python
        sim = simulate_pet(zywy, now, cfg)
        if sim.discharged_at is not None:
            persist_discharge(zywy, sim, now)
```

(gwiazdka dla pupila w szpitalu: `apply_state(istniejacy, stan_teraz, now)` zostaje — `hospital_healed_at` nietknięte.)

- [ ] **Step 6: `state.py`** — w pętli żywych:

```python
        elif pet.status == 'alive':
            sim = simulate_pet(pet, now, cfg)
            if sim.discharged_at is not None and not lite:
                if persist_discharge(pet, sim, now):
                    zapisano_odejscie = True          # ta sama flaga: commit + refresh profilu
            if sim.died_at is None:
                zywe.append(pet_dict(pet, sim.state, now, cfg, discharged=sim.discharged_at is not None))
```

(`lite` z wyliczonym wypisem niczego nie zapisuje — `discharged=True` mówi `pet_dict`, że pupil jest już w domku; zapis zrobi następny pełny odczyt lub cron. Gałęzie `elif lite:` / `else:` dla odejścia zostają jak są.) Dalej:

```python
    poza_szpitalem = [p for p in zywe if p['hospital'] is None]
    auto = most_in_need(poza_szpitalem)
    stan['most_in_need_pet_id'] = auto['id'] if auto else None
    wybrany = None
    if profil is not None and profil.companion_pet_id is not None:
        wybrany = next((p for p in poza_szpitalem if p['id'] == profil.companion_pet_id), None)
```

`needs_care`: warunki na paskach i nastroju licz po `poza_szpitalem`, dopisz `or any(p['hospital']['ready'] for p in zywe if p['hospital'])`. W `config` dopisz `'hospital_hours': int(cfg.hospital['hours']),`.

- [ ] **Step 7: `service.py`** — dopisz `admit_pet, discharge_pet` do importu z `actions` (z `# noqa: F401`).

- [ ] **Step 8: GREEN** — `venv/bin/python -m pytest tests/test_pets_szpital.py tests/test_pets_actions.py tests/test_pets_common.py tests/test_pets_eggs.py tests/test_pets_state.py tests/test_pets_cron.py tests/test_pets_widget_companion.py -q -p no:cacheprovider` → Expected: passed. Każda inna czerwień w plikach pupili wynikająca z usunięcia `heal` — popraw test (nie kod), zapisz w ledgerze jako Ruling.

- [ ] **Step 9: Commit** — `feat(pupile): pobyt w szpitalu w serwisie (przyjecie, odbior, auto-wypis, tesknota), warianty akcji, skorki jajek`.

---

### Task 4: Trasy — sceny świata, API szpitala, wariant

**Files:**
- Modify: `modules/pets/routes.py`
- Modify: `templates/client/pets/home.html` (atrybut `data-scene` na `#petsApp`)
- Test: `tests/test_pets_swiat_trasy.py`

**Interfaces:**
- Consumes: Task 3 (`service.admit_pet`, `service.discharge_pet`, `perform_action(..., variant=)`).
- Produces: GET `/client/pupile`, `/client/pupile/domek`, `/client/pupile/szpital`, `/client/pupile/warsztat`, `/client/pupile/ogrod` (200, ten sam szablon, `#petsApp[data-scene="mapa|domek|szpital|warsztat|ogrod"]`), inne `/client/pupile/<x>` → 404 HTML; POST `/client/pupile/api/<id>/szpital` → `{ok, state}`; POST `/client/pupile/api/<id>/wypis` → `{ok, state}`; POST `/client/pupile/api/<id>/akcja` przyjmuje `variant` (str) i zwraca `variant`; `url_for('pets.home')` = `/client/pupile`, `url_for('pets.scene', scene='domek')` = `/client/pupile/domek`.

- [ ] **Step 1: Testy (RED)** — `tests/test_pets_swiat_trasy.py`:

```python
"""Spec v3 §3.1, §4.5: adresy miejsc świata i API szpitala."""
import re

from tests.pets_helpers import zaloz_profil, zaloz_pupila
from tests.test_pets_routes import _wlacz


def _scena(html):
    return re.search(r'id="petsApp"[^>]*data-scene="([a-z]+)"', html).group(1)


def test_sceny_maja_adresy(client, login, make_user, db):
    login(make_user(profile_completed=True))
    _wlacz(db)
    for sciezka, scena in (('', 'mapa'), ('/domek', 'domek'), ('/szpital', 'szpital'),
                           ('/warsztat', 'warsztat'), ('/ogrod', 'ogrod')):
        r = client.get('/client/pupile' + sciezka)
        assert r.status_code == 200 and _scena(r.data.decode()) == scena, sciezka
    assert client.get('/client/pupile/strych').status_code == 404
    assert client.get('/client/pupile/api').status_code == 404


def test_sceny_za_flaga(client, login, make_user):
    login(make_user(profile_completed=True))
    assert client.get('/client/pupile/szpital').status_code == 404


def test_api_szpital_i_wypis(client, login, make_user, db):
    user = make_user()
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=20.0, health=50.0)
    r = client.post(f'/client/pupile/api/{pet.id}/szpital', json={})
    assert r.status_code == 200 and r.get_json()['state']['pets'][0]['hospital'] is not None
    r = client.post(f'/client/pupile/api/{pet.id}/szpital', json={})
    assert r.status_code == 409 and r.get_json()['error'] == 'in_hospital'
    r = client.post(f'/client/pupile/api/{pet.id}/wypis', json={})
    assert r.status_code == 200 and r.get_json()['state']['pets'][0]['hospital'] is None
    r = client.post(f'/client/pupile/api/{pet.id}/wypis', json={})
    assert r.status_code == 409 and r.get_json()['error'] == 'not_in_hospital'


def test_api_szpital_cudzy_i_zdrowy(client, login, make_user, db):
    wlasciciel = make_user()
    zaloz_profil(wlasciciel)
    cudzy = zaloz_pupila(wlasciciel, health=50.0)
    user = make_user()
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    zdrowy = zaloz_pupila(user, species='mis')
    assert client.post(f'/client/pupile/api/{cudzy.id}/szpital', json={}).status_code == 403
    r = client.post(f'/client/pupile/api/{zdrowy.id}/szpital', json={})
    assert r.status_code == 409 and r.get_json()['error'] == 'not_sick'


def test_api_akcja_z_wariantem(client, login, make_user, db):
    user = make_user()
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=20.0)
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'feed', 'variant': 'ciastko'})
    assert r.status_code == 200 and r.get_json()['variant'] == 'ciastko'
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'feed', 'variant': 7})
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_variant'
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'heal'})
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_action'
```

- [ ] **Step 2: RED** — `venv/bin/python -m pytest tests/test_pets_swiat_trasy.py -q -p no:cacheprovider` → Expected: failures (404 na `/domek`, brak `data-scene`).

- [ ] **Step 3: Implementacja** — w `routes.py` zamień trasę strony:

```python
SCENES = ('domek', 'szpital', 'warsztat', 'ogrod')


def _render_scene(scene):
    stan = _state()
    return render_template(
        'client/pets/home.html',
        title='Moje pupile',
        scene=scene,
        state_json=json.dumps(stan, ensure_ascii=False),
        species_json=_species_json(),
        api_base=API_BASE,
    )


@pets_bp.route('')     # '' zamiast '/': adres /client/pupile bez 308 na wersję ze slashem
@feature_required
def home():
    return _render_scene('mapa')


@pets_bp.route('/<scene>')
@feature_required
def scene(scene):
    if scene not in SCENES:
        abort(404)
    return _render_scene(scene)
```

Nowe endpointy (wzór jak `api_light_candle`):

```python
@pets_bp.route('/api/<int:pet_id>/szpital', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_admit(pet_id):
    service.admit_pet(current_user._get_current_object(), pet_id)
    return jsonify({'ok': True, 'state': _state()})


@pets_bp.route('/api/<int:pet_id>/wypis', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_discharge(pet_id):
    service.discharge_pet(current_user._get_current_object(), pet_id)
    return jsonify({'ok': True, 'state': _state()})
```

W `api_action`:

```python
    variant = dane.get('variant')
    if variant is not None and not isinstance(variant, str):
        raise PetError('bad_variant', 'Nieznany wariant akcji.', 400)
    wynik = service.perform_action(current_user._get_current_object(), pet_id, action,
                                   count=dane.get('count', 1), variant=variant)
```

i w odpowiedzi `'variant': wynik['variant'],`. W `home.html` na `#petsApp` dopisz `data-scene="{{ scene }}"`.

- [ ] **Step 4: GREEN** — `venv/bin/python -m pytest tests/test_pets_swiat_trasy.py tests/test_pets_routes.py tests/test_pets_widget_companion.py -q -p no:cacheprovider` → passed.

- [ ] **Step 5: Commit** — `feat(pupile): adresy miejsc swiata, API przyjecia i odbioru ze szpitala, wariant akcji`.

---

### Task 5: Cron i powiadomienia — szpital

**Files:**
- Modify: `modules/pets/notifications.py`
- Modify: `tests/test_pets_cron.py`

**Interfaces:**
- Consumes: Task 3 (`simulate_pet` z wypisem, `persist_discharge`).
- Produces: koszyk ma klucz `healed` (lista pupili); `build_push_text` mówi „Pupil {imię} wyzdrowiał — odbierz go ze szpitala.” i „Pupil {imię} jest chory — zabierz go do szpitala.”; `push_path(basket) -> str` (jedna z `/client/pupile/szpital`, `/client/pupile/ogrod`, `/client/pupile/domek`) używana w `_wyslij_push`.

- [ ] **Step 1: Testy (RED)** — dopisz do `tests/test_pets_cron.py`:

```python
def _przyjmij(user, pet, now):
    from modules.pets.actions import admit_pet
    return admit_pet(user, pet.id, now=now, cfg=_cfg())


def test_w_szpitalu_bez_alertow_i_push_wyzdrowial_raz(db, make_user):
    from modules.pets.notifications import build_push_text, collect_for_user
    user = make_user(); zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0, health=40.0)
    _przyjmij(user, pet, T0)
    k = collect_for_user(user, T0 + timedelta(hours=1), _cfg())
    db.session.commit()
    assert k['alerts'] == [] and k['healed'] == []
    k = collect_for_user(user, T0 + timedelta(hours=6), _cfg())        # healed po 4,8 h
    db.session.commit()
    assert k['healed'] == [pet] and pet.hospital_ready_notified_at == T0 + timedelta(hours=6)
    assert 'wyzdrowiał — odbierz go ze szpitala' in build_push_text(k)[1]
    k = collect_for_user(user, T0 + timedelta(hours=7), _cfg())
    assert k['healed'] == []


def test_auto_wypis_w_cronie_zapisany(db, make_user):
    from modules.pets.notifications import collect_for_user
    from modules.pets.models import PetEvent
    user = make_user(); zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=20.0, health=50.0)
    _przyjmij(user, pet, T0)
    collect_for_user(user, T0 + timedelta(hours=40), _cfg())
    db.session.commit()
    assert pet.hospital_since is None
    assert PetEvent.query.filter_by(pet_id=pet.id, type='discharge').count() == 1


def test_tekst_chory_i_sciezki_pushu(db, make_user):
    from modules.pets.notifications import (LEVEL_CRITICAL, LEVEL_SAD, LEVEL_SICK, build_push_text,
                                            push_path)
    user = make_user()
    p = zaloz_pupila(user, name='Burek')
    assert 'Pupil Burek jest chory — zabierz go do szpitala.' in build_push_text(_koszyk(user, alerts=[(p, LEVEL_SICK)]))[1]
    assert push_path(_koszyk(user, alerts=[(p, LEVEL_CRITICAL)], deaths=[p])) == '/client/pupile/szpital'
    assert push_path(_koszyk(user, deaths=[p])) == '/client/pupile/ogrod'
    assert push_path(_koszyk(user, healed=[p])) == '/client/pupile/szpital'
    assert push_path(_koszyk(user, eggs_ready=[p])) == '/client/pupile/szpital'
    assert push_path(_koszyk(user, alerts=[(p, LEVEL_SAD)])) == '/client/pupile/domek'
```

oraz w helperze `_koszyk` dopisz `healed=[]` do słownika bazowego.

- [ ] **Step 2: RED** — `venv/bin/python -m pytest tests/test_pets_cron.py -q -p no:cacheprovider` → Expected: failures (`healed`, `push_path`).

- [ ] **Step 3: Implementacja** — w `notifications.py`:
  - `_OPIS_POZIOMU[LEVEL_SICK] = 'jest chory — zabierz go do szpitala'`;
  - `empty_basket` → dodaj `healed=[]`; `basket_is_empty` → dodaj `or basket['healed']`;
  - w `build_push_text` po pętli alertów:

```python
    for pet in basket['healed']:
        zdania.append(f'Pupil {_imie(pet)} wyzdrowiał — odbierz go ze szpitala.')
```

  - nowa funkcja:

```python
def push_path(basket):
    """Gdzie prowadzi zbiorczy push (spec v3 §6.4): najpierw to, co wymaga działania w szpitalu."""
    if any(poziom >= LEVEL_SICK for _, poziom in basket['alerts']):
        return PETS_URL_PATH + '/szpital'
    if basket['deaths'] or basket['rescue_reminders']:
        return PETS_URL_PATH + '/ogrod'
    if basket['healed'] or basket['eggs_ready'] or basket['monthly']:
        return PETS_URL_PATH + '/szpital'
    return PETS_URL_PATH + '/domek'
```

  - w `_wyslij_push` `url=push_path(basket)`;
  - w `collect_for_user` gałąź żywych:

```python
        if pet.status == 'alive':
            sim = simulate_pet(pet, now, cfg)
            if sim.discharged_at is not None:
                persist_discharge(pet, sim, now)
            if sim.died_at is not None:
                persist_death(pet, sim, now)
                pet.death_notified_at = now
                basket['deaths'].append(pet)
                continue
            if pet.hospital_since is not None:
                if pet.hospital_ready_notified_at is None and now >= pet.hospital_healed_at:
                    pet.hospital_ready_notified_at = now
                    basket['healed'].append(pet)
                continue                                  # w szpitalu: bez alertów (spec v3 §6.4)
            poziom = level_of(sim.state)
```

  (import `persist_discharge`; `persist_discharge` robi `expire`, więc `pet.hospital_since` po wypisie czyta się jako `None`).

- [ ] **Step 4: GREEN** — `venv/bin/python -m pytest tests/test_pets_cron.py tests/test_pets_szpital.py -q -p no:cacheprovider` → passed. Potem pełna suita do pliku z `--deselect` znanego DST → Expected: 0 failed.

- [ ] **Step 5: Commit** — `feat(pupile): cron - bez alertow w szpitalu, push wyzdrowial, sciezki pushu do miejsc swiata`.

---

### Task 6 (paczka R — rig, subagent Opus, równolegle z Task 1–5): zachowania potrzeb, dłoń, warianty, skórki, łóżko, nakładka wyklucia

**Files:**
- Modify: `static/js/components/pet-rig.js`, `static/css/components/pet-rig.css`, `static/js/pet/species.js` (tylko jeśli potrzebne nowe części postaci)
- Create: `static/js/components/pet-hatch.js`
- Modify: `static/css/components/modals.css` (sekcja `/* === Pet hatch overlay (v3) === */`; stara sekcja „Pet hatch modal” zostaje do Task 7)
- Modify: `static/dev/pet-rig-demo.html|.css|.js` (galeria nowych stanów do weryfikacji)

**Interfaces (Produces — nazwy wiążące dla Task 7 i 8):**
- `PetRig.NEEDS = ['happy', 'hungry', 'dirty', 'sad', 'bored', 'sick', 'critical', 'sleep']`; `PetRig.POSES = ['stand', 'sit', 'lie', 'bed']`.
- `PetRig.needOf(pet) -> string` — z `pet_dict`: `pet.hospital` → `'sick'` gdy `!pet.hospital.ready`, inaczej `'happy'`; `pet.mood` `krytyczny` → `'critical'`, `chory` → `'sick'`; `pet.asleep` → `'sleep'`; `glodny` → `'hungry'`; `brudny` → `'dirty'`; `smutny` → `'sad'`; `znudzony` → `'bored'`; inaczej `'happy'`.
- `PetRig.mount(container, {species, stage, stars, mood, asleep, size, need, pose, idle})` → rig z dotychczasowymi `update(opts)`, `gesture(name)`, `setStars(n)`, `destroy()`, `el` oraz nowymi: `rig.setNeed(need)`, `rig.setPose(pose)`, `rig.pat() -> Promise` (dłoń: wjeżdża z góry nad głowę, 2–3 klepnięcia, pupil mruży oczy, czasem serduszko; ~1,2 s; kolejne wywołanie w trakcie odświeża animację i zwraca ten sam Promise), `rig.playAction(action, {variant}) -> Promise` dla `feed|play|wash` (każdy z 9 wariantów ma własne rekwizyty i trwa 3–4 s; `reducedMotion()` → ≤ 0,9 s, statyczne rekwizyty) oraz dotychczasowe `wake`, `celebrate`, `hatch`.
- Wygląd potrzeb (na roocie klasa `need-<need>`): `hungry` — dymek z miseczką i „burczenie” (lekkie drganie brzuszka); `dirty` — plamki + muszka krążąca wokół + co kilka s drapanie; `sad` — opuszczone uszy, chmurka z deszczykiem; `bored` — ziewanie, dymek „…”; `sick` — zielonkawy odcień, termometr w buzi, wolniejszy oddech; `critical` — jak `sick` + szare kolory, łezka; `sleep` — zamknięte oczy, „zzz”; `happy` — podskoki co kilka s. `pose: 'lie'` — pupil leży (używane dla `sick`/`critical` w pokoju); `pose: 'bed'` — pupil w łóżeczku szpitalnym z kołderką (rysuje łóżko pod pupilem).
- `PetRig.mountEgg(container, {pct, boosted, ready, size, skin})` — `skin` 0–4 wg `PetRig.EGG_SKINS = ['kropki', 'niebo', 'laczka', 'paski', 'laty']` (wzory ze szkiców: kropki z falką / granat z gwiazdkami i księżycem / jasna zieleń z kwiatkami / różowe pastelowe pasy / kremowe z brązowymi łatkami); pęknięcia i światło wspólne dla skórek.
- `PetRig.VARIANTS = {feed: ['miska', 'jablko', 'ciastko'], play: ['pilka', 'wloczka', 'banki'], wash: ['kapiel', 'prysznic', 'gabka']}` (identyczne z backendem).
- `window.PetHatch.run({skin, hatch, onName}) -> Promise<{result, pet_id, new_achievements}>`:
  - `hatch` — funkcja zwracająca Promise odpowiedzi API `/jajka/<id>/wykluj` (`{result, species, species_name, pet_id, starred_pet_id, new_achievements, state}`), wołana na starcie animacji;
  - sekwencja ~4–5 s: nakładka pełnoekranowa → jajko (w skórce) kołysze się → pęknięcia → ciepłe światło → skorupka odskakuje → pupil (`PetRig.mount` gatunku z odpowiedzi, `stage: 'maluch'`) przeciąga się → serduszka i gwiazdki → dla `new`: pole imienia (1–20 znaków, błąd serwera przy polu; `onName(name) -> Promise` wołane przy zapisie; „Później” zamyka) → zamknięcie; dla `dupe` (~2,5 s): „Znowu {species_name}!” i gwiazdka;
  - błąd `hatch()` → nakładka zamyka się i Promise odrzuca błąd (wołający pokazuje toast);
  - ESC / tło nie zamyka w trakcie żądania; focus trap; `prefers-reduced-motion` → bez kołysania i konfetti, od razu odsłonięcie;
  - style w `modals.css` (light + dark), klasy z prefiksem `pet-hatch-`.

- [ ] **Step 1:** Przeczytaj spec v3 §2, §5, §6.1, §6.3 i obecne `pet-rig.js`/`pet-rig.css` (API i guardy idempotencji zostają; nowe rzeczy addytywnie).
- [ ] **Step 2:** `needOf`, `setNeed`, `setPose` + 8 wyglądów potrzeb i pozy `lie`/`bed` — każdy gatunek × stadium (sprawdź w demo).
- [ ] **Step 3:** Dłoń `pat()` i 9 wariantów akcji (`playAction(action, {variant})`).
- [ ] **Step 4:** 5 skórek jajka w `mountEgg`.
- [ ] **Step 5:** `pet-hatch.js` + sekcja w `modals.css`.
- [ ] **Step 6:** Demo `static/dev/pet-rig-demo.*`: siatka potrzeb × pozy, przyciski wariantów, dłoń, 5 skórek, przycisk „wyklucie (new)” / „(dupe)” na atrapie `hatch()`. Weryfikacja w przeglądarce (statyczny serwer z worktree, port 8765): light/dark, reduced-motion (klasa `.pet-rig-rm` na `<html>` i podmiana `matchMedia`), konsola bez błędów, zrzuty do scratchpadu.
- [ ] **Step 7:** Commity per krok (`feat(pupile): rig - …`). Nie merguj, nie pushuj; raport: commity, zrzuty, rulingi.

---

### Task 7 (paczka W — świat, subagent Opus, po Task 4 i 6): router scen, mapa, domek + panel, szpital, warsztat, ogród

**Files:**
- Modify: `templates/client/pets/home.html` (kontenery scen, link CSS/JS), `static/js/pages/client/pets.js` (router + wspólne akcje; usunięcie starego układu gniazdko/siatka/album/ustawienia)
- Create: `static/js/pet/world/map.js`, `static/js/pet/world/room.js`, `static/js/pet/world/house.js`, `static/js/pet/world/hospital.js`, `static/js/pet/world/workshop.js`, `static/js/pet/world/garden.js`
- Create: `static/css/pages/client/pets-map.css`, `static/css/components/pet-room.css`, `static/css/pages/client/pets-house.css`, `static/css/pages/client/pets-hospital.css`, `static/css/pages/client/pets-workshop.css`, `static/css/pages/client/pets-garden.css`
- Modify: `static/js/components/pet-card.js` + `static/css/components/pet-card.css` (karta → treść panelu pupila; wariant `mini` usunięty), `static/css/pages/client/pets.css` (wspólne: nagłówek sceny, „← Świat”, przejścia), `static/css/components/modals.css` (usunięcie starej sekcji „Pet hatch modal”, jeśli nic jej nie używa)
- Test: `tests/test_pets_swiat_trasy.py` (dopisz asercje o podlinkowanych plikach)

**Interfaces:**
- Consumes: Task 4 (sceny, `data-scene`, API `szpital`/`wypis`/`akcja` z `variant`), Task 3 (`pet.hospital`, `can.admit`, `egg.skin`, `state.config.hospital_hours`, `companion`), Task 6 (`PetRig.*`, `PetHatch.run`), `PetsApi`/`PetsState` z `static/js/pet/pets-core.js` (bez zmian w kontrakcie).
- Produces (dla Task 8): `window.PetRoom.mount(container, {pets, night, compact, mainPetId, onPetClick(petId), interactive}) -> room` z `room.update(pets, {night, mainPetId})`, `room.focus(petId | null)`, `room.pat(petId) -> Promise`, `room.playAction(petId, action, variant) -> Promise`, `room.destroy()`, `room.el`. `compact: true` (widget): mniejsza skala, `mainPetId` duży na środku, max 4 pozostałych w tle + znacznik „+N”, bez spaceru po całej szerokości (lekkie ruchy w miejscu), dymek potrzeby nad głównym; `interactive: false` = klik tylko woła `onPetClick`. Pupile w szpitalu (`pet.hospital`) nie pojawiają się w pokoju.

**Zachowanie (spec v3 §3, §5, §6):**
- Router (`pets.js`): scena z `#petsApp[data-scene]`; `history.pushState` przy wejściu w miejsce, `popstate` przełącza scenę bez przeładowania; `?pupil=ID` na domku otwiera panel (pupil w szpitalu → `replaceState` na `/client/pupile/szpital?pupil=ID`; pupil nieistniejący/odeszły → pokój bez panelu, bez błędu — Review Focus 5); na szpitalu `?pupil=ID` przewija do łóżka. Przejście: zoom w stronę miejsca 300–400 ms (reduced-motion: bez). Każda scena poza mapą ma nagłówek z „← Świat”.
- Mapa: SVG wg szkicu „A. Mapa-plansza” (polanka, ścieżka, drzewka; domek w środku największy; szpital lewo, warsztat prawo, ogród dół); ≤ 640 px wersja pionowa; miejsca jako `<a>` z `aria-label` i celem ≥ 44 px; znaczki: krzyż nad szpitalem (`pets.some(p => p.hospital || p.mood in chory/krytyczny)`), „!” nad szpitalem (jajko `ready`, `eggs_available.length`, `pet.hospital.ready`), serduszko nad domkiem (ktoś `glodny|smutny|brudny|znudzony` poza szpitalem), świeczka nad ogrodem (`album` ma kartę z `can_light`); noc (`state.night.is_night`): granatowe niebo, gwiazdy, księżyc, światło w oknach.
- Domek: `PetRoom.mount` pełny; klik w pupila → `room.focus(id)` + panel (arkusz od dołu na < 1024 px, panel z boku ≥ 1024 px; zamknięcie: przeciągnięcie w dół, klik w pokój, ESC); drugi klik w pupila przy otwartym panelu = `room.pat(id)` + paczka pat do API (jak dziś: debounce 2 s, max 50, `keepalive`, flush na `pagehide`/`beforeunload`).
- Panel (przebudowana `PetCard`): imię (edycja jak dziś), stadium, wiek, gwiazdki, dni opieki, 4 paski (ekstrapolacja z `rates_per_hour`), nastrój słownie; akcje Nakarm / Pobaw się / Umyj — klik rozwija 3 kafelki wariantów (`PetRig.VARIANTS`), wybór → `POST akcja {action, variant}` → `room.playAction(id, action, variant)`; Obudź (gdy `asleep`); „Zabierz do szpitala” (gdy `can.admit`) → `POST szpital` → przejście do szpitala; powód pod nieaktywną akcją; fokus i `aria-disabled` jak dziś (fix pass B).
- Szpital: inkubatornia (jajka w gniazdkach pod lampą, `mountEgg` ze `skin`; kafelki odbioru jak dziś: start/monthly/rescue z imieniem/granted z liczbą; Ogrzej z odliczaniem boostu; Wykluj → `PetHatch.run({skin, hatch: () => PetsApi.post('/jajka/'+id+'/wykluj'), onName: name => PetsApi.post('/'+petId+'/imie', {name})})`, po zamknięciu odznaki jak dziś) i sala chorych (łóżka: `PetRig.mount({... pose: 'bed', need})`, pasek postępu `hospital.progress_pct`, „~N h do wyzdrowienia” z `healed_at`, gotowy: „Gotowy do odbioru” + wyróżniony przycisk „Odbierz” → `POST wypis` → przejście do domku z panelem; przed wyleczeniem „Zabierz wcześniej” (potwierdzenie „Pupil wróci z obecnym zdrowiem”); lista chorych z domku z przyciskiem „Przyjmij”); klik w pupila na łóżku = pat.
- Warsztat: scena stołu z „narzędziami”: ramka (wybór towarzysza: lista żywych poza szpitalem + „automatycznie”, włącznik — `POST /towarzysz` jak dziś), dzwonek (przełącznik „Powiadomienia o pupilach” — `GET/POST /notifications/preferences` jak dziś), książeczka (zasady: noc z `state.config.night_factor`, szpital z `state.config.hospital_hours`, jajka, gwiazdki).
- Ogród: nagrobki na trawie (`mountMemorial` + „Zapal światełko” jak dziś), tablica albumu 8 gatunków (`state.album`; nieodkryte = sylwetka bez animacji), licznik `n/8`.
- Błędy: jak dziś (`pets-core.js` + 409 ciche odświeżenie, 410 toast + odświeżenie, sesja wygasła); `escapeHtml` na komunikatach; zero inline handlerów.
- GA4: `trackEvent('pet_action', {action, mood, variant})`, `trackEvent('pet_hatch', {result})`, nowe: `trackEvent('pet_hospital', {step: 'admit'|'discharge'})` — z guardem `typeof`.

- [ ] **Step 1:** Szkielet routera + mapa (z adresami i znaczkami) + przejścia; wpis `pets-preview-world` w lokalnym `.claude/launch.json` (centrala doda; port 5007, `--repo` = worktree, `--no-night`).
- [ ] **Step 2:** `room.js` + domek + panel (warianty, pat, Obudź, Zabierz do szpitala).
- [ ] **Step 3:** Szpital (inkubatornia z `PetHatch`, sala chorych).
- [ ] **Step 4:** Warsztat i ogród; usunięcie starego układu; dopisanie do `tests/test_pets_swiat_trasy.py` asercji, że `home.html` linkuje `js/pet/world/map.js`, `js/pet/world/room.js`, `js/pet/world/house.js`, `js/pet/world/hospital.js`, `js/pet/world/workshop.js`, `js/pet/world/garden.js`, `js/components/pet-hatch.js` (RED→GREEN).
- [ ] **Step 5:** Weryfikacja w przeglądarce (podgląd SQLite `docs/dev/dev_pets_preview.py`): każda scena dzień/noc (bez `--no-night` dla nocy), 375 / 768 / 1280 px, light/dark, reduced-motion, wstecz/naprzód, `?pupil=` (w tym Review Focus 5), wszystkie akcje i warianty, szpital od przyjęcia do odbioru (przesuń `hospital_healed_at` w bazie podglądu, żeby nie czekać), wyklucie new/dupe, konsola bez błędów; cele ≥ 44 px i brak poziomego scrolla zmierzone w DevTools.
- [ ] **Step 6:** Commity per krok (`feat(pupile): swiat - …`); raport z rulingami.

---

### Task 8 (paczka T — widget i towarzysz, subagent Opus, po Task 7)

**Files:**
- Modify: `static/js/pages/client/pets-widget.js`, `static/css/components/pet-widget.css`, `templates/client/pets/_widget.html` (jeśli trzeba kontenera), `templates/client/dashboard.html` (linki CSS/JS: `pet-room.css`, `js/pet/world/room.js`; bez `pet-card.js`)
- Modify: `static/js/components/pet-companion.js` (pamięć pozycji; pomijanie pupili w szpitalu), `static/css/components/pet-companion.css` (jeśli trzeba)
- Test: `tests/test_pets_widget_companion.py` (asercja na linki dashboardu: `js/pet/world/room.js` jest, `js/components/pet-card.js` nie)

**Interfaces:**
- Consumes: Task 7 (`PetRoom.mount(…, {compact: true, interactive: false, mainPetId, onPetClick})`), Task 3 (`companion.pet_id`, `pet.hospital`, `egg.skin`), Task 6 (`mountEgg({skin})`, `mount({pose: 'bed'})`).
- Produces: nic nowego dla innych zadań.

**Zachowanie (spec v3 §7, §8):**
- Widget: mini-pokój `PetRoom.mount(container, {pets: żywi poza szpitalem, mainPetId: state.companion.pet_id, compact: true, interactive: false, onPetClick})`; klik w pupila → `location.href = '/client/pupile/domek?pupil=' + id`; nagłówek „🐾 Moje pupile” + link „Do świata →” (`/client/pupile`). Bez pasków, bez przycisków, bez pat. Stany bez żywych poza szpitalem: (a) ktoś w szpitalu → łóżko (`mount({pose:'bed'})`) + „Wraca do zdrowia — jeszcze ~N h” lub „Gotowy do odbioru”, klik → `/client/pupile/szpital?pupil=ID`; (b) jajka w inkubacji → inkubator z jajkami w skórkach + „Wykluje się za ~N h” (prognoza jak dziś, mnożnik z `state.config.boost_factor`), klik → `/client/pupile/szpital`; (c) `eggs_available` → jajko z kokardką „Odbierz w szpitalu”; (d) nic → „Następne jajko: za N dni”. Odświeżanie co 5 min i straż kolejności stanów jak dziś.
- Towarzysz: pupil w szpitalu nigdy nie jest towarzyszem (stan już to załatwia; JS nie zakłada inaczej). Pamięć pozycji: `sessionStorage['pets_companion_pos_' + userId] = JSON.stringify({x_ratio, facing, t})` zapisywane przy każdym kroku spaceru i na `pagehide`; przy starcie w trybie `walk`, jeśli zapis < 30 min: `left = x_ratio × dostępna szerokość`, `facing` jak zapisany, **bez przejścia CSS** (klasa wyłączająca transition na pierwszą klatkę), potem spacer dalej; tryb `sit` ignoruje zapis (nie kasuje go). `try/catch` na `sessionStorage`.

- [ ] **Step 1:** Test szablonu dashboardu (RED → GREEN).
- [ ] **Step 2:** Widget na `PetRoom` + 4 stany.
- [ ] **Step 3:** Pamięć pozycji towarzysza.
- [ ] **Step 4:** Weryfikacja w przeglądarce: dashboard (każdy stan widgetu — scenariusze podglądu `domyslny`, `bez-pupili`, `tylko-start` + pupil przyjęty do szpitalu), przejście dashboard → zamówienia → sklep → dashboard: towarzysz stoi w tym samym miejscu; 375 px, dark, reduced-motion; konsola czysta.
- [ ] **Step 5:** Commity (`feat(pupile): widget mini-pokoj …`, `feat(pupile): towarzysz pamieta pozycje …`), raport.

---

### Task 9 (centrala): integracja, podgląd, recenzja, raport

- [ ] **Step 1:** Scal paczki R, W, T (`--no-ff`); bump `CACHE_VERSION` w `static/sw.js` (`v28` → `v29`); rozszerz `docs/dev/dev_pets_preview.py`: scenariusz `szpital` (jeden pupil przyjęty, drugi wyleczony i czekający) + jajka w różnych skórkach.
- [ ] **Step 2:** Pełna suita do pliku z `--deselect` znanego DST → Expected: 0 failed.
- [ ] **Step 3:** Własna weryfikacja w przeglądarce: ścieżka gracza od mapy przez wszystkie miejsca, szpital (przyjęcie → postęp → push „wyzdrowiał” z `flask pets tick --dry-run` na bazie podglądu → odbiór), wyklucie, widget, towarzysz przez 3 strony; 375 px + dark + noc.
- [ ] **Step 4:** Świeża recenzja (backend + frontend, dwa Opusy) zakresu od `4aa7dcc3`; fix pass Critical/Important (TDD dla backendu, repro w przeglądarce dla frontu).
- [ ] **Step 5:** Pamięć projektu, ClickUp 869ffdb58 (komentarz), raport dla Konrada „Sprawdź i zobacz swoje jajko” (jak włączyć podgląd, co przeklikać, rulingi, odroczone). Bez pusha.
