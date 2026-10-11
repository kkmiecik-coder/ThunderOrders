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


def test_blokujace_odczyty_pod_mutexem_kompiluja_sie_z_for_update(db, make_user):
    """Recenzja (Important 2): MariaDB REPEATABLE READ robi snapshot przy pierwszym SELECT
    w żądaniu (Flask-Login wczytuje usera), więc odczyty PO blokadzie profilu muszą same być
    blokujące (FOR UPDATE) i nadpisywać identity map (populate_existing)."""
    from sqlalchemy.dialects import mysql
    from modules.pets.common import profile_lock_query, pet_lock_query, alive_pets_lock_query
    user = make_user()
    for q in (profile_lock_query(user.id), pet_lock_query(1), alive_pets_lock_query(user.id)):
        sql = str(q.statement.compile(dialect=mysql.dialect()))
        assert 'FOR UPDATE' in sql, sql
        assert q.load_options._populate_existing is True   # SA 2.0: flaga w load_options


def test_persist_death_najpierw_blokuje_profil(db, make_user):
    """Recenzja (deadlock): kolejność blokad profil → pupil wszędzie; persist_death z odczytu
    (bez mutexu) nie może brać pupila przed profilem."""
    from sqlalchemy import event
    from modules.pets.common import persist_death, simulate_pet
    from modules.pets.config import PetConfig
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0)
    sim = simulate_pet(pet, T0 + timedelta(hours=80), PetConfig())
    zapytania = []

    def zbieraj(conn, cursor, statement, parameters, context, executemany):
        zapytania.append(statement)

    event.listen(db.engine, 'before_cursor_execute', zbieraj)
    try:
        persist_death(pet, sim, T0 + timedelta(hours=80))
        db.session.commit()
    finally:
        event.remove(db.engine, 'before_cursor_execute', zbieraj)
    norm = [s.lstrip().upper() for s in zapytania]
    i_profil = next(i for i, s in enumerate(norm) if s.startswith('SELECT') and 'PET_PROFILES' in s)
    i_update = next(i for i, s in enumerate(norm) if s.startswith('UPDATE PETS'))
    assert i_profil < i_update, zapytania
