"""Testy podziału Wysyłki KR na cały album i samo incl.

Model: przy pozycji zamówienia klienta siedzi `incl_only_quantity` (ile sztuk
klient bierze jako samo incl), a przy pozycji partii do Polski dwie stawki za
sztukę. Podział FIFO bez zmian — zmienia się tylko cena sztuki, zależna od typu.
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _strona_sprzedazy(strona_sprzedazy):
    """Zamówienia w tym pliku powstają z `offer_page_id=1`, a to kolumna FK — strona
    o tym id musi realnie istnieć (fixture `strona_sprzedazy` w conftest)."""


def test_domyslne_wartosci_nowych_kolumn(db, make_user, make_order, make_product):
    """Bez jawnego ustawienia: pozycja klienta ma 0 incl, partia nie ma stawek."""
    from modules.orders.models import OrderItem
    from modules.products.models import (
        PolandOrder, PolandOrderItem, ProxyOrder, ProxyOrderItem,
    )

    produkt = make_product()
    zamowienie = make_order(make_user(), offer_page_id=1)
    pozycja = OrderItem(
        order_id=zamowienie.id, product_id=produkt.id, quantity=2,
        price=Decimal('130'), total=Decimal('260'),
    )
    db.session.add(pozycja)

    proxy = ProxyOrder(order_number='PRX/T1', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(
        proxy_order_id=proxy.id, product_id=produkt.id, quantity=2,
        unit_price=Decimal('100'), total_price=Decimal('200'),
    )
    db.session.add(proxy_item)
    db.session.flush()
    partia = PolandOrder(
        order_number='PRX/PL/T1', proxy_order_id=proxy.id,
        status='zamowione', shipping_cost=Decimal('100'),
    )
    db.session.add(partia)
    db.session.flush()
    pozycja_partii = PolandOrderItem(
        poland_order_id=partia.id, proxy_order_item_id=proxy_item.id,
        product_id=produkt.id, quantity=2, shipping_cost=Decimal('100'),
    )
    db.session.add(pozycja_partii)
    db.session.commit()

    assert pozycja.incl_only_quantity == 0
    assert pozycja_partii.shipping_cost_album_per_unit is None
    assert pozycja_partii.shipping_cost_incl_per_unit is None


def _partia(db, product_id, qty, shipping, created_at,
            album_rate=None, incl_rate=None, status='zamowione'):
    """Tworzy ProxyOrder+Item oraz PolandOrder+Item — jedną partię danego produktu."""
    from modules.products.models import (
        PolandOrder, PolandOrderItem, ProxyOrder, ProxyOrderItem,
    )
    suffix = f'{product_id}-{int(created_at.timestamp())}'
    proxy = ProxyOrder(order_number=f'PRX/T{suffix}', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(
        proxy_order_id=proxy.id, product_id=product_id, quantity=qty,
        unit_price=Decimal('100'), total_price=Decimal('100') * qty,
    )
    db.session.add(proxy_item)
    db.session.flush()

    partia = PolandOrder(
        order_number=f'PRX/PL/T{suffix}', proxy_order_id=proxy.id,
        status=status, shipping_cost=Decimal(str(shipping)),
    )
    partia.created_at = created_at
    db.session.add(partia)
    db.session.flush()
    pozycja = PolandOrderItem(
        poland_order_id=partia.id, proxy_order_item_id=proxy_item.id,
        product_id=product_id, quantity=qty, shipping_cost=Decimal(str(shipping)),
        shipping_cost_album_per_unit=(
            None if album_rate is None else Decimal(str(album_rate))),
        shipping_cost_incl_per_unit=(
            None if incl_rate is None else Decimal(str(incl_rate))),
    )
    db.session.add(pozycja)
    db.session.commit()
    return partia


def _zamowienie_klienta(db, make_user, make_order, product_id, qty, created_at,
                        incl=0, price=130):
    """Zamówienie klienta (exclusive) z jedną pozycją i wskazaną liczbą sztuk incl."""
    from modules.orders.models import OrderItem
    zam = make_order(make_user(), offer_page_id=1, created_at=created_at)
    poz = OrderItem(
        order_id=zam.id, product_id=product_id, quantity=qty,
        price=Decimal(str(price)), total=Decimal(str(price)) * qty,
        incl_only_quantity=incl,
    )
    db.session.add(poz)
    db.session.commit()
    return zam


def test_bez_incl_podzial_jak_dotad(db, make_user, make_order, make_product):
    """Regresja: gdy nikt nie bierze incl, wynik jest identyczny jak przed zmianą."""
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=4, shipping='200', created_at=baza)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2, baza - timedelta(days=2))
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2, baza - timedelta(days=1))

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('100.00')
    assert alokacja[b.id] == Decimal('100.00')


def test_partia_bez_stawek_stara_logika(db, make_user, make_order, make_product):
    """Stara partia (stawki NULL) dzieli po równo, nawet gdy klient ma incl."""
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=2, shipping='100', created_at=baza)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=2), incl=1)
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=1))

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('50.00')
    assert alokacja[b.id] == Decimal('50.00')


def test_klient_w_calosci_na_incl(db, make_user, make_order, make_product):
    """3 szt. samego incl po 12 zł = 36 zł, mimo że album kosztuje 45 zł/szt."""
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=4, shipping='81', created_at=baza,
            album_rate='45.00', incl_rate='12.00')
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 3,
                            baza - timedelta(days=2), incl=3)
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=1))

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('36.00')
    assert alokacja[b.id] == Decimal('45.00')


def test_klient_mieszany_album_i_incl(db, make_user, make_order, make_product):
    """2 szt. = 1 album (45) + 1 incl (12) = 57 zł na jednym zamówieniu."""
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=2, shipping='57', created_at=baza,
            album_rate='45.00', incl_rate='12.00')
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=2), incl=1)

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('57.00')


def test_dwie_partie_rozne_stawki_bez_dublowania(db, make_user, make_order, make_product):
    """Dwie partie, każda ze swoimi stawkami; przeliczenie od zera daje ten sam wynik."""
    from modules.products.routes import (
        _allocate_product_shipping_fifo, _distribute_proxy_shipping_to_client_orders,
    )
    from modules.orders.models import Order

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=2, shipping='57', created_at=baza,
            album_rate='45.00', incl_rate='12.00')
    _partia(db, produkt.id, qty=2, shipping='40', created_at=baza + timedelta(days=1),
            album_rate='30.00', incl_rate='10.00')

    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=3), incl=1)   # 1. partia: 45 + 12
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=2), incl=2)   # 2. partia: 10 + 10

    alokacja = _allocate_product_shipping_fifo(produkt.id)
    assert alokacja[a.id] == Decimal('57.00')
    assert alokacja[b.id] == Decimal('20.00')

    _distribute_proxy_shipping_to_client_orders({produkt.id: Decimal('1')})
    db.session.commit()
    _distribute_proxy_shipping_to_client_orders({produkt.id: Decimal('1')})
    db.session.commit()

    assert db.session.get(Order, a.id).proxy_shipping_cost == Decimal('57.00')
    assert db.session.get(Order, b.id).proxy_shipping_cost == Decimal('20.00')


def test_incl_przyciete_do_ilosci_zrealizowanej(db, make_user, make_order, make_product):
    """Set zrealizowany częściowo: incl nie może przekroczyć ilości, którą klient dostał."""
    from modules.orders.models import OrderItem
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=1, shipping='12', created_at=baza,
            album_rate='45.00', incl_rate='12.00')
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 3,
                            baza - timedelta(days=2), incl=3)
    pozycja = OrderItem.query.filter_by(order_id=a.id).one()
    pozycja.fulfilled_quantity = 1
    db.session.commit()

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('12.00')
