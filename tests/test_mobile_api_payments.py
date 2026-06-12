"""Testy E6: mobilne API płatności (metody, lista potwierdzeń, BULK upload dowodu).

_auth skopiowany z tests/test_mobile_api_orders.py. Multipart: BytesIO + content_type.
"""
import io
import json
import os
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _cleanup_proofs(app):
    folder = os.path.join(app.root_path, 'uploads', 'payment_confirmations')
    before = set(os.listdir(folder)) if os.path.isdir(folder) else set()
    yield
    if os.path.isdir(folder):
        for f in set(os.listdir(folder)) - before:
            try:
                os.remove(os.path.join(folder, f))
            except OSError:
                pass


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


def test_proof_requires_jwt(client, db, make_user, make_order):
    u = make_user(); o = make_order(u)
    _add_payment(db, o, 'domestic_shipping', proof_file='abc.png')
    assert client.get('/api/mobile/v1/payment-confirmations/proof/abc.png').status_code == 401


def test_proof_owner_gets_file(client, db, make_user, make_order, app):
    import os
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', shipping_cost=Decimal('10.00'))
    folder = os.path.join(app.root_path, 'uploads', 'payment_confirmations')
    os.makedirs(folder, exist_ok=True)
    fname = 'e6test_owner.png'
    with open(os.path.join(folder, fname), 'wb') as f:
        f.write(_tiny_png().read())
    _add_payment(db, o, 'domestic_shipping', proof_file=fname)
    try:
        r = client.get(f'/api/mobile/v1/payment-confirmations/proof/{fname}', headers=h)
        assert r.status_code == 200
        assert r.data[:8] == b'\x89PNG\r\n\x1a\n'
    finally:
        os.remove(os.path.join(folder, fname))


def test_proof_other_user_404(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    other = make_user()
    o = make_order(other, order_type='on_hand', shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'domestic_shipping', proof_file='secret.png')
    r = client.get('/api/mobile/v1/payment-confirmations/proof/secret.png', headers=h)
    assert r.status_code == 404                               # maskowanie istnienia


def test_proof_missing_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    assert client.get('/api/mobile/v1/payment-confirmations/proof/nope.png',
                      headers=h).status_code == 404


# === Task 4: BULK upload (multipart) ===

def _post_proof(client, headers, items, fileobj=None, filename='proof.png', method_id=None,
                raw_items=None):
    data = {'items': raw_items if raw_items is not None else json.dumps(items),
            'file': (fileobj or _tiny_png(), filename)}
    if method_id is not None:
        data['payment_method_id'] = str(method_id)
    return client.post('/api/mobile/v1/payment-confirmations', data=data,
                       content_type='multipart/form-data', headers=headers)


def _pair(order, stage):
    return {'order_id': order.id, 'payment_stage': stage}


def test_upload_requires_jwt(client, db, make_user, make_order):
    u = make_user(); o = make_order(u, order_type='on_hand', shipping_cost=Decimal('10.00'))
    r = client.post('/api/mobile/v1/payment-confirmations',
                    data={'items': json.dumps([_pair(o, 'domestic_shipping')]),
                          'file': (_tiny_png(), 'p.png')},
                    content_type='multipart/form-data')
    assert r.status_code == 401


def test_upload_happy_single_pair(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('15.00'))
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping')])
    assert r.status_code == 200
    d = r.get_json()['data']
    assert d['count'] == 1
    c = d['confirmations'][0]
    assert c['order_id'] == o.id and c['payment_stage'] == 'domestic_shipping'
    assert c['status'] == 'pending' and c['amount'] == 1500 and c['action'] == 'created'
    assert d['proof_url'].startswith('http')


def test_upload_bulk_multi_order_shared_file(client, db, make_user, make_order):
    # SERCE D2: 2 zamówienia × różne etapy, JEDEN plik → 3 wiersze z tym samym proof_file
    h, u = _auth(client, db, make_user)
    o1 = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    o2 = make_order(u, order_type='pre_order', status='nowe', payment_stages=3,
                    customs_vat_sale_cost=Decimal('20.00'), shipping_cost=Decimal('5.00'))
    r = _post_proof(client, h, [_pair(o1, 'domestic_shipping'),
                                _pair(o2, 'customs_vat'), _pair(o2, 'domestic_shipping')])
    assert r.status_code == 200
    d = r.get_json()['data']
    assert d['count'] == 3
    from modules.orders.models import PaymentConfirmation
    rows = PaymentConfirmation.query.all()
    assert len({row.proof_file for row in rows}) == 1         # jeden współdzielony plik
    by = {(c['order_id'], c['payment_stage']): c for c in d['confirmations']}
    assert by[(o2.id, 'customs_vat')]['amount'] == 2000       # grosze per para


def test_upload_dedupes_pairs(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping'), _pair(o, 'domestic_shipping')])
    assert r.status_code == 200 and r.get_json()['data']['count'] == 1


def test_upload_bad_items_json_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = _post_proof(client, h, None, raw_items='not-json')
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_upload_empty_items_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = _post_proof(client, h, [])
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_upload_unknown_stage_enum_400(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = _post_proof(client, h, [_pair(o, 'banana')])
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_upload_foreign_order_404_all_or_nothing(client, db, make_user, make_order):
    # P1: jedna cudza para → CAŁY bulk 404 (nic nie utworzone, plik nie zapisany)
    h, u = _auth(client, db, make_user)
    other = make_user()
    mine = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    foreign = make_order(other, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = _post_proof(client, h, [_pair(mine, 'domestic_shipping'), _pair(foreign, 'product')])
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'order_not_found'
    assert foreign.id in r.get_json()['error']['details']['missing_order_ids']
    from modules.orders.models import PaymentConfirmation
    assert PaymentConfirmation.query.count() == 0             # nic nie powstało


def test_upload_stage_not_applicable_400(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping'), _pair(o, 'korean_shipping')])
    assert r.status_code == 400
    e = r.get_json()['error']
    assert e['code'] == 'stage_not_applicable'
    assert e['details']['failures'][0]['payment_stage'] == 'korean_shipping'


def test_upload_approved_pair_409_all_or_nothing(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'product', status='approved')
    r = _post_proof(client, h, [_pair(o, 'product'), _pair(o, 'domestic_shipping')])
    assert r.status_code == 409 and r.get_json()['error']['code'] == 'stage_not_uploadable'


def test_upload_e1_pending_overwrite_e4_pending_blocks(client, db, make_user, make_order):
    # P2: asymetria pending — parytet z webem
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'product', status='pending', proof_file='old.png')
    r = _post_proof(client, h, [_pair(o, 'product')])
    assert r.status_code == 200                                # E1 pending → nadpis
    assert r.get_json()['data']['confirmations'][0]['action'] == 'overwritten'
    _add_payment(db, o, 'domestic_shipping', status='pending')
    r2 = _post_proof(client, h, [_pair(o, 'domestic_shipping')])
    assert r2.status_code == 409                               # E4 pending → blokada


def test_upload_overwrites_rejected(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    pc = _add_payment(db, o, 'domestic_shipping', status='rejected', proof_file='old.png')
    pc.rejection_reason = 'Nieczytelne'; db.session.commit()
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping')])
    assert r.status_code == 200
    db.session.refresh(pc)
    assert pc.status == 'pending' and pc.rejection_reason is None and pc.proof_file != 'old.png'


def test_upload_missing_file_400(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = client.post('/api/mobile/v1/payment-confirmations',
                    data={'items': json.dumps([_pair(o, 'domestic_shipping')])},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_upload_bad_extension_400(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping')],
                    fileobj=io.BytesIO(b'hello'), filename='evil.txt')
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_file'


def test_upload_oversize_400(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    big = io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'0' * (5 * 1024 * 1024 + 10))
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping')], fileobj=big, filename='big.png')
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'file_too_large'


def test_upload_corrupt_image_400(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping')],
                    fileobj=io.BytesIO(b'not really a png'), filename='fake.png')
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_file'


def test_upload_optional_payment_method(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    m = _make_method(db, name='BLIK')
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping')], method_id=m.id)
    assert r.status_code == 200
    from modules.orders.models import PaymentConfirmation
    assert PaymentConfirmation.query.first().payment_method_id == m.id


# === Task 5: lista potwierdzeń (GET, tab=active|archive) ===

def test_confirmations_requires_jwt(client, db, make_user):
    assert client.get('/api/mobile/v1/payment-confirmations').status_code == 401


def test_confirmations_invalid_tab_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.get('/api/mobile/v1/payment-confirmations?tab=banana', headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_confirmations_active_shape(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    d = client.get('/api/mobile/v1/payment-confirmations', headers=h).get_json()['data']
    assert d['tab'] == 'active'
    row = next(r for r in d['orders'] if r['id'] == o.id)
    assert 'payment_stages' in row
    assert {'total_to_pay', 'paid_amount', 'remaining_to_pay'} <= set(row['payment_summary'])
    assert row['all_approved'] is False
    assert 'active_total' in d and 'archive_count' in d


def test_confirmations_archive_tab(client, db, make_user, make_order):
    from datetime import timedelta
    from modules.orders.models import get_local_now
    h, u = _auth(client, db, make_user)
    old = get_local_now() - timedelta(days=5)
    o = make_order(u, order_type='on_hand', status='dostarczone_gom',
                   shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'product', status='approved', updated_at=old)
    _add_payment(db, o, 'domestic_shipping', status='approved', updated_at=old)
    active = client.get('/api/mobile/v1/payment-confirmations?tab=active',
                        headers=h).get_json()['data']
    archive = client.get('/api/mobile/v1/payment-confirmations?tab=archive',
                         headers=h).get_json()['data']
    assert all(r['id'] != o.id for r in active['orders'])
    assert any(r['id'] == o.id for r in archive['orders'])
    assert archive['archive_count'] == 1


def test_confirmations_recent_paid_stays_active(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='dostarczone_gom',
                   shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'product', status='approved')
    _add_payment(db, o, 'domestic_shipping', status='approved')
    active = client.get('/api/mobile/v1/payment-confirmations?tab=active',
                        headers=h).get_json()['data']
    row = next(r for r in active['orders'] if r['id'] == o.id)
    assert row['all_approved'] is True
