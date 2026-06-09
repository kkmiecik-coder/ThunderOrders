def _admin(make_user):
    return make_user(role='admin')


def test_list_requires_admin(client, make_user, login):
    login(make_user(role='client'))
    assert client.get('/admin/konkursy').status_code == 403


def test_create_contest(client, db, make_user, make_product, login):
    from modules.contests.models import Contest
    login(_admin(make_user))
    prod = make_product()
    resp = client.post('/admin/konkursy/nowy', data={
        'name': 'Klawiatura', 'prize_product_id': prod.id,
        'num_winners': 1, 'ticket_min': 1, 'ticket_max': 50,
        'cooldown_minutes': 1440, 'eligibility_min_orders': 1,
    }, follow_redirects=True)
    assert resp.status_code == 200
    c = Contest.query.filter_by(name='Klawiatura').first()
    assert c is not None and c.status == 'szkic'


def test_activate_blocks_second_active(client, db, make_user, make_product, login):
    from modules.contests.models import Contest
    login(_admin(make_user))
    prod = make_product()
    c1 = Contest(name='A', prize_product_id=prod.id, ticket_min=1, ticket_max=50, status='aktywny')
    c2 = Contest(name='B', prize_product_id=prod.id, ticket_min=1, ticket_max=50, status='szkic')
    db.session.add_all([c1, c2])
    db.session.commit()
    resp = client.post(f'/admin/konkursy/{c2.id}/aktywuj', follow_redirects=True)
    db.session.refresh(c2)
    assert c2.status == 'szkic'   # zablokowane — już jest aktywny


def test_activate_happy_path(client, db, make_user, make_product, login):
    from modules.contests.models import Contest
    login(make_user(role='admin')); prod = make_product()
    c = Contest(name='A', prize_product_id=prod.id, ticket_min=1, ticket_max=50, status='szkic')
    db.session.add(c); db.session.commit()
    resp = client.post(f'/admin/konkursy/{c.id}/aktywuj', follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(c)
    assert c.status == 'aktywny'   # brak innego aktywnego => aktywuje


def test_create_rejects_ticket_max_below_min(client, db, make_user, make_product, login):
    from modules.contests.models import Contest
    login(make_user(role='admin')); prod = make_product()
    resp = client.post('/admin/konkursy/nowy', data={
        'name': 'Zly zakres', 'prize_product_id': prod.id,
        'num_winners': 1, 'ticket_min': 50, 'ticket_max': 1,
        'cooldown_minutes': 1440,
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert Contest.query.filter_by(name='Zly zakres').first() is None  # walidacja odrzuciła


def test_edit_saves_changes(client, db, make_user, make_product, login):
    from modules.contests.models import Contest
    login(make_user(role='admin')); prod = make_product()
    c = Contest(name='Stara', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, cooldown_minutes=1440, status='szkic')
    db.session.add(c); db.session.commit()
    cid = c.id
    resp = client.post(f'/admin/konkursy/{cid}/edytuj', data={
        'name': 'Nowa', 'prize_product_id': prod.id,
        'num_winners': 2, 'ticket_min': 5, 'ticket_max': 25,
        'cooldown_minutes': 720,
    }, follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(c)
    assert c.name == 'Nowa' and c.num_winners == 2 and c.ticket_max == 25


def test_draw_endpoint(client, db, make_user, make_product, login):
    from modules.contests.models import Contest, ContestSpin, ContestWinner
    login(make_user(role='admin')); prod = make_product()
    c = Contest(name='A', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, status='aktywny')
    db.session.add(c); db.session.commit()
    u = make_user()
    db.session.add(ContestSpin(contest_id=c.id, user_id=u.id, tickets_won=10))
    db.session.commit()
    resp = client.post(f'/admin/konkursy/{c.id}/losuj')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert len(body['winners']) == 1
    assert ContestWinner.query.filter_by(contest_id=c.id).count() == 1
    db.session.refresh(c); assert c.status == 'rozlosowany'


def test_draw_blocked_when_spins_open(client, db, make_user, make_product, login):
    from datetime import timedelta
    from modules.auth.models import get_local_now
    from modules.contests.models import Contest, ContestSpin
    login(make_user(role='admin')); prod = make_product()
    c = Contest(name='A', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                status='aktywny', ends_at=get_local_now() + timedelta(hours=1))
    db.session.add(c); db.session.commit()
    db.session.add(ContestSpin(contest_id=c.id, user_id=make_user().id, tickets_won=5))
    db.session.commit()
    resp = client.post(f'/admin/konkursy/{c.id}/losuj')
    assert resp.get_json()['success'] is False   # spiny jeszcze otwarte (ends_at w przyszłości)
