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


def _login_tokens(client, db, make_user, email='me@example.com', pw='Haslo123!'):
    u = make_user(email=email)
    u.set_password(pw); u.email_verified = True; u.is_active = True
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login', json={'email': email, 'password': pw})
    return r.get_json()['data'], u


def test_me_requires_token(client):
    r = client.get('/api/mobile/v1/auth/me')
    assert r.status_code == 401


def test_me_returns_user(client, db, make_user):
    tokens, u = _login_tokens(client, db, make_user)
    r = client.get('/api/mobile/v1/auth/me',
                   headers={'Authorization': f'Bearer {tokens["access_token"]}'})
    assert r.status_code == 200
    assert r.get_json()['data']['user']['email'] == 'me@example.com'


def test_refresh_issues_new_access(client, db, make_user):
    tokens, u = _login_tokens(client, db, make_user, email='ref@example.com')
    r = client.post('/api/mobile/v1/auth/refresh',
                    headers={'Authorization': f'Bearer {tokens["refresh_token"]}'})
    assert r.status_code == 200
    assert 'access_token' in r.get_json()['data']


def test_logout_revokes_refresh(client, db, make_user):
    tokens, u = _login_tokens(client, db, make_user, email='out@example.com')
    # logout używa refresh tokenu
    r = client.post('/api/mobile/v1/auth/logout',
                    headers={'Authorization': f'Bearer {tokens["refresh_token"]}'})
    assert r.status_code == 200
    # ponowny refresh tym samym tokenem ma być odrzucony
    r2 = client.post('/api/mobile/v1/auth/refresh',
                     headers={'Authorization': f'Bearer {tokens["refresh_token"]}'})
    assert r2.status_code == 401


def test_register_creates_unverified_user(client, db, monkeypatch):
    sent = {}
    import utils.email_manager as em
    monkeypatch.setattr(em.EmailManager, 'send_verification_code',
                        staticmethod(lambda user, code: sent.update(code=code) or True))

    r = client.post('/api/mobile/v1/auth/register', json={
        'email': 'new@example.com', 'password': 'Haslo123!',
        'first_name': 'Jan', 'last_name': 'Kowalski', 'phone': '+48500500500',
    })
    assert r.status_code == 201
    assert r.get_json()['data']['email'] == 'new@example.com'

    from modules.auth.models import User
    u = User.query.filter_by(email='new@example.com').first()
    assert u is not None and u.email_verified is False
    assert sent.get('code')  # kod został "wysłany"


def test_register_duplicate_email(client, db, make_user, monkeypatch):
    import utils.email_manager as em
    monkeypatch.setattr(em.EmailManager, 'send_verification_code',
                        staticmethod(lambda user, code: True))
    make_user(email='dup@example.com')
    r = client.post('/api/mobile/v1/auth/register', json={
        'email': 'dup@example.com', 'password': 'Haslo123!',
        'first_name': 'A', 'last_name': 'B', 'phone': '+48500',
    })
    assert r.status_code == 409
    assert r.get_json()['error']['code'] == 'email_taken'


def test_verify_email_success(client, db, make_user):
    u = make_user(email='ver@example.com')
    u.set_password('Haslo123!'); u.email_verified = False
    db.session.commit()
    code, _ = u.generate_verification_code()
    db.session.commit()

    r = client.post('/api/mobile/v1/auth/verify-email',
                    json={'email': 'ver@example.com', 'code': code})
    assert r.status_code == 200
    data = r.get_json()['data']
    assert 'access_token' in data and 'refresh_token' in data
    db.session.refresh(u)
    assert u.email_verified is True


def test_verify_email_wrong_code(client, db, make_user):
    u = make_user(email='verbad@example.com')
    u.email_verified = False
    db.session.commit()
    u.generate_verification_code()
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/verify-email',
                    json={'email': 'verbad@example.com', 'code': '000000'})
    assert r.status_code == 400
    assert r.get_json()['error']['code'] in ('invalid_code', 'code_expired')


def test_verify_email_locked_with_expired_code_reports_invalid_code(client, db, make_user):
    from datetime import timedelta
    from modules.orders.models import get_local_now
    u = make_user(email='lock@example.com')
    u.email_verified = False
    db.session.commit()
    u.generate_verification_code()
    # symuluj lockout + wygasły kod
    u.email_verification_locked_until = get_local_now() + timedelta(minutes=15)
    u.email_verification_code_expires = get_local_now() - timedelta(minutes=1)
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/verify-email',
                    json={'email': 'lock@example.com', 'code': '123456'})
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'invalid_code'
