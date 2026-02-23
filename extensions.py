"""
Flask Extensions
Centralne miejsce dla wszystkich rozszerzeń Flask
Rozwiązuje problem circular imports
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from flask_executor import Executor
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Inicjalizacja rozszerzeń (bez app - zostanie zrobione w app.py)
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
csrf = CSRFProtect()
executor = Executor()
limiter = Limiter(key_func=get_remote_address, default_limits=[], storage_uri="memory://")
