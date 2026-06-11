"""Trasy auth + meta (health, app-version) dla mobilnego API."""

from datetime import datetime, timezone

from flask import current_app, request
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt, jwt_required, get_jwt_identity
from extensions import db
from modules.auth.models import User
from modules.orders.models import get_local_now
from utils.email_manager import EmailManager
from . import api_mobile_bp
from .helpers import json_ok, json_err, serialize_user
from .models import MobileTokenBlocklist


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


@api_mobile_bp.route('/auth/register', methods=['POST'])
def register():
    p = request.get_json(silent=True) or {}
    email = (p.get('email') or '').strip().lower()
    password = p.get('password') or ''
    first_name = (p.get('first_name') or '').strip()
    last_name = (p.get('last_name') or '').strip()
    phone = (p.get('phone') or '').strip()

    if not email or not password:
        return json_err('missing_fields', 'E-mail i hasło są wymagane.', 400)
    if User.query.filter(db.func.lower(User.email) == email).first():
        return json_err('email_taken', 'Konto z tym adresem już istnieje.', 409)

    user = User(email=email, first_name=first_name, last_name=last_name,
                phone=phone, role='client', is_active=True, email_verified=False)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    code, _ = user.generate_verification_code()
    db.session.commit()
    EmailManager.send_verification_code(user, code)

    return json_ok({'email': email, 'message': 'Wysłaliśmy kod weryfikacyjny na e-mail.'}, 201)


@api_mobile_bp.route('/auth/resend-code', methods=['POST'])
def resend_code():
    p = request.get_json(silent=True) or {}
    email = (p.get('email') or '').strip().lower()
    user = User.query.filter(db.func.lower(User.email) == email).first()
    # Nie zdradzamy, czy konto istnieje — zawsze 200.
    if user and not user.email_verified:
        can_resend, _secs = user.can_resend_code()
        if can_resend:
            code, _ = user.generate_verification_code()
            db.session.commit()
            EmailManager.send_verification_code(user, code)
    return json_ok({'message': 'Jeśli konto wymaga weryfikacji, wysłaliśmy nowy kod.'})


@api_mobile_bp.route('/auth/verify-email', methods=['POST'])
def verify_email_code():
    p = request.get_json(silent=True) or {}
    email = (p.get('email') or '').strip().lower()
    code = (p.get('code') or '').strip()

    user = User.query.filter(db.func.lower(User.email) == email).first()
    if user is None:
        return json_err('invalid_code', 'Nieprawidłowy kod.', 400)
    if user.email_verified:
        return json_err('already_verified', 'Konto jest już zweryfikowane.', 400)

    success, error_message = user.verify_code(code)
    db.session.commit()  # verify_code mutuje attempts/lock/verified — utrwalamy zawsze
    if not success:
        if user.is_verification_locked():
            slug = 'invalid_code'  # lockout świadomie mapowany na invalid_code (komunikat niesie szczegóły)
        elif (not user.email_verification_code_expires
              or get_local_now() > user.email_verification_code_expires):
            slug = 'code_expired'
        else:
            slug = 'invalid_code'
        return json_err(slug, error_message, 400)

    identity = str(user.id)
    return json_ok({
        'access_token': create_access_token(identity=identity),
        'refresh_token': create_refresh_token(identity=identity),
        'user': serialize_user(user),
    })


@api_mobile_bp.route('/auth/me', methods=['GET'])
@jwt_required()
def me():
    user = User.query.get(int(get_jwt_identity()))
    if user is None:
        return json_err('user_not_found', 'Nie znaleziono użytkownika.', 404)
    return json_ok({'user': serialize_user(user)})


@api_mobile_bp.route('/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    return json_ok({'access_token': create_access_token(identity=identity)})


@api_mobile_bp.route('/auth/logout', methods=['POST'])
@jwt_required(refresh=True)
def logout():
    token = get_jwt()
    exp = datetime.fromtimestamp(token['exp'], tz=timezone.utc).replace(tzinfo=None)
    db.session.add(MobileTokenBlocklist(
        jti=token['jti'],
        token_type='refresh',
        user_id=int(get_jwt_identity()),
        expires_at=exp,
    ))
    db.session.commit()
    return json_ok({'message': 'Wylogowano.'})
