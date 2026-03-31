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
        Also stores a Notification record in the database for the notification center.

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

        # Always store notification in DB for the notification center
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

            # Auto-cleanup: remove notifications older than 30 days for this user
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

        # Check user preference (only affects push delivery, not DB storage)
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

        webpush(
            subscription_info={
                'endpoint': sub.endpoint,
                'keys': {
                    'p256dh': sub.p256dh_key,
                    'auth': sub.auth_key,
                }
            },
            data=payload,
            vapid_private_key=vapid_private_key,
            vapid_claims={'sub': vapid_claims_email or 'mailto:noreply@thunderorders.cloud'}
        )

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
    def notify_payment_reminder(order):
        """Push notification reminding about pending payment."""
        user_id = order.user_id
        if not user_id:
            return

        from flask import url_for
        PushManager._fire_and_forget(
            user_id=user_id,
            title=f'Przypomnienie: {order.order_number}',
            body='Masz oczekującą płatność do potwierdzenia.',
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
