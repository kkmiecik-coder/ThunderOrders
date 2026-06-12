"""Trasy sklepu on-hand (odczyt) + kurs walut dla mobilnego API (E1)."""

from decimal import Decimal

from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
from modules.client import shop_service
from modules.products.models import ProductImage
from . import api_mobile_bp
from .helpers import json_ok, json_err, json_page, to_grosze, absolute_static_url
from .validators import parse_int

# Parytet z webowym /api/exchange-rate (modules/api/routes.py)
ALLOWED_CURRENCIES = ('KRW', 'USD', 'EUR', 'GBP', 'CHF', 'JPY', 'CNY')


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


def _serialize_product_detail(p):
    data = _serialize_product_brief(p)
    data.update({
        'description': p.description,
        'category': p.category.name if p.category else None,
        'images': [{
            'id': img.id,
            'url': absolute_static_url(img.path_compressed),
            'is_primary': bool(img.is_primary),
            'sort_order': img.sort_order,
        } for img in p.images.order_by(ProductImage.sort_order.asc(),
                                       ProductImage.id.asc())],
        'variants': [_serialize_product_brief(v) for v in shop_service.get_variants(p)],
    })
    return data


@api_mobile_bp.route('/shop/products', methods=['GET'])
@jwt_required()
def shop_products():
    page = parse_int(request.args.get('page'), 'page', default=1, min_value=1)
    per_page = min(parse_int(request.args.get('per_page'), 'per_page', default=12, min_value=1), 48)
    price_min = parse_int(request.args.get('price_min'), 'price_min', default=None, min_value=0)   # grosze
    price_max = parse_int(request.args.get('price_max'), 'price_max', default=None, min_value=0)   # grosze

    on_hand_type = shop_service.get_on_hand_type()
    if not on_hand_type:
        return json_page([], page=page, per_page=per_page, total=0, has_next=False)

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


@api_mobile_bp.route('/shop/products/<int:product_id>', methods=['GET'])
@jwt_required()
def shop_product_detail(product_id):
    product = shop_service.get_active_shop_product(product_id)
    if product is None:
        return json_err('product_not_found',
                        'Produkt nie istnieje lub jest niedostępny.', 404)

    shop_service.record_interaction(int(get_jwt_identity()), product.id, 'view')
    db.session.commit()

    return json_ok({'product': _serialize_product_detail(product)})


@api_mobile_bp.route('/shop/filters', methods=['GET'])
@jwt_required()
def shop_filters():
    data = shop_service.get_filters_data()
    return json_ok({
        'categories': data['categories'],
        'sizes': data['sizes'],
        'price_min': to_grosze(data['price_min']) if data['price_min'] is not None else 0,
        'price_max': to_grosze(data['price_max']) if data['price_max'] is not None else 0,
    })


@api_mobile_bp.route('/exchange-rate', methods=['GET'])
@jwt_required()
def exchange_rate():
    currency = (request.args.get('currency') or '').strip().upper()
    if not currency:
        return json_err('missing_currency', 'Parametr currency jest wymagany.', 400)
    if currency not in ALLOWED_CURRENCIES:
        return json_err('unsupported_currency',
                        f'Nieobsługiwana waluta: {currency}.', 400)

    # Import lazy jak w webowym odpowiedniku — łatwy monkeypatch w testach.
    from utils.currency import get_exchange_rate
    try:
        rate_data = get_exchange_rate(currency)
    except Exception:
        return json_err('exchange_rate_unavailable',
                        'Nie udało się pobrać kursu waluty.', 503)

    return json_ok({
        'currency': rate_data['currency'],
        'rate': rate_data['rate'],
        'date': rate_data.get('date'),
        'cached': rate_data.get('cached', False),
        'cached_at': rate_data.get('cached_at'),
    })
