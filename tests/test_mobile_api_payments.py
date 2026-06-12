"""Testy E6: mobilne API płatności (metody, lista potwierdzeń, BULK upload dowodu).

_auth skopiowany z tests/test_mobile_api_orders.py. Multipart: BytesIO + content_type.
"""
import io
import json
from decimal import Decimal


def _auth(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': u.email, 'password': 'Haslo123!'})
    token = r.get_json()['data']['access_token']
    return {'Authorization': f'Bearer {token}'}, u


def _tiny_png():
    """Najmniejszy WALIDNY PNG (PIL load przejdzie) jako bajty."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (1, 1), (255, 0, 0)).save(buf, 'PNG')
    buf.seek(0)
    return buf


def _add_payment(db, order, stage, status='pending', amount=Decimal('20.00'),
                 proof_file='proof.jpg', updated_at=None):
    from modules.orders.models import PaymentConfirmation
    pc = PaymentConfirmation(order_id=order.id, payment_stage=stage,
                             amount=amount, status=status, proof_file=proof_file)
    db.session.add(pc); db.session.commit()
    if updated_at is not None:
        pc.updated_at = updated_at
        db.session.commit()
    return pc


def _make_method(db, **kw):
    from modules.payments.models import PaymentMethod
    m = PaymentMethod(name=kw.pop('name', 'BLIK'), is_active=kw.pop('is_active', True),
                      sort_order=kw.pop('sort_order', 0), **kw)
    db.session.add(m); db.session.commit()
    return m


def test_payment_methods_requires_jwt(client, db, make_user):
    assert client.get('/api/mobile/v1/payment-methods').status_code == 401


def test_payment_methods_shape_and_active_only(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _make_method(db, name='BLIK', account_number='500600700', sort_order=1)
    _make_method(db, name='Stara', is_active=False, sort_order=0)   # nieaktywna — pomijana
    r = client.get('/api/mobile/v1/payment-methods', headers=h)
    assert r.status_code == 200
    methods = r.get_json()['data']['methods']
    assert [m['name'] for m in methods] == ['BLIK']
    m = methods[0]
    assert set(m) >= {'id', 'name', 'recipient', 'account_number', 'account_number_label',
                      'code', 'code_label', 'transfer_title', 'additional_info', 'sort_order',
                      'logo_light_url', 'logo_dark_url'}


def test_payment_methods_absolute_logo_url(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _make_method(db, name='Revolut', logo_light='rev.png')
    m = client.get('/api/mobile/v1/payment-methods', headers=h).get_json()['data']['methods'][0]
    assert m['logo_light_url'].startswith('http')
    assert m['logo_light_url'].endswith('/static/uploads/payment_methods/rev.png')
    assert m['logo_dark_url'] is None
