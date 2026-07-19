from modules.orders.models import ShippingRequest, ShippingRequestStatus
from modules.admin.routes import get_shipping_alert_counts


def _seed_status(db, slug, name):
    s = ShippingRequestStatus(slug=slug, name=name, is_active=True)
    db.session.add(s)
    return s


def _seed_request(db, number, status):
    r = ShippingRequest(request_number=number, status=status)
    db.session.add(r)
    return r


def test_shipping_alert_counts_by_status(app, db):
    for slug, name in [
        ('czeka_na_wycene', 'Czeka na wycenę'),
        ('czeka_na_oplacenie', 'Czeka na opłacenie'),
        ('oplacone', 'Opłacone'),
        ('spakowane', 'Spakowane'),
    ]:
        _seed_status(db, slug, name)
    db.session.commit()

    # 2x do wyceny, 1x czeka na opłacenie, 3x do spakowania, 5x spakowane (ignorowane)
    counts = {'czeka_na_wycene': 2, 'czeka_na_oplacenie': 1, 'oplacone': 3, 'spakowane': 5}
    n = 0
    for status, qty in counts.items():
        for _ in range(qty):
            n += 1
            _seed_request(db, f'WYS/{n:06d}', status)
    db.session.commit()

    result = get_shipping_alert_counts()

    assert result['to_quote'] == 2
    assert result['to_pay'] == 1
    assert result['to_pack'] == 3
    assert result['total'] == 6  # spakowane NIE wliczone
