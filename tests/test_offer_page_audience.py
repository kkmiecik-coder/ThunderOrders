def _page(db):
    from modules.offers.models import OfferPage
    from modules.auth.models import User
    admin = User(email='owner@example.com', role='admin', is_active=True, email_verified=True)
    db.session.add(admin)
    db.session.commit()
    p = OfferPage(name='Test', token=OfferPage.generate_token(), status='active', created_by=admin.id)
    db.session.add(p)
    db.session.commit()
    return p


def test_page_is_private_default(db):
    p = _page(db)
    assert p.is_private is False


def test_page_allowed_users_and_groups(db, make_user):
    from modules.auth.models import UserGroup
    p = _page(db)
    u = make_user(email='member@example.com')
    g = UserGroup(name='Grupa A')
    g.members.append(u)
    db.session.add(g)
    db.session.commit()

    solo = make_user(email='solo@example.com')
    p.is_private = True
    p.allowed_users.append(solo)
    p.allowed_groups.append(g)
    db.session.commit()

    assert p.is_private is True
    assert len(p.allowed_users) == 1
    assert g in p.allowed_groups
