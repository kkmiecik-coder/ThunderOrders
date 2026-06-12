"""Wspólny serwis potwierdzeń płatności — web (bulk upload, lista) + mobilne API (E6)."""

from decimal import Decimal

from extensions import db
from modules.orders.models import Order, PaymentConfirmation, get_local_now
from utils.activity_logger import log_activity

VALID_STAGES = {'product', 'korean_shipping', 'customs_vat', 'domestic_shipping'}
_CAN_UPLOAD = {
    'product': 'can_upload_product_payment',
    'korean_shipping': 'can_upload_stage_2',
    'customs_vat': 'can_upload_stage_3',
    'domestic_shipping': 'can_upload_stage_4',
}
_STAGE_NAMES_PL = {
    'product': 'Płatność za produkt', 'korean_shipping': 'Wysyłka z Korei',
    'customs_vat': 'Cło i VAT', 'domestic_shipping': 'Wysyłka krajowa',
}


def order_stage_keys(order):
    """Zbiór etapów STRUKTURALNIE obecnych dla zamówienia (kanon: web + E5 + walidacja bulku)."""
    keys = {'product', 'domestic_shipping'}
    if order.payment_stages == 4:
        keys.add('korean_shipping')
    if order.order_type != 'on_hand':
        keys.add('customs_vat')
    return keys


def stage_amount(order, stage):
    """Autorytatywna kwota etapu (przeniesione 1:1 z webowej pętli, l. 351-358)."""
    return {
        'product': order.effective_total,
        'korean_shipping': order.proxy_shipping_total,
        'customs_vat': order.customs_vat_total,
        'domestic_shipping': (Decimal(str(order.shipping_cost))
                              if order.shipping_cost else Decimal('0.00')),
    }[stage]


def validate_bulk_upload(user_id, order_stages):
    """Walidacja bulku ALL-OR-NOTHING (parytet web l. 273-308) + klasyfikacja błędów dla mobile.

    order_stages: [{'order_id': int, 'stages': [str]}] (stages już przefiltrowane do VALID_STAGES).
    Zwraca (True, None) lub (False, {'code', ...details}):
      orders_not_found        — brakujące/cudze id (missing_order_ids)
      stage_not_applicable    — etap strukturalnie nieobecny (failures[])
      stage_not_uploadable    — can_upload False mimo obecności (failures[])
    Web skleja oba ostatnie w jeden komunikat (parytet zachowany w trasie webowej).
    """
    all_ids = [e['order_id'] for e in order_stages]
    orders = Order.query.filter(Order.id.in_(all_ids), Order.user_id == user_id).all()
    orders_by_id = {o.id: o for o in orders}
    missing = sorted(set(all_ids) - set(orders_by_id))
    if missing:
        return False, {'code': 'orders_not_found', 'missing_order_ids': missing}

    not_applicable, not_uploadable = [], []
    for entry in order_stages:
        order = orders_by_id[entry['order_id']]
        present = order_stage_keys(order)
        for stage in entry['stages']:
            fail = {'order_id': order.id, 'order_number': order.order_number,
                    'payment_stage': stage}
            if stage not in present:
                not_applicable.append(fail)
            elif not getattr(order, _CAN_UPLOAD[stage]):
                not_uploadable.append(fail)
    if not_applicable:
        return False, {'code': 'stage_not_applicable', 'failures': not_applicable}
    if not_uploadable:
        return False, {'code': 'stage_not_uploadable', 'failures': not_uploadable}
    return True, None


def record_bulk_payment_proofs(user, order_stages, saved_filename, payment_method_id):
    """Pętla record + commit + OCR + notify (przeniesione 1:1 z webowej trasy l. 341-481).

    Zakłada wcześniejszą walidację (validate_bulk_upload); approved → defensywny skip (P2).
    Jeden saved_filename współdzielony przez wszystkie wiersze. Zwraca listę utworzonych/
    nadpisanych wpisów: [{'confirmation': pc, 'order': order, 'stage': str, 'action': str}].
    """
    now = get_local_now()
    all_ids = [e['order_id'] for e in order_stages]
    orders_by_id = {o.id: o for o in Order.query.filter(
        Order.id.in_(all_ids), Order.user_id == user.id).all()}
    entries = []
    for entry in order_stages:
        order = orders_by_id.get(entry['order_id'])
        if not order:
            continue
        for stage in entry['stages']:
            amount = stage_amount(order, stage)
            existing = PaymentConfirmation.query.filter_by(
                order_id=order.id, payment_stage=stage).first()
            if existing and existing.is_approved:
                continue                                     # parytet: defensywny skip (P2)
            if existing:
                existing.proof_file = saved_filename
                existing.uploaded_at = now
                existing.status = 'pending'
                existing.rejection_reason = None
                existing.amount = amount
                existing.payment_method_id = payment_method_id
                pc, action = existing, 'payment_confirmation_reuploaded'
            else:
                pc = PaymentConfirmation(order_id=order.id, payment_stage=stage, amount=amount,
                                         proof_file=saved_filename, uploaded_at=now,
                                         status='pending', payment_method_id=payment_method_id)
                db.session.add(pc)
                action = 'payment_confirmation_uploaded'
            log_activity(user=user, action=action, entity_type='order', entity_id=order.id,
                         new_value={'order_number': order.order_number, 'payment_stage': stage,
                                    'filename': saved_filename, 'amount': float(amount)})
            entries.append({'confirmation': pc, 'order': order, 'stage': stage, 'action': action})
    db.session.commit()
    _submit_ocr(user, entries, saved_filename, payment_method_id)
    _notify_admins(entries)
    return entries


def _submit_ocr(user, entries, saved_filename, payment_method_id):
    """JEDEN task OCR dla całego bulku (parytet l. 421-461; tylko gdy ocr_enabled)."""
    from flask import current_app
    try:
        from modules.auth.models import Settings
        if not Settings.get_value('ocr_enabled', False):
            return
        total = sum((Decimal(str(e['confirmation'].amount)) for e in entries), Decimal('0.00'))
        from extensions import executor
        from utils.ocr_background import process_ocr_verification
        executor.submit(process_ocr_verification, {
            'saved_filename': saved_filename, 'payment_method_id': payment_method_id,
            'user_id': user.id,
            'order_numbers': sorted({e['order'].order_number for e in entries}),
            'total_expected': float(total)})
    except Exception as e:
        current_app.logger.error(f'Error submitting OCR background task: {e}')


def _notify_admins(entries):
    """Notify BATCHOWANE PER ORDER (parytet l. 463-481): 1 email + 1 push per zamówienie."""
    from flask import current_app
    by_order = {}
    for e in entries:
        by_order.setdefault(e['order'].id, {'order': e['order'], 'stages': []})
        by_order[e['order'].id]['stages'].append(e['stage'])
    for group in by_order.values():
        stage_names = ', '.join(_STAGE_NAMES_PL.get(s, s) for s in group['stages'])
        try:
            from utils.email_manager import EmailManager
            from utils.push_manager import PushManager
            EmailManager.notify_admin_payment_uploaded(group['order'], stage_names)
            PushManager.notify_admin_payment_uploaded(group['order'], stage_names)
        except Exception as e:
            current_app.logger.error(f'Błąd powiadomienia admina o płatności: {e}')
