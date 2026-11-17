from flask import Blueprint

gift_cards_bp = Blueprint('gift_cards', __name__)

from . import routes_admin  # noqa: E402,F401
from . import routes_client  # noqa: E402,F401
from . import models  # noqa: E402,F401  # explicit: create_all() potrzebuje modeli
