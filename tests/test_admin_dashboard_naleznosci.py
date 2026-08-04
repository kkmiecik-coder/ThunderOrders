"""Kafelek „Do zapłaty" na pulpicie admina nie może liczyć zamówień zamkniętych.

Zamówienie anulowane albo czekające na zwrot nie jest już należnością — nikt
tych pieniędzy nie zapłaci, więc nie mogą podbijać kwoty do rozliczenia.
"""
from decimal import Decimal

import pytest
from flask import template_rendered


def _kontekst_pulpitu(app, client):
    """Zwraca kontekst szablonu z GET /admin/dashboard."""
    zebrane = []

    def zapamietaj(sender, template, context, **extra):
        zebrane.append(context)

    template_rendered.connect(zapamietaj, app)
    try:
        resp = client.get('/admin/dashboard')
        assert resp.status_code == 200
    finally:
        template_rendered.disconnect(zapamietaj, app)

    return zebrane[0]


@pytest.mark.parametrize('status', ['anulowane', 'do_zwrotu', 'zwrocone', 'czesciowo_zwrocone'])
def test_naleznosci_pomijaja_zamkniete_zamowienia(
    app, client, db, make_user, make_order, login, status
):
    login(make_user(role='admin', profile_completed=True))
    make_order(make_user(), total_amount=Decimal('500.00'), status=status)

    kontekst = _kontekst_pulpitu(app, client)

    assert kontekst['revenue']['outstanding_remaining'] == 0


def test_naleznosci_liczy_aktywne_zamowienia(app, client, db, make_user, make_order, login):
    login(make_user(role='admin', profile_completed=True))
    make_order(make_user(), total_amount=Decimal('120.00'), status='oczekujace')
    make_order(make_user(), total_amount=Decimal('900.00'), status='do_zwrotu')

    kontekst = _kontekst_pulpitu(app, client)

    assert kontekst['revenue']['outstanding_remaining'] == 120.0
