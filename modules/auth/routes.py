"""
Auth Module - Routes
Endpointy autentykacji: login, register, logout, password reset
"""

from flask import render_template, redirect, url_for, flash, request, current_app, jsonify, session
from flask_login import login_user, logout_user, current_user, login_required
from datetime import datetime, timedelta
from collections import defaultdict
import secrets
import threading

# Import db z extensions.py (unika circular import)
from extensions import db, csrf, limiter
from modules.auth import auth_bp
from modules.auth.models import User
from modules.auth.forms import (
    LoginForm,
    RegisterForm,
    CompleteProfileForm,
    ForgotPasswordForm,
    ResetPasswordForm,
    VerificationCodeForm
)


# =============================================
# Brute-force Protection (in-memory)
# =============================================

# Struktura: { "email_or_ip": [datetime, datetime, ...] }
_login_attempts = defaultdict(list)
_login_lock = threading.Lock()

# Konfiguracja
MAX_ATTEMPTS = 5          # Maksymalna liczba nieudanych prób
LOCKOUT_MINUTES = 15      # Czas blokady w minutach
ATTEMPT_WINDOW_MINUTES = 15  # Okno czasowe liczenia prób


def _cleanup_old_attempts(key):
    """Usuwa próby starsze niż okno czasowe."""
    cutoff = datetime.now() - timedelta(minutes=ATTEMPT_WINDOW_MINUTES)
    _login_attempts[key] = [t for t in _login_attempts[key] if t > cutoff]
    if not _login_attempts[key]:
        del _login_attempts[key]


def check_login_attempts(email, ip_address):
    """
    Sprawdza czy konto/IP jest zablokowane po zbyt wielu nieudanych próbach.

    Returns:
        tuple: (is_locked, minutes_until_unlock)
    """
    with _login_lock:
        for key in [email.lower(), ip_address]:
            _cleanup_old_attempts(key)
            attempts = _login_attempts.get(key, [])
            if len(attempts) >= MAX_ATTEMPTS:
                oldest = attempts[0]
                unlock_at = oldest + timedelta(minutes=LOCKOUT_MINUTES)
                remaining = (unlock_at - datetime.now()).total_seconds() / 60
                if remaining > 0:
                    return True, int(remaining) + 1
    return False, 0


def record_login_attempt(email, ip_address, success):
    """
    Zapisuje próbę logowania. Przy sukcesie czyści historię.
    """
    with _login_lock:
        if success:
            # Wyczyść próby po udanym logowaniu
            _login_attempts.pop(email.lower(), None)
            _login_attempts.pop(ip_address, None)
        else:
            now = datetime.now()
            _login_attempts[email.lower()].append(now)
            _login_attempts[ip_address].append(now)


from utils.email_manager import EmailManager
from utils.turnstile import verify_turnstile_token, is_turnstile_enabled
from utils.oauth import oauth


# =============================================
# Routes
# =============================================

@auth_bp.route('/login', methods=['GET', 'POST'])
@csrf.exempt
@limiter.limit("5 per minute", methods=["POST"])
def login():
    """
    Strona logowania
    GET: Wyświetla formularz
    POST: Przetwarza logowanie (obsługuje też AJAX, bez CSRF dla AJAX)
    """
    # Helper do wykrywania żądań AJAX
    def is_ajax_request():
        return (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
            'application/json' in request.headers.get('Accept', '')
        )

    is_ajax = is_ajax_request()

    # Jeśli użytkownik już zalogowany, przekieruj
    if current_user.is_authenticated:
        # Sprawdź czy profil jest kompletny
        if not current_user.profile_completed:
            if is_ajax:
                return jsonify({
                    'success': True,
                    'requires_profile': True,
                    'redirect_url': url_for('auth.complete_profile')
                })
            return redirect(url_for('auth.complete_profile'))
        if is_ajax:
            return jsonify({
                'success': True,
                'user': {
                    'id': current_user.id,
                    'full_name': current_user.full_name,
                    'email': current_user.email,
                    'avatar_url': current_user.avatar_url
                }
            })
        if current_user.role in ['admin', 'mod']:
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('client.dashboard'))

    form = LoginForm()

    # Dla żądań AJAX - ręczna walidacja bez CSRF
    if is_ajax and request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember_me') == 'on'
        ip_address = request.remote_addr

        # Podstawowa walidacja
        if not email or not password:
            return jsonify({
                'success': False,
                'error': 'Email i hasło są wymagane.'
            }), 400

        # Sprawdź rate limiting
        is_locked, minutes = check_login_attempts(email, ip_address)
        if is_locked:
            return jsonify({
                'success': False,
                'error': f'Zbyt wiele nieudanych prób logowania. Spróbuj ponownie za {minutes} minut.'
            }), 429

        # Znajdź użytkownika
        user = User.get_by_email(email)

        # Sprawdź czy użytkownik istnieje i hasło jest poprawne
        if user is None or not user.check_password(password):
            record_login_attempt(email, ip_address, success=False)
            return jsonify({
                'success': False,
                'error': 'Nieprawidłowy email lub hasło.'
            }), 401

        # Sprawdź czy konto jest aktywne
        if not user.is_active:
            token = secrets.token_urlsafe(32)
            session['reactivation_token'] = token
            session['reactivation_user_id'] = user.id
            return jsonify({
                'success': False,
                'deactivated': True,
                'redirect': url_for('auth.account_deactivated')
            }), 403

        # Sprawdź czy email został zweryfikowany
        if not user.email_verified:
            # Jeśli nie ma tokena sesji lub kod wygasł, wygeneruj nowy
            if not user.verification_session_token or not user.email_verification_code_expires or \
               datetime.now() > user.email_verification_code_expires:
                code, session_token = user.generate_verification_code()
                db.session.commit()
                # Wyślij nowy kod
                EmailManager.send_verification_code(user, code)
            else:
                session_token = user.verification_session_token

            return jsonify({
                'success': False,
                'error': 'Twoje konto nie zostało jeszcze zweryfikowane. Sprawdź swoją skrzynkę email.',
                'requires_verification': True,
                'verification_url': url_for('auth.verify_email_code', token=session_token)
            }), 403

        # Logowanie pomyślne
        login_user(user, remember=remember)
        user.update_last_login()
        user.update_login_streak()
        record_login_attempt(email, ip_address, success=True)

        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'full_name': user.full_name,
                'email': user.email,
                'avatar_url': user.avatar_url
            },
            'requires_profile': not user.profile_completed
        })

    # Standardowa walidacja formularza (z CSRF) dla zwykłych żądań
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
            token = secrets.token_urlsafe(32)
            session['reactivation_token'] = token
            session['reactivation_user_id'] = user.id
            return redirect(url_for('auth.account_deactivated'))

        # Sprawdź czy email został zweryfikowany
        if not user.email_verified:
            # Jeśli nie ma tokena sesji lub kod wygasł, wygeneruj nowy
            if not user.verification_session_token or not user.email_verification_code_expires or \
               datetime.now() > user.email_verification_code_expires:
                code, session_token = user.generate_verification_code()
                db.session.commit()
                # Wyślij nowy kod
                EmailManager.send_verification_code(user, code)
            else:
                session_token = user.verification_session_token

            flash('Twoje konto nie zostało jeszcze zweryfikowane. Wpisz kod, który wysłaliśmy na Twój email.', 'warning')
            return redirect(url_for('auth.verify_email_code', token=session_token))

        # Logowanie pomyślne
        login_user(user, remember=remember)
        user.update_last_login()
        user.update_login_streak()
        record_login_attempt(email, ip_address, success=True)

        # Sprawdź czy profil jest kompletny
        if not user.profile_completed:
            return redirect(url_for('auth.complete_profile'))

        # Redirect na odpowiedni dashboard
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        elif user.role in ['admin', 'mod']:
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('client.dashboard'))

    register_form = RegisterForm()
    return render_template('auth/auth_login_register.html',
                           login_form=form, register_form=register_form, mode='login')


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("30 per hour", methods=["POST"])
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

    # Helper do wykrywania żądań AJAX
    def is_ajax_request():
        return (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
            'application/json' in request.headers.get('Accept', '')
        )

    is_ajax = is_ajax_request()

    if request.method == 'POST':
        # Honeypot check - cichy odrzut botów
        honeypot = request.form.get('website', '')
        if honeypot:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Spam detected.'}), 400
            login_form = LoginForm()
            return render_template('auth/auth_login_register.html',
                                   login_form=login_form, register_form=form, mode='register')

    if form.validate_on_submit():
        # Weryfikacja Cloudflare Turnstile (jeśli włączone)
        if is_turnstile_enabled():
            turnstile_token = request.form.get('cf-turnstile-response', '')
            if not verify_turnstile_token(turnstile_token):
                if is_ajax:
                    return jsonify({'success': False, 'error': 'Weryfikacja anty-bot nie powiodła się.'}), 400
                flash('Weryfikacja anty-bot nie powiodła się. Spróbuj ponownie.', 'error')
                login_form = LoginForm()
                return render_template('auth/auth_login_register.html',
                                       login_form=login_form, register_form=form, mode='register')

        # Sprawdź czy email już istnieje
        email = form.email.data.lower().strip()
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            if is_ajax:
                return jsonify({'success': False, 'error': 'Ten adres email jest już zarejestrowany.'}), 400
            form.email.errors.append('Ten adres email jest już zarejestrowany')
            login_form = LoginForm()
            return render_template('auth/auth_login_register.html',
                                   login_form=login_form, register_form=form, mode='register')

        # Stwórz nowego użytkownika (tylko email + hasło)
        marketing_consent = request.form.get('marketing_consent') == 'y'
        user = User(
            email=email,
            role='client',
            is_active=True,
            email_verified=False,
            profile_completed=False,
            marketing_consent=marketing_consent
        )

        # Ustaw hasło (zahashowane)
        user.set_password(form.password.data)

        # Wygeneruj 6-cyfrowy kod weryfikacyjny i token sesji
        code, session_token = user.generate_verification_code()

        # Zapisz do bazy
        try:
            db.session.add(user)
            db.session.commit()

            # Wyślij email z kodem weryfikacyjnym (synchronicznie)
            email_sent = EmailManager.send_verification_code(user, code)

            if is_ajax:
                response_data = {
                    'success': True,
                    'token': session_token,
                    'email': email,
                    'seconds_remaining': 60
                }
                if not email_sent:
                    response_data['email_warning'] = 'Konto utworzone, ale wystąpił problem z wysłaniem kodu. Użyj przycisku "Wyślij ponownie".'
                return jsonify(response_data)

            # Przekieruj na stronę weryfikacji kodem
            return redirect(url_for('auth.verify_email_code', token=session_token))

        except Exception as e:
            db.session.rollback()
            if is_ajax:
                return jsonify({'success': False, 'error': 'Wystąpił błąd podczas rejestracji.'}), 500
            flash('Wystąpił błąd podczas rejestracji. Spróbuj ponownie.', 'error')
            print(f"[ERROR] Registration failed: {e}")

    elif is_ajax and request.method == 'POST':
        # Form validation failed - return errors
        errors = {}
        for field_name, field_errors in form.errors.items():
            if field_name != 'csrf_token' and field_errors:
                errors[field_name] = field_errors[0]
        return jsonify({'success': False, 'errors': errors}), 400

    login_form = LoginForm()
    return render_template('auth/auth_login_register.html',
                           login_form=login_form, register_form=form, mode='register')


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

    # Achievement hook: email verified
    try:
        from modules.achievements.services import AchievementService
        AchievementService().check_event(user, 'email_verify')
    except Exception:
        pass

    # Wyślij email powitalny
    from utils.email_manager import EmailManager
    EmailManager.send_welcome(user)

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
            EmailManager.send_password_reset(user)

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

    # Helper do wykrywania żądań AJAX
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        'application/json' in request.headers.get('Accept', '')
    )

    if form.validate_on_submit():
        # Pobierz pełny kod z formularza
        code = form.get_full_code()

        # Weryfikuj kod
        success, error_message = user.verify_code(code)
        db.session.commit()

        if success:
            # Achievement hook: email verified
            try:
                from modules.achievements.services import AchievementService
                AchievementService().check_event(user, 'email_verify')
            except Exception:
                pass

            # Wyślij email powitalny
            from utils.email_manager import EmailManager
            EmailManager.send_welcome(user)

            if is_ajax:
                return jsonify({
                    'success': True,
                    'redirect': url_for('auth.verification_success')
                })

            # Przekieruj na stronę sukcesu
            return redirect(url_for('auth.verification_success'))
        else:
            if is_ajax:
                return jsonify({'success': False, 'error': error_message}), 400
            flash(error_message, 'error')
            return redirect(url_for('auth.verify_email_code', token=token))

    elif is_ajax and request.method == 'POST':
        errors = {}
        for field_name, field_errors in form.errors.items():
            if field_name != 'csrf_token' and field_errors:
                errors[field_name] = field_errors[0]
        return jsonify({'success': False, 'errors': errors}), 400

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
        # Wyślij email z nowym kodem (synchronicznie)
        email_sent = EmailManager.send_verification_code(user, new_code)

        if email_sent:
            return jsonify({
                'success': True,
                'message': 'Nowy kod został wysłany na Twój email.',
                'seconds_remaining': 60
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Nie udało się wysłać kodu email. Sprawdź adres email i spróbuj ponownie.'
            }), 500

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


@auth_bp.route('/account-deactivated')
def account_deactivated():
    """
    Strona informująca o dezaktywowanym koncie z opcją reaktywacji.
    Token reaktywacji przechowywany w session.
    """
    token = session.get('reactivation_token')
    if not token:
        return redirect(url_for('auth.login'))

    return render_template(
        'auth/auth_unified.html',
        mode='deactivated',
        reactivation_token=token
    )


@auth_bp.route('/reactivate-account', methods=['POST'])
def reactivate_account():
    """
    Reaktywacja konta przez użytkownika.
    """
    token = request.form.get('token')
    session_token = session.get('reactivation_token')

    if not token or not session_token or token != session_token:
        flash('Nieprawidłowy token reaktywacji. Spróbuj zalogować się ponownie.', 'error')
        return redirect(url_for('auth.login'))

    user_id = session.pop('reactivation_user_id', None)
    session.pop('reactivation_token', None)

    if not user_id:
        flash('Sesja wygasła. Spróbuj zalogować się ponownie.', 'error')
        return redirect(url_for('auth.login'))

    user = User.query.get(user_id)
    if not user:
        flash('Nie znaleziono konta.', 'error')
        return redirect(url_for('auth.login'))

    user.reactivate()
    db.session.commit()

    login_user(user, remember=True)
    user.update_last_login()

    if not user.profile_completed:
        return redirect(url_for('auth.complete_profile'))

    if user.role in ['admin', 'mod']:
        return redirect(url_for('admin.dashboard'))
    return redirect(url_for('client.dashboard'))


# =============================================
# OAuth Login (Google, Facebook)
# =============================================

@auth_bp.route('/login/<provider>')
def oauth_login(provider):
    """
    Rozpoczyna flow OAuth - redirect do providera (Google/Facebook).
    """
    if provider not in ('google', 'facebook'):
        flash('Nieobsługiwany provider.', 'error')
        return redirect(url_for('auth.login'))

    client = oauth.create_client(provider)
    if client is None:
        flash('Logowanie przez ten serwis nie jest dostępne.', 'error')
        return redirect(url_for('auth.login'))

    redirect_uri = url_for('auth.oauth_callback', provider=provider, _external=True)
    return client.authorize_redirect(redirect_uri)


@auth_bp.route('/callback/<provider>')
def oauth_callback(provider):
    """
    Callback od providera OAuth.
    Pobiera dane użytkownika, tworzy/loguje konto.
    """
    if provider not in ('google', 'facebook'):
        flash('Nieobsługiwany provider.', 'error')
        return redirect(url_for('auth.login'))

    client = oauth.create_client(provider)
    if client is None:
        flash('Logowanie przez ten serwis nie jest dostępne.', 'error')
        return redirect(url_for('auth.login'))

    try:
        token = client.authorize_access_token()
    except Exception as e:
        current_app.logger.error(f'OAuth token error ({provider}): {e}')
        flash('Nie udało się zalogować. Spróbuj ponownie.', 'error')
        return redirect(url_for('auth.login'))

    # Pobierz dane użytkownika z providera
    if provider == 'google':
        user_info = token.get('userinfo')
        if not user_info:
            user_info = client.userinfo()
        oauth_id = user_info.get('sub')
        email = user_info.get('email', '').lower().strip()
        first_name = user_info.get('given_name', '')
        last_name = user_info.get('family_name', '')
    else:  # facebook
        resp = client.get('me?fields=id,name,email,first_name,last_name')
        user_info = resp.json()
        oauth_id = user_info.get('id')
        email = user_info.get('email', '').lower().strip()
        first_name = user_info.get('first_name', '')
        last_name = user_info.get('last_name', '')

    if not email:
        flash('Nie udało się pobrać adresu email z konta. Upewnij się, że konto ma przypisany email.', 'error')
        return redirect(url_for('auth.login'))

    # 1. Szukaj usera po OAuth ID
    if provider == 'google':
        user = User.get_by_google_id(oauth_id)
    else:
        user = User.get_by_facebook_id(oauth_id)

    # 2. Jeśli nie znaleziono po OAuth ID → szukaj po emailu
    if user is None:
        user = User.get_by_email(email)

        if user:
            # Dowiąż OAuth ID do istniejącego konta
            if provider == 'google':
                user.google_id = oauth_id
            else:
                user.facebook_id = oauth_id
            # Oznacz email jako zweryfikowany (provider gwarantuje)
            was_unverified = not user.email_verified
            if was_unverified:
                user.email_verified = True
            db.session.commit()
            if was_unverified:
                try:
                    from modules.achievements.services import AchievementService
                    AchievementService().check_event(user, 'email_verify')
                except Exception:
                    pass
        else:
            # 3. Stwórz nowe konto
            user = User(
                email=email,
                role='client',
                is_active=True,
                email_verified=True,
                profile_completed=False,
                first_name=first_name or None,
                last_name=last_name or None,
            )
            if provider == 'google':
                user.google_id = oauth_id
            else:
                user.facebook_id = oauth_id

            db.session.add(user)
            db.session.commit()

            # Wyślij email powitalny
            EmailManager.send_welcome(user)

    # Sprawdź czy konto aktywne
    if not user.is_active:
        token = secrets.token_urlsafe(32)
        session['reactivation_token'] = token
        session['reactivation_user_id'] = user.id
        return redirect(url_for('auth.account_deactivated'))

    # Zaloguj użytkownika
    login_user(user, remember=True)
    user.update_last_login()
    user.update_login_streak()

    # Redirect
    if not user.profile_completed:
        return redirect(url_for('auth.complete_profile'))

    if user.role in ['admin', 'mod']:
        return redirect(url_for('admin.dashboard'))
    return redirect(url_for('client.dashboard'))


# =============================================
# Complete Profile (2-step wizard)
# =============================================

@auth_bp.route('/complete-profile', methods=['GET', 'POST'])
@login_required
def complete_profile():
    """
    Strona dokończenia profilu (2-krokowy wizard).
    Krok 1: dane osobowe (imię, nazwisko, telefon)
    Krok 2: wybór avatara

    GET: renderuje wizard z odpowiednim krokiem
    POST (AJAX): zapisuje dane osobowe (krok 1)
    """
    # Jeśli profil jest już kompletny, przekieruj na dashboard
    if current_user.profile_completed:
        if current_user.role in ['admin', 'mod']:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('client.dashboard'))

    # Ustal aktualny krok
    # Krok 1 wymaga imienia, nazwiska i telefonu (OAuth daje imię/nazwisko, ale nie telefon)
    current_step = 1
    if (current_user.first_name and current_user.first_name.strip()
            and current_user.phone and current_user.phone.strip()):
        current_step = 2

    form = CompleteProfileForm()

    # POST — zapis danych osobowych (krok 1, AJAX)
    if request.method == 'POST':
        if form.validate_on_submit():
            # Połącz prefix + numer telefonu
            phone_prefix = form.phone_prefix.data.strip() if form.phone_prefix.data else '+48'
            phone_number = form.phone_number.data.strip() if form.phone_number.data else ''
            full_phone = f"{phone_prefix}{phone_number}"

            # Pobierz zgodę na analytics
            analytics_consent = request.form.get('analytics_consent') == 'on'

            current_user.first_name = form.first_name.data.strip()
            current_user.last_name = form.last_name.data.strip()
            current_user.phone = full_phone
            current_user.analytics_consent = analytics_consent
            db.session.commit()

            # Check profile achievements
            from modules.achievements.services import AchievementService
            AchievementService().check_event(current_user, 'profile_update')

            return jsonify({'success': True})
        else:
            # Zbierz błędy walidacji
            errors = {}
            for field_name, field_errors in form.errors.items():
                errors[field_name] = field_errors[0] if field_errors else ''
            return jsonify({'success': False, 'errors': errors}), 400

    # GET — pre-fill danymi OAuth (jeśli użytkownik logował przez Google/Facebook)
    if request.method == 'GET' and current_step == 1:
        if current_user.first_name and not form.first_name.data:
            form.first_name.data = current_user.first_name
        if current_user.last_name and not form.last_name.data:
            form.last_name.data = current_user.last_name

    # GET — renderuj wizard
    from modules.profile.models import AvatarSeries
    series_list = AvatarSeries.get_all_ordered()
    has_avatars = any(s.avatar_count > 0 for s in series_list)

    return render_template(
        'auth/complete_profile.html',
        form=form,
        current_step=current_step,
        series_list=series_list,
        has_avatars=has_avatars,
        current_avatar_id=current_user.avatar_id
    )


@auth_bp.route('/complete-profile/save-avatar', methods=['POST'])
@login_required
def complete_profile_save_avatar():
    """
    Zapis avatara (krok 2) i oznaczenie profilu jako kompletny.
    POST (AJAX): zapisuje avatar_id, ustawia profile_completed=True
    """
    from modules.profile.models import Avatar

    avatar_id = request.form.get('avatar_id', type=int)

    if not avatar_id:
        return jsonify({'success': False, 'error': 'Nie wybrano avatara.'}), 400

    avatar = Avatar.query.get(avatar_id)
    if not avatar:
        return jsonify({'success': False, 'error': 'Wybrany avatar nie istnieje.'}), 400

    try:
        current_user.avatar_id = avatar_id
        current_user.profile_completed = True
        db.session.commit()

        # Check achievements for profile completion and avatar
        from modules.achievements.services import AchievementService
        AchievementService().check_event(current_user, 'profile_update')
        AchievementService().check_event(current_user, 'avatar_change')

        # Ustal URL dashboardu
        if current_user.role in ['admin', 'mod']:
            redirect_url = url_for('admin.dashboard')
        else:
            redirect_url = url_for('client.dashboard')

        return jsonify({'success': True, 'redirect_url': redirect_url})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Wystąpił błąd. Spróbuj ponownie.'}), 500


