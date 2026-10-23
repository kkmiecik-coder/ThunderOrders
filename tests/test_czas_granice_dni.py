"""Granice dni w statystykach, pulpitach i osiągnięciach liczone po POLSKU.

W bazie leży UTC, więc grupowanie po `func.date(col)` dawało dobę UTC: zamówienie z 00:30
czasu polskiego lądowało pod dniem poprzednim. Teraz filtr w SQL to zakres UTC z
`pl_day_bounds_utc`, a kubełki dni/miesięcy liczy Python (`pl_date`).

Punkt odniesienia (lato, CEST = UTC+2):
    2026-07-01 22:30 UTC = 2026-07-02 00:30 PL  -> doba 2 lipca
    2026-07-01 21:30 UTC = 2026-07-01 23:30 PL  -> doba 1 lipca
    2026-07-31 22:30 UTC = 2026-08-01 00:30 PL  -> sierpień
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from flask import template_rendered

UTC = timezone.utc

PO_POLNOCY_PL = datetime(2026, 7, 1, 22, 30, tzinfo=UTC)    # 2.07 00:30 PL
PRZED_POLNOCA_PL = datetime(2026, 7, 1, 21, 30, tzinfo=UTC)  # 1.07 23:30 PL
SIERPIEN_PL = datetime(2026, 7, 31, 22, 30, tzinfo=UTC)     # 1.08 00:30 PL


def _zamroz_dzis(monkeypatch, dzien, *moduly):
    for modul in moduly:
        monkeypatch.setattr(f'{modul}.pl_today', lambda: dzien)


def _admin(make_user, login):
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))


# ---------------------------------------------------------------------------
# utils.timeutil.bucket_by_pl_day
# ---------------------------------------------------------------------------

def test_bucket_by_pl_day_grupuje_po_dobie_polskiej():
    from utils.timeutil import bucket_by_pl_day

    kubelki = bucket_by_pl_day([
        (PRZED_POLNOCA_PL, 'a'),
        (PO_POLNOCY_PL, 'b'),
        (datetime(2026, 7, 2, 10, 0, tzinfo=UTC), 'c'),
    ])

    assert kubelki == {date(2026, 7, 1): ['a'], date(2026, 7, 2): ['b', 'c']}


def test_bucket_by_pl_day_zima_i_zmiana_czasu():
    from utils.timeutil import bucket_by_pl_day

    kubelki = bucket_by_pl_day([
        # zima (CET = UTC+1): 23:30 UTC to już następna doba polska
        (datetime(2026, 1, 15, 23, 30, tzinfo=UTC), 'zima'),
        # 25.10.2026 (zmiana CEST -> CET): 22:30 UTC 24.10 = 00:30 CEST 25.10
        (datetime(2026, 10, 24, 22, 30, tzinfo=UTC), 'start'),
        # ta doba ma 25 h: 22:30 UTC 25.10 = 23:30 CET 25.10
        (datetime(2026, 10, 25, 22, 30, tzinfo=UTC), 'koniec'),
    ])

    assert kubelki == {
        date(2026, 1, 16): ['zima'],
        date(2026, 10, 25): ['start', 'koniec'],
    }


def test_bucket_by_pl_day_pomija_brak_daty_a_naiwna_to_blad():
    from utils.timeutil import bucket_by_pl_day

    assert bucket_by_pl_day([(None, 'x')]) == {}
    with pytest.raises(ValueError):
        bucket_by_pl_day([(datetime(2026, 7, 1, 22, 30), 'naiwny')])


# ---------------------------------------------------------------------------
# Statystyki admina (modules/admin/statistics.py)
# ---------------------------------------------------------------------------

def test_statystyki_przychod_dzis_i_wykres_dzienny_po_polsku(
    client, db, make_user, make_order, login, monkeypatch
):
    _zamroz_dzis(monkeypatch, date(2026, 7, 2), 'modules.admin.statistics')
    _admin(make_user, login)
    klient = make_user()
    make_order(klient, total_amount=Decimal('100.00'), created_at=PO_POLNOCY_PL)
    make_order(klient, total_amount=Decimal('7.00'), created_at=PRZED_POLNOCA_PL)

    dane = client.get('/admin/statistics/api/revenue?range=7d').get_json()

    kpi = {k['label']: k['raw'] for k in dane['kpis']}
    assert kpi['Przychód dziś'] == 100.0
    assert kpi['Przychód ten tydzień'] == 107.0
    assert kpi['Przychód ten miesiąc'] == 107.0
    wykres = dict(zip(dane['charts']['main']['labels'], dane['charts']['main']['values']))
    assert wykres['02.07'] == 100.0
    assert wykres['01.07'] == 7.0
    top = {wiersz[0]: wiersz[2] for wiersz in dane['tables'][0]['rows']}
    assert top == {'2026-07-02': 1, '2026-07-01': 1}


def test_statystyki_zamowienia_per_dzien_po_polsku(
    client, db, make_user, make_order, login, monkeypatch
):
    _zamroz_dzis(monkeypatch, date(2026, 7, 2), 'modules.admin.statistics')
    _admin(make_user, login)
    klient = make_user()
    make_order(klient, created_at=PO_POLNOCY_PL)
    make_order(klient, created_at=PO_POLNOCY_PL)
    make_order(klient, created_at=PRZED_POLNOCA_PL)

    dane = client.get('/admin/statistics/api/orders?range=7d').get_json()

    wykres = dict(zip(dane['charts']['bar']['labels'], dane['charts']['bar']['values']))
    assert wykres['02.07'] == 2
    assert wykres['01.07'] == 1


def test_statystyki_rejestracje_po_polsku(client, db, make_user, login, monkeypatch):
    _zamroz_dzis(monkeypatch, date(2026, 7, 2), 'modules.admin.statistics')
    _admin(make_user, login)
    make_user(created_at=PO_POLNOCY_PL)
    make_user(created_at=PRZED_POLNOCA_PL)

    dane = client.get('/admin/statistics/api/clients?range=7d').get_json()

    wykres = dict(zip(dane['charts']['main']['labels'], dane['charts']['main']['values']))
    assert wykres['02.07'] == 1
    assert wykres['01.07'] == 1
    kpi = {k['label']: k['raw'] for k in dane['kpis']}
    assert kpi['Nowych (ten miesiąc)'] == 2


def test_statystyki_ten_miesiac_od_polskiej_polnocy(
    client, db, make_user, make_order, login, monkeypatch
):
    """30.06 22:30 UTC to w Polsce już 1.07 00:30 - lipiec; 21:30 UTC (23:30 PL) to jeszcze czerwiec."""
    _zamroz_dzis(monkeypatch, date(2026, 7, 2), 'modules.admin.statistics')
    _admin(make_user, login)
    klient = make_user()
    make_order(klient, total_amount=Decimal('5.00'),
               created_at=datetime(2026, 6, 30, 21, 30, tzinfo=UTC))   # 30.06 23:30 PL
    make_order(klient, total_amount=Decimal('50.00'),
               created_at=datetime(2026, 6, 30, 22, 30, tzinfo=UTC))   # 1.07 00:30 PL

    dane = client.get('/admin/statistics/api/revenue?range=7d').get_json()

    kpi = {k['label']: k['raw'] for k in dane['kpis']}
    assert kpi['Przychód ten miesiąc'] == 50.0


# ---------------------------------------------------------------------------
# Pulpit admina (modules/admin/routes.py)
# ---------------------------------------------------------------------------

def _kontekst_pulpitu(app, client):
    zebrane = []

    def zapamietaj(sender, template, context, **extra):
        zebrane.append(context)

    template_rendered.connect(zapamietaj, app)
    try:
        assert client.get('/admin/dashboard').status_code == 200
    finally:
        template_rendered.disconnect(zapamietaj, app)
    return zebrane[0]


def test_pulpit_admina_dzisiaj_po_polsku(app, client, db, make_user, make_order, login, monkeypatch):
    _zamroz_dzis(monkeypatch, date(2026, 7, 2), 'modules.admin.routes')
    _admin(make_user, login)
    klient = make_user()
    make_order(klient, total_amount=Decimal('100.00'), created_at=PO_POLNOCY_PL)
    make_order(klient, total_amount=Decimal('7.00'), created_at=PRZED_POLNOCA_PL)

    kontekst = _kontekst_pulpitu(app, client)

    assert kontekst['orders']['today'] == 1
    assert kontekst['revenue']['today'] == 100.0
    wykres = {p['date']: p['revenue'] for p in kontekst['sales_chart']}
    assert wykres['2026-07-02'] == 100.0
    assert wykres['2026-07-01'] == 7.0


def test_pulpit_admina_wykres_dzienny_po_polsku(client, db, make_user, make_order, login, monkeypatch):
    _zamroz_dzis(monkeypatch, date(2026, 7, 2), 'modules.admin.routes')
    _admin(make_user, login)
    klient = make_user()
    make_order(klient, total_amount=Decimal('100.00'), created_at=PO_POLNOCY_PL)
    make_order(klient, total_amount=Decimal('7.00'), created_at=PRZED_POLNOCA_PL)

    dane = client.get('/admin/dashboard/sales-data?range=7d').get_json()

    wykres = dict(zip(dane['labels'], dane['values']))
    assert wykres['02.07'] == 100.0
    assert wykres['01.07'] == 7.0


def test_pulpit_admina_wykres_miesieczny_po_polsku(client, db, make_user, make_order, login, monkeypatch):
    _zamroz_dzis(monkeypatch, date(2026, 8, 15), 'modules.admin.routes')
    _admin(make_user, login)
    make_order(make_user(), total_amount=Decimal('100.00'), created_at=SIERPIEN_PL)

    dane = client.get('/admin/dashboard/sales-data?range=3m').get_json()

    assert dane['labels'] == ['Cze', 'Lip', 'Sie']
    assert dane['values'] == [0.0, 0.0, 100.0]


# ---------------------------------------------------------------------------
# Pulpit klienta (modules/client)
# ---------------------------------------------------------------------------

def test_wykres_klienta_dzienny_po_polsku(client, db, make_user, make_order, login, monkeypatch):
    _zamroz_dzis(monkeypatch, date(2026, 7, 2), 'modules.client.routes')
    u = make_user(profile_completed=True)
    login(u)
    make_order(u, created_at=PO_POLNOCY_PL)

    dane = client.get('/client/api/chart-data?period=7').get_json()

    wykres = dict(zip(dane['labels'], dane['values']))
    assert wykres['02.07'] == 1
    assert wykres['01.07'] == 0


def test_wykres_klienta_miesieczny_po_polsku(client, db, make_user, make_order, login, monkeypatch):
    _zamroz_dzis(monkeypatch, date(2026, 8, 15), 'modules.client.routes')
    u = make_user(profile_completed=True)
    login(u)
    make_order(u, created_at=SIERPIEN_PL)

    dane = client.get('/client/api/chart-data?period=90').get_json()

    wykres = dict(zip(dane['labels'], dane['values']))
    assert wykres['Sie 2026'] == 1
    assert wykres['Lip 2026'] == 0


def test_serwis_pulpitu_klienta_wykres_po_polsku(db, make_user, make_order, monkeypatch):
    from modules.client.dashboard_service import get_client_dashboard_stats
    _zamroz_dzis(monkeypatch, date(2026, 7, 2), 'modules.client.dashboard_service')
    u = make_user()
    make_order(u, created_at=PO_POLNOCY_PL)

    wykres = get_client_dashboard_stats(u)['chart_data']

    dzienny = dict(zip(wykres['labels'], wykres['values']))
    assert wykres['labels'][-1] == '2026-07-02'
    assert dzienny['2026-07-02'] == 1
    assert dzienny['2026-07-01'] == 0


# ---------------------------------------------------------------------------
# Podsumowanie strony sprzedaży (utils/offer_closure.py)
# ---------------------------------------------------------------------------

def test_podsumowanie_strony_zamowienia_per_dzien_po_polsku(db, make_user, make_order, strona_sprzedazy):
    from utils.offer_closure import get_page_summary
    make_order(make_user(), created_at=PO_POLNOCY_PL, offer_page_id=strona_sprzedazy.id)

    podsumowanie = get_page_summary(strona_sprzedazy.id)

    assert podsumowanie['orders_by_date'] == [{'date': '2026-07-02', 'count': 1}]


# ---------------------------------------------------------------------------
# Osiągnięcia (modules/achievements/checkers.py)
# ---------------------------------------------------------------------------

def _zamroz_teraz(monkeypatch, chwila):
    monkeypatch.setattr('modules.achievements.checkers.utcnow', lambda: chwila)


def test_godzina_zamowienia_po_polsku(db, make_user, monkeypatch):
    from modules.achievements.checkers import METRIC_EVALUATORS
    _zamroz_teraz(monkeypatch, PO_POLNOCY_PL)  # 00:30 PL, 22:30 UTC

    godzina, w_zakresie = METRIC_EVALUATORS['order_hour_range'](make_user(), {'start': 0, 'end': 5}, None)

    assert godzina == 0
    assert w_zakresie is True


def test_weekend_zaczyna_sie_o_polskiej_polnocy(db, make_user, make_order, monkeypatch):
    """Sobota 4.07.2026 zaczyna się o 22:00 UTC w piątek."""
    from modules.achievements.checkers import METRIC_EVALUATORS
    u = make_user()
    make_order(u, created_at=datetime(2026, 7, 3, 21, 30, tzinfo=UTC))   # pt 23:30 PL
    make_order(u, created_at=datetime(2026, 7, 3, 22, 30, tzinfo=UTC))   # sob 00:30 PL
    sprawdz = METRIC_EVALUATORS['orders_in_weekend']

    # sobota 00:45 PL (w UTC wciąż piątek) - weekend już trwa
    _zamroz_teraz(monkeypatch, datetime(2026, 7, 3, 22, 45, tzinfo=UTC))
    assert sprawdz(u, {'threshold': 1}, None) == (1, True)

    # niedziela 00:30 PL (w UTC wciąż sobota) - liczy od soboty 00:00 PL
    _zamroz_teraz(monkeypatch, datetime(2026, 7, 4, 22, 30, tzinfo=UTC))
    assert sprawdz(u, {'threshold': 2}, None) == (1, False)

    # poniedziałek 00:30 PL (w UTC wciąż niedziela) - po weekendzie
    _zamroz_teraz(monkeypatch, datetime(2026, 7, 5, 22, 30, tzinfo=UTC))
    assert sprawdz(u, {'threshold': 1}, None) == (0, False)


# ---------------------------------------------------------------------------
# Kampanie QR (modules/tracking/routes.py)
# ---------------------------------------------------------------------------

def _kampania_z_wizyta(db, admin_id, chwila):
    from modules.tracking.models import QRCampaign, QRVisit
    kampania = QRCampaign(name='K', slug='k', created_by=admin_id)
    db.session.add(kampania)
    db.session.flush()
    db.session.add(QRVisit(campaign_id=kampania.id, visitor_id='v1', is_unique=True, visited_at=chwila))
    db.session.commit()
    return kampania


@pytest.mark.parametrize('granulacja, klucz', [
    ('daily', '2026-07-02'),
    ('hourly', '2026-07-02 00:00'),
    ('minutely', '2026-07-02 00:30'),
    ('weekly', '2026-06-29'),
    ('monthly', '2026-07'),
])
def test_kampania_qr_os_czasu_po_polsku(client, db, make_user, login, granulacja, klucz):
    admin = make_user(role='admin', email='admin@example.com', profile_completed=True)
    login(admin)
    kampania = _kampania_z_wizyta(db, admin.id, PO_POLNOCY_PL)

    dane = client.get(
        f'/admin/qr-tracking/{kampania.id}/api/stats'
        f'?date_from=2026-07-02&date_to=2026-07-02&granularity={granulacja}'
    ).get_json()

    os_czasu = {p['date']: p['total'] for p in dane['timeline']}
    assert os_czasu[klucz] == 1
    assert sum(os_czasu.values()) == 1


def test_kampania_qr_tydzien_od_polskiego_poniedzialku(client, db, make_user, login):
    """Pn 6.07 00:30 PL to w UTC jeszcze niedziela 5.07 - tydzień od 6.07, nie od 29.06."""
    admin = make_user(role='admin', email='admin@example.com', profile_completed=True)
    login(admin)
    kampania = _kampania_z_wizyta(db, admin.id, datetime(2026, 7, 5, 22, 30, tzinfo=UTC))

    dane = client.get(
        f'/admin/qr-tracking/{kampania.id}/api/stats'
        f'?date_from=2026-07-06&date_to=2026-07-06&granularity=weekly'
    ).get_json()

    os_czasu = {p['date']: p['total'] for p in dane['timeline']}
    assert os_czasu['2026-07-06'] == 1
    assert os_czasu.get('2026-06-29', 0) == 0
