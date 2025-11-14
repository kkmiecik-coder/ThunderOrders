import os
from flask import Flask, render_template, redirect, url_for

# Import rozszerzeń z extensions.py (rozwiązuje circular imports)
from extensions import db, migrate, login_manager, mail, csrf, executor


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
    # from modules.orders.routes import orders_bp
    # app.register_blueprint(orders_bp, url_prefix='/orders')

    # Exclusive module
    # from modules.exclusive.routes import exclusive_bp
    # app.register_blueprint(exclusive_bp, url_prefix='/exclusive')

    # API module (CSRF exempt for AJAX requests)
    from modules.api import api_bp
    csrf.exempt(api_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Imports module (CSRF exempt for file uploads)
    from modules.imports import imports_bp
    csrf.exempt(imports_bp)
    app.register_blueprint(imports_bp)

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
        return {
            'app_name': 'ThunderOrders',
            'app_version': '1.0.0-MVP',
        }


# Uruchomienie aplikacji (tylko dla development)
if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5001, debug=True)
