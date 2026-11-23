"""Pomocnicze funkcje sesji webowej (Flask-Login)."""
from flask import current_app, request, session
from flask_login.config import COOKIE_NAME


def refresh_session_after_password_change(user):
    """Po zmianie własnego hasła: przepisz bieżącą sesję na nowy odcisk hasła.

    Identyfikator sesji zawiera odcisk hasła (User.get_id), więc po zmianie hasła
    wszystkie sesje by wygasły — także ta, z której użytkownik zmienia hasło. Tę jedną
    odświeżamy; jeśli miał „zapamiętaj mnie", ciasteczko zostaje wystawione na nowo.
    """
    session['_user_id'] = user.get_id()
    cookie_name = current_app.config.get('REMEMBER_COOKIE_NAME', COOKIE_NAME)
    if cookie_name in request.cookies:
        session['_remember'] = 'set'
