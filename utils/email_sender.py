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

# Odstęp między kolejnymi mailami w batchu — trzyma nas pod limitami dostawcy
# (~30 maili/min u Hostingera).
SMTP_ODSTEP_MIEDZY_MAILAMI = 2


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


# ---------------------------------------------------------------------------
# EmailLog — trwały ślad po wysyłce
#
# Logi tekstowe serwera odpowiadają na pytania o maile tylko dopóki nie zrotują,
# i tylko komuś z dostępem po SSH. Wpis w bazie zostaje i pokazuje się wprost w
# historii zmian zamówienia.
#
# Zapis idzie WŁASNĄ, krótkotrwałą sesją — nigdy przez db.session. Powód jest
# konkretny: część miejsc woła EmailManager mając w sesji niescommitowane zmiany
# (np. _sync_order_statuses_from_shipping_request ustawia order.status i dopiero
# wywołujący robi commit). Gdyby logger commitował na wspólnej sesji, wciągnąłby
# tamte zmiany ze sobą — i rollback po późniejszym błędzie już by ich nie cofnął.
#
# Żadna z tych funkcji nie rzuca wyjątku: log jest dodatkiem do wysyłki, nie
# warunkiem jej powodzenia.
# ---------------------------------------------------------------------------

def _zaloguj_kolejkowanie(to, subject, template, log_context=None):
    """Zakłada wiersz EmailLog w stanie 'queued'. Zwraca id albo None przy błędzie."""
    try:
        from sqlalchemy.orm import Session
        from extensions import db
        from modules.admin.models import EmailLog

        kontekst = log_context or {}
        wpis = EmailLog(
            recipient=(to or '')[:255],
            subject=(subject or '')[:500],
            template=(template or '')[:100] or None,
            entity_type=kontekst.get('entity_type'),
            entity_id=kontekst.get('entity_id'),
            status='queued',
            attempts=0,
        )
        with Session(bind=db.engine) as sesja:
            sesja.add(wpis)
            sesja.commit()
            return wpis.id
    except Exception as e:
        logger.error(f"[EMAIL-LOG] Nie udało się zapisać wpisu 'queued' to={to}: "
                     f"{type(e).__name__}: {e}")
        return None


def _zapisz_wynik_logu(log_id, status, attempts, error=None, duration_ms=None):
    """Domyka wiersz EmailLog wynikiem wysyłki ('sent' albo 'failed')."""
    if not log_id:
        return
    try:
        from sqlalchemy.orm import Session
        from extensions import db
        from modules.admin.models import EmailLog, get_local_now

        with Session(bind=db.engine) as sesja:
            wpis = sesja.get(EmailLog, log_id)
            if wpis is None:
                return
            wpis.status = status
            wpis.attempts = attempts
            wpis.error = (f"{type(error).__name__}: {error}")[:2000] if error else None
            wpis.duration_ms = int(duration_ms) if duration_ms is not None else None
            wpis.sent_at = get_local_now() if status == 'sent' else None
            sesja.commit()
    except Exception as e:
        logger.error(f"[EMAIL-LOG] Nie udało się domknąć wpisu id={log_id}: "
                     f"{type(e).__name__}: {e}")


def send_async_email(app, msg, log_id=None):
    """Wysyła email asynchronicznie w osobnym wątku z retry dla błędów tymczasowych.

    `log_id` wskazuje wiersz EmailLog założony przy kolejkowaniu — domykamy go tu
    wynikiem, bo dopiero ten wątek wie, czy i po ilu próbach mail faktycznie poszedł.
    """
    recipient = msg.recipients[0] if msg.recipients else 'unknown'
    subject = msg.subject or 'no subject'
    logger.info(f"[EMAIL-THREAD] Starting SMTP send to={recipient}, subject='{subject}'")
    start_time = time.time()

    with app.app_context():
        for attempt in range(1, SMTP_MAX_RETRIES + 1):
            try:
                mail.send(msg)
                elapsed = time.time() - start_time
                logger.info(f"[EMAIL-THREAD] SUCCESS to={recipient}, subject='{subject}', took={elapsed:.2f}s" +
                            (f" (attempt {attempt})" if attempt > 1 else ""))
                _zapisz_wynik_logu(log_id, 'sent', attempt, duration_ms=elapsed * 1000)
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
                    _zapisz_wynik_logu(log_id, 'failed', attempt, error=e,
                                       duration_ms=elapsed * 1000)
                    return


def send_async_email_batch(app, messages, odstep_s=SMTP_ODSTEP_MIEDZY_MAILAMI):
    """Wysyła wiele emaili w jednym wątku, reużywając połączenie SMTP.

    `odstep_s` to przerwa między kolejnymi wiadomościami. Zero znaczy „bez
    przerwy" i używa go wyłącznie gałąź testowa send_email_batch() — patrz
    tam uzasadnienie.
    """
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
                    log_id = getattr(msg, '_email_log_id', None)
                    msg_start = time.time()
                    msg_sent = False
                    for attempt in range(1, SMTP_MAX_RETRIES + 1):
                        try:
                            conn.send(msg)
                            sent += 1
                            msg_sent = True
                            logger.info(f"[EMAIL-BATCH] {i+1}/{total} SUCCESS to={recipient}" +
                                        (f" (attempt {attempt})" if attempt > 1 else ""))
                            _zapisz_wynik_logu(log_id, 'sent', attempt,
                                               duration_ms=(time.time() - msg_start) * 1000)
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
                                _zapisz_wynik_logu(log_id, 'failed', attempt, error=e,
                                                   duration_ms=(time.time() - msg_start) * 1000)
                                break
                    # Delay between emails to avoid SMTP rate limits
                    # (SMTP_ODSTEP_MIEDZY_MAILAMI; 0 = wyłączony, patrz odstep_s)
                    if i < total - 1 and odstep_s:
                        time.sleep(odstep_s)
    except Exception as e:
        logger.error(f"[EMAIL-BATCH] Connection error: {type(e).__name__}: {e}")
        # Padło całe połączenie, więc pętla wyżej nie zdążyła domknąć wpisów
        # pozostałych wiadomości. Bez tego zostałyby w bazie jako 'queued' —
        # nie do odróżnienia od maila, który wciąż wisi w wysyłce.
        _oznacz_reszte_batcha_jako_nieudane(app, messages, e)

    elapsed = time.time() - start_time
    logger.info(f"[EMAIL-BATCH] Batch complete: {sent} sent, {failed} failed, took={elapsed:.2f}s")


def _oznacz_reszte_batcha_jako_nieudane(app, messages, blad):
    """Domyka jako 'failed' te wpisy batcha, które zostały w stanie 'queued'."""
    try:
        with app.app_context():
            for msg in messages:
                log_id = getattr(msg, '_email_log_id', None)
                if log_id:
                    _zapisz_wynik_logu_gdy_w_kolejce(log_id, blad)
    except Exception as e:
        logger.error(f"[EMAIL-LOG] Nie udało się domknąć wpisów batcha: "
                     f"{type(e).__name__}: {e}")


def _zapisz_wynik_logu_gdy_w_kolejce(log_id, blad):
    """Ustawia 'failed' wyłącznie na wpisie, który wciąż jest 'queued'.

    Warunek na stan jest istotny: część wiadomości batcha mogła wyjść, zanim
    połączenie padło, i te mają już swój wynik — nadpisanie zamieniłoby wysłany
    mail w nieudany.
    """
    try:
        from sqlalchemy.orm import Session
        from extensions import db
        from modules.admin.models import EmailLog

        with Session(bind=db.engine) as sesja:
            wpis = sesja.get(EmailLog, log_id)
            if wpis is None or wpis.status != 'queued':
                return
            wpis.status = 'failed'
            wpis.error = (f"{type(blad).__name__}: {blad}")[:2000]
            sesja.commit()
    except Exception as e:
        logger.error(f"[EMAIL-LOG] Nie udało się domknąć wpisu id={log_id}: "
                     f"{type(e).__name__}: {e}")


def send_email_batch_sync(messages):
    """
    Wysyła listę przygotowanych Message SYNCHRONICZNIE, reużywając JEDNO połączenie SMTP
    (jeden AUTH dla całego batcha) z opóźnieniem 2s między mailami.

    W przeciwieństwie do send_email_batch() (async, fire-and-forget) zwraca wynik per
    wiadomość — dzięki temu wołający (np. zadania CLI/cron) może zarejestrować stan
    dopiero po faktycznej wysyłce. Musi być wywoływane w aktywnym kontekście aplikacji.

    Args:
        messages (list): Lista obiektów Message (z prepare_email()).

    Returns:
        list[bool]: Lista zgodna kolejnościowo z `messages`; True = wysłany.
    """
    results = [False] * len(messages)
    if not messages:
        return results

    total = len(messages)
    logger.info(f"[EMAIL-BATCH-SYNC] Starting batch send of {total} emails")
    start_time = time.time()
    sent = 0
    failed = 0

    try:
        with mail.connect() as conn:
            for i, msg in enumerate(messages):
                recipient = msg.recipients[0] if msg.recipients else 'unknown'
                log_id = getattr(msg, '_email_log_id', None)
                msg_start = time.time()
                for attempt in range(1, SMTP_MAX_RETRIES + 1):
                    try:
                        conn.send(msg)
                        results[i] = True
                        sent += 1
                        logger.info(f"[EMAIL-BATCH-SYNC] {i+1}/{total} SUCCESS to={recipient}" +
                                    (f" (attempt {attempt})" if attempt > 1 else ""))
                        _zapisz_wynik_logu(log_id, 'sent', attempt,
                                           duration_ms=(time.time() - msg_start) * 1000)
                        break
                    except Exception as e:
                        if attempt < SMTP_MAX_RETRIES and _is_retryable_smtp_error(e):
                            delay = SMTP_RETRY_DELAYS[attempt - 1]
                            logger.warning(f"[EMAIL-BATCH-SYNC] {i+1}/{total} RETRY {attempt}/{SMTP_MAX_RETRIES} "
                                           f"to={recipient}, error={type(e).__name__}: {e}, retrying in {delay}s")
                            time.sleep(delay)
                        else:
                            failed += 1
                            logger.error(f"[EMAIL-BATCH-SYNC] {i+1}/{total} FAILED to={recipient}, "
                                         f"attempt={attempt}, error={type(e).__name__}: {e}")
                            _zapisz_wynik_logu(log_id, 'failed', attempt, error=e,
                                               duration_ms=(time.time() - msg_start) * 1000)
                            break
                # Odstęp między mailami — trzyma nas pod limitami dostawcy (~30 maili/min)
                if i < total - 1:
                    time.sleep(SMTP_ODSTEP_MIEDZY_MAILAMI)
    except Exception as e:
        logger.error(f"[EMAIL-BATCH-SYNC] Connection error: {type(e).__name__}: {e}")
        # Patrz send_async_email_batch: wpisy bez wyniku nie mogą zostać 'queued'.
        for msg in messages:
            log_id = getattr(msg, '_email_log_id', None)
            if log_id:
                _zapisz_wynik_logu_gdy_w_kolejce(log_id, e)

    elapsed = time.time() - start_time
    logger.info(f"[EMAIL-BATCH-SYNC] Batch complete: {sent} sent, {failed} failed, took={elapsed:.2f}s")
    return results


def send_email(to, subject, template, log_context=None, **kwargs):
    """
    Wysyła email z templatem HTML

    Args:
        to (str): Adres odbiorcy
        subject (str): Temat emaila
        template (str): Ścieżka do template HTML (bez .html)
        log_context (dict): Opcjonalne powiązanie wpisu EmailLog z encją —
            {'entity_type': 'order', 'entity_id': 123}. Bez tego mail nadal
            trafia do logu, tylko nie pokaże się w historii zamówienia.
        **kwargs: Dodatkowe zmienne przekazywane do template

    Returns:
        bool: True jeśli email został ZAKOLEJKOWANY (wysyłka idzie w tle —
            o jej wyniku mówi dopiero EmailLog, nie ta wartość)
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
        try:
            log_id = _zaloguj_kolejkowanie(to, subject, template, log_context)
        except Exception as e:
            # _zaloguj_kolejkowanie łapie własne błędy, ale nie chcemy, żeby
            # JAKAKOLWIEK awaria logu zabrała klientowi maila.
            logger.error(f"[EMAIL-LOG] Pominięto log dla to={to}: {type(e).__name__}: {e}")
            log_id = None

        Thread(
            target=send_async_email,
            args=(app, msg, log_id),
            name=f"email-{to}"
        ).start()
        logger.info(f"[EMAIL] Thread started for to={to}")

        return True

    except Exception as e:
        logger.error(f"[EMAIL] Preparation FAILED to={to}, subject='{subject}', error={type(e).__name__}: {e}")
        return False


def send_email_sync(to, subject, template, log_context=None, **kwargs):
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
        log_id = _zaloguj_kolejkowanie(to, subject, template, log_context)
        start_time = time.time()

        for attempt in range(1, SMTP_MAX_RETRIES + 1):
            try:
                mail.send(msg)
                elapsed = time.time() - start_time
                logger.info(f"[EMAIL-SYNC] SUCCESS to={to}, took={elapsed:.2f}s" +
                            (f" (attempt {attempt})" if attempt > 1 else ""))
                _zapisz_wynik_logu(log_id, 'sent', attempt, duration_ms=elapsed * 1000)
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
                    _zapisz_wynik_logu(log_id, 'failed', attempt, error=e,
                                       duration_ms=elapsed * 1000)
                    return False

        return False

    except Exception as e:
        logger.error(f"[EMAIL-SYNC] Preparation FAILED to={to}, subject='{subject}', error={type(e).__name__}: {e}")
        return False


def prepare_email(to, subject, template, log_context=None, **kwargs):
    """
    Przygotowuje obiekt Message bez wysyłania.
    Używane przez send_email_batch() do batch'owego wysyłania.

    Wpis EmailLog zakładamy już TUTAJ, a jego id wieszamy na wiadomości
    (`_email_log_id`) — batch dostaje samą listę Message, więc bez tego nie miałby
    jak połączyć wyniku wysyłki z odbiorcą.

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

        msg._email_log_id = _zaloguj_kolejkowanie(to, subject, template, log_context)
        return msg

    except Exception as e:
        logger.error(f"[EMAIL] Prepare FAILED to={to}, subject='{subject}', error={type(e).__name__}: {e}")
        return None


def send_email_batch(messages):
    """
    Wysyła listę przygotowanych Message w jednym wątku z jednym połączeniem SMTP.

    Wątek świadomie NIE jest daemonem. `daemon=True` zostałby ubity natychmiast,
    gdy proces się kończy — a gunicorn worker kończy się właśnie zwykłym wyjściem
    Pythona przy SIGTERM (restart usługi / deploy), które domyślnie CZEKA na
    wątki nie-daemon zamiast przerywać je w połowie. Dla maila to różnica między
    „batch dokończy wysyłkę mimo restartu w trakcie” a „część uczestników paczki
    zbiorczej nie dostanie nic, bez śladu w logach" — nieakceptowalne, bo to
    jedyne miejsce, gdzie klient dowiaduje się o wysyłce/dostawie.

    Pod TESTING wysyłka idzie więc SYNCHRONICZNIE, w wątku wołającego (ten sam
    wzorzec co PushManager._fire_and_forget) — bez tego każdy test, który trafia
    tę funkcję bez własnego monkeypatcha (patrz fixture `maile_synchronicznie`
    w conftest), zostawiał żywy nie-daemon wątek, na którego zakończenie pytest
    czekał przy wyjściu procesu (Python joinuje wątki nie-daemon przy zamknięciu
    interpretera).

    Pod TESTING pomijamy przy tym odstęp między wiadomościami (`odstep_s=0`).
    Odstęp broni przed limitem dostawcy, a TESTING włącza domyślnie
    MAIL_SUPPRESS_SEND (patrz flask_mail.Mail.init_mail), więc `mail.connect()`
    i tak nie dotyka sieci — nie ma czego limitować. Bez tego przeniesienie
    wysyłki do wątku wołającego wciągnęłoby te 2 s na wiadomość wprost w czas
    testu: same paczki zbiorcze w zestawie kosztowały tak ok. 10 s.
    Produkcja nie ma TESTING i dostaje wątek tła z pełnym odstępem, bez zmian.

    Args:
        messages (list): Lista obiektów Message (z prepare_email())
    """
    messages = [m for m in messages if m is not None]
    if not messages:
        return

    app = current_app._get_current_object()
    logger.info(f"[EMAIL-BATCH] Queuing batch of {len(messages)} emails")
    if app.config.get('TESTING'):
        send_async_email_batch(app, messages, odstep_s=0)
        return
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


def send_order_confirmation_email(user_email, user_name, order_number, order_total, order_items, is_offer=False, payment_stages=None, log_context=None):
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
        log_context=log_context,
        user_name=user_name,
        order_number=order_number,
        order_total=order_total,
        order_items=order_items,
        is_offer=is_offer,
        payment_stages=payment_stages
    )


def send_admin_created_order_email(user_email, user_name, admin_name, order_number,
                                    page_name, order_total, order_items,
                                    payment_stages=None, payment_deadline=None,
                                    log_context=None):
    """
    Wysyła powiadomienie o zamówieniu utworzonym ręcznie przez administratora
    (np. po zamknięciu strony PRE-ORDER).

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        admin_name (str): Imię/nazwisko administratora który dodał zamówienie
        order_number (str): Numer zamówienia
        page_name (str): Nazwa strony sprzedaży
        order_total (float): Suma za produkty
        order_items (list): Lista pozycji [{'product_name', 'quantity', 'total'}]
        payment_stages (int, optional): 3 lub 4 — etapy płatności
        payment_deadline (str, optional): Sformatowany termin płatności (np. "12.05.2026 23:59")
    """
    return send_email(
        to=user_email,
        subject=f'Zamówienie {order_number} dodane przez administratora - ThunderOrders',
        template='admin_created_order',
        log_context=log_context,
        user_name=user_name,
        admin_name=admin_name,
        order_number=order_number,
        page_name=page_name,
        order_total=order_total,
        order_items=order_items,
        payment_stages=payment_stages,
        payment_deadline=payment_deadline,
    )


def send_order_status_change_email(user_email, user_name, order_number, old_status, new_status,
                                   log_context=None):
    """
    Wysyła powiadomienie o zmianie statusu zamówienia

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia
        old_status (str): Poprzedni status
        new_status (str): Nowy status
        log_context (dict): Powiązanie wpisu EmailLog z zamówieniem
    """
    return send_email(
        to=user_email,
        subject=f'Zmiana statusu zamówienia {order_number} - ThunderOrders',
        template='order_status_change',
        log_context=log_context,
        user_name=user_name,
        order_number=order_number,
        old_status=old_status,
        new_status=new_status
    )


def send_supplier_ordered_email(user_email, user_name, order_number, order_detail_url,
                                log_context=None):
    """Wysyła email o zamówieniu produktów u dostawcy."""
    return send_email(
        to=user_email,
        subject=f'Zamówiliśmy Twoje produkty u dostawcy ({order_number}) - ThunderOrders',
        template='order_supplier_ordered',
        log_context=log_context,
        user_name=user_name,
        order_number=order_number,
        order_detail_url=order_detail_url
    )


def send_supplier_cancelled_email(user_email, user_name, order_number, order_detail_url,
                                  log_context=None):
    """Wysyła email o anulowaniu zamówienia u dostawcy."""
    return send_email(
        to=user_email,
        subject=f'Anulowano zamówienie u dostawcy ({order_number}) - ThunderOrders',
        template='order_supplier_cancelled',
        log_context=log_context,
        user_name=user_name,
        order_number=order_number,
        order_detail_url=order_detail_url
    )


def send_offer_closure_email(customer_email, customer_name, page_name, items,
                                fulfilled_items=None, fulfilled_total=0, shipping_cost=0,
                                grand_total=0, order_number='', payment_methods=None,
                                upload_payment_url='', log_context=None):
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
        log_context=log_context,
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
                               cancelled_items, reason='', log_context=None):
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
            log_context=log_context,
            customer_name=user_name,
            order_number=order_number,
            page_name=page_name,
            cancelled_items=cancelled_items,
            reason=reason
        )
    except Exception as e:
        logger.error(f"Error sending order cancelled email to {user_email}: {e}")
        return False


def send_payment_approved_email(user_email, user_name, order_number, amount, order_detail_url, stage_name='za produkt', log_context=None):
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
        log_context=log_context,
        user_name=user_name,
        order_number=order_number,
        amount=amount,
        order_detail_url=order_detail_url,
        stage_name=stage_name
    )


def send_payment_rejected_email(user_email, user_name, order_number, amount, rejection_reason, upload_url, stage_name='za produkt', log_context=None):
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
        log_context=log_context,
        user_name=user_name,
        order_number=order_number,
        amount=amount,
        rejection_reason=rejection_reason,
        upload_url=upload_url,
        stage_name=stage_name
    )


def send_admin_payment_uploaded_email(admin_email, customer_name, customer_email,
                                      order_number, stage_names, review_url,
                                      log_context=None):
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
        log_context=log_context,
        customer_name=customer_name,
        customer_email=customer_email,
        order_number=order_number,
        stage_names=stage_names,
        review_url=review_url
    )


def send_admin_new_order_email(admin_email, customer_name, customer_email,
                               order_number, page_name, items,
                               order_total, order_detail_url, created_at,
                               log_context=None):
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
        log_context=log_context,
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
                                shipping_cost, grand_total, order_detail_url,
                                log_context=None):
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
        log_context=log_context,
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
                                courier_name, tracking_url=None, log_context=None):
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
        log_context=log_context,
        user_name=user_name,
        order_number=order_number,
        tracking_number=tracking_number,
        courier_name=courier_name,
        tracking_url=tracking_url
    )


def _cost_added_subject(cost_type, order_number):
    """Temat maila o dodaniu kosztu — wspólny dla wysyłki pojedynczej i batchowej."""
    if cost_type == 'proxy_shipping':
        return f'Koszt wysyłki z proxy - {order_number} - ThunderOrders'
    if cost_type == 'domestic_shipping':
        return f'Koszt wysyłki krajowej - {order_number} - ThunderOrders'
    return f'Koszt cła i VAT - {order_number} - ThunderOrders'


def send_cost_added_email(user_email, user_name, order_number, cost_type, cost_amount, order_detail_url, log_context=None):
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
    return send_email(
        to=user_email,
        subject=_cost_added_subject(cost_type, order_number),
        template='cost_added',
        log_context=log_context,
        user_name=user_name,
        order_number=order_number,
        cost_type=cost_type,
        cost_amount=cost_amount,
        order_detail_url=order_detail_url
    )


def prepare_cost_added_email(user_email, user_name, order_number, cost_type, cost_amount, order_detail_url, log_context=None):
    """
    Buduje Message o dodaniu kosztu (BEZ wysyłania) — do send_email_batch().
    Parytet treści z send_cost_added_email().

    Returns:
        Message lub None w przypadku błędu
    """
    return prepare_email(
        to=user_email,
        subject=_cost_added_subject(cost_type, order_number),
        template='cost_added',
        log_context=log_context,
        user_name=user_name,
        order_number=order_number,
        cost_type=cost_type,
        cost_amount=cost_amount,
        order_detail_url=order_detail_url
    )


def send_shipping_request_created_email(user_email, user_name, request_number,
                                         orders, delivery_method_display,
                                         full_address, shipping_requests_url,
                                         log_context=None):
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
        log_context=log_context,
        user_name=user_name,
        request_number=request_number,
        orders=orders,
        delivery_method_display=delivery_method_display,
        full_address=full_address,
        shipping_requests_url=shipping_requests_url
    )


def _shipping_status_change_subject(request_number, new_status_name):
    """Temat maila o zmianie statusu — wspólny dla wysyłki pojedynczej i batchowej."""
    return f'Zmiana statusu zlecenia {request_number} - {new_status_name}'


def send_shipping_status_change_email(user_email, user_name, request_number,
                                       old_status_name, new_status_name, new_status_color,
                                       orders, tracking_number=None, courier_name=None,
                                       shipping_requests_url=None, log_context=None):
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
        subject=_shipping_status_change_subject(request_number, new_status_name),
        template='shipping_status_change',
        log_context=log_context,
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


def prepare_shipping_status_change_email(user_email, user_name, request_number,
                                          old_status_name, new_status_name, new_status_color,
                                          orders, tracking_number=None, courier_name=None,
                                          shipping_requests_url=None, log_context=None):
    """Wersja send_shipping_status_change_email do wysyłki wsadowej (BEZ wysyłania).

    Potrzebna dla paczki zbiorczej: zmiana statusu zbiorczego zjeżdża na wszystkie
    zlecenia źródłowe naraz, więc trzeba powiadomić kilku uczestników jednym
    połączeniem SMTP zamiast pętlą po send_email() (patrz prepare_shipment_sent_email).

    Returns:
        Message lub None w przypadku błędu
    """
    return prepare_email(
        to=user_email,
        subject=_shipping_status_change_subject(request_number, new_status_name),
        template='shipping_status_change',
        log_context=log_context,
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


def _shipment_sent_subject(request_number, tracking_number=None):
    """Temat maila o wysłanej paczce — wspólny dla wysyłki pojedynczej i batchowej."""
    if tracking_number:
        return f'Numer przesyłki do Twojej paczki - {request_number} - ThunderOrders'
    return f'Twoja paczka została wysłana - {request_number} - ThunderOrders'


def send_shipment_sent_email(user_email, user_name, request_number, order_numbers,
                             tracking_number=None, courier_name=None, tracking_url=None,
                             shipping_requests_url=None, log_context=None):
    """
    Wysyła JEDEN mail o wysłanej paczce — na całe zlecenie wysyłki.

    Zastępuje mail per zamówienie: klient dostaje jedną wiadomość z listą
    wszystkich zamówień jadących w tej paczce. Blok ze śledzeniem pojawia się
    w szablonie tylko wtedy, gdy jest numer przesyłki — temat maila rozróżnia
    obie sytuacje, treść jest ta sama.

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        request_number (str): Numer zlecenia wysyłki (np. WYS/000001)
        order_numbers (list): Lista numerów zamówień w paczce (same stringi)
        tracking_number (str): Numer przesyłki (opcjonalny)
        courier_name (str): Nazwa kuriera do wyświetlenia (opcjonalna)
        tracking_url (str): URL do śledzenia przesyłki (opcjonalny)
        shipping_requests_url (str): URL do listy zleceń wysyłki klienta
    """
    return send_email(
        to=user_email,
        subject=_shipment_sent_subject(request_number, tracking_number),
        template='shipment_sent',
        log_context=log_context,
        user_name=user_name,
        request_number=request_number,
        order_numbers=order_numbers,
        tracking_number=tracking_number,
        courier_name=courier_name,
        tracking_url=tracking_url,
        shipping_requests_url=shipping_requests_url
    )


def prepare_shipment_sent_email(user_email, user_name, request_number, order_numbers,
                                tracking_number=None, courier_name=None, tracking_url=None,
                                shipping_requests_url=None, consolidation_note=None,
                                log_context=None):
    """Wersja send_shipment_sent_email do wysyłki wsadowej (BEZ wysyłania).

    Pętla po uczestnikach paczki zbiorczej na send_email() otworzyłaby osobne
    połączenie SMTP na każdy mail — Hostinger limituje uwierzytelnienia per IP.
    consolidation_note trafia do uczestnika, który NIE jest adresatem paczki —
    informuje, że jego zamówienia jadą na adres kogoś innego.

    Returns:
        Message lub None w przypadku błędu
    """
    return prepare_email(
        to=user_email,
        subject=_shipment_sent_subject(request_number, tracking_number),
        template='shipment_sent',
        log_context=log_context,
        user_name=user_name,
        request_number=request_number,
        order_numbers=order_numbers,
        tracking_number=tracking_number,
        courier_name=courier_name,
        tracking_url=tracking_url,
        shipping_requests_url=shipping_requests_url,
        consolidation_note=consolidation_note,
    )


def prepare_shipment_consolidated_email(user_email, user_name, request_number, order_numbers,
                                        recipient_name, is_recipient,
                                        shipping_requests_url=None, log_context=None):
    """Mail o połączeniu wysyłki w paczkę zbiorczą — wersja wsadowa (jedno połączenie SMTP).

    Wysyłany raz, w chwili utworzenia paczki — inaczej uczestnik dowiaduje się
    o zmianie dopiero z maila o wysyłce, gdzie nagle pojawia się cudzy adres.
    Tylko wersja batchowa: to powiadomienie zawsze idzie do >=2 uczestników naraz.
    """
    return prepare_email(
        to=user_email,
        subject=f'Twoja wysyłka {request_number} została połączona w paczkę zbiorczą',
        template='shipment_consolidated',
        log_context=log_context,
        user_name=user_name,
        request_number=request_number,
        order_numbers=order_numbers,
        recipient_name=recipient_name,
        is_recipient=is_recipient,
        shipping_requests_url=shipping_requests_url,
    )


def send_payment_reminder_email(user_email, user_name, order_number, unpaid_stages, order_detail_url, payment_deadline=None, reminder_context='before_deadline', log_context=None):
    """Wysyła email z przypomnieniem o niezapłaconych etapach zamówienia."""
    return send_email(
        to=user_email,
        subject=f'Przypomnienie o płatności - {order_number} - ThunderOrders',
        template='payment_reminder',
        log_context=log_context,
        user_name=user_name,
        order_number=order_number,
        unpaid_stages=unpaid_stages,
        order_detail_url=order_detail_url,
        payment_deadline=payment_deadline,
        reminder_context=reminder_context
    )


def prepare_payment_reminder_email(user_email, user_name, order_number, unpaid_stages, order_detail_url, payment_deadline=None, reminder_context='before_deadline', log_context=None):
    """Buduje Message przypomnienia o płatności (bez wysyłania) — do batch sendingu."""
    return prepare_email(
        to=user_email,
        subject=f'Przypomnienie o płatności - {order_number} - ThunderOrders',
        template='payment_reminder',
        log_context=log_context,
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


def send_contest_win_email(user_email, user_name, contest_name, prize_name, url):
    """
    Wysyła email do zwycięzcy konkursu.

    Args:
        user_email (str): Email zwycięzcy
        user_name (str): Imię zwycięzcy
        contest_name (str): Nazwa konkursu
        prize_name (str): Nazwa nagrody
        url (str): URL do strony konkursu
    """
    return send_email(
        to=user_email,
        subject=f'Wygrałeś w konkursie {contest_name} - ThunderOrders',
        template='contest_win',
        user_name=user_name,
        contest_name=contest_name,
        prize_name=prize_name,
        url=url,
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


def prepare_packing_photo_email(user_email, user_name, order_number, photo_path,
                                consolidation_note=None, log_context=None):
    """Buduje Message ze zdjęciem paczki (BEZ wysyłania) — do batch sendingu.

    Nie korzysta z `prepare_email`, bo ten dokłada wyłącznie logo, a tutaj
    potrzebny jest drugi inline attachment (samo zdjęcie kartonu).

    `consolidation_note`: zdanie uprzedzające, że karton jest wspólny. Zdjęcie
    paczki zbiorczej pokazuje produkty wszystkich uczestników i może zawierać
    etykietę z pełnym adresem adresata — uczestnik musi wiedzieć o tym, ZANIM
    zobaczy zdjęcie (spec, sekcja „Zdjęcie paczki").

    Returns:
        Message lub None w przypadku błędu
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
            consolidation_note=consolidation_note,
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

        msg._email_log_id = _zaloguj_kolejkowanie(
            user_email, msg.subject, 'packing_photo', log_context)
        return msg

    except Exception as e:
        logger.error(f"[EMAIL] Packing photo prepare FAILED to={user_email}, "
                     f"error={type(e).__name__}: {e}")
        return None


def send_packing_photo_email(user_email, user_name, order_number, photo_path,
                             consolidation_note=None, log_context=None):
    """
    Wysyła email ze zdjęciem spakowanej paczki do klienta.

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        order_number (str): Numer zamówienia
        photo_path (str): Ścieżka do zdjęcia paczki (relatywna od static/)
        consolidation_note (str): zdanie o wspólnym kartonie (paczka zbiorcza)
    """
    app = current_app._get_current_object()

    msg = prepare_packing_photo_email(user_email, user_name, order_number, photo_path,
                                      consolidation_note=consolidation_note,
                                      log_context=log_context)
    if msg is None:
        logger.error(f"[EMAIL] Packing photo email FAILED to={user_email}: brak wiadomości")
        return False

    logger.info(f"[EMAIL] Queuing packing photo email to={user_email}, order={order_number}")
    Thread(
        target=send_async_email,
        args=(app, msg, getattr(msg, '_email_log_id', None)),
        name=f"email-packing-{user_email}"
    ).start()

    return True


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


def prepare_shipment_unconsolidated_email(user_email, user_name, request_number,
                                          order_numbers, shipping_requests_url=None,
                                          log_context=None):
    """Mail o wyjściu zlecenia z paczki zbiorczej — wersja wsadowa.

    Wysyłany przy rozwiązaniu paczki i przy wypięciu pojedynczego uczestnika.
    Bez niego klient zostaje z jedyną, nieaktualną wersją prawdy w skrzynce:
    „Twoje zamówienia jadą w paczce zbiorczej wysłanej na adres X".
    """
    return prepare_email(
        to=user_email,
        subject=f'Twoja wysyłka {request_number} jedzie osobno',
        template='shipment_unconsolidated',
        log_context=log_context,
        user_name=user_name,
        request_number=request_number,
        order_numbers=order_numbers,
        shipping_requests_url=shipping_requests_url,
    )


def prepare_consolidation_address_changed_email(user_email, user_name, request_number,
                                                order_numbers, recipient_name, is_recipient,
                                                shipping_requests_url=None, log_context=None):
    """Mail o zmianie adresu odbioru paczki zbiorczej — wersja wsadowa.

    Zmiana zlecenia wiodącego realnie nadpisuje adres paczki (`_kopiuj_adres`),
    więc bez tego maila uczestnik ma w skrzynce STARY adres i pojedzie po
    przesyłkę w złe miejsce.
    """
    return prepare_email(
        to=user_email,
        subject=f'Zmiana adresu odbioru paczki — {request_number}',
        template='consolidation_address_changed',
        log_context=log_context,
        user_name=user_name,
        request_number=request_number,
        order_numbers=order_numbers,
        recipient_name=recipient_name,
        is_recipient=is_recipient,
        shipping_requests_url=shipping_requests_url,
    )


def prepare_pickup_reminder_email(user_email, user_name, orders_summary,
                                  shipping_url, log_context=None):
    """Buduje Message z przypomnieniem o odbiorze (BEZ wysyłania) — do send_email_batch().

    `orders_summary` to lista dictów {'numer': str, 'pozycje': str} — jeden mail
    obejmuje WSZYSTKIE zaległe zamówienia klienta, więc szablon dostaje listę,
    nie pojedyncze zamówienie.
    """
    liczba = len(orders_summary)
    temat = ('Twoje zamówienie czeka na odbiór' if liczba == 1
             else f'Twoje zamówienia ({liczba}) czekają na odbiór')
    return prepare_email(
        to=user_email,
        subject=temat,
        template='pickup_reminder',
        log_context=log_context,
        user_name=user_name,
        orders_summary=orders_summary,
        shipping_url=shipping_url,
    )
