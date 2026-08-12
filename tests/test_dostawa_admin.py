"""Admin: lista opinii i metryki dostaw."""


def _dostarczone(db, user, numer, source):
    from modules.orders.models import ShippingRequest, get_local_now
    sr = ShippingRequest(request_number=numer, user_id=user.id, status='dostarczone',
                         delivered_at=get_local_now(), delivered_source=source)
    db.session.add(sr)
    db.session.commit()
    return sr


def test_statystyki_licza_srednia_i_rozklad(app, db, make_user):
    from modules.admin.statistics import statystyki_dostaw
    from modules.orders.review_models import DeliveryReview

    user = make_user()
    for i, ocena in enumerate((5, 5, 3), start=1):
        sr = _dostarczone(db, user, f'WYS/00060{i}', 'klient')
        db.session.add(DeliveryReview(
            shipping_request_id=sr.id, user_id=user.id, rating=ocena))
    db.session.commit()

    dane = statystyki_dostaw()

    assert dane['liczba_opinii'] == 3
    assert round(dane['srednia_ocena'], 2) == 4.33
    assert dane['rozklad'][5] == 2
    assert dane['rozklad'][3] == 1
    assert dane['rozklad'][1] == 0


def test_statystyki_licza_udzial_potwierdzen(app, db, make_user):
    from modules.admin.statistics import statystyki_dostaw

    user = make_user()
    _dostarczone(db, user, 'WYS/000610', 'klient')
    _dostarczone(db, user, 'WYS/000611', 'auto')
    _dostarczone(db, user, 'WYS/000612', 'auto')
    _dostarczone(db, user, 'WYS/000613', 'auto')

    dane = statystyki_dostaw()

    assert dane['potwierdzone_przez_klienta'] == 1
    assert dane['domkniete_automatem'] == 3
    assert dane['udzial_potwierdzen'] == 25.0


def test_statystyki_nie_licza_paczki_zbiorczej_obok_jej_zrodel(app, db, make_user):
    """Paczka zbiorcza to byt magazynowy — liczą się zlecenia klientów.

    `propaguj_na_zrodla` kopiuje `delivered_source` z paczki na wszystkie jej
    zlecenia źródłowe, więc jedna fizyczna przesyłka dwóch osób zapisywała się
    w bazie TRZY razy: paczka + dwa źródła. Kafelek raportuje „X z Y dostarczonych
    zleceń", a Y liczy `total_requests` z filtrem `nie_paczka_zbiorcza` — bez tego
    samego filtra po stronie X liczby obok siebie były w różnych jednostkach
    i obie zawyżone.

    Oczekujemy 2, nie 1: dwóch klientów zamówiło dwie wysyłki i obie zostały
    dostarczone. Zliczenie samej paczki (1) mówiłoby „1 z 2", czyli że jeden
    z klientów odbioru nie ma — nieprawda, a przy tym rozjazd z `total_requests`.
    """
    from modules.admin.statistics import statystyki_dostaw
    from modules.orders.models import ShippingRequest, get_local_now

    lider = make_user(email='lider-stat@example.com')
    drugi = make_user(email='drugi-stat@example.com')
    teraz = get_local_now()

    zbiorcze = ShippingRequest(
        request_number='WYS/000620', user_id=lider.id, status='dostarczone',
        delivered_at=teraz, delivered_source='klient')
    db.session.add(zbiorcze)
    db.session.commit()

    # Stan po propaguj_na_zrodla(): źródła dziedziczą status, datę i źródło.
    for numer, user in (('WYS/000621', lider), ('WYS/000622', drugi)):
        db.session.add(ShippingRequest(
            request_number=numer, user_id=user.id, status='dostarczone',
            delivered_at=teraz, delivered_source='klient',
            consolidated_into_id=zbiorcze.id))
    db.session.commit()
    assert zbiorcze.is_consolidation
    assert ShippingRequest.query.filter_by(delivered_source='klient').count() == 3

    dane = statystyki_dostaw()

    assert dane['potwierdzone_przez_klienta'] == 2
    assert dane['domkniete_automatem'] == 0
    assert dane['udzial_potwierdzen'] == 100.0


def test_statystyki_dostaw_licza_w_tych_samych_jednostkach_co_kafelek_obok(
        app, db, client, login, make_user):
    """Mianownik podpowiedzi („X z Y dostarczonych zleceń") ma się mieścić
    w `total_requests` z tego samego JSON-a. Jedno wywołanie endpointu, bo to
    właśnie zestawienie obu liczb obok siebie widzi admin."""
    from modules.orders.models import ShippingRequest, get_local_now

    # profile_completed=True — bez tego before_request odsyła na uzupełnienie
    # profilu i endpoint nie oddaje JSON-a.
    admin = make_user(role='admin', email='admin-stat@example.com',
                      profile_completed=True)
    klient = make_user(email='klient-stat@example.com')
    teraz = get_local_now()

    zbiorcze = ShippingRequest(
        request_number='WYS/000630', user_id=klient.id, status='dostarczone',
        delivered_at=teraz, delivered_source='auto')
    db.session.add(zbiorcze)
    db.session.commit()
    for numer in ('WYS/000631', 'WYS/000632'):
        db.session.add(ShippingRequest(
            request_number=numer, user_id=klient.id, status='dostarczone',
            delivered_at=teraz, delivered_source='auto',
            consolidated_into_id=zbiorcze.id))
    db.session.commit()

    login(admin)
    dane = client.get('/admin/statistics/api/shipping').get_json()

    delivery = dane['delivery']
    razem = delivery['potwierdzone_przez_klienta'] + delivery['domkniete_automatem']
    lacznie_zlecen = next(
        k['raw'] for k in dane['kpis'] if k['label'] == 'Łącznie zleceń wysyłki')

    assert razem == 2
    assert lacznie_zlecen == 2
    assert razem <= lacznie_zlecen, (
        'dostarczonych zleceń nie może być więcej niż wszystkich zleceń')


def test_statystyki_bez_danych_nie_dziela_przez_zero(app, db):
    from modules.admin.statistics import statystyki_dostaw

    dane = statystyki_dostaw()

    assert dane['liczba_opinii'] == 0
    assert dane['srednia_ocena'] is None
    assert dane['udzial_potwierdzen'] == 0.0


def test_lista_opinii_wymaga_admina(app, db, client, login, make_user):
    klient = make_user()
    login(klient)

    odp = client.get('/admin/shipping-requests/opinie')

    assert odp.status_code in (302, 403)


def test_lista_opinii_filtruje_po_ocenie(app, db, client, login, make_user):
    from modules.orders.review_models import DeliveryReview

    admin = make_user(role='admin', profile_completed=True)
    klient = make_user()
    sr_a = _dostarczone(db, klient, 'WYS/000620', 'klient')
    sr_b = _dostarczone(db, klient, 'WYS/000621', 'klient')
    db.session.add(DeliveryReview(shipping_request_id=sr_a.id, user_id=klient.id, rating=5))
    db.session.add(DeliveryReview(shipping_request_id=sr_b.id, user_id=klient.id, rating=2))
    db.session.commit()

    login(admin)
    odp = client.get('/admin/shipping-requests/opinie?rating=2')

    assert odp.status_code == 200
    assert b'WYS/000621' in odp.data
    assert b'WYS/000620' not in odp.data
