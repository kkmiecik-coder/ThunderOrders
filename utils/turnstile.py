"""
Cloudflare Turnstile - weryfikacja CAPTCHA
Fail-open: jeśli Cloudflare nieosiągalny, przepuszcza (logi error)
"""

import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'


def is_turnstile_enabled():
    """Sprawdza czy Turnstile jest skonfigurowany (oba klucze ustawione)."""
    site_key = current_app.config.get('CF_TURNSTILE_SITE_KEY')
    secret_key = current_app.config.get('CF_TURNSTILE_SECRET_KEY')
    return bool(site_key and secret_key)


def verify_turnstile_token(token):
    """
    Weryfikuje token Turnstile przez Cloudflare API.

    Args:
        token (str): Token z formularza (cf-turnstile-response)

    Returns:
        bool: True jeśli weryfikacja przeszła, False jeśli nie
    """
    if not is_turnstile_enabled():
        return True

    if not token:
        logger.warning('Turnstile: brak tokenu w żądaniu')
        return False

    secret_key = current_app.config.get('CF_TURNSTILE_SECRET_KEY')

    try:
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            data={
                'secret': secret_key,
                'response': token,
            },
            timeout=5
        )
        result = response.json()

        if result.get('success'):
            return True

        error_codes = result.get('error-codes', [])
        logger.warning(f'Turnstile: weryfikacja nieudana, kody: {error_codes}')
        return False

    except requests.exceptions.Timeout:
        logger.error('Turnstile: timeout przy weryfikacji - przepuszczam (fail-open)')
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f'Turnstile: błąd połączenia - przepuszczam (fail-open): {e}')
        return True
    except Exception as e:
        logger.error(f'Turnstile: nieoczekiwany błąd - przepuszczam (fail-open): {e}')
        return True
