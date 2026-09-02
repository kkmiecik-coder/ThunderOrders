"""Przypomnienia „odbierz swoje rzeczy" (projekt 2026-09-02).

Reguła nadrzędna: jedna osoba = jeden mail, choćby zalegała z pięcioma paczkami.
Wysyłka jednym batchem — limit AUTH Hostingera, tak samo jak przy kosztach.
"""
import pytest


@pytest.fixture
def batch_capture(monkeypatch):
    """Przechwytuje send_email_batch — zwraca listę wywołań (każde = lista Message)."""
    import utils.email_sender as es
    calls = []
    monkeypatch.setattr(es, 'send_email_batch', lambda msgs: calls.append(msgs))
    return calls


def test_klient_z_trzema_zamowieniami_dostaje_jeden_mail(app, db, make_user,
                                                          make_order, batch_capture):
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    u = make_user(email='zalegacz@example.com')
    for _ in range(3):
        make_order(u, status='dostarczone_gom')

    with app.test_request_context():
        wynik = wyslij_przypomnienia([u.id])

    assert wynik['wyslane'] == 1
    assert len(batch_capture) == 1
    assert len(batch_capture[0]) == 1
    assert batch_capture[0][0].recipients == ['zalegacz@example.com']


def test_trzech_klientow_jednym_batchem(app, db, make_user, make_order, batch_capture):
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    users = [make_user(email=f'k{i}@example.com') for i in range(3)]
    for u in users:
        make_order(u, status='dostarczone_gom')

    with app.test_request_context():
        wynik = wyslij_przypomnienia([u.id for u in users])

    assert wynik['wyslane'] == 3
    assert len(batch_capture) == 1  # jedno połączenie SMTP, nie trzy
    assert len(batch_capture[0]) == 3


def test_wysylka_stempluje_wszystkie_zamowienia(app, db, make_user, make_order,
                                                 batch_capture):
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    u = make_user()
    zamowienia = [make_order(u, status='dostarczone_gom') for _ in range(3)]

    with app.test_request_context():
        wyslij_przypomnienia([u.id])

    for z in zamowienia:
        db.session.refresh(z)
        assert z.pickup_reminder_sent_at is not None


def test_zamowienie_juz_w_zleceniu_nie_dostaje_stempla(app, db, make_user, make_order,
                                                        batch_capture):
    """Przypomnienie dotyczy tylko tego, co realnie zalega."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    u = make_user()
    zalega = make_order(u, status='dostarczone_gom')
    zamowione = make_order(u, status='dostarczone_gom')
    zlecenie = ShippingRequest(request_number='WYS/9', user_id=u.id)
    db.session.add(zlecenie)
    db.session.commit()
    db.session.add(ShippingRequestOrder(shipping_request_id=zlecenie.id,
                                        order_id=zamowione.id))
    db.session.commit()

    with app.test_request_context():
        wyslij_przypomnienia([u.id])

    db.session.refresh(zalega)
    db.session.refresh(zamowione)
    assert zalega.pickup_reminder_sent_at is not None
    assert zamowione.pickup_reminder_sent_at is None


def test_klient_bez_zaleglosci_nie_dostaje_maila(app, db, make_user, make_order,
                                                  batch_capture):
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    u = make_user()
    make_order(u, status='nowe')

    with app.test_request_context():
        wynik = wyslij_przypomnienia([u.id])

    assert wynik['wyslane'] == 0
    assert batch_capture == []


def test_wylaczony_przelacznik_blokuje_maile_ale_nie_push(
        app, db, make_user, make_order, batch_capture, monkeypatch):
    """Wyłączenie maila to decyzja o JEDNYM kanale — push, dzwoneczek i stempel
    mają iść dalej, bo klient dalej realnie zalega."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    monkeypatch.setattr(
        EmailManager, 'is_email_enabled',
        staticmethod(lambda key: key != 'notify_pickup_reminder'),
    )
    push_calls = []
    monkeypatch.setattr(
        PushManager, 'notify_pickup_reminder',
        staticmethod(lambda user_id, n: push_calls.append((user_id, n))),
    )
    u = make_user()
    z = make_order(u, status='dostarczone_gom')

    with app.test_request_context():
        wynik = wyslij_przypomnienia([u.id])

    assert wynik['maile'] == 0
    assert batch_capture == []
    assert wynik['wyslane'] == 1
    assert push_calls == [(u.id, 1)]
    db.session.refresh(z)
    assert z.pickup_reminder_sent_at is not None


def test_mail_wymienia_numery_zamowien(app, db, make_user, make_order, batch_capture):
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    u = make_user()
    z = make_order(u, status='dostarczone_gom')

    with app.test_request_context():
        wyslij_przypomnienia([u.id])

    assert z.order_number in batch_capture[0][0].html


def test_klient_bez_maila_dostaje_mimo_to_push_i_stempel(
        app, db, make_user, make_order, batch_capture, monkeypatch):
    """Brak adresu u jednego z zaznaczonych nie wywraca operacji: pozostali
    dostają maile normalnie, a klient bez adresu i tak dostaje push + stempel."""
    from utils.push_manager import PushManager
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    push_calls = []
    monkeypatch.setattr(
        PushManager, 'notify_pickup_reminder',
        staticmethod(lambda user_id, n: push_calls.append((user_id, n))),
    )

    bez_maila = make_user(email='ktos-bez-maila@example.com')
    z_mailem = make_user(email='zmailem@example.com')
    z1 = make_order(bez_maila, status='dostarczone_gom')
    z2 = make_order(z_mailem, status='dostarczone_gom')

    # Symulacja braku adresu: EmailManager czyta atrybut na obiekcie z sesji
    # (identity map), więc modyfikacja w pamięci — bez commitu — wystarczy, żeby
    # zobaczyć, jak zachowuje się branch „klient bez adresu".
    bez_maila.email = ''

    with app.test_request_context():
        wynik = wyslij_przypomnienia([bez_maila.id, z_mailem.id])

    assert wynik['wyslane'] == 2
    assert wynik['maile'] == 1
    assert len(batch_capture) == 1
    assert len(batch_capture[0]) == 1
    assert batch_capture[0][0].recipients == ['zmailem@example.com']

    assert (bez_maila.id, 1) in push_calls
    assert (z_mailem.id, 1) in push_calls

    db.session.refresh(z1)
    db.session.refresh(z2)
    assert z1.pickup_reminder_sent_at is not None
    assert z2.pickup_reminder_sent_at is not None


def test_push_wywolany_raz_na_klienta_z_liczba_zamowien(
        app, db, make_user, make_order, batch_capture, monkeypatch):
    """Push ma iść RAZ na klienta (z liczbą jego zamówień w argumencie), nie
    raz na zamówienie — inaczej klient z trzema paczkami dostałby trzy powiadomienia."""
    from utils.push_manager import PushManager
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    push_calls = []
    monkeypatch.setattr(
        PushManager, 'notify_pickup_reminder',
        staticmethod(lambda user_id, n: push_calls.append((user_id, n))),
    )

    u = make_user()
    for _ in range(3):
        make_order(u, status='dostarczone_gom')

    with app.test_request_context():
        wyslij_przypomnienia([u.id])

    assert push_calls == [(u.id, 3)]


def test_pozycja_bez_nazwy_nie_wypuszcza_none_do_maila(
        app, db, make_user, make_order, batch_capture):
    """Bliźniacza sytuacja do `zbierz_nieodebrane()`: pozycja bez produktu i bez
    własnej nazwy ma dostać fallback 'Bez nazwy', a nie zaśmiecić maila słowem
    'None' (obie kolumny — product_id i custom_name — są nullable)."""
    from decimal import Decimal
    from modules.orders.models import OrderItem
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    u = make_user()
    z = make_order(u, status='dostarczone_gom')
    it = OrderItem(
        order_id=z.id,
        product_id=None,
        custom_name=None,
        is_custom=True,
        quantity=2,
        price=Decimal('50.00'),
        total=Decimal('100.00'),
    )
    db.session.add(it)
    db.session.commit()

    with app.test_request_context():
        wyslij_przypomnienia([u.id])

    html = batch_capture[0][0].html
    assert 'None' not in html
    assert 'Bez nazwy' in html


def test_trasa_wymaga_admina(app, client, db, make_user, login):
    login(make_user(role='client'))

    r = client.post('/admin/orders/nieodebrane/przypomnij', json={'user_ids': [1]})

    assert r.status_code in (302, 403)


def test_trasa_zwraca_liczbe_wyslanych(app, client, db, make_user, make_order,
                                        login, batch_capture):
    login(make_user(role='admin', email='admin@example.com'))
    u = make_user(email='zalegacz@example.com')
    make_order(u, status='dostarczone_gom')

    r = client.post('/admin/orders/nieodebrane/przypomnij', json={'user_ids': [u.id]})

    assert r.status_code == 200
    assert r.get_json()['wyslane'] == 1


def test_trasa_odrzuca_pusta_liste(app, client, db, make_user, login):
    login(make_user(role='admin', email='admin@example.com'))

    r = client.post('/admin/orders/nieodebrane/przypomnij', json={'user_ids': []})

    assert r.status_code == 400


def test_trasa_odrzuca_nieliczbowy_identyfikator(app, client, db, make_user, login):
    """Zły payload (np. z popsutego JS-a) ma dać czytelny błąd 400 po polsku,
    a nie wywrócić się nieobsłużonym 500 na `int(uid)`."""
    login(make_user(role='admin', email='admin@example.com'))

    r = client.post('/admin/orders/nieodebrane/przypomnij',
                    json={'user_ids': ['abc']})

    assert r.status_code == 400
    dane = r.get_json()
    assert dane['success'] is False
    assert dane['message']
