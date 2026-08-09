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
