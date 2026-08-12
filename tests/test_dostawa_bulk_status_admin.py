"""Zbiorcza zmiana statusu zleceń wysyłki (/admin/orders/shipping-requests/bulk-status).

Endpoint rzucał UnboundLocalError przy KAŻDYM wywołaniu (500) — lokalny import
`ShippingRequestStatus` w bloku wysyłki powiadomień czynił tę nazwę lokalną dla
CAŁEJ funkcji (reguła zasięgu Pythona), a była już użyta ~30 linii wcześniej przy
walidacji statusu. Zero istniejącego pokrycia testami. Te testy to pierwsze
przejście przez endpoint end-to-end, plus poprawka „przy okazji": zlecenie
źródłowe paczki zbiorczej nie może dostać statusu wprost, bo dostarcz_zlecenie()
i tak by je odrzuciło, ale PO tym, jak commit wyżej już zapisałby połowiczny stan.
"""
from modules.orders.models import ShippingRequest, ShippingRequestOrder


def _admin(make_user):
    return make_user(role='admin', email='admin-bulk-status@example.com', profile_completed=True)


def _zlecenie(db, user, numer, status='wyslane'):
    sr = ShippingRequest(request_number=numer, user_id=user.id, status=status)
    db.session.add(sr)
    db.session.commit()
    return sr


def _podepnij(db, sr, order):
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=order.id))
    db.session.commit()


def test_endpoint_dziala_end_to_end_zamiast_500(db, client, login, make_user, make_order):
    """Regresja na I1: przed poprawką KAŻDE wywołanie tego endpointu kończyło się
    UnboundLocalError, niezależnie od danych wejściowych."""
    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000700', status='spakowane')
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/bulk-status', json={
        'ids': [sr.id], 'status': 'wyslane',
    })

    assert r.status_code == 200
    dane = r.get_json()
    assert dane['success'] is True

    db.session.refresh(sr)
    assert sr.status == 'wyslane'


def test_przejscie_na_dostarczone_kaskaduje_i_dopisuje_kolekcje(
        db, client, login, make_user, make_order, make_product):
    """Przejście na 'dostarczone' przez ten endpoint ma iść przez dostarcz_zlecenie()
    (via _sync_order_statuses_from_shipping_request) — delivered_at, kaskada na
    zamówienie i dopisanie do kolekcji klienta, nie samo przestawienie kolumny status."""
    from modules.client.models import CollectionItem
    from modules.orders.models import OrderItem

    user = make_user()
    produkt = make_product()
    sr = _zlecenie(db, user, 'WYS/000701', status='wyslane')
    order = make_order(user, status='wyslane')
    db.session.add(OrderItem(
        order_id=order.id, product_id=produkt.id, quantity=1, price=50.00, total=50.00))
    db.session.commit()
    _podepnij(db, sr, order)
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/bulk-status', json={
        'ids': [sr.id], 'status': 'dostarczone',
    })

    assert r.status_code == 200
    db.session.refresh(sr)
    db.session.refresh(order)
    assert sr.status == 'dostarczone'
    assert sr.delivered_at is not None
    assert sr.delivered_source == 'admin'
    assert order.status == 'dostarczone'
    assert CollectionItem.query.filter_by(user_id=user.id).count() == 1


def test_pomija_samo_zrodlo_paczki_zbiorczej_bez_polowicznego_stanu(
        db, client, login, make_user, make_order):
    """I2, znalezione przy naprawie I1: zaznaczenie SAMEGO źródła (bez jego paczki)
    nie może ustawić mu status='dostarczone' bez delivered_at/kaskady/kolekcji.
    Dawniej właśnie to się działo — dostarcz_zlecenie() odrzucał źródło poprzez
    ZlecenieZrodloweNieDomykane, ale DOPIERO PO tym, jak wcześniejszy commit w tej
    samej funkcji już zapisał status wprost. Nic tego już nie podnosiło (cron
    filtruje status=='wyslane')."""
    from modules.client.models import CollectionItem

    lider = make_user(email='lider-bulk@example.com')
    zbiorcze = _zlecenie(db, lider, 'WYS/000710', status='wyslane')
    zrodlo = _zlecenie(db, lider, 'WYS/000711', status='wyslane')
    zrodlo.consolidated_into_id = zbiorcze.id
    db.session.commit()
    order = make_order(lider, status='wyslane')
    _podepnij(db, zrodlo, order)
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/bulk-status', json={
        'ids': [zrodlo.id], 'status': 'dostarczone',
    })

    assert r.status_code == 200
    dane = r.get_json()
    assert dane['skipped_source_count'] == 1

    db.session.refresh(zrodlo)
    db.session.refresh(order)
    # Kluczowa asercja: bez poprawki status byłby 'dostarczone' z pustym delivered_at.
    assert zrodlo.status == 'wyslane'
    assert zrodlo.delivered_at is None
    assert order.status == 'wyslane'
    assert CollectionItem.query.filter_by(user_id=lider.id).count() == 0


def test_paczka_i_zrodlo_razem_domykaja_sie_poprawnie(db, client, login, make_user):
    """Gdy paczka zbiorcza JEST w tym samym zaznaczeniu co jej źródło, źródło i tak
    dostaje pełne domknięcie (status + delivered_at) — przez propagację z paczki
    (propaguj_na_zrodla / dostarcz_zlecenie), a nie przez bezpośredni zapis, który
    dla źródeł teraz pomijamy. Dotyczy też drugiego źródła, którego wcale nie było
    w `ids` — paczka domyka WSZYSTKICH swoich uczestników."""
    lider = make_user(email='lider-bulk2@example.com')
    drugi = make_user(email='drugi-bulk2@example.com')
    zbiorcze = _zlecenie(db, lider, 'WYS/000720', status='wyslane')
    zrodlo_a = _zlecenie(db, lider, 'WYS/000721', status='wyslane')
    zrodlo_b = _zlecenie(db, drugi, 'WYS/000722', status='wyslane')
    for z in (zrodlo_a, zrodlo_b):
        z.consolidated_into_id = zbiorcze.id
    db.session.commit()
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/bulk-status', json={
        'ids': [zrodlo_a.id, zbiorcze.id], 'status': 'dostarczone',
    })

    assert r.status_code == 200
    db.session.refresh(zbiorcze)
    db.session.refresh(zrodlo_a)
    db.session.refresh(zrodlo_b)
    assert zbiorcze.status == 'dostarczone'
    assert zbiorcze.delivered_at is not None
    assert zrodlo_a.status == 'dostarczone'
    assert zrodlo_a.delivered_at is not None
    assert zrodlo_b.status == 'dostarczone'
    assert zrodlo_b.delivered_at is not None


def test_endpoint_wymaga_roli_admina_lub_mod(client, db, make_user, login):
    login(make_user(role='client'))

    r = client.post('/admin/orders/shipping-requests/bulk-status', json={
        'ids': [1], 'status': 'wyslane',
    })

    assert r.status_code == 403


def test_endpoint_odrzuca_brak_id(client, db, make_user, login):
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/bulk-status', json={
        'ids': [], 'status': 'wyslane',
    })

    assert r.status_code == 400


def test_endpoint_odrzuca_nieznany_status(db, client, login, make_user):
    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000730', status='wyslane')
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/bulk-status', json={
        'ids': [sr.id], 'status': 'nieistniejacy-status',
    })

    assert r.status_code == 400
    db.session.refresh(sr)
    assert sr.status == 'wyslane'
