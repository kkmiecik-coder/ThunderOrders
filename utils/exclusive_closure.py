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
from decimal import Decimal
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
            key=lambda x: (x['created_at'], x['order_id'])
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

                # NOWE: Zeruj cenę, total i quantity
                order_item.price = Decimal('0.00')
                order_item.total = Decimal('0.00')
                order_item.quantity = 0

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
                # CZĘŚCIOWE ZREALIZOWANIE - rozdziel na 2 OrderItems
                fulfilled_qty = remaining_capacity
                unfulfilled_qty = qty - remaining_capacity

                # MODYFIKUJ ISTNIEJĄCY ITEM → część fulfilled
                original_price = order_item.price  # Zachowaj oryginalną cenę
                order_item.quantity = fulfilled_qty
                order_item.fulfilled_quantity = fulfilled_qty
                order_item.is_set_fulfilled = True
                order_item.set_section_id = section.id
                order_item.total = original_price * fulfilled_qty  # Przelicz total

                # STWÓRZ NOWY ITEM → część unfulfilled
                unfulfilled_item = OrderItem(
                    order_id=order_item.order_id,
                    product_id=order_item.product_id,
                    quantity=0,  # Wyzerowane
                    price=Decimal('0.00'),  # Wyzerowane
                    total=Decimal('0.00'),  # Wyzerowane
                    is_set_fulfilled=False,
                    set_section_id=section.id,
                    fulfilled_quantity=0,
                    picked=False,
                    picked_at=None,
                    picked_by=None
                )
                db.session.add(unfulfilled_item)

                fulfilled_so_far += fulfilled_qty
                fulfilled_count += fulfilled_qty
                unfulfilled_count += unfulfilled_qty

                # Allocation dla fulfilled part
                allocations.append({
                    'order_id': po['order_id'],
                    'order_item_id': order_item.id,
                    'product_id': product_id,
                    'product_name': sp['product_name'],
                    'quantity': fulfilled_qty,
                    'fulfilled_quantity': fulfilled_qty,
                    'is_fulfilled': True,
                })

                # Allocation dla unfulfilled part
                allocations.append({
                    'order_id': po['order_id'],
                    'order_item_id': unfulfilled_item.id,
                    'product_id': product_id,
                    'product_name': sp['product_name'],
                    'quantity': unfulfilled_qty,
                    'fulfilled_quantity': 0,
                    'is_fulfilled': False,
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


def auto_update_order_statuses(page_id, admin_user_id=None):
    """
    Automatycznie aktualizuje statusy zamówień po closure Exclusive.

    Zamówienia są klasyfikowane jako:
    - Fully fulfilled: wszystkie items są fulfilled
    - Partially fulfilled: część items fulfilled, część unfulfilled
    - Not fulfilled: żaden item nie jest fulfilled

    Statusy docelowe są konfigurowalne przez ustawienia:
    - exclusive_closure_status_fully_fulfilled
    - exclusive_closure_status_partially_fulfilled
    - exclusive_closure_status_not_fulfilled

    Args:
        page_id: ID ExclusivePage
        admin_user_id: ID użytkownika wykonującego closure (dla activity log)

    Returns:
        Dict with counts: {
            'fully_fulfilled': int,
            'partially_fulfilled': int,
            'not_fulfilled': int,
            'updated_order_ids': [...]
        }
    """
    from utils.activity_logger import log_activity
    from modules.auth.models import Settings

    page = ExclusivePage.query.get(page_id)
    if not page:
        return {
            'fully_fulfilled': 0,
            'partially_fulfilled': 0,
            'not_fulfilled': 0,
            'updated_order_ids': []
        }

    # Pobierz ustawienia statusów z bazy
    def get_status_setting(key, default):
        setting = Settings.query.filter_by(key=key).first()
        return setting.value if setting else default

    status_fully = get_status_setting('exclusive_closure_status_fully_fulfilled', 'oczekujace')
    status_partially = get_status_setting('exclusive_closure_status_partially_fulfilled', 'oczekujace')
    status_not = get_status_setting('exclusive_closure_status_not_fulfilled', 'anulowane')

    orders = Order.query.filter_by(exclusive_page_id=page_id).all()

    counts = {
        'fully_fulfilled': 0,
        'partially_fulfilled': 0,
        'not_fulfilled': 0,
        'updated_order_ids': []
    }

    for order in orders:
        # Klasyfikacja zamówienia
        fulfilled_items = [item for item in order.items if item.is_set_fulfilled is not False]
        unfulfilled_items = [item for item in order.items if item.is_set_fulfilled is False]

        total_items = len(order.items)
        fulfilled_count = len(fulfilled_items)

        # Określ typ realizacji
        if fulfilled_count == 0:
            # Żaden produkt nie przeszedł
            fulfillment_type = 'not_fulfilled'
            new_status = status_not
        elif fulfilled_count == total_items:
            # Wszystkie produkty przeszły
            fulfillment_type = 'fully_fulfilled'
            new_status = status_fully
        else:
            # Część produktów przeszła
            fulfillment_type = 'partially_fulfilled'
            new_status = status_partially

        # Aktualizuj status jeśli się zmienił
        if order.status != new_status:
            old_status = order.status
            order.status = new_status
            order.updated_at = datetime.now()

            counts[fulfillment_type] += 1
            counts['updated_order_ids'].append(order.id)

            # Log activity
            if admin_user_id:
                from modules.auth.models import User
                admin_user = User.query.get(admin_user_id)
                if admin_user:
                    log_activity(
                        user=admin_user,
                        action='order_status_auto_updated',
                        entity_type='order',
                        entity_id=order.id,
                        old_value={'status': old_status},
                        new_value={'status': new_status}
                    )

    return counts


def close_exclusive_page(page_id, user_id, send_emails=True):
    """
    Całkowicie zamyka stronę Exclusive.

    1. Sprawdza czy strona może być zamknięta (status='ended', not is_fully_closed)
    2. Wykonuje algorytm alokacji setów (zerowanie unfulfilled, split partial)
    3. Auto-anuluje zamówienia bez fulfilled items
    4. Przelicza total_amount dla wszystkich zamówień
    5. Zapisuje wyniki w bazie (atomowa transakcja)
    6. Opcjonalnie wysyła emaile do klientów

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

    try:
        # 1. Wykonaj algorytm alokacji (ZMODYFIKOWANY - zeruje ceny, splituje partial)
        allocation_result = calculate_set_fulfillment(page_id)

        # 2. NOWE: Auto-aktualizuj statusy zamówień (konfigurowalne)
        status_update_result = auto_update_order_statuses(page_id, user_id)

        # 3. NOWE: Przelicz total_amount dla wszystkich zamówień
        orders = Order.query.filter_by(exclusive_page_id=page_id).all()
        for order in orders:
            order.recalculate_total_amount()

        # 4. Ustaw flagę zamknięcia
        page.is_fully_closed = True
        page.closed_at = datetime.now()
        page.closed_by_id = user_id

        # 5. COMMIT - atomowa transakcja
        db.session.commit()

        current_app.logger.info(f"Exclusive page {page_id} closed successfully. "
                                f"Status updates: fully={status_update_result['fully_fulfilled']}, "
                                f"partially={status_update_result['partially_fulfilled']}, "
                                f"not_fulfilled={status_update_result['not_fulfilled']}")

        # 6. Wysyłka emaili (PO commit, żeby nie rollbackować przy błędzie email)
        if send_emails:
            try:
                # Email o closure (istniejący)
                send_closure_emails(page_id)

                # NOWE: Email o anulowaniu (tylko dla zamówień not_fulfilled)
                not_fulfilled_orders = [
                    oid for oid in status_update_result['updated_order_ids']
                    if Order.query.get(oid).status == Settings.query.filter_by(
                        key='exclusive_closure_status_not_fulfilled'
                    ).first().value
                ]
                if not_fulfilled_orders:
                    send_cancellation_emails(page_id, not_fulfilled_orders)

            except Exception as e:
                current_app.logger.error(f"Błąd wysyłki emaili dla strony {page_id}: {str(e)}")
                # NIE rollbackuj - zamknięcie już się dokonało!

        return {
            'success': True,
            'page_id': page_id,
            'allocation': allocation_result,
            'status_updates': status_update_result,
        }

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Błąd zamykania strony Exclusive {page_id}: {str(e)}")
        raise


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


def send_cancellation_emails(page_id, cancelled_order_ids):
    """
    Wysyła emaile do klientów o anulowanych zamówieniach.

    Args:
        page_id: ID ExclusivePage
        cancelled_order_ids: Lista ID zamówień do anulowania
    """
    from modules.auth.models import User
    from utils.email_sender import send_order_cancelled_email

    page = ExclusivePage.query.get(page_id)
    if not page:
        return

    for order_id in cancelled_order_ids:
        order = Order.query.get(order_id)
        if not order:
            continue

        # Przygotuj listę anulowanych produktów
        cancelled_items = []
        for item in order.items:
            cancelled_items.append({
                'name': item.product_name or 'Nieznany produkt',
                'quantity': item.quantity or 0,
                'image_url': item.product_image_url
            })

        # Określ email i nazwę odbiorcy
        if order.is_guest_order:
            recipient_email = order.guest_email
            recipient_name = order.guest_name or 'Kliencie'
        else:
            user = User.query.get(order.user_id)
            if user:
                recipient_email = user.email
                recipient_name = user.first_name or 'Kliencie'
            else:
                continue

        # Wyślij email
        try:
            send_order_cancelled_email(
                user_email=recipient_email,
                user_name=recipient_name,
                order_number=order.order_number,
                page_name=page.name,
                cancelled_items=cancelled_items,
                reason='Żaden z produktów w Twoim zamówieniu nie załapał się do kompletu.'
            )
            current_app.logger.info(f"Cancellation email sent for order {order.order_number}")
        except Exception as e:
            current_app.logger.error(f"Failed to send cancellation email for order {order.order_number}: {e}")


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

        # KRYTYCZNE: Pomiń zamówienia bez żadnych zrealizowanych produktów
        # Te zamówienia dostają email o anulowaniu przez send_cancellation_emails()
        if not fulfilled_items or len(fulfilled_items) == 0:
            current_app.logger.info(
                f"Pomijam email closure dla zamówienia {order.order_number} - "
                f"brak zrealizowanych produktów (email anulowania zostanie wysłany osobno)"
            )
            continue

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
            current_app.logger.info(f"Email closure wysłany do {customer_email} dla zamówienia {order.order_number}")
        except Exception as e:
            current_app.logger.error(f"Błąd wysyłki email closure do {customer_email}: {str(e)}")
