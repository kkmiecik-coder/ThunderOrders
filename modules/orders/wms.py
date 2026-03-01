"""
WMS (Warehouse Management System) - Routes
============================================

Routes for WMS picking/packing sessions.
Uses the existing orders_bp blueprint.
"""

import io
import os
import base64
import secrets
from datetime import timedelta

import qrcode
from flask import request, jsonify, abort, render_template, redirect, url_for, current_app
from flask_login import login_required, current_user

from extensions import csrf
from modules.orders import orders_bp
from modules.orders.models import (
    Order, OrderItem, OrderStatus, WmsStatus,
    ShippingRequest, ShippingRequestOrder, ShippingRequestStatus,
    get_local_now
)
from modules.orders.wms_models import (
    WmsSession, WmsSessionOrder, WmsSessionShippingRequest, PackagingMaterial
)
from modules.orders.wms_utils import suggest_packaging
from extensions import db, socketio
from utils.decorators import role_required
from utils.activity_logger import log_activity


# Lock timeout in minutes — orders locked longer than this are considered abandoned
WMS_LOCK_TIMEOUT_MINUTES = 10


# ====================
# HELPER FUNCTIONS
# ====================


def _validate_orders_for_wms(order_ids):
    """
    Validate that orders can enter a WMS session.
    Returns (valid_orders, errors) tuple.
    """
    errors = []
    valid_orders = []
    now = get_local_now()
    lock_cutoff = now - timedelta(minutes=WMS_LOCK_TIMEOUT_MINUTES)

    for oid in order_ids:
        order = Order.query.get(oid)
        if not order:
            errors.append(f'Zamówienie #{oid} nie istnieje')
            continue

        if order.status != 'dostarczone_gom':
            errors.append(
                f'{order.order_number}: wymagany status "Dostarczone GOM", '
                f'obecny: "{order.status_display_name}"'
            )
            continue

        # Check WMS lock
        if order.wms_locked_at and order.wms_locked_at > lock_cutoff:
            errors.append(
                f'{order.order_number}: zamówienie jest w trakcie pakowania '
                f'(zablokowane {order.wms_locked_at.strftime("%H:%M")})'
            )
            continue

        valid_orders.append(order)

    return valid_orders, errors


def _collect_orders_from_shipping_requests(sr_ids):
    """
    Collect all order IDs from given shipping request IDs.
    Returns (order_ids, sr_objects, errors) tuple.
    """
    order_ids = []
    sr_objects = []
    errors = []

    for sr_id in sr_ids:
        sr = ShippingRequest.query.get(sr_id)
        if not sr:
            errors.append(f'Zlecenie wysyłki #{sr_id} nie istnieje')
            continue

        sr_orders = [ro.order for ro in sr.request_orders if ro.order]
        if not sr_orders:
            errors.append(f'{sr.request_number}: brak zamówień w zleceniu')
            continue

        sr_objects.append(sr)
        for order in sr_orders:
            if order.id not in order_ids:
                order_ids.append(order.id)

    return order_ids, sr_objects, errors


def _build_session_data(session):
    """Build JSON-serializable dict with full session state."""
    orders_data = []
    for so in session.session_orders:
        order = so.order
        if not order:
            continue

        items_data = []
        for item in order.items:
            items_data.append({
                'id': item.id,
                'product_name': item.product_name,
                'product_sku': item.product_sku,
                'product_image_url': item.product_image_url,
                'quantity': item.quantity,
                'picked_quantity': item.picked_quantity or 0,
                'wms_status': item.wms_status,
                'wms_status_name': item.wms_status_name,
                'wms_status_color': item.wms_status_color,
                'is_picked': (item.picked_quantity or 0) >= item.quantity,
                'picked_at': item.picked_at.isoformat() if item.picked_at else None,
            })

        # Quantity-based progress
        total_qty = sum(i.quantity for i in order.items)
        picked_qty = sum(i.picked_quantity or 0 for i in order.items)
        picked_pct = int((picked_qty / total_qty) * 100) if total_qty > 0 else 0

        orders_data.append({
            'id': order.id,
            'order_number': order.order_number,
            'customer_name': order.customer_name,
            'order_type': order.order_type,
            'type_display_name': order.type_display_name,
            'status': order.status,
            'status_display_name': order.status_display_name,
            'items_count': order.items_count,
            'total_quantity': total_qty,
            'picked_quantity': picked_qty,
            'is_picked': picked_qty >= total_qty and total_qty > 0,
            'picked_percentage': picked_pct,
            'delivery_method': order.delivery_method_display,
            'sort_order': so.sort_order,
            'picking_started_at': so.picking_started_at.isoformat() if so.picking_started_at else None,
            'picking_completed_at': so.picking_completed_at.isoformat() if so.picking_completed_at else None,
            'packing_completed_at': so.packing_completed_at.isoformat() if so.packing_completed_at else None,
            'packaging_material_id': order.packaging_material_id,
            'packaging_material_name': order.packaging_material.name if order.packaging_material else None,
            'total_package_weight': float(order.total_package_weight) if order.total_package_weight else None,
            'packing_photo_url': f'/static/{order.packing_photo}' if order.packing_photo else None,
            'items': items_data,
            'shipping_request': None,
        })

        # Add shipping request info if available
        sr = order.shipping_request
        if sr:
            orders_data[-1]['shipping_request'] = {
                'id': sr.id,
                'request_number': sr.request_number,
                'status': sr.status,
                'status_display_name': sr.status_display_name,
            }

    # WMS statuses for the UI dropdown
    wms_statuses = WmsStatus.query.filter_by(is_active=True).order_by(WmsStatus.sort_order).all()
    statuses_data = [{
        'slug': s.slug,
        'name': s.name,
        'badge_color': s.badge_color,
        'is_picked': s.is_picked,
    } for s in wms_statuses]

    return {
        'session': {
            'id': session.id,
            'session_token': session.session_token,
            'status': session.status,
            'is_active': session.is_active,
            'created_at': session.created_at.isoformat() if session.created_at else None,
            'completed_at': session.completed_at.isoformat() if session.completed_at else None,
            'current_order_index': session.current_order_index,
            'orders_count': session.orders_count,
            'picked_orders_count': session.picked_orders_count,
            'packed_orders_count': session.packed_orders_count,
            'progress_percentage': session.progress_percentage,
            'created_by': session.user.full_name if session.user else 'Nieznany',
            'notes': session.notes,
            'phone_connected': bool(getattr(session, 'phone_connected', False)),
            'phone_connected_at': session.phone_connected_at.isoformat()
                if getattr(session, 'phone_connected_at', None) else None,
        },
        'orders': orders_data,
        'wms_statuses': statuses_data,
    }


def _release_order_lock(order):
    """Release WMS lock from an order."""
    order.wms_locked_at = None
    order.wms_session_id = None


def _ensure_do_wyslania_status():
    """Ensure 'do_wyslania' status exists in shipping_request_statuses."""
    if not ShippingRequestStatus.query.filter_by(slug='do_wyslania').first():
        db.session.add(ShippingRequestStatus(
            slug='do_wyslania',
            name='Do wysłania',
            badge_color='#f97316',
            sort_order=50,
            is_active=True,
            is_initial=False,
        ))


def _update_sr_after_packing(order):
    """
    After packing an order, check if all orders in its ShippingRequest are packed.
    If so, change SR status to 'do_wyslania'.
    Also ensure 'spakowane' is in allowed shipping statuses.
    Returns dict with SR status info or None.
    """
    from modules.auth.models import Settings
    import json

    sr = order.shipping_request
    if not sr:
        return None

    all_packed = all(o.status == 'spakowane' for o in sr.orders)

    sr_status_changed = False
    if all_packed:
        _ensure_do_wyslania_status()
        sr.status = 'do_wyslania'
        sr_status_changed = True

    # Auto-add 'spakowane' to allowed shipping statuses (one-time)
    setting = Settings.query.filter_by(key='shipping_request_allowed_statuses').first()
    if setting and setting.value:
        try:
            allowed = json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            allowed = []
        if 'spakowane' not in allowed:
            allowed.append('spakowane')
            setting.value = json.dumps(allowed)
    elif not setting:
        setting = Settings(
            key='shipping_request_allowed_statuses',
            value=json.dumps(['dostarczone_gom', 'spakowane']),
            type='json',
            description='Lista statusów zamówień kwalifikujących się do zlecenia wysyłki'
        )
        db.session.add(setting)

    return {
        'id': sr.id,
        'request_number': sr.request_number,
        'all_orders_packed': all_packed,
        'sr_status_changed': sr_status_changed,
        'sr_new_status': 'do_wyslania' if sr_status_changed else sr.status,
    }


# ====================
# WMS ROUTES
# ====================


@orders_bp.route('/admin/orders/wms')
@login_required
@role_required('admin', 'mod')
def wms_dashboard():
    """WMS Dashboard — sessions overview + packaging materials management."""
    from datetime import datetime, time as dt_time
    from sqlalchemy import case

    now = get_local_now()
    today_start = datetime.combine(now.date(), dt_time.min)

    # Sessions: active first, then completed/cancelled, limit 50
    sessions = WmsSession.query.order_by(
        case(
            (WmsSession.status == 'active', 0),
            else_=1,
        ),
        WmsSession.created_at.desc()
    ).limit(50).all()

    # Packaging materials
    materials = PackagingMaterial.query.order_by(PackagingMaterial.sort_order).all()

    # Stats
    today_packed = Order.query.filter(Order.packed_at >= today_start).count()
    to_pack_count = Order.query.filter(
        Order.status == 'dostarczone_gom',
        Order.wms_session_id.is_(None),
    ).count()

    # Tab counts
    active_sessions_count = WmsSession.query.filter_by(status='active').count()
    sessions_count = WmsSession.query.count()
    materials_count = len(materials)

    active_tab = request.args.get('tab', 'sessions')

    return render_template(
        'admin/orders/wms_dashboard.html',
        sessions=sessions,
        materials=materials,
        today_packed=today_packed,
        to_pack_count=to_pack_count,
        active_sessions_count=active_sessions_count,
        sessions_count=sessions_count,
        materials_count=materials_count,
        active_tab=active_tab,
        material_types=PackagingMaterial.TYPE_CHOICES,
    )


@orders_bp.route('/admin/orders/wms/create-session', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def wms_create_session():
    """
    Create a new WMS session from selected orders and/or shipping requests.
    Accepts JSON body with order_ids and/or shipping_request_ids.
    Returns JSON with redirect URL.
    """
    try:
        data = request.get_json(silent=True) or {}
        order_ids = data.get('order_ids', [])
        sr_ids = data.get('shipping_request_ids', [])

        # Fallback to form data
        if not order_ids and not sr_ids:
            order_ids_str = request.form.get('order_ids', '')
            sr_ids_str = request.form.get('shipping_request_ids', '')
            if order_ids_str:
                order_ids = [int(x) for x in order_ids_str.split(',') if x.strip()]
            if sr_ids_str:
                sr_ids = [int(x) for x in sr_ids_str.split(',') if x.strip()]

        if not order_ids and not sr_ids:
            return jsonify({
                'success': False,
                'message': 'Nie wybrano zamówień ani zleceń wysyłki'
            }), 400

        # Collect orders from shipping requests
        sr_objects = []
        all_errors = []
        if sr_ids:
            extra_order_ids, sr_objects, sr_errors = _collect_orders_from_shipping_requests(sr_ids)
            all_errors.extend(sr_errors)
            # Merge order IDs (avoid duplicates)
            for oid in extra_order_ids:
                if oid not in order_ids:
                    order_ids.append(oid)

        if not order_ids:
            return jsonify({
                'success': False,
                'message': 'Brak zamówień do przetworzenia',
                'errors': all_errors
            }), 400

        # Validate orders
        valid_orders, validation_errors = _validate_orders_for_wms(order_ids)
        all_errors.extend(validation_errors)

        if not valid_orders:
            return jsonify({
                'success': False,
                'message': 'Żadne zamówienie nie spełnia wymagań WMS',
                'errors': all_errors
            }), 400

        # Create session
        now = get_local_now()
        session = WmsSession(
            session_token=secrets.token_urlsafe(32),
            user_id=current_user.id,
            status='active',
            desktop_connected_at=now,
            created_at=now,
        )
        db.session.add(session)
        db.session.flush()  # Get session.id

        # Create WmsSessionOrder entries
        for idx, order in enumerate(valid_orders):
            session_order = WmsSessionOrder(
                session_id=session.id,
                order_id=order.id,
                sort_order=idx,
            )
            db.session.add(session_order)

            # Set WMS lock on order
            order.wms_locked_at = now
            order.wms_session_id = session.id

        # Create WmsSessionShippingRequest entries
        for sr in sr_objects:
            session_sr = WmsSessionShippingRequest(
                session_id=session.id,
                shipping_request_id=sr.id,
            )
            db.session.add(session_sr)

        db.session.commit()

        # Activity log
        log_activity(
            user=current_user,
            action='wms_session_created',
            entity_type='wms_session',
            entity_id=session.id,
            new_value={
                'orders': [o.order_number for o in valid_orders],
                'orders_count': len(valid_orders),
            }
        )

        result = {
            'success': True,
            'message': f'Sesja WMS utworzona — {len(valid_orders)} zamówień',
            'session_id': session.id,
            'redirect_url': url_for('orders.wms_session_page', session_id=session.id),
        }

        # Include warnings about skipped orders
        if all_errors:
            result['warnings'] = all_errors

        return jsonify(result)

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'WMS create session error: {e}')
        return jsonify({
            'success': False,
            'message': f'Błąd podczas tworzenia sesji: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/wms/<int:session_id>')
@login_required
@role_required('admin', 'mod')
def wms_session_page(session_id):
    """
    Desktop WMS session page.
    Renders the picking/packing interface.
    """
    session = WmsSession.query.get_or_404(session_id)

    # Build full session data for template
    session_data = _build_session_data(session)

    return render_template(
        'admin/orders/wms.html',
        wms_session=session,
        session_data=session_data,
    )


@orders_bp.route('/admin/orders/wms/<int:session_id>/data')
@login_required
@role_required('admin', 'mod')
def wms_session_data(session_id):
    """
    JSON endpoint with full session state.
    Used for initial load and page refresh.
    """
    session = WmsSession.query.get_or_404(session_id)
    return jsonify(_build_session_data(session))


@orders_bp.route('/admin/orders/wms/update-item-status', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def wms_update_item_status():
    """
    Update picked_quantity of an order item via increment/decrement/pick_all.
    Automatically sets wms_status, picked, picked_at, picked_by based on progress.
    Returns JSON with new state and order/session progress.
    """
    try:
        data = request.get_json(silent=True) or {}
        order_item_id = data.get('order_item_id')
        action = data.get('action')  # "increment", "decrement", "pick_all"

        if not order_item_id or action not in ('increment', 'decrement', 'pick_all'):
            return jsonify({
                'success': False,
                'message': 'Brak wymaganych danych (order_item_id, action: increment/decrement/pick_all)'
            }), 400

        # Load item
        item = OrderItem.query.get(order_item_id)
        if not item:
            return jsonify({
                'success': False,
                'message': 'Pozycja zamówienia nie istnieje'
            }), 404

        # Validate item belongs to an order in an active WMS session
        order = item.order
        if not order or not order.wms_session_id:
            return jsonify({
                'success': False,
                'message': 'Zamówienie nie jest w aktywnej sesji WMS'
            }), 400

        wms_session = WmsSession.query.get(order.wms_session_id)
        if not wms_session or not wms_session.is_active:
            return jsonify({
                'success': False,
                'message': 'Sesja WMS nie jest aktywna'
            }), 400

        now = get_local_now()
        current_qty = item.picked_quantity or 0

        # Apply action
        if action == 'increment':
            new_qty = min(current_qty + 1, item.quantity)
        elif action == 'decrement':
            new_qty = max(current_qty - 1, 0)
        else:  # pick_all
            new_qty = item.quantity

        item.picked_quantity = new_qty

        # Update WMS status & picked fields based on picked_quantity
        if new_qty >= item.quantity:
            # Fully picked
            item.wms_status = 'zebrane'
            item.picked = True
            item.picked_at = now
            item.picked_by = current_user.id
        else:
            # Not fully picked (including 0)
            item.wms_status = 'do_zebrania'
            item.picked = False
            item.picked_at = None
            item.picked_by = None

        # Update picking timestamps on WmsSessionOrder
        session_order = WmsSessionOrder.query.filter_by(
            session_id=wms_session.id,
            order_id=order.id
        ).first()

        if session_order:
            if not session_order.picking_started_at:
                session_order.picking_started_at = now

            # Recalculate: all items fully picked?
            all_picked = all(
                (i.picked_quantity or 0) >= i.quantity for i in order.items
            )
            if all_picked:
                session_order.picking_completed_at = now
            else:
                session_order.picking_completed_at = None

        db.session.commit()

        # Compute quantity-based progress for this order
        total_qty = sum(i.quantity for i in order.items)
        picked_qty = sum(i.picked_quantity or 0 for i in order.items)
        order_picked_pct = int((picked_qty / total_qty) * 100) if total_qty > 0 else 0
        order_is_picked = picked_qty >= total_qty

        return jsonify({
            'success': True,
            'item': {
                'id': item.id,
                'picked_quantity': item.picked_quantity,
                'quantity': item.quantity,
                'wms_status': item.wms_status,
                'wms_status_name': item.wms_status_name,
                'wms_status_color': item.wms_status_color,
                'is_picked': item.picked_quantity >= item.quantity,
                'picked_at': item.picked_at.isoformat() if item.picked_at else None,
            },
            'order': {
                'id': order.id,
                'is_picked': order_is_picked,
                'picked_percentage': order_picked_pct,
                'total_quantity': total_qty,
                'picked_quantity': picked_qty,
            },
            'session': {
                'picked_orders_count': wms_session.picked_orders_count,
                'packed_orders_count': wms_session.packed_orders_count,
                'progress_percentage': wms_session.progress_percentage,
            },
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'WMS update item status error: {e}')
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/wms/<int:session_id>/pack-order', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def wms_pack_order(session_id):
    """
    Mark an order as packed within a WMS session.
    Sets order status to 'spakowane', releases lock.
    """
    try:
        session = WmsSession.query.get_or_404(session_id)

        if not session.is_active:
            return jsonify({
                'success': False,
                'message': 'Sesja WMS nie jest aktywna'
            }), 400

        data = request.get_json(silent=True) or {}
        order_id = data.get('order_id')

        if not order_id:
            return jsonify({
                'success': False,
                'message': 'Brak order_id'
            }), 400

        order = Order.query.get(order_id)
        if not order:
            return jsonify({
                'success': False,
                'message': 'Zamówienie nie istnieje'
            }), 404

        # Verify order belongs to this session
        session_order = WmsSessionOrder.query.filter_by(
            session_id=session.id,
            order_id=order.id
        ).first()

        if not session_order:
            return jsonify({
                'success': False,
                'message': 'Zamówienie nie należy do tej sesji WMS'
            }), 400

        if session_order.packing_completed_at:
            return jsonify({
                'success': False,
                'message': 'Zamówienie jest już spakowane'
            }), 400

        # Mark as packed
        now = get_local_now()
        old_status = order.status

        order.status = 'spakowane'
        order.packed_at = now
        order.packed_by = current_user.id

        # Packaging material & weight
        packaging_material_id = data.get('packaging_material_id')
        total_package_weight = data.get('total_package_weight')
        low_stock_warning = None

        if packaging_material_id:
            mat = PackagingMaterial.query.get(packaging_material_id)
            if mat:
                order.packaging_material_id = mat.id
                mat.quantity_in_stock = max(0, mat.quantity_in_stock - 1)
                if mat.is_low_stock:
                    low_stock_warning = f'Materiał "{mat.name}": stan magazynowy: {mat.quantity_in_stock}'

        if total_package_weight is not None:
            try:
                order.total_package_weight = float(total_package_weight)
            except (ValueError, TypeError):
                pass

        session_order.packing_completed_at = now

        # Release WMS lock
        _release_order_lock(order)

        db.session.commit()

        # Send packing photo email if requested
        send_email_flag = data.get('send_email', False)
        if send_email_flag and order.packing_photo:
            try:
                from utils.email_manager import EmailManager
                EmailManager.notify_packing_photo(order)
            except Exception as email_err:
                current_app.logger.error(f'WMS packing email error: {email_err}')

        # Activity log
        log_activity(
            user=current_user,
            action='order_packed',
            entity_type='order',
            entity_id=order.id,
            old_value={'status': old_status},
            new_value={
                'status': 'spakowane',
                'wms_session_id': session.id,
                'packaging_material_id': order.packaging_material_id,
                'total_package_weight': float(order.total_package_weight) if order.total_package_weight else None,
            }
        )

        # Update ShippingRequest status if all orders are packed
        sr_info = _update_sr_after_packing(order)
        db.session.commit()  # commit SR status change

        result = {
            'success': True,
            'message': f'Zamówienie {order.order_number} spakowane',
            'order': {
                'id': order.id,
                'order_number': order.order_number,
                'status': order.status,
                'status_display_name': order.status_display_name,
                'packed_at': now.isoformat(),
            },
            'session': {
                'picked_orders_count': session.picked_orders_count,
                'packed_orders_count': session.packed_orders_count,
                'progress_percentage': session.progress_percentage,
            },
            'shipping_request': sr_info,
        }

        if low_stock_warning:
            result['low_stock_warning'] = low_stock_warning

        return jsonify(result)

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'WMS pack order error: {e}')
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/wms/<int:session_id>/complete', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def wms_complete_session(session_id):
    """
    Complete a WMS session.
    Releases all locks, sets session status to 'completed'.
    """
    try:
        session = WmsSession.query.get_or_404(session_id)

        if session.status == 'completed':
            return jsonify({
                'success': False,
                'message': 'Sesja jest już zakończona'
            }), 400

        now = get_local_now()
        session.status = 'completed'
        session.completed_at = now

        # Release locks on all orders still locked by this session
        for so in session.session_orders:
            order = so.order
            if order and order.wms_session_id == session.id:
                _release_order_lock(order)

        db.session.commit()

        # Notify other devices (mobile) that session ended
        socketio.emit('session_ended', {
            'session_id': session.id,
            'status': 'completed',
            'message': f'Sesja WMS zakończona — spakowano {session.packed_orders_count}/{session.orders_count} zamówień',
        }, to=f'wms_{session.id}')

        log_activity(
            user=current_user,
            action='wms_session_completed',
            entity_type='wms_session',
            entity_id=session.id,
            new_value={
                'packed_count': session.packed_orders_count,
                'total_count': session.orders_count,
            }
        )

        return jsonify({
            'success': True,
            'message': f'Sesja WMS zakończona — spakowano {session.packed_orders_count}/{session.orders_count} zamówień',
            'redirect_url': url_for('orders.admin_list'),
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'WMS complete session error: {e}')
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/wms/<int:session_id>/cancel', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def wms_cancel_session(session_id):
    """
    Cancel a WMS session.
    Releases all locks, sets session status to 'cancelled'.
    Does NOT revert order statuses (only releases WMS locks).
    """
    try:
        session = WmsSession.query.get_or_404(session_id)

        if session.status in ('completed', 'cancelled'):
            return jsonify({
                'success': False,
                'message': f'Sesja jest już {session.status}'
            }), 400

        session.status = 'cancelled'
        session.completed_at = get_local_now()

        # Release all locks
        for so in session.session_orders:
            order = so.order
            if order and order.wms_session_id == session.id:
                _release_order_lock(order)

        db.session.commit()

        # Notify other devices (mobile) that session was cancelled
        socketio.emit('session_ended', {
            'session_id': session.id,
            'status': 'cancelled',
            'message': 'Sesja WMS anulowana — zamówienia odblokowane',
        }, to=f'wms_{session.id}')

        log_activity(
            user=current_user,
            action='wms_session_cancelled',
            entity_type='wms_session',
            entity_id=session.id,
        )

        return jsonify({
            'success': True,
            'message': 'Sesja WMS anulowana — zamówienia odblokowane',
            'redirect_url': url_for('orders.admin_list'),
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'WMS cancel session error: {e}')
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


@orders_bp.route('/admin/orders/wms/<int:session_id>/qr')
@login_required
@role_required('admin', 'mod')
def wms_session_qr(session_id):
    """
    Generate a QR code for pairing a mobile device with this WMS session.
    Returns JSON with base64-encoded QR image data URI.
    """
    try:
        session = WmsSession.query.get_or_404(session_id)

        # Build mobile URL
        mobile_url = request.url_root.rstrip('/') + f'/wms/mobile/{session.session_token}'

        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(mobile_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color='black', back_color='white')

        # Convert to base64 data URI
        buffer = io.BytesIO()
        qr_img.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        qr_data_uri = f'data:image/png;base64,{qr_base64}'

        return jsonify({
            'success': True,
            'qr_image': qr_data_uri,
            'mobile_url': mobile_url,
        })

    except Exception as e:
        current_app.logger.error(f'WMS QR generation error: {e}')
        return jsonify({
            'success': False,
            'message': f'Błąd generowania QR: {str(e)}'
        }), 500


# ====================
# PACKAGING SUGGESTIONS API
# ====================


@orders_bp.route('/api/orders/wms/suggest-packaging/<int:order_id>')
@login_required
@role_required('admin', 'mod')
def wms_suggest_packaging(order_id):
    """
    Suggest best-fit packaging materials for an order.
    Returns ranked suggestions + full list of active materials for manual selection.
    """
    try:
        order = Order.query.get(order_id)
        if not order:
            return jsonify({'success': False, 'message': 'Zamówienie nie istnieje'}), 404

        result = suggest_packaging(order)

        # Full list of active materials for manual dropdown
        all_materials = PackagingMaterial.query.filter_by(is_active=True).order_by(
            PackagingMaterial.sort_order
        ).all()

        all_materials_data = [{
            'id': m.id,
            'name': m.name,
            'type': m.type,
            'type_display': m.type_display,
            'dimensions_display': m.dimensions_display,
            'max_weight': float(m.max_weight) if m.max_weight else None,
            'own_weight': float(m.own_weight) if m.own_weight else None,
            'quantity_in_stock': m.quantity_in_stock,
            'is_low_stock': m.is_low_stock,
            'cost': float(m.cost) if m.cost else None,
        } for m in all_materials]

        return jsonify({
            'success': True,
            'suggestions': result['suggestions'],
            'warnings': result['warnings'],
            'total_weight': result['total_weight'],
            'total_volume': result['total_volume'],
            'all_materials': all_materials_data,
        })

    except Exception as e:
        current_app.logger.error(f'WMS suggest packaging error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


# ====================
# PACKAGING SUGGESTIONS (MOBILE — token-based auth)
# ====================


@orders_bp.route('/api/orders/wms/suggest-packaging/<int:order_id>/<session_token>')
def wms_suggest_packaging_mobile(order_id, session_token):
    """
    Suggest packaging materials for mobile (auth via session_token).
    Same as wms_suggest_packaging but uses token instead of login.
    """
    try:
        wms_session = WmsSession.query.filter_by(session_token=session_token).first()
        if not wms_session or not wms_session.is_active:
            return jsonify({'success': False, 'message': 'Nieprawidłowy token sesji'}), 403

        # Verify order belongs to this session
        session_order = WmsSessionOrder.query.filter_by(
            session_id=wms_session.id,
            order_id=order_id
        ).first()
        if not session_order:
            return jsonify({'success': False, 'message': 'Zamówienie nie należy do tej sesji'}), 403

        order = Order.query.get(order_id)
        if not order:
            return jsonify({'success': False, 'message': 'Zamówienie nie istnieje'}), 404

        result = suggest_packaging(order)

        all_materials = PackagingMaterial.query.filter_by(is_active=True).order_by(
            PackagingMaterial.sort_order
        ).all()

        all_materials_data = [{
            'id': m.id,
            'name': m.name,
            'type': m.type,
            'type_display': m.type_display,
            'dimensions_display': m.dimensions_display,
            'max_weight': float(m.max_weight) if m.max_weight else None,
            'own_weight': float(m.own_weight) if m.own_weight else None,
            'quantity_in_stock': m.quantity_in_stock,
            'is_low_stock': m.is_low_stock,
            'cost': float(m.cost) if m.cost else None,
        } for m in all_materials]

        return jsonify({
            'success': True,
            'suggestions': result['suggestions'],
            'warnings': result['warnings'],
            'total_weight': result['total_weight'],
            'total_volume': result['total_volume'],
            'all_materials': all_materials_data,
        })

    except Exception as e:
        current_app.logger.error(f'WMS suggest packaging (mobile) error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


# ====================
# MOBILE PHOTO UPLOAD
# ====================


@orders_bp.route('/wms/mobile/upload-packing-photo', methods=['POST'])
@csrf.exempt
def wms_upload_packing_photo():
    """
    Upload a packing photo from mobile device.
    Auth via session_token (form field), not flask_login.
    Accepts multipart/form-data with session_token, order_id, photo.
    """
    try:
        session_token = request.form.get('session_token')
        order_id = request.form.get('order_id')
        photo = request.files.get('photo')

        if not session_token or not order_id or not photo:
            return jsonify({
                'success': False,
                'message': 'Brak wymaganych danych (session_token, order_id, photo)'
            }), 400

        order_id = int(order_id)

        # Validate session
        wms_session = WmsSession.query.filter_by(session_token=session_token).first()
        if not wms_session or not wms_session.is_active:
            return jsonify({
                'success': False,
                'message': 'Nieprawidłowy token sesji lub sesja nieaktywna'
            }), 403

        # Verify order belongs to session
        session_order = WmsSessionOrder.query.filter_by(
            session_id=wms_session.id,
            order_id=order_id
        ).first()
        if not session_order:
            return jsonify({
                'success': False,
                'message': 'Zamówienie nie należy do tej sesji'
            }), 403

        order = Order.query.get(order_id)
        if not order:
            return jsonify({
                'success': False,
                'message': 'Zamówienie nie istnieje'
            }), 404

        # Validate file
        allowed_extensions = {'jpg', 'jpeg', 'png', 'webp'}
        filename = photo.filename or ''
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if ext not in allowed_extensions:
            return jsonify({
                'success': False,
                'message': 'Niedozwolony format pliku. Dozwolone: jpg, jpeg, png, webp'
            }), 400

        # Check file size (max 10MB)
        photo.seek(0, 2)
        file_size = photo.tell()
        photo.seek(0)
        if file_size > 10 * 1024 * 1024:
            return jsonify({
                'success': False,
                'message': 'Plik jest za duży (max 10MB)'
            }), 400

        # Save file
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'packing_photos')
        os.makedirs(upload_dir, exist_ok=True)

        now = get_local_now()
        timestamp = now.strftime('%Y%m%d_%H%M%S')
        save_filename = f'{order_id}_{timestamp}.jpg'
        save_path = os.path.join(upload_dir, save_filename)
        photo.save(save_path)

        # Update order
        relative_path = f'uploads/packing_photos/{save_filename}'
        order.packing_photo = relative_path
        db.session.commit()

        photo_url = f'/static/{relative_path}'

        # Emit WebSocket event
        socketio.emit('packing_photo_uploaded', {
            'order_id': order_id,
            'photo_url': photo_url,
        }, to=f'wms_{wms_session.id}')

        return jsonify({
            'success': True,
            'photo_url': photo_url,
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'WMS upload packing photo error: {e}')
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


# ====================
# MOBILE WMS ROUTE
# ====================


@orders_bp.route('/wms/mobile/<session_token>')
@csrf.exempt
def wms_mobile_page(session_token):
    """
    Mobile WMS page — accessed by scanning the QR code.
    No login required; the session_token acts as authorization.
    """
    wms_session = WmsSession.query.filter_by(session_token=session_token).first()

    if not wms_session:
        return render_template(
            'admin/orders/wms_mobile_error.html',
            error_title='Sesja nie istnieje',
            error_message='Link jest nieprawidłowy lub sesja została usunięta.',
        ), 404

    if not wms_session.is_active:
        status_messages = {
            'completed': 'Sesja WMS została zakończona.',
            'cancelled': 'Sesja WMS została anulowana.',
            'paused': 'Sesja WMS jest wstrzymana.',
        }
        return render_template(
            'admin/orders/wms_mobile_error.html',
            error_title='Sesja nieaktywna',
            error_message=status_messages.get(
                wms_session.status,
                'Sesja WMS nie jest już aktywna.'
            ),
        ), 410

    session_data = _build_session_data(wms_session)

    return render_template(
        'admin/orders/wms_mobile.html',
        wms_session=wms_session,
        session_data=session_data,
    )


# ====================
# SEND PACKING EMAIL (manual re-send)
# ====================


@orders_bp.route('/admin/orders/wms/send-packing-email', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def wms_send_packing_email():
    """
    Manually send (or re-send) packing photo email to client.
    Requires order to have a packing_photo set.
    """
    try:
        data = request.get_json(silent=True) or {}
        order_id = data.get('order_id')

        if not order_id:
            return jsonify({'success': False, 'message': 'Brak order_id'}), 400

        order = Order.query.get(order_id)
        if not order:
            return jsonify({'success': False, 'message': 'Zamówienie nie istnieje'}), 404

        if not order.packing_photo:
            return jsonify({'success': False, 'message': 'Brak zdjęcia paczki'}), 400

        if not order.customer_email:
            return jsonify({'success': False, 'message': 'Brak adresu email klienta'}), 400

        from utils.email_manager import EmailManager
        EmailManager.notify_packing_photo(order)

        return jsonify({
            'success': True,
            'message': f'Email ze zdjęciem paczki wysłany do {order.customer_email}',
        })

    except Exception as e:
        current_app.logger.error(f'WMS send packing email error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


# ====================
# PACKAGING MATERIALS CRUD
# ====================


@orders_bp.route('/api/orders/packaging-materials/<int:material_id>')
@login_required
@role_required('admin', 'mod')
def packaging_material_get(material_id):
    """Get a single packaging material as JSON (for edit modal)."""
    m = PackagingMaterial.query.get_or_404(material_id)
    return jsonify({
        'success': True,
        'material': {
            'id': m.id,
            'name': m.name,
            'type': m.type,
            'inner_length': float(m.inner_length) if m.inner_length else None,
            'inner_width': float(m.inner_width) if m.inner_width else None,
            'inner_height': float(m.inner_height) if m.inner_height else None,
            'max_weight': float(m.max_weight) if m.max_weight else None,
            'own_weight': float(m.own_weight) if m.own_weight else None,
            'quantity_in_stock': m.quantity_in_stock,
            'low_stock_threshold': m.low_stock_threshold,
            'cost': float(m.cost) if m.cost else None,
            'is_active': m.is_active,
            'sort_order': m.sort_order,
        }
    })


@orders_bp.route('/api/orders/packaging-materials')
@login_required
@role_required('admin', 'mod')
def packaging_materials_list_api():
    """List active packaging materials as JSON (for dropdowns)."""
    materials = PackagingMaterial.query.filter_by(is_active=True).order_by(
        PackagingMaterial.sort_order
    ).all()
    return jsonify({
        'success': True,
        'materials': [{
            'id': m.id,
            'name': m.name,
            'type': m.type,
            'type_display': m.type_display,
            'dimensions_display': m.dimensions_display,
            'max_weight': float(m.max_weight) if m.max_weight else None,
            'own_weight': float(m.own_weight) if m.own_weight else None,
            'quantity_in_stock': m.quantity_in_stock,
            'is_low_stock': m.is_low_stock,
            'cost': float(m.cost) if m.cost else None,
        } for m in materials]
    })


@orders_bp.route('/admin/orders/packaging-materials/create', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def packaging_material_create():
    """Create a new packaging material."""
    try:
        data = request.get_json(silent=True) or {}

        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'message': 'Nazwa jest wymagana'}), 400

        mat_type = data.get('type', 'karton')
        if mat_type not in PackagingMaterial.TYPE_CHOICES:
            mat_type = 'karton'

        max_sort = db.session.query(db.func.max(PackagingMaterial.sort_order)).scalar() or 0

        m = PackagingMaterial(
            name=name,
            type=mat_type,
            inner_length=data.get('inner_length'),
            inner_width=data.get('inner_width'),
            inner_height=data.get('inner_height'),
            max_weight=data.get('max_weight'),
            own_weight=data.get('own_weight'),
            quantity_in_stock=data.get('quantity_in_stock', 0),
            low_stock_threshold=data.get('low_stock_threshold', 5),
            cost=data.get('cost'),
            is_active=data.get('is_active', True),
            sort_order=max_sort + 1,
        )
        db.session.add(m)
        db.session.commit()

        return jsonify({'success': True, 'message': f'Materiał "{name}" dodany', 'id': m.id})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Packaging material create error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


@orders_bp.route('/admin/orders/packaging-materials/<int:material_id>/update', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def packaging_material_update(material_id):
    """Update an existing packaging material."""
    try:
        m = PackagingMaterial.query.get_or_404(material_id)
        data = request.get_json(silent=True) or {}

        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'success': False, 'message': 'Nazwa jest wymagana'}), 400

        mat_type = data.get('type', m.type)
        if mat_type not in PackagingMaterial.TYPE_CHOICES:
            mat_type = m.type

        m.name = name
        m.type = mat_type
        m.inner_length = data.get('inner_length')
        m.inner_width = data.get('inner_width')
        m.inner_height = data.get('inner_height')
        m.max_weight = data.get('max_weight')
        m.own_weight = data.get('own_weight')
        m.quantity_in_stock = data.get('quantity_in_stock', m.quantity_in_stock)
        m.low_stock_threshold = data.get('low_stock_threshold', m.low_stock_threshold)
        m.cost = data.get('cost')
        m.is_active = data.get('is_active', m.is_active)

        db.session.commit()

        return jsonify({'success': True, 'message': f'Materiał "{name}" zaktualizowany'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Packaging material update error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


@orders_bp.route('/admin/orders/packaging-materials/<int:material_id>', methods=['DELETE'])
@login_required
@role_required('admin', 'mod')
def packaging_material_delete(material_id):
    """Delete a packaging material."""
    try:
        m = PackagingMaterial.query.get_or_404(material_id)
        name = m.name
        db.session.delete(m)
        db.session.commit()

        return jsonify({'success': True, 'message': f'Materiał "{name}" usunięty'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Packaging material delete error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


@orders_bp.route('/admin/orders/packaging-materials/reorder', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def packaging_materials_reorder():
    """Reorder packaging materials via drag & drop."""
    try:
        data = request.get_json(silent=True) or {}
        order_list = data.get('order', [])

        if not order_list:
            return jsonify({'success': False, 'message': 'Brak danych kolejności'}), 400

        for item in order_list:
            m = PackagingMaterial.query.get(item.get('id'))
            if m:
                m.sort_order = item.get('sort_order', 0)

        db.session.commit()

        return jsonify({'success': True, 'message': 'Kolejność zaktualizowana'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Packaging materials reorder error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500
