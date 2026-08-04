"""WMS: wysyłka zlecenia (w sesji i z listy) oraz powrót spakowanego zlecenia do WMS."""

import pytest


# ---------- pomocnicze ----------

def _seed_statuses(db):
    """Statusy zamówień używane przez wysyłkę — testowa baza startuje pusta."""
    from modules.orders.models import OrderStatus
    for slug, name in (('dostarczone_gom', 'Dostarczone GOM'),
                       ('spakowane', 'Spakowane'),
                       ('wyslane', 'Wysłane')):
        if not OrderStatus.query.filter_by(slug=slug).first():
            db.session.add(OrderStatus(slug=slug, name=name, is_active=True))
    db.session.commit()


def _sr_packed(db, make_user, make_order, orders_count=1):
    """Zlecenie w statusie 'spakowane' z zamówieniami w statusie 'spakowane'."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    u = make_user()
    sr = ShippingRequest(request_number=ShippingRequest.generate_request_number(),
                         user_id=u.id, status='spakowane')
    db.session.add(sr)
    db.session.commit()
    orders = []
    for _ in range(orders_count):
        o = make_order(u, status='spakowane')
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
        orders.append(o)
    db.session.commit()
    return sr, orders


def _wms_session(db, admin):
    from modules.orders.wms_models import WmsSession
    s = WmsSession(session_token='tok-test', user_id=admin.id, status='active')
    db.session.add(s)
    db.session.commit()
    return s


@pytest.fixture
def notifications(monkeypatch):
    """Podmienia powiadomienia na zapis do listy — testy nie wysyłają maili."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    sent = {'tracking': [], 'status': []}
    monkeypatch.setattr(EmailManager, 'notify_tracking_added',
                        staticmethod(lambda order, **kw: sent['tracking'].append(order.id)))
    monkeypatch.setattr(EmailManager, 'notify_status_change',
                        staticmethod(lambda order, old, new: sent['status'].append(order.id)))
    monkeypatch.setattr(PushManager, 'notify_tracking_added',
                        staticmethod(lambda order, **kw: None))
    monkeypatch.setattr(PushManager, 'notify_status_change',
                        staticmethod(lambda order, old, new: None))
    return sent


# ---------- Task 1: panel w sesji WMS ----------

def test_session_ship_sr_still_works(client, db, make_user, make_order, login, notifications):
    """Regresja: panel w sesji działa jak przed przeniesieniem logiki."""
    from modules.orders.models import OrderShipment
    admin = make_user(role='admin')
    login(admin)
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)
    session = _wms_session(db, admin)

    r = client.post(f'/admin/orders/wms/{session.id}/ship-sr',
                    json={'shipping_request_id': sr.id, 'courier': 'inpost',
                          'tracking_number': 'ABC123', 'parcel_size': 'B'})

    assert r.status_code == 200
    db.session.refresh(sr)
    assert sr.status == 'wyslane'
    assert sr.tracking_number == 'ABC123'
    assert all(o.status == 'wyslane' for o in orders)
    assert OrderShipment.query.filter_by(tracking_number='ABC123').count() == len(orders)
    assert notifications['tracking'] == [o.id for o in orders]


def test_session_ship_sr_without_tracking(client, db, make_user, make_order, login, notifications):
    """Numer przesyłki nieobowiązkowy również w sesji; klient dostaje mail o statusie."""
    from modules.orders.models import OrderShipment
    admin = make_user(role='admin')
    login(admin)
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)
    session = _wms_session(db, admin)

    r = client.post(f'/admin/orders/wms/{session.id}/ship-sr',
                    json={'shipping_request_id': sr.id})

    assert r.status_code == 200
    db.session.refresh(sr)
    assert sr.status == 'wyslane'
    assert OrderShipment.query.count() == 0          # bez numeru nie ma wpisu przesyłki
    assert notifications['tracking'] == []
    assert notifications['status'] == [o.id for o in orders]


# ---------- Task 2: wysyłka z listy zleceń ----------

def test_ship_from_list_with_tracking(client, db, make_user, make_order, login, notifications):
    from modules.orders.models import OrderShipment
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order, orders_count=2)

    r = client.post(f'/admin/orders/shipping-requests/{sr.id}/ship',
                    json={'courier': 'dpd', 'tracking_number': 'XYZ999', 'parcel_size': 'A'})

    assert r.status_code == 200
    db.session.refresh(sr)
    assert sr.status == 'wyslane'
    assert sr.courier == 'dpd'
    assert all(o.status == 'wyslane' for o in orders)
    assert OrderShipment.query.filter_by(tracking_number='XYZ999').count() == 2
    assert sorted(notifications['tracking']) == sorted(o.id for o in orders)


def test_ship_from_list_without_tracking(client, db, make_user, make_order, login, notifications):
    from modules.orders.models import OrderShipment
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)

    r = client.post(f'/admin/orders/shipping-requests/{sr.id}/ship', json={})

    assert r.status_code == 200
    db.session.refresh(sr)
    assert sr.status == 'wyslane'
    assert OrderShipment.query.count() == 0
    assert notifications['status'] == [o.id for o in orders]


def test_ship_from_list_rejects_not_packed(client, db, make_user, make_order, login, notifications):
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)
    sr.status = 'oplacone'
    db.session.commit()

    r = client.post(f'/admin/orders/shipping-requests/{sr.id}/ship',
                    json={'tracking_number': 'AAA'})

    assert r.status_code == 400
    db.session.refresh(sr)
    assert sr.status == 'oplacone'
    assert notifications['tracking'] == []


def test_ship_from_list_rejects_already_shipped(client, db, make_user, make_order, login,
                                                notifications):
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)
    sr.status = 'wyslane'
    db.session.commit()

    r = client.post(f'/admin/orders/shipping-requests/{sr.id}/ship',
                    json={'tracking_number': 'BBB'})

    assert r.status_code in (400, 409)
    assert notifications['tracking'] == []   # klient nie dostaje drugiego trackingu


def test_ship_from_list_rejects_order_locked_in_session(client, db, make_user, make_order, login,
                                                        notifications):
    from modules.orders.models import get_local_now
    admin = make_user(role='admin')
    login(admin)
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)
    session = _wms_session(db, admin)
    orders[0].wms_locked_at = get_local_now()
    orders[0].wms_session_id = session.id
    db.session.commit()

    r = client.post(f'/admin/orders/shipping-requests/{sr.id}/ship',
                    json={'tracking_number': 'CCC'})

    assert r.status_code == 409
    db.session.refresh(sr)
    assert sr.status == 'spakowane'
