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
        PushManager, 'notify_pickup_reminder_bulk',
        staticmethod(lambda pary: push_calls.extend(pary)),
    )
    u = make_user()
    z = make_order(u, status='dostarczone_gom')

    with app.test_request_context():
        wynik = wyslij_przypomnienia([u.id])

    assert wynik['maile'] == 0
    assert wynik['mail_wylaczony'] is True
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
        PushManager, 'notify_pickup_reminder_bulk',
        staticmethod(lambda pary: push_calls.extend(pary)),
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
    assert wynik['bez_maila'] == 1
    assert wynik['mail_wylaczony'] is False
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
        PushManager, 'notify_pickup_reminder_bulk',
        staticmethod(lambda pary: push_calls.extend(pary)),
    )

    u = make_user()
    for _ in range(3):
        make_order(u, status='dostarczone_gom')

    with app.test_request_context():
        wyslij_przypomnienia([u.id])

    assert push_calls == [(u.id, 3)]


def test_push_jednym_wywolaniem_bulk_dla_wielu_klientow(
        app, db, make_user, make_order, batch_capture, monkeypatch):
    """Push dla całego zaznaczenia ma iść PRZEZ JEDNO wywołanie `notify_pickup_reminder_bulk`,
    nie przez pętlę wołającą `notify_pickup_reminder` per klient.

    To sedno P3 recenzji: `_fire_and_forget` na produkcji odpala osobny wątek OS
    na każde wywołanie, a ekran nie ma paginacji i ma „Zaznacz wszystkich" — pętla
    per klient przy większej zaległości odpalałaby dziesiątki/setki wątków naraz.
    Regresja do starego wzorca (`notify_pickup_reminder` w pętli w
    `wyslij_przypomnienia`) przeszłaby niezauważona przez test powyżej, bo on
    tylko sprawdza TREŚĆ argumentów, nie to, ile razy metoda bulk została wywołana.
    """
    from utils.push_manager import PushManager
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    calls = []
    monkeypatch.setattr(
        PushManager, 'notify_pickup_reminder_bulk',
        staticmethod(lambda pary: calls.append(list(pary))),
    )

    users = [make_user(email=f'zalegacz{i}@example.com') for i in range(5)]
    for u in users:
        make_order(u, status='dostarczone_gom')

    with app.test_request_context():
        wyslij_przypomnienia([u.id for u in users])

    assert len(calls) == 1  # jedno wywołanie bulk, nie pięć osobnych
    assert sorted(calls[0]) == sorted((u.id, 1) for u in users)


def test_bulk_pusha_wola_send_to_user_dla_kazdego_klienta(
        app, db, make_user, monkeypatch):
    """`notify_pickup_reminder_bulk` ma sam iterować po parach i wywołać
    `send_to_user` dla każdej — pod TESTING synchronicznie, w wątku wołającego
    (patrz docstring `_fire_and_forget`: testowa konfiguracja dzieli jedno
    połączenie SQLite między wątkami, więc wątek tła commitujący w tle
    rozjeżdżałby testy niezwiązane z pushem)."""
    from utils.push_manager import PushManager

    u1 = make_user(email='a@example.com')
    u2 = make_user(email='b@example.com')

    calls = []
    monkeypatch.setattr(
        PushManager, 'send_to_user',
        staticmethod(lambda user_id, title, body, url='/', tag='default',
                             notification_type=None: calls.append((user_id, body))),
    )

    with app.test_request_context():
        PushManager.notify_pickup_reminder_bulk([(u1.id, 1), (u2.id, 5)])

    assert len(calls) == 2
    tresci = dict(calls)
    assert tresci[u1.id] == 'Twoje zamówienie czeka na odbiór — zamów wysyłkę'
    assert tresci[u2.id] == 'Twoich 5 zamówień czeka na odbiór — zamów wysyłkę'


def test_bulk_pusha_pusta_lista_nic_nie_robi(app, monkeypatch):
    from utils.push_manager import PushManager

    calls = []
    monkeypatch.setattr(
        PushManager, 'send_to_user',
        staticmethod(lambda *a, **kw: calls.append((a, kw))),
    )

    with app.test_request_context():
        PushManager.notify_pickup_reminder_bulk([])

    assert calls == []


@pytest.mark.parametrize('n, oczekiwana', [
    (1, 'Twoje zamówienie czeka na odbiór — zamów wysyłkę'),
    (2, 'Twoje 2 zamówienia czekają na odbiór — zamów wysyłkę'),
    (5, 'Twoich 5 zamówień czeka na odbiór — zamów wysyłkę'),
    (12, 'Twoich 12 zamówień czeka na odbiór — zamów wysyłkę'),
])
def test_tresc_przypomnienia_odmienia_liczebnik(n, oczekiwana):
    """Klient dostaje poprawną polszczyznę dla każdej liczby zaległych zamówień —
    P5 recenzji: dla 5+ dotychczasowy tekst dawał '5 Twoje zamówienia czekają'
    zamiast '5 Twoich zamówień czeka'. 2-4 (poza 12-14) to inna forma niż 5+/12-14:
    zaimek, rzeczownik I czasownik zmieniają się razem z liczebnikiem."""
    from utils.push_manager import _tresc_przypomnienia_o_odbiorze

    assert _tresc_przypomnienia_o_odbiorze(n) == oczekiwana


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
