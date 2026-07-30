from decimal import Decimal


def test_build_reminder_message_for_customs_vat_stage(app, db, make_user, make_order):
    from utils.email_manager import EmailManager

    order = make_order(
        make_user(email='klient@example.com'),
        total_amount=Decimal('100.00'),
        order_type='exclusive',
        customs_vat_sale_cost=Decimal('45.00'),
    )

    with app.test_request_context():
        msg = EmailManager.build_payment_reminder_message(order, stage='customs_vat')

    assert msg is not None
    assert 'klient@example.com' in msg.recipients


def test_build_reminder_message_none_when_stage_already_paid(app, db, make_user, make_order):
    from decimal import Decimal
    from modules.orders.models import PaymentConfirmation
    from utils.email_manager import EmailManager

    order = make_order(
        make_user(email='klient2@example.com'),
        total_amount=Decimal('100.00'),
        order_type='exclusive',
        customs_vat_sale_cost=Decimal('45.00'),
    )
    db.session.add(PaymentConfirmation(
        order_id=order.id, payment_stage='customs_vat', status='approved', amount=Decimal('45.00')
    ))
    db.session.commit()

    with app.test_request_context():
        msg = EmailManager.build_payment_reminder_message(order, stage='customs_vat')

    assert msg is None


def test_build_reminder_message_default_stage_uses_effective_total_for_partial_fulfillment(
    app, db, make_user, make_order
):
    """
    Domyślne wywołanie (bez `stage`, jak w app.py:709) buduje przypomnienie
    dla etapu 'product'. Przy częściowej realizacji zamówienia (np. brak
    towaru w komplecie) kwota w mailu ma być liczona wg effective_total
    (kwota faktycznie należna), a NIE pełnej total_amount — to zachowanie
    sprzed Task 6, przywrócone po recenzji.
    """
    from modules.orders.models import OrderItem
    from utils.email_manager import EmailManager

    order = make_order(
        make_user(email='klient3@example.com'),
        total_amount=Decimal('100.00'),
        order_type='exclusive',
    )
    # Jeden produkt zamówiony w ilości 2, ale zrealizowany tylko w ilości 1
    # (fulfilled_quantity < quantity) -> effective_total = 50.00, nie 100.00.
    db.session.add(OrderItem(
        order_id=order.id,
        quantity=2,
        price=Decimal('50.00'),
        total=Decimal('100.00'),
        fulfilled_quantity=1,
    ))
    db.session.commit()

    assert order.effective_total == Decimal('50.00')

    with app.test_request_context():
        msg = EmailManager.build_payment_reminder_message(order)

    assert msg is not None
    assert 'klient3@example.com' in msg.recipients
    assert '50.00 PLN' in msg.html
    assert '100.00 PLN' not in msg.html
