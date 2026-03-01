"""
WMS (Warehouse Management System) Models
==========================================

Models for WMS session management:
- WmsSession: Main WMS picking/packing session
- WmsSessionOrder: Junction table linking sessions to orders
- WmsSessionShippingRequest: Junction table linking sessions to shipping requests
"""

from extensions import db
from modules.orders.models import get_local_now


# ====================
# WMS SESSION
# ====================


class WmsSession(db.Model):
    """
    WMS picking/packing session.
    Groups orders for warehouse processing (picking + packing).
    """
    __tablename__ = 'wms_sessions'

    id = db.Column(db.Integer, primary_key=True)
    session_token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='active')  # active, paused, completed, cancelled
    phone_connected = db.Column(db.Boolean, default=False)
    phone_connected_at = db.Column(db.DateTime, nullable=True)
    desktop_connected_at = db.Column(db.DateTime, nullable=True)
    current_order_index = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id])
    session_orders = db.relationship(
        'WmsSessionOrder', back_populates='session',
        cascade='all, delete-orphan', order_by='WmsSessionOrder.sort_order'
    )
    session_shipping_requests = db.relationship(
        'WmsSessionShippingRequest', back_populates='session',
        cascade='all, delete-orphan'
    )
    locked_orders = db.relationship('Order', foreign_keys='Order.wms_session_id', backref='wms_session')

    def __repr__(self):
        return f'<WmsSession {self.id} ({self.status})>'

    @property
    def is_active(self):
        """Returns True if session is active"""
        return self.status == 'active'

    @property
    def orders_count(self):
        """Returns total number of orders in session"""
        return len(self.session_orders)

    @property
    def picked_orders_count(self):
        """Returns number of fully picked orders"""
        count = 0
        for so in self.session_orders:
            if so.order and so.order.is_picked:
                count += 1
        return count

    @property
    def packed_orders_count(self):
        """Returns number of packed orders"""
        count = 0
        for so in self.session_orders:
            if so.packing_completed_at is not None:
                count += 1
        return count

    @property
    def progress_percentage(self):
        """Returns overall session progress (0-100)"""
        total = self.orders_count
        if total == 0:
            return 0
        packed = self.packed_orders_count
        return int((packed / total) * 100)


# ====================
# SESSION JUNCTION TABLES
# ====================


class WmsSessionOrder(db.Model):
    """
    Junction table linking WMS sessions to orders.
    Tracks picking/packing progress per order within a session.
    """
    __tablename__ = 'wms_session_orders'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('wms_sessions.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    picking_started_at = db.Column(db.DateTime, nullable=True)
    picking_completed_at = db.Column(db.DateTime, nullable=True)
    packing_completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    session = db.relationship('WmsSession', back_populates='session_orders')
    order = db.relationship('Order')

    def __repr__(self):
        return f'<WmsSessionOrder S:{self.session_id} O:{self.order_id}>'


class WmsSessionShippingRequest(db.Model):
    """
    Junction table linking WMS sessions to shipping requests.
    Tracks which shipping requests entered the session (for SR status updates after packing).
    """
    __tablename__ = 'wms_session_shipping_requests'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('wms_sessions.id'), nullable=False)
    shipping_request_id = db.Column(db.Integer, db.ForeignKey('shipping_requests.id'), nullable=False)

    # Relationships
    session = db.relationship('WmsSession', back_populates='session_shipping_requests')
    shipping_request = db.relationship('ShippingRequest')

    def __repr__(self):
        return f'<WmsSessionShippingRequest S:{self.session_id} SR:{self.shipping_request_id}>'


# ====================
# PACKAGING MATERIALS
# ====================


class PackagingMaterial(db.Model):
    """
    Packaging material for WMS packing workflow.
    Represents a physical packaging type (box, envelope, bubble mailer, etc.)
    with dimensions, weight limits, and stock tracking.
    """
    __tablename__ = 'packaging_materials'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g. "Karton 30x20x15"
    type = db.Column(db.String(30), nullable=False, default='karton')  # karton, koperta_babelkowa, koperta, foliopak, inne
    inner_length = db.Column(db.Numeric(8, 2), nullable=True)  # inner dimensions in cm
    inner_width = db.Column(db.Numeric(8, 2), nullable=True)
    inner_height = db.Column(db.Numeric(8, 2), nullable=True)
    max_weight = db.Column(db.Numeric(8, 2), nullable=True)  # max content weight in kg
    own_weight = db.Column(db.Numeric(8, 2), nullable=True)  # packaging weight in kg
    quantity_in_stock = db.Column(db.Integer, default=0)
    low_stock_threshold = db.Column(db.Integer, default=5)  # alert threshold
    cost = db.Column(db.Numeric(8, 2), nullable=True)  # unit cost
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    def __repr__(self):
        return f'<PackagingMaterial {self.id}: {self.name}>'

    @property
    def dimensions_display(self):
        """Returns formatted dimensions string like '30×20×15 cm'"""
        if self.inner_length and self.inner_width and self.inner_height:
            return f'{self.inner_length:.0f}×{self.inner_width:.0f}×{self.inner_height:.0f} cm'
        return None

    @property
    def inner_volume(self):
        """Returns inner volume in cm³"""
        if self.inner_length and self.inner_width and self.inner_height:
            return float(self.inner_length) * float(self.inner_width) * float(self.inner_height)
        return None

    @property
    def is_low_stock(self):
        """Returns True if quantity is at or below threshold"""
        return self.quantity_in_stock <= self.low_stock_threshold

    TYPE_CHOICES = {
        'karton': 'Karton',
        'koperta_babelkowa': 'Koperta bąbelkowa',
        'koperta': 'Koperta',
        'foliopak': 'Foliopak',
        'inne': 'Inne',
    }

    @property
    def type_display(self):
        """Returns human-readable type name"""
        return self.TYPE_CHOICES.get(self.type, self.type)
