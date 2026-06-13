"""Trasy auth + meta (health, app-version) dla mobilnego API."""

import hashlib
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app, request
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt, jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from extensions import db, limiter
from modules.auth.models import User
from modules.orders.models import get_local_now
from utils.email_manager import EmailManager
from . import api_mobile_bp
from .google_auth import verify_google_id_token
from .helpers import json_ok, json_err, serialize_user
from .models import MobileTokenBlocklist


EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _password_fingerprint(user):
    """Skrót hasła osadzany w tokenach — zmiana hasła unieważnia refresh tokeny."""
    return hashlib.sha256((user.password_hash or '').encode()).hexdigest()[:16]


def _issue_tokens(user, refresh=True):
    identity = str(user.id)
    claims = {'pwd': _password_fingerprint(user)}
    data = {'access_token': create_access_token(identity=identity, additional_claims=claims)}
    if refresh:
        data['refresh_token'] = create_refresh_token(identity=identity, additional_claims=claims)
    return data


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
@limiter.limit("15 per minute")  # parytet z logowaniem webowym
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

    return json_ok({**_issue_tokens(user), 'user': serialize_user(user)})


@api_mobile_bp.route('/auth/register', methods=['POST'])
@limiter.limit("30 per hour")  # parytet z rejestracją webową
def register():
    p = request.get_json(silent=True) or {}
    email = (p.get('email') or '').strip().lower()
    password = p.get('password') or ''
    first_name = (p.get('first_name') or '').strip()
    last_name = (p.get('last_name') or '').strip()
    phone = (p.get('phone') or '').strip()

    if not email or not password:
        return json_err('missing_fields', 'E-mail i hasło są wymagane.', 400)
    if not EMAIL_RE.match(email) or len(email) > 255:
        return json_err('invalid_email', 'Podaj poprawny adres e-mail.', 400)
    if len(first_name) > 100 or len(last_name) > 100 or len(phone) > 20:
        return json_err('invalid_input', 'Pola imię/nazwisko/telefon są zbyt długie.', 400)
    if User.query.filter(db.func.lower(User.email) == email).first():
        return json_err('email_taken', 'Konto z tym adresem już istnieje.', 409)

    user = User(email=email, first_name=first_name, last_name=last_name,
                phone=phone, role='client', is_active=True, email_verified=False)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # Wyścig równoległych rejestracji: unikalność email złamana mimo pre-checku.
        db.session.rollback()
        return json_err('email_taken', 'Konto z tym adresem już istnieje.', 409)

    code, _ = user.generate_verification_code()
    db.session.commit()
    email_sent = bool(EmailManager.send_verification_code(user, code))
    if not email_sent:
        # Nieudana wysyłka nie może blokować ponownej próby 60-sekundowym cooldownem.
        user.email_verification_code_sent_at = None
        db.session.commit()

    return json_ok({
        'email': email,
        'email_sent': email_sent,
        'message': ('Wysłaliśmy kod weryfikacyjny na e-mail.' if email_sent
                    else 'Konto utworzone, ale wysyłka kodu się nie powiodła. Poproś o nowy kod.'),
    }, 201)


@api_mobile_bp.route('/auth/resend-code', methods=['POST'])
@limiter.limit("30 per hour")  # wysyła e-maile — limit jak rejestracja
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
@limiter.limit("30 per minute")  # limit IP; per-konto chroni lockout verify_code
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

    if not user.is_active:
        # Konto zweryfikowane, ale dezaktywowane — nie wydajemy tokenów (parytet z login).
        return json_err('account_inactive', 'Konto jest nieaktywne.', 403)

    return json_ok({**_issue_tokens(user), 'user': serialize_user(user)})


@api_mobile_bp.route('/auth/google', methods=['POST'])
@limiter.limit("15 per minute")  # parytet z logowaniem
def google_login():
    p = request.get_json(silent=True) or {}
    token = p.get('id_token') or ''
    info = verify_google_id_token(token)
    if info is None:
        return json_err('invalid_google_token', 'Nieprawidłowy token Google.', 401)

    email = (info.get('email') or '').strip().lower()
    google_sub = info.get('sub')

    user = (User.query.filter_by(google_id=google_sub).first()
            or User.query.filter(db.func.lower(User.email) == email).first())

    if user is None:
        user = User(email=email, first_name=info.get('given_name'),
                    last_name=info.get('family_name'), role='client',
                    is_active=True, email_verified=True, google_id=google_sub)
        db.session.add(user)
    else:
        if not user.google_id:
            user.google_id = google_sub
        user.email_verified = True
    db.session.commit()

    if not user.is_active:
        return json_err('account_inactive', 'Konto jest nieaktywne.', 403)

    return json_ok({**_issue_tokens(user), 'user': serialize_user(user)})


@api_mobile_bp.route('/auth/me', methods=['GET'])
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        return json_err('user_not_found', 'Nie znaleziono użytkownika.', 404)
    if not user.is_active:
        return json_err('account_inactive', 'Konto jest nieaktywne.', 403)
    return json_ok({'user': serialize_user(user)})


@api_mobile_bp.route('/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        return json_err('user_not_found', 'Nie znaleziono użytkownika.', 401)
    if not user.is_active:
        return json_err('account_inactive', 'Konto jest nieaktywne.', 403)
    if get_jwt().get('pwd') != _password_fingerprint(user):
        # Hasło zmienione po wydaniu tokenu — wymuszamy ponowne logowanie.
        return json_err('token_revoked', 'Sesja wygasła. Zaloguj się ponownie.', 401)
    return json_ok(_issue_tokens(user, refresh=False))


@api_mobile_bp.route('/auth/logout', methods=['POST'])
@jwt_required(refresh=True)
def logout():
    token = get_jwt()
    # exp (unix ts, UTC) -> naive czas lokalny PL, spójnie z resztą bazy (get_local_now)
    exp = datetime.fromtimestamp(token['exp'], tz=ZoneInfo('Europe/Warsaw')).replace(tzinfo=None)
    MobileTokenBlocklist.purge_expired()
    db.session.add(MobileTokenBlocklist(
        jti=token['jti'],
        token_type='refresh',
        user_id=int(get_jwt_identity()),
        expires_at=exp,
    ))
    try:
        db.session.commit()
    except IntegrityError:
        # Wyścig podwójnego logout tym samym tokenem — wpis już istnieje, cel osiągnięty.
        db.session.rollback()
    return json_ok({'message': 'Wylogowano.'})
