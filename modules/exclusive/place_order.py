"""
Exclusive Place Order Logic
Logika składania zamówień przez strony exclusive
"""

from flask_login import current_user
from decimal import Decimal
from extensions import db
from modules.exclusive.models import ExclusiveReservation, ExclusivePage, ExclusiveSetBonus, ExclusiveSetBonusRequiredProduct
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


def place_exclusive_order(page, session_id, order_note=None, full_set_items=None):
    """
    Place an order from exclusive page (requires authenticated user)

    Args:
        page (ExclusivePage): Exclusive page object
        session_id (str): User session ID
        order_note (str, optional): Order note/comment
        full_set_items (list, optional): List of full set items [{'product_id': int, 'quantity': int}]

    Returns:
        tuple: (success: bool, result: dict)
    """
    from modules.products.models import Product

    if full_set_items is None:
        full_set_items = []

    # 1. Cleanup expired reservations
    cleanup_expired_reservations(page.id)

    # 2. Get user's reservations
    reservations = ExclusiveReservation.query.filter_by(
        session_id=session_id,
        exclusive_page_id=page.id
    ).all()

    # Check if there are any items to order (reservations OR full set items)
    if not reservations and not full_set_items:
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

    # 7a. Process full set items (not in reservations — unlimited)
    for fs_item in full_set_items:
        fs_product_id = fs_item.get('product_id')
        fs_quantity = fs_item.get('quantity', 0)
        if not fs_product_id or fs_quantity <= 0:
            continue

        # Max 5 full sets per order
        if fs_quantity > 5:
            fs_quantity = 5

        # Verify this is actually a set_product for this page
        if fs_product_id not in set_product_ids:
            continue

        fs_product = Product.query.get(fs_product_id)
        if not fs_product:
            continue

        fs_price = fs_product.sale_price
        fs_total = fs_price * fs_quantity

        order_item = OrderItem(
            order_id=order.id,
            product_id=fs_product.id,
            quantity=fs_quantity,
            price=fs_price,
            total=fs_total,
            picked=False,
            is_full_set=True,
        )
        db.session.add(order_item)
        total_amount += fs_total

    # 7b. Evaluate bonuses for set sections
    # Flush so order.items relationship sees all newly added items
    db.session.flush()

    for sec in set_sections:
        active_bonuses = ExclusiveSetBonus.query.filter_by(
            section_id=sec.id, is_active=True
        ).all()

        for bonus in active_bonuses:
            # Check global limit for this bonus
            claimed = 0
            if bonus.max_available is not None:
                from sqlalchemy import func as sql_func2
                claimed = db.session.query(
                    sql_func2.coalesce(sql_func2.sum(OrderItem.quantity), 0)
                ).join(Order).filter(
                    OrderItem.is_bonus == True,
                    OrderItem.bonus_source_section_id == sec.id,
                    OrderItem.product_id == bonus.bonus_product_id,
                    Order.exclusive_page_id == page.id,
                    Order.status != 'anulowane'
                ).with_for_update().scalar()
                if claimed >= bonus.max_available:
                    continue

            # Get order items from this section in current order (non-bonus only)
            section_items = [item for item in order.items if
                            item.product_id in product_set_info and
                            product_set_info[item.product_id]['section_id'] == sec.id and
                            not item.is_bonus]

            # Get full set items for this section
            section_full_set_items = [item for item in order.items if
                                      item.is_full_set and item.product_id == sec.set_product_id]
            full_set_qty = sum(item.quantity for item in section_full_set_items)

            bonus_earned = 0

            if bonus.trigger_type == 'buy_products':
                # Check if all required products are in the order
                required = bonus.required_products
                if not required:
                    continue
                # Calculate how many complete bundles
                bundle_counts = []
                for req in required:
                    matching = [i for i in section_items if i.product_id == req.product_id]
                    qty_in_order = sum(i.quantity for i in matching)
                    # Full set contains all products — each full set counts as quantity_per_set
                    if bonus.count_full_set and full_set_qty > 0:
                        qps = product_set_info.get(req.product_id, {}).get('quantity_per_set', 1)
                        qty_in_order += full_set_qty * qps
                    bundle_counts.append(qty_in_order // req.min_quantity)
                bonus_earned = min(bundle_counts) if bundle_counts else 0

            elif bonus.trigger_type == 'price_threshold':
                if bonus.threshold_value is None or float(bonus.threshold_value) <= 0:
                    continue
                section_total = sum(float(item.total) for item in section_items)
                if bonus.count_full_set:
                    section_total += sum(float(item.total) for item in section_full_set_items)
                if section_total >= float(bonus.threshold_value):
                    bonus_earned = 1

            elif bonus.trigger_type == 'quantity_threshold':
                if bonus.threshold_value is None or int(bonus.threshold_value) <= 0:
                    continue
                section_qty = sum(item.quantity for item in section_items)
                if bonus.count_full_set:
                    section_qty += full_set_qty
                if section_qty >= int(bonus.threshold_value):
                    bonus_earned = 1

            # Apply limit
            if bonus.max_available is not None:
                bonus_earned = min(bonus_earned, bonus.max_available - claimed)

            if bonus_earned > 0:
                bonus_product = Product.query.get(bonus.bonus_product_id)
                if not bonus_product:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Bonus product id={bonus.bonus_product_id} not found for bonus id={bonus.id}, skipping"
                    )
                    continue

                bonus_item = OrderItem(
                    order_id=order.id,
                    product_id=bonus.bonus_product_id,
                    quantity=bonus.bonus_quantity * bonus_earned,
                    price=Decimal('0.00'),
                    total=Decimal('0.00'),
                    is_bonus=True,
                    bonus_source_section_id=sec.id,
                    picked=False,
                )
                db.session.add(bonus_item)

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

    # Calculate total items count (reservations + full set items)
    total_items_count = len(reservations) + len([fs for fs in full_set_items if fs.get('quantity', 0) > 0 and fs.get('product_id') in set_product_ids])

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
    PushManager.notify_order_confirmation(order)
    EmailManager.notify_admin_new_order(order)
    PushManager.notify_admin_new_order(order)

    # 12b. Broadcast dostępności do kupujących (rezerwacje usunięte → produkty wolne)
    page_id = page.id
    try:
        from modules.exclusive.socket_events import broadcast_availability_update, _schedule_expiry_timer
        broadcast_availability_update(page_id)
        _schedule_expiry_timer(page_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Broadcast availability failed for page {page_id}: {e}")

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
                'is_bonus': item.is_bonus,
            })

        emit_new_order(page.id, {
            'id': order.id,
            'order_number': order.order_number,
            'customer_name': f'{current_user.first_name} {current_user.last_name}'.strip() or current_user.email,
            'customer_email': current_user.email,
            'total_amount': float(order.total_amount),
            'item_count': total_items_count,
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

    # 12d. Achievement hook: order placed
    try:
        from flask import request as flask_request
        from modules.achievements.services import AchievementService
        page_entered_at = None
        try:
            page_entered_at = flask_request.form.get('page_entered_at', type=float)
        except Exception:
            pass
        AchievementService().check_event(current_user, 'order_placed', {
            'items_count': total_items_count,
            'total_amount': float(order.total_amount),
            'is_exclusive': True,
            'exclusive_page_starts_at': page.starts_at,
            'page_entered_at': page_entered_at,
        })
    except Exception:
        pass

    # 13. Return success
    return True, {
        'order_id': order.id,
        'order_number': order.order_number,
        'total_amount': float(order.total_amount),
        'items_count': total_items_count,
    }
