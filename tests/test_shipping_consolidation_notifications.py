"""Powiadomienia o paczce zbiorczej — każdy uczestnik dostaje swoje, bez cudzych danych."""
import pytest
from test_shipping_consolidation import _seed_sr_statuses, _sr, _konsolidacja  # noqa: E402


@pytest.fixture
def przechwycone(monkeypatch):
    from utils.push_manager import PushManager
    import utils.email_sender as es
    dane = {'email': [], 'push': []}
    monkeypatch.setattr(es, 'prepare_shipment_sent_email',
                        lambda **kw: dane['email'].append(kw) or None)
    monkeypatch.setattr(es, 'send_email_batch', lambda messages: None)
    monkeypatch.setattr(PushManager, '_fire_and_forget',
                        staticmethod(lambda **kw: dane['push'].append(kw)))
    return dane


def test_kazdy_uczestnik_dostaje_wlasna_liste_zamowien(db, przechwycone, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order, orders_count=2)
    zbiorcze.tracking_number = '622333444'
    zbiorcze.courier = 'inpost'
    db.session.commit()

    from utils.email_manager import EmailManager
    EmailManager.notify_shipment_sent(zbiorcze, tracking_number='622333444', courier='inpost')

    assert len(przechwycone['email']) == 2
    po_adresie = {m['user_email']: m for m in przechwycone['email']}
    mail_b = po_adresie[sr_b.user.email]
    moje = {o.order_number for o in sr_b.display_orders}
    cudze = {o.order_number for o in sr_a.display_orders}
    assert set(mail_b['order_numbers']) == moje
    assert not (set(mail_b['order_numbers']) & cudze)


def test_uczestnik_niewiodacy_dostaje_push(db, przechwycone, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    db.session.commit()

    from utils.push_manager import PushManager
    PushManager.notify_shipment_sent(zbiorcze, tracking_number='622333444')

    odbiorcy = {p['user_id'] for p in przechwycone['push']}
    assert odbiorcy == {sr_a.user_id, sr_b.user_id}


def test_paczka_bez_wlasciciela_nie_wysyla_nic(db, przechwycone, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.user_id = None
    sr_a.user_id = None
    sr_b.user_id = None
    db.session.commit()

    from utils.email_manager import EmailManager
    EmailManager.notify_shipment_sent(zbiorcze, tracking_number='622333444')

    # Fallback na adres z pierwszego zamówienia wysłałby obcej osobie listę
    # zamówień wszystkich uczestników — dla paczki zbiorczej jest wyłączony.
    assert przechwycone['email'] == []
