"""Zaznaczanie „na wszystkich stronach" — endpoint z ID po aktywnych filtrach."""

URL = '/api/orders/shipping-requests/filtered-ids'


def _admin(make_user):
    return make_user(role='admin', email='admin@example.com', profile_completed=True)


def _sr(db, user, status='oplacone', **kwargs):
    from modules.orders.models import ShippingRequest
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id,
        status=status,
        **kwargs,
    )
    db.session.add(sr)
    db.session.commit()
    return sr


def _link_order(db, sr, order):
    from modules.orders.models import ShippingRequestOrder
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=order.id))
    db.session.commit()


def test_returns_all_ids_without_filters(client, db, make_user, login):
    login(_admin(make_user))
    user = make_user()
    a = _sr(db, user)
    b = _sr(db, user)

    data = client.get(URL).get_json()

    assert data['success'] is True
    ids = [r['id'] for r in data['requests']]
    assert a.id in ids and b.id in ids


def test_returns_client_id_for_merge_check(client, db, make_user, login):
    login(_admin(make_user))
    user = make_user()
    sr = _sr(db, user)

    data = client.get(URL).get_json()
    row = next(r for r in data['requests'] if r['id'] == sr.id)

    assert row['client_id'] == user.id


def test_status_filter_narrows_results(client, db, make_user, login):
    login(_admin(make_user))
    user = make_user()
    oplacone = _sr(db, user, status='oplacone')
    czeka = _sr(db, user, status='czeka_na_wycene')

    data = client.get(URL, query_string={'status': 'oplacone'}).get_json()
    ids = [r['id'] for r in data['requests']]

    assert oplacone.id in ids
    assert czeka.id not in ids


def test_search_filter_narrows_results(client, db, make_user, login):
    login(_admin(make_user))
    kowalski = make_user(first_name='Jan', last_name='Kowalski')
    nowak = make_user(first_name='Anna', last_name='Nowak')
    sr_kowalski = _sr(db, kowalski)
    sr_nowak = _sr(db, nowak)

    data = client.get(URL, query_string={'search': 'Kowalski'}).get_json()
    ids = [r['id'] for r in data['requests']]

    assert sr_kowalski.id in ids
    assert sr_nowak.id not in ids


def test_order_type_filter_narrows_results(client, db, make_user, make_order, login):
    login(_admin(make_user))
    user = make_user()
    exclusive_order = make_order(user, order_type='exclusive')
    onhand_order = make_order(user, order_type='on_hand')

    sr_exclusive = _sr(db, user)
    _link_order(db, sr_exclusive, exclusive_order)
    sr_onhand = _sr(db, user)
    _link_order(db, sr_onhand, onhand_order)

    data = client.get(URL, query_string={'order_type': 'exclusive'}).get_json()
    ids = [r['id'] for r in data['requests']]

    assert sr_exclusive.id in ids
    assert sr_onhand.id not in ids


def test_matches_what_the_list_shows(client, db, make_user, login):
    """Endpoint i lista muszą liczyć zlecenia tak samo — inaczej zaznaczenie
    obejmie coś, czego admin nie widzi."""
    login(_admin(make_user))
    user = make_user()
    for _ in range(3):
        _sr(db, user, status='oplacone')
    _sr(db, user, status='czeka_na_wycene')

    data = client.get(URL, query_string={'status': 'oplacone'}).get_json()
    page = client.get('/admin/orders/wms?tab=shipping&status=oplacone')

    assert page.status_code == 200
    assert len(data['requests']) == 3


def test_requires_admin(client, db, make_user, login):
    user = make_user()
    _sr(db, user)
    login(user)

    resp = client.get(URL)
    assert resp.status_code in (302, 403)
