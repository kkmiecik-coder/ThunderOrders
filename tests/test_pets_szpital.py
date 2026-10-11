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


# --- recenzja końcowa „Świat” (backend) ---

def test_zmiana_wait_hours_po_checkpoincie_nie_liczy_spadku_dwa_razy(db, make_user):
    """Important 1: obniżenie wait_hours po zapisie stanu (checkpoint admina) — odcinek po wypisie
    liczy się od state_at, nie od (wcześniejszego) wyliczonego wypisu."""
    from modules.pets import rules
    from modules.pets.actions import admit_pet
    from modules.pets.common import checkpoint_alive_pets, simulate_pet, state_of
    user = make_user(); zaloz_profil(user)
    pet = _chory(user)
    admit_pet(user, pet.id, now=T0, cfg=CFG)                          # healed T0+4h
    checkpoint_alive_pets(T0 + timedelta(hours=14), CFG)              # stan domknięty starą konfiguracją
    nowy = _cfg(hospital={'hours': 8, 'floor': 60, 'wait_hours': 2})  # wypis „byłby” w T0+6h
    sim = simulate_pet(pet, T0 + timedelta(hours=15), nowy)
    oczekiwane = rules.simulate(state_of(pet), nowy, pet.state_at, T0 + timedelta(hours=15))
    assert sim.discharged_at == pet.state_at == T0 + timedelta(hours=14)
    assert sim.state == oczekiwane.state and sim.died_at is None


def test_zmiana_wait_hours_do_zera_nie_zabija_wstecz(db, make_user):
    from modules.pets.actions import admit_pet
    from modules.pets.common import checkpoint_alive_pets, simulate_pet
    user = make_user(); zaloz_profil(user)
    pet = _chory(user)
    admit_pet(user, pet.id, now=T0, cfg=_cfg(hospital={'hours': 8, 'floor': 60, 'wait_hours': 168}))
    checkpoint_alive_pets(T0 + timedelta(hours=110), _cfg(hospital={'hours': 8, 'floor': 60, 'wait_hours': 168}))
    sim = simulate_pet(pet, T0 + timedelta(hours=111), _cfg(hospital={'hours': 8, 'floor': 60, 'wait_hours': 0}))
    assert sim.died_at is None and sim.discharged_at == T0 + timedelta(hours=110)


def test_persist_discharge_najpierw_blokuje_profil(db, make_user):
    """Important 2: kolejność blokad profil → pupil także przy wypisie z odczytu (bez mutexu)."""
    from sqlalchemy import event
    from modules.pets.actions import admit_pet
    from modules.pets.common import persist_discharge, simulate_pet
    user = make_user(); zaloz_profil(user)
    pet = _chory(user)
    admit_pet(user, pet.id, now=T0, cfg=CFG)
    sim = simulate_pet(pet, T0 + timedelta(hours=40), CFG)
    zapytania = []

    def zbieraj(conn, cursor, statement, parameters, context, executemany):
        zapytania.append(statement)

    event.listen(db.engine, 'before_cursor_execute', zbieraj)
    try:
        persist_discharge(pet, sim, T0 + timedelta(hours=40))
        db.session.commit()
    finally:
        event.remove(db.engine, 'before_cursor_execute', zbieraj)
    norm = [s.lstrip().upper() for s in zapytania]
    i_profil = next(i for i, s in enumerate(norm) if s.startswith('SELECT') and 'PET_PROFILES' in s)
    i_update = next(i for i, s in enumerate(norm) if s.startswith('UPDATE PETS'))
    assert i_profil < i_update, zapytania


def test_odbior_pupila_ktory_odszedl_po_wypisie_to_410(db, make_user):
    """Re-grade Minor 4 → Important: „wrócił już do domku” o pupilu, który odszedł, wprowadza w błąd."""
    from modules.pets.actions import admit_pet, discharge_pet
    from modules.pets.errors import PetError
    user = make_user(); zaloz_profil(user)
    pet = _chory(user)
    admit_pet(user, pet.id, now=T0, cfg=CFG)                          # wypis T0+28h, radość 0 → zdrowie spada
    with pytest.raises(PetError) as e:
        discharge_pet(user, pet.id, now=T0 + timedelta(hours=28 + 24 + 80), cfg=CFG)
    assert e.value.code == 'pet_gone' and e.value.status == 410
    assert pet.status == 'dead'
