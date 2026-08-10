"""Endpointy admina do konsolidacji zleceń wysyłki."""
import pytest
from test_shipping_consolidation import _seed_sr_statuses, _sr, _konsolidacja  # noqa: E402


def _admin(make_user):
    return make_user(role='admin', email='admin@example.com', profile_completed=True)


def test_preview_zwraca_zlecenia_z_adresami(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)
    login(_admin(make_user))

    r = client.get(f'/admin/orders/shipping-requests/consolidation-preview?ids={sr_a.id},{sr_b.id}')
    assert r.status_code == 200
    dane = r.get_json()
    assert dane['success'] is True
    assert len(dane['requests']) == 2
    assert dane['requests'][0]['full_address']
    assert dane['requests'][0]['client_name']
    assert dane['blocked'] == []


def test_konsolidacja_endpointem(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_a.id, sr_b.id], 'lead_request_id': sr_a.id,
    })
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    db.session.expire_all()
    assert sr_a.consolidated_into_id is not None


def test_konsolidacja_odrzuca_wyslane(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order, status='wyslane')
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_a.id, sr_b.id], 'lead_request_id': sr_a.id,
    })
    assert r.status_code == 409
    assert 'wysłane' in r.get_json()['error']


def test_zmiana_wiodacego_wypiecie_i_rozwiazanie(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order, ile=3)
    login(_admin(make_user))

    r = client.post(f'/admin/orders/shipping-requests/{zbiorcze.id}/consolidation/lead',
                    json={'lead_request_id': zrodla[1].id})
    assert r.status_code == 200

    r = client.post(f'/admin/orders/shipping-requests/{zbiorcze.id}/consolidation/detach',
                    json={'source_id': zrodla[2].id})
    assert r.status_code == 200
    assert r.get_json()['dissolved'] is False

    r = client.post(f'/admin/orders/shipping-requests/{zbiorcze.id}/consolidation/dissolve', json={})
    assert r.status_code == 200


def test_endpointy_wymagaja_admina(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)
    login(make_user())  # zwykły klient

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_a.id, sr_b.id], 'lead_request_id': sr_a.id,
    })
    assert r.status_code in (302, 403)


def test_stary_bulk_merge_zniknal(db, client, login, make_user):
    login(_admin(make_user))
    r = client.post('/admin/orders/shipping-requests/bulk-merge', json={'ids': [1, 2]})
    assert r.status_code == 404


def test_konsolidacja_dopina_do_istniejacej_paczki(db, client, login, make_user, make_order):
    """Gałąź target_id — jedyna, której do tej pory nic nie sprawdzało (użyje jej Task 14)."""
    _seed_sr_statuses(db)
    zbiorcze, _zrodla = _konsolidacja(db, make_user, make_order, ile=2)
    c = make_user()
    sr_c, _ = _sr(db, c, make_order)
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_c.id], 'target_id': zbiorcze.id,
    })
    assert r.status_code == 200
    db.session.expire_all()
    assert sr_c.consolidated_into_id == zbiorcze.id


def test_preview_z_istniejaca_paczka_w_zestawie_nie_blokuje(db, client, login, make_user, make_order):
    """Modal (Task 14) w trybie dopięcia wysyła do preview zaznaczenie, które zawiera
    ISTNIEJĄCĄ paczkę zbiorczą + nowego kandydata. Bez target= w waliduj_do_konsolidacji
    taki zestaw był zawsze fałszywie odrzucany jako „łączenie paczek ze sobą", mimo że to
    poprawny scenariusz dopięcia (patrz openConsolidationModal w shipping-requests.js)."""
    _seed_sr_statuses(db)
    zbiorcze, _zrodla = _konsolidacja(db, make_user, make_order, ile=2)
    c = make_user()
    sr_c, _ = _sr(db, c, make_order)
    login(_admin(make_user))

    r = client.get(
        f'/admin/orders/shipping-requests/consolidation-preview?ids={zbiorcze.id},{sr_c.id}')
    assert r.status_code == 200
    dane = r.get_json()
    assert dane['blocked'] == []


def test_preview_same_nieparsowalne_ids(db, client, login, make_user):
    login(_admin(make_user))
    r = client.get('/admin/orders/shipping-requests/consolidation-preview?ids=abc,def')
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_konsolidacja_odrzuca_nieparsowalne_ids(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_a.id, 'abc'], 'lead_request_id': sr_a.id,
    })
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_konsolidacja_odrzuca_nieparsowalny_target_id(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_a.id, sr_b.id], 'target_id': 'abc',
    })
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_konsolidacja_odrzuca_nieparsowalny_lead_request_id(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_a.id, sr_b.id], 'lead_request_id': 'abc',
    })
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_zmiana_wiodacego_odrzuca_nieparsowalny_id(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, _zrodla = _konsolidacja(db, make_user, make_order, ile=2)
    login(_admin(make_user))

    r = client.post(f'/admin/orders/shipping-requests/{zbiorcze.id}/consolidation/lead',
                    json={'lead_request_id': 'abc'})
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_detach_odrzuca_nieparsowalny_source_id(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, _zrodla = _konsolidacja(db, make_user, make_order, ile=2)
    login(_admin(make_user))

    r = client.post(f'/admin/orders/shipping-requests/{zbiorcze.id}/consolidation/detach',
                    json={'source_id': 'abc'})
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_lista_wms_pokazuje_paczke_zamiast_zrodel(db, client, login, make_user, make_order):
    """Źródło nie dostaje własnej karty na liście — jest tylko wchłonięte w kartę
    paczki zbiorczej. Od Task 15 karta paczki grupuje zamówienia po uczestniku i
    podpisuje każdą grupę numerem jej źródłowego zlecenia (żeby dało się je
    rozróżnić przy zarządzaniu paczką) — więc numer źródła w treści strony jest
    tu oczekiwany, o ile pojawia się tylko jako etykieta grupy, nie jako osobna
    karta z tym numerem w nagłówku."""
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.get('/admin/orders/wms')
    tresc = r.get_data(as_text=True)
    assert zbiorcze.request_number in tresc
    assert f'data-request-id="{zrodla[0].id}"' not in tresc


def test_filtr_scalone_pokazuje_zrodla(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.get('/admin/orders/wms?consolidation=sources')
    tresc = r.get_data(as_text=True)
    assert zrodla[0].request_number in tresc


def test_filtr_scalone_z_typem_zamowienia_widzi_zrodlo(db, client, login, make_user, make_order):
    """Źródło traci własne wiersze junction (przeniesione do zbiorczego ze śladem
    source_request_id) — filtr typu w widoku źródeł musi czytać TEN ślad, inaczej
    żadne źródło nigdy by go nie przeszło, mimo że realnie ma takie zamówienia."""
    _seed_sr_statuses(db)
    from modules.orders.consolidation import utworz_konsolidacje
    from modules.orders.models import ShippingRequest, ShippingRequestOrder

    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)  # zamówienie domyślnego typu on_hand

    order_exclusive = make_order(b, order_type='exclusive')
    sr_b = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=b.id, status='oplacone', address_type='home',
    )
    db.session.add(sr_b)
    db.session.flush()
    db.session.add(ShippingRequestOrder(shipping_request_id=sr_b.id, order_id=order_exclusive.id))
    db.session.commit()

    utworz_konsolidacje([sr_a.id, sr_b.id], lead_request_id=sr_a.id)
    db.session.commit()
    login(_admin(make_user))

    r = client.get('/admin/orders/wms?consolidation=sources&order_type=exclusive')
    tresc = r.get_data(as_text=True)
    assert sr_b.request_number in tresc
    assert sr_a.request_number not in tresc


def test_filtered_ids_pomija_zrodla(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.get('/api/orders/shipping-requests/filtered-ids')
    ids = {int(x['id']) for x in r.get_json()['requests']}
    assert zbiorcze.id in ids
    assert zrodla[0].id not in ids


def test_eksport_inpost_nie_dubluje_etykiet(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    zbiorcze.parcel_size = 'A'
    for zr in zrodla:
        zr.parcel_size = 'A'
    db.session.commit()
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/export-inpost',
                    json={'ids': [zbiorcze.id] + [z.id for z in zrodla]})
    assert r.status_code == 200
    csv_text = r.get_json()['csv']
    # Jedna paczka fizyczna = jeden wiersz, niezależnie od liczby zaznaczonych zleceń.
    assert csv_text.count(zbiorcze.request_number) <= 1
    for zr in zrodla:
        assert zr.request_number not in csv_text


def test_kasowanie_paczki_odpina_zrodla(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.delete(f'/admin/orders/shipping-requests/{zbiorcze.id}')
    assert r.status_code == 200
    db.session.expire_all()

    from modules.orders.models import ShippingRequest
    for zr in zrodla:
        odswiezone = db.session.get(ShippingRequest, zr.id)
        assert odswiezone is not None
        assert odswiezone.consolidated_into_id is None
        # Zamówienia wróciły do właściciela, a nie zniknęły razem z paczką.
        assert len(odswiezone.request_orders) == 1


def test_nie_da_sie_skasowac_zrodlowego(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.delete(f'/admin/orders/shipping-requests/{zrodla[0].id}')
    assert r.status_code == 409
    assert 'zbiorcz' in r.get_json()['message'].lower()


def test_kasowanie_spakowanej_paczki_ma_komunikat_o_kasowaniu(db, client, login, make_user, make_order):
    """Regres z code review (rundy 1, task 17): _sprawdz_edytowalnosc (wołane przez
    rozwiaz_konsolidacje) rzuca „nie można zmieniać jej składu" — trafne przy
    dopinaniu/wypinaniu, ale mylące przy próbie SKASOWANIA. Endpoint musi dać
    komunikat pasujący do tego, co admin faktycznie próbował zrobić."""
    _seed_sr_statuses(db)
    zbiorcze, _zrodla = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'spakowane'
    db.session.commit()
    login(_admin(make_user))

    r = client.delete(f'/admin/orders/shipping-requests/{zbiorcze.id}')
    assert r.status_code == 409
    tresc = r.get_json()['message'].lower()
    assert 'spakowana' in tresc
    assert 'skasować' in tresc or 'usun' in tresc
    assert 'skład' not in tresc  # stary, mylący komunikat z _sprawdz_edytowalnosc


def test_koszt_tylko_dla_zamowien_z_tego_zlecenia(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, orders_a = _sr(db, a, make_order)
    sr_b, orders_b = _sr(db, b, make_order)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr_a.id}', json={
        'order_costs': [{'order_id': orders_b[0].id, 'shipping_cost': 99}],
    })
    assert r.status_code == 400
    db.session.expire_all()
    # Order.shipping_cost ma default=0.00 (nullable=False) — świeże zamówienie z
    # make_order nigdy nie jest None. Test brief-u zakładał None; realna asercja
    # to „nie 99", czyli że endpoint nie zapisał cudzego kosztu.
    assert orders_b[0].shipping_cost == 0


@pytest.fixture
def bez_powiadomien_o_koszcie(monkeypatch):
    """Koszt zaakceptowany przez endpoint wysyła mail/push (notify_cost_added).
    PushManager robi to w wątku tła (_fire_and_forget) — bez podmiany wątek
    dobija się do zamkniętej już testowej sesji SQLite po zakończeniu testu
    (PytestUnhandledThreadExceptionWarning). Podmieniamy na wyższym poziomie,
    tak jak `przechwycone`/`package_notifications` gdzie indziej w pakiecie."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    monkeypatch.setattr(EmailManager, 'notify_cost_added', staticmethod(lambda *a, **kw: None))
    monkeypatch.setattr(PushManager, 'notify_cost_added', staticmethod(lambda *a, **kw: None))


def test_koszt_dla_wlasnego_zamowienia_przechodzi(db, client, login, make_user, make_order,
                                                   bez_powiadomien_o_koszcie):
    """Regres z code review (rundy 1, task 17): brief ostrzegał, że regresja na
    ekranie wyceny byłaby dotkliwa, a jedyny trwały test pokrywał wyłącznie
    odmowę — trzeba też sprawdzić, że walidacja NIE blokuje poprawnego żądania."""
    _seed_sr_statuses(db)
    a = make_user()
    sr_a, orders_a = _sr(db, a, make_order)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr_a.id}', json={
        'order_costs': [{'order_id': orders_a[0].id, 'shipping_cost': 42}],
    })
    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert float(orders_a[0].shipping_cost) == 42.0


def test_koszt_dla_uczestnika_paczki_zbiorczej_przechodzi(db, client, login, make_user, make_order,
                                                           bez_powiadomien_o_koszcie):
    """Zamówienie NIE-lidera paczki zbiorczej musi przejść walidację — należy do
    zlecenia zbiorczego przez request_orders (source_request_id), mimo że jego
    właściciel to nie sr.user (tym jest lider)."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    zamowienie_b = sr_b.display_orders[0]
    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}', json={
        'order_costs': [{'order_id': zamowienie_b.id, 'shipping_cost': 15}],
    })
    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert float(zamowienie_b.shipping_cost) == 15.0


def test_bulk_cancel_paczka_i_zrodlo_zaznaczone_razem_zrodlo_pierwsze(
        db, client, login, make_user, make_order):
    """Regres z code review (rundy 1, task 17): zaznaczenie w UI przeżywa
    przełączenie filtra `consolidation=sources` (sessionStorage), więc admin może
    zaznaczyć źródło w widoku źródeł, wrócić do widoku domyślnego, dozaznaczyć
    paczkę i kliknąć „usuń zaznaczone" — z ID w kolejności [źródło, paczka].
    Wynik NIE może zależeć od tej kolejności: skoro admin zaznaczył oba, oba mają
    zniknąć, a nie „źródło ciche przywrócone, bez ostrzeżenia"."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/bulk-cancel', json={
        'ids': [sr_a.id, zbiorcze.id],
    })
    assert r.status_code == 200
    dane = r.get_json()
    assert dane['skipped_count'] == 0

    db.session.expire_all()
    from modules.orders.models import ShippingRequest
    assert db.session.get(ShippingRequest, zbiorcze.id) is None
    assert db.session.get(ShippingRequest, sr_a.id) is None
    odswiezone_b = db.session.get(ShippingRequest, sr_b.id)
    assert odswiezone_b is not None
    assert odswiezone_b.consolidated_into_id is None
    assert len(odswiezone_b.request_orders) == 1


def test_bulk_cancel_paczka_i_zrodlo_zaznaczone_razem_paczka_pierwsza(
        db, client, login, make_user, make_order):
    """To samo zaznaczenie, ID w kolejności [paczka, źródło] — wynik ma być
    identyczny jak w poprzednim teście, niezależnie od kolejności."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/bulk-cancel', json={
        'ids': [zbiorcze.id, sr_a.id],
    })
    assert r.status_code == 200
    dane = r.get_json()
    assert dane['skipped_count'] == 0

    db.session.expire_all()
    from modules.orders.models import ShippingRequest
    assert db.session.get(ShippingRequest, zbiorcze.id) is None
    assert db.session.get(ShippingRequest, sr_a.id) is None
    odswiezone_b = db.session.get(ShippingRequest, sr_b.id)
    assert odswiezone_b is not None
    assert odswiezone_b.consolidated_into_id is None
    assert len(odswiezone_b.request_orders) == 1


def test_bulk_cancel_samo_zrodlo_bez_paczki_jest_pomijane(db, client, login, make_user, make_order):
    """Kontrast wobec dwóch powyższych: gdy paczka NIE jest w zaznaczeniu, samo
    źródło musi zostać pominięte (nie skasowane), z powodem w komunikacie."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/bulk-cancel', json={
        'ids': [sr_a.id],
    })
    assert r.status_code == 200
    dane = r.get_json()
    assert dane['skipped_count'] == 1
    assert sr_a.request_number in dane['message']
    assert 'paczce zbiorczej' in dane['message']

    db.session.expire_all()
    from modules.orders.models import ShippingRequest
    odswiezone_a = db.session.get(ShippingRequest, sr_a.id)
    assert odswiezone_a is not None
    assert odswiezone_a.consolidated_into_id == zbiorcze.id


def test_eksport_inpost_ostrzega_o_pominietych_zrodlach(db, client, login, make_user, make_order):
    """Zaznaczone źródła znikają z zapytania (filtr consolidated_into_id), więc bez
    jawnego ostrzeżenia admin nie wiedziałby, czemu zaznaczył więcej pozycji, niż
    ma wierszy w pliku."""
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    zbiorcze.parcel_size = 'A'
    db.session.commit()
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/export-inpost',
                    json={'ids': [zbiorcze.id] + [z.id for z in zrodla]})
    assert r.status_code == 200
    dane = r.get_json()
    assert dane['exported'] == 1
    ostrzezenia = ' '.join(dane['warnings'])
    for zr in zrodla:
        assert zr.request_number in ostrzezenia
    assert zbiorcze.request_number in ostrzezenia



@pytest.fixture
def bez_powiadomien(monkeypatch, bez_powiadomien_o_koszcie):
    """Pełny przepływ dotyka też maili o statusie i o wysyłce. Każdy z nich startuje
    wątek tła, a testowe SQLite trzyma jedno wspólne połączenie in-memory — wątek
    zostawiony po teście potrafi wywrócić dane NASTĘPNEGO (obserwowane: koszty
    zamówień wracające do 0.00). Ta sama technika co `bez_powiadomien_o_koszcie`."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    for nazwa in ('notify_shipping_status_change', 'notify_shipment_sent',
                  'notify_status_change'):
        monkeypatch.setattr(EmailManager, nazwa, staticmethod(lambda *a, **kw: None))
        monkeypatch.setattr(PushManager, nazwa, staticmethod(lambda *a, **kw: None))
    monkeypatch.setattr(PushManager, '_fire_and_forget', staticmethod(lambda **kw: None))


def test_pelny_przeplyw_konsolidacja_wycena_zaplata_wysylka(
        db, client, login, make_user, make_order, bez_powiadomien):
    """Scenariusz wprost ze specyfikacji, od stanu powstającego naturalnie.

    Regres z finalnej recenzji: auto-przejście po wycenie ustawiało
    'czeka_na_oplacenie' WYŁĄCZNIE na edytowanym zleceniu, czyli na paczce
    zbiorczej. `propaguj_na_zrodla` świadomie nie zjeżdża ze statusem finansowym
    w dół, a `_sprawdz_oplacenie_konsolidacji` podnosi uczestnika na 'oplacone'
    tylko z 'czeka_na_oplacenie' — warunku, którego nikt nigdy nie spełniał.
    Paczka wisiała na 'czeka_na_oplacenie' i `ship_shipping_request` odrzucał ją
    przez UNPAID_SR_STATUSES, a klient widział u siebie „Czeka na wycenę".

    Dlatego ten test NIE ustawia statusów ręcznie na żadnym etapie — każdy stan
    ma powstać z poprzedniego kroku.
    """
    from decimal import Decimal
    from test_wms_ship_and_reopen import _seed_statuses
    from modules.orders.models import PaymentConfirmation, ShippingRequest

    _seed_sr_statuses(db)
    _seed_statuses(db)
    a, b = make_user(), make_user()
    sr_a, orders_a = _sr(db, a, make_order, status='czeka_na_wycene')
    sr_b, orders_b = _sr(db, b, make_order, status='czeka_na_wycene')
    login(_admin(make_user))

    # 1. Admin konsoliduje dwa zlecenia różnych klientów.
    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_a.id, sr_b.id], 'lead_request_id': sr_a.id,
    })
    assert r.status_code == 200
    db.session.expire_all()
    zbiorcze = db.session.get(ShippingRequest, sr_a.consolidated_into_id)
    assert zbiorcze.status == 'czeka_na_wycene'

    # 2. Admin wpisuje koszty w modalu „Dodaj koszty" — na PACZCE, bo tylko ona
    #    jest widoczna na liście WMS.
    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}', json={
        'order_costs': [{'order_id': o.id, 'shipping_cost': 15.0}
                        for o in (orders_a[0], orders_b[0])],
    })
    assert r.status_code == 200
    db.session.expire_all()

    # Sedno poprawki: uczestnicy schodzą z „czeka na wycenę". To także jest to,
    # co klient widzi u siebie w panelu — zgodne ze statusem paczki.
    assert sr_a.status == 'czeka_na_oplacenie'
    assert sr_b.status == 'czeka_na_oplacenie'
    assert zbiorcze.status == 'czeka_na_oplacenie'

    # 3. Obaj klienci płacą E4, admin zatwierdza potwierdzenia.
    from modules.admin.payment_confirmations import _check_sr_auto_oplacone
    for zamowienie in (orders_a[0], orders_b[0]):
        db.session.add(PaymentConfirmation(
            order_id=zamowienie.id, payment_stage='domestic_shipping',
            status='approved', amount=Decimal('15.00')))
    db.session.commit()
    for zamowienie in (orders_a[0], orders_b[0]):
        _check_sr_auto_oplacone(zamowienie)
    db.session.expire_all()

    assert sr_a.status == 'oplacone'
    assert sr_b.status == 'oplacone'
    assert zbiorcze.status == 'oplacone'

    # 4. Wysyłka przechodzi — wcześniej leciał ShippingRequestUnpaid.
    from modules.orders.wms_utils import ship_shipping_request
    ship_shipping_request(zbiorcze, courier='inpost', tracking_number='622555666')
    db.session.expire_all()

    assert zbiorcze.status == 'wyslane'
    assert sr_a.status == 'wyslane'
    assert sr_b.status == 'wyslane'
    assert sr_b.tracking_number == '622555666'


def test_wycena_paczki_podnosi_tylko_wycenionego_uczestnika(
        db, client, login, make_user, make_order, bez_powiadomien):
    """Wycena części zamówień nie może przepchnąć nieopłaconego uczestnika dalej —
    paczka zostaje na „czeka na wycenę", bo jej status to minimum ze źródeł."""
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, orders_a = _sr(db, a, make_order, status='czeka_na_wycene')
    sr_b, _orders_b = _sr(db, b, make_order, status='czeka_na_wycene')
    login(_admin(make_user))

    client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_a.id, sr_b.id], 'lead_request_id': sr_a.id,
    })
    db.session.expire_all()
    from modules.orders.models import ShippingRequest
    zbiorcze = db.session.get(ShippingRequest, sr_a.consolidated_into_id)

    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}', json={
        'order_costs': [{'order_id': orders_a[0].id, 'shipping_cost': 12.0}],
    })
    assert r.status_code == 200
    db.session.expire_all()

    assert sr_a.status == 'czeka_na_oplacenie'
    assert sr_b.status == 'czeka_na_wycene'
    assert zbiorcze.status == 'czeka_na_wycene'

