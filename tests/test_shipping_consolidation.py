"""Konsolidacja zleceń wysyłki wielu klientów: model, serwis i propagacja statusów."""
import pytest


def _seed_sr_statuses(db):
    """Statusy zleceń wysyłki w kolejności łańcucha — sort_order decyduje o „najmniej zaawansowanym"."""
    from modules.orders.models import ShippingRequestStatus
    for i, (slug, name) in enumerate([
        ('czeka_na_wycene', 'Czeka na wycenę'),
        ('czeka_na_oplacenie', 'Czeka na opłacenie'),
        ('oplacone', 'Opłacone'),
        ('spakowane', 'Spakowane'),
        ('wyslane', 'Wysłane'),
        ('dostarczone', 'Dostarczone'),
    ]):
        db.session.add(ShippingRequestStatus(
            slug=slug, name=name, sort_order=i,
            is_active=True, is_initial=(slug == 'czeka_na_wycene'),
        ))
    db.session.commit()


def _sr(db, user, make_order, status='oplacone', orders_count=1):
    """Zlecenie wysyłki z zamówieniami danego klienta."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status=status, address_type='home',
        shipping_name=f'{user.first_name} {user.last_name}',
        shipping_address='ul. Kwiatowa 12', shipping_postal_code='30-001',
        shipping_city='Kraków',
    )
    db.session.add(sr)
    db.session.flush()
    orders = []
    for _ in range(orders_count):
        o = make_order(user)
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
        orders.append(o)
    db.session.commit()
    return sr, orders


def test_konsolidacja_ma_relacje_do_zrodel(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)

    from modules.orders.models import ShippingRequest
    zbiorcze = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=a.id, status='oplacone', address_type='home',
    )
    db.session.add(zbiorcze)
    db.session.flush()
    sr_a.consolidated_into_id = zbiorcze.id
    sr_b.consolidated_into_id = zbiorcze.id
    zbiorcze.lead_source_request_id = sr_a.id
    db.session.commit()

    assert {s.id for s in zbiorcze.consolidated_sources} == {sr_a.id, sr_b.id}
    assert zbiorcze.lead_source.id == sr_a.id
    assert sr_b.consolidated_into.id == zbiorcze.id


def _skonsoliduj(db, zbiorcze, zrodla, lead):
    """Ręczne złożenie konsolidacji — serwis powstaje dopiero w Task 3."""
    from modules.orders.models import ShippingRequestOrder
    for zr in zrodla:
        for ro in list(zr.request_orders):
            ro.shipping_request_id = zbiorcze.id
            ro.source_request_id = zr.id
        zr.consolidated_into_id = zbiorcze.id
    zbiorcze.lead_source_request_id = lead.id
    db.session.commit()
    db.session.expire_all()


def test_display_orders_zwraca_tylko_wlasne_zamowienia(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, orders_a = _sr(db, a, make_order, orders_count=2)
    sr_b, orders_b = _sr(db, b, make_order, orders_count=1)

    from modules.orders.models import ShippingRequest
    zbiorcze = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=a.id, status='oplacone', address_type='home')
    db.session.add(zbiorcze)
    db.session.flush()
    _skonsoliduj(db, zbiorcze, [sr_a, sr_b], sr_a)

    assert zbiorcze.is_consolidation is True
    assert sr_b.is_consolidated_source is True
    assert {o.id for o in sr_b.display_orders} == {orders_b[0].id}
    assert {o.id for o in sr_a.display_orders} == {o.id for o in orders_a}
    assert len(zbiorcze.display_orders) == 3


def test_uczestnicy_pogrupowani_po_wlascicielu(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order, orders_count=2)
    sr_b, _ = _sr(db, b, make_order, orders_count=1)

    from modules.orders.models import ShippingRequest
    zbiorcze = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=a.id, status='oplacone', address_type='home')
    db.session.add(zbiorcze)
    db.session.flush()
    _skonsoliduj(db, zbiorcze, [sr_a, sr_b], sr_a)

    uczestnicy = zbiorcze.consolidation_participants
    assert len(uczestnicy) == 2
    assert [len(u['orders']) for u in uczestnicy] == [2, 1]
    assert uczestnicy[0]['source_request'].id == sr_a.id


def test_zamowienie_pokazuje_klientowi_jego_zlecenie(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, orders_b = _sr(db, b, make_order)

    from modules.orders.models import ShippingRequest
    zbiorcze = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=a.id, status='oplacone', address_type='home')
    db.session.add(zbiorcze)
    db.session.flush()
    _skonsoliduj(db, zbiorcze, [sr_a, sr_b], sr_a)

    zamowienie_b = orders_b[0]
    # WMS musi widzieć paczkę zbiorczą…
    assert zamowienie_b.shipping_request.id == zbiorcze.id
    # …ale klient B swoje własne zlecenie, nie cudzy adres.
    assert zamowienie_b.client_shipping_request.id == sr_b.id


def test_skonsolidowanego_zlecenia_klient_nie_anuluje(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order, status='czeka_na_wycene')
    sr_b, _ = _sr(db, b, make_order, status='czeka_na_wycene')

    from modules.orders.models import ShippingRequest
    assert sr_a.can_cancel is True  # przed konsolidacją wolno

    zbiorcze = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=a.id, status='czeka_na_wycene', address_type='home')
    db.session.add(zbiorcze)
    db.session.flush()
    _skonsoliduj(db, zbiorcze, [sr_a, sr_b], sr_a)

    # Status początkowy, brak kosztu i trackingu — a mimo to nie wolno.
    assert sr_a.can_cancel is False
    assert sr_b.can_cancel is False
    assert zbiorcze.can_cancel is False


def test_koszt_zrodlowego_liczony_z_jego_zamowien(db, make_user, make_order):
    from decimal import Decimal
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, orders_a = _sr(db, a, make_order)
    sr_b, orders_b = _sr(db, b, make_order)
    orders_a[0].shipping_cost = Decimal('12.00')
    orders_b[0].shipping_cost = Decimal('8.00')
    db.session.commit()

    from modules.orders.models import ShippingRequest
    zbiorcze = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=a.id, status='oplacone', address_type='home')
    db.session.add(zbiorcze)
    db.session.flush()
    _skonsoliduj(db, zbiorcze, [sr_a, sr_b], sr_a)

    assert sr_b.calculated_shipping_cost == Decimal('8.00')
    assert zbiorcze.calculated_shipping_cost == Decimal('20.00')
    assert sr_b.orders_count == 1


def test_konsolidacja_tworzy_nowy_numer_i_przenosi_zamowienia(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, orders_a = _sr(db, a, make_order, orders_count=2)
    sr_b, orders_b = _sr(db, b, make_order, orders_count=1)

    from modules.orders.consolidation import utworz_konsolidacje
    zbiorcze = utworz_konsolidacje([sr_a.id, sr_b.id], lead_request_id=sr_a.id)
    db.session.commit()

    assert zbiorcze.request_number not in (sr_a.request_number, sr_b.request_number)
    assert len(zbiorcze.request_orders) == 3
    assert zbiorcze.user_id == a.id
    assert zbiorcze.shipping_city == sr_a.shipping_city
    assert sr_a.consolidated_into_id == zbiorcze.id
    assert sr_b.consolidated_into_id == zbiorcze.id
    # Ślad pochodzenia — bez niego wypięcie nie wie, dokąd wrócić.
    zrodla = {ro.order_id: ro.source_request_id for ro in zbiorcze.request_orders}
    assert zrodla[orders_b[0].id] == sr_b.id
    assert zrodla[orders_a[0].id] == sr_a.id


def test_status_zbiorczego_to_najmniej_zaawansowany(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order, status='oplacone')
    sr_b, _ = _sr(db, b, make_order, status='czeka_na_oplacenie')

    from modules.orders.consolidation import utworz_konsolidacje
    zbiorcze = utworz_konsolidacje([sr_a.id, sr_b.id], lead_request_id=sr_a.id)
    db.session.commit()

    assert zbiorcze.status == 'czeka_na_oplacenie'
    # Opłacone zlecenie NIE cofa się — finanse są indywidualne.
    assert sr_a.status == 'oplacone'


def test_odmowa_dla_jednego_zlecenia_i_wyslanych(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order, status='wyslane')

    from modules.orders.consolidation import utworz_konsolidacje, ConsolidationError
    with pytest.raises(ConsolidationError):
        utworz_konsolidacje([sr_a.id], lead_request_id=sr_a.id)
    with pytest.raises(ConsolidationError):
        utworz_konsolidacje([sr_a.id, sr_b.id], lead_request_id=sr_a.id)


def test_odmowa_konsolidacji_zagniezdzonej(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b, c = make_user(), make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)
    sr_c, _ = _sr(db, c, make_order)

    from modules.orders.consolidation import utworz_konsolidacje, ConsolidationError
    utworz_konsolidacje([sr_a.id, sr_b.id], lead_request_id=sr_a.id)
    db.session.commit()

    with pytest.raises(ConsolidationError):
        utworz_konsolidacje([sr_a.id, sr_c.id], lead_request_id=sr_c.id)


def test_przepiecie_nie_kasuje_wierszy_przez_kaskade(db, make_user, make_order):
    """Regres: request_orders ma cascade='all, delete-orphan'. Odczytanie kolekcji
    przed przepięciem i późniejszy delete kasował właśnie przeniesione wiersze."""
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order, orders_count=2)
    sr_b, _ = _sr(db, b, make_order, orders_count=2)

    from modules.orders.consolidation import utworz_konsolidacje
    from modules.orders.models import ShippingRequestOrder
    zbiorcze = utworz_konsolidacje([sr_a.id, sr_b.id], lead_request_id=sr_a.id)
    db.session.commit()
    db.session.expire_all()

    assert ShippingRequestOrder.query.filter_by(shipping_request_id=zbiorcze.id).count() == 4


def _konsolidacja(db, make_user, make_order, ile=2, orders_count=1):
    from modules.orders.consolidation import utworz_konsolidacje
    zrodla = []
    for _ in range(ile):
        sr, _o = _sr(db, make_user(), make_order, orders_count=orders_count)
        zrodla.append(sr)
    zbiorcze = utworz_konsolidacje([s.id for s in zrodla], lead_request_id=zrodla[0].id)
    db.session.commit()
    return zbiorcze, zrodla


def test_zmiana_wiodacego_przepisuje_adres_i_wlasciciela(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_b.shipping_city = 'Gdańsk'
    db.session.commit()

    from modules.orders.consolidation import zmien_wiodace
    zmien_wiodace(zbiorcze, sr_b.id)
    db.session.commit()

    assert zbiorcze.lead_source_request_id == sr_b.id
    assert zbiorcze.user_id == sr_b.user_id
    assert zbiorcze.shipping_city == 'Gdańsk'


def test_wypiecie_zwraca_zamowienia_do_zrodla(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order, ile=3)
    sr_c = zrodla[2]

    from modules.orders.consolidation import wypnij_zlecenie
    rozwiazana = wypnij_zlecenie(zbiorcze, sr_c.id)
    db.session.commit()
    db.session.expire_all()

    assert rozwiazana is False
    assert sr_c.consolidated_into_id is None
    assert len(sr_c.request_orders) == 1
    assert len(zbiorcze.request_orders) == 2


def test_wypiecie_przedostatniego_rozwiazuje_konsolidacje(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze_id = zbiorcze.id

    from modules.orders.consolidation import wypnij_zlecenie
    from modules.orders.models import ShippingRequest
    rozwiazana = wypnij_zlecenie(zbiorcze, sr_b.id)
    db.session.commit()

    assert rozwiazana is True
    assert db.session.get(ShippingRequest, zbiorcze_id) is None
    assert sr_a.consolidated_into_id is None
    assert len(sr_a.request_orders) == 1


def test_rozwiazanie_zwraca_wszystko_i_kasuje_zbiorcze(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order, ile=3, orders_count=2)
    zbiorcze_id = zbiorcze.id

    from modules.orders.consolidation import rozwiaz_konsolidacje
    from modules.orders.models import ShippingRequest
    zwrocone = rozwiaz_konsolidacje(zbiorcze)
    db.session.commit()
    db.session.expire_all()

    assert len(zwrocone) == 3
    assert db.session.get(ShippingRequest, zbiorcze_id) is None
    for sr in zrodla:
        assert sr.consolidated_into_id is None
        assert len(sr.request_orders) == 2


def test_edycja_zablokowana_po_spakowaniu(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'spakowane'
    db.session.commit()

    from modules.orders.consolidation import wypnij_zlecenie, rozwiaz_konsolidacje, ConsolidationError
    with pytest.raises(ConsolidationError):
        wypnij_zlecenie(zbiorcze, sr_b.id)
    with pytest.raises(ConsolidationError):
        rozwiaz_konsolidacje(zbiorcze)


def test_dwa_wypiecia_pod_rzad_bez_commitu_nie_korumpuja_stanu(db, make_user, make_order):
    """Regres z code review: wypnij_zlecenie liczyło pozostałych uczestników przez
    cache'owaną kolekcję target.consolidated_sources. Drugie wywołanie w tej samej
    transakcji (bez commit/expire pomiędzy) widziało uczestnika odpiętego przez
    pierwsze wywołanie jako wciąż należącego do paczki — paczka NIE rozwiązywała się
    mimo jednego realnego uczestnika, a przy wypinaniu wiodącego zmien_wiodace
    dostawało jako kandydata na wiodące już niezależne, odpięte zlecenie (sr_b poniżej),
    co trafiało do bazy po commicie.

    Kolejność wypięć jest tu istotna: najpierw NIE-wiodące (sr_b), potem WIODĄCE
    (sr_a) — to dokładnie odtwarza scenariusz ze zgłoszenia."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b, sr_c) = _konsolidacja(db, make_user, make_order, ile=3)
    assert zbiorcze.lead_source_request_id == sr_a.id
    zbiorcze_id = zbiorcze.id

    from modules.orders.consolidation import wypnij_zlecenie
    from modules.orders.models import ShippingRequest

    r1 = wypnij_zlecenie(zbiorcze, sr_b.id)  # odpina zlecenie NIE-wiodące
    r2 = wypnij_zlecenie(zbiorcze, sr_a.id)  # odpina WIODĄCE — zostaje tylko sr_c
    db.session.commit()
    db.session.expire_all()

    assert r1 is False
    assert r2 is True  # pod starym kodem: False — paczka „nie widziała", że zostań 1 uczestnik
    assert db.session.get(ShippingRequest, zbiorcze_id) is None
    for sr in (sr_a, sr_b, sr_c):
        assert sr.consolidated_into_id is None
        assert len(sr.request_orders) == 1


def test_dopiecie_dokleja_zlecenie_ze_sladem_pochodzenia(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_c, orders_c = _sr(db, make_user(), make_order, status='czeka_na_oplacenie')

    from modules.orders.consolidation import dopnij_do_konsolidacji
    wynik = dopnij_do_konsolidacji(zbiorcze, [sr_c.id])
    db.session.commit()
    db.session.expire_all()

    assert wynik.id == zbiorcze.id
    assert sr_c.consolidated_into_id == zbiorcze.id
    zrodla = {ro.order_id: ro.source_request_id for ro in zbiorcze.request_orders}
    assert zrodla[orders_c[0].id] == sr_c.id
    assert len(sr_c.request_orders) == 0
    # sr_a, sr_b były 'oplacone' (sort_order wyżej); sr_c 'czeka_na_oplacenie' — to ona
    # teraz jest najmniej zaawansowanym uczestnikiem paczki.
    assert zbiorcze.status == 'czeka_na_oplacenie'


def test_dopiecie_do_samej_siebie_nie_mutuje_niczego(db, make_user, make_order):
    """Regres z code review: self-referencja (target we własnej liście request_ids)
    sprawdzana wewnątrz pętli mutującej zostawiała już przepięte zlecenia stojące na
    liście PRZED target-em. Walidacja musi być przed jakąkolwiek mutacją — operacja
    ma zrobić wszystko albo nic.

    sr_c jest tworzone PRZED zbiorcze (niższe id) — zapytanie ShippingRequest.query
    .filter(id.in_(...)) w SQLite bez ORDER BY zwraca wiersze w kolejności rowid, więc
    sr_c trafia w pętli PRZED target-em. Pod starym kodem (self-check wewnątrz pętli)
    to właśnie ta kolejność ujawniała częściową mutację."""
    _seed_sr_statuses(db)
    sr_c, orders_c = _sr(db, make_user(), make_order, status='czeka_na_oplacenie')
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    assert sr_c.id < zbiorcze.id

    from modules.orders.consolidation import dopnij_do_konsolidacji, ConsolidationError
    # sr_c.id PRZED zbiorcze.id na liście — pod starym kodem sr_c zdążyłby się przepiąć,
    # zanim pętla dotarłaby do zbiorcze i rzuciła wyjątek.
    with pytest.raises(ConsolidationError):
        dopnij_do_konsolidacji(zbiorcze, [sr_c.id, zbiorcze.id])

    # Bez commitu/rollbacku — sprawdzamy stan obiektów w pamięci sesji tuż po wyjątku:
    # gdyby funkcja zmutowała sr_c przed rzuceniem błędu, zobaczylibyśmy to tutaj.
    assert sr_c.consolidated_into_id is None
    assert len(sr_c.request_orders) == 1
    assert len(zbiorcze.request_orders) == 2


def test_wyslanie_paczki_propaguje_status_i_tracking(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'wyslane'
    zbiorcze.tracking_number = '622334455'
    zbiorcze.courier = 'inpost'

    from modules.orders.consolidation import propaguj_na_zrodla
    zmienione = propaguj_na_zrodla(zbiorcze)
    db.session.commit()

    assert len(zmienione) == 2
    for sr in (sr_a, sr_b):
        assert sr.status == 'wyslane'
        assert sr.tracking_number == '622334455'
        assert sr.courier == 'inpost'


def test_propagacja_nie_cofa_statusu_finansowego(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_a.status = 'oplacone'
    sr_b.status = 'czeka_na_oplacenie'
    zbiorcze.status = 'czeka_na_oplacenie'
    db.session.commit()

    from modules.orders.consolidation import propaguj_na_zrodla
    propaguj_na_zrodla(zbiorcze)
    db.session.commit()

    assert sr_a.status == 'oplacone'
    assert sr_b.status == 'czeka_na_oplacenie'


def test_oplacenie_zrodla_podnosi_status_zbiorczego(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_a.status = 'czeka_na_oplacenie'
    sr_b.status = 'czeka_na_oplacenie'
    zbiorcze.status = 'czeka_na_oplacenie'
    db.session.commit()

    from modules.orders.consolidation import przelicz_status_zbiorczego
    sr_a.status = 'oplacone'
    przelicz_status_zbiorczego(sr_a)
    db.session.commit()
    assert zbiorcze.status == 'czeka_na_oplacenie'  # B jeszcze nie zapłacił

    sr_b.status = 'oplacone'
    przelicz_status_zbiorczego(sr_b)
    db.session.commit()
    assert zbiorcze.status == 'oplacone'


def test_cofniecie_do_wms_propaguje_w_dol(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'spakowane'
    from modules.orders.consolidation import propaguj_na_zrodla
    propaguj_na_zrodla(zbiorcze)
    db.session.commit()
    assert sr_a.status == 'spakowane'

    zbiorcze.status = 'oplacone'
    propaguj_na_zrodla(zbiorcze)
    db.session.commit()
    assert sr_a.status == 'oplacone'
    assert sr_b.status == 'oplacone'


def test_wyslanie_przez_wms_propaguje_na_zrodla(db, make_user, make_order):
    from tests.test_wms_ship_and_reopen import _seed_statuses
    _seed_sr_statuses(db)
    _seed_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'spakowane'
    db.session.commit()

    from modules.orders.wms_utils import ship_shipping_request
    ship_shipping_request(zbiorcze, courier='inpost', tracking_number='622999888')
    db.session.expire_all()

    assert sr_a.status == 'wyslane'
    assert sr_b.tracking_number == '622999888'


def test_oplacenie_przez_jednego_uczestnika_podnosi_tylko_jego_zlecenie(db, make_user, make_order):
    """Klient płaci za swoje zamówienia niezależnie — nie ma czekać, aż zapłacą inni,
    żeby zobaczyć u siebie 'opłacone'. Paczka czeka na komplet."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    for sr in (sr_a, sr_b, zbiorcze):
        sr.status = 'czeka_na_oplacenie'
    db.session.commit()

    from decimal import Decimal
    from modules.orders.models import PaymentConfirmation
    zamowienie_a = sr_a.display_orders[0]
    # amount jest NOT NULL w modelu — brief pominął je, dopisane żeby insert przeszedł.
    db.session.add(PaymentConfirmation(
        order_id=zamowienie_a.id, payment_stage='domestic_shipping', status='approved',
        amount=Decimal('10.00')))
    db.session.commit()

    from modules.admin.payment_confirmations import _check_sr_auto_oplacone
    _check_sr_auto_oplacone(zamowienie_a)
    db.session.expire_all()

    assert sr_a.status == 'oplacone'
    assert sr_b.status == 'czeka_na_oplacenie'
    assert zbiorcze.status == 'czeka_na_oplacenie'


def test_short_addressee_name_przypadki_brzegowe(db, make_user, make_order):
    """`short_addressee_name` skraca adresata do 'Imię P.' — uczestnicy paczki zbiorczej
    niebędący adresatem mają tego użyć zamiast pełnego shipping_name (spec: panel klienta).
    Sprawdza też przypadki brzegowe: brak nazwiska, brak imienia i nazwiska, pusty ciąg."""
    _seed_sr_statuses(db)
    sr, _o = _sr(db, make_user(), make_order)

    sr.shipping_name = 'Karolina Burza'
    assert sr.short_addressee_name == 'Karolina B.'

    sr.shipping_name = 'karolina burza'
    assert sr.short_addressee_name == 'karolina B.'

    sr.shipping_name = 'Karolina Maria Burza'
    assert sr.short_addressee_name == 'Karolina B.'

    # Brak nazwiska — samo imię, bez sklejania kropki znikąd.
    sr.shipping_name = 'Karolina'
    assert sr.short_addressee_name == 'Karolina'

    # Brak adresata w ogóle (np. zlecenie typu paczkomat bez wypełnionego shipping_name).
    sr.shipping_name = None
    assert sr.short_addressee_name is None

    sr.shipping_name = '   '
    assert sr.short_addressee_name is None


def test_anulowane_zamowienie_wypina_sie_z_paczki(db, make_user, make_order):
    """Anulowanie jednego z kilku zamówień uczestnika wypina tylko ten wiersz
    junction — reszta zamówień tego uczestnika (i inni uczestnicy) zostają."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order, orders_count=2)
    zamowienie = sr_b.display_orders[0]

    from modules.orders.consolidation import odepnij_anulowane_zamowienie
    odepnij_anulowane_zamowienie(zamowienie)
    db.session.commit()
    db.session.expire_all()

    assert len(zbiorcze.request_orders) == 3
    assert zamowienie.id not in {o.id for o in zbiorcze.display_orders}
    assert sr_b.consolidated_into_id == zbiorcze.id  # drugie zamówienie B zostaje


def test_anulowanie_ostatniego_zamowienia_wypina_zlecenie(db, make_user, make_order):
    """Gdy anulowane zamówienie było ostatnim zamówieniem uczestnika w paczce,
    jego zlecenie źródłowe wraca do samodzielnego bytu — ale paczka (z dwoma
    pozostałymi uczestnikami) nadal istnieje."""
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order, ile=3, orders_count=1)
    sr_c = zrodla[2]
    zamowienie = sr_c.display_orders[0]

    from modules.orders.consolidation import odepnij_anulowane_zamowienie
    odepnij_anulowane_zamowienie(zamowienie)
    db.session.commit()
    db.session.expire_all()

    assert sr_c.consolidated_into_id is None
    assert len(zbiorcze.consolidated_sources) == 2


def test_anulowanie_jedynego_zamowienia_ostatniego_uczestnika_rozwiazuje_zbiorcze(db, make_user, make_order):
    """Regres na pułapkę z cache'owanym backrefem: `odepnij_anulowane_zamowienie`
    wywołuje `zbiorcze.is_consolidation` (czyli `bool(self.consolidated_sources)`)
    ZANIM odepnie źródło — to ładuje i cache'uje kolekcję `consolidated_sources`
    w pamięci sesji. Gdyby finalne liczenie „ilu uczestników zostało" czytało tę
    samą cache'owaną kolekcję zamiast pytać bazę na nowo (_uczestnicy_z_bazy),
    zobaczyłoby nieaktualny stan sprzed odpięcia i NIE rozwiązałoby paczki mimo
    jednego realnego uczestnika (dokładnie tak jak w regresie z `wypnij_zlecenie`,
    patrz `test_dwa_wypiecia_pod_rzad_bez_commitu_nie_korumpuja_stanu`)."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)  # ile=2, orders_count=1
    zbiorcze_id = zbiorcze.id
    zamowienie = sr_b.display_orders[0]

    from modules.orders.consolidation import odepnij_anulowane_zamowienie
    from modules.orders.models import ShippingRequest
    odepnij_anulowane_zamowienie(zamowienie)
    db.session.commit()
    db.session.expire_all()

    assert db.session.get(ShippingRequest, zbiorcze_id) is None
    assert sr_a.consolidated_into_id is None
    assert sr_b.consolidated_into_id is None


def test_anulowanie_nie_rusza_spakowanej_paczki(db, make_user, make_order):
    """Paczka spakowana odpowiada temu, co fizycznie leży w kartonie — anulowanie
    zamówienia jednego z uczestników PO spakowaniu nie może go z niej wyjąć."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order, orders_count=2)
    zbiorcze.status = 'spakowane'
    db.session.commit()
    zamowienie = sr_b.display_orders[0]

    from modules.orders.consolidation import odepnij_anulowane_zamowienie
    odepnij_anulowane_zamowienie(zamowienie)
    db.session.commit()
    db.session.expire_all()

    assert len(zbiorcze.request_orders) == 4
    assert zamowienie.id in {o.id for o in zbiorcze.display_orders}
    assert sr_b.consolidated_into_id == zbiorcze.id


def test_anulowanie_przelicza_koszt_zbiorczego(db, make_user, make_order):
    """calculated_shipping_cost jest własnością liczoną na bieżąco z display_orders —
    po wypięciu anulowanego zamówienia przestaje wliczać jego koszt, bez potrzeby
    ręcznego przeliczania. total_shipping_cost (zapisany snapshot z ostatniej wyceny
    admina) świadomie zostaje nietknięty — tak samo jak w wypnij_zlecenie/
    rozwiaz_konsolidacje, które też go nie aktualizują; odświeży go dopiero kolejna
    wycena."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order, orders_count=2)
    for o in sr_a.display_orders:
        o.shipping_cost = 10
    for o in sr_b.display_orders:
        o.shipping_cost = 20
    db.session.commit()
    from decimal import Decimal
    assert zbiorcze.calculated_shipping_cost == Decimal('60.00')

    zamowienie = sr_b.display_orders[0]
    from modules.orders.consolidation import odepnij_anulowane_zamowienie
    odepnij_anulowane_zamowienie(zamowienie)
    db.session.commit()
    db.session.expire_all()

    assert zbiorcze.calculated_shipping_cost == Decimal('40.00')


def test_anulowanie_przelicza_status_zbiorczego_gdy_zostaja_uczestnicy(db, make_user, make_order):
    """Regres z code review: odepnij_anulowane_zamowienie przeliczała status paczki
    tylko przy pełnym rozwiązaniu (rozwiaz_konsolidacje). Gdy po ewikcji zostają
    >=2 uczestnicy, zbiorcze.status zostawał nietknięty — mimo że ewikowany
    uczestnik mógł trzymać go na mniej zaawansowanym etapie (np. nieopłacony),
    podczas gdy reszta już zapłaciła. sr.status == 'oplacone' to bramka „do
    spakowania" w WMS, więc bez przeliczenia paczka niesłusznie znika z listy do
    pakowania mimo kompletu opłaconych realnych uczestników."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b, sr_c) = _konsolidacja(db, make_user, make_order, ile=3, orders_count=1)
    sr_a.status = 'oplacone'
    sr_b.status = 'oplacone'
    sr_c.status = 'czeka_na_oplacenie'
    zbiorcze.status = 'czeka_na_oplacenie'
    db.session.commit()
    zamowienie = sr_c.display_orders[0]

    from modules.orders.consolidation import odepnij_anulowane_zamowienie
    odepnij_anulowane_zamowienie(zamowienie)
    db.session.commit()
    db.session.expire_all()

    assert sr_c.consolidated_into_id is None
    assert zbiorcze.status == 'oplacone'


def test_anulowanie_nie_jest_blokowana_przez_sesje_wms(db, make_user, make_order):
    """Regres z code review (runda 2 → runda 3): gdy paczka schodzi do jednego
    realnego uczestnika, funkcja wołała publiczne rozwiaz_konsolidacje — a to
    sprawdza _sprawdz_edytowalnosc, w tym otwartą sesję WMS na paczce.
    Anulowanie zamówienia NIGDY nie powinno zostać zablokowane WYJĄTKIEM —
    ale (regres wykryty w drugiej rundzie recenzji) samo wymuszone
    `db.session.delete(target)` na paczce, którą wciąż trzyma aktywna sesja
    WMS (`WmsSessionShippingRequest`, FK bez ondelete=CASCADE), jest RÓWNIE
    złym pomysłem: na SQLite w testach przechodzi cicho, ale na MariaDB
    skończyłoby się IntegrityError przy commicie — gorszym, mniej czytelnym
    błędem niż poprzedni ConsolidationError, a przy okazji wyrywa zlecenie
    spod pracy magazyniera w trakcie skanowania. Poprawne zachowanie: tak jak
    `admin_delete_shipping_request`/`admin_bulk_cancel_shipping_requests` przy
    identycznym konflikcie — NIE kasować paczki, dopóki sesja jest aktywna/
    wstrzymana; ewikcja samego zamówienia i źródła i tak się udaje (bramki
    gotowości i tak przestają liczyć anulowane zamówienie), a pełne
    rozwiązanie paczki poczeka do zamknięcia sesji."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze_id = zbiorcze.id

    admin = make_user(role='admin')
    from modules.orders.wms_models import WmsSession, WmsSessionShippingRequest
    sesja = WmsSession(session_token='tok-anulowanie', user_id=admin.id, status='active')
    db.session.add(sesja)
    db.session.flush()
    db.session.add(WmsSessionShippingRequest(session_id=sesja.id, shipping_request_id=zbiorcze.id))
    db.session.commit()

    zamowienie = sr_b.display_orders[0]
    from modules.orders.consolidation import odepnij_anulowane_zamowienie
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    odepnij_anulowane_zamowienie(zamowienie)  # NIE powinno rzucić ConsolidationError
    db.session.commit()
    db.session.expire_all()

    # Zamówienie faktycznie wypięte — to jest właściwy cel Task 13, niezależnie
    # od tego, czy cała paczka się rozwiązuje.
    assert zamowienie.id not in {o.id for o in zbiorcze.display_orders}
    assert sr_b.consolidated_into_id is None

    # Ale paczka NIE jest kasowana, dopóki trzyma ją aktywna sesja WMS — inaczej
    # delete(target) uderzyłby w FK z wms_session_shipping_requests.
    zbiorcze_po = db.session.get(ShippingRequest, zbiorcze_id)
    assert zbiorcze_po is not None
    assert sr_a.consolidated_into_id == zbiorcze_id
    # Junction sesji WMS zostaje nietknięty — nic go nie osierociło.
    assert WmsSessionShippingRequest.query.filter_by(
        session_id=sesja.id, shipping_request_id=zbiorcze_id
    ).count() == 1


def test_anulowanie_po_zamknieciu_sesji_wms_pozwala_dokonczyc_rozwiazanie(db, make_user, make_order):
    """Dopełnienie poprzedniego testu: gdy sesja WMS, która wcześniej blokowała
    pełne rozwiązanie paczki, jest już zamknięta (nieaktywna), zwykła, jawna
    ścieżka administracyjna (wypnij_zlecenie) w końcu dokańcza to, czego
    odepnij_anulowane_zamowienie musiała odłożyć.

    Regres z rundy 4 code review: `_sesja_wms_blokujaca` filtruje po statusie
    active/paused, więc sesja 'completed'/'cancelled' NIE blokuje już
    `_sprawdz_edytowalnosc` — ale wiersz `WmsSessionShippingRequest` z tej sesji
    nigdy nie ginie (`wms_complete_session`/`wms_cancel_session` zmieniają tylko
    `session.status`, nie kasują junction). FK `shipping_request_id →
    shipping_requests.id` nie ma `ondelete` (domyślne RESTRICT), więc
    `db.session.delete(target)` bez uprzedniego sprzątania tego wiersza
    uderzyłby w FK na MariaDB. SQLite w testach FK nie egzekwuje — więc samo
    `assert rozwiazana is True` / brak wyjątku (jak w poprzedniej wersji tego
    testu) przechodziłoby również dla zepsutego kodu. Test musi więc sprawdzać
    STAN, nie brak wyjątku: że po skasowaniu paczki nie zostaje ani jeden
    wiersz `WmsSessionShippingRequest` wskazujący na jej (już nieistniejące) id."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze_id = zbiorcze.id

    admin = make_user(role='admin')
    from modules.orders.wms_models import WmsSession, WmsSessionShippingRequest
    sesja = WmsSession(session_token='tok-zamknieta', user_id=admin.id, status='active')
    db.session.add(sesja)
    db.session.flush()
    db.session.add(WmsSessionShippingRequest(session_id=sesja.id, shipping_request_id=zbiorcze.id))
    db.session.commit()

    zamowienie = sr_b.display_orders[0]
    from modules.orders.consolidation import odepnij_anulowane_zamowienie, wypnij_zlecenie
    from modules.orders.models import ShippingRequest
    odepnij_anulowane_zamowienie(zamowienie)
    db.session.commit()

    # Sesja się kończy — magazynier dokańcza pracę. Wiersz WmsSessionShippingRequest
    # NIE znika przy zamknięciu sesji (wms_complete_session tego nie robi) — zostaje
    # jako „stary" junction, dokładnie jak w realnym scenariuszu z rundy 4.
    sesja.status = 'completed'
    db.session.commit()

    # sr_a jest jedynym uczestnikiem — zwykłe wypnij_zlecenie(zbiorcze, sr_a.id)
    # teraz przechodzi bez błędu i sprząta resztę.
    rozwiazana = wypnij_zlecenie(zbiorcze, sr_a.id)
    db.session.commit()
    db.session.expire_all()

    assert rozwiazana is True
    assert db.session.get(ShippingRequest, zbiorcze_id) is None
    assert sr_a.consolidated_into_id is None
    # Kluczowa asercja rundy 4: żaden wiersz WmsSessionShippingRequest nie
    # wskazuje już na skasowaną paczkę — inaczej na MariaDB delete(target) by
    # się nie udał (FK RESTRICT), a tu byśmy tego nie zobaczyli.
    assert WmsSessionShippingRequest.query.filter_by(
        shipping_request_id=zbiorcze_id
    ).count() == 0


def test_rozwiazanie_jawne_sprzata_zakonczona_sesje_wms(db, make_user, make_order):
    """Ta sama pułapka co wyżej, ale na WPROST jawnej ścieżce administracyjnej
    (rozwiaz_konsolidacje — wołane też przez endpoint „Rozwiąż paczkę" z Task 7),
    nie przez ewikcję z anulowania. `rozwiaz_konsolidacje` i
    `odepnij_anulowane_zamowienie` współdzielą dokładnie tę samą linię
    `db.session.delete(target)` (przez `_rozwiaz_konsolidacje_bez_walidacji`),
    więc ten sam fix musi obsłużyć obie ścieżki jedną poprawką."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze_id = zbiorcze.id

    admin = make_user(role='admin')
    from modules.orders.wms_models import WmsSession, WmsSessionShippingRequest
    sesja = WmsSession(session_token='tok-rozwiazanie', user_id=admin.id, status='active')
    db.session.add(sesja)
    db.session.flush()
    db.session.add(WmsSessionShippingRequest(session_id=sesja.id, shipping_request_id=zbiorcze.id))
    db.session.commit()

    # Sesja kończy się PRZED jawnym rozwiązaniem paczki — _sprawdz_edytowalnosc
    # przepuści (sesja nie jest już active/paused), ale junction zostaje.
    sesja.status = 'completed'
    db.session.commit()

    from modules.orders.consolidation import rozwiaz_konsolidacje
    from modules.orders.models import ShippingRequest
    zrodla = rozwiaz_konsolidacje(zbiorcze)
    db.session.commit()
    db.session.expire_all()

    assert len(zrodla) == 2
    assert db.session.get(ShippingRequest, zbiorcze_id) is None
    assert WmsSessionShippingRequest.query.filter_by(
        shipping_request_id=zbiorcze_id
    ).count() == 0


def test_anulowanie_ewikcja_wiodacego_wymienia_lidera(db, make_user, make_order):
    """Regres z code review: gdy ewikowany uczestnik był wiodący
    (lead_source_request_id), odepnij_anulowane_zamowienie zostawiała ten
    wskaźnik osieroconym — consolidation_participants (mail/push o scaleniu) nie
    znajdowałby dopasowania, a pozostali uczestnicy dostaliby komunikat, że
    paczka jedzie na adres kogoś, kto już nie jest w paczce, mimo że fizyczny
    adres się nie zmienił."""
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order, ile=3, orders_count=1)
    sr_a, sr_b, sr_c = zrodla
    assert zbiorcze.lead_source_request_id == sr_a.id
    sr_b.shipping_city = 'Gdańsk'
    db.session.commit()
    zamowienie = sr_a.display_orders[0]

    from modules.orders.consolidation import odepnij_anulowane_zamowienie
    odepnij_anulowane_zamowienie(zamowienie)
    db.session.commit()
    db.session.expire_all()

    assert sr_a.consolidated_into_id is None
    assert zbiorcze.lead_source_request_id == sr_b.id
    assert zbiorcze.shipping_city == 'Gdańsk'
    assert zbiorcze.user_id == sr_b.user_id


# ---------- Zamówienie do zwrotu (finalna recenzja, pkt 7) ----------
#
# Gałąź 'do_zwrotu' nie wypinała zamówienia z paczki, z uzasadnieniem „paczka
# i tak nie ruszy do wysyłki". To było prawdą dla zlecenia JEDNEGO klienta. Po
# konsolidacji bramki gotowości obejmują zamówienia wszystkich uczestników, więc
# jeden zwrot u jednej osoby zamrażał paczkę pozostałym.

def test_zamowienie_do_zwrotu_wypina_sie_z_paczki(db, make_user, make_order):
    from decimal import Decimal
    from modules.offers.models import OfferPage
    from modules.orders.models import PaymentConfirmation
    from utils.offer_closure import cancel_offer_orders

    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order, orders_count=2)
    admin = make_user(role='admin')
    strona = OfferPage(name='Zbiórka', token='tok-do-zwrotu', created_by=admin.id,
                       is_fully_closed=True, status='ended')
    db.session.add(strona)
    db.session.commit()

    zamowienie = sr_b.display_orders[0]
    zamowienie.offer_page_id = strona.id
    # Wpłata decyduje o 'do_zwrotu' zamiast 'anulowane' (order_has_payment).
    db.session.add(PaymentConfirmation(
        order_id=zamowienie.id, payment_stage='product',
        amount=Decimal('100.00'), status='approved'))
    db.session.commit()

    wynik = cancel_offer_orders(strona.id, [zamowienie.id], 'Wyprzedane', admin.id, notify=False)
    db.session.expire_all()

    assert wynik['to_refund'] == 1
    assert zamowienie.status == 'do_zwrotu'
    # Zamówienie wypada z paczki, reszta (3 pozostałe) zostaje — bramki gotowości
    # przestają na nie czekać.
    assert zamowienie.id not in {o.id for o in zbiorcze.display_orders}
    assert len(zbiorcze.request_orders) == 3
    assert sr_b.consolidated_into_id == zbiorcze.id


def test_admin_ustawiajac_do_zwrotu_tez_wypina_z_paczki(db, client, login, make_user, make_order):
    """Ta sama luka po stronie ręcznej zmiany statusu w panelu — inaczej admin
    wpisujący 'do zwrotu' jednemu klientowi zamraża paczkę pozostałym."""
    from modules.orders.models import OrderStatus
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order, orders_count=2)
    db.session.add(OrderStatus(slug='do_zwrotu', name='Do zwrotu', is_active=True))
    db.session.commit()

    zamowienie = sr_b.display_orders[0]
    login(make_user(role='admin', email='admin-zwrot@example.com', profile_completed=True))

    r = client.post(f'/admin/orders/{zamowienie.id}/status', data={'status': 'do_zwrotu'})
    assert r.status_code == 200
    db.session.expire_all()

    assert zamowienie.status == 'do_zwrotu'
    assert zamowienie.id not in {o.id for o in zbiorcze.display_orders}
    assert len(zbiorcze.request_orders) == 3
