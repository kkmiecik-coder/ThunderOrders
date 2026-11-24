"""Serwis przepisywania zamówienia na inną klientkę (modules/orders/transfer.py).

Spec: docs/superpowers/specs/2026-11-24-przepisz-zamowienie-design.md
"""
from decimal import Decimal

import pytest

from tests.przepisanie_helpers import T0, przydzial_gift_card, zamowienie_klientki


@pytest.fixture(autouse=True)
def _strona(strona_sprzedazy):
    """Zamówienia powstają z offer_page_id=1 (FK)."""


@pytest.fixture
def admin(make_user):
    return make_user(role='admin', email='admin@example.com')


@pytest.fixture
def ania(make_user):
    return make_user(email='ania@example.com', first_name='Ania', last_name='Nowak')


@pytest.fixture
def basia(make_user):
    return make_user(email='basia@example.com', first_name='Basia', last_name='Kowal')


def _potwierdzenie(db, order, etap, kwota, status='approved', plik=None):
    from modules.orders.models import PaymentConfirmation
    conf = PaymentConfirmation(order_id=order.id, payment_stage=etap, amount=Decimal(str(kwota)),
                               status=status, proof_file=plik)
    db.session.add(conf)
    db.session.commit()
    return conf


# ---------------------------------------------------------------- całe zamówienie

def test_cale_zmienia_klientke(db, make_product, make_order, ania, basia, admin):
    from modules.orders.transfer import przepisz_cale_zamowienie

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 2, 30)], user=ania, paid_amount=60)
    numer, data = a.order_number, a.created_at

    wynik = przepisz_cale_zamowienie(a, basia, admin)
    db.session.commit()

    assert wynik.cale is True and wynik.cel is a and wynik.zrodlo is a
    assert a.user_id == basia.id
    assert a.order_number == numer and a.created_at == data
    assert a.paid_amount == Decimal('60')


def test_cale_czysci_dane_poprzedniej(db, make_product, make_order, ania, basia, admin):
    from modules.orders.transfer import przepisz_cale_zamowienie

    p = make_product()
    a = zamowienie_klientki(
        db, None, make_order, [(p.id, 1, 30)], user=ania,
        shipping_name='Ania Nowak', shipping_address='Lipowa 1', shipping_postal_code='00-001',
        shipping_city='Warszawa', pickup_courier='InPost', pickup_point_id='WAW1',
        pickup_address='Punkt 1', pickup_postal_code='00-002', pickup_city='Warszawa',
        delivery_method='paczkomat', custom_name='Moje karty', notes='Proszę o folię',
        admin_notes='VIP')

    przepisz_cale_zamowienie(a, basia, admin)
    db.session.commit()

    for pole in ('shipping_name', 'shipping_address', 'shipping_postal_code', 'shipping_city',
                 'pickup_courier', 'pickup_point_id', 'pickup_address', 'pickup_postal_code',
                 'pickup_city', 'delivery_method', 'custom_name', 'notes'):
        assert getattr(a, pole) is None, pole
    assert 'VIP' in a.admin_notes
    assert 'Notatka poprzedniej klientki: Proszę o folię' in a.admin_notes


def test_cale_ukrywa_dowody(db, make_product, make_order, ania, basia, admin):
    from modules.orders.transfer import przepisz_cale_zamowienie

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 1, 30)], user=ania)
    z_plikiem = _potwierdzenie(db, a, 'product', 30, plik='ania.png')
    bez_pliku = _potwierdzenie(db, a, 'customs_vat', 5)

    przepisz_cale_zamowienie(a, basia, admin)
    db.session.commit()

    assert z_plikiem.proof_hidden_for_client is True
    assert bez_pliku.proof_hidden_for_client is False


def test_cale_przenosi_gift_assignments(db, make_product, make_order, strona_sprzedazy,
                                        ania, basia, admin):
    from modules.orders.models import OrderItem
    from modules.orders.transfer import przepisz_cale_zamowienie

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 1, 30)], user=ania)
    item = OrderItem.query.filter_by(order_id=a.id).one()
    przydzial = przydzial_gift_card(db, make_product, strona_sprzedazy, ania, item)

    przepisz_cale_zamowienie(a, basia, admin)
    db.session.commit()

    assert przydzial.user_id == basia.id


def test_cale_dodaje_komentarz_wewnetrzny(db, make_product, make_order, ania, basia, admin):
    from modules.orders.models import OrderComment
    from modules.orders.transfer import przepisz_cale_zamowienie

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 1, 30)], user=ania)

    przepisz_cale_zamowienie(a, basia, admin)
    db.session.commit()

    komentarze = OrderComment.query.filter_by(order_id=a.id).all()
    assert len(komentarze) == 1
    assert komentarze[0].is_internal is True and komentarze[0].user_id == admin.id
    assert 'ania@example.com' in komentarze[0].comment
    assert 'basia@example.com' in komentarze[0].comment


# ---------------------------------------------------------------- blokady

@pytest.mark.parametrize('status', ['anulowane', 'do_zwrotu', 'zwrocone', 'czesciowo_zwrocone',
                                    'wyslane', 'dostarczone'])
def test_blokada_statusu(db, make_product, make_order, ania, basia, admin, status):
    from modules.orders.transfer import TransferError, przepisz_cale_zamowienie, sprawdz_blokady

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 1, 30)], user=ania, status=status)

    assert sprawdz_blokady(a)
    with pytest.raises(TransferError):
        przepisz_cale_zamowienie(a, basia, admin)
    assert a.user_id == ania.id


def test_blokada_zlecenia_wysylki(db, make_product, make_order, ania, basia, admin):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    from modules.orders.transfer import TransferError, przepisz_cale_zamowienie

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 1, 30)], user=ania)
    sr = ShippingRequest(request_number='WYS/1', user_id=ania.id, status='czeka_na_wycene')
    db.session.add(sr)
    db.session.flush()
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=a.id))
    db.session.commit()

    with pytest.raises(TransferError, match='zleceniu wysyłki'):
        przepisz_cale_zamowienie(a, basia, admin)


def test_blokada_wms(db, make_product, make_order, ania, basia, admin):
    from modules.orders.transfer import TransferError, przepisz_cale_zamowienie
    from utils.timeutil import utcnow

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 1, 30)], user=ania, wms_locked_at=utcnow())

    with pytest.raises(TransferError, match='pakowane'):
        przepisz_cale_zamowienie(a, basia, admin)


def test_blokada_ta_sama_klientka(db, make_product, make_order, ania, admin):
    from modules.orders.transfer import TransferError, przepisz_cale_zamowienie

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 1, 30)], user=ania)

    with pytest.raises(TransferError):
        przepisz_cale_zamowienie(a, ania, admin)


def test_blokada_cel_nie_klientka(db, make_product, make_order, ania, admin):
    from modules.orders.transfer import TransferError, przepisz_cale_zamowienie

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 1, 30)], user=ania)

    with pytest.raises(TransferError):
        przepisz_cale_zamowienie(a, admin, admin)


def test_bez_blokad_zwraca_none(db, make_product, make_order, ania):
    from modules.orders.transfer import sprawdz_blokady

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 1, 30)], user=ania)

    assert sprawdz_blokady(a) is None
