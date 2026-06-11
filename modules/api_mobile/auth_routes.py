"""Trasy auth + meta (health, app-version) dla mobilnego API."""

from flask import current_app, request
from flask_jwt_extended import create_access_token, create_refresh_token
from extensions import db
from modules.auth.models import User
from . import api_mobile_bp
from .helpers import json_ok, json_err, serialize_user


@api_mobile_bp.route('/health', methods=['GET'])
def health():
    return json_ok({'status': 'ok'})


@api_mobile_bp.route('/app-version', methods=['GET'])
def app_version():
    return json_ok({
        'min_version': current_app.config['MOBILE_MIN_APP_VERSION'],
        'latest_version': current_app.config['MOBILE_LATEST_APP_VERSION'],
    })


@api_mobile_bp.route('/auth/login', methods=['POST'])
def login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get('email') or '').strip().lower()
    password = payload.get('password') or ''

    if not email or not password:
        return json_err('missing_fields', 'Podaj e-mail i hasło.', 401)

    user = User.query.filter(db.func.lower(User.email) == email).first()
    if user is None or not user.check_password(password):
        return json_err('invalid_credentials', 'Nieprawidłowy e-mail lub hasło.', 401)
    if not user.is_active:
        return json_err('account_inactive', 'Konto jest nieaktywne.', 403)
    if not user.email_verified:
        return json_err('email_not_verified', 'Potwierdź adres e-mail, aby się zalogować.', 403)

    identity = str(user.id)
    return json_ok({
        'access_token': create_access_token(identity=identity),
        'refresh_token': create_refresh_token(identity=identity),
        'user': serialize_user(user),
    })
