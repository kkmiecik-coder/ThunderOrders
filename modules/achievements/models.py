from extensions import db
from modules.auth.models import get_local_now


class Achievement(db.Model):
    __tablename__ = 'achievement'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    category = db.Column(
        db.Enum('orders', 'collection', 'loyalty', 'speed', 'exclusive',
                'social', 'financial', 'profile', 'special',
                name='achievement_category'),
        nullable=False
    )
    rarity = db.Column(
        db.Enum('common', 'rare', 'epic', 'legendary', 'cosmic',
                name='achievement_rarity'),
        nullable=False
    )
    tier = db.Column(db.Integer, nullable=True)
    tier_group = db.Column(db.String(60), nullable=True, index=True)
    trigger_type = db.Column(
        db.Enum('event', 'cron', 'manual', name='achievement_trigger_type'),
        nullable=False
    )
    trigger_config = db.Column(db.JSON, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    is_hidden_until_unlocked = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=get_local_now)

    user_achievements = db.relationship('UserAchievement', back_populates='achievement', lazy='dynamic')
    stat = db.relationship('AchievementStat', back_populates='achievement', uselist=False)

    def __repr__(self):
        return f'<Achievement {self.slug}>'


class UserAchievement(db.Model):
    __tablename__ = 'user_achievement'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'achievement_id', name='uq_user_achievement'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id', ondelete='CASCADE'), nullable=False, index=True)
    unlocked_at = db.Column(db.DateTime, default=get_local_now)
    seen = db.Column(db.Boolean, default=False)
    shared = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_local_now)
    granted_by_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True
    )

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('achievements_unlocked', lazy='dynamic'))
    achievement = db.relationship('Achievement', back_populates='user_achievements')
    granted_by = db.relationship('User', foreign_keys=[granted_by_id])

    def __repr__(self):
        return f'<UserAchievement user={self.user_id} achievement={self.achievement_id}>'


class AchievementStat(db.Model):
    __tablename__ = 'achievement_stat'

    id = db.Column(db.Integer, primary_key=True)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id', ondelete='CASCADE'), unique=True, nullable=False)
    total_unlocked = db.Column(db.Integer, default=0)
    percentage = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    achievement = db.relationship('Achievement', back_populates='stat')
