"""Wspólne klocki serwisu pupili.

- czas (`now`), konfiguracja (`cfg`) i losowość (`rng`) są wstrzykiwalne — testy nie
  monkeypatchują get_local_now;
- `lock_profile()` = mutex użytkownika (FOR UPDATE na pet_profiles): każda operacja zapisu
  zaczyna się od niego, zanim przeczyta żywe gatunki / dostępne jajka (spec §6);
- MariaDB (REPEATABLE READ) robi snapshot przy pierwszym SELECT w żądaniu — Flask-Login
  wczytuje usera PRZED naszą blokadą. Dlatego odczyty PO blokadzie (profil, pupil, żywe
  gatunki, suma pat pat) też są blokujące (FOR UPDATE) i nadpisują identity map
  (populate_existing). Kolejność blokad zawsze profil → pupil (persist_death też);
- odczyt nie zapisuje; jedyny wyjątek to `persist_death()` warunkowym UPDATE (spec §3.1);
- serializacja do słowników API wg spec §3.5 — etap 4 tylko je zwraca.
"""
import random
from datetime import timedelta

from flask import current_app
from sqlalchemy import update

from extensions import db
from modules.auth.models import get_local_now
from modules.pets import rules
from modules.pets.config import PetConfig
from modules.pets.errors import PetError
from modules.pets.models import Pet, PetEvent, PetProfile

CARE_ACTIONS = ('feed', 'play', 'wash', 'pat')
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


def profile_lock_query(user_id):
    """SELECT … FOR UPDATE + populate_existing: świeży wiersz mimo snapshotu REPEATABLE READ."""
    return PetProfile.query.filter_by(user_id=user_id).populate_existing().with_for_update()


def pet_lock_query(pet_id):
    return Pet.query.filter_by(id=pet_id).populate_existing().with_for_update()


def alive_pets_lock_query(user_id):
    return Pet.query.filter_by(user_id=user_id, status='alive').populate_existing().with_for_update()


def lock_profile(user, required=True):
    """Blokada wiersza profilu na czas transakcji (na SQLite no-op)."""
    profil = profile_lock_query(user.id).one_or_none()
    if profil is None and required:
        raise PetError('no_profile', 'Najpierw odbierz jajko startowe.', 409)
    return profil


def own_pet(user, pet_id, statuses):
    pet = pet_lock_query(pet_id).one_or_none() if pet_id is not None else None
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


def auto_discharge_at(pet, cfg):
    if pet.hospital_since is None or pet.hospital_healed_at is None:
        return None
    return pet.hospital_healed_at + timedelta(hours=float(cfg.hospital['wait_hours']))


def simulate_pet(pet, now, cfg):
    """Stan „na teraz”. W szpitalu: odcinek szpitalny do auto-wypisu, potem zwykła symulacja (spec v3 §4.4)."""
    if pet.hospital_since is None:
        return rules.simulate(state_of(pet), cfg, pet.state_at, now)
    # Wypis nie wcześniej niż zapisany stan: po obniżeniu wait_hours (checkpoint admina zapisał stan
    # później niż nowy wyliczony wypis) albo cofnięciu zegara odcinek [wypis, state_at] nie może liczyć
    # się drugi raz zwykłym spadkiem (recenzja „Świat”, Important 1).
    koniec = max(auto_discharge_at(pet, cfg), pet.state_at)
    do = min(now, koniec)
    stan = rules.hospital_state(state_of(pet), cfg, pet.state_at, do, pet.hospital_healed_at)
    if now <= koniec:
        return rules.SimResult(stan, None)
    dalej = rules.simulate(stan, cfg, koniec, now)
    return rules.SimResult(dalej.state, dalej.died_at, discharged_at=koniec)


def persist_discharge(pet, sim, now, manual=False):
    """Wypis ze szpitala warunkowym UPDATE (jak persist_death): dwa równoległe wypisy = jedno zdarzenie.

    Zapisuje stan `sim.state` na `now`. Zdarzenie `discharge` ma created_at = chwila wypisu
    (auto: `sim.discharged_at`, ręczny: `now`) i value 1 = ręczny, 0 = automatyczny. Wołający commituje.
    """
    od_kiedy = pet.hospital_since
    if od_kiedy is None:
        return False
    stan = sim.state
    # Kolejność blokad profil → pupil, jak w persist_death — wypis bywa zapisywany z odczytu (state_for_user)
    profile_lock_query(pet.user_id).one_or_none()
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


def apply_state(pet, state, now):
    pet.hunger, pet.fun, pet.clean, pet.health = state.hunger, state.fun, state.clean, state.health
    pet.state_at = now


def checkpoint_alive_pets(now, cfg):
    """Domyka stan WSZYSTKICH żywych pupili do `now` bieżącą konfiguracją (recenzja końcowa, Important 5).

    Symulacja liczy od `state_at` konfiguracją obowiązującą w chwili odczytu, więc obniżenie tempa w panelu
    działałoby wstecz (pupil nieobecnego od 2 dni odchodziłby natychmiast). Wołane PRZED zapisem nowych liczb,
    pod blokadami per użytkownik (profil → pupile), commit per użytkownik. Zwraca liczbę przeliczonych pupili.
    """
    from modules.auth.models import User
    ids = [r[0] for r in db.session.query(Pet.user_id).filter(Pet.status == 'alive').distinct().all()]
    n = 0
    for uid in ids:
        user = db.session.get(User, uid)
        if user is None or lock_profile(user, required=False) is None:
            continue
        for pet in alive_pets_lock_query(uid).all():
            sim = simulate_pet(pet, now, cfg)
            if sim.discharged_at is not None:
                persist_discharge(pet, sim, now)
            if sim.died_at is not None:
                persist_death(pet, sim, now)
            elif sim.discharged_at is None:
                apply_state(pet, sim.state, now)     # w szpitalu: hospital_healed_at zostaje (Review Focus 4)
            n += 1
        db.session.commit()
    return n


def persist_death(pet, sim, now):
    """Zapis odejścia warunkowym UPDATE — dwa równoległe odczyty zrobią jedno zdarzenie.

    Zwraca True, gdy to to wywołanie przestawiło status (i dopisało `die` + wyzerowało
    towarzysza). Wołający robi commit.
    """
    stan = sim.state
    przyczyna = next((DEATH_CAUSE[bar] for bar in rules.BARS if getattr(stan, bar) <= 0), 0)
    # Kolejność blokad profil → pupil, jak w perform_action — inaczej odczyt wykrywający
    # odejście i równoległa akcja mogą się zakleszczyć (MariaDB 1213).
    profile_lock_query(pet.user_id).one_or_none()
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
    istnieje = PetEvent.query.filter_by(pet_id=pet.id, type='milestone', value=code).with_for_update().first()
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
        'skin': int(pet.egg_skin or 0),
    }


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


def pet_dict(pet, state, now, cfg, discharged=False):
    """`discharged=True` = pupil już w domku (odczyt `lite` z wyliczonym, niezapisanym wypisem)."""
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
