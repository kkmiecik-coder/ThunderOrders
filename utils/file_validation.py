"""
File integrity validation helpers.
Wykrywa uszkodzone/niepełne uploady (np. ucięte JPEGi z urządzeń mobilnych)
zanim trafią do bazy lub pipeline'u OCR.
"""
import os
import logging
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


def validate_image_file(filepath):
    """
    Sprawdza czy obraz jest kompletny (pełny load pikseli).

    Returns:
        (is_valid: bool, error_message: str | None)
    """
    try:
        with Image.open(filepath) as img:
            img.load()
        return True, None
    except (OSError, UnidentifiedImageError, ValueError) as e:
        return False, str(e)


def validate_pdf_file(filepath):
    """
    Sprawdza czy PDF ma poprawne nagłówki (magic bytes %PDF-).

    Returns:
        (is_valid: bool, error_message: str | None)
    """
    try:
        with open(filepath, 'rb') as f:
            header = f.read(5)
        if header != b'%PDF-':
            return False, 'Brak nagłówka PDF'
        return True, None
    except OSError as e:
        return False, str(e)


def validate_proof_file(filepath):
    """
    Waliduje plik potwierdzenia płatności (image lub PDF).
    Wykrywa truncated images, corrupt files, podmienione rozszerzenia.

    Returns:
        (is_valid: bool, error_message: str | None)
    """
    if not os.path.exists(filepath):
        return False, 'Plik nie istnieje'

    if os.path.getsize(filepath) == 0:
        return False, 'Plik jest pusty'

    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.pdf':
        return validate_pdf_file(filepath)
    if ext in ('.jpg', '.jpeg', '.png'):
        return validate_image_file(filepath)

    return False, f'Nieobsługiwane rozszerzenie: {ext}'
