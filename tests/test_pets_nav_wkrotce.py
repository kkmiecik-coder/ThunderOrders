"""Zakładka „Wkrótce” w nawigacji klienta, gdy pupile są dla niego niedostępne (flaga wyłączona / poza rolloutem).

Wdrożenie z kontrolą: klient widzi wyszarzoną, nieklikalną zakładkę z łapką i napisem „Wkrótce” (sidebar i arkusz
„Więcej” paska PWA), a prawdziwą dopiero gdy Konrad włączy funkcję. Admin/mod widzą prawdziwą po włączeniu flagi
(rollout 0% = tylko oni); przy WYŁĄCZONEJ fladze bramka nie wpuszcza nikogo, więc też dostają „Wkrótce”.
"""
import re

from tests.test_pets_routes import _wlacz

SIDEBAR_WKROTCE = re.compile(r'<li class="sidebar-item">\s*<span class="sidebar-link disabled"[^>]*>(.*?)</span>\s*</li>', re.S)
SHEET_WKROTCE = re.compile(r'<li>\s*<span class="pwa-sheet-item pwa-sheet-item--disabled"[^>]*>(.*?)</span>\s*</li>', re.S)


def _dashboard(client, login, make_user, **kwargs):
    login(make_user(profile_completed=True, **kwargs))
    r = client.get('/client/dashboard')
    assert r.status_code == 200
    return r.data.decode()


def test_wylaczona_funkcja_pokazuje_zakladke_wkrotce_w_sidebarze(client, login, make_user, db):
    html = _dashboard(client, login, make_user)
    m = SIDEBAR_WKROTCE.search(html)
    assert m, 'brak wyszarzonej zakładki w sidebarze'
    wnetrze = m.group(0)
    assert 'Wkrótce' in wnetrze and 'img/icons/paw.svg' in wnetrze           # ikona łapki zostaje
    assert 'aria-disabled="true"' in wnetrze and '<a ' not in wnetrze          # nie jest linkiem
    assert 'Moje pupile' not in html and 'href="/client/pupile"' not in html   # nic nie zdradza ani nie prowadzi do funkcji


def test_wylaczona_funkcja_pokazuje_zakladke_wkrotce_w_arkuszu_pwa(client, login, make_user, db):
    html = _dashboard(client, login, make_user)
    m = SHEET_WKROTCE.search(html)
    assert m, 'brak wyszarzonej pozycji w arkuszu paska PWA'
    assert 'Wkrótce' in m.group(0) and 'img/icons/paw.svg' in m.group(0)
    assert 'aria-disabled="true"' in m.group(0) and '<a ' not in m.group(0)


def test_wylaczona_funkcja_nie_laduje_towarzysza_ani_widgetu(client, login, make_user, db):
    html = _dashboard(client, login, make_user)
    assert 'id="petCompanion"' not in html and 'id="petsWidget"' not in html


def test_wlaczona_funkcja_pokazuje_prawdziwa_zakladke(client, login, make_user, db):
    _wlacz(db, pct=100)
    html = _dashboard(client, login, make_user)
    assert html.count('href="/client/pupile"') >= 2                             # sidebar + arkusz PWA
    assert not SIDEBAR_WKROTCE.search(html) and not SHEET_WKROTCE.search(html)


def test_poza_rolloutem_klient_widzi_wkrotce(client, login, make_user, db):
    _wlacz(db, pct=0)
    html = _dashboard(client, login, make_user)
    assert SIDEBAR_WKROTCE.search(html) and SHEET_WKROTCE.search(html)
    assert 'href="/client/pupile"' not in html


def test_rollout_0_admin_i_mod_widza_prawdziwa_zakladke(client, login, make_user, db):
    _wlacz(db, pct=0)
    for rola in ('admin', 'mod'):
        login(make_user(role=rola, profile_completed=True))
        r = client.get('/client/pupile')
        assert r.status_code == 200, rola
        html = r.data.decode()
        assert 'href="/client/pupile"' in html, rola
        assert not SIDEBAR_WKROTCE.search(html), rola


def test_wylaczona_flaga_admin_tez_widzi_wkrotce(client, login, make_user, db):
    """Dokumentuje bramkę: przy wyłączonej fladze nie wpuszcza nikogo — żeby testować na produkcji, włącz flagę z rolloutem 0%."""
    login(make_user(role='admin', profile_completed=True))
    assert client.get('/client/pupile').status_code == 404
