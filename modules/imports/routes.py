"""
CSV Import Routes
API endpoints for CSV import functionality
"""
import os
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from extensions import db
from modules.imports.models import CsvImport
from modules.imports.csv_processor import (
    parse_csv_preview,
    auto_map_columns,
    process_csv_import
)
from utils.decorators import role_required


imports_bp = Blueprint('imports', __name__)


# Configuration
UPLOAD_FOLDER = 'static/uploads/csv/temp'
ALLOWED_EXTENSIONS = {'csv'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@imports_bp.route('/admin/imports/csv/upload', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def upload_csv():
    """
    Upload CSV file and return preview

    Returns:
        JSON with temp_file_id, columns, preview_rows, total_rows
    """
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'Brak pliku'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'success': False, 'error': 'Nie wybrano pliku'}), 400

        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Nieprawidłowy format pliku. Dozwolone: CSV'}), 400

        # Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        if file_size > MAX_FILE_SIZE:
            return jsonify({'success': False, 'error': 'Plik za duży. Maksymalny rozmiar: 5MB'}), 400

        # Create upload folder if not exists
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)

        # Generate unique filename
        temp_file_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)
        temp_filename = f"{current_user.id}_{temp_file_id}_{filename}"
        temp_path = os.path.join(UPLOAD_FOLDER, temp_filename)

        # Save file
        file.save(temp_path)

        # Parse CSV preview
        preview_data = parse_csv_preview(temp_path, has_headers=True, max_rows=5)

        # Auto-map columns
        suggested_mapping = auto_map_columns(preview_data['columns'])

        return jsonify({
            'success': True,
            'temp_file_id': temp_file_id,
            'temp_path': temp_path,
            'columns': preview_data['columns'],
            'preview_rows': preview_data['preview_rows'],
            'total_rows': preview_data['total_rows'],
            'delimiter': preview_data['delimiter'],
            'encoding': preview_data['encoding'],
            'suggested_mapping': suggested_mapping
        })

    except Exception as e:
        # Clean up temp file if exists
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)

        return jsonify({'success': False, 'error': f'Błąd parsowania pliku: {str(e)}'}), 500


@imports_bp.route('/admin/imports/csv/start', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def start_import():
    """
    Start CSV import process

    Request body:
        - temp_file_path: Path to temp file
        - has_headers: Boolean
        - match_column: 'id', 'sku', or 'ean'
        - column_mapping: Dictionary {csv_col: product_field}
        - total_rows: Number of rows to import

    Returns:
        JSON with import_id
    """
    try:
        data = request.get_json()

        temp_file_path = data.get('temp_file_path')
        has_headers = data.get('has_headers', True)
        skip_empty_values = data.get('skip_empty_values', True)
        match_column = data.get('match_column', 'sku')
        column_mapping = data.get('column_mapping', {})
        total_rows = data.get('total_rows', 0)
        filename = data.get('filename', 'import.csv')

        # Validate
        if not temp_file_path or not os.path.exists(temp_file_path):
            return jsonify({'success': False, 'error': 'Plik tymczasowy nie istnieje'}), 400

        if not column_mapping:
            return jsonify({'success': False, 'error': 'Brak mapowania kolumn'}), 400

        # Check if at least 'name' field is mapped
        if 'name' not in column_mapping.values():
            return jsonify({'success': False, 'error': 'Pole "name" (nazwa) jest wymagane'}), 400

        # Clean up old imports (keep last 15)
        old_imports = CsvImport.query.filter_by(user_id=current_user.id)\
                                      .order_by(CsvImport.created_at.desc())\
                                      .offset(15).all()

        for old_import in old_imports:
            # Delete temp file if exists
            if old_import.temp_file_path and os.path.exists(old_import.temp_file_path):
                os.remove(old_import.temp_file_path)
            db.session.delete(old_import)

        db.session.commit()

        # Create CsvImport record
        csv_import = CsvImport(
            filename=filename,
            user_id=current_user.id,
            total_rows=total_rows,
            status='pending',
            match_column=match_column,
            has_headers=has_headers,
            skip_empty_values=skip_empty_values,
            column_mapping=column_mapping,
            error_log=[],
            temp_file_path=temp_file_path
        )

        db.session.add(csv_import)
        db.session.commit()

        # Start background import with Flask-Executor
        from extensions import executor
        executor.submit(process_csv_import, csv_import.id)

        return jsonify({
            'success': True,
            'import_id': csv_import.id,
            'message': 'Import rozpoczęty'
        })

    except Exception as e:
        return jsonify({'success': False, 'error': f'Błąd rozpoczynania importu: {str(e)}'}), 500


@imports_bp.route('/admin/imports/csv/status/<int:import_id>', methods=['GET'])
@login_required
@role_required('admin', 'mod')
def get_import_status(import_id):
    """
    Get import status (for polling)

    Returns:
        JSON with status, processed_rows, total_rows, progress_percent
    """
    try:
        csv_import = CsvImport.query.get_or_404(import_id)

        # Check if user owns this import or is admin
        if csv_import.user_id != current_user.id and current_user.role != 'admin':
            return jsonify({'success': False, 'error': 'Brak dostępu'}), 403

        return jsonify({
            'success': True,
            **csv_import.to_dict()
        })

    except Exception as e:
        return jsonify({'success': False, 'error': f'Błąd pobierania statusu: {str(e)}'}), 500


@imports_bp.route('/admin/imports/csv/history', methods=['GET'])
@login_required
@role_required('admin', 'mod')
def get_import_history():
    """
    Get import history (last 15 imports)

    Returns:
        JSON with list of imports
    """
    try:
        imports = CsvImport.query.filter_by(user_id=current_user.id)\
                                  .order_by(CsvImport.created_at.desc())\
                                  .limit(15).all()

        return jsonify({
            'success': True,
            'imports': [imp.to_dict() for imp in imports]
        })

    except Exception as e:
        return jsonify({'success': False, 'error': f'Błąd pobierania historii: {str(e)}'}), 500


@imports_bp.route('/admin/imports/csv/details/<int:import_id>', methods=['GET'])
@login_required
@role_required('admin', 'mod')
def get_import_details(import_id):
    """
    Get detailed import information including error log

    Returns:
        JSON with full import details
    """
    try:
        csv_import = CsvImport.query.get_or_404(import_id)

        # Check if user owns this import or is admin
        if csv_import.user_id != current_user.id and current_user.role != 'admin':
            return jsonify({'success': False, 'error': 'Brak dostępu'}), 403

        return jsonify({
            'success': True,
            **csv_import.to_dict()
        })

    except Exception as e:
        return jsonify({'success': False, 'error': f'Błąd pobierania szczegółów: {str(e)}'}), 500
