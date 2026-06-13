"""Trasy push (rejestracja/wyrejestrowanie urządzeń FCM) dla mobilnego API (E10)."""
from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError

from extensions import db, limiter
from modules.notifications.models import get_local_now
from . import api_mobile_bp
from .helpers import json_ok, json_err
from .models import MobileDevice

_PLATFORMS = {'android', 'ios', 'web'}


@api_mobile_bp.route('/push/devices', methods=['POST'])
@jwt_required()
@limiter.limit("60 per hour")
def register_device():
    """Rejestracja/odświeżenie tokenu FCM urządzenia (upsert keyed na fcm_token).

    Token globalnie unikalny → należy do dokładnie jednego, aktualnie zalogowanego
    usera. Ponowny POST tego samego tokenu = odświeżenie (bez duplikatu); token
    zarejestrowany wcześniej przez innego usera → przepięcie na bieżącego (D4).
    """
    uid = int(get_jwt_identity())
    p = request.get_json(silent=True) or {}
    token = (p.get('fcm_token') or '').strip()
    platform = (p.get('platform') or '').strip().lower()
    if not token or len(token) > 512:
        return json_err('invalid_input', 'Pole fcm_token jest wymagane (max 512 znaków).', 400)
    if platform not in _PLATFORMS:
        return json_err('invalid_input', 'Pole platform musi być: android, ios lub web.', 400)

    dev = MobileDevice.query.filter_by(fcm_token=token).first()
    if dev is None:
        dev = MobileDevice(user_id=uid, fcm_token=token, platform=platform)
        db.session.add(dev)
    else:
        dev.user_id = uid          # przepięcie tokenu na bieżącego usera (bezpieczeństwo)
        dev.platform = platform
        dev.last_used_at = get_local_now()
    try:
        db.session.commit()
    except IntegrityError:
        # Wyścig: równoległy POST tego samego tokenu wstawił wiersz między SELECT a INSERT.
        db.session.rollback()
        dev = MobileDevice.query.filter_by(fcm_token=token).first()
        if dev is None:
            raise
        dev.user_id = uid
        dev.platform = platform
        dev.last_used_at = get_local_now()
        db.session.commit()
    return json_ok({'id': dev.id, 'platform': dev.platform}, 201)


@api_mobile_bp.route('/push/devices/<path:token>', methods=['DELETE'])
@jwt_required()
def unregister_device(token):
    """Wyrejestrowanie tokenu FCM (przy logout). Filtr po token AND user_id z JWT;
    brak dopasowania (nie istnieje LUB cudzy) → 404 maskujące (parytet ownership E5–E8)."""
    uid = int(get_jwt_identity())
    dev = MobileDevice.query.filter_by(fcm_token=token, user_id=uid).first()
    if dev is None:
        return json_err('not_found', 'Nie znaleziono urządzenia.', 404)  # maskuje też cudzy token
    db.session.delete(dev)
    db.session.commit()
    return json_ok({'message': 'Wyrejestrowano urządzenie.'})
