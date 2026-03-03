"""
Exclusive Module - SocketIO Event Handlers
==========================================

Real-time WebSocket events dla stron Exclusive:
- Zliczanie odwiedzających (countdown/order pages) + admin dashboard
- System rezerwacji w czasie rzeczywistym (reserve/release/extend)
- Broadcast dostępności produktów do kupujących
- Server-side expiry timer dla rezerwacji
- Push powiadomienia "Powiadom mnie" o dostępności produktu
"""

import time
import threading
from flask import request as flask_request
from flask_socketio import join_room, leave_room, emit

from extensions import socketio

# =============================================
# STRUKTURY TRACKINGU POŁĄCZEŃ
# =============================================

# Tracking odwiedzających per strona exclusive
# Struktura: { page_id: { 'countdown': set(sid), 'order': set(sid) } }
_visitor_rooms = {}
_visitor_lock = threading.Lock()

# Połączenia adminów per strona
# Struktura: { page_id: set(sid) }
_admin_rooms = {}
_admin_lock = threading.Lock()

# Mapping sid → { page_id, role ('countdown'|'order'|'admin'|'reservation') }
_connected_clients = {}

# Deduplikacja rezerwacji: (page_id, session_id) → sid
_reservation_sessions = {}
# Deduplikacja po user_id: (page_id, user_id) → sid
_user_sessions = {}
_reservation_lock = threading.RLock()  # RLock — reentrant, bo _cleanup_reservation_client też go używa

# =============================================
# EXPIRY TIMER — wygaszanie rezerwacji
# =============================================

# { page_id: threading.Timer }
_expiry_timers = {}
_expiry_lock = threading.Lock()

# Ostatnia znana dostępność per strona (do detekcji zmian w powiadomieniach)
_last_availability = {}


# =============================================
# HELPERY ROOMÓW
# =============================================

def _get_visitor_room(page_id, page_type):
    """Zwraca nazwę rooma dla odwiedzających stronę exclusive."""
    return f'exclusive_{page_id}_{page_type}'


def _get_admin_room(page_id):
    """Zwraca nazwę rooma dla admin LIVE dashboard."""
    return f'exclusive_admin_{page_id}'


# =============================================
# ZLICZANIE ODWIEDZAJĄCYCH (BEZ ZMIAN)
# =============================================

def _get_visitor_counts(page_id):
    """Pobiera liczbę odwiedzających i aktywnych rezerwacji dla strony."""
    with _visitor_lock:
        rooms = _visitor_rooms.get(page_id, {})
        counts = {
            'countdown': len(rooms.get('countdown', set())),
            'order': len(rooms.get('order', set())),
        }

    # Aktywne rezerwacje (odświeżane przy każdym cyklu broadcastu)
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
    """Wysyła update liczby odwiedzających do rooma admina."""
    counts = _get_visitor_counts(page_id)
    admin_room = _get_admin_room(page_id)
    socketio.emit('visitor_count_update', counts, to=admin_room)


# Wątek broadcastu odwiedzających (periodic, co 5s)
_broadcast_threads = {}
_broadcast_stop_events = {}


def _start_broadcast_thread(page_id):
    """Uruchamia wątek broadcastu liczby odwiedzających co 5 sekund."""
    if page_id in _broadcast_threads and _broadcast_threads[page_id].is_alive():
        return

    stop_event = threading.Event()
    _broadcast_stop_events[page_id] = stop_event

    # Przechwycenie app context dla wątku tła (potrzebne do DB queries)
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
    """Zatrzymuje wątek broadcastu jeśli nie ma więcej adminów."""
    with _admin_lock:
        if page_id in _admin_rooms and len(_admin_rooms[page_id]) > 0:
            return

    stop_event = _broadcast_stop_events.pop(page_id, None)
    if stop_event:
        stop_event.set()
    _broadcast_threads.pop(page_id, None)


# =============================================
# BROADCAST DOSTĘPNOŚCI PRODUKTÓW
# =============================================

def broadcast_availability_update(page_id):
    """
    Emituje 'availability_updated' do rooma kupujących.

    Dane są globalne (nie per-user) — klient śledzi swój user_reserved
    z lokalnego stanu koszyka.

    Wywoływana po: reserve, release, extend, order placed, expiry timer.
    """
    from modules.exclusive.reservation import (
        get_section_products_map, cleanup_expired_reservations
    )
    from modules.exclusive.models import ExclusiveReservation
    from modules.orders.models import Order, OrderItem
    from extensions import db
    from sqlalchemy import func

    cleanup_expired_reservations(page_id)

    section_products = get_section_products_map(page_id)
    now = int(time.time())
    products_data = {}

    for product_id, section_max in section_products.items():
        # Suma zarezerwowanych (wszystkich)
        total_reserved = db.session.query(
            func.sum(ExclusiveReservation.quantity)
        ).filter(
            ExclusiveReservation.exclusive_page_id == page_id,
            ExclusiveReservation.product_id == product_id,
            ExclusiveReservation.expires_at > now
        ).scalar() or 0

        # Suma zamówionych (permanentne)
        total_ordered = db.session.query(
            func.sum(OrderItem.quantity)
        ).join(Order).filter(
            Order.exclusive_page_id == page_id,
            Order.status != 'anulowane',
            OrderItem.product_id == product_id
        ).scalar() or 0

        if section_max and section_max > 0:
            available = max(0, section_max - int(total_reserved) - int(total_ordered))
        else:
            available = 999999  # Bez limitu

        products_data[str(product_id)] = {
            'available': available,
            'total_reserved': int(total_reserved),
            'total_ordered': int(total_ordered),
        }

    room = _get_visitor_room(page_id, 'order')
    socketio.emit('availability_updated', {
        'products': products_data,
        'timestamp': int(time.time()),
    }, to=room)

    # Sprawdź subskrypcje powiadomień (dostępność wróciła)
    _check_notification_subscriptions(page_id, products_data)


def _check_notification_subscriptions(page_id, current_availability):
    """
    Sprawdza czy produkty, które były niedostępne, stały się ponownie dostępne.
    Jeśli tak — wysyła SocketIO push lub email fallback.
    """
    global _last_availability

    old = _last_availability.get(page_id, {})
    _last_availability[page_id] = current_availability

    if not old:
        return  # Pierwsza iteracja — brak porównania

    newly_available = []
    for product_id_str, data in current_availability.items():
        old_data = old.get(product_id_str, {})
        old_avail = old_data.get('available', 0)
        new_avail = data.get('available', 0)

        if old_avail <= 0 and new_avail > 0:
            newly_available.append(int(product_id_str))

    if not newly_available:
        return

    try:
        from modules.exclusive.models import ExclusiveProductNotificationSubscription
        from modules.products.models import Product

        subscriptions = ExclusiveProductNotificationSubscription.query.filter(
            ExclusiveProductNotificationSubscription.exclusive_page_id == page_id,
            ExclusiveProductNotificationSubscription.product_id.in_(newly_available),
            ExclusiveProductNotificationSubscription.notified == False
        ).all()

        if not subscriptions:
            return

        # Cache nazw produktów
        products = {p.id: p.name for p in Product.query.filter(
            Product.id.in_(newly_available)
        ).all()}

        for sub in subscriptions:
            product_name = products.get(sub.product_id, 'Produkt')
            user_sid = None

            # Sprawdź czy user ma aktywne połączenie SocketIO
            if sub.user_id:
                key = (page_id, sub.user_id)
                with _reservation_lock:
                    user_sid = _user_sessions.get(key)

            if user_sid and user_sid in _connected_clients:
                # Push SocketIO — user jest na stronie
                socketio.emit('product_available', {
                    'product_id': sub.product_id,
                    'product_name': product_name,
                    'available': current_availability[str(sub.product_id)]['available'],
                }, to=user_sid)
                sub.notified = True
            else:
                # Email fallback — user nie jest na stronie
                try:
                    from utils.email_sender import send_back_in_stock_email
                    from modules.exclusive.models import ExclusivePage
                    from flask import url_for

                    email = sub.guest_email
                    if not email and sub.user_id:
                        from modules.auth.models import User
                        user = User.query.get(sub.user_id)
                        if user:
                            email = user.email

                    if email:
                        page = ExclusivePage.query.get(page_id)
                        page_name = page.name if page else 'Exclusive'
                        page_url = ''
                        try:
                            page_url = url_for('exclusive.order_page',
                                               token=page.token, _external=True) if page else ''
                        except RuntimeError:
                            pass

                        send_back_in_stock_email(
                            email=email,
                            product_name=product_name,
                            product_image_url=None,
                            exclusive_page_name=page_name,
                            exclusive_page_url=page_url
                        )
                        sub.notified = True
                except Exception as e:
                    print(f"[NOTIFICATIONS] Email fallback error: {e}")

        from extensions import db
        db.session.commit()
    except Exception as e:
        print(f"[NOTIFICATIONS] Check subscriptions error: {e}")


# =============================================
# SERVER-SIDE EXPIRY TIMER
# =============================================

def _schedule_expiry_timer(page_id):
    """
    Planuje timer wygaśnięcia dla najbliższej rezerwacji na stronie.

    Po wygaśnięciu — czyści rezerwacje i broadcastuje nową dostępność.
    """
    from modules.exclusive.models import ExclusiveReservation
    from flask import current_app

    app = current_app._get_current_object()

    with _expiry_lock:
        # Anuluj istniejący timer
        old_timer = _expiry_timers.pop(page_id, None)
        if old_timer:
            old_timer.cancel()

        # Znajdź najbliższe wygaśnięcie
        now = int(time.time())
        earliest = ExclusiveReservation.query.filter(
            ExclusiveReservation.exclusive_page_id == page_id,
            ExclusiveReservation.expires_at > now
        ).order_by(ExclusiveReservation.expires_at.asc()).first()

        if not earliest:
            return  # Brak aktywnych rezerwacji

        delay = max(1, earliest.expires_at - now)

        timer = threading.Timer(delay, _on_expiry_fired, [page_id, app])
        timer.daemon = True
        timer.start()
        _expiry_timers[page_id] = timer


def _on_expiry_fired(page_id, app):
    """
    Callback gdy timer wygaśnięcia się odpala.

    Czyści wygasłe rezerwacje, broadcastuje dostępność,
    i planuje następny timer.
    """
    try:
        with app.app_context():
            from modules.exclusive.reservation import cleanup_expired_reservations
            cleanup_expired_reservations(page_id)
            broadcast_availability_update(page_id)
            # Zaplanuj timer dla następnego wygaśnięcia
            _schedule_expiry_timer_internal(page_id, app)
    except Exception as e:
        print(f"[EXPIRY TIMER] Error for page {page_id}: {e}")


def _schedule_expiry_timer_internal(page_id, app):
    """
    Wewnętrzna wersja _schedule_expiry_timer — nie wymaga current_app
    (używana z wątku tła, gdzie app jest już przekazane).
    """
    from modules.exclusive.models import ExclusiveReservation

    with _expiry_lock:
        old_timer = _expiry_timers.pop(page_id, None)
        if old_timer:
            old_timer.cancel()

        now = int(time.time())
        earliest = ExclusiveReservation.query.filter(
            ExclusiveReservation.exclusive_page_id == page_id,
            ExclusiveReservation.expires_at > now
        ).order_by(ExclusiveReservation.expires_at.asc()).first()

        if not earliest:
            return

        delay = max(1, earliest.expires_at - now)

        timer = threading.Timer(delay, _on_expiry_fired, [page_id, app])
        timer.daemon = True
        timer.start()
        _expiry_timers[page_id] = timer


# =============================================
# EVENT HANDLERS — ISTNIEJĄCE (visitor + admin)
# =============================================

@socketio.on('join_exclusive')
def handle_join_exclusive(data):
    """
    Klient (odwiedzający) dołącza do rooma strony exclusive.
    Używane do zliczania odwiedzających na stronach countdown i order.

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

    # Śledzenie odwiedzających
    with _visitor_lock:
        if page_id not in _visitor_rooms:
            _visitor_rooms[page_id] = {'countdown': set(), 'order': set()}
        _visitor_rooms[page_id][page_type].add(sid)

    _connected_clients[sid] = {'page_id': page_id, 'role': page_type}

    # Broadcast zaktualizowanych liczb do admina
    _broadcast_visitor_counts(page_id)


@socketio.on('join_exclusive_admin')
def handle_join_exclusive_admin(data):
    """
    Admin dołącza do rooma LIVE dashboard.

    Data: { page_id: int }
    """
    page_id = data.get('page_id')
    sid = flask_request.sid

    if not page_id:
        emit('error', {'message': 'Invalid page_id'})
        return

    room = _get_admin_room(page_id)
    join_room(room)

    # Śledzenie adminów
    with _admin_lock:
        if page_id not in _admin_rooms:
            _admin_rooms[page_id] = set()
        _admin_rooms[page_id].add(sid)

    _connected_clients[sid] = {'page_id': page_id, 'role': 'admin'}

    # Wyślij początkowe statystyki odwiedzających
    counts = _get_visitor_counts(page_id)
    emit('visitor_count_update', counts)

    # Uruchom periodyczny broadcast jeśli nie działa
    _start_broadcast_thread(page_id)


# =============================================
# EVENT HANDLERS — NOWE (rezerwacja SocketIO)
# =============================================

@socketio.on('join_exclusive_reservation')
def handle_join_exclusive_reservation(data):
    """
    Klient dołącza do systemu rezerwacji exclusive (z deduplikacją).

    Data: { page_id, session_id, user_id (or null), token }
    Return (ack): { success, products: {...}, session: {...} }
    """
    try:
        from modules.exclusive.models import ExclusivePage
        from modules.exclusive.reservation import (
            get_availability_snapshot, get_section_products_map
        )

        page_id = data.get('page_id')
        session_id = data.get('session_id')
        user_id = data.get('user_id')
        token = data.get('token')
        sid = flask_request.sid

        if not page_id or not session_id or not token:
            return {'success': False, 'error': 'missing_params'}

        # Safety net: blokada rezerwacji dla niezalogowanych
        if not user_id:
            return {'success': False, 'error': 'login_required'}

        # Normalizacja typów (JS może wysłać string lub int)
        page_id = int(page_id)
        if user_id:
            user_id = int(user_id)

        # Walidacja tokena strony
        page = ExclusivePage.get_by_token(token)
        if not page or page.id != page_id or not page.is_active:
            return {'success': False, 'error': 'invalid_page'}

        with _reservation_lock:
            # Sprawdź duplikat po session_id
            session_key = (page_id, session_id)
            old_sid = _reservation_sessions.get(session_key)
            if old_sid and old_sid != sid and old_sid in _connected_clients:
                socketio.emit('force_disconnect', {
                    'reason': 'Sesja została przejęta w innej karcie.'
                }, to=old_sid)
                _cleanup_reservation_client(old_sid)

            # Sprawdź duplikat po user_id (zalogowany user)
            if user_id:
                user_key = (page_id, user_id)
                old_user_sid = _user_sessions.get(user_key)
                if old_user_sid and old_user_sid != sid and old_user_sid in _connected_clients:
                    socketio.emit('force_disconnect', {
                        'reason': 'Sesja została przejęta w innej karcie.'
                    }, to=old_user_sid)
                    _cleanup_reservation_client(old_user_sid)

            # Rejestracja nowej sesji
            _reservation_sessions[session_key] = sid
            if user_id:
                _user_sessions[(page_id, user_id)] = sid

        # Dołącz do rooma
        room = _get_visitor_room(page_id, 'order')
        join_room(room)

        # Śledzenie (nadpisz jeśli był visitor)
        _connected_clients[sid] = {
            'page_id': page_id,
            'role': 'reservation',
            'session_id': session_id,
            'user_id': user_id,
        }

        # Śledzenie odwiedzających (reuse handle_join_exclusive)
        with _visitor_lock:
            if page_id not in _visitor_rooms:
                _visitor_rooms[page_id] = {'countdown': set(), 'order': set()}
            _visitor_rooms[page_id]['order'].add(sid)

        _broadcast_visitor_counts(page_id)

        # Pobierz snapshot dostępności
        section_products = get_section_products_map(page_id)
        products_data, session_info = get_availability_snapshot(
            page_id=page_id,
            section_products=section_products,
            session_id=session_id
        )

        # Uruchom expiry timer jeśli są aktywne rezerwacje
        if session_info.get('has_reservations'):
            try:
                _schedule_expiry_timer(page_id)
            except Exception:
                pass

        return {
            'success': True,
            'products': products_data,
            'session': session_info,
        }

    except Exception as e:
        import traceback
        print(f"[SOCKET] join_exclusive_reservation ERROR: {e}")
        traceback.print_exc()
        return {'success': False, 'error': 'server_error', 'message': str(e)}


@socketio.on('reserve_product')
def handle_reserve_product(data):
    """
    Rezerwuje produkt przez SocketIO (z ack callback).

    Data: { page_id, session_id, product_id, quantity }
    Return (ack): { success, reservation: {...}, available_quantity, error? }
    """
    from modules.exclusive.reservation import (
        reserve_product, get_section_max_for_product
    )

    page_id = data.get('page_id')
    session_id = data.get('session_id')
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)
    sid = flask_request.sid

    if not page_id or not session_id or not product_id:
        return {'success': False, 'error': 'missing_params'}

    # Normalizacja typów (JS może wysłać string)
    page_id = int(page_id)
    product_id = int(product_id)
    quantity = int(quantity)

    # Walidacja — czy ten sid jest zarejestrowany
    client = _connected_clients.get(sid)
    if not client or client.get('role') != 'reservation':
        return {'success': False, 'error': 'not_connected'}

    # Safety net: blokada rezerwacji dla niezalogowanych
    if not client.get('user_id'):
        return {'success': False, 'error': 'login_required'}

    try:
        # Oblicz section_max
        section_max = get_section_max_for_product(page_id, product_id)

        # Wywołaj istniejącą logikę rezerwacji (SELECT FOR UPDATE)
        success, result = reserve_product(
            session_id=session_id,
            page_id=page_id,
            product_id=product_id,
            quantity=quantity,
            section_max=section_max
        )

        if success:
            # Broadcast nowej dostępności do wszystkich kupujących
            broadcast_availability_update(page_id)
            # Aktualizuj admin dashboard
            emit_reservations_update(page_id)
            # Zaplanuj/aktualizuj expiry timer
            try:
                _schedule_expiry_timer(page_id)
            except Exception:
                pass

        return {'success': success, **result}

    except Exception as e:
        import traceback
        print(f"[SOCKET] reserve_product ERROR: {e}")
        traceback.print_exc()
        return {'success': False, 'error': 'server_error', 'message': str(e)}


@socketio.on('release_product')
def handle_release_product(data):
    """
    Zwalnia rezerwację produktu przez SocketIO.

    Data: { page_id, session_id, product_id, quantity }
    """
    from modules.exclusive.reservation import release_product

    page_id = data.get('page_id')
    session_id = data.get('session_id')
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)
    sid = flask_request.sid

    if not page_id or not session_id or not product_id:
        return

    # Normalizacja typów
    page_id = int(page_id)
    product_id = int(product_id)
    quantity = int(quantity)

    client = _connected_clients.get(sid)
    if not client or client.get('role') != 'reservation':
        return

    success, result = release_product(
        session_id=session_id,
        page_id=page_id,
        product_id=product_id,
        quantity=quantity
    )

    if success:
        broadcast_availability_update(page_id)
        emit_reservations_update(page_id)


@socketio.on('extend_reservation')
def handle_extend_reservation(data):
    """
    Przedłuża rezerwację przez SocketIO (z ack callback).

    Data: { page_id, session_id }
    Return (ack): { success, new_expires_at, error? }
    """
    from modules.exclusive.reservation import extend_reservation

    page_id = data.get('page_id')
    session_id = data.get('session_id')
    sid = flask_request.sid

    if not page_id or not session_id:
        return {'success': False, 'error': 'missing_params'}

    # Normalizacja typów
    page_id = int(page_id)

    client = _connected_clients.get(sid)
    if not client or client.get('role') != 'reservation':
        return {'success': False, 'error': 'not_connected'}

    success, result = extend_reservation(
        session_id=session_id,
        page_id=page_id
    )

    if success:
        broadcast_availability_update(page_id)
        # Przelicz expiry timer
        try:
            _schedule_expiry_timer(page_id)
        except Exception:
            pass

    return {'success': success, **result}


# =============================================
# ADMIN PUSH — status strony i deadline
# =============================================

def broadcast_page_status(page_id, status, ends_at=None):
    """
    Emituje zmianę statusu strony do kupujących.

    Wywoływane z admin routes po zmianie statusu/deadline.
    """
    room = _get_visitor_room(page_id, 'order')
    socketio.emit('page_status_changed', {
        'status': status,
        'is_active': status == 'active',
        'is_manually_closed': status in ('ended', 'paused'),
    }, to=room)

    if ends_at is not None:
        socketio.emit('deadline_changed', {
            'ends_at': ends_at,
        }, to=room)


# =============================================
# DISCONNECT HANDLER (rozszerzony)
# =============================================

def _cleanup_reservation_client(sid):
    """
    Czyści struktury trackingu dla danego sid (rezerwacja).

    Uwaga: disconnect NIE usuwa rezerwacji z bazy —
    wygasają naturalnie po expires_at.
    """
    client = _connected_clients.pop(sid, None)
    if not client:
        return

    page_id = client.get('page_id')
    role = client.get('role')

    # Cleanup z dedup map
    if role == 'reservation':
        session_id = client.get('session_id')
        user_id = client.get('user_id')

        with _reservation_lock:
            if session_id:
                key = (page_id, session_id)
                if _reservation_sessions.get(key) == sid:
                    del _reservation_sessions[key]

            if user_id:
                key = (page_id, user_id)
                if _user_sessions.get(key) == sid:
                    del _user_sessions[key]

    # Cleanup visitor tracking (usunięcie z licznika odwiedzających)
    if page_id:
        room_role = 'order' if role == 'reservation' else role
        if room_role in ('countdown', 'order'):
            with _visitor_lock:
                if page_id in _visitor_rooms and room_role in _visitor_rooms[page_id]:
                    _visitor_rooms[page_id][room_role].discard(sid)

                    if (not _visitor_rooms[page_id].get('countdown') and
                            not _visitor_rooms[page_id].get('order')):
                        del _visitor_rooms[page_id]


def handle_exclusive_disconnect(sid=None):
    """
    Obsługa rozłączenia klienta — usunięcie z trackingu i update statystyk.

    Wywoływane z centralnego disconnect handlera w wms_events.py
    (bez dekoratora @socketio.on('disconnect'), żeby nie nadpisać WMS).
    """
    if sid is None:
        sid = flask_request.sid
    client = _connected_clients.get(sid)
    if not client:
        return

    page_id = client['page_id']
    role = client['role']

    if role == 'reservation':
        # Cleanup dedup map + visitor rooms (oba w _cleanup_reservation_client)
        _cleanup_reservation_client(sid)
        _broadcast_visitor_counts(page_id)

    elif role in ('countdown', 'order'):
        # Usunięcie odwiedzającego — _cleanup_reservation_client obsługuje visitor rooms
        _cleanup_reservation_client(sid)
        _broadcast_visitor_counts(page_id)

    elif role == 'admin':
        # Usunięcie admina
        _connected_clients.pop(sid, None)
        with _admin_lock:
            if page_id in _admin_rooms:
                _admin_rooms[page_id].discard(sid)
                if not _admin_rooms[page_id]:
                    del _admin_rooms[page_id]

        # Zatrzymaj broadcast jeśli brak adminów
        _stop_broadcast_thread(page_id)


# =============================================
# EMIT HELPERS (wywoływane z innych modułów)
# =============================================

def emit_new_order(page_id, order_data):
    """
    Emituje event nowego zamówienia do admin LIVE dashboard.
    Wywoływane z place_order.py po złożeniu zamówienia.
    """
    admin_room = _get_admin_room(page_id)
    socketio.emit('new_order', order_data, to=admin_room)


def emit_stats_update(page_id, stats_data):
    """
    Emituje zaktualizowane statystyki do admin LIVE dashboard.
    Wywoływane z place_order.py po złożeniu zamówienia.
    """
    admin_room = _get_admin_room(page_id)
    socketio.emit('stats_update', stats_data, to=admin_room)


def emit_reservations_update(page_id):
    """
    Emituje zaktualizowane liczby rezerwacji per produkt do admin LIVE dashboard.
    Wywoływane z routes.py po akcjach reserve/release.
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
