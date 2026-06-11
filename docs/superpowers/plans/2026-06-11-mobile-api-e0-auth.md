# Mobile API — Etap E0 (Fundament + Auth) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zbudować fundament mobilnego API ThunderOrders — nowy moduł `modules/api_mobile/` z blueprintem `/api/mobile/v1`, autoryzacją JWT (access + refresh), odwoływaniem tokenów (blocklist w bazie) oraz pełnym flow auth (rejestracja + 6-cyfrowy kod e-mail, logowanie, Google Sign-In, refresh, logout, me, app-version, health).

**Architecture:** Nowy blueprint CSRF-exempt obok istniejącego `/api`. Reużywa istniejący model `User` i jego metody (`set_password`, `check_password`, `generate_verification_code`, `EmailManager.send_verification_code`) — NIE duplikuje logiki auth. JWT przez `flask-jwt-extended`; refresh tokeny unieważnialne przez tabelę `mobile_token_blocklist` (jti). Google Sign-In: apka wysyła Google ID token, backend weryfikuje przez `google-auth`, wydaje własne JWT. Każda zmiana bazy idzie przez migrację Flask-Migrate.

**Tech Stack:** Flask, flask-jwt-extended, google-auth, SQLAlchemy, Flask-Migrate (Alembic), pytest.

---

## Założenia i kontekst dla wykonawcy

**Czytaj najpierw spec:** `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md` (sekcje 4 i 5 — auth i kontrakt API).

**Istniejące elementy do REUŻYCIA (nie pisz ich od nowa):**
- `modules/auth/models.py` → klasa `User`:
  - `user.set_password(pw)` / `user.check_password(pw)` (pbkdf2:sha256)
  - `user.generate_verification_code()` → zwraca `(code, session_token)`, ustawia `email_verification_code`, `email_verification_code_expires` (+24h), `verification_session_token`, zeruje `email_verification_attempts`
  - `user.can_resend_code()` → `(can_resend: bool, seconds_remaining: int)`
  - Pola: `email`, `password_hash` (nullable dla OAuth), `google_id`, `is_active`, `email_verified`, `first_name`, `last_name`, `phone`, `role`, `email_verification_code`, `email_verification_code_expires`, `email_verification_attempts`, `email_verification_locked_until`, `verification_session_token`
- `modules/emails/...` → `EmailManager.send_verification_code(user, code)` (wysyła e-mail z kodem). Import: `from modules.emails.email_manager import EmailManager` — **zweryfikuj dokładną ścieżkę importu w Task 5** przez `grep -rn "class EmailManager" modules/`.
- `modules/orders/models.py` → `get_local_now()` (czas lokalny PL, używany w całym projekcie zamiast `datetime.now()`).
- `extensions.py` → `db`, `limiter`, `csrf` (zarejestrowane rozszerzenia).

**Konwencje testów (z `tests/conftest.py`):**
- Fixtury: `app` (`create_app('testing')` + `db.create_all`), `client` (test_client), `db`, `make_user(role=, email=, **kwargs)` (tworzy `User` z `is_active=True, email_verified=True`), `make_product`, `make_order`, `login(user)`.
- Importy modeli **wewnątrz** funkcji testowych (nie na górze pliku) — bo `create_app()` musi pierwszy zainicjalizować SQLAlchemy.
- Uruchamianie: `pytest tests/<plik>.py -v` z aktywnym venv (`source venv/bin/activate`).

**Format odpowiedzi API (spójny w całym module):**
- Sukces: `{"success": true, "data": {...}}`
- Błąd: `{"success": false, "error": {"code": "<slug>", "message": "<tekst>"}}`
- Helper do tego budujemy w Task 3 (`json_ok`, `json_err`).

**Wartość `user` w odpowiedziach auth (DTO):**
```json
{"id": 1, "email": "x@y.pl", "first_name": "Jan", "last_name": "Kowalski",
 "full_name": "Jan Kowalski", "phone": "+48...", "role": "client",
 "avatar_url": null, "email_verified": true}
```
Serializer budujemy w Task 3 (`serialize_user`).

---

## File Structure

- `requirements.txt` — dodać `Flask-JWT-Extended`, `google-auth`.
- `extensions.py` — dodać instancję `jwt = JWTManager()`.
- `app.py` — `jwt.init_app(app)`, rejestracja nowego blueprintu z `csrf.exempt`, konfiguracja JWT, callback blocklisty.
- `config.py` — klucze JWT (sekret, TTL), `MOBILE_MIN_APP_VERSION`, `MOBILE_LATEST_APP_VERSION`, `GOOGLE_OAUTH_CLIENT_IDS`.
- `modules/api_mobile/__init__.py` — blueprint `api_mobile_bp` (`url_prefix='/api/mobile/v1'`).
- `modules/api_mobile/models.py` — `MobileTokenBlocklist`.
- `modules/api_mobile/helpers.py` — `json_ok`, `json_err`, `serialize_user`.
- `modules/api_mobile/auth_routes.py` — endpointy auth + health + app-version.
- `modules/api_mobile/google_auth.py` — weryfikacja Google ID tokenu.
- `migrations/versions/<hash>_mobile_token_blocklist.py` — migracja tabeli blocklisty.
- `tests/test_mobile_api_auth.py` — testy całego E0.

---

### Task 1: Zależności (flask-jwt-extended, google-auth)

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Dodać zależności do requirements.txt**

Dodaj dwie linie (zachowaj porządek alfabetyczny pliku — wstaw w sensownym miejscu):
```
Flask-JWT-Extended==4.6.0
google-auth==2.35.0
```

- [ ] **Step 2: Zainstalować w venv**

Run: `source venv/bin/activate && pip install Flask-JWT-Extended==4.6.0 google-auth==2.35.0`
Expected: `Successfully installed Flask-JWT-Extended-4.6.0 ... google-auth-2.35.0 ...`

- [ ] **Step 3: Zweryfikować import**

Run: `source venv/bin/activate && python -c "import flask_jwt_extended, google.oauth2.id_token; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "build(mobile-api): dodaj Flask-JWT-Extended i google-auth"
```

---

### Task 2: Konfiguracja JWT + wersja apki + Google client IDs

**Files:**
- Modify: `config.py`
- Modify: `extensions.py`

- [ ] **Step 1: Dodać konfigurację do config.py**

Znajdź klasę bazową `Config` w `config.py` i dodaj pola (czytane z env, z sensownymi domyślnymi dla dev):
```python
    # --- Mobile API (JWT) ---
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY') or os.getenv('SECRET_KEY', 'dev-jwt-secret-change-me')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv('JWT_ACCESS_MINUTES', '30')))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.getenv('JWT_REFRESH_DAYS', '30')))

    # Minimalna i najnowsza wersja aplikacji mobilnej (wymuszanie aktualizacji)
    MOBILE_MIN_APP_VERSION = os.getenv('MOBILE_MIN_APP_VERSION', '1.0.0')
    MOBILE_LATEST_APP_VERSION = os.getenv('MOBILE_LATEST_APP_VERSION', '1.0.0')

    # Dozwolone Google OAuth client ID (z aplikacji mobilnej). Lista po przecinku.
    GOOGLE_OAUTH_CLIENT_IDS = [
        c.strip() for c in os.getenv('GOOGLE_OAUTH_CLIENT_IDS', '').split(',') if c.strip()
    ]
```

Upewnij się, że na górze `config.py` jest `from datetime import timedelta` i `import os` (dodaj `timedelta` do istniejącego importu, jeśli go nie ma).

- [ ] **Step 2: Dodać instancję JWTManager do extensions.py**

W `extensions.py`, obok pozostałych rozszerzeń, dodaj:
```python
from flask_jwt_extended import JWTManager

jwt = JWTManager()
```

- [ ] **Step 3: Sanity check — aplikacja się importuje**

Run: `source venv/bin/activate && python -c "from extensions import jwt; print(type(jwt).__name__)"`
Expected: `JWTManager`

- [ ] **Step 4: Commit**

```bash
git add config.py extensions.py
git commit -m "feat(mobile-api): konfiguracja JWT, wersji apki i Google client IDs"
```

---

### Task 3: Model blocklisty tokenów + migracja

**Files:**
- Create: `modules/api_mobile/__init__.py`
- Create: `modules/api_mobile/models.py`
- Create: `migrations/versions/<auto>_mobile_token_blocklist.py` (generowana)
- Test: `tests/test_mobile_api_auth.py`

- [ ] **Step 1: Utworzyć pusty pakiet i blueprint**

`modules/api_mobile/__init__.py`:
```python
"""
Mobile API Module
Dedykowane, wersjonowane API dla aplikacji mobilnej (Flutter).
Autoryzacja przez JWT (nie session/CSRF jak web).
"""

from flask import Blueprint

api_mobile_bp = Blueprint('api_mobile', __name__, url_prefix='/api/mobile/v1')

# Trasy importujemy na końcu, aby uniknąć cyklicznych importów.
from . import auth_routes  # noqa: E402,F401
```

> Uwaga: `auth_routes` powstaje w Task 5. Do tego czasu ten import się wywali — dlatego
> w tym tasku tymczasowo zakomentuj ostatnią linię (`from . import auth_routes`) i odkomentuj ją w Task 5, Step 1.
> Zakomentuj teraz:
```python
# from . import auth_routes  # odkomentowane w Task 5
```

- [ ] **Step 2: Utworzyć model blocklisty**

`modules/api_mobile/models.py`:
```python
"""Model blocklisty refresh tokenów dla mobilnego API (realny logout / unieważnianie)."""

from extensions import db
from modules.orders.models import get_local_now


class MobileTokenBlocklist(db.Model):
    __tablename__ = 'mobile_token_blocklist'

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, index=True, unique=True)
    token_type = db.Column(db.String(16), nullable=False)  # 'access' | 'refresh'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=get_local_now)

    @classmethod
    def contains(cls, jti):
        return db.session.query(cls.id).filter_by(jti=jti).first() is not None
```

> Zweryfikuj, że tabela użytkowników nazywa się `users` (FK `users.id`): `grep -n "__tablename__" modules/auth/models.py`.
> Jeśli inna — popraw FK.

- [ ] **Step 3: Wygenerować migrację**

Najpierw upewnij się, że model jest importowany przy starcie aplikacji, aby Alembic go zobaczył. Tymczasowo dodaj do `modules/api_mobile/__init__.py` po definicji blueprintu:
```python
from . import models  # noqa: E402,F401  (żeby Alembic wykrył tabelę)
```
Zarejestruj blueprint w `app.py` (pełna rejestracja w Task 4, ale do migracji wystarczy import modelu — jeśli blueprint nie jest jeszcze zarejestrowany, dodaj sam import modelu w `app.py` tymczasowo LUB wykonaj rejestrację z Task 4 najpierw). Najprościej: **wykonaj Task 4 Step 1–2 przed generowaniem migracji.**

Run: `source venv/bin/activate && flask db migrate -m "mobile_token_blocklist"`
Expected: `Generating migrations/versions/<hash>_mobile_token_blocklist.py ... done`

- [ ] **Step 4: Sprawdzić wygenerowaną migrację**

Otwórz nowy plik w `migrations/versions/`. Zweryfikuj, że `upgrade()` tworzy tabelę `mobile_token_blocklist` z kolumnami `id, jti, token_type, user_id, expires_at, created_at`, indeksami na `jti` (unique) i `user_id`, oraz FK do `users.id`. Zweryfikuj, że `downgrade()` robi `op.drop_table('mobile_token_blocklist')`. Usuń ewentualne niezwiązane zmiany, które Alembic mógł błędnie wykryć.

- [ ] **Step 5: Zastosować migrację lokalnie**

Run: `source venv/bin/activate && flask db upgrade`
Expected: `Running upgrade ... -> <hash>, mobile_token_blocklist`

- [ ] **Step 6: Test — model działa**

Dodaj do `tests/test_mobile_api_auth.py` (utwórz plik):
```python
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
```

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py::test_blocklist_contains -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add modules/api_mobile/__init__.py modules/api_mobile/models.py migrations/versions/ tests/test_mobile_api_auth.py
git commit -m "feat(mobile-api): model i migracja blocklisty tokenów JWT"
```

---

### Task 4: Rejestracja JWT + blueprint w app.py (z callbackiem blocklisty)

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Zainicjalizować JWT i zarejestrować blueprint**

W `app.py`:
1. Dodaj `jwt` do importu z `extensions` (linia ~55): `from extensions import db, migrate, login_manager, mail, csrf, executor, limiter, socketio, jwt`.
2. Po `csrf.init_app(app)` (ok. linii 91) dodaj `jwt.init_app(app)`.
3. W `register_blueprints(app)` (ok. linii 255), obok pozostałych rejestracji, dodaj:
```python
    from modules.api_mobile import api_mobile_bp
    csrf.exempt(api_mobile_bp)
    app.register_blueprint(api_mobile_bp)
```

- [ ] **Step 2: Dodać callback blocklisty JWT**

W `create_app`, po `jwt.init_app(app)`, dodaj rejestrację callbacku sprawdzającego blocklistę:
```python
    @jwt.token_in_blocklist_loader
    def _mobile_token_revoked(jwt_header, jwt_payload):
        from modules.api_mobile.models import MobileTokenBlocklist
        return MobileTokenBlocklist.contains(jwt_payload['jti'])
```

- [ ] **Step 3: Sanity check — aplikacja startuje i trasa health istnieje po Task 5**

Na tym etapie blueprint jest pusty (auth_routes dojdzie w Task 5). Zweryfikuj jedynie, że aplikacja się tworzy bez błędu:
Run: `source venv/bin/activate && python -c "from app import create_app; a=create_app('testing'); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat(mobile-api): init JWT, rejestracja blueprintu, callback blocklisty"
```

---

### Task 5: Helpery + endpointy health i app-version

**Files:**
- Create: `modules/api_mobile/helpers.py`
- Create: `modules/api_mobile/auth_routes.py`
- Modify: `modules/api_mobile/__init__.py` (odkomentować import auth_routes)
- Test: `tests/test_mobile_api_auth.py`

- [ ] **Step 1: Helpery odpowiedzi i serializacji**

`modules/api_mobile/helpers.py`:
```python
"""Wspólne helpery odpowiedzi JSON i serializacji dla mobilnego API."""

from flask import jsonify


def json_ok(data=None, status=200):
    return jsonify({'success': True, 'data': data if data is not None else {}}), status


def json_err(code, message, status=400):
    return jsonify({'success': False, 'error': {'code': code, 'message': message}}), status


def serialize_user(user):
    full = ' '.join(p for p in [user.first_name, user.last_name] if p).strip() or None
    avatar_url = None
    # Avatar jest opcjonalny; jeśli model ma relację/URL — uzupełnij tutaj.
    return {
        'id': user.id,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': full,
        'phone': user.phone,
        'role': user.role,
        'avatar_url': avatar_url,
        'email_verified': bool(user.email_verified),
    }
```

Odkomentuj w `modules/api_mobile/__init__.py` import tras:
```python
from . import auth_routes  # noqa: E402,F401
```

- [ ] **Step 2: Test — health i app-version (najpierw failujący)**

Dodaj do `tests/test_mobile_api_auth.py`:
```python
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
```

- [ ] **Step 3: Uruchomić test — ma FAILOWAĆ (brak tras)**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py::test_health -v`
Expected: FAIL (404 — trasa nie istnieje)

- [ ] **Step 4: Zaimplementować trasy w auth_routes.py**

`modules/api_mobile/auth_routes.py` (na razie tylko health + app-version; reszta w kolejnych taskach):
```python
"""Trasy auth + meta (health, app-version) dla mobilnego API."""

from flask import current_app
from . import api_mobile_bp
from .helpers import json_ok


@api_mobile_bp.route('/health', methods=['GET'])
def health():
    return json_ok({'status': 'ok'})


@api_mobile_bp.route('/app-version', methods=['GET'])
def app_version():
    return json_ok({
        'min_version': current_app.config['MOBILE_MIN_APP_VERSION'],
        'latest_version': current_app.config['MOBILE_LATEST_APP_VERSION'],
    })
```

- [ ] **Step 5: Uruchomić testy — mają PRZEJŚĆ**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py::test_health tests/test_mobile_api_auth.py::test_app_version -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add modules/api_mobile/helpers.py modules/api_mobile/auth_routes.py modules/api_mobile/__init__.py tests/test_mobile_api_auth.py
git commit -m "feat(mobile-api): helpery JSON + endpointy health i app-version"
```

---

### Task 6: Logowanie (login) — wydawanie JWT

**Files:**
- Modify: `modules/api_mobile/auth_routes.py`
- Test: `tests/test_mobile_api_auth.py`

- [ ] **Step 1: Test — logowanie poprawne i błędne (najpierw failujący)**

Dodaj do `tests/test_mobile_api_auth.py`:
```python
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
```

- [ ] **Step 2: Uruchomić — ma FAILOWAĆ**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py::test_login_success -v`
Expected: FAIL (404)

- [ ] **Step 3: Zaimplementować login**

Dodaj importy na górze `auth_routes.py`:
```python
from flask import request
from flask_jwt_extended import create_access_token, create_refresh_token
from extensions import db
from modules.auth.models import User
from .helpers import json_err
```

Dodaj trasę:
```python
@api_mobile_bp.route('/auth/login', methods=['POST'])
def login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get('email') or '').strip().lower()
    password = payload.get('password') or ''

    if not email or not password:
        return json_err('missing_fields', 'Podaj e-mail i hasło.', 401)

    user = User.query.filter(db.func.lower(User.email) == email).first()
    if user is None or not user.check_password(password):
        return json_err('invalid_credentials', 'Nieprawidłowy e-mail lub hasło.', 401)
    if not user.is_active:
        return json_err('account_inactive', 'Konto jest nieaktywne.', 403)
    if not user.email_verified:
        return json_err('email_not_verified', 'Potwierdź adres e-mail, aby się zalogować.', 403)

    identity = str(user.id)
    return json_ok({
        'access_token': create_access_token(identity=identity),
        'refresh_token': create_refresh_token(identity=identity),
        'user': serialize_user(user),
    })
```

Dodaj brakujący import serializera na górze: `from .helpers import json_ok, json_err, serialize_user` (scal z istniejącym importem helpers).

- [ ] **Step 4: Uruchomić testy logowania**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py -k login -v`
Expected: PASS (test_login_success, test_login_wrong_password)

- [ ] **Step 5: Commit**

```bash
git add modules/api_mobile/auth_routes.py tests/test_mobile_api_auth.py
git commit -m "feat(mobile-api): logowanie z wydawaniem JWT (access+refresh)"
```

---

### Task 7: /auth/me + /auth/refresh

**Files:**
- Modify: `modules/api_mobile/auth_routes.py`
- Test: `tests/test_mobile_api_auth.py`

- [ ] **Step 1: Test — /me wymaga tokenu, /refresh wydaje nowy access (najpierw failujący)**

Dodaj do testów helper logowania zwracający tokeny + testy:
```python
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
```

> Uwaga: `flask-jwt-extended` domyślnie czyta refresh token z nagłówka `Authorization` dla tras
> oznaczonych `@jwt_required(refresh=True)`. Dlatego w teście refresh wysyłamy refresh token w nagłówku.
> Kontrakt API w specie pokazuje `{ refresh_token }` w body — w implementacji przyjmujemy nagłówek
> (standard flask-jwt-extended). Apka Flutter wyśle refresh w nagłówku `Authorization`. To jest świadoma,
> drobna korekta kontraktu — odnotuj ją (Task 12 zaktualizuje spec).

- [ ] **Step 2: Uruchomić — ma FAILOWAĆ**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py::test_me_returns_user -v`
Expected: FAIL (404)

- [ ] **Step 3: Zaimplementować /me i /refresh**

Dodaj do importów: `from flask_jwt_extended import jwt_required, get_jwt_identity`.

Dodaj trasy:
```python
@api_mobile_bp.route('/auth/me', methods=['GET'])
@jwt_required()
def me():
    user = User.query.get(int(get_jwt_identity()))
    if user is None:
        return json_err('user_not_found', 'Nie znaleziono użytkownika.', 404)
    return json_ok({'user': serialize_user(user)})


@api_mobile_bp.route('/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    return json_ok({'access_token': create_access_token(identity=identity)})
```

- [ ] **Step 4: Uruchomić testy**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py -k "me or refresh" -v`
Expected: PASS (test_me_requires_token, test_me_returns_user, test_refresh_issues_new_access)

- [ ] **Step 5: Commit**

```bash
git add modules/api_mobile/auth_routes.py tests/test_mobile_api_auth.py
git commit -m "feat(mobile-api): endpointy /auth/me i /auth/refresh"
```

---

### Task 8: Logout (unieważnienie refresh tokenu w blocklist)

**Files:**
- Modify: `modules/api_mobile/auth_routes.py`
- Test: `tests/test_mobile_api_auth.py`

- [ ] **Step 1: Test — po logout refresh przestaje działać (najpierw failujący)**

```python
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
```

- [ ] **Step 2: Uruchomić — ma FAILOWAĆ**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py::test_logout_revokes_refresh -v`
Expected: FAIL (404 na logout)

- [ ] **Step 3: Zaimplementować logout**

Dodaj do importów: `from flask_jwt_extended import get_jwt` oraz `from datetime import datetime, timezone` i `from .models import MobileTokenBlocklist`.

```python
@api_mobile_bp.route('/auth/logout', methods=['POST'])
@jwt_required(refresh=True)
def logout():
    token = get_jwt()
    exp = datetime.fromtimestamp(token['exp'], tz=timezone.utc).replace(tzinfo=None)
    db.session.add(MobileTokenBlocklist(
        jti=token['jti'],
        token_type='refresh',
        user_id=int(get_jwt_identity()),
        expires_at=exp,
    ))
    db.session.commit()
    return json_ok({'message': 'Wylogowano.'})
```

- [ ] **Step 4: Uruchomić test**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py::test_logout_revokes_refresh -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/api_mobile/auth_routes.py tests/test_mobile_api_auth.py
git commit -m "feat(mobile-api): logout unieważniający refresh token (blocklist)"
```

---

### Task 9: Rejestracja (register) + ponowne wysłanie kodu (resend-code)

**Files:**
- Modify: `modules/api_mobile/auth_routes.py`
- Test: `tests/test_mobile_api_auth.py`

> Reużywamy `user.generate_verification_code()` i `EmailManager.send_verification_code()`.
> W testach **mockujemy wysyłkę e-maila**, by nie wysyłać realnych wiadomości.

- [ ] **Step 1: Zweryfikować ścieżkę importu EmailManager**

Run: `grep -rn "class EmailManager" modules/ && grep -rn "def send_verification_code" modules/`
Zanotuj dokładny import (np. `from modules.emails.email_manager import EmailManager`). Użyj go w Step 3 i w mocku w Step 2.

- [ ] **Step 2: Test — rejestracja tworzy konto i wysyła kod (najpierw failujący)**

```python
def test_register_creates_unverified_user(client, db, monkeypatch):
    sent = {}
    # Podmień ścieżkę importu zgodnie z wynikiem Step 1:
    import modules.emails.email_manager as em
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
    import modules.emails.email_manager as em
    monkeypatch.setattr(em.EmailManager, 'send_verification_code',
                        staticmethod(lambda user, code: True))
    make_user(email='dup@example.com')
    r = client.post('/api/mobile/v1/auth/register', json={
        'email': 'dup@example.com', 'password': 'Haslo123!',
        'first_name': 'A', 'last_name': 'B', 'phone': '+48500',
    })
    assert r.status_code == 409
    assert r.get_json()['error']['code'] == 'email_taken'
```

> Jeśli Step 1 wykaże inną ścieżkę modułu niż `modules.emails.email_manager`, popraw `import ... as em` w obu testach.

- [ ] **Step 3: Uruchomić — ma FAILOWAĆ**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py::test_register_creates_unverified_user -v`
Expected: FAIL (404)

- [ ] **Step 4: Zaimplementować register i resend-code**

Dodaj import EmailManagera (ścieżka z Step 1), np.:
```python
from modules.emails.email_manager import EmailManager
```

```python
@api_mobile_bp.route('/auth/register', methods=['POST'])
def register():
    p = request.get_json(silent=True) or {}
    email = (p.get('email') or '').strip().lower()
    password = p.get('password') or ''
    first_name = (p.get('first_name') or '').strip()
    last_name = (p.get('last_name') or '').strip()
    phone = (p.get('phone') or '').strip()

    if not email or not password:
        return json_err('missing_fields', 'E-mail i hasło są wymagane.', 400)
    if User.query.filter(db.func.lower(User.email) == email).first():
        return json_err('email_taken', 'Konto z tym adresem już istnieje.', 409)

    user = User(email=email, first_name=first_name, last_name=last_name,
                phone=phone, role='client', is_active=True, email_verified=False)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    code, _ = user.generate_verification_code()
    db.session.commit()
    EmailManager.send_verification_code(user, code)

    return json_ok({'email': email, 'message': 'Wysłaliśmy kod weryfikacyjny na e-mail.'}, 201)


@api_mobile_bp.route('/auth/resend-code', methods=['POST'])
def resend_code():
    p = request.get_json(silent=True) or {}
    email = (p.get('email') or '').strip().lower()
    user = User.query.filter(db.func.lower(User.email) == email).first()
    # Nie zdradzamy, czy konto istnieje — zawsze 200.
    if user and not user.email_verified:
        can_resend, _secs = user.can_resend_code()
        if can_resend:
            code, _ = user.generate_verification_code()
            db.session.commit()
            EmailManager.send_verification_code(user, code)
    return json_ok({'message': 'Jeśli konto wymaga weryfikacji, wysłaliśmy nowy kod.'})
```

- [ ] **Step 5: Uruchomić testy**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py -k register -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add modules/api_mobile/auth_routes.py tests/test_mobile_api_auth.py
git commit -m "feat(mobile-api): rejestracja + ponowne wysłanie kodu weryfikacyjnego"
```

---

### Task 10: Weryfikacja e-mail kodem (verify-email) — aktywacja + wydanie JWT

**Files:**
- Modify: `modules/api_mobile/auth_routes.py`
- Test: `tests/test_mobile_api_auth.py`

- [ ] **Step 1: Test — poprawny kod aktywuje konto i zwraca tokeny (najpierw failujący)**

```python
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
```

- [ ] **Step 2: Uruchomić — ma FAILOWAĆ**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py::test_verify_email_success -v`
Expected: FAIL (404)

- [ ] **Step 3: Zaimplementować verify-email**

> Sprawdź, czy `User` ma gotową metodę weryfikacji kodu (np. `verify_code`/`check_verification_code`):
> `grep -n "def .*code\|def verify" modules/auth/models.py`. Jeśli istnieje — użyj jej. Jeśli nie,
> zastosuj poniższą logikę inline (porównanie kodu + ważność `email_verification_code_expires`).

```python
from modules.orders.models import get_local_now

@api_mobile_bp.route('/auth/verify-email', methods=['POST'])
def verify_email_code():
    p = request.get_json(silent=True) or {}
    email = (p.get('email') or '').strip().lower()
    code = (p.get('code') or '').strip()

    user = User.query.filter(db.func.lower(User.email) == email).first()
    if user is None:
        return json_err('invalid_code', 'Nieprawidłowy kod.', 400)
    if user.email_verified:
        return json_err('already_verified', 'Konto jest już zweryfikowane.', 400)
    if not user.email_verification_code or not user.email_verification_code_expires:
        return json_err('invalid_code', 'Brak aktywnego kodu. Wyślij nowy.', 400)
    if get_local_now() > user.email_verification_code_expires:
        return json_err('code_expired', 'Kod wygasł. Wyślij nowy.', 400)
    if code != user.email_verification_code:
        user.email_verification_attempts = (user.email_verification_attempts or 0) + 1
        db.session.commit()
        return json_err('invalid_code', 'Nieprawidłowy kod.', 400)

    user.email_verified = True
    user.email_verification_code = None
    user.email_verification_code_expires = None
    db.session.commit()

    identity = str(user.id)
    return json_ok({
        'access_token': create_access_token(identity=identity),
        'refresh_token': create_refresh_token(identity=identity),
        'user': serialize_user(user),
    })
```

- [ ] **Step 4: Uruchomić testy**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py -k verify -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/api_mobile/auth_routes.py tests/test_mobile_api_auth.py
git commit -m "feat(mobile-api): weryfikacja e-mail kodem + aktywacja konta"
```

---

### Task 11: Google Sign-In (weryfikacja ID tokenu → JWT)

**Files:**
- Create: `modules/api_mobile/google_auth.py`
- Modify: `modules/api_mobile/auth_routes.py`
- Test: `tests/test_mobile_api_auth.py`

- [ ] **Step 1: Moduł weryfikacji Google ID tokenu**

`modules/api_mobile/google_auth.py`:
```python
"""Weryfikacja Google ID tokenu z aplikacji mobilnej."""

from flask import current_app
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests


def verify_google_id_token(token):
    """Zwraca dict z danymi (email, sub, given_name, family_name) albo None gdy niepoprawny."""
    try:
        info = google_id_token.verify_oauth2_token(
            token, google_requests.Request()
        )
    except ValueError:
        return None

    allowed = current_app.config.get('GOOGLE_OAUTH_CLIENT_IDS') or []
    if allowed and info.get('aud') not in allowed:
        return None
    if info.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
        return None
    if not info.get('email_verified'):
        return None
    return info
```

- [ ] **Step 2: Test — Google login (z mockiem weryfikacji) (najpierw failujący)**

```python
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
```

- [ ] **Step 3: Uruchomić — ma FAILOWAĆ**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py::test_google_login_new_user -v`
Expected: FAIL (404)

- [ ] **Step 4: Zaimplementować /auth/google**

Dodaj import na górze `auth_routes.py`:
```python
from .google_auth import verify_google_id_token
```

```python
@api_mobile_bp.route('/auth/google', methods=['POST'])
def google_login():
    p = request.get_json(silent=True) or {}
    token = p.get('id_token') or ''
    info = verify_google_id_token(token)
    if info is None:
        return json_err('invalid_google_token', 'Nieprawidłowy token Google.', 401)

    email = (info.get('email') or '').strip().lower()
    google_sub = info.get('sub')

    user = (User.query.filter_by(google_id=google_sub).first()
            or User.query.filter(db.func.lower(User.email) == email).first())

    if user is None:
        user = User(email=email, first_name=info.get('given_name'),
                    last_name=info.get('family_name'), role='client',
                    is_active=True, email_verified=True, google_id=google_sub)
        db.session.add(user)
    else:
        if not user.google_id:
            user.google_id = google_sub
        user.email_verified = True
    db.session.commit()

    if not user.is_active:
        return json_err('account_inactive', 'Konto jest nieaktywne.', 403)

    identity = str(user.id)
    return json_ok({
        'access_token': create_access_token(identity=identity),
        'refresh_token': create_refresh_token(identity=identity),
        'user': serialize_user(user),
    })
```

- [ ] **Step 5: Uruchomić testy**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py -k google -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add modules/api_mobile/google_auth.py modules/api_mobile/auth_routes.py tests/test_mobile_api_auth.py
git commit -m "feat(mobile-api): logowanie przez Google (ID token -> JWT)"
```

---

### Task 12: Pełny przebieg testów + aktualizacja specu

**Files:**
- Modify: `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md`

- [ ] **Step 1: Uruchomić cały zestaw testów E0**

Run: `source venv/bin/activate && pytest tests/test_mobile_api_auth.py -v`
Expected: wszystkie testy PASS (blocklist, health, app-version, login x2, me x2, refresh, logout, register x2, verify x2, google x2).

- [ ] **Step 2: Uruchomić pełny pakiet testów (regresja)**

Run: `source venv/bin/activate && pytest -q`
Expected: brak nowych błędów względem stanu sprzed E0 (istniejące testy nadal przechodzą).

- [ ] **Step 3: Zaktualizować spec o drobną korektę kontraktu**

W `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md`, w sekcji „Auth — `/auth/`",
dopisz notę przy `refresh` i `logout`: refresh token przekazywany jest w nagłówku
`Authorization: Bearer <refresh_token>` (standard flask-jwt-extended), nie w body.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md
git commit -m "docs(mobile-api): doprecyzowanie przekazywania refresh tokenu (nagłówek)"
```

---

## Definition of Done (E0)

- [ ] Nowy moduł `modules/api_mobile/` z blueprintem `/api/mobile/v1` zarejestrowany i CSRF-exempt.
- [ ] JWT (access+refresh) działa; refresh tokeny unieważnialne przez `mobile_token_blocklist` (migracja zastosowana).
- [ ] Endpointy: `health`, `app-version`, `auth/login`, `auth/me`, `auth/refresh`, `auth/logout`, `auth/register`, `auth/resend-code`, `auth/verify-email`, `auth/google` — wszystkie pokryte testami.
- [ ] Reużyto istniejącą logikę auth (`User`, kody weryfikacyjne, `EmailManager`) — bez duplikacji.
- [ ] Cały `pytest -q` przechodzi (brak regresji).
- [ ] Migracja zacommitowana razem z kodem.

## Uwaga deploymentowa (po E0, przy pierwszym wdrożeniu na serwer)

Na produkcji w `.env` ustawić: `JWT_SECRET_KEY` (silny, losowy), `GOOGLE_OAUTH_CLIENT_IDS`
(client ID z konsoli Google dla aplikacji Android/iOS), `MOBILE_MIN_APP_VERSION`,
`MOBILE_LATEST_APP_VERSION`. Migracja wejdzie auto-deployem (webhook). Restart obu usług:
`sudo systemctl restart thunderorders-http thunderorders-ws`. (Szczegóły: `docs/DEPLOYMENT.md`.)
