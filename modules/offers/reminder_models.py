"""
Modele konfiguracji i logowania przypomnień o płatnościach.
"""
from extensions import db
from modules.offers.models import get_local_now


class PaymentReminderConfig(db.Model):
    """Globalna konfiguracja reguł przypomnień o płatnościach."""
    __tablename__ = 'payment_reminder_configs'

    id = db.Column(db.Integer, primary_key=True)
    reminder_type = db.Column(db.String(30), nullable=False)  # 'before_deadline' | 'after_order_placed'
    hours = db.Column(db.Integer, nullable=False)
    payment_stage = db.Column(db.String(30), nullable=False, default='product')
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=get_local_now)

    logs = db.relationship('PaymentReminderLog', back_populates='config', lazy='dynamic')

    def __repr__(self):
        return f'<PaymentReminderConfig {self.reminder_type} {self.hours}h>'


class PaymentReminderLog(db.Model):
    """Log wysłanych przypomnień — zapobiega duplikacji."""
    __tablename__ = 'payment_reminder_logs'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    config_id = db.Column(db.Integer, db.ForeignKey('payment_reminder_configs.id'), nullable=True)
    reminder_type = db.Column(db.String(30), nullable=True)  # 'deadline_exceeded' gdy config_id=NULL
    sent_at = db.Column(db.DateTime, default=get_local_now, nullable=False)

    config = db.relationship('PaymentReminderConfig', back_populates='logs')
    order = db.relationship('Order', backref=db.backref('reminder_logs', lazy='dynamic'))

    def __repr__(self):
        return f'<PaymentReminderLog order={self.order_id} config={self.config_id}>'
