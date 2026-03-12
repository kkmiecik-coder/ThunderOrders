import os
from dotenv import load_dotenv

# Załaduj zmienne z pliku .env
load_dotenv()

class Config:
    """Bazowa klasa konfiguracyjna - wspólne ustawienia"""

    # Flask Core
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-this')

    # Database
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{os.getenv('DB_USER', 'root')}:"
        f"{os.getenv('DB_PASSWORD', '')}@"
        f"{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '3306')}/"
        f"{os.getenv('DB_NAME', 'thunder_orders')}"
        f"?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
    }

    # Session Configuration
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = int(os.getenv('SESSION_LIFETIME', 604800))  # 7 dni

    # Remember Me Cookie (Flask-Login)
    REMEMBER_COOKIE_DURATION = 30 * 24 * 3600  # 30 dni
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'

    # Upload Configuration
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_UPLOAD_SIZE', 50 * 1024 * 1024))  # 50MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    # Pagination
    ITEMS_PER_PAGE = 20

    # Email Configuration (Hostinger SMTP)
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.hostinger.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 465))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'False').lower() == 'true'
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'True').lower() == 'true'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', 'noreply@thunderorders.cloud')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@thunderorders.cloud')

    # Exchange Rate API
    EXCHANGE_RATE_API_KEY = os.getenv('EXCHANGE_RATE_API_KEY')

    # Google Analytics 4
    GA_MEASUREMENT_ID = os.getenv('GA_MEASUREMENT_ID')

    # GeoIP Database
    GEOIP_DB_PATH = os.environ.get('GEOIP_DB_PATH') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'GeoLite2-City.mmdb')

    # Cloudflare Turnstile (anti-bot CAPTCHA)
    CF_TURNSTILE_SITE_KEY = os.getenv('CF_TURNSTILE_SITE_KEY', '')
    CF_TURNSTILE_SECRET_KEY = os.getenv('CF_TURNSTILE_SECRET_KEY', '')

    # OAuth (Google, Facebook)
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')
    FACEBOOK_CLIENT_ID = os.getenv('FACEBOOK_CLIENT_ID', '')
    FACEBOOK_CLIENT_SECRET = os.getenv('FACEBOOK_CLIENT_SECRET', '')

    # VAPID (Web Push Notifications)
    VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY', '')
    VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY', '')
    VAPID_CLAIMS_EMAIL = os.getenv('VAPID_CLAIMS_EMAIL', 'mailto:noreply@thunderorders.cloud')

    # Security
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # Token nie wygasa


class DevelopmentConfig(Config):
    """Konfiguracja dla środowiska deweloperskiego (lokalnie)"""

    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False  # HTTP dozwolone lokalnie
    REMEMBER_COOKIE_SECURE = False

    # Wyłącz cache dla plików statycznych w development
    SEND_FILE_MAX_AGE_DEFAULT = 0  # Brak cache dla plików statycznych
    TEMPLATES_AUTO_RELOAD = True  # Auto-reload templates

    # Więcej logów w development
    SQLALCHEMY_ECHO = False  # True jeśli chcesz widzieć SQL queries w konsoli


class ProductionConfig(Config):
    """Konfiguracja dla środowiska produkcyjnego (serwer VPS)"""

    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True  # Wymaga HTTPS
    REMEMBER_COOKIE_SECURE = True

    # Zwiększone bezpieczeństwo
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'

    # Wymagaj silniejszego SECRET_KEY w produkcji
    @classmethod
    def init_app(cls, app):
        Config.init_app(app)

        # Sprawdź czy SECRET_KEY nie jest domyślny
        if app.config['SECRET_KEY'] == 'dev-secret-key-change-this':
            raise ValueError(
                'SECRET_KEY musi być zmieniony w produkcji! '
                'Ustaw go w pliku .env'
            )


class TestingConfig(Config):
    """Konfiguracja dla testów (opcjonalnie, na przyszłość)"""

    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'  # Baza w pamięci dla testów
    WTF_CSRF_ENABLED = False  # Wyłącz CSRF w testach


# Słownik wyboru konfiguracji
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
