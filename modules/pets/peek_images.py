"""Obrazki wychylania towarzysza (spec v3.2 §6.4): zapis wgranego pliku jako WebP z przezroczystością.

`utils.image_processor.compress_image` spłaszcza alfę do białego tła — ozdobniki (gwiazdka, serduszko)
jej potrzebują, więc ten moduł robi własny zapis.
"""
import io
import os
import uuid

from flask import current_app
from PIL import Image, ImageOps

ALLOWED_EXT = frozenset({'png', 'jpg', 'jpeg', 'webp', 'gif'})
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_SOURCE_PIXELS = 4_000_000        # ~2000×2000 — chroni przed „bombą” zakodowaną w małym pliku
MAX_IMAGES = 30
BOX = 240                            # dłuższy bok po zapisie
UPLOAD_SUBDIR = ('uploads', 'pet_peeks')


class PeekImageError(ValueError):
    """Komunikat dla admina (po polsku), pokazywany we flashu."""


def upload_dir():
    """Katalog zapisu; testy podmieniają go przez config['PETS_PEEK_UPLOAD_DIR']."""
    return current_app.config.get('PETS_PEEK_UPLOAD_DIR') or os.path.join(current_app.static_folder, *UPLOAD_SUBDIR)


def save_upload(storage):
    """Waliduje i zapisuje wgrany plik; zwraca nazwę pliku (`<uuid>.webp`) albo rzuca PeekImageError."""
    nazwa = storage.filename or ''
    ext = nazwa.rsplit('.', 1)[-1].lower() if '.' in nazwa else ''
    if ext not in ALLOWED_EXT:
        raise PeekImageError('Dozwolone formaty: PNG, JPG, WebP, GIF.')
    dane = storage.read(MAX_SOURCE_BYTES + 1)
    if not dane:
        raise PeekImageError('Plik jest pusty.')
    if len(dane) > MAX_SOURCE_BYTES:
        raise PeekImageError('Plik jest za duży (maks. 2 MB).')
    try:
        obraz = Image.open(io.BytesIO(dane))
        if obraz.width * obraz.height > MAX_SOURCE_PIXELS:
            raise PeekImageError('Obrazek ma za dużo pikseli (maks. 2000×2000).')
        obraz.load()                                    # GIF: pierwsza klatka
        obraz = ImageOps.exif_transpose(obraz).convert('RGBA')
    except PeekImageError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError):
        raise PeekImageError('Nie udało się odczytać obrazka — plik jest uszkodzony.')
    obraz.thumbnail((BOX, BOX), Image.Resampling.LANCZOS)
    katalog = upload_dir()
    os.makedirs(katalog, exist_ok=True)
    filename = f'{uuid.uuid4().hex}.webp'
    obraz.save(os.path.join(katalog, filename), 'WEBP', quality=85)
    return filename


def remove_file(filename):
    """Kasuje plik z dysku; brak pliku lub błąd systemu plików nie blokuje usunięcia rekordu."""
    try:
        os.remove(os.path.join(upload_dir(), filename))
    except OSError:
        current_app.logger.warning('pets: nie udało się usunąć pliku obrazka %s', filename)
