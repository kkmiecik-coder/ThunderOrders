"""Trasy sklepu on-hand (odczyt) + kurs walut dla mobilnego API (E1)."""

from decimal import Decimal

from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
from modules.client import shop_service
from modules.products.models import ProductImage
from . import api_mobile_bp
from .helpers import json_ok, json_err, json_page, to_grosze, absolute_static_url


def _serialize_product_brief(p):
    """Pozycja listy / wariantu — parytet pól z webowym gridem + kwoty w groszach."""
    img = p.primary_image
    return {
        'id': p.id,
        'name': p.name,
        'slug': shop_service.slugify(p.name),
        'sku': p.sku,
        'price': to_grosze(p.sale_price),
        'quantity': p.quantity,
        'image_url': absolute_static_url(img.path_compressed) if img else None,
        'brand': p.manufacturer.name if p.manufacturer else None,
        'sizes': [s.name for s in p.sizes],
    }


@api_mobile_bp.route('/shop/products', methods=['GET'])
@jwt_required()
def shop_products():
    page = max(request.args.get('page', 1, type=int) or 1, 1)
    per_page = min(max(request.args.get('per_page', 12, type=int) or 12, 1), 48)

    on_hand_type = shop_service.get_on_hand_type()
    if not on_hand_type:
        return json_page([], page=page, per_page=per_page, total=0, has_next=False)

    price_min = request.args.get('price_min', type=int)   # grosze
    price_max = request.args.get('price_max', type=int)   # grosze

    query = shop_service.build_products_query(
        on_hand_type,
        search=(request.args.get('q') or '').strip(),
        category=(request.args.get('category') or '').strip(),
        size=(request.args.get('size') or '').strip(),
        price_min=Decimal(price_min) / 100 if price_min is not None else None,
        price_max=Decimal(price_max) / 100 if price_max is not None else None,
        sort=request.args.get('sort', 'newest'),
    )

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    items = shop_service.dedupe_variant_groups(pagination.items)

    return json_page(
        [_serialize_product_brief(p) for p in items],
        page=pagination.page,
        per_page=pagination.per_page,
        total=pagination.total,
        has_next=pagination.has_next,
    )
