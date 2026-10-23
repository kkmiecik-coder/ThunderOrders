"""Testy migracji danych czasu polskiego na UTC (`e3b9a6c1d4f7_czas_utc_dane.py`).

Migracja przelicza naiwny czas polski w bazie na naiwny UTC. Jej lista kolumn (`KOLUMNY`)
i konwersja są zamrożone w pliku migracji; tutaj leży lista kolumn pominiętych
(`WYKLUCZONE`) i strażnik, że każda kolumna `UTCDateTime` z modeli jest w jednej z nich.
Sprawdzamy też konwersję przy obu zmianach czasu i przebieg migracji na SQLite.
"""
import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from utils.timeutil import UTCDateTime

PLIK_MIGRACJI = Path(__file__).resolve().parent.parent / 'migrations' / 'versions' / 'e3b9a6c1d4f7_czas_utc_dane.py'


def _wczytaj_migracje():
    """Świeży moduł migracji (każdy test może bezpiecznie podmieniać w nim WSAD/KOLUMNY)."""
    spec = importlib.util.spec_from_file_location('migracja_czas_utc_dane', PLIK_MIGRACJI)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


_MIGRACJA = _wczytaj_migracje()
KOLUMNY = _MIGRACJA.KOLUMNY
pl_naive_to_utc_naive = _MIGRACJA.pl_naive_to_utc_naive
utc_naive_to_pl_naive = _MIGRACJA.utc_naive_to_pl_naive

# Kolumny już w UTC, których migracja nie rusza (źródła zapisu w kodzie sprzed zmiany, d681efb9;
# serwer i sesja MariaDB w UTC). Kolumna `UTCDateTime` dodana po migracji jest od początku w UTC —
# dopisz ją TUTAJ, nigdy do zamrożonego `KOLUMNY` w pliku migracji.
WYKLUCZONE: dict[str, list[str]] = {
    # default=db.func.now() i onupdate=db.func.now() — czas sesji MariaDB (UTC)
    'cart_items': ['created_at', 'updated_at'],
    # jedyny zapis: csv_processor.py `completed_at = datetime.now()` (wcześniej utcnow)
    'csv_imports': ['completed_at'],
    # default=datetime.now — serwer w UTC
    'offer_section_images': ['created_at'],
    # default=datetime.now — serwer w UTC
    'offer_sections': ['created_at'],
    # default/onupdate=datetime.now(timezone.utc)
    'payment_methods': ['created_at', 'updated_at'],
    # default=db.func.now() — czas sesji MariaDB (UTC)
    'product_interactions': ['created_at'],
    # created_at: default=datetime.utcnow; last_used_at: push_manager `datetime.utcnow()`
    'push_subscriptions': ['created_at', 'last_used_at'],
    # jedyny zapis: api/analytics.py `analytics_consent_date = datetime.now()` (poza NULL przy anonimizacji)
    'users': ['analytics_consent_date'],
}


# --- konwersja -------------------------------------------------------------

def test_lato_i_zima():
    assert pl_naive_to_utc_naive(datetime(2026, 7, 1, 20, 0)) == datetime(2026, 7, 1, 18, 0)
    assert pl_naive_to_utc_naive(datetime(2026, 1, 15, 20, 0)) == datetime(2026, 1, 15, 19, 0)
    assert utc_naive_to_pl_naive(datetime(2026, 7, 1, 18, 0)) == datetime(2026, 7, 1, 20, 0)
    assert utc_naive_to_pl_naive(datetime(2026, 1, 15, 19, 0)) == datetime(2026, 1, 15, 20, 0)


def test_wynik_naiwny_z_mikrosekundami():
    wynik = pl_naive_to_utc_naive(datetime(2026, 7, 1, 20, 0, 5, 123456))
    assert wynik == datetime(2026, 7, 1, 18, 0, 5, 123456)
    assert wynik.tzinfo is None
    assert utc_naive_to_pl_naive(wynik).tzinfo is None


def test_jesienna_podwojna_godzina_pierwsze_wystapienie():
    # 26.10.2025 2:30 zdarza się dwa razy (CEST, potem CET) — bierzemy pierwsze (fold=0, CEST)
    assert pl_naive_to_utc_naive(datetime(2025, 10, 26, 2, 30)) == datetime(2025, 10, 26, 0, 30)
    assert pl_naive_to_utc_naive(datetime(2026, 10, 25, 2, 30)) == datetime(2026, 10, 25, 0, 30)


def test_wiosenna_nieistniejaca_godzina():
    # 29.03.2026 2:30 w Polsce nie istnieje; zoneinfo dla fold=0 bierze offset sprzed zmiany (CET)
    assert pl_naive_to_utc_naive(datetime(2026, 3, 29, 2, 30)) == datetime(2026, 3, 29, 1, 30)


def test_granice_zmian_czasu():
    # ostatnia minuta CET i pierwsza CEST (wiosna), ostatnia CEST przed podwójną godziną i pierwsza po niej (jesień)
    assert pl_naive_to_utc_naive(datetime(2026, 3, 29, 1, 59)) == datetime(2026, 3, 29, 0, 59)
    assert pl_naive_to_utc_naive(datetime(2026, 3, 29, 3, 0)) == datetime(2026, 3, 29, 1, 0)
    assert pl_naive_to_utc_naive(datetime(2025, 10, 26, 1, 59)) == datetime(2025, 10, 25, 23, 59)
    assert pl_naive_to_utc_naive(datetime(2025, 10, 26, 3, 0)) == datetime(2025, 10, 26, 2, 0)


def test_aware_rzuca():
    from datetime import timezone
    with pytest.raises(ValueError):
        pl_naive_to_utc_naive(datetime(2026, 7, 1, 20, 0, tzinfo=timezone.utc))
    with pytest.raises(ValueError):
        utc_naive_to_pl_naive(datetime(2026, 7, 1, 20, 0, tzinfo=timezone.utc))


def _co_15_minut(od, do):
    chwila = od
    while chwila < do:
        yield chwila
        chwila += timedelta(minutes=15)


def _wiosenna_luka(x):
    """Godzina 2:00–2:59 w ostatnią niedzielę marca (w Polsce nie istnieje)."""
    return x.month == 3 and x.weekday() == 6 and x.day >= 25 and x.hour == 2


def test_upgrade_potem_downgrade_odtwarza_czas_polski():
    # Każdy istniejący polski czas wraca bez zmian — także podwójna jesienna godzina (fold=0 tam i z powrotem).
    # Stratna jest tylko nieistniejąca wiosenna godzina: 2:30 -> 1:30 UTC -> 3:30.
    for x in _co_15_minut(datetime(2025, 1, 1), datetime(2027, 1, 1)):
        if _wiosenna_luka(x):
            assert utc_naive_to_pl_naive(pl_naive_to_utc_naive(x)) == x + timedelta(hours=1)
        else:
            assert utc_naive_to_pl_naive(pl_naive_to_utc_naive(x)) == x


def test_downgrade_potem_upgrade_odtwarza_utc():
    # Odwrotny kierunek jest stratny tylko w drugim wystąpieniu jesiennej godziny (UTC 1:00–1:59
    # w dniu zmiany): polski zapis 2:xx nie niesie fold, więc wraca jako pierwsze wystąpienie (-1 h).
    for x in _co_15_minut(datetime(2025, 1, 1), datetime(2027, 1, 1)):
        druga_jesienna = x.month == 10 and x.weekday() == 6 and x.day >= 25 and x.hour == 1
        if druga_jesienna:
            assert pl_naive_to_utc_naive(utc_naive_to_pl_naive(x)) == x - timedelta(hours=1)
        else:
            assert pl_naive_to_utc_naive(utc_naive_to_pl_naive(x)) == x


# --- lista kolumn ----------------------------------------------------------

def _kolumny_utc_z_modeli(db):
    return {
        (tabela.name, kolumna.name)
        for tabela in db.metadata.tables.values()
        for kolumna in tabela.columns
        if isinstance(kolumna.type, UTCDateTime)
    }


def _pary(slownik):
    return {(tabela, kolumna) for tabela, kolumny in slownik.items() for kolumna in kolumny}


def test_kazda_kolumna_utc_jest_sklasyfikowana(db):
    brakujace = _kolumny_utc_z_modeli(db) - _pary(KOLUMNY) - _pary(WYKLUCZONE)
    assert not brakujace, (
        f'Kolumny UTCDateTime ani w KOLUMNY migracji e3b9a6c1d4f7, ani w WYKLUCZONE: {sorted(brakujace)}. '
        'Kolumna dodana po migracji czasu na UTC jest od początku w UTC — dopisz ją do WYKLUCZONE w tym pliku.'
    )


def test_kolumny_i_wykluczone_rozlaczne():
    assert not _pary(KOLUMNY) & _pary(WYKLUCZONE)


def test_bez_duplikatow_w_listach():
    for slownik in (KOLUMNY, WYKLUCZONE):
        for tabela, kolumny in slownik.items():
            assert len(kolumny) == len(set(kolumny)), tabela


def test_tabele_do_konwersji_maja_klucz_id(db):
    # Migracja idzie wsadami po `id`; tabela z innym kluczem wymagałaby osobnej obsługi.
    for tabela in KOLUMNY:
        if tabela in db.metadata.tables:
            assert [k.name for k in db.metadata.tables[tabela].primary_key.columns] == ['id'], tabela


def test_pewne_wykluczenia_i_poprawki_specu():
    assert set(WYKLUCZONE['cart_items']) == {'created_at', 'updated_at'}
    assert set(WYKLUCZONE['payment_methods']) == {'created_at', 'updated_at'}
    assert set(WYKLUCZONE['push_subscriptions']) == {'created_at', 'last_used_at'}
    assert WYKLUCZONE['product_interactions'] == ['created_at']
    assert WYKLUCZONE['offer_sections'] == ['created_at']
    assert WYKLUCZONE['offer_section_images'] == ['created_at']
    # notifications.created_at miało default=get_local_now (utcnow z linii 85 to push_subscriptions)
    assert KOLUMNY['notifications'] == ['created_at']


# --- przebieg migracji na SQLite -------------------------------------------

def _uruchom(modul, kierunek, db):
    polaczenie = db.session.connection()
    with Operations.context(MigrationContext.configure(polaczenie)):
        getattr(modul, kierunek)()


def _tabela(nazwa, *kolumny):
    return sa.table(nazwa, sa.column('id', sa.Integer), *(sa.column(k, sa.DateTime) for k in kolumny))


def _ustaw(db, nazwa, id_, **wartosci):
    t = _tabela(nazwa, *wartosci)
    db.session.execute(sa.update(t).where(t.c.id == id_).values(**wartosci))


def _odczytaj(db, nazwa, id_, *kolumny):
    t = _tabela(nazwa, *kolumny)
    wiersz = db.session.execute(sa.select(*(t.c[k] for k in kolumny)).where(t.c.id == id_)).one()
    return dict(zip(kolumny, wiersz))


def test_migracja_przelicza_kolumny_i_omija_wykluczone(db, make_user, make_product, make_order, capsys):
    from modules.notifications.models import Notification, PushSubscription
    from modules.products.models import CartItem

    uzytkownik = make_user()
    zamowienie = make_order(uzytkownik)
    koszyk = CartItem(user_id=uzytkownik.id, product_id=make_product().id, quantity=1)
    powiadomienie = Notification(user_id=uzytkownik.id, title='Test')
    subskrypcja = PushSubscription(user_id=uzytkownik.id, endpoint='https://push.example.com/x',
                                   p256dh_key='k', auth_key='a')
    db.session.add_all([koszyk, powiadomienie, subskrypcja])
    db.session.commit()

    lato = datetime(2026, 7, 1, 20, 0)
    zima = datetime(2026, 1, 15, 20, 0)
    jesien = datetime(2025, 10, 26, 2, 30)        # podwójna godzina
    wiosna = datetime(2026, 3, 29, 2, 30)         # nieistniejąca godzina

    _ustaw(db, 'users', uzytkownik.id, created_at=lato, last_login=jesien, analytics_consent_date=lato,
           deactivated_at=None)
    _ustaw(db, 'orders', zamowienie.id, created_at=zima, updated_at=wiosna, status_changed_at=None)
    _ustaw(db, 'cart_items', koszyk.id, created_at=lato, updated_at=lato)
    _ustaw(db, 'notifications', powiadomienie.id, created_at=lato)
    _ustaw(db, 'push_subscriptions', subskrypcja.id, created_at=lato, last_used_at=lato)

    migracja = _wczytaj_migracje()
    _uruchom(migracja, 'upgrade', db)

    assert _odczytaj(db, 'users', uzytkownik.id, 'created_at', 'last_login', 'analytics_consent_date',
                     'deactivated_at') == {
        'created_at': datetime(2026, 7, 1, 18, 0),
        'last_login': datetime(2025, 10, 26, 0, 30),
        'analytics_consent_date': lato,             # wykluczona — już w UTC
        'deactivated_at': None,                     # NULL zostaje NULL
    }
    assert _odczytaj(db, 'orders', zamowienie.id, 'created_at', 'updated_at', 'status_changed_at') == {
        'created_at': datetime(2026, 1, 15, 19, 0),
        'updated_at': datetime(2026, 3, 29, 1, 30),
        'status_changed_at': None,
    }
    assert _odczytaj(db, 'notifications', powiadomienie.id, 'created_at') == {'created_at': datetime(2026, 7, 1, 18, 0)}
    assert _odczytaj(db, 'cart_items', koszyk.id, 'created_at', 'updated_at') == {'created_at': lato, 'updated_at': lato}
    assert _odczytaj(db, 'push_subscriptions', subskrypcja.id, 'created_at', 'last_used_at') == {
        'created_at': lato, 'last_used_at': lato}

    wypis = capsys.readouterr().out
    assert 'users.created_at: 1' in wypis
    assert 'users.deactivated_at: 0' in wypis
    assert 'orders.updated_at: 1' in wypis

    _uruchom(migracja, 'downgrade', db)

    assert _odczytaj(db, 'users', uzytkownik.id, 'created_at', 'last_login', 'analytics_consent_date',
                     'deactivated_at') == {
        'created_at': lato, 'last_login': jesien, 'analytics_consent_date': lato, 'deactivated_at': None}
    assert _odczytaj(db, 'orders', zamowienie.id, 'created_at', 'updated_at', 'status_changed_at') == {
        'created_at': zima,
        'updated_at': datetime(2026, 3, 29, 3, 30),   # nieistniejąca godzina wraca jako 3:30 (stratna)
        'status_changed_at': None,
    }
    assert _odczytaj(db, 'notifications', powiadomienie.id, 'created_at') == {'created_at': lato}
    assert _odczytaj(db, 'cart_items', koszyk.id, 'created_at', 'updated_at') == {'created_at': lato, 'updated_at': lato}


def test_migracja_wsadami_przelicza_kazdy_wiersz_raz(db, make_user, make_order, monkeypatch):
    uzytkownik = make_user()
    zamowienia = [make_order(uzytkownik) for _ in range(5)]
    for i, z in enumerate(zamowienia):
        _ustaw(db, 'orders', z.id, created_at=datetime(2026, 7, 1, 10 + i, 0), updated_at=None)

    migracja = _wczytaj_migracje()
    monkeypatch.setattr(migracja, 'WSAD', 2)
    _uruchom(migracja, 'upgrade', db)

    for i, z in enumerate(zamowienia):
        assert _odczytaj(db, 'orders', z.id, 'created_at', 'updated_at') == {
            'created_at': datetime(2026, 7, 1, 8 + i, 0), 'updated_at': None}


def test_migracja_po_aktualnym_headzie():
    migracja = _wczytaj_migracje()
    assert migracja.down_revision == 'c7a4d1e9f2b6'


def test_migracja_bez_importow_z_aplikacji():
    # Zamrożona kopia: zmiana modeli albo utils/ nie może zmienić wyniku tej migracji.
    import ast
    drzewo = ast.parse(PLIK_MIGRACJI.read_text(encoding='utf-8'))
    moduly = set()
    for wezel in ast.walk(drzewo):
        if isinstance(wezel, ast.Import):
            moduly |= {a.name.split('.')[0] for a in wezel.names}
        elif isinstance(wezel, ast.ImportFrom):
            moduly.add(wezel.module.split('.')[0])
    assert moduly <= {'datetime', 'zoneinfo', 'sqlalchemy', 'alembic'}, moduly


def test_migracja_przerywa_sie_na_nie_datetime_i_nic_nie_zostaje(db, make_user, make_order):
    # `orders` idzie przed `users` (kolejność KOLUMNY), więc zamówienie zostaje przeliczone,
    # zanim migracja trafi na zepsutą wartość — po wycofaniu transakcji musi wrócić do stanu sprzed.
    uzytkownik = make_user()
    zamowienie = make_order(uzytkownik)
    _ustaw(db, 'orders', zamowienie.id, created_at=datetime(2026, 7, 1, 20, 0), updated_at=None)
    db.session.execute(sa.text("UPDATE users SET created_at = 'to nie data' WHERE id = :id"), {'id': uzytkownik.id})
    db.session.commit()

    migracja = _wczytaj_migracje()
    # SQLite: parser typu DateTime odrzuca tekst sam (ValueError); MariaDB/PyMySQL oddaje zerową
    # datę jako str, którą łapie jawne sprawdzenie w migracji (RuntimeError).
    with pytest.raises((RuntimeError, ValueError)):
        _uruchom(migracja, 'upgrade', db)
    db.session.rollback()

    assert _odczytaj(db, 'orders', zamowienie.id, 'created_at') == {'created_at': datetime(2026, 7, 1, 20, 0)}


def test_migracja_odrzuca_tabele_bez_klucza_id(db, monkeypatch):
    db.session.execute(sa.text('CREATE TABLE czas_test_klucz (kod VARCHAR(10) PRIMARY KEY, kiedy DATETIME)'))
    db.session.execute(sa.text("INSERT INTO czas_test_klucz VALUES ('a', '2026-07-01 20:00:00.000000')"))

    migracja = _wczytaj_migracje()
    monkeypatch.setattr(migracja, 'KOLUMNY', {'czas_test_klucz': ['kiedy']})
    with pytest.raises(RuntimeError, match='klucz główny'):
        _uruchom(migracja, 'upgrade', db)
    db.session.rollback()
