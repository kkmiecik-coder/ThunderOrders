"""Testy E1 mobilnego API: helpery + sklep on-hand (odczyt) + kurs walut."""

from decimal import Decimal


# ---------------------------------------------------------------------------
# Helpery (Task 1)
# ---------------------------------------------------------------------------

def test_to_grosze(app):
    from modules.api_mobile.helpers import to_grosze
    assert to_grosze(Decimal('99.00')) == 9900
    assert to_grosze(Decimal('0.01')) == 1
    assert to_grosze(123.45) == 12345
    assert to_grosze(0) == 0
    assert to_grosze(None) is None


def test_absolute_static_url(app):
    from modules.api_mobile.helpers import absolute_static_url
    with app.test_request_context():
        assert absolute_static_url('uploads/products/x.jpg') == \
            'http://localhost/static/uploads/products/x.jpg'
        assert absolute_static_url('/uploads/p.jpg') == \
            'http://localhost/static/uploads/p.jpg'
        assert absolute_static_url(None) is None
        assert absolute_static_url('') is None


def test_json_page_envelope(app):
    from modules.api_mobile.helpers import json_page
    with app.test_request_context():
        resp, status = json_page([{'id': 1}], page=2, per_page=12, total=25, has_next=True)
        body = resp.get_json()
    assert status == 200
    assert body['success'] is True
    assert body['data'] == [{'id': 1}]
    assert body['pagination'] == {'page': 2, 'per_page': 12, 'total': 25, 'has_next': True}
