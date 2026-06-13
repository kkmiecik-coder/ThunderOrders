"""
Mobile API Module
Dedykowane, wersjonowane API dla aplikacji mobilnej (Flutter).
Autoryzacja przez JWT (nie session/CSRF jak web).
"""

from flask import Blueprint

api_mobile_bp = Blueprint('api_mobile', __name__, url_prefix='/api/mobile/v1')

from .validators import ValidationError  # noqa: E402


@api_mobile_bp.errorhandler(ValidationError)
def _validation_error(e):
    from .helpers import json_err
    return json_err('invalid_input', str(e), 400)


from . import models  # noqa: E402,F401  (żeby Alembic wykrył tabelę)

# Trasy importujemy na końcu, aby uniknąć cyklicznych importów.
from . import auth_routes  # noqa: E402,F401
from . import shop_routes  # noqa: E402,F401
from . import cart_routes  # noqa: E402,F401
from . import offers_routes  # noqa: E402,F401
from . import orders_routes  # noqa: E402,F401
from . import payments_routes  # noqa: E402,F401
from . import shipping_routes  # noqa: E402,F401
from . import collection_routes  # noqa: E402,F401

# E9: rejestruje globalny handler Socket.IO `connect` (auth JWT + wiązanie sid→user).
from . import ws  # noqa: E402,F401
