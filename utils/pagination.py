"""
Wspólna obsługa „ile pozycji na stronie" dla list paginowanych.

Wybór użytkownika żyje w sesji logowania: raz ustawiony trzyma się przy
przechodzeniu między stronami, a wylogowanie go kasuje (patrz
`clear_per_page_preferences`, wołane w modules/auth/routes.py::logout).
Parametr `?per_page=` w URL nadpisuje zapamiętaną wartość, więc link
z konkretnym ustawieniem da się wysłać komuś innemu.

Każda lista ma własny klucz (`offers`, `wms_shipping`, ...) — inaczej ustawienie
500 na stronach sprzedaży wywracałoby też listę zleceń wysyłki.
"""
from flask import request, session

# Opcje w selektorze; 'all' renderuje się jako „Wszystkie".
PER_PAGE_ALL = 'all'
PER_PAGE_OPTIONS = [10, 20, 30, 40, 50, 100, 150, 200, 300, 500]
PER_PAGE_CHOICES = PER_PAGE_OPTIONS + [PER_PAGE_ALL]

_SESSION_PREFIX = 'per_page:'


def _normalize(raw):
    """Surowa wartość -> liczba z listy opcji albo 'all'. None, gdy niedozwolona."""
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip().lower() == PER_PAGE_ALL:
        return PER_PAGE_ALL
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value in PER_PAGE_OPTIONS else None


def resolve_per_page(key, default=20):
    """
    Zwraca wybór dla listy `key`: liczbę z PER_PAGE_OPTIONS albo PER_PAGE_ALL.

    Kolejność: `?per_page=` z URL (i zapis do sesji) -> zapamiętane w sesji ->
    `default`. Wartość spoza listy jest ignorowana — bez tego ktoś mógłby
    parametrem w adresie kazać bazie wyciągnąć dowolnie dużą stronę.
    """
    from_url = _normalize(request.args.get('per_page'))
    if from_url is not None:
        session[_SESSION_PREFIX + key] = from_url
        return from_url

    stored = _normalize(session.get(_SESSION_PREFIX + key))
    return stored if stored is not None else default


def paginate_with_choice(query, page, per_page_choice):
    """
    Paginuje zapytanie zgodnie z wyborem użytkownika.

    Dla „Wszystkie" wynik ląduje na jednej stronie. `per_page` nie może być 0
    (Flask-SQLAlchemy odrzuca zero), więc przy pustej liście używamy 1 —
    pagination.total i tak wychodzi wtedy 0.
    """
    if per_page_choice == PER_PAGE_ALL:
        return query.paginate(page=1, per_page=max(query.count(), 1), error_out=False)
    return query.paginate(page=page, per_page=per_page_choice, error_out=False)


class ListPagination:
    """
    Paginacja gotowej listy — odpowiednik obiektu Pagination dla danych, których
    nie da się wyrazić zapytaniem (np. „produkty do zamówienia" liczone
    w Pythonie z kilku źródeł). Wystawia tyle, ile potrzebuje
    components/_pagination.html.
    """

    def __init__(self, items, page, per_page):
        self.total = len(items)
        self.per_page = max(per_page, 1)
        self.pages = max((self.total + self.per_page - 1) // self.per_page, 1) if self.total else 0

        # Numer strony poza zakresem (np. po zawężeniu filtra) cofamy na ostatnią.
        self.page = min(max(page, 1), self.pages) if self.pages else 1

        start = (self.page - 1) * self.per_page
        self.items = items[start:start + self.per_page]

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None


def paginate_list(items, page, per_page_choice):
    """Jak paginate_with_choice, ale dla zwykłej listy."""
    if per_page_choice == PER_PAGE_ALL:
        return ListPagination(items, 1, max(len(items), 1))
    return ListPagination(items, page, per_page_choice)


def clear_per_page_preferences():
    """Kasuje zapamiętane ustawienia — wołane przy wylogowaniu."""
    for key in [k for k in session if k.startswith(_SESSION_PREFIX)]:
        session.pop(key, None)
