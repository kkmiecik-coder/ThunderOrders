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


def _campaign(db, bonus, page, status='szkic', types=('Typ A', 'Typ B'), quantities=None, race=True):
    from datetime import timedelta
    from modules.gift_cards.models import GiftCampaign, GiftCampaignPage, GiftCardType
    from utils.timeutil import utcnow
    c = GiftCampaign(name='Akcja', bonus_product_id=bonus.id, status=status,
                     race_at=utcnow() + timedelta(days=1) if race else None)
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


def test_swap_over_stock_allowed_summary_shows_excess_and_blocks_approve(client, admin, db, setup, make_user,
                                                                         make_order, maile_synchronicznie):
    from extensions import mail
    from modules.gift_cards.models import GiftAssignment, GiftCampaign
    bonus, page = setup
    c = _campaign(db, bonus, page, status='zamknieta', quantities=[1, 1])
    _entitled(db, make_user, make_order, bonus, page)
    _entitled(db, make_user, make_order, bonus, page)
    client.post(f'{BASE}/{c.id}/rozdziel')
    a, b = GiftAssignment.query.order_by(GiftAssignment.id).all()
    a_type, b_type = a.card_type_id, b.card_type_id
    resp = client.post(f'{BASE}/{c.id}/zamien', json={'assignment_id': a.id, 'type_id': b_type})
    assert resp.get_json() == {'success': True}
    html = client.get(f'{BASE}/{c.id}').get_data(as_text=True)
    assert '2 / 1' in html and 'o 1 za dużo' in html and '0 / 1' in html
    assert 'Nie można zatwierdzić przydziału' in html
    with mail.record_messages() as outbox:
        client.post(f'{BASE}/{c.id}/zatwierdz')
    assert db.session.get(GiftCampaign, c.id).status == 'rozdzielona' and outbox == []
    # Druga zamiana kończy wymianę między osobami — można zatwierdzić.
    client.post(f'{BASE}/{c.id}/zamien', json={'assignment_id': b.id, 'type_id': a_type})
    html = client.get(f'{BASE}/{c.id}').get_data(as_text=True)
    assert 'za dużo' not in html and 'Nie można zatwierdzić przydziału' not in html
    client.post(f'{BASE}/{c.id}/zatwierdz')
    assert db.session.get(GiftCampaign, c.id).status == 'zatwierdzona'


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


def _second_page(db, make_user):
    from modules.offers.models import OfferPage
    p = OfferPage(name='Druga', token=OfferPage.generate_token(), status='active',
                  created_by=make_user(role='admin').id)
    db.session.add(p)
    db.session.commit()
    return p


def _edit_pages(client, c, bonus, page_ids):
    return client.post(f'{BASE}/{c.id}/edytuj', data={
        'name': 'Akcja', 'offer_page_ids': page_ids, 'bonus_product_id': bonus.id,
        'type_name': ['Typ A', 'Typ B'], 'type_existing_image': ['', '']})


def test_edit_draft_keeps_same_page_and_adds_second(client, admin, db, setup, make_user):
    bonus, page = setup
    c = _campaign(db, bonus, page)
    second = _second_page(db, make_user)
    resp = _edit_pages(client, c, bonus, [page.id, second.id])
    assert resp.status_code == 302
    db.session.refresh(c)
    assert sorted(c.offer_page_ids) == sorted([page.id, second.id])


def test_edit_draft_removes_a_page(client, admin, db, setup, make_user):
    bonus, page = setup
    c = _campaign(db, bonus, page)
    second = _second_page(db, make_user)
    _edit_pages(client, c, bonus, [page.id, second.id])
    resp = _edit_pages(client, c, bonus, [second.id])
    assert resp.status_code == 302
    db.session.refresh(c)
    assert c.offer_page_ids == [second.id]


# ---- Strażnik zatwierdzenia (I1) ----

def _distributed(client, db, bonus, page, make_user, make_order, qty=1):
    c = _campaign(db, bonus, page, status='zamknieta', quantities=[2, 2])
    u, item = _entitled(db, make_user, make_order, bonus, page, qty=qty)
    other, _ = _entitled(db, make_user, make_order, bonus, page)
    client.post(f'{BASE}/{c.id}/rozdziel')
    return c, u, item


def test_cancelled_order_after_distribute_banner_and_approve_blocked(client, admin, db, setup, make_user,
                                                                    make_order, maile_synchronicznie):
    from extensions import mail
    from modules.gift_cards.models import GiftCampaign
    bonus, page = setup
    c, u, item = _distributed(client, db, bonus, page, make_user, make_order)
    item.order.status = 'anulowane'; db.session.commit()
    html = client.get(f'{BASE}/{c.id}').get_data(as_text=True)
    assert 'Nie można zatwierdzić przydziału' in html
    assert f'{u.full_name} — nie ma już uprawnień do kart' in html
    # Osoba bez uprawnień nadal widnieje w tabeli razem ze swoją kartą.
    assert html.count('bez uprawnień') == 1 and html.count('data-assignment-id') == 2
    assert 'disabled>Zatwierdź i wyślij wyniki' in html
    with mail.record_messages() as outbox:
        client.post(f'{BASE}/{c.id}/zatwierdz')
    assert db.session.get(GiftCampaign, c.id).status == 'rozdzielona' and outbox == []
    with client.session_transaction() as sess:
        assert any('rozdziel karty ponownie' in m for _, m in sess['_flashes'])
    # Ponowny rozdział naprawia sytuację.
    client.post(f'{BASE}/{c.id}/rozdziel')
    assert 'Nie można zatwierdzić przydziału' not in client.get(f'{BASE}/{c.id}').get_data(as_text=True)


def test_quantity_lowered_after_distribute_blocks_approve(client, admin, db, setup, make_user, make_order,
                                                          maile_synchronicznie):
    from modules.gift_cards.models import GiftCampaign
    bonus, page = setup
    c, u, item = _distributed(client, db, bonus, page, make_user, make_order, qty=2)
    item.quantity = 1; db.session.commit()
    assert 'zmieniła się ilość gratisu (2 → 1)' in client.get(f'{BASE}/{c.id}').get_data(as_text=True)
    client.post(f'{BASE}/{c.id}/zatwierdz')
    assert db.session.get(GiftCampaign, c.id).status == 'rozdzielona'


# ---- Publikacja i zatwierdzenie tylko raz (M1, M2) ----

def test_publish_requires_race_at(client, admin, db, setup, make_user, make_order, maile_synchronicznie):
    from extensions import mail
    from modules.gift_cards.models import GiftCampaign
    bonus, page = setup
    c = _campaign(db, bonus, page, race=False)
    _entitled(db, make_user, make_order, bonus, page)
    with mail.record_messages() as outbox:
        client.post(f'{BASE}/{c.id}/publikuj')
    assert db.session.get(GiftCampaign, c.id).status == 'szkic' and outbox == []
    with client.session_transaction() as sess:
        assert ('error', 'Ustaw datę i godzinę wyścigu przed publikacją.') in sess['_flashes']


def _stale_campaign(monkeypatch, db, new_status):
    """Symuluje drugie, równoczesne kliknięcie: obiekt akcji ma stary status, w bazie jest już nowy."""
    from sqlalchemy import text
    import modules.gift_cards.routes_admin as routes
    real = routes._get_campaign

    def stale(cid):
        campaign = real(cid)
        _ = campaign.status  # załadowany stary status
        db.session.execute(text('UPDATE gift_campaigns SET status = :s WHERE id = :id'),
                           {'s': new_status, 'id': cid})
        return campaign

    monkeypatch.setattr(routes, '_get_campaign', stale)


def test_second_publish_sends_no_extra_mails(client, admin, db, setup, make_user, make_order,
                                             maile_synchronicznie, monkeypatch):
    from extensions import mail
    bonus, page = setup
    c = _campaign(db, bonus, page)
    _entitled(db, make_user, make_order, bonus, page)
    with mail.record_messages() as outbox:
        client.post(f'{BASE}/{c.id}/publikuj')
        client.post(f'{BASE}/{c.id}/publikuj')
    assert len(outbox) == 1
    # Równoczesne kliknięcie: status już zmieniony w bazie -> żadnych maili.
    c2 = _campaign(db, bonus, page)
    _stale_campaign(monkeypatch, db, 'otwarta')
    with mail.record_messages() as outbox:
        client.post(f'{BASE}/{c2.id}/publikuj')
    assert outbox == []
    with client.session_transaction() as sess:
        assert ('error', 'Akcja została już opublikowana.') in sess['_flashes']


def test_concurrent_approve_sends_no_extra_mails(client, admin, db, setup, make_user, make_order,
                                                 maile_synchronicznie, monkeypatch):
    from extensions import mail
    bonus, page = setup
    c, u, item = _distributed(client, db, bonus, page, make_user, make_order)
    _stale_campaign(monkeypatch, db, 'zatwierdzona')
    with mail.record_messages() as outbox:
        client.post(f'{BASE}/{c.id}/zatwierdz')
    assert outbox == []
    with client.session_transaction() as sess:
        assert ('error', 'Ta akcja została już zatwierdzona.') in sess['_flashes']


# ---- Grafiki rodzajów: tylko własne pliki akcji (I5) ----

@pytest.fixture
def static_tmp(app, tmp_path, monkeypatch):
    """Podmiana katalogu aplikacji na tymczasowy — testy nie dotykają prawdziwego static/."""
    monkeypatch.setattr(app, 'root_path', str(tmp_path))
    uploads = tmp_path / 'static' / 'uploads' / 'gift_cards' / 'compressed'
    uploads.mkdir(parents=True)
    secret = tmp_path / 'static' / 'sekret.txt'
    secret.write_text('nie ruszac')
    outside = tmp_path / 'poza.txt'
    outside.write_text('nie ruszac')
    return uploads, secret, outside


def test_crafted_existing_image_is_ignored(client, admin, db, setup, static_tmp):
    from modules.gift_cards.models import GiftCardType
    uploads, secret, outside = static_tmp
    bonus, page = setup
    c = _campaign(db, bonus, page)
    resp = client.post(f'{BASE}/{c.id}/edytuj', data={
        'name': 'Akcja', 'offer_page_ids': [page.id], 'bonus_product_id': bonus.id,
        'type_name': ['Typ A', 'Typ B'],
        'type_existing_image': ['uploads/gift_cards/../sekret.txt', '../poza.txt']})
    assert resp.status_code == 302
    assert [t.image_path for t in GiftCardType.query.filter_by(campaign_id=c.id)] == [None, None]
    assert secret.exists() and outside.exists()


def test_existing_image_of_this_campaign_is_kept(client, admin, db, setup, static_tmp):
    from modules.gift_cards.models import GiftCardType
    uploads, _, _ = static_tmp
    (uploads / 'a.png').write_bytes(b'x')
    bonus, page = setup
    c = _campaign(db, bonus, page)
    c.card_types[0].image_path = 'uploads/gift_cards/compressed/a.png'
    db.session.commit()
    client.post(f'{BASE}/{c.id}/edytuj', data={
        'name': 'Akcja', 'offer_page_ids': [page.id], 'bonus_product_id': bonus.id,
        'type_name': ['Typ A', 'Typ B'],
        'type_existing_image': ['uploads/gift_cards/compressed/a.png', '']})
    paths = [t.image_path for t in GiftCardType.query.filter_by(campaign_id=c.id).order_by(GiftCardType.sort_order)]
    assert paths == ['uploads/gift_cards/compressed/a.png', None]
    assert (uploads / 'a.png').exists()


def test_delete_type_image_only_inside_uploads(app, static_tmp):
    from modules.gift_cards.routes_admin import _delete_type_image
    uploads, secret, outside = static_tmp
    (uploads / 'b.png').write_bytes(b'x')
    with app.app_context():
        _delete_type_image('uploads/gift_cards/../sekret.txt')
        _delete_type_image('uploads/gift_cards/../../../poza.txt')
        _delete_type_image('../poza.txt')
        _delete_type_image('uploads/gift_cards/compressed/b.png')
    assert secret.exists() and outside.exists()
    assert not (uploads / 'b.png').exists()
