from datetime import datetime


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
