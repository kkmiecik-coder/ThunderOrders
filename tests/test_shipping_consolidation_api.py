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
