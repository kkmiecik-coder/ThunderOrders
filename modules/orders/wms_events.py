"""
WMS (Warehouse Management System) - SocketIO Event Handlers
=============================================================

Real-time WebSocket events for WMS picking/packing sessions.
Handles desktop ↔ mobile synchronization via Flask-SocketIO.
"""

from flask import request as flask_request
from flask_login import current_user
from flask_socketio import join_room, emit

from extensions import socketio, db
from modules.orders.models import Order, OrderItem, get_local_now
from modules.orders.wms_models import WmsSession, WmsSessionOrder, PackagingMaterial

# Mapping: SocketIO sid → {session_id, role}
connected_clients = {}


def _get_room(session_id):
    """Return room name for a WMS session."""
    return f'wms_{session_id}'


def _build_item_data(item):
    """Build JSON-serializable dict for a single order item."""
    return {
        'id': item.id,
        'product_name': item.product_name,
        'product_sku': item.product_sku,
        'quantity': item.quantity,
        'picked_quantity': item.picked_quantity or 0,
        'wms_status': item.wms_status,
        'wms_status_name': item.wms_status_name,
        'wms_status_color': item.wms_status_color,
        'is_picked': (item.picked_quantity or 0) >= item.quantity,
        'picked_at': item.picked_at.isoformat() if item.picked_at else None,
    }


def _build_order_progress(order):
    """Build order-level progress data."""
    total_qty = sum(i.quantity for i in order.items)
    picked_qty = sum(i.picked_quantity or 0 for i in order.items)
    return {
        'id': order.id,
        'order_number': order.order_number,
        'is_picked': picked_qty >= total_qty and total_qty > 0,
        'picked_percentage': int((picked_qty / total_qty) * 100) if total_qty > 0 else 0,
        'total_quantity': total_qty,
        'picked_quantity': picked_qty,
    }


def _build_session_progress(wms_session):
    """Build session-level progress data."""
    return {
        'picked_orders_count': wms_session.picked_orders_count,
        'packed_orders_count': wms_session.packed_orders_count,
        'progress_percentage': wms_session.progress_percentage,
        'orders_count': wms_session.orders_count,
    }


# ====================
# EVENT HANDLERS
# ====================


@socketio.on('join_session')
def handle_join_session(data):
    """
    Client joins a WMS session room.

    Desktop: authenticated via flask_login (current_user).
    Mobile: authenticated via session_token.

    Data: {session_id, role: "desktop"|"mobile", token (mobile only)}
    """
    session_id = data.get('session_id')
    role = data.get('role', 'desktop')
    token = data.get('token')
    sid = flask_request.sid

    if not session_id:
        emit('error', {'message': 'Brak session_id'})
        return

    wms_session = db.session.get(WmsSession, session_id)
    if not wms_session:
        emit('error', {'message': 'Sesja WMS nie istnieje'})
        return

    if not wms_session.is_active:
        emit('error', {'message': 'Sesja WMS nie jest aktywna'})
        return

    # Authentication
    if role == 'mobile':
        if not token or token != wms_session.session_token:
            emit('error', {'message': 'Nieprawidłowy token sesji'})
            return

        # Mark phone as connected
        now = get_local_now()
        wms_session.phone_connected = True
        wms_session.phone_connected_at = now
        db.session.commit()

    else:
        # Desktop — require flask_login
        if not current_user or not current_user.is_authenticated:
            emit('error', {'message': 'Wymagane zalogowanie'})
            return

    # Join the room
    room = _get_room(session_id)
    join_room(room)

    # Track connection
    connected_clients[sid] = {
        'session_id': session_id,
        'role': role,
    }

    # Notify room if mobile joined
    if role == 'mobile':
        emit('phone_connected', {
            'connected_at': wms_session.phone_connected_at.isoformat()
            if wms_session.phone_connected_at else None,
        }, to=room)

    # Send full session state to the joining client
    from modules.orders.wms import _build_session_data
    session_data = _build_session_data(wms_session)
    emit('session_state', session_data)


@socketio.on('update_item_status')
def handle_update_item_status(data):
    """
    Update picked_quantity of an order item (from mobile scanner).

    Data: {order_item_id, action: "increment"|"decrement"|"pick_all"}
    Emits: item_status_updated, (optionally) order_picked
    """
    sid = flask_request.sid
    client = connected_clients.get(sid)
    if not client:
        emit('error', {'message': 'Nie jesteś podłączony do sesji'})
        return

    session_id = client['session_id']
    order_item_id = data.get('order_item_id')
    action = data.get('action')

    if not order_item_id or action not in ('increment', 'decrement', 'pick_all'):
        emit('error', {'message': 'Brak wymaganych danych (order_item_id, action)'})
        return

    item = db.session.get(OrderItem, order_item_id)
    if not item:
        emit('error', {'message': 'Pozycja zamówienia nie istnieje'})
        return

    order = item.order
    if not order or not order.wms_session_id:
        emit('error', {'message': 'Zamówienie nie jest w aktywnej sesji WMS'})
        return

    if order.wms_session_id != session_id:
        emit('error', {'message': 'Pozycja nie należy do tej sesji WMS'})
        return

    wms_session = db.session.get(WmsSession, session_id)
    if not wms_session or not wms_session.is_active:
        emit('error', {'message': 'Sesja WMS nie jest aktywna'})
        return

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

    # Update WMS status & picked fields
    if new_qty >= item.quantity:
        item.wms_status = 'zebrane'
        item.picked = True
        item.picked_at = now
        # For mobile — use session owner's user_id
        item.picked_by = wms_session.user_id
    else:
        item.wms_status = 'do_zebrania'
        item.picked = False
        item.picked_at = None
        item.picked_by = None

    # Update picking timestamps on WmsSessionOrder
    session_order = WmsSessionOrder.query.filter_by(
        session_id=session_id,
        order_id=order.id,
    ).first()

    if session_order:
        if not session_order.picking_started_at:
            session_order.picking_started_at = now

        all_picked = all(
            (i.picked_quantity or 0) >= i.quantity for i in order.items
        )
        if all_picked:
            session_order.picking_completed_at = now
        else:
            session_order.picking_completed_at = None

    db.session.commit()

    room = _get_room(session_id)
    order_progress = _build_order_progress(order)
    session_progress = _build_session_progress(wms_session)

    # Emit item update to the whole room
    emit('item_status_updated', {
        'item': _build_item_data(item),
        'order': order_progress,
        'session': session_progress,
    }, to=room)

    # If order is fully picked — additional event
    if order_progress['is_picked']:
        emit('order_picked', {
            'order': order_progress,
            'session': session_progress,
        }, to=room)


@socketio.on('mark_order_packed')
def handle_mark_order_packed(data):
    """
    Mark an order as packed (from mobile).

    Data: {order_id}
    Emits: order_packed, session_progress
    """
    sid = flask_request.sid
    client = connected_clients.get(sid)
    if not client:
        emit('error', {'message': 'Nie jesteś podłączony do sesji'})
        return

    session_id = client['session_id']
    order_id = data.get('order_id')

    if not order_id:
        emit('error', {'message': 'Brak order_id'})
        return

    wms_session = db.session.get(WmsSession, session_id)
    if not wms_session or not wms_session.is_active:
        emit('error', {'message': 'Sesja WMS nie jest aktywna'})
        return

    order = db.session.get(Order, order_id)
    if not order:
        emit('error', {'message': 'Zamówienie nie istnieje'})
        return

    session_order = WmsSessionOrder.query.filter_by(
        session_id=session_id,
        order_id=order.id,
    ).first()

    if not session_order:
        emit('error', {'message': 'Zamówienie nie należy do tej sesji WMS'})
        return

    if session_order.packing_completed_at:
        emit('error', {'message': 'Zamówienie jest już spakowane'})
        return

    now = get_local_now()

    order.status = 'spakowane'
    order.packed_at = now
    order.packed_by = wms_session.user_id

    # Packaging material & weight
    packaging_material_id = data.get('packaging_material_id')
    weight = data.get('weight')
    low_stock_warning = None

    if packaging_material_id:
        mat = db.session.get(PackagingMaterial, packaging_material_id)
        if mat:
            order.packaging_material_id = mat.id
            mat.quantity_in_stock = max(0, mat.quantity_in_stock - 1)
            if mat.is_low_stock:
                low_stock_warning = f'Materiał "{mat.name}": stan magazynowy: {mat.quantity_in_stock}'

    if weight is not None:
        try:
            order.total_package_weight = float(weight)
        except (ValueError, TypeError):
            pass

    session_order.packing_completed_at = now

    # Release WMS lock
    order.wms_locked_at = None
    order.wms_session_id = None

    db.session.commit()

    # Update ShippingRequest status if all orders are packed
    from modules.orders.wms import _update_sr_after_packing
    sr_info = _update_sr_after_packing(order)

    db.session.commit()

    # Send packing photo email if requested
    send_email_flag = data.get('send_email', False)
    if send_email_flag and order.packing_photo:
        try:
            from flask import current_app
            from utils.email_manager import EmailManager
            EmailManager.notify_packing_photo(order)
        except Exception as email_err:
            import logging
            logging.getLogger(__name__).error(f'WMS packing email error: {email_err}')

    room = _get_room(session_id)
    session_progress = _build_session_progress(wms_session)

    emit('order_packed', {
        'order': {
            'id': order.id,
            'order_number': order.order_number,
            'status': order.status,
            'status_display_name': order.status_display_name,
            'packed_at': now.isoformat(),
            'packaging_material_name': order.packaging_material.name if order.packaging_material else None,
            'total_package_weight': float(order.total_package_weight) if order.total_package_weight else None,
        },
        'session': session_progress,
        'shipping_request': sr_info,
        'low_stock_warning': low_stock_warning,
    }, to=room)

    emit('session_progress', session_progress, to=room)


@socketio.on('navigate_order')
def handle_navigate_order(data):
    """Mobile user navigated to a different order — sync desktop."""
    sid = flask_request.sid
    client = connected_clients.get(sid)
    if not client:
        return

    session_id = client['session_id']
    order_id = data.get('order_id')
    if not order_id:
        return

    room = _get_room(session_id)
    emit('order_navigated', {'order_id': order_id}, room=room, include_self=False)


@socketio.on('disconnect')
def handle_disconnect():
    """
    Handle client disconnect.
    If mobile — mark phone_connected=False and notify the room.
    """
    sid = flask_request.sid
    client = connected_clients.pop(sid, None)
    if not client:
        return

    session_id = client['session_id']
    role = client['role']

    if role == 'mobile':
        wms_session = db.session.get(WmsSession, session_id)
        if wms_session and wms_session.is_active:
            wms_session.phone_connected = False
            db.session.commit()

            room = _get_room(session_id)
            emit('phone_disconnected', {
                'session_id': session_id,
            }, to=room)
