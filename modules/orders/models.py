"""
Orders Module - Database Models
================================

Models for orders management:
- OrderStatus: Lookup table for order statuses
- OrderType: Lookup table for order types (Pre-order, On-hand, Exclusive)
- Order: Main order model
- OrderItem: Order line items (products in order)
- OrderComment: Comments/messages for orders (admin <-> client communication)
- OrderRefund: Refund records for orders
"""

from datetime import datetime
from extensions import db


# ====================
# LOOKUP TABLES
# ====================

class OrderStatus(db.Model):
    """
    Order status lookup table.
    Allows admin to manage statuses through UI without code changes.
    """
    __tablename__ = 'order_statuses'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    badge_color = db.Column(db.String(7), default='#6B7280')  # HEX color for badge
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    orders = db.relationship('Order', back_populates='status_rel', foreign_keys='Order.status')

    def __repr__(self):
        return f'<OrderStatus {self.slug}>'

    @property
    def display_name(self):
        """Returns formatted name for display"""
        return self.name


class OrderType(db.Model):
    """
    Order type lookup table.
    Types: Pre-order (PO), On-hand (OH), Exclusive (EX)
    """
    __tablename__ = 'order_types'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    prefix = db.Column(db.String(5), nullable=False)  # PO, OH, EX for order numbers
    badge_color = db.Column(db.String(7), default='#6B7280')  # HEX color for type badge
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    orders = db.relationship('Order', back_populates='type_rel', foreign_keys='Order.order_type')

    def __repr__(self):
        return f'<OrderType {self.slug}>'

    @property
    def display_name(self):
        """Returns formatted name for display"""
        return self.name


class WmsStatus(db.Model):
    """
    WMS (Warehouse Management System) status lookup table.
    Configurable statuses for order item picking/packing workflow.
    """
    __tablename__ = 'wms_statuses'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    badge_color = db.Column(db.String(7), default='#6B7280')  # HEX color for badge
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    is_default = db.Column(db.Boolean, default=False)  # Default status for new items
    is_picked = db.Column(db.Boolean, default=False)  # Marks item as picked (for progress calculation)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    order_items = db.relationship('OrderItem', back_populates='wms_status_rel', foreign_keys='OrderItem.wms_status')

    def __repr__(self):
        return f'<WmsStatus {self.slug}>'

    @property
    def display_name(self):
        """Returns formatted name for display"""
        return self.name


# ====================
# MAIN MODELS
# ====================

class Order(db.Model):
    """
    Main order model.
    Supports both registered users and guest orders.
    """
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)  # Format: PO/00000001
    order_type = db.Column(db.String(50), db.ForeignKey('order_types.slug'), default='on_hand')

    # User relationship (NULL for guest orders)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    user = db.relationship('User', back_populates='orders')

    # Status (foreign key to order_statuses)
    status = db.Column(db.String(50), db.ForeignKey('order_statuses.slug'), default='nowe')
    status_rel = db.relationship('OrderStatus', back_populates='orders', foreign_keys=[status])
    type_rel = db.relationship('OrderType', back_populates='orders', foreign_keys=[order_type])

    # Financial
    total_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    paid_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)  # Amount paid by customer
    shipping_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)  # Koszt wysyłki

    # Delivery and payment
    delivery_method = db.Column(db.String(50), nullable=True)  # kurier, paczkomat, odbior_osobisty
    payment_method = db.Column(db.String(50), nullable=True)  # przelew, pobranie, gotowka, blik

    # Exclusive order fields
    is_exclusive = db.Column(db.Boolean, default=False)
    exclusive_page_id = db.Column(db.Integer, db.ForeignKey('exclusive_pages.id'), nullable=True)
    exclusive_page = db.relationship('ExclusivePage', back_populates='orders')

    # Guest order fields
    is_guest_order = db.Column(db.Boolean, default=False)
    guest_email = db.Column(db.String(255), nullable=True)
    guest_name = db.Column(db.String(200), nullable=True)
    guest_phone = db.Column(db.String(20), nullable=True)

    # Shipping request
    shipping_requested = db.Column(db.Boolean, default=False)
    shipping_requested_at = db.Column(db.DateTime, nullable=True)

    # Tracking
    tracking_number = db.Column(db.String(100), nullable=True)
    courier = db.Column(db.String(50), nullable=True)

    # Shipping Address (Adres dostawy)
    shipping_name = db.Column(db.String(200), nullable=True)  # Imię i nazwisko
    shipping_address = db.Column(db.String(500), nullable=True)  # Adres (ulica, numer)
    shipping_postal_code = db.Column(db.String(10), nullable=True)  # Kod pocztowy
    shipping_city = db.Column(db.String(100), nullable=True)  # Miejscowość
    shipping_voivodeship = db.Column(db.String(50), nullable=True)  # Województwo
    shipping_country = db.Column(db.String(100), nullable=True, default='Polska')  # Kraj

    # Pickup Point (Odbiór w punkcie)
    pickup_courier = db.Column(db.String(100), nullable=True)  # Nazwa kuriera (InPost, DPD, etc.)
    pickup_point_id = db.Column(db.String(50), nullable=True)  # ID punktu (np. WAW123)
    pickup_address = db.Column(db.String(500), nullable=True)  # Adres punktu
    pickup_postal_code = db.Column(db.String(10), nullable=True)  # Kod pocztowy punktu
    pickup_city = db.Column(db.String(100), nullable=True)  # Miasto punktu

    # Notes
    notes = db.Column(db.Text, nullable=True)  # Client notes
    admin_notes = db.Column(db.Text, nullable=True)  # Internal admin notes

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    items = db.relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')
    comments = db.relationship('OrderComment', back_populates='order', cascade='all, delete-orphan', order_by='OrderComment.created_at.desc()')
    refunds = db.relationship('OrderRefund', back_populates='order', cascade='all, delete-orphan')
    shipments = db.relationship('OrderShipment', back_populates='order', cascade='all, delete-orphan', order_by='OrderShipment.created_at.desc()')

    def __repr__(self):
        return f'<Order {self.order_number}>'

    @property
    def customer_name(self):
        """Returns customer name (user or guest)"""
        if self.is_guest_order:
            return self.guest_name
        elif self.user:
            return self.user.full_name
        return 'Unknown'

    @property
    def customer_email(self):
        """Returns customer email (user or guest)"""
        if self.is_guest_order:
            return self.guest_email
        elif self.user:
            return self.user.email
        return None

    @property
    def status_badge_color(self):
        """Returns HEX color for status badge"""
        if self.status_rel:
            return self.status_rel.badge_color
        return '#6B7280'  # Default gray

    @property
    def status_display_name(self):
        """Returns formatted status name"""
        if self.status_rel:
            return self.status_rel.name
        return self.status

    @property
    def type_badge_color(self):
        """Returns HEX color for type badge"""
        if self.type_rel:
            return self.type_rel.badge_color
        return '#6B7280'  # Default gray

    @property
    def type_display_name(self):
        """Returns formatted type name"""
        if self.type_rel:
            return self.type_rel.name
        return self.order_type

    @property
    def tracking_url(self):
        """Returns tracking URL based on courier"""
        if not self.tracking_number or not self.courier:
            return None

        # Import here to avoid circular dependency
        from modules.orders.utils import get_tracking_url
        return get_tracking_url(self.courier, self.tracking_number)

    @property
    def items_count(self):
        """Returns total number of items in order"""
        return sum(item.quantity for item in self.items)

    @property
    def is_picked(self):
        """Returns True if all items are picked (WMS)"""
        if not self.items:
            return False
        return all(item.is_picked for item in self.items)

    @property
    def picked_percentage(self):
        """Returns percentage of picked items (for WMS progress bar)"""
        if not self.items:
            return 0
        total = len(self.items)
        picked = sum(1 for item in self.items if item.is_picked)
        return int((picked / total) * 100)

    @property
    def grand_total(self):
        """Returns total amount including shipping cost (produkty + wysyłka)"""
        from decimal import Decimal
        products = Decimal(str(self.total_amount)) if self.total_amount else Decimal('0.00')
        shipping = Decimal(str(self.shipping_cost)) if self.shipping_cost else Decimal('0.00')
        return products + shipping

    @property
    def is_fully_paid(self):
        """Returns True if order is fully paid exactly (products + shipping)"""
        from decimal import Decimal
        paid = Decimal(str(self.paid_amount)) if self.paid_amount else Decimal('0.00')
        return paid == self.grand_total and self.grand_total > Decimal('0.00')

    @property
    def is_overpaid(self):
        """Returns True if order is overpaid (nadpłata)"""
        from decimal import Decimal
        paid = Decimal(str(self.paid_amount)) if self.paid_amount else Decimal('0.00')
        return paid > self.grand_total and self.grand_total > Decimal('0.00')

    @property
    def is_partially_paid(self):
        """Returns True if order is partially paid (some payment, but not full)"""
        from decimal import Decimal
        paid = Decimal(str(self.paid_amount)) if self.paid_amount else Decimal('0.00')
        return paid > Decimal('0.00') and paid < self.grand_total

    @property
    def remaining_amount(self):
        """Returns remaining amount to be paid"""
        from decimal import Decimal
        paid = Decimal(str(self.paid_amount)) if self.paid_amount else Decimal('0.00')
        remaining = self.grand_total - paid
        return remaining if remaining > Decimal('0.00') else Decimal('0.00')

    @property
    def delivery_method_display(self):
        """Returns human-readable delivery method name"""
        methods = {
            'kurier': 'Kurier',
            'paczkomat': 'Paczkomat',
            'odbior_osobisty': 'Odbiór osobisty',
            'poczta': 'Poczta Polska',
            'dpd_pickup': 'DPD Pickup',
            'orlen_paczka': 'Orlen Paczka'
        }
        return methods.get(self.delivery_method, self.delivery_method) if self.delivery_method else '-'

    @property
    def payment_method_display(self):
        """Returns human-readable payment method name"""
        methods = {
            'przelew': 'Przelew bankowy',
            'pobranie': 'Pobranie',
            'gotowka': 'Gotówka',
            'blik': 'BLIK',
            'karta': 'Karta płatnicza',
            'paypal': 'PayPal'
        }
        return methods.get(self.payment_method, self.payment_method) if self.payment_method else '-'

    def recalculate_total(self):
        """Recalculates order total from items"""
        from decimal import Decimal
        total = Decimal('0.00')
        for item in self.items:
            if item.total:
                total += Decimal(str(item.total))
        self.total_amount = total


class OrderItem(db.Model):
    """
    Order line items - products in order.
    Includes WMS (Warehouse Management System) fields for picking.
    """
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)

    # Order details
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price = db.Column(db.Numeric(10, 2), nullable=False)  # Price at time of order
    total = db.Column(db.Numeric(10, 2), nullable=False)  # price * quantity

    # WMS fields
    wms_status = db.Column(db.String(50), db.ForeignKey('wms_statuses.slug'), nullable=True)
    picked = db.Column(db.Boolean, default=False)  # Legacy field, kept for compatibility
    picked_at = db.Column(db.DateTime, nullable=True)
    picked_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    order = db.relationship('Order', back_populates='items')
    product = db.relationship('Product', back_populates='order_items')
    picker = db.relationship('User', foreign_keys=[picked_by])
    wms_status_rel = db.relationship('WmsStatus', back_populates='order_items', foreign_keys=[wms_status])

    def __repr__(self):
        return f'<OrderItem {self.id} - Order {self.order_id}>'

    @property
    def product_name(self):
        """Returns product name"""
        return self.product.name if self.product else 'Unknown Product'

    @property
    def product_sku(self):
        """Returns product SKU"""
        return self.product.sku if self.product else None

    @property
    def product_ean(self):
        """Returns product EAN"""
        return self.product.ean if self.product else None

    @property
    def product_image_url(self):
        """Returns primary product image URL"""
        if self.product and self.product.primary_image:
            path = self.product.primary_image.path_compressed
            # Ensure path starts with /static/
            if path and not path.startswith('/static/'):
                return f'/static/{path}'
            return path
        return '/static/img/placeholders/product.svg'

    @property
    def wms_status_name(self):
        """Returns WMS status display name"""
        if self.wms_status_rel:
            return self.wms_status_rel.name
        return 'Do zebrania'

    @property
    def wms_status_color(self):
        """Returns WMS status badge color"""
        if self.wms_status_rel:
            return self.wms_status_rel.badge_color
        return '#FF9800'  # Default orange for pending

    @property
    def is_picked(self):
        """Returns True if item is picked (based on WMS status or legacy field)"""
        if self.wms_status_rel:
            return self.wms_status_rel.is_picked
        return self.picked


class OrderComment(db.Model):
    """
    Comments/messages for orders.
    Supports admin <-> client communication.
    Internal notes are visible only to admin/mod.
    """
    __tablename__ = 'order_comments'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    comment = db.Column(db.Text, nullable=False)
    is_internal = db.Column(db.Boolean, default=False)  # Internal notes (admin only)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    order = db.relationship('Order', back_populates='comments')
    user = db.relationship('User', back_populates='order_comments')

    def __repr__(self):
        return f'<OrderComment {self.id} - Order {self.order_id}>'

    @property
    def author_name(self):
        """Returns comment author name"""
        if self.user:
            return self.user.full_name
        return 'System'

    @property
    def author_initials(self):
        """Returns author initials for avatar"""
        if self.user:
            return self.user.initials
        return 'SY'

    @property
    def is_from_admin(self):
        """Returns True if comment is from admin/mod"""
        if self.user:
            return self.user.role in ['admin', 'mod']
        return False


class OrderRefund(db.Model):
    """
    Refund records for orders.
    Tracks partial and full refunds.
    """
    __tablename__ = 'order_refunds'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)

    amount = db.Column(db.Numeric(10, 2), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, completed, cancelled

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    order = db.relationship('Order', back_populates='refunds')
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<OrderRefund {self.id} - {self.amount} PLN>'

    @property
    def creator_name(self):
        """Returns name of user who created refund"""
        return self.creator.full_name if self.creator else 'Unknown'

    @property
    def is_completed(self):
        """Returns True if refund is completed"""
        return self.status == 'completed'

    @property
    def is_pending(self):
        """Returns True if refund is pending"""
        return self.status == 'pending'


class OrderShipment(db.Model):
    """
    Shipment records for orders.
    Allows multiple shipments per order (e.g., split shipments).
    """
    __tablename__ = 'order_shipments'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)

    tracking_number = db.Column(db.String(100), nullable=False)
    courier = db.Column(db.String(50), nullable=False)  # inpost, dpd, dhl, gls, poczta_polska, orlen, ups, fedex, other

    # Optional notes
    notes = db.Column(db.String(255), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relationships
    order = db.relationship('Order', back_populates='shipments')
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<OrderShipment {self.id} - {self.tracking_number}>'

    @property
    def tracking_url(self):
        """Returns tracking URL based on courier"""
        from modules.orders.utils import get_tracking_url
        return get_tracking_url(self.courier, self.tracking_number)

    @property
    def courier_display_name(self):
        """Returns human-readable courier name"""
        courier_names = {
            'inpost': 'InPost',
            'dpd': 'DPD',
            'dhl': 'DHL',
            'gls': 'GLS',
            'poczta_polska': 'Poczta Polska',
            'orlen': 'Orlen Paczka',
            'ups': 'UPS',
            'fedex': 'FedEx',
            'other': 'Inny'
        }
        return courier_names.get(self.courier, self.courier)

    @property
    def courier_icon(self):
        """Returns courier icon class or SVG identifier"""
        # Can be extended to return actual icons
        return self.courier
