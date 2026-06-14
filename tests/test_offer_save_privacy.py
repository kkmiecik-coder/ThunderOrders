"""
Tests for privacy/visibility save in offers_save endpoint.
Task 9: Panel prywatności w pagebuilderze.
"""


def _page(db, admin_id):
    from modules.offers.models import OfferPage
    p = OfferPage(name='P', token=OfferPage.generate_token(), status='draft', created_by=admin_id)
    db.session.add(p)
    db.session.commit()
    return p


def _admin(make_user):
    return make_user(role='admin', email='admin@example.com', profile_completed=True)


def test_save_sets_private_and_audience(db, client, make_user, login):
    from modules.auth.models import UserGroup
    admin = _admin(make_user)
    login(admin)
    p = _page(db, admin.id)
    u = make_user(email='member@example.com')
    g = UserGroup(name='G')
    db.session.add(g)
    db.session.commit()

    resp = client.post(f'/admin/offers/{p.id}/save', json={
        'is_private': True,
        'group_ids': [g.id],
        'user_ids': [u.id],
    })
    assert resp.status_code == 200
    db.session.refresh(p)
    assert p.is_private is True
    assert g in p.allowed_groups
    assert u in p.allowed_users


def test_save_public_clears_flag(db, client, make_user, login):
    admin = _admin(make_user)
    login(admin)
    p = _page(db, admin.id)
    p.is_private = True
    db.session.commit()
    resp = client.post(f'/admin/offers/{p.id}/save', json={'is_private': False})
    assert resp.status_code == 200
    db.session.refresh(p)
    assert p.is_private is False


def test_save_replaces_audience(db, client, make_user, login):
    from modules.auth.models import UserGroup
    admin = _admin(make_user)
    login(admin)
    p = _page(db, admin.id)
    u1 = make_user(email='u1@example.com')
    u2 = make_user(email='u2@example.com')
    p.allowed_users.append(u1)
    db.session.commit()
    resp = client.post(f'/admin/offers/{p.id}/save', json={'is_private': True, 'user_ids': [u2.id]})
    assert resp.status_code == 200
    db.session.refresh(p)
    assert u2 in p.allowed_users and u1 not in p.allowed_users
