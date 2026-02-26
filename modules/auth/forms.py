"""
Auth Module - Forms
Formularze autentykacji z walidacją
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    ValidationError,
    Regexp
)

from modules.auth.models import User


class LoginForm(FlaskForm):
    """Formularz logowania"""

    email = StringField(
        'Email',
        validators=[
            DataRequired(message='Email jest wymagany'),
            Email(message='Podaj poprawny adres email')
        ]
    )

    password = PasswordField(
        'Hasło',
        validators=[
            DataRequired(message='Hasło jest wymagane')
        ]
    )

    remember_me = BooleanField('Zapamiętaj mnie')

    submit = SubmitField('Zaloguj się')


class RegisterForm(FlaskForm):
    """Formularz rejestracji"""

    first_name = StringField(
        'Imię',
        validators=[
            DataRequired(message='Imię jest wymagane'),
            Length(min=2, max=100, message='Imię musi mieć od 2 do 100 znaków')
        ],
        render_kw={'placeholder': 'Jan', 'autofocus': True}
    )

    last_name = StringField(
        'Nazwisko',
        validators=[
            DataRequired(message='Nazwisko jest wymagane'),
            Length(min=2, max=100, message='Nazwisko musi mieć od 2 do 100 znaków')
        ],
        render_kw={'placeholder': 'Kowalski'}
    )

    email = StringField(
        'Email',
        validators=[
            DataRequired(message='Email jest wymagany'),
            Email(message='Podaj poprawny adres email'),
            Length(max=255, message='Email jest za długi')
        ],
        render_kw={'placeholder': 'twoj@email.pl'}
    )

    phone_prefix = StringField(
        'Prefix',
        validators=[
            DataRequired(message='Prefix jest wymagany'),
            Regexp(
                r'^\+\d{1,4}$',
                message='Prefix musi zaczynać się od + i zawierać 1-4 cyfry'
            )
        ],
        render_kw={'readonly': True}
    )

    phone_number = StringField(
        'Numer telefonu',
        validators=[
            DataRequired(message='Numer telefonu jest wymagany'),
            Length(min=6, max=15, message='Numer telefonu musi mieć od 6 do 15 cyfr'),
            Regexp(
                r'^\d+$',
                message='Numer telefonu może zawierać tylko cyfry'
            )
        ],
        render_kw={'placeholder': '123456789', 'inputmode': 'tel'}
    )

    password = PasswordField(
        'Hasło',
        validators=[
            DataRequired(message='Hasło jest wymagane'),
            Length(min=8, message='Hasło musi mieć minimum 8 znaków'),
            Regexp(
                r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)',
                message='Hasło musi zawierać: dużą literę, małą literę i cyfrę'
            )
        ],
        render_kw={'placeholder': 'Minimum 8 znaków'}
    )

    password_confirm = PasswordField(
        'Potwierdź hasło',
        validators=[
            DataRequired(message='Potwierdzenie hasła jest wymagane'),
            EqualTo('password', message='Hasła muszą być identyczne')
        ],
        render_kw={'placeholder': 'Wpisz hasło ponownie'}
    )

    submit = SubmitField('Zarejestruj się')

    # Usunięto validate_email - sprawdzanie unikalności przeniesione do routes.py
    # aby uniknąć problemów z application context


class ForgotPasswordForm(FlaskForm):
    """Formularz zapomniałem hasła"""

    email = StringField(
        'Email',
        validators=[
            DataRequired(message='Email jest wymagany'),
            Email(message='Podaj poprawny adres email')
        ],
        render_kw={'placeholder': 'twoj@email.pl', 'autofocus': True}
    )

    submit = SubmitField('Wyślij link do resetowania')


class ResetPasswordForm(FlaskForm):
    """Formularz resetowania hasła"""

    password = PasswordField(
        'Nowe hasło',
        validators=[
            DataRequired(message='Hasło jest wymagane'),
            Length(min=8, message='Hasło musi mieć minimum 8 znaków'),
            Regexp(
                r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)',
                message='Hasło musi zawierać: dużą literę, małą literę i cyfrę'
            )
        ],
        render_kw={'placeholder': 'Minimum 8 znaków', 'autofocus': True}
    )

    password_confirm = PasswordField(
        'Potwierdź nowe hasło',
        validators=[
            DataRequired(message='Potwierdzenie hasła jest wymagane'),
            EqualTo('password', message='Hasła muszą być identyczne')
        ],
        render_kw={'placeholder': 'Wpisz hasło ponownie'}
    )

    submit = SubmitField('Zmień hasło')


class VerificationCodeForm(FlaskForm):
    """Formularz weryfikacji kodem 6-cyfrowym"""

    digit1 = StringField(
        validators=[
            DataRequired(message=''),
            Length(min=1, max=1),
            Regexp(r'^\d$', message='')
        ],
        render_kw={
            'maxlength': '1',
            'pattern': '[0-9]',
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
            'autofocus': True
        }
    )

    digit2 = StringField(
        validators=[
            DataRequired(message=''),
            Length(min=1, max=1),
            Regexp(r'^\d$', message='')
        ],
        render_kw={
            'maxlength': '1',
            'pattern': '[0-9]',
            'inputmode': 'numeric'
        }
    )

    digit3 = StringField(
        validators=[
            DataRequired(message=''),
            Length(min=1, max=1),
            Regexp(r'^\d$', message='')
        ],
        render_kw={
            'maxlength': '1',
            'pattern': '[0-9]',
            'inputmode': 'numeric'
        }
    )

    digit4 = StringField(
        validators=[
            DataRequired(message=''),
            Length(min=1, max=1),
            Regexp(r'^\d$', message='')
        ],
        render_kw={
            'maxlength': '1',
            'pattern': '[0-9]',
            'inputmode': 'numeric'
        }
    )

    digit5 = StringField(
        validators=[
            DataRequired(message=''),
            Length(min=1, max=1),
            Regexp(r'^\d$', message='')
        ],
        render_kw={
            'maxlength': '1',
            'pattern': '[0-9]',
            'inputmode': 'numeric'
        }
    )

    digit6 = StringField(
        validators=[
            DataRequired(message=''),
            Length(min=1, max=1),
            Regexp(r'^\d$', message='')
        ],
        render_kw={
            'maxlength': '1',
            'pattern': '[0-9]',
            'inputmode': 'numeric'
        }
    )

    submit = SubmitField('Weryfikuj')

    def get_full_code(self):
        """Zwraca pełny 6-cyfrowy kod z połączonych pól"""
        return f"{self.digit1.data}{self.digit2.data}{self.digit3.data}{self.digit4.data}{self.digit5.data}{self.digit6.data}"
