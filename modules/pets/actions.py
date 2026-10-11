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
