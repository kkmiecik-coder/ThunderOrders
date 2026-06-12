"""Testy E3 (follow-up E2): Idempotency-Key dla POST /shop/checkout (claim-first).

Helpery `_auth`/`_onhand_type`/`_onhand_order_type` skopiowane z test_mobile_api_cart.py.
"""


# ---------------------------------------------------------------------------
# Wspólne helpery
# ---------------------------------------------------------------------------

def _auth(client, db, make_user):
    """Tworzy usera, loguje przez mobile API i zwraca (headers, user)."""
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': u.email, 'password': 'Haslo123!'})
    token = r.get_json()['data']['access_token']
    return {'Authorization': f'Bearer {token}'}, u


def _onhand_type(db):
    from modules.products.models import ProductType
    pt = ProductType.query.filter_by(slug='on-hand').first()
    if not pt:
        pt = ProductType(name='On-hand', slug='on-hand')
        db.session.add(pt)
        db.session.commit()
    return pt


def _onhand_order_type(db):
    """Seed OrderType('on_hand') wymagany przez generate_order_number przy checkout."""
    from modules.orders.models import OrderType
    ot = OrderType.query.filter_by(slug='on_hand').first()
    if not ot:
        ot = OrderType(slug='on_hand', name='On-hand', prefix='OH')
        db.session.add(ot)
        db.session.commit()
    return ot


def _add_to_cart(client, h, product_id, qty=1):
    return client.post('/api/mobile/v1/shop/cart/items', headers=h,
                       json={'product_id': product_id, 'quantity': qty})


def test_checkout_idempotent_replay_returns_same_order(client, db, make_user, make_product):
    h, _ = _auth(client, db, make_user)
    _onhand_order_type(db)
    p = make_product(product_type_id=_onhand_type(db).id, quantity=5, sale_price='10.00')
    _add_to_cart(client, h, p.id, 2)
    key = 'idem-123e4567-e89b-12d3-a456-426614174000'
    hk = {**h, 'Idempotency-Key': key}
    r1 = client.post('/api/mobile/v1/shop/checkout', headers=hk, json={})
    assert r1.status_code == 201
    order_id_1 = r1.get_json()['data']['order_id']
    # Powtórka tym samym kluczem — koszyk już pusty, ale idempotencja zwraca pierwotną odpowiedź
    r2 = client.post('/api/mobile/v1/shop/checkout', headers=hk, json={})
    assert r2.status_code == 201
    assert r2.get_json()['data']['order_id'] == order_id_1
    # Tylko JEDNO zamówienie w bazie
    from modules.orders.models import Order
    assert Order.query.filter_by(order_type='on_hand').count() == 1


def test_checkout_without_key_works_as_before(client, db, make_user, make_product):
    h, _ = _auth(client, db, make_user)
    _onhand_order_type(db)
    p = make_product(product_type_id=_onhand_type(db).id, quantity=5, sale_price='10.00')
    _add_to_cart(client, h, p.id, 1)
    r = client.post('/api/mobile/v1/shop/checkout', headers=h, json={})
    assert r.status_code == 201


def test_checkout_different_keys_two_orders(client, db, make_user, make_product):
    h, _ = _auth(client, db, make_user)
    _onhand_order_type(db)
    p = make_product(product_type_id=_onhand_type(db).id, quantity=5, sale_price='10.00')
    _add_to_cart(client, h, p.id, 1)
    client.post('/api/mobile/v1/shop/checkout', headers={**h, 'Idempotency-Key': 'k1'}, json={})
    _add_to_cart(client, h, p.id, 1)
    client.post('/api/mobile/v1/shop/checkout', headers={**h, 'Idempotency-Key': 'k2'}, json={})
    from modules.orders.models import Order
    assert Order.query.filter_by(order_type='on_hand').count() == 2
