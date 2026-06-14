"""Testy CRUD grup użytkowników (Task 7)."""
import pytest


def _admin(make_user):
    return make_user(role='admin', email='admin@example.com', profile_completed=True)


def test_create_group(db, client, make_user, login):
    login(_admin(make_user))
    m1 = make_user(email='m1@example.com')
    resp = client.post('/admin/user-groups/create', json={'name': 'Nowa', 'member_ids': [m1.id]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['group']['name'] == 'Nowa'
    assert data['group']['member_count'] == 1


def test_create_requires_name(db, client, make_user, login):
    login(_admin(make_user))
    resp = client.post('/admin/user-groups/create', json={'name': '', 'member_ids': []})
    assert resp.status_code == 400


def test_create_duplicate_name_fails(db, client, make_user, login):
    from modules.auth.models import UserGroup
    login(_admin(make_user))
    db.session.add(UserGroup(name='Dup')); db.session.commit()
    resp = client.post('/admin/user-groups/create', json={'name': 'Dup', 'member_ids': []})
    assert resp.status_code == 400


def test_create_name_too_long(db, client, make_user, login):
    login(_admin(make_user))
    resp = client.post('/admin/user-groups/create', json={'name': 'x' * 101, 'member_ids': []})
    assert resp.status_code == 400


def test_crud_requires_admin(db, client, make_user, login):
    login(make_user(role='client', email='client@example.com', profile_completed=True))
    resp = client.post('/admin/user-groups/create', json={'name': 'X', 'member_ids': []})
    assert resp.status_code == 403


def test_update_group_members(db, client, make_user, login):
    from modules.auth.models import UserGroup
    login(_admin(make_user))
    g = UserGroup(name='Edit'); db.session.add(g); db.session.commit()
    m1 = make_user(email='x@example.com')
    resp = client.post(f'/admin/user-groups/{g.id}/update', json={'name': 'Edit2', 'member_ids': [m1.id]})
    assert resp.status_code == 200
    db.session.refresh(g)
    assert g.name == 'Edit2'
    assert g.member_count == 1


def test_delete_group_keeps_users(db, client, make_user, login):
    from modules.auth.models import UserGroup, User
    login(_admin(make_user))
    m1 = make_user(email='keep@example.com')
    g = UserGroup(name='Del'); g.members.append(m1); db.session.add(g); db.session.commit()
    gid = g.id
    resp = client.post(f'/admin/user-groups/{gid}/delete')
    assert resp.status_code == 200
    assert UserGroup.query.get(gid) is None
    assert User.query.filter_by(email='keep@example.com').first() is not None
