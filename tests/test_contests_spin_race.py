"""Konkurs: równoległe POST /konkurs/spin nie mogą dać dwóch losów w oknie cooldownu.

SQLite w testach nie odtworzy prawdziwej współbieżności, więc symulujemy
wyścig: w chwili, gdy trasa czeka na blokadę wiersza usera, równoległe
żądanie zapisuje swój spin. Trasa musi sprawdzać cooldown dopiero PO
blokadzie, więc ten spin zobaczy i odmówi.
"""


def _active(db, **kw):
    from modules.contests.models import Contest
    c = Contest(name='K', ticket_min=5, ticket_max=5, status='aktywny', **kw)
    db.session.add(c)
    db.session.commit()
    return c


def test_spin_sees_parallel_spin_committed_while_waiting_for_lock(
        client, db, make_user, login, monkeypatch):
    from modules.contests import utils as cu
    from modules.contests.models import ContestSpin

    c = _active(db, cooldown_minutes=60)
    u = make_user()
    login(u)
    real_lock = getattr(cu, 'lock_user_for_spin', None)

    def lock_while_other_request_commits(user_id):
        # równoległe żądanie kończy się, zanim dostaniemy blokadę
        db.session.add(ContestSpin(contest_id=c.id, user_id=u.id, tickets_won=5))
        db.session.commit()
        if real_lock:
            real_lock(user_id)

    monkeypatch.setattr(cu, 'lock_user_for_spin', lock_while_other_request_commits,
                        raising=False)

    body = client.post('/konkurs/spin').get_json()

    assert body['success'] is False
    assert ContestSpin.query.filter_by(contest_id=c.id, user_id=u.id).count() == 1


def test_spin_takes_user_row_lock_before_checks(client, db, make_user, login, monkeypatch):
    """Kolejność: najpierw blokada wiersza usera, potem sprawdzenie can_spin."""
    from modules.contests import utils as cu

    _active(db, cooldown_minutes=60)
    u = make_user()
    login(u)
    events = []

    real_lock = cu.lock_user_for_spin
    real_can_spin = cu.can_spin

    def spy_lock(user_id):
        events.append(('lock', user_id))
        return real_lock(user_id)

    def spy_can_spin(contest, user):
        events.append(('can_spin',))
        return real_can_spin(contest, user)

    monkeypatch.setattr(cu, 'lock_user_for_spin', spy_lock)
    monkeypatch.setattr(cu, 'can_spin', spy_can_spin)

    assert client.post('/konkurs/spin').get_json()['success'] is True
    assert events[0] == ('lock', u.id)
    assert ('can_spin',) in events[1:]


def test_lock_user_for_spin_uses_select_for_update(db, make_user):
    """Na MariaDB blokada to SELECT ... FOR UPDATE na wierszu users."""
    from sqlalchemy.dialects import mysql
    from modules.contests import utils as cu

    u = make_user()
    stmt = cu._user_lock_query(u.id)
    sql = str(stmt.compile(dialect=mysql.dialect()))
    assert 'FOR UPDATE' in sql
    assert 'users' in sql
    cu.lock_user_for_spin(u.id)   # na SQLite: no-op, ale nie może wybuchnąć
