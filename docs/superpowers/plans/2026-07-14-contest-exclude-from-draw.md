# Wykluczenie osoby z losowania zwycięzców — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Umożliwić adminowi wskazanie w ustawieniach konkursu osób, które biorą normalnie udział i pojawiają się w ruletce, ale nie mogą zostać wybrane jako zwycięzcy.

**Architecture:** Nowa tabela `contest_excluded_users` (wiele-do-wielu konkurs↔user). `participants()` zostaje bez zmian (bęben pokazuje wszystkich); wykluczeni są odfiltrowywani wyłącznie w `draw_winners()` i w procentach szans widoku admina. UI ustawień to inline picker (wyszukiwarka + chipy) zasilający ukryte pole `excluded_json`, przetwarzane serwerowo jak `prizes_json`.

**Tech Stack:** Flask, Flask-Migrate (Alembic), SQLAlchemy, MariaDB, Jinja2, vanilla JS, pytest.

## Global Constraints

- **Zawsze po polsku** w komunikacji, komentarzach i tekstach UI.
- **Każda zmiana struktury bazy MUSI iść przez migrację Flask-Migrate** — nie tylko model.
- **CSS zawsze light + dark mode** (`[data-theme="dark"]`).
- **Nie dotykać `modals.css`** — picker jest inline (bez modala).
- **CSS/JS w osobnych plikach** (`static/css/pages/admin/contests.css`, `static/js/pages/admin/contest-form.js`), nie inline w HTML.
- **Testy uruchamiać przez `python -m pytest`** (gołe `pytest` pada: `No module named 'app'`).
- Reużyć istniejący endpoint wyszukiwania `/admin/users/api/search` (świadomie `@admin_required`).
- Testy używają `db.create_all()` (conftest), więc nowy model wystarczy do testów; migracja jest dla lokalnej/prod bazy.

## Pliki (mapa zmian)

| Plik | Rola |
|------|------|
| `modules/contests/models.py` | +model `ContestExcludedUser`, +relacja `Contest.excluded_entries`, +property `excluded_user_ids` |
| `migrations/versions/<nowy>.py` | ręcznie napisana migracja `create_table('contest_excluded_users')` |
| `modules/contests/utils.py` | +helper `excluded_user_ids()`, modyfikacja `draw_winners()` |
| `modules/contests/routes.py` | modyfikacja `admin_distribution` i `admin_draw` (pole `excluded` + % bez wykluczonych); +helper `_apply_excluded()` wołany w `admin_new`/`admin_edit` |
| `app.py` | +filtr `tojson_excluded` (prefill przy edycji) |
| `templates/admin/contests/form.html` | +karta „Wykluczeni z losowania zwycięzców" |
| `static/js/pages/admin/contest-form.js` | +logika pickera wykluczeń |
| `static/js/pages/admin/contest-distribution.js` | +badge „wykluczony" w wierszu rozkładu |
| `static/js/pages/admin/contest-draw.js` | +badge „wykluczony" w breakdown |
| `static/css/pages/admin/contests.css` | +style pickera i badge (light + dark) |
| `tests/test_contests_models.py` | testy modelu + relacji |
| `tests/test_contests_draw.py` | testy wykluczania w losowaniu |
| `tests/test_contests_distribution.py` | testy pola `excluded`/% w `/rozklad` |
| `tests/test_contests_routes_admin.py` | testy `_apply_excluded` (nowy/edycja) |
| `tests/test_contests_admin_ui.py` | test obecności karty w formularzu |

---

### Task 1: Model `ContestExcludedUser` + relacja + migracja

**Files:**
- Modify: `modules/contests/models.py`
- Create: `migrations/versions/<nowy>_contest_excluded_users.py`
- Test: `tests/test_contests_models.py`

**Interfaces:**
- Produces: model `ContestExcludedUser(id, contest_id, user_id, created_at, user)`; `Contest.excluded_entries` (relacja, cascade all/delete-orphan); `Contest.excluded_user_ids` (property → `set[int]`).

- [ ] **Step 1: Napisz test modelu (failing)**

Dopisz na końcu `tests/test_contests_models.py`:

```python
def test_excluded_user_relationship_and_cascade(db, make_product, make_user):
    from modules.contests.models import Contest, ContestExcludedUser
    admin = make_user(role='admin'); prod = make_product()
    c = Contest(name='C', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                status='aktywny', created_by_admin_id=admin.id)
    db.session.add(c); db.session.commit()
    u1, u2 = make_user(), make_user()
    c.excluded_entries.append(ContestExcludedUser(user_id=u1.id))
    c.excluded_entries.append(ContestExcludedUser(user_id=u2.id))
    db.session.commit()

    assert c.excluded_user_ids == {u1.id, u2.id}
    assert ContestExcludedUser.query.filter_by(contest_id=c.id).count() == 2

    # cascade: usunięcie konkursu kasuje wiersze wykluczeń
    db.session.delete(c); db.session.commit()
    assert ContestExcludedUser.query.count() == 0


def test_excluded_clear_removes_orphans(db, make_product, make_user):
    from modules.contests.models import Contest, ContestExcludedUser
    admin = make_user(role='admin'); prod = make_product()
    c = Contest(name='C', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                status='aktywny', created_by_admin_id=admin.id)
    db.session.add(c); db.session.commit()
    c.excluded_entries.append(ContestExcludedUser(user_id=make_user().id))
    db.session.commit()
    c.excluded_entries.clear()   # delete-orphan usuwa wiersz
    db.session.commit()
    assert ContestExcludedUser.query.count() == 0
    assert c.excluded_user_ids == set()
```

- [ ] **Step 2: Uruchom test — ma failować**

Run: `python -m pytest tests/test_contests_models.py::test_excluded_user_relationship_and_cascade -v`
Expected: FAIL — `ImportError: cannot import name 'ContestExcludedUser'`.

- [ ] **Step 3: Dodaj model i relację**

W `modules/contests/models.py` dodaj nowy model na końcu pliku:

```python
class ContestExcludedUser(db.Model):
    __tablename__ = 'contest_excluded_users'

    id = db.Column(db.Integer, primary_key=True)
    contest_id = db.Column(db.Integer, db.ForeignKey('contests.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)

    user = db.relationship('User', foreign_keys=[user_id])

    __table_args__ = (
        db.UniqueConstraint('contest_id', 'user_id', name='uq_contest_excluded_user'),
    )

    def __repr__(self):
        return f'<ContestExcludedUser contest={self.contest_id} user={self.user_id}>'
```

W klasie `Contest`, tuż pod istniejącą relacją `prizes = db.relationship(...)` (linia ~28-29), dodaj relację:

```python
    excluded_entries = db.relationship('ContestExcludedUser', backref='contest',
                                       cascade='all, delete-orphan')
```

Oraz property (obok istniejącego `prize_summary`, np. zaraz po nim):

```python
    @property
    def excluded_user_ids(self):
        """Zbiór ID użytkowników wykluczonych z losowania zwycięzców."""
        return {e.user_id for e in self.excluded_entries}
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `python -m pytest tests/test_contests_models.py -v`
Expected: PASS (oba nowe testy + istniejące).

- [ ] **Step 5: Wygeneruj migrację ręcznie**

Autogenerate w tym repo produkuje szum (drift modeli vs baza) — **nie ufaj `flask db migrate`**, napisz migrację ręcznie.

Najpierw ustal aktualną głowę (down_revision):

Run: `python -m flask db current`
Zanotuj revision id (na dziś prawdopodobnie `261f567bb320`).

Utwórz `migrations/versions/<krótki_hash>_contest_excluded_users.py` (hash dowolny 12-znakowy, np. `a1b2c3d4e5f6`):

```python
"""Dodaj tabelę contest_excluded_users (wykluczeni z losowania)

Revision ID: a1b2c3d4e5f6
Revises: 261f567bb320
Create Date: 2026-07-14 00:00:00.000000

Migracja zawęża się WYŁĄCZNIE do nowej tabeli contest_excluded_users
(wykluczanie osób z losowania zwycięzców konkursu).
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '261f567bb320'   # ZWERYFIKUJ: musi być wynik `flask db current`
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'contest_excluded_users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contest_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['contest_id'], ['contests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('contest_id', 'user_id', name='uq_contest_excluded_user'),
    )


def downgrade():
    op.drop_table('contest_excluded_users')
```

- [ ] **Step 6: Zastosuj migrację lokalnie i zweryfikuj**

Run: `python -m flask db upgrade`
Expected: brak błędów; tabela `contest_excluded_users` istnieje.

Weryfikacja (opcjonalnie): `python -m flask db current` → pokazuje nowy revision jako head.

- [ ] **Step 7: Commit**

```bash
git add modules/contests/models.py migrations/versions/*contest_excluded_users.py tests/test_contests_models.py
git commit -m "feat(contests): model ContestExcludedUser + migracja

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Wykluczanie w `draw_winners()`

**Files:**
- Modify: `modules/contests/utils.py`
- Test: `tests/test_contests_draw.py`

**Interfaces:**
- Consumes: `Contest.excluded_user_ids`; model `ContestExcludedUser` (Task 1).
- Produces: `excluded_user_ids(contest) -> set[int]`; zmodyfikowany `draw_winners(contest, rng=None)` losujący wyłącznie z uczestników spoza wykluczonych.

- [ ] **Step 1: Napisz testy (failing)**

Dopisz na końcu `tests/test_contests_draw.py`:

```python
def _exclude(db, c, u):
    from modules.contests.models import ContestExcludedUser
    db.session.add(ContestExcludedUser(contest_id=c.id, user_id=u.id))
    db.session.commit()


def test_excluded_user_never_wins_despite_tickets(db, make_product, make_user):
    from modules.contests.utils import draw_winners
    c = _contest(db, make_product, make_user, num_winners=1)
    big, small = make_user(), make_user()
    _spin(db, c, big, 1000)   # ogromna przewaga losów
    _spin(db, c, small, 1)
    _exclude(db, c, big)      # ale wykluczony
    winners = draw_winners(c, rng=random.Random(1))
    assert len(winners) == 1
    assert winners[0].user_id == small.id           # wygrywa jedyny nie-wykluczony
    assert winners[0].tickets_at_draw == 1
    assert winners[0].chance_pct == 100.0           # % liczony z puli bez wykluczonych


def test_excluded_reduces_winner_count(db, make_product, make_user):
    from modules.contests.utils import draw_winners
    c = _contest(db, make_product, make_user, num_winners=3)
    a, b, cc = make_user(), make_user(), make_user()
    _spin(db, c, a, 10); _spin(db, c, b, 10); _spin(db, c, cc, 10)
    _exclude(db, c, a); _exclude(db, c, b)
    winners = draw_winners(c, rng=random.Random(2))
    assert len(winners) == 1                         # tylko cc losowalny
    assert winners[0].user_id == cc.id


def test_all_participants_excluded_no_winners(db, make_product, make_user):
    from modules.contests.utils import draw_winners
    c = _contest(db, make_product, make_user, num_winners=2)
    a, b = make_user(), make_user()
    _spin(db, c, a, 10); _spin(db, c, b, 20)
    _exclude(db, c, a); _exclude(db, c, b)
    winners = draw_winners(c, rng=random.Random(3))
    assert winners == []
    assert c.status == 'rozlosowany'


def test_excluded_user_ids_helper(db, make_product, make_user):
    from modules.contests.utils import excluded_user_ids
    c = _contest(db, make_product, make_user)
    u = make_user()
    assert excluded_user_ids(c) == set()
    _exclude(db, c, u)
    assert excluded_user_ids(c) == {u.id}
```

- [ ] **Step 2: Uruchom testy — mają failować**

Run: `python -m pytest tests/test_contests_draw.py::test_excluded_user_ids_helper -v`
Expected: FAIL — `ImportError: cannot import name 'excluded_user_ids'`.

- [ ] **Step 3: Dodaj helper i zmodyfikuj `draw_winners`**

W `modules/contests/utils.py` dodaj helper (np. tuż nad `def draw_winners`):

```python
def excluded_user_ids(contest):
    """Zbiór ID użytkowników wykluczonych z losowania zwycięzców tego konkursu."""
    from modules.contests.models import ContestExcludedUser
    rows = db.session.query(ContestExcludedUser.user_id) \
        .filter(ContestExcludedUser.contest_id == contest.id).all()
    return {uid for (uid,) in rows}
```

W `draw_winners`, zamień linię budującą pulę. Obecnie (linie ~164-166):

```python
    rng = rng or _random.SystemRandom()
    pool_participants = participants(contest)
    initial_pool_total = sum(t for _, t in pool_participants)
    n = min(contest.num_winners, len(pool_participants))
```

na:

```python
    rng = rng or _random.SystemRandom()
    excluded = excluded_user_ids(contest)
    # Wykluczeni pozostają w participants() (widoczni w bębnie), ale NIE mogą wygrać —
    # usuwamy ich z puli losowalnej i z mianownika szans.
    pool_participants = [(u, t) for (u, t) in participants(contest) if u.id not in excluded]
    initial_pool_total = sum(t for _, t in pool_participants)
    n = min(contest.num_winners, len(pool_participants))
```

(Reszta funkcji — `remaining`, pętla, `_weighted_pick`, commit, powiadomienia — bez zmian.)

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `python -m pytest tests/test_contests_draw.py -v`
Expected: PASS (nowe + istniejące, w tym `test_weighting_is_proportional`).

- [ ] **Step 5: Commit**

```bash
git add modules/contests/utils.py tests/test_contests_draw.py
git commit -m "feat(contests): wyklucz wskazane osoby z puli losowania zwycięzców

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Kontrakt JSON widoku admina (`excluded` + realne %)

**Files:**
- Modify: `modules/contests/routes.py` (funkcje `admin_distribution`, `admin_draw`)
- Test: `tests/test_contests_distribution.py`, `tests/test_contests_routes_admin.py`

**Interfaces:**
- Consumes: `contest.excluded_user_ids` (property z Task 1, zwraca `set[int]`), `cu.participants(contest)`, `cu.get_pool(contest)`.
- Produces: w JSON z `/rozklad` każdy element `participants[]` ma pole `excluded: bool`; `chance_pct` = 0 dla wykluczonych, dla reszty liczony z puli bez wykluczonych. W JSON z `/losuj` każdy `breakdown[]` ma `excluded: bool`; `pct` analogicznie.

> **Uwaga (konsolidacja po review Task 2):** używaj property `c.excluded_user_ids` — samodzielna funkcja `cu.excluded_user_ids()` została usunięta jako duplikat.

- [ ] **Step 1: Napisz testy (failing)**

Dopisz do `tests/test_contests_distribution.py`:

```python
def test_distribution_marks_excluded_and_recomputes_pct(client, db, make_product, make_user, login):
    from modules.contests.models import ContestExcludedUser
    c = _contest(db, make_product, make_user)
    u1, u2 = make_user(), make_user()
    _spin(db, c, u1, 30); _spin(db, c, u2, 10)
    db.session.add(ContestExcludedUser(contest_id=c.id, user_id=u1.id)); db.session.commit()
    login(_admin(make_user))
    data = client.get(f'/admin/konkursy/{c.id}/rozklad').get_json()
    by_name = {p['tickets']: p for p in data['participants']}
    # wykluczony (30 losów) -> excluded True, 0%
    assert by_name[30]['excluded'] is True
    assert by_name[30]['chance_pct'] == 0
    # nie-wykluczony (10 losów) -> 100% z puli bez wykluczonych
    assert by_name[10]['excluded'] is False
    assert by_name[10]['chance_pct'] == 100.0
    assert data['pool'] == 40   # pool całkowity bez zmian (informacyjny)
```

Dopisz do `tests/test_contests_routes_admin.py`:

```python
def test_draw_breakdown_marks_excluded(client, db, make_user, make_product, login):
    from modules.contests.models import Contest, ContestSpin, ContestExcludedUser
    login(make_user(role='admin')); prod = make_product()
    c = Contest(name='A', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, status='aktywny')
    db.session.add(c); db.session.commit()
    big, small = make_user(), make_user()
    db.session.add(ContestSpin(contest_id=c.id, user_id=big.id, tickets_won=90))
    db.session.add(ContestSpin(contest_id=c.id, user_id=small.id, tickets_won=10))
    db.session.add(ContestExcludedUser(contest_id=c.id, user_id=big.id))
    db.session.commit()
    body = client.post(f'/admin/konkursy/{c.id}/losuj').get_json()
    assert body['success'] is True
    assert body['winners'][0]['user_id'] == small.id     # wykluczony nie wygrał
    row = {r['user_id']: r for r in body['breakdown']}
    assert row[big.id]['excluded'] is True and row[big.id]['pct'] == 0
    assert row[small.id]['excluded'] is False and row[small.id]['pct'] == 100.0
```

- [ ] **Step 2: Uruchom testy — mają failować**

Run: `python -m pytest tests/test_contests_distribution.py::test_distribution_marks_excluded_and_recomputes_pct tests/test_contests_routes_admin.py::test_draw_breakdown_marks_excluded -v`
Expected: FAIL — `KeyError: 'excluded'`.

- [ ] **Step 3: Zmodyfikuj `admin_distribution`**

W `modules/contests/routes.py`, funkcja `admin_distribution` (linie ~41-60). Zamień blok budujący `parts`:

```python
    c = Contest.query.get_or_404(cid)
    pool = cu.get_pool(c)
    parts = []
    for user, tickets in cu.participants(c):
        parts.append({
            'name': _display_name(user),
            'tickets': tickets,
            'chance_pct': round(tickets / pool * 100, 3) if pool else 0,
        })
```

na:

```python
    c = Contest.query.get_or_404(cid)
    pool = cu.get_pool(c)
    excluded = c.excluded_user_ids
    # mianownik szans = suma losów uczestników BEZ wykluczonych (realne %)
    drawable_pool = sum(t for u, t in cu.participants(c) if u.id not in excluded)
    parts = []
    for user, tickets in cu.participants(c):
        is_excl = user.id in excluded
        parts.append({
            'name': _display_name(user),
            'tickets': tickets,
            'excluded': is_excl,
            'chance_pct': 0 if is_excl else (round(tickets / drawable_pool * 100, 3) if drawable_pool else 0),
        })
```

- [ ] **Step 4: Zmodyfikuj `admin_draw` (breakdown)**

W tej samej funkcji `admin_draw` (linie ~264-274). Zamień blok `breakdown`:

```python
    winners = cu.draw_winners(c)
    pool = cu.get_pool(c)
    # pełne rozbicie puli z procentami — TYLKO dla admina (klient tego nie widzi)
    breakdown = []
    for user, tickets in cu.participants(c):
        breakdown.append({
            'user_id': user.id,
            'name': _display_name(user),
            'tickets': tickets,
            'pct': round(tickets / pool * 100, 2) if pool else 0,
        })
```

na:

```python
    winners = cu.draw_winners(c)
    pool = cu.get_pool(c)
    excluded = c.excluded_user_ids
    drawable_pool = sum(t for u, t in cu.participants(c) if u.id not in excluded)
    # pełne rozbicie puli z procentami — TYLKO dla admina (klient tego nie widzi)
    breakdown = []
    for user, tickets in cu.participants(c):
        is_excl = user.id in excluded
        breakdown.append({
            'user_id': user.id,
            'name': _display_name(user),
            'tickets': tickets,
            'excluded': is_excl,
            'pct': 0 if is_excl else (round(tickets / drawable_pool * 100, 2) if drawable_pool else 0),
        })
```

(`breakdown.sort(...)` poniżej bez zmian.)

- [ ] **Step 5: Uruchom testy — mają przejść**

Run: `python -m pytest tests/test_contests_distribution.py tests/test_contests_routes_admin.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/contests/routes.py tests/test_contests_distribution.py tests/test_contests_routes_admin.py
git commit -m "feat(contests): oznacz wykluczonych w rozkładzie i breakdown admina

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Zapis wykluczeń z formularza + prefill

**Files:**
- Modify: `modules/contests/routes.py` (helper `_apply_excluded`, wywołanie w `admin_new`/`admin_edit`)
- Modify: `app.py` (filtr `tojson_excluded`)
- Test: `tests/test_contests_routes_admin.py`

**Interfaces:**
- Consumes: model `ContestExcludedUser`, `User`.
- Produces: `_apply_excluded(contest)` — czyta `request.form['excluded_json']` (tablica ID), przebudowuje `contest.excluded_entries`, waliduje istnienie userów, pomija duplikaty. Filtr Jinja `tojson_excluded` → JSON `[{"id","name","email"}]`.

- [ ] **Step 1: Napisz testy (failing)**

Dopisz do `tests/test_contests_routes_admin.py`:

```python
def test_create_contest_with_excluded(client, db, make_user, make_product, login):
    import json
    from modules.contests.models import Contest, ContestExcludedUser
    login(make_user(role='admin'))
    u1, u2 = make_user(), make_user()
    resp = client.post('/admin/konkursy/nowy', data={
        'name': 'Konkurs Excl', 'num_winners': 1,
        'ticket_min': 1, 'ticket_max': 50, 'cooldown_minutes': 1440,
        'excluded_json': json.dumps([u1.id, u2.id]),
    }, follow_redirects=True)
    assert resp.status_code == 200
    c = Contest.query.filter_by(name='Konkurs Excl').first()
    assert c.excluded_user_ids == {u1.id, u2.id}


def test_excluded_replaced_on_edit(client, db, make_user, make_product, login):
    import json
    from modules.contests.models import Contest, ContestExcludedUser
    login(make_user(role='admin')); prod = make_product()
    c = Contest(name='C', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, cooldown_minutes=1440, status='szkic')
    db.session.add(c); db.session.commit()
    u1, u2 = make_user(), make_user()
    db.session.add(ContestExcludedUser(contest_id=c.id, user_id=u1.id)); db.session.commit()
    # edycja: zostaw tylko u2
    client.post(f'/admin/konkursy/{c.id}/edytuj', data={
        'name': 'C', 'num_winners': 1, 'ticket_min': 1, 'ticket_max': 50,
        'cooldown_minutes': 1440, 'excluded_json': json.dumps([u2.id]),
    }, follow_redirects=True)
    db.session.refresh(c)
    assert c.excluded_user_ids == {u2.id}


def test_excluded_json_empty_clears(client, db, make_user, make_product, login):
    from modules.contests.models import Contest, ContestExcludedUser
    login(make_user(role='admin')); prod = make_product()
    c = Contest(name='C', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, cooldown_minutes=1440, status='szkic')
    db.session.add(c); db.session.commit()
    db.session.add(ContestExcludedUser(contest_id=c.id, user_id=make_user().id)); db.session.commit()
    client.post(f'/admin/konkursy/{c.id}/edytuj', data={
        'name': 'C', 'num_winners': 1, 'ticket_min': 1, 'ticket_max': 50,
        'cooldown_minutes': 1440, 'excluded_json': '',
    }, follow_redirects=True)
    db.session.refresh(c)
    assert c.excluded_user_ids == set()


def test_excluded_json_skips_invalid_and_dupes(client, db, make_user, make_product, login):
    import json
    from modules.contests.models import Contest
    login(make_user(role='admin'))
    u = make_user()
    resp = client.post('/admin/konkursy/nowy', data={
        'name': 'Konkurs Excl2', 'num_winners': 1,
        'ticket_min': 1, 'ticket_max': 50, 'cooldown_minutes': 1440,
        'excluded_json': json.dumps([u.id, u.id, 999999, 'x']),  # dup + nieistniejący + śmieć
    }, follow_redirects=True)
    assert resp.status_code == 200
    c = Contest.query.filter_by(name='Konkurs Excl2').first()
    assert c.excluded_user_ids == {u.id}
```

- [ ] **Step 2: Uruchom testy — mają failować**

Run: `python -m pytest tests/test_contests_routes_admin.py::test_create_contest_with_excluded -v`
Expected: FAIL — wykluczenia nie zapisane (`excluded_user_ids` puste).

- [ ] **Step 3: Dodaj `_apply_excluded` i wywołania**

W `modules/contests/routes.py`, dodaj helper obok `_apply_prizes` (np. zaraz po nim):

```python
def _apply_excluded(contest):
    """Przebuduj listę wykluczonych z pola excluded_json (tablica ID użytkowników)."""
    from modules.contests.models import ContestExcludedUser
    from modules.auth.models import User
    raw = request.form.get('excluded_json', '').strip()
    contest.excluded_entries.clear()  # cascade delete-orphan usuwa stare wiersze
    if not raw:
        return
    try:
        ids = json.loads(raw)
    except (ValueError, TypeError):
        return
    seen = set()
    for uid in ids or []:
        try:
            uid = int(uid)
        except (ValueError, TypeError):
            continue
        if uid in seen:
            continue
        if db.session.get(User, uid):
            seen.add(uid)
            contest.excluded_entries.append(ContestExcludedUser(user_id=uid))
```

W `admin_new` — po `_apply_prizes(c)` dodaj `_apply_excluded(c)`:

```python
        _apply_prizes(c)
        _apply_excluded(c)
        _handle_contest_image(c)
```

W `admin_edit` — analogicznie po `_apply_prizes(c)`:

```python
        _apply_form(form, c)
        _apply_prizes(c)
        _apply_excluded(c)
        _handle_contest_image(c)
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `python -m pytest tests/test_contests_routes_admin.py -v`
Expected: PASS.

- [ ] **Step 5: Dodaj filtr `tojson_excluded` do prefill**

W `app.py`, tuż pod filtrem `tojson_prizes_filter` (kończy się ~linia 1559), dodaj:

```python
    @app.template_filter('tojson_excluded')
    def tojson_excluded_filter(entries):
        """
        Serializuje listę ContestExcludedUser do JSON dla inicjalizacji JS na stronie edycji.
        Format: [{"id": int, "name": str, "email": str}]
        Użycie: {{ contest.excluded_entries|tojson_excluded }}
        """
        import json as _json
        result = []
        for e in entries:
            u = e.user
            if not u:
                continue
            name = ((u.first_name or '') + ' ' + (u.last_name or '')).strip() or u.email
            result.append({'id': u.id, 'name': name, 'email': u.email})
        return _json.dumps(result, ensure_ascii=False)
```

- [ ] **Step 6: Sanity — aplikacja się ładuje**

Run: `python -m pytest tests/test_contests_routes_admin.py tests/test_contests_models.py tests/test_contests_draw.py -q`
Expected: PASS (potwierdza, że `app.py` importuje się bez błędu).

- [ ] **Step 7: Commit**

```bash
git add modules/contests/routes.py app.py tests/test_contests_routes_admin.py
git commit -m "feat(contests): zapis i prefill listy wykluczonych z formularza

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: UI — picker wykluczeń + badge w widokach admina

**Files:**
- Modify: `templates/admin/contests/form.html`
- Modify: `static/js/pages/admin/contest-form.js`
- Modify: `static/js/pages/admin/contest-distribution.js`
- Modify: `static/js/pages/admin/contest-draw.js`
- Modify: `static/css/pages/admin/contests.css`
- Test: `tests/test_contests_admin_ui.py`

**Interfaces:**
- Consumes: endpoint `GET /admin/users/api/search?q=` (zwraca `[{id,name,email,avatar}]`); ukryte pole `excluded_json`; filtr `tojson_excluded`; pola JSON `excluded`/`pct` z Task 3.
- Produces: karta ustawień „Wykluczeni z losowania zwycięzców"; badge „wykluczony" w rozkładzie i breakdown.

- [ ] **Step 1: Napisz test obecności karty (failing)**

Dopisz do `tests/test_contests_admin_ui.py` (jeśli brak importów/helperów, wzoruj się na istniejących testach w tym pliku — logowanie admina + GET formularza):

```python
def test_edit_form_has_excluded_card(client, db, make_user, make_product, login):
    from modules.contests.models import Contest
    login(make_user(role='admin')); prod = make_product()
    c = Contest(name='C', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, cooldown_minutes=1440, status='szkic')
    db.session.add(c); db.session.commit()
    html = client.get(f'/admin/konkursy/{c.id}/edytuj').data.decode()
    assert 'Wykluczeni z losowania' in html
    assert 'excluded_json' in html
    assert 'id="excludedSearch"' in html
```

- [ ] **Step 2: Uruchom test — ma failować**

Run: `python -m pytest tests/test_contests_admin_ui.py::test_edit_form_has_excluded_card -v`
Expected: FAIL — brak markupu.

- [ ] **Step 3: Dodaj kartę do `form.html`**

W `templates/admin/contests/form.html`, w kolumnie bocznej `aside`, po sekcji „Kryteria udziału" (po jej zamykającym `</section>`, przed `</aside>` — okolice linii 270), wstaw:

```html
                {# ---- Wykluczeni z losowania zwycięzców ---- #}
                <section class="ca-card">
                    <div class="ca-card-head">
                        <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/>
                            <path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708"/>
                        </svg>
                        <h2>Wykluczeni z losowania zwycięzców</h2>
                    </div>
                    <div class="ca-card-body">
                        <p class="ca-prize-helper">Te osoby normalnie biorą udział i pojawiają się w ruletce, ale nie zostaną wybrane jako zwycięzcy.</p>

                        <input type="hidden" name="excluded_json" id="excludedJson"
                               value="{{ contest.excluded_entries|tojson_excluded if contest and contest.excluded_entries else '[]' }}">

                        <div class="ca-excl-search-wrap">
                            <svg class="ca-excl-search-icon" width="15" height="15" viewBox="0 0 16 16" fill="currentColor">
                                <path d="M11.742 10.344a6.5 6.5 0 10-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 001.415-1.414l-3.85-3.85a1.007 1.007 0 00-.115-.1zM12 6.5a5.5 5.5 0 11-11 0 5.5 5.5 0 0111 0z"/>
                            </svg>
                            <input type="text" id="excludedSearch" class="ca-excl-search-inp"
                                   placeholder="Szukaj po imieniu, nazwisku lub emailu…" autocomplete="off">
                            <div id="excludedResults" class="ca-excl-results"></div>
                        </div>

                        <div id="excludedChips" class="ca-excl-chips"></div>
                    </div>
                </section>
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `python -m pytest tests/test_contests_admin_ui.py::test_edit_form_has_excluded_card -v`
Expected: PASS.

- [ ] **Step 5: Dodaj logikę pickera do `contest-form.js`**

Na końcu IIFE w `static/js/pages/admin/contest-form.js` (przed zamykającym `})();`), dodaj samodzielny blok. Reużywa istniejących `debounce` i `escHtml`:

```javascript
  /* -------------------------------------------------------------- */
  /* Picker: wykluczeni z losowania zwycięzców                        */
  /* -------------------------------------------------------------- */
  var excludedJsonEl = document.getElementById('excludedJson');
  var excludedSearch = document.getElementById('excludedSearch');
  var excludedResults = document.getElementById('excludedResults');
  var excludedChips = document.getElementById('excludedChips');

  if (excludedJsonEl && excludedSearch && excludedChips) {
    var excluded = [];   // [{id, name, email}]
    try { excluded = JSON.parse(excludedJsonEl.value) || []; } catch (e) { excluded = []; }

    function syncExcluded() {
      excludedJsonEl.value = JSON.stringify(excluded.map(function (u) { return u.id; }));
    }

    function renderChips() {
      if (!excluded.length) {
        excludedChips.innerHTML = '<div class="ca-excl-empty">Nikt nie jest wykluczony.</div>';
        syncExcluded();
        return;
      }
      excludedChips.innerHTML = excluded.map(function (u) {
        return '<span class="ca-excl-chip" data-uid="' + u.id + '">' +
               '<span class="ca-excl-chip-name">' + escHtml(u.name) + '</span>' +
               '<button type="button" class="ca-excl-chip-x" data-uid="' + u.id + '" aria-label="Usuń">&times;</button>' +
               '</span>';
      }).join('');
      excludedChips.querySelectorAll('.ca-excl-chip-x').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var id = parseInt(btn.getAttribute('data-uid'), 10);
          excluded = excluded.filter(function (u) { return u.id !== id; });
          renderChips();
        });
      });
      syncExcluded();
    }

    function hideResults() { excludedResults.innerHTML = ''; excludedResults.classList.remove('is-open'); }

    function searchUsers(q) {
      fetch('/admin/users/api/search?q=' + encodeURIComponent(q), { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (users) {
          var chosen = {};
          excluded.forEach(function (u) { chosen[u.id] = true; });
          var avail = users.filter(function (u) { return !chosen[u.id]; });
          if (!avail.length) { hideResults(); return; }
          excludedResults.innerHTML = avail.map(function (u) {
            return '<div class="ca-excl-result" data-uid="' + u.id + '" ' +
                   'data-name="' + escHtml(u.name) + '" data-email="' + escHtml(u.email || '') + '">' +
                   '<span class="ca-excl-result-name">' + escHtml(u.name) + '</span>' +
                   '<span class="ca-excl-result-email">' + escHtml(u.email || '') + '</span>' +
                   '</div>';
          }).join('');
          excludedResults.classList.add('is-open');
          excludedResults.querySelectorAll('.ca-excl-result').forEach(function (row) {
            row.addEventListener('click', function () {
              excluded.push({
                id: parseInt(row.getAttribute('data-uid'), 10),
                name: row.getAttribute('data-name'),
                email: row.getAttribute('data-email'),
              });
              excludedSearch.value = '';
              hideResults();
              renderChips();
            });
          });
        })
        .catch(function () { hideResults(); });
    }

    excludedSearch.addEventListener('input', function () {
      var q = excludedSearch.value.trim();
      if (q.length < 2) { hideResults(); return; }
      debounce('excludedSearch', function () { searchUsers(q); }, 250);
    });

    document.addEventListener('click', function (e) {
      if (!excludedResults.contains(e.target) && e.target !== excludedSearch) hideResults();
    });

    renderChips();
  }
```

> `debounce(key, fn, delay)` i `escHtml(s)` są już zdefiniowane w tym pliku (linie 18 i 23). `escHtml` escapuje `& < > "` — atrybuty `data-*` w kodzie używają podwójnych cudzysłowów, więc apostrofy w nazwiskach są bezpieczne, a wybór idzie przez `addEventListener` (nie inline `onclick`).

- [ ] **Step 6: Dodaj badge w rozkładzie (`contest-distribution.js`)**

W `renderPool` (element nazwy to `var name` z klasą `ca-bar-name`, linia 120: `name.textContent = p.name;`). Wstaw **bezpośrednio po** linii 120:

```javascript
      if (p.excluded) {
        name.insertAdjacentHTML('beforeend', '<span class="ca-excl-badge">wykluczony</span>');
      }
```

- [ ] **Step 7: Dodaj badge w breakdown (`contest-draw.js`)**

W `renderBreakdown` element nazwy to `var name` z klasą `ca-bar-name` (linia 331: `name.textContent = entry.name;`, a winner dokleja trofeum przez `insertAdjacentHTML` w linii 333). Wstaw **bezpośrednio po** bloku winner (po linii 334, `}`):

```javascript
      if (entry.excluded) {
        name.insertAdjacentHTML('beforeend', '<span class="ca-excl-badge">wykluczony</span>');
      }
```

- [ ] **Step 8: Dodaj style (light + dark) do `contests.css`**

Dopisz na końcu `static/css/pages/admin/contests.css`:

```css
/* ---- Picker wykluczonych z losowania ---- */
.ca-excl-search-wrap { position: relative; }
.ca-excl-search-icon {
    position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
    color: #9aa0a6; pointer-events: none;
}
.ca-excl-search-inp {
    width: 100%; padding: 8px 12px 8px 32px; box-sizing: border-box;
    border: 1px solid #e0e0e0; border-radius: 8px; background: #fff; color: #333;
    font-size: 14px;
}
.ca-excl-search-inp:focus { outline: none; border-color: #f093fb; }
.ca-excl-results {
    display: none; position: absolute; z-index: 20; left: 0; right: 0; top: calc(100% + 4px);
    background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.12); max-height: 240px; overflow-y: auto;
}
.ca-excl-results.is-open { display: block; }
.ca-excl-result {
    display: flex; flex-direction: column; gap: 2px; padding: 8px 12px; cursor: pointer;
}
.ca-excl-result:hover { background: #f6f2ff; }
.ca-excl-result-name { font-size: 14px; color: #333; }
.ca-excl-result-email { font-size: 12px; color: #888; }
.ca-excl-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.ca-excl-empty { font-size: 13px; color: #999; }
.ca-excl-chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 6px 4px 10px; border-radius: 999px;
    background: #f6f2ff; border: 1px solid rgba(240,147,251,0.3); color: #333; font-size: 13px;
}
.ca-excl-chip-x {
    display: inline-flex; align-items: center; justify-content: center;
    width: 18px; height: 18px; border: none; border-radius: 50%;
    background: rgba(245,87,108,0.15); color: #f5576c; cursor: pointer;
    font-size: 15px; line-height: 1;
}
.ca-excl-chip-x:hover { background: rgba(245,87,108,0.3); }
.ca-excl-badge {
    display: inline-block; margin-left: 6px; padding: 1px 7px; border-radius: 999px;
    background: rgba(245,87,108,0.12); color: #f5576c;
    font-size: 11px; font-weight: 600; vertical-align: middle;
}

/* ---- Dark mode ---- */
[data-theme="dark"] .ca-excl-search-inp {
    background: rgba(255,255,255,0.05); border: 1px solid rgba(240,147,251,0.15); color: #fff;
}
[data-theme="dark"] .ca-excl-search-inp:focus { border-color: #f093fb; }
[data-theme="dark"] .ca-excl-results {
    background: #1e1b2e; border: 1px solid rgba(240,147,251,0.15);
    box-shadow: 0 6px 20px rgba(0,0,0,0.4);
}
[data-theme="dark"] .ca-excl-result:hover { background: rgba(240,147,251,0.08); }
[data-theme="dark"] .ca-excl-result-name { color: #fff; }
[data-theme="dark"] .ca-excl-result-email { color: rgba(255,255,255,0.6); }
[data-theme="dark"] .ca-excl-empty { color: rgba(255,255,255,0.5); }
[data-theme="dark"] .ca-excl-chip {
    background: rgba(255,255,255,0.05); border: 1px solid rgba(240,147,251,0.3); color: #fff;
}
[data-theme="dark"] .ca-excl-badge { background: rgba(245,87,108,0.2); color: #f5576c; }
```

- [ ] **Step 9: Weryfikacja w przeglądarce (dev server)**

Uruchom dev server (przez preview_start / `.claude/launch.json`, NIE przez Bash) i wejdź na `http://localhost:5001/admin/konkursy/2/edytuj` zalogowany jako admin. Sprawdź:
1. Karta „Wykluczeni z losowania zwycięzców" widoczna w kolumnie bocznej.
2. Wpisanie ≥2 znaków w wyszukiwarkę pokazuje wyniki; klik dodaje chip; × usuwa.
3. Zapis formularza → ponowne wejście w edycję pokazuje zachowane chipy (prefill).
4. Toggle light/dark — oba czytelne (read_console_messages bez błędów, screenshot jako dowód).
5. Ekran `/admin/konkursy/2/losowanie` (jeśli konkurs losowalny) i modal rozkładu — wykluczeni mają badge „wykluczony".

- [ ] **Step 10: Pełny zestaw testów kontestów**

Run: `python -m pytest tests/ -k contests -q`
Expected: PASS (wszystkie).

- [ ] **Step 11: Commit**

```bash
git add templates/admin/contests/form.html static/js/pages/admin/contest-form.js \
        static/js/pages/admin/contest-distribution.js static/js/pages/admin/contest-draw.js \
        static/css/pages/admin/contests.css tests/test_contests_admin_ui.py
git commit -m "feat(contests): UI pickera wykluczeń + badge w widokach admina

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Uwagi końcowe

- **NIE pushować bez zgody** — push = auto-deploy na produkcję. Po implementacji i pełnym przetestowaniu Konrad decyduje o wdrożeniu (migracja `flask db upgrade` na serwerze idzie z webhookiem).
- Migracja jest już uwzględniona w Task 1; na produkcji zastosuje się automatycznie przy deployu.
- `participants()` celowo NIE jest zmieniane — to gwarancja, że wykluczeni nadal przewijają się w bębnie/ruletce.
