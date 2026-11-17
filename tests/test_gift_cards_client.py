from datetime import timedelta

import pytest

from tests.gift_helpers import add_pool, add_types

from utils.timeutil import utcnow


@pytest.fixture
def setup(db, make_user, make_product, make_order, strona_sprzedazy, login):
    """Akcja 'otwarta' z dwoma rodzajami kart i jednym uprawnionym klientem (zalogowanym)."""
    from modules.gift_cards.models import GiftCampaign, GiftCampaignPage, GiftCardType
    from modules.orders.models import OrderItem
    bonus = make_product(name='Gratis')
    c = GiftCampaign(name='Akcja', status='otwarta',
                     race_at=utcnow() - timedelta(minutes=1))
    db.session.add(c); db.session.commit()
    db.session.add(GiftCampaignPage(campaign_id=c.id, offer_page_id=strona_sprzedazy.id))
    db.session.commit()
    pool = add_pool(db, c, bonus)
    t = add_types(db, c, {'San': 1, 'Yunho': 1})
    t1, t2 = t['San'], t['Yunho']
    user = make_user()
    order = make_order(user, offer_page_id=strona_sprzedazy.id)
    item = OrderItem(order_id=order.id, product_id=bonus.id, quantity=2, price=0, total=0, is_bonus=True)
    db.session.add(item); db.session.commit()
    login(user)
    return c, t1, t2, user, item


def test_entitled_sees_page(client, setup):
    c, t1, t2, *_ = setup
    html = client.get(f'/gratisy/{c.id}').get_data(as_text=True)
    assert 'Przysługują Ci' in html and '2 karty' in html
    assert f'name="rank_{t1.id}"' in html and 'Zgłaszam się' in html


def test_non_entitled_sees_not_for_you(client, setup, make_user, login):
    c = setup[0]
    login(make_user())
    resp = client.get(f'/gratisy/{c.id}')
    assert resp.status_code == 200
    assert 'Ta akcja Cię nie dotyczy' in resp.get_data(as_text=True)


def test_draft_looks_like_not_for_you(client, setup, db):
    c = setup[0]
    c.status = 'szkic'; db.session.commit()
    assert 'Ta akcja Cię nie dotyczy' in client.get(f'/gratisy/{c.id}').get_data(as_text=True)


def test_non_entitled_race_forbidden(client, setup, make_user, login):
    c = setup[0]
    login(make_user())
    assert client.post(f'/gratisy/{c.id}/zglaszam-sie').status_code == 403


def test_race_before_time_rejected(client, setup, db):
    from modules.gift_cards.models import GiftRaceEntry
    c = setup[0]
    c.race_at = utcnow() + timedelta(hours=1); db.session.commit()
    resp = client.post(f'/gratisy/{c.id}/zglaszam-sie')
    assert resp.status_code == 400 and resp.get_json()['success'] is False
    assert GiftRaceEntry.query.count() == 0


def test_race_rejected_when_not_open(client, setup, db):
    c = setup[0]
    c.status = 'zamknieta'; db.session.commit()
    assert client.post(f'/gratisy/{c.id}/zglaszam-sie').status_code == 400


def test_double_race_click_single_entry(client, setup):
    from modules.gift_cards.models import GiftRaceEntry
    c = setup[0]
    r1 = client.post(f'/gratisy/{c.id}/zglaszam-sie').get_json()
    r2 = client.post(f'/gratisy/{c.id}/zglaszam-sie').get_json()
    assert r1['position'] == r2['position'] == 1
    assert GiftRaceEntry.query.count() == 1
    assert 'Jesteś nr' in client.get(f'/gratisy/{c.id}').get_data(as_text=True)


def test_race_insert_conflict_returns_existing_position(client, setup, monkeypatch):
    """Wyścig dwóch żądań: commit rzuca IntegrityError -> odpowiedź z istniejącym wpisem."""
    from sqlalchemy.exc import IntegrityError
    from extensions import db as _db
    from modules.gift_cards.models import GiftRaceEntry
    c, _, _, user, _ = setup
    real_commit = _db.session.commit

    def commit_with_conflict():
        _db.session.rollback()
        _db.session.add(GiftRaceEntry(campaign_id=c.id, user_id=user.id))
        real_commit()
        monkeypatch.undo()
        raise IntegrityError('x', {}, Exception('dup'))

    monkeypatch.setattr(_db.session, 'commit', commit_with_conflict)
    resp = client.post(f'/gratisy/{c.id}/zglaszam-sie')
    assert resp.get_json() == {'success': True, 'position': 1}


def test_ranking_saved_as_type_ids_in_order(client, setup):
    from modules.gift_cards.models import GiftParticipant
    c, t1, t2, *_ = setup
    resp = client.post(f'/gratisy/{c.id}/ranking', data={f'rank_{t1.id}': 2, f'rank_{t2.id}': 1})
    assert resp.status_code == 302
    assert GiftParticipant.query.one().ranking == [t2.id, t1.id]
    resp = client.post(f'/gratisy/{c.id}/ranking', data={f'rank_{t1.id}': 1, f'rank_{t2.id}': 2})
    assert GiftParticipant.query.one().ranking == [t1.id, t2.id]


def test_ranking_first_save_conflict_updates_existing(client, setup, monkeypatch):
    """Podwójne wysłanie pierwszego rankingu: insert trafia w unikalny klucz -> aktualizacja, nie 500."""
    import json
    from sqlalchemy.exc import IntegrityError
    from extensions import db as _db
    from modules.gift_cards.models import GiftParticipant
    c, t1, t2, user, _ = setup
    real_commit = _db.session.commit

    def commit_with_conflict():
        _db.session.rollback()
        _db.session.add(GiftParticipant(campaign_id=c.id, user_id=user.id,
                                        ranking_json=json.dumps([t1.id, t2.id])))
        real_commit()
        monkeypatch.undo()
        raise IntegrityError('x', {}, Exception('dup'))

    monkeypatch.setattr(_db.session, 'commit', commit_with_conflict)
    resp = client.post(f'/gratisy/{c.id}/ranking', data={f'rank_{t1.id}': 2, f'rank_{t2.id}': 1})
    assert resp.status_code == 302
    assert GiftParticipant.query.one().ranking == [t2.id, t1.id]


def test_race_box_carries_server_time(client, setup):
    """Odliczanie liczy się względem czasu serwera, nie zegara urządzenia."""
    import re
    c = setup[0]
    html = client.get(f'/gratisy/{c.id}').get_data(as_text=True)
    assert re.search(r'data-server-now="\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', html)


@pytest.mark.parametrize('dane', ['duplikat_miejsca', 'obcy_rodzaj', 'brak_rodzaju', 'zle_miejsce', 'tekst'])
def test_ranking_tampering_rejected(dane, client, setup):
    from modules.gift_cards.models import GiftParticipant
    c, t1, t2, *_ = setup
    data = {
        'duplikat_miejsca': {f'rank_{t1.id}': 1, f'rank_{t2.id}': 1},
        'obcy_rodzaj': {f'rank_{t1.id}': 1, 'rank_99999': 2},
        'brak_rodzaju': {f'rank_{t1.id}': 1},
        'zle_miejsce': {f'rank_{t1.id}': 1, f'rank_{t2.id}': 3},
        'tekst': {f'rank_{t1.id}': 'a', f'rank_{t2.id}': 'b'},
    }[dane]
    assert client.post(f'/gratisy/{c.id}/ranking', data=data).status_code == 400
    assert GiftParticipant.query.count() == 0


def test_ranking_locked_after_close(client, setup, db):
    from modules.gift_cards.models import GiftParticipant
    c, t1, t2, *_ = setup
    c.status = 'zamknieta'; db.session.commit()
    resp = client.post(f'/gratisy/{c.id}/ranking', data={f'rank_{t1.id}': 1, f'rank_{t2.id}': 2})
    assert resp.status_code == 400 and GiftParticipant.query.count() == 0


def test_ranking_not_entitled_forbidden(client, setup, make_user, login):
    c, t1, t2, *_ = setup
    login(make_user())
    assert client.post(f'/gratisy/{c.id}/ranking',
                       data={f'rank_{t1.id}': 1, f'rank_{t2.id}': 2}).status_code == 403


def test_shows_assigned_cards_after_approve(client, setup, db):
    from modules.gift_cards.models import GiftAssignment
    c, t1, t2, user, item = setup
    db.session.add_all([
        GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item.id, pool_id=c.pools[0].id, card_type_id=t1.id, round_no=1),
        GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item.id, pool_id=c.pools[0].id, card_type_id=t2.id, round_no=2),
    ])
    c.status = 'zatwierdzona'; db.session.commit()
    html = client.get(f'/gratisy/{c.id}').get_data(as_text=True)
    assert 'San' in html and 'Yunho' in html and 'Brakuje' not in html


def test_shortage_note_after_approve(client, setup, db):
    from modules.gift_cards.models import GiftAssignment
    c, t1, t2, user, item = setup
    db.session.add(GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item.id,
                                  pool_id=c.pools[0].id, card_type_id=t1.id, round_no=1))
    c.status = 'zatwierdzona'; db.session.commit()
    assert 'Brakuje 1 karta' in client.get(f'/gratisy/{c.id}').get_data(as_text=True)


def test_order_detail_links_to_open_campaign(client, setup, db):
    c, _, _, user, item = setup
    url = f'/client/orders/{item.order_id}'
    assert 'Wybierz swoje gratisowe karty' in client.get(url).get_data(as_text=True)
    c.status = 'zamknieta'; db.session.commit()
    assert 'Wybierz swoje gratisowe karty' not in client.get(url).get_data(as_text=True)


# --- Kafelek akcji na stronie głównej klientki -------------------------------------------

DASH = '/client/dashboard'


@pytest.fixture
def dash(setup, db):
    """Uprawniona klientka z uzupełnionym profilem (inaczej panel przekierowuje do profilu)."""
    setup[3].profile_completed = True
    db.session.commit()
    return setup


def test_dashboard_tile_for_entitled_client_after_start(client, dash):
    setup = dash
    html = client.get(DASH).get_data(as_text=True)
    assert 'gc-dash' in html and 'Akcja' in html
    assert 'Przysługują Ci 2 karty' in html
    assert 'Zgłoszenia trwają' in html
    assert f'/gratisy/{setup[0].id}' in html


def test_dashboard_tile_before_start_asks_for_ranking(client, dash, db):
    c = dash[0]
    c.race_at = utcnow() + timedelta(hours=2); db.session.commit()
    html = client.get(DASH).get_data(as_text=True)
    assert 'Zgłoszenia ruszają' in html and 'Ułóż ranking' in html


def test_dashboard_tile_shows_queue_position(client, dash):
    c = dash[0]
    assert client.post(f'/gratisy/{c.id}/zglaszam-sie').status_code == 200
    html = client.get(DASH).get_data(as_text=True)
    assert 'Jesteś nr' in html and 'w kolejce' in html


def test_dashboard_tile_closed_campaign_waits_for_result(client, dash, db):
    c = dash[0]
    c.status = 'zamknieta'; db.session.commit()
    html = client.get(DASH).get_data(as_text=True)
    assert 'gc-dash' in html and 'przydzielamy karty' in html


@pytest.mark.parametrize('status', ['szkic', 'zatwierdzona'])
def test_dashboard_tile_hidden_for_draft_and_approved(client, dash, db, status):
    c = dash[0]
    c.status = status; db.session.commit()
    assert 'gc-dash' not in client.get(DASH).get_data(as_text=True)


def test_dashboard_tile_hidden_for_non_entitled(client, dash, make_user, login):
    login(make_user(profile_completed=True))
    assert 'gc-dash' not in client.get(DASH).get_data(as_text=True)


# ---- Pule i uwagi ----

@pytest.fixture
def dwie_pule(db, make_product, setup):
    """Do akcji z `setup` dochodzi druga pula (Benefit 100k) z 1 kartą dla klientki."""
    from modules.orders.models import OrderItem
    from tests.gift_helpers import set_stock
    c, t1, t2, user, item = setup
    c.pools[0].bonus_product.name = 'Benefit 50k'
    b100 = make_product(name='Benefit 100k')
    p100 = add_pool(db, c, b100)
    set_stock(db, p100, {t1: 1, t2: 1})
    item100 = OrderItem(order_id=item.order_id, product_id=b100.id, quantity=1, price=0, total=0, is_bonus=True)
    db.session.add(item100); db.session.commit()
    return c, t1, t2, user, item, p100, item100


def test_page_shows_breakdown_per_pool(client, dwie_pule):
    c = dwie_pule[0]
    html = client.get(f'/gratisy/{c.id}').get_data(as_text=True)
    assert '3 karty' in html
    assert '2 karty</strong> — Benefit 50k' in html and '1 karta</strong> — Benefit 100k' in html
    assert 'Ten sam ranking liczy się dla wszystkich' in html


def test_result_grouped_per_pool(client, db, dwie_pule):
    from modules.gift_cards.models import GiftAssignment
    c, t1, t2, user, item, p100, item100 = dwie_pule
    db.session.add_all([
        GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item.id, pool_id=c.pools[0].id,
                       card_type_id=t1.id, round_no=1),
        GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item100.id, pool_id=p100.id,
                       card_type_id=t1.id, round_no=1),
    ])
    c.status = 'zatwierdzona'; db.session.commit()
    html = client.get(f'/gratisy/{c.id}').get_data(as_text=True)
    assert html.index('Benefit 50k</h3>') < html.index('Benefit 100k</h3>')
    assert 'Brakuje 1 karta' in html


def test_invite_mail_has_breakdown(app, db, dwie_pule, maile_synchronicznie):
    from extensions import mail
    from modules.gift_cards.emails import send_invites
    c = dwie_pule[0]
    with app.test_request_context(), mail.record_messages() as out:
        assert send_invites(c) == 1
    assert 'przysługują Ci 3 karty (2 karty — Benefit 50k, 1 karta — Benefit 100k)' in out[0].body


def test_result_mail_lists_cards_per_pool(app, db, dwie_pule, maile_synchronicznie):
    from extensions import mail
    from modules.gift_cards.emails import send_results
    from modules.gift_cards.models import GiftAssignment
    c, t1, t2, user, item, p100, item100 = dwie_pule
    db.session.add_all([
        GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item.id, pool_id=c.pools[0].id,
                       card_type_id=t1.id, round_no=1),
        GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item.id, pool_id=c.pools[0].id,
                       card_type_id=t2.id, round_no=2),
        GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item100.id, pool_id=p100.id,
                       card_type_id=t1.id, round_no=1),
    ])
    db.session.commit()
    with app.test_request_context(), mail.record_messages() as out:
        send_results(c)
    assert 'Benefit 50k: San, Yunho; Benefit 100k: San' in out[0].body


def test_save_notes_when_open(client, db, setup):
    from modules.gift_cards.models import GiftParticipant
    c, *_ , user, _item = setup
    resp = client.post(f'/gratisy/{c.id}/uwagi', data={'notes': '  Proszę bez Yunho  '})
    assert resp.status_code == 302
    p = GiftParticipant.query.filter_by(campaign_id=c.id, user_id=user.id).one()
    assert p.notes == 'Proszę bez Yunho' and p.ranking == []
    html = client.get(f'/gratisy/{c.id}').get_data(as_text=True)
    assert 'Proszę bez Yunho</textarea>' in html


def test_notes_do_not_touch_saved_ranking(client, db, setup):
    from modules.gift_cards.models import GiftParticipant
    c, t1, t2, user, _ = setup
    client.post(f'/gratisy/{c.id}/ranking', data={f'rank_{t1.id}': 2, f'rank_{t2.id}': 1})
    client.post(f'/gratisy/{c.id}/uwagi', data={'notes': 'Hej'})
    p = GiftParticipant.query.filter_by(campaign_id=c.id, user_id=user.id).one()
    assert p.ranking == [t2.id, t1.id] and p.notes == 'Hej'


def test_notes_rejected_when_closed_or_too_long(client, db, setup):
    from modules.gift_cards.models import GiftParticipant
    c = setup[0]
    assert client.post(f'/gratisy/{c.id}/uwagi', data={'notes': 'x' * 1001}).status_code == 400
    c.status = 'zamknieta'; db.session.commit()
    assert client.post(f'/gratisy/{c.id}/uwagi', data={'notes': 'późno'}).status_code == 400
    assert GiftParticipant.query.filter(GiftParticipant.notes.isnot(None)).count() == 0


def test_notes_forbidden_for_non_entitled(client, setup, make_user, login):
    c = setup[0]
    login(make_user())
    assert client.post(f'/gratisy/{c.id}/uwagi', data={'notes': 'x'}).status_code == 403
