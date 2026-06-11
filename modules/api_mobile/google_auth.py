"""Weryfikacja Google ID tokenu z aplikacji mobilnej."""

from flask import current_app
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests


def verify_google_id_token(token):
    """Zwraca dict z danymi (email, sub, given_name, family_name) albo None gdy niepoprawny."""
    try:
        info = google_id_token.verify_oauth2_token(
            token, google_requests.Request()
        )
    except ValueError:
        return None

    allowed = current_app.config.get('GOOGLE_OAUTH_CLIENT_IDS') or []
    if allowed and info.get('aud') not in allowed:
        return None
    if info.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
        return None
    if not info.get('email_verified'):
        return None
    return info
