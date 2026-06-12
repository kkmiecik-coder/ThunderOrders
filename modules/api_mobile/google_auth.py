"""Weryfikacja Google ID tokenu z aplikacji mobilnej."""

from flask import current_app
from google.auth.exceptions import GoogleAuthError
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests


def verify_google_id_token(token):
    """Zwraca dict z danymi (email, sub, given_name, family_name) albo None gdy niepoprawny."""
    allowed = current_app.config.get('GOOGLE_OAUTH_CLIENT_IDS') or []
    if not allowed:
        # Fail-closed: brak skonfigurowanych client ID = logowanie Google wyłączone.
        # Pusta lista oznaczałaby brak weryfikacji audience (tokeny z dowolnej apki Google).
        current_app.logger.error(
            'GOOGLE_OAUTH_CLIENT_IDS nie skonfigurowane — odrzucam logowanie Google (fail-closed)')
        return None

    try:
        info = google_id_token.verify_oauth2_token(
            token, google_requests.Request()
        )
    except (ValueError, GoogleAuthError):
        # ValueError: token niepoprawny/wygasły. GoogleAuthError (w tym TransportError
        # przy awarii pobierania certów Google): traktujemy jak nieudaną weryfikację,
        # żeby klient dostał czyste 401 zamiast HTML-owego 500.
        return None

    if info.get('aud') not in allowed:
        return None
    if info.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
        return None
    if not info.get('email_verified'):
        return None
    return info
