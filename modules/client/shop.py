"""
Client Shop Module
On-hand product shop - browsing, filtering, cart, and checkout.
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from extensions import db
from modules.products.models import (
    Product, ProductType,
    CartItem, ProductInteraction,
)
from modules.orders.models import Order
from modules.auth.models import ShippingAddress
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from modules.client import shop_service, cart_service
from modules.client.shop_service import slugify


shop_bp = Blueprint('shop', __name__)


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
    on_hand_type = shop_service.get_on_hand_type()
    if not on_hand_type:
        return jsonify(products=[], total=0, pages=0, current_page=1)

    query = shop_service.build_products_query(
        on_hand_type,
        search=request.args.get('search', '').strip(),
        category=request.args.get('category', '').strip(),
        size=request.args.get('size', '').strip(),
        price_min=request.args.get('price_min', type=float),
        price_max=request.args.get('price_max', type=float),
        sort=request.args.get('sort', 'newest'),
    )

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    per_page = min(per_page, 48)  # cap

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    deduplicated = shop_service.dedupe_variant_groups(pagination.items)

    result = []
    for p in deduplicated:
        img = p.primary_image
        image_url = f'/static/{img.path_compressed}' if img else None
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
        total=len(result),
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
    data = shop_service.get_filters_data()
    return jsonify(
        categories=data['categories'],
        sizes=data['sizes'],
        price_min=float(data['price_min']) if data['price_min'] else 0,
        price_max=float(data['price_max']) if data['price_max'] else 0,
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

    # Verify it's an active on-hand product
    if not product.is_active or not product.product_type or product.product_type.slug != 'on-hand':
        return redirect(url_for('shop.index'))

    # Record view interaction
    shop_service.record_interaction(current_user.id, product.id, 'view')
    db.session.commit()

    # Get variant group products
    variants = shop_service.get_variants(product)

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

def _get_related(product, exclude_ids, limit=8):
    """Products from same manufacturer."""
    if not product.manufacturer_id:
        return []
    on_hand_type = ProductType.query.filter_by(slug='on-hand').first()
    if not on_hand_type:
        return []
    return Product.query.options(
        joinedload(Product.manufacturer)
    ).filter(
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
    ).options(
        joinedload(Product.manufacturer)
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

    eager = [joinedload(Product.manufacturer)]
    if mfr_ids:
        return Product.query.options(*eager).filter(
            *base_filter, Product.manufacturer_id.in_(mfr_ids)
        ).order_by(func.rand()).limit(limit).all()
    else:
        # Fallback: random on-hand products
        return Product.query.options(*eager).filter(
            *base_filter
        ).order_by(func.rand()).limit(limit).all()


# ---------------------------------------------------------------------------
# API: Cart endpoints
# ---------------------------------------------------------------------------

@shop_bp.route('/client/shop/api/cart')
@login_required
def api_cart():
    """Get cart contents with stock validation."""
    cart_data, total, count = cart_service.build_cart_data(current_user.id)
    return jsonify(items=cart_data, total=total, count=count)


@shop_bp.route('/client/shop/api/cart/add', methods=['POST'])
@login_required
def api_cart_add():
    """Add a product to the cart."""
    data = request.get_json(silent=True) or {}
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)

    result = cart_service.add_to_cart(current_user.id, product_id, quantity)
    if not result.ok:
        return jsonify(success=False, error=result.message), result.status

    return jsonify(success=True, cart_count=result.extras['cart_count'])


@shop_bp.route('/client/shop/api/cart/update', methods=['POST'])
@login_required
def api_cart_update():
    """Update quantity of a cart item."""
    data = request.get_json(silent=True) or {}
    item_id = data.get('item_id')
    quantity = data.get('quantity')

    result = cart_service.update_cart_item(current_user.id, item_id, quantity)
    if not result.ok:
        if result.code == 'exceeds_stock':
            return jsonify(
                success=False,
                error=result.message,
                available=result.extras['available'],
            ), result.status
        return jsonify(success=False, error=result.message), result.status

    return jsonify(success=True, cart_count=result.extras['cart_count'])


@shop_bp.route('/client/shop/api/cart/remove', methods=['POST'])
@login_required
def api_cart_remove():
    """Remove an item from the cart."""
    data = request.get_json(silent=True) or {}
    item_id = data.get('item_id')

    result = cart_service.remove_cart_item(current_user.id, item_id)
    if not result.ok:
        return jsonify(success=False, error=result.message), result.status

    return jsonify(success=True, cart_count=result.extras['cart_count'])


@shop_bp.route('/client/shop/api/cart/count')
@login_required
def api_cart_count():
    """Return cart badge count."""
    count = cart_service.get_cart_count(current_user.id)
    return jsonify(count=count)


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

    result = cart_service.place_order_on_hand(
        current_user.id,
        create_shipping=create_shipping,
        address_id=address_id,
    )

    if not result.ok:
        if result.code == 'stock_errors':
            return jsonify(success=False, stock_errors=result.stock_errors), 400
        return jsonify(success=False, error=result.message), result.status

    order = result.order
    return jsonify(
        success=True,
        order_id=order.id,
        order_number=result.extras['order_number'],
        total_amount=result.extras['total_amount'],
        items_count=result.extras['items_count'],
        items=result.extras['ga_items'],
        shipping_request_number=result.extras['shipping_request_number'],
        redirect_url=url_for('shop.order_success', order_id=order.id),
    )


@shop_bp.route('/client/shop/order-success/<int:order_id>')
@login_required
def order_success(order_id):
    """Show order success page."""
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        return redirect(url_for('shop.index'))
    return render_template('client/shop/success.html', order=order)
