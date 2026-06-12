"""
Serwis sklepu on-hand — logika współdzielona przez web (modules/client/shop.py)
i mobilne API (modules/api_mobile/shop_routes.py).

Zasada ze specu mobile API: współdzielenie logiki, nie duplikacja.
"""

import re
import unicodedata

from extensions import db
from modules.products.models import (
    Product, ProductType, ProductInteraction, Size, Manufacturer,
    variant_products, product_sizes,
)
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import joinedload


ON_HAND_SLUG = 'on-hand'

_POLISH_MAP = str.maketrans({
    'ą': 'a', 'Ą': 'A',   # ą Ą
    'ć': 'c', 'Ć': 'C',   # ć Ć
    'ę': 'e', 'Ę': 'E',   # ę Ę
    'ł': 'l', 'Ł': 'L',   # ł Ł
    'ń': 'n', 'Ń': 'N',   # ń Ń
    'ó': 'o', 'Ó': 'O',   # ó Ó
    'ś': 's', 'Ś': 'S',   # ś Ś
    'ż': 'z', 'Ż': 'Z',   # ż Ż
    'ź': 'z', 'Ź': 'Z',   # ź Ź
})

_SORT_MAP = {
    'newest':     lambda: Product.created_at.desc(),
    'price_asc':  lambda: Product.sale_price.asc(),
    'price_desc': lambda: Product.sale_price.desc(),
    'name_asc':   lambda: Product.name.asc(),
    'name_desc':  lambda: Product.name.desc(),
}


def slugify(text: str) -> str:
    """Convert *text* to a URL-friendly slug, handling Polish characters."""
    text = text.translate(_POLISH_MAP)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'-{2,}', '-', text).strip('-')
    return text


def get_on_hand_type():
    return ProductType.query.filter_by(slug=ON_HAND_SLUG).first()


def _base_shop_filter(on_hand_type):
    """Produkt widoczny w sklepie: typ on-hand, aktywny, na stanie."""
    return and_(
        Product.product_type_id == on_hand_type.id,
        Product.is_active == True,   # noqa: E712
        Product.quantity > 0,
    )


def build_products_query(on_hand_type, search='', category='', size='',
                         price_min=None, price_max=None, sort='newest'):
    """Zapytanie listy sklepu: filtry + sortowanie (bez paginacji)."""
    query = Product.query.options(
        joinedload(Product.manufacturer), joinedload(Product.sizes)
    ).filter(_base_shop_filter(on_hand_type))

    if search:
        pattern = f'%{search}%'
        query = query.filter(or_(
            Product.name.ilike(pattern),
            Product.sku.ilike(pattern),
        ))

    if category:
        query = query.join(Product.manufacturer).filter(Manufacturer.name == category)

    if size:
        query = query.join(Product.sizes).filter(Size.name == size)

    if price_min is not None:
        query = query.filter(Product.sale_price >= price_min)
    if price_max is not None:
        query = query.filter(Product.sale_price <= price_max)

    order = _SORT_MAP.get(sort, _SORT_MAP['newest'])()
    return query.order_by(order)


def dedupe_variant_groups(products):
    """Z każdej grupy wariantów pokazuj na liście tylko PIERWSZY produkt."""
    product_ids = [p.id for p in products]
    vp_rows = (
        db.session.query(variant_products.c.variant_group_id, variant_products.c.product_id)
        .filter(variant_products.c.product_id.in_(product_ids))
        .all()
    ) if product_ids else []

    pid_to_groups: dict[int, set[int]] = {}
    for gid, pid in vp_rows:
        pid_to_groups.setdefault(pid, set()).add(gid)

    seen_groups: set[int] = set()
    deduplicated: list = []
    for p in products:
        groups = pid_to_groups.get(p.id, set())
        if groups:
            if groups & seen_groups:
                continue
            seen_groups.update(groups)
        deduplicated.append(p)
    return deduplicated


def get_filters_data():
    """Kategorie (producenci), rozmiary i zakres cen widocznych produktów on-hand.

    Zwraca surowe wartości (Decimal/None) — formatowanie należy do warstwy
    prezentacji (web: float, mobile: grosze).
    """
    on_hand_type = get_on_hand_type()
    if not on_hand_type:
        return {'categories': [], 'sizes': [], 'price_min': None, 'price_max': None}

    base_filter = _base_shop_filter(on_hand_type)

    categories = (
        db.session.query(Manufacturer.name)
        .join(Product, Product.manufacturer_id == Manufacturer.id)
        .filter(base_filter)
        .distinct()
        .order_by(Manufacturer.name)
        .all()
    )
    sizes = (
        db.session.query(Size.name)
        .join(product_sizes, product_sizes.c.size_id == Size.id)
        .join(Product, Product.id == product_sizes.c.product_id)
        .filter(base_filter)
        .distinct()
        .order_by(Size.name)
        .all()
    )
    price_range = (
        db.session.query(func.min(Product.sale_price), func.max(Product.sale_price))
        .filter(base_filter)
        .first()
    )

    return {
        'categories': [c[0] for c in categories],
        'sizes': [s[0] for s in sizes],
        'price_min': price_range[0] if price_range else None,
        'price_max': price_range[1] if price_range else None,
    }


def get_active_shop_product(product_id):
    """Produkt do karty szczegółów: musi być aktywny i typu on-hand (stan 0 dozwolony)."""
    product = Product.query.get(product_id)
    if (not product or not product.is_active
            or not product.product_type or product.product_type.slug != ON_HAND_SLUG):
        return None
    return product


def get_variants(product):
    """Inne aktywne produkty on-hand z tej samej grupy wariantów."""
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
    on_hand_type = get_on_hand_type()
    if not on_hand_type:
        return []
    return Product.query.filter(
        Product.id.in_(variant_ids),
        Product.is_active == True,   # noqa: E712
        Product.product_type_id == on_hand_type.id
    ).all()


def record_interaction(user_id, product_id, interaction_type):
    """Zapis interakcji (view/cart_add/purchase) do silnika rekomendacji.

    Dodaje do sesji — commit należy do wołającego.
    """
    db.session.add(ProductInteraction(
        user_id=user_id,
        product_id=product_id,
        interaction_type=interaction_type,
    ))
