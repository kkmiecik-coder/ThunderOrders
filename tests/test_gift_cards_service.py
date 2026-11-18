import pytest

from tests.gift_helpers import add_pool, add_types, set_stock


def test_race_entry_unique_per_user(db, make_user, make_product):
    from sqlalchemy.exc import IntegrityError
    from modules.gift_cards.models import GiftCampaign, GiftRaceEntry
    c = GiftCampaign(name='ATEEZ')
    db.session.add(c); db.session.commit()
    u = make_user()
    db.session.add(GiftRaceEntry(campaign_id=c.id, user_id=u.id)); db.session.commit()
    db.session.add(GiftRaceEntry(campaign_id=c.id, user_id=u.id))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_participant_ranking_property(db, make_user, make_product):
    from modules.gift_cards.models import GiftCampaign, GiftParticipant
    c = GiftCampaign(name='X'); db.session.add(c); db.session.commit()
    p = GiftParticipant(campaign_id=c.id, user_id=make_user().id)
    assert p.ranking == []
    p.ranking_json = '[3, 1, 2]'
    assert p.ranking == [3, 1, 2]
    assert c.status == 'szkic'



def test_campaign_defaults_kind_gratis_and_results_visible(db):
    from modules.gift_cards.models import GiftCampaign
    c = GiftCampaign(name='X'); db.session.add(c); db.session.commit()
    assert c.kind == 'gratis'
    assert c.results_hidden is False
    assert c.is_purchase is False
    z = GiftCampaign(name='Z', kind='zakup'); db.session.add(z); db.session.commit()
    assert z.is_purchase is True

# ---- Task 2: uprawnienia i kolejka ----

@pytest.fixture
def akcja(db, make_user, make_product, strona_sprzedazy):
    from modules.gift_cards.models import GiftCampaign, GiftCampaignPage
    bonus = make_product(name='Gratis')
    c = GiftCampaign(name='Akcja')
    db.session.add(c); db.session.commit()
    db.session.add(GiftCampaignPage(campaign_id=c.id, offer_page_id=strona_sprzedazy.id))
    db.session.commit()
    add_pool(db, c, bonus)
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
    db.session.delete(c.pools[0]); db.session.commit(); db.session.refresh(c)
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
    return add_types(db, c, ilosci)


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
    assert [r.picks for r in result.values()] == [{}] and c.status == 'rozdzielona'


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


def test_swap_over_stock_allowed_but_blocks_approve_until_fixed(db, make_user, make_order, akcja):
    """Zamiana swobodna (decyzja I2 = A): nadmiar sztuk blokuje zatwierdzenie, nie zamianę."""
    from modules.gift_cards.models import GiftAssignment
    from modules.gift_cards.service import GiftCardsError, approve, distribution_problems, swap_assignment
    c, a, b, ia, ib, t = _dwoje_z_kartami(db, make_user, make_order, akcja)
    a_row = GiftAssignment.query.filter_by(user_id=a.id).one()
    b_row = GiftAssignment.query.filter_by(user_id=b.id).one()
    assert b_row.card_type_id == t['Yunho'].id  # San poszedł do A
    swap_assignment(b_row.id, t['San'].id)
    assert b_row.card_type_id == t['San'].id and b_row.rank_position == 1
    assert distribution_problems(c) == ['San — przydzielono 2, a jest 1 szt. (o 1 za dużo).']
    with pytest.raises(GiftCardsError, match='więcej przydziałów niż sztuk'):
        approve(c)
    assert c.status == 'rozdzielona'
    # Wymiana kart między dwiema osobami = dwie zamiany; po drugiej wszystko się zgadza.
    swap_assignment(a_row.id, t['Yunho'].id)
    assert distribution_problems(c) == []
    approve(c)
    assert c.status == 'zatwierdzona'


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



# ---- Kupione produkty (rodzaj akcji „zakup”) ----

@pytest.fixture
def akcja_zakup(db, make_product, strona_sprzedazy):
    from modules.gift_cards.models import GiftCampaign, GiftCampaignPage
    produkt = make_product(name='Trading PC')
    c = GiftCampaign(name='Trading', kind='zakup')
    db.session.add(c); db.session.commit()
    db.session.add(GiftCampaignPage(campaign_id=c.id, offer_page_id=strona_sprzedazy.id))
    db.session.commit()
    add_pool(db, c, produkt)
    return c, produkt, strona_sprzedazy


def test_purchase_entitlements_count_regular_items_only(db, make_user, make_order, akcja_zakup):
    from modules.gift_cards.service import compute_entitlements
    c, produkt, page = akcja_zakup
    u = make_user()
    o = make_order(u, offer_page_id=page.id)
    _bonus(db, o, produkt, 3, is_bonus=False)
    _bonus(db, o, produkt, 2, is_bonus=True)
    assert compute_entitlements(c)[u.id].total == 3


def test_gratis_campaign_ignores_regular_items_of_same_product(db, make_user, make_order, akcja):
    from modules.gift_cards.service import compute_entitlements
    c, bonus, page = akcja
    u = make_user()
    o = make_order(u, offer_page_id=page.id)
    _bonus(db, o, bonus, 3, is_bonus=False)
    _bonus(db, o, bonus, 2, is_bonus=True)
    assert compute_entitlements(c)[u.id].total == 2


def _zakup_rozdzielony(db, make_user, make_order, akcja_zakup):
    from modules.gift_cards.service import run_distribution
    c, produkt, page = akcja_zakup
    u = make_user()
    item = _bonus(db, make_order(u, offer_page_id=page.id), produkt, 1, is_bonus=False)
    t = _typy(db, c, San=1, Yunho=1)
    _ranking(db, c, u, [t['San'], t['Yunho']])
    c.status = 'otwarta'; db.session.commit()
    pending = item.gift_cards_label
    c.status = 'zamknieta'; db.session.commit()
    run_distribution(c)
    return c, item, pending


def test_purchase_label_pending_then_names_after_approve(db, make_user, make_order, akcja_zakup):
    from modules.gift_cards.service import approve
    c, item, pending = _zakup_rozdzielony(db, make_user, make_order, akcja_zakup)
    assert pending == 'przydział w toku'
    approve(c)
    assert item.gift_cards_label == 'San'
    assert item.client_gift_cards_label == 'San'


def test_client_label_hidden_when_results_hidden(db, make_user, make_order, akcja_zakup):
    from modules.gift_cards.service import approve
    c, item, _ = _zakup_rozdzielony(db, make_user, make_order, akcja_zakup)
    approve(c)
    c.results_hidden = True; db.session.commit()
    assert item.gift_cards_label == 'San'
    assert item.client_gift_cards_label is None


def test_purchase_item_in_open_campaign_has_link(db, make_user, make_order, akcja_zakup):
    c, produkt, page = akcja_zakup
    item = _bonus(db, make_order(make_user(), offer_page_id=page.id), produkt, 1, is_bonus=False)
    c.status = 'otwarta'; db.session.commit()
    assert item.open_gift_campaign == c


def test_regular_item_label_no_extra_queries_without_purchase_campaigns(app, db, make_user, make_order,
                                                                         make_product, akcja):
    from sqlalchemy import event
    c, bonus, page = akcja
    c.status = 'otwarta'; db.session.commit()
    o = make_order(make_user(), offer_page_id=page.id)
    items = [_bonus(db, o, make_product(name=f'Album {i}'), 1, is_bonus=False) for i in range(5)]
    for it in items:
        db.session.refresh(it); it.order  # załaduj relacje przed liczeniem
    queries = []
    listener = lambda *args, **kw: queries.append(1)
    with app.test_request_context():
        event.listen(db.engine, 'before_cursor_execute', listener)
        try:
            labels = [it.gift_cards_label for it in items]
        finally:
            event.remove(db.engine, 'before_cursor_execute', listener)
    assert labels == [None] * 5
    assert len(queries) <= 1

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


# ---- Strażnik zatwierdzenia: zmiany od rozdziału (I1) ----

def test_run_distribution_saves_entitlements_snapshot(db, make_user, make_order, akcja):
    import json
    c, a, b, ia, ib, t = _dwoje_z_kartami(db, make_user, make_order, akcja)
    assert json.loads(c.entitlements_snapshot) == {str(a.id): [[ia.id, 1]], str(b.id): [[ib.id, 1]]}


def test_problems_empty_right_after_distribution_and_outside_distributed(db, make_user, make_order, akcja):
    from modules.gift_cards.service import distribution_problems
    c, a, b, ia, ib, t = _dwoje_z_kartami(db, make_user, make_order, akcja)
    assert distribution_problems(c) == []
    ia.order.status = 'anulowane'; db.session.commit()
    assert distribution_problems(c) != []
    c.status = 'zamknieta'; db.session.commit()
    assert distribution_problems(c) == []


def test_cancelled_order_after_distribution_blocks_approve(db, make_user, make_order, akcja):
    from modules.gift_cards.service import GiftCardsError, approve, distribution_problems
    c, a, b, ia, ib, t = _dwoje_z_kartami(db, make_user, make_order, akcja)
    ia.order.status = 'anulowane'; db.session.commit()
    problems = distribution_problems(c)
    assert len(problems) == 1 and a.full_name in problems[0] and 'nie ma już uprawnień' in problems[0]
    with pytest.raises(GiftCardsError, match='rozdziel karty ponownie'):
        approve(c)
    assert c.status == 'rozdzielona'


def test_bonus_quantity_lowered_after_distribution_blocks_approve(db, make_user, make_order, akcja):
    from modules.gift_cards.service import GiftCardsError, approve, distribution_problems, run_distribution
    c, bonus, page = akcja
    a = make_user()
    item = _bonus(db, make_order(a, offer_page_id=page.id), bonus, 2)
    _typy(db, c, San=2, Yunho=2)
    c.status = 'zamknieta'; db.session.commit()
    run_distribution(c)
    item.quantity = 1; db.session.commit()
    assert distribution_problems(c) == [f'{a.full_name} — zmieniła się ilość gratisu (2 → 1).']
    with pytest.raises(GiftCardsError, match='rozdziel karty ponownie'):
        approve(c)
    run_distribution(c)  # ponowny rozdział zapisuje nowy stan
    assert distribution_problems(c) == []
    approve(c)
    assert c.status == 'zatwierdzona'


def test_new_entitled_person_and_new_item_after_distribution(db, make_user, make_order, akcja):
    from modules.gift_cards.service import distribution_problems
    c, a, b, ia, ib, t = _dwoje_z_kartami(db, make_user, make_order, akcja)
    c_, bonus, page = akcja
    nowa = make_user()
    _bonus(db, make_order(nowa, offer_page_id=page.id), bonus, 1)
    _bonus(db, make_order(a, offer_page_id=page.id), bonus, 1)
    problems = distribution_problems(c)
    assert f'{nowa.full_name} — nowa osoba uprawniona do kart.' in problems
    assert f'{a.full_name} — nowa pozycja gratisowa w zamówieniu.' in problems


def test_card_quantity_lowered_after_distribution_blocks_approve(db, make_user, make_order, akcja):
    from modules.gift_cards.service import GiftCardsError, approve, distribution_problems
    c, a, b, ia, ib, t = _dwoje_z_kartami(db, make_user, make_order, akcja)
    set_stock(db, c.pools[0], {t['San']: 0})
    assert distribution_problems(c) == ['San — przydzielono 1, a jest 0 szt. (o 1 za dużo).']
    with pytest.raises(GiftCardsError):
        approve(c)


# ---- Task 5: maile ----

def test_pl_cards_plural_forms():
    from modules.gift_cards.emails import pl_cards
    assert [pl_cards(n) for n in (1, 2, 4, 5, 12, 14, 22, 25)] == [
        '1 karta', '2 karty', '4 karty', '5 kart', '12 kart', '14 kart', '22 karty', '25 kart']


def test_send_invites_one_mail_per_entitled_user(db, app, make_user, make_order, akcja, maile_synchronicznie):
    from datetime import datetime, timezone
    from extensions import mail
    from modules.gift_cards.emails import send_invites
    c, bonus, page = akcja
    a, b, nie = make_user(email='a@example.com'), make_user(email='b@example.com'), make_user(email='n@example.com')
    _bonus(db, make_order(a, offer_page_id=page.id), bonus, 3)
    _bonus(db, make_order(b, offer_page_id=page.id), bonus, 1)
    c.race_at = datetime(2026, 12, 1, 18, 30, tzinfo=timezone.utc)  # zima: 19:30 w Polsce
    db.session.commit()
    with app.test_request_context(), mail.record_messages() as out:
        assert send_invites(c) == 2
    assert len(out) == 2
    by_rcpt = {m.recipients[0]: m for m in out}
    assert set(by_rcpt) == {'a@example.com', 'b@example.com'}
    assert 'przysługują Ci 3 karty' in by_rcpt['a@example.com'].body
    assert 'przysługuje Ci 1 karta' in by_rcpt['b@example.com'].body
    assert '01.12.2026 19:30' in by_rcpt['a@example.com'].body
    assert f'/gratisy/{c.id}' in by_rcpt['a@example.com'].html
    assert by_rcpt['a@example.com'].subject == 'Gratisowe karty: Akcja - ThunderOrders'


def test_send_results_lists_cards_and_shortage(db, app, make_user, make_order, akcja, maile_synchronicznie):
    from extensions import mail
    from modules.gift_cards.emails import send_results
    from modules.gift_cards.models import GiftAssignment
    c, bonus, page = akcja
    a = make_user(email='a@example.com')
    item = _bonus(db, make_order(a, offer_page_id=page.id), bonus, 3)
    t = _typy(db, c, San=1, Yunho=1)
    for rnd, nazwa in ((2, 'Yunho'), (1, 'San')):
        db.session.add(GiftAssignment(campaign_id=c.id, user_id=a.id, order_item_id=item.id,
                                      pool_id=c.pools[0].id, card_type_id=t[nazwa].id, round_no=rnd))
    db.session.commit()
    with app.test_request_context(), mail.record_messages() as out:
        assert send_results(c) == 1
    body = out[0].body
    assert 'San, Yunho' in body and 'Brakuje 1 karta — skontaktujemy się w tej sprawie.' in body
    assert 'San, Yunho' in out[0].html
    assert out[0].subject == 'Twoje gratisowe karty: Akcja - ThunderOrders'


@pytest.mark.parametrize('n, expected', [
    (1, 'przysługuje Ci 1 karta'),
    (2, 'przysługują Ci 2 karty'),
    (4, 'przysługują Ci 4 karty'),
    (5, 'przysługuje Ci 5 kart'),
    (6, 'przysługuje Ci 6 kart'),
    (12, 'przysługuje Ci 12 kart'),
    (22, 'przysługują Ci 22 karty'),
])
def test_entitled_text_polish_grammar(n, expected):
    from modules.gift_cards.emails import _entitled_text
    assert _entitled_text(n) == expected


# ---- Pule: kilka gratisów w jednej akcji ----

@pytest.fixture
def dwie_pule(db, make_product, akcja):
    """Akcja z pulami 50k (pierwsza) i 100k; rodzaje San/Yunho wspólne."""
    c, bonus50, page = akcja
    bonus50.name = 'Benefit 50k'
    bonus100 = make_product(name='Benefit 100k')
    p100 = add_pool(db, c, bonus100)
    p50 = c.pools[0]
    t = add_types(db, c, {'San': 1, 'Yunho': 1}, pool=p50)
    set_stock(db, p100, {t['San']: 1, t['Yunho']: 1})
    return c, page, (p50, bonus50), (p100, bonus100), t


def test_entitlements_split_per_pool(db, make_user, make_order, dwie_pule):
    from modules.gift_cards.service import compute_entitlements, pool_breakdown
    c, page, (p50, b50), (p100, b100), _ = dwie_pule
    a = make_user()
    o = make_order(a, offer_page_id=page.id)
    _bonus(db, o, b50, 2); _bonus(db, o, b100, 1)
    ent = compute_entitlements(c)[a.id]
    assert ent.total == 3
    assert ent.pool_total(p50.id) == 2 and ent.pool_total(p100.id) == 1
    assert [(p.id, n) for p, n in pool_breakdown(c, ent)] == [(p50.id, 2), (p100.id, 1)]
    assert p100.label == 'Benefit 100k'


def test_distribution_per_pool_same_type_is_not_duplicate(db, make_user, make_order, dwie_pule):
    from modules.gift_cards.models import GiftAssignment
    from modules.gift_cards.service import run_distribution
    c, page, (p50, b50), (p100, b100), t = dwie_pule
    a = make_user()
    o = make_order(a, offer_page_id=page.id)
    _bonus(db, o, b50, 1); _bonus(db, o, b100, 1)
    _ranking(db, c, a, [t['San'], t['Yunho']])
    c.status = 'zamknieta'; db.session.commit()
    run_distribution(c)
    rows = GiftAssignment.query.filter_by(campaign_id=c.id).order_by(GiftAssignment.pool_id).all()
    assert [(r.pool_id, r.card_type_id, r.is_duplicate) for r in rows] == [
        (p50.id, t['San'].id, False), (p100.id, t['San'].id, False)]


def test_person_only_in_one_pool_gets_only_that_pool(db, make_user, make_order, dwie_pule):
    from modules.gift_cards.models import GiftAssignment
    from modules.gift_cards.service import run_distribution
    c, page, (p50, b50), (p100, b100), t = dwie_pule
    a, b = make_user(), make_user()
    _bonus(db, make_order(a, offer_page_id=page.id), b50, 1)
    _bonus(db, make_order(b, offer_page_id=page.id), b100, 2)
    c.status = 'zamknieta'; db.session.commit()
    run_distribution(c)
    by_user = {}
    for r in GiftAssignment.query.filter_by(campaign_id=c.id).all():
        by_user.setdefault(r.user_id, set()).add(r.pool_id)
    assert by_user == {a.id: {p50.id}, b.id: {p100.id}}


def test_zero_stock_in_pool_is_never_assigned(db, make_user, make_order, dwie_pule):
    from modules.gift_cards.models import GiftAssignment
    from modules.gift_cards.service import run_distribution
    c, page, (p50, b50), (p100, b100), t = dwie_pule
    set_stock(db, p100, {t['San']: 0})
    a = make_user()
    _bonus(db, make_order(a, offer_page_id=page.id), b100, 1)
    _ranking(db, c, a, [t['San'], t['Yunho']])
    c.status = 'zamknieta'; db.session.commit()
    run_distribution(c)
    row = GiftAssignment.query.filter_by(campaign_id=c.id).one()
    assert row.pool_id == p100.id and row.card_type_id == t['Yunho'].id


def test_missing_stock_in_second_pool_blocks_distribution(db, make_user, make_order, dwie_pule):
    from modules.gift_cards.service import GiftCardsError, run_distribution
    c, page, (p50, b50), (p100, b100), t = dwie_pule
    set_stock(db, p100, {t['Yunho']: None})
    c.status = 'zamknieta'; db.session.commit()
    with pytest.raises(GiftCardsError):
        run_distribution(c)


def test_stock_problem_names_the_pool(db, make_user, make_order, dwie_pule):
    from modules.gift_cards.service import distribution_problems, run_distribution
    c, page, (p50, b50), (p100, b100), t = dwie_pule
    a = make_user()
    _bonus(db, make_order(a, offer_page_id=page.id), b100, 1)
    c.status = 'zamknieta'; db.session.commit()
    run_distribution(c)
    set_stock(db, p100, {t['San']: 0, t['Yunho']: 0})
    problems = distribution_problems(c)
    assert len(problems) == 1 and '(Benefit 100k)' in problems[0]


def test_swap_duplicates_counted_within_pool(db, make_user, make_order, dwie_pule):
    from modules.gift_cards.models import GiftAssignment
    from modules.gift_cards.service import run_distribution, swap_assignment
    c, page, (p50, b50), (p100, b100), t = dwie_pule
    a = make_user()
    o = make_order(a, offer_page_id=page.id)
    _bonus(db, o, b50, 1); _bonus(db, o, b100, 1)
    _ranking(db, c, a, [t['Yunho'], t['San']])
    c.status = 'zamknieta'; db.session.commit()
    run_distribution(c)
    row50 = GiftAssignment.query.filter_by(campaign_id=c.id, pool_id=p50.id).one()
    swap_assignment(row50.id, t['San'].id)
    swap_assignment(row50.id, t['Yunho'].id)  # ten sam rodzaj co w 100k — to nie powtórka
    assert not any(r.is_duplicate for r in GiftAssignment.query.filter_by(campaign_id=c.id))


def test_label_pending_for_item_of_second_pool(db, make_user, make_order, dwie_pule):
    from modules.gift_cards.service import item_gift_label
    c, page, (p50, b50), (p100, b100), t = dwie_pule
    c.status = 'otwarta'; db.session.commit()
    item = _bonus(db, make_order(make_user(), offer_page_id=page.id), b100, 1)
    assert item_gift_label(item) == 'przydział w toku'
