"""Jajka: odbiór z czterech źródeł, ogrzewanie, wyklucie (spec §2.2–2.3).

Każda funkcja zapisu zaczyna się od lock_profile() — mutex użytkownika. Odbiór
startowego tworzy profil (jedyne miejsce, gdzie profil powstaje).
"""
from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from extensions import db
from modules.pets import rules
from modules.pets.common import (
    MILESTONE_FIRST_STAR, achievements_after_commit, add_event, add_milestone, alive_pets_lock_query,
    apply_state, cfg_or, egg_progress, lock_profile, next_monthly_at, now_or, own_pet, persist_death,
    rng_or, simulate_pet,
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
        try:
            db.session.flush()
        except IntegrityError:
            # Dwa równoległe odbiory startowego: oba widziały brak profilu, drugi INSERT łamie UNIQUE(user_id)
            db.session.rollback()
            raise PetError('start_claimed', 'Jajko startowe już odebrane.', 409)
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


def hatch_egg(user, pet_id, now=None, cfg=None, rng=None):
    """Wyklucie: losowanie gatunku, duplikat → gwiazdka, gwarancja po `pity_after` duplikatach."""
    now, cfg, rng = now_or(now), cfg_or(cfg), rng_or(rng)
    profil = lock_profile(user)
    jajko = own_pet(user, pet_id, ('egg',))
    if not rules.egg_is_ready(egg_progress(jajko, now, cfg), jajko.egg_hours):
        raise PetError('egg_not_ready', 'Jajko jeszcze się nie wykluło.', 409)

    # Stan żywych liczony na teraz pod blokadą (spec §3.1): kto odszedł, nie jest już żywy
    # (zapisujemy odejście), a gwiazdka ma działać od chwili wyklucia, nie wstecz od state_at.
    zywe = {}
    for zywy in alive_pets_lock_query(user.id).all():
        sim = simulate_pet(zywy, now, cfg)
        if sim.died_at is not None:
            persist_death(zywy, sim, now)
            continue
        zywe[zywy.species] = (zywy, sim.state)
    kandydaci = list(SPECIES_SLUGS)
    if profil.dupes_in_row >= int(cfg.pity_after):
        brakujace = [slug for slug in SPECIES_SLUGS if slug not in zywe]
        if brakujace:
            kandydaci = brakujace
    wybrany = rng.choice(kandydaci)

    if wybrany in zywe:
        istniejacy, stan_teraz = zywe[wybrany]
        apply_state(istniejacy, stan_teraz, now)
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
