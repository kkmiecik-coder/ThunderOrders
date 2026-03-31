"""
Offer Reservation Logic
Logika systemu rezerwacji produktów na stronach ofertowych
"""

import time
from flask import request
from sqlalchemy import func
from .models import OfferReservation
from modules.products.models import Product
from extensions import db

# Stałe
RESERVATION_DURATION = 120  # 2 minuty w sekundach
EXTENSION_DURATION = 60     # 1 minuta w sekundach


def cleanup_expired_reservations(page_id, auto_commit=True):
    """
    Lazy cleanup - usuwa wygasłe rezerwacje dla danej strony ofertowej

    Args:
        page_id: ID strony ofertowej
        auto_commit: Czy commitować od razu (False gdy wywołane wewnątrz większej transakcji)

    Returns:
        int: Liczba usuniętych rezerwacji
    """
    import logging
    logger = logging.getLogger(__name__)

    for attempt in range(3):
        try:
            now = int(time.time())
            deleted = OfferReservation.query.filter(
                OfferReservation.offer_page_id == page_id,
                OfferReservation.expires_at < now
            ).delete()
            if auto_commit:
                db.session.commit()
            else:
                db.session.flush()
            return deleted
        except Exception as e:
            db.session.rollback()
            if 'Deadlock' in str(e) and attempt < 2:
                logger.warning(f"Deadlock on cleanup attempt {attempt + 1}, retrying...")
                time.sleep(0.1 * (attempt + 1))
                continue
            raise
    return 0


def get_first_reservation_time(session_id, page_id):
    """
    Pobiera czas pierwszej rezerwacji sesji (dla timera)

    Args:
        session_id: UUID sesji
        page_id: ID strony ofertowej

    Returns:
        int: UNIX timestamp pierwszej rezerwacji lub None
    """
    reservation = OfferReservation.query.filter_by(
        session_id=session_id,
        offer_page_id=page_id
    ).order_by(OfferReservation.reserved_at).first()

    return reservation.reserved_at if reservation else None


def get_available_quantity(page_id, product_id, section_max=None, auto_commit=True):
    """
    Oblicza dostępną ilość produktu (rezerwacje + już złożone zamówienia)

    Args:
        page_id: ID strony ofertowej
        product_id: ID produktu
        section_max: max_quantity z sekcji ofertowej (może być None dla unlimited)
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
        func.sum(OfferReservation.quantity)
    ).filter(
        OfferReservation.offer_page_id == page_id,
        OfferReservation.product_id == product_id,
        OfferReservation.expires_at > now
    ).scalar() or 0

    # Suma już zamówionych (złożone zamówienia, bez anulowanych)
    ordered = db.session.query(
        func.sum(OrderItem.quantity)
    ).join(Order).filter(
        Order.offer_page_id == page_id,
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
        page_id: ID strony ofertowej
        product_id: ID produktu

    Returns:
        OfferReservation: Obiekt rezerwacji lub None
    """
    return OfferReservation.query.filter_by(
        session_id=session_id,
        offer_page_id=page_id,
        product_id=product_id
    ).first()


def reserve_product(session_id, page_id, product_id, quantity, section_max=None, user_id=None):
    """
    Rezerwuje produkt (atomowo z row-level locking)

    Cała operacja (cleanup + check + reserve) odbywa się w jednej transakcji.
    SELECT FOR UPDATE lockuje wiersze rezerwacji dla danego produktu,
    zapobiegając race condition przy jednoczesnych rezerwacjach.

    Args:
        session_id: UUID sesji
        page_id: ID strony ofertowej
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
        locked_reservations = OfferReservation.query.filter(
            OfferReservation.offer_page_id == page_id,
            OfferReservation.product_id == product_id,
            OfferReservation.expires_at > now
        ).with_for_update().all()

        # 3. Oblicz dostępność na podstawie zlockowanych danych
        reserved = sum(r.quantity for r in locked_reservations)

        # Suma już zamówionych (złożone zamówienia, bez anulowanych)
        ordered = db.session.query(
            func.sum(OrderItem.quantity)
        ).join(Order).filter(
            Order.offer_page_id == page_id,
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
                'message': 'Ktoś właśnie zarezerwował lub zakupił ten produkt.',
                'available_quantity': available_qty,
                'check_back_at': earliest_expiry
            }

        # 5. Oblicz czas wygaśnięcia
        first_reserved_at = get_first_reservation_time(session_id, page_id)
        if not first_reserved_at:
            first_reserved_at = int(time.time())

        extended_reservation = OfferReservation.query.filter_by(
            session_id=session_id,
            offer_page_id=page_id,
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
            # Bezpieczne pobieranie IP/UA (SocketIO może nie mieć tych danych)
            try:
                ip_addr = request.remote_addr or ''
                user_agent = request.headers.get('User-Agent', '')
            except (RuntimeError, AttributeError):
                ip_addr = ''
                user_agent = ''

            user_reservation = OfferReservation(
                session_id=session_id,
                offer_page_id=page_id,
                product_id=product_id,
                quantity=quantity,
                reserved_at=first_reserved_at,
                expires_at=expires_at,
                user_id=user_id,
                ip_address=ip_addr,
                user_agent=user_agent
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
        page_id: ID strony ofertowej
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
    Przedłuża rezerwację o 1 minutę (jednokrotnie)

    Args:
        session_id: UUID sesji
        page_id: ID strony ofertowej

    Returns:
        tuple: (success: bool, data: dict)
    """
    # Cleanup expired BEFORE checking — zapobiega wskrzeszaniu wygasłych rezerwacji
    cleanup_expired_reservations(page_id)

    now = int(time.time())
    reservations = OfferReservation.query.filter(
        OfferReservation.session_id == session_id,
        OfferReservation.offer_page_id == page_id,
        OfferReservation.expires_at > now
    ).all()

    if not reservations:
        return False, {
            'error': 'reservation_expired',
            'message': 'Twoja rezerwacja wygasła. Dodaj produkty ponownie.'
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


def get_section_max_for_product(page_id, product_id):
    """
    Zwraca limit max_quantity dla produktu na stronie ofertowej.

    Sprawdza kolejno:
    1. Sekcja typu 'product' z bezpośrednim product_id
    2. Sekcja typu 'variant_group' z grupą wariantową produktu
    3. Sekcja typu 'set' — element setu z bezpośrednim product_id
    4. Sekcja typu 'set' — element setu przez grupę wariantową

    Args:
        page_id: ID strony ofertowej
        product_id: ID produktu

    Returns:
        int | None: Limit ilości (None = bez limitu)
    """
    from .models import OfferSection, OfferSetItem
    from modules.products.models import variant_products

    # 1. Bezpośrednia sekcja produktowa
    section = OfferSection.query.filter_by(
        offer_page_id=page_id,
        section_type='product',
        product_id=product_id
    ).first()

    if section:
        return section.max_quantity

    # Znajdź grupy wariantowe produktu (potrzebne dla kroków 2-4)
    product_vg_ids = db.session.query(variant_products.c.variant_group_id).filter(
        variant_products.c.product_id == product_id
    ).all()
    product_vg_ids = [vg_id for (vg_id,) in product_vg_ids]

    # 2. Sekcja variant_group
    if product_vg_ids:
        vg_section = OfferSection.query.filter(
            OfferSection.offer_page_id == page_id,
            OfferSection.section_type == 'variant_group',
            OfferSection.variant_group_id.in_(product_vg_ids)
        ).first()

        if vg_section:
            return vg_section.max_quantity

    # 3. Bezpośredni element setu
    set_item = OfferSetItem.query.join(OfferSection).filter(
        OfferSection.offer_page_id == page_id,
        OfferSection.section_type == 'set',
        OfferSetItem.product_id == product_id
    ).first()

    if set_item:
        return set_item.section.set_max_sets

    # 4. Element setu przez grupę wariantową
    if product_vg_ids:
        set_item_vg = OfferSetItem.query.join(OfferSection).filter(
            OfferSection.offer_page_id == page_id,
            OfferSection.section_type == 'set',
            OfferSetItem.variant_group_id.in_(product_vg_ids)
        ).first()
        if set_item_vg:
            return set_item_vg.section.set_max_sets

    return None


def get_section_products_map(page_id):
    """
    Zwraca mapę {product_id: section_max} dla wszystkich produktów na stronie ofertowej.

    Potrzebne do broadcast_availability_update() — zamiast budować mapę
    za każdym razem w route, robimy to raz.

    Args:
        page_id: ID strony ofertowej

    Returns:
        dict: {product_id: max_quantity (int lub None)}
    """
    from .models import OfferSection, OfferSetItem
    from modules.products.models import Product, VariantGroup

    sections = OfferSection.query.filter_by(offer_page_id=page_id).all()
    section_products = {}

    for section in sections:
        if section.section_type == 'product' and section.product_id:
            section_products[section.product_id] = section.max_quantity

        elif section.section_type == 'variant_group' and section.variant_group_id:
            products = Product.query.join(
                Product.variant_groups
            ).filter(
                VariantGroup.id == section.variant_group_id,
                Product.is_active == True
            ).all()
            for product in products:
                section_products[product.id] = section.max_quantity

        elif section.section_type == 'set':
            product_limit = section.set_max_sets
            set_items = OfferSetItem.query.filter_by(section_id=section.id).all()

            for set_item in set_items:
                if set_item.product_id:
                    section_products[set_item.product_id] = product_limit
                elif set_item.variant_group_id:
                    vg_products = Product.query.join(
                        Product.variant_groups
                    ).filter(
                        VariantGroup.id == set_item.variant_group_id,
                        Product.is_active == True
                    ).all()
                    for product in vg_products:
                        section_products[product.id] = product_limit

    return section_products


def get_sold_counts(page_id, product_ids):
    """
    Pobiera liczbę sprzedanych sztuk dla listy produktów na danej stronie ofertowej.

    Args:
        page_id: ID strony ofertowej
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
        Order.offer_page_id == page_id,
        Order.status != 'anulowane',
        OrderItem.product_id.in_(product_ids)
    ).group_by(OrderItem.product_id).all()

    # Konwertuj do dict
    sold_counts = {pid: 0 for pid in product_ids}
    for product_id, total in results:
        sold_counts[product_id] = int(total) if total else 0

    return sold_counts


def get_set_probabilities(order):
    """
    Oblicza prawdopodobieństwo wypełnienia setu PER ORDER ITEM na podstawie
    zapisanego set_number.

    Dla każdego itemu z set_number = N:
    - Oblicz ile produktów z tego setu ma slots >= N (tzn. ma wypełniony slot w Secie N)
    - probability = count / total_products × 100%

    Przykład: 8 produktów, item w Secie 1 (kompletnym) → 8/8 = 100%
              item w Secie 5 (3 produkty) → 3/8 = 37.5%

    Args:
        order: Order object with items loaded

    Returns:
        dict: {order_item_id: {'probability': float, 'set_name': str,
                               'set_number': int, 'section_id': int}}
    """
    from .models import OfferSection
    from modules.orders.models import Order, OrderItem

    if not order.offer_page_id:
        return {}

    page_id = order.offer_page_id

    set_sections = OfferSection.query.filter_by(
        offer_page_id=page_id,
        section_type='set'
    ).all()

    if not set_sections:
        return {}

    result = {}

    for section in set_sections:
        product_qty_per_set = {}
        for set_item in section.set_items:
            qps = set_item.quantity_per_set or 1
            for product in set_item.get_products():
                product_qty_per_set[product.id] = qps

        if not product_qty_per_set:
            continue

        all_product_ids = set(product_qty_per_set.keys())
        total_products = len(all_product_ids)
        set_name = section.set_name or f'Set #{section.id}'

        # Calculate slots per product (global across all page orders)
        ordered_counts = db.session.query(
            OrderItem.product_id,
            func.sum(OrderItem.quantity)
        ).join(Order).filter(
            Order.offer_page_id == page_id,
            Order.status != 'anulowane',
            OrderItem.product_id.in_(all_product_ids)
        ).group_by(OrderItem.product_id).all()

        ordered_map = {pid: int(qty) for pid, qty in ordered_counts}

        slots_per_product = {}
        for pid in all_product_ids:
            ordered = ordered_map.get(pid, 0)
            qps = product_qty_per_set[pid]
            slots_per_product[pid] = ordered // qps if qps > 0 else 0

        # For each order item with set_number, calculate per-set probability
        for item in order.items:
            if item.set_number is None or item.set_section_id != section.id:
                continue

            N = item.set_number
            products_in_set_N = sum(1 for s in slots_per_product.values() if s >= N)
            probability = (products_in_set_N / total_products) * 100 if total_products > 0 else 0

            result[item.id] = {
                'probability': probability,
                'set_name': set_name,
                'set_number': N,
                'section_id': section.id,
            }

    return result


def get_availability_snapshot(page_id, section_products, session_id):
    """
    Zwraca snapshot dostępności wszystkich produktów

    Args:
        page_id: ID strony ofertowej
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
            func.sum(OfferReservation.quantity)
        ).filter(
            OfferReservation.offer_page_id == page_id,
            OfferReservation.product_id == product_id,
            OfferReservation.expires_at > now
        ).scalar() or 0

        # Total already ordered (permanent) - from completed offer orders for this product
        total_ordered = db.session.query(
            func.sum(OrderItem.quantity)
        ).join(Order).filter(
            Order.offer_page_id == page_id,
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
    first_reservation = OfferReservation.query.filter_by(
        session_id=session_id,
        offer_page_id=page_id
    ).order_by(OfferReservation.reserved_at).first()

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
