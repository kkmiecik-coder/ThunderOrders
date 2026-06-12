"""Wspólne helpery odpowiedzi JSON i serializacji dla mobilnego API."""

from decimal import Decimal, ROUND_HALF_UP

from flask import jsonify, request


def json_ok(data=None, status=200):
    return jsonify({'success': True, 'data': data if data is not None else {}}), status


def json_err(code, message, status=400):
    return jsonify({'success': False, 'error': {'code': code, 'message': message}}), status


def serialize_user(user):
    full = ' '.join(p for p in [user.first_name, user.last_name] if p).strip() or None
    avatar = user.avatar_url
    if avatar and avatar.startswith('/'):
        # Kontrakt API wymaga absolutnych URL-i; Avatar.url zwraca ścieżkę względną.
        avatar = request.url_root.rstrip('/') + avatar
    return {
        'id': user.id,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': full,
        'phone': user.phone,
        'role': user.role,
        'avatar_url': avatar,
        'email_verified': bool(user.email_verified),
    }


def to_grosze(amount):
    """Kwota PLN (Decimal/float/int) -> grosze (int). Kontrakt API: kwoty w groszach."""
    if amount is None:
        return None
    return int((Decimal(str(amount)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def absolute_static_url(path):
    """Względna ścieżka pliku statycznego -> absolutny URL (kontrakt: pełne URL-e zdjęć)."""
    if not path:
        return None
    return request.url_root.rstrip('/') + '/static/' + path.lstrip('/')


def json_page(items, page, per_page, total, has_next):
    """Koperta odpowiedzi paginowanej: { success, data: [...], pagination: {...} }."""
    return jsonify({
        'success': True,
        'data': items,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'has_next': has_next,
        },
    }), 200
