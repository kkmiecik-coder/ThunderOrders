"""Odznaki — spójność metryk z seeda z funkcjami liczącymi.

Regresja: po przemianowaniu „Exclusive" na „Oferty" (b7b10ea) metryka
`distinct_exclusive_pages` zniknęła z `METRIC_EVALUATORS` (została jako
`distinct_offer_pages`), ale seed odznaki `exclusive-veteran` dalej prosił o starą
nazwę. `get_metric_value` na nieznaną metrykę zwraca po cichu `(0, False)` — bez
wyjątku, bez logu — więc odznaka nigdy nie odblokowała się nikomu i nikt tego nie
zauważył przez pół roku. Pierwszy test pilnuje tego dla WSZYSTKICH odznak naraz,
bo cicha ścieżka błędu powtórzy się przy każdej kolejnej zmianie nazwy.
"""

import pytest

from modules.achievements.checkers import METRIC_EVALUATORS, get_metric_value
from modules.achievements.seed import ACHIEVEMENTS


@pytest.mark.parametrize(
    'odznaka',
    ACHIEVEMENTS,
    ids=[a['slug'] for a in ACHIEVEMENTS],
)
def test_kazda_odznaka_ma_funkcje_liczaca(odznaka):
    metryka = odznaka['trigger_config'].get('metric')

    assert metryka in METRIC_EVALUATORS, (
        f"Odznaka '{odznaka['slug']}' prosi o metrykę '{metryka}', której nie ma "
        f'w METRIC_EVALUATORS — nigdy się nie odblokuje.'
    )


def _konfig(slug):
    return next(a['trigger_config'] for a in ACHIEVEMENTS if a['slug'] == slug)


def _strona_sprzedazy(db, autor, nazwa):
    from modules.offers.models import OfferPage

    strona = OfferPage(name=nazwa, token=OfferPage.generate_token(),
                       status='active', created_by=autor.id)
    db.session.add(strona)
    db.session.commit()
    return strona


def test_exclusive_veteran_zlicza_rozne_strony_sprzedazy(app, db, make_user, make_order):
    """Trzy zamówienia z trzech różnych stron sprzedaży odblokowują odznakę."""
    konfig = _konfig('exclusive-veteran')
    autor = make_user(role='admin', email='autor@example.com')
    klient = make_user(email='klient@example.com')

    for nazwa in ('Drop 1', 'Drop 2'):
        make_order(klient, offer_page_id=_strona_sprzedazy(db, autor, nazwa).id)

    ile, spelnia = get_metric_value(klient, konfig['metric'], konfig)
    assert (ile, spelnia) == (2, False)

    make_order(klient, offer_page_id=_strona_sprzedazy(db, autor, 'Drop 3').id)

    ile, spelnia = get_metric_value(klient, konfig['metric'], konfig)
    assert (ile, spelnia) == (3, True)


def test_exclusive_veteran_nie_liczy_tej_samej_strony_dwa_razy(app, db, make_user, make_order):
    konfig = _konfig('exclusive-veteran')
    autor = make_user(role='admin', email='autor@example.com')
    klient = make_user(email='klient@example.com')
    strona = _strona_sprzedazy(db, autor, 'Drop 1')

    for _ in range(3):
        make_order(klient, offer_page_id=strona.id)

    assert get_metric_value(klient, konfig['metric'], konfig) == (1, False)
