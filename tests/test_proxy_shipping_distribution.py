"""Testy rozdziału kosztów wysyłki KR (proxy) na zamówienia klientów.

Model: koszt liczony PER PARTIA, sztuki przydzielane do partii wg daty złożenia
zamówienia (FIFO). Regresja: bug, w którym koszt jednej partii był dzielony przez
cały popyt klientów (i nadpisywany przy wielu partiach) → zaniżony koszt.
"""
from datetime import datetime, timedelta
from decimal import Decimal


def _make_batch(db, product_id, qty, shipping, created_at, status='zamowione'):
    """Tworzy ProxyOrder+Item oraz PolandOrder+Item (jedna partia danego produktu)."""
    from modules.products.models import (
        ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem,
    )
    suffix = f'{product_id}-{int(created_at.timestamp())}'
    proxy = ProxyOrder(order_number=f'PRX/T{suffix}', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    pitem = ProxyOrderItem(
        proxy_order_id=proxy.id, product_id=product_id,
        quantity=qty, unit_price=Decimal('100'), total_price=Decimal('100') * qty,
    )
    db.session.add(pitem)
    db.session.flush()

    pol = PolandOrder(
        order_number=f'PRX/PL/T{suffix}', proxy_order_id=proxy.id,
        status=status, shipping_cost=Decimal(str(shipping)),
    )
    pol.created_at = created_at
    db.session.add(pol)
    db.session.flush()
    poli = PolandOrderItem(
        poland_order_id=pol.id, proxy_order_item_id=pitem.id,
        product_id=product_id, quantity=qty, shipping_cost=Decimal(str(shipping)),
    )
    db.session.add(poli)
    db.session.commit()
    return pol


def _client_order(db, make_user, make_order, product_id, qty, created_at, price=130):
    """Zamówienie klienta (exclusive: offer_page_id ustawione) z jedną pozycją."""
    from modules.orders.models import OrderItem
    u = make_user()
    o = make_order(u, offer_page_id=1, created_at=created_at)
    it = OrderItem(
        order_id=o.id, product_id=product_id, quantity=qty,
        price=Decimal(str(price)), total=Decimal(str(price)) * qty,
    )
    db.session.add(it)
    db.session.commit()
    return o


def test_dwie_partie_ta_sama_stawka_per_szt(db, make_user, make_product):
    """Regresja produkcyjna: 14 klientów po 1 szt, partie 11 (212.74) i 3 (58.02),
    obie 19.34/szt → każdy klient ma 19.34, NIE 4.14."""
    from modules.products.routes import _distribute_proxy_shipping_to_client_orders
    from modules.orders.models import Order, OrderItem

    p = make_product()
    base = datetime(2026, 6, 1, 10, 0, 0)
    orders = []
    for i in range(14):
        u = make_user()
        o = Order(order_number=f'PO/T{i:05d}', user_id=u.id, status='nowe',
                  total_amount=130, offer_page_id=1,
                  created_at=base + timedelta(minutes=i))
        db.session.add(o)
        db.session.flush()
        db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=1,
                                 price=Decimal('130'), total=Decimal('130')))
        orders.append(o)
    db.session.commit()

    # Partia 1 wcześniejsza (11 szt), partia 2 późniejsza (3 szt)
    _make_batch(db, p.id, 11, '212.74', base + timedelta(hours=1))
    _make_batch(db, p.id, 3, '58.02', base + timedelta(hours=2))

    _distribute_proxy_shipping_to_client_orders({p.id: Decimal('58.02')})
    db.session.commit()

    for o in orders:
        db.session.refresh(o)
        assert o.proxy_shipping_cost == Decimal('19.34'), \
            f'order {o.id} = {o.proxy_shipping_cost}, oczekiwano 19.34'


def test_fifo_rozne_stawki_miedzy_partiami(db, make_user, make_product, make_order):
    """FIFO: 4 klientów po 1 szt (o1<o2<o3<o4 wg daty), partia1 2szt=20.00 (10/szt),
    partia2 2szt=30.00 (15/szt). Oczekiwane: o1=10, o2=10, o3=15, o4=15."""
    from modules.products.routes import _distribute_proxy_shipping_to_client_orders

    p = make_product()
    base = datetime(2026, 6, 1, 10, 0, 0)
    o1 = _client_order(db, make_user, make_order, p.id, 1, base + timedelta(minutes=1))
    o2 = _client_order(db, make_user, make_order, p.id, 1, base + timedelta(minutes=2))
    o3 = _client_order(db, make_user, make_order, p.id, 1, base + timedelta(minutes=3))
    o4 = _client_order(db, make_user, make_order, p.id, 1, base + timedelta(minutes=4))

    _make_batch(db, p.id, 2, '20.00', base + timedelta(hours=1))
    _make_batch(db, p.id, 2, '30.00', base + timedelta(hours=2))

    _distribute_proxy_shipping_to_client_orders({p.id: Decimal('50.00')})
    db.session.commit()

    for o, exp in [(o1, '10.00'), (o2, '10.00'), (o3, '15.00'), (o4, '15.00')]:
        db.session.refresh(o)
        assert o.proxy_shipping_cost == Decimal(exp), \
            f'order {o.id} = {o.proxy_shipping_cost}, oczekiwano {exp}'


def test_anulowana_partia_pomijana(db, make_user, make_product, make_order):
    """Anulowana PolandOrder nie liczy się do puli partii."""
    from modules.products.routes import _distribute_proxy_shipping_to_client_orders

    p = make_product()
    base = datetime(2026, 6, 1, 10, 0, 0)
    o1 = _client_order(db, make_user, make_order, p.id, 1, base + timedelta(minutes=1))

    _make_batch(db, p.id, 1, '99.00', base + timedelta(hours=1), status='anulowane')
    _make_batch(db, p.id, 1, '20.00', base + timedelta(hours=2))

    _distribute_proxy_shipping_to_client_orders({p.id: Decimal('20.00')})
    db.session.commit()

    db.session.refresh(o1)
    assert o1.proxy_shipping_cost == Decimal('20.00')
