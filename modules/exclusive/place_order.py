"""
Exclusive Place Order Logic
Logika składania zamówień przez strony exclusive
"""

from flask_login import current_user
from decimal import Decimal
from extensions import db
from modules.exclusive.models import ExclusiveReservation, ExclusivePage
from modules.exclusive.reservation import cleanup_expired_reservations
from modules.orders.models import Order, OrderItem
from modules.orders.utils import generate_order_number
from utils.activity_logger import log_activity
from utils.exclusive_auto_increase import check_and_apply_auto_increase


def check_product_availability(reservations, page_id, session_id):
    """
    Check if all reserved products are still available.

    Sprawdza faktyczną dostępność: section_max - total_ordered - reserved_by_others.
    Używa SELECT FOR UPDATE żeby uniknąć race condition przy jednoczesnych zamówieniach.

    Args:
        reservations (list): List of ExclusiveReservation objects
        page_id (int): Exclusive page ID
        session_id (str): Current session ID (to exclude own reservations)

    Returns:
        tuple: (available: bool, error: dict or None)
    """
    import time
    from modules.exclusive.models import ExclusiveSection, ExclusiveSetItem
    from modules.products.models import VariantGroup, variant_products
    from modules.exclusive.reservation import get_section_max_for_product
    from sqlalchemy import func

    now = int(time.time())

    for reservation in reservations:
        product = reservation.product
        section_max = get_section_max_for_product(page_id, product.id)

        if section_max is None:
            continue  # Unlimited

        # Lock reservations for this product (prevents concurrent order race)
        locked_reservations = ExclusiveReservation.query.filter(
            ExclusiveReservation.exclusive_page_id == page_id,
            ExclusiveReservation.product_id == product.id,
            ExclusiveReservation.expires_at > now
        ).with_for_update().all()

        # Total reserved by OTHER sessions
        reserved_by_others = sum(
            r.quantity for r in locked_reservations if r.session_id != session_id
        )

        # Total already ordered (permanent)
        total_ordered = db.session.query(
            func.sum(OrderItem.quantity)
        ).join(Order).filter(
            Order.exclusive_page_id == page_id,
            Order.status != 'anulowane',
            OrderItem.product_id == product.id
        ).scalar() or 0

        available = section_max - int(total_ordered) - reserved_by_others

        if available < reservation.quantity:
            return False, {
                'error': 'insufficient_availability',
                'product_id': product.id,
                'product_name': product.name,
                'requested': reservation.quantity,
                'available': max(0, available),
                'message': f'Produkt "{product.name}" nie ma wystarczającej dostępności ({max(0, available)} szt.)'
            }

    return True, None


def place_exclusive_order(page, session_id, order_note=None):
    """
    Place an order from exclusive page (requires authenticated user)

    Args:
        page (ExclusivePage): Exclusive page object
        session_id (str): User session ID
        order_note (str, optional): Order note/comment

    Returns:
        tuple: (success: bool, result: dict)
    """
    # 1. Cleanup expired reservations
    cleanup_expired_reservations(page.id)

    # 2. Get user's reservations
    reservations = ExclusiveReservation.query.filter_by(
        session_id=session_id,
        exclusive_page_id=page.id
    ).all()

    # Check if there are any items to order
    if not reservations:
        return False, {'error': 'no_reservations', 'message': 'Brak produktów w koszyku'}

    # 3. Check product availability (with SELECT FOR UPDATE to prevent race conditions)
    available, error = check_product_availability(reservations, page.id, session_id)
    if not available:
        return False, error

    # 5. Generate order number
    try:
        order_number = generate_order_number('exclusive')
    except Exception as e:
        return False, {'error': 'order_number_failed', 'message': str(e)}

    # 6. Create order
    order = Order(
        order_number=order_number,
        order_type='exclusive',
        user_id=current_user.id,
        status='nowe',
        is_exclusive=True,
        exclusive_page_id=page.id,
        exclusive_page_name=page.name,  # Preserve page name for history
        payment_stages=page.payment_stages,  # Dziedziczenie z ExclusivePage (3 lub 4)
        notes=order_note,
        total_amount=Decimal('0.00')
    )

    db.session.add(order)
    db.session.flush()  # Get order.id

    # 7. Create order items (exclusive orders do NOT affect global stock)
    total_amount = Decimal('0.00')

    # Build set mappings for this page
    from modules.exclusive.models import ExclusiveSection
    set_product_ids = set()  # Products that ARE the full set bundle
    product_set_info = {}    # product_id → {section_id, quantity_per_set}
    set_sections = ExclusiveSection.query.filter_by(
        exclusive_page_id=page.id,
        section_type='set'
    ).all()
    for sec in set_sections:
        if sec.set_product_id:
            set_product_ids.add(sec.set_product_id)
        for set_item in sec.set_items:
            qps = set_item.quantity_per_set or 1
            for prod in set_item.get_products():
                product_set_info[prod.id] = {
                    'section_id': sec.id,
                    'quantity_per_set': qps,
                }

    # Pre-query existing ordered quantities for set products (before this order)
    prev_ordered_map = {}
    if product_set_info:
        from sqlalchemy import func as sql_func
        prev_counts = db.session.query(
            OrderItem.product_id,
            sql_func.sum(OrderItem.quantity)
        ).join(Order).filter(
            Order.exclusive_page_id == page.id,
            Order.status != 'anulowane',
            OrderItem.product_id.in_(product_set_info.keys())
        ).group_by(OrderItem.product_id).all()
        prev_ordered_map = {pid: int(qty) for pid, qty in prev_counts}

    for reservation in reservations:
        product = reservation.product
        quantity = reservation.quantity
        price = product.sale_price
        item_total = price * quantity

        # Calculate set_number for products that are part of a set
        item_set_number = None
        item_set_section_id = None
        if product.id in product_set_info:
            info = product_set_info[product.id]
            item_set_section_id = info['section_id']
            qps = info['quantity_per_set']
            prev = prev_ordered_map.get(product.id, 0)
            item_set_number = (prev // qps) + 1 if qps > 0 else 1
            # Update prev_ordered_map for subsequent items in the same order
            prev_ordered_map[product.id] = prev + quantity

        # Create order item
        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            price=price,
            total=item_total,
            picked=False,
            is_full_set=(product.id in set_product_ids),
            set_section_id=item_set_section_id,
            set_number=item_set_number,
        )

        db.session.add(order_item)

        # NOTE: Exclusive orders do NOT decrease global stock (product.quantity)
        # Stock is managed separately for exclusive orders

        # Update total
        total_amount += item_total

    # 8. Update order total
    order.total_amount = total_amount

    # 9. Delete all reservations
    for reservation in reservations:
        db.session.delete(reservation)

    # 10. Commit transaction
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return False, {'error': 'database_error', 'message': str(e)}

    # 10b. Check and apply auto-increase if enabled
    try:
        check_and_apply_auto_increase(page.id)
    except Exception as e:
        # Don't fail the order if auto-increase fails
        from flask import current_app
        current_app.logger.error(f"Auto-increase check failed for page {page.id}: {str(e)}")

    # Calculate total items count
    total_items_count = len(reservations)

    # 11. Activity log
    log_activity(
        user=current_user,
        action='order_created',
        entity_type='order',
        entity_id=order.id,
        old_value=None,
        new_value={
            'order_number': order.order_number,
            'total': float(order.total_amount),
            'is_exclusive': True,
            'exclusive_page_id': page.id,
            'items_count': total_items_count
        }
    )

    # 12. Send emails + push (async)
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    EmailManager.notify_order_confirmation(order)
    EmailManager.notify_admin_new_order(order)
    PushManager.notify_admin_new_order(order)

    # 12b. Broadcast dostępności do kupujących (rezerwacje usunięte → produkty wolne)
    try:
        from modules.exclusive.socket_events import broadcast_availability_update, _schedule_expiry_timer
        broadcast_availability_update(page.id)
        _schedule_expiry_timer(page.id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Broadcast availability failed for page {page.id}: {e}")

    # 12c. Emit Socket.IO events to LIVE dashboard
    try:
        from modules.exclusive.socket_events import emit_new_order, emit_stats_update
        from utils.exclusive_closure import get_live_summary

        # Build order data for real-time display
        order_items_list = []
        for item in order.items:
            order_items_list.append({
                'product_name': item.product_name,
                'quantity': item.quantity,
                'price': float(item.price),
                'total': float(item.total),
                'is_full_set': item.is_full_set,
                'is_custom': item.is_custom,
            })

        emit_new_order(page.id, {
            'id': order.id,
            'order_number': order.order_number,
            'customer_name': f'{current_user.first_name} {current_user.last_name}'.strip() or current_user.email,
            'customer_email': current_user.email,
            'total_amount': float(order.total_amount),
            'items_count': total_items_count,
            'items': order_items_list,
            'created_at': order.created_at.isoformat() if order.created_at else None,
        })

        # Get full live summary (stats + sets + products) and emit
        live = get_live_summary(page.id, include_financials=True)

        emit_stats_update(page.id, {
            'total_orders': live['total_orders'],
            'unique_customers': live['unique_customers'],
            'total_revenue': live.get('total_revenue', 0),
            'avg_order_value': live.get('avg_order_value', 0),
            'total_items': live['total_items'],
            'active_reservations': live['active_reservations'],
            'sets': live['sets'],
            'products_aggregated': live['products_aggregated'],
            'order_timestamps': live.get('order_timestamps', []),
        })
    except Exception as e:
        # Don't fail the order if Socket.IO emit fails
        import logging
        logging.getLogger(__name__).error(f"Socket.IO emit failed for page {page.id}: {str(e)}")

    # 13. Return success
    return True, {
        'order_id': order.id,
        'order_number': order.order_number,
        'total_amount': float(order.total_amount),
        'items_count': total_items_count,
    }
