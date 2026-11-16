import pytest

BASE = '/admin/rozdzial-gratisow'


@pytest.fixture
def admin(login, make_user):
    u = make_user(role='admin')
    login(u)
    return u


@pytest.fixture
def setup(db, make_user, make_product, strona_sprzedazy):
    """Produkt-gratis ustawiony jako bonus na stronie oferty."""
    from modules.offers.models import OfferSection, OfferSetBonus
    bonus = make_product(name='Gratis')
    section = OfferSection(offer_page_id=strona_sprzedazy.id, section_type='set')
    db.session.add(section)
    db.session.commit()
    db.session.add(OfferSetBonus(section_id=section.id, trigger_type='quantity_threshold',
                                 threshold_value=1, bonus_product_id=bonus.id))
    db.session.commit()
    return bonus, strona_sprzedazy


def _campaign(db, bonus, page, status='szkic', types=('Typ A', 'Typ B'), quantities=None):
    from modules.gift_cards.models import GiftCampaign, GiftCampaignPage, GiftCardType
    c = GiftCampaign(name='Akcja', bonus_product_id=bonus.id, status=status)
    db.session.add(c)
    db.session.commit()
    db.session.add(GiftCampaignPage(campaign_id=c.id, offer_page_id=page.id))
    for i, name in enumerate(types):
        db.session.add(GiftCardType(campaign_id=c.id, name=name, sort_order=i,
                                    quantity=quantities[i] if quantities else None))
    db.session.commit()
    return c


def _entitled(db, make_user, make_order, bonus, page, qty=1):
    from modules.orders.models import OrderItem
    u = make_user()
    o = make_order(u, offer_page_id=page.id)
    item = OrderItem(order_id=o.id, product_id=bonus.id, quantity=qty, price=0, total=0, is_bonus=True)
    db.session.add(item)
    db.session.commit()
    return u, item


def test_list_requires_admin(client, login, make_user):
    login(make_user(role='client'))
    assert client.get(BASE).status_code in (302, 403)


def test_list_and_form_render(client, admin, db, setup):
    bonus, page = setup
    _campaign(db, bonus, page)
    assert 'Akcja' in client.get(BASE).get_data(as_text=True)
    html = client.get(BASE + '/nowa').get_data(as_text=True)
    assert 'Gratis' in html and 'Rodzaje kart' in html


def test_create_campaign_with_card_types(client, admin, db, setup):
    from modules.gift_cards.models import GiftCampaign
    from utils.timeutil import to_pl
    bonus, page = setup
    resp = client.post(BASE + '/nowa', data={
        'name': 'ATEEZ unit', 'offer_page_ids': [page.id], 'bonus_product_id': bonus.id,
        'race_at': '2026-11-20T20:00', 'type_name': ['Hongjoong + Seonghwa', 'Yunho + Yeosang'],
        'type_existing_image': ['', '']})
    assert resp.status_code == 302
    c = GiftCampaign.query.one()
    assert [t.name for t in c.card_types] == ['Hongjoong + Seonghwa', 'Yunho + Yeosang']
    assert to_pl(c.race_at).hour == 20
    assert c.offer_page_ids == [page.id] and c.bonus_product_id == bonus.id
    assert c.status == 'szkic'
    assert client.get(f'{BASE}/{c.id}/edytuj').status_code == 200


def test_create_without_types_shows_error(client, admin, db, setup):
    from modules.gift_cards.models import GiftCampaign
    bonus, page = setup
    resp = client.post(BASE + '/nowa', data={'name': 'X', 'offer_page_ids': [page.id],
                                             'bonus_product_id': bonus.id})
    assert resp.status_code == 200
    assert GiftCampaign.query.count() == 0


def test_edit_non_draft_keeps_types(client, admin, db, setup):
    bonus, page = setup
    c = _campaign(db, bonus, page, status='otwarta')
    ids = [t.id for t in c.card_types]
    resp = client.post(f'{BASE}/{c.id}/edytuj', data={'name': 'Nowa nazwa', 'race_at': '2026-12-01T10:30'})
    assert resp.status_code == 302
    db.session.refresh(c)
    assert c.name == 'Nowa nazwa' and [t.id for t in c.card_types] == ids


def test_publish_sends_invites_and_opens(client, admin, db, setup, make_user, make_order, maile_synchronicznie, app):
    from extensions import mail
    from modules.gift_cards.models import GiftCampaign
    bonus, page = setup
    c = _campaign(db, bonus, page)
    _entitled(db, make_user, make_order, bonus, page)
    with mail.record_messages() as outbox:
        resp = client.post(f'{BASE}/{c.id}/publikuj', follow_redirects=True)
    assert r'Wys\u0142ano 1 zaprosze' in resp.get_data(as_text=True)
    assert db.session.get(GiftCampaign, c.id).status == 'otwarta'
    assert len(outbox) == 1


def test_close(client, admin, db, setup):
    bonus, page = setup
    c = _campaign(db, bonus, page, status='otwarta')
    client.post(f'{BASE}/{c.id}/zamknij')
    db.session.refresh(c)
    assert c.status == 'zamknieta'


def test_distribute_without_quantities_shows_error(client, admin, db, setup):
    bonus, page = setup
    c = _campaign(db, bonus, page, status='zamknieta')
    resp = client.post(f'{BASE}/{c.id}/rozdziel')
    assert resp.status_code == 302
    db.session.refresh(c)
    assert c.status == 'zamknieta'
    with client.session_transaction() as sess:
        assert any('ilości' in m for _, m in sess['_flashes'])


def test_quantities_reject_invalid(client, admin, db, setup):
    bonus, page = setup
    c = _campaign(db, bonus, page, status='zamknieta')
    t1, t2 = c.card_types
    client.post(f'{BASE}/{c.id}/ilosci', data={f'quantity_{t1.id}': '3', f'quantity_{t2.id}': '-1'})
    db.session.refresh(t1)
    assert t1.quantity is None


def test_full_flow_close_quantities_distribute_approve(client, admin, db, setup, make_user, make_order,
                                                        maile_synchronicznie):
    from modules.gift_cards.models import GiftCampaign
    from modules.gift_cards.service import item_gift_label
    bonus, page = setup
    c = _campaign(db, bonus, page, status='otwarta')
    u, item = _entitled(db, make_user, make_order, bonus, page, qty=2)
    client.post(f'{BASE}/{c.id}/zamknij')
    t1, t2 = c.card_types
    client.post(f'{BASE}/{c.id}/ilosci', data={f'quantity_{t1.id}': '1', f'quantity_{t2.id}': '1'})
    client.post(f'{BASE}/{c.id}/rozdziel')
    assert db.session.get(GiftCampaign, c.id).status == 'rozdzielona'
    html = client.get(f'{BASE}/{c.id}').get_data(as_text=True)
    assert 'Zatwierdź i wyślij wyniki' in html and 'data-assignment-id' in html
    client.post(f'{BASE}/{c.id}/zatwierdz')
    assert db.session.get(GiftCampaign, c.id).status == 'zatwierdzona'
    db.session.refresh(item)
    assert item_gift_label(item) == 'Typ A, Typ B'
    assert 'Cofnij zatwierdzenie' in client.get(f'{BASE}/{c.id}').get_data(as_text=True)
    client.post(f'{BASE}/{c.id}/cofnij')
    assert db.session.get(GiftCampaign, c.id).status == 'rozdzielona'


def test_swap_endpoint_returns_error_json_over_stock(client, admin, db, setup, make_user, make_order):
    from modules.gift_cards.models import GiftAssignment
    bonus, page = setup
    c = _campaign(db, bonus, page, status='zamknieta', quantities=[1, 1])
    _entitled(db, make_user, make_order, bonus, page)
    _entitled(db, make_user, make_order, bonus, page)
    client.post(f'{BASE}/{c.id}/rozdziel')
    a, b = GiftAssignment.query.order_by(GiftAssignment.id).all()
    resp = client.post(f'{BASE}/{c.id}/zamien', json={'assignment_id': a.id, 'type_id': b.card_type_id})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body['success'] is False and 'Brak wolnych sztuk' in body['error']


def test_swap_endpoint_success(client, admin, db, setup, make_user, make_order):
    from modules.gift_cards.models import GiftAssignment
    bonus, page = setup
    c = _campaign(db, bonus, page, status='zamknieta', quantities=[1, 1])
    _entitled(db, make_user, make_order, bonus, page)
    client.post(f'{BASE}/{c.id}/rozdziel')
    a = GiftAssignment.query.one()
    other = next(t.id for t in c.card_types if t.id != a.card_type_id)
    resp = client.post(f'{BASE}/{c.id}/zamien', json={'assignment_id': a.id, 'type_id': other})
    assert resp.get_json() == {'success': True}
    db.session.refresh(a)
    assert a.card_type_id == other
