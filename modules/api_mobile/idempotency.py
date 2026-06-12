"""Idempotency-Key dla mutacji składających zamówienia (checkout + place-order)."""
import json
from functools import wraps

from flask import request, jsonify
from flask_jwt_extended import get_jwt_identity
from sqlalchemy.exc import IntegrityError

from extensions import db
from .models import MobileIdempotencyKey


def idempotent(endpoint_name):
    """Dekorator: jeśli nagłówek Idempotency-Key obecny — zapewnia jednokrotne wykonanie
    per (user_id, key). Brak nagłówka = zachowanie jak dotychczas (D3: klucz opcjonalny).

    Wzorzec claim-first (D2a): wiersz `processing` (status_code=NULL) wstawiany PRZED
    przetwarzaniem; UNIQUE (user_id, idempotency_key) gwarantuje brak duplikatu nawet
    przy współbieżności. Dekorator MUSI być POD @jwt_required() (używa get_jwt_identity).
    """
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = (request.headers.get('Idempotency-Key') or '').strip()
            if not key:
                return fn(*args, **kwargs)
            user_id = int(get_jwt_identity())
            MobileIdempotencyKey.purge_expired()  # lazy cleanup
            # Claim: spróbuj wstawić wiersz processing
            claim = MobileIdempotencyKey(user_id=user_id, idempotency_key=key,
                                         endpoint=endpoint_name)
            db.session.add(claim)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                existing = MobileIdempotencyKey.query.filter_by(
                    user_id=user_id, idempotency_key=key).first()
                if existing and existing.status_code is not None:
                    return jsonify(json.loads(existing.response_body)), existing.status_code
                # Wciąż przetwarzane przez inne żądanie
                return jsonify({'success': False, 'error': {
                    'code': 'idempotency_in_progress',
                    'message': 'Żądanie z tym kluczem jest właśnie przetwarzane.'}}), 409
            # Wykonaj właściwą logikę
            rv = fn(*args, **kwargs)
            if not isinstance(rv, tuple):
                rv = (rv, 200)
            resp, status = rv
            claim.status_code = status
            claim.response_body = resp.get_data(as_text=True)
            db.session.commit()
            return resp, status
        return wrapper
    return deco
