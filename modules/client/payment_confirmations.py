"""
Client Payment Confirmations Module - Routes
Endpointy uploadu i zarządzania potwierdzeniami płatności dla zamówień ze stron sprzedaży.
"""

import os
import uuid
import json
from datetime import datetime
from modules.orders.models import get_local_now
from flask import render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from decimal import Decimal
from extensions import db
from modules.client import client_bp
from modules.orders.models import Order, PaymentConfirmation
from modules.payments.models import PaymentMethod
from utils.activity_logger import log_activity
from utils.file_validation import validate_proof_file
from modules.client.payment_confirmation_service import (
    validate_bulk_upload,
    record_bulk_payment_proofs,
    get_confirmation_orders,
)


# === HELPER FUNCTIONS ===

ALLOWED_PROOF_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}
MAX_PROOF_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def allowed_proof_file(filename):
    """Sprawdza czy plik ma dozwolone rozszerzenie (jpg, jpeg, png, pdf)."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_PROOF_EXTENSIONS


def save_payment_proof_file(file):
    """
    Zapisuje plik potwierdzenia płatności z unikalną nazwą.

    Args:
        file: FileStorage object z request.files

    Returns:
        str: Nazwa zapisanego pliku (z uuid prefix) lub None przy błędzie
    """
    if not file or file.filename == '':
        return None

    if not allowed_proof_file(file.filename):
        return None

    original_filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{original_filename}"

    upload_folder = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'uploads', 'payment_confirmations'
    )
    os.makedirs(upload_folder, exist_ok=True)

    filepath = os.path.join(upload_folder, unique_filename)
    file.save(filepath)

    return unique_filename


# === ROUTES ===

@client_bp.route('/payment-confirmations')
@login_required
def payment_confirmations():
    """
    Panel potwierdzeń płatności - lista zamówień ze stron sprzedaży wymagających potwierdzenia.
    Zakładki: active (domyślna) i archive.
    """
    tab = request.args.get('tab', 'active')

    # Kwalifikacja + podział active/recent/archive — wspólny serwis (parytet 1:1)
    groups = get_confirmation_orders(current_user.id)
    orders = groups['payable']
    fully_paid_recent = groups['recent_paid']
    archive_orders = groups['archived']
    fully_paid_orders = []

    # Liczniki do zakładek
    active_total = len(orders) + len(fully_paid_recent)
    archive_count = len(archive_orders)

    # Sprawdź czy którekolwiek zamówienie ma 4 etapy
    if tab == 'archive':
        display_orders = []
        fully_paid_orders = archive_orders
        any_order_has_4_stages = any(order.payment_stages == 4 for order in archive_orders)
    else:
        display_orders = orders
        fully_paid_orders = fully_paid_recent
        any_order_has_4_stages = any(order.payment_stages == 4 for order in orders)

    # Metody płatności (dane do przelewu)
    payment_methods = PaymentMethod.get_active()

    return render_template(
        'client/payment_confirmations/list.html',
        orders=display_orders,
        fully_paid_orders=fully_paid_orders,
        any_order_has_4_stages=any_order_has_4_stages,
        payment_methods=payment_methods,
        tab=tab,
        active_total=active_total,
        archive_count=archive_count,
        title='Potwierdzenia płatności',
        now=get_local_now()
    )


@client_bp.route('/payment-confirmations/upload', methods=['POST'])
@login_required
def payment_confirmations_upload():
    """
    Upload potwierdzenia płatności dla jednego lub wielu zamówień.

    Oczekiwane dane POST (form-data):
    - order_stages: JSON string z listą [{order_id, stages: ['product', ...]}, ...]
    - proof_file: plik (jpg/jpeg/png/pdf, max 5MB)

    Fallback: order_ids (stary format) z domyślnym etapem 'product'.

    Tworzy osobny rekord PaymentConfirmation dla każdego zamówienia × etap
    z tą samą nazwą pliku.
    """
    VALID_STAGES = {'product', 'korean_shipping', 'customs_vat', 'domestic_shipping'}
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def _upload_error(message):
        if is_ajax:
            return jsonify({'success': False, 'message': message}), 400
        flash(message, 'error')
        return redirect(url_for('client.payment_confirmations'))

    try:
        # === Parsowanie order_stages lub order_ids (fallback) ===
        order_stages_raw = request.form.get('order_stages', '')
        order_stages = []  # lista: [{order_id: int, stages: [str]}]

        if order_stages_raw:
            try:
                parsed = json.loads(order_stages_raw)
                for entry in parsed:
                    oid = int(entry.get('order_id', 0))
                    stages = [s for s in entry.get('stages', []) if s in VALID_STAGES]
                    if oid and stages:
                        order_stages.append({'order_id': oid, 'stages': stages})
            except (ValueError, json.JSONDecodeError, TypeError):
                return _upload_error('Nieprawidłowe dane zamówień.')
        else:
            # Fallback: stary format order_ids → domyślny etap 'product'
            order_ids_raw = request.form.get('order_ids', '')
            try:
                if order_ids_raw.startswith('['):
                    order_ids = json.loads(order_ids_raw)
                else:
                    order_ids = [int(oid.strip()) for oid in order_ids_raw.split(',') if oid.strip()]
            except (ValueError, json.JSONDecodeError):
                return _upload_error('Nieprawidłowe dane zamówień.')

            for oid in order_ids:
                order_stages.append({'order_id': oid, 'stages': ['product']})

        if not order_stages:
            return _upload_error('Nie wybrano żadnych zamówień.')

        # === QR Upload flow: file already on server ===
        qr_session_token = request.form.get('qr_session_token')
        if qr_session_token:
            from modules.client.payment_upload_sessions import PaymentUploadSession
            qr_session = PaymentUploadSession.query.filter_by(
                session_token=qr_session_token,
                user_id=current_user.id,
                status='uploaded'
            ).first()
            if not qr_session or not qr_session.uploaded_filename:
                return _upload_error('Nieprawidłowa sesja QR lub plik nie został przesłany.')
            saved_filename = qr_session.uploaded_filename
        else:
            # === Normal file upload flow ===
            if 'proof_file' not in request.files:
                return _upload_error('Nie przesłano pliku potwierdzenia.')

            file = request.files['proof_file']

            if file.filename == '':
                return _upload_error('Nie wybrano pliku.')

            if not allowed_proof_file(file.filename):
                return _upload_error('Nieprawidłowy format pliku. Dozwolone: JPG, PNG, PDF.')

            # Sprawdź rozmiar pliku
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)

            if file_size > MAX_PROOF_FILE_SIZE:
                return _upload_error('Plik jest za duży. Maksymalny rozmiar: 5MB.')

            saved_filename = None

        # === Walidacja zamówień (ownership + can_upload per para) — wspólny serwis ===
        ok, err = validate_bulk_upload(current_user.id, order_stages)
        if not ok:
            if err['code'] == 'orders_not_found':
                return _upload_error('Nie masz uprawnień do wybranych zamówień.')
            # stage_not_applicable / stage_not_uploadable — web skleja w jeden komunikat (parytet)
            order_numbers = ', '.join(sorted({f['order_number'] for f in err['failures']}))
            return _upload_error(f'Nie można wgrać potwierdzenia dla zamówień: {order_numbers}')

        # === Zapisz plik ===
        if not saved_filename:
            # Normal upload - save file now
            saved_filename = save_payment_proof_file(file)
            if not saved_filename:
                return _upload_error('Błąd podczas zapisywania pliku.')

            # Walidacja integralności pliku (truncated/corrupt detection)
            upload_folder = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                'uploads', 'payment_confirmations'
            )
            saved_filepath = os.path.join(upload_folder, saved_filename)
            is_valid, validation_error = validate_proof_file(saved_filepath)
            if not is_valid:
                # Sprzątaj uszkodzony plik
                try:
                    os.remove(saved_filepath)
                except OSError:
                    pass
                current_app.logger.warning(
                    f'Payment proof validation failed for user {current_user.id}: {validation_error}'
                )
                return _upload_error(
                    'Plik wydaje się uszkodzony lub niepełny. '
                    'Spróbuj ponownie lub wybierz inny plik.'
                )

        # Metoda płatności wybrana przez klienta
        payment_method_id = request.form.get('payment_method_id', type=int)

        # === Zapis + commit + OCR + notify — wspólny serwis (parytet: commit po pętli,
        # notify batchowane per zamówienie, jeden task OCR dla bulku) ===
        entries = record_bulk_payment_proofs(
            current_user, order_stages, saved_filename, payment_method_id
        )
        created_count = len(entries)

        if is_ajax:
            # Zwróć JSON — JS zamknie modal i zaktualizuje karty
            updated_stages = []
            for entry in order_stages:
                for stage in entry['stages']:
                    updated_stages.append({
                        'order_id': entry['order_id'],
                        'stage': stage,
                        'status': 'pending',
                    })
            return jsonify({
                'success': True,
                'message': f'Potwierdzenie przesłane dla {created_count} zamówień.' if created_count > 1
                           else 'Potwierdzenie płatności zostało przesłane.',
                'updated_stages': updated_stages,
            })
        else:
            if created_count == 1:
                flash('Potwierdzenie płatności zostało przesłane.', 'success')
            else:
                flash(f'Potwierdzenie płatności zostało przesłane dla {created_count} zamówień.', 'success')
            return redirect(url_for('client.payment_confirmations'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Błąd podczas uploadu potwierdzenia płatności: {str(e)}")
        return _upload_error('Wystąpił błąd podczas przesyłania. Spróbuj ponownie.')


@client_bp.route('/payment-confirmations/payment-methods')
@login_required
def payment_confirmations_methods():
    """
    Zwraca aktywne metody płatności (dane do przelewu) w formacie JSON.
    Używane przez modal do wyświetlenia danych przelewu.
    """
    methods = PaymentMethod.get_active()

    return jsonify({
        'success': True,
        'methods': [m.to_dict() for m in methods]
    })
