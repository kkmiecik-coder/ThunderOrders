"""
Exclusive Module - SocketIO Event Handlers
==========================================

Real-time WebSocket events for Exclusive LIVE Dashboard.
Handles visitor counting (countdown/order pages) and admin room updates.
"""

import time
import threading
from flask import request as flask_request
from flask_socketio import join_room, leave_room, emit

from extensions import socketio

# Tracking visitors per exclusive page
# Structure: { page_id: { 'countdown': set(sid), 'order': set(sid) } }
_visitor_rooms = {}
_visitor_lock = threading.Lock()

# Admin connections per page
# Structure: { page_id: set(sid) }
_admin_rooms = {}
_admin_lock = threading.Lock()

# Mapping sid → { page_id, role ('countdown'|'order'|'admin') }
_connected_clients = {}


def _get_visitor_room(page_id, page_type):
    """Return room name for visitors on exclusive page."""
    return f'exclusive_{page_id}_{page_type}'


def _get_admin_room(page_id):
    """Return room name for admin LIVE dashboard."""
    return f'exclusive_admin_{page_id}'


def _get_visitor_counts(page_id):
    """Get current visitor counts and active reservations for a page."""
    with _visitor_lock:
        rooms = _visitor_rooms.get(page_id, {})
        counts = {
            'countdown': len(rooms.get('countdown', set())),
            'order': len(rooms.get('order', set())),
        }

    # Include active reservations count (refreshed every broadcast cycle)
    try:
        from modules.exclusive.models import ExclusiveReservation
        from modules.exclusive.reservation import cleanup_expired_reservations
        cleanup_expired_reservations(page_id)
        counts['active_reservations'] = ExclusiveReservation.query.filter_by(
            exclusive_page_id=page_id
        ).count()
    except Exception:
        pass

    return counts


def _broadcast_visitor_counts(page_id):
    """Send visitor count update to admin room."""
    counts = _get_visitor_counts(page_id)
    admin_room = _get_admin_room(page_id)
    socketio.emit('visitor_count_update', counts, to=admin_room)


# Background thread for periodic visitor count broadcasts
_broadcast_threads = {}
_broadcast_stop_events = {}


def _start_broadcast_thread(page_id):
    """Start a background thread that broadcasts visitor counts every 5 seconds."""
    if page_id in _broadcast_threads and _broadcast_threads[page_id].is_alive():
        return

    stop_event = threading.Event()
    _broadcast_stop_events[page_id] = stop_event

    # Capture app for context in background thread (needed for DB queries)
    from flask import current_app
    app = current_app._get_current_object()

    def _broadcast_loop():
        while not stop_event.is_set():
            with app.app_context():
                _broadcast_visitor_counts(page_id)
            stop_event.wait(5)

    thread = threading.Thread(target=_broadcast_loop, daemon=True)
    _broadcast_threads[page_id] = thread
    thread.start()


def _stop_broadcast_thread(page_id):
    """Stop the broadcast thread for a page if no admins remain."""
    with _admin_lock:
        if page_id in _admin_rooms and len(_admin_rooms[page_id]) > 0:
            return

    stop_event = _broadcast_stop_events.pop(page_id, None)
    if stop_event:
        stop_event.set()
    _broadcast_threads.pop(page_id, None)


# ====================
# EVENT HANDLERS
# ====================


@socketio.on('join_exclusive')
def handle_join_exclusive(data):
    """
    Client (visitor) joins an exclusive page room.
    Used for tracking visitor counts on countdown and order pages.

    Data: { page_id: int, page_type: 'countdown'|'order' }
    """
    page_id = data.get('page_id')
    page_type = data.get('page_type')
    sid = flask_request.sid

    if not page_id or page_type not in ('countdown', 'order'):
        emit('error', {'message': 'Invalid page_id or page_type'})
        return

    room = _get_visitor_room(page_id, page_type)
    join_room(room)

    # Track visitor
    with _visitor_lock:
        if page_id not in _visitor_rooms:
            _visitor_rooms[page_id] = {'countdown': set(), 'order': set()}
        _visitor_rooms[page_id][page_type].add(sid)

    _connected_clients[sid] = {'page_id': page_id, 'role': page_type}

    # Broadcast updated counts to admin
    _broadcast_visitor_counts(page_id)


@socketio.on('join_exclusive_admin')
def handle_join_exclusive_admin(data):
    """
    Admin joins the LIVE dashboard room for a page.

    Data: { page_id: int }
    """
    page_id = data.get('page_id')
    sid = flask_request.sid

    if not page_id:
        emit('error', {'message': 'Invalid page_id'})
        return

    room = _get_admin_room(page_id)
    join_room(room)

    # Track admin
    with _admin_lock:
        if page_id not in _admin_rooms:
            _admin_rooms[page_id] = set()
        _admin_rooms[page_id].add(sid)

    _connected_clients[sid] = {'page_id': page_id, 'role': 'admin'}

    # Send initial visitor counts
    counts = _get_visitor_counts(page_id)
    emit('visitor_count_update', counts)

    # Start periodic broadcast if not already running
    _start_broadcast_thread(page_id)


def handle_exclusive_disconnect(sid=None):
    """
    Handle client disconnect — remove from tracking and update counts.
    Called from wms_events.py's central disconnect handler (no decorator here
    to avoid overwriting WMS's @socketio.on('disconnect')).
    """
    if sid is None:
        sid = flask_request.sid
    client = _connected_clients.pop(sid, None)
    if not client:
        return

    page_id = client['page_id']
    role = client['role']

    if role in ('countdown', 'order'):
        # Remove visitor
        with _visitor_lock:
            if page_id in _visitor_rooms and role in _visitor_rooms[page_id]:
                _visitor_rooms[page_id][role].discard(sid)

                # Cleanup empty sets
                if (not _visitor_rooms[page_id]['countdown'] and
                        not _visitor_rooms[page_id]['order']):
                    del _visitor_rooms[page_id]

        # Broadcast updated counts
        _broadcast_visitor_counts(page_id)

    elif role == 'admin':
        # Remove admin
        with _admin_lock:
            if page_id in _admin_rooms:
                _admin_rooms[page_id].discard(sid)
                if not _admin_rooms[page_id]:
                    del _admin_rooms[page_id]

        # Stop broadcast thread if no admins left
        _stop_broadcast_thread(page_id)


def emit_new_order(page_id, order_data):
    """
    Emit a new order event to the admin LIVE dashboard room.
    Called from place_order.py after successful order creation.

    Args:
        page_id: Exclusive page ID
        order_data: dict with order details
    """
    admin_room = _get_admin_room(page_id)
    socketio.emit('new_order', order_data, to=admin_room)


def emit_stats_update(page_id, stats_data):
    """
    Emit updated stats to the admin LIVE dashboard room.
    Called from place_order.py after successful order creation.

    Args:
        page_id: Exclusive page ID
        stats_data: dict with updated statistics
    """
    admin_room = _get_admin_room(page_id)
    socketio.emit('stats_update', stats_data, to=admin_room)


def emit_reservations_update(page_id):
    """
    Emit updated reservation counts per product to the admin LIVE dashboard.
    Called from routes.py after reserve/release actions.

    Args:
        page_id: Exclusive page ID
    """
    import time as _time
    from extensions import db
    from modules.exclusive.models import ExclusiveReservation

    now_ts = int(_time.time())
    reservations = {}
    rows = db.session.query(
        ExclusiveReservation.product_id,
        db.func.sum(ExclusiveReservation.quantity)
    ).filter(
        ExclusiveReservation.exclusive_page_id == page_id,
        ExclusiveReservation.expires_at > now_ts
    ).group_by(ExclusiveReservation.product_id).all()

    for pid, qty in rows:
        reservations[pid] = int(qty)

    total = sum(reservations.values())

    admin_room = _get_admin_room(page_id)
    socketio.emit('reservations_update', {
        'by_product': reservations,
        'total': total,
    }, to=admin_room)
