"""Konsolidacja zleceń wysyłki wielu klientów: model, serwis i propagacja statusów."""
import pytest


def _seed_sr_statuses(db):
    """Statusy zleceń wysyłki w kolejności łańcucha — sort_order decyduje o „najmniej zaawansowanym"."""
    from modules.orders.models import ShippingRequestStatus
    for i, (slug, name) in enumerate([
        ('czeka_na_wycene', 'Czeka na wycenę'),
        ('czeka_na_oplacenie', 'Czeka na opłacenie'),
        ('oplacone', 'Opłacone'),
        ('spakowane', 'Spakowane'),
        ('wyslane', 'Wysłane'),
        ('dostarczone', 'Dostarczone'),
    ]):
        db.session.add(ShippingRequestStatus(
            slug=slug, name=name, sort_order=i,
            is_active=True, is_initial=(slug == 'czeka_na_wycene'),
        ))
    db.session.commit()


def _sr(db, user, make_order, status='oplacone', orders_count=1):
    """Zlecenie wysyłki z zamówieniami danego klienta."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status=status, address_type='home',
        shipping_name=f'{user.first_name} {user.last_name}',
        shipping_address='ul. Kwiatowa 12', shipping_postal_code='30-001',
        shipping_city='Kraków',
    )
    db.session.add(sr)
    db.session.flush()
    orders = []
    for _ in range(orders_count):
        o = make_order(user)
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
        orders.append(o)
    db.session.commit()
    return sr, orders


def test_konsolidacja_ma_relacje_do_zrodel(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)

    from modules.orders.models import ShippingRequest
    zbiorcze = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=a.id, status='oplacone', address_type='home',
    )
    db.session.add(zbiorcze)
    db.session.flush()
    sr_a.consolidated_into_id = zbiorcze.id
    sr_b.consolidated_into_id = zbiorcze.id
    zbiorcze.lead_source_request_id = sr_a.id
    db.session.commit()

    assert {s.id for s in zbiorcze.consolidated_sources} == {sr_a.id, sr_b.id}
    assert zbiorcze.lead_source.id == sr_a.id
    assert sr_b.consolidated_into.id == zbiorcze.id
