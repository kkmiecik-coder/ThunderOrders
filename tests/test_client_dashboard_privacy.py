"""Testy prywatności stron sprzedaży na webowym dashboardzie klienta.

Regresja: prywatne strony wyciekały do widgetu stron sprzedaży na
`/client/dashboard` oraz do API paginacji `/client/api/offer-pages`,
mimo że bramka chroniła same strony (token routes) i Mobile API.
"""


def _make_page(db, status='active', is_private=False, created_by=1):
    from modules.offers.models import OfferPage
    p = OfferPage(
        name=f'Drop {status} priv={is_private}',
        token=OfferPage.generate_token(),
        status=status,
        page_type='exclusive',
        payment_stages=4,
        created_by=created_by,
        is_private=is_private,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _add_audience_user(db, page, user):
    from modules.offers.models import offer_page_users
    db.session.execute(
        offer_page_users.insert().values(offer_page_id=page.id, user_id=user.id)
    )
    db.session.commit()


def _add_audience_via_group(db, page, user):
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


def _page_ids(resp):
    return {p['id'] for p in resp.get_json()['pages']}


# ---------------------------------------------------------------------------
# /client/api/offer-pages
# ---------------------------------------------------------------------------

def test_api_outsider_does_not_see_private_page(db, client, make_user, login):
    outsider = make_user(email='outsider@example.com', profile_completed=True)
    login(outsider)
    public = _make_page(db, 'active', is_private=False)
    private = _make_page(db, 'active', is_private=True)
    resp = client.get('/client/api/offer-pages?filter=live')
    assert resp.status_code == 200
    ids = _page_ids(resp)
    assert public.id in ids
    assert private.id not in ids


def test_api_audience_user_sees_private_page(db, client, make_user, login):
    member = make_user(email='member@example.com', profile_completed=True)
    login(member)
    private = _make_page(db, 'active', is_private=True)
    _add_audience_user(db, private, member)
    resp = client.get('/client/api/offer-pages?filter=live')
    assert private.id in _page_ids(resp)


def test_api_group_member_sees_private_page(db, client, make_user, login):
    member = make_user(email='gmember@example.com', profile_completed=True)
    login(member)
    private = _make_page(db, 'active', is_private=True)
    _add_audience_via_group(db, private, member)
    resp = client.get('/client/api/offer-pages?filter=live')
    assert private.id in _page_ids(resp)


def test_api_admin_sees_all_private_pages(db, client, make_user, login):
    admin = make_user(role='admin', email='admin@example.com', profile_completed=True)
    login(admin)
    private = _make_page(db, 'active', is_private=True)
    resp = client.get('/client/api/offer-pages?filter=live')
    assert private.id in _page_ids(resp)


# ---------------------------------------------------------------------------
# /client/api/offers/<id>/matrix
# ---------------------------------------------------------------------------

def test_matrix_outsider_blocked_for_private_page(db, client, make_user, login):
    outsider = make_user(email='mout@example.com', profile_completed=True)
    login(outsider)
    private = _make_page(db, 'active', is_private=True)
    resp = client.get(f'/client/api/offers/{private.id}/matrix')
    assert resp.status_code == 404


def test_matrix_audience_allowed_for_private_page(db, client, make_user, login):
    member = make_user(email='min@example.com', profile_completed=True)
    login(member)
    private = _make_page(db, 'active', is_private=True)
    _add_audience_user(db, private, member)
    resp = client.get(f'/client/api/offers/{private.id}/matrix')
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /client/dashboard  (flagi widoczności widgetu)
# ---------------------------------------------------------------------------

def test_dashboard_outsider_no_private_only_widget(db, client, make_user, login):
    """Gdy jedyna 'live' strona jest prywatna i niedostępna — widget pusty."""
    outsider = make_user(email='out2@example.com', profile_completed=True)
    login(outsider)
    _make_page(db, 'active', is_private=True)
    resp = client.get('/client/dashboard')
    assert resp.status_code == 200
    # has_current/has_any nie powinny być wywołane samą prywatną stroną.
    # Sprawdzamy przez API, że nie ma żadnej widocznej strony live.
    api = client.get('/client/api/offer-pages?filter=live')
    assert _page_ids(api) == set()
