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


def test_create_contest_with_prize_set(client, db, make_user, make_product, login):
    """POST prize_product_id[] + prize_quantity[] tworzy ContestPrize z poprawnymi ilościami."""
    from modules.contests.models import Contest, ContestPrize
    login(_admin(make_user))
    prod1 = make_product(name='Album A')
    prod2 = make_product(name='Photocard B')
    resp = client.post('/admin/konkursy/nowy', data={
        'name': 'Konkurs Kpop',
        'num_winners': 1, 'ticket_min': 1, 'ticket_max': 50,
        'cooldown_minutes': 1440,
        'prize_product_id[]': [str(prod1.id), str(prod2.id)],
        'prize_quantity[]': ['2', '3'],
    }, follow_redirects=True)
    assert resp.status_code == 200
    c = Contest.query.filter_by(name='Konkurs Kpop').first()
    assert c is not None
    prizes = ContestPrize.query.filter_by(contest_id=c.id).order_by(ContestPrize.id).all()
    assert len(prizes) == 2
    assert prizes[0].product_id == prod1.id and prizes[0].quantity == 2
    assert prizes[1].product_id == prod2.id and prizes[1].quantity == 3
    assert '2×' in c.prize_summary and 'Album A' in c.prize_summary


def test_prize_set_replaced_on_edit(client, db, make_user, make_product, login):
    """Edycja konkursu przebudowuje zestaw nagród."""
    from modules.contests.models import Contest, ContestPrize
    login(_admin(make_user))
    prod1 = make_product(name='Stare')
    prod2 = make_product(name='Nowe')
    c = Contest(name='Test', prize_product_id=prod1.id, ticket_min=1, ticket_max=50,
                num_winners=1, cooldown_minutes=1440, status='szkic')
    db.session.add(c); db.session.commit()
    # Dodaj stary ContestPrize
    from modules.contests.models import ContestPrize as CP
    db.session.add(CP(contest_id=c.id, product_id=prod1.id, quantity=1))
    db.session.commit()
    # Edytuj — zastąp zestawem z prod2
    resp = client.post(f'/admin/konkursy/{c.id}/edytuj', data={
        'name': 'Test', 'num_winners': 1, 'ticket_min': 1, 'ticket_max': 50,
        'cooldown_minutes': 1440,
        'prize_product_id[]': [str(prod2.id)],
        'prize_quantity[]': ['5'],
    }, follow_redirects=True)
    assert resp.status_code == 200
    prizes = ContestPrize.query.filter_by(contest_id=c.id).all()
    assert len(prizes) == 1
    assert prizes[0].product_id == prod2.id and prizes[0].quantity == 5
