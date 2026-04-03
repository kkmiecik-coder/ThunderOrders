"""
Client Shop Module
On-hand product shop - browsing, filtering, cart, and checkout.
"""

import re
import unicodedata
from decimal import Decimal
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from extensions import db
from modules.products.models import (
    Product, ProductType, ProductImage, Size, Manufacturer,
    CartItem, ProductInteraction,
    variant_products, product_sizes,
)
from modules.orders.models import (
    Order, OrderItem, OrderType,
    ShippingRequest, ShippingRequestOrder, ShippingRequestStatus,
)
from modules.orders.utils import generate_order_number
from modules.auth.models import Settings, ShippingAddress
from utils.activity_logger import log_activity
from sqlalchemy import func, and_, or_


shop_bp = Blueprint('shop', __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_POLISH_MAP = str.maketrans({
    '\u0105': 'a', '\u0104': 'A',   # ą Ą
    '\u0107': 'c', '\u0106': 'C',   # ć Ć
    '\u0119': 'e', '\u0118': 'E',   # ę Ę
    '\u0142': 'l', '\u0141': 'L',   # ł Ł
    '\u0144': 'n', '\u0143': 'N',   # ń Ń
    '\u00f3': 'o', '\u00d3': 'O',   # ó Ó
    '\u015b': 's', '\u015a': 'S',   # ś Ś
    '\u017c': 'z', '\u017b': 'Z',   # ż Ż
    '\u017a': 'z', '\u0179': 'Z',   # ź Ź
})


def slugify(text: str) -> str:
    """Convert *text* to a URL-friendly slug, handling Polish characters."""
    text = text.translate(_POLISH_MAP)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'-{2,}', '-', text).strip('-')
    return text


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------

@shop_bp.route('/client/shop')
@login_required
def index():
    """Render the shop page (grid is populated via JS/AJAX)."""
    return render_template('client/shop/index.html')


# ---------------------------------------------------------------------------
# API: product list (filtered / sorted / paginated)
# ---------------------------------------------------------------------------

@shop_bp.route('/client/shop/api/products')
@login_required
def api_products():
    """Return paginated, filtered JSON list of on-hand products."""

    # --- base query: on-hand, active, in stock ---
    on_hand_type = ProductType.query.filter_by(slug='on-hand').first()
    if not on_hand_type:
        return jsonify(products=[], total=0, pages=0, current_page=1)

    query = Product.query.filter(
        Product.product_type_id == on_hand_type.id,
        Product.is_active == True,   # noqa: E712
        Product.quantity > 0,
    )

    # --- search (name / SKU) ---
    search = request.args.get('search', '').strip()
    if search:
        pattern = f'%{search}%'
        query = query.filter(
            or_(
                Product.name.ilike(pattern),
                Product.sku.ilike(pattern),
            )
        )

    # --- category filter (manufacturer name) ---
    category = request.args.get('category', '').strip()
    if category:
        query = query.join(Product.manufacturer).filter(Manufacturer.name == category)

    # --- size filter ---
    size = request.args.get('size', '').strip()
    if size:
        query = query.join(Product.sizes).filter(Size.name == size)

    # --- price range ---
    price_min = request.args.get('price_min', type=float)
    price_max = request.args.get('price_max', type=float)
    if price_min is not None:
        query = query.filter(Product.sale_price >= price_min)
    if price_max is not None:
        query = query.filter(Product.sale_price <= price_max)

    # --- sorting ---
    sort = request.args.get('sort', 'newest')
    sort_map = {
        'newest':     Product.created_at.desc(),
        'price_asc':  Product.sale_price.asc(),
        'price_desc': Product.sale_price.desc(),
        'name_asc':   Product.name.asc(),
        'name_desc':  Product.name.desc(),
    }
    query = query.order_by(sort_map.get(sort, Product.created_at.desc()))

    # --- pagination ---
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    per_page = min(per_page, 48)  # cap

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    products = pagination.items

    # ------------------------------------------------------------------
    # Variant-group deduplication
    # Show only ONE product per variant group on the grid.
    # ------------------------------------------------------------------
    product_ids = [p.id for p in products]

    # Fetch variant-group memberships for these products
    vp_rows = (
        db.session.query(variant_products.c.variant_group_id, variant_products.c.product_id)
        .filter(variant_products.c.product_id.in_(product_ids))
        .all()
    ) if product_ids else []

    # Build mapping: product_id -> set of group ids
    pid_to_groups: dict[int, set[int]] = {}
    for gid, pid in vp_rows:
        pid_to_groups.setdefault(pid, set()).add(gid)

    seen_groups: set[int] = set()
    deduplicated: list[Product] = []
    for p in products:
        groups = pid_to_groups.get(p.id, set())
        if groups:
            # If ANY of this product's groups was already shown, skip
            if groups & seen_groups:
                continue
            seen_groups.update(groups)
        deduplicated.append(p)

    # --- build JSON response ---
    result = []
    for p in deduplicated:
        img = p.primary_image
        image_url = f'/static/{img.path_compressed}' if img else None

        # Sizes for this product
        p_sizes = [s.name for s in p.sizes]

        result.append({
            'id': p.id,
            'name': p.name,
            'slug': slugify(p.name),
            'sku': p.sku,
            'price': float(p.sale_price) if p.sale_price else 0,
            'quantity': p.quantity,
            'image_url': image_url,
            'brand': p.manufacturer.name if p.manufacturer else None,
            'sizes': p_sizes,
        })

    return jsonify(
        products=result,
        total=pagination.total,
        pages=pagination.pages,
        current_page=pagination.page,
    )


# ---------------------------------------------------------------------------
# API: available filter values
# ---------------------------------------------------------------------------

@shop_bp.route('/client/shop/api/filters')
@login_required
def api_filters():
    """Return categories (manufacturers), sizes and price range for on-hand products."""

    on_hand_type = ProductType.query.filter_by(slug='on-hand').first()
    if not on_hand_type:
        return jsonify(categories=[], sizes=[], price_min=0, price_max=0)

    base_filter = and_(
        Product.product_type_id == on_hand_type.id,
        Product.is_active == True,   # noqa: E712
        Product.quantity > 0,
    )

    # Categories = distinct manufacturer names
    categories = (
        db.session.query(Manufacturer.name)
        .join(Product, Product.manufacturer_id == Manufacturer.id)
        .filter(base_filter)
        .distinct()
        .order_by(Manufacturer.name)
        .all()
    )

    # Sizes available on on-hand products
    sizes = (
        db.session.query(Size.name)
        .join(product_sizes, product_sizes.c.size_id == Size.id)
        .join(Product, Product.id == product_sizes.c.product_id)
        .filter(base_filter)
        .distinct()
        .order_by(Size.name)
        .all()
    )

    # Price range
    price_range = (
        db.session.query(
            func.min(Product.sale_price),
            func.max(Product.sale_price),
        )
        .filter(base_filter)
        .first()
    )

    return jsonify(
        categories=[c[0] for c in categories],
        sizes=[s[0] for s in sizes],
        price_min=float(price_range[0]) if price_range and price_range[0] else 0,
        price_max=float(price_range[1]) if price_range and price_range[1] else 0,
    )


# ---------------------------------------------------------------------------
# Product detail
# ---------------------------------------------------------------------------

@shop_bp.route('/client/shop/product/<int:product_id>-<path:slug>')
@shop_bp.route('/client/shop/product/<int:product_id>')
@login_required
def product_detail(product_id, slug=None):
    """Product detail page."""
    product = Product.query.get_or_404(product_id)

    # Verify it's an on-hand product
    if not product.product_type or product.product_type.slug != 'on-hand':
        return redirect(url_for('shop.index'))

    # Record view interaction
    interaction = ProductInteraction(
        user_id=current_user.id,
        product_id=product.id,
        interaction_type='view'
    )
    db.session.add(interaction)
    db.session.commit()

    # Get variant group products
    variants = _get_variants(product)

    # Related products (same manufacturer, exclude current + variants)
    exclude_ids = [product.id] + [v.id for v in variants]
    related = _get_related(product, exclude_ids)

    # "Others also viewed" — collaborative filtering
    also_viewed = _get_also_viewed(product.id, exclude_ids)

    # "You might like" — personalized recommendations
    all_exclude = exclude_ids + [p.id for p in related] + [p.id for p in also_viewed]
    might_like = _get_recommendations(current_user.id, all_exclude)

    return render_template('client/shop/product.html',
                           product=product,
                           variants=variants,
                           related=related,
                           also_viewed=also_viewed,
                           might_like=might_like,
                           slugify=slugify)


# ---------------------------------------------------------------------------
# Recommendation helpers
# ---------------------------------------------------------------------------

def _get_variants(product):
    """Get other products in the same variant group."""
    row = db.session.query(variant_products.c.variant_group_id).filter(
        variant_products.c.product_id == product.id
    ).first()
    if not row:
        return []
    group_id = row[0]
    variant_ids = [r[0] for r in db.session.query(variant_products.c.product_id).filter(
        variant_products.c.variant_group_id == group_id,
        variant_products.c.product_id != product.id
    ).all()]
    if not variant_ids:
        return []
    return Product.query.filter(Product.id.in_(variant_ids), Product.is_active == True).all()


def _get_related(product, exclude_ids, limit=8):
    """Products from same manufacturer."""
    if not product.manufacturer_id:
        return []
    on_hand_type = ProductType.query.filter_by(slug='on-hand').first()
    if not on_hand_type:
        return []
    return Product.query.filter(
        Product.product_type_id == on_hand_type.id,
        Product.is_active == True,
        Product.quantity > 0,
        Product.manufacturer_id == product.manufacturer_id,
        ~Product.id.in_(exclude_ids)
    ).limit(limit).all()


def _get_also_viewed(product_id, exclude_ids, limit=8):
    """Collaborative filtering: users who viewed this also viewed X."""
    viewer_ids = db.session.query(ProductInteraction.user_id).filter(
        ProductInteraction.product_id == product_id,
        ProductInteraction.interaction_type.in_(['view', 'purchase'])
    ).distinct().subquery()

    on_hand_type = ProductType.query.filter_by(slug='on-hand').first()
    if not on_hand_type:
        return []

    results = db.session.query(
        Product,
        func.sum(
            db.case(
                (ProductInteraction.interaction_type == 'purchase', 5),
                (ProductInteraction.interaction_type == 'cart_add', 3),
                else_=1
            )
        ).label('score')
    ).join(
        ProductInteraction, ProductInteraction.product_id == Product.id
    ).filter(
        ProductInteraction.user_id.in_(db.select(viewer_ids.c.user_id)),
        Product.product_type_id == on_hand_type.id,
        Product.is_active == True,
        Product.quantity > 0,
        ~Product.id.in_(exclude_ids + [product_id])
    ).group_by(Product.id).order_by(db.desc('score')).limit(limit).all()

    return [r[0] for r in results]


def _get_recommendations(user_id, exclude_ids, limit=8):
    """Personalized recommendations based on user's interaction history."""
    on_hand_type = ProductType.query.filter_by(slug='on-hand').first()
    if not on_hand_type:
        return []

    # Get preferred manufacturers
    preferred = db.session.query(
        Product.manufacturer_id,
        func.sum(
            db.case(
                (ProductInteraction.interaction_type == 'purchase', 5),
                (ProductInteraction.interaction_type == 'cart_add', 3),
                else_=1
            )
        ).label('score')
    ).join(
        ProductInteraction, ProductInteraction.product_id == Product.id
    ).filter(
        ProductInteraction.user_id == user_id,
        Product.manufacturer_id.isnot(None)
    ).group_by(Product.manufacturer_id).order_by(db.desc('score')).limit(5).all()

    mfr_ids = [m[0] for m in preferred if m[0]]

    base_filter = [
        Product.product_type_id == on_hand_type.id,
        Product.is_active == True,
        Product.quantity > 0,
        ~Product.id.in_(exclude_ids)
    ]

    if mfr_ids:
        return Product.query.filter(
            *base_filter, Product.manufacturer_id.in_(mfr_ids)
        ).order_by(func.rand()).limit(limit).all()
    else:
        # Fallback: random on-hand products
        return Product.query.filter(
            *base_filter
        ).order_by(func.rand()).limit(limit).all()


# ---------------------------------------------------------------------------
# Cart helpers
# ---------------------------------------------------------------------------

def _get_cart_count(user_id):
    """Return total quantity of items in user's cart."""
    return db.session.query(
        func.coalesce(func.sum(CartItem.quantity), 0)
    ).filter(
        CartItem.user_id == user_id
    ).scalar()


# ---------------------------------------------------------------------------
# API: Cart endpoints
# ---------------------------------------------------------------------------

@shop_bp.route('/client/shop/api/cart')
@login_required
def api_cart():
    """Get cart contents with stock validation."""
    items = CartItem.query.filter_by(
        user_id=current_user.id
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
    return jsonify(items=cart_data, total=round(total, 2), count=count)


@shop_bp.route('/client/shop/api/cart/add', methods=['POST'])
@login_required
def api_cart_add():
    """Add a product to the cart."""
    data = request.get_json(silent=True) or {}
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)

    if not product_id:
        return jsonify(success=False, error='Brak ID produktu.'), 400

    product = Product.query.get(product_id)
    if not product or not product.is_active:
        return jsonify(success=False, error='Produkt nie istnieje lub jest nieaktywny.'), 404

    # Must be on-hand type
    if not product.product_type or product.product_type.slug != 'on-hand':
        return jsonify(success=False, error='Ten produkt nie jest dostępny w sklepie.'), 400

    if product.quantity <= 0:
        return jsonify(success=False, error='Produkt jest niedostępny (brak na stanie).'), 400

    # Check if already in cart
    existing = CartItem.query.filter_by(
        user_id=current_user.id,
        product_id=product_id,
    ).first()

    if existing:
        new_qty = existing.quantity + quantity
        if new_qty > product.quantity:
            return jsonify(
                success=False,
                error=f'Nie można dodać więcej. Dostępne: {product.quantity}, w koszyku: {existing.quantity}.',
            ), 400
        existing.quantity = new_qty
    else:
        if quantity > product.quantity:
            return jsonify(
                success=False,
                error=f'Żądana ilość ({quantity}) przekracza dostępną ({product.quantity}).',
            ), 400
        cart_item = CartItem(
            user_id=current_user.id,
            product_id=product_id,
            quantity=quantity,
        )
        db.session.add(cart_item)

    # Record interaction
    interaction = ProductInteraction(
        user_id=current_user.id,
        product_id=product_id,
        interaction_type='cart_add',
    )
    db.session.add(interaction)
    db.session.commit()

    return jsonify(success=True, cart_count=_get_cart_count(current_user.id))


@shop_bp.route('/client/shop/api/cart/update', methods=['POST'])
@login_required
def api_cart_update():
    """Update quantity of a cart item."""
    data = request.get_json(silent=True) or {}
    item_id = data.get('item_id')
    quantity = data.get('quantity')

    if not item_id or quantity is None:
        return jsonify(success=False, error='Brak wymaganych parametrów.'), 400

    item = CartItem.query.filter_by(id=item_id, user_id=current_user.id).first()
    if not item:
        return jsonify(success=False, error='Nie znaleziono elementu koszyka.'), 404

    if quantity <= 0:
        db.session.delete(item)
        db.session.commit()
        return jsonify(success=True, cart_count=_get_cart_count(current_user.id))

    product = item.product
    if product and quantity > product.quantity:
        return jsonify(
            success=False,
            error=f'Dostępna ilość: {product.quantity}.',
            available=product.quantity,
        ), 400

    item.quantity = quantity
    db.session.commit()
    return jsonify(success=True, cart_count=_get_cart_count(current_user.id))


@shop_bp.route('/client/shop/api/cart/remove', methods=['POST'])
@login_required
def api_cart_remove():
    """Remove an item from the cart."""
    data = request.get_json(silent=True) or {}
    item_id = data.get('item_id')

    if not item_id:
        return jsonify(success=False, error='Brak ID elementu.'), 400

    item = CartItem.query.filter_by(id=item_id, user_id=current_user.id).first()
    if not item:
        return jsonify(success=False, error='Nie znaleziono elementu koszyka.'), 404

    db.session.delete(item)
    db.session.commit()
    return jsonify(success=True, cart_count=_get_cart_count(current_user.id))


@shop_bp.route('/client/shop/api/cart/count')
@login_required
def api_cart_count():
    """Return cart badge count."""
    count = _get_cart_count(current_user.id)
    return jsonify(count=count)


# ---------------------------------------------------------------------------
# Checkout helpers
# ---------------------------------------------------------------------------

def _get_initial_shipping_status():
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


# ---------------------------------------------------------------------------
# Checkout routes
# ---------------------------------------------------------------------------

@shop_bp.route('/client/shop/checkout')
@login_required
def checkout():
    """Render checkout page."""
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        return redirect(url_for('shop.index'))

    addresses = ShippingAddress.query.filter_by(
        user_id=current_user.id,
        is_active=True,
    ).all()

    return render_template('client/shop/checkout.html', addresses=addresses)


@shop_bp.route('/client/shop/checkout/place', methods=['POST'])
@login_required
def checkout_place():
    """Place order (AJAX). Validate stock, create order + optional shipping request."""
    data = request.get_json(silent=True) or {}
    create_shipping = data.get('create_shipping', False)
    address_id = data.get('address_id')

    # 1. Get cart items
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not items:
        return jsonify(success=False, error='Koszyk jest pusty.'), 400

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
        return jsonify(success=False, stock_errors=stock_errors), 400

    # 3. Shipping validation
    address = None
    if create_shipping:
        if not address_id:
            return jsonify(success=False, error='Wybierz adres dostawy.'), 400
        address = ShippingAddress.query.filter_by(
            id=address_id,
            user_id=current_user.id,
            is_active=True,
        ).first()
        if not address:
            return jsonify(success=False, error='Wybrany adres nie istnieje.'), 400

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
            user_id=current_user.id,
            order_type='on_hand',
            status='nowe',
            total_amount=total,
        )
        db.session.add(order)
        db.session.flush()  # get order.id

        # 5. Create order items, decrease stock, record interaction
        for item in items:
            product = item.product
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

            product.quantity -= item.quantity

            interaction = ProductInteraction(
                user_id=current_user.id,
                product_id=product.id,
                interaction_type='purchase',
            )
            db.session.add(interaction)

        # 6. Optional shipping request
        shipping_request_number = None
        if create_shipping and address:
            initial_status = _get_initial_shipping_status()
            sr = ShippingRequest(
                request_number=ShippingRequest.generate_request_number(),
                user_id=current_user.id,
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
        CartItem.query.filter_by(user_id=current_user.id).delete()

        db.session.commit()

        # 8. Log activity
        log_activity(
            user=current_user,
            action='order_created',
            entity_type='order',
            entity_id=order.id,
            new_value={'order_number': order_number, 'total': float(total)},
        )

        return jsonify(
            success=True,
            order_id=order.id,
            order_number=order_number,
            shipping_request_number=shipping_request_number,
            redirect_url=url_for('shop.order_success', order_id=order.id),
        )

    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=f'Wystąpił błąd: {str(e)}'), 500


@shop_bp.route('/client/shop/order-success/<int:order_id>')
@login_required
def order_success(order_id):
    """Show order success page."""
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        return redirect(url_for('shop.index'))
    return render_template('client/shop/success.html', order=order)
