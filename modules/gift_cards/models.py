import json

from extensions import db
from utils.timeutil import UTCDateTime, utcnow

STATUS_DRAFT = 'szkic'
STATUS_OPEN = 'otwarta'
STATUS_CLOSED = 'zamknieta'
STATUS_DISTRIBUTED = 'rozdzielona'
STATUS_APPROVED = 'zatwierdzona'


class GiftCampaign(db.Model):
    __tablename__ = 'gift_campaigns'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_DRAFT)
    race_at = db.Column(UTCDateTime, nullable=True)
    created_at = db.Column(UTCDateTime, default=utcnow, nullable=False)
    updated_at = db.Column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    # JSON {user_id: [[order_item_id, ilość], ...]} — uprawnienia z chwili rozdziału (strażnik zatwierdzenia)
    entitlements_snapshot = db.Column(db.Text, nullable=True)

    pools = db.relationship('GiftCampaignPool', backref='campaign', cascade='all, delete-orphan',
                            order_by='GiftCampaignPool.sort_order, GiftCampaignPool.id')
    pages = db.relationship('GiftCampaignPage', backref='campaign', cascade='all, delete-orphan')
    card_types = db.relationship('GiftCardType', backref='campaign', cascade='all, delete-orphan',
                                 order_by='GiftCardType.sort_order, GiftCardType.id')
    participants = db.relationship('GiftParticipant', backref='campaign', cascade='all, delete-orphan')
    race_entries = db.relationship('GiftRaceEntry', backref='campaign', cascade='all, delete-orphan',
                                   order_by='GiftRaceEntry.id')
    assignments = db.relationship('GiftAssignment', backref='campaign', cascade='all, delete-orphan')

    @property
    def offer_page_ids(self):
        return [p.offer_page_id for p in self.pages]

    @property
    def bonus_product_ids(self):
        return [p.bonus_product_id for p in self.pools if p.bonus_product_id is not None]

    def stock_map(self) -> dict:
        """(pool_id, card_type_id) -> ilość (None = jeszcze nie wpisana)."""
        return {(s.pool_id, s.card_type_id): s.quantity for pool in self.pools for s in pool.stock}

    def __repr__(self):
        return f'<GiftCampaign {self.id}: {self.name} [{self.status}]>'


class GiftCampaignPage(db.Model):
    __tablename__ = 'gift_campaign_pages'
    __table_args__ = (db.UniqueConstraint('campaign_id', 'offer_page_id', name='uq_gift_campaign_page'),)

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('gift_campaigns.id', ondelete='CASCADE'), nullable=False)
    offer_page_id = db.Column(db.Integer, db.ForeignKey('offer_pages.id', ondelete='CASCADE'), nullable=False)

    offer_page = db.relationship('OfferPage', foreign_keys=[offer_page_id])


class GiftCampaignPool(db.Model):
    """Pula = jeden produkt-gratis w akcji (np. „50k benefit” i „100k benefit”)."""
    __tablename__ = 'gift_campaign_pools'
    __table_args__ = (db.UniqueConstraint('campaign_id', 'bonus_product_id', name='uq_gift_campaign_pool'),)

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('gift_campaigns.id', ondelete='CASCADE'), nullable=False)
    bonus_product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='SET NULL'), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    bonus_product = db.relationship('Product', foreign_keys=[bonus_product_id])
    stock = db.relationship('GiftPoolStock', backref='pool', cascade='all, delete-orphan')

    @property
    def label(self):
        name = (self.bonus_product.name or '').strip() if self.bonus_product else ''
        return name or f'Gratis #{self.id}'


class GiftPoolStock(db.Model):
    """Ilość sztuk danego rodzaju karty w danej puli."""
    __tablename__ = 'gift_pool_stock'
    __table_args__ = (db.UniqueConstraint('pool_id', 'card_type_id', name='uq_gift_pool_stock'),)

    id = db.Column(db.Integer, primary_key=True)
    pool_id = db.Column(db.Integer, db.ForeignKey('gift_campaign_pools.id', ondelete='CASCADE'), nullable=False)
    card_type_id = db.Column(db.Integer, db.ForeignKey('gift_card_types.id', ondelete='CASCADE'), nullable=False)
    quantity = db.Column(db.Integer, nullable=True)  # wpisywane po dotarciu kart


class GiftCardType(db.Model):
    __tablename__ = 'gift_card_types'

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('gift_campaigns.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    image_path = db.Column(db.String(512), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    stock = db.relationship('GiftPoolStock', backref='card_type', cascade='all, delete-orphan')


class GiftParticipant(db.Model):
    __tablename__ = 'gift_participants'
    __table_args__ = (db.UniqueConstraint('campaign_id', 'user_id', name='uq_gift_participant'),)

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('gift_campaigns.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    ranking_json = db.Column(db.Text, nullable=True)  # lista id rodzajów, najlepszy pierwszy
    ranking_updated_at = db.Column(UTCDateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)  # uwagi klientki do akcji

    user = db.relationship('User', foreign_keys=[user_id])

    @property
    def ranking(self):
        if not self.ranking_json:
            return []
        return json.loads(self.ranking_json)


class GiftRaceEntry(db.Model):
    __tablename__ = 'gift_race_entries'
    __table_args__ = (db.UniqueConstraint('campaign_id', 'user_id', name='uq_gift_race_entry'),)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # = kolejność w kolejce
    campaign_id = db.Column(db.Integer, db.ForeignKey('gift_campaigns.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(UTCDateTime, default=utcnow, nullable=False)

    user = db.relationship('User', foreign_keys=[user_id])


class GiftAssignment(db.Model):
    __tablename__ = 'gift_assignments'

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('gift_campaigns.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_items.id', ondelete='CASCADE'), nullable=False)
    card_type_id = db.Column(db.Integer, db.ForeignKey('gift_card_types.id', ondelete='CASCADE'), nullable=False)
    pool_id = db.Column(db.Integer, db.ForeignKey('gift_campaign_pools.id', ondelete='CASCADE'), nullable=False)
    round_no = db.Column(db.Integer, nullable=False)
    rank_position = db.Column(db.Integer, nullable=True)
    is_duplicate = db.Column(db.Boolean, nullable=False, default=False)

    user = db.relationship('User', foreign_keys=[user_id])
    card_type = db.relationship('GiftCardType', foreign_keys=[card_type_id])
    pool = db.relationship('GiftCampaignPool', foreign_keys=[pool_id])
