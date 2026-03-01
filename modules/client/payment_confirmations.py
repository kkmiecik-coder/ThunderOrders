"""
Client Payment Confirmations Module - Routes
Endpointy uploadu i zarządzania potwierdzeniami płatności dla zamówień Exclusive.
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
    Panel potwierdzeń płatności - lista zamówień Exclusive wymagających potwierdzenia.
    """
    # Dozwolone statusy (te same co w Order.can_upload_product_payment)
    allowed_statuses = [
        'oczekujace',
        'dostarczone_proxy',
        'w_drodze_polska',
        'urzad_celny',
        'dostarczone_gom',
        'spakowane',
    ]

    # Zamówienia Exclusive użytkownika w dozwolonych statusach
    orders = Order.query.filter(
        Order.user_id == current_user.id,
        Order.is_exclusive == True,
        Order.status.in_(allowed_statuses)
    ).order_by(Order.created_at.desc()).all()

    # Sprawdź czy którekolwiek zamówienie ma 4 etapy (dla warunkowego renderowania kolumny E4)
    any_order_has_4_stages = any(order.payment_stages == 4 for order in orders)

    # Metody płatności (dane do przelewu)
    payment_methods = PaymentMethod.get_active()

    return render_template(
        'client/payment_confirmations/list.html',
        orders=orders,
        any_order_has_4_stages=any_order_has_4_stages,
        payment_methods=payment_methods,
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
                flash('Nieprawidłowe dane zamówień.', 'error')
                return redirect(url_for('client.payment_confirmations'))
        else:
            # Fallback: stary format order_ids → domyślny etap 'product'
            order_ids_raw = request.form.get('order_ids', '')
            try:
                if order_ids_raw.startswith('['):
                    order_ids = json.loads(order_ids_raw)
                else:
                    order_ids = [int(oid.strip()) for oid in order_ids_raw.split(',') if oid.strip()]
            except (ValueError, json.JSONDecodeError):
                flash('Nieprawidłowe dane zamówień.', 'error')
                return redirect(url_for('client.payment_confirmations'))

            for oid in order_ids:
                order_stages.append({'order_id': oid, 'stages': ['product']})

        if not order_stages:
            flash('Nie wybrano żadnych zamówień.', 'error')
            return redirect(url_for('client.payment_confirmations'))

        # === Walidacja pliku ===
        if 'proof_file' not in request.files:
            flash('Nie przesłano pliku potwierdzenia.', 'error')
            return redirect(url_for('client.payment_confirmations'))

        file = request.files['proof_file']

        if file.filename == '':
            flash('Nie wybrano pliku.', 'error')
            return redirect(url_for('client.payment_confirmations'))

        if not allowed_proof_file(file.filename):
            flash('Nieprawidłowy format pliku. Dozwolone: JPG, PNG, PDF.', 'error')
            return redirect(url_for('client.payment_confirmations'))

        # Sprawdź rozmiar pliku
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        if file_size > MAX_PROOF_FILE_SIZE:
            flash('Plik jest za duży. Maksymalny rozmiar: 5MB.', 'error')
            return redirect(url_for('client.payment_confirmations'))

        # === Walidacja zamówień ===
        all_order_ids = [entry['order_id'] for entry in order_stages]

        orders = Order.query.filter(
            Order.id.in_(all_order_ids),
            Order.user_id == current_user.id
        ).all()

        orders_by_id = {o.id: o for o in orders}

        if len(orders) != len(set(all_order_ids)):
            flash('Nie masz uprawnień do wybranych zamówień.', 'error')
            return redirect(url_for('client.payment_confirmations'))

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
            flash(f'Nie można wgrać potwierdzenia dla zamówień: {order_numbers}', 'error')
            return redirect(url_for('client.payment_confirmations'))

        # === Zapisz plik ===
        saved_filename = save_payment_proof_file(file)

        if not saved_filename:
            flash('Błąd podczas zapisywania pliku.', 'error')
            return redirect(url_for('client.payment_confirmations'))

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
                        status='pending'
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

        db.session.commit()

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
                EmailManager.notify_admin_payment_uploaded(order, stage_names)
            except Exception as e:
                current_app.logger.error(f'Błąd powiadomienia admina o płatności: {e}')

        if created_count == 1:
            flash('Potwierdzenie płatności zostało przesłane.', 'success')
        else:
            flash(f'Potwierdzenie płatności zostało przesłane dla {created_count} zamówień.', 'success')

        return redirect(url_for('client.payment_confirmations'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Błąd podczas uploadu potwierdzenia płatności: {str(e)}")
        flash('Wystąpił błąd podczas przesyłania potwierdzenia. Spróbuj ponownie.', 'error')
        return redirect(url_for('client.payment_confirmations'))


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
