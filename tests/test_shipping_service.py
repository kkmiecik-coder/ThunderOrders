"""Testy serwisu wysyłki (ekstrakcja z webowych tras shipping.py — parytet)."""
from decimal import Decimal


def _home(**over):
    d = {'address_type': 'home', 'shipping_name': 'Jan Kowalski',
         'shipping_address': 'Główna 1', 'shipping_postal_code': '00-001',
         'shipping_city': 'Warszawa'}
    d.update(over)
    return d


def _pickup(**over):
    d = {'address_type': 'pickup_point', 'pickup_courier': 'InPost',
         'pickup_point_id': 'WAW001', 'pickup_address': 'Kwiatowa 2',
         'pickup_postal_code': '00-002', 'pickup_city': 'Warszawa'}
    d.update(over)
    return d


def test_validate_ok_home_and_pickup(db):
    from modules.client.shipping_service import validate_address_payload
    assert validate_address_payload(_home()) == (True, None)
    assert validate_address_payload(_pickup()) == (True, None)


def test_validate_bad_type(db):
    from modules.client.shipping_service import validate_address_payload
    ok, err = validate_address_payload({'address_type': 'office'})
    assert not ok and err['code'] == 'invalid_address_type'


def test_validate_missing_home_field(db):
    from modules.client.shipping_service import validate_address_payload
    ok, err = validate_address_payload(_home(shipping_city=''))
    assert not ok and err['code'] == 'missing_field' and err['field'] == 'shipping_city'


def test_validate_missing_pickup_field(db):
    from modules.client.shipping_service import validate_address_payload
    ok, err = validate_address_payload(_pickup(pickup_point_id=None))
    assert not ok and err['code'] == 'missing_field' and err['field'] == 'pickup_point_id'


def test_create_address_defaults_country_and_flushes_default(db, make_user):
    from modules.client.shipping_service import create_address
    from modules.auth.models import ShippingAddress
    u = make_user()
    a1 = create_address(u, _home(is_default=True))[2]
    a2 = create_address(u, _home(shipping_city='Kraków', is_default=True))[2]
    db.session.refresh(a1)
    assert a2.is_default is True and a1.is_default is False     # clearing innych
    assert a2.shipping_country == 'Polska'                      # default kraju


def test_set_default_clears_others_and_owns(db, make_user):
    from modules.client.shipping_service import create_address, set_default_address
    u, other = make_user(), make_user()
    a1 = create_address(u, _home(is_default=True))[2]
    a2 = create_address(u, _home(shipping_city='Gdańsk'))[2]
    ok, err, addr = set_default_address(u.id, a2.id)
    db.session.refresh(a1)
    assert ok and addr.id == a2.id and a2.is_default and not a1.is_default
    # cudzy adres → not_found (maskowanie)
    ok2, err2, _ = set_default_address(other.id, a1.id)
    assert not ok2 and err2['code'] == 'not_found'


def test_soft_delete_marks_inactive_and_owns(db, make_user):
    from modules.client.shipping_service import create_address, soft_delete_address
    u, other = make_user(), make_user()
    a = create_address(u, _home())[2]
    ok, err = soft_delete_address(other.id, a.id)               # cudzy
    assert not ok and err['code'] == 'not_found'
    ok2, _ = soft_delete_address(u.id, a.id)
    db.session.refresh(a)
    assert ok2 and a.is_active is False
    # ponowny soft-delete nieaktywnego → not_found (filtr is_active)
    ok3, err3 = soft_delete_address(u.id, a.id)
    assert not ok3 and err3['code'] == 'not_found'


def test_list_active_sorted_default_first(db, make_user):
    from modules.client.shipping_service import create_address, list_active_addresses, soft_delete_address
    u = make_user()
    a1 = create_address(u, _home())[2]
    a2 = create_address(u, _home(shipping_city='Łódź', is_default=True))[2]
    dead = create_address(u, _home(shipping_city='Poznań'))[2]
    soft_delete_address(u.id, dead.id)
    out = list_active_addresses(u.id)
    assert [a.id for a in out] == [a2.id, a1.id]                # default first, dead pominięty


def test_web_address_add_route_parity_smoke(client, db, make_user, login):
    u = make_user(profile_completed=True); login(u)
    r = client.post('/client/shipping/addresses/add', json=_home(),
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert 'address_id' in r.get_json()


def test_web_address_add_missing_field_parity(client, db, make_user, login):
    u = make_user(profile_completed=True); login(u)
    r = client.post('/client/shipping/addresses/add', json=_home(shipping_city=''),
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400 and 'shipping_city' in r.get_json()['message']  # web message BEZ zmian


def test_web_address_set_default_and_delete_parity(client, db, make_user, login):
    from modules.client.shipping_service import create_address
    u = make_user(profile_completed=True); login(u)
    a = create_address(u, _home())[2]
    assert client.post(f'/client/shipping/addresses/{a.id}/set-default',
                       headers={'X-Requested-With': 'XMLHttpRequest'}).status_code == 200
    assert client.post(f'/client/shipping/addresses/{a.id}/delete',
                       headers={'X-Requested-With': 'XMLHttpRequest'}).status_code == 200
