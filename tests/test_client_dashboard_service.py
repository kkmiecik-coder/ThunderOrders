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
