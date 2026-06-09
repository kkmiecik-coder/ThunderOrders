# Moduł Konkursów / Losowania — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zbudować modułowy konkurs „radiowy": klienci raz na cooldown losują losy (kumulują się), a admin ręcznie „na żywo" losuje N zwycięzców ważonych liczbą losów.

**Architecture:** Nowy blueprint `modules/contests/` (modele Contest / ContestSpin / ContestWinner, dziennik spinów jako źródło prawdy). Logika domenowa (eligibility AND, tickets/pula/cooldown, losowanie ważone server-side) w `utils.py`. Routes klient (`/konkurs`, `/konkurs/spin`) + admin (`/admin/konkursy/*`). UI: widget na dashboardzie klienta + modal z pionową karuzelą (spin), panel admina z losowaniem na żywo. Powiadomienia in-app + e-mail do zwycięzcy.

**Tech Stack:** Flask + Flask-SQLAlchemy + Flask-Migrate (Alembic, MariaDB prod / SQLite in-memory w testach) · WTForms · Jinja2 · vanilla JS (requestAnimationFrame) · Flask-Mail.

**Spec:** `docs/superpowers/specs/2026-06-09-konkursy-losowania-design.md`

---

## Mapa plików

**Nowe:**
- `modules/contests/__init__.py` — blueprint `contests_bp` (bez url_prefix; pełne ścieżki w routes)
- `modules/contests/models.py` — `Contest`, `ContestSpin`, `ContestWinner`
- `modules/contests/utils.py` — logika domenowa
- `modules/contests/forms.py` — `ContestForm`
- `modules/contests/routes.py` — routes klient + admin
- `migrations/versions/<rev>_add_contests_tables.py`
- `templates/client/contest.html` — strona `/konkurs`
- `templates/client/_contest_widget.html` — partial widgetu dashboardu
- `templates/admin/contests/list.html`, `form.html`, `draw.html`, `results.html`
- `templates/emails/contest_win.html`, `templates/emails/contest_win.txt`
- `static/css/pages/client/contest.css`
- `static/css/pages/admin/contests.css`
- `static/js/pages/client/contest.js` — spin + karuzela w modalu
- `static/js/pages/admin/contest-form.js` — pola warunkowe + picker produktu
- `static/js/pages/admin/contest-draw.js` — animacja losowania na żywo
- `tests/conftest.py` — fixtures (app, client, db, make_user/make_product/make_order, login)
- `tests/test_contests_models.py`, `tests/test_contests_eligibility.py`, `tests/test_contests_tickets.py`, `tests/test_contests_draw.py`, `tests/test_contests_routes_admin.py`, `tests/test_contests_routes_client.py`, `tests/test_contests_email.py`

**Modyfikowane:**
- `app.py` — rejestracja `contests_bp` w `register_blueprints()` (po `achievements_bp`, przed `shop_bp`)
- `modules/client/routes.py` — wstrzyknięcie kontekstu widgetu do `dashboard()`
- `templates/client/dashboard.html` — `{% include %}` widgetu
- `static/css/components/modals.css` — style modala spinnera (light + dark)
- `utils/email_sender.py` — `send_contest_win_email(...)`

**Konwencje:** każda zmiana DB przez migrację; CSS light + dark (`[data-theme="dark"]`); style modali w `modals.css`; CSS/JS w osobnych plikach; odpowiadamy po polsku.

---

## Task 0: Infrastruktura testowa (conftest)

**Files:**
- Create: `tests/conftest.py`

Tworzymy fixtures dla testów integracyjnych na bazie `TestingConfig` (SQLite in-memory, CSRF wyłączone). Tabele budujemy przez `db.create_all()` (modele rejestrują się przy imporcie blueprintów w `create_app`).

- [ ] **Step 1: Utwórz `tests/conftest.py`**

```python
import pytest
from app import create_app
from extensions import db as _db
from modules.auth.models import User
from modules.products.models import Product
from modules.orders.models import Order


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(db):
    counter = {'n': 0}

    def _make(role='client', email=None, **kwargs):
        counter['n'] += 1
        u = User(
            email=email or f'user{counter["n"]}@example.com',
            role=role,
            is_active=True,
            email_verified=True,
            **kwargs,
        )
        db.session.add(u)
        db.session.commit()
        return u
    return _make


@pytest.fixture
def make_product(db):
    counter = {'n': 0}

    def _make(name=None, sale_price=99.00, quantity=10, **kwargs):
        counter['n'] += 1
        p = Product(
            name=name or f'Produkt {counter["n"]}',
            sale_price=sale_price,
            quantity=quantity,
            **kwargs,
        )
        db.session.add(p)
        db.session.commit()
        return p
    return _make


@pytest.fixture
def make_order(db):
    counter = {'n': 0}

    def _make(user, status='nowe', total_amount=100.00, created_at=None, **kwargs):
        counter['n'] += 1
        o = Order(
            order_number=f'PO/{counter["n"]:08d}',
            user_id=user.id,
            status=status,
            total_amount=total_amount,
            **kwargs,
        )
        if created_at is not None:
            o.created_at = created_at
        db.session.add(o)
        db.session.commit()
        return o
    return _make


@pytest.fixture
def login(client):
    """Loguje użytkownika przez Flask-Login test session."""
    def _login(user):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
    return _login
```

- [ ] **Step 2: Sanity-check — uruchom pustą kolekcję**

Run: `python3 -m pytest tests/conftest.py -q`
Expected: `no tests ran` (brak błędów importu). Jeśli `Order`/`Product`/`User` wymagają innych NOT NULL pól — uzupełnij `_make` minimalnymi wartościami aż import i `db.create_all()` przechodzą (uruchom dowolny późniejszy test z Taska 1, by zweryfikować tworzenie rekordów).

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test(contests): fixtures bazowe (app, db, make_user/product/order, login)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 1: Scaffolding modułu + modele

**Files:**
- Create: `modules/contests/__init__.py`, `modules/contests/models.py`
- Test: `tests/test_contests_models.py`

- [ ] **Step 1: Test — domyślne wartości i relacje modeli**

```python
# tests/test_contests_models.py
from datetime import datetime


def test_contest_defaults(db, make_product, make_user):
    from modules.contests.models import Contest
    admin = make_user(role='admin')
    prod = make_product()
    c = Contest(name='Klawiatura', prize_product_id=prod.id,
                ticket_min=1, ticket_max=50, created_by_admin_id=admin.id)
    db.session.add(c)
    db.session.commit()
    assert c.id is not None
    assert c.status == 'szkic'
    assert c.num_winners == 1
    assert c.cooldown_minutes == 1440
    assert isinstance(c.created_at, datetime)


def test_spin_and_winner_persist(db, make_product, make_user):
    from modules.contests.models import Contest, ContestSpin, ContestWinner
    admin = make_user(role='admin'); user = make_user(); prod = make_product()
    c = Contest(name='X', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                created_by_admin_id=admin.id)
    db.session.add(c); db.session.commit()
    s = ContestSpin(contest_id=c.id, user_id=user.id, tickets_won=20)
    w = ContestWinner(contest_id=c.id, user_id=user.id, place=1,
                      tickets_at_draw=20, chance_pct=100.0, prize_product_id=prod.id)
    db.session.add_all([s, w]); db.session.commit()
    assert s.id and w.id
```

- [ ] **Step 2: Uruchom test — ma się wywalić**

Run: `python3 -m pytest tests/test_contests_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.contests'`.

- [ ] **Step 3: Utwórz `modules/contests/__init__.py`**

```python
from flask import Blueprint

contests_bp = Blueprint('contests', __name__)

from modules.contests import routes  # noqa: E402,F401
```

(Tymczasowo `routes` jeszcze nie istnieje — utworzymy pusty plik, by import nie padał.)

- [ ] **Step 4: Utwórz pusty `modules/contests/routes.py`**

```python
from modules.contests import contests_bp  # noqa: F401
# routes dodawane w kolejnych taskach
```

- [ ] **Step 5: Utwórz `modules/contests/models.py`**

```python
from extensions import db
from modules.orders.models import get_local_now


class Contest(db.Model):
    __tablename__ = 'contests'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(512), nullable=True)
    prize_product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    num_winners = db.Column(db.Integer, nullable=False, default=1)
    ticket_min = db.Column(db.Integer, nullable=False, default=1)
    ticket_max = db.Column(db.Integer, nullable=False, default=50)
    cooldown_minutes = db.Column(db.Integer, nullable=False, default=1440)
    eligibility_min_orders = db.Column(db.Integer, nullable=True)
    eligibility_min_total_value = db.Column(db.Numeric(10, 2), nullable=True)
    eligibility_active_within_days = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='szkic')  # szkic|aktywny|rozlosowany
    starts_at = db.Column(db.DateTime, nullable=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now, nullable=False)
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    prize_product = db.relationship('Product', foreign_keys=[prize_product_id])


class ContestSpin(db.Model):
    __tablename__ = 'contest_spins'

    id = db.Column(db.Integer, primary_key=True)
    contest_id = db.Column(db.Integer, db.ForeignKey('contests.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tickets_won = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)

    __table_args__ = (db.Index('ix_contest_spins_contest_user', 'contest_id', 'user_id'),)


class ContestWinner(db.Model):
    __tablename__ = 'contest_winners'

    id = db.Column(db.Integer, primary_key=True)
    contest_id = db.Column(db.Integer, db.ForeignKey('contests.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    place = db.Column(db.Integer, nullable=False)
    tickets_at_draw = db.Column(db.Integer, nullable=False)
    chance_pct = db.Column(db.Numeric(6, 3), nullable=True)
    prize_product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    drawn_at = db.Column(db.DateTime, default=get_local_now, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('contest_id', 'user_id', name='uq_contest_winner_user'),
        db.UniqueConstraint('contest_id', 'place', name='uq_contest_winner_place'),
    )

    user = db.relationship('User', foreign_keys=[user_id])
    prize_product = db.relationship('Product', foreign_keys=[prize_product_id])
```

- [ ] **Step 6: Zarejestruj import modeli w `create_app`**

W `modules/contests/__init__.py` import modeli musi nastąpić, by `db.create_all()` w testach je widział. Dodaj na końcu pliku:

```python
from modules.contests import models  # noqa: E402,F401
```

- [ ] **Step 7: Uruchom test — ma przejść**

Run: `python3 -m pytest tests/test_contests_models.py -v`
Expected: PASS (2 testy).

> Jeśli `db.create_all()` nie tworzy tabel `contests*`, upewnij się, że `create_app('testing')` importuje blueprint contests — patrz Task 6 Step (rejestracja). Tymczasowo można zaimportować `modules.contests.models` w conftest przed `create_all` jeśli rejestracja blueprintu jest dopiero w Tasku 6. **Najpewniej:** wykonaj Task 6 Step 1 (rejestracja blueprintu) już teraz, by modele były ładowane przez app factory.

- [ ] **Step 8: Commit**

```bash
git add modules/contests/__init__.py modules/contests/models.py modules/contests/routes.py tests/test_contests_models.py
git commit -m "feat(contests): modele Contest/ContestSpin/ContestWinner + scaffolding

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Migracja tabel

**Files:**
- Create: `migrations/versions/<rev>_add_contests_tables.py`

- [ ] **Step 1: Wygeneruj migrację**

Run: `flask db migrate -m "Add contests tables"`
Expected: powstaje plik w `migrations/versions/`.

- [ ] **Step 2: Zweryfikuj/popraw wygenerowany plik**

Sprawdź, że tworzy `contests`, `contest_spins`, `contest_winners` z FK do `users.id`/`products.id`, indeksem `ix_contest_spins_contest_user` oraz unikalnościami `uq_contest_winner_user` / `uq_contest_winner_place`. Wzorzec (dopasuj `revision`/`down_revision` do realnych):

```python
def upgrade():
    op.create_table('contests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('image_path', sa.String(length=512), nullable=True),
        sa.Column('prize_product_id', sa.Integer(), nullable=True),
        sa.Column('num_winners', sa.Integer(), nullable=False),
        sa.Column('ticket_min', sa.Integer(), nullable=False),
        sa.Column('ticket_max', sa.Integer(), nullable=False),
        sa.Column('cooldown_minutes', sa.Integer(), nullable=False),
        sa.Column('eligibility_min_orders', sa.Integer(), nullable=True),
        sa.Column('eligibility_min_total_value', sa.Numeric(10, 2), nullable=True),
        sa.Column('eligibility_active_within_days', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('starts_at', sa.DateTime(), nullable=True),
        sa.Column('ends_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_admin_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['prize_product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['created_by_admin_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('contest_spins',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contest_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tickets_won', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['contest_id'], ['contests.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contest_spins_contest_user', 'contest_spins', ['contest_id', 'user_id'], unique=False)
    op.create_table('contest_winners',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contest_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('place', sa.Integer(), nullable=False),
        sa.Column('tickets_at_draw', sa.Integer(), nullable=False),
        sa.Column('chance_pct', sa.Numeric(6, 3), nullable=True),
        sa.Column('prize_product_id', sa.Integer(), nullable=True),
        sa.Column('drawn_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['contest_id'], ['contests.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['prize_product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('contest_id', 'user_id', name='uq_contest_winner_user'),
        sa.UniqueConstraint('contest_id', 'place', name='uq_contest_winner_place'),
    )


def downgrade():
    op.drop_table('contest_winners')
    op.drop_index('ix_contest_spins_contest_user', table_name='contest_spins')
    op.drop_table('contest_spins')
    op.drop_table('contests')
```

- [ ] **Step 3: Zastosuj migrację lokalnie**

Run: `flask db upgrade`
Expected: trzy tabele w lokalnej bazie MariaDB (XAMPP), brak błędów.

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/
git commit -m "migrate(contests): tabele contests/contest_spins/contest_winners

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Eligibility (logika udziału, AND)

**Files:**
- Create/Modify: `modules/contests/utils.py`
- Test: `tests/test_contests_eligibility.py`

- [ ] **Step 1: Testy — każde kryterium i kombinacja AND**

```python
# tests/test_contests_eligibility.py
from datetime import timedelta
from modules.orders.models import get_local_now


def _contest(db, make_product, make_user, **kw):
    from modules.contests.models import Contest
    admin = make_user(role='admin'); prod = make_product()
    c = Contest(name='C', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                created_by_admin_id=admin.id, **kw)
    db.session.add(c); db.session.commit()
    return c


def test_no_criteria_everyone_eligible(db, make_product, make_user):
    from modules.contests.utils import is_eligible
    c = _contest(db, make_product, make_user)
    assert is_eligible(c, make_user()) is True


def test_min_orders(db, make_product, make_user, make_order):
    from modules.contests.utils import is_eligible
    c = _contest(db, make_product, make_user, eligibility_min_orders=2)
    u = make_user()
    assert is_eligible(c, u) is False
    make_order(u); make_order(u)
    assert is_eligible(c, u) is True


def test_cancelled_orders_excluded(db, make_product, make_user, make_order):
    from modules.contests.utils import is_eligible
    c = _contest(db, make_product, make_user, eligibility_min_orders=1)
    u = make_user()
    make_order(u, status='anulowane')
    assert is_eligible(c, u) is False


def test_min_total_value(db, make_product, make_user, make_order):
    from modules.contests.utils import is_eligible
    c = _contest(db, make_product, make_user, eligibility_min_total_value=300)
    u = make_user()
    make_order(u, total_amount=100); make_order(u, total_amount=150)
    assert is_eligible(c, u) is False
    make_order(u, total_amount=100)
    assert is_eligible(c, u) is True


def test_active_within_days(db, make_product, make_user, make_order):
    from modules.contests.utils import is_eligible
    c = _contest(db, make_product, make_user, eligibility_active_within_days=30)
    u = make_user()
    make_order(u, created_at=get_local_now() - timedelta(days=60))
    assert is_eligible(c, u) is False
    make_order(u, created_at=get_local_now() - timedelta(days=5))
    assert is_eligible(c, u) is True


def test_and_combination(db, make_product, make_user, make_order):
    from modules.contests.utils import is_eligible
    c = _contest(db, make_product, make_user,
                 eligibility_min_orders=2, eligibility_active_within_days=30)
    u = make_user()
    make_order(u, created_at=get_local_now() - timedelta(days=5))  # 1 zamówienie, świeże
    assert is_eligible(c, u) is False   # brak progu 2
    make_order(u, created_at=get_local_now() - timedelta(days=5))
    assert is_eligible(c, u) is True
```

- [ ] **Step 2: Uruchom — FAIL (brak `is_eligible`)**

Run: `python3 -m pytest tests/test_contests_eligibility.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_eligible'`.

- [ ] **Step 3: Zaimplementuj `is_eligible` w `modules/contests/utils.py`**

```python
from datetime import timedelta

from sqlalchemy import func

from extensions import db
from modules.orders.models import Order, get_local_now


def _orders_base(user_id):
    """Bazowe zapytanie o realne zamówienia (bez anulowanych)."""
    return Order.query.filter(Order.user_id == user_id, Order.status != 'anulowane')


def is_eligible(contest, user):
    """Łączy aktywne kryteria (AND). Puste kryterium = pomijane."""
    uid = user.id

    if contest.eligibility_min_orders:
        count = _orders_base(uid).count()
        if count < contest.eligibility_min_orders:
            return False

    if contest.eligibility_min_total_value:
        total = db.session.query(func.coalesce(func.sum(Order.total_amount), 0)) \
            .filter(Order.user_id == uid, Order.status != 'anulowane').scalar()
        if float(total or 0) < float(contest.eligibility_min_total_value):
            return False

    if contest.eligibility_active_within_days:
        cutoff = get_local_now() - timedelta(days=contest.eligibility_active_within_days)
        recent = _orders_base(uid).filter(Order.created_at >= cutoff).count()
        if recent == 0:
            return False

    return True
```

- [ ] **Step 4: Uruchom — PASS**

Run: `python3 -m pytest tests/test_contests_eligibility.py -v`
Expected: PASS (6 testów).

- [ ] **Step 5: Commit**

```bash
git add modules/contests/utils.py tests/test_contests_eligibility.py
git commit -m "feat(contests): eligibility AND (orders/value/recency, bez anulowanych)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Losy, pula, cooldown, stan spinów

**Files:**
- Modify: `modules/contests/utils.py`
- Test: `tests/test_contests_tickets.py`

- [ ] **Step 1: Testy**

```python
# tests/test_contests_tickets.py
from datetime import timedelta
from modules.orders.models import get_local_now


def _active_contest(db, make_product, make_user, **kw):
    from modules.contests.models import Contest
    admin = make_user(role='admin'); prod = make_product()
    c = Contest(name='C', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                status='aktywny', created_by_admin_id=admin.id, **kw)
    db.session.add(c); db.session.commit()
    return c


def _spin(db, c, u, tickets, when=None):
    from modules.contests.models import ContestSpin
    s = ContestSpin(contest_id=c.id, user_id=u.id, tickets_won=tickets)
    db.session.add(s); db.session.commit()
    if when is not None:
        s.created_at = when; db.session.commit()
    return s


def test_user_tickets_and_pool(db, make_product, make_user):
    from modules.contests.utils import get_user_tickets, get_pool
    c = _active_contest(db, make_product, make_user)
    a, b = make_user(), make_user()
    _spin(db, c, a, 20); _spin(db, c, a, 5); _spin(db, c, b, 30)
    assert get_user_tickets(c, a) == 25
    assert get_pool(c) == 55


def test_next_spin_at_cooldown(db, make_product, make_user):
    from modules.contests.utils import get_next_spin_at, can_spin
    c = _active_contest(db, make_product, make_user, cooldown_minutes=60)
    u = make_user()
    assert get_next_spin_at(c, u) is None       # brak spinów => można od razu
    _spin(db, c, u, 10, when=get_local_now())
    nxt = get_next_spin_at(c, u)
    assert nxt is not None and nxt > get_local_now()
    assert can_spin(c, u) is False              # w cooldownie


def test_spins_open(db, make_product, make_user):
    from modules.contests.utils import spins_open
    c = _active_contest(db, make_product, make_user)
    assert spins_open(c) is True
    c.ends_at = get_local_now() - timedelta(minutes=1); db.session.commit()
    assert spins_open(c) is False
    c.ends_at = None; c.status = 'szkic'; db.session.commit()
    assert spins_open(c) is False
```

- [ ] **Step 2: Uruchom — FAIL**

Run: `python3 -m pytest tests/test_contests_tickets.py -v`
Expected: FAIL — brak `get_user_tickets`.

- [ ] **Step 3: Dopisz funkcje do `modules/contests/utils.py`**

```python
def get_user_tickets(contest, user):
    from modules.contests.models import ContestSpin
    total = db.session.query(func.coalesce(func.sum(ContestSpin.tickets_won), 0)) \
        .filter(ContestSpin.contest_id == contest.id,
                ContestSpin.user_id == user.id).scalar()
    return int(total or 0)


def get_pool(contest):
    from modules.contests.models import ContestSpin
    total = db.session.query(func.coalesce(func.sum(ContestSpin.tickets_won), 0)) \
        .filter(ContestSpin.contest_id == contest.id).scalar()
    return int(total or 0)


def get_last_spin_at(contest, user):
    from modules.contests.models import ContestSpin
    return db.session.query(func.max(ContestSpin.created_at)) \
        .filter(ContestSpin.contest_id == contest.id,
                ContestSpin.user_id == user.id).scalar()


def get_next_spin_at(contest, user):
    last = get_last_spin_at(contest, user)
    if last is None:
        return None
    return last + timedelta(minutes=contest.cooldown_minutes)


def spins_open(contest):
    if contest.status != 'aktywny':
        return False
    if contest.ends_at is not None and get_local_now() >= contest.ends_at:
        return False
    return True


def can_spin(contest, user):
    if not spins_open(contest):
        return False
    if not is_eligible(contest, user):
        return False
    nxt = get_next_spin_at(contest, user)
    if nxt is not None and get_local_now() < nxt:
        return False
    return True


def get_active_contest():
    from modules.contests.models import Contest
    return Contest.query.filter_by(status='aktywny').first()
```

- [ ] **Step 4: Uruchom — PASS**

Run: `python3 -m pytest tests/test_contests_tickets.py -v`
Expected: PASS (3 testy).

- [ ] **Step 5: Commit**

```bash
git add modules/contests/utils.py tests/test_contests_tickets.py
git commit -m "feat(contests): losy/pula/cooldown/can_spin/active_contest

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Losowanie zwycięzców (ważone, bez powtórzeń, idempotentne)

**Files:**
- Modify: `modules/contests/utils.py`
- Test: `tests/test_contests_draw.py`

- [ ] **Step 1: Testy**

```python
# tests/test_contests_draw.py
import random


def _contest(db, make_product, make_user, **kw):
    from modules.contests.models import Contest
    admin = make_user(role='admin'); prod = make_product()
    c = Contest(name='C', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                status='aktywny', created_by_admin_id=admin.id, **kw)
    db.session.add(c); db.session.commit()
    return c


def _spin(db, c, u, t):
    from modules.contests.models import ContestSpin
    db.session.add(ContestSpin(contest_id=c.id, user_id=u.id, tickets_won=t))
    db.session.commit()


def test_draw_single_winner_sets_status(db, make_product, make_user):
    from modules.contests.utils import draw_winners
    c = _contest(db, make_product, make_user, num_winners=1)
    u = make_user(); _spin(db, c, u, 10)
    winners = draw_winners(c, rng=random.Random(1))
    assert len(winners) == 1
    assert winners[0].user_id == u.id
    assert winners[0].place == 1
    assert winners[0].tickets_at_draw == 10
    assert c.status == 'rozlosowany'


def test_draw_no_repeats_multiple_winners(db, make_product, make_user):
    from modules.contests.utils import draw_winners
    c = _contest(db, make_product, make_user, num_winners=3)
    us = [make_user() for _ in range(5)]
    for i, u in enumerate(us):
        _spin(db, c, u, 10 + i)
    winners = draw_winners(c, rng=random.Random(7))
    uids = [w.user_id for w in winners]
    assert len(winners) == 3
    assert len(set(uids)) == 3   # bez powtórzeń
    assert [w.place for w in winners] == [1, 2, 3]


def test_draw_more_winners_than_participants(db, make_product, make_user):
    from modules.contests.utils import draw_winners
    c = _contest(db, make_product, make_user, num_winners=5)
    a, b = make_user(), make_user()
    _spin(db, c, a, 10); _spin(db, c, b, 10)
    winners = draw_winners(c, rng=random.Random(3))
    assert len(winners) == 2   # tylu ilu uczestników


def test_draw_is_idempotent(db, make_product, make_user):
    from modules.contests.utils import draw_winners
    c = _contest(db, make_product, make_user, num_winners=1)
    u = make_user(); _spin(db, c, u, 10)
    first = draw_winners(c, rng=random.Random(1))
    again = draw_winners(c, rng=random.Random(999))
    assert [w.id for w in first] == [w.id for w in again]


def test_weighting_is_proportional(db, make_product, make_user):
    """Statystyka: uczestnik z 90% losów wygrywa ~większość losowań."""
    from modules.contests.models import Contest, ContestWinner
    from modules.contests.utils import draw_winners
    wins_big = 0
    rng = random.Random(123)
    for _ in range(200):
        c = _contest(db, make_product, make_user, num_winners=1)
        big, small = make_user(), make_user()
        _spin(db, c, big, 90); _spin(db, c, small, 10)
        winners = draw_winners(c, rng=rng)
        if winners[0].user_id == big.id:
            wins_big += 1
    assert wins_big > 150   # ~90% oczekiwane, próg z zapasem
```

- [ ] **Step 2: Uruchom — FAIL**

Run: `python3 -m pytest tests/test_contests_draw.py -v`
Expected: FAIL — brak `draw_winners`.

- [ ] **Step 3: Zaimplementuj `draw_winners`**

```python
import random as _random


def _participants(contest):
    """Lista (user, tickets) z losami > 0 i wciąż spełniających eligibility."""
    from modules.contests.models import ContestSpin
    from modules.auth.models import User
    rows = db.session.query(ContestSpin.user_id,
                            func.sum(ContestSpin.tickets_won)) \
        .filter(ContestSpin.contest_id == contest.id) \
        .group_by(ContestSpin.user_id).all()
    out = []
    for uid, total in rows:
        total = int(total or 0)
        if total <= 0:
            continue
        user = User.query.get(uid)
        if user and is_eligible(contest, user):
            out.append((user, total))
    return out


def draw_winners(contest, rng=None):
    """Autorytatywne, ważone losowanie bez powtórzeń. Idempotentne."""
    from modules.contests.models import ContestWinner
    if contest.status == 'rozlosowany':
        return ContestWinner.query.filter_by(contest_id=contest.id) \
            .order_by(ContestWinner.place).all()

    rng = rng or _random.SystemRandom()
    participants = _participants(contest)
    pool_total = sum(t for _, t in participants)
    n = min(contest.num_winners, len(participants))

    remaining = list(participants)
    winners = []
    for place in range(1, n + 1):
        total = sum(t for _, t in remaining)
        pick = rng.uniform(0, total)
        acc = 0
        chosen_idx = len(remaining) - 1
        for idx, (_, t) in enumerate(remaining):
            acc += t
            if pick <= acc:
                chosen_idx = idx
                break
        user, tickets = remaining.pop(chosen_idx)
        chance = round(tickets / pool_total * 100, 3) if pool_total else 0
        w = ContestWinner(
            contest_id=contest.id, user_id=user.id, place=place,
            tickets_at_draw=tickets, chance_pct=chance,
            prize_product_id=contest.prize_product_id, drawn_at=get_local_now(),
        )
        db.session.add(w)
        winners.append(w)

    contest.status = 'rozlosowany'
    db.session.commit()

    for w in winners:
        _notify_winner(contest, w)   # zdefiniowane w Task 9
    return winners
```

- [ ] **Step 4: Tymczasowy stub `_notify_winner`**

Dodaj na końcu `utils.py` (zostanie rozbudowany w Tasku 9):

```python
def _notify_winner(contest, winner):
    """Powiadomienie + e-mail. Pełna implementacja w Task 9."""
    return None
```

- [ ] **Step 5: Uruchom — PASS**

Run: `python3 -m pytest tests/test_contests_draw.py -v`
Expected: PASS (5 testów).

- [ ] **Step 6: Commit**

```bash
git add modules/contests/utils.py tests/test_contests_draw.py
git commit -m "feat(contests): draw_winners ważone bez powtórzeń + idempotencja

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Rejestracja blueprintu + admin CRUD (lista, formularz, aktywacja)

**Files:**
- Modify: `app.py` (rejestracja), `modules/contests/routes.py`
- Create: `modules/contests/forms.py`
- Test: `tests/test_contests_routes_admin.py`

- [ ] **Step 1: Zarejestruj blueprint w `app.py`**

W `register_blueprints()`, po `app.register_blueprint(achievements_bp, ...)` i przed `shop_bp`:

```python
from modules.contests import contests_bp
app.register_blueprint(contests_bp)
```

- [ ] **Step 2: Testy admin CRUD**

```python
# tests/test_contests_routes_admin.py
def _admin(make_user): return make_user(role='admin')


def test_list_requires_admin(client, make_user, login):
    login(make_user(role='client'))
    assert client.get('/admin/konkursy').status_code == 403


def test_create_contest(client, db, make_user, make_product, login):
    from modules.contests.models import Contest
    login(_admin(make_user))
    prod = make_product()
    resp = client.post('/admin/konkursy/nowy', data={
        'name': 'Klawiatura', 'prize_product_id': prod.id,
        'num_winners': 1, 'ticket_min': 1, 'ticket_max': 50,
        'cooldown_minutes': 1440, 'eligibility_min_orders': 1,
    }, follow_redirects=True)
    assert resp.status_code == 200
    c = Contest.query.filter_by(name='Klawiatura').first()
    assert c is not None and c.status == 'szkic'


def test_activate_blocks_second_active(client, db, make_user, make_product, login):
    from modules.contests.models import Contest
    login(_admin(make_user)); prod = make_product()
    c1 = Contest(name='A', prize_product_id=prod.id, ticket_min=1, ticket_max=50, status='aktywny')
    c2 = Contest(name='B', prize_product_id=prod.id, ticket_min=1, ticket_max=50, status='szkic')
    db.session.add_all([c1, c2]); db.session.commit()
    resp = client.post(f'/admin/konkursy/{c2.id}/aktywuj', follow_redirects=True)
    db.session.refresh(c2)
    assert c2.status == 'szkic'   # zablokowane — już jest aktywny
```

- [ ] **Step 3: Uruchom — FAIL**

Run: `python3 -m pytest tests/test_contests_routes_admin.py -v`
Expected: FAIL (404/brak route).

- [ ] **Step 4: Utwórz `modules/contests/forms.py`**

```python
from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, IntegerField, DecimalField,
                     DateTimeLocalField, SelectField)
from wtforms.validators import DataRequired, NumberRange, Optional


class ContestForm(FlaskForm):
    name = StringField('Nazwa', validators=[DataRequired()])
    description = TextAreaField('Opis nagrody', validators=[Optional()])
    image_path = StringField('Grafika', validators=[Optional()])
    prize_product_id = IntegerField('Produkt-nagroda', validators=[Optional()])
    num_winners = IntegerField('Liczba zwycięzców', default=1, validators=[NumberRange(min=1)])
    ticket_min = IntegerField('Min losów', default=1, validators=[NumberRange(min=1)])
    ticket_max = IntegerField('Max losów', default=50, validators=[NumberRange(min=1)])
    cooldown_minutes = IntegerField('Cooldown (min)', default=1440, validators=[NumberRange(min=1)])
    eligibility_min_orders = IntegerField('Min. zamówień', validators=[Optional(), NumberRange(min=0)])
    eligibility_min_total_value = DecimalField('Min. wartość', validators=[Optional(), NumberRange(min=0)])
    eligibility_active_within_days = IntegerField('Aktywny w dniach', validators=[Optional(), NumberRange(min=0)])
    ends_at = DateTimeLocalField('Koniec', format='%Y-%m-%dT%H:%M', validators=[Optional()])

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        if self.ticket_max.data < self.ticket_min.data:
            self.ticket_max.errors.append('Max musi być ≥ min.')
            return False
        return True
```

- [ ] **Step 5: Dopisz routes admin do `modules/contests/routes.py`**

```python
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from sqlalchemy import func, distinct

from extensions import db
from utils.decorators import role_required
from modules.contests import contests_bp
from modules.contests.models import Contest, ContestSpin, ContestWinner
from modules.contests.forms import ContestForm
from modules.contests import utils as cu


def _count_participants(contest):
    return db.session.query(func.count(distinct(ContestSpin.user_id))) \
        .filter(ContestSpin.contest_id == contest.id).scalar() or 0


@contests_bp.route('/admin/konkursy')
@login_required
@role_required('admin', 'mod')
def admin_list():
    contests = Contest.query.order_by(Contest.created_at.desc()).all()
    data = [{'c': c, 'pool': cu.get_pool(c),
             'participants': _count_participants(c)} for c in contests]
    return render_template('admin/contests/list.html', items=data)


def _apply_form(form, contest):
    for f in ['name', 'description', 'image_path', 'prize_product_id', 'num_winners',
              'ticket_min', 'ticket_max', 'cooldown_minutes', 'eligibility_min_orders',
              'eligibility_min_total_value', 'eligibility_active_within_days', 'ends_at']:
        setattr(contest, f, getattr(form, f).data)


@contests_bp.route('/admin/konkursy/nowy', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def admin_new():
    form = ContestForm()
    if form.validate_on_submit():
        from flask_login import current_user
        c = Contest(status='szkic', created_by_admin_id=current_user.id)
        _apply_form(form, c)
        db.session.add(c); db.session.commit()
        flash('Konkurs utworzony.', 'success')
        return redirect(url_for('contests.admin_list'))
    return render_template('admin/contests/form.html', form=form, contest=None)


@contests_bp.route('/admin/konkursy/<int:cid>/edytuj', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def admin_edit(cid):
    c = Contest.query.get_or_404(cid)
    form = ContestForm(obj=c)
    if form.validate_on_submit():
        _apply_form(form, c); db.session.commit()
        flash('Zapisano.', 'success')
        return redirect(url_for('contests.admin_list'))
    return render_template('admin/contests/form.html', form=form, contest=c)


@contests_bp.route('/admin/konkursy/<int:cid>/aktywuj', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_activate(cid):
    c = Contest.query.get_or_404(cid)
    if cu.get_active_contest() is not None:
        flash('Inny konkurs jest już aktywny.', 'error')
        return redirect(url_for('contests.admin_list'))
    c.status = 'aktywny'; db.session.commit()
    flash('Konkurs aktywny.', 'success')
    return redirect(url_for('contests.admin_list'))
```

> Uproszczenie liczenia uczestników w `admin_list` możesz wyciągnąć do helpera `cu.count_participants(contest)` — opcjonalne, ale czytelniejsze.

- [ ] **Step 6: Minimalne szablony (by testy follow_redirects=True przeszły)**

`templates/admin/contests/list.html`:

```html
{% extends "admin/base_admin.html" %}
{% block title %}Konkursy{% endblock %}
{% block content %}
<h1>Konkursy</h1>
<a href="{{ url_for('contests.admin_new') }}">Nowy konkurs</a>
<table>
  {% for it in items %}
  <tr><td>{{ it.c.name }}</td><td>{{ it.c.status }}</td>
      <td>{{ it.participants }}</td><td>{{ it.pool }}</td></tr>
  {% endfor %}
</table>
{% endblock %}
```

`templates/admin/contests/form.html`:

```html
{% extends "admin/base_admin.html" %}
{% block title %}Konkurs — formularz{% endblock %}
{% block content %}
<form method="post">
  {{ form.hidden_tag() }}
  {{ form.name() }} {{ form.prize_product_id() }} {{ form.num_winners() }}
  {{ form.ticket_min() }} {{ form.ticket_max() }} {{ form.cooldown_minutes() }}
  {{ form.eligibility_min_orders() }} {{ form.eligibility_min_total_value() }}
  {{ form.eligibility_active_within_days() }} {{ form.ends_at() }}
  <button type="submit">Zapisz</button>
</form>
{% endblock %}
```

(Pełny, ostylowany formularz powstaje w Tasku 11.)

- [ ] **Step 7: Uruchom — PASS**

Run: `python3 -m pytest tests/test_contests_routes_admin.py -v`
Expected: PASS (3 testy).

- [ ] **Step 8: Commit**

```bash
git add app.py modules/contests/routes.py modules/contests/forms.py templates/admin/contests/ tests/test_contests_routes_admin.py
git commit -m "feat(contests): rejestracja bp + admin CRUD + aktywacja (1 aktywny)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Admin — ekran i akcja losowania

**Files:**
- Modify: `modules/contests/routes.py`
- Create: `templates/admin/contests/draw.html`, `templates/admin/contests/results.html`
- Test: dopisz do `tests/test_contests_routes_admin.py`

- [ ] **Step 1: Testy akcji losowania**

```python
# dopisz do tests/test_contests_routes_admin.py
def test_draw_endpoint(client, db, make_user, make_product, login):
    from modules.contests.models import Contest, ContestSpin, ContestWinner
    login(make_user(role='admin')); prod = make_product()
    c = Contest(name='A', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, status='aktywny')
    db.session.add(c); db.session.commit()
    u = make_user()
    db.session.add(ContestSpin(contest_id=c.id, user_id=u.id, tickets_won=10))
    db.session.commit()
    resp = client.post(f'/admin/konkursy/{c.id}/losuj')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert len(body['winners']) == 1
    assert ContestWinner.query.filter_by(contest_id=c.id).count() == 1
    db.session.refresh(c); assert c.status == 'rozlosowany'


def test_draw_blocked_when_spins_open(client, db, make_user, make_product, login):
    from datetime import timedelta
    from modules.orders.models import get_local_now
    from modules.contests.models import Contest, ContestSpin
    login(make_user(role='admin')); prod = make_product()
    c = Contest(name='A', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                status='aktywny', ends_at=get_local_now() + timedelta(hours=1))
    db.session.add(c); db.session.commit()
    db.session.add(ContestSpin(contest_id=c.id, user_id=make_user().id, tickets_won=5))
    db.session.commit()
    resp = client.post(f'/admin/konkursy/{c.id}/losuj')
    assert resp.get_json()['success'] is False   # spiny jeszcze otwarte
```

- [ ] **Step 2: Uruchom — FAIL**

Run: `python3 -m pytest tests/test_contests_routes_admin.py::test_draw_endpoint -v`
Expected: FAIL (404).

- [ ] **Step 3: Dopisz routes losowania**

```python
from flask import jsonify
from modules.contests.models import ContestSpin


@contests_bp.route('/admin/konkursy/<int:cid>/losowanie')
@login_required
@role_required('admin', 'mod')
def admin_draw_screen(cid):
    c = Contest.query.get_or_404(cid)
    return render_template('admin/contests/draw.html', contest=c,
                           pool=cu.get_pool(c))


@contests_bp.route('/admin/konkursy/<int:cid>/losuj', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_draw(cid):
    c = Contest.query.get_or_404(cid)
    if c.status == 'aktywny' and cu.spins_open(c):
        return jsonify(success=False,
                       error='Spiny wciąż otwarte — zakończ konkurs (ends_at) przed losowaniem.'), 200
    if c.status not in ('aktywny', 'rozlosowany'):
        return jsonify(success=False, error='Konkurs nie jest aktywny.'), 200

    winners = cu.draw_winners(c)
    pool = cu.get_pool(c)
    # pełne rozbicie puli dla animacji (tylko admin)
    breakdown = []
    for user, tickets in cu._participants(c):
        breakdown.append({
            'user_id': user.id,
            'name': (user.first_name or user.email),
            'tickets': tickets,
            'pct': round(tickets / pool * 100, 2) if pool else 0,
        })
    breakdown.sort(key=lambda x: x['tickets'], reverse=True)
    return jsonify(success=True, pool=pool, breakdown=breakdown, winners=[{
        'user_id': w.user_id, 'place': w.place, 'tickets': w.tickets_at_draw,
        'pct': float(w.chance_pct or 0),
        'name': (w.user.first_name or w.user.email),
    } for w in winners])


@contests_bp.route('/admin/konkursy/<int:cid>/wyniki')
@login_required
@role_required('admin', 'mod')
def admin_results(cid):
    c = Contest.query.get_or_404(cid)
    winners = ContestWinner.query.filter_by(contest_id=cid).order_by(ContestWinner.place).all()
    return render_template('admin/contests/results.html', contest=c, winners=winners)
```

- [ ] **Step 4: Minimalne szablony `draw.html` i `results.html`**

`templates/admin/contests/draw.html`:

```html
{% extends "admin/base_admin.html" %}
{% block title %}Losowanie — {{ contest.name }}{% endblock %}
{% block content %}
<div id="drawRoot" data-contest-id="{{ contest.id }}"
     data-draw-url="{{ url_for('contests.admin_draw', cid=contest.id) }}">
  <h1>Losowanie: {{ contest.name }}</h1>
  <button id="btnDraw">LOSUJ ZWYCIĘZCĘ</button>
  <div id="drawResult"></div>
</div>
{% endblock %}
```

`templates/admin/contests/results.html`:

```html
{% extends "admin/base_admin.html" %}
{% block title %}Wyniki — {{ contest.name }}{% endblock %}
{% block content %}
<h1>Wyniki: {{ contest.name }}</h1>
<ol>
  {% for w in winners %}
  <li>#{{ w.place }} — {{ w.user.first_name or w.user.email }} ({{ w.tickets_at_draw }} losów, {{ w.chance_pct }}%)</li>
  {% endfor %}
</ol>
{% endblock %}
```

(Animowany ekran losowania powstaje w Tasku 11.)

- [ ] **Step 5: Uruchom — PASS**

Run: `python3 -m pytest tests/test_contests_routes_admin.py -v`
Expected: PASS (5 testów łącznie).

- [ ] **Step 6: Commit**

```bash
git add modules/contests/routes.py templates/admin/contests/ tests/test_contests_routes_admin.py
git commit -m "feat(contests): admin losowanie (endpoint + blokady) + wyniki

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Klient — strona konkursu i spin

**Files:**
- Modify: `modules/contests/routes.py`
- Create: `templates/client/contest.html` (minimalny; pełny w Tasku 10)
- Test: `tests/test_contests_routes_client.py`

- [ ] **Step 1: Testy spinu**

```python
# tests/test_contests_routes_client.py
def _active(db, make_product, **kw):
    from modules.contests.models import Contest
    from modules.products.models import Product
    prod = Product.query.first() or None
    c = Contest(name='K', ticket_min=5, ticket_max=5, status='aktywny',
                prize_product_id=(prod.id if prod else None), **kw)
    db.session.add(c); db.session.commit()
    return c


def test_spin_requires_eligibility(client, db, make_user, make_product, login):
    c = _active(db, make_product, eligibility_min_orders=1)
    u = make_user(); login(u)
    resp = client.post('/konkurs/spin')
    assert resp.get_json()['success'] is False   # brak zamówień


def test_spin_grants_tickets_in_range(client, db, make_user, make_product, make_order, login):
    from modules.contests.models import ContestSpin
    c = _active(db, make_product, eligibility_min_orders=1)  # min=max=5
    u = make_user(); make_order(u); login(u)
    resp = client.post('/konkurs/spin')
    body = resp.get_json()
    assert body['success'] is True
    assert body['tickets_won'] == 5
    assert body['my_total'] == 5
    assert ContestSpin.query.filter_by(contest_id=c.id, user_id=u.id).count() == 1


def test_spin_blocked_during_cooldown(client, db, make_user, make_product, make_order, login):
    c = _active(db, make_product, eligibility_min_orders=1, cooldown_minutes=60)
    u = make_user(); make_order(u); login(u)
    assert client.post('/konkurs/spin').get_json()['success'] is True
    second = client.post('/konkurs/spin').get_json()
    assert second['success'] is False   # cooldown
```

- [ ] **Step 2: Uruchom — FAIL**

Run: `python3 -m pytest tests/test_contests_routes_client.py -v`
Expected: FAIL (404).

- [ ] **Step 3: Dopisz routes klienta**

```python
from flask_login import current_user


@contests_bp.route('/konkurs')
@login_required
def client_contest():
    c = cu.get_active_contest()
    ctx = cu.widget_context(c, current_user) if c else None
    return render_template('client/contest.html', contest=c, ctx=ctx)


@contests_bp.route('/konkurs/spin', methods=['POST'])
@login_required
def client_spin():
    c = cu.get_active_contest()
    if c is None:
        return jsonify(success=False, error='Brak aktywnego konkursu.'), 200
    if not cu.spins_open(c):
        return jsonify(success=False, error='Konkurs nie przyjmuje losów.'), 200
    if not cu.is_eligible(c, current_user):
        return jsonify(success=False, error='Nie spełniasz warunków udziału.'), 200
    if not cu.can_spin(c, current_user):
        return jsonify(success=False, error='Następny los dostępny później.',
                       next_spin_at=cu.get_next_spin_at(c, current_user).isoformat()
                       if cu.get_next_spin_at(c, current_user) else None), 200

    import random
    tickets = random.SystemRandom().randint(c.ticket_min, c.ticket_max)
    db.session.add(ContestSpin(contest_id=c.id, user_id=current_user.id, tickets_won=tickets))
    db.session.commit()
    nxt = cu.get_next_spin_at(c, current_user)
    return jsonify(success=True, tickets_won=tickets,
                   my_total=cu.get_user_tickets(c, current_user),
                   next_spin_at=nxt.isoformat() if nxt else None)
```

- [ ] **Step 4: Dodaj helper `widget_context` do `utils.py`**

```python
def widget_context(contest, user):
    """Dane dla widgetu/strony klienta (bez puli i %)."""
    if contest is None:
        return None
    nxt = get_next_spin_at(contest, user)
    return {
        'contest': contest,
        'my_tickets': get_user_tickets(contest, user),
        'eligible': is_eligible(contest, user),
        'can_spin': can_spin(contest, user),
        'next_spin_at': nxt.isoformat() if nxt else None,
        'spins_open': spins_open(contest),
    }
```

- [ ] **Step 5: Minimalny `templates/client/contest.html`**

```html
{% extends "client/base_client.html" %}
{% block title %}Konkurs - ThunderOrders{% endblock %}
{% block content %}
{% if contest %}
  <h1>{{ contest.name }}</h1>
  <p>Twoich losów: <b id="myTickets">{{ ctx.my_tickets }}</b></p>
{% else %}
  <p>Aktualnie brak aktywnego konkursu.</p>
{% endif %}
{% endblock %}
```

(Pełna strona + spinner w Tasku 10.)

- [ ] **Step 6: Uruchom — PASS**

Run: `python3 -m pytest tests/test_contests_routes_client.py -v`
Expected: PASS (3 testy).

- [ ] **Step 7: Commit**

```bash
git add modules/contests/routes.py modules/contests/utils.py templates/client/contest.html tests/test_contests_routes_client.py
git commit -m "feat(contests): strona konkursu + endpoint spin (cooldown/eligibility/zakres)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Powiadomienia + e-mail do zwycięzcy

**Files:**
- Modify: `modules/contests/utils.py` (`_notify_winner`), `utils/email_sender.py`
- Create: `templates/emails/contest_win.html`, `templates/emails/contest_win.txt`
- Test: `tests/test_contests_email.py`

- [ ] **Step 1: Test — powiadomienie in-app + wywołanie maila**

```python
# tests/test_contests_email.py
def test_winner_gets_notification_and_email(db, make_user, make_product, monkeypatch):
    import modules.contests.utils as cu
    from modules.contests.models import Contest, ContestSpin
    from modules.notifications.models import Notification

    sent = []
    monkeypatch.setattr(cu, 'send_contest_win_email',
                        lambda **kw: sent.append(kw), raising=False)

    prod = make_product(name='Klawiatura')
    c = Contest(name='Konkurs', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, status='aktywny')
    db.session.add(c); db.session.commit()
    u = make_user(email='winner@example.com')
    db.session.add(ContestSpin(contest_id=c.id, user_id=u.id, tickets_won=10))
    db.session.commit()

    import random
    cu.draw_winners(c, rng=random.Random(1))

    assert Notification.query.filter_by(user_id=u.id,
                                        notification_type='contest_win').count() == 1
    assert len(sent) == 1
    assert sent[0]['user_email'] == 'winner@example.com'
```

- [ ] **Step 2: Uruchom — FAIL**

Run: `python3 -m pytest tests/test_contests_email.py -v`
Expected: FAIL (brak Notification / `send_contest_win_email`).

- [ ] **Step 3: Dodaj `send_contest_win_email` w `utils/email_sender.py`**

Wzoruj się na istniejących senderach (`send_order_confirmation_email`). Dopisz:

```python
def send_contest_win_email(user_email, user_name, contest_name, prize_name, url):
    return send_email(
        to=user_email,
        subject=f'Wygrałeś w konkursie {contest_name} - ThunderOrders',
        template='contest_win',
        user_name=user_name,
        contest_name=contest_name,
        prize_name=prize_name,
        url=url,
    )
```

- [ ] **Step 4: Szablony e-mail**

`templates/emails/contest_win.html`:

```html
<p>Cześć {{ user_name or '' }}!</p>
<p>Gratulacje — wygrałeś w konkursie <strong>{{ contest_name }}</strong>!</p>
<p>Twoja nagroda: <strong>{{ prize_name }}</strong>.</p>
<p>Szczegóły: <a href="{{ url }}">{{ url }}</a></p>
<p>Pozdrawiamy,<br>ThunderOrders</p>
```

`templates/emails/contest_win.txt`:

```text
Cześć {{ user_name or '' }}!

Gratulacje — wygrałeś w konkursie {{ contest_name }}!
Twoja nagroda: {{ prize_name }}.
Szczegóły: {{ url }}

Pozdrawiamy,
ThunderOrders
```

- [ ] **Step 5: Zaimplementuj `_notify_winner` w `utils.py`**

Zastąp stub z Taska 5:

```python
from flask import url_for

from utils.email_sender import send_contest_win_email   # import na górze pliku


def _notify_winner(contest, winner):
    from modules.notifications.models import Notification
    from modules.auth.models import User
    user = User.query.get(winner.user_id)
    prize_name = contest.prize_product.name if contest.prize_product else 'nagroda'
    try:
        link = url_for('contests.client_contest', _external=True)
    except Exception:
        link = '/konkurs'

    db.session.add(Notification(
        user_id=winner.user_id,
        title='Wygrałeś w konkursie!',
        body=f'Twoja nagroda: {prize_name}.',
        url=link,
        notification_type='contest_win',
    ))
    db.session.commit()

    try:
        send_contest_win_email(
            user_email=user.email,
            user_name=getattr(user, 'first_name', None),
            contest_name=contest.name,
            prize_name=prize_name,
            url=link,
        )
    except Exception:
        pass   # mail nigdy nie blokuje losowania
```

> Uwaga: import `send_contest_win_email` jako atrybut modułu `cu` (test go monkeypatchuje przez `cu.send_contest_win_email`). Importuj go na poziomie modułu `utils.py` (`from utils.email_sender import send_contest_win_email`), aby `monkeypatch.setattr(cu, 'send_contest_win_email', ...)` zadziałał.

- [ ] **Step 6: Uruchom — PASS**

Run: `python3 -m pytest tests/test_contests_email.py -v`
Expected: PASS.

- [ ] **Step 7: Pełna regresja backendu**

Run: `python3 -m pytest tests/ -v`
Expected: wszystkie testy contests PASS (modele, eligibility, tickets, draw, routes admin/client, email).

- [ ] **Step 8: Commit**

```bash
git add modules/contests/utils.py utils/email_sender.py templates/emails/contest_win.* tests/test_contests_email.py
git commit -m "feat(contests): powiadomienie in-app + e-mail do zwycięzcy

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: UI klienta — widget na dashboardzie + strona + modal ze spinnerem

**Files:**
- Modify: `modules/client/routes.py` (kontekst widgetu), `templates/client/dashboard.html` (include), `static/css/components/modals.css` (modal spinnera)
- Create: `templates/client/_contest_widget.html`, `static/css/pages/client/contest.css`, `static/js/pages/client/contest.js`
- Rewrite: `templates/client/contest.html` (pełna strona)

> UI testujemy manualnie (animacja). Każdy plik CSS ma warianty **light i dark**.

- [ ] **Step 1: Wstrzyknij kontekst widgetu do dashboardu**

W `modules/client/routes.py`, w funkcji `dashboard()`, przed `render_template(...)`:

```python
from modules.contests import utils as contest_utils
_active_contest = contest_utils.get_active_contest()
contest_widget = contest_utils.widget_context(_active_contest, current_user) if _active_contest else None
```

i dodaj do `render_template('client/dashboard.html', ..., contest_widget=contest_widget)`.

- [ ] **Step 2: Partial widgetu `templates/client/_contest_widget.html`**

```html
{% if contest_widget %}
<div class="contest-widget" id="contestWidget"
     data-spin-url="{{ url_for('contests.client_spin') }}"
     data-contest-url="{{ url_for('contests.client_contest') }}"
     data-can-spin="{{ '1' if contest_widget.can_spin else '0' }}"
     data-next-spin="{{ contest_widget.next_spin_at or '' }}"
     data-eligible="{{ '1' if contest_widget.eligible else '0' }}">
  <span class="contest-widget__badge">🎰 KONKURS TRWA</span>
  <h3 class="contest-widget__title">{{ contest_widget.contest.name }}</h3>
  <div class="contest-widget__sub">Nagroda • {{ contest_widget.contest.num_winners }} zwycięzca(ów)</div>
  <div class="contest-widget__tickets">
    <b id="widgetTickets">{{ contest_widget.my_tickets }}</b>
    <span>Twoich losów</span>
  </div>
  {% if not contest_widget.eligible %}
    <div class="contest-widget__cool">Nie spełniasz warunków udziału</div>
  {% else %}
    <button class="contest-widget__btn" id="widgetSpinBtn"
            {{ 'hidden' if not contest_widget.can_spin else '' }}>🎲 LOSUJ</button>
    <div class="contest-widget__cool" id="widgetCooldown"
         {{ 'hidden' if contest_widget.can_spin else '' }}>⏳ Następny los za <span id="widgetClock">--:--:--</span></div>
  {% endif %}
  <div class="contest-widget__hint">Pula i szanse ujawnią się przy losowaniu 🤫</div>
</div>
{% endif %}
```

- [ ] **Step 3: Włącz partial w `templates/client/dashboard.html`**

W widocznym miejscu siatki dashboardu:

```html
{% include 'client/_contest_widget.html' %}
```

- [ ] **Step 4: `static/css/pages/client/contest.css` — widget + strona (light + dark)**

Bazuj na palecie z makiet (róż `#f093fb`, czerwony `#f5576c`, liczba `#e35ec6`). Wymagane sekcje: `.contest-widget` (karta, badge, tytuł, sub, `.contest-widget__tickets b` duża liczba `#e35ec6`, `__tickets span` 17px/700, przycisk gradientowy, `__cool` licznik), warianty `[data-theme="dark"] .contest-widget { ... }`. Dla strony `/konkurs`: hero z grafiką nagrody i opisem, duży licznik losów, przycisk. Trzymaj się wzorca z `client-ui-v3.html` w `.superpowers/brainstorm/` (zatwierdzona makieta). Przykład rdzenia:

```css
.contest-widget { background:#fff; border:1px solid #ececf3; border-radius:16px; padding:18px; position:relative; overflow:hidden; box-shadow:0 8px 26px rgba(80,40,120,.08); }
.contest-widget__badge { display:inline-block; font-size:11px; font-weight:800; color:#fff; padding:4px 11px; border-radius:999px; background:linear-gradient(135deg,#f093fb,#f5576c); }
.contest-widget__title { margin:12px 0 3px; font-size:18px; font-weight:800; }
.contest-widget__tickets b { font-size:38px; color:#e35ec6; line-height:1; }
.contest-widget__tickets span { font-size:17px; font-weight:700; opacity:.85; margin-left:9px; }
.contest-widget__btn { width:100%; margin-top:14px; padding:14px; border:0; border-radius:12px; font-weight:900; letter-spacing:.06em; font-size:16px; color:#fff; background:linear-gradient(135deg,#f093fb,#f5576c); cursor:pointer; box-shadow:0 8px 22px rgba(245,87,108,.35); }
.contest-widget__cool { width:100%; margin-top:14px; padding:14px; border-radius:12px; text-align:center; font-weight:800; background:#f4f2f8; border:1px solid #e7e4ee; color:#5b5570; }
.contest-widget__hint { margin-top:11px; text-align:center; font-size:12px; opacity:.55; }

[data-theme="dark"] .contest-widget { background:#15121c; border:1px solid rgba(240,147,251,.18); color:#fff; box-shadow:none; }
[data-theme="dark"] .contest-widget::before { content:""; position:absolute; inset:0; background:radial-gradient(120% 100% at 100% 0,rgba(240,147,251,.20),transparent 60%); pointer-events:none; }
[data-theme="dark"] .contest-widget__cool { background:rgba(255,255,255,.05); border:1px solid rgba(240,147,251,.18); color:rgba(255,255,255,.85); }
```

- [ ] **Step 5: Styl modala spinnera w `static/css/components/modals.css`**

Dopisz (light + dark) klasy z makiety `spinner-modal-v2.html`: `.contest-spin-overlay` (overlay + blur), `.contest-spin-modal`, `.contest-reel-wrap` (252px, maski góra/dół, `.contest-marker` celownik), `.contest-num` (84px, 46px font), `.contest-num.hot`, przyciski `.contest-spin-btn` (START/ZAMKNIJ gradient) i `.contest-stop-btn`, `.contest-spin-result`. Skopiuj wartości z zatwierdzonej makiety `.superpowers/brainstorm/.../spinner-modal-v2.html` i dodaj odpowiedniki light mode.

- [ ] **Step 6: `static/js/pages/client/contest.js` — spin + karuzela**

Logika: klik LOSUJ → otwórz modal (overlay), `POST /konkurs/spin` (CSRF header `X-CSRFToken` przez `getCsrfToken()`), z odpowiedzi weź `tickets_won`; uruchom karuzelę (kod z zatwierdzonej `spinner-modal-v2.html`: pionowa, w dół, losowe liczby, START rozpędza, STOP hamuje easeOutQuart do `tickets_won`); po zakończeniu zaktualizuj `#widgetTickets`/`#myTickets`, schowaj przycisk, pokaż licznik `next_spin_at` (odliczanie co 1s). Rdzeń (adaptacja makiety — `DRAWN` pochodzi z serwera, nie sztywne 37):

```javascript
function getCsrfToken() {
  var meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) return meta.getAttribute('content');
  var m = document.cookie.match(/csrf_token=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

async function requestSpin(url) {
  const r = await fetch(url, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json',
               'X-CSRFToken': getCsrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
    body: '{}'
  });
  return r.json();
}
// openModal(), runReel(targetValue, onDone) — przenieś z spinner-modal-v2.html,
// zamieniając stałą DRAWN na wartość z requestSpin().tickets_won.
// Obsłuż błąd success:false (Toast/alert) zamiast animacji.
```

Pełną mechanikę karuzeli (render(), targetSlot(), frame(), easeOutQuart, rozpęd) skopiuj 1:1 z makiety, podmieniając źródło wyniku i selektory na klasy `.contest-*`.

- [ ] **Step 7: Pełna strona `templates/client/contest.html` + wpięcie assetów**

```html
{% extends "client/base_client.html" %}
{% block title %}Konkurs - ThunderOrders{% endblock %}
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/client/contest.css') }}">
{% endblock %}
{% block content %}
{% if contest %}
<div class="contest-page" id="contestPage"
     data-spin-url="{{ url_for('contests.client_spin') }}"
     data-can-spin="{{ '1' if ctx.can_spin else '0' }}"
     data-next-spin="{{ ctx.next_spin_at or '' }}"
     data-eligible="{{ '1' if ctx.eligible else '0' }}">
  <div class="contest-hero">
    {% if contest.image_path %}<img class="contest-hero__img" src="{{ contest.image_path }}" alt="">{% endif %}
    <div>
      <span class="contest-widget__badge">KONKURS TRWA</span>
      <h1>{{ contest.name }}</h1>
      <p>{{ contest.description or '' }}</p>
      {% if contest.ends_at %}<p>Koniec: {{ contest.ends_at.strftime('%d.%m.%Y %H:%M') }}</p>{% endif %}
    </div>
  </div>
  <div class="contest-spinbox">
    <div>Masz teraz</div>
    <div class="contest-reveal"><b id="myTickets">{{ ctx.my_tickets }}</b> losów</div>
    {% if ctx.eligible %}
      <button class="contest-widget__btn" id="pageSpinBtn" {{ 'hidden' if not ctx.can_spin else '' }}>🎲 LOSUJ</button>
      <div class="contest-widget__cool" id="pageCooldown" {{ 'hidden' if ctx.can_spin else '' }}>⏳ Następny los za <span id="pageClock">--:--:--</span></div>
    {% else %}
      <div class="contest-widget__cool">Nie spełniasz warunków udziału w konkursie</div>
    {% endif %}
  </div>
</div>
{% else %}
<p class="contest-empty">Aktualnie brak aktywnego konkursu.</p>
{% endif %}
{% endblock %}
{% block extra_js %}
<script src="{{ url_for('static', filename='js/pages/client/contest.js') }}"></script>
{% endblock %}
```

> Dołącz `contest.js` także na dashboardzie (dla widgetu) — dodaj `<script>` w bloku `extra_js` `dashboard.html` lub w partial `_contest_widget.html` (jednorazowo). Skrypt powinien działać dla obu: `#widgetSpinBtn` i `#pageSpinBtn`.

- [ ] **Step 8: Weryfikacja manualna**

Uruchom lokalnie (`flask run` / port 5001). Zaloguj klienta z ≥1 zamówieniem przy aktywnym konkursie. Sprawdź:
- Widget na `/dashboard`: badge, liczba losów (duża, `#e35ec6`), „Twoich losów" 17px/bold, przycisk LOSUJ albo licznik (nie oba). Brak zakresu/% gdziekolwiek.
- Klik LOSUJ → modal z overlayem, karuzela w dół, losowe liczby, START rozpędza, STOP hamuje na liczbie z serwera; po zamknięciu liczba losów rośnie, pojawia się licznik cooldownu.
- Light i dark mode (`data-theme`) — oba czytelne.
- Klient nie-eligible: komunikat zamiast przycisku.

- [ ] **Step 9: Commit**

```bash
git add modules/client/routes.py templates/client/ static/css/pages/client/contest.css static/css/components/modals.css static/js/pages/client/contest.js
git commit -m "feat(contests): widget dashboardu + strona konkursu + modal ze spinnerem (light/dark)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: UI admina — formularz (pola warunkowe + picker) + losowanie na żywo

**Files:**
- Rewrite: `templates/admin/contests/form.html`, `templates/admin/contests/list.html`, `templates/admin/contests/draw.html`
- Create: `static/css/pages/admin/contests.css`, `static/js/pages/admin/contest-form.js`, `static/js/pages/admin/contest-draw.js`

- [ ] **Step 1: Formularz z kontrolkami zależnymi od pola**

Rozbuduj `form.html` (na bazie makiety `admin-form-v2.html`): osobne inputy `ticket_min`/`ticket_max`, `datetime-local` dla `ends_at`, picker produktu (input szukania + lista wyników z `/api/products/search`), kryteria jako checkbox odsłaniający input. Wpięcie CSS/JS:

```html
{% block extra_css %}<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/admin/contests.css') }}">{% endblock %}
{% block extra_js %}<script src="{{ url_for('static', filename='js/pages/admin/contest-form.js') }}"></script>{% endblock %}
```

Pole produktu: ukryte `prize_product_id` (z `form.prize_product_id`) + widoczny input szukania i kontener `#prizeResults`; wybór ustawia wartość ukrytego pola i etykietę.

- [ ] **Step 2: `static/js/pages/admin/contest-form.js`**

- Kryteria: każdy checkbox `data-target="#inpId"` włącza/wyłącza (`disabled`) powiązany input; przy submit puste/wyłączone = brak wartości (backend zapisze NULL).
- Picker: debounced fetch `GET /api/products/search?q=...` (header `X-Requested-With: XMLHttpRequest`), render wyników (`data.products`: id, name, sku, price, image_url), klik → `#prizeProductId.value = id`, pokaż wybrany.

```javascript
function getCsrfToken(){var m=document.querySelector('meta[name="csrf-token"]');return m?m.getAttribute('content'):'';}
const inp = document.getElementById('prizeSearch');
const box = document.getElementById('prizeResults');
const hidden = document.getElementById('prizeProductId');
let t;
inp && inp.addEventListener('input', () => {
  clearTimeout(t); const q = inp.value.trim(); if (q.length < 2) { box.innerHTML=''; return; }
  t = setTimeout(async () => {
    const r = await fetch('/api/products/search?q=' + encodeURIComponent(q),
      { credentials:'same-origin', headers:{'X-Requested-With':'XMLHttpRequest'} });
    const data = await r.json();
    box.innerHTML = (data.products||[]).map(p =>
      `<div class="prize-result" data-id="${p.id}">${p.name} <small>${p.sku||''} • ${p.price} zł</small></div>`).join('');
  }, 250);
});
box && box.addEventListener('click', e => {
  const el = e.target.closest('.prize-result'); if (!el) return;
  hidden.value = el.dataset.id; inp.value = el.textContent.trim();
  box.innerHTML='';
});
document.querySelectorAll('[data-crit-toggle]').forEach(cb => {
  const sync = () => { const t = document.querySelector(cb.dataset.target); if (t) t.disabled = !cb.checked; };
  cb.addEventListener('change', sync); sync();
});
```

- [ ] **Step 3: Ekran losowania na żywo `draw.html` + `contest-draw.js`**

`draw.html` (na bazie makiety `admin-ui.html` sekcja 3): statystyki (uczestnicy/pula/zwycięzcy), karuzela slot (reużyj logiki karuzeli), karta zwycięzcy, przycisk „LOSUJ ZWYCIĘZCĘ", kontener `#poolBreakdown`. JS:

```javascript
// contest-draw.js
const root = document.getElementById('drawRoot');
document.getElementById('btnDraw').addEventListener('click', async () => {
  const r = await fetch(root.dataset.drawUrl, {
    method:'POST', credentials:'same-origin',
    headers:{'Content-Type':'application/json','X-CSRFToken':getCsrfToken(),'X-Requested-With':'XMLHttpRequest'},
    body:'{}'
  });
  const data = await r.json();
  if (!data.success) { alert(data.error); return; }
  // 1) animuj slot na data.winners[0..n] kolejno (#1,#2,...)
  // 2) po animacji wyrenderuj data.breakdown jako paski z % (tylko admin)
  renderWinners(data.winners); renderBreakdown(data.breakdown, data.pool);
});
```

(Animacja slot — adaptacja karuzeli z części klienckiej; dla N zwycięzców odtwarzaj kolejno.)

- [ ] **Step 4: `static/css/pages/admin/contests.css` (light + dark)**

Style listy (tabela, pille statusów), formularza (pola, picker, kryteria), ekranu losowania (stage z gradientem, reels, paski puli). Warianty `[data-theme="dark"]`. Bazuj na makietach `admin-form-v2.html` i `admin-ui.html`.

- [ ] **Step 5: Lista z akcjami `list.html`**

Rozbuduj o pille statusów i akcje zależne od statusu: `aktywny` → „Losowanie"; `szkic` → „Edytuj" + „Aktywuj" (POST); `rozlosowany` → „Wyniki".

- [ ] **Step 6: Weryfikacja manualna (admin)**

- `/admin/konkursy`: lista, statusy, akcje.
- Formularz: dwa inputy zakresu, `datetime-local`, picker produktu (szukanie po nazwie/SKU, wybór), kryteria — checkbox włącza/wyłącza input.
- Utwórz konkurs → szkic; aktywuj (gdy brak innego aktywnego); spróbuj aktywować drugi → blokada z komunikatem.
- `/admin/konkursy/<id>/losowanie`: po (symulowanym) końcu spinów klik LOSUJ → slot animuje zwycięzcę, pojawia się rozbicie puli z %; ponowny klik nie przelosowuje (idempotencja). Wyniki w `/wyniki`.
- Light + dark mode.

- [ ] **Step 7: Commit**

```bash
git add templates/admin/contests/ static/css/pages/admin/contests.css static/js/pages/admin/contest-form.js static/js/pages/admin/contest-draw.js
git commit -m "feat(contests): admin UI — formularz (pola warunkowe + picker) + losowanie na żywo (light/dark)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Regresja końcowa, nawigacja i deploy

**Files:**
- Modify: szablony nawigacji (link do `/admin/konkursy` w menu admina; opcjonalnie `/konkurs` w menu klienta)

- [ ] **Step 1: Dodaj wejścia w nawigacji**

W menu admina (sidebar `base_admin.html` lub jego partial) dodaj link „Konkursy" → `url_for('contests.admin_list')`. Opcjonalnie w menu klienta link „Konkurs" → `url_for('contests.client_contest')` (widget i tak jest na dashboardzie).

- [ ] **Step 2: Pełna regresja testów**

Run: `python3 -m pytest tests/ -v`
Expected: wszystkie PASS (w tym istniejące `test_client_offer_filter.py` itd.).

- [ ] **Step 3: Smoke manualny end-to-end**

Lokalnie: admin tworzy konkurs (produkt z magazynu, min. 1 zamówienie, koniec za chwilę) → aktywuje → klient (z zamówieniem) kręci na dashboardzie (modal, karuzela) → po `ends_at` admin losuje na żywo → zwycięzca dostaje powiadomienie in-app, a w logach mailera widać wysyłkę `contest_win`. Klient nie widzi puli/%.

- [ ] **Step 4: Commit + push + deploy**

```bash
git add templates/
git commit -m "feat(contests): linki nawigacji do konkursów

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
git push -u origin feature/konkursy-losowania
```

Po code-review i merge do `main`: auto-deploy webhook uruchomi `flask db upgrade` na VPS (tworzy tabele konkursów). Restart usług na serwerze: `sudo systemctl restart thunderorders-http thunderorders-ws`. Szczegóły: `docs/DEPLOYMENT.md`.

---

## Uwagi wykonawcze

- **Kolejność:** Task 0 → 1 → 2 muszą iść pierwsze (fixtures, modele, migracja). Backend (3–9) jest w pełni TDD. UI (10–11) testujemy manualnie.
- **`get_local_now`** importujemy z `modules.orders.models` (jedyne źródło w projekcie). Jeśli powstanie współdzielony helper czasu, zaktualizuj importy.
- **Bezpieczeństwo:** wynik spinu i losowanie liczy wyłącznie serwer; frontend tylko odgrywa. `POST /losuj` idempotentne.
- **Skala:** wolumen mały — `SUM`/`GROUP BY` po `contest_spins` są tanie; brak potrzeby denormalizacji.
