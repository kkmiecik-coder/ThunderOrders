"""
Push Notification Models
- PushSubscription: stores browser push subscriptions per user/device
- NotificationPreference: per-user toggle for each notification category
- Notification: stored notification record for the notification center
"""

from datetime import datetime, timedelta, timezone
from extensions import db


def get_local_now():
    """
    Zwraca aktualny czas polski (Europe/Warsaw).
    Używa stałego offsetu +1h (CET) lub +2h (CEST) w zależności od daty.
    Zwraca naive datetime dla porównań z naive datetime w bazie.
    """
    utc_now = datetime.now(timezone.utc)
    year = utc_now.year

    march_last = datetime(year, 3, 31, tzinfo=timezone.utc)
    march_switch = march_last - timedelta(days=march_last.weekday() + 1 % 7)
    march_switch = march_switch.replace(hour=1, minute=0, second=0, microsecond=0)
    if march_last.weekday() == 6:
        march_switch = march_last.replace(hour=1, minute=0, second=0, microsecond=0)

    october_last = datetime(year, 10, 31, tzinfo=timezone.utc)
    october_switch = october_last - timedelta(days=october_last.weekday() + 1 % 7)
    october_switch = october_switch.replace(hour=1, minute=0, second=0, microsecond=0)
    if october_last.weekday() == 6:
        october_switch = october_last.replace(hour=1, minute=0, second=0, microsecond=0)

    if march_switch <= utc_now < october_switch:
        offset = timedelta(hours=2)
    else:
        offset = timedelta(hours=1)

    return (utc_now + offset).replace(tzinfo=None)


class Notification(db.Model):
    """Stored notification for the in-app notification center."""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=True)
    url = db.Column(db.String(512), nullable=True)
    notification_type = db.Column(db.String(50), nullable=True)
    tag = db.Column(db.String(100), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False, index=True)

    user = db.relationship('User', backref=db.backref('notifications', lazy='dynamic'))

    def __repr__(self):
        return f'<Notification {self.id} user={self.user_id} read={self.is_read}>'

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'body': self.body,
            'url': self.url,
            'notification_type': self.notification_type,
            'tag': self.tag,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


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
