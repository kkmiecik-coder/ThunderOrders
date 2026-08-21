"""E4 (wysyłka PL) rozliczone przy koszcie 0 zł.

E4 był jedynym etapem bez predykatu „rozliczone". E3 ma `is_customs_vat_settled`,
gdzie 0 zł znaczy rozliczone; dla E4 odpowiednika nie było, więc zero było
nieodróżnialne od „niewycenione" i domykało pętlę trzech bramek:

1. wejście na `any(shipping_cost > 0)` — zlecenie idzie na „czeka na opłacenie",
2. `can_upload_stage_4` odmawia uploadu przy kwocie 0 — klient NIE MOŻE zapłacić,
3. wyjście na `all(approved E4)` — wymaga potwierdzenia także dla zamówienia z 0 zł.

Skutek: zlecenie, w którym część zamówień wyceniono, a część została na zerze
(„cena kartonu się nie zmienia" — zgłoszenie właściciela), nigdy nie osiągało
statusu „opłacone", mimo że klient nic nie był winien.

Wiersz PaymentConfirmation powstaje w całym repo w jednym miejscu — przy uploadzie
klienta — więc dla zamówienia z kwotą 0 nie powstanie nigdy.
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


def _zatwierdz_e4(db, order, kwota):
    """Potwierdzenie E4 w stanie 'approved' — jak po akceptacji admina."""
    from modules.orders.models import PaymentConfirmation
    conf = PaymentConfirmation(
        order_id=order.id,
        payment_stage='domestic_shipping',
        amount=kwota,
        status='approved',
    )
    db.session.add(conf)
    db.session.commit()
    return conf


def _zlecenie(db, user, make_order, koszty):
    """Zlecenie z zamówieniami o zadanych kosztach wysyłki."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status='czeka_na_oplacenie')
    db.session.add(sr)
    db.session.flush()
    zamowienia = []
    for koszt in koszty:
        o = make_order(user=user, status='dostarczone_gom')
        o.shipping_cost = koszt
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
        zamowienia.append(o)
    db.session.commit()
    return sr, zamowienia


# ---------------------------------------------------------------------------
# Predykat
# ---------------------------------------------------------------------------

def test_zero_zlotych_jest_rozliczone(db, make_user, make_order):
    """0 zł = nie ma czego płacić. Parytet z is_customs_vat_settled."""
    o = make_order(user=make_user())
    o.shipping_cost = 0
    db.session.commit()

    assert o.is_domestic_shipping_settled is True


def test_kwota_bez_zatwierdzenia_nie_jest_rozliczona(db, make_user, make_order):
    o = make_order(user=make_user())
    o.shipping_cost = 20
    db.session.commit()

    assert o.is_domestic_shipping_settled is False


def test_kwota_z_zatwierdzeniem_jest_rozliczona(db, make_user, make_order):
    o = make_order(user=make_user())
    o.shipping_cost = 20
    db.session.commit()
    _zatwierdz_e4(db, o, 20)

    assert o.is_domestic_shipping_settled is True


def test_kwota_z_potwierdzeniem_oczekujacym_nie_jest_rozliczona(db, make_user, make_order):
    """'pending' nie wystarcza — tak samo jak przy E3."""
    from modules.orders.models import PaymentConfirmation
    o = make_order(user=make_user())
    o.shipping_cost = 20
    db.session.add(PaymentConfirmation(
        order_id=o.id, payment_stage='domestic_shipping', amount=20, status='pending'))
    db.session.commit()

    assert o.is_domestic_shipping_settled is False


# ---------------------------------------------------------------------------
# Bramka zwykłego zlecenia
# ---------------------------------------------------------------------------

def test_zlecenie_z_mieszanymi_kosztami_dochodzi_do_oplacone(db, make_user, make_order):
    """Zgłoszenie właściciela: część zamówień wyceniona, część na zerze."""
    from modules.admin.payment_confirmations import _check_sr_auto_oplacone

    _seed_sr_statuses(db)
    user = make_user()
    sr, (platne, gratis) = _zlecenie(db, user, make_order, koszty=[20, 0])
    _zatwierdz_e4(db, platne, 20)

    _check_sr_auto_oplacone(platne)

    assert sr.status == 'oplacone', (
        'Zamówienie z kosztem 0 zł nie ma jak dostać potwierdzenia płatności — '
        'nie może blokować całego zlecenia'
    )


def test_zlecenie_z_nieoplaconym_zamowieniem_nie_dochodzi_do_oplacone(db, make_user, make_order):
    """Regresja: predykat nie może przepuścić realnie nieopłaconego zlecenia."""
    from modules.admin.payment_confirmations import _check_sr_auto_oplacone

    _seed_sr_statuses(db)
    user = make_user()
    sr, (platne, drugie_platne) = _zlecenie(db, user, make_order, koszty=[20, 30])
    _zatwierdz_e4(db, platne, 20)

    _check_sr_auto_oplacone(platne)

    assert sr.status == 'czeka_na_oplacenie'


# ---------------------------------------------------------------------------
# Bramka paczki zbiorczej — dokładny scenariusz ze zgłoszenia
# ---------------------------------------------------------------------------

def test_uczestnik_paczki_z_zerowym_kosztem_dochodzi_do_oplacone(db, make_user, make_order):
    """„Cena się nie zmienia" — dołożenie osoby do kartonu nie kosztuje nic.

    Uczestnik z zamówieniem na 0 zł nie ma jak wgrać potwierdzenia, więc wisiał
    na „czeka na opłacenie", a paczka (minimum ze źródeł) nie dochodziła do
    „opłacone" i WMS odrzucał wysyłkę przez UNPAID_SR_STATUSES.
    """
    from test_shipping_consolidation import _konsolidacja
    from modules.admin.payment_confirmations import _sprawdz_oplacenie_konsolidacji

    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)

    uczestnicy = {u['source_request'].id: u for u in zbiorcze.consolidation_participants}
    # sr_a płaci za karton, sr_b dołączył za darmo.
    for o in uczestnicy[sr_a.id]['orders']:
        o.shipping_cost = 25
    for o in uczestnicy[sr_b.id]['orders']:
        o.shipping_cost = 0
    sr_a.status = 'czeka_na_oplacenie'
    sr_b.status = 'czeka_na_oplacenie'
    db.session.commit()

    for o in uczestnicy[sr_a.id]['orders']:
        _zatwierdz_e4(db, o, 25)

    _sprawdz_oplacenie_konsolidacji(zbiorcze)

    assert sr_b.status == 'oplacone', (
        'Uczestnik bez dopłaty nie ma czego zapłacić — nie może blokować paczki'
    )
    assert sr_a.status == 'oplacone'
    assert zbiorcze.status == 'oplacone', (
        'Status paczki to minimum ze źródeł — komplet rozliczonych daje „opłacone"'
    )


def test_uczestnik_paczki_z_nieoplacona_kwota_blokuje(db, make_user, make_order):
    """Regresja: realnie nieopłacony uczestnik nadal wstrzymuje paczkę."""
    from test_shipping_consolidation import _konsolidacja
    from modules.admin.payment_confirmations import _sprawdz_oplacenie_konsolidacji

    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)

    uczestnicy = {u['source_request'].id: u for u in zbiorcze.consolidation_participants}
    for u in uczestnicy.values():
        for o in u['orders']:
            o.shipping_cost = 25
    sr_a.status = 'czeka_na_oplacenie'
    sr_b.status = 'czeka_na_oplacenie'
    db.session.commit()

    for o in uczestnicy[sr_a.id]['orders']:
        _zatwierdz_e4(db, o, 25)

    _sprawdz_oplacenie_konsolidacji(zbiorcze)

    assert sr_a.status == 'oplacone'
    assert sr_b.status == 'czeka_na_oplacenie'
    assert zbiorcze.status != 'oplacone'


# ---------------------------------------------------------------------------
# BUG 3.2 — status liczony ze stanu, nie z wykrytej zmiany kwoty
#
# Awans na „czeka na opłacenie" był warunkowany deltą: `nowy_koszt != old_cost`.
# Zapis modalu bez zmiany kwoty nie robił w warstwie statusów nic, a kwotę E4
# dało się ustawić drugą, niezależną drogą (inline edytor na karcie zamówienia,
# admin_update_order_field), która statusu zlecenia nie dotykała ani razu.
# Efekt: zlecenie w pełni zapłacone widniało jako „Czeka na wycenę".
# ---------------------------------------------------------------------------

def _admin(make_user):
    return make_user(role='admin')


def test_zapis_bez_zmiany_kwoty_przelicza_status(db, client, login, make_user, make_order,
                                                  monkeypatch):
    """Status ma wynikać ze stanu zamówień, nie z tego, czy kwota akurat drgnęła."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    monkeypatch.setattr(EmailManager, 'notify_cost_added', staticmethod(lambda *a, **kw: None))
    monkeypatch.setattr(PushManager, 'notify_cost_added', staticmethod(lambda *a, **kw: None))
    monkeypatch.setattr(EmailManager, 'notify_shipping_status_change',
                        staticmethod(lambda *a, **kw: None))
    monkeypatch.setattr(PushManager, 'notify_shipping_status_change',
                        staticmethod(lambda *a, **kw: None))

    _seed_sr_statuses(db)
    user = make_user()
    sr, (zamowienie,) = _zlecenie(db, user, make_order, koszty=[30])
    # Stan rozjechany: kwota jest, ale status został na „czeka na wycenę"
    # (np. koszt wpisano inline na karcie zamówienia, poza modalem zlecenia).
    sr.status = 'czeka_na_wycene'
    db.session.commit()
    login(_admin(make_user))

    # Zapis TĄ SAMĄ kwotą — delta zerowa.
    r = client.put(f'/admin/orders/shipping-requests/{sr.id}', json={
        'order_costs': [{'order_id': zamowienie.id, 'shipping_cost': 30}],
    })

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert sr.status == 'czeka_na_oplacenie', (
        'Zlecenie z naliczonym kosztem nie może zostać na „czeka na wycenę" '
        'tylko dlatego, że kwota się nie zmieniła'
    )


def test_koszt_wpisany_na_karcie_zamowienia_przelicza_status_zlecenia(
        db, client, login, make_user, make_order, monkeypatch):
    """Inline edytor kosztu na karcie zamówienia to druga droga zapisu E4.

    Ustawiał kwotę i wysyłał klientowi maila „nowy koszt wysyłki krajowej",
    ale statusu zlecenia nie dotykał — klient płacił, admin zatwierdzał,
    a zlecenie zostawało na „czeka na wycenę", bo bramka opłacenia wchodzi
    wyłącznie z „czeka na opłacenie".
    """
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    monkeypatch.setattr(EmailManager, 'notify_cost_added', staticmethod(lambda *a, **kw: None))
    monkeypatch.setattr(PushManager, 'notify_cost_added', staticmethod(lambda *a, **kw: None))
    monkeypatch.setattr(EmailManager, 'notify_shipping_status_change',
                        staticmethod(lambda *a, **kw: None))
    monkeypatch.setattr(PushManager, 'notify_shipping_status_change',
                        staticmethod(lambda *a, **kw: None))

    _seed_sr_statuses(db)
    user = make_user()
    sr, (zamowienie,) = _zlecenie(db, user, make_order, koszty=[0])
    sr.status = 'czeka_na_wycene'
    db.session.commit()
    login(_admin(make_user))

    r = client.post(f'/admin/orders/{zamowienie.id}/update-field', json={
        'field': 'shipping_cost', 'value': 24.99,
    })

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert float(zamowienie.shipping_cost) == 24.99
    assert sr.status == 'czeka_na_oplacenie', (
        'Naliczenie kosztu tą drogą też musi przestawić zlecenie — inaczej '
        'klient płaci, a zlecenie wisi na „czeka na wycenę"'
    )
