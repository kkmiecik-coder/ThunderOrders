"""Pliki tymczasowe importu CSV — ścieżki budowane WYŁĄCZNIE po stronie serwera.

Klient dostaje tylko identyfikator (UUID) wydany przy uploadzie; serwer sam
odtwarza z niego ścieżkę i odmawia wszystkiego, co wychodzi poza katalog
tymczasowy importu. Katalog leży poza publicznym static/ (nie da się go
pobrać przez URL).
"""
import os
import uuid

from flask import current_app


def get_temp_dir():
    """Absolutna ścieżka katalogu tymczasowego (nadpisywalna w configu/testach)."""
    configured = current_app.config.get('CSV_IMPORT_TEMP_DIR')
    path = configured or os.path.join(current_app.root_path, 'uploads', 'csv_import_temp')
    return os.path.realpath(path)


def new_temp_file_id():
    return str(uuid.uuid4())


def _normalize_id(temp_file_id):
    """Zwraca kanoniczny UUID albo None, gdy to nie jest poprawny UUID."""
    if not isinstance(temp_file_id, str):
        return None
    try:
        parsed = uuid.UUID(temp_file_id)
    except ValueError:
        return None
    canonical = str(parsed)
    return canonical if canonical == temp_file_id.strip().lower() else None


def build_temp_path(user_id, temp_file_id):
    """Ścieżka pliku dla (user, id) albo None, gdy id niepoprawne."""
    canonical = _normalize_id(temp_file_id)
    if canonical is None:
        return None
    return os.path.join(get_temp_dir(), f'{int(user_id)}_{canonical}.csv')


def is_safe_temp_path(path):
    """True tylko dla zwykłego pliku-ścieżki wewnątrz katalogu tymczasowego."""
    if not path or not isinstance(path, str):
        return False
    temp_dir = get_temp_dir()
    resolved = os.path.realpath(path)
    return os.path.dirname(resolved) == temp_dir


def safe_remove(path):
    """Usuwa plik tylko, gdy leży w katalogu tymczasowym importu. Zwraca True, gdy usunięto."""
    if not is_safe_temp_path(path):
        return False
    resolved = os.path.realpath(path)
    if os.path.isfile(resolved):
        os.remove(resolved)
        return True
    return False
