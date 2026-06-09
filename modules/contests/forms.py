from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, IntegerField, DecimalField,
                     DateTimeLocalField, SelectField)
from wtforms.validators import DataRequired, NumberRange, Optional


class ContestForm(FlaskForm):
    name = StringField('Nazwa', validators=[DataRequired()])
    description = TextAreaField('Opis nagrody', validators=[Optional()])
    image_path = StringField('Grafika', validators=[Optional()])
    prize_product_id = IntegerField('Produkt-nagroda', validators=[Optional()])
    num_winners = IntegerField('Liczba zwycięzców', default=1, validators=[NumberRange(min=1)])
    ticket_min = IntegerField('Min losów', default=1, validators=[NumberRange(min=1)])
    ticket_max = IntegerField('Max losów', default=50, validators=[NumberRange(min=1)])
    cooldown_minutes = IntegerField('Cooldown (min)', default=1440, validators=[NumberRange(min=1)])
    eligibility_min_orders = IntegerField('Min. zamówień', validators=[Optional(), NumberRange(min=0)])
    eligibility_min_total_value = DecimalField('Min. wartość', validators=[Optional(), NumberRange(min=0)])
    eligibility_active_within_days = IntegerField('Aktywny w dniach', validators=[Optional(), NumberRange(min=0)])
    ends_at = DateTimeLocalField('Koniec', format='%Y-%m-%dT%H:%M', validators=[Optional()])

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        if self.ticket_max.data < self.ticket_min.data:
            self.ticket_max.errors.append('Max musi być ≥ min.')
            return False
        return True
