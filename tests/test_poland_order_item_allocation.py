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
