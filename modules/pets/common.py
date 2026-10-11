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
from sqlalchemy import update

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
