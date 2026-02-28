"""
Client Module - Database Models
================================

Models for client features:
- CollectionItem: User's K-pop collection item
- CollectionItemImage: Images for collection items
- PublicCollectionConfig: Public collection page configuration
- CollectionUploadSession: QR code upload session
- CollectionTempUpload: Temporary upload from QR flow
"""

import string
import random
from datetime import datetime, timezone, timedelta
from extensions import db


def get_local_now():
    """Returns current time in Poland (Europe/Warsaw) timezone."""
    utc_now = datetime.now(timezone.utc)
    year = utc_now.year

    march_last = datetime(year, 3, 31, tzinfo=timezone.utc)
    march_last_sunday = march_last - timedelta(days=(march_last.weekday() + 1) % 7)
    dst_start = march_last_sunday.replace(hour=1)

    oct_last = datetime(year, 10, 31, tzinfo=timezone.utc)
    oct_last_sunday = oct_last - timedelta(days=(oct_last.weekday() + 1) % 7)
    dst_end = oct_last_sunday.replace(hour=1)

    if dst_start <= utc_now < dst_end:
        offset = timedelta(hours=2)
    else:
        offset = timedelta(hours=1)

    return (utc_now + offset).replace(tzinfo=None)


class CollectionItem(db.Model):
    """
    User's K-pop collection item.
    Can be added manually or auto-added when order status changes to 'dostarczone'.
    """
    __tablename__ = 'collection_items'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    market_price = db.Column(db.Numeric(10, 2), nullable=True)
    source = db.Column(db.String(20), default='manual')  # 'manual' or 'order'
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_items.id'), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_public = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relationships
    user = db.relationship('User', backref=db.backref('collection_items', lazy='dynamic'))
    order_item = db.relationship('OrderItem', backref=db.backref('collection_item', uselist=False))
    product = db.relationship('Product', backref=db.backref('collection_items', lazy='dynamic'))
    images = db.relationship('CollectionItemImage', back_populates='collection_item',
                             cascade='all, delete-orphan', order_by='CollectionItemImage.sort_order')

    def __repr__(self):
        return f'<CollectionItem {self.id} - {self.name}>'

    @property
    def primary_image(self):
        """Returns the primary image or the first image."""
        for img in self.images:
            if img.is_primary:
                return img
        return self.images[0] if self.images else None

    @property
    def image_url(self):
        """Returns URL for display (compressed primary image, product image fallback, or placeholder)."""
        img = self.primary_image
        if img:
            return f'/static/{img.path_compressed}'
        # Fallback: use linked product's image if imported from order
        if self.product_id and self.product:
            product_img = self.product.primary_image
            if product_img:
                return f'/static/{product_img.path_compressed}'
        return '/static/img/placeholders/collection-item.svg'

    @property
    def is_from_order(self):
        """Returns True if item was auto-added from an order."""
        return self.source == 'order'

    @property
    def images_count(self):
        """Returns number of images."""
        return len(self.images)

    @property
    def can_add_image(self):
        """Returns True if more images can be added (max 3)."""
        return self.images_count < 3


class CollectionItemImage(db.Model):
    """
    Images for collection items.
    Max 3 images per item (enforced at application level).
    """
    __tablename__ = 'collection_item_images'

    id = db.Column(db.Integer, primary_key=True)
    collection_item_id = db.Column(db.Integer, db.ForeignKey('collection_items.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    path_original = db.Column(db.String(500), nullable=False)
    path_compressed = db.Column(db.String(500), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    uploaded_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    collection_item = db.relationship('CollectionItem', back_populates='images')

    def __repr__(self):
        return f'<CollectionItemImage {self.id} - {self.filename}>'


class PublicCollectionConfig(db.Model):
    """
    Configuration for a user's public collection page.
    One config per user (UNIQUE constraint on user_id).
    """
    __tablename__ = 'public_collection_configs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    token = db.Column(db.String(12), unique=True, nullable=False, index=True)
    show_prices = db.Column(db.Boolean, default=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relationships
    user = db.relationship('User', backref=db.backref('public_collection_config', uselist=False))

    def __repr__(self):
        return f'<PublicCollectionConfig user={self.user_id} token={self.token}>'

    @staticmethod
    def generate_token():
        """Generate a unique 12-character token (a-zA-Z0-9)."""
        chars = string.ascii_letters + string.digits
        for _ in range(10):  # retry loop
            token = ''.join(random.choices(chars, k=12))
            if not PublicCollectionConfig.query.filter_by(token=token).first():
                return token
        raise ValueError('Could not generate unique token after 10 attempts')


class CollectionUploadSession(db.Model):
    """
    QR code upload session for adding photos from mobile.
    Sessions expire after 15 minutes.
    """
    __tablename__ = 'collection_upload_sessions'

    id = db.Column(db.Integer, primary_key=True)
    session_token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    collection_item_id = db.Column(db.Integer, db.ForeignKey('collection_items.id'), nullable=True)
    status = db.Column(db.String(20), default='waiting', nullable=False)

    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

    # Relationships
    user = db.relationship('User', backref=db.backref('upload_sessions', lazy='dynamic'))
    collection_item = db.relationship('CollectionItem', backref=db.backref('upload_sessions', lazy='dynamic'))
    temp_uploads = db.relationship('CollectionTempUpload', back_populates='session',
                                   cascade='all, delete-orphan')

    def __repr__(self):
        return f'<CollectionUploadSession {self.session_token} status={self.status}>'

    @property
    def is_expired(self):
        """Check if session has expired."""
        return get_local_now() > self.expires_at

    @property
    def is_valid(self):
        """Check if session is still valid (not expired, status waiting)."""
        return self.status == 'waiting' and not self.is_expired


class CollectionTempUpload(db.Model):
    """
    Temporary upload from QR code flow.
    Linked to a session, moved to CollectionItemImage when item is saved.
    """
    __tablename__ = 'collection_temp_uploads'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('collection_upload_sessions.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    path_original = db.Column(db.String(500), nullable=False)
    path_compressed = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    session = db.relationship('CollectionUploadSession', back_populates='temp_uploads')

    def __repr__(self):
        return f'<CollectionTempUpload {self.id} - {self.filename}>'
