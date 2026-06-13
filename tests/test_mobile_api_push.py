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
