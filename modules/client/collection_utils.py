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

    - Skips guest orders (no user_id)
    - Checks for duplicates via order_item_id (idempotent)
    - For quantity > 1, creates separate CollectionItem per unit (K-pop = unique items)
    - Uses order_item.price as initial market_price

    Args:
        order: Order model instance
    """
    from modules.client.models import CollectionItem

    # Skip guest orders
    if not order.user_id:
        return

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
