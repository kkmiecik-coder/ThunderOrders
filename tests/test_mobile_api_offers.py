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
