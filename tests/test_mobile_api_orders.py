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


def test_order_detail_requires_jwt(client, db, make_user, make_order):
    u = make_user()
    o = make_order(u)
    assert client.get(f'/api/mobile/v1/orders/{o.id}').status_code == 401


def test_order_detail_not_found_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.get('/api/mobile/v1/orders/999999', headers=h)
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'order_not_found'


def test_order_detail_other_user_404(client, db, make_user, make_order):
    # Korekta 4: cudze zamówienie → 404 (NIE 403) — bez wycieku istnienia.
    h, u = _auth(client, db, make_user)
    other = make_user()
    o = make_order(other, total_amount=100.00)
    r = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h)
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'order_not_found'


def test_order_detail_items_sets_bonuses(client, db, make_user, make_order, make_product):
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=60.00, order_type='pre_order', payment_stages=3)
    p1 = make_product(name='Bluza', sale_price=Decimal('50.00'))
    gift = make_product(name='Gratis', sale_price=Decimal('0.00'))
    _add_item(db, o, product=p1, quantity=1, price=Decimal('50.00'))
    _add_item(db, o, product=gift, quantity=1, price=Decimal('0.00'), is_bonus=True)
    _add_item(db, o, product=None, quantity=1, price=Decimal('10.00'),
              is_full_set=True, custom_name='Set niespodzianka', set_number=1)
    r = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h)
    assert r.status_code == 200
    d = r.get_json()['data']
    assert d['id'] == o.id
    assert d['order_type'] == 'pre_order'
    assert 'status_display_name' in d and 'remaining_to_pay' in d
    assert len(d['items']) == 3
    bluza = next(i for i in d['items'] if i['name'] == 'Bluza')
    assert bluza['price'] == 5000 and bluza['total'] == 5000     # grosze
    assert bluza['is_bonus'] is False and bluza['is_full_set'] is False
    assert bluza['image_url'].startswith('http')                 # absolutny URL
    bonus = next(i for i in d['items'] if i['is_bonus'])
    assert bonus['name'] == 'Gratis'
    full_set = next(i for i in d['items'] if i['is_full_set'])
    assert full_set['name'] == 'Set niespodzianka' and full_set['set_number'] == 1


def test_order_detail_financial_summary_grosze(client, db, make_user, make_order, make_product):
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=100.00, order_type='on_hand', shipping_cost=Decimal('15.00'))
    p = make_product(sale_price=Decimal('100.00'))
    _add_item(db, o, product=p, quantity=1, price=Decimal('100.00'))
    d = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h).get_json()['data']
    assert d['total_amount'] == 10000          # E1, grosze
    assert d['shipping_cost'] == 1500          # E4
    assert d['total_to_pay'] == 11500          # on_hand: E1 100 + E4 15
    assert d['paid_amount'] == 0
    assert d['remaining_to_pay'] == 11500


def test_payment_stages_preorder_4(client, db, make_user, make_order):
    """Pre-order 4-etapowy: E1+E2+E3+E4 ze statusami i kwotami."""
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=4,
                   proxy_shipping_cost=Decimal('30.00'),
                   customs_vat_sale_cost=Decimal('20.00'),
                   shipping_cost=Decimal('15.00'))
    _add_payment(db, o, 'product', status='approved')
    _add_payment(db, o, 'korean_shipping', status='pending')
    d = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h).get_json()['data']
    by = {s['stage']: s for s in d['payment_stages']}
    assert set(by) == {'product', 'korean_shipping', 'customs_vat', 'domestic_shipping'}
    assert [s['stage_index'] for s in d['payment_stages']] == ['E1', 'E2', 'E3', 'E4']
    assert by['product']['status'] == 'approved'
    assert by['korean_shipping']['status'] == 'pending'
    assert by['customs_vat']['status'] == 'none'         # brak rekordu
    assert by['korean_shipping']['amount'] == 3000        # grosze
    assert by['domestic_shipping']['amount'] == 1500
    assert by['product']['has_proof'] is True             # _add_payment ma proof_file


def test_payment_stages_onhand_2(client, db, make_user, make_order):
    """On-hand: TYLKO 2 etapy E1+E4 (brak E2/E3)."""
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=80.00, order_type='on_hand', shipping_cost=Decimal('15.00'))
    d = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h).get_json()['data']
    assert {s['stage'] for s in d['payment_stages']} == {'product', 'domestic_shipping'}
    assert [s['stage_index'] for s in d['payment_stages']] == ['E1', 'E4']


def test_payment_stages_exclusive_3(client, db, make_user, make_order):
    """Exclusive 3-etapowy: E1+E3+E4 (brak E2 bo payment_stages != 4)."""
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=80.00, order_type='exclusive', payment_stages=3,
                   customs_vat_sale_cost=Decimal('20.00'), shipping_cost=Decimal('10.00'))
    d = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h).get_json()['data']
    assert {s['stage'] for s in d['payment_stages']} == {'product', 'customs_vat', 'domestic_shipping'}
    assert (by_customs := next(s for s in d['payment_stages'] if s['stage'] == 'customs_vat'))
    assert by_customs['amount'] == 2000                   # grosze
    assert by_customs['status'] == 'none'
    # każdy etap ma komplet pól kontraktu
    for s in d['payment_stages']:
        assert set(s) >= {'stage', 'stage_index', 'name', 'amount', 'status',
                          'can_upload', 'deadline', 'has_proof', 'rejection_reason'}


def test_payment_stage_rejected_reason(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=50.00, order_type='on_hand', shipping_cost=Decimal('10.00'))
    pc = _add_payment(db, o, 'domestic_shipping', status='rejected')
    pc.rejection_reason = 'Nieczytelny dowód'
    db.session.commit()
    d = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h).get_json()['data']
    e4 = next(s for s in d['payment_stages'] if s['stage'] == 'domestic_shipping')
    assert e4['status'] == 'rejected'
    assert e4['rejection_reason'] == 'Nieczytelny dowód'


def test_dashboard_requires_jwt(client, db, make_user):
    assert client.get('/api/mobile/v1/dashboard').status_code == 401


def test_dashboard_counts_and_recent(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    make_order(u, status='nowe')
    make_order(u, status='oczekujace')
    make_order(u, status='dostarczone')
    make_user()  # cudzy bez zamówień
    d = client.get('/api/mobile/v1/dashboard', headers=h).get_json()['data']
    assert d['orders'] == {'all': 3, 'in_progress': 2, 'delivered': 1, 'awaiting_shipping': 0}
    assert d['recent_orders_total'] == 3
    assert 'order_number' in d['recent_orders'][0] and 'total' in d['recent_orders'][0]
    assert len(d['chart']['labels']) == 31


def test_dashboard_to_pay_grosze(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    make_order(u, total_amount=100.00, order_type='on_hand', shipping_cost=Decimal('20.00'))
    d = client.get('/api/mobile/v1/dashboard', headers=h).get_json()['data']
    assert d['payment']['to_pay'] == 12000          # grosze (120 PLN)
    assert d['payment']['paid'] == 0
