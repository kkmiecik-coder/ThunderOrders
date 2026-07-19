"""Testy serwisu wysyłki (ekstrakcja z webowych tras shipping.py — parytet)."""
from decimal import Decimal


def _home(**over):
    d = {'address_type': 'home', 'shipping_name': 'Jan Kowalski',
         'shipping_address': 'Główna 1', 'shipping_postal_code': '00-001',
         'shipping_city': 'Warszawa'}
    d.update(over)
    return d


def _pickup(**over):
    d = {'address_type': 'pickup_point', 'pickup_courier': 'InPost',
         'pickup_point_id': 'WAW001', 'pickup_address': 'Kwiatowa 2',
         'pickup_postal_code': '00-002', 'pickup_city': 'Warszawa'}
    d.update(over)
    return d


def test_validate_ok_home_and_pickup(db):
    from modules.client.shipping_service import validate_address_payload
    assert validate_address_payload(_home()) == (True, None)
    assert validate_address_payload(_pickup()) == (True, None)


def test_validate_bad_type(db):
    from modules.client.shipping_service import validate_address_payload
    ok, err = validate_address_payload({'address_type': 'office'})
    assert not ok and err['code'] == 'invalid_address_type'


def test_validate_missing_home_field(db):
    from modules.client.shipping_service import validate_address_payload
    ok, err = validate_address_payload(_home(shipping_city=''))
    assert not ok and err['code'] == 'missing_field' and err['field'] == 'shipping_city'


def test_validate_missing_pickup_field(db):
    from modules.client.shipping_service import validate_address_payload
    ok, err = validate_address_payload(_pickup(pickup_point_id=None))
    assert not ok and err['code'] == 'missing_field' and err['field'] == 'pickup_point_id'


def test_create_address_defaults_country_and_flushes_default(db, make_user):
    from modules.client.shipping_service import create_address
    from modules.auth.models import ShippingAddress
    u = make_user()
    a1 = create_address(u, _home(is_default=True))[2]
    a2 = create_address(u, _home(shipping_city='Kraków', is_default=True))[2]
    db.session.refresh(a1)
    assert a2.is_default is True and a1.is_default is False     # clearing innych
    assert a2.shipping_country == 'Polska'                      # default kraju


def test_set_default_clears_others_and_owns(db, make_user):
    from modules.client.shipping_service import create_address, set_default_address
    u, other = make_user(), make_user()
    a1 = create_address(u, _home(is_default=True))[2]
    a2 = create_address(u, _home(shipping_city='Gdańsk'))[2]
    ok, err, addr = set_default_address(u.id, a2.id)
    db.session.refresh(a1)
    assert ok and addr.id == a2.id and a2.is_default and not a1.is_default
    # cudzy adres → not_found (maskowanie)
    ok2, err2, _ = set_default_address(other.id, a1.id)
    assert not ok2 and err2['code'] == 'not_found'


def test_soft_delete_marks_inactive_and_owns(db, make_user):
    from modules.client.shipping_service import create_address, soft_delete_address
    u, other = make_user(), make_user()
    a = create_address(u, _home())[2]
    ok, err = soft_delete_address(other.id, a.id)               # cudzy
    assert not ok and err['code'] == 'not_found'
    ok2, _ = soft_delete_address(u.id, a.id)
    db.session.refresh(a)
    assert ok2 and a.is_active is False
    # ponowny soft-delete nieaktywnego → not_found (filtr is_active)
    ok3, err3 = soft_delete_address(u.id, a.id)
    assert not ok3 and err3['code'] == 'not_found'


def test_list_active_sorted_default_first(db, make_user):
    from modules.client.shipping_service import create_address, list_active_addresses, soft_delete_address
    u = make_user()
    a1 = create_address(u, _home())[2]
    a2 = create_address(u, _home(shipping_city='Łódź', is_default=True))[2]
    dead = create_address(u, _home(shipping_city='Poznań'))[2]
    soft_delete_address(u.id, dead.id)
    out = list_active_addresses(u.id)
    assert [a.id for a in out] == [a2.id, a1.id]                # default first, dead pominięty


def test_web_address_add_route_parity_smoke(client, db, make_user, login):
    u = make_user(profile_completed=True); login(u)
    r = client.post('/client/shipping/addresses/add', json=_home(),
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert 'address_id' in r.get_json()


def test_web_address_add_missing_field_parity(client, db, make_user, login):
    u = make_user(profile_completed=True); login(u)
    r = client.post('/client/shipping/addresses/add', json=_home(shipping_city=''),
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400 and 'shipping_city' in r.get_json()['message']  # web message BEZ zmian


def test_web_address_set_default_and_delete_parity(client, db, make_user, login):
    from modules.client.shipping_service import create_address
    u = make_user(profile_completed=True); login(u)
    a = create_address(u, _home())[2]
    assert client.post(f'/client/shipping/addresses/{a.id}/set-default',
                       headers={'X-Requested-With': 'XMLHttpRequest'}).status_code == 200
    assert client.post(f'/client/shipping/addresses/{a.id}/delete',
                       headers={'X-Requested-With': 'XMLHttpRequest'}).status_code == 200


# ============================================================================
# Task 3 — serwis ZLECEŃ wysyłki (available-orders / create / cancel)
# ============================================================================

def _seed_status(db, slug='czeka_na_wycene', is_initial=True):
    from modules.orders.models import ShippingRequestStatus
    s = ShippingRequestStatus(slug=slug, name='Czeka na wycenę', is_active=True,
                              is_initial=is_initial, sort_order=0)
    db.session.add(s); db.session.commit()
    return s


def _allow(db, statuses=('dostarczone_gom',)):
    from modules.auth.models import Settings
    import json as _j
    Settings.set_value('shipping_request_allowed_statuses', _j.dumps(list(statuses)), type='json')


def test_get_available_orders_filters(db, make_user, make_order):
    from modules.client.shipping_service import get_available_orders, validate_and_create_request
    _seed_status(db); _allow(db)
    u = make_user()
    ok = make_order(u, status='dostarczone_gom')
    make_order(u, status='nowe')                               # zły status → poza
    out = get_available_orders(u.id)
    assert [o.id for o in out] == [ok.id]
    # po wpięciu w zlecenie znika z available
    validate_and_create_request(u, [ok.id], _addr(db, u).id)
    assert get_available_orders(u.id) == []


def _addr(db, user):
    from modules.client.shipping_service import create_address
    return create_address(user, {'address_type': 'home', 'shipping_name': 'J',
                                  'shipping_address': 'A 1', 'shipping_postal_code': '00-001',
                                  'shipping_city': 'W'})[2]


def test_create_request_snapshots_and_delivery_method(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom')
    a = _addr(db, u)
    ok, err, req = validate_and_create_request(u, [o.id], a.id)
    assert ok and req.request_number.startswith('WYS/')
    assert req.shipping_city == 'W' and req.address_type == 'home'   # snapshot
    db.session.refresh(o)
    assert o.delivery_method == 'kurier'                              # home → kurier


def test_create_request_foreign_order_404(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    _seed_status(db); _allow(db)
    u, other = make_user(), make_user()
    foreign = make_order(other, status='dostarczone_gom')
    ok, err, _ = validate_and_create_request(u, [foreign.id], _addr(db, u).id)
    assert not ok and err['code'] == 'orders_not_found' and foreign.id in err['missing_order_ids']


def test_create_request_wrong_status_409(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='nowe')                          # mój, ale zły status
    ok, err, _ = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert not ok and err['code'] == 'orders_not_available' and o.id in err['unavailable_order_ids']


def test_create_request_bad_address_404(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom')
    ok, err, _ = validate_and_create_request(u, [o.id], 99999)
    assert not ok and err['code'] == 'address_not_found'


def test_create_request_empty_inputs(db, make_user):
    from modules.client.shipping_service import validate_and_create_request
    u = make_user()
    assert validate_and_create_request(u, [], 1)[1]['code'] == 'no_orders'
    assert validate_and_create_request(u, [5], None)[1]['code'] == 'no_address'


def test_cancel_request_initial_only(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request, cancel_request
    from modules.orders.models import ShippingRequest
    _seed_status(db); _allow(db)
    u, other = make_user(), make_user()
    o = make_order(u, status='dostarczone_gom')
    _, _, req = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert cancel_request(other.id, req.id)[1]['code'] == 'not_found'      # cudzy
    ok, _ = cancel_request(u.id, req.id)
    assert ok and db.session.get(ShippingRequest, req.id) is None               # usunięte
    # zamówienie wraca do available
    from modules.client.shipping_service import get_available_orders
    assert [x.id for x in get_available_orders(u.id)] == [o.id]


def test_cancel_request_blocked_after_quote(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request, cancel_request
    from decimal import Decimal
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom')
    _, _, req = validate_and_create_request(u, [o.id], _addr(db, u).id)
    req.total_shipping_cost = Decimal('25.00'); db.session.commit()       # admin wycenił
    ok, err = cancel_request(u.id, req.id)
    assert not ok and err['code'] == 'cannot_cancel'


def test_web_request_create_and_cancel_parity(client, db, make_user, make_order, login):
    from modules.client.shipping_service import create_address
    _seed_status(db); _allow(db)
    u = make_user(profile_completed=True); login(u)
    o = make_order(u, status='dostarczone_gom')
    a = create_address(u, {'address_type': 'home', 'shipping_name': 'J', 'shipping_address': 'A 1',
                           'shipping_postal_code': '00-001', 'shipping_city': 'W'})[2]
    r = client.post('/client/shipping/requests/create',
                    json={'order_ids': [o.id], 'address_id': a.id},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert r.get_json()['request_number'].startswith('WYS/')


# ============================================================================
# Task 869e674fd — gate Cło/VAT (zlecenie wysyłki dopiero po opłaceniu podatku)
# ============================================================================

def _approve_customs_vat(db, order, amount=50):
    from modules.orders.models import PaymentConfirmation
    db.session.add(PaymentConfirmation(order_id=order.id, payment_stage='customs_vat',
                                       amount=amount, status='approved'))
    db.session.commit()


def test_create_request_blocked_when_customs_vat_unpaid(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom', order_type='exclusive',
                   customs_vat_sale_cost=50)                  # cło należne, nieopłacone
    ok, err, req = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert not ok and err['code'] == 'customs_vat_unpaid'
    assert o.id in err['customs_vat_unpaid_order_ids'] and req is None


def test_create_request_blocked_when_customs_vat_pending(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    from modules.orders.models import PaymentConfirmation
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom', order_type='exclusive', customs_vat_sale_cost=50)
    db.session.add(PaymentConfirmation(order_id=o.id, payment_stage='customs_vat',
                                       amount=50, status='pending'))  # wgrane, niezatwierdzone
    db.session.commit()
    ok, err, _ = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert not ok and err['code'] == 'customs_vat_unpaid'   # 'pending' nie wystarcza


def test_create_request_ok_when_customs_vat_approved(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom', order_type='exclusive', customs_vat_sale_cost=50)
    _approve_customs_vat(db, o)
    ok, err, req = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert ok and req is not None


def test_create_request_ok_when_no_customs_due(db, make_user, make_order):
    # on_hand (default) bez kwoty cła → gate nie dotyczy
    from modules.client.shipping_service import validate_and_create_request
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom')
    ok, err, req = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert ok and req is not None


def test_web_available_orders_expose_customs_vat_flag(client, db, make_user, make_order, login):
    _seed_status(db); _allow(db)
    u = make_user(profile_completed=True); login(u)
    paid = make_order(u, status='dostarczone_gom')            # on_hand → settled
    unpaid = make_order(u, status='dostarczone_gom', order_type='exclusive', customs_vat_sale_cost=50)
    r = client.get('/client/shipping/requests/available-orders')
    by_id = {o['id']: o for o in r.get_json()['orders']}
    assert by_id[paid.id]['customs_vat_paid'] is True
    assert by_id[unpaid.id]['customs_vat_paid'] is False


def test_web_request_create_customs_vat_unpaid_parity(client, db, make_user, make_order, login):
    _seed_status(db); _allow(db)
    u = make_user(profile_completed=True); login(u)
    o = make_order(u, status='dostarczone_gom', order_type='exclusive', customs_vat_sale_cost=50)
    a = _addr(db, u)
    r = client.post('/client/shipping/requests/create',
                    json={'order_ids': [o.id], 'address_id': a.id},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400 and r.get_json()['success'] is False
    assert 'Cło/VAT' in r.get_json()['error']


def test_web_request_create_foreign_rejected_parity(client, db, make_user, make_order, login):
    from modules.client.shipping_service import create_address
    _seed_status(db); _allow(db)
    u, other = make_user(profile_completed=True), make_user()
    login(u)
    foreign = make_order(other, status='dostarczone_gom')
    a = create_address(u, {'address_type': 'home', 'shipping_name': 'J', 'shipping_address': 'A 1',
                           'shipping_postal_code': '00-001', 'shipping_city': 'W'})[2]
    r = client.post('/client/shipping/requests/create',
                    json={'order_ids': [foreign.id], 'address_id': a.id},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400 and r.get_json()['success'] is False     # web: zbiorczy komunikat
