from datetime import timedelta
from decimal import Decimal

from modules.orders.models import get_local_now


def _confirm(db, order, stage, status='approved', amount=Decimal('10.00')):
    from modules.orders.models import PaymentConfirmation
    c = PaymentConfirmation(order_id=order.id, payment_stage=stage, status=status, amount=amount)
    db.session.add(c)
    db.session.commit()
    return c


def test_no_overdue_when_no_deadlines(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    order = make_order(make_user(), total_amount=Decimal('100.00'))
    order.get_product_deadline = lambda: None
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None

    assert get_order_overdue_stages(order) == []


def test_product_overdue_when_deadline_passed_and_unpaid(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    now = get_local_now()
    order = make_order(make_user(), total_amount=Decimal('100.00'))
    order.get_product_deadline = lambda: now - timedelta(days=3)
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None

    stages = get_order_overdue_stages(order, now=now)

    assert len(stages) == 1
    assert stages[0]['stage'] == 'product'
    assert stages[0]['amount'] == Decimal('100.00')
    assert stages[0]['days_overdue'] == 3


def test_not_overdue_when_deadline_in_future(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    now = get_local_now()
    order = make_order(make_user(), total_amount=Decimal('100.00'))
    order.get_product_deadline = lambda: now + timedelta(days=1)
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None

    assert get_order_overdue_stages(order, now=now) == []


def test_not_overdue_when_already_approved(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    now = get_local_now()
    order = make_order(make_user(), total_amount=Decimal('100.00'))
    order.get_product_deadline = lambda: now - timedelta(days=1)
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None
    _confirm(db, order, 'product', status='approved')

    assert get_order_overdue_stages(order, now=now) == []


def test_not_overdue_when_pending_confirmation(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    now = get_local_now()
    order = make_order(make_user(), total_amount=Decimal('100.00'))
    order.get_product_deadline = lambda: now - timedelta(days=1)
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None
    _confirm(db, order, 'product', status='pending')

    assert get_order_overdue_stages(order, now=now) == []


def test_customs_vat_not_overdue_when_stage_not_applicable(db, make_user, make_order):
    """order_type='on_hand' -> has_customs_vat_stage=False, etap E3 pomijany nawet z minionym terminem."""
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    now = get_local_now()
    order = make_order(
        make_user(), total_amount=Decimal('100.00'),
        order_type='on_hand', customs_vat_sale_cost=Decimal('20.00')
    )
    order.get_product_deadline = lambda: None
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: now - timedelta(days=5)
    order.get_shipping_pl_deadline = lambda: None

    assert get_order_overdue_stages(order, now=now) == []


def test_multiple_overdue_stages_on_one_order(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    now = get_local_now()
    order = make_order(
        make_user(), total_amount=Decimal('100.00'),
        order_type='exclusive', payment_stages=4,
        proxy_shipping_cost=Decimal('30.00'),
        customs_vat_sale_cost=Decimal('20.00'),
        shipping_cost=Decimal('15.00'),
    )
    order.get_product_deadline = lambda: now - timedelta(days=5)
    order.get_shipping_kr_deadline = lambda: now - timedelta(days=2)
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None

    stages = get_order_overdue_stages(order, now=now)

    assert {s['stage'] for s in stages} == {'product', 'shipping_kr'}
    days = {s['stage']: s['days_overdue'] for s in stages}
    assert days['product'] == 5 and days['shipping_kr'] == 2


def test_summary_sorts_by_most_overdue_first(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_overdue_orders_summary

    now = get_local_now()
    u = make_user()
    o1 = make_order(u, total_amount=Decimal('50.00'))
    o1.get_product_deadline = lambda: now - timedelta(days=1)
    o1.get_shipping_kr_deadline = lambda: None
    o1.get_customs_vat_deadline = lambda: None
    o1.get_shipping_pl_deadline = lambda: None

    o2 = make_order(u, total_amount=Decimal('50.00'))
    o2.get_product_deadline = lambda: now - timedelta(days=10)
    o2.get_shipping_kr_deadline = lambda: None
    o2.get_customs_vat_deadline = lambda: None
    o2.get_shipping_pl_deadline = lambda: None

    result = get_overdue_orders_summary()

    ids_in_order = [r['order'].id for r in result if r['order'].id in (o1.id, o2.id)]
    assert ids_in_order == [o2.id, o1.id]


def test_summary_excludes_cancelled_orders(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_overdue_orders_summary

    now = get_local_now()
    order = make_order(make_user(), total_amount=Decimal('50.00'), status='anulowane')
    order.get_product_deadline = lambda: now - timedelta(days=1)
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None

    result = get_overdue_orders_summary()

    assert order.id not in [r['order'].id for r in result]
