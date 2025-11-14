"""
Product Models
Database models for products, categories, tags, suppliers and images
"""

from extensions import db
from datetime import datetime


class Category(db.Model):
    """Product Category with hierarchical structure"""
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    products = db.relationship('Product', back_populates='supplier', lazy='dynamic')

    def __repr__(self):
        return f'<Supplier {self.name}>'


class Tag(db.Model):
    """Product Tag"""
    __tablename__ = 'tags'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Tag {self.name}>'


class Manufacturer(db.Model):
    """Product Manufacturer"""
    __tablename__ = 'manufacturers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    products = db.relationship('Product', back_populates='product_type', lazy='dynamic')

    def __repr__(self):
        return f'<ProductType {self.name}>'


class VariantGroup(db.Model):
    """Variant Group - supports multiple groups per product"""
    __tablename__ = 'variant_groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)  # e.g. "Grupa 1", "Grupa 2"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<VariantGroup {self.id} - {self.name}>'


# Junction table for Product-VariantGroup many-to-many relationship
variant_products = db.Table('variant_products',
    db.Column('id', db.Integer, primary_key=True),
    db.Column('variant_group_id', db.Integer, db.ForeignKey('variant_groups.id', ondelete='CASCADE'), nullable=False),
    db.Column('product_id', db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
    db.Column('added_at', db.DateTime, default=datetime.utcnow),
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

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    category = db.relationship('Category', back_populates='products')
    manufacturer = db.relationship('Manufacturer', back_populates='products')
    series = db.relationship('ProductSeries', back_populates='products')
    product_type = db.relationship('ProductType', back_populates='products')
    supplier = db.relationship('Supplier', back_populates='products')
    images = db.relationship('ProductImage', back_populates='product', lazy='dynamic', cascade='all, delete-orphan')
    tags = db.relationship('Tag', secondary='product_tags', backref='products')
    variant_groups = db.relationship('VariantGroup', secondary=variant_products, backref='products')

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
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

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
