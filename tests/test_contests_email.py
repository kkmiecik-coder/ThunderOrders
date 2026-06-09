def test_winner_gets_notification_and_email(db, make_user, make_product, monkeypatch):
    import modules.contests.utils as cu
    from modules.contests.models import Contest, ContestSpin
    from modules.notifications.models import Notification

    sent = []
    monkeypatch.setattr(cu, 'send_contest_win_email',
                        lambda **kw: sent.append(kw), raising=False)

    prod = make_product(name='Klawiatura')
    c = Contest(name='Konkurs', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, status='aktywny')
    db.session.add(c); db.session.commit()
    u = make_user(email='winner@example.com')
    db.session.add(ContestSpin(contest_id=c.id, user_id=u.id, tickets_won=10))
    db.session.commit()

    import random
    cu.draw_winners(c, rng=random.Random(1))

    assert Notification.query.filter_by(user_id=u.id,
                                        notification_type='contest_win').count() == 1
    assert len(sent) == 1
    assert sent[0]['user_email'] == 'winner@example.com'
    assert sent[0]['contest_name'] == 'Konkurs'
    assert sent[0]['prize_name'] == 'Klawiatura'


def test_email_failure_does_not_break_draw(db, make_user, make_product, monkeypatch):
    import modules.contests.utils as cu
    from modules.contests.models import Contest, ContestSpin, ContestWinner
    from modules.notifications.models import Notification

    def _boom(**kw):
        raise RuntimeError('SMTP down')
    monkeypatch.setattr(cu, 'send_contest_win_email', _boom, raising=False)

    prod = make_product(name='Nagroda')
    c = Contest(name='K', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, status='aktywny')
    db.session.add(c); db.session.commit()
    u = make_user()
    db.session.add(ContestSpin(contest_id=c.id, user_id=u.id, tickets_won=10))
    db.session.commit()

    import random
    winners = cu.draw_winners(c, rng=random.Random(1))
    assert len(winners) == 1                      # losowanie się powiodło mimo błędu maila
    assert ContestWinner.query.filter_by(contest_id=c.id).count() == 1
    assert Notification.query.filter_by(user_id=u.id, notification_type='contest_win').count() == 1
    db.session.refresh(c); assert c.status == 'rozlosowany'
