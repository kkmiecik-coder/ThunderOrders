"""Admin: wybór materiału na zleceniu ustawia FK + gabaryt, nie rusza magazynu."""


def _admin(make_user):
    return make_user(role='admin')


def _sr(db, make_user, make_order):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    u = make_user()
    o = make_order(u, status='dostarczone_gom')
    sr = ShippingRequest(request_number=ShippingRequest.generate_request_number(),
                         user_id=u.id, status='czeka_na_wycene')
    db.session.add(sr); db.session.commit()
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
    db.session.commit()
    return sr


def _material(db):
    from modules.orders.wms_models import PackagingMaterial
    m = PackagingMaterial(name='Karton B', type='karton', sale_price=21.49,
                          size_category='B', quantity_in_stock=10, is_active=True)
    db.session.add(m); db.session.commit()
    return m


def test_put_sets_material_and_derives_parcel_size(client, db, make_user, make_order, login):
    login(_admin(make_user))
    sr = _sr(db, make_user, make_order)
    mat = _material(db)
    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'packaging_material_id': mat.id})
    assert r.status_code == 200
    db.session.refresh(sr); db.session.refresh(mat)
    assert sr.packaging_material_id == mat.id
    assert sr.parcel_size == 'B'                 # wyprowadzone z materiału
    assert mat.quantity_in_stock == 10           # magazyn NIE ruszony


def test_put_explicit_parcel_size_wins(client, db, make_user, make_order, login):
    login(_admin(make_user))
    sr = _sr(db, make_user, make_order)
    mat = _material(db)
    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'packaging_material_id': mat.id, 'parcel_size': 'C'})
    assert r.status_code == 200
    db.session.refresh(sr)
    assert sr.parcel_size == 'C'                 # jawny parcel_size ma priorytet


def test_get_serializes_new_fields(client, db, make_user, make_order, login):
    login(_admin(make_user))
    sr = _sr(db, make_user, make_order)
    mat = _material(db)
    sr.packaging_material_id = mat.id
    sr.client_package_preference = 'koperta'
    sr.client_notes = 'Ostrożnie'
    db.session.commit()
    data = client.get(f'/admin/orders/shipping-requests/{sr.id}').get_json()
    assert data['packaging_material_id'] == mat.id
    assert data['packaging_material']['size_category'] == 'B'
    assert data['client_package_preference'] == 'koperta'
    assert data['client_notes'] == 'Ostrożnie'
