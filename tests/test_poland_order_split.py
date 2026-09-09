"""Testy podziału partii Polska — wydzielenie pozycji do nowej partii.

Projekt: docs/superpowers/specs/2026-09-09-podzial-partii-polska-design.md
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _strona_sprzedazy(strona_sprzedazy):
    """Zamówienia w tym pliku powstają z `offer_page_id=1`, a to kolumna FK — strona
    o tym id musi realnie istnieć (fixture `strona_sprzedazy` w conftest)."""


def test_przelicz_sumy_partii_sumuje_zakup_wysylke_i_clo(db, make_product):
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem
    from modules.products.routes import _przelicz_sumy_partii

    produkt = make_product(purchase_price_pln=Decimal('25.00'))

    proxy = ProxyOrder(order_number='PRX/S1', order_type='polska')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=produkt.id,
                                quantity=4, unit_price=Decimal('25'), total_price=Decimal('100'))
    db.session.add(proxy_item)
    db.session.flush()

    partia = PolandOrder(order_number='PL/S1', proxy_order_id=proxy.id, status='zamowione',
                         shipping_cost=Decimal('30.00'), customs_cost=Decimal('12.00'))
    db.session.add(partia)
    db.session.flush()
    db.session.add(PolandOrderItem(poland_order_id=partia.id, proxy_order_item_id=proxy_item.id,
                                   product_id=produkt.id, quantity=4))
    db.session.commit()

    wartosc_produktow = _przelicz_sumy_partii(partia)

    assert wartosc_produktow == Decimal('100.00')
    assert partia.total_amount == Decimal('142.00')
