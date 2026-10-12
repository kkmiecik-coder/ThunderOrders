"""Blokada pupili dla zwykłych klientów (wdrożenie z kontrolą: widzą je dopiero po decyzji Konrada).

Dwa stany, w których klient NIE może wejść w pupile: (1) domyślne ustawienia (flaga nie istnieje, więc wyłączona),
(2) flaga włączona z rolloutem 0% (tylko admin/mod). Test przechodzi po WSZYSTKICH trasach `pets.*` (metody GET i POST,
liczone dynamicznie z mapy URL, więc nowa trasa bez bramki zaświeci test na czerwono), po stronach panelu klienta
i stronie oferty, szukając śladów pupili w HTML.
"""
import re

import pytest

from tests.test_pets_routes import _wlacz

# ślady funkcji w HTML dla klienta, który jej nie widzi (zakładka „Wkrótce” używa tylko ikony paw.svg i słowa „Wkrótce”)
SLADY = ('petCompanion', 'petsWidget', 'pet-companion', 'pet-jokes', 'pet-rig', 'pets-widget', 'pupil', 'Pupil',
         'pet-updates-toggle', 'client/pupile', 'PetCompanionApi')
STRONY_KLIENTA = ('client.dashboard', 'orders.client_list', 'client.collection_list', 'achievements.gallery',
                  'contests.client_contest', 'client.help_index', 'profile.index')
ZMIENNE_TRAS = {'scene': 'domek', 'sala': 'izba-przyjec'}


def _adres(rule):
    adres = re.sub(r'<int:[^>]+>', '1', rule.rule)
    adres = re.sub(r'<path:[^>]+>', 'cokolwiek', adres)
    return re.sub(r'<(?:[a-z]+:)?([^>]+)>', lambda m: ZMIENNE_TRAS.get(m.group(1), 'x'), adres)


def _trasy(app, prefiks):
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith(prefiks):
            for metoda in sorted(rule.methods - {'HEAD', 'OPTIONS'}):
                yield rule.endpoint, metoda, _adres(rule)


def _otworz(client, metoda, adres):
    return client.open(adres, method=metoda, json={}) if metoda == 'POST' else client.open(adres, method=metoda)


@pytest.fixture(params=['domyslnie', 'rollout_0'])
def stan_zablokowany(request, db):
    """Dwa stany zablokowane dla klienta: brak jakichkolwiek ustawień oraz flaga ON z rolloutem 0%."""
    if request.param == 'rollout_0':
        _wlacz(db, pct=0)
    return request.param


def test_domyslne_ustawienia_to_wylaczone(db):
    from modules.pets.config import PetConfig, feature_flags
    assert PetConfig().enabled is False and PetConfig().rollout_pct == 0
    assert feature_flags() == (False, 0)


def test_klient_nie_wejdzie_w_zadna_trase_pupili(app, client, login, make_user, stan_zablokowany):
    login(make_user(profile_completed=True))
    trasy = list(_trasy(app, 'pets.'))
    assert len(trasy) >= 15, 'test nic by nie sprawdził — nie znaleziono tras pupili'
    for endpoint, metoda, adres in trasy:
        r = _otworz(client, metoda, adres)
        assert r.status_code == 404, (stan_zablokowany, endpoint, metoda, adres, r.status_code)


def test_klient_nie_wejdzie_w_panel_admina_pupili(app, client, login, make_user, stan_zablokowany):
    login(make_user(profile_completed=True))
    trasy = list(_trasy(app, 'pets_admin.'))
    assert len(trasy) >= 7
    for endpoint, metoda, adres in trasy:
        r = _otworz(client, metoda, adres)
        assert r.status_code == 403, (stan_zablokowany, endpoint, metoda, adres, r.status_code)


def test_strony_klienta_nie_zdradzaja_pupili(app, client, login, make_user, stan_zablokowany):
    from flask import url_for
    login(make_user(profile_completed=True))
    with app.test_request_context():
        adresy = [url_for(endpoint) for endpoint in STRONY_KLIENTA]
    for adres in adresy:
        r = client.get(adres, follow_redirects=True)
        assert r.status_code == 200, (adres, r.status_code)
        html = r.data.decode()
        znalezione = [s for s in SLADY if s in html]
        assert not znalezione, (stan_zablokowany, adres, znalezione)
        assert 'sidebar-link disabled' in html and 'Wkrótce' in html, (adres, 'brak zakładki „Wkrótce”')


def test_strona_oferty_nie_laduje_towarzysza(client, login, make_user, strona_sprzedazy, stan_zablokowany):
    login(make_user(profile_completed=True))
    html = client.get(f'/offer/{strona_sprzedazy.token}/thank-you', follow_redirects=True).data.decode()
    assert 'petCompanion' not in html and 'pet-companion' not in html and 'pet-jokes' not in html


def test_admin_po_wlaczeniu_flagi_dostaje_dostep_ale_klient_nie(app, client, login, make_user, db):
    """Kontrola odwrotna: ten sam stan (flaga ON, rollout 0%) wpuszcza admina, a klienta nie."""
    _wlacz(db, pct=0)
    login(make_user(role='admin', profile_completed=True))
    assert client.get('/client/pupile').status_code == 200
    assert client.get('/admin/pupile').status_code == 200
