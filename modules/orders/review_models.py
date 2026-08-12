"""Opinie klientów o dostawie i obsłudze (task 869efhwph).

Osobny plik, nie models.py — ten ma już blisko dwa tysiące linii, a opinie są
samodzielnym bytem z własnym cyklem życia. Wzorzec jak modules/offers/reminder_models.py.

Ocena dotyczy PACZKI, nie produktu: na to, co producent włożył do pudełka, nie mamy
wpływu, więc pytanie o ocenę produktu wprowadzałoby klienta w błąd.
"""
from sqlalchemy.orm import validates

from extensions import db
from modules.orders.models import get_local_now


class DeliveryReview(db.Model):
    """Jedna opinia na zlecenie wysyłki."""

    __tablename__ = 'delivery_reviews'

    # Ile dni po wystawieniu klient może zmienić zdanie. Okno chroni przed pomyłką
    # przy klikaniu, a nie domyka rekordu w konkretnej dacie — dlatego liczy się od
    # wystawienia opinii, niezależnie od okna na jej wystawienie.
    OKNO_EDYCJI_DNI = 3

    id = db.Column(db.Integer, primary_key=True)
    shipping_request_id = db.Column(
        db.Integer, db.ForeignKey('shipping_requests.id', ondelete='CASCADE'),
        unique=True, nullable=False, index=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    rating = db.Column(db.SmallInteger, nullable=False)
    comment = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    shipping_request = db.relationship('ShippingRequest', back_populates='review')
    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<DeliveryReview {self.id} sr={self.shipping_request_id} {self.rating}/5>'

    @validates('rating')
    def _sprawdz_ocene(self, key, wartosc):
        """Walidacja przy przypisaniu, nie dopiero przy commicie.

        SmallInteger przyjmie każdą liczbę, a ocena 0 albo 7 zepsułaby średnią
        w statystykach po cichu.
        """
        if wartosc is None or int(wartosc) < 1 or int(wartosc) > 5:
            raise ValueError(f'Ocena musi być liczbą od 1 do 5, otrzymano: {wartosc!r}')
        return int(wartosc)

    @validates('comment')
    def _przytnij_komentarz(self, key, wartosc):
        """Puste pole formularza zapisujemy jako NULL, nie jako pusty łańcuch."""
        if wartosc is None:
            return None
        wartosc = wartosc.strip()
        return wartosc[:2000] or None

    @property
    def mozna_edytowac(self):
        """Czy klient może jeszcze zmienić ocenę."""
        from datetime import timedelta
        if not self.created_at:
            return True
        return get_local_now() - self.created_at <= timedelta(days=self.OKNO_EDYCJI_DNI)
