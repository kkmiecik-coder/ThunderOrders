"""Przydział gratisowych kart widoczny w zamówieniach (klient, admin) i w WMS."""
from datetime import timedelta

import pytest

from tests.gift_helpers import add_pool, add_types

from utils.timeutil import utcnow


@pytest.fixture
def setup(db, make_user, make_product, make_order, strona_sprzedazy):
    """Akcja 'zatwierdzona' z przydziałem San + Yunho dla jednej pozycji-gratisu."""
    from modules.gift_cards.models import (GiftAssignment, GiftCampaign,
                                           GiftCampaignPage, GiftCardType)
    from modules.orders.models import OrderItem
    bonus = make_product(name='Gratis')
    c = GiftCampaign(name='Akcja', status='zatwierdzona',
                     race_at=utcnow() - timedelta(minutes=1))
    db.session.add(c); db.session.commit()
    db.session.add(GiftCampaignPage(campaign_id=c.id, offer_page_id=strona_sprzedazy.id))
    db.session.commit()
    pool = add_pool(db, c, bonus)
    t = add_types(db, c, {'San': 1, 'Yunho': 1})
    t1, t2 = t['San'], t['Yunho']
    user = make_user()
    order = make_order(user, offer_page_id=strona_sprzedazy.id)
    item = OrderItem(order_id=order.id, product_id=bonus.id, quantity=2, price=0,
                     total=0, is_bonus=True)
    db.session.add(item); db.session.commit()
    db.session.add_all([
        GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item.id,
                       pool_id=c.pools[0].id, card_type_id=t1.id, round_no=1),
        GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item.id,
                       pool_id=c.pools[0].id, card_type_id=t2.id, round_no=2),
    ])
    db.session.commit()
    return c, user, order, item


def test_client_order_detail_shows_assigned_cards(client, login, setup):
    c, user, order, item = setup
    login(user)
    html = client.get(f'/client/orders/{order.id}').get_data(as_text=True)
    assert 'Karty: San, Yunho' in html


def test_admin_order_detail_shows_pending_badge(client, login, make_user, db, setup):
    c, user, order, item = setup
    c.status = 'zamknieta'; db.session.commit()
    login(make_user(role='admin', email='admin-gratisy@example.com'))
    html = client.get(f'/admin/orders/{order.id}').get_data(as_text=True)
    assert 'przydział w toku' in html


def test_admin_order_detail_shows_assigned_cards(client, login, make_user, setup):
    c, user, order, item = setup
    login(make_user(role='admin', email='admin-gratisy@example.com'))
    html = client.get(f'/admin/orders/{order.id}').get_data(as_text=True)
    assert 'Karty: San, Yunho' in html


def test_admin_order_list_shows_assigned_cards(client, login, make_user, setup):
    login(make_user(role='admin', email='admin-gratisy@example.com'))
    html = client.get('/admin/orders').get_data(as_text=True)
    assert 'Karty: San, Yunho' in html


def test_wms_session_data_includes_gift_label(db, make_user, setup):
    from modules.orders.wms import _build_session_data
    from modules.orders.wms_models import WmsSession, WmsSessionOrder
    c, user, order, item = setup
    admin = make_user(role='admin', email='magazyn-gratisy@example.com')
    sesja = WmsSession(session_token='tok-gratisy-1', user_id=admin.id, status='active')
    db.session.add(sesja)
    db.session.flush()
    db.session.add(WmsSessionOrder(session_id=sesja.id, order_id=order.id))
    db.session.commit()

    data = _build_session_data(sesja)

    assert data['orders'][0]['items'][0]['gift_cards_label'] == 'San, Yunho'
