"""Konfiguracja dostawy — wartości domyślne i nadpisania z tabeli settings."""


def test_domyslne_wartosci_bez_wpisow(app, db):
    from modules.orders.delivery_config import pobierz_konfig_dostawy

    konfig = pobierz_konfig_dostawy()

    assert konfig['reminder_enabled'] is True
    assert konfig['reminder_days'] == 3
    assert konfig['autocomplete_enabled'] is True
    assert konfig['autocomplete_days'] == 10
    assert konfig['autocomplete_batch'] == 50
    assert konfig['review_window_days'] == 30


def test_nadpisanie_z_ustawien(app, db):
    from modules.auth.models import Settings
    from modules.orders.delivery_config import pobierz_konfig_dostawy

    Settings.set_value('delivery_autocomplete_days', 14, type='integer')
    Settings.set_value('delivery_autocomplete_enabled', False, type='boolean')
    db.session.commit()

    konfig = pobierz_konfig_dostawy()

    assert konfig['autocomplete_days'] == 14
    assert konfig['autocomplete_enabled'] is False


def test_smiec_w_ustawieniu_schodzi_na_domyslna(app, db):
    from modules.auth.models import Settings
    from modules.orders.delivery_config import pobierz_konfig_dostawy

    Settings.set_value('delivery_reminder_days', 'trzy', type='string')
    db.session.commit()

    assert pobierz_konfig_dostawy()['reminder_days'] == 3


def test_liczby_dni_maja_dolna_granice(app, db):
    from modules.auth.models import Settings
    from modules.orders.delivery_config import pobierz_konfig_dostawy

    Settings.set_value('delivery_autocomplete_days', 0, type='integer')
    Settings.set_value('delivery_autocomplete_batch', -5, type='integer')
    db.session.commit()

    konfig = pobierz_konfig_dostawy()

    assert konfig['autocomplete_days'] == 1
    assert konfig['autocomplete_batch'] == 1


def test_smiec_w_typie_integer_nie_wywraca_crona(app, db):
    """Settings.get_value() dla type='integer' woła int(setting.value) bez
    try/except — wpis zapisany jako integer z nieliczbową wartością (np. ręcznie
    w bazie albo przez starszą wersję UI) rzuca ValueError. pobierz_konfig_dostawy()
    musi to złapać i zejść na wartość domyślną, żeby cron się nie wywrócił.
    """
    from modules.auth.models import Settings
    from modules.orders.delivery_config import pobierz_konfig_dostawy

    Settings.set_value('delivery_reminder_days', 'trzy', type='integer')
    db.session.commit()

    assert pobierz_konfig_dostawy()['reminder_days'] == 3


# --- Endpoint POST /admin/settings/delivery -------------------------------
#
# Odtworzone po tym, jak poprzedni implementer napisał, uruchomił i skasował te
# testy przed commitem (patrz task-4-report.md). To dokładnie ścieżka, w której
# siedział bug z brakiem atomowości zapisu (Settings.set_value() commituje przy
# każdym wywołaniu) — stąd nacisk na test „brak częściowego zapisu".


def _admin(make_user):
    return make_user(role='admin')


def test_endpoint_zapisuje_poprawne_wartosci(client, db, make_user, login):
    from modules.orders.delivery_config import pobierz_konfig_dostawy

    login(_admin(make_user))

    resp = client.post('/admin/settings/delivery', json={
        'reminder_enabled': False,
        'reminder_days': 5,
        'autocomplete_enabled': False,
        'autocomplete_days': 14,
        'autocomplete_batch': 25,
        'review_window_days': 45,
    })

    assert resp.status_code == 200
    assert resp.get_json()['success'] is True

    konfig = pobierz_konfig_dostawy()
    assert konfig['reminder_enabled'] is False
    assert konfig['reminder_days'] == 5
    assert konfig['autocomplete_enabled'] is False
    assert konfig['autocomplete_days'] == 14
    assert konfig['autocomplete_batch'] == 25
    assert konfig['review_window_days'] == 45


def test_endpoint_odrzuca_wartosc_nieliczbowa(client, db, make_user, login):
    login(_admin(make_user))

    resp = client.post('/admin/settings/delivery', json={'reminder_days': 'abc'})

    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_endpoint_odrzuca_wartosc_ponizej_jeden(client, db, make_user, login):
    login(_admin(make_user))

    resp = client.post('/admin/settings/delivery', json={'autocomplete_batch': 0})

    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_endpoint_ignoruje_klucze_spoza_klucze(client, db, make_user, login):
    """Pola spoza KLUCZE (np. literówka albo próba nadpisania czegoś innego)
    mają być po prostu pomijane, nie trafiać do tabeli settings."""
    from modules.auth.models import Settings

    login(_admin(make_user))

    resp = client.post('/admin/settings/delivery', json={
        'reminder_days': 4,
        'nieznany_klucz': 'cokolwiek',
        'is_admin': True,
    })

    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    assert Settings.get_value('nieznany_klucz') is None
    assert Settings.get_value('is_admin') is None


def test_endpoint_odrzuca_string_zamiast_bool_dla_pola_logicznego(client, db, make_user, login):
    """bool("false") == True w Pythonie (niepusty string jest prawdziwy) — bez
    jawnego sprawdzenia typu endpoint cicho włączyłby przełącznik zamiast go
    wyłączyć. Nieosiągalne z checkboksa w UI (zawsze wysyła prawdziwy bool), ale
    to publiczne API admina."""
    from modules.orders.delivery_config import pobierz_konfig_dostawy

    login(_admin(make_user))
    stan_przed = pobierz_konfig_dostawy()

    resp = client.post('/admin/settings/delivery', json={'reminder_enabled': 'false'})

    assert resp.status_code == 400
    assert resp.get_json()['success'] is False
    # Zero efektu ubocznego — walidacja jest w pierwszym przebiegu, przed zapisem.
    assert pobierz_konfig_dostawy() == stan_przed


def test_endpoint_odrzuca_liczbe_zamiast_bool_dla_pola_logicznego(client, db, make_user, login):
    login(_admin(make_user))

    resp = client.post('/admin/settings/delivery', json={'autocomplete_enabled': 1})

    assert resp.status_code == 400
    assert resp.get_json()['success'] is False


def test_endpoint_blad_pokazuje_etykiete_z_ui_a_nie_surowy_klucz(client, db, make_user, login):
    """Komunikat błędu ma mówić to samo, co admin widzi w formularzu
    (templates/admin/orders/settings.html), nie surowy klucz z KLUCZE."""
    login(_admin(make_user))

    resp = client.post('/admin/settings/delivery', json={'reminder_days': 'abc'})

    tresc = resp.get_json()['message']
    assert 'reminder_days' not in tresc
    assert 'Przypomnienie po (dni od wysyłki)' in tresc


def test_endpoint_blad_bool_pokazuje_etykiete_z_ui(client, db, make_user, login):
    login(_admin(make_user))

    resp = client.post('/admin/settings/delivery', json={'autocomplete_enabled': 'nie'})

    tresc = resp.get_json()['message']
    assert 'autocomplete_enabled' not in tresc
    assert 'Domykaj niepotwierdzone zlecenia automatycznie' in tresc


def test_endpoint_wymaga_roli_admina(client, db, make_user, login):
    login(make_user(role='client'))

    resp = client.post('/admin/settings/delivery', json={'reminder_days': 5})

    assert resp.status_code == 403


def test_endpoint_wymaga_zalogowania(client, db):
    resp = client.post('/admin/settings/delivery', json={'reminder_days': 5})

    assert resp.status_code == 302


def test_endpoint_brak_czesciowego_zapisu_przy_bledzie_walidacji(client, db, make_user, login):
    """Regresja: Settings.set_value() commituje przy KAŻDYM wywołaniu (patrz
    modules/auth/models.py), więc pętla zapisz-po-polu zostawiałaby część
    konfiguracji trwale zmienioną w bazie, mimo że odpowiedź mówi o niepowodzeniu.

    Ustaw znane, niedomyślne wartości, wyślij żądanie z jednym polem błędnym —
    ŻADNE pole nie może się zmienić. Błędne pole (`review_window_days`) jest
    celowo ostatnim kluczem w KLUCZE — w naiwnej pętli jednoprzebiegowej
    wszystkie poprzedzające je pola zdążyłyby się już zapisać, zanim walidacja
    by je złapała.
    """
    from modules.orders.delivery_config import pobierz_konfig_dostawy

    login(_admin(make_user))

    client.post('/admin/settings/delivery', json={
        'reminder_enabled': True,
        'reminder_days': 7,
        'autocomplete_enabled': True,
        'autocomplete_days': 20,
        'autocomplete_batch': 40,
        'review_window_days': 60,
    })
    stan_przed = pobierz_konfig_dostawy()

    resp = client.post('/admin/settings/delivery', json={
        'reminder_enabled': False,
        'reminder_days': 9,
        'autocomplete_enabled': False,
        'autocomplete_days': 99,
        'autocomplete_batch': 77,
        'review_window_days': 'niepoprawna',
    })

    assert resp.status_code == 400

    stan_po = pobierz_konfig_dostawy()
    assert stan_po == stan_przed
