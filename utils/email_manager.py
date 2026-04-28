"""
Email Manager - Centralized Email Dispatcher for ThunderOrders
==============================================================

Centralny punkt zarządzania wszystkimi emailami w aplikacji.
Każda metoda przyjmuje obiekty modeli (Order, User) i sama rozwiązuje
email/nazwę odbiorcy, obsługując zarówno zalogowanych jak i gości.

Wszystkie funkcje bazowe (rendering, wysyłka async) pozostają w utils/email_sender.py.
Ten moduł jest warstwą wyższego poziomu - "co wysłać i do kogo".

REJESTR EMAILI:
    AUTH:
        - send_verification_code(user, code)     -> kod weryfikacyjny 6-cyfrowy
        - send_verification_link(user)            -> link weryfikacyjny (legacy)
        - send_welcome(user)                     -> email powitalny po weryfikacji
        - send_password_reset(user)               -> link resetu hasła

    ZAMÓWIENIA:
        - notify_order_confirmation(order)        -> potwierdzenie złożenia zamówienia
        - notify_status_change(order, old_status, new_status) -> zmiana statusu

    OFFER:
        - notify_offer_closure(order, page, items, ...) -> podsumowanie po zamknięciu
        - notify_order_cancelled(order, page, cancelled_items, reason) -> anulowanie
        - notify_back_in_stock(email, product, page_name, page_url) -> powrót produktu

    PŁATNOŚCI:
        - notify_payment_approved(order, confirmation) -> zatwierdzenie płatności
        - notify_payment_rejected(order, confirmation, reason) -> odrzucenie płatności
        - notify_payment_reminder(order) -> przypomnienie o niezapłaconych etapach

    WYSYŁKA:
        - notify_shipping_request_created(shipping_request, user) -> potwierdzenie zlecenia wysyłki
        - notify_shipping_status_change(shipping_request, old_status_slug) -> zmiana statusu zlecenia wysyłki

    ADMIN:
        - notify_admin_payment_uploaded(order, stage_names) -> nowe potwierdzenie płatności
        - notify_admin_new_order(order) -> nowe zamówienie offer
"""

import time

from flask import current_app, url_for


class EmailManager:
    """Centralny dispatcher emailowy dla ThunderOrders."""

    # Cache for email notification config (shared across requests within a worker)
    _email_config_cache = None
    _email_config_cache_time = 0
    _EMAIL_CONFIG_CACHE_TTL = 60  # seconds

    @classmethod
    def clear_email_config_cache(cls):
        """Clear the email config cache (call after saving settings)."""
        cls._email_config_cache = None
        cls._email_config_cache_time = 0

    @classmethod
    def is_email_enabled(cls, notification_key):
        """
        Check if a specific email notification is enabled.
        Uses cached config with TTL to avoid DB queries on every email.
        Returns True by default if no config exists.
        """
        now = time.time()
        if cls._email_config_cache is None or (now - cls._email_config_cache_time) > cls._EMAIL_CONFIG_CACHE_TTL:
            try:
                from modules.auth.models import Settings
                cls._email_config_cache = Settings.get_value('email_notifications_config', {})
                cls._email_config_cache_time = now
            except Exception:
                return True

        if not cls._email_config_cache or not isinstance(cls._email_config_cache, dict):
            return True

        return cls._email_config_cache.get(notification_key, True)

    @classmethod
    def get_admin_notification_emails(cls):
        """
        Get list of admin notification email addresses from settings.
        Uses admin_notification_recipients config:
        - disabled_admin_ids: list of admin user IDs to exclude
        - extra_emails: comma-separated extra email addresses
        Falls back to all admins from DB if not configured.
        Returns list of email strings.
        """
        from modules.auth.models import User

        # Load recipients config
        recipients_config = {}
        try:
            from modules.auth.models import Settings
            recipients_config = Settings.get_value('admin_notification_recipients', {})
            if not isinstance(recipients_config, dict):
                recipients_config = {}
        except Exception:
            pass

        disabled_ids = set(recipients_config.get('disabled_admin_ids', []))
        extra_emails_str = recipients_config.get('extra_emails', '')

        # Get enabled admins (all admins minus disabled ones)
        admins = User.query.filter_by(role='admin', is_active=True).all()
        emails = [a.email for a in admins if a.email and a.id not in disabled_ids]

        # Add extra emails
        if extra_emails_str and extra_emails_str.strip():
            for e in extra_emails_str.split(','):
                e = e.strip()
                if e and e not in emails:
                    emails.append(e)

        return emails

    # ========================================
    # AUTH EMAILS
    # ========================================

    @staticmethod
    def send_verification_code(user, code):
        """
        Wysyła email z 6-cyfrowym kodem weryfikacyjnym.
        Wysyłka SYNCHRONICZNA - czeka na potwierdzenie SMTP.

        Args:
            user: obiekt User
            code (str): 6-cyfrowy kod weryfikacyjny

        Returns:
            bool: True jeśli email został wysłany, False w przypadku błędu
        """
        from utils.email_sender import send_email_sync

        try:
            result = send_email_sync(
                to=user.email,
                subject='Twój kod weryfikacyjny - ThunderOrders',
                template='verification_code',
                user_name=user.first_name,
                verification_code=code
            )
            if result:
                current_app.logger.info(f"Verification code sent to {user.email}")
            else:
                current_app.logger.error(f"Verification code SMTP failed for {user.email}")
            return result
        except Exception as e:
            current_app.logger.error(f"Failed to send verification code to {user.email}: {e}")
            return False

    @staticmethod
    def send_verification_link(user):
        """
        Wysyła email weryfikacyjny z linkiem (legacy system).

        Args:
            user: obiekt User (musi mieć email_verification_token)
        """
        from utils.email_sender import send_verification_email

        try:
            send_verification_email(
                user_email=user.email,
                verification_token=user.email_verification_token,
                user_name=user.first_name
            )
            current_app.logger.info(f"Verification email sent to {user.email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send verification email to {user.email}: {e}")

    @staticmethod
    def send_welcome(user):
        """
        Wysyła email powitalny po pomyślnej weryfikacji konta.

        Args:
            user: obiekt User
        """
        from utils.email_sender import send_welcome_email

        try:
            send_welcome_email(
                user_email=user.email,
                user_name=user.first_name
            )
            current_app.logger.info(f"Welcome email sent to {user.email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send welcome email to {user.email}: {e}")

    @staticmethod
    def send_password_reset(user):
        """
        Wysyła email z linkiem do resetu hasła.
        Wysyłka SYNCHRONICZNA - czeka na potwierdzenie SMTP.

        Args:
            user: obiekt User (musi mieć password_reset_token)

        Returns:
            bool: True jeśli email został wysłany
        """
        from utils.email_sender import send_email_sync
        from flask import url_for

        try:
            reset_url = url_for('auth.reset_password', token=user.password_reset_token, _external=True)
            result = send_email_sync(
                to=user.email,
                subject='Reset hasła - ThunderOrders',
                template='reset_password',
                user_name=user.first_name,
                reset_url=reset_url
            )
            if result:
                current_app.logger.info(f"Password reset email sent to {user.email}")
            else:
                current_app.logger.error(f"Password reset SMTP failed for {user.email}")
            return result
        except Exception as e:
            current_app.logger.error(f"Failed to send password reset email to {user.email}: {e}")
            return False

    # ========================================
    # ORDER EMAILS
    # ========================================

    @staticmethod
    def notify_order_confirmation(order):
        """
        Wysyła potwierdzenie złożenia zamówienia.
        Automatycznie rozwiązuje email/nazwę klienta (zalogowany lub gość).

        Args:
            order: obiekt Order
        """
        if not EmailManager.is_email_enabled('notify_order_confirmation'):
            current_app.logger.info("Email notification 'notify_order_confirmation' is disabled, skipping")
            return

        from utils.email_sender import send_order_confirmation_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send order confirmation for {order.order_number}: no email")
            return

        try:
            order_items = []
            for item in order.items:
                order_items.append({
                    'product_name': item.product.name,
                    'quantity': item.quantity,
                    'price': float(item.price),
                    'total': float(item.total)
                })

            send_order_confirmation_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                order_total=float(order.total_amount),
                order_items=order_items,
                is_offer=order.offer_page_id is not None,
                payment_stages=order.payment_stages
            )
            current_app.logger.info(f"Order confirmation email sent for {order.order_number} to {email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send order confirmation email for {order.order_number}: {e}")

    @staticmethod
    def notify_packing_photo(order):
        """
        Wysyła email ze zdjęciem spakowanej paczki do klienta.

        Args:
            order: obiekt Order (musi mieć ustawione packing_photo)
        """
        if not EmailManager.is_email_enabled('notify_packing_photo'):
            current_app.logger.info("Email notification 'notify_packing_photo' is disabled, skipping")
            return

        from utils.email_sender import send_packing_photo_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(
                f"Cannot send packing photo email for {order.order_number}: no email"
            )
            return

        if not order.packing_photo:
            current_app.logger.warning(
                f"Cannot send packing photo email for {order.order_number}: no photo"
            )
            return

        try:
            send_packing_photo_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                photo_path=order.packing_photo,
            )
            current_app.logger.info(
                f"Packing photo email sent for {order.order_number} to {email}"
            )
        except Exception as e:
            current_app.logger.error(
                f"Failed to send packing photo email for {order.order_number}: {e}"
            )

    @staticmethod
    def notify_status_change(order, old_status, new_status):
        """
        Wysyła powiadomienie o zmianie statusu zamówienia.
        Jeśli nowy status to 'dostarczone', wysyła specjalny email podsumowujący.
        Automatycznie rozwiązuje email klienta.

        Args:
            order: obiekt Order
            old_status (str): poprzedni status (display name)
            new_status (str): nowy status (display name)
        """
        if not EmailManager.is_email_enabled('notify_status_change'):
            current_app.logger.info("Email notification 'notify_status_change' is disabled, skipping")
            return

        email = order.customer_email
        if not email:
            return

        # Jeśli zamówienie zostało dostarczone - wyślij specjalny email podsumowujący
        if order.status == 'dostarczone':
            try:
                EmailManager.notify_order_completed(order)
                return
            except Exception as e:
                current_app.logger.error(
                    f"Failed to send order completed email for {order.order_number}, "
                    f"falling back to generic status change: {e}"
                )

        # Standardowy email o zmianie statusu
        from utils.email_sender import send_order_status_change_email

        try:
            send_order_status_change_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                old_status=old_status,
                new_status=new_status
            )
            current_app.logger.info(f"Status change email sent for {order.order_number} to {email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send status change email for {order.order_number}: {e}")

    @staticmethod
    def notify_supplier_ordered(order):
        """Wysyła email o zamówieniu produktów u dostawcy."""
        if not EmailManager.is_email_enabled('notify_supplier_ordered'):
            current_app.logger.info("Email notification 'notify_supplier_ordered' is disabled, skipping")
            return

        from utils.email_sender import send_supplier_ordered_email

        email = order.customer_email
        if not email:
            return

        try:
            order_detail_url = url_for('orders.client_detail', order_id=order.id, _external=True)
            send_supplier_ordered_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                order_detail_url=order_detail_url
            )
            current_app.logger.info(f"Supplier ordered email sent for {order.order_number} to {email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send supplier ordered email for {order.order_number}: {e}")

    @staticmethod
    def notify_supplier_cancelled(order):
        """Wysyła email o anulowaniu zamówienia u dostawcy."""
        if not EmailManager.is_email_enabled('notify_supplier_cancelled'):
            current_app.logger.info("Email notification 'notify_supplier_cancelled' is disabled, skipping")
            return

        from utils.email_sender import send_supplier_cancelled_email

        email = order.customer_email
        if not email:
            return

        try:
            order_detail_url = url_for('orders.client_detail', order_id=order.id, _external=True)
            send_supplier_cancelled_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                order_detail_url=order_detail_url
            )
            current_app.logger.info(f"Supplier cancelled email sent for {order.order_number} to {email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send supplier cancelled email for {order.order_number}: {e}")

    @staticmethod
    def notify_order_completed(order):
        """
        Wysyła email podsumowujący zakończone zamówienie.
        Zawiera listę produktów i pełny breakdown kosztów.

        Args:
            order: obiekt Order (ze statusem 'dostarczone')
        """
        if not EmailManager.is_email_enabled('notify_order_completed'):
            current_app.logger.info("Email notification 'notify_order_completed' is disabled, skipping")
            return

        from utils.email_sender import send_order_completed_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send order completed email for {order.order_number}: no email")
            return

        order_detail_url = url_for('orders.client_detail',
                                   order_id=order.id, _external=True)

        # Przygotuj listę produktów
        order_items = []
        for item in order.items:
            order_items.append({
                'product_name': item.product.name if item.product else 'Produkt usunięty',
                'quantity': item.quantity,
                'total': float(item.total)
            })

        # Oblicz koszty
        products_total = float(order.effective_total or order.total_amount or 0)
        proxy_shipping = float(order.proxy_shipping_cost or 0)
        customs_vat = float(order.customs_vat_sale_cost or 0)
        shipping_cost = float(order.shipping_cost or 0)
        grand_total = products_total + proxy_shipping + customs_vat + shipping_cost

        try:
            send_order_completed_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                order_items=order_items,
                products_total=products_total,
                proxy_shipping=proxy_shipping,
                customs_vat=customs_vat,
                shipping_cost=shipping_cost,
                grand_total=grand_total,
                order_detail_url=order_detail_url
            )
            current_app.logger.info(f"Order completed email sent for {order.order_number} to {email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send order completed email for {order.order_number}: {e}")

    @staticmethod
    def notify_tracking_added(order, tracking_number, courier, courier_name, tracking_url=None):
        """
        Wysyła email o nadaniu przesyłki (dodaniu numeru śledzenia).
        Automatycznie rozwiązuje email klienta.

        Args:
            order: obiekt Order
            tracking_number (str): numer śledzenia
            courier (str): slug kuriera (np. 'inpost')
            courier_name (str): display name kuriera (np. 'InPost')
            tracking_url (str): URL do śledzenia (opcjonalny, generowany jeśli brak)
        """
        if not EmailManager.is_email_enabled('notify_tracking_added'):
            current_app.logger.info("Email notification 'notify_tracking_added' is disabled, skipping")
            return

        from utils.email_sender import send_tracking_number_email

        email = order.customer_email
        if not email:
            return

        # Wygeneruj tracking URL jeśli nie podano
        if not tracking_url and courier and tracking_number:
            from modules.orders.utils import get_tracking_url
            tracking_url = get_tracking_url(courier, tracking_number)

        try:
            send_tracking_number_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                tracking_number=tracking_number,
                courier_name=courier_name,
                tracking_url=tracking_url
            )
            current_app.logger.info(f"Tracking email sent for {order.order_number} to {email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send tracking email for {order.order_number}: {e}")

    # ========================================
    # OFFER EMAILS
    # ========================================

    @staticmethod
    def notify_offer_closure(order, page, items, fulfilled_items=None,
                                 fulfilled_total=0, shipping_cost=0, grand_total=0,
                                 payment_methods=None):
        """
        Wysyła email z podsumowaniem zamówienia po zamknięciu strony Offer.
        Automatycznie rozwiązuje email klienta i generuje URL do uploadu płatności.

        Args:
            order: obiekt Order
            page: obiekt OfferPage
            items (list): lista dict z kluczami product_name, quantity, is_fulfilled
            fulfilled_items (list): lista zrealizowanych produktów
            fulfilled_total (float): suma zrealizowanych
            shipping_cost (float): koszt wysyłki
            grand_total (float): suma całkowita
            payment_methods (list): lista metod płatności
        """
        if not EmailManager.is_email_enabled('notify_offer_closure'):
            current_app.logger.info("Email notification 'notify_offer_closure' is disabled, skipping")
            return

        from utils.email_sender import send_offer_closure_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send closure email for {order.order_number}: no email")
            return

        upload_payment_url = url_for('orders.client_detail',
                                     order_id=order.id,
                                     _external=True) + '?action=upload_payment'

        try:
            send_offer_closure_email(
                customer_email=email,
                customer_name=order.customer_name,
                page_name=page.name,
                items=items,
                fulfilled_items=fulfilled_items or [],
                fulfilled_total=fulfilled_total,
                shipping_cost=shipping_cost,
                grand_total=grand_total,
                order_number=order.order_number,
                payment_methods=payment_methods or [],
                upload_payment_url=upload_payment_url
            )
            current_app.logger.info(f"Offer closure email sent for {order.order_number} to {email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send closure email for {order.order_number}: {e}")

    @staticmethod
    def notify_order_cancelled(order, page, cancelled_items, reason=''):
        """
        Wysyła email o anulowaniu zamówienia offer.
        Automatycznie rozwiązuje email klienta.

        Args:
            order: obiekt Order
            page: obiekt OfferPage
            cancelled_items (list): lista dict z name, quantity, image_url
            reason (str): powód anulowania
        """
        if not EmailManager.is_email_enabled('notify_order_cancelled'):
            current_app.logger.info("Email notification 'notify_order_cancelled' is disabled, skipping")
            return

        from utils.email_sender import send_order_cancelled_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send cancellation email for {order.order_number}: no email")
            return

        try:
            send_order_cancelled_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                page_name=page.name,
                cancelled_items=cancelled_items,
                reason=reason
            )
            current_app.logger.info(f"Cancellation email sent for {order.order_number} to {email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send cancellation email for {order.order_number}: {e}")

    @staticmethod
    def notify_back_in_stock(email, product_name, product_image_url,
                             offer_page_name, offer_page_url):
        """
        Wysyła powiadomienie o powrocie produktu do dostępności na stronie Offer.

        Args:
            email (str): email odbiorcy (z subskrypcji)
            product_name (str): nazwa produktu
            product_image_url (str): URL do zdjęcia produktu
            offer_page_name (str): nazwa strony Offer
            offer_page_url (str): URL do strony Offer

        Returns:
            bool: True jeśli wysłano
        """
        if not EmailManager.is_email_enabled('notify_back_in_stock'):
            current_app.logger.info("Email notification 'notify_back_in_stock' is disabled, skipping")
            return False

        from utils.email_sender import send_back_in_stock_email

        if not email:
            return False

        try:
            result = send_back_in_stock_email(
                email=email,
                product_name=product_name,
                product_image_url=product_image_url,
                offer_page_name=offer_page_name,
                offer_page_url=offer_page_url
            )
            if result:
                current_app.logger.info(f"Back in stock email sent to {email} for {product_name}")
            return result
        except Exception as e:
            current_app.logger.error(f"Failed to send back in stock email to {email}: {e}")
            return False

    @staticmethod
    def notify_new_offer_page(page, clients):
        """
        Wysyła email o nowej stronie Offer do listy klientów.

        Args:
            page: obiekt OfferPage
            clients: lista obiektów User z rolą 'client'
        """
        if not EmailManager.is_email_enabled('notify_new_offer_page'):
            current_app.logger.info("Email notification 'notify_new_offer_page' is disabled, skipping")
            return 0

        from utils.email_sender import send_new_offer_page_email

        page_url = url_for('offers.order_page', token=page.token, _external=True)
        sent_count = 0

        for client in clients:
            email = client.email
            if not email:
                continue

            name = client.first_name or 'Kliencie'

            try:
                send_new_offer_page_email(
                    user_email=email,
                    user_name=name,
                    page_name=page.name,
                    page_url=page_url
                )
                sent_count += 1
            except Exception as e:
                current_app.logger.error(f"Failed to send new offer page email to {email}: {e}")

        current_app.logger.info(f"New offer page emails sent: {sent_count}/{len(clients)} for '{page.name}'")
        return sent_count

    @staticmethod
    def notify_sale_end_date_changed(page, old_ends_at, new_ends_at, recipients):
        """
        Wysyła e-mail o zmianie daty zakończenia sprzedaży do listy odbiorców.

        Args:
            page: obiekt OfferPage
            old_ends_at: datetime lub None — poprzednia data
            new_ends_at: datetime lub None — nowa data
            recipients: lista obiektów User (już rozwiązana — bez duplikatów)

        Returns:
            int: liczba wysłanych e-maili
        """
        if not EmailManager.is_email_enabled('notify_sale_end_date_changed'):
            current_app.logger.info(
                "Email notification 'notify_sale_end_date_changed' is disabled, skipping"
            )
            return 0

        from utils.email_sender import send_sale_end_date_changed_email

        def _format_date(dt):
            if dt is None:
                return 'bez limitu czasowego'
            return dt.strftime('%d.%m.%Y, %H:%M')

        old_display = _format_date(old_ends_at)
        new_display = _format_date(new_ends_at)

        page_url = url_for('offers.order_page', token=page.token, _external=True)
        sent_count = 0

        for client in recipients:
            email = client.email
            if not email:
                continue

            name = client.first_name or 'Kliencie'

            try:
                ok = send_sale_end_date_changed_email(
                    user_email=email,
                    user_name=name,
                    page_name=page.name,
                    old_ends_at_display=old_display,
                    new_ends_at_display=new_display,
                    page_url=page_url,
                )
                if ok:
                    sent_count += 1
            except Exception as e:
                current_app.logger.error(
                    f"Failed to send sale end date changed email to {email}: {e}"
                )

        current_app.logger.info(
            f"Sale end date changed emails sent: {sent_count}/{len(recipients)} for '{page.name}'"
        )
        return sent_count

    # ========================================
    # SHIPPING REQUEST EMAILS
    # ========================================

    @staticmethod
    def notify_shipping_request_created(shipping_request, user):
        """
        Wysyła potwierdzenie utworzenia zlecenia wysyłki.

        Args:
            shipping_request: obiekt ShippingRequest
            user: obiekt User (zalogowany klient)
        """
        if not EmailManager.is_email_enabled('notify_shipping_request_created'):
            current_app.logger.info("Email notification 'notify_shipping_request_created' is disabled, skipping")
            return

        from utils.email_sender import send_shipping_request_created_email

        email = user.email
        if not email:
            current_app.logger.warning(
                f"Cannot send shipping request email for {shipping_request.request_number}: no email"
            )
            return

        # Mapowanie delivery_method na czytelną nazwę
        delivery_labels = {
            'kurier': 'Kurier (adres domowy)',
            'paczkomat': 'InPost Paczkomat',
            'orlen_paczka': 'Orlen Paczka',
            'dpd_pickup': 'DPD Pickup',
        }

        # Ustal metodę dostawy
        if shipping_request.address_type == 'home':
            delivery_method_display = 'Kurier (adres domowy)'
        elif shipping_request.pickup_courier:
            courier_lower = shipping_request.pickup_courier.lower()
            if 'inpost' in courier_lower or 'paczkomat' in courier_lower:
                delivery_method_display = 'InPost Paczkomat'
            elif 'orlen' in courier_lower:
                delivery_method_display = 'Orlen Paczka'
            elif 'dpd' in courier_lower:
                delivery_method_display = 'DPD Pickup'
            else:
                delivery_method_display = f'Punkt odbioru ({shipping_request.pickup_courier})'
        else:
            delivery_method_display = 'Punkt odbioru'

        try:
            send_shipping_request_created_email(
                user_email=email,
                user_name=user.first_name or 'Kliencie',
                request_number=shipping_request.request_number,
                orders=shipping_request.orders,
                delivery_method_display=delivery_method_display,
                full_address=shipping_request.full_address,
                shipping_requests_url=url_for('client.shipping_requests_list', _external=True)
            )
            current_app.logger.info(
                f"Shipping request email sent for {shipping_request.request_number} to {email}"
            )
        except Exception as e:
            current_app.logger.error(
                f"Failed to send shipping request email for {shipping_request.request_number}: {e}"
            )

    @staticmethod
    def notify_shipping_status_change(shipping_request, old_status_slug):
        """
        Wysyła powiadomienie o zmianie statusu zlecenia wysyłki.

        Args:
            shipping_request: obiekt ShippingRequest
            old_status_slug: poprzedni status (slug)
        """
        if not EmailManager.is_email_enabled('notify_shipping_status_change'):
            current_app.logger.info("Email notification 'notify_shipping_status_change' is disabled, skipping")
            return

        from utils.email_sender import send_shipping_status_change_email
        from modules.orders.models import ShippingRequestStatus

        user = shipping_request.user
        if not user or not user.email:
            current_app.logger.warning(
                f"Cannot send shipping status email for {shipping_request.request_number}: no user email"
            )
            return

        # Get status display names
        old_status_obj = ShippingRequestStatus.query.filter_by(slug=old_status_slug).first()
        new_status_obj = ShippingRequestStatus.query.filter_by(slug=shipping_request.status).first()

        old_status_name = old_status_obj.name if old_status_obj else old_status_slug
        new_status_name = new_status_obj.name if new_status_obj else shipping_request.status
        new_status_color = new_status_obj.badge_color if new_status_obj else '#6B7280'

        # Courier name mapping
        courier_names = {
            'inpost': 'InPost', 'dpd': 'DPD', 'dhl': 'DHL', 'gls': 'GLS',
            'poczta_polska': 'Poczta Polska', 'orlen': 'Orlen Paczka',
            'ups': 'UPS', 'fedex': 'FedEx', 'other': 'Inny'
        }
        courier_name = courier_names.get(shipping_request.courier, shipping_request.courier) if shipping_request.courier else None

        try:
            send_shipping_status_change_email(
                user_email=user.email,
                user_name=user.first_name or 'Kliencie',
                request_number=shipping_request.request_number,
                old_status_name=old_status_name,
                new_status_name=new_status_name,
                new_status_color=new_status_color,
                orders=shipping_request.orders,
                tracking_number=shipping_request.tracking_number,
                courier_name=courier_name,
                shipping_requests_url=url_for('client.shipping_requests_list', _external=True)
            )
            current_app.logger.info(
                f"Shipping status change email sent for {shipping_request.request_number} to {user.email}"
            )
        except Exception as e:
            current_app.logger.error(
                f"Failed to send shipping status change email for {shipping_request.request_number}: {e}"
            )

    # ========================================
    # COST NOTIFICATION EMAILS
    # ========================================

    @staticmethod
    def notify_cost_added(order, cost_type, cost_amount):
        """
        Wysyła email o dodaniu kosztu do zamówienia.
        Automatycznie rozwiązuje email klienta.

        Args:
            order: obiekt Order
            cost_type (str): 'proxy_shipping', 'customs_vat' lub 'domestic_shipping'
            cost_amount (float): kwota kosztu
        """
        if not EmailManager.is_email_enabled('notify_cost_added'):
            current_app.logger.info("Email notification 'notify_cost_added' is disabled, skipping")
            return

        from utils.email_sender import send_cost_added_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send cost email for {order.order_number}: no email")
            return

        detail_url = url_for('orders.client_detail', order_id=order.id, _external=True)

        try:
            send_cost_added_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                cost_type=cost_type,
                cost_amount=cost_amount,
                order_detail_url=detail_url
            )
            cost_labels = {'proxy_shipping': 'proxy shipping', 'customs_vat': 'customs/VAT', 'domestic_shipping': 'domestic shipping'}
            cost_label = cost_labels.get(cost_type, cost_type)
            current_app.logger.info(f"Cost ({cost_label}) email sent for {order.order_number} to {email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send cost email for {order.order_number}: {e}")

    # ========================================
    # ADMIN NOTIFICATION EMAILS
    # ========================================

    @staticmethod
    def notify_admin_payment_uploaded(order, stage_names):
        """
        Wysyła email do adminów o nowym potwierdzeniu płatności do weryfikacji.

        Args:
            order: obiekt Order
            stage_names (str): nazwy etapów (np. 'Płatność za produkt, Cło i VAT')
        """
        if not EmailManager.is_email_enabled('notify_admin_payment_uploaded'):
            current_app.logger.info("Email notification 'notify_admin_payment_uploaded' is disabled, skipping")
            return

        from utils.email_sender import send_admin_payment_uploaded_email

        admin_emails = EmailManager.get_admin_notification_emails()
        if not admin_emails:
            current_app.logger.warning("No admin emails found to notify about payment upload")
            return

        review_url = url_for('admin.payment_confirmations_list', _external=True)

        for email in admin_emails:
            if not email:
                continue
            try:
                send_admin_payment_uploaded_email(
                    admin_email=email,
                    customer_name=order.customer_name,
                    customer_email=order.customer_email,
                    order_number=order.order_number,
                    stage_names=stage_names,
                    review_url=review_url
                )
            except Exception as e:
                current_app.logger.error(
                    f"Failed to send admin payment notification to {email}: {e}"
                )

        current_app.logger.info(
            f"Admin payment upload notifications sent for {order.order_number} ({len(admin_emails)} recipients)"
        )

    @staticmethod
    def notify_admin_new_order(order):
        """
        Wysyła email do adminów o nowym zamówieniu offer.

        Args:
            order: obiekt Order
        """
        if not EmailManager.is_email_enabled('notify_admin_new_order'):
            current_app.logger.info("Email notification 'notify_admin_new_order' is disabled, skipping")
            return

        from utils.email_sender import send_admin_new_order_email

        admin_emails = EmailManager.get_admin_notification_emails()
        if not admin_emails:
            current_app.logger.warning("No admin emails found to notify about new order")
            return

        order_detail_url = url_for('orders.admin_detail', order_id=order.id, _external=True)

        items = [{
            'product_name': item.product.name,
            'quantity': item.quantity,
            'price': float(item.price),
            'total': float(item.total)
        } for item in order.items]

        page_name = order.offer_page.name if order.offer_page else (order.offer_page_name or 'Offer')
        created_at = order.created_at.strftime('%d.%m.%Y %H:%M') if order.created_at else ''
        order_total = float(order.total_amount or 0)

        for email in admin_emails:
            if not email:
                continue
            try:
                send_admin_new_order_email(
                    admin_email=email,
                    customer_name=order.customer_name,
                    customer_email=order.customer_email,
                    order_number=order.order_number,
                    page_name=page_name,
                    items=items,
                    order_total=order_total,
                    order_detail_url=order_detail_url,
                    created_at=created_at
                )
            except Exception as e:
                current_app.logger.error(
                    f"Failed to send admin new order notification to {email}: {e}"
                )

        current_app.logger.info(
            f"Admin new order notifications sent for {order.order_number} ({len(admin_emails)} recipients)"
        )

    # ========================================
    # PAYMENT REMINDER EMAILS
    # ========================================

    @staticmethod
    def notify_payment_reminder(order, payment_deadline=None, reminder_context='before_deadline'):
        """
        Wysyła przypomnienie o niezapłaconych etapach zamówienia.
        """
        if not EmailManager.is_email_enabled('notify_payment_reminder'):
            current_app.logger.info("Email notification 'notify_payment_reminder' is disabled, skipping")
            return False

        from utils.email_sender import send_payment_reminder_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send payment reminder for {order.order_number}: no email")
            return False

        # Na razie tylko E1 (produkt)
        unpaid_stages = []
        product_status = order.product_payment_status
        if product_status in ('none', 'rejected'):
            unpaid_stages.append({
                'name': 'Płatność za produkt',
                'amount': float(order.effective_total or order.total_amount or 0),
                'status': product_status
            })

        if not unpaid_stages:
            return False

        confirmations_url = url_for('client.payment_confirmations', _external=True)

        try:
            send_payment_reminder_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                unpaid_stages=unpaid_stages,
                order_detail_url=confirmations_url,
                payment_deadline=payment_deadline,
                reminder_context=reminder_context
            )
            current_app.logger.info(
                f"Payment reminder sent for {order.order_number} to {email} "
                f"(context={reminder_context}, deadline={payment_deadline})"
            )
            return True
        except Exception as e:
            current_app.logger.error(f"Failed to send payment reminder for {order.order_number}: {e}")
            return False

    @staticmethod
    def notify_admin_deadline_exceeded(page, orders):
        """Wysyła email do admina o zamówieniach z przekroczonym deadline."""
        from utils.email_sender import send_deadline_exceeded_email

        admin_emails = EmailManager.get_admin_notification_emails()
        if not admin_emails:
            current_app.logger.warning("No admin emails configured for deadline exceeded notification")
            return

        orders_data = []
        for order in orders:
            orders_data.append({
                'order_number': order.order_number,
                'customer_name': order.customer_name or 'Brak',
                'customer_email': order.customer_email or 'Brak',
                'amount': float(order.effective_total or order.total_amount or 0),
            })

        try:
            for email in admin_emails:
                send_deadline_exceeded_email(
                    to_email=email,
                    page_name=page.name,
                    payment_deadline=page.payment_deadline,
                    orders=orders_data
                )
        except Exception as e:
            current_app.logger.error(f"Failed to send deadline exceeded email: {e}")

    # ========================================
    # PAYMENT EMAILS
    # ========================================

    @staticmethod
    def notify_payment_approved(order, confirmation):
        """
        Wysyła email o zaakceptowaniu potwierdzenia płatności.
        Automatycznie rozwiązuje email klienta (obsługuje gości!).

        Args:
            order: obiekt Order
            confirmation: obiekt PaymentConfirmation
        """
        if not EmailManager.is_email_enabled('notify_payment_approved'):
            current_app.logger.info("Email notification 'notify_payment_approved' is disabled, skipping")
            return

        from utils.email_sender import send_payment_approved_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send payment approved email for {order.order_number}: no email")
            return

        order_detail_url = url_for('orders.client_detail',
                                   order_id=order.id, _external=True)

        stage_name = confirmation.stage_display_name

        try:
            send_payment_approved_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                amount=float(confirmation.amount),
                order_detail_url=order_detail_url,
                stage_name=stage_name
            )
            current_app.logger.info(f"Payment approved email sent for {order.order_number} ({stage_name}) to {email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send payment approved email for {order.order_number}: {e}")

    @staticmethod
    def notify_payment_rejected(order, confirmation, rejection_reason):
        """
        Wysyła email o odrzuceniu potwierdzenia płatności.
        Automatycznie rozwiązuje email klienta (obsługuje gości!).

        Args:
            order: obiekt Order
            confirmation: obiekt PaymentConfirmation
            rejection_reason (str): powód odrzucenia
        """
        if not EmailManager.is_email_enabled('notify_payment_rejected'):
            current_app.logger.info("Email notification 'notify_payment_rejected' is disabled, skipping")
            return

        from utils.email_sender import send_payment_rejected_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send payment rejected email for {order.order_number}: no email")
            return

        try:
            upload_url = url_for('client.payment_confirmations', _external=True)

            stage_name = confirmation.stage_display_name

            send_payment_rejected_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                amount=float(confirmation.amount),
                rejection_reason=rejection_reason,
                upload_url=upload_url,
                stage_name=stage_name
            )
            current_app.logger.info(f"Payment rejected email sent for {order.order_number} ({stage_name}) to {email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send payment rejected email for {order.order_number}: {e}")
