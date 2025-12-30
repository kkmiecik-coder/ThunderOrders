"""
Exclusive Notifications Module
Moduł do obsługi powiadomień email o powrocie dostępności produktów na stronach Exclusive.
"""

from flask import url_for, current_app
from extensions import db
from modules.exclusive.models import ExclusiveProductNotificationSubscription, ExclusivePage
from modules.products.models import Product
from utils.email_sender import send_back_in_stock_email
from modules.auth.models import get_local_now
import logging

logger = logging.getLogger(__name__)


def send_notifications_for_product_availability(page_id, product_id, old_available, new_available):
    """
    Sprawdza czy produkt stał się dostępny i wysyła powiadomienia.

    Args:
        page_id (int): ID strony exclusive
        product_id (int): ID produktu
        old_available (int): Poprzednia dostępność (0 = niedostępny)
        new_available (int): Nowa dostępność (>0 = dostępny)

    Returns:
        int: Liczba wysłanych powiadomień
    """
    # Produkt musi stać się dostępny (było 0, teraz >0)
    if old_available > 0 or new_available <= 0:
        return 0

    # Pobierz stronę i produkt
    page = ExclusivePage.query.get(page_id)
    product = Product.query.get(product_id)

    if not page or not product:
        logger.warning(f"Page {page_id} or product {product_id} not found for notification")
        return 0

    # Pobierz subskrypcje dla tego produktu na tej stronie, które nie zostały jeszcze powiadomione
    subscriptions = ExclusiveProductNotificationSubscription.query.filter_by(
        exclusive_page_id=page_id,
        product_id=product_id,
        notified=False
    ).all()

    if not subscriptions:
        return 0

    # Przygotuj dane do emaila
    product_image_url = None
    if product.images:
        primary_image = next((img for img in product.images if img.is_primary), None)
        if not primary_image and product.images:
            primary_image = product.images[0]
        if primary_image:
            product_image_url = f"https://thunderorders.cloud/static/uploads/products/{primary_image.filename}"

    exclusive_page_url = f"https://thunderorders.cloud/exclusive/{page.token}"

    sent_count = 0

    for subscription in subscriptions:
        # Pobierz email
        if subscription.user_id:
            from modules.auth.models import User
            user = User.query.get(subscription.user_id)
            if user:
                email = user.email
            else:
                continue
        else:
            email = subscription.guest_email

        if not email:
            continue

        try:
            # Wyślij email
            success = send_back_in_stock_email(
                email=email,
                product_name=product.name,
                product_image_url=product_image_url,
                exclusive_page_name=page.name,
                exclusive_page_url=exclusive_page_url
            )

            if success:
                # Oznacz jako wysłane
                subscription.notified = True
                subscription.notified_at = get_local_now()
                sent_count += 1
                logger.info(f"Sent back-in-stock notification to {email} for product {product_id} on page {page_id}")
        except Exception as e:
            logger.error(f"Failed to send notification to {email}: {str(e)}")

    # Zapisz zmiany
    db.session.commit()

    return sent_count


def check_and_send_notifications_for_section(page_id, section_id, old_max, new_max):
    """
    Sprawdza produkty w sekcji i wysyła powiadomienia jeśli któryś stał się dostępny.

    Używane przez auto-increase gdy zwiększa się set_max_sets dla sekcji typu 'set'.

    Args:
        page_id (int): ID strony exclusive
        section_id (int): ID sekcji
        old_max (int): Poprzedni limit (set_max_sets)
        new_max (int): Nowy limit (set_max_sets)

    Returns:
        int: Liczba wysłanych powiadomień
    """
    from modules.exclusive.models import ExclusiveSection, ExclusiveSetItem
    from modules.exclusive.reservation import get_sold_counts

    section = ExclusiveSection.query.get(section_id)
    if not section:
        return 0

    total_sent = 0

    # Pobierz produkty z sekcji
    product_ids = []

    if section.section_type == 'set':
        # Sekcja typu set - pobierz produkty z set_items
        set_items = ExclusiveSetItem.query.filter_by(section_id=section_id).all()
        for item in set_items:
            if item.product_id:
                product_ids.append(item.product_id)
            elif item.variant_group_id:
                # Produkty z grupy wariantów
                from modules.products.models import Product, VariantGroup
                vg_products = Product.query.join(
                    Product.variant_groups
                ).filter(
                    VariantGroup.id == item.variant_group_id,
                    Product.is_active == True
                ).all()
                product_ids.extend([p.id for p in vg_products])

    elif section.section_type == 'product' and section.product_id:
        product_ids.append(section.product_id)
        old_max = section.max_quantity if hasattr(section, '_old_max_quantity') else 0
        new_max = section.max_quantity

    elif section.section_type == 'variant_group' and section.variant_group_id:
        from modules.products.models import Product, VariantGroup
        vg_products = Product.query.join(
            Product.variant_groups
        ).filter(
            VariantGroup.id == section.variant_group_id,
            Product.is_active == True
        ).all()
        product_ids.extend([p.id for p in vg_products])

    if not product_ids:
        return 0

    # Pobierz sprzedane ilości
    sold_counts = get_sold_counts(page_id, product_ids)

    for product_id in product_ids:
        sold = sold_counts.get(product_id, 0)

        # Oblicz dostępność przed i po zmianie
        old_available = max(0, old_max - sold)
        new_available = max(0, new_max - sold)

        # Jeśli produkt stał się dostępny, wyślij powiadomienia
        if old_available <= 0 and new_available > 0:
            sent = send_notifications_for_product_availability(
                page_id=page_id,
                product_id=product_id,
                old_available=old_available,
                new_available=new_available
            )
            total_sent += sent

    return total_sent


def check_and_send_notifications_for_product_section(page_id, section, old_max_quantity):
    """
    Sprawdza pojedynczą sekcję typu 'product' lub 'variant_group' i wysyła powiadomienia.

    Używane przy ręcznej zmianie max_quantity przez admina.

    Args:
        page_id (int): ID strony exclusive
        section: Obiekt ExclusiveSection
        old_max_quantity (int): Poprzedni limit max_quantity

    Returns:
        int: Liczba wysłanych powiadomień
    """
    from modules.exclusive.reservation import get_sold_counts

    new_max_quantity = section.max_quantity

    if old_max_quantity is None or new_max_quantity is None:
        return 0

    # Pobierz produkty z sekcji
    product_ids = []

    if section.section_type == 'product' and section.product_id:
        product_ids.append(section.product_id)

    elif section.section_type == 'variant_group' and section.variant_group_id:
        from modules.products.models import Product, VariantGroup
        vg_products = Product.query.join(
            Product.variant_groups
        ).filter(
            VariantGroup.id == section.variant_group_id,
            Product.is_active == True
        ).all()
        product_ids.extend([p.id for p in vg_products])

    if not product_ids:
        return 0

    # Pobierz sprzedane ilości
    sold_counts = get_sold_counts(page_id, product_ids)

    total_sent = 0

    for product_id in product_ids:
        sold = sold_counts.get(product_id, 0)

        # Oblicz dostępność przed i po zmianie
        old_available = max(0, old_max_quantity - sold)
        new_available = max(0, new_max_quantity - sold)

        # Jeśli produkt stał się dostępny, wyślij powiadomienia
        if old_available <= 0 and new_available > 0:
            sent = send_notifications_for_product_availability(
                page_id=page_id,
                product_id=product_id,
                old_available=old_available,
                new_available=new_available
            )
            total_sent += sent

    return total_sent
