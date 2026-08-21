"""Anulowane zamówienie nie może blokować zlecenia wysyłki (BUG 1.3 z audytu).

Obie bramki awansu wymagają KOMPLETU zamówień:
- `update_sr_after_packing` — `all(o.status == 'spakowane')`,
- `_check_sr_auto_oplacone` — rozliczone E4 dla każdego wiersza junction.

Zamówienie `anulowane` / `do_zwrotu` nigdy żadnej nie spełni, a jednocześnie nie
wejdzie do sesji WMS (`_validate_orders_for_wms` wpuszcza tylko `dostarczone_gom`).
Mechanizm ratunkowy `odepnij_anulowane_zamowienie` istnieje, ale działa WYŁĄCZNIE
dla paczek zbiorczych — mimo że komentarz nad nim sam opisuje problem jako
strukturalny dla obu przypadków.

Efekt: zwykłe zlecenie z jednym anulowanym zamówieniem nie osiągnie ani
„opłacone", ani „spakowane". Wyjścia awaryjne są dwa i oba brzydkie: wysłać
trasą z sesji WMS albo skasować całe zlecenie razem z historią.

Naprawa liczy bramki po zamówieniach AKTYWNYCH zamiast wypinać wiersz junction —
historia zostaje w bazie, a `do_zwrotu` bywa cofane.
"""

import pytest


def _seed_sr_statuses(db):
    from modules.orders.models import ShippingRequestStatus
    for i, (slug, name) in enumerate([
        ('czeka_na_wycene', 'Czeka na wycenę'),
        ('czeka_na_oplacenie', 'Czeka na opłacenie'),
        ('oplacone', 'Opłacone'),
        ('spakowane', 'Spakowane'),
        ('wyslane', 'Wysłane'),
        ('dostarczone', 'Dostarczone'),
    ]):
        if ShippingRequestStatus.query.filter_by(slug=slug).first():
            continue
        db.session.add(ShippingRequestStatus(
            slug=slug, name=name, sort_order=i, is_active=True,
            is_initial=(slug == 'czeka_na_wycene')))
    db.session.commit()


def _zlecenie(db, user, make_order, statusy_zamowien, koszt=10, status_sr='czeka_na_oplacenie'):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status=status_sr)
    db.session.add(sr)
    db.session.flush()
    zamowienia = []
    for st in statusy_zamowien:
        o = make_order(user=user, status=st)
        o.shipping_cost = koszt
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
        zamowienia.append(o)
    db.session.commit()
    return sr, zamowienia


def _zatwierdz_e4(db, order, kwota=10):
    from modules.orders.models import PaymentConfirmation
    db.session.add(PaymentConfirmation(
        order_id=order.id, payment_stage='domestic_shipping',
        amount=kwota, status='approved'))
    db.session.commit()


# ---------------------------------------------------------------------------
# active_orders — jedyna definicja „zamówień, które jeszcze pojadą"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('status_martwy', ['anulowane', 'do_zwrotu'])
def test_active_orders_pomija_martwe_zamowienia(db, make_user, make_order, status_martwy):
    _seed_sr_statuses(db)
    user = make_user()
    sr, (zywe, martwe) = _zlecenie(
        db, user, make_order, ['dostarczone_gom', status_martwy])

    aktywne = {o.id for o in sr.active_orders}
    assert aktywne == {zywe.id}
    # `orders` zostaje kompletne — historia zlecenia się nie zmienia.
    assert {o.id for o in sr.orders} == {zywe.id, martwe.id}


def test_active_orders_bez_martwych_to_wszystkie(db, make_user, make_order):
    _seed_sr_statuses(db)
    user = make_user()
    sr, zamowienia = _zlecenie(db, user, make_order, ['dostarczone_gom', 'dostarczone_gom'])

    assert {o.id for o in sr.active_orders} == {o.id for o in zamowienia}


# ---------------------------------------------------------------------------
# Bramka opłacenia
# ---------------------------------------------------------------------------

def test_anulowane_zamowienie_nie_blokuje_oplacenia(db, make_user, make_order):
    """Zwykłe zlecenie — dotąd ratunek działał tylko dla paczek zbiorczych."""
    from modules.admin.payment_confirmations import _check_sr_auto_oplacone

    _seed_sr_statuses(db)
    user = make_user()
    sr, (zywe, anulowane) = _zlecenie(
        db, user, make_order, ['dostarczone_gom', 'anulowane'])
    _zatwierdz_e4(db, zywe)

    _check_sr_auto_oplacone(zywe)

    assert sr.status == 'oplacone', (
        'Anulowane zamówienie nie dostanie potwierdzenia płatności — '
        'nie może trzymać zlecenia w „czeka na opłacenie" na zawsze'
    )


def test_nieoplacone_zywe_zamowienie_nadal_blokuje(db, make_user, make_order):
    """Regresja: pomijamy martwe, nie rozluźniamy bramki."""
    from modules.admin.payment_confirmations import _check_sr_auto_oplacone

    _seed_sr_statuses(db)
    user = make_user()
    sr, (zywe_a, zywe_b) = _zlecenie(
        db, user, make_order, ['dostarczone_gom', 'dostarczone_gom'])
    _zatwierdz_e4(db, zywe_a)

    _check_sr_auto_oplacone(zywe_a)

    assert sr.status == 'czeka_na_oplacenie'


def test_zlecenie_z_samymi_anulowanymi_nie_awansuje(db, make_user, make_order):
    """Pusty zbiór aktywnych nie może przejść przez `all()` jako komplet."""
    from modules.admin.payment_confirmations import _check_sr_auto_oplacone

    _seed_sr_statuses(db)
    user = make_user()
    sr, (a, b) = _zlecenie(db, user, make_order, ['anulowane', 'anulowane'])

    _check_sr_auto_oplacone(a)

    assert sr.status == 'czeka_na_oplacenie', (
        'Zlecenie bez żywych zamówień nie ma czego wysłać — nie awansuje'
    )


# ---------------------------------------------------------------------------
# Bramka pakowania
# ---------------------------------------------------------------------------

def test_anulowane_zamowienie_nie_blokuje_pakowania(db, make_user, make_order):
    from modules.orders.wms_packing import update_sr_after_packing

    _seed_sr_statuses(db)
    user = make_user()
    sr, (spakowane, anulowane) = _zlecenie(
        db, user, make_order, ['spakowane', 'anulowane'], status_sr='oplacone')

    # Funkcja przyjmuje ZAMÓWIENIE, które właśnie spakowano, i sama znajduje zlecenie.
    update_sr_after_packing(spakowane)

    assert sr.status == 'spakowane'


def test_niespakowane_zywe_zamowienie_nadal_blokuje(db, make_user, make_order):
    """Regresja: magazyn nie może zamknąć zlecenia z nieskompletowaną pozycją."""
    from modules.orders.wms_packing import update_sr_after_packing

    _seed_sr_statuses(db)
    user = make_user()
    sr, (spakowane, w_toku) = _zlecenie(
        db, user, make_order, ['spakowane', 'dostarczone_gom'], status_sr='oplacone')

    update_sr_after_packing(spakowane)

    assert sr.status == 'oplacone'


def test_zlecenie_z_samymi_anulowanymi_nie_pakuje_sie(db, make_user, make_order):
    from modules.orders.wms_packing import update_sr_after_packing

    _seed_sr_statuses(db)
    user = make_user()
    sr, (anulowane,) = _zlecenie(db, user, make_order, ['anulowane'], status_sr='oplacone')

    update_sr_after_packing(anulowane)

    assert sr.status == 'oplacone'


# ---------------------------------------------------------------------------
# Wysyłka — anulowane zamówienie nie jedzie
#
# `ship_shipping_request` iterowała po `sr.orders` bez filtra statusu, więc
# anulowane zamówienie dostawało status „wysłane" i wpis OrderShipment z numerem
# przesyłki — czyli ślad nadania czegoś, czego fizycznie w kartonie nie ma.
# ---------------------------------------------------------------------------

def test_wysylka_nie_oznacza_anulowanego_jako_wyslane(app, db, make_user, make_order):
    from modules.orders.wms_utils import ship_shipping_request

    _seed_sr_statuses(db)
    user = make_user()
    sr, (zywe, anulowane) = _zlecenie(
        db, user, make_order, ['spakowane', 'anulowane'], status_sr='spakowane')
    # Zlecenie gotowe do wysyłki jest opłacone — bramka płatności liczy z danych
    # (patrz tests/test_bramka_platnosci_wysylki.py). Anulowane zamówienie nie
    # wymaga zapłaty, bo nie jedzie w kartonie.
    _zatwierdz_e4(db, zywe)

    ship_shipping_request(sr, courier='inpost', tracking_number='6200000000009')

    db.session.expire_all()
    assert zywe.status == 'wyslane'
    assert anulowane.status == 'anulowane', (
        'Anulowane zamówienie nie jedzie w kartonie — nie może dostać statusu wysłane'
    )


def test_wysylka_nie_tworzy_wpisu_przesylki_dla_anulowanego(app, db, make_user, make_order):
    from modules.orders.models import OrderShipment
    from modules.orders.wms_utils import ship_shipping_request

    _seed_sr_statuses(db)
    user = make_user()
    sr, (zywe, anulowane) = _zlecenie(
        db, user, make_order, ['spakowane', 'anulowane'], status_sr='spakowane')
    _zatwierdz_e4(db, zywe)

    ship_shipping_request(sr, courier='inpost', tracking_number='6200000000010')

    db.session.expire_all()
    numery = {w.order_id for w in OrderShipment.query.filter_by(
        tracking_number='6200000000010').all()}
    assert numery == {zywe.id}, (
        'Wpis przesyłki dla anulowanego zamówienia to ślad nadania czegoś, '
        'czego w paczce nie ma'
    )
