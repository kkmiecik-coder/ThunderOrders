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
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.get('/admin/orders/wms')
    tresc = r.get_data(as_text=True)
    assert zbiorcze.request_number in tresc
    assert zrodla[0].request_number not in tresc


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
