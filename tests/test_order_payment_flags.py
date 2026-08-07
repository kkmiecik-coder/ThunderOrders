"""Flagi opłacenia zamówienia (is_fully_paid / is_overpaid / is_partially_paid).

Flagi odpowiadają na pytanie „czy klient ma jeszcze coś do zapłaty", więc muszą
mierzyć wpłaty względem PEŁNEJ należności `Order.total_to_pay` (E1 produkt +
E2 wysyłka KR + E3 cło/VAT + E4 wysyłka PL). Wcześniej porównywały `paid_amount`
z `grand_total` = E1 + E4, przez co zamówienie z zaległym cłem uchodziło za
w pełni opłacone (m.in. badge „Zapłacono" w szczegółach zamówienia w adminie).

`grand_total` celowo POZOSTAJE surową sumą E1+E4 — jest sumą wyświetlaną, nie
miarą opłacenia. Pilnuje tego test na końcu pliku.
"""
from decimal import Decimal


def _order_z_zaleglym_clem(make_user, make_order, db):
    """E1 produkt 100 + E4 wysyłka 20 opłacone, E3 cło 40 zaległe."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=3,
                   shipping_cost=Decimal('20.00'), customs_vat_sale_cost=Decimal('40.00'))
    o.paid_amount = Decimal('120.00')
    db.session.commit()
    return o


# === Regresje ===

def test_zalegle_clo_nie_jest_w_pelni_oplacone(db, make_user, make_order):
    """REGRESJA: paid 120 przy należności 160 (z cłem) → NIE w pełni opłacone."""
    o = _order_z_zaleglym_clem(make_user, make_order, db)

    assert o.is_fully_paid is False


def test_zalegle_clo_to_platnosc_czesciowa(db, make_user, make_order):
    o = _order_z_zaleglym_clem(make_user, make_order, db)

    assert o.is_partially_paid is True


def test_zalegle_clo_nie_jest_nadplata(db, make_user, make_order):
    """REGRESJA: 120 > grand_total (120)? nie — i tak nie może być nadpłatą."""
    o = _order_z_zaleglym_clem(make_user, make_order, db)

    assert o.is_overpaid is False


def test_remaining_amount_obejmuje_wszystkie_etapy(db, make_user, make_order):
    """REGRESJA: zostało cło 40 zł, nie 0 zł."""
    o = _order_z_zaleglym_clem(make_user, make_order, db)

    assert o.remaining_amount == Decimal('40.00')


def test_zalegla_wysylka_kr_nie_jest_w_pelni_oplacona(db, make_user, make_order):
    """REGRESJA na etapie E2 (zamówienia 4-etapowe)."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=4,
                   shipping_cost=Decimal('20.00'), proxy_shipping_cost=Decimal('30.00'))
    o.paid_amount = Decimal('120.00')
    db.session.commit()

    assert o.is_fully_paid is False
    assert o.is_partially_paid is True


# === Zachowanie niezmienione ===

def test_pelna_wplata_wszystkich_etapow(db, make_user, make_order):
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=4,
                   shipping_cost=Decimal('20.00'), proxy_shipping_cost=Decimal('30.00'),
                   customs_vat_sale_cost=Decimal('40.00'))
    o.paid_amount = Decimal('190.00')
    db.session.commit()

    assert o.is_fully_paid is True
    assert o.is_overpaid is False
    assert o.is_partially_paid is False
    assert o.remaining_amount == Decimal('0.00')


def test_nadplata_ponad_pelna_naleznosc(db, make_user, make_order):
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=3,
                   shipping_cost=Decimal('20.00'), customs_vat_sale_cost=Decimal('40.00'))
    o.paid_amount = Decimal('200.00')
    db.session.commit()

    assert o.is_overpaid is True
    assert o.is_fully_paid is False
    assert o.remaining_amount == Decimal('0.00')


def test_brak_wplaty(db, make_user, make_order):
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='on_hand',
                   shipping_cost=Decimal('20.00'))

    assert o.is_fully_paid is False
    assert o.is_partially_paid is False
    assert o.is_overpaid is False
    assert o.remaining_amount == Decimal('120.00')


def test_on_hand_bez_zmiany_zachowania(db, make_user, make_order):
    """on_hand nie ma E2 ani E3 — dla niego total_to_pay == grand_total."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='on_hand',
                   shipping_cost=Decimal('20.00'), customs_vat_sale_cost=Decimal('40.00'))
    o.paid_amount = Decimal('120.00')
    db.session.commit()

    assert o.is_fully_paid is True
    assert o.remaining_amount == Decimal('0.00')


def test_zerowa_naleznosc_nie_jest_oplacona(db, make_user, make_order):
    """Zachowany warunek 'jest co płacić' — zamówienie 0 zł nie jest opłacone."""
    u = make_user()
    o = make_order(u, total_amount=Decimal('0.00'), order_type='on_hand',
                   shipping_cost=Decimal('0.00'))

    assert o.is_fully_paid is False
    assert o.is_overpaid is False


# === grand_total zostaje sumą E1+E4 ===

def test_grand_total_pozostaje_e1_plus_e4(db, make_user, make_order):
    """Świadoma granica zmiany: grand_total to suma wyświetlana, nie miara opłacenia."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=4,
                   shipping_cost=Decimal('20.00'), proxy_shipping_cost=Decimal('30.00'),
                   customs_vat_sale_cost=Decimal('40.00'))

    assert o.grand_total == Decimal('120.00')
    assert o.total_to_pay == Decimal('190.00')
