"""
Email Sender Module
Funkcje do wysyłania emaili (rejestracja, reset hasła, powiadomienia)
"""

from flask import current_app, render_template
from flask_mail import Message
from extensions import mail
from threading import Thread


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


def send_order_confirmation_email(user_email, user_name, order_number, order_total, order_items):
    """
    Wysyła potwierdzenie zamówienia do klienta

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia (np. ST/00000001)
        order_total (float): Łączna kwota zamówienia
        order_items (list): Lista produktów w zamówieniu
    """
    return send_email(
        to=user_email,
        subject=f'Potwierdzenie zamówienia {order_number} - ThunderOrders',
        template='order_confirmation',
        user_name=user_name,
        order_number=order_number,
        order_total=order_total,
        order_items=order_items
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


def send_exclusive_closure_email(customer_email, customer_name, page_name, items):
    """
    Wysyła email z podsumowaniem zamówienia po zamknięciu strony Exclusive.

    Email zawiera listę wszystkich produktów z informacją:
    - Zostanie zamówiony (produkt załapał się do kompletu)
    - Nie załapał się do kompletu (produkt przepadł)

    Args:
        customer_email (str): Email klienta
        customer_name (str): Imię klienta
        page_name (str): Nazwa strony Exclusive
        items (list): Lista słowników z kluczami:
            - product_name (str): Nazwa produktu
            - quantity (int): Zamówiona ilość
            - is_fulfilled (bool): Czy produkt zostanie zrealizowany
    """
    return send_email(
        to=customer_email,
        subject=f'Podsumowanie zamówienia - {page_name} - ThunderOrders',
        template='exclusive_closure',
        customer_name=customer_name,
        page_name=page_name,
        items=items
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
