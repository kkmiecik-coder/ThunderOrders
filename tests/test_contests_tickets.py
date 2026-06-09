from datetime import timedelta


def _now():
    from modules.orders.models import get_local_now
    return get_local_now()


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
    _spin(db, c, u, 10, when=_now())
    nxt = get_next_spin_at(c, u)
    assert nxt is not None and nxt > _now()
    assert can_spin(c, u) is False              # w cooldownie


def test_spins_open(db, make_product, make_user):
    from modules.contests.utils import spins_open
    c = _active_contest(db, make_product, make_user)
    assert spins_open(c) is True
    c.ends_at = _now() - timedelta(minutes=1); db.session.commit()
    assert spins_open(c) is False
    c.ends_at = None; c.status = 'szkic'; db.session.commit()
    assert spins_open(c) is False


def test_draw_ticket_count_skewed_low(db, make_product, make_user):
    """Rozkład skośny ku ticket_min — niższe wartości częstsze, wyższe rzadsze."""
    import random
    from modules.contests.models import Contest
    from modules.contests.utils import draw_ticket_count
    prod = make_product()
    c = Contest(name='C', prize_product_id=prod.id, ticket_min=1, ticket_max=500, status='aktywny')
    db.session.add(c); db.session.commit()

    rng = random.Random(42)
    vals = [draw_ticket_count(c, rng=rng) for _ in range(2000)]
    assert all(1 <= v <= 500 for v in vals)                       # w zakresie
    assert sum(vals) / len(vals) < 220                            # średnia poniżej środka (uniform ~250)
    assert sum(1 for v in vals if v > 400) / len(vals) < 0.10     # wysokie rzadkie (uniform ~20%)

    # min == max => deterministyczne
    c2 = Contest(name='C2', prize_product_id=prod.id, ticket_min=7, ticket_max=7, status='aktywny')
    db.session.add(c2); db.session.commit()
    assert draw_ticket_count(c2, rng=random.Random(1)) == 7
