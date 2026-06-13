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


def test_create_contest_with_single_prize(client, db, make_user, make_product, login):
    """POST prizes_json z pojedynczą pozycją tworzy ContestPrize + ContestPrizeItem."""
    import json
    from modules.contests.models import Contest, ContestPrize, ContestPrizeItem
    login(_admin(make_user))
    prod = make_product(name='Album A')
    prizes_json = json.dumps([
        {'name': None, 'quantity': 2, 'items': [{'product_id': prod.id, 'quantity': 1}]},
    ])
    resp = client.post('/admin/konkursy/nowy', data={
        'name': 'Konkurs Single',
        'num_winners': 1, 'ticket_min': 1, 'ticket_max': 50,
        'cooldown_minutes': 1440,
        'prizes_json': prizes_json,
    }, follow_redirects=True)
    assert resp.status_code == 200
    c = Contest.query.filter_by(name='Konkurs Single').first()
    assert c is not None
    prizes = ContestPrize.query.filter_by(contest_id=c.id).all()
    assert len(prizes) == 1
    assert prizes[0].name is None
    assert prizes[0].quantity == 2
    items = ContestPrizeItem.query.filter_by(prize_id=prizes[0].id).all()
    assert len(items) == 1
    assert items[0].product_id == prod.id
    assert '2× Album A' in c.prize_summary


def test_create_contest_with_set_prize(client, db, make_user, make_product, login):
    """POST prizes_json z zestawem (2 produkty) tworzy prawidłową strukturę."""
    import json
    from modules.contests.models import Contest, ContestPrize, ContestPrizeItem
    login(_admin(make_user))
    prod1 = make_product(name='Album A')
    prod2 = make_product(name='Photocard B')
    prizes_json = json.dumps([{
        'name': 'Zestaw debiutancki',
        'quantity': 1,
        'items': [
            {'product_id': prod1.id, 'quantity': 2},
            {'product_id': prod2.id, 'quantity': 3},
        ],
    }])
    resp = client.post('/admin/konkursy/nowy', data={
        'name': 'Konkurs Set',
        'num_winners': 1, 'ticket_min': 1, 'ticket_max': 50,
        'cooldown_minutes': 1440,
        'prizes_json': prizes_json,
    }, follow_redirects=True)
    assert resp.status_code == 200
    c = Contest.query.filter_by(name='Konkurs Set').first()
    assert c is not None
    prizes = ContestPrize.query.filter_by(contest_id=c.id).all()
    assert len(prizes) == 1
    assert prizes[0].name == 'Zestaw debiutancki'
    assert prizes[0].quantity == 1
    items = ContestPrizeItem.query.filter_by(prize_id=prizes[0].id).order_by(ContestPrizeItem.id).all()
    assert len(items) == 2
    assert items[0].product_id == prod1.id and items[0].quantity == 2
    assert items[1].product_id == prod2.id and items[1].quantity == 3
    summary = c.prize_summary
    assert 'Zestaw debiutancki' in summary
    assert '2× Album A' in summary


def test_prize_replaced_on_edit(client, db, make_user, make_product, login):
    """Edycja konkursu zastępuje nagrody na podstawie prizes_json."""
    import json
    from modules.contests.models import Contest, ContestPrize, ContestPrizeItem
    login(_admin(make_user))
    prod1 = make_product(name='Stare')
    prod2 = make_product(name='Nowe')
    c = Contest(name='Test', prize_product_id=prod1.id, ticket_min=1, ticket_max=50,
                num_winners=1, cooldown_minutes=1440, status='szkic')
    db.session.add(c); db.session.commit()
    # Dodaj stary ContestPrize (single)
    old_prize = ContestPrize(contest_id=c.id, name=None, quantity=1)
    db.session.add(old_prize); db.session.flush()
    from modules.contests.models import ContestPrizeItem as CPI
    db.session.add(CPI(prize_id=old_prize.id, product_id=prod1.id, quantity=1))
    db.session.commit()

    # Edytuj — zastąp nową pozycją z prod2, quantity=5
    prizes_json = json.dumps([
        {'name': None, 'quantity': 5, 'items': [{'product_id': prod2.id, 'quantity': 1}]},
    ])
    resp = client.post(f'/admin/konkursy/{c.id}/edytuj', data={
        'name': 'Test', 'num_winners': 1, 'ticket_min': 1, 'ticket_max': 50,
        'cooldown_minutes': 1440,
        'prizes_json': prizes_json,
    }, follow_redirects=True)
    assert resp.status_code == 200
    prizes = ContestPrize.query.filter_by(contest_id=c.id).all()
    assert len(prizes) == 1
    assert prizes[0].quantity == 5
    items = ContestPrizeItem.query.filter_by(prize_id=prizes[0].id).all()
    assert len(items) == 1
    assert items[0].product_id == prod2.id


def test_prizes_empty_json_clears_prizes(client, db, make_user, make_product, login):
    """prizes_json pusty/brak → brak nagród po zapisie."""
    from modules.contests.models import Contest, ContestPrize
    login(_admin(make_user))
    resp = client.post('/admin/konkursy/nowy', data={
        'name': 'Bez Nagrody',
        'num_winners': 1, 'ticket_min': 1, 'ticket_max': 50,
        'cooldown_minutes': 1440,
        'prizes_json': '',
    }, follow_redirects=True)
    assert resp.status_code == 200
    c = Contest.query.filter_by(name='Bez Nagrody').first()
    assert c is not None
    assert ContestPrize.query.filter_by(contest_id=c.id).count() == 0


def test_prizes_invalid_json_skipped(client, db, make_user, make_product, login):
    """Nieprawidłowy JSON → brak nagród, konkurs tworzony normalnie."""
    from modules.contests.models import Contest, ContestPrize
    login(_admin(make_user))
    resp = client.post('/admin/konkursy/nowy', data={
        'name': 'Zly JSON',
        'num_winners': 1, 'ticket_min': 1, 'ticket_max': 50,
        'cooldown_minutes': 1440,
        'prizes_json': 'not-valid-json',
    }, follow_redirects=True)
    assert resp.status_code == 200
    c = Contest.query.filter_by(name='Zly JSON').first()
    assert c is not None
    assert ContestPrize.query.filter_by(contest_id=c.id).count() == 0


def test_delete_draft(client, db, make_user, make_product, login):
    """DELETE /usun na szkicu usuwa konkurs i przekierowuje na listę."""
    from modules.contests.models import Contest
    login(_admin(make_user)); prod = make_product()
    c = Contest(name='DoUsuniecia', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, cooldown_minutes=1440, status='szkic')
    db.session.add(c); db.session.commit()
    cid = c.id
    resp = client.post(f'/admin/konkursy/{cid}/usun', follow_redirects=True)
    assert resp.status_code == 200
    assert db.session.get(Contest, cid) is None


def test_delete_non_draft_blocked(client, db, make_user, make_product, login):
    """DELETE /usun na aktywnym konkursie nie usuwa go."""
    from modules.contests.models import Contest
    login(_admin(make_user)); prod = make_product()
    c = Contest(name='Aktywny', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, cooldown_minutes=1440, status='aktywny')
    db.session.add(c); db.session.commit()
    cid = c.id
    resp = client.post(f'/admin/konkursy/{cid}/usun', follow_redirects=True)
    assert resp.status_code == 200
    assert db.session.get(Contest, cid) is not None  # zablokowane — nie szkic


def test_prize_entry_with_no_valid_product_skipped(client, db, make_user, make_product, login):
    """Pozycja z nieistniejącym product_id jest pomijana."""
    import json
    from modules.contests.models import Contest, ContestPrize
    login(_admin(make_user))
    prizes_json = json.dumps([
        {'name': None, 'quantity': 1, 'items': [{'product_id': 99999999, 'quantity': 1}]},
    ])
    resp = client.post('/admin/konkursy/nowy', data={
        'name': 'Bez Produktu',
        'num_winners': 1, 'ticket_min': 1, 'ticket_max': 50,
        'cooldown_minutes': 1440,
        'prizes_json': prizes_json,
    }, follow_redirects=True)
    assert resp.status_code == 200
    c = Contest.query.filter_by(name='Bez Produktu').first()
    assert c is not None
    assert ContestPrize.query.filter_by(contest_id=c.id).count() == 0


def test_edit_clears_unchecked_eligibility(client, db, make_user, make_product, login):
    """Odznaczone kryterium (input disabled => nieobecne w POST) ma się WYCZYŚCIĆ, nie zostać.

    Regresja: edycja przez ContestForm(obj=c) zachowywała starą wartość dla pól
    nieobecnych w danych formularza — odznaczenie warunku nie czyściło go.
    """
    from modules.contests.models import Contest
    login(_admin(make_user)); prod = make_product()
    c = Contest(name='K', prize_product_id=prod.id, ticket_min=1, ticket_max=50,
                num_winners=1, cooldown_minutes=1440, status='aktywny',
                eligibility_min_orders=3)
    db.session.add(c); db.session.commit()
    cid = c.id
    # POST bez pola eligibility_min_orders (symuluje odznaczony, wyłączony input)
    resp = client.post(f'/admin/konkursy/{cid}/edytuj', data={
        'name': 'K', 'num_winners': 1, 'ticket_min': 1, 'ticket_max': 50,
        'cooldown_minutes': 1440,
    }, follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(c)
    assert c.eligibility_min_orders is None
