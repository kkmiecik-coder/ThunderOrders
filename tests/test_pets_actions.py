"""Akcje opieki (spec §2.5), dni opieki + seria logowań, kamienie milowe, odejście przy akcji."""
from datetime import date, timedelta

import pytest

from tests.pets_helpers import T0, NOC, zaloz_profil, zaloz_pupila, zaloz_zmarlego


def _cfg():
    from modules.pets.config import PetConfig
    return PetConfig()


def _akcja(user, pet, akcja, now=T0, **kw):
    from modules.pets.actions import perform_action
    return perform_action(user, pet.id, akcja, now=now, cfg=_cfg(), **kw)


# --- karmienie / zabawa / mycie ---

def test_nakarm_plus_50_i_zasada_80(db, make_user):
    from modules.pets.errors import PetError
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=20.0)
    wynik = _akcja(user, pet, 'feed', now=T0 + timedelta(hours=1))
    # 20 − 4.17 (godzina spadku) + 50 = 65.83
    assert abs(pet.hunger - 65.83) < 0.05 and pet.state_at == T0 + timedelta(hours=1)
    assert wynik['accepted'] == 1
    _akcja(user, pet, 'feed', now=T0 + timedelta(hours=1))      # 65.8 ≤ 80 → druga miseczka
    assert pet.hunger == 100.0
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'feed', now=T0 + timedelta(hours=1))  # 100 > 80 → najedzony
    assert (e.value.code, e.value.status, e.value.message) == ('not_available', 409, 'najedzony')


def test_dwie_miseczki_z_zera(db, make_user):
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0, health=90.0)
    _akcja(user, pet, 'feed')
    assert pet.hunger == 50.0
    _akcja(user, pet, 'feed')
    assert pet.hunger == 100.0


def test_zabawa_i_mycie(db, make_user):
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, fun=30.0, clean=10.0)
    _akcja(user, pet, 'play')
    assert pet.fun == 80.0
    _akcja(user, pet, 'wash')
    assert pet.clean == 100.0


# --- leczenie ---

def test_wylecz_plus_40_co_12h_tylko_chory(db, make_user):
    from modules.pets.errors import PetError
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0, health=50.0)
    _akcja(user, pet, 'heal')
    assert pet.health == 90.0 and pet.last_heal_at == T0
    pet.health = 50.0
    db.session.commit()
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'heal', now=T0 + timedelta(hours=11))
    assert e.value.message == 'lek już podany'
    pet.health = 60.0
    pet.state_at = T0 + timedelta(hours=12)
    db.session.commit()
    _akcja(user, pet, 'heal', now=T0 + timedelta(hours=12))
    assert pet.health == 100.0
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'heal', now=T0 + timedelta(hours=25))
    assert e.value.message == 'zdrowy'


# --- pat pat ---

def test_pat_pat_paczki_limit_60_na_godzine(db, make_user):
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, fun=50.0)
    w1 = _akcja(user, pet, 'pat', count=40)
    assert w1['accepted'] == 40 and pet.fun == 60.0
    w2 = _akcja(user, pet, 'pat', now=T0 + timedelta(minutes=10), count=50)
    assert w2['accepted'] == 20   # limit 60/h
    w3 = _akcja(user, pet, 'pat', now=T0 + timedelta(minutes=20), count=5)
    assert w3['accepted'] == 0    # animacja tak, przyrost nie
    assert PetEvent.query.filter_by(pet_id=pet.id, type='pat').count() == 2   # 0 nie loguje
    w4 = _akcja(user, pet, 'pat', now=T0 + timedelta(hours=1, minutes=1), count=10)
    assert w4['accepted'] == 10   # okno godziny minęło


@pytest.mark.parametrize('count,oczekiwane', [(0, 1), (-3, 1), (10 ** 9, 50), ('abc', 1), (None, 1), ('7', 7)])
def test_pat_count_przyciety_bez_wyjatku(db, make_user, count, oczekiwane):
    """Review Focus 1."""
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, fun=10.0)
    assert _akcja(user, pet, 'pat', count=count)['accepted'] == oczekiwane


# --- noc / obudź ---

def test_we_snie_brak_akcji_poza_obudz(db, make_user):
    from modules.pets.errors import PetError
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=60.0, now=NOC)
    for akcja in ('feed', 'play', 'wash', 'pat'):
        with pytest.raises(PetError) as e:
            _akcja(user, pet, akcja, now=NOC)
        assert e.value.message == 'śpi'


def test_obudz_kara_okno_20_min_i_przedluzanie(db, make_user):
    from modules.pets.errors import PetError
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=60.0, fun=50.0, clean=30.0, now=NOC)
    _akcja(user, pet, 'wake', now=NOC)
    assert pet.fun == 40.0 and pet.clean == 20.0 and pet.hunger == 60.0
    assert pet.awake_until == NOC + timedelta(minutes=20)
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'wake', now=NOC + timedelta(minutes=1))
    assert e.value.message == 'nie śpi'
    _akcja(user, pet, 'feed', now=NOC + timedelta(minutes=15))
    assert pet.awake_until == NOC + timedelta(minutes=35)
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'feed', now=NOC + timedelta(minutes=36))
    assert e.value.message == 'śpi'


def test_obudz_nie_zbija_ponizej_1(db, make_user):
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=60.0, fun=4.0, clean=100.0, now=NOC)
    _akcja(user, pet, 'wake', now=NOC)
    assert pet.fun == 1.0 and pet.clean == 90.0


def test_glodny_w_nocy_nie_spi_wiec_mozna_karmic(db, make_user):
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=20.0, now=NOC)
    _akcja(user, pet, 'feed', now=NOC)
    assert pet.hunger == 70.0 and pet.awake_until is None


# --- dni opieki, seria logowań, kamienie milowe ---

def test_dni_opieki_raz_dziennie_i_login_streak(db, make_user, monkeypatch):
    """update_login_streak() liczy po PRAWDZIWYM zegarze (nie przyjmuje now), więc kontrakt
    „wołane dokładnie przy pierwszej opiece dnia" sprawdzamy atrapą liczącą wywołania."""
    from modules.auth.models import User
    wywolania = []
    monkeypatch.setattr(User, 'update_login_streak', lambda self: wywolania.append(1))
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=10.0)
    w = _akcja(user, pet, 'feed')
    assert w['first_care_today'] is True and pet.care_days == 1 and pet.last_care_date == date(2026, 10, 12)
    assert len(wywolania) == 1
    w = _akcja(user, pet, 'feed', now=T0 + timedelta(hours=2))
    assert w['first_care_today'] is False and pet.care_days == 1 and len(wywolania) == 1
    _akcja(user, pet, 'wash', now=T0 + timedelta(days=1, hours=1))
    assert pet.care_days == 2 and len(wywolania) == 2


def test_login_streak_naprawde_rosnie_przy_pierwszej_opiece(db, make_user):
    from modules.auth.models import get_local_now
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=10.0)
    assert (user.login_streak or 0) == 0
    _akcja(user, pet, 'feed')
    assert user.login_streak == 1 and user.last_login_date == get_local_now().date()


def test_obudz_i_pat_zero_nie_licza_dnia_opieki(db, make_user):
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=60.0, now=NOC)
    _akcja(user, pet, 'wake', now=NOC)
    assert pet.care_days == 0
    pet2 = zaloz_pupila(user, species='mis', fun=100.0)
    _akcja(user, pet2, 'pat', count=60)
    assert pet2.care_days == 1
    pet3 = zaloz_pupila(user, species='kroliczek', fun=100.0)
    _akcja(user, pet3, 'pat', count=60)
    _akcja(user, pet3, 'pat', count=5, now=T0 + timedelta(minutes=1))   # 0 zaliczonych
    assert pet3.care_days == 1


def test_kamienie_milowe_dni_opieki_i_stadium(db, make_user):
    from modules.pets.models import PetEvent
    from modules.pets.common import MILESTONE_STAGE
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=20.0, care_days=6, last_care_date=date(2026, 10, 11),
                       hatched_at=T0 - timedelta(days=23, hours=20))
    _akcja(user, pet, 'feed', now=T0 + timedelta(hours=1))   # 7. dzień; 23 d 21 h → nadal maluch
    assert PetEvent.query.filter_by(pet_id=pet.id, type='milestone', value=7).count() == 1
    assert PetEvent.query.filter_by(pet_id=pet.id, type='milestone', value=MILESTONE_STAGE['dziecko']).count() == 0
    _akcja(user, pet, 'feed', now=T0 + timedelta(hours=5))   # 24 d 1 h → dziecko (sytość 49 ≤ 80, karmienie dostępne)
    assert PetEvent.query.filter_by(pet_id=pet.id, type='milestone', value=MILESTONE_STAGE['dziecko']).count() == 1
    _akcja(user, pet, 'pat', now=T0 + timedelta(hours=9), count=1)   # bez duplikatu (pat zawsze dostępny)
    assert PetEvent.query.filter_by(pet_id=pet.id, type='milestone').count() == 2


# --- odejście ---

def test_akcja_na_odeszlym_zapisuje_odejscie_410(db, make_user):
    """Review Focus 5."""
    from modules.pets.errors import PetError
    from modules.pets.models import PetEvent
    user = make_user()
    profil = zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0)
    profil.companion_pet_id = pet.id
    db.session.commit()
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'feed', now=T0 + timedelta(hours=80))
    assert e.value.code == 'pet_gone' and e.value.status == 410 and e.value.message.startswith('Pupil ') and 'odszedł do gwiazd' in e.value.message
    assert pet.status == 'dead' and pet.died_at == T0 + timedelta(hours=72) and pet.notify_level == 4
    assert profil.companion_pet_id is None
    assert PetEvent.query.filter_by(pet_id=pet.id, type='die').count() == 1
    with pytest.raises(PetError) as e:
        _akcja(user, pet, 'feed', now=T0 + timedelta(hours=81))
    assert e.value.code == 'wrong_status'
    assert PetEvent.query.filter_by(pet_id=pet.id, type='die').count() == 1


def test_cudzy_pupil_403_nieznana_akcja_400(db, make_user):
    from modules.pets.errors import PetError
    a, b = make_user(), make_user()
    zaloz_profil(a)
    zaloz_profil(b)
    pet = zaloz_pupila(a)
    with pytest.raises(PetError) as e:
        _akcja(b, pet, 'feed')
    assert e.value.status == 403
    with pytest.raises(PetError) as e:
        _akcja(a, pet, 'tickle')
    assert e.value.code == 'bad_action' and e.value.status == 400


# --- światełko ---

def test_swiatelko_raz_na_dobe_tylko_odeszly(db, make_user):
    from modules.pets.actions import light_candle
    from modules.pets.errors import PetError
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user)
    zmarly = zaloz_zmarlego(user, died_at=T0 - timedelta(days=1))
    light_candle(user, zmarly.id, now=T0)
    assert zmarly.lights_count == 1 and zmarly.last_light_date == date(2026, 10, 12)
    with pytest.raises(PetError) as e:
        light_candle(user, zmarly.id, now=T0 + timedelta(hours=5))
    assert e.value.code == 'already_lit'
    light_candle(user, zmarly.id, now=T0 + timedelta(days=1))
    assert zmarly.lights_count == 2
    assert PetEvent.query.filter_by(pet_id=zmarly.id, type='light').count() == 2
    zywy = zaloz_pupila(user)
    with pytest.raises(PetError) as e:
        light_candle(user, zywy.id, now=T0)
    assert e.value.code == 'wrong_status'


# --- imię ---

@pytest.mark.parametrize('surowe,oczekiwane', [
    ('Mruczek', 'Mruczek'), ('  Puszek  Mały ', 'Puszek Mały'), ('🐱 Kot', '🐱 Kot'), ('a' * 20, 'a' * 20),
    ('tab\there', 'tab here'),   # białe znaki (także tabulator) zbijane do pojedynczej spacji
])
def test_validate_name_ok(surowe, oczekiwane):
    from modules.pets.actions import validate_name
    assert validate_name(surowe) == oczekiwane


@pytest.mark.parametrize('zle', ['', '   ', 'a' * 21, None, 'Zły\x00znak'])
def test_validate_name_odrzuca(zle):
    from modules.pets.actions import validate_name
    from modules.pets.errors import PetError
    with pytest.raises(PetError) as e:
        validate_name(zle)
    assert e.value.code == 'bad_name'


def test_rename_zapisuje_i_loguje(db, make_user):
    from modules.pets.actions import rename_pet
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user)
    rename_pet(user, pet.id, '  Mruczuś ', now=T0)
    assert pet.name == 'Mruczuś'
    assert PetEvent.query.filter_by(pet_id=pet.id, type='rename').count() == 1


# --- towarzysz ---

def test_set_companion(db, make_user):
    from modules.pets.actions import set_companion
    from modules.pets.errors import PetError
    user = make_user()
    profil = zaloz_profil(user)
    pet = zaloz_pupila(user)
    set_companion(user, pet_id=pet.id, enabled=True)
    assert profil.companion_pet_id == pet.id and profil.companion_enabled is True
    set_companion(user, pet_id=None, enabled=False)
    assert profil.companion_pet_id is None and profil.companion_enabled is False
    zmarly = zaloz_zmarlego(user)
    with pytest.raises(PetError) as e:
        set_companion(user, pet_id=zmarly.id)
    assert e.value.code == 'wrong_status'


def test_set_companion_bez_profilu_409(db, make_user):
    from modules.pets.actions import set_companion
    from modules.pets.errors import PetError
    user = make_user()
    with pytest.raises(PetError) as e:
        set_companion(user, pet_id=None, enabled=False)
    assert e.value.code == 'no_profile'


# --- przyznanie jajka ---

def test_admin_grant_egg(db, make_user):
    from modules.pets.actions import admin_grant_egg
    from modules.pets.errors import PetError
    from modules.pets.models import PetEvent
    user = make_user()
    with pytest.raises(PetError) as e:
        admin_grant_egg(user, now=T0)
    assert e.value.code == 'no_profile'
    profil = zaloz_profil(user)
    admin_grant_egg(user, now=T0)
    admin_grant_egg(user, now=T0)
    assert profil.granted_eggs_pending == 2
    assert PetEvent.query.filter_by(user_id=user.id, type='grant', pet_id=None).count() == 2


# --- recenzja ---

@pytest.mark.parametrize('count,oczekiwane', [
    (float('inf'), 1), (float('-inf'), 1), (float('nan'), 1), (1e309, 1), (2.0 ** 70, 50),
])
def test_pat_count_nieskonczony_lub_ogromny_float(db, make_user, count, oczekiwane):
    """Review Focus 1 uzupełniony po recenzji: json.loads('Infinity'/'1e309') daje inf → nie 500."""
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, fun=10.0)
    assert _akcja(user, pet, 'pat', count=count)['accepted'] == oczekiwane


def test_limit_pat_liczony_blokujacym_odczytem(db, make_user):
    """Recenzja (Important 2): SUM zdarzeń pat po blokadzie profilu musi omijać snapshot RR."""
    from sqlalchemy.dialects import mysql
    from modules.pets.actions import pats_last_hour_query
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user)
    sql = str(pats_last_hour_query(pet, T0).statement.compile(dialect=mysql.dialect()))
    assert 'FOR UPDATE' in sql and 'sum(' in sql.lower(), sql
