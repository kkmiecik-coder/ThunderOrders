"""
Orders Module - Database Models
================================

Models for orders management:
- OrderStatus: Lookup table for order statuses
- OrderType: Lookup table for order types (Pre-order, On-hand, Offer)
- Order: Main order model
- OrderItem: Order line items (products in order)
- OrderComment: Comments/messages for orders (admin <-> client communication)
- OrderRefund: Refund records for orders
- ShippingRequestStatus: Lookup table for shipping request statuses
- ShippingRequest: Shipping request model (groups orders for shipment)
- ShippingRequestOrder: Junction table between ShippingRequest and Order
- PaymentConfirmation: Potwierdzenia płatności dla zamówień Offer
"""

from datetime import datetime, timezone, timedelta

from sqlalchemy import case, func
from sqlalchemy.ext.hybrid import hybrid_property

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
    Types: Pre-order (PO), On-hand (OH), Offer (EX)
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
    Zamówienia składane wyłącznie przez zalogowanych użytkowników.
    """
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)  # Format: PO/00000001
    order_type = db.Column(db.String(50), db.ForeignKey('order_types.slug'), default='on_hand')

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', back_populates='orders', foreign_keys=[user_id])

    # Admin who manually created this order on behalf of the customer
    # (NULL = standard customer-placed order; set = order added via "Dodaj zamówienie extra")
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    created_by_admin = db.relationship('User', foreign_keys=[created_by_admin_id])

    # Status (foreign key to order_statuses)
    status = db.Column(db.String(50), db.ForeignKey('order_statuses.slug'), default='nowe')
    status_rel = db.relationship('OrderStatus', back_populates='orders', foreign_keys=[status])
    type_rel = db.relationship('OrderType', back_populates='orders', foreign_keys=[order_type])

    # Financial
    total_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    paid_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)  # Amount paid by customer
    shipping_cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)  # Koszt wysyłki
    proxy_shipping_cost = db.Column(db.Numeric(10, 2), default=0.00)  # Koszt dostawy proxy (z Korei)
    customs_vat_sale_cost = db.Column(db.Numeric(10, 2), nullable=True, default=None)  # CŁO/VAT od ceny sprzedaży; NULL = nie ustalono, 0 = bez podatku
    # Delivery and payment
    delivery_method = db.Column(db.String(50), nullable=True)  # kurier, paczkomat, odbior_osobisty
    payment_method = db.Column(db.String(50), nullable=True)  # przelew, pobranie, gotowka, blik

    # Offer page order fields
    offer_page_id = db.Column(db.Integer, db.ForeignKey('offer_pages.id', ondelete='SET NULL'), nullable=True)
    offer_page = db.relationship('OfferPage', back_populates='orders')
    offer_page_name = db.Column(db.String(200), nullable=True)  # Preserved page name for history
    payment_stages = db.Column(db.Integer, nullable=True)  # Dziedziczone z OfferPage (2 lub 3)

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

    # Custom name (client-defined alias)
    custom_name = db.Column(db.String(50), nullable=True)

    # Notes
    notes = db.Column(db.Text, nullable=True)  # Client notes
    admin_notes = db.Column(db.Text, nullable=True)  # Internal admin notes

    # WMS / Packing
    wms_locked_at = db.Column(db.DateTime, nullable=True)  # WMS lock timestamp
    wms_session_id = db.Column(db.Integer, db.ForeignKey('wms_sessions.id'), nullable=True)  # Active WMS session
    packed_at = db.Column(db.DateTime, nullable=True)
    packed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    packing_photo = db.Column(db.String(500), nullable=True)  # Path to packing photo
    total_package_weight = db.Column(db.Numeric(8, 2), nullable=True)  # Package weight in kg
    packaging_material_id = db.Column(db.Integer, db.ForeignKey('packaging_materials.id'), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relationships
    items = db.relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')
    comments = db.relationship('OrderComment', back_populates='order', cascade='all, delete-orphan', order_by='OrderComment.created_at.desc()')
    refunds = db.relationship('OrderRefund', back_populates='order', cascade='all, delete-orphan')
    shipments = db.relationship('OrderShipment', back_populates='order', cascade='all, delete-orphan', order_by='OrderShipment.created_at.desc()')
    payment_confirmations = db.relationship('PaymentConfirmation', back_populates='order', lazy='dynamic', cascade='all, delete-orphan')
    shipping_request_orders = db.relationship('ShippingRequestOrder', back_populates='order', cascade='all, delete-orphan')
    packer = db.relationship('User', foreign_keys=[packed_by])
    packaging_material = db.relationship('PackagingMaterial', foreign_keys=[packaging_material_id])

    def __repr__(self):
        return f'<Order {self.order_number}>'

    @property
    def customer_name(self):
        return self.user.full_name

    @property
    def customer_email(self):
        return self.user.email

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
        """Returns formatted type name. For offer orders, includes page name."""
        if self.order_type == 'exclusive':
            if self.offer_page:
                return f"Exclusive - {self.offer_page.name}"
            elif self.offer_page_name:
                return f"Exclusive - {self.offer_page_name}"
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

    # Flagi opłacenia mierzą wpłaty względem total_to_pay (wszystkie etapy E1–E4),
    # NIE względem grand_total (E1+E4) — inaczej zamówienie z zaległym cłem lub
    # wysyłką z Korei uchodziło za w pełni opłacone. grand_total zostaje surową
    # sumą „produkty + wysyłka PL" do wyświetlania.

    @property
    def is_fully_paid(self):
        """True, gdy wpłacono dokładnie pełną należność ze wszystkich etapów."""
        from decimal import Decimal
        paid = Decimal(str(self.paid_amount)) if self.paid_amount else Decimal('0.00')
        due = self.total_to_pay
        return paid == due and due > Decimal('0.00')

    @property
    def is_overpaid(self):
        """True przy nadpłacie ponad pełną należność ze wszystkich etapów."""
        from decimal import Decimal
        paid = Decimal(str(self.paid_amount)) if self.paid_amount else Decimal('0.00')
        due = self.total_to_pay
        return paid > due and due > Decimal('0.00')

    @property
    def is_partially_paid(self):
        """True, gdy coś wpłacono, ale został jeszcze jakiś etap do opłacenia."""
        from decimal import Decimal
        paid = Decimal(str(self.paid_amount)) if self.paid_amount else Decimal('0.00')
        return paid > Decimal('0.00') and paid < self.total_to_pay

    @property
    def remaining_amount(self):
        """Pozostało do zapłaty ze wszystkich etapów (podłoga 0).

        Alias remaining_to_pay — po ujednoliceniu miary obie nazwy znaczą to samo.
        """
        return self.remaining_to_pay

    @hybrid_property
    def total_to_pay(self):
        """
        Pełna kwota do zapłaty przez klienta — suma wszystkich należnych etapów:
        E1 produkt (total_amount) + E2 wysyłka KR (proxy_shipping_cost, tylko
        4-etapowe) + E3 cło/VAT (customs_vat_sale_cost, nie dotyczy on_hand) +
        E4 wysyłka PL (shipping_cost). Mirror logiki etapów z payment_icon_state.

        Uwaga: grand_total/remaining_amount obejmują tylko E1+E4 — ta właściwość
        jest ich pełnym (wszystkie etapy) odpowiednikiem.

        Hybrid: działa też jako wyrażenie SQL (patrz .expression niżej), dzięki
        czemu filtry płatnicze na listach zamówień mierzą wpłaty względem tej
        samej definicji, bez rozjeżdżania się kopii warunków etapowych.
        """
        from decimal import Decimal
        total = Decimal(str(self.total_amount)) if self.total_amount else Decimal('0.00')  # E1
        # E2: wysyłka z Korei — tylko zamówienia 4-etapowe
        if self.payment_stages == 4 and self.proxy_shipping_cost:
            total += Decimal(str(self.proxy_shipping_cost))
        # E3: cło/VAT — nie dotyczy on_hand
        if self.order_type != 'on_hand' and self.customs_vat_sale_cost:
            total += Decimal(str(self.customs_vat_sale_cost))
        # E4: wysyłka lokalna PL — zawsze
        if self.shipping_cost:
            total += Decimal(str(self.shipping_cost))
        return total

    @total_to_pay.expression
    def total_to_pay(cls):
        """Odpowiednik SQL właściwości wyżej — 1:1 te same warunki etapowe.

        NULL-e: coalesce na kwotach (brak wartości = 0 zł) oraz na order_type,
        żeby zamówienie bez ustawionego typu zachowywało się jak w Pythonie
        (None != 'on_hand' → etap E3 wliczany).
        """
        return (
            func.coalesce(cls.total_amount, 0)                                  # E1
            + case((cls.payment_stages == 4, func.coalesce(cls.proxy_shipping_cost, 0)),
                   else_=0)                                                     # E2
            + case((func.coalesce(cls.order_type, '') != 'on_hand',
                    func.coalesce(cls.customs_vat_sale_cost, 0)),
                   else_=0)                                                     # E3
            + func.coalesce(cls.shipping_cost, 0)                               # E4
        )

    @property
    def remaining_to_pay(self):
        """
        Pozostało do zapłaty łącznie ze wszystkich etapów: total_to_pay − paid_amount,
        podłoga 0 (nadpłata nie generuje wartości ujemnej).

        paid_amount akumuluje sumę WSZYSTKICH zatwierdzonych etapów (E1–E4),
        więc odejmujemy ją od pełnej należności total_to_pay.
        """
        from decimal import Decimal
        paid = Decimal(str(self.paid_amount)) if self.paid_amount else Decimal('0.00')
        remaining = self.total_to_pay - paid
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
        """Returns order source for display (Offer page name or order type)"""
        if self.order_type == 'exclusive':
            if self.offer_page:
                return f"Exclusive: {self.offer_page.name}"
            elif self.offer_page_name:
                return f"Exclusive: {self.offer_page_name} (usunięta)"
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

    @property
    def is_offer(self):
        """Czy zamówienie pochodzi ze strony sprzedaży (Live/Exclusive)."""
        return self.offer_page_id is not None

    @property
    def proxy_shipping_total(self):
        """Koszt dostawy proxy (z Korei) - odczyt z kolumny Order."""
        from decimal import Decimal
        return Decimal(str(self.proxy_shipping_cost)) if self.proxy_shipping_cost else Decimal('0.00')

    @property
    def customs_vat_total(self):
        """CŁO/VAT od ceny sprzedaży - odczyt z kolumny Order."""
        from decimal import Decimal
        return Decimal(str(self.customs_vat_sale_cost)) if self.customs_vat_sale_cost else Decimal('0.00')

    def recalculate_total_amount(self):
        """
        Przelicza total_amount na podstawie aktualnych order_items.
        Używane po closure offer (gdy items są zerowane/splitowane).

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
    def client_shipping_request(self):
        """Zlecenie wysyłki, które należy POKAZAĆ właścicielowi tego zamówienia.

        shipping_request zwraca zlecenie, w którym zamówienie fizycznie leży — po
        konsolidacji jest to paczka zbiorcza z adresem i zamówieniami innej osoby.
        Każdy widok klienta musi używać tej właściwości, inaczej pokaże cudze dane.
        """
        if not self.shipping_request_orders:
            return None
        ro = self.shipping_request_orders[0]
        if ro.source_request_id:
            from modules.orders.models import ShippingRequest
            return db.session.get(ShippingRequest, ro.source_request_id)
        return ro.shipping_request

    @property
    def is_in_shipping_request(self):
        """Returns True if this order is assigned to a shipping request."""
        return self.shipping_request is not None

    @property
    def shipping_request_other_orders(self):
        """Inne zamówienia klienta z tego samego zlecenia — WYŁĄCZNIE jego własne.
        Dla paczki zbiorczej surowe request_orders zwróciłyby zamówienia obcych osób."""
        sr = self.client_shipping_request
        if not sr:
            return []
        return [o for o in sr.display_orders if o.id != self.id]

    # === WŁAŚCIWOŚCI IKON (lista zamówień admin) ===

    @property
    def payment_icon_state(self):
        """Zwraca dict z css_class i tooltip dla ikony statusu płatności."""
        from decimal import Decimal

        paid = Decimal(str(self.paid_amount)) if self.paid_amount else Decimal('0.00')
        grand = self.grand_total

        # Zamówienia z etapami płatności (exclusive, pre_order, on_hand)
        if self.order_type in ('exclusive', 'pre_order', 'on_hand') and self.payment_stages:
            stages_info = []
            statuses = []

            # Mapa ikon statusów etapów
            default_icon = '\u2b55'
            status_icons = {'approved': '\u2705', 'pending': '\u23f3', 'rejected': '\u274c', 'none': default_icon}

            # Kwoty do zapłaty z pól zamówienia
            e1_due = Decimal(str(self.total_amount)) if self.total_amount else Decimal('0.00')
            e4_due = Decimal(str(self.shipping_cost)) if self.shipping_cost else Decimal('0.00')

            # E1: Produkt
            e1_status = self.product_payment_status
            e1_conf = self.product_payment_confirmation
            e1_paid = e1_conf.amount if e1_conf and e1_conf.is_approved else Decimal('0.00')
            e1_icon = status_icons.get(e1_status, default_icon)
            stages_info.append(f"E1 Produkt: {e1_icon} {e1_paid} / {e1_due} z\u0142")
            statuses.append(e1_status)

            # E2: Wysyłka KR (tylko dla 4-etapowych)
            if self.payment_stages == 4:
                e2_due = Decimal(str(self.proxy_shipping_cost)) if self.proxy_shipping_cost else Decimal('0.00')
                e2_status = self.stage_2_status or 'none'
                e2_conf = self.stage_2_confirmation
                e2_paid = e2_conf.amount if e2_conf and e2_conf.is_approved else Decimal('0.00')
                e2_icon = status_icons.get(e2_status, default_icon)
                stages_info.append(f"E2 Wysy\u0142ka KR: {e2_icon} {e2_paid} / {e2_due} z\u0142")
                statuses.append(e2_status)

            # E3: Cło/VAT — obecność etapu rozstrzyga has_customs_vat_stage
            if self.has_customs_vat_stage:
                e3_due = Decimal(str(self.customs_vat_sale_cost)) if self.customs_vat_sale_cost else Decimal('0.00')
                e3_status = self.stage_3_status
                e3_conf = self.stage_3_confirmation
                e3_paid = e3_conf.amount if e3_conf and e3_conf.is_approved else Decimal('0.00')
                e3_icon = status_icons.get(e3_status, default_icon)
                stages_info.append(f"E3 C\u0142o/VAT: {e3_icon} {e3_paid} / {e3_due} z\u0142")
                statuses.append(e3_status)

            # E4: Wysyłka PL
            e4_status = self.stage_4_status
            e4_conf = self.stage_4_confirmation
            e4_paid = e4_conf.amount if e4_conf and e4_conf.is_approved else Decimal('0.00')
            e4_icon = status_icons.get(e4_status, default_icon)
            stages_info.append(f"E4 Wysy\u0142ka PL: {e4_icon} {e4_paid} / {e4_due} z\u0142")
            statuses.append(e4_status)

            tooltip = '\n'.join(stages_info)

            # Ustal klasę CSS na podstawie statusów etapów
            if all(s == 'approved' for s in statuses):
                return {'css_class': 'active', 'tooltip': tooltip}
            if 'rejected' in statuses:
                return {'css_class': 'danger', 'tooltip': tooltip}
            if 'pending' in statuses:
                return {'css_class': 'pending', 'tooltip': tooltip}
            if 'approved' in statuses:
                return {'css_class': 'warning', 'tooltip': tooltip}
            return {'css_class': 'inactive', 'tooltip': tooltip}

        # Zamówienia standardowe (nie-offer)
        payment_method = self.payment_method_display
        shipping = self.shipping_cost or Decimal('0.00')
        tooltip = f"Op\u0142acone: {paid}/{grand} z\u0142 ({int(paid / grand * 100) if grand > 0 else 0}%) | Metoda: {payment_method} | Wysy\u0142ka: {shipping} z\u0142"

        if grand == Decimal('0.00'):
            return {'css_class': 'inactive', 'tooltip': tooltip}
        if self.is_fully_paid or self.is_overpaid:
            return {'css_class': 'active', 'tooltip': tooltip}
        if self.is_partially_paid:
            return {'css_class': 'warning', 'tooltip': tooltip}
        return {'css_class': 'danger', 'tooltip': tooltip}

    @property
    def payment_badge(self):
        """Uproszczony 3-stanowy status płatności dla badge na kafelkach zamówień
        (widok LIVE oferty i podsumowanie zamkniętej strony). Agregat całego
        zamówienia — patrzy na łączną kwotę i potwierdzenia ze wszystkich etapów.

        - 'paid'    → Opłacone (w pełni opłacone lub nadpłata)
        - 'pending' → Wgrane potwierdzenie (jest oczekujące potwierdzenie, ale
                      zamówienie nie jest jeszcze w pełni opłacone)
        - 'unpaid'  → Nieopłacone (brak/odrzucone potwierdzenie, brak pełnej płatności)

        Miarą jest total_to_pay (wszystkie etapy E1–E4), NIE grand_total (tylko
        E1+E4) — inaczej zamówienie z zaległym cłem lub wysyłką z Korei dostawało
        badge „Opłacone". Ten sam mianownik ma filtr płatności na liście klienta
        (apply_payment_status_filter w modules/orders/routes.py).
        """
        from decimal import Decimal
        paid = Decimal(str(self.paid_amount)) if self.paid_amount else Decimal('0.00')
        due = self.total_to_pay
        # Warunek due > 0 zachowany za is_fully_paid — zamówienie bez należności
        # nie jest „opłacone", bo nie było czego opłacać.
        if due > Decimal('0.00') and paid >= due:
            return {'state': 'paid', 'label': 'Opłacone'}
        has_pending = self.payment_confirmations.filter_by(status='pending').first() is not None
        if has_pending:
            return {'state': 'pending', 'label': 'Wgrane potwierdzenie'}
        return {'state': 'unpaid', 'label': 'Nieopłacone'}

    @property
    def shipping_icon_state(self):
        """Zwraca dict z css_class i tooltip dla ikony statusu wysyłki/kuriera — widok admina/WMS.

        Celowo na surowym `shipping_request` (fizyczna paczka), NIE `client_shipping_request`.
        Pracownik magazynu szuka paczki po numerze z tego tooltipa (WMS, eksport InPost) —
        po konsolidacji zlecenie źródłowe ma inny numer niż paczka zbiorcza, więc podanie mu
        numeru źródłowego skończy się nieodnalezioną przesyłką. Odpowiednik dla panelu klienta:
        `client_shipping_icon_state` niżej — te dwie właściwości MUSZĄ pozostać rozdzielone,
        bo każda strona (WMS vs klient) potrzebuje innego zlecenia jako źródła prawdy.
        """
        return self._build_shipping_icon_state(self.shipping_request)

    @property
    def client_shipping_icon_state(self):
        """Jak `shipping_icon_state`, ale dla paneli klienta (listy zamówień w panelu web).

        Czyta `client_shipping_request` — klient ma zobaczyć numer i status WŁASNEGO
        zlecenia, nie paczki zbiorczej z zamówieniami i danymi innej osoby. Nie współdzielić
        z `shipping_icon_state`: patrz komentarz tam, dlaczego rozdzielenie jest celowe.
        """
        return self._build_shipping_icon_state(self.client_shipping_request)

    def _build_shipping_icon_state(self, sr):
        """Wspólna logika ikony statusu wysyłki, parametryzowana zleceniem — żeby
        `shipping_icon_state` i `client_shipping_icon_state` nie duplikowały kodu, mając
        jednocześnie każda swoje własne, odpowiednie źródło zlecenia."""
        if self.has_tracking:
            shipment = self.first_shipment
            courier_name = shipment.courier_display_name if shipment else 'Nieznany'
            tracking = shipment.tracking_number if shipment else '-'
            return {
                'css_class': 'active',
                'tooltip': f"Wys\u0142ane\nTracking: {tracking}\nKurier: {courier_name}"
            }
        if sr:
            return {
                'css_class': 'warning',
                'tooltip': f"Zlecenie {sr.request_number}\nStatus: {sr.status_display_name}"
            }
        return {
            'css_class': 'inactive',
            'tooltip': 'Brak zlecenia wysy\u0142ki'
        }

    # === PAYMENT CONFIRMATIONS PROPERTIES ===

    def _get_cached_confirmation(self, stage):
        """Zwraca PaymentConfirmation dla etapu z `_cached_payment_confirmations`,
        jeśli batch preload je ustawił (get_overdue_orders_summary), inaczej None."""
        if hasattr(self, '_cached_payment_confirmations'):
            return self._cached_payment_confirmations.get(stage)
        return None

    @property
    def product_payment_confirmation(self):
        """Zwraca obiekt PaymentConfirmation dla etapu 'product' (jeśli istnieje)."""
        if hasattr(self, '_cached_payment_confirmations'):
            return self._get_cached_confirmation('product')
        return self.payment_confirmations.filter_by(payment_stage='product').first()

    @property
    def has_product_payment_confirmation(self):
        """Czy zamówienie ma potwierdzenie płatności za produkt"""
        conf = self.product_payment_confirmation
        return conf is not None and conf.has_proof

    @property
    def product_payment_status(self):
        """Status płatności za produkt: 'none', 'pending', 'approved', 'rejected'"""
        conf = self.product_payment_confirmation
        if not conf:
            return 'none'
        return conf.status

    @property
    def can_upload_product_payment(self):
        """
        Czy można wgrać potwierdzenie płatności za produkt.
        Dozwolone statusy obejmują różne etapy realizacji zamówienia,
        aby klient mógł wgrać potwierdzenie nawet jeśli zapomni na etapie 'oczekujace'.
        Pre-order: 'nowe' jest dozwolone (klient płaci od razu po złożeniu).
        Exclusive: wymagane is_fully_closed na stronie offer (płatność dopiero po zamknięciu sprzedaży).
        """
        allowed_statuses = [
            'oczekujace',
            'dostarczone_proxy',
            'w_drodze_polska',
            'urzad_celny',
            'dostarczone_gom',
            'spakowane',
        ]

        # Exclusive: płatność dostępna dopiero po zamknięciu strony offer
        if self.order_type == 'exclusive' and self.offer_page and not self.offer_page.is_fully_closed:
            return False

        # Pre-order i on-hand: 'nowe' jest dozwolone (klient płaci od razu)
        if self.order_type in ('pre_order', 'on_hand') and self.status == 'nowe':
            pass  # allowed
        elif self.status not in allowed_statuses:
            return False

        conf = self.product_payment_confirmation
        if conf and conf.is_approved:
            return False  # Już zatwierdzone

        return True

    # === E2: Wysyłka z Korei (TYLKO dla 4-płatnościowych) ===

    @property
    def stage_2_confirmation(self):
        """E2: Wysyłka KR — tylko dla payment_stages == 4"""
        if self.payment_stages != 4:
            return None
        if hasattr(self, '_cached_payment_confirmations'):
            return self._get_cached_confirmation('korean_shipping')
        return PaymentConfirmation.query.filter_by(
            order_id=self.id,
            payment_stage='korean_shipping'
        ).first()

    @property
    def stage_2_name(self):
        """Nazwa E2"""
        if self.payment_stages == 4:
            return 'Wysyłka z Korei'
        return None

    @property
    def stage_2_status(self):
        """Status E2: None (nie dotyczy) / none/pending/approved/rejected"""
        if self.payment_stages != 4:
            return None  # Dla 3-płatnościowych E2 nie istnieje
        conf = self.stage_2_confirmation
        if not conf:
            return 'none'
        return conf.status

    # === E3: Cło/VAT (ZAWSZE — dla obu typów) ===

    @property
    def stage_3_confirmation(self):
        """E3: Cło/VAT — dla obu typów zamówień"""
        if hasattr(self, '_cached_payment_confirmations'):
            return self._get_cached_confirmation('customs_vat')
        return PaymentConfirmation.query.filter_by(
            order_id=self.id,
            payment_stage='customs_vat'
        ).first()

    @property
    def stage_3_name(self):
        """Nazwa E3: zawsze Cło/VAT"""
        return 'Cło/VAT'

    @property
    def stage_3_status(self):
        """Status E3: none/pending/approved/rejected"""
        conf = self.stage_3_confirmation
        if not conf:
            return 'none'
        return conf.status

    # === E4: Wysyłka lokalna PL (ZAWSZE — dla obu typów) ===

    @property
    def stage_4_confirmation(self):
        """E4: Wysyłka lokalna PL — dla obu typów zamówień"""
        if hasattr(self, '_cached_payment_confirmations'):
            return self._get_cached_confirmation('domestic_shipping')
        return PaymentConfirmation.query.filter_by(
            order_id=self.id,
            payment_stage='domestic_shipping'
        ).first()

    @property
    def stage_4_name(self):
        """Nazwa E4: zawsze Wysyłka lokalna PL"""
        return 'Wysyłka lokalna PL'

    @property
    def stage_4_status(self):
        """Status E4: none/pending/approved/rejected"""
        conf = self.stage_4_confirmation
        if not conf:
            return 'none'
        return conf.status

    # === Helper: Can upload dla E2-E4 ===

    @property
    def can_upload_stage_2(self):
        """Można wgrać E2? (tylko 4-płatnościowe, kwota > 0, nie approved/pending)"""
        if self.payment_stages != 4:
            return False
        if self.stage_2_status in ['approved', 'pending']:
            return False
        if not self.proxy_shipping_cost or self.proxy_shipping_cost <= 0:
            return False
        return True

    @property
    def can_upload_stage_3(self):
        """Można wgrać E3? (kwota > 0, nie approved/pending, nie on-hand)"""
        if self.order_type == 'on_hand':
            return False
        if self.stage_3_status in ['approved', 'pending']:
            return False
        if not self.customs_vat_sale_cost or self.customs_vat_sale_cost <= 0:
            return False
        return True

    @property
    def can_upload_stage_4(self):
        """Można wgrać E4? (kwota > 0, nie approved/pending)"""
        if self.stage_4_status in ['approved', 'pending']:
            return False
        if not self.shipping_cost or self.shipping_cost <= 0:
            return False
        return True

    @property
    def has_customs_vat_stage(self):
        """Czy etap E3 Cło/VAT dotyczy tego zamówienia.

        JEDYNA definicja tej reguły — korzystają z niej order_stage_keys(),
        szablon konta klienta i podpowiedź ikony płatności w panelu admina.
        Nie powielaj warunku w innych miejscach.

        on_hand                → False (etap nigdy nie dotyczy).
        0 (ustalono: bez cła)  → False — brak wiersza, brak możliwości opłacenia.
        NULL (nie ustalono)    → True  — wiersz widoczny, klient widzi 'Zablokowane'.
        > 0                    → True.
        """
        if self.order_type == 'on_hand':
            return False
        return self.customs_vat_sale_cost != 0

    @property
    def is_customs_vat_not_set(self):
        """Cło/VAT jeszcze NIEUSTALONE — etap dotyczy zamówienia, ale admin
        nie podał kwoty (NULL).

        Odróżnia "nieustalone" od "naliczone, ale nieopłacone". Klient nie ma
        wtedy czego opłacić, więc komunikat "najpierw opłać Cło/VAT" byłby
        mylący — front pokazuje "Trwa ustalanie Cła/VAT".

        JEDYNA definicja tego stanu — korzystają z niej walidacja zlecenia
        wysyłki oraz serializacja listy zamówień (web i API mobilne).
        Regułę "czy etap w ogóle dotyczy" bierze z has_customs_vat_stage.
        """
        return self.has_customs_vat_stage and self.customs_vat_sale_cost is None

    @property
    def is_customs_vat_settled(self):
        """E3 Cło/VAT rozliczone — warunek dopuszczenia zlecenia wysyłki (task 869e674fd).

        on_hand                → True (etap nie dotyczy).
        NULL (nie ustalono)    → False — blokuje do czasu decyzji admina w modalu Cło/VAT.
        0 (ustalono bez cła)   → True.
        > 0                    → True dopiero gdy stage_3_status == 'approved'
                                 ('pending'/'rejected'/'none' nie wystarczają).
        """
        if self.order_type == 'on_hand':
            return True
        if self.customs_vat_sale_cost is None:
            return False
        if self.customs_vat_sale_cost <= 0:
            return True
        return self.stage_3_status == 'approved'

    def get_product_deadline(self):
        """Get payment deadline for E1 (product) from the offer page.

        Zamówienia on_hand/pre_order bez strony sprzedaży nie mają stałego
        terminu — ich przypomnienie liczy się regułą 'after_order_placed'
        (godziny od created_at), nie tym getterem.
        """
        if self.offer_page:
            return self.offer_page.payment_deadline
        return None

    def _get_poland_items(self):
        """Zwraca wszystkie PolandOrderItem powiązane z tym zamówieniem przez
        PolandOrderItemOrder (rozdział partii FIFO — jedno zamówienie może
        mieć produkty w kilku różnych partiach).

        Jeśli `_cached_poland_items` zostało wcześniej ustawione (batch preload
        w get_overdue_orders_summary, żeby uniknąć N+1 zapytań), używa go
        zamiast odpytywać bazę ponownie.
        """
        if hasattr(self, '_cached_poland_items'):
            return self._cached_poland_items
        from modules.products.models import PolandOrderItemOrder
        links = PolandOrderItemOrder.query.filter_by(order_id=self.id).all()
        return [link.poland_order_item for link in links if link.poland_order_item]

    def get_shipping_kr_deadline(self):
        """Get payment deadline for E2 (Korean shipping) from PolandOrder.

        Przy kilku partiach (różne produkty tego zamówienia trafiły do różnych
        wysyłek) zwraca NAJWCZEŚNIEJSZY z ich terminów — ten wymaga uwagi
        pierwszy.
        """
        deadlines = [
            item.poland_order.payment_deadline
            for item in self._get_poland_items()
            if item.poland_order and item.poland_order.status != 'anulowane' and item.poland_order.payment_deadline
        ]
        return min(deadlines) if deadlines else None

    def get_customs_vat_deadline(self):
        """Get payment deadline for E3 (Customs/VAT) from PolandOrder.

        Patrz get_shipping_kr_deadline — ta sama zasada najwcześniejszego terminu.
        """
        deadlines = [
            item.poland_order.customs_payment_deadline
            for item in self._get_poland_items()
            if item.poland_order and item.poland_order.status != 'anulowane' and item.poland_order.customs_payment_deadline
        ]
        return min(deadlines) if deadlines else None

    def get_shipping_pl_deadline(self):
        """Get payment deadline for E4 (Domestic shipping) from ShippingRequest."""
        for sr_order in self.shipping_request_orders:
            if sr_order.shipping_request and sr_order.shipping_request.payment_deadline:
                return sr_order.shipping_request.payment_deadline
        return None

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
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)  # NULL for custom products

    # Custom product fields (for items without product_id, e.g., full sets)
    custom_name = db.Column(db.String(255), nullable=True)  # Custom product name
    custom_sku = db.Column(db.String(100), nullable=True)   # Optional custom SKU
    is_custom = db.Column(db.Boolean, default=False)        # Flag: True = custom product (no product_id)
    is_full_set = db.Column(db.Boolean, default=False)      # Flag: True = full set from offer page

    # Size selection (snapshot at time of order)
    selected_size = db.Column(db.String(50), nullable=True)

    # Order details
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price = db.Column(db.Numeric(10, 2), nullable=False)  # Price at time of order
    total = db.Column(db.Numeric(10, 2), nullable=False)  # price * quantity

    # WMS fields
    wms_status = db.Column(db.String(50), db.ForeignKey('wms_statuses.slug'), nullable=True)
    picked = db.Column(db.Boolean, default=False)  # Legacy field, kept for compatibility
    picked_quantity = db.Column(db.Integer, default=0)  # How many units picked so far (0..quantity)
    picked_at = db.Column(db.DateTime, nullable=True)
    picked_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Offer set fulfillment fields
    # NULL = nie dotyczy setu (produkt pojedynczy lub variant_group)
    # True = produkt został przydzielony (zmieścił się w komplecie)
    # False = produkt przepadł (nie zmieścił się w komplecie)
    is_set_fulfilled = db.Column(db.Boolean, nullable=True)
    set_section_id = db.Column(db.Integer, db.ForeignKey('offer_sections.id', ondelete='SET NULL'), nullable=True)
    set_number = db.Column(db.Integer, nullable=True)  # Which set this item belongs to (1-based, e.g. Set 1, Set 2...)
    # Ilość zrealizowana w secie (dla częściowego zrealizowania)
    # NULL = nie dotyczy setu
    # fulfilled_quantity == quantity = całość zrealizowana
    # 0 < fulfilled_quantity < quantity = częściowo zrealizowane
    # fulfilled_quantity == 0 = nic nie zrealizowane
    fulfilled_quantity = db.Column(db.Integer, nullable=True)

    # Bonus (gratis) fields
    is_bonus = db.Column(db.Boolean, default=False, nullable=False)
    bonus_source_section_id = db.Column(db.Integer, db.ForeignKey('offer_sections.id', ondelete='SET NULL'), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    order = db.relationship('Order', back_populates='items')
    product = db.relationship('Product', back_populates='order_items')
    picker = db.relationship('User', foreign_keys=[picked_by])
    wms_status_rel = db.relationship('WmsStatus', back_populates='order_items', foreign_keys=[wms_status])
    set_section = db.relationship('OfferSection', foreign_keys=[set_section_id])
    bonus_source_section = db.relationship('OfferSection', foreign_keys=[bonus_source_section_id])

    def __repr__(self):
        return f'<OrderItem {self.id} - Order {self.order_id}>'

    @property
    def product_name(self):
        """Returns product name (or custom_name for custom products)"""
        if self.custom_name:
            return self.custom_name
        return self.product.name if self.product else 'Unknown Product'

    @property
    def product_name_with_size(self):
        """Returns product name with size badge if applicable"""
        name = self.product_name
        if self.selected_size:
            return f"{name} [{self.selected_size}]"
        return name

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
        # For custom products without a linked product, use a special placeholder
        if (self.is_custom or self.is_full_set) and not self.product_id:
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
        """Czytelna nazwa kuriera (np. "InPost") zamiast surowego sluga ("inpost").

        Czyta z `wms_utils.COURIER_NAMES` — kanonicznej mapy, którą posługuje się
        już WMS (routes.py, wms_utils.py) i `ShippingRequest.courier_display_name`
        — zamiast trzymać własną, drugą kopię literału. Import wewnątrz property,
        nie na górze pliku: `wms_utils` importuje na poziomie modułu
        `wms_models.PackagingMaterial`, a `wms_models` — `models.get_local_now`,
        więc import na górze tego pliku zamyka cykl i wywala się na
        „partially initialized module" (sprawdzone empirycznie).

        Ta zmiana naprawia też realny brak: lokalny literał tutaj nie miał klucza
        'pocztex', mimo że kurier jest wybieralny w interfejsie (ten sam rodzaj
        błędu, co w routes.py — zobacz test_update_sr_pocztex_courier_name_capitalized).
        """
        from modules.orders.wms_utils import COURIER_NAMES
        return COURIER_NAMES.get(self.courier, self.courier)

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

    # User relationship (nullable - user can be deleted, request history preserved)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    user = db.relationship('User', backref='shipping_requests')

    # Status (foreign key to shipping_request_statuses)
    status = db.Column(db.String(50), db.ForeignKey('shipping_request_statuses.slug'), default='czeka_na_wycene')
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

    # Tracking
    tracking_number = db.Column(db.String(100), nullable=True)
    courier = db.Column(db.String(50), nullable=True)

    # Parcel size (mini, A, B, C)
    parcel_size = db.Column(db.String(10), nullable=True)  # mini, A, B, C

    # Notes
    admin_notes = db.Column(db.Text, nullable=True)

    # Wybrany materiał opakowaniowy (źródło ceny/gabarytu/typu — task 869e674tp/xk)
    packaging_material_id = db.Column(db.Integer, db.ForeignKey('packaging_materials.id'), nullable=True)
    packaging_material = db.relationship('PackagingMaterial', foreign_keys=[packaging_material_id])

    # Sugerowany przez klienta typ opakowania: 'karton' / 'koperta' (task 869e674xk)
    client_package_preference = db.Column(db.String(30), nullable=True)

    # Uwagi klienta do wysyłki (task 869e674je) — read-only dla admina
    client_notes = db.Column(db.Text, nullable=True)

    # Termin płatności za wysyłkę PL (E4)
    payment_deadline = db.Column(db.DateTime, nullable=True)

    # Dostawa (task 869efhwph). shipped_at jest punktem odniesienia dla przypomnienia
    # i automatycznego domknięcia — updated_at się do tego nie nadaje, bo zmienia się
    # przy każdej edycji zlecenia, a OrderShipment.created_at powstaje tylko wtedy,
    # gdy podano numer przesyłki.
    shipped_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    # 'klient' | 'auto' | 'admin' — bez tego statystyki nie odróżnią realnych
    # potwierdzeń od domknięć automatu.
    delivered_source = db.Column(db.String(20), nullable=True)
    # Deduplikacja przypomnienia: jedno na zlecenie, więc kolumna zamiast tabeli logu.
    delivery_reminder_sent_at = db.Column(db.DateTime, nullable=True)

    # Konsolidacja — paczka zbiorcza łącząca zlecenia kilku klientów (task 869eckz7u).
    # Na zleceniu ŹRÓDŁOWYM: wskazuje paczkę zbiorczą, w której jadą jego zamówienia.
    consolidated_into_id = db.Column(
        db.Integer, db.ForeignKey('shipping_requests.id', ondelete='SET NULL'), nullable=True
    )
    # Na zleceniu ZBIORCZYM: które ze źródeł jest wiodące (adres, adresat, kontakt).
    lead_source_request_id = db.Column(
        db.Integer, db.ForeignKey('shipping_requests.id', ondelete='SET NULL'), nullable=True
    )

    consolidated_into = db.relationship(
        'ShippingRequest', remote_side=[id], foreign_keys=[consolidated_into_id],
        backref=db.backref('consolidated_sources', lazy='select'),
    )
    lead_source = db.relationship(
        'ShippingRequest', remote_side=[id], foreign_keys=[lead_source_request_id],
    )

    # Timestamps
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relationships
    # foreign_keys jawnie wskazuje shipping_request_id — bez tego SQLAlchemy nie wie,
    # której z dwóch kolumn FK (ta czy source_request_id) użyć do złączenia.
    request_orders = db.relationship(
        'ShippingRequestOrder', back_populates='shipping_request', cascade='all, delete-orphan',
        foreign_keys='ShippingRequestOrder.shipping_request_id',
    )

    # Opinia klienta o dostawie (task 869efhwph) — jedna na zlecenie, patrz
    # modules/orders/review_models.py.
    review = db.relationship(
        'DeliveryReview', back_populates='shipping_request',
        uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ShippingRequest {self.request_number}>'

    @property
    def orders(self):
        """Returns list of Order objects in this shipping request"""
        return [ro.order for ro in self.request_orders if ro.order]

    @property
    def is_consolidation(self):
        """Paczka zbiorcza: ma podpięte zlecenia źródłowe. Jedyne źródło prawdy —
        nie ma osobnej flagi w bazie, żeby stan nie mógł się rozjechać z relacją."""
        return bool(self.consolidated_sources)

    @property
    def is_consolidated_source(self):
        """Zlecenie oddane do paczki zbiorczej — nie jest już samodzielną paczką."""
        return self.consolidated_into_id is not None

    @property
    def display_orders(self):
        """Zamówienia, które należą do TEGO zlecenia z punktu widzenia jego właściciela.

        Po konsolidacji wiersze junction wiszą przy zleceniu zbiorczym, więc źródłowe
        musi odnaleźć swoje zamówienia po source_request_id. Wszystko, co pokazujemy
        klientowi, idzie tędy — self.orders dałoby mu zamówienia obcych osób.
        """
        if self.consolidated_into_id and self.consolidated_into:
            return [
                ro.order for ro in self.consolidated_into.request_orders
                if ro.source_request_id == self.id and ro.order
            ]
        return self.orders

    @property
    def consolidation_participants(self):
        """Uczestnicy paczki zbiorczej, pogrupowani po właścicielu.

        Kolejność: zlecenie wiodące pierwsze, reszta wg numeru zlecenia. Z tego
        korzystają karta w WMS, modal, maile i pushe — jedno miejsce grupowania.
        """
        if not self.is_consolidation:
            return []
        po_zrodle = {}
        for ro in self.request_orders:
            if not ro.order or not ro.source_request_id:
                continue
            po_zrodle.setdefault(ro.source_request_id, []).append(ro.order)

        wynik = []
        for source in self.consolidated_sources:
            wynik.append({
                'user': source.user,
                'source_request': source,
                'orders': po_zrodle.get(source.id, []),
            })
        wynik.sort(key=lambda u: (
            u['source_request'].id != self.lead_source_request_id,
            u['source_request'].request_number or '',
        ))
        return wynik

    @property
    def review_dostawy(self):
        """Opinia o dostawie TEJ przesyłki — dla zbiorczej z zlecenia wiodącego.

        Odbiór paczki zbiorczej potwierdza klient wiodący ze SWOJEGO zlecenia
        źródłowego, więc `zapisz_ocene` zakłada DeliveryReview właśnie tam, a
        `zbiorcze.review` zostaje puste. Wszędzie, gdzie mówimy o ocenie całej
        przesyłki (powiadomienia dla adminów), pytamy tędy — inaczej dla paczki
        zbiorczej ocena zawsze wyglądałaby na niewystawioną.
        """
        if self.review:
            return self.review
        if not self.lead_source_request_id or not self.is_consolidation:
            return None
        lead = next((z for z in self.consolidated_sources
                     if z.id == self.lead_source_request_id), None)
        return lead.review if lead else None

    # Etykiety etapów rozliczenia, na których paczka zbiorcza stoi i czeka na ludzi.
    # Dalsze statusy (opłacone, spakowane, wysłane…) nie blokują niczego po stronie
    # klientów, więc nie mają tu wpisu — brak klucza = brak zdania.
    _ETAPY_BLOKUJACE = {
        'czeka_na_wycene': 'Czeka na wycenę',
        'czeka_na_oplacenie': 'Czeka na opłacenie',
    }

    @property
    def consolidation_block_note(self):
        """Jedno zdanie: co wstrzymuje paczkę zbiorczą i na kogo czekamy.

        Paczka dostaje status NAJMNIEJ zaawansowany ze scalanych zleceń, więc karta
        krzyczała „Czeka na wycenę” nawet wtedy, gdy trzy osoby z czterech już
        zapłaciły — i nie mówiła, która osoba jest tą czwartą. Admin musiał otwierać
        modal i porównywać kwoty przy zamówieniach, żeby to ustalić.

        Zwraca np. „Czeka na wycenę: Jagoda R., Amelia K.” albo None, gdy paczka jest
        opłacona (albo dalej) — wtedy nie ma czego tłumaczyć. Property, nie sklejanie
        w Jinja, bo to samo zdanie renderuje karta WMS i modal wyceny (przez JSON
        endpointu) — a nazwiska skracamy jednym, wspólnym `short_addressee_name`.
        """
        if not self.is_consolidation:
            return None
        etykieta = self._ETAPY_BLOKUJACE.get(self.status)
        if not etykieta:
            return None

        nazwy = []
        for uczestnik in self.consolidation_participants:
            zrodlo = uczestnik['source_request']
            # Blokują wyłącznie ci, którzy stoją na tym samym etapie co cała paczka —
            # reszta jest już dalej i wymienianie jej byłoby wprowadzaniem w błąd.
            if zrodlo.status != self.status:
                continue
            # Konto bywa usunięte albo bez imienia (`short_addressee_name` oddaje wtedy
            # None) — numer zlecenia jest gorszą, ale wciąż działającą wskazówką dla
            # admina, lepszą niż „None” albo milczące pominięcie uczestnika.
            nazwy.append(zrodlo.short_addressee_name or zrodlo.request_number)

        if not nazwy:
            return None
        return f"{etykieta}: {', '.join(nazwy)}"

    @property
    def orders_count(self):
        """Returns number of orders in this shipping request"""
        return len(self.display_orders)

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
        """Returns True if client can cancel this request.

        Cancellation is allowed only when:
        - Status is initial (czeka_na_wycene)
        - No shipping cost has been set (no admin quote)
        - No tracking number has been added
        """
        # Paczka zbiorcza to ustalenie między kilkoma osobami i magazynem — rozmontować
        # ją może wyłącznie admin, niezależnie od statusu, kosztu i numeru przesyłki.
        if self.is_consolidated_source or self.is_consolidation:
            return False

        if not self.status_rel or not self.status_rel.is_initial:
            return False

        # Check if any action has been taken
        if self.total_shipping_cost is not None:
            return False  # Admin added shipping quote
        if self.tracking_number:
            return False  # Admin added tracking

        return True

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
    def addressee_name(self):
        """Pełne imię i nazwisko adresata — do widoków admina, magazynu i etykiet.

        `shipping_name` wypełnia się WYŁĄCZNIE przy dostawie na adres domowy. Przy
        paczkomacie adres siedzi w polach `pickup_*`, a rubryka z nazwiskiem zostaje
        pusta — w tym sklepie to zdecydowana większość zleceń. Adresatem jest wtedy po
        prostu właściciel zlecenia, więc pytamy najpierw adres, potem konto.

        Konto bywa usunięte (`user_id` jest nullable) albo bez wypełnionego profilu —
        wtedy None, żeby wołający pokazał swój zastępnik zamiast „None”. Świadomie NIE
        sięgamy po `User.full_name`: ono degraduje do adresu e-mail, a e-mail w miejscu
        nazwiska adresata wygląda jak błąd danych.
        """
        z_adresu = (self.shipping_name or '').strip()
        if z_adresu:
            return z_adresu
        if not self.user:
            return None
        z_konta = ' '.join(czesc for czesc in (
            (self.user.first_name or '').strip(),
            (self.user.last_name or '').strip(),
        ) if czesc)
        return z_konta or None

    @property
    def short_addressee_name(self):
        """Imię i pierwsza litera nazwiska adresata, np. „Karolina B.”.

        Do pokazania uczestnikom paczki zbiorczej, którzy NIE są adresatem — spec
        (sekcja „Panel klienta”) wymaga, żeby wiedzieli dokąd jedzie ich paczka, ale bez
        ujawniania pełnego nazwiska obcej osoby. Property na modelu, nie sklejanie w
        Jinja, bo ta sama skrócona forma trafi też do maili o scaleniu/wysyłce.

        Źródło nazwy jak w `addressee_name` (adres → konto): przy paczkomacie
        `shipping_name` jest puste, więc wcześniej cała funkcja mówiła uczestnikowi, że
        paczka jedzie „do innej osoby”, nie mówiąc do której — czyli nie mówiła nic.
        """
        z_adresu = (self.shipping_name or '').strip()
        if z_adresu:
            # Jedno pole tekstowe: nie odróżnimy imienia od nazwiska, więc bierzemy
            # pierwszy i ostatni człon — pojedynczy człon zostaje bez zmian.
            czlony = z_adresu.split()
            if len(czlony) == 1:
                return czlony[0]
            return f"{czlony[0]} {czlony[-1][0].upper()}."

        if not self.user:
            return None
        imie = (self.user.first_name or '').strip()
        nazwisko = (self.user.last_name or '').strip()
        # Bez imienia nie ma formy „Imię N.”, a samo nazwisko obcej osoby ujawnia
        # więcej, niż pozwala kontrakt — oddajemy None, żeby wołający użył swojego
        # zastępnika („osoby odbierającej paczkę”).
        if not imie:
            return None
        return f"{imie} {nazwisko[0].upper()}." if nazwisko else imie

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
    def calculated_shipping_cost(self):
        """
        Dynamically calculates total shipping cost from all orders in this request.
        Returns sum of order.shipping_cost for all orders in this shipping request.
        """
        from decimal import Decimal
        total = Decimal('0.00')
        for order in self.display_orders:
            if order.shipping_cost:
                total += Decimal(str(order.shipping_cost))
        return total if total > 0 else None

    @property
    def display_shipping_cost(self):
        """Kwota wysyłki do POKAZANIA: suma z zamówień, a w ostateczności zapisana kolumna.

        `total_shipping_cost` to snapshot zapisywany tylko przy edycji konkretnego
        zlecenia. Konsolidacja go nie przenosi (paczka zbiorcza ma NULL, a źródła
        trzymają swoje stare kwoty), więc karta w WMS pokazywała „Brak wyceny” nad
        zamówieniami wycenionymi na 42,98 zł. `calculated_shipping_cost` liczy z
        zamówień na bieżąco i jest odporne na scalanie — dlatego idzie pierwsze.

        Kolumna zostaje jako źródło zapasowe, bo panel wysyłki w WMS potrafi zapisać
        kwotę łączną bez rozbicia jej na zamówienia (`mark_as_shipped`) — wtedy suma z
        zamówień jest pusta, choć wycena istnieje.

        To wyłącznie warstwa ODCZYTU — nic tu nie zmienia sposobu zapisu kolumny.
        """
        return self.calculated_shipping_cost or self.total_shipping_cost

    @property
    def tracking_url(self):
        """Returns tracking URL based on courier"""
        if not self.tracking_number or not self.courier:
            return None
        from modules.orders.utils import get_tracking_url
        return get_tracking_url(self.courier, self.tracking_number)

    @property
    def courier_display_name(self):
        """Czytelna nazwa kuriera (np. "InPost") zamiast surowego sluga ("inpost").

        Czyta z `wms_utils.COURIER_NAMES` — kanonicznej mapy, którą posługuje się
        już WMS (routes.py, wms_utils.py) i `OrderShipment.courier_display_name`
        (do sierpnia 2026 trzymał własną kopię literału, dziś czyta z tej samej
        mapy) — zamiast drugiego literału. Import wewnątrz property, nie na górze:
        `wms_utils` importuje na poziomie modułu `wms_models.PackagingMaterial`,
        a `wms_models` — `models.get_local_now`, więc import na górze tego pliku
        zamyka cykl i wywala się na „partially initialized module"
        (sprawdzone empirycznie).
        """
        from modules.orders.wms_utils import COURIER_NAMES
        return COURIER_NAMES.get(self.courier, self.courier)

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

    # Z którego zlecenia przyszło zamówienie. NULL = leży tu od początku.
    # Bez tego wypięcie i rozwiązanie konsolidacji nie wie, dokąd zwrócić zamówienie.
    source_request_id = db.Column(
        db.Integer, db.ForeignKey('shipping_requests.id', ondelete='SET NULL'), nullable=True
    )

    created_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    # foreign_keys jawnie wskazuje shipping_request_id (patrz komentarz przy request_orders wyżej).
    shipping_request = db.relationship(
        'ShippingRequest', back_populates='request_orders', foreign_keys=[shipping_request_id],
    )
    order = db.relationship('Order', back_populates='shipping_request_orders')

    def __repr__(self):
        return f'<ShippingRequestOrder SR:{self.shipping_request_id} O:{self.order_id}>'


# ====================
# PAYMENT CONFIRMATIONS
# ====================


class PaymentConfirmation(db.Model):
    """
    Potwierdzenia płatności dla zamówień Offer.
    Wieloetapowy system płatności (produkt, wysyłka KR, cło/VAT, wysyłka PL).
    Jeden plik może być przypisany do wielu zamówień.
    """
    __tablename__ = 'payment_confirmations'

    # Klucze
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)

    # Metoda płatności wybrana przez klienta
    payment_method_id = db.Column(
        db.Integer,
        db.ForeignKey('payment_methods.id'),
        nullable=True,
        comment="Metoda płatności wybrana przez klienta przy uploadzie"
    )

    # OCR Verification
    ocr_score = db.Column(
        db.Integer,
        nullable=True,
        comment="OCR confidence score 0-100"
    )
    ocr_details = db.Column(
        db.Text,
        nullable=True,
        comment="JSON z detalami OCR: wykryte kwoty, tytuły, dane odbiorcy"
    )
    auto_approved = db.Column(
        db.Boolean,
        default=False,
        nullable=False,
        comment="Czy auto-zatwierdzone przez OCR (score >= próg)"
    )

    # Etap płatności
    payment_stage = db.Column(
        db.String(50),
        nullable=False,
        comment="Etap: 'product', 'korean_shipping', 'customs_vat', 'domestic_shipping'"
    )

    # Kwota i potwierdzenie
    amount = db.Column(db.Numeric(10, 2), nullable=False, comment="Kwota do zapłaty w PLN")
    proof_file = db.Column(db.String(255), nullable=True, comment="Nazwa pliku potwierdzenia")
    uploaded_at = db.Column(db.DateTime, nullable=True, comment="Data uploadu przez klienta")

    # Status i weryfikacja
    status = db.Column(
        db.String(20),
        nullable=False,
        default='pending',
        comment="Status: 'pending', 'approved', 'rejected'"
    )
    rejection_reason = db.Column(db.Text, nullable=True, comment="Powód odrzucenia (admin)")

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=get_local_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=get_local_now, onupdate=get_local_now)

    # Relacje
    order = db.relationship('Order', back_populates='payment_confirmations')
    payment_method = db.relationship('PaymentMethod', foreign_keys=[payment_method_id])

    @property
    def is_pending(self):
        """Czy potwierdzenie oczekuje na weryfikację"""
        return self.status == 'pending'

    @property
    def is_approved(self):
        """Czy potwierdzenie zostało zaakceptowane"""
        return self.status == 'approved'

    @property
    def is_rejected(self):
        """Czy potwierdzenie zostało odrzucone"""
        return self.status == 'rejected'

    @property
    def has_proof(self):
        """Czy potwierdzenie ma uploadowany plik"""
        return self.proof_file is not None

    @property
    def proof_url(self):
        """URL do pliku potwierdzenia (przez zabezpieczony endpoint)"""
        if not self.proof_file:
            return None
        from flask import url_for
        return url_for('orders.serve_payment_proof', filename=self.proof_file)

    @property
    def stage_display_name(self):
        """Nazwa etapu po polsku"""
        stages = {
            'product': 'Płatność za produkt',
            'korean_shipping': 'Wysyłka z Korei',
            'customs_vat': 'Cło i VAT',
            'domestic_shipping': 'Wysyłka krajowa'
        }
        return stages.get(self.payment_stage, self.payment_stage)

    def __repr__(self):
        return f'<PaymentConfirmation {self.id} Order:{self.order_id} Stage:{self.payment_stage} Status:{self.status}>'
