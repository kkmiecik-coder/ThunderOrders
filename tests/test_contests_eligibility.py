from datetime import timedelta


# Lazy wrapper — odracza import, by uniknąć circular import podczas kolekcji pytest.
def _get_local_now():
    from modules.orders.models import get_local_now
    return get_local_now()


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
    make_order(u, created_at=_get_local_now() - timedelta(days=60))
    assert is_eligible(c, u) is False
    make_order(u, created_at=_get_local_now() - timedelta(days=5))
    assert is_eligible(c, u) is True


def test_and_combination(db, make_product, make_user, make_order):
    from modules.contests.utils import is_eligible
    c = _contest(db, make_product, make_user,
                 eligibility_min_orders=2, eligibility_active_within_days=30)
    u = make_user()
    make_order(u, created_at=_get_local_now() - timedelta(days=5))  # 1 zamówienie, świeże
    assert is_eligible(c, u) is False   # brak progu 2
    make_order(u, created_at=_get_local_now() - timedelta(days=5))
    assert is_eligible(c, u) is True


def test_cancelled_excluded_from_total_value(db, make_product, make_user, make_order):
    from modules.contests.utils import is_eligible
    c = _contest(db, make_product, make_user, eligibility_min_total_value=300)
    u = make_user()
    make_order(u, total_amount=500, status='anulowane')  # nie liczy się
    assert is_eligible(c, u) is False
    make_order(u, total_amount=400, status='nowe')
    assert is_eligible(c, u) is True
