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

    # Zgodne z maxlength w formularzu (confirm_delivery.html). Kolumna to Text bez
    # własnego limitu — to jedyne miejsce, które go egzekwuje, więc musi obowiązywać
    # też dla API (mobile), które nie przechodzi przez ten formularz.
    MAX_DLUGOSC_KOMENTARZA = 2000

    id = db.Column(db.Integer, primary_key=True)
    # Bez index=True: UNIQUE w MariaDB samo zakłada indeks, więc osobny `index=True`
    # nie dodałby nic poza rozjazdem wobec migracji (tam ta kolumna ma tylko
    # UniqueConstraint, bez create_index) — autogenerate próbowałby go co chwilę
    # kasować i tworzyć na nowo.
    shipping_request_id = db.Column(
        db.Integer, db.ForeignKey('shipping_requests.id', ondelete='CASCADE'),
        unique=True, nullable=False)
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

        Ułamek odrzucamy zamiast go obcinać: samo `int(4.9)` zapisywało 4, czyli
        ocenę, której klient nie wystawił — dokładnie ta sama cicha utrata treści,
        którą `_sprawdz_komentarz` odrzuca kilka linii niżej. Ścieżka HTTP (web
        i mobile) łapie to już w `zapisz_ocene`, ale tam kończy się jej zasięg:
        backfill, powłoka i każdy przyszły zapis prosto do modelu omijają tamten
        strażnik, a średnia w statystykach liczy się z tej kolumny.
        """
        blad = ValueError(f'Ocena musi być liczbą od 1 do 5, otrzymano: {wartosc!r}')
        if wartosc is None:
            raise blad
        try:
            ocena = int(wartosc)
        except (TypeError, ValueError, OverflowError):
            # OverflowError: int(float('inf')). Tłumaczymy na ValueError, żeby
            # wołający miał jeden typ wyjątku do złapania.
            raise blad from None
        # Stringi przepuszczamy jak dotąd ("4" to poprawna ocena), bo int() sam
        # odrzuca "4.9". Dla liczb wymagamy, żeby konwersja niczego nie zgubiła.
        if not isinstance(wartosc, str) and ocena != wartosc:
            raise blad
        if ocena < 1 or ocena > 5:
            raise blad
        return ocena

    @validates('comment')
    def _sprawdz_komentarz(self, key, wartosc):
        """Puste pole formularza zapisujemy jako NULL, nie jako pusty łańcuch.

        Wcześniej ucinaliśmy tu komentarz do 2000 znaków po cichu — klient tracił
        końcówkę tego, co napisał, bez żadnego sygnału, że coś zniknęło. Formularz
        ma `maxlength`, więc ścieżka UI i tak nigdy nie wyśle więcej; to zabezpieczenie
        jest realnie dla API (mobile), które omija ten formularz. Ciche obcinanie
        treści wpisanej przez klienta jest gorsze niż jawny błąd, więc odrzucamy.
        """
        if wartosc is None:
            return None
        wartosc = wartosc.strip()
        if not wartosc:
            return None
        if len(wartosc) > self.MAX_DLUGOSC_KOMENTARZA:
            raise ValueError(
                f'Komentarz może mieć maksymalnie {self.MAX_DLUGOSC_KOMENTARZA} znaków')
        return wartosc

    @property
    def mozna_edytowac(self):
        """Czy klient może jeszcze zmienić ocenę."""
        from datetime import timedelta
        if not self.created_at:
            return True
        return get_local_now() - self.created_at <= timedelta(days=self.OKNO_EDYCJI_DNI)
