"""Walidacja parametrów wejścia mobilnego API (query stringi i body JSON)."""


class ValidationError(ValueError):
    """Niepoprawny parametr wejścia — mapowany na 400 invalid_input."""


def parse_int(value, field, required=False, default=None, min_value=None, max_value=None):
    """str/num -> int z zakresem; None/'' -> default (lub błąd gdy required)."""
    if value is None or value == '':
        if required:
            raise ValidationError(f'Pole {field} jest wymagane.')
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f'Pole {field} musi być liczbą całkowitą.')
    if min_value is not None and result < min_value:
        raise ValidationError(f'Pole {field} musi być >= {min_value}.')
    if max_value is not None and result > max_value:
        raise ValidationError(f'Pole {field} musi być <= {max_value}.')
    return result
