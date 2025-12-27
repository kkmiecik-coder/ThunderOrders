"""
Product Models
Database models for products, categories, tags, suppliers and images
"""

from extensions import db
from datetime import datetime, timezone, timedelta




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

class Category(db.Model):
    """Product Category with hierarchical structure"""
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    parent = db.relationship('Category', remote_side=[id], backref='children')
    products = db.relationship('Product', back_populates='category', lazy='dynamic')

    def __repr__(self):
        return f'<Category {self.name}>'


class Supplier(db.Model):
    """Product Supplier"""
    __tablename__ = 'suppliers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    contact_email = db.Column(db.String(255), nullable=True)
    contact_phone = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relationships
    products = db.relationship('Product', back_populates='supplier', lazy='dynamic')

    def __repr__(self):
        return f'<Supplier {self.name}>'


class Tag(db.Model):
    """Product Tag"""
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=get_local_now)

    def __repr__(self):
        return f'<Tag {self.name}>'


class Manufacturer(db.Model):
    """Product Manufacturer"""
    __tablename__ = 'manufacturers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relationships
    products = db.relationship('Product', back_populates='manufacturer', lazy='dynamic')

    def __repr__(self):
        return f'<Manufacturer {self.name}>'


class ProductSeries(db.Model):
    """Product Series"""
    __tablename__ = 'product_series'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relationships
    products = db.relationship('Product', back_populates='series', lazy='dynamic')

    def __repr__(self):
        return f'<ProductSeries {self.name}>'


class ProductType(db.Model):
    """Product Type (Pre-order, On-hand, Exclusive)"""
    __tablename__ = 'product_types'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    products = db.relationship('Product', back_populates='product_type', lazy='dynamic')

    def __repr__(self):
        return f'<ProductType {self.name}>'


class VariantGroup(db.Model):
    """Variant Group - supports multiple groups per product"""
    __tablename__ = 'variant_groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)  # e.g. "Grupa 1", "Grupa 2"
    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    def __repr__(self):
        return f'<VariantGroup {self.id} - {self.name}>'


# Junction table for Product-VariantGroup many-to-many relationship
variant_products = db.Table('variant_products',
    db.Column('id', db.Integer, primary_key=True),
    db.Column('variant_group_id', db.Integer, db.ForeignKey('variant_groups.id', ondelete='CASCADE'), nullable=False),
    db.Column('product_id', db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
    db.Column('added_at', db.DateTime, default=get_local_now),
    db.UniqueConstraint('variant_group_id', 'product_id', name='unique_variant_product')
)


class Product(db.Model):
    """Main Product Model"""
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    sku = db.Column(db.String(100), unique=True, nullable=True)
    ean = db.Column(db.String(13), nullable=True)

    # Taxonomy
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    manufacturer_id = db.Column(db.Integer, db.ForeignKey('manufacturers.id'), nullable=True)
    series_id = db.Column(db.Integer, db.ForeignKey('product_series.id'), nullable=True)
    product_type_id = db.Column(db.Integer, db.ForeignKey('product_types.id'), nullable=True)

    # Physical properties
    length = db.Column(db.Numeric(8, 2), nullable=True)  # cm
    width = db.Column(db.Numeric(8, 2), nullable=True)   # cm
    height = db.Column(db.Numeric(8, 2), nullable=True)  # cm
    weight = db.Column(db.Numeric(8, 2), nullable=True)  # kg

    # Pricing
    sale_price = db.Column(db.Numeric(10, 2), nullable=False)
    purchase_price = db.Column(db.Numeric(10, 2), nullable=True)
    purchase_currency = db.Column(db.Enum('PLN', 'KRW', 'USD', name='currency_types'), default='PLN')
    purchase_price_pln = db.Column(db.Numeric(10, 2), nullable=True)  # Converted price
    margin = db.Column(db.Numeric(5, 2), nullable=True)  # Percentage

    # Stock
    quantity = db.Column(db.Integer, default=0)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)

    # Description
    description = db.Column(db.Text, nullable=True)

    # Status
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relationships
    category = db.relationship('Category', back_populates='products')
    manufacturer = db.relationship('Manufacturer', back_populates='products')
    series = db.relationship('ProductSeries', back_populates='products')
    product_type = db.relationship('ProductType', back_populates='products')
    supplier = db.relationship('Supplier', back_populates='products')
    images = db.relationship('ProductImage', back_populates='product', lazy='dynamic', cascade='all, delete-orphan')
    tags = db.relationship('Tag', secondary='product_tags', backref='products')
    variant_groups = db.relationship('VariantGroup', secondary=variant_products, backref='products')
    order_items = db.relationship('OrderItem', back_populates='product', lazy='dynamic')

    def __repr__(self):
        return f'<Product {self.name}>'

    @property
    def primary_image(self):
        """Get primary image or first image"""
        primary = self.images.filter_by(is_primary=True).first()
        if primary:
            return primary
        return self.images.first()

    def calculate_margin(self):
        """Calculate margin percentage"""
        if self.purchase_price_pln and self.sale_price:
            margin = ((float(self.sale_price) - float(self.purchase_price_pln)) / float(self.purchase_price_pln)) * 100
            self.margin = round(margin, 2)
        else:
            self.margin = None


class ProductImage(db.Model):
    """Product Image"""
    __tablename__ = 'product_images'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    path_original = db.Column(db.String(500), nullable=False)
    path_compressed = db.Column(db.String(500), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    uploaded_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    product = db.relationship('Product', back_populates='images')

    def __repr__(self):
        return f'<ProductImage {self.filename}>'


# Junction table for Product-Tag many-to-many relationship
product_tags = db.Table('product_tags',
    db.Column('id', db.Integer, primary_key=True),
    db.Column('product_id', db.Integer, db.ForeignKey('products.id'), nullable=False),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), nullable=False),
    db.UniqueConstraint('product_id', 'tag_id', name='unique_product_tag')
)


class StockOrder(db.Model):
    """Stock Order - zamówienia produktów od dostawców"""
    __tablename__ = 'stock_orders'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False)  # Format: SO/PROXY/00001 lub SO/PL/00001
    order_type = db.Column(db.Enum('proxy', 'polska', name='stock_order_types'), nullable=False)

    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)

    # Status based on PRD order statuses
    status = db.Column(db.Enum(
        'nowe',
        'oczekujace',
        'dostarczone_proxy',
        'w_drodze_polska',
        'urzad_celny',
        'dostarczone_gom',
        'anulowane',
        name='stock_order_status'
    ), default='nowe', nullable=False)

    # Financial
    total_amount = db.Column(db.Numeric(10, 2), default=0.00)
    currency = db.Column(db.Enum('PLN', 'KRW', 'USD', name='order_currency_types'), default='PLN')
    total_amount_pln = db.Column(db.Numeric(10, 2), default=0.00)  # Converted to PLN

    # Dates
    order_date = db.Column(db.DateTime, default=get_local_now)
    expected_delivery_date = db.Column(db.DateTime, nullable=True)
    actual_delivery_date = db.Column(db.DateTime, nullable=True)

    # Notes
    notes = db.Column(db.Text, nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)

    # Tracking
    tracking_number = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relationships
    supplier = db.relationship('Supplier', backref='stock_orders')
    items = db.relationship('StockOrderItem', back_populates='stock_order', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<StockOrder {self.order_number}>'


class StockOrderItem(db.Model):
    """Stock Order Item - produkty w zamówieniu magazynowym"""
    __tablename__ = 'stock_order_items'

    id = db.Column(db.Integer, primary_key=True)
    stock_order_id = db.Column(db.Integer, db.ForeignKey('stock_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)

    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    total_price = db.Column(db.Numeric(10, 2), nullable=False)

    received_quantity = db.Column(db.Integer, default=0)  # Ilość otrzymana

    created_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    stock_order = db.relationship('StockOrder', back_populates='items')
    product = db.relationship('Product', backref='stock_order_items')

    def __repr__(self):
        return f'<StockOrderItem {self.id} - Product {self.product_id}>'
