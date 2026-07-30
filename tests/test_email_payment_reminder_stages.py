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
