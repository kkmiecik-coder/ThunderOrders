from extensions import db
from utils.timeutil import UTCDateTime, utcnow


class QRCampaign(db.Model):
    __tablename__ = 'qr_campaigns'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    target_url = db.Column(db.String(500), nullable=False, default='https://thunderorders.cloud')
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(UTCDateTime, default=utcnow)
    updated_at = db.Column(UTCDateTime, default=utcnow, onupdate=utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    creator = db.relationship('User', backref='qr_campaigns', foreign_keys=[created_by])
    visits = db.relationship(
        'QRVisit',
        back_populates='campaign',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<QRCampaign {self.name}>'

    @property
    def total_visits(self):
        return self.visits.count()

    @property
    def unique_visits(self):
        return self.visits.filter_by(is_unique=True).count()

    @property
    def last_visit(self):
        visit = self.visits.order_by(QRVisit.visited_at.desc()).first()
        return visit.visited_at if visit else None

    @property
    def full_url(self):
        return f'/qr/{self.slug}'


class QRVisit(db.Model):
    __tablename__ = 'qr_visits'

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('qr_campaigns.id'), nullable=False, index=True)
    visitor_id = db.Column(db.String(64), nullable=False)
    is_unique = db.Column(db.Boolean, nullable=False, default=True)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    device_type = db.Column(db.String(20))
    browser = db.Column(db.String(50))
    os = db.Column(db.String(50))
    country = db.Column(db.String(100))
    city = db.Column(db.String(100))
    referer = db.Column(db.String(500))
    visited_at = db.Column(UTCDateTime, default=utcnow, nullable=False, index=True)

    campaign = db.relationship('QRCampaign', back_populates='visits')

    __table_args__ = (
        db.Index('ix_qr_visits_visitor_campaign', 'visitor_id', 'campaign_id'),
    )

    def __repr__(self):
        return f'<QRVisit campaign={self.campaign_id} visitor={self.visitor_id[:8]}>'
