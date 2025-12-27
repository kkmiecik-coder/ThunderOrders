"""
Profile Module - Avatar Models
Modele serii avatarów i avatarów
"""

from datetime import datetime, timezone, timedelta
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

class AvatarSeries(db.Model):
    """
    Model serii avatarów (np. K-pop, Animals, Abstract)
    Tabela: avatar_series
    """
    __tablename__ = 'avatar_series'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    avatars = db.relationship('Avatar', backref='series', lazy='dynamic',
                              cascade='all, delete-orphan', order_by='Avatar.sort_order')

    def __repr__(self):
        return f'<AvatarSeries {self.name}>'

    @property
    def avatar_count(self):
        """Zwraca liczbę avatarów w serii"""
        return self.avatars.count()

    @property
    def folder_path(self):
        """Zwraca ścieżkę do folderu serii"""
        return f'uploads/avatars/{self.slug}'

    @classmethod
    def get_all_ordered(cls):
        """Pobiera wszystkie serie posortowane po sort_order"""
        return cls.query.order_by(cls.sort_order.asc()).all()

    @classmethod
    def get_by_slug(cls, slug):
        """Znajduje serię po slug"""
        return cls.query.filter_by(slug=slug).first()

    def get_next_avatar_number(self):
        """Zwraca następny numer dla avatara w serii"""
        # Używamy bezpośredniego query zamiast relationship, żeby uniknąć problemów z cache
        max_order = db.session.query(db.func.max(Avatar.sort_order))\
            .filter(Avatar.series_id == self.id).scalar()
        if max_order:
            return max_order + 1
        return 1


class Avatar(db.Model):
    """
    Model avatara
    Tabela: avatars
    """
    __tablename__ = 'avatars'

    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey('avatar_series.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=get_local_now)

    def __repr__(self):
        return f'<Avatar {self.filename}>'

    @property
    def url(self):
        """Zwraca URL do avatara"""
        from flask import url_for
        return url_for('static', filename=f'uploads/avatars/{self.series.slug}/{self.filename}')

    @property
    def file_path(self):
        """Zwraca pełną ścieżkę do pliku"""
        return f'static/uploads/avatars/{self.series.slug}/{self.filename}'

    @classmethod
    def get_by_id(cls, avatar_id):
        """Znajduje avatar po ID"""
        return cls.query.get(avatar_id)
