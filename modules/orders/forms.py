"""
Orders Module - WTForms
=======================

Forms for orders management:
- OrderFilterForm: Filtering orders list
- OrderStatusForm: Changing order status
- OrderCommentForm: Adding comments to orders
- OrderTrackingForm: Updating tracking information
- RefundForm: Issuing refunds
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, SelectField, SelectMultipleField,
    DateField, BooleanField, DecimalField, SubmitField
)
from wtforms.validators import DataRequired, Optional, Email, Length, NumberRange
from modules.orders.utils import get_courier_choices


# ====================
# FILTER FORMS
# ====================

class OrderFilterForm(FlaskForm):
    """
    Form for filtering orders list.
    Used in admin orders list page.
    """
    # Order type filter
    order_type = SelectField(
        'Typ zamówienia',
        choices=[
            ('', 'Wszystkie'),
            ('pre_order', 'Pre-order'),
            ('on_hand', 'On-hand'),
            ('exclusive', 'Exclusive'),
        ],
        validators=[Optional()]
    )

    # Status filter (multi-select)
    status = SelectMultipleField(
        'Status',
        choices=[],  # Will be populated dynamically from database
        validators=[Optional()]
    )

    # Date range
    date_from = DateField(
        'Data od',
        format='%Y-%m-%d',
        validators=[Optional()]
    )

    date_to = DateField(
        'Data do',
        format='%Y-%m-%d',
        validators=[Optional()]
    )

    # Search field (order number, customer name, email)
    search = StringField(
        'Szukaj',
        validators=[Optional(), Length(max=200)]
    )

    # Items per page
    per_page = SelectField(
        'Na stronę',
        choices=[
            ('10', '10'),
            ('20', '20'),
            ('30', '30'),
            ('40', '40'),
            ('50', '50'),
            ('100', '100'),
            ('200', '200'),
        ],
        default='20',
        validators=[Optional()]
    )

    submit = SubmitField('Filtruj')


# ====================
# ORDER MANAGEMENT FORMS
# ====================

class OrderStatusForm(FlaskForm):
    """
    Form for changing order status.
    Used in admin order detail page (HTMX endpoint).
    """
    status = SelectField(
        'Status',
        choices=[],  # Will be populated dynamically from database
        validators=[DataRequired(message='Wybierz status')]
    )

    submit = SubmitField('Zmień status')


class OrderCommentForm(FlaskForm):
    """
    Form for adding comments to orders.
    Used in both admin and client order detail pages.
    """
    comment = TextAreaField(
        'Komentarz',
        validators=[
            DataRequired(message='Wpisz treść komentarza'),
            Length(min=1, max=5000, message='Komentarz może mieć max 5000 znaków')
        ],
        render_kw={'placeholder': 'Wpisz komentarz...', 'rows': 4}
    )

    # Only visible for admin/mod
    is_internal = BooleanField(
        'Notatka wewnętrzna (nie wysyła email do klienta)',
        default=False
    )

    submit = SubmitField('Dodaj komentarz')


class OrderTrackingForm(FlaskForm):
    """
    Form for updating tracking information.
    Used in admin order detail page.
    """
    tracking_number = StringField(
        'Numer przesyłki',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': 'Wpisz numer przesyłki'}
    )

    courier = SelectField(
        'Kurier',
        choices=[],  # Will be populated from get_courier_choices()
        validators=[Optional()]
    )

    submit = SubmitField('Zapisz tracking')

    def __init__(self, *args, **kwargs):
        super(OrderTrackingForm, self).__init__(*args, **kwargs)
        # Populate courier choices
        self.courier.choices = get_courier_choices()


class RefundForm(FlaskForm):
    """
    Form for issuing refunds.
    Used in admin order detail page (modal).
    """
    amount = DecimalField(
        'Kwota zwrotu (PLN)',
        places=2,
        validators=[
            DataRequired(message='Podaj kwotę zwrotu'),
            NumberRange(min=0.01, message='Kwota musi być większa niż 0')
        ],
        render_kw={'placeholder': '0.00', 'step': '0.01'}
    )

    reason = TextAreaField(
        'Powód zwrotu',
        validators=[
            DataRequired(message='Podaj powód zwrotu'),
            Length(min=10, max=1000, message='Powód musi mieć od 10 do 1000 znaków')
        ],
        render_kw={'placeholder': 'Opisz powód zwrotu...', 'rows': 4}
    )

    submit = SubmitField('Potwierdź zwrot')


# ====================
# GUEST ORDER FORM
# ====================

class GuestOrderForm(FlaskForm):
    """
    Form for guest orders (exclusive pages).
    Used when placing order without account.
    """
    guest_name = StringField(
        'Imię i nazwisko',
        validators=[
            DataRequired(message='Podaj imię i nazwisko'),
            Length(min=3, max=200, message='Imię i nazwisko musi mieć od 3 do 200 znaków')
        ],
        render_kw={'placeholder': 'Jan Kowalski'}
    )

    guest_email = StringField(
        'Email',
        validators=[
            DataRequired(message='Podaj adres email'),
            Email(message='Podaj prawidłowy adres email'),
            Length(max=255)
        ],
        render_kw={'placeholder': 'jan@example.com'}
    )

    guest_phone = StringField(
        'Telefon',
        validators=[
            Optional(),
            Length(max=20, message='Numer telefonu może mieć max 20 znaków')
        ],
        render_kw={'placeholder': '+48 123 456 789'}
    )

    notes = TextAreaField(
        'Uwagi do zamówienia',
        validators=[Optional(), Length(max=1000)],
        render_kw={'placeholder': 'Dodatkowe uwagi (opcjonalnie)...', 'rows': 3}
    )

    # Optional: Create account
    create_account = BooleanField(
        'Chcę założyć konto',
        default=False
    )

    submit = SubmitField('Złóż zamówienie')


# ====================
# BULK ACTIONS FORM
# ====================

class BulkActionForm(FlaskForm):
    """
    Form for bulk actions on orders.
    Used in admin orders list page.
    """
    action = SelectField(
        'Akcja',
        choices=[
            ('', '-- Wybierz akcję --'),
            ('status', 'Zmień status'),
            ('export', 'Export CSV'),
            ('wms', 'Zabierz do WMS'),
            ('delete', 'Usuń'),
        ],
        validators=[DataRequired(message='Wybierz akcję')]
    )

    # For status change action
    new_status = SelectField(
        'Nowy status',
        choices=[],  # Will be populated dynamically
        validators=[Optional()]
    )

    submit = SubmitField('Wykonaj')


# ====================
# SHIPPING REQUEST FORM
# ====================

class ShippingRequestForm(FlaskForm):
    """
    Form for requesting shipping (client panel).
    Used when client wants to ship ready orders.
    """
    # Hidden field with selected order IDs (comma-separated)
    order_ids = StringField(
        'Order IDs',
        validators=[DataRequired()]
    )

    notes = TextAreaField(
        'Uwagi do wysyłki',
        validators=[Optional(), Length(max=500)],
        render_kw={'placeholder': 'Dodatkowe uwagi dotyczące wysyłki...', 'rows': 3}
    )

    submit = SubmitField('Zleć wysyłkę')


# ====================
# SHIPPING ADDRESS FORM
# ====================

class ShippingAddressForm(FlaskForm):
    """
    Form for delivery address.
    Used in admin order detail page.
    """
    shipping_name = StringField(
        'Imię i nazwisko',
        validators=[Optional(), Length(max=200)],
        render_kw={'placeholder': 'Jan Kowalski'}
    )

    shipping_address = StringField(
        'Adres',
        validators=[Optional(), Length(max=500)],
        render_kw={'placeholder': 'ul. Przykładowa 123/4'}
    )

    shipping_postal_code = StringField(
        'Kod pocztowy',
        validators=[Optional(), Length(max=10)],
        render_kw={'placeholder': '00-000'}
    )

    shipping_city = StringField(
        'Miejscowość',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': 'Warszawa'}
    )

    shipping_voivodeship = SelectField(
        'Województwo',
        choices=[
            ('', '-- Wybierz --'),
            ('dolnośląskie', 'dolnośląskie'),
            ('kujawsko-pomorskie', 'kujawsko-pomorskie'),
            ('lubelskie', 'lubelskie'),
            ('lubuskie', 'lubuskie'),
            ('łódzkie', 'łódzkie'),
            ('małopolskie', 'małopolskie'),
            ('mazowieckie', 'mazowieckie'),
            ('opolskie', 'opolskie'),
            ('podkarpackie', 'podkarpackie'),
            ('podlaskie', 'podlaskie'),
            ('pomorskie', 'pomorskie'),
            ('śląskie', 'śląskie'),
            ('świętokrzyskie', 'świętokrzyskie'),
            ('warmińsko-mazurskie', 'warmińsko-mazurskie'),
            ('wielkopolskie', 'wielkopolskie'),
            ('zachodniopomorskie', 'zachodniopomorskie'),
        ],
        validators=[Optional()]
    )

    shipping_country = StringField(
        'Kraj',
        validators=[Optional(), Length(max=100)],
        default='Polska',
        render_kw={'placeholder': 'Polska'}
    )

    submit = SubmitField('Zapisz adres')


# ====================
# PICKUP POINT FORM
# ====================

class PickupPointForm(FlaskForm):
    """
    Form for pickup point details.
    Used in admin order detail page.
    """
    pickup_courier = SelectField(
        'Kurier',
        choices=[
            ('', '-- Wybierz --'),
            ('inpost', 'InPost'),
            ('dpd', 'DPD Pickup'),
            ('dhl', 'DHL POP'),
            ('poczta', 'Poczta Polska'),
            ('orlen', 'Orlen Paczka'),
            ('ups', 'UPS Access Point'),
            ('fedex', 'FedEx Location'),
            ('inne', 'Inny'),
        ],
        validators=[Optional()]
    )

    pickup_point_id = StringField(
        'ID punktu',
        validators=[Optional(), Length(max=50)],
        render_kw={'placeholder': 'np. WAW123A'}
    )

    pickup_address = StringField(
        'Adres punktu',
        validators=[Optional(), Length(max=500)],
        render_kw={'placeholder': 'ul. Punktowa 1'}
    )

    pickup_postal_code = StringField(
        'Kod pocztowy',
        validators=[Optional(), Length(max=10)],
        render_kw={'placeholder': '00-000'}
    )

    pickup_city = StringField(
        'Miasto',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': 'Warszawa'}
    )

    submit = SubmitField('Zapisz punkt')
