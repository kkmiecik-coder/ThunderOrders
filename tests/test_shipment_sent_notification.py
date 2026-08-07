"""Jeden mail i jeden push o wysyłce na paczkę zamiast na każde zamówienie."""

import pytest


# ---------- Task 1: szablon i funkcja wysyłająca ----------

def test_template_lists_all_order_numbers(app):
    """W mailu o paczce muszą być wszystkie numery zamówień, nie tylko pierwszy."""
    from flask import render_template

    with app.test_request_context():
        html = render_template(
            'emails/shipment_sent.html',
            user_name='Anna',
            request_number='WYS/000123',
            order_numbers=['PO/00000001', 'PO/00000002', 'PO/00000003'],
            tracking_number='123456789012',
            courier_name='InPost',
            tracking_url='https://inpost.pl/sledzenie/123456789012',
            shipping_requests_url='https://thunderorders.cloud/zlecenia',
        )

    assert 'WYS/000123' in html
    assert 'PO/00000001' in html
    assert 'PO/00000002' in html
    assert 'PO/00000003' in html
    assert '123456789012' in html
    assert 'InPost' in html
    assert 'https://inpost.pl/sledzenie/123456789012' in html


def test_template_without_tracking_hides_tracking_block(app):
    """Bez numeru przesyłki nie ma ramki kuriera ani przycisku śledzenia."""
    from flask import render_template

    with app.test_request_context():
        html = render_template(
            'emails/shipment_sent.html',
            user_name='Anna',
            request_number='WYS/000123',
            order_numbers=['PO/00000001'],
            tracking_number=None,
            courier_name=None,
            tracking_url=None,
            shipping_requests_url='https://thunderorders.cloud/zlecenia',
        )

    assert 'PO/00000001' in html
    assert 'Numer przesyłki' not in html
    assert 'Śledź przesyłkę' not in html


def test_template_without_courier_name_falls_back(app):
    """Numer przesyłki bez nazwy kuriera nie może pokazać dosłownego 'None'."""
    from flask import render_template

    with app.test_request_context():
        html = render_template(
            'emails/shipment_sent.html',
            user_name='Anna',
            request_number='WYS/000123',
            order_numbers=['PO/00000001'],
            tracking_number='123456789012',
            courier_name=None,
            tracking_url=None,
            shipping_requests_url='https://thunderorders.cloud/zlecenia',
        )

    assert 'None' not in html
    assert 'Kurier' in html


def test_subject_differs_with_and_without_tracking(app, monkeypatch):
    """Temat maila rozróżnia obie sytuacje — treść w środku jest ta sama."""
    import utils.email_sender as es

    captured = []
    monkeypatch.setattr(es, 'send_email',
                        lambda **kw: captured.append(kw) or True)

    with app.app_context():
        es.send_shipment_sent_email(
            user_email='klient@example.com', user_name='Anna',
            request_number='WYS/000123', order_numbers=['PO/00000001'],
            tracking_number='123456789012', courier_name='InPost',
            tracking_url=None, shipping_requests_url='https://x/zlecenia')
        es.send_shipment_sent_email(
            user_email='klient@example.com', user_name='Anna',
            request_number='WYS/000123', order_numbers=['PO/00000001'],
            shipping_requests_url='https://x/zlecenia')

    assert 'Numer przesyłki' in captured[0]['subject']
    assert 'WYS/000123' in captured[0]['subject']
    assert 'wysłana' in captured[1]['subject']
    assert captured[0]['template'] == 'shipment_sent'
    assert captured[1]['tracking_number'] is None


# ---------- Task 2: EmailManager.notify_shipment_sent ----------

def _sr_with_orders(db, make_user, make_order, count=3, tracking=None, courier=None):
    """Zlecenie wysyłki z podanym numerem zamówień, gotowe do powiadomienia."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    u = make_user()
    sr = ShippingRequest(request_number=ShippingRequest.generate_request_number(),
                         user_id=u.id, status='spakowane',
                         tracking_number=tracking, courier=courier)
    db.session.add(sr)
    db.session.commit()
    for _ in range(count):
        o = make_order(u, status='spakowane')
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
    db.session.commit()
    return sr


@pytest.fixture
def captured_email(monkeypatch):
    """Przechwytuje wywołania send_shipment_sent_email zamiast wysyłać maile."""
    import utils.email_sender as es

    calls = []
    monkeypatch.setattr(es, 'send_shipment_sent_email',
                        lambda **kw: calls.append(kw) or True)
    return calls


def test_email_sends_once_with_all_order_numbers(app, db, make_user, make_order,
                                                 captured_email):
    """Trzy zamówienia w paczce = jeden mail, w środku trzy numery."""
    from utils.email_manager import EmailManager

    sr = _sr_with_orders(db, make_user, make_order, count=3,
                         tracking='ABC123', courier='inpost')

    with app.test_request_context():
        EmailManager.notify_shipment_sent(
            sr, tracking_number='ABC123', courier='inpost',
            courier_name='InPost', tracking_url='https://inpost.pl/ABC123')

    assert len(captured_email) == 1
    assert len(captured_email[0]['order_numbers']) == 3
    assert captured_email[0]['request_number'] == sr.request_number
    assert captured_email[0]['tracking_number'] == 'ABC123'
    assert captured_email[0]['tracking_url'] == 'https://inpost.pl/ABC123'


def test_email_without_tracking_passes_none(app, db, make_user, make_order,
                                            captured_email):
    """Bez numeru przesyłki mail idzie, ale bez danych śledzenia."""
    from utils.email_manager import EmailManager

    sr = _sr_with_orders(db, make_user, make_order, count=2)

    with app.test_request_context():
        EmailManager.notify_shipment_sent(sr)

    assert len(captured_email) == 1
    assert captured_email[0]['tracking_number'] is None
    assert len(captured_email[0]['order_numbers']) == 2


def test_email_builds_tracking_url_when_missing(app, db, make_user, make_order,
                                                captured_email):
    """Gdy URL nie podano, a jest kurier i numer — metoda go generuje."""
    from utils.email_manager import EmailManager

    sr = _sr_with_orders(db, make_user, make_order, count=1,
                         tracking='XYZ999', courier='inpost')

    with app.test_request_context():
        EmailManager.notify_shipment_sent(
            sr, tracking_number='XYZ999', courier='inpost', courier_name='InPost')

    assert len(captured_email) == 1
    assert captured_email[0]['tracking_url']
    assert 'XYZ999' in captured_email[0]['tracking_url']


def test_email_skipped_when_toggle_disabled(app, db, make_user, make_order,
                                            captured_email, monkeypatch):
    """Wyłączony przełącznik 'Numer przesyłki' blokuje mail o paczce z numerem."""
    from utils.email_manager import EmailManager

    sr = _sr_with_orders(db, make_user, make_order, count=2,
                         tracking='ABC123', courier='inpost')
    monkeypatch.setattr(EmailManager, 'is_email_enabled',
                        classmethod(lambda cls, key: key != 'notify_tracking_added'))

    with app.test_request_context():
        EmailManager.notify_shipment_sent(
            sr, tracking_number='ABC123', courier='inpost', courier_name='InPost')

    assert captured_email == []


def test_email_without_tracking_uses_status_toggle(app, db, make_user, make_order,
                                                    captured_email, monkeypatch):
    """Bez numeru przesyłki liczy się przełącznik 'Zmiana statusu', nie 'Numer przesyłki'.

    Odwrotność sąsiedniego testu: tu wyłączamy notify_status_change, a
    notify_tracking_added zostawiamy włączony. Gdyby metoda sprawdzała na
    sztywno tylko notify_tracking_added (ignorując brak numeru przesyłki),
    ten test by tego nie złapał — a ten test właśnie po to istnieje.
    """
    from utils.email_manager import EmailManager

    sr = _sr_with_orders(db, make_user, make_order, count=2)
    monkeypatch.setattr(EmailManager, 'is_email_enabled',
                        classmethod(lambda cls, key: key != 'notify_status_change'))

    with app.test_request_context():
        EmailManager.notify_shipment_sent(sr)

    assert captured_email == []


def test_email_skipped_when_no_recipient(app, db, make_user, make_order,
                                         captured_email):
    """Brak adresu e-mail kończy się cicho, bez wyjątku.

    Kolumna users.email jest NOT NULL, więc adresu nie da się wyzerować —
    brak odbiorcy odtwarzamy zleceniem bez konta klienta i bez zamówień,
    czyli dokładnie tą sytuacją, przed którą broni się metoda.
    """
    from utils.email_manager import EmailManager

    sr = _sr_with_orders(db, make_user, make_order, count=0)
    sr.user_id = None
    db.session.commit()

    with app.test_request_context():
        EmailManager.notify_shipment_sent(sr)

    assert captured_email == []
