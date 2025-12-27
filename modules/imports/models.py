"""
CSV Import Models
"""
from datetime import datetime, timezone, timedelta
from app import db




def get_local_now():
    """
    Zwraca aktualny czas polski (Europe/Warsaw).
    Używa stałego offsetu +1h (CET) lub +2h (CEST) w zależności od daty.
    Zwraca naive datetime dla porównań z naive datetime w bazie.
    """
    utc_now = datetime.now(timezone.utc)

    # Prosty algorytm DST dla Polski:
    # CEST (UTC+2): ostatnia niedziela marca do ostatniej niedzieli października
    # CET (UTC+1): reszta roku
    year = utc_now.year

    # Ostatnia niedziela marca
    march_last = datetime(year, 3, 31, tzinfo=timezone.utc)
    march_last_sunday = march_last - timedelta(days=(march_last.weekday() + 1) % 7)
    dst_start = march_last_sunday.replace(hour=1)  # 01:00 UTC

    # Ostatnia niedziela października
    oct_last = datetime(year, 10, 31, tzinfo=timezone.utc)
    oct_last_sunday = oct_last - timedelta(days=(oct_last.weekday() + 1) % 7)
    dst_end = oct_last_sunday.replace(hour=1)  # 01:00 UTC

    # Sprawdź czy jesteśmy w czasie letnim
    if dst_start <= utc_now < dst_end:
        offset = timedelta(hours=2)  # CEST
    else:
        offset = timedelta(hours=1)  # CET

    # Zwróć naive datetime w czasie polskim
    return (utc_now + offset).replace(tzinfo=None)

class CsvImport(db.Model):
    """CSV Import model for tracking import history"""
    __tablename__ = 'csv_imports'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    total_rows = db.Column(db.Integer, nullable=False)
    processed_rows = db.Column(db.Integer, default=0)
    successful_rows = db.Column(db.Integer, default=0)
    failed_rows = db.Column(db.Integer, default=0)
    status = db.Column(db.Enum('pending', 'processing', 'completed', 'partial', 'failed'), default='pending')
    match_column = db.Column(db.Enum('id', 'sku', 'ean'), default='sku')
    has_headers = db.Column(db.Boolean, default=True)
    skip_empty_values = db.Column(db.Boolean, default=True)
    column_mapping = db.Column(db.JSON)
    error_log = db.Column(db.JSON)
    temp_file_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=get_local_now)
    completed_at = db.Column(db.DateTime)

    # Relationship
    user = db.relationship('User', backref='csv_imports')

    def __repr__(self):
        return f'<CsvImport {self.filename} - {self.status}>'

    def to_dict(self):
        """Convert to dictionary for JSON response"""
        return {
            'id': self.id,
            'filename': self.filename,
            'user_id': self.user_id,
            'total_rows': self.total_rows,
            'processed_rows': self.processed_rows,
            'successful_rows': self.successful_rows,
            'failed_rows': self.failed_rows,
            'status': self.status,
            'match_column': self.match_column,
            'has_headers': self.has_headers,
            'column_mapping': self.column_mapping,
            'error_log': self.error_log or [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'progress_percent': round((self.processed_rows / self.total_rows * 100) if self.total_rows > 0 else 0)
        }
