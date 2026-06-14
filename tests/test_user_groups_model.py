def test_user_group_membership(db, make_user):
    from modules.auth.models import UserGroup
    u1 = make_user(email='a@example.com')
    u2 = make_user(email='b@example.com')
    g = UserGroup(name='VIP')
    g.members.append(u1)
    g.members.append(u2)
    db.session.add(g)
    db.session.commit()

    assert g.id is not None
    assert g.member_count == 2
    assert u1 in g.members
