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
    """Podmienia powiadomienia na zapis do listy — testy nie wysyłają maili.

    Powiadomienia idą raz na zlecenie wysyłki, więc listy zbierają id zlecenia,
    nie id zamówień. Rozdział na 'tracking'/'status' po tym, czy poszedł numer.
    """
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    sent = {'tracking': [], 'status': []}

    def _email(shipping_request, **kw):
        bucket = 'tracking' if kw.get('tracking_number') else 'status'
        sent[bucket].append(shipping_request.id)

    monkeypatch.setattr(EmailManager, 'notify_shipment_sent', staticmethod(_email))
    monkeypatch.setattr(PushManager, 'notify_shipment_sent',
                        staticmethod(lambda shipping_request, **kw: None))
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
    assert notifications['tracking'] == [sr.id]


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
    assert notifications['status'] == [sr.id]


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
    assert notifications['tracking'] == [sr.id]


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
    assert notifications['status'] == [sr.id]


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

    assert r.status_code == 409
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


# ---------- Task 3: powrót do WMS ----------

def _packed_with_material(db, make_user, make_order):
    """Spakowane zlecenie z pozycją odhaczoną i przypisanym materiałem."""
    from modules.orders.models import OrderItem
    from modules.orders.wms_models import PackagingMaterial
    sr, orders = _sr_packed(db, make_user, make_order)
    mat = PackagingMaterial(name='Karton B', type='karton', quantity_in_stock=7, is_active=True)
    db.session.add(mat)
    db.session.commit()

    order = orders[0]
    order.packaging_material_id = mat.id
    # price i total są NOT NULL w OrderItem — muszą być podane wprost.
    item = OrderItem(order_id=order.id, custom_name='Figurka', is_custom=True, quantity=2,
                     price=50.00, total=100.00,
                     picked=True, picked_quantity=2, wms_status='zebrane')
    db.session.add(item)
    db.session.commit()
    return sr, order, mat, item


def test_reopen_full_resets_picking(client, db, make_user, make_order, login):
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, order, mat, item = _packed_with_material(db, make_user, make_order)

    r = client.post('/admin/orders/wms/create-session',
                    json={'shipping_request_ids': [sr.id], 'reopen_mode': 'full'})

    assert r.status_code == 200
    db.session.refresh(sr); db.session.refresh(order); db.session.refresh(mat); db.session.refresh(item)
    assert order.status == 'dostarczone_gom'
    assert sr.status == 'oplacone'
    assert item.picked is False
    assert item.picked_quantity == 0
    assert item.wms_status == 'do_zebrania'
    assert mat.quantity_in_stock == 8              # opakowanie wróciło na stan
    assert order.packaging_material_id is None


def test_reopen_repack_keeps_picking(client, db, make_user, make_order, login):
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, order, mat, item = _packed_with_material(db, make_user, make_order)

    r = client.post('/admin/orders/wms/create-session',
                    json={'shipping_request_ids': [sr.id], 'reopen_mode': 'repack'})

    assert r.status_code == 200
    db.session.refresh(sr); db.session.refresh(order); db.session.refresh(mat); db.session.refresh(item)
    assert order.status == 'dostarczone_gom'
    assert sr.status == 'oplacone'
    assert item.picked is True                     # zebranie zachowane
    assert item.wms_status == 'zebrane'
    assert mat.quantity_in_stock == 8


def test_packed_order_still_rejected_without_reopen_mode(client, db, make_user, make_order, login):
    """Zwykłe zakładanie sesji nie wpuszcza spakowanych — tylko świadomy powrót."""
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)

    r = client.post('/admin/orders/wms/create-session',
                    json={'shipping_request_ids': [sr.id]})

    assert r.status_code == 400
    db.session.refresh(orders[0])
    assert orders[0].status == 'spakowane'


def test_reopen_rejects_unknown_mode(client, db, make_user, make_order, login):
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)

    r = client.post('/admin/orders/wms/create-session',
                    json={'shipping_request_ids': [sr.id], 'reopen_mode': 'cokolwiek'})

    assert r.status_code == 400
    db.session.refresh(orders[0])
    assert orders[0].status == 'spakowane'


def test_ship_with_tracking_without_courier(client, db, make_user, make_order, login, notifications):
    """Numer przesyłki bez kuriera — nie wolno wywalić się na NOT NULL, dostaje
    kuriera zastępczego 'other', widoczny zarówno na zleceniu jak i na przesyłce."""
    from modules.orders.models import OrderShipment
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)

    r = client.post(f'/admin/orders/shipping-requests/{sr.id}/ship',
                    json={'tracking_number': 'NOCOURIER1'})

    assert r.status_code == 200
    db.session.refresh(sr)
    assert sr.courier == 'other'
    shipments = OrderShipment.query.filter_by(tracking_number='NOCOURIER1').all()
    assert len(shipments) == len(orders)
    assert all(s.courier == 'other' for s in shipments)
    assert notifications['tracking'] == [sr.id]


def test_ship_failure_leaves_nothing_changed(client, db, make_user, make_order, login,
                                             notifications, monkeypatch):
    """Gdy zapis wpisu przesyłki się wywali, statusy nie mogą zostać w połowie
    zmienione — albo wszystko wchodzi razem, albo nic."""
    from modules.orders.models import OrderShipment
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)

    def boom(self, *args, **kwargs):
        raise RuntimeError('symulowany blad zapisu')

    monkeypatch.setattr(OrderShipment, '__init__', boom)

    r = client.post(f'/admin/orders/shipping-requests/{sr.id}/ship',
                    json={'tracking_number': 'WILLFAIL'})

    assert r.status_code == 500
    db.session.refresh(sr)
    assert sr.status == 'spakowane'
    for o in orders:
        db.session.refresh(o)
        assert o.status != 'wyslane'
    assert OrderShipment.query.count() == 0


# ---------- C1: brak duplikatu powiadomienia o trackingu ----------

def test_ship_does_not_resend_tracking_when_shipment_exists(client, db, make_user, make_order,
                                                             login, notifications):
    """Numer przesyłki wpisany wcześniej w oknie "Dodaj koszty" już wysłał maila
    i utworzył OrderShipment. "Oznacz jako wysłane" z tym samym numerem nie może
    wysłać identycznego maila/pusha drugi raz."""
    from modules.orders.models import OrderShipment
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)
    db.session.add(OrderShipment(
        order_id=orders[0].id,
        tracking_number='PREEXIST1',
        courier='dpd',
        notes='Dodano z okna kosztow',
    ))
    db.session.commit()

    r = client.post(f'/admin/orders/shipping-requests/{sr.id}/ship',
                    json={'courier': 'dpd', 'tracking_number': 'PREEXIST1'})

    assert r.status_code == 200
    db.session.refresh(sr)
    assert sr.status == 'wyslane'
    assert notifications['tracking'] == []            # brak drugiego maila o trackingu
    assert OrderShipment.query.filter_by(tracking_number='PREEXIST1').count() == 1


# ---------- Decyzja 2: nie da się wysłać nieopłaconego zlecenia z sesji WMS ----------

def test_session_ship_rejects_unpaid_request(client, db, make_user, make_order, login,
                                             notifications):
    """Zlecenie czekające na opłacenie nie może zostać wysłane nawet z sesji WMS —
    wspólna funkcja ship_shipping_request() blokuje statusy przedpłatne."""
    from modules.orders.models import OrderShipment
    admin = make_user(role='admin')
    login(admin)
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)
    sr.status = 'czeka_na_oplacenie'
    for o in orders:
        o.status = 'spakowane'
    db.session.commit()
    session = _wms_session(db, admin)

    r = client.post(f'/admin/orders/wms/{session.id}/ship-sr',
                    json={'shipping_request_id': sr.id, 'tracking_number': 'UNPAID1'})

    assert r.status_code == 409
    db.session.refresh(sr)
    assert sr.status == 'czeka_na_oplacenie'
    for o in orders:
        db.session.refresh(o)
        assert o.status != 'wyslane'
    assert OrderShipment.query.count() == 0
    assert notifications['tracking'] == []
    assert notifications['status'] == []


def test_session_ship_allows_partially_packed_request(client, db, make_user, make_order, login,
                                                       notifications):
    """Zlecenie w statusie 'oplacone' (jeszcze nie 'spakowane', bo część zamówień
    pakuje się w innej sesji) musi dać się wysłać z sesji WMS — blokada dotyczy
    wyłącznie statusów przedpłatnych, nie ma twardego wymogu 'tylko spakowane'."""
    admin = make_user(role='admin')
    login(admin)
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)
    sr.status = 'oplacone'
    db.session.commit()
    session = _wms_session(db, admin)

    r = client.post(f'/admin/orders/wms/{session.id}/ship-sr',
                    json={'shipping_request_id': sr.id})

    assert r.status_code == 200
    db.session.refresh(sr)
    assert sr.status == 'wyslane'


def test_reopen_by_order_ids_also_resets_shipping_request(client, db, make_user, make_order, login):
    """Cofnięcie przez same order_ids (bez shipping_request_ids) musi też cofnąć
    status zlecenia wysyłki — inaczej zlecenie zostaje 'spakowane', mimo że jego
    zamówienia wróciły do zbierania."""
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order)

    r = client.post('/admin/orders/wms/create-session',
                    json={'order_ids': [orders[0].id], 'reopen_mode': 'full'})

    assert r.status_code == 200
    db.session.refresh(sr); db.session.refresh(orders[0])
    assert orders[0].status == 'dostarczone_gom'
    assert sr.status == 'oplacone'
