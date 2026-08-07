"""Kontrakt JSON: flagi opłacenia w odpowiedziach panelu admina.

Szczegóły zamówienia kolorują badge „Zapłacono" po stronie klienta. Kolor NIE
może być liczony z grand_total (produkt + wysyłka PL), bo pomija cło i wysyłkę
z Korei — dlatego serwer musi odesłać komplet flag (is_fully_paid, is_overpaid,
is_partially_paid), a JS ma je tylko przepisać na klasy CSS.

Testy pilnują, żeby flagi nie wypadły z odpowiedzi przy przyszłych zmianach.
"""
from decimal import Decimal

import pytest

FLAGI = ('is_fully_paid', 'is_partially_paid', 'is_overpaid')


@pytest.fixture
def admin(make_user):
    return make_user(role='admin', profile_completed=True)


@pytest.fixture
def zamowienie_z_clem(db, make_user, make_order):
    """Produkt 100 + wysyłka PL 20 opłacone, cło 40 zaległe → nie jest opłacone."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=3,
                   shipping_cost=Decimal('20.00'), customs_vat_sale_cost=Decimal('40.00'))
    o.paid_amount = Decimal('120.00')
    db.session.commit()
    return o


def test_endpoint_platnosci_zwraca_komplet_flag(client, login, admin, zamowienie_z_clem):
    login(admin)

    r = client.post(f'/admin/orders/{zamowienie_z_clem.id}/payment',
                    json={'paid_amount': 120.00})

    assert r.status_code == 200
    data = r.get_json()
    assert all(f in data for f in FLAGI), data
    # Zaległe cło → badge nie może być zielony
    assert data['is_fully_paid'] is False
    assert data['is_overpaid'] is False
    assert data['is_partially_paid'] is True


def test_endpoint_edycji_kosztu_zwraca_komplet_flag(client, login, admin, zamowienie_z_clem):
    login(admin)

    r = client.post(f'/admin/orders/{zamowienie_z_clem.id}/update-field',
                    json={'field': 'shipping_cost', 'value': '20.00'})

    assert r.status_code == 200
    data = r.get_json()
    assert all(f in data for f in FLAGI), data
    assert data['is_fully_paid'] is False
    assert data['is_partially_paid'] is True


def test_ustawienie_cla_odbiera_status_oplacone(client, login, admin, db, make_user, make_order):
    """Admin dolicza cło do opłaconego zamówienia → przestaje być opłacone."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=3,
                   shipping_cost=Decimal('20.00'))
    o.paid_amount = Decimal('120.00')
    db.session.commit()
    assert o.is_fully_paid is True          # przed doliczeniem cła
    login(admin)

    r = client.post(f'/admin/orders/{o.id}/update-field',
                    json={'field': 'customs_vat_sale_cost', 'value': '40.00'})

    assert r.status_code == 200
    assert r.get_json()['is_fully_paid'] is False
