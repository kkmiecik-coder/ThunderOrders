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
        total = _orders_base(uid).with_entities(
            func.coalesce(func.sum(Order.total_amount), 0)).scalar()
        if float(total) < float(contest.eligibility_min_total_value):
            return False

    if contest.eligibility_active_within_days:
        cutoff = get_local_now() - timedelta(days=contest.eligibility_active_within_days)
        recent = _orders_base(uid).filter(Order.created_at >= cutoff).count()
        if recent == 0:
            return False

    return True


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
