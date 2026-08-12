"""shipped_at — moment wysyłki jako punkt odniesienia dla przypomnień i automatu."""
from datetime import datetime, timedelta


def _zlecenie(db, user, status='spakowane'):
    from modules.orders.models import ShippingRequest
    sr = ShippingRequest(
        request_number=f'WYS/{user.id:06d}', user_id=user.id, status=status)
    db.session.add(sr)
    db.session.commit()
    return sr


def test_wysylka_zapisuje_shipped_at(app, db, make_user):
    from modules.orders.wms_utils import ship_shipping_request

    user = make_user()
    sr = _zlecenie(db, user)

    przed = datetime.now() - timedelta(seconds=5)
    ship_shipping_request(sr, courier='inpost', tracking_number='123456789')

    assert sr.status == 'wyslane'
    assert sr.shipped_at is not None
    assert sr.shipped_at >= przed


def test_nowe_zlecenie_nie_ma_shipped_at(app, db, make_user):
    user = make_user()
    sr = _zlecenie(db, user)
    assert sr.shipped_at is None
    assert sr.delivered_at is None
    assert sr.delivered_source is None
    assert sr.delivery_reminder_sent_at is None


def test_backfill_bierze_date_z_logu_aktywnosci(app, db, make_user):
    from modules.admin.models import ActivityLog
    from modules.orders.delivery_backfill import odtworz_shipped_at

    user = make_user()
    sr = _zlecenie(db, user, status='wyslane')
    kiedy = datetime.now() - timedelta(days=20)
    db.session.add(ActivityLog(
        action='shipping_request_shipped', entity_type='shipping_request',
        entity_id=sr.id, created_at=kiedy))
    db.session.commit()

    wynik = odtworz_shipped_at()

    assert wynik['z_logu'] == 1
    assert abs((sr.shipped_at - kiedy).total_seconds()) < 1


def test_backfill_schodzi_na_date_przesylki(app, db, make_user, make_order):
    from modules.orders.models import OrderShipment, ShippingRequestOrder
    from modules.orders.delivery_backfill import odtworz_shipped_at

    user = make_user()
    sr = _zlecenie(db, user, status='wyslane')
    order = make_order(user, status='wyslane')
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=order.id))
    kiedy = datetime.now() - timedelta(days=15)
    db.session.add(OrderShipment(
        order_id=order.id, tracking_number='X1', courier='inpost', created_at=kiedy))
    db.session.commit()

    wynik = odtworz_shipped_at()

    assert wynik['z_przesylek'] == 1
    assert abs((sr.shipped_at - kiedy).total_seconds()) < 1


def test_backfill_nie_rusza_zlecen_nigdy_niewyslanych(app, db, make_user):
    from modules.orders.delivery_backfill import odtworz_shipped_at

    user = make_user()
    sr = _zlecenie(db, user, status='czeka_na_wycene')

    odtworz_shipped_at()

    assert sr.shipped_at is None


def test_backfill_jest_idempotentny(app, db, make_user):
    from modules.orders.delivery_backfill import odtworz_shipped_at

    user = make_user()
    sr = _zlecenie(db, user, status='wyslane')
    sr.updated_at = datetime.now() - timedelta(days=30)
    db.session.commit()

    pierwszy = odtworz_shipped_at()
    zapisana = sr.shipped_at
    drugi = odtworz_shipped_at()

    assert pierwszy['z_updated_at'] == 1
    assert sum(drugi.values()) == 0
    assert sr.shipped_at == zapisana
