"""Pupile (tamagotchi) dla klientów.

Spec: docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md
Etap 1: tylko modele, konfiguracja i reguły czasu. Trasy (routes.py, admin_routes.py)
dochodzą w etapie 4 — blueprinty rejestrujemy już teraz, żeby create_all() i Alembic
widziały modele.
"""
from flask import Blueprint

pets_bp = Blueprint('pets', __name__, url_prefix='/client/pupile')
pets_admin_bp = Blueprint('pets_admin', __name__, url_prefix='/admin/pupile')

from . import models  # noqa: E402,F401  (create_all() i Alembic potrzebują modeli)
from . import routes  # noqa: E402,F401
