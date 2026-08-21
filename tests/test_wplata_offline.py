"""Rejestracja wpłaty offline przez admina (BRAK 3.4 z audytu).

Do tej pory nie istniała ŻADNA ścieżka, którą admin oznaczyłby etap płatności
jako opłacony. `PaymentConfirmation(` występowało w kodzie produkcyjnym dokładnie
dwa razy: definicja modelu i upload klienta. Trasy admina mutowały wyłącznie
istniejący wiersz i tylko w statusie 'pending'.

`admin_update_payment` ustawia `order.paid_amount`, ale obie bramki opłacenia
zlecenia pytają o PaymentConfirmation, nigdy o paid_amount — ręczne wpisanie
kwoty nie ruszało statusu zlecenia ani o milimetr.

Obejścia, które istniały, to nie funkcje: odrzucić zatwierdzone potwierdzenie
i prosić klienta o ponowne wgranie, albo spakować zlecenie mimo braku zapłaty.

Wariant A z audytu: admin tworzy PaymentConfirmation „za klienta" (gotówka,
przelew poza systemem), a bramki `all(settled)` zaczynają działać same — bez
wyjątków w regule opłacenia.
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


def _admin(make_user):
    return make_user(role='admin', profile_completed=True)


@pytest.fixture
def bez_powiadomien(monkeypatch):
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    for nazwa in ('notify_payment_approved', 'notify_shipping_status_change'):
        monkeypatch.setattr(EmailManager, nazwa, staticmethod(lambda *a, **kw: None))
        monkeypatch.setattr(PushManager, nazwa, staticmethod(lambda *a, **kw: None))


def _zlecenie(db, user, make_order, koszt):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status='czeka_na_oplacenie')
    db.session.add(sr)
    db.session.flush()
    o = make_order(user=user, status='dostarczone_gom')
    o.shipping_cost = koszt
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
    db.session.commit()
    return sr, o


URL = '/admin/payment-confirmations/register/{}'


def test_rejestracja_wplaty_tworzy_zatwierdzone_potwierdzenie(
        db, client, login, make_user, make_order, bez_powiadomien):
    from modules.orders.models import PaymentConfirmation

    _seed_sr_statuses(db)
    user = make_user()
    sr, zamowienie = _zlecenie(db, user, make_order, koszt=30)
    login(_admin(make_user))

    r = client.post(URL.format(zamowienie.id), json={
        'payment_stage': 'domestic_shipping',
        'amount': 30,
        'note': 'Gotówka przy odbiorze',
    })

    assert r.status_code == 200, r.get_json()
    conf = PaymentConfirmation.query.filter_by(
        order_id=zamowienie.id, payment_stage='domestic_shipping').first()
    assert conf is not None
    assert conf.status == 'approved'
    assert float(conf.amount) == 30
    assert conf.proof_file is None, 'Wpłata offline nie ma załącznika'


def test_rejestracja_wplaty_podnosi_saldo_zamowienia(
        db, client, login, make_user, make_order, bez_powiadomien):
    _seed_sr_statuses(db)
    user = make_user()
    sr, zamowienie = _zlecenie(db, user, make_order, koszt=30)
    login(_admin(make_user))

    client.post(URL.format(zamowienie.id), json={
        'payment_stage': 'domestic_shipping', 'amount': 30})

    db.session.expire_all()
    assert float(zamowienie.paid_amount) == 30, (
        'Parytet z payment_confirmation_approve — saldo rośnie o zaksięgowaną kwotę'
    )


def test_rejestracja_wplaty_domyka_zlecenie(
        db, client, login, make_user, make_order, bez_powiadomien):
    """Sedno: bramka all(settled) ma zadziałać sama, bez wyjątków w regule."""
    _seed_sr_statuses(db)
    user = make_user()
    sr, zamowienie = _zlecenie(db, user, make_order, koszt=30)
    login(_admin(make_user))

    client.post(URL.format(zamowienie.id), json={
        'payment_stage': 'domestic_shipping', 'amount': 30})

    db.session.expire_all()
    assert sr.status == 'oplacone'


def test_nie_nadpisuje_zatwierdzonej_platnosci(
        db, client, login, make_user, make_order, bez_powiadomien):
    """Klient już zapłacił — rejestracja drugiej wpłaty to pomyłka, nie korekta."""
    from modules.orders.models import PaymentConfirmation

    _seed_sr_statuses(db)
    user = make_user()
    sr, zamowienie = _zlecenie(db, user, make_order, koszt=30)
    db.session.add(PaymentConfirmation(
        order_id=zamowienie.id, payment_stage='domestic_shipping',
        amount=30, status='approved', proof_file='dowod.jpg'))
    db.session.commit()
    login(_admin(make_user))

    r = client.post(URL.format(zamowienie.id), json={
        'payment_stage': 'domestic_shipping', 'amount': 30})

    assert r.status_code == 409, r.get_json()
    db.session.expire_all()
    conf = PaymentConfirmation.query.filter_by(order_id=zamowienie.id).first()
    assert conf.proof_file == 'dowod.jpg', 'Dowód klienta nie może zniknąć'


def test_zastepuje_oczekujace_potwierdzenie(
        db, client, login, make_user, make_order, bez_powiadomien):
    """Klient wgrał dowód, ale zapłacił gotówką — admin księguje i zamyka temat."""
    from modules.orders.models import PaymentConfirmation

    _seed_sr_statuses(db)
    user = make_user()
    sr, zamowienie = _zlecenie(db, user, make_order, koszt=30)
    db.session.add(PaymentConfirmation(
        order_id=zamowienie.id, payment_stage='domestic_shipping',
        amount=30, status='pending', proof_file='dowod.jpg'))
    db.session.commit()
    login(_admin(make_user))

    r = client.post(URL.format(zamowienie.id), json={
        'payment_stage': 'domestic_shipping', 'amount': 30})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    confs = PaymentConfirmation.query.filter_by(
        order_id=zamowienie.id, payment_stage='domestic_shipping').all()
    assert len(confs) == 1, 'Jedno gniazdo na etap — bez duplikatów'
    assert confs[0].status == 'approved'


def test_odrzuca_ujemna_kwote(db, client, login, make_user, make_order, bez_powiadomien):
    _seed_sr_statuses(db)
    user = make_user()
    sr, zamowienie = _zlecenie(db, user, make_order, koszt=30)
    login(_admin(make_user))

    r = client.post(URL.format(zamowienie.id), json={
        'payment_stage': 'domestic_shipping', 'amount': -5})

    assert r.status_code == 400


def test_odrzuca_nieznany_etap(db, client, login, make_user, make_order, bez_powiadomien):
    _seed_sr_statuses(db)
    user = make_user()
    sr, zamowienie = _zlecenie(db, user, make_order, koszt=30)
    login(_admin(make_user))

    r = client.post(URL.format(zamowienie.id), json={
        'payment_stage': 'nie_ma_takiego', 'amount': 10})

    assert r.status_code == 400


def test_klient_nie_zarejestruje_wplaty(db, client, login, make_user, make_order):
    """Rejestracja wpłaty to uprawnienie magazynowo-księgowe, nie klienckie."""
    _seed_sr_statuses(db)
    user = make_user()
    sr, zamowienie = _zlecenie(db, user, make_order, koszt=30)
    login(user)

    r = client.post(URL.format(zamowienie.id), json={
        'payment_stage': 'domestic_shipping', 'amount': 30})

    assert r.status_code in (302, 403)
