"""
Cło/VAT liczy się od ceny sprzedaży — tej, którą płacą klienci.

Wcześniej brano cenę zakupu przeliczoną na złotówki (`purchase_price_pln`).
To pole bywa rozjechane z ceną w walucie: OT8 „Hello Live" miał tam 49 zł,
czyli cenę JEDNEJ karty zamiast całego zestawu ośmiu (392 zł), więc cło
wychodziło 12,74 zł zamiast 101,92 zł. Cena sprzedaży jest polem, które
Karolina realnie utrzymuje i widzi na liście produktów.
"""
from decimal import Decimal

import pytest


@pytest.fixture
def admin(make_user):
    return make_user(role='admin', email='admin@example.com')


@pytest.fixture
def zamowienie_polska(db, make_product):
    """Zamówienie z Polski z jedną pozycją, gdzie cena sprzedaży != cena zakupu w PLN."""
    from modules.products.models import PolandOrder, PolandOrderItem, ProxyOrder, ProxyOrderItem

    produkt = make_product(
        name='GH5 - Hello Live 1.0 (Album) Bubble tea - OT8',
        sale_price=Decimal('392.00'),
        purchase_price=Decimal('148800.00'),
        purchase_currency='KRW',
        purchase_price_pln=Decimal('49.00'),
    )
    proxy = ProxyOrder(order_number='PRX/T-CLO', order_type='proxy', status='zamowiono')
    db.session.add(proxy)
    db.session.flush()
    pozycja_proxy = ProxyOrderItem(
        proxy_order_id=proxy.id, product_id=produkt.id,
        quantity=1, unit_price=Decimal('363.67'), total_price=Decimal('363.67'),
    )
    db.session.add(pozycja_proxy)
    db.session.flush()
    zamowienie = PolandOrder(
        order_number='PRX/PL/T-CLO', proxy_order_id=proxy.id, status='zamowione',
    )
    db.session.add(zamowienie)
    db.session.flush()
    pozycja = PolandOrderItem(
        poland_order_id=zamowienie.id, proxy_order_item_id=pozycja_proxy.id,
        product_id=produkt.id, quantity=1,
    )
    db.session.add(pozycja)
    db.session.commit()
    return zamowienie, pozycja, produkt


def test_okno_pokazuje_cene_sprzedazy(app, client, login, admin, zamowienie_polska):
    """Okno pojedynczego zamówienia pokazuje 392 zł, nie 49 zł."""
    zamowienie, _pozycja, _produkt = zamowienie_polska
    login(admin)

    odp = client.get(f'/admin/products/api/poland-order-customs/{zamowienie.id}')

    assert odp.status_code == 200
    dane = odp.get_json()['items'][0]
    assert dane['unit_value'] == 392.00
    assert dane['product_value'] == 392.00


def test_okno_zbiorcze_pokazuje_cene_sprzedazy(app, client, login, admin, zamowienie_polska):
    """Okno zbiorcze musi brać cenę z tego samego źródła co pojedyncze."""
    zamowienie, _pozycja, _produkt = zamowienie_polska
    login(admin)

    odp = client.post(
        '/admin/products/api/poland-orders-customs-bulk',
        json={'order_ids': [zamowienie.id]},
    )

    assert odp.status_code == 200
    dane = odp.get_json()['orders'][0]['items'][0]
    assert dane['unit_value'] == 392.00


def test_zapis_cla_liczy_od_ceny_sprzedazy(app, db, client, login, admin, zamowienie_polska):
    """Najwazniejszy test: zapisana kwota to 26% z 392 zl, nie z 49 zl."""
    _zamowienie, pozycja, _produkt = zamowienie_polska
    login(admin)

    odp = client.put(
        '/admin/products/api/update-poland-customs-vat',
        json={
            'items': [{'poland_order_item_id': pozycja.id, 'customs_vat_percentage': 26}],
            'customs_payment_deadline': '2026-10-01T23:59:00',
        },
    )

    assert odp.status_code == 200, odp.get_json()
    db.session.refresh(pozycja)
    assert pozycja.customs_vat_amount == Decimal('101.92')
