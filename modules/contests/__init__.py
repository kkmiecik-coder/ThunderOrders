from flask import Blueprint

contests_bp = Blueprint('contests', __name__)

from . import routes  # noqa: E402,F401
from . import models  # noqa: E402,F401  # explicit: routes nie importuje modeli, a create_all() ich potrzebuje
