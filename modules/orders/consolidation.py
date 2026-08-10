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
        brakujace = sorted(set(request_ids) - {r.id for r in requests})
        raise ConsolidationError(
            f'Nie znaleziono zleceń o id {brakujace} — sprawdź listę do konsolidacji.',
            status_code=404,
        )

    waliduj_do_konsolidacji(requests)

    lead = next((sr for sr in requests if sr.id == lead_request_id), None)
    if lead is None:
        raise ConsolidationError(
            f'Zlecenie wiodące #{lead_request_id} nie jest jednym ze scalanych zleceń.',
        )

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


def _uczestnicy_z_bazy(target):
    """Aktualni uczestnicy paczki — zapytaniem do bazy, NIE przez cache'owaną kolekcję
    `target.consolidated_sources`.

    Backref `consolidated_sources` (od `consolidated_into`), raz załadowany w danej
    sesji, nie synchronizuje się z mutacjami surowej kolumny `consolidated_into_id` —
    a dokładnie tak odpina uczestników `_oddaj_zamowienia`. Efekt: drugie wywołanie
    funkcji edycyjnej na tym samym obiekcie w tej samej transakcji (bez commit/expire
    pomiędzy) widziałoby uczestnika odpiętego przez pierwsze wywołanie jako wciąż
    należącego do paczki — stąd błędne liczenie „pozostałych" i możliwość przełączenia
    wiodącego na już niezależne zlecenie. Zapytanie po kolumnie FK nie ma tego problemu:
    autoflush przed SELECT-em widzi każdą wcześniejszą, jeszcze niescommitowaną zmianę.
    """
    from modules.orders.models import ShippingRequest
    return ShippingRequest.query.filter_by(consolidated_into_id=target.id).all()


def zmien_wiodace(target, lead_request_id):
    """Przełącza zlecenie wiodące — przepisuje adres, adresata i właściciela paczki."""
    _sprawdz_edytowalnosc(target)
    lead = next((s for s in _uczestnicy_z_bazy(target) if s.id == lead_request_id), None)
    if lead is None:
        raise ConsolidationError(
            f'Zlecenie #{lead_request_id} nie należy do paczki {target.request_number}.',
            status_code=404,
        )
    _kopiuj_adres(target, lead)
    target.lead_source_request_id = lead.id


def dopnij_do_konsolidacji(target, request_ids):
    """Dokłada kolejne zlecenia do istniejącej paczki zbiorczej."""
    from modules.orders.models import ShippingRequest
    _sprawdz_edytowalnosc(target)

    nowe = ShippingRequest.query.filter(ShippingRequest.id.in_(request_ids)).all()
    if not nowe:
        raise ConsolidationError(
            f'Nie znaleziono żadnego z podanych zleceń (id {sorted(request_ids)}) '
            f'do dopięcia do paczki {target.request_number}.',
            status_code=404,
        )
    # Walidacja PRZED jakąkolwiek mutacją. Gdy self-referencja (target we własnej liście
    # request_ids) była sprawdzana wewnątrz pętli mutującej, zlecenia stojące na liście
    # PRZED target-em zdążyły się już przepiąć (consolidated_into_id ustawione), zanim
    # pętla do niego dotarła i rzuciła wyjątek — operacja miała robić wszystko albo nic.
    if target.id in {sr.id for sr in nowe}:
        raise ConsolidationError(
            f'Paczka {target.request_number} nie może zostać dopięta do samej siebie.',
        )
    waliduj_do_konsolidacji(nowe, target=target)

    uczestnicy_przed = _uczestnicy_z_bazy(target)
    for zrodlo in nowe:
        for ro in list(zrodlo.request_orders):
            # Re-parenting przez relację, nie przez surową kolumnę: request_orders ma
            # cascade='all, delete-orphan', więc ustawienie samego shipping_request_id
            # zostawia wiersz osierocony w kolekcji źródła i kasuje go przy flushu.
            ro.shipping_request = target
            ro.source_request_id = zrodlo.id
        zrodlo.consolidated_into_id = target.id

    target.status = status_najmniej_zaawansowany(uczestnicy_przed + nowe)
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
    # Zapytanie do bazy (_uczestnicy_z_bazy), nie target.consolidated_sources — patrz
    # docstring helpera. Istotne zwłaszcza tu, bo tę funkcję woła też wypnij_zlecenie
    # w tej samej transakcji, po tym jak inni uczestnicy mogli już zostać odpięci.
    zrodla = _uczestnicy_z_bazy(target)
    for zrodlo in zrodla:
        _oddaj_zamowienia(target, zrodlo)
    target.lead_source_request_id = None
    db.session.flush()
    # Kolekcja jest już pusta, więc delete-orphan nie ma czego zabrać.
    db.session.delete(target)
    return zrodla


# Statusy opisujące jedną fizyczną paczkę — te zjeżdżają na zlecenia źródłowe.
STATUSY_LOGISTYCZNE = ('spakowane', 'wyslane', 'dostarczone')


def propaguj_na_zrodla(sr):
    """Kopiuje stan paczki zbiorczej na jej zlecenia źródłowe.

    Idą tylko statusy logistyczne plus tracking i kurier. Statusy finansowe
    zostają indywidualne — inaczej zlecenie klienta, który już zapłacił, cofnęłoby
    się na „czeka na opłacenie" razem z mailem o wpłacie.

    Cofnięcie paczki do WMS też tędy przechodzi: gdy zbiorcze wraca ze „spakowane"
    na „oplacone", źródłowe muszą zejść razem z nim.

    Uczestnicy przez _uczestnicy_z_bazy (zapytanie po consolidated_into_id), nie
    przez sr.consolidated_sources — ten sam powód co w innych funkcjach modułu:
    cache'owany backref nie widzi mutacji surowej kolumny FK w tej samej transakcji.

    Zwraca listę zleceń, którym faktycznie coś się zmieniło.
    """
    if not sr.is_consolidation:
        return []

    zmienione = []
    for zrodlo in _uczestnicy_z_bazy(sr):
        zmiana = False
        if sr.status in STATUSY_LOGISTYCZNE or zrodlo.status in STATUSY_LOGISTYCZNE:
            if zrodlo.status != sr.status:
                zrodlo.status = sr.status
                zmiana = True
        if zrodlo.tracking_number != sr.tracking_number:
            zrodlo.tracking_number = sr.tracking_number
            zmiana = True
        if zrodlo.courier != sr.courier:
            zrodlo.courier = sr.courier
            zmiana = True
        if zmiana:
            zmienione.append(zrodlo)
    return zmienione


def przelicz_status_zbiorczego(source):
    """Podnosi status paczki po zmianie statusu finansowego jednego z uczestników.

    Woła się po stronie zdarzeń płatniczych: paczka jest opłacona dopiero wtedy,
    gdy zapłacili wszyscy. Paczki po spakowaniu już nie ruszamy — logistyka raz
    nadana nie cofa się przez zdarzenie finansowe.
    """
    if not source.is_consolidated_source:
        return
    zbiorcze = source.consolidated_into
    if not zbiorcze or zbiorcze.status in STATUSY_LOGISTYCZNE:
        return
    zbiorcze.status = status_najmniej_zaawansowany(_uczestnicy_z_bazy(zbiorcze))


def odepnij_anulowane_zamowienie(order):
    """Wyjmuje anulowane zamówienie z paczki zbiorczej.

    Bramki gotowości wymagają KOMPLETU zamówień: `all(o.status == 'spakowane')`
    przy pakowaniu i zatwierdzonego E4 dla każdego przy opłaceniu. Anulowane
    zamówienie nigdy ich nie spełni, więc jedno anulowanie zablokowałoby wysyłkę
    wszystkim uczestnikom paczki.

    Funkcja NIE sprawdza sama order.status — ufa wywołującemu, że woła ją
    dokładnie wtedy, gdy status faktycznie zmienia się na 'anulowane' (patrz
    wywołania w routes.py / offer_closure.py).
    """
    from modules.orders.models import ShippingRequestOrder

    ro = ShippingRequestOrder.query.filter_by(order_id=order.id).first()
    if not ro:
        return
    zbiorcze = ro.shipping_request
    if not zbiorcze or not zbiorcze.is_consolidation:
        return
    if zbiorcze.status in STATUSY_BEZ_EDYCJI:
        # Paczka spakowana — fizycznie zawiera tę przesyłkę, więc nie kłamiemy w bazie.
        return

    source_id = ro.source_request_id
    # Usuwamy PRZEZ relację (zbiorcze.request_orders.remove(ro)), nie surowym
    # db.session.delete(ro): request_orders ma cascade='all, delete-orphan', więc
    # odpięcie od kolekcji i tak skończy się skasowaniem wiersza przy flushu — ale
    # w odróżnieniu od surowego delete() od razu aktualizuje TĘ SAMĄ listę w pamięci
    # sesji. Gdyby wywołujący (np. kod czytający wcześniej display_orders) zdążył już
    # załadować i zcache'ować `zbiorcze.request_orders`, surowy delete() zostawiłby w
    # niej widmowy wpis — a `_oddaj_zamowienia` niżej (przez rozwiaz_konsolidacje)
    # iteruje dokładnie tę kolekcję i próbowałaby skasować już nieistniejący wiersz
    # drugi raz (SAWarning: „0 matched" — nieszkodliwe tu, ale sygnał rozjazdu stanu).
    zbiorcze.request_orders.remove(ro)
    db.session.flush()

    if not source_id:
        return
    # Zapytanie do bazy, NIE zbiorcze.request_orders — ta kolekcja mogła już zostać
    # załadowana i zcache'owana wcześniej w tej samej transakcji (np. przez
    # `display_orders` wywołującego kodu, który czyta `consolidated_into.request_orders`
    # zanim w ogóle trafi tu, do funkcji). Skasowany wyżej wiersz `ro` zostałby wtedy
    # wciąż widoczny w tej cache'owanej liście — mimo że w bazie już go nie ma — i
    # funkcja błędnie uznałaby, że uczestnik ma jeszcze coś w paczce.
    zostalo = ShippingRequestOrder.query.filter_by(
        shipping_request_id=zbiorcze.id, source_request_id=source_id
    ).count()
    if zostalo:
        return

    # Uczestnik nie ma już nic w paczce — jego zlecenie wraca do samodzielnego życia.
    zrodlo = db.session.get(type(zbiorcze), source_id)
    if zrodlo:
        zrodlo.consolidated_into_id = None
    db.session.flush()
    # _uczestnicy_z_bazy (zapytanie), NIE zbiorcze.consolidated_sources — powyższy
    # `zbiorcze.is_consolidation` (parę linijek wyżej) już załadował i zcache'ował tę
    # kolekcję w pamięci sesji; surowa mutacja zrodlo.consolidated_into_id jej nie
    # odświeża, więc czytana teraz pokazywałaby wciąż-nieaktualne członkostwo i przy
    # dokładnie jednym pozostałym uczestniku NIE rozwiązałaby paczki.
    if len(_uczestnicy_z_bazy(zbiorcze)) <= 1:
        rozwiaz_konsolidacje(zbiorcze)


def wypnij_zlecenie(target, source_id):
    """Wypina jedno zlecenie z paczki. Zwraca True, gdy paczka została rozwiązana,
    bo z jednym uczestnikiem przestaje mieć sens.

    Liczbę pozostałych uczestników i samo `zrodlo` czytamy przez _uczestnicy_z_bazy
    (zapytanie), nie przez target.consolidated_sources (cache'owana kolekcja) — inaczej
    dwa wywołania tej funkcji na tym samym obiekcie w jednej transakcji, bez commit/expire
    pomiędzy, drugim razem liczyłyby uczestnika odpiętego w pierwszym wywołaniu jako
    wciąż należącego do paczki. Skutek byłby podwójny: paczka NIE rozwiązywałaby się mimo
    jednego realnego uczestnika, a przy wypinaniu wiodącego zmien_wiodace dostawałoby jako
    kandydata już niezależne, odpięte zlecenie — i to trafiałoby do bazy po commicie.
    """
    _sprawdz_edytowalnosc(target)
    zrodlo = next((s for s in _uczestnicy_z_bazy(target) if s.id == source_id), None)
    if zrodlo is None:
        raise ConsolidationError(
            f'Zlecenie #{source_id} nie należy do paczki {target.request_number}.',
            status_code=404,
        )

    _oddaj_zamowienia(target, zrodlo)
    db.session.flush()

    pozostale = _uczestnicy_z_bazy(target)
    if len(pozostale) <= 1:
        rozwiaz_konsolidacje(target)
        return True

    if target.lead_source_request_id == source_id:
        zmien_wiodace(target, pozostale[0].id)
    target.status = status_najmniej_zaawansowany(pozostale)
    return False
