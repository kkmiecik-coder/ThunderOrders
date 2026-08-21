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


# ---------- Liczniki admina (finalna recenzja, pkt 2) ----------
#
# Paczka zbiorcza i jej zlecenia źródłowe współistnieją w tabeli, więc COUNT po
# ShippingRequest bez żadnego filtra liczy jedną konsolidację tyle razy, ilu ma
# uczestników (+1). Które wiersze odpadają, zależy od jednostki danego widoku:
# dashboard liczy PACZKI do obsłużenia, statystyki — ZLECENIA klientów.

def test_kafelki_dashboardu_licza_paczke_raz(db, make_user, make_order):
    """Kafelki to kolejka zadań magazynu: dwa scalone zlecenia to jeden karton
    do wyceny, spakowania i wysłania — jedna pozycja na liście WMS, jedna na kafelku."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    for sr in (zbiorcze, sr_a, sr_b):
        sr.status = 'czeka_na_wycene'
    db.session.commit()

    from modules.admin.routes import get_shipping_alert_counts
    liczniki = get_shipping_alert_counts()
    assert liczniki['to_quote'] == 1
    assert liczniki['total'] == 1


def test_statystyki_wysylki_licza_zlecenia_klientow(db, client, login, make_user, make_order):
    """Statystyki raportują, ile wysyłek zamówili KLIENCI — dwóch klientów zamówiło
    dwie, a to, że magazyn włożył je do jednego kartonu, jest jego decyzją operacyjną
    i nie może wstecznie zmniejszać biznesowego wolumenu."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    for sr in (zbiorcze, sr_a, sr_b):
        sr.status = 'czeka_na_wycene'
    db.session.commit()
    login(_admin(make_user))

    dane = client.get('/admin/statistics/api/shipping').get_json()
    kpi = {k['label']: k['raw'] for k in dane['kpis']}
    assert kpi['Łącznie zleceń wysyłki'] == 2
    assert kpi['Oczekujących'] == 2


def test_statystyki_oczekujacych_liczy_oba_statusy_przedplatne(
        db, client, login, make_user, make_order):
    """KPI „Oczekujących" ma znaczyć wszystko PRZED wysyłką — regres slugu
    'wycenione' (nigdy nie istniał w shipping_request_statuses) gubił zlecenia,
    które są już wycenione, ale jeszcze nieopłacone. Właściwa para statusów
    przedpłatnych to czeka_na_wycene i czeka_na_oplacenie (tak samo liczy je
    UNPAID_SR_STATUSES w modules/orders/wms_utils.py). Zlecenia opłacone,
    spakowane i wysłane mają wysyłkę już za sobą (albo w toku) i nie są
    „oczekujące"."""
    _seed_sr_statuses(db)
    a, b, c, d, e = (make_user() for _ in range(5))
    _sr(db, a, make_order, status='czeka_na_wycene')
    _sr(db, b, make_order, status='czeka_na_oplacenie')
    _sr(db, c, make_order, status='oplacone')
    _sr(db, d, make_order, status='spakowane')
    _sr(db, e, make_order, status='wyslane')
    login(_admin(make_user))

    dane = client.get('/admin/statistics/api/shipping').get_json()
    kpi = {k['label']: k['raw'] for k in dane['kpis']}
    # Łącznie zleceń liczy wszystkie zlecenia klientów niezależnie od statusu.
    assert kpi['Łącznie zleceń wysyłki'] == 5
    # Oczekujących — tylko te dwa statusy przed wysyłką.
    assert kpi['Oczekujących'] == 2


def test_statystyki_koszt_wysylki_nie_zmienia_sie_po_konsolidacji(
        db, client, login, make_user, make_order):
    """Sedno regresu: zlecenia wycenione PRZED scaleniem trzymają kwoty na sobie, a
    nowa paczka ma total_shipping_cost = NULL. KPI liczone z kolumny na zleceniu gubiło
    wtedy całą sumę; liczone z zamówień jest identyczne przed i po konsolidacji."""
    from modules.orders.models import ShippingRequest
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, orders_a = _sr(db, a, make_order)
    sr_b, orders_b = _sr(db, b, make_order)
    for o, kwota in zip(orders_a + orders_b, [15.00, 24.50]):
        o.shipping_cost = kwota
    sr_a.total_shipping_cost = 15.00
    sr_b.total_shipping_cost = 24.50
    db.session.commit()
    login(_admin(make_user))

    def _koszt():
        dane = client.get('/admin/statistics/api/shipping').get_json()
        return {k['label']: k['raw'] for k in dane['kpis']}['Łączny koszt wysyłki']

    przed = _koszt()
    assert przed == pytest.approx(39.50)

    from modules.orders.consolidation import utworz_konsolidacje
    zbiorcze = utworz_konsolidacje([sr_a.id, sr_b.id], lead_request_id=sr_a.id)
    db.session.commit()
    # Paczka nie dostała kwoty przy scaleniu — tak działa serwis i tak wygląda stan
    # w bazie do czasu, aż admin otworzy modal wyceny.
    assert db.session.get(ShippingRequest, zbiorcze.id).total_shipping_cost is None

    assert _koszt() == pytest.approx(przed)


# ---------- Luki pokrycia wymagane specyfikacją (finalna recenzja, pkt 8) ----------

def test_konsolidacja_odrzuca_zlecenie_w_aktywnej_sesji_wms(
        db, client, login, make_user, make_order):
    """Spec, sekcja „Wejście w konsolidację": zlecenie wiszące w otwartej sesji WMS
    nie może zmienić składu — magazynier ma je fizycznie na stole."""
    from modules.orders.wms_models import WmsSession, WmsSessionShippingRequest
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)
    magazynier = _admin(make_user)

    sesja = WmsSession(session_token='tok-konsolidacja', user_id=magazynier.id, status='active')
    db.session.add(sesja)
    db.session.flush()
    db.session.add(WmsSessionShippingRequest(session_id=sesja.id, shipping_request_id=sr_b.id))
    db.session.commit()
    login(magazynier)

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_a.id, sr_b.id], 'lead_request_id': sr_a.id,
    })
    assert r.status_code == 409
    blad = r.get_json()['error']
    assert sr_b.request_number in blad
    assert 'sesji WMS' in blad
    db.session.expire_all()
    assert sr_a.consolidated_into_id is None


def test_nie_laczymy_dwoch_paczek_zbiorczych(db, client, login, make_user, make_order):
    """Spec, „poza zakresem": łączenie dwóch paczek zbiorczych. Dotąd testy trafiały
    wyłącznie w gałąź `is_consolidated_source` (zlecenie źródłowe), nigdy w
    `is_consolidation` dla elementu scalanego."""
    _seed_sr_statuses(db)
    paczka_1, _ = _konsolidacja(db, make_user, make_order)
    paczka_2, _ = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [paczka_1.id, paczka_2.id], 'target_id': paczka_1.id,
    })
    assert r.status_code == 409
    blad = r.get_json()['error']
    assert paczka_2.request_number in blad
    assert 'paczką zbiorczą' in blad
    db.session.expire_all()
    assert paczka_2.consolidated_into_id is None


def test_karta_wms_pokazuje_wycene_paczki_zbiorczej(db, client, login, make_user, make_order):
    """Karta zlecenia w WMS renderowała surową kolumnę `total_shipping_cost`, której
    konsolidacja nie ustawia — nad zamówieniami wycenionymi na 21,49 + 21,49 admin
    czytał „Brak wyceny", choć modal wysyłki w tej samej chwili liczył 42,98."""
    from decimal import Decimal
    _seed_sr_statuses(db)
    zbiorcze, _zrodla = _konsolidacja(db, make_user, make_order)
    for o in zbiorcze.display_orders:
        o.shipping_cost = Decimal('21.49')
    db.session.commit()
    login(_admin(make_user))

    tresc = client.get('/admin/orders/wms').get_data(as_text=True)
    assert '42.98 PLN' in tresc
    assert 'Brak wyceny' not in tresc


def test_panel_pakowania_zna_adresata_i_wycene(db, make_user, make_order):
    """Nagłówek panelu pakowania pokazywał „WYS/000049 — — 2 zam." — magazynier nie
    widział, do kogo pakuje karton. Payload sesji dawał tylko `shipping_name` (puste
    przy paczkomacie) i surową kolumnę kosztu (pustą na paczce zbiorczej)."""
    from decimal import Decimal
    from modules.orders.wms_models import WmsSession, WmsSessionOrder
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, _sr_b) = _konsolidacja(db, make_user, make_order)
    # Paczkomat: adres w polach pickup_*, rubryka z nazwiskiem pusta.
    zbiorcze.address_type = 'pickup_point'
    zbiorcze.shipping_name = None
    zbiorcze.pickup_courier = 'InPost'
    zbiorcze.pickup_point_id = 'KRA01M'
    for o in zbiorcze.display_orders:
        o.shipping_cost = Decimal('21.49')
    magazynier = _admin(make_user)
    db.session.commit()

    sesja = WmsSession(session_token='tok-pakowanie', user_id=magazynier.id, status='active')
    db.session.add(sesja)
    db.session.flush()
    for i, o in enumerate(zbiorcze.display_orders):
        db.session.add(WmsSessionOrder(session_id=sesja.id, order_id=o.id, sort_order=i))
    db.session.commit()

    from modules.orders.wms import _build_session_data
    dane = _build_session_data(sesja)
    payload = dane['orders'][0]['shipping_request']

    oczekiwany = f'{sr_a.user.first_name} {sr_a.user.last_name}'
    assert payload['addressee_name'] == oczekiwany
    assert payload['total_shipping_cost'] == 42.98


def _paczka_z_wycena_mieszana(db, make_user, make_order):
    """Paczka zbiorcza: zlecenie WYCENIONE + zlecenie NIEWYCENIONE.

    Dokładnie ten układ wywalał produkcję — dopiero konsolidacja stawia w jednym
    modalu zamówienia z kosztem i bez kosztu, więc część pól wyceny renderuje się
    pusta i wraca w payloadzie jako 0.
    """
    from decimal import Decimal
    from modules.orders.consolidation import utworz_konsolidacje
    _seed_sr_statuses(db)
    sr_a, (order_a,) = _sr(db, make_user(), make_order, status='czeka_na_wycene')
    sr_b, (order_b,) = _sr(db, make_user(), make_order, status='czeka_na_wycene')
    order_a.shipping_cost = Decimal('21.49')   # wycenione wcześniej
    order_b.shipping_cost = Decimal('0.00')    # jeszcze nie wycenione → pole puste w modalu
    db.session.commit()

    zbiorcze = utworz_konsolidacje([sr_a.id, sr_b.id], lead_request_id=sr_a.id)
    db.session.commit()
    return zbiorcze, order_a, order_b


def test_zapis_wyceny_z_pustym_polem_kosztu_zapisuje_zero(db, client, login, make_user, make_order):
    """Regres 500 z produkcji: pusta kwota w modalu wyceny paczki zbiorczej.

    `order.shipping_cost = koszt if koszt > 0 else None` wpisywało NULL do kolumny
    NOT NULL — pymysql wywalał IntegrityError 1048, a admin dostawał gołe 500 bez
    komunikatu. Decyzja właściciela produktu: pusta kwota = 0 zł, zapis ma przejść.
    """
    from decimal import Decimal
    from modules.orders.models import Order
    zbiorcze, order_a, order_b = _paczka_z_wycena_mieszana(db, make_user, make_order)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}', json={
        'order_costs': [
            {'order_id': order_a.id, 'shipping_cost': 30.0},   # admin dopisał kwotę
            {'order_id': order_b.id, 'shipping_cost': 0},      # pole zostawione puste
        ],
        'parcel_size': 'A',
    })

    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()['success'] is True
    db.session.expire_all()
    assert db.session.get(Order, order_a.id).shipping_cost == Decimal('30.00')
    # Zero, nie NULL — „brak kosztu" w tym module zawsze znaczyło 0 (patrz
    # `(o.shipping_cost or 0) > 0` w consolidation.py i email_managerze).
    assert db.session.get(Order, order_b.id).shipping_cost == Decimal('0.00')


def test_zapis_wyceny_zerowanie_wczesniejszej_kwoty(db, client, login, make_user, make_order):
    """Wyczyszczenie wcześniej wpisanej kwoty też ma przejść, a nie kończyć się 500."""
    from decimal import Decimal
    from modules.orders.models import Order
    zbiorcze, order_a, order_b = _paczka_z_wycena_mieszana(db, make_user, make_order)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}', json={
        'order_costs': [
            {'order_id': order_a.id, 'shipping_cost': 0},   # skasowana kwota 21,49
            {'order_id': order_b.id, 'shipping_cost': 0},
        ],
    })

    assert r.status_code == 200, r.get_data(as_text=True)
    db.session.expire_all()
    assert db.session.get(Order, order_a.id).shipping_cost == Decimal('0.00')


def test_zapis_odmawia_zamowienia_spoza_zlecenia_i_mowi_dlaczego(db, client, login, make_user, make_order):
    """Komunikat ma nazwać zlecenie, zamówienie i powód — nie samo „Błąd zapisu"."""
    zbiorcze, _order_a, _order_b = _paczka_z_wycena_mieszana(db, make_user, make_order)
    obce = make_order(make_user())
    db.session.commit()
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}', json={
        'order_costs': [{'order_id': obce.id, 'shipping_cost': 10}],
    })

    assert r.status_code == 400
    blad = r.get_json()['error']
    assert blad == (f'Nie zapisano zlecenia {zbiorcze.request_number} — '
                    f'zamówienie {obce.order_number}: nie należy do tego zlecenia wysyłki')


def test_zapis_odmawia_kwoty_ktora_nie_jest_liczba(db, client, login, make_user, make_order):
    """Wcześniej `shipping_cost > 0` na tekście wywalało TypeError → gołe 500."""
    zbiorcze, order_a, _order_b = _paczka_z_wycena_mieszana(db, make_user, make_order)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}', json={
        'order_costs': [{'order_id': order_a.id, 'shipping_cost': 'dwadzieścia'}],
    })

    assert r.status_code == 400
    blad = r.get_json()['error']
    assert zbiorcze.request_number in blad
    assert order_a.order_number in blad
    assert 'nie jest liczbą' in blad


def test_zapis_odmawia_kwoty_ujemnej(db, client, login, make_user, make_order):
    from decimal import Decimal
    from modules.orders.models import Order
    zbiorcze, order_a, _order_b = _paczka_z_wycena_mieszana(db, make_user, make_order)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}', json={
        'order_costs': [{'order_id': order_a.id, 'shipping_cost': -5}],
    })

    assert r.status_code == 400
    assert 'ujemna' in r.get_json()['error']
    db.session.expire_all()
    assert db.session.get(Order, order_a.id).shipping_cost == Decimal('21.49')   # bez zmian


def test_zapis_odmawia_nieczytelnego_terminu_platnosci(db, client, login, make_user, make_order):
    zbiorcze, _order_a, _order_b = _paczka_z_wycena_mieszana(db, make_user, make_order)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}',
                   json={'payment_deadline': 'jutro'})

    assert r.status_code == 400
    blad = r.get_json()['error']
    assert zbiorcze.request_number in blad
    assert 'termin płatności' in blad


def test_nieoczekiwany_blad_zapisu_daje_identyfikator_do_logu(
        db, client, login, make_user, make_order, monkeypatch, caplog):
    """Awaria nieprzewidziana ma dać komunikat z numerem zlecenia i identyfikatorem
    błędu — tym samym, który poszedł do logu obok tracebacka. Bez tego zgłoszenie
    „nie zapisało się" trzeba było szukać w logach po godzinie."""
    import re
    zbiorcze, order_a, _order_b = _paczka_z_wycena_mieszana(db, make_user, make_order)
    login(_admin(make_user))

    def wybuchnij(_sr):
        raise RuntimeError('symulacja awarii bazy')

    monkeypatch.setattr('modules.orders.consolidation.propaguj_na_zrodla', wybuchnij)

    with caplog.at_level('ERROR'):
        r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}', json={
            'order_costs': [{'order_id': order_a.id, 'shipping_cost': 12}],
        })

    assert r.status_code == 500
    blad = r.get_json()['error']
    assert zbiorcze.request_number in blad
    assert 'Identyfikator błędu' in blad
    assert 'Traceback' not in blad and 'RuntimeError' not in blad   # bez wnętrzności serwera

    identyfikator = re.search(r'Identyfikator błędu: (\w+)', blad).group(1)
    assert identyfikator in caplog.text          # ten sam ciąg w logu…
    assert 'symulacja awarii bazy' in caplog.text  # …obok tracebacka


def test_get_zlecenia_mowi_czy_to_paczka_zbiorcza(db, client, login, make_user, make_order):
    """Modal nazywa przycisk destrukcyjny wg tej flagi („Rozwiąż paczkę" vs „Usuń zlecenie")."""
    zbiorcze, _order_a, _order_b = _paczka_z_wycena_mieszana(db, make_user, make_order)
    zrodlo = zbiorcze.consolidated_sources[0]
    login(_admin(make_user))

    dane = client.get(f'/admin/orders/shipping-requests/{zbiorcze.id}').get_json()
    assert dane['is_consolidation'] is True
    assert dane['is_consolidated_source'] is False

    dane_zrodla = client.get(f'/admin/orders/shipping-requests/{zrodlo.id}').get_json()
    assert dane_zrodla['is_consolidation'] is False
    assert dane_zrodla['is_consolidated_source'] is True


# ---------- Stan rozliczeń uczestników na karcie i w modalu ----------

def test_karta_pokazuje_status_kazdego_uczestnika(db, client, login, make_user, make_order):
    """Pigułka na nagłówku karty niesie status NAJMNIEJ zaawansowany ze scalanych, więc
    przy mieszanych rozliczeniach mówiła „Czeka na wycenę" nad zleceniem, które było
    już opłacone. Nagłówek grupy uczestnika dokłada status JEGO zlecenia."""
    from test_shipping_consolidation import _ustaw_statusy
    from modules.orders.models import ShippingRequestStatus
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    _ustaw_statusy(db, zbiorcze, {sr_a: 'oplacone', sr_b: 'czeka_na_wycene'})
    login(_admin(make_user))

    tresc = client.get('/admin/orders/wms').get_data(as_text=True)
    assert 'sr-group-status' in tresc
    # Kropka bierze kolor ZLECENIA UCZESTNIKA — zielony opłaconego musi być na karcie
    # obok bursztynu paczki, inaczej renderowalibyśmy status zbiorczego dwa razy.
    kolory = {s.slug: s.badge_color for s in ShippingRequestStatus.query.all()}
    assert f'background-color: {kolory["oplacone"]};' in tresc
    assert f'background-color: {kolory["czeka_na_wycene"]};' in tresc


def test_karta_mowi_co_blokuje_paczke(db, client, login, make_user, make_order):
    from test_shipping_consolidation import _ustaw_statusy
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    _ustaw_statusy(db, zbiorcze, {sr_a: 'oplacone', sr_b: 'czeka_na_oplacenie'})
    login(_admin(make_user))

    tresc = client.get('/admin/orders/wms').get_data(as_text=True)
    assert 'sr-block-note' in tresc
    assert f'Czeka na opłacenie: {sr_b.short_addressee_name}' in tresc


def test_karta_paczki_rozliczonej_bez_zdania(db, client, login, make_user, make_order):
    """Wszyscy uczestnicy opłaceni — nie ma czego tłumaczyć, zdanie znika."""
    _seed_sr_statuses(db)
    _konsolidacja(db, make_user, make_order)   # oba źródła 'oplacone'
    login(_admin(make_user))

    tresc = client.get('/admin/orders/wms').get_data(as_text=True)
    assert 'sr-group-status' in tresc          # statusy uczestników zostają…
    assert 'sr-block-note' not in tresc        # …ale bez ostrzeżenia bez treści


def test_zwykle_zlecenie_renderuje_sie_bez_zmian(db, client, login, make_user, make_order):
    """Karta zlecenia jednego klienta nie dostaje ani statusów uczestników, ani zdania
    o blokadzie — cała gałąź jest pod `sr.is_consolidation`."""
    _seed_sr_statuses(db)
    _sr(db, make_user(first_name='Anna', last_name='Kowalska'), make_order,
        status='czeka_na_wycene')
    login(_admin(make_user))

    tresc = client.get('/admin/orders/wms').get_data(as_text=True)
    assert 'sr-order-group' not in tresc
    assert 'sr-group-status' not in tresc
    assert 'sr-block-note' not in tresc


def test_get_zlecenia_oddaje_powod_blokady_dla_modalu(db, client, login, make_user, make_order):
    """Modal wyceny renderuje płaską listę numerów zamówień, bez podziału na ludzi —
    bez tego pola admin nie wie, czyje pole kosztu zostawia puste."""
    from test_shipping_consolidation import _ustaw_statusy
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    _ustaw_statusy(db, zbiorcze, {sr_a: 'oplacone', sr_b: 'czeka_na_wycene'})
    login(_admin(make_user))

    dane = client.get(f'/admin/orders/shipping-requests/{zbiorcze.id}').get_json()
    assert dane['consolidation_block_note'] == f'Czeka na wycenę: {sr_b.short_addressee_name}'

    # Zwykłe zlecenie: pole obecne, ale puste — modal nie musi zgadywać, czy je pominąć.
    sr_c, _o = _sr(db, make_user(), make_order, status='czeka_na_wycene')
    zwykle = client.get(f'/admin/orders/shipping-requests/{sr_c.id}').get_json()
    assert zwykle['consolidation_block_note'] is None


def test_zdanie_nie_chowa_sie_razem_z_zamowieniami(db, client, login, make_user, make_order):
    """Pułapka karty: limit „3 widoczne" liczy się łącznie przez wszystkie grupy, a
    `toggleExtraOrders` chowa WSZYSTKO z klasą `sr-order-extra` wewnątrz
    `.sr-orders-compact`. Zdanie o blokadzie dotyczy całej paczki, więc nie może tej
    klasy dostać ani wylądować wewnątrz grupy uczestnika."""
    import re
    from test_shipping_consolidation import _ustaw_statusy
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order, orders_count=3)
    _ustaw_statusy(db, zbiorcze, {sr_a: 'oplacone', sr_b: 'czeka_na_wycene'})
    login(_admin(make_user))

    tresc = client.get('/admin/orders/wms').get_data(as_text=True)
    assert 'Pokaż więcej (3)' in tresc          # 6 zamówień, 3 widoczne
    zdanie = re.search(r'<div class="sr-block-note">', tresc)
    assert zdanie, 'zdanie renderuje się z gołą klasą, bez sr-order-extra'
    # …i za przyciskiem rozwijania, czyli poza grupami uczestników.
    assert tresc.index('Pokaż więcej (3)') < zdanie.start()


# ---------------------------------------------------------------------------
# Powiadomienie o wycenie idzie do wycenionego uczestnika (BUG 3.3)
# ---------------------------------------------------------------------------

@pytest.fixture
def zebrane_statusy(monkeypatch):
    """Zbiera (numer_zlecenia, stary_status) z powiadomień o zmianie statusu."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    zebrane = []
    monkeypatch.setattr(
        EmailManager, 'notify_shipping_status_change',
        staticmethod(lambda sr, old: zebrane.append((sr.request_number, old))))
    monkeypatch.setattr(
        PushManager, 'notify_shipping_status_change',
        staticmethod(lambda sr, name: None))
    return zebrane


def test_wycena_uczestnika_powiadamia_jego_a_nie_cala_paczke(
        db, client, login, make_user, make_order, bez_powiadomien_o_koszcie, zebrane_statusy):
    """Uczestnik z „opłacone" nie może dostać maila o cudzym „czeka na opłacenie".

    Status paczki to minimum ze źródeł, więc powiadomienie wysłane na paczce
    rozeszłoby jej przejście do wszystkich uczestników.
    """
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_a.status = 'oplacone'
    sr_b.status = 'czeka_na_wycene'
    db.session.commit()
    login(_admin(make_user))

    zamowienie_b = sr_b.display_orders[0]
    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}', json={
        'order_costs': [{'order_id': zamowienie_b.id, 'shipping_cost': 15}],
    })

    assert r.status_code == 200, r.get_json()
    assert zebrane_statusy == [(sr_b.request_number, 'czeka_na_wycene')], (
        f'Powiadomienie ma iść do wycenionego uczestnika z JEGO przejściem; '
        f'zebrano: {zebrane_statusy}'
    )


def test_wycena_powiadamia_nawet_gdy_minimum_paczki_bez_zmian(
        db, client, login, make_user, make_order, bez_powiadomien_o_koszcie, zebrane_statusy):
    """Przypadek lustrzany: gdy status paczki się nie rusza, uczestnik i tak musi
    dostać informację o naliczonej należności.

    Wcześniej powiadomienie zależało od zmiany statusu PACZKI — a ta jest
    minimum ze źródeł, więc podniesienie jednego uczestnika przy innym stojącym
    niżej nie ruszało minimum i nie szło nic do nikogo.
    """
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    # sr_a zostaje na „czeka na wycenę" i trzyma minimum paczki w miejscu.
    # Status paczki musi być spójny z uczestnikami już na starcie — inaczej
    # zmieni się przez samo przeliczenie minimum, a nie przez wycenę.
    sr_a.status = 'czeka_na_wycene'
    sr_b.status = 'czeka_na_wycene'
    zbiorcze.status = 'czeka_na_wycene'
    db.session.commit()
    status_paczki_przed = zbiorcze.status

    login(_admin(make_user))
    zamowienie_b = sr_b.display_orders[0]
    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}', json={
        'order_costs': [{'order_id': zamowienie_b.id, 'shipping_cost': 15}],
    })

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert zbiorcze.status == status_paczki_przed, (
        'Założenie testu: minimum paczki trzyma nadal sr_a'
    )
    assert zebrane_statusy == [(sr_b.request_number, 'czeka_na_wycene')], (
        f'Wyceniony uczestnik musi dostać powiadomienie mimo braku ruchu na '
        f'paczce; zebrano: {zebrane_statusy}'
    )
