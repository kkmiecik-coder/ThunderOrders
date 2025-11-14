"""
Product Forms
WTForms for products, categories, tags, and suppliers
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, MultipleFileField
from wtforms import (
    StringField, TextAreaField, DecimalField, IntegerField,
    SelectField, SelectMultipleField, BooleanField, SubmitField
)
from wtforms.validators import DataRequired, Optional, Length, NumberRange, ValidationError, Regexp
from modules.products.models import Product, Category, Tag, Supplier


class ProductForm(FlaskForm):
    """Form for creating/editing products"""

    # Basic Information
    name = StringField(
        'Nazwa produktu',
        validators=[DataRequired(message='Nazwa produktu jest wymagana'), Length(max=255)]
    )

    sku = StringField(
        'SKU',
        validators=[Optional(), Length(max=100)]
    )

    ean = StringField(
        'EAN',
        validators=[
            Optional(),
            Length(min=13, max=13, message='EAN musi mieć dokładnie 13 cyfr'),
            Regexp(r'^\d{13}$', message='EAN musi zawierać tylko cyfry')
        ]
    )

    # Taxonomy
    category_id = SelectField(
        'Kategoria',
        coerce=int,
        validators=[Optional()]
    )

    manufacturer_id = SelectField(
        'Producent',
        coerce=int,
        validators=[Optional()]
    )

    series_id = SelectField(
        'Seria produktowa',
        coerce=int,
        validators=[Optional()]
    )

    product_type_id = SelectField(
        'Typ produktu',
        coerce=int,
        validators=[Optional()]
    )

    # Physical Properties
    length = DecimalField(
        'Długość (cm)',
        places=2,
        validators=[Optional(), NumberRange(min=0, message='Długość musi być dodatnia')]
    )

    width = DecimalField(
        'Szerokość (cm)',
        places=2,
        validators=[Optional(), NumberRange(min=0, message='Szerokość musi być dodatnia')]
    )

    height = DecimalField(
        'Wysokość (cm)',
        places=2,
        validators=[Optional(), NumberRange(min=0, message='Wysokość musi być dodatnia')]
    )

    weight = DecimalField(
        'Waga (kg)',
        places=2,
        validators=[Optional(), NumberRange(min=0, message='Waga musi być dodatnia')]
    )

    # Pricing
    sale_price = DecimalField(
        'Cena sprzedaży (PLN)',
        places=2,
        validators=[DataRequired(message='Cena sprzedaży jest wymagana'), NumberRange(min=0.01)]
    )

    purchase_price = DecimalField(
        'Cena zakupu',
        places=2,
        validators=[Optional(), NumberRange(min=0)]
    )

    purchase_currency = SelectField(
        'Waluta zakupu',
        choices=[('PLN', 'PLN'), ('KRW', 'KRW'), ('USD', 'USD')],
        default='PLN'
    )

    purchase_price_pln = DecimalField(
        'Cena zakupu w PLN (przeliczona)',
        places=2,
        validators=[Optional()],
        render_kw={'readonly': True}
    )

    margin = DecimalField(
        'Marża (%)',
        places=2,
        validators=[Optional()],
        render_kw={'readonly': True}
    )

    # Stock
    quantity = IntegerField(
        'Stan magazynowy',
        default=0,
        validators=[Optional()]
    )

    supplier_id = SelectField(
        'Dostawca',
        coerce=int,
        validators=[Optional()]
    )

    # Description
    description = TextAreaField(
        'Opis produktu',
        validators=[Optional()],
        render_kw={'rows': 6}
    )

    # Tags
    tags = SelectMultipleField(
        'Tagi',
        coerce=int,
        validators=[Optional()]
    )

    # Images
    images = MultipleFileField(
        'Zdjęcia produktu',
        validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Tylko pliki graficzne!')]
    )

    # Status
    is_active = BooleanField(
        'Aktywny',
        default=True
    )

    submit = SubmitField('Zapisz produkt')

    def __init__(self, *args, **kwargs):
        super(ProductForm, self).__init__(*args, **kwargs)

        from modules.products.models import Manufacturer, ProductSeries, ProductType

        # Populate category choices
        self.category_id.choices = [(0, '-- Wybierz kategorię --')] + [
            (c.id, c.name) for c in Category.query.filter_by(is_active=True).order_by(Category.name).all()
        ]

        # Populate manufacturer choices
        self.manufacturer_id.choices = [(0, '-- Wybierz producenta --')] + [
            (m.id, m.name) for m in Manufacturer.query.filter_by(is_active=True).order_by(Manufacturer.name).all()
        ]

        # Populate series choices
        self.series_id.choices = [(0, '-- Wybierz serię --')] + [
            (s.id, s.name) for s in ProductSeries.query.filter_by(is_active=True).order_by(ProductSeries.name).all()
        ]

        # Populate product type choices
        self.product_type_id.choices = [(0, '-- Wybierz typ --')] + [
            (pt.id, pt.name) for pt in ProductType.query.filter_by(is_active=True).all()
        ]

        # Populate supplier choices (only for admin - will be hidden for mod in template)
        self.supplier_id.choices = [(0, '-- Wybierz dostawcę --')] + [
            (s.id, s.name) for s in Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
        ]

        # Populate tag choices
        self.tags.choices = [
            (t.id, t.name) for t in Tag.query.order_by(Tag.name).all()
        ]

    def validate_sku(self, field):
        """Validate SKU uniqueness"""
        if field.data:
            # Check if SKU already exists (exclude current product if editing)
            product = Product.query.filter_by(sku=field.data).first()
            if product:
                # If editing, check if it's not the same product
                if not hasattr(self, 'product_id') or product.id != self.product_id:
                    raise ValidationError('SKU już istnieje w bazie danych.')

    def validate_quantity(self, field):
        """Validate quantity based on stock_allow_negative setting"""
        if field.data is not None:
            from modules.auth.models import Settings

            # Check if negative stock is allowed
            allow_negative = Settings.get_value('warehouse_stock_allow_negative', False)

            if not allow_negative and field.data < 0:
                raise ValidationError('Stan magazynowy nie może być ujemny. Zmień ustawienie "Zezwól na ujemny stan magazynowy" w ustawieniach magazynu.')


class CategoryForm(FlaskForm):
    """Form for creating/editing categories"""

    name = StringField(
        'Nazwa kategorii',
        validators=[DataRequired(message='Nazwa kategorii jest wymagana'), Length(max=100)]
    )

    parent_id = SelectField(
        'Kategoria nadrzędna',
        coerce=int,
        validators=[Optional()]
    )

    is_active = BooleanField(
        'Aktywna',
        default=True
    )

    submit = SubmitField('Zapisz kategorię')

    def __init__(self, *args, **kwargs):
        super(CategoryForm, self).__init__(*args, **kwargs)

        # Populate parent category choices (exclude self if editing)
        categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()

        # Filter out current category if editing
        if hasattr(self, 'category_id'):
            categories = [c for c in categories if c.id != self.category_id]

        self.parent_id.choices = [(0, '-- Brak (kategoria główna) --')] + [
            (c.id, c.name) for c in categories
        ]

    def validate_parent_id(self, field):
        """Prevent circular reference"""
        if field.data and field.data != 0:
            # Check if parent_id is not the same as current category
            if hasattr(self, 'category_id') and field.data == self.category_id:
                raise ValidationError('Kategoria nie może być swoim własnym rodzicem.')


class TagForm(FlaskForm):
    """Form for creating/editing tags"""

    name = StringField(
        'Nazwa taga',
        validators=[DataRequired(message='Nazwa taga jest wymagana'), Length(max=50)]
    )

    submit = SubmitField('Zapisz tag')

    def validate_name(self, field):
        """Validate tag name uniqueness"""
        tag = Tag.query.filter_by(name=field.data).first()
        if tag:
            if not hasattr(self, 'tag_id') or tag.id != self.tag_id:
                raise ValidationError('Tag o tej nazwie już istnieje.')


class SupplierForm(FlaskForm):
    """Form for creating/editing suppliers"""

    name = StringField(
        'Nazwa dostawcy',
        validators=[DataRequired(message='Nazwa dostawcy jest wymagana'), Length(max=200)]
    )

    contact_email = StringField(
        'Email kontaktowy',
        validators=[Optional(), Length(max=255)]
    )

    contact_phone = StringField(
        'Telefon kontaktowy',
        validators=[Optional(), Length(max=20)]
    )

    country = StringField(
        'Kraj',
        validators=[Optional(), Length(max=100)]
    )

    notes = TextAreaField(
        'Notatki',
        validators=[Optional()],
        render_kw={'rows': 4}
    )

    is_active = BooleanField(
        'Aktywny',
        default=True
    )

    submit = SubmitField('Zapisz dostawcę')


class QuickTagForm(FlaskForm):
    """Quick form for adding tags (AJAX)"""

    name = StringField(
        'Nazwa taga',
        validators=[DataRequired(), Length(max=50)]
    )


class ProductSearchForm(FlaskForm):
    """Form for searching/filtering products"""

    search = StringField(
        'Szukaj',
        render_kw={'placeholder': 'Nazwa, SKU, EAN...'}
    )

    category_id = SelectField(
        'Kategoria',
        coerce=int,
        validators=[Optional()]
    )

    manufacturer = SelectField(
        'Producent',
        coerce=int,
        validators=[Optional()]
    )

    series = SelectField(
        'Seria',
        coerce=int,
        validators=[Optional()]
    )

    tags = SelectMultipleField(
        'Tagi',
        coerce=int,
        validators=[Optional()]
    )

    is_active = SelectField(
        'Status',
        choices=[('', 'Wszystkie'), ('1', 'Aktywne'), ('0', 'Nieaktywne')],
        default=''
    )

    stock_filter = SelectField(
        'Stan magazynowy',
        choices=[
            ('', 'Wszystkie'),
            ('in_stock', 'W magazynie (>0)'),
            ('out_of_stock', 'Wyprzedane (=0)'),
            ('low_stock', 'Niski stan (<10)')
        ],
        default=''
    )

    def __init__(self, *args, **kwargs):
        super(ProductSearchForm, self).__init__(*args, **kwargs)

        from modules.products.models import Manufacturer, ProductSeries

        # Populate category choices
        self.category_id.choices = [(0, '-- Wszystkie kategorie --')] + [
            (c.id, c.name) for c in Category.query.filter_by(is_active=True).order_by(Category.name).all()
        ]

        # Populate manufacturer choices
        self.manufacturer.choices = [(0, '-- Wszyscy producenci --')] + [
            (m.id, m.name) for m in Manufacturer.query.filter_by(is_active=True).order_by(Manufacturer.name).all()
        ]

        # Populate series choices
        self.series.choices = [(0, '-- Wszystkie serie --')] + [
            (s.id, s.name) for s in ProductSeries.query.filter_by(is_active=True).order_by(ProductSeries.name).all()
        ]

        # Populate tag choices
        self.tags.choices = [
            (t.id, t.name) for t in Tag.query.order_by(Tag.name).all()
        ]


class WarehouseSettingsForm(FlaskForm):
    """Form for warehouse settings"""

    # Image Management
    image_max_size_mb = IntegerField('Max rozmiar zdjęcia (MB)', validators=[Optional(), NumberRange(min=1, max=50)])
    image_max_dimension = IntegerField('Max wymiar zdjęcia (px)', validators=[Optional(), NumberRange(min=800, max=4000)])
    image_quality = IntegerField('Jakość JPEG', validators=[Optional(), NumberRange(min=50, max=100)])
    image_dpi = IntegerField('DPI', validators=[Optional(), NumberRange(min=72, max=300)])
    image_max_per_product = IntegerField('Max zdjęć na produkt', validators=[Optional(), NumberRange(min=1, max=50)])
    image_formats = StringField('Dozwolone formaty', validators=[Length(max=255)])
    
    # Stock Management
    stock_alert_enabled = BooleanField('Włącz alerty stanów')
    stock_alert_threshold = IntegerField('Próg alertu', validators=[Optional(), NumberRange(min=0, max=100)])
    stock_allow_negative = BooleanField('Zezwól na ujemny stan magazynowy')
    stock_show_out_of_stock = BooleanField('Pokazuj produkty wyprzedane')
    
    # Pricing & Currency
    default_purchase_currency = SelectField('Domyślna waluta zakupu', choices=[
        ('PLN', 'PLN'),
        ('KRW', 'KRW'),
        ('USD', 'USD')
    ])
    currency_source = SelectField('Źródło kursów', choices=[
        ('nbp', 'NBP (Narodowy Bank Polski)'),
        ('exchangerate', 'ExchangeRate-API')
    ])
    currency_update_frequency = IntegerField('Częstotliwość aktualizacji (h)', validators=[Optional(), NumberRange(min=1, max=168)])
    currency_krw_rate = DecimalField('Kurs KRW → PLN', validators=[Optional()], places=4)
    currency_usd_rate = DecimalField('Kurs USD → PLN', validators=[Optional()], places=2)
    default_margin = IntegerField('Domyślna marża (%)', validators=[Optional(), NumberRange(min=0, max=500)])
    price_rounding = SelectField('Zaokrąglanie cen', choices=[
        ('full', 'Pełne złote (np. 45.00)'),
        ('decimal', 'Z groszami (np. 45.99)')
    ])

    submit = SubmitField('Zapisz ustawienia')
