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

    EXCLUSIVE:
        - notify_exclusive_closure(order, page, items, ...) -> podsumowanie po zamknięciu
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
        - notify_admin_new_order(order) -> nowe zamówienie exclusive
"""

from flask import current_app, url_for


class EmailManager:
    """Centralny dispatcher emailowy dla ThunderOrders."""

    # ========================================
    # AUTH EMAILS
    # ========================================

    @staticmethod
    def send_verification_code(user, code):
        """
        Wysyła email z 6-cyfrowym kodem weryfikacyjnym.

        Args:
            user: obiekt User
            code (str): 6-cyfrowy kod weryfikacyjny
        """
        from utils.email_sender import send_verification_code_email

        try:
            send_verification_code_email(
                user_email=user.email,
                verification_code=code,
                user_name=user.first_name
            )
            current_app.logger.info(f"Verification code sent to {user.email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send verification code to {user.email}: {e}")

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

        Args:
            user: obiekt User (musi mieć password_reset_token)
        """
        from utils.email_sender import send_password_reset_email

        try:
            send_password_reset_email(
                user_email=user.email,
                reset_token=user.password_reset_token,
                user_name=user.first_name
            )
            current_app.logger.info(f"Password reset email sent to {user.email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send password reset email to {user.email}: {e}")

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
        from utils.email_sender import send_order_confirmation_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send order confirmation for {order.order_number}: no email")
            return

        is_guest = order.is_guest_order

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
                is_guest=is_guest,
                guest_view_token=order.guest_view_token if is_guest else None,
                is_exclusive=order.is_exclusive,
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
    def notify_order_completed(order):
        """
        Wysyła email podsumowujący zakończone zamówienie.
        Zawiera listę produktów i pełny breakdown kosztów.

        Args:
            order: obiekt Order (ze statusem 'dostarczone')
        """
        from utils.email_sender import send_order_completed_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send order completed email for {order.order_number}: no email")
            return

        # URL różny dla gości i zalogowanych
        if order.is_guest_order and order.guest_view_token:
            order_detail_url = url_for('orders.guest_track',
                                       token=order.guest_view_token, _external=True)
        else:
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
    # EXCLUSIVE EMAILS
    # ========================================

    @staticmethod
    def notify_exclusive_closure(order, page, items, fulfilled_items=None,
                                 fulfilled_total=0, shipping_cost=0, grand_total=0,
                                 payment_methods=None):
        """
        Wysyła email z podsumowaniem zamówienia po zamknięciu strony Exclusive.
        Automatycznie rozwiązuje email klienta i generuje URL do uploadu płatności.

        Args:
            order: obiekt Order
            page: obiekt ExclusivePage
            items (list): lista dict z kluczami product_name, quantity, is_fulfilled
            fulfilled_items (list): lista zrealizowanych produktów
            fulfilled_total (float): suma zrealizowanych
            shipping_cost (float): koszt wysyłki
            grand_total (float): suma całkowita
            payment_methods (list): lista metod płatności
        """
        from utils.email_sender import send_exclusive_closure_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send closure email for {order.order_number}: no email")
            return

        # URL do wgrania dowodu - różny dla gości i zalogowanych
        if order.is_guest_order and order.guest_view_token:
            upload_payment_url = url_for('orders.guest_track',
                                         token=order.guest_view_token,
                                         _external=True) + '?action=upload_payment'
        else:
            upload_payment_url = url_for('orders.client_detail',
                                         order_id=order.id,
                                         _external=True) + '?action=upload_payment'

        try:
            send_exclusive_closure_email(
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
            current_app.logger.info(f"Exclusive closure email sent for {order.order_number} to {email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send closure email for {order.order_number}: {e}")

    @staticmethod
    def notify_order_cancelled(order, page, cancelled_items, reason=''):
        """
        Wysyła email o anulowaniu zamówienia exclusive.
        Automatycznie rozwiązuje email klienta.

        Args:
            order: obiekt Order
            page: obiekt ExclusivePage
            cancelled_items (list): lista dict z name, quantity, image_url
            reason (str): powód anulowania
        """
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
                             exclusive_page_name, exclusive_page_url):
        """
        Wysyła powiadomienie o powrocie produktu do dostępności na stronie Exclusive.

        Args:
            email (str): email odbiorcy (z subskrypcji)
            product_name (str): nazwa produktu
            product_image_url (str): URL do zdjęcia produktu
            exclusive_page_name (str): nazwa strony Exclusive
            exclusive_page_url (str): URL do strony Exclusive

        Returns:
            bool: True jeśli wysłano
        """
        from utils.email_sender import send_back_in_stock_email

        if not email:
            return False

        try:
            result = send_back_in_stock_email(
                email=email,
                product_name=product_name,
                product_image_url=product_image_url,
                exclusive_page_name=exclusive_page_name,
                exclusive_page_url=exclusive_page_url
            )
            if result:
                current_app.logger.info(f"Back in stock email sent to {email} for {product_name}")
            return result
        except Exception as e:
            current_app.logger.error(f"Failed to send back in stock email to {email}: {e}")
            return False

    @staticmethod
    def notify_new_exclusive_page(page, clients):
        """
        Wysyła email o nowej stronie Exclusive do listy klientów.

        Args:
            page: obiekt ExclusivePage
            clients: lista obiektów User z rolą 'client'
        """
        from utils.email_sender import send_new_exclusive_page_email

        page_url = url_for('exclusive.order_page', token=page.token, _external=True)
        sent_count = 0

        for client in clients:
            email = client.email
            if not email:
                continue

            name = client.first_name or 'Kliencie'

            try:
                send_new_exclusive_page_email(
                    user_email=email,
                    user_name=name,
                    page_name=page.name,
                    page_url=page_url
                )
                sent_count += 1
            except Exception as e:
                current_app.logger.error(f"Failed to send new exclusive page email to {email}: {e}")

        current_app.logger.info(f"New exclusive page emails sent: {sent_count}/{len(clients)} for '{page.name}'")
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
        from utils.email_sender import send_cost_added_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send cost email for {order.order_number}: no email")
            return

        # Guest → link do guest_track, zalogowany → client_detail
        if order.is_guest_order and order.guest_view_token:
            detail_url = url_for('orders.guest_track', token=order.guest_view_token, _external=True)
        else:
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
        from utils.email_sender import send_admin_payment_uploaded_email
        from modules.auth.models import User

        admins = User.query.filter_by(role='admin').all()
        if not admins:
            current_app.logger.warning("No admins found to notify about payment upload")
            return

        review_url = url_for('admin.payment_confirmations_list', _external=True)
        is_guest = order.is_guest_order

        for admin in admins:
            if not admin.email:
                continue
            try:
                send_admin_payment_uploaded_email(
                    admin_email=admin.email,
                    customer_name=order.customer_name,
                    customer_email=order.customer_email,
                    order_number=order.order_number,
                    stage_names=stage_names,
                    is_guest=is_guest,
                    review_url=review_url
                )
            except Exception as e:
                current_app.logger.error(
                    f"Failed to send admin payment notification to {admin.email}: {e}"
                )

        current_app.logger.info(
            f"Admin payment upload notifications sent for {order.order_number} ({len(admins)} admins)"
        )

    @staticmethod
    def notify_admin_new_order(order):
        """
        Wysyła email do adminów o nowym zamówieniu exclusive.

        Args:
            order: obiekt Order
        """
        from utils.email_sender import send_admin_new_order_email
        from modules.auth.models import User

        admins = User.query.filter_by(role='admin').all()
        if not admins:
            current_app.logger.warning("No admins found to notify about new order")
            return

        order_detail_url = url_for('orders.admin_detail', order_id=order.id, _external=True)

        items = [{
            'product_name': item.product.name,
            'quantity': item.quantity,
            'price': float(item.price),
            'total': float(item.total)
        } for item in order.items]

        page_name = order.exclusive_page.name if order.exclusive_page else (order.exclusive_page_name or 'Exclusive')
        is_guest = order.is_guest_order
        created_at = order.created_at.strftime('%d.%m.%Y %H:%M') if order.created_at else ''
        order_total = float(order.total_amount or 0)

        for admin in admins:
            if not admin.email:
                continue
            try:
                send_admin_new_order_email(
                    admin_email=admin.email,
                    customer_name=order.customer_name,
                    customer_email=order.customer_email,
                    order_number=order.order_number,
                    page_name=page_name,
                    is_guest=is_guest,
                    items=items,
                    order_total=order_total,
                    order_detail_url=order_detail_url,
                    created_at=created_at
                )
            except Exception as e:
                current_app.logger.error(
                    f"Failed to send admin new order notification to {admin.email}: {e}"
                )

        current_app.logger.info(
            f"Admin new order notifications sent for {order.order_number} ({len(admins)} admins)"
        )

    # ========================================
    # PAYMENT REMINDER EMAILS
    # ========================================

    @staticmethod
    def notify_payment_reminder(order):
        """
        Wysyła przypomnienie o niezapłaconych etapach zamówienia.
        Automatycznie wykrywa które etapy wymagają płatności.

        Args:
            order: obiekt Order

        Returns:
            bool: True jeśli wysłano (były niezapłacone etapy), False w przeciwnym razie
        """
        from utils.email_sender import send_payment_reminder_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send payment reminder for {order.order_number}: no email")
            return False

        # Zbierz niezapłacone etapy
        unpaid_stages = []

        # E1: Produkt
        product_status = order.product_payment_status
        if product_status in ('none', 'rejected'):
            unpaid_stages.append({
                'name': 'Płatność za produkt',
                'amount': float(order.effective_total or order.total_amount or 0),
                'status': product_status
            })

        # E2: Wysyłka KR (tylko 4-płatnościowe)
        if order.payment_stages == 4 and order.proxy_shipping_cost and float(order.proxy_shipping_cost) > 0:
            stage_2_status = order.stage_2_status
            if stage_2_status in ('none', 'rejected'):
                unpaid_stages.append({
                    'name': 'Wysyłka z Korei',
                    'amount': float(order.proxy_shipping_cost),
                    'status': stage_2_status
                })

        # E3: Cło/VAT
        if order.customs_vat_sale_cost and float(order.customs_vat_sale_cost) > 0:
            stage_3_status = order.stage_3_status
            if stage_3_status in ('none', 'rejected'):
                unpaid_stages.append({
                    'name': 'Cło i VAT',
                    'amount': float(order.customs_vat_sale_cost),
                    'status': stage_3_status
                })

        # E4: Wysyłka krajowa
        if order.shipping_cost and float(order.shipping_cost) > 0:
            stage_4_status = order.stage_4_status
            if stage_4_status in ('none', 'rejected'):
                unpaid_stages.append({
                    'name': 'Wysyłka krajowa',
                    'amount': float(order.shipping_cost),
                    'status': stage_4_status
                })

        if not unpaid_stages:
            return False

        # URL różny dla gości i zalogowanych
        if order.is_guest_order and order.guest_view_token:
            order_detail_url = url_for('orders.guest_track',
                                       token=order.guest_view_token, _external=True)
        else:
            order_detail_url = url_for('orders.client_detail',
                                       order_id=order.id, _external=True)

        try:
            send_payment_reminder_email(
                user_email=email,
                user_name=order.customer_name,
                order_number=order.order_number,
                unpaid_stages=unpaid_stages,
                order_detail_url=order_detail_url
            )
            current_app.logger.info(
                f"Payment reminder sent for {order.order_number} to {email} "
                f"({len(unpaid_stages)} unpaid stages)"
            )
            return True
        except Exception as e:
            current_app.logger.error(f"Failed to send payment reminder for {order.order_number}: {e}")
            return False

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
        from utils.email_sender import send_payment_approved_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send payment approved email for {order.order_number}: no email")
            return

        # URL różny dla gości i zalogowanych
        if order.is_guest_order and order.guest_view_token:
            order_detail_url = url_for('orders.guest_track',
                                       token=order.guest_view_token, _external=True)
        else:
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
        from utils.email_sender import send_payment_rejected_email

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send payment rejected email for {order.order_number}: no email")
            return

        try:
            # URL różny dla gości i zalogowanych
            if order.is_guest_order and order.guest_view_token:
                upload_url = url_for('orders.guest_track',
                                     token=order.guest_view_token, _external=True)
            else:
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
