"""Żarty towarzysza: stan (profil ∧ wyłącznik admina), zapis przełącznika, lista obrazków (spec v3.2 §6.7–6.8)."""
import json

import pytest

from tests.pets_helpers import zaloz_profil, zaloz_pupila


def _wlacz(db):
    from modules.auth.models import Settings
    from modules.pets.config import reset_feature_cache
    Settings.set_value('pets_enabled', 'true', type='boolean')
    Settings.set_value('pets_rollout_pct', 100, type='integer')
    Settings.set_value('pets_night', json.dumps({'start': 0, 'end': 0}), type='json')
    db.session.commit()
    reset_feature_cache()


@pytest.fixture
def gracz(db, make_user, login):
    user = make_user()
    login(user)
    _wlacz(db)
    return user


def _jokes(user):
    from modules.pets.config import PetConfig
    from modules.pets.service import state_for_user
    return state_for_user(user, lite=True, cfg=PetConfig.load(force=True))['companion']['jokes']


def test_stan_bez_profilu_zarty_wlaczone(db, make_user):
    assert _jokes(make_user()) is True


def test_stan_zarty_wylaczone_w_profilu(db, make_user):
    user = make_user()
    zaloz_profil(user).jokes_enabled = False
    db.session.commit()
    assert _jokes(user) is False


def test_stan_zarty_wylaczone_przez_admina(db, make_user):
    from modules.auth.models import Settings
    user = make_user()
    zaloz_profil(user)
    Settings.set_value('pets_jokes_enabled', 'false', type='boolean')
    db.session.commit()
    assert _jokes(user) is False


def _companion(user):
    from modules.pets.config import PetConfig
    from modules.pets.service import state_for_user
    return state_for_user(user, lite=True, cfg=PetConfig.load(force=True))['companion']


def test_stan_wylacznik_admina_nie_zmienia_preferencji_uzytkownika(db, make_user):
    """Review końcowy #3: warsztat pokazuje preferencję użytkownika (jokes_pref), moduł żartów — flagę efektywną."""
    from modules.auth.models import Settings
    user = make_user()
    zaloz_profil(user)
    Settings.set_value('pets_jokes_enabled', 'false', type='boolean')
    db.session.commit()
    c = _companion(user)
    assert c['jokes'] is False and c['jokes_pref'] is True


def test_stan_preferencja_uzytkownika_wylaczona(db, make_user):
    user = make_user()
    zaloz_profil(user).jokes_enabled = False
    db.session.commit()
    c = _companion(user)
    assert c['jokes'] is False and c['jokes_pref'] is False


def test_stan_bez_profilu_preferencja_wlaczona(db, make_user):
    c = _companion(make_user())
    assert c['jokes'] is True and c['jokes_pref'] is True


def test_zapis_preferencji_przy_wylaczniku_admina(client, gracz, db):
    """Użytkownik może włączyć żarty mimo wyłącznika admina; po ponownym włączeniu przez admina działają od razu."""
    from modules.auth.models import Settings
    from modules.pets.models import PetProfile
    zaloz_profil(gracz)
    zywy = zaloz_pupila(gracz)
    Settings.set_value('pets_jokes_enabled', 'false', type='boolean')
    db.session.commit()
    from modules.pets.config import PetConfig
    PetConfig.load(force=True)
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': zywy.id, 'enabled': True, 'jokes': True})
    c = r.get_json()['state']['companion']
    assert r.status_code == 200 and c['jokes'] is False and c['jokes_pref'] is True
    assert PetProfile.query.filter_by(user_id=gracz.id).one().jokes_enabled is True


def test_set_companion_zarty(db, make_user):
    from modules.pets.actions import set_companion
    user = make_user()
    profil = zaloz_profil(user)
    set_companion(user, jokes=False)
    assert profil.jokes_enabled is False and profil.companion_enabled is True
    set_companion(user, enabled=False)          # jokes=None = bez zmiany
    assert profil.jokes_enabled is False and profil.companion_enabled is False
    set_companion(user, jokes=True)
    assert profil.jokes_enabled is True


def test_towarzysz_zapisuje_zarty(client, gracz, db):
    from modules.pets.models import PetProfile
    zaloz_profil(gracz)
    zywy = zaloz_pupila(gracz)
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': zywy.id, 'enabled': True, 'jokes': False})
    assert r.status_code == 200 and r.get_json()['state']['companion']['jokes'] is False
    assert PetProfile.query.filter_by(user_id=gracz.id).one().jokes_enabled is False
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': zywy.id, 'enabled': True, 'jokes': True})
    assert r.get_json()['state']['companion']['jokes'] is True


def test_towarzysz_bez_pola_jokes_nie_zmienia_ustawienia(client, gracz, db):
    """Review Focus 2: starszy front (bez `jokes`) nie może po cichu włączyć wyłączonych żartów."""
    from modules.pets.models import PetProfile
    profil = zaloz_profil(gracz)
    profil.jokes_enabled = False
    db.session.commit()
    zywy = zaloz_pupila(gracz)
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': zywy.id, 'enabled': True})
    assert r.status_code == 200
    assert PetProfile.query.filter_by(user_id=gracz.id).one().jokes_enabled is False


@pytest.mark.parametrize('zle', ['false', 0, 1, 'tak'])
def test_towarzysz_jokes_nie_bool_400(client, gracz, db, zle):
    zaloz_profil(gracz)
    zywy = zaloz_pupila(gracz)
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': zywy.id, 'enabled': True, 'jokes': zle})
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_request'


def test_wychylenia_tylko_aktywne_posortowane(client, gracz, db):
    from modules.pets.models import PetPeekImage
    db.session.add_all([PetPeekImage(filename='b.webp', is_active=True),
                        PetPeekImage(filename='x.webp', is_active=False),
                        PetPeekImage(filename='a.webp', is_active=True)])
    db.session.commit()
    r = client.get('/client/pupile/api/wychylenia')
    assert r.status_code == 200
    dane = r.get_json()
    assert dane['ok'] is True
    assert [o['url'] for o in dane['images']] == ['/static/uploads/pet_peeks/b.webp', '/static/uploads/pet_peeks/a.webp']
    assert all(isinstance(o['id'], int) for o in dane['images'])
    assert 'private' in r.headers['Cache-Control'] and 'max-age=300' in r.headers['Cache-Control']


def test_wychylenia_pusta_lista(client, gracz, db):
    assert client.get('/client/pupile/api/wychylenia').get_json() == {'ok': True, 'images': []}


def test_wychylenia_bramka_funkcji_404(client, login, make_user):
    login(make_user())
    r = client.get('/client/pupile/api/wychylenia')
    assert r.status_code == 404 and r.get_json()['error'] == 'not_found'


def test_wychylenia_wymagaja_logowania(client, db):
    assert client.get('/client/pupile/api/wychylenia').status_code == 302
