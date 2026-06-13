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
