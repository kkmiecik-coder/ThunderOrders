from datetime import timedelta

import pytest

from utils.timeutil import utcnow


@pytest.fixture
def setup(db, make_user, make_product, make_order, strona_sprzedazy, login):
    """Akcja 'otwarta' z dwoma rodzajami kart i jednym uprawnionym klientem (zalogowanym)."""
    from modules.gift_cards.models import GiftCampaign, GiftCampaignPage, GiftCardType
    from modules.orders.models import OrderItem
    bonus = make_product(name='Gratis')
    c = GiftCampaign(name='Akcja', bonus_product_id=bonus.id, status='otwarta',
                     race_at=utcnow() - timedelta(minutes=1))
    db.session.add(c); db.session.commit()
    db.session.add(GiftCampaignPage(campaign_id=c.id, offer_page_id=strona_sprzedazy.id))
    t1 = GiftCardType(campaign_id=c.id, name='San', sort_order=0, quantity=1)
    t2 = GiftCardType(campaign_id=c.id, name='Yunho', sort_order=1, quantity=1)
    db.session.add_all([t1, t2]); db.session.commit()
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
        GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item.id, card_type_id=t1.id, round_no=1),
        GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item.id, card_type_id=t2.id, round_no=2),
    ])
    c.status = 'zatwierdzona'; db.session.commit()
    html = client.get(f'/gratisy/{c.id}').get_data(as_text=True)
    assert 'San' in html and 'Yunho' in html and 'Brakuje' not in html


def test_shortage_note_after_approve(client, setup, db):
    from modules.gift_cards.models import GiftAssignment
    c, t1, t2, user, item = setup
    db.session.add(GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item.id,
                                  card_type_id=t1.id, round_no=1))
    c.status = 'zatwierdzona'; db.session.commit()
    assert 'Brakuje 1 karta' in client.get(f'/gratisy/{c.id}').get_data(as_text=True)


def test_order_detail_links_to_open_campaign(client, setup, db):
    c, _, _, user, item = setup
    url = f'/client/orders/{item.order_id}'
    assert 'Wybierz swoje gratisowe karty' in client.get(url).get_data(as_text=True)
    c.status = 'zamknieta'; db.session.commit()
    assert 'Wybierz swoje gratisowe karty' not in client.get(url).get_data(as_text=True)
