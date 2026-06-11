def test_blocklist_contains(db, make_user):
    from modules.api_mobile.models import MobileTokenBlocklist
    from modules.orders.models import get_local_now
    from datetime import timedelta

    u = make_user()
    assert MobileTokenBlocklist.contains('abc') is False
    db.session.add(MobileTokenBlocklist(
        jti='abc', token_type='refresh', user_id=u.id,
        expires_at=get_local_now() + timedelta(days=1),
    ))
    db.session.commit()
    assert MobileTokenBlocklist.contains('abc') is True
