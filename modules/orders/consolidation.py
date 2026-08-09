"""Konsolidacja zleceń wysyłki — paczka zbiorcza dla kilku klientów (task 869eckz7u).

Paczka zbiorcza jest zwykłym ShippingRequest, dzięki czemu dziedziczy cały pipeline
WMS. Zlecenia źródłowe zostają w bazie: tracą swoje wiersze junction (przeniesione
do zbiorczego ze śladem source_request_id), ale nadal są tym, co widzi ich właściciel.

Funkcje NIE commitują — commituje endpoint, zgodnie z konwencją modułu.
"""
from extensions import db


class ConsolidationError(Exception):
    """Odmowa operacji na konsolidacji. status_code czytany wprost przez endpoint."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# Paczka, która już pojechała, nie podlega scalaniu ani rozmontowaniu.
STATUSY_ZAMKNIETE = ('wyslane', 'dostarczone')


def _sesja_wms_blokujaca(sr):
    """Zwraca aktywną/wstrzymaną sesję WMS trzymającą to zlecenie, albo None."""
    from modules.orders.wms_models import WmsSession, WmsSessionShippingRequest
    return (
        WmsSessionShippingRequest.query.join(WmsSession)
        .filter(
            WmsSessionShippingRequest.shipping_request_id == sr.id,
            WmsSession.status.in_(['active', 'paused']),
        )
        .first()
    )


def status_najmniej_zaawansowany(requests):
    """Status paczki zbiorczej — najniższy sort_order ze scalanych zleceń.

    Paczka nie może być „opłacona", dopóki którykolwiek uczestnik nie zapłacił;
    WMS blokuje wysyłkę nieopłaconych, więc to samo z siebie wstrzymuje wysyłkę.
    """
    from modules.orders.models import ShippingRequestStatus
    slugi = [sr.status for sr in requests if sr.status]
    if not slugi:
        return 'czeka_na_wycene'
    kolejnosc = {
        s.slug: s.sort_order
        for s in ShippingRequestStatus.query.filter(ShippingRequestStatus.slug.in_(slugi)).all()
    }
    return min(slugi, key=lambda s: kolejnosc.get(s, 0))


def waliduj_do_konsolidacji(requests, target=None):
    """Sprawdza, czy zlecenia wolno scalić. Rzuca ConsolidationError z powodem."""
    if len(requests) < 2 and target is None:
        raise ConsolidationError('Wybierz co najmniej 2 zlecenia do konsolidacji.')

    for sr in requests:
        if sr.status in STATUSY_ZAMKNIETE:
            raise ConsolidationError(
                f'Zlecenie {sr.request_number} zostało już wysłane — nie można go konsolidować.',
                status_code=409,
            )
        if sr.is_consolidated_source:
            raise ConsolidationError(
                f'Zlecenie {sr.request_number} należy już do innej paczki zbiorczej.',
                status_code=409,
            )
        if sr.is_consolidation and sr is not target:
            raise ConsolidationError(
                f'Zlecenie {sr.request_number} jest paczką zbiorczą — '
                f'nie łączymy paczek zbiorczych ze sobą.',
                status_code=409,
            )
        sesja = _sesja_wms_blokujaca(sr)
        if sesja:
            raise ConsolidationError(
                f'Zlecenie {sr.request_number} jest w otwartej sesji WMS #{sesja.session_id} — '
                f'dokończ ją albo anuluj.',
                status_code=409,
            )


def _kopiuj_adres(zbiorcze, lead):
    """Adres, adresat i właściciel paczki idą z wiodącego. Kopia, nie referencja —
    eksport InPost i etykiety czytają pola zlecenia wprost."""
    zbiorcze.user_id = lead.user_id
    for pole in (
        'address_type', 'shipping_name', 'shipping_address', 'shipping_postal_code',
        'shipping_city', 'shipping_voivodeship', 'shipping_country',
        'pickup_courier', 'pickup_point_id', 'pickup_address',
        'pickup_postal_code', 'pickup_city',
    ):
        setattr(zbiorcze, pole, getattr(lead, pole))


def _nowy_numer():
    """Numer paczki zbiorczej. Generator czyta ostatni wiersz bez blokady, a admin
    tworzy zlecenia równolegle do klientów — przy kolizji próbujemy ponownie."""
    from modules.orders.models import ShippingRequest
    for _ in range(5):
        numer = ShippingRequest.generate_request_number()
        if not ShippingRequest.query.filter_by(request_number=numer).first():
            return numer
    raise ConsolidationError('Nie udało się nadać numeru paczki — spróbuj ponownie.', 500)


def utworz_konsolidacje(request_ids, lead_request_id, user=None):
    """Tworzy paczkę zbiorczą z podanych zleceń. Zwraca nowy ShippingRequest."""
    from modules.orders.models import ShippingRequest

    requests = ShippingRequest.query.filter(ShippingRequest.id.in_(request_ids)).all()
    if len(requests) != len(set(request_ids)):
        raise ConsolidationError('Nie znaleziono części wybranych zleceń.', status_code=404)

    waliduj_do_konsolidacji(requests)

    lead = next((sr for sr in requests if sr.id == lead_request_id), None)
    if lead is None:
        raise ConsolidationError('Zlecenie wiodące musi być jednym ze scalanych zleceń.')

    zbiorcze = ShippingRequest(
        request_number=_nowy_numer(),
        status=status_najmniej_zaawansowany(requests),
    )
    _kopiuj_adres(zbiorcze, lead)
    db.session.add(zbiorcze)
    db.session.flush()

    # Przepinamy przez relację (ro.shipping_request = zbiorcze), NIE przez surową
    # kolumnę ro.shipping_request_id ani masowy .update(). Surowa kolumna nie
    # synchronizuje kolekcji zrodlo.request_orders trzymanej w pamięci sesji — więc
    # jawne wyczyszczenie tej kolekcji (np. zrodlo.request_orders = []) albo jej
    # późniejszy odczyt/kasowanie widziałoby stare, nieodpięte obiekty i — przez
    # cascade='all, delete-orphan' — skasowałoby właśnie przeniesione wiersze jako
    # „osierocone". Przypisanie do relacji odpina wiersz od starego rodzica i dopina
    # do nowego atomowo, więc nic nigdy nie jest osierocone.
    for zrodlo in requests:
        for ro in list(zrodlo.request_orders):
            ro.source_request_id = zrodlo.id
            ro.shipping_request = zbiorcze
        zrodlo.consolidated_into_id = zbiorcze.id

    zbiorcze.lead_source_request_id = lead.id
    db.session.flush()
    return zbiorcze
