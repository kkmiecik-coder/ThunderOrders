"""Spec v3 §3.1, §4.5: adresy miejsc świata i API szpitala."""
import re

from tests.pets_helpers import zaloz_profil, zaloz_pupila
from tests.test_pets_routes import _wlacz


def _scena(html):
    return re.search(r'id="petsApp"[^>]*data-scene="([a-z]+)"', html).group(1)


def test_sceny_maja_adresy(client, login, make_user, db):
    login(make_user(profile_completed=True))
    _wlacz(db)
    for sciezka, scena in (('', 'mapa'), ('/domek', 'domek'), ('/szpital', 'szpital'),
                           ('/warsztat', 'warsztat'), ('/ogrod', 'ogrod')):
        r = client.get('/client/pupile' + sciezka)
        assert r.status_code == 200 and _scena(r.data.decode()) == scena, sciezka
    assert client.get('/client/pupile/strych').status_code == 404
    assert client.get('/client/pupile/api').status_code == 404


def test_sceny_za_flaga(client, login, make_user):
    login(make_user(profile_completed=True))
    assert client.get('/client/pupile/szpital').status_code == 404


def test_api_szpital_i_wypis(client, login, make_user, db):
    user = make_user()
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=20.0, health=50.0)
    r = client.post(f'/client/pupile/api/{pet.id}/szpital', json={})
    assert r.status_code == 200 and r.get_json()['state']['pets'][0]['hospital'] is not None
    r = client.post(f'/client/pupile/api/{pet.id}/szpital', json={})
    assert r.status_code == 409 and r.get_json()['error'] == 'in_hospital'
    r = client.post(f'/client/pupile/api/{pet.id}/wypis', json={})
    assert r.status_code == 200 and r.get_json()['state']['pets'][0]['hospital'] is None
    r = client.post(f'/client/pupile/api/{pet.id}/wypis', json={})
    assert r.status_code == 409 and r.get_json()['error'] == 'not_in_hospital'


def test_api_szpital_cudzy_i_zdrowy(client, login, make_user, db):
    wlasciciel = make_user()
    zaloz_profil(wlasciciel)
    cudzy = zaloz_pupila(wlasciciel, health=50.0)
    user = make_user()
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    zdrowy = zaloz_pupila(user, species='mis')
    assert client.post(f'/client/pupile/api/{cudzy.id}/szpital', json={}).status_code == 403
    r = client.post(f'/client/pupile/api/{zdrowy.id}/szpital', json={})
    assert r.status_code == 409 and r.get_json()['error'] == 'not_sick'


def test_api_akcja_z_wariantem(client, login, make_user, db):
    user = make_user()
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=20.0)
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'feed', 'variant': 'ciastko'})
    assert r.status_code == 200 and r.get_json()['variant'] == 'ciastko'
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'feed', 'variant': 7})
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_variant'
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'heal'})
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_action'
