"""
Auth Module - User Model
Model użytkownika z metodami autentykacji
"""

from datetime import datetime, timedelta, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import random

# Import db z extensions.py (unika circular import)
from extensions import db


def get_local_now():
    """
    Zwraca aktualny czas polski (Europe/Warsaw).
    Używa stałego offsetu +1h (CET) lub +2h (CEST) w zależności od daty.
    Zwraca naive datetime dla porównań z naive datetime w bazie.
    """
    utc_now = datetime.now(timezone.utc)

    # Prosty algorytm DST dla Polski:
    # CEST (UTC+2): ostatnia niedziela marca do ostatniej niedzieli października
    # CET (UTC+1): reszta roku
    year = utc_now.year

    # Ostatnia niedziela marca
    march_last = datetime(year, 3, 31, tzinfo=timezone.utc)
    march_last_sunday = march_last - timedelta(days=(march_last.weekday() + 1) % 7)
    dst_start = march_last_sunday.replace(hour=1)  # 01:00 UTC

    # Ostatnia niedziela października
    oct_last = datetime(year, 10, 31, tzinfo=timezone.utc)
    oct_last_sunday = oct_last - timedelta(days=(oct_last.weekday() + 1) % 7)
    dst_end = oct_last_sunday.replace(hour=1)  # 01:00 UTC

    # Sprawdź czy jesteśmy w czasie letnim
    if dst_start <= utc_now < dst_end:
        offset = timedelta(hours=2)  # CEST
    else:
        offset = timedelta(hours=1)  # CET

    # Zwróć naive datetime w czasie polskim
    return (utc_now + offset).replace(tzinfo=None)


class User(UserMixin, db.Model):
    """
    Model użytkownika
    Tabela: users
    """
    __tablename__ = 'users'

    # Primary Key
    id = db.Column(db.Integer, primary_key=True)

    # Basic Info
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)

    # Role & Permissions
    role = db.Column(
        db.Enum('admin', 'mod', 'client', name='user_roles'),
        default='client',
        nullable=False,
        index=True
    )

    # Contact
    phone = db.Column(db.String(20), nullable=False)

    # Status
    is_active = db.Column(db.Boolean, default=True)
    email_verified = db.Column(db.Boolean, default=False)

    # Deactivation (by admin)
    deactivation_reason = db.Column(db.Text)
    deactivated_at = db.Column(db.DateTime)
    deactivated_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Verification & Reset Tokens (legacy - kept for backward compatibility)
    email_verification_token = db.Column(db.String(255), index=True)
    password_reset_token = db.Column(db.String(255), index=True)
    password_reset_expires = db.Column(db.DateTime)

    # New 6-digit code verification system
    email_verification_code = db.Column(db.String(6))
    email_verification_code_expires = db.Column(db.DateTime)
    email_verification_code_sent_at = db.Column(db.DateTime)
    email_verification_attempts = db.Column(db.Integer, default=0)
    email_verification_locked_until = db.Column(db.DateTime)
    verification_session_token = db.Column(db.String(64), index=True)

    # Timestamps
    last_login = db.Column(db.DateTime)

    # User Preferences
    dark_mode_enabled = db.Column(db.Boolean, default=False)
    sidebar_collapsed = db.Column(db.Boolean, default=False)

    # Privacy & Analytics
    analytics_consent = db.Column(
        db.Boolean,
        default=None,
        nullable=True,
        comment='Zgoda na cookies analityczne (Google Analytics). NULL=nie podjęto decyzji, TRUE=zgoda, FALSE=odmowa'
    )

    # Avatar
    avatar_id = db.Column(db.Integer, db.ForeignKey('avatars.id'), index=True)

    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(
        db.DateTime,
        default=get_local_now,
        onupdate=get_local_now
    )

    # Relationships
    avatar = db.relationship('Avatar', backref='users', foreign_keys=[avatar_id])
    orders = db.relationship('Order', back_populates='user', lazy='dynamic')
    order_comments = db.relationship('OrderComment', back_populates='user', lazy='dynamic')
    shipping_addresses = db.relationship('ShippingAddress', back_populates='user', lazy='dynamic')
    # activity_logs = db.relationship('ActivityLog', backref='user', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.email}>'

    # ============================================
    # Password Methods
    # ============================================

    def set_password(self, password):
        """
        Hashuje i zapisuje hasło

        Args:
            password (str): Hasło w plain text
        """
        # Użyj pbkdf2:sha256 dla kompatybilności z Python 3.9
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        """
        Sprawdza czy hasło jest poprawne

        Args:
            password (str): Hasło do sprawdzenia

        Returns:
            bool: True jeśli hasło poprawne
        """
        return check_password_hash(self.password_hash, password)

    # ============================================
    # Token Generation Methods
    # ============================================

    def generate_verification_token(self):
        """
        Generuje token weryfikacji emaila

        Returns:
            str: Unikalny token
        """
        self.email_verification_token = secrets.token_urlsafe(32)
        return self.email_verification_token

    def generate_password_reset_token(self, expires_in=3600):
        """
        Generuje token resetu hasła

        Args:
            expires_in (int): Czas wygaśnięcia w sekundach (default: 1h)

        Returns:
            str: Unikalny token
        """
        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_expires = get_local_now() + timedelta(seconds=expires_in)
        return self.password_reset_token

    def verify_password_reset_token(self, token):
        """
        Sprawdza czy token resetu hasła jest ważny

        Args:
            token (str): Token do sprawdzenia

        Returns:
            bool: True jeśli token ważny i nie wygasł
        """
        if self.password_reset_token != token:
            return False

        if self.password_reset_expires and get_local_now() > self.password_reset_expires:
            return False

        return True

    def clear_password_reset_token(self):
        """Czyści token resetu hasła po użyciu"""
        self.password_reset_token = None
        self.password_reset_expires = None

    # ============================================
    # Email Verification Methods (6-digit code system)
    # ============================================

    def generate_verification_code(self):
        """
        Generuje 6-cyfrowy kod weryfikacyjny i token sesji.
        Kod ważny przez 24h.

        Returns:
            tuple: (code, session_token)
        """
        # Generuj 6-cyfrowy kod
        self.email_verification_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])

        # Ustaw czas wygaśnięcia (24h)
        self.email_verification_code_expires = get_local_now() + timedelta(hours=24)

        # Zapisz czas wysłania (do cooldown 60s)
        self.email_verification_code_sent_at = get_local_now()

        # Resetuj licznik prób
        self.email_verification_attempts = 0
        self.email_verification_locked_until = None

        # Generuj token sesji weryfikacji
        self.verification_session_token = secrets.token_urlsafe(32)

        return self.email_verification_code, self.verification_session_token

    def verify_code(self, code):
        """
        Weryfikuje podany kod. Obsługuje blokadę po 5 nieudanych próbach.

        Args:
            code (str): 6-cyfrowy kod do weryfikacji

        Returns:
            tuple: (success: bool, error_message: str|None)
        """
        # Sprawdź czy weryfikacja nie jest zablokowana
        if self.is_verification_locked():
            remaining = (self.email_verification_locked_until - get_local_now()).seconds // 60
            return False, f'Weryfikacja zablokowana. Spróbuj ponownie za {remaining + 1} minut.'

        # Sprawdź czy kod nie wygasł
        if not self.email_verification_code_expires or get_local_now() > self.email_verification_code_expires:
            return False, 'Kod weryfikacyjny wygasł. Wyślij nowy kod.'

        # Sprawdź kod
        if self.email_verification_code != code:
            self.email_verification_attempts = (self.email_verification_attempts or 0) + 1

            # Blokada po 5 próbach
            if self.email_verification_attempts >= 5:
                self.email_verification_locked_until = get_local_now() + timedelta(minutes=15)
                return False, 'Zbyt wiele nieudanych prób. Weryfikacja zablokowana na 15 minut.'

            remaining = 5 - self.email_verification_attempts
            return False, f'Niepoprawny kod. Pozostało prób: {remaining}.'

        # Kod poprawny - weryfikuj email
        self.verify_email()
        return True, None

    def verify_email(self):
        """Oznacza email jako zweryfikowany i czyści dane weryfikacji"""
        self.email_verified = True
        # Wyczyść stary system tokenów
        self.email_verification_token = None
        # Wyczyść nowy system kodów
        self.email_verification_code = None
        self.email_verification_code_expires = None
        self.email_verification_code_sent_at = None
        self.email_verification_attempts = 0
        self.email_verification_locked_until = None
        self.verification_session_token = None

    def can_resend_code(self):
        """
        Sprawdza czy można wysłać nowy kod (cooldown 60s).

        Returns:
            tuple: (can_resend: bool, seconds_remaining: int)
        """
        if not self.email_verification_code_sent_at:
            return True, 0

        elapsed = (get_local_now() - self.email_verification_code_sent_at).total_seconds()
        if elapsed >= 60:
            return True, 0

        return False, int(60 - elapsed)

    def resend_verification_code(self):
        """
        Generuje nowy kod weryfikacyjny (unieważnia poprzedni).
        Token sesji pozostaje ten sam.

        Returns:
            str: Nowy 6-cyfrowy kod lub None jeśli cooldown aktywny
        """
        can_resend, _ = self.can_resend_code()
        if not can_resend:
            return None

        # Generuj nowy kod (unieważnia poprzedni)
        self.email_verification_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])

        # Ustaw nowy czas wygaśnięcia (24h)
        self.email_verification_code_expires = get_local_now() + timedelta(hours=24)

        # Zapisz czas wysłania
        self.email_verification_code_sent_at = get_local_now()

        # Resetuj licznik prób przy nowym kodzie
        self.email_verification_attempts = 0
        self.email_verification_locked_until = None

        return self.email_verification_code

    def is_verification_locked(self):
        """
        Sprawdza czy weryfikacja jest zablokowana.

        Returns:
            bool: True jeśli zablokowana
        """
        if not self.email_verification_locked_until:
            return False

        return get_local_now() < self.email_verification_locked_until

    @classmethod
    def get_by_verification_session_token(cls, token):
        """
        Znajduje użytkownika po tokenie sesji weryfikacji.

        Args:
            token (str): Token sesji weryfikacji

        Returns:
            User|None: Obiekt użytkownika lub None
        """
        return cls.query.filter_by(verification_session_token=token).first()

    # ============================================
    # Helper Methods
    # ============================================

    @property
    def full_name(self):
        """Zwraca pełne imię i nazwisko"""
        return f"{self.first_name} {self.last_name}"

    @property
    def has_avatar(self):
        """Sprawdza czy użytkownik ma wybrany avatar"""
        return self.avatar_id is not None

    @property
    def avatar_url(self):
        """Zwraca URL avatara lub None jeśli nie ma"""
        if self.avatar:
            return self.avatar.url
        return None

    def is_admin(self):
        """Sprawdza czy użytkownik jest adminem"""
        return self.role == 'admin'

    def is_mod(self):
        """Sprawdza czy użytkownik jest moderatorem"""
        return self.role == 'mod'

    def is_client(self):
        """Sprawdza czy użytkownik jest klientem"""
        return self.role == 'client'

    def has_permission(self, permission):
        """
        Sprawdza czy użytkownik ma dane uprawnienie

        Args:
            permission (str): Nazwa uprawnienia ('admin', 'mod')

        Returns:
            bool: True jeśli ma uprawnienie
        """
        if permission == 'admin':
            return self.is_admin()
        elif permission == 'mod':
            return self.is_admin() or self.is_mod()
        return True

    def update_last_login(self):
        """Aktualizuje timestamp ostatniego logowania"""
        self.last_login = get_local_now()
        db.session.commit()

    def deactivate(self, reason, deactivated_by_user_id):
        """
        Dezaktywuje konto użytkownika

        Args:
            reason (str): Powód dezaktywacji
            deactivated_by_user_id (int): ID admina który dezaktywował
        """
        self.is_active = False
        self.deactivation_reason = reason
        self.deactivated_at = get_local_now()
        self.deactivated_by = deactivated_by_user_id

    def reactivate(self):
        """Reaktywuje konto użytkownika"""
        self.is_active = True
        self.deactivation_reason = None
        self.deactivated_at = None
        self.deactivated_by = None

    # ============================================
    # Class Methods
    # ============================================

    @classmethod
    def get_by_email(cls, email):
        """
        Znajduje użytkownika po emailu

        Args:
            email (str): Email użytkownika

        Returns:
            User|None: Obiekt użytkownika lub None
        """
        return cls.query.filter_by(email=email).first()

    @classmethod
    def get_by_reset_token(cls, token):
        """
        Znajduje użytkownika po tokenie resetu hasła

        Args:
            token (str): Token resetu

        Returns:
            User|None: Obiekt użytkownika lub None
        """
        return cls.query.filter_by(password_reset_token=token).first()

    @classmethod
    def get_by_verification_token(cls, token):
        """
        Znajduje użytkownika po tokenie weryfikacji

        Args:
            token (str): Token weryfikacji

        Returns:
            User|None: Obiekt użytkownika lub None
        """
        return cls.query.filter_by(email_verification_token=token).first()

    # ============================================
    # Flask-Login Required Methods
    # ============================================

    def get_id(self):
        """Zwraca ID użytkownika jako string (wymagane przez Flask-Login)"""
        return str(self.id)

    @property
    def is_authenticated(self):
        """Sprawdza czy użytkownik jest zalogowany"""
        return True

    @property
    def is_anonymous(self):
        """Sprawdza czy użytkownik jest anonimowy"""
        return False

    def get_user_id(self):
        """Alias dla get_id()"""
        return self.get_id()


class Settings(db.Model):
    """
    Model ustawień aplikacji
    Tabela: settings
    """
    __tablename__ = 'settings'

    # Primary Key
    id = db.Column(db.Integer, primary_key=True)

    # Settings Key-Value
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    type = db.Column(
        db.Enum('string', 'integer', 'boolean', 'json', name='setting_types'),
        default='string',
        nullable=False
    )
    description = db.Column(db.String(500))

    # Timestamps
    updated_at = db.Column(
        db.DateTime,
        default=get_local_now,
        onupdate=get_local_now
    )
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self):
        return f'<Settings {self.key}={self.value}>'

    @classmethod
    def get_value(cls, key, default=None):
        """
        Pobiera wartość ustawienia

        Args:
            key (str): Klucz ustawienia
            default: Wartość domyślna jeśli nie znaleziono

        Returns:
            Wartość ustawienia lub default (skonwertowana na odpowiedni typ)
        """
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            return default

        # Convert value based on type
        if setting.type == 'boolean':
            return setting.value.lower() in ('true', '1', 'yes')
        elif setting.type == 'integer':
            return int(setting.value)
        elif setting.type == 'json':
            import json
            return json.loads(setting.value)
        else:  # string
            return setting.value

    @classmethod
    def set_value(cls, key, value, updated_by=None, type='string', description=None):
        """
        Ustawia wartość ustawienia

        Args:
            key (str): Klucz ustawienia
            value: Wartość
            updated_by (int): ID użytkownika aktualizującego
            type (str): Typ wartości
            description (str): Opis ustawienia
        """
        setting = cls.query.filter_by(key=key).first()

        if setting:
            setting.value = str(value)
            setting.type = type
            if updated_by:
                setting.updated_by = updated_by
            if description:
                setting.description = description
        else:
            setting = cls(
                key=key,
                value=str(value),
                type=type,
                updated_by=updated_by,
                description=description
            )
            db.session.add(setting)

        db.session.commit()
        return setting


class ShippingAddress(db.Model):
    """
    Model adresu dostawy klienta
    Obsługuje adresy domowe oraz punkty odbioru (InPost, Orlen Paczka)
    Tabela: shipping_addresses
    """
    __tablename__ = 'shipping_addresses'

    # Primary Key
    id = db.Column(db.Integer, primary_key=True)

    # Foreign Key
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Address Type: 'home' lub 'pickup_point'
    address_type = db.Column(db.String(20), nullable=False)

    # Nazwa adresu (przyjazna nazwa do identyfikacji, np. "Dom", "Biuro", "Mama")
    name = db.Column(db.String(100), nullable=True)

    # Pickup Point fields (dla address_type='pickup_point')
    pickup_courier = db.Column(db.String(50), nullable=True)  # 'InPost' lub 'Orlen Paczka'
    pickup_point_id = db.Column(db.String(50), nullable=True)  # ID paczkomatu (np. 'KRA010', 'WAW001')
    pickup_address = db.Column(db.String(500), nullable=True)  # Pełny adres punktu
    pickup_postal_code = db.Column(db.String(10), nullable=True)
    pickup_city = db.Column(db.String(100), nullable=True)

    # Home Address fields (dla address_type='home')
    shipping_name = db.Column(db.String(200), nullable=True)  # Imię i nazwisko odbiorcy
    shipping_address = db.Column(db.String(500), nullable=True)  # Ulica i numer
    shipping_postal_code = db.Column(db.String(10), nullable=True)
    shipping_city = db.Column(db.String(100), nullable=True)
    shipping_voivodeship = db.Column(db.String(50), nullable=True)
    shipping_country = db.Column(db.String(100), nullable=True, default='Polska')

    # Metadata
    is_default = db.Column(db.Boolean, default=False, index=True)  # Czy domyślny adres
    is_active = db.Column(db.Boolean, default=True, index=True)  # Soft delete

    # Timestamps
    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relationship
    user = db.relationship('User', back_populates='shipping_addresses')

    def __repr__(self):
        if self.address_type == 'pickup_point':
            return f'<ShippingAddress {self.pickup_courier} {self.pickup_point_id}>'
        else:
            return f'<ShippingAddress {self.shipping_name} - {self.shipping_city}>'

    @property
    def display_name(self):
        """Human-readable nazwa adresu do wyświetlenia"""
        # Jeśli jest nazwa własna, użyj jej
        if self.name:
            return self.name
        # Fallback do generowanej nazwy
        if self.address_type == 'pickup_point':
            return f"{self.pickup_courier} - {self.pickup_point_id}"
        else:
            return f"{self.shipping_name}, {self.shipping_city}"

    @property
    def full_address(self):
        """Pełny adres do wyświetlenia"""
        if self.address_type == 'pickup_point':
            # Include pickup point code (e.g. paczkomat ID)
            point_id = f" ({self.pickup_point_id})" if self.pickup_point_id else ""
            return f"{self.pickup_address}, {self.pickup_postal_code} {self.pickup_city}{point_id}"
        else:
            return f"{self.shipping_address}, {self.shipping_postal_code} {self.shipping_city}"
