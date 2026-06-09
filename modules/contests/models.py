from extensions import db
from modules.auth.models import get_local_now


class Contest(db.Model):
    __tablename__ = 'contests'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(512), nullable=True)
    prize_product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    num_winners = db.Column(db.Integer, nullable=False, default=1)
    ticket_min = db.Column(db.Integer, nullable=False, default=1)
    ticket_max = db.Column(db.Integer, nullable=False, default=50)
    cooldown_minutes = db.Column(db.Integer, nullable=False, default=1440)
    eligibility_min_orders = db.Column(db.Integer, nullable=True)
    eligibility_min_total_value = db.Column(db.Numeric(10, 2), nullable=True)
    eligibility_active_within_days = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='szkic')  # szkic|aktywny|rozlosowany
    starts_at = db.Column(db.DateTime, nullable=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now, nullable=False)
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    prize_product = db.relationship('Product', foreign_keys=[prize_product_id])
    prizes = db.relationship('ContestPrize', backref='contest', cascade='all, delete-orphan',
                             order_by='ContestPrize.id')

    @property
    def prize_summary(self):
        """Czytelny opis nagrody-zestawu, np. '2× Album, 1× Photocard'."""
        if self.prizes:
            return ', '.join(f'{p.quantity}× {p.product.name}' for p in self.prizes if p.product)
        if self.prize_product:
            return self.prize_product.name
        return None

    def __repr__(self):
        return f'<Contest {self.id}: {self.name} [{self.status}]>'


class ContestPrize(db.Model):
    __tablename__ = 'contest_prizes'

    id = db.Column(db.Integer, primary_key=True)
    contest_id = db.Column(db.Integer, db.ForeignKey('contests.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    product = db.relationship('Product', foreign_keys=[product_id])

    __table_args__ = (db.Index('ix_contest_prizes_contest', 'contest_id'),)

    def __repr__(self):
        return f'<ContestPrize contest={self.contest_id} product={self.product_id} x{self.quantity}>'


class ContestSpin(db.Model):
    __tablename__ = 'contest_spins'

    id = db.Column(db.Integer, primary_key=True)
    contest_id = db.Column(db.Integer, db.ForeignKey('contests.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tickets_won = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)

    __table_args__ = (db.Index('ix_contest_spins_contest_user', 'contest_id', 'user_id'),)

    def __repr__(self):
        return f'<ContestSpin contest={self.contest_id} user={self.user_id} +{self.tickets_won}>'


class ContestWinner(db.Model):
    __tablename__ = 'contest_winners'

    id = db.Column(db.Integer, primary_key=True)
    contest_id = db.Column(db.Integer, db.ForeignKey('contests.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    place = db.Column(db.Integer, nullable=False)
    tickets_at_draw = db.Column(db.Integer, nullable=False)
    chance_pct = db.Column(db.Numeric(6, 3), nullable=True)
    prize_product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    drawn_at = db.Column(db.DateTime, default=get_local_now, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('contest_id', 'user_id', name='uq_contest_winner_user'),
        db.UniqueConstraint('contest_id', 'place', name='uq_contest_winner_place'),
    )

    user = db.relationship('User', foreign_keys=[user_id])
    prize_product = db.relationship('Product', foreign_keys=[prize_product_id])

    def __repr__(self):
        return f'<ContestWinner contest={self.contest_id} user={self.user_id} place={self.place}>'
