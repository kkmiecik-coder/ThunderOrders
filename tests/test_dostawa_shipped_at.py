"""shipped_at — moment wysyłki jako punkt odniesienia dla przypomnień i automatu."""
from contextlib import contextmanager
from datetime import datetime, timedelta


@contextmanager
def _zliczone_selecty(db):
    """Liczy SELECT-y puszczone na bazę w obrębie bloku.

    Podpina się pod `before_cursor_execute`, czyli widzi KAŻDE zapytanie, także te
    z leniwych relacji — a o to tu chodzi: pilnujemy, żeby liczba zapytań backfillu
    nie zależała od liczby kandydatów. INSERT/UPDATE pomijamy świadomie, bo tych
    z definicji jest tyle, ile uzupełnionych wierszy.
    """
    from sqlalchemy import event

    selecty = []

    def _zapisz(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            selecty.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _zapisz)
    try:
        yield selecty
    finally:
        event.remove(db.engine, 'before_cursor_execute', _zapisz)


def _zlecenie(db, user, status='spakowane'):
    from modules.orders.models import ShippingRequest
    sr = ShippingRequest(
        request_number=f'WYS/{user.id:06d}', user_id=user.id, status=status)
    db.session.add(sr)
    db.session.commit()
    return sr


def test_wysylka_zapisuje_shipped_at(app, db, make_user):
    from modules.orders.wms_utils import ship_shipping_request

    user = make_user()
    sr = _zlecenie(db, user)

    przed = datetime.now() - timedelta(seconds=5)
    ship_shipping_request(sr, courier='inpost', tracking_number='123456789')

    assert sr.status == 'wyslane'
    assert sr.shipped_at is not None
    assert sr.shipped_at >= przed


def test_nowe_zlecenie_nie_ma_shipped_at(app, db, make_user):
    user = make_user()
    sr = _zlecenie(db, user)
    assert sr.shipped_at is None
    assert sr.delivered_at is None
    assert sr.delivered_source is None
    assert sr.delivery_reminder_sent_at is None


def test_backfill_bierze_date_z_logu_aktywnosci(app, db, make_user):
    from modules.admin.models import ActivityLog
    from modules.orders.delivery_backfill import odtworz_shipped_at

    user = make_user()
    sr = _zlecenie(db, user, status='wyslane')
    kiedy = datetime.now() - timedelta(days=20)
    db.session.add(ActivityLog(
        action='shipping_request_shipped', entity_type='shipping_request',
        entity_id=sr.id, created_at=kiedy))
    db.session.commit()

    wynik = odtworz_shipped_at()

    assert wynik['z_logu'] == 1
    assert abs((sr.shipped_at - kiedy).total_seconds()) < 1


def test_backfill_schodzi_na_date_przesylki(app, db, make_user, make_order):
    from modules.orders.models import OrderShipment, ShippingRequestOrder
    from modules.orders.delivery_backfill import odtworz_shipped_at

    user = make_user()
    sr = _zlecenie(db, user, status='wyslane')
    order = make_order(user, status='wyslane')
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=order.id))
    kiedy = datetime.now() - timedelta(days=15)
    db.session.add(OrderShipment(
        order_id=order.id, tracking_number='X1', courier='inpost', created_at=kiedy))
    db.session.commit()

    wynik = odtworz_shipped_at()

    assert wynik['z_przesylek'] == 1
    assert abs((sr.shipped_at - kiedy).total_seconds()) < 1


def test_backfill_nie_rusza_zlecen_nigdy_niewyslanych(app, db, make_user):
    from modules.orders.delivery_backfill import odtworz_shipped_at

    user = make_user()
    sr = _zlecenie(db, user, status='czeka_na_wycene')

    odtworz_shipped_at()

    assert sr.shipped_at is None


def test_backfill_jest_idempotentny(app, db, make_user):
    from modules.orders.delivery_backfill import odtworz_shipped_at

    user = make_user()
    sr = _zlecenie(db, user, status='wyslane')
    sr.updated_at = datetime.now() - timedelta(days=30)
    db.session.commit()

    pierwszy = odtworz_shipped_at()
    zapisana = sr.shipped_at
    drugi = odtworz_shipped_at()

    assert pierwszy['z_updated_at'] == 1
    assert sum(drugi.values()) == 0
    assert sr.shipped_at == zapisana


def test_backfill_wielu_kandydatow_nie_miesza_zrodel(app, db, make_user, make_order):
    """Dług #6 (G4-cron): backfill robił dwa zapytania NA ZLECENIE (log +
    przesyłka) zamiast zbiorczych. Po przejściu na GROUP BY/MIN kluczowe jest, żeby
    wynik per zlecenie dalej trafiał do WŁAŚCIWEGO wiersza — trzej kandydaci, każdy
    z innego źródła kaskady, muszą dostać każdy SWOJĄ datę, nie datę sąsiada."""
    from modules.admin.models import ActivityLog
    from modules.orders.models import OrderShipment, ShippingRequestOrder, ShippingRequest
    from modules.orders.delivery_backfill import odtworz_shipped_at

    user_a, user_b, user_c = make_user(), make_user(), make_user()

    sr_log = ShippingRequest(request_number='WYS/000601', user_id=user_a.id, status='wyslane')
    sr_przesylka = ShippingRequest(request_number='WYS/000602', user_id=user_b.id, status='wyslane')
    sr_updated = ShippingRequest(request_number='WYS/000603', user_id=user_c.id, status='wyslane')
    db.session.add_all([sr_log, sr_przesylka, sr_updated])
    db.session.commit()

    kiedy_log = datetime.now() - timedelta(days=25)
    db.session.add(ActivityLog(
        action='shipping_request_shipped', entity_type='shipping_request',
        entity_id=sr_log.id, created_at=kiedy_log))

    order = make_order(user_b, status='wyslane')
    db.session.add(ShippingRequestOrder(shipping_request_id=sr_przesylka.id, order_id=order.id))
    kiedy_przesylka = datetime.now() - timedelta(days=18)
    db.session.add(OrderShipment(
        order_id=order.id, tracking_number='X9', courier='inpost', created_at=kiedy_przesylka))
    db.session.commit()

    kiedy_updated = datetime.now() - timedelta(days=12)
    sr_updated.updated_at = kiedy_updated
    db.session.commit()

    with _zliczone_selecty(db) as selecty:
        wynik = odtworz_shipped_at()

    # sr_updated.updated_at NIE nadaje się tu jako punkt odniesienia po fakcie:
    # backfill sam robi UPDATE na tym wierszu (ustawia shipped_at), więc kolumna z
    # onupdate=get_local_now przestawia się na „teraz" przy TYM SAMYM commicie —
    # porównujemy więc do wartości złapanej PRZED wywołaniem odtworz_shipped_at().
    assert wynik == {'z_logu': 1, 'z_przesylek': 1, 'z_updated_at': 1}
    assert abs((sr_log.shipped_at - kiedy_log).total_seconds()) < 1
    assert abs((sr_przesylka.shipped_at - kiedy_przesylka).total_seconds()) < 1
    assert abs((sr_updated.shipped_at - kiedy_updated).total_seconds()) < 1

    # Sedno tej naprawy było WYDAJNOŚCIOWE, a same asercje na daty przechodzą tak
    # samo dla wersji per-wiersz — bez tej asercji powrót do N+1 zostawiłby test
    # zielony (sprawdzone: cofnięcie backfillu do pętli per-wiersz zostawia
    # wszystkie asercje wyżej zielone i pada dopiero tutaj).
    # Trzy SELECT-y i ani jednego więcej — kandydaci, MIN() z activity_log, MIN()
    # z przesyłek — i ta trójka NIE rośnie z liczbą kandydatów. Wersja per-wiersz
    # robiła 1 + N + (ilu bez wpisu w logu), czyli tu zmierzone 6, a na jednorazowym
    # przebiegu po wdrożeniu (~1800 zaległych zleceń) do ~3600.
    assert len(selecty) == 3, (
        'liczba zapytań backfillu musi być STAŁA, niezależna od liczby '
        f'kandydatów — poszło {len(selecty)}: ' + ' | '.join(
            ' '.join(s.split())[:90] for s in selecty))


# ---------------------------------------------------------------------------
# Ręczna zmiana statusu na „wysłane" (etap 8 audytu)
#
# `_sync_order_statuses_from_shipping_request` miała własną, uboższą kopię
# przejścia: ustawiała status zamówień, ale NIE zapisywała shipped_at, NIE
# tworzyła OrderShipment i wysyłała notify_status_change PER ZAMÓWIENIE.
# Skutki: zlecenie w „wysłane" z pustym shipped_at jest niewidoczne dla crona
# dostaw (filtruje shipped_at.isnot(None)), a klient z trzema zamówieniami
# w jednym kartonie dostawał trzy maile.
# Gałąź 'dostarczone' tej samej funkcji od dawna deleguje do dostarcz_zlecenie().
# ---------------------------------------------------------------------------

def _admin(make_user):
    return make_user(role='admin')


def _zlecenie_z_zamowieniami(db, user, make_order, ile=3):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    sr = ShippingRequest(
        request_number=f'WYS/{user.id:06d}', user_id=user.id, status='oplacone')
    db.session.add(sr)
    db.session.flush()
    for _ in range(ile):
        o = make_order(user=user, status='dostarczone_gom')
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
    db.session.commit()
    return sr


def test_reczna_zmiana_na_wyslane_zapisuje_shipped_at(
        app, db, client, login, make_user, make_order):
    user = make_user()
    sr = _zlecenie_z_zamowieniami(db, user, make_order, ile=1)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}', json={'status': 'wyslane'})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert sr.status == 'wyslane'
    assert sr.shipped_at is not None, (
        'Bez shipped_at cron dostaw nie zobaczy zlecenia — ani przypomnienie, '
        'ani automatyczne domknięcie nie zadziała'
    )


def test_reczna_zmiana_na_wyslane_tworzy_wpis_przesylki(
        app, db, client, login, make_user, make_order):
    from modules.orders.models import OrderShipment

    user = make_user()
    sr = _zlecenie_z_zamowieniami(db, user, make_order, ile=2)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}', json={
        'status': 'wyslane', 'tracking_number': '6200000000001', 'courier': 'inpost',
    })

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    wpisy = OrderShipment.query.filter_by(tracking_number='6200000000001').all()
    assert len(wpisy) == 2, (
        f'Każde zamówienie w paczce dostaje wpis przesyłki; jest {len(wpisy)}'
    )


def test_reczna_zmiana_na_wyslane_wysyla_jeden_mail_na_paczke(
        app, db, client, login, make_user, make_order, monkeypatch):
    """Klient dostaje fizycznie JEDEN karton — nie trzy maile."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    maile = []
    monkeypatch.setattr(EmailManager, 'notify_shipment_sent',
                        staticmethod(lambda sr, **kw: maile.append(('paczka', sr.id))))
    monkeypatch.setattr(EmailManager, 'notify_status_change',
                        staticmethod(lambda o, *a, **kw: maile.append(('zamowienie', o.id))))
    monkeypatch.setattr(PushManager, 'notify_shipment_sent',
                        staticmethod(lambda *a, **kw: None))
    monkeypatch.setattr(PushManager, 'notify_status_change',
                        staticmethod(lambda *a, **kw: None))

    user = make_user()
    sr = _zlecenie_z_zamowieniami(db, user, make_order, ile=3)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}', json={
        'status': 'wyslane', 'tracking_number': '6200000000002', 'courier': 'inpost',
    })

    assert r.status_code == 200, r.get_json()
    per_zamowienie = [m for m in maile if m[0] == 'zamowienie']
    assert per_zamowienie == [], (
        f'Trzy zamówienia w jednym kartonie = trzy maile do klienta; wysłano '
        f'{len(per_zamowienie)} powiadomień per zamówienie'
    )
    assert [m for m in maile if m[0] == 'paczka'], 'Jeden mail na paczkę musi pójść'
