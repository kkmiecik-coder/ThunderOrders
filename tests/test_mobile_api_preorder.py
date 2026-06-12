"""Testy E4: mobilne API pre-order (validate-cart + place-order-preorder).

Helper _auth skopiowany z tests/test_mobile_api_offers.py.
"""


def _auth(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': u.email, 'password': 'Haslo123!'})
    token = r.get_json()['data']['access_token']
    return {'Authorization': f'Bearer {token}'}, u


def _preorder_page(db, status='active', payment_stages=3):
    from modules.offers.models import OfferPage
    p = OfferPage(name=f'PO {status}', token=OfferPage.generate_token(), status=status,
                  page_type='preorder', payment_stages=payment_stages, created_by=1)
    db.session.add(p); db.session.commit()
    return p


def _exclusive_page(db, status='active'):
    from modules.offers.models import OfferPage
    p = OfferPage(name=f'EX {status}', token=OfferPage.generate_token(), status=status,
                  page_type='exclusive', payment_stages=4, created_by=1)
    db.session.add(p); db.session.commit()
    return p


def test_validate_cart_requires_token(client, db, make_user):
    page = _preorder_page(db)
    assert client.post(f'/api/mobile/v1/offers/{page.token}/validate-cart',
                       json={'cart_items': []}).status_code == 401


def test_validate_cart_filters_invalid_and_grosze(client, db, make_user, make_product):
    h, _ = _auth(client, db, make_user)
    page = _preorder_page(db)
    active = make_product(sale_price='50.00')
    inactive = make_product(sale_price='30.00'); inactive.is_active = False; db.session.commit()
    r = client.post(f'/api/mobile/v1/offers/{page.token}/validate-cart', headers=h,
                    json={'cart_items': [
                        {'product_id': active.id, 'quantity': 2},
                        {'product_id': inactive.id, 'quantity': 1},
                        {'product_id': 999999, 'quantity': 1},
                    ]})
    assert r.status_code == 200
    d = r.get_json()['data']
    assert [i['product_id'] for i in d['cart_items']] == [active.id]
    assert d['cart_items'][0]['price'] == 5000      # grosze
    assert d['cart_items'][0]['quantity'] == 2      # ilość zamawiana
    # D2(a): odrzucone raportowane
    removed = {x['product_id']: x['reason'] for x in d['removed']}
    assert removed.get(inactive.id) == 'inactive'
    assert removed.get(999999) == 'not_found'


def test_validate_cart_wrong_page_type(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    page = _exclusive_page(db)
    r = client.post(f'/api/mobile/v1/offers/{page.token}/validate-cart', headers=h,
                    json={'cart_items': []})
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'wrong_page_type'


def test_validate_cart_draft_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    page = _preorder_page(db, status='draft')
    r = client.post(f'/api/mobile/v1/offers/{page.token}/validate-cart', headers=h,
                    json={'cart_items': []})
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'page_not_found'


# ---------------------------------------------------------------------------
# Task 3: POST /offers/<token>/place-order-preorder (+ @idempotent)
# ---------------------------------------------------------------------------

def _po_order_type(db):
    from modules.orders.models import OrderType
    ot = OrderType.query.filter_by(slug='pre_order').first()
    if not ot:
        ot = OrderType(slug='pre_order', name='Pre-order', prefix='PO')
        db.session.add(ot); db.session.commit()
    return ot


def test_place_preorder_requires_token(client, db, make_user):
    page = _preorder_page(db)
    assert client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder',
                       json={'cart_items': []}).status_code == 401


def test_place_preorder_happy_path(client, db, make_user, make_product):
    h, _ = _auth(client, db, make_user)
    _po_order_type(db)
    page = _preorder_page(db, status='active', payment_stages=3)
    prod = make_product(sale_price='50.00')
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=h,
                    json={'cart_items': [{'product_id': prod.id, 'quantity': 2}],
                          'order_note': 'proszę szybko'})
    assert r.status_code == 201
    d = r.get_json()['data']
    assert d['order_number'].startswith('PO/')
    assert d['total'] == 10000          # grosze
    assert d['items_count'] == 2


def test_place_preorder_wrong_page_type_400(client, db, make_user, make_product):
    h, _ = _auth(client, db, make_user)
    _po_order_type(db)
    page = _exclusive_page(db, status='active')   # exclusive aktywny → wrong_page_type (przed is_active)
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=h,
                    json={'cart_items': [{'product_id': 1, 'quantity': 1}]})
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'wrong_page_type'


def test_place_preorder_page_not_active_403(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _po_order_type(db)
    page = _preorder_page(db, status='ended')
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=h,
                    json={'cart_items': [{'product_id': 1, 'quantity': 1}]})
    assert r.status_code == 403
    assert r.get_json()['error']['code'] == 'page_not_active'


def test_place_preorder_draft_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _po_order_type(db)
    page = _preorder_page(db, status='draft')
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=h,
                    json={'cart_items': [{'product_id': 1, 'quantity': 1}]})
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'page_not_found'


def test_place_preorder_empty_cart_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _po_order_type(db)
    page = _preorder_page(db, status='active')
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=h,
                    json={'cart_items': []})
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'empty_cart'


def test_place_preorder_idempotent_replay(client, db, make_user, make_product):
    # Bez guardu pre-order (D3a) drugi POST bez klucza tworzyłby drugie zamówienie —
    # dlatego dedup testujemy przez Idempotency-Key.
    h, _ = _auth(client, db, make_user)
    _po_order_type(db)
    page = _preorder_page(db, status='active')
    prod = make_product(sale_price='50.00')
    hk = {**h, 'Idempotency-Key': 'po-idem-123'}
    body = {'cart_items': [{'product_id': prod.id, 'quantity': 1}]}
    r1 = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=hk, json=body)
    assert r1.status_code == 201
    oid1 = r1.get_json()['data']['order_id']
    r2 = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=hk, json=body)
    assert r2.status_code == 201
    assert r2.get_json()['data']['order_id'] == oid1
    from modules.orders.models import Order
    assert Order.query.filter_by(order_type='pre_order').count() == 1
