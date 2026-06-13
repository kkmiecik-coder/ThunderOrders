"""
Push Manager - Centralized Push Notification Dispatcher for ThunderOrders
=========================================================================

Follows the same pattern as EmailManager:
- Static methods, lazy imports, graceful error handling
- Each method resolves recipients and checks preferences
- Sends via pywebpush in a background thread

NOTIFICATION TYPES (mapped to NotificationPreference fields):
    order_status_changes  - order status changed
    payment_updates       - payment approved/rejected
    shipping_updates      - shipping request status changed
    new_offer_pages       - new offer page available
    cost_added            - new cost added to order
    admin_alerts          - admin: new order, payment uploaded
"""

import json
import time
import threading
from datetime import datetime

from flask import current_app


# Retry config dla aktualizacji push_subscriptions po webpush.
# Pod obciążeniem (wielu klientów składa zamówienia → wiele wątków pisze do tych samych
# rzędów subskrypcji adminów) MySQL może zwrócić 1205 lock wait timeout.
_SUB_UPDATE_MAX_RETRIES = 3


def _is_lock_timeout(exc):
    """Sprawdza czy wyjątek to MySQL lock wait timeout (errno 1205)."""
    msg = str(exc).lower()
    return '1205' in msg or 'lock wait timeout' in msg


# ============================================================================
# FCM (Firebase Cloud Messaging) HTTP v1 — drugi kanał push (apka mobilna).
# Dołożony ADDYTYWNIE obok Web Push: send_to_user wachluje na wszystkie
# MobileDevice usera. Brak konfiguracji Firebase → kanał wyłączony gracefully
# (jak VAPID gate dla Web Push). google-auth + requests już w requirements.
# ============================================================================
_FCM_SCOPE = 'https://www.googleapis.com/auth/firebase.messaging'
_FCM_ENDPOINT = 'https://fcm.googleapis.com/v1/projects/{project_id}/messages:send'

# Cache OAuth2 Credentials (modułowy) + lock — żeby nie pobierać tokenu per-wysyłka.
_fcm_creds = None
_fcm_creds_lock = threading.Lock()


class PushManager:
    """Centralny dispatcher push notifications dla ThunderOrders."""

    # ========================================
    # CORE SEND METHOD
    # ========================================

    @staticmethod
    def send_to_user(user_id, title, body, url='/', tag='default',
                     notification_type=None):
        """
        Send a push notification to all active subscriptions of a user.
        Also stores a Notification record in the database for the notification center.

        Architektura (Opcja 1 — webpush poza transakcją):
            1. Krótka transakcja: zapis Notification + cleanup starych
            2. Krótka transakcja: pobranie subskrypcji + snapshot do dictów
            3. webpush() w pętli — BEZ otwartej sesji DB
            4. Mikro-transakcja per sub z retry na lock timeout — update last_used_at,
               failed_count, is_active

        Eliminuje 1205 lock wait timeout pod obciążeniem (wiele wątków konkurujących
        o te same wiersze push_subscriptions adminów).

        Args:
            user_id (int): Target user ID
            title (str): Notification title
            body (str): Notification body text
            url (str): URL to open on click
            tag (str): Notification tag (for grouping/replacing)
            notification_type (str|None): Preference field to check. None = skip check.

        Returns:
            bool: True if at least one notification was sent
        """
        from modules.notifications.models import (
            PushSubscription, NotificationPreference, Notification
        )
        from extensions import db as _db

        # === Krok 1: Notification record + cleanup (krótka transakcja) ===
        try:
            notif = Notification(
                user_id=user_id,
                title=title,
                body=body,
                url=url,
                notification_type=notification_type,
                tag=tag,
            )
            _db.session.add(notif)
            _db.session.commit()

            from datetime import datetime, timedelta
            cutoff = datetime.utcnow() - timedelta(days=30)
            Notification.query.filter(
                Notification.user_id == user_id,
                Notification.created_at < cutoff
            ).delete(synchronize_session=False)
            _db.session.commit()
        except Exception as e:
            _db.session.rollback()
            current_app.logger.warning(f'Failed to store notification for user {user_id}: {e}')

        # === Krok 2: Preferencje + snapshot subskrypcji ===
        if notification_type:
            pref = NotificationPreference.query.filter_by(user_id=user_id).first()
            if pref and not getattr(pref, notification_type, True):
                return False

        # === Kanał FCM (apka mobilna) — ADDYTYWNIE, niezależny od Web Push ===
        # Fan-out na urządzenia mobilne PO wspólnym checku preferencji (parytet z Web
        # Push), ale przed blokiem Web Push poniżej — żeby FCM NIE był ucinany przez
        # web-pushowe early-returny (brak aktywnej subskrypcji / brak VAPID). Użytkownik
        # z samą apką mobilną (bez subskrypcji przeglądarkowej) i tak dostanie push.
        # Brak konfiguracji Firebase → no-op. FCM nie może wywrócić Web Pusha ani zapisu
        # notyfikacji → twardy try/except.
        try:
            PushManager._send_fcm_to_user(user_id, title, body, url, tag)
        except Exception as e:
            current_app.logger.warning(f'FCM fan-out failed for user {user_id}: {e}')

        subs = PushSubscription.query.filter_by(
            user_id=user_id, is_active=True
        ).all()

        if not subs:
            return False

        # Odetnij od ORM — webpush nie potrzebuje sesji DB
        sub_snapshots = [
            {
                'id': s.id,
                'endpoint': s.endpoint,
                'p256dh': s.p256dh_key,
                'auth': s.auth_key,
            }
            for s in subs
        ]

        # Zwolnij transakcję czytania zanim zaczną się wolne calle webpush
        _db.session.commit()

        payload = json.dumps({
            'title': title,
            'body': body,
            'url': url,
            'tag': tag,
        })

        vapid_private_key = current_app.config.get('VAPID_PRIVATE_KEY')
        vapid_claims_email = current_app.config.get('VAPID_CLAIMS_EMAIL')

        if not vapid_private_key:
            current_app.logger.warning('VAPID_PRIVATE_KEY not configured, skipping push')
            return False

        # === Krok 3: webpush poza sesją DB ===
        results = []  # [(sub_id, error_or_None)]
        for snap in sub_snapshots:
            try:
                PushManager._send_single_raw(
                    snap['endpoint'], snap['p256dh'], snap['auth'],
                    payload, vapid_private_key, vapid_claims_email
                )
                results.append((snap['id'], None))
            except Exception as e:
                results.append((snap['id'], e))

        # === Krok 4: mikro-transakcje z retry ===
        sent = False
        for sub_id, error in results:
            if error is None:
                PushManager._update_sub_success(sub_id)
                sent = True
            else:
                PushManager._handle_send_error_by_id(sub_id, error)

        return sent

    @staticmethod
    def _send_single_raw(endpoint, p256dh, auth, payload, vapid_private_key, vapid_claims_email):
        """Wysyła pojedynczy push przez pywebpush — bez referencji do ORM."""
        from pywebpush import webpush

        webpush(
            subscription_info={
                'endpoint': endpoint,
                'keys': {
                    'p256dh': p256dh,
                    'auth': auth,
                }
            },
            data=payload,
            vapid_private_key=vapid_private_key,
            vapid_claims={'sub': vapid_claims_email or 'mailto:noreply@thunderorders.cloud'}
        )

    @staticmethod
    def _update_sub_success(sub_id):
        """Po udanej wysyłce: last_used_at=now(), failed_count=0.
        Mikro-transakcja z retry przy 1205 lock wait timeout."""
        from extensions import db
        from modules.notifications.models import PushSubscription

        for attempt in range(1, _SUB_UPDATE_MAX_RETRIES + 1):
            try:
                sub = db.session.get(PushSubscription, sub_id)
                if not sub:
                    return
                sub.last_used_at = datetime.utcnow()
                sub.failed_count = 0
                db.session.commit()
                return
            except Exception as e:
                db.session.rollback()
                if _is_lock_timeout(e) and attempt < _SUB_UPDATE_MAX_RETRIES:
                    time.sleep(0.1 * attempt)
                    continue
                current_app.logger.warning(
                    f'Failed to update push_subscription {sub_id} success: {e}'
                )
                return

    @staticmethod
    def _handle_send_error_by_id(sub_id, error):
        """Po błędzie webpush: deaktywuj na 410, inkrementuj failed_count na resztę.
        Mikro-transakcja per sub z retry przy lock timeout. Świeży SELECT zapewnia
        dedup gdy inny wątek już deaktywował sub."""
        from extensions import db
        from modules.notifications.models import PushSubscription

        error_str = str(error)
        status_code = (
            getattr(error, 'status_code', None)
            or getattr(getattr(error, 'response', None), 'status_code', None)
        )

        for attempt in range(1, _SUB_UPDATE_MAX_RETRIES + 1):
            try:
                sub = db.session.get(PushSubscription, sub_id)
                if not sub or not sub.is_active:
                    # Inny wątek już deaktywował lub sub usunięty
                    return

                if status_code == 410:
                    sub.is_active = False
                    db.session.commit()
                    current_app.logger.info(
                        f'Push subscription {sub_id} expired (410), deactivated'
                    )
                else:
                    sub.failed_count += 1
                    if sub.failed_count >= 5:
                        sub.is_active = False
                        db.session.commit()
                        current_app.logger.info(
                            f'Push subscription {sub_id} deactivated after '
                            f'{sub.failed_count} failures'
                        )
                    else:
                        db.session.commit()
                        current_app.logger.warning(
                            f'Push send error for sub {sub_id}: {error_str}'
                        )
                return
            except Exception as e:
                db.session.rollback()
                if _is_lock_timeout(e) and attempt < _SUB_UPDATE_MAX_RETRIES:
                    time.sleep(0.1 * attempt)
                    continue
                current_app.logger.warning(
                    f'Failed to update push_subscription {sub_id} after error: {e}'
                )
                return

    @staticmethod
    def _send_async(app, user_id, title, body, url, tag, notification_type):
        """Send push in a background thread (like EmailManager async pattern)."""
        with app.app_context():
            PushManager.send_to_user(user_id, title, body, url, tag, notification_type)

    @staticmethod
    def _fire_and_forget(user_id, title, body, url='/', tag='default', notification_type=None):
        """Non-blocking push send using a background thread."""
        app = current_app._get_current_object()
        thread = threading.Thread(
            target=PushManager._send_async,
            args=(app, user_id, title, body, url, tag, notification_type)
        )
        thread.daemon = True
        thread.start()

    # ========================================
    # FCM (Firebase Cloud Messaging) HTTP v1
    # ========================================

    @staticmethod
    def _fcm_enabled():
        """FCM aktywny gdy jest project_id ORAZ źródło credentials (path|json)."""
        cfg = current_app.config
        has_project = bool(cfg.get('FIREBASE_PROJECT_ID'))
        has_creds = bool(cfg.get('FIREBASE_CREDENTIALS_PATH') or
                         cfg.get('FIREBASE_CREDENTIALS_JSON'))
        return has_project and has_creds

    @staticmethod
    def _get_fcm_project_id():
        """project_id z configu (override) lub z service-account JSON."""
        cfg = current_app.config
        pid = cfg.get('FIREBASE_PROJECT_ID') or ''
        if pid:
            return pid
        raw = cfg.get('FIREBASE_CREDENTIALS_JSON') or ''
        path = cfg.get('FIREBASE_CREDENTIALS_PATH') or ''
        try:
            if raw:
                return (json.loads(raw) or {}).get('project_id') or ''
            if path:
                with open(path, 'r', encoding='utf-8') as f:
                    return (json.load(f) or {}).get('project_id') or ''
        except Exception as e:
            current_app.logger.warning(f'FCM: nie udało się odczytać project_id: {e}')
        return ''

    @staticmethod
    def _get_fcm_access_token():
        """Zwraca OAuth2 access token dla FCM. Cache modułowy Credentials + lock;
        refresh tylko gdy token wygasł (google-auth pilnuje ważności). None = brak creds."""
        global _fcm_creds
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as _GoogleAuthRequest

        cfg = current_app.config
        with _fcm_creds_lock:
            if _fcm_creds is None:
                path = cfg.get('FIREBASE_CREDENTIALS_PATH') or ''
                raw = cfg.get('FIREBASE_CREDENTIALS_JSON') or ''
                if path:
                    _fcm_creds = service_account.Credentials.from_service_account_file(
                        path, scopes=[_FCM_SCOPE])
                elif raw:
                    _fcm_creds = service_account.Credentials.from_service_account_info(
                        json.loads(raw), scopes=[_FCM_SCOPE])
                else:
                    return None
            if not _fcm_creds.valid:
                _fcm_creds.refresh(_GoogleAuthRequest())
            return _fcm_creds.token

    @staticmethod
    def _build_fcm_message(token, title, body, url, tag):
        """Buduje payload FCM HTTP v1 (parytet z Web Push: niesie url/tag do nawigacji;
        tag mapowany na android.notification.tag / apns thread-id — kolapsowanie)."""
        tag = tag or 'default'
        return {
            'token': token,
            'notification': {'title': title, 'body': body},
            'data': {'url': url or '/', 'tag': tag},
            'android': {'notification': {'tag': tag}},
            'apns': {'payload': {'aps': {'thread-id': tag}}},
        }

    @staticmethod
    def _send_fcm_raw(token, message, access_token, project_id):
        """Wysyła pojedynczy push przez FCM HTTP v1 — bez referencji do ORM.
        Zwraca obiekt odpowiedzi requests (status_code/json do mapowania D8)."""
        import requests

        return requests.post(
            _FCM_ENDPOINT.format(project_id=project_id),
            json={'message': message},
            headers={'Authorization': f'Bearer {access_token}',
                     'Content-Type': 'application/json'},
            timeout=10,
        )

    @staticmethod
    def _classify_fcm_response(resp):
        """Mapuje odpowiedź FCM na akcję (D8): 'success' | 'delete' | 'keep'.
        - 200 → success (last_used_at=now)
        - 404 / UNREGISTERED / NOT_FOUND, 400 INVALID_ARGUMENT → delete (token nieaktualny)
        - 401/403 (nasz misconfig/auth) → keep (NIE usuwaj tokenów)
        - 429/5xx/inne (transient) → keep
        """
        status = getattr(resp, 'status_code', None)
        if status == 200:
            return 'success'

        err_code = ''
        try:
            data = resp.json()
            err = data.get('error', {}) if isinstance(data, dict) else {}
            err_code = (err.get('status') or '').upper()
            for detail in (err.get('details') or []):
                code = (detail.get('errorCode') or '').upper()
                if code:
                    err_code = code
                    break
        except Exception:
            pass

        # Kasujemy token TYLKO przy jednoznacznym sygnale „token martwy" (UNREGISTERED/NOT_FOUND).
        # NIE kasujemy na generyczne 400 INVALID_ARGUMENT — FCM zwraca je też dla źle zbudowanego
        # PAYLOADU, więc regresja schematu wybiłaby tokeny WSZYSTKICH userów (apka i tak
        # re-rejestruje token przy starcie, więc martwy token jest nieszkodliwy).
        if status == 404 or 'UNREGISTERED' in err_code or err_code == 'NOT_FOUND':
            return 'delete'
        if status == 400:
            current_app.logger.warning(
                f'FCM 400 (code={err_code}) — możliwy zły payload; NIE usuwam tokenów')
            return 'keep'
        if status in (401, 403):
            current_app.logger.warning(
                f'FCM auth/config error (status={status}); nie usuwam tokenów')
            return 'keep'
        current_app.logger.warning(
            f'FCM transient/unknown response (status={status}, code={err_code})')
        return 'keep'

    @staticmethod
    def _send_fcm_to_user(user_id, title, body, url, tag):
        """Fan-out FCM na wszystkie urządzenia mobilne usera. Brak konfiguracji
        Firebase / brak urządzeń → no-op. Snapshot tokenów poza sesją (jak Web Push),
        wysyłka w pętli, sprzątanie wg D8 (mikro-transakcje per urządzenie)."""
        if not PushManager._fcm_enabled():
            return

        from modules.api_mobile.models import MobileDevice
        from extensions import db as _db

        project_id = PushManager._get_fcm_project_id()
        if not project_id:
            current_app.logger.warning('FCM: brak project_id — pomijam fan-out')
            return

        access_token = PushManager._get_fcm_access_token()
        if not access_token:
            current_app.logger.warning('FCM: brak access tokenu — pomijam fan-out')
            return

        devices = MobileDevice.query.filter_by(user_id=user_id).all()
        if not devices:
            return

        # Odetnij od ORM — wysyłka HTTP nie potrzebuje sesji DB
        device_snapshots = [{'id': d.id, 'token': d.fcm_token} for d in devices]
        _db.session.commit()

        for snap in device_snapshots:
            try:
                message = PushManager._build_fcm_message(
                    snap['token'], title, body, url, tag)
                resp = PushManager._send_fcm_raw(
                    snap['token'], message, access_token, project_id)
            except Exception as e:
                current_app.logger.warning(
                    f'FCM send error for device {snap["id"]}: {e}')
                continue

            action = PushManager._classify_fcm_response(resp)
            if action == 'delete':
                PushManager._delete_stale_device(snap['id'])
            elif action == 'success':
                PushManager._update_device_success(snap['id'])

    @staticmethod
    def _update_device_success(device_id):
        """Po udanej wysyłce FCM: last_used_at=now(). Mikro-transakcja z retry
        przy 1205 lock wait timeout (parytet z Web Push)."""
        from extensions import db
        from modules.api_mobile.models import MobileDevice

        for attempt in range(1, _SUB_UPDATE_MAX_RETRIES + 1):
            try:
                dev = db.session.get(MobileDevice, device_id)
                if not dev:
                    return
                dev.last_used_at = datetime.utcnow()
                db.session.commit()
                return
            except Exception as e:
                db.session.rollback()
                if _is_lock_timeout(e) and attempt < _SUB_UPDATE_MAX_RETRIES:
                    time.sleep(0.1 * attempt)
                    continue
                current_app.logger.warning(
                    f'Failed to update mobile_device {device_id} success: {e}')
                return

    @staticmethod
    def _delete_stale_device(device_id):
        """Nieaktualny token FCM (404/UNREGISTERED/invalid) → hard-delete wiersza.
        Mikro-transakcja z retry przy lock timeout."""
        from extensions import db
        from modules.api_mobile.models import MobileDevice

        for attempt in range(1, _SUB_UPDATE_MAX_RETRIES + 1):
            try:
                dev = db.session.get(MobileDevice, device_id)
                if not dev:
                    return
                db.session.delete(dev)
                db.session.commit()
                current_app.logger.info(
                    f'FCM: usunięto nieaktualny token urządzenia {device_id}')
                return
            except Exception as e:
                db.session.rollback()
                if _is_lock_timeout(e) and attempt < _SUB_UPDATE_MAX_RETRIES:
                    time.sleep(0.1 * attempt)
                    continue
                current_app.logger.warning(
                    f'Failed to delete stale mobile_device {device_id}: {e}')
                return

    # ========================================
    # ORDER STATUS
    # ========================================

    @staticmethod
    def notify_status_change(order, old_status, new_status):
        """Push notification for order status change."""
        user_id = order.user_id
        if not user_id:
            return

        from flask import url_for
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Zmiana statusu: {order.order_number}',
            body=f'{old_status} \u2192 {new_status}',
            url=url_for('orders.client_detail', order_id=order.id, _external=True),
            tag=f'order-status-{order.id}',
            notification_type='order_status_changes'
        )

    @staticmethod
    def notify_supplier_ordered(order):
        """Push: zam\u00f3wienie zosta\u0142o zam\u00f3wione u dostawcy."""
        user_id = order.user_id
        if not user_id:
            return

        from flask import url_for
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Zam\u00f3wiono u dostawcy: {order.order_number}',
            body='Tw\u00f3j produkt zosta\u0142 zam\u00f3wiony u dostawcy.',
            url=url_for('orders.client_detail', order_id=order.id, _external=True),
            tag=f'order-supplier-{order.id}',
            notification_type='order_supplier_ordered'
        )

    @staticmethod
    def notify_supplier_cancelled(order):
        """Push: zam\u00f3wienie u dostawcy zosta\u0142o anulowane."""
        user_id = order.user_id
        if not user_id:
            return

        from flask import url_for
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Anulowano u dostawcy: {order.order_number}',
            body='Zam\u00f3wienie u dostawcy zosta\u0142o anulowane \u2014 zostanie ponownie zam\u00f3wione.',
            url=url_for('orders.client_detail', order_id=order.id, _external=True),
            tag=f'order-supplier-{order.id}',
            notification_type='order_supplier_ordered'
        )

    # ========================================
    # PAYMENTS
    # ========================================

    @staticmethod
    def notify_payment_approved(order, confirmation):
        """Push notification for payment approval."""
        user_id = order.user_id
        if not user_id:
            return

        stage_name = confirmation.stage_display_name
        from flask import url_for
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Płatność zatwierdzona: {order.order_number}',
            body=f'{stage_name} - {float(confirmation.amount):.2f} PLN',
            url=url_for('orders.client_detail', order_id=order.id, _external=True),
            tag=f'payment-{order.id}',
            notification_type='payment_updates'
        )

    @staticmethod
    def notify_payment_rejected(order, confirmation, reason):
        """Push notification for payment rejection."""
        user_id = order.user_id
        if not user_id:
            return

        stage_name = confirmation.stage_display_name
        from flask import url_for
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Płatność odrzucona: {order.order_number}',
            body=f'{stage_name} - {reason}' if reason else stage_name,
            url=url_for('orders.client_detail', order_id=order.id, _external=True),
            tag=f'payment-{order.id}',
            notification_type='payment_updates'
        )

    @staticmethod
    def notify_payment_bulk_approved(user_id, confirmations):
        """Skonsolidowany push dla bulk-approve jednego użytkownika.

        Args:
            user_id (int): ID użytkownika-odbiorcy.
            confirmations (list[PaymentConfirmation]): lista potwierdzeń tego usera
                (muszą mieć już załadowane `order`).

        Jeśli lista ma 1 element - wysyła standardowego pojedynczego pusha
        (tak jak `notify_payment_approved`). Przy >1 wysyła zbiorczego.
        """
        if not user_id or not confirmations:
            return

        from flask import url_for
        import time

        if len(confirmations) == 1:
            # Zachowaj dotychczasowy format dla pojedynczego potwierdzenia
            PushManager.notify_payment_approved(confirmations[0].order, confirmations[0])
            return

        order_numbers = [c.order.order_number for c in confirmations if c.order]
        count = len(confirmations)

        # URL: lista potwierdzeń klienta
        url = url_for('client.payment_confirmations', _external=True)

        # Tag z timestampem - nie nadpisuje poprzednich bulk pushy
        tag = f'payment-bulk-{int(time.time() * 1000)}'

        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Zatwierdzono {count} potwierdzeń',
            body=', '.join(order_numbers),
            url=url,
            tag=tag,
            notification_type='payment_updates'
        )

    @staticmethod
    def notify_payment_bulk_rejected(user_id, confirmations, reason):
        """Skonsolidowany push dla bulk-reject jednego użytkownika.

        Args:
            user_id (int): ID użytkownika-odbiorcy.
            confirmations (list[PaymentConfirmation]): lista potwierdzeń tego usera.
            reason (str): powód odrzucenia (wspólny dla całego bulk).

        Jeśli lista ma 1 element - wysyła standardowego pojedynczego pusha.
        """
        if not user_id or not confirmations:
            return

        from flask import url_for
        import time

        if len(confirmations) == 1:
            PushManager.notify_payment_rejected(confirmations[0].order, confirmations[0], reason)
            return

        order_numbers = [c.order.order_number for c in confirmations if c.order]
        count = len(confirmations)

        url = url_for('client.payment_confirmations', _external=True)
        tag = f'payment-bulk-{int(time.time() * 1000)}'

        body_orders = ', '.join(order_numbers)
        body = f'{body_orders} - {reason}' if reason else body_orders

        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Odrzucono {count} potwierdzeń',
            body=body,
            url=url,
            tag=tag,
            notification_type='payment_updates'
        )

    # ========================================
    # COSTS
    # ========================================

    @staticmethod
    def notify_cost_added(order, cost_type, cost_amount):
        """Push notification when a new cost is added to an order."""
        user_id = order.user_id
        if not user_id:
            return

        cost_labels = {
            'proxy_shipping': 'Koszt wysyłki z Korei',
            'customs_vat': 'Cło i VAT',
            'domestic_shipping': 'Koszt wysyłki krajowej',
        }
        label = cost_labels.get(cost_type, 'Nowy koszt')

        from flask import url_for
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Nowy koszt: {order.order_number}',
            body=f'{label}: {cost_amount:.2f} PLN',
            url=url_for('orders.client_detail', order_id=order.id, _external=True),
            tag=f'cost-{order.id}',
            notification_type='cost_added'
        )

    # ========================================
    # SHIPPING
    # ========================================

    @staticmethod
    def notify_shipping_status_change(shipping_request, new_status_name):
        """Push notification for shipping request status change."""
        user = shipping_request.user
        if not user:
            return

        from flask import url_for
        PushManager._fire_and_forget(
            user_id=user.id,
            title=f'Wysyłka: {shipping_request.request_number}',
            body=f'Nowy status: {new_status_name}',
            url=url_for('client.shipping_requests_list', _external=True),
            tag=f'shipping-{shipping_request.id}',
            notification_type='shipping_updates'
        )

    # ========================================
    # ORDER CONFIRMATION
    # ========================================

    @staticmethod
    def notify_order_confirmation(order):
        """Push notification confirming a new order was placed."""
        user_id = order.user_id
        if not user_id:
            return

        from flask import url_for
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Zamówienie złożone: {order.order_number}',
            body=f'Kwota: {float(order.total_amount):.2f} PLN',
            url=url_for('orders.client_detail', order_id=order.id, _external=True),
            tag=f'order-confirm-{order.id}',
            notification_type='order_status_changes'
        )

    @staticmethod
    def notify_admin_created_order(order):
        """Push notification: admin created an order on behalf of the customer."""
        user_id = order.user_id
        if not user_id:
            return

        from flask import url_for
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Admin złożył zamówienie: {order.order_number}',
            body=f'Kwota: {float(order.total_amount):.2f} PLN. Sprawdź szczegóły i opłać.',
            url=url_for('orders.client_detail', order_id=order.id, _external=True),
            tag=f'order-admin-created-{order.id}',
            notification_type='order_status_changes'
        )

    # ========================================
    # TRACKING
    # ========================================

    @staticmethod
    def notify_tracking_added(order, tracking_number, courier_name='Kurier'):
        """Push notification when tracking number is added."""
        user_id = order.user_id
        if not user_id:
            return

        from flask import url_for
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Tracking: {order.order_number}',
            body=f'{courier_name}: {tracking_number}',
            url=url_for('orders.client_detail', order_id=order.id, _external=True),
            tag=f'tracking-{order.id}',
            notification_type='shipping_updates'
        )

    # ========================================
    # CANCELLATION
    # ========================================

    @staticmethod
    def notify_order_cancelled(order, reason=None):
        """Push notification when an order is cancelled."""
        user_id = order.user_id
        if not user_id:
            return

        from flask import url_for
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Zamówienie anulowane: {order.order_number}',
            body=reason or 'Zamówienie zostało anulowane',
            url=url_for('orders.client_detail', order_id=order.id, _external=True),
            tag=f'order-cancelled-{order.id}',
            notification_type='order_status_changes'
        )

    # ========================================
    # OFFER CLOSURE
    # ========================================

    @staticmethod
    def notify_offer_closure(order, grand_total=None):
        """Push notification about offer page closure settlement."""
        user_id = order.user_id
        if not user_id:
            return

        from flask import url_for
        body = f'Kwota do zapłaty: {grand_total:.2f} PLN' if grand_total else 'Sprawdź szczegóły rozliczenia'
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Rozliczenie: {order.order_number}',
            body=body,
            url=url_for('orders.client_detail', order_id=order.id, _external=True),
            tag=f'closure-{order.id}',
            notification_type='order_status_changes'
        )

    # ========================================
    # PACKING PHOTO
    # ========================================

    @staticmethod
    def notify_packing_photo(order):
        """Push notification when packing photo is available."""
        user_id = order.user_id
        if not user_id:
            return

        from flask import url_for
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Zdjęcie paczki: {order.order_number}',
            body='Twoja paczka została zapakowana! Zobacz zdjęcie.',
            url=url_for('orders.client_detail', order_id=order.id, _external=True),
            tag=f'packing-{order.id}',
            notification_type='shipping_updates'
        )

    # ========================================
    # PAYMENT REMINDER
    # ========================================

    @staticmethod
    def notify_payment_reminder(order, payment_deadline=None):
        """Push notification reminding about pending payment."""
        user_id = order.user_id
        if not user_id:
            return

        from flask import url_for

        if payment_deadline:
            deadline_str = payment_deadline.strftime('%d.%m %H:%M')
            body = f'Termin płatności upływa {deadline_str}. Prześlij potwierdzenie.'
        else:
            body = 'Masz oczekującą płatność do potwierdzenia.'

        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Przypomnienie: {order.order_number}',
            body=body,
            url=url_for('client.payment_confirmations', _external=True),
            tag=f'reminder-{order.id}',
            notification_type='payment_updates'
        )

    # ========================================
    # ADMIN: SHIPPING REQUEST
    # ========================================

    @staticmethod
    def notify_admin_shipping_request(shipping_request, admin_ids=None):
        """Push notification to admins about new shipping request."""
        if not admin_ids:
            from modules.auth.models import User
            admins = User.query.filter_by(role='admin').all()
            admin_ids = [a.id for a in admins]

        if not admin_ids:
            return

        from flask import url_for
        app = current_app._get_current_object()
        url = url_for('orders.admin_shipping_requests_list', _external=True)
        request_number = shipping_request.request_number
        user_name = shipping_request.user.full_name if shipping_request.user else "Klient"
        request_id = shipping_request.id

        def _send_all():
            with app.app_context():
                for uid in admin_ids:
                    PushManager.send_to_user(
                        user_id=uid,
                        title=f'Nowe zlecenie wysyłki: {request_number}',
                        body=f'Od: {user_name}',
                        url=url,
                        tag=f'admin-shipping-{request_id}',
                        notification_type='admin_alerts'
                    )

        thread = threading.Thread(target=_send_all)
        thread.daemon = True
        thread.start()

    # ========================================
    # OFFER PAGES
    # ========================================

    @staticmethod
    def notify_new_offer_page(page, user_ids):
        """Push notification about new offer page to multiple users."""
        from flask import url_for

        app = current_app._get_current_object()
        page_url = url_for('offers.order_page', token=page.token, _external=True)
        page_name = page.name
        page_id = page.id

        def _send_all():
            with app.app_context():
                for uid in user_ids:
                    PushManager.send_to_user(
                        user_id=uid,
                        title='Nowa strona sprzedaży!',
                        body=page_name,
                        url=page_url,
                        tag=f'offer-page-{page_id}',
                        notification_type='new_offer_pages'
                    )

        thread = threading.Thread(target=_send_all)
        thread.daemon = True
        thread.start()

    @staticmethod
    def notify_back_in_stock(user_id, product_name, page_name, page_url, product_id=None):
        """Push: subskrybowany produkt znów dostępny na stronie oferty („produkt wrócił").

        Kanał OBOK e-maila back-in-stock (gałąź e-mail-fallback w
        `modules/offers/socket_events.py`) — leci na Web Push + FCM przez wspólny
        `send_to_user`/`_fire_and_forget` (jak pozostałe `notify_*`).

        `notification_type=None`: subskrypcja `OfferProductNotificationSubscription`
        jest JAWNYM, per-produktowym opt-inem, więc nie bramkujemy pusha generyczną
        preferencją — parytet z e-mailem, który również wysyła bezwarunkowo do
        subskrybenta. Rekord `Notification` i tak powstaje (centrum powiadomień).
        Tag per-produkt → powroty różnych produktów nie nadpisują się wzajemnie.
        """
        if not user_id:
            return

        tag = f'back-in-stock-{product_id}' if product_id else 'back-in-stock'
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'{product_name} znów dostępny!',
            body=f'Produkt wrócił do oferty: {page_name}',
            url=page_url or '/',
            tag=tag,
            notification_type=None,
        )

    # ========================================
    # ADMIN NOTIFICATIONS
    # ========================================

    @staticmethod
    def notify_admin_new_order(order, admin_ids=None):
        """Push notification to admins about a new order."""
        if not admin_ids:
            from modules.auth.models import User
            admins = User.query.filter_by(role='admin').all()
            admin_ids = [a.id for a in admins]

        if not admin_ids:
            return

        from flask import url_for
        app = current_app._get_current_object()
        detail_url = url_for('orders.admin_detail', order_id=order.id, _external=True)
        order_number = order.order_number
        customer_name = order.customer_name
        order_id = order.id

        def _send_all():
            with app.app_context():
                for uid in admin_ids:
                    PushManager.send_to_user(
                        user_id=uid,
                        title=f'Nowe zamówienie: {order_number}',
                        body=f'Od: {customer_name}',
                        url=detail_url,
                        tag=f'admin-order-{order_id}',
                        notification_type='admin_alerts'
                    )

        thread = threading.Thread(target=_send_all)
        thread.daemon = True
        thread.start()

    @staticmethod
    def notify_admin_payment_uploaded(order, stage_names, admin_ids=None):
        """Push notification to admins about new payment upload."""
        if not admin_ids:
            from modules.auth.models import User
            admins = User.query.filter_by(role='admin').all()
            admin_ids = [a.id for a in admins]

        if not admin_ids:
            return

        from flask import url_for
        app = current_app._get_current_object()
        review_url = url_for('admin.payment_confirmations_list', _external=True)
        order_number = order.order_number
        customer_name = order.customer_name
        order_id = order.id

        def _send_all():
            with app.app_context():
                for uid in admin_ids:
                    PushManager.send_to_user(
                        user_id=uid,
                        title=f'Nowa płatność: {order_number}',
                        body=f'{customer_name} - {stage_names}',
                        url=review_url,
                        tag=f'admin-payment-{order_id}',
                        notification_type='admin_alerts'
                    )

        thread = threading.Thread(target=_send_all)
        thread.daemon = True
        thread.start()

    # ========================================
    # SALE DATE CHANGES
    # ========================================

    @staticmethod
    def notify_sale_end_date_changed(page, new_ends_at, user_ids):
        """
        Wysyła push notification o zmianie daty zakończenia sprzedaży.

        Args:
            page: obiekt OfferPage
            new_ends_at: datetime lub None — nowa data
            user_ids: lista ID użytkowników do powiadomienia

        Returns:
            int: liczba użytkowników, do których push został wystrzelony
                 (sukces dostarczenia weryfikuje się asynchronicznie)
        """
        from flask import url_for

        if new_ends_at is None:
            body = 'Sprzedaż przedłużona bez limitu czasowego'
        else:
            body = f'Nowa data zakończenia: {new_ends_at.strftime("%d.%m.%Y, %H:%M")}'

        title = f'{page.name} — zmiana daty zakończenia'

        try:
            url = url_for('offers.order_page', token=page.token, _external=False)
        except Exception:
            url = '/'

        tag = f'sale-date-{page.id}'
        sent = 0

        for user_id in user_ids:
            try:
                PushManager._fire_and_forget(
                    user_id=user_id,
                    title=title,
                    body=body,
                    url=url,
                    tag=tag,
                    notification_type='sale_date_changes',
                )
                sent += 1
            except Exception as e:
                current_app.logger.error(
                    f"Failed to fire sale_date_changes push for user {user_id}: {e}"
                )

        current_app.logger.info(
            f"Sale end date changed push fired for {sent}/{len(user_ids)} users (page={page.id})"
        )
        return sent
