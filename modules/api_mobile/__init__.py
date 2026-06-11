"""
Mobile API Module
Dedykowane, wersjonowane API dla aplikacji mobilnej (Flutter).
Autoryzacja przez JWT (nie session/CSRF jak web).
"""

from flask import Blueprint

api_mobile_bp = Blueprint('api_mobile', __name__, url_prefix='/api/mobile/v1')

from . import models  # noqa: E402,F401  (żeby Alembic wykrył tabelę)

# Trasy importujemy na końcu, aby uniknąć cyklicznych importów.
# from . import auth_routes  # odkomentowane w Task 5
