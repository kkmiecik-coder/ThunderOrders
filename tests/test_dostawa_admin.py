"""Admin: lista opinii i metryki dostaw."""


def _dostarczone(db, user, numer, source):
    from modules.orders.models import ShippingRequest, get_local_now
    sr = ShippingRequest(request_number=numer, user_id=user.id, status='dostarczone',
                         delivered_at=get_local_now(), delivered_source=source)
    db.session.add(sr)
    db.session.commit()
    return sr


def test_statystyki_licza_srednia_i_rozklad(app, db, make_user):
    from modules.admin.statistics import statystyki_dostaw
    from modules.orders.review_models import DeliveryReview

    user = make_user()
    for i, ocena in enumerate((5, 5, 3), start=1):
        sr = _dostarczone(db, user, f'WYS/00060{i}', 'klient')
        db.session.add(DeliveryReview(
            shipping_request_id=sr.id, user_id=user.id, rating=ocena))
    db.session.commit()

    dane = statystyki_dostaw()

    assert dane['liczba_opinii'] == 3
    assert round(dane['srednia_ocena'], 2) == 4.33
    assert dane['rozklad'][5] == 2
    assert dane['rozklad'][3] == 1
    assert dane['rozklad'][1] == 0


def test_statystyki_licza_udzial_potwierdzen(app, db, make_user):
    from modules.admin.statistics import statystyki_dostaw

    user = make_user()
    _dostarczone(db, user, 'WYS/000610', 'klient')
    _dostarczone(db, user, 'WYS/000611', 'auto')
    _dostarczone(db, user, 'WYS/000612', 'auto')
    _dostarczone(db, user, 'WYS/000613', 'auto')

    dane = statystyki_dostaw()

    assert dane['potwierdzone_przez_klienta'] == 1
    assert dane['domkniete_automatem'] == 3
    assert dane['udzial_potwierdzen'] == 25.0


def test_statystyki_bez_danych_nie_dziela_przez_zero(app, db):
    from modules.admin.statistics import statystyki_dostaw

    dane = statystyki_dostaw()

    assert dane['liczba_opinii'] == 0
    assert dane['srednia_ocena'] is None
    assert dane['udzial_potwierdzen'] == 0.0


def test_lista_opinii_wymaga_admina(app, db, client, login, make_user):
    klient = make_user()
    login(klient)

    odp = client.get('/admin/shipping-requests/opinie')

    assert odp.status_code in (302, 403)


def test_lista_opinii_filtruje_po_ocenie(app, db, client, login, make_user):
    from modules.orders.review_models import DeliveryReview

    admin = make_user(role='admin', profile_completed=True)
    klient = make_user()
    sr_a = _dostarczone(db, klient, 'WYS/000620', 'klient')
    sr_b = _dostarczone(db, klient, 'WYS/000621', 'klient')
    db.session.add(DeliveryReview(shipping_request_id=sr_a.id, user_id=klient.id, rating=5))
    db.session.add(DeliveryReview(shipping_request_id=sr_b.id, user_id=klient.id, rating=2))
    db.session.commit()

    login(admin)
    odp = client.get('/admin/shipping-requests/opinie?rating=2')

    assert odp.status_code == 200
    assert b'WYS/000621' in odp.data
    assert b'WYS/000620' not in odp.data
