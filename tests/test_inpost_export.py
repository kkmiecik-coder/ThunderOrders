"""Eksport zleceń wysyłki do pliku masowego nadania InPost."""

import pytest


HEADER = ('e-mail;telefon;rozmiar;paczkomat;numer_referencyjny;dodatkowa_ochrona;'
          'za_pobraniem;imie_i_nazwisko;nazwa_firmy;ulica;kod_pocztowy;miejscowosc;'
          'typ_przesylki;paczka_w_weekend')


def _sr(db, user, **kwargs):
    from modules.orders.models import ShippingRequest
    defaults = dict(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id,
        status='oplacone',
        address_type='pickup_point',
        pickup_courier='InPost',
        pickup_point_id='KRA128',
        parcel_size='A',
    )
    defaults.update(kwargs)
    sr = ShippingRequest(**defaults)
    db.session.add(sr)
    db.session.commit()
    return sr


def _rows(csv_text):
    """Wiersze danych bez nagłówka."""
    return [line for line in csv_text.splitlines()[1:] if line]


def test_header_matches_inpost_template(db, make_user):
    from modules.orders.inpost_export import build_inpost_csv
    csv_text, _ = build_inpost_csv([_sr(db, make_user(phone='+48500300100'))])
    assert csv_text.splitlines()[0] == HEADER


def test_pickup_point_row(db, make_user):
    from modules.orders.inpost_export import build_inpost_csv
    user = make_user(email='klient@example.com', phone='+48500300100')
    sr = _sr(db, user, pickup_point_id='WAW350', parcel_size='B',
             shipping_name='Anna Nowak')

    csv_text, warnings = build_inpost_csv([sr])
    row = _rows(csv_text)[0].split(';')

    assert row[0] == 'klient@example.com'
    assert row[1] == '500300100'
    assert row[2] == 'B'
    assert row[3] == 'WAW350'
    assert row[4] == f'Anna Nowak {sr.request_number}'
    assert row[7] == 'Anna Nowak'           # odbiorca także przy paczkomacie
    assert row[12] == 'paczkomat'
    # przy paczkomacie pola adresowe zostają puste
    assert row[8:12] == ['', '', '', '']
    assert warnings == []


def test_courier_row_carries_address(db, make_user):
    from modules.orders.inpost_export import build_inpost_csv
    user = make_user(email='kurier@example.com', phone='+48111222333')
    sr = _sr(db, user, address_type='home', pickup_point_id=None,
             pickup_courier=None, shipping_name='Jan Kowalski',
             shipping_address='ul. Klonowa 5', shipping_postal_code='43-300',
             shipping_city='Bielsko-Biała', parcel_size='C')

    csv_text, warnings = build_inpost_csv([sr])
    row = _rows(csv_text)[0].split(';')

    assert row[2] == 'C'
    assert row[3] == ''                     # kurier nie ma paczkomatu
    assert row[7] == 'Jan Kowalski'
    assert row[9] == 'ul. Klonowa 5'
    assert row[10] == '43-300'
    assert row[11] == 'Bielsko-Biała'
    assert row[12] == 'kurier'
    assert warnings == []


def test_recipient_comes_from_address_not_from_account(db, make_user):
    """Paczkę odbiera osoba z adresu wysyłki, nie zamawiający."""
    from modules.orders.inpost_export import build_inpost_csv
    user = make_user(first_name='Konrad', last_name='Kmiecik', phone='+48500300100')
    sr = _sr(db, user, address_type='home', pickup_point_id=None,
             shipping_name='Karolina Burza', shipping_address='Przykładowa 21/37',
             shipping_postal_code='00-105', shipping_city='Warszawa')

    csv_text, _ = build_inpost_csv([sr])
    row = _rows(csv_text)[0].split(';')

    assert row[7] == 'Karolina Burza'
    assert row[4] == f'Karolina Burza {sr.request_number}'


def test_recipient_falls_back_to_profile(db, make_user):
    """Przy paczkomacie adres często nie ma nazwy — wtedy bierzemy klienta z konta."""
    from modules.orders.inpost_export import build_inpost_csv
    user = make_user(first_name='Zuzanna', last_name='Kopyść', phone='+48500300100')
    sr = _sr(db, user, shipping_name=None)

    csv_text, _ = build_inpost_csv([sr])
    row = _rows(csv_text)[0].split(';')

    assert row[7] == 'Zuzanna Kopyść'
    assert row[4] == f'Zuzanna Kopyść {sr.request_number}'


def test_optional_columns_stay_empty(db, make_user):
    from modules.orders.inpost_export import build_inpost_csv
    csv_text, _ = build_inpost_csv([_sr(db, make_user(phone='+48500300100'))])
    row = _rows(csv_text)[0].split(';')

    assert row[5] == ''      # dodatkowa_ochrona
    assert row[6] == ''      # za_pobraniem
    assert row[8] == ''      # nazwa_firmy
    assert row[13] == 'NIE'  # paczka_w_weekend


def test_reference_joins_name_and_request_number(db, make_user):
    from modules.orders.inpost_export import build_inpost_csv
    sr = _sr(db, make_user(phone='+48500300100'), shipping_name='Iga Bednarek')

    csv_text, _ = build_inpost_csv([sr])
    assert _rows(csv_text)[0].split(';')[4] == f'Iga Bednarek {sr.request_number}'


def test_mini_parcel_is_excluded_with_warning(db, make_user):
    from modules.orders.inpost_export import build_inpost_csv
    user = make_user(phone='+48500300100')
    ok = _sr(db, user, parcel_size='A')
    mini = _sr(db, user, parcel_size='mini')

    csv_text, warnings = build_inpost_csv([ok, mini])

    assert len(_rows(csv_text)) == 1
    assert mini.request_number in ' '.join(warnings)
    assert 'mini' in ' '.join(warnings).lower()


def test_missing_parcel_size_is_excluded_with_warning(db, make_user):
    from modules.orders.inpost_export import build_inpost_csv
    user = make_user(phone='+48500300100')
    bez = _sr(db, user, parcel_size=None)

    csv_text, warnings = build_inpost_csv([bez])

    assert _rows(csv_text) == []
    assert bez.request_number in ' '.join(warnings)


def test_missing_phone_exports_but_warns(db, make_user):
    """Braki telefonu to niedokończone rejestracje — wiersz zostaje, admin dostaje ostrzeżenie."""
    from modules.orders.inpost_export import build_inpost_csv
    sr = _sr(db, make_user(phone=None))

    csv_text, warnings = build_inpost_csv([sr])
    row = _rows(csv_text)[0].split(';')

    assert row[1] == ''
    assert sr.request_number in ' '.join(warnings)
    assert 'telefon' in ' '.join(warnings).lower()


def test_pickup_point_id_is_trimmed(db, make_user):
    """W bazie zdarzają się kody z wiodącą spacją (' POZ282M')."""
    from modules.orders.inpost_export import build_inpost_csv
    sr = _sr(db, make_user(phone='+48500300100'), pickup_point_id=' POZ282M ')

    csv_text, _ = build_inpost_csv([sr])
    assert _rows(csv_text)[0].split(';')[3] == 'POZ282M'


@pytest.mark.parametrize('stored, expected', [
    ('+48500300100', '500300100'),          # dominujący format w bazie
    ('+48 690 364 820', '690364820'),       # ze spacjami
    ('500300100', '500300100'),             # już bez prefiksu
    ('48500300100', '500300100'),           # bez plusa
    ('0048500300100', '500300100'),
    ('+48-500-300-100', '500300100'),
    ('+49517905240', '+49517905240'),       # zagraniczny zostaje z prefiksem
    ('+372534495773', '+372534495773'),
])
def test_phone_normalized_to_nine_digits(db, make_user, stored, expected):
    """InPost dostaje polskie numery jako 9 cyfr; zagranicznych nie ruszamy."""
    from modules.orders.inpost_export import build_inpost_csv
    csv_text, _ = build_inpost_csv([_sr(db, make_user(phone=stored))])
    assert _rows(csv_text)[0].split(';')[1] == expected


def test_semicolon_in_data_does_not_break_columns(db, make_user):
    """Średnik jest separatorem — dane muszą zostać zacytowane."""
    from modules.orders.inpost_export import build_inpost_csv
    sr = _sr(db, make_user(phone='+48500300100'), address_type='home',
             pickup_point_id=None, shipping_name='Kowalski; Jan',
             shipping_address='ul. Testowa 1', shipping_postal_code='00-001',
             shipping_city='Warszawa')

    csv_text, _ = build_inpost_csv([sr])
    import csv as csv_module
    from io import StringIO
    rows = list(csv_module.reader(StringIO(csv_text), delimiter=';'))

    assert len(rows[1]) == 14
    assert rows[1][7] == 'Kowalski; Jan'


def test_export_endpoint_returns_csv_and_warnings(client, db, make_user, login):
    from modules.orders.inpost_export import build_inpost_csv  # noqa: F401
    admin = make_user(role='admin', email='admin@example.com', profile_completed=True)
    login(admin)
    user = make_user(phone='+48500300100')
    ok = _sr(db, user, parcel_size='A')
    mini = _sr(db, user, parcel_size='mini')

    resp = client.post('/admin/orders/shipping-requests/export-inpost',
                       json={'ids': [ok.id, mini.id]})
    assert resp.status_code == 200
    data = resp.get_json()

    assert data['success'] is True
    assert data['filename'].startswith('inpost_')
    assert data['filename'].endswith('.csv')
    assert data['exported'] == 1
    assert ok.request_number in data['csv']
    assert mini.request_number not in data['csv']
    assert any(mini.request_number in w for w in data['warnings'])


def test_export_endpoint_requires_ids(client, make_user, login):
    login(make_user(role='admin', email='admin2@example.com', profile_completed=True))
    resp = client.post('/admin/orders/shipping-requests/export-inpost', json={'ids': []})
    assert resp.status_code == 400


def test_export_endpoint_rejects_client(client, db, make_user, login):
    user = make_user(phone='+48500300100')
    sr = _sr(db, user)
    login(user)
    resp = client.post('/admin/orders/shipping-requests/export-inpost', json={'ids': [sr.id]})
    assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# Kurier punktu odbioru (K3)
#
# Plik jest szablonem masowego nadania InPost — przesyłki do Orlen Paczki nie
# da się przez niego nadać. Wcześniej `build_inpost_csv` czytał wyłącznie
# `address_type`, więc kod Orlenu lądował w kolumnie `paczkomat` z typem
# 'paczkomat', a pola adresowe były zerowane: wiersz nie do zaimportowania,
# a adres zapasowy przepadał.
# ---------------------------------------------------------------------------

def test_orlen_paczka_pomijana_z_ostrzezeniem(db, make_user):
    from modules.orders.inpost_export import build_inpost_csv
    user = make_user(phone='+48500300100')
    sr = _sr(db, user, pickup_courier='Orlen Paczka', pickup_point_id='PL1234')

    csv_text, warnings = build_inpost_csv([sr])

    assert _rows(csv_text) == [], 'Orlen Paczki nie da się nadać przez InPost'
    assert any('Orlen' in w for w in warnings), (
        f'Eksportujący musi wiedzieć, czego brakuje w pliku; ostrzeżenia: {warnings}'
    )


def test_orlen_nie_blokuje_pozostalych_zlecen(db, make_user):
    from modules.orders.inpost_export import build_inpost_csv
    user = make_user(phone='+48500300100')
    orlen = _sr(db, user, pickup_courier='Orlen Paczka', pickup_point_id='PL1234')
    inpost = _sr(db, user, pickup_courier='InPost', pickup_point_id='KRA128')

    csv_text, warnings = build_inpost_csv([orlen, inpost])
    wiersze = _rows(csv_text)

    assert len(wiersze) == 1
    assert wiersze[0].split(';')[3] == 'KRA128'


def test_dostawa_kurierem_nie_patrzy_na_kuriera_punktu(db, make_user):
    """Adres domowy jedzie kurierem — `pickup_courier` bywa resztką po zmianie adresu."""
    from modules.orders.inpost_export import build_inpost_csv
    user = make_user(phone='+48500300100')
    sr = _sr(db, user, address_type='home', pickup_courier='Orlen Paczka',
             shipping_address='Kwiatowa 1', shipping_postal_code='30-001',
             shipping_city='Kraków', shipping_name='Jan Kowalski')

    csv_text, warnings = build_inpost_csv([sr])
    wiersze = _rows(csv_text)

    assert len(wiersze) == 1, 'Przesyłka kurierska nie jest zależna od pickup_courier'
    assert wiersze[0].split(';')[12] == 'kurier'


def test_brak_kuriera_punktu_traktowany_jak_inpost(db, make_user):
    """Historyczne zlecenia bez `pickup_courier` — domyślnie InPost, jak dotąd."""
    from modules.orders.inpost_export import build_inpost_csv
    user = make_user(phone='+48500300100')
    sr = _sr(db, user, pickup_courier=None, pickup_point_id='KRA128')

    csv_text, warnings = build_inpost_csv([sr])

    assert len(_rows(csv_text)) == 1
    assert _rows(csv_text)[0].split(';')[3] == 'KRA128'


# ---------------------------------------------------------------------------
# Ponowne nadanie (K4)
#
# Eksport nie zostawia śladu na rekordzie, więc nic nie wykrywa powtórzenia:
# admin, który zaznaczył „wszystkie na wszystkich stronach" i wyeksportował
# drugi raz (bo import w panelu InPost częściowo padł), nadawał ponownie
# przesyłki już wysłane — realny koszt u kuriera.
# ---------------------------------------------------------------------------

def test_zlecenie_z_numerem_przesylki_pomijane(db, make_user):
    from modules.orders.inpost_export import build_inpost_csv
    user = make_user(phone='+48500300100')
    sr = _sr(db, user, tracking_number='6200000000001')

    csv_text, warnings = build_inpost_csv([sr])

    assert _rows(csv_text) == [], 'Zlecenie z numerem przesyłki jest już nadane'
    # Asercja na treść informacyjną, nie na brzmienie komunikatu: eksportujący
    # musi zobaczyć, którego zlecenia brakuje i dlaczego.
    assert len(warnings) == 1
    assert sr.request_number in warnings[0]
    assert '6200000000001' in warnings[0]


@pytest.mark.parametrize('status', ['wyslane', 'dostarczone'])
def test_zlecenie_juz_wyslane_pomijane(db, make_user, status):
    from modules.orders.inpost_export import build_inpost_csv
    user = make_user(phone='+48500300100')
    sr = _sr(db, user, status=status)

    csv_text, warnings = build_inpost_csv([sr])

    assert _rows(csv_text) == [], f'Zlecenie w statusie {status} już pojechało'
    assert warnings


def test_swieze_zlecenie_bez_trackingu_eksportowane(db, make_user):
    """Regresja: normalna ścieżka nadania nie może zostać zablokowana."""
    from modules.orders.inpost_export import build_inpost_csv
    user = make_user(phone='+48500300100')
    sr = _sr(db, user, status='spakowane', tracking_number=None)

    csv_text, warnings = build_inpost_csv([sr])

    assert len(_rows(csv_text)) == 1
    assert warnings == []
