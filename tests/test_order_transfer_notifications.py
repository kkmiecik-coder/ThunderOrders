"""Powiadomienia (mail + push) po przepisaniu zamówienia.

Nowa właścicielka dostaje zamówienie z pozycjami i kwotą; poprzednia — informację,
co przepisano, BEZ danych nowej klientki.
"""
import pytest

from tests.przepisanie_helpers import zamowienie_klientki


@pytest.fixture(autouse=True)
def _strona(strona_sprzedazy):
    """Zamówienia powstają z offer_page_id=1 (FK)."""


@pytest.fixture
def wynik(db, make_user, make_product, make_order):
    from modules.orders.models import OrderItem
    from modules.orders.transfer import przepisz_pozycje

    admin = make_user(role='admin', email='admin@example.com')
    ania = make_user(email='ania@example.com', first_name='Ania', last_name='Nowak')
    basia = make_user(email='basia@example.com', first_name='Basia', last_name='Kowalczyk')
    p = make_product(name='Karta San')
    a = zamowienie_klientki(db, None, make_order, [(p.id, 2, 30)], user=ania)
    item = OrderItem.query.filter_by(order_id=a.id).one()
    w = przepisz_pozycje(a, basia, admin, [(item.id, 1)], wplata_za_karta=True)
    db.session.commit()
    return w


def test_maile_do_obu_klientek(app, wynik, maile_synchronicznie):
    from extensions import mail
    from utils.email_manager import EmailManager

    with app.test_request_context(), mail.record_messages() as wyslane:
        EmailManager.notify_order_transferred(wynik)

    do = {m.recipients[0]: m for m in wyslane}
    assert set(do) == {'ania@example.com', 'basia@example.com'}
    dla_basi = do['basia@example.com'].html
    assert wynik.cel.order_number in dla_basi and 'Karta San' in dla_basi
    dla_ani = do['ania@example.com'].html
    assert 'Karta San' in dla_ani and wynik.zrodlo.order_number in dla_ani
    assert 'Basia' not in dla_ani and 'Kowalczyk' not in dla_ani and 'basia@' not in dla_ani


def test_wylaczony_mail_nie_idzie(app, db, wynik, maile_synchronicznie):
    import json
    from extensions import mail
    from modules.auth.models import Settings
    from utils.email_manager import EmailManager

    Settings.set_value('email_notifications_config', json.dumps({'notify_order_transferred': False}),
                       type='json')
    db.session.commit()
    EmailManager.clear_email_config_cache()

    with app.test_request_context(), mail.record_messages() as wyslane:
        EmailManager.notify_order_transferred(wynik)

    assert wyslane == []


def test_push_do_obu_klientek(app, wynik, monkeypatch):
    from utils.push_manager import PushManager

    wywolania = []
    monkeypatch.setattr(PushManager, '_fire_and_forget',
                        staticmethod(lambda **kw: wywolania.append(kw)))

    with app.test_request_context():
        PushManager.notify_order_transferred(wynik)

    odbiorcy = {w['user_id']: w for w in wywolania}
    assert set(odbiorcy) == {wynik.cel.user_id, wynik.poprzednia.id}
    assert 'Basia' not in odbiorcy[wynik.poprzednia.id]['body']
    assert wynik.cel.order_number in odbiorcy[wynik.cel.user_id]['title']


def test_przelacznik_w_ustawieniach_zapisywany(client, db, make_user, login):
    from modules.auth.models import Settings

    login(make_user(role='admin', email='szef@example.com'))
    r = client.post('/admin/orders/settings/email-notifications',
                    json={'toggles': {'notify_order_transferred': False}})

    assert r.status_code == 200
    assert Settings.get_value('email_notifications_config', {})['notify_order_transferred'] is False
