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
