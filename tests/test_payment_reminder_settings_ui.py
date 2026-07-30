"""
Test payment reminder settings UI.
Verifies that rules are displayed regardless of payment_stage.
"""

def test_settings_page_lists_rule_regardless_of_saved_stage(db, make_user, client, login):
    """Test that a rule with payment_stage='shipping_kr' appears on the settings page."""
    from modules.offers.reminder_models import PaymentReminderConfig

    admin = make_user(role='admin', profile_completed=True)
    login(admin)

    rule = PaymentReminderConfig(reminder_type='before_deadline', hours=48, payment_stage='shipping_kr', enabled=True)
    db.session.add(rule)
    db.session.commit()

    resp = client.get('/admin/offers/settings')

    assert resp.status_code == 200
    assert b'48h przed terminem p' in resp.data
