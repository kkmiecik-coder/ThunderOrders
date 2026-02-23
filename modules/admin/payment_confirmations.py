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
from modules.orders.models import get_local_now


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

    # Paginacja
    page = request.args.get('page', 1, type=int)
    per_page = 20
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Grupowanie po proof_file — ten sam dowód = jeden wiersz
    groups = []
    proof_file_map = {}
    for conf in pagination.items:
        if conf.proof_file and conf.proof_file in proof_file_map:
            proof_file_map[conf.proof_file]['items'].append(conf)
        else:
            group = {'items': [conf]}
            groups.append(group)
            if conf.proof_file:
                proof_file_map[conf.proof_file] = group

    # Statystyki statusów
    pending_count = PaymentConfirmation.query.filter_by(status='pending').count()
    approved_count = PaymentConfirmation.query.filter_by(status='approved').count()
    rejected_count = PaymentConfirmation.query.filter_by(status='rejected').count()

    # Statystyki etapów
    stage_counts = {
        'product': PaymentConfirmation.query.filter_by(payment_stage='product').count(),
        'korean_shipping': PaymentConfirmation.query.filter_by(payment_stage='korean_shipping').count(),
        'customs_vat': PaymentConfirmation.query.filter_by(payment_stage='customs_vat').count(),
        'domestic_shipping': PaymentConfirmation.query.filter_by(payment_stage='domestic_shipping').count(),
    }

    return render_template(
        'admin/payment_confirmations/list.html',
        groups=groups,
        pagination=pagination,
        status_filter=status_filter,
        stage_filter=stage_filter,
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        stage_counts=stage_counts,
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
    confirmation.updated_at = get_local_now()

    # Auto-update paid_amount na zamówieniu
    from decimal import Decimal
    current_paid = Decimal(str(order.paid_amount)) if order.paid_amount else Decimal('0.00')
    order.paid_amount = current_paid + Decimal(str(confirmation.amount))

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

    # Wyślij email do klienta (obsługuje też gości przez order.customer_email)
    from utils.email_manager import EmailManager
    EmailManager.notify_payment_approved(order, confirmation)

    return jsonify({
        'success': True,
        'message': f'Potwierdzenie płatności dla zamówienia {order.order_number} zostało zaakceptowane.'
    })


@admin_bp.route('/payment-confirmations/bulk-approve', methods=['POST'])
@login_required
@role_required('admin')
def payment_confirmation_bulk_approve():
    """Zatwierdzenie wielu potwierdzeń naraz (konsolidacja tego samego dowodu)"""
    from utils.activity_logger import log_activity
    from decimal import Decimal

    data = request.get_json()
    confirmation_ids = data.get('confirmation_ids', []) if data else []

    if not confirmation_ids:
        return jsonify({'success': False, 'message': 'Brak potwierdzeń do zatwierdzenia.'}), 400

    confirmations = PaymentConfirmation.query.filter(
        PaymentConfirmation.id.in_(confirmation_ids),
        PaymentConfirmation.status == 'pending'
    ).all()

    if not confirmations:
        return jsonify({'success': False, 'message': 'Nie znaleziono oczekujących potwierdzeń.'}), 400

    approved_orders = []
    for confirmation in confirmations:
        order = confirmation.order
        confirmation.status = 'approved'
        confirmation.updated_at = get_local_now()

        current_paid = Decimal(str(order.paid_amount)) if order.paid_amount else Decimal('0.00')
        order.paid_amount = current_paid + Decimal(str(confirmation.amount))

        approved_orders.append(order.order_number)

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
                'payment_stage': confirmation.payment_stage,
                'bulk': True
            }
        )

    db.session.commit()

    # Wyślij emaile po commit
    from utils.email_manager import EmailManager
    for confirmation in confirmations:
        EmailManager.notify_payment_approved(confirmation.order, confirmation)

    return jsonify({
        'success': True,
        'message': f'Zatwierdzono {len(confirmations)} potwierdzeń ({", ".join(approved_orders)}).'
    })


@admin_bp.route('/payment-confirmations/bulk-reject', methods=['POST'])
@login_required
@role_required('admin')
def payment_confirmation_bulk_reject():
    """Odrzucenie wielu potwierdzeń naraz (ten sam dowód dla kilku zamówień)"""
    from utils.activity_logger import log_activity

    data = request.get_json()
    confirmation_ids = data.get('confirmation_ids', []) if data else []
    rejection_reason = data.get('rejection_reason', '').strip() if data else ''

    if not confirmation_ids:
        return jsonify({'success': False, 'message': 'Brak potwierdzeń do odrzucenia.'}), 400

    if not rejection_reason or len(rejection_reason) < 10:
        return jsonify({'success': False, 'message': 'Powód odrzucenia jest wymagany (min. 10 znaków).'}), 400

    confirmations = PaymentConfirmation.query.filter(
        PaymentConfirmation.id.in_(confirmation_ids),
        PaymentConfirmation.status == 'pending'
    ).all()

    if not confirmations:
        return jsonify({'success': False, 'message': 'Nie znaleziono oczekujących potwierdzeń.'}), 400

    rejected_orders = []
    for confirmation in confirmations:
        order = confirmation.order
        confirmation.status = 'rejected'
        confirmation.rejection_reason = rejection_reason
        confirmation.updated_at = get_local_now()
        rejected_orders.append(order.order_number)

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
                'rejection_reason': rejection_reason,
                'bulk': True
            }
        )

    db.session.commit()

    from utils.email_manager import EmailManager
    for confirmation in confirmations:
        EmailManager.notify_payment_rejected(confirmation.order, confirmation, rejection_reason)

    return jsonify({
        'success': True,
        'message': f'Odrzucono {len(confirmations)} potwierdzeń ({", ".join(rejected_orders)}).'
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
    confirmation.updated_at = get_local_now()

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

    # Wyślij email do klienta (obsługuje też gości przez order.customer_email)
    from utils.email_manager import EmailManager
    EmailManager.notify_payment_rejected(order, confirmation, rejection_reason)

    return jsonify({
        'success': True,
        'message': f'Potwierdzenie płatności dla zamówienia {order.order_number} zostało odrzucone.'
    })
