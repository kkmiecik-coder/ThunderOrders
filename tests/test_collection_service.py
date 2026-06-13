"""Testy serwisu kolekcji (ekstrakcja z webowych tras collection.py — parytet)."""
import io
import os
import shutil
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _cleanup_collections(app):
    """Sprząta pliki zdjęć kolekcji utworzone w teście (per-user podkatalogi)."""
    base = os.path.join(app.root_path, 'static', 'uploads', 'collections')
    before = set(os.listdir(base)) if os.path.isdir(base) else set()
    yield
    if os.path.isdir(base):
        for d in set(os.listdir(base)) - before:
            shutil.rmtree(os.path.join(base, d), ignore_errors=True)


def _png_storage(name='a.png'):
    from PIL import Image
    from werkzeug.datastructures import FileStorage
    buf = io.BytesIO()
    Image.new('RGB', (1, 1), (255, 0, 0)).save(buf, 'PNG')
    buf.seek(0)
    return FileStorage(stream=buf, filename=name, content_type='image/png')


def _make_item(db, user, name='Photocard', price=None, **kw):
    from modules.client.models import CollectionItem
    item = CollectionItem(user_id=user.id, name=name, market_price=price, **kw)
    db.session.add(item); db.session.commit()
    return item


def test_create_item_minimal(db, make_user):
    from modules.client.collection_service import create_item
    u = make_user()
    ok, err, item = create_item(u, 'PC Jisoo')
    assert ok and item.id and item.source == 'manual'
    assert item.market_price is None and item.notes is None and item.is_public is True


def test_create_item_with_files_saves_and_marks_primary(db, make_user, app):
    from modules.client.collection_service import create_item
    u = make_user()
    ok, err, item = create_item(u, 'PC', market_price=Decimal('129.99'),
                                files=[_png_storage('a.png'), _png_storage('b.png')])
    assert ok and item.images_count == 2
    assert item.images[0].is_primary is True and item.images[1].is_primary is False
    assert item.images[0].sort_order == 0 and item.images[1].sort_order == 1
    for img in item.images:                                   # pliki fizycznie na dysku
        assert os.path.exists(os.path.join(app.root_path, 'static', img.path_original))
        assert os.path.exists(os.path.join(app.root_path, 'static', img.path_compressed))


def test_create_item_invalid_file_rolls_back(db, make_user):
    from modules.client.collection_service import create_item
    from modules.client.models import CollectionItem
    from werkzeug.datastructures import FileStorage
    u = make_user()
    bad = FileStorage(stream=io.BytesIO(b'not an image'), filename='evil.txt')
    ok, err, _ = create_item(u, 'PC', files=[bad])
    assert not ok and err['code'] == 'invalid_file'
    assert CollectionItem.query.filter_by(user_id=u.id).count() == 0   # all-or-nothing


def test_get_owned_item_masks_foreign(db, make_user):
    from modules.client.collection_service import get_owned_item
    u, other = make_user(), make_user()
    item = _make_item(db, other)
    assert get_owned_item(u.id, item.id) is None
    assert get_owned_item(other.id, item.id).id == item.id


def test_list_items_search_and_sorts(db, make_user):
    from modules.client.collection_service import list_items
    u = make_user()
    a = _make_item(db, u, name='Album BP', price=Decimal('50'))
    b = _make_item(db, u, name='Photocard', price=None)
    c = _make_item(db, u, name='Album TXT', price=Decimal('80'))
    assert [i.id for i in list_items(u.id).items] == [c.id, b.id, a.id]       # newest
    assert [i.id for i in list_items(u.id, sort='oldest').items] == [a.id, b.id, c.id]
    assert [i.id for i in list_items(u.id, sort='name_asc').items] == [a.id, c.id, b.id]
    assert [i.id for i in list_items(u.id, sort='price_desc').items] == [c.id, a.id, b.id]  # NULL last
    assert [i.id for i in list_items(u.id, search='album').items] == [c.id, a.id]


def test_list_items_paginates_and_isolates_users(db, make_user):
    from modules.client.collection_service import list_items
    u, other = make_user(), make_user()
    for i in range(3):
        _make_item(db, u, name=f'I{i}')
    _make_item(db, other, name='Cudzy')
    page = list_items(u.id, page=1, per_page=2)
    assert page.total == 3 and len(page.items) == 2 and page.has_next is True


def test_update_item_partial_and_clears(db, make_user):
    from modules.client.collection_service import update_item
    u = make_user()
    item = _make_item(db, u, price=Decimal('10'), notes='stare')
    ok, err, it = update_item(u.id, item.id, {'name': 'Nowa', 'market_price': None})
    assert ok and it.name == 'Nowa' and it.market_price is None and it.notes == 'stare'
    ok2, err2, _ = update_item(u.id, item.id, {'name': ''})
    assert not ok2 and err2['code'] == 'name_required'


def test_update_item_foreign_not_found(db, make_user):
    from modules.client.collection_service import update_item
    u, other = make_user(), make_user()
    item = _make_item(db, other)
    ok, err, _ = update_item(u.id, item.id, {'name': 'X'})
    assert not ok and err['code'] == 'not_found'


def test_delete_item_removes_files_and_row(db, make_user, app):
    from modules.client.collection_service import create_item, delete_item
    from modules.client.models import CollectionItem, CollectionItemImage
    u = make_user()
    _, _, item = create_item(u, 'PC', files=[_png_storage()])
    paths = [(i.path_original, i.path_compressed) for i in item.images]
    ok, _ = delete_item(u.id, item.id)
    assert ok and CollectionItem.query.get(item.id) is None
    assert CollectionItemImage.query.count() == 0             # cascade
    for orig, compr in paths:
        assert not os.path.exists(os.path.join(app.root_path, 'static', orig))
        assert not os.path.exists(os.path.join(app.root_path, 'static', compr))


def test_delete_item_foreign_not_found(db, make_user):
    from modules.client.collection_service import delete_item
    u, other = make_user(), make_user()
    item = _make_item(db, other)
    ok, err = delete_item(u.id, item.id)
    assert not ok and err['code'] == 'not_found'


# === Smoke webowych tras itemów (fixtura login, profile_completed=True — bramka klienta) ===

def test_web_collection_add_parity_smoke(client, db, make_user, login):
    u = make_user(profile_completed=True); login(u)
    r = client.post('/client/collection/add', data={'name': 'PC', 'market_price': '12.50'},
                    content_type='multipart/form-data')
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert 'item_id' in r.get_json()


def test_web_collection_add_missing_name_parity(client, db, make_user, login):
    u = make_user(profile_completed=True); login(u)
    r = client.post('/client/collection/add', data={'name': ''},
                    content_type='multipart/form-data')
    assert r.status_code == 400 and 'Nazwa' in r.get_json()['message']


def test_web_collection_edit_and_delete_parity(client, db, make_user, login):
    u = make_user(profile_completed=True); login(u)
    item = _make_item(db, u)
    r = client.post(f'/client/collection/{item.id}/edit',
                    data={'name': 'Po edycji', 'market_price': '', 'notes': ''},
                    content_type='multipart/form-data')
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert client.delete(f'/client/collection/{item.id}/delete').status_code == 200


def test_web_collection_foreign_403_parity(client, db, make_user, login):
    u, other = make_user(profile_completed=True), make_user()
    login(u)
    item = _make_item(db, other)
    r = client.post(f'/client/collection/{item.id}/edit', data={'name': 'X'},
                    content_type='multipart/form-data')
    assert r.status_code == 403                               # web: 403 (mobile zamaskuje 404)


# === Task 3: zdjęcia (serwis) ===

def test_add_image_marks_first_primary_and_limits_to_3(db, make_user):
    from modules.client.collection_service import create_item, add_image
    u = make_user()
    _, _, item = create_item(u, 'PC')
    ok, _, img1 = add_image(u, item.id, _png_storage('1.png'))
    assert ok and img1.is_primary is True and img1.sort_order == 0
    add_image(u, item.id, _png_storage('2.png'))
    ok3, _, img3 = add_image(u, item.id, _png_storage('3.png'))
    assert ok3 and img3.is_primary is False and img3.sort_order == 2
    ok4, err4, _ = add_image(u, item.id, _png_storage('4.png'))
    assert not ok4 and err4['code'] == 'max_images'           # limit 3 (can_add_image)


def test_add_image_validations(db, make_user):
    from modules.client.collection_service import create_item, add_image
    from werkzeug.datastructures import FileStorage
    u, other = make_user(), make_user()
    _, _, item = create_item(u, 'PC')
    assert add_image(other, item.id, _png_storage())[1]['code'] == 'not_found'   # cudzy
    assert add_image(u, item.id, None)[1]['code'] == 'no_file'
    bad = FileStorage(stream=io.BytesIO(b'x'), filename='x.txt')
    assert add_image(u, item.id, bad)[1]['code'] == 'invalid_file'


def test_delete_image_reassigns_primary_and_removes_files(db, make_user, app):
    from modules.client.collection_service import create_item, add_image, delete_image
    u = make_user()
    _, _, item = create_item(u, 'PC')
    _, _, img1 = add_image(u, item.id, _png_storage('1.png'))     # primary
    _, _, img2 = add_image(u, item.id, _png_storage('2.png'))
    paths = (img1.path_original, img1.path_compressed)
    ok, _ = delete_image(u.id, item.id, img1.id)
    assert ok
    db.session.refresh(img2)
    assert img2.is_primary is True                            # reassignment
    assert not os.path.exists(os.path.join(app.root_path, 'static', paths[0]))
    assert not os.path.exists(os.path.join(app.root_path, 'static', paths[1]))


def test_delete_image_mismatched_item_not_found(db, make_user):
    from modules.client.collection_service import create_item, add_image, delete_image
    u = make_user()
    _, _, item_a = create_item(u, 'A')
    _, _, item_b = create_item(u, 'B')
    _, _, img = add_image(u, item_a.id, _png_storage())
    ok, err = delete_image(u.id, item_b.id, img.id)           # zdjęcie z INNEGO itemu
    assert not ok and err['code'] == 'not_found'


def test_set_primary_image(db, make_user):
    from modules.client.collection_service import create_item, add_image, set_primary_image
    u, other = make_user(), make_user()
    _, _, item = create_item(u, 'PC')
    _, _, img1 = add_image(u, item.id, _png_storage('1.png'))
    _, _, img2 = add_image(u, item.id, _png_storage('2.png'))
    ok, _, img = set_primary_image(u.id, item.id, img2.id)
    db.session.refresh(img1)
    assert ok and img.is_primary is True and img1.is_primary is False
    assert set_primary_image(other.id, item.id, img2.id)[1]['code'] == 'not_found'


def _png_storage_raw():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (1, 1), (0, 255, 0)).save(buf, 'PNG')
    buf.seek(0)
    return buf


def test_web_image_add_delete_primary_parity(client, db, make_user, login):
    from modules.client.collection_service import create_item, add_image
    u = make_user(profile_completed=True); login(u)
    _, _, item = create_item(u, 'PC')
    r = client.post(f'/client/collection/{item.id}/images',
                    data={'image': (_png_storage_raw(), 'a.png')},
                    content_type='multipart/form-data')
    assert r.status_code == 200 and r.get_json()['image']['is_primary'] is True
    _, _, img2 = add_image(u, item.id, _png_storage('b.png'))
    assert client.post(
        f'/client/collection/{item.id}/images/{img2.id}/primary').status_code == 200
    assert client.delete(
        f'/client/collection/{item.id}/images/{img2.id}').status_code == 200


def test_web_image_add_over_limit_parity(client, db, make_user, login):
    from modules.client.collection_service import create_item, add_image
    u = make_user(profile_completed=True); login(u)
    _, _, item = create_item(u, 'PC')
    for i in range(3):
        add_image(u, item.id, _png_storage(f'{i}.png'))
    r = client.post(f'/client/collection/{item.id}/images',
                    data={'image': (_png_storage_raw(), 'x.png')},
                    content_type='multipart/form-data')
    assert r.status_code == 400 and 'Maksymalnie 3' in r.get_json()['message']  # web: 400
