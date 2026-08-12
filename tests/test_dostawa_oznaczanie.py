"""dostarcz_zlecenie() — jedyne miejsce przeprowadzające przejście na 'dostarczone'."""
import pytest


def _zlecenie(db, user, numer, status='wyslane'):
    from modules.orders.models import ShippingRequest
    sr = ShippingRequest(request_number=numer, user_id=user.id, status=status)
    db.session.add(sr)
    db.session.commit()
    return sr


def _podepnij(db, sr, order):
    from modules.orders.models import ShippingRequestOrder
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=order.id))
    db.session.commit()


def test_domyka_zlecenie_i_kaskaduje_na_zamowienia(app, db, make_user, make_order):
    from modules.orders.wms_utils import dostarcz_zlecenie

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000001')
    order = make_order(user, status='wyslane')
    _podepnij(db, sr, order)

    wynik = dostarcz_zlecenie(sr, source='klient', powiadom=False)

    assert sr.status == 'dostarczone'
    assert sr.delivered_at is not None
    assert sr.delivered_source == 'klient'
    assert order.status == 'dostarczone'
    assert [o.id for o in wynik['zmienione_zamowienia']] == [order.id]


def test_dopisuje_przedmioty_do_kolekcji(app, db, make_user, make_order, make_product):
    from modules.client.models import CollectionItem
    from modules.orders.models import OrderItem
    from modules.orders.wms_utils import dostarcz_zlecenie

    user = make_user()
    produkt = make_product()
    sr = _zlecenie(db, user, 'WYS/000002')
    order = make_order(user, status='wyslane')
    # product_name to @property (product.name albo custom_name), nie kolumna —
    # OrderItem wymaga za to total (NOT NULL, nieliczony automatycznie).
    db.session.add(OrderItem(
        order_id=order.id, product_id=produkt.id,
        quantity=1, price=99.00, total=99.00))
    db.session.commit()
    _podepnij(db, sr, order)

    dostarcz_zlecenie(sr, source='klient', powiadom=False)

    assert CollectionItem.query.filter_by(user_id=user.id).count() == 1


def test_drugie_wywolanie_nic_nie_zmienia(app, db, make_user):
    from modules.orders.wms_utils import ZlecenieJuzDostarczone, dostarcz_zlecenie

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000003')
    dostarcz_zlecenie(sr, source='klient', powiadom=False)
    pierwsza_data = sr.delivered_at

    with pytest.raises(ZlecenieJuzDostarczone):
        dostarcz_zlecenie(sr, source='auto', powiadom=False)

    assert sr.delivered_source == 'klient'
    assert sr.delivered_at == pierwsza_data


def test_zlecenie_zrodlowe_nie_domyka_sie_samo(app, db, make_user):
    from modules.orders.wms_utils import ZlecenieZrodloweNieDomykane, dostarcz_zlecenie

    user = make_user()
    zbiorcze = _zlecenie(db, user, 'WYS/000010')
    zrodlo = _zlecenie(db, user, 'WYS/000011')
    zrodlo.consolidated_into_id = zbiorcze.id
    db.session.commit()

    with pytest.raises(ZlecenieZrodloweNieDomykane):
        dostarcz_zlecenie(zrodlo, source='klient', powiadom=False)


def test_paczka_zbiorcza_domyka_wszystkie_zrodla(app, db, make_user, make_order):
    from modules.orders.models import ShippingRequestOrder
    from modules.orders.wms_utils import dostarcz_zlecenie

    lider = make_user()
    drugi = make_user()
    zbiorcze = _zlecenie(db, lider, 'WYS/000020')
    zrodlo_a = _zlecenie(db, lider, 'WYS/000021')
    zrodlo_b = _zlecenie(db, drugi, 'WYS/000022')
    for z in (zrodlo_a, zrodlo_b):
        z.consolidated_into_id = zbiorcze.id
    zbiorcze.lead_source_request_id = zrodlo_a.id

    order_a = make_order(lider, status='wyslane')
    order_b = make_order(drugi, status='wyslane')
    db.session.add(ShippingRequestOrder(
        shipping_request_id=zbiorcze.id, order_id=order_a.id, source_request_id=zrodlo_a.id))
    db.session.add(ShippingRequestOrder(
        shipping_request_id=zbiorcze.id, order_id=order_b.id, source_request_id=zrodlo_b.id))
    db.session.commit()

    dostarcz_zlecenie(zbiorcze, source='klient', powiadom=False)

    assert zbiorcze.status == 'dostarczone'
    assert zrodlo_a.status == 'dostarczone'
    assert zrodlo_b.status == 'dostarczone'
    assert order_a.status == 'dostarczone'
    assert order_b.status == 'dostarczone'


def test_powiadom_false_nic_nie_wysyla(app, db, make_user, make_order, monkeypatch):
    from utils.email_manager import EmailManager
    from modules.orders.wms_utils import dostarcz_zlecenie

    wyslane = []
    monkeypatch.setattr(
        EmailManager, 'notify_delivery_confirmed',
        staticmethod(lambda *a, **k: wyslane.append(1)),
        raising=False)

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000030')
    _podepnij(db, sr, make_order(user, status='wyslane'))

    dostarcz_zlecenie(sr, source='klient', powiadom=False)

    assert wyslane == []


def test_zlecenie_historyczne_bez_delivered_at_nie_domyka_sie_wprost(
        app, db, make_user, monkeypatch):
    """Zlecenia sprzed tej funkcjonalności (aplikacja działa od kwietnia) mają
    status='dostarczone', ale puste delivered_at — Task 1 backfillował wyłącznie
    shipped_at, nikt nie backfillował delivered_at. Wywołanie bezpośrednie (bez
    status_juz_ustawiony, czyli tak jak wołają panel klienta/cron/API mobilne)
    musi taki rekord potraktować jako już dostarczony i nie ruszać go — inaczej
    dostałby nadpisaną datą „teraz", delivered_source i mailem z podziękowaniem
    za odbiór sprzed miesięcy."""
    from utils.email_manager import EmailManager
    from modules.orders.wms_utils import ZlecenieJuzDostarczone, dostarcz_zlecenie

    wyslane = []
    monkeypatch.setattr(
        EmailManager, 'notify_delivery_confirmed',
        staticmethod(lambda *a, **k: wyslane.append(1)),
        raising=False)

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000040', status='dostarczone')
    assert sr.delivered_at is None

    with pytest.raises(ZlecenieJuzDostarczone):
        dostarcz_zlecenie(sr, source='klient', powiadom=True)

    assert sr.delivered_at is None
    assert sr.delivered_source is None
    assert wyslane == []


def test_status_juz_ustawiony_domyka_zlecenie_ktore_admin_juz_przestawil(
        app, db, make_user, make_order):
    """Ścieżka admina (_sync_order_statuses_from_shipping_request) sama ustawia
    sr.status='dostarczone' i commituje ZANIM wywoła dostarcz_zlecenie() — z
    status_juz_ustawiony=True funkcja wie, że to nie jest rekord historyczny,
    tylko domknięcie w toku, i mimo status=='dostarczone' na wejściu poprawnie
    ustawia delivered_at/delivered_source oraz kaskaduje zamówienia."""
    from modules.orders.wms_utils import dostarcz_zlecenie

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000041', status='dostarczone')
    order = make_order(user, status='wyslane')
    _podepnij(db, sr, order)
    assert sr.delivered_at is None

    wynik = dostarcz_zlecenie(
        sr, source='admin', powiadom=False, status_juz_ustawiony=True)

    assert sr.delivered_at is not None
    assert sr.delivered_source == 'admin'
    assert order.status == 'dostarczone'
    assert [o.id for o in wynik['zmienione_zamowienia']] == [order.id]


def test_put_endpoint_domyka_dostawe_mimo_wczesniejszego_ustawienia_statusu(
        client, db, make_user, make_order, make_product, login):
    """Regresja spoza briefu: `_zapisz_zlecenie_wysylki` (routes.py) ustawia
    `sr.status` na nową wartość i commituje ZANIM wywoła
    `_sync_order_statuses_from_shipping_request` — dla przejścia na 'dostarczone'
    strażnik `dostarcz_zlecenie()` widziałby więc `sr.status == 'dostarczone'`
    już na WEJŚCIU, mimo że to pierwsze (i jedyne) domknięcie. Strażnik patrzy
    na `delivered_at`, nie na `status`, właśnie dlatego — inaczej zapis statusu
    z panelu admina zawsze łapałby ZlecenieJuzDostarczone i dokładnie ta ścieżka
    (jedna z trzech, które to zadanie miało scalić) nadal gubiłaby dopisanie do
    kolekcji, mimo napisanej funkcji."""
    from modules.client.models import CollectionItem
    from modules.orders.models import OrderItem, ShippingRequest, ShippingRequestOrder

    admin = make_user(role='admin')
    user = make_user()
    produkt = make_product()
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status='wyslane')
    db.session.add(sr)
    db.session.commit()
    order = make_order(user, status='wyslane')
    db.session.add(OrderItem(
        order_id=order.id, product_id=produkt.id,
        quantity=1, price=42.00, total=42.00))
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=order.id))
    db.session.commit()

    login(admin)
    r = client.put(f'/admin/orders/shipping-requests/{sr.id}', json={'status': 'dostarczone'})

    assert r.status_code == 200
    db.session.refresh(sr)
    db.session.refresh(order)
    assert sr.status == 'dostarczone'
    assert sr.delivered_at is not None
    assert sr.delivered_source == 'admin'
    assert order.status == 'dostarczone'
    assert CollectionItem.query.filter_by(user_id=user.id).count() == 1
