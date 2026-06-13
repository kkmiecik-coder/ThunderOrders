"""Testy E7: mobilne API wysyłki (adresy CRUD + zlecenia). _auth jak w orders."""
import json
from decimal import Decimal


def _auth(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login', json={'email': u.email, 'password': 'Haslo123!'})
    return {'Authorization': f'Bearer {r.get_json()["data"]["access_token"]}'}, u


def _home(**over):
    d = {'address_type': 'home', 'shipping_name': 'Jan', 'shipping_address': 'Główna 1',
         'shipping_postal_code': '00-001', 'shipping_city': 'Warszawa'}
    d.update(over); return d


def test_addresses_requires_jwt(client, db, make_user):
    assert client.get('/api/mobile/v1/shipping/addresses').status_code == 401


def test_post_then_get_addresses(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/shipping/addresses', json=_home(is_default=True), headers=h)
    assert r.status_code == 201
    a = r.get_json()['data']['address']
    assert a['is_default'] is True and a['shipping_country'] == 'Polska'
    assert set(a) >= {'id', 'address_type', 'name', 'display_name', 'full_address', 'is_default',
                      'shipping_name', 'pickup_courier', 'created_at'}
    lst = client.get('/api/mobile/v1/shipping/addresses', headers=h).get_json()['data']['addresses']
    assert [x['id'] for x in lst] == [a['id']]


def test_post_address_bad_type(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/shipping/addresses', json={'address_type': 'office'}, headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_post_address_missing_field_details(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/shipping/addresses', json=_home(shipping_city=''), headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['details']['field'] == 'shipping_city'


def test_patch_default(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    a1 = client.post('/api/mobile/v1/shipping/addresses', json=_home(is_default=True),
                     headers=h).get_json()['data']['address']
    a2 = client.post('/api/mobile/v1/shipping/addresses', json=_home(shipping_city='Kraków'),
                     headers=h).get_json()['data']['address']
    r = client.patch(f'/api/mobile/v1/shipping/addresses/{a2["id"]}/default', headers=h)
    assert r.status_code == 200 and r.get_json()['data']['address']['is_default'] is True
    lst = client.get('/api/mobile/v1/shipping/addresses', headers=h).get_json()['data']['addresses']
    assert {x['id']: x['is_default'] for x in lst}[a1['id']] is False


def test_patch_default_foreign_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    h2, _ = _auth(client, db, make_user)
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h2
                    ).get_json()['data']['address']
    r = client.patch(f'/api/mobile/v1/shipping/addresses/{a["id"]}/default', headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'address_not_found'


def test_delete_soft(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h
                    ).get_json()['data']['address']
    assert client.delete(f'/api/mobile/v1/shipping/addresses/{a["id"]}', headers=h).status_code == 200
    assert client.get('/api/mobile/v1/shipping/addresses', headers=h
                      ).get_json()['data']['addresses'] == []
    # powtórny delete → 404
    assert client.delete(f'/api/mobile/v1/shipping/addresses/{a["id"]}', headers=h).status_code == 404
