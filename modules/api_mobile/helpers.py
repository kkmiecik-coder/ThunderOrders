"""Wspólne helpery odpowiedzi JSON i serializacji dla mobilnego API."""

from flask import jsonify


def json_ok(data=None, status=200):
    return jsonify({'success': True, 'data': data if data is not None else {}}), status


def json_err(code, message, status=400):
    return jsonify({'success': False, 'error': {'code': code, 'message': message}}), status


def serialize_user(user):
    full = ' '.join(p for p in [user.first_name, user.last_name] if p).strip() or None
    return {
        'id': user.id,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': full,
        'phone': user.phone,
        'role': user.role,
        'avatar_url': user.avatar_url,
        'email_verified': bool(user.email_verified),
    }
