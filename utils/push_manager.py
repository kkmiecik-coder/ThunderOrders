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
    new_exclusive_pages   - new exclusive page available
    cost_added            - new cost added to order
    admin_alerts          - admin: new order, payment uploaded
"""

import json
import threading
from datetime import datetime

from flask import current_app


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
        from modules.notifications.models import PushSubscription, NotificationPreference

        # Check user preference
        if notification_type:
            pref = NotificationPreference.query.filter_by(user_id=user_id).first()
            if pref and not getattr(pref, notification_type, True):
                return False

        subs = PushSubscription.query.filter_by(
            user_id=user_id, is_active=True
        ).all()

        if not subs:
            return False

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

        sent = False
        for sub in subs:
            try:
                PushManager._send_single(sub, payload, vapid_private_key, vapid_claims_email)
                sub.last_used_at = datetime.utcnow()
                sub.failed_count = 0
                sent = True
            except Exception as e:
                PushManager._handle_send_error(sub, e)

        from extensions import db
        db.session.commit()
        return sent

    @staticmethod
    def _send_single(sub, payload, vapid_private_key, vapid_claims_email):
        """Send push to a single subscription via pywebpush."""
        from pywebpush import webpush

        # Detect PEM vs base64url key format
        is_pem = vapid_private_key.strip().startswith('-----')

        kwargs = dict(
            subscription_info={
                'endpoint': sub.endpoint,
                'keys': {
                    'p256dh': sub.p256dh_key,
                    'auth': sub.auth_key,
                }
            },
            data=payload,
            vapid_claims={'sub': vapid_claims_email or 'mailto:noreply@thunderorders.cloud'}
        )

        if is_pem:
            kwargs['vapid_private_key'] = vapid_private_key
        else:
            # base64url encoded raw key - decode to PEM for pywebpush
            import base64
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

            # Pad base64url and decode
            padded = vapid_private_key + '=' * (4 - len(vapid_private_key) % 4)
            raw_bytes = base64.urlsafe_b64decode(padded)
            private_key = ec.derive_private_key(
                int.from_bytes(raw_bytes, 'big'),
                ec.SECP256R1()
            )
            pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
            kwargs['vapid_private_key'] = pem

        webpush(**kwargs)

    @staticmethod
    def _handle_send_error(sub, error):
        """Handle push send errors. Deactivate subscription on 410 or repeated failures."""
        from extensions import db

        error_str = str(error)
        status_code = getattr(error, 'status_code', None) or getattr(getattr(error, 'response', None), 'status_code', None)

        if status_code == 410:
            # Subscription expired
            sub.is_active = False
            current_app.logger.info(f'Push subscription {sub.id} expired (410), deactivated')
        else:
            sub.failed_count += 1
            if sub.failed_count >= 5:
                sub.is_active = False
                current_app.logger.info(f'Push subscription {sub.id} deactivated after {sub.failed_count} failures')
            else:
                current_app.logger.warning(f'Push send error for sub {sub.id}: {error_str}')

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
    # EXCLUSIVE
    # ========================================

    @staticmethod
    def notify_new_exclusive_page(page, user_ids):
        """Push notification about new exclusive page to multiple users."""
        from flask import url_for

        app = current_app._get_current_object()
        page_url = url_for('exclusive.order_page', token=page.token, _external=True)

        def _send_all():
            with app.app_context():
                for uid in user_ids:
                    PushManager.send_to_user(
                        user_id=uid,
                        title='Nowa strona Exclusive!',
                        body=page.name,
                        url=page_url,
                        tag=f'exclusive-page-{page.id}',
                        notification_type='new_exclusive_pages'
                    )

        thread = threading.Thread(target=_send_all)
        thread.daemon = True
        thread.start()

    # ========================================
    # ADMIN NOTIFICATIONS
    # ========================================

    @staticmethod
    def notify_admin_new_order(order, admin_ids=None):
        """Push notification to admins about a new exclusive order."""
        if not admin_ids:
            from modules.auth.models import User
            admins = User.query.filter_by(role='admin').all()
            admin_ids = [a.id for a in admins]

        if not admin_ids:
            return

        from flask import url_for
        app = current_app._get_current_object()
        detail_url = url_for('orders.admin_detail', order_id=order.id, _external=True)

        def _send_all():
            with app.app_context():
                for uid in admin_ids:
                    PushManager.send_to_user(
                        user_id=uid,
                        title=f'Nowe zamówienie: {order.order_number}',
                        body=f'Od: {order.customer_name}',
                        url=detail_url,
                        tag=f'admin-order-{order.id}',
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

        def _send_all():
            with app.app_context():
                for uid in admin_ids:
                    PushManager.send_to_user(
                        user_id=uid,
                        title=f'Nowa płatność: {order.order_number}',
                        body=f'{order.customer_name} - {stage_names}',
                        url=review_url,
                        tag=f'admin-payment-{order.id}',
                        notification_type='admin_alerts'
                    )

        thread = threading.Thread(target=_send_all)
        thread.daemon = True
        thread.start()
