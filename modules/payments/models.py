from extensions import db
from datetime import datetime

class PaymentMethod(db.Model):
    __tablename__ = 'payment_methods'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get_active(cls):
        """Zwraca aktywne metody płatności posortowane"""
        return cls.query.filter_by(is_active=True).order_by(cls.sort_order, cls.name).all()

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'details': self.details,
            'is_active': self.is_active,
            'sort_order': self.sort_order
        }
