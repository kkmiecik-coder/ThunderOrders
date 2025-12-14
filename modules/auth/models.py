"""
Auth Module - User Model
Model użytkownika z metodami autentykacji
"""

from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

# Import db z extensions.py (unika circular import)
from extensions import db


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
    phone = db.Column(db.String(20))

    # Status
    is_active = db.Column(db.Boolean, default=True)
    email_verified = db.Column(db.Boolean, default=False)

    # Deactivation (by admin)
    deactivation_reason = db.Column(db.Text)
    deactivated_at = db.Column(db.DateTime)
    deactivated_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Verification & Reset Tokens
    email_verification_token = db.Column(db.String(255), index=True)
    password_reset_token = db.Column(db.String(255), index=True)
    password_reset_expires = db.Column(db.DateTime)

    # Timestamps
    last_login = db.Column(db.DateTime)

    # User Preferences
    dark_mode_enabled = db.Column(db.Boolean, default=False)
    sidebar_collapsed = db.Column(db.Boolean, default=False)

    # Avatar
    avatar_id = db.Column(db.Integer, db.ForeignKey('avatars.id'), index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    avatar = db.relationship('Avatar', backref='users', foreign_keys=[avatar_id])
    orders = db.relationship('Order', back_populates='user', lazy='dynamic')
    order_comments = db.relationship('OrderComment', back_populates='user', lazy='dynamic')
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
        from datetime import timedelta

        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_expires = datetime.utcnow() + timedelta(seconds=expires_in)
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

        if self.password_reset_expires and datetime.utcnow() > self.password_reset_expires:
            return False

        return True

    def clear_password_reset_token(self):
        """Czyści token resetu hasła po użyciu"""
        self.password_reset_token = None
        self.password_reset_expires = None

    # ============================================
    # Email Verification Methods
    # ============================================

    def verify_email(self):
        """Oznacza email jako zweryfikowany"""
        self.email_verified = True
        self.email_verification_token = None

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
        self.last_login = datetime.utcnow()
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
        self.deactivated_at = datetime.utcnow()
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
        default=datetime.utcnow,
        onupdate=datetime.utcnow
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
