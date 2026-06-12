"""Serwis koszyka i checkoutu on-hand — wspólny dla weba i mobilnego API.

Logika przeniesiona 1:1 z modules/client/shop.py (trasy koszyka i checkoutu).
Serwis zwraca kody maszynowe + dokładne obecne komunikaty PL weba; warstwa
prezentacji (web / mobile) mapuje wynik na swoją odpowiedź.
"""

from collections import namedtuple
from decimal import Decimal

from extensions import db
from sqlalchemy import func

from modules.products.models import Product, CartItem, ProductInteraction
from modules.orders.models import (
    Order, OrderItem,
    ShippingRequest, ShippingRequestOrder, ShippingRequestStatus,
)
from modules.orders.utils import generate_order_number
from modules.auth.models import Settings, ShippingAddress, User
from utils.activity_logger import log_activity
from modules.client.shop_service import slugify


CartResult = namedtuple('CartResult', 'ok code message status extras')
# ok=True:  code/message None, extras np. {'cart_count': n}
# ok=False: code maszynowy, message = DOKŁADNY dotychczasowy komunikat PL weba, status HTTP


# ---------------------------------------------------------------------------
# Koszyk
# ---------------------------------------------------------------------------

def get_cart_count(user_id):
    """Return total quantity of items in user's cart."""
    return db.session.query(
        func.coalesce(func.sum(CartItem.quantity), 0)
    ).filter(
        CartItem.user_id == user_id
    ).scalar()


def build_cart_data(user_id):
    """Zawartość koszyka z walidacją stocku.

    Zwraca (cart_data: list[dict], total: float, count: int) — dict dokładnie
    jak dotychczasowa trasa api_cart (price float, image_url '/static/...').
    """
    items = CartItem.query.filter_by(
        user_id=user_id
    ).order_by(CartItem.created_at.desc()).all()

    cart_data = []
    for item in items:
        product = item.product
        available = product.quantity if product and product.is_active else 0
        img = product.primary_image if product else None
        cart_data.append({
            'id': item.id,
            'product_id': item.product_id,
            'name': product.name if product else 'Produkt usunięty',
            'price': float(product.sale_price) if product and product.sale_price else 0,
            'quantity': item.quantity,
            'available': available,
            'image_url': f'/static/{img.path_compressed}' if img else None,
            'is_available': available > 0 and product.is_active if product else False,
            'slug': slugify(product.name) if product else '',
            'size': product.sizes[0].name if product and product.sizes else None,
        })

    total = sum(i['price'] * i['quantity'] for i in cart_data if i['is_available'])
    count = sum(i['quantity'] for i in cart_data if i['is_available'])
    return cart_data, round(total, 2), count


def add_to_cart(user_id, product_id, quantity):
    """Dodaj produkt do koszyka (scala z istniejącą pozycją)."""
    if not product_id:
        return CartResult(False, 'missing_product_id', 'Brak ID produktu.', 400, None)

    product = Product.query.get(product_id)
    if not product or not product.is_active:
        return CartResult(False, 'product_not_found',
                          'Produkt nie istnieje lub jest nieaktywny.', 404, None)

    # Must be on-hand type
    if not product.product_type or product.product_type.slug != 'on-hand':
        return CartResult(False, 'not_on_hand',
                          'Ten produkt nie jest dostępny w sklepie.', 400, None)

    if product.quantity <= 0:
        return CartResult(False, 'out_of_stock',
                          'Produkt jest niedostępny (brak na stanie).', 400, None)

    # Check if already in cart
    existing = CartItem.query.filter_by(
        user_id=user_id,
        product_id=product_id,
    ).first()

    if existing:
        new_qty = existing.quantity + quantity
        if new_qty > product.quantity:
            return CartResult(
                False, 'exceeds_stock',
                f'Nie można dodać więcej. Dostępne: {product.quantity}, w koszyku: {existing.quantity}.',
                400, {'available': product.quantity})
        existing.quantity = new_qty
    else:
        if quantity > product.quantity:
            return CartResult(
                False, 'exceeds_stock',
                f'Żądana ilość ({quantity}) przekracza dostępną ({product.quantity}).',
                400, {'available': product.quantity})
        cart_item = CartItem(
            user_id=user_id,
            product_id=product_id,
            quantity=quantity,
        )
        db.session.add(cart_item)

    # Record interaction
    interaction = ProductInteraction(
        user_id=user_id,
        product_id=product_id,
        interaction_type='cart_add',
    )
    db.session.add(interaction)
    db.session.commit()

    return CartResult(True, None, None, 200, {'cart_count': get_cart_count(user_id)})


def update_cart_item(user_id, item_id, quantity):
    """Zmień ilość pozycji koszyka (quantity<=0 usuwa pozycję)."""
    try:
        quantity = int(quantity)
    except (ValueError, TypeError):
        return CartResult(False, 'invalid_quantity', 'Ilość musi być liczbą.', 400, None)

    if not item_id:
        return CartResult(False, 'missing_item_id', 'Brak wymaganych parametrów.', 400, None)

    item = CartItem.query.filter_by(id=item_id, user_id=user_id).first()
    if not item:
        return CartResult(False, 'item_not_found', 'Nie znaleziono elementu koszyka.', 404, None)

    if quantity <= 0:
        db.session.delete(item)
        db.session.commit()
        return CartResult(True, None, None, 200, {'cart_count': get_cart_count(user_id)})

    product = item.product
    if product and quantity > product.quantity:
        return CartResult(False, 'exceeds_stock',
                          f'Dostępna ilość: {product.quantity}.', 400,
                          {'available': product.quantity})

    item.quantity = quantity
    db.session.commit()
    return CartResult(True, None, None, 200, {'cart_count': get_cart_count(user_id)})


def remove_cart_item(user_id, item_id):
    """Usuń pozycję z koszyka."""
    if not item_id:
        return CartResult(False, 'missing_item_id', 'Brak ID elementu.', 400, None)

    item = CartItem.query.filter_by(id=item_id, user_id=user_id).first()
    if not item:
        return CartResult(False, 'item_not_found', 'Nie znaleziono elementu koszyka.', 404, None)

    db.session.delete(item)
    db.session.commit()
    return CartResult(True, None, None, 200, {'cart_count': get_cart_count(user_id)})


# ---------------------------------------------------------------------------
# Checkout on-hand
# ---------------------------------------------------------------------------

CheckoutResult = namedtuple(
    'CheckoutResult', 'ok code message status order stock_errors extras')


def get_initial_shipping_status():
    """Determine the initial status slug for a new shipping request."""
    setting = Settings.query.filter_by(key='shipping_request_default_status').first()
    if setting and setting.value:
        status = ShippingRequestStatus.query.filter_by(slug=setting.value, is_active=True).first()
        if status:
            return status.slug
    status = ShippingRequestStatus.query.filter_by(is_initial=True, is_active=True).first()
    if status:
        return status.slug
    status = ShippingRequestStatus.query.filter_by(is_active=True).order_by(ShippingRequestStatus.sort_order).first()
    return status.slug if status else 'nowe'


def place_order_on_hand(user_id, create_shipping=False, address_id=None):
    """Złóż zamówienie on-hand: walidacja stocku, Order + opcjonalny ShippingRequest.

    Zwraca CheckoutResult. Mechanika 1:1 z webowym checkout_place (atomowa
    re-walidacja stocku z blokadą wiersza).
    """
    # 1. Get cart items
    items = CartItem.query.filter_by(user_id=user_id).all()
    if not items:
        return CheckoutResult(False, 'cart_empty', 'Koszyk jest pusty.', 400,
                              None, None, None)

    # 2. Validate stock for ALL items — collect every error
    stock_errors = []
    for item in items:
        product = item.product
        if not product or not product.is_active:
            stock_errors.append({
                'product_id': item.product_id,
                'error': 'Produkt nie istnieje lub jest nieaktywny.',
                'available': 0,
            })
            continue
        if product.quantity == 0:
            stock_errors.append({
                'product_id': product.id,
                'error': f'{product.name} — wyprzedany.',
                'available': 0,
            })
            continue
        if product.quantity < item.quantity:
            stock_errors.append({
                'product_id': product.id,
                'error': f'{product.name} — dostępne tylko {product.quantity} szt.',
                'available': product.quantity,
            })

    if stock_errors:
        return CheckoutResult(False, 'stock_errors', None, 400,
                              None, stock_errors, None)

    # 3. Shipping validation
    address = None
    if create_shipping:
        if not address_id:
            return CheckoutResult(False, 'address_required',
                                  'Wybierz adres dostawy.', 400, None, None, None)
        address = ShippingAddress.query.filter_by(
            id=address_id,
            user_id=user_id,
            is_active=True,
        ).first()
        if not address:
            return CheckoutResult(False, 'address_not_found',
                                  'Wybrany adres nie istnieje.', 400, None, None, None)

    # 4. Create order
    try:
        order_number = generate_order_number('on_hand')
        total = sum(
            (item.product.sale_price or Decimal('0')) * item.quantity
            for item in items
            if item.product
        )

        order = Order(
            order_number=order_number,
            user_id=user_id,
            order_type='on_hand',
            status='nowe',
            total_amount=total,
            payment_stages=2,
        )
        db.session.add(order)
        db.session.flush()  # get order.id

        # 5. Create order items, decrease stock, record interaction
        # Re-validate stock with row lock to prevent race conditions
        ga_items = []          # GA4 Enhanced Ecommerce items[]
        total_items_count = 0
        for item in items:
            product = Product.query.with_for_update().get(item.product_id)
            if not product or product.quantity < item.quantity:
                db.session.rollback()
                return CheckoutResult(
                    False, 'stock_conflict',
                    f'Produkt "{product.name if product else "?"}" został właśnie wyprzedany. Odśwież stronę.',
                    409, None, None, None)

            selected_size = product.sizes[0].name if product.sizes else None

            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=item.quantity,
                price=product.sale_price,
                total=(product.sale_price or Decimal('0')) * item.quantity,
                selected_size=selected_size,
            )
            db.session.add(order_item)

            ga_items.append({
                'item_id': product.sku or str(product.id),
                'item_name': product.name,
                'price': float(product.sale_price or 0),
                'quantity': item.quantity,
            })
            total_items_count += item.quantity

            product.quantity -= item.quantity

            interaction = ProductInteraction(
                user_id=user_id,
                product_id=product.id,
                interaction_type='purchase',
            )
            db.session.add(interaction)

        # 6. Optional shipping request
        shipping_request_number = None
        if create_shipping and address:
            initial_status = get_initial_shipping_status()
            sr = ShippingRequest(
                request_number=ShippingRequest.generate_request_number(),
                user_id=user_id,
                status=initial_status,
                address_type=address.address_type,
                shipping_name=address.shipping_name,
                shipping_address=address.shipping_address,
                shipping_postal_code=address.shipping_postal_code,
                shipping_city=address.shipping_city,
                shipping_voivodeship=address.shipping_voivodeship,
                shipping_country=address.shipping_country,
                pickup_courier=address.pickup_courier,
                pickup_point_id=address.pickup_point_id,
                pickup_address=address.pickup_address,
                pickup_postal_code=address.pickup_postal_code,
                pickup_city=address.pickup_city,
            )
            db.session.add(sr)
            db.session.flush()

            sro = ShippingRequestOrder(
                shipping_request_id=sr.id,
                order_id=order.id,
            )
            db.session.add(sro)
            shipping_request_number = sr.request_number

        # 7. Clear cart
        CartItem.query.filter_by(user_id=user_id).delete()

        db.session.commit()

        # 8. Log activity
        user = User.query.get(user_id)
        log_activity(
            user=user,
            action='order_created',
            entity_type='order',
            entity_id=order.id,
            new_value={'order_number': order_number, 'total': float(total)},
        )

        return CheckoutResult(True, None, None, 200, order, None, {
            'order_number': order_number,
            'total_amount': float(total),
            'items_count': total_items_count,
            'ga_items': ga_items,
            'shipping_request_number': shipping_request_number,
        })

    except Exception as e:
        db.session.rollback()
        from flask import current_app
        current_app.logger.exception('Checkout error for user %s: %s', user_id, e)
        return CheckoutResult(False, 'checkout_error',
                              'Wystąpił błąd podczas składania zamówienia.', 500,
                              None, None, None)
