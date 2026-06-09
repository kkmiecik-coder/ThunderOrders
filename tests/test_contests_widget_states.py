"""
Tests for widget_context() state resolution and get_display_contest() logic.
"""
from datetime import timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_contest(db, prod, status='aktywny', ends_at=None, updated_at=None):
    from modules.contests.models import Contest
    from modules.orders.models import get_local_now
    c = Contest(
        name='Test Konkurs',
        prize_product_id=prod.id,
        ticket_min=1,
        ticket_max=50,
        status=status,
    )
    if ends_at is not None:
        c.ends_at = ends_at
    db.session.add(c)
    db.session.flush()  # get id
    if updated_at is not None:
        # override updated_at after flush so it stores correctly
        db.session.execute(
            db.text('UPDATE contests SET updated_at = :ua WHERE id = :id'),
            {'ua': updated_at, 'id': c.id}
        )
    db.session.commit()
    return c


def _add_spin(db, contest, user, tickets=3):
    from modules.contests.models import ContestSpin
    s = ContestSpin(contest_id=contest.id, user_id=user.id, tickets_won=tickets)
    db.session.add(s)
    db.session.commit()


def _add_winner(db, contest, user, place=1):
    from modules.contests.models import ContestWinner
    w = ContestWinner(
        contest_id=contest.id,
        user_id=user.id,
        place=place,
        tickets_at_draw=3,
    )
    db.session.add(w)
    db.session.commit()
    return w


# ---------------------------------------------------------------------------
# widget_context state tests
# ---------------------------------------------------------------------------

def test_widget_state_trwa_no_ends_at(db, make_user, make_product):
    """Active contest with no ends_at → state 'trwa'."""
    from modules.contests import utils as cu
    prod = make_product()
    user = make_user()
    contest = _make_contest(db, prod, status='aktywny', ends_at=None)

    ctx = cu.widget_context(contest, user)

    assert ctx is not None
    assert ctx['state'] == 'trwa'
    assert ctx['spins_open'] is True


def test_widget_state_trwa_ends_at_future(db, make_user, make_product):
    """Active contest with ends_at in the future → state 'trwa'."""
    from modules.contests import utils as cu
    from modules.orders.models import get_local_now
    prod = make_product()
    user = make_user()
    contest = _make_contest(db, prod, status='aktywny', ends_at=get_local_now() + timedelta(hours=2))

    ctx = cu.widget_context(contest, user)

    assert ctx['state'] == 'trwa'
    assert ctx['spins_open'] is True


def test_widget_state_zamkniete_ends_at_past(db, make_user, make_product):
    """Active contest with ends_at already past → state 'zamkniete'."""
    from modules.contests import utils as cu
    from modules.orders.models import get_local_now
    prod = make_product()
    user = make_user()
    contest = _make_contest(db, prod, status='aktywny', ends_at=get_local_now() - timedelta(hours=1))

    ctx = cu.widget_context(contest, user)

    assert ctx['state'] == 'zamkniete'
    assert ctx['spins_open'] is False
    assert ctx['can_spin'] is False
    # No winners keys for this state
    assert 'winners' not in ctx
    assert 'did_i_win' not in ctx


def test_widget_state_rozstrzygniete(db, make_user, make_product):
    """Contest with status 'rozlosowany' → state 'rozstrzygniete', winners list present."""
    from modules.contests import utils as cu
    prod = make_product()
    winner_user = make_user()
    other_user = make_user()
    contest = _make_contest(db, prod, status='rozlosowany')
    _add_spin(db, contest, winner_user, tickets=5)
    _add_winner(db, contest, winner_user, place=1)

    # The winner viewing the widget
    ctx_winner = cu.widget_context(contest, winner_user)
    assert ctx_winner['state'] == 'rozstrzygniete'
    assert ctx_winner['did_i_win'] is True
    assert len(ctx_winner['winners']) == 1
    assert ctx_winner['winners'][0].user_id == winner_user.id
    assert ctx_winner['winners'][0].place == 1

    # A non-winner viewing the widget
    ctx_other = cu.widget_context(contest, other_user)
    assert ctx_other['state'] == 'rozstrzygniete'
    assert ctx_other['did_i_win'] is False
    assert len(ctx_other['winners']) == 1


def test_widget_context_keeps_all_legacy_keys(db, make_user, make_product):
    """widget_context must always return the original keys so contest.html keeps working."""
    from modules.contests import utils as cu
    prod = make_product()
    user = make_user()
    contest = _make_contest(db, prod, status='aktywny')

    ctx = cu.widget_context(contest, user)

    required_keys = {'contest', 'my_tickets', 'participants', 'eligible',
                     'can_spin', 'next_spin_at', 'spins_open', 'state'}
    assert required_keys.issubset(ctx.keys())


# ---------------------------------------------------------------------------
# get_display_contest tests
# ---------------------------------------------------------------------------

def test_get_display_contest_returns_active_when_present(db, make_product):
    """When an active contest exists, return it."""
    from modules.contests import utils as cu
    prod = make_product()
    contest = _make_contest(db, prod, status='aktywny')

    result = cu.get_display_contest()

    assert result is not None
    assert result.id == contest.id
    assert result.status == 'aktywny'


def test_get_display_contest_returns_recent_rozlosowany_when_no_active(db, make_product):
    """When no active contest, return a 'rozlosowany' contest updated within 14 days."""
    from modules.contests import utils as cu
    from modules.orders.models import get_local_now
    prod = make_product()
    # updated 5 days ago — within the 14-day window
    recent_updated = get_local_now() - timedelta(days=5)
    contest = _make_contest(db, prod, status='rozlosowany', updated_at=recent_updated)

    result = cu.get_display_contest()

    assert result is not None
    assert result.id == contest.id
    assert result.status == 'rozlosowany'


def test_get_display_contest_returns_none_when_rozlosowany_too_old(db, make_product):
    """A 'rozlosowany' contest updated more than 14 days ago must NOT be shown."""
    from modules.contests import utils as cu
    from modules.orders.models import get_local_now
    prod = make_product()
    old_updated = get_local_now() - timedelta(days=20)
    _make_contest(db, prod, status='rozlosowany', updated_at=old_updated)

    result = cu.get_display_contest()

    assert result is None


def test_get_display_contest_active_beats_rozlosowany(db, make_product):
    """Active contest takes priority over any 'rozlosowany' contest."""
    from modules.contests import utils as cu
    from modules.orders.models import get_local_now
    prod = make_product()
    recent_updated = get_local_now() - timedelta(days=2)
    _make_contest(db, prod, status='rozlosowany', updated_at=recent_updated)
    active = _make_contest(db, prod, status='aktywny')

    result = cu.get_display_contest()

    assert result is not None
    assert result.id == active.id
    assert result.status == 'aktywny'


# ---------------------------------------------------------------------------
# Dashboard render sanity — zamkniete state
# ---------------------------------------------------------------------------

def test_dashboard_renders_zamkniete_state(client, db, make_user, make_product, login):
    """Dashboard with a closed (ends_at past) active contest renders without error."""
    from modules.contests.models import Contest
    from modules.orders.models import get_local_now
    prod = make_product()
    c = Contest(
        name='Zamknięty Konkurs',
        prize_product_id=prod.id,
        ticket_min=1,
        ticket_max=50,
        status='aktywny',
        ends_at=get_local_now() - timedelta(hours=3),
    )
    db.session.add(c)
    db.session.commit()

    login(make_user(profile_completed=True))
    resp = client.get('/client/dashboard')

    assert resp.status_code == 200
    assert b'contest-widget' in resp.data
    assert 'ZAKOŃCZONE' in resp.data.decode('utf-8') or 'zamkniete' in resp.data.decode('utf-8')


def test_dashboard_renders_rozstrzygniete_state(client, db, make_user, make_product, login):
    """Dashboard with a 'rozlosowany' contest (within 14 days) renders the winners block."""
    from modules.contests.models import Contest, ContestWinner
    from modules.orders.models import get_local_now
    prod = make_product()
    c = Contest(
        name='Rozstrzygnięty Konkurs',
        prize_product_id=prod.id,
        ticket_min=1,
        ticket_max=50,
        status='rozlosowany',
    )
    db.session.add(c)
    db.session.commit()

    user = make_user(profile_completed=True)
    winner = ContestWinner(
        contest_id=c.id,
        user_id=user.id,
        place=1,
        tickets_at_draw=5,
    )
    db.session.add(winner)
    db.session.commit()

    login(user)
    resp = client.get('/client/dashboard')

    assert resp.status_code == 200
    assert b'contest-widget' in resp.data
    decoded = resp.data.decode('utf-8')
    assert 'ROZSTRZYGNIĘTY' in decoded or 'Zwycięzcy' in decoded
