"""
Exclusive Pages Models
Modele dla stron ekskluzywnych zamówień (formularze pre-order)
"""

from datetime import datetime, timezone
import secrets
from extensions import db


def get_local_now():
    """Zwraca aktualny czas lokalny (bez timezone info dla porównań z naive datetime)"""
    return datetime.now()


class ExclusivePage(db.Model):
    """
    Strona ekskluzywna - formularz zamówień pre-order

    Statusy:
    - draft: Strona w budowie (niepubliczna)
    - scheduled: Zaplanowana, czeka na datę startu
    - active: Sprzedaż aktywna
    - paused: Sprzedaż wstrzymana tymczasowo
    - ended: Sprzedaż zakończona
    """
    __tablename__ = 'exclusive_pages'

    id = db.Column(db.Integer, primary_key=True)

    # Podstawowe informacje
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    token = db.Column(db.String(100), unique=True, nullable=False, index=True)

    # Status
    status = db.Column(
        db.Enum('draft', 'scheduled', 'active', 'paused', 'ended', name='exclusive_page_status'),
        default='draft',
        nullable=False,
        index=True
    )

    # Daty sprzedaży
    starts_at = db.Column(db.DateTime, nullable=True)  # NULL = brak zaplanowanej daty
    ends_at = db.Column(db.DateTime, nullable=True)    # NULL = bez daty końca

    # Stopka (zawsze na dole strony)
    footer_content = db.Column(db.Text, nullable=True)

    # Metadane
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    creator = db.relationship('User', backref='exclusive_pages', foreign_keys=[created_by])
    sections = db.relationship(
        'ExclusiveSection',
        back_populates='page',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='ExclusiveSection.sort_order'
    )

    def __repr__(self):
        return f'<ExclusivePage {self.name}>'

    # ============================================
    # Token Generation
    # ============================================

    @staticmethod
    def generate_token():
        """Generuje unikalny token dla strony"""
        return secrets.token_urlsafe(16)

    # ============================================
    # Status Helpers
    # ============================================

    @property
    def is_draft(self):
        return self.status == 'draft'

    @property
    def is_scheduled(self):
        return self.status == 'scheduled'

    @property
    def is_active(self):
        return self.status == 'active'

    @property
    def is_paused(self):
        return self.status == 'paused'

    @property
    def is_ended(self):
        return self.status == 'ended'

    @property
    def is_public(self):
        """Czy strona jest dostępna publicznie (nie draft)"""
        return self.status != 'draft'

    @property
    def can_order(self):
        """Czy można składać zamówienia"""
        return self.status == 'active'

    # ============================================
    # Date Helpers
    # ============================================

    @property
    def has_start_date(self):
        return self.starts_at is not None

    @property
    def has_end_date(self):
        return self.ends_at is not None

    @property
    def is_before_start(self):
        """Czy jest przed datą rozpoczęcia"""
        if not self.starts_at:
            return False
        return get_local_now() < self.starts_at

    @property
    def is_after_end(self):
        """Czy jest po dacie zakończenia"""
        if not self.ends_at:
            return False
        return get_local_now() > self.ends_at

    @property
    def time_to_start(self):
        """Zwraca timedelta do rozpoczęcia lub None"""
        if not self.starts_at:
            return None
        diff = self.starts_at - get_local_now()
        if diff.total_seconds() > 0:
            return diff
        return None

    @property
    def time_to_end(self):
        """Zwraca timedelta do zakończenia lub None"""
        if not self.ends_at:
            return None
        diff = self.ends_at - get_local_now()
        if diff.total_seconds() > 0:
            return diff
        return None

    # ============================================
    # URL Helpers
    # ============================================

    def get_public_url(self, _external=True):
        """Zwraca publiczny URL strony"""
        from flask import url_for
        return url_for('exclusive.order_page', token=self.token, _external=_external)

    # ============================================
    # Status Management
    # ============================================

    def publish(self):
        """Publikuje stronę natychmiast (status = active)"""
        self.status = 'active'

    def schedule(self):
        """Planuje publikację na datę starts_at (status = scheduled)"""
        if self.starts_at:
            self.status = 'scheduled'
        else:
            # Brak daty = publikuj od razu
            self.status = 'active'

    def pause(self):
        """Wstrzymuje sprzedaż"""
        self.status = 'paused'

    def resume(self):
        """Wznawia sprzedaż"""
        self.status = 'active'

    def end(self):
        """Kończy sprzedaż"""
        self.status = 'ended'

    def check_and_update_status(self):
        """
        Sprawdza daty i automatycznie aktualizuje status.
        Wywoływane przy każdym dostępie do strony.
        """
        now = get_local_now()

        # Jeśli scheduled i minęła data startu -> active
        if self.status == 'scheduled' and self.starts_at and now >= self.starts_at:
            self.status = 'active'
            db.session.commit()
            return True

        # Jeśli active i minęła data końca -> ended
        if self.status == 'active' and self.ends_at and now >= self.ends_at:
            self.status = 'ended'
            db.session.commit()
            return True

        # Jeśli ended ale data końca jest w przyszłości (lub brak daty końca) -> wznów jako active
        # (np. admin przesunął datę zakończenia na później)
        if self.status == 'ended':
            # Sprawdź czy data końca jest w przyszłości lub nie ma daty końca
            end_date_ok = not self.ends_at or now < self.ends_at
            # Sprawdź czy data startu już minęła lub nie ma daty startu
            start_date_ok = not self.starts_at or now >= self.starts_at

            if end_date_ok and start_date_ok:
                self.status = 'active'
                db.session.commit()
                return True

        return False

    # ============================================
    # Sections Management
    # ============================================

    def get_sections_ordered(self):
        """Zwraca sekcje posortowane po sort_order"""
        return self.sections.order_by(ExclusiveSection.sort_order).all()

    def get_product_sections(self):
        """Zwraca tylko sekcje z produktami"""
        return self.sections.filter_by(section_type='product').order_by(ExclusiveSection.sort_order).all()

    def get_set_sections(self):
        """Zwraca tylko sekcje z setami"""
        return self.sections.filter_by(section_type='set').order_by(ExclusiveSection.sort_order).all()

    # ============================================
    # Class Methods
    # ============================================

    @classmethod
    def get_by_token(cls, token):
        """Znajduje stronę po tokenie"""
        return cls.query.filter_by(token=token).first()

    @classmethod
    def get_active_pages(cls):
        """Zwraca wszystkie aktywne strony"""
        return cls.query.filter_by(status='active').all()


class ExclusiveSection(db.Model):
    """
    Sekcja strony ekskluzywnej

    Typy sekcji:
    - heading: Nagłówek H2
    - paragraph: Paragraf tekstu
    - product: Pojedynczy produkt
    - set: Set produktów (komplet)
    - variant_group: Grupa wariantowa (produkty z wariantami)
    """
    __tablename__ = 'exclusive_sections'

    id = db.Column(db.Integer, primary_key=True)
    exclusive_page_id = db.Column(db.Integer, db.ForeignKey('exclusive_pages.id'), nullable=False, index=True)

    # Typ sekcji
    section_type = db.Column(
        db.Enum('heading', 'paragraph', 'product', 'set', 'variant_group', name='exclusive_section_type'),
        nullable=False
    )
    sort_order = db.Column(db.Integer, default=0)

    # Dla heading i paragraph
    content = db.Column(db.Text, nullable=True)

    # Dla product
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    min_quantity = db.Column(db.Integer, nullable=True)  # NULL = brak minimum
    max_quantity = db.Column(db.Integer, nullable=True)  # NULL = brak maksimum

    # Dla set
    set_name = db.Column(db.String(200), nullable=True)
    set_image = db.Column(db.String(500), nullable=True)  # Ścieżka do zdjęcia tła seta
    set_min_sets = db.Column(db.Integer, default=1)       # Min. kompletnych setów
    set_max_sets = db.Column(db.Integer, nullable=True)   # NULL = brak maksimum
    set_max_per_product = db.Column(db.Integer, nullable=True)  # Max sztuk na produkt (globalny limit sprzedaży)

    # Dla variant_group
    variant_group_id = db.Column(db.Integer, db.ForeignKey('variant_groups.id'), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    page = db.relationship('ExclusivePage', back_populates='sections')
    product = db.relationship('Product', backref='exclusive_sections')
    variant_group = db.relationship('VariantGroup', backref='exclusive_sections')
    set_items = db.relationship(
        'ExclusiveSetItem',
        back_populates='section',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='ExclusiveSetItem.sort_order'
    )

    def __repr__(self):
        return f'<ExclusiveSection {self.section_type} #{self.id}>'

    # ============================================
    # Type Helpers
    # ============================================

    @property
    def is_heading(self):
        return self.section_type == 'heading'

    @property
    def is_paragraph(self):
        return self.section_type == 'paragraph'

    @property
    def is_product(self):
        return self.section_type == 'product'

    @property
    def is_set(self):
        return self.section_type == 'set'

    @property
    def is_variant_group(self):
        return self.section_type == 'variant_group'

    @property
    def is_content_section(self):
        """Czy to sekcja tekstowa (heading lub paragraph)"""
        return self.section_type in ('heading', 'paragraph')

    @property
    def is_orderable_section(self):
        """Czy to sekcja z możliwością zamówienia (product, set lub variant_group)"""
        return self.section_type in ('product', 'set', 'variant_group')

    # ============================================
    # Variant Group Helpers
    # ============================================

    def get_variant_group_products(self):
        """Zwraca produkty z grupy wariantowej"""
        if not self.variant_group:
            return []
        return self.variant_group.products

    # ============================================
    # Quantity Helpers
    # ============================================

    @property
    def has_min_quantity(self):
        return self.min_quantity is not None

    @property
    def has_max_quantity(self):
        return self.max_quantity is not None

    # ============================================
    # Set Helpers
    # ============================================

    def get_set_items_ordered(self):
        """Zwraca elementy setu posortowane"""
        return self.set_items.order_by(ExclusiveSetItem.sort_order).all()

    def get_set_products(self):
        """Zwraca produkty z setu"""
        return [item.product for item in self.get_set_items_ordered() if item.product]


class ExclusiveSetItem(db.Model):
    """
    Element setu - pojedynczy produkt LUB grupa wariantowa wchodząca w skład setu

    Może zawierać:
    - product_id: pojedynczy produkt
    - variant_group_id: grupa wariantowa (wszystkie produkty z grupy)

    Jeden z tych dwóch musi być wypełniony.
    """
    __tablename__ = 'exclusive_set_items'

    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('exclusive_sections.id'), nullable=False, index=True)

    # Można dodać pojedynczy produkt LUB grupę wariantową
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    variant_group_id = db.Column(db.Integer, db.ForeignKey('variant_groups.id'), nullable=True)

    quantity_per_set = db.Column(db.Integer, default=1)  # Ile sztuk tego produktu w jednym secie
    sort_order = db.Column(db.Integer, default=0)

    # Relationships
    section = db.relationship('ExclusiveSection', back_populates='set_items')
    product = db.relationship('Product', backref='exclusive_set_items')
    variant_group = db.relationship('VariantGroup', backref='exclusive_set_items')

    def __repr__(self):
        if self.product_id:
            return f'<ExclusiveSetItem #{self.id} - Product {self.product_id}>'
        elif self.variant_group_id:
            return f'<ExclusiveSetItem #{self.id} - VariantGroup {self.variant_group_id}>'
        return f'<ExclusiveSetItem #{self.id}>'

    @property
    def is_product(self):
        """Czy element to pojedynczy produkt"""
        return self.product_id is not None

    @property
    def is_variant_group(self):
        """Czy element to grupa wariantowa"""
        return self.variant_group_id is not None

    def get_products(self):
        """
        Zwraca listę produktów dla tego elementu.
        Dla pojedynczego produktu - [product]
        Dla grupy wariantowej - wszystkie produkty z grupy
        """
        if self.product:
            return [self.product]
        elif self.variant_group:
            return [p for p in self.variant_group.products if p.is_active]
        return []

    @property
    def display_name(self):
        """Nazwa do wyświetlenia"""
        if self.product:
            return self.product.name
        elif self.variant_group:
            return self.variant_group.name
        return "Nieznany element"
