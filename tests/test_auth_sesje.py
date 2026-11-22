"""Sesje webowe: dezaktywacja konta i zmiana/reset hasła kończą inne sesje.

Mechanizm: identyfikator w sesji i w ciasteczku „zapamiętaj mnie" to
`<id>:<odcisk hasła>`. Stare sesje (sam `<id>`, sprzed wdrożenia) działają dalej,
dopóki hasło nie zostanie zmienione — żeby wdrożenie nikogo nie wylogowało.
"""
from datetime import timedelta
from unittest.mock import patch

import pytest
from flask import current_app
from flask_login import current_user
from flask_login.utils import encode_cookie

from utils.timeutil import utcnow

HASLO = 'StareHaslo1'
NOWE_HASLO = 'NoweHaslo2'


@pytest.fixture
def whoami(app):
    """Testowy endpoint zwracający id zalogowanego użytkownika albo 'anon'."""
    def _whoami():
        return str(current_user.id) if current_user.is_authenticated else 'anon'
    app.add_url_rule('/_test/whoami', 'test_whoami', _whoami)
    return lambda c: c.get('/_test/whoami').get_data(as_text=True)


@pytest.fixture
def user_z_haslem(db, make_user):
    u = make_user(email='sesja@example.com', profile_completed=True)
    u.set_password(HASLO)
    db.session.commit()
    return u


def _zaloguj(c, email='sesja@example.com', haslo=HASLO, remember=False):
    data = {'email': email, 'password': haslo}
    if remember:
        data['remember_me'] = 'on'
    r = c.post('/auth/login', data=data, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200, r.get_data(as_text=True)


def _zmien_haslo_poza_sesja(db, user, haslo=NOWE_HASLO):
    """Zmiana hasła „z innego urządzenia" (np. reset w aplikacji mobilnej)."""
    user.set_password(haslo)
    db.session.commit()


def _cookie_remember():
    return current_app.config.get('REMEMBER_COOKIE_NAME', 'remember_token')


def _tylko_remember(c):
    """Symuluje zamknięcie przeglądarki: zostaje samo ciasteczko „zapamiętaj mnie"."""
    c.delete_cookie('session')


# ---------- dezaktywacja ----------

def test_dezaktywowany_uzytkownik_traci_sesje(app, db, client, login, make_user, whoami):
    u = make_user()
    login(u)
    assert whoami(client) == str(u.id)

    u.deactivate('test', None)
    db.session.commit()
    assert whoami(client) == 'anon'


def test_konto_w_trakcie_usuwania_traci_sesje(app, db, client, login, make_user, whoami):
    u = make_user()
    login(u)
    u.request_deletion()
    db.session.commit()
    assert whoami(client) == 'anon'


def test_dezaktywowany_traci_tez_remember_cookie(app, db, client, user_z_haslem, whoami):
    _zaloguj(client, remember=True)
    _tylko_remember(client)
    assert whoami(client) == str(user_z_haslem.id)

    user_z_haslem.deactivate('test', None)
    db.session.commit()
    _tylko_remember(client)
    assert whoami(client) == 'anon'


# ---------- zmiana hasła poza sesją ----------

def test_zmiana_hasla_konczy_sesje(app, db, client, user_z_haslem, whoami):
    _zaloguj(client)
    assert whoami(client) == str(user_z_haslem.id)

    _zmien_haslo_poza_sesja(db, user_z_haslem)
    assert whoami(client) == 'anon'


def test_zmiana_hasla_uniewaznia_remember_cookie(app, db, client, user_z_haslem, whoami):
    _zaloguj(client, remember=True)
    _tylko_remember(client)
    assert whoami(client) == str(user_z_haslem.id)

    _zmien_haslo_poza_sesja(db, user_z_haslem)
    _tylko_remember(client)
    assert whoami(client) == 'anon'


# ---------- stare sesje sprzed wdrożenia (grandfathering) ----------

def test_stara_sesja_bez_odcisku_dziala(app, db, client, login, user_z_haslem, whoami):
    login(user_z_haslem)  # sam '<id>' — format sprzed wdrożenia
    assert whoami(client) == str(user_z_haslem.id)


def test_stara_sesja_bez_odcisku_ginie_po_zmianie_hasla(app, db, client, login, user_z_haslem, whoami):
    login(user_z_haslem)
    _zmien_haslo_poza_sesja(db, user_z_haslem)
    assert whoami(client) == 'anon'


def test_stare_remember_cookie_dziala_i_ginie_po_zmianie_hasla(app, db, client, user_z_haslem, whoami):
    client.set_cookie(_cookie_remember(), encode_cookie(str(user_z_haslem.id)))
    assert whoami(client) == str(user_z_haslem.id)

    _zmien_haslo_poza_sesja(db, user_z_haslem)
    client.delete_cookie('session')
    client.set_cookie(_cookie_remember(), encode_cookie(str(user_z_haslem.id)))
    assert whoami(client) == 'anon'


def test_pierwsze_ustawienie_hasla_nie_kasuje_starych_sesji(app, db, client, login, make_user, whoami):
    """Konto bez hasła (np. OAuth) ustawiające hasło pierwszy raz — to nie jest zmiana."""
    u = make_user()
    login(u)
    u.set_password(HASLO)
    db.session.commit()
    assert whoami(client) == str(u.id)


# ---------- zmiana własnego hasła w profilu ----------

def test_zmiana_wlasnego_hasla_zostawia_biezaca_sesje_i_konczy_inne(app, db, user_z_haslem, whoami):
    ja = app.test_client()
    inne_urzadzenie = app.test_client()
    _zaloguj(ja)
    _zaloguj(inne_urzadzenie)

    r = ja.post('/profile/change-password', data={
        'current_password': HASLO, 'new_password': NOWE_HASLO, 'confirm_password': NOWE_HASLO,
    }, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200 and r.get_json()['success'] is True

    assert whoami(ja) == str(user_z_haslem.id)
    assert whoami(inne_urzadzenie) == 'anon'


def test_zmiana_wlasnego_hasla_odnawia_remember_cookie(app, db, user_z_haslem, whoami):
    ja = app.test_client()
    _zaloguj(ja, remember=True)

    r = ja.post('/profile/change-password', data={
        'current_password': HASLO, 'new_password': NOWE_HASLO, 'confirm_password': NOWE_HASLO,
    }, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200

    _tylko_remember(ja)
    assert whoami(ja) == str(user_z_haslem.id)


# ---------- reset hasła linkiem ----------

def test_reset_hasla_linkiem_konczy_sesje(app, db, user_z_haslem, whoami):
    zalogowany = app.test_client()
    _zaloguj(zalogowany, remember=True)

    token = user_z_haslem.generate_password_reset_token()
    db.session.commit()
    anonim = app.test_client()
    r = anonim.post(f'/auth/reset-password/{token}',
                    data={'password': NOWE_HASLO, 'password_confirm': NOWE_HASLO})
    assert r.status_code == 302

    assert whoami(zalogowany) == 'anon'
    _tylko_remember(zalogowany)
    assert whoami(zalogowany) == 'anon'


# ---------- zapomniałem hasła: cooldown i limit ----------

def test_ponowne_zapomnialem_haslo_w_cooldownie_nie_zmienia_tokenu(app, db, client, user_z_haslem):
    with patch('modules.auth.routes.EmailManager.send_password_reset') as wyslij:
        r1 = client.post('/auth/forgot-password', data={'email': 'sesja@example.com'})
        token1 = user_z_haslem.password_reset_token
        r2 = client.post('/auth/forgot-password', data={'email': 'sesja@example.com'})
    db.session.refresh(user_z_haslem)

    assert token1 is not None
    assert user_z_haslem.password_reset_token == token1  # pierwszy link dalej działa
    assert wyslij.call_count == 1
    assert r1.status_code == r2.status_code == 302
    assert r1.headers['Location'] == r2.headers['Location']


def test_zapomnialem_haslo_po_cooldownie_wysyla_nowy_link(app, db, client, user_z_haslem):
    with patch('modules.auth.routes.EmailManager.send_password_reset') as wyslij:
        client.post('/auth/forgot-password', data={'email': 'sesja@example.com'})
        token1 = user_z_haslem.password_reset_token
        user_z_haslem.password_reset_sent_at = utcnow() - timedelta(seconds=61)
        db.session.commit()
        client.post('/auth/forgot-password', data={'email': 'sesja@example.com'})
    db.session.refresh(user_z_haslem)

    assert user_z_haslem.password_reset_token != token1
    assert wyslij.call_count == 2


def test_zapomnialem_haslo_ta_sama_odpowiedz_dla_nieistniejacego_maila(app, db, client, user_z_haslem):
    with patch('modules.auth.routes.EmailManager.send_password_reset'):
        jest = client.post('/auth/forgot-password', data={'email': 'sesja@example.com'})
        nie_ma = client.post('/auth/forgot-password', data={'email': 'nikt@example.com'})
    assert jest.status_code == nie_ma.status_code == 302
    assert jest.headers['Location'] == nie_ma.headers['Location']


def test_zapomnialem_haslo_ma_limit_zadan(app, db):
    from extensions import limiter
    app.config['RATELIMIT_ENABLED'] = True
    app.config['RATELIMIT_STORAGE_URI'] = 'memory://'
    limiter.init_app(app)  # re-init z włączonymi limitami (domyślnie off w testach)
    c = app.test_client()
    with patch('modules.auth.routes.EmailManager.send_password_reset'):
        statusy = [c.post('/auth/forgot-password', data={'email': f'x{i}@example.com'}).status_code
                   for i in range(6)]
    assert statusy[:5] == [302] * 5
    assert statusy[5] == 429
    # GET formularza nie zużywa limitu
    assert c.get('/auth/forgot-password').status_code == 200
