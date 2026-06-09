"""
Integration tests for the contest client UI:
 - contest page renders correctly with an active contest
 - contest page renders the empty state when no contest is active
 - dashboard shows the contest widget partial when an active contest exists
"""


def test_contest_page_renders_with_active(client, db, make_user, make_product, login):
    from modules.contests.models import Contest
    prod = make_product()
    c = Contest(
        name='Wielki Konkurs',
        prize_product_id=prod.id,
        ticket_min=1,
        ticket_max=50,
        status='aktywny',
    )
    db.session.add(c)
    db.session.commit()
    login(make_user())
    resp = client.get('/konkurs')
    assert resp.status_code == 200
    assert b'Wielki Konkurs' in resp.data


def test_contest_page_empty_state(client, make_user, login):
    login(make_user())
    resp = client.get('/konkurs')
    assert resp.status_code == 200  # brak aktywnego konkursu => empty state, nadal 200


def test_dashboard_shows_widget_when_active(client, db, make_user, make_product, login):
    from modules.contests.models import Contest
    prod = make_product()
    c = Contest(
        name='Widget Test',
        prize_product_id=prod.id,
        ticket_min=1,
        ticket_max=50,
        status='aktywny',
    )
    db.session.add(c)
    db.session.commit()
    # profile_completed=True is required to bypass the client blueprint's before_request redirect
    login(make_user(profile_completed=True))
    resp = client.get('/client/dashboard')
    assert resp.status_code == 200
    assert b'contest-widget' in resp.data  # partial wyrenderowany
