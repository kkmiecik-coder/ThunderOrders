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

    phone = StringField(
        'Telefon (opcjonalnie)',
        validators=[
            Length(max=20, message='Numer telefonu jest za długi'),
            Regexp(
                r'^[\d\s\+\-\(\)]*$',
                message='Niepoprawny format numeru telefonu'
            )
        ],
        render_kw={'placeholder': '+48 123 456 789'}
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
