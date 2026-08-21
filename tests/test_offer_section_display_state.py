"""Stan wyświetlania sekcji strony pre-order: Aktywna / Sold-out / Ukryta.

Sekcja przełączona na Sold-out lub Ukryta znika ze sprzedaży, ale NIE rusza
złożonych już zamówień — dlatego blokada siedzi w warstwie zamawiania
(preorder_page_product_ids + place_preorder_order), a nie w modelu zamówień.
"""
from decimal import Decimal


def _po_order_type(db):
    from modules.orders.models import OrderType
    ot = OrderType.query.filter_by(slug='pre_order').first()
    if not ot:
        ot = OrderType(slug='pre_order', name='Pre-order', prefix='PO')
        db.session.add(ot); db.session.commit()
    return ot


def _preorder_page(db):
    from modules.offers.models import OfferPage
    p = OfferPage(name='Preorder Drop', token=OfferPage.generate_token(), status='active',
                  page_type='preorder', payment_stages=3, created_by=1)
    db.session.add(p); db.session.commit()
    return p


def _product_section(db, page, product, display_state='active', sort_order=0):
    from modules.offers.models import OfferSection
    s = OfferSection(offer_page_id=page.id, section_type='product',
                     product_id=product.id, sort_order=sort_order,
                     display_state=display_state)
    db.session.add(s); db.session.commit()
    return s


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def test_display_state_defaults_to_active(db, make_user, make_product):
    """Sekcje sprzed migracji i nowo tworzone są aktywne — bez zmiany zachowania."""
    from modules.offers.models import OfferSection
    make_user()  # OfferPage.created_by=1 musi wskazywać na istniejącego użytkownika
    page = _preorder_page(db)
    prod = make_product()
    s = OfferSection(offer_page_id=page.id, section_type='product', product_id=prod.id)
    db.session.add(s); db.session.commit()

    assert s.display_state == 'active'
    assert s.is_visible is True
    assert s.is_sold_out is False
    assert s.is_purchasable is True


def test_helpers_reflect_each_state(db, make_user, make_product):
    make_user()
    page = _preorder_page(db)
    sold_out = _product_section(db, page, make_product(), 'sold_out')
    hidden = _product_section(db, page, make_product(), 'hidden', sort_order=1)

    assert (sold_out.is_visible, sold_out.is_sold_out, sold_out.is_purchasable) == (True, True, False)
    assert (hidden.is_visible, hidden.is_sold_out, hidden.is_purchasable) == (False, False, False)


# ---------------------------------------------------------------------------
# Zamawialność
# ---------------------------------------------------------------------------

def test_purchasable_ids_skip_sold_out_and_hidden(db, make_user, make_product):
    from modules.offers.place_order import preorder_page_product_ids
    make_user()
    page = _preorder_page(db)
    active = make_product()
    sold_out = make_product()
    hidden = make_product()
    _product_section(db, page, active, 'active', 0)
    _product_section(db, page, sold_out, 'sold_out', 1)
    _product_section(db, page, hidden, 'hidden', 2)

    assert preorder_page_product_ids(page) == {active.id}
    # Wariant "wszystko ze strony" — potrzebny, by odróżnić produkt spoza strony
    # od produktu wyłączonego ze sprzedaży
    assert preorder_page_product_ids(page, only_purchasable=False) == {
        active.id, sold_out.id, hidden.id
    }


def test_order_with_sold_out_item_is_rejected_with_names(db, make_user, make_product):
    from modules.offers.place_order import place_preorder_order
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    prod = make_product(sale_price=Decimal('50.00'), name='Bransoletka')
    _product_section(db, page, prod, 'sold_out')

    ok, result = place_preorder_order(
        page=page, cart_items=[{'product_id': prod.id, 'quantity': 1}], user=user
    )

    assert ok is False
    assert result['error'] == 'items_unavailable'
    assert 'Bransoletka' in result['message']
    assert result['product_ids'] == [prod.id]


def test_hidden_section_item_is_rejected(db, make_user, make_product):
    from modules.offers.place_order import place_preorder_order
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    prod = make_product(sale_price=Decimal('20.00'))
    _product_section(db, page, prod, 'hidden')

    ok, result = place_preorder_order(
        page=page, cart_items=[{'product_id': prod.id, 'quantity': 1}], user=user
    )

    assert ok is False
    assert result['error'] == 'items_unavailable'


def test_active_items_still_go_through(db, make_user, make_product):
    """Wyłączenie jednej sekcji nie może zablokować sprzedaży pozostałych."""
    from modules.offers.place_order import place_preorder_order
    from modules.orders.models import Order
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    ok_prod = make_product(sale_price=Decimal('30.00'))
    _product_section(db, page, ok_prod, 'active', 0)
    _product_section(db, page, make_product(), 'sold_out', 1)

    ok, result = place_preorder_order(
        page=page, cart_items=[{'product_id': ok_prod.id, 'quantity': 2}], user=user
    )

    assert ok is True
    order = db.session.get(Order, result['order_id'])
    assert float(order.total_amount) == 60.0


def test_existing_orders_survive_switching_section_off(db, make_user, make_product):
    """Sedno funkcji: przełączenie sekcji nie rusza już złożonych zamówień."""
    from modules.offers.place_order import place_preorder_order
    from modules.orders.models import Order, OrderItem
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    prod = make_product(sale_price=Decimal('45.00'))
    section = _product_section(db, page, prod, 'active')

    ok, result = place_preorder_order(
        page=page, cart_items=[{'product_id': prod.id, 'quantity': 3}], user=user
    )
    assert ok is True
    order_id = result['order_id']

    section.display_state = 'sold_out'
    db.session.commit()

    order = db.session.get(Order, order_id)
    items = OrderItem.query.filter_by(order_id=order_id).all()
    assert order is not None
    assert len(items) == 1
    assert items[0].product_id == prod.id
    assert items[0].quantity == 3
    assert float(order.total_amount) == 135.0


# ---------------------------------------------------------------------------
# Bonusy
# ---------------------------------------------------------------------------

def test_bonus_from_disabled_section_is_not_granted(db, make_user, make_product):
    from modules.offers.models import OfferSection, OfferSetBonus
    from modules.offers.place_order import place_preorder_order
    from modules.orders.models import OrderItem
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    prod = make_product(sale_price=Decimal('100.00'))
    _product_section(db, page, prod, 'active')

    gift = make_product(sale_price=Decimal('10.00'))
    bonus_section = OfferSection(offer_page_id=page.id, section_type='bonus',
                                 sort_order=1, display_state='hidden')
    db.session.add(bonus_section); db.session.commit()
    db.session.add(OfferSetBonus(
        section_id=bonus_section.id, trigger_type='price_threshold',
        threshold_value=Decimal('50.00'), bonus_product_id=gift.id,
        bonus_quantity=1, is_active=True
    ))
    db.session.commit()

    ok, result = place_preorder_order(
        page=page, cart_items=[{'product_id': prod.id, 'quantity': 1}], user=user
    )

    assert ok is True
    bonus_items = OrderItem.query.filter_by(order_id=result['order_id'], is_bonus=True).all()
    assert bonus_items == []


# ---------------------------------------------------------------------------
# Walidacja zapisu w adminie
# ---------------------------------------------------------------------------

def test_sold_out_rejected_for_text_sections():
    from modules.admin.offers import _validate_section_data
    ok, error = _validate_section_data({'type': 'heading', 'display_state': 'sold_out'})
    assert ok is False
    assert 'Sold-out' in error


def test_hidden_allowed_for_text_sections():
    from modules.admin.offers import _validate_section_data
    ok, _ = _validate_section_data({'type': 'paragraph', 'display_state': 'hidden'})
    assert ok is True


def test_unknown_state_rejected():
    from modules.admin.offers import _validate_section_data
    ok, error = _validate_section_data({'type': 'product', 'display_state': 'whatever'})
    assert ok is False
    assert 'stan' in error.lower()


# ---------------------------------------------------------------------------
# Mapa niedostępności dla koszyka
# ---------------------------------------------------------------------------

def test_unavailable_map_lists_only_disabled_sections(db, make_user, make_product):
    from modules.offers.routes import build_preorder_unavailable_map
    make_user()
    page = _preorder_page(db)
    active = make_product()
    sold_out = make_product()
    hidden = make_product()
    sections = [
        _product_section(db, page, active, 'active', 0),
        _product_section(db, page, sold_out, 'sold_out', 1),
        _product_section(db, page, hidden, 'hidden', 2),
    ]

    mapping = build_preorder_unavailable_map(sections)

    assert mapping == {sold_out.id: 'sold_out', hidden.id: 'hidden'}
