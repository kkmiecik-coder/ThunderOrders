"""Testy endpointów wyszukiwania użytkowników i grup (Task 6)."""
import pytest


def test_user_search(db, client, make_user, login):
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    make_user(email='kasia.nowak@example.com', first_name='Kasia', last_name='Nowak')
    resp = client.get('/admin/users/api/search?q=kasia')
    assert resp.status_code == 200
    data = resp.get_json()
    assert any('kasia' in u['email'] for u in data)


def test_user_search_too_short(db, client, make_user, login):
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    resp = client.get('/admin/users/api/search?q=k')
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_group_search(db, client, make_user, login):
    from modules.auth.models import UserGroup
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    db.session.add(UserGroup(name='Hurtownicy'))
    db.session.commit()
    resp = client.get('/admin/user-groups/api/search?q=hurt')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data[0]['name'] == 'Hurtownicy'
    assert 'member_count' in data[0]


def test_search_requires_admin(db, client, make_user, login):
    login(make_user(role='client', email='client@example.com'))
    resp = client.get('/admin/users/api/search?q=kasia')
    assert resp.status_code in (302, 403)
