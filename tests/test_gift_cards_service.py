import pytest


def test_race_entry_unique_per_user(db, make_user, make_product):
    from sqlalchemy.exc import IntegrityError
    from modules.gift_cards.models import GiftCampaign, GiftRaceEntry
    c = GiftCampaign(name='ATEEZ', bonus_product_id=make_product().id)
    db.session.add(c); db.session.commit()
    u = make_user()
    db.session.add(GiftRaceEntry(campaign_id=c.id, user_id=u.id)); db.session.commit()
    db.session.add(GiftRaceEntry(campaign_id=c.id, user_id=u.id))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_participant_ranking_property(db, make_user, make_product):
    from modules.gift_cards.models import GiftCampaign, GiftParticipant
    c = GiftCampaign(name='X', bonus_product_id=make_product().id); db.session.add(c); db.session.commit()
    p = GiftParticipant(campaign_id=c.id, user_id=make_user().id)
    assert p.ranking == []
    p.ranking_json = '[3, 1, 2]'
    assert p.ranking == [3, 1, 2]
    assert c.status == 'szkic'


# ---- Task 2: uprawnienia i kolejka ----

@pytest.fixture
def akcja(db, make_user, make_product, strona_sprzedazy):
    from modules.gift_cards.models import GiftCampaign, GiftCampaignPage
    bonus = make_product(name='Gratis')
    c = GiftCampaign(name='Akcja', bonus_product_id=bonus.id)
    db.session.add(c); db.session.commit()
    db.session.add(GiftCampaignPage(campaign_id=c.id, offer_page_id=strona_sprzedazy.id))
    db.session.commit()
    return c, bonus, strona_sprzedazy


def _bonus(db, order, product, qty, is_bonus=True):
    from modules.orders.models import OrderItem
    it = OrderItem(order_id=order.id, product_id=product.id, quantity=qty, price=0, total=0, is_bonus=is_bonus)
    db.session.add(it); db.session.commit()
    return it


def test_entitlements_sum_bonus_items_across_orders(db, make_user, make_product, make_order, akcja):
    from datetime import datetime, timezone
    from modules.offers.models import OfferPage
    from modules.gift_cards.service import compute_entitlements
    c, bonus, page = akcja
    inna = OfferPage(name='Inna', token=OfferPage.generate_token(), status='active', created_by=make_user(role='admin').id)
    db.session.add(inna); db.session.commit()
    a, b, cc = make_user(), make_user(), make_user()
    o1 = make_order(a, offer_page_id=page.id, created_at=datetime(2026, 11, 1, tzinfo=timezone.utc))
    o2 = make_order(a, offer_page_id=page.id, created_at=datetime(2026, 11, 2, tzinfo=timezone.utc))
    _bonus(db, o1, bonus, 1); _bonus(db, o2, bonus, 2)
    _bonus(db, o2, make_product(), 5)                      # inny produkt, bonus
    _bonus(db, o2, bonus, 4, is_bonus=False)               # nie-bonus
    ob = make_order(b, status='anulowane', offer_page_id=page.id)
    _bonus(db, ob, bonus, 1)
    oc = make_order(cc, offer_page_id=inna.id)
    _bonus(db, oc, bonus, 1)
    ents = compute_entitlements(c)
    assert set(ents) == {a.id}
    assert ents[a.id].total == 3
    assert [q for _, q in ents[a.id].items] == [1, 2]


def test_entitlements_empty_without_bonus_product(db, akcja):
    from modules.gift_cards.service import compute_entitlements
    c, _, _ = akcja
    c.bonus_product_id = None
    assert compute_entitlements(c) == {}


def _kolejka_setup(db, make_user, make_order, akcja):
    from datetime import datetime, timezone
    c, bonus, page = akcja
    a, b, cc = make_user(), make_user(), make_user()
    for u, d in ((a, 1), (b, 2), (cc, 3)):
        _bonus(db, make_order(u, offer_page_id=page.id, created_at=datetime(2026, 11, d, tzinfo=timezone.utc)), bonus, 1)
    return c, a, b, cc


def test_queue_racers_first_then_by_first_order(db, make_user, make_order, akcja):
    from modules.gift_cards.models import GiftRaceEntry
    from modules.gift_cards.service import compute_entitlements, queue_order, queue_position
    c, a, b, cc = _kolejka_setup(db, make_user, make_order, akcja)
    db.session.add(GiftRaceEntry(campaign_id=c.id, user_id=cc.id)); db.session.commit()
    db.session.add(GiftRaceEntry(campaign_id=c.id, user_id=a.id)); db.session.commit()
    ents = compute_entitlements(c)
    assert queue_order(c, ents) == [cc.id, a.id, b.id]
    assert queue_position(c, cc.id) == 1
    assert queue_position(c, a.id) == 2
    assert queue_position(c, b.id) is None


def test_queue_ignores_race_entry_of_non_entitled_user(db, make_user, make_order, akcja):
    from modules.gift_cards.models import GiftRaceEntry
    from modules.gift_cards.service import compute_entitlements, queue_order
    c, a, b, cc = _kolejka_setup(db, make_user, make_order, akcja)
    d = make_user()
    db.session.add(GiftRaceEntry(campaign_id=c.id, user_id=d.id)); db.session.commit()
    assert queue_order(c, compute_entitlements(c)) == [a.id, b.id, cc.id]


# ---- Task 4: rozdział, zamiany, zatwierdzanie ----

def _typy(db, c, **ilosci):
    from modules.gift_cards.models import GiftCardType
    out = {}
    for i, (nazwa, q) in enumerate(ilosci.items()):
        t = GiftCardType(campaign_id=c.id, name=nazwa, quantity=q, sort_order=i)
        db.session.add(t); out[nazwa] = t
    db.session.commit()
    return out


def _ranking(db, c, user, typy):
    import json
    from modules.gift_cards.models import GiftParticipant
    db.session.add(GiftParticipant(campaign_id=c.id, user_id=user.id, ranking_json=json.dumps([t.id for t in typy])))
    db.session.commit()


def test_run_distribution_saves_assignments_on_order_items(db, make_user, make_order, akcja):
    from modules.gift_cards.models import GiftAssignment
    from modules.gift_cards.service import run_distribution
    c, bonus, page = akcja
    a = make_user()
    o1, o2 = make_order(a, offer_page_id=page.id), make_order(a, offer_page_id=page.id)
    item1, item2 = _bonus(db, o1, bonus, 1), _bonus(db, o2, bonus, 1)
    t = _typy(db, c, San=1, Yunho=1)
    _ranking(db, c, a, [t['San'], t['Yunho']])
    c.status = 'zamknieta'; db.session.commit()
    run_distribution(c)
    rows = GiftAssignment.query.filter_by(user_id=a.id).order_by(GiftAssignment.round_no).all()
    assert [r.order_item_id for r in rows] == [item1.id, item2.id]
    assert [r.card_type_id for r in rows] == [t['San'].id, t['Yunho'].id]
    assert c.status == 'rozdzielona'


def test_run_distribution_requires_quantities(db, make_user, make_order, akcja):
    from modules.gift_cards.service import GiftCardsError, run_distribution
    c, bonus, page = akcja
    t = _typy(db, c, San=None)
    c.status = 'zamknieta'; db.session.commit()
    with pytest.raises(GiftCardsError, match='ilości'):
        run_distribution(c)


def test_run_distribution_no_entitled_users(db, akcja):
    from modules.gift_cards.service import run_distribution
    c, _, _ = akcja
    _typy(db, c, San=2)
    c.status = 'zamknieta'; db.session.commit()
    result = run_distribution(c)
    assert result.picks == {} and c.status == 'rozdzielona'


def _dwoje_z_kartami(db, make_user, make_order, akcja, san=1, yunho=1):
    from modules.gift_cards.service import run_distribution
    c, bonus, page = akcja
    a, b = make_user(), make_user()
    ia = _bonus(db, make_order(a, offer_page_id=page.id), bonus, 1)
    ib = _bonus(db, make_order(b, offer_page_id=page.id), bonus, 1)
    t = _typy(db, c, San=san, Yunho=yunho)
    _ranking(db, c, a, [t['San'], t['Yunho']])
    _ranking(db, c, b, [t['San'], t['Yunho']])
    c.status = 'zamknieta'; db.session.commit()
    run_distribution(c)
    return c, a, b, ia, ib, t


def test_swap_over_stock_rejected(db, make_user, make_order, akcja):
    from modules.gift_cards.models import GiftAssignment
    from modules.gift_cards.service import GiftCardsError, swap_assignment
    c, a, b, ia, ib, t = _dwoje_z_kartami(db, make_user, make_order, akcja)
    b_row = GiftAssignment.query.filter_by(user_id=b.id).one()
    assert b_row.card_type_id == t['Yunho'].id  # San poszedł do A
    with pytest.raises(GiftCardsError, match='Brak wolnych sztuk'):
        swap_assignment(b_row.id, t['San'].id)


def test_swap_recomputes_duplicate_flag(db, make_user, make_order, akcja):
    from modules.gift_cards.models import GiftAssignment
    from modules.gift_cards.service import run_distribution, swap_assignment
    c, bonus, page = akcja
    a = make_user()
    o = make_order(a, offer_page_id=page.id)
    _bonus(db, o, bonus, 2)
    t = _typy(db, c, San=2, Yunho=2)
    _ranking(db, c, a, [t['San'], t['Yunho']])
    c.status = 'zamknieta'; db.session.commit()
    run_distribution(c)
    rows = GiftAssignment.query.filter_by(user_id=a.id).order_by(GiftAssignment.round_no).all()
    assert [r.is_duplicate for r in rows] == [False, False]
    swap_assignment(rows[1].id, rows[0].card_type_id)
    rows = GiftAssignment.query.filter_by(user_id=a.id).order_by(GiftAssignment.round_no).all()
    assert [r.is_duplicate for r in rows] == [False, True]
    assert [r.rank_position for r in rows] == [1, 1]


def test_label_pending_then_names_after_approve(db, make_user, make_order, akcja):
    from modules.gift_cards.service import approve
    c, a, b, ia, ib, t = _dwoje_z_kartami(db, make_user, make_order, akcja)
    assert ia.gift_cards_label == 'przydział w toku'
    approve(c)
    assert ia.gift_cards_label == 'San'
    assert ib.gift_cards_label == 'Yunho'


def test_label_none_for_non_bonus_item(db, make_user, make_order, make_product, akcja):
    c, bonus, page = akcja
    it = _bonus(db, make_order(make_user(), offer_page_id=page.id), bonus, 1, is_bonus=False)
    assert it.gift_cards_label is None


def test_revert_blocked_when_order_packed(db, make_user, make_order, akcja):
    from modules.gift_cards.service import GiftCardsError, approve, can_revert, revert_approval
    c, a, b, ia, ib, t = _dwoje_z_kartami(db, make_user, make_order, akcja)
    approve(c)
    assert can_revert(c) is True
    ia.order.status = 'spakowane'; db.session.commit()
    assert can_revert(c) is False
    with pytest.raises(GiftCardsError):
        revert_approval(c)
    ia.order.status = 'nowe'; db.session.commit()
    revert_approval(c)
    assert c.status == 'rozdzielona'
