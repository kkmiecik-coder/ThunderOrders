"""Serwis koszyka i checkoutu on-hand — wspólny dla weba i mobilnego API.

Logika przeniesiona 1:1 z modules/client/shop.py (trasy koszyka i checkoutu).
Serwis zwraca kody maszynowe + dokładne obecne komunikaty PL weba; warstwa
prezentacji (web / mobile) mapuje wynik na swoją odpowiedź.
"""

from collections import namedtuple

from extensions import db
from sqlalchemy import func

from modules.products.models import Product, CartItem, ProductInteraction
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
