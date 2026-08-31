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
