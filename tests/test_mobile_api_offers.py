"""Testy E3: mobilne API stron ofertowych (read-only: lista, struktura, availability).

Helper _auth skopiowany z tests/test_mobile_api_cart.py.
"""


# ---------------------------------------------------------------------------
# Wspólne helpery
# ---------------------------------------------------------------------------

def _auth(client, db, make_user):
    """Tworzy usera, loguje przez mobile API i zwraca (headers, user)."""
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': u.email, 'password': 'Haslo123!'})
    token = r.get_json()['data']['access_token']
    return {'Authorization': f'Bearer {token}'}, u


def _make_page(db, status, page_type='exclusive', payment_stages=4):
    """Tworzy OfferPage z podanym statusem. Wymaga usera id=1 (tworzonego przez _auth)."""
    from modules.offers.models import OfferPage
    p = OfferPage(
        name=f'Drop {status}',
        token=OfferPage.generate_token(),
        status=status,
        page_type=page_type,
        payment_stages=payment_stages,
        created_by=1,
    )
    db.session.add(p)
    db.session.commit()
    return p


# ---------------------------------------------------------------------------
# Task 4: GET /offers/offer-pages (lista + mapowanie statusów)
# ---------------------------------------------------------------------------

def test_offer_pages_requires_token(client):
    assert client.get('/api/mobile/v1/offers/offer-pages').status_code == 401


def test_offer_pages_filter_live(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _make_page(db, 'active'); _make_page(db, 'scheduled'); _make_page(db, 'ended')
    _make_page(db, 'draft')  # nigdy nie eksponowany
    r = client.get('/api/mobile/v1/offers/offer-pages?status=live', headers=h)
    assert r.status_code == 200
    data = r.get_json()
    assert all(p['status'] == 'live' for p in data['data'])
    assert len(data['data']) == 1
    assert 'pagination' in data


def test_offer_pages_excludes_draft_always(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _make_page(db, 'draft')
    for st in ('live', 'upcoming', 'closed'):
        r = client.get(f'/api/mobile/v1/offers/offer-pages?status={st}', headers=h)
        assert all(p['status'] != 'draft' for p in r.get_json()['data'])


def test_offer_pages_includes_both_types(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _make_page(db, 'active', page_type='exclusive')
    _make_page(db, 'active', page_type='preorder')
    r = client.get('/api/mobile/v1/offers/offer-pages?status=live', headers=h)
    types = {p['page_type'] for p in r.get_json()['data']}
    assert types == {'exclusive', 'preorder'}


# ---------------------------------------------------------------------------
# Task 5: GET /offers/offer-pages/<token> (struktura) + GET .../availability
# ---------------------------------------------------------------------------

def test_offer_page_structure_draft_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    page = _make_page(db, 'draft')
    assert client.get(
        f'/api/mobile/v1/offers/offer-pages/{page.token}', headers=h
    ).status_code == 404


def test_offer_page_structure_product_section(client, db, make_user, make_product):
    from modules.offers.models import OfferSection
    h, _ = _auth(client, db, make_user)
    page = _make_page(db, 'active')
    prod = make_product(sale_price='50.00')
    db.session.add(OfferSection(offer_page_id=page.id, section_type='product',
                                product_id=prod.id, max_quantity=10, sort_order=0))
    db.session.add(OfferSection(offer_page_id=page.id, section_type='heading',
                                content='Nagłówek', sort_order=1))
    db.session.commit()
    r = client.get(f'/api/mobile/v1/offers/offer-pages/{page.token}', headers=h)
    assert r.status_code == 200
    d = r.get_json()['data']
    assert d['page_type'] == 'exclusive' and d['payment_stages'] in (3, 4)
    secs = d['sections']
    prod_sec = next(s for s in secs if s['section_type'] == 'product')
    assert prod_sec['product']['price'] == 5000          # grosze
    assert prod_sec['max_quantity'] == 10
    head_sec = next(s for s in secs if s['section_type'] == 'heading')
    assert head_sec['content'] == 'Nagłówek'


def test_offer_availability_snapshot(client, db, make_user, make_product):
    from modules.offers.models import OfferSection, OfferReservation
    import time
    h, _ = _auth(client, db, make_user)
    page = _make_page(db, 'active')
    prod = make_product(sale_price='10.00')
    db.session.add(OfferSection(offer_page_id=page.id, section_type='product',
                                product_id=prod.id, max_quantity=5, sort_order=0))
    now = int(time.time())
    db.session.add(OfferReservation(session_id='other', offer_page_id=page.id, product_id=prod.id,
                                    quantity=2, reserved_at=now, expires_at=now + 120))
    db.session.commit()
    r = client.get(
        f'/api/mobile/v1/offers/offer-pages/{page.token}/availability?session_id=mine',
        headers=h,
    )
    assert r.status_code == 200
    pdata = r.get_json()['data']['products'][str(prod.id)]
    assert pdata['available'] == 3 and pdata['total_reserved'] == 2   # SZTUKI, nie grosze


# ---------------------------------------------------------------------------
# Task 6: POST /offers/<token>/{reserve,extend,release} (+ emisje Socket.IO)
# ---------------------------------------------------------------------------

def test_reserve_requires_token(client, db, make_user):
    page = _make_page(db, 'active')
    assert client.post(f'/api/mobile/v1/offers/{page.token}/reserve', json={}).status_code == 401


def test_reserve_then_availability_reflects(client, db, make_user, make_product):
    from modules.offers.models import OfferSection
    h, _ = _auth(client, db, make_user)
    page = _make_page(db, 'active')
    prod = make_product(sale_price='10.00')
    db.session.add(OfferSection(offer_page_id=page.id, section_type='product',
                                product_id=prod.id, max_quantity=5, sort_order=0)); db.session.commit()
    r = client.post(f'/api/mobile/v1/offers/{page.token}/reserve', headers=h,
                    json={'session_id': 'mine', 'product_id': prod.id, 'quantity': 2})
    assert r.status_code == 200 and r.get_json()['data']['reservation']['quantity'] == 2
    a = client.get(f'/api/mobile/v1/offers/offer-pages/{page.token}/availability?session_id=mine',
                   headers=h)
    assert a.get_json()['data']['products'][str(prod.id)]['available'] == 3


def test_reserve_insufficient_409(client, db, make_user, make_product):
    from modules.offers.models import OfferSection, OfferReservation
    import time
    h, _ = _auth(client, db, make_user)
    page = _make_page(db, 'active')
    prod = make_product(sale_price='10.00')
    db.session.add(OfferSection(offer_page_id=page.id, section_type='product',
                                product_id=prod.id, max_quantity=1, sort_order=0))
    now = int(time.time())
    db.session.add(OfferReservation(session_id='other', offer_page_id=page.id, product_id=prod.id,
                                    quantity=1, reserved_at=now, expires_at=now + 120))
    db.session.commit()
    r = client.post(f'/api/mobile/v1/offers/{page.token}/reserve', headers=h,
                    json={'session_id': 'mine', 'product_id': prod.id, 'quantity': 1})
    assert r.status_code == 409
    assert r.get_json()['error']['code'] == 'insufficient_availability'


def test_extend_once_then_already_extended(client, db, make_user, make_product):
    # reserve → extend (200) → extend ponownie (400 already_extended)
    from modules.offers.models import OfferSection
    h, _ = _auth(client, db, make_user)
    page = _make_page(db, 'active')
    prod = make_product(sale_price='10.00')
    db.session.add(OfferSection(offer_page_id=page.id, section_type='product',
                                product_id=prod.id, max_quantity=5, sort_order=0)); db.session.commit()
    client.post(f'/api/mobile/v1/offers/{page.token}/reserve', headers=h,
                json={'session_id': 'mine', 'product_id': prod.id, 'quantity': 1})
    r1 = client.post(f'/api/mobile/v1/offers/{page.token}/extend', headers=h,
                     json={'session_id': 'mine'})
    assert r1.status_code == 200 and 'new_expires_at' in r1.get_json()['data']
    r2 = client.post(f'/api/mobile/v1/offers/{page.token}/extend', headers=h,
                     json={'session_id': 'mine'})
    assert r2.status_code == 400
    assert r2.get_json()['error']['code'] == 'already_extended'


def test_release_reduces_reservation(client, db, make_user, make_product):
    # reserve qty=2 → release qty=2 → availability wraca do max
    from modules.offers.models import OfferSection
    h, _ = _auth(client, db, make_user)
    page = _make_page(db, 'active')
    prod = make_product(sale_price='10.00')
    db.session.add(OfferSection(offer_page_id=page.id, section_type='product',
                                product_id=prod.id, max_quantity=5, sort_order=0)); db.session.commit()
    client.post(f'/api/mobile/v1/offers/{page.token}/reserve', headers=h,
                json={'session_id': 'mine', 'product_id': prod.id, 'quantity': 2})
    r = client.post(f'/api/mobile/v1/offers/{page.token}/release', headers=h,
                    json={'session_id': 'mine', 'product_id': prod.id, 'quantity': 2})
    assert r.status_code == 200
    a = client.get(f'/api/mobile/v1/offers/offer-pages/{page.token}/availability?session_id=mine',
                   headers=h)
    assert a.get_json()['data']['products'][str(prod.id)]['available'] == 5
