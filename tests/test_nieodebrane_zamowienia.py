"""Testy listy nieodebranych zamówień (projekt 2026-09-02).

„Nieodebrane" = zamówienie w statusie pozwalającym zamówić wysyłkę, którego klient
nie wrzucił do żadnego zlecenia WYS/. Ta sama definicja, którą widzi klient u siebie —
testy pilnują, żeby oba widoki nie zaczęły pokazywać czegoś innego.
"""
import pytest


@pytest.fixture
def zamowienie_gotowe(db, make_user, make_order):
    """Zamówienie w statusie 'dostarczone_gom', bez zlecenia wysyłki."""
    def _make(user=None, **kwargs):
        u = user or make_user()
        return make_order(u, status='dostarczone_gom', **kwargs)
    return _make


def test_gotowe_bez_zlecenia_jest_nieodebrane(app, db, make_user, zamowienie_gotowe):
    from modules.client.shipping_service import unclaimed_orders_query

    o = zamowienie_gotowe()

    assert [z.id for z in unclaimed_orders_query().all()] == [o.id]


def test_zamowienie_w_zleceniu_znika_z_listy(app, db, make_user, zamowienie_gotowe):
    from modules.client.shipping_service import unclaimed_orders_query
    from modules.orders.models import ShippingRequest, ShippingRequestOrder

    o = zamowienie_gotowe()
    zlecenie = ShippingRequest(request_number='WYS/1', user_id=o.user_id)
    db.session.add(zlecenie)
    db.session.commit()
    db.session.add(ShippingRequestOrder(shipping_request_id=zlecenie.id, order_id=o.id))
    db.session.commit()

    assert unclaimed_orders_query().all() == []


def test_anulowane_nie_trafia_na_liste(app, db, make_user, make_order):
    from modules.client.shipping_service import unclaimed_orders_query

    make_order(make_user(), status='anulowane')

    assert unclaimed_orders_query().all() == []


def test_zmiana_ustawienia_statusow_przestawia_liste(app, db, make_user, make_order):
    """Lista czyta Settings, nie zaszytą stałą."""
    from modules.auth.models import Settings
    from modules.client.shipping_service import unclaimed_orders_query

    o = make_order(make_user(), status='spakowane')
    assert unclaimed_orders_query().all() == []

    db.session.add(Settings(key='shipping_request_allowed_statuses',
                            value='["spakowane"]'))
    db.session.commit()

    assert [z.id for z in unclaimed_orders_query().all()] == [o.id]


def test_parytet_ze_strefa_klienta(app, db, make_user, zamowienie_gotowe):
    """Admin i klient widzą ten sam zbiór zamówień tego klienta."""
    from modules.client.shipping_service import (
        get_available_orders, unclaimed_orders_query,
    )

    u = make_user()
    zamowienie_gotowe(user=u)
    zamowienie_gotowe(user=u)
    zamowienie_gotowe()  # inny klient — nie może wejść do porównania

    admin = {z.id for z in unclaimed_orders_query().filter_by(user_id=u.id).all()}
    klient = {z.id for z in get_available_orders(u.id)}

    assert admin == klient


# ============================================
# Stemplowanie daty zmiany statusu
# ============================================

def test_utworzenie_zamowienia_stempluje_date(app, db, make_user, make_order):
    """Nowe zamówienie też wchodzi w status — stempel powstaje od razu."""
    o = make_order(make_user(), status='nowe')

    assert o.status_changed_at is not None


def test_zmiana_statusu_przesuwa_date(app, db, make_user, make_order):
    """Listener działa niezależnie od tego, która trasa zmienia status."""
    from datetime import timedelta

    o = make_order(make_user(), status='nowe')
    o.status_changed_at = o.status_changed_at - timedelta(days=30)
    db.session.commit()
    stary_stempel = o.status_changed_at

    o.status = 'dostarczone_gom'
    db.session.commit()

    assert o.status_changed_at > stary_stempel


def test_edycja_innego_pola_nie_rusza_daty(app, db, make_user, make_order):
    """Notatka dopisana do zamówienia nie może „odmłodzić" zaległości."""
    o = make_order(make_user(), status='nowe')
    o.status = 'dostarczone_gom'
    db.session.commit()
    stempel = o.status_changed_at

    o.admin_notes = 'klient prosił o wstrzymanie'
    db.session.commit()

    assert o.status_changed_at == stempel


def test_przypisanie_tego_samego_statusu_nie_rusza_daty(app, db, make_user, make_order):
    o = make_order(make_user(), status='dostarczone_gom')
    o.status = 'dostarczone_gom'
    db.session.commit()
    stempel = o.status_changed_at

    o.status = 'dostarczone_gom'
    db.session.commit()

    assert o.status_changed_at == stempel


def test_migracja_statusu_celowo_nie_rusza_daty(app, db, make_user, make_order):
    """Świadoma decyzja: masowy update() w migrate_status omija listener.

    `migrate_status` przenosi zamówienia masowym `Order.query...update()`
    (synchronize_session=False), więc omija ORM i tym samym listener
    `_stempluj_zmiane_statusu` — to nie jest przeoczenie, tylko wybór
    opisany w docstringu listenera (modules/orders/models.py). Zmiana
    etykiety skasowanego statusu nie jest realnym krokiem zamówienia
    naprzód, więc odświeżanie stempla wyzerowałoby wiek zaległości. Ten
    test ma pilnować, żeby ktoś przypadkiem tego nie „naprawił".
    """
    from datetime import datetime

    o = make_order(make_user(), status='oczekujace')
    stary_stempel = datetime(2026, 1, 1, 12, 0, 0)
    o.status_changed_at = stary_stempel
    db.session.commit()

    from modules.orders.models import Order
    Order.query.filter_by(status='oczekujace').update(
        {'status': 'w_drodze_polska'},
        synchronize_session=False,
    )
    db.session.commit()

    db.session.refresh(o)
    assert o.status == 'w_drodze_polska'
    assert o.status_changed_at == stary_stempel


# ============================================
# Wiek zaległości
# ============================================

def test_wiek_z_kolumny_jest_dokladny(app, db, make_user, make_order):
    from datetime import timedelta
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import wiek_zaleglosci

    o = make_order(make_user(), status='dostarczone_gom')
    o.status_changed_at = get_local_now() - timedelta(days=47)
    db.session.commit()

    assert wiek_zaleglosci([o]) == {o.id: (47, True)}


def test_wiek_z_dziennika_jest_przyblizony(app, db, make_user, make_order):
    """Zamówienie sprzed wdrożenia — kolumna pusta, ale dziennik pamięta."""
    import json
    from datetime import timedelta
    from modules.admin.models import ActivityLog
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import wiek_zaleglosci

    o = make_order(make_user(), status='dostarczone_gom')
    o.status_changed_at = None
    db.session.add(ActivityLog(
        action='order_status_change', entity_type='order', entity_id=o.id,
        new_value=json.dumps({'status': 'dostarczone_gom'}),
        created_at=get_local_now() - timedelta(days=120),
    ))
    db.session.commit()

    assert wiek_zaleglosci([o]) == {o.id: (120, False)}


def test_dziennik_o_innym_statusie_jest_ignorowany(app, db, make_user, make_order):
    """Wpis o wejściu w JAKIŚ status nie mówi nic o wieku OBECNEJ zaległości."""
    import json
    from datetime import timedelta
    from modules.admin.models import ActivityLog
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import wiek_zaleglosci

    o = make_order(make_user(), status='dostarczone_gom')
    o.status_changed_at = None
    db.session.add(ActivityLog(
        action='order_status_change', entity_type='order', entity_id=o.id,
        new_value=json.dumps({'status': 'urzad_celny'}),
        created_at=get_local_now() - timedelta(days=200),
    ))
    db.session.commit()

    assert wiek_zaleglosci([o]) == {o.id: (None, False)}


def test_brak_obu_zrodel_daje_none(app, db, make_user, make_order):
    from modules.orders.unclaimed_service import wiek_zaleglosci

    o = make_order(make_user(), status='dostarczone_gom')
    o.status_changed_at = None
    db.session.commit()

    assert wiek_zaleglosci([o]) == {o.id: (None, False)}


def test_uszkodzony_wpis_dziennika_nie_wywraca_reszty(app, db, make_user, make_order):
    """Jeden wpis o `new_value`, który zdekoduje się do nie-słownika, ma być pominięty.

    `activity_log` to tabela współdzielona przez wielu piszących w systemie — nic nie
    gwarantuje, że każdy zapis do `new_value` jest obiektem JSON. `.get('status')` na
    czymkolwiek innym (np. na liście) rzuca AttributeError, który bez zabezpieczenia
    wywaliłby liczenie dla WSZYSTKICH zamówień w wywołaniu, nie tylko dla tego jednego
    wiersza.
    """
    import json
    from datetime import timedelta
    from modules.admin.models import ActivityLog
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import wiek_zaleglosci

    uszkodzone = make_order(make_user(), status='dostarczone_gom')
    uszkodzone.status_changed_at = None
    db.session.add(ActivityLog(
        action='order_status_change', entity_type='order', entity_id=uszkodzone.id,
        new_value='[1,2,3]',  # poprawny JSON, ale nie słownik — .get() by tu wybuchło
        created_at=get_local_now() - timedelta(days=10),
    ))

    zdrowe = make_order(make_user(), status='dostarczone_gom')
    zdrowe.status_changed_at = None
    db.session.add(ActivityLog(
        action='order_status_change', entity_type='order', entity_id=zdrowe.id,
        new_value=json.dumps({'status': 'dostarczone_gom'}),
        created_at=get_local_now() - timedelta(days=5),
    ))
    db.session.commit()

    wynik = wiek_zaleglosci([uszkodzone, zdrowe])

    assert wynik[uszkodzone.id] == (None, False)  # wpis pominięty, nie ma innego źródła
    assert wynik[zdrowe.id] == (5, False)  # sąsiedni wiersz policzony normalnie


def test_wiek_liczony_jednym_zapytaniem_dla_wielu(app, db, make_user, make_order):
    """Regresja na N+1: dziennik dociągany JEDNYM zapytaniem, niezależnie od liczby wierszy.

    Połowa z 30 zamówień ma wypełnioną kolumnę `status_changed_at` (zamówienia
    sprzed i po wdrożeniu współistnieją na produkcji), połowa ma kolumnę pustą i
    wpis w `ActivityLog` — tylko ta druga połowa w ogóle uruchamia zapytanie do
    dziennika (`if bez_kolumny:` w `wiek_zaleglosci`). Poprzednia wersja tego testu
    stemplowała WSZYSTKIE zamówienia kolumną, więc `bez_kolumny` był zawsze pusty,
    zapytanie do dziennika nigdy się nie wykonywało, a test przechodziłby tak samo
    przy zepsutym, nieobecnym albo N+1-owym fallbacku — sprawdzał tylko `len(wynik)`.

    Liczbę faktycznie wykonanych zapytań do `activity_log` mierzymy przez listener
    `before_cursor_execute` na silniku SQLAlchemy, więc regresja na N+1 (zapytanie w
    pętli po zamówieniach) zostanie złapana niezależnie od tego, jak zmieni się
    implementacja — asercja nie liczy wyników, tylko realny ruch do bazy.
    """
    from datetime import timedelta

    import json

    from sqlalchemy import event

    from modules.admin.models import ActivityLog
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import wiek_zaleglosci

    teraz = get_local_now()
    z_kolumny = []
    z_dziennika = []

    for i in range(15):
        o = make_order(make_user(), status='dostarczone_gom')
        o.status_changed_at = teraz - timedelta(days=i + 1)
        z_kolumny.append(o)

    for i in range(15):
        o = make_order(make_user(), status='dostarczone_gom')
        o.status_changed_at = None
        db.session.add(ActivityLog(
            action='order_status_change', entity_type='order', entity_id=o.id,
            new_value=json.dumps({'status': 'dostarczone_gom'}),
            created_at=teraz - timedelta(days=i + 100),
        ))
        z_dziennika.append(o)

    db.session.commit()

    zapytania_do_dziennika = []

    def _licz_zapytania(conn, cursor, statement, parameters, context, executemany):
        if 'activity_log' in statement:
            zapytania_do_dziennika.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _licz_zapytania)
    try:
        wynik = wiek_zaleglosci(z_kolumny + z_dziennika)
    finally:
        event.remove(db.engine, 'before_cursor_execute', _licz_zapytania)

    assert len(zapytania_do_dziennika) == 1, (
        f'oczekiwano jednego zapytania do activity_log, wykonano '
        f'{len(zapytania_do_dziennika)}: {zapytania_do_dziennika}'
    )

    assert len(wynik) == 30
    for i, o in enumerate(z_kolumny):
        assert wynik[o.id] == (i + 1, True)
    for i, o in enumerate(z_dziennika):
        assert wynik[o.id] == (i + 100, False)
