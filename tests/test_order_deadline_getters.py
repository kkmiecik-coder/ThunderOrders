from datetime import datetime


def test_get_product_deadline_from_offer_page(db, make_user, make_order):
    from modules.offers.models import OfferPage

    user = make_user()
    admin = make_user(role='admin')
    deadline = datetime(2026, 8, 1, 12, 0)
    page = OfferPage(name='Test Page', token=OfferPage.generate_token(), payment_deadline=deadline, created_by=admin.id)
    db.session.add(page)
    db.session.commit()

    order = make_order(user, offer_page_id=page.id)

    assert order.get_product_deadline() == deadline


def test_get_product_deadline_none_without_offer_page(db, make_user, make_order):
    user = make_user()
    order = make_order(user)

    assert order.get_product_deadline() is None
