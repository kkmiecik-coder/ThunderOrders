"""
Blokada tymczasowych adresów email
Lista ~5000 domen z github.com/disposable-email-domains
"""

import os

_BLOCKLIST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data',
    'disposable_email_blocklist.conf'
)

def _load_blocklist():
    """Ładuje listę domen z pliku conf do frozenset."""
    try:
        with open(_BLOCKLIST_PATH, 'r') as f:
            return frozenset(
                line.strip().lower()
                for line in f
                if line.strip() and not line.startswith('#')
            )
    except FileNotFoundError:
        return frozenset()


DISPOSABLE_DOMAINS = _load_blocklist()


def is_disposable_email(email):
    """
    Sprawdza czy email używa tymczasowej domeny.

    Args:
        email (str): Adres email do sprawdzenia

    Returns:
        bool: True jeśli domena jest na blackliście
    """
    if not email or '@' not in email:
        return False
    domain = email.rsplit('@', 1)[1].lower().strip()
    return domain in DISPOSABLE_DOMAINS
