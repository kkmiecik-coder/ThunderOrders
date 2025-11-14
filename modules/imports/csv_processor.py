"""
CSV Processing Logic
Functions for parsing, validating, and importing products from CSV files
"""
import csv
import os
import chardet
from datetime import datetime
from flask import current_app
from werkzeug.utils import secure_filename
from extensions import db
from modules.products.models import Product
from modules.imports.models import CsvImport
from modules.imports.validators import validate_product_data


# Column mapping dictionary (CSV column name → Product field name)
COLUMN_MAPPING = {
    # Polish
    'nazwa': 'name',
    'sku': 'sku',
    'ean': 'ean',
    'kategoria': 'category_id',
    'producent': 'manufacturer',
    'seria': 'series',
    'cena': 'sale_price',
    'cena_sprzedazy': 'sale_price',
    'cena_zakupu': 'purchase_price',
    'waluta_zakupu': 'purchase_currency',
    'ilosc': 'quantity',
    'dlugosc': 'length',
    'szerokosc': 'width',
    'wysokosc': 'height',
    'waga': 'weight',
    'dostawca': 'supplier_id',
    'tagi': 'tags',
    'opis': 'description',
    'aktywny': 'is_active',
    'grupa_wariantow': 'variant_group',

    # English
    'name': 'name',
    'category': 'category_id',
    'category_id': 'category_id',  # Direct field name
    'manufacturer': 'manufacturer',
    'series': 'series',
    'sale_price': 'sale_price',
    'purchase_price': 'purchase_price',
    'purchase_currency': 'purchase_currency',
    'quantity': 'quantity',
    'length': 'length',
    'width': 'width',
    'height': 'height',
    'weight': 'weight',
    'supplier': 'supplier_id',
    'supplier_id': 'supplier_id',  # Direct field name
    'tags': 'tags',
    'description': 'description',
    'is_active': 'is_active',
    'variant_group': 'variant_group',
}


def detect_encoding(file_path):
    """Detect file encoding using chardet"""
    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read(10000))  # First 10KB
        return result['encoding'] or 'utf-8'


def detect_delimiter(file_path, encoding='utf-8'):
    """Detect CSV delimiter (comma or semicolon)"""
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            sample = f.read(4096)
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
            return delimiter
    except:
        # Fallback to comma
        return ','


def auto_map_columns(csv_columns):
    """
    Auto-map CSV columns to Product fields

    Args:
        csv_columns: List of column names from CSV

    Returns:
        Dictionary {csv_col: product_field}
    """
    print(f"[AUTO MAP] Input columns ({len(csv_columns)}): {csv_columns}")

    mapping = {}
    for col in csv_columns:
        col_lower = col.lower().strip()
        if col_lower in COLUMN_MAPPING:
            mapping[col] = COLUMN_MAPPING[col_lower]
        else:
            mapping[col] = None  # Skip column

    print(f"[AUTO MAP] Output mapping ({len(mapping)}): {list(mapping.keys())}")
    print(f"[AUTO MAP] Mapped fields: {list(mapping.values())}")

    return mapping


def parse_csv_preview(file_path, has_headers=True, max_rows=5):
    """
    Parse CSV and return preview data

    Args:
        file_path: Path to CSV file
        has_headers: Whether first row contains headers
        max_rows: Maximum rows to preview (INCLUDING first row if has_headers)

    Returns:
        Dictionary with columns, preview_rows, total_rows, delimiter, encoding
    """
    encoding = detect_encoding(file_path)
    delimiter = detect_delimiter(file_path, encoding)

    columns = []
    preview_rows = []
    total_rows = 0

    with open(file_path, 'r', encoding=encoding) as f:
        reader = csv.reader(f, delimiter=delimiter)

        # Read first row
        first_row = next(reader, None)
        if not first_row:
            raise ValueError("Plik CSV jest pusty")

        if has_headers:
            columns = [col.strip() for col in first_row]

            # IMPORTANT: Always show first row in preview (as header row data)
            # It will be visually marked as "skipped" in frontend
            preview_rows.append(dict(zip(columns, first_row)))

            # Count total rows (excluding header)
            total_rows = sum(1 for _ in reader)

            # Reset reader to read preview rows
            f.seek(0)
            next(reader)  # Skip header row
        else:
            # Generate column names: Col1, Col2, etc.
            columns = [f"Col{i+1}" for i in range(len(first_row))]
            # Add first row to preview
            preview_rows.append(dict(zip(columns, first_row)))
            total_rows = 1  # Count first row

        # Read preview rows (max_rows - 1 since we already have first row)
        for i, row in enumerate(reader):
            if i >= (max_rows - 1):
                break
            if len(row) == len(columns):
                preview_rows.append(dict(zip(columns, row)))

        # Count remaining rows if not already counted
        if has_headers:
            # Already counted above
            pass
        else:
            # Count remaining rows
            total_rows += sum(1 for _ in reader)

    return {
        'columns': columns,
        'preview_rows': preview_rows,
        'total_rows': total_rows,
        'delimiter': delimiter,
        'encoding': encoding
    }


def map_row_to_product(row, column_mapping):
    """
    Map CSV row to Product data using column_mapping

    Args:
        row: Dictionary {csv_column: value}
        column_mapping: Dictionary {csv_column: product_field}

    Returns:
        Dictionary {product_field: value or None}
    """
    product_data = {}

    for csv_col, product_field in column_mapping.items():
        if product_field and csv_col in row:
            value = row[csv_col]
            # Check if value is empty
            if value is not None and str(value).strip() != '':
                product_data[product_field] = str(value).strip()
            else:
                # Add field with None value (will be handled by update_product based on skip_empty_values)
                product_data[product_field] = None

    return product_data


def match_product(data, match_column):
    """
    Match existing product by ID, SKU, or EAN

    Args:
        data: Product data dictionary
        match_column: 'id', 'sku', or 'ean'

    Returns:
        Product object or None
    """
    if match_column == 'id' and 'id' in data:
        return Product.query.get(int(data['id']))

    elif match_column == 'sku' and 'sku' in data:
        return Product.query.filter_by(sku=data['sku']).first()

    elif match_column == 'ean' and 'ean' in data:
        return Product.query.filter_by(ean=data['ean']).first()

    return None


def create_product(data):
    """
    Create new product from data

    Args:
        data: Validated product data

    Returns:
        Product object
    """
    # Extract tags (many-to-many)
    tags = data.pop('tags', [])

    # Extract variant_group (many-to-many)
    variant_group = data.pop('_variant_group_obj', None)

    # Clean foreign key fields - convert empty strings to None
    if 'category_id' in data and (not data['category_id'] or data['category_id'] == ''):
        data['category_id'] = None
    if 'supplier_id' in data and (not data['supplier_id'] or data['supplier_id'] == ''):
        data['supplier_id'] = None

    # Convert string IDs to integers
    if 'category_id' in data and data['category_id'] is not None:
        try:
            data['category_id'] = int(data['category_id'])
        except (ValueError, TypeError):
            data['category_id'] = None
    if 'supplier_id' in data and data['supplier_id'] is not None:
        try:
            data['supplier_id'] = int(data['supplier_id'])
        except (ValueError, TypeError):
            data['supplier_id'] = None

    # Debug: Print data types
    print(f"[DEBUG] Creating product with data types:")
    for key, value in data.items():
        print(f"  {key}: {type(value).__name__} = {repr(value)[:100]}")

    # Create product
    product = Product(**data)
    db.session.add(product)
    db.session.flush()  # Get ID

    # Add tags
    if tags:
        print(f"[DEBUG] Adding {len(tags)} tags to product")
        for tag in tags:
            print(f"  Tag: {type(tag).__name__} = {repr(tag)}")
            product.tags.append(tag)

    # Add variant group
    if variant_group:
        print(f"[DEBUG] Adding variant group: {variant_group.name}")
        product.variant_groups.append(variant_group)

    return product


def update_product(product, data, skip_empty_values=True):
    """
    Update existing product with new data

    Args:
        product: Existing Product object
        data: New product data
        skip_empty_values: If True, skip updating fields that are None/empty in data

    Returns:
        Updated Product object
    """
    # Extract tags (many-to-many)
    tags = data.pop('tags', None)

    # Extract variant_group (many-to-many)
    variant_group = data.pop('_variant_group_obj', None)

    # Clean foreign key fields - convert empty strings to None
    if 'category_id' in data and (not data['category_id'] or data['category_id'] == ''):
        data['category_id'] = None
    if 'supplier_id' in data and (not data['supplier_id'] or data['supplier_id'] == ''):
        data['supplier_id'] = None

    # Convert string IDs to integers
    if 'category_id' in data and data['category_id'] is not None:
        try:
            data['category_id'] = int(data['category_id'])
        except (ValueError, TypeError):
            data['category_id'] = None
    if 'supplier_id' in data and data['supplier_id'] is not None:
        try:
            data['supplier_id'] = int(data['supplier_id'])
        except (ValueError, TypeError):
            data['supplier_id'] = None

    # Update fields
    for key, value in data.items():
        if hasattr(product, key):
            # If skip_empty_values is True, only update if value is not None
            if skip_empty_values:
                if value is not None:
                    setattr(product, key, value)
            else:
                # Always update, even with None values
                setattr(product, key, value)

    # Update tags if provided (only if not None)
    if tags is not None:
        if skip_empty_values and len(tags) == 0:
            # Don't clear tags if skip_empty_values and no tags provided
            pass
        else:
            product.tags = []  # Clear existing tags
            for tag in tags:
                product.tags.append(tag)

    # Update variant group if provided
    if variant_group is not None:
        if skip_empty_values:
            # Only update if variant_group is not empty
            if not product.variant_groups or len(product.variant_groups) == 0:
                product.variant_groups.append(variant_group)
            # If product already has variant groups, don't override unless explicitly set
        else:
            # Replace existing variant groups
            product.variant_groups = [variant_group]

    product.updated_at = datetime.utcnow()

    return product


def process_csv_import(import_id):
    """
    Main function to process CSV import (runs in background)
    Wraps the actual processing in Flask app context

    Args:
        import_id: CsvImport record ID
    """
    # Import app here to avoid circular imports
    from app import create_app
    app = create_app()

    with app.app_context():
        _process_csv_import_internal(import_id)


def _process_csv_import_internal(import_id):
    """
    Internal function that does the actual CSV import processing

    Args:
        import_id: CsvImport record ID
    """
    csv_import = CsvImport.query.get(import_id)
    if not csv_import:
        print(f"[CSV Import] Import {import_id} not found")
        return

    print(f"[CSV Import] Starting import {import_id} - {csv_import.filename}")

    # Update status to processing
    csv_import.status = 'processing'
    db.session.commit()

    try:
        # Detect encoding and delimiter
        encoding = detect_encoding(csv_import.temp_file_path)
        delimiter = detect_delimiter(csv_import.temp_file_path, encoding)

        # Open CSV file
        with open(csv_import.temp_file_path, 'r', encoding=encoding) as f:
            reader = csv.reader(f, delimiter=delimiter)

            # Skip header if has_headers
            if csv_import.has_headers:
                next(reader, None)

            # Get column names from mapping
            csv_columns = list(csv_import.column_mapping.keys())

            # Process rows in batches
            BATCH_SIZE = 50
            batch_count = 0

            for idx, row in enumerate(reader, start=1):
                try:
                    # Skip empty rows
                    if not row or all(not cell.strip() for cell in row):
                        continue

                    # Map row to dictionary
                    if len(row) != len(csv_columns):
                        raise ValueError(f"Liczba kolumn ({len(row)}) nie pasuje do nagłówka ({len(csv_columns)})")

                    row_dict = dict(zip(csv_columns, row))

                    # Map to product data
                    product_data = map_row_to_product(row_dict, csv_import.column_mapping)

                    # Validate
                    errors = validate_product_data(product_data)
                    if errors:
                        raise ValueError('; '.join(errors))

                    # Match existing product (if match_column set)
                    product = match_product(product_data, csv_import.match_column)

                    if product:
                        # Update existing
                        print(f"[CSV Import] Updating product: {product.name} (ID: {product.id})")
                        update_product(product, product_data, skip_empty_values=csv_import.skip_empty_values)
                    else:
                        # Create new
                        print(f"[CSV Import] Creating product: {product_data.get('name')}")
                        product = create_product(product_data)

                    csv_import.successful_rows += 1

                except Exception as e:
                    # Print full traceback for debugging
                    import traceback
                    print(f"[CSV Import] Full traceback for row {idx}:")
                    traceback.print_exc()
                    # Log error
                    error_entry = {
                        'row': idx,
                        'error': str(e),
                        'data': row_dict if 'row_dict' in locals() else dict(zip(csv_columns, row))
                    }

                    if csv_import.error_log is None:
                        csv_import.error_log = []

                    # Important: Create new list to trigger SQLAlchemy change detection
                    current_errors = csv_import.error_log.copy()
                    current_errors.append(error_entry)
                    csv_import.error_log = current_errors

                    csv_import.failed_rows += 1

                    print(f"[CSV Import] Error on row {idx}: {str(e)}")

                # Update progress
                csv_import.processed_rows = idx

                # Commit in batches
                batch_count += 1
                if batch_count >= BATCH_SIZE:
                    db.session.commit()
                    batch_count = 0
                    print(f"[CSV Import] Progress: {csv_import.processed_rows}/{csv_import.total_rows}")

            # Final commit
            db.session.commit()

        # Determine final status
        if csv_import.failed_rows == 0:
            csv_import.status = 'completed'
        elif csv_import.successful_rows == 0:
            csv_import.status = 'failed'
        else:
            csv_import.status = 'partial'

        csv_import.completed_at = datetime.utcnow()
        db.session.commit()

        print(f"[CSV Import] Import {import_id} finished: {csv_import.status}")
        print(f"[CSV Import] Success: {csv_import.successful_rows}, Failed: {csv_import.failed_rows}")

        # Delete temp file
        if os.path.exists(csv_import.temp_file_path):
            os.remove(csv_import.temp_file_path)
            print(f"[CSV Import] Temp file deleted: {csv_import.temp_file_path}")

    except Exception as e:
        print(f"[CSV Import] Fatal error: {str(e)}")
        csv_import.status = 'failed'
        csv_import.completed_at = datetime.utcnow()

        if csv_import.error_log is None:
            csv_import.error_log = []

        # Important: Create new list to trigger SQLAlchemy change detection
        current_errors = (csv_import.error_log or []).copy()
        current_errors.append({
            'row': 0,
            'error': f"Fatal error: {str(e)}",
            'data': {}
        })
        csv_import.error_log = current_errors

        db.session.commit()
