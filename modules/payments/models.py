from extensions import db
from datetime import datetime, timezone, timedelta



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

class PaymentMethod(db.Model):
    """
    Metody płatności dla systemu potwierdzeń.
    Każda metoda ma osobne pola dla różnych typów danych.
    """
    __tablename__ = 'payment_methods'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, comment="Nazwa metody (BLIK, Przelew, PayPal, Revolut)")

    # Typ metody płatności
    method_type = db.Column(
        db.String(20),
        nullable=False,
        default='other',
        comment="Typ: 'transfer' (przelew), 'instant' (BLIK), 'online' (PayPal/Revolut), 'other'"
    )

    # Szczegóły płatności - różne dla różnych typów
    recipient = db.Column(db.String(200), nullable=True, comment="Odbiorca przelewu (imię nazwisko / firma)")
    account_number = db.Column(db.String(100), nullable=True, comment="Numer konta / telefon / email")
    code = db.Column(db.String(100), nullable=True, comment="Kod Revolut / SWIFT / BIC")
    transfer_title = db.Column(db.String(200), nullable=True, comment="Szablon tytułu przelewu (np. [NUMER ZAMÓWIENIA])")
    additional_info = db.Column(db.Text, nullable=True, comment="Dodatkowe informacje (opcjonalne)")

    # Logo metody płatności (osobne dla light/dark mode)
    logo_light = db.Column(db.String(300), nullable=True, comment="Ścieżka do logo dla light mode")
    logo_dark = db.Column(db.String(300), nullable=True, comment="Ścieżka do logo dla dark mode")

    # Metadane
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @classmethod
    def get_active(cls):
        """Zwraca aktywne metody płatności posortowane"""
        return cls.query.filter_by(is_active=True).order_by(cls.sort_order, cls.name).all()

    def to_dict(self):
        """
        Zwraca słownik z danymi metody płatności.
        Używane w API dla panelu klienta.
        """
        return {
            'id': self.id,
            'name': self.name,
            'method_type': self.method_type,
            'recipient': self.recipient,
            'account_number': self.account_number,
            'code': self.code,
            'transfer_title': self.transfer_title,
            'additional_info': self.additional_info,
            'is_active': self.is_active,
            'sort_order': self.sort_order,
            'logo_light': self.logo_light,
            'logo_dark': self.logo_dark,
            'logo_light_url': f'/static/uploads/payment_methods/{self.logo_light}' if self.logo_light else None,
            'logo_dark_url': f'/static/uploads/payment_methods/{self.logo_dark}' if self.logo_dark else None
        }

    def __repr__(self):
        return f'<PaymentMethod {self.id}: {self.name} ({self.method_type})>'
