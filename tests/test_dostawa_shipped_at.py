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


def test_backfill_wielu_kandydatow_nie_miesza_zrodel(app, db, make_user, make_order):
    """Dług #6 (G4-cron): backfill robił dwa zapytania NA ZLECENIE (log +
    przesyłka) zamiast zbiorczych. Po przejściu na GROUP BY/MIN kluczowe jest, żeby
    wynik per zlecenie dalej trafiał do WŁAŚCIWEGO wiersza — trzej kandydaci, każdy
    z innego źródła kaskady, muszą dostać każdy SWOJĄ datę, nie datę sąsiada."""
    from modules.admin.models import ActivityLog
    from modules.orders.models import OrderShipment, ShippingRequestOrder, ShippingRequest
    from modules.orders.delivery_backfill import odtworz_shipped_at

    user_a, user_b, user_c = make_user(), make_user(), make_user()

    sr_log = ShippingRequest(request_number='WYS/000601', user_id=user_a.id, status='wyslane')
    sr_przesylka = ShippingRequest(request_number='WYS/000602', user_id=user_b.id, status='wyslane')
    sr_updated = ShippingRequest(request_number='WYS/000603', user_id=user_c.id, status='wyslane')
    db.session.add_all([sr_log, sr_przesylka, sr_updated])
    db.session.commit()

    kiedy_log = datetime.now() - timedelta(days=25)
    db.session.add(ActivityLog(
        action='shipping_request_shipped', entity_type='shipping_request',
        entity_id=sr_log.id, created_at=kiedy_log))

    order = make_order(user_b, status='wyslane')
    db.session.add(ShippingRequestOrder(shipping_request_id=sr_przesylka.id, order_id=order.id))
    kiedy_przesylka = datetime.now() - timedelta(days=18)
    db.session.add(OrderShipment(
        order_id=order.id, tracking_number='X9', courier='inpost', created_at=kiedy_przesylka))
    db.session.commit()

    kiedy_updated = datetime.now() - timedelta(days=12)
    sr_updated.updated_at = kiedy_updated
    db.session.commit()

    wynik = odtworz_shipped_at()

    # sr_updated.updated_at NIE nadaje się tu jako punkt odniesienia po fakcie:
    # backfill sam robi UPDATE na tym wierszu (ustawia shipped_at), więc kolumna z
    # onupdate=get_local_now przestawia się na „teraz" przy TYM SAMYM commicie —
    # porównujemy więc do wartości złapanej PRZED wywołaniem odtworz_shipped_at().
    assert wynik == {'z_logu': 1, 'z_przesylek': 1, 'z_updated_at': 1}
    assert abs((sr_log.shipped_at - kiedy_log).total_seconds()) < 1
    assert abs((sr_przesylka.shipped_at - kiedy_przesylka).total_seconds()) < 1
    assert abs((sr_updated.shipped_at - kiedy_updated).total_seconds()) < 1
