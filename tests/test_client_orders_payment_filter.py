"""Filtr płatności na liście zamówień klienta (/client/orders?payment_status=...).

Filtr musi mierzyć wpłaty względem PEŁNEJ należności ze wszystkich etapów
(E1 produkt + E2 wysyłka KR + E3 cło/VAT + E4 wysyłka PL), czyli dokładnie
tak, jak liczy to `Order.total_to_pay`. Wcześniej porównywał `paid_amount`
z samym `total_amount` (E1), przez co zamówienie z opłaconym produktem
i zaległym cłem wypadało z „Nieopłacone" i lądowało w „Opłacone".

Testy jadą po wyrażeniu SQL `Order.total_to_pay` (hybrid), bo to ono jest
źródłem prawdy dla filtra — dzięki temu sprawdzamy realny warunek WHERE,
a nie kopię logiki.
"""
from decimal import Decimal

import pytest


def _paid(order, amount):
    """Ustawia sumę zatwierdzonych wpłat (paid_amount akumuluje etapy E1–E4)."""
    order.paid_amount = Decimal(str(amount))
    return order


def _query(db, user, variant):
    """Zwraca zamówienia użytkownika przefiltrowane tak jak trasa client_list."""
    from modules.orders.routes import apply_payment_status_filter
    from modules.orders.models import Order

    q = Order.query.filter_by(user_id=user.id)
    return apply_payment_status_filter(q, variant).all()


# === Odwzorowanie total_to_pay w SQL ===

def test_total_to_pay_expression_zgadza_sie_z_pythonem(db, make_user, make_order):
    """Wyrażenie SQL musi zwracać tę samą kwotę co właściwość w Pythonie."""
    from modules.orders.models import Order

    u = make_user()
    make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=4,
               shipping_cost=Decimal('20.00'), proxy_shipping_cost=Decimal('30.00'),
               customs_vat_sale_cost=Decimal('40.00'))

    order = Order.query.filter_by(user_id=u.id).one()
    from_sql = db.session.query(Order.total_to_pay).filter(Order.id == order.id).scalar()

    assert Decimal(str(from_sql)) == order.total_to_pay == Decimal('190.00')


def test_total_to_pay_expression_pomija_e2_gdy_trzy_etapy(db, make_user, make_order):
    """E2 (wysyłka KR) dotyczy wyłącznie zamówień 4-etapowych."""
    from modules.orders.models import Order

    u = make_user()
    make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=3,
               shipping_cost=Decimal('20.00'), proxy_shipping_cost=Decimal('30.00'))

    order = Order.query.filter_by(user_id=u.id).one()
    from_sql = db.session.query(Order.total_to_pay).filter(Order.id == order.id).scalar()

    assert Decimal(str(from_sql)) == order.total_to_pay == Decimal('120.00')


def test_total_to_pay_expression_pomija_e3_dla_on_hand(db, make_user, make_order):
    """E3 (cło/VAT) nie dotyczy zamówień on_hand."""
    from modules.orders.models import Order

    u = make_user()
    make_order(u, total_amount=100.00, order_type='on_hand',
               shipping_cost=Decimal('20.00'), customs_vat_sale_cost=Decimal('40.00'))

    order = Order.query.filter_by(user_id=u.id).one()
    from_sql = db.session.query(Order.total_to_pay).filter(Order.id == order.id).scalar()

    assert Decimal(str(from_sql)) == order.total_to_pay == Decimal('120.00')


# === Filtr „Nieopłacone" ===

def test_nieoplacone_lapie_oplacony_e1_z_zaleglym_clem(db, make_user, make_order):
    """REGRESJA: E1 opłacony w całości, E3 cło i E4 wysyłka zaległe → NIEOPŁACONE.

    Wcześniej filtr porównywał paid_amount z total_amount (E1), więc takie
    zamówienie wypadało z 'unpaid'.
    """
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=3,
                   status='oczekujace', shipping_cost=Decimal('20.00'),
                   customs_vat_sale_cost=Decimal('40.00'))
    _paid(o, '100.00')
    db.session.commit()

    assert [x.id for x in _query(db, u, 'unpaid')] == [o.id]


def test_nieoplacone_lapie_zamowienie_bez_zadnej_wplaty(db, make_user, make_order):
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='on_hand', status='oczekujace',
                   shipping_cost=Decimal('20.00'))

    assert [x.id for x in _query(db, u, 'unpaid')] == [o.id]


def test_nieoplacone_pomija_zamowienie_oplacone_w_calosci(db, make_user, make_order):
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='on_hand', status='oczekujace',
                   shipping_cost=Decimal('20.00'))
    _paid(o, '120.00')
    db.session.commit()

    assert _query(db, u, 'unpaid') == []


def test_nieoplacone_pomija_nadplate(db, make_user, make_order):
    """Nadpłata to nie zaległość."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='on_hand', status='oczekujace',
                   shipping_cost=Decimal('20.00'))
    _paid(o, '150.00')
    db.session.commit()

    assert _query(db, u, 'unpaid') == []


@pytest.mark.parametrize('status', ['anulowane', 'do_zwrotu', 'zwrocone', 'czesciowo_zwrocone'])
def test_nieoplacone_pomija_zamowienia_zamkniete(db, make_user, make_order, status):
    """Anulowane / w zwrocie nie są należnością — parytet z kafelkiem 'Do zapłaty'."""
    u = make_user()
    make_order(u, total_amount=100.00, order_type='on_hand', status=status,
               shipping_cost=Decimal('20.00'))

    assert _query(db, u, 'unpaid') == []


# === Filtr „Opłacone" ===

def test_oplacone_nie_lapie_zamowienia_z_zaleglym_etapem(db, make_user, make_order):
    """REGRESJA: opłacony E1 przy zaległym E3 NIE może uchodzić za opłacone."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=3,
                   status='oczekujace', shipping_cost=Decimal('20.00'),
                   customs_vat_sale_cost=Decimal('40.00'))
    _paid(o, '100.00')
    db.session.commit()

    assert _query(db, u, 'paid') == []


def test_oplacone_lapie_pelna_wplate_i_nadplate(db, make_user, make_order):
    u = make_user()
    full = make_order(u, total_amount=100.00, order_type='on_hand', status='oczekujace',
                      shipping_cost=Decimal('20.00'))
    _paid(full, '120.00')
    over = make_order(u, total_amount=100.00, order_type='on_hand', status='oczekujace',
                      shipping_cost=Decimal('20.00'))
    _paid(over, '130.00')
    db.session.commit()

    assert sorted(x.id for x in _query(db, u, 'paid')) == sorted([full.id, over.id])


# === Filtr „Częściowo opłacone" ===

def test_czesciowo_lapie_oplacony_e1_przy_zaleglym_e3(db, make_user, make_order):
    """REGRESJA: E1 spłacony, E3 zaległy → to jest płatność częściowa."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=3,
                   status='oczekujace', shipping_cost=Decimal('20.00'),
                   customs_vat_sale_cost=Decimal('40.00'))
    _paid(o, '100.00')
    db.session.commit()

    assert [x.id for x in _query(db, u, 'partial')] == [o.id]


def test_czesciowo_pomija_zero_i_pelna_wplate(db, make_user, make_order):
    u = make_user()
    make_order(u, total_amount=100.00, order_type='on_hand', status='oczekujace',
               shipping_cost=Decimal('20.00'))  # 0 wpłacone
    full = make_order(u, total_amount=100.00, order_type='on_hand', status='oczekujace',
                      shipping_cost=Decimal('20.00'))
    _paid(full, '120.00')
    db.session.commit()

    assert _query(db, u, 'partial') == []


# === Rozłączność wariantów ===

def test_warianty_sa_rozlaczne_i_pokrywaja_wszystkie_aktywne(db, make_user, make_order):
    """Każde aktywne zamówienie wpada dokładnie do jednego wariantu."""
    u = make_user()
    zero = make_order(u, total_amount=100.00, order_type='on_hand', status='oczekujace',
                      shipping_cost=Decimal('20.00'))
    part = make_order(u, total_amount=100.00, order_type='on_hand', status='oczekujace',
                      shipping_cost=Decimal('20.00'))
    _paid(part, '50.00')
    full = make_order(u, total_amount=100.00, order_type='on_hand', status='oczekujace',
                      shipping_cost=Decimal('20.00'))
    _paid(full, '120.00')
    db.session.commit()

    unpaid = {x.id for x in _query(db, u, 'unpaid')}
    partial = {x.id for x in _query(db, u, 'partial')}
    paid = {x.id for x in _query(db, u, 'paid')}

    assert unpaid == {zero.id, part.id}          # 'nieopłacone' = cokolwiek zostało
    assert partial == {part.id}
    assert paid == {full.id}
    assert partial & paid == set()
    assert unpaid | paid == {zero.id, part.id, full.id}
