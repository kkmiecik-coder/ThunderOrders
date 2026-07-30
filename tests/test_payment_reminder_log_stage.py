def test_same_order_and_config_different_stage_both_allowed(db, make_user, make_order):
    from modules.offers.reminder_models import PaymentReminderConfig, PaymentReminderLog

    order = make_order(make_user())
    config = PaymentReminderConfig(reminder_type='before_deadline', hours=24, payment_stage='product')
    db.session.add(config)
    db.session.commit()

    db.session.add(PaymentReminderLog(order_id=order.id, config_id=config.id, stage='product'))
    db.session.add(PaymentReminderLog(order_id=order.id, config_id=config.id, stage='customs_vat'))
    db.session.commit()

    logs = PaymentReminderLog.query.filter_by(order_id=order.id, config_id=config.id).all()
    assert {l.stage for l in logs} == {'product', 'customs_vat'}
