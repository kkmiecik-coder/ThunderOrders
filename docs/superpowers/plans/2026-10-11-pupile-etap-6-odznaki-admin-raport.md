# Pupile — etap 6: odznaki, panel admina, raport, GA4, tour, dokumentacja — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Domknąć v1 pupili: odznaki za opiekę (seed + ewaluatory + cron), panel `/admin/pupile` (włącznik, rollout, liczby, statystyki, przyznawanie jajek), `flask pets report --days N`, zdarzenia GA4, krok toura i checklista włączenia na produkcji.

**Architecture:** Odznaki wpinają się w istniejący `AchievementService` (`EVENT_METRICS['pet_event']` + ewaluatory w `checkers.py`; `check_event(user, 'pet_event')` już woła `achievements_after_commit` po wykluciu i akcji). Panel admina to osobny blueprint `pets_admin_bp` (zarejestrowany od etapu 1) z formularzem zapisującym `Settings` przez `PetConfig`-owe nazwy i walidację jak w `_przetworz`. Raport to czyste funkcje nad `pet_events`/`pets`/`pet_profiles`/`push_subscriptions` z `now=` do testów; cron dopisuje zdarzenie `alert` przy podniesieniu `notify_level`, żeby raport umiał policzyć reakcję na ostrzeżenia.

**Tech Stack:** Flask 3, SQLAlchemy 2, pytest (`venv/bin/python -m pytest`), Jinja2 + CSS admina (`ca-*` z `static/css/pages/admin/contests.css` jako wzór), vanilla JS, GA4 przez `window.trackEvent` (guard `typeof`).

**Spec:** `docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md` — §3.7 (raport), §3.8 (odznaki), §5 (panel admina), §7 (wdrożenie), §8 (testy: `test_pets_achievements.py`, `test_pets_admin.py`, `test_pets_report.py`), §9 pkt 6.

## Global Constraints

- Klucze `Settings` snake_case `pets_*`; json przez `Settings.set_value(key, json.dumps(v), type='json')`; każdy zapis `updated_by=current_user.id`; po zapisie `reset_feature_cache()` (cache flagi 10 s).
- Walidacja formularza admina = te same reguły co `modules/pets/config.py::_przetworz` (liczby dodatnie poza `rollout_pct`, `rescue_hours`, `pity_after`, `max_stars`; `0 ≤ pct ≤ 100`; `0 < factor ≤ 1` dla nocy; `boost.factor ≥ 1`); błąd walidacji = brak zapisu czegokolwiek + komunikat przy polu.
- `role_required('admin', 'mod')` na każdej trasie admina; `log_activity(user=current_user, action='pets_settings_updated' | 'pet_egg_granted', entity_type='user'|'settings', entity_id=…)`.
- Light + dark mode w CSS admina; zero inline JS/CSS.
- Odznaki: kategoria `pets` (enum już ma `pets` i `cosmic`); bez odznak za odejście; `pet-adults-8` jako `trigger_type='cron'` (stadium wynika z czasu).
- Raport i panel liczą z DANYCH (zdarzeń i wierszy), nie ze statusów cache; `now=` wstrzykiwalne.
- GA4: `trackEvent('pet_action', {action, mood})` tylko z guardem `typeof window.trackEvent === 'function'`, bez imion i identyfikatorów.
- Repo publiczne: checklista wdrożenia bez IP/haseł (ścieżki na serwerze dozwolone jak w instrukcji crona).

## Review Focus

1. **Odznaka „Komplet” przy duplikacie**: użytkownik ma 7 gatunków w albumie, ósmy wykluwa się jako duplikat (`merged`) — gatunek i tak jest „odkryty”. Oczekiwanie: `pet_species_discovered` liczy gatunki po wszystkich pupilach użytkownika poza jajkami (alive/dead/merged). Test w Task 1 (`test_species_discovered_liczy_merged`).
2. **`pet-adults-8` po śmierci jednego z ośmiu**: cron odznak nie może odblokować, gdy w chwili sprawdzenia żyje 7 dorosłych, nawet jeśli wczoraj było 8. Oczekiwanie: metryka liczy stan *teraz* z `hatched_at` i `cfg.stage_days`. Test w Task 1.
3. **Zapis ustawień z jednym złym polem**: admin wpisuje `pets_rollout_pct=150` i poprawne pozostałe. Oczekiwanie: nic się nie zapisuje (żadnego `set_value` przed pełną walidacją), formularz wraca z komunikatem przy polu. Test w Task 3 (`test_ustawienia_bledne_pole_nic_nie_zapisuje`).
4. **Przyznanie jajka użytkownikowi bez profilu** (nie odebrał startowego): `lock_profile(user)` rzuca. Oczekiwanie: czytelny komunikat „Użytkownik nie odebrał jeszcze startowego jajka” zamiast 500. Test w Task 3.
5. **Raport na pustej bazie / dzieleniu przez zero** (0 żywych → „odejścia na 100 żywych”): Oczekiwanie: `None`/`0.0` i czytelny wiersz, nie `ZeroDivisionError`. Test w Task 2.

---

### Task 1 (TDD): odznaki — metryki, ewaluatory, seed, cron

**Files:**
- Modify: `modules/achievements/services.py:43-57` (`EVENT_METRICS['pet_event']`), `modules/achievements/checkers.py` (6 ewaluatorów + wpisy w `METRIC_EVALUATORS`), `modules/achievements/seed.py` (sekcja `# === PUPILE (pets) ===`, 9 wpisów)
- Test: `tests/test_pets_achievements.py`

**Interfaces:**
- Consumes: `PetEvent` (`hatch_new`, `hatch_dupe`), `Pet` (`status`, `species`, `stars`, `care_days`, `hatched_at`), `rules.stage(hatched_at, now, cfg)` → `'maluch'|'dziecko'|'dorosly'`, `PetConfig.load()`, `AchievementService().check_event(user, 'pet_event')`, `run_daily_checks()`.
- Produces: metryki `pets_hatched`, `pet_species_discovered`, `pet_adult_alive`, `pet_stars_max`, `pet_care_days_max` (+ istniejąca `all_badges_unlocked`); slugi odznak jak w specu §3.8.

- [ ] **Step 1: Testy (RED)** — `tests/test_pets_achievements.py`:

```python
"""Odznaki za pupile (spec §3.8): metryki, zdarzenie pet_event, cron pet-adults-8."""
from datetime import timedelta

from tests.pets_helpers import T0, zaloz_profil, zaloz_pupila, zaloz_zmarlego


def _seed(db):
    from modules.achievements.seed import seed_achievements
    seed_achievements()
    db.session.commit()


def _odblokowane(user):
    from modules.achievements.models import UserAchievement
    return sorted(ua.achievement.slug for ua in UserAchievement.query.filter_by(user_id=user.id).all())


def test_metryki_pupili_zarejestrowane():
    from modules.achievements.checkers import METRIC_EVALUATORS
    from modules.achievements.services import EVENT_METRICS
    for m in ('pets_hatched', 'pet_species_discovered', 'pet_adult_alive', 'pet_stars_max', 'pet_care_days_max'):
        assert m in METRIC_EVALUATORS and m in EVENT_METRICS['pet_event']
    assert 'all_badges_unlocked' in EVENT_METRICS['pet_event']


def test_pierwsze_wyklucie_odblokowuje(db, make_user):
    from modules.achievements.services import AchievementService
    from modules.pets.common import add_event
    _seed(db)
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user)
    add_event(user.id, 'hatch_new', T0, pet_id=pet.id)
    db.session.commit()
    nowe = AchievementService().check_event(user, 'pet_event')
    assert 'pet-first-hatch' in [a.slug for a in nowe]


def test_species_discovered_liczy_merged(db, make_user):
    """Review Focus 1: duplikat (merged) też odkrywa gatunek."""
    from modules.achievements.checkers import get_metric_value
    user = make_user()
    zaloz_profil(user)
    for s in ('kotek', 'mis', 'piesek'):
        zaloz_pupila(user, species=s)
    zaloz_pupila(user, species='kroliczek', status='merged')
    zaloz_pupila(user, status='egg', species=None)
    wartosc, spelnia = get_metric_value(user, 'pet_species_discovered', {'metric': 'pet_species_discovered', 'threshold': 4})
    assert (wartosc, spelnia) == (4, True)


def test_care_days_max_i_stars_max(db, make_user):
    from modules.achievements.checkers import get_metric_value
    user = make_user()
    zaloz_profil(user)
    zaloz_pupila(user, species='kotek', care_days=12, stars=1)
    zaloz_zmarlego(user, species='mis', care_days=40, stars=3)   # zmarły też się liczy (opieka była)
    assert get_metric_value(user, 'pet_care_days_max', {'threshold': 30}) == (40, True)
    assert get_metric_value(user, 'pet_stars_max', {'threshold': 3}) == (3, True)
    assert get_metric_value(user, 'pet_care_days_max', {'threshold': 100}) == (40, False)


def test_adult_alive_liczy_stan_teraz(db, make_user):
    """Review Focus 2: 8 dorosłych wczoraj, dziś 7 — nie odblokowuje."""
    from modules.achievements.checkers import get_metric_value
    from modules.pets.species import SPECIES_SLUGS
    user = make_user()
    zaloz_profil(user)
    dawno = T0 - timedelta(days=100)
    for slug in SPECIES_SLUGS[:7]:
        zaloz_pupila(user, species=slug, hatched_at=dawno, now=dawno)
    zaloz_zmarlego(user, species=SPECIES_SLUGS[7], hatched_at=dawno, died_at=T0 - timedelta(hours=1))
    assert get_metric_value(user, 'pet_adult_alive', {'threshold': 8}, {'now': T0}) == (7, False)
    zaloz_pupila(user, species='kotek', name='Nowy', hatched_at=T0 - timedelta(days=1), now=T0, status='alive')
    # ósmy żyje, ale jest maluchem → nadal 7 dorosłych
    assert get_metric_value(user, 'pet_adult_alive', {'threshold': 8}, {'now': T0})[0] == 7


def test_cron_check_daily_odblokowuje_osmiu_doroslych(db, make_user):
    from modules.achievements.services import AchievementService
    from modules.pets.species import SPECIES_SLUGS
    _seed(db)
    user = make_user()
    zaloz_profil(user)
    dawno = T0 - timedelta(days=400)
    for slug in SPECIES_SLUGS:
        zaloz_pupila(user, species=slug, hatched_at=dawno, now=dawno)
    AchievementService().run_daily_checks()
    assert 'pet-adults-8' in _odblokowane(user)


def test_seed_ma_komplet_odznak_pupili(db):
    from modules.achievements.models import Achievement
    _seed(db)
    slugi = {a.slug: a for a in Achievement.query.filter_by(category='pets').all()}
    assert set(slugi) == {'pet-first-hatch', 'pet-care-7', 'pet-species-4', 'pet-species-8', 'pet-adults-8',
                          'pet-stars-3', 'pet-care-30', 'pet-care-100', 'pet-care-365'}
    assert slugi['pet-adults-8'].trigger_type == 'cron' and slugi['pet-adults-8'].rarity == 'cosmic'
    assert slugi['pet-species-8'].rarity == 'legendary' and slugi['pet-care-7'].tier_group == 'pet-care'
```

Uwaga: `zaloz_pupila(user, status='egg', species=None)` wymaga, by helper przyjmował `species=None` — przyjmuje (`dane.update(pola)` nadpisuje). `zaloz_pupila(..., hatched_at=dawno, now=dawno)` ustawia `state_at=dawno` — do metryk nieistotne (nie symulujemy).

- [ ] **Step 2: RED** — `venv/bin/python -m pytest tests/test_pets_achievements.py -q -p no:cacheprovider > <scratch>/e6t1_red.txt 2>&1; echo $?` → Expected: 7 failed (KeyError `pet_event`, metryki `(0, False)`, brak slugów w seedzie).

- [ ] **Step 3: ewaluatory** — na końcu sekcji funkcji w `checkers.py` (przed `METRIC_EVALUATORS`):

```python
# === PUPILE (modules/pets) — metryki liczą z wierszy pets/pet_events, nie ze statusu w cache ===

def _pets_hatched(user, config, context):
    from modules.pets.models import PetEvent
    n = PetEvent.query.filter(PetEvent.user_id == user.id, PetEvent.type.in_(('hatch_new', 'hatch_dupe'))).count()
    return (n, n >= config.get('threshold', 1))


def _pet_species_discovered(user, config, context):
    from modules.pets.models import Pet
    n = (db.session.query(Pet.species).filter(Pet.user_id == user.id, Pet.species.isnot(None),
                                              Pet.status.in_(('alive', 'dead', 'merged')))
         .distinct().count())
    return (n, n >= config.get('threshold', 8))


def _pet_adult_alive(user, config, context):
    from modules.pets import rules
    from modules.pets.config import PetConfig
    from modules.pets.models import Pet
    now = (context or {}).get('now') or get_local_now()
    cfg = PetConfig.load()
    zywe = Pet.query.filter(Pet.user_id == user.id, Pet.status == 'alive', Pet.hatched_at.isnot(None)).all()
    n = sum(1 for p in zywe if rules.stage(p.hatched_at, now, cfg) == 'dorosly')
    return (n, n >= config.get('threshold', 8))


def _pet_stars_max(user, config, context):
    from modules.pets.models import Pet
    m = db.session.query(db.func.max(Pet.stars)).filter(Pet.user_id == user.id, Pet.status.in_(('alive', 'dead'))).scalar() or 0
    return (int(m), m >= config.get('threshold', 3))


def _pet_care_days_max(user, config, context):
    from modules.pets.models import Pet
    m = db.session.query(db.func.max(Pet.care_days)).filter(Pet.user_id == user.id, Pet.status.in_(('alive', 'dead'))).scalar() or 0
    return (int(m), m >= config.get('threshold', 7))
```

i w `METRIC_EVALUATORS`: `'pets_hatched': _pets_hatched, 'pet_species_discovered': _pet_species_discovered, 'pet_adult_alive': _pet_adult_alive, 'pet_stars_max': _pet_stars_max, 'pet_care_days_max': _pet_care_days_max`. `PetConfig.load()` wymaga kontekstu aplikacji z `g` — `run_daily_checks` działa w CLI z `app.app_context()`; `g` istnieje w kontekście aplikacji (Flask ≥ 2.2), więc OK. Sprawdź, czy `rules.stage` zwraca dokładnie `'dorosly'` (grep `rules.py:193`); jeśli zwraca inną etykietę, użyj jej.

- [ ] **Step 4: `EVENT_METRICS`** — dodaj `'pet_event': ['pets_hatched', 'pet_species_discovered', 'pet_stars_max', 'pet_care_days_max', 'all_badges_unlocked']` (bez `pet_adult_alive` — to cron).

- [ ] **Step 5: seed** — sekcja w `ACHIEVEMENTS` (przed meta-odznakami, jeśli seed ma kolejność znaczącą dla `sort_order` — zachowaj styl sąsiadów):

```python
    # === PUPILE (pets) — spec pupili §3.8; ikony dogrywa admin w panelu ===
    {'slug': 'pet-first-hatch', 'name': 'Pierwsze pęknięcie', 'description': 'Wykluj swojego pierwszego pupila',
     'category': 'pets', 'rarity': 'common', 'tier': None, 'tier_group': None,
     'trigger_type': 'event', 'trigger_config': {'metric': 'pets_hatched', 'threshold': 1}},
    {'slug': 'pet-care-7', 'name': 'Pierwszy tydzień', 'description': '7 dni opieki nad jednym pupilem',
     'category': 'pets', 'rarity': 'common', 'tier': 1, 'tier_group': 'pet-care',
     'trigger_type': 'event', 'trigger_config': {'metric': 'pet_care_days_max', 'threshold': 7}},
    {'slug': 'pet-care-30', 'name': 'Opiekun', 'description': '30 dni opieki nad jednym pupilem',
     'category': 'pets', 'rarity': 'rare', 'tier': 2, 'tier_group': 'pet-care',
     'trigger_type': 'event', 'trigger_config': {'metric': 'pet_care_days_max', 'threshold': 30}},
    {'slug': 'pet-care-100', 'name': 'Oddany opiekun', 'description': '100 dni opieki nad jednym pupilem',
     'category': 'pets', 'rarity': 'epic', 'tier': 3, 'tier_group': 'pet-care',
     'trigger_type': 'event', 'trigger_config': {'metric': 'pet_care_days_max', 'threshold': 100}},
    {'slug': 'pet-care-365', 'name': 'Opiekun roku', 'description': '365 dni opieki nad jednym pupilem',
     'category': 'pets', 'rarity': 'legendary', 'tier': 4, 'tier_group': 'pet-care',
     'trigger_type': 'event', 'trigger_config': {'metric': 'pet_care_days_max', 'threshold': 365}},
    {'slug': 'pet-species-4', 'name': 'Pół drużyny', 'description': '4 gatunki w albumie',
     'category': 'pets', 'rarity': 'rare', 'tier': 1, 'tier_group': 'pet-species',
     'trigger_type': 'event', 'trigger_config': {'metric': 'pet_species_discovered', 'threshold': 4}},
    {'slug': 'pet-species-8', 'name': 'Komplet', 'description': 'Wszystkie 8 gatunków w albumie',
     'category': 'pets', 'rarity': 'legendary', 'tier': 2, 'tier_group': 'pet-species',
     'trigger_type': 'event', 'trigger_config': {'metric': 'pet_species_discovered', 'threshold': 8}},
    {'slug': 'pet-stars-3', 'name': 'Gwiazdor', 'description': 'Pupil z trzema gwiazdkami',
     'category': 'pets', 'rarity': 'epic', 'tier': None, 'tier_group': None,
     'trigger_type': 'event', 'trigger_config': {'metric': 'pet_stars_max', 'threshold': 3}},
    {'slug': 'pet-adults-8', 'name': 'Ośmiu dorosłych', 'description': 'Ośmiu dorosłych pupili żyjących naraz',
     'category': 'pets', 'rarity': 'cosmic', 'tier': None, 'tier_group': None,
     'trigger_type': 'cron', 'trigger_config': {'metric': 'pet_adult_alive', 'threshold': 8}},
```

Jeśli słownik seedów ma pola, których tu nie ma (np. `sort_order`, `is_hidden_until_unlocked`) — uzupełnij jak sąsiedzi. Jeśli `all_badges_unlocked` (meta „wszystkie odznaki profilu”) liczy po kategorii, nie dotykaj — pupile mają własne meta w ramach `pet-species-8`.

- [ ] **Step 6: GREEN** — pytest jw. → Expected: 7 passed; potem `venv/bin/python -m pytest tests/test_achievements*.py tests/test_pets_eggs.py tests/test_pets_actions.py -q -p no:cacheprovider` → passed (istniejące testy odznak i `new_achievements` z wyklucia).

- [ ] **Step 7: Commit** — `feat(pupile): odznaki za pupile - metryki, seed, cron pet-adults-8`.

---

### Task 2 (TDD): `flask pets report --days N` + zdarzenie `alert`

**Files:**
- Create: `modules/pets/report.py`
- Modify: `modules/pets/notifications.py` (`collect_for_user`: przy podniesieniu `notify_level` → `add_event(user.id, 'alert', now, pet_id=pet.id, value=poziom)`), `modules/pets/models.py` (`'alert'` w `EVENT_TYPES` i `PRUNABLE_EVENT_TYPES`), `app.py` (komenda `pets report`)
- Test: `tests/test_pets_report.py`, `tests/test_pets_cron.py` (1 test na zdarzenie `alert`)

**Interfaces:**
- Consumes: `PetEvent` (`claim` z `egg_source` przez `Pet`, `hatch_*`, `CARE_ACTIONS`, `die.value` = kod paska: sprawdź w `persist_death` jakie kody — `grep -n "przyczyna" modules/pets/common.py`), `PushSubscription.is_active`, `PetProfile.start_egg_claimed_at`.
- Produces: `build_report(days, now=None) -> dict` z kluczami: `window` {days, since, until}, `funnel` {profiles, claimed_start, hatched_any, alive_d7}, `retention` {d1, d7, d30: {cohort, active, pct}}, `caretakers_daily` [(date_iso, count)], `deaths` {total, per_day, per_100_alive, causes: {hunger, fun, clean}}, `alert_reaction_hours` {median, n}, `push_owners_pct` {owners, with_push, pct}, `rescue_claimed_7d` {deaths, claimed, pct}; `format_report(raport) -> str` (tabela tekstowa do CLI).

- [ ] **Step 1: Test zdarzenia `alert` (RED)** — w `tests/test_pets_cron.py`:

```python
def test_podniesienie_poziomu_zapisuje_zdarzenie_alert(db, make_user):
    """Etap 6: raport liczy czas reakcji na ostrzeżenie z pet_events.type='alert'."""
    from modules.pets.notifications import collect_for_user
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, fun=0.0)
    collect_for_user(user, T0 + timedelta(hours=1), _cfg())
    db.session.commit()
    alerty = PetEvent.query.filter_by(pet_id=pet.id, type='alert').all()
    assert len(alerty) == 1 and alerty[0].value == pet.notify_level >= 1
    collect_for_user(user, T0 + timedelta(hours=2), _cfg())      # ten sam poziom → bez drugiego wpisu
    db.session.commit()
    assert PetEvent.query.filter_by(pet_id=pet.id, type='alert').count() == 1
```

- [ ] **Step 2: Testy raportu (RED)** — `tests/test_pets_report.py`:

```python
"""flask pets report (spec §3.7) — metryki na danych syntetycznych, bez dzielenia przez zero."""
from datetime import timedelta

from tests.pets_helpers import T0, zaloz_profil, zaloz_pupila, zaloz_zmarlego


def test_raport_pusta_baza_bez_wyjatkow(db):
    from modules.pets.report import build_report, format_report
    r = build_report(7, now=T0)
    assert r['funnel']['profiles'] == 0 and r['deaths']['per_100_alive'] is None
    assert 'Profile' in format_report(r)


def test_lejek_retencja_i_odejscia(db, make_user):
    from modules.pets.common import add_event
    from modules.pets.report import build_report
    from modules.notifications.models import PushSubscription
    start = T0 - timedelta(days=10)
    # A: odebrał, wykluł, dba codziennie, ma push, pupil żyje
    a = make_user(); zaloz_profil(a, now=start)
    pa = zaloz_pupila(a, now=start + timedelta(days=2))
    add_event(a.id, 'claim', start, pet_id=pa.id); add_event(a.id, 'hatch_new', start + timedelta(days=2), pet_id=pa.id)
    for d in range(1, 10):
        add_event(a.id, 'feed', start + timedelta(days=d, hours=9), pet_id=pa.id)
    db.session.add(PushSubscription(user_id=a.id, endpoint='e', p256dh_key='k', auth_key='a', is_active=True))
    # B: odebrał, wykluł, porzucił → pupil odszedł z głodu 3 dni temu, ratunkowe odebrane
    b = make_user(); zaloz_profil(b, now=start)
    pb = zaloz_zmarlego(b, species='mis', died_at=T0 - timedelta(days=3), hatched_at=start + timedelta(days=2),
                        rescue_egg_claimed_at=T0 - timedelta(days=2))
    add_event(b.id, 'claim', start, pet_id=pb.id); add_event(b.id, 'hatch_new', start + timedelta(days=2), pet_id=pb.id)
    add_event(b.id, 'alert', T0 - timedelta(days=5), pet_id=pb.id, value=1)
    add_event(b.id, 'feed', T0 - timedelta(days=5) + timedelta(hours=6), pet_id=pb.id)
    add_event(b.id, 'die', T0 - timedelta(days=3), pet_id=pb.id, value=1)
    # C: tylko profil (odebrał), nic więcej
    c = make_user(); zaloz_profil(c, now=start)
    db.session.commit()

    r = build_report(14, now=T0)
    assert r['funnel'] == {'profiles': 3, 'claimed_start': 2, 'hatched_any': 2, 'alive_d7': 1}
    assert r['retention']['d7']['cohort'] == 2 and r['retention']['d7']['active'] == 1
    assert r['deaths']['total'] == 1 and r['deaths']['causes']['hunger'] == 1
    assert r['deaths']['per_100_alive'] == 100.0            # 1 odejście / 1 żywy
    assert r['alert_reaction_hours'] == {'median': 6.0, 'n': 1}
    assert r['push_owners_pct'] == {'owners': 1, 'with_push': 1, 'pct': 100.0}
    assert r['rescue_claimed_7d'] == {'deaths': 1, 'claimed': 1, 'pct': 100.0}
    assert any(c == 1 for _, c in r['caretakers_daily'])
```

Kody przyczyn w `die.value`: ustal z `persist_death` (np. `1=hunger, 2=fun, 3=clean`) i użyj tych samych w `causes`. `claimed_start` = profile z `start_egg_claimed_at` w oknie ALBO zdarzenie `claim` — przyjmij: liczba użytkowników ze zdarzeniem `claim` (dowolne jajko) w oknie; `hatched_any` = użytkownicy ze zdarzeniem `hatch_*` w oknie; `alive_d7` = użytkownicy z `claim` ≥ 7 dni temu, którzy mają żywego pupila teraz; retencja `dN`: kohorta = użytkownicy z pierwszym `claim` ≥ N dni temu (w oknie), aktywny = dowolne zdarzenie z `CARE_ACTIONS` w dniu `claim + N` (±12 h). `alert_reaction_hours`: dla każdego `alert` najbliższe późniejsze zdarzenie opieki tego pupila; mediana godzin.

- [ ] **Step 3: RED** — oba pliki → Expected: `ModuleNotFoundError: modules.pets.report`, brak `alert`.

- [ ] **Step 4: implementacja** — `report.py` (czyste funkcje; zapytania przez `db.session.query`, grupowanie w Pythonie — wolumen pupili jest mały), `alert` w `collect_for_user` tuż po `pet.notify_level = poziom` (gdy poziom wzrósł), modele: `'alert'` dopisane do `EVENT_TYPES` i `PRUNABLE_EVENT_TYPES` (90 dni wystarczy raportowi `--days ≤ 30`), komenda w `app.py` w grupie `pets`:

```python
    @pets.command('report')
    @click.option('--days', default=7, show_default=True, type=int)
    def pets_report(days):
        """Metryki pupili (lejek, retencja, odejścia, reakcja na ostrzeżenia, push, ratunkowe)."""
        from modules.pets.report import build_report, format_report
        click.echo(format_report(build_report(days)))
```

- [ ] **Step 5: GREEN** — `venv/bin/python -m pytest tests/test_pets_report.py tests/test_pets_cron.py -q -p no:cacheprovider` → passed. Ręcznie: `venv/bin/flask pets report --days 7` na bazie podglądu (ustaw `DATABASE_URL`/konfigurację jak skrypt podglądu albo wywołaj `build_report` w `--smoke`) → tabela bez wyjątków.

- [ ] **Step 6: Commit** — `feat(pupile): flask pets report + zdarzenie alert w cronie`.

---

### Task 3 (TDD): panel admina `/admin/pupile`

**Files:**
- Create: `modules/pets/admin_routes.py`, `templates/admin/pets/index.html`, `static/css/pages/admin/pets.css`, `static/js/pages/admin/pets.js`
- Modify: `modules/pets/__init__.py` (`from . import admin_routes`), `templates/components/sidebar_admin.html` (pozycja „Pupile” po „Konkursy”, ikona `img/icons/paw.svg`, `active` gdy `request.endpoint.startswith('pets_admin.')`)
- Test: `tests/test_pets_admin.py`

**Interfaces:**
- Consumes: `PetConfig` (pola i `_przetworz` do walidacji — wyeksponuj w `config.py` funkcję `validate_settings(form: dict) -> (values: dict[str, str], errors: dict[str, str])`, która dla każdego klucza `pets_*` zwraca gotowy string do `set_value` i typ), `service.admin_grant_egg(user)`, `PetError`, `log_activity`, `reset_feature_cache`, `report.build_report(7)` (statystyki 7 dni) + zapytania zliczające (profile, żywi per gatunek, jajka w inkubacji/do odebrania, rozkład stadiów, komplety = użytkownicy z 8 gatunkami w albumie).
- Produces: trasy `pets_admin.index` (GET `/admin/pupile`), `pets_admin.save_settings` (POST `/admin/pupile/ustawienia`), `pets_admin.search_users` (GET `/admin/pupile/szukaj?q=` → JSON `[{id, email, name, pets: [{name, species_name, mood, stage}], granted_pending}]`), `pets_admin.grant_egg` (POST `/admin/pupile/przyznaj`, JSON `{user_id}` → `{ok, granted_pending}`).

- [ ] **Step 1: Testy (RED)** — `tests/test_pets_admin.py`:

```python
"""Panel /admin/pupile (spec §5): role, zapis ustawień z walidacją, statystyki, przyznanie jajka."""
import json

from tests.pets_helpers import zaloz_profil, zaloz_pupila


def _admin(make_user, login):
    u = make_user(role='admin', profile_completed=True)
    login(u)
    return u


def test_role_required(client, login, make_user):
    login(make_user(role='client', profile_completed=True))
    assert client.get('/admin/pupile').status_code in (302, 403)
    assert client.post('/admin/pupile/ustawienia', data={}).status_code in (302, 403)


def test_index_renderuje_formularz_i_statystyki(client, login, make_user, db):
    _admin(make_user, login)
    r = client.get('/admin/pupile')
    html = r.data.decode()
    assert r.status_code == 200
    for pole in ('pets_enabled', 'pets_rollout_pct', 'pets_decay_hours_hunger', 'pets_night_start', 'pets_actions_feed'):
        assert f'name="{pole}"' in html
    assert 'Profile' in html and 'css/pages/admin/pets.css' in html and 'js/pages/admin/pets.js' in html


def test_zapis_ustawien_poprawny(client, login, make_user, db):
    from modules.auth.models import Settings
    from modules.pets.config import PetConfig, feature_flags, reset_feature_cache
    admin = _admin(make_user, login)
    dane = {'pets_enabled': 'on', 'pets_rollout_pct': '25', 'pets_decay_hours_hunger': '20',
            'pets_decay_hours_fun': '30', 'pets_decay_hours_clean': '48', 'pets_night_start': '22',
            'pets_night_end': '7', 'pets_night_factor': '0.25', 'pets_health_drop_hours': '72',
            'pets_health_regen_hours': '24', 'pets_egg_hours': '168', 'pets_start_egg_hours': '48',
            'pets_boost_hours': '8', 'pets_boost_factor': '2', 'pets_monthly_days': '30',
            'pets_rescue_hours': '0', 'pets_rescue_reminder_days': '7', 'pets_pity_after': '2',
            'pets_max_stars': '5', 'pets_stage_days_child': '24', 'pets_stage_days_adult': '80',
            'pets_actions_feed': '50', 'pets_actions_play': '50', 'pets_actions_heal': '40',
            'pets_actions_heal_cooldown_h': '12', 'pets_actions_allow_below': '80',
            'pets_actions_pat_gain': '0.25', 'pets_actions_pat_per_hour': '60',
            'pets_actions_wake_penalty': '10', 'pets_actions_awake_minutes': '20'}
    r = client.post('/admin/pupile/ustawienia', data=dane, follow_redirects=False)
    assert r.status_code == 302
    reset_feature_cache()
    assert feature_flags() == (True, 25)
    cfg = PetConfig.load(force=True)
    assert cfg.decay_hours['hunger'] == 20 and cfg.night['start'] == 22
    assert Settings.query.filter_by(key='pets_decay_hours').one().updated_by == admin.id
    from modules.auth.models import ActivityLog
    assert ActivityLog.query.filter_by(action='pets_settings_updated').count() == 1


def test_ustawienia_bledne_pole_nic_nie_zapisuje(client, login, make_user, db):
    """Review Focus 3: jedno złe pole = zero zapisów."""
    from modules.auth.models import Settings
    _admin(make_user, login)
    dane = {'pets_enabled': 'on', 'pets_rollout_pct': '150', 'pets_decay_hours_hunger': '24'}
    r = client.post('/admin/pupile/ustawienia', data=dane)
    assert r.status_code == 400 and 'pets_rollout_pct' in r.data.decode()
    assert Settings.query.filter(Settings.key.like('pets_%')).count() == 0


def test_szukaj_i_przyznaj_jajko(client, login, make_user, db):
    from modules.auth.models import ActivityLog
    _admin(make_user, login)
    gracz = make_user(email='gracz@example.com', first_name='Ola')
    zaloz_profil(gracz)
    zaloz_pupila(gracz, name='Mruczek')
    r = client.get('/admin/pupile/szukaj?q=gracz')
    wynik = r.get_json()
    assert r.status_code == 200 and wynik[0]['email'] == 'gracz@example.com' and wynik[0]['pets'][0]['name'] == 'Mruczek'
    r = client.post('/admin/pupile/przyznaj', json={'user_id': gracz.id})
    assert r.status_code == 200 and r.get_json() == {'ok': True, 'granted_pending': 1}
    assert ActivityLog.query.filter_by(action='pet_egg_granted', entity_id=gracz.id).count() == 1


def test_przyznaj_bez_profilu_czytelny_blad(client, login, make_user, db):
    """Review Focus 4: użytkownik bez startowego jajka."""
    _admin(make_user, login)
    nowy = make_user()
    r = client.post('/admin/pupile/przyznaj', json={'user_id': nowy.id})
    assert r.status_code == 409 and 'startowego' in r.get_json()['message']
```

Jeśli model logu aktywności nazywa się inaczej niż `ActivityLog` lub leży gdzie indziej — `grep -rn "class ActivityLog" modules/` i popraw import w teście (nie w kodzie).

- [ ] **Step 2: RED** → Expected: 404 na `/admin/pupile` (brak tras).

- [ ] **Step 3: `config.py::validate_settings(form)`** — mapa pól formularza → klucze Settings: pola płaskie 1:1 (`pets_rollout_pct` → `pets_rollout_pct`), pola json rozbite `pets_<klucz>_<pole>` → składane w dict i `json.dumps`; `pets_enabled` = checkbox (`'on'`/brak → `'true'`/`'false'`). Walidacja: int ≥ 1 (lub ≥ 0 dla `_ZERO_OK`), `pct ≤ 100`, `night.factor` w `(0, 1]`, `boost.factor ≥ 1`, `pat_gain > 0`, `start/end` w `0..23`. Zwraca `(values, errors)`; `values` = `{klucz: (string, typ)}`.

- [ ] **Step 4: `admin_routes.py`** — `index` (formularz z wartościami z `PetConfig.load(force=True)`, statystyki z pomocniczej `admin_stats(now)`: profile, żywi per gatunek (`group_by Pet.species`), jajka w inkubacji (`status='egg'`), do odebrania (suma `granted_eggs_pending` + profile z należnym miesięcznym + zmarli bez `rescue_egg_claimed_at`), odejścia 7/30 dni (zdarzenia `die`), aktywni opiekunowie dziś/7 dni (`CARE_ACTIONS`), rozkład stadiów (`rules.stage`), komplety (użytkownicy z 8 distinct `species` w alive/dead/merged), odsetek właścicieli z pushem), `save_settings` (walidacja → przy błędach `render_template(..., errors=..., form=request.form), 400`; przy sukcesie pętla `Settings.set_value(key, value, updated_by=current_user.id, type=typ)` + `reset_feature_cache()` + `log_activity(user=current_user, action='pets_settings_updated', entity_type='settings', entity_id=None, new_value=json.dumps(zmienione))` + `flash` + redirect), `search_users` (`User.query.filter(or_(User.email.ilike(f'%{q}%'), User.first_name.ilike(...), User.last_name.ilike(...))).limit(20)`; pupile przez `state_for_user(user, lite=True)` → `pets` z `name`, `species_name`, `mood`, `stage`), `grant_egg` (`PetError` → JSON ze statusem; brak profilu → `PetError('no_profile', 'Użytkownik nie odebrał jeszcze startowego jajka.', 409)` — `lock_profile(user)` bez profilu rzuca `PetError`? sprawdź w `common.py`; jeśli rzuca inny kod, zmapuj na ten komunikat; potem `log_activity(user=current_user, action='pet_egg_granted', entity_type='user', entity_id=user.id)`).

- [ ] **Step 5: szablon + CSS + JS** — `index.html` rozszerza `admin/base_admin.html`, klasy `ca-page`, `ca-table-card` (skopiuj potrzebne reguły do `pets.css` zamiast linkować `contests.css`); sekcje: Włącznik i rollout (z ostrzeżeniem o auto-deployu? nie — to Settings, działa od razu), Liczby gry (grupy pól wg tabeli §3.4), Statystyki (kafelki), Użytkownik (pole szukania → tabela wyników → przycisk „Przyznaj jajko” z `data-user-id`, delegacja zdarzeń, `fetch` z CSRF z meta, `window.showToast`). Dark mode dla kart/tabel/pól.

- [ ] **Step 6: sidebar** — pozycja po Konkursach w tym samym bloku `{% if current_user.role in ('admin', 'mod') %}`.

- [ ] **Step 7: GREEN** — `venv/bin/python -m pytest tests/test_pets_admin.py tests/test_pets_config.py -q -p no:cacheprovider` → passed. Podgląd: `preview_start {name: "pets-preview"}` → zaloguj admina (`/dev-login-admin` — dopisz do skryptu podglądu trasę logującą `admin@example.com`) → `/admin/pupile`: zapis, błąd walidacji przy polu, szukaj, przyznaj; light/dark; 375 px.

- [ ] **Step 8: Commit** — `feat(pupile): panel /admin/pupile - ustawienia, statystyki, przyznawanie jajek`.

---

### Task 4: GA4, krok toura, dokumentacja wdrożenia

**Files:**
- Modify: `static/js/pages/client/pets.js` (po udanej akcji: `if (typeof window.trackEvent === 'function') window.trackEvent('pet_action', {action: action, mood: pet.mood});` oraz po wykluciu `trackEvent('pet_hatch', {result: 'new'|'dupe'})`), `static/js/components/onboarding-tour.js` (krok `pets` po `badges`: `attachTo: {element: '#petsWidget', on: 'top'}`, tytuł „Twój pupil”, tekst „Zaopiekuj się nim codziennie — karm, baw, myj. W nocy śpi.”, `skipWhen: function() { return !document.querySelector('#petsWidget'); }`; dopisz `pets` do odpowiedniej sekcji w `sections`, jeśli tour grupuje kroki), `docs/GOOGLE_ANALYTICS.md` (dwa nowe zdarzenia — plik lokalny, gitignored)
- Create: `docs/superpowers/plans/2026-10-11-pupile-wdrozenie-checklista.md` (force-add) — kolejność z §7: deploy z flagą `false`/`0` → na serwerze `flask achievements seed`, crontab `10 * * * *` dla `pets tick` (plik `2026-10-11-pupile-cron-instrukcja.md`), sprawdzenie `flask achievements check-daily` w crontabie, `flask pets tick --dry-run`, `flask pets report --days 7` → w panelu: `pets_enabled=true`, `pets_rollout_pct=10` → po tygodniu 50 → 100; ikony odznak kategorii `pets` przez panel odznak; popup ogłoszenia (decyzja Konrada); rollback = `pets_enabled=false` (cron milczy, strona 404, dane zostają).

- [ ] **Step 1:** Zmiany JS + test szablonu nie są potrzebne (brak runnera) — weryfikacja: w podglądzie `window.trackEvent = function(n, p) { console.log('GA', n, p); }` przed akcją → wpis w konsoli; tour: `localStorage.removeItem` klucza toura / przycisk „Przewodnik” na dashboardzie → krok „Twój pupil” pojawia się przy widgecie i jest pomijany, gdy widgetu brak (flaga off).
- [ ] **Step 2:** Checklista i wpisy w `docs/` (bez danych infrastruktury).
- [ ] **Step 3: Commit** — `feat(pupile): zdarzenia GA4, krok toura, checklista wdrozenia`.

---

### Task 5 (centrala): integracja, pełna suita, recenzja całej gałęzi, raport dla Konrada

- [ ] **Step 1:** `CACHE_VERSION` +1 (zmienione `pets.js`, `onboarding-tour.js`), pełna suita do pliku (`--deselect` znanego DST), `git status` czysty poza `.claude/launch.json`.
- [ ] **Step 2:** Recenzja świeżym Opusem **całej gałęzi `feat/pupile` od `main`** (etapy 1–6, ~60 commitów) z pakietem `review-package` i wskazaniem Review Focus z planów 4–6 oraz rulingów z ledgerów; fix pass Critical/Important (TDD), Minor do ledgera.
- [ ] **Step 3:** Pamięć (`project_pupile_tamagotchi.md`: stan „gotowe lokalnie, niepushowane”, lista odroczonych minorów wszystkich etapów), ClickUp (komentarz + opis), ledger etapu 6.
- [ ] **Step 4:** Raport końcowy dla Konrada zaczynający się od „Sprawdź i zobacz swoje jajko”: jak uruchomić podgląd lokalny (XAMPP nie wstaje → skrypt SQLite + `/dev-login`), co przeklikać, rulingi per etap, odroczone minory, checklista przed deployem, informacja, że nic nie zostało wypchnięte.
