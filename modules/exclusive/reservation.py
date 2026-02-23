"""
Exclusive Reservation Logic
Logika systemu rezerwacji produktów na stronach exclusive
"""

import time
from flask import request
from sqlalchemy import func
from modules.exclusive.models import ExclusiveReservation
from modules.products.models import Product
from extensions import db

# Stałe
RESERVATION_DURATION = 600  # 10 minut w sekundach
EXTENSION_DURATION = 120    # 2 minuty w sekundach


def cleanup_expired_reservations(page_id, auto_commit=True):
    """
    Lazy cleanup - usuwa wygasłe rezerwacje dla danej strony exclusive

    Args:
        page_id: ID strony exclusive
        auto_commit: Czy commitować od razu (False gdy wywołane wewnątrz większej transakcji)

    Returns:
        int: Liczba usuniętych rezerwacji
    """
    now = int(time.time())
    deleted = ExclusiveReservation.query.filter(
        ExclusiveReservation.exclusive_page_id == page_id,
        ExclusiveReservation.expires_at < now
    ).delete()
    if auto_commit:
        db.session.commit()
    else:
        db.session.flush()
    return deleted


def get_first_reservation_time(session_id, page_id):
    """
    Pobiera czas pierwszej rezerwacji sesji (dla timera)

    Args:
        session_id: UUID sesji
        page_id: ID strony exclusive

    Returns:
        int: UNIX timestamp pierwszej rezerwacji lub None
    """
    reservation = ExclusiveReservation.query.filter_by(
        session_id=session_id,
        exclusive_page_id=page_id
    ).order_by(ExclusiveReservation.reserved_at).first()

    return reservation.reserved_at if reservation else None


def get_available_quantity(page_id, product_id, section_max=None, auto_commit=True):
    """
    Oblicza dostępną ilość produktu (rezerwacje + już złożone zamówienia)

    Args:
        page_id: ID strony exclusive
        product_id: ID produktu
        section_max: max_quantity z sekcji exclusive (może być None dla unlimited)
        auto_commit: Czy cleanup ma commitować (False w transakcji)

    Returns:
        int: Dostępna ilość (może być float('inf') dla unlimited)
    """
    from modules.orders.models import Order, OrderItem

    # Usuń wygasłe rezerwacje
    cleanup_expired_reservations(page_id, auto_commit=auto_commit)

    now = int(time.time())

    # Suma zarezerwowanych (aktywnych)
    reserved = db.session.query(
        func.sum(ExclusiveReservation.quantity)
    ).filter(
        ExclusiveReservation.exclusive_page_id == page_id,
        ExclusiveReservation.product_id == product_id,
        ExclusiveReservation.expires_at > now
    ).scalar() or 0

    # Suma już zamówionych (złożone zamówienia, bez anulowanych)
    ordered = db.session.query(
        func.sum(OrderItem.quantity)
    ).join(Order).filter(
        Order.exclusive_page_id == page_id,
        Order.status != 'anulowane',
        OrderItem.product_id == product_id
    ).scalar() or 0

    # Jeśli jest limit sekcji, odejmij rezerwacje I zamówienia
    if section_max is not None and section_max > 0:
        available = section_max - reserved - ordered
    else:
        available = float('inf')  # Unlimited

    return max(0, available)


def get_user_reservation(session_id, page_id, product_id):
    """
    Pobiera rezerwację użytkownika dla produktu

    Args:
        session_id: UUID sesji
        page_id: ID strony exclusive
        product_id: ID produktu

    Returns:
        ExclusiveReservation: Obiekt rezerwacji lub None
    """
    return ExclusiveReservation.query.filter_by(
        session_id=session_id,
        exclusive_page_id=page_id,
        product_id=product_id
    ).first()


def reserve_product(session_id, page_id, product_id, quantity, section_max=None):
    """
    Rezerwuje produkt (atomowo z row-level locking)

    Cała operacja (cleanup + check + reserve) odbywa się w jednej transakcji.
    SELECT FOR UPDATE lockuje wiersze rezerwacji dla danego produktu,
    zapobiegając race condition przy jednoczesnych rezerwacjach.

    Args:
        session_id: UUID sesji
        page_id: ID strony exclusive
        product_id: ID produktu
        quantity: Ilość do zarezerwowania
        section_max: max_quantity z sekcji (None dla unlimited)

    Returns:
        tuple: (success: bool, data: dict)
    """
    from modules.orders.models import Order, OrderItem

    try:
        now = int(time.time())

        # --- JEDNA TRANSAKCJA: cleanup + check + reserve ---

        # 1. Cleanup expired (bez commit - flush only)
        cleanup_expired_reservations(page_id, auto_commit=False)

        # 2. Lockuj aktywne rezerwacje dla tego produktu (SELECT FOR UPDATE)
        #    Inne requesty czekają aż ta transakcja się zakończy
        locked_reservations = ExclusiveReservation.query.filter(
            ExclusiveReservation.exclusive_page_id == page_id,
            ExclusiveReservation.product_id == product_id,
            ExclusiveReservation.expires_at > now
        ).with_for_update().all()

        # 3. Oblicz dostępność na podstawie zlockowanych danych
        reserved = sum(r.quantity for r in locked_reservations)

        # Suma już zamówionych (złożone zamówienia, bez anulowanych)
        ordered = db.session.query(
            func.sum(OrderItem.quantity)
        ).join(Order).filter(
            Order.exclusive_page_id == page_id,
            Order.status != 'anulowane',
            OrderItem.product_id == product_id
        ).scalar() or 0

        if section_max is not None and section_max > 0:
            available = max(0, section_max - reserved - ordered)
        else:
            available = float('inf')

        # 4. Sprawdź czy jest wystarczająco
        user_reservation = None
        for r in locked_reservations:
            if r.session_id == session_id:
                user_reservation = r
                break

        if available < quantity:
            # Niewystarczająca dostępność - rollback locka
            db.session.rollback()

            earliest_expiry = min(
                (r.expires_at for r in locked_reservations if r.session_id != session_id),
                default=None
            )

            available_qty = int(available) if available != float('inf') else 999999
            return False, {
                'error': 'insufficient_availability',
                'message': 'Ten produkt został już zarezerwowany przez innych użytkowników.',
                'available_quantity': available_qty,
                'check_back_at': earliest_expiry
            }

        # 5. Oblicz czas wygaśnięcia
        first_reserved_at = get_first_reservation_time(session_id, page_id)
        if not first_reserved_at:
            first_reserved_at = int(time.time())

        extended_reservation = ExclusiveReservation.query.filter_by(
            session_id=session_id,
            exclusive_page_id=page_id,
            extended=True
        ).first()

        if extended_reservation:
            expires_at = extended_reservation.expires_at
        else:
            expires_at = first_reserved_at + RESERVATION_DURATION

        # 6. UPSERT rezerwacji
        if user_reservation:
            user_reservation.quantity += quantity
            user_reservation.expires_at = expires_at
        else:
            user_reservation = ExclusiveReservation(
                session_id=session_id,
                exclusive_page_id=page_id,
                product_id=product_id,
                quantity=quantity,
                reserved_at=first_reserved_at,
                expires_at=expires_at,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', '')
            )
            db.session.add(user_reservation)

        # 7. COMMIT - koniec transakcji, zwolnienie locków
        db.session.commit()

        remaining_available = available - quantity
        if remaining_available == float('inf'):
            remaining_available = 999999

        return True, {
            'reservation': {
                'session_id': session_id,
                'product_id': product_id,
                'quantity': user_reservation.quantity,
                'reserved_at': user_reservation.reserved_at,
                'expires_at': user_reservation.expires_at,
                'first_reservation_at': first_reserved_at
            },
            'available_quantity': int(remaining_available)
        }

    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"[RESERVE ERROR] {e}")
        traceback.print_exc()
        return False, {
            'error': 'server_error',
            'message': 'Wystąpił błąd serwera. Spróbuj ponownie.'
        }


def release_product(session_id, page_id, product_id, quantity):
    """
    Zwalnia rezerwację produktu

    Args:
        session_id: UUID sesji
        page_id: ID strony exclusive
        product_id: ID produktu
        quantity: Ilość do zwolnienia

    Returns:
        tuple: (success: bool, data: dict)
    """
    user_reservation = get_user_reservation(session_id, page_id, product_id)

    if not user_reservation:
        return True, {'reservation': {'quantity': 0}}

    user_reservation.quantity -= quantity

    if user_reservation.quantity <= 0:
        db.session.delete(user_reservation)

    db.session.commit()

    return True, {
        'reservation': {
            'quantity': max(0, user_reservation.quantity if user_reservation.quantity > 0 else 0)
        }
    }


def extend_reservation(session_id, page_id):
    """
    Przedłuża rezerwację o 2 minuty (jednokrotnie)

    Args:
        session_id: UUID sesji
        page_id: ID strony exclusive

    Returns:
        tuple: (success: bool, data: dict)
    """
    reservations = ExclusiveReservation.query.filter_by(
        session_id=session_id,
        exclusive_page_id=page_id
    ).all()

    if not reservations:
        return False, {
            'error': 'no_reservations',
            'message': 'Brak aktywnych rezerwacji.'
        }

    # Check if already extended
    if any(r.extended for r in reservations):
        return False, {
            'error': 'already_extended',
            'message': 'Rezerwacja została już przedłużona.'
        }

    # Extend all reservations
    for reservation in reservations:
        reservation.expires_at += EXTENSION_DURATION
        reservation.extended = True

    db.session.commit()

    return True, {
        'new_expires_at': reservations[0].expires_at
    }


def get_sold_counts(page_id, product_ids):
    """
    Pobiera liczbę sprzedanych sztuk dla listy produktów na danej stronie exclusive.

    Args:
        page_id: ID strony exclusive
        product_ids: Lista ID produktów

    Returns:
        dict: {product_id: sold_count}
    """
    from modules.orders.models import Order, OrderItem

    if not product_ids:
        return {}

    # Pobierz sumę zamówionych dla każdego produktu
    results = db.session.query(
        OrderItem.product_id,
        func.sum(OrderItem.quantity).label('total')
    ).join(Order).filter(
        Order.exclusive_page_id == page_id,
        Order.status != 'anulowane',
        OrderItem.product_id.in_(product_ids)
    ).group_by(OrderItem.product_id).all()

    # Konwertuj do dict
    sold_counts = {pid: 0 for pid in product_ids}
    for product_id, total in results:
        sold_counts[product_id] = int(total) if total else 0

    return sold_counts


def get_availability_snapshot(page_id, section_products, session_id):
    """
    Zwraca snapshot dostępności wszystkich produktów

    Args:
        page_id: ID strony exclusive
        section_products: dict {product_id: max_quantity_from_section}
        session_id: UUID sesji

    Returns:
        tuple: (products_data: dict, session_info: dict)
    """
    from modules.orders.models import Order, OrderItem

    cleanup_expired_reservations(page_id)

    result = {}
    now = int(time.time())

    for product_id, section_max in section_products.items():
        # Total reserved (all users) - temporary reservations
        total_reserved = db.session.query(
            func.sum(ExclusiveReservation.quantity)
        ).filter(
            ExclusiveReservation.exclusive_page_id == page_id,
            ExclusiveReservation.product_id == product_id,
            ExclusiveReservation.expires_at > now
        ).scalar() or 0

        # Total already ordered (permanent) - from completed exclusive orders for this product
        total_ordered = db.session.query(
            func.sum(OrderItem.quantity)
        ).join(Order).filter(
            Order.exclusive_page_id == page_id,
            Order.status != 'anulowane',
            OrderItem.product_id == product_id
        ).scalar() or 0

        # User reserved
        user_reservation = get_user_reservation(session_id, page_id, product_id)
        user_reserved = user_reservation.quantity if user_reservation else 0

        # Available = max - reserved - already ordered
        if section_max and section_max > 0:
            available = max(0, section_max - total_reserved - total_ordered)
        else:
            available = float('inf')

        result[str(product_id)] = {
            'available': int(available) if available != float('inf') else 999999,
            'user_reserved': user_reserved,
            'total_reserved': int(total_reserved),
            'total_ordered': int(total_ordered)
        }

    # Session info
    first_reservation = ExclusiveReservation.query.filter_by(
        session_id=session_id,
        exclusive_page_id=page_id
    ).order_by(ExclusiveReservation.reserved_at).first()

    session_info = {
        'has_reservations': first_reservation is not None,
        'can_extend': True,
        'extended': False
    }

    if first_reservation:
        session_info['first_reserved_at'] = first_reservation.reserved_at
        session_info['expires_at'] = first_reservation.expires_at
        session_info['extended'] = first_reservation.extended
        session_info['can_extend'] = not first_reservation.extended

    return result, session_info
