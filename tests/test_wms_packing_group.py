"""WMS: pakowanie zlecenia wysyłki jako jednej paczki."""

import pytest


# ---------- pomocnicze ----------

def _seed_statuses(db):
    """Statusy zamówień — testowa baza startuje pusta."""
    from modules.orders.models import OrderStatus
    for slug, name in (('dostarczone_gom', 'Dostarczone GOM'),
                       ('spakowane', 'Spakowane'),
                       ('wyslane', 'Wysłane')):
        if not OrderStatus.query.filter_by(slug=slug).first():
            db.session.add(OrderStatus(slug=slug, name=name, is_active=True))
    db.session.commit()


def _order_with_item(db, user, make_order, make_product, weight, dims, qty=1):
    """Zamówienie z jedną pozycją produktową o zadanej wadze i wymiarach."""
    from modules.orders.models import OrderItem
    o = make_order(user, status='dostarczone_gom')
    p = make_product(weight=weight, length=dims[0], width=dims[1], height=dims[2])
    # price i total są NOT NULL w OrderItem — muszą być podane wprost.
    db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=qty,
                             price=10.00, total=10.00 * qty,
                             picked=True, picked_quantity=qty))
    db.session.commit()
    return o


# ---------- Task 1: sugestie dla grupy ----------

def test_suggest_for_group_sums_weight_of_all_orders(app, db, make_user, make_order,
                                                     make_product):
    """Dopasowanie liczy się po sumie wszystkich zamówień z paczki, nie po jednym."""
    from modules.orders.wms_utils import suggest_packaging_for_orders
    u = make_user()
    o1 = _order_with_item(db, u, make_order, make_product, weight=1.5, dims=(10, 10, 10))
    o2 = _order_with_item(db, u, make_order, make_product, weight=2.0, dims=(10, 10, 10))

    result = suggest_packaging_for_orders([o1, o2])

    assert result['total_weight'] == 3.5
    # objętość: 2 × 1000 cm³ × bufor 1.3
    assert result['total_volume'] == pytest.approx(2600.0)


def test_suggest_single_order_unchanged(app, db, make_user, make_order, make_product):
    """suggest_packaging(order) zwraca to samo co suggest_packaging_for_orders([order])."""
    from modules.orders.wms_utils import suggest_packaging, suggest_packaging_for_orders
    u = make_user()
    o = _order_with_item(db, u, make_order, make_product, weight=1.5, dims=(10, 10, 10))

    assert suggest_packaging(o) == suggest_packaging_for_orders([o])


def test_suggest_for_group_without_items_warns(app, db, make_user, make_order):
    """Grupa bez pozycji zwraca ostrzeżenie zamiast wywalać się."""
    from modules.orders.wms_utils import suggest_packaging_for_orders
    u = make_user()
    o = make_order(u, status='dostarczone_gom')

    result = suggest_packaging_for_orders([o])

    assert result['suggestions'] == []
    assert result['warnings'] == ['Zamówienie nie ma pozycji']


# ---------- Task 2: pakowanie grupy ----------

def _material(db, name='Karton B', stock=7):
    from modules.orders.wms_models import PackagingMaterial
    mat = PackagingMaterial(name=name, type='karton', quantity_in_stock=stock, is_active=True)
    db.session.add(mat)
    db.session.commit()
    return mat


def _sr_in_session(db, admin, make_user, make_order, make_product, orders_count=3,
                   in_session=None):
    """Zlecenie wysyłki + sesja WMS. in_session = ile zamówień wchodzi do sesji."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    from modules.orders.wms_models import WmsSession, WmsSessionOrder
    u = make_user()
    sr = ShippingRequest(request_number=ShippingRequest.generate_request_number(),
                         user_id=u.id, status='oplacone')
    db.session.add(sr)
    db.session.commit()

    orders = []
    for _ in range(orders_count):
        o = _order_with_item(db, u, make_order, make_product, weight=1.0, dims=(10, 10, 10))
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
        orders.append(o)
    db.session.commit()

    session = WmsSession(session_token='tok-pack', user_id=admin.id, status='active')
    db.session.add(session)
    db.session.commit()

    count = orders_count if in_session is None else in_session
    for o in orders[:count]:
        db.session.add(WmsSessionOrder(session_id=session.id, order_id=o.id))
    db.session.commit()

    return sr, orders, session


@pytest.fixture
def packing_emails(monkeypatch):
    """Podmienia mail/push ze zdjęciem paczki na zapis do listy."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    sent = []
    monkeypatch.setattr(EmailManager, 'notify_packing_photo',
                        staticmethod(lambda order: sent.append(order.id)))
    monkeypatch.setattr(PushManager, 'notify_packing_photo',
                        staticmethod(lambda order: None))
    return sent


def test_pack_group_packs_all_orders_once(app, db, make_user, make_order, make_product,
                                          packing_emails):
    """Jedno wywołanie pakuje wszystkie zamówienia, zdejmuje 1 karton, wysyła 1 mail."""
    from modules.orders.wms_packing import pack_shipping_request_group
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)
    for o in orders:
        o.packing_photo = 'uploads/packing_photos/x.jpg'
    db.session.commit()

    result = pack_shipping_request_group(
        session, sr, packaging_material_id=mat.id, total_package_weight=2.5,
        send_email=True, user_id=admin.id,
    )
    db.session.commit()

    assert len(result['orders']) == 3
    for o in orders:
        db.session.refresh(o)
        assert o.status == 'spakowane'
        assert o.packaging_material_id == mat.id
        assert float(o.total_package_weight) == 2.5
    db.session.refresh(mat)
    assert mat.quantity_in_stock == 6          # jedno opakowanie, nie trzy
    assert len(packing_emails) == 1            # jeden mail na paczkę
    db.session.refresh(sr)
    assert sr.status == 'spakowane'
    assert sr.packaging_material_id == mat.id  # wycena zgodna z rzeczywistością


def test_pack_group_partial_session_leaves_sr_unpacked(app, db, make_user, make_order,
                                                       make_product, packing_emails):
    """W sesji są 2 z 3 zamówień — pakują się 2, zlecenie nie jest jeszcze spakowane."""
    from modules.orders.wms_packing import pack_shipping_request_group
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product,
                                         orders_count=3, in_session=2)
    mat = _material(db, stock=7)

    result = pack_shipping_request_group(session, sr, packaging_material_id=mat.id,
                                         user_id=admin.id)
    db.session.commit()

    assert len(result['orders']) == 2
    db.session.refresh(orders[2])
    assert orders[2].status == 'dostarczone_gom'
    db.session.refresh(sr)
    assert sr.status != 'spakowane'
    db.session.refresh(mat)
    assert mat.quantity_in_stock == 6


def test_pack_group_rejects_unpicked_order(app, db, make_user, make_order, make_product,
                                           packing_emails):
    """Niedokompletowane zamówienie blokuje pakowanie całej paczki."""
    from modules.orders.wms_packing import pack_shipping_request_group, PackingGroupError
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)
    orders[1].items[0].picked_quantity = 0
    db.session.commit()

    with pytest.raises(PackingGroupError):
        pack_shipping_request_group(session, sr, packaging_material_id=mat.id,
                                    user_id=admin.id)
    db.session.rollback()

    db.session.refresh(mat)
    assert mat.quantity_in_stock == 7
    for o in orders:
        db.session.refresh(o)
        assert o.status == 'dostarczone_gom'


def test_pack_group_rejects_empty_group(app, db, make_user, make_order, make_product,
                                        packing_emails):
    """Drugie pakowanie tego samego zlecenia odbija się błędem."""
    from modules.orders.wms_packing import pack_shipping_request_group, PackingGroupError
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)

    pack_shipping_request_group(session, sr, packaging_material_id=mat.id, user_id=admin.id)
    db.session.commit()

    with pytest.raises(PackingGroupError):
        pack_shipping_request_group(session, sr, packaging_material_id=mat.id,
                                    user_id=admin.id)


def test_pack_group_copies_photo_across_orders(app, db, make_user, make_order, make_product,
                                               packing_emails):
    """Zdjęcie zrobione przy pierwszym zamówieniu trafia do całej paczki."""
    from modules.orders.wms_packing import pack_shipping_request_group
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)
    orders[0].packing_photo = 'uploads/packing_photos/paczka.jpg'
    db.session.commit()

    pack_shipping_request_group(session, sr, packaging_material_id=mat.id, user_id=admin.id)
    db.session.commit()

    for o in orders:
        db.session.refresh(o)
        assert o.packing_photo == 'uploads/packing_photos/paczka.jpg'


def test_pack_group_without_material_does_not_touch_stock(app, db, make_user, make_order,
                                                          make_product, packing_emails):
    """Brak wybranego opakowania — pakujemy, ale nic nie schodzi ze stanu."""
    from modules.orders.wms_packing import pack_shipping_request_group
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)

    pack_shipping_request_group(session, sr, user_id=admin.id)
    db.session.commit()

    db.session.refresh(mat)
    assert mat.quantity_in_stock == 7
    for o in orders:
        db.session.refresh(o)
        assert o.status == 'spakowane'


def test_pack_group_with_deleted_material_warns_and_packs(app, db, make_user, make_order,
                                                          make_product, packing_emails):
    """Materiał skasowany między wyceną a pakowaniem — pakujemy z ostrzeżeniem."""
    from modules.orders.wms_packing import pack_shipping_request_group
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)

    result = pack_shipping_request_group(session, sr, packaging_material_id=999999,
                                         user_id=admin.id)
    db.session.commit()

    assert result['low_stock_warning']         # użytkownik dowiaduje się, że coś nie gra
    for o in orders:
        db.session.refresh(o)
        assert o.status == 'spakowane'
        assert o.packaging_material_id is None


# ---------- Task 3: endpoint HTTP ----------

def test_endpoint_packs_shipping_request(client, app, db, make_user, make_order,
                                         make_product, login, packing_emails):
    _seed_statuses(db)
    admin = make_user(role='admin')
    login(admin)
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)

    r = client.post(f'/admin/orders/wms/{session.id}/pack-shipping-request',
                    json={'shipping_request_id': sr.id,
                          'packaging_material_id': mat.id,
                          'total_package_weight': 2.5})

    assert r.status_code == 200
    assert len(r.get_json()['orders']) == 3
    db.session.refresh(mat)
    assert mat.quantity_in_stock == 6
    for o in orders:
        db.session.refresh(o)
        assert o.status == 'spakowane'


def test_endpoint_rejects_unpicked(client, app, db, make_user, make_order, make_product,
                                   login, packing_emails):
    _seed_statuses(db)
    admin = make_user(role='admin')
    login(admin)
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)
    orders[1].items[0].picked_quantity = 0
    db.session.commit()

    r = client.post(f'/admin/orders/wms/{session.id}/pack-shipping-request',
                    json={'shipping_request_id': sr.id, 'packaging_material_id': mat.id})

    assert r.status_code == 400
    db.session.refresh(mat)
    assert mat.quantity_in_stock == 7
    for o in orders:
        db.session.refresh(o)
        assert o.status == 'dostarczone_gom'


def test_old_pack_order_endpoint_is_gone(client, app, db, make_user, make_order,
                                         make_product, login):
    """Pakowanie per zamówienie znika — została jedna droga, przez zlecenie."""
    _seed_statuses(db)
    admin = make_user(role='admin')
    login(admin)
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)

    r = client.post(f'/admin/orders/wms/{session.id}/pack-order',
                    json={'order_id': orders[0].id})

    assert r.status_code == 404


# ---------- Task 4: zwrot opakowania raz na paczkę ----------

def test_reopen_returns_one_material_per_package(app, db, make_user, make_order,
                                                 make_product, packing_emails):
    """Spakowanie zdjęło 1 karton — cofnięcie musi oddać 1, nie 3."""
    from modules.orders.wms_packing import pack_shipping_request_group
    from modules.orders.wms_utils import reopen_orders_for_wms
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)

    pack_shipping_request_group(session, sr, packaging_material_id=mat.id, user_id=admin.id)
    db.session.commit()
    db.session.refresh(mat)
    assert mat.quantity_in_stock == 6

    reopen_orders_for_wms(orders, mode='full', shipping_requests=[sr])
    db.session.commit()

    db.session.refresh(mat)
    assert mat.quantity_in_stock == 7          # stan wraca do punktu wyjścia
    for o in orders:
        db.session.refresh(o)
        assert o.packaging_material_id is None
        assert o.status == 'dostarczone_gom'


# ---------- Task 5: sugestie dla zlecenia ----------

def test_suggest_sr_endpoint_returns_group_totals(client, app, db, make_user, make_order,
                                                  make_product, login):
    _seed_statuses(db)
    admin = make_user(role='admin')
    login(admin)
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)
    sr.packaging_material_id = mat.id
    db.session.commit()

    r = client.get(f'/api/orders/wms/{session.id}/suggest-packaging-sr/{sr.id}')

    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['orders_count'] == 3
    assert data['total_weight'] == 3.0            # 3 × 1.0 kg
    assert data['suggested_material_id'] == mat.id
    assert any(m['id'] == mat.id for m in data['all_materials'])


def test_suggest_sr_endpoint_mobile_requires_valid_token(client, app, db, make_user,
                                                         make_order, make_product):
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)

    ok = client.get(f'/api/orders/wms/{session.id}/suggest-packaging-sr/{sr.id}/tok-pack')
    bad = client.get(f'/api/orders/wms/{session.id}/suggest-packaging-sr/{sr.id}/zly-token')

    assert ok.status_code == 200
    assert ok.get_json()['orders_count'] == 3
    assert bad.status_code == 403
