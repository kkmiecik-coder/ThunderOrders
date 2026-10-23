"""Wejście czasu z formularzy: admin zawsze wpisuje czas polski, w bazie ląduje UTC.

Formularze edycji muszą pokazywać zapisaną chwilę z powrotem w czasie polskim —
inaczej każdy zapis bez dotykania pola przesuwa termin o 1–2 h (pole wypełnione
zegarem UTC, a zapis czyta je jako czas polski).
"""
import re
from datetime import datetime, timezone


UTC = timezone.utc

# Lato (CEST, UTC+2) i zima (CET, UTC+1)
LATO_UTC = datetime(2026, 7, 1, 18, 0, tzinfo=UTC)
LATO_PL = '2026-07-01T20:00'
ZIMA_UTC = datetime(2026, 1, 15, 19, 0, tzinfo=UTC)
ZIMA_PL = '2026-01-15T20:00'


def _admin(make_user):
    return make_user(role='admin', email='admin@example.com', profile_completed=True)


def _wartosc_pola(html, wzorzec):
    m = re.search(wzorzec, html, re.S)
    assert m, f'nie znaleziono pola: {wzorzec}'
    return m.group(1)


# ---------------------------------------------------------------------------
# Filtr format_datetime_local
# ---------------------------------------------------------------------------

def test_format_datetime_local(app):
    f = app.jinja_env.filters['format_datetime_local']
    assert f(LATO_UTC) == LATO_PL
    assert f(ZIMA_UTC) == ZIMA_PL
    assert f(None) == ''


def test_format_datetime_local_naiwny_to_blad(app):
    import pytest
    f = app.jinja_env.filters['format_datetime_local']
    with pytest.raises(ValueError):
        f(datetime(2026, 7, 1, 20, 0))


# ---------------------------------------------------------------------------
# Strony sprzedaży (offers)
# ---------------------------------------------------------------------------

def _strona(db, admin_id, **kw):
    from modules.offers.models import OfferPage
    p = OfferPage(name='P', token=OfferPage.generate_token(), status='draft',
                  created_by=admin_id, **kw)
    db.session.add(p)
    db.session.commit()
    return p


def test_oferta_start_z_formularza_lato(db, client, make_user, login):
    admin = _admin(make_user)
    login(admin)
    p = _strona(db, admin.id)
    resp = client.post(f'/admin/offers/{p.id}/save', json={'starts_at': LATO_PL, 'ends_at': LATO_PL})
    assert resp.status_code == 200
    db.session.refresh(p)
    assert p.starts_at == LATO_UTC
    assert p.ends_at == LATO_UTC


def test_oferta_start_z_formularza_zima(db, client, make_user, login):
    admin = _admin(make_user)
    login(admin)
    p = _strona(db, admin.id)
    resp = client.post(f'/admin/offers/{p.id}/save', json={'starts_at': ZIMA_PL})
    assert resp.status_code == 200
    db.session.refresh(p)
    assert p.starts_at == ZIMA_UTC


def test_oferta_tworzenie_z_datami(db, client, make_user, login):
    from modules.offers.models import OfferPage
    login(_admin(make_user))
    client.post('/admin/offers/create', data={
        'name': 'Drop lato', 'page_type': 'exclusive',
        'starts_at': LATO_PL, 'ends_at': '2026-07-02T20:00',
    })
    p = OfferPage.query.filter_by(name='Drop lato').first()
    assert p is not None
    assert p.starts_at == LATO_UTC
    assert p.ends_at == datetime(2026, 7, 2, 18, 0, tzinfo=UTC)


def test_oferta_edycja_round_trip(db, client, make_user, login):
    """Pole wypełnione z bazy i odesłane bez zmian nie przesuwa terminu."""
    admin = _admin(make_user)
    login(admin)
    p = _strona(db, admin.id, starts_at=LATO_UTC, ends_at=ZIMA_UTC.replace(year=2027))
    html = client.get(f'/admin/offers/{p.id}/edit').get_data(as_text=True)
    start = _wartosc_pola(html, r'id="startsAt"[^>]*value="([^"]*)"')
    koniec = _wartosc_pola(html, r'id="endsAt"[^>]*value="([^"]*)"')
    assert start == LATO_PL

    client.post(f'/admin/offers/{p.id}/save', json={'starts_at': start, 'ends_at': koniec})
    db.session.refresh(p)
    assert p.starts_at == LATO_UTC
    assert p.ends_at == ZIMA_UTC.replace(year=2027)


def test_oferty_masowe_daty(db, client, make_user, login):
    admin = _admin(make_user)
    login(admin)
    p = _strona(db, admin.id)
    resp = client.post('/admin/offers/bulk/set-dates', json={
        'page_ids': [p.id], 'field': 'ends_at', 'value': ZIMA_PL})
    assert resp.status_code == 200, resp.get_json()
    db.session.refresh(p)
    assert p.ends_at == ZIMA_UTC


def test_oferty_masowe_daty_odrzuca_smieci(db, client, make_user, login):
    admin = _admin(make_user)
    login(admin)
    p = _strona(db, admin.id)
    resp = client.post('/admin/offers/bulk/set-dates', json={
        'page_ids': [p.id], 'field': 'ends_at', 'value': '2026-01-15T20:00+09:00'})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Round-tripy formularzy edycji (prefill musi być polski)
# ---------------------------------------------------------------------------

def test_zadanie_termin_round_trip(db, client, make_user, login):
    from modules.admin.models import AdminTask
    admin = _admin(make_user)
    login(admin)
    t = AdminTask(name='Zadanie', created_by=admin.id, due_date=LATO_UTC)
    db.session.add(t)
    db.session.commit()

    dane = client.get(f'/admin/tasks/{t.id}').get_json()
    # Pole formularza dostaje polski zegar, wyświetlanie - chwilę z `Z`
    assert dane['task']['due_date_input'] == LATO_PL
    assert dane['task']['due_date'] == '2026-07-01T18:00:00Z'

    resp = client.post(f'/admin/tasks/{t.id}/update', data={
        'name': 'Zadanie', 'due_date': dane['task']['due_date_input']})
    assert resp.status_code == 200
    db.session.refresh(t)
    assert t.due_date == LATO_UTC


def test_zadanie_tworzenie_czas_polski(db, client, make_user, login):
    from modules.admin.models import AdminTask
    login(_admin(make_user))
    resp = client.post('/admin/tasks/create', data={'name': 'Nowe', 'due_date': ZIMA_PL})
    assert resp.status_code == 200
    assert AdminTask.query.filter_by(name='Nowe').one().due_date == ZIMA_UTC


def test_ankieta_zamkniecie_round_trip(db, client, make_user, login):
    from modules.feedback.models import FeedbackSurvey
    admin = _admin(make_user)
    login(admin)
    s = FeedbackSurvey(name='Ankieta', token=FeedbackSurvey.generate_token(),
                       created_by=admin.id, closes_at=ZIMA_UTC)
    db.session.add(s)
    db.session.commit()

    html = client.get(f'/admin/feedback/{s.id}/edit').get_data(as_text=True)
    wartosc = _wartosc_pola(html, r'id="closesAt"[^>]*value="([^"]*)"')
    assert wartosc == ZIMA_PL

    resp = client.post(f'/admin/feedback/{s.id}/save', json={
        'name': 'Ankieta', 'closes_at': wartosc, 'questions': []})
    assert resp.status_code == 200, resp.get_json()
    db.session.refresh(s)
    assert s.closes_at == ZIMA_UTC


def test_konkurs_koniec_round_trip(db, client, make_user, make_product, login):
    from modules.contests.models import Contest
    login(_admin(make_user))
    prod = make_product()
    c = Contest(name='Konkurs', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, cooldown_minutes=1440, status='szkic', ends_at=LATO_UTC)
    db.session.add(c)
    db.session.commit()

    html = client.get(f'/admin/konkursy/{c.id}/edytuj').get_data(as_text=True)
    wartosc = _wartosc_pola(html, r'<input[^>]*name="ends_at"[^>]*value="([^"]*)"')
    assert wartosc == LATO_PL

    resp = client.post(f'/admin/konkursy/{c.id}/edytuj', data={
        'name': 'Konkurs', 'prize_product_id': prod.id, 'num_winners': 1,
        'ticket_min': 1, 'ticket_max': 50, 'cooldown_minutes': 1440,
        'ends_at': wartosc,
    })
    assert resp.status_code == 302
    db.session.refresh(c)
    assert c.ends_at == LATO_UTC


def test_konkurs_nowy_koniec_czas_polski(db, client, make_user, make_product, login):
    from modules.contests.models import Contest
    login(_admin(make_user))
    prod = make_product()
    client.post('/admin/konkursy/nowy', data={
        'name': 'Zimowy', 'prize_product_id': prod.id, 'num_winners': 1,
        'ticket_min': 1, 'ticket_max': 50, 'cooldown_minutes': 1440,
        'ends_at': ZIMA_PL,
    })
    assert Contest.query.filter_by(name='Zimowy').one().ends_at == ZIMA_UTC


def _zlecenie(db, make_user, make_order, **kw):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    u = make_user()
    o = make_order(u, status='dostarczone_gom')
    sr = ShippingRequest(request_number=ShippingRequest.generate_request_number(),
                         user_id=u.id, status='czeka_na_wycene', **kw)
    db.session.add(sr)
    db.session.commit()
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
    db.session.commit()
    return sr


def test_zlecenie_wysylki_termin_round_trip(db, client, make_user, make_order, login):
    login(_admin(make_user))
    sr = _zlecenie(db, make_user, make_order, payment_deadline=LATO_UTC)

    dane = client.get(f'/admin/orders/shipping-requests/{sr.id}').get_json()
    assert dane['payment_deadline_input'] == LATO_PL

    resp = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                      json={'payment_deadline': dane['payment_deadline_input']})
    assert resp.status_code == 200, resp.get_json()
    db.session.refresh(sr)
    assert sr.payment_deadline == LATO_UTC


def test_zlecenie_wysylki_termin_czas_polski_zima(db, client, make_user, make_order, login):
    login(_admin(make_user))
    sr = _zlecenie(db, make_user, make_order)
    resp = client.put(f'/admin/orders/shipping-requests/{sr.id}', json={'payment_deadline': ZIMA_PL})
    assert resp.status_code == 200, resp.get_json()
    db.session.refresh(sr)
    assert sr.payment_deadline == ZIMA_UTC


# ---------------------------------------------------------------------------
# Filtry zakresów dat = polskie doby
# ---------------------------------------------------------------------------

# 2026-07-01 22:30 UTC = 2026-07-02 00:30 w Polsce — już „2 lipca"
PO_POLNOCY_PL = datetime(2026, 7, 1, 22, 30, tzinfo=UTC)


def _filtry(**kw):
    f = {'q': '', 'tracking': '', 'statuses': [], 'date_from': '', 'date_to': ''}
    f.update(kw)
    return f


def test_filtr_zakladek_magazynu_polska_doba(app, db, make_user, make_order):
    from modules.orders.models import Order
    from modules.products.routes import _apply_stock_order_filters
    o = make_order(make_user(), created_at=PO_POLNOCY_PL)

    def ids(**kw):
        return [x.id for x in _apply_stock_order_filters(Order.query, Order, _filtry(**kw)).all()]

    assert ids(date_from='2026-07-02') == [o.id]
    assert ids(date_to='2026-07-02') == [o.id]
    assert ids(date_to='2026-07-01') == []
    assert ids(date_from='2026-07-03') == []


def test_filtr_zamowien_klienta_polska_doba(db, client, make_user, make_order, login):
    u = make_user()
    login(u)
    o = make_order(u, created_at=PO_POLNOCY_PL)
    assert o.order_number in client.get('/client/orders?date_from=2026-07-02').get_data(as_text=True)
    assert o.order_number not in client.get('/client/orders?date_to=2026-07-01').get_data(as_text=True)


def test_filtr_zamowien_admina_polska_doba(db, client, make_user, make_order, login):
    login(_admin(make_user))
    o = make_order(make_user(), created_at=PO_POLNOCY_PL)
    resp = client.get('/admin/orders?date_from=2026-07-02&date_to=2026-07-02')
    assert resp.status_code == 200
    assert o.order_number in resp.get_data(as_text=True)
    resp = client.get('/admin/orders?date_to=2026-07-01')
    assert resp.status_code == 200
    assert o.order_number not in resp.get_data(as_text=True)


def test_filtr_wizyt_qr_polska_doba(db, client, make_user, login):
    from modules.tracking.models import QRCampaign, QRVisit
    admin = _admin(make_user)
    login(admin)
    kampania = QRCampaign(name='K', slug='k', created_by=admin.id)
    db.session.add(kampania)
    db.session.commit()
    db.session.add(QRVisit(campaign_id=kampania.id, visitor_id='v1', visited_at=PO_POLNOCY_PL))
    db.session.commit()

    def wizyty(**kw):
        return client.get(f'/admin/qr-tracking/{kampania.id}/api/stats',
                          query_string={'granularity': 'hourly', **kw}).get_json()['total_visits']

    assert wizyty(date_from='2026-07-02', date_to='2026-07-02') == 1
    assert wizyty(date_from='2026-07-01', date_to='2026-07-01') == 0


def test_zadanie_bez_terminu_round_trip(db, client, make_user, login):
    """Puste pole terminu zostaje puste (nie zamienia się w 'teraz')."""
    from modules.admin.models import AdminTask
    admin = _admin(make_user)
    login(admin)
    t = AdminTask(name='Bez terminu', created_by=admin.id)
    db.session.add(t)
    db.session.commit()
    dane = client.get(f'/admin/tasks/{t.id}').get_json()
    assert dane['task']['due_date_input'] == ''
    assert dane['task']['due_date'] is None
    client.post(f'/admin/tasks/{t.id}/update', data={'name': 'Bez terminu', 'due_date': ''})
    db.session.refresh(t)
    assert t.due_date is None
