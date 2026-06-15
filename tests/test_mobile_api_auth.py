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


def test_google_login_new_user(client, db, monkeypatch):
    import modules.api_mobile.auth_routes as ar
    monkeypatch.setattr(ar, 'verify_google_id_token', lambda t: {
        'email': 'gphone@example.com', 'sub': 'google-uid-1',
        'given_name': 'Goo', 'family_name': 'Gle', 'email_verified': True,
    })
    r = client.post('/api/mobile/v1/auth/google', json={'id_token': 'fake'})
    assert r.status_code == 200
    data = r.get_json()['data']
    assert 'access_token' in data and data['user']['email'] == 'gphone@example.com'

    from modules.auth.models import User
    u = User.query.filter_by(email='gphone@example.com').first()
    assert u is not None and u.google_id == 'google-uid-1' and u.email_verified is True


def test_google_login_invalid_token(client, db, monkeypatch):
    import modules.api_mobile.auth_routes as ar
    monkeypatch.setattr(ar, 'verify_google_id_token', lambda t: None)
    r = client.post('/api/mobile/v1/auth/google', json={'id_token': 'bad'})
    assert r.status_code == 401
    assert r.get_json()['error']['code'] == 'invalid_google_token'


def test_resend_code_sends_new_code_for_unverified(client, db, make_user, monkeypatch):
    sent = []
    import utils.email_manager as em
    monkeypatch.setattr(em.EmailManager, 'send_verification_code',
                        staticmethod(lambda user, code: sent.append(code) or True))
    u = make_user(email='rs@example.com')
    u.email_verified = False
    db.session.commit()

    r = client.post('/api/mobile/v1/auth/resend-code', json={'email': 'rs@example.com'})
    assert r.status_code == 200
    assert len(sent) == 1  # nowy kod został "wysłany"

    # cooldown 60s: natychmiastowa druga prośba zwraca 200, ale nie wysyła nowego kodu
    r2 = client.post('/api/mobile/v1/auth/resend-code', json={'email': 'rs@example.com'})
    assert r2.status_code == 200
    assert len(sent) == 1


def test_resend_code_no_leak_for_unknown_or_verified(client, db, make_user, monkeypatch):
    sent = []
    import utils.email_manager as em
    monkeypatch.setattr(em.EmailManager, 'send_verification_code',
                        staticmethod(lambda user, code: sent.append(code) or True))
    make_user(email='done@example.com')  # email_verified=True z fixtury

    r1 = client.post('/api/mobile/v1/auth/resend-code', json={'email': 'ghost@example.com'})
    r2 = client.post('/api/mobile/v1/auth/resend-code', json={'email': 'done@example.com'})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.get_json() == r2.get_json()  # identyczna odpowiedź — brak wycieku istnienia konta
    assert sent == []


def test_google_verifier_fail_closed_without_allowlist(app, monkeypatch):
    # Pusta GOOGLE_OAUTH_CLIENT_IDS => odrzucamy BEZ wołania Google (fail-closed)
    import modules.api_mobile.google_auth as ga
    called = []
    monkeypatch.setattr(ga.google_id_token, 'verify_oauth2_token',
                        lambda *a, **k: called.append(1) or {})
    app.config['GOOGLE_OAUTH_CLIENT_IDS'] = []  # jawny warunek, niezależny od .env
    with app.test_request_context():
        assert ga.verify_google_id_token('whatever') is None
    assert called == []  # weryfikator (sieć) nie został dotknięty


def test_google_verifier_handles_google_auth_error(app, monkeypatch):
    # Awaria pobierania certów Google (TransportError) => None (401), nie wyjątek/500
    import modules.api_mobile.google_auth as ga
    from google.auth.exceptions import TransportError

    def boom(*a, **k):
        raise TransportError('cert fetch failed')

    monkeypatch.setattr(ga.google_id_token, 'verify_oauth2_token', boom)
    app.config['GOOGLE_OAUTH_CLIENT_IDS'] = ['client-1']
    with app.test_request_context():
        assert ga.verify_google_id_token('tok') is None


def test_register_duplicate_race_returns_409(client, db, monkeypatch):
    # Symulacja wyścigu: pre-check duplikatu przechodzi, ale INSERT łamie unique(email)
    from sqlalchemy.exc import IntegrityError
    import utils.email_manager as em
    monkeypatch.setattr(em.EmailManager, 'send_verification_code',
                        staticmethod(lambda user, code: True))
    real_commit = db.session.commit
    state = {'raised': False}

    def racing_commit():
        if not state['raised']:
            state['raised'] = True
            raise IntegrityError('INSERT INTO users', {}, Exception('Duplicate entry'))
        return real_commit()

    monkeypatch.setattr(db.session, 'commit', racing_commit)
    r = client.post('/api/mobile/v1/auth/register', json={
        'email': 'race@example.com', 'password': 'Haslo123!',
        'first_name': 'A', 'last_name': 'B', 'phone': '+48500',
    })
    assert r.status_code == 409
    assert r.get_json()['error']['code'] == 'email_taken'


def test_logout_race_is_idempotent(client, db, make_user, monkeypatch):
    # Symulacja wyścigu podwójnego logout: INSERT do blocklisty łamie unique(jti)
    from sqlalchemy.exc import IntegrityError
    tokens, u = _login_tokens(client, db, make_user, email='race-out@example.com')
    real_commit = db.session.commit
    state = {'raised': False}

    def racing_commit():
        if not state['raised']:
            state['raised'] = True
            raise IntegrityError('INSERT INTO mobile_token_blocklist', {},
                                 Exception('Duplicate entry'))
        return real_commit()

    monkeypatch.setattr(db.session, 'commit', racing_commit)
    r = client.post('/api/mobile/v1/auth/logout',
                    headers={'Authorization': f'Bearer {tokens["refresh_token"]}'})
    assert r.status_code == 200


def test_refresh_rejected_after_deactivation(client, db, make_user):
    tokens, u = _login_tokens(client, db, make_user, email='deact@example.com')
    u.is_active = False
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/refresh',
                    headers={'Authorization': f'Bearer {tokens["refresh_token"]}'})
    assert r.status_code == 403
    assert r.get_json()['error']['code'] == 'account_inactive'


def test_refresh_rejected_after_password_change(client, db, make_user):
    tokens, u = _login_tokens(client, db, make_user, email='pwchange@example.com')
    u.set_password('NoweHaslo456!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/refresh',
                    headers={'Authorization': f'Bearer {tokens["refresh_token"]}'})
    assert r.status_code == 401
    assert r.get_json()['error']['code'] == 'token_revoked'


def test_me_rejected_after_deactivation(client, db, make_user):
    tokens, u = _login_tokens(client, db, make_user, email='deact-me@example.com')
    u.is_active = False
    db.session.commit()
    r = client.get('/api/mobile/v1/auth/me',
                   headers={'Authorization': f'Bearer {tokens["access_token"]}'})
    assert r.status_code == 403
    assert r.get_json()['error']['code'] == 'account_inactive'


def test_verify_email_inactive_account_gets_no_tokens(client, db, make_user):
    u = make_user(email='inactive-ver@example.com')
    u.email_verified = False
    u.is_active = False
    db.session.commit()
    code, _ = u.generate_verification_code()
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/verify-email',
                    json={'email': 'inactive-ver@example.com', 'code': code})
    assert r.status_code == 403
    assert r.get_json()['error']['code'] == 'account_inactive'
    assert 'access_token' not in (r.get_json().get('data') or {})


def test_jwt_errors_use_api_envelope(client, db, make_user):
    # Brak tokenu
    r = client.get('/api/mobile/v1/auth/me')
    assert r.status_code == 401
    body = r.get_json()
    assert body['success'] is False and body['error']['code'] == 'authorization_required'

    # Zły typ tokenu (access na trasie refresh) — 422 w kopercie
    tokens, u = _login_tokens(client, db, make_user, email='env@example.com')
    r2 = client.post('/api/mobile/v1/auth/refresh',
                     headers={'Authorization': f'Bearer {tokens["access_token"]}'})
    assert r2.status_code == 422
    assert r2.get_json()['error']['code'] == 'invalid_token'

    # Unieważniony refresh (po logout) — 401 token_revoked
    client.post('/api/mobile/v1/auth/logout',
                headers={'Authorization': f'Bearer {tokens["refresh_token"]}'})
    r3 = client.post('/api/mobile/v1/auth/refresh',
                     headers={'Authorization': f'Bearer {tokens["refresh_token"]}'})
    assert r3.status_code == 401
    assert r3.get_json()['error']['code'] == 'token_revoked'


def test_jwt_expired_token_envelope(client, db, make_user, app):
    from datetime import timedelta
    from flask_jwt_extended import create_access_token
    u = make_user(email='exp@example.com')
    with app.test_request_context():
        expired = create_access_token(identity=str(u.id),
                                      expires_delta=timedelta(seconds=-1))
    r = client.get('/api/mobile/v1/auth/me',
                   headers={'Authorization': f'Bearer {expired}'})
    assert r.status_code == 401
    assert r.get_json()['error']['code'] == 'token_expired'


def test_maintenance_mode_mobile_api(client, db, app):
    from modules.auth.models import Settings
    Settings.set_value('maintenance_mode', True, type='boolean')
    app.maintenance_cache = {'enabled': False, 'checked_at': 0}  # wymuś świeży odczyt z DB

    # health i app-version działają mimo maintenance (apka wykrywa stan serwera)
    assert client.get('/api/mobile/v1/health').status_code == 200
    assert client.get('/api/mobile/v1/app-version').status_code == 200

    # reszta API mobilnego dostaje JSON 503 w kopercie kontraktu (nie HTML)
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': 'x@y.pl', 'password': 'x'})
    assert r.status_code == 503
    body = r.get_json()
    assert body['success'] is False
    assert body['error']['code'] == 'maintenance'


def test_register_rejects_invalid_email_format(client, db, monkeypatch):
    import utils.email_manager as em
    monkeypatch.setattr(em.EmailManager, 'send_verification_code',
                        staticmethod(lambda user, code: True))
    r = client.post('/api/mobile/v1/auth/register', json={
        'email': 'notanemail', 'password': 'Haslo123!',
        'first_name': 'A', 'last_name': 'B', 'phone': '+48500',
    })
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'invalid_email'
    from modules.auth.models import User
    assert User.query.filter_by(email='notanemail').first() is None


def test_register_rejects_overlong_fields(client, db, monkeypatch):
    import utils.email_manager as em
    monkeypatch.setattr(em.EmailManager, 'send_verification_code',
                        staticmethod(lambda user, code: True))
    r = client.post('/api/mobile/v1/auth/register', json={
        'email': 'long@example.com', 'password': 'Haslo123!',
        'first_name': 'A' * 101, 'last_name': 'B', 'phone': '+48500',
    })
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'invalid_input'


def test_register_smtp_failure_is_honest_and_allows_instant_resend(client, db, monkeypatch):
    import utils.email_manager as em
    sent = []
    state = {'fail': True}

    def fake_send(user, code):
        if state['fail']:
            return False
        sent.append(code)
        return True

    monkeypatch.setattr(em.EmailManager, 'send_verification_code', staticmethod(fake_send))
    r = client.post('/api/mobile/v1/auth/register', json={
        'email': 'smtp@example.com', 'password': 'Haslo123!',
        'first_name': 'A', 'last_name': 'B', 'phone': '+48500',
    })
    assert r.status_code == 201
    assert r.get_json()['data']['email_sent'] is False  # uczciwa informacja zamiast ślepego 201

    # nieudana wysyłka nie blokuje natychmiastowego resend (cooldown wyczyszczony)
    state['fail'] = False
    r2 = client.post('/api/mobile/v1/auth/resend-code', json={'email': 'smtp@example.com'})
    assert r2.status_code == 200
    assert len(sent) == 1


def test_serialize_user_returns_absolute_avatar_url(app):
    from types import SimpleNamespace
    from modules.api_mobile.helpers import serialize_user
    stub = SimpleNamespace(id=1, email='a@b.pl', first_name='A', last_name='B',
                           phone=None, role='client', email_verified=True,
                           avatar_url='/static/uploads/avatars/default/x.png')
    with app.test_request_context():
        data = serialize_user(stub)
    assert data['avatar_url'] == 'http://localhost/static/uploads/avatars/default/x.png'

    stub.avatar_url = None
    with app.test_request_context():
        assert serialize_user(stub)['avatar_url'] is None


def test_rate_limit_returns_envelope_for_mobile_api(app, db):
    from extensions import limiter
    app.config['RATELIMIT_ENABLED'] = True
    limiter.init_app(app)  # re-init z włączonymi limitami (domyślnie off w testach)
    c = app.test_client()
    last = None
    for _ in range(16):  # limit loginu: 15/min
        last = c.post('/api/mobile/v1/auth/login',
                      json={'email': 'x@y.pl', 'password': 'x'})
    assert last.status_code == 429
    assert last.get_json()['error']['code'] == 'rate_limited'


def test_logout_stores_expiry_in_local_time_and_purges_expired(client, db, make_user):
    from datetime import timedelta
    from modules.api_mobile.models import MobileTokenBlocklist
    from modules.orders.models import get_local_now

    # wpis dawno wygasły — powinien zostać sprzątnięty przy logout (lazy cleanup)
    db.session.add(MobileTokenBlocklist(
        jti='stale-jti', token_type='refresh', user_id=None,
        expires_at=get_local_now() - timedelta(hours=2),
    ))
    db.session.commit()

    tokens, u = _login_tokens(client, db, make_user, email='tz@example.com')
    r = client.post('/api/mobile/v1/auth/logout',
                    headers={'Authorization': f'Bearer {tokens["refresh_token"]}'})
    assert r.status_code == 200

    assert MobileTokenBlocklist.contains('stale-jti') is False  # sprzątnięte
    entry = MobileTokenBlocklist.query.one()
    # expires_at w czasie lokalnym PL (spójnie z created_at): ~30 dni od teraz
    delta = entry.expires_at - get_local_now()
    assert timedelta(days=29, hours=23) < delta < timedelta(days=30, hours=1)


def test_mobile_404_returns_envelope(client):
    r = client.get('/api/mobile/v1/nope')
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'not_found'


def test_mobile_500_returns_envelope(app, db):
    app.config['PROPAGATE_EXCEPTIONS'] = False
    app.testing = False

    @app.route('/api/mobile/v1/_boom')
    def _boom():
        raise RuntimeError('boom')

    c = app.test_client()
    r = c.get('/api/mobile/v1/_boom')
    assert r.status_code == 500
    assert r.get_json()['error']['code'] == 'server_error'


# ============================================
# Password reset (forgot-password / reset-password)
# ============================================

def _patch_reset_email(monkeypatch):
    """Przechwytuje kod resetu zamiast wysyłać e-mail. Zwraca listę wysłanych kodów."""
    sent = []
    import utils.email_manager as em
    monkeypatch.setattr(em.EmailManager, 'send_password_reset_code',
                        staticmethod(lambda user, code: sent.append(code) or True))
    return sent


def _request_reset_code(client, db, make_user, monkeypatch, email='reset@example.com',
                        pw='StareHaslo123'):
    """Tworzy zweryfikowanego usera i pobiera świeży kod resetu przez forgot-password."""
    sent = _patch_reset_email(monkeypatch)
    u = make_user(email=email)
    u.set_password(pw)
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/forgot-password', json={'email': email})
    assert r.status_code == 200
    assert len(sent) == 1
    return u, sent[0]


def test_forgot_password_sends_code_for_existing_user(client, db, make_user, monkeypatch):
    sent = _patch_reset_email(monkeypatch)
    u = make_user(email='fp@example.com')

    r = client.post('/api/mobile/v1/auth/forgot-password', json={'email': 'fp@example.com'})
    assert r.status_code == 200
    body = r.get_json()
    assert body == {'success': True, 'data': {}}
    assert len(sent) == 1 and len(sent[0]) == 6
    db.session.refresh(u)
    assert u.password_reset_code == sent[0]


def test_forgot_password_no_leak_for_unknown_email(client, db, make_user, monkeypatch):
    sent = _patch_reset_email(monkeypatch)
    make_user(email='known@example.com')

    r_known = client.post('/api/mobile/v1/auth/forgot-password', json={'email': 'known@example.com'})
    r_ghost = client.post('/api/mobile/v1/auth/forgot-password', json={'email': 'ghost@example.com'})
    assert r_known.status_code == 200 and r_ghost.status_code == 200
    assert r_known.get_json() == r_ghost.get_json() == {'success': True, 'data': {}}
    assert len(sent) == 1  # tylko dla istniejącego konta


def test_forgot_password_inactive_user_gets_no_code(client, db, make_user, monkeypatch):
    sent = _patch_reset_email(monkeypatch)
    u = make_user(email='inactive@example.com')
    u.is_active = False
    db.session.commit()

    r = client.post('/api/mobile/v1/auth/forgot-password', json={'email': 'inactive@example.com'})
    assert r.status_code == 200 and r.get_json() == {'success': True, 'data': {}}
    assert sent == []


def test_forgot_password_resend_respects_cooldown(client, db, make_user, monkeypatch):
    sent = _patch_reset_email(monkeypatch)
    make_user(email='cool@example.com')

    r1 = client.post('/api/mobile/v1/auth/forgot-password', json={'email': 'cool@example.com'})
    r2 = client.post('/api/mobile/v1/auth/forgot-password', json={'email': 'cool@example.com'})
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(sent) == 1  # cooldown 60s: druga prośba nie wysyła nowego kodu


def test_reset_password_success(client, db, make_user, monkeypatch):
    u, code = _request_reset_code(client, db, make_user, monkeypatch)

    r = client.post('/api/mobile/v1/auth/reset-password',
                    json={'email': 'reset@example.com', 'code': code,
                          'new_password': 'NoweHaslo123'})
    assert r.status_code == 200
    assert r.get_json() == {'success': True, 'data': {}}

    db.session.refresh(u)
    assert u.check_password('NoweHaslo123')          # hasło ustawione
    assert not u.check_password('StareHaslo123')
    assert u.password_reset_code is None              # kod jednorazowy — unieważniony

    # logowanie nowym hasłem działa
    login = client.post('/api/mobile/v1/auth/login',
                        json={'email': 'reset@example.com', 'password': 'NoweHaslo123'})
    assert login.status_code == 200


def test_reset_password_revokes_existing_refresh_tokens(client, db, make_user, monkeypatch):
    u, code = _request_reset_code(client, db, make_user, monkeypatch)
    # token wydany przed zmianą hasła
    login = client.post('/api/mobile/v1/auth/login',
                        json={'email': 'reset@example.com', 'password': 'StareHaslo123'})
    old_refresh = login.get_json()['data']['refresh_token']

    client.post('/api/mobile/v1/auth/reset-password',
                json={'email': 'reset@example.com', 'code': code, 'new_password': 'NoweHaslo123'})

    r = client.post('/api/mobile/v1/auth/refresh',
                    headers={'Authorization': f'Bearer {old_refresh}'})
    assert r.status_code == 401
    assert r.get_json()['error']['code'] == 'token_revoked'


def test_reset_password_wrong_code(client, db, make_user, monkeypatch):
    u, code = _request_reset_code(client, db, make_user, monkeypatch)
    wrong = '000000' if code != '000000' else '111111'

    r = client.post('/api/mobile/v1/auth/reset-password',
                    json={'email': 'reset@example.com', 'code': wrong,
                          'new_password': 'NoweHaslo123'})
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'invalid_code'
    db.session.refresh(u)
    assert u.check_password('StareHaslo123')  # hasło bez zmian


def test_reset_password_expired_code(client, db, make_user, monkeypatch):
    from modules.orders.models import get_local_now
    from datetime import timedelta
    u, code = _request_reset_code(client, db, make_user, monkeypatch)
    u.password_reset_code_expires = get_local_now() - timedelta(minutes=1)
    db.session.commit()

    r = client.post('/api/mobile/v1/auth/reset-password',
                    json={'email': 'reset@example.com', 'code': code,
                          'new_password': 'NoweHaslo123'})
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'invalid_code'


def test_reset_password_unknown_email_is_invalid_code(client, db, make_user, monkeypatch):
    r = client.post('/api/mobile/v1/auth/reset-password',
                    json={'email': 'ghost@example.com', 'code': '123456',
                          'new_password': 'NoweHaslo123'})
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'invalid_code'  # brak wycieku istnienia konta


def test_reset_password_weak_password_does_not_consume_code(client, db, make_user, monkeypatch):
    u, code = _request_reset_code(client, db, make_user, monkeypatch)

    r = client.post('/api/mobile/v1/auth/reset-password',
                    json={'email': 'reset@example.com', 'code': code, 'new_password': 'krotkie'})
    assert r.status_code == 400
    err = r.get_json()['error']
    assert err['code'] == 'invalid_input'
    assert err['details']['field'] == 'new_password'

    # kod NIE został zużyty — ten sam kod z poprawnym hasłem działa
    db.session.refresh(u)
    assert u.password_reset_code == code
    r2 = client.post('/api/mobile/v1/auth/reset-password',
                     json={'email': 'reset@example.com', 'code': code,
                           'new_password': 'NoweHaslo123'})
    assert r2.status_code == 200


def test_reset_password_weak_password_complexity_rule(client, db, make_user, monkeypatch):
    u, code = _request_reset_code(client, db, make_user, monkeypatch)
    # 8+ znaków, ale bez dużej litery/cyfry — łamie regułę złożoności
    r = client.post('/api/mobile/v1/auth/reset-password',
                    json={'email': 'reset@example.com', 'code': code,
                          'new_password': 'samemalelitery'})
    assert r.status_code == 400
    err = r.get_json()['error']
    assert err['code'] == 'invalid_input' and err['details']['field'] == 'new_password'


def test_reset_password_lockout_after_five_attempts(client, db, make_user, monkeypatch):
    u, code = _request_reset_code(client, db, make_user, monkeypatch)
    wrong = '000000' if code != '000000' else '111111'

    for _ in range(5):
        r = client.post('/api/mobile/v1/auth/reset-password',
                        json={'email': 'reset@example.com', 'code': wrong,
                              'new_password': 'NoweHaslo123'})
        assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_code'

    db.session.refresh(u)
    assert u.is_password_reset_locked()
    # po lockout nawet POPRAWNY kod jest odrzucany (mapowany na invalid_code)
    r = client.post('/api/mobile/v1/auth/reset-password',
                    json={'email': 'reset@example.com', 'code': code,
                          'new_password': 'NoweHaslo123'})
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_code'


def test_reset_password_code_is_single_use(client, db, make_user, monkeypatch):
    u, code = _request_reset_code(client, db, make_user, monkeypatch)
    r1 = client.post('/api/mobile/v1/auth/reset-password',
                     json={'email': 'reset@example.com', 'code': code,
                           'new_password': 'NoweHaslo123'})
    assert r1.status_code == 200
    # ponowne użycie zużytego kodu odrzucone
    r2 = client.post('/api/mobile/v1/auth/reset-password',
                     json={'email': 'reset@example.com', 'code': code,
                           'new_password': 'InneHaslo123'})
    assert r2.status_code == 400 and r2.get_json()['error']['code'] == 'invalid_code'
