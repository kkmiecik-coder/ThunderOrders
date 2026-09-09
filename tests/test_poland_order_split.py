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


def _zbuduj_partie(db, produkty_i_ilosci, numer='PL/S9', created_at=None,
                   shipping=Decimal('0'), customs=Decimal('0'), status='zamowione',
                   order_type='polska', stawka_za_szt=None):
    """Partia Polska z własnym rodzicem: ProxyOrder + ProxyOrderItem + PolandOrder + PolandOrderItem.

    produkty_i_ilosci: lista (product_id, ilość).
    stawka_za_szt: gdy podana, każda pozycja dostaje shipping_cost = stawka * ilość
                   oraz obie stawki za sztukę (album/incl) równe tej stawce.
    Zwraca (partia, [pozycje]).
    """
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem

    proxy = ProxyOrder(order_number=f'PRX/{numer.replace("/", "-")}', order_type=order_type)
    db.session.add(proxy)
    db.session.flush()

    partia = PolandOrder(order_number=numer, proxy_order_id=proxy.id, status=status,
                         shipping_cost=shipping, customs_cost=customs)
    if created_at is not None:
        partia.created_at = created_at
    db.session.add(partia)
    db.session.flush()

    pozycje = []
    for product_id, ilosc in produkty_i_ilosci:
        proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product_id,
                                    quantity=ilosc, unit_price=Decimal('25'),
                                    total_price=Decimal('25') * ilosc)
        db.session.add(proxy_item)
        db.session.flush()
        pozycja = PolandOrderItem(poland_order_id=partia.id, proxy_order_item_id=proxy_item.id,
                                  product_id=product_id, quantity=ilosc)
        if stawka_za_szt is not None:
            pozycja.shipping_cost = Decimal(str(stawka_za_szt)) * ilosc
            pozycja.shipping_cost_album_per_unit = Decimal(str(stawka_za_szt))
            pozycja.shipping_cost_incl_per_unit = Decimal(str(stawka_za_szt))
        db.session.add(pozycja)
        db.session.flush()
        pozycje.append(pozycja)

    db.session.commit()
    return partia, pozycje


def _zamowienie_klienta(db, make_user, make_order, product_id, ilosc, created_at, cena=130):
    """Zamówienie klienta z jedną pozycją (exclusive — offer_page_id ustawione)."""
    from modules.orders.models import OrderItem

    uzytkownik = make_user()
    zamowienie = make_order(uzytkownik, offer_page_id=1, created_at=created_at)
    db.session.add(OrderItem(order_id=zamowienie.id, product_id=product_id, quantity=ilosc,
                             price=Decimal(str(cena)), total=Decimal(str(cena)) * ilosc))
    db.session.commit()
    return zamowienie


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


def test_podglad_podzialu_zwraca_pozycje_i_kwoty(db, client, login, make_user, make_product):
    admin = make_user(role='admin', email='admin-split@example.com')
    login(admin)

    p1 = make_product(name='Album A', purchase_price_pln=Decimal('25.00'))
    p2 = make_product(name='Poca B', purchase_price_pln=Decimal('10.00'))
    partia, _ = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/S2',
                               shipping=Decimal('80.00'), customs=Decimal('20.00'))

    odpowiedz = client.get(f'/admin/products/api/poland-orders/{partia.id}/split-preview')

    assert odpowiedz.status_code == 200
    dane = odpowiedz.get_json()
    assert dane['success'] is True
    assert dane['numer'] == 'PL/S2'
    assert dane['shipping_cost'] == 80.0
    assert dane['customs_cost'] == 20.0
    assert [p['nazwa'] for p in dane['pozycje']] == ['Album A', 'Poca B']
    assert [p['ilosc'] for p in dane['pozycje']] == [4, 6]
    assert [p['wartosc_zakupu'] for p in dane['pozycje']] == [100.0, 60.0]
