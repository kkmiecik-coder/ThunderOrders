import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import Flask, render_template, redirect, url_for

# Import rozszerzeń z extensions.py (rozwiązuje circular imports)
from extensions import db, migrate, login_manager, mail, csrf, executor

# Strefa czasowa dla Polski
POLAND_TZ = ZoneInfo('Europe/Warsaw')


def create_app(config_name=None):
    """
    Application Factory Pattern
    Tworzy i konfiguruje instancję aplikacji Flask
    """
    app = Flask(__name__)

    # Załaduj konfigurację
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    from config import config
    app.config.from_object(config[config_name])

    # Inicjalizuj rozszerzenia
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    executor.init_app(app)

    # Konfiguracja Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Zaloguj się, aby uzyskać dostęp do tej strony.'
    login_manager.login_message_category = 'warning'

    # User loader dla Flask-Login (zostanie uzupełniony w module auth)
    @login_manager.user_loader
    def load_user(user_id):
        # Import tutaj aby uniknąć circular imports
        from modules.auth.models import User
        return User.query.get(int(user_id))

    # Rejestracja blueprintów (modułów)
    register_blueprints(app)

    # Error handlers (strony błędów)
    register_error_handlers(app)

    # Context processors (zmienne globalne w templates)
    register_context_processors(app)

    # Template filters (filtry Jinja2)
    register_template_filters(app)

    # Utwórz folder uploads jeśli nie istnieje
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    return app


def register_blueprints(app):
    """
    Rejestruje wszystkie blueprinty (moduły aplikacji)
    Lazy loading - blueprinty są ładowane tylko gdy potrzebne
    """

    # Import blueprintów (zostaną stworzone w kolejnych etapach)
    # Na razie są zakomentowane - odkomentujemy gdy je stworzymy

    # Auth module
    from modules.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # Client module
    from modules.client import client_bp
    app.register_blueprint(client_bp, url_prefix='/client')

    # Admin module
    from modules.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Products module
    from modules.products import products_bp
    app.register_blueprint(products_bp)

    # Orders module
    from modules.orders import orders_bp
    app.register_blueprint(orders_bp)

    # Exclusive module (publiczne strony zamówień pre-order)
    # CSRF exempt dla API endpoints rezerwacji (reserve, release, extend, restore, availability)
    from modules.exclusive import exclusive_bp
    csrf.exempt(exclusive_bp)
    app.register_blueprint(exclusive_bp)

    # API module (CSRF exempt for AJAX requests)
    from modules.api import api_bp
    csrf.exempt(api_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Analytics API (CSRF exempt for consent updates)
    from modules.api.analytics import analytics_bp
    csrf.exempt(analytics_bp)
    app.register_blueprint(analytics_bp)

    # Imports module (CSRF exempt for file uploads)
    from modules.imports import imports_bp
    csrf.exempt(imports_bp)
    app.register_blueprint(imports_bp)

    # Profile module (wspólny dla wszystkich ról)
    from modules.profile import profile_bp
    app.register_blueprint(profile_bp, url_prefix='/profile')

    # Payments module
    from modules.payments import payments_bp
    app.register_blueprint(payments_bp)

    # Feedback module (ankiety i zbieranie opinii)
    from modules.feedback import feedback_bp
    app.register_blueprint(feedback_bp)

    # Strona główna - smart redirect
    @app.route('/')
    def index():
        """
        Strona główna:
        - Jeśli użytkownik niezalogowany → Pokaż stronę logowania
        - Jeśli zalogowany → Przekieruj na odpowiedni dashboard
        """
        from flask_login import current_user

        if current_user.is_authenticated:
            # Redirect zalogowanych użytkowników na dashboard
            if current_user.role in ['admin', 'mod']:
                return redirect(url_for('admin.dashboard'))
            else:
                return redirect(url_for('client.dashboard'))
        else:
            # Pokaż stronę logowania dla niezalogowanych
            return redirect(url_for('auth.login'))

    # Polityka Prywatności (RODO-compliant)
    @app.route('/privacy-policy')
    def privacy_policy():
        """
        Strona polityki prywatności (RODO/GDPR compliance)
        Dostępna publicznie dla wszystkich użytkowników
        """
        return render_template('legal/privacy_policy.html')


def register_error_handlers(app):
    """Rejestruje handlery dla błędów HTTP"""

    @app.errorhandler(403)
    def forbidden(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(error):
        db.session.rollback()  # Rollback na wypadek błędu bazy danych
        return render_template('errors/500.html'), 500


def register_context_processors(app):
    """
    Rejestruje context processors
    Zmienne/funkcje dostępne globalnie we wszystkich templates
    """

    @app.context_processor
    def inject_globals():
        """Wstrzykuje zmienne globalne do wszystkich szablonów"""
        from modules.payments.models import PaymentMethod

        def get_active_payment_methods():
            """Pomocnicza funkcja do pobierania aktywnych metod płatności"""
            return PaymentMethod.get_active()

        return {
            'app_name': 'ThunderOrders',
            'app_version': '1.0.0-MVP',
            'get_active_payment_methods': get_active_payment_methods,
        }


def register_template_filters(app):
    """
    Rejestruje filtry Jinja2 do użycia w szablonach
    """

    @app.template_filter('to_poland_tz')
    def to_poland_tz_filter(dt):
        """
        Konwertuje datetime UTC na czas polski (Europe/Warsaw).
        Użycie w template: {{ date|to_poland_tz }}
        """
        if dt is None:
            return None
        # Jeśli datetime nie ma timezone, zakładamy że jest UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(POLAND_TZ)

    @app.template_filter('format_datetime')
    def format_datetime_filter(dt, fmt='%Y-%m-%d %H:%M'):
        """
        Formatuje datetime.
        Naive datetime traktowany jako czas polski (nie konwertujemy).
        Aware datetime konwertowany na czas polski.
        Użycie: {{ date|format_datetime }} lub {{ date|format_datetime('%d.%m.%Y %H:%M') }}
        """
        if dt is None:
            return ''
        # Naive datetime = już czas polski, nie konwertujemy
        if dt.tzinfo is not None:
            dt = dt.astimezone(POLAND_TZ)
        return dt.strftime(fmt)

    @app.template_filter('format_date')
    def format_date_filter(dt, fmt='%Y-%m-%d'):
        """
        Formatuje tylko datę.
        Naive datetime traktowany jako czas polski (nie konwertujemy).
        Użycie: {{ date|format_date }} lub {{ date|format_date('%d.%m.%Y') }}
        """
        if dt is None:
            return ''
        # Naive datetime = już czas polski, nie konwertujemy
        if dt.tzinfo is not None:
            dt = dt.astimezone(POLAND_TZ)
        return dt.strftime(fmt)

    @app.template_filter('format_time')
    def format_time_filter(dt, fmt='%H:%M'):
        """
        Formatuje tylko godzinę.
        Naive datetime traktowany jako czas polski (nie konwertujemy).
        Użycie: {{ date|format_time }} lub {{ date|format_time('%H:%M:%S') }}
        """
        if dt is None:
            return ''
        # Naive datetime = już czas polski, nie konwertujemy
        if dt.tzinfo is not None:
            dt = dt.astimezone(POLAND_TZ)
        return dt.strftime(fmt)

    @app.template_filter('format_datetime_local')
    def format_datetime_local_filter(dt):
        """
        Formatuje datetime dla input type="datetime-local".
        Naive datetime traktowany jako czas polski (nie konwertujemy).
        Użycie: {{ date|format_datetime_local }}
        """
        if dt is None:
            return ''
        # Naive datetime = już czas polski, nie konwertujemy
        if dt.tzinfo is not None:
            dt = dt.astimezone(POLAND_TZ)
        return dt.strftime('%Y-%m-%dT%H:%M')

    @app.template_filter('format_currency')
    def format_currency_filter(value, currency='PLN'):
        """
        Formatuje kwotę jako walutę.
        Użycie: {{ amount|format_currency }} lub {{ amount|format_currency('USD') }}
        """
        if value is None:
            return '0,00 PLN'

        # Konwertuj do float jeśli potrzeba
        try:
            value = float(value)
        except (ValueError, TypeError):
            return '0,00 PLN'

        # Formatuj z przecinkiem jako separator dziesiętny (polski standard)
        formatted = f"{value:,.2f}".replace(',', ' ').replace('.', ',')

        return f"{formatted} {currency}"

    @app.template_filter('reject_key')
    def reject_key_filter(d, key):
        """
        Zwraca kopię słownika bez podanego klucza.
        Użycie: {{ request.args|reject_key('status') }}
        """
        if not isinstance(d, dict):
            # Dla ImmutableMultiDict (request.args)
            result = {}
            for k in d.keys():
                if k != key:
                    # Pobierz wszystkie wartości dla klucza (dla multi-value)
                    values = d.getlist(k)
                    if len(values) == 1:
                        result[k] = values[0]
                    else:
                        result[k] = values
            return result
        return {k: v for k, v in d.items() if k != key}


# Uruchomienie aplikacji (tylko dla development)
if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5001, debug=True)
