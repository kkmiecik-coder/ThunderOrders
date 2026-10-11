"""Jajka: cztery źródła, odbiór, ogrzewanie, wyklucie z duplikatami i gwarancją (spec §2.2–2.3)."""
from datetime import timedelta

import pytest

from tests.pets_helpers import T0, zaloz_profil, zaloz_pupila, zaloz_zmarlego, zaloz_jajko, RngStaly


def _cfg():
    from modules.pets.config import PetConfig
    return PetConfig()


# --- odbiór ---

def test_startowe_tworzy_profil_i_jajko_48h(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.models import PetProfile, PetEvent
    user = make_user()
    jajko = claim_egg(user, 'start', now=T0, cfg=_cfg())
    profil = PetProfile.query.filter_by(user_id=user.id).one()
    assert profil.start_egg_claimed_at == T0 and profil.last_monthly_egg_at == T0
    assert jajko.status == 'egg' and jajko.egg_source == 'start' and jajko.egg_hours == 48
    assert jajko.egg_progress_sec == 0 and jajko.egg_progress_at == T0 and jajko.boost_until is None
    assert PetEvent.query.filter_by(pet_id=jajko.id, type='claim').count() == 1


def test_startowe_drugi_raz_409(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    claim_egg(user, 'start', now=T0, cfg=_cfg())
    with pytest.raises(PetError) as e:
        claim_egg(user, 'start', now=T0 + timedelta(days=1), cfg=_cfg())
    assert (e.value.code, e.value.status) == ('start_claimed', 409)


def test_miesieczne_tylko_po_30_dniach_od_odbioru_bez_kumulacji(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    profil = zaloz_profil(user, now=T0)
    with pytest.raises(PetError) as e:
        claim_egg(user, 'monthly', now=T0 + timedelta(days=29, hours=23), cfg=_cfg())
    assert e.value.code == 'monthly_not_ready'
    # odebrane po 45 dniach — licznik biegnie od ODBIORU, nie od dostępności
    jajko = claim_egg(user, 'monthly', now=T0 + timedelta(days=45), cfg=_cfg())
    assert jajko.egg_hours == 168 and profil.last_monthly_egg_at == T0 + timedelta(days=45)
    with pytest.raises(PetError):
        claim_egg(user, 'monthly', now=T0 + timedelta(days=60), cfg=_cfg())
    assert claim_egg(user, 'monthly', now=T0 + timedelta(days=75), cfg=_cfg()).status == 'egg'


def test_miesieczne_bez_profilu_409(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    with pytest.raises(PetError) as e:
        claim_egg(user, 'monthly', now=T0, cfg=_cfg())
    assert e.value.code == 'no_profile'


def test_ratunkowe_od_razu_jedno_na_odejscie(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    profil = zaloz_profil(user)
    zmarly = zaloz_zmarlego(user, died_at=T0 + timedelta(days=3))
    jajko = claim_egg(user, 'rescue', pet_id=zmarly.id, now=T0 + timedelta(days=3, minutes=1), cfg=_cfg())
    assert jajko.egg_source == 'rescue' and jajko.egg_hours == 168
    assert zmarly.rescue_egg_claimed_at == T0 + timedelta(days=3, minutes=1)
    assert profil.last_monthly_egg_at == T0   # nie rusza miesięcznego
    with pytest.raises(PetError) as e:
        claim_egg(user, 'rescue', pet_id=zmarly.id, now=T0 + timedelta(days=4), cfg=_cfg())
    assert e.value.code == 'rescue_claimed'


def test_ratunkowe_z_opoznieniem_gdy_rescue_hours_dodatnie(db, make_user):
    from modules.pets.config import PetConfig
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    cfg = PetConfig(rescue_hours=24)
    user = make_user()
    zaloz_profil(user)
    zmarly = zaloz_zmarlego(user, died_at=T0)
    with pytest.raises(PetError) as e:
        claim_egg(user, 'rescue', pet_id=zmarly.id, now=T0 + timedelta(hours=23), cfg=cfg)
    assert e.value.code == 'rescue_not_ready'
    assert claim_egg(user, 'rescue', pet_id=zmarly.id, now=T0 + timedelta(hours=24), cfg=cfg).status == 'egg'


def test_ratunkowe_za_cudzego_pupila_403(db, make_user):
    """Review Focus 2."""
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    a, b = make_user(), make_user()
    zaloz_profil(a)
    zaloz_profil(b)
    zmarly = zaloz_zmarlego(a, died_at=T0)
    with pytest.raises(PetError) as e:
        claim_egg(b, 'rescue', pet_id=zmarly.id, now=T0 + timedelta(hours=1), cfg=_cfg())
    assert (e.value.code, e.value.status) == ('forbidden', 403)
    assert zmarly.rescue_egg_claimed_at is None


def test_ratunkowe_bez_pet_id_400(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    zaloz_profil(user)
    with pytest.raises(PetError) as e:
        claim_egg(user, 'rescue', now=T0, cfg=_cfg())
    assert e.value.code == 'pet_required' and e.value.status == 400


def test_przyznane_zmniejsza_licznik(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    profil = zaloz_profil(user)
    profil.granted_eggs_pending = 1
    db.session.commit()
    jajko = claim_egg(user, 'granted', now=T0, cfg=_cfg())
    assert jajko.egg_source == 'granted' and profil.granted_eggs_pending == 0
    with pytest.raises(PetError) as e:
        claim_egg(user, 'granted', now=T0, cfg=_cfg())
    assert e.value.code == 'nothing_granted'


def test_nieznane_zrodlo_400(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.errors import PetError
    user = make_user()
    with pytest.raises(PetError) as e:
        claim_egg(user, 'zloty', now=T0, cfg=_cfg())
    assert e.value.code == 'bad_source'


def test_kilka_jajek_moze_inkubowac_sie_naraz(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.models import Pet
    user = make_user()
    profil = zaloz_profil(user, now=T0 - timedelta(days=31))
    profil.granted_eggs_pending = 1
    db.session.commit()
    claim_egg(user, 'monthly', now=T0, cfg=_cfg())
    claim_egg(user, 'granted', now=T0, cfg=_cfg())
    assert Pet.query.filter_by(user_id=user.id, status='egg').count() == 2


# --- ogrzewanie ---

def test_ogrzej_zapisuje_postep_i_boost_8h(db, make_user):
    from modules.pets.eggs import warm_egg
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user)
    jajko = zaloz_jajko(user, now=T0)
    warm_egg(user, jajko.id, now=T0 + timedelta(hours=2), cfg=_cfg())
    assert jajko.egg_progress_sec == 2 * 3600 and jajko.egg_progress_at == T0 + timedelta(hours=2)
    assert jajko.boost_until == T0 + timedelta(hours=10)
    assert PetEvent.query.filter_by(pet_id=jajko.id, type='warm').count() == 1


def test_ogrzej_drugi_raz_dopiero_po_wygasnieciu(db, make_user):
    from modules.pets.eggs import warm_egg
    from modules.pets.errors import PetError
    user = make_user()
    zaloz_profil(user)
    jajko = zaloz_jajko(user, now=T0)
    warm_egg(user, jajko.id, now=T0, cfg=_cfg())
    with pytest.raises(PetError) as e:
        warm_egg(user, jajko.id, now=T0 + timedelta(hours=7, minutes=59), cfg=_cfg())
    assert e.value.code == 'boost_active'
    warm_egg(user, jajko.id, now=T0 + timedelta(hours=8), cfg=_cfg())
    # 8 h ×2 zapisane w postępie, nowy boost od 8 h
    assert jajko.egg_progress_sec == 16 * 3600 and jajko.boost_until == T0 + timedelta(hours=16)


def test_ogrzej_tylko_jajko_i_tylko_swoje(db, make_user):
    from modules.pets.eggs import warm_egg
    from modules.pets.errors import PetError
    a, b = make_user(), make_user()
    zaloz_profil(a)
    zaloz_profil(b)
    pupil = zaloz_pupila(a)
    with pytest.raises(PetError) as e:
        warm_egg(a, pupil.id, now=T0, cfg=_cfg())
    assert e.value.code == 'wrong_status'
    jajko = zaloz_jajko(a)
    with pytest.raises(PetError) as e:
        warm_egg(b, jajko.id, now=T0, cfg=_cfg())
    assert e.value.status == 403
