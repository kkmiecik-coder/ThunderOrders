"""
Popups Module - Modele ogłoszeń/popupów
System wyświetlania modalnych ogłoszeń dla użytkowników
"""

import json
from extensions import db
from modules.auth.models import get_local_now


class Popup(db.Model):
    """
    Model popupa/ogłoszenia
    Tabela: popups
    """
    __tablename__ = 'popups'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=True)
    content = db.Column(db.Text, nullable=False)

    # Status: ręczne włączanie/wyłączanie przez admina
    status = db.Column(
        db.Enum('draft', 'active', 'archived', name='popup_status'),
        default='draft',
        nullable=False,
        index=True
    )

    # Targetowanie - JSON array ról np. '["client"]' lub NULL = wszyscy
    target_roles = db.Column(db.Text, nullable=True)

    # Tryb wyświetlania
    display_mode = db.Column(
        db.Enum('once', 'every_login', 'first_login', name='popup_display_mode'),
        default='once',
        nullable=False
    )

    # CTA (Call To Action)
    cta_text = db.Column(db.String(100), nullable=True)
    cta_url = db.Column(db.String(500), nullable=True)
    cta_color = db.Column(db.String(20), nullable=True, default='#f093fb')

    # Wygląd
    bg_color = db.Column(db.String(20), nullable=True)
    modal_size = db.Column(
        db.Enum('sm', 'md', 'lg', name='popup_modal_size'),
        default='md',
        nullable=False
    )

    # Priorytet (niższy = ważniejszy)
    priority = db.Column(db.Integer, default=0, nullable=False)

    # Metadane
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relacje
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_popups')
    views = db.relationship('PopupView', backref='popup', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Popup {self.id}: {self.title}>'

    def get_target_roles(self):
        """Zwraca listę ról docelowych lub None (wszyscy)"""
        if not self.target_roles:
            return None
        try:
            return json.loads(self.target_roles)
        except (json.JSONDecodeError, TypeError):
            return None

    def set_target_roles(self, roles):
        """Ustawia role docelowe z listy"""
        if not roles:
            self.target_roles = None
        else:
            self.target_roles = json.dumps(roles)

    def is_targeted_at(self, user):
        """Sprawdza czy popup jest skierowany do danego użytkownika"""
        roles = self.get_target_roles()
        if roles is None:
            return True
        return user.role in roles

    @property
    def views_count(self):
        """Liczba wyświetleń"""
        return self.views.filter_by(action='viewed').count()

    @property
    def dismissed_count(self):
        """Liczba zamknięć"""
        return self.views.filter_by(action='dismissed').count()

    @property
    def cta_clicked_count(self):
        """Liczba kliknięć CTA"""
        return self.views.filter_by(action='cta_clicked').count()

    @property
    def avg_display_time_ms(self):
        """Średni czas wyświetlania popupa w milisekundach"""
        result = db.session.query(
            db.func.avg(PopupView.duration_ms)
        ).filter(
            PopupView.popup_id == self.id,
            PopupView.duration_ms.isnot(None)
        ).scalar()
        return int(result) if result else 0

    @property
    def unique_viewers_count(self):
        """Liczba unikalnych użytkowników, którzy widzieli popup"""
        return db.session.query(
            db.func.count(db.func.distinct(PopupView.user_id))
        ).filter(
            PopupView.popup_id == self.id,
            PopupView.action == 'viewed'
        ).scalar() or 0


class PopupView(db.Model):
    """
    Model statystyk wyświetleń popupów
    Tabela: popup_views
    """
    __tablename__ = 'popup_views'

    id = db.Column(db.Integer, primary_key=True)
    popup_id = db.Column(
        db.Integer,
        db.ForeignKey('popups.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    action = db.Column(
        db.Enum('viewed', 'dismissed', 'cta_clicked', name='popup_view_action'),
        nullable=False
    )
    duration_ms = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=get_local_now)

    # Relacja do usera
    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<PopupView popup={self.popup_id} user={self.user_id} action={self.action}>'
