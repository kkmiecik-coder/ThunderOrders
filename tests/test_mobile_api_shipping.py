"""Testy E7: mobilne API wysyłki (adresy CRUD + zlecenia). _auth jak w orders."""
import json
from decimal import Decimal


def _auth(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login', json={'email': u.email, 'password': 'Haslo123!'})
    return {'Authorization': f'Bearer {r.get_json()["data"]["access_token"]}'}, u


def _home(**over):
    d = {'address_type': 'home', 'shipping_name': 'Jan', 'shipping_address': 'Główna 1',
         'shipping_postal_code': '00-001', 'shipping_city': 'Warszawa'}
    d.update(over); return d


def test_addresses_requires_jwt(client, db, make_user):
    assert client.get('/api/mobile/v1/shipping/addresses').status_code == 401


def test_post_then_get_addresses(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/shipping/addresses', json=_home(is_default=True), headers=h)
    assert r.status_code == 201
    a = r.get_json()['data']['address']
    assert a['is_default'] is True and a['shipping_country'] == 'Polska'
    assert set(a) >= {'id', 'address_type', 'name', 'display_name', 'full_address', 'is_default',
                      'shipping_name', 'pickup_courier', 'created_at'}
    lst = client.get('/api/mobile/v1/shipping/addresses', headers=h).get_json()['data']['addresses']
    assert [x['id'] for x in lst] == [a['id']]


def test_post_address_bad_type(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/shipping/addresses', json={'address_type': 'office'}, headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_post_address_missing_field_details(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/shipping/addresses', json=_home(shipping_city=''), headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['details']['field'] == 'shipping_city'


def test_patch_default(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    a1 = client.post('/api/mobile/v1/shipping/addresses', json=_home(is_default=True),
                     headers=h).get_json()['data']['address']
    a2 = client.post('/api/mobile/v1/shipping/addresses', json=_home(shipping_city='Kraków'),
                     headers=h).get_json()['data']['address']
    r = client.patch(f'/api/mobile/v1/shipping/addresses/{a2["id"]}/default', headers=h)
    assert r.status_code == 200 and r.get_json()['data']['address']['is_default'] is True
    lst = client.get('/api/mobile/v1/shipping/addresses', headers=h).get_json()['data']['addresses']
    assert {x['id']: x['is_default'] for x in lst}[a1['id']] is False


def test_patch_default_foreign_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    h2, _ = _auth(client, db, make_user)
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h2
                    ).get_json()['data']['address']
    r = client.patch(f'/api/mobile/v1/shipping/addresses/{a["id"]}/default', headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'address_not_found'


def test_delete_soft(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h
                    ).get_json()['data']['address']
    assert client.delete(f'/api/mobile/v1/shipping/addresses/{a["id"]}', headers=h).status_code == 200
    assert client.get('/api/mobile/v1/shipping/addresses', headers=h
                      ).get_json()['data']['addresses'] == []
    # powtórny delete → 404
    assert client.delete(f'/api/mobile/v1/shipping/addresses/{a["id"]}', headers=h).status_code == 404


# ============================================================================
# Task 4 — ODCZYT zleceń (GET /requests, GET /requests/available-orders)
# ============================================================================

def _seed_status(db, slug='czeka_na_wycene', is_initial=True):
    from modules.orders.models import ShippingRequestStatus
    s = ShippingRequestStatus(slug=slug, name='Czeka na wycenę', is_active=True,
                              is_initial=is_initial, sort_order=0, badge_color='#6B7280')
    db.session.add(s); db.session.commit(); return s


def _allow(db, statuses=('dostarczone_gom',)):
    from modules.auth.models import Settings
    Settings.set_value('shipping_request_allowed_statuses', json.dumps(list(statuses)), type='json')


def test_available_orders_shape_and_grosze(client, db, make_user, make_order, make_product):
    from modules.orders.models import OrderItem
    h, u = _auth(client, db, make_user)
    _allow(db)
    o = make_order(u, status='dostarczone_gom', total_amount=Decimal('120.00'))
    p = make_product(sale_price=Decimal('60.00'))
    db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=2,
                             price=Decimal('60.00'), total=Decimal('120.00')))
    db.session.commit()
    r = client.get('/api/mobile/v1/shipping/requests/available-orders', headers=h)
    assert r.status_code == 200
    orders = r.get_json()['data']['orders']
    assert orders[0]['total_amount'] == 12000                 # grosze
    assert orders[0]['items'][0]['price'] == 6000


def test_requests_list_shape(client, db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request, create_address
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='dostarczone_gom')
    a = create_address(u, _home())[2]
    validate_and_create_request(u, [o.id], a.id)
    r = client.get('/api/mobile/v1/shipping/requests', headers=h)
    assert r.status_code == 200
    req = r.get_json()['data']['requests'][0]
    assert req['request_number'].startswith('WYS/')
    assert req['can_cancel'] is True and req['orders'][0]['id'] == o.id
    assert set(req) >= {'id', 'request_number', 'status', 'status_display_name',
                        'status_badge_color', 'address_type', 'short_address', 'full_address',
                        'total_shipping_cost', 'tracking_number', 'tracking_url', 'can_cancel',
                        'orders_count', 'orders', 'created_at'}


def test_requests_only_own(client, db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request, create_address
    h, u = _auth(client, db, make_user)
    h2, u2 = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o2 = make_order(u2, status='dostarczone_gom')
    validate_and_create_request(u2, [o2.id], create_address(u2, _home())[2].id)
    assert client.get('/api/mobile/v1/shipping/requests', headers=h
                      ).get_json()['data']['requests'] == []


# ============================================================================
# Task 5 — MUTACJE zleceń (POST /requests @idempotent, POST /requests/<id>/cancel)
# ============================================================================

def test_create_request_success(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='dostarczone_gom')
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h
                    ).get_json()['data']['address']
    r = client.post('/api/mobile/v1/shipping/requests',
                    json={'order_ids': [o.id], 'address_id': a['id']}, headers=h)
    assert r.status_code == 201
    body = r.get_json()['data']
    assert body['request_number'].startswith('WYS/') and 'request_id' in body
    # po utworzeniu zamówienie znika z available
    assert client.get('/api/mobile/v1/shipping/requests/available-orders', headers=h
                      ).get_json()['data']['orders'] == []


def test_create_request_empty_orders_400(client, db, make_user):
    h, u = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/shipping/requests',
                    json={'order_ids': [], 'address_id': 1}, headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'no_orders'


def test_create_request_foreign_order_404(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    other = make_user()
    _seed_status(db); _allow(db)
    foreign = make_order(other, status='dostarczone_gom')
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h
                    ).get_json()['data']['address']
    r = client.post('/api/mobile/v1/shipping/requests',
                    json={'order_ids': [foreign.id], 'address_id': a['id']}, headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'orders_not_found'
    assert foreign.id in r.get_json()['error']['details']['missing_order_ids']


def test_create_request_wrong_status_409(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='nowe')
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h
                    ).get_json()['data']['address']
    r = client.post('/api/mobile/v1/shipping/requests',
                    json={'order_ids': [o.id], 'address_id': a['id']}, headers=h)
    assert r.status_code == 409 and r.get_json()['error']['code'] == 'orders_not_available'


def test_create_request_bad_address_404(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='dostarczone_gom')
    r = client.post('/api/mobile/v1/shipping/requests',
                    json={'order_ids': [o.id], 'address_id': 99999}, headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'address_not_found'


def test_create_request_idempotency_key_replays(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='dostarczone_gom')
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h
                    ).get_json()['data']['address']
    hk = dict(h); hk['Idempotency-Key'] = 'e7-key-1'
    body = {'order_ids': [o.id], 'address_id': a['id']}
    r1 = client.post('/api/mobile/v1/shipping/requests', json=body, headers=hk)
    r2 = client.post('/api/mobile/v1/shipping/requests', json=body, headers=hk)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.get_json() == r2.get_json()                     # odtworzona odpowiedź, brak 2. zlecenia
    from modules.orders.models import ShippingRequest
    assert ShippingRequest.query.filter_by(user_id=u.id).count() == 1


def test_cancel_request(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='dostarczone_gom')
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h
                    ).get_json()['data']['address']
    rid = client.post('/api/mobile/v1/shipping/requests',
                      json={'order_ids': [o.id], 'address_id': a['id']}, headers=h
                      ).get_json()['data']['request_id']
    r = client.post(f'/api/mobile/v1/shipping/requests/{rid}/cancel', headers=h)
    assert r.status_code == 200 and r.get_json()['data']['cancelled'] is True
    # powtórny cancel → 404 (już usunięte)
    assert client.post(f'/api/mobile/v1/shipping/requests/{rid}/cancel',
                       headers=h).status_code == 404


def test_cancel_request_foreign_404(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    h2, u2 = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o2 = make_order(u2, status='dostarczone_gom')
    from modules.client.shipping_service import validate_and_create_request, create_address
    _, _, req = validate_and_create_request(u2, [o2.id], create_address(u2, _home())[2].id)
    r = client.post(f'/api/mobile/v1/shipping/requests/{req.id}/cancel', headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'request_not_found'


def test_cancel_blocked_after_quote_409(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='dostarczone_gom')
    from modules.client.shipping_service import validate_and_create_request, create_address
    _, _, req = validate_and_create_request(u, [o.id], create_address(u, _home())[2].id)
    req.total_shipping_cost = Decimal('25.00'); db.session.commit()
    r = client.post(f'/api/mobile/v1/shipping/requests/{req.id}/cancel', headers=h)
    assert r.status_code == 409 and r.get_json()['error']['code'] == 'cannot_cancel'
