"""
Help Routes - Pomoc
====================

Routes for the client help center.
"""

from flask import render_template, abort
from flask_login import login_required
from modules.client import client_bp


HELP_CATEGORIES = [
    {
        'slug': 'orders',
        'name': 'Zamówienia',
        'icon': 'orders',
        'articles': [
            {'slug': 'exclusive-pages', 'title': 'Jak działają strony Exclusive'},
            {'slug': 'place-order', 'title': 'Jak złożyć zamówienie Exclusive'},
            {'slug': 'order-statuses', 'title': 'Statusy zamówień — co oznaczają'},
        ]
    },
    {
        'slug': 'payments',
        'name': 'Płatności',
        'icon': 'payment',
        'articles': [
            {'slug': 'payment-confirmation', 'title': 'Jak przesłać potwierdzenie płatności'},
            {'slug': 'payment-stages', 'title': 'Etapy płatności (zamówienia exclusive)'},
        ]
    },
    {
        'slug': 'shipping',
        'name': 'Wysyłka',
        'icon': 'truck',
        'articles': [
            {'slug': 'shipping-addresses', 'title': 'Zarządzanie adresami dostawy'},
            {'slug': 'shipping-request', 'title': 'Jak zlecić wysyłkę'},
            {'slug': 'tracking', 'title': 'Śledzenie przesyłki'},
        ]
    },
    {
        'slug': 'account',
        'name': 'Konto',
        'icon': 'user',
        'articles': [
            {'slug': 'profile', 'title': 'Ustawienia profilu'},
            {'slug': 'push-notifications', 'title': 'Powiadomienia'},
            {'slug': 'collection', 'title': 'Moja kolekcja'},
            {'slug': 'achievements', 'title': 'Osiągnięcia'},
            {'slug': 'pwa-install', 'title': 'Aplikacja na telefon'},
        ]
    },
]


def _get_all_articles():
    """Return a flat list of (category, article) tuples in order."""
    result = []
    for category in HELP_CATEGORIES:
        for article in category['articles']:
            result.append((category, article))
    return result


def find_article(slug):
    """Find an article by slug. Returns (category, article, prev_article, next_article) or None."""
    all_articles = _get_all_articles()
    for i, (category, article) in enumerate(all_articles):
        if article['slug'] == slug:
            prev_article = all_articles[i - 1][1] if i > 0 else None
            next_article = all_articles[i + 1][1] if i < len(all_articles) - 1 else None
            return category, article, prev_article, next_article
    return None


@client_bp.route('/help')
@login_required
def help_index():
    """Help center index page."""
    return render_template(
        'client/help/index.html',
        categories=HELP_CATEGORIES
    )


@client_bp.route('/help/<slug>')
@login_required
def help_article(slug):
    """Individual help article page."""
    result = find_article(slug)
    if result is None:
        abort(404)

    category, article, prev_article, next_article = result

    return render_template(
        f'client/help/articles/{slug}.html',
        category=category,
        article=article,
        prev_article=prev_article,
        next_article=next_article,
        categories=HELP_CATEGORIES
    )
