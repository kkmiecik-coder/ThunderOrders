"""
Email Sender Module
Funkcje do wysyłania emaili (rejestracja, reset hasła, powiadomienia)
"""

from flask import current_app, render_template
from flask_mail import Message
from extensions import mail
from threading import Thread
import os


def send_async_email(app, msg):
    """Wysyła email asynchronicznie w osobnym wątku"""
    with app.app_context():
        mail.send(msg)


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
        Thread(
            target=send_async_email,
            args=(app, msg)
        ).start()

        return True

    except Exception as e:
        current_app.logger.error(f"Email sending failed: {str(e)}")
        return False


def send_verification_email(user_email, verification_token, user_name):
    """
    Wysyła email weryfikacyjny po rejestracji (legacy - stary system z linkami)

    Args:
        user_email (str): Email użytkownika
        verification_token (str): Token weryfikacyjny
        user_name (str): Imię użytkownika
    """
    verification_url = f"https://thunderorders.cloud/auth/verify-email/{verification_token}"

    return send_email(
        to=user_email,
        subject='Potwierdź swój adres email - ThunderOrders',
        template='verify_email',
        user_name=user_name,
        verification_url=verification_url
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
    reset_url = f"https://thunderorders.cloud/auth/reset-password/{reset_token}"

    return send_email(
        to=user_email,
        subject='Reset hasła - ThunderOrders',
        template='reset_password',
        user_name=user_name,
        reset_url=reset_url
    )


def send_order_confirmation_email(user_email, user_name, order_number, order_total, order_items, is_guest=False, guest_view_token=None):
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
        guest_view_token=guest_view_token
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


def send_payment_proof_approved_email(user_email, user_name, order_number, paid_amount):
    """
    Wysyła email do klienta po zaakceptowaniu dowodu wpłaty.

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia (np. ST/00000001)
        paid_amount (float): Zapłacona kwota
    """
    return send_email(
        to=user_email,
        subject=f'Płatność potwierdzona - {order_number} - ThunderOrders',
        template='payment_proof_approved',
        user_name=user_name,
        order_number=order_number,
        paid_amount=paid_amount
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
