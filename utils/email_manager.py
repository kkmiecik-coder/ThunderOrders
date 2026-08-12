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
        - notify_shipment_sent(shipping_request, ...) -> jeden mail o wysłanej paczce
        - notify_shipment_consolidated(shipping_request) -> mail o połączeniu wysyłek w paczkę zbiorczą

    ADMIN:
        - notify_admin_payment_uploaded(order, stage_names) -> nowe potwierdzenie płatności
        - notify_admin_new_order(order) -> nowe zamówienie offer
        - notify_admin_delivery_confirmed(sr) -> klient potwierdził odbiór paczki

    DOSTAWA (build_* zwracają LISTĘ Message — paczka zbiorcza to jedna wiadomość
    na uczestnika, zwykłe zlecenie jedna pozycja):
        - build_delivery_confirmation_message(sr) -> przypomnienie „czy paczka dotarła?" (batch)
        - build_delivery_autoclosed_message(sr) -> info o automatycznym domknięciu (batch)
        - notify_delivery_confirmed(sr) -> podziękowanie po potwierdzeniu odbioru
        - notify_delivery_autoclosed(sr) -> pojedyncza wysyłka info o domknięciu
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
    def send_password_reset_code(user, code):
        """
        Wysyła email z 6-cyfrowym kodem resetu hasła (mobile API).
        Wysyłka SYNCHRONICZNA - czeka na potwierdzenie SMTP.

        Args:
            user: obiekt User
            code (str): 6-cyfrowy kod resetu

        Returns:
            bool: True jeśli email został wysłany, False w przypadku błędu
        """
        from utils.email_sender import send_email_sync

        try:
            result = send_email_sync(
                to=user.email,
                subject='Kod resetu hasła - ThunderOrders',
                template='password_reset_code',
                user_name=user.first_name,
                reset_code=code
            )
            if result:
                current_app.logger.info(f"Password reset code sent to {user.email}")
            else:
                current_app.logger.error(f"Password reset code SMTP failed for {user.email}")
            return result
        except Exception as e:
            current_app.logger.error(f"Failed to send password reset code to {user.email}: {e}")
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
    def notify_admin_created_order(order, admin_user):
        """
        Wysyła klientowi powiadomienie o zamówieniu utworzonym ręcznie przez
        administratora (np. "Dodaj zamówienie extra" po zamknięciu strony PRE-ORDER).

        Args:
            order: obiekt Order (musi mieć ustawione user, items, offer_page)
            admin_user: obiekt User administratora który utworzył zamówienie
        """
        if not EmailManager.is_email_enabled('notify_admin_created_order'):
            current_app.logger.info(
                "Email notification 'notify_admin_created_order' is disabled, skipping"
            )
            return

        from utils.email_sender import send_admin_created_order_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(
                f"Cannot send admin-created order email for {order.order_number}: no email"
            )
            return

        try:
            order_items = []
            for item in order.items:
                order_items.append({
                    'product_name': item.product.name,
                    'quantity': item.quantity,
                    'price': float(item.price),
                    'total': float(item.total),
                })

            page_name = (
                order.offer_page.name if order.offer_page
                else (order.offer_page_name or '-')
            )

            admin_name = (
                f"{admin_user.first_name} {admin_user.last_name}".strip()
                or admin_user.email
            )

            payment_deadline_str = None
            if order.offer_page and order.offer_page.payment_deadline:
                payment_deadline_str = order.offer_page.payment_deadline.strftime(
                    '%d.%m.%Y %H:%M'
                )

            send_admin_created_order_email(
                user_email=email,
                user_name=order.customer_name,
                admin_name=admin_name,
                order_number=order.order_number,
                page_name=page_name,
                order_total=float(order.total_amount),
                order_items=order_items,
                payment_stages=order.payment_stages,
                payment_deadline=payment_deadline_str,
            )
            current_app.logger.info(
                f"Admin-created order email sent for {order.order_number} to {email}"
            )
        except Exception as e:
            current_app.logger.error(
                f"Failed to send admin-created order email for {order.order_number}: {e}"
            )

    @staticmethod
    def notify_packing_photo(order, consolidation_note=None):
        """
        Wysyła email ze zdjęciem spakowanej paczki do klienta.

        Args:
            order: obiekt Order (musi mieć ustawione packing_photo)
            consolidation_note (str): zdanie o wspólnym kartonie (paczka zbiorcza)
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
                consolidation_note=consolidation_note,
            )
            current_app.logger.info(
                f"Packing photo email sent for {order.order_number} to {email}"
            )
        except Exception as e:
            current_app.logger.error(
                f"Failed to send packing photo email for {order.order_number}: {e}"
            )

    @staticmethod
    def notify_packing_photo_for_request(sr, packed_orders=None):
        """Zdjęcie spakowanej paczki — po jednym mailu na uczestnika.

        Dotychczas mail leciał z pojedynczego zamówienia, więc przy paczce zbiorczej
        dostawał go właściciel przypadkowego zamówienia z grupy, a reszta nic.
        Karton jest wspólny, więc zdjęcie należy się każdemu.

        `packed_orders`: opcjonalna lista zamówień, które FIZYCZNIE trafiły do tego
        kartonu w TEJ sesji WMS (patrz `pack_shipping_request_group` w
        wms_packing.py). Paczka zbiorcza bywa pakowana częściowo — jeden uczestnik
        w tej sesji, drugi jeszcze czeka na swoją — więc bez tego filtra
        uczestnik, którego towaru fizycznie jeszcze nie ma w kartonie, dostałby
        mylące „Twoja paczka spakowana" (code review rundy 1, task 17; scenariusz
        analogiczny do test_pack_group_partial_session_leaves_sr_unpacked). Gdy
        nie podane (domyślne wywołanie, np. ręczny resend z panelu), zachowanie
        jest jak dotąd — powiadamiamy WSZYSTKICH uczestników zlecenia.
        """
        packed_ids = {o.id for o in packed_orders} if packed_orders is not None else None

        if not sr.is_consolidation:
            # Jeden karton = jeden mail, niezależnie od liczby zamówień w zleceniu —
            # osobny mail na każde zamówienie dublowałby wiadomość temu samemu
            # klientowi (regres z briefu: `for order in sr.orders` łamał
            # test_pack_group_packs_all_orders_once, który wymaga dokładnie 1 maila).
            kandydaci = sr.orders
            if packed_ids is not None:
                kandydaci = [o for o in kandydaci if o.id in packed_ids]
            if kandydaci:
                EmailManager.notify_packing_photo(kandydaci[0])
            return

        EmailManager._zdjecie_paczki_zbiorczej(sr, packed_ids)

    @staticmethod
    def _zdjecie_paczki_zbiorczej(sr, packed_ids):
        """Zdjęcie paczki zbiorczej — mail per uczestnik, jedno połączenie SMTP.

        Batch zamiast pętli po `notify_packing_photo`: paczkę zbiorczą z definicji
        dzieli kilka osób, a Hostinger limituje uwierzytelnienia SMTP per IP.

        Każdy uczestnik dostaje zdanie o wspólnym kartonie. Bez tego zdjęcie
        etykiety z pełnym imieniem, nazwiskiem i adresem adresata szło do obcych
        osób bez słowa komentarza — przy jednoczesnym skracaniu tego samego
        nazwiska do „Karolina B." wszędzie indziej. Adresata nazywamy więc
        wyłącznie przez `short_addressee_name`.
        """
        from utils.email_sender import prepare_packing_photo_email, send_email_batch

        if not EmailManager.is_email_enabled('notify_packing_photo'):
            current_app.logger.info(
                "Email notification 'notify_packing_photo' is disabled, skipping")
            return

        adresat = sr.short_addressee_name or 'osoby odbierającej paczkę'
        wiadomosci = []
        for uczestnik in sr.consolidation_participants:
            zamowienia = uczestnik['orders']
            if packed_ids is not None:
                zamowienia = [o for o in zamowienia if o.id in packed_ids]
            if not zamowienia:
                continue

            order = zamowienia[0]
            if not order.customer_email or not order.packing_photo:
                current_app.logger.warning(
                    f'Zdjęcie paczki {sr.request_number}: pomijam {order.order_number} '
                    f'(brak adresu e-mail albo zdjęcia)')
                continue

            czy_adresat = uczestnik['source_request'].id == sr.lead_source_request_id
            notatka = (
                'To paczka zbiorcza — w kartonie są też zamówienia innych osób, '
                'które odbierzesz razem ze swoimi.'
            ) if czy_adresat else (
                f'To paczka zbiorcza — w kartonie są zamówienia kilku osób, a na zdjęciu '
                f'może być widoczna etykieta z danymi odbiorcy ({adresat}), do którego '
                f'jedzie przesyłka.'
            )
            wiadomosci.append(prepare_packing_photo_email(
                user_email=order.customer_email,
                user_name=order.customer_name,
                order_number=order.order_number,
                photo_path=order.packing_photo,
                consolidation_note=notatka,
            ))

        if not wiadomosci:
            current_app.logger.info(
                f'Paczka {sr.request_number}: brak uczestników do powiadomienia o zdjęciu')
            return

        send_email_batch(wiadomosci)
        current_app.logger.info(
            f'Wysłano {len(wiadomosci)} maili ze zdjęciem paczki zbiorczej {sr.request_number}')

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

        Dla paczki zbiorczej (is_consolidation) rozgałęzia do _status_change_consolidated:
        bez tego mail poszedłby tylko do usera zlecenia zbiorczego (lidera) z listą
        WSZYSTKICH zamówień wszystkich uczestników — ten sam wyciek co w
        notify_shipment_sent, tylko przy zwykłej zmianie statusu (np. spakowane).

        Args:
            shipping_request: obiekt ShippingRequest
            old_status_slug: poprzedni status (slug)
        """
        if not EmailManager.is_email_enabled('notify_shipping_status_change'):
            current_app.logger.info("Email notification 'notify_shipping_status_change' is disabled, skipping")
            return

        from modules.orders.models import ShippingRequestStatus

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

        if shipping_request.is_consolidation:
            EmailManager._status_change_consolidated(
                shipping_request, old_status_name, new_status_name, new_status_color, courier_name)
            return

        from utils.email_sender import send_shipping_status_change_email

        user = shipping_request.user
        if not user or not user.email:
            current_app.logger.warning(
                f"Cannot send shipping status email for {shipping_request.request_number}: no user email"
            )
            return

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

    @staticmethod
    def _status_change_consolidated(sr, old_status_name, new_status_name, new_status_color, courier_name):
        """Zmiana statusu paczki zbiorczej: jeden mail na uczestnika, z jego zamówieniami.

        Ten sam powód co w _shipment_sent_consolidated — wspólny mail ujawniłby
        adresatowi numery zamówień pozostałych uczestników. Batch, nie pętla po
        send_email() — patrz komentarz w _shipment_sent_consolidated.
        """
        from flask import url_for
        from utils.email_sender import prepare_shipping_status_change_email, send_email_batch

        uczestnicy = []
        for u in sr.consolidation_participants:
            user = u['user']
            if not user or not user.email:
                current_app.logger.warning(
                    f'Uczestnik paczki {sr.request_number} bez adresu e-mail — pomijam')
                continue
            uczestnicy.append(u)

        if not uczestnicy:
            current_app.logger.info(
                f'Paczka {sr.request_number}: brak uczestników z adresem e-mail przy zmianie statusu')
            return

        # Poza aktywnym requestem (np. wywołanie spoza kontekstu żądania) url_for
        # się wywali brakiem SERVER_NAME — degradujemy do braku linku zamiast
        # tracić powiadomienia wszystkich uczestników.
        try:
            requests_url = url_for('client.shipping_requests_list', _external=True)
        except RuntimeError:
            requests_url = None

        wiadomosci = []
        for uczestnik in uczestnicy:
            user = uczestnik['user']
            wiadomosci.append(prepare_shipping_status_change_email(
                user_email=user.email,
                user_name=user.first_name or 'Kliencie',
                request_number=uczestnik['source_request'].request_number,
                old_status_name=old_status_name,
                new_status_name=new_status_name,
                new_status_color=new_status_color,
                orders=uczestnik['orders'],
                tracking_number=sr.tracking_number,
                courier_name=courier_name,
                shipping_requests_url=requests_url,
            ))

        send_email_batch(wiadomosci)
        current_app.logger.info(
            f'Wysłano {len(wiadomosci)} maili o zmianie statusu paczki zbiorczej {sr.request_number}')

    @staticmethod
    def notify_shipment_sent(shipping_request, *, tracking_number=None, courier=None,
                             courier_name=None, tracking_url=None):
        """Wysyła JEDEN mail o wysłanej paczce — na całe zlecenie wysyłki.

        Zastępuje mail per zamówienie: przy trzech zamówieniach w jednym kartonie
        klient dostawał trzy wiadomości o tej samej przesyłce. Teraz dostaje jedną,
        z listą wszystkich zamówień w środku.

        Przełączniki powiadomień: świadomie korzystamy z istniejących kluczy
        zamiast dokładać nowy — nowy klucz startowałby jako włączony i po cichu
        zmieniłby to, co sklep wysyła.

        Args:
            shipping_request: obiekt ShippingRequest
            tracking_number (str): numer przesyłki (opcjonalny)
            courier (str): slug kuriera, potrzebny do wygenerowania URL śledzenia
            courier_name (str): nazwa kuriera do wyświetlenia
            tracking_url (str): URL śledzenia; gdy brak, generowany z kuriera i numeru
        """
        tracking_number = (tracking_number or '').strip()
        toggle_key = 'notify_tracking_added' if tracking_number else 'notify_status_change'
        if not EmailManager.is_email_enabled(toggle_key):
            current_app.logger.info(
                f"Email notification '{toggle_key}' is disabled, skipping")
            return

        from utils.email_sender import send_shipment_sent_email

        if shipping_request.is_consolidation:
            # Paczka zbiorcza: shipping_request.orders to WSZYSTKIE zamówienia
            # wszystkich uczestników (junction rows zjechały tu przy konsolidacji) —
            # jeden mail do sr.user (lidera) ujawniłby mu cudze numery zamówień.
            EmailManager._shipment_sent_consolidated(
                shipping_request, tracking_number, courier, courier_name, tracking_url)
            return

        orders = list(shipping_request.orders)
        if not orders:
            # Puste zlecenie (bez żadnych zamówień) nie ma czego wymieniać w mailu —
            # klient dostałby wiadomość z pustą listą zamówień. Nie ma o czym
            # powiadamiać, więc po prostu nic nie wysyłamy.
            current_app.logger.info(
                f"Shipping request {shipping_request.request_number} has no orders, "
                f"skipping shipment email"
            )
            return

        user = shipping_request.user
        # Zlecenie bez użytkownika (usunięte konto) — adres bierzemy z zamówienia,
        # Order.customer_email i tak sięga do konta klienta.
        email = user.email if user else (orders[0].customer_email if orders else None)
        if not email:
            current_app.logger.warning(
                f"Cannot send shipment email for {shipping_request.request_number}: no email"
            )
            return

        if tracking_number and not tracking_url and courier:
            from modules.orders.utils import get_tracking_url
            tracking_url = get_tracking_url(courier, tracking_number)

        try:
            send_shipment_sent_email(
                user_email=email,
                user_name=(user.first_name if user else None) or 'Kliencie',
                request_number=shipping_request.request_number,
                order_numbers=[o.order_number for o in orders],
                tracking_number=tracking_number or None,
                courier_name=courier_name,
                tracking_url=tracking_url,
                shipping_requests_url=url_for('client.shipping_requests_list', _external=True),
            )
            current_app.logger.info(
                f"Shipment email sent for {shipping_request.request_number} to {email}"
            )
        except Exception as e:
            current_app.logger.error(
                f"Failed to send shipment email for {shipping_request.request_number}: {e}"
            )

    @staticmethod
    def _shipment_sent_consolidated(sr, tracking_number, courier, courier_name, tracking_url):
        """Paczka zbiorcza: jeden mail na uczestnika, każdy ze swoją listą zamówień.

        Wspólny mail ujawniłby adresatowi numery zamówień pozostałych osób. Bez
        fallbacku na e-mail z zamówienia (jak w gałęzi niekonsolidowanej) — dla
        paczki zbiorczej wysłałby liczbę zamówień WSZYSTKICH uczestników obcej
        osobie, gdyby konto właściciela zostało usunięte.
        """
        from flask import url_for
        from utils.email_sender import prepare_shipment_sent_email, send_email_batch
        from modules.orders.utils import get_tracking_url

        if not tracking_url and tracking_number and courier:
            tracking_url = get_tracking_url(courier, tracking_number)

        uczestnicy = []
        for u in sr.consolidation_participants:
            user = u['user']
            if not user or not user.email:
                # Konto usunięte: fallback na adres z zamówienia wysłałby listę
                # zamówień wszystkich uczestników obcej osobie.
                current_app.logger.warning(
                    f'Uczestnik paczki {sr.request_number} bez adresu e-mail — pomijam')
                continue
            uczestnicy.append(u)

        if not uczestnicy:
            current_app.logger.info(
                f'Paczka {sr.request_number}: brak uczestników z adresem e-mail, nic nie wysyłam')
            return

        # URL-e liczymy tu, w kontekście wołającego — wątek batcha go nie ma. Poza
        # aktywnym requestem url_for się wywali brakiem SERVER_NAME — degradujemy
        # do braku linku zamiast tracić powiadomienia wszystkich uczestników.
        try:
            requests_url = url_for('client.shipping_requests_list', _external=True)
        except RuntimeError:
            requests_url = None
        # Konto bez imienia albo paczkomat bez shipping_name daje short_addressee_name
        # == None — bez zastępnika zdanie kończyło się dosłownym „na adres: None.”
        # (patrz ten sam wzorzec w notify_shipment_consolidated / _nota_paczki_zbiorczej).
        adresat = sr.short_addressee_name or 'osoby odbierającej paczkę'

        wiadomosci = []
        for uczestnik in uczestnicy:
            user = uczestnik['user']
            czy_adresat = uczestnik['source_request'].id == sr.lead_source_request_id
            nota = None
            if not czy_adresat:
                # short_addressee_name kończy się kropką skrótu nazwiska („Ola K.”) —
                # dokładanie własnej kropki dawało „Ola K..”. Stawiamy ją tylko wtedy,
                # gdy zdanie jeszcze jej nie ma.
                nota = f'Twoje zamówienia jadą w paczce zbiorczej wysłanej na adres: {adresat}'
                if not nota.endswith('.'):
                    nota += '.'
            wiadomosci.append(prepare_shipment_sent_email(
                user_email=user.email,
                user_name=user.first_name or 'Kliencie',
                request_number=uczestnik['source_request'].request_number,
                order_numbers=[o.order_number for o in uczestnik['orders']],
                tracking_number=tracking_number or None,
                courier_name=courier_name,
                tracking_url=tracking_url,
                shipping_requests_url=requests_url,
                consolidation_note=nota,
            ))

        send_email_batch(wiadomosci)
        current_app.logger.info(
            f'Wysłano {len(wiadomosci)} maili o paczce zbiorczej {sr.request_number}')

    @staticmethod
    def notify_shipment_consolidated(sr):
        """Informuje uczestników, że ich wysyłki pojechały do jednej paczki.

        Bez tego klient dowiaduje się o zmianie dopiero z maila o wysyłce, gdzie
        nagle pojawia się cudzy adres. Świadomie korzysta z istniejącego klucza
        przełącznika ('notify_status_change') zamiast dokładać nowy — patrz
        komentarz w notify_shipment_sent.
        """
        if not EmailManager.is_email_enabled('notify_status_change'):
            current_app.logger.info(
                "Email notification 'notify_status_change' is disabled, skipping")
            return
        if not sr.is_consolidation:
            return

        from flask import url_for
        from utils.email_sender import prepare_shipment_consolidated_email, send_email_batch

        # Poza aktywnym requestem (np. wywołanie z serwisu konsolidacji spoza
        # kontekstu żądania) url_for wywali RuntimeError brakiem SERVER_NAME —
        # degradujemy do braku linku zamiast tracić powiadomienia wszystkich uczestników.
        try:
            requests_url = url_for('client.shipping_requests_list', _external=True)
        except RuntimeError:
            requests_url = None
        adresat = sr.short_addressee_name or 'osoby odbierającej paczkę'

        wiadomosci = []
        for uczestnik in sr.consolidation_participants:
            user = uczestnik['user']
            if not user or not user.email:
                current_app.logger.warning(
                    f'Uczestnik paczki {sr.request_number} bez adresu e-mail — pomijam')
                continue
            wiadomosci.append(prepare_shipment_consolidated_email(
                user_email=user.email,
                user_name=user.first_name or 'Kliencie',
                request_number=uczestnik['source_request'].request_number,
                order_numbers=[o.order_number for o in uczestnik['orders']],
                recipient_name=adresat,
                is_recipient=uczestnik['source_request'].id == sr.lead_source_request_id,
                shipping_requests_url=requests_url,
            ))

        if not wiadomosci:
            current_app.logger.info(
                f'Paczka {sr.request_number}: brak uczestników z adresem e-mail przy scaleniu')
            return

        send_email_batch(wiadomosci)
        current_app.logger.info(
            f'Wysłano {len(wiadomosci)} maili o konsolidacji {sr.request_number}')

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

    @staticmethod
    def notify_costs_added_bulk(orders_costs, cost_type):
        """
        Wysyła emaile o dodaniu kosztu do WIELU zamówień jednym połączeniem SMTP.

        Używane przez masowe rozdzielanie kosztów (modale "Zamów do Polski" i
        "Cło/VAT") — pętla notify_cost_added() otwierałaby osobne połączenie
        per mail i wpadała w limit AUTH Hostingera (patrz fix 27787e2).

        Args:
            orders_costs: lista krotek (order, cost_amount)
            cost_type (str): 'proxy_shipping', 'customs_vat' lub 'domestic_shipping'

        Returns:
            int: liczba zakolejkowanych wiadomości
        """
        if not EmailManager.is_email_enabled('notify_cost_added'):
            current_app.logger.info("Email notification 'notify_cost_added' is disabled, skipping bulk")
            return 0

        from utils.email_sender import prepare_cost_added_email, send_email_batch

        messages = []
        for order, cost_amount in orders_costs:
            email = order.customer_email
            if not email:
                current_app.logger.warning(f"Cannot send cost email for {order.order_number}: no email")
                continue

            msg = prepare_cost_added_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                cost_type=cost_type,
                cost_amount=cost_amount,
                order_detail_url=url_for('orders.client_detail', order_id=order.id, _external=True),
            )
            if msg:
                messages.append(msg)

        if messages:
            send_email_batch(messages)
            current_app.logger.info(
                f"Queued batch of {len(messages)} cost ({cost_type}) emails"
            )
        return len(messages)

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
    def build_payment_reminder_message(order, stage='product', payment_deadline=None, reminder_context='before_deadline'):
        """
        Buduje wiadomość przypomnienia o płatności (BEZ wysyłania) do batch sendingu,
        dla dowolnego z czterech etapów (product/shipping_kr/customs_vat/domestic_shipping).

        Returns:
            Message lub None (gdy: powiadomienia wyłączone / brak emaila /
            etap już opłacony lub w trakcie weryfikacji / błąd budowania).
        """
        if not EmailManager.is_email_enabled('notify_payment_reminder'):
            current_app.logger.info("Email notification 'notify_payment_reminder' is disabled, skipping")
            return None

        from utils.email_sender import prepare_payment_reminder_email
        from modules.orders.payment_overdue_service import STAGE_DEFINITIONS

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send payment reminder for {order.order_number}: no email")
            return None

        definition = STAGE_DEFINITIONS[stage]
        status = definition['status'](order)
        if status not in ('none', 'rejected'):
            return None

        if stage == 'product':
            # Etap produktowy (E1): mail ma pokazywać kwotę faktycznie należną
            # przy częściowej realizacji (effective_total), a nie pełną
            # total_amount jak kafelek/lista zaległości w adminie.
            amount = order.effective_total or order.total_amount
        else:
            amount = definition['amount'](order)
        unpaid_stages = [{
            'name': definition['label'],
            'amount': float(amount or 0),
            'status': status,
        }]

        confirmations_url = url_for('client.payment_confirmations', _external=True)

        return prepare_payment_reminder_email(
            user_email=email,
            user_name=order.customer_name,
            order_number=order.order_number,
            unpaid_stages=unpaid_stages,
            order_detail_url=confirmations_url,
            payment_deadline=payment_deadline,
            reminder_context=reminder_context
        )

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

    # ========================================
    # DOSTAWA (task 869efhwph)
    # ========================================

    @staticmethod
    def _adresat_zlecenia(sr):
        """(email, imię) dla zlecenia wysyłki albo (None, None).

        Konto mogło zostać usunięte — dla ZWYKŁEGO (niezbiorczego) zlecenia wtedy
        schodzimy na adres z pierwszego zamówienia, tak samo jak robi to
        notify_shipment_sent.

        Dla paczki zbiorczej (sr.is_consolidation) tego fallbacku CELOWO nie ma.
        sr.orders idzie po surowym request_orders, a przy konsolidacji junction
        rows wszystkich uczestników wiszą pod zleceniem zbiorczym — sr.orders[0]
        mógłby więc być zamówieniem zupełnie obcej osoby, niezwiązanej z
        właścicielem paczki. Wysłany do niej mail ujawniłby cudzy numer
        zlecenia i listę zamówień (patrz _kontekst_dostawy — używa poprawnie
        display_orders, ale dla samej paczki zbiorczej display_orders i tak
        zwraca zamówienia wszystkich uczestników, bo to ona jest ich wspólnym
        "właścicielem"), a w notify_delivery_confirmed dodatkowo cudzą ocenę i
        komentarz. _shipment_sent_consolidated obok rozwiązuje ten sam problem
        inaczej — wysyła osobny mail do KAŻDEGO uczestnika z jego własną listą
        zamówień i pomija tych bez adresu zamiast zgadywać adresata. Tutaj przy
        braku właściciela paczki zbiorczej nie ma jednoznacznego adresata w
        ogóle, więc zwracamy (None, None) — wywołujący (build_* / notify_*)
        traktuje to jak zwykły brak adresu i nic nie wysyła.
        """
        user = sr.user
        if user and user.email:
            return user.email, (user.first_name or 'Kliencie')

        if sr.is_consolidation:
            return None, None

        orders = list(sr.orders)
        if orders and orders[0].customer_email:
            return orders[0].customer_email, (orders[0].customer_name or 'Kliencie')
        return None, None

    @staticmethod
    def _kontekst_dostawy(sr, orders=None):
        """Wspólne zmienne maili o dostawie — dla JEDNEGO adresata.

        `sr` to zlecenie, które adresat widzi u siebie w panelu: dla uczestnika
        paczki zbiorczej jego własne zlecenie ŹRÓDŁOWE, nie sama paczka. Stąd bierze
        się numer w treści maila i cel linku, więc nikt nie dostaje identyfikatora
        paczki, w której jadą cudze zamówienia (strona potwierdzenia i tak odrzuca
        wejście po id paczki zbiorczej — patrz zlecenie_do_potwierdzenia).

        `orders` pozwala podać listę zamówień wprost; domyślnie `sr.display_orders`.
        Dla zlecenia źródłowego display_orders już filtruje po source_request_id, ale
        wołający konsolidacyjny ma tę listę policzoną raz w consolidation_participants
        i nie ma sensu jej odtwarzać.
        """
        from flask import url_for
        if orders is None:
            orders = sr.display_orders
        return {
            'request_number': sr.request_number,
            'order_numbers': [o.order_number for o in orders],
            'confirm_url': url_for('client.confirm_delivery',
                                   request_id=sr.id, _external=True),
        }

    @staticmethod
    def _odbiorcy_dostawy(sr):
        """Adresaci maila o dostawie.

        [{'email', 'imie', 'zlecenie', 'kontekst', 'czy_lider'}].

        Dla zwykłego zlecenia jedna pozycja. Dla paczki zbiorczej — po jednej na
        uczestnika, każdy z WŁASNĄ listą zamówień i własnym numerem zlecenia.

        Dlaczego to nie może być jeden mail do sr.user: `_kopiuj_adres` przy
        konsolidacji ustawia `zbiorcze.user_id = lead.user_id`, a wiersze junction
        wszystkich uczestników zjeżdżają pod zlecenie zbiorcze. Jeden mail do lidera
        wymieniałby więc numery zamówień obcych osób, a pozostali uczestnicy nie
        dostawaliby o dostawie ŻADNEJ wiadomości. Ten sam problem i to samo
        rozwiązanie co w `_shipment_sent_consolidated` — bez fallbacku na adres z
        zamówienia dla osób z usuniętym kontem, bo przy paczce zbiorczej taki adres
        może należeć do kogoś zupełnie innego niż właściciel danych w mailu.

        `czy_lider` to dokładnie to samo rozróżnienie co `czy_adresat`
        w `_shipment_sent_consolidated`: czy TEN adresat jest osobą, na której adres
        paczkę nadano. Tylko ona może potwierdzić odbiór (`zlecenie_do_potwierdzenia`
        odsyła pozostałych) i tylko ona faktycznie klika, więc bez tej flagi
        rozesłanie maila do wszystkich uczestników znaczyłoby proszenie ich o czynność
        niewykonalną i dziękowanie im za cudze kliknięcie. Dla zwykłego zlecenia
        zawsze True — jedyny adresat jest zarazem jedynym potwierdzającym.
        """
        if not sr.is_consolidation:
            email, imie = EmailManager._adresat_zlecenia(sr)
            if not email:
                return []
            return [{
                'email': email,
                'imie': imie,
                'zlecenie': sr,
                'kontekst': EmailManager._kontekst_dostawy(sr),
                'czy_lider': True,
            }]

        odbiorcy = []
        for uczestnik in sr.consolidation_participants:
            user = uczestnik['user']
            if not user or not user.email:
                current_app.logger.warning(
                    f'Uczestnik paczki {sr.request_number} bez adresu e-mail — pomijam')
                continue
            zrodlo = uczestnik['source_request']
            odbiorcy.append({
                'email': user.email,
                'imie': user.first_name or 'Kliencie',
                'zlecenie': zrodlo,
                'kontekst': EmailManager._kontekst_dostawy(zrodlo, uczestnik['orders']),
                'czy_lider': zrodlo.id == sr.lead_source_request_id,
            })
        return odbiorcy

    @staticmethod
    def _nota_paczki_zbiorczej(sr, potwierdzony=False):
        """Zdanie dla uczestnika paczki zbiorczej, który NIE jest jej adresatem.

        Odpowiednik `consolidation_note` z `_shipment_sent_consolidated` dla maili
        o dostawie: uczestnik dostaje wiadomość o cudzym kartonie, więc musi wiedzieć,
        że jego zamówienia jechały zbiorczo i na czyj adres. Nazwisko skracamy przez
        `short_addressee_name` (jak wszędzie indziej), a gdy go nie ma — mówimy
        „innego uczestnika” zamiast wstawiać puste miejsce.

        `potwierdzony=True` dokłada zdanie o tym, KTO potwierdził odbiór. Używa go
        wyłącznie mail po potwierdzeniu; przy domknięciu automatem nie potwierdził
        nikt, więc takie zdanie byłoby nieprawdą.
        """
        adresat = sr.short_addressee_name
        gdzie = (f'wysłanej na adres: {adresat}' if adresat
                 else 'wysłanej na adres innego uczestnika')
        # `short_addressee_name` kończy się kropką skrótu nazwiska („Ola K.”), więc
        # dokładanie własnej dawało „Ola K...”. Kropkę stawiamy tylko wtedy, gdy
        # zdania jeszcze nie zamyka.
        nota = f'Twoje zamówienia jechały w paczce zbiorczej {gdzie}'
        if not nota.endswith('.'):
            nota += '.'
        if potwierdzony:
            nota += ' Odbiór potwierdziła osoba, do której paczka została nadana.'
        return nota

    @staticmethod
    def build_delivery_confirmation_message(sr):
        """Przypomnienie „czy paczka dotarła?" BEZ wysyłania — do batcha cronowego.

        Przy paczce zbiorczej idzie WYŁĄCZNIE do lidera. Ten mail nie informuje, tylko
        prosi o jedną konkretną czynność (CTA „Potwierdzam odbiór”), a wykonać ją może
        wyłącznie osoba, na której adres paczkę nadano — `zlecenie_do_potwierdzenia`
        odsyła pozostałych uczestników komunikatem, że tej paczki stąd nie potwierdzą.
        Wysłanie im prośby o rzecz niemożliwą to czysty szum; o samej dostawie
        dowiedzą się z maila po potwierdzeniu albo po domknięciu automatem (te idą do
        wszystkich, bo informują, a nie proszą).

        Returns:
            list[Message]: jednoelementowa dla zwykłego zlecenia i dla paczki
            zbiorczej (sam lider), pusta gdy powiadomienia wyłączone albo nie ma do
            kogo pisać. Lista, a nie pojedynczy Message, bo pozostałe maile o dostawie
            rodzą po jednej wiadomości na uczestnika i wołający (cron) obsługuje
            wszystkie tym samym kodem, zbierając je do jednego batcha SMTP.
        """
        if not EmailManager.is_email_enabled('notify_delivery_confirmation'):
            current_app.logger.info(
                "Email notification 'notify_delivery_confirmation' is disabled, skipping")
            return []

        from utils.email_sender import prepare_email

        odbiorcy = EmailManager._odbiorcy_dostawy(sr)
        if not odbiorcy:
            current_app.logger.warning(
                f'Brak adresata przypomnienia o dostawie {sr.request_number}')
            return []

        odbiorcy = [odb for odb in odbiorcy if odb['czy_lider']]
        if not odbiorcy:
            # Paczka zbiorcza bez wskazanego zlecenia wiodącego: odbioru nie potwierdzi
            # NIKT (zlecenie_do_potwierdzenia porównuje się właśnie z tym polem), więc
            # nie ma komu przypominać. Stan niespodziewany — konsolidacja ustawia
            # lead_source_request_id przy każdym scaleniu i przy wypięciu lidera —
            # dlatego zostaje w logu zamiast przejść po cichu.
            current_app.logger.warning(
                f'Paczka {sr.request_number} bez zlecenia wiodącego — nie ma komu '
                f'przypomnieć o potwierdzeniu odbioru')
            return []

        wiadomosci = []
        for odb in odbiorcy:
            wiadomosci.append(prepare_email(
                to=odb['email'],
                subject=f"Czy paczka {odb['kontekst']['request_number']} do Ciebie dotarła?",
                template='delivery_confirmation',
                user_name=odb['imie'],
                **odb['kontekst'],
            ))
        # prepare_email oddaje None, gdy render szablonu padnie — jedna zepsuta
        # wiadomość nie może wywrócić batcha pozostałych uczestników.
        return [m for m in wiadomosci if m is not None]

    @staticmethod
    def build_delivery_autoclosed_message(sr):
        """Informacja o automatycznym domknięciu — do batcha cronowego.

        W odróżnieniu od przypomnienia idzie do WSZYSTKICH uczestników paczki
        zbiorczej: to informacja, nie prośba o czynność. Uczestnik ma prawo wiedzieć,
        że jego zlecenie zostało zamknięte, a zamówienia trafiły do kolekcji — nie
        prosimy go o nic, czego nie może zrobić (ocenę wystawia na SWOIM zleceniu
        źródłowym, patrz delivery_review_submit).

        Nie-lider dostaje dodatkowo `consolidation_note`: mail mówi o paczce, której
        fizycznie nie odbierał, więc bez tego zdania nie wiedziałby, że jechała
        zbiorczo i na czyj adres.

        Returns:
            list[Message] — patrz build_delivery_confirmation_message.
        """
        if not EmailManager.is_email_enabled('notify_delivery_autoclosed'):
            current_app.logger.info(
                "Email notification 'notify_delivery_autoclosed' is disabled, skipping")
            return []

        from utils.email_sender import prepare_email
        from modules.orders.delivery_config import pobierz_konfig_dostawy

        odbiorcy = EmailManager._odbiorcy_dostawy(sr)
        if not odbiorcy:
            current_app.logger.warning(
                f'Brak adresata informacji o domknięciu {sr.request_number}')
            return []

        konfig = pobierz_konfig_dostawy()
        wiadomosci = []
        for odb in odbiorcy:
            numer = odb['kontekst']['request_number']
            wiadomosci.append(prepare_email(
                to=odb['email'],
                # Temat jest prawdziwy dla obu ról: zlecenie adresata faktycznie
                # zamykamy, niezależnie od tego, kto był adresatem kartonu.
                subject=f'Zamykamy zlecenie {numer} — dziękujemy za zakupy',
                template='delivery_autoclosed',
                user_name=odb['imie'],
                dni_do_domkniecia=konfig['autocomplete_days'],
                okno_oceny_dni=konfig['review_window_days'],
                consolidation_note=(
                    None if odb['czy_lider']
                    else EmailManager._nota_paczki_zbiorczej(sr)),
                **odb['kontekst'],
            ))
        return [m for m in wiadomosci if m is not None]

    @staticmethod
    def notify_delivery_autoclosed(sr):
        """Pojedyncza wysyłka informacji o domknięciu (poza batchem)."""
        from utils.email_sender import send_email_batch_sync

        wiadomosci = EmailManager.build_delivery_autoclosed_message(sr)
        if wiadomosci:
            # Jedno połączenie SMTP na całą paczkę zbiorczą — Hostinger limituje
            # AUTH per IP, a uczestników bywa kilku.
            send_email_batch_sync(wiadomosci)

    @staticmethod
    def notify_delivery_confirmed(sr):
        """Podziękowanie po potwierdzeniu odbioru przez klienta.

        Mail nie jest tu grzecznościowy: to jedyne miejsce, w którym klient dostaje
        trwały link do zmiany wystawionej oceny — okno edycji ma tylko 3 dni, a na
        stronę potwierdzenia sam z siebie nie wróci.

        Paczka zbiorcza idzie osobną gałęzią (patrz _delivery_confirmed_consolidated):
        wspólny mail do lidera ujawniłby mu cudze numery zamówień, a reszta uczestników
        nie dowiedziałaby się o dostawie w ogóle.
        """
        if not EmailManager.is_email_enabled('notify_delivery_confirmed'):
            current_app.logger.info(
                "Email notification 'notify_delivery_confirmed' is disabled, skipping")
            return

        if sr.is_consolidation:
            EmailManager._delivery_confirmed_consolidated(sr)
            return

        from utils.email_sender import send_email
        from modules.orders.review_models import DeliveryReview

        email, imie = EmailManager._adresat_zlecenia(sr)
        if not email:
            return

        opinia = sr.review
        # Bez try/except: send_email() łapie własne wyjątki (render szablonu, SMTP)
        # i zwraca bool — nigdy nie rzuca. Błąd trafia już do logu przez [EMAIL]
        # w send_email(), więc dublowanie go tutaj tylko sugerowałoby nieistniejące ryzyko.
        send_email(
            to=email,
            subject=f'Dziękujemy za potwierdzenie odbioru — {sr.request_number}',
            template='delivery_confirmed',
            user_name=imie,
            rating=opinia.rating if opinia else None,
            comment=opinia.comment if opinia else None,
            okno_edycji_dni=DeliveryReview.OKNO_EDYCJI_DNI,
            # Zwykłe zlecenie: adresat sam potwierdził, więc żadnego zdania
            # o cudzej paczce nie ma. Przekazujemy jawnie, żeby szablon nie
            # zależał od Undefined (patrz gałąź konsolidacyjna niżej).
            consolidation_note=None,
            **EmailManager._kontekst_dostawy(sr),
        )

    @staticmethod
    def _delivery_confirmed_consolidated(sr):
        """Paczka zbiorcza: jeden mail na uczestnika, każdy ze swoją oceną i linkiem.

        Ocenę czytamy ze zlecenia ŹRÓDŁOWEGO adresata, nie ze zbiorczego: klient
        wiodący potwierdza odbiór ze swojego zlecenia i tam `zapisz_ocene` zakłada
        DeliveryReview, więc `zbiorcze.review` jest z definicji puste. Bez tego mail
        z podziękowaniem szedłby bez wystawionej przed chwilą oceny i z przyciskiem
        „Oceń dostawę" pokazanym komuś, kto właśnie ocenił.

        Kliknął JEDEN uczestnik — lider. Pozostałym nie wolno powiedzieć „dziękujemy
        za potwierdzenie odbioru”: nie potwierdzali niczego i nawet nie mogli (patrz
        `zlecenie_do_potwierdzenia`). Wiadomość dostają mimo to, bo ich zamówienia
        naprawdę zostały zamknięte i trafiły do kolekcji — zmienia się temat, nagłówek
        i pierwszy akapit, a `consolidation_note` mówi wprost, że odbiór potwierdziła
        osoba, na której adres nadano paczkę. To ta sama konwencja co
        `_shipment_sent_consolidated`.

        send_email_batch (jak w _shipment_sent_consolidated), nie pętla send_email —
        pętla otwierałaby tyle sesji SMTP, ilu jest uczestników.
        """
        from utils.email_sender import prepare_email, send_email_batch
        from modules.orders.review_models import DeliveryReview

        odbiorcy = EmailManager._odbiorcy_dostawy(sr)
        if not odbiorcy:
            current_app.logger.info(
                f'Paczka {sr.request_number}: brak uczestników z adresem e-mail, '
                f'nie wysyłam potwierdzenia odbioru')
            return

        wiadomosci = []
        for odb in odbiorcy:
            opinia = odb['zlecenie'].review
            numer = odb['kontekst']['request_number']
            wiadomosci.append(prepare_email(
                to=odb['email'],
                subject=(f'Dziękujemy za potwierdzenie odbioru — {numer}'
                         if odb['czy_lider']
                         else f'Paczka z Twoimi zamówieniami została odebrana — {numer}'),
                template='delivery_confirmed',
                user_name=odb['imie'],
                rating=opinia.rating if opinia else None,
                comment=opinia.comment if opinia else None,
                okno_edycji_dni=DeliveryReview.OKNO_EDYCJI_DNI,
                consolidation_note=(
                    None if odb['czy_lider']
                    else EmailManager._nota_paczki_zbiorczej(sr, potwierdzony=True)),
                **odb['kontekst'],
            ))

        wiadomosci = [m for m in wiadomosci if m is not None]
        if wiadomosci:
            send_email_batch(wiadomosci)
            current_app.logger.info(
                f'Wysłano {len(wiadomosci)} maili o potwierdzeniu odbioru '
                f'paczki zbiorczej {sr.request_number}')

    @staticmethod
    def notify_admin_delivery_confirmed(sr):
        """Informacja do adminów, że klient potwierdził odbiór.

        Świadomie tylko dla potwierdzeń klienta — domknięcia automatu idą porcjami
        po kilkadziesiąt na godzinę i zasypałyby skrzynkę.
        """
        if not EmailManager.is_email_enabled('notify_admin_delivery_confirmed'):
            current_app.logger.info(
                "Email notification 'notify_admin_delivery_confirmed' is disabled, skipping")
            return

        from utils.email_sender import send_email

        odbiorcy = EmailManager.get_admin_notification_emails()
        if not odbiorcy:
            return

        # review_dostawy, nie review: dla paczki zbiorczej opinia wisi na zleceniu
        # źródłowym klienta wiodącego, więc samo `sr.review` byłoby zawsze puste i
        # admin dostawałby mail bez oceny, którą klient przed chwilą wystawił.
        opinia = sr.review_dostawy
        user = sr.user
        klient = f'{user.first_name} {user.last_name}'.strip() if user else 'nieznany'

        # Bez try/except: send_email() łapie własne wyjątki i zwraca bool — nigdy
        # nie rzuca (patrz uzasadnienie w notify_delivery_confirmed).
        for adres in odbiorcy:
            send_email(
                to=adres,
                subject=f'Klient potwierdził odbiór — {sr.request_number}',
                template='admin_delivery_confirmed',
                request_number=sr.request_number,
                client_name=klient,
                client_email=(user.email if user else None),
                rating=opinia.rating if opinia else None,
                comment=opinia.comment if opinia else None,
                order_numbers=[o.order_number for o in sr.display_orders],
            )
