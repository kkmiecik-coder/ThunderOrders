from decimal import Decimal
import time


def _ex_order_type(db):
    from modules.orders.models import OrderType
    ot = OrderType.query.filter_by(slug='exclusive').first()
    if not ot:
        ot = OrderType(slug='exclusive', name='Exclusive', prefix='EX')
        db.session.add(ot); db.session.commit()
    return ot


def _active_page(db, payment_stages=3):
    from modules.offers.models import OfferPage
    p = OfferPage(name='Drop', token=OfferPage.generate_token(), status='active',
                  page_type='exclusive', payment_stages=payment_stages, created_by=1)
    db.session.add(p); db.session.commit()
    return p


def _product_section(db, page, product, max_quantity=10):
    from modules.offers.models import OfferSection
    s = OfferSection(offer_page_id=page.id, section_type='product',
                     product_id=product.id, max_quantity=max_quantity, sort_order=0)
    db.session.add(s); db.session.commit()
    return s


def _reserve(db, page, product, session_id, qty=1, user=None, size=None):
    from modules.offers.models import OfferReservation
    now = int(time.time())
    r = OfferReservation(session_id=session_id, offer_page_id=page.id, product_id=product.id,
                         quantity=qty, reserved_at=now, expires_at=now + 120,
                         user_id=user.id if user else None, selected_size=size)
    db.session.add(r); db.session.commit()
    return r


def test_place_offer_order_happy_path(app, db, make_user, make_product):
    from modules.offers.place_order import place_offer_order
    from modules.orders.models import Order, OrderItem
    _ex_order_type(db)
    user = make_user(); make_user()  # created_by=1 istnieje
    page = _active_page(db, payment_stages=3)
    prod = make_product(sale_price=Decimal('50.00'))
    _product_section(db, page, prod, max_quantity=10)
    sid = 'sess-aaaa'
    _reserve(db, page, prod, sid, qty=2, user=user)

    # Serwis wysyła push/email przez url_for(_external=True); w produkcji zawsze
    # działa w request context (trasa web/mobile). Tu wołamy go wprost, więc
    # owijamy w test_request_context (konwencja repo).
    with app.test_request_context():
        ok, result = place_offer_order(page=page, session_id=sid, user=user)

    assert ok is True
    order = db.session.get(Order, result['order_id'])
    assert order.order_type == 'exclusive'
    assert order.user_id == user.id
    assert order.payment_stages == 3
    assert order.status == 'nowe'
    assert float(order.total_amount) == 100.0
    assert OrderItem.query.filter_by(order_id=order.id).count() == 1
    # Rezerwacje usunięte
    from modules.offers.models import OfferReservation
    assert OfferReservation.query.filter_by(session_id=sid).count() == 0


def test_place_offer_order_size_required(db, make_user, make_product):
    from modules.offers.place_order import place_offer_order
    from modules.products.models import Size
    _ex_order_type(db)
    user = make_user(); make_user()
    page = _active_page(db)
    prod = make_product(sale_price=Decimal('10.00'))
    size = Size(name='M'); db.session.add(size); db.session.commit()
    prod.sizes.append(size); db.session.commit()
    _product_section(db, page, prod)
    sid = 'sess-bbbb'
    _reserve(db, page, prod, sid, qty=1, user=user, size=None)  # brak rozmiaru

    ok, result = place_offer_order(page=page, session_id=sid, user=user)
    assert ok is False
    assert result['error'] == 'size_required'


def test_place_offer_order_no_reservations(db, make_user):
    from modules.offers.place_order import place_offer_order
    _ex_order_type(db)
    user = make_user(); make_user()
    page = _active_page(db)
    ok, result = place_offer_order(page=page, session_id='empty', user=user)
    assert ok is False
    assert result['error'] == 'no_reservations'
