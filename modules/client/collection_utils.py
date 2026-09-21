"""
Collection Utils - Auto-add mechanism
=======================================

Automatically adds order items to user's collection when order status
changes to 'dostarczone'.
"""

from flask import current_app
from extensions import db


def auto_add_order_to_collection(order):
    """
    Automatically add order items to user's collection.

    - Checks for duplicates via order_item_id (idempotent)
    - For quantity > 1, creates separate CollectionItem per unit (K-pop = unique items)
    - Uses order_item.price as initial market_price

    Args:
        order: Order model instance

    Returns:
        int|None: user_id, jeśli dopisano choć jedną pozycję (wtedy trzeba po
            commicie wywołać `sprawdz_odznaki_kolekcji`); None, gdy nic nie doszło.
    """
    from modules.client.models import CollectionItem

    dopisano = False

    for item in order.items:
        # Check if already added (idempotent)
        existing = CollectionItem.query.filter_by(
            user_id=order.user_id,
            order_item_id=item.id
        ).first()
        if existing:
            continue

        # Skip items that were not fulfilled in set (is_set_fulfilled == False)
        if item.is_set_fulfilled is False:
            continue

        # Determine effective quantity
        effective_qty = item.quantity
        if item.fulfilled_quantity is not None:
            effective_qty = item.fulfilled_quantity

        if effective_qty <= 0:
            continue

        # Create separate items for each unit
        for i in range(effective_qty):
            name = item.product_name
            if effective_qty > 1:
                name = f"{item.product_name} ({i + 1}/{effective_qty})"

            collection_item = CollectionItem(
                user_id=order.user_id,
                name=name,
                market_price=float(item.price) if item.price else None,
                source='order',
                order_item_id=item.id if i == 0 else None,  # Link only first to avoid FK duplication
                product_id=item.product_id,
                notes=None
            )
            db.session.add(collection_item)
            dopisano = True

    return order.user_id if dopisano else None


def sprawdz_odznaki_kolekcji(user_ids):
    """
    Odpala `check_event('collection_add')` dla użytkowników, którym auto-dodawanie
    dopisało pozycje.

    WOŁAĆ DOPIERO PO `db.session.commit()`. `AchievementService.unlock()` robi
    własny `db.session.commit()`, więc wywołane wcześniej zatwierdziłoby razem
    z odznaką niedokończoną zmianę statusu zamówienia. To ten sam układ, co
    w `collection_service.add_item` (commit → check_event).

    Bez tego wywołania kolekcja rośnie sama przy dostawie, licznik na ekranie
    klienta rośnie, a odznaki collection-* nie odblokowują się NIGDY — bo nic
    innego nie porównuje postępu z faktem odblokowania.

    Args:
        user_ids: iterowalne z id użytkowników (None-y są pomijane)
    """
    from modules.achievements.services import AchievementService
    from modules.auth.models import User

    service = AchievementService()
    for user_id in {uid for uid in user_ids if uid}:
        try:
            user = db.session.get(User, user_id)
            if user is not None:
                service.check_event(user, 'collection_add')
        except Exception as err:
            current_app.logger.error(
                f'Odznaki kolekcji dla user_id={user_id}: {err}', exc_info=True)
