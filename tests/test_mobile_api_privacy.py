"""Testy Task 12: bramka prywatności stron ofertowych w Mobile API.

Wzorzec auth skopiowany z tests/test_mobile_api_offers.py.
"""


# ---------------------------------------------------------------------------
# Helpery
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


def _make_page(db, status='active', page_type='exclusive', payment_stages=4, is_private=False):
    """Tworzy OfferPage. Wymaga usera id=1 (tworzonego przez _auth)."""
    from modules.offers.models import OfferPage
    p = OfferPage(
        name=f'Drop {status} priv={is_private}',
        token=OfferPage.generate_token(),
        status=status,
        page_type=page_type,
        payment_stages=payment_stages,
        created_by=1,
        is_private=is_private,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _add_audience_user(db, page, user):
    """Dodaje usera bezpośrednio do odbiorców strony (offer_page_users)."""
    from modules.offers.models import offer_page_users
    db.session.execute(
        offer_page_users.insert().values(offer_page_id=page.id, user_id=user.id)
    )
    db.session.commit()


def _add_audience_via_group(db, page, user):
    """Tworzy grupę, wpisuje do niej usera, dodaje grupę do odbiorców strony."""
    from modules.auth.models import UserGroup, user_group_members
    from modules.offers.models import offer_page_groups
    group = UserGroup(name=f'Priv-group-{page.id}-{user.id}', created_by=1)
    db.session.add(group)
    db.session.commit()
    db.session.execute(
        user_group_members.insert().values(user_group_id=group.id, user_id=user.id)
    )
    db.session.execute(
        offer_page_groups.insert().values(offer_page_id=page.id, user_group_id=group.id)
    )
    db.session.commit()
    return group


# ---------------------------------------------------------------------------
# GET /offers/offer-pages/<token>  (detail)
# ---------------------------------------------------------------------------

def test_private_page_detail_outsider_404(client, db, make_user):
    """Outsider nie widzi prywatnej strony przez token — 404 page_not_found."""
    h, _outsider = _auth(client, db, make_user)
    page = _make_page(db, 'active', is_private=True)
    r = client.get(f'/api/mobile/v1/offers/offer-pages/{page.token}', headers=h)
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'page_not_found'


def test_private_page_detail_audience_user_direct_200(client, db, make_user):
    """Użytkownik w allowed_users (bezpośredni) widzi prywatną stronę — 200."""
    h_outsider, _outsider = _auth(client, db, make_user)   # id=1
    h_member, member = _auth(client, db, make_user)        # id=2
    page = _make_page(db, 'active', is_private=True)
    _add_audience_user(db, page, member)
    r = client.get(f'/api/mobile/v1/offers/offer-pages/{page.token}', headers=h_member)
    assert r.status_code == 200
    # Upewniamy się, że outsider nadal nie widzi
    r2 = client.get(f'/api/mobile/v1/offers/offer-pages/{page.token}', headers=h_outsider)
    assert r2.status_code == 404


def test_private_page_detail_audience_via_group_200(client, db, make_user):
    """Użytkownik w dozwolonej grupie widzi prywatną stronę — 200."""
    h_outsider, _outsider = _auth(client, db, make_user)   # id=1
    h_member, member = _auth(client, db, make_user)        # id=2
    page = _make_page(db, 'active', is_private=True)
    _add_audience_via_group(db, page, member)
    r = client.get(f'/api/mobile/v1/offers/offer-pages/{page.token}', headers=h_member)
    assert r.status_code == 200
    r2 = client.get(f'/api/mobile/v1/offers/offer-pages/{page.token}', headers=h_outsider)
    assert r2.status_code == 404


# ---------------------------------------------------------------------------
# GET /offers/offer-pages  (lista)
# ---------------------------------------------------------------------------

def test_private_page_not_in_list_for_outsider(client, db, make_user):
    """Outsider nie widzi prywatnej strony na liście."""
    h, _outsider = _auth(client, db, make_user)
    page = _make_page(db, 'active', is_private=True)
    r = client.get('/api/mobile/v1/offers/offer-pages?status=live', headers=h)
    assert r.status_code == 200
    tokens = [p['token'] for p in r.get_json()['data']]
    assert page.token not in tokens


def test_private_page_in_list_for_audience_user(client, db, make_user):
    """Użytkownik w allowed_users widzi prywatną stronę na liście."""
    h_outsider, _outsider = _auth(client, db, make_user)   # id=1
    h_member, member = _auth(client, db, make_user)        # id=2
    page = _make_page(db, 'active', is_private=True)
    _add_audience_user(db, page, member)
    r = client.get('/api/mobile/v1/offers/offer-pages?status=live', headers=h_member)
    tokens = [p['token'] for p in r.get_json()['data']]
    assert page.token in tokens
    # Outsider nadal nie widzi
    r2 = client.get('/api/mobile/v1/offers/offer-pages?status=live', headers=h_outsider)
    tokens2 = [p['token'] for p in r2.get_json()['data']]
    assert page.token not in tokens2


def test_private_page_in_list_for_audience_group_member(client, db, make_user):
    """Użytkownik w dozwolonej grupie widzi prywatną stronę na liście."""
    h_outsider, _outsider = _auth(client, db, make_user)   # id=1
    h_member, member = _auth(client, db, make_user)        # id=2
    page = _make_page(db, 'active', is_private=True)
    _add_audience_via_group(db, page, member)
    r = client.get('/api/mobile/v1/offers/offer-pages?status=live', headers=h_member)
    tokens = [p['token'] for p in r.get_json()['data']]
    assert page.token in tokens


def test_public_page_always_in_list(client, db, make_user):
    """Strona publiczna widoczna dla każdego zalogowanego (regres)."""
    h, _user = _auth(client, db, make_user)
    page = _make_page(db, 'active', is_private=False)
    r = client.get('/api/mobile/v1/offers/offer-pages?status=live', headers=h)
    tokens = [p['token'] for p in r.get_json()['data']]
    assert page.token in tokens


# ---------------------------------------------------------------------------
# POST /offers/<token>/place-order  (exclusive)
# ---------------------------------------------------------------------------

def test_private_page_place_order_outsider_404(client, db, make_user):
    """Outsider nie może złożyć zamówienia na prywatnej stronie — 404 page_not_found."""
    h, _outsider = _auth(client, db, make_user)
    page = _make_page(db, 'active', is_private=True)
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order', headers=h,
                    json={'session_id': 'x'})
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'page_not_found'


def test_public_page_place_order_audience_not_required(client, db, make_user):
    """Publiczna strona nie wymaga audytorium — place-order nie zwraca 404 privacy-gate
    (może zwrócić inny błąd np. page_not_active lub no_reservations, ale NIE page_not_found
    z powodu prywatności)."""
    h, _user = _auth(client, db, make_user)
    page = _make_page(db, 'active', is_private=False)
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order', headers=h,
                    json={'session_id': 'x'})
    # Może być 400/409 etc — ważne że nie 404 przez bramkę prywatności
    assert not (r.status_code == 404 and r.get_json()['error']['code'] == 'page_not_found')


# ---------------------------------------------------------------------------
# Dostępność i rezerwacje na prywatnych stronach
# ---------------------------------------------------------------------------

def test_private_page_availability_outsider_404(client, db, make_user):
    """Outsider nie widzi dostępności prywatnej strony."""
    h, _outsider = _auth(client, db, make_user)
    page = _make_page(db, 'active', is_private=True)
    r = client.get(f'/api/mobile/v1/offers/offer-pages/{page.token}/availability', headers=h)
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'page_not_found'


def test_private_page_reserve_outsider_404(client, db, make_user, make_product):
    """Outsider nie może zarezerwować na prywatnej stronie."""
    from modules.offers.models import OfferSection
    h, _outsider = _auth(client, db, make_user)
    page = _make_page(db, 'active', is_private=True)
    prod = make_product(sale_price='10.00')
    db.session.add(OfferSection(offer_page_id=page.id, section_type='product',
                                product_id=prod.id, max_quantity=5, sort_order=0))
    db.session.commit()
    r = client.post(f'/api/mobile/v1/offers/{page.token}/reserve', headers=h,
                    json={'session_id': 'x', 'product_id': prod.id, 'quantity': 1})
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'page_not_found'
