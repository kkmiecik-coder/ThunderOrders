"""API mobilne — potwierdzenie odbioru i ocena dostawy (parytet z webem)."""
from datetime import timedelta


def _auth(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': u.email, 'password': 'Haslo123!'})
    return {'Authorization': f'Bearer {r.get_json()["data"]["access_token"]}'}, u


def _wyslane(db, user, numer, dni_temu=4):
    from modules.orders.models import ShippingRequest, get_local_now
    sr = ShippingRequest(
        request_number=numer, user_id=user.id, status='wyslane',
        shipped_at=get_local_now() - timedelta(days=dni_temu))
    db.session.add(sr)
    db.session.commit()
    return sr


def test_serializacja_zawiera_pola_dostawy(client, db, make_user):
    h, u = _auth(client, db, make_user)
    _wyslane(db, u, 'WYS/000700')

    dane = client.get('/api/mobile/v1/shipping/requests', headers=h).get_json()['data']
    zlecenie = dane['requests'][0]

    assert set(zlecenie) >= {'shipped_at', 'delivered_at', 'delivered_source',
                             'can_confirm_delivery', 'review'}
    assert zlecenie['can_confirm_delivery'] is True
    assert zlecenie['review'] is None


def test_potwierdzenie_domyka_zlecenie(client, db, make_user):
    h, u = _auth(client, db, make_user)
    sr = _wyslane(db, u, 'WYS/000701')

    r = client.post(f'/api/mobile/v1/shipping/requests/{sr.id}/confirm-delivery',
                    json={'rating': 5, 'comment': 'Ekspresowo'}, headers=h)

    assert r.status_code == 200
    assert sr.status == 'dostarczone'
    assert sr.delivered_source == 'klient'
    assert sr.review.rating == 5
    assert r.get_json()['data']['request']['review']['rating'] == 5


def test_cudze_zlecenie_zwraca_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    h2, obcy = _auth(client, db, make_user)
    sr = _wyslane(db, obcy, 'WYS/000702')

    r = client.post(f'/api/mobile/v1/shipping/requests/{sr.id}/confirm-delivery',
                    json={}, headers=h)

    assert r.status_code == 404
    assert sr.status == 'wyslane'


def test_uczestnik_paczki_zbiorczej_dostaje_403(client, db, make_user):
    h, uczestnik = _auth(client, db, make_user)
    lider = make_user()
    zbiorcze = _wyslane(db, lider, 'WYS/000710')
    zrodlo_lidera = _wyslane(db, lider, 'WYS/000711')
    zrodlo_uczestnika = _wyslane(db, uczestnik, 'WYS/000712')
    for z in (zrodlo_lidera, zrodlo_uczestnika):
        z.consolidated_into_id = zbiorcze.id
    zbiorcze.lead_source_request_id = zrodlo_lidera.id
    db.session.commit()

    r = client.post(
        f'/api/mobile/v1/shipping/requests/{zrodlo_uczestnika.id}/confirm-delivery',
        json={}, headers=h)

    assert r.status_code == 403
    assert zbiorcze.status == 'wyslane'


def test_powtorzony_idempotency_key_nie_dubluje(client, db, make_user):
    h, u = _auth(client, db, make_user)
    sr = _wyslane(db, u, 'WYS/000720')
    naglowki = dict(h)
    naglowki['Idempotency-Key'] = 'dostawa-720'

    pierwsza = client.post(
        f'/api/mobile/v1/shipping/requests/{sr.id}/confirm-delivery',
        json={'rating': 4}, headers=naglowki)
    druga = client.post(
        f'/api/mobile/v1/shipping/requests/{sr.id}/confirm-delivery',
        json={'rating': 4}, headers=naglowki)

    assert pierwsza.status_code == 200
    assert druga.status_code == 200
    assert druga.get_json() == pierwsza.get_json()

    from modules.orders.review_models import DeliveryReview
    assert DeliveryReview.query.filter_by(shipping_request_id=sr.id).count() == 1


def test_edycja_oceny_po_oknie_zwraca_409(client, db, make_user):
    from modules.orders.models import get_local_now

    h, u = _auth(client, db, make_user)
    sr = _wyslane(db, u, 'WYS/000730')
    client.post(f'/api/mobile/v1/shipping/requests/{sr.id}/confirm-delivery',
                json={'rating': 3}, headers=h)

    sr.review.created_at = get_local_now() - timedelta(days=4)
    db.session.commit()

    r = client.put(f'/api/mobile/v1/shipping/requests/{sr.id}/review',
                   json={'rating': 1}, headers=h)

    assert r.status_code == 409
    assert sr.review.rating == 3


def test_potwierdzenie_niewyslanego_zlecenia_zwraca_409(client, db, make_user):
    """Poprawka do briefu: mobilne API musi tak samo jak web odrzucać status != 'wyslane'
    (409) ZANIM cokolwiek zapisze — inaczej apka miałaby furtkę, której web nie ma."""
    from modules.orders.models import ShippingRequest

    h, u = _auth(client, db, make_user)
    # 'oplacone' to poprawny slug w słowniku ShippingRequestStatus (status.shipping_requests
    # jest FK do słownika, w odróżnieniu od orders.status — 'nowe' tam nie istnieje).
    sr = ShippingRequest(request_number='WYS/000740', user_id=u.id, status='oplacone')
    db.session.add(sr)
    db.session.commit()

    r = client.post(f'/api/mobile/v1/shipping/requests/{sr.id}/confirm-delivery',
                    json={'rating': 5}, headers=h)

    assert r.status_code == 409
    assert sr.status == 'oplacone'
    assert sr.review is None
