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
- ShippingRequestStatus: Lookup table for shipping request statuses
- ShippingRequest: Shipping request model (groups orders for shipment)
- ShippingRequestOrder: Junction table between ShippingRequest and Order
"""

from datetime import datetime, timezone, timedelta
import secrets
from extensions import db


# ====================
# LOOKUP TABLES
# ====================



def get_local_now():
    """
    Zwraca aktualny czas polski (Europe/Warsaw).
    Używa stałego offsetu +1h (CET) lub +2h (CEST) w zależności od daty.
    Zwraca naive datetime dla porównań z naive datetime w bazie.
    """
    utc_now = datetime.now(timezone.utc)

    # Prosty algorytm DST dla Polski:
    # CEST (UTC+2): ostatnia niedziela marca do ostatniej niedzieli października
    # CET (UTC+1): reszta roku
    year = utc_now.year

    # Ostatnia niedziela marca
    march_last = datetime(year, 3, 31, tzinfo=timezone.utc)
    march_last_sunday = march_last - timedelta(days=(march_last.weekday() + 1) % 7)
    dst_start = march_last_sunday.replace(hour=1)  # 01:00 UTC

    # Ostatnia niedziela października
    oct_last = datetime(year, 10, 31, tzinfo=timezone.utc)
    oct_last_sunday = oct_last - timedelta(days=(oct_last.weekday() + 1) % 7)
    dst_end = oct_last_sunday.replace(hour=1)  # 01:00 UTC

    # Sprawdź czy jesteśmy w czasie letnim
    if dst_start <= utc_now < dst_end:
        offset = timedelta(hours=2)  # CEST
    else:
        offset = timedelta(hours=1)  # CET

    # Zwróć naive datetime w czasie polskim
    return (utc_now + offset).replace(tzinfo=None)

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
    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

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
    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

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
    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

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

    # Dual Payment Proof System (order + shipping)
    payment_proof_order_file = db.Column(db.String(255), nullable=True)  # Dowód za zamówienie (produkty)
    payment_proof_order_uploaded_at = db.Column(db.DateTime, nullable=True)
    payment_proof_order_status = db.Column(db.String(20), nullable=True)  # pending, approved, rejected
    payment_proof_order_rejection_reason = db.Column(db.Text, nullable=True)

    payment_proof_shipping_file = db.Column(db.String(255), nullable=True)  # Dowód za wysyłkę
    payment_proof_shipping_uploaded_at = db.Column(db.DateTime, nullable=True)
    payment_proof_shipping_status = db.Column(db.String(20), nullable=True)  # pending, approved, rejected
    payment_proof_shipping_rejection_reason = db.Column(db.Text, nullable=True)

    # Exclusive order fields
    is_exclusive = db.Column(db.Boolean, default=False)
    exclusive_page_id = db.Column(db.Integer, db.ForeignKey('exclusive_pages.id', ondelete='SET NULL'), nullable=True)
    exclusive_page = db.relationship('ExclusivePage', back_populates='orders')
    exclusive_page_name = db.Column(db.String(200), nullable=True)  # Preserved page name for history

    # Guest order fields
    is_guest_order = db.Column(db.Boolean, default=False)
    guest_email = db.Column(db.String(255), nullable=True)
    guest_name = db.Column(db.String(200), nullable=True)
    guest_phone = db.Column(db.String(20), nullable=True)
    guest_view_token = db.Column(db.String(64), nullable=True, unique=True, index=True)  # Token for guest order tracking

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
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

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
        """Returns formatted type name. For exclusive orders, includes page name."""
        if self.is_exclusive:
            if self.exclusive_page:
                return f"Exclusive - {self.exclusive_page.name}"
            elif self.exclusive_page_name:
                return f"Exclusive - {self.exclusive_page_name}"
            return "Exclusive"
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
            'paczkomat': 'InPost',
            'odbior_osobisty': 'Odbiór osobisty',
            'poczta': 'Poczta Polska',
            'dpd_pickup': 'DPD Pickup',
            'orlen_paczka': 'Orlen Paczka'
        }
        return methods.get(self.delivery_method, self.delivery_method) if self.delivery_method else '-'

    @property
    def payment_method_display(self):
        """Returns payment method name (from database or saved value)"""
        # Jeśli nie ma metody płatności zapisanej, zwróć '-'
        if not self.payment_method:
            return '-'

        # Zwróć zapisaną nazwę metody płatności
        # (nawet jeśli metoda została później usunięta z ustawień)
        return self.payment_method

    @property
    def shipping_country_flag(self):
        """Returns emoji flag for shipping country"""
        # Map of country names to emoji flags
        country_flags = {
            'polska': '🇵🇱',
            'poland': '🇵🇱',
            'niemcy': '🇩🇪',
            'germany': '🇩🇪',
            'francja': '🇫🇷',
            'france': '🇫🇷',
            'wielka brytania': '🇬🇧',
            'uk': '🇬🇧',
            'united kingdom': '🇬🇧',
            'anglia': '🇬🇧',
            'stany zjednoczone': '🇺🇸',
            'usa': '🇺🇸',
            'united states': '🇺🇸',
            'czechy': '🇨🇿',
            'czech republic': '🇨🇿',
            'słowacja': '🇸🇰',
            'slovakia': '🇸🇰',
            'austria': '🇦🇹',
            'holandia': '🇳🇱',
            'netherlands': '🇳🇱',
            'belgia': '🇧🇪',
            'belgium': '🇧🇪',
            'włochy': '🇮🇹',
            'italy': '🇮🇹',
            'hiszpania': '🇪🇸',
            'spain': '🇪🇸',
            'szwecja': '🇸🇪',
            'sweden': '🇸🇪',
            'norwegia': '🇳🇴',
            'norway': '🇳🇴',
            'dania': '🇩🇰',
            'denmark': '🇩🇰',
            'finlandia': '🇫🇮',
            'finland': '🇫🇮',
            'ukraina': '🇺🇦',
            'ukraine': '🇺🇦',
            'litwa': '🇱🇹',
            'lithuania': '🇱🇹',
            'łotwa': '🇱🇻',
            'latvia': '🇱🇻',
            'estonia': '🇪🇪',
            'węgry': '🇭🇺',
            'hungary': '🇭🇺',
            'rumunia': '🇷🇴',
            'romania': '🇷🇴',
            'bułgaria': '🇧🇬',
            'bulgaria': '🇧🇬',
            'grecja': '🇬🇷',
            'greece': '🇬🇷',
            'portugalia': '🇵🇹',
            'portugal': '🇵🇹',
            'irlandia': '🇮🇪',
            'ireland': '🇮🇪',
            'szwajcaria': '🇨🇭',
            'switzerland': '🇨🇭',
        }

        if not self.shipping_country:
            return '🇵🇱'  # Default to Poland

        country_lower = self.shipping_country.lower().strip()
        return country_flags.get(country_lower, '🏳️')

    @property
    def order_source_display(self):
        """Returns order source for display (Exclusive page name or order type)"""
        if self.is_exclusive:
            if self.exclusive_page:
                return f"Exclusive: {self.exclusive_page.name}"
            elif self.exclusive_page_name:
                return f"Exclusive: {self.exclusive_page_name} (usunięta)"
            return "Exclusive"
        if self.type_rel:
            return self.type_rel.name
        return self.order_type or 'Standard'

    @property
    def has_tracking(self):
        """Returns True if order has at least one shipment with tracking"""
        return len(self.shipments) > 0

    @property
    def first_shipment(self):
        """Returns the first (most recent) shipment or None"""
        return self.shipments[0] if self.shipments else None

    @property
    def first_tracking_url(self):
        """Returns tracking URL for the first shipment"""
        if self.first_shipment:
            return self.first_shipment.tracking_url
        return None

    @property
    def first_tracking_number(self):
        """Returns tracking number for the first shipment"""
        if self.first_shipment:
            return self.first_shipment.tracking_number
        return None

    @property
    def has_items_outside_set(self):
        """
        Returns True if any order item has is_set_fulfilled = False
        OR has partial fulfillment (fulfilled_quantity < quantity).
        This means some items didn't make it into the complete set.
        """
        for item in self.items:
            if item.is_set_fulfilled is False:
                return True
            if item.fulfilled_quantity is not None and item.fulfilled_quantity < item.quantity:
                return True
        return False

    @property
    def has_set_items(self):
        """
        Returns True if order has any items that are part of a set
        (is_set_fulfilled is not None).
        """
        return any(item.is_set_fulfilled is not None for item in self.items)

    @property
    def has_partial_items(self):
        """
        Returns True if any order item has partial fulfillment
        (fulfilled_quantity > 0 but < quantity).
        """
        for item in self.items:
            if item.fulfilled_quantity is not None and 0 < item.fulfilled_quantity < item.quantity:
                return True
        return False

    @property
    def sorted_items(self):
        """
        Returns order items sorted so that:
        1. Items that are IN the set (is_set_fulfilled == True or None) come first
        2. Items that are OUTSIDE the set (is_set_fulfilled == False) come last
        3. Within each group, maintain original order (by id)

        This ensures that fulfilled items are shown at the top of the list.
        """
        def sort_key(item):
            # is_set_fulfilled can be: True, False, or None
            # Priority:
            # - None (not part of any set) -> 0 (first)
            # - True (in set) -> 1 (second)
            # - False (outside set) -> 2 (last)
            if item.is_set_fulfilled is None:
                return (0, item.id)
            elif item.is_set_fulfilled is True:
                return (1, item.id)
            else:  # False
                return (2, item.id)

        return sorted(self.items, key=sort_key)

    @property
    def effective_total(self):
        """
        Returns effective total - suma tylko zrealizowanych produktów.
        Items with is_set_fulfilled == False are counted as 0.00.
        Items with partial fulfillment (fulfilled_quantity < quantity) are counted proportionally.
        Items with is_set_fulfilled == True or None are counted normally.
        """
        from decimal import Decimal
        total = Decimal('0.00')
        for item in self.items:
            # Skip items that are completely outside set (is_set_fulfilled == False)
            if item.is_set_fulfilled is False:
                continue
            # Check for partial fulfillment
            if item.fulfilled_quantity is not None and item.fulfilled_quantity < item.quantity:
                # Partial - count only fulfilled quantity
                if item.price:
                    total += Decimal(str(item.price)) * item.fulfilled_quantity
            elif item.total:
                total += Decimal(str(item.total))
        return total

    @property
    def effective_grand_total(self):
        """
        Returns effective grand total including shipping.
        Uses effective_total (excluding items outside set) + shipping cost.
        """
        from decimal import Decimal
        shipping = Decimal(str(self.shipping_cost)) if self.shipping_cost else Decimal('0.00')
        return self.effective_total + shipping

    def recalculate_total_amount(self):
        """
        Przelicza total_amount na podstawie aktualnych order_items.
        Używane po closure exclusive (gdy items są zerowane/splitowane).

        Returns:
            Decimal: Nowa wartość total_amount
        """
        from decimal import Decimal

        new_total = Decimal('0.00')
        for item in self.items:
            if item.total:
                new_total += Decimal(str(item.total))

        self.total_amount = new_total
        return new_total

    # ===================================
    # Payment Proof Properties - NEW SYSTEM
    # ===================================

    # --- ORDER PROOF (produkty) ---
    @property
    def has_payment_proof_order(self):
        """Czy wgrano dowód wpłaty za zamówienie"""
        return self.payment_proof_order_file is not None

    @property
    def payment_proof_order_filename(self):
        """Nazwa pliku dowodu ORDER (bez ścieżki)"""
        if not self.payment_proof_order_file:
            return None
        return self.payment_proof_order_file.split('/')[-1]

    @property
    def payment_proof_order_url(self):
        """URL do podglądu dowodu ORDER"""
        if not self.payment_proof_order_file:
            return None
        return f'/admin/orders/{self.id}/payment-proof-order/{self.payment_proof_order_filename}'

    @property
    def can_upload_payment_proof_order(self):
        """Czy można wgrać dowód ORDER (brak lub odrzucony)"""
        return self.payment_proof_order_status is None or self.payment_proof_order_status == 'rejected'

    @property
    def payment_proof_order_is_pending(self):
        """Czy dowód ORDER oczekuje na weryfikację"""
        return self.payment_proof_order_status == 'pending'

    @property
    def payment_proof_order_is_approved(self):
        """Czy dowód ORDER zaakceptowany"""
        return self.payment_proof_order_status == 'approved'

    @property
    def payment_proof_order_is_rejected(self):
        """Czy dowód ORDER odrzucony"""
        return self.payment_proof_order_status == 'rejected'

    # --- SHIPPING PROOF (wysyłka) ---
    @property
    def has_payment_proof_shipping(self):
        """Czy wgrano dowód wpłaty za wysyłkę"""
        return self.payment_proof_shipping_file is not None

    @property
    def payment_proof_shipping_filename(self):
        """Nazwa pliku dowodu SHIPPING (bez ścieżki)"""
        if not self.payment_proof_shipping_file:
            return None
        return self.payment_proof_shipping_file.split('/')[-1]

    @property
    def payment_proof_shipping_url(self):
        """URL do podglądu dowodu SHIPPING"""
        if not self.payment_proof_shipping_file:
            return None
        return f'/admin/orders/{self.id}/payment-proof-shipping/{self.payment_proof_shipping_filename}'

    @property
    def can_upload_payment_proof_shipping(self):
        """
        Czy można wgrać dowód SHIPPING (brak lub odrzucony).
        Wymaga kwoty wysyłki > 0.
        """
        # Musi być kwota > 0
        if not self.shipping_cost or self.shipping_cost <= 0:
            return False

        # Globalna blokada uploadu
        if self.is_payment_proof_upload_disabled:
            return False

        # Status musi być None lub rejected
        return self.payment_proof_shipping_status is None or self.payment_proof_shipping_status == 'rejected'

    @property
    def payment_proof_shipping_is_pending(self):
        """Czy dowód SHIPPING oczekuje na weryfikację"""
        return self.payment_proof_shipping_status == 'pending'

    @property
    def payment_proof_shipping_is_approved(self):
        """Czy dowód SHIPPING zaakceptowany"""
        return self.payment_proof_shipping_status == 'approved'

    @property
    def payment_proof_shipping_is_rejected(self):
        """Czy dowód SHIPPING odrzucony"""
        return self.payment_proof_shipping_status == 'rejected'

    # ===================================
    # Icon Status Properties (dla list zamówień)
    # ===================================

    @property
    def order_payment_icon_status(self):
        """
        Status ikony płatności za zamówienie dla list zamówień.
        Zwraca: {'status': str, 'color': str, 'tooltip': str}

        Statusy:
        - 'none' (szary) - brak dowodu
        - 'pending' (pomarańczowy) - czeka na potwierdzenie
        - 'approved' (zielony) - wpłata potwierdzona
        - 'rejected' (fioletowo-czerwony) - odrzucone potwierdzenie
        - 'error' (czerwony) - błąd
        """
        if self.payment_proof_order_is_approved:
            return {
                'status': 'approved',
                'color': '#4CAF50',
                'tooltip': 'Wpłata za zamówienie potwierdzona'
            }
        elif self.payment_proof_order_is_rejected:
            return {
                'status': 'rejected',
                'color': '#f5576c',
                'tooltip': f'Dowód wpłaty odrzucony: {self.payment_proof_order_rejection_reason or "Brak powodu"}'
            }
        elif self.payment_proof_order_is_pending:
            return {
                'status': 'pending',
                'color': '#FF9800',
                'tooltip': 'Dowód wpłaty czeka na potwierdzenie'
            }
        else:
            return {
                'status': 'none',
                'color': '#9E9E9E',
                'tooltip': 'Brak dowodu wpłaty za zamówienie'
            }

    @property
    def shipping_payment_icon_status(self):
        """
        Status ikony dostawy + płatności za wysyłkę dla list zamówień.
        Zwraca: {'status': str, 'color': str, 'tooltip': str, 'tracking': str, 'shipping_request': ShippingRequest|None}

        Statusy:
        - 'none' (szary) - brak zlecenia wysyłki
        - 'awaiting_price' (żółty) - ma zlecenie, brak kwoty wysyłki
        - 'pending' (pomarańczowy) - ma zlecenie i kwotę, czeka na wpłatę
        - 'shipped' (zielony) - ma numer tracking
        - 'rejected' (czerwony) - błąd/problem
        """
        sr = self.shipping_request

        # Brak zlecenia wysyłki - szara ikona
        if not sr:
            return {
                'status': 'none',
                'color': '#9E9E9E',
                'tooltip': 'Brak zlecenia wysyłki',
                'tracking': None,
                'shipping_request': None
            }

        # Ma zlecenie wysyłki
        tracking = sr.tracking_number
        tooltip = f'Zlecenie: {sr.request_number}'

        # Dodaj info o innych zamówieniach w tym samym zleceniu
        other_orders = self.shipping_request_other_orders
        if other_orders:
            other_nums = ', '.join([o.order_number for o in other_orders[:3]])
            if len(other_orders) > 3:
                other_nums += f' +{len(other_orders) - 3}'
            tooltip += f' | Razem z: {other_nums}'

        # ZIELONY: Ma numer tracking - wysłane
        if tracking:
            tooltip += f' | Nr przesyłki: {tracking}'
            return {
                'status': 'shipped',
                'color': '#4CAF50',
                'tooltip': tooltip,
                'tracking': tracking,
                'shipping_request': sr
            }

        # CZERWONY: Dowód wpłaty odrzucony
        if sr.payment_proof_is_rejected:
            tooltip += ' | Dowód odrzucony'
            return {
                'status': 'rejected',
                'color': '#f5576c',
                'tooltip': tooltip,
                'tracking': tracking,
                'shipping_request': sr
            }

        # Sprawdź czy jest wycena
        has_price = sr.total_shipping_cost and sr.total_shipping_cost > 0

        if has_price:
            tooltip += f' | Koszt: {sr.total_shipping_cost:.2f} zł'
            # POMARAŃCZOWY: Ma kwotę, czeka na potwierdzenie wpłaty
            return {
                'status': 'pending',
                'color': '#FF9800',
                'tooltip': tooltip + ' | Czeka na wpłatę',
                'tracking': tracking,
                'shipping_request': sr
            }

        # ŻÓŁTY: Ma zlecenie, brak wyceny
        tooltip += ' | Oczekuje na wycenę'
        return {
            'status': 'awaiting_price',
            'color': '#FFC107',
            'tooltip': tooltip,
            'tracking': tracking,
            'shipping_request': sr
        }

    # --- SHARED ---
    @property
    def is_payment_proof_upload_disabled(self):
        """
        Czy upload dowodu wpłaty jest zablokowany dla danego statusu zamówienia.
        Lista zablokowanych statusów jest konfigurowana w Ustawienia > Sposoby płatności.
        Dotyczy OBUWAŻNE typy dowodów (ORDER i SHIPPING).
        """
        from modules.auth.models import Settings

        # get_value już parsuje JSON dla typu 'json', więc dostajemy listę
        disabled_statuses = Settings.get_value('payment_proof_disabled_statuses', [])

        # Upewnij się że to lista
        if not isinstance(disabled_statuses, list):
            disabled_statuses = []

        return self.status in disabled_statuses

    # --- SHIPPING REQUEST INTEGRATION ---
    @property
    def shipping_request(self):
        """
        Returns the ShippingRequest this order is assigned to, or None.
        """
        if self.shipping_request_orders and len(self.shipping_request_orders) > 0:
            return self.shipping_request_orders[0].shipping_request
        return None

    @property
    def is_in_shipping_request(self):
        """Returns True if this order is assigned to a shipping request."""
        return self.shipping_request is not None

    @property
    def shipping_request_other_orders(self):
        """
        Returns list of other orders in the same shipping request (excluding this one).
        """
        sr = self.shipping_request
        if not sr:
            return []
        return [ro.order for ro in sr.request_orders if ro.order and ro.order.id != self.id]

    def recalculate_total(self):
        """Recalculates order total from items"""
        from decimal import Decimal
        total = Decimal('0.00')
        for item in self.items:
            if item.total:
                total += Decimal(str(item.total))
        self.total_amount = total

    def generate_guest_view_token(self):
        """Generates a unique token for guest order tracking"""
        self.guest_view_token = secrets.token_urlsafe(32)
        return self.guest_view_token

    @classmethod
    def get_by_guest_token(cls, token):
        """Find order by guest view token"""
        if not token:
            return None
        return cls.query.filter_by(guest_view_token=token, is_guest_order=True).first()


class OrderItem(db.Model):
    """
    Order line items - products in order.
    Includes WMS (Warehouse Management System) fields for picking.
    """
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)  # NULL for custom products

    # Custom product fields (for items without product_id, e.g., full sets)
    custom_name = db.Column(db.String(255), nullable=True)  # Custom product name
    custom_sku = db.Column(db.String(100), nullable=True)   # Optional custom SKU
    is_custom = db.Column(db.Boolean, default=False)        # Flag: True = custom product (no product_id)
    is_full_set = db.Column(db.Boolean, default=False)      # Flag: True = full set from exclusive page

    # Order details
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price = db.Column(db.Numeric(10, 2), nullable=False)  # Price at time of order
    total = db.Column(db.Numeric(10, 2), nullable=False)  # price * quantity

    # WMS fields
    wms_status = db.Column(db.String(50), db.ForeignKey('wms_statuses.slug'), nullable=True)
    picked = db.Column(db.Boolean, default=False)  # Legacy field, kept for compatibility
    picked_at = db.Column(db.DateTime, nullable=True)
    picked_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Exclusive set fulfillment fields
    # NULL = nie dotyczy setu (produkt pojedynczy lub variant_group)
    # True = produkt został przydzielony (zmieścił się w komplecie)
    # False = produkt przepadł (nie zmieścił się w komplecie)
    is_set_fulfilled = db.Column(db.Boolean, nullable=True)
    set_section_id = db.Column(db.Integer, db.ForeignKey('exclusive_sections.id', ondelete='SET NULL'), nullable=True)
    # Ilość zrealizowana w secie (dla częściowego zrealizowania)
    # NULL = nie dotyczy setu
    # fulfilled_quantity == quantity = całość zrealizowana
    # 0 < fulfilled_quantity < quantity = częściowo zrealizowane
    # fulfilled_quantity == 0 = nic nie zrealizowane
    fulfilled_quantity = db.Column(db.Integer, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    order = db.relationship('Order', back_populates='items')
    product = db.relationship('Product', back_populates='order_items')
    picker = db.relationship('User', foreign_keys=[picked_by])
    wms_status_rel = db.relationship('WmsStatus', back_populates='order_items', foreign_keys=[wms_status])
    set_section = db.relationship('ExclusiveSection', foreign_keys=[set_section_id])

    def __repr__(self):
        return f'<OrderItem {self.id} - Order {self.order_id}>'

    @property
    def product_name(self):
        """Returns product name (or custom_name for custom products)"""
        if self.custom_name:
            return self.custom_name
        return self.product.name if self.product else 'Unknown Product'

    @property
    def product_sku(self):
        """Returns product SKU (or custom_sku for custom products)"""
        if self.custom_sku:
            return self.custom_sku
        return self.product.sku if self.product else None

    @property
    def product_ean(self):
        """Returns product EAN"""
        return self.product.ean if self.product else None

    @property
    def product_image_url(self):
        """Returns primary product image URL (or placeholder for custom products)"""
        # For custom products (full sets, manually added), use a special placeholder
        if self.is_custom or self.is_full_set:
            return '/static/img/placeholders/custom-product.svg'
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

    created_at = db.Column(db.DateTime, default=get_local_now)

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
    created_at = db.Column(db.DateTime, default=get_local_now)

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
    created_at = db.Column(db.DateTime, default=get_local_now)
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


# ====================
# SHIPPING REQUESTS
# ====================


class ShippingRequestStatus(db.Model):
    """
    Shipping request status lookup table.
    Allows admin to manage statuses through UI without code changes.
    """
    __tablename__ = 'shipping_request_statuses'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    badge_color = db.Column(db.String(7), default='#6B7280')  # HEX color for badge
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    is_initial = db.Column(db.Boolean, default=False)  # Initial status - client can cancel
    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relationships
    shipping_requests = db.relationship('ShippingRequest', back_populates='status_rel', foreign_keys='ShippingRequest.status')

    def __repr__(self):
        return f'<ShippingRequestStatus {self.slug}>'

    @property
    def display_name(self):
        """Returns formatted name for display"""
        return self.name


class ShippingRequest(db.Model):
    """
    Shipping request model.
    Groups multiple orders for a single shipment.
    """
    __tablename__ = 'shipping_requests'

    id = db.Column(db.Integer, primary_key=True)
    request_number = db.Column(db.String(20), unique=True, nullable=False)  # Format: WYS/000001

    # User relationship
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', backref='shipping_requests')

    # Status (foreign key to shipping_request_statuses)
    status = db.Column(db.String(50), db.ForeignKey('shipping_request_statuses.slug'), default='nowe')
    status_rel = db.relationship('ShippingRequestStatus', back_populates='shipping_requests', foreign_keys=[status])

    # Shipping Address (copy from ShippingAddress at creation time)
    address_type = db.Column(db.String(20), nullable=True)  # 'home' or 'pickup_point'
    shipping_name = db.Column(db.String(200), nullable=True)
    shipping_address = db.Column(db.String(500), nullable=True)
    shipping_postal_code = db.Column(db.String(10), nullable=True)
    shipping_city = db.Column(db.String(100), nullable=True)
    shipping_voivodeship = db.Column(db.String(50), nullable=True)
    shipping_country = db.Column(db.String(100), nullable=True, default='Polska')
    pickup_courier = db.Column(db.String(100), nullable=True)
    pickup_point_id = db.Column(db.String(50), nullable=True)
    pickup_address = db.Column(db.String(500), nullable=True)
    pickup_postal_code = db.Column(db.String(10), nullable=True)
    pickup_city = db.Column(db.String(100), nullable=True)

    # Financial
    total_shipping_cost = db.Column(db.Numeric(10, 2), nullable=True)  # Total shipping cost

    # Payment proof for shipping
    payment_method = db.Column(db.String(100), nullable=True)  # Selected payment method for shipping
    payment_proof_file = db.Column(db.String(255), nullable=True)
    payment_proof_uploaded_at = db.Column(db.DateTime, nullable=True)
    payment_proof_status = db.Column(db.String(20), nullable=True)  # pending, approved, rejected
    payment_proof_rejection_reason = db.Column(db.Text, nullable=True)

    # Tracking
    tracking_number = db.Column(db.String(100), nullable=True)
    courier = db.Column(db.String(50), nullable=True)

    # Parcel size (for pickup points - A, B, C)
    parcel_size = db.Column(db.String(1), nullable=True)  # A, B, C

    # Notes
    admin_notes = db.Column(db.Text, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relationships
    request_orders = db.relationship('ShippingRequestOrder', back_populates='shipping_request', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ShippingRequest {self.request_number}>'

    @property
    def orders(self):
        """Returns list of Order objects in this shipping request"""
        return [ro.order for ro in self.request_orders if ro.order]

    @property
    def orders_count(self):
        """Returns number of orders in this shipping request"""
        return len(self.request_orders)

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
    def can_cancel(self):
        """Returns True if client can cancel this request (only in initial status)"""
        if self.status_rel:
            return self.status_rel.is_initial
        return False

    @property
    def short_address(self):
        """Returns short address for display in lists"""
        if self.address_type == 'pickup_point':
            if self.pickup_courier and self.pickup_point_id:
                return f"{self.pickup_courier}: {self.pickup_point_id}"
            return self.pickup_address or '-'
        else:
            if self.shipping_city:
                return f"{self.shipping_city}, {self.shipping_postal_code or ''}"
            return self.shipping_address or '-'

    @property
    def full_address(self):
        """Returns full address for display"""
        if self.address_type == 'pickup_point':
            parts = []
            if self.pickup_courier:
                parts.append(self.pickup_courier)
            if self.pickup_point_id:
                parts.append(f"({self.pickup_point_id})")
            if self.pickup_address:
                parts.append(self.pickup_address)
            if self.pickup_postal_code and self.pickup_city:
                parts.append(f"{self.pickup_postal_code} {self.pickup_city}")
            return ' '.join(parts) if parts else '-'
        else:
            parts = []
            if self.shipping_name:
                parts.append(self.shipping_name)
            if self.shipping_address:
                parts.append(self.shipping_address)
            if self.shipping_postal_code and self.shipping_city:
                parts.append(f"{self.shipping_postal_code} {self.shipping_city}")
            if self.shipping_voivodeship:
                parts.append(f"woj. {self.shipping_voivodeship}")
            return ', '.join(parts) if parts else '-'

    @property
    def has_payment_proof(self):
        """Returns True if payment proof is uploaded"""
        return self.payment_proof_file is not None

    @property
    def payment_proof_is_pending(self):
        """Returns True if payment proof is pending review"""
        return self.payment_proof_status == 'pending'

    @property
    def payment_proof_is_approved(self):
        """Returns True if payment proof is approved"""
        return self.payment_proof_status == 'approved'

    @property
    def payment_proof_is_rejected(self):
        """Returns True if payment proof is rejected"""
        return self.payment_proof_status == 'rejected'

    @property
    def calculated_shipping_cost(self):
        """
        Dynamically calculates total shipping cost from all orders in this request.
        Returns sum of order.shipping_cost for all orders in this shipping request.
        """
        from decimal import Decimal
        total = Decimal('0.00')
        for ro in self.request_orders:
            if ro.order and ro.order.shipping_cost:
                total += Decimal(str(ro.order.shipping_cost))
        return total if total > 0 else None

    @property
    def can_upload_payment_proof(self):
        """Returns True if client can upload payment proof"""
        # Must have shipping cost set (use calculated cost)
        cost = self.calculated_shipping_cost
        if not cost or cost <= 0:
            return False
        # Status must be None or rejected
        return self.payment_proof_status is None or self.payment_proof_status == 'rejected'

    @property
    def tracking_url(self):
        """Returns tracking URL based on courier"""
        if not self.tracking_number or not self.courier:
            return None
        from modules.orders.utils import get_tracking_url
        return get_tracking_url(self.courier, self.tracking_number)

    @classmethod
    def generate_request_number(cls):
        """Generates next request number in format WYS/000001"""
        last_request = cls.query.order_by(cls.id.desc()).first()
        if last_request and last_request.request_number:
            try:
                last_num = int(last_request.request_number.split('/')[1])
                next_num = last_num + 1
            except (IndexError, ValueError):
                next_num = 1
        else:
            next_num = 1
        return f"WYS/{next_num:06d}"


class ShippingRequestOrder(db.Model):
    """
    Junction table between ShippingRequest and Order.
    Stores shipping cost per order.
    """
    __tablename__ = 'shipping_request_orders'

    id = db.Column(db.Integer, primary_key=True)
    shipping_request_id = db.Column(db.Integer, db.ForeignKey('shipping_requests.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    shipping_cost = db.Column(db.Numeric(10, 2), nullable=True)  # Shipping cost for this order
    created_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    shipping_request = db.relationship('ShippingRequest', back_populates='request_orders')
    order = db.relationship('Order', backref='shipping_request_orders')

    def __repr__(self):
        return f'<ShippingRequestOrder SR:{self.shipping_request_id} O:{self.order_id}>'
