import random as _random
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


def participants(contest):
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
        user = db.session.get(User, uid)
        if user and is_eligible(contest, user):
            out.append((user, total))
    return out


def _weighted_pick(remaining, rng):
    """Zwraca indeks wylosowanego elementu z listy (user, tickets) ważony liczbą losów."""
    total = sum(t for _, t in remaining)
    pick = rng.uniform(0, total)
    acc = 0
    for idx, (_, t) in enumerate(remaining):
        acc += t
        if pick <= acc:
            return idx
    return len(remaining) - 1   # fallback dla edge'a zmiennoprzecinkowego pick==total


def draw_winners(contest, rng=None):
    """Autorytatywne, ważone losowanie bez powtórzeń. Idempotentne."""
    from modules.contests.models import ContestWinner
    if contest.status == 'rozlosowany':
        return ContestWinner.query.filter_by(contest_id=contest.id) \
            .order_by(ContestWinner.place).all()

    rng = rng or _random.SystemRandom()
    pool_participants = participants(contest)
    initial_pool_total = sum(t for _, t in pool_participants)
    n = min(contest.num_winners, len(pool_participants))

    remaining = list(pool_participants)
    winners = []
    for place in range(1, n + 1):
        chosen_idx = _weighted_pick(remaining, rng)
        user, tickets = remaining.pop(chosen_idx)
        chance = round(tickets / initial_pool_total * 100, 3) if initial_pool_total else 0
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
        _notify_winner(contest, w)
    return winners


def _notify_winner(contest, winner):
    """Powiadomienie + e-mail. Pełna implementacja w Task 9."""
    return None
