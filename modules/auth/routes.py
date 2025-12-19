"""
Auth Module - Routes
Endpointy autentykacji: login, register, logout, password reset
"""

from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from datetime import datetime

# Import db z extensions.py (unika circular import)
from extensions import db
from modules.auth import auth_bp
from modules.auth.models import User
from modules.auth.forms import (
    LoginForm,
    RegisterForm,
    ForgotPasswordForm,
    ResetPasswordForm,
    VerificationCodeForm
)


# =============================================
# Helper Functions
# =============================================

def check_login_attempts(email, ip_address):
    """
    Sprawdza liczbę nieudanych prób logowania (rate limiting)
    TODO: Implementacja w ETAPIE 2 Task 7

    Args:
        email (str): Email użytkownika
        ip_address (str): IP address

    Returns:
        tuple: (is_locked, minutes_until_unlock)
    """
    # Na razie zwracamy False (brak blokady)
    # W Task 7 dodamy logikę z tabeli login_attempts
    return False, 0


def record_login_attempt(email, ip_address, success):
    """
    Zapisuje próbę logowania do bazy
    TODO: Implementacja w ETAPIE 2 Task 7

    Args:
        email (str): Email użytkownika
        ip_address (str): IP address
        success (bool): Czy logowanie się powiodło
    """
    # Na razie nic nie robimy
    # W Task 7 dodamy zapis do tabeli login_attempts
    pass


def send_verification_email(user):
    """
    Wysyła email weryfikacyjny (legacy - stary system z linkami)

    Args:
        user (User): Użytkownik
    """
    from utils.email_sender import send_verification_email as send_email

    try:
        send_email(
            user_email=user.email,
            verification_token=user.email_verification_token,
            user_name=user.first_name
        )
        current_app.logger.info(f"Verification email sent to {user.email}")
    except Exception as e:
        current_app.logger.error(f"Failed to send verification email to {user.email}: {str(e)}")


def send_verification_code(user, code):
    """
    Wysyła email z 6-cyfrowym kodem weryfikacyjnym

    Args:
        user (User): Użytkownik
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
        current_app.logger.error(f"Failed to send verification code to {user.email}: {str(e)}")


def send_password_reset_email(user):
    """
    Wysyła email z linkiem do resetu hasła

    Args:
        user (User): Użytkownik
    """
    from utils.email_sender import send_password_reset_email as send_email

    try:
        send_email(
            user_email=user.email,
            reset_token=user.password_reset_token,
            user_name=user.first_name
        )
        current_app.logger.info(f"Password reset email sent to {user.email}")
    except Exception as e:
        current_app.logger.error(f"Failed to send password reset email to {user.email}: {str(e)}")


# =============================================
# Routes
# =============================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Strona logowania
    GET: Wyświetla formularz
    POST: Przetwarza logowanie
    """
    # Jeśli użytkownik już zalogowany, przekieruj
    if current_user.is_authenticated:
        if current_user.role in ['admin', 'mod']:
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('client.dashboard'))

    form = LoginForm()

    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        password = form.password.data
        remember = form.remember_me.data
        ip_address = request.remote_addr

        # Sprawdź rate limiting
        is_locked, minutes = check_login_attempts(email, ip_address)
        if is_locked:
            flash(f'Zbyt wiele nieudanych prób logowania. Spróbuj ponownie za {minutes} minut.', 'error')
            return redirect(url_for('auth.login'))

        # Znajdź użytkownika
        user = User.get_by_email(email)

        # Sprawdź czy użytkownik istnieje i hasło jest poprawne
        if user is None or not user.check_password(password):
            record_login_attempt(email, ip_address, success=False)
            flash('Nieprawidłowy email lub hasło.', 'error')
            return redirect(url_for('auth.login'))

        # Sprawdź czy konto jest aktywne
        if not user.is_active:
            flash('Twoje konto zostało dezaktywowane. Skontaktuj się z administratorem.', 'error')
            return redirect(url_for('auth.login'))

        # Sprawdź czy email został zweryfikowany
        if not user.email_verified:
            # Jeśli nie ma tokena sesji lub kod wygasł, wygeneruj nowy
            if not user.verification_session_token or not user.email_verification_code_expires or \
               datetime.now() > user.email_verification_code_expires:
                code, session_token = user.generate_verification_code()
                db.session.commit()
                # Wyślij nowy kod
                send_verification_code(user, code)
            else:
                session_token = user.verification_session_token

            flash('Twoje konto nie zostało jeszcze zweryfikowane. Wpisz kod, który wysłaliśmy na Twój email.', 'warning')
            return redirect(url_for('auth.verify_email_code', token=session_token))

        # Logowanie pomyślne
        login_user(user, remember=remember)
        user.update_last_login()
        record_login_attempt(email, ip_address, success=True)

        flash(f'Witaj, {user.first_name}!', 'success')

        # Sprawdź czy użytkownik ma wybrany avatar
        if not user.has_avatar:
            return redirect(url_for('profile.select_avatar'))

        # Redirect na odpowiedni dashboard
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        elif user.role in ['admin', 'mod']:
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('client.dashboard'))

    return render_template('auth/login.html', form=form, title='Logowanie')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    Strona rejestracji (zunifikowany szablon)
    GET: Wyświetla formularz
    POST: Przetwarza rejestrację i przekierowuje na stronę weryfikacji kodem
    """
    # Jeśli użytkownik już zalogowany, przekieruj
    if current_user.is_authenticated:
        return redirect(url_for('client.dashboard'))

    form = RegisterForm()

    if form.validate_on_submit():
        # Sprawdź czy email już istnieje (manualna walidacja)
        email = form.email.data.lower().strip()
        # Bezpośrednie query zamiast używania metody klasowej
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            form.email.errors.append('Ten adres email jest już zarejestrowany')
            return render_template('auth/auth_unified.html', form=form, mode='register')

        # Stwórz nowego użytkownika
        user = User(
            email=form.email.data.lower().strip(),
            first_name=form.first_name.data.strip(),
            last_name=form.last_name.data.strip(),
            phone=form.phone.data.strip() if form.phone.data else None,
            role='client',  # Domyślnie klient
            is_active=True,
            email_verified=False  # Wymaga weryfikacji
        )

        # Ustaw hasło (zahashowane)
        user.set_password(form.password.data)

        # Wygeneruj 6-cyfrowy kod weryfikacyjny i token sesji
        code, session_token = user.generate_verification_code()

        # Zapisz do bazy
        try:
            db.session.add(user)
            db.session.commit()

            # Wyślij email z kodem weryfikacyjnym
            send_verification_code(user, code)

            # Przekieruj na stronę weryfikacji kodem
            return redirect(url_for('auth.verify_email_code', token=session_token))

        except Exception as e:
            db.session.rollback()
            flash('Wystąpił błąd podczas rejestracji. Spróbuj ponownie.', 'error')
            print(f"[ERROR] Registration failed: {e}")

    return render_template('auth/auth_unified.html', form=form, mode='register')


@auth_bp.route('/logout')
@login_required
def logout():
    """Wylogowanie użytkownika"""
    logout_user()
    flash('Zostałeś wylogowany.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    """
    Weryfikacja emaila po kliknięciu w link

    Args:
        token (str): Token weryfikacyjny
    """
    user = User.get_by_verification_token(token)

    if user is None:
        flash('Link weryfikacyjny jest nieprawidłowy lub wygasł.', 'error')
        return redirect(url_for('auth.login'))

    if user.email_verified:
        flash('Twój email został już zweryfikowany. Możesz się zalogować.', 'info')
        return redirect(url_for('auth.login'))

    # Weryfikuj email
    user.verify_email()
    db.session.commit()

    flash('Email został zweryfikowany! Możesz się teraz zalogować.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """
    Strona zapomniałem hasła (zunifikowany szablon)
    GET: Wyświetla formularz
    POST: Wysyła email z linkiem do resetu
    """
    if current_user.is_authenticated:
        return redirect(url_for('client.dashboard'))

    form = ForgotPasswordForm()

    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        user = User.get_by_email(email)

        if user:
            # Wygeneruj token resetu hasła (ważny 1h)
            user.generate_password_reset_token(expires_in=3600)
            db.session.commit()

            # Wyślij email
            send_password_reset_email(user)

        # Zawsze przekieruj na stronę potwierdzenia (security by obscurity)
        return redirect(url_for('auth.forgot_password_confirmation'))

    return render_template('auth/auth_unified.html', form=form, mode='forgot')


@auth_bp.route('/forgot-password-confirmation')
def forgot_password_confirmation():
    """
    Strona potwierdzenia wysłania emaila z linkiem do resetu hasła (zunifikowany szablon)
    """
    if current_user.is_authenticated:
        return redirect(url_for('client.dashboard'))

    return render_template('auth/auth_unified.html', mode='forgot_sent')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """
    Strona resetowania hasła z tokenem (zunifikowany szablon)
    GET: Wyświetla formularz nowego hasła
    POST: Zapisuje nowe hasło

    Args:
        token (str): Token resetu hasła
    """
    if current_user.is_authenticated:
        return redirect(url_for('client.dashboard'))

    user = User.get_by_reset_token(token)

    if user is None or not user.verify_password_reset_token(token):
        flash('Link resetowania hasła jest nieprawidłowy lub wygasł.', 'error')
        return redirect(url_for('auth.forgot_password'))

    form = ResetPasswordForm()

    if form.validate_on_submit():
        # Ustaw nowe hasło
        user.set_password(form.password.data)
        user.clear_password_reset_token()
        db.session.commit()

        flash('Hasło zostało zmienione. Możesz się teraz zalogować.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/auth_unified.html', form=form, mode='reset', token=token)


# =============================================
# New 6-digit Code Verification Routes
# =============================================

@auth_bp.route('/verify-email-code/<token>', methods=['GET', 'POST'])
def verify_email_code(token):
    """
    Strona weryfikacji emaila 6-cyfrowym kodem (zunifikowany szablon)
    GET: Wyświetla formularz z 6 inputami na kod
    POST: Weryfikuje wprowadzony kod

    Args:
        token (str): Token sesji weryfikacji (bezpieczny, zakodowany)
    """
    # Jeśli użytkownik już zalogowany, przekieruj
    if current_user.is_authenticated:
        return redirect(url_for('client.dashboard'))

    # Znajdź użytkownika po tokenie sesji
    user = User.get_by_verification_session_token(token)

    if user is None:
        flash('Link weryfikacyjny jest nieprawidłowy lub wygasł.', 'error')
        return redirect(url_for('auth.login'))

    # Sprawdź czy email nie jest już zweryfikowany
    if user.email_verified:
        flash('Twój email został już zweryfikowany. Możesz się zalogować.', 'info')
        return redirect(url_for('auth.login'))

    form = VerificationCodeForm()

    # Oblicz pozostały czas do ponownego wysłania kodu
    can_resend, seconds_remaining = user.can_resend_code()

    if form.validate_on_submit():
        # Pobierz pełny kod z formularza
        code = form.get_full_code()

        # Weryfikuj kod
        success, error_message = user.verify_code(code)
        db.session.commit()

        if success:
            # Przekieruj na stronę sukcesu
            return redirect(url_for('auth.verification_success'))
        else:
            flash(error_message, 'error')
            return redirect(url_for('auth.verify_email_code', token=token))

    return render_template(
        'auth/auth_unified.html',
        form=form,
        mode='verify',
        token=token,
        user_email=user.email,
        can_resend=can_resend,
        seconds_remaining=seconds_remaining
    )


@auth_bp.route('/resend-code/<token>', methods=['POST'])
def resend_verification_code(token):
    """
    Endpoint do ponownego wysłania kodu weryfikacyjnego (AJAX)

    Args:
        token (str): Token sesji weryfikacji

    Returns:
        JSON response z nowym czasem do ponownego wysłania
    """
    from flask import jsonify

    # Znajdź użytkownika po tokenie sesji
    user = User.get_by_verification_session_token(token)

    if user is None:
        return jsonify({
            'success': False,
            'error': 'Nieprawidłowy token sesji.'
        }), 400

    if user.email_verified:
        return jsonify({
            'success': False,
            'error': 'Email został już zweryfikowany.'
        }), 400

    # Sprawdź czy można wysłać nowy kod (cooldown 60s)
    can_resend, seconds_remaining = user.can_resend_code()

    if not can_resend:
        return jsonify({
            'success': False,
            'error': f'Poczekaj jeszcze {seconds_remaining} sekund przed wysłaniem nowego kodu.',
            'seconds_remaining': seconds_remaining
        }), 429

    # Wygeneruj nowy kod (unieważnia poprzedni)
    new_code = user.resend_verification_code()
    db.session.commit()

    if new_code:
        # Wyślij email z nowym kodem
        send_verification_code(user, new_code)

        return jsonify({
            'success': True,
            'message': 'Nowy kod został wysłany na Twój email.',
            'seconds_remaining': 60
        })

    return jsonify({
        'success': False,
        'error': 'Nie udało się wysłać nowego kodu. Spróbuj ponownie.'
    }), 500


@auth_bp.route('/verification-success')
def verification_success():
    """
    Strona sukcesu po weryfikacji emaila (zunifikowany szablon)
    """
    return render_template(
        'auth/auth_unified.html',
        mode='success',
        success_title='Konto aktywowane!',
        success_message='Twój adres email został pomyślnie zweryfikowany. Możesz teraz zalogować się na swoje konto.'
    )


@auth_bp.route('/register-from-guest', methods=['POST'])
def register_from_guest():
    """
    Rejestracja użytkownika z danych zamówienia gościa.
    Pre-wypełnione dane: imię, nazwisko, email, telefon.
    Użytkownik wpisuje tylko hasło.
    """
    from modules.orders.models import Order
    from utils.activity_logger import log_activity

    order_id = request.form.get('order_id')
    guest_token = request.form.get('guest_token')
    password = request.form.get('password')
    password_confirm = request.form.get('password_confirm')

    # Validation
    if not all([order_id, guest_token, password, password_confirm]):
        flash('Brak wymaganych danych.', 'error')
        return redirect(request.referrer or url_for('auth.register'))

    if password != password_confirm:
        flash('Hasła nie są identyczne.', 'error')
        return redirect(request.referrer)

    if len(password) < 8:
        flash('Hasło musi mieć minimum 8 znaków.', 'error')
        return redirect(request.referrer)

    # Find order
    try:
        order_id = int(order_id)
    except (ValueError, TypeError):
        flash('Nieprawidłowe dane zamówienia.', 'error')
        return redirect(url_for('auth.register'))

    order = Order.query.filter_by(id=order_id, guest_view_token=guest_token, is_guest_order=True).first()

    if not order:
        flash('Nie znaleziono zamówienia.', 'error')
        return redirect(url_for('auth.register'))

    # Check if email already exists
    existing_user = User.query.filter_by(email=order.guest_email.lower()).first()
    if existing_user:
        flash('Konto z tym adresem email już istnieje. Zaloguj się.', 'warning')
        return redirect(url_for('auth.login'))

    # Split name into first_name and last_name
    name_parts = order.guest_name.split(' ', 1) if order.guest_name else ['', '']
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ''

    # Create user
    user = User(
        email=order.guest_email.lower(),
        first_name=first_name,
        last_name=last_name,
        phone=order.guest_phone,
        role='client',
        is_active=True,
        email_verified=True  # Email already verified by order
    )
    user.set_password(password)

    try:
        db.session.add(user)
        db.session.flush()  # Get user.id

        # Assign order to user
        order.user_id = user.id
        order.is_guest_order = False
        # Keep guest_* fields for history

        # Find and assign other guest orders with the same email
        other_guest_orders = Order.query.filter_by(
            guest_email=order.guest_email.lower(),
            is_guest_order=True
        ).all()

        for other_order in other_guest_orders:
            if other_order.id != order.id:
                other_order.user_id = user.id
                other_order.is_guest_order = False

        db.session.commit()

        # Activity log
        log_activity(
            user=user,
            action='user_registered_from_guest',
            entity_type='user',
            entity_id=user.id,
            old_value=None,
            new_value={
                'email': user.email,
                'order_id': order.id,
                'order_number': order.order_number
            }
        )

        # Log in user
        login_user(user)

        flash(f'Witaj, {user.first_name}! Twoje konto zostało utworzone, a zamówienia przypisane.', 'success')
        return redirect(url_for('orders.client_list'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error creating user from guest order: {e}')
        flash('Wystąpił błąd podczas tworzenia konta.', 'error')
        return redirect(request.referrer or url_for('auth.register'))
