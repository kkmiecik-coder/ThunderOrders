"""Dowód przelewu poprzedniej właścicielki zamówienia jest niewidoczny dla obecnej.

Po przepisaniu całego zamówienia potwierdzenia z plikiem mają
`proof_hidden_for_client=True` — są na nich dane bankowe Ani. Admin widzi dalej.
"""
import os
from decimal import Decimal

import pytest

PLIK = 'przepisanie_test_dowod.png'


@pytest.fixture
def plik_dowodu(app):
    folder = os.path.join(app.root_path, 'uploads', 'payment_confirmations')
    os.makedirs(folder, exist_ok=True)
    sciezka = os.path.join(folder, PLIK)
    with open(sciezka, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
    yield PLIK
    os.remove(sciezka)


def _zamowienie_z_dowodem(db, make_user, make_order, ukryty, user=None):
    from modules.orders.models import PaymentConfirmation
    u = user or make_user()
    o = make_order(u, order_type='on_hand')
    conf = PaymentConfirmation(order_id=o.id, payment_stage='product', amount=Decimal('10'),
                               status='approved', proof_file=PLIK,
                               proof_hidden_for_client=ukryty)
    db.session.add(conf)
    db.session.commit()
    return o, u


def test_klientka_nie_pobierze_ukrytego_dowodu(client, db, make_user, make_order, login,
                                               plik_dowodu):
    _, basia = _zamowienie_z_dowodem(db, make_user, make_order, ukryty=True)
    login(basia)

    assert client.get(f'/payment-proof/{PLIK}').status_code == 403


def test_klientka_pobierze_swoj_dowod(client, db, make_user, make_order, login, plik_dowodu):
    _, ania = _zamowienie_z_dowodem(db, make_user, make_order, ukryty=False)
    login(ania)

    assert client.get(f'/payment-proof/{PLIK}').status_code == 200


def test_admin_widzi_ukryty_dowod(client, db, make_user, make_order, login, plik_dowodu):
    _zamowienie_z_dowodem(db, make_user, make_order, ukryty=True)
    login(make_user(role='admin', email='admin@example.com'))

    assert client.get(f'/payment-proof/{PLIK}').status_code == 200


def _token(client, db, user):
    user.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': user.email, 'password': 'Haslo123!'})
    return {'Authorization': f"Bearer {r.get_json()['data']['access_token']}"}


def test_aplikacja_nie_poda_ukrytego_dowodu(client, db, make_user, make_order, plik_dowodu):
    o, basia = _zamowienie_z_dowodem(db, make_user, make_order, ukryty=True)
    h = _token(client, db, basia)

    r = client.get(f'/api/mobile/v1/payment-confirmations/proof/{PLIK}', headers=h)
    assert r.status_code == 404

    etapy = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h).get_json()['data']
    produkt = next(e for e in etapy['payment_stages'] if e['stage'] == 'product')
    assert produkt['proof_url'] is None
