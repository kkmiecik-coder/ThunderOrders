"""Testy E10: mobilne API push (rejestracja/wyrejestrowanie urządzeń FCM).

_auth jak w orders/payments/collection (login → Bearer).
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def _auth(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': u.email, 'password': 'Haslo123!'})
    return {'Authorization': f'Bearer {r.get_json()["data"]["access_token"]}'}, u


# === Task 1: model MobileDevice + migracja ===

def test_mobile_device_table_and_unique(db, make_user):
    from modules.api_mobile.models import MobileDevice
    u = make_user()

    dev = MobileDevice(user_id=u.id, fcm_token='t1', platform='android')
    db.session.add(dev)
    db.session.commit()
    assert dev.id is not None
    assert dev.created_at is not None

    # Drugi insert tego samego fcm_token → IntegrityError (unique globalnie)
    dup = MobileDevice(user_id=u.id, fcm_token='t1', platform='ios')
    db.session.add(dup)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    # FK user_id ondelete CASCADE: usunięcie usera kasuje wiersz urządzenia.
    db.session.execute(text('PRAGMA foreign_keys=ON'))
    db.session.execute(text('DELETE FROM users WHERE id = :uid'), {'uid': u.id})
    db.session.commit()
    assert MobileDevice.query.filter_by(fcm_token='t1').first() is None


# === Task 2: POST /push/devices (rejestracja / upsert) ===

def test_register_device_requires_jwt(client, db):
    r = client.post('/api/mobile/v1/push/devices',
                    json={'fcm_token': 't1', 'platform': 'android'})
    assert r.status_code == 401


def test_register_device_creates(client, db, make_user):
    from modules.api_mobile.models import MobileDevice
    h, u = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/push/devices',
                    json={'fcm_token': 't1', 'platform': 'android'}, headers=h)
    assert r.status_code == 201
    body = r.get_json()
    assert body['success'] is True
    dev = MobileDevice.query.filter_by(fcm_token='t1').first()
    assert dev is not None
    assert dev.user_id == u.id
    assert dev.platform == 'android'
    assert body['data']['id'] == dev.id


def test_register_same_token_same_user_no_dup(client, db, make_user):
    from datetime import datetime
    from modules.api_mobile.models import MobileDevice
    h, u = _auth(client, db, make_user)
    assert client.post('/api/mobile/v1/push/devices',
                       json={'fcm_token': 't1', 'platform': 'android'},
                       headers=h).status_code == 201
    # Postarz last_used_at, by udowodnić odświeżenie przy ponownym POST.
    dev = MobileDevice.query.filter_by(fcm_token='t1').first()
    dev.last_used_at = datetime(2000, 1, 1)
    db.session.commit()
    old = dev.last_used_at

    r = client.post('/api/mobile/v1/push/devices',
                    json={'fcm_token': 't1', 'platform': 'ios'}, headers=h)
    assert r.status_code == 201
    assert MobileDevice.query.filter_by(fcm_token='t1').count() == 1  # brak duplikatu
    db.session.expire_all()
    dev = MobileDevice.query.filter_by(fcm_token='t1').first()
    assert dev.last_used_at > old                                     # odświeżony
    assert dev.platform == 'ios'                                      # zaktualizowany


def test_register_token_rebinds_to_caller(client, db, make_user):
    from modules.api_mobile.models import MobileDevice
    h_a, ua = _auth(client, db, make_user)
    h_b, ub = _auth(client, db, make_user)
    assert client.post('/api/mobile/v1/push/devices',
                       json={'fcm_token': 't1', 'platform': 'android'},
                       headers=h_a).status_code == 201
    # User B rejestruje TEN SAM token (to samo urządzenie po przelogowaniu).
    r = client.post('/api/mobile/v1/push/devices',
                    json={'fcm_token': 't1', 'platform': 'android'}, headers=h_b)
    assert r.status_code == 201
    assert MobileDevice.query.filter_by(fcm_token='t1').count() == 1   # brak duplikatu
    dev = MobileDevice.query.filter_by(fcm_token='t1').first()
    assert dev.user_id == ub.id                                       # przepięty na B
    assert MobileDevice.query.filter_by(user_id=ua.id).count() == 0   # A już nie posiada


def test_register_invalid_platform(client, db, make_user):
    h, u = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/push/devices',
                    json={'fcm_token': 't1', 'platform': 'windows'}, headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'invalid_input'


def test_register_missing_token(client, db, make_user):
    h, u = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/push/devices',
                    json={'platform': 'android'}, headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'invalid_input'


def test_register_token_too_long(client, db, make_user):
    h, u = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/push/devices',
                    json={'fcm_token': 'x' * 513, 'platform': 'android'}, headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'invalid_input'


# === Task 3: DELETE /push/devices/<token> (wyrejestrowanie) ===

def test_delete_device_requires_jwt(client, db):
    assert client.delete('/api/mobile/v1/push/devices/t1').status_code == 401


def test_delete_own_token(client, db, make_user):
    from modules.api_mobile.models import MobileDevice
    h, u = _auth(client, db, make_user)
    assert client.post('/api/mobile/v1/push/devices',
                       json={'fcm_token': 't1', 'platform': 'android'},
                       headers=h).status_code == 201
    r = client.delete('/api/mobile/v1/push/devices/t1', headers=h)
    assert r.status_code == 200
    assert MobileDevice.query.filter_by(fcm_token='t1').first() is None


def test_delete_foreign_token_404_masking(client, db, make_user):
    from modules.api_mobile.models import MobileDevice
    h_a, ua = _auth(client, db, make_user)
    h_b, ub = _auth(client, db, make_user)
    assert client.post('/api/mobile/v1/push/devices',
                       json={'fcm_token': 't1', 'platform': 'android'},
                       headers=h_a).status_code == 201
    # User B próbuje usunąć token usera A → 404 maskujące, wiersz A nietknięty.
    r = client.delete('/api/mobile/v1/push/devices/t1', headers=h_b)
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'not_found'
    dev = MobileDevice.query.filter_by(fcm_token='t1').first()
    assert dev is not None and dev.user_id == ua.id


def test_delete_unknown_token_404(client, db, make_user):
    h, u = _auth(client, db, make_user)
    r = client.delete('/api/mobile/v1/push/devices/nieistnieje', headers=h)
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'not_found'


# === Task 4: kanał FCM (HTTP v1) w PushManager (wysyłka MOCKOWANA, D11) ===
#
# Wysyłka FCM jest w pełni mockowana: patchujemy PushManager._send_fcm_raw i
# _get_fcm_access_token, dzięki czemu realny FCM nigdy nie jest wołany. send_to_user
# wołane SYNCHRONICZNIE (bez wątku _fire_and_forget — by uniknąć flaky testów).

from unittest.mock import MagicMock


class _FakeFcmResp:
    """Lekka atrapa odpowiedzi requests (status_code + json())."""
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


def _enable_fcm(app):
    app.config['FIREBASE_PROJECT_ID'] = 'test-project'
    app.config['FIREBASE_CREDENTIALS_JSON'] = '{"type": "service_account"}'
    app.config['FIREBASE_CREDENTIALS_PATH'] = ''


def _register_device(db, user_id, token, platform='android'):
    from modules.api_mobile.models import MobileDevice
    d = MobileDevice(user_id=user_id, fcm_token=token, platform=platform)
    db.session.add(d)
    db.session.commit()
    return d


def test_fcm_sent_to_device(app, db, make_user, monkeypatch):
    from utils.push_manager import PushManager
    _enable_fcm(app)
    u = make_user()
    _register_device(db, u.id, 'devtok1')
    monkeypatch.setattr(PushManager, '_get_fcm_access_token',
                        staticmethod(lambda: 'fake-token'))
    raw = MagicMock(return_value=_FakeFcmResp(200))
    monkeypatch.setattr(PushManager, '_send_fcm_raw', staticmethod(raw))

    PushManager.send_to_user(u.id, 'Tytuł', 'Treść', url='/zamowienia/1',
                             tag='order-1', notification_type='order_status_changes')

    assert raw.call_count == 1
    args, _ = raw.call_args
    token, message = args[0], args[1]                  # _send_fcm_raw(token, message, token, pid)
    assert token == 'devtok1'
    assert message['token'] == 'devtok1'
    assert message['notification']['title'] == 'Tytuł'
    assert message['notification']['body'] == 'Treść'
    assert message['data']['url'] == '/zamowienia/1'
    assert message['data']['tag'] == 'order-1'


def test_fcm_multi_device(app, db, make_user, monkeypatch):
    from utils.push_manager import PushManager
    _enable_fcm(app)
    u = make_user()
    for t in ('a', 'b', 'c'):
        _register_device(db, u.id, t)
    monkeypatch.setattr(PushManager, '_get_fcm_access_token',
                        staticmethod(lambda: 'fake-token'))
    raw = MagicMock(return_value=_FakeFcmResp(200))
    monkeypatch.setattr(PushManager, '_send_fcm_raw', staticmethod(raw))

    PushManager.send_to_user(u.id, 'T', 'B', notification_type='order_status_changes')

    assert raw.call_count == 3


def test_fcm_unregistered_deletes_token(app, db, make_user, monkeypatch):
    from utils.push_manager import PushManager
    from modules.api_mobile.models import MobileDevice
    _enable_fcm(app)
    u = make_user()
    _register_device(db, u.id, 'stale1')
    monkeypatch.setattr(PushManager, '_get_fcm_access_token',
                        staticmethod(lambda: 'tok'))
    resp = _FakeFcmResp(404, {'error': {'status': 'NOT_FOUND',
                                         'details': [{'errorCode': 'UNREGISTERED'}]}})
    monkeypatch.setattr(PushManager, '_send_fcm_raw',
                        staticmethod(MagicMock(return_value=resp)))

    PushManager.send_to_user(u.id, 'T', 'B', notification_type='order_status_changes')

    assert MobileDevice.query.filter_by(fcm_token='stale1').first() is None


def test_fcm_transient_keeps_token(app, db, make_user, monkeypatch):
    from utils.push_manager import PushManager
    from modules.api_mobile.models import MobileDevice
    _enable_fcm(app)
    u = make_user()
    _register_device(db, u.id, 'keep1')
    monkeypatch.setattr(PushManager, '_get_fcm_access_token',
                        staticmethod(lambda: 'tok'))
    resp = _FakeFcmResp(503, {'error': {'status': 'UNAVAILABLE'}})
    monkeypatch.setattr(PushManager, '_send_fcm_raw',
                        staticmethod(MagicMock(return_value=resp)))

    PushManager.send_to_user(u.id, 'T', 'B', notification_type='order_status_changes')

    assert MobileDevice.query.filter_by(fcm_token='keep1').first() is not None


def test_fcm_disabled_noop(app, db, make_user, monkeypatch):
    from utils.push_manager import PushManager
    from modules.api_mobile.models import MobileDevice
    # NIE włączamy FCM (config puste) → fan-out FCM to no-op
    app.config['FIREBASE_PROJECT_ID'] = ''
    app.config['FIREBASE_CREDENTIALS_JSON'] = ''
    app.config['FIREBASE_CREDENTIALS_PATH'] = ''
    u = make_user()
    _register_device(db, u.id, 'tok')
    raw = MagicMock()
    monkeypatch.setattr(PushManager, '_send_fcm_raw', staticmethod(raw))

    # Nie wywala wysyłki (Web Push nietknięty); FCM nie wołane; token zostaje.
    PushManager.send_to_user(u.id, 'T', 'B', notification_type='order_status_changes')

    assert raw.call_count == 0
    assert MobileDevice.query.filter_by(fcm_token='tok').first() is not None


def test_fcm_respects_preference_off(app, db, make_user, monkeypatch):
    from utils.push_manager import PushManager
    from modules.notifications.models import NotificationPreference
    _enable_fcm(app)
    u = make_user()
    _register_device(db, u.id, 'tok')
    db.session.add(NotificationPreference(user_id=u.id, order_status_changes=False))
    db.session.commit()
    raw = MagicMock(return_value=_FakeFcmResp(200))
    monkeypatch.setattr(PushManager, '_get_fcm_access_token',
                        staticmethod(lambda: 'tok'))
    monkeypatch.setattr(PushManager, '_send_fcm_raw', staticmethod(raw))

    result = PushManager.send_to_user(u.id, 'T', 'B',
                                      notification_type='order_status_changes')

    assert raw.call_count == 0          # preferencja wyłączona → ani Web Push, ani FCM
    assert result is False


def test_existing_notify_reaches_fcm(app, db, make_user, make_order, monkeypatch):
    """Dowód integracji: istniejące notify_* (przez _fire_and_forget) docierają na FCM
    bez zmiany call-site — fan-out jest w rdzeniu send_to_user."""
    from utils.push_manager import PushManager
    _enable_fcm(app)
    u = make_user()
    _register_device(db, u.id, 'tok')
    order = make_order(u, status='nowe')
    monkeypatch.setattr(PushManager, '_get_fcm_access_token',
                        staticmethod(lambda: 'tok'))
    raw = MagicMock(return_value=_FakeFcmResp(200))
    monkeypatch.setattr(PushManager, '_send_fcm_raw', staticmethod(raw))
    # _fire_and_forget → synchroniczny send_to_user (bez wątku, by uniknąć flaky)
    monkeypatch.setattr(PushManager, '_fire_and_forget',
                        staticmethod(PushManager.send_to_user))

    with app.test_request_context():
        PushManager.notify_status_change(order, 'nowe', 'zamowiono')

    assert raw.call_count == 1


def test_web_push_unchanged_without_devices(app, db, make_user, monkeypatch):
    """Brak MobileDevice → FCM no-op; Web Push 1:1 (brak subs/VAPID → False)."""
    from utils.push_manager import PushManager
    _enable_fcm(app)
    u = make_user()                                      # brak MobileDevice
    monkeypatch.setattr(PushManager, '_get_fcm_access_token',
                        staticmethod(lambda: 'tok'))
    raw = MagicMock(return_value=_FakeFcmResp(200))
    monkeypatch.setattr(PushManager, '_send_fcm_raw', staticmethod(raw))

    result = PushManager.send_to_user(u.id, 'T', 'B',
                                      notification_type='order_status_changes')

    assert raw.call_count == 0
    assert result is False
