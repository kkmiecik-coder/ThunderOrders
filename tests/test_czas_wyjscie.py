"""Wyjście czasu: człowiek zawsze widzi czas polski, JS i API dostają chwilę ze strefą (`...Z`).

Błąd, od którego wszystko się zaczęło: admin w Seulu widział, że odliczanie do startu
sprzedaży kończy się 7 h za wcześnie — strona podawała `starts_at.isoformat()` bez strefy,
a przeglądarka czytała to jako swój czas lokalny.
"""
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from utils.timeutil import utcnow

UTC = timezone.utc

# Lato (CEST, UTC+2) i zima (CET, UTC+1)
LATO_UTC = datetime(2026, 7, 1, 18, 0, tzinfo=UTC)
ZIMA_UTC = datetime(2026, 1, 15, 19, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Filtry Jinja
# ---------------------------------------------------------------------------

def test_format_datetime_lato_i_zima(app):
    tpl = app.jinja_env.from_string("{{ dt|format_datetime('%d.%m.%Y %H:%M') }}")
    assert tpl.render(dt=LATO_UTC) == '01.07.2026 20:00'
    assert tpl.render(dt=ZIMA_UTC) == '15.01.2026 20:00'


def test_format_date_i_time_w_czasie_polskim(app):
    f_date = app.jinja_env.filters['format_date']
    f_time = app.jinja_env.filters['format_time']
    # 23:30 UTC w lecie to już następny dzień w Polsce
    pozno = datetime(2026, 7, 1, 23, 30, tzinfo=UTC)
    assert f_date(pozno, '%d.%m.%Y') == '02.07.2026'
    assert f_time(pozno) == '01:30'


def test_format_date_przyjmuje_sama_date(app):
    """Kolumny `Date` (np. dzień rozliczenia) nie mają strefy — data to data."""
    assert app.jinja_env.filters['format_date'](date(2026, 7, 1), '%d.%m.%Y') == '01.07.2026'


def test_filtry_puste_dla_none(app):
    for nazwa in ('format_datetime', 'format_date', 'format_time'):
        assert app.jinja_env.filters[nazwa](None) == ''


def test_filtry_naiwny_datetime_to_blad(app):
    for nazwa in ('format_datetime', 'format_date', 'format_time'):
        with pytest.raises(ValueError):
            app.jinja_env.filters[nazwa](datetime(2026, 7, 1, 20, 0))


def test_filtr_iso_utc(app):
    tpl = app.jinja_env.from_string('{{ dt|iso_utc }}')
    assert tpl.render(dt=LATO_UTC) == '2026-07-01T18:00:00Z'
    assert app.jinja_env.filters['iso_utc'](None) is None


def test_stary_filtr_to_poland_tz_usuniety(app):
    assert 'to_poland_tz' not in app.jinja_env.filters


# ---------------------------------------------------------------------------
# Strony z odliczaniem: JS dostaje chwilę z `Z`
# ---------------------------------------------------------------------------

def _strona(db, **kw):
    from modules.auth.models import User
    from modules.offers.models import OfferPage
    wlasciciel = User(email='wlasciciel@example.com', role='admin', is_active=True, email_verified=True)
    db.session.add(wlasciciel)
    db.session.commit()
    p = OfferPage(name='P', token=OfferPage.generate_token(), created_by=wlasciciel.id, **kw)
    db.session.add(p)
    db.session.commit()
    return p


def test_countdown_podaje_start_ze_strefa(db, client):
    start = (utcnow() + timedelta(days=2)).replace(microsecond=0)
    p = _strona(db, status='scheduled', starts_at=start)
    resp = client.get(f'/offer/countdown?page={p.token}')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    m = re.search(r'data-target="([^"]+)"', html)
    assert m, 'brak data-target na odliczaniu'
    assert m.group(1) == start.strftime('%Y-%m-%dT%H:%M:%SZ')


def test_strona_zamowien_podaje_koniec_ze_strefa(db, client):
    koniec = (utcnow() + timedelta(days=2)).replace(microsecond=0)
    p = _strona(db, status='active', starts_at=utcnow() - timedelta(hours=1), ends_at=koniec)
    resp = client.get(f'/offer/{p.token}')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    oczekiwane = koniec.strftime('%Y-%m-%dT%H:%M:%SZ')
    assert f'data-deadline="{oczekiwane}"' in html
    assert f'window.initialEndsAt = "{oczekiwane}"' in html


def test_status_strony_podaje_koniec_ze_strefa(db, client):
    koniec = (utcnow() + timedelta(days=2)).replace(microsecond=0)
    p = _strona(db, status='active', starts_at=utcnow() - timedelta(hours=1), ends_at=koniec)
    dane = client.get(f'/offer/{p.token}/status').get_json()
    assert dane['ends_at'] == koniec.strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------------------------------------------------------------------------
# Maile z umówioną godziną: godzina polska + „czasu polskiego"
# ---------------------------------------------------------------------------

def test_mail_zmiany_daty_konca_w_czasie_polskim(app, db, make_user, maile_synchronicznie):
    from extensions import mail
    from utils.email_manager import EmailManager

    p = _strona(db, status='active')
    klient = make_user(email='klient@example.com', first_name='Ola')
    with app.test_request_context(), mail.record_messages() as outbox:
        EmailManager.notify_sale_end_date_changed(p, ZIMA_UTC, LATO_UTC, [klient])

    assert len(outbox) == 1
    for tresc in (outbox[0].html, outbox[0].body):
        assert '01.07.2026, 20:00' in tresc
        assert '15.01.2026, 20:00' in tresc
        assert 'czasu polskiego' in tresc


# ---------------------------------------------------------------------------
# API mobilne: każda chwila w formacie `...Z`
# ---------------------------------------------------------------------------

def test_api_mobilne_lista_ofert_daty_ze_strefa(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    token = client.post('/api/mobile/v1/auth/login',
                        json={'email': u.email, 'password': 'Haslo123!'}).get_json()['data']['access_token']
    start = (utcnow() + timedelta(days=1)).replace(microsecond=0)
    _strona(db, status='scheduled', starts_at=start)

    r = client.get('/api/mobile/v1/offers/offer-pages?status=upcoming',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    strony = r.get_json()['data']
    assert len(strony) == 1
    assert strony[0]['starts_at'] == start.strftime('%Y-%m-%dT%H:%M:%SZ')
    assert strony[0]['ends_at'] is None


# ---------------------------------------------------------------------------
# Wyjście z Pythona dla człowieka (JSON z gotowym tekstem, eksporty)
# ---------------------------------------------------------------------------

def test_lista_stron_sprzedazy_admina_w_czasie_polskim(db, client, make_user, login):
    """Widget dashboardu dostaje gotowy tekst daty - ma być polski, nie UTC."""
    admin = make_user(role='admin', email='admin@example.com', profile_completed=True)
    login(admin)
    _strona(db, status='draft', starts_at=LATO_UTC, ends_at=ZIMA_UTC)
    dane = client.get('/admin/dashboard/offer-pages').get_json()
    assert dane['pages'][0]['starts_at'] == '01.07.2026 20:00'
    assert dane['pages'][0]['ends_at'] == '15.01.2026 20:00'


def test_eksport_wizyt_qr_w_czasie_polskim(app, monkeypatch):
    """Excel z wizytami: nagłówek „Eksport:" i daty wizyt w czasie polskim, nie UTC."""
    import io
    from types import SimpleNamespace

    from openpyxl import load_workbook

    import modules.tracking.export as eksport

    monkeypatch.setattr(eksport, 'utcnow', lambda: ZIMA_UTC)
    kampania = SimpleNamespace(name='K', slug='k')
    wizyta = SimpleNamespace(visited_at=LATO_UTC, device_type=None, browser=None, os=None,
                             country=None, city=None, ip_address=None, is_unique=True, referer=None)
    wynik = eksport.export_visits_xlsx(kampania, [wizyta])
    ws = load_workbook(io.BytesIO(wynik)).active
    assert ws['A3'].value == 'Eksport: 2026-01-15 20:00'
    assert ws['A6'].value == '2026-07-01 20:00:00'
