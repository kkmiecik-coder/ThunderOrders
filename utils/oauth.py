"""
OAuth Helper - Google & Facebook login
Konfiguracja Authlib OAuth registry z dwoma providerami
"""

from authlib.integrations.flask_client import OAuth

oauth = OAuth()


def init_oauth(app):
    """
    Inicjalizuje OAuth z providerami Google i Facebook.
    Wywoływane w app.py przy tworzeniu aplikacji.
    """
    oauth.init_app(app)

    # Google OAuth 2.0
    if app.config.get('GOOGLE_CLIENT_ID'):
        oauth.register(
            name='google',
            client_id=app.config['GOOGLE_CLIENT_ID'],
            client_secret=app.config['GOOGLE_CLIENT_SECRET'],
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={
                'scope': 'openid email profile',
            },
        )

    # Facebook OAuth 2.0
    if app.config.get('FACEBOOK_CLIENT_ID'):
        oauth.register(
            name='facebook',
            client_id=app.config['FACEBOOK_CLIENT_ID'],
            client_secret=app.config['FACEBOOK_CLIENT_SECRET'],
            authorize_url='https://www.facebook.com/v19.0/dialog/oauth',
            access_token_url='https://graph.facebook.com/v19.0/oauth/access_token',
            api_base_url='https://graph.facebook.com/v19.0/',
            client_kwargs={
                'scope': 'email public_profile',
            },
        )
