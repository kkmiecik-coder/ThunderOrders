"""Pomocniki testów gratisowych kart: pule i ilości sztuk."""


def add_pool(db, campaign, product, sort_order=None):
    """Dodaje pulę (produkt-gratis) do akcji."""
    from modules.gift_cards.models import GiftCampaignPool
    pool = GiftCampaignPool(campaign_id=campaign.id, bonus_product_id=product.id,
                            sort_order=len(campaign.pools) if sort_order is None else sort_order)
    db.session.add(pool)
    db.session.commit()
    db.session.refresh(campaign)
    return pool


def set_stock(db, pool, quantities):
    """quantities: {GiftCardType: ilość albo None} — tworzy lub nadpisuje wiersze stanu puli."""
    from modules.gift_cards.models import GiftPoolStock
    for card_type, quantity in quantities.items():
        row = GiftPoolStock.query.filter_by(pool_id=pool.id, card_type_id=card_type.id).first()
        if row is None:
            db.session.add(GiftPoolStock(pool_id=pool.id, card_type_id=card_type.id, quantity=quantity))
        else:
            row.quantity = quantity
    db.session.commit()


def add_types(db, campaign, quantities, pool=None):
    """quantities: {nazwa: ilość} — rodzaje kart akcji; ilości trafiają do `pool` (domyślnie pierwszej puli)."""
    from modules.gift_cards.models import GiftCardType
    start = len(campaign.card_types)
    out = {}
    for i, (name, _) in enumerate(quantities.items()):
        card_type = GiftCardType(campaign_id=campaign.id, name=name, sort_order=start + i)
        db.session.add(card_type)
        out[name] = card_type
    db.session.commit()
    db.session.refresh(campaign)
    pool = pool or (campaign.pools[0] if campaign.pools else None)
    if pool is not None:
        set_stock(db, pool, {out[name]: q for name, q in quantities.items()})
    return out
