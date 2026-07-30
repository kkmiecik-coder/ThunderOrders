"""Testy rozróżnienia NULL (cło nieustalone) od 0 (cło ustalone na zero)."""
from decimal import Decimal


def test_new_order_has_null_customs_by_default(db, make_user, make_order):
    # NULL = "jeszcze nie ustalono"; wcześniej domyślną wartością było 0.00
    u = make_user()
    o = make_order(u, order_type='exclusive')
    assert o.customs_vat_sale_cost is None


def test_order_accepts_explicit_zero(db, make_user, make_order):
    # 0 = "ustalono: bez podatku" — musi dać się zapisać i odczytać jako zero, nie NULL
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    db.session.refresh(o)
    assert o.customs_vat_sale_cost is not None
    assert o.customs_vat_sale_cost == 0


def test_poland_order_item_customs_defaults_to_null(db, make_product):
    from modules.products.models import PolandOrder, PolandOrderItem, ProxyOrder, ProxyOrderItem
    p = make_product()
    proxy = ProxyOrder(order_number='PRX/TEST/1', order_type='proxy', status='zamowiono')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=p.id,
                                quantity=1, unit_price=10, total_price=10)
    db.session.add(proxy_item)
    db.session.flush()
    po = PolandOrder(order_number='PL/TEST/1', proxy_order_id=proxy.id, status='zamowione')
    db.session.add(po)
    db.session.flush()
    item = PolandOrderItem(poland_order_id=po.id, proxy_order_item_id=proxy_item.id,
                           product_id=p.id, quantity=1)
    db.session.add(item)
    db.session.commit()
    assert item.customs_vat_percentage is None
    assert item.customs_vat_amount is None


def test_stage_keys_omit_customs_when_zero(db, make_user, make_order):
    from modules.client.payment_confirmation_service import order_stage_keys
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    assert 'customs_vat' not in order_stage_keys(o)


def test_stage_keys_include_customs_when_null(db, make_user, make_order):
    # NULL = nie ustalono → etap nadal obecny (klient widzi "Zablokowane")
    from modules.client.payment_confirmation_service import order_stage_keys
    u = make_user()
    o = make_order(u, order_type='exclusive')
    assert o.customs_vat_sale_cost is None
    assert 'customs_vat' in order_stage_keys(o)


def test_stage_keys_include_customs_when_positive(db, make_user, make_order):
    from modules.client.payment_confirmation_service import order_stage_keys
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('50.00'))
    assert 'customs_vat' in order_stage_keys(o)


def test_upload_rejected_for_zero_customs(db, make_user, make_order):
    # Brak etapu → brak możliwości opłacenia (wymóg właścicielki)
    from modules.client.payment_confirmation_service import validate_bulk_upload
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    ok, err = validate_bulk_upload(u.id, [{'order_id': o.id, 'stages': ['customs_vat']}])
    assert not ok and err['code'] == 'stage_not_applicable'


def test_mobile_stages_omit_customs_when_zero(db, make_user, make_order):
    # API mobilne czyta order_stage_keys — zmiana propaguje się bez osobnego kodu
    from modules.api_mobile.orders_routes import _serialize_payment_stages
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    assert 'customs_vat' not in [s['stage'] for s in _serialize_payment_stages(o)]


def test_settled_false_when_customs_not_set(db, make_user, make_order):
    # Decyzja właścicielki: dopóki cło nie jest ustalone, wysyłki zlecić nie można
    u = make_user()
    o = make_order(u, order_type='exclusive')
    assert o.customs_vat_sale_cost is None
    assert o.is_customs_vat_settled is False


def test_settled_true_when_customs_zero(db, make_user, make_order):
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    assert o.is_customs_vat_settled is True


def test_settled_false_when_customs_due_unpaid(db, make_user, make_order):
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('50.00'))
    assert o.is_customs_vat_settled is False


def test_settled_true_for_on_hand_regardless(db, make_user, make_order):
    u = make_user()
    o = make_order(u, order_type='on_hand')
    assert o.is_customs_vat_settled is True


def test_shipping_blocked_with_not_set_code(db, make_user, make_order):
    # "Nieustalone" musi mieć własny kod — komunikat "opłać" byłby mylący,
    # bo klient nie ma czego opłacić
    from modules.client.shipping_service import validate_and_create_request
    from tests.test_shipping_service import _seed_status, _allow, _addr
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom', order_type='exclusive')
    ok, err, req = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert not ok and err['code'] == 'customs_vat_not_set'
    assert o.id in err['customs_vat_not_set_order_ids'] and req is None


def test_shipping_allowed_when_customs_zero(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    from tests.test_shipping_service import _seed_status, _allow, _addr
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom', order_type='exclusive',
                   customs_vat_sale_cost=Decimal('0.00'))
    ok, err, req = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert ok and req is not None


def test_shipping_unpaid_code_unchanged_for_due_customs(db, make_user, make_order):
    # Kwota > 0 nieopłacona → nadal stary kod, bez zmiany zachowania
    from modules.client.shipping_service import validate_and_create_request
    from tests.test_shipping_service import _seed_status, _allow, _addr
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom', order_type='exclusive',
                   customs_vat_sale_cost=Decimal('50.00'))
    ok, err, _ = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert not ok and err['code'] == 'customs_vat_unpaid'


def _client_order_with_product(db, make_user, make_order, make_product, price, qty=1):
    """Zamówienie klienta z jedną pozycją danego produktu — wspólne dla testów dystrybucji."""
    from modules.orders.models import OrderItem
    from modules.offers.models import OfferPage
    u = make_user()
    admin = make_user(role='admin')
    page = OfferPage(name='Strona testowa', token=OfferPage.generate_token(),
                     status='active', created_by=admin.id)
    db.session.add(page)
    db.session.flush()
    p = make_product()
    o = make_order(u, order_type='exclusive', offer_page_id=page.id)
    db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=qty,
                             price=price, total=price * qty))
    db.session.commit()
    return o, p


def test_zero_percentage_clears_client_amount(db, make_user, make_order, make_product):
    # Scenariusz właścicielki: najpierw 23%, potem poprawka na "bez podatku"
    from modules.products.routes import _distribute_customs_vat_to_client_orders
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)

    _distribute_customs_vat_to_client_orders({p.id: Decimal('23')})
    db.session.commit()
    assert o.customs_vat_sale_cost == Decimal('230.00')

    _distribute_customs_vat_to_client_orders({p.id: Decimal('0')})
    db.session.commit()
    assert o.customs_vat_sale_cost == 0          # zero, nie NULL — to zapisana decyzja
    assert o.customs_vat_sale_cost is not None


def test_zeroing_sends_no_notifications(db, make_user, make_order, make_product, monkeypatch):
    # Decyzja właścicielki: przy zejściu kwoty do zera nie wysyłamy nic
    from modules.products import routes as product_routes
    sent = []
    monkeypatch.setattr('utils.email_manager.EmailManager.notify_costs_added_bulk',
                        lambda *a, **kw: sent.append('email'), raising=False)
    product_routes._notify_distributed_costs({1: {'old': 230.0, 'new': 0.0}}, 'customs_vat')
    assert sent == []


def test_zero_customs_order_reaches_fully_paid(db, make_user, make_order):
    # Zamówienie bez cła nie może wisieć w "do zapłaty" czekając na wpłatę, której nie ma
    from modules.orders.models import PaymentConfirmation
    from modules.offers.models import OfferPage
    from modules.client.payment_confirmation_service import get_confirmation_orders
    u = make_user()
    admin = make_user(role='admin')
    # get_confirmation_orders bierze pod uwagę tylko zamówienia z oferty (offer_page_id)
    # albo on_hand — bez strony oferty zamówienie nie trafia do żadnego koszyka.
    page = OfferPage(name='Strona testowa', token=OfferPage.generate_token(),
                     status='active', created_by=admin.id)
    db.session.add(page)
    db.session.commit()
    o = make_order(u, order_type='pre_order', status='nowe', payment_stages=3,
                   offer_page_id=page.id,
                   customs_vat_sale_cost=Decimal('0.00'), shipping_cost=Decimal('15.00'))
    for stage in ('product', 'domestic_shipping'):
        db.session.add(PaymentConfirmation(order_id=o.id, payment_stage=stage,
                                           amount=Decimal('10.00'), status='approved'))
    db.session.commit()
    buckets = get_confirmation_orders(u.id)
    assert o.id in [x.id for x in buckets['recent_paid']]
    assert o.id not in [x.id for x in buckets['payable']]


def test_positive_rate_does_not_clear_unfulfilled_item(db, make_user, make_order, make_product):
    # Decyzja właścicielki: zwykła korekta stawki nie może kasować kwoty
    # na pozycji, której klient i tak nie dostaje
    from modules.products.routes import _distribute_customs_vat_to_client_orders
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    _distribute_customs_vat_to_client_orders({p.id: Decimal('23')})
    db.session.commit()
    assert o.customs_vat_sale_cost == Decimal('230.00')

    o.items[0].is_set_fulfilled = False          # klient jednak nie dostaje tej pozycji
    db.session.commit()

    _distribute_customs_vat_to_client_orders({p.id: Decimal('25')})   # korekta stawki
    db.session.commit()
    assert o.customs_vat_sale_cost == Decimal('230.00')   # kwota nietknięta


def test_zero_rate_clears_even_unfulfilled_item(db, make_user, make_order, make_product):
    # Stawka 0 = "bez podatku" — zeruje niezależnie od realizacji pozycji
    from modules.products.routes import _distribute_customs_vat_to_client_orders
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    _distribute_customs_vat_to_client_orders({p.id: Decimal('23')})
    db.session.commit()
    o.items[0].is_set_fulfilled = False
    db.session.commit()

    _distribute_customs_vat_to_client_orders({p.id: Decimal('0')})
    db.session.commit()
    assert o.customs_vat_sale_cost == 0


def test_positive_rate_does_not_clear_free_item_only_order(db, make_user, make_order,
                                                           make_product):
    # Gratis (cena 0) nie generuje cła, więc nie może też skasować etapu E3:
    # przy stawce dodatniej zamówienie z samą pozycją gratisową zostaje nietknięte
    from modules.products.routes import _distribute_customs_vat_to_client_orders
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('0.00'), qty=5)
    assert o.customs_vat_sale_cost is None

    _distribute_customs_vat_to_client_orders({p.id: Decimal('23')})
    db.session.commit()
    assert o.customs_vat_sale_cost is None        # nietknięte, nie 0
    assert o.has_customs_vat_stage is True        # etap nadal dotyczy


def test_zero_rate_still_clears_free_item_only_order(db, make_user, make_order, make_product):
    # Stawka 0 = zapisana decyzja "bez podatku" — zeruje niezależnie od ceny pozycji
    from modules.products.routes import _distribute_customs_vat_to_client_orders
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('0.00'), qty=5)
    _distribute_customs_vat_to_client_orders({p.id: Decimal('0')})
    db.session.commit()
    assert o.customs_vat_sale_cost == 0
    assert o.customs_vat_sale_cost is not None


def _poland_setup(db, order, product, percentage):
    """Paczka do Polski z jedną pozycją — minimalne dane dla endpointu cła."""
    from modules.products.models import (PolandOrder, PolandOrderItem,
                                          ProxyOrder, ProxyOrderItem)
    proxy = ProxyOrder(order_number=f'PRX/T/{order.id}',
                       order_type='proxy', status='zamowiono')
    db.session.add(proxy)
    db.session.flush()
    pi = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product.id,
                        quantity=1, unit_price=10, total_price=10)
    db.session.add(pi)
    db.session.flush()
    po = PolandOrder(order_number=f'PL/T/{order.id}', proxy_order_id=proxy.id,
                     status='zamowione')
    db.session.add(po)
    db.session.flush()
    item = PolandOrderItem(poland_order_id=po.id, proxy_order_item_id=pi.id,
                           product_id=product.id, quantity=1,
                           customs_vat_percentage=percentage)
    db.session.add(item)
    db.session.commit()
    return po, item


DEADLINE = '2026-12-31T23:59'   # termin w przyszłości — endpoint go dziś wymaga


def _blocked_zeroing_response(client, db, make_user, make_order, make_product,
                              login, stage3_status):
    """Wspólny scenariusz: cło 230 zł opłacone/oczekujące, próba zejścia do zera."""
    from modules.orders.models import PaymentConfirmation
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    o.customs_vat_sale_cost = Decimal('230.00')
    db.session.add(PaymentConfirmation(order_id=o.id, payment_stage='customs_vat',
                                       amount=Decimal('230.00'), status=stage3_status))
    _, item = _poland_setup(db, o, p, Decimal('23'))
    r = client.put('/admin/products/api/update-poland-customs-vat',
                   json={'items': [{'poland_order_item_id': item.id,
                                    'customs_vat_percentage': 0}],
                         'customs_payment_deadline': DEADLINE})
    return o, r


def test_zeroing_blocked_when_stage3_approved(client, db, make_user, make_order,
                                              make_product, login):
    o, r = _blocked_zeroing_response(client, db, make_user, make_order, make_product,
                                     login, 'approved')
    assert r.status_code == 409
    assert r.get_json()['success'] is False
    assert o.order_number in r.get_json()['error']


def test_zeroing_blocked_when_stage3_pending(client, db, make_user, make_order,
                                             make_product, login):
    # Wgrane potwierdzenie = przelew najpewniej już wyszedł
    o, r = _blocked_zeroing_response(client, db, make_user, make_order, make_product,
                                     login, 'pending')
    assert r.status_code == 409


def test_zeroing_allowed_when_stage3_untouched(client, db, make_user, make_order,
                                               make_product, login):
    # Brak potwierdzenia → wyzerowanie przechodzi normalnie
    o, r = _blocked_zeroing_response(client, db, make_user, make_order, make_product,
                                     login, 'rejected')
    assert r.status_code == 200 and r.get_json()['success'] is True


def test_no_customs_saves_zero_not_null(client, db, make_user, make_order,
                                        make_product, login):
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    po, item = _poland_setup(db, o, p, None)

    r = client.put('/admin/products/api/update-poland-customs-vat',
                   json={'items': [{'poland_order_item_id': item.id,
                                    'customs_vat_percentage': 0}],
                         'no_customs': True})
    assert r.status_code == 200 and r.get_json()['success'] is True
    db.session.refresh(item)
    assert item.customs_vat_percentage == 0        # zapisana decyzja, nie brak decyzji
    assert item.customs_vat_percentage is not None
    assert item.customs_vat_amount == 0


def test_empty_percentage_does_not_touch_item(client, db, make_user, make_order,
                                              make_product, login):
    # Puste pole % w modalu = brak decyzji. Front wysyła null, serwer pomija
    # pozycję — inaczej pusty wiersz zapisałby 0 ("bez podatku").
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    o.customs_vat_sale_cost = Decimal('230.00')
    po, item = _poland_setup(db, o, p, Decimal('23'))

    r = client.put('/admin/products/api/update-poland-customs-vat',
                   json={'items': [{'poland_order_item_id': item.id,
                                    'customs_vat_percentage': None}],
                         'customs_payment_deadline': DEADLINE})
    assert r.status_code == 200 and r.get_json()['success'] is True
    db.session.refresh(item); db.session.refresh(o)
    assert item.customs_vat_percentage == Decimal('23')      # stawka nietknięta
    assert o.customs_vat_sale_cost == Decimal('230.00')      # kwota u klienta nietknięta


def test_empty_percentage_keeps_client_customs_null(client, db, make_user, make_order,
                                                    make_product, login):
    # Najgroźniejszy wariant: cło jeszcze nieustalone (NULL) nie może przez
    # pusty wiersz zamienić się w 0 i skasować klientowi etap E3.
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    po, item = _poland_setup(db, o, p, None)
    assert o.customs_vat_sale_cost is None

    r = client.put('/admin/products/api/update-poland-customs-vat',
                   json={'items': [{'poland_order_item_id': item.id,
                                    'customs_vat_percentage': ''}],
                         'customs_payment_deadline': DEADLINE})
    assert r.status_code == 200
    db.session.refresh(item); db.session.refresh(o)
    assert item.customs_vat_percentage is None
    assert o.customs_vat_sale_cost is None
    assert o.has_customs_vat_stage is True                   # etap nadal dotyczy


def test_explicit_zero_percentage_still_zeroes(client, db, make_user, make_order,
                                               make_product, login):
    # Jawnie wpisane 0 to nadal decyzja "bez podatku" — musi zerować.
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    o.customs_vat_sale_cost = Decimal('230.00')
    po, item = _poland_setup(db, o, p, Decimal('23'))

    r = client.put('/admin/products/api/update-poland-customs-vat',
                   json={'items': [{'poland_order_item_id': item.id,
                                    'customs_vat_percentage': 0}],
                         'customs_payment_deadline': DEADLINE})
    assert r.status_code == 200 and r.get_json()['success'] is True
    db.session.refresh(item); db.session.refresh(o)
    assert item.customs_vat_percentage == 0
    assert o.customs_vat_sale_cost == 0


def test_no_customs_zeroes_even_with_empty_percentage(client, db, make_user, make_order,
                                                      make_product, login):
    # Tryb "bez cła/VAT" czyści pola % w modalu — mimo to wszystkie pozycje
    # muszą dostać 0 (przełącznik dotyczy całej paczki).
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    po, item = _poland_setup(db, o, p, Decimal('23'))

    r = client.put('/admin/products/api/update-poland-customs-vat',
                   json={'items': [{'poland_order_item_id': item.id,
                                    'customs_vat_percentage': None}],
                         'no_customs': True})
    assert r.status_code == 200 and r.get_json()['success'] is True
    db.session.refresh(item); db.session.refresh(o)
    assert item.customs_vat_percentage == 0
    assert item.customs_vat_amount == 0
    assert o.customs_vat_sale_cost == 0


def test_no_customs_clears_payment_deadline(client, db, make_user, make_order,
                                            make_product, login):
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    po, item = _poland_setup(db, o, p, Decimal('23'))
    from datetime import datetime
    po.customs_payment_deadline = datetime(2026, 12, 31, 23, 59)
    db.session.commit()

    client.put('/admin/products/api/update-poland-customs-vat',
               json={'items': [{'poland_order_item_id': item.id,
                                'customs_vat_percentage': 0}],
                     'no_customs': True})
    db.session.refresh(po)
    assert po.customs_payment_deadline is None     # nie ma płatności → nie ma terminu


def test_deadline_still_required_with_customs(client, db, make_user, make_order,
                                              make_product, login):
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    po, item = _poland_setup(db, o, p, None)

    r = client.put('/admin/products/api/update-poland-customs-vat',
                   json={'items': [{'poland_order_item_id': item.id,
                                    'customs_vat_percentage': 23}]})
    assert r.status_code == 400
    assert 'Termin' in r.get_json()['error']


def test_not_set_property_distinguishes_from_unpaid(db, make_user, make_order):
    u = make_user()
    not_set = make_order(u, order_type='exclusive')
    due = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('50.00'))
    zero = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    on_hand = make_order(u, order_type='on_hand')
    assert not_set.is_customs_vat_not_set is True
    assert due.is_customs_vat_not_set is False
    assert zero.is_customs_vat_not_set is False
    assert on_hand.is_customs_vat_not_set is False


def _available_orders_setup(db, make_user, make_order, login):
    """Dwa zamówienia gotowe do zlecenia wysyłki: cło nieustalone vs. nieopłacone."""
    from tests.test_shipping_service import _seed_status, _allow
    _seed_status(db); _allow(db)
    u = make_user(profile_completed=True); login(u)
    not_set = make_order(u, status='dostarczone_gom', order_type='exclusive')
    due = make_order(u, status='dostarczone_gom', order_type='exclusive',
                     customs_vat_sale_cost=Decimal('50.00'))
    db.session.commit()
    return u, not_set, due


def test_available_orders_web_distinguishes_not_set(client, db, make_user, make_order, login):
    # Klient z nieustalonym cłem nie może zobaczyć "Najpierw opłać Cło/VAT"
    _, not_set, due = _available_orders_setup(db, make_user, make_order, login)
    data = client.get('/client/shipping/requests/available-orders').get_json()
    assert data['success'] is True
    by_id = {o['id']: o for o in data['orders']}

    assert by_id[not_set.id]['customs_vat_paid'] is False
    assert by_id[not_set.id]['customs_vat_not_set'] is True
    assert by_id[due.id]['customs_vat_paid'] is False
    assert by_id[due.id]['customs_vat_not_set'] is False


def test_available_orders_mobile_distinguishes_not_set(db, make_user, make_order, login):
    # Parytet API mobilnego z wersją webową
    from modules.api_mobile.shipping_routes import _serialize_available_order
    _, not_set, due = _available_orders_setup(db, make_user, make_order, login)

    a = _serialize_available_order(not_set)
    b = _serialize_available_order(due)
    assert a['customs_vat_paid'] is False and a['customs_vat_not_set'] is True
    assert b['customs_vat_paid'] is False and b['customs_vat_not_set'] is False


def _update_customs_field(client, order, value):
    """Ręczna edycja kwoty Cła/VAT w szczegółach zamówienia (panel admina)."""
    return client.post(f'/admin/orders/{order.id}/update-field',
                       json={'field': 'customs_vat_sale_cost', 'value': value})


def test_manual_edit_empty_saves_null(client, db, make_user, make_order, login):
    # Puste pole = "nieustalone" (NULL). Zapis 0 znaczyłby "ustalono: bez cła"
    # i skasowałby klientowi etap E3 oraz odblokował wysyłkę.
    admin = make_user(role='admin'); login(admin)
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('230.00'))
    db.session.commit()

    r = _update_customs_field(client, o, '')
    assert r.status_code == 200 and r.get_json()['success'] is True
    db.session.refresh(o)
    assert o.customs_vat_sale_cost is None
    assert o.has_customs_vat_stage is True
    assert o.is_customs_vat_settled is False


def test_manual_edit_null_saves_null(client, db, make_user, make_order, login):
    admin = make_user(role='admin'); login(admin)
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('230.00'))
    db.session.commit()

    r = _update_customs_field(client, o, None)
    assert r.status_code == 200
    db.session.refresh(o)
    assert o.customs_vat_sale_cost is None


def test_manual_edit_explicit_zero_saves_zero(client, db, make_user, make_order, login):
    # Jawne 0 to nadal świadoma decyzja "bez cła" — musi się zapisać jako 0.
    admin = make_user(role='admin'); login(admin)
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('230.00'))
    db.session.commit()

    r = _update_customs_field(client, o, 0)
    assert r.status_code == 200 and r.get_json()['success'] is True
    db.session.refresh(o)
    assert o.customs_vat_sale_cost is not None
    assert o.customs_vat_sale_cost == 0
    assert o.has_customs_vat_stage is False


def _manual_zeroing_blocked(client, db, make_user, make_order, login, stage3_status, value):
    from modules.orders.models import PaymentConfirmation
    admin = make_user(role='admin'); login(admin)
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('230.00'))
    db.session.add(PaymentConfirmation(order_id=o.id, payment_stage='customs_vat',
                                       amount=Decimal('230.00'), status=stage3_status))
    db.session.commit()
    r = _update_customs_field(client, o, value)
    db.session.refresh(o)
    return o, r


def test_manual_zeroing_blocked_when_stage3_approved(client, db, make_user, make_order, login):
    o, r = _manual_zeroing_blocked(client, db, make_user, make_order, login, 'approved', 0)
    assert r.status_code == 409
    assert r.get_json()['success'] is False
    assert o.order_number in r.get_json()['message']
    assert o.customs_vat_sale_cost == Decimal('230.00')      # kwota nietknięta


def test_manual_zeroing_blocked_when_stage3_pending(client, db, make_user, make_order, login):
    # Wgrane potwierdzenie = przelew najpewniej już wyszedł
    o, r = _manual_zeroing_blocked(client, db, make_user, make_order, login, 'pending', 0)
    assert r.status_code == 409
    assert o.customs_vat_sale_cost == Decimal('230.00')


def test_manual_clearing_blocked_when_stage3_approved(client, db, make_user, make_order, login):
    # Zejście do NULL jest tak samo groźne jak do zera
    o, r = _manual_zeroing_blocked(client, db, make_user, make_order, login, 'approved', '')
    assert r.status_code == 409
    assert o.customs_vat_sale_cost == Decimal('230.00')


def test_manual_zeroing_allowed_when_stage3_untouched(client, db, make_user, make_order, login):
    o, r = _manual_zeroing_blocked(client, db, make_user, make_order, login, 'rejected', 0)
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert o.customs_vat_sale_cost == 0


def test_manual_edit_shipping_cost_empty_still_zero(client, db, make_user, make_order, login):
    # Parytet: pozostałe koszty zachowują dotychczasowe zachowanie (puste → 0.00)
    admin = make_user(role='admin'); login(admin)
    u = make_user()
    o = make_order(u, order_type='exclusive', shipping_cost=Decimal('15.00'))
    db.session.commit()

    r = client.post(f'/admin/orders/{o.id}/update-field',
                    json={'field': 'shipping_cost', 'value': ''})
    assert r.status_code == 200
    db.session.refresh(o)
    assert o.shipping_cost == 0
    assert o.shipping_cost is not None


def _order_on_confirmations_page(db, make_user, make_order, login, **kwargs):
    """Zamówienie widoczne na stronie potwierdzeń płatności.

    get_confirmation_orders() filtruje `offer_page_id IS NOT NULL OR order_type == 'on_hand'`,
    więc samo pre_order bez strony ofertowej w ogóle nie trafia na listę.
    """
    from modules.offers.models import OfferPage
    u = make_user(profile_completed=True); login(u)
    admin = make_user(role='admin')
    page = OfferPage(name='Strona testowa', token=OfferPage.generate_token(),
                     status='active', created_by=admin.id)
    db.session.add(page)
    db.session.flush()
    make_order(u, order_type='pre_order', status='nowe', payment_stages=3,
               offer_page_id=page.id, shipping_cost=Decimal('15.00'), **kwargs)
    db.session.commit()
    return u


def test_client_view_hides_customs_row_when_zero(client, db, make_user, make_order, login):
    _order_on_confirmations_page(db, make_user, make_order, login,
                                 customs_vat_sale_cost=Decimal('0.00'))
    html = client.get('/client/payment-confirmations').get_data(as_text=True)
    assert 'Cło/VAT' not in html
    assert 'data-has-customs-vat="false"' in html


def test_client_view_shows_customs_row_when_not_set(client, db, make_user, make_order, login):
    # NULL = nie ustalono → wiersz nadal widoczny (bez zmian wobec dziś)
    _order_on_confirmations_page(db, make_user, make_order, login)
    html = client.get('/client/payment-confirmations').get_data(as_text=True)
    assert 'Cło/VAT' in html
    assert 'data-has-customs-vat="true"' in html


def test_admin_tooltip_omits_customs_when_zero(db, make_user, make_order):
    # Ikona statusu na liście admina nie może czekać na wpłatę, której nie ma
    u = make_user()
    o = make_order(u, order_type='exclusive', payment_stages=3,
                   customs_vat_sale_cost=Decimal('0.00'))
    assert 'E3 Cło/VAT' not in o.payment_icon_state['tooltip']


def test_admin_tooltip_shows_customs_when_not_set(db, make_user, make_order):
    u = make_user()
    o = make_order(u, order_type='exclusive', payment_stages=3)
    assert 'E3 Cło/VAT' in o.payment_icon_state['tooltip']
