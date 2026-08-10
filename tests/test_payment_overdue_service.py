from datetime import timedelta
from decimal import Decimal

import pytest

from modules.orders.models import get_local_now
@pytest.fixture(autouse=True)
def _strona_sprzedazy(strona_sprzedazy):
    """Zamówienia w tym pliku powstają z `offer_page_id=1`, a to kolumna FK — strona
    o tym id musi realnie istnieć (fixture `strona_sprzedazy` w conftest)."""


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


@pytest.mark.parametrize('status', ['do_zwrotu', 'zwrocone', 'czesciowo_zwrocone'])
def test_summary_excludes_closed_orders(db, make_user, make_order, status):
    """Zamówienie po stronie zwrotów nie może dostawać ponagleń o zapłatę."""
    from modules.orders.payment_overdue_service import get_overdue_orders_summary

    now = get_local_now()
    order = make_order(make_user(), total_amount=Decimal('50.00'), status=status)
    order.get_product_deadline = lambda: now - timedelta(days=1)
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None

    result = get_overdue_orders_summary()

    assert order.id not in [r['order'].id for r in result]


def test_get_overdue_orders_summary_finds_real_shipping_kr_deadline(db, make_user, make_product, make_order):
    """Regresja end-to-end: zaległość E2 wykryta przez prawdziwe dane w
    PolandOrderItemOrder, nie przez monkeypatch getterów."""
    from datetime import datetime, timedelta
    from decimal import Decimal
    from modules.orders.models import OrderItem
    from modules.orders.payment_overdue_service import get_overdue_orders_summary
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem, PolandOrderItemOrder

    now = datetime.utcnow()
    product = make_product()
    user = make_user()
    order = make_order(user, offer_page_id=1, payment_stages=4,
                        proxy_shipping_cost=Decimal('15.50'))
    db.session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=1,
                              price=Decimal('100'), total=Decimal('100')))
    db.session.commit()

    proxy = ProxyOrder(order_number='PRX/OV1', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product.id,
                                 quantity=1, unit_price=Decimal('100'), total_price=Decimal('100'))
    db.session.add(proxy_item)
    db.session.flush()

    poland_order = PolandOrder(order_number='PRX/PL/OV1', proxy_order_id=proxy.id, status='zamowione',
                                payment_deadline=now - timedelta(days=3))
    db.session.add(poland_order)
    db.session.flush()
    poland_item = PolandOrderItem(poland_order_id=poland_order.id, proxy_order_item_id=proxy_item.id,
                                   product_id=product.id, quantity=1)
    db.session.add(poland_item)
    db.session.flush()
    db.session.add(PolandOrderItemOrder(poland_order_item_id=poland_item.id, order_id=order.id, quantity=1))
    db.session.commit()

    summary = get_overdue_orders_summary()
    matching = [r for r in summary if r['order'].id == order.id]
    assert len(matching) == 1
    assert any(s['stage'] == 'shipping_kr' for s in matching[0]['overdue_stages'])


def test_get_overdue_orders_summary_batches_poland_order_item_order_queries(
        db, make_user, make_product, make_order):
    """Regresja N+1: preload w get_overdue_orders_summary() musi odpytać
    PolandOrderItemOrder JEDNYM zbiorczym zapytaniem dla wszystkich zamówień,
    a nie osobno dla każdego.

    _get_poland_items() (Task 4) ma poprawny fallback per-zamówienie, gdy
    order._cached_poland_items nie zostało ustawione — więc sama poprawność
    wyniku (inny test w tym pliku) NIE wykryje, jeśli ktoś przypadkiem
    usunie/zepsuje batching w preloadzie. Ten test liczy realne zapytania
    SQL przez SQLAlchemy `before_cursor_execute` i asercją pilnuje, że
    zapytań dotykających poland_order_item_orders jest <=1 niezależnie od
    liczby zamówień."""
    from datetime import datetime, timedelta
    from decimal import Decimal
    from sqlalchemy import event
    from modules.orders.models import OrderItem
    from modules.orders.payment_overdue_service import get_overdue_orders_summary
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem, PolandOrderItemOrder

    now = datetime.utcnow()
    product = make_product()

    orders = []
    for i in range(5):
        user = make_user()
        order = make_order(user, offer_page_id=1, payment_stages=4,
                            proxy_shipping_cost=Decimal('15.50'))
        db.session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=1,
                                  price=Decimal('100'), total=Decimal('100')))
        db.session.commit()

        proxy = ProxyOrder(order_number=f'PRX/BATCH{i}', order_type='proxy')
        db.session.add(proxy)
        db.session.flush()
        proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product.id,
                                     quantity=1, unit_price=Decimal('100'), total_price=Decimal('100'))
        db.session.add(proxy_item)
        db.session.flush()

        poland_order = PolandOrder(order_number=f'PRX/PL/BATCH{i}', proxy_order_id=proxy.id, status='zamowione',
                                    payment_deadline=now - timedelta(days=3))
        db.session.add(poland_order)
        db.session.flush()
        poland_item = PolandOrderItem(poland_order_id=poland_order.id, proxy_order_item_id=proxy_item.id,
                                       product_id=product.id, quantity=1)
        db.session.add(poland_item)
        db.session.flush()
        db.session.add(PolandOrderItemOrder(poland_order_item_id=poland_item.id, order_id=order.id, quantity=1))
        db.session.commit()
        orders.append(order)

    queries = []

    def _record_query(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _record_query)
    try:
        summary = get_overdue_orders_summary()
    finally:
        event.remove(db.engine, 'before_cursor_execute', _record_query)

    # Sanity check: wszystkie posiane zamówienia rzeczywiście trafiły do
    # wyniku (zaległość E2 wykryta) — inaczej licznik zapytań poniżej
    # niczego by nie dowodził.
    order_ids = {o.id for o in orders}
    assert {r['order'].id for r in summary} & order_ids == order_ids

    poi_queries = [q for q in queries if 'poland_order_item_orders' in q.lower()]
    assert len(poi_queries) <= 1, (
        f"Preload powinien odpytać PolandOrderItemOrder JEDNYM zbiorczym "
        f"zapytaniem dla wszystkich {len(orders)} zamówień, a nie osobno "
        f"dla każdego (N+1). Wykryto {len(poi_queries)} takich zapytań — "
        f"batching w get_overdue_orders_summary() prawdopodobnie się zepsuł."
    )
