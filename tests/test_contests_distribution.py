from datetime import timedelta


def _now():
    from modules.orders.models import get_local_now
    return get_local_now()


def _contest(db, make_product, make_user, **kw):
    from modules.contests.models import Contest
    admin = make_user(role='admin'); prod = make_product()
    fields = dict(name='C', prize_product_id=prod.id, ticket_min=1, ticket_max=500,
                  status='aktywny', created_by_admin_id=admin.id)
    fields.update(kw)
    c = Contest(**fields)
    db.session.add(c); db.session.commit()
    return c


def test_draw_locked_true_when_window_open(db, make_product, make_user):
    from modules.contests.utils import draw_locked
    c = _contest(db, make_product, make_user, ends_at=_now() + timedelta(hours=2))
    assert draw_locked(c) is True


def test_draw_locked_false_without_ends_at(db, make_product, make_user):
    from modules.contests.utils import draw_locked
    c = _contest(db, make_product, make_user, ends_at=None)
    assert draw_locked(c) is False


def test_draw_locked_false_when_window_passed(db, make_product, make_user):
    from modules.contests.utils import draw_locked
    c = _contest(db, make_product, make_user, ends_at=_now() - timedelta(hours=1))
    assert draw_locked(c) is False


def test_draw_locked_false_when_not_active(db, make_product, make_user):
    from modules.contests.utils import draw_locked
    c = _contest(db, make_product, make_user, status='rozlosowany',
                 ends_at=_now() + timedelta(hours=2))
    assert draw_locked(c) is False


def test_spin_buckets_sum_to_100(db, make_product, make_user):
    from modules.contests.utils import spin_distribution_buckets
    c = _contest(db, make_product, make_user)  # 1..500
    buckets = spin_distribution_buckets(c)
    assert len(buckets) == 16
    total = sum(b['pct'] for b in buckets)
    assert abs(total - 100.0) < 0.5


def test_spin_buckets_are_skewed_to_min(db, make_product, make_user):
    from modules.contests.utils import spin_distribution_buckets
    c = _contest(db, make_product, make_user)  # moda = ticket_min => malejąco
    buckets = spin_distribution_buckets(c)
    assert buckets[0]['pct'] > buckets[-1]['pct']
    # każdy koszyk ma poprawny kształt
    assert set(buckets[0].keys()) == {'label', 'from', 'to', 'pct'}


def test_spin_buckets_degenerate_range(db, make_product, make_user):
    from modules.contests.utils import spin_distribution_buckets
    from modules.contests.models import Contest
    c = _contest(db, make_product, make_user)
    c.ticket_min = 5; c.ticket_max = 5; db.session.commit()
    buckets = spin_distribution_buckets(c)
    assert buckets == [{'label': '5', 'from': 5, 'to': 5, 'pct': 100.0}]


def _admin(make_user):
    return make_user(role='admin')


def _spin(db, c, u, tickets):
    from modules.contests.models import ContestSpin
    s = ContestSpin(contest_id=c.id, user_id=u.id, tickets_won=tickets)
    db.session.add(s); db.session.commit()
    return s


def test_distribution_endpoint_shape(client, db, make_product, make_user, login):
    c = _contest(db, make_product, make_user)
    u1, u2 = make_user(), make_user()
    _spin(db, c, u1, 40); _spin(db, c, u2, 10)
    login(_admin(make_user))
    resp = client.get(f'/admin/konkursy/{c.id}/rozklad')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['config'] == {'ticket_min': 1, 'ticket_max': 500}
    assert data['pool'] == 50
    assert len(data['spin_buckets']) == 16
    # posortowane malejąco po tickets
    assert [p['tickets'] for p in data['participants']] == [40, 10]
    assert data['participants'][0]['chance_pct'] == 80.0


def test_distribution_endpoint_empty_pool(client, db, make_product, make_user, login):
    c = _contest(db, make_product, make_user)
    login(_admin(make_user))
    data = client.get(f'/admin/konkursy/{c.id}/rozklad').get_json()
    assert data['pool'] == 0
    assert data['participants'] == []


def test_distribution_requires_admin(client, db, make_product, make_user, login):
    c = _contest(db, make_product, make_user)
    login(make_user(role='client'))
    assert client.get(f'/admin/konkursy/{c.id}/rozklad').status_code == 403


def test_draw_screen_blocked_when_window_open(client, db, make_product, make_user, login):
    from datetime import timedelta
    c = _contest(db, make_product, make_user, ends_at=_now() + timedelta(hours=2))
    login(_admin(make_user))
    resp = client.get(f'/admin/konkursy/{c.id}/losowanie')
    assert resp.status_code == 302
    assert '/admin/konkursy' in resp.headers['Location']


def test_draw_screen_open_when_no_window(client, db, make_product, make_user, login):
    c = _contest(db, make_product, make_user, ends_at=None)
    login(_admin(make_user))
    assert client.get(f'/admin/konkursy/{c.id}/losowanie').status_code == 200


def test_list_context_has_draw_locked_flag(client, db, make_product, make_user, login):
    from datetime import timedelta
    c = _contest(db, make_product, make_user, ends_at=_now() + timedelta(hours=2))
    login(_admin(make_user))
    resp = client.get('/admin/konkursy')
    assert resp.status_code == 200
    # przycisk Losowanie renderowany jako disabled (patrz Task 3 dot. markup);
    # tu sprawdzamy tylko, że strona się renderuje z aktywnym konkursem w oknie
    assert b'Losowanie' in resp.data


def test_list_shows_dist_button_for_active(client, db, make_product, make_user, login):
    c = _contest(db, make_product, make_user, ends_at=None)
    login(_admin(make_user))
    html = client.get('/admin/konkursy').data.decode()
    assert 'ca-action--dist' in html
    assert f'data-cid="{c.id}"' in html


def test_list_draw_button_disabled_when_window_open(client, db, make_product, make_user, login):
    from datetime import timedelta
    c = _contest(db, make_product, make_user, ends_at=_now() + timedelta(hours=2))
    login(_admin(make_user))
    html = client.get('/admin/konkursy').data.decode()
    assert 'ca-action--disabled' in html
    # brak klikalnego linku do ekranu losowania dla tego konkursu
    assert f'/admin/konkursy/{c.id}/losowanie' not in html


def test_list_draw_button_active_when_no_window(client, db, make_product, make_user, login):
    c = _contest(db, make_product, make_user, ends_at=None)
    login(_admin(make_user))
    html = client.get('/admin/konkursy').data.decode()
    assert f'/admin/konkursy/{c.id}/losowanie' in html
    assert 'ca-action--disabled' not in html
