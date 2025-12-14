"""
Orders Module - Routes
======================

Routes for orders management (Admin + Client + API).
Includes HTMX endpoints for partial updates.
"""

import json
from flask import render_template, request, redirect, url_for, flash, jsonify, abort, make_response
from flask_login import login_required, current_user
from sqlalchemy import or_, and_
from datetime import datetime
from decimal import Decimal

from modules.orders import orders_bp
from modules.orders.models import (
    Order, OrderItem, OrderComment, OrderRefund,
    OrderStatus, OrderType, WmsStatus
)
from modules.orders.forms import (
    OrderFilterForm, OrderStatusForm, OrderCommentForm,
    OrderTrackingForm, RefundForm, BulkActionForm,
    ShippingAddressForm, PickupPointForm
)
from modules.orders.utils import (
    generate_order_number, detect_courier, get_tracking_url,
    calculate_order_total, get_order_summary
)
from extensions import db
from utils.decorators import role_required
from utils.activity_logger import log_activity
# from modules.emails.sender import send_email  # Uncomment when email module is ready


# ====================
# ADMIN ROUTES
# ====================

@orders_bp.route('/admin/orders')
@login_required
@role_required('admin', 'mod')
def admin_list():
    """
    Admin orders list with filters and pagination.
    Supports quick filters (order type) and advanced filters.
    """
    # Initialize filter form
    filter_form = OrderFilterForm(request.args)

    # Populate status choices dynamically
    statuses = OrderStatus.query.filter_by(is_active=True).order_by(OrderStatus.sort_order).all()
    filter_form.status.choices = [(s.slug, s.name) for s in statuses]

    # Base query
    query = Order.query

    # Apply filters
    if filter_form.order_type.data:
        query = query.filter(Order.order_type == filter_form.order_type.data)

    if filter_form.status.data:
        query = query.filter(Order.status.in_(filter_form.status.data))

    if filter_form.date_from.data:
        query = query.filter(Order.created_at >= filter_form.date_from.data)

    if filter_form.date_to.data:
        # Add 1 day to include the end date
        from datetime import timedelta
        end_date = filter_form.date_to.data + timedelta(days=1)
        query = query.filter(Order.created_at < end_date)

    if filter_form.search.data:
        search_term = f"%{filter_form.search.data}%"
        query = query.join(Order.user, isouter=True).filter(
            or_(
                Order.order_number.like(search_term),
                Order.guest_name.like(search_term),
                Order.guest_email.like(search_term),
                db.func.concat(db.text("users.first_name"), ' ', db.text("users.last_name")).like(search_term),
                db.text("users.email").like(search_term)
            )
        )

    # Sorting
    sort_by = request.args.get('sort', 'created_at')
    sort_order = request.args.get('order', 'desc')

    if sort_by == 'order_number':
        query = query.order_by(Order.order_number.desc() if sort_order == 'desc' else Order.order_number.asc())
    elif sort_by == 'total_amount':
        query = query.order_by(Order.total_amount.desc() if sort_order == 'desc' else Order.total_amount.asc())
    else:  # Default: created_at
        query = query.order_by(Order.created_at.desc() if sort_order == 'desc' else Order.created_at.asc())

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = int(filter_form.per_page.data) if filter_form.per_page.data else 20

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'admin/orders/list.html',
        orders=pagination,
        filter_form=filter_form,
        page_title='Zamówienia'
    )


@orders_bp.route('/admin/orders/<int:order_id>')
@login_required
@role_required('admin', 'mod')
def admin_detail(order_id):
    """
    Admin order detail page.
    Shows full order information, timeline, comments, products, etc.
    """
    order = Order.query.get_or_404(order_id)

    # Eager load relationships
    order_items = OrderItem.query.filter_by(order_id=order_id).all()
    comments = OrderComment.query.filter_by(order_id=order_id).order_by(OrderComment.created_at.desc()).all()
    refunds = OrderRefund.query.filter_by(order_id=order_id).order_by(OrderRefund.created_at.desc()).all()

    # Forms
    status_form = OrderStatusForm()
    comment_form = OrderCommentForm()
    tracking_form = OrderTrackingForm(obj=order)
    refund_form = RefundForm()
    shipping_address_form = ShippingAddressForm(obj=order)
    pickup_point_form = PickupPointForm(obj=order)

    # Populate status choices
    statuses = OrderStatus.query.filter_by(is_active=True).order_by(OrderStatus.sort_order).all()
    status_form.status.choices = [(s.slug, s.name) for s in statuses]
    status_form.status.data = order.status

    # Build statuses list with colors for custom dropdown
    statuses_with_colors = [
        {'slug': s.slug, 'name': s.name, 'color': s.badge_color}
        for s in statuses
    ]

    # Set default refund amount to order total
    refund_form.amount.data = order.total_amount

    # Build timeline (merge comments and events)
    timeline = []

    # Add created event
    timeline.append({
        'type': 'created',
        'created_at': order.created_at,
        'icon': '📦',
        'message': 'Zamówienie utworzone'
    })

    # Add comments
    for comment in comments:
        timeline.append({
            'type': 'comment',
            'created_at': comment.created_at,
            'user': comment.user,
            'comment': comment.comment,
            'is_internal': comment.is_internal,
            'is_from_admin': comment.is_from_admin
        })

    # Add refunds
    for refund in refunds:
        timeline.append({
            'type': 'refund',
            'created_at': refund.created_at,
            'amount': refund.amount,
            'reason': refund.reason,
            'status': refund.status,
            'creator': refund.creator
        })

    # Add activity logs for this order
    from modules.admin.models import ActivityLog
    import json
    activity_logs = ActivityLog.query.filter_by(
        entity_type='order',
        entity_id=order.id
    ).order_by(ActivityLog.created_at).all()

    for log in activity_logs:
        # Parse new_value JSON if exists
        new_value_data = {}
        if log.new_value:
            try:
                new_value_data = json.loads(log.new_value)
            except:
                pass

        old_value_data = {}
        if log.old_value:
            try:
                old_value_data = json.loads(log.old_value)
            except:
                pass

        timeline.append({
            'type': 'activity',
            'created_at': log.created_at,
            'action': log.action,
            'user': log.user,
            'old_value': old_value_data,
            'new_value': new_value_data
        })

    # Sort timeline by date (oldest first, newest at bottom)
    timeline.sort(key=lambda x: x['created_at'], reverse=False)

    # Get categories and product series for add products modal
    from modules.products.models import Category, ProductSeries
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
    product_series = ProductSeries.query.filter_by(is_active=True).order_by(ProductSeries.name).all()

    return render_template(
        'admin/orders/detail.html',
        order=order,
        order_items=order_items,
        timeline=timeline,
        status_form=status_form,
        statuses_with_colors=statuses_with_colors,
        comment_form=comment_form,
        tracking_form=tracking_form,
        refund_form=refund_form,
        shipping_address_form=shipping_address_form,
        pickup_point_form=pickup_point_form,
        categories=categories,
        product_series=product_series,
        page_title=f'Zamówienie {order.order_number}'
    )


# ====================
# ADMIN HTMX ENDPOINTS
# ====================

@orders_bp.route('/admin/orders/<int:order_id>/status', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_update_status(order_id):
    """
    HTMX endpoint for changing order status.
    Returns updated status badge HTML with HX-Trigger for toast.
    """
    order = Order.query.get_or_404(order_id)

    # Get status from form data (works with both WTForms and custom dropdown)
    new_status = request.form.get('status')

    if not new_status:
        response = make_response('<span class="badge badge-error">Błąd: brak statusu</span>', 400)
        response.headers['HX-Trigger'] = json.dumps({'showToast': {'message': 'Błąd: brak statusu', 'type': 'error'}})
        return response

    # Validate that status exists
    status_obj = OrderStatus.query.filter_by(slug=new_status, is_active=True).first()
    if not status_obj:
        response = make_response('<span class="badge badge-error">Błąd: nieprawidłowy status</span>', 400)
        response.headers['HX-Trigger'] = json.dumps({'showToast': {'message': 'Błąd: nieprawidłowy status', 'type': 'error'}})
        return response

    old_status = order.status
    old_status_name = order.status_display_name

    if old_status != new_status:
        order.status = new_status
        order.updated_at = datetime.utcnow()
        db.session.commit()

        # Activity log
        log_activity(
            user=current_user,
            action='order_status_change',
            entity_type='order',
            entity_id=order.id,
            old_value={'status': old_status},
            new_value={'status': new_status}
        )

        # Return updated badge HTML with HX-Trigger for toast
        badge_html = f'<span class="badge" style="background-color: {order.status_badge_color}; color: #fff;" id="statusBadge">{order.status_display_name}</span>'
        response = make_response(badge_html)
        response.headers['HX-Trigger'] = json.dumps({
            'showToast': {
                'message': f'Status zmieniony: {old_status_name} → {order.status_display_name}',
                'type': 'success'
            }
        })
        return response

    # No change - return current badge
    return f'<span class="badge" style="background-color: {order.status_badge_color}; color: #fff;" id="statusBadge">{order.status_display_name}</span>'


@orders_bp.route('/admin/orders/<int:order_id>/comment', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_add_comment(order_id):
    """
    HTMX endpoint for adding comment to order.
    Returns new comment HTML to prepend to timeline.
    """
    order = Order.query.get_or_404(order_id)
    form = OrderCommentForm()

    if form.validate_on_submit():
        comment = OrderComment(
            order_id=order.id,
            user_id=current_user.id,
            comment=form.comment.data,
            is_internal=form.is_internal.data if current_user.role in ['admin', 'mod'] else False
        )
        db.session.add(comment)
        db.session.commit()

        # Activity log
        # log_activity(
        #     user=current_user,
        #     action='order_comment_added',
        #     entity_type='order',
        #     entity_id=order.id,
        #     new_value={'comment_id': comment.id, 'is_internal': comment.is_internal}
        # )

        # Email notification (if not internal)
        # if not comment.is_internal:
        #     send_email(
        #         to=order.customer_email,
        #         template_type='order_comment',
        #         context={
        #             'order': get_order_summary(order),
        #             'comment': comment.comment,
        #             'author': comment.author_name
        #         }
        #     )

        flash('Komentarz dodany', 'success')

        # Return new comment HTML
        return render_template('admin/orders/_comment_item.html', comment=comment)

    return '<div class="alert alert-error">Błąd podczas dodawania komentarza</div>', 400


@orders_bp.route('/admin/orders/<int:order_id>/shipping-address', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_update_shipping_address(order_id):
    """
    HTMX endpoint for updating shipping address.
    Returns success message.
    """
    order = Order.query.get_or_404(order_id)
    form = ShippingAddressForm()

    if form.validate_on_submit():
        order.shipping_name = form.shipping_name.data
        order.shipping_address = form.shipping_address.data
        order.shipping_postal_code = form.shipping_postal_code.data
        order.shipping_city = form.shipping_city.data
        order.shipping_voivodeship = form.shipping_voivodeship.data
        order.shipping_country = form.shipping_country.data or 'Polska'
        order.updated_at = datetime.utcnow()
        db.session.commit()

        flash('Adres dostawy zaktualizowany', 'success')
        return '<div class="alert alert-success">Adres dostawy zapisany</div>'

    return '<div class="alert alert-error">Błąd podczas aktualizacji adresu</div>', 400


@orders_bp.route('/admin/orders/<int:order_id>/pickup-point', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_update_pickup_point(order_id):
    """
    HTMX endpoint for updating pickup point.
    Returns success message.
    """
    order = Order.query.get_or_404(order_id)
    form = PickupPointForm()

    if form.validate_on_submit():
        order.pickup_courier = form.pickup_courier.data
        order.pickup_point_id = form.pickup_point_id.data
        order.pickup_address = form.pickup_address.data
        order.pickup_postal_code = form.pickup_postal_code.data
        order.pickup_city = form.pickup_city.data
        order.updated_at = datetime.utcnow()
        db.session.commit()

        flash('Punkt odbioru zaktualizowany', 'success')
        return '<div class="alert alert-success">Punkt odbioru zapisany</div>'

    return '<div class="alert alert-error">Błąd podczas aktualizacji punktu odbioru</div>', 400


@orders_bp.route('/admin/orders/<int:order_id>/tracking', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_update_tracking(order_id):
    """
    HTMX endpoint for updating tracking information.
    Returns updated tracking info HTML.
    """
    order = Order.query.get_or_404(order_id)
    form = OrderTrackingForm()

    if form.validate_on_submit():
        order.tracking_number = form.tracking_number.data
        order.courier = form.courier.data
        order.updated_at = datetime.utcnow()
        db.session.commit()

        # Activity log
        # log_activity(
        #     user=current_user,
        #     action='order_tracking_updated',
        #     entity_type='order',
        #     entity_id=order.id,
        #     new_value={
        #         'tracking_number': order.tracking_number,
        #         'courier': order.courier
        #     }
        # )

        flash('Informacje o śledzeniu zaktualizowane', 'success')

        # Return updated tracking info HTML
        return render_template('admin/orders/_tracking_info.html', order=order)

    return '<div class="alert alert-error">Błąd podczas aktualizacji</div>', 400


@orders_bp.route('/admin/orders/<int:order_id>/refund', methods=['POST'])
@login_required
@role_required('admin')  # Only admin can issue refunds
def admin_issue_refund(order_id):
    """
    Issue refund for order.
    Changes order status to 'do_zwrotu' or 'czesciowo_zwrocone'.
    """
    order = Order.query.get_or_404(order_id)
    form = RefundForm()

    if form.validate_on_submit():
        # Create refund record
        refund = OrderRefund(
            order_id=order.id,
            amount=form.amount.data,
            reason=form.reason.data,
            status='pending',
            created_by=current_user.id
        )
        db.session.add(refund)

        # Update order status
        total_refunded = sum(r.amount for r in order.refunds if r.status == 'completed')
        total_refunded += form.amount.data

        if total_refunded >= order.total_amount:
            order.status = 'zwrocone'
        else:
            order.status = 'czesciowo_zwrocone'

        order.updated_at = datetime.utcnow()
        db.session.commit()

        # Activity log
        # log_activity(
        #     user=current_user,
        #     action='refund_issued',
        #     entity_type='order',
        #     entity_id=order.id,
        #     new_value={
        #         'refund_id': refund.id,
        #         'amount': float(refund.amount),
        #         'reason': refund.reason
        #     }
        # )

        # Email notification
        # send_email(
        #     to=order.customer_email,
        #     template_type='refund_notification',
        #     context={
        #         'order': get_order_summary(order),
        #         'refund_amount': float(refund.amount),
        #         'refund_reason': refund.reason
        #     }
        # )

        flash(f'Zwrot w kwocie {refund.amount} PLN został utworzony', 'success')
        return redirect(url_for('orders.admin_detail', order_id=order.id))

    flash('Błąd podczas tworzenia zwrotu', 'error')
    return redirect(url_for('orders.admin_detail', order_id=order.id))


# ====================
# PAYMENT ENDPOINT
# ====================

@orders_bp.route('/admin/orders/<int:order_id>/payment', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_update_payment(order_id):
    """
    Update order payment amount.
    Returns JSON response.
    """
    order = Order.query.get_or_404(order_id)

    try:
        data = request.get_json()
        paid_amount = data.get('paid_amount')

        if paid_amount is None:
            return jsonify({
                'success': False,
                'message': 'Kwota płatności jest wymagana'
            }), 400

        # Convert to Decimal
        try:
            paid_amount = Decimal(str(paid_amount))
        except:
            return jsonify({
                'success': False,
                'message': 'Nieprawidłowa kwota'
            }), 400

        if paid_amount < 0:
            return jsonify({
                'success': False,
                'message': 'Kwota nie może być ujemna'
            }), 400

        # Store old value for logging
        old_paid_amount = order.paid_amount

        # Update payment
        order.paid_amount = paid_amount
        order.updated_at = datetime.utcnow()
        db.session.commit()

        # Activity log
        log_activity(
            user=current_user,
            action='order_payment_updated',
            entity_type='order',
            entity_id=order.id,
            old_value={'paid_amount': float(old_paid_amount) if old_paid_amount else 0},
            new_value={'paid_amount': float(paid_amount)}
        )

        return jsonify({
            'success': True,
            'message': 'Płatność została zaktualizowana',
            'paid_amount': float(paid_amount),
            'is_fully_paid': order.is_fully_paid,
            'is_partially_paid': order.is_partially_paid
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


# ====================
# UPDATE ORDER FIELD ENDPOINT
# ====================

@orders_bp.route('/admin/orders/<int:order_id>/update-field', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_update_order_field(order_id):
    """
    Update a single field of an order.
    Returns JSON response with updated values.
    """
    order = Order.query.get_or_404(order_id)

    try:
        data = request.get_json()
        field = data.get('field')
        value = data.get('value')

        if not field:
            return jsonify({
                'success': False,
                'message': 'Nazwa pola jest wymagana'
            }), 400

        # Allowed fields that can be updated
        allowed_fields = ['delivery_method', 'shipping_cost', 'payment_method']

        if field not in allowed_fields:
            return jsonify({
                'success': False,
                'message': f'Pole "{field}" nie może być aktualizowane'
            }), 400

        # Store old value for logging
        old_value = getattr(order, field)

        # Update the field
        if field == 'shipping_cost':
            from decimal import Decimal
            try:
                value = Decimal(str(value)) if value else Decimal('0.00')
            except:
                return jsonify({
                    'success': False,
                    'message': 'Nieprawidłowa kwota'
                }), 400

            if value < 0:
                return jsonify({
                    'success': False,
                    'message': 'Koszt wysyłki nie może być ujemny'
                }), 400

            order.shipping_cost = value
        elif field == 'delivery_method':
            order.delivery_method = value if value else None
        elif field == 'payment_method':
            order.payment_method = value if value else None

        order.updated_at = datetime.utcnow()
        db.session.commit()

        # Activity log
        log_activity(
            user=current_user,
            action='order_field_updated',
            entity_type='order',
            entity_id=order.id,
            old_value={field: str(old_value) if old_value is not None else None},
            new_value={field: str(value) if value is not None else None}
        )

        # Return updated values
        response_data = {
            'success': True,
            'message': 'Zaktualizowano pomyślnie',
            'field': field,
            'value': str(value) if value else None
        }

        # For shipping_cost, also return grand_total and payment status
        if field == 'shipping_cost':
            response_data['grand_total'] = float(order.grand_total)
            response_data['paid_amount'] = float(order.paid_amount) if order.paid_amount else 0
            response_data['is_fully_paid'] = order.is_fully_paid
            response_data['is_partially_paid'] = order.is_partially_paid

        return jsonify(response_data)

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


# ====================
# SHIPMENTS ENDPOINTS
# ====================

@orders_bp.route('/admin/orders/<int:order_id>/shipments', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_add_shipment(order_id):
    """
    Add a shipment to order.
    Returns JSON response.
    """
    from modules.orders.models import OrderShipment

    order = Order.query.get_or_404(order_id)

    try:
        data = request.get_json()
        tracking_number = data.get('tracking_number', '').strip()
        courier = data.get('courier', '').strip()

        if not tracking_number:
            return jsonify({
                'success': False,
                'message': 'Numer przesyłki jest wymagany'
            }), 400

        if not courier:
            return jsonify({
                'success': False,
                'message': 'Kurier jest wymagany'
            }), 400

        # Check if shipment already exists
        existing = OrderShipment.query.filter_by(
            order_id=order_id,
            tracking_number=tracking_number
        ).first()

        if existing:
            return jsonify({
                'success': False,
                'message': 'Przesyłka o tym numerze już istnieje'
            }), 400

        # Create new shipment
        shipment = OrderShipment(
            order_id=order_id,
            tracking_number=tracking_number,
            courier=courier,
            created_by=current_user.id
        )
        db.session.add(shipment)
        db.session.commit()

        # Activity log
        log_activity(
            user=current_user,
            action='shipment_added',
            entity_type='order',
            entity_id=order.id,
            new_value={
                'tracking_number': tracking_number,
                'courier': courier,
                'order_number': order.order_number
            }
        )

        return jsonify({
            'success': True,
            'message': 'Przesyłka została dodana',
            'shipment': {
                'id': shipment.id,
                'tracking_number': shipment.tracking_number,
                'courier': shipment.courier,
                'courier_name': shipment.courier_display_name,
                'tracking_url': shipment.tracking_url,
                'created_at': shipment.created_at.strftime('%Y-%m-%d %H:%M')
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas dodawania przesyłki: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/<int:order_id>/shipments/<int:shipment_id>', methods=['DELETE'])
@login_required
@role_required('admin', 'mod')
def admin_delete_shipment(order_id, shipment_id):
    """
    Delete a shipment from order.
    Returns JSON response.
    """
    from modules.orders.models import OrderShipment

    order = Order.query.get_or_404(order_id)
    shipment = OrderShipment.query.filter_by(id=shipment_id, order_id=order_id).first_or_404()

    try:
        tracking_number = shipment.tracking_number
        courier = shipment.courier

        db.session.delete(shipment)
        db.session.commit()

        # Activity log
        log_activity(
            user=current_user,
            action='shipment_deleted',
            entity_type='order',
            entity_id=order.id,
            old_value={
                'tracking_number': tracking_number,
                'courier': courier,
                'order_number': order.order_number
            }
        )

        return jsonify({
            'success': True,
            'message': 'Przesyłka została usunięta'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas usuwania przesyłki: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/<int:order_id>/delete', methods=['DELETE', 'POST'])
@login_required
@role_required('admin')  # Only admin can delete
def admin_delete_order(order_id):
    """
    Delete order (admin only).
    Returns JSON response for AJAX/HTMX.
    """
    order = Order.query.get_or_404(order_id)

    # Activity log before deletion
    # log_activity(
    #     user=current_user,
    #     action='order_deleted',
    #     entity_type='order',
    #     entity_id=order.id,
    #     old_value={
    #         'order_number': order.order_number,
    #         'customer': order.customer_name,
    #         'total_amount': float(order.total_amount)
    #     }
    # )

    db.session.delete(order)
    db.session.commit()

    flash(f'Zamówienie {order.order_number} zostało usunięte', 'success')

    return jsonify({'success': True, 'message': 'Zamówienie usunięte'}), 200


# ====================
# API ENDPOINTS
# ====================

@orders_bp.route('/api/orders/detect-courier')
@login_required
@role_required('admin', 'mod')
def api_detect_courier():
    """
    API endpoint for courier auto-detection.
    Returns JSON with courier suggestion.
    """
    tracking_number = request.args.get('tracking', '')

    if not tracking_number:
        return jsonify({'courier': None, 'confidence': 'low', 'url': None})

    result = detect_courier(tracking_number)

    return jsonify(result)


# ====================
# CLIENT ROUTES
# ====================

@orders_bp.route('/client/orders')
@login_required
def client_list():
    """
    Client order history.
    Shows only orders belonging to current user.
    """
    # Filters
    status_filter = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    # Base query (only user's orders)
    query = Order.query.filter_by(user_id=current_user.id)

    # Apply filters
    if status_filter:
        query = query.filter(Order.status == status_filter)

    if date_from:
        query = query.filter(Order.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))

    if date_to:
        from datetime import timedelta
        end_date = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
        query = query.filter(Order.created_at < end_date)

    # Sorting
    query = query.order_by(Order.created_at.desc())

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Get statuses for filter dropdown
    statuses = OrderStatus.query.filter_by(is_active=True).order_by(OrderStatus.sort_order).all()

    return render_template(
        'client/orders/list.html',
        orders=pagination,
        statuses=statuses,
        page_title='Moje zamówienia'
    )


@orders_bp.route('/client/orders/<int:order_id>')
@login_required
def client_detail(order_id):
    """
    Client order detail page.
    User can only view their own orders.
    """
    order = Order.query.get_or_404(order_id)

    # Security check: User can only view their own orders
    if order.user_id != current_user.id:
        abort(403)

    # Load relationships
    order_items = OrderItem.query.filter_by(order_id=order_id).all()
    comments = OrderComment.query.filter_by(
        order_id=order_id,
        is_internal=False  # Hide internal comments from client
    ).order_by(OrderComment.created_at.desc()).all()

    # Comment form
    comment_form = OrderCommentForm()

    # Build timeline (only non-internal items)
    timeline = []

    timeline.append({
        'type': 'created',
        'created_at': order.created_at,
        'icon': '📦',
        'message': 'Zamówienie utworzone'
    })

    for comment in comments:
        timeline.append({
            'type': 'comment',
            'created_at': comment.created_at,
            'user': comment.user,
            'comment': comment.comment,
            'is_from_admin': comment.is_from_admin
        })

    timeline.sort(key=lambda x: x['created_at'], reverse=True)

    return render_template(
        'client/orders/detail.html',
        order=order,
        order_items=order_items,
        timeline=timeline,
        comment_form=comment_form,
        page_title=f'Zamówienie {order.order_number}'
    )


@orders_bp.route('/client/orders/<int:order_id>/comment', methods=['POST'])
@login_required
def client_add_comment(order_id):
    """
    HTMX endpoint for client to add comment to their order.
    """
    order = Order.query.get_or_404(order_id)

    # Security check
    if order.user_id != current_user.id:
        abort(403)

    form = OrderCommentForm()

    if form.validate_on_submit():
        comment = OrderComment(
            order_id=order.id,
            user_id=current_user.id,
            comment=form.comment.data,
            is_internal=False  # Client comments are never internal
        )
        db.session.add(comment)
        db.session.commit()

        # Email to admin
        # send_email(
        #     to='karolinaburza@gmail.com',  # From settings
        #     template_type='order_comment',
        #     context={
        #         'order': get_order_summary(order),
        #         'comment': comment.comment,
        #         'author': comment.author_name
        #     }
        # )

        flash('Komentarz dodany', 'success')

        # Return new comment HTML
        return render_template('client/orders/_comment_item.html', comment=comment)

    return '<div class="alert alert-error">Błąd podczas dodawania komentarza</div>', 400


# ====================
# SETTINGS
# ====================

@orders_bp.route('/admin/orders/settings', methods=['GET'])
@login_required
@role_required('admin')
def settings():
    """
    Orders settings page - manage statuses and WMS statuses.
    Only accessible to admins.
    """
    # Load all order statuses
    statuses = OrderStatus.query.order_by(OrderStatus.sort_order).all()

    # Load all WMS statuses
    wms_statuses = WmsStatus.query.order_by(WmsStatus.sort_order).all()

    return render_template(
        'admin/orders/settings.html',
        statuses=statuses,
        wms_statuses=wms_statuses,
        page_title='Ustawienia zamówień'
    )


# ============================================
# API ENDPOINTS (for modals)
# ============================================

@orders_bp.route('/api/orders/statuses/<int:status_id>')
@login_required
@role_required('admin')
def api_get_status(status_id):
    """Get status data for edit modal."""
    status = OrderStatus.query.get_or_404(status_id)
    return jsonify({
        'id': status.id,
        'name': status.name,
        'slug': status.slug,
        'badge_color': status.badge_color,
        'is_active': status.is_active
    })


@orders_bp.route('/admin/orders/statuses/create', methods=['POST'])
@login_required
@role_required('admin')
def create_status():
    """Create new order status."""
    from modules.orders.utils import generate_slug

    name = request.form.get('name', '').strip()
    badge_color = request.form.get('badge_color', '#6B7280')
    is_active = request.form.get('is_active') == 'on'

    # Validation
    errors = {}
    if not name:
        errors['name'] = 'Nazwa statusu jest wymagana'

    # Generate slug from name
    slug = generate_slug(name)

    # Check if slug already exists
    existing = OrderStatus.query.filter_by(slug=slug).first()
    if existing:
        errors['name'] = f'Status o nazwie "{name}" już istnieje (slug: {slug})'

    if errors:
        return jsonify({'success': False, 'errors': errors}), 400

    # Create new status
    status = OrderStatus(
        name=name,
        slug=slug,
        badge_color=badge_color,
        is_active=is_active,
        sort_order=OrderStatus.query.count()  # Add at the end
    )

    db.session.add(status)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Status "{name}" został utworzony',
        'status_id': status.id
    })


@orders_bp.route('/admin/orders/statuses/<int:status_id>/edit', methods=['POST'])
@login_required
@role_required('admin')
def edit_status(status_id):
    """Edit existing order status."""
    from modules.orders.utils import generate_slug

    status = OrderStatus.query.get_or_404(status_id)

    name = request.form.get('name', '').strip()
    badge_color = request.form.get('badge_color', '#6B7280')
    is_active = request.form.get('is_active') == 'on'

    # Validation
    errors = {}
    if not name:
        errors['name'] = 'Nazwa statusu jest wymagana'

    # Generate new slug from name
    new_slug = generate_slug(name)

    # Check if slug already exists (but not for this status)
    existing = OrderStatus.query.filter(
        OrderStatus.slug == new_slug,
        OrderStatus.id != status_id
    ).first()
    if existing:
        errors['name'] = f'Status o nazwie "{name}" już istnieje (slug: {new_slug})'

    if errors:
        return jsonify({'success': False, 'errors': errors}), 400

    # Update status
    status.name = name
    status.slug = new_slug
    status.badge_color = badge_color
    status.is_active = is_active

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Status "{name}" został zaktualizowany'
    })


@orders_bp.route('/admin/orders/statuses/<int:status_id>/check-usage')
@login_required
@role_required('admin')
def check_status_usage(status_id):
    """Check if status is used in any orders before deletion."""
    status = OrderStatus.query.get_or_404(status_id)
    orders_count = Order.query.filter_by(status=status.slug).count()

    # Get other available statuses for migration
    other_statuses = OrderStatus.query.filter(
        OrderStatus.id != status_id,
        OrderStatus.is_active == True
    ).order_by(OrderStatus.sort_order).all()

    return jsonify({
        'status_id': status.id,
        'status_name': status.name,
        'orders_count': orders_count,
        'can_delete_directly': orders_count == 0,
        'available_statuses': [
            {'id': s.id, 'slug': s.slug, 'name': s.name, 'badge_color': s.badge_color}
            for s in other_statuses
        ]
    })


@orders_bp.route('/admin/orders/statuses/<int:status_id>/migrate', methods=['POST'])
@login_required
@role_required('admin')
def migrate_status(status_id):
    """Migrate orders from one status to another and delete the old status."""
    try:
        status = OrderStatus.query.get_or_404(status_id)
        data = request.get_json()
        new_status_slug = data.get('new_status')

        if not new_status_slug:
            return jsonify({
                'success': False,
                'message': 'Nie wybrano statusu zastępczego'
            }), 400

        # Verify new status exists
        new_status = OrderStatus.query.filter_by(slug=new_status_slug).first()
        if not new_status:
            return jsonify({
                'success': False,
                'message': 'Wybrany status zastępczy nie istnieje'
            }), 400

        # Migrate all orders to new status
        orders_updated = Order.query.filter_by(status=status.slug).update(
            {'status': new_status_slug},
            synchronize_session=False
        )

        # Delete old status
        db.session.delete(status)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Przeniesiono {orders_updated} zamówień na status "{new_status.name}" i usunięto status "{status.name}"'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas migracji: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/statuses/<int:status_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_status(status_id):
    """Delete order status (only if not used)."""
    try:
        status = OrderStatus.query.get_or_404(status_id)

        # Check if status is used in any orders
        orders_count = Order.query.filter_by(status=status.slug).count()
        if orders_count > 0:
            return jsonify({
                'success': False,
                'requires_migration': True,
                'orders_count': orders_count,
                'message': f'Status jest używany w {orders_count} zamówieniach. Wybierz status zastępczy.'
            }), 400

        db.session.delete(status)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Status "{status.name}" został usunięty'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas usuwania statusu: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/statuses/reorder', methods=['POST'])
@login_required
@role_required('admin')
def reorder_statuses():
    """Update sort_order for statuses based on drag & drop."""
    try:
        data = request.get_json()
        statuses = data.get('statuses', [])

        if not statuses:
            return jsonify({
                'success': False,
                'message': 'Brak danych do aktualizacji'
            }), 400

        # Update sort_order for each status
        for status_data in statuses:
            status_id = status_data.get('id')
            sort_order = status_data.get('sort_order')

            if status_id is None or sort_order is None:
                continue

            status = OrderStatus.query.get(status_id)
            if status:
                status.sort_order = sort_order

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Kolejność statusów została zaktualizowana'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas aktualizacji kolejności: {str(e)}'
        }), 500


# ============================================
# WMS STATUSES API ENDPOINTS
# ============================================

@orders_bp.route('/api/orders/wms-statuses/<int:status_id>')
@login_required
@role_required('admin')
def api_get_wms_status(status_id):
    """Get WMS status data for edit modal."""
    status = WmsStatus.query.get_or_404(status_id)
    return jsonify({
        'id': status.id,
        'name': status.name,
        'slug': status.slug,
        'badge_color': status.badge_color,
        'is_active': status.is_active,
        'is_default': status.is_default,
        'is_picked': status.is_picked
    })


@orders_bp.route('/admin/orders/wms-statuses/create', methods=['POST'])
@login_required
@role_required('admin')
def create_wms_status():
    """Create new WMS status."""
    from modules.orders.utils import generate_slug

    name = request.form.get('name', '').strip()
    badge_color = request.form.get('badge_color', '#6B7280')
    is_active = request.form.get('is_active') == 'on'
    is_default = request.form.get('is_default') == 'on'
    is_picked = request.form.get('is_picked') == 'on'

    # Validation
    errors = {}
    if not name:
        errors['name'] = 'Nazwa statusu jest wymagana'

    # Generate slug from name
    slug = generate_slug(name)

    # Check if slug already exists
    existing = WmsStatus.query.filter_by(slug=slug).first()
    if existing:
        errors['name'] = f'Status WMS o nazwie "{name}" już istnieje'

    if errors:
        return jsonify({'success': False, 'errors': errors}), 400

    # If this is set as default, unset other defaults
    if is_default:
        WmsStatus.query.filter_by(is_default=True).update({'is_default': False})

    # Create new status
    status = WmsStatus(
        name=name,
        slug=slug,
        badge_color=badge_color,
        is_active=is_active,
        is_default=is_default,
        is_picked=is_picked,
        sort_order=WmsStatus.query.count()
    )

    db.session.add(status)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Status WMS "{name}" został utworzony',
        'status': {
            'id': status.id,
            'name': status.name,
            'slug': status.slug,
            'badge_color': status.badge_color,
            'is_active': status.is_active,
            'is_default': status.is_default,
            'is_picked': status.is_picked
        }
    })


@orders_bp.route('/admin/orders/wms-statuses/<int:status_id>/update', methods=['POST'])
@login_required
@role_required('admin')
def update_wms_status(status_id):
    """Update existing WMS status."""
    from modules.orders.utils import generate_slug

    status = WmsStatus.query.get_or_404(status_id)

    name = request.form.get('name', '').strip()
    badge_color = request.form.get('badge_color', '#6B7280')
    is_active = request.form.get('is_active') == 'on'
    is_default = request.form.get('is_default') == 'on'
    is_picked = request.form.get('is_picked') == 'on'

    # Validation
    errors = {}
    if not name:
        errors['name'] = 'Nazwa statusu jest wymagana'

    # Generate new slug if name changed
    new_slug = generate_slug(name)
    if new_slug != status.slug:
        existing = WmsStatus.query.filter_by(slug=new_slug).first()
        if existing:
            errors['name'] = f'Status WMS o nazwie "{name}" już istnieje'

    if errors:
        return jsonify({'success': False, 'errors': errors}), 400

    # If this is set as default, unset other defaults
    if is_default and not status.is_default:
        WmsStatus.query.filter(WmsStatus.id != status_id).filter_by(is_default=True).update({'is_default': False})

    # Update status
    status.name = name
    status.slug = new_slug
    status.badge_color = badge_color
    status.is_active = is_active
    status.is_default = is_default
    status.is_picked = is_picked

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'Status WMS "{name}" został zaktualizowany',
        'status': {
            'id': status.id,
            'name': status.name,
            'slug': status.slug,
            'badge_color': status.badge_color,
            'is_active': status.is_active,
            'is_default': status.is_default,
            'is_picked': status.is_picked
        }
    })


@orders_bp.route('/admin/orders/wms-statuses/<int:status_id>/check-usage')
@login_required
@role_required('admin')
def check_wms_status_usage(status_id):
    """Check if WMS status is used in any order items before deletion."""
    status = WmsStatus.query.get_or_404(status_id)
    items_count = OrderItem.query.filter_by(wms_status=status.slug).count()

    # Get other available WMS statuses for migration
    other_statuses = WmsStatus.query.filter(
        WmsStatus.id != status_id,
        WmsStatus.is_active == True
    ).order_by(WmsStatus.sort_order).all()

    return jsonify({
        'status_id': status.id,
        'status_name': status.name,
        'items_count': items_count,
        'can_delete_directly': items_count == 0,
        'available_statuses': [
            {'id': s.id, 'slug': s.slug, 'name': s.name, 'badge_color': s.badge_color}
            for s in other_statuses
        ]
    })


@orders_bp.route('/admin/orders/wms-statuses/<int:status_id>/migrate', methods=['POST'])
@login_required
@role_required('admin')
def migrate_wms_status(status_id):
    """Migrate order items from one WMS status to another and delete the old status."""
    try:
        status = WmsStatus.query.get_or_404(status_id)
        data = request.get_json()
        new_status_slug = data.get('new_status')

        if not new_status_slug:
            return jsonify({
                'success': False,
                'message': 'Nie wybrano statusu zastępczego'
            }), 400

        # Verify new status exists
        new_status = WmsStatus.query.filter_by(slug=new_status_slug).first()
        if not new_status:
            return jsonify({
                'success': False,
                'message': 'Wybrany status zastępczy nie istnieje'
            }), 400

        # Migrate all order items to new status
        items_updated = OrderItem.query.filter_by(wms_status=status.slug).update(
            {'wms_status': new_status_slug},
            synchronize_session=False
        )

        # Delete old status
        db.session.delete(status)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Przeniesiono {items_updated} pozycji na status "{new_status.name}" i usunięto status "{status.name}"'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas migracji: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/wms-statuses/<int:status_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_wms_status(status_id):
    """Delete WMS status (only if not used)."""
    try:
        status = WmsStatus.query.get_or_404(status_id)

        # Check if status is in use
        items_count = OrderItem.query.filter_by(wms_status=status.slug).count()
        if items_count > 0:
            return jsonify({
                'success': False,
                'requires_migration': True,
                'items_count': items_count,
                'message': f'Status jest używany w {items_count} pozycjach zamówień. Wybierz status zastępczy.'
            }), 400

        db.session.delete(status)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Status WMS "{status.name}" został usunięty'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas usuwania statusu: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/wms-statuses/reorder', methods=['POST'])
@login_required
@role_required('admin')
def reorder_wms_statuses():
    """Update sort_order for WMS statuses based on drag & drop."""
    try:
        data = request.get_json()
        statuses = data.get('statuses', [])

        if not statuses:
            return jsonify({
                'success': False,
                'message': 'Brak danych do aktualizacji'
            }), 400

        for status_data in statuses:
            status_id = status_data.get('id')
            sort_order = status_data.get('sort_order')

            if status_id is None or sort_order is None:
                continue

            status = WmsStatus.query.get(status_id)
            if status:
                status.sort_order = sort_order

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Kolejność statusów WMS została zaktualizowana'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas aktualizacji kolejności: {str(e)}'
        }), 500


# ============================================
# API - Pobieranie produktów do modala
# ============================================

@orders_bp.route('/admin/orders/api/products')
@login_required
@role_required('admin', 'mod')
def api_get_products():
    """API endpoint do pobierania produktów dla modala dodawania"""
    from modules.products.models import Product, Category, ProductSeries, ProductImage

    search = request.args.get('search', '').strip()
    category_id = request.args.get('category_id', type=int)
    series_id = request.args.get('series_id', type=int)

    query = Product.query.filter(Product.is_active == True)

    if search:
        search_term = f'%{search}%'
        query = query.filter(
            db.or_(
                Product.name.ilike(search_term),
                Product.sku.ilike(search_term),
                Product.ean.ilike(search_term)
            )
        )

    if category_id:
        query = query.filter(Product.category_id == category_id)

    if series_id:
        query = query.filter(Product.series_id == series_id)

    products = query.order_by(Product.name).limit(50).all()

    products_data = []
    for product in products:
        primary_image = ProductImage.query.filter_by(
            product_id=product.id,
            is_primary=True
        ).first()

        if not primary_image:
            primary_image = ProductImage.query.filter_by(product_id=product.id).first()

        if primary_image:
            image_url = f'/static/uploads/products/compressed/{primary_image.filename}'
        else:
            image_url = '/static/img/placeholders/product.svg'

        category_name = product.category.name if product.category else None
        series_name = product.series.name if product.series else None

        products_data.append({
            'id': product.id,
            'name': product.name,
            'sku': product.sku,
            'ean': product.ean,
            'sale_price': float(product.sale_price) if product.sale_price else 0,
            'quantity': product.quantity or 0,
            'category_name': category_name,
            'series_name': series_name,
            'image_url': image_url
        })

    return jsonify({
        'success': True,
        'products': products_data
    })


@orders_bp.route('/admin/orders/<int:order_id>/add-products', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_add_products(order_id):
    """Dodaje produkty do istniejącego zamówienia"""
    from modules.products.models import Product

    order = Order.query.get_or_404(order_id)

    try:
        data = request.get_json()
        products_to_add = data.get('products', [])

        if not products_to_add:
            return jsonify({
                'success': False,
                'message': 'Nie wybrano żadnych produktów'
            }), 400

        added_count = 0

        for item in products_to_add:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 1)

            if not product_id or quantity < 1:
                continue

            product = Product.query.get(product_id)
            if not product or not product.is_active:
                continue

            # Sprawdź czy produkt już jest w zamówieniu
            existing_item = OrderItem.query.filter_by(
                order_id=order_id,
                product_id=product_id
            ).first()

            if existing_item:
                # Dodaj do istniejącej pozycji
                existing_item.quantity += quantity
                existing_item.total = existing_item.quantity * existing_item.price
            else:
                # Dodaj nową pozycję
                new_item = OrderItem(
                    order_id=order_id,
                    product_id=product_id,
                    quantity=quantity,
                    price=product.sale_price or 0,
                    total=(product.sale_price or 0) * quantity
                )
                db.session.add(new_item)

            added_count += 1

        # Flush żeby nowe items były widoczne w relacji
        db.session.flush()

        # Odśwież order z bazy (aby items były aktualne)
        db.session.refresh(order)

        # Przelicz sumę zamówienia
        order.recalculate_total()

        db.session.commit()

        # Log aktywności
        log_activity(
            user=current_user,
            action='order_products_added',
            entity_type='order',
            entity_id=order.id,
            new_value={'added_products': added_count, 'order_number': order.order_number}
        )

        return jsonify({
            'success': True,
            'message': f'Dodano {added_count} produkt(ów) do zamówienia',
            'new_total': float(order.total_amount) if order.total_amount else 0
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas dodawania produktów: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/<int:order_id>/items/<int:item_id>', methods=['PUT'])
@login_required
@role_required('admin', 'mod')
def admin_update_item(order_id, item_id):
    """Aktualizuje produkt w zamówieniu (ilość, cena)"""
    order = Order.query.get_or_404(order_id)
    item = OrderItem.query.filter_by(id=item_id, order_id=order_id).first_or_404()

    try:
        data = request.get_json()
        quantity = data.get('quantity')
        price = data.get('price')

        if quantity is None or price is None:
            return jsonify({
                'success': False,
                'message': 'Wymagane pola: quantity, price'
            }), 400

        quantity = int(quantity)
        price = float(price)

        if quantity < 1:
            return jsonify({
                'success': False,
                'message': 'Ilość musi być większa niż 0'
            }), 400

        if price < 0:
            return jsonify({
                'success': False,
                'message': 'Cena nie może być ujemna'
            }), 400

        # Zapisz stare wartości do logu
        old_quantity = item.quantity
        old_price = float(item.price)

        # Aktualizuj item
        item.quantity = quantity
        item.price = price
        item.total = quantity * price

        # Przelicz sumę zamówienia
        db.session.flush()
        db.session.refresh(order)
        order.recalculate_total()

        db.session.commit()

        # Log aktywności
        log_activity(
            user=current_user,
            action='order_item_updated',
            entity_type='order',
            entity_id=order.id,
            old_value={
                'product_name': item.product_name,
                'quantity': old_quantity,
                'price': old_price
            },
            new_value={
                'product_name': item.product_name,
                'quantity': quantity,
                'price': price
            }
        )

        return jsonify({
            'success': True,
            'message': 'Produkt został zaktualizowany',
            'new_total': float(order.total_amount) if order.total_amount else 0,
            'item_total': float(item.total)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas aktualizacji produktu: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/<int:order_id>/items/<int:item_id>', methods=['DELETE'])
@login_required
@role_required('admin', 'mod')
def admin_delete_item(order_id, item_id):
    """Usuwa produkt z zamówienia"""
    order = Order.query.get_or_404(order_id)
    item = OrderItem.query.filter_by(id=item_id, order_id=order_id).first_or_404()

    try:
        # Zapisz dane do logu przed usunięciem
        product_name = item.product_name
        quantity = item.quantity
        price = float(item.price)

        # Usuń item
        db.session.delete(item)

        # Przelicz sumę zamówienia
        db.session.flush()
        db.session.refresh(order)
        order.recalculate_total()

        db.session.commit()

        # Log aktywności
        log_activity(
            user=current_user,
            action='order_item_deleted',
            entity_type='order',
            entity_id=order.id,
            old_value={
                'product_name': product_name,
                'quantity': quantity,
                'price': price
            }
        )

        return jsonify({
            'success': True,
            'message': f'Produkt "{product_name}" został usunięty',
            'new_total': float(order.total_amount) if order.total_amount else 0
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas usuwania produktu: {str(e)}'
        }), 500
