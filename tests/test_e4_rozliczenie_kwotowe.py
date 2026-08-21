"""E4 rozliczone po KWOCIE, nie po istnieniu zatwierdzonego wiersza (BUG K1).

`PaymentConfirmation` wiąże się z ZAMÓWIENIEM (`order_id` + `payment_stage`), ale
zobowiązanie powstaje per ZLECENIE WYSYŁKI. Zamówienie ma więc jedno gniazdo na
E4 na całe życie, a przez zlecenia może przejść wielokrotnie — po skasowaniu
zlecenia, po wypięciu z paczki, po ponownym złożeniu.

Sedno jest jednak szersze niż samo gniazdo: predykat pytał o ISTNIENIE wiersza
`approved`, nie o zapłaconą kwotę. Ta sama awaria zachodzi więc bez kasowania
czegokolwiek — wystarczy podnieść `shipping_cost` po zatwierdzeniu płatności.

Dwie gałęzie:

DEADLOCK — klient nie ma jak zapłacić za nową przesyłkę, bo `can_upload_stage_4`
widzi stare `approved`. Admin też nie pomoże: rejestracja wpłaty zwracała 409.

DARMOWY PRZEJAZD — zatwierdzone 20 zł „rozlicza" należność 30 zł, zlecenie
przechodzi na „opłacone" i paczka wychodzi bez dopłaty. Sprzedawca traci różnicę
bez żadnego śladu.

Naprawa: rozliczenie liczy SUMĘ zatwierdzonych kwot E4 wobec należności, a przy
niedopłacie klient znów może wgrać dowód — na kwotę pozostałą.
"""

from decimal import Decimal

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


def _zatwierdz_e4(db, order, kwota):
    from modules.orders.models import PaymentConfirmation
    conf = PaymentConfirmation(
        order_id=order.id, payment_stage='domestic_shipping',
        amount=Decimal(str(kwota)), status='approved')
    db.session.add(conf)
    order.paid_amount = (order.paid_amount or Decimal('0.00')) + Decimal(str(kwota))
    db.session.commit()
    return conf


# ---------------------------------------------------------------------------
# Predykat rozliczenia — po kwocie
# ---------------------------------------------------------------------------

def test_niedoplata_nie_jest_rozliczeniem(db, make_user, make_order):
    """Sedno gałęzi „darmowy przejazd": 20 zł nie pokrywa należności 30 zł."""
    o = make_order(user=make_user())
    o.shipping_cost = Decimal('20.00')
    db.session.commit()
    _zatwierdz_e4(db, o, 20)

    # Admin koryguje wycenę w górę — bez kasowania czegokolwiek.
    o.shipping_cost = Decimal('30.00')
    db.session.commit()

    assert o.is_domestic_shipping_settled is False, (
        'Zatwierdzone 20 zł nie może rozliczać należności 30 zł — paczka '
        'wyjechałaby bez dopłaty, a sprzedawca straciłby różnicę bez śladu'
    )


def test_pelna_kwota_jest_rozliczeniem(db, make_user, make_order):
    o = make_order(user=make_user())
    o.shipping_cost = Decimal('30.00')
    db.session.commit()
    _zatwierdz_e4(db, o, 30)

    assert o.is_domestic_shipping_settled is True


def test_nadplata_jest_rozliczeniem(db, make_user, make_order):
    """Klient zapłacił więcej, niż trzeba — należność pokryta."""
    o = make_order(user=make_user())
    o.shipping_cost = Decimal('20.00')
    db.session.commit()
    _zatwierdz_e4(db, o, 25)

    assert o.is_domestic_shipping_settled is True


def test_doplata_sumuje_sie_do_rozliczenia(db, make_user, make_order):
    """Dwa zatwierdzone potwierdzenia razem pokrywają należność."""
    o = make_order(user=make_user())
    o.shipping_cost = Decimal('30.00')
    db.session.commit()
    _zatwierdz_e4(db, o, 20)
    _zatwierdz_e4(db, o, 10)

    assert o.is_domestic_shipping_settled is True


def test_zero_zlotych_nadal_rozliczone(db, make_user, make_order):
    """Regresja: część „0 zł = rozliczone" musi zostać nietknięta."""
    o = make_order(user=make_user())
    o.shipping_cost = Decimal('0.00')
    db.session.commit()

    assert o.is_domestic_shipping_settled is True


def test_potwierdzenie_oczekujace_nie_rozlicza(db, make_user, make_order):
    """Regresja: 'pending' nie wystarcza, liczą się tylko zatwierdzone kwoty."""
    from modules.orders.models import PaymentConfirmation
    o = make_order(user=make_user())
    o.shipping_cost = Decimal('30.00')
    db.session.add(PaymentConfirmation(
        order_id=o.id, payment_stage='domestic_shipping',
        amount=Decimal('30.00'), status='pending'))
    db.session.commit()

    assert o.is_domestic_shipping_settled is False


# ---------------------------------------------------------------------------
# Możliwość dopłaty — gałąź „deadlock"
# ---------------------------------------------------------------------------

def test_klient_moze_doplacic_przy_niedoplacie(db, make_user, make_order):
    """Bez tego klient nie ma jak zapłacić za nową, droższą przesyłkę."""
    o = make_order(user=make_user())
    o.shipping_cost = Decimal('20.00')
    db.session.commit()
    _zatwierdz_e4(db, o, 20)

    o.shipping_cost = Decimal('35.00')
    db.session.commit()

    assert o.can_upload_stage_4 is True, (
        'Stare zatwierdzone potwierdzenie zamykało drogę zapłaty za nową należność'
    )


def test_klient_nie_placi_gdy_rozliczone(db, make_user, make_order):
    """Regresja: w pełni rozliczony etap nie prosi o kolejną wpłatę."""
    o = make_order(user=make_user())
    o.shipping_cost = Decimal('30.00')
    db.session.commit()
    _zatwierdz_e4(db, o, 30)

    assert o.can_upload_stage_4 is False


def test_klient_nie_placi_gdy_weryfikacja_w_toku(db, make_user, make_order):
    """Regresja: 'pending' blokuje, żeby nie mnożyć dowodów na tę samą kwotę."""
    from modules.orders.models import PaymentConfirmation
    o = make_order(user=make_user())
    o.shipping_cost = Decimal('30.00')
    db.session.add(PaymentConfirmation(
        order_id=o.id, payment_stage='domestic_shipping',
        amount=Decimal('30.00'), status='pending'))
    db.session.commit()

    assert o.can_upload_stage_4 is False


def test_kwota_do_zaplaty_to_roznica(db, make_user, make_order):
    """Klient dopłaca RÓŻNICĘ, nie pełną kwotę drugi raz."""
    from modules.client.payment_confirmation_service import stage_amount

    o = make_order(user=make_user())
    o.shipping_cost = Decimal('30.00')
    db.session.commit()
    _zatwierdz_e4(db, o, 20)

    assert stage_amount(o, 'domestic_shipping') == Decimal('10.00')


def test_kwota_do_zaplaty_bez_wplat_to_calosc(db, make_user, make_order):
    from modules.client.payment_confirmation_service import stage_amount

    o = make_order(user=make_user())
    o.shipping_cost = Decimal('30.00')
    db.session.commit()

    assert stage_amount(o, 'domestic_shipping') == Decimal('30.00')


# ---------------------------------------------------------------------------
# Bramka zlecenia — pełny scenariusz „darmowego przejazdu"
# ---------------------------------------------------------------------------

def test_zlecenie_nie_domyka_sie_przy_niedoplacie(db, make_user, make_order):
    """Odtworzenie gałęzi B: zlecenie nie może przejść na „opłacone",
    gdy jedno z zamówień ma zaległą dopłatę."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    from modules.admin.payment_confirmations import _check_sr_auto_oplacone

    _seed_sr_statuses(db)
    user = make_user()
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status='czeka_na_oplacenie')
    db.session.add(sr)
    db.session.flush()

    stare = make_order(user=user, status='dostarczone_gom')
    stare.shipping_cost = Decimal('20.00')
    nowe = make_order(user=user, status='dostarczone_gom')
    nowe.shipping_cost = Decimal('30.00')
    for o in (stare, nowe):
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
    db.session.commit()

    # Stare zamówienie ma potwierdzenie z POPRZEDNIEJ, tańszej przesyłki.
    _zatwierdz_e4(db, stare, 20)
    stare.shipping_cost = Decimal('30.00')
    db.session.commit()
    # Klient płaci tylko za nowe zamówienie.
    _zatwierdz_e4(db, nowe, 30)

    _check_sr_auto_oplacone(nowe)

    assert sr.status == 'czeka_na_oplacenie', (
        'Zlecenie z niedopłatą 10 zł nie może przejść na „opłacone" — paczka '
        'wyszłaby, a różnica przepadłaby bez śladu'
    )


# ---------------------------------------------------------------------------
# Ścieżka uploadu klienta — dopłata musi utworzyć NOWY wiersz
#
# `record_bulk_payment_proofs` miała regułę „jedno gniazdo na etap": przy
# istniejącym potwierdzeniu 'approved' pomijała wpis (`continue`). Po
# odblokowaniu dopłaty klient mógłby wgrać dowód w próżnię — plik zapisany,
# wiersz nie powstaje, należność dalej wisi.
# ---------------------------------------------------------------------------

def test_doplata_klienta_tworzy_nowy_wiersz(db, make_user, make_order):
    from modules.orders.models import PaymentConfirmation
    from modules.client.payment_confirmation_service import record_bulk_payment_proofs

    user = make_user()
    o = make_order(user=user)
    o.shipping_cost = Decimal('20.00')
    db.session.commit()
    _zatwierdz_e4(db, o, 20)

    o.shipping_cost = Decimal('35.00')
    db.session.commit()

    record_bulk_payment_proofs(
        user=user,
        order_stages=[{'order_id': o.id, 'stages': ['domestic_shipping']}],
        saved_filename='doplata.jpg',
        payment_method_id=None,
    )

    wiersze = PaymentConfirmation.query.filter_by(
        order_id=o.id, payment_stage='domestic_shipping').all()
    assert len(wiersze) == 2, (
        f'Dopłata musi powstać jako NOWY wiersz obok zatwierdzonego; '
        f'jest {len(wiersze)}'
    )
    nowy = [w for w in wiersze if w.status == 'pending']
    assert len(nowy) == 1
    assert nowy[0].amount == Decimal('15.00'), 'Klient dopłaca różnicę, nie całość'
    assert nowy[0].proof_file == 'doplata.jpg'


def test_ponowny_upload_przy_odrzuconym_nie_mnozy_wierszy(db, make_user, make_order):
    """Regresja: odrzucone potwierdzenie jest NADPISYWANE, nie duplikowane."""
    from modules.orders.models import PaymentConfirmation
    from modules.client.payment_confirmation_service import record_bulk_payment_proofs

    user = make_user()
    o = make_order(user=user)
    o.shipping_cost = Decimal('20.00')
    db.session.add(PaymentConfirmation(
        order_id=o.id, payment_stage='domestic_shipping',
        amount=Decimal('20.00'), status='rejected', proof_file='stary.jpg'))
    db.session.commit()

    record_bulk_payment_proofs(
        user=user,
        order_stages=[{'order_id': o.id, 'stages': ['domestic_shipping']}],
        saved_filename='poprawiony.jpg',
        payment_method_id=None,
    )

    wiersze = PaymentConfirmation.query.filter_by(
        order_id=o.id, payment_stage='domestic_shipping').all()
    assert len(wiersze) == 1, 'Odrzucony dowód wymieniamy, nie mnożymy'
    assert wiersze[0].status == 'pending'
    assert wiersze[0].proof_file == 'poprawiony.jpg'


def test_stage_4_confirmation_zwraca_najnowszy(db, make_user, make_order):
    """Właściwości etapu mają pokazywać stan BIEŻĄCY, nie najstarszy wiersz."""
    o = make_order(user=make_user())
    o.shipping_cost = Decimal('35.00')
    db.session.commit()
    stary = _zatwierdz_e4(db, o, 20)

    from modules.orders.models import PaymentConfirmation
    nowy = PaymentConfirmation(
        order_id=o.id, payment_stage='domestic_shipping',
        amount=Decimal('15.00'), status='pending')
    db.session.add(nowy)
    db.session.commit()

    assert o.stage_4_confirmation.id == nowy.id, (
        f'Zwrócono wiersz {o.stage_4_confirmation.id}, oczekiwano najnowszego {nowy.id}'
    )
    assert o.stage_4_status == 'pending'
