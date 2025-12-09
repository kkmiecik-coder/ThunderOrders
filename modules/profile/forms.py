"""
Profile Module - Forms
Formularze dla zarządzania avatarami
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, MultipleFileField
from wtforms.validators import DataRequired, Length, Regexp


class AvatarSeriesForm(FlaskForm):
    """Formularz tworzenia/edycji serii avatarów"""

    name = StringField('Nazwa serii', validators=[
        DataRequired(message='Nazwa serii jest wymagana'),
        Length(min=2, max=100, message='Nazwa musi mieć od 2 do 100 znaków')
    ])

    slug = StringField('Slug (URL)', validators=[
        DataRequired(message='Slug jest wymagany'),
        Length(min=2, max=100, message='Slug musi mieć od 2 do 100 znaków'),
        Regexp(r'^[a-z0-9-]+$', message='Slug może zawierać tylko małe litery, cyfry i myślniki')
    ])


class AvatarUploadForm(FlaskForm):
    """Formularz uploadu avatarów do serii"""

    files = MultipleFileField('Pliki avatarów', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'],
                    'Dozwolone formaty: JPG, PNG, GIF, WEBP')
    ])
