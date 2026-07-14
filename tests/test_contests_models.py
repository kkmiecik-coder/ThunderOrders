"""Tests for Contest model and prize_summary property."""
from datetime import datetime


# ---------------------------------------------------------------------------
# prize_summary — new two-level structure
# ---------------------------------------------------------------------------

def test_prize_summary_single_entry(db, make_product, make_user):
    """prize_summary zwraca 'q× name' dla pojedynczej pozycji."""
    from modules.contests.models import Contest, ContestPrize, ContestPrizeItem
    admin = make_user(role='admin')
    prod = make_product(name='Album ATE')
    c = Contest(name='KSummary', ticket_min=1, ticket_max=50, created_by_admin_id=admin.id)
    db.session.add(c); db.session.commit()
    prize = ContestPrize(contest_id=c.id, name=None, quantity=2)
    db.session.add(prize); db.session.flush()
    db.session.add(ContestPrizeItem(prize_id=prize.id, product_id=prod.id, quantity=1))
    db.session.commit()
    db.session.refresh(c)
    assert c.prize_summary == '2× Album ATE'


def test_prize_summary_set_entry(db, make_product, make_user):
    """prize_summary zwraca 'q× SetName (ia× a, ib× b)' dla zestawu."""
    from modules.contests.models import Contest, ContestPrize, ContestPrizeItem
    admin = make_user(role='admin')
    p1 = make_product(name='Album A')
    p2 = make_product(name='Photocard B')
    c = Contest(name='SetContest', ticket_min=1, ticket_max=50, created_by_admin_id=admin.id)
    db.session.add(c); db.session.commit()
    prize = ContestPrize(contest_id=c.id, name='Zestaw debiutancki', quantity=1)
    db.session.add(prize); db.session.flush()
    db.session.add(ContestPrizeItem(prize_id=prize.id, product_id=p1.id, quantity=2))
    db.session.add(ContestPrizeItem(prize_id=prize.id, product_id=p2.id, quantity=3))
    db.session.commit()
    db.session.refresh(c)
    summary = c.prize_summary
    assert 'Zestaw debiutancki' in summary
    assert '2× Album A' in summary
    assert '3× Photocard B' in summary


def test_prize_summary_multiple_entries(db, make_product, make_user):
    """prize_summary łączy wiele wpisów średnikiem."""
    from modules.contests.models import Contest, ContestPrize, ContestPrizeItem
    admin = make_user(role='admin')
    p1 = make_product(name='Album ATE')
    p2 = make_product(name='Photocard HH')
    c = Contest(name='KSummary2', ticket_min=1, ticket_max=50, created_by_admin_id=admin.id)
    db.session.add(c); db.session.commit()

    prize1 = ContestPrize(contest_id=c.id, name=None, quantity=2)
    db.session.add(prize1); db.session.flush()
    db.session.add(ContestPrizeItem(prize_id=prize1.id, product_id=p1.id, quantity=1))

    prize2 = ContestPrize(contest_id=c.id, name=None, quantity=1)
    db.session.add(prize2); db.session.flush()
    db.session.add(ContestPrizeItem(prize_id=prize2.id, product_id=p2.id, quantity=1))
    db.session.commit()
    db.session.refresh(c)
    summary = c.prize_summary
    assert '2× Album ATE' in summary
    assert '1× Photocard HH' in summary


def test_prize_summary_falls_back_to_prize_product(db, make_product, make_user):
    """prize_summary bez ContestPrize zwraca nazwę legacy prize_product."""
    from modules.contests.models import Contest
    admin = make_user(role='admin')
    prod = make_product(name='Legacy Klawiatura')
    c = Contest(name='LegacyContest', prize_product_id=prod.id,
                ticket_min=1, ticket_max=50, created_by_admin_id=admin.id)
    db.session.add(c); db.session.commit()
    assert c.prize_summary == 'Legacy Klawiatura'


def test_prize_summary_returns_none_when_empty(db, make_user):
    """prize_summary bez nagród i bez prize_product → None."""
    from modules.contests.models import Contest
    admin = make_user(role='admin')
    c = Contest(name='Empty', ticket_min=1, ticket_max=50, created_by_admin_id=admin.id)
    db.session.add(c); db.session.commit()
    assert c.prize_summary is None


# ---------------------------------------------------------------------------
# ContestPrize.is_set property
# ---------------------------------------------------------------------------

def test_contest_prize_is_set_false_when_name_none(db, make_user):
    from modules.contests.models import Contest, ContestPrize, ContestPrizeItem
    admin = make_user(role='admin')
    c = Contest(name='X', ticket_min=1, ticket_max=50, created_by_admin_id=admin.id)
    db.session.add(c); db.session.commit()
    p = ContestPrize(contest_id=c.id, name=None, quantity=1)
    db.session.add(p); db.session.commit()
    assert p.is_set is False


def test_contest_prize_is_set_true_when_named(db, make_user):
    from modules.contests.models import Contest, ContestPrize
    admin = make_user(role='admin')
    c = Contest(name='X', ticket_min=1, ticket_max=50, created_by_admin_id=admin.id)
    db.session.add(c); db.session.commit()
    p = ContestPrize(contest_id=c.id, name='Zestaw', quantity=1)
    db.session.add(p); db.session.commit()
    assert p.is_set is True


# ---------------------------------------------------------------------------
# Legacy fields + other model tests
# ---------------------------------------------------------------------------

def test_contest_defaults(db, make_product, make_user):
    from modules.contests.models import Contest
    admin = make_user(role='admin')
    prod = make_product()
    c = Contest(name='Klawiatura', prize_product_id=prod.id,
                ticket_min=1, ticket_max=50, created_by_admin_id=admin.id)
    db.session.add(c)
    db.session.commit()
    assert c.id is not None
    assert c.status == 'szkic'
    assert c.num_winners == 1
    assert c.cooldown_minutes == 1440
    assert isinstance(c.created_at, datetime)


def test_spin_and_winner_persist(db, make_product, make_user):
    from modules.contests.models import Contest, ContestSpin, ContestWinner
    admin = make_user(role='admin'); user = make_user(); prod = make_product()
    c = Contest(name='X', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                created_by_admin_id=admin.id)
    db.session.add(c); db.session.commit()
    s = ContestSpin(contest_id=c.id, user_id=user.id, tickets_won=20)
    w = ContestWinner(contest_id=c.id, user_id=user.id, place=1,
                      tickets_at_draw=20, chance_pct=100.0, prize_product_id=prod.id)
    db.session.add_all([s, w]); db.session.commit()
    assert s.id and w.id
    assert s.tickets_won == 20
    assert w.place == 1
    assert w.tickets_at_draw == 20
    assert float(w.chance_pct) == 100.0


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
