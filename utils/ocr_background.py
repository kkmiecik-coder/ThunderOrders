"""
Background OCR Payment Verification
====================================

Runs OCR verification in a background thread via Flask-Executor.
After processing, updates PaymentConfirmation records and emits WebSocket events.
"""

import os
import time
import json
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# Retry configuration dla transient OCR errors (Tesseract crash, DB deadlock, OOM)
MAX_OCR_RETRIES = 3
# Frazy w komunikacie błędu, które wskazują na trwałe uszkodzenie pliku —
# nie retry-ujemy, bo kolejne próby na tym samym pliku zwrócą ten sam błąd.
PERMANENT_OCR_ERROR_PATTERNS = (
    'truncated',
    'cannot identify image file',
    'no such file',
    'permission denied',
    'unsupported',
)


def _is_permanent_ocr_error(exc):
    """Czy błąd OCR jest trwały (no point in retry)."""
    msg = str(exc).lower()
    return any(p in msg for p in PERMANENT_OCR_ERROR_PATTERNS)


def _verify_with_retry(verify_kwargs):
    """
    Uruchamia verify_payment_proof z retry/backoff dla transient errors.
    Zwraca dict z wynikiem OCR lub None gdy się nie udało.
    """
    from utils.ocr_verifier import verify_payment_proof

    last_error = None
    for attempt in range(1, MAX_OCR_RETRIES + 1):
        try:
            return verify_payment_proof(**verify_kwargs)
        except Exception as e:
            last_error = e
            if _is_permanent_ocr_error(e):
                logger.warning(f"OCR permanent error (no retry): {e}")
                return None
            if attempt < MAX_OCR_RETRIES:
                wait_seconds = 2 ** attempt
                logger.info(
                    f"OCR attempt {attempt}/{MAX_OCR_RETRIES} failed, "
                    f"retrying in {wait_seconds}s: {e}"
                )
                time.sleep(wait_seconds)

    logger.warning(f"OCR failed after {MAX_OCR_RETRIES} attempts: {last_error}")
    return None


def process_ocr_verification(task_data):
    """
    Background OCR verification task. Runs via executor.submit().

    Args:
        task_data: dict with keys:
            - saved_filename: str
            - payment_method_id: int or None
            - user_id: int
            - order_numbers: list[str]
            - total_expected: float
    """
    from app import create_app
    app = create_app()

    with app.app_context():
        _process_ocr_internal(task_data)


def _process_ocr_internal(task_data):
    """Internal OCR processing within app context."""
    from extensions import db
    from modules.orders.models import PaymentConfirmation, get_local_now
    from modules.payments.models import PaymentMethod
    from modules.auth.models import Settings
    from utils.ocr_verifier import TESSERACT_AVAILABLE

    saved_filename = task_data['saved_filename']
    payment_method_id = task_data.get('payment_method_id')
    user_id = task_data['user_id']
    order_numbers = task_data.get('order_numbers', [])
    total_expected = Decimal(str(task_data.get('total_expected', 0)))

    if not TESSERACT_AVAILABLE:
        logger.warning("Tesseract not available — skipping background OCR")
        return

    # Ścieżka do pliku
    upload_folder = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'uploads', 'payment_confirmations'
    )
    proof_filepath = os.path.join(upload_folder, saved_filename)

    if not os.path.exists(proof_filepath):
        logger.error(f"OCR background: proof file not found: {proof_filepath}")
        return

    # Pobierz obiekt metody płatności
    pm_obj = None
    if payment_method_id:
        pm_obj = PaymentMethod.query.get(payment_method_id)

    # Pobierz wszystkie aktywne metody (do fallback w score_recipient)
    all_methods = PaymentMethod.get_active()

    # Uruchom OCR z retry dla transient errors (Tesseract crash, DB deadlock)
    ocr_result = _verify_with_retry({
        'filepath': proof_filepath,
        'expected_amount': total_expected,
        'order_numbers': order_numbers,
        'payment_method': pm_obj,
        'all_payment_methods': all_methods,
    })

    if ocr_result is None:
        # Wszystkie retry wyczerpane lub permanent error — moderator zweryfikuje ręcznie
        return

    ocr_score = ocr_result.get('score')
    ocr_details_json = json.dumps(ocr_result.get('details', {}), ensure_ascii=False)

    # Pobierz potwierdzenia do zaktualizowania
    confirmations = PaymentConfirmation.query.filter_by(
        proof_file=saved_filename
    ).all()

    if not confirmations:
        logger.warning(f"OCR background: no confirmations found for {saved_filename}")
        return

    auto_threshold = Settings.get_value('ocr_auto_approve_threshold', 90)
    now = get_local_now()
    auto_approved_confs = []

    for conf in confirmations:
        conf.ocr_score = ocr_score
        conf.ocr_details = ocr_details_json

        # Auto-approve jeśli score >= próg
        if ocr_score is not None and ocr_score >= auto_threshold and conf.status == 'pending':
            conf.status = 'approved'
            conf.auto_approved = True
            conf.updated_at = now

            # Zaktualizuj paid_amount
            order = conf.order
            current_paid = Decimal(str(order.paid_amount)) if order.paid_amount else Decimal('0.00')
            order.paid_amount = current_paid + Decimal(str(conf.amount))

            auto_approved_confs.append(conf)

    db.session.commit()

    logger.info(f"OCR background: {saved_filename} scored {ocr_score}%, "
                f"{len(auto_approved_confs)} auto-approved")

    # Powiadomienia i WebSocket po commit
    _send_notifications(auto_approved_confs, user_id)


def _send_notifications(auto_approved_confs, user_id):
    """Send email/push notifications for auto-approved confirmations."""
    if not auto_approved_confs:
        return

    try:
        from utils.email_manager import EmailManager
        from utils.push_manager import PushManager
        from utils.activity_logger import log_activity
        from modules.auth.models import User

        user = User.query.get(user_id)

        for conf in auto_approved_confs:
            EmailManager.notify_payment_approved(conf.order, conf)
            PushManager.notify_payment_approved(conf.order, conf)

            if user:
                log_activity(
                    user=user,
                    action='payment_confirmation_auto_approved',
                    entity_type='order',
                    entity_id=conf.order_id,
                    new_value={
                        'order_number': conf.order.order_number,
                        'amount': float(conf.amount),
                        'payment_stage': conf.payment_stage,
                        'ocr_score': conf.ocr_score,
                        'auto': True
                    }
                )

            # Auto-transition SR
            if conf.payment_stage == 'domestic_shipping':
                from modules.admin.payment_confirmations import _check_sr_auto_oplacone
                _check_sr_auto_oplacone(conf.order)

    except Exception as e:
        logger.error(f"OCR background notification error: {e}")


