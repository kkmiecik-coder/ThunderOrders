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
    from datetime import timedelta
    from sqlalchemy import func

    tab = request.args.get('tab', 'active')

    # Granica archiwum: 3 dni od teraz
    archive_cutoff = get_local_now() - timedelta(days=3)

    # Dozwolone statusy (te same co w Order.can_upload_product_payment)
    allowed_statuses = [
        'oczekujace',
        'dostarczone_proxy',
        'w_drodze_polska',
        'urzad_celny',
        'dostarczone_gom',
        'spakowane',
    ]

    # Zamówienia użytkownika w dozwolonych statusach
    # - Offer orders (exclusive/pre-order): muszą mieć offer_page_id
    # - On-hand orders: nie mają offer_page_id, ale mają payment_stages=2
    # - Pre-order/on-hand: 'nowe' też dozwolone (klient płaci od razu)
    all_orders = Order.query.filter(
        Order.user_id == current_user.id,
        db.or_(
            # Offer orders (exclusive, pre-order)
            Order.offer_page_id.isnot(None),
            # On-hand orders
            Order.order_type == 'on_hand'
        ),
        db.or_(
            Order.status.in_(allowed_statuses),
            db.and_(Order.order_type.in_(['pre_order', 'on_hand']), Order.status == 'nowe')
        )
    ).order_by(Order.created_at.desc()).all()

    # Podział: zamówienia do opłacenia vs w pełni opłacone
    orders = []
    fully_paid_orders = []
    fully_paid_recent = []
    archive_orders = []

    for order in all_orders:
        statuses = [order.product_payment_status]
        if order.payment_stages == 4:
            statuses.append(order.stage_2_status or 'none')
        if order.order_type != 'on_hand':
            statuses.append(order.stage_3_status)
        statuses.append(order.stage_4_status)

        if all(s == 'approved' for s in statuses):
            # Sprawdź datę ostatniego zatwierdzenia
            last_approval = db.session.query(
                func.max(PaymentConfirmation.updated_at)
            ).filter(
                PaymentConfirmation.order_id == order.id,
                PaymentConfirmation.status == 'approved'
            ).scalar()

            if last_approval and last_approval < archive_cutoff:
                archive_orders.append(order)
            else:
                fully_paid_recent.append(order)
        else:
            orders.append(order)

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
        title='Potwierdzenia płatności'
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

        # === Walidacja zamówień ===
        all_order_ids = [entry['order_id'] for entry in order_stages]

        orders = Order.query.filter(
            Order.id.in_(all_order_ids),
            Order.user_id == current_user.id
        ).all()

        orders_by_id = {o.id: o for o in orders}

        if len(orders) != len(set(all_order_ids)):
            return _upload_error('Nie masz uprawnień do wybranych zamówień.')

        # Sprawdź uprawnienia per zamówienie × etap
        cannot_upload_entries = []
        for entry in order_stages:
            order = orders_by_id.get(entry['order_id'])
            if not order:
                continue
            for stage in entry['stages']:
                can_upload = False
                if stage == 'product':
                    can_upload = order.can_upload_product_payment
                elif stage == 'korean_shipping':
                    can_upload = order.can_upload_stage_2
                elif stage == 'customs_vat':
                    can_upload = order.can_upload_stage_3
                elif stage == 'domestic_shipping':
                    can_upload = order.can_upload_stage_4
                if not can_upload:
                    cannot_upload_entries.append(order.order_number)
                    break

        if cannot_upload_entries:
            order_numbers = ', '.join(set(cannot_upload_entries))
            return _upload_error(f'Nie można wgrać potwierdzenia dla zamówień: {order_numbers}')

        # === Zapisz plik ===
        if not saved_filename:
            # Normal upload - save file now
            saved_filename = save_payment_proof_file(file)
            if not saved_filename:
                return _upload_error('Błąd podczas zapisywania pliku.')

        # Metoda płatności wybrana przez klienta
        payment_method_id = request.form.get('payment_method_id', type=int)

        # === Twórz/aktualizuj PaymentConfirmation per zamówienie × etap ===
        created_count = 0
        now = get_local_now()

        for entry in order_stages:
            order = orders_by_id.get(entry['order_id'])
            if not order:
                continue

            for stage in entry['stages']:
                # Kwota zależna od etapu
                stage_amounts = {
                    'product': order.effective_total,
                    'korean_shipping': order.proxy_shipping_total,
                    'customs_vat': order.customs_vat_total,
                    'domestic_shipping': Decimal(str(order.shipping_cost)) if order.shipping_cost else Decimal('0.00'),
                }
                amount = stage_amounts.get(stage, order.effective_total)

                # Pobierz istniejące potwierdzenie dla tego etapu
                existing = PaymentConfirmation.query.filter_by(
                    order_id=order.id,
                    payment_stage=stage
                ).first()

                if existing:
                    if existing.is_approved:
                        continue

                    # Nadpisz istniejące (pending lub rejected)
                    existing.proof_file = saved_filename
                    existing.uploaded_at = now
                    existing.status = 'pending'
                    existing.rejection_reason = None
                    existing.amount = amount
                    existing.payment_method_id = payment_method_id

                    log_activity(
                        user=current_user,
                        action='payment_confirmation_reuploaded',
                        entity_type='order',
                        entity_id=order.id,
                        new_value={
                            'order_number': order.order_number,
                            'payment_stage': stage,
                            'filename': saved_filename,
                            'amount': float(amount)
                        }
                    )
                else:
                    # Nowy rekord
                    confirmation = PaymentConfirmation(
                        order_id=order.id,
                        payment_stage=stage,
                        amount=amount,
                        proof_file=saved_filename,
                        uploaded_at=now,
                        status='pending',
                        payment_method_id=payment_method_id,
                    )
                    db.session.add(confirmation)

                    log_activity(
                        user=current_user,
                        action='payment_confirmation_uploaded',
                        entity_type='order',
                        entity_id=order.id,
                        new_value={
                            'order_number': order.order_number,
                            'payment_stage': stage,
                            'filename': saved_filename,
                            'amount': float(amount)
                        }
                    )

                created_count += 1

        # === Commit: klient widzi "Weryfikacja" ===
        db.session.commit()

        # === OCR Verification (background) ===
        from modules.auth.models import Settings
        ocr_enabled = Settings.get_value('ocr_enabled', False)
        if ocr_enabled:
            try:
                # Przygotuj dane do background task (serializowalne, bez ORM)
                all_order_numbers = [
                    orders_by_id[e['order_id']].order_number
                    for e in order_stages
                    if e['order_id'] in orders_by_id
                ]

                total_expected = Decimal('0.00')
                for entry in order_stages:
                    order = orders_by_id.get(entry['order_id'])
                    if not order:
                        continue
                    for stage in entry['stages']:
                        stage_amounts = {
                            'product': order.effective_total,
                            'korean_shipping': order.proxy_shipping_total,
                            'customs_vat': order.customs_vat_total,
                            'domestic_shipping': Decimal(str(order.shipping_cost)) if order.shipping_cost else Decimal('0.00'),
                        }
                        total_expected += stage_amounts.get(stage, Decimal('0.00'))

                ocr_task_data = {
                    'saved_filename': saved_filename,
                    'payment_method_id': payment_method_id,
                    'user_id': current_user.id,
                    'order_numbers': all_order_numbers,
                    'total_expected': float(total_expected),
                }

                from extensions import executor
                from utils.ocr_background import process_ocr_verification
                executor.submit(process_ocr_verification, ocr_task_data)

                current_app.logger.info(f"OCR background task submitted for {saved_filename}")
            except Exception as e:
                current_app.logger.error(f"Error submitting OCR background task: {e}")

        # Powiadom adminów o nowym potwierdzeniu płatności
        stage_display_names = {
            'product': 'Płatność za produkt',
            'korean_shipping': 'Wysyłka z Korei',
            'customs_vat': 'Cło i VAT',
            'domestic_shipping': 'Wysyłka krajowa'
        }
        for entry in order_stages:
            order = orders_by_id.get(entry['order_id'])
            if not order:
                continue
            stage_names = ', '.join(stage_display_names.get(s, s) for s in entry['stages'])
            try:
                from utils.email_manager import EmailManager
                from utils.push_manager import PushManager
                EmailManager.notify_admin_payment_uploaded(order, stage_names)
                PushManager.notify_admin_payment_uploaded(order, stage_names)
            except Exception as e:
                current_app.logger.error(f'Błąd powiadomienia admina o płatności: {e}')

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
