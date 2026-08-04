"""
Masowe anulowanie zamówień z podsumowania zamkniętej strony sprzedaży.

Nieopłacone zamówienia dostają status 'anulowane', opłacone 'do_zwrotu'.
Kwoty i potwierdzenia płatności zostają nietknięte.
"""
import pytest
from decimal import Decimal


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
            token=f'token-{counter["n"]}',
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


def test_nieoplacone_zamowienie_dostaje_anulowane(db, make_user, make_order, make_page):
    from utils.offer_closure import cancel_offer_orders

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)

    result = cancel_offer_orders(page.id, [order.id], 'Wyprzedane', admin.id, notify=False)

    assert order.status == 'anulowane'
    assert result['cancelled'] == 1
    assert result['to_refund'] == 0


def test_zamowienie_z_zatwierdzona_wplata_dostaje_do_zwrotu(
    db, make_user, make_order, make_page, make_confirmation
):
    from utils.offer_closure import cancel_offer_orders

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)
    make_confirmation(order, status='approved')

    result = cancel_offer_orders(page.id, [order.id], 'Wyprzedane', admin.id, notify=False)

    assert order.status == 'do_zwrotu'
    assert result['to_refund'] == 1
    assert result['cancelled'] == 0


def test_wplata_czekajaca_na_zatwierdzenie_tez_liczy_sie_jako_oplacona(
    db, make_user, make_order, make_page, make_confirmation
):
    """Pieniądze mogą już być na koncie, mimo że potwierdzenie nie zostało sprawdzone."""
    from utils.offer_closure import cancel_offer_orders

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)
    make_confirmation(order, status='pending')

    cancel_offer_orders(page.id, [order.id], 'Wyprzedane', admin.id, notify=False)

    assert order.status == 'do_zwrotu'


def test_odrzucona_wplata_nie_liczy_sie_jako_oplacona(
    db, make_user, make_order, make_page, make_confirmation
):
    from utils.offer_closure import cancel_offer_orders

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)
    make_confirmation(order, status='rejected')

    cancel_offer_orders(page.id, [order.id], 'Wyprzedane', admin.id, notify=False)

    assert order.status == 'anulowane'


def test_wplata_na_dowolnym_etapie_liczy_sie_jako_oplacona(
    db, make_user, make_order, make_page, make_confirmation
):
    from utils.offer_closure import cancel_offer_orders

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)
    make_confirmation(order, status='approved', stage='customs_vat')

    cancel_offer_orders(page.id, [order.id], 'Wyprzedane', admin.id, notify=False)

    assert order.status == 'do_zwrotu'


@pytest.mark.parametrize('status', ['anulowane', 'do_zwrotu', 'zwrocone', 'czesciowo_zwrocone'])
def test_zamowienia_juz_zamkniete_sa_pomijane(db, make_user, make_order, make_page, status):
    from utils.offer_closure import cancel_offer_orders

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(make_user(), status=status, offer_page_id=page.id)

    result = cancel_offer_orders(page.id, [order.id], 'Wyprzedane', admin.id, notify=False)

    assert result['skipped'] == 1
    assert result['cancelled'] == 0
    assert result['to_refund'] == 0
    assert order.status == status


def test_zamowienie_spoza_strony_konczy_sie_bledem(db, make_user, make_order, make_page):
    from utils.offer_closure import cancel_offer_orders

    admin = make_user(role='admin')
    page = make_page()
    obca = make_order(make_user(), status='oczekujace')

    with pytest.raises(ValueError):
        cancel_offer_orders(page.id, [obca.id], 'Wyprzedane', admin.id, notify=False)

    assert obca.status == 'oczekujace'


def test_pusty_powod_konczy_sie_bledem(db, make_user, make_order, make_page):
    from utils.offer_closure import cancel_offer_orders

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)

    with pytest.raises(ValueError):
        cancel_offer_orders(page.id, [order.id], '   ', admin.id, notify=False)

    assert order.status == 'oczekujace'


def test_pusta_lista_zamowien_konczy_sie_bledem(db, make_user, make_page):
    from utils.offer_closure import cancel_offer_orders

    admin = make_user(role='admin')
    page = make_page()

    with pytest.raises(ValueError):
        cancel_offer_orders(page.id, [], 'Wyprzedane', admin.id, notify=False)


def test_kwoty_i_potwierdzenia_zostaja_nietkniete(
    db, make_user, make_order, make_page, make_confirmation
):
    from utils.offer_closure import cancel_offer_orders

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(
        make_user(), status='oczekujace', offer_page_id=page.id, total_amount=Decimal('250.00')
    )
    order.paid_amount = Decimal('100.00')
    db.session.commit()
    make_confirmation(order, status='approved')

    cancel_offer_orders(page.id, [order.id], 'Wyprzedane', admin.id, notify=False)

    assert order.total_amount == Decimal('250.00')
    assert order.paid_amount == Decimal('100.00')
    assert order.payment_confirmations.count() == 1


def test_powod_ladnie_w_komentarzu_zamowienia(db, make_user, make_order, make_page):
    from utils.offer_closure import cancel_offer_orders

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)

    cancel_offer_orders(page.id, [order.id], 'Produkt wyprzedany u dostawcy', admin.id, notify=False)

    comments = [c.comment for c in order.comments]
    assert any('Produkt wyprzedany u dostawcy' in c for c in comments)


def test_mieszana_paczka_zamowien(db, make_user, make_order, make_page, make_confirmation):
    """Jedno wywołanie rozdziela zamówienia na dwie grupy i pomija zamknięte."""
    from utils.offer_closure import cancel_offer_orders

    admin = make_user(role='admin')
    page = make_page()

    nieoplacone_1 = make_order(make_user(), status='oczekujace', offer_page_id=page.id)
    nieoplacone_2 = make_order(make_user(), status='nowe', offer_page_id=page.id)
    oplacone = make_order(make_user(), status='oczekujace', offer_page_id=page.id)
    make_confirmation(oplacone, status='approved')
    juz_anulowane = make_order(make_user(), status='anulowane', offer_page_id=page.id)

    result = cancel_offer_orders(
        page.id,
        [nieoplacone_1.id, nieoplacone_2.id, oplacone.id, juz_anulowane.id],
        'Wyprzedane',
        admin.id,
        notify=False,
    )

    assert result == {'cancelled': 2, 'to_refund': 1, 'skipped': 1, 'notified': 0}
    assert nieoplacone_1.status == 'anulowane'
    assert nieoplacone_2.status == 'anulowane'
    assert oplacone.status == 'do_zwrotu'
    assert juz_anulowane.status == 'anulowane'


def _przechwyc_wysylke(monkeypatch):
    """Podmienia batch mailowy i push — zwraca listę przechwyconych paczek maili."""
    from utils.push_manager import PushManager

    wyslane = []
    monkeypatch.setattr('utils.email_sender.send_email_batch', lambda msgs: wyslane.append(msgs))
    monkeypatch.setattr(
        PushManager, 'notify_order_cancelled',
        lambda order, refund_pending=False: None,
        raising=False,
    )
    return wyslane


def test_notify_false_nie_wysyla_nic(db, make_user, make_order, make_page, monkeypatch):
    from utils.offer_closure import cancel_offer_orders

    wyslane = _przechwyc_wysylke(monkeypatch)

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)

    result = cancel_offer_orders(page.id, [order.id], 'Wyprzedane', admin.id, notify=False)

    assert wyslane == []
    assert result['notified'] == 0


def test_notify_true_wysyla_jeden_batch(app, db, make_user, make_order, make_page, monkeypatch):
    """Wszystkie maile idą jedną paczką — jedno połączenie SMTP."""
    from utils.offer_closure import cancel_offer_orders

    wyslane = _przechwyc_wysylke(monkeypatch)

    admin = make_user(role='admin')
    page = make_page()
    o1 = make_order(make_user(email='a@example.com'), status='oczekujace', offer_page_id=page.id)
    o2 = make_order(make_user(email='b@example.com'), status='oczekujace', offer_page_id=page.id)

    # Szablony maili renderują się w kontekście żądania (tak jak w produkcji,
    # gdzie anulowanie leci z endpointu).
    with app.test_request_context():
        result = cancel_offer_orders(page.id, [o1.id, o2.id], 'Wyprzedane', admin.id, notify=True)

    assert len(wyslane) == 1
    assert len(wyslane[0]) == 2
    assert result['notified'] == 2


def test_mail_o_zwrocie_ma_inny_temat_i_tresc(
    app, db, make_user, make_order, make_page, make_confirmation, monkeypatch
):
    from utils.offer_closure import cancel_offer_orders

    wyslane = _przechwyc_wysylke(monkeypatch)

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(make_user(email='c@example.com'), status='oczekujace', offer_page_id=page.id)
    make_confirmation(order, status='approved')

    with app.test_request_context():
        cancel_offer_orders(page.id, [order.id], 'Wyprzedane', admin.id, notify=True)

    msg = wyslane[0][0]
    assert 'zwrot' in msg.subject.lower()
    assert 'zwrócona' in msg.html or 'zwrotu' in msg.html


def test_mail_o_anulowaniu_bez_wplaty_nie_obiecuje_zwrotu(
    app, db, make_user, make_order, make_page, monkeypatch
):
    from utils.offer_closure import cancel_offer_orders

    wyslane = _przechwyc_wysylke(monkeypatch)

    admin = make_user(role='admin')
    page = make_page()
    order = make_order(make_user(email='d@example.com'), status='oczekujace', offer_page_id=page.id)

    with app.test_request_context():
        cancel_offer_orders(page.id, [order.id], 'Wyprzedane', admin.id, notify=True)

    msg = wyslane[0][0]
    assert 'zwrot' not in msg.subject.lower()
    assert 'Wyprzedane' in msg.html


def test_pominiete_zamowienia_nie_dostaja_maila(db, make_user, make_order, make_page, monkeypatch):
    from utils.offer_closure import cancel_offer_orders

    wyslane = _przechwyc_wysylke(monkeypatch)

    admin = make_user(role='admin')
    page = make_page()
    juz_anulowane = make_order(
        make_user(email='e@example.com'), status='anulowane', offer_page_id=page.id
    )

    result = cancel_offer_orders(page.id, [juz_anulowane.id], 'Wyprzedane', admin.id, notify=True)

    assert wyslane == []
    assert result['notified'] == 0
