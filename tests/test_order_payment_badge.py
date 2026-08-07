"""Badge płatności na kafelkach zamówień (widok LIVE oferty, podsumowanie strony).

`Order.payment_badge` musi mierzyć wpłaty względem PEŁNEJ należności ze wszystkich
etapów (`Order.total_to_pay`: E1 produkt + E2 wysyłka KR + E3 cło/VAT + E4 wysyłka PL).
Wcześniej opierał się na `is_fully_paid`/`is_overpaid`, które porównują `paid_amount`
z `grand_total` = E1 + E4 — przez co zamówienie z opłaconym produktem i wysyłką PL,
ale zaległym cłem lub wysyłką z Korei, dostawało badge „Opłacone".

Parytet z filtrem płatności na liście klienta — patrz
tests/test_client_orders_payment_filter.py.
"""
from decimal import Decimal


def _confirm(db, order, stage, amount, status='approved'):
    from modules.orders.models import PaymentConfirmation
    db.session.add(PaymentConfirmation(order_id=order.id, payment_stage=stage,
                                       amount=Decimal(str(amount)), status=status))
    db.session.commit()


# === Regresje: zaległy etap nie może uchodzić za opłacony ===

def test_zalegle_clo_nie_daje_badge_oplacone(db, make_user, make_order):
    """REGRESJA: E1 produkt + E4 wysyłka PL opłacone, E3 cło zaległe → Nieopłacone."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=3,
                   shipping_cost=Decimal('20.00'), customs_vat_sale_cost=Decimal('40.00'))
    o.paid_amount = Decimal('120.00')          # E1 + E4, bez E3
    db.session.commit()

    assert o.payment_badge['state'] == 'unpaid'


def test_zalegla_wysylka_kr_nie_daje_badge_oplacone(db, make_user, make_order):
    """REGRESJA: zamówienie 4-etapowe z zaległym E2 (wysyłka z Korei) → Nieopłacone."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=4,
                   shipping_cost=Decimal('20.00'), proxy_shipping_cost=Decimal('30.00'))
    o.paid_amount = Decimal('120.00')          # E1 + E4, bez E2
    db.session.commit()

    assert o.payment_badge['state'] == 'unpaid'


def test_zalegly_etap_z_oczekujacym_potwierdzeniem_daje_pending(db, make_user, make_order):
    """Zaległe cło, ale klient wgrał potwierdzenie → 'Wgrane potwierdzenie'."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=3,
                   shipping_cost=Decimal('20.00'), customs_vat_sale_cost=Decimal('40.00'))
    o.paid_amount = Decimal('120.00')
    db.session.commit()
    _confirm(db, o, 'customs_vat', '40.00', status='pending')

    assert o.payment_badge['state'] == 'pending'


# === Stany pozytywne ===

def test_wszystkie_etapy_oplacone_daje_badge_oplacone(db, make_user, make_order):
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=4,
                   shipping_cost=Decimal('20.00'), proxy_shipping_cost=Decimal('30.00'),
                   customs_vat_sale_cost=Decimal('40.00'))
    o.paid_amount = Decimal('190.00')          # E1+E2+E3+E4
    db.session.commit()

    assert o.payment_badge['state'] == 'paid'


def test_nadplata_daje_badge_oplacone(db, make_user, make_order):
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='on_hand',
                   shipping_cost=Decimal('20.00'))
    o.paid_amount = Decimal('150.00')
    db.session.commit()

    assert o.payment_badge['state'] == 'paid'


def test_pelna_wplata_wygrywa_z_oczekujacym_potwierdzeniem(db, make_user, make_order):
    """Gdy wszystko opłacone, wiszące potwierdzenie nie cofa badge do 'pending'."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='on_hand',
                   shipping_cost=Decimal('20.00'))
    o.paid_amount = Decimal('120.00')
    db.session.commit()
    _confirm(db, o, 'domestic_shipping', '20.00', status='pending')

    assert o.payment_badge['state'] == 'paid'


# === Warunki etapowe (etap nie dotyczy → nie blokuje badge) ===

def test_on_hand_ignoruje_clo(db, make_user, make_order):
    """on_hand nie ma etapu E3 — kwota cła nie może blokować badge."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='on_hand',
                   shipping_cost=Decimal('20.00'), customs_vat_sale_cost=Decimal('40.00'))
    o.paid_amount = Decimal('120.00')
    db.session.commit()

    assert o.payment_badge['state'] == 'paid'


def test_trzyetapowe_ignoruje_wysylke_kr(db, make_user, make_order):
    """E2 dotyczy tylko zamówień 4-etapowych."""
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=3,
                   shipping_cost=Decimal('20.00'), proxy_shipping_cost=Decimal('30.00'))
    o.paid_amount = Decimal('120.00')
    db.session.commit()

    assert o.payment_badge['state'] == 'paid'


# === Stany negatywne ===

def test_brak_wplaty_daje_badge_nieoplacone(db, make_user, make_order):
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='on_hand',
                   shipping_cost=Decimal('20.00'))

    assert o.payment_badge['state'] == 'unpaid'


def test_odrzucone_potwierdzenie_nie_daje_pending(db, make_user, make_order):
    u = make_user()
    o = make_order(u, total_amount=100.00, order_type='on_hand',
                   shipping_cost=Decimal('20.00'))
    _confirm(db, o, 'product', '100.00', status='rejected')

    assert o.payment_badge['state'] == 'unpaid'


def test_zerowa_naleznosc_nie_daje_badge_oplacone(db, make_user, make_order):
    """Zamówienie bez żadnej należności nie jest 'opłacone' — zachowanie sprzed zmiany."""
    u = make_user()
    o = make_order(u, total_amount=Decimal('0.00'), order_type='on_hand',
                   shipping_cost=Decimal('0.00'))

    assert o.payment_badge['state'] == 'unpaid'


# === Spójność z filtrem listy klienta ===

def test_badge_zgadza_sie_z_filtrem_platnosci(db, make_user, make_order):
    """Badge 'paid' ⟺ zamówienie wpada do filtra 'paid' na liście klienta."""
    from modules.orders.models import Order
    from modules.orders.routes import apply_payment_status_filter

    u = make_user()
    zalegle = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=3,
                         status='oczekujace', shipping_cost=Decimal('20.00'),
                         customs_vat_sale_cost=Decimal('40.00'))
    zalegle.paid_amount = Decimal('120.00')
    oplacone = make_order(u, total_amount=100.00, order_type='on_hand', status='oczekujace',
                          shipping_cost=Decimal('20.00'))
    oplacone.paid_amount = Decimal('120.00')
    db.session.commit()

    z_filtra = {o.id for o in apply_payment_status_filter(
        Order.query.filter_by(user_id=u.id), 'paid')}
    z_badge = {o.id for o in (zalegle, oplacone) if o.payment_badge['state'] == 'paid'}

    assert z_filtra == z_badge == {oplacone.id}
