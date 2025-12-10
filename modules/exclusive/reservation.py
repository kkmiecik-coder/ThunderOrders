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


def cleanup_expired_reservations(page_id):
    """
    Lazy cleanup - usuwa wygasłe rezerwacje dla danej strony exclusive

    Args:
        page_id: ID strony exclusive

    Returns:
        int: Liczba usuniętych rezerwacji
    """
    now = int(time.time())
    deleted = ExclusiveReservation.query.filter(
        ExclusiveReservation.exclusive_page_id == page_id,
        ExclusiveReservation.expires_at < now
    ).delete()
    db.session.commit()
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


def get_available_quantity(page_id, product_id, section_max=None):
    """
    Oblicza dostępną ilość produktu

    Args:
        page_id: ID strony exclusive
        product_id: ID produktu
        section_max: max_quantity z sekcji exclusive (może być None dla unlimited)

    Returns:
        int: Dostępna ilość (może być float('inf') dla unlimited)
    """
    # Usuń wygasłe rezerwacje
    cleanup_expired_reservations(page_id)

    # Suma zarezerwowanych (aktywnych)
    now = int(time.time())
    reserved = db.session.query(
        func.sum(ExclusiveReservation.quantity)
    ).filter(
        ExclusiveReservation.exclusive_page_id == page_id,
        ExclusiveReservation.product_id == product_id,
        ExclusiveReservation.expires_at > now
    ).scalar() or 0

    # Jeśli jest limit sekcji, użyj go; w przeciwnym razie unlimited
    if section_max is not None and section_max > 0:
        available = section_max - reserved
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
    Rezerwuje produkt (atomowo)

    Args:
        session_id: UUID sesji
        page_id: ID strony exclusive
        product_id: ID produktu
        quantity: Ilość do zarezerwowania
        section_max: max_quantity z sekcji (None dla unlimited)

    Returns:
        tuple: (success: bool, data: dict)
    """
    try:
        # Check availability
        available = get_available_quantity(page_id, product_id, section_max)
        user_reservation = get_user_reservation(session_id, page_id, product_id)

        current_user_qty = user_reservation.quantity if user_reservation else 0
        requested_increase = quantity

        if available < requested_increase:
            # Insufficient availability
            # Find when earliest reservation expires
            now = int(time.time())
            earliest_expiry = db.session.query(
                func.min(ExclusiveReservation.expires_at)
            ).filter(
                ExclusiveReservation.exclusive_page_id == page_id,
                ExclusiveReservation.product_id == product_id,
                ExclusiveReservation.expires_at > now
            ).scalar()

            available_qty = int(available) if available != float('inf') else 999999
            return False, {
                'error': 'insufficient_availability',
                'message': 'Ten produkt został już zarezerwowany przez innych użytkowników.',
                'available_quantity': available_qty,
                'check_back_at': earliest_expiry if earliest_expiry else None
            }

        # Get or create first reservation time for session
        first_reserved_at = get_first_reservation_time(session_id, page_id)
        if not first_reserved_at:
            first_reserved_at = int(time.time())

        # Check if session has been extended - if so, preserve extended time
        extended_reservation = ExclusiveReservation.query.filter_by(
            session_id=session_id,
            exclusive_page_id=page_id,
            extended=True
        ).first()

        if extended_reservation:
            # Session was extended - use the extended expiry time
            expires_at = extended_reservation.expires_at
        else:
            # Normal reservation - 10 minutes from first reservation
            expires_at = first_reserved_at + RESERVATION_DURATION

        # UPSERT reservation
        if user_reservation:
            # Update existing
            user_reservation.quantity += quantity
            user_reservation.expires_at = expires_at
        else:
            # Create new
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

        db.session.commit()

        # Handle infinity for unlimited products
        remaining_available = available - quantity
        if remaining_available == float('inf'):
            remaining_available = 999999  # Large number for "unlimited"

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
    cleanup_expired_reservations(page_id)

    result = {}
    now = int(time.time())

    for product_id, section_max in section_products.items():
        # Total reserved (all users)
        total_reserved = db.session.query(
            func.sum(ExclusiveReservation.quantity)
        ).filter(
            ExclusiveReservation.exclusive_page_id == page_id,
            ExclusiveReservation.product_id == product_id,
            ExclusiveReservation.expires_at > now
        ).scalar() or 0

        # User reserved
        user_reservation = get_user_reservation(session_id, page_id, product_id)
        user_reserved = user_reservation.quantity if user_reservation else 0

        # Available
        if section_max and section_max > 0:
            available = max(0, section_max - total_reserved)
        else:
            available = float('inf')

        result[str(product_id)] = {
            'available': int(available) if available != float('inf') else 999999,
            'user_reserved': user_reserved,
            'total_reserved': int(total_reserved)
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
