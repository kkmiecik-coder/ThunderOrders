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

# Retry configuration for transient SMTP errors (e.g. 454 rate limit)
SMTP_MAX_RETRIES = 3
SMTP_RETRY_DELAYS = [5, 15, 30]  # seconds between retries (exponential backoff)

# SMTP error codes that are transient and worth retrying
SMTP_RETRYABLE_CODES = {421, 450, 451, 452, 454}


def _is_retryable_smtp_error(exc):
    """Check if an SMTP exception is transient and worth retrying."""
    import smtplib
    if isinstance(exc, (smtplib.SMTPServerDisconnected, ConnectionError, OSError)):
        return True
    if isinstance(exc, smtplib.SMTPSenderRefused):
        # SMTPSenderRefused stores code in .smtp_code
        return exc.smtp_code in SMTP_RETRYABLE_CODES
    if isinstance(exc, smtplib.SMTPResponseException):
        return exc.smtp_code in SMTP_RETRYABLE_CODES
    return False


def send_async_email(app, msg):
    """Wysyła email asynchronicznie w osobnym wątku z retry dla błędów tymczasowych"""
    recipient = msg.recipients[0] if msg.recipients else 'unknown'
    subject = msg.subject or 'no subject'
    logger.info(f"[EMAIL-THREAD] Starting SMTP send to={recipient}, subject='{subject}'")
    start_time = time.time()

    for attempt in range(1, SMTP_MAX_RETRIES + 1):
        try:
            with app.app_context():
                mail.send(msg)
            elapsed = time.time() - start_time
            logger.info(f"[EMAIL-THREAD] SUCCESS to={recipient}, subject='{subject}', took={elapsed:.2f}s" +
                        (f" (attempt {attempt})" if attempt > 1 else ""))
            return
        except Exception as e:
            elapsed = time.time() - start_time
            if attempt < SMTP_MAX_RETRIES and _is_retryable_smtp_error(e):
                delay = SMTP_RETRY_DELAYS[attempt - 1]
                logger.warning(f"[EMAIL-THREAD] RETRY {attempt}/{SMTP_MAX_RETRIES} to={recipient}, "
                               f"error={type(e).__name__}: {e}, retrying in {delay}s")
                time.sleep(delay)
            else:
                logger.error(f"[EMAIL-THREAD] FAILED to={recipient}, subject='{subject}', "
                             f"took={elapsed:.2f}s, attempt={attempt}, error={type(e).__name__}: {e}")


def send_async_email_batch(app, messages):
    """Wysyła wiele emaili w jednym wątku, reużywając połączenie SMTP"""
    import smtplib
    total = len(messages)
    logger.info(f"[EMAIL-BATCH] Starting batch send of {total} emails")
    start_time = time.time()
    sent = 0
    failed = 0

    try:
        with app.app_context():
            with mail.connect() as conn:
                for i, msg in enumerate(messages):
                    recipient = msg.recipients[0] if msg.recipients else 'unknown'
                    msg_sent = False
                    for attempt in range(1, SMTP_MAX_RETRIES + 1):
                        try:
                            conn.send(msg)
                            sent += 1
                            msg_sent = True
                            logger.info(f"[EMAIL-BATCH] {i+1}/{total} SUCCESS to={recipient}" +
                                        (f" (attempt {attempt})" if attempt > 1 else ""))
                            break
                        except Exception as e:
                            if attempt < SMTP_MAX_RETRIES and _is_retryable_smtp_error(e):
                                delay = SMTP_RETRY_DELAYS[attempt - 1]
                                logger.warning(f"[EMAIL-BATCH] {i+1}/{total} RETRY {attempt}/{SMTP_MAX_RETRIES} "
                                               f"to={recipient}, error={type(e).__name__}: {e}, retrying in {delay}s")
                                time.sleep(delay)
                            else:
                                failed += 1
                                logger.error(f"[EMAIL-BATCH] {i+1}/{total} FAILED to={recipient}, "
                                             f"attempt={attempt}, error={type(e).__name__}: {e}")
                                break
                    # Delay between emails to avoid SMTP rate limits
                    # 2s gap keeps us under typical provider limits (~30 emails/min)
                    if i < total - 1:
                        time.sleep(2)
    except Exception as e:
        logger.error(f"[EMAIL-BATCH] Connection error: {type(e).__name__}: {e}")

    elapsed = time.time() - start_time
    logger.info(f"[EMAIL-BATCH] Batch complete: {sent} sent, {failed} failed, took={elapsed:.2f}s")


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


def send_email_sync(to, subject, template, **kwargs):
    """
    Wysyła email SYNCHRONICZNIE - czeka na wynik SMTP.
    Używaj dla krytycznych maili (weryfikacja, reset hasła) gdzie musimy
    wiedzieć czy email dotarł do serwera SMTP.

    Returns:
        bool: True jeśli SMTP przyjął email, False w przypadku błędu
    """
    app = current_app._get_current_object()

    msg = Message(
        subject=subject,
        recipients=[to],
        sender=app.config['MAIL_DEFAULT_SENDER']
    )

    try:
        msg.html = render_template(f'emails/{template}.html', **kwargs)

        try:
            msg.body = render_template(f'emails/{template}.txt', **kwargs)
        except Exception:
            msg.body = "Sprawdź email w kliencie obsługującym HTML."

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

        logger.info(f"[EMAIL-SYNC] Sending to={to}, subject='{subject}'")
        start_time = time.time()

        for attempt in range(1, SMTP_MAX_RETRIES + 1):
            try:
                mail.send(msg)
                elapsed = time.time() - start_time
                logger.info(f"[EMAIL-SYNC] SUCCESS to={to}, took={elapsed:.2f}s" +
                            (f" (attempt {attempt})" if attempt > 1 else ""))
                return True
            except Exception as e:
                if attempt < SMTP_MAX_RETRIES and _is_retryable_smtp_error(e):
                    delay = SMTP_RETRY_DELAYS[attempt - 1]
                    logger.warning(f"[EMAIL-SYNC] RETRY {attempt}/{SMTP_MAX_RETRIES} to={to}, "
                                   f"error={type(e).__name__}: {e}, retrying in {delay}s")
                    time.sleep(delay)
                else:
                    elapsed = time.time() - start_time
                    logger.error(f"[EMAIL-SYNC] FAILED to={to}, subject='{subject}', "
                                 f"took={elapsed:.2f}s, attempt={attempt}, error={type(e).__name__}: {e}")
                    return False

        return False

    except Exception as e:
        logger.error(f"[EMAIL-SYNC] Preparation FAILED to={to}, subject='{subject}', error={type(e).__name__}: {e}")
        return False


def prepare_email(to, subject, template, **kwargs):
    """
    Przygotowuje obiekt Message bez wysyłania.
    Używane przez send_email_batch() do batch'owego wysyłania.

    Returns:
        Message lub None w przypadku błędu
    """
    app = current_app._get_current_object()

    msg = Message(
        subject=subject,
        recipients=[to],
        sender=app.config['MAIL_DEFAULT_SENDER']
    )

    try:
        msg.html = render_template(f'emails/{template}.html', **kwargs)

        try:
            msg.body = render_template(f'emails/{template}.txt', **kwargs)
        except:
            msg.body = f"Sprawdź email w kliencie obsługującym HTML."

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

        return msg

    except Exception as e:
        logger.error(f"[EMAIL] Prepare FAILED to={to}, subject='{subject}', error={type(e).__name__}: {e}")
        return None


def send_email_batch(messages):
    """
    Wysyła listę przygotowanych Message w jednym wątku z jednym połączeniem SMTP.

    Args:
        messages (list): Lista obiektów Message (z prepare_email())
    """
    messages = [m for m in messages if m is not None]
    if not messages:
        return

    app = current_app._get_current_object()
    logger.info(f"[EMAIL-BATCH] Queuing batch of {len(messages)} emails")
    Thread(
        target=send_async_email_batch,
        args=(app, messages),
        name="email-batch"
    ).start()


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


def send_order_confirmation_email(user_email, user_name, order_number, order_total, order_items, is_offer=False, payment_stages=None):
    """
    Wysyła potwierdzenie zamówienia do klienta

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia (np. ST/00000001)
        order_total (float): Łączna kwota zamówienia
        order_items (list): Lista produktów w zamówieniu
        is_offer (bool): Czy zamówienie ze strony sprzedaży
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
        is_offer=is_offer,
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


def send_supplier_ordered_email(user_email, user_name, order_number, order_detail_url):
    """Wysyła email o zamówieniu produktów u dostawcy."""
    return send_email(
        to=user_email,
        subject=f'Zamówiliśmy Twoje produkty u dostawcy ({order_number}) - ThunderOrders',
        template='order_supplier_ordered',
        user_name=user_name,
        order_number=order_number,
        order_detail_url=order_detail_url
    )


def send_supplier_cancelled_email(user_email, user_name, order_number, order_detail_url):
    """Wysyła email o anulowaniu zamówienia u dostawcy."""
    return send_email(
        to=user_email,
        subject=f'Anulowano zamówienie u dostawcy ({order_number}) - ThunderOrders',
        template='order_supplier_cancelled',
        user_name=user_name,
        order_number=order_number,
        order_detail_url=order_detail_url
    )


def send_offer_closure_email(customer_email, customer_name, page_name, items,
                                fulfilled_items=None, fulfilled_total=0, shipping_cost=0,
                                grand_total=0, order_number='', payment_methods=None,
                                upload_payment_url=''):
    """
    Wysyła email z podsumowaniem zamówienia po zamknięciu strony sprzedaży.

    Email zawiera listę wszystkich produktów z informacją:
    - Zostanie zamówiony (produkt załapał się do kompletu)
    - Nie załapał się do kompletu (produkt przepadł)
    + Informacje finansowe i dane do przelewu

    Args:
        customer_email (str): Email klienta
        customer_name (str): Imię klienta
        page_name (str): Nazwa strony sprzedaży
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
        template='offer_closure',
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
    Wysyła email o anulowaniu zamówienia.

    Args:
        user_email: Email odbiorcy
        user_name: Imię odbiorcy
        order_number: Numer zamówienia (np. EX/00000123)
        page_name: Nazwa strony sprzedaży
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
                                      order_number, stage_names, review_url):
    """
    Wysyła email do admina o nowym potwierdzeniu płatności do weryfikacji.

    Args:
        admin_email (str): Email admina
        customer_name (str): Imię klienta
        customer_email (str): Email klienta
        order_number (str): Numer zamówienia
        stage_names (str): Nazwy etapów (np. 'Płatność za produkt, Cło i VAT')
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
        review_url=review_url
    )


def send_admin_new_order_email(admin_email, customer_name, customer_email,
                               order_number, page_name, items,
                               order_total, order_detail_url, created_at):
    """
    Wysyła email do admina o nowym zamówieniu ze strony sprzedaży.

    Args:
        admin_email (str): Email admina
        customer_name (str): Imię klienta
        customer_email (str): Email klienta
        order_number (str): Numer zamówienia
        page_name (str): Nazwa strony sprzedaży
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


def send_back_in_stock_email(email, product_name, product_image_url, offer_page_name, offer_page_url):
    """
    Wysyła powiadomienie o powrocie produktu do dostępności na stronie sprzedaży.

    Args:
        email (str): Email odbiorcy
        product_name (str): Nazwa produktu
        product_image_url (str): URL do zdjęcia produktu (lub None)
        offer_page_name (str): Nazwa strony sprzedaży
        offer_page_url (str): URL do strony sprzedaży

    Returns:
        bool: True jeśli email został wysłany
    """
    return send_email(
        to=email,
        subject=f'{product_name} jest znów dostępny! - ThunderOrders',
        template='back_in_stock',
        product_name=product_name,
        product_image_url=product_image_url,
        offer_page_name=offer_page_name,
        offer_page_url=offer_page_url
    )


def send_sale_end_date_changed_email(user_email, user_name, page_name,
                                      old_ends_at_display, new_ends_at_display,
                                      page_url):
    """
    Wysyła e-mail o zmianie daty zakończenia sprzedaży strony.

    Args:
        user_email (str): Adres e-mail odbiorcy
        user_name (str): Imię odbiorcy (lub 'Kliencie' jeśli brak)
        page_name (str): Nazwa strony sprzedaży
        old_ends_at_display (str): Poprzednia data sformatowana po polsku
                                   (lub 'bez limitu czasowego' jeśli brak)
        new_ends_at_display (str): Nowa data sformatowana po polsku
                                   (lub 'bez limitu czasowego' jeśli brak)
        page_url (str): Pełny URL strony sprzedaży

    Returns:
        bool: True jeśli wysłano, False w przypadku błędu
    """
    if not user_email:
        logger.warning("Cannot send sale end date changed email: no email address")
        return False

    try:
        return send_email(
            to=user_email,
            subject=f'Zaktualizowano datę zakończenia sprzedaży — {page_name}',
            template='sale_end_date_changed',
            user_name=user_name,
            page_name=page_name,
            old_ends_at_display=old_ends_at_display,
            new_ends_at_display=new_ends_at_display,
            page_url=page_url,
        )
    except Exception as e:
        logger.error(f"Failed to send sale end date changed email to {user_email}: {e}")
        return False


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


def send_payment_reminder_email(user_email, user_name, order_number, unpaid_stages, order_detail_url, payment_deadline=None, reminder_context='before_deadline'):
    """Wysyła email z przypomnieniem o niezapłaconych etapach zamówienia."""
    return send_email(
        to=user_email,
        subject=f'Przypomnienie o płatności - {order_number} - ThunderOrders',
        template='payment_reminder',
        user_name=user_name,
        order_number=order_number,
        unpaid_stages=unpaid_stages,
        order_detail_url=order_detail_url,
        payment_deadline=payment_deadline,
        reminder_context=reminder_context
    )


def send_deadline_exceeded_email(to_email, page_name, payment_deadline, orders):
    """Wysyła email do admina o przekroczonym terminie płatności."""
    return send_email(
        to=to_email,
        subject=f'Przekroczony termin płatności - {page_name} - ThunderOrders',
        template='payment_deadline_exceeded',
        page_name=page_name,
        payment_deadline=payment_deadline,
        orders=orders
    )


def send_new_offer_page_email(user_email, user_name, page_name, page_url):
    """
    Wysyła email z powiadomieniem o nowej stronie sprzedaży (nowy drop).

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        page_name (str): Nazwa strony sprzedaży
        page_url (str): URL do strony sprzedaży
    """
    return send_email(
        to=user_email,
        subject=f'Nowy drop: {page_name} - ThunderOrders',
        template='new_offer_page',
        user_name=user_name,
        page_name=page_name,
        page_url=page_url
    )


def send_account_deletion_requested_email(user_email, user_name):
    """
    Wysyła email potwierdzający żądanie usunięcia konta (RODO art. 17).
    """
    return send_email(
        to=user_email,
        subject='Żądanie usunięcia konta - ThunderOrders',
        template='account_deletion_requested',
        user_name=user_name
    )


def send_account_deactivated_email(user_email, user_name, reason=''):
    """
    Wysyła email informujący klienta o dezaktywacji konta.

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        reason (str): Powód dezaktywacji (opcjonalny)

    Returns:
        bool: True jeśli email został wysłany
    """
    return send_email(
        to=user_email,
        subject='Konto dezaktywowane - ThunderOrders',
        template='account_deactivated',
        user_name=user_name,
        reason=reason
    )


def send_packing_photo_email(user_email, user_name, order_number, photo_path):
    """
    Wysyła email ze zdjęciem spakowanej paczki do klienta.

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia
        photo_path (str): Ścieżka do zdjęcia paczki (relatywna od static/)
    """
    app = current_app._get_current_object()

    msg = Message(
        subject=f'Twoja paczka jest gotowa! - {order_number} - ThunderOrders',
        recipients=[user_email],
        sender=app.config['MAIL_DEFAULT_SENDER']
    )

    try:
        msg.html = render_template(
            'emails/packing_photo.html',
            user_name=user_name,
            order_number=order_number,
        )

        msg.body = f"Sprawdź email w kliencie obsługującym HTML."

        # Logo inline attachment (CID)
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

        # Packing photo inline attachment (CID)
        full_photo_path = os.path.join(app.root_path, 'static', photo_path)
        if os.path.exists(full_photo_path):
            with open(full_photo_path, 'rb') as fp:
                photo_data = fp.read()
            msg.attach(
                filename='packing_photo.jpg',
                content_type='image/jpeg',
                data=photo_data,
                disposition='inline',
                headers=[('Content-ID', '<packing_photo@thunderorders>')],
            )

        logger.info(f"[EMAIL] Queuing packing photo email to={user_email}, order={order_number}")
        Thread(
            target=send_async_email,
            args=(app, msg),
            name=f"email-packing-{user_email}"
        ).start()

        return True

    except Exception as e:
        logger.error(f"[EMAIL] Packing photo email FAILED to={user_email}, error={type(e).__name__}: {e}")
        return False


def send_achievement_granted_email(user_email, user_name, achievement_name,
                                   achievement_description, achievement_slug,
                                   gallery_url):
    """
    Wysyła email po ręcznym przyznaniu specjalnej odznaki przez admina.

    Args:
        user_email (str): Email odbiorcy
        user_name (str): Imię klienta
        achievement_name (str): Nazwa przyznanej odznaki
        achievement_description (str): Krótki opis odznaki
        achievement_slug (str): Slug odznaki (np. do deeplinka w przyszłości)
        gallery_url (str): URL do galerii odznak klienta

    Returns:
        bool: True jeśli email został wysłany
    """
    return send_email(
        to=user_email,
        subject=f'🎖️ Otrzymałeś specjalną odznakę: {achievement_name}',
        template='achievement_granted',
        user_name=user_name,
        achievement_name=achievement_name,
        achievement_description=achievement_description,
        achievement_slug=achievement_slug,
        gallery_url=gallery_url,
    )
