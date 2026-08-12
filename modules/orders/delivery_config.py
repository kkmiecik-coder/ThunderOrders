"""Konfiguracja potwierdzeń dostawy (task 869efhwph).

Sześć wartości trzymanych w tabeli settings, nie w osobnej tabeli reguł jak przy
przypomnieniach o płatnościach — tam regułą jest wiersz (można ich mieć wiele), tu
mamy pojedyncze liczby.

Cała obrona przed śmieciem w bazie jest tutaj, w jednym miejscu: ustawienie zapisane
ręcznie albo przez starszą wersję UI nie może wywrócić crona.
"""
from modules.auth.models import Settings

DOMYSLNE = {
    'reminder_enabled': True,
    'reminder_days': 3,
    'autocomplete_enabled': True,
    'autocomplete_days': 10,
    'autocomplete_batch': 50,
    'review_window_days': 30,
}

# Klucz w tabeli settings dla każdej pozycji konfiguracji.
KLUCZE = {
    'reminder_enabled': 'delivery_reminder_enabled',
    'reminder_days': 'delivery_reminder_days',
    'autocomplete_enabled': 'delivery_autocomplete_enabled',
    'autocomplete_days': 'delivery_autocomplete_days',
    'autocomplete_batch': 'delivery_autocomplete_batch',
    'review_window_days': 'delivery_review_window_days',
}

# Liczba dni ani wielkość porcji nie mogą zejść poniżej 1 — zero dni oznaczałoby
# domykanie paczek w chwili wysyłki, a porcja zero zatrzymałaby automat na zawsze.
MINIMUM = 1


def _jako_bool(wartosc, domyslna):
    if isinstance(wartosc, bool):
        return wartosc
    if wartosc is None:
        return domyslna
    return str(wartosc).strip().lower() in ('1', 'true', 'yes', 'on')


def _jako_int(wartosc, domyslna):
    try:
        liczba = int(wartosc)
    except (TypeError, ValueError):
        return domyslna
    return max(MINIMUM, liczba)


def pobierz_konfig_dostawy():
    """Zwraca komplet ustawień dostawy z wartościami domyślnymi tam, gdzie brak wpisu."""
    konfig = {}
    for pole, klucz in KLUCZE.items():
        domyslna = DOMYSLNE[pole]
        try:
            # Settings.get_value() dla type='integer' woła int(setting.value) bez
            # obsługi wyjątku — wpis zapisany ręcznie albo przez starszą wersję UI
            # z nieliczbową wartością rzuca tu ValueError, zanim _jako_int w ogóle
            # dostanie szansę zadziałać. Cron nie może się na tym wywrócić, więc
            # dowolny błąd odczytu pojedynczego klucza schodzi na wartość domyślną.
            surowa = Settings.get_value(klucz, None)
        except (ValueError, TypeError):
            surowa = None
        if isinstance(domyslna, bool):
            konfig[pole] = _jako_bool(surowa, domyslna)
        else:
            konfig[pole] = _jako_int(surowa, domyslna)
    return konfig
