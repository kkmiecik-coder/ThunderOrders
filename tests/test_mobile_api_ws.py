"""
Testy Socket.IO dla aplikacji mobilnej (E9).

Część 1 (Task 2): autoryzacja połączenia `connect` przez JWT + wiązanie sid→user
(`_ws_users`) + czyszczenie przy disconnect. Handler jest PERMISYWNY — połączenia
bez tokenu (web/WMS/payment) są akceptowane; odrzucane są wyłącznie połączenia
z niepoprawnym JWT (śmieć/wygasły/refresh/blocklista/inactive).
"""

from datetime import timedelta

import pytest

from extensions import socketio


# Import odłożony do czasu wykonania testu — `modules.api_mobile` ładuje się poprawnie
# dopiero po `create_app` (fixture `app`); kolejność importów blueprintu rozwiązuje
# cykle, których import na poziomie modułu (przy collection) by nie rozwiązał.
def _bound_uids():
    from modules.api_mobile.ws import _ws_users
    return _ws_users.values()


@pytest.fixture(autouse=True)
def _ws_handlers(app):
    """Re-rejestracja handlerów Socket.IO na świeżym serwerze per-test.

    `app` jest function-scoped → każdy test woła `create_app` → `socketio.init_app`
    tworzy NOWY `socketio.server`. flask-socketio re-aplikuje tylko `self.handlers`
    (handlery zarejestrowane gdy serwer jeszcze nie istniał). W tym repo wszystkie
    handlery rejestrują się przez `register_blueprints` PO `init_app` → lądują wprost
    na serwerze pierwszego testu i nie są przenoszone na kolejne. W produkcji
    `create_app` jest wołane RAZ, więc problem nie występuje. Tu re-bindujemy handlery,
    których ta suita używa, na bieżący serwer (idempotentne — nadpisuje ten sam slot).
    """
    from modules.api_mobile.ws import ws_connect
    from modules.orders.wms_events import handle_disconnect
    socketio.on_event('connect', ws_connect)
    socketio.on_event('disconnect', handle_disconnect)
    yield


# ---------------------------------------------------------------------------
# Helpery tokenów (parytet z apką: identity=str(user.id), claim 'pwd')
# ---------------------------------------------------------------------------

def _access_token(app, user, expires_delta=None):
    from flask_jwt_extended import create_access_token
    with app.app_context():
        return create_access_token(
            identity=str(user.id),
            additional_claims={'pwd': 'x'},
            expires_delta=expires_delta,
        )


def _refresh_token(app, user):
    from flask_jwt_extended import create_refresh_token
    with app.app_context():
        return create_refresh_token(
            identity=str(user.id),
            additional_claims={'pwd': 'x'},
        )


def _jti_of(app, token):
    from flask_jwt_extended import decode_token
    with app.app_context():
        return decode_token(token)['jti']


# ---------------------------------------------------------------------------
# AKCEPTACJA
# ---------------------------------------------------------------------------

def test_ws_connect_with_jwt_in_auth(app, db, make_user):
    u = make_user()
    token = _access_token(app, u)
    tc = socketio.test_client(app, auth={'token': token})
    assert tc.is_connected()
    assert u.id in _bound_uids()
    tc.disconnect()


def test_ws_connect_with_jwt_in_query_string(app, db, make_user):
    u = make_user()
    token = _access_token(app, u)
    tc = socketio.test_client(app, query_string=f'token={token}')
    assert tc.is_connected()
    assert u.id in _bound_uids()
    tc.disconnect()


def test_ws_connect_without_token_accepted(app, db):
    # Parytet web/WMS — brak tokenu nie odrzuca połączenia.
    tc = socketio.test_client(app)
    assert tc.is_connected()
    tc.disconnect()


def test_ws_connect_with_session_cookie_accepted(app, db, make_user, client, login):
    # Połączenie webowe (cookie sesji, bez JWT) musi przejść — connect bez tokenu akceptuje.
    u = make_user()
    login(u)
    tc = socketio.test_client(app, flask_test_client=client)
    assert tc.is_connected()
    # Web NIE jest wiązany w _ws_users (tylko JWT).
    assert u.id not in _bound_uids()
    tc.disconnect()


# ---------------------------------------------------------------------------
# ODRZUCENIE
# ---------------------------------------------------------------------------

def test_ws_connect_garbage_token_rejected(app, db):
    tc = socketio.test_client(app, auth={'token': 'to-nie-jest-jwt'})
    assert not tc.is_connected()


def test_ws_connect_expired_token_rejected(app, db, make_user):
    u = make_user()
    token = _access_token(app, u, expires_delta=timedelta(seconds=-10))
    tc = socketio.test_client(app, auth={'token': token})
    assert not tc.is_connected()
    assert u.id not in _bound_uids()


def test_ws_connect_refresh_token_rejected(app, db, make_user):
    u = make_user()
    token = _refresh_token(app, u)
    tc = socketio.test_client(app, auth={'token': token})
    assert not tc.is_connected()
    assert u.id not in _bound_uids()


def test_ws_connect_blocklisted_token_rejected(app, db, make_user):
    from modules.api_mobile.models import MobileTokenBlocklist
    from modules.orders.models import get_local_now

    u = make_user()
    token = _access_token(app, u)
    jti = _jti_of(app, token)
    db.session.add(MobileTokenBlocklist(
        jti=jti, token_type='access', user_id=u.id,
        expires_at=get_local_now() + timedelta(hours=1),
    ))
    db.session.commit()

    tc = socketio.test_client(app, auth={'token': token})
    assert not tc.is_connected()
    assert u.id not in _bound_uids()


def test_ws_connect_inactive_user_rejected(app, db, make_user):
    u = make_user()
    token = _access_token(app, u)
    u.is_active = False
    db.session.commit()

    tc = socketio.test_client(app, auth={'token': token})
    assert not tc.is_connected()
    assert u.id not in _bound_uids()


# ---------------------------------------------------------------------------
# CLEANUP PRZY DISCONNECT
# ---------------------------------------------------------------------------

def test_ws_disconnect_unbinds_sid(app, db, make_user):
    u = make_user()
    token = _access_token(app, u)
    tc = socketio.test_client(app, auth={'token': token})
    assert tc.is_connected()
    assert u.id in _bound_uids()

    tc.disconnect()
    assert u.id not in _bound_uids()
