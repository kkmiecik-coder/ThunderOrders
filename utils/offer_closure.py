"""
Offer Page Closure Module
=========================

Zawiera logikę całkowitego zamykania stron Offer:
- Algorytm alokacji setów (które zamówienia dostają produkty)
- Generowanie podsumowania sprzedaży
- Wysyłka emaili do klientów
"""

from datetime import datetime
from collections import defaultdict
from decimal import Decimal
from flask import current_app, url_for
from extensions import db
from modules.offers.models import OfferPage, OfferSection, OfferSetItem
from modules.orders.models import Order, OrderItem
from modules.auth.models import Settings, User


def calculate_set_fulfillment(page_id):
    """
    Główna funkcja obliczająca alokację produktów w setach.

    Algorytm dla każdego SET:
    1. Pobierz wszystkie produkty w secie z quantity_per_set
    2. Dla każdego produktu policz łączną zamówioną ilość
    3. Oblicz complete_sets = MIN(total_ordered / qty_per_set) dla wszystkich produktów
    4. Przydziel produkty do zamówień posortowanych po created_at (najstarsze pierwsze)

    Args:
        page_id: ID strony Offer

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
    page = OfferPage.query.get(page_id)
    if not page:
        raise ValueError(f"Strona Offer o ID {page_id} nie istnieje")

    # Pobierz wszystkie zamówienia dla tej strony (bez anulowanych)
    orders = Order.query.filter_by(offer_page_id=page_id).filter(
        Order.status != 'anulowane'
    ).order_by(Order.created_at.asc()).all()

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
        section: OfferSection typu 'set'
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
            # Skip bonus items — they don't count toward set fulfillment
            if item.is_bonus:
                continue
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
                    selected_size=order_item.selected_size,
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
    Automatycznie aktualizuje statusy zamówień po closure Offer.

    Zamówienia są klasyfikowane jako:
    - Fully fulfilled: wszystkie items są fulfilled
    - Partially fulfilled: część items fulfilled, część unfulfilled
    - Not fulfilled: żaden item nie jest fulfilled

    Statusy docelowe są konfigurowalne przez ustawienia:
    - offer_closure_status_fully_fulfilled
    - offer_closure_status_partially_fulfilled
    - offer_closure_status_not_fulfilled

    Args:
        page_id: ID OfferPage
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

    page = OfferPage.query.get(page_id)
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

    status_fully = get_status_setting('offer_closure_status_fully_fulfilled', 'oczekujace')
    status_partially = get_status_setting('offer_closure_status_partially_fulfilled', 'oczekujace')
    status_not = get_status_setting('offer_closure_status_not_fulfilled', 'anulowane')

    orders = Order.query.filter_by(offer_page_id=page_id).all()

    counts = {
        'fully_fulfilled': 0,
        'partially_fulfilled': 0,
        'not_fulfilled': 0,
        'updated_order_ids': []
    }

    for order in orders:
        # Klasyfikacja zamówienia (pomijamy bonus items)
        non_bonus_items = [item for item in order.items if not item.is_bonus]
        fulfilled_items = [item for item in non_bonus_items if item.is_set_fulfilled is not False]
        unfulfilled_items = [item for item in non_bonus_items if item.is_set_fulfilled is False]

        total_items = len(non_bonus_items)
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
            old_status_name = order.status_display_name
            order.status = new_status
            order.updated_at = datetime.now()

            counts[fulfillment_type] += 1
            counts['updated_order_ids'].append(order.id)

            # Kolejkuj email o zmianie statusu
            if order.customer_email:
                counts.setdefault('_email_queue', []).append({
                    'order': order,
                    'old_status_name': old_status_name,
                })

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

    # Wyslij emaile o zmianie statusu (flush zeby status_display_name zwrocil nowa nazwe)
    email_queue = counts.pop('_email_queue', [])
    if email_queue:
        from utils.email_manager import EmailManager
        from utils.push_manager import PushManager
        db.session.flush()
        for data in email_queue:
            EmailManager.notify_status_change(
                data['order'],
                data['old_status_name'],
                data['order'].status_display_name
            )
            PushManager.notify_status_change(
                data['order'],
                data['old_status_name'],
                data['order'].status_display_name
            )

    return counts


def close_offer_page(page_id, user_id, send_emails=True):
    """
    Całkowicie zamyka stronę Offer.

    1. Sprawdza czy strona może być zamknięta (status='ended', not is_fully_closed)
    2. Wykonuje algorytm alokacji setów (zerowanie unfulfilled, split partial)
    3. Auto-anuluje zamówienia bez fulfilled items
    4. Przelicza total_amount dla wszystkich zamówień
    5. Zapisuje wyniki w bazie (atomowa transakcja)
    6. Opcjonalnie wysyła emaile do klientów

    Args:
        page_id: ID strony Offer
        user_id: ID użytkownika wykonującego zamknięcie
        send_emails: Czy wysyłać emaile do klientów (domyślnie True)

    Returns:
        dict: Wyniki zamknięcia
    """
    page = OfferPage.query.get(page_id)

    if not page:
        raise ValueError(f"Strona Offer o ID {page_id} nie istnieje")

    if page.status != 'ended':
        raise ValueError(f"Strona musi mieć status 'Zakończona' (ended), obecnie: {page.status}")

    if page.is_fully_closed:
        raise ValueError("Strona została już całkowicie zamknięta")

    try:
        # Zachowaj stare total_amount przed alokacją (do logowania)
        orders = Order.query.filter_by(offer_page_id=page_id).all()
        old_totals = {order.id: float(order.total_amount) if order.total_amount else 0 for order in orders}

        # 1. Wykonaj algorytm alokacji (ZMODYFIKOWANY - zeruje ceny, splituje partial)
        allocation_result = calculate_set_fulfillment(page_id)

        # 2. NOWE: Auto-aktualizuj statusy zamówień (konfigurowalne)
        status_update_result = auto_update_order_statuses(page_id, user_id)

        # 3. NOWE: Przelicz total_amount dla wszystkich zamówień
        orders = Order.query.filter_by(offer_page_id=page_id).all()
        for order in orders:
            order.recalculate_total_amount()

        # 3b. Log fulfillment per order (inline, przed commit)
        import json as _json
        from modules.admin.models import ActivityLog
        for order in orders:
            non_bonus = [item for item in order.items if not item.is_bonus]
            fulfilled_items = [item for item in non_bonus if item.is_set_fulfilled is not False]
            unfulfilled_items = [item for item in non_bonus if item.is_set_fulfilled is False]
            total_items = len(non_bonus)
            fulfilled_count = len(fulfilled_items)
            new_total = float(order.total_amount) if order.total_amount else 0
            old_total = old_totals.get(order.id, 0)

            db.session.add(ActivityLog(
                user_id=user_id,
                action='offer_closure_fulfillment',
                entity_type='order',
                entity_id=order.id,
                old_value=_json.dumps({'total_amount': old_total}),
                new_value=_json.dumps({
                    'total_items': total_items,
                    'fulfilled_items': fulfilled_count,
                    'unfulfilled_items': len(unfulfilled_items),
                    'old_total_amount': old_total,
                    'new_total_amount': new_total,
                    'offer_page_name': page.name,
                }),
            ))

        # 4. Ustaw flagę zamknięcia
        page.is_fully_closed = True
        page.closed_at = datetime.now()
        page.closed_by_id = user_id

        # 5. COMMIT - atomowa transakcja
        db.session.commit()

        current_app.logger.info(f"Offer page {page_id} closed successfully. "
                                f"Status updates: fully={status_update_result['fully_fulfilled']}, "
                                f"partially={status_update_result['partially_fulfilled']}, "
                                f"not_fulfilled={status_update_result['not_fulfilled']}")

        # 6. Wysyłka emaili (PO commit, żeby nie rollbackować przy błędzie email)
        if send_emails:
            try:
                # Email o closure (istniejący)
                send_closure_emails(page_id)

                # NOWE: Email o anulowaniu (tylko dla zamówień not_fulfilled)
                status_not_fulfilled_setting = Settings.query.filter_by(
                    key='offer_closure_status_not_fulfilled'
                ).first()

                if status_not_fulfilled_setting:
                    status_not = status_not_fulfilled_setting.value
                    not_fulfilled_orders = [
                        oid for oid in status_update_result['updated_order_ids']
                        if Order.query.get(oid).status == status_not
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
        current_app.logger.error(f"Błąd zamykania strony Offer {page_id}: {str(e)}")
        raise


def get_page_summary(page_id, include_financials=True):
    """
    Generuje podsumowanie sprzedaży dla zamkniętej strony Offer.

    Args:
        page_id: ID strony Offer
        include_financials: Czy uwzględniać dane finansowe (tylko Admin)

    Returns:
        dict: Podsumowanie sprzedaży
    """
    page = OfferPage.query.get(page_id)
    if not page:
        raise ValueError(f"Strona Offer o ID {page_id} nie istnieje")

    orders = Order.query.filter_by(offer_page_id=page_id).filter(
        Order.status != 'anulowane'
    ).order_by(Order.created_at.asc()).all()

    # Podstawowe statystyki
    total_orders = len(orders)
    unique_customers = len(set(
        order.user_id for order in orders if order.user_id
    ))

    # Przychód liczony tylko z produktów zrealizowanych (bez bonusów)
    # is_set_fulfilled = True -> zrealizowane w secie
    # is_set_fulfilled = None -> produkt spoza setu (zawsze realizowany)
    # is_set_fulfilled = False -> NIE zrealizowane (nie liczymy)
    total_revenue = 0.0
    total_bonus_items = 0
    for order in orders:
        for item in order.items:
            if item.is_bonus:
                total_bonus_items += item.quantity
                continue
            # Liczymy tylko zrealizowane produkty (True lub None)
            if item.is_set_fulfilled is not False:
                total_revenue += float(item.total) if item.total else 0

    # Zbierz informacje o setach (z macierzą slotów jak w live)
    sets_info = []
    set_sections = page.sections.filter_by(section_type='set').all()

    for section in set_sections:
        set_items = section.get_set_items_ordered()
        max_sets = section.set_max_sets or 0
        products_in_set = []

        # Collect all product IDs in this set section
        all_set_product_ids = []
        for item in set_items:
            for product in item.get_products():
                all_set_product_ids.append(product.id)

        # Query slot data: customer names + fulfillment status per product
        # Build sequential mapping from ALL OrderItems (chronologically)
        # to handle items without set_number
        slot_data_map = {}  # {product_id: {slot_number: {'customer': str, 'fulfilled': bool}}}
        if all_set_product_ids:
            # Include ALL orders (even cancelled by closure) to show unfulfilled slots with X
            slot_rows = db.session.query(
                OrderItem.product_id,
                OrderItem.quantity,
                OrderItem.is_set_fulfilled,
                User.first_name,
                User.last_name,
                User.email
            ).join(Order, OrderItem.order_id == Order.id
            ).join(User, Order.user_id == User.id
            ).filter(
                Order.offer_page_id == page_id,
                OrderItem.product_id.in_(all_set_product_ids),
                OrderItem.is_bonus != True,
            ).order_by(OrderItem.id.asc()).all()

            slot_counter = {}  # {product_id: next_slot_number}
            for pid, qty, is_fulfilled, fname, lname, email in slot_rows:
                name = f'{fname} {lname}'.strip() if (fname or lname) else email
                if pid not in slot_data_map:
                    slot_data_map[pid] = {}
                if pid not in slot_counter:
                    slot_counter[pid] = 1
                # After closure, unfulfilled items may have quantity=0 but still represent a slot
                effective_qty = max(qty, 1) if qty == 0 else qty
                for _ in range(effective_qty):
                    slot_data_map[pid][slot_counter[pid]] = {
                        'customer': name,
                        'fulfilled': is_fulfilled is True,
                    }
                    slot_counter[pid] += 1

        # When max_sets is 0 (no limit), determine effective columns from slot data
        if max_sets > 0:
            effective_max_sets = max_sets
        else:
            max_slots = max((max(slots.keys()) if slots else 0) for slots in slot_data_map.values()) if slot_data_map else 0
            effective_max_sets = max_slots

        for item in set_items:
            for product in item.get_products():
                product_slots = slot_data_map.get(product.id, {})
                slots = []
                total_ordered = 0
                fulfilled = 0
                unfulfilled = 0

                if effective_max_sets > 0:
                    for i in range(effective_max_sets):
                        set_num = i + 1  # 1-based
                        sd = product_slots.get(set_num)
                        if sd:
                            total_ordered += 1
                            if sd['fulfilled']:
                                fulfilled += 1
                            else:
                                unfulfilled += 1
                            slots.append({
                                'filled': True,
                                'fulfilled': sd['fulfilled'],
                                'customer': sd['customer'],
                            })
                        else:
                            slots.append({
                                'filled': False,
                                'fulfilled': None,
                                'customer': None,
                            })

                products_in_set.append({
                    'product_id': product.id,
                    'product_name': product.name,
                    'quantity_per_set': item.quantity_per_set,
                    'total_ordered': total_ordered,
                    'fulfilled': fulfilled,
                    'unfulfilled': unfulfilled,
                    'reserved': 0,
                    'slots': slots,
                    'is_full_set': False,
                })

        # Full set product (set_product_id) — dodatkowy wiersz
        full_set_sold = 0
        if section.set_product_id and section.set_product:
            full_set_qty = db.session.query(
                db.func.coalesce(db.func.sum(OrderItem.quantity), 0)
            ).filter(
                OrderItem.product_id == section.set_product_id,
                OrderItem.order_id.in_(
                    db.session.query(Order.id).filter(
                        Order.offer_page_id == page_id,
                        Order.status != 'anulowane'
                    )
                )
            ).scalar()
            full_set_qty = int(full_set_qty)
            full_set_sold = full_set_qty

            products_in_set.append({
                'product_id': section.set_product_id,
                'product_name': section.set_product.name,
                'quantity_per_set': 1,
                'total_ordered': full_set_qty,
                'fulfilled': full_set_qty,
                'unfulfilled': 0,
                'reserved': 0,
                'slots': [{'filled': full_set_qty > 0, 'customer': None}],
                'is_full_set': True,
            })

        # Oblicz kompletne sety (minimum ordered per produkt / qty_per_set)
        non_full_set = [p for p in products_in_set if not p['is_full_set']]
        if non_full_set:
            ordered_sets = min(
                p['total_ordered'] // p['quantity_per_set']
                for p in non_full_set
                if p['quantity_per_set'] > 0
            ) if any(p['quantity_per_set'] > 0 for p in non_full_set) else 0
        else:
            ordered_sets = 0

        total_sets_sold = ordered_sets + full_set_sold

        total_set_ordered = sum(p['total_ordered'] for p in products_in_set if not p['is_full_set'])
        total_set_fulfilled = sum(p['fulfilled'] for p in products_in_set if not p['is_full_set'])

        # Bonus items for this section
        bonus_items_count = db.session.query(
            db.func.coalesce(db.func.sum(OrderItem.quantity), 0)
        ).join(Order, OrderItem.order_id == Order.id
        ).filter(
            Order.offer_page_id == page_id,
            Order.status != 'anulowane',
            OrderItem.is_bonus == True,
            OrderItem.bonus_source_section_id == section.id,
        ).scalar()
        bonus_items_count = int(bonus_items_count)

        sets_info.append({
            'section_id': section.id,
            'set_name': section.set_name or 'Bez nazwy',
            'set_image': section.set_image,
            'set_max_sets': effective_max_sets,
            'has_limit': max_sets > 0,
            'ordered_sets': ordered_sets,
            'full_set_sold': full_set_sold,
            'total_sets_sold': total_sets_sold,
            'bonus_items_count': bonus_items_count,
            'complete_sets': ordered_sets,
            'products': products_in_set,
            'fulfillment_pct': round((total_set_fulfilled / total_set_ordered) * 100, 1) if total_set_ordered > 0 else 0,
            'total_ordered': total_set_ordered,
            'total_fulfilled': total_set_fulfilled,
        })

    # Lista zamówień z detalami
    orders_list = []
    for order in orders:
        items_details = []
        fulfilled_amount = 0.0  # Wartość tylko zrealizowanych produktów

        for item in order.items:
            item_total = float(item.total) if item.total else 0

            # Liczymy wartość tylko zrealizowanych produktów (bez bonusów)
            if not item.is_bonus and item.is_set_fulfilled is not False:
                fulfilled_amount += item_total

            item_data = {
                'product_id': item.product_id,
                'product_name': item.product_name,
                'selected_size': item.selected_size,
                'quantity': item.quantity,
                'price': float(item.price) if item.price else 0,
                'total': item_total,
                'is_set_fulfilled': item.is_set_fulfilled,
                'set_section_id': item.set_section_id,
                'is_full_set': item.is_full_set,
                'is_custom': item.is_custom,
                'is_bonus': item.is_bonus,
            }
            items_details.append(item_data)

        order_data = {
            'order_id': order.id,
            'order_number': order.order_number,
            'customer_name': order.customer_name,
            'customer_email': order.customer_email,
            'customer_phone': order.user.phone if order.user else None,
            'created_at': order.created_at,
            'total_amount': fulfilled_amount,  # Tylko zrealizowane produkty
            'order_items': items_details,
        }
        orders_list.append(order_data)

    # === Nowe metryki ===

    # Total items (zrealizowane, bez bonusów)
    total_items = 0
    for order in orders:
        for item in order.items:
            if item.is_bonus:
                continue
            if item.is_set_fulfilled is not False:
                total_items += item.quantity

    # Fulfillment % (realizacja setów)
    total_set_items_qty = 0
    fulfilled_set_items_qty = 0
    for order in orders:
        for item in order.items:
            if item.is_set_fulfilled is not None:
                total_set_items_qty += item.quantity
                if item.is_set_fulfilled:
                    fulfilled_set_items_qty += item.quantity

    fulfillment_pct = round((fulfilled_set_items_qty / total_set_items_qty) * 100, 1) if total_set_items_qty > 0 else 100.0

    # Orders by date (do wykresu) - zachowujemy dla kompatybilności
    from collections import Counter
    orders_by_date = Counter()
    for order in orders:
        if order.created_at:
            date_key = order.created_at.strftime('%Y-%m-%d')
            orders_by_date[date_key] += 1

    sorted_dates = sorted(orders_by_date.items())
    orders_by_date_list = [{'date': d, 'count': c} for d, c in sorted_dates]

    # Order timestamps (do Chart.js line chart - pełne ISO timestamps)
    order_timestamps = []
    for order in orders:
        if order.created_at:
            order_timestamps.append(order.created_at.isoformat())

    # Products aggregated (do Tab Produkty)
    products_agg = {}
    for order in orders:
        for item in order.items:
            key = (item.product_id, item.selected_size) if item.product_id else f"custom_{item.product_name}"

            if key not in products_agg:
                products_agg[key] = {
                    'product_id': item.product_id,
                    'product_name': item.product_name,
                    'selected_size': item.selected_size,
                    'total_quantity': 0,
                    'fulfilled_quantity': 0,
                    'unfulfilled_quantity': 0,
                    'non_set_quantity': 0,
                    'revenue': 0.0,
                    'order_count': 0,
                    'is_custom': item.is_custom,
                    'is_full_set': item.is_full_set,
                    'is_bonus': item.is_bonus,
                }

            p = products_agg[key]
            p['total_quantity'] += item.quantity
            p['order_count'] += 1

            if item.is_set_fulfilled is True:
                p['fulfilled_quantity'] += item.quantity
            elif item.is_set_fulfilled is False:
                p['unfulfilled_quantity'] += item.quantity
            else:
                p['non_set_quantity'] += item.quantity

            if include_financials:
                item_total = float(item.total) if item.total else 0
                if not item.is_bonus and item.is_set_fulfilled is not False:
                    p['revenue'] += item_total

    for key, p in products_agg.items():
        set_total = p['fulfilled_quantity'] + p['unfulfilled_quantity']
        if set_total > 0:
            p['fulfillment_pct'] = round((p['fulfilled_quantity'] / set_total) * 100, 1)
        else:
            p['fulfillment_pct'] = None

    products_aggregated = sorted(products_agg.values(), key=lambda x: x['total_quantity'], reverse=True)

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
        'total_items': total_items,
        'fulfillment_pct': fulfillment_pct,
        'orders_by_date': orders_by_date_list,
        'order_timestamps': order_timestamps,
        'products_aggregated': products_aggregated,
    }

    result['total_bonus_items'] = total_bonus_items

    if include_financials:
        result['total_revenue'] = total_revenue
        result['avg_order_value'] = round(total_revenue / total_orders, 2) if total_orders > 0 else 0

    return result


def get_live_summary(page_id, include_financials=True):
    """
    Generuje podsumowanie LIVE dla aktywnej/wstrzymanej/zakończonej strony Offer.
    W odróżnieniu od get_page_summary() — nie filtruje po is_set_fulfilled
    i nie wymaga is_fully_closed.

    Args:
        page_id: ID strony Offer
        include_financials: Czy uwzględniać dane finansowe (tylko Admin)

    Returns:
        dict: Podsumowanie LIVE
    """
    from collections import Counter

    page = OfferPage.query.get(page_id)
    if not page:
        raise ValueError(f"Strona Offer o ID {page_id} nie istnieje")

    orders = Order.query.filter_by(offer_page_id=page_id).filter(
        Order.status != 'anulowane'
    ).order_by(Order.created_at.asc()).all()

    # Podstawowe statystyki
    total_orders = len(orders)
    unique_customers = len(set(
        order.user_id for order in orders if order.user_id
    ))

    # Revenue = suma WSZYSTKICH itemów (bez filtrowania po fulfillment, bez bonusów)
    total_revenue = 0.0
    total_items = 0
    total_bonus_items = 0
    for order in orders:
        for item in order.items:
            if item.is_bonus:
                total_bonus_items += item.quantity
                continue
            total_revenue += float(item.total) if item.total else 0
            total_items += item.quantity

    # Aktywne rezerwacje
    from modules.offers.models import OfferReservation
    active_reservations = OfferReservation.query.filter_by(
        offer_page_id=page_id
    ).count()

    # Aktywne rezerwacje per product (ilości + imiona do tooltipów) — jedno zapytanie
    import time as _time
    from modules.auth.models import User
    now_ts = int(_time.time())
    active_reservations_by_product = {}
    reservation_customers_by_product = {}
    active_res_rows = db.session.query(
        OfferReservation.product_id,
        OfferReservation.quantity,
        User.first_name,
        User.last_name
    ).outerjoin(User, OfferReservation.user_id == User.id).filter(
        OfferReservation.offer_page_id == page_id,
        OfferReservation.expires_at > now_ts
    ).all()
    for pid, qty, first_name, last_name in active_res_rows:
        active_reservations_by_product[pid] = active_reservations_by_product.get(pid, 0) + int(qty)
        if pid not in reservation_customers_by_product:
            reservation_customers_by_product[pid] = []
        name = f"{first_name or ''} {last_name or ''}".strip() or 'Anonim'
        reservation_customers_by_product[pid].append(name)

    # Sety — macierz slotów (ordered vs available)
    sets_info = []
    set_sections = page.sections.filter_by(section_type='set').all()

    for section in set_sections:
        set_items = section.get_set_items_ordered()
        max_sets = section.set_max_sets or 0
        products_matrix = []

        # Collect all product IDs in this set section
        all_set_product_ids = []
        for item in set_items:
            for product in item.get_products():
                all_set_product_ids.append(product.id)

        # Query customer names per product — build sequential slot mapping
        # from ALL OrderItems (chronologically), excluding bonus items
        slot_customer_map = {}  # {product_id: {slot_number: customer_name}}
        if all_set_product_ids:
            customer_rows = db.session.query(
                OrderItem.product_id,
                OrderItem.quantity,
                User.first_name,
                User.last_name,
                User.email
            ).join(Order, OrderItem.order_id == Order.id
            ).join(User, Order.user_id == User.id
            ).filter(
                Order.offer_page_id == page_id,
                Order.status != 'anulowane',
                OrderItem.product_id.in_(all_set_product_ids),
                OrderItem.is_bonus != True,
            ).order_by(OrderItem.id.asc()).all()

            slot_counter = {}  # {product_id: next_slot_number}
            for pid, qty, fname, lname, email in customer_rows:
                name = f'{fname} {lname}'.strip() if (fname or lname) else email
                if pid not in slot_customer_map:
                    slot_customer_map[pid] = {}
                if pid not in slot_counter:
                    slot_counter[pid] = 1
                for _ in range(qty):
                    slot_customer_map[pid][slot_counter[pid]] = name
                    slot_counter[pid] += 1

        # First pass: collect ordered quantities (excluding bonus) to determine effective_max_sets
        product_ordered_qtys = {}
        for item in set_items:
            for product in item.get_products():
                ordered_qty = db.session.query(
                    db.func.coalesce(db.func.sum(OrderItem.quantity), 0)
                ).filter(
                    OrderItem.product_id == product.id,
                    OrderItem.is_bonus != True,
                    OrderItem.order_id.in_(
                        db.session.query(Order.id).filter(
                            Order.offer_page_id == page_id,
                            Order.status != 'anulowane'
                        )
                    )
                ).scalar()
                product_ordered_qtys[product.id] = int(ordered_qty)

        # When max_sets is 0 (no limit), use the highest ordered quantity as effective columns
        if max_sets > 0:
            effective_max_sets = max_sets
        else:
            effective_max_sets = max(product_ordered_qtys.values()) if product_ordered_qtys else 0

        for item in set_items:
            for product in item.get_products():
                ordered_qty = product_ordered_qtys[product.id]

                # Slots: objects with filled status + customer name
                product_customers = slot_customer_map.get(product.id, {})
                slots = []
                if effective_max_sets > 0:
                    for i in range(effective_max_sets):
                        set_num = i + 1  # 1-based
                        filled = i < ordered_qty
                        slots.append({
                            'filled': filled,
                            'customer': product_customers.get(set_num) if filled else None,
                        })

                reserved_qty = active_reservations_by_product.get(product.id, 0)

                products_matrix.append({
                    'product_id': product.id,
                    'product_name': product.name,
                    'quantity_per_set': item.quantity_per_set,
                    'total_ordered': ordered_qty,
                    'reserved': reserved_qty,
                    'reserved_customers': reservation_customers_by_product.get(product.id, []),
                    'slots': slots,
                    'is_full_set': False,
                })

        # Full set product (set_product_id) — dodatkowy wiersz
        if section.set_product_id and section.set_product:
            full_set_qty = db.session.query(
                db.func.coalesce(db.func.sum(OrderItem.quantity), 0)
            ).filter(
                OrderItem.product_id == section.set_product_id,
                OrderItem.order_id.in_(
                    db.session.query(Order.id).filter(
                        Order.offer_page_id == page_id,
                        Order.status != 'anulowane'
                    )
                )
            ).scalar()
            full_set_qty = int(full_set_qty)

            full_set_reserved = active_reservations_by_product.get(section.set_product_id, 0)

            products_matrix.append({
                'product_id': section.set_product_id,
                'product_name': section.set_product.name,
                'quantity_per_set': 1,
                'total_ordered': full_set_qty,
                'reserved': full_set_reserved,
                'reserved_customers': reservation_customers_by_product.get(section.set_product_id, []),
                'slots': [{'filled': full_set_qty > 0, 'customer': None}],
                'is_full_set': True,
            })

        # Oblicz kompletne sety (minimum slotów sprzedanych per produkt)
        if products_matrix:
            non_full_set = [p for p in products_matrix if not p['is_full_set']]
            if non_full_set:
                ordered_sets = min(
                    p['total_ordered'] // p['quantity_per_set']
                    for p in non_full_set
                    if p['quantity_per_set'] > 0
                ) if any(p['quantity_per_set'] > 0 for p in non_full_set) else 0
            else:
                ordered_sets = 0
        else:
            ordered_sets = 0

        # Łączna liczba setów sprzedanych = kompletne (ordered_sets) + pojedyncze (full_set product)
        full_set_entries = [p for p in products_matrix if p['is_full_set']]
        full_set_sold = full_set_entries[0]['total_ordered'] if full_set_entries else 0
        total_sets_sold = ordered_sets + full_set_sold

        # Bonus items for this section
        bonus_items_count = db.session.query(
            db.func.coalesce(db.func.sum(OrderItem.quantity), 0)
        ).join(Order, OrderItem.order_id == Order.id
        ).filter(
            Order.offer_page_id == page_id,
            Order.status != 'anulowane',
            OrderItem.is_bonus == True,
            OrderItem.bonus_source_section_id == section.id,
        ).scalar()
        bonus_items_count = int(bonus_items_count)

        sets_info.append({
            'section_id': section.id,
            'set_name': section.set_name or 'Bez nazwy',
            'set_image': section.set_image,
            'set_max_sets': effective_max_sets,
            'has_limit': max_sets > 0,
            'ordered_sets': ordered_sets,
            'full_set_sold': full_set_sold,
            'total_sets_sold': total_sets_sold,
            'bonus_items_count': bonus_items_count,
            'progress_pct': round((ordered_sets / max_sets) * 100, 1) if max_sets > 0 else 0,
            'products': products_matrix,
        })

    # Order timestamps (do Chart.js)
    order_timestamps = []
    for order in orders:
        if order.created_at:
            order_timestamps.append(order.created_at.isoformat())

    # Products aggregated
    products_agg = {}
    for order in orders:
        for item in order.items:
            key = (item.product_id, item.selected_size) if item.product_id else f"custom_{item.product_name}"

            if key not in products_agg:
                products_agg[key] = {
                    'product_id': item.product_id,
                    'product_name': item.product_name,
                    'selected_size': item.selected_size,
                    'total_quantity': 0,
                    'revenue': 0.0,
                    'order_count': 0,
                    'is_custom': item.is_custom,
                    'is_full_set': item.is_full_set,
                    'is_bonus': item.is_bonus,
                }

            p = products_agg[key]
            p['total_quantity'] += item.quantity
            p['order_count'] += 1

            if include_financials and not item.is_bonus:
                p['revenue'] += float(item.total) if item.total else 0

    products_aggregated = sorted(products_agg.values(), key=lambda x: x['total_quantity'], reverse=True)

    # Lista zamówień
    orders_list = []
    for order in orders:
        items_details = []
        for item in order.items:
            items_details.append({
                'product_id': item.product_id,
                'product_name': item.product_name,
                'selected_size': item.selected_size,
                'quantity': item.quantity,
                'price': float(item.price) if item.price else 0,
                'total': float(item.total) if item.total else 0,
                'is_full_set': item.is_full_set,
                'is_custom': item.is_custom,
                'is_bonus': item.is_bonus,
            })

        orders_list.append({
            'order_id': order.id,
            'order_number': order.order_number,
            'customer_name': order.customer_name,
            'customer_email': order.customer_email,
            'customer_phone': order.user.phone if order.user else None,
            'created_at': order.created_at,
            'total_amount': float(order.total_amount) if order.total_amount else 0,
            'order_items': items_details,
        })

    result = {
        'page_id': page_id,
        'page_name': page.name,
        'status': page.status,
        'starts_at': page.starts_at,
        'ends_at': page.ends_at,
        'total_orders': total_orders,
        'unique_customers': unique_customers,
        'total_items': total_items,
        'total_bonus_items': total_bonus_items,
        'active_reservations': active_reservations,
        'sets': sets_info,
        'orders': orders_list,
        'order_timestamps': order_timestamps,
        'products_aggregated': products_aggregated,
        'top_products': products_aggregated[:5],
    }

    if include_financials:
        result['total_revenue'] = total_revenue
        result['avg_order_value'] = round(total_revenue / total_orders, 2) if total_orders > 0 else 0

    return result


def send_cancellation_emails(page_id, cancelled_order_ids):
    """
    Wysyła emaile do klientów o anulowanych zamówieniach.

    Args:
        page_id: ID OfferPage
        cancelled_order_ids: Lista ID zamówień do anulowania
    """
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    page = OfferPage.query.get(page_id)
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

        EmailManager.notify_order_cancelled(
            order, page, cancelled_items,
            reason='Żaden z produktów w Twoim zamówieniu nie załapał się do kompletu.'
        )
        PushManager.notify_order_cancelled(
            order,
            reason='Żaden z produktów nie załapał się do kompletu.'
        )


def send_closure_emails(page_id):
    """
    Wysyła emaile do wszystkich klientów z podsumowaniem ich zamówień.
    ROZSZERZONE: Dodaje informacje finansowe i dane do przelewu.
    Używa batch sendingu (jedno połączenie SMTP) żeby uniknąć rate limitów.

    Args:
        page_id: ID strony Offer
    """
    from utils.email_sender import prepare_email, send_email_batch
    from utils.push_manager import PushManager
    from modules.payments.models import PaymentMethod
    from decimal import Decimal

    page = OfferPage.query.get(page_id)
    if not page:
        return

    orders = Order.query.filter_by(offer_page_id=page_id).all()

    # Pobierz aktywne metody płatności
    payment_methods_raw = PaymentMethod.get_active()

    email_messages = []

    for order in orders:
        if not order.customer_email:
            continue

        # Przygotuj listę produktów z ich statusem
        items = []
        fulfilled_items = []
        bonus_items = []
        for item in order.items:
            if item.is_bonus:
                bonus_items.append({
                    'product_name': '\U0001f381 GRATIS: ' + item.product_name,
                    'quantity': item.quantity,
                    'price': 0.0,
                    'is_fulfilled': True,
                    'is_bonus': True,
                })
                continue
            is_fulfilled = item.is_set_fulfilled if item.is_set_fulfilled is not None else True
            items.append({
                'product_name': item.product_name,
                'selected_size': item.selected_size,
                'quantity': item.quantity,
                'price': float(item.price) if item.price else 0.0,
                'is_fulfilled': is_fulfilled,
            })
            if is_fulfilled:
                fulfilled_items.append(item)

        # Dołącz bonusy na koniec listy produktów (tylko jeśli są zrealizowane produkty)
        if fulfilled_items:
            items.extend(bonus_items)

        # KRYTYCZNE: Pomiń zamówienia bez żadnych zrealizowanych produktów
        # Te zamówienia dostają email o anulowaniu przez send_cancellation_emails()
        if not fulfilled_items or len(fulfilled_items) == 0:
            current_app.logger.info(
                f"Pomijam email closure dla zamówienia {order.order_number} - "
                f"brak zrealizowanych produktów (email anulowania zostanie wysłany osobno)"
            )
            continue

        # Oblicz sumę TYLKO zrealizowanych produktów
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
            title = (method.transfer_title or '').replace('[NUMER ZAMÓWIENIA]', order.order_number)
            additional = (method.additional_info or '').replace('[NUMER ZAMÓWIENIA]', order.order_number)

            payment_methods.append({
                'name': method.name,
                'recipient': method.recipient,
                'account_number': method.account_number,
                'account_number_label': method.account_number_label,
                'code': method.code,
                'code_label': method.code_label,
                'transfer_title': title,
                'additional_info': additional
            })

        # Przygotuj URL do uploadu płatności
        upload_payment_url = url_for('orders.client_detail',
                                     order_id=order.id,
                                     _external=True) + '?action=upload_payment'

        # Przygotuj email (bez wysyłania)
        msg = prepare_email(
            to=order.customer_email,
            subject=f'Podsumowanie zamówienia - {page.name} - ThunderOrders',
            template='offer_closure',
            customer_name=order.customer_name,
            page_name=page.name,
            items=items,
            fulfilled_items=[{
                'product_name': fi.product_name,
                'quantity': fi.fulfilled_quantity if fi.fulfilled_quantity is not None else fi.quantity,
                'price': float(fi.price) if fi.price else 0.0,
            } for fi in fulfilled_items],
            fulfilled_total=fulfilled_total,
            shipping_cost=shipping_cost,
            grand_total=grand_total,
            order_number=order.order_number,
            payment_methods=payment_methods,
            upload_payment_url=upload_payment_url
        )
        if msg:
            email_messages.append(msg)

        # Push notification (nie wymaga SMTP)
        PushManager.notify_offer_closure(order, grand_total=grand_total)

    # Wyślij wszystkie emaile batch'em (jedno połączenie SMTP)
    if email_messages:
        current_app.logger.info(f"Sending {len(email_messages)} closure emails in batch for page {page_id}")
        send_email_batch(email_messages)
