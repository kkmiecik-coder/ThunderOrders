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
