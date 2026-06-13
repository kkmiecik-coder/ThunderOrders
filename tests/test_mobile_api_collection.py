"""Testy E8: mobilne API kolekcji (items CRUD + zdjęcia + publiczna strona).

_auth jak w orders/payments. Multipart: BytesIO + content_type (wzorzec E6).
"""
import io
import os
import shutil
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _cleanup_collections(app):
    base = os.path.join(app.root_path, 'static', 'uploads', 'collections')
    before = set(os.listdir(base)) if os.path.isdir(base) else set()
    yield
    if os.path.isdir(base):
        for d in set(os.listdir(base)) - before:
            shutil.rmtree(os.path.join(base, d), ignore_errors=True)


def _auth(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': u.email, 'password': 'Haslo123!'})
    return {'Authorization': f'Bearer {r.get_json()["data"]["access_token"]}'}, u


def _tiny_png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (1, 1), (255, 0, 0)).save(buf, 'PNG')
    buf.seek(0)
    return buf


def _make_item(db, user, name='Photocard', price=None, **kw):
    from modules.client.models import CollectionItem
    item = CollectionItem(user_id=user.id, name=name, market_price=price, **kw)
    db.session.add(item); db.session.commit()
    return item


# === Task 2: items CRUD ===

def test_items_requires_jwt(client, db):
    assert client.get('/api/mobile/v1/collection/items').status_code == 401


def test_items_list_pagination_grosze_and_isolation(client, db, make_user):
    h, u = _auth(client, db, make_user)
    other = make_user()
    _make_item(db, u, name='A', price=Decimal('129.99'))
    _make_item(db, u, name='B')
    _make_item(db, other, name='Cudzy')
    r = client.get('/api/mobile/v1/collection/items?per_page=1', headers=h)
    assert r.status_code == 200
    body = r.get_json()
    assert body['pagination'] == {'page': 1, 'per_page': 1, 'total': 2, 'has_next': True}
    row = body['data'][0]
    assert set(row) >= {'id', 'name', 'market_price', 'source', 'is_public',
                        'images_count', 'image_url', 'created_at'}
    assert row['image_url'].startswith('http')                # absolutny (placeholder)


def test_items_list_q_and_sort(client, db, make_user):
    h, u = _auth(client, db, make_user)
    a = _make_item(db, u, name='Album BP', price=Decimal('50'))
    _make_item(db, u, name='Photocard')
    c = _make_item(db, u, name='Album TXT', price=Decimal('80'))
    data = client.get('/api/mobile/v1/collection/items?q=album&sort=price_desc',
                      headers=h).get_json()['data']
    assert [r['id'] for r in data] == [c.id, a.id]
    assert data[0]['market_price'] == 8000                    # grosze


def test_items_list_bad_sort_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.get('/api/mobile/v1/collection/items?sort=cheapest', headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_item_detail_shape(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item = _make_item(db, u, price=Decimal('12.34'), notes='notka')
    r = client.get(f'/api/mobile/v1/collection/items/{item.id}', headers=h)
    assert r.status_code == 200
    d = r.get_json()['data']
    assert d['market_price'] == 1234 and d['notes'] == 'notka'
    assert d['can_add_image'] is True and d['images'] == []


def test_item_detail_foreign_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    other = make_user()
    item = _make_item(db, other)
    r = client.get(f'/api/mobile/v1/collection/items/{item.id}', headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'item_not_found'


def test_create_item_multipart_with_images(client, db, make_user, app):
    h, u = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/collection/items',
                    data={'name': 'PC Jisoo', 'market_price': '12999', 'notes': 'rzadka',
                          'images': [(_tiny_png(), 'a.png'), (_tiny_png(), 'b.png')]},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 201
    d = r.get_json()['data']
    assert d['market_price'] == 12999 and d['images_count'] == 2
    assert d['images'][0]['is_primary'] is True
    assert d['images'][0]['url'].startswith('http')
    # plik fizycznie na dysku
    from modules.client.models import CollectionItemImage
    img = CollectionItemImage.query.first()
    assert os.path.exists(os.path.join(app.root_path, 'static', img.path_compressed))


def test_create_item_missing_name_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/collection/items', data={'name': ''},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['details']['field'] == 'name'


def test_create_item_too_many_images_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    files = [(_tiny_png(), f'{i}.png') for i in range(4)]
    r = client.post('/api/mobile/v1/collection/items',
                    data={'name': 'PC', 'images': files},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['details']['max_images'] == 3


def test_create_item_invalid_file_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/collection/items',
                    data={'name': 'PC', 'images': [(io.BytesIO(b'nope'), 'x.txt')]},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_file'


def test_create_item_bad_price_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/collection/items',
                    data={'name': 'PC', 'market_price': 'abc'},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_create_item_idempotency_replay(client, db, make_user):
    from modules.client.models import CollectionItem
    h, u = _auth(client, db, make_user)
    hk = dict(h); hk['Idempotency-Key'] = 'e8-key-1'
    r1 = client.post('/api/mobile/v1/collection/items',
                     data={'name': 'PC', 'images': [(_tiny_png(), 'a.png')]},
                     content_type='multipart/form-data', headers=hk)
    r2 = client.post('/api/mobile/v1/collection/items',
                     data={'name': 'PC', 'images': [(_tiny_png(), 'a.png')]},
                     content_type='multipart/form-data', headers=hk)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.get_json() == r2.get_json()
    assert CollectionItem.query.filter_by(user_id=u.id).count() == 1   # bez duplikatu


def test_patch_item_partial(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item = _make_item(db, u, name='Stara', price=Decimal('10.00'), notes='n')
    r = client.patch(f'/api/mobile/v1/collection/items/{item.id}',
                     data={'name': 'Nowa', 'market_price': ''},
                     content_type='multipart/form-data', headers=h)
    assert r.status_code == 200
    d = r.get_json()['data']
    assert d['name'] == 'Nowa' and d['market_price'] is None and d['notes'] == 'n'


def test_patch_item_foreign_404_and_empty_400(client, db, make_user):
    h, u = _auth(client, db, make_user)
    other = make_user()
    foreign = _make_item(db, other)
    r = client.patch(f'/api/mobile/v1/collection/items/{foreign.id}',
                     data={'name': 'X'}, content_type='multipart/form-data', headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'item_not_found'
    mine = _make_item(db, u)
    r2 = client.patch(f'/api/mobile/v1/collection/items/{mine.id}', data={},
                      content_type='multipart/form-data', headers=h)
    assert r2.status_code == 400


def test_delete_item(client, db, make_user):
    from modules.client.models import CollectionItem
    h, u = _auth(client, db, make_user)
    item = _make_item(db, u)
    r = client.delete(f'/api/mobile/v1/collection/items/{item.id}', headers=h)
    assert r.status_code == 200 and r.get_json()['data']['deleted'] is True
    assert CollectionItem.query.get(item.id) is None
    # powtórka / cudzy → 404
    assert client.delete(f'/api/mobile/v1/collection/items/{item.id}',
                         headers=h).status_code == 404


# === Task 4: zdjęcia ===

def _make_item_with_images(db, user, n=1):
    from modules.client.collection_service import create_item, add_image
    _, _, item = create_item(user, 'PC')
    imgs = []
    for i in range(n):
        from werkzeug.datastructures import FileStorage
        from PIL import Image
        buf = io.BytesIO(); Image.new('RGB', (1, 1)).save(buf, 'PNG'); buf.seek(0)
        _, _, img = add_image(user, item.id,
                              FileStorage(stream=buf, filename=f'{i}.png'))
        imgs.append(img)
    return item, imgs


def test_add_image_201_first_primary(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item, _ = _make_item_with_images(db, u, n=0)
    r = client.post(f'/api/mobile/v1/collection/items/{item.id}/images',
                    data={'image': (_tiny_png(), 'a.png')},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 201
    img = r.get_json()['data']['image']
    assert img['is_primary'] is True and img['url'].startswith('http')


def test_add_image_max_3_409(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item, _ = _make_item_with_images(db, u, n=3)
    r = client.post(f'/api/mobile/v1/collection/items/{item.id}/images',
                    data={'image': (_tiny_png(), 'd.png')},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 409 and r.get_json()['error']['code'] == 'max_images'


def test_add_image_no_file_400_and_foreign_404(client, db, make_user):
    h, u = _auth(client, db, make_user)
    other = make_user()
    item, _ = _make_item_with_images(db, u, n=0)
    r = client.post(f'/api/mobile/v1/collection/items/{item.id}/images',
                    data={}, content_type='multipart/form-data', headers=h)
    assert r.status_code == 400
    foreign_item = _make_item(db, other)
    r2 = client.post(f'/api/mobile/v1/collection/items/{foreign_item.id}/images',
                     data={'image': (_tiny_png(), 'a.png')},
                     content_type='multipart/form-data', headers=h)
    assert r2.status_code == 404 and r2.get_json()['error']['code'] == 'item_not_found'


def test_add_image_invalid_file_400(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item, _ = _make_item_with_images(db, u, n=0)
    r = client.post(f'/api/mobile/v1/collection/items/{item.id}/images',
                    data={'image': (io.BytesIO(b'x'), 'x.txt')},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_file'


def test_delete_image_reassigns_primary(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item, imgs = _make_item_with_images(db, u, n=2)
    r = client.delete(
        f'/api/mobile/v1/collection/items/{item.id}/images/{imgs[0].id}', headers=h)
    assert r.status_code == 200 and r.get_json()['data']['deleted'] is True
    d = client.get(f'/api/mobile/v1/collection/items/{item.id}',
                   headers=h).get_json()['data']
    assert len(d['images']) == 1 and d['images'][0]['is_primary'] is True


def test_delete_image_mismatch_404(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item_a, imgs = _make_item_with_images(db, u, n=1)
    item_b, _ = _make_item_with_images(db, u, n=0)
    r = client.delete(
        f'/api/mobile/v1/collection/items/{item_b.id}/images/{imgs[0].id}', headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'image_not_found'


def test_set_primary_image_patch(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item, imgs = _make_item_with_images(db, u, n=2)
    r = client.patch(
        f'/api/mobile/v1/collection/items/{item.id}/images/{imgs[1].id}/primary',
        headers=h)
    assert r.status_code == 200 and r.get_json()['data']['image']['is_primary'] is True
    d = client.get(f'/api/mobile/v1/collection/items/{item.id}',
                   headers=h).get_json()['data']
    flags = {i['id']: i['is_primary'] for i in d['images']}
    assert flags[imgs[1].id] is True and flags[imgs[0].id] is False


def test_set_primary_foreign_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    h2, u2 = _auth(client, db, make_user)
    item, imgs = _make_item_with_images(db, u2, n=1)
    r = client.patch(
        f'/api/mobile/v1/collection/items/{item.id}/images/{imgs[0].id}/primary',
        headers=h)
    assert r.status_code == 404


# === Task 5: publiczna strona ===

def test_public_config_get_not_exists(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.get('/api/mobile/v1/collection/public/config', headers=h)
    assert r.status_code == 200
    assert r.get_json()['data'] == {'exists': False, 'config': None}


def test_public_config_post_upsert_creates_then_updates(client, db, make_user):
    h, u = _auth(client, db, make_user)
    r1 = client.post('/api/mobile/v1/collection/public/config',
                     json={'show_prices': False}, headers=h)
    assert r1.status_code == 201
    d1 = r1.get_json()['data']
    assert d1['created'] is True and d1['config']['show_prices'] is False
    assert d1['config']['is_active'] is True
    assert d1['config']['public_url'].startswith('http')
    assert d1['config']['public_url'].endswith('/collection/' + d1['config']['token'])
    r2 = client.post('/api/mobile/v1/collection/public/config',
                     json={'is_active': False}, headers=h)
    assert r2.status_code == 200
    d2 = r2.get_json()['data']
    assert d2['created'] is False and d2['config']['is_active'] is False
    assert d2['config']['token'] == d1['config']['token']     # ten sam config
    g = client.get('/api/mobile/v1/collection/public/config', headers=h).get_json()['data']
    assert g['exists'] is True and g['config']['is_active'] is False


def test_toggle_public_flips_and_masks(client, db, make_user):
    h, u = _auth(client, db, make_user)
    other = make_user()
    item = _make_item(db, u)
    r = client.post(f'/api/mobile/v1/collection/items/{item.id}/toggle-public', headers=h)
    assert r.status_code == 200 and r.get_json()['data']['is_public'] is False
    r2 = client.post(f'/api/mobile/v1/collection/items/{item.id}/toggle-public', headers=h)
    assert r2.get_json()['data']['is_public'] is True
    foreign = _make_item(db, other)
    r3 = client.post(f'/api/mobile/v1/collection/items/{foreign.id}/toggle-public', headers=h)
    assert r3.status_code == 404 and r3.get_json()['error']['code'] == 'item_not_found'


def test_mobile_config_visible_on_public_web_page(client, db, make_user):
    """E2E: konfiguracja przez mobile → publiczna strona webowa odzwierciedla stan."""
    h, u = _auth(client, db, make_user)
    _make_item(db, u, name='Mobilny item')
    token = client.post('/api/mobile/v1/collection/public/config', json={},
                        headers=h).get_json()['data']['config']['token']
    r = client.get(f'/collection/{token}')                    # BEZ auth
    assert r.status_code == 200 and 'Mobilny item' in r.get_data(as_text=True)
