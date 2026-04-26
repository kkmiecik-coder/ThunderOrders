"""
Admin CRUD for achievements (manual badges).
Endpointy będą dodane w Tasku 6.
"""
import os
import re
from flask import current_app
from PIL import Image

from modules.achievements.models import Achievement


ALLOWED_IMAGE_MIMES = {'image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif'}
SLUG_RE = re.compile(r'^[a-z0-9-]+$')
MAX_ICON_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MIN_ICON_DIMENSION = 64


def _slugify(name):
    """Bardzo prosta slugifikacja PL → ASCII bez polskich znaków."""
    pl_map = str.maketrans({
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
        'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
        'Ą': 'a', 'Ć': 'c', 'Ę': 'e', 'Ł': 'l', 'Ń': 'n',
        'Ó': 'o', 'Ś': 's', 'Ź': 'z', 'Ż': 'z',
    })
    s = name.translate(pl_map).lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:80] or 'badge'


def _ensure_unique_slug(base_slug, exclude_id=None):
    """Zwraca slug + ewentualny suffix -2, -3, jeśli kolizja."""
    slug = base_slug
    n = 2
    while True:
        q = Achievement.query.filter_by(slug=slug)
        if exclude_id is not None:
            q = q.filter(Achievement.id != exclude_id)
        if not q.first():
            return slug
        slug = f'{base_slug}-{n}'
        n += 1


def _process_icon_upload(file_storage, slug):
    """
    Waliduje i zapisuje ikonę jako <slug>@256.png w static/uploads/achievements/.
    Rzuca ValueError przy błędzie walidacji.
    """
    if not file_storage or not file_storage.filename:
        raise ValueError('Brak pliku ikony')

    if file_storage.mimetype not in ALLOWED_IMAGE_MIMES:
        raise ValueError(f'Nieobsługiwany format: {file_storage.mimetype}')

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > MAX_ICON_SIZE_BYTES:
        raise ValueError(f'Plik za duży ({size} B), max {MAX_ICON_SIZE_BYTES} B')

    try:
        img = Image.open(file_storage.stream)
        img.verify()
    except Exception as e:
        raise ValueError(f'Nieprawidłowy plik obrazu: {e}')

    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream).convert('RGBA')

    if img.width < MIN_ICON_DIMENSION or img.height < MIN_ICON_DIMENSION:
        raise ValueError(f'Obraz za mały ({img.width}×{img.height}), min {MIN_ICON_DIMENSION}×{MIN_ICON_DIMENSION}')

    img.thumbnail((256, 256), Image.LANCZOS)
    canvas = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    x = (256 - img.width) // 2
    y = (256 - img.height) // 2
    canvas.paste(img, (x, y), img)

    if not SLUG_RE.match(slug):
        raise ValueError(f'Nieprawidłowy slug: {slug}')

    upload_dir = os.path.join(current_app.static_folder, 'uploads', 'achievements')
    os.makedirs(upload_dir, exist_ok=True)
    out_path = os.path.join(upload_dir, f'{slug}@256.png')
    canvas.save(out_path, 'PNG', optimize=True)

    # Invalidate icon cache
    from modules.achievements.services import _icon_cache
    _icon_cache.pop(slug, None)
