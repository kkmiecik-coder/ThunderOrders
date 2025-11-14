"""
Utility Decorators
Dekoratory pomocnicze do kontroli dostępu i innych funkcjonalności
"""

from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user


def role_required(*roles):
    """
    Dekorator sprawdzający czy użytkownik ma wymaganą rolę

    Usage:
        @role_required('admin')
        @role_required('admin', 'mod')

    Args:
        *roles: Lista dopuszczalnych ról

    Returns:
        Decorator function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Sprawdź czy użytkownik jest zalogowany
            if not current_user.is_authenticated:
                flash('Musisz być zalogowany, aby uzyskać dostęp do tej strony.', 'warning')
                return redirect(url_for('auth.login'))

            # Sprawdź czy użytkownik ma odpowiednią rolę
            if current_user.role not in roles:
                flash('Nie masz uprawnień do tej strony.', 'error')
                abort(403)  # Forbidden

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """
    Dekorator wymagający roli admin
    Skrót dla @role_required('admin')

    Usage:
        @admin_required
        def admin_only_view():
            pass
    """
    return role_required('admin')(f)


def mod_required(f):
    """
    Dekorator wymagający roli admin lub mod

    Usage:
        @mod_required
        def mod_view():
            pass
    """
    return role_required('admin', 'mod')(f)


def email_verified_required(f):
    """
    Dekorator wymagający zweryfikowanego emaila

    Usage:
        @email_verified_required
        def verified_only_view():
            pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Musisz być zalogowany.', 'warning')
            return redirect(url_for('auth.login'))

        if not current_user.email_verified:
            flash('Musisz zweryfikować swój adres email.', 'warning')
            return redirect(url_for('auth.resend_verification'))

        return f(*args, **kwargs)
    return decorated_function


def active_user_required(f):
    """
    Dekorator wymagający aktywnego konta (is_active=True)

    Usage:
        @active_user_required
        def active_only_view():
            pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Musisz być zalogowany.', 'warning')
            return redirect(url_for('auth.login'))

        if not current_user.is_active:
            flash('Twoje konto zostało dezaktywowane. Skontaktuj się z administratorem.', 'error')
            return redirect(url_for('auth.login'))

        return f(*args, **kwargs)
    return decorated_function
