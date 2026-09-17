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

FILTER_ALL = 'all'
FILTER_INCOMING = 'incoming'
FILTER_OWNED = 'owned'
ALLOWED_FILTERS = (FILTER_ALL, FILTER_INCOMING, FILTER_OWNED)


class MergedPagination:
    """Odpowiednik flask-sqlalchemy Pagination dla listy scalonej w Pythonie.

    Pozycji wirtualnych nie ma w żadnej tabeli, więc LIMIT/OFFSET po stronie
    bazy nie wchodzi w grę — tniemy gotową listę i podajemy szablonowi ten sam
    interfejs, którego używał dotąd (szablon paginacji zostaje bez zmian).
    """

    def __init__(self, items, page, per_page):
        self.total = len(items)
        self.per_page = per_page
        self.pages = max(1, (self.total + per_page - 1) // per_page) if self.total else 0
        self.page = page
        start = (page - 1) * per_page
        self.items = items[start:start + per_page]

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None

    def iter_pages(self, left_edge=2, left_current=2, right_current=3, right_edge=2):
        """Uproszczona wersja — kolekcja klienta nie dochodzi do setek stron."""
        for num in range(1, self.pages + 1):
            yield num


def _sort_key(sort):
    """(funkcja klucza, malejąco) dla listy scalonej — parytet z sortami SQL."""
    from decimal import Decimal
    if sort == 'oldest':
        return (lambda i: i.created_at), False
    if sort == 'name_asc':
        return (lambda i: (i.name or '').lower()), False
    if sort == 'price_desc':
        # NULL-e na koniec niezależnie od kierunku — tak samo jak db.case w SQL
        return (lambda i: (i.market_price is not None,
                           Decimal(str(i.market_price)) if i.market_price is not None
                           else Decimal('0'))), True
    return (lambda i: i.created_at), True          # newest (domyślny)


def get_owned_item(user_id, item_id):
    """Item usera albo None — cudze/nieistniejące traktowane identycznie (mobile maskuje 404)."""
    item = db.session.get(CollectionItem, item_id)
    if item is None or item.user_id != user_id:
        return None
    return item


def list_items(user_id, search=None, sort='newest', page=1, per_page=24,
               include_incoming=False, stage_filter=None):
    """Pagination obiekt. Bez `include_incoming` zachowanie jest identyczne jak
    przed dodaniem pozycji w drodze — mobile API i publiczna kolekcja na tym stoją.

    Z `include_incoming` scalamy wiersze z bazy z pozycjami wyliczonymi z zamówień,
    sortujemy wspólnie i tniemy na strony w Pythonie (patrz MergedPagination).
    """
    query = CollectionItem.query.filter_by(user_id=user_id)
    if search:
        query = query.filter(CollectionItem.name.ilike(f'%{search}%'))

    if not include_incoming:                       # ŚCIEŻKA BEZ ZMIAN
        if sort == 'oldest':
            query = query.order_by(CollectionItem.created_at.asc())
        elif sort == 'name_asc':
            query = query.order_by(CollectionItem.name.asc())
        elif sort == 'price_desc':
            query = query.order_by(
                db.case((CollectionItem.market_price.is_(None), 1), else_=0),
                CollectionItem.market_price.desc())
        else:
            query = query.order_by(CollectionItem.created_at.desc())
        return query.paginate(page=page, per_page=per_page, error_out=False)

    from modules.client.collection_incoming import incoming_items

    stage_filter = stage_filter if stage_filter in ALLOWED_FILTERS else FILTER_ALL

    owned = [] if stage_filter == FILTER_INCOMING else query.all()
    if stage_filter == FILTER_OWNED:
        incoming = []
        incoming_total = None       # serwis nie liczył w tej gałęzi — wołający musi sam
    else:
        incoming = incoming_items(user_id)
        # Licznik WSZYSTKICH pozycji w drodze użytkownika — przed filtrowaniem
        # wyszukiwarką, żeby jedno wywołanie serwisowało zarówno listę, jak
        # i licznik pokazywany niezależnie od `search`/`stage_filter`.
        incoming_total = len(incoming)
        if search:
            needle = search.lower()
            incoming = [i for i in incoming if needle in (i.name or '').lower()]

    key, reverse = _sort_key(sort)
    merged = sorted(owned + incoming, key=key, reverse=reverse)
    pagination = MergedPagination(merged, page=page, per_page=per_page)
    pagination.incoming_total = incoming_total
    return pagination


def create_item(user, name, market_price=None, notes=None, files=None, temp_uploads=None):
    """(ok, err, item). Item + max 3 zdjęć z `files` (FileStorage; pierwszy = primary)
    + opcjonalne rekordy QR temp_uploads (web). All-or-nothing przy błędzie pliku.
    Parytet web collection_add (l. 97-153)."""
    from utils.image_processor import process_collection_upload, delete_collection_image_files
    item = CollectionItem(user_id=user.id, name=name, market_price=market_price,
                          notes=notes or None, source='manual')
    db.session.add(item)
    db.session.flush()                                        # item.id
    saved_paths = []                                          # pliki zapisane w tej próbie
    try:
        for i, file in enumerate((files or [])[:MAX_IMAGES_PER_ITEM]):
            if file and file.filename:
                result = process_collection_upload(file, user.id)
                saved_paths.append((result['path_original'], result['path_compressed']))
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
        # rollback cofa wiersze DB, ale pliki z udanych iteracji są już na dysku — sprzątamy
        for orig, compr in saved_paths:
            delete_collection_image_files(orig, compr)
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
    image = db.session.get(CollectionItemImage, image_id)
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


def get_public_config(user_id):
    from modules.client.models import PublicCollectionConfig
    return PublicCollectionConfig.query.filter_by(user_id=user_id).first()


def create_public_config(user):
    """(ok, err, config). Token + defaulty + achievement. Parytet web public/create
    (l. 405-425); 'exists' gdy już jest (web: 409)."""
    from modules.client.models import PublicCollectionConfig
    if get_public_config(user.id):
        return False, {'code': 'exists'}, None
    config = PublicCollectionConfig(user_id=user.id,
                                    token=PublicCollectionConfig.generate_token(),
                                    show_prices=True, is_active=True)
    db.session.add(config)
    db.session.commit()
    try:                                                      # achievement (parytet l. 421-425)
        from modules.achievements.services import AchievementService
        AchievementService().check_event(user, 'collection_public_toggle')
    except Exception:
        pass
    return True, None, config


def update_public_config(user_id, show_prices=None, is_active=None):
    """(ok, err, config). Tylko podane flagi. Parytet web public/config POST (l. 479-493)."""
    config = get_public_config(user_id)
    if config is None:
        return False, {'code': 'not_found'}, None
    if show_prices is not None:
        config.show_prices = bool(show_prices)
    if is_active is not None:
        config.is_active = bool(is_active)
    db.session.commit()
    return True, None, config


def toggle_item_public(user_id, item_id):
    """(ok, err, item). Parytet web toggle-public (l. 512-518)."""
    item = get_owned_item(user_id, item_id)
    if item is None:
        return False, {'code': 'not_found'}, None
    item.is_public = not item.is_public
    db.session.commit()
    return True, None, item
