from extensions import db
from utils.timeutil import UTCDateTime, utcnow


class PaymentMethod(db.Model):
    """
    Metody płatności dla systemu potwierdzeń.
    Każda metoda ma osobne pola dla różnych typów danych.
    """
    __tablename__ = 'payment_methods'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, comment="Nazwa metody (BLIK, Przelew, PayPal, Revolut)")

    # Szczegóły płatności
    recipient = db.Column(db.String(200), nullable=True, comment="Odbiorca przelewu (imię nazwisko / firma)")
    account_number = db.Column(db.String(100), nullable=True, comment="Numer konta / telefon / email")
    account_number_label = db.Column(db.String(100), nullable=True, comment="Etykieta pola account_number (np. Numer konta, Numer telefonu, Email)")
    code = db.Column(db.String(100), nullable=True, comment="Kod Revolut / SWIFT / BIC")
    code_label = db.Column(db.String(100), nullable=True, comment="Etykieta pola code (np. Kod SWIFT, RevTag)")
    transfer_title = db.Column(db.String(200), nullable=True, comment="Szablon tytułu przelewu (np. [NUMER ZAMÓWIENIA])")
    additional_info = db.Column(db.Text, nullable=True, comment="Dodatkowe informacje (opcjonalne)")

    # Logo metody płatności (osobne dla light/dark mode)
    logo_light = db.Column(db.String(300), nullable=True, comment="Ścieżka do logo dla light mode")
    logo_dark = db.Column(db.String(300), nullable=True, comment="Ścieżka do logo dla dark mode")

    # Metadane
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(UTCDateTime, default=utcnow)
    updated_at = db.Column(UTCDateTime, default=utcnow, onupdate=utcnow)

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
            'recipient': self.recipient,
            'account_number': self.account_number,
            'account_number_label': self.account_number_label,
            'code': self.code,
            'code_label': self.code_label,
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
        return f'<PaymentMethod {self.id}: {self.name}>'
