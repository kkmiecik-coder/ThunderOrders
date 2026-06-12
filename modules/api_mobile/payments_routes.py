"""Trasy płatności (metody, potwierdzenia, BULK upload dowodu) dla mobilnego API (E6)."""

import os

from flask import request, current_app, send_from_directory, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from extensions import limiter
from modules.payments.models import PaymentMethod
from modules.orders.models import PaymentConfirmation
from . import api_mobile_bp
from .helpers import json_ok, json_err, to_grosze


def _abs_static(path):
    """Względny URL '/static/...' -> absolutny (kontrakt: pełne URL-e)."""
    if not path:
        return None
    if path.startswith('http'):
        return path
    return request.url_root.rstrip('/') + path


def _serialize_payment_method(m):
    d = m.to_dict()
    return {
        'id': d['id'], 'name': d['name'], 'recipient': d['recipient'],
        'account_number': d['account_number'], 'account_number_label': d['account_number_label'],
        'code': d['code'], 'code_label': d['code_label'], 'transfer_title': d['transfer_title'],
        'additional_info': d['additional_info'], 'sort_order': d['sort_order'],
        'logo_light_url': _abs_static(d['logo_light_url']),
        'logo_dark_url': _abs_static(d['logo_dark_url']),
    }


@api_mobile_bp.route('/payment-methods', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def payment_methods():
    methods = PaymentMethod.get_active()
    return json_ok({'methods': [_serialize_payment_method(m) for m in methods]})


def _proof_url(filename):
    """Absolutny URL dowodu przez bliźniaczą trasę JWT (D1=a)."""
    if not filename:
        return None
    return request.url_root.rstrip('/') + url_for('api_mobile.serve_proof_mobile',
                                                   filename=filename)


@api_mobile_bp.route('/payment-confirmations/proof/<path:filename>', methods=['GET'])
@jwt_required()
@limiter.limit("300 per minute")  # read-only; ekrany z wieloma miniaturami dowodów
def serve_proof_mobile(filename):
    filename = secure_filename(filename)                      # traversal-guard
    conf = PaymentConfirmation.query.filter_by(proof_file=filename).first()
    if conf is None or conf.order is None or conf.order.user_id != int(get_jwt_identity()):
        return json_err('not_found', 'Plik nie istnieje.', 404)
    folder = os.path.join(current_app.root_path, 'uploads', 'payment_confirmations')
    return send_from_directory(folder, filename)


# === Task 4: BULK upload dowodu (multipart) — [D2 bulk, D4=a bez @idempotent] ===

import json as _json
from extensions import db
from modules.orders.models import Order
from modules.client.payment_confirmation_service import (
    VALID_STAGES, validate_bulk_upload, record_bulk_payment_proofs,
)
from modules.client.payment_confirmations import (
    allowed_proof_file, save_payment_proof_file, MAX_PROOF_FILE_SIZE,
)
from utils.file_validation import validate_proof_file

MAX_BULK_PAIRS = 50


def _parse_items(raw):
    """JSON-string płaskich par -> webowy kształt order_stages (grupowanie + dedupe).

    Zwraca (order_stages, None) lub (None, komunikat_błędu).
    """
    try:
        parsed = _json.loads(raw or '')
    except (ValueError, TypeError):
        return None, 'Pole items musi być poprawnym JSON-em (lista par).'
    if not isinstance(parsed, list) or not parsed:
        return None, 'Pole items musi być niepustą listą par {order_id, payment_stage}.'
    if len(parsed) > MAX_BULK_PAIRS:
        return None, f'Maksymalnie {MAX_BULK_PAIRS} par w jednym żądaniu.'
    pairs = set()
    for it in parsed:
        if not isinstance(it, dict):
            return None, 'Każdy element items musi być obiektem {order_id, payment_stage}.'
        try:
            oid = int(it.get('order_id'))
        except (TypeError, ValueError):
            return None, 'Pole order_id musi być liczbą całkowitą.'
        stage = (it.get('payment_stage') or '').strip()
        if stage not in VALID_STAGES:
            return None, f'Nieznany etap płatności: {stage or "(brak)"}.'
        pairs.add((oid, stage))                               # dedupe (Korekta 3)
    grouped = {}
    for oid, stage in sorted(pairs):
        grouped.setdefault(oid, []).append(stage)
    return [{'order_id': oid, 'stages': stages} for oid, stages in grouped.items()], None


@api_mobile_bp.route('/payment-confirmations', methods=['POST'])
@jwt_required()
@limiter.limit("10 per minute")            # heavy-write (parytet checkout); D4=a: BEZ @idempotent
def upload_payment_confirmations():
    user_id = int(get_jwt_identity())
    order_stages, parse_err = _parse_items(request.form.get('items'))
    if parse_err:
        return json_err('invalid_input', parse_err, 400)

    # Walidacja bulku (wspólny serwis; all-or-nothing — P1)
    ok, err = validate_bulk_upload(user_id, order_stages)
    if not ok:
        if err['code'] == 'orders_not_found':                 # Korekta 4: maskowanie istnienia
            return _err_with_details('order_not_found', 'Zamówienie nie istnieje.', 404,
                                     {'missing_order_ids': err['missing_order_ids']})
        if err['code'] == 'stage_not_applicable':
            return _err_with_details('stage_not_applicable',
                                     'Etap nie dotyczy danego zamówienia.', 400,
                                     {'failures': err['failures']})
        return _err_with_details('stage_not_uploadable',
                                 'Nie można teraz wgrać dowodu dla wskazanych etapów.', 409,
                                 {'failures': err['failures']})

    # Plik (kolejność jak web: walidacja items/zamówień PRZED zapisem pliku)
    file = request.files.get('file')
    if file is None or file.filename == '':
        return json_err('invalid_input', 'Nie przesłano pliku dowodu (pole file).', 400)
    if not allowed_proof_file(file.filename):
        return json_err('invalid_file', 'Dozwolone formaty: JPG, PNG, PDF.', 400)
    file.seek(0, 2); size = file.tell(); file.seek(0)
    if size > MAX_PROOF_FILE_SIZE:
        return json_err('file_too_large', 'Maksymalny rozmiar pliku to 5 MB.', 400)
    saved = save_payment_proof_file(file)
    if not saved:
        return json_err('invalid_file', 'Błąd zapisu pliku.', 400)
    folder = os.path.join(current_app.root_path, 'uploads', 'payment_confirmations')
    valid, _msg = validate_proof_file(os.path.join(folder, saved))
    if not valid:
        _remove_quiet(os.path.join(folder, saved))
        return json_err('invalid_file', 'Plik jest uszkodzony lub niepełny.', 400)

    # Record + efekty uboczne — WSPÓLNY SERWIS (log_activity, commit, OCR, notify per order)
    from modules.auth.models import User
    user = User.query.get(user_id)
    method_id = request.form.get('payment_method_id', type=int)
    try:
        entries = record_bulk_payment_proofs(user, order_stages, saved, method_id)
    except Exception:
        db.session.rollback()
        _remove_quiet(os.path.join(folder, saved))
        return json_err('database_error', 'Wystąpił błąd zapisu. Spróbuj ponownie.', 500)

    return json_ok({
        'confirmations': [{
            'confirmation_id': e['confirmation'].id,
            'order_id': e['order'].id,
            'order_number': e['order'].order_number,
            'payment_stage': e['stage'],
            'status': 'pending',
            'amount': to_grosze(e['confirmation'].amount),
            'action': 'overwritten' if e['action'].endswith('reuploaded') else 'created',
        } for e in entries],
        'count': len(entries),
        'proof_url': _proof_url(saved),
    })


def _remove_quiet(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _err_with_details(code, message, status, details):
    from flask import jsonify
    return jsonify({'success': False,
                    'error': {'code': code, 'message': message, 'details': details}}), status


# === Task 5: lista potwierdzeń active/archive — [D3=a wspólny serwis] ===

from modules.client.payment_confirmation_service import get_confirmation_orders
from .orders_routes import _serialize_order_brief, _serialize_payment_stages

ALLOWED_CONFIRMATION_TABS = ('active', 'archive')


def _serialize_confirmation_row(order):
    row = _serialize_order_brief(order)
    stages = _serialize_payment_stages(order)                 # zawiera proof_url (Task 2)
    row['payment_stages'] = stages
    row['payment_summary'] = {
        'total_to_pay': to_grosze(order.total_to_pay),
        'paid_amount': to_grosze(order.paid_amount),
        'remaining_to_pay': to_grosze(order.remaining_to_pay),
    }
    row['all_approved'] = all(s['status'] == 'approved' for s in stages)
    return row


@api_mobile_bp.route('/payment-confirmations', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def list_payment_confirmations():
    user_id = int(get_jwt_identity())
    tab = (request.args.get('tab') or 'active').strip()
    if tab not in ALLOWED_CONFIRMATION_TABS:
        return json_err('invalid_input', f'Nieznana zakładka: {tab}.', 400)
    groups = get_confirmation_orders(user_id)
    shown = groups['archived'] if tab == 'archive' else groups['payable'] + groups['recent_paid']
    return json_ok({
        'tab': tab,
        'orders': [_serialize_confirmation_row(o) for o in shown],
        'active_total': len(groups['payable']) + len(groups['recent_paid']),
        'archive_count': len(groups['archived']),
    })
