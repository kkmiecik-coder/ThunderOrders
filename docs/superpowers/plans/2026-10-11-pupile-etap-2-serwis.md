# Pupile — Etap 2 (serwis) — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cała logika gry po stronie serwera bez tras i UI: profil i jajka z czterech źródeł,
wyklucie z duplikatami i gwarancją, akcje (karmienie, zabawa, mycie, leczenie, pat pat, obudź),
noc/budzenie przez reguły z etapu 1, dni opieki + seria logowań, kamienie milowe, światełko,
zapis odejścia przy odczycie, słownik stanu dla przyszłego API (§3.5) oraz krok anonimizacji
konta. Po tym etapie etap 4 (trasy) jest cienką warstwą nad gotowymi funkcjami.

**Architecture:** Serwis podzielony na pliki o jednej odpowiedzialności, żeby zadania mogły iść
równolegle: `errors.py` (wyjątek domenowy), `common.py` (czas/konfiguracja/losowość
wstrzykiwalne, **blokada wiersza profilu = mutex użytkownika**, własność pupila, symulacja, zapis
odejścia warunkowym UPDATE, kamienie milowe, serializacja), `eggs.py` (jajka i wyklucie),
`actions.py` (akcje, światełko, imię, towarzysz, przyznanie jajka, anonimizacja), `state.py`
(`state_for_user`). `service.py` to cienka fasada re-eksportująca całość. Zasada z etapu 1 bez
zmian: odczyt nie zapisuje (wyjątek: odejście), stan liczy `rules.simulate()`.

**Tech Stack:** Python 3.12, Flask 3.0, SQLAlchemy 2.0.23 (`with_for_update`, Core `update()`),
pytest na SQLite (fixture `app`, `db`, `make_user` z `tests/conftest.py`).

**Spec:** `docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md` (§2.2–2.7, §3.1–3.3,
§3.5, §3.8, §6, §8, §9 etap 2).

## Global Constraints

- Gałąź bazowa: `feat/pupile` (etap 1 scalony, `b9091275`). Zadania 2–4 idą na gałęziach
  `feat/pupile-e2-jajka`, `feat/pupile-e2-akcje`, `feat/pupile-e2-stan` od **commitu Task 1**
  (centrala poda hash). Pliki każdego zadania są rozłączne — nie dotykaj cudzych.
- Testy **zawsze** przez `/Users/konradkmiecik/Documents/GitHub/ThunderOrders/venv/bin/python -m pytest …`
  z katalogu głównego checkoutu/worktree. Znana porażka niezwiązana: `test_mobile_api_auth.py::
  test_logout_stores_expiry_in_local_time_and_purges_expired` (DST, osobna gałąź).
- Czas: naiwny czas polski; **każda funkcja serwisu przyjmuje `now=None`** (→ `get_local_now()`),
  `cfg=None` (→ `PetConfig.load()`), a losujące `rng=None` (→ `random.SystemRandom()`). Testy
  wstrzykują te parametry, nie monkeypatchują.
- **Każda operacja zapisu zaczyna się od `lock_profile(user)`** (`with_for_update()` na
  `pet_profiles`), dopiero potem czyta żywe gatunki/dostępne jajka. Na SQLite to no-op — testy
  wyścigu nie istnieją; inwariantów pilnują testy sekwencyjne + warunkowe UPDATE-y.
- Commity po polsku z tematem ASCII (`feat(pupile): …`), na końcu linia
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. **Nie pushować** (push = auto-deploy).
- Komunikaty `PetError.message` po polsku, dla użytkownika (trafią 1:1 do JSON w etapie 4).
  Język odejścia: „odszedł do gwiazd", nigdy „zmarł".
- Wywołania po commicie, które same commitują: `user.update_login_streak()` i
  `AchievementService().check_event(...)` — **nigdy w środku transakcji**.

## Review Focus

1. **Pat pat z `count` spoza 1–50 albo nie-liczbą** (`"abc"`, `0`, `-3`, `10**9`) → przycięte do
   zakresu, nie wyjątek 500 (Task 4).
2. **Jajko ratunkowe za cudzego zmarłego pupila** → 403, a licznik/flagi nie ruszone (Task 2).
3. **Wyklucie, gdy wszystkie 8 gatunków żyje i gwarancja aktywna** → duplikat bez błędu, licznik
   gwarancji rośnie dalej (Task 3).
4. **`state_for_user` dla użytkownika bez profilu** (nigdy nie odebrał startowego) → wirtualne
   jajko startowe, puste listy, `needs_care=True`, zero zapisów (Task 6).
5. **Akcja na pupilu, który wg symulacji już odszedł** → odejście zapisane, 410 z komunikatem
   „odszedł do gwiazd", drugi równoległy odczyt nie robi drugiego zdarzenia `die` (Task 4).

---

### Task 1 (centrala): `errors.py`, `common.py`, `action_availability` w `rules.py`, helpery testowe

**Files:**
- Create: `modules/pets/errors.py`
- Create: `modules/pets/common.py`
- Modify: `modules/pets/rules.py` (dopisz `ACTIONS`, `GESTURES_BY_STAGE`, `action_availability`)
- Create: `tests/pets_helpers.py`
- Test: `tests/test_pets_rules.py` (dopisz), `tests/test_pets_common.py`

**Interfaces (produces — pozostałe zadania polegają na tych nazwach 1:1):**
- `modules.pets.errors.PetError(code: str, message: str, status: int = 400)` z atrybutami
  `.code`, `.message`, `.status`.
- `modules.pets.rules`: `ACTIONS = ('feed','play','wash','heal','pat','wake')`,
  `GESTURES_BY_STAGE: dict[str, list[str]]`,
  `action_availability(state, now, cfg, last_heal_at=None) -> (can: dict, reasons: dict)`.
- `modules.pets.common`: stałe `CARE_ACTIONS`, `MILESTONE_CARE_DAYS = (7,14,30,50,100)`,
  `MILESTONE_FIRST_STAR = 1001`, `MILESTONE_STAGE = {'dziecko': 2001, 'dorosly': 2002}`,
  `DEATH_CAUSE = {'hunger': 1, 'fun': 2, 'clean': 3}`, `NAME_MAX = 20`,
  `PAT_MAX_PER_REQUEST = 50`; funkcje `now_or(now)`, `cfg_or(cfg)`, `rng_or(rng)`,
  `get_profile(user) -> PetProfile|None`, `lock_profile(user, required=True) -> PetProfile|None`
  (rzuca `PetError('no_profile', …, 409)`), `own_pet(user, pet_id, statuses) -> Pet`
  (404 `not_found`, 403 `forbidden`, 409 `wrong_status`), `state_of(pet) -> PetState`,
  `simulate_pet(pet, now, cfg) -> SimResult`, `apply_state(pet, state, now)`,
  `persist_death(pet, sim, now) -> bool`, `add_event(user_id, type, now, pet_id=None, value=1)`,
  `add_milestone(pet, code, now)`, `record_stage_milestone(pet, previous_state_at, now, cfg)`,
  `achievements_after_commit(user) -> list[str]`, `iso(dt) -> str|None`,
  `dead_pets_awaiting_rescue(user, now, cfg) -> list[Pet]`,
  `eggs_available(user, profile, now, cfg) -> list[dict]`, `next_monthly_at(profile, cfg)`,
  `egg_progress(pet, now, cfg) -> float`, `egg_dict(pet, now, cfg) -> dict`,
  `pet_dict(pet, state, now, cfg) -> dict`, `memorial_dict(pet, now) -> dict`.
- `tests.pets_helpers`: `T0 = datetime(2026,10,12,8,0)`, `NOC = datetime(2026,10,12,23,30)`,
  `zaloz_profil(user, now=T0) -> PetProfile`, `zaloz_pupila(user, species='kotek', now=T0,
  **pola) -> Pet` (żywy, pełne paski), `zaloz_jajko(user, now=T0, source='monthly', hours=168,
  **pola) -> Pet`, `zaloz_zmarlego(user, species='mis', died_at=T0, **pola) -> Pet`,
  `RngStaly(slug)` (`.choice(seq)` zwraca `slug`, jeśli jest w `seq`, inaczej `seq[0]`; zapisuje
  ostatnie `seq` w `.ostatni_wybor_z`).

- [ ] **Step 1: Failujące testy reguł dostępności akcji**

Dopisz do `tests/test_pets_rules.py`:

```python
# --- dostępność akcji ---

def test_action_availability_dzien_pelny():
    can, reasons = rules.action_availability(PELNY, PON_08, CFG)
    assert can == {'feed': False, 'play': False, 'wash': False, 'heal': False, 'pat': True, 'wake': False}
    assert reasons == {'feed': 'najedzony', 'play': 'nie chce się bawić', 'wash': 'czysty',
                       'heal': 'zdrowy', 'wake': 'nie śpi'}


def test_action_availability_progi_80():
    stan = PetState(hunger=80, fun=80.1, clean=79.9)
    can, _ = rules.action_availability(stan, PON_08, CFG)
    assert can['feed'] is True and can['play'] is False and can['wash'] is True


def test_action_availability_leczenie():
    chory = PetState(health=60)
    can, reasons = rules.action_availability(chory, PON_08, CFG)
    assert can['heal'] is True
    can, reasons = rules.action_availability(chory, PON_08, CFG, last_heal_at=PON_08 - timedelta(hours=11))
    assert can['heal'] is False and reasons['heal'] == 'lek już podany'
    can, _ = rules.action_availability(chory, PON_08, CFG, last_heal_at=PON_08 - timedelta(hours=12))
    assert can['heal'] is True


def test_action_availability_spiacy_tylko_obudz():
    can, reasons = rules.action_availability(PetState(hunger=60), PON_23, CFG)
    assert can == {'feed': False, 'play': False, 'wash': False, 'heal': False, 'pat': False, 'wake': True}
    assert set(reasons.values()) == {'śpi'}


def test_action_availability_obudzony_w_nocy():
    stan = PetState(hunger=60, awake_until=PON_23 + timedelta(minutes=10))
    can, _ = rules.action_availability(stan, PON_23, CFG)
    assert can['feed'] is True and can['wake'] is False


def test_gestures_rosna_ze_stadium():
    g = rules.GESTURES_BY_STAGE
    assert g['maluch'] == ['jump', 'blink', 'sway']
    assert g['dziecko'] == ['jump', 'blink', 'sway', 'spin', 'wave']
    assert g['dorosly'] == ['jump', 'blink', 'sway', 'spin', 'wave', 'dance', 'flip']
    assert rules.ACTIONS == ('feed', 'play', 'wash', 'heal', 'pat', 'wake')
```

- [ ] **Step 2: Uruchom — mają paść**

Run: `venv/bin/python -m pytest tests/test_pets_rules.py -q 2>&1 | tail -2`
Expected: 6 FAIL (`AttributeError: … has no attribute 'action_availability'`).

- [ ] **Step 3: Dopisz do końca `modules/pets/rules.py`**

```python
# ---------------------------------------------------------------------------
# Akcje: dostępność (spec §2.5) i gesty per stadium (§2.7)
# ---------------------------------------------------------------------------

ACTIONS = ('feed', 'play', 'wash', 'heal', 'pat', 'wake')

GESTURES_BY_STAGE = {
    'maluch': ['jump', 'blink', 'sway'],
    'dziecko': ['jump', 'blink', 'sway', 'spin', 'wave'],
    'dorosly': ['jump', 'blink', 'sway', 'spin', 'wave', 'dance', 'flip'],
}


def action_availability(state, now, cfg, last_heal_at=None):
    """`can` + `reasons` (po polsku, dla API §3.5). Śpiący: tylko „Obudź"."""
    can, reasons = {}, {}

    def ustaw(akcja, ok, powod):
        can[akcja] = ok
        if not ok:
            reasons[akcja] = powod

    if is_asleep(state, now, cfg):
        for akcja in ('feed', 'play', 'wash', 'heal', 'pat'):
            ustaw(akcja, False, 'śpi')
        ustaw('wake', True, '')
        return can, reasons

    prog = float(cfg.actions['allow_below'])
    ustaw('feed', state.hunger <= prog, 'najedzony')
    ustaw('play', state.fun <= prog, 'nie chce się bawić')
    ustaw('wash', state.clean <= prog, 'czysty')
    if state.health >= SICK_BELOW:
        ustaw('heal', False, 'zdrowy')
    elif last_heal_at is not None and now < last_heal_at + timedelta(hours=float(cfg.actions['heal_cooldown_h'])):
        ustaw('heal', False, 'lek już podany')
    else:
        ustaw('heal', True, '')
    ustaw('pat', True, '')
    ustaw('wake', False, 'nie śpi')
    return can, reasons
```

- [ ] **Step 4: Uruchom — mają przejść**

Run: `venv/bin/python -m pytest tests/test_pets_rules.py -q 2>&1 | tail -1`
Expected: `62 passed`.

- [ ] **Step 5: Napisz `errors.py` i helpery testowe**

```python
# modules/pets/errors.py
"""Wyjątek domenowy pupili — trasy (etap 4) mapują go na JSON {ok, error, message} i status."""


class PetError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
```

```python
# tests/pets_helpers.py
"""Wspólne klocki testów serwisu pupili (etap 2). Import: `from tests.pets_helpers import …`
(działa, bo `python -m pytest` dodaje katalog repo do sys.path)."""
from datetime import datetime

from extensions import db
from modules.pets.models import Pet, PetProfile

T0 = datetime(2026, 10, 12, 8, 0)      # poniedziałek, dzień
NOC = datetime(2026, 10, 12, 23, 30)   # noc 23–07


def zaloz_profil(user, now=T0):
    profil = PetProfile(user_id=user.id, start_egg_claimed_at=now, last_monthly_egg_at=now, created_at=now)
    db.session.add(profil)
    db.session.commit()
    return profil


def zaloz_pupila(user, species='kotek', now=T0, **pola):
    dane = dict(user_id=user.id, status='alive', species=species, name='Mruczek', egg_source='start',
                egg_hours=48, hatched_at=now, egg_progress_at=now, state_at=now, created_at=now)
    dane.update(pola)
    pet = Pet(**dane)
    db.session.add(pet)
    db.session.commit()
    return pet


def zaloz_jajko(user, now=T0, source='monthly', hours=168, **pola):
    dane = dict(user_id=user.id, status='egg', egg_source=source, egg_hours=hours,
                egg_progress_sec=0, egg_progress_at=now, state_at=now, created_at=now)
    dane.update(pola)
    pet = Pet(**dane)
    db.session.add(pet)
    db.session.commit()
    return pet


def zaloz_zmarlego(user, species='mis', died_at=T0, **pola):
    dane = dict(user_id=user.id, status='dead', species=species, name='Puszek', egg_source='monthly',
                egg_hours=168, hatched_at=died_at, egg_progress_at=died_at, state_at=died_at,
                created_at=died_at, died_at=died_at, health=0.0, hunger=0.0, notify_level=4)
    dane.update(pola)
    pet = Pet(**dane)
    db.session.add(pet)
    db.session.commit()
    return pet


class RngStaly:
    """Atrapa random: zawsze wybiera `slug`, jeśli jest wśród kandydatów; zapamiętuje kandydatów."""

    def __init__(self, slug):
        self.slug = slug
        self.ostatni_wybor_z = None

    def choice(self, seq):
        self.ostatni_wybor_z = list(seq)
        return self.slug if self.slug in seq else seq[0]
```

- [ ] **Step 6: Failujące testy `common.py`**

```python
# tests/test_pets_common.py
"""Wspólne klocki serwisu: blokada profilu, własność, zapis odejścia, jajka dostępne, serializacja."""
from datetime import timedelta

import pytest

from tests.pets_helpers import T0, zaloz_profil, zaloz_pupila, zaloz_zmarlego, zaloz_jajko


def test_lock_profile_wymaga_profilu(db, make_user):
    from modules.pets.common import lock_profile
    from modules.pets.errors import PetError
    user = make_user()
    assert lock_profile(user, required=False) is None
    with pytest.raises(PetError) as e:
        lock_profile(user)
    assert e.value.code == 'no_profile' and e.value.status == 409
    profil = zaloz_profil(user)
    assert lock_profile(user) is profil


def test_own_pet_statusy_i_wlasnosc(db, make_user):
    from modules.pets.common import own_pet
    from modules.pets.errors import PetError
    a, b = make_user(), make_user()
    pet = zaloz_pupila(a)
    assert own_pet(a, pet.id, ('alive',)) is pet
    with pytest.raises(PetError) as e:
        own_pet(b, pet.id, ('alive',))
    assert (e.value.code, e.value.status) == ('forbidden', 403)
    with pytest.raises(PetError) as e:
        own_pet(a, pet.id, ('egg',))
    assert (e.value.code, e.value.status) == ('wrong_status', 409)
    with pytest.raises(PetError) as e:
        own_pet(a, 999999, ('alive',))
    assert (e.value.code, e.value.status) == ('not_found', 404)


def test_persist_death_warunkowy_update(db, make_user):
    from modules.pets import rules
    from modules.pets.common import persist_death, simulate_pet, DEATH_CAUSE
    from modules.pets.config import PetConfig
    from modules.pets.models import PetEvent
    user = make_user()
    profil = zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0)
    profil.companion_pet_id = pet.id
    db.session.commit()
    sim = simulate_pet(pet, T0 + timedelta(hours=80), PetConfig())
    assert sim.died_at is not None
    assert persist_death(pet, sim, T0 + timedelta(hours=80)) is True
    db.session.commit()
    assert pet.status == 'dead' and pet.died_at == sim.died_at and pet.notify_level == 4 and pet.health == 0
    assert profil.companion_pet_id is None
    zdarzenia = PetEvent.query.filter_by(pet_id=pet.id, type='die').all()
    assert len(zdarzenia) == 1 and zdarzenia[0].value == DEATH_CAUSE['hunger']
    # drugi zapis (np. z drugiej karty) nic nie robi
    assert persist_death(pet, sim, T0 + timedelta(hours=81)) is False
    assert PetEvent.query.filter_by(pet_id=pet.id, type='die').count() == 1


def test_eggs_available_bez_profilu_tylko_start(db, make_user):
    from modules.pets.common import eggs_available, next_monthly_at
    from modules.pets.config import PetConfig
    user = make_user()
    assert eggs_available(user, None, T0, PetConfig()) == [{'source': 'start'}]
    assert next_monthly_at(None, PetConfig()) is None


def test_eggs_available_miesieczne_ratunkowe_przyznane(db, make_user):
    from modules.pets.common import eggs_available, next_monthly_at
    from modules.pets.config import PetConfig
    cfg = PetConfig()
    user = make_user()
    profil = zaloz_profil(user, now=T0)
    assert eggs_available(user, profil, T0 + timedelta(days=29), cfg) == []
    assert next_monthly_at(profil, cfg) == T0 + timedelta(days=30)
    zmarly = zaloz_zmarlego(user, died_at=T0 + timedelta(days=1))
    profil.granted_eggs_pending = 2
    db.session.commit()
    dostepne = eggs_available(user, profil, T0 + timedelta(days=30), cfg)
    assert dostepne == [
        {'source': 'monthly'},
        {'source': 'rescue', 'pet_id': zmarly.id, 'pet_name': 'Puszek'},
        {'source': 'granted', 'count': 2},
    ]
    zmarly.rescue_egg_claimed_at = T0 + timedelta(days=2)
    db.session.commit()
    assert all(d['source'] != 'rescue' for d in eggs_available(user, profil, T0 + timedelta(days=30), cfg))


def test_egg_dict_i_pet_dict(db, make_user):
    from modules.pets import rules
    from modules.pets.common import egg_dict, pet_dict, memorial_dict
    from modules.pets.config import PetConfig
    cfg = PetConfig()
    user = make_user()
    jajko = zaloz_jajko(user, now=T0, hours=48, boost_until=T0 + timedelta(hours=8))
    d = egg_dict(jajko, T0 + timedelta(hours=10), cfg)
    assert d['id'] == jajko.id and d['source'] == 'monthly' and d['egg_hours'] == 48
    assert d['progress_pct'] == 37.5 and d['ready'] is False and d['can_warm'] is True and d['boost_until'] is None
    pet = zaloz_pupila(user, stars=2, care_days=12)
    # stan jak z state_of(pet): gwiazdki są częścią PetState, bo wpływają na tempo
    p = pet_dict(pet, rules.PetState(hunger=61.26, fun=40.0, clean=88.0, stars=2), T0, cfg)
    assert p['species'] == 'kotek' and p['name'] == 'Mruczek' and p['stage'] == 'maluch'
    assert p['bars'] == {'hunger': 61.3, 'fun': 40.0, 'clean': 88.0, 'health': 100.0}
    assert p['rates_per_hour']['hunger'] == -3.33 and p['mood'] == 'znudzony' and p['asleep'] is False
    assert p['can']['play'] is True and p['reasons']['wash'] == 'czysty'
    assert p['care_days'] == 12 and p['stars'] == 2 and p['gestures'] == ['jump', 'blink', 'sway']
    assert p['heal_available_at'] is None and p['awake_until'] is None
    zmarly = zaloz_zmarlego(user, died_at=T0, hatched_at=T0 - timedelta(days=60), care_days=41, lights_count=3)
    m = memorial_dict(zmarly, T0 + timedelta(days=1))
    assert m == {'species': 'mis', 'status': 'memorial', 'pet_id': zmarly.id, 'name': 'Puszek',
                 'hatched_at': '2026-08-13', 'died_at': '2026-10-12', 'age_days': 60,
                 'care_days': 41, 'lights_count': 3, 'can_light': True}
```

- [ ] **Step 7: Uruchom — mają paść**

Run: `venv/bin/python -m pytest tests/test_pets_common.py -q 2>&1 | tail -2`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.pets.common'`.

- [ ] **Step 8: Napisz `common.py`**

```python
# modules/pets/common.py
"""Wspólne klocki serwisu pupili.

- czas (`now`), konfiguracja (`cfg`) i losowość (`rng`) są wstrzykiwalne — testy nie
  monkeypatchują get_local_now;
- `lock_profile()` = mutex użytkownika (FOR UPDATE na pet_profiles): każda operacja zapisu
  zaczyna się od niego, zanim przeczyta żywe gatunki / dostępne jajka (spec §6);
- odczyt nie zapisuje; jedyny wyjątek to `persist_death()` warunkowym UPDATE (spec §3.1);
- serializacja do słowników API wg spec §3.5 — etap 4 tylko je zwraca.
"""
import random
from datetime import timedelta

from flask import current_app
from sqlalchemy import func, update

from extensions import db
from modules.auth.models import get_local_now
from modules.pets import rules
from modules.pets.config import PetConfig
from modules.pets.errors import PetError
from modules.pets.models import Pet, PetEvent, PetProfile

CARE_ACTIONS = ('feed', 'play', 'wash', 'heal', 'pat')
MILESTONE_CARE_DAYS = (7, 14, 30, 50, 100)
MILESTONE_FIRST_STAR = 1001
MILESTONE_STAGE = {'dziecko': 2001, 'dorosly': 2002}
DEATH_CAUSE = {'hunger': 1, 'fun': 2, 'clean': 3}   # pet_events.value dla type='die'
NAME_MAX = 20
PAT_MAX_PER_REQUEST = 50


def now_or(now):
    return now if now is not None else get_local_now()


def cfg_or(cfg):
    return cfg if cfg is not None else PetConfig.load()


def rng_or(rng):
    return rng if rng is not None else random.SystemRandom()


def iso(dt):
    return dt.isoformat(timespec='seconds') if dt is not None else None


# ---------------------------------------------------------------------------
# Profil i własność
# ---------------------------------------------------------------------------

def get_profile(user):
    return PetProfile.query.filter_by(user_id=user.id).one_or_none()


def lock_profile(user, required=True):
    """Blokada wiersza profilu na czas transakcji (na SQLite no-op)."""
    profil = PetProfile.query.filter_by(user_id=user.id).with_for_update().one_or_none()
    if profil is None and required:
        raise PetError('no_profile', 'Najpierw odbierz jajko startowe.', 409)
    return profil


def own_pet(user, pet_id, statuses):
    pet = db.session.get(Pet, pet_id) if pet_id is not None else None
    if pet is None:
        raise PetError('not_found', 'Nie ma takiego pupila.', 404)
    if pet.user_id != user.id:
        raise PetError('forbidden', 'To nie Twój pupil.', 403)
    if pet.status not in statuses:
        raise PetError('wrong_status', 'Ta akcja nie pasuje do stanu pupila.', 409)
    return pet


# ---------------------------------------------------------------------------
# Stan i odejście
# ---------------------------------------------------------------------------

def state_of(pet):
    return rules.PetState(hunger=pet.hunger, fun=pet.fun, clean=pet.clean, health=pet.health,
                          stars=pet.stars, awake_until=pet.awake_until)


def simulate_pet(pet, now, cfg):
    return rules.simulate(state_of(pet), cfg, pet.state_at, now)


def apply_state(pet, state, now):
    pet.hunger, pet.fun, pet.clean, pet.health = state.hunger, state.fun, state.clean, state.health
    pet.state_at = now


def persist_death(pet, sim, now):
    """Zapis odejścia warunkowym UPDATE — dwa równoległe odczyty zrobią jedno zdarzenie.

    Zwraca True, gdy to to wywołanie przestawiło status (i dopisało `die` + wyzerowało
    towarzysza). Wołający robi commit.
    """
    stan = sim.state
    przyczyna = next((DEATH_CAUSE[bar] for bar in rules.BARS if getattr(stan, bar) <= 0), 0)
    wynik = db.session.execute(
        update(Pet)
        .where(Pet.id == pet.id, Pet.status == 'alive')
        .values(status='dead', died_at=sim.died_at, notify_level=4,
                hunger=stan.hunger, fun=stan.fun, clean=stan.clean, health=0.0, state_at=now)
    )
    db.session.expire(pet)
    if wynik.rowcount != 1:
        return False
    db.session.execute(
        update(PetProfile)
        .where(PetProfile.user_id == pet.user_id, PetProfile.companion_pet_id == pet.id)
        .values(companion_pet_id=None)
    )
    add_event(pet.user_id, 'die', now, pet_id=pet.id, value=przyczyna)
    return True


# ---------------------------------------------------------------------------
# Zdarzenia, kamienie milowe, odznaki
# ---------------------------------------------------------------------------

def add_event(user_id, type, now, pet_id=None, value=1):
    zdarzenie = PetEvent(pet_id=pet_id, user_id=user_id, type=type, value=value, created_at=now)
    db.session.add(zdarzenie)
    return zdarzenie


def add_milestone(pet, code, now):
    """Trwałe zdarzenie `milestone` (raz na kod na pupila)."""
    istnieje = PetEvent.query.filter_by(pet_id=pet.id, type='milestone', value=code).first()
    if istnieje is None:
        add_event(pet.user_id, 'milestone', now, pet_id=pet.id, value=code)


def record_stage_milestone(pet, previous_state_at, now, cfg):
    """Zmiana stadium między poprzednim zapisem a teraz → kamień milowy nowego stadium."""
    if pet.hatched_at is None:
        return
    stare = rules.stage(pet.hatched_at, previous_state_at, cfg)
    nowe = rules.stage(pet.hatched_at, now, cfg)
    if nowe != stare and nowe in MILESTONE_STAGE:
        add_milestone(pet, MILESTONE_STAGE[nowe], now)


def achievements_after_commit(user):
    """`check_event` commituje sam — wołać PO głównym commicie. Odznaki nie mogą wywrócić akcji."""
    from modules.achievements.services import AchievementService
    try:
        return [a.slug for a in AchievementService().check_event(user, 'pet_event')]
    except Exception:  # noqa: BLE001 — logujemy i jedziemy dalej
        current_app.logger.exception('pets: check_event pet_event nie powiódł się')
        db.session.rollback()
        return []


# ---------------------------------------------------------------------------
# Jajka — dostępność (wspólne dla eggs.py i state.py)
# ---------------------------------------------------------------------------

def dead_pets_awaiting_rescue(user, now, cfg):
    prog = now - timedelta(hours=float(cfg.rescue_hours))
    return (Pet.query
            .filter(Pet.user_id == user.id, Pet.status == 'dead',
                    Pet.rescue_egg_claimed_at.is_(None), Pet.died_at <= prog)
            .order_by(Pet.died_at, Pet.id).all())


def next_monthly_at(profile, cfg):
    if profile is None:
        return None
    return profile.last_monthly_egg_at + timedelta(days=int(cfg.monthly_days))


def eggs_available(user, profile, now, cfg):
    """Lista jajek do odebrania (spec §2.2). Bez profilu: wirtualne startowe."""
    if profile is None:
        return [{'source': 'start'}]
    dostepne = []
    if now >= next_monthly_at(profile, cfg):
        dostepne.append({'source': 'monthly'})
    for zmarly in dead_pets_awaiting_rescue(user, now, cfg):
        dostepne.append({'source': 'rescue', 'pet_id': zmarly.id, 'pet_name': zmarly.name})
    if profile.granted_eggs_pending > 0:
        dostepne.append({'source': 'granted', 'count': int(profile.granted_eggs_pending)})
    return dostepne


def egg_progress(pet, now, cfg):
    return rules.egg_progress_seconds(pet.egg_progress_sec, pet.egg_progress_at, pet.boost_until, now, cfg)


# ---------------------------------------------------------------------------
# Serializacja (spec §3.5)
# ---------------------------------------------------------------------------

def egg_dict(pet, now, cfg):
    postep = egg_progress(pet, now, cfg)
    boost_aktywny = pet.boost_until is not None and now < pet.boost_until
    return {
        'id': pet.id,
        'source': pet.egg_source,
        'egg_hours': int(pet.egg_hours),
        'progress_pct': rules.egg_progress_pct(postep, pet.egg_hours),
        'ready': rules.egg_is_ready(postep, pet.egg_hours),
        'boost_until': iso(pet.boost_until) if boost_aktywny else None,
        'can_warm': not boost_aktywny,
    }


def pet_dict(pet, state, now, cfg):
    can, reasons = rules.action_availability(state, now, cfg, pet.last_heal_at)
    stadium = rules.stage(pet.hatched_at, now, cfg)
    tempo = rules.rates_per_hour(state, now, cfg)
    heal_available_at = None
    if reasons.get('heal') == 'lek już podany':
        heal_available_at = pet.last_heal_at + timedelta(hours=float(cfg.actions['heal_cooldown_h']))
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
        'asleep': rules.is_asleep(state, now, cfg),
        'awake_until': iso(state.awake_until) if state.awake_until and now < state.awake_until else None,
        'can': can,
        'reasons': reasons,
        'heal_available_at': iso(heal_available_at),
        'care_days': int(pet.care_days),
        'gestures': list(rules.GESTURES_BY_STAGE[stadium]),
    }


def memorial_dict(pet, now):
    return {
        'species': pet.species,
        'status': 'memorial',
        'pet_id': pet.id,
        'name': pet.name,
        'hatched_at': pet.hatched_at.date().isoformat() if pet.hatched_at else None,
        'died_at': pet.died_at.date().isoformat() if pet.died_at else None,
        'age_days': rules.age_days(pet.hatched_at, pet.died_at) if pet.hatched_at and pet.died_at else 0,
        'care_days': int(pet.care_days),
        'lights_count': int(pet.lights_count),
        'can_light': pet.last_light_date != now.date(),
    }
```

- [ ] **Step 9: Uruchom — mają przejść**

Run: `venv/bin/python -m pytest tests/test_pets_common.py tests/test_pets_rules.py -q 2>&1 | tail -1`
Expected: `68 passed` (6 common + 62 rules). Jeśli `test_egg_dict_i_pet_dict` różni się o zaokrąglenie
(`61.3` vs `61.26`) — sprawdź, że `bars` zaokrągla do 1 miejsca, a `rates_per_hour` do 2.

- [ ] **Step 10: Commit (centrala)**

```bash
git add modules/pets/errors.py modules/pets/common.py modules/pets/rules.py tests/pets_helpers.py tests/test_pets_common.py tests/test_pets_rules.py
git commit -m "$(cat <<'EOF'
feat(pupile): fundament serwisu - PetError, common.py, dostepnosc akcji

Blokada profilu (mutex uzytkownika), wlasnosc pupila, zapis odejscia
warunkowym UPDATE, kamienie milowe, jajka dostepne, serializacja do API
(spec 3.5); rules.action_availability + gesty per stadium; helpery testow.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

Hash tego commitu to baza dla Task 2–4 (karty).

---

### Task 2: `eggs.py` — odbiór i ogrzewanie jajek

**Files:**
- Create: `modules/pets/eggs.py` (część 1: `claim_egg`, `warm_egg`; `hatch_egg` dochodzi w Task 3
  **w tym samym pliku i tej samej sesji**)
- Test: `tests/test_pets_eggs.py`

**Interfaces:**
- Consumes (Task 1): `common.now_or/cfg_or`, `lock_profile`, `own_pet`, `add_event`,
  `next_monthly_at`, `egg_progress`, `PetError`; `models.EGG_SOURCES`; `rules.egg_is_ready`.
- Produces: `claim_egg(user, source, pet_id=None, now=None, cfg=None) -> Pet` (status `egg`),
  `warm_egg(user, pet_id, now=None, cfg=None) -> Pet`.

- [ ] **Step 1: Failujące testy**

```python
# tests/test_pets_eggs.py
"""Jajka: cztery źródła, odbiór, ogrzewanie, wyklucie z duplikatami i gwarancją (spec §2.2–2.3)."""
from datetime import timedelta

import pytest

from tests.pets_helpers import T0, zaloz_profil, zaloz_pupila, zaloz_zmarlego, zaloz_jajko, RngStaly


def _cfg():
    from modules.pets.config import PetConfig
    return PetConfig()


# --- odbiór ---

def test_startowe_tworzy_profil_i_jajko_48h(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.models import PetProfile, PetEvent
    user = make_user()
    jajko = claim_egg(user, 'start', now=T0, cfg=_cfg())
    profil = PetProfile.query.filter_by(user_id=user.id).one()
    assert profil.start_egg_claimed_at == T0 and profil.last_monthly_egg_at == T0
    assert jajko.status == 'egg' and jajko.egg_source == 'start' and jajko.egg_hours == 48
    assert jajko.egg_progress_sec == 0 and jajko.egg_progress_at == T0 and jajko.boost_until is None
    assert PetEvent.query.filter_by(pet_id=jajko.id, type='claim').count() == 1


def test_startowe_drugi_raz_409(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    claim_egg(user, 'start', now=T0, cfg=_cfg())
    with pytest.raises(PetError) as e:
        claim_egg(user, 'start', now=T0 + timedelta(days=1), cfg=_cfg())
    assert (e.value.code, e.value.status) == ('start_claimed', 409)


def test_miesieczne_tylko_po_30_dniach_od_odbioru_bez_kumulacji(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    profil = zaloz_profil(user, now=T0)
    with pytest.raises(PetError) as e:
        claim_egg(user, 'monthly', now=T0 + timedelta(days=29, hours=23), cfg=_cfg())
    assert e.value.code == 'monthly_not_ready'
    # odebrane po 45 dniach — licznik biegnie od ODBIORU, nie od dostępności
    jajko = claim_egg(user, 'monthly', now=T0 + timedelta(days=45), cfg=_cfg())
    assert jajko.egg_hours == 168 and profil.last_monthly_egg_at == T0 + timedelta(days=45)
    with pytest.raises(PetError):
        claim_egg(user, 'monthly', now=T0 + timedelta(days=60), cfg=_cfg())
    assert claim_egg(user, 'monthly', now=T0 + timedelta(days=75), cfg=_cfg()).status == 'egg'


def test_miesieczne_bez_profilu_409(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    with pytest.raises(PetError) as e:
        claim_egg(user, 'monthly', now=T0, cfg=_cfg())
    assert e.value.code == 'no_profile'


def test_ratunkowe_od_razu_jedno_na_odejscie(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    profil = zaloz_profil(user)
    zmarly = zaloz_zmarlego(user, died_at=T0 + timedelta(days=3))
    jajko = claim_egg(user, 'rescue', pet_id=zmarly.id, now=T0 + timedelta(days=3, minutes=1), cfg=_cfg())
    assert jajko.egg_source == 'rescue' and jajko.egg_hours == 168
    assert zmarly.rescue_egg_claimed_at == T0 + timedelta(days=3, minutes=1)
    assert profil.last_monthly_egg_at == T0   # nie rusza miesięcznego
    with pytest.raises(PetError) as e:
        claim_egg(user, 'rescue', pet_id=zmarly.id, now=T0 + timedelta(days=4), cfg=_cfg())
    assert e.value.code == 'rescue_claimed'


def test_ratunkowe_z_opoznieniem_gdy_rescue_hours_dodatnie(db, make_user):
    from modules.pets.config import PetConfig
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    cfg = PetConfig(rescue_hours=24)
    user = make_user()
    zaloz_profil(user)
    zmarly = zaloz_zmarlego(user, died_at=T0)
    with pytest.raises(PetError) as e:
        claim_egg(user, 'rescue', pet_id=zmarly.id, now=T0 + timedelta(hours=23), cfg=cfg)
    assert e.value.code == 'rescue_not_ready'
    assert claim_egg(user, 'rescue', pet_id=zmarly.id, now=T0 + timedelta(hours=24), cfg=cfg).status == 'egg'


def test_ratunkowe_za_cudzego_pupila_403(db, make_user):
    """Review Focus 2."""
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    a, b = make_user(), make_user()
    zaloz_profil(a)
    zaloz_profil(b)
    zmarly = zaloz_zmarlego(a, died_at=T0)
    with pytest.raises(PetError) as e:
        claim_egg(b, 'rescue', pet_id=zmarly.id, now=T0 + timedelta(hours=1), cfg=_cfg())
    assert (e.value.code, e.value.status) == ('forbidden', 403)
    assert zmarly.rescue_egg_claimed_at is None


def test_ratunkowe_bez_pet_id_400(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    zaloz_profil(user)
    with pytest.raises(PetError) as e:
        claim_egg(user, 'rescue', now=T0, cfg=_cfg())
    assert e.value.code == 'pet_required' and e.value.status == 400


def test_przyznane_zmniejsza_licznik(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    profil = zaloz_profil(user)
    profil.granted_eggs_pending = 1
    db.session.commit()
    jajko = claim_egg(user, 'granted', now=T0, cfg=_cfg())
    assert jajko.egg_source == 'granted' and profil.granted_eggs_pending == 0
    with pytest.raises(PetError) as e:
        claim_egg(user, 'granted', now=T0, cfg=_cfg())
    assert e.value.code == 'nothing_granted'


def test_nieznane_zrodlo_400(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    with pytest.raises(PetError) as e:
        claim_egg(user, 'zloty', now=T0, cfg=_cfg())
    assert e.value.code == 'bad_source'


def test_kilka_jajek_moze_inkubowac_sie_naraz(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.models import Pet
    user = make_user()
    profil = zaloz_profil(user, now=T0 - timedelta(days=31))
    profil.granted_eggs_pending = 1
    db.session.commit()
    claim_egg(user, 'monthly', now=T0, cfg=_cfg())
    claim_egg(user, 'granted', now=T0, cfg=_cfg())
    assert Pet.query.filter_by(user_id=user.id, status='egg').count() == 2


# --- ogrzewanie ---

def test_ogrzej_zapisuje_postep_i_boost_8h(db, make_user):
    from modules.pets.eggs import warm_egg
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user)
    jajko = zaloz_jajko(user, now=T0)
    warm_egg(user, jajko.id, now=T0 + timedelta(hours=2), cfg=_cfg())
    assert jajko.egg_progress_sec == 2 * 3600 and jajko.egg_progress_at == T0 + timedelta(hours=2)
    assert jajko.boost_until == T0 + timedelta(hours=10)
    assert PetEvent.query.filter_by(pet_id=jajko.id, type='warm').count() == 1


def test_ogrzej_drugi_raz_dopiero_po_wygasnieciu(db, make_user):
    from modules.pets.eggs import warm_egg
    from modules.pets.errors import PetError
    user = make_user()
    zaloz_profil(user)
    jajko = zaloz_jajko(user, now=T0)
    warm_egg(user, jajko.id, now=T0, cfg=_cfg())
    with pytest.raises(PetError) as e:
        warm_egg(user, jajko.id, now=T0 + timedelta(hours=7, minutes=59), cfg=_cfg())
    assert e.value.code == 'boost_active'
    warm_egg(user, jajko.id, now=T0 + timedelta(hours=8), cfg=_cfg())
    # 8 h ×2 zapisane w postępie, nowy boost od 8 h
    assert jajko.egg_progress_sec == 16 * 3600 and jajko.boost_until == T0 + timedelta(hours=16)


def test_ogrzej_tylko_jajko_i_tylko_swoje(db, make_user):
    from modules.pets.eggs import warm_egg
    from modules.pets.errors import PetError
    a, b = make_user(), make_user()
    zaloz_profil(a)
    zaloz_profil(b)
    pupil = zaloz_pupila(a)
    with pytest.raises(PetError) as e:
        warm_egg(a, pupil.id, now=T0, cfg=_cfg())
    assert e.value.code == 'wrong_status'
    jajko = zaloz_jajko(a)
    with pytest.raises(PetError) as e:
        warm_egg(b, jajko.id, now=T0, cfg=_cfg())
    assert e.value.status == 403
```

- [ ] **Step 2: Uruchom — mają paść**

Run: `…/venv/bin/python -m pytest tests/test_pets_eggs.py -q 2>&1 | tail -2`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.pets.eggs'`.

- [ ] **Step 3: Napisz `eggs.py` (część 1)**

```python
# modules/pets/eggs.py
"""Jajka: odbiór z czterech źródeł, ogrzewanie, wyklucie (spec §2.2–2.3).

Każda funkcja zapisu zaczyna się od lock_profile() — mutex użytkownika. Odbiór
startowego tworzy profil (jedyne miejsce, gdzie profil powstaje).
"""
from datetime import timedelta

from extensions import db
from modules.pets import rules
from modules.pets.common import (
    MILESTONE_FIRST_STAR, achievements_after_commit, add_event, add_milestone, apply_state,
    cfg_or, egg_progress, lock_profile, next_monthly_at, now_or, own_pet, rng_or,
)
from modules.pets.errors import PetError
from modules.pets.models import EGG_SOURCES, Pet, PetProfile
from modules.pets.species import SPECIES_BY_SLUG, SPECIES_SLUGS


def claim_egg(user, source, pet_id=None, now=None, cfg=None):
    """Odbiór jajka. Zwraca nowy wiersz Pet ze statusem `egg`."""
    now, cfg = now_or(now), cfg_or(cfg)
    if source not in EGG_SOURCES:
        raise PetError('bad_source', 'Nieznane źródło jajka.')
    profil = lock_profile(user, required=(source != 'start'))

    if source == 'start':
        if profil is not None:
            raise PetError('start_claimed', 'Jajko startowe już odebrane.', 409)
        profil = PetProfile(user_id=user.id, start_egg_claimed_at=now, last_monthly_egg_at=now, created_at=now)
        db.session.add(profil)
        db.session.flush()
        godziny = int(cfg.start_egg_hours)
    elif source == 'monthly':
        if now < next_monthly_at(profil, cfg):
            raise PetError('monthly_not_ready', 'Miesięczne jajko jeszcze nie jest gotowe.', 409)
        profil.last_monthly_egg_at = now
        profil.monthly_notified_at = None
        godziny = int(cfg.egg_hours)
    elif source == 'rescue':
        if pet_id is None:
            raise PetError('pet_required', 'Wskaż pupila, za którego odbierasz jajko ratunkowe.')
        zmarly = own_pet(user, pet_id, ('dead',))
        if zmarly.rescue_egg_claimed_at is not None:
            raise PetError('rescue_claimed', 'Jajko ratunkowe za tego pupila już odebrane.', 409)
        if now < zmarly.died_at + timedelta(hours=float(cfg.rescue_hours)):
            raise PetError('rescue_not_ready', 'Jajko ratunkowe nie jest jeszcze gotowe.', 409)
        zmarly.rescue_egg_claimed_at = now
        godziny = int(cfg.egg_hours)
    else:  # granted
        if profil.granted_eggs_pending <= 0:
            raise PetError('nothing_granted', 'Nie masz przyznanych jajek.', 409)
        profil.granted_eggs_pending -= 1
        godziny = int(cfg.egg_hours)

    jajko = Pet(user_id=user.id, status='egg', egg_source=source, egg_hours=godziny,
                egg_progress_sec=0, egg_progress_at=now, state_at=now, created_at=now)
    db.session.add(jajko)
    db.session.flush()
    add_event(user.id, 'claim', now, pet_id=jajko.id)
    db.session.commit()
    return jajko


def warm_egg(user, pet_id, now=None, cfg=None):
    """Ogrzej: zapisuje dotychczasowy postęp i włącza ×factor na boost.hours."""
    now, cfg = now_or(now), cfg_or(cfg)
    lock_profile(user)
    jajko = own_pet(user, pet_id, ('egg',))
    if jajko.boost_until is not None and now < jajko.boost_until:
        raise PetError('boost_active', 'Jajko jest już ogrzane — poczekaj, aż ciepło się skończy.', 409)
    jajko.egg_progress_sec = int(egg_progress(jajko, now, cfg))
    jajko.egg_progress_at = now
    jajko.boost_until = now + timedelta(hours=float(cfg.boost['hours']))
    add_event(user.id, 'warm', now, pet_id=jajko.id)
    db.session.commit()
    return jajko
```

- [ ] **Step 4: Uruchom — testy odbioru i ogrzewania mają przejść**

Run: `…/venv/bin/python -m pytest tests/test_pets_eggs.py -q 2>&1 | tail -1`
Expected: `14 passed`.

- [ ] **Step 5: Commit**

```bash
git add modules/pets/eggs.py tests/test_pets_eggs.py
git commit -m "$(cat <<'EOF'
feat(pupile): eggs.py - odbior jajek z czterech zrodel i ogrzewanie

claim_egg tworzy profil przy startowym (48 h), miesieczne co 30 dni od
odbioru bez kumulacji, ratunkowe jedno na odejscie bez ruszania
miesiecznego, przyznane z licznika; warm_egg zapisuje postep i boost x2/8 h.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `eggs.py` — wyklucie z duplikatami i gwarancją

**Files:**
- Modify: `modules/pets/eggs.py` (dopisz `hatch_egg`)
- Test: `tests/test_pets_eggs.py` (dopisz)

**Interfaces:**
- Produces: `hatch_egg(user, pet_id, now=None, cfg=None, rng=None) -> dict` z kluczami
  `result` (`'new'|'dupe'`), `species`, `pet` (Pet: nowy żywy albo `merged` jajko),
  `starred_pet` (Pet|None), `new_achievements` (list[str]).

- [ ] **Step 1: Failujące testy**

Dopisz do `tests/test_pets_eggs.py`:

```python
# --- wyklucie ---

def _gotowe_jajko(user, now=T0):
    # 168 h postępu zapisane → gotowe od razu
    return zaloz_jajko(user, now=now, egg_progress_sec=168 * 3600)


def test_wykluj_niegotowe_409(db, make_user):
    from modules.pets.eggs import hatch_egg
    from modules.pets.errors import PetError
    user = make_user()
    zaloz_profil(user)
    jajko = zaloz_jajko(user, now=T0)
    with pytest.raises(PetError) as e:
        hatch_egg(user, jajko.id, now=T0 + timedelta(hours=100), cfg=_cfg(), rng=RngStaly('kotek'))
    assert e.value.code == 'egg_not_ready'


def test_wykluj_nowy_gatunek(db, make_user):
    from modules.pets.eggs import hatch_egg
    from modules.pets.models import PetEvent, PetProfile
    user = make_user()
    zaloz_profil(user)
    jajko = _gotowe_jajko(user)
    rng = RngStaly('kotek')
    wynik = hatch_egg(user, jajko.id, now=T0 + timedelta(hours=1), cfg=_cfg(), rng=rng)
    assert wynik['result'] == 'new' and wynik['species'] == 'kotek' and wynik['starred_pet'] is None
    from modules.pets.species import SPECIES_SLUGS
    assert set(rng.ostatni_wybor_z) == set(SPECIES_SLUGS)   # bez gwarancji: losowanie z całej ósemki
    pet = wynik['pet']
    assert pet.status == 'alive' and pet.species == 'kotek' and pet.name == 'Kotek'
    assert pet.hatched_at == T0 + timedelta(hours=1) and pet.state_at == T0 + timedelta(hours=1)
    assert (pet.hunger, pet.fun, pet.clean, pet.health) == (100.0, 100.0, 100.0, 100.0)
    assert PetEvent.query.filter_by(pet_id=pet.id, type='hatch_new').count() == 1
    assert PetProfile.query.filter_by(user_id=user.id).one().dupes_in_row == 0
    assert wynik['new_achievements'] == []   # metryki pet_event dochodzą w etapie 6


def test_wykluj_duplikat_daje_gwiazdke_i_merged(db, make_user):
    from modules.pets.eggs import hatch_egg
    from modules.pets.models import PetEvent, PetProfile
    from modules.pets.common import MILESTONE_FIRST_STAR
    user = make_user()
    zaloz_profil(user)
    zywy = zaloz_pupila(user, species='kotek')
    jajko = _gotowe_jajko(user)
    wynik = hatch_egg(user, jajko.id, now=T0 + timedelta(hours=1), cfg=_cfg(), rng=RngStaly('kotek'))
    assert wynik['result'] == 'dupe' and wynik['starred_pet'] is zywy
    assert zywy.stars == 1
    assert jajko.status == 'merged' and jajko.species == 'kotek' and jajko.merged_into_pet_id == zywy.id
    assert PetProfile.query.filter_by(user_id=user.id).one().dupes_in_row == 1
    assert PetEvent.query.filter_by(pet_id=jajko.id, type='hatch_dupe').count() == 1
    assert PetEvent.query.filter_by(pet_id=zywy.id, type='merge', value=1).count() == 1
    assert PetEvent.query.filter_by(pet_id=zywy.id, type='milestone', value=MILESTONE_FIRST_STAR).count() == 1


def test_gwiazdki_max_5(db, make_user):
    from modules.pets.eggs import hatch_egg
    user = make_user()
    zaloz_profil(user)
    zywy = zaloz_pupila(user, species='kotek', stars=5)
    jajko = _gotowe_jajko(user)
    hatch_egg(user, jajko.id, now=T0, cfg=_cfg(), rng=RngStaly('kotek'))
    assert zywy.stars == 5


def test_gwarancja_po_dwoch_duplikatach(db, make_user):
    from modules.pets.eggs import hatch_egg
    user = make_user()
    profil = zaloz_profil(user)
    zaloz_pupila(user, species='kotek')
    zaloz_pupila(user, species='mis')
    profil.dupes_in_row = 2
    db.session.commit()
    jajko = _gotowe_jajko(user)
    rng = RngStaly('kotek')   # chce kotka, ale gwarancja nie pozwoli
    wynik = hatch_egg(user, jajko.id, now=T0, cfg=_cfg(), rng=rng)
    assert set(rng.ostatni_wybor_z) == {'wiewiorka', 'kroliczek', 'szczeniak', 'piesek', 'kurczaczek', 'czarny-kotek'}
    assert wynik['result'] == 'new' and wynik['species'] != 'kotek'
    assert profil.dupes_in_row == 0


def test_gwarancja_liczy_zmarlych_jako_brakujacych(db, make_user):
    from modules.pets.eggs import hatch_egg
    user = make_user()
    profil = zaloz_profil(user)
    for slug in ('wiewiorka', 'kroliczek', 'szczeniak', 'piesek', 'kotek', 'kurczaczek', 'czarny-kotek'):
        zaloz_pupila(user, species=slug)
    zaloz_zmarlego(user, species='mis', died_at=T0 - timedelta(days=1))
    profil.dupes_in_row = 2
    db.session.commit()
    rng = RngStaly('kotek')
    wynik = hatch_egg(user, _gotowe_jajko(user).id, now=T0, cfg=_cfg(), rng=rng)
    assert rng.ostatni_wybor_z == ['mis'] and wynik['result'] == 'new' and wynik['species'] == 'mis'


def test_wszystkie_osiem_zyje_gwarancja_nie_ma_z_czego(db, make_user):
    """Review Focus 3."""
    from modules.pets.eggs import hatch_egg
    from modules.pets.species import SPECIES_SLUGS
    user = make_user()
    profil = zaloz_profil(user)
    for slug in SPECIES_SLUGS:
        zaloz_pupila(user, species=slug)
    profil.dupes_in_row = 2
    db.session.commit()
    rng = RngStaly('mis')
    wynik = hatch_egg(user, _gotowe_jajko(user).id, now=T0, cfg=_cfg(), rng=rng)
    assert len(rng.ostatni_wybor_z) == 8 and wynik['result'] == 'dupe'
    assert profil.dupes_in_row == 3


def test_licznik_duplikatow_ponizej_progu_losuje_ze_wszystkich(db, make_user):
    from modules.pets.eggs import hatch_egg
    user = make_user()
    profil = zaloz_profil(user)
    zaloz_pupila(user, species='kotek')
    profil.dupes_in_row = 1
    db.session.commit()
    rng = RngStaly('kotek')
    wynik = hatch_egg(user, _gotowe_jajko(user).id, now=T0, cfg=_cfg(), rng=rng)
    assert len(rng.ostatni_wybor_z) == 8 and wynik['result'] == 'dupe' and profil.dupes_in_row == 2


def test_nigdy_dwa_zywe_tego_samego_gatunku(db, make_user):
    from modules.pets.eggs import hatch_egg
    from modules.pets.models import Pet
    user = make_user()
    zaloz_profil(user)
    zaloz_pupila(user, species='kotek')
    from modules.pets.config import PetConfig
    bez_gwarancji = PetConfig(pity_after=99)   # izolujemy inwariant od gwarancji (ta po 2 dupach dałaby nowy gatunek)
    for _ in range(3):
        hatch_egg(user, _gotowe_jajko(user).id, now=T0, cfg=bez_gwarancji, rng=RngStaly('kotek'))
    assert Pet.query.filter_by(user_id=user.id, status='alive', species='kotek').count() == 1
    assert Pet.query.filter_by(user_id=user.id, status='merged').count() == 3


def test_wykluj_cudze_jajko_403(db, make_user):
    from modules.pets.eggs import hatch_egg
    from modules.pets.errors import PetError
    a, b = make_user(), make_user()
    zaloz_profil(a)
    zaloz_profil(b)
    jajko = _gotowe_jajko(a)
    with pytest.raises(PetError) as e:
        hatch_egg(b, jajko.id, now=T0, cfg=_cfg(), rng=RngStaly('kotek'))
    assert e.value.status == 403
```

- [ ] **Step 2: Uruchom — mają paść**

Run: `…/venv/bin/python -m pytest tests/test_pets_eggs.py -q 2>&1 | tail -2`
Expected: 10 FAIL (`ImportError: cannot import name 'hatch_egg'`).

- [ ] **Step 3: Dopisz `hatch_egg` do `eggs.py`**

```python
def hatch_egg(user, pet_id, now=None, cfg=None, rng=None):
    """Wyklucie: losowanie gatunku, duplikat → gwiazdka, gwarancja po `pity_after` duplikatach."""
    now, cfg, rng = now_or(now), cfg_or(cfg), rng_or(rng)
    profil = lock_profile(user)
    jajko = own_pet(user, pet_id, ('egg',))
    if not rules.egg_is_ready(egg_progress(jajko, now, cfg), jajko.egg_hours):
        raise PetError('egg_not_ready', 'Jajko jeszcze się nie wykluło.', 409)

    zywe = {p.species: p for p in Pet.query.filter_by(user_id=user.id, status='alive').all()}
    kandydaci = list(SPECIES_SLUGS)
    if profil.dupes_in_row >= int(cfg.pity_after):
        brakujace = [slug for slug in SPECIES_SLUGS if slug not in zywe]
        if brakujace:
            kandydaci = brakujace
    wybrany = rng.choice(kandydaci)

    if wybrany in zywe:
        istniejacy = zywe[wybrany]
        istniejacy.stars = min(int(istniejacy.stars) + 1, int(cfg.max_stars))
        jajko.status = 'merged'
        jajko.species = wybrany
        jajko.merged_into_pet_id = istniejacy.id
        jajko.hatched_at = now
        profil.dupes_in_row += 1
        add_event(user.id, 'hatch_dupe', now, pet_id=jajko.id)
        add_event(user.id, 'merge', now, pet_id=istniejacy.id, value=istniejacy.stars)
        if istniejacy.stars == 1:
            add_milestone(istniejacy, MILESTONE_FIRST_STAR, now)
        wynik, starred = 'dupe', istniejacy
    else:
        jajko.status = 'alive'
        jajko.species = wybrany
        jajko.name = SPECIES_BY_SLUG[wybrany].name
        jajko.hatched_at = now
        apply_state(jajko, rules.PetState(), now)
        profil.dupes_in_row = 0
        add_event(user.id, 'hatch_new', now, pet_id=jajko.id)
        wynik, starred = 'new', None

    db.session.commit()
    nowe_odznaki = achievements_after_commit(user)
    return {'result': wynik, 'species': wybrany, 'pet': jajko, 'starred_pet': starred,
            'new_achievements': nowe_odznaki}
```

- [ ] **Step 4: Uruchom — mają przejść**

Run: `…/venv/bin/python -m pytest tests/test_pets_eggs.py -q 2>&1 | tail -1`
Expected: `24 passed`.

- [ ] **Step 5: Commit**

```bash
git add modules/pets/eggs.py tests/test_pets_eggs.py
git commit -m "$(cat <<'EOF'
feat(pupile): hatch_egg - losowanie, duplikat = gwiazdka, gwarancja po 2

Losowanie rowne z 8 gatunkow; duplikat wtapia jajko (merged) w zywego
i daje gwiazdke (max 5) + kamien milowy pierwszej gwiazdki; po 2 duplikatach
z rzedu losowanie tylko z gatunkow bez zywego pupila. Nigdy 2 zywe tego
samego gatunku.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `actions.py` — akcje opieki, odejście przy akcji, dni opieki, seria logowań

**Files:**
- Create: `modules/pets/actions.py` (część 1: `perform_action`; reszta w Task 5 **w tym samym
  pliku i tej samej sesji**)
- Test: `tests/test_pets_actions.py`

**Interfaces:**
- Consumes (Task 1): `common.*` (`lock_profile`, `own_pet`, `simulate_pet`, `apply_state`,
  `persist_death`, `add_event`, `add_milestone`, `record_stage_milestone`,
  `achievements_after_commit`, `CARE_ACTIONS`, `MILESTONE_CARE_DAYS`, `PAT_MAX_PER_REQUEST`),
  `rules.action_availability`, `rules.ACTIONS`; `User.update_login_streak()` (commituje sam).
- Produces: `perform_action(user, pet_id, action, count=1, now=None, cfg=None) -> dict`
  z kluczami `pet` (Pet), `accepted` (int — zaliczone klepnięcia; 1 dla innych akcji),
  `first_care_today` (bool), `new_achievements` (list[str]).

- [ ] **Step 1: Failujące testy**

```python
# tests/test_pets_actions.py
"""Akcje opieki (spec §2.5), dni opieki + seria logowań, kamienie milowe, odejście przy akcji."""
from datetime import date, timedelta

import pytest

from tests.pets_helpers import T0, NOC, zaloz_profil, zaloz_pupila, zaloz_zmarlego


def _cfg():
    from modules.pets.config import PetConfig
    return PetConfig()


def _akcja(user, pet, akcja, now=T0, **kw):
    from modules.pets.actions import perform_action
    return perform_action(user, pet.id, akcja, now=now, cfg=_cfg(), **kw)


# --- karmienie / zabawa / mycie ---

def test_nakarm_plus_50_i_zasada_80(db, make_user):
    from modules.pets.errors import PetError
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=20.0)
    wynik = _akcja(user, pet, 'feed', now=T0 + timedelta(hours=1))
    # 20 − 4.17 (godzina spadku) + 50 = 65.83
    assert abs(pet.hunger - 65.83) < 0.05 and pet.state_at == T0 + timedelta(hours=1)
    assert wynik['accepted'] == 1
    _akcja(user, pet, 'feed', now=T0 + timedelta(hours=1))      # 65.8 ≤ 80 → druga miseczka
    assert pet.hunger == 100.0
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'feed', now=T0 + timedelta(hours=1))  # 100 > 80 → najedzony
    assert (e.value.code, e.value.status, e.value.message) == ('not_available', 409, 'najedzony')


def test_dwie_miseczki_z_zera(db, make_user):
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0, health=90.0)
    _akcja(user, pet, 'feed')
    assert pet.hunger == 50.0
    _akcja(user, pet, 'feed')
    assert pet.hunger == 100.0


def test_zabawa_i_mycie(db, make_user):
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, fun=30.0, clean=10.0)
    _akcja(user, pet, 'play')
    assert pet.fun == 80.0
    _akcja(user, pet, 'wash')
    assert pet.clean == 100.0


# --- leczenie ---

def test_wylecz_plus_40_co_12h_tylko_chory(db, make_user):
    from modules.pets.errors import PetError
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0, health=50.0)
    _akcja(user, pet, 'heal')
    assert pet.health == 90.0 and pet.last_heal_at == T0
    pet.health = 50.0
    db.session.commit()
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'heal', now=T0 + timedelta(hours=11))
    assert e.value.message == 'lek już podany'
    pet.health = 60.0
    pet.state_at = T0 + timedelta(hours=12)
    db.session.commit()
    _akcja(user, pet, 'heal', now=T0 + timedelta(hours=12))
    assert pet.health == 100.0
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'heal', now=T0 + timedelta(hours=25))
    assert e.value.message == 'zdrowy'


# --- pat pat ---

def test_pat_pat_paczki_limit_60_na_godzine(db, make_user):
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, fun=50.0)
    w1 = _akcja(user, pet, 'pat', count=40)
    assert w1['accepted'] == 40 and pet.fun == 60.0
    w2 = _akcja(user, pet, 'pat', now=T0 + timedelta(minutes=10), count=50)
    assert w2['accepted'] == 20   # limit 60/h
    w3 = _akcja(user, pet, 'pat', now=T0 + timedelta(minutes=20), count=5)
    assert w3['accepted'] == 0    # animacja tak, przyrost nie
    assert PetEvent.query.filter_by(pet_id=pet.id, type='pat').count() == 2   # 0 nie loguje
    w4 = _akcja(user, pet, 'pat', now=T0 + timedelta(hours=1, minutes=1), count=10)
    assert w4['accepted'] == 10   # okno godziny minęło


@pytest.mark.parametrize('count,oczekiwane', [(0, 1), (-3, 1), (10 ** 9, 50), ('abc', 1), (None, 1), ('7', 7)])
def test_pat_count_przyciety_bez_wyjatku(db, make_user, count, oczekiwane):
    """Review Focus 1."""
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, fun=10.0)
    assert _akcja(user, pet, 'pat', count=count)['accepted'] == oczekiwane


# --- noc / obudź ---

def test_we_snie_brak_akcji_poza_obudz(db, make_user):
    from modules.pets.errors import PetError
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=60.0, now=NOC)
    for akcja in ('feed', 'play', 'wash', 'pat'):
        with pytest.raises(PetError) as e:
            _akcja(user, pet, akcja, now=NOC)
        assert e.value.message == 'śpi'


def test_obudz_kara_okno_20_min_i_przedluzanie(db, make_user):
    from modules.pets.errors import PetError
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=60.0, fun=50.0, clean=30.0, now=NOC)
    _akcja(user, pet, 'wake', now=NOC)
    assert pet.fun == 40.0 and pet.clean == 20.0 and pet.hunger == 60.0
    assert pet.awake_until == NOC + timedelta(minutes=20)
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'wake', now=NOC + timedelta(minutes=1))
    assert e.value.message == 'nie śpi'
    _akcja(user, pet, 'feed', now=NOC + timedelta(minutes=15))
    assert pet.awake_until == NOC + timedelta(minutes=35)
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'feed', now=NOC + timedelta(minutes=36))
    assert e.value.message == 'śpi'


def test_obudz_nie_zbija_ponizej_1(db, make_user):
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=60.0, fun=4.0, clean=100.0, now=NOC)
    _akcja(user, pet, 'wake', now=NOC)
    assert pet.fun == 1.0 and pet.clean == 90.0


def test_glodny_w_nocy_nie_spi_wiec_mozna_karmic(db, make_user):
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=20.0, now=NOC)
    _akcja(user, pet, 'feed', now=NOC)
    assert pet.hunger == 70.0 and pet.awake_until is None


# --- dni opieki, seria logowań, kamienie milowe ---

def test_dni_opieki_raz_dziennie_i_login_streak(db, make_user, monkeypatch):
    """update_login_streak() liczy po PRAWDZIWYM zegarze (nie przyjmuje now), więc kontrakt
    „wołane dokładnie przy pierwszej opiece dnia" sprawdzamy atrapą liczącą wywołania."""
    from modules.auth.models import User
    wywolania = []
    monkeypatch.setattr(User, 'update_login_streak', lambda self: wywolania.append(1))
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=10.0)
    w = _akcja(user, pet, 'feed')
    assert w['first_care_today'] is True and pet.care_days == 1 and pet.last_care_date == date(2026, 10, 12)
    assert len(wywolania) == 1
    w = _akcja(user, pet, 'feed', now=T0 + timedelta(hours=2))
    assert w['first_care_today'] is False and pet.care_days == 1 and len(wywolania) == 1
    _akcja(user, pet, 'wash', now=T0 + timedelta(days=1, hours=1))
    assert pet.care_days == 2 and len(wywolania) == 2


def test_login_streak_naprawde_rosnie_przy_pierwszej_opiece(db, make_user):
    from modules.auth.models import get_local_now
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=10.0)
    assert (user.login_streak or 0) == 0
    _akcja(user, pet, 'feed')
    assert user.login_streak == 1 and user.last_login_date == get_local_now().date()


def test_obudz_i_pat_zero_nie_licza_dnia_opieki(db, make_user):
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=60.0, now=NOC)
    _akcja(user, pet, 'wake', now=NOC)
    assert pet.care_days == 0
    pet2 = zaloz_pupila(user, species='mis', fun=100.0)
    _akcja(user, pet2, 'pat', count=60)
    assert pet2.care_days == 1
    pet3 = zaloz_pupila(user, species='kroliczek', fun=100.0)
    _akcja(user, pet3, 'pat', count=60)
    _akcja(user, pet3, 'pat', count=5, now=T0 + timedelta(minutes=1))   # 0 zaliczonych
    assert pet3.care_days == 1


def test_kamienie_milowe_dni_opieki_i_stadium(db, make_user):
    from modules.pets.models import PetEvent
    from modules.pets.common import MILESTONE_STAGE
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=20.0, care_days=6, last_care_date=date(2026, 10, 11),
                       hatched_at=T0 - timedelta(days=23, hours=20))
    _akcja(user, pet, 'feed', now=T0 + timedelta(hours=1))   # 7. dzień; 23 d 21 h → nadal maluch
    assert PetEvent.query.filter_by(pet_id=pet.id, type='milestone', value=7).count() == 1
    assert PetEvent.query.filter_by(pet_id=pet.id, type='milestone', value=MILESTONE_STAGE['dziecko']).count() == 0
    _akcja(user, pet, 'feed', now=T0 + timedelta(hours=5))   # 24 d 1 h → dziecko (sytość 49 ≤ 80, karmienie dostępne)
    assert PetEvent.query.filter_by(pet_id=pet.id, type='milestone', value=MILESTONE_STAGE['dziecko']).count() == 1
    _akcja(user, pet, 'pat', now=T0 + timedelta(hours=9), count=1)   # bez duplikatu (pat zawsze dostępny)
    assert PetEvent.query.filter_by(pet_id=pet.id, type='milestone').count() == 2


# --- odejście ---

def test_akcja_na_odeszlym_zapisuje_odejscie_410(db, make_user):
    """Review Focus 5."""
    from modules.pets.errors import PetError
    from modules.pets.models import PetEvent
    user = make_user()
    profil = zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0)
    profil.companion_pet_id = pet.id
    db.session.commit()
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'feed', now=T0 + timedelta(hours=80))
    assert e.value.code == 'pet_gone' and e.value.status == 410 and 'odszedł do gwiazd' in e.value.message
    assert pet.status == 'dead' and pet.died_at == T0 + timedelta(hours=72) and pet.notify_level == 4
    assert profil.companion_pet_id is None
    assert PetEvent.query.filter_by(pet_id=pet.id, type='die').count() == 1
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'feed', now=T0 + timedelta(hours=81))
    assert e.value.code == 'wrong_status'
    assert PetEvent.query.filter_by(pet_id=pet.id, type='die').count() == 1


def test_cudzy_pupil_403_nieznana_akcja_400(db, make_user):
    from modules.pets.errors import PetError
    a, b = make_user(), make_user()
    zaloz_profil(a)
    zaloz_profil(b)
    pet = zaloz_pupila(a)
    with pytest.raises(PetError) as e:
        _akcja(b, pet, 'feed')
    assert e.value.status == 403
    with pytest.raises(PetError) as e:
        _akcja(a, pet, 'tickle')
    assert e.value.code == 'bad_action' and e.value.status == 400
```

- [ ] **Step 2: Uruchom — mają paść**

Run: `…/venv/bin/python -m pytest tests/test_pets_actions.py -q 2>&1 | tail -2`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.pets.actions'`.

- [ ] **Step 3: Napisz `actions.py` (część 1)**

```python
# modules/pets/actions.py
"""Akcje opieki (spec §2.5), światełko, imię, towarzysz, przyznanie jajka, anonimizacja.

Każda funkcja zapisu zaczyna się od lock_profile(). perform_action najpierw liczy stan
„na teraz" (rules.simulate), zapisuje odejście, jeśli do niego doszło, sprawdza dostępność
akcji (rules.action_availability) i dopiero wtedy zmienia paski.
"""
import unicodedata
from dataclasses import replace
from datetime import timedelta

from sqlalchemy import func

from extensions import db
from modules.pets import rules
from modules.pets.common import (
    CARE_ACTIONS, MILESTONE_CARE_DAYS, NAME_MAX, PAT_MAX_PER_REQUEST, achievements_after_commit,
    add_event, add_milestone, apply_state, cfg_or, lock_profile, now_or, own_pet, persist_death,
    record_stage_milestone, simulate_pet,
)
from modules.pets.errors import PetError
from modules.pets.models import Pet, PetEvent, PetProfile


def _pats_last_hour(pet, now):
    od = now - timedelta(hours=1)
    suma = (db.session.query(func.coalesce(func.sum(PetEvent.value), 0))
            .filter(PetEvent.pet_id == pet.id, PetEvent.type == 'pat', PetEvent.created_at > od)
            .scalar())
    return int(suma or 0)


def _clamp_count(count):
    """Review Focus 1: cokolwiek przyjdzie z requestu, wychodzi 1..PAT_MAX_PER_REQUEST."""
    try:
        liczba = int(count)
    except (TypeError, ValueError):
        liczba = 1
    return max(1, min(liczba, PAT_MAX_PER_REQUEST))


def perform_action(user, pet_id, action, count=1, now=None, cfg=None):
    now, cfg = now_or(now), cfg_or(cfg)
    if action not in rules.ACTIONS:
        raise PetError('bad_action', 'Nieznana akcja.')
    lock_profile(user)
    pet = own_pet(user, pet_id, ('alive',))

    sim = simulate_pet(pet, now, cfg)
    if sim.died_at is not None:
        persist_death(pet, sim, now)
        db.session.commit()
        raise PetError('pet_gone', f'{pet.name} odszedł do gwiazd.', 410)

    stan = sim.state
    can, reasons = rules.action_availability(stan, now, cfg, pet.last_heal_at)
    if not can[action]:
        raise PetError('not_available', reasons[action], 409)

    akcje = cfg.actions
    poprzedni_state_at = pet.state_at
    zaliczone = 1
    if action == 'feed':
        stan = replace(stan, hunger=min(100.0, stan.hunger + float(akcje['feed'])))
    elif action == 'play':
        stan = replace(stan, fun=min(100.0, stan.fun + float(akcje['play'])))
    elif action == 'wash':
        stan = replace(stan, clean=100.0)
    elif action == 'heal':
        stan = replace(stan, health=min(100.0, stan.health + float(akcje['heal'])))
        pet.last_heal_at = now
    elif action == 'pat':
        chce = _clamp_count(count)
        wolne = int(akcje['pat_per_hour']) - _pats_last_hour(pet, now)
        zaliczone = max(0, min(chce, wolne))
        stan = replace(stan, fun=min(100.0, stan.fun + zaliczone * float(akcje['pat_gain'])))
    elif action == 'wake':
        kara = float(akcje['wake_penalty'])
        stan = replace(stan, fun=max(1.0, stan.fun - kara), clean=max(1.0, stan.clean - kara))
        pet.awake_until = now + timedelta(minutes=float(akcje['awake_minutes']))

    # Każda akcja w oknie obudzenia przedłuża je o awake_minutes od tej akcji
    if action != 'wake' and pet.awake_until is not None and now < pet.awake_until:
        pet.awake_until = now + timedelta(minutes=float(akcje['awake_minutes']))

    apply_state(pet, stan, now)

    pierwsza_dzis = False
    liczy_sie = action in CARE_ACTIONS and (action != 'pat' or zaliczone > 0)
    if liczy_sie and pet.last_care_date != now.date():
        pet.care_days += 1
        pet.last_care_date = now.date()
        pierwsza_dzis = True
        if pet.care_days in MILESTONE_CARE_DAYS:
            add_milestone(pet, pet.care_days, now)
    record_stage_milestone(pet, poprzedni_state_at, now, cfg)
    if action != 'pat' or zaliczone > 0:
        add_event(user.id, action, now, pet_id=pet.id, value=zaliczone)
    db.session.commit()

    if pierwsza_dzis:
        user.update_login_streak()   # commituje sam — dlatego po głównym commicie
    nowe_odznaki = achievements_after_commit(user)
    return {'pet': pet, 'accepted': zaliczone, 'first_care_today': pierwsza_dzis,
            'new_achievements': nowe_odznaki}
```

- [ ] **Step 4: Uruchom — mają przejść**

Run: `…/venv/bin/python -m pytest tests/test_pets_actions.py -q 2>&1 | tail -1`
Expected: `21 passed` (15 testów + 6 parametryzowanych). Jeśli
`test_wylecz…` pada na `'zdrowy'` przy 25 h — upewnij się, że symulacja do 25 h nie zbiła zdrowia
poniżej 75 (hunger=0 od `T0+12h` → zdrowie 100 − 13·1,39 ≈ 82 ≥ 75 → nadal „zdrowy") — wartości
są policzone tak, by test przechodził z kodem z planu.

- [ ] **Step 5: Commit**

```bash
git add modules/pets/actions.py tests/test_pets_actions.py
git commit -m "$(cat <<'EOF'
feat(pupile): perform_action - karmienie, zabawa, mycie, leczenie, pat pat, obudz

Stan liczony do teraz przed akcja, odejscie zapisywane i 410; zasada <=80,
leczenie co 12 h, pat pat paczkami z limitem 60/h z SUM(value), obudz
z kara i oknem 20 min; dni opieki raz dziennie + update_login_streak po
commicie; kamienie milowe dni opieki i stadium.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `actions.py` — światełko, imię, towarzysz, przyznanie jajka, anonimizacja

**Files:**
- Modify: `modules/pets/actions.py` (dopisz)
- Modify: `modules/auth/models.py:695-699` (`User.anonymize()` — krok 4)
- Test: `tests/test_pets_actions.py` (dopisz), `tests/test_pets_anonymize.py`

**Interfaces:**
- Produces: `light_candle(user, pet_id, now=None) -> Pet`, `validate_name(name) -> str`,
  `rename_pet(user, pet_id, name, now=None) -> Pet`,
  `set_companion(user, pet_id=None, enabled=True) -> PetProfile`,
  `admin_grant_egg(user, now=None) -> PetProfile`, `anonymize_user_pets(user, now=None) -> None`
  (bez commitu — commituje wołający).

- [ ] **Step 1: Failujące testy**

Dopisz do `tests/test_pets_actions.py`:

```python
# --- światełko ---

def test_swiatelko_raz_na_dobe_tylko_odeszly(db, make_user):
    from modules.pets.actions import light_candle
    from modules.pets.errors import PetError
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user)
    zmarly = zaloz_zmarlego(user, died_at=T0 - timedelta(days=1))
    light_candle(user, zmarly.id, now=T0)
    assert zmarly.lights_count == 1 and zmarly.last_light_date == date(2026, 10, 12)
    with pytest.raises(PetError) as e:
        light_candle(user, zmarly.id, now=T0 + timedelta(hours=5))
    assert e.value.code == 'already_lit'
    light_candle(user, zmarly.id, now=T0 + timedelta(days=1))
    assert zmarly.lights_count == 2
    assert PetEvent.query.filter_by(pet_id=zmarly.id, type='light').count() == 2
    zywy = zaloz_pupila(user)
    with pytest.raises(PetError) as e:
        light_candle(user, zywy.id, now=T0)
    assert e.value.code == 'wrong_status'


# --- imię ---

@pytest.mark.parametrize('surowe,oczekiwane', [
    ('Mruczek', 'Mruczek'), ('  Puszek  Mały ', 'Puszek Mały'), ('🐱 Kot', '🐱 Kot'), ('a' * 20, 'a' * 20),
    ('tab\there', 'tab here'),   # białe znaki (także tabulator) zbijane do pojedynczej spacji
])
def test_validate_name_ok(surowe, oczekiwane):
    from modules.pets.actions import validate_name
    assert validate_name(surowe) == oczekiwane


@pytest.mark.parametrize('zle', ['', '   ', 'a' * 21, None, 'Zły\x00znak'])
def test_validate_name_odrzuca(zle):
    from modules.pets.actions import validate_name
    from modules.pets.errors import PetError
    with pytest.raises(PetError) as e:
        validate_name(zle)
    assert e.value.code == 'bad_name'


def test_rename_zapisuje_i_loguje(db, make_user):
    from modules.pets.actions import rename_pet
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user)
    rename_pet(user, pet.id, '  Mruczuś ', now=T0)
    assert pet.name == 'Mruczuś'
    assert PetEvent.query.filter_by(pet_id=pet.id, type='rename').count() == 1


# --- towarzysz ---

def test_set_companion(db, make_user):
    from modules.pets.actions import set_companion
    from modules.pets.errors import PetError
    user = make_user()
    profil = zaloz_profil(user)
    pet = zaloz_pupila(user)
    set_companion(user, pet_id=pet.id, enabled=True)
    assert profil.companion_pet_id == pet.id and profil.companion_enabled is True
    set_companion(user, pet_id=None, enabled=False)
    assert profil.companion_pet_id is None and profil.companion_enabled is False
    zmarly = zaloz_zmarlego(user)
    with pytest.raises(PetError) as e:
        set_companion(user, pet_id=zmarly.id)
    assert e.value.code == 'wrong_status'


def test_set_companion_bez_profilu_409(db, make_user):
    from modules.pets.actions import set_companion
    from modules.pets.errors import PetError
    user = make_user()
    with pytest.raises(PetError) as e:
        set_companion(user, pet_id=None, enabled=False)
    assert e.value.code == 'no_profile'


# --- przyznanie jajka ---

def test_admin_grant_egg(db, make_user):
    from modules.pets.actions import admin_grant_egg
    from modules.pets.errors import PetError
    from modules.pets.models import PetEvent
    user = make_user()
    with pytest.raises(PetError) as e:
        admin_grant_egg(user, now=T0)
    assert e.value.code == 'no_profile'
    profil = zaloz_profil(user)
    admin_grant_egg(user, now=T0)
    admin_grant_egg(user, now=T0)
    assert profil.granted_eggs_pending == 2
    assert PetEvent.query.filter_by(user_id=user.id, type='grant', pet_id=None).count() == 2
```

Nowy plik:

```python
# tests/test_pets_anonymize.py
"""Anonimizacja konta (RODO) usuwa to, co użytkownik wpisał, i kończy grę (spec §3.3)."""
from datetime import timedelta

from tests.pets_helpers import T0, zaloz_profil, zaloz_pupila, zaloz_zmarlego, zaloz_jajko


def test_anonymize_user_pets(db, make_user):
    from modules.pets.actions import anonymize_user_pets, perform_action
    from modules.pets.config import PetConfig
    from modules.pets.models import Pet, PetEvent, PetProfile
    user = make_user()
    profil = zaloz_profil(user)
    zywy = zaloz_pupila(user, hunger=10.0)
    zmarly = zaloz_zmarlego(user)
    jajko = zaloz_jajko(user)
    profil.companion_pet_id = zywy.id
    db.session.commit()
    perform_action(user, zywy.id, 'feed', now=T0, cfg=PetConfig())
    assert PetEvent.query.filter_by(user_id=user.id).count() >= 1

    anonymize_user_pets(user, now=T0 + timedelta(days=1))
    db.session.commit()

    assert zywy.status == 'dead' and zywy.died_at == T0 + timedelta(days=1)
    assert zywy.notify_level == 4 and zywy.death_notified_at == T0 + timedelta(days=1)
    assert zywy.name is None and zmarly.name is None
    assert zmarly.died_at == T0                      # stare odejście nietknięte
    assert jajko.status == 'egg'                     # jajko zostaje (bez danych osobowych), nie wykluje się bez profilu aktywnego konta
    assert profil.companion_enabled is False and profil.companion_pet_id is None
    assert PetEvent.query.filter_by(user_id=user.id).count() == 0
    assert Pet.query.filter_by(user_id=user.id).count() == 3


def test_user_anonymize_wola_krok_pupili(db, make_user):
    user = make_user()
    zaloz_profil(user)
    zywy = zaloz_pupila(user)
    user.anonymize()
    db.session.commit()
    assert user.is_active is False
    assert zywy.status == 'dead' and zywy.name is None
```

- [ ] **Step 2: Uruchom — mają paść**

Run: `…/venv/bin/python -m pytest tests/test_pets_actions.py tests/test_pets_anonymize.py -q 2>&1 | tail -2`
Expected: FAIL (`ImportError: cannot import name 'light_candle'` itd.; `test_user_anonymize_wola_krok_pupili`
pada na `zywy.status == 'alive'`).

- [ ] **Step 3: Dopisz do `actions.py`**

```python
# ---------------------------------------------------------------------------
# Światełko, imię, towarzysz, przyznanie jajka, anonimizacja
# ---------------------------------------------------------------------------

def light_candle(user, pet_id, now=None):
    """Zapal światełko na karcie pamięci — raz na dobę, zero efektu w grze (spec §2.5)."""
    now = now_or(now)
    lock_profile(user)
    pet = own_pet(user, pet_id, ('dead',))
    if pet.last_light_date == now.date():
        raise PetError('already_lit', 'Światełko już dziś zapalone.', 409)
    pet.lights_count += 1
    pet.last_light_date = now.date()
    add_event(user.id, 'light', now, pet_id=pet.id)
    db.session.commit()
    return pet


def validate_name(name):
    """1–20 znaków po zbiciu białych znaków, bez znaków sterujących (kategorie Unicode C*)."""
    if name is None:
        raise PetError('bad_name', 'Podaj imię.')
    czyste = ' '.join(str(name).split())
    if not 1 <= len(czyste) <= NAME_MAX:
        raise PetError('bad_name', f'Imię ma mieć od 1 do {NAME_MAX} znaków.')
    if any(unicodedata.category(znak).startswith('C') for znak in czyste):
        raise PetError('bad_name', 'Imię zawiera niedozwolone znaki.')
    return czyste


def rename_pet(user, pet_id, name, now=None):
    now = now_or(now)
    lock_profile(user)
    pet = own_pet(user, pet_id, ('alive',))
    pet.name = validate_name(name)
    add_event(user.id, 'rename', now, pet_id=pet.id)
    db.session.commit()
    return pet


def set_companion(user, pet_id=None, enabled=True):
    profil = lock_profile(user)
    if pet_id is not None:
        own_pet(user, pet_id, ('alive',))
    profil.companion_pet_id = pet_id
    profil.companion_enabled = bool(enabled)
    db.session.commit()
    return profil


def admin_grant_egg(user, now=None):
    """Panel admina: +1 jajko do odebrania. `log_activity` woła trasa (etap 6)."""
    now = now_or(now)
    profil = lock_profile(user)   # bez profilu: użytkownik nie odebrał jeszcze startowego
    profil.granted_eggs_pending += 1
    add_event(user.id, 'grant', now, pet_id=None)
    db.session.commit()
    return profil


def anonymize_user_pets(user, now=None):
    """Krok User.anonymize(): żywe odchodzą (bez maila — cron i tak pomija nieaktywnych),
    imiona (dane użytkownika) znikają, towarzysz wyłączony, zdarzenia usunięte. Bez commitu."""
    now = now_or(now)
    Pet.query.filter_by(user_id=user.id, status='alive').update(
        {'status': 'dead', 'died_at': now, 'notify_level': 4, 'death_notified_at': now},
        synchronize_session='fetch')
    Pet.query.filter_by(user_id=user.id).update({'name': None}, synchronize_session='fetch')
    PetProfile.query.filter_by(user_id=user.id).update(
        {'companion_enabled': False, 'companion_pet_id': None}, synchronize_session='fetch')
    PetEvent.query.filter_by(user_id=user.id).delete(synchronize_session='fetch')
```

- [ ] **Step 4: Podepnij krok w `User.anonymize()`**

W `modules/auth/models.py` po bloku „3. Zamówienia" (po linii
`ShippingRequest.query.filter_by(user_id=user_id).update({'user_id': None})`) dodaj:

```python

        # 4. Pupile — żywe odchodzą do gwiazd, imiona (dane użytkownika) znikają,
        #    zdarzenia usunięte (modules/pets/actions.py; bez commitu — commituje wołający)
        from modules.pets.actions import anonymize_user_pets
        anonymize_user_pets(self)
```

- [ ] **Step 5: Uruchom — mają przejść**

Run: `…/venv/bin/python -m pytest tests/test_pets_actions.py tests/test_pets_anonymize.py -q 2>&1 | tail -1`
Expected: `38 passed` = 36 w `test_pets_actions.py` (21 z Task 4 + światełko 1 + imię 5 + 5 +
rename 1 + towarzysz 2 + przyznanie 1) + 2 w `test_pets_anonymize.py`. Jeśli liczba się różni,
policz z listy, nie zgaduj.

- [ ] **Step 6: Istniejące testy usuwania konta**

Run: `…/venv/bin/python -m pytest tests -q -k "anonymiz or deletion or usuni" --no-header 2>&1 | tail -1`
Expected: wszystkie `passed`.

- [ ] **Step 7: Commit**

```bash
git add modules/pets/actions.py modules/auth/models.py tests/test_pets_actions.py tests/test_pets_anonymize.py
git commit -m "$(cat <<'EOF'
feat(pupile): swiatelko, imie, towarzysz, przyznanie jajka, anonimizacja

light_candle raz na dobe na karcie pamieci; validate_name 1-20 znakow bez
znakow sterujacych; set_companion; admin_grant_egg (+1 do licznika);
anonymize_user_pets podpiete jako krok 4 User.anonymize().

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `state.py` — `state_for_user`

**Files:**
- Create: `modules/pets/state.py`
- Test: `tests/test_pets_state.py`

**Interfaces:**
- Consumes (Task 1): `common.get_profile`, `simulate_pet`, `persist_death`, `eggs_available`,
  `next_monthly_at`, `egg_dict`, `pet_dict`, `memorial_dict`, `iso`, `now_or`, `cfg_or`;
  `rules.is_night`, `rules.mood`; `species.SPECIES_SLUGS`.
- Produces: `state_for_user(user, lite=False, now=None, cfg=None) -> dict` dokładnie wg spec §3.5
  (`ok`, `now`, `night`, `eggs_available`, `next_monthly_at`, `eggs`, `pets`, `album` — pomijany
  w `lite`, `companion`, `needs_care`), `most_in_need(pet_dicts) -> dict|None`.

- [ ] **Step 1: Failujące testy**

```python
# tests/test_pets_state.py
"""state_for_user — słownik stanu dla API (spec §3.5): bez zapisów poza odejściem; lite bez zapisów."""
from datetime import timedelta

from tests.pets_helpers import T0, NOC, zaloz_profil, zaloz_pupila, zaloz_zmarlego, zaloz_jajko


def _cfg():
    from modules.pets.config import PetConfig
    return PetConfig()


def test_bez_profilu_wirtualne_startowe_i_zero_zapisow(db, make_user):
    """Review Focus 4."""
    from modules.pets.state import state_for_user
    from modules.pets.models import PetProfile, Pet
    user = make_user()
    s = state_for_user(user, now=T0, cfg=_cfg())
    assert s['ok'] is True and s['now'] == '2026-10-12T08:00:00'
    assert s['night'] == {'start': 23, 'end': 7, 'is_night': False}
    assert s['eggs_available'] == [{'source': 'start'}] and s['next_monthly_at'] is None
    assert s['eggs'] == [] and s['pets'] == []
    assert all(k['status'] == 'unknown' for k in s['album']) and len(s['album']) == 8
    assert s['companion'] == {'enabled': True, 'pet_id': None, 'auto': True}
    assert s['needs_care'] is True
    assert PetProfile.query.count() == 0 and Pet.query.count() == 0


def test_pelny_stan_z_jajkiem_pupilem_i_pamiecia(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    profil = zaloz_profil(user, now=T0 - timedelta(days=10))
    jajko = zaloz_jajko(user, now=T0 - timedelta(hours=10), boost_until=T0 - timedelta(hours=2))
    pet = zaloz_pupila(user, species='kotek', hunger=70.0, stars=1)
    zmarly = zaloz_zmarlego(user, species='mis', died_at=T0 - timedelta(days=2), lights_count=1)
    profil.companion_pet_id = pet.id
    db.session.commit()
    s = state_for_user(user, now=T0, cfg=_cfg())
    assert s['next_monthly_at'] == '2026-11-01T08:00:00'   # profil z 2.10 + 30 dni
    assert [d['source'] for d in s['eggs_available']] == ['rescue']
    assert s['eggs'][0]['id'] == jajko.id and s['eggs'][0]['progress_pct'] == round(100 * 18 / 168, 1)
    p = s['pets'][0]
    assert p['id'] == pet.id and p['bars']['hunger'] == 70.0 and p['mood'] == 'szczesliwy' and p['stars'] == 1
    album = {a['species']: a for a in s['album']}
    assert album['kotek'] == {'species': 'kotek', 'status': 'alive', 'pet_id': pet.id}
    assert album['mis']['status'] == 'memorial' and album['mis']['lights_count'] == 1 and album['mis']['can_light'] is True
    assert album['wiewiorka'] == {'species': 'wiewiorka', 'status': 'unknown'}
    assert s['companion'] == {'enabled': True, 'pet_id': pet.id, 'auto': False}
    assert s['needs_care'] is True   # jajko ratunkowe do odebrania


def test_needs_care_false_gdy_wszystko_dobrze(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    zaloz_profil(user, now=T0)
    zaloz_pupila(user)
    s = state_for_user(user, now=T0 + timedelta(hours=1), cfg=_cfg())
    assert s['needs_care'] is False and s['eggs_available'] == []


def test_needs_care_true_gdy_pasek_ponizej_30_lub_chory_lub_jajko_gotowe(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    zaloz_profil(user, now=T0)
    pet = zaloz_pupila(user, hunger=29.0)
    assert state_for_user(user, now=T0, cfg=_cfg())['needs_care'] is True
    pet.hunger = 100.0
    pet.health = 70.0
    db.session.commit()
    assert state_for_user(user, now=T0, cfg=_cfg())['needs_care'] is True
    pet.health = 100.0
    db.session.commit()
    zaloz_jajko(user, now=T0, hours=48, egg_progress_sec=48 * 3600)
    assert state_for_user(user, now=T0, cfg=_cfg())['needs_care'] is True


def test_towarzysz_auto_najbardziej_potrzebujacy(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    zaloz_profil(user, now=T0)
    a = zaloz_pupila(user, species='kotek', hunger=90.0)
    b = zaloz_pupila(user, species='mis', clean=35.0)
    s = state_for_user(user, now=T0, cfg=_cfg())
    assert s['companion'] == {'enabled': True, 'pet_id': b.id, 'auto': True}


def test_towarzysz_wskazany_ale_odeszly_wraca_do_auto(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    profil = zaloz_profil(user, now=T0)
    zywy = zaloz_pupila(user, species='kotek')
    zmarly = zaloz_zmarlego(user, species='mis')
    profil.companion_pet_id = zmarly.id
    profil.companion_enabled = False
    db.session.commit()
    s = state_for_user(user, now=T0, cfg=_cfg())
    assert s['companion'] == {'enabled': False, 'pet_id': zywy.id, 'auto': True}


def test_odejscie_zapisane_przy_odczycie_i_nagrobek(db, make_user):
    from modules.pets.state import state_for_user
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user, now=T0)
    pet = zaloz_pupila(user, hunger=0.0)
    s = state_for_user(user, now=T0 + timedelta(hours=80), cfg=_cfg())
    assert s['pets'] == []
    assert pet.status == 'dead' and pet.died_at == T0 + timedelta(hours=72)
    album = {a['species']: a for a in s['album']}
    assert album['kotek']['status'] == 'memorial' and album['kotek']['pet_id'] == pet.id
    assert [d['source'] for d in s['eggs_available']] == ['rescue']
    assert PetEvent.query.filter_by(pet_id=pet.id, type='die').count() == 1


def test_lite_nie_zapisuje_odejscia_i_nie_ma_albumu(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    zaloz_profil(user, now=T0)
    pet = zaloz_pupila(user, hunger=0.0)
    s = state_for_user(user, lite=True, now=T0 + timedelta(hours=80), cfg=_cfg())
    assert 'album' not in s
    assert pet.status == 'alive'
    assert s['pets'][0]['bars']['health'] == 0.0 and s['pets'][0]['mood'] == 'krytyczny'
    assert s['needs_care'] is True


def test_noc_w_stanie(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    zaloz_profil(user, now=T0)
    zaloz_pupila(user, now=NOC)
    s = state_for_user(user, now=NOC, cfg=_cfg())
    assert s['night']['is_night'] is True and s['pets'][0]['asleep'] is True and s['pets'][0]['can']['wake'] is True


def test_most_in_need_pusty(db):
    from modules.pets.state import most_in_need
    assert most_in_need([]) is None
```

- [ ] **Step 2: Uruchom — mają paść**

Run: `…/venv/bin/python -m pytest tests/test_pets_state.py -q 2>&1 | tail -2`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.pets.state'`.

- [ ] **Step 3: Napisz `state.py`**

```python
# modules/pets/state.py
"""state_for_user — stan dla API (spec §3.5).

Odczyt nie zapisuje; jedyny wyjątek: wyliczone odejście (persist_death) — pomijany w trybie
`lite` (towarzysz na stronach, cache w przeglądarce), który też nie buduje albumu.
"""
from dataclasses import replace

from extensions import db
from modules.pets import rules
from modules.pets.common import (
    cfg_or, egg_dict, eggs_available, get_profile, iso, memorial_dict, next_monthly_at,
    now_or, persist_death, pet_dict, simulate_pet,
)
from modules.pets.models import Pet
from modules.pets.species import SPECIES_SLUGS

_PILNOSC_NASTROJU = {'krytyczny': 0, 'chory': 1, 'smutny': 2, 'glodny': 3, 'znudzony': 3, 'brudny': 3, 'szczesliwy': 4}


def most_in_need(pet_dicts):
    """Pupil do towarzysza automatycznego: najgorszy nastrój, potem najniższy pasek."""
    if not pet_dicts:
        return None
    return min(pet_dicts, key=lambda p: (_PILNOSC_NASTROJU.get(p['mood'], 9),
                                         min(p['bars']['hunger'], p['bars']['fun'], p['bars']['clean']),
                                         p['id']))


def state_for_user(user, lite=False, now=None, cfg=None):
    now, cfg = now_or(now), cfg_or(cfg)
    profil = get_profile(user)
    wszystkie = (Pet.query.filter(Pet.user_id == user.id, Pet.status.in_(('egg', 'alive', 'dead')))
                 .order_by(Pet.created_at, Pet.id).all())

    jajka, zywe, zmarle = [], [], []
    zapisano_odejscie = False
    for pet in wszystkie:
        if pet.status == 'egg':
            jajka.append(egg_dict(pet, now, cfg))
        elif pet.status == 'alive':
            sim = simulate_pet(pet, now, cfg)
            if sim.died_at is None:
                zywe.append(pet_dict(pet, sim.state, now, cfg))
            elif lite:
                # Bez zapisu: pokaż jako krytycznego, zapisze następny pełny odczyt
                zywe.append(pet_dict(pet, replace(sim.state, health=0.0), now, cfg))
            else:
                if persist_death(pet, sim, now):
                    zapisano_odejscie = True
                zmarle.append(pet)
        else:
            zmarle.append(pet)
    if zapisano_odejscie:
        db.session.commit()
        if profil is not None:
            db.session.refresh(profil)

    dostepne = eggs_available(user, profil, now, cfg)
    stan = {
        'ok': True,
        'now': iso(now),
        'night': {'start': int(cfg.night['start']), 'end': int(cfg.night['end']),
                  'is_night': rules.is_night(now, cfg)},
        'eggs_available': dostepne,
        'next_monthly_at': iso(next_monthly_at(profil, cfg)),
        'eggs': jajka,
        'pets': zywe,
    }
    if not lite:
        stan['album'] = _album(zywe, zmarle, now)

    auto = most_in_need(zywe)
    wybrany = None
    if profil is not None and profil.companion_pet_id is not None:
        wybrany = next((p for p in zywe if p['id'] == profil.companion_pet_id), None)
    stan['companion'] = {
        'enabled': bool(profil.companion_enabled) if profil is not None else True,
        'pet_id': (wybrany or auto or {}).get('id'),
        'auto': wybrany is None,
    }
    stan['needs_care'] = (
        any(min(p['bars']['hunger'], p['bars']['fun'], p['bars']['clean']) < rules.HUNGRY_BELOW for p in zywe)
        or any(p['mood'] in ('chory', 'krytyczny') for p in zywe)
        or any(j['ready'] for j in jajka)
        or bool(dostepne)
    )
    return stan


def _album(zywe, zmarle, now):
    zywe_po_gatunku = {p['species']: p for p in zywe}
    pamiec = {}
    for pet in zmarle:   # posortowane po created_at — ostatni wygrywa
        pamiec[pet.species] = pet
    karty = []
    for slug in SPECIES_SLUGS:
        if slug in zywe_po_gatunku:
            karty.append({'species': slug, 'status': 'alive', 'pet_id': zywe_po_gatunku[slug]['id']})
        elif slug in pamiec:
            karty.append(memorial_dict(pamiec[slug], now))
        else:
            karty.append({'species': slug, 'status': 'unknown'})
    return karty
```

- [ ] **Step 4: Uruchom — mają przejść**

Run: `…/venv/bin/python -m pytest tests/test_pets_state.py -q 2>&1 | tail -1`
Expected: `10 passed`. Jeśli `test_towarzysz_auto…` wybierze kotka — sprawdź, że najniższy
pasek misia (35) jest brany z `bars` po symulacji (w chwili `T0` paski nie spadły).

- [ ] **Step 5: Commit**

```bash
git add modules/pets/state.py tests/test_pets_state.py
git commit -m "$(cat <<'EOF'
feat(pupile): state_for_user - stan dla API wg specu 3.5

Jajka, pupile po symulacji, album 8 kart (zywy / karta pamieci / nieznany),
towarzysz wskazany lub automatyczny (najbardziej potrzebujacy), needs_care;
odejscie zapisywane przy odczycie, tryb lite bez zapisow i bez albumu.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7 (centrala): fasada `service.py`, integracja, pełna suita

**Files:**
- Create: `modules/pets/service.py`
- Test: `tests/test_pets_service_facade.py`

- [ ] **Step 1: Scal gałęzie zadań do `feat/pupile`** (`--no-ff`, kolejność dowolna — pliki rozłączne).

- [ ] **Step 2: Fasada + test**

```python
# modules/pets/service.py
"""Fasada serwisu pupili — jeden import dla tras (etap 4), crona (etap 3) i admina (etap 6).

Implementacja w plikach o jednej odpowiedzialności: eggs.py, actions.py, state.py, common.py.
"""
from modules.pets.actions import (  # noqa: F401
    admin_grant_egg, anonymize_user_pets, light_candle, perform_action, rename_pet, set_companion,
    validate_name,
)
from modules.pets.common import eggs_available, get_profile, next_monthly_at  # noqa: F401
from modules.pets.eggs import claim_egg, hatch_egg, warm_egg  # noqa: F401
from modules.pets.errors import PetError  # noqa: F401
from modules.pets.state import most_in_need, state_for_user  # noqa: F401
```

```python
# tests/test_pets_service_facade.py
"""Fasada eksportuje cały kontrakt serwisu — etap 3/4/6 importują tylko stąd."""


def test_fasada_eksportuje_kontrakt():
    from modules.pets import service
    for nazwa in ('claim_egg', 'warm_egg', 'hatch_egg', 'perform_action', 'light_candle', 'rename_pet',
                  'validate_name', 'set_companion', 'admin_grant_egg', 'anonymize_user_pets',
                  'state_for_user', 'most_in_need', 'eggs_available', 'next_monthly_at', 'get_profile',
                  'PetError'):
        assert callable(getattr(service, nazwa)), nazwa


def test_scenariusz_od_jajka_do_opieki(db, make_user):
    """Smoke przez fasadę: start → ogrzej → wykluj → nakarm → stan."""
    from datetime import timedelta
    from modules.pets import service
    from modules.pets.config import PetConfig
    from tests.pets_helpers import T0, RngStaly
    cfg = PetConfig()
    user = make_user()
    jajko = service.claim_egg(user, 'start', now=T0, cfg=cfg)
    service.warm_egg(user, jajko.id, now=T0, cfg=cfg)
    # 48 h startowego: 8 h ×2 + 32 h = 48 h → gotowe po 40 h
    wynik = service.hatch_egg(user, jajko.id, now=T0 + timedelta(hours=40), cfg=cfg, rng=RngStaly('mis'))
    assert wynik['result'] == 'new' and wynik['pet'].species == 'mis'
    pet = wynik['pet']
    service.rename_pet(user, pet.id, 'Puchatek', now=T0 + timedelta(hours=40))
    # T0+40 h = środa 00:00 (noc, pupil śpi) — opieka dopiero rano, T0+48 h = środa 08:00
    service.perform_action(user, pet.id, 'pat', count=10, now=T0 + timedelta(hours=48), cfg=cfg)
    stan = service.state_for_user(user, now=T0 + timedelta(hours=48), cfg=cfg)
    assert stan['pets'][0]['name'] == 'Puchatek' and stan['pets'][0]['care_days'] == 1
    assert stan['album'][7]['status'] == 'alive'   # 'mis' jest ostatni w SPECIES_SLUGS
```

Run: `venv/bin/python -m pytest tests/test_pets_service_facade.py -q` → `2 passed`.
Commit: `feat(pupile): fasada service.py nad eggs/actions/state`.

- [ ] **Step 3: Pełna suita**

Run: `venv/bin/python -m pytest -q --no-header -p no:cacheprovider 2>&1 | tail -3`
Expected: 1864 (etap 1) + nowe: common 6, rules +6, eggs 24, actions 36, anonymize 2, state 10,
fasada 2 = **+86 → 1950 passed**, 1 failed (znany DST). Jeśli liczba się nie zgadza — policz z
raportów sesji, nie zgaduj.

- [ ] **Step 4: Kontrole**

- `grep -nE "^(from|import) (flask|sqlalchemy|extensions|modules\.)" modules/pets/rules.py` → pusto.
- `grep -n "datetime.now\|get_local_now()" modules/pets/eggs.py modules/pets/actions.py modules/pets/state.py` →
  jedyne trafienia to `now_or` w `common.py` (pliki serwisu nie wołają czasu wprost).
- `git log --oneline main..feat/pupile | wc -l` → liczba commitów etapu 1 + 2.

- [ ] **Step 5: Raport dla Konrada + ClickUp** — gotowość etapu 2 na `feat/pupile`, liczba testów,
  odstępstwa zgłoszone przez sesje; status taska `869ffdb58` zostaje `in progress`. **Bez pusha.**
