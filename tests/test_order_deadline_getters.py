from datetime import datetime


def test_get_product_deadline_from_offer_page(db, make_user, make_order):
    from modules.offers.models import OfferPage

    user = make_user()
    admin = make_user(role='admin')
    deadline = datetime(2026, 8, 1, 12, 0)
    page = OfferPage(name='Test Page', token=OfferPage.generate_token(), payment_deadline=deadline, created_by=admin.id)
    db.session.add(page)
    db.session.commit()

    order = make_order(user, offer_page_id=page.id)

    assert order.get_product_deadline() == deadline


def test_get_product_deadline_none_without_offer_page(db, make_user, make_order):
    user = make_user()
    order = make_order(user)

    assert order.get_product_deadline() is None


def test_get_shipping_kr_deadline_finds_batch_customer_belongs_to(db, make_user, make_product, make_order):
    """Regresja: klient kupił produkt z partii, której PolandOrder ma ustawiony
    payment_deadline (E2) — order.get_shipping_kr_deadline() powinien go znaleźć.

    Bug: ProxyOrderItem/PolandOrderItem.order_id nigdy nie jest ustawiany przy
    tworzeniu (create_stock_orders*, create_poland_order w modules/products/routes.py),
    więc _get_poland_item() (PolandOrderItem.query.filter_by(order_id=self.id))
    zawsze zwraca None, mimo że deadline jest poprawnie zapisany na PolandOrder.
    """
    from decimal import Decimal
    from modules.orders.models import OrderItem
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem

    user = make_user()
    product = make_product()
    order = make_order(user, offer_page_id=1)
    db.session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=1,
                              price=Decimal('100'), total=Decimal('100')))
    db.session.commit()

    proxy = ProxyOrder(order_number='PRX/T1', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product.id,
                                 quantity=1, unit_price=Decimal('100'), total_price=Decimal('100'))
    db.session.add(proxy_item)
    db.session.flush()

    deadline = datetime(2026, 8, 15, 23, 59)
    poland_order = PolandOrder(order_number='PRX/PL/T1', proxy_order_id=proxy.id,
                                status='zamowione', payment_deadline=deadline)
    db.session.add(poland_order)
    db.session.flush()
    poland_item = PolandOrderItem(poland_order_id=poland_order.id, proxy_order_item_id=proxy_item.id,
                                   product_id=product.id, quantity=1)
    db.session.add(poland_item)
    db.session.commit()

    assert order.get_shipping_kr_deadline() == deadline, (
        "get_shipping_kr_deadline() zwrócił None mimo że deadline jest ustawiony "
        "na PolandOrder tej partii — order_id nigdy nie łączy zamówienia klienta "
        "z jego PolandOrderItem."
    )


def test_get_customs_vat_deadline_finds_batch_customer_belongs_to(db, make_user, make_product, make_order):
    """Analogiczna regresja dla E3 (cło/VAT) — patrz test powyżej dla E2."""
    from decimal import Decimal
    from modules.orders.models import OrderItem
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem

    user = make_user()
    product = make_product()
    order = make_order(user, offer_page_id=1)
    db.session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=1,
                              price=Decimal('100'), total=Decimal('100')))
    db.session.commit()

    proxy = ProxyOrder(order_number='PRX/T2', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product.id,
                                 quantity=1, unit_price=Decimal('100'), total_price=Decimal('100'))
    db.session.add(proxy_item)
    db.session.flush()

    customs_deadline = datetime(2026, 8, 20, 23, 59)
    poland_order = PolandOrder(order_number='PRX/PL/T2', proxy_order_id=proxy.id,
                                status='urzad_celny', customs_payment_deadline=customs_deadline)
    db.session.add(poland_order)
    db.session.flush()
    poland_item = PolandOrderItem(poland_order_id=poland_order.id, proxy_order_item_id=proxy_item.id,
                                   product_id=product.id, quantity=1)
    db.session.add(poland_item)
    db.session.commit()

    assert order.get_customs_vat_deadline() == customs_deadline, (
        "get_customs_vat_deadline() zwrócił None mimo że termin cła jest ustawiony "
        "na PolandOrder tej partii — order_id nigdy nie łączy zamówienia klienta "
        "z jego PolandOrderItem."
    )
