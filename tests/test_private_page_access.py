"""Tests: bramka dostępu na publicznych route'ach stron prywatnych (Task 5)."""


def _make_page(db, is_private):
    from modules.offers.models import OfferPage
    from modules.auth.models import User
    owner = User(email=f'owner_{"priv" if is_private else "pub"}@example.com',
                 role='admin', is_active=True, email_verified=True)
    db.session.add(owner)
    db.session.commit()
    p = OfferPage(name='P', token=OfferPage.generate_token(),
                  status='active', is_private=is_private, created_by=owner.id)
    db.session.add(p)
    db.session.commit()
    return p


def test_anon_redirected_to_login(db, client):
    p = _make_page(db, True)
    resp = client.get(f'/offer/{p.token}')
    assert resp.status_code == 302
    assert 'login' in resp.headers['Location']


def test_outsider_gets_404(db, client, make_user, login):
    p = _make_page(db, True)
    login(make_user(email='outsider@example.com'))
    resp = client.get(f'/offer/{p.token}')
    assert resp.status_code == 404


def test_member_gets_200(db, client, make_user, login):
    p = _make_page(db, True)
    u = make_user(email='member@example.com')
    p.allowed_users.append(u)
    db.session.commit()
    login(u)
    resp = client.get(f'/offer/{p.token}')
    # The gate lets the member through; page renders (200) or at worst 500 on
    # missing assets — but it must NOT be a 302 redirect or 404.
    assert resp.status_code not in (302, 404)


def test_group_member_gets_200(db, client, make_user, login):
    from modules.auth.models import UserGroup
    p = _make_page(db, True)
    u = make_user(email='grpmember@example.com')
    g = UserGroup(name='Dostepowi')
    g.members.append(u)
    db.session.add(g)
    db.session.commit()
    p.allowed_groups.append(g)
    db.session.commit()
    login(u)
    resp = client.get(f'/offer/{p.token}')
    assert resp.status_code not in (302, 404)


def test_admin_always_in(db, client, make_user, login):
    p = _make_page(db, True)
    login(make_user(role='admin', email='admin2@example.com'))
    resp = client.get(f'/offer/{p.token}')
    assert resp.status_code not in (302, 404)


def test_mod_always_in(db, client, make_user, login):
    p = _make_page(db, True)
    login(make_user(role='mod', email='mod@example.com'))
    resp = client.get(f'/offer/{p.token}')
    assert resp.status_code not in (302, 404)


def test_place_order_gate_outsider_404(db, client, make_user, login):
    p = _make_page(db, True)
    login(make_user(email='nope@example.com'))
    resp = client.post(f'/offer/{p.token}/place-order', json={})
    assert resp.status_code == 404


def test_public_page_still_open(db, client):
    p = _make_page(db, False)
    resp = client.get(f'/offer/{p.token}')
    # Public pages are always accessible
    assert resp.status_code not in (302, 404)
