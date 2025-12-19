"""
Exclusive Place Order Logic
Logika składania zamówień przez strony exclusive
"""

from flask import request
from flask_login import current_user
from datetime import datetime
from decimal import Decimal
from extensions import db
from modules.exclusive.models import ExclusiveReservation, ExclusivePage
from modules.exclusive.reservation import cleanup_expired_reservations
from modules.orders.models import Order, OrderItem
from modules.orders.utils import generate_order_number
from modules.products.models import Product
from utils.activity_logger import log_activity


def validate_guest_data(guest_data):
    """
    Validate guest order data

    Args:
        guest_data (dict): Guest information

    Returns:
        tuple: (valid: bool, error: str or None)
    """
    required_fields = ['name', 'email', 'phone']

    for field in required_fields:
        if not guest_data.get(field):
            return False, f'missing_field_{field}'

    # Basic email validation
    email = guest_data.get('email', '')
    if '@' not in email or '.' not in email:
        return False, 'invalid_email'

    # Basic phone validation (at least 9 digits)
    phone = guest_data.get('phone', '').replace(' ', '').replace('-', '').replace('+', '')
    if len(phone) < 9 or not phone.isdigit():
        return False, 'invalid_phone'

    return True, None


def check_product_availability(reservations, page_id):
    """
    Check if all reserved products are still available

    Args:
        reservations (list): List of ExclusiveReservation objects
        page_id (int): Exclusive page ID

    Returns:
        tuple: (available: bool, error: dict or None)
    """
    from modules.exclusive.models import ExclusiveSection, ExclusiveSetItem
    from modules.products.models import VariantGroup, variant_products

    for reservation in reservations:
        product = reservation.product

        # NOTE: Exclusive orders do NOT check global product stock (product.quantity)
        # Availability is controlled only by section limits (max_quantity)

        # Check section max_quantity limits
        # 1. Direct product section
        section = ExclusiveSection.query.filter_by(
            exclusive_page_id=page_id,
            section_type='product',
            product_id=product.id
        ).first()

        section_max = None

        if section:
            section_max = section.max_quantity
        else:
            # 2. Variant group section
            product_vg_ids = db.session.query(variant_products.c.variant_group_id).filter(
                variant_products.c.product_id == product.id
            ).all()
            product_vg_ids = [vg_id for (vg_id,) in product_vg_ids]

            if product_vg_ids:
                vg_section = ExclusiveSection.query.filter(
                    ExclusiveSection.exclusive_page_id == page_id,
                    ExclusiveSection.section_type == 'variant_group',
                    ExclusiveSection.variant_group_id.in_(product_vg_ids)
                ).first()

                if vg_section:
                    section_max = vg_section.max_quantity

            # 3. Set section
            if section_max is None:
                set_item = ExclusiveSetItem.query.join(ExclusiveSection).filter(
                    ExclusiveSection.exclusive_page_id == page_id,
                    ExclusiveSection.section_type == 'set',
                    ExclusiveSetItem.product_id == product.id
                ).first()

                if set_item:
                    section_max = set_item.section.set_max_per_product
                elif product_vg_ids:
                    set_item_vg = ExclusiveSetItem.query.join(ExclusiveSection).filter(
                        ExclusiveSection.exclusive_page_id == page_id,
                        ExclusiveSection.section_type == 'set',
                        ExclusiveSetItem.variant_group_id.in_(product_vg_ids)
                    ).first()
                    if set_item_vg:
                        section_max = set_item_vg.section.set_max_per_product

        # If section has max_quantity, check if product has enough
        if section_max is not None and section_max < reservation.quantity:
            return False, {
                'error': 'exceeds_section_limit',
                'product_id': product.id,
                'product_name': product.name,
                'requested': reservation.quantity,
                'section_max': section_max
            }

    return True, None


def place_exclusive_order(page, session_id, guest_data=None, order_note=None, full_sets=None):
    """
    Place an order from exclusive page

    Args:
        page (ExclusivePage): Exclusive page object
        session_id (str): User session ID
        guest_data (dict, optional): Guest information (name, email, phone)
        order_note (str, optional): Order note/comment
        full_sets (list, optional): Full sets from frontend (no reservation needed)

    Returns:
        tuple: (success: bool, result: dict)
    """
    if full_sets is None:
        full_sets = []

    # 1. Cleanup expired reservations
    cleanup_expired_reservations(page.id)

    # 2. Get user's reservations
    reservations = ExclusiveReservation.query.filter_by(
        session_id=session_id,
        exclusive_page_id=page.id
    ).all()

    # Check if there are any items to order (reservations OR full sets)
    has_full_sets = any(fs.get('qty', 0) > 0 for fs in full_sets)

    if not reservations and not has_full_sets:
        return False, {'error': 'no_reservations', 'message': 'Brak produktów w koszyku'}

    # 3. Validate guest data (if guest order)
    is_guest = not current_user.is_authenticated

    if is_guest:
        if not guest_data:
            return False, {'error': 'missing_guest_data', 'message': 'Brak danych użytkownika'}

        valid, error = validate_guest_data(guest_data)
        if not valid:
            return False, {'error': error, 'message': 'Nieprawidłowe dane użytkownika'}

        # Check if user with this email already exists - require login
        from modules.auth.models import User
        guest_email = guest_data.get('email', '').lower().strip()
        existing_user = User.query.filter_by(email=guest_email).first()
        if existing_user:
            return False, {
                'error': 'email_exists',
                'message': 'Konto z tym adresem email już istnieje. Zaloguj się, aby złożyć zamówienie.',
                'require_login': True
            }

    # 4. Check product availability
    available, error = check_product_availability(reservations, page.id)
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
        user_id=current_user.id if current_user.is_authenticated else None,
        status='nowe',
        is_exclusive=True,
        exclusive_page_id=page.id,
        is_guest_order=is_guest,
        guest_name=guest_data.get('name') if is_guest else None,
        guest_email=guest_data.get('email') if is_guest else None,
        guest_phone=guest_data.get('phone') if is_guest else None,
        notes=order_note,
        total_amount=Decimal('0.00')
    )

    db.session.add(order)
    db.session.flush()  # Get order.id

    # 6b. Generate guest view token for guest orders
    if is_guest:
        order.generate_guest_view_token()

    # 7. Create order items (exclusive orders do NOT affect global stock)
    total_amount = Decimal('0.00')

    for reservation in reservations:
        product = reservation.product
        quantity = reservation.quantity
        price = product.sale_price
        item_total = price * quantity

        # Create order item
        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            price=price,
            total=item_total,
            picked=False
        )

        db.session.add(order_item)

        # NOTE: Exclusive orders do NOT decrease global stock (product.quantity)
        # Stock is managed separately for exclusive orders

        # Update total
        total_amount += item_total

    # 7b. Create order items for FULL SETS (as custom products, no product_id)
    full_sets_count = 0
    for full_set in full_sets:
        set_qty = full_set.get('qty', 0)
        if set_qty <= 0:
            continue

        set_name = full_set.get('name', 'Pełny Set')
        set_price = full_set.get('price', 0)
        section_id = full_set.get('sectionId')

        # Parse section_id safely
        try:
            section_id = int(section_id) if section_id else None
        except (ValueError, TypeError):
            section_id = None

        # Calculate price
        price_per_set = Decimal(str(set_price)) if set_price else Decimal('0.00')
        item_total = price_per_set * set_qty

        # Create OrderItem as custom product (no product_id)
        order_item = OrderItem(
            order_id=order.id,
            product_id=None,  # No linked product
            custom_name=set_name,
            is_custom=True,
            is_full_set=True,
            quantity=set_qty,
            price=price_per_set,
            total=item_total,
            picked=False,
            is_set_fulfilled=True,  # Full sets are always "fulfilled"
            set_section_id=section_id
        )

        db.session.add(order_item)
        total_amount += item_total
        full_sets_count += 1

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

    # Calculate total items count
    total_items_count = len(reservations) + full_sets_count

    # 11. Activity log
    log_activity(
        user=current_user if current_user.is_authenticated else None,
        action='order_created',
        entity_type='order',
        entity_id=order.id,
        old_value=None,
        new_value={
            'order_number': order.order_number,
            'total': float(order.total_amount),
            'is_exclusive': True,
            'exclusive_page_id': page.id,
            'is_guest': is_guest,
            'items_count': total_items_count,
            'full_sets_count': full_sets_count
        }
    )

    # 12. Send emails (async)
    # TODO: Implement email sending
    # send_order_confirmation_email(order)
    # send_admin_notification_email(order)

    # 13. Return success
    return True, {
        'order_id': order.id,
        'order_number': order.order_number,
        'total_amount': float(order.total_amount),
        'items_count': total_items_count,
        'is_guest': is_guest,
        'guest_view_token': order.guest_view_token if is_guest else None,
        'guest_name': order.guest_name if is_guest else None,
        'guest_email': order.guest_email if is_guest else None,
        'guest_phone': order.guest_phone if is_guest else None
    }
