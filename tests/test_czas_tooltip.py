"""Tooltip z godziną w innych miastach + ustawienie stref (`display_timezones`).

Czas polski zostaje główną, widoczną wartością (liczony na serwerze, działa bez JS).
`pl_time` owija go w `<time datetime="...Z" class="tz-time">`, a tz-tooltip.js dokleja
podpowiedź „Seul: 31.10, 03:00" dla miast z ustawień — listę edytuje admin.
"""
import json
import re
from datetime import datetime, timezone

from utils.timeutil import get_display_timezones

UTC = timezone.utc
LATO_UTC = datetime(2026, 7, 1, 18, 0, tzinfo=UTC)

SEUL = {'label': 'Seul', 'tz': 'Asia/Seoul'}
LONDYN = {'label': 'Londyn', 'tz': 'Europe/London'}

URL_DODAJ = '/admin/offers/settings/timezones'
URL_USUN = '/admin/offers/settings/timezones/delete'


def _zapisane_strefy():
    """Surowy wiersz ustawienia (None, gdy nic nie zapisano) — bez wartości domyślnej helpera."""
    from modules.auth.models import Settings
    wiersz = Settings.query.filter_by(key='display_timezones').first()
    return None if wiersz is None else json.loads(wiersz.value)


def _admin(make_user, login):
    admin = make_user(role='admin', profile_completed=True)
    login(admin)
    return admin


# ---------------------------------------------------------------------------
# Filtr pl_time
# ---------------------------------------------------------------------------

def test_pl_time_lato(app):
    html = app.jinja_env.from_string('{{ dt|pl_time }}').render(dt=LATO_UTC)
    assert 'datetime="2026-07-01T18:00:00Z"' in html
    assert '>01.07.2026, 20:00<' in html
    assert 'class="tz-time"' in html
    assert html.startswith('<time ') and html.endswith('</time>')


def test_pl_time_wlasny_format(app):
    html = app.jinja_env.from_string("{{ dt|pl_time('%H:%M') }}").render(dt=LATO_UTC)
    assert '>20:00<' in html and 'datetime="2026-07-01T18:00:00Z"' in html


def test_pl_time_pusty_dla_none(app):
    assert app.jinja_env.from_string('{{ dt|pl_time }}').render(dt=None) == ''


def test_pl_time_naiwny_datetime_to_blad(app):
    import pytest
    with pytest.raises(ValueError):
        app.jinja_env.filters['pl_time'](datetime(2026, 7, 1, 18, 0))


# ---------------------------------------------------------------------------
# Ustawienie display_timezones
# ---------------------------------------------------------------------------

def test_domyslnie_seul(app, db):
    assert get_display_timezones() == [SEUL]


def test_admin_dodaje_strefe(app, db, client, login, make_user):
    _admin(make_user, login)
    resp = client.post(URL_DODAJ, json=LONDYN)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()['success'] is True
    assert _zapisane_strefy() == [SEUL, LONDYN]
    assert get_display_timezones() == [SEUL, LONDYN]


def test_etykieta_przycinana(app, db, client, login, make_user):
    _admin(make_user, login)
    assert client.post(URL_DODAJ, json={'label': '  Londyn  ', 'tz': 'Europe/London'}).status_code == 200
    assert _zapisane_strefy() == [SEUL, LONDYN]


def test_nieznana_strefa_400_bez_zapisu(app, db, client, login, make_user):
    _admin(make_user, login)
    resp = client.post(URL_DODAJ, json={'label': 'Mars', 'tz': 'Mars/Base'})
    assert resp.status_code == 400
    assert resp.get_json()['success'] is False
    assert _zapisane_strefy() is None


def test_zle_dane_400_bez_zapisu(app, db, client, login, make_user):
    _admin(make_user, login)
    zle = [
        {'label': '', 'tz': 'Europe/London'},
        {'label': '   ', 'tz': 'Europe/London'},
        {'label': 'x' * 41, 'tz': 'Europe/London'},
        {'label': 'Seul 2', 'tz': 'Asia/Seoul'},        # duplikat strefy z domyślnej listy
        {'label': 'Londyn'},
        {'label': 123, 'tz': 'Europe/London'},
        {'label': 'Londyn', 'tz': ['Europe/London']},
    ]
    for dane in zle:
        resp = client.post(URL_DODAJ, json=dane)
        assert resp.status_code == 400, dane
    assert client.post(URL_DODAJ, data='nie-json', content_type='text/plain').status_code == 400
    assert _zapisane_strefy() is None


def test_limit_stref(app, db, client, login, make_user):
    _admin(make_user, login)
    strefy = ['Europe/London', 'Europe/Paris', 'America/New_York', 'America/Los_Angeles',
              'Asia/Tokyo', 'Asia/Shanghai', 'Australia/Sydney', 'Asia/Dubai', 'Asia/Bangkok']
    for tz in strefy:      # Seul + 9 = 10
        assert client.post(URL_DODAJ, json={'label': tz, 'tz': tz}).status_code == 200
    assert len(get_display_timezones()) == 10
    resp = client.post(URL_DODAJ, json={'label': 'Za dużo', 'tz': 'America/Chicago'})
    assert resp.status_code == 400
    assert len(get_display_timezones()) == 10


def test_admin_usuwa_strefe(app, db, client, login, make_user):
    _admin(make_user, login)
    client.post(URL_DODAJ, json=LONDYN)
    resp = client.post(URL_USUN, json={'tz': 'Asia/Seoul'})
    assert resp.status_code == 200 and resp.get_json()['success'] is True
    assert get_display_timezones() == [LONDYN]
    # Ostatnia strefa też do usunięcia — pusta lista wyłącza podpowiedź (nie wraca Seul)
    assert client.post(URL_USUN, json={'tz': 'Europe/London'}).status_code == 200
    assert _zapisane_strefy() == []
    assert get_display_timezones() == []


def test_usuniecie_nieistniejacej_404(app, db, client, login, make_user):
    _admin(make_user, login)
    assert client.post(URL_USUN, json={'tz': 'Europe/London'}).status_code == 404
    assert _zapisane_strefy() is None


def test_tylko_admin(app, db, client, login, make_user):
    klient = make_user(role='client', profile_completed=True)
    login(klient)
    assert client.post(URL_DODAJ, json=LONDYN).status_code == 403
    assert client.post(URL_USUN, json={'tz': 'Asia/Seoul'}).status_code == 403
    assert _zapisane_strefy() is None


def test_strona_ustawien_pokazuje_strefy(app, db, client, login, make_user):
    _admin(make_user, login)
    html = client.get('/admin/offers/settings').get_data(as_text=True)
    assert 'id="tab-display-timezones"' in html
    assert 'data-tz="Asia/Seoul"' in html
    assert '<option value="Europe/London"' in html


# ---------------------------------------------------------------------------
# Strony: lista stref na <body>, komponent ładowany raz
# ---------------------------------------------------------------------------

def _body(html):
    m = re.search(r'<body[^>]*>', html)
    assert m, 'brak <body>'
    return m.group(0)


def _strefy_z_body(html):
    m = re.search(r"data-display-timezones='([^']*)'", _body(html))
    assert m, _body(html)
    return json.loads(m.group(1))


def test_panel_klienta_ma_strefy_i_komponent(app, db, client, login, make_user, make_order):
    klient = make_user(profile_completed=True)
    login(klient)
    make_order(klient, created_at=LATO_UTC)
    html = client.get('/client/orders').get_data(as_text=True)
    assert _strefy_z_body(html) == [SEUL]
    assert html.count('js/components/tz-tooltip.js') == 1
    assert html.count('css/components/tz-tooltip.css') == 1
    # lista zamówień klienta pokazuje godzinę złożenia w <time> z chwilą UTC
    assert '<time datetime="2026-07-01T18:00:00Z" class="tz-time">01.07.2026 20:00</time>' in html


def test_strona_oferty_ma_strefy_i_komponent(app, db, client, login, make_user, strona_sprzedazy):
    klient = make_user(profile_completed=True)
    login(klient)
    html = client.get(f'/offer/{strona_sprzedazy.token}/thank-you', follow_redirects=True).get_data(as_text=True)
    assert 'offer-page-body' in _body(html)
    assert _strefy_z_body(html) == [SEUL]
    assert html.count('js/components/tz-tooltip.js') == 1
    assert html.count('css/components/tz-tooltip.css') == 1


def test_etykieta_bezpieczna_w_atrybucie(app, db, client, login, make_user):
    """Etykietę wpisuje admin — w atrybucie body nie może zamknąć cudzysłowu ani wstawić tagu."""
    _admin(make_user, login)
    assert client.post(URL_DODAJ, json={'label': "Seul'><b>", 'tz': 'Europe/London'}).status_code == 200
    html = client.get('/admin/offers/settings').get_data(as_text=True)
    assert _strefy_z_body(html)[1]['label'] == "Seul'><b>"
    assert '<b>' not in _body(html)


def test_pusta_lista_bez_atrybutu(app, db, client, login, make_user):
    _admin(make_user, login)
    client.post(URL_USUN, json={'tz': 'Asia/Seoul'})
    html = client.get('/admin/offers/settings').get_data(as_text=True)
    assert 'data-display-timezones' not in _body(html)
