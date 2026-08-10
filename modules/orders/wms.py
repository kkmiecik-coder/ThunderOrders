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
from PIL import Image, ImageOps
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
from modules.orders.wms_utils import (
    suggest_packaging, suggest_packaging_for_orders,
    ship_shipping_request, ShippingRequestAlreadyShipped,
    ShippingRequestUnpaid, reopen_orders_for_wms, REOPEN_MODES,
)
from modules.orders.wms_packing import (
    pack_shipping_request_group, get_packing_group, release_order_lock,
    update_sr_after_packing, PackingGroupError,
)
from extensions import db, socketio
from utils.decorators import role_required
from utils.activity_logger import log_activity


# Lock timeout in minutes — orders locked longer than this are considered abandoned
WMS_LOCK_TIMEOUT_MINUTES = 10


# ====================
# HELPER FUNCTIONS
# ====================


def _validate_orders_for_wms(order_ids, allow_packed=False):
    """
    Validate that orders can enter a WMS session.
    allow_packed=True wpuszcza też zamówienia spakowane — wyłącznie przy
    świadomym powrocie zlecenia do WMS (reopen_mode).
    Returns (valid_orders, errors) tuple.
    """
    errors = []
    valid_orders = []
    now = get_local_now()
    lock_cutoff = now - timedelta(minutes=WMS_LOCK_TIMEOUT_MINUTES)

    allowed_statuses = {'dostarczone_gom'}
    if allow_packed:
        allowed_statuses.add('spakowane')

    for oid in order_ids:
        order = db.session.get(Order, oid)
        if not order:
            errors.append(f'Zamówienie #{oid} nie istnieje')
            continue

        if order.status not in allowed_statuses:
            required_desc = (
                'status "Dostarczone GOM" lub "Spakowane"' if allow_packed
                else 'status "Dostarczone GOM"'
            )
            errors.append(
                f'{order.order_number}: wymagany {required_desc}, '
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
        sr = db.session.get(ShippingRequest, sr_id)
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
                'selected_size': item.selected_size,
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
                'address_type': sr.address_type,
                'full_address': sr.full_address,
                'shipping_name': sr.shipping_name,
                'shipping_address': sr.shipping_address,
                'shipping_postal_code': sr.shipping_postal_code,
                'shipping_city': sr.shipping_city,
                'pickup_courier': sr.pickup_courier,
                'pickup_point_id': sr.pickup_point_id,
                'pickup_address': sr.pickup_address,
                'courier': sr.courier,
                'tracking_number': sr.tracking_number,
                'parcel_size': sr.parcel_size,
                # Wycena i adresat przez właściwości modelu, nie surowe kolumny: przy
                # paczce zbiorczej `total_shipping_cost` jest puste, a `shipping_name`
                # jest puste przy każdej dostawie do paczkomatu (dominujący scenariusz).
                'total_shipping_cost': float(sr.display_shipping_cost) if sr.display_shipping_cost else None,
                'addressee_name': sr.addressee_name,
                'orders_count': sr.orders_count,
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


# ====================
# WMS ROUTES
# ====================


def build_shipping_requests_query(status_filter=None, order_type_filter=None, search=None,
                                   consolidation_filter=None):
    """Zlecenia wysyłki po filtrach z listy — wspólne dla widoku i zaznaczania.

    Zaznaczanie „na wszystkich stronach" musi objąć dokładnie te zlecenia,
    które admin widzi po filtrach, więc obie ścieżki liczą je tak samo.
    """
    from modules.auth.models import User
    from sqlalchemy import or_, func
    from sqlalchemy.orm import selectinload

    query = ShippingRequest.query

    if consolidation_filter == 'sources':
        # Podgląd zleceń oddanych do paczek zbiorczych — normalnie ukrytych.
        query = query.filter(ShippingRequest.consolidated_into_id.isnot(None))
    else:
        # Domyślnie admin widzi jedną paczkę zamiast N pozycji tej samej przesyłki.
        query = query.filter(ShippingRequest.consolidated_into_id.is_(None))

    # Karta zbiorcza pokazuje uczestników i ich zamówienia — bez tego mamy N+1
    # na źródłach/userach (can_cancel, consolidation_participants) i na
    # zamówieniach (orders_count, calculated_shipping_cost, karta listy).
    query = query.options(
        selectinload(ShippingRequest.consolidated_sources).selectinload(ShippingRequest.user),
        selectinload(ShippingRequest.request_orders).selectinload(ShippingRequestOrder.order),
    )

    if status_filter:
        query = query.filter(ShippingRequest.status == status_filter)

    if order_type_filter:
        # Zlecenie źródłowe straciło własne wiersze junction — przeniosły się do
        # paczki zbiorczej ze śladem source_request_id (patrz consolidation.py).
        # W widoku źródeł (`consolidation=sources`) filtr typu musi więc czytać
        # TEN ślad, bo shipping_request_id źródła nigdy nie ma już wierszy —
        # inaczej żadne źródło nie przeszłoby filtra, mimo że realnie ma
        # zamówienia danego typu.
        id_column = (
            ShippingRequestOrder.source_request_id if consolidation_filter == 'sources'
            else ShippingRequestOrder.shipping_request_id
        )
        query = query.filter(
            ShippingRequest.id.in_(
                db.session.query(id_column)
                .join(Order, ShippingRequestOrder.order_id == Order.id)
                .filter(Order.order_type == order_type_filter)
                .subquery()
            )
        )

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

    return query.order_by(ShippingRequest.created_at.desc())


@orders_bp.route('/api/orders/shipping-requests/filtered-ids')
@login_required
@role_required('admin', 'mod')
def shipping_requests_filtered_ids():
    """ID zleceń pasujących do aktywnych filtrów — dla „zaznacz na wszystkich stronach".

    Zwraca też ID klienta, bo pasek akcji potrzebuje go do oceny, czy
    zaznaczone zlecenia da się scalić, oraz status — zaznaczone spoza bieżącej
    strony nie mają karty w DOM, więc np. akcja "Oznacz jako wysłane" musi umieć
    ocenić je bez karty.
    """
    query = build_shipping_requests_query(
        request.args.get('status', ''),
        request.args.get('order_type', ''),
        request.args.get('search', ''),
        request.args.get('consolidation', ''),
    )

    rows = query.with_entities(
        ShippingRequest.id, ShippingRequest.user_id, ShippingRequest.status
    ).all()

    return jsonify({
        'success': True,
        'requests': [
            {'id': sr_id, 'client_id': user_id, 'status': status}
            for sr_id, user_id, status in rows
        ],
    })


@orders_bp.route('/admin/orders/wms')
@login_required
@role_required('admin', 'mod')
def wms_dashboard():
    """WMS Dashboard — shipping requests + sessions + packaging materials."""
    from datetime import datetime, time as dt_time
    from sqlalchemy import case, or_, func
    from modules.auth.models import User

    now = get_local_now()
    today_start = datetime.combine(now.date(), dt_time.min)

    active_tab = request.args.get('tab', 'shipping')

    # Active sessions (always show all)
    active_sessions_list = WmsSession.query.filter_by(status='active').order_by(
        WmsSession.created_at.desc()
    ).all()

    # History sessions (paginated, 5 per page)
    hist_page = request.args.get('hist_page', 1, type=int)
    hist_per_page = 5
    history_pagination = WmsSession.query.filter(
        WmsSession.status != 'active'
    ).order_by(
        WmsSession.created_at.desc()
    ).paginate(page=hist_page, per_page=hist_per_page, error_out=False)

    # Packaging materials
    materials = PackagingMaterial.query.order_by(PackagingMaterial.sort_order).all()

    # Stats — liczone po zleceniach wysyłki (widget na zakładce shipping)
    # "Do spakowania": zlecenia opłacone, czekające na spakowanie.
    to_pack_count = ShippingRequest.query.filter(
        ShippingRequest.status == 'oplacone'
    ).count()

    # "Spakowano dziś": zlecenia, których wszystkie zamówienia są spakowane
    # (Order.packed_at ustawione) i ostatnie spakowanie przypada na dziś.
    # ShippingRequest nie ma własnego packed_at, więc bazujemy na Order.packed_at
    # (zlecenie staje się 'spakowane' dokładnie gdy wszystkie jego zamówienia są spakowane).
    today_packed = (
        db.session.query(ShippingRequest.id)
        .join(ShippingRequestOrder, ShippingRequestOrder.shipping_request_id == ShippingRequest.id)
        .join(Order, ShippingRequestOrder.order_id == Order.id)
        .group_by(ShippingRequest.id)
        .having(func.count(Order.id) == func.count(Order.packed_at))
        .having(func.max(Order.packed_at) >= today_start)
        .count()
    )

    # Tab counts
    active_sessions_count = WmsSession.query.filter_by(status='active').count()
    sessions_count = WmsSession.query.count()
    materials_count = len(materials)

    # --- Shipping Requests tab data ---
    from utils.pagination import resolve_per_page, paginate_with_choice

    sr_status_filter = request.args.get('status', '')
    order_type_filter = request.args.get('order_type', '')
    sr_search = request.args.get('search', '')
    sr_consolidation_filter = request.args.get('consolidation', '')
    sr_page = request.args.get('page', 1, type=int)
    sr_per_page = resolve_per_page('wms_shipping', default=20)

    sr_query = build_shipping_requests_query(
        sr_status_filter, order_type_filter, sr_search, sr_consolidation_filter)
    sr_pagination = paginate_with_choice(sr_query, sr_page, sr_per_page)
    shipping_requests = sr_pagination.items

    sr_statuses = ShippingRequestStatus.query.filter_by(is_active=True).order_by(ShippingRequestStatus.sort_order).all()

    # SR count for badge — bez zleceń źródłowych, żeby liczba na zakładce zgadzała
    # się z tym, co admin faktycznie widzi na liście domyślnej.
    sr_total_count = ShippingRequest.query.filter(
        ShippingRequest.consolidated_into_id.is_(None)).count()

    return render_template(
        'admin/orders/wms_dashboard.html',
        active_sessions=active_sessions_list,
        history_sessions=history_pagination.items,
        history_pagination=history_pagination,
        materials=materials,
        today_packed=today_packed,
        to_pack_count=to_pack_count,
        active_sessions_count=active_sessions_count,
        sessions_count=sessions_count,
        materials_count=materials_count,
        active_tab=active_tab,
        material_types=PackagingMaterial.TYPE_CHOICES,
        size_choices=PackagingMaterial.SIZE_CHOICES,
        # SR data
        shipping_requests=shipping_requests,
        sr_pagination=sr_pagination,
        sr_statuses=sr_statuses,
        sr_status_filter=sr_status_filter,
        order_type_filter=order_type_filter,
        sr_search=sr_search,
        sr_consolidation_filter=sr_consolidation_filter,
        sr_total_count=sr_total_count,
        sr_per_page=sr_per_page,
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

        reopen_mode = data.get('reopen_mode') or None
        if reopen_mode and reopen_mode not in REOPEN_MODES:
            return jsonify({
                'success': False,
                'message': f'Nieznany tryb powrotu do WMS: {reopen_mode}'
            }), 400

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
        valid_orders, validation_errors = _validate_orders_for_wms(
            order_ids, allow_packed=bool(reopen_mode)
        )
        all_errors.extend(validation_errors)

        if not valid_orders:
            return jsonify({
                'success': False,
                'message': 'Żadne zamówienie nie spełnia wymagań WMS',
                'errors': all_errors
            }), 400

        # Powrót spakowanego zlecenia — cofnięcie musi się wydarzyć przed założeniem sesji,
        # żeby sesja widziała zamówienia już w stanie roboczym.
        if reopen_mode:
            # sr_objects zawiera tylko zlecenia przekazane wprost przez shipping_request_ids.
            # Jeśli żądanie cofa zamówienia podane samymi order_ids (bez shipping_request_ids),
            # musimy doszukać ich zleceń przez Order.shipping_request — inaczej zlecenie
            # zostałoby w statusie "spakowane", mimo że jego zamówienia wróciły do zbierania.
            # Nie "upraszczać" z powrotem do samego sr_objects.
            reopen_sr_objects = list(sr_objects)
            reopen_sr_ids = {sr.id for sr in reopen_sr_objects}
            for order in valid_orders:
                order_sr = order.shipping_request
                if order_sr and order_sr.id not in reopen_sr_ids:
                    reopen_sr_objects.append(order_sr)
                    reopen_sr_ids.add(order_sr.id)

            reopen_orders_for_wms(valid_orders, reopen_mode, reopen_sr_objects)

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

        # Cofnięcie zamówień do WMS trafia do bazy razem z sesją w powyższym commicie.
        # log_activity() samo commituje, więc wołamy je DOPIERO teraz — sesja już
        # istnieje w bazie. Wywołane przed commitem wyżej utrwaliłoby cofnięcie,
        # zanim sesja powstała: awaria zakładania sesji zostawiłaby cofnięte
        # zamówienia bez żadnej sesji.
        if reopen_mode:
            log_activity(
                user=current_user,
                action='wms_session_reopened',
                entity_type='shipping_request',
                entity_id=sr_objects[0].id if sr_objects else None,
                new_value={
                    'mode': reopen_mode,
                    'orders': [o.order_number for o in valid_orders],
                },
            )

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
        item = db.session.get(OrderItem, order_item_id)
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

        wms_session = db.session.get(WmsSession, order.wms_session_id)
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


@orders_bp.route('/admin/orders/wms/<int:session_id>/pack-shipping-request', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def wms_pack_shipping_request(session_id):
    """
    Pakuje całe zlecenie wysyłki jako jedną paczkę.
    Jedno zlecenie = jeden karton, więc opakowanie schodzi ze stanu raz,
    a klient dostaje jednego maila ze zdjęciem.
    """
    try:
        session = db.session.get(WmsSession, session_id)
        if not session:
            return jsonify({'success': False, 'message': 'Sesja nie istnieje'}), 404

        if not session.is_active:
            return jsonify({'success': False, 'message': 'Sesja WMS nie jest aktywna'}), 400

        data = request.get_json(silent=True) or {}
        sr_id = data.get('shipping_request_id')
        if not sr_id:
            return jsonify({'success': False, 'message': 'Brak shipping_request_id'}), 400

        shipping_request = db.session.get(ShippingRequest, sr_id)
        if not shipping_request:
            return jsonify({'success': False, 'message': 'Zlecenie wysyłki nie istnieje'}), 404

        result = pack_shipping_request_group(
            session,
            shipping_request,
            packaging_material_id=data.get('packaging_material_id'),
            total_package_weight=data.get('total_package_weight'),
            send_email=bool(data.get('send_email')),
            user_id=current_user.id,
        )
        db.session.commit()

        response = {
            'success': True,
            'message': f'Zlecenie {shipping_request.request_number} spakowane '
                       f'({len(result["orders"])} zam.)',
            'orders': result['orders'],
            'session': {
                'picked_orders_count': session.picked_orders_count,
                'packed_orders_count': session.packed_orders_count,
                'progress_percentage': session.progress_percentage,
            },
            'shipping_request': result['shipping_request'],
        }
        if result['low_stock_warning']:
            response['low_stock_warning'] = result['low_stock_warning']

        socketio.emit('shipping_request_packed', {
            'orders': result['orders'],
            'session': response['session'],
            'shipping_request': result['shipping_request'],
            'low_stock_warning': result['low_stock_warning'],
        }, to=f'wms_{session.id}')

        return jsonify(response)

    except PackingGroupError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': e.message}), e.status_code
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'WMS pack shipping request error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


@orders_bp.route('/admin/orders/wms/<int:session_id>/ship-sr', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def wms_ship_sr(session_id):
    """
    Oznacza zlecenie wysyłki jako wysłane z poziomu sesji WMS.
    Logika wspólna z listą zleceń — patrz wms_utils.ship_shipping_request().
    """
    try:
        session = WmsSession.query.get_or_404(session_id)
        data = request.get_json(silent=True) or {}

        sr_id = data.get('shipping_request_id')
        if not sr_id:
            return jsonify({'success': False, 'message': 'Brak shipping_request_id'}), 400

        sr = db.session.get(ShippingRequest, sr_id)
        if not sr:
            return jsonify({'success': False, 'message': 'Zlecenie wysyłki nie istnieje'}), 404

        result = ship_shipping_request(
            sr,
            courier=data.get('courier'),
            tracking_number=data.get('tracking_number'),
            parcel_size=data.get('parcel_size'),
            shipping_cost=data.get('shipping_cost'),
            order_costs=data.get('order_costs', []),
            user=current_user,
            wms_session=session,
        )

        return jsonify({
            'success': True,
            'message': f'Zlecenie {sr.request_number} oznaczone jako wysłane',
            'shipping_request': result,
        })

    except (ShippingRequestAlreadyShipped, ShippingRequestUnpaid) as e:
        return jsonify({'success': False, 'message': str(e)}), 409
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'WMS ship SR error: {e}')
        return jsonify({
            'success': False,
            'message': 'Nie udało się oznaczyć zlecenia jako wysłane — szczegóły w logach.'
        }), 500


def _wms_lock_blocking_session(sr):
    """Id otwartej sesji WMS blokującej którekolwiek zamówienie zlecenia, albo None."""
    # Źródłowe nie ma własnych zamówień, więc pętla po sr.orders nie wykryłaby
    # blokady. Sesję trzyma paczka zbiorcza — pytamy o nią.
    if sr.is_consolidated_source and sr.consolidated_into:
        sr = sr.consolidated_into

    lock_cutoff = get_local_now() - timedelta(minutes=WMS_LOCK_TIMEOUT_MINUTES)
    for order in sr.orders:
        if order.wms_locked_at and order.wms_locked_at > lock_cutoff:
            return order.wms_session_id
    return None


@orders_bp.route('/admin/orders/shipping-requests/<int:sr_id>/ship', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_ship_shipping_request(sr_id):
    """
    Oznacza spakowane zlecenie jako wysłane — poza sesją WMS, z listy zleceń.
    Logika wspólna z panelem w sesji — patrz wms_utils.ship_shipping_request().
    """
    sr = ShippingRequest.query.get_or_404(sr_id)
    data = request.get_json(silent=True) or {}

    if sr.is_consolidated_source:
        return jsonify({
            'success': False,
            'message': f'Zlecenie {sr.request_number} jedzie w paczce zbiorczej '
                       f'{sr.consolidated_into.request_number} — wyślij tamtą paczkę.',
        }), 409

    if sr.status not in ('spakowane', 'wyslane'):
        return jsonify({
            'success': False,
            'message': (f'Zlecenie {sr.request_number} nie jest spakowane '
                        f'(status: „{sr.status_display_name}")'),
        }), 400

    blocking_session_id = _wms_lock_blocking_session(sr)
    if blocking_session_id:
        return jsonify({
            'success': False,
            'message': (f'Zlecenie {sr.request_number} jest w otwartej sesji WMS '
                        f'#{blocking_session_id} — dokończ ją albo anuluj'),
        }), 409

    try:
        result = ship_shipping_request(
            sr,
            courier=data.get('courier'),
            tracking_number=data.get('tracking_number'),
            parcel_size=data.get('parcel_size'),
            shipping_cost=data.get('shipping_cost'),
            order_costs=data.get('order_costs', []),
            user=current_user,
        )
    except (ShippingRequestAlreadyShipped, ShippingRequestUnpaid) as e:
        return jsonify({'success': False, 'message': str(e)}), 409
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Ship SR from list error: {e}')
        return jsonify({
            'success': False,
            'message': 'Nie udało się oznaczyć zlecenia jako wysłane — szczegóły w logach.'
        }), 500

    return jsonify({
        'success': True,
        'message': f'Zlecenie {sr.request_number} oznaczone jako wysłane',
        'shipping_request': result,
    })


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
                release_order_lock(order)

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
                release_order_lock(order)

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
            'redirect_url': url_for('orders.wms_dashboard'),
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


def _packaging_materials_payload():
    """Lista aktywnych materiałów dla ręcznego wyboru — wspólna dla wszystkich
    endpointów sugestii, żeby nie utrzymywać trzech kopii tego samego kodu."""
    materials = PackagingMaterial.query.filter_by(is_active=True).order_by(
        PackagingMaterial.sort_order
    ).all()
    return [{
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


def _suggest_for_shipping_request(session, shipping_request):
    """Wspólna odpowiedź sugestii dla całej paczki — desktop i telefon."""
    group = get_packing_group(session, shipping_request)
    result = suggest_packaging_for_orders(group)
    return {
        'success': True,
        'suggestions': result['suggestions'],
        'warnings': result['warnings'],
        'total_weight': result['total_weight'],
        'total_volume': result['total_volume'],
        'all_materials': _packaging_materials_payload(),
        'suggested_material_id': shipping_request.packaging_material_id,
        'orders_count': len(group),
    }


@orders_bp.route('/api/orders/wms/<int:session_id>/suggest-packaging-sr/<int:sr_id>')
@login_required
@role_required('admin', 'mod')
def wms_suggest_packaging_sr(session_id, sr_id):
    """Sugestie opakowań dla całego zlecenia wysyłki (desktop)."""
    try:
        session = db.session.get(WmsSession, session_id)
        shipping_request = db.session.get(ShippingRequest, sr_id)
        if not session or not shipping_request:
            return jsonify({'success': False, 'message': 'Nie znaleziono'}), 404

        return jsonify(_suggest_for_shipping_request(session, shipping_request))

    except Exception as e:
        current_app.logger.error(f'WMS suggest packaging (SR) error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


@orders_bp.route(
    '/api/orders/wms/<int:session_id>/suggest-packaging-sr/<int:sr_id>/<session_token>'
)
def wms_suggest_packaging_sr_mobile(session_id, sr_id, session_token):
    """Sugestie opakowań dla zlecenia na telefonie — autoryzacja tokenem sesji."""
    try:
        session = WmsSession.query.filter_by(
            id=session_id, session_token=session_token
        ).first()
        if not session or not session.is_active:
            return jsonify({'success': False, 'message': 'Nieprawidłowy token sesji'}), 403

        shipping_request = db.session.get(ShippingRequest, sr_id)
        if not shipping_request:
            return jsonify({'success': False, 'message': 'Zlecenie nie istnieje'}), 404

        return jsonify(_suggest_for_shipping_request(session, shipping_request))

    except Exception as e:
        current_app.logger.error(f'WMS suggest packaging (SR, mobile) error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


@orders_bp.route('/api/orders/wms/suggest-packaging/<int:order_id>')
@login_required
@role_required('admin', 'mod')
def wms_suggest_packaging(order_id):
    """
    Suggest best-fit packaging materials for an order.
    Returns ranked suggestions + full list of active materials for manual selection.
    """
    try:
        order = db.session.get(Order, order_id)
        if not order:
            return jsonify({'success': False, 'message': 'Zamówienie nie istnieje'}), 404

        result = suggest_packaging(order)

        return jsonify({
            'success': True,
            'suggestions': result['suggestions'],
            'warnings': result['warnings'],
            'total_weight': result['total_weight'],
            'total_volume': result['total_volume'],
            'all_materials': _packaging_materials_payload(),
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

        order = db.session.get(Order, order_id)
        if not order:
            return jsonify({'success': False, 'message': 'Zamówienie nie istnieje'}), 404

        result = suggest_packaging(order)

        return jsonify({
            'success': True,
            'suggestions': result['suggestions'],
            'warnings': result['warnings'],
            'total_weight': result['total_weight'],
            'total_volume': result['total_volume'],
            'all_materials': _packaging_materials_payload(),
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

        order = db.session.get(Order, order_id)
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

        # Fix EXIF orientation (phone photos may be rotated)
        img = Image.open(save_path)
        img = ImageOps.exif_transpose(img)
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        img.save(save_path, 'JPEG', quality=85)

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

        order = db.session.get(Order, order_id)
        if not order:
            return jsonify({'success': False, 'message': 'Zamówienie nie istnieje'}), 404

        if not order.packing_photo:
            return jsonify({'success': False, 'message': 'Brak zdjęcia paczki'}), 400

        if not order.customer_email:
            return jsonify({'success': False, 'message': 'Brak adresu email klienta'}), 400

        from utils.email_manager import EmailManager
        from utils.push_manager import PushManager

        # Per zlecenie, nie per zamówienie: przy paczce zbiorczej karton jest
        # wspólny, więc zdjęcie należy się KAŻDEMU uczestnikowi, nie tylko
        # właścicielowi zamówienia, które admin wybrał w UI.
        sr = order.shipping_request
        if sr:
            EmailManager.notify_packing_photo_for_request(sr)
            PushManager.notify_packing_photo_for_request(sr)
        else:
            EmailManager.notify_packing_photo(order)
            PushManager.notify_packing_photo(order)

        message = (
            'Email ze zdjęciem paczki wysłany do wszystkich uczestników paczki zbiorczej'
            if sr and sr.is_consolidation else
            f'Email ze zdjęciem paczki wysłany do {order.customer_email}'
        )
        return jsonify({'success': True, 'message': message})

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
            'sale_price': float(m.sale_price) if m.sale_price else None,
            'size_category': m.size_category,
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
            'sale_price': float(m.sale_price) if m.sale_price else None,
            'size_category': m.size_category,
            'size_display': m.size_display,
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

        size_category = data.get('size_category')
        if size_category not in PackagingMaterial.SIZE_CHOICES:
            size_category = None

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
            sale_price=data.get('sale_price'),
            size_category=size_category,
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

        size_category = data.get('size_category')
        if size_category not in PackagingMaterial.SIZE_CHOICES:
            size_category = None

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
        m.sale_price = data.get('sale_price')
        m.size_category = size_category
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
            m = db.session.get(PackagingMaterial, item.get('id'))
            if m:
                m.sort_order = item.get('sort_order', 0)

        db.session.commit()

        return jsonify({'success': True, 'message': 'Kolejność zaktualizowana'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Packaging materials reorder error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500
