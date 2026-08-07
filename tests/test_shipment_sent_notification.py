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
