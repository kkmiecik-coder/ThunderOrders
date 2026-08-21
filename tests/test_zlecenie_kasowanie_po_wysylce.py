"""Kasowanie zlecenia po wysyłce zabiera dane nieodtwarzalne (BUG 1.6).

Słownik statusów zlecenia nie ma statusu „anulowane", więc jedyna operacja
destrukcyjna to fizyczny DELETE. Ani kasowanie pojedyncze, ani zbiorcze nie
miało strażnika statusu dla ZWYKŁEGO zlecenia — `STATUSY_BEZ_EDYCJI`
sprawdzane było wyłącznie w gałęzi paczki zbiorczej.

Skasowanie dostarczonego zlecenia zabiera ze sobą numer przesyłki, `shipped_at`,
`delivered_at` oraz OPINIĘ O DOSTAWIE (`DeliveryReview`, cascade delete-orphan
plus FK `ondelete='CASCADE'`) — czyli dane, których nie da się odtworzyć,
a które zasilają statystyki dostaw.

Na produkcji (stan z 21 sierpnia): 10 opinii o dostawie i 39 zleceń
w statusach „wyslane"/„dostarczone".
"""

import pytest


def _seed_sr_statuses(db):
    from modules.orders.models import ShippingRequestStatus
    for i, (slug, name) in enumerate([
        ('czeka_na_wycene', 'Czeka na wycenę'),
        ('czeka_na_oplacenie', 'Czeka na opłacenie'),
        ('oplacone', 'Opłacone'),
        ('spakowane', 'Spakowane'),
        ('wyslane', 'Wysłane'),
        ('dostarczone', 'Dostarczone'),
    ]):
        if ShippingRequestStatus.query.filter_by(slug=slug).first():
            continue
        db.session.add(ShippingRequestStatus(
            slug=slug, name=name, sort_order=i, is_active=True,
            is_initial=(slug == 'czeka_na_wycene')))
    db.session.commit()


def _admin(make_user):
    return make_user(role='admin', email='admin-kasowanie@example.com',
                     profile_completed=True)


def _zlecenie(db, make_user, make_order, status):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    user = make_user()
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status=status, tracking_number='6200000000123')
    db.session.add(sr)
    db.session.flush()
    o = make_order(user=user, status='wyslane')
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
    db.session.commit()
    return sr, o


# ---------------------------------------------------------------------------
# Strażnik kasowania
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('status', ['wyslane', 'dostarczone'])
def test_delete_zlecenia_po_wysylce_odmawia(db, client, login, make_user, make_order, status):
    from modules.orders.models import ShippingRequest

    _seed_sr_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, status)
    sr_id = sr.id
    login(_admin(make_user))

    r = client.delete(f'/admin/orders/shipping-requests/{sr_id}')

    assert r.status_code == 409, r.get_json()
    assert db.session.get(ShippingRequest, sr_id) is not None, (
        'Zlecenie znikło razem z trackingiem, datami i opinią o dostawie'
    )


def test_delete_zlecenia_przed_wysylka_nadal_dziala(db, client, login, make_user, make_order):
    """Regresja: normalna ścieżka kasowania pomyłkowego zlecenia zostaje."""
    from modules.orders.models import ShippingRequest

    _seed_sr_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, 'czeka_na_wycene')
    sr_id = sr.id
    login(_admin(make_user))

    r = client.delete(f'/admin/orders/shipping-requests/{sr_id}')

    assert r.status_code == 200, r.get_json()
    assert db.session.get(ShippingRequest, sr_id) is None


def test_bulk_cancel_pomija_zlecenia_po_wysylce(db, client, login, make_user, make_order):
    """Kasowanie zbiorcze ma tę samą bramkę — zaznaczenie „wszystkie na
    wszystkich stronach" nie może wyczyścić historii wysyłek."""
    from modules.orders.models import ShippingRequest

    _seed_sr_statuses(db)
    swieze, _o1 = _zlecenie(db, make_user, make_order, 'czeka_na_wycene')
    wyslane, _o2 = _zlecenie(db, make_user, make_order, 'wyslane')
    swieze_id, wyslane_id = swieze.id, wyslane.id
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/bulk-cancel',
                    json={'ids': [swieze_id, wyslane_id]})

    assert r.status_code == 200, r.get_json()
    assert db.session.get(ShippingRequest, swieze_id) is None
    assert db.session.get(ShippingRequest, wyslane_id) is not None, (
        'Zlecenie po wysyłce musi przetrwać kasowanie zbiorcze'
    )


def test_delete_zlecenia_z_opinia_odmawia(db, client, login, make_user, make_order):
    """Opinia o dostawie jest nieodtwarzalna i zasila statystyki."""
    from modules.orders.models import ShippingRequest
    from modules.orders.review_models import DeliveryReview

    _seed_sr_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, 'dostarczone')
    db.session.add(DeliveryReview(
        shipping_request_id=sr.id, user_id=sr.user_id, rating=5))
    db.session.commit()
    sr_id = sr.id
    login(_admin(make_user))

    r = client.delete(f'/admin/orders/shipping-requests/{sr_id}')

    assert r.status_code == 409
    assert db.session.get(ShippingRequest, sr_id) is not None
    assert DeliveryReview.query.filter_by(shipping_request_id=sr_id).count() == 1


# ---------------------------------------------------------------------------
# Cofnięcie wysyłki — wyjście ze ślepej uliczki
#
# Strażnik wyżej zabiera jedyną dotychczasową drogę naprawy pomyłkowej wysyłki
# (skasowanie zlecenia), więc musi ją zastąpić operacja odwracalna. Cofamy
# WYŁĄCZNIE ze statusu „wyslane": „dostarczone" oznacza, że paczka dotarła do
# klienta, a istniejąca opinia to dowód, że ją odebrał.
# ---------------------------------------------------------------------------

URL_COFNIJ = '/admin/orders/shipping-requests/{}/unship'


def test_cofniecie_wysylki_czysci_slady_nadania(db, client, login, make_user, make_order):
    from modules.orders.models import OrderShipment

    _seed_sr_statuses(db)
    sr, zamowienie = _zlecenie(db, make_user, make_order, 'wyslane')
    from modules.orders.models import get_local_now
    sr.shipped_at = get_local_now()
    db.session.add(OrderShipment(
        order_id=zamowienie.id, tracking_number=sr.tracking_number, courier='inpost'))
    db.session.commit()
    sr_id = sr.id
    login(_admin(make_user))

    r = client.post(URL_COFNIJ.format(sr_id))

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert sr.status == 'spakowane', 'Zlecenie wraca do stanu sprzed nadania'
    assert sr.shipped_at is None, 'Bez tego cron dostaw liczyłby czas od fałszywej daty'
    assert sr.tracking_number is None
    assert zamowienie.status == 'spakowane'
    assert OrderShipment.query.filter_by(order_id=zamowienie.id).count() == 0, (
        'Wpis przesyłki to ślad nadania — po cofnięciu nie ma go czego dotyczyć'
    )


def test_cofniecie_odmawia_dla_dostarczonego(db, client, login, make_user, make_order):
    """Paczka u klienta — cofnięcie byłoby kłamstwem wobec jego historii."""
    _seed_sr_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, 'dostarczone')
    sr_id = sr.id
    login(_admin(make_user))

    r = client.post(URL_COFNIJ.format(sr_id))

    assert r.status_code == 409, r.get_json()
    db.session.expire_all()
    assert sr.status == 'dostarczone'


def test_cofniecie_odmawia_gdy_jest_opinia(db, client, login, make_user, make_order):
    """Opinia to dowód, że klient paczkę odebrał."""
    from modules.orders.review_models import DeliveryReview

    _seed_sr_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, 'wyslane')
    db.session.add(DeliveryReview(
        shipping_request_id=sr.id, user_id=sr.user_id, rating=5))
    db.session.commit()
    sr_id = sr.id
    login(_admin(make_user))

    r = client.post(URL_COFNIJ.format(sr_id))

    assert r.status_code == 409, r.get_json()
    db.session.expire_all()
    assert sr.status == 'wyslane'


def test_cofniecie_odmawia_dla_niewyslanego(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, 'spakowane')
    sr_id = sr.id
    login(_admin(make_user))

    r = client.post(URL_COFNIJ.format(sr_id))

    assert r.status_code == 409


def test_cofniecie_wymaga_admina(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, 'wyslane')
    login(make_user())

    r = client.post(URL_COFNIJ.format(sr.id))

    assert r.status_code in (302, 403)


def test_po_cofnieciu_mozna_skasowac(db, client, login, make_user, make_order):
    """Sedno: cofnięcie przywraca możliwość naprawy pomyłki."""
    from modules.orders.models import ShippingRequest

    _seed_sr_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, 'wyslane')
    sr_id = sr.id
    login(_admin(make_user))

    assert client.post(URL_COFNIJ.format(sr_id)).status_code == 200
    r = client.delete(f'/admin/orders/shipping-requests/{sr_id}')

    assert r.status_code == 200, r.get_json()
    assert db.session.get(ShippingRequest, sr_id) is None
