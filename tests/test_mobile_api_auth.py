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


def test_health(client):
    r = client.get('/api/mobile/v1/health')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['data']['status'] == 'ok'


def test_app_version(client):
    r = client.get('/api/mobile/v1/app-version')
    assert r.status_code == 200
    data = r.get_json()['data']
    assert 'min_version' in data and 'latest_version' in data


def _make_verified_user_with_password(db, make_user, email='log@example.com', pw='Haslo123!'):
    u = make_user(email=email)
    u.set_password(pw)
    u.email_verified = True
    u.is_active = True
    db.session.commit()
    return u


def test_login_success(client, db, make_user):
    _make_verified_user_with_password(db, make_user)
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': 'log@example.com', 'password': 'Haslo123!'})
    assert r.status_code == 200
    data = r.get_json()['data']
    assert 'access_token' in data and 'refresh_token' in data
    assert data['user']['email'] == 'log@example.com'


def test_login_wrong_password(client, db, make_user):
    _make_verified_user_with_password(db, make_user)
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': 'log@example.com', 'password': 'zle'})
    assert r.status_code == 401
    assert r.get_json()['success'] is False
    assert r.get_json()['error']['code'] == 'invalid_credentials'
