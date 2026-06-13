"""Wspólny serwis kolekcji klienta — web (trasy collection.py) + mobilne API (E8).

Logika przeniesiona 1:1 z modules/client/collection.py. Serwis NIE importuje nic
z modules.api_mobile (brak cyklu). Funkcje zwracają (ok, err[, value]) — kanał serializuje.
Kwoty: serwis operuje na Decimal|None — parsowanie (float PLN w webie, grosze w mobile)
zostaje w kanałach. QR temp_uploads (web-only) wchodzą parametrem do create_item, żeby
webowy add zachował JEDEN commit.
"""

from extensions import db
from modules.client.models import CollectionItem, CollectionItemImage

MAX_IMAGES_PER_ITEM = 3
ALLOWED_SORTS = ('newest', 'oldest', 'name_asc', 'price_desc')


def get_owned_item(user_id, item_id):
    """Item usera albo None — cudze/nieistniejące traktowane identycznie (mobile maskuje 404)."""
    item = CollectionItem.query.get(item_id)
    if item is None or item.user_id != user_id:
        return None
    return item


def list_items(user_id, search=None, sort='newest', page=1, per_page=24):
    """Pagination obiekt. Parytet web collection_list (l. 36-55): ilike, 4 sorty, NULL-e
    cen na końcu przy price_desc."""
    query = CollectionItem.query.filter_by(user_id=user_id)
    if search:
        query = query.filter(CollectionItem.name.ilike(f'%{search}%'))
    if sort == 'oldest':
        query = query.order_by(CollectionItem.created_at.asc())
    elif sort == 'name_asc':
        query = query.order_by(CollectionItem.name.asc())
    elif sort == 'price_desc':
        query = query.order_by(
            db.case((CollectionItem.market_price.is_(None), 1), else_=0),
            CollectionItem.market_price.desc())
    else:  # newest (default)
        query = query.order_by(CollectionItem.created_at.desc())
    return query.paginate(page=page, per_page=per_page, error_out=False)


def create_item(user, name, market_price=None, notes=None, files=None, temp_uploads=None):
    """(ok, err, item). Item + max 3 zdjęć z `files` (FileStorage; pierwszy = primary)
    + opcjonalne rekordy QR temp_uploads (web). All-or-nothing przy błędzie pliku.
    Parytet web collection_add (l. 97-153)."""
    from utils.image_processor import process_collection_upload
    item = CollectionItem(user_id=user.id, name=name, market_price=market_price,
                          notes=notes or None, source='manual')
    db.session.add(item)
    db.session.flush()                                        # item.id
    try:
        for i, file in enumerate((files or [])[:MAX_IMAGES_PER_ITEM]):
            if file and file.filename:
                result = process_collection_upload(file, user.id)
                db.session.add(CollectionItemImage(
                    collection_item_id=item.id, filename=result['filename'],
                    path_original=result['path_original'],
                    path_compressed=result['path_compressed'],
                    is_primary=(i == 0), sort_order=i))
        for temp in (temp_uploads or []):                     # QR flow (web-only; parytet l. 132-144)
            if item.can_add_image:
                db.session.add(CollectionItemImage(
                    collection_item_id=item.id, filename=temp.filename,
                    path_original=temp.path_original,
                    path_compressed=temp.path_compressed,
                    is_primary=(item.images_count == 0),
                    sort_order=item.images_count))
                db.session.flush()
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return False, {'code': 'invalid_file', 'message': str(e)}, None
    try:                                                      # achievement (parytet l. 149-153)
        from modules.achievements.services import AchievementService
        AchievementService().check_event(user, 'collection_add')
    except Exception:
        pass
    return True, None, item


def update_item(user_id, item_id, fields):
    """(ok, err, item). `fields`: dict z kluczami spośród name/market_price/notes —
    obecny klucz nadpisuje (None czyści cenę/notatki; name puste → name_required).
    Web wysyła komplet pól → zachowanie identyczne; mobile robi PATCH częściowy."""
    item = get_owned_item(user_id, item_id)
    if item is None:
        return False, {'code': 'not_found'}, None
    if 'name' in fields:
        if not fields['name']:
            return False, {'code': 'name_required'}, None
        item.name = fields['name']
    if 'market_price' in fields:
        item.market_price = fields['market_price']
    if 'notes' in fields:
        item.notes = fields['notes'] or None
    db.session.commit()
    return True, None, item


def delete_item(user_id, item_id):
    """(ok, err). Pliki zdjęć (best-effort) + wiersz (cascade images). Parytet web l. 246-252."""
    from utils.image_processor import delete_collection_image_files
    item = get_owned_item(user_id, item_id)
    if item is None:
        return False, {'code': 'not_found'}
    for image in item.images:
        delete_collection_image_files(image.path_original, image.path_compressed)
    db.session.delete(item)
    db.session.commit()
    return True, None


def add_image(user, item_id, file):
    """(ok, err, image). Limit 3 (can_add_image); pierwszy = primary; achievement.
    Parytet web collection_add_image (l. 272-313)."""
    from utils.image_processor import process_collection_upload
    item = get_owned_item(user.id, item_id)
    if item is None:
        return False, {'code': 'not_found'}, None
    if not item.can_add_image:
        return False, {'code': 'max_images'}, None
    if not file or not file.filename:
        return False, {'code': 'no_file'}, None
    try:
        result = process_collection_upload(file, user.id)
    except ValueError as e:
        return False, {'code': 'invalid_file', 'message': str(e)}, None
    image = CollectionItemImage(
        collection_item_id=item.id, filename=result['filename'],
        path_original=result['path_original'], path_compressed=result['path_compressed'],
        is_primary=(item.images_count == 0), sort_order=item.images_count)
    db.session.add(image)
    db.session.commit()
    try:                                                      # achievement (parytet l. 298-303)
        from modules.achievements.services import AchievementService
        AchievementService().check_event(user, 'photo_upload')
    except Exception:
        pass
    return True, None, image


def _get_owned_image(user_id, item_id, image_id):
    """(item, image) — (None, None) gdy item cudzy/brak; (item, None) gdy zdjęcie nie
    należy do itemu (web: 404 — parytet l. 331-337)."""
    item = get_owned_item(user_id, item_id)
    if item is None:
        return None, None
    image = CollectionItemImage.query.get(image_id)
    if image is None or image.collection_item_id != item.id:
        return item, None
    return item, image


def delete_image(user_id, item_id, image_id):
    """(ok, err). Pliki + wiersz; primary przechodzi na pierwszy pozostały.
    Parytet web collection_delete_image (l. 339-350) — verbatim, łącznie z flush."""
    from utils.image_processor import delete_collection_image_files
    item, image = _get_owned_image(user_id, item_id, image_id)
    if item is None or image is None:
        return False, {'code': 'not_found'}
    was_primary = image.is_primary
    delete_collection_image_files(image.path_original, image.path_compressed)
    db.session.delete(image)
    db.session.flush()
    if was_primary and item.images:
        item.images[0].is_primary = True
    db.session.commit()
    return True, None


def set_primary_image(user_id, item_id, image_id):
    """(ok, err, image). Unset wszystkich → set wskazanego. Parytet web l. 377-384."""
    item, image = _get_owned_image(user_id, item_id, image_id)
    if item is None or image is None:
        return False, {'code': 'not_found'}, None
    for img in item.images:
        img.is_primary = False
    image.is_primary = True
    db.session.commit()
    return True, None, image
