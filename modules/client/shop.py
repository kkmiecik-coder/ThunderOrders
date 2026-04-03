"""
Client Shop Module
On-hand product shop - browsing, filtering, and product grid API.
"""

import re
import unicodedata
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from modules.products.models import (
    Product, ProductType, ProductImage, Size, Manufacturer,
    variant_products, product_sizes,
)
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
    on_hand_type = ProductType.query.filter_by(slug='on_hand').first()
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

    on_hand_type = ProductType.query.filter_by(slug='on_hand').first()
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
