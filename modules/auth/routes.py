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
    ResetPasswordForm
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
    Wysyła email weryfikacyjny

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
            flash('Musisz zweryfikować swój adres email. Sprawdź swoją skrzynkę pocztową.', 'warning')
            # TODO: Opcjonalnie - przycisk "Wyślij ponownie email weryfikacyjny"
            return redirect(url_for('auth.login'))

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
    Strona rejestracji
    GET: Wyświetla formularz
    POST: Przetwarza rejestrację
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
            return render_template('auth/register.html', form=form, title='Rejestracja')

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

        # Wygeneruj token weryfikacji emaila
        user.generate_verification_token()

        # Zapisz do bazy
        try:
            db.session.add(user)
            db.session.commit()

            # Wyślij email weryfikacyjny
            send_verification_email(user)

            flash(
                'Rejestracja pomyślna! Sprawdź swoją skrzynkę email, aby aktywować konto.',
                'success'
            )
            return redirect(url_for('auth.login'))

        except Exception as e:
            db.session.rollback()
            flash('Wystąpił błąd podczas rejestracji. Spróbuj ponownie.', 'error')
            print(f"[ERROR] Registration failed: {e}")

    return render_template('auth/register.html', form=form, title='Rejestracja')


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
    Strona zapomniałem hasła
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

    return render_template('auth/forgot_password.html', form=form, title='Resetowanie hasła')


@auth_bp.route('/forgot-password-confirmation')
def forgot_password_confirmation():
    """
    Strona potwierdzenia wysłania emaila z linkiem do resetu hasła
    """
    if current_user.is_authenticated:
        return redirect(url_for('client.dashboard'))

    return render_template('auth/forgot_password_confirmation.html', title='Email wysłany')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """
    Strona resetowania hasła z tokenem
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

    return render_template('auth/reset_password.html', form=form, title='Nowe hasło', token=token)
