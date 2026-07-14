import random


class _FakeRng:
    def __init__(self, value): self._v = value
    def uniform(self, a, b): return self._v


def test_weighted_pick_boundaries(app):
    from modules.contests.utils import _weighted_pick
    items = [('a', 10), ('b', 30), ('c', 60)]  # total 100
    assert _weighted_pick(items, _FakeRng(0)) == 0      # pick=0 -> pierwszy
    assert _weighted_pick(items, _FakeRng(10)) == 0     # granica a (acc=10)
    assert _weighted_pick(items, _FakeRng(10.5)) == 1   # tuż za a -> b
    assert _weighted_pick(items, _FakeRng(40)) == 1     # granica b (acc=40)
    assert _weighted_pick(items, _FakeRng(100)) == 2    # pick=total -> ostatni
    assert _weighted_pick([('x', 5)], _FakeRng(5)) == 0 # single element


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


def test_excluded_user_ids_property(db, make_product, make_user):
    c = _contest(db, make_product, make_user)
    u = make_user()
    assert c.excluded_user_ids == set()
    _exclude(db, c, u)
    assert c.excluded_user_ids == {u.id}
