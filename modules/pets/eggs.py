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
