"""state_for_user — stan dla API (spec §3.5).

Odczyt nie zapisuje; jedyny wyjątek: wyliczone odejście (persist_death) — pomijany w trybie
`lite` (towarzysz na stronach, cache w przeglądarce), który też nie buduje albumu.
"""
from dataclasses import replace

from extensions import db
from modules.pets import rules
from modules.pets.common import (
    cfg_or, egg_dict, eggs_available, get_profile, iso, memorial_dict, next_monthly_at,
    now_or, persist_death, persist_discharge, pet_dict, simulate_pet,
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
            if sim.discharged_at is not None and not lite:
                if persist_discharge(pet, sim, now):
                    zapisano_odejscie = True          # ta sama flaga: commit + refresh profilu
            if sim.died_at is None:
                zywe.append(pet_dict(pet, sim.state, now, cfg, discharged=sim.discharged_at is not None))
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
        # Liczby z konfiguracji do tekstów UI (etap 6): „potrzeby rosną N× wolniej”, „tempo ×N”, kara za obudzenie
        'config': {
            'night_factor': float(cfg.night['factor']),
            'boost_factor': float(cfg.boost['factor']) if not float(cfg.boost['factor']).is_integer() else int(cfg.boost['factor']),
            'boost_hours': int(cfg.boost['hours']),
            'wake_penalty': int(cfg.actions['wake_penalty']),
            'awake_minutes': int(cfg.actions['awake_minutes']),
            'hospital_hours': int(cfg.hospital['hours']),
        },
    }
    if not lite:
        stan['album'] = _album(zywe, zmarle, now)

    poza_szpitalem = [p for p in zywe if p['hospital'] is None]   # spec v3 §4.1: szpital nie towarzyszy
    auto = most_in_need(poza_szpitalem)
    stan['most_in_need_pet_id'] = auto['id'] if auto else None   # widget dashboardu i towarzysz (etap 5)
    wybrany = None
    if profil is not None and profil.companion_pet_id is not None:
        wybrany = next((p for p in poza_szpitalem if p['id'] == profil.companion_pet_id), None)
    stan['companion'] = {
        'enabled': bool(profil.companion_enabled) if profil is not None else True,
        'pet_id': (wybrany or auto or {}).get('id'),
        'auto': wybrany is None,
        # Żarty (spec v3.2 §6.8): przełącznik użytkownika ∧ wyłącznik admina — klient dostaje jedną liczbę
        'jokes': (bool(profil.jokes_enabled) if profil is not None else True) and bool(cfg.jokes_enabled),
    }
    stan['needs_care'] = (
        any(min(p['bars']['hunger'], p['bars']['fun'], p['bars']['clean']) < rules.HUNGRY_BELOW for p in poza_szpitalem)
        or any(p['mood'] in ('chory', 'krytyczny') for p in poza_szpitalem)
        or any(p['hospital']['ready'] for p in zywe if p['hospital'])     # wyleczony czeka na odbiór
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
