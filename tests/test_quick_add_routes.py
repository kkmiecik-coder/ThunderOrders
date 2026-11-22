"""Testy tras szybkiego dodawania produktów on hand."""

import io
from decimal import Decimal

import pytest
from PIL import Image


@pytest.fixture
def on_hand_type(db):
    from modules.products.models import ProductType
    pt = ProductType(name='On-hand', slug='on-hand')
    db.session.add(pt)
    db.session.commit()
    return pt


@pytest.fixture
def upload_dir(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, 'UPLOAD_FOLDER', str(tmp_path))
    return tmp_path


def _jpeg_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (40, 30), (10, 120, 200)).save(buf, 'JPEG')
    buf.seek(0)
    return buf


def _post_create(client, **overrides):
    data = {'name': 'Album', 'sale_price': '49,99', 'quantity': ''}
    data.update(overrides)
    if 'images' not in overrides:
        data['images'] = [(_jpeg_bytes(), 'zdjecie-1.jpg')]
    return client.post('/admin/products/quick-add', data=data,
                       content_type='multipart/form-data')


@pytest.fixture
def as_admin(make_user, login):
    u = make_user(role='admin')
    login(u)
    return u


def test_client_role_gets_no_access(db, client, make_user, login, on_hand_type, upload_dir):
    from modules.products.models import Product
    login(make_user(role='client'))
    assert client.get('/admin/products/quick-add').status_code != 200
    assert _post_create(client).status_code != 200
    assert Product.query.count() == 0


def test_mod_can_open_page(db, client, make_user, login, on_hand_type):
    login(make_user(role='mod'))
    assert client.get('/admin/products/quick-add').status_code == 200


def test_create_returns_product_json(db, client, as_admin, on_hand_type, upload_dir):
    resp = _post_create(client)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['product']['name'] == 'Album'
    assert body['product']['sale_price'] == '49.99'
    assert body['product']['quantity'] == 1
    assert body['product']['thumb_url'].startswith('/static/uploads/products/')


def test_create_validation_error_is_400(db, client, as_admin, on_hand_type, upload_dir):
    from modules.products.models import Product
    resp = _post_create(client, images=[])
    assert resp.status_code == 400
    assert resp.get_json() == {'success': False, 'error': 'Dodaj co najmniej jedno zdjęcie'}
    assert Product.query.count() == 0


def test_update_and_hide_work_for_on_hand(db, client, as_admin, on_hand_type, upload_dir):
    from modules.products.models import Product
    pid = _post_create(client).get_json()['product']['id']

    resp = client.post(f'/admin/products/quick-add/{pid}/update',
                       json={'name': 'Album 2', 'sale_price': '59,50', 'quantity': '4'})
    assert resp.status_code == 200
    assert resp.get_json()['product']['sale_price'] == '59.50'

    resp = client.post(f'/admin/products/quick-add/{pid}/update',
                       json={'name': '', 'sale_price': '59', 'quantity': '4'})
    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'Podaj nazwę'

    resp = client.post(f'/admin/products/quick-add/{pid}/hide')
    assert resp.status_code == 200
    assert resp.get_json()['product']['is_active'] is False
    p = db.session.get(Product, pid)
    assert (p.name, p.sale_price, p.quantity, p.is_active) == ('Album 2', Decimal('59.50'), 4, False)


def test_update_and_hide_404_for_non_on_hand(db, client, as_admin, on_hand_type, make_product):
    other = make_product(name='Preorder', sale_price=Decimal('10.00'))
    assert client.post(f'/admin/products/quick-add/{other.id}/update',
                       json={'name': 'X', 'sale_price': '1', 'quantity': '1'}).status_code == 404
    assert client.post(f'/admin/products/quick-add/{other.id}/hide').status_code == 404
    assert client.post('/admin/products/quick-add/999999/hide').status_code == 404
    db.session.refresh(other)
    assert other.name == 'Preorder' and other.is_active is True


def test_quick_add_page_renders_form(db, client, as_admin, on_hand_type):
    html = client.get('/admin/products/quick-add').get_data(as_text=True)
    assert 'id="qa-photos"' in html
    assert 'accept="image/*"' in html
    assert 'capture' not in html.split('id="qa-photos"')[1].split('>')[0]
    assert 'Dodaj i następny' in html
    assert 'quick-add.js' in html
    assert 'quick-add.css' in html
    assert 'data-max-photos="10"' in html
    assert 'inputmode="decimal"' in html


def test_menu_and_products_list_link_to_quick_add(db, client, as_admin, on_hand_type):
    html = client.get('/admin/products/').get_data(as_text=True)
    assert html.count('/admin/products/quick-add') >= 2  # menu + przycisk na liście


def test_create_passes_description(db, client, as_admin, on_hand_type, upload_dir):
    from modules.products.models import Product
    pid = _post_create(client, description='Nowy, w folii').get_json()['product']['id']
    assert db.session.get(Product, pid).description == 'Nowy, w folii'


def test_quick_add_page_has_optional_description(db, client, as_admin, on_hand_type):
    html = client.get('/admin/products/quick-add').get_data(as_text=True)
    assert 'id="qa-description"' in html
    assert 'maxlength="1000"' in html
