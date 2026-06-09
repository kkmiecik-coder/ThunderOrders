def _active(db, make_product, **kw):
    from modules.contests.models import Contest
    from modules.products.models import Product
    prod = Product.query.first() or None
    c = Contest(name='K', ticket_min=5, ticket_max=5, status='aktywny',
                prize_product_id=(prod.id if prod else None), **kw)
    db.session.add(c); db.session.commit()
    return c


def test_spin_requires_eligibility(client, db, make_user, make_product, login):
    c = _active(db, make_product, eligibility_min_orders=1)
    u = make_user(); login(u)
    resp = client.post('/konkurs/spin')
    assert resp.get_json()['success'] is False   # brak zamówień


def test_spin_grants_tickets_in_range(client, db, make_user, make_product, make_order, login):
    from modules.contests.models import ContestSpin
    c = _active(db, make_product, eligibility_min_orders=1)  # min=max=5
    u = make_user(); make_order(u); login(u)
    resp = client.post('/konkurs/spin')
    body = resp.get_json()
    assert body['success'] is True
    assert body['tickets_won'] == 5
    assert body['my_total'] == 5
    assert ContestSpin.query.filter_by(contest_id=c.id, user_id=u.id).count() == 1


def test_spin_blocked_during_cooldown(client, db, make_user, make_product, make_order, login):
    c = _active(db, make_product, eligibility_min_orders=1, cooldown_minutes=60)
    u = make_user(); make_order(u); login(u)
    assert client.post('/konkurs/spin').get_json()['success'] is True
    second = client.post('/konkurs/spin').get_json()
    assert second['success'] is False   # cooldown
