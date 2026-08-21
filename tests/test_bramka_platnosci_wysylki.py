"""Nieopłacona paczka nie wyjeżdża — bramka liczona z danych (BUG 1.1).

`update_sr_after_packing` podnosi zlecenie na „spakowane" na podstawie samych
statusów zamówień — nie sprawdzając płatności. Żadne ogniwo wcześniej też jej
nie sprawdza: wejście do sesji WMS patrzy tylko na `Order.status`, a przycisk
„Zabierz do WMS" renderuje się dla każdego statusu poza wysłanym.

Jedyna bramka finansowa była sprawdzana DOPIERO przy wysyłce i opierała się na
STATUSIE zlecenia (`UNPAID_SR_STATUSES`). „spakowane" do tego zbioru nie należy,
więc pakowanie skutecznie kasowało informację „nieopłacone" i paczka wyjeżdżała
bez opłaty E4 — klient dostawał maila o nadaniu, a ślad po nierozliczonym etapie
znikał.

Naprawa liczy bramkę z DANYCH (`is_domestic_shipping_settled` na aktywnych
zamówieniach), a nie ze statusu zlecenia. Dzięki temu jest odporna na każdą
ścieżkę zapisu statusu — także tę, która dopiero powstanie.
"""

from decimal import Decimal

import pytest


def _seed_statuses(db):
    from modules.orders.models import OrderStatus, ShippingRequestStatus
    for i, (slug, name) in enumerate([
        ('czeka_na_wycene', 'Czeka na wycenę'),
        ('czeka_na_oplacenie', 'Czeka na opłacenie'),
        ('oplacone', 'Opłacone'),
        ('spakowane', 'Spakowane'),
        ('wyslane', 'Wysłane'),
        ('dostarczone', 'Dostarczone'),
    ]):
        if not ShippingRequestStatus.query.filter_by(slug=slug).first():
            db.session.add(ShippingRequestStatus(
                slug=slug, name=name, sort_order=i, is_active=True,
                is_initial=(slug == 'czeka_na_wycene')))
    for slug, name in [('dostarczone_gom', 'Dostarczone GOM'),
                       ('spakowane', 'Spakowane'), ('wyslane', 'Wysłane'),
                       ('anulowane', 'Anulowane')]:
        if not OrderStatus.query.filter_by(slug=slug).first():
            db.session.add(OrderStatus(slug=slug, name=name, is_active=True))
    db.session.commit()


def _zlecenie(db, make_user, make_order, koszty, status_sr='spakowane',
              status_zam='spakowane'):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    user = make_user()
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status=status_sr)
    db.session.add(sr)
    db.session.flush()
    zamowienia = []
    for koszt in koszty:
        o = make_order(user=user, status=status_zam)
        o.shipping_cost = Decimal(str(koszt))
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
        zamowienia.append(o)
    db.session.commit()
    return sr, zamowienia


def _zatwierdz_e4(db, order, kwota):
    from modules.orders.models import PaymentConfirmation
    db.session.add(PaymentConfirmation(
        order_id=order.id, payment_stage='domestic_shipping',
        amount=Decimal(str(kwota)), status='approved'))
    order.paid_amount = (order.paid_amount or Decimal('0.00')) + Decimal(str(kwota))
    db.session.commit()


# ---------------------------------------------------------------------------
# Odmowa wysyłki nieopłaconego zlecenia
# ---------------------------------------------------------------------------

def test_spakowane_ale_nieoplacone_nie_wyjezdza(db, make_user, make_order):
    """Sedno BUG 1.1: pakowanie nie może kasować informacji „nieopłacone"."""
    from modules.orders.wms_utils import ShippingRequestUnpaid, ship_shipping_request

    _seed_statuses(db)
    sr, _z = _zlecenie(db, make_user, make_order, koszty=[25])

    with pytest.raises(ShippingRequestUnpaid) as e:
        ship_shipping_request(sr, courier='inpost', tracking_number='NIEOPL1')

    assert sr.request_number in str(e.value)
    assert sr.status == 'spakowane', 'Odmowa nie może zmienić stanu zlecenia'
    assert sr.shipped_at is None


def test_spakowane_z_niedoplata_nie_wyjezdza(db, make_user, make_order):
    """Częściowa wpłata to nadal niedopłata — parytet z rozliczeniem kwotowym."""
    from modules.orders.wms_utils import ShippingRequestUnpaid, ship_shipping_request

    _seed_statuses(db)
    sr, (zamowienie,) = _zlecenie(db, make_user, make_order, koszty=[30])
    _zatwierdz_e4(db, zamowienie, 20)

    with pytest.raises(ShippingRequestUnpaid):
        ship_shipping_request(sr, courier='inpost', tracking_number='NIEDOPL1')


def test_jedno_nieoplacone_zamowienie_wstrzymuje_cala_paczke(db, make_user, make_order):
    from modules.orders.wms_utils import ShippingRequestUnpaid, ship_shipping_request

    _seed_statuses(db)
    sr, (a, b) = _zlecenie(db, make_user, make_order, koszty=[25, 15])
    _zatwierdz_e4(db, a, 25)

    with pytest.raises(ShippingRequestUnpaid):
        ship_shipping_request(sr, courier='inpost', tracking_number='CZESC1')


# ---------------------------------------------------------------------------
# Regresje — bramka nie może zablokować legalnej wysyłki
# ---------------------------------------------------------------------------

def test_oplacone_zlecenie_wyjezdza(db, make_user, make_order):
    from modules.orders.wms_utils import ship_shipping_request

    _seed_statuses(db)
    sr, (zamowienie,) = _zlecenie(db, make_user, make_order, koszty=[25])
    _zatwierdz_e4(db, zamowienie, 25)

    ship_shipping_request(sr, courier='inpost', tracking_number='OPL1')

    assert sr.status == 'wyslane'
    assert sr.shipped_at is not None


def test_zlecenie_bez_naleznosci_wyjezdza(db, make_user, make_order):
    """0 zł = nie ma czego płacić (parytet z is_domestic_shipping_settled)."""
    from modules.orders.wms_utils import ship_shipping_request

    _seed_statuses(db)
    sr, _z = _zlecenie(db, make_user, make_order, koszty=[0])

    ship_shipping_request(sr, courier='inpost', tracking_number='GRATIS1')

    assert sr.status == 'wyslane'


def test_anulowane_zamowienie_nie_wstrzymuje_wysylki(db, make_user, make_order):
    """Bramka liczy po zamówieniach AKTYWNYCH — anulowane nie jedzie w kartonie."""
    from modules.orders.wms_utils import ship_shipping_request

    _seed_statuses(db)
    sr, (zywe, martwe) = _zlecenie(db, make_user, make_order, koszty=[25, 40])
    _zatwierdz_e4(db, zywe, 25)
    martwe.status = 'anulowane'
    db.session.commit()

    ship_shipping_request(sr, courier='inpost', tracking_number='ANUL1')

    assert sr.status == 'wyslane'


def test_zlecenie_bez_zamowien_nie_wyjezdza(db, make_user, make_order):
    """Pusty zbiór aktywnych nie może przejść przez `all()` jako komplet."""
    from modules.orders.wms_utils import ShippingRequestUnpaid, ship_shipping_request

    _seed_statuses(db)
    sr, _z = _zlecenie(db, make_user, make_order, koszty=[])

    with pytest.raises(ShippingRequestUnpaid):
        ship_shipping_request(sr, courier='inpost', tracking_number='PUSTE1')


# ---------------------------------------------------------------------------
# Cofnięcie do WMS nie stempluje statusu „opłacone" (BUG 1.2)
#
# `reopen_orders_for_wms` zakładało, że do „spakowane" można było dojść WYŁĄCZNIE
# z „opłacone", i przy cofaniu przypisywało ten status na sztywno. W połączeniu
# z BUG 1.1 (pakowanie nie sprawdzało płatności) dawało to AWANS W GÓRĘ:
# zlecenie, które weszło do WMS jako „czeka na opłacenie", wychodziło jako
# „opłacone" — a ten stan jest już nieodwracalny automatem, bo
# `_check_sr_auto_oplacone` wchodzi wyłącznie z „czeka na opłacenie".
# ---------------------------------------------------------------------------

def test_cofniecie_do_wms_nie_awansuje_nieoplaconego(db, make_user, make_order):
    from modules.orders.wms_utils import reopen_orders_for_wms

    _seed_statuses(db)
    sr, zamowienia = _zlecenie(db, make_user, make_order, koszty=[25])

    reopen_orders_for_wms(zamowienia, 'repack', [sr])

    assert sr.status == 'czeka_na_oplacenie', (
        f'Zlecenie nieopłacone wyszło z WMS jako „{sr.status}" — ten stan jest '
        f'nieodwracalny automatem i fałszywie mówi, że klient zapłacił'
    )


def test_cofniecie_do_wms_zachowuje_oplacone(db, make_user, make_order):
    """Regresja: realnie opłacone zlecenie wraca jako „opłacone"."""
    from modules.orders.wms_utils import reopen_orders_for_wms

    _seed_statuses(db)
    sr, (zamowienie,) = _zlecenie(db, make_user, make_order, koszty=[25])
    _zatwierdz_e4(db, zamowienie, 25)

    reopen_orders_for_wms([zamowienie], 'repack', [sr])

    assert sr.status == 'oplacone'


def test_cofniecie_do_wms_bez_naleznosci_daje_oplacone(db, make_user, make_order):
    """0 zł = rozliczone, więc zlecenie wraca jako gotowe do wysyłki."""
    from modules.orders.wms_utils import reopen_orders_for_wms

    _seed_statuses(db)
    sr, (zamowienie,) = _zlecenie(db, make_user, make_order, koszty=[0])

    reopen_orders_for_wms([zamowienie], 'repack', [sr])

    assert sr.status == 'oplacone'
