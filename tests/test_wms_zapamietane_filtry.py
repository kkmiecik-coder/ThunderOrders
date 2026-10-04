"""Panel WMS pamięta filtry z lewej kolumny (status, typ, paczki zbiorcze).

Po zakończeniu pakowania `wms_complete_session` odsyła na gołe `/admin/orders/wms`
— obsługa lądowała na „Wszystkie" zamiast w widoku, z którego zaczęła. Filtry
trzymamy w sesji i przywracamy tylko wtedy, gdy panel otwarto bez parametrów
(menu, link „wróć", przekierowanie po pakowaniu). Linki filtrów zawsze niosą
`tab=shipping`, więc „Wszystkie" nadal czyści zapisany filtr.
"""

import re
from urllib.parse import parse_qs, urlparse

import pytest


@pytest.fixture
def admin(login, make_user):
    login(make_user(role='admin', email='admin-filtry@example.com'))


def _query(odpowiedz):
    return parse_qs(urlparse(odpowiedz.headers['Location']).query)


def test_goly_adres_przywraca_zapisany_status(client, admin):
    client.get('/admin/orders/wms?tab=shipping&status=oplacone')

    odpowiedz = client.get('/admin/orders/wms')

    assert odpowiedz.status_code == 302
    assert urlparse(odpowiedz.headers['Location']).path == '/admin/orders/wms'
    assert _query(odpowiedz) == {'tab': ['shipping'], 'status': ['oplacone']}


def test_przywraca_wszystkie_trzy_filtry(client, admin):
    client.get('/admin/orders/wms?tab=shipping&status=oplacone'
               '&order_type=exclusive&consolidation=sources')

    odpowiedz = client.get('/admin/orders/wms')

    assert odpowiedz.status_code == 302
    assert _query(odpowiedz) == {
        'tab': ['shipping'], 'status': ['oplacone'],
        'order_type': ['exclusive'], 'consolidation': ['sources'],
    }


def test_po_przekierowaniu_filtr_jest_aktywny_w_widoku(client, admin):
    client.get('/admin/orders/wms?tab=shipping&status=oplacone')

    html = client.get('/admin/orders/wms', follow_redirects=True).get_data(as_text=True)

    # aktywny jest link „Opłacone", a nie status „Wszystkie"
    assert re.search(r'status=oplacone[^"]*"\s+class="sr-status-item active', html)


def test_klikniecie_wszystkie_czysci_zapisany_filtr(client, admin):
    client.get('/admin/orders/wms?tab=shipping&status=oplacone')
    client.get('/admin/orders/wms?tab=shipping')  # link „Wszystkie"

    odpowiedz = client.get('/admin/orders/wms')

    assert odpowiedz.status_code == 200


def test_bez_zapisanych_filtrow_goly_adres_nie_przekierowuje(client, admin):
    assert client.get('/admin/orders/wms').status_code == 200


def test_wyszukiwarka_i_strona_nie_sa_zapamietywane(client, admin):
    client.get('/admin/orders/wms?tab=shipping&status=oplacone&search=Mingi&page=2')

    odpowiedz = client.get('/admin/orders/wms')

    assert _query(odpowiedz) == {'tab': ['shipping'], 'status': ['oplacone']}


def test_inne_zakladki_nie_nadpisuja_zapisanych_filtrow(client, admin):
    client.get('/admin/orders/wms?tab=shipping&status=oplacone')
    client.get('/admin/orders/wms?tab=materials')
    client.get('/admin/orders/wms?tab=sessions')

    odpowiedz = client.get('/admin/orders/wms')

    assert odpowiedz.status_code == 302
    assert _query(odpowiedz)['status'] == ['oplacone']


def test_filtry_sa_per_uzytkownik_sesji(app, login, make_user):
    """Druga przeglądarka (inna sesja) nie dziedziczy filtrów pierwszej."""
    pierwsza = app.test_client()
    druga = app.test_client()
    with pierwsza.session_transaction() as s:
        s['_user_id'] = str(make_user(role='admin', email='a1@example.com').id)
        s['_fresh'] = True
    with druga.session_transaction() as s:
        s['_user_id'] = str(make_user(role='admin', email='a2@example.com').id)
        s['_fresh'] = True

    pierwsza.get('/admin/orders/wms?tab=shipping&status=oplacone')

    assert druga.get('/admin/orders/wms').status_code == 200
