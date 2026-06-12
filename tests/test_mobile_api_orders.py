"""Testy E5: mobilne API odczytu zamówień + dashboard.

Helper _auth skopiowany z tests/test_mobile_api_offers.py.
make_order (conftest) NIE tworzy OrderItem ani PaymentConfirmation — robią to helpery niżej.
"""
from decimal import Decimal


def _auth(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': u.email, 'password': 'Haslo123!'})
    token = r.get_json()['data']['access_token']
    return {'Authorization': f'Bearer {token}'}, u


def _add_item(db, order, product=None, quantity=1, price=Decimal('10.00'),
              is_bonus=False, is_full_set=False, **kwargs):
    from modules.orders.models import OrderItem
    it = OrderItem(order_id=order.id, product_id=product.id if product else None,
                   quantity=quantity, price=price, total=price * quantity,
                   is_bonus=is_bonus, is_full_set=is_full_set, **kwargs)
    db.session.add(it); db.session.commit()
    return it


def _add_payment(db, order, stage, status='pending', amount=Decimal('20.00'),
                 proof_file='proof.jpg'):
    from modules.orders.models import PaymentConfirmation
    pc = PaymentConfirmation(order_id=order.id, payment_stage=stage,
                             amount=amount, status=status, proof_file=proof_file)
    db.session.add(pc); db.session.commit()
    return pc


def test_orders_requires_jwt(client, db, make_user):
    assert client.get('/api/mobile/v1/orders').status_code == 401


def test_orders_lists_only_owner(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    other = make_user()
    make_order(u, total_amount=100.00)
    make_order(u, total_amount=50.00)
    make_order(other, total_amount=999.00)            # cudze — nie powinno wyciec
    r = client.get('/api/mobile/v1/orders', headers=h)
    assert r.status_code == 200
    body = r.get_json()
    assert body['pagination']['total'] == 2
    assert len(body['data']) == 2


def test_orders_brief_shape_and_grosze(client, db, make_user, make_order, make_product):
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=50.00, order_type='pre_order',
                   offer_page_name='Drop PO', shipping_cost=Decimal('0.00'))
    p = make_product(sale_price=Decimal('50.00'))
    _add_item(db, o, product=p, quantity=1, price=Decimal('50.00'))
    r = client.get('/api/mobile/v1/orders', headers=h)
    obj = r.get_json()['data'][0]
    assert set(obj) >= {'id', 'order_number', 'order_type', 'status',
                        'status_display_name', 'status_badge_color', 'total',
                        'items_count', 'created_at', 'offer_page_name'}
    assert obj['order_type'] == 'pre_order'
    assert obj['total'] == 5000                       # effective_grand_total grosze (item 50 + ship 0)
    assert obj['items_count'] == 1
    assert obj['offer_page_name'] == 'Drop PO'


def test_orders_filter_by_type(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    make_order(u, order_type='on_hand')
    make_order(u, order_type='pre_order')
    make_order(u, order_type='pre_order')
    r = client.get('/api/mobile/v1/orders?type=pre_order', headers=h)
    body = r.get_json()
    assert body['pagination']['total'] == 2
    assert all(o['order_type'] == 'pre_order' for o in body['data'])


def test_orders_filter_by_status(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    make_order(u, status='nowe')
    make_order(u, status='dostarczone')
    r = client.get('/api/mobile/v1/orders?status=dostarczone', headers=h)
    body = r.get_json()
    assert body['pagination']['total'] == 1
    assert body['data'][0]['status'] == 'dostarczone'


def test_orders_invalid_type_400(client, db, make_user):
    # D1(a): nieznany type → 400 invalid_input. [D1(b): usuń ten test, oczekuj 200 + total 0]
    h, _ = _auth(client, db, make_user)
    r = client.get('/api/mobile/v1/orders?type=banana', headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'invalid_input'


def test_orders_pagination(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    for _ in range(3):
        make_order(u)
    r = client.get('/api/mobile/v1/orders?per_page=2&page=1', headers=h)
    assert r.get_json()['pagination'] == {'page': 1, 'per_page': 2, 'total': 3, 'has_next': True}
    r2 = client.get('/api/mobile/v1/orders?per_page=2&page=2', headers=h)
    assert r2.get_json()['pagination']['has_next'] is False
