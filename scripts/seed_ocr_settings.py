"""Seed OCR settings into Settings table."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db
from modules.auth.models import Settings

app = create_app()
with app.app_context():
    settings = [
        ('ocr_enabled', 'false', 'boolean', 'Włącz/wyłącz automatyczną weryfikację OCR'),
        ('ocr_auto_approve_threshold', '90', 'integer', 'Próg auto-akceptacji OCR (0-100)'),
        ('ocr_suggest_threshold', '60', 'integer', 'Próg sugestii OCR (0-100)'),
    ]
    for key, value, type_, desc in settings:
        existing = Settings.query.filter_by(key=key).first()
        if not existing:
            s = Settings(key=key, value=value, type=type_, description=desc)
            db.session.add(s)
            print(f"Added: {key} = {value}")
        else:
            print(f"Exists: {key} = {existing.value}")
    db.session.commit()
    print("Done.")
