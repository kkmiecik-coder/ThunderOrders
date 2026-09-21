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


def test_exclusive_veteran_zlicza_rozne_dropy(app, db, make_user, make_order):
    """Trzy zamówienia z trzech różnych dropów odblokowują odznakę."""
    konfig = _konfig('exclusive-veteran')
    autor = make_user(role='admin', email='autor@example.com')
    klient = make_user(email='klient@example.com')

    for nazwa in ('Drop 1', 'Drop 2'):
        make_order(klient, order_type='exclusive',
                   offer_page_id=_strona_sprzedazy(db, autor, nazwa).id)

    ile, spelnia = get_metric_value(klient, konfig['metric'], konfig)
    assert (ile, spelnia) == (2, False)

    make_order(klient, order_type='exclusive',
               offer_page_id=_strona_sprzedazy(db, autor, 'Drop 3').id)

    ile, spelnia = get_metric_value(klient, konfig['metric'], konfig)
    assert (ile, spelnia) == (3, True)


def test_exclusive_veteran_nie_liczy_tej_samej_strony_dwa_razy(app, db, make_user, make_order):
    konfig = _konfig('exclusive-veteran')
    autor = make_user(role='admin', email='autor@example.com')
    klient = make_user(email='klient@example.com')
    strona = _strona_sprzedazy(db, autor, 'Drop 1')

    for _ in range(3):
        make_order(klient, order_type='exclusive', offer_page_id=strona.id)

    assert get_metric_value(klient, konfig['metric'], konfig) == (1, False)


def test_odznaki_exclusive_nie_licza_preorderow(app, db, make_user, make_order):
    """Pre-order to nie drop — odznaki exclusive-* mają go pomijać.

    Wcześniej `exclusive_orders` liczyło każde zamówienie ze stroną sprzedaży,
    a taką stronę ma 3007 z 3008 zamówień na produkcji. Skutek: exclusive-*
    miało co do jednej osoby tych samych posiadaczy co orders-* (185/81/61/40),
    czyli osiem odznak nagradzało to samo.
    """
    autor = make_user(role='admin', email='autor@example.com')
    klient = make_user(email='klient@example.com')

    for nazwa in ('Pre 1', 'Pre 2', 'Pre 3'):
        make_order(klient, order_type='pre_order',
                   offer_page_id=_strona_sprzedazy(db, autor, nazwa).id)

    konfig_liczba = _konfig('exclusive-first')
    assert get_metric_value(klient, konfig_liczba['metric'], konfig_liczba) == (0, False)

    konfig_strony = _konfig('exclusive-veteran')
    assert get_metric_value(klient, konfig_strony['metric'], konfig_strony) == (0, False)

    # …a zwykła drabinka zamówień dalej je widzi.
    konfig_zamowien = _konfig('first-order')
    assert get_metric_value(klient, konfig_zamowien['metric'], konfig_zamowien) == (3, True)


def test_drabinki_maja_spojne_poziomy():
    """W każdej drabince rosnący `tier` musi znaczyć rosnący próg.

    Poziomy dokładane w kolejnych iteracjach łatwo wstawić w złej kolejności,
    a galeria pokaże wtedy „wyższą" odznakę jako łatwiejszą od poprzedniej.
    """
    grupy = {}
    for odznaka in ACHIEVEMENTS:
        grupa = odznaka.get('tier_group')
        if not grupa:
            continue
        prog = odznaka['trigger_config'].get('threshold')
        grupy.setdefault(grupa, []).append((odznaka['tier'], odznaka['slug'], prog))

    for grupa, poziomy in grupy.items():
        poziomy.sort()
        numery = [t for t, _, _ in poziomy]
        assert numery == list(range(1, len(numery) + 1)), (
            f'Drabinka {grupa} ma dziurę albo duplikat w numeracji tier: {poziomy}'
        )
        progi = [p for _, _, p in poziomy]
        assert progi == sorted(progi), (
            f'Drabinka {grupa} ma progi niezgodne z kolejnością poziomów: {poziomy}'
        )


def test_kazda_odznaka_z_progiem_nalezy_do_drabinki():
    """Odznaka progowa bez `tier_group` wypada z drabinki w galerii.

    Tak wyglądały wcześniej najwyższe progi pięciu z sześciu drabinek
    (orders-50, orders-100, collection-100, member-730d, spent-10000) —
    miały tier=None i traciły związek ze swoją grupą.
    """
    BEZ_DRABINKI = {          # progi jednorazowe, świadomie poza drabinką
        'bulk-order', 'mega-order', 'repeat-week', 'photos-10', 'photos-50',
        'weekend-warrior', 'first-address',
    }
    sieroty = [
        a['slug'] for a in ACHIEVEMENTS
        if a['trigger_config'].get('threshold') is not None
        and not a.get('tier_group')
        and a['slug'] not in BEZ_DRABINKI
    ]
    assert not sieroty, f'Odznaki progowe bez drabinki: {sieroty}'
