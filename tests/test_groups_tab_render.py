"""Task 8: Test renderowania zakładki Grupy w panelu użytkowników."""


def test_groups_tab_present(db, client, make_user, login):
    from modules.auth.models import UserGroup
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    db.session.add(UserGroup(name='WidocznaGrupa'))
    db.session.commit()
    resp = client.get('/admin/clients')
    assert resp.status_code == 200
    assert b'data-tab="groups"' in resp.data
    assert 'WidocznaGrupa'.encode() in resp.data
