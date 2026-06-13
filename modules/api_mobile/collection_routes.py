"""Trasy kolekcji klienta (CRUD + zdjęcia + publiczna strona) dla mobilnego API (E8)."""

from decimal import Decimal

from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import limiter
from modules.auth.models import User
from modules.client import collection_service as svc
from . import api_mobile_bp
from .helpers import json_ok, json_err, json_page, to_grosze
from .validators import parse_int, ValidationError
from .idempotency import idempotent

MAX_IMAGE_SIZE = 10 * 1024 * 1024     # 10 MB per plik (D8 — hardening; web nie sprawdza)


def _abs(path):
    """Property modeli zwracają już '/static/...' — dokleja origin (URL absolutny)."""
    if not path:
        return None
    if path.startswith('http'):
        return path
    return request.url_root.rstrip('/') + path


def _serialize_item_brief(item):
    return {
        'id': item.id,
        'name': item.name,
        'market_price': to_grosze(item.market_price),
        'source': item.source,
        'is_public': bool(item.is_public),
        'images_count': item.images_count,
        'image_url': _abs(item.image_url),                    # primary/produkt/placeholder
        'created_at': item.created_at.isoformat() if item.created_at else None,
    }


def _serialize_image(img, source='collection'):
    return {'id': img.id, 'url': _abs(f'/static/{img.path_compressed}'),
            'is_primary': bool(img.is_primary),
            'sort_order': img.sort_order if source == 'collection' else None,
            'source': source}


def _serialize_item_images(item):
    """Parytet web edit GET (l. 181-197): własne zdjęcia, fallback na zdjęcia produktu."""
    images = [_serialize_image(img) for img in item.images]
    if not images and item.product_id and item.product:
        images = [_serialize_image(img, source='product') for img in item.product.images]
    return images


def _serialize_item_detail(item):
    d = _serialize_item_brief(item)
    d.update({
        'notes': item.notes,
        'can_add_image': item.can_add_image,
        'images': _serialize_item_images(item),
        'updated_at': item.updated_at.isoformat() if item.updated_at else None,
    })
    return d


def _market_price_from_form(form):
    """'market_price' w GROSZACH (string-int) -> Decimal PLN; ''/brak -> None (Korekta 2)."""
    grosze = parse_int(form.get('market_price'), 'market_price', min_value=0)
    if grosze is None:
        return None
    return Decimal(grosze) / 100


def _file_too_large(file):
    file.seek(0, 2); size = file.tell(); file.seek(0)
    return size > MAX_IMAGE_SIZE


@api_mobile_bp.route('/collection/items', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def collection_items_list():
    user_id = int(get_jwt_identity())
    page = parse_int(request.args.get('page'), 'page', default=1, min_value=1)
    per_page = min(parse_int(request.args.get('per_page'), 'per_page',
                             default=20, min_value=1), 50)
    sort = (request.args.get('sort') or 'newest').strip()
    if sort not in svc.ALLOWED_SORTS:                         # zamknięty enum (D1(a) z E5)
        raise ValidationError(f'Nieznane sortowanie: {sort}.')
    q = (request.args.get('q') or '').strip() or None
    pagination = svc.list_items(user_id, search=q, sort=sort, page=page, per_page=per_page)
    return json_page([_serialize_item_brief(i) for i in pagination.items],
                     page=pagination.page, per_page=pagination.per_page,
                     total=pagination.total, has_next=pagination.has_next)


@api_mobile_bp.route('/collection/items/<int:item_id>', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def collection_item_detail(item_id):
    item = svc.get_owned_item(int(get_jwt_identity()), item_id)
    if item is None:
        return json_err('item_not_found', 'Przedmiot nie istnieje.', 404)
    return json_ok(_serialize_item_detail(item))


@api_mobile_bp.route('/collection/items', methods=['POST'])
@jwt_required()
@limiter.limit("15 per minute")           # heavy-write (upload plików)
@idempotent('collection_item_create')     # D3: duplikat itemu + plików szkodliwy
def collection_item_create():
    name = (request.form.get('name') or '').strip()
    if not name:
        return json_err('invalid_input', 'Nazwa jest wymagana.', 400,
                        details={'field': 'name'})
    market_price = _market_price_from_form(request.form)      # ValidationError → 400
    notes = (request.form.get('notes') or '').strip()
    files = [f for f in request.files.getlist('images') if f and f.filename]
    if len(files) > svc.MAX_IMAGES_PER_ITEM:                  # D9: jawny błąd zamiast cichego capa
        return json_err('invalid_input', 'Maksymalnie 3 zdjęcia na przedmiot.', 400,
                        details={'max_images': svc.MAX_IMAGES_PER_ITEM})
    for f in files:
        if _file_too_large(f):
            return json_err('file_too_large', 'Maksymalny rozmiar zdjęcia to 10 MB.', 400)
    user = User.query.get(int(get_jwt_identity()))
    ok, err, item = svc.create_item(user, name, market_price=market_price,
                                    notes=notes, files=files)
    if not ok:
        return json_err('invalid_file', err.get('message', 'Nieprawidłowy plik.'), 400)
    return json_ok(_serialize_item_detail(item), 201)


@api_mobile_bp.route('/collection/items/<int:item_id>', methods=['PATCH'])
@jwt_required()
@limiter.limit("30 per minute")
def collection_item_update(item_id):
    """PATCH częściowy (Korekta 3): tylko pola obecne w form; zdjęcia mają osobne endpointy."""
    fields = {}
    if 'name' in request.form:
        fields['name'] = (request.form.get('name') or '').strip()
    if 'market_price' in request.form:
        fields['market_price'] = _market_price_from_form(request.form)
    if 'notes' in request.form:
        fields['notes'] = (request.form.get('notes') or '').strip()
    if not fields:
        return json_err('invalid_input', 'Brak pól do aktualizacji.', 400)
    ok, err, item = svc.update_item(int(get_jwt_identity()), item_id, fields)
    if not ok:
        if err['code'] == 'name_required':
            return json_err('invalid_input', 'Nazwa jest wymagana.', 400,
                            details={'field': 'name'})
        return json_err('item_not_found', 'Przedmiot nie istnieje.', 404)
    return json_ok(_serialize_item_detail(item))


@api_mobile_bp.route('/collection/items/<int:item_id>', methods=['DELETE'])
@jwt_required()
@limiter.limit("30 per minute")
def collection_item_delete(item_id):
    ok, err = svc.delete_item(int(get_jwt_identity()), item_id)
    if not ok:
        return json_err('item_not_found', 'Przedmiot nie istnieje.', 404)
    return json_ok({'deleted': True})


@api_mobile_bp.route('/collection/items/<int:item_id>/images', methods=['POST'])
@jwt_required()
@limiter.limit("15 per minute")           # heavy-write (upload); D4: bez @idempotent
def collection_image_add(item_id):
    file = request.files.get('image')
    if file is None or file.filename == '':
        return json_err('invalid_input', 'Nie przesłano pliku (pole image).', 400)
    if _file_too_large(file):
        return json_err('file_too_large', 'Maksymalny rozmiar zdjęcia to 10 MB.', 400)
    user = User.query.get(int(get_jwt_identity()))
    ok, err, image = svc.add_image(user, item_id, file)
    if not ok:
        if err['code'] == 'not_found':
            return json_err('item_not_found', 'Przedmiot nie istnieje.', 404)
        if err['code'] == 'max_images':                       # Korekta 6: 409 (web: 400)
            return json_err('max_images', 'Maksymalnie 3 zdjęcia na przedmiot.', 409)
        return json_err('invalid_file', err.get('message', 'Nieprawidłowy plik.'), 400)
    return json_ok({'image': _serialize_image(image)}, 201)


@api_mobile_bp.route('/collection/items/<int:item_id>/images/<int:image_id>',
                     methods=['DELETE'])
@jwt_required()
@limiter.limit("30 per minute")
def collection_image_delete(item_id, image_id):
    ok, err = svc.delete_image(int(get_jwt_identity()), item_id, image_id)
    if not ok:
        return json_err('image_not_found', 'Zdjęcie nie istnieje.', 404)
    return json_ok({'deleted': True})


@api_mobile_bp.route('/collection/items/<int:item_id>/images/<int:image_id>/primary',
                     methods=['PATCH'])
@jwt_required()
@limiter.limit("30 per minute")
def collection_image_set_primary(item_id, image_id):
    ok, err, image = svc.set_primary_image(int(get_jwt_identity()), item_id, image_id)
    if not ok:
        return json_err('image_not_found', 'Zdjęcie nie istnieje.', 404)
    return json_ok({'image': _serialize_image(image)})


def _serialize_public_config(config):
    return {
        'token': config.token,
        'show_prices': bool(config.show_prices),
        'is_active': bool(config.is_active),
        'public_url': request.url_root.rstrip('/') + f'/collection/{config.token}',
    }


@api_mobile_bp.route('/collection/public/config', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def collection_public_config_get():
    config = svc.get_public_config(int(get_jwt_identity()))
    if config is None:                                        # Korekta 7: stan, nie błąd
        return json_ok({'exists': False, 'config': None})
    return json_ok({'exists': True, 'config': _serialize_public_config(config)})


@api_mobile_bp.route('/collection/public/config', methods=['POST'])
@jwt_required()
@limiter.limit("30 per minute")
def collection_public_config_update():
    """UPSERT (D6): pierwszy POST tworzy config (token + achievement), każdy aplikuje flagi."""
    data = request.get_json(silent=True) or {}
    user = User.query.get(int(get_jwt_identity()))
    created = False
    if svc.get_public_config(user.id) is None:
        svc.create_public_config(user)
        created = True
    _, _, config = svc.update_public_config(
        user.id,
        show_prices=data.get('show_prices') if 'show_prices' in data else None,
        is_active=data.get('is_active') if 'is_active' in data else None)
    return json_ok({'created': created, 'config': _serialize_public_config(config)},
                   201 if created else 200)


@api_mobile_bp.route('/collection/items/<int:item_id>/toggle-public', methods=['POST'])
@jwt_required()
@limiter.limit("30 per minute")
def collection_item_toggle_public(item_id):
    ok, err, item = svc.toggle_item_public(int(get_jwt_identity()), item_id)
    if not ok:
        return json_err('item_not_found', 'Przedmiot nie istnieje.', 404)
    return json_ok({'id': item.id, 'is_public': bool(item.is_public)})
