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


def test_szablon_swiata_linkuje_sceny(client, login, make_user, db):
    """Task 7: jeden szablon ładuje wszystkie sceny świata, pokój, nakładkę wyklucia i router (na końcu)."""
    login(make_user(profile_completed=True))
    _wlacz(db)
    html = client.get('/client/pupile/domek').data.decode()
    pliki = ['js/pet/world/map.js', 'js/pet/world/room.js', 'js/pet/world/house.js', 'js/pet/world/hospital.js',
             'js/pet/world/workshop.js', 'js/pet/world/garden.js', 'js/components/pet-hatch.js']
    for plik in pliki:
        assert plik in html, plik
        assert html.index(plik) < html.index('js/pages/client/pets.js'), plik   # sceny rejestrują się przed routerem
    for css in ('css/components/pet-room.css', 'css/pages/client/pets-map.css', 'css/pages/client/pets-house.css',
                'css/pages/client/pets-hospital.css', 'css/pages/client/pets-workshop.css', 'css/pages/client/pets-garden.css'):
        assert css in html, css
    assert 'petHatchModal' not in html          # stary modal wyklucia zastąpiony nakładką PetHatch
    for scena in ('mapa', 'domek', 'szpital', 'warsztat', 'ogrod'):
        assert f'data-scene-view="{scena}"' in html, scena


def test_sale_szpitala_maja_adresy(client, login, make_user, db):
    """Spec v3.1 §4.1: hol ma dwie sale pod własnymi adresami; klucz sceny to nie adres."""
    login(make_user(profile_completed=True))
    _wlacz(db)
    for sciezka, scena in (('/szpital/inkubatorium', 'inkubatorium'), ('/szpital/izba-przyjec', 'izba')):
        r = client.get('/client/pupile' + sciezka)
        assert r.status_code == 200 and _scena(r.data.decode()) == scena, sciezka
    assert client.get('/client/pupile/szpital/kostnica').status_code == 404
    assert client.get('/client/pupile/szpital/izba').status_code == 404


def test_sale_szpitala_za_flaga(client, login, make_user):
    login(make_user(profile_completed=True))
    assert client.get('/client/pupile/szpital/inkubatorium').status_code == 404
    assert client.get('/client/pupile/szpital/izba-przyjec').status_code == 404
