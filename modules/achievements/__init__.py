from flask import Blueprint

achievements_bp = Blueprint('achievements', __name__)

from . import routes  # noqa: E402, F401
