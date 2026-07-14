import logging
import random as _random
from datetime import timedelta

from sqlalchemy import func

from extensions import db
from modules.orders.models import Order, get_local_now
from flask import url_for
from utils.email_sender import send_contest_win_email

logger = logging.getLogger(__name__)


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


def draw_ticket_count(contest, rng=None):
    """Losowa liczba losów dla pojedynczego spinu.

    Rozkład SKOŚNY ku ticket_min (wierzchołek trójkąta przy minimum) — niższe
    wartości są częstsze, wyższe rzadsze. Np. dla 1–500 wartości >400 wypadają
    kilka %, a nie ~20% jak przy rozkładzie równomiernym. rng wstrzykiwalny dla testów.
    """
    rng = rng or _random.SystemRandom()
    n = int(round(rng.triangular(contest.ticket_min, contest.ticket_max, contest.ticket_min)))
    return max(contest.ticket_min, min(contest.ticket_max, n))


def get_active_contest():
    from modules.contests.models import Contest
    return Contest.query.filter_by(status='aktywny').first()


def get_display_contest():
    """Konkurs do pokazania w widgecie: aktywny, a jeśli brak — ostatni rozstrzygnięty (do 14 dni)."""
    from modules.contests.models import Contest
    active = Contest.query.filter_by(status='aktywny').first()
    if active:
        return active
    cutoff = get_local_now() - timedelta(days=14)
    return Contest.query.filter(Contest.status == 'rozlosowany', Contest.updated_at >= cutoff) \
        .order_by(Contest.id.desc()).first()


def get_winners(contest):
    from modules.contests.models import ContestWinner
    return ContestWinner.query.filter_by(contest_id=contest.id).order_by(ContestWinner.place).all()


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


def excluded_user_ids(contest):
    """Zbiór ID użytkowników wykluczonych z losowania zwycięzców tego konkursu."""
    from modules.contests.models import ContestExcludedUser
    rows = db.session.query(ContestExcludedUser.user_id) \
        .filter(ContestExcludedUser.contest_id == contest.id).all()
    return {uid for (uid,) in rows}


def draw_winners(contest, rng=None):
    """Autorytatywne, ważone losowanie bez powtórzeń. Idempotentne."""
    from modules.contests.models import ContestWinner
    if contest.status == 'rozlosowany':
        return ContestWinner.query.filter_by(contest_id=contest.id) \
            .order_by(ContestWinner.place).all()

    rng = rng or _random.SystemRandom()
    excluded = excluded_user_ids(contest)
    # Wykluczeni pozostają w participants() (widoczni w bębnie), ale NIE mogą wygrać —
    # usuwamy ich z puli losowalnej i z mianownika szans.
    pool_participants = [(u, t) for (u, t) in participants(contest) if u.id not in excluded]
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
    """Powiadomienie in-app + e-mail do zwycięzcy. Błąd nigdy nie blokuje losowania."""
    from modules.notifications.models import Notification
    from modules.auth.models import User
    user = db.session.get(User, winner.user_id)
    prize_name = contest.prize_summary or 'nagroda'
    try:
        link = url_for('contests.client_contest', _external=True)
    except Exception:
        link = 'https://thunderorders.cloud/konkurs'

    try:
        db.session.add(Notification(
            user_id=winner.user_id,
            title='Wygrałeś w konkursie!',
            body=f'Twoja nagroda: {prize_name}.',
            url=link,
            notification_type='contest_win',
        ))
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.warning("[_notify_winner] powiadomienie dla user_id=%s nieutworzone: %s: %s",
                       winner.user_id, type(exc).__name__, exc)

    try:
        send_contest_win_email(
            user_email=user.email,
            user_name=getattr(user, 'first_name', None),
            contest_name=contest.name,
            prize_name=prize_name,
            url=link,
        )
    except Exception as exc:
        logger.warning("[_notify_winner] email do user_id=%s niewyslany: %s: %s",
                       winner.user_id, type(exc).__name__, exc)


def count_participants(contest):
    """Liczba unikalnych uczestników (osób, które zakręciły) w konkursie."""
    from modules.contests.models import ContestSpin
    return db.session.query(func.count(func.distinct(ContestSpin.user_id))) \
        .filter(ContestSpin.contest_id == contest.id).scalar() or 0


def widget_context(contest, user):
    """Dane dla widgetu/strony klienta (bez puli i %)."""
    if contest is None:
        return None
    nxt = get_next_spin_at(contest, user)
    is_open = spins_open(contest)
    eligible = is_eligible(contest, user)
    cooldown_ok = (nxt is None or get_local_now() >= nxt)

    # Determine display state
    if contest.status == 'rozlosowany':
        state = 'rozstrzygniete'
    elif not is_open:
        state = 'zamkniete'
    else:
        state = 'trwa'

    ctx = {
        'contest': contest,
        'my_tickets': get_user_tickets(contest, user),
        'participants': count_participants(contest),
        'eligible': eligible,
        'can_spin': is_open and eligible and cooldown_ok,
        'next_spin_at': nxt.isoformat() if nxt else None,
        'spins_open': is_open,
        'state': state,
    }

    if state == 'rozstrzygniete':
        winners = get_winners(contest)
        ctx['winners'] = winners
        ctx['did_i_win'] = any(w.user_id == user.id for w in winners)

    return ctx


def draw_locked(contest):
    """Czy losowanie jest zablokowane, bo trwa zaplanowane okno (ends_at w przyszłości).

    Jedno źródło prawdy dla: przycisku na liście, wejścia na ekran losowania i POST /losuj.
    Konkursy bez ends_at (losowanie „na żywo") NIE są blokowane.
    """
    return (contest.status == 'aktywny'
            and contest.ends_at is not None
            and get_local_now() < contest.ends_at)


def spin_histogram(contest, bins=10):
    """Empiryczny histogram realnych losowań: ile spinów wpadło w każdy przedział losów.

    Zakres [ticket_min, ticket_max] dzielony na do `bins` równych przedziałów całkowitych
    (adaptacyjnie: mniej przedziałów gdy zakres wąski — najwyżej jeden na wartość całkowitą).
    Zwraca listę {'label', 'from', 'to', 'count'} — count to liczba spinów w danym przedziale.
    Pokazuje, jakie liczby losów ludzie faktycznie najczęściej wylosowali.
    """
    from modules.contests.models import ContestSpin
    a = int(contest.ticket_min)
    b = int(contest.ticket_max)
    if b < a:
        b = a

    total_values = b - a + 1
    n = max(1, min(bins, total_values))

    # Równy podział całkowitego zakresu [a, b] na n kolejnych przedziałów (inclusive).
    base, rem = divmod(total_values, n)
    edges = []  # (start, end) inclusive
    start = a
    for i in range(n):
        width = base + (1 if i < rem else 0)
        end = start + width - 1
        edges.append((start, end))
        start = end + 1

    counts = [0] * n
    tickets = db.session.query(ContestSpin.tickets_won) \
        .filter(ContestSpin.contest_id == contest.id).all()
    for (t,) in tickets:
        t = int(t)
        if t <= edges[0][1]:
            counts[0] += 1
        elif t >= edges[-1][0]:
            counts[-1] += 1
        else:
            for i, (s, e) in enumerate(edges):
                if s <= t <= e:
                    counts[i] += 1
                    break

    out = []
    for (s, e), c in zip(edges, counts):
        label = str(s) if s == e else f'{s}–{e}'
        out.append({'label': label, 'from': s, 'to': e, 'count': c})
    return out
