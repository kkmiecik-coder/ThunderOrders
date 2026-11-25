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


# ---------------------------------------------------------------- wybrane pozycje

def _pozycje(order):
    from modules.orders.models import OrderItem
    return OrderItem.query.filter_by(order_id=order.id).order_by(OrderItem.id).all()


def test_pozycja_w_calosci_trafia_do_nowego_zamowienia(db, make_product, make_order,
                                                         ania, basia, admin):
    from modules.orders.transfer import przepisz_pozycje

    p1, p2 = make_product(), make_product()
    a = zamowienie_klientki(db, None, make_order, [(p1.id, 1, 60), (p2.id, 1, 40)], user=ania,
                            status='oczekujace', payment_stages=4, offer_page_name='Drop')
    karta = _pozycje(a)[1]

    wynik = przepisz_pozycje(a, basia, admin, [(karta.id, 1)], wplata_za_karta=False)
    db.session.commit()
    b = wynik.cel

    assert b.id != a.id and b.user_id == basia.id
    assert (b.order_type, b.status, b.offer_page_id, b.payment_stages, b.offer_page_name) == \
        ('exclusive', 'oczekujace', 1, 4, 'Drop')
    assert b.created_at == a.created_at
    assert b.fifo_anchor_order_id == a.id
    assert b.order_number == f'EX/{b.id}'
    assert b.created_by_admin_id == admin.id
    assert karta.order_id == b.id
    assert a.total_amount == Decimal('60') and b.total_amount == Decimal('40')
    assert wynik.pozycje == [(karta.product_name, 1)]


def test_czesc_sztuk_dzieli_pozycje(db, make_product, make_order, ania, basia, admin):
    from modules.orders.transfer import przepisz_pozycje

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 2, 30)], user=ania)
    item = _pozycje(a)[0]
    item.selected_size = 'M'
    db.session.commit()

    b = przepisz_pozycje(a, basia, admin, [(item.id, 1)], wplata_za_karta=False).cel
    db.session.commit()

    assert (item.quantity, item.total) == (1, Decimal('30'))
    [nowa] = _pozycje(b)
    assert (nowa.product_id, nowa.quantity, nowa.price, nowa.total, nowa.selected_size) == \
        (p.id, 1, Decimal('30'), Decimal('30'), 'M')
    assert a.total_amount == Decimal('30') and b.total_amount == Decimal('30')


def test_lancuch_kotwicy(db, make_product, make_order, make_user, ania, basia, admin):
    from modules.orders.transfer import przepisz_pozycje

    celina = make_user(email='celina@example.com')
    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 3, 30)], user=ania)
    b = przepisz_pozycje(a, basia, admin, [(_pozycje(a)[0].id, 2)], wplata_za_karta=False).cel
    db.session.commit()
    c = przepisz_pozycje(b, celina, admin, [(_pozycje(b)[0].id, 1)], wplata_za_karta=False).cel
    db.session.commit()

    assert c.fifo_anchor_order_id == a.id
    assert c.created_at == a.created_at


def test_komentarz_w_obu_zamowieniach(db, make_product, make_order, ania, basia, admin):
    from modules.orders.models import OrderComment
    from modules.orders.transfer import przepisz_pozycje

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 2, 30)], user=ania)
    b = przepisz_pozycje(a, basia, admin, [(_pozycje(a)[0].id, 1)], wplata_za_karta=True).cel
    db.session.commit()

    for o in (a, b):
        [k] = OrderComment.query.filter_by(order_id=o.id).all()
        assert k.is_internal and a.order_number in k.comment and b.order_number in k.comment
        assert 'wpłata poszła razem z kartą' in k.comment


@pytest.mark.parametrize('wybor_fn', [
    lambda items: [],                                          # pusty wybór
    lambda items: [(items[0].id, 2), (items[1].id, 1)],        # wszystko
    lambda items: [(items[0].id, 0)],                          # ilość 0
    lambda items: [(items[0].id, 3)],                          # ponad ilość
    lambda items: [(999999, 1)],                               # obca pozycja
])
def test_walidacja_wyboru(db, make_product, make_order, ania, basia, admin, wybor_fn):
    from modules.orders.transfer import TransferError, przepisz_pozycje

    p1, p2 = make_product(), make_product()
    a = zamowienie_klientki(db, None, make_order, [(p1.id, 2, 30), (p2.id, 1, 10)], user=ania)

    with pytest.raises(TransferError):
        przepisz_pozycje(a, basia, admin, wybor_fn(_pozycje(a)), wplata_za_karta=False)


@pytest.mark.parametrize('ustaw', [
    lambda i: setattr(i, 'incl_only_quantity', 1),
    lambda i: setattr(i, 'fulfilled_quantity', 1),
    lambda i: setattr(i, 'picked_quantity', 1),
])
def test_czesc_sztuk_tylko_dla_prostej_pozycji(db, make_product, make_order, ania, basia, admin,
                                              ustaw):
    from modules.orders.transfer import TransferError, przepisz_pozycje

    p1, p2 = make_product(), make_product()
    a = zamowienie_klientki(db, None, make_order, [(p1.id, 2, 30), (p2.id, 1, 10)], user=ania)
    item = _pozycje(a)[0]
    ustaw(item)
    db.session.commit()

    with pytest.raises(TransferError, match='całą pozycję'):
        przepisz_pozycje(a, basia, admin, [(item.id, 1)], wplata_za_karta=False)
    # w całości wolno
    przepisz_pozycje(a, basia, admin, [(item.id, 2)], wplata_za_karta=False)


def test_czesc_sztuk_z_gift_card_zablokowana(db, make_product, make_order, strona_sprzedazy,
                                            ania, basia, admin):
    from modules.orders.transfer import TransferError, przepisz_pozycje

    p1, p2 = make_product(), make_product()
    a = zamowienie_klientki(db, None, make_order, [(p1.id, 2, 30), (p2.id, 1, 10)], user=ania)
    item = _pozycje(a)[0]
    przydzial = przydzial_gift_card(db, make_product, strona_sprzedazy, ania, item)

    with pytest.raises(TransferError, match='całą pozycję'):
        przepisz_pozycje(a, basia, admin, [(item.id, 1)], wplata_za_karta=False)

    przepisz_pozycje(a, basia, admin, [(item.id, 2)], wplata_za_karta=False)
    db.session.commit()
    assert przydzial.user_id == basia.id


def test_wplata_za_karta_blokowana_przy_oczekujacym(db, make_product, make_order,
                                                     ania, basia, admin):
    from modules.orders.transfer import TransferError, przepisz_pozycje

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 2, 30)], user=ania)
    _potwierdzenie(db, a, 'product', 60, status='pending')
    item = _pozycje(a)[0]

    with pytest.raises(TransferError, match='czeka na sprawdzenie'):
        przepisz_pozycje(a, basia, admin, [(item.id, 1)], wplata_za_karta=True)
    przepisz_pozycje(a, basia, admin, [(item.id, 1)], wplata_za_karta=False)


def test_pozycje_respektuja_blokady(db, make_product, make_order, ania, basia, admin):
    from modules.orders.transfer import TransferError, przepisz_pozycje

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 2, 30)], user=ania, status='wyslane')

    with pytest.raises(TransferError):
        przepisz_pozycje(a, basia, admin, [(_pozycje(a)[0].id, 1)], wplata_za_karta=False)


# ---------------------------------------------------------------- koszty, wpłaty, partie

def test_e2_przechodzi_i_suma_zachowana(db, make_product, make_order, make_user,
                                        ania, basia, admin):
    """Ania (2 szt.) i Celina (1 szt.) w tej samej sekundzie; partie 2 szt. po 10 zł
    i 1 szt. po 30 zł. Basia przejmuje 1 szt. Ani i staje za Anią — dostaje sztukę
    z tańszej partii, Celina zostaje przy swoich 30 zł."""
    from datetime import timedelta
    from modules.orders.transfer import przepisz_pozycje
    from tests.przepisanie_helpers import partia

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 2, 30)], user=ania,
                            payment_stages=4, proxy_shipping_cost=20)
    c = zamowienie_klientki(db, make_user, make_order, [(p.id, 1, 30)],
                            payment_stages=4, proxy_shipping_cost=30)
    partia(db, p.id, 2, T0 + timedelta(hours=1), koszt=20)
    partia(db, p.id, 1, T0 + timedelta(hours=2), koszt=30)

    b = przepisz_pozycje(a, basia, admin, [(_pozycje(a)[0].id, 1)], wplata_za_karta=False).cel
    db.session.commit()

    assert b.proxy_shipping_cost == Decimal('10.00')
    assert a.proxy_shipping_cost == Decimal('10.00')
    assert c.proxy_shipping_cost == Decimal('30.00')


def test_e2_przyciete_do_kosztu_ani(db, make_product, make_order, ania, basia, admin):
    """Ręcznie wyzerowany koszt u Ani — nie robimy z niego wartości ujemnej."""
    from datetime import timedelta
    from modules.orders.transfer import przepisz_pozycje
    from tests.przepisanie_helpers import partia

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 2, 30)], user=ania,
                            payment_stages=4, proxy_shipping_cost=0)
    partia(db, p.id, 2, T0 + timedelta(hours=1), koszt=20)

    b = przepisz_pozycje(a, basia, admin, [(_pozycje(a)[0].id, 1)], wplata_za_karta=False).cel
    db.session.commit()

    assert a.proxy_shipping_cost == Decimal('0') and b.proxy_shipping_cost == Decimal('0')


def test_e3_wg_stawki(db, make_product, make_order, ania, basia, admin):
    from datetime import timedelta
    from modules.orders.transfer import przepisz_pozycje
    from tests.przepisanie_helpers import partia

    karta, album = make_product(), make_product()
    a = zamowienie_klientki(db, None, make_order, [(karta.id, 1, 40), (album.id, 1, 60)],
                            user=ania, customs_vat_sale_cost=Decimal('9.20'))
    partia(db, karta.id, 1, T0 + timedelta(hours=1), stawka_cla=23)
    pozycja_karty = _pozycje(a)[0]

    b = przepisz_pozycje(a, basia, admin, [(pozycja_karty.id, 1)], wplata_za_karta=False).cel
    db.session.commit()

    assert b.customs_vat_sale_cost == Decimal('9.20')
    assert a.customs_vat_sale_cost == Decimal('0.00')


def test_e3_null_zostaje_null(db, make_product, make_order, ania, basia, admin):
    from datetime import timedelta
    from modules.orders.transfer import przepisz_pozycje
    from tests.przepisanie_helpers import partia

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 2, 40)], user=ania)
    partia(db, p.id, 2, T0 + timedelta(hours=1), stawka_cla=23)

    b = przepisz_pozycje(a, basia, admin, [(_pozycje(a)[0].id, 1)], wplata_za_karta=False).cel
    db.session.commit()

    assert a.customs_vat_sale_cost is None and b.customs_vat_sale_cost is None


def test_wplata_idzie_za_karta(db, make_product, make_order, ania, basia, admin):
    from datetime import timedelta
    from modules.orders.models import PaymentConfirmation
    from modules.orders.transfer import przepisz_pozycje
    from tests.przepisanie_helpers import partia

    p1, p2 = make_product(), make_product()
    a = zamowienie_klientki(db, None, make_order, [(p1.id, 1, 60), (p2.id, 1, 40)], user=ania,
                            payment_stages=4, proxy_shipping_cost=15, paid_amount=115)
    partia(db, p2.id, 1, T0 + timedelta(hours=1), koszt=15)
    e1 = _potwierdzenie(db, a, 'product', 100, plik='ania.png')
    e2 = _potwierdzenie(db, a, 'korean_shipping', 15)

    b = przepisz_pozycje(a, basia, admin, [(_pozycje(a)[1].id, 1)], wplata_za_karta=True).cel
    db.session.commit()

    assert e1.amount == Decimal('60.00') and e2.amount == Decimal('0.00')
    assert a.paid_amount == Decimal('60.00')
    confs = {c.payment_stage: c for c in PaymentConfirmation.query.filter_by(order_id=b.id)}
    assert set(confs) == {'product', 'korean_shipping'}
    assert confs['product'].amount == Decimal('40.00')
    assert confs['korean_shipping'].amount == Decimal('15.00')
    assert all(c.status == 'approved' and c.proof_file is None for c in confs.values())
    assert b.paid_amount == Decimal('55.00')
    assert a.paid_amount + b.paid_amount == Decimal('115')


def test_wplata_zostaje_u_ani(db, make_product, make_order, ania, basia, admin):
    from modules.orders.models import PaymentConfirmation
    from modules.orders.transfer import przepisz_pozycje

    p1, p2 = make_product(), make_product()
    a = zamowienie_klientki(db, None, make_order, [(p1.id, 1, 60), (p2.id, 1, 40)], user=ania,
                            paid_amount=100)
    e1 = _potwierdzenie(db, a, 'product', 100)

    b = przepisz_pozycje(a, basia, admin, [(_pozycje(a)[1].id, 1)], wplata_za_karta=False).cel
    db.session.commit()

    assert a.paid_amount == Decimal('100') and e1.amount == Decimal('100')
    assert b.paid_amount == Decimal('0')
    assert PaymentConfirmation.query.filter_by(order_id=b.id).count() == 0


def test_wplata_tylko_z_zatwierdzonych(db, make_product, make_order, ania, basia, admin):
    """Odrzucone potwierdzenie to nie wpłata — nic nie przechodzi."""
    from modules.orders.models import PaymentConfirmation
    from modules.orders.transfer import przepisz_pozycje

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 2, 30)], user=ania)
    _potwierdzenie(db, a, 'product', 60, status='rejected')

    b = przepisz_pozycje(a, basia, admin, [(_pozycje(a)[0].id, 1)], wplata_za_karta=True).cel
    db.session.commit()

    assert PaymentConfirmation.query.filter_by(order_id=b.id).count() == 0
    assert b.paid_amount == Decimal('0')


def test_powiazania_partii_przeniesione(db, make_product, make_order, ania, basia, admin):
    from datetime import timedelta
    from modules.products.models import PolandOrderItemOrder
    from modules.orders.transfer import przepisz_pozycje
    from tests.przepisanie_helpers import partia

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 3, 30)], user=ania)
    pierwsza = partia(db, p.id, 2, T0 + timedelta(hours=1))
    druga = partia(db, p.id, 1, T0 + timedelta(hours=2))
    db.session.add_all([
        PolandOrderItemOrder(poland_order_item_id=pierwsza.id, order_id=a.id, quantity=2),
        PolandOrderItemOrder(poland_order_item_id=druga.id, order_id=a.id, quantity=1),
    ])
    db.session.commit()

    b = przepisz_pozycje(a, basia, admin, [(_pozycje(a)[0].id, 2)], wplata_za_karta=False).cel
    db.session.commit()

    def mapa(order):
        return {l.poland_order_item_id: l.quantity
                for l in PolandOrderItemOrder.query.filter_by(order_id=order.id)}
    assert mapa(a) == {pierwsza.id: 1}
    assert mapa(b) == {pierwsza.id: 1, druga.id: 1}


def test_bez_powiazan_partii_dziala(db, make_product, make_order, ania, basia, admin):
    from datetime import timedelta
    from modules.products.models import PolandOrderItemOrder
    from modules.orders.transfer import przepisz_pozycje
    from tests.przepisanie_helpers import partia

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 2, 30)], user=ania)
    partia(db, p.id, 2, T0 + timedelta(hours=1))

    b = przepisz_pozycje(a, basia, admin, [(_pozycje(a)[0].id, 1)], wplata_za_karta=False).cel
    db.session.commit()

    assert PolandOrderItemOrder.query.filter_by(order_id=b.id).count() == 0


def test_czesc_sztuk_zrealizowanej_pozycji_dzieli_licznik(db, make_product, make_order,
                                                          ania, basia, admin):
    """Pozycja zrealizowana w całości (fulfilled_quantity == quantity) po podziale
    nadal jest zrealizowana w całości po obu stronach."""
    from modules.orders.transfer import przepisz_pozycje

    p = make_product()
    a = zamowienie_klientki(db, None, make_order, [(p.id, 3, 30)], user=ania)
    item = _pozycje(a)[0]
    item.fulfilled_quantity = 3
    item.is_set_fulfilled = True
    db.session.commit()

    b = przepisz_pozycje(a, basia, admin, [(item.id, 1)], wplata_za_karta=False).cel
    db.session.commit()

    [nowa] = _pozycje(b)
    assert (item.quantity, item.fulfilled_quantity) == (2, 2)
    assert (nowa.quantity, nowa.fulfilled_quantity, nowa.is_set_fulfilled) == (1, 1, True)
