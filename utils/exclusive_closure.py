"""
Exclusive Page Closure Module
=============================

Zawiera logikę całkowitego zamykania stron Exclusive:
- Algorytm alokacji setów (które zamówienia dostają produkty)
- Generowanie podsumowania sprzedaży
- Wysyłka emaili do klientów
"""

from datetime import datetime
from collections import defaultdict
from flask import current_app
from extensions import db
from modules.exclusive.models import ExclusivePage, ExclusiveSection, ExclusiveSetItem
from modules.orders.models import Order, OrderItem


def calculate_set_fulfillment(page_id):
    """
    Główna funkcja obliczająca alokację produktów w setach.

    Algorytm dla każdego SET:
    1. Pobierz wszystkie produkty w secie z quantity_per_set
    2. Dla każdego produktu policz łączną zamówioną ilość
    3. Oblicz complete_sets = MIN(total_ordered / qty_per_set) dla wszystkich produktów
    4. Przydziel produkty do zamówień posortowanych po created_at (najstarsze pierwsze)

    Args:
        page_id: ID strony Exclusive

    Returns:
        dict: Słownik z wynikami alokacji
            {
                'page_id': int,
                'sets': [
                    {
                        'section_id': int,
                        'set_name': str,
                        'complete_sets': int,
                        'products': [...],
                        'allocations': [...],
                    }
                ],
                'total_orders': int,
                'total_fulfilled': int,
                'total_unfulfilled': int,
            }
    """
    page = ExclusivePage.query.get(page_id)
    if not page:
        raise ValueError(f"Strona Exclusive o ID {page_id} nie istnieje")

    # Pobierz wszystkie zamówienia dla tej strony
    orders = Order.query.filter_by(exclusive_page_id=page_id).order_by(Order.created_at.asc()).all()

    result = {
        'page_id': page_id,
        'page_name': page.name,
        'sets': [],
        'total_orders': len(orders),
        'total_fulfilled': 0,
        'total_unfulfilled': 0,
    }

    # Pobierz sekcje typu 'set'
    set_sections = page.sections.filter_by(section_type='set').all()

    for section in set_sections:
        set_result = process_set_section(section, orders)
        result['sets'].append(set_result)
        result['total_fulfilled'] += set_result['fulfilled_count']
        result['total_unfulfilled'] += set_result['unfulfilled_count']

    return result


def process_set_section(section, orders):
    """
    Przetwarza pojedynczą sekcję SET i alokuje produkty do zamówień.

    Args:
        section: ExclusiveSection typu 'set'
        orders: Lista zamówień posortowana po created_at

    Returns:
        dict: Wyniki alokacji dla tego setu
    """
    set_items = section.get_set_items_ordered()

    # Zbierz wszystkie produkty z setu (z grup wariantowych rozwijamy na pojedyncze produkty)
    set_products = []  # [(product_id, quantity_per_set), ...]
    for item in set_items:
        products = item.get_products()
        for product in products:
            set_products.append({
                'product_id': product.id,
                'product_name': product.name,
                'quantity_per_set': item.quantity_per_set,
                'set_item_id': item.id,
            })

    if not set_products:
        return {
            'section_id': section.id,
            'set_name': section.set_name or 'Bez nazwy',
            'complete_sets': 0,
            'products': [],
            'allocations': [],
            'fulfilled_count': 0,
            'unfulfilled_count': 0,
        }

    # Zbierz zamówienia dla każdego produktu w secie
    # Struktura: {product_id: [(order_id, order_item, quantity, created_at), ...]}
    product_orders = defaultdict(list)

    for order in orders:
        for item in order.items:
            for sp in set_products:
                if item.product_id == sp['product_id']:
                    product_orders[sp['product_id']].append({
                        'order_id': order.id,
                        'order_item': item,
                        'quantity': item.quantity,
                        'created_at': order.created_at,
                    })

    # Oblicz liczbę dostępnych kompletnych setów
    # complete_sets = MIN(sum(ordered) / qty_per_set) dla każdego produktu
    available_sets_per_product = []
    products_summary = []

    for sp in set_products:
        total_ordered = sum(po['quantity'] for po in product_orders.get(sp['product_id'], []))
        qty_per_set = sp['quantity_per_set']
        available = total_ordered // qty_per_set if qty_per_set > 0 else 0
        available_sets_per_product.append(available)

        products_summary.append({
            'product_id': sp['product_id'],
            'product_name': sp['product_name'],
            'quantity_per_set': qty_per_set,
            'total_ordered': total_ordered,
            'available_sets': available,
        })

    complete_sets = min(available_sets_per_product) if available_sets_per_product else 0

    # Alokacja: przydziel produkty do zamówień
    # Dla każdego produktu w secie, przydziel pierwsze N zamówień (gdzie suma qty <= complete_sets * qty_per_set)
    allocations = []
    fulfilled_count = 0
    unfulfilled_count = 0

    for sp in set_products:
        product_id = sp['product_id']
        qty_per_set = sp['quantity_per_set']
        max_to_fulfill = complete_sets * qty_per_set

        fulfilled_so_far = 0
        orders_for_product = sorted(
            product_orders.get(product_id, []),
            key=lambda x: x['created_at']
        )

        for po in orders_for_product:
            order_item = po['order_item']
            qty = po['quantity']
            remaining_capacity = max_to_fulfill - fulfilled_so_far

            if remaining_capacity <= 0:
                # Brak miejsca - całość poza setem
                order_item.is_set_fulfilled = False
                order_item.set_section_id = section.id
                order_item.fulfilled_quantity = 0
                unfulfilled_count += qty

                allocations.append({
                    'order_id': po['order_id'],
                    'order_item_id': order_item.id,
                    'product_id': product_id,
                    'product_name': sp['product_name'],
                    'quantity': qty,
                    'fulfilled_quantity': 0,
                    'is_fulfilled': False,
                })
            elif qty <= remaining_capacity:
                # Całość mieści się
                order_item.is_set_fulfilled = True
                order_item.set_section_id = section.id
                order_item.fulfilled_quantity = qty
                fulfilled_so_far += qty
                fulfilled_count += qty

                allocations.append({
                    'order_id': po['order_id'],
                    'order_item_id': order_item.id,
                    'product_id': product_id,
                    'product_name': sp['product_name'],
                    'quantity': qty,
                    'fulfilled_quantity': qty,
                    'is_fulfilled': True,
                })
            else:
                # CZĘŚCIOWE ZREALIZOWANIE - część mieści się, reszta przepada
                order_item.is_set_fulfilled = True  # Oznacz jako zrealizowane (choć częściowo)
                order_item.set_section_id = section.id
                order_item.fulfilled_quantity = remaining_capacity
                fulfilled_so_far += remaining_capacity
                fulfilled_count += remaining_capacity
                unfulfilled_count += (qty - remaining_capacity)

                allocations.append({
                    'order_id': po['order_id'],
                    'order_item_id': order_item.id,
                    'product_id': product_id,
                    'product_name': sp['product_name'],
                    'quantity': qty,
                    'fulfilled_quantity': remaining_capacity,
                    'is_fulfilled': 'partial',  # Specjalny status dla częściowego
                })

    return {
        'section_id': section.id,
        'set_name': section.set_name or 'Bez nazwy',
        'complete_sets': complete_sets,
        'products': products_summary,
        'allocations': allocations,
        'fulfilled_count': fulfilled_count,
        'unfulfilled_count': unfulfilled_count,
    }


def close_exclusive_page(page_id, user_id, send_emails=True):
    """
    Całkowicie zamyka stronę Exclusive.

    1. Sprawdza czy strona może być zamknięta (status='ended', not is_fully_closed)
    2. Wykonuje algorytm alokacji setów
    3. Zapisuje wyniki w bazie
    4. Ustawia is_fully_closed = True
    5. Opcjonalnie wysyła emaile do klientów

    Args:
        page_id: ID strony Exclusive
        user_id: ID użytkownika wykonującego zamknięcie
        send_emails: Czy wysyłać emaile do klientów (domyślnie True)

    Returns:
        dict: Wyniki zamknięcia
    """
    page = ExclusivePage.query.get(page_id)

    if not page:
        raise ValueError(f"Strona Exclusive o ID {page_id} nie istnieje")

    if page.status != 'ended':
        raise ValueError(f"Strona musi mieć status 'Zakończona' (ended), obecnie: {page.status}")

    if page.is_fully_closed:
        raise ValueError("Strona została już całkowicie zamknięta")

    # Wykonaj algorytm alokacji
    allocation_result = calculate_set_fulfillment(page_id)

    # Zapisz zmiany w OrderItem (już zapisane przez process_set_section)
    # Ustaw flagę zamknięcia
    page.is_fully_closed = True
    page.closed_at = datetime.now()
    page.closed_by_id = user_id

    db.session.commit()

    # Wysyłka emaili
    if send_emails:
        try:
            send_closure_emails(page_id)
        except Exception as e:
            current_app.logger.error(f"Błąd wysyłki emaili dla strony {page_id}: {str(e)}")
            # Nie przerywamy - zamknięcie już się dokonało

    return {
        'success': True,
        'page_id': page_id,
        'allocation': allocation_result,
    }


def get_page_summary(page_id, include_financials=True):
    """
    Generuje podsumowanie sprzedaży dla zamkniętej strony Exclusive.

    Args:
        page_id: ID strony Exclusive
        include_financials: Czy uwzględniać dane finansowe (tylko Admin)

    Returns:
        dict: Podsumowanie sprzedaży
    """
    page = ExclusivePage.query.get(page_id)
    if not page:
        raise ValueError(f"Strona Exclusive o ID {page_id} nie istnieje")

    orders = Order.query.filter_by(exclusive_page_id=page_id).order_by(Order.created_at.asc()).all()

    # Podstawowe statystyki
    total_orders = len(orders)
    unique_customers = len(set(
        order.guest_email or order.user_id for order in orders
    ))

    # Przychód liczony tylko z produktów zrealizowanych
    # is_set_fulfilled = True -> zrealizowane w secie
    # is_set_fulfilled = None -> produkt spoza setu (zawsze realizowany)
    # is_set_fulfilled = False -> NIE zrealizowane (nie liczymy)
    total_revenue = 0.0
    for order in orders:
        for item in order.items:
            # Liczymy tylko zrealizowane produkty (True lub None)
            if item.is_set_fulfilled is not False:
                total_revenue += float(item.total) if item.total else 0

    # Zbierz informacje o setach
    sets_info = []
    set_sections = page.sections.filter_by(section_type='set').all()

    for section in set_sections:
        set_items = section.get_set_items_ordered()
        products_in_set = []

        for item in set_items:
            for product in item.get_products():
                # Znajdź wszystkie OrderItem dla tego produktu w tej sekcji
                order_items = OrderItem.query.filter_by(
                    product_id=product.id,
                    set_section_id=section.id
                ).all()

                total_ordered = sum(oi.quantity for oi in order_items)
                fulfilled = sum(oi.quantity for oi in order_items if oi.is_set_fulfilled)
                unfulfilled = sum(oi.quantity for oi in order_items if oi.is_set_fulfilled is False)

                products_in_set.append({
                    'product_id': product.id,
                    'product_name': product.name,
                    'quantity_per_set': item.quantity_per_set,
                    'total_ordered': total_ordered,
                    'fulfilled': fulfilled,
                    'unfulfilled': unfulfilled,
                })

        # Oblicz complete sets na podstawie fulfilled items
        if products_in_set:
            complete_sets = min(
                p['fulfilled'] // p['quantity_per_set']
                for p in products_in_set
                if p['quantity_per_set'] > 0
            ) if any(p['quantity_per_set'] > 0 for p in products_in_set) else 0
        else:
            complete_sets = 0

        sets_info.append({
            'section_id': section.id,
            'set_name': section.set_name or 'Bez nazwy',
            'set_image': section.set_image,
            'complete_sets': complete_sets,
            'products': products_in_set,
        })

    # Lista zamówień z detalami
    orders_list = []
    for order in orders:
        items_details = []
        fulfilled_amount = 0.0  # Wartość tylko zrealizowanych produktów

        for item in order.items:
            item_total = float(item.total) if item.total else 0

            # Liczymy wartość tylko zrealizowanych produktów
            if item.is_set_fulfilled is not False:
                fulfilled_amount += item_total

            item_data = {
                'product_id': item.product_id,
                'product_name': item.product_name,
                'quantity': item.quantity,
                'price': float(item.price) if item.price else 0,
                'total': item_total,
                'is_set_fulfilled': item.is_set_fulfilled,
                'set_section_id': item.set_section_id,
            }
            items_details.append(item_data)

        order_data = {
            'order_id': order.id,
            'order_number': order.order_number,
            'customer_name': order.customer_name,
            'customer_email': order.customer_email,
            'customer_phone': order.guest_phone if order.is_guest_order else (order.user.phone if order.user else None),
            'created_at': order.created_at,
            'total_amount': fulfilled_amount,  # Tylko zrealizowane produkty
            'order_items': items_details,
        }
        orders_list.append(order_data)

    result = {
        'page_id': page_id,
        'page_name': page.name,
        'is_fully_closed': page.is_fully_closed,
        'closed_at': page.closed_at,
        'closed_by': page.closed_by.full_name if page.closed_by else None,
        'starts_at': page.starts_at,
        'ends_at': page.ends_at,
        'total_orders': total_orders,
        'unique_customers': unique_customers,
        'sets': sets_info,
        'orders': orders_list,
    }

    if include_financials:
        result['total_revenue'] = total_revenue

    return result


def send_closure_emails(page_id):
    """
    Wysyła emaile do wszystkich klientów z podsumowaniem ich zamówień.
    ROZSZERZONE: Dodaje informacje finansowe i dane do przelewu.

    Args:
        page_id: ID strony Exclusive
    """
    from utils.email_sender import send_exclusive_closure_email
    from modules.payments.models import PaymentMethod
    from flask import url_for

    page = ExclusivePage.query.get(page_id)
    if not page:
        return

    orders = Order.query.filter_by(exclusive_page_id=page_id).all()

    # Pobierz aktywne metody płatności
    payment_methods_raw = PaymentMethod.get_active()

    for order in orders:
        customer_email = order.customer_email
        customer_name = order.customer_name

        if not customer_email:
            continue

        # Przygotuj listę produktów z ich statusem
        items = []
        fulfilled_items = []
        for item in order.items:
            is_fulfilled = item.is_set_fulfilled if item.is_set_fulfilled is not None else True
            items.append({
                'product_name': item.product_name,
                'quantity': item.quantity,
                'is_fulfilled': is_fulfilled,
            })
            if is_fulfilled:
                fulfilled_items.append(item)

        # Oblicz sumę TYLKO zrealizowanych produktów
        from decimal import Decimal
        fulfilled_total = Decimal('0.00')
        for item in fulfilled_items:
            if item.fulfilled_quantity is not None:
                fulfilled_total += Decimal(str(item.price)) * item.fulfilled_quantity
            else:
                fulfilled_total += Decimal(str(item.total))

        # Shipping cost (jeśli jest)
        shipping_cost = Decimal(str(order.shipping_cost)) if order.shipping_cost else Decimal('0.00')
        grand_total = fulfilled_total + shipping_cost

        # Przygotuj metody płatności z podstawionym numerem zamówienia
        payment_methods = []
        for method in payment_methods_raw:
            details = method.details.replace('[NUMER ZAMÓWIENIA]', order.order_number)
            payment_methods.append({
                'name': method.name,
                'details': details
            })

        # URL do wgrania dowodu
        upload_payment_url = url_for('orders.client_detail',
                                     order_id=order.id,
                                     _external=True) + '?action=upload_payment'

        try:
            send_exclusive_closure_email(
                customer_email=customer_email,
                customer_name=customer_name,
                page_name=page.name,
                items=items,
                fulfilled_items=fulfilled_items,
                fulfilled_total=fulfilled_total,
                shipping_cost=shipping_cost,
                grand_total=grand_total,
                order_number=order.order_number,
                payment_methods=payment_methods,
                upload_payment_url=upload_payment_url
            )
            current_app.logger.info(f"Email wysłany do {customer_email} dla zamówienia {order.order_number}")
        except Exception as e:
            current_app.logger.error(f"Błąd wysyłki email do {customer_email}: {str(e)}")
