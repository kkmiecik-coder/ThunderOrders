"""Scalony modal zlecenia wysyłki: jeden markup na obu stronach."""


def _admin(make_user):
    return make_user(role='admin', email='admin@example.com', profile_completed=True)


def _sr_with_order(db, make_user, make_order):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    u = make_user()
    o = make_order(u, status='dostarczone_gom')
    sr = ShippingRequest(request_number=ShippingRequest.generate_request_number(),
                         user_id=u.id, status='czeka_na_wycene')
    db.session.add(sr)
    db.session.commit()
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
    db.session.commit()
    return sr, o


def test_wms_renders_merged_modal_without_bulk_modal(client, db, make_user, make_order, login):
    login(_admin(make_user))
    _sr_with_order(db, make_user, make_order)
    resp = client.get('/admin/orders/wms?tab=shipping')
    assert resp.status_code == 200
    assert b'id="editShippingRequestModal"' in resp.data
    assert b'id="srModalList"' in resp.data
    assert b'id="srBulkBar"' in resp.data
    assert b'id="bulkCostModal"' not in resp.data


def test_wms_bulk_button_relabeled(client, db, make_user, make_order, login):
    login(_admin(make_user))
    _sr_with_order(db, make_user, make_order)
    resp = client.get('/admin/orders/wms?tab=shipping')
    assert 'Koszty i gabaryt'.encode() in resp.data


def test_order_detail_uses_same_modal_partial(client, db, make_user, make_order, login):
    login(_admin(make_user))
    _sr, order = _sr_with_order(db, make_user, make_order)
    resp = client.get(f'/admin/orders/{order.id}')
    assert resp.status_code == 200
    assert b'id="editShippingRequestModal"' in resp.data
    assert b'id="srModalDetail"' in resp.data
    # gniazda, których stara kopia w detail.html nie miała:
    assert b'id="srBulkParcelSize"' in resp.data
    assert b'id="srModalList"' in resp.data


def test_modal_partial_included_once_per_page(client, db, make_user, make_order, login):
    login(_admin(make_user))
    _sr_with_order(db, make_user, make_order)
    resp = client.get('/admin/orders/wms?tab=shipping')
    assert resp.data.count(b'id="editShippingRequestModal"') == 1
