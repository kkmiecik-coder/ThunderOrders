"""
Supplier order state helpers.

Computes per-Order state describing whether a client order is:
- 'czeka'      -> visible in admin "Zamówienia produktów" tab (E1 approved, not yet ordered)
- 'zamowione'  -> at least one ProxyOrder with status 'zamowiono' covers its items
- None         -> neither (already delivered to proxy / cancelled / not yet eligible)

Also resolves which client Orders are affected by a given ProxyOrder
(used to dispatch notifications when ProxyOrder is created or its status changes).
"""

from extensions import db


_PAYMENT_STAGES_BY_PROXY_TYPE = {'proxy': 4, 'polska': 3}


def _map_proxy_type_to_order_match(proxy_order_type):
    """
    Mapuje order_type ProxyOrder ('proxy'|'polska') na (payment_stages, eligible_statuses)
    klientów, którzy mogliby być zsynchronizowani.
    """
    if proxy_order_type == 'proxy':
        return 4, ('nowe', 'oczekujace')
    if proxy_order_type == 'polska':
        return 3, ('nowe', 'oczekujace')
    return None, ()


def _order_is_e1_approved(order):
    """Czy Order ma zatwierdzone E1 (płatność za produkt)."""
    from modules.orders.models import PaymentConfirmation
    return db.session.query(PaymentConfirmation.id).filter(
        PaymentConfirmation.order_id == order.id,
        PaymentConfirmation.payment_stage == 'product',
        PaymentConfirmation.status == 'approved'
    ).first() is not None


def _exclusive_offer_page_fully_paid(offer_page_id):
    """Wszystkie exclusive zamówienia z danej offer page mają E1 zatwierdzone."""
    from modules.orders.models import Order, PaymentConfirmation
    from sqlalchemy import func

    if not offer_page_id:
        return False

    total = db.session.query(func.count(Order.id)).filter(
        Order.order_type == 'exclusive',
        Order.status == 'oczekujace',
        Order.offer_page_id == offer_page_id
    ).scalar() or 0

    if total == 0:
        return False

    paid = db.session.query(func.count(db.distinct(Order.id))).join(
        PaymentConfirmation,
        db.and_(
            PaymentConfirmation.order_id == Order.id,
            PaymentConfirmation.payment_stage == 'product',
            PaymentConfirmation.status == 'approved'
        )
    ).filter(
        Order.order_type == 'exclusive',
        Order.status == 'oczekujace',
        Order.offer_page_id == offer_page_id
    ).scalar() or 0

    return paid == total


def _order_matches_waiting_filter(order):
    """
    Czy Order pojawia się w zakładce "Zamówienia produktów" (DO ZAMÓWIENIA).
    Bazuje na regułach z modules/products/routes.py:get_products_to_order().
    """
    if order.order_type == 'pre_order':
        return order.status == 'nowe' and _order_is_e1_approved(order)
    if order.order_type == 'exclusive':
        return order.status == 'oczekujace' and _exclusive_offer_page_fully_paid(order.offer_page_id)
    return False


def _order_has_active_proxy_link(order):
    """
    Order ma przynajmniej jeden ProxyOrderItem powiązany przez product_id i payment_stages
    do ProxyOrder o statusie 'zamowiono' (czyli zamówiono u dostawcy, jeszcze nie dostarczono).
    Korzystamy z mapowania payment_stages <-> order_type:
        proxy ↔ 4, polska ↔ 3.
    """
    from modules.products.models import ProxyOrder, ProxyOrderItem
    from modules.orders.models import OrderItem

    proxy_type = None
    if order.payment_stages == 4:
        proxy_type = 'proxy'
    elif order.payment_stages == 3:
        proxy_type = 'polska'
    else:
        return False

    product_ids = [
        oi.product_id for oi in order.items
        if oi.product_id and not getattr(oi, 'is_bonus', False)
    ]
    if not product_ids:
        return False

    return db.session.query(ProxyOrderItem.id).join(
        ProxyOrder, ProxyOrderItem.proxy_order_id == ProxyOrder.id
    ).filter(
        ProxyOrder.order_type == proxy_type,
        ProxyOrder.status == 'zamowiono',
        ProxyOrderItem.product_id.in_(product_ids)
    ).first() is not None


def get_supplier_order_state(order):
    """
    Zwraca 'czeka' | 'zamowione' | None dla danego Order.

    Logika:
    - 'zamowione' jeśli istnieje aktywny powiązany ProxyOrder (status='zamowiono')
    - 'czeka'     jeśli pasuje do filtra zakładki "Zamówienia produktów" (E1 approved itd.)
    - None        w pozostałych przypadkach
    """
    if not order:
        return None

    if _order_has_active_proxy_link(order):
        return 'zamowione'

    if _order_matches_waiting_filter(order):
        return 'czeka'

    return None


def get_supplier_states_for_orders(orders):
    """
    Zwraca dict {order_id: state} dla listy Order.
    Wersja zoptymalizowana — wszystkie zapytania jednorazowe zamiast per-order.
    """
    if not orders:
        return {}

    from modules.products.models import ProxyOrder, ProxyOrderItem
    from modules.orders.models import Order, OrderItem, PaymentConfirmation
    from sqlalchemy import func

    order_ids = [o.id for o in orders]

    # E1 approved per order
    paid_order_ids = {
        row[0] for row in db.session.query(PaymentConfirmation.order_id).filter(
            PaymentConfirmation.order_id.in_(order_ids),
            PaymentConfirmation.payment_stage == 'product',
            PaymentConfirmation.status == 'approved'
        ).distinct()
    }

    # Exclusive offer pages w pełni opłacone (cache per page_id)
    exclusive_pages = {
        o.offer_page_id for o in orders
        if o.order_type == 'exclusive' and o.offer_page_id
    }
    fully_paid_pages = set()
    if exclusive_pages:
        total_per_page = dict(db.session.query(
            Order.offer_page_id, func.count(Order.id)
        ).filter(
            Order.order_type == 'exclusive',
            Order.status == 'oczekujace',
            Order.offer_page_id.in_(exclusive_pages)
        ).group_by(Order.offer_page_id).all())

        paid_per_page = dict(db.session.query(
            Order.offer_page_id, func.count(db.distinct(Order.id))
        ).join(
            PaymentConfirmation,
            db.and_(
                PaymentConfirmation.order_id == Order.id,
                PaymentConfirmation.payment_stage == 'product',
                PaymentConfirmation.status == 'approved'
            )
        ).filter(
            Order.order_type == 'exclusive',
            Order.status == 'oczekujace',
            Order.offer_page_id.in_(exclusive_pages)
        ).group_by(Order.offer_page_id).all())

        for page_id, total in total_per_page.items():
            if total > 0 and paid_per_page.get(page_id, 0) == total:
                fully_paid_pages.add(page_id)

    # Aktywne ProxyOrderItem'y (status='zamowiono') indeksowane (proxy_type, product_id)
    active_proxy_pairs = set()
    rows = db.session.query(
        ProxyOrder.order_type, ProxyOrderItem.product_id
    ).join(
        ProxyOrderItem, ProxyOrderItem.proxy_order_id == ProxyOrder.id
    ).filter(
        ProxyOrder.status == 'zamowiono'
    ).distinct().all()
    for proxy_type, pid in rows:
        active_proxy_pairs.add((proxy_type, pid))

    # OrderItems per order (do wyznaczenia produktów)
    items_by_order = {}
    item_rows = db.session.query(OrderItem.order_id, OrderItem.product_id, OrderItem.is_bonus).filter(
        OrderItem.order_id.in_(order_ids)
    ).all()
    for oid, pid, is_bonus in item_rows:
        if is_bonus or not pid:
            continue
        items_by_order.setdefault(oid, []).append(pid)

    result = {}
    for order in orders:
        proxy_type = None
        if order.payment_stages == 4:
            proxy_type = 'proxy'
        elif order.payment_stages == 3:
            proxy_type = 'polska'

        state = None
        product_ids = items_by_order.get(order.id, [])

        if proxy_type and product_ids and any(
            (proxy_type, pid) in active_proxy_pairs for pid in product_ids
        ):
            state = 'zamowione'
        elif order.order_type == 'pre_order':
            if order.status == 'nowe' and order.id in paid_order_ids:
                state = 'czeka'
        elif order.order_type == 'exclusive':
            if order.status == 'oczekujace' and order.offer_page_id in fully_paid_pages:
                state = 'czeka'

        result[order.id] = state

    return result


def dispatch_supplier_ordered_notifications(proxy_order):
    """
    Wysyła push + email do każdego unikalnego klienta, którego Order jest pokryty
    przez przekazany ProxyOrder. Wywoływane gdy ProxyOrder zostaje utworzony lub
    przywrócony do statusu 'zamowiono'.
    """
    from flask import current_app
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    try:
        affected_orders = get_affected_orders_for_proxy_order(proxy_order)
    except Exception as e:
        current_app.logger.error(
            f'Failed to resolve affected orders for ProxyOrder {proxy_order.id}: {e}'
        )
        return 0

    seen_orders = set()
    sent = 0
    for order in affected_orders:
        if order.id in seen_orders:
            continue
        seen_orders.add(order.id)
        try:
            PushManager.notify_supplier_ordered(order)
            EmailManager.notify_supplier_ordered(order)
            sent += 1
        except Exception as e:
            current_app.logger.error(
                f'Failed to send supplier-ordered notifications for order {order.id}: {e}'
            )
    return sent


def dispatch_supplier_cancelled_notifications(proxy_order):
    """
    Wysyła push + email do każdego unikalnego klienta, którego Order był pokryty
    przez przekazany ProxyOrder. Wywoływane gdy ProxyOrder zostaje anulowany.
    """
    from flask import current_app
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    try:
        affected_orders = get_affected_orders_for_proxy_order(proxy_order)
    except Exception as e:
        current_app.logger.error(
            f'Failed to resolve affected orders for ProxyOrder {proxy_order.id}: {e}'
        )
        return 0

    seen_orders = set()
    sent = 0
    for order in affected_orders:
        if order.id in seen_orders:
            continue
        seen_orders.add(order.id)
        try:
            PushManager.notify_supplier_cancelled(order)
            EmailManager.notify_supplier_cancelled(order)
            sent += 1
        except Exception as e:
            current_app.logger.error(
                f'Failed to send supplier-cancelled notifications for order {order.id}: {e}'
            )
    return sent


def get_affected_orders_for_proxy_order(proxy_order):
    """
    Zwraca listę unikalnych Order objects, które mogłyby zostać poinformowane
    o utworzeniu/anulowaniu danego ProxyOrder.

    Klient jest "afektowany" gdy:
    - jego Order.payment_stages pasuje do ProxyOrder.order_type (proxy=4, polska=3)
    - jego Order.status jest jednym z eligible (nowe/oczekujace)
    - jego Order ma OrderItem z product_id obecnym w ProxyOrder
    - jego Order.user_id != NULL (mamy do kogo wysłać)
    - E1 produkt jest zatwierdzone
    """
    from modules.products.models import ProxyOrderItem
    from modules.orders.models import Order, OrderItem, PaymentConfirmation

    payment_stages, eligible_statuses = _map_proxy_type_to_order_match(proxy_order.order_type)
    if not payment_stages:
        return []

    proxy_product_ids = [pid for pid, in db.session.query(
        ProxyOrderItem.product_id
    ).filter(ProxyOrderItem.proxy_order_id == proxy_order.id).distinct()]

    if not proxy_product_ids:
        return []

    orders = db.session.query(Order).join(
        OrderItem, OrderItem.order_id == Order.id
    ).join(
        PaymentConfirmation,
        db.and_(
            PaymentConfirmation.order_id == Order.id,
            PaymentConfirmation.payment_stage == 'product',
            PaymentConfirmation.status == 'approved'
        )
    ).filter(
        Order.payment_stages == payment_stages,
        Order.status.in_(eligible_statuses),
        Order.user_id.isnot(None),
        OrderItem.product_id.in_(proxy_product_ids),
        OrderItem.is_bonus == False
    ).distinct().all()

    return orders
