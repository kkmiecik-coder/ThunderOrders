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
