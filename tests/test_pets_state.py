"""state_for_user — słownik stanu dla API (spec §3.5): bez zapisów poza odejściem; lite bez zapisów."""
from datetime import timedelta

from tests.pets_helpers import T0, NOC, zaloz_profil, zaloz_pupila, zaloz_zmarlego, zaloz_jajko


def _cfg():
    from modules.pets.config import PetConfig
    return PetConfig()


def test_bez_profilu_wirtualne_startowe_i_zero_zapisow(db, make_user):
    """Review Focus 4."""
    from modules.pets.state import state_for_user
    from modules.pets.models import PetProfile, Pet
    user = make_user()
    s = state_for_user(user, now=T0, cfg=_cfg())
    assert s['ok'] is True and s['now'] == '2026-10-12T08:00:00'
    assert s['night'] == {'start': 23, 'end': 7, 'is_night': False}
    assert s['eggs_available'] == [{'source': 'start'}] and s['next_monthly_at'] is None
    assert s['eggs'] == [] and s['pets'] == []
    assert all(k['status'] == 'unknown' for k in s['album']) and len(s['album']) == 8
    assert s['companion'] == {'enabled': True, 'pet_id': None, 'auto': True}
    assert s['needs_care'] is True
    assert PetProfile.query.count() == 0 and Pet.query.count() == 0


def test_pelny_stan_z_jajkiem_pupilem_i_pamiecia(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    profil = zaloz_profil(user, now=T0 - timedelta(days=10))
    jajko = zaloz_jajko(user, now=T0 - timedelta(hours=10), boost_until=T0 - timedelta(hours=2))
    pet = zaloz_pupila(user, species='kotek', hunger=70.0, stars=1)
    zmarly = zaloz_zmarlego(user, species='mis', died_at=T0 - timedelta(days=2), lights_count=1)
    profil.companion_pet_id = pet.id
    db.session.commit()
    s = state_for_user(user, now=T0, cfg=_cfg())
    assert s['next_monthly_at'] == '2026-11-01T08:00:00'   # profil z 2.10 + 30 dni
    assert [d['source'] for d in s['eggs_available']] == ['rescue']
    assert s['eggs'][0]['id'] == jajko.id and s['eggs'][0]['progress_pct'] == round(100 * 18 / 168, 1)
    p = s['pets'][0]
    assert p['id'] == pet.id and p['bars']['hunger'] == 70.0 and p['mood'] == 'szczesliwy' and p['stars'] == 1
    album = {a['species']: a for a in s['album']}
    assert album['kotek'] == {'species': 'kotek', 'status': 'alive', 'pet_id': pet.id}
    assert album['mis']['status'] == 'memorial' and album['mis']['lights_count'] == 1 and album['mis']['can_light'] is True
    assert album['wiewiorka'] == {'species': 'wiewiorka', 'status': 'unknown'}
    assert s['companion'] == {'enabled': True, 'pet_id': pet.id, 'auto': False}
    assert s['needs_care'] is True   # jajko ratunkowe do odebrania


def test_needs_care_false_gdy_wszystko_dobrze(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    zaloz_profil(user, now=T0)
    zaloz_pupila(user)
    s = state_for_user(user, now=T0 + timedelta(hours=1), cfg=_cfg())
    assert s['needs_care'] is False and s['eggs_available'] == []


def test_needs_care_true_gdy_pasek_ponizej_30_lub_chory_lub_jajko_gotowe(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    zaloz_profil(user, now=T0)
    pet = zaloz_pupila(user, hunger=29.0)
    assert state_for_user(user, now=T0, cfg=_cfg())['needs_care'] is True
    pet.hunger = 100.0
    pet.health = 70.0
    db.session.commit()
    assert state_for_user(user, now=T0, cfg=_cfg())['needs_care'] is True
    pet.health = 100.0
    db.session.commit()
    zaloz_jajko(user, now=T0, hours=48, egg_progress_sec=48 * 3600)
    assert state_for_user(user, now=T0, cfg=_cfg())['needs_care'] is True


def test_towarzysz_auto_najbardziej_potrzebujacy(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    zaloz_profil(user, now=T0)
    a = zaloz_pupila(user, species='kotek', hunger=90.0)
    b = zaloz_pupila(user, species='mis', clean=35.0)
    s = state_for_user(user, now=T0, cfg=_cfg())
    assert s['companion'] == {'enabled': True, 'pet_id': b.id, 'auto': True}


def test_towarzysz_wskazany_ale_odeszly_wraca_do_auto(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    profil = zaloz_profil(user, now=T0)
    zywy = zaloz_pupila(user, species='kotek')
    zmarly = zaloz_zmarlego(user, species='mis')
    profil.companion_pet_id = zmarly.id
    profil.companion_enabled = False
    db.session.commit()
    s = state_for_user(user, now=T0, cfg=_cfg())
    assert s['companion'] == {'enabled': False, 'pet_id': zywy.id, 'auto': True}


def test_odejscie_zapisane_przy_odczycie_i_nagrobek(db, make_user):
    from modules.pets.state import state_for_user
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user, now=T0)
    pet = zaloz_pupila(user, hunger=0.0)
    s = state_for_user(user, now=T0 + timedelta(hours=80), cfg=_cfg())
    assert s['pets'] == []
    assert pet.status == 'dead' and pet.died_at == T0 + timedelta(hours=72)
    album = {a['species']: a for a in s['album']}
    assert album['kotek']['status'] == 'memorial' and album['kotek']['pet_id'] == pet.id
    assert [d['source'] for d in s['eggs_available']] == ['rescue']
    assert PetEvent.query.filter_by(pet_id=pet.id, type='die').count() == 1


def test_lite_nie_zapisuje_odejscia_i_nie_ma_albumu(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    zaloz_profil(user, now=T0)
    pet = zaloz_pupila(user, hunger=0.0)
    s = state_for_user(user, lite=True, now=T0 + timedelta(hours=80), cfg=_cfg())
    assert 'album' not in s
    assert pet.status == 'alive'
    assert s['pets'][0]['bars']['health'] == 0.0 and s['pets'][0]['mood'] == 'krytyczny'
    assert s['needs_care'] is True


def test_noc_w_stanie(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    zaloz_profil(user, now=T0)
    zaloz_pupila(user, now=NOC)
    s = state_for_user(user, now=NOC, cfg=_cfg())
    assert s['night']['is_night'] is True and s['pets'][0]['asleep'] is True and s['pets'][0]['can']['wake'] is True


def test_most_in_need_pusty(db):
    from modules.pets.state import most_in_need
    assert most_in_need([]) is None


def test_stan_ma_config_dla_tekstow_ui(db, make_user):
    """Etap 6 (uwaga C): teksty UI („4× wolniej”, „10 punktów”, „×2”) mają czytać liczby z konfiguracji."""
    from modules.pets.config import PetConfig
    from modules.pets.state import state_for_user
    user = make_user()
    cfg = PetConfig(night={'start': 23, 'end': 7, 'factor': 0.5}, boost={'hours': 6, 'factor': 3},
                    actions={**PetConfig().actions, 'wake_penalty': 7, 'awake_minutes': 15})
    for lite in (False, True):
        stan = state_for_user(user, lite=lite, cfg=cfg)
        assert stan['config'] == {'night_factor': 0.5, 'boost_factor': 3, 'boost_hours': 6,
                                  'wake_penalty': 7, 'awake_minutes': 15}
