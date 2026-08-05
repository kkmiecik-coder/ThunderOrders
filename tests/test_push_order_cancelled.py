"""
Push o anulowaniu zamówienia — jedna metoda dla obu ścieżek anulowania.

Historia błędu: `PushManager.notify_order_cancelled` była zdefiniowana DWA RAZY
w tej samej klasie. Późniejsza definicja (`reason=None`) nadpisywała wcześniejszą
(`refund_pending=False`), więc masowe anulowanie z podsumowania zbiórki wywalało się
na produkcji: "got an unexpected keyword argument 'refund_pending'".

Powiadomienie musi obsłużyć oba wymiary naraz:
  - POWÓD anulowania (np. "Wyprzedane"),
  - czy klient odzyska pieniądze (`refund_pending`) czy po prostu nic nie płaci.
"""
import pytest
from decimal import Decimal


@pytest.fixture
def zlapane_pushe(monkeypatch):
    """Przechwytuje wyjście PushManager._fire_and_forget — bez wątku i bez FCM.

    Celowo NIE podmieniamy samego notify_order_cancelled: to właśnie taka podmiana
    w testach ukryła produkcyjny błąd sygnatury.
    """
    from utils.push_manager import PushManager

    zlapane = []
    monkeypatch.setattr(
        PushManager, '_fire_and_forget',
        staticmethod(lambda **kwargs: zlapane.append(kwargs)),
    )
    return zlapane


@pytest.fixture
def make_page(db, make_user):
    from modules.offers.models import OfferPage

    counter = {'n': 0}

    def _make(**kwargs):
        counter['n'] += 1
        kwargs.setdefault('is_fully_closed', True)
        kwargs.setdefault('status', 'ended')
        page = OfferPage(
            name=f'Zbiorka {counter["n"]}',
            token=f'push-cancel-token-{counter["n"]}',
            created_by=make_user(role='admin').id,
            **kwargs,
        )
        db.session.add(page)
        db.session.commit()
        return page
    return _make


@pytest.fixture
def make_confirmation(db):
    from modules.orders.models import PaymentConfirmation

    def _make(order, status='approved', stage='product', amount=Decimal('100.00')):
        conf = PaymentConfirmation(
            order_id=order.id,
            payment_stage=stage,
            amount=amount,
            status=status,
        )
        db.session.add(conf)
        db.session.commit()
        return conf
    return _make


# ============================================================
# Sama metoda PushManager.notify_order_cancelled
# ============================================================

def test_push_z_powodem_i_zwrotem_mowi_o_obu_rzeczach(
        app, db, make_user, make_order, zlapane_pushe):
    """Klient zapłacił: push podaje powód I obiecuje zwrot wpłaty."""
    from utils.push_manager import PushManager

    order = make_order(make_user(), status='do_zwrotu')

    with app.test_request_context():
        PushManager.notify_order_cancelled(
            order, reason='Wyprzedane', refund_pending=True)

    assert len(zlapane_pushe) == 1
    body = zlapane_pushe[0]['body']
    assert 'Wyprzedane' in body
    assert 'zwrócona' in body


def test_push_z_powodem_bez_zwrotu_mowi_ze_nie_ma_do_zaplaty(
        app, db, make_user, make_order, zlapane_pushe):
    """Klient nie zapłacił: push podaje powód I uspokaja, że nic nie płaci."""
    from utils.push_manager import PushManager

    order = make_order(make_user(), status='anulowane')

    with app.test_request_context():
        PushManager.notify_order_cancelled(
            order, reason='Wyprzedane', refund_pending=False)

    assert len(zlapane_pushe) == 1
    body = zlapane_pushe[0]['body']
    assert 'Wyprzedane' in body
    assert 'nic do zapłaty' in body
    assert 'zwrócona' not in body


def test_push_bez_powodu_nadal_mowi_o_pieniadzach(
        app, db, make_user, make_order, zlapane_pushe):
    """Powód jest opcjonalny — informacja o pieniądzach zostaje."""
    from utils.push_manager import PushManager

    order = make_order(make_user(), status='do_zwrotu')

    with app.test_request_context():
        PushManager.notify_order_cancelled(order, refund_pending=True)

    assert len(zlapane_pushe) == 1
    body = zlapane_pushe[0]['body']
    assert 'zwrócona' in body
    assert body.strip()


def test_push_bez_zadnych_dodatkow_dziala(
        app, db, make_user, make_order, zlapane_pushe):
    """Wywołanie z samym zamówieniem (najstarszy kontrakt) nadal działa."""
    from utils.push_manager import PushManager

    order = make_order(make_user(), status='anulowane')

    with app.test_request_context():
        PushManager.notify_order_cancelled(order)

    assert len(zlapane_pushe) == 1
    assert zlapane_pushe[0]['title'].endswith(order.order_number)
    assert zlapane_pushe[0]['body'].strip()


def test_push_nie_leci_bez_wlasciciela_zamowienia(
        app, db, make_user, make_order, zlapane_pushe):
    """Zamówienie bez user_id → nie ma komu wysłać."""
    from utils.push_manager import PushManager

    order = make_order(make_user(), status='anulowane')
    order.user_id = None

    with app.test_request_context():
        PushManager.notify_order_cancelled(order, refund_pending=True)

    assert zlapane_pushe == []


# ============================================================
# Ścieżka 1: masowe anulowanie z podsumowania (notify_cancelled_orders)
# ============================================================

def test_masowe_anulowanie_oplaconego_wysyla_push_o_zwrocie(
        app, db, make_user, make_order, make_page, make_confirmation,
        monkeypatch, zlapane_pushe):
    """To jest ścieżka, która wywalała się na produkcji (EX/00001710)."""
    from utils.offer_closure import cancel_offer_orders

    monkeypatch.setattr('utils.email_sender.send_email_batch', lambda msgs: None)

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(make_user(email='klient@example.com'),
                       status='oczekujace', offer_page_id=page.id)
    make_confirmation(order)

    with app.test_request_context():
        cancel_offer_orders(page.id, [order.id], 'Wyprzedane', admin.id, notify=True)

    assert order.status == 'do_zwrotu'
    assert len(zlapane_pushe) == 1
    assert 'zwrócona' in zlapane_pushe[0]['body']


def test_masowe_anulowanie_nieoplaconego_wysyla_push_bez_zwrotu(
        app, db, make_user, make_order, make_page, monkeypatch, zlapane_pushe):
    from utils.offer_closure import cancel_offer_orders

    monkeypatch.setattr('utils.email_sender.send_email_batch', lambda msgs: None)

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(make_user(email='klient@example.com'),
                       status='oczekujace', offer_page_id=page.id)

    with app.test_request_context():
        cancel_offer_orders(page.id, [order.id], 'Wyprzedane', admin.id, notify=True)

    assert order.status == 'anulowane'
    assert len(zlapane_pushe) == 1
    assert 'nic do zapłaty' in zlapane_pushe[0]['body']
    assert 'zwrócona' not in zlapane_pushe[0]['body']


# ============================================================
# Ścieżka 2: "nie załapało się do kompletu" (send_cancellation_emails)
# ============================================================

def test_brak_kompletu_u_oplaconego_klienta_mowi_o_zwrocie(
        app, db, make_user, make_order, make_page, make_confirmation,
        monkeypatch, zlapane_pushe):
    """Klient, który już wpłacił, też musi usłyszeć o zwrocie w tej ścieżce."""
    from utils.offer_closure import send_cancellation_emails

    monkeypatch.setattr('utils.email_manager.EmailManager.notify_order_cancelled',
                        staticmethod(lambda *a, **kw: None))

    page = make_page()
    order = make_order(make_user(email='klient@example.com'),
                       status='oczekujace', offer_page_id=page.id)
    make_confirmation(order)

    with app.test_request_context():
        send_cancellation_emails(page.id, [order.id])

    assert len(zlapane_pushe) == 1
    body = zlapane_pushe[0]['body']
    assert 'kompletu' in body
    assert 'zwrócona' in body


def test_brak_kompletu_u_nieoplaconego_klienta_nie_obiecuje_zwrotu(
        app, db, make_user, make_order, make_page, monkeypatch, zlapane_pushe):
    from utils.offer_closure import send_cancellation_emails

    monkeypatch.setattr('utils.email_manager.EmailManager.notify_order_cancelled',
                        staticmethod(lambda *a, **kw: None))

    page = make_page()
    order = make_order(make_user(email='klient@example.com'),
                       status='oczekujace', offer_page_id=page.id)

    with app.test_request_context():
        send_cancellation_emails(page.id, [order.id])

    assert len(zlapane_pushe) == 1
    body = zlapane_pushe[0]['body']
    assert 'kompletu' in body
    assert 'zwrócona' not in body
