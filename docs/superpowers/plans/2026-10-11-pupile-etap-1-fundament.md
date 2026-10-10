# Pupile — Etap 1 (fundament) — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fundament modułu pupili: pakiet `modules/pets/` z gatunkami, modelami, migracją,
konfiguracją z `Settings` (z bramką rolloutu) i czystą matematyką stanu (`rules.py`) — bez tras,
bez UI, bez crona. Po tym etapie aplikacja działa dokładnie jak dziś (flaga wyłączona), a etap 2
dostaje przetestowane klocki.

**Architecture:** Stan pupila nie jest przechowywany „na żywo" — w bazie leżą wartości pasków
w chwili `state_at`, a `rules.simulate()` liczy stan „na teraz" krokami co 5 minut (noc, sen,
budzenie, zdrowie, odejście). `rules.py` nie importuje Flaska ani SQLAlchemy. Konfiguracja to
dataclass z domyślnymi liczbami, nadpisywana wierszami `Settings` o kluczach `pets_*`.

**Tech Stack:** Python 3.12, Flask 3.0, Flask-SQLAlchemy / SQLAlchemy 2.0.23, Flask-Migrate /
Alembic 1.16.5, MariaDB (prod) / SQLite (testy), pytest.

**Spec:** `docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md` (sekcje 2, 3.1–3.4, 8, 9).

## Global Constraints

- Testy uruchamiaj **zawsze** przez `venv/bin/python -m pytest …` (gołe `pytest` pada na
  `No module named 'app'`). Suita korzysta z SQLite in-memory (`TestingConfig`), fixture `app`,
  `db`, `client`, `make_user` z `tests/conftest.py`.
- Czas: wyłącznie naiwny czas polski z `modules.auth.models.get_local_now()`; w kodzie reguł czas
  jest **parametrem**, nigdy `datetime.now()`.
- Klucze `Settings` są snake_case z prefiksem `pets_` (np. `pets_egg_hours`), nie `pets.egg_hours`.
  Wartości `json` zapisuje się przez `json.dumps(...)` (`Settings.set_value` robi `str()`).
- Liczby domyślne **dokładnie ze specu** (3.4): decay 24/30/48 h, noc 23–07 ×0,25, zdrowie −100/72 h
  i +100/24 h, jajko 168 h, startowe 48 h, boost 8 h ×2, miesięczne 30 dni, ratunkowe 0 h,
  przypomnienie 7 dni, gwarancja po 2, max 5 gwiazdek, stadia 24/80 dni, akcje
  `{feed 50, play 50, heal 40, heal_cooldown_h 12, allow_below 80, pat_gain 0.25, pat_per_hour 60,
  wake_penalty 10, awake_minutes 20}`.
- Migracja: `down_revision = 'dde1a45a7d87'` (jedyna głowa, zweryfikowana `ScriptDirectory`).
  Surowy `ALTER TABLE … MODIFY … ENUM` tylko pod `if bind.dialect.name == 'mysql'`.
  W `downgrade()` **nie** dropuj indeksów osobno przed `drop_table` (MariaDB nie pozwala usunąć
  indeksu podtrzymującego FK).
- Komentarze i komunikaty po polsku; tematy commitów ASCII bez polskich znaków, w stylu repo
  (`feat(pupile): …`, `migrate(pupile): …`). Każdy commit kończy się linią
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **Nie pushować na `main`** — push = auto-deploy na produkcję. Praca na gałęzi `feat/pupile`;
  o merge/pushu decyduje Konrad.
- Repo jest publiczne: do commitów nie trafiają dane infrastruktury.

## Review Focus

Wejścia, których spec nie wymienia wprost, a które muszą być poprawnie obsłużone (każde ma test
w zadaniu, które jest właścicielem kodu):

1. **Wiersz `Settings` typu `json` z niepoprawnym JSON-em** (np. `str(dict)` z apostrofami — dokładnie
   pułapka `set_value`) → `PetConfig.load()` loguje ostrzeżenie i używa domyślnych, nic nie pada
   (Task 4).
2. **Konfiguracja nocy `start == end`** → brak nocy (pupil nigdy nie śpi), a nie wyjątek ani
   „noc całą dobę" (Task 5).
3. **`awake_until` w przeszłości** → traktowane jak `None` (pupil śpi), bez błędu porównania (Task 5).
4. **Wartości pasków poza 0–100 w bazie** (ręczna edycja, przyszły błąd) → `simulate()` klamruje je
   na wejściu, zamiast propagować ujemne albo >100 (Task 6).
5. **`boost_until` wcześniejsze niż `egg_progress_at`** (stary boost sprzed ostatniego zapisu
   postępu) → liczony jako 0 s przyspieszenia, nie jako ujemny czas (Task 6).

---

### Task 0: Synchronizacja z origin i gałąź robocza

**Files:** brak zmian w plikach.

- [ ] **Step 1: Sprawdź stan i pobierz zmiany Karoliny**

Run:
```bash
cd /Users/konradkmiecik/Documents/GitHub/ThunderOrders && git status --short && git fetch && git log --oneline main..origin/main
```
Expected: drzewo czyste; 2 commity z origin (`fix(wysylka): preordery bez pol samo incl…` + merge),
żaden nie dotyka `migrations/` ani `modules/pets/`.

- [ ] **Step 2: Scal origin/main do lokalnego main**

Run:
```bash
git pull --no-rebase origin main
```
Expected: `Merge made by the 'ort' strategy` (lub fast-forward), bez konfliktów. Jeśli konflikt —
STOP i zgłoś Konradowi.

- [ ] **Step 3: Utwórz gałąź**

Run:
```bash
git checkout -b feat/pupile
```
Expected: `Switched to a new branch 'feat/pupile'`.

- [ ] **Step 4: Baseline testów (bez zmian w kodzie)**

Run:
```bash
venv/bin/python -m pytest -q -x --no-header -p no:cacheprovider 2>&1 | tail -3
```
Expected: `N passed` (zapisz N — porównasz w Task 7). Jeśli pada pojedynczy, znany flaky test,
odnotuj jego nazwę i jedź dalej.

---

### Task 1: Szkielet modułu i stałe gatunków

**Files:**
- Create: `modules/pets/__init__.py`
- Create: `modules/pets/species.py`
- Create: `modules/pets/models.py` (pusty plik z docstringiem — wypełniany w Task 2; `__init__`
  musi go importować już teraz)
- Modify: `app.py:380-383` (rejestracja blueprintów po `contests_bp`)
- Test: `tests/test_pets_fundament.py`

**Interfaces:**
- Produces: `modules.pets.pets_bp` (Blueprint `'pets'`, prefix `/client/pupile`),
  `modules.pets.pets_admin_bp` (Blueprint `'pets_admin'`, prefix `/admin/pupile`);
  `modules.pets.species.SPECIES: tuple[Species, ...]` (8 pozycji),
  `SPECIES_BY_SLUG: dict[str, Species]`, `SPECIES_SLUGS: tuple[str, ...]`;
  `Species(slug: str, name: str, palette: dict, extras: tuple)`.

- [ ] **Step 1: Napisz failujący test**

```python
# tests/test_pets_fundament.py
"""Etap 1 pupili: szkielet modułu, gatunki, modele."""


def test_blueprinty_pupili_sa_zarejestrowane(app):
    assert 'pets' in app.blueprints
    assert 'pets_admin' in app.blueprints
    assert app.blueprints['pets'].url_prefix == '/client/pupile'
    assert app.blueprints['pets_admin'].url_prefix == '/admin/pupile'


def test_osiem_gatunkow_z_unikalnymi_slugami():
    from modules.pets.species import SPECIES, SPECIES_BY_SLUG, SPECIES_SLUGS
    assert len(SPECIES) == 8
    assert len(set(SPECIES_SLUGS)) == 8
    assert set(SPECIES_SLUGS) == {
        'wiewiorka', 'kroliczek', 'szczeniak', 'piesek',
        'kotek', 'kurczaczek', 'czarny-kotek', 'mis',
    }
    assert SPECIES_BY_SLUG['mis'].name == 'Miś'


def test_kazdy_gatunek_ma_pelna_palete():
    from modules.pets.species import SPECIES
    for s in SPECIES:
        assert set(s.palette) == {'base', 'light', 'dark', 'cheek'}, s.slug
        for kolor in s.palette.values():
            assert kolor.startswith('#') and len(kolor) == 7, (s.slug, kolor)
        assert isinstance(s.extras, tuple)
```

- [ ] **Step 2: Uruchom test — ma paść**

Run: `venv/bin/python -m pytest tests/test_pets_fundament.py -q`
Expected: FAIL — `KeyError: 'pets'` / `ModuleNotFoundError: No module named 'modules.pets'`.

- [ ] **Step 3: Utwórz pakiet, gatunki, pusty models.py**

```python
# modules/pets/__init__.py
"""Pupile (tamagotchi) dla klientów.

Spec: docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md
Etap 1: tylko modele, konfiguracja i reguły czasu. Trasy (routes.py, admin_routes.py)
dochodzą w etapie 4 — blueprinty rejestrujemy już teraz, żeby create_all() i Alembic
widziały modele.
"""
from flask import Blueprint

pets_bp = Blueprint('pets', __name__, url_prefix='/client/pupile')
pets_admin_bp = Blueprint('pets_admin', __name__, url_prefix='/admin/pupile')

from . import models  # noqa: E402,F401  (create_all() i Alembic potrzebują modeli)
```

```python
# modules/pets/species.py
"""Gatunki pupili — stałe.

Osiem gatunków inspirowanych maskotkami ATEEZ, własna grafika (rig SVG w etapie 4;
lustro tej listy powstanie w static/js/pet/species.js). Zmiana nazwy = edycja tej stałej,
celowo bez UI.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Species:
    slug: str
    name: str
    palette: dict   # base, light, dark, cheek — kolory HEX
    extras: tuple = ()  # cechy rigu: uszy, ogon, dodatki


SPECIES = (
    Species('wiewiorka', 'Wiewiórka',
            {'base': '#F4A261', 'light': '#FBE3C9', 'dark': '#C8732F', 'cheek': '#F7B7A3'},
            ('stripes', 'bushy_tail')),
    Species('kroliczek', 'Króliczek',
            {'base': '#F7B6D2', 'light': '#FDE4EF', 'dark': '#E58BB5', 'cheek': '#F48FB1'},
            ('long_ears', 'sparkles')),
    Species('szczeniak', 'Szczeniak',
            {'base': '#F6E3B4', 'light': '#FFF6DE', 'dark': '#D9BE7A', 'cheek': '#F5B5A1'},
            ('floppy_ears', 'fringe')),
    Species('piesek', 'Piesek',
            {'base': '#FFFFFF', 'light': '#FFFFFF', 'dark': '#D9D9D9', 'cheek': '#F8BBD0'},
            ('long_floppy_ears',)),
    Species('kotek', 'Kotek',
            {'base': '#C9C3E6', 'light': '#E8E4F5', 'dark': '#9D94C9', 'cheek': '#F3A6C4'},
            ('pointy_ears', 'white_muzzle')),
    Species('kurczaczek', 'Kurczaczek',
            {'base': '#FDE68A', 'light': '#FFF4C2', 'dark': '#E3C44A', 'cheek': '#F9B27A'},
            ('beak', 'crest')),
    Species('czarny-kotek', 'Czarny Kotek',
            {'base': '#2B2B2B', 'light': '#4A4A4A', 'dark': '#111111', 'cheek': '#6B4A4A'},
            ('pointy_ears', 'collar_bell')),
    Species('mis', 'Miś',
            {'base': '#B5835A', 'light': '#E3C3A0', 'dark': '#8A5F3C', 'cheek': '#E9A087'},
            ('round_ears', 'leaf')),
)

SPECIES_BY_SLUG = {s.slug: s for s in SPECIES}
SPECIES_SLUGS = tuple(s.slug for s in SPECIES)
```

```python
# modules/pets/models.py
"""Modele modułu pupili — wypełniane w Task 2 planu etapu 1."""
```

- [ ] **Step 4: Zarejestruj blueprinty w `app.py`**

W `register_blueprints` zaraz po bloku `contests_bp` (ok. linii 383) dodaj:

```python
    # Pupile (tamagotchi) — etap 1: same modele; trasy dochodzą w etapie 4
    from modules.pets import pets_bp, pets_admin_bp
    app.register_blueprint(pets_bp)
    app.register_blueprint(pets_admin_bp)
```

- [ ] **Step 5: Uruchom test — ma przejść**

Run: `venv/bin/python -m pytest tests/test_pets_fundament.py -q`
Expected: `3 passed`.

- [ ] **Step 6: Commit**

```bash
git add modules/pets/__init__.py modules/pets/species.py modules/pets/models.py app.py tests/test_pets_fundament.py
git commit -m "$(cat <<'EOF'
feat(pupile): szkielet modulu i stale gatunkow

Blueprinty pets/pets_admin (bez tras), 8 gatunkow z paletami.
Spec: docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Modele `PetProfile`, `Pet`, `PetEvent` + `pet_updates` + kategoria odznak `pets`

**Files:**
- Modify: `modules/pets/models.py` (pełna treść)
- Modify: `modules/notifications/models.py:93-124` (kolumna `pet_updates` + `to_dict`)
- Modify: `modules/achievements/models.py:12-16` (enum `achievement_category` + `'pets'`)
- Test: `tests/test_pets_fundament.py` (dopisz testy)

**Interfaces:**
- Consumes: `extensions.db`, `modules.auth.models.get_local_now`.
- Produces: `PetProfile`, `Pet`, `PetEvent` (kolumny dokładnie jak w specu 3.3), stałe
  `PET_STATUSES`, `EGG_SOURCES`, `EVENT_TYPES`, `PRUNABLE_EVENT_TYPES`;
  backrefy `User.pet_profile` (1:1), `User.pets` (lista), `Pet.events` (dynamic);
  `NotificationPreference.pet_updates: bool` (domyślnie `True`, w `to_dict()`).

- [ ] **Step 1: Sprawdź, że nazwy backrefów są wolne**

Run: `grep -n "pet_profile\|'pets'\|\.pets\b" modules/auth/models.py | head`
Expected: brak wyników (żadnych kolizji z `User`).

- [ ] **Step 2: Napisz failujące testy**

Dopisz do `tests/test_pets_fundament.py`:

```python
from datetime import datetime


def test_profil_pupil_i_zdarzenie_z_domyslnymi(db, make_user):
    from modules.pets.models import PetProfile, Pet, PetEvent
    user = make_user()
    profil = PetProfile(user_id=user.id)
    pupil = Pet(user_id=user.id, egg_source='start', egg_hours=48)
    db.session.add_all([profil, pupil])
    db.session.commit()

    assert user.pet_profile is profil
    assert profil.companion_enabled is True
    assert profil.dupes_in_row == 0
    assert profil.granted_eggs_pending == 0
    assert isinstance(profil.start_egg_claimed_at, datetime)
    assert isinstance(profil.last_monthly_egg_at, datetime)

    assert pupil.status == 'egg'
    assert pupil.species is None
    assert pupil.egg_progress_sec == 0
    assert (pupil.hunger, pupil.fun, pupil.clean, pupil.health) == (100.0, 100.0, 100.0, 100.0)
    assert pupil.stars == 0 and pupil.care_days == 0 and pupil.notify_level == 0
    assert pupil.lights_count == 0
    assert user.pets == [pupil]

    zdarzenie = PetEvent(pet_id=pupil.id, user_id=user.id, type='claim')
    db.session.add(zdarzenie)
    db.session.commit()
    assert zdarzenie.value == 1
    assert pupil.events.count() == 1


def test_profil_moze_wskazywac_towarzysza(db, make_user):
    from modules.pets.models import PetProfile, Pet
    user = make_user()
    pupil = Pet(user_id=user.id, egg_source='monthly', status='alive', species='kotek',
                name='Mruczek', hatched_at=datetime(2026, 10, 1, 12, 0))
    db.session.add(pupil)
    db.session.commit()
    profil = PetProfile(user_id=user.id, companion_pet_id=pupil.id)
    db.session.add(profil)
    db.session.commit()
    assert profil.companion_pet is pupil


def test_merged_jajko_pamieta_w_kogo_sie_wtopilo(db, make_user):
    from modules.pets.models import Pet
    user = make_user()
    zywy = Pet(user_id=user.id, egg_source='start', status='alive', species='mis', name='Puchatek')
    db.session.add(zywy)
    db.session.commit()
    dupl = Pet(user_id=user.id, egg_source='monthly', status='merged', species='mis',
               merged_into_pet_id=zywy.id)
    db.session.add(dupl)
    db.session.commit()
    assert dupl.merged_into is zywy


def test_stale_typow_zdarzen_i_porzadkow():
    from modules.pets.models import EVENT_TYPES, PRUNABLE_EVENT_TYPES, PET_STATUSES, EGG_SOURCES
    assert set(PRUNABLE_EVENT_TYPES) == {'feed', 'play', 'wash', 'heal', 'pat', 'wake', 'warm', 'light'}
    assert set(PRUNABLE_EVENT_TYPES) < set(EVENT_TYPES)
    assert {'claim', 'grant', 'hatch_new', 'hatch_dupe', 'merge', 'die', 'rename', 'milestone'} < set(EVENT_TYPES)
    assert PET_STATUSES == ('egg', 'alive', 'dead', 'merged')
    assert EGG_SOURCES == ('start', 'monthly', 'rescue', 'granted')


def test_preferencja_pet_updates_domyslnie_wlaczona(db, make_user):
    from modules.notifications.models import NotificationPreference
    user = make_user()
    pref = NotificationPreference(user_id=user.id)
    db.session.add(pref)
    db.session.commit()
    assert pref.pet_updates is True
    assert pref.to_dict()['pet_updates'] is True


def test_enum_kategorii_odznak_zawiera_pets(db):
    """SQLAlchemy nie waliduje nieznanych stringów w Enum (validate_strings=False),
    więc sam INSERT by przeszedł — sprawdzamy definicję typu, a potem zapis."""
    from modules.achievements.models import Achievement
    assert 'pets' in Achievement.__table__.c.category.type.enums
    a = Achievement(slug='pet-test', name='Test', description='x', category='pets',
                    rarity='common', trigger_type='event',
                    trigger_config={'metric': 'pets_hatched', 'threshold': 1})
    db.session.add(a)
    db.session.commit()
    assert Achievement.query.filter_by(category='pets').count() == 1
```

- [ ] **Step 3: Uruchom testy — mają paść**

Run: `venv/bin/python -m pytest tests/test_pets_fundament.py -q`
Expected: 6 nowych FAIL (`ImportError: cannot import name 'PetProfile'`, brak `pet_updates`,
`assert 'pets' in [...]` dla enumu kategorii).

- [ ] **Step 4: Napisz modele**

```python
# modules/pets/models.py
"""Modele modułu pupili (tamagotchi).

Spec: docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md §3.3

Zasada: w bazie leżą wartości pasków W CHWILI `state_at`; stan „na teraz" liczy
modules/pets/rules.py. Modele nie zawierają logiki gry. Kolumny muszą być 1:1
z migracją f3e9a1c7b2d4 (pilnuje tego tests/test_pets_migration.py).
"""
from extensions import db
from modules.auth.models import get_local_now

PET_STATUSES = ('egg', 'alive', 'dead', 'merged')
EGG_SOURCES = ('start', 'monthly', 'rescue', 'granted')
EVENT_TYPES = (
    'claim', 'grant', 'warm', 'hatch_new', 'hatch_dupe', 'merge',
    'feed', 'play', 'wash', 'heal', 'pat', 'wake', 'light',
    'die', 'rename', 'milestone',
)
# Zdarzenia akcji — cron kasuje je po 90 dniach. Reszta jest trwała (historia pupila, raport).
PRUNABLE_EVENT_TYPES = ('feed', 'play', 'wash', 'heal', 'pat', 'wake', 'warm', 'light')


class PetProfile(db.Model):
    """Jeden na użytkownika; powstaje przy odbiorze jajka startowego (nie przy GET)."""
    __tablename__ = 'pet_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, unique=True)
    # NULL = towarzysz automatyczny (ten, który najbardziej potrzebuje opieki)
    companion_pet_id = db.Column(db.Integer, db.ForeignKey('pets.id', ondelete='SET NULL'),
                                 nullable=True)
    companion_enabled = db.Column(db.Boolean, nullable=False, default=True,
                                  server_default=db.text('1'))
    dupes_in_row = db.Column(db.Integer, nullable=False, default=0, server_default=db.text('0'))
    start_egg_claimed_at = db.Column(db.DateTime, nullable=False, default=get_local_now)
    # Licznik miesięczny biegnie od ODBIORU (startowego lub poprzedniego miesięcznego)
    last_monthly_egg_at = db.Column(db.DateTime, nullable=False, default=get_local_now)
    monthly_notified_at = db.Column(db.DateTime, nullable=True)
    granted_eggs_pending = db.Column(db.SmallInteger, nullable=False, default=0,
                                     server_default=db.text('0'))
    created_at = db.Column(db.DateTime, nullable=False, default=get_local_now)

    user = db.relationship('User', backref=db.backref('pet_profile', uselist=False))
    companion_pet = db.relationship('Pet', foreign_keys=[companion_pet_id])

    def __repr__(self):
        return f'<PetProfile user={self.user_id}>'


class Pet(db.Model):
    """Jajko, żywy pupil, karta pamięci (dead) albo wtopiony duplikat (merged)."""
    __tablename__ = 'pets'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.Enum(*PET_STATUSES, name='pet_status'), nullable=False, default='egg')
    species = db.Column(db.String(32), nullable=True)   # NULL dopóki jajko
    name = db.Column(db.String(20), nullable=True)

    # --- jajko ---
    egg_source = db.Column(db.Enum(*EGG_SOURCES, name='pet_egg_source'), nullable=False)
    # Zamrożone przy odbiorze: zmiana ustawień nie przestawia trwających inkubacji
    egg_hours = db.Column(db.SmallInteger, nullable=False, default=168)
    egg_progress_sec = db.Column(db.Integer, nullable=False, default=0, server_default=db.text('0'))
    egg_progress_at = db.Column(db.DateTime, nullable=False, default=get_local_now)
    boost_until = db.Column(db.DateTime, nullable=True)
    egg_ready_notified_at = db.Column(db.DateTime, nullable=True)
    hatched_at = db.Column(db.DateTime, nullable=True)
    merged_into_pet_id = db.Column(db.Integer, db.ForeignKey('pets.id', ondelete='SET NULL'),
                                   nullable=True)

    # --- paski w chwili state_at (0–100) ---
    hunger = db.Column(db.Float, nullable=False, default=100.0)
    fun = db.Column(db.Float, nullable=False, default=100.0)
    clean = db.Column(db.Float, nullable=False, default=100.0)
    health = db.Column(db.Float, nullable=False, default=100.0)
    state_at = db.Column(db.DateTime, nullable=False, default=get_local_now)
    awake_until = db.Column(db.DateTime, nullable=True)   # okno po „Obudź"

    stars = db.Column(db.SmallInteger, nullable=False, default=0, server_default=db.text('0'))
    care_days = db.Column(db.Integer, nullable=False, default=0, server_default=db.text('0'))
    last_care_date = db.Column(db.Date, nullable=True)
    last_heal_at = db.Column(db.DateTime, nullable=True)
    # 0 brak, 1 smutny, 2 chory, 3 krytyczny, 4 odszedł — raz na epizod
    notify_level = db.Column(db.SmallInteger, nullable=False, default=0, server_default=db.text('0'))

    # --- odejście ---
    died_at = db.Column(db.DateTime, nullable=True)
    death_notified_at = db.Column(db.DateTime, nullable=True)
    rescue_egg_claimed_at = db.Column(db.DateTime, nullable=True)
    rescue_reminder_sent_at = db.Column(db.DateTime, nullable=True)
    lights_count = db.Column(db.Integer, nullable=False, default=0, server_default=db.text('0'))
    last_light_date = db.Column(db.Date, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=get_local_now)  # = odebranie jajka

    __table_args__ = (
        db.Index('ix_pets_user_status', 'user_id', 'status'),
    )

    user = db.relationship('User', backref=db.backref('pets', lazy='select'))
    merged_into = db.relationship('Pet', remote_side=[id], foreign_keys=[merged_into_pet_id])

    def __repr__(self):
        return f'<Pet {self.id} {self.status} {self.species or "?"} user={self.user_id}>'


class PetEvent(db.Model):
    """Log zdarzeń: limit pat pat, dni opieki, statystyki, odznaki, raport."""
    __tablename__ = 'pet_events'

    id = db.Column(db.Integer, primary_key=True)
    pet_id = db.Column(db.Integer, db.ForeignKey('pets.id', ondelete='CASCADE'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    # pat: liczba ZALICZONYCH klepnięć w paczce; milestone: numer progu; reszta: 1
    value = db.Column(db.Integer, nullable=False, default=1, server_default=db.text('1'))
    created_at = db.Column(db.DateTime, nullable=False, default=get_local_now)

    __table_args__ = (
        db.Index('ix_pet_events_pet_type_created', 'pet_id', 'type', 'created_at'),
        db.Index('ix_pet_events_user_created', 'user_id', 'created_at'),
    )

    pet = db.relationship('Pet', backref=db.backref('events', lazy='dynamic'))

    def __repr__(self):
        return f'<PetEvent {self.type} pet={self.pet_id} value={self.value}>'
```

- [ ] **Step 5: Dodaj `pet_updates` do preferencji**

W `modules/notifications/models.py` w klasie `NotificationPreference` po
`order_supplier_ordered` dodaj:

```python
    # Pupile (tamagotchi): push + e-mail o stanie pupili — przełącznik widoczny też bez pusha
    pet_updates = db.Column(db.Boolean, default=True, nullable=False, server_default=db.text('1'))
```

oraz w `to_dict()` dopisz klucz:

```python
            'pet_updates': self.pet_updates,
```

- [ ] **Step 6: Rozszerz enum kategorii odznak**

W `modules/achievements/models.py` zmień definicję `category` na:

```python
    category = db.Column(
        db.Enum('orders', 'collection', 'loyalty', 'speed', 'exclusive',
                'social', 'financial', 'profile', 'special', 'pets',
                name='achievement_category'),
        nullable=False
    )
```

- [ ] **Step 7: Uruchom testy — mają przejść**

Run: `venv/bin/python -m pytest tests/test_pets_fundament.py -q`
Expected: `9 passed`.

- [ ] **Step 8: Upewnij się, że istniejące testy preferencji i odznak nie ucierpiały**

Run: `venv/bin/python -m pytest tests -q -k "preference or notification or achievement" --no-header 2>&1 | tail -2`
Expected: wszystkie `passed`.

- [ ] **Step 9: Commit**

```bash
git add modules/pets/models.py modules/notifications/models.py modules/achievements/models.py tests/test_pets_fundament.py
git commit -m "$(cat <<'EOF'
feat(pupile): modele pet_profiles/pets/pet_events, preferencja pet_updates

Kolumny 1:1 ze specem 3.3; kategoria odznak 'pets' w enumie modelu
(migracja w kolejnym commicie).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Migracja `f3e9a1c7b2d4` + test parytetu z modelami

**Files:**
- Create: `migrations/versions/f3e9a1c7b2d4_pupile_fundament.py`
- Test: `tests/test_pets_migration.py`

**Interfaces:**
- Consumes: modele z Task 2 (`Pet.__table__` itd.), `User.__table__`, `Achievement.__table__`,
  `NotificationPreference.__table__`.
- Produces: rewizja `f3e9a1c7b2d4` jako jedyna głowa łańcucha.

- [ ] **Step 1: Napisz failujący test**

```python
# tests/test_pets_migration.py
"""Migracja pupili uruchamiana na świeżym SQLite — parytet z modelami i odwracalność.

Nie da się tu odpalić całego łańcucha migracji (15 starszych plików ma surowy SQL dla
MariaDB bez guardu), więc budujemy tylko tabele-zależności z modeli i uruchamiamy
wyłącznie upgrade()/downgrade() tej jednej rewizji przez Operations.context.
"""
import importlib.util
import pathlib

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

REWIZJA = 'f3e9a1c7b2d4'
PLIK = pathlib.Path('migrations/versions') / f'{REWIZJA}_pupile_fundament.py'


def _zaladuj_migracje():
    spec = importlib.util.spec_from_file_location('migracja_pupile', PLIK)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture
def silnik(app):
    """Osobny SQLite z tabelami, do których migracja się odwołuje (FK / ALTER)."""
    from extensions import db
    from modules.auth.models import User
    from modules.achievements.models import Achievement
    from modules.notifications.models import NotificationPreference
    # Metadane znają już nowe tabele (Task 2) — celowo ich NIE tworzymy: zrobi to migracja.
    engine = sa.create_engine('sqlite://')
    db.metadata.create_all(bind=engine, tables=[
        User.__table__, Achievement.__table__, NotificationPreference.__table__,
    ])
    yield engine
    engine.dispose()


def _kolumny(insp, tabela):
    return {c['name']: c['nullable'] for c in insp.get_columns(tabela)}


def test_migracja_jest_jedyna_glowa():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config('migrations/alembic.ini')
    cfg.set_main_option('script_location', 'migrations')
    sd = ScriptDirectory.from_config(cfg)
    assert sd.get_heads() == [REWIZJA]
    assert sd.get_revision(REWIZJA).down_revision == 'dde1a45a7d87'


def test_upgrade_tworzy_tabele_zgodne_z_modelami(silnik):
    from modules.pets.models import Pet, PetProfile, PetEvent
    migracja = _zaladuj_migracje()
    with silnik.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migracja.upgrade()
        insp = sa.inspect(conn)
        tabele = set(insp.get_table_names())
        assert {'pets', 'pet_profiles', 'pet_events'} <= tabele

        for model in (Pet, PetProfile, PetEvent):
            z_modelu = {c.name: c.nullable for c in model.__table__.columns}
            assert _kolumny(insp, model.__tablename__) == z_modelu, model.__tablename__

        indeksy = {i['name'] for i in insp.get_indexes('pets')}
        assert 'ix_pets_user_status' in indeksy
        indeksy_zdarzen = {i['name'] for i in insp.get_indexes('pet_events')}
        assert {'ix_pet_events_pet_type_created', 'ix_pet_events_user_created'} <= indeksy_zdarzen

        assert 'pet_updates' in _kolumny(insp, 'notification_preferences')


def test_downgrade_odwraca_upgrade(silnik):
    migracja = _zaladuj_migracje()
    with silnik.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migracja.upgrade()
        with Operations.context(ctx):
            migracja.downgrade()
        insp = sa.inspect(conn)
        tabele = set(insp.get_table_names())
        assert not ({'pets', 'pet_profiles', 'pet_events'} & tabele)
        assert 'pet_updates' not in _kolumny(insp, 'notification_preferences')
```

- [ ] **Step 2: Uruchom test — ma paść**

Run: `venv/bin/python -m pytest tests/test_pets_migration.py -q`
Expected: FAIL — `FileNotFoundError` (brak pliku migracji) / `assert ['dde1a45a7d87'] == ['f3e9a1c7b2d4']`.

- [ ] **Step 3: Napisz migrację**

```python
# migrations/versions/f3e9a1c7b2d4_pupile_fundament.py
"""Pupile (tamagotchi): tabele pet_profiles/pets/pet_events, preferencja pet_updates,
kategoria odznak 'pets'

Revision ID: f3e9a1c7b2d4
Revises: dde1a45a7d87
Create Date: 2026-10-11 12:00:00.000000

Spec: docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md §3.3
"""
from alembic import op
import sqlalchemy as sa

revision = 'f3e9a1c7b2d4'
down_revision = 'dde1a45a7d87'
branch_labels = None
depends_on = None

KATEGORIE_STARE = ('orders', 'collection', 'loyalty', 'speed', 'exclusive',
                   'social', 'financial', 'profile', 'special')
KATEGORIE_NOWE = KATEGORIE_STARE + ('pets',)


def _enum_sql(wartosci):
    return 'ENUM(' + ', '.join(f"'{w}'" for w in wartosci) + ')'


def upgrade():
    # Kolejność: pets -> pet_profiles (FK companion_pet_id -> pets) -> pet_events
    op.create_table(
        'pets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('egg', 'alive', 'dead', 'merged', name='pet_status'), nullable=False),
        sa.Column('species', sa.String(length=32), nullable=True),
        sa.Column('name', sa.String(length=20), nullable=True),
        sa.Column('egg_source', sa.Enum('start', 'monthly', 'rescue', 'granted', name='pet_egg_source'), nullable=False),
        sa.Column('egg_hours', sa.SmallInteger(), nullable=False),
        sa.Column('egg_progress_sec', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('egg_progress_at', sa.DateTime(), nullable=False),
        sa.Column('boost_until', sa.DateTime(), nullable=True),
        sa.Column('egg_ready_notified_at', sa.DateTime(), nullable=True),
        sa.Column('hatched_at', sa.DateTime(), nullable=True),
        sa.Column('merged_into_pet_id', sa.Integer(), nullable=True),
        sa.Column('hunger', sa.Float(), nullable=False),
        sa.Column('fun', sa.Float(), nullable=False),
        sa.Column('clean', sa.Float(), nullable=False),
        sa.Column('health', sa.Float(), nullable=False),
        sa.Column('state_at', sa.DateTime(), nullable=False),
        sa.Column('awake_until', sa.DateTime(), nullable=True),
        sa.Column('stars', sa.SmallInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('care_days', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_care_date', sa.Date(), nullable=True),
        sa.Column('last_heal_at', sa.DateTime(), nullable=True),
        sa.Column('notify_level', sa.SmallInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('died_at', sa.DateTime(), nullable=True),
        sa.Column('death_notified_at', sa.DateTime(), nullable=True),
        sa.Column('rescue_egg_claimed_at', sa.DateTime(), nullable=True),
        sa.Column('rescue_reminder_sent_at', sa.DateTime(), nullable=True),
        sa.Column('lights_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_light_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['merged_into_pet_id'], ['pets.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pets_user_status', 'pets', ['user_id', 'status'], unique=False)

    op.create_table(
        'pet_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('companion_pet_id', sa.Integer(), nullable=True),
        sa.Column('companion_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('dupes_in_row', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('start_egg_claimed_at', sa.DateTime(), nullable=False),
        sa.Column('last_monthly_egg_at', sa.DateTime(), nullable=False),
        sa.Column('monthly_notified_at', sa.DateTime(), nullable=True),
        sa.Column('granted_eggs_pending', sa.SmallInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['companion_pet_id'], ['pets.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_pet_profiles_user_id'),
    )

    op.create_table(
        'pet_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pet_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('value', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pet_id'], ['pets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pet_events_pet_type_created', 'pet_events', ['pet_id', 'type', 'created_at'], unique=False)
    op.create_index('ix_pet_events_user_created', 'pet_events', ['user_id', 'created_at'], unique=False)

    # Preferencja powiadomień o pupilach (domyślnie włączona dla wszystkich)
    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pet_updates', sa.Boolean(), nullable=False,
                                      server_default=sa.text('1')))

    # Enum kategorii odznak: MariaDB wymaga jawnego ALTER (jak w 405efca8e619);
    # SQLite (testy, lokalny podgląd) nie zna MODIFY, a tam schemat powstaje z modeli.
    bind = op.get_bind()
    if bind.dialect.name == 'mysql':
        op.execute('ALTER TABLE achievement MODIFY category ' + _enum_sql(KATEGORIE_NOWE) + ' NOT NULL')


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'mysql':
        # Odznaki z nowej kategorii nie mogą zostać w enumie bez tej wartości
        op.execute("UPDATE achievement SET category = 'special' WHERE category = 'pets'")
        op.execute('ALTER TABLE achievement MODIFY category ' + _enum_sql(KATEGORIE_STARE) + ' NOT NULL')

    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.drop_column('pet_updates')

    # Bez osobnego drop_index: MariaDB nie pozwala zdjąć indeksu podtrzymującego FK,
    # a drop_table usuwa indeksy razem z tabelą. Kolejność odwrotna do FK.
    op.drop_table('pet_events')
    op.drop_table('pet_profiles')
    op.drop_table('pets')
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `venv/bin/python -m pytest tests/test_pets_migration.py -q`
Expected: `3 passed`. Jeśli test parytetu wskaże różnicę `nullable` albo brak kolumny — popraw
**migrację**, nie model (model jest źródłem prawdy ze specu).

- [ ] **Step 5: Podejrzyj SQL dla MariaDB w trybie offline**

Run:
```bash
FLASK_APP=app.py venv/bin/flask db upgrade dde1a45a7d87:f3e9a1c7b2d4 --sql 2>/dev/null | grep -E "CREATE TABLE|ALTER TABLE|CREATE INDEX" | head -20
```
Expected: `CREATE TABLE pets`, `CREATE INDEX ix_pets_user_status`, `CREATE TABLE pet_profiles`,
`CREATE TABLE pet_events`, 2× `CREATE INDEX ix_pet_events_*`, `ALTER TABLE notification_preferences
ADD COLUMN pet_updates`, `ALTER TABLE achievement MODIFY category ENUM(... 'pets') NOT NULL`.
Jeśli komenda nie wstanie bez bazy (XAMPP leży), pomiń ten krok — test z kroku 4 pokrywa schemat.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/f3e9a1c7b2d4_pupile_fundament.py tests/test_pets_migration.py
git commit -m "$(cat <<'EOF'
migrate(pupile): tabele pupili, pet_updates, kategoria odznak pets

Rewizja f3e9a1c7b2d4 po dde1a45a7d87. ALTER enumu tylko pod MySQL
(guard dialektu — lokalny podglad i testy chodza na SQLite).
Test uruchamia upgrade/downgrade na swiezym SQLite i porownuje
kolumny z modelami.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `PetConfig` z `Settings` + bramka rolloutu

**Files:**
- Create: `modules/pets/config.py`
- Test: `tests/test_pets_config.py`

**Interfaces:**
- Consumes: `modules.auth.models.Settings` (kolumny `key`, `value`, `type` ∈ string/integer/boolean/json).
- Produces:
  - `PetConfig` (frozen dataclass; pola: `enabled: bool`, `rollout_pct: int`, `decay_hours: dict`,
    `night: dict`, `health_drop_hours: int`, `health_regen_hours: int`, `egg_hours: int`,
    `start_egg_hours: int`, `boost: dict`, `monthly_days: int`, `rescue_hours: int`,
    `rescue_reminder_days: int`, `pity_after: int`, `max_stars: int`, `stage_days: dict`,
    `actions: dict`);
  - `PetConfig.load(force: bool = False) -> PetConfig` (cache w `flask.g`);
  - `PetConfig.from_rows(rows) -> PetConfig`;
  - `SETTINGS_PREFIX = 'pets_'`;
  - `feature_flags() -> tuple[bool, int]`, `pets_feature_for(user) -> bool`,
    `reset_feature_cache() -> None`.
- Uwaga dla testów: `load()` cache'uje w `g` na czas kontekstu aplikacji (= całego testu) — po
  zmianie `Settings` wołaj `PetConfig.load(force=True)`; po zmianie flag wołaj
  `reset_feature_cache()`.

- [ ] **Step 1: Napisz failujące testy**

```python
# tests/test_pets_config.py
"""PetConfig: domyślne liczby ze specu, nadpisania z Settings, bramka rolloutu."""
import json
from types import SimpleNamespace

import pytest


def _ustaw(db, key, value, typ):
    from modules.auth.models import Settings
    Settings.set_value(key, value, type=typ)
    db.session.commit()


def test_domyslne_liczby_ze_specu():
    from modules.pets.config import PetConfig
    cfg = PetConfig()
    assert cfg.enabled is False and cfg.rollout_pct == 0
    assert cfg.decay_hours == {'hunger': 24, 'fun': 30, 'clean': 48}
    assert cfg.night == {'start': 23, 'end': 7, 'factor': 0.25}
    assert (cfg.health_drop_hours, cfg.health_regen_hours) == (72, 24)
    assert (cfg.egg_hours, cfg.start_egg_hours) == (168, 48)
    assert cfg.boost == {'hours': 8, 'factor': 2}
    assert (cfg.monthly_days, cfg.rescue_hours, cfg.rescue_reminder_days) == (30, 0, 7)
    assert (cfg.pity_after, cfg.max_stars) == (2, 5)
    assert cfg.stage_days == {'child': 24, 'adult': 80}
    assert cfg.actions == {'feed': 50, 'play': 50, 'heal': 40, 'heal_cooldown_h': 12,
                           'allow_below': 80, 'pat_gain': 0.25, 'pat_per_hour': 60,
                           'wake_penalty': 10, 'awake_minutes': 20}


def test_load_bez_wierszy_daje_domyslne(app):
    from modules.pets.config import PetConfig
    assert PetConfig.load(force=True) == PetConfig()


def test_nadpisanie_integer_i_boolean(db):
    from modules.pets.config import PetConfig
    _ustaw(db, 'pets_egg_hours', 100, 'integer')
    _ustaw(db, 'pets_enabled', 'true', 'boolean')
    cfg = PetConfig.load(force=True)
    assert cfg.egg_hours == 100
    assert cfg.enabled is True
    assert cfg.start_egg_hours == 48  # nietknięte


def test_nadpisanie_json_scala_sie_z_domyslnymi(db):
    from modules.pets.config import PetConfig
    _ustaw(db, 'pets_decay_hours', json.dumps({'hunger': 12}), 'json')
    cfg = PetConfig.load(force=True)
    assert cfg.decay_hours == {'hunger': 12, 'fun': 30, 'clean': 48}


def test_load_cache_w_g_i_force(db):
    from modules.pets.config import PetConfig
    pierwszy = PetConfig.load(force=True)
    _ustaw(db, 'pets_monthly_days', 45, 'integer')
    assert PetConfig.load().monthly_days == pierwszy.monthly_days  # cache
    assert PetConfig.load(force=True).monthly_days == 45


def test_niepoprawny_json_nie_wywraca_i_daje_domyslne(db, caplog):
    """Review Focus 1: str(dict) z apostrofami — pułapka Settings.set_value."""
    from modules.pets.config import PetConfig
    _ustaw(db, 'pets_boost', str({'hours': 4, 'factor': 3}), 'json')
    cfg = PetConfig.load(force=True)
    assert cfg.boost == {'hours': 8, 'factor': 2}
    assert any('pets_boost' in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize('key,value,typ', [
    ('pets_egg_hours', -5, 'integer'),
    ('pets_rollout_pct', 150, 'integer'),
    ('pets_night', json.dumps({'start': 23, 'end': 7, 'factor': 1.5}), 'json'),
    ('pets_decay_hours', json.dumps({'hunger': 0}), 'json'),
    ('pets_decay_hours', json.dumps([24, 30, 48]), 'json'),
])
def test_wartosci_poza_zakresem_sa_ignorowane(db, key, value, typ):
    from modules.pets.config import PetConfig
    _ustaw(db, key, value, typ)
    assert PetConfig.load(force=True) == PetConfig()


def test_nieznany_klucz_pets_jest_ignorowany(db):
    from modules.pets.config import PetConfig
    _ustaw(db, 'pets_foo', 1, 'integer')
    assert PetConfig.load(force=True) == PetConfig()


# --- bramka funkcji / rollout ---

def _user(id, role='client', auth=True):
    return SimpleNamespace(id=id, role=role, is_authenticated=auth)


def test_funkcja_wylaczona_dla_wszystkich_gdy_flaga_off(db):
    from modules.pets.config import pets_feature_for, reset_feature_cache
    reset_feature_cache()
    assert pets_feature_for(_user(1, 'admin')) is False
    assert pets_feature_for(_user(2)) is False


def test_rollout_procentowy_po_user_id(db):
    from modules.pets.config import pets_feature_for, reset_feature_cache
    _ustaw(db, 'pets_enabled', 'true', 'boolean')
    _ustaw(db, 'pets_rollout_pct', 50, 'integer')
    reset_feature_cache()
    assert pets_feature_for(_user(10)) is True     # 10 % 100 = 10 < 50
    assert pets_feature_for(_user(160)) is False   # 160 % 100 = 60 >= 50
    assert pets_feature_for(_user(999, 'admin')) is True   # admin zawsze
    assert pets_feature_for(_user(999, 'mod')) is True


def test_rollout_0_i_100(db):
    from modules.pets.config import pets_feature_for, reset_feature_cache
    _ustaw(db, 'pets_enabled', 'true', 'boolean')
    _ustaw(db, 'pets_rollout_pct', 0, 'integer')
    reset_feature_cache()
    assert pets_feature_for(_user(1)) is False
    assert pets_feature_for(_user(1, 'admin')) is True
    _ustaw(db, 'pets_rollout_pct', 100, 'integer')
    reset_feature_cache()
    assert pets_feature_for(_user(199)) is True


def test_anonim_i_none_nie_maja_dostepu(db):
    from modules.pets.config import pets_feature_for, reset_feature_cache
    _ustaw(db, 'pets_enabled', 'true', 'boolean')
    _ustaw(db, 'pets_rollout_pct', 100, 'integer')
    reset_feature_cache()
    assert pets_feature_for(None) is False
    assert pets_feature_for(_user(5, auth=False)) is False


def test_cache_flag_wymaga_resetu(db):
    from modules.pets.config import feature_flags, reset_feature_cache
    reset_feature_cache()
    assert feature_flags() == (False, 0)
    _ustaw(db, 'pets_enabled', 'true', 'boolean')
    _ustaw(db, 'pets_rollout_pct', 25, 'integer')
    assert feature_flags() == (False, 0)      # jeszcze z cache (TTL 10 s)
    reset_feature_cache()
    assert feature_flags() == (True, 25)
```

- [ ] **Step 2: Uruchom testy — mają paść**

Run: `venv/bin/python -m pytest tests/test_pets_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.pets.config'`.

- [ ] **Step 3: Napisz `config.py`**

```python
# modules/pets/config.py
"""Konfiguracja pupili: domyślne liczby ze specu (§3.4) + nadpisania z Settings.

Klucze Settings: snake_case z prefiksem `pets_` (np. `pets_egg_hours`), typy
integer/boolean/json. Wartości json zapisuj przez json.dumps — Settings.set_value
robi str(), a str(dict) nie jest JSON-em; taki wiersz jest tu ignorowany z ostrzeżeniem.

PetConfig.load() robi JEDNO zapytanie (LIKE 'pets_%') i cache'uje wynik w flask.g
na czas żądania. Flagi włączenia/rolloutu mają osobny cache w procesie (10 s, jak
app.maintenance_cache), bo sprawdza je context processor na każdej stronie.
"""
import json
import time
from dataclasses import dataclass, field, fields
from typing import ClassVar

from flask import current_app, g

SETTINGS_PREFIX = 'pets_'

_DICT_DEFAULTS = {
    'decay_hours': {'hunger': 24, 'fun': 30, 'clean': 48},
    'night': {'start': 23, 'end': 7, 'factor': 0.25},
    'boost': {'hours': 8, 'factor': 2},
    'stage_days': {'child': 24, 'adult': 80},
    'actions': {
        'feed': 50, 'play': 50, 'heal': 40, 'heal_cooldown_h': 12, 'allow_below': 80,
        'pat_gain': 0.25, 'pat_per_hour': 60, 'wake_penalty': 10, 'awake_minutes': 20,
    },
}


def _slownik(nazwa):
    return field(default_factory=lambda: dict(_DICT_DEFAULTS[nazwa]))


@dataclass(frozen=True)
class PetConfig:
    enabled: bool = False
    rollout_pct: int = 0
    decay_hours: dict = _slownik('decay_hours')
    night: dict = _slownik('night')
    health_drop_hours: int = 72
    health_regen_hours: int = 24
    egg_hours: int = 168
    start_egg_hours: int = 48
    boost: dict = _slownik('boost')
    monthly_days: int = 30
    rescue_hours: int = 0
    rescue_reminder_days: int = 7
    pity_after: int = 2
    max_stars: int = 5
    stage_days: dict = _slownik('stage_days')
    actions: dict = _slownik('actions')

    # Pola, które mogą być zerem (reszta liczb musi być dodatnia)
    _ZERO_OK: ClassVar[frozenset] = frozenset({'rollout_pct', 'rescue_hours', 'pity_after', 'max_stars'})

    @classmethod
    def load(cls, force=False):
        """Konfiguracja z Settings, cache w g na czas żądania."""
        if not force:
            cached = getattr(g, '_pet_config', None)
            if cached is not None:
                return cached
        from modules.auth.models import Settings
        rows = Settings.query.filter(Settings.key.like(f'{SETTINGS_PREFIX}%')).all()
        cfg = cls.from_rows(rows)
        g._pet_config = cfg
        return cfg

    @classmethod
    def from_rows(cls, rows):
        domyslne = cls()
        nazwy = {f.name for f in fields(cls)}
        nadpisania = {}
        for row in rows:
            nazwa = row.key[len(SETTINGS_PREFIX):]
            if nazwa not in nazwy:
                continue
            try:
                nadpisania[nazwa] = _przetworz(nazwa, row.value, getattr(domyslne, nazwa), cls._ZERO_OK)
            except (ValueError, TypeError) as exc:
                current_app.logger.warning('pets: ignoruję ustawienie %s=%r (%s)', row.key, row.value, exc)
        return cls(**nadpisania)


def _przetworz(nazwa, surowe, domyslna, zero_ok):
    """Konwersja + walidacja jednej wartości; ValueError = użyj domyślnej."""
    if isinstance(domyslna, bool):
        return str(surowe).strip().lower() in ('true', '1', 'yes')
    if isinstance(domyslna, int):
        liczba = int(str(surowe).strip())
        if liczba < 0 or (liczba == 0 and nazwa not in zero_ok):
            raise ValueError('liczba poza zakresem')
        if nazwa == 'rollout_pct' and liczba > 100:
            raise ValueError('procent > 100')
        return liczba
    if isinstance(domyslna, dict):
        try:
            parsed = json.loads(surowe)
        except json.JSONDecodeError as exc:
            raise ValueError(f'niepoprawny JSON: {exc}') from exc
        if not isinstance(parsed, dict):
            raise ValueError('oczekiwano obiektu JSON')
        scalone = {**domyslna, **parsed}
        for klucz, wartosc in scalone.items():
            if not isinstance(wartosc, (int, float)) or isinstance(wartosc, bool):
                raise ValueError(f'{klucz}: nie liczba')
            if klucz == 'factor' and nazwa == 'night':
                if not 0 < wartosc <= 1:
                    raise ValueError('night.factor poza (0, 1]')
            elif klucz in ('start', 'end') and nazwa == 'night':
                if not 0 <= wartosc <= 23:
                    raise ValueError('godzina nocy poza 0–23')
            elif wartosc <= 0:
                raise ValueError(f'{klucz}: musi być dodatnia')
        return scalone
    raise TypeError(f'nieobsługiwany typ pola {nazwa}')


# ---------------------------------------------------------------------------
# Bramka funkcji: włącznik + rollout procentowy (cache w procesie, 10 s)
# ---------------------------------------------------------------------------

FEATURE_CACHE_SECONDS = 10
_feature_cache = {'enabled': False, 'pct': 0, 'checked_at': None}


def reset_feature_cache():
    _feature_cache.update(enabled=False, pct=0, checked_at=None)


def feature_flags():
    """(pets_enabled, pets_rollout_pct) z krótkim cache — jak app.maintenance_cache."""
    teraz = time.monotonic()
    ttl = current_app.config.get('PETS_FEATURE_CACHE_SECONDS', FEATURE_CACHE_SECONDS)
    sprawdzono = _feature_cache['checked_at']
    if sprawdzono is None or teraz - sprawdzono > ttl:
        from modules.auth.models import Settings
        _feature_cache['enabled'] = bool(Settings.get_value('pets_enabled', False))
        try:
            pct = int(Settings.get_value('pets_rollout_pct', 0))
        except (TypeError, ValueError):
            pct = 0
        _feature_cache['pct'] = max(0, min(100, pct))
        _feature_cache['checked_at'] = teraz
    return _feature_cache['enabled'], _feature_cache['pct']


def pets_feature_for(user):
    """Czy ten użytkownik widzi pupile: flaga + rollout po user_id; admin/mod zawsze."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    enabled, pct = feature_flags()
    if not enabled:
        return False
    if getattr(user, 'role', None) in ('admin', 'mod'):
        return True
    return (user.id % 100) < pct
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `venv/bin/python -m pytest tests/test_pets_config.py -q`
Expected: `17 passed` (12 testów + 5 parametryzowanych przypadków).

- [ ] **Step 5: Commit**

```bash
git add modules/pets/config.py tests/test_pets_config.py
git commit -m "$(cat <<'EOF'
feat(pupile): PetConfig z Settings i bramka rolloutu

Domyslne liczby ze specu 3.4, nadpisania z kluczy pets_* jednym LIKE,
odporne na zly JSON; pets_feature_for() z procentem rolloutu po user_id
i cache 10 s.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `rules.py` — noc, warunki budzenia, sen, tempo spadku

**Files:**
- Create: `modules/pets/rules.py` (część 1)
- Test: `tests/test_pets_rules.py` (część 1)

**Interfaces:**
- Consumes: `PetConfig` (tylko jako nośnik liczb; żadnego Flaska).
- Produces:
  - stałe `STEP_SECONDS = 300`, `BARS = ('hunger', 'fun', 'clean')`, `HUNGRY_BELOW = 30`,
    `SICK_BELOW = 75`, `CRITICAL_BELOW = 25`, `HAPPY_FROM = 50`;
  - `PetState(hunger: float = 100, fun: float = 100, clean: float = 100, health: float = 100,
    stars: int = 0, awake_until: datetime | None = None)` — frozen dataclass;
  - `clamp_state(state) -> PetState`;
  - `is_night(dt, cfg) -> bool`;
  - `wake_reasons(state, dt) -> tuple[str, ...]` (podzbiór `'hungry'`, `'zero'`, `'sick'`, `'woken'`);
  - `is_asleep(state, dt, cfg) -> bool`;
  - `decay_multiplier(state, dt, cfg) -> float`;
  - `rates_per_hour(state, dt, cfg) -> dict` z kluczami `hunger`, `fun`, `clean`, `health`
    (ujemne = spadek).

- [ ] **Step 1: Napisz failujące testy**

```python
# tests/test_pets_rules.py
"""Czysta matematyka stanu pupila (modules/pets/rules.py) — bez Flaska i bazy.

Czasy: poniedziałek 2026-10-12. Dzień = 08:00–20:00 (daleko od nocy 23–07).

Testy reguł CELOWO nie importują PetConfig: rules.py ma być niezależne od reszty
modułu (i od sesji, która równolegle pisze config.py). Konfiguracja to obiekt
o kształcie PetConfig z liczbami ze specu §3.4; zgodność z prawdziwym PetConfig
sprawdza test dopisywany przy integracji etapu (Task 7).
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from modules.pets import rules
from modules.pets.rules import PetState


def _cfg(**nadpisania):
    """Atrapa PetConfig: te same nazwy pól, te same domyślne liczby co spec §3.4."""
    bazowe = dict(
        decay_hours={'hunger': 24, 'fun': 30, 'clean': 48},
        night={'start': 23, 'end': 7, 'factor': 0.25},
        health_drop_hours=72, health_regen_hours=24,
        egg_hours=168, start_egg_hours=48,
        boost={'hours': 8, 'factor': 2},
        max_stars=5, stage_days={'child': 24, 'adult': 80},
    )
    bazowe.update(nadpisania)
    return SimpleNamespace(**bazowe)


CFG = _cfg()
PON_08 = datetime(2026, 10, 12, 8, 0)
PON_23 = datetime(2026, 10, 12, 23, 0)
WT_07 = datetime(2026, 10, 13, 7, 0)
PELNY = PetState()


def blisko(a, b, eps=0.05):
    return abs(a - b) <= eps


# --- noc / sen ---

@pytest.mark.parametrize('godzina,minuta,noc', [
    (22, 59, False), (23, 0, True), (2, 30, True), (6, 59, True), (7, 0, False), (12, 0, False),
])
def test_is_night_granice(godzina, minuta, noc):
    assert rules.is_night(datetime(2026, 10, 12, godzina, minuta), CFG) is noc


def test_is_night_bez_nocy_gdy_start_rowny_end():
    """Review Focus 2: start == end oznacza brak nocy, nie noc całą dobę."""
    cfg = _cfg(night={'start': 7, 'end': 7, 'factor': 0.25})
    for h in range(24):
        assert rules.is_night(datetime(2026, 10, 12, h, 0), cfg) is False


def test_is_night_okno_niewychodzace_poza_polnoc():
    cfg = _cfg(night={'start': 1, 'end': 5, 'factor': 0.25})
    assert rules.is_night(datetime(2026, 10, 12, 3, 0), cfg) is True
    assert rules.is_night(datetime(2026, 10, 12, 23, 0), cfg) is False


def test_wake_reasons():
    assert rules.wake_reasons(PELNY, PON_23) == ()
    assert rules.wake_reasons(PetState(hunger=29.9), PON_23) == ('hungry',)
    assert rules.wake_reasons(PetState(fun=0), PON_23) == ('zero',)
    assert rules.wake_reasons(PetState(health=74.9), PON_23) == ('sick',)
    obudzony = PetState(awake_until=PON_23 + timedelta(minutes=20))
    assert rules.wake_reasons(obudzony, PON_23) == ('woken',)
    assert rules.wake_reasons(PetState(hunger=0, health=10), PON_23) == ('hungry', 'zero', 'sick')


def test_awake_until_w_przeszlosci_jak_none():
    """Review Focus 3."""
    stan = PetState(awake_until=PON_23 - timedelta(minutes=1))
    assert rules.wake_reasons(stan, PON_23) == ()
    assert rules.is_asleep(stan, PON_23, CFG) is True


def test_is_asleep():
    assert rules.is_asleep(PELNY, PON_23, CFG) is True
    assert rules.is_asleep(PELNY, PON_08, CFG) is False          # dzień
    assert rules.is_asleep(PetState(hunger=20), PON_23, CFG) is False   # głodny nie śpi
    assert rules.is_asleep(PetState(clean=0), PON_23, CFG) is False     # zero nie śpi
    assert rules.is_asleep(PetState(health=50), PON_23, CFG) is False   # chory nie śpi


# --- tempo ---

def test_decay_multiplier_dzien_noc_gwiazdki():
    assert rules.decay_multiplier(PELNY, PON_08, CFG) == 1.0
    assert rules.decay_multiplier(PELNY, PON_23, CFG) == 0.25
    assert blisko(rules.decay_multiplier(PetState(stars=2), PON_08, CFG), 0.8, 1e-9)
    assert blisko(rules.decay_multiplier(PetState(stars=2), PON_23, CFG), 0.2, 1e-9)


def test_gwiazdki_ponad_max_licza_sie_jak_max():
    assert blisko(rules.decay_multiplier(PetState(stars=9), PON_08, CFG), 0.5, 1e-9)


def test_rates_per_hour_pelny_w_dzien():
    r = rules.rates_per_hour(PELNY, PON_08, CFG)
    assert blisko(r['hunger'], -100 / 24, 1e-6)
    assert blisko(r['fun'], -100 / 30, 1e-6)
    assert blisko(r['clean'], -100 / 48, 1e-6)
    assert r['health'] == 0.0   # zdrowie pełne — nic do regeneracji


def test_rates_per_hour_pasek_na_zerze_zbija_zdrowie():
    r = rules.rates_per_hour(PetState(hunger=0), PON_08, CFG)
    assert r['hunger'] == 0.0            # nie schodzi poniżej zera
    assert blisko(r['health'], -100 / 72, 1e-6)


def test_rates_per_hour_regeneracja_gdy_wszystko_ponad_50():
    r = rules.rates_per_hour(PetState(hunger=60, fun=51, clean=90, health=40), PON_08, CFG)
    assert blisko(r['health'], 100 / 24, 1e-6)


def test_rates_per_hour_zdrowie_stoi_gdy_pasek_ponizej_50_bez_zera():
    r = rules.rates_per_hour(PetState(hunger=40, health=60), PON_08, CFG)
    assert r['health'] == 0.0


def test_rates_per_hour_we_snie_cztery_razy_wolniej():
    r = rules.rates_per_hour(PELNY, PON_23, CFG)
    assert blisko(r['hunger'], -100 / 24 * 0.25, 1e-6)
```

- [ ] **Step 2: Uruchom testy — mają paść**

Run: `venv/bin/python -m pytest tests/test_pets_rules.py -q`
Expected: FAIL — `ImportError: cannot import name 'rules'`.

- [ ] **Step 3: Napisz część 1 `rules.py`**

```python
# modules/pets/rules.py
"""Czysta matematyka stanu pupila. ZERO importów z Flaska / SQLAlchemy.

Spec: docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md §2.4–2.7, §3.1

Stan „na teraz" = simulate(stan_z_bazy, cfg, state_at, teraz). Czas jest zawsze parametrem
(naiwny czas polski, jak w całej aplikacji) — tu nie ma datetime.now().
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

STEP_SECONDS = 300          # krok symulacji: 5 minut
BARS = ('hunger', 'fun', 'clean')
HUNGRY_BELOW = 30           # głodny → budzi się w nocy
SICK_BELOW = 75             # chory → budzi się, dostępne „Wylecz"
CRITICAL_BELOW = 25
HAPPY_FROM = 50             # wszystkie paski ≥ 50 = szczęśliwy; > 50 = regeneracja zdrowia


@dataclass(frozen=True)
class PetState:
    hunger: float = 100.0
    fun: float = 100.0
    clean: float = 100.0
    health: float = 100.0
    stars: int = 0
    awake_until: datetime | None = None


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(v)))


def clamp_state(state):
    """Paski i zdrowie przycięte do 0–100 (dane z bazy mogą być brudne)."""
    return replace(
        state,
        hunger=_clamp(state.hunger), fun=_clamp(state.fun),
        clean=_clamp(state.clean), health=_clamp(state.health),
        stars=max(0, int(state.stars or 0)),
    )


# ---------------------------------------------------------------------------
# Noc i sen
# ---------------------------------------------------------------------------

def is_night(dt, cfg):
    """Noc wg konfiguracji (domyślnie 23:00–07:00). start == end → brak nocy."""
    start = int(cfg.night['start'])
    end = int(cfg.night['end'])
    if start == end:
        return False
    godzina = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    if start > end:                      # okno przez północ, np. 23 → 7
        return godzina >= start or godzina < end
    return start <= godzina < end        # okno w obrębie doby, np. 1 → 5


def wake_reasons(state, dt):
    """Dlaczego pupil NIE śpi mimo nocy (kolejność stała — testy na niej polegają)."""
    powody = []
    if state.hunger < HUNGRY_BELOW:
        powody.append('hungry')
    if any(getattr(state, bar) <= 0 for bar in BARS):
        powody.append('zero')
    if state.health < SICK_BELOW:
        powody.append('sick')
    if state.awake_until is not None and dt < state.awake_until:
        powody.append('woken')
    return tuple(powody)


def is_asleep(state, dt, cfg):
    return is_night(dt, cfg) and not wake_reasons(state, dt)


# ---------------------------------------------------------------------------
# Tempo zmian
# ---------------------------------------------------------------------------

def decay_multiplier(state, dt, cfg):
    """Mnożnik spadku pasków: sen ×factor (0,25), każda gwiazdka −10 % (do max_stars)."""
    gwiazdki = min(max(int(state.stars or 0), 0), int(cfg.max_stars))
    mnoznik_gwiazdek = 1.0 - 0.1 * gwiazdki
    mnoznik_snu = float(cfg.night['factor']) if is_asleep(state, dt, cfg) else 1.0
    return mnoznik_snu * mnoznik_gwiazdek


def rates_per_hour(state, dt, cfg):
    """Zmiana na godzinę dla każdego paska i zdrowia w chwili dt (ujemne = spadek).

    Paski: liniowo 100 → 0 w decay_hours[bar] godzin × mnożnik. Pasek na zerze już nie spada.
    Zdrowie: −100/health_drop_hours gdy KTÓRYKOLWIEK pasek = 0 (bez spowolnienia nocnego);
    +100/health_regen_hours gdy WSZYSTKIE paski > 50 i zdrowie < 100; inaczej 0.
    """
    mnoznik = decay_multiplier(state, dt, cfg)
    tempo = {}
    for bar in BARS:
        wartosc = getattr(state, bar)
        tempo[bar] = 0.0 if wartosc <= 0 else -(100.0 / float(cfg.decay_hours[bar])) * mnoznik

    jakis_na_zerze = any(getattr(state, bar) <= 0 for bar in BARS)
    wszystkie_ponad = all(getattr(state, bar) > HAPPY_FROM for bar in BARS)
    if jakis_na_zerze:
        tempo['health'] = -(100.0 / float(cfg.health_drop_hours)) if state.health > 0 else 0.0
    elif wszystkie_ponad and state.health < 100:
        tempo['health'] = 100.0 / float(cfg.health_regen_hours)
    else:
        tempo['health'] = 0.0
    return tempo
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `venv/bin/python -m pytest tests/test_pets_rules.py -q`
Expected: `18 passed` (6 parametryzowanych + 12).

- [ ] **Step 5: Commit**

```bash
git add modules/pets/rules.py tests/test_pets_rules.py
git commit -m "$(cat <<'EOF'
feat(pupile): rules.py - noc, sen, budzenie, tempo spadku

Czysta matematyka bez Flaska: is_night z oknem przez polnoc, warunki
budzenia (glod/zero/choroba/Obudz), mnoznik snu i gwiazdek, tempo
paskow i zdrowia na godzine.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `rules.py` — symulacja, odejście, nastrój, stadia, jajko

**Files:**
- Modify: `modules/pets/rules.py` (dopisz część 2)
- Test: `tests/test_pets_rules.py` (dopisz część 2)

**Interfaces:**
- Consumes: wszystko z Task 5.
- Produces:
  - `SimResult(state: PetState, died_at: datetime | None)` — frozen dataclass;
  - `simulate(state, cfg, from_dt, to_dt) -> SimResult` (kroki 5 min od `from_dt`, ostatni
    ułamkowy; `elapsed = max(0, …)`; przy odejściu `state.health == 0`, `died_at` interpolowane
    liniowo w kroku; stan wejściowy klamrowany);
  - `mood(state) -> str` ∈ `krytyczny | chory | smutny | glodny | znudzony | brudny | szczesliwy`;
  - `STAGES = ('maluch', 'dziecko', 'dorosly')`, `stage(hatched_at, now, cfg) -> str`,
    `age_days(hatched_at, now) -> int`;
  - `egg_progress_seconds(progress_sec, progress_at, boost_until, now, cfg) -> float`,
    `egg_is_ready(progress_seconds, egg_hours) -> bool`,
    `egg_progress_pct(progress_seconds, egg_hours) -> float` (0–100, 1 miejsce po przecinku).

- [ ] **Step 1: Napisz failujące testy**

Dopisz do `tests/test_pets_rules.py`:

```python
# --- symulacja ---

def test_spadek_w_dzien_12h_polowa_sytosci():
    wynik = rules.simulate(PELNY, CFG, PON_08, PON_08 + timedelta(hours=12))
    assert blisko(wynik.state.hunger, 50)
    assert blisko(wynik.state.fun, 60)
    assert blisko(wynik.state.clean, 75)
    assert wynik.state.health == 100 and wynik.died_at is None


def test_gwiazdki_spowalniaja_spadek():
    wynik = rules.simulate(PetState(stars=2), CFG, PON_08, PON_08 + timedelta(hours=10))
    assert blisko(wynik.state.hunger, 100 - (100 / 24) * 10 * 0.8)


def test_noc_cztery_razy_wolniej():
    wynik = rules.simulate(PELNY, CFG, PON_23, WT_07)
    assert blisko(wynik.state.hunger, 100 - (100 / 24) * 8 * 0.25)   # 91.67


def test_glodny_budzi_sie_w_nocy_i_glodnieje_normalnie():
    # 32 → asleep do 30 (~2 h), potem pełne tempo przez ~6 h → ~4.9
    wynik = rules.simulate(PetState(hunger=32), CFG, PON_23, WT_07)
    assert 4 < wynik.state.hunger < 6


def test_pasek_na_zerze_budzi_i_zbija_zdrowie_w_nocy():
    wynik = rules.simulate(PetState(fun=0), CFG, PON_23, WT_07)
    assert blisko(wynik.state.hunger, 100 - (100 / 24) * 8)      # 66.67, bez snu
    assert blisko(wynik.state.health, 100 - (100 / 72) * 8)      # 88.89
    assert wynik.state.fun == 0


def test_chory_nie_spi_i_regeneruje_sie_gdy_paski_pelne():
    # Chory (70) nie śpi → paski pełnym tempem, zdrowie +4.17/h → 100 po ~7.25 h;
    # od tej chwili już zdrowy, więc ZASYPIA na resztę nocy (~0.75 h ×0.25).
    # Sytość ≈ 100 − 4.17·7.25 − 1.04·0.75 ≈ 69.0 (zamiast 66.7, gdyby nie zasnął).
    wynik = rules.simulate(PetState(health=70), CFG, PON_23, WT_07)
    assert wynik.state.health == 100
    assert 68 < wynik.state.hunger < 70


def test_obudz_okno_potem_sen():
    stan = PetState(awake_until=PON_23 + timedelta(hours=1))
    wynik = rules.simulate(stan, CFG, PON_23, WT_07)
    oczekiwane = 100 - (100 / 24) * 1 - (100 / 24) * 0.25 * 7     # 88.54
    assert blisko(wynik.state.hunger, oczekiwane)


def test_zdrowie_spada_do_zera_w_72h_od_zera_paska():
    wynik = rules.simulate(PetState(hunger=0), CFG, PON_08, PON_08 + timedelta(hours=80))
    assert wynik.state.health == 0
    assert wynik.died_at is not None
    assert abs((wynik.died_at - (PON_08 + timedelta(hours=72))).total_seconds()) < 60


def test_odejscie_po_okolo_96h_bez_opieki_od_pelna():
    wynik = rules.simulate(PELNY, CFG, PON_08, PON_08 + timedelta(hours=120))
    assert wynik.died_at is not None
    godzin = (wynik.died_at - PON_08).total_seconds() / 3600
    assert 96 <= godzin <= 104, godzin   # noc spowalnia głodnienie, stąd > 96


def test_regeneracja_zdrowia_gdy_wszystko_ponad_50():
    wynik = rules.simulate(PetState(health=40), CFG, PON_08, PON_08 + timedelta(hours=10))
    assert blisko(wynik.state.health, 40 + (100 / 24) * 10)   # 81.67


def test_zdrowie_stoi_gdy_pasek_ponizej_50_ale_nie_zero():
    wynik = rules.simulate(PetState(hunger=40, health=60), CFG, PON_08, PON_08 + timedelta(hours=2))
    assert wynik.state.health == 60


def test_ostatni_krok_ulamkowy():
    wynik = rules.simulate(PELNY, CFG, PON_08, PON_08 + timedelta(minutes=7))
    assert blisko(wynik.state.hunger, 100 - (100 / 24) * (7 / 60), 1e-6)


def test_determinizm_siatki():
    calosc = rules.simulate(PELNY, CFG, PON_08, PON_08 + timedelta(hours=4)).state
    polowa = rules.simulate(PELNY, CFG, PON_08, PON_08 + timedelta(hours=2)).state
    reszta = rules.simulate(polowa, CFG, PON_08 + timedelta(hours=2), PON_08 + timedelta(hours=4)).state
    for pole in ('hunger', 'fun', 'clean', 'health'):
        assert blisko(getattr(calosc, pole), getattr(reszta, pole), 1e-6)


def test_czas_wstecz_nie_zmienia_stanu():
    """Zmiana czasu 25.10: get_local_now() cofa się o godzinę → T < state_at."""
    stan = PetState(hunger=70)
    wynik = rules.simulate(stan, CFG, datetime(2026, 10, 25, 3, 0), datetime(2026, 10, 25, 2, 0))
    assert wynik.state == stan and wynik.died_at is None


def test_brudne_wartosci_z_bazy_sa_klamrowane():
    """Review Focus 4."""
    wynik = rules.simulate(PetState(hunger=130, fun=-20, health=250), CFG, PON_08, PON_08)
    assert (wynik.state.hunger, wynik.state.fun, wynik.state.health) == (100, 0, 100)


def test_juz_odeszly_nie_ozywa():
    wynik = rules.simulate(PetState(hunger=0, health=0), CFG, PON_08, PON_08 + timedelta(hours=5))
    assert wynik.state.health == 0 and wynik.died_at is None   # died_at zna baza, nie symulacja


# --- nastrój ---

@pytest.mark.parametrize('stan,nastroj', [
    (PetState(), 'szczesliwy'),
    (PetState(hunger=50, fun=50, clean=50), 'szczesliwy'),
    (PetState(hunger=49), 'glodny'),
    (PetState(fun=30, hunger=40), 'znudzony'),      # najniższy pasek decyduje
    (PetState(clean=10), 'brudny'),
    (PetState(clean=0), 'smutny'),
    (PetState(clean=0, health=74), 'chory'),
    (PetState(health=24.9), 'krytyczny'),
])
def test_mood(stan, nastroj):
    assert rules.mood(stan) == nastroj


# --- stadia ---

@pytest.mark.parametrize('dni,stadium', [(0, 'maluch'), (23.99, 'maluch'), (24, 'dziecko'),
                                          (79.9, 'dziecko'), (80, 'dorosly'), (400, 'dorosly')])
def test_stage(dni, stadium):
    wyklucie = PON_08
    teraz = wyklucie + timedelta(days=dni)
    assert rules.stage(wyklucie, teraz, CFG) == stadium


def test_age_days_zaokragla_w_dol():
    assert rules.age_days(PON_08, PON_08 + timedelta(days=5, hours=23)) == 5
    assert rules.age_days(PON_08, PON_08 - timedelta(hours=1)) == 0


# --- jajko ---

def test_jajko_bez_ogrzania_liczy_czas_1_do_1():
    assert rules.egg_progress_seconds(0, PON_08, None, PON_08 + timedelta(hours=10), CFG) == 10 * 3600


def test_jajko_ogrzanie_x2_przez_8h():
    boost = PON_08 + timedelta(hours=8)
    # 10 h od zapisu: 8 h ×2 + 2 h ×1 = 18 h
    assert rules.egg_progress_seconds(0, PON_08, boost, PON_08 + timedelta(hours=10), CFG) == 18 * 3600
    # 3 h od zapisu, boost nadal trwa: 3 h ×2
    assert rules.egg_progress_seconds(0, PON_08, boost, PON_08 + timedelta(hours=3), CFG) == 6 * 3600


def test_jajko_dolicza_zapisany_postep():
    assert rules.egg_progress_seconds(5000, PON_08, None, PON_08 + timedelta(hours=1), CFG) == 5000 + 3600


def test_jajko_boost_sprzed_zapisu_liczy_sie_jako_zero():
    """Review Focus 5."""
    stary_boost = PON_08 - timedelta(hours=2)
    assert rules.egg_progress_seconds(0, PON_08, stary_boost, PON_08 + timedelta(hours=4), CFG) == 4 * 3600


def test_jajko_czas_wstecz_nie_cofa_postepu():
    assert rules.egg_progress_seconds(7200, PON_08, None, PON_08 - timedelta(hours=1), CFG) == 7200


def test_egg_is_ready_i_pct():
    assert rules.egg_is_ready(48 * 3600, 48) is True
    assert rules.egg_is_ready(48 * 3600 - 1, 48) is False
    assert rules.egg_progress_pct(84 * 3600, 168) == 50.0
    assert rules.egg_progress_pct(200 * 3600, 168) == 100.0
    assert rules.egg_progress_pct(0, 168) == 0.0
```

- [ ] **Step 2: Uruchom testy — mają paść**

Run: `venv/bin/python -m pytest tests/test_pets_rules.py -q 2>&1 | tail -3`
Expected: nowe testy FAIL — `AttributeError: module 'modules.pets.rules' has no attribute 'simulate'`.

- [ ] **Step 3: Dopisz część 2 `rules.py`**

Na końcu `modules/pets/rules.py`:

```python
# ---------------------------------------------------------------------------
# Symulacja krokami co 5 minut
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SimResult:
    state: PetState
    died_at: datetime | None


def _advance(state, tempo, godziny):
    """Liniowy ruch wszystkich wartości o `godziny` przy zadanym tempie, z klamrą 0–100."""
    return replace(
        state,
        hunger=_clamp(state.hunger + tempo['hunger'] * godziny),
        fun=_clamp(state.fun + tempo['fun'] * godziny),
        clean=_clamp(state.clean + tempo['clean'] * godziny),
        health=_clamp(state.health + tempo['health'] * godziny),
    )


def simulate(state, cfg, from_dt, to_dt):
    """Stan w chwili to_dt, licząc od stanu zapisanego w from_dt.

    Kroki co STEP_SECONDS od from_dt (siatka startuje w from_dt → odczyty bez akcji są
    spójne), ostatni krok ułamkowy. elapsed klamrowane do ≥ 0 (zmiana czasu 25.10 cofa
    zegar). Odejście: zdrowie dobija do 0 → died_at interpolowane liniowo wewnątrz kroku,
    stan zamrożony ze zdrowiem 0. Pupil już martwy na wejściu nie ożywa (died_at=None —
    tę datę zna baza).
    """
    state = clamp_state(state)
    elapsed = max(0.0, (to_dt - from_dt).total_seconds())
    if elapsed == 0.0 or state.health <= 0.0:
        return SimResult(state, None)

    dt = from_dt
    pozostalo = elapsed
    while pozostalo > 1e-9:
        krok = min(float(STEP_SECONDS), pozostalo)
        tempo = rates_per_hour(state, dt, cfg)
        godziny = krok / 3600.0
        nowy = _advance(state, tempo, godziny)
        if nowy.health <= 0.0:
            spadek_na_h = -tempo['health']          # > 0, bo zdrowie spadło
            died_at = dt + timedelta(hours=state.health / spadek_na_h)
            return SimResult(replace(nowy, health=0.0), died_at)
        state = nowy
        dt = dt + timedelta(seconds=krok)
        pozostalo -= krok
    return SimResult(state, None)


# ---------------------------------------------------------------------------
# Nastrój i stadium
# ---------------------------------------------------------------------------

_NASTROJ_PASKA = {'hunger': 'glodny', 'fun': 'znudzony', 'clean': 'brudny'}


def mood(state):
    """Jedna etykieta, pierwsza pasująca od góry (spec §2.6)."""
    if state.health < CRITICAL_BELOW:
        return 'krytyczny'
    if state.health < SICK_BELOW:
        return 'chory'
    if any(getattr(state, bar) <= 0 for bar in BARS):
        return 'smutny'
    najnizszy = min(BARS, key=lambda bar: getattr(state, bar))
    if getattr(state, najnizszy) < HAPPY_FROM:
        return _NASTROJ_PASKA[najnizszy]
    return 'szczesliwy'


STAGES = ('maluch', 'dziecko', 'dorosly')


def age_days(hatched_at, now):
    return int(max(0.0, (now - hatched_at).total_seconds()) // 86400)


def stage(hatched_at, now, cfg):
    """Stadium z czasu kalendarzowego od wyklucia: 0–24 maluch, 24–80 dziecko, 80+ dorosły."""
    dni = max(0.0, (now - hatched_at).total_seconds()) / 86400.0
    if dni >= float(cfg.stage_days['adult']):
        return 'dorosly'
    if dni >= float(cfg.stage_days['child']):
        return 'dziecko'
    return 'maluch'


# ---------------------------------------------------------------------------
# Jajko (analitycznie, bez kroków)
# ---------------------------------------------------------------------------

def egg_progress_seconds(progress_sec, progress_at, boost_until, now, cfg):
    """Postęp inkubacji: zapisany + czas od zapisu, przy czym odcinek do boost_until liczy ×factor.

    boost_until sprzed progress_at (stary boost) daje 0 s przyspieszenia; czas wstecz daje 0.
    """
    elapsed = max(0.0, (now - progress_at).total_seconds())
    boosted = 0.0
    if boost_until is not None:
        boosted = min(elapsed, max(0.0, (boost_until - progress_at).total_seconds()))
    factor = float(cfg.boost['factor'])
    return float(progress_sec) + (elapsed - boosted) + boosted * factor


def egg_is_ready(progress_seconds, egg_hours):
    return progress_seconds >= float(egg_hours) * 3600.0


def egg_progress_pct(progress_seconds, egg_hours):
    calosc = float(egg_hours) * 3600.0
    if calosc <= 0:
        return 100.0
    return round(min(100.0, 100.0 * float(progress_seconds) / calosc), 1)
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `venv/bin/python -m pytest tests/test_pets_rules.py -q 2>&1 | tail -3`
Expected: `55 passed` (18 z Task 5 + 16 symulacji + 8 nastrojów + 6 stadiów + 1 wiek + 6 jajka).
Jeśli `test_odejscie_po_okolo_96h…` da liczbę spoza 96–104 — sprawdź najpierw, czy
`rates_per_hour` nie spowalnia zdrowia we śnie (nie wolno) i czy pasek na zerze budzi.

- [ ] **Step 5: Commit**

```bash
git add modules/pets/rules.py tests/test_pets_rules.py
git commit -m "$(cat <<'EOF'
feat(pupile): rules.py - symulacja, odejscie, nastroj, stadia, jajko

simulate() krokami 5 min od state_at z ulamkowym ostatnim krokiem,
klamra czasu wstecz (DST) i brudnych wartosci, died_at interpolowane
w kroku; mood(), stage(), postep jajka z ogrzaniem x2 liczony analitycznie.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Pełna suita, przegląd etapu, aktualizacja taska

**Files:** brak nowych; ewentualne poprawki z suity.

- [ ] **Step 1: Cała suita**

Run:
```bash
venv/bin/python -m pytest -q --no-header -p no:cacheprovider 2>&1 | tail -3
```
Expected: `passed` = baseline z Task 0 + 84 nowe testy (fundament 9, migracja 3,
config 17, rules 55). Żadnego nowego `failed`. Jeśli pada coś spoza `tests/test_pets_*` —
zdiagnozuj (najczęstsza przyczyna: kolizja backrefu `User.pets`/`pet_profile` albo zmieniony
`to_dict()` preferencji w jakimś teście snapshotowym) i napraw przed zgłoszeniem.

- [ ] **Step 1b: Dopnij reguły do prawdziwego `PetConfig` (integracja Task 4 + Task 6)**

Dopisz na końcu `tests/test_pets_rules.py`:

```python
def test_prawdziwy_PetConfig_jest_zgodny_z_regulami():
    """Atrapa _cfg() i PetConfig muszą mieć te same pola i liczby."""
    from modules.pets.config import PetConfig
    cfg = PetConfig()
    for pole in ('decay_hours', 'night', 'health_drop_hours', 'health_regen_hours',
                 'egg_hours', 'start_egg_hours', 'boost', 'max_stars', 'stage_days'):
        assert getattr(cfg, pole) == getattr(CFG, pole), pole
    wynik = rules.simulate(PELNY, cfg, PON_08, PON_08 + timedelta(hours=12))
    assert blisko(wynik.state.hunger, 50)
    assert rules.stage(PON_08, PON_08 + timedelta(days=30), cfg) == 'dziecko'
    assert rules.egg_progress_seconds(0, PON_08, None, PON_08 + timedelta(hours=1), cfg) == 3600
```

Run: `venv/bin/python -m pytest tests/test_pets_rules.py -q 2>&1 | tail -2`
Expected: `56 passed`. Commit: `test(pupile): reguly zgodne z prawdziwym PetConfig`.

- [ ] **Step 2: Sprawdź, że `rules.py` nie importuje Flaska ani SQLAlchemy**

Run: `grep -nE "^(from|import) (flask|sqlalchemy|extensions|modules\.)" modules/pets/rules.py`
Expected: brak wyników.

- [ ] **Step 3: Sprawdź, że aplikacja wstaje z zarejestrowanym modułem**

Run:
```bash
venv/bin/python -c "from app import create_app; a=create_app('testing'); print(sorted(b for b in a.blueprints if b.startswith('pets')))"
```
Expected: `['pets', 'pets_admin']`.

- [ ] **Step 4: Stan gałęzi**

Run: `git log --oneline main..feat/pupile`
Expected: 6 commitów (Task 1–6) nad `main`. **Nie pushuj** — zgłoś Konradowi gotowość etapu 1
z liczbą testów i poproś o decyzję o merge/pushu (push = auto-deploy; sama migracja i modele są
bezpieczne przy wyłączonej fladze, ale decyzja należy do niego).

- [ ] **Step 5: Komentarz w ClickUp**

Dodaj komentarz do taska `869ffdb58`: „Etap 1 (fundament) gotowy na gałęzi `feat/pupile`:
modele + migracja `f3e9a1c7b2d4` + PetConfig + rules.py, N testów. Czeka na decyzję o merge."
Status taska zostaje `in progress`.
