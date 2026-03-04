"""
AdminBroadcast Model
Stores admin-sent broadcast notifications with targeting and read statistics.
"""

from extensions import db
from modules.notifications.models import get_local_now, Notification


class AdminBroadcast(db.Model):
    __tablename__ = 'admin_broadcasts'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=True)
    url = db.Column(db.String(512), nullable=True)
    target_type = db.Column(db.String(20), nullable=False)  # 'all', 'roles', 'users'
    target_data = db.Column(db.Text, nullable=True)  # JSON: roles list or user IDs list
    sent_count = db.Column(db.Integer, default=0, nullable=False)
    sent_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False, index=True)

    sender = db.relationship('User', backref=db.backref('sent_broadcasts', lazy='dynamic'))

    @property
    def tag(self):
        return f'broadcast-{self.id}'

    @property
    def target_display(self):
        """Human-readable target description."""
        import json
        if self.target_type == 'all':
            return 'Wszyscy'
        elif self.target_type == 'roles':
            try:
                roles = json.loads(self.target_data) if self.target_data else []
                role_names = {'admin': 'Admin', 'mod': 'Moderator', 'client': 'Klient'}
                return ', '.join(role_names.get(r, r) for r in roles)
            except (json.JSONDecodeError, TypeError):
                return 'Role'
        elif self.target_type == 'users':
            try:
                user_ids = json.loads(self.target_data) if self.target_data else []
                return f'{len(user_ids)} wybranych'
            except (json.JSONDecodeError, TypeError):
                return 'Wybrani'
        return '—'

    @property
    def read_count(self):
        """Live count of read notifications for this broadcast."""
        return Notification.query.filter_by(tag=self.tag, is_read=True).count()

    def __repr__(self):
        return f'<AdminBroadcast {self.id} "{self.title}">'
