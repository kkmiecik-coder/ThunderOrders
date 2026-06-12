"""Testy serwisu bulk-uploadu potwierdzeń (ekstrakcja z webowej trasy — parytet)."""
import os
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _cleanup_proofs(app):
    folder = os.path.join(app.root_path, 'uploads', 'payment_confirmations')
    before = set(os.listdir(folder)) if os.path.isdir(folder) else set()
    yield
    if os.path.isdir(folder):
        for f in set(os.listdir(folder)) - before:           # usuwa TYLKO pliki z tego testu
            try:
                os.remove(os.path.join(folder, f))
            except OSError:
                pass


def _stages(*pairs):
    """[(order, [stages])] -> kształt order_stages serwisu."""
    return [{'order_id': o.id, 'stages': list(st)} for o, st in pairs]


def test_validate_ok_multi_order(db, make_user, make_order):
    from modules.client.payment_confirmation_service import validate_bulk_upload
    u = make_user()
    o1 = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    o2 = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('5.00'))
    ok, err = validate_bulk_upload(u.id, _stages((o1, ['product', 'domestic_shipping']),
                                                 (o2, ['product'])))
    assert ok and err is None


def test_validate_foreign_order_fails_whole_bulk(db, make_user, make_order):
    from modules.client.payment_confirmation_service import validate_bulk_upload
    u, other = make_user(), make_user()
    mine = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    foreign = make_order(other, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    ok, err = validate_bulk_upload(u.id, _stages((mine, ['product']), (foreign, ['product'])))
    assert not ok and err['code'] == 'orders_not_found'
    assert foreign.id in err['missing_order_ids']            # all-or-nothing (P1)


def test_validate_classifies_not_applicable(db, make_user, make_order):
    # on_hand nie ma E2/E3 → klasyfikacja strukturalna (web tego nie rozróżnia — mobile tak)
    from modules.client.payment_confirmation_service import validate_bulk_upload
    u = make_user()
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    ok, err = validate_bulk_upload(u.id, _stages((o, ['korean_shipping'])))
    assert not ok and err['code'] == 'stage_not_applicable'
    assert err['failures'][0]['payment_stage'] == 'korean_shipping'


def test_validate_pending_asymmetry(db, make_user, make_order):
    # P2: E1 pending PRZECHODZI (nadpis dozwolony); E4 pending ODRZUCA bulk
    from modules.client.payment_confirmation_service import validate_bulk_upload
    from tests.test_mobile_api_payments import _add_payment
    u = make_user()
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'product', status='pending')
    ok, _ = validate_bulk_upload(u.id, _stages((o, ['product'])))
    assert ok                                                 # E1 pending → wolno
    _add_payment(db, o, 'domestic_shipping', status='pending')
    ok2, err2 = validate_bulk_upload(u.id, _stages((o, ['product', 'domestic_shipping'])))
    assert not ok2 and err2['code'] == 'stage_not_uploadable'  # E4 pending → cały bulk pada


def test_validate_approved_rejects(db, make_user, make_order):
    from modules.client.payment_confirmation_service import validate_bulk_upload
    from tests.test_mobile_api_payments import _add_payment
    u = make_user()
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'product', status='approved')
    ok, err = validate_bulk_upload(u.id, _stages((o, ['product'])))
    assert not ok and err['code'] == 'stage_not_uploadable'


def test_record_creates_rows_sharing_file(db, make_user, make_order, make_product):
    from modules.client.payment_confirmation_service import record_bulk_payment_proofs
    from modules.orders.models import PaymentConfirmation, OrderItem
    u = make_user()
    o1 = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    o2 = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('5.00'))
    p = make_product(sale_price=Decimal('50.00'))
    it = OrderItem(order_id=o1.id, product_id=p.id, quantity=1,
                   price=Decimal('50.00'), total=Decimal('50.00'))
    db.session.add(it); db.session.commit()
    entries = record_bulk_payment_proofs(u, _stages((o1, ['product', 'domestic_shipping']),
                                                    (o2, ['domestic_shipping'])),
                                         'shared_file.png', None)
    assert len(entries) == 3
    rows = PaymentConfirmation.query.all()
    assert {r.proof_file for r in rows} == {'shared_file.png'}   # JEDEN plik, wiele wierszy
    assert all(r.status == 'pending' for r in rows)
    by = {(r.order_id, r.payment_stage): r for r in rows}
    assert by[(o1.id, 'product')].amount == Decimal('50.00')      # effective_total
    assert by[(o1.id, 'domestic_shipping')].amount == Decimal('10.00')
    assert by[(o2.id, 'domestic_shipping')].amount == Decimal('5.00')


def test_record_overwrites_rejected_and_skips_approved(db, make_user, make_order):
    from modules.client.payment_confirmation_service import record_bulk_payment_proofs
    from tests.test_mobile_api_payments import _add_payment
    u = make_user()
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    rej = _add_payment(db, o, 'domestic_shipping', status='rejected', proof_file='old.png')
    rej.rejection_reason = 'Nieczytelne'; db.session.commit()
    appr = _add_payment(db, o, 'product', status='approved', proof_file='done.png')
    entries = record_bulk_payment_proofs(u, _stages((o, ['product', 'domestic_shipping'])),
                                         'fresh.png', None)
    db.session.refresh(rej); db.session.refresh(appr)
    assert rej.status == 'pending' and rej.proof_file == 'fresh.png'
    assert rej.rejection_reason is None
    assert appr.status == 'approved' and appr.proof_file == 'done.png'   # P2: skip approved
    assert len(entries) == 1                                  # tylko nadpis liczony (parytet continue)


def test_record_logs_activity_per_pair(db, make_user, make_order):
    from modules.client.payment_confirmation_service import record_bulk_payment_proofs
    from modules.admin.models import ActivityLog
    u = make_user()
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    record_bulk_payment_proofs(u, _stages((o, ['product', 'domestic_shipping'])), 'f.png', None)
    actions = [a.action for a in ActivityLog.query.all()]
    assert actions.count('payment_confirmation_uploaded') == 2


def test_web_upload_route_parity_smoke(client, db, make_user, make_order, login):
    import io, json
    from PIL import Image
    u = make_user(profile_completed=True)        # client_bp.before_request wymaga ukończonego profilu
    login(u)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    buf = io.BytesIO(); Image.new('RGB', (1, 1)).save(buf, 'PNG'); buf.seek(0)
    r = client.post('/client/payment-confirmations/upload',
                    data={'order_stages': json.dumps([{'order_id': o.id,
                                                       'stages': ['domestic_shipping']}]),
                          'proof_file': (buf, 'p.png')},
                    content_type='multipart/form-data',
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert r.get_json()['updated_stages'] == [
        {'order_id': o.id, 'stage': 'domestic_shipping', 'status': 'pending'}]


def test_web_upload_route_rejects_foreign(client, db, make_user, make_order, login):
    import io, json
    u, other = make_user(profile_completed=True), make_user()   # u musi przejść gate profilu
    login(u)
    o = make_order(other, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = client.post('/client/payment-confirmations/upload',
                    data={'order_stages': json.dumps([{'order_id': o.id, 'stages': ['product']}]),
                          'proof_file': (io.BytesIO(b'x'), 'p.png')},
                    content_type='multipart/form-data',
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400 and r.get_json()['success'] is False    # zachowanie weba BEZ zmian



# === Task 5: lista active/archive (serwis) ===

def test_confirmation_orders_base_set_and_owner(db, make_user, make_order):
    from modules.client.payment_confirmation_service import get_confirmation_orders
    u, other = make_user(), make_user()
    inscope = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    make_order(u, order_type='on_hand', status='anulowane')        # poza zbiorem statusów
    make_order(other, order_type='on_hand', status='nowe')         # cudzy
    groups = get_confirmation_orders(u.id)
    assert [o.id for o in groups['payable']] == [inscope.id]
    assert groups['recent_paid'] == [] and groups['archived'] == []


def test_confirmation_orders_archive_split(db, make_user, make_order):
    from modules.client.payment_confirmation_service import get_confirmation_orders
    from datetime import timedelta
    from modules.orders.models import get_local_now
    from tests.test_mobile_api_payments import _add_payment
    u = make_user()
    old = get_local_now() - timedelta(days=5)
    o_arch = make_order(u, order_type='on_hand', status='dostarczone_gom',
                        shipping_cost=Decimal('10.00'))
    _add_payment(db, o_arch, 'product', status='approved', updated_at=old)
    _add_payment(db, o_arch, 'domestic_shipping', status='approved', updated_at=old)
    o_recent = make_order(u, order_type='on_hand', status='dostarczone_gom',
                          shipping_cost=Decimal('10.00'))
    _add_payment(db, o_recent, 'product', status='approved')       # updated_at = teraz
    _add_payment(db, o_recent, 'domestic_shipping', status='approved')
    groups = get_confirmation_orders(u.id)
    assert [o.id for o in groups['archived']] == [o_arch.id]
    assert [o.id for o in groups['recent_paid']] == [o_recent.id]
