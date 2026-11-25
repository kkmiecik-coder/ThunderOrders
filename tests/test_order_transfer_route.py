"""Trasa POST /admin/orders/<id>/transfer i przycisk na stronie zamówienia."""
import pytest

from tests.przepisanie_helpers import zamowienie_klientki


@pytest.fixture(autouse=True)
def _strona(strona_sprzedazy):
    """Zamówienia powstają z offer_page_id=1 (FK)."""


@pytest.fixture
def powiadomienia(monkeypatch):
    """Zbiera wywołania powiadomień zamiast je wysyłać."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    wywolania = []
    monkeypatch.setattr(EmailManager, 'notify_order_transferred',
                        staticmethod(lambda w: wywolania.append(('mail', w))))
    monkeypatch.setattr(PushManager, 'notify_order_transferred',
                        staticmethod(lambda w: wywolania.append(('push', w))))
    return wywolania


@pytest.fixture
def scena(db, make_user, make_product, make_order):
    from modules.orders.models import OrderItem
    admin = make_user(role='admin', email='admin@example.com')
    ania = make_user(email='ania@example.com')
    basia = make_user(email='basia@example.com')
    p1, p2 = make_product(), make_product()
    a = zamowienie_klientki(db, None, make_order, [(p1.id, 2, 30), (p2.id, 1, 10)], user=ania)
    items = OrderItem.query.filter_by(order_id=a.id).order_by(OrderItem.id).all()
    return admin, ania, basia, a, items


def _post(client, order, **body):
    return client.post(f'/admin/orders/{order.id}/transfer', json=body)


def test_klientka_nie_ma_dostepu(client, login, scena):
    admin, ania, basia, a, items = scena
    login(ania)

    r = _post(client, a, client_id=basia.id, mode='whole', notify=False)

    assert r.status_code in (302, 403)
    assert a.user_id == ania.id


def test_cale_zamowienie(client, db, login, scena, powiadomienia):
    from modules.orders.models import Order
    admin, ania, basia, a, items = scena
    login(admin)

    r = _post(client, a, client_id=basia.id, mode='whole', notify=True)

    assert r.status_code == 200, r.get_json()
    dane = r.get_json()
    assert dane['success'] is True
    assert dane['redirect_url'].endswith(f'/admin/orders/{a.id}')
    assert db.session.get(Order, a.id).user_id == basia.id
    assert [rodzaj for rodzaj, _ in powiadomienia] == ['mail', 'push']


def test_wybrane_pozycje(client, db, login, scena, powiadomienia):
    from modules.orders.models import Order, PaymentConfirmation
    admin, ania, basia, a, items = scena
    login(admin)

    r = _post(client, a, client_id=basia.id, mode='items',
              items=[{'item_id': items[0].id, 'quantity': 1}],
              payment_follows=False, notify=False)

    assert r.status_code == 200, r.get_json()
    nowe = Order.query.filter_by(user_id=basia.id).one()
    assert r.get_json()['redirect_url'].endswith(f'/admin/orders/{nowe.id}')
    assert powiadomienia == []


def test_zablokowane_zwraca_400(client, db, login, scena, powiadomienia):
    admin, ania, basia, a, items = scena
    a.status = 'wyslane'
    db.session.commit()
    login(admin)

    r = _post(client, a, client_id=basia.id, mode='whole', notify=True)

    assert r.status_code == 400
    assert r.get_json()['success'] is False and r.get_json()['message']
    assert powiadomienia == []


@pytest.mark.parametrize('body', [
    {'client_id': None, 'mode': 'whole', 'notify': False},  # brak klientki
    {'client_id': 999999, 'mode': 'whole'},                  # nie istnieje
    {'client_id': 'x', 'mode': 'whole'},                     # śmieci
    {'mode': 'cos'},                                         # zły tryb
    {'mode': 'items', 'items': [{'item_id': 'a', 'quantity': 1}]},
])
def test_zle_dane_400(client, login, scena, body):
    admin, ania, basia, a, items = scena
    body.setdefault('client_id', basia.id)
    login(admin)

    r = _post(client, a, **body)

    assert r.status_code == 400
    assert a.user_id == ania.id


def test_strona_zamowienia_ma_przycisk(client, login, scena):
    admin, ania, basia, a, items = scena
    login(admin)

    html = client.get(f'/admin/orders/{a.id}').get_data(as_text=True)

    assert 'Przepisz na inną klientkę' in html
    assert 'id="transferOrderModal"' in html
    assert 'order-transfer.js' in html


def test_strona_zablokowanego_pokazuje_powod(client, db, login, scena):
    admin, ania, basia, a, items = scena
    a.status = 'dostarczone'
    db.session.commit()
    login(admin)

    html = client.get(f'/admin/orders/{a.id}').get_data(as_text=True)

    assert 'nie można przepisać' in html
