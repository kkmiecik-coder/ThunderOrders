"""
Admin Payment Confirmations Routes
Zarządzanie potwierdzeniami płatności w panelu admina
"""

from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from modules.admin import admin_bp
from utils.decorators import role_required
# Lazy import log_activity inside functions to avoid circular import
from extensions import db
from modules.orders.models import PaymentConfirmation, Order
from datetime import datetime


@admin_bp.route('/payment-confirmations')
@login_required
@role_required('admin', 'mod')
def payment_confirmations_list():
    """
    Lista potwierdzeń płatności
    Sortowanie: pending first (oldest first), potem approved/rejected (newest first)
    """
    # Filtry
    status_filter = request.args.get('status', 'all')
    stage_filter = request.args.get('stage', 'all')

    # Bazowe query
    query = PaymentConfirmation.query.join(Order)

    # Filtruj po statusie
    if status_filter != 'all':
        query = query.filter(PaymentConfirmation.status == status_filter)

    # Filtruj po etapie
    if stage_filter != 'all':
        query = query.filter(PaymentConfirmation.payment_stage == stage_filter)

    # Sortowanie: pending first (oldest first), potem reszta (newest first)
    from sqlalchemy import case
    query = query.order_by(
        # Pending first (value 0), then approved/rejected (value 1)
        case(
            (PaymentConfirmation.status == 'pending', 0),
            else_=1
        ).asc(),
        # For pending: oldest first (uploaded_at ASC)
        # For others: newest first (uploaded_at DESC)
        case(
            (PaymentConfirmation.status == 'pending', PaymentConfirmation.uploaded_at),
            else_=PaymentConfirmation.updated_at
        ).asc()
    )

    confirmations = query.all()

    # Statystyki
    pending_count = PaymentConfirmation.query.filter_by(status='pending').count()
    approved_count = PaymentConfirmation.query.filter_by(status='approved').count()
    rejected_count = PaymentConfirmation.query.filter_by(status='rejected').count()

    return render_template(
        'admin/payment_confirmations/list.html',
        confirmations=confirmations,
        status_filter=status_filter,
        stage_filter=stage_filter,
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        page_title='Potwierdzenia płatności'
    )


@admin_bp.route('/payment-confirmations/<int:confirmation_id>/approve', methods=['POST'])
@login_required
@role_required('admin')
def payment_confirmation_approve(confirmation_id):
    """Akceptuj potwierdzenie płatności"""
    from utils.activity_logger import log_activity
    confirmation = PaymentConfirmation.query.get_or_404(confirmation_id)
    order = confirmation.order

    if confirmation.status != 'pending':
        return jsonify({
            'success': False,
            'message': 'To potwierdzenie nie jest w statusie oczekującym.'
        }), 400

    # Zmień status
    confirmation.status = 'approved'
    confirmation.updated_at = datetime.now()

    db.session.commit()

    # Activity log
    log_activity(
        user=current_user,
        action='payment_confirmation_approved',
        entity_type='order',
        entity_id=order.id,
        old_value={'status': 'pending'},
        new_value={
            'status': 'approved',
            'order_number': order.order_number,
            'amount': float(confirmation.amount),
            'payment_stage': confirmation.payment_stage
        }
    )

    # Wyślij email do klienta
    try:
        from utils.email_sender import send_payment_approved_email
        if order.user and order.user.email:
            send_payment_approved_email(
                user_email=order.user.email,
                user_name=order.user.first_name or order.user.email,
                order_number=order.order_number,
                amount=float(confirmation.amount),
                order_detail_url=url_for('client.order_detail', order_id=order.id, _external=True)
            )
    except Exception as e:
        # Nie blokuj akceptacji jeśli email się nie wysłał
        print(f"[WARNING] Email payment_approved failed: {e}")

    return jsonify({
        'success': True,
        'message': f'Potwierdzenie płatności dla zamówienia {order.order_number} zostało zaakceptowane.'
    })


@admin_bp.route('/payment-confirmations/<int:confirmation_id>/reject', methods=['POST'])
@login_required
@role_required('admin')
def payment_confirmation_reject(confirmation_id):
    """Odrzuć potwierdzenie płatności"""
    from utils.activity_logger import log_activity
    confirmation = PaymentConfirmation.query.get_or_404(confirmation_id)
    order = confirmation.order

    data = request.get_json()
    rejection_reason = data.get('rejection_reason', '').strip() if data else ''

    if not rejection_reason or len(rejection_reason) < 10:
        return jsonify({
            'success': False,
            'message': 'Powód odrzucenia jest wymagany (min. 10 znaków).'
        }), 400

    if confirmation.status != 'pending':
        return jsonify({
            'success': False,
            'message': 'To potwierdzenie nie jest w statusie oczekującym.'
        }), 400

    # Zmień status
    confirmation.status = 'rejected'
    confirmation.rejection_reason = rejection_reason
    confirmation.updated_at = datetime.now()

    db.session.commit()

    # Activity log
    log_activity(
        user=current_user,
        action='payment_confirmation_rejected',
        entity_type='order',
        entity_id=order.id,
        old_value={'status': 'pending'},
        new_value={
            'status': 'rejected',
            'order_number': order.order_number,
            'amount': float(confirmation.amount),
            'payment_stage': confirmation.payment_stage,
            'rejection_reason': rejection_reason
        }
    )

    # Wyślij email do klienta
    try:
        from utils.email_sender import send_payment_rejected_email
        if order.user and order.user.email:
            send_payment_rejected_email(
                user_email=order.user.email,
                user_name=order.user.first_name or order.user.email,
                order_number=order.order_number,
                amount=float(confirmation.amount),
                rejection_reason=rejection_reason,
                upload_url=url_for('client.payment_confirmations', _external=True)
            )
    except Exception as e:
        print(f"[WARNING] Email payment_rejected failed: {e}")

    return jsonify({
        'success': True,
        'message': f'Potwierdzenie płatności dla zamówienia {order.order_number} zostało odrzucone.'
    })
