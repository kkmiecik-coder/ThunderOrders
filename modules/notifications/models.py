"""
Push Notification Models
- PushSubscription: stores browser push subscriptions per user/device
- NotificationPreference: per-user toggle for each notification category
"""

from datetime import datetime
from extensions import db


class PushSubscription(db.Model):
    __tablename__ = 'push_subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False)
    p256dh_key = db.Column(db.String(255), nullable=False)
    auth_key = db.Column(db.String(255), nullable=False)
    device_name = db.Column(db.String(255), default='')
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    failed_count = db.Column(db.Integer, default=0, nullable=False)
    last_used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref=db.backref('push_subscriptions', lazy='dynamic'))

    def __repr__(self):
        return f'<PushSubscription {self.id} user={self.user_id}>'


class NotificationPreference(db.Model):
    __tablename__ = 'notification_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)

    # Category toggles (all default True)
    order_status_changes = db.Column(db.Boolean, default=True, nullable=False)
    payment_updates = db.Column(db.Boolean, default=True, nullable=False)
    shipping_updates = db.Column(db.Boolean, default=True, nullable=False)
    new_exclusive_pages = db.Column(db.Boolean, default=True, nullable=False)
    cost_added = db.Column(db.Boolean, default=True, nullable=False)
    admin_alerts = db.Column(db.Boolean, default=True, nullable=False)

    user = db.relationship('User', backref=db.backref('notification_preference', uselist=False))

    def __repr__(self):
        return f'<NotificationPreference user={self.user_id}>'

    def to_dict(self):
        return {
            'order_status_changes': self.order_status_changes,
            'payment_updates': self.payment_updates,
            'shipping_updates': self.shipping_updates,
            'new_exclusive_pages': self.new_exclusive_pages,
            'cost_added': self.cost_added,
            'admin_alerts': self.admin_alerts,
        }
