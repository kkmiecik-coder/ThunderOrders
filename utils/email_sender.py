"""
Email Sender Module
Funkcje do wysyłania emaili (rejestracja, reset hasła, powiadomienia)
"""

from flask import current_app, render_template
from flask_mail import Message
from extensions import mail
from threading import Thread
import os
import time
import logging

logger = logging.getLogger(__name__)


def send_async_email(app, msg):
    """Wysyła email asynchronicznie w osobnym wątku"""
    recipient = msg.recipients[0] if msg.recipients else 'unknown'
    subject = msg.subject or 'no subject'
    logger.info(f"[EMAIL-THREAD] Starting SMTP send to={recipient}, subject='{subject}'")
    start_time = time.time()

    try:
        with app.app_context():
            mail.send(msg)
        elapsed = time.time() - start_time
        logger.info(f"[EMAIL-THREAD] SUCCESS to={recipient}, subject='{subject}', took={elapsed:.2f}s")
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[EMAIL-THREAD] FAILED to={recipient}, subject='{subject}', took={elapsed:.2f}s, error={type(e).__name__}: {e}")


def send_email(to, subject, template, **kwargs):
    """
    Wysyła email z templatem HTML

    Args:
        to (str): Adres odbiorcy
        subject (str): Temat emaila
        template (str): Ścieżka do template HTML (bez .html)
        **kwargs: Dodatkowe zmienne przekazywane do template

    Returns:
        bool: True jeśli email został wysłany, False w przypadku błędu
    """
    app = current_app._get_current_object()

    msg = Message(
        subject=subject,
        recipients=[to],
        sender=app.config['MAIL_DEFAULT_SENDER']
    )

    try:
        # Renderuj HTML template
        msg.html = render_template(f'emails/{template}.html', **kwargs)

        # Opcjonalnie: text fallback (dla klientów bez HTML)
        try:
            msg.body = render_template(f'emails/{template}.txt', **kwargs)
        except:
            # Jeśli nie ma .txt template, użyj prostej wersji tekstowej
            msg.body = f"Sprawdź email w kliencie obsługującym HTML."

        # Dołącz logo jako inline attachment (CID)
        # WAŻNE: Logo musi być w formacie PNG, nie SVG (dla kompatybilności z email klientami)
        logo_path = os.path.join(app.root_path, 'static', 'img', 'icons', 'logo-full-black-email.png')
        if os.path.exists(logo_path):
            with app.open_resource(logo_path, 'rb') as fp:
                msg.attach(
                    filename='logo.png',
                    content_type='image/png',
                    data=fp.read(),
                    disposition='inline',
                    headers=[('Content-ID', '<logo@thunderorders>')],
                )

        # Wysyłka asynchroniczna (nie blokuje aplikacji)
        logger.info(f"[EMAIL] Queuing email to={to}, subject='{subject}', smtp={app.config.get('MAIL_SERVER')}:{app.config.get('MAIL_PORT')}")
        Thread(
            target=send_async_email,
            args=(app, msg),
            name=f"email-{to}"
        ).start()
        logger.info(f"[EMAIL] Thread started for to={to}")

        return True

    except Exception as e:
        logger.error(f"[EMAIL] Preparation FAILED to={to}, subject='{subject}', error={type(e).__name__}: {e}")
        return False


def send_verification_email(user_email, verification_token, user_name):
    """
    Wysyła email weryfikacyjny po rejestracji (legacy - stary system z linkami)

    Args:
        user_email (str): Email użytkownika
        verification_token (str): Token weryfikacyjny
        user_name (str): Imię użytkownika
    """
    from flask import url_for
    verification_url = url_for('auth.verify_email', token=verification_token, _external=True)

    return send_email(
        to=user_email,
        subject='Potwierdź swój adres email - ThunderOrders',
        template='verify_email',
        user_name=user_name,
        verification_url=verification_url
    )


def send_welcome_email(user_email, user_name):
    """
    Wysyła email powitalny po pomyślnej weryfikacji konta.

    Args:
        user_email (str): Email użytkownika
        user_name (str): Imię użytkownika
    """
    from flask import url_for
    login_url = url_for('auth.login', _external=True)

    return send_email(
        to=user_email,
        subject='Witamy w ThunderOrders!',
        template='welcome',
        user_name=user_name,
        login_url=login_url
    )


def send_verification_code_email(user_email, verification_code, user_name):
    """
    Wysyła email z 6-cyfrowym kodem weryfikacyjnym

    Args:
        user_email (str): Email użytkownika
        verification_code (str): 6-cyfrowy kod weryfikacyjny
        user_name (str): Imię użytkownika

    Returns:
        bool: True jeśli email został wysłany
    """
    return send_email(
        to=user_email,
        subject='Twój kod weryfikacyjny - ThunderOrders',
        template='verification_code',
        user_name=user_name,
        verification_code=verification_code
    )


def send_password_reset_email(user_email, reset_token, user_name):
    """
    Wysyła email z linkiem do resetowania hasła

    Args:
        user_email (str): Email użytkownika
        reset_token (str): Token resetu hasła
        user_name (str): Imię użytkownika
    """
    from flask import url_for
    reset_url = url_for('auth.reset_password', token=reset_token, _external=True)

    return send_email(
        to=user_email,
        subject='Reset hasła - ThunderOrders',
        template='reset_password',
        user_name=user_name,
        reset_url=reset_url
    )


def send_order_confirmation_email(user_email, user_name, order_number, order_total, order_items, is_guest=False, guest_view_token=None, is_exclusive=False, payment_stages=None):
    """
    Wysyła potwierdzenie zamówienia do klienta

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia (np. ST/00000001)
        order_total (float): Łączna kwota zamówienia
        order_items (list): Lista produktów w zamówieniu
        is_guest (bool): Czy zamówienie złożone przez gościa
        guest_view_token (str): Token do podglądu zamówienia dla gościa
        is_exclusive (bool): Czy zamówienie exclusive
        payment_stages (int): Liczba etapów płatności (3 lub 4)
    """
    return send_email(
        to=user_email,
        subject=f'Potwierdzenie zamówienia {order_number} - ThunderOrders',
        template='order_confirmation',
        user_name=user_name,
        order_number=order_number,
        order_total=order_total,
        order_items=order_items,
        is_guest=is_guest,
        guest_view_token=guest_view_token,
        is_exclusive=is_exclusive,
        payment_stages=payment_stages
    )


def send_order_status_change_email(user_email, user_name, order_number, old_status, new_status):
    """
    Wysyła powiadomienie o zmianie statusu zamówienia

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia
        old_status (str): Poprzedni status
        new_status (str): Nowy status
    """
    return send_email(
        to=user_email,
        subject=f'Zmiana statusu zamówienia {order_number} - ThunderOrders',
        template='order_status_change',
        user_name=user_name,
        order_number=order_number,
        old_status=old_status,
        new_status=new_status
    )


def send_exclusive_closure_email(customer_email, customer_name, page_name, items,
                                fulfilled_items=None, fulfilled_total=0, shipping_cost=0,
                                grand_total=0, order_number='', payment_methods=None,
                                upload_payment_url=''):
    """
    Wysyła email z podsumowaniem zamówienia po zamknięciu strony Exclusive.

    Email zawiera listę wszystkich produktów z informacją:
    - Zostanie zamówiony (produkt załapał się do kompletu)
    - Nie załapał się do kompletu (produkt przepadł)
    + Informacje finansowe i dane do przelewu

    Args:
        customer_email (str): Email klienta
        customer_name (str): Imię klienta
        page_name (str): Nazwa strony Exclusive
        items (list): Lista słowników z kluczami:
            - product_name (str): Nazwa produktu
            - quantity (int): Zamówiona ilość
            - is_fulfilled (bool): Czy produkt zostanie zrealizowany
        fulfilled_items (list): Lista zrealizowanych produktów
        fulfilled_total (float): Suma zrealizowanych produktów
        shipping_cost (float): Koszt wysyłki
        grand_total (float): Suma całkowita (produkty + wysyłka)
        order_number (str): Numer zamówienia
        payment_methods (list): Lista metod płatności
        upload_payment_url (str): URL do wgrania dowodu wpłaty
    """
    return send_email(
        to=customer_email,
        subject=f'Podsumowanie zamówienia - {page_name} - ThunderOrders',
        template='exclusive_closure',
        customer_name=customer_name,
        page_name=page_name,
        items=items,
        fulfilled_items=fulfilled_items or [],
        fulfilled_total=fulfilled_total,
        shipping_cost=shipping_cost,
        grand_total=grand_total,
        order_number=order_number,
        payment_methods=payment_methods or [],
        upload_payment_url=upload_payment_url
    )


def send_order_cancelled_email(user_email, user_name, order_number, page_name,
                               cancelled_items, reason=''):
    """
    Wysyła email o anulowaniu zamówienia exclusive.

    Args:
        user_email: Email odbiorcy
        user_name: Imię odbiorcy
        order_number: Numer zamówienia (np. EX/00000123)
        page_name: Nazwa strony Exclusive
        cancelled_items: Lista dict z kluczami: name, quantity, image_url
        reason: Powód anulowania (opcjonalny)

    Returns:
        True jeśli wysłano, False w przeciwnym razie
    """
    if not user_email:
        logger.warning("Cannot send cancellation email: no email address")
        return False

    try:
        subject = f'Zamówienie {order_number} zostało anulowane'

        return send_email(
            to=user_email,
            subject=subject,
            template='order_cancelled',
            customer_name=user_name,
            order_number=order_number,
            page_name=page_name,
            cancelled_items=cancelled_items,
            reason=reason
        )
    except Exception as e:
        logger.error(f"Error sending order cancelled email to {user_email}: {e}")
        return False


def send_payment_approved_email(user_email, user_name, order_number, amount, order_detail_url, stage_name='za produkt'):
    """
    Wysyła email o zaakceptowaniu potwierdzenia płatności

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia
        amount (float): Kwota płatności
        order_detail_url (str): URL do szczegółów zamówienia
        stage_name (str): Nazwa etapu płatności (np. 'Płatność za produkt', 'Wysyłka z Korei')
    """
    return send_email(
        to=user_email,
        subject=f'Płatność zatwierdzona ({stage_name}) - {order_number} - ThunderOrders',
        template='payment_approved',
        user_name=user_name,
        order_number=order_number,
        amount=amount,
        order_detail_url=order_detail_url,
        stage_name=stage_name
    )


def send_payment_rejected_email(user_email, user_name, order_number, amount, rejection_reason, upload_url, stage_name='za produkt'):
    """
    Wysyła email o odrzuceniu potwierdzenia płatności

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia
        amount (float): Kwota płatności
        rejection_reason (str): Powód odrzucenia
        upload_url (str): URL do ponownego wgrania potwierdzenia
        stage_name (str): Nazwa etapu płatności (np. 'Płatność za produkt', 'Wysyłka z Korei')
    """
    return send_email(
        to=user_email,
        subject=f'Płatność odrzucona ({stage_name}) - {order_number} - ThunderOrders',
        template='payment_rejected',
        user_name=user_name,
        order_number=order_number,
        amount=amount,
        rejection_reason=rejection_reason,
        upload_url=upload_url,
        stage_name=stage_name
    )


def send_admin_payment_uploaded_email(admin_email, customer_name, customer_email,
                                      order_number, stage_names, is_guest, review_url):
    """
    Wysyła email do admina o nowym potwierdzeniu płatności do weryfikacji.

    Args:
        admin_email (str): Email admina
        customer_name (str): Imię klienta
        customer_email (str): Email klienta
        order_number (str): Numer zamówienia
        stage_names (str): Nazwy etapów (np. 'Płatność za produkt, Cło i VAT')
        is_guest (bool): Czy klient jest gościem
        review_url (str): URL do strony weryfikacji płatności
    """
    return send_email(
        to=admin_email,
        subject=f'Nowe potwierdzenie płatności - {order_number} - ThunderOrders',
        template='admin_payment_uploaded',
        customer_name=customer_name,
        customer_email=customer_email,
        order_number=order_number,
        stage_names=stage_names,
        is_guest=is_guest,
        review_url=review_url
    )


def send_admin_new_order_email(admin_email, customer_name, customer_email,
                               order_number, page_name, is_guest, items,
                               order_total, order_detail_url, created_at):
    """
    Wysyła email do admina o nowym zamówieniu exclusive.

    Args:
        admin_email (str): Email admina
        customer_name (str): Imię klienta
        customer_email (str): Email klienta
        order_number (str): Numer zamówienia
        page_name (str): Nazwa strony Exclusive
        is_guest (bool): Czy klient jest gościem
        items (list): Lista dict z product_name, quantity, price, total
        order_total (float): Suma zamówienia
        order_detail_url (str): URL do szczegółów zamówienia (admin)
        created_at (str): Data złożenia zamówienia (sformatowana)
    """
    return send_email(
        to=admin_email,
        subject=f'Nowe zamówienie {order_number} - {page_name}',
        template='admin_new_order',
        customer_name=customer_name,
        customer_email=customer_email,
        order_number=order_number,
        page_name=page_name,
        is_guest=is_guest,
        items=items,
        order_total=order_total,
        order_detail_url=order_detail_url,
        created_at=created_at
    )


def send_order_completed_email(user_email, user_name, order_number, order_items,
                                products_total, proxy_shipping, customs_vat,
                                shipping_cost, grand_total, order_detail_url):
    """
    Wysyła email podsumowujący zakończone zamówienie (status: dostarczone).

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia
        order_items (list): Lista dict z product_name, quantity, total
        products_total (float): Suma za produkty
        proxy_shipping (float): Koszt wysyłki proxy
        customs_vat (float): Koszt cła/VAT
        shipping_cost (float): Koszt wysyłki krajowej
        grand_total (float): Suma całkowita
        order_detail_url (str): URL do szczegółów zamówienia
    """
    return send_email(
        to=user_email,
        subject=f'Zamówienie {order_number} zrealizowane - ThunderOrders',
        template='order_completed',
        user_name=user_name,
        order_number=order_number,
        order_items=order_items,
        products_total=products_total,
        proxy_shipping=proxy_shipping,
        customs_vat=customs_vat,
        shipping_cost=shipping_cost,
        grand_total=grand_total,
        order_detail_url=order_detail_url
    )


def send_back_in_stock_email(email, product_name, product_image_url, exclusive_page_name, exclusive_page_url):
    """
    Wysyła powiadomienie o powrocie produktu do dostępności na stronie Exclusive.

    Args:
        email (str): Email odbiorcy
        product_name (str): Nazwa produktu
        product_image_url (str): URL do zdjęcia produktu (lub None)
        exclusive_page_name (str): Nazwa strony Exclusive
        exclusive_page_url (str): URL do strony Exclusive

    Returns:
        bool: True jeśli email został wysłany
    """
    return send_email(
        to=email,
        subject=f'{product_name} jest znów dostępny! - ThunderOrders',
        template='back_in_stock',
        product_name=product_name,
        product_image_url=product_image_url,
        exclusive_page_name=exclusive_page_name,
        exclusive_page_url=exclusive_page_url
    )


def send_tracking_number_email(user_email, user_name, order_number, tracking_number,
                                courier_name, tracking_url=None):
    """
    Wysyła email z informacją o dodaniu numeru śledzenia przesyłki.

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia
        tracking_number (str): Numer śledzenia
        courier_name (str): Nazwa kuriera (display name)
        tracking_url (str): URL do śledzenia przesyłki (opcjonalny)
    """
    return send_email(
        to=user_email,
        subject=f'Przesyłka nadana - {order_number} - ThunderOrders',
        template='tracking_added',
        user_name=user_name,
        order_number=order_number,
        tracking_number=tracking_number,
        courier_name=courier_name,
        tracking_url=tracking_url
    )


def send_cost_added_email(user_email, user_name, order_number, cost_type, cost_amount, order_detail_url):
    """
    Wysyła email o dodaniu kosztu do zamówienia (wysyłka proxy, cło/VAT lub wysyłka krajowa).

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia
        cost_type (str): Typ kosztu ('proxy_shipping', 'customs_vat' lub 'domestic_shipping')
        cost_amount (float): Kwota kosztu
        order_detail_url (str): URL do szczegółów zamówienia
    """
    if cost_type == 'proxy_shipping':
        subject = f'Koszt wysyłki z proxy - {order_number} - ThunderOrders'
    elif cost_type == 'domestic_shipping':
        subject = f'Koszt wysyłki krajowej - {order_number} - ThunderOrders'
    else:
        subject = f'Koszt cła i VAT - {order_number} - ThunderOrders'

    return send_email(
        to=user_email,
        subject=subject,
        template='cost_added',
        user_name=user_name,
        order_number=order_number,
        cost_type=cost_type,
        cost_amount=cost_amount,
        order_detail_url=order_detail_url
    )


def send_shipping_request_created_email(user_email, user_name, request_number,
                                         orders, delivery_method_display,
                                         full_address, shipping_requests_url):
    """
    Wysyła potwierdzenie utworzenia zlecenia wysyłki.

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        request_number (str): Numer zlecenia (np. WYS/000001)
        orders (list): Lista obiektów Order
        delivery_method_display (str): Wyświetlana nazwa metody dostawy
        full_address (str): Pełny adres dostawy
        shipping_requests_url (str): URL do listy zleceń wysyłki
    """
    return send_email(
        to=user_email,
        subject=f'Zlecenie wysyłki {request_number} - ThunderOrders',
        template='shipping_request_created',
        user_name=user_name,
        request_number=request_number,
        orders=orders,
        delivery_method_display=delivery_method_display,
        full_address=full_address,
        shipping_requests_url=shipping_requests_url
    )


def send_shipping_status_change_email(user_email, user_name, request_number,
                                       old_status_name, new_status_name, new_status_color,
                                       orders, tracking_number=None, courier_name=None,
                                       shipping_requests_url=None):
    """
    Wysyła powiadomienie o zmianie statusu zlecenia wysyłki.

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        request_number (str): Numer zlecenia (np. WYS/000001)
        old_status_name (str): Poprzedni status (display name)
        new_status_name (str): Nowy status (display name)
        new_status_color (str): Kolor badge'a nowego statusu (hex)
        orders (list): Lista obiektów Order powiązanych ze zleceniem
        tracking_number (str): Numer śledzenia przesyłki (opcjonalny)
        courier_name (str): Nazwa kuriera (opcjonalny)
        shipping_requests_url (str): URL do listy zleceń wysyłki
    """
    return send_email(
        to=user_email,
        subject=f'Zmiana statusu zlecenia {request_number} - {new_status_name}',
        template='shipping_status_change',
        user_name=user_name,
        request_number=request_number,
        old_status_name=old_status_name,
        new_status_name=new_status_name,
        new_status_color=new_status_color,
        orders=orders,
        tracking_number=tracking_number,
        courier_name=courier_name,
        shipping_requests_url=shipping_requests_url
    )


def send_payment_reminder_email(user_email, user_name, order_number, unpaid_stages, order_detail_url):
    """
    Wysyła email z przypomnieniem o niezapłaconych etapach zamówienia.

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia
        unpaid_stages (list): Lista dict z kluczami: name, amount, status
        order_detail_url (str): URL do szczegółów zamówienia
    """
    return send_email(
        to=user_email,
        subject=f'Przypomnienie o płatności - {order_number} - ThunderOrders',
        template='payment_reminder',
        user_name=user_name,
        order_number=order_number,
        unpaid_stages=unpaid_stages,
        order_detail_url=order_detail_url
    )


def send_new_exclusive_page_email(user_email, user_name, page_name, page_url):
    """
    Wysyła email z powiadomieniem o nowej stronie Exclusive (nowy drop).

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        page_name (str): Nazwa strony Exclusive
        page_url (str): URL do strony Exclusive
    """
    return send_email(
        to=user_email,
        subject=f'Nowy drop: {page_name} - ThunderOrders',
        template='new_exclusive_page',
        user_name=user_name,
        page_name=page_name,
        page_url=page_url
    )
