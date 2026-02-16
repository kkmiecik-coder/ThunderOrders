"""
Orders Module - Routes
======================

Routes for orders management (Admin + Client + API).
Includes HTMX endpoints for partial updates.
"""

import json
import os
from flask import render_template, request, redirect, url_for, flash, jsonify, abort, make_response, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, func
from datetime import datetime
from decimal import Decimal

from modules.orders import orders_bp
from modules.orders.models import (
    Order, OrderItem, OrderComment, OrderRefund,
    OrderStatus, OrderType, WmsStatus,
    ShippingRequestStatus, ShippingRequest, ShippingRequestOrder
)
from modules.products.models import Product
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

    # Products filter - find orders containing selected products
    if filter_form.products.data:
        product_ids_str = filter_form.products.data
        try:
            product_ids = [int(pid.strip()) for pid in product_ids_str.split(',') if pid.strip()]
            if product_ids:
                # Subquery: orders that have at least one of these products
                from modules.orders.models import OrderItem
                subquery = db.session.query(OrderItem.order_id).filter(
                    OrderItem.product_id.in_(product_ids)
                ).distinct().subquery()
                query = query.filter(Order.id.in_(subquery))
        except ValueError:
            pass  # Invalid product IDs, skip filter

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

    # Get status counts for sidebar
    status_counts = db.session.query(
        Order.status,
        func.count(Order.id)
    ).group_by(Order.status).all()
    status_counts_dict = {status: count for status, count in status_counts}

    # Get all statuses with their counts
    all_statuses = OrderStatus.query.filter_by(is_active=True).order_by(OrderStatus.sort_order).all()
    statuses_with_counts = []
    total_count = 0
    for status in all_statuses:
        count = status_counts_dict.get(status.slug, 0)
        total_count += count
        statuses_with_counts.append({
            'slug': status.slug,
            'name': status.name,
            'badge_color': status.badge_color,
            'count': count
        })

    return render_template(
        'admin/orders/list.html',
        orders=pagination,
        filter_form=filter_form,
        statuses_with_counts=statuses_with_counts,
        total_orders_count=total_count,
        page_title='Zamówienia'
    )


@orders_bp.route('/api/orders/create-for-client', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def api_create_order_for_client():
    """
    API endpoint to create a new empty order for a client.
    Used by the modal in orders list - creates order and returns order ID for redirect.
    """
    from modules.auth.models import User

    try:
        data = request.get_json()
        client_id = data.get('client_id')

        if not client_id:
            return jsonify({
                'success': False,
                'message': 'Nie podano ID klienta'
            }), 400

        # Validate client exists
        client = User.query.get(client_id)
        if not client or client.role != 'client':
            return jsonify({
                'success': False,
                'message': 'Nie znaleziono klienta'
            }), 404

        # Generate order number (use 'on_hand' type for manual orders)
        order_number = generate_order_number('on_hand')

        # Create empty order
        new_order = Order(
            order_number=order_number,
            user_id=client.id,
            order_type='on_hand',  # Manual orders use on_hand type
            status='nowe',
            total_amount=0
        )
        db.session.add(new_order)
        db.session.commit()

        # Log activity
        log_activity(
            user=current_user,
            action='order_created',
            entity_type='order',
            entity_id=new_order.id,
            new_value={'order_number': order_number, 'client': client.full_name}
        )

        return jsonify({
            'success': True,
            'message': f'Zamówienie {order_number} zostało utworzone',
            'order_id': new_order.id,
            'order_number': order_number,
            'redirect_url': url_for('orders.admin_detail', order_id=new_order.id)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas tworzenia zamówienia: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/create', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def admin_create_order():
    """
    Admin order creation page.
    Creates a new manual order for a selected client.
    DEPRECATED: This page is kept for backwards compatibility.
    New flow uses API endpoint + redirect to order detail page.
    """
    from modules.auth.models import User
    from modules.products.models import Product

    client_id = request.args.get('client_id', type=int)

    # Validate client exists
    client = None
    if client_id:
        client = User.query.get(client_id)
        if not client or client.role != 'client':
            flash('Nie znaleziono klienta', 'error')
            return redirect(url_for('orders.admin_list'))

    if request.method == 'POST':
        # Handle order creation
        try:
            # Get client from form or URL
            form_client_id = request.form.get('client_id', type=int)
            if not client and form_client_id:
                client = User.query.get(form_client_id)

            if not client:
                flash('Wybierz klienta', 'error')
                return redirect(url_for('orders.admin_create_order'))

            # Get products from form
            product_ids = request.form.getlist('product_id[]', type=int)
            quantities = request.form.getlist('quantity[]', type=int)

            if not product_ids or not quantities:
                flash('Dodaj przynajmniej jeden produkt', 'error')
                return redirect(url_for('orders.admin_create_order', client_id=client.id))

            # Generate order number (use 'on_hand' type for manual orders)
            order_number = generate_order_number('on_hand')

            # Create order
            new_order = Order(
                order_number=order_number,
                user_id=client.id,
                order_type='on_hand',  # Manual orders use on_hand type
                status='nowe',
                total_amount=0
            )
            db.session.add(new_order)
            db.session.flush()  # Get order ID

            # Add order items
            total = 0
            for pid, qty in zip(product_ids, quantities):
                if qty <= 0:
                    continue
                product = Product.query.get(pid)
                if not product:
                    continue

                item_total = product.sale_price * qty
                total += item_total

                order_item = OrderItem(
                    order_id=new_order.id,
                    product_id=pid,
                    quantity=qty,
                    price=product.sale_price,
                    total=item_total
                )
                db.session.add(order_item)

            new_order.total_amount = total
            db.session.commit()

            # Log activity
            log_activity(
                user=current_user,
                action='order_created',
                entity_type='order',
                entity_id=new_order.id,
                new_value={'order_number': order_number, 'client': client.full_name}
            )

            flash(f'Zamówienie {order_number} zostało utworzone', 'success')
            return redirect(url_for('orders.admin_detail', order_id=new_order.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Błąd podczas tworzenia zamówienia: {str(e)}', 'error')
            return redirect(url_for('orders.admin_create_order', client_id=client_id))

    # GET request - show form
    # Get all active products for selection
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    return render_template(
        'admin/orders/create.html',
        client=client,
        products=products,
        page_title='Nowe zamówienie'
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
    # Sort items: fulfilled items first, unfulfilled items last
    order_items = sorted(
        OrderItem.query.filter_by(order_id=order_id).all(),
        key=lambda item: (
            2 if item.is_set_fulfilled is False else (1 if item.is_set_fulfilled is True else 0),
            item.id
        )
    )
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

    # Get active payment methods from database
    from modules.payments.models import PaymentMethod
    payment_methods = PaymentMethod.get_active()

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
        payment_methods=payment_methods,
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
        order.updated_at = datetime.now()
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
        order.updated_at = datetime.now()
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
        order.updated_at = datetime.now()
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
        order.updated_at = datetime.now()
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

        order.updated_at = datetime.now()
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
        order.updated_at = datetime.now()
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
        allowed_fields = ['delivery_method', 'shipping_cost', 'payment_method', 'admin_notes']

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
        elif field == 'admin_notes':
            order.admin_notes = value.strip() if value else None

        order.updated_at = datetime.now()
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
# BULK ACTIONS
# ====================

@orders_bp.route('/admin/orders/bulk/status', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def bulk_status_change():
    """
    Bulk status change for multiple orders.
    Returns JSON response with success count.
    """
    try:
        data = request.get_json()
        order_ids = data.get('order_ids', [])
        new_status = data.get('status')

        if not order_ids:
            return jsonify({
                'success': False,
                'message': 'Nie wybrano żadnych zamówień'
            }), 400

        if not new_status:
            return jsonify({
                'success': False,
                'message': 'Nie wybrano statusu'
            }), 400

        # Validate status exists
        status_obj = OrderStatus.query.filter_by(slug=new_status, is_active=True).first()
        if not status_obj:
            return jsonify({
                'success': False,
                'message': 'Nieprawidłowy status'
            }), 400

        # Update orders
        updated_count = 0
        for order_id in order_ids:
            order = Order.query.get(order_id)
            if order:
                old_status = order.status
                if old_status != new_status:
                    order.status = new_status
                    order.updated_at = datetime.now()
                    updated_count += 1

                    # Activity log
                    log_activity(
                        user=current_user,
                        action='order_status_change',
                        entity_type='order',
                        entity_id=order.id,
                        old_value={'status': old_status},
                        new_value={'status': new_status}
                    )

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Zmieniono status {updated_count} zamówień na "{status_obj.name}"',
            'updated_count': updated_count
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas zmiany statusu: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/bulk/delete', methods=['POST'])
@login_required
@role_required('admin')  # Only admin can delete
def bulk_delete():
    """
    Bulk delete multiple orders.
    Returns JSON response with success count.
    """
    try:
        data = request.get_json()
        order_ids = data.get('order_ids', [])

        if not order_ids:
            return jsonify({
                'success': False,
                'message': 'Nie wybrano żadnych zamówień'
            }), 400

        # Delete orders
        deleted_count = 0
        deleted_numbers = []
        for order_id in order_ids:
            order = Order.query.get(order_id)
            if order:
                deleted_numbers.append(order.order_number)
                db.session.delete(order)
                deleted_count += 1

        db.session.commit()

        # Activity log for bulk delete
        log_activity(
            user=current_user,
            action='orders_bulk_deleted',
            entity_type='order',
            entity_id=None,
            old_value={'order_numbers': deleted_numbers, 'count': deleted_count}
        )

        return jsonify({
            'success': True,
            'message': f'Usunięto {deleted_count} zamówień',
            'deleted_count': deleted_count
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas usuwania zamówień: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/export')
@login_required
@role_required('admin', 'mod')
def export_orders():
    """
    Export selected orders to XLSX with nice formatting.
    """
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    # Get order IDs from query param
    ids_param = request.args.get('ids', '')

    if not ids_param:
        flash('Nie wybrano żadnych zamówień do eksportu', 'error')
        return redirect(url_for('orders.admin_list'))

    try:
        order_ids = [int(id.strip()) for id in ids_param.split(',') if id.strip()]
    except ValueError:
        flash('Nieprawidłowe ID zamówień', 'error')
        return redirect(url_for('orders.admin_list'))

    # Get orders
    orders = Order.query.filter(Order.id.in_(order_ids)).order_by(Order.created_at.desc()).all()

    if not orders:
        flash('Nie znaleziono zamówień do eksportu', 'error')
        return redirect(url_for('orders.admin_list'))

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Zamówienia"

    # Styles
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="5A189A", end_color="5A189A", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    data_alignment = Alignment(vertical="center", wrap_text=True)
    currency_alignment = Alignment(horizontal="right", vertical="center")

    thin_border = Border(
        left=Side(style='thin', color='E0E0E0'),
        right=Side(style='thin', color='E0E0E0'),
        top=Side(style='thin', color='E0E0E0'),
        bottom=Side(style='thin', color='E0E0E0')
    )

    alt_row_fill = PatternFill(start_color="F5F5F5", end_color="F5F5F5", fill_type="solid")

    # Header row
    headers = [
        'Numer zamówienia',
        'Data utworzenia',
        'Status',
        'Typ',
        'Klient',
        'Email klienta',
        'Telefon klienta',
        'Produkty',
        'Suma (PLN)',
        'Wysyłka (PLN)',
        'Razem (PLN)',
        'Wpłacono (PLN)',
        'Dostawa',
        'Płatność',
        'Uwagi admina'
    ]

    # Column widths
    column_widths = [18, 18, 15, 12, 20, 25, 15, 50, 12, 12, 12, 12, 15, 15, 30]

    for col_num, (header, width) in enumerate(zip(headers, column_widths), 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border
        ws.column_dimensions[get_column_letter(col_num)].width = width

    # Set header row height
    ws.row_dimensions[1].height = 30

    # Data rows
    for row_num, order in enumerate(orders, 2):
        # Get products string
        products_list = []
        for item in order.items:
            products_list.append(f"{item.product_name} x{item.quantity} ({item.price:.2f} PLN)")
        products_str = "\n".join(products_list)

        # Get customer info
        if order.is_guest_order:
            customer_name = order.guest_name or 'Gość'
            customer_email = order.guest_email or ''
            customer_phone = order.guest_phone or ''
        elif order.user:
            customer_name = order.user.full_name
            customer_email = order.user.email
            customer_phone = order.user.phone or ''
        else:
            customer_name = 'Nieznany'
            customer_email = ''
            customer_phone = ''

        # Get type display name
        type_name = order.type_rel.name if order.type_rel else (order.order_type or '')

        # Get delivery method display
        delivery_display = order.delivery_method_display if hasattr(order, 'delivery_method_display') and order.delivery_method else (order.delivery_method or '')

        row_data = [
            order.order_number,
            order.created_at.strftime('%Y-%m-%d %H:%M'),
            order.status_display_name,
            type_name,
            customer_name,
            customer_email,
            customer_phone,
            products_str,
            float(order.total_amount) if order.total_amount else 0.00,
            float(order.shipping_cost) if order.shipping_cost else 0.00,
            float(order.grand_total) if order.grand_total else 0.00,
            float(order.paid_amount) if order.paid_amount else 0.00,
            delivery_display,
            order.payment_method or '',
            order.admin_notes or ''
        ]

        for col_num, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_num, column=col_num, value=value)
            cell.border = thin_border

            # Apply currency format to money columns
            if col_num in [9, 10, 11, 12]:
                cell.number_format = '#,##0.00 "PLN"'
                cell.alignment = currency_alignment
            else:
                cell.alignment = data_alignment

            # Alternate row colors
            if row_num % 2 == 0:
                cell.fill = alt_row_fill

        # Adjust row height for products column
        if products_str:
            line_count = len(products_str.split('\n'))
            ws.row_dimensions[row_num].height = max(20, min(line_count * 15, 100))

    # Freeze header row
    ws.freeze_panes = 'A2'

    # Create response
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = f'attachment; filename=zamowienia_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

    return response


@orders_bp.route('/api/orders/bulk/info', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def bulk_orders_info():
    """
    Get info about selected orders for bulk actions modal.
    Returns order numbers and basic info.
    """
    try:
        data = request.get_json()
        order_ids = data.get('order_ids', [])

        if not order_ids:
            return jsonify({
                'success': False,
                'message': 'Nie wybrano żadnych zamówień'
            }), 400

        orders = Order.query.filter(Order.id.in_(order_ids)).all()

        orders_info = []
        for order in orders:
            customer_name = order.guest_name if order.is_guest_order else (order.user.full_name if order.user else 'Nieznany')
            orders_info.append({
                'id': order.id,
                'order_number': order.order_number,
                'customer_name': customer_name,
                'status': order.status_display_name,
                'status_color': order.status_badge_color,
                'total': float(order.total_amount) if order.total_amount else 0
            })

        return jsonify({
            'success': True,
            'orders': orders_info,
            'count': len(orders_info)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


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
    statuses_filter = request.args.get('statuses', '').strip()  # comma-separated list of statuses
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    search_query = request.args.get('search', '').strip()
    payment_status_filter = request.args.get('payment_status', '').strip()
    # Base query (only user's orders) with eager loading
    query = Order.query.filter_by(user_id=current_user.id).options(
        db.joinedload(Order.items).joinedload(OrderItem.product)
    )

    # Apply filters
    if statuses_filter:
        # Multiple statuses (comma-separated)
        status_list = [s.strip() for s in statuses_filter.split(',') if s.strip()]
        if status_list:
            query = query.filter(Order.status.in_(status_list))
    elif status_filter:
        query = query.filter(Order.status == status_filter)

    if date_from:
        query = query.filter(Order.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))

    if date_to:
        from datetime import timedelta
        end_date = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
        query = query.filter(Order.created_at < end_date)

    # Search filter (by order number)
    if search_query:
        query = query.filter(Order.order_number.ilike(f'%{search_query}%'))

    # Payment status filter
    if payment_status_filter:
        if payment_status_filter == 'paid':
            # Opłacone: paid_amount >= total_amount
            query = query.filter(Order.paid_amount >= Order.total_amount)
        elif payment_status_filter == 'unpaid':
            # Nieopłacone: paid_amount = 0 lub NULL
            query = query.filter(db.or_(Order.paid_amount == 0, Order.paid_amount.is_(None)))
        elif payment_status_filter == 'partial':
            # Częściowo opłacone: 0 < paid_amount < total_amount
            query = query.filter(
                Order.paid_amount > 0,
                Order.paid_amount < Order.total_amount
            )

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

    # Order history - WSZYSTKIE activity logs dla zamówienia
    from modules.admin.models import ActivityLog
    import json

    # Mapowanie akcji na polskie opisy i ikony
    action_config = {
        'order_created': {'label': 'Zamówienie utworzone', 'icon': '📦'},
        'order_status_change': {'label': 'Zmiana statusu', 'icon': '🔄'},
        'order_status_auto_updated': {'label': 'Automatyczna zmiana statusu', 'icon': '⚡'},
        'order_updated': {'label': 'Zaktualizowano zamówienie', 'icon': '✏️'},
        'order_item_added': {'label': 'Dodano produkt', 'icon': '➕'},
        'order_item_added_custom': {'label': 'Dodano produkt niestandardowy', 'icon': '➕'},
        'order_item_removed': {'label': 'Usunięto produkt', 'icon': '🗑️'},
        'order_item_deleted': {'label': 'Usunięto produkt', 'icon': '🗑️'},
        'order_item_updated': {'label': 'Zaktualizowano produkt', 'icon': '✏️'},
        'order_products_added': {'label': 'Dodano produkty', 'icon': '➕'},
        'order_field_updated': {'label': 'Zaktualizowano dane zamówienia', 'icon': '✏️'},
        'order_payment_updated': {'label': 'Zaktualizowano płatność', 'icon': '💳'},
        'tracking_number_added': {'label': 'Dodano numer śledzenia', 'icon': '🚚'},
        'tracking_number_updated': {'label': 'Zaktualizowano numer śledzenia', 'icon': '🚚'},
        'shipping_requested': {'label': 'Utworzono zlecenie wysyłki', 'icon': '📬'},
        'shipping_cost_updated': {'label': 'Zaktualizowano koszt wysyłki', 'icon': '💰'},
        'comment_added': {'label': 'Dodano komentarz', 'icon': '💬'},
        'order_cancelled': {'label': 'Anulowano zamówienie', 'icon': '🚫'},
        'order_completed': {'label': 'Zamówienie zakończone', 'icon': '🎉'},
        'refund_issued': {'label': 'Wystawiono zwrot', 'icon': '💸'}
    }

    order_history = []
    activity_logs = ActivityLog.query.filter_by(
        entity_type='order',
        entity_id=order.id
    ).order_by(ActivityLog.created_at.desc()).all()

    for log in activity_logs:
        # Pobierz konfigurację akcji
        config = action_config.get(log.action, {'label': log.action, 'icon': '📝'})

        # Podstawowe dane zdarzenia
        history_item = {
            'created_at': log.created_at,
            'user_name': log.user.full_name if log.user else 'System',
            'action': log.action,
            'action_label': config['label'],
            'action_icon': config['icon']
        }

        # Specjalna obsługa zmian statusu (z kolorowym badge)
        if log.action == 'order_status_change':
            new_value_data = json.loads(log.new_value) if log.new_value else {}
            status_slug = new_value_data.get('status')
            status_obj = OrderStatus.query.filter_by(slug=status_slug).first()

            history_item['is_status_change'] = True
            history_item['status_name'] = status_obj.name if status_obj else status_slug
            history_item['status_color'] = status_obj.badge_color if status_obj else '#6B7280'
        else:
            history_item['is_status_change'] = False

        order_history.append(history_item)

    return render_template(
        'client/orders/detail.html',
        order=order,
        order_items=order_items,
        timeline=timeline,
        order_history=order_history,  # Zmieniono z status_history na order_history
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
    Orders settings page - manage statuses, WMS statuses, payment methods, and exclusive closure settings.
    Only accessible to admins.
    """
    from modules.payments.models import PaymentMethod
    from modules.auth.models import Settings

    # Load all order statuses
    statuses = OrderStatus.query.order_by(OrderStatus.sort_order).all()

    # Load all WMS statuses
    wms_statuses = WmsStatus.query.order_by(WmsStatus.sort_order).all()

    # Load all payment methods
    payment_methods = PaymentMethod.query.order_by(PaymentMethod.sort_order, PaymentMethod.name).all()

    # Load exclusive closure settings
    def get_setting_value(key, default):
        setting = Settings.query.filter_by(key=key).first()
        return setting.value if setting else default

    exclusive_closure_settings = {
        'fully_fulfilled': get_setting_value('exclusive_closure_status_fully_fulfilled', 'oczekujace'),
        'partially_fulfilled': get_setting_value('exclusive_closure_status_partially_fulfilled', 'oczekujace'),
        'not_fulfilled': get_setting_value('exclusive_closure_status_not_fulfilled', 'anulowane')
    }

    # Load shipping request statuses
    shipping_request_statuses = ShippingRequestStatus.query.order_by(ShippingRequestStatus.sort_order).all()

    # Load shipping request allowed statuses
    shipping_request_allowed_json = get_setting_value('shipping_request_allowed_statuses', '["dostarczone_gom"]')
    try:
        shipping_request_allowed_statuses = json.loads(shipping_request_allowed_json) if shipping_request_allowed_json else []
    except (json.JSONDecodeError, TypeError):
        shipping_request_allowed_statuses = []

    # Load shipping request default status
    shipping_request_default_status = get_setting_value('shipping_request_default_status', '')

    return render_template(
        'admin/orders/settings.html',
        statuses=statuses,
        wms_statuses=wms_statuses,
        payment_methods=payment_methods,
        exclusive_closure_settings=exclusive_closure_settings,
        shipping_request_statuses=shipping_request_statuses,
        shipping_request_allowed_statuses=shipping_request_allowed_statuses,
        shipping_request_default_status=shipping_request_default_status,
        page_title='Ustawienia zamówień'
    )


@orders_bp.route('/admin/orders/settings/exclusive-closure', methods=['POST'])
@login_required
@role_required('admin')
def update_exclusive_closure_settings():
    """
    Update exclusive closure settings - configure automatic status changes after exclusive page closure.
    Only accessible to admins.
    """
    from modules.auth.models import Settings

    try:
        # Get form data
        status_fully = request.form.get('exclusive_closure_status_fully_fulfilled', '').strip()
        status_partially = request.form.get('exclusive_closure_status_partially_fulfilled', '').strip()
        status_not = request.form.get('exclusive_closure_status_not_fulfilled', '').strip()

        # Validate required fields
        if not status_fully or not status_partially or not status_not:
            flash('Wszystkie pola są wymagane', 'error')
            return redirect(url_for('orders.settings'))

        # Validate that statuses exist
        valid_statuses = [s.slug for s in OrderStatus.query.filter_by(is_active=True).all()]

        if status_fully not in valid_statuses:
            flash(f'Status "{status_fully}" nie istnieje lub jest nieaktywny', 'error')
            return redirect(url_for('orders.settings'))

        if status_partially not in valid_statuses:
            flash(f'Status "{status_partially}" nie istnieje lub jest nieaktywny', 'error')
            return redirect(url_for('orders.settings'))

        if status_not not in valid_statuses:
            flash(f'Status "{status_not}" nie istnieje lub jest nieaktywny', 'error')
            return redirect(url_for('orders.settings'))

        # Update or create settings
        def update_or_create_setting(key, value):
            setting = Settings.query.filter_by(key=key).first()
            if setting:
                setting.value = value
                setting.updated_at = datetime.now()
            else:
                # Create new setting if it doesn't exist
                setting = Settings(
                    key=key,
                    value=value,
                    type='string',
                    description=f'Auto-generated setting for {key}'
                )
                db.session.add(setting)

        update_or_create_setting('exclusive_closure_status_fully_fulfilled', status_fully)
        update_or_create_setting('exclusive_closure_status_partially_fulfilled', status_partially)
        update_or_create_setting('exclusive_closure_status_not_fulfilled', status_not)

        db.session.commit()

        # Activity log
        from utils.activity_logger import log_activity
        log_activity(
            user=current_user,
            action='settings_updated',
            entity_type='settings',
            entity_id=None,
            old_value=None,
            new_value={
                'fully_fulfilled': status_fully,
                'partially_fulfilled': status_partially,
                'not_fulfilled': status_not
            }
        )

        flash('Ustawienia zostały zapisane', 'success')
        return redirect(url_for('orders.settings') + '#tab-exclusive-closure')

    except Exception as e:
        db.session.rollback()
        flash(f'Błąd podczas zapisywania ustawień: {str(e)}', 'error')
        return redirect(url_for('orders.settings'))


# ============================================
# SHIPPING REQUEST SETTINGS
# ============================================

@orders_bp.route('/admin/orders/update-shipping-request-allowed-statuses', methods=['POST'])
@login_required
@role_required('admin')
def update_shipping_request_allowed_statuses():
    """
    Update list of order statuses that qualify for shipping request.
    Only accessible to admins.
    """
    from modules.auth.models import Settings

    try:
        # Get selected statuses (list of slugs)
        allowed_statuses = request.form.getlist('allowed_statuses')

        # Validate that all selected statuses exist
        valid_statuses = [s.slug for s in OrderStatus.query.filter_by(is_active=True).all()]

        # Filter only valid statuses
        validated_statuses = [s for s in allowed_statuses if s in valid_statuses]

        # Update or create setting
        setting = Settings.query.filter_by(key='shipping_request_allowed_statuses').first()
        if setting:
            setting.value = json.dumps(validated_statuses)
            setting.type = 'json'
            setting.updated_at = datetime.now()
        else:
            setting = Settings(
                key='shipping_request_allowed_statuses',
                value=json.dumps(validated_statuses),
                type='json',
                description='Lista statusów zamówień kwalifikujących się do zlecenia wysyłki'
            )
            db.session.add(setting)

        db.session.commit()

        # Activity log
        log_activity(
            user=current_user,
            action='settings_updated',
            entity_type='settings',
            entity_id=None,
            old_value=None,
            new_value={'shipping_request_allowed_statuses': validated_statuses}
        )

        flash('Ustawienia zostały zapisane', 'success')
        return redirect(url_for('orders.settings') + '#tab-shipping-requests')

    except Exception as e:
        db.session.rollback()
        flash(f'Błąd podczas zapisywania ustawień: {str(e)}', 'error')
        return redirect(url_for('orders.settings') + '#tab-shipping-requests')


@orders_bp.route('/admin/orders/settings/shipping-request-default-status', methods=['POST'])
@login_required
@role_required('admin')
def update_shipping_request_default_status():
    """
    Update default status for new shipping requests.
    Only accessible to admins.
    """
    from modules.auth.models import Settings

    try:
        # Get selected status
        default_status = request.form.get('default_status', '').strip()

        # Validate that status exists
        if default_status:
            valid_statuses = [s.slug for s in ShippingRequestStatus.query.filter_by(is_active=True).all()]
            if default_status not in valid_statuses:
                flash('Wybrany status nie istnieje lub jest nieaktywny', 'error')
                return redirect(url_for('orders.settings') + '#tab-shipping-requests')

        # Update or create setting
        setting = Settings.query.filter_by(key='shipping_request_default_status').first()
        if setting:
            setting.value = default_status
            setting.updated_at = datetime.now()
        else:
            setting = Settings(
                key='shipping_request_default_status',
                value=default_status,
                type='string',
                description='Domyślny status dla nowych zleceń wysyłki'
            )
            db.session.add(setting)

        db.session.commit()

        # Activity log
        log_activity(
            user=current_user,
            action='settings_updated',
            entity_type='settings',
            entity_id=None,
            old_value=None,
            new_value={'shipping_request_default_status': default_status}
        )

        flash('Ustawienia zostały zapisane', 'success')
        return redirect(url_for('orders.settings') + '#tab-shipping-requests')

    except Exception as e:
        db.session.rollback()
        flash(f'Błąd podczas zapisywania ustawień: {str(e)}', 'error')
        return redirect(url_for('orders.settings') + '#tab-shipping-requests')


@orders_bp.route('/admin/orders/shipping-request-statuses/<int:status_id>', methods=['GET'])
@login_required
@role_required('admin')
def get_shipping_request_status(status_id):
    """Get shipping request status data for edit modal."""
    status = ShippingRequestStatus.query.get_or_404(status_id)
    return jsonify({
        'id': status.id,
        'name': status.name,
        'slug': status.slug,
        'badge_color': status.badge_color,
        'is_initial': status.is_initial,
        'is_active': status.is_active
    })


@orders_bp.route('/admin/orders/shipping-request-statuses/create', methods=['POST'])
@login_required
@role_required('admin')
def create_shipping_request_status():
    """Create new shipping request status."""
    from modules.orders.utils import generate_slug

    try:
        data = request.get_json()
        name = data.get('name', '').strip()

        if not name:
            return jsonify({'success': False, 'error': 'Nazwa jest wymagana'}), 400

        # Generate slug from name
        slug = generate_slug(name)

        # Check if slug already exists
        existing = ShippingRequestStatus.query.filter_by(slug=slug).first()
        if existing:
            return jsonify({'success': False, 'error': 'Status o takiej nazwie już istnieje'}), 400

        # Get max sort_order
        max_order = db.session.query(func.max(ShippingRequestStatus.sort_order)).scalar() or 0

        # Create new status
        status = ShippingRequestStatus(
            slug=slug,
            name=name,
            badge_color=data.get('badge_color', '#6B7280'),
            is_initial=data.get('is_initial', False),
            is_active=data.get('is_active', True),
            sort_order=max_order + 1
        )
        db.session.add(status)
        db.session.commit()

        # Activity log
        log_activity(
            user=current_user,
            action='shipping_request_status_created',
            entity_type='shipping_request_status',
            entity_id=status.id,
            old_value=None,
            new_value={'name': name, 'slug': slug}
        )

        return jsonify({'success': True, 'id': status.id})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@orders_bp.route('/admin/orders/shipping-request-statuses/<int:status_id>', methods=['PUT'])
@login_required
@role_required('admin')
def update_shipping_request_status(status_id):
    """Update shipping request status."""
    status = ShippingRequestStatus.query.get_or_404(status_id)

    try:
        data = request.get_json()
        name = data.get('name', '').strip()

        if not name:
            return jsonify({'success': False, 'error': 'Nazwa jest wymagana'}), 400

        old_values = {
            'name': status.name,
            'badge_color': status.badge_color,
            'is_initial': status.is_initial,
            'is_active': status.is_active
        }

        status.name = name
        status.badge_color = data.get('badge_color', status.badge_color)
        status.is_initial = data.get('is_initial', status.is_initial)
        status.is_active = data.get('is_active', status.is_active)
        status.updated_at = datetime.now()

        db.session.commit()

        # Activity log
        log_activity(
            user=current_user,
            action='shipping_request_status_updated',
            entity_type='shipping_request_status',
            entity_id=status.id,
            old_value=old_values,
            new_value={
                'name': status.name,
                'badge_color': status.badge_color,
                'is_initial': status.is_initial,
                'is_active': status.is_active
            }
        )

        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@orders_bp.route('/admin/orders/shipping-request-statuses/<int:status_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_shipping_request_status(status_id):
    """Delete shipping request status."""
    status = ShippingRequestStatus.query.get_or_404(status_id)

    try:
        # Check if status is in use
        in_use_count = ShippingRequest.query.filter_by(status=status.slug).count()
        if in_use_count > 0:
            return jsonify({
                'success': False,
                'error': f'Nie można usunąć statusu - jest używany w {in_use_count} zleceniach'
            }), 400

        status_name = status.name

        db.session.delete(status)
        db.session.commit()

        # Activity log
        log_activity(
            user=current_user,
            action='shipping_request_status_deleted',
            entity_type='shipping_request_status',
            entity_id=status_id,
            old_value={'name': status_name},
            new_value=None
        )

        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


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


@orders_bp.route('/admin/orders/<int:order_id>/add-custom-product', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_add_custom_product(order_id):
    """
    Dodaje ręcznie wpisany produkt do zamówienia (bez product_id).
    Używane dla pełnych setów i innych custom produktów.
    """
    from decimal import Decimal

    order = Order.query.get_or_404(order_id)
    data = request.get_json()

    custom_name = data.get('custom_name', '').strip()
    custom_sku = data.get('custom_sku', '').strip() or None
    quantity = data.get('quantity', 0)
    price = data.get('price', 0)

    # Walidacja
    if not custom_name:
        return jsonify({'success': False, 'message': 'Podaj nazwę produktu'}), 400

    if not isinstance(quantity, int) or quantity <= 0:
        try:
            quantity = int(quantity)
            if quantity <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Ilość musi być liczbą całkowitą większą od 0'}), 400

    try:
        price = Decimal(str(price))
        if price < 0:
            raise ValueError()
    except (ValueError, TypeError, InvalidOperation):
        return jsonify({'success': False, 'message': 'Nieprawidłowa cena'}), 400

    item_total = price * quantity

    try:
        # Utwórz OrderItem jako custom produkt (bez product_id)
        order_item = OrderItem(
            order_id=order.id,
            product_id=None,  # Brak linku do produktu
            custom_name=custom_name,
            custom_sku=custom_sku,
            is_custom=True,
            quantity=quantity,
            price=price,
            total=item_total,
            picked=False
        )

        db.session.add(order_item)

        # Przelicz sumę zamówienia
        db.session.flush()
        db.session.refresh(order)
        order.recalculate_total()

        db.session.commit()

        # Log aktywności
        log_activity(
            user=current_user,
            action='order_item_added_custom',
            entity_type='order',
            entity_id=order.id,
            new_value={
                'custom_name': custom_name,
                'custom_sku': custom_sku,
                'quantity': quantity,
                'price': float(price),
                'total': float(item_total)
            }
        )

        return jsonify({
            'success': True,
            'message': f'Produkt "{custom_name}" został dodany',
            'item_id': order_item.id,
            'new_total': float(order.total_amount) if order.total_amount else 0
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd podczas dodawania produktu: {str(e)}'
        }), 500


# ============================================
# GUEST ORDER TRACKING
# ============================================

@orders_bp.route('/order/track/<token>')
def guest_track(token):
    """
    Publiczny podgląd zamówienia dla gościa (bez logowania).
    Token jest unikalny i nigdy nie wygasa.
    """
    order = Order.get_by_guest_token(token)

    if not order:
        abort(404)

    return render_template('orders/guest_track.html', order=order)


# ============================================
# PAYMENT METHODS CRUD (Settings Tab)
# ============================================

@orders_bp.route('/admin/orders/payment-methods/create', methods=['POST'])
@login_required
@role_required('admin')
def create_payment_method():
    """Create new payment method."""
    from modules.payments.models import PaymentMethod

    name = request.form.get('name', '').strip()
    details = request.form.get('details', '').strip()
    is_active = request.form.get('is_active') == 'on'

    if not name or not details:
        return jsonify({'success': False, 'error': 'Nazwa i szczegóły są wymagane'}), 400

    try:
        # Auto-assign sort_order (max + 1)
        max_sort_order = db.session.query(db.func.max(PaymentMethod.sort_order)).scalar() or -1
        sort_order = max_sort_order + 1

        method = PaymentMethod(
            name=name,
            details=details,
            is_active=is_active,
            sort_order=sort_order
        )

        db.session.add(method)
        db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@orders_bp.route('/admin/orders/payment-methods/<int:id>/edit', methods=['POST'])
@login_required
@role_required('admin')
def edit_payment_method(id):
    """Edit payment method."""
    from modules.payments.models import PaymentMethod

    method = PaymentMethod.query.get_or_404(id)

    try:
        method.name = request.form.get('name', '').strip()
        method.details = request.form.get('details', '').strip()
        method.is_active = request.form.get('is_active') == 'on'
        # sort_order is managed by drag & drop, don't change it here

        db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@orders_bp.route('/admin/orders/payment-methods/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_payment_method(id):
    """Delete payment method."""
    from modules.payments.models import PaymentMethod

    method = PaymentMethod.query.get_or_404(id)

    try:
        db.session.delete(method)
        db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@orders_bp.route('/admin/orders/payment-methods/list', methods=['GET'])
@login_required
@role_required('admin')
def get_payment_methods_list():
    """Get payment methods list HTML (for AJAX refresh)."""
    from modules.payments.models import PaymentMethod
    from flask import render_template_string

    payment_methods = PaymentMethod.query.order_by(PaymentMethod.sort_order, PaymentMethod.name).all()

    template = '''<!-- Data rows -->
{% if payment_methods %}
    {% for method in payment_methods %}
        <div class="payment-method-list-item" data-method-id="{{ method.id }}" draggable="true">
            <div class="payment-method-col-name">
                <div class="drag-handle">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M2 3h12v2H2V3zm0 4h12v2H2V7zm0 4h12v2H2v-2z"/>
                    </svg>
                </div>
                <strong>{{ method.name }}</strong>
            </div>
            <div class="payment-method-col-details">
                <pre class="payment-details-preview">{{ method.details[:100] }}{% if method.details|length > 100 %}...{% endif %}</pre>
            </div>
            <div class="payment-method-col-status">
                {% if method.is_active %}
                    <span class="badge badge-success">Aktywny</span>
                {% else %}
                    <span class="badge badge-secondary">Nieaktywny</span>
                {% endif %}
            </div>
            <div class="payment-method-col-actions">
                <button type="button" class="action-link" onclick='openEditPaymentMethodModal({{ method.id }}, "{{ method.name }}", {{ method.details|tojson }}, {{ method.is_active|tojson }})'>Edytuj</button>
                <button type="button" class="action-link delete-link" onclick="deletePaymentMethod({{ method.id }}, '{{ method.name }}')">Usuń</button>
            </div>
        </div>
    {% endfor %}
{% else %}
    <div class="empty-state">
        <p>Brak metod płatności. Dodaj pierwszą metodę.</p>
    </div>
{% endif %}'''

    return render_template_string(template, payment_methods=payment_methods)


@orders_bp.route('/admin/orders/payment-methods/reorder', methods=['POST'])
@login_required
@role_required('admin')
def reorder_payment_methods():
    """Reorder payment methods via drag & drop."""
    from modules.payments.models import PaymentMethod

    data = request.get_json()
    order = data.get('order', [])

    try:
        for item in order:
            method = PaymentMethod.query.get(item['id'])
            if method:
                method.sort_order = item['sort_order']

        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@orders_bp.route('/admin/orders/shipping-requests/<int:shipping_request_id>', methods=['GET'])
@login_required
@role_required('admin', 'mod')
def admin_get_shipping_request(shipping_request_id):
    """Get shipping request details as JSON."""
    from modules.orders.models import ShippingRequest

    sr = ShippingRequest.query.get_or_404(shipping_request_id)

    # Build orders list with shipping costs
    orders_data = []
    for ro in sr.request_orders:
        if ro.order:
            orders_data.append({
                'id': ro.order.id,
                'order_number': ro.order.order_number,
                'total_amount': float(ro.order.total_amount or 0),
                'shipping_cost': float(ro.order.shipping_cost or 0)
            })

    return jsonify({
        'id': sr.id,
        'request_number': sr.request_number,
        'status': sr.status,
        'status_display_name': sr.status_display_name,
        'courier': sr.courier,
        'tracking_number': sr.tracking_number,
        'parcel_size': sr.parcel_size,
        'calculated_shipping_cost': float(sr.calculated_shipping_cost or 0),
        'admin_notes': sr.admin_notes,
        'address_type': sr.address_type,
        'shipping_name': sr.shipping_name,
        'shipping_address': sr.shipping_address,
        'shipping_postal_code': sr.shipping_postal_code,
        'shipping_city': sr.shipping_city,
        'shipping_voivodeship': sr.shipping_voivodeship,
        'pickup_courier': sr.pickup_courier,
        'pickup_point_id': sr.pickup_point_id,
        'pickup_address': sr.pickup_address,
        'pickup_postal_code': sr.pickup_postal_code,
        'pickup_city': sr.pickup_city,
        'orders': orders_data,
        'created_at': sr.created_at.isoformat() if sr.created_at else None
    })


@orders_bp.route('/admin/orders/shipping-requests/<int:shipping_request_id>', methods=['PUT'])
@login_required
@role_required('admin', 'mod')
def admin_update_shipping_request(shipping_request_id):
    """Update shipping request."""
    from modules.orders.models import ShippingRequest

    sr = ShippingRequest.query.get_or_404(shipping_request_id)
    data = request.get_json() or {}

    # Update basic fields
    if 'status' in data:
        sr.status = data['status']
    if 'courier' in data:
        sr.courier = data['courier'] or None
    if 'tracking_number' in data:
        sr.tracking_number = data['tracking_number'] or None
    if 'parcel_size' in data:
        sr.parcel_size = data['parcel_size'] or None
    if 'admin_notes' in data:
        sr.admin_notes = data['admin_notes'] or None

    # Update order shipping costs
    if 'order_costs' in data:
        for cost_data in data['order_costs']:
            order_id = cost_data.get('order_id')
            shipping_cost = cost_data.get('shipping_cost', 0)

            # Find the order and update its shipping cost
            order = Order.query.get(order_id)
            if order:
                order.shipping_cost = shipping_cost if shipping_cost > 0 else None

    db.session.commit()

    # Activity log
    import json
    log_activity(
        user=current_user,
        action='shipping_request_updated',
        entity_type='shipping_request',
        entity_id=sr.id,
        new_value=json.dumps({
            'request_number': sr.request_number,
            'status': sr.status,
            'tracking_number': sr.tracking_number
        })
    )

    return jsonify({
        'success': True,
        'message': f'Zlecenie {sr.request_number} zostało zaktualizowane'
    })


@orders_bp.route('/admin/orders/shipping-requests/<int:shipping_request_id>', methods=['DELETE'])
@login_required
@role_required('admin', 'mod')
def admin_delete_shipping_request(shipping_request_id):
    """Cancel/delete shipping request."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder

    sr = ShippingRequest.query.get_or_404(shipping_request_id)
    request_number = sr.request_number

    # Remove all order associations (orders go back to pool)
    ShippingRequestOrder.query.filter_by(shipping_request_id=sr.id).delete()

    # Delete the shipping request
    db.session.delete(sr)
    db.session.commit()

    # Activity log
    import json
    log_activity(
        user=current_user,
        action='shipping_request_cancelled',
        entity_type='shipping_request',
        entity_id=shipping_request_id,
        new_value=json.dumps({
            'request_number': request_number
        })
    )

    return jsonify({
        'success': True,
        'message': f'Zlecenie {request_number} zostało anulowane'
    })


@orders_bp.route('/admin/orders/shipping-requests/bulk-cancel', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_bulk_cancel_shipping_requests():
    """Bulk cancel/delete multiple shipping requests."""
    data = request.get_json()
    ids = data.get('ids', [])

    if not ids:
        return jsonify({'error': 'Nie wybrano żadnych zleceń'}), 400

    deleted_numbers = []

    for sr_id in ids:
        sr = ShippingRequest.query.get(sr_id)
        if sr:
            deleted_numbers.append(sr.request_number)
            # Remove all order associations (orders go back to pool)
            ShippingRequestOrder.query.filter_by(shipping_request_id=sr.id).delete()
            # Delete the shipping request
            db.session.delete(sr)

    db.session.commit()

    # Activity log
    log_activity(
        user=current_user,
        action='shipping_requests_bulk_cancelled',
        entity_type='shipping_request',
        new_value=json.dumps({
            'request_numbers': deleted_numbers,
            'count': len(deleted_numbers)
        })
    )

    return jsonify({
        'success': True,
        'message': f'Usunięto {len(deleted_numbers)} zleceń'
    })


@orders_bp.route('/admin/orders/shipping-requests/bulk-merge', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_bulk_merge_shipping_requests():
    """
    Merge multiple shipping requests into one.
    Uses the oldest request (lowest ID) as the target.
    All orders from other requests are moved to the target.
    Other requests are deleted.
    """
    data = request.get_json()
    ids = data.get('ids', [])

    if len(ids) < 2:
        return jsonify({'error': 'Wybierz co najmniej 2 zlecenia do scalenia'}), 400

    # Get all shipping requests and sort by ID (oldest first)
    shipping_requests = ShippingRequest.query.filter(ShippingRequest.id.in_(ids)).order_by(ShippingRequest.id.asc()).all()

    if len(shipping_requests) < 2:
        return jsonify({'error': 'Nie znaleziono wybranych zleceń'}), 404

    # Verify all requests belong to the same user
    user_ids = set(sr.user_id for sr in shipping_requests)
    if len(user_ids) > 1:
        return jsonify({'error': 'Zaznaczone zlecenia pochodzą od różnych klientów'}), 400

    # Target is the oldest request (first in sorted list)
    target_request = shipping_requests[0]
    requests_to_delete = shipping_requests[1:]
    merged_numbers = [sr.request_number for sr in requests_to_delete]

    # Move all orders from other requests to the target
    for sr in requests_to_delete:
        # Update all ShippingRequestOrder associations
        ShippingRequestOrder.query.filter_by(shipping_request_id=sr.id).update({
            'shipping_request_id': target_request.id
        })

    # Delete the now-empty requests
    for sr in requests_to_delete:
        db.session.delete(sr)

    db.session.commit()

    # Activity log
    log_activity(
        user=current_user,
        action='shipping_requests_merged',
        entity_type='shipping_request',
        entity_id=target_request.id,
        new_value=json.dumps({
            'target_request_number': target_request.request_number,
            'merged_request_numbers': merged_numbers,
            'count': len(merged_numbers) + 1
        })
    )

    return jsonify({
        'success': True,
        'message': f'Scalono {len(shipping_requests)} zleceń w {target_request.request_number}'
    })


@orders_bp.route('/admin/orders/shipping-requests/bulk-status', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_bulk_status_shipping_requests():
    """Bulk change status for multiple shipping requests."""
    data = request.get_json()
    ids = data.get('ids', [])
    new_status = data.get('status')

    if not ids:
        return jsonify({'error': 'Nie wybrano żadnych zleceń'}), 400

    if not new_status:
        return jsonify({'error': 'Nie wybrano nowego statusu'}), 400

    # Verify status exists
    status_obj = ShippingRequestStatus.query.filter_by(slug=new_status, is_active=True).first()
    if not status_obj:
        return jsonify({'error': 'Nieprawidłowy status'}), 400

    updated_count = 0
    for sr_id in ids:
        sr = ShippingRequest.query.get(sr_id)
        if sr:
            sr.status = new_status
            updated_count += 1

    db.session.commit()

    # Activity log
    log_activity(
        user=current_user,
        action='shipping_requests_bulk_status_change',
        entity_type='shipping_request',
        new_value=json.dumps({
            'ids': ids,
            'new_status': new_status,
            'count': updated_count
        })
    )

    return jsonify({
        'success': True,
        'message': f'Zmieniono status {updated_count} zleceń na "{status_obj.name}"'
    })


@orders_bp.route('/admin/orders/shipping-request-statuses/list', methods=['GET'])
@login_required
@role_required('admin', 'mod')
def admin_list_shipping_request_statuses():
    """List all active shipping request statuses."""
    from modules.orders.models import ShippingRequestStatus

    statuses = ShippingRequestStatus.query.filter_by(is_active=True).order_by(ShippingRequestStatus.sort_order).all()

    return jsonify([{
        'id': s.id,
        'slug': s.slug,
        'name': s.name,
        'badge_color': s.badge_color,
        'is_initial': s.is_initial
    } for s in statuses])


# ====================
# ADMIN SHIPPING REQUESTS LIST
# ====================

@orders_bp.route('/admin/orders/shipping-requests')
@login_required
@role_required('admin', 'mod')
def admin_shipping_requests_list():
    """
    Admin shipping requests list with filters and pagination.
    """
    from modules.auth.models import User

    # Get filter parameters
    status_filter = request.args.get('status', '')
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Base query
    query = ShippingRequest.query

    # Apply status filter
    if status_filter:
        query = query.filter(ShippingRequest.status == status_filter)

    # Apply search filter (request number or user name)
    if search:
        search_term = f"%{search}%"
        query = query.join(User, ShippingRequest.user_id == User.id).filter(
            or_(
                ShippingRequest.request_number.ilike(search_term),
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                func.concat(User.first_name, ' ', User.last_name).ilike(search_term)
            )
        )

    # Order by creation date (newest first)
    query = query.order_by(ShippingRequest.created_at.desc())

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    shipping_requests = pagination.items

    # Get all active statuses for filter dropdown
    statuses = ShippingRequestStatus.query.filter_by(is_active=True).order_by(ShippingRequestStatus.sort_order).all()

    return render_template(
        'admin/orders/shipping_requests_list.html',
        shipping_requests=shipping_requests,
        pagination=pagination,
        statuses=statuses,
        current_status=status_filter,
        search=search,
        page_title='Zlecenia wysyłki'
    )
