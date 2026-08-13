"""Push i dzwonek dla zdarzeń dostawy."""


def _zlecenie(db, user, numer='WYS/000300', status='wyslane'):
    from modules.orders.models import ShippingRequest
    sr = ShippingRequest(request_number=numer, user_id=user.id, status=status)
    db.session.add(sr)
    db.session.commit()
    return sr


def test_przypomnienie_trafia_do_wlasciciela(app, db, make_user, monkeypatch):
    from utils.push_manager import PushManager

    wyslane = []
    monkeypatch.setattr(
        PushManager, '_fire_and_forget',
        staticmethod(lambda **kw: wyslane.append(kw)))

    user = make_user()
    sr = _zlecenie(db, user)

    PushManager.notify_delivery_confirmation(sr)

    assert len(wyslane) == 1
    assert wyslane[0]['user_id'] == user.id
    assert wyslane[0]['notification_type'] == 'shipping_updates'
    assert sr.request_number in wyslane[0]['body']


def test_zlecenie_bez_wlasciciela_nie_wysyla(app, db, monkeypatch):
    from extensions import db as _db
    from modules.orders.models import ShippingRequest
    from utils.push_manager import PushManager

    wyslane = []
    monkeypatch.setattr(
        PushManager, '_fire_and_forget',
        staticmethod(lambda **kw: wyslane.append(kw)))

    sr = ShippingRequest(request_number='WYS/000301', user_id=None, status='wyslane')
    _db.session.add(sr)
    _db.session.commit()

    PushManager.notify_delivery_confirmation(sr)

    assert wyslane == []


def _paczka_zbiorcza_push(db, make_user, make_order, numery):
    """Paczka zbiorcza dwóch klientów — odpowiednik helpera z test_dostawa_maile."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    from extensions import db as _db

    lider = make_user(email='lider-push@example.com')
    drugi = make_user(email='drugi-push@example.com')

    zbiorcze = ShippingRequest(
        request_number=numery[0], user_id=lider.id, status='wyslane')
    _db.session.add(zbiorcze)
    _db.session.commit()

    zrodla = []
    for numer, user in ((numery[1], lider), (numery[2], drugi)):
        zrodlo = ShippingRequest(
            request_number=numer, user_id=user.id, status='wyslane',
            consolidated_into_id=zbiorcze.id)
        _db.session.add(zrodlo)
        _db.session.commit()
        order = make_order(user, status='wyslane')
        _db.session.add(ShippingRequestOrder(
            shipping_request_id=zbiorcze.id, order_id=order.id,
            source_request_id=zrodlo.id))
        _db.session.commit()
        zrodla.append((user, zrodlo))

    zbiorcze.lead_source_request_id = zrodla[0][1].id
    _db.session.commit()
    return zbiorcze, zrodla


def test_push_z_przypomnieniem_omija_uczestnikow_paczki_zbiorczej(
        app, db, make_user, make_order, monkeypatch):
    """Push niesie to samo CTA co mail: „potwierdź odbiór". Uczestnik paczki
    zbiorczej po kliknięciu trafiał na stronę odmawiającą mu tej akcji."""
    from utils.push_manager import PushManager

    wyslane = []
    monkeypatch.setattr(
        PushManager, '_fire_and_forget',
        staticmethod(lambda **kw: wyslane.append(kw)))

    zbiorcze, zrodla = _paczka_zbiorcza_push(
        db, make_user, make_order, ('WYS/000310', 'WYS/000311', 'WYS/000312'))
    (lider, zrodlo_a), (drugi, zrodlo_b) = zrodla

    with app.test_request_context():
        PushManager.notify_delivery_confirmation(zbiorcze)

    assert len(wyslane) == 1, 'o potwierdzenie prosimy wyłącznie lidera'
    assert wyslane[0]['user_id'] == lider.id
    assert zrodlo_a.request_number in wyslane[0]['body']


def test_push_po_odbiorze_nie_dziekuje_uczestnikowi(
        app, db, make_user, make_order, monkeypatch):
    """Odpowiednik ustalenia 1a po stronie pusha: „Dziękujemy za potwierdzenie"
    trafiało do osoby, która nic nie kliknęła."""
    from utils.push_manager import PushManager

    wyslane = []
    monkeypatch.setattr(
        PushManager, '_fire_and_forget',
        staticmethod(lambda **kw: wyslane.append(kw)))

    zbiorcze, zrodla = _paczka_zbiorcza_push(
        db, make_user, make_order, ('WYS/000320', 'WYS/000321', 'WYS/000322'))
    (lider, zrodlo_a), (drugi, zrodlo_b) = zrodla

    with app.test_request_context():
        PushManager.notify_delivery_confirmed(zbiorcze)

    assert len(wyslane) == 2, 'o odbiorze dowiadują się obaj uczestnicy'
    po_userze = {w['user_id']: w for w in wyslane}
    assert po_userze[lider.id]['title'] == 'Dziękujemy za potwierdzenie'
    assert po_userze[drugi.id]['title'] == 'Twoja paczka została odebrana'
    assert 'Dziękujemy' not in po_userze[drugi.id]['title']
    assert 'odbiór potwierdziła osoba' in po_userze[drugi.id]['body']
    assert zrodlo_b.request_number in po_userze[drugi.id]['body']
    assert zrodlo_a.request_number not in po_userze[drugi.id]['body']


def test_potwierdzenie_trafia_do_wlasciciela_zwyklego_zlecenia(
        app, db, make_user, monkeypatch):
    """Podstawowa ścieżka notify_delivery_confirmed (poza paczką zbiorczą) — do tej
    pory pokrywał ją wyłącznie wariant zbiorczy poniżej."""
    from utils.push_manager import PushManager

    wyslane = []
    monkeypatch.setattr(
        PushManager, '_fire_and_forget',
        staticmethod(lambda **kw: wyslane.append(kw)))

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000330', status='dostarczone')

    with app.test_request_context():
        PushManager.notify_delivery_confirmed(sr)

    assert len(wyslane) == 1
    assert wyslane[0]['user_id'] == user.id
    assert wyslane[0]['title'] == 'Dziękujemy za potwierdzenie'
    assert sr.request_number in wyslane[0]['body']
    assert wyslane[0]['notification_type'] == 'shipping_updates'


def test_autoclosed_trafia_do_wlasciciela_zwyklego_zlecenia(
        app, db, make_user, monkeypatch):
    """Brak jakiegokolwiek testu treści dla notify_delivery_autoclosed."""
    from utils.push_manager import PushManager

    wyslane = []
    monkeypatch.setattr(
        PushManager, '_fire_and_forget',
        staticmethod(lambda **kw: wyslane.append(kw)))

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000340', status='dostarczone')

    with app.test_request_context():
        PushManager.notify_delivery_autoclosed(sr)

    assert len(wyslane) == 1
    assert wyslane[0]['user_id'] == user.id
    assert wyslane[0]['title'] == 'Zamykamy Twoje zlecenie'
    assert sr.request_number in wyslane[0]['body']
    assert wyslane[0]['notification_type'] == 'shipping_updates'


def test_autoclosed_zbiorcza_dociera_do_obu_uczestnikow_bez_wycieku(
        app, db, make_user, make_order, monkeypatch):
    """Wariant paczki zbiorczej notify_delivery_autoclosed: idzie do WSZYSTKICH
    uczestników (w odróżnieniu od notify_delivery_confirmation, które idzie
    wyłącznie do lidera) — to informacja, nie prośba o czynność, którą wykonać
    może tylko jedna osoba. Każdy dostaje treść o SWOIM zleceniu źródłowym i nie
    widzi numeru zamówienia drugiego uczestnika."""
    from utils.push_manager import PushManager

    wyslane = []
    monkeypatch.setattr(
        PushManager, '_fire_and_forget',
        staticmethod(lambda **kw: wyslane.append(kw)))

    zbiorcze, zrodla = _paczka_zbiorcza_push(
        db, make_user, make_order, ('WYS/000350', 'WYS/000351', 'WYS/000352'))
    (lider, zrodlo_a), (drugi, zrodlo_b) = zrodla

    with app.test_request_context():
        PushManager.notify_delivery_autoclosed(zbiorcze)

    assert len(wyslane) == 2, 'o domknięciu dowiadują się obaj uczestnicy'
    po_userze = {w['user_id']: w for w in wyslane}
    assert zrodlo_a.request_number in po_userze[lider.id]['body']
    assert zrodlo_b.request_number in po_userze[drugi.id]['body']
    assert zrodlo_b.request_number not in po_userze[lider.id]['body']
    assert zrodlo_a.request_number not in po_userze[drugi.id]['body']
    # Bez rozróżnienia ról — tytuł i ton identyczne dla lidera i uczestnika,
    # bo nikt tu niczego nie potwierdzał (patrz docstring w push_manager.py).
    assert po_userze[lider.id]['title'] == po_userze[drugi.id]['title']


def test_powiadomienie_dla_adminow_idzie_do_kazdego(app, db, make_user, monkeypatch):
    from utils.push_manager import PushManager

    wyslane = []
    monkeypatch.setattr(
        PushManager, '_fire_and_forget',
        staticmethod(lambda **kw: wyslane.append(kw)))

    make_user(role='admin', email='a1@example.com')
    make_user(role='admin', email='a2@example.com')
    klient = make_user()
    sr = _zlecenie(db, klient, 'WYS/000302', status='dostarczone')

    PushManager.notify_admin_delivery_confirmed(sr)

    assert len(wyslane) == 2
    assert all(w['notification_type'] == 'admin_alerts' for w in wyslane)


def test_powiadomienie_dla_adminow_bledny_push_nie_przerywa_petli(
        app, db, make_user, monkeypatch):
    """Wyrównanie do notify_sale_date_changed: wyjątek przy jednym adminie (np.
    martwa subskrypcja push) nie może uciąć powiadomień dla pozostałych — pętla
    ma try/except per admin, tak jak sąsiedni wzorzec."""
    from utils.push_manager import PushManager

    wyslane = []

    def _fire(**kw):
        if kw['user_id'] == pierwszy.id:
            raise RuntimeError('subskrypcja martwa')
        wyslane.append(kw)

    monkeypatch.setattr(PushManager, '_fire_and_forget', staticmethod(_fire))

    pierwszy = make_user(role='admin', email='a1-fail@example.com')
    drugi = make_user(role='admin', email='a2-ok@example.com')
    klient = make_user()
    sr = _zlecenie(db, klient, 'WYS/000303', status='dostarczone')

    wynik = PushManager.notify_admin_delivery_confirmed(sr)

    assert len(wyslane) == 1, 'drugi admin ma dostać push mimo błędu u pierwszego'
    assert wyslane[0]['user_id'] == drugi.id
    assert wynik == 1, 'zwrócona liczba to sent/total, jak w notify_sale_date_changed'
