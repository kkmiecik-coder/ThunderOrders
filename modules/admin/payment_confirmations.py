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
from decimal import Decimal

import logging
logger = logging.getLogger(__name__)


def _check_sr_auto_oplacone(order):
    """
    After approving a domestic_shipping (E4) payment, check if ALL orders
    in the associated ShippingRequest have approved E4.
    If so, auto-change SR status to 'oplacone'.
    """
    from modules.orders.models import ShippingRequest, ShippingRequestOrder, ShippingRequestStatus

    # Find SR containing this order
    sro = ShippingRequestOrder.query.filter_by(order_id=order.id).first()
    if not sro:
        return

    sr = sro.shipping_request
    if not sr:
        return

    # Only transition from 'czeka_na_oplacenie'
    if sr.status != 'czeka_na_oplacenie':
        return

    # Check if ALL orders in this SR have an approved domestic_shipping confirmation
    all_paid = True
    for ro in sr.request_orders:
        has_approved_e4 = PaymentConfirmation.query.filter_by(
            order_id=ro.order_id,
            payment_stage='domestic_shipping',
            status='approved'
        ).first()
        if not has_approved_e4:
            all_paid = False
            break

    if all_paid:
        # Verify 'oplacone' status exists and is active
        status_obj = ShippingRequestStatus.query.filter_by(slug='oplacone', is_active=True).first()
        if not status_obj:
            logger.warning("SR status 'oplacone' not found or inactive — skipping auto-transition")
            return

        old_status = sr.status
        sr.status = 'oplacone'
        db.session.commit()

        logger.info(f"SR {sr.request_number} auto-transitioned to 'oplacone' (all E4 approved)")

        # Send notification about SR status change
        try:
            from utils.email_manager import EmailManager
            from utils.push_manager import PushManager
            EmailManager.notify_shipping_status_change(sr, old_status)
            PushManager.notify_shipping_status_change(sr, status_obj.name)
        except Exception as e:
            logger.error(f"Error sending SR status change notification for {sr.request_number}: {e}")


@admin_bp.route('/payment-confirmations')
@login_required
@role_required('admin', 'mod')
def payment_confirmations_list():
    """
    Lista potwierdzeń płatności
    Zakładki:
      - pending (domyślna) — tylko status='pending'
      - processed — status='approved' (jeszcze nie w archiwum) + wszystkie status='rejected'
      - archive — status='approved' AND updated_at < 3 dni temu
    Sortowanie: najstarsze na początku w każdej zakładce
    """
    from datetime import timedelta

    # Zakładka: pending / processed / archive
    tab = request.args.get('tab', 'pending')
    # Backward-compat: stary link ?tab=active traktuj jako pending
    if tab == 'active':
        tab = 'pending'
    if tab not in ('pending', 'processed', 'archive'):
        tab = 'pending'

    # Filtry
    stage_filter = request.args.get('stage', 'all')
    ocr_filter = request.args.get('ocr', 'all')

    # Granica archiwum: 3 dni od teraz
    archive_cutoff = get_local_now() - timedelta(days=3)

    # Bazowe query
    query = PaymentConfirmation.query.join(Order)

    # Filtruj po zakładce
    if tab == 'archive':
        query = query.filter(
            PaymentConfirmation.status == 'approved',
            PaymentConfirmation.updated_at < archive_cutoff
        )
    elif tab == 'processed':
        query = query.filter(
            db.or_(
                db.and_(
                    PaymentConfirmation.status == 'approved',
                    PaymentConfirmation.updated_at >= archive_cutoff
                ),
                PaymentConfirmation.status == 'rejected'
            )
        )
    else:  # pending
        query = query.filter(PaymentConfirmation.status == 'pending')

    # Filtruj po etapie
    if stage_filter != 'all':
        query = query.filter(PaymentConfirmation.payment_stage == stage_filter)

    # Filtruj po OCR
    if ocr_filter == 'auto':
        query = query.filter(PaymentConfirmation.auto_approved == True)
    elif ocr_filter == 'suggested':
        from modules.auth.models import Settings
        suggest_thresh = Settings.get_value('ocr_suggest_threshold', 60)
        auto_thresh = Settings.get_value('ocr_auto_approve_threshold', 90)
        query = query.filter(
            PaymentConfirmation.ocr_score >= suggest_thresh,
            PaymentConfirmation.ocr_score < auto_thresh,
            PaymentConfirmation.auto_approved == False
        )
    elif ocr_filter == 'manual':
        from modules.auth.models import Settings
        suggest_thresh = Settings.get_value('ocr_suggest_threshold', 60)
        query = query.filter(
            db.or_(
                PaymentConfirmation.ocr_score < suggest_thresh,
                PaymentConfirmation.ocr_score.is_(None)
            )
        )

    # Sortowanie: najstarsze na początku
    if tab == 'pending':
        query = query.order_by(PaymentConfirmation.uploaded_at.asc())
    else:
        query = query.order_by(PaymentConfirmation.updated_at.asc())

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

    # Liczniki do badge w zakładkach — liczymy grupy (po proof_file), tak jak w widoku.
    # Wiersze z NULL proof_file są liczone pojedynczo (każdy jako osobna grupa).
    from sqlalchemy import func, distinct

    def _count_groups(*filters):
        with_proof = db.session.query(
            func.count(distinct(PaymentConfirmation.proof_file))
        ).filter(*filters, PaymentConfirmation.proof_file.isnot(None)).scalar() or 0
        without_proof = PaymentConfirmation.query.filter(
            *filters, PaymentConfirmation.proof_file.is_(None)
        ).count()
        return with_proof + without_proof

    pending_count = _count_groups(PaymentConfirmation.status == 'pending')
    processed_count = _count_groups(
        db.or_(
            db.and_(
                PaymentConfirmation.status == 'approved',
                PaymentConfirmation.updated_at >= archive_cutoff
            ),
            PaymentConfirmation.status == 'rejected'
        )
    )
    archive_count = _count_groups(
        PaymentConfirmation.status == 'approved',
        PaymentConfirmation.updated_at < archive_cutoff
    )

    # Statystyki etapów
    stage_counts = {
        'product': PaymentConfirmation.query.filter_by(payment_stage='product').count(),
        'korean_shipping': PaymentConfirmation.query.filter_by(payment_stage='korean_shipping').count(),
        'customs_vat': PaymentConfirmation.query.filter_by(payment_stage='customs_vat').count(),
        'domestic_shipping': PaymentConfirmation.query.filter_by(payment_stage='domestic_shipping').count(),
    }

    auto_approved_count = PaymentConfirmation.query.filter_by(auto_approved=True).count()

    return render_template(
        'admin/payment_confirmations/list.html',
        groups=groups,
        pagination=pagination,
        tab=tab,
        stage_filter=stage_filter,
        ocr_filter=ocr_filter,
        pending_count=pending_count,
        processed_count=processed_count,
        archive_count=archive_count,
        auto_approved_count=auto_approved_count,
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

    # Wyślij email + push do klienta
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    EmailManager.notify_payment_approved(order, confirmation)
    PushManager.notify_payment_approved(order, confirmation)

    # Auto-transition SR to 'oplacone' if all E4 payments approved
    if confirmation.payment_stage == 'domestic_shipping':
        _check_sr_auto_oplacone(order)

    return jsonify({
        'success': True,
        'message': f'Potwierdzenie płatności dla zamówienia {order.order_number} zostało zaakceptowane.',
        'new_status': 'approved'
    })


@admin_bp.route('/payment-confirmations/bulk-approve', methods=['POST'])
@login_required
@role_required('admin')
def payment_confirmation_bulk_approve():
    """Zatwierdzenie wielu potwierdzeń naraz (konsolidacja tego samego dowodu)"""
    from utils.activity_logger import log_activity

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

    # Wyślij emaile - 1 mail per potwierdzenie (OK)
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    for confirmation in confirmations:
        EmailManager.notify_payment_approved(confirmation.order, confirmation)

    # Skonsolidowane push - 1 push per user_id (zapobiega race condition
    # gdy N wątków równolegle próbuje wysłać pusha do tych samych subskrypcji)
    confirmations_by_user = {}
    for confirmation in confirmations:
        order = confirmation.order
        if not order or not order.user_id:
            continue
        confirmations_by_user.setdefault(order.user_id, []).append(confirmation)

    for user_id, user_confirmations in confirmations_by_user.items():
        PushManager.notify_payment_bulk_approved(user_id, user_confirmations)

    # Auto-transition SRs to 'oplacone' if all E4 payments approved
    checked_orders = set()
    for confirmation in confirmations:
        if confirmation.payment_stage == 'domestic_shipping' and confirmation.order_id not in checked_orders:
            checked_orders.add(confirmation.order_id)
            _check_sr_auto_oplacone(confirmation.order)

    return jsonify({
        'success': True,
        'message': f'Zatwierdzono {len(confirmations)} potwierdzeń ({", ".join(approved_orders)}).',
        'new_status': 'approved'
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
        PaymentConfirmation.status != 'rejected'
    ).all()

    if not confirmations:
        return jsonify({'success': False, 'message': 'Nie znaleziono potwierdzeń do odrzucenia.'}), 400

    rejected_orders = []
    for confirmation in confirmations:
        order = confirmation.order
        old_status = confirmation.status

        # Cofnij paid_amount jeśli odrzucamy zatwierdzone
        if old_status == 'approved':
            current_paid = Decimal(str(order.paid_amount)) if order.paid_amount else Decimal('0.00')
            order.paid_amount = max(Decimal('0.00'), current_paid - Decimal(str(confirmation.amount)))

        confirmation.status = 'rejected'
        confirmation.rejection_reason = rejection_reason
        confirmation.updated_at = get_local_now()
        rejected_orders.append(order.order_number)

        log_activity(
            user=current_user,
            action='payment_confirmation_rejected',
            entity_type='order',
            entity_id=order.id,
            old_value={'status': old_status},
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

    # Emaile - 1 mail per potwierdzenie (OK)
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    for confirmation in confirmations:
        EmailManager.notify_payment_rejected(confirmation.order, confirmation, rejection_reason)

    # Skonsolidowane push - 1 push per user_id
    confirmations_by_user = {}
    for confirmation in confirmations:
        order = confirmation.order
        if not order or not order.user_id:
            continue
        confirmations_by_user.setdefault(order.user_id, []).append(confirmation)

    for user_id, user_confirmations in confirmations_by_user.items():
        PushManager.notify_payment_bulk_rejected(user_id, user_confirmations, rejection_reason)

    return jsonify({
        'success': True,
        'message': f'Odrzucono {len(confirmations)} potwierdzeń ({", ".join(rejected_orders)}).',
        'new_status': 'rejected'
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

    if confirmation.status == 'rejected':
        return jsonify({
            'success': False,
            'message': 'To potwierdzenie jest już odrzucone.'
        }), 400

    old_status = confirmation.status

    # Cofnij paid_amount jeśli odrzucamy zatwierdzone
    if old_status == 'approved':
        current_paid = Decimal(str(order.paid_amount)) if order.paid_amount else Decimal('0.00')
        order.paid_amount = max(Decimal('0.00'), current_paid - Decimal(str(confirmation.amount)))

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
        old_value={'status': old_status},
        new_value={
            'status': 'rejected',
            'order_number': order.order_number,
            'amount': float(confirmation.amount),
            'payment_stage': confirmation.payment_stage,
            'rejection_reason': rejection_reason
        }
    )

    # Wyślij email + push do klienta
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    EmailManager.notify_payment_rejected(order, confirmation, rejection_reason)
    PushManager.notify_payment_rejected(order, confirmation, rejection_reason)

    return jsonify({
        'success': True,
        'message': f'Potwierdzenie płatności dla zamówienia {order.order_number} zostało odrzucone.',
        'new_status': 'rejected',
        'old_status': old_status
    })
