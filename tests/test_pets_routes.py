"""Trasy pupili: bramka funkcji (404), strona, API i mapowanie błędów na JSON (spec §3.5, §6)."""
import json
from datetime import timedelta

import pytest
from flask import url_for

from tests.pets_helpers import zaloz_profil, zaloz_pupila, zaloz_zmarlego, zaloz_jajko


def _wlacz(db, pct=100):
    from modules.auth.models import Settings
    from modules.pets.config import reset_feature_cache
    Settings.set_value('pets_enabled', 'true', type='boolean')
    Settings.set_value('pets_rollout_pct', pct, type='integer')
    # Trasy liczą na zegarze ściennym (now nie da się wstrzyknąć przez HTTP) — bez tego
    # między 23 a 7 pupil śpi i akcje dają 409 'śpi'. start == end = brak nocy (rules.is_night).
    Settings.set_value('pets_night', json.dumps({'start': 0, 'end': 0}), type='json')
    db.session.commit()
    reset_feature_cache()


def _teraz():
    from modules.auth.models import get_local_now
    return get_local_now()


@pytest.fixture
def gracz(db, make_user, login):
    """Zalogowany klient z włączoną funkcją; bez profilu (startowe jajko wirtualne)."""
    user = make_user()
    login(user)
    _wlacz(db)
    return user


# --- bramka ---

def test_flaga_wylaczona_strona_i_api_404(client, login, make_user):
    user = make_user()
    login(user)
    r = client.get('/client/pupile')
    # strona: szablon 404 aplikacji, nie goła strona Werkzeuga (errorhandler blueprintu z `return e`)
    assert r.status_code == 404 and '404 - Nie znaleziono strony' in r.data.decode()
    r = client.get('/client/pupile/api/stan')
    assert r.status_code == 404 and r.get_json()['error'] == 'not_found'


def test_rollout_po_user_id(client, login, make_user, db):
    user = make_user()
    login(user)
    _wlacz(db, pct=0)
    assert client.get('/client/pupile').status_code == 404
    _wlacz(db, pct=100)
    assert client.get('/client/pupile').status_code == 200


def test_niezalogowany_przekierowanie(client, db):
    r = client.get('/client/pupile')
    assert r.status_code == 302 and '/auth/login' in r.headers['Location']


def test_nawigacja_pokazuje_pupile_tylko_z_flaga(app, client, login, make_user, db):
    user = make_user(profile_completed=True)
    login(user)
    with app.test_request_context():
        link = url_for('pets.home').encode()
    r = client.get('/client/dashboard')
    assert r.status_code == 200 and link not in r.data
    _wlacz(db)
    r = client.get('/client/dashboard')
    assert r.status_code == 200 and link in r.data
    assert b'petsNavDot' in r.data and b'paw.svg' in r.data


# --- strona ---

def test_strona_szkielet_z_data_state(client, gracz):
    r = client.get('/client/pupile')
    assert r.status_code == 200
    html = r.data.decode()
    assert 'id="petsApp"' in html and 'data-state=' in html and 'data-species=' in html
    assert 'data-api="/client/pupile/api"' in html
    assert 'css/pages/client/pets.css' in html and 'js/pages/client/pets.js' in html
    assert 'js/pet/species.js' in html and 'js/components/pet-rig.js' in html and 'js/components/pet-card.js' in html
    assert html.index('js/pet/pets-core.js') < html.index('js/components/pet-card.js')   # core przed kartą (etap 5)
    assert 'css/layouts/client-layout.css' in html     # {{ super() }} w extra_css


def test_strona_bez_profile_completed_dziala(client, db, make_user, login):
    """Review Focus 1: bramka profilu z client_bp nie obejmuje pets_bp — i tak ma działać."""
    user = make_user(profile_completed=False, first_name=None, last_name=None)
    login(user)
    _wlacz(db)
    assert client.get('/client/pupile').status_code == 200


# --- API: stan i jajka ---

def test_api_stan_ksztalt(client, gracz):
    r = client.get('/client/pupile/api/stan')
    assert r.status_code == 200
    s = r.get_json()
    assert s['ok'] is True
    for klucz in ('now', 'night', 'eggs_available', 'next_monthly_at', 'eggs', 'pets', 'album', 'companion', 'needs_care'):
        assert klucz in s, klucz
    assert s['eggs_available'] == [{'source': 'start'}] and len(s['album']) == 8


def test_api_stan_lite_bez_albumu(client, gracz):
    s = client.get('/client/pupile/api/stan?lite=1').get_json()
    assert s['ok'] is True and 'album' not in s


def test_odbierz_startowe_ogrzej_wykluj_imie(client, gracz, db, monkeypatch):
    from modules.pets import eggs as eggs_mod
    from modules.pets.models import Pet
    from tests.pets_helpers import RngStaly
    r = client.post('/client/pupile/api/jajka/odbierz', json={'source': 'start'})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    jajko = Pet.query.filter_by(user_id=gracz.id).one()
    assert jajko.status == 'egg' and jajko.egg_hours == 48
    r = client.post(f'/client/pupile/api/jajka/{jajko.id}/ogrzej', json={})
    assert r.status_code == 200 and r.get_json()['state']['eggs'][0]['can_warm'] is False
    r = client.post(f'/client/pupile/api/jajka/{jajko.id}/ogrzej', json={})
    assert r.status_code == 409 and r.get_json() == {'ok': False, 'error': 'boost_active',
                                                     'message': 'Jajko jest już ogrzane — poczekaj, aż ciepło się skończy.'}
    r = client.post(f'/client/pupile/api/jajka/{jajko.id}/wykluj', json={})
    assert r.status_code == 409 and r.get_json()['error'] == 'egg_not_ready'
    jajko.egg_progress_sec = 48 * 3600
    db.session.commit()
    monkeypatch.setattr(eggs_mod, 'rng_or', lambda rng: RngStaly('mis'))
    r = client.post(f'/client/pupile/api/jajka/{jajko.id}/wykluj', json={})
    dane = r.get_json()
    assert r.status_code == 200 and dane['result'] == 'new' and dane['species'] == 'mis'
    assert dane['species_name'] == 'Miś' and dane['pet_id'] == jajko.id and dane['starred_pet_id'] is None
    assert dane['new_achievements'] == [] and dane['state']['pets'][0]['name'] == 'Miś'
    r = client.post(f'/client/pupile/api/{jajko.id}/imie', json={'name': '  Puchatek '})
    assert r.status_code == 200 and r.get_json()['name'] == 'Puchatek'


def test_imie_zle_400_z_komunikatem(client, gracz, db):
    """Review Focus 4."""
    zaloz_profil(gracz)
    pet = zaloz_pupila(gracz, now=_teraz())
    r = client.post(f'/client/pupile/api/{pet.id}/imie', json={'name': 'a' * 21})
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_name'
    assert 'od 1 do 20' in r.get_json()['message']
    assert client.post(f'/client/pupile/api/{pet.id}/imie', json={'name': '🐱 Kot'}).status_code == 200


# --- API: akcje ---

def test_akcja_nakarm_i_drugi_klik_409(client, gracz, db):
    """Review Focus 3."""
    zaloz_profil(gracz)
    pet = zaloz_pupila(gracz, hunger=20.0, now=_teraz() - timedelta(minutes=1))
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'feed'})
    assert r.status_code == 200
    dane = r.get_json()
    assert dane['ok'] is True and dane['accepted'] == 1 and dane['first_care_today'] is True
    assert dane['state']['pets'][0]['bars']['hunger'] >= 69.9
    client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'feed'})      # druga miseczka → 100
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'feed'})
    assert r.status_code == 409 and r.get_json()['error'] == 'not_available' and r.get_json()['message'] == 'najedzony'


def test_akcja_pat_z_count_i_bez(client, gracz, db):
    zaloz_profil(gracz)
    pet = zaloz_pupila(gracz, fun=10.0, now=_teraz() - timedelta(minutes=1))
    assert client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'pat', 'count': 7}).get_json()['accepted'] == 7
    assert client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'pat'}).get_json()['accepted'] == 1
    assert client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'pat', 'count': 'abc'}).get_json()['accepted'] == 1


def test_akcja_na_cudzym_403_nieznana_400_nieistniejacy_404(client, gracz, db, make_user):
    zaloz_profil(gracz)
    inny = make_user()
    zaloz_profil(inny)
    cudzy = zaloz_pupila(inny, now=_teraz())
    r = client.post(f'/client/pupile/api/{cudzy.id}/akcja', json={'action': 'feed'})
    assert r.status_code == 403 and r.get_json()['error'] == 'forbidden'
    pet = zaloz_pupila(gracz, now=_teraz())
    assert client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'tickle'}).status_code == 400
    assert client.post('/client/pupile/api/999999/akcja', json={'action': 'feed'}).status_code == 404
    r = client.post('/client/pupile/api/abc/akcja', json={'action': 'feed'})
    assert r.status_code == 404 and r.get_json()['error'] == 'not_found'   # zły segment ścieżki pod /api/
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', data='nie-json', content_type='text/plain')
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_request'


def test_akcja_na_odeszlym_410(client, gracz, db):
    zaloz_profil(gracz)
    pet = zaloz_pupila(gracz, hunger=0.0, now=_teraz() - timedelta(hours=80))
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'feed'})
    assert r.status_code == 410 and r.get_json()['error'] == 'pet_gone'
    assert 'odszedł do gwiazd' in r.get_json()['message']


def test_swiatelko_i_towarzysz(client, gracz, db):
    profil = zaloz_profil(gracz)
    zywy = zaloz_pupila(gracz, now=_teraz())
    zmarly = zaloz_zmarlego(gracz, died_at=_teraz() - timedelta(days=1))
    r = client.post(f'/client/pupile/api/{zmarly.id}/swiatelko', json={})
    assert r.status_code == 200 and r.get_json()['lights_count'] == 1
    assert client.post(f'/client/pupile/api/{zmarly.id}/swiatelko', json={}).status_code == 409
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': zywy.id, 'enabled': False})
    assert r.status_code == 200 and r.get_json()['state']['companion'] == {'enabled': False, 'pet_id': zywy.id, 'auto': False}
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': 'x', 'enabled': True})
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_request'


def test_ratunkowe_wymaga_pet_id_int(client, gracz, db):
    zaloz_profil(gracz)
    zmarly = zaloz_zmarlego(gracz, died_at=_teraz() - timedelta(hours=1))
    assert client.post('/client/pupile/api/jajka/odbierz', json={'source': 'rescue', 'pet_id': [1]}).status_code == 400
    r = client.post('/client/pupile/api/jajka/odbierz', json={'source': 'rescue', 'pet_id': str(zmarly.id)})
    assert r.status_code == 200


def test_limiter_120_na_minute_per_uzytkownik(app, client, gracz, db, monkeypatch):
    """Precedens: tests/test_mobile_api_auth.py::test_rate_limit_returns_envelope_for_mobile_api.

    RATELIMIT_ENABLED w TestingConfig jest False, więc create_app() nie dał limiterowi ani storage,
    ani hooków na tej instancji aplikacji — samo `limiter.enabled = True` nie wystarcza (i zależy
    od kolejności testów). Re-init z włączonymi limitami; storage w pamięci, nie lokalny Redis.
    """
    from extensions import limiter
    monkeypatch.setitem(app.config, 'RATELIMIT_ENABLED', True)
    monkeypatch.setitem(app.config, 'RATELIMIT_STORAGE_URI', 'memory://')
    limiter.init_app(app)
    try:
        limiter.reset()
        zaloz_profil(gracz)
        pet = zaloz_pupila(gracz, fun=0.0, now=_teraz())
        kody = [client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'pat'}).status_code for _ in range(121)]
        assert kody[:120] == [200] * 120 and kody[120] == 429
        r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'pat'})
        assert r.get_json()['error'] == 'rate_limited'
    finally:
        limiter.reset()
        limiter.enabled = False


def test_lite_nie_zapisuje_odejscia_pelny_zapisuje(client, gracz, db):
    zaloz_profil(gracz)
    pet = zaloz_pupila(gracz, hunger=0.0, now=_teraz() - timedelta(hours=80))
    client.get('/client/pupile/api/stan?lite=1')
    db.session.expire_all()
    assert pet.status == 'alive'
    client.get('/client/pupile/api/stan')
    db.session.expire_all()
    assert pet.status == 'dead'
