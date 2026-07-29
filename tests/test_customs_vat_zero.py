"""Testy rozróżnienia NULL (cło nieustalone) od 0 (cło ustalone na zero)."""
from decimal import Decimal


def test_new_order_has_null_customs_by_default(db, make_user, make_order):
    # NULL = "jeszcze nie ustalono"; wcześniej domyślną wartością było 0.00
    u = make_user()
    o = make_order(u, order_type='exclusive')
    assert o.customs_vat_sale_cost is None


def test_order_accepts_explicit_zero(db, make_user, make_order):
    # 0 = "ustalono: bez podatku" — musi dać się zapisać i odczytać jako zero, nie NULL
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    db.session.refresh(o)
    assert o.customs_vat_sale_cost is not None
    assert o.customs_vat_sale_cost == 0


def test_poland_order_item_customs_defaults_to_null(db, make_product):
    from modules.products.models import PolandOrder, PolandOrderItem, ProxyOrder, ProxyOrderItem
    p = make_product()
    proxy = ProxyOrder(order_number='PRX/TEST/1', order_type='proxy', status='zamowiono')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=p.id,
                                quantity=1, unit_price=10, total_price=10)
    db.session.add(proxy_item)
    db.session.flush()
    po = PolandOrder(order_number='PL/TEST/1', proxy_order_id=proxy.id, status='zamowione')
    db.session.add(po)
    db.session.flush()
    item = PolandOrderItem(poland_order_id=po.id, proxy_order_item_id=proxy_item.id,
                           product_id=p.id, quantity=1)
    db.session.add(item)
    db.session.commit()
    assert item.customs_vat_percentage is None
    assert item.customs_vat_amount is None
