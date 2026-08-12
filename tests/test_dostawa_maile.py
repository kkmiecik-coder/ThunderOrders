"""Maile dostawy — przełączniki, adresaci, treść."""


def _zlecenie(db, user, numer='WYS/000200', status='wyslane'):
    from modules.orders.models import ShippingRequest
    sr = ShippingRequest(request_number=numer, user_id=user.id, status=status)
    db.session.add(sr)
    db.session.commit()
    return sr


def _wlacz(db, klucz, wartosc=True):
    import json
    from modules.auth.models import Settings
    from utils.email_manager import EmailManager
    config = Settings.get_value('email_notifications_config', {}) or {}
    config[klucz] = wartosc
    # Settings.set_value() robi str(value), nie json.dumps(value) — z gołym
    # dict-em zapisałby reprezentację Pythona ({'a': False}, pojedyncze cudzysłowy,
    # wielka litera False), której get_value(type='json') nie odczyta z powrotem
    # (json.loads rzuci wyjątkiem, is_email_enabled po cichu wróci do True).
    # Produkcyjny kod (modules/orders/routes.py:update_email_notification_settings)
    # zawsze serializuje ręcznie przed zapisem — ten helper musi robić to samo.
    Settings.set_value('email_notifications_config', json.dumps(config), type='json')
    db.session.commit()
    EmailManager.clear_email_config_cache()


def test_przypomnienie_buduje_wiadomosc(app, db, make_user, make_order):
    from modules.orders.models import ShippingRequestOrder
    from utils.email_manager import EmailManager

    user = make_user(email='klient@example.com')
    sr = _zlecenie(db, user)
    order = make_order(user, status='wyslane')
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=order.id))
    db.session.commit()

    with app.test_request_context():
        msg = EmailManager.build_delivery_confirmation_message(sr)

    assert msg is not None
    assert msg.recipients == ['klient@example.com']
    assert sr.request_number in msg.html


def test_przypomnienie_respektuje_przelacznik(app, db, make_user):
    from utils.email_manager import EmailManager

    _wlacz(db, 'notify_delivery_confirmation', False)
    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000201')

    with app.test_request_context():
        assert EmailManager.build_delivery_confirmation_message(sr) is None


def test_przypomnienie_bez_adresata_zwraca_none(app, db):
    from modules.orders.models import ShippingRequest
    from utils.email_manager import EmailManager
    from extensions import db as _db

    sr = ShippingRequest(request_number='WYS/000202', user_id=None, status='wyslane')
    _db.session.add(sr)
    _db.session.commit()

    with app.test_request_context():
        assert EmailManager.build_delivery_confirmation_message(sr) is None


def test_mail_o_automatycznym_domknieciu_podaje_liczbe_dni(app, db, make_user):
    from modules.auth.models import Settings
    from utils.email_manager import EmailManager

    Settings.set_value('delivery_autocomplete_days', 14, type='integer')
    db.session.commit()

    user = make_user(email='auto@example.com')
    sr = _zlecenie(db, user, 'WYS/000203', status='dostarczone')

    with app.test_request_context():
        msg = EmailManager.build_delivery_autoclosed_message(sr)

    assert msg is not None
    assert '14' in msg.html


def test_mail_do_adminow_zawiera_ocene(app, db, make_user, monkeypatch):
    from modules.orders.review_models import DeliveryReview
    from utils.email_manager import EmailManager

    wyslane = []
    monkeypatch.setattr(
        EmailManager, 'get_admin_notification_emails',
        classmethod(lambda cls: ['admin@example.com']))
    monkeypatch.setattr(
        'utils.email_sender.send_email',
        lambda to, subject, template, **kw: wyslane.append((to, kw)) or True)

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000204', status='dostarczone')
    db.session.add(DeliveryReview(
        shipping_request_id=sr.id, user_id=user.id, rating=5, comment='Super'))
    db.session.commit()

    with app.test_request_context():
        EmailManager.notify_admin_delivery_confirmed(sr)

    assert wyslane, 'mail do adminów nie poszedł'
    assert wyslane[0][1]['rating'] == 5
    assert wyslane[0][1]['comment'] == 'Super'
