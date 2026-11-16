"""Uprawnienia do gratisowych kart i kolejka rozdziału."""
from dataclasses import dataclass, field
from datetime import datetime

from extensions import db
from modules.orders.models import Order, OrderItem
from modules.gift_cards.models import GiftRaceEntry

EXCLUDED_ORDER_STATUSES = ('anulowane', 'zwrocone')


@dataclass
class Entitlement:
    user_id: int
    items: list = field(default_factory=list)  # (order_item_id, quantity), wg Order.created_at, OrderItem.id
    first_order_at: datetime = None

    @property
    def total(self) -> int:
        return sum(q for _, q in self.items)


def compute_entitlements(campaign) -> dict:
    """Uprawnienia klientów: user_id -> Entitlement (gratisowe pozycje z zamówień akcji)."""
    page_ids = campaign.offer_page_ids
    if campaign.bonus_product_id is None or not page_ids:
        return {}

    rows = (
        db.session.query(OrderItem.id, OrderItem.quantity, Order.user_id, Order.created_at)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            OrderItem.is_bonus.is_(True),
            OrderItem.product_id == campaign.bonus_product_id,
            Order.offer_page_id.in_(page_ids),
            Order.status.notin_(EXCLUDED_ORDER_STATUSES),
        )
        .order_by(Order.created_at, OrderItem.id)
        .all()
    )

    result = {}
    for item_id, quantity, user_id, created_at in rows:
        ent = result.get(user_id)
        if ent is None:
            ent = result[user_id] = Entitlement(user_id=user_id, items=[], first_order_at=created_at)
        ent.items.append((item_id, quantity))
    return result


def queue_order(campaign, entitlements: dict) -> list:
    """Kolejka: najpierw uprawnieni z wyścigu (wg id wpisu), potem reszta wg pierwszego zamówienia."""
    racers = [e.user_id for e in campaign.race_entries if e.user_id in entitlements]
    racer_set = set(racers)
    rest = sorted(
        (e for uid, e in entitlements.items() if uid not in racer_set),
        key=lambda e: (e.first_order_at, e.user_id),
    )
    return racers + [e.user_id for e in rest]


def queue_position(campaign, user_id):
    """1-based miejsce w wyścigu albo None, gdy użytkownik nie kliknął."""
    entry = GiftRaceEntry.query.filter_by(campaign_id=campaign.id, user_id=user_id).first()
    if entry is None:
        return None
    return GiftRaceEntry.query.filter(
        GiftRaceEntry.campaign_id == campaign.id, GiftRaceEntry.id <= entry.id
    ).count()
