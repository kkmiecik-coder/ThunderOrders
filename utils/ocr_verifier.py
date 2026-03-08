"""
OCR Payment Verification Engine
Analizuje screenshoty potwierdzeń przelewów i oblicza confidence score.
"""

import os
import re
import json
import logging
from decimal import Decimal, InvalidOperation

from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

# Próba importu pytesseract — graceful fallback jeśli nie zainstalowany
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract not installed — OCR verification disabled")

# Próba importu pdf2image
try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    logger.warning("pdf2image not installed — PDF OCR disabled")


# ========================
# IMAGE PREPROCESSING
# ========================

def preprocess_image(image):
    """
    Przygotowuje obraz do OCR: grayscale, kontrast, wyostrzenie.
    Args:
        image: PIL.Image object
    Returns:
        PIL.Image object (preprocessed)
    """
    # Konwertuj do grayscale
    img = image.convert('L')

    # Zwiększ kontrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)

    # Wyostrz
    img = img.filter(ImageFilter.SHARPEN)

    # Skaluj małe obrazy do min. 1000px szerokości
    if img.width < 1000:
        ratio = 1000 / img.width
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    return img


def load_image_from_file(filepath):
    """
    Ładuje obraz z pliku. Obsługuje JPG, PNG, PDF.
    Dla PDF konwertuje pierwszą stronę.
    Returns:
        PIL.Image object lub None
    """
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.pdf':
        if not PDF2IMAGE_AVAILABLE:
            logger.warning("pdf2image not available, cannot process PDF")
            return None
        try:
            pages = convert_from_path(filepath, first_page=1, last_page=1, dpi=300)
            return pages[0] if pages else None
        except Exception as e:
            logger.error(f"Error converting PDF to image: {e}")
            return None
    else:
        try:
            return Image.open(filepath)
        except Exception as e:
            logger.error(f"Error opening image: {e}")
            return None


# ========================
# TEXT EXTRACTION
# ========================

def extract_text(image):
    """
    Wyciąga tekst z obrazu przez Tesseract OCR.
    Args:
        image: PIL.Image object
    Returns:
        str: wyciągnięty tekst (lub pusty string)
    """
    if not TESSERACT_AVAILABLE:
        return ""

    try:
        # Użyj polskiego i angielskiego modelu
        text = pytesseract.image_to_string(image, lang='pol+eng')
        return text
    except Exception as e:
        logger.error(f"Tesseract OCR error: {e}")
        return ""


# ========================
# AMOUNT PARSING
# ========================

# Wzorce kwot precise (z groszami)
PRECISE_AMOUNT_PATTERNS = [
    # "442,86 zł", "442,86 PLN", "442.86 zł"
    r'(\d[\d\s]*[\d])[,.](\d{2})\s*(?:zł|PLN|pln|ZŁ|złotych)',
    # "442,86" lub "442.86" (standalone, z separatorem tysięcy)
    r'(\d[\d\s]*[\d])[,.](\d{2})',
]

# Wzorce kwot imprecise (bez groszy — np. "442 zł")
IMPRECISE_AMOUNT_PATTERNS = [
    r'(?<![,.\d])(\d[\d\s]*\d)\s*(?:zł|PLN|pln|ZŁ|złotych)',
]


def extract_amounts(text):
    """
    Wyciąga wszystkie kwoty z tekstu OCR.
    Returns:
        list[tuple(Decimal, bool)]: lista (kwota, precise)
            precise=True — kwota z groszami (np. 442.86)
            precise=False — kwota bez groszy (np. 442)
    """
    amounts = []

    # Precise patterns (z groszami)
    for pattern in PRECISE_AMOUNT_PATTERNS:
        for match in re.finditer(pattern, text):
            try:
                groups = match.groups()
                whole = re.sub(r'\s', '', groups[0])
                decimal_part = groups[1]
                amount = Decimal(f"{whole}.{decimal_part}")
                if Decimal('0.01') <= amount <= Decimal('999999.99'):
                    amounts.append((amount, True))
            except (InvalidOperation, ValueError):
                continue

    # Imprecise patterns (bez groszy)
    for pattern in IMPRECISE_AMOUNT_PATTERNS:
        for match in re.finditer(pattern, text):
            try:
                whole = re.sub(r'\s', '', match.group(1))
                amount = Decimal(whole)
                if Decimal('1') <= amount <= Decimal('999999'):
                    amounts.append((amount, False))
            except (InvalidOperation, ValueError):
                continue

    # Usuń duplikaty, zachowaj kolejność
    seen = set()
    unique = []
    for item in amounts:
        if item not in seen:
            seen.add(item)
            unique.append(item)

    return unique


# ========================
# SCORING
# ========================

def score_amount(extracted_amounts, expected_amount):
    """
    Ocenia dopasowanie kwoty. Max 40 punktów.

    Args:
        extracted_amounts: list[tuple(Decimal, bool)] — (kwota, precise) znalezione na screenshocie
        expected_amount: Decimal — oczekiwana kwota

    Returns:
        tuple(int, dict): (score, details)
    """
    if not extracted_amounts or not expected_amount:
        return 0, {'found_amounts': [], 'expected': str(expected_amount), 'match': 'none'}

    expected = Decimal(str(expected_amount))

    # Znajdź najlepsze dopasowanie — preferuj precise
    best_match = None
    best_diff = None
    best_precise = False

    for amount, precise in extracted_amounts:
        diff = abs(amount - expected)
        # Preferuj precise przy tej samej różnicy
        if best_diff is None or diff < best_diff or (diff == best_diff and precise and not best_precise):
            best_diff = diff
            best_match = amount
            best_precise = precise

    details = {
        'found_amounts': [str(a) for a, _ in extracted_amounts],
        'expected': str(expected),
        'best_match': str(best_match),
        'difference': str(best_diff),
        'precise': best_precise,
    }

    if best_precise:
        # Precise match (z groszami) — pełny scoring max 40 pkt
        if best_diff <= Decimal('1.00'):
            details['match'] = 'exact'
            return 40, details
        elif best_diff <= Decimal('5.00'):
            details['match'] = 'close'
            return 20, details
        elif best_diff <= Decimal('10.00'):
            details['match'] = 'partial'
            return 10, details
        else:
            details['match'] = 'none'
            return 0, details
    else:
        # Imprecise match (bez groszy) — max 20 pkt
        if int(best_match) == int(expected):
            details['match'] = 'imprecise_exact'
            return 20, details
        elif abs(int(best_match) - int(expected)) <= 1:
            details['match'] = 'imprecise_close'
            return 10, details
        else:
            details['match'] = 'none'
            return 0, details


def score_transfer_title(text, order_numbers):
    """
    Ocenia czy tytuł przelewu zawiera numery zamówień. Max 30 punktów.

    Args:
        text: str — tekst OCR
        order_numbers: list[str] — np. ['EX/00000002', 'EX/00000001']

    Returns:
        tuple(int, dict): (score, details)
    """
    if not order_numbers:
        return 0, {'expected': [], 'found': [], 'match': 'none'}

    found = []
    text_normalized = text.upper().replace(' ', '')

    for order_num in order_numbers:
        # Szukaj dokładnego numeru lub wariantów
        variants = [
            order_num,                          # EX/00000002
            order_num.replace('/', ''),          # EX00000002
            order_num.replace('/', ' '),         # EX 00000002
        ]
        for variant in variants:
            if variant.upper().replace(' ', '') in text_normalized:
                found.append(order_num)
                break

    details = {
        'expected': order_numbers,
        'found': found,
    }

    if not found:
        details['match'] = 'none'
        return 0, details

    ratio = len(found) / len(order_numbers)
    score = int(30 * ratio)

    details['match'] = 'full' if ratio == 1.0 else 'partial'
    details['ratio'] = f"{len(found)}/{len(order_numbers)}"

    return score, details


def score_recipient(text, payment_method):
    """
    Ocenia czy dane odbiorcy pasują do wybranej metody płatności. Max 20 punktów.

    Args:
        text: str — tekst OCR
        payment_method: PaymentMethod object lub None

    Returns:
        tuple(int, dict): (score, details)
    """
    if not payment_method:
        return 0, {'match': 'no_method', 'searched': []}

    text_upper = text.upper()
    text_normalized = re.sub(r'\s', '', text_upper)
    searched = []
    found = []

    # Sprawdź dane zależne od metody
    method_name = (payment_method.name or '').lower()

    # Nazwa/keyword metody (PayPal, Revolut, BLIK)
    if method_name in ('paypal', 'revolut', 'blik'):
        keyword = method_name.upper()
        searched.append(f"keyword:{keyword}")
        if keyword in text_upper:
            found.append(f"keyword:{keyword}")

    # Numer konta (dla przelewu tradycyjnego)
    if payment_method.account_number:
        account = payment_method.account_number.strip()
        account_normalized = re.sub(r'\s', '', account)
        searched.append(f"account:{account}")

        # Szukaj pełnego lub częściowego numeru konta
        if account_normalized in text_normalized:
            found.append(f"account:full")
        else:
            # Szukaj fragmentów (ostatnie 8 cyfr, środkowe fragmenty)
            digits_only = re.sub(r'\D', '', account_normalized)
            if len(digits_only) >= 8:
                last8 = digits_only[-8:]
                if last8 in re.sub(r'\D', '', text):
                    found.append(f"account:partial")

    # Odbiorca (imię/nazwisko)
    if payment_method.recipient:
        recipient = payment_method.recipient.strip()
        searched.append(f"recipient:{recipient}")
        if recipient.upper() in text_upper:
            found.append(f"recipient:{recipient}")
        else:
            # Szukaj poszczególnych słów
            words = recipient.split()
            for word in words:
                if len(word) >= 3 and word.upper() in text_upper:
                    found.append(f"recipient_word:{word}")
                    break

    # Kod (SWIFT, Revtag)
    if payment_method.code:
        code = payment_method.code.strip()
        searched.append(f"code:{code}")
        if code.upper() in text_upper:
            found.append(f"code:{code}")

    details = {
        'method': payment_method.name,
        'searched': searched,
        'found': found,
    }

    if not found:
        details['match'] = 'none'
        return 0, details
    elif len(found) >= 2:
        details['match'] = 'strong'
        return 20, details
    else:
        details['match'] = 'partial'
        return 12, details


def score_readability(text):
    """
    Ocenia czytelność wyciągniętego tekstu. Max 10 punktów.

    Args:
        text: str — tekst OCR

    Returns:
        tuple(int, dict): (score, details)
    """
    # Policz znaki alfanumeryczne
    alnum_count = sum(1 for c in text if c.isalnum())

    details = {
        'total_chars': len(text),
        'alnum_chars': alnum_count,
    }

    if alnum_count >= 50:
        details['quality'] = 'good'
        return 10, details
    elif alnum_count >= 20:
        details['quality'] = 'fair'
        return 5, details
    else:
        details['quality'] = 'poor'
        return 0, details


# ========================
# MAIN VERIFY FUNCTION
# ========================

def verify_payment_proof(filepath, expected_amount, order_numbers, payment_method=None):
    """
    Główna funkcja weryfikacji potwierdzenia płatności.

    Args:
        filepath: str — ścieżka do pliku (JPG/PNG/PDF)
        expected_amount: Decimal — oczekiwana kwota sumaryczna
        order_numbers: list[str] — numery zamówień (np. ['EX/00000002', 'EX/00000001'])
        payment_method: PaymentMethod object lub None

    Returns:
        dict: {
            'score': int (0-100),
            'details': {
                'amount': {...},
                'title': {...},
                'recipient': {...},
                'readability': {...},
                'raw_text_preview': str (first 500 chars)
            }
        }
    """
    if not TESSERACT_AVAILABLE:
        return {
            'score': None,
            'details': {'error': 'Tesseract not available'}
        }

    # 1. Załaduj obraz
    image = load_image_from_file(filepath)
    if image is None:
        return {
            'score': None,
            'details': {'error': 'Cannot load image'}
        }

    # 2. Preprocessing
    processed = preprocess_image(image)

    # 3. OCR
    text = extract_text(processed)

    if not text.strip():
        return {
            'score': 0,
            'details': {
                'error': 'OCR extracted no text',
                'amount': {'score': 0, 'match': 'none'},
                'title': {'score': 0, 'match': 'none'},
                'recipient': {'score': 0, 'match': 'none'},
                'readability': {'score': 0, 'quality': 'poor'},
            }
        }

    # 4. Scoring
    amount_score, amount_details = score_amount(
        extract_amounts(text),
        expected_amount
    )

    title_score, title_details = score_transfer_title(text, order_numbers)

    recipient_score, recipient_details = score_recipient(text, payment_method)

    readability_score, readability_details = score_readability(text)

    # 5. Łączny score
    total_score = amount_score + title_score + recipient_score + readability_score

    return {
        'score': total_score,
        'details': {
            'amount': {**amount_details, 'score': amount_score},
            'title': {**title_details, 'score': title_score},
            'recipient': {**recipient_details, 'score': recipient_score},
            'readability': {**readability_details, 'score': readability_score},
            'raw_text_preview': text[:500],
        }
    }
