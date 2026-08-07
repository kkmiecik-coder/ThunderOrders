"""WMS: pakowanie zlecenia wysyłki jako jednej paczki."""

import pytest


# ---------- pomocnicze ----------

def _seed_statuses(db):
    """Statusy zamówień — testowa baza startuje pusta."""
    from modules.orders.models import OrderStatus
    for slug, name in (('dostarczone_gom', 'Dostarczone GOM'),
                       ('spakowane', 'Spakowane'),
                       ('wyslane', 'Wysłane')):
        if not OrderStatus.query.filter_by(slug=slug).first():
            db.session.add(OrderStatus(slug=slug, name=name, is_active=True))
    db.session.commit()


def _order_with_item(db, user, make_order, make_product, weight, dims, qty=1):
    """Zamówienie z jedną pozycją produktową o zadanej wadze i wymiarach."""
    from modules.orders.models import OrderItem
    o = make_order(user, status='dostarczone_gom')
    p = make_product(weight=weight, length=dims[0], width=dims[1], height=dims[2])
    # price i total są NOT NULL w OrderItem — muszą być podane wprost.
    db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=qty,
                             price=10.00, total=10.00 * qty,
                             picked=True, picked_quantity=qty))
    db.session.commit()
    return o


# ---------- Task 1: sugestie dla grupy ----------

def test_suggest_for_group_sums_weight_of_all_orders(app, db, make_user, make_order,
                                                     make_product):
    """Dopasowanie liczy się po sumie wszystkich zamówień z paczki, nie po jednym."""
    from modules.orders.wms_utils import suggest_packaging_for_orders
    u = make_user()
    o1 = _order_with_item(db, u, make_order, make_product, weight=1.5, dims=(10, 10, 10))
    o2 = _order_with_item(db, u, make_order, make_product, weight=2.0, dims=(10, 10, 10))

    result = suggest_packaging_for_orders([o1, o2])

    assert result['total_weight'] == 3.5
    # objętość: 2 × 1000 cm³ × bufor 1.3
    assert result['total_volume'] == pytest.approx(2600.0)


def test_suggest_single_order_unchanged(app, db, make_user, make_order, make_product):
    """suggest_packaging(order) zwraca to samo co suggest_packaging_for_orders([order])."""
    from modules.orders.wms_utils import suggest_packaging, suggest_packaging_for_orders
    u = make_user()
    o = _order_with_item(db, u, make_order, make_product, weight=1.5, dims=(10, 10, 10))

    assert suggest_packaging(o) == suggest_packaging_for_orders([o])


def test_suggest_for_group_without_items_warns(app, db, make_user, make_order):
    """Grupa bez pozycji zwraca ostrzeżenie zamiast wywalać się."""
    from modules.orders.wms_utils import suggest_packaging_for_orders
    u = make_user()
    o = make_order(u, status='dostarczone_gom')

    result = suggest_packaging_for_orders([o])

    assert result['suggestions'] == []
    assert result['warnings'] == ['Zamówienie nie ma pozycji']
