"""Testy serwisu szybkiego dodawania produktów on hand (ekran na telefon)."""

import io
import os
from decimal import Decimal

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage


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


@pytest.fixture
def admin(make_user):
    return make_user(role='admin')


@pytest.fixture(autouse=True)
def _request_ctx(app):
    # serialize_quick_product używa url_for, a Settings/maile czytają flask.session
    with app.test_request_context():
        yield


def _jpeg(name='a.jpg'):
    buf = io.BytesIO()
    Image.new('RGB', (40, 30), (200, 100, 50)).save(buf, 'JPEG')
    buf.seek(0)
    return FileStorage(stream=buf, filename=name, content_type='image/jpeg')


def _files_in(upload_dir):
    found = []
    for sub in ('original', 'compressed'):
        d = os.path.join(upload_dir, 'products', sub)
        if os.path.isdir(d):
            found += os.listdir(d)
    return found


# --- parsowanie ---

def test_parse_price_accepts_comma_and_dot():
    from modules.products.quick_add_service import parse_price, QuickAddError
    assert parse_price('49,99') == Decimal('49.99')
    assert parse_price('49.99') == Decimal('49.99')
    assert parse_price(' 50 ') == Decimal('50.00')
    for bad in ['', None, 'abc', '0', '-5', 'NaN', 'Infinity']:
        with pytest.raises(QuickAddError):
            parse_price(bad)


def test_parse_quantity_defaults_to_one():
    from modules.products.quick_add_service import parse_quantity, QuickAddError
    assert parse_quantity('') == 1
    assert parse_quantity(None) == 1
    assert parse_quantity('3') == 3
    for bad in ['0', '-1', '1.5', 'x']:
        with pytest.raises(QuickAddError):
            parse_quantity(bad)


# --- tworzenie ---

def test_create_makes_active_on_hand_product_visible_in_shop(db, on_hand_type, upload_dir, admin):
    from modules.products.models import Product
    from modules.products.quick_add_service import create_quick_product
    from modules.client.shop_service import build_products_query

    p = create_quick_product('  Album X  ', '49,99', '2', [_jpeg('a.jpg'), _jpeg('b.jpg')], admin)

    assert p.name == 'Album X'
    assert p.product_type_id == on_hand_type.id
    assert p.is_active is True
    assert p.is_gratis is False
    assert p.quantity == 2
    assert p.sale_price == Decimal('49.99')
    assert p.sku is None and p.margin is None and p.category_id is None
    imgs = sorted(p.images, key=lambda i: i.sort_order)
    assert [i.sort_order for i in imgs] == [1, 2]
    assert imgs[0].is_primary is True and imgs[1].is_primary is False
    assert build_products_query(on_hand_type).filter(Product.id == p.id).count() == 1


def test_create_defaults_quantity_to_one(db, on_hand_type, upload_dir, admin):
    from modules.products.quick_add_service import create_quick_product
    p = create_quick_product('Album', '10', '', [_jpeg()], admin)
    assert p.quantity == 1


@pytest.mark.parametrize('name,price,with_photo,message', [
    ('   ', '10', True, 'Podaj nazwę'),
    ('Album', '', True, 'Podaj poprawną cenę'),
    ('Album', '10', False, 'Dodaj co najmniej jedno zdjęcie'),
    ('x' * 256, '10', True, 'Nazwa jest za długa'),
])
def test_create_requires_name_price_and_photo(db, on_hand_type, upload_dir, admin,
                                              name, price, with_photo, message):
    from modules.products.models import Product
    from modules.products.quick_add_service import create_quick_product, QuickAddError
    files = [_jpeg()] if with_photo else []
    with pytest.raises(QuickAddError) as exc:
        create_quick_product(name, price, '1', files, admin)
    assert str(exc.value) == message
    assert Product.query.count() == 0
    assert _files_in(upload_dir) == []


def test_create_rejects_more_photos_than_limit(db, on_hand_type, upload_dir, admin):
    from modules.auth.models import Settings
    from modules.products.models import Product
    from modules.products.quick_add_service import create_quick_product, QuickAddError
    Settings.set_value('warehouse_image_max_per_product', 2, type='integer')
    with pytest.raises(QuickAddError) as exc:
        create_quick_product('Album', '10', '1', [_jpeg('a.jpg'), _jpeg('b.jpg'), _jpeg('c.jpg')], admin)
    assert str(exc.value) == 'Maksymalnie 2 zdjęć'
    assert Product.query.count() == 0


def test_create_without_on_hand_type_fails_cleanly(db, upload_dir, admin):
    from modules.products.models import Product
    from modules.products.quick_add_service import create_quick_product, QuickAddError
    with pytest.raises(QuickAddError) as exc:
        create_quick_product('Album', '10', '1', [_jpeg()], admin)
    assert 'On-hand' in str(exc.value)
    assert Product.query.count() == 0


def test_failed_second_photo_rolls_back_and_removes_files(db, on_hand_type, upload_dir, admin, monkeypatch):
    from modules.products import quick_add_service
    from modules.products.models import Product, ProductImage
    from modules.products.quick_add_service import create_quick_product, QuickAddError

    real = quick_add_service.process_upload
    calls = {'n': 0}

    def flaky(file, folder):
        calls['n'] += 1
        if calls['n'] == 2:
            raise ValueError('boom')
        return real(file, folder)

    monkeypatch.setattr(quick_add_service, 'process_upload', flaky)

    with pytest.raises(QuickAddError) as exc:
        create_quick_product('Album', '10', '1', [_jpeg('a.jpg'), _jpeg('b.jpg')], admin)
    assert str(exc.value) == 'Nie udało się zapisać zdjęcia — spróbuj ponownie'
    assert Product.query.count() == 0
    assert ProductImage.query.count() == 0
    assert _files_in(upload_dir) == []


# --- poprawka / ukrycie ---

def test_update_changes_fields_and_validates(db, on_hand_type, upload_dir, admin):
    from modules.products.quick_add_service import (
        create_quick_product, update_quick_product, QuickAddError,
    )
    p = create_quick_product('Album', '10', '1', [_jpeg()], admin)

    update_quick_product(p, 'Album 2', '59,00', '5')
    db.session.refresh(p)
    assert (p.name, p.sale_price, p.quantity) == ('Album 2', Decimal('59.00'), 5)

    with pytest.raises(QuickAddError):
        update_quick_product(p, '  ', '59', '5')
    db.session.refresh(p)
    assert p.name == 'Album 2'


def test_hide_sets_inactive_and_drops_from_shop(db, on_hand_type, upload_dir, admin):
    from modules.products.models import Product
    from modules.products.quick_add_service import create_quick_product, hide_quick_product
    from modules.client.shop_service import build_products_query
    p = create_quick_product('Album', '10', '1', [_jpeg()], admin)

    hide_quick_product(p)

    assert p.is_active is False
    assert build_products_query(on_hand_type).filter(Product.id == p.id).count() == 0


def test_is_quick_editable_only_for_on_hand(db, on_hand_type, upload_dir, admin, make_product):
    from modules.products.quick_add_service import create_quick_product, is_quick_editable
    p = create_quick_product('Album', '10', '1', [_jpeg()], admin)
    other = make_product()
    assert is_quick_editable(p) is True
    assert is_quick_editable(other) is False


def test_serialize_quick_product(db, on_hand_type, upload_dir, admin):
    from modules.products.quick_add_service import create_quick_product, serialize_quick_product
    p = create_quick_product('Album', '49,9', '3', [_jpeg()], admin)
    data = serialize_quick_product(p)
    assert data['id'] == p.id
    assert data['name'] == 'Album'
    assert data['sale_price'] == '49.90'
    assert data['quantity'] == 3
    assert data['is_active'] is True
    assert data['thumb_url'].startswith('/static/uploads/products/compressed/')
