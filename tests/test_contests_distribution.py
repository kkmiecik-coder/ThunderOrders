from datetime import timedelta


def _now():
    from modules.orders.models import get_local_now
    return get_local_now()


def _contest(db, make_product, make_user, **kw):
    from modules.contests.models import Contest
    admin = make_user(role='admin'); prod = make_product()
    fields = dict(name='C', prize_product_id=prod.id, ticket_min=1, ticket_max=500,
                  status='aktywny', created_by_admin_id=admin.id)
    fields.update(kw)
    c = Contest(**fields)
    db.session.add(c); db.session.commit()
    return c


def test_draw_locked_true_when_window_open(db, make_product, make_user):
    from modules.contests.utils import draw_locked
    c = _contest(db, make_product, make_user, ends_at=_now() + timedelta(hours=2))
    assert draw_locked(c) is True


def test_draw_locked_false_without_ends_at(db, make_product, make_user):
    from modules.contests.utils import draw_locked
    c = _contest(db, make_product, make_user, ends_at=None)
    assert draw_locked(c) is False


def test_draw_locked_false_when_window_passed(db, make_product, make_user):
    from modules.contests.utils import draw_locked
    c = _contest(db, make_product, make_user, ends_at=_now() - timedelta(hours=1))
    assert draw_locked(c) is False


def test_draw_locked_false_when_not_active(db, make_product, make_user):
    from modules.contests.utils import draw_locked
    c = _contest(db, make_product, make_user, status='rozlosowany',
                 ends_at=_now() + timedelta(hours=2))
    assert draw_locked(c) is False


def test_spin_buckets_sum_to_100(db, make_product, make_user):
    from modules.contests.utils import spin_distribution_buckets
    c = _contest(db, make_product, make_user)  # 1..500
    buckets = spin_distribution_buckets(c)
    assert len(buckets) == 16
    total = sum(b['pct'] for b in buckets)
    assert abs(total - 100.0) < 0.5


def test_spin_buckets_are_skewed_to_min(db, make_product, make_user):
    from modules.contests.utils import spin_distribution_buckets
    c = _contest(db, make_product, make_user)  # moda = ticket_min => malejąco
    buckets = spin_distribution_buckets(c)
    assert buckets[0]['pct'] > buckets[-1]['pct']
    # każdy koszyk ma poprawny kształt
    assert set(buckets[0].keys()) == {'label', 'from', 'to', 'pct'}


def test_spin_buckets_degenerate_range(db, make_product, make_user):
    from modules.contests.utils import spin_distribution_buckets
    from modules.contests.models import Contest
    c = _contest(db, make_product, make_user)
    c.ticket_min = 5; c.ticket_max = 5; db.session.commit()
    buckets = spin_distribution_buckets(c)
    assert buckets == [{'label': '5', 'from': 5, 'to': 5, 'pct': 100.0}]
