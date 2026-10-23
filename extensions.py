"""
Flask Extensions
Centralne miejsce dla wszystkich rozszerzeń Flask
Rozwiązuje problem circular imports
"""

import pymysql
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from flask_executor import Executor
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO
from flask_jwt_extended import JWTManager

# Inicjalizacja rozszerzeń (bez app - zostanie zrobione w app.py)
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
csrf = CSRFProtect()
executor = Executor()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
socketio = SocketIO()
jwt = JWTManager()


@event.listens_for(Engine, 'connect')
def _ustaw_strefe_utc_w_mariadb(dbapi_connection, connection_record):
    """Ustawia strefę sesji MariaDB na UTC przy każdym nowym połączeniu.

    Kolumny `UTCDateTime` trzymają naiwny UTC, a funkcje SQL typu NOW() muszą zwracać to samo
    niezależnie od ustawień serwera. Dotyczy tylko PyMySQL — SQLite (testy) pomijamy.
    """
    if isinstance(dbapi_connection, pymysql.connections.Connection):
        kursor = dbapi_connection.cursor()
        kursor.execute("SET time_zone = '+00:00'")
        kursor.close()
