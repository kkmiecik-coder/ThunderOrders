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


def test_tabela_ostatnich_zlecen_pomija_paczke_zbiorcza(
        app, db, client, login, make_user):
    """Tabela „Ostatnie zlecenia wysyłki" ma tę samą jednostkę co KPI i wykresy w
    tej samej zakładce (ZLECENIE KLIENTA, patrz `_bez_paczek_zbiorczych()`) — bez
    filtra pokazywała zarówno paczkę zbiorczą, jak i jej zlecenia źródłowe, czyli
    tę samą fizyczną wysyłkę więcej niż raz, inaczej niż liczniki obok."""
    from modules.orders.models import ShippingRequest

    admin = make_user(role='admin', email='admin-tabela@example.com',
                      profile_completed=True)
    lider = make_user(email='lider-tabela@example.com')
    drugi = make_user(email='drugi-tabela@example.com')

    zbiorcze = ShippingRequest(
        request_number='WYS/000640', user_id=lider.id, status='wyslane')
    db.session.add(zbiorcze)
    db.session.commit()
    for numer, user in (('WYS/000641', lider), ('WYS/000642', drugi)):
        db.session.add(ShippingRequest(
            request_number=numer, user_id=user.id, status='wyslane',
            consolidated_into_id=zbiorcze.id))
    db.session.commit()

    login(admin)
    dane = client.get('/admin/statistics/api/shipping').get_json()

    tabela = next(t for t in dane['tables'] if t['title'] == 'Ostatnie zlecenia wysyłki')
    numery_w_tabeli = [row[0] for row in tabela['rows']]

    assert 'WYS/000640' not in numery_w_tabeli, 'paczka zbiorcza nie jest zleceniem klienta'
    assert 'WYS/000641' in numery_w_tabeli
    assert 'WYS/000642' in numery_w_tabeli


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


def test_lista_opinii_filtruje_tylko_z_komentarzem(app, db, client, login, make_user):
    """Brak pokrycia dla `with_comment=1` — jedynego filtra listy opinii poza
    oceną. `DeliveryReview.comment` jest nullable, więc filtr musi realnie
    odróżnić NULL od pustego/wypełnionego komentarza, nie tylko nie wywalić się."""
    from modules.orders.review_models import DeliveryReview

    admin = make_user(role='admin', profile_completed=True)
    klient = make_user()
    sr_z_komentarzem = _dostarczone(db, klient, 'WYS/000622', 'klient')
    sr_bez_komentarza = _dostarczone(db, klient, 'WYS/000623', 'klient')
    db.session.add(DeliveryReview(
        shipping_request_id=sr_z_komentarzem.id, user_id=klient.id, rating=5,
        comment='Szybka dostawa, wszystko OK'))
    db.session.add(DeliveryReview(
        shipping_request_id=sr_bez_komentarza.id, user_id=klient.id, rating=4))
    db.session.commit()

    login(admin)
    odp = client.get('/admin/shipping-requests/opinie?with_comment=1')

    assert odp.status_code == 200
    assert b'WYS/000622' in odp.data
    assert b'WYS/000623' not in odp.data


def test_lista_opinii_bez_filtra_pokazuje_wszystkie_niezaleznie_od_komentarza(
        app, db, client, login, make_user):
    """Kontrast wobec testu wyżej: bez `with_comment` filtr nie działa wcale —
    opinia bez komentarza ma się pokazać."""
    from modules.orders.review_models import DeliveryReview

    admin = make_user(role='admin', profile_completed=True)
    klient = make_user()
    sr_z_komentarzem = _dostarczone(db, klient, 'WYS/000624', 'klient')
    sr_bez_komentarza = _dostarczone(db, klient, 'WYS/000625', 'klient')
    db.session.add(DeliveryReview(
        shipping_request_id=sr_z_komentarzem.id, user_id=klient.id, rating=5,
        comment='Super'))
    db.session.add(DeliveryReview(
        shipping_request_id=sr_bez_komentarza.id, user_id=klient.id, rating=4))
    db.session.commit()

    login(admin)
    odp = client.get('/admin/shipping-requests/opinie')

    assert odp.status_code == 200
    assert b'WYS/000624' in odp.data
    assert b'WYS/000625' in odp.data


def test_lista_opinii_filtruje_tylko_z_komentarzem_w_kombinacji_z_ocena(
        app, db, client, login, make_user):
    """Oba filtry naraz (AND, nie OR) — opinia musi spełnić WARUNEK OCENY i mieć
    komentarz, żeby się pokazać."""
    from modules.orders.review_models import DeliveryReview

    admin = make_user(role='admin', profile_completed=True)
    klient = make_user()
    # Pasuje do obu filtrów naraz.
    pasujaca = _dostarczone(db, klient, 'WYS/000626', 'klient')
    # Ocena się zgadza, ale bez komentarza — ma odpaść przez with_comment.
    bez_komentarza = _dostarczone(db, klient, 'WYS/000627', 'klient')
    # Komentarz jest, ale inna ocena — ma odpaść przez rating.
    inna_ocena = _dostarczone(db, klient, 'WYS/000628', 'klient')
    db.session.add(DeliveryReview(
        shipping_request_id=pasujaca.id, user_id=klient.id, rating=5, comment='Ok'))
    db.session.add(DeliveryReview(
        shipping_request_id=bez_komentarza.id, user_id=klient.id, rating=5))
    db.session.add(DeliveryReview(
        shipping_request_id=inna_ocena.id, user_id=klient.id, rating=3, comment='Ok'))
    db.session.commit()

    login(admin)
    odp = client.get('/admin/shipping-requests/opinie?rating=5&with_comment=1')

    assert odp.status_code == 200
    assert b'WYS/000626' in odp.data
    assert b'WYS/000627' not in odp.data
    assert b'WYS/000628' not in odp.data


def test_lista_opinii_pokazuje_nawigacje_i_liczbe_wszystkich_wynikow(
        app, db, client, login, make_user):
    """Paginacja bez sygnału w UI była gorsza niż jej brak.

    Pierwsza wersja tej zmiany oddawała szablonowi samą listę `pagination.items`,
    więc widok ucinał się po cichu na 20 wierszach: admin przy 25 opiniach widział
    20 i NIE MIAŁ SKĄD wiedzieć, że reszta istnieje — w tym ewentualne oceny 1–2
    z reklamacjami. Wcześniej (`.all()`) widział wszystko.

    Sprawdzamy jedno i drugie: że da się przejść na kolejną stronę i że widoczna
    jest łączna liczba wyników.
    """
    from modules.orders.review_models import DeliveryReview

    admin = make_user(role='admin', profile_completed=True)
    klient = make_user()
    for i in range(25):
        sr = _dostarczone(db, klient, f'WYS/0008{i:02d}', 'klient')
        db.session.add(DeliveryReview(shipping_request_id=sr.id, user_id=klient.id, rating=5))
    db.session.commit()

    login(admin)
    odp = client.get('/admin/shipping-requests/opinie')
    html = odp.get_data(as_text=True)

    assert odp.status_code == 200
    # Nawigacja z makra components/_pagination.html — link „następna strona".
    assert 'rel="next"' in html
    assert 'page=2' in html
    # Licznik wszystkich wyników, nie tylko tych z bieżącej strony.
    assert '25 pozycji' in html


def test_lista_opinii_niesie_filtry_w_linkach_paginacji(
        app, db, client, login, make_user):
    """Skok na stronę 2 nie może gubić filtra — inaczej admin ogląda drugą stronę
    czegoś zupełnie innego niż to, co przefiltrował."""
    import re

    from modules.orders.review_models import DeliveryReview

    admin = make_user(role='admin', profile_completed=True)
    klient = make_user()
    for i in range(25):
        sr = _dostarczone(db, klient, f'WYS/0009{i:02d}', 'klient')
        db.session.add(DeliveryReview(
            shipping_request_id=sr.id, user_id=klient.id, rating=1, comment='Reklamacja'))
    db.session.commit()

    login(admin)
    odp = client.get('/admin/shipping-requests/opinie?rating=1&with_comment=1')
    html = odp.get_data(as_text=True)

    assert odp.status_code == 200
    dopasowanie = re.search(r'<a href="([^"]+)"[^>]*rel="next"', html)
    assert dopasowanie, 'brak linku „następna strona" mimo 25 opinii na stronach po 20'

    # Oba filtry muszą jechać razem z numerem strony w tym samym adresie.
    link_next = dopasowanie.group(1)
    assert 'page=2' in link_next
    assert 'rating=1' in link_next
    assert 'with_comment=1' in link_next


def test_lista_opinii_ma_paginacje_i_nie_laduje_wszystkiego_naraz(
        app, db, client, login, make_user):
    """`.all()` bez limitu ładowało całą tabelę na raz — tu sprawdzamy, że ponad
    jedna strona wyników realnie ogranicza to, co wraca w pojedynczym żądaniu
    (per_page=20 w admin_delivery_reviews)."""
    from modules.orders.review_models import DeliveryReview

    admin = make_user(role='admin', profile_completed=True)
    klient = make_user()
    for i in range(25):
        sr = _dostarczone(db, klient, f'WYS/0007{i:02d}', 'klient')
        db.session.add(DeliveryReview(shipping_request_id=sr.id, user_id=klient.id, rating=5))
    db.session.commit()

    login(admin)
    strona_1 = client.get('/admin/shipping-requests/opinie')
    strona_2 = client.get('/admin/shipping-requests/opinie?page=2')

    assert strona_1.status_code == 200
    assert strona_2.status_code == 200
    assert strona_1.data.count(b'WYS/0007') == 20
    assert strona_2.data.count(b'WYS/0007') == 5


# ====================
# ZLECENIE ŹRÓDŁOWE PACZKI ZBIORCZEJ A ZAPIS STATUSU
# ====================

def _admin_statusow(make_user):
    return make_user(role='admin', email='admin-statusy@example.com', profile_completed=True)


def _zrodlo_w_paczce(db, user, numer_paczki, numer_zrodla, status):
    """Paczka zbiorcza + jedno zlecenie źródłowe w tym samym statusie."""
    from modules.orders.models import ShippingRequest

    zbiorcze = ShippingRequest(request_number=numer_paczki, user_id=user.id, status=status)
    db.session.add(zbiorcze)
    db.session.commit()
    zrodlo = ShippingRequest(request_number=numer_zrodla, user_id=user.id, status=status,
                             consolidated_into_id=zbiorcze.id)
    db.session.add(zrodlo)
    db.session.commit()
    return zbiorcze, zrodlo


def test_bulk_status_zapisuje_status_finansowy_na_zrodle_paczki_zbiorczej(
        app, db, client, login, make_user):
    """Pomijanie źródeł miało dotyczyć TYLKO statusów logistycznych.

    `propaguj_na_zrodla` kopiuje na uczestników wyłącznie STATUSY_LOGISTYCZNE —
    dla finansów propagacja jest celowo wyłączona („finanse zostają indywidualne"),
    a `przeprowadz_uczestnikow_na_oplacenie` wprost ZAPISUJE je na źródłach. Gdy
    pomijanie objęło każdy status, ustawienie źródłu „opłacone" stało się cichym
    no-opem, a komunikat radził adminowi „zmień status całej paczki", co też by
    źródeł nie ruszyło.
    """
    lider = make_user(email='lider-finanse@example.com')
    _zbiorcze, zrodlo = _zrodlo_w_paczce(
        db, lider, 'WYS/000810', 'WYS/000811', 'czeka_na_oplacenie')
    login(_admin_statusow(make_user))

    r = client.post('/admin/orders/shipping-requests/bulk-status', json={
        'ids': [zrodlo.id], 'status': 'oplacone',
    })

    assert r.status_code == 200
    assert r.get_json()['skipped_source_count'] == 0
    db.session.refresh(zrodlo)
    assert zrodlo.status == 'oplacone'


def test_put_zlecenia_odmawia_statusu_logistycznego_zrodlu_ale_zapisuje_reszte(
        app, db, client, login, make_user, make_order):
    """Ten sam połowiczny stan żył w bliźniaczej trasie PUT (`_zapisz_zlecenie_wysylki`).

    Zapis ustawiał źródłu `status='dostarczone'` i commitował, a strażnik
    `ZlecenieZrodloweNieDomykane` w `dostarcz_zlecenie()` odrzucał je dopiero
    w synchronizacji statusów — czyli PO commicie. Zostawało „dostarczone" bez
    `delivered_at`, bez kaskady na zamówienia i bez kolekcji; cron tego nie
    podniesie (filtruje status=='wyslane').

    Drugi człon testu pilnuje, żeby strażnik nie był ZA szeroki: modal wysyła cały
    payload, więc niezmieniony status w żądaniu nie może blokować zapisu kosztów.
    """
    from modules.orders.models import ShippingRequestOrder

    lider = make_user(email='lider-put@example.com')
    _zbiorcze, zrodlo = _zrodlo_w_paczce(db, lider, 'WYS/000820', 'WYS/000821', 'wyslane')
    zamowienie = make_order(lider, status='wyslane')
    db.session.add(ShippingRequestOrder(
        shipping_request_id=zrodlo.id, order_id=zamowienie.id))
    db.session.commit()
    login(_admin_statusow(make_user))

    odmowa = client.put(f'/admin/orders/shipping-requests/{zrodlo.id}', json={
        'status': 'dostarczone',
    })

    assert odmowa.status_code == 400
    assert 'paczce zbiorczej' in odmowa.get_json()['error']
    db.session.refresh(zrodlo)
    db.session.refresh(zamowienie)
    assert zrodlo.status == 'wyslane'
    assert zrodlo.delivered_at is None
    assert zamowienie.status == 'wyslane'

    # Ten sam status co w bazie = brak zmiany: zapis ma przejść razem z kosztami.
    bez_zmiany = client.put(f'/admin/orders/shipping-requests/{zrodlo.id}', json={
        'status': 'wyslane',
        'order_costs': [{'order_id': zamowienie.id, 'shipping_cost': 19.99}],
    })

    assert bez_zmiany.status_code == 200
    db.session.refresh(zamowienie)
    assert float(zamowienie.shipping_cost) == 19.99
