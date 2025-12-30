"""
Auto-increase Module for Exclusive Pages
=========================================

Automatyczne zwiększanie maksymalnej liczby setów w sekcjach 'set'
na stronach exclusive, oparte na konfigurowalnych progach sprzedaży.

Architektura: 1 set = 1 sztuka każdego produktu z setu (współdzielą set_max_sets)

System trzech parametrów:
- Próg wyprzedania produktu (%) - jaki % max setów musi się wyprzedać dla pojedynczego produktu
- Próg wyprzedanych produktów w secie (%) - jaki % produktów musi osiągnąć próg
- Zwiększenie max o (szt.) - o ile zwiększyć set_max_sets dla całej sekcji
"""

import json
from extensions import db
from modules.exclusive.models import ExclusivePage, ExclusiveSection, ExclusiveAutoIncreaseLog, ExclusiveSetItem
from modules.orders.models import Order, OrderItem


def get_product_sales_count(product_id, page_id):
    """
    Zwraca liczbę sprzedanych sztuk danego produktu dla tej strony exclusive.

    Args:
        product_id (int): ID produktu
        page_id (int): ID strony exclusive

    Returns:
        int: Liczba sprzedanych sztuk
    """
    sold_count = db.session.query(db.func.sum(OrderItem.quantity)).join(Order).filter(
        OrderItem.product_id == product_id,
        Order.exclusive_page_id == page_id
    ).scalar()

    return sold_count or 0


def check_and_apply_auto_increase(page_id):
    """
    Główna funkcja sprawdzająca i aplikująca auto-zwiększanie max setów.

    ARCHITEKTURA: 1 set = 1 sztuka każdego produktu z setu
    Wszystkie produkty w secie współdzielą parametr set_max_sets.

    Algorytm:
    1. Pobierz globalne ustawienia auto-increase z tabeli settings
    2. Sprawdź czy auto-zwiększanie jest włączone globalnie
    3. Pobierz stronę exclusive i sprawdź czy jest aktywna
    4. Pobierz wszystkie sekcje typu 'set'
    5. Dla każdej sekcji:
       a. Pobierz wszystkie produkty z set_items (wykluczając set_product_id)
       b. Dla każdego produktu policz sprzedaż (liczba zamówionych setów tego produktu)
       c. Oblicz % sprzedaży dla każdego produktu: (sprzedane / set_max_sets) * 100
       d. Policz ile produktów osiągnęło próg wyprzedania produktu
       e. Oblicz % produktów spełniających próg: (produkty_na_progu / wszystkie_produkty) * 100
       f. Jeśli % >= próg wyprzedanych produktów w secie → zwiększ set_max_sets i zaloguj

    Args:
        page_id (int): ID strony exclusive

    Returns:
        list: Lista ID sekcji gdzie nastąpiło zwiększenie set_max_sets
    """
    from modules.auth.models import Settings

    print(f"[AUTO-INCREASE] Starting check for page_id={page_id}")

    # Helper function to get setting value
    def get_setting_value(key, default):
        setting = Settings.query.filter_by(key=key).first()
        return setting.value if setting else default

    # Pobierz globalne ustawienia auto-increase
    auto_increase_enabled = get_setting_value('auto_increase_enabled', 'false') == 'true'
    print(f"[AUTO-INCREASE] Enabled: {auto_increase_enabled}")

    # Sprawdź czy auto-zwiększanie jest włączone globalnie
    if not auto_increase_enabled:
        print("[AUTO-INCREASE] Disabled globally, exiting")
        return []

    # Pobierz ustawienia progów
    auto_increase_product_threshold = int(get_setting_value('auto_increase_product_threshold', '100'))
    auto_increase_set_threshold = int(get_setting_value('auto_increase_set_threshold', '50'))
    auto_increase_amount = int(get_setting_value('auto_increase_amount', '1'))
    print(f"[AUTO-INCREASE] Thresholds: product={auto_increase_product_threshold}%, set={auto_increase_set_threshold}%, amount={auto_increase_amount}")

    # Pobierz stronę exclusive
    page = ExclusivePage.query.get(page_id)
    if not page:
        print(f"[AUTO-INCREASE] Page {page_id} not found")
        return []

    # Sprawdź czy strona jest aktywna
    if page.status != 'active':
        print(f"[AUTO-INCREASE] Page {page_id} is not active (status={page.status})")
        return []

    # Pobierz wszystkie sekcje typu 'set'
    set_sections = page.sections.filter_by(section_type='set').all()
    print(f"[AUTO-INCREASE] Found {len(set_sections)} set sections")

    increased_sections = []

    for section in set_sections:
        print(f"[AUTO-INCREASE] Checking section {section.id}, set_max_sets={section.set_max_sets}")
        # Sprawdź czy sekcja ma ustawiony set_max_sets
        if not section.set_max_sets or section.set_max_sets <= 0:
            print(f"[AUTO-INCREASE] Section {section.id} has no set_max_sets, skipping")
            continue

        # Pobierz wszystkie produkty z setu (wykluczając set_product_id)
        set_items = section.set_items.all()
        if not set_items:
            print(f"[AUTO-INCREASE] Section {section.id} has no set_items, skipping")
            continue

        # Zbierz wszystkie ID produktów (wykluczamy set_product_id)
        # Obsługujemy zarówno pojedyncze produkty jak i grupy wariantowe
        product_ids = []
        for item in set_items:
            if item.product_id and item.product_id != section.set_product_id:
                # Pojedynczy produkt
                product_ids.append(item.product_id)
            elif item.variant_group_id:
                # Grupa wariantowa - pobierz wszystkie produkty z grupy
                if item.variant_group and item.variant_group.products:
                    for product in item.variant_group.products:
                        if product.id != section.set_product_id and product.is_active:
                            product_ids.append(product.id)

        if not product_ids:
            print(f"[AUTO-INCREASE] Section {section.id} has no valid products (excluding set_product_id={section.set_product_id}), skipping")
            continue

        total_products = len(product_ids)
        print(f"[AUTO-INCREASE] Section {section.id} has {total_products} products: {product_ids}")
        products_sold_count = {}
        products_at_threshold = []

        # Dla każdego produktu policz sprzedaż i sprawdź próg
        for product_id in product_ids:
            sold_count = get_product_sales_count(product_id, page_id)
            # Konwertuj do int dla JSON serialization (może być Decimal z DB)
            products_sold_count[product_id] = int(sold_count) if sold_count else 0

            # Oblicz % sprzedaży dla tego produktu
            if section.set_max_sets > 0:
                product_percentage = (sold_count / section.set_max_sets) * 100
            else:
                product_percentage = 0

            print(f"[AUTO-INCREASE]   Product {product_id}: sold={sold_count}, percentage={product_percentage:.1f}%")

            # Sprawdź czy produkt osiągnął próg wyprzedania produktu
            if product_percentage >= auto_increase_product_threshold:
                products_at_threshold.append(product_id)
                print(f"[AUTO-INCREASE]     ✓ Product {product_id} reached threshold")

        # Policz % produktów które spełniły warunek
        if total_products > 0:
            set_percentage = (len(products_at_threshold) / total_products) * 100
        else:
            set_percentage = 0

        # Sprawdź czy warunek auto-zwiększania jest spełniony
        print(f"[AUTO-INCREASE] Section {section.id}: {len(products_at_threshold)}/{total_products} products at threshold ({set_percentage:.1f}% >= {auto_increase_set_threshold}%)")
        if set_percentage >= auto_increase_set_threshold:
            # WARUNEK SPEŁNIONY - zwiększ max setów
            print(f"[AUTO-INCREASE] ✓ Condition met! Increasing from {section.set_max_sets} to {section.set_max_sets + auto_increase_amount}")

            old_max = section.set_max_sets
            new_max = old_max + auto_increase_amount

            # Zaktualizuj set_max_sets
            section.set_max_sets = new_max

            # Stwórz wpis w logu
            log_entry = ExclusiveAutoIncreaseLog(
                exclusive_page_id=page_id,
                section_id=section.id,
                old_max_quantity=old_max,
                new_max_quantity=new_max,
                products_at_threshold=json.dumps(products_at_threshold),
                total_products_in_set=total_products,
                products_sold_count=json.dumps(products_sold_count),
                trigger_product_threshold=auto_increase_product_threshold,
                trigger_set_threshold=auto_increase_set_threshold,
                trigger_increase_amount=auto_increase_amount
            )
            db.session.add(log_entry)

            # Dodaj do listy zwiększonych sekcji
            increased_sections.append(section.id)

    # Zapisz wszystkie zmiany PRZED próbą logowania do activity_log
    if increased_sections:
        db.session.commit()
        print(f"[AUTO-INCREASE] Changes committed for sections: {increased_sections}")

        # Wyślij powiadomienia o dostępności dla zwiększonych sekcji
        for section_id in increased_sections:
            try:
                section = ExclusiveSection.query.get(section_id)
                if section:
                    from utils.exclusive_notifications import check_and_send_notifications_for_section
                    # old_max i new_max są już zapisane w logu, pobierz je
                    log_entry = ExclusiveAutoIncreaseLog.query.filter_by(
                        section_id=section_id
                    ).order_by(ExclusiveAutoIncreaseLog.triggered_at.desc()).first()
                    if log_entry:
                        sent_count = check_and_send_notifications_for_section(
                            page_id=page_id,
                            section_id=section_id,
                            old_max=log_entry.old_max_quantity,
                            new_max=log_entry.new_max_quantity
                        )
                        if sent_count > 0:
                            print(f"[AUTO-INCREASE] Sent {sent_count} back-in-stock notifications for section {section_id}")
            except Exception as e:
                print(f"[AUTO-INCREASE] Failed to send notifications for section {section_id}: {e}")

        # Zaloguj do activity log (osobna operacja, nie blokuje głównej zmiany)
        for section_id in increased_sections:
            try:
                from utils.activity_logger import log_activity
                log_activity(
                    user=None,  # System action
                    action='exclusive_auto_increase_triggered',
                    entity_type='ExclusiveSection',
                    entity_id=section_id,
                    old_value=None,
                    new_value=json.dumps({'section_id': section_id, 'increased': True})
                )
            except Exception as e:
                # Nie przerywaj procesu jeśli logowanie nie zadziała
                print(f"[AUTO-INCREASE] Failed to log activity (non-critical): {e}")

    return increased_sections
