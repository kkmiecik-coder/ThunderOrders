"""Etap 5: widget na dashboardzie i towarzysz — kontekst SSR, gating flagą, celebracja po endpointcie."""
import json

from tests.pets_helpers import zaloz_profil, zaloz_pupila
from tests.test_pets_routes import _wlacz


def _stan_widgetu(html):
    import re
    from html import unescape
    m = re.search(r'id="petsWidget"[^>]*data-state=\'([^\']*)\'', html)
    assert m, 'brak #petsWidget z data-state'
    return json.loads(unescape(m.group(1)))


def test_most_in_need_pet_id_w_stanie(db, make_user):
    from modules.pets.service import state_for_user
    user = make_user()
    zaloz_profil(user)
    szczesliwy = zaloz_pupila(user, species='kotek')
    glodny = zaloz_pupila(user, species='mis', name='Głodek', hunger=20.0)
    _wlacz(db)
    stan = state_for_user(user)
    assert stan['most_in_need_pet_id'] == glodny.id and glodny.id != szczesliwy.id


def test_most_in_need_none_bez_zywych(db, make_user):
    from modules.pets.service import state_for_user
    user = make_user()
    _wlacz(db)
    assert state_for_user(user)['most_in_need_pet_id'] is None


def test_dashboard_widget_tylko_z_flaga(client, login, make_user, db):
    user = make_user(profile_completed=True)
    login(user)
    r = client.get('/client/dashboard')
    assert r.status_code == 200 and b'id="petsWidget"' not in r.data and b'id="petCompanion"' not in r.data
    _wlacz(db)
    r = client.get('/client/dashboard')
    html = r.data.decode()
    assert r.status_code == 200 and 'id="petsWidget"' in html and 'id="petCompanion"' in html
    stan = _stan_widgetu(html)
    assert stan['eggs_available'] == [{'source': 'start'}] and stan['pets'] == [] and stan['most_in_need_pet_id'] is None
    assert 'js/pet/pets-core.js' in html and 'js/components/pet-card.js' in html and 'js/pages/client/pets-widget.js' in html
    assert 'data-mode="walk"' in html and 'data-user-id="%d"' % user.id in html


def test_dashboard_widget_z_pupilem(client, login, make_user, db):
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    pet = zaloz_pupila(user, species='kroliczek', name='Puszek', fun=10.0)
    html = client.get('/client/dashboard').data.decode()
    stan = _stan_widgetu(html)
    assert stan['most_in_need_pet_id'] == pet.id and stan['pets'][0]['name'] == 'Puszek'


def test_towarzysz_gosc_na_stronie_oferty_nic_nie_widzi(client, db, strona_sprzedazy):
    # Osobny test (świeża aplikacja): w jednym teście żądanie gościa i późniejsze `login` tego samego
    # procesu dzielą stan uwierzytelnienia (quirk środowiska testowego), więc nie mieszamy ich.
    _wlacz(db)
    r = client.get(f'/offer/{strona_sprzedazy.token}/thank-you')
    assert r.status_code == 200 and b'id="petCompanion"' not in r.data


def test_towarzysz_na_stronie_oferty_siedzi_i_celebruje(client, login, make_user, db, strona_sprzedazy):
    strona = strona_sprzedazy
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    html = client.get(f'/offer/{strona.token}/thank-you').data.decode()
    assert 'id="petCompanion"' in html and 'data-mode="sit"' in html and 'data-celebrate="1"' in html
    assert 'js/pet/pets-core.js' in html and 'js/components/pet-companion.js' in html


def test_towarzysz_bez_celebrate_na_zwyklej_stronie(client, login, make_user, db):
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    html = client.get('/client/dashboard').data.decode()
    assert 'data-celebrate="0"' in html


def test_pet_companion_css_ladowany_na_stronie_bez_super(app, client, login, make_user, db):
    """Recenzja etapu 4 (paczka A): 11 szablonów nadpisuje extra_css bez super() — link musi być poza blokiem."""
    from flask import url_for
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    with app.test_request_context():
        url = url_for('orders.client_list')
    html = client.get(url).data.decode()
    assert 'css/components/pet-companion.css' in html and 'id="petCompanion"' in html
