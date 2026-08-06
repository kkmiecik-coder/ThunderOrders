"""Testy nowej tabeli łączącej PolandOrderItemOrder i funkcji
_allocate_batch_units_to_orders() — naprawa terminów E2/E3 (patrz
docs/superpowers/plans/2026-08-06-terminy-e2-e3-poland-order-link.md).
"""
from datetime import datetime, timedelta
from decimal import Decimal


def test_poland_order_item_order_roundtrip(db, make_user, make_product, make_order):
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem, PolandOrderItemOrder

    product = make_product()
    user = make_user()
    order = make_order(user, offer_page_id=1)

    proxy = ProxyOrder(order_number='PRX/R1', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product.id,
                                 quantity=1, unit_price=Decimal('100'), total_price=Decimal('100'))
    db.session.add(proxy_item)
    db.session.flush()

    poland_order = PolandOrder(order_number='PRX/PL/R1', proxy_order_id=proxy.id, status='zamowione')
    db.session.add(poland_order)
    db.session.flush()
    poland_item = PolandOrderItem(poland_order_id=poland_order.id, proxy_order_item_id=proxy_item.id,
                                   product_id=product.id, quantity=1)
    db.session.add(poland_item)
    db.session.flush()

    link = PolandOrderItemOrder(poland_order_item_id=poland_item.id, order_id=order.id, quantity=1)
    db.session.add(link)
    db.session.commit()

    fetched = PolandOrderItemOrder.query.filter_by(order_id=order.id).first()
    assert fetched is not None
    assert fetched.poland_order_item.id == poland_item.id
    assert fetched.quantity == 1


def _client_order(db, make_user, make_order, product_id, qty, created_at, price=100):
    from modules.orders.models import OrderItem
    u = make_user()
    o = make_order(u, offer_page_id=1, created_at=created_at)
    db.session.add(OrderItem(order_id=o.id, product_id=product_id, quantity=qty,
                              price=Decimal(str(price)), total=Decimal(str(price)) * qty))
    db.session.commit()
    return o


def _make_batch_item(db, product_id, qty, created_at, status='zamowione'):
    """Tworzy ProxyOrder+Item oraz PolandOrder+Item (jedna partia), zwraca PolandOrderItem."""
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem

    suffix = f'{product_id}-{int(created_at.timestamp())}-{qty}'
    proxy = ProxyOrder(order_number=f'PRX/A{suffix}', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product_id, quantity=qty,
                                 unit_price=Decimal('100'), total_price=Decimal('100') * qty)
    db.session.add(proxy_item)
    db.session.flush()

    poland_order = PolandOrder(order_number=f'PRX/PL/A{suffix}', proxy_order_id=proxy.id, status=status)
    poland_order.created_at = created_at
    db.session.add(poland_order)
    db.session.flush()
    poland_item = PolandOrderItem(poland_order_id=poland_order.id, proxy_order_item_id=proxy_item.id,
                                   product_id=product_id, quantity=qty)
    db.session.add(poland_item)
    db.session.commit()
    return poland_item


def test_single_order_single_batch(db, make_user, make_product, make_order):
    from modules.products.routes import _allocate_batch_units_to_orders

    p = make_product()
    base = datetime(2026, 6, 1, 10, 0, 0)
    o = _client_order(db, make_user, make_order, p.id, 2, base + timedelta(minutes=1))
    poland_item = _make_batch_item(db, p.id, 2, base + timedelta(hours=1))

    assert _allocate_batch_units_to_orders(poland_item) == [(o.id, 2)]


def test_aggregated_batch_splits_across_orders_fifo(db, make_user, make_product, make_order):
    """Jedna partia (agregacja) obsługuje dwa zamówienia — kolejność FIFO wg daty zamówienia."""
    from modules.products.routes import _allocate_batch_units_to_orders

    p = make_product()
    base = datetime(2026, 6, 1, 10, 0, 0)
    o1 = _client_order(db, make_user, make_order, p.id, 1, base + timedelta(minutes=1))
    o2 = _client_order(db, make_user, make_order, p.id, 1, base + timedelta(minutes=2))
    poland_item = _make_batch_item(db, p.id, 2, base + timedelta(hours=1))

    assert _allocate_batch_units_to_orders(poland_item) == [(o1.id, 1), (o2.id, 1)]


def test_order_split_across_two_batches(db, make_user, make_product, make_order):
    """Jedno zamówienie (3 szt) rozjeżdża się na dwie partie — 2 w pierwszej, 1 w drugiej."""
    from modules.products.routes import _allocate_batch_units_to_orders

    p = make_product()
    base = datetime(2026, 6, 1, 10, 0, 0)
    o = _client_order(db, make_user, make_order, p.id, 3, base + timedelta(minutes=1))
    batch1 = _make_batch_item(db, p.id, 2, base + timedelta(hours=1))
    batch2 = _make_batch_item(db, p.id, 1, base + timedelta(hours=2))

    assert _allocate_batch_units_to_orders(batch1) == [(o.id, 2)]
    assert _allocate_batch_units_to_orders(batch2) == [(o.id, 1)]


def test_cancelled_batch_ignored_in_offset(db, make_user, make_product, make_order):
    """Anulowana partia nie liczy się do przesunięcia FIFO kolejnej partii."""
    from modules.products.routes import _allocate_batch_units_to_orders

    p = make_product()
    base = datetime(2026, 6, 1, 10, 0, 0)
    o = _client_order(db, make_user, make_order, p.id, 1, base + timedelta(minutes=1))
    _make_batch_item(db, p.id, 1, base + timedelta(hours=1), status='anulowane')
    poland_item = _make_batch_item(db, p.id, 1, base + timedelta(hours=2))

    assert _allocate_batch_units_to_orders(poland_item) == [(o.id, 1)]


def test_partial_fulfillment_reduces_effective_quantity(db, make_user, make_product, make_order):
    """fulfilled_quantity < quantity ogranicza ile sztuk zamówienia liczy się do FIFO."""
    from modules.orders.models import OrderItem
    from modules.products.routes import _allocate_batch_units_to_orders

    p = make_product()
    base = datetime(2026, 6, 1, 10, 0, 0)
    u = make_user()
    o = make_order(u, offer_page_id=1, created_at=base + timedelta(minutes=1))
    db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=3, fulfilled_quantity=1,
                              price=Decimal('100'), total=Decimal('300')))
    db.session.commit()

    poland_item = _make_batch_item(db, p.id, 1, base + timedelta(hours=1))

    assert _allocate_batch_units_to_orders(poland_item) == [(o.id, 1)]


def test_create_poland_order_endpoint_persists_allocations(client, db, make_user, make_product, make_order, login):
    """Integracyjny: prawdziwe wywołanie POST /admin/products/api/create-poland-order
    musi zapisać PolandOrderItemOrder dla zamówienia klienta, którego produkt
    trafił do tej partii."""
    from modules.orders.models import OrderItem
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrderItemOrder

    admin = make_user(role='admin', profile_completed=True)
    login(admin)

    product = make_product()
    client_user = make_user()
    order = make_order(client_user, offer_page_id=1)
    db.session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=2,
                              price=Decimal('100'), total=Decimal('200')))
    db.session.commit()

    proxy = ProxyOrder(order_number='PRX/E1', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product.id,
                                 quantity=2, unit_price=Decimal('100'), total_price=Decimal('200'))
    db.session.add(proxy_item)
    db.session.commit()

    resp = client.post('/admin/products/api/create-poland-order', json={
        'proxy_order_ids': [proxy.id],
        'shipping_cost_total': '20.00',
        'payment_deadline': '2026-09-01T23:59:00',
        'items': [{'proxy_order_item_id': proxy_item.id, 'shipping_cost': '20.00'}],
    })

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['success'] is True

    links = PolandOrderItemOrder.query.filter_by(order_id=order.id).all()
    assert len(links) == 1
    assert links[0].quantity == 2
