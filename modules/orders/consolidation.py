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


# Po spakowaniu skład paczki odpowiada temu, co fizycznie leży w kartonie —
# zmiana w systemie byłaby kłamstwem wobec magazynu.
STATUSY_BEZ_EDYCJI = ('spakowane', 'wyslane', 'dostarczone')


def _sprawdz_edytowalnosc(target):
    if not target.is_consolidation:
        raise ConsolidationError(
            f'Zlecenie {target.request_number} nie jest paczką zbiorczą.', status_code=404)
    if target.status in STATUSY_BEZ_EDYCJI:
        raise ConsolidationError(
            f'Paczka {target.request_number} jest już spakowana — '
            f'nie można zmieniać jej składu.', status_code=409)
    sesja = _sesja_wms_blokujaca(target)
    if sesja:
        raise ConsolidationError(
            f'Paczka {target.request_number} jest w otwartej sesji WMS #{sesja.session_id} — '
            f'dokończ ją albo anuluj.', status_code=409)


def zmien_wiodace(target, lead_request_id):
    """Przełącza zlecenie wiodące — przepisuje adres, adresata i właściciela paczki."""
    _sprawdz_edytowalnosc(target)
    lead = next((s for s in target.consolidated_sources if s.id == lead_request_id), None)
    if lead is None:
        raise ConsolidationError('Wskazane zlecenie nie należy do tej paczki.', status_code=404)
    _kopiuj_adres(target, lead)
    target.lead_source_request_id = lead.id


def dopnij_do_konsolidacji(target, request_ids):
    """Dokłada kolejne zlecenia do istniejącej paczki zbiorczej."""
    from modules.orders.models import ShippingRequest
    _sprawdz_edytowalnosc(target)

    nowe = ShippingRequest.query.filter(ShippingRequest.id.in_(request_ids)).all()
    if not nowe:
        raise ConsolidationError('Nie znaleziono zleceń do dopięcia.', status_code=404)
    waliduj_do_konsolidacji(nowe, target=target)

    for zrodlo in nowe:
        if zrodlo.id == target.id:
            raise ConsolidationError('Nie można dopiąć paczki do samej siebie.')
        for ro in list(zrodlo.request_orders):
            # Re-parenting przez relację, nie przez surową kolumnę: request_orders ma
            # cascade='all, delete-orphan', więc ustawienie samego shipping_request_id
            # zostawia wiersz osierocony w kolekcji źródła i kasuje go przy flushu.
            ro.shipping_request = target
            ro.source_request_id = zrodlo.id
        zrodlo.consolidated_into_id = target.id

    target.status = status_najmniej_zaawansowany(list(target.consolidated_sources) + nowe)
    db.session.flush()
    return target


def _oddaj_zamowienia(target, zrodlo):
    """Zwraca wiersze junction do zlecenia źródłowego, zgodnie ze śladem pochodzenia.

    Przepinamy przez relację (`ro.shipping_request = zrodlo`), nie przez surową
    kolumnę — `request_orders` ma `cascade='all, delete-orphan'`, więc wiersz
    ustawiony samą kolumną zostaje osierocony w kolekcji paczki i ginie przy flushu.
    """
    for ro in list(target.request_orders):
        if ro.source_request_id == zrodlo.id:
            ro.shipping_request = zrodlo
            ro.source_request_id = None
    zrodlo.consolidated_into_id = None


def rozwiaz_konsolidacje(target):
    """Rozmontowuje paczkę: zamówienia wracają do źródeł, zlecenie zbiorcze znika."""
    _sprawdz_edytowalnosc(target)
    zrodla = list(target.consolidated_sources)
    for zrodlo in zrodla:
        _oddaj_zamowienia(target, zrodlo)
    target.lead_source_request_id = None
    db.session.flush()
    # Kolekcja jest już pusta, więc delete-orphan nie ma czego zabrać.
    db.session.delete(target)
    return zrodla


def wypnij_zlecenie(target, source_id):
    """Wypina jedno zlecenie z paczki. Zwraca True, gdy paczka została rozwiązana,
    bo z jednym uczestnikiem przestaje mieć sens."""
    _sprawdz_edytowalnosc(target)
    zrodlo = next((s for s in target.consolidated_sources if s.id == source_id), None)
    if zrodlo is None:
        raise ConsolidationError('Wskazane zlecenie nie należy do tej paczki.', status_code=404)

    _oddaj_zamowienia(target, zrodlo)
    db.session.flush()

    pozostale = [s for s in target.consolidated_sources if s.id != source_id]
    if len(pozostale) <= 1:
        rozwiaz_konsolidacje(target)
        return True

    if target.lead_source_request_id == source_id:
        zmien_wiodace(target, pozostale[0].id)
    target.status = status_najmniej_zaawansowany(pozostale)
    return False
