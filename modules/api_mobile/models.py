"""Model blocklisty refresh tokenów dla mobilnego API (realny logout / unieważnianie)."""

from extensions import db
from modules.orders.models import get_local_now


class MobileTokenBlocklist(db.Model):
    __tablename__ = 'mobile_token_blocklist'

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, index=True, unique=True)
    token_type = db.Column(db.String(16), nullable=False)  # 'access' | 'refresh'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=get_local_now)

    @classmethod
    def contains(cls, jti):
        return db.session.query(cls.id).filter_by(jti=jti).first() is not None
