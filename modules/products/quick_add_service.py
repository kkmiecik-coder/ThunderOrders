"""
Szybkie dodawanie produktów on hand — ekran pod telefon.

Zdjęcie(a) + nazwa + cena + ilość → aktywny produkt typu on-hand, widoczny od razu
w sklepie. Pozostałe pola produktu zostają puste; resztę da się uzupełnić w zwykłym
formularzu magazynu.
"""

import os
from decimal import Decimal, InvalidOperation

from flask import current_app, url_for
from markupsafe import escape

from extensions import db
from modules.client.shop_service import ON_HAND_SLUG, get_on_hand_type
from modules.products.models import Product, ProductImage
from utils.activity_logger import log_activity
from utils.image_processor import get_image_settings, process_upload


NAME_MAX_LEN = 255
DESCRIPTION_MAX_LEN = 1000


class QuickAddError(ValueError):
    """Błąd walidacji/zapisu — komunikat po polsku, do pokazania w toaście."""


def parse_price(raw):
    try:
        value = Decimal(str(raw).strip().replace(',', '.'))
    except (InvalidOperation, AttributeError):
        raise QuickAddError('Podaj poprawną cenę')
    if raw is None or not value.is_finite() or value <= 0:
        raise QuickAddError('Podaj poprawną cenę')
    return value.quantize(Decimal('0.01'))


def parse_quantity(raw):
    if raw is None or str(raw).strip() == '':
        return 1
    text = str(raw).strip()
    if not text.isdigit() or int(text) < 1:
        raise QuickAddError('Ilość musi być liczbą od 1 wzwyż')
    return int(text)


def _clean_name(name):
    name = (name or '').strip()
    if not name:
        raise QuickAddError('Podaj nazwę')
    if len(name) > NAME_MAX_LEN:
        raise QuickAddError('Nazwa jest za długa')
    return name


def _clean_description(text):
    """Zwykły tekst z telefonu → bezpieczny HTML (sklep wyświetla opis przez |safe,
    bo zwykły formularz ma edytor HTML). Enter → <br>."""
    text = (text or '').strip()
    if not text:
        return None
    if len(text) > DESCRIPTION_MAX_LEN:
        raise QuickAddError(f'Opis jest za długi (maks. {DESCRIPTION_MAX_LEN} znaków)')
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    return '<br>'.join(str(escape(line)) for line in lines)


def _remove_saved_files(upload_folder, filenames):
    for filename in filenames:
        for sub in ('original', 'compressed'):
            path = os.path.join(upload_folder, sub, filename)
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                current_app.logger.warning(f'Nie udało się usunąć pliku {path}')


def create_quick_product(name, price_raw, quantity_raw, files, user, description=None):
    name = _clean_name(name)
    description = _clean_description(description)
    price = parse_price(price_raw)
    quantity = parse_quantity(quantity_raw)

    files = [f for f in (files or []) if f and f.filename]
    if not files:
        raise QuickAddError('Dodaj co najmniej jedno zdjęcie')
    max_photos = int(get_image_settings()['max_per_product'])
    if len(files) > max_photos:
        raise QuickAddError(f'Maksymalnie {max_photos} zdjęć')

    on_hand_type = get_on_hand_type()
    if on_hand_type is None:
        raise QuickAddError('Brak typu produktu „On-hand” w ustawieniach magazynu')

    product = Product(
        name=name,
        sale_price=price,
        quantity=quantity,
        description=description,
        product_type_id=on_hand_type.id,
        is_active=True,
        is_gratis=False,
    )
    product.calculate_margin()
    db.session.add(product)
    db.session.flush()

    upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'products')
    saved = []
    try:
        for index, file in enumerate(files, start=1):
            data = process_upload(file, upload_folder)
            saved.append(data['filename'])
            db.session.add(ProductImage(
                product_id=product.id,
                filename=data['filename'],
                path_original=data['path_original'],
                path_compressed=data['path_compressed'],
                is_primary=(index == 1),
                sort_order=index,
            ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        _remove_saved_files(upload_folder, saved)
        current_app.logger.error(f'Szybkie dodawanie: błąd zapisu zdjęcia: {e}')
        raise QuickAddError('Nie udało się zapisać zdjęcia — spróbuj ponownie')

    log_activity(user=user, action='product_created', entity_type='product', entity_id=product.id)
    return product


def update_quick_product(product, name, price_raw, quantity_raw):
    name = _clean_name(name)
    price = parse_price(price_raw)
    quantity = parse_quantity(quantity_raw)
    product.name = name
    product.sale_price = price
    product.quantity = quantity
    product.calculate_margin()
    db.session.commit()
    return product


def hide_quick_product(product):
    product.is_active = False
    db.session.commit()
    return product


def is_quick_editable(product):
    return product.product_type is not None and product.product_type.slug == ON_HAND_SLUG


def serialize_quick_product(product):
    primary = (product.images.filter_by(is_primary=True).first()
               or product.images.order_by(ProductImage.sort_order).first())
    return {
        'id': product.id,
        'name': product.name,
        'sale_price': f'{Decimal(product.sale_price):.2f}',
        'quantity': product.quantity,
        'is_active': bool(product.is_active),
        'thumb_url': url_for('static', filename=primary.path_compressed) if primary else None,
    }
