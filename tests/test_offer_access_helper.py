"""Tests for modules/offers/access.py — user_is_in_page_audience helper."""


def _page(db, private=False):
    from modules.offers.models import OfferPage
    from modules.auth.models import User
    owner = User(email='owner@example.com', role='admin', is_active=True, email_verified=True)
    db.session.add(owner)
    db.session.commit()
    p = OfferPage(name='T', token=OfferPage.generate_token(), status='active', is_private=private, created_by=owner.id)
    db.session.add(p)
    db.session.commit()
    return p


def test_audience_direct_user(db, make_user):
    from modules.offers.access import user_is_in_page_audience
    p = _page(db, private=True)
    u = make_user(email='solo@example.com')
    p.allowed_users.append(u)
    db.session.commit()
    assert user_is_in_page_audience(p, u) is True


def test_audience_via_group(db, make_user):
    from modules.offers.access import user_is_in_page_audience
    from modules.auth.models import UserGroup
    p = _page(db, private=True)
    u = make_user(email='g@example.com')
    g = UserGroup(name='G1')
    g.members.append(u)
    db.session.add(g)
    db.session.commit()
    p.allowed_groups.append(g)
    db.session.commit()
    assert user_is_in_page_audience(p, u) is True


def test_audience_outsider(db, make_user):
    from modules.offers.access import user_is_in_page_audience
    p = _page(db, private=True)
    outsider = make_user(email='out@example.com')
    assert user_is_in_page_audience(p, outsider) is False
