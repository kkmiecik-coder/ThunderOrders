"""Testy serwisu statystyk dashboardu klienta (E5, D3=(a)).

Serwis `get_client_dashboard_stats(user)` to wspólne źródło prawdy dla webowej
trasy `dashboard()` oraz mobilnego `GET /dashboard`. Zwraca surowe dane
(obiekty Order + Decimale + liczby) — mapowanie na koperty robią wywołujący.
"""
from decimal import Decimal


def test_dashboard_stats_counts(db, make_user, make_order):
    from modules.client.dashboard_service import get_client_dashboard_stats
    u = make_user()
    make_order(u, status='nowe')
    make_order(u, status='oczekujace')
    make_order(u, status='dostarczone')
    make_user()  # inny user bez zamówień
    stats = get_client_dashboard_stats(u)
    assert stats['orders']['all'] == 3
    assert stats['orders']['in_progress'] == 2          # nowe + oczekujace
    assert stats['orders']['delivered'] == 1
    assert len(stats['recent_orders']['visible']) == 3
    assert 'labels' in stats['chart_data'] and 'values' in stats['chart_data']


def test_dashboard_stats_to_pay(db, make_user, make_order):
    from modules.client.dashboard_service import get_client_dashboard_stats
    u = make_user()
    make_order(u, total_amount=100.00, order_type='on_hand', shipping_cost=Decimal('20.00'))
    stats = get_client_dashboard_stats(u)
    # on_hand total_to_pay = 100 + 20 = 120; paid 0
    assert stats['payment']['to_pay'] == Decimal('120.00')
    assert stats['payment']['paid'] == Decimal('0.00')


def test_dashboard_stats_isolated_per_user(db, make_user, make_order):
    from modules.client.dashboard_service import get_client_dashboard_stats
    a, b = make_user(), make_user()
    make_order(a); make_order(b); make_order(b)
    assert get_client_dashboard_stats(a)['orders']['all'] == 1
    assert get_client_dashboard_stats(b)['orders']['all'] == 2


import pytest


@pytest.mark.parametrize('status', ['anulowane', 'do_zwrotu', 'zwrocone', 'czesciowo_zwrocone'])
def test_dashboard_to_pay_pomija_zamkniete_zamowienia(db, make_user, make_order, status):
    """Anulowane zamówienie i takie do zwrotu nie mogą wisieć klientowi w 'do zapłaty'."""
    from modules.client.dashboard_service import get_client_dashboard_stats

    u = make_user()
    make_order(u, total_amount=100.00, order_type='on_hand',
               shipping_cost=Decimal('20.00'), status=status)

    stats = get_client_dashboard_stats(u)

    assert stats['payment']['to_pay'] == Decimal('0.00')


def test_dashboard_to_pay_liczy_tylko_aktywne(db, make_user, make_order):
    """Przy mieszance liczy się wyłącznie zamówienie, które klient realnie ma zapłacić."""
    from modules.client.dashboard_service import get_client_dashboard_stats

    u = make_user()
    make_order(u, total_amount=100.00, order_type='on_hand',
               shipping_cost=Decimal('20.00'), status='oczekujace')
    make_order(u, total_amount=500.00, order_type='on_hand',
               shipping_cost=Decimal('50.00'), status='anulowane')
    make_order(u, total_amount=300.00, order_type='on_hand',
               shipping_cost=Decimal('30.00'), status='do_zwrotu')

    stats = get_client_dashboard_stats(u)

    assert stats['payment']['to_pay'] == Decimal('120.00')
