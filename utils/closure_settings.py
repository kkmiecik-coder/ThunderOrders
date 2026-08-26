"""Kontrakt ustawień domykania oferty — nazwy kluczy Settings w jednym miejscu.

Powód istnienia tego modułu: rename z `b7b10ea` (2026-03-31) przemianował ten sam
klucz na dwa sposoby. Panel poszedł za nazwą modułu (`offers_closure_status_*`),
silnik za nazwą pliku (`offer_closure_status_*`). Obie strony działały „poprawnie"
w izolacji, więc nikt niczego nie zauważył przez pięć miesięcy: ustawienia z panelu
były ignorowane, a maile o anulowaniu nie wyszły ani razu.

Dopóki nazwy kluczy były literałami rozsypanymi po trzech plikach, taki rozjazd był
kwestią czasu. Teraz zapis, odczyt i walidacja biorą je stąd — kolejny rename albo
zmieni wszystkie strony naraz, albo nie skompiluje się wcale.

Kanoniczna forma to `offers_*` (mnoga), zgodna z resztą nazewnictwa modułu:
`admin.offers_settings`, `update_offers_closure_settings`, `templates/admin/offers/`.
"""

# Kategoria realizacji zamówienia -> klucz w tabeli settings
CLOSURE_STATUS_KEYS = {
    'fully_fulfilled': 'offers_closure_status_fully_fulfilled',
    'partially_fulfilled': 'offers_closure_status_partially_fulfilled',
    'not_fulfilled': 'offers_closure_status_not_fulfilled',
}

# Wartości używane, gdy admin nigdy nie ruszył ustawień albo zapisany slug jest martwy.
# Muszą się zgadzać z tym, co formularz pokazuje jako domyślne (modules/admin/offers.py).
CLOSURE_STATUS_DEFAULTS = {
    'fully_fulfilled': 'oczekujace',
    'partially_fulfilled': 'oczekujace',
    'not_fulfilled': 'anulowane',
}


def active_status_slugs():
    """Slugi statusów, które wolno zapisać w ustawieniach domykania."""
    from modules.orders.models import OrderStatus

    return {s.slug for s in OrderStatus.query.filter_by(is_active=True).all()}


def validate_closure_statuses(wybrane):
    """Sprawdza slugi przed zapisem. Zwraca listę komunikatów o błędach (pusta = OK).

    `orders.status` to klucz obcy do słownika statusów, nie dowolny string. Slug spoza
    słownika przechodzi przez zapis bez szemrania, a wywala się dopiero przy domykaniu
    oferty — w środku transakcji, która rolluje alokację setów i wyzerowane ceny,
    zostawiając admina z błędem 500 przy operacji opisanej jako nieodwracalna.
    """
    dozwolone = active_status_slugs()
    bledy = []
    for kategoria, slug in wybrane.items():
        if not slug:
            bledy.append('Wszystkie statusy muszą być wybrane.')
        elif slug not in dozwolone:
            bledy.append(f'Status "{slug}" nie istnieje lub jest nieaktywny.')
    return bledy


def get_closure_statuses():
    """Zwraca {kategoria: slug} do użycia przy domykaniu oferty.

    Slug, którego nie ma już w słowniku (status zdezaktywowany po zapisie ustawień),
    schodzi na wartość domyślną i zostawia ślad w logu. Lepiej domknąć ofertę
    ze statusem domyślnym niż wywrócić całą transakcję na kluczu obcym.
    """
    from flask import current_app
    from modules.auth.models import Settings

    zapisane = {
        s.key: s.value
        for s in Settings.query.filter(Settings.key.in_(CLOSURE_STATUS_KEYS.values())).all()
    }
    dozwolone = active_status_slugs()

    wynik = {}
    for kategoria, klucz in CLOSURE_STATUS_KEYS.items():
        domyslny = CLOSURE_STATUS_DEFAULTS[kategoria]
        slug = zapisane.get(klucz) or domyslny
        if slug not in dozwolone:
            current_app.logger.warning(
                'Ustawienie domykania oferty %s wskazuje na nieaktywny status %r — '
                'używam domyślnego %r', klucz, slug, domyslny
            )
            slug = domyslny
        wynik[kategoria] = slug
    return wynik
