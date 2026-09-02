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


# ============================================
# Agregacja ekranu
# ============================================

def _pozycja(db, order, product=None, nazwa=None, qty=1):
    from decimal import Decimal
    from modules.orders.models import OrderItem

    it = OrderItem(
        order_id=order.id,
        product_id=product.id if product else None,
        custom_name=nazwa,
        is_custom=product is None,
        quantity=qty,
        price=Decimal('100.00'),
        total=Decimal('100.00') * qty,
    )
    db.session.add(it)
    db.session.commit()
    return it


def test_klient_z_trzema_zamowieniami_to_jeden_wiersz(app, db, make_user, make_order):
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    u = make_user()
    for _ in range(3):
        make_order(u, status='dostarczone_gom')

    dane = zbierz_nieodebrane()

    assert len(dane['klienci']) == 1
    assert dane['klienci'][0]['user'].id == u.id
    assert len(dane['klienci'][0]['zamowienia']) == 3


def test_klienci_sortowani_od_najstarszej_zaleglosci(app, db, make_user, make_order):
    from datetime import timedelta
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    swiezy = make_user(email='swiezy@example.com')
    stary = make_user(email='stary@example.com')
    o1 = make_order(swiezy, status='dostarczone_gom')
    o2 = make_order(stary, status='dostarczone_gom')
    o1.status_changed_at = get_local_now() - timedelta(days=3)
    o2.status_changed_at = get_local_now() - timedelta(days=90)
    db.session.commit()

    dane = zbierz_nieodebrane()

    assert [k['user'].id for k in dane['klienci']] == [stary.id, swiezy.id]
    assert dane['klienci'][0]['dni'] == 90


def test_produkty_sumuja_sztuki_i_licza_klientow(app, db, make_user, make_order,
                                                  make_product):
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    ls = make_product(name='Light stick ATEEZ')
    for qty in (2, 3):
        o = make_order(make_user(), status='dostarczone_gom')
        _pozycja(db, o, product=ls, qty=qty)

    dane = zbierz_nieodebrane()

    assert len(dane['produkty']) == 1
    assert dane['produkty'][0]['nazwa'] == 'Light stick ATEEZ'
    assert dane['produkty'][0]['sztuk'] == 5
    assert dane['produkty'][0]['klientow'] == 2


def test_ten_sam_klient_liczony_raz_na_produkt(app, db, make_user, make_order,
                                                make_product):
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    ls = make_product(name='Light stick ATEEZ')
    u = make_user()
    for _ in range(2):
        o = make_order(u, status='dostarczone_gom')
        _pozycja(db, o, product=ls, qty=1)

    dane = zbierz_nieodebrane()

    assert dane['produkty'][0]['sztuk'] == 2
    assert dane['produkty'][0]['klientow'] == 1


def test_pozycje_wlasne_ida_na_koniec(app, db, make_user, make_order, make_product):
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    o1 = make_order(make_user(), status='dostarczone_gom')
    _pozycja(db, o1, nazwa='Zestaw niespodzianka', qty=99)
    o2 = make_order(make_user(), status='dostarczone_gom')
    _pozycja(db, o2, product=make_product(name='Album TXT'), qty=1)

    dane = zbierz_nieodebrane()

    assert [p['wlasny'] for p in dane['produkty']] == [False, True]
    assert dane['produkty'][1]['nazwa'] == 'Zestaw niespodzianka'


def test_klient_bez_wieku_jest_pierwszy(app, db, make_user, make_order):
    """Klient bez policzalnego wieku ma stać PRZED klientem z konkretną liczbą dni.

    `zbierz_nieodebrane` sortuje kluczem `float('inf') if dni is None else dni`
    z `reverse=True` — brak śladu po zmianie statusu (`status_changed_at=None`
    i żaden pasujący wpis w `ActivityLog`) ma znaczyć „leży najdłużej", nie
    „leży najkrócej". Gdyby ktoś podmienił `float('inf')` na `-1`, klient bez
    wieku spadłby na sam dół listy — dokładne przeciwieństwo zamierzonego
    zachowania — a żaden dotychczasowy test by tego nie złapał, bo
    `test_klienci_sortowani_od_najstarszej_zaleglosci` porównuje wyłącznie
    dwie policzalne liczby dni.
    """
    from datetime import timedelta
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    bez_wieku = make_user(email='bez-wieku@example.com')
    z_wiekiem = make_user(email='z-wiekiem@example.com')

    o_bez_wieku = make_order(bez_wieku, status='dostarczone_gom')
    o_bez_wieku.status_changed_at = None
    db.session.commit()

    o_z_wiekiem = make_order(z_wiekiem, status='dostarczone_gom')
    o_z_wiekiem.status_changed_at = get_local_now() - timedelta(days=90)
    db.session.commit()

    dane = zbierz_nieodebrane()

    assert [k['user'].id for k in dane['klienci']] == [bez_wieku.id, z_wiekiem.id]
    assert dane['klienci'][0]['dni'] is None


def test_dokladne_false_gdy_jedno_zamowienie_ma_wiek_przyblizony(
    app, db, make_user, make_order,
):
    """Jedna niepewna data w wierszu klienta ma ustawić `dokladne=False` na CAŁYM wierszu.

    Klient ma dwa zamówienia: jedno z wiekiem dokładnym (kolumna
    `status_changed_at`), drugie z wiekiem przybliżonym (kolumna pusta, wiek
    z `ActivityLog`). Regresja usuwająca `if not dokladne: wpis['dokladne'] =
    False` w `zbierz_nieodebrane` przeszłaby niezauważona przez wszystkie
    dotychczasowe testy — żaden nie czyta klucza `dokladne` z wyniku.
    """
    import json
    from datetime import timedelta
    from modules.admin.models import ActivityLog
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    u = make_user()

    dokladne_zam = make_order(u, status='dostarczone_gom')
    dokladne_zam.status_changed_at = get_local_now() - timedelta(days=10)
    db.session.commit()

    przyblizone_zam = make_order(u, status='dostarczone_gom')
    przyblizone_zam.status_changed_at = None
    db.session.add(ActivityLog(
        action='order_status_change', entity_type='order',
        entity_id=przyblizone_zam.id,
        new_value=json.dumps({'status': 'dostarczone_gom'}),
        created_at=get_local_now() - timedelta(days=5),
    ))
    db.session.commit()

    dane = zbierz_nieodebrane()

    assert len(dane['klienci']) == 1
    assert dane['klienci'][0]['dokladne'] is False


def test_dokladne_true_gdy_wszystkie_zamowienia_maja_wiek_z_kolumny(
    app, db, make_user, make_order,
):
    """Przypadek kontrolny do testu powyżej: same dokładne wieki dają `dokladne=True`.

    Bez tego testu poprzedni (sprawdzający tylko `dokladne is False`) nie
    odróżniałby prawdziwej logiki „jedna niepewność brudzi wiersz" od zepsutej
    wersji, która ustawia `dokladne=False` zawsze, niezależnie od danych.
    """
    from datetime import timedelta
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    u = make_user()
    for dni in (10, 20):
        o = make_order(u, status='dostarczone_gom')
        o.status_changed_at = get_local_now() - timedelta(days=dni)
        db.session.commit()

    dane = zbierz_nieodebrane()

    assert len(dane['klienci']) == 1
    assert dane['klienci'][0]['dokladne'] is True


def test_ostatnie_przypomnienie_to_najnowsza_data(app, db, make_user, make_order):
    """Wiersz klienta ma pokazać NAJNOWSZE `pickup_reminder_sent_at` spośród jego zamówień.

    Klient ma trzy zamówienia — jedno bez przypomnienia (`None`, ma zostać
    zignorowane) i dwa z różnymi datami — żeby odwrócone porównanie (`<`
    zamiast `>` w `zbierz_nieodebrane`) dawało inny wynik niż poprawne i test
    faktycznie na tym łapał regresję, a nie tylko sprawdzał obecność wartości.
    """
    from datetime import timedelta
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    u = make_user()
    teraz = get_local_now()

    make_order(u, status='dostarczone_gom', pickup_reminder_sent_at=None)
    make_order(u, status='dostarczone_gom',
               pickup_reminder_sent_at=teraz - timedelta(days=5))
    najnowsze = teraz - timedelta(days=1)
    make_order(u, status='dostarczone_gom', pickup_reminder_sent_at=najnowsze)

    dane = zbierz_nieodebrane()

    assert len(dane['klienci']) == 1
    assert dane['klienci'][0]['ostatnie_przypomnienie'] == najnowsze


def test_pusta_baza_nie_wywraca_ekranu(app, db):
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    assert zbierz_nieodebrane() == {'klienci': [], 'produkty': []}


# ============================================
# Ekran admina
# ============================================

def test_ekran_wymaga_admina(app, client, db, make_user, login):
    login(make_user(role='client'))

    r = client.get('/admin/orders/nieodebrane')

    assert r.status_code in (302, 403)


def test_ekran_pokazuje_klienta_i_produkt(app, client, db, make_user, make_order,
                                           make_product, login):
    login(make_user(role='admin', email='admin@example.com'))
    o = make_order(make_user(email='zalegacz@example.com'), status='dostarczone_gom')
    _pozycja(db, o, product=make_product(name='Light stick ATEEZ'), qty=5)

    r = client.get('/admin/orders/nieodebrane')

    assert r.status_code == 200
    tresc = r.get_data(as_text=True)
    assert 'zalegacz@example.com' in tresc
    assert 'Light stick ATEEZ' in tresc


def test_ekran_bez_zaleglosci_nie_wywala_sie(app, client, db, make_user, login):
    login(make_user(role='admin', email='admin@example.com'))

    r = client.get('/admin/orders/nieodebrane')

    assert r.status_code == 200
