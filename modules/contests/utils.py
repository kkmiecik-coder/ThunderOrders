from datetime import timedelta

from sqlalchemy import func

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
