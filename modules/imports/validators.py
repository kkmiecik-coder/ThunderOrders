"""
CSV Import Validators
Functions for validating product data during CSV import
"""
from modules.products.models import Category, Tag, Supplier, Manufacturer, ProductSeries, VariantGroup


def validate_product_data(data):
    """
    Validate product data from CSV row

    Args:
        data: Dictionary with product fields

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Required: name
    if not data.get('name') or not str(data.get('name')).strip():
        errors.append("Nazwa produktu jest wymagana")

    # Validate category (match by ID or name)
    if 'category_id' in data and data['category_id']:
        category = match_category(data['category_id'])
        if not category:
            errors.append(f"Kategoria '{data['category_id']}' nie istnieje")
        else:
            data['category_id'] = category.id

    # Validate supplier (match by ID or name)
    if 'supplier_id' in data and data['supplier_id']:
        supplier = match_supplier(data['supplier_id'])
        if not supplier:
            errors.append(f"Dostawca '{data['supplier_id']}' nie istnieje")
        else:
            data['supplier_id'] = supplier.id

    # Validate manufacturer (match by ID or name, create if not exists)
    if 'manufacturer' in data and data['manufacturer']:
        manufacturer = match_or_create_manufacturer(data['manufacturer'])
        data['manufacturer'] = manufacturer

    # Validate series (match by ID or name, create if not exists)
    if 'series' in data and data['series']:
        series = match_or_create_series(data['series'])
        data['series'] = series

    # Validate tags (match by ID or name, create if missing)
    if 'tags' in data and data['tags']:
        tag_names = [t.strip() for t in str(data['tags']).split(',') if t.strip()]
        tag_objects = []
        for tag_name in tag_names:
            tag = match_or_create_tag(tag_name)
            tag_objects.append(tag)
        data['tags'] = tag_objects

    # Validate variant_group (match by ID or name, create if missing)
    if 'variant_group' in data:
        if data['variant_group']:  # Only create if value is not empty
            variant_group = match_or_create_variant_group(data['variant_group'])
            # Store in special key to handle after product creation
            data['_variant_group_obj'] = variant_group
        # Always remove from data so it doesn't get passed to Product constructor
        del data['variant_group']

    # Validate numeric fields
    numeric_fields = {
        'sale_price': 'Cena sprzedaży',
        'purchase_price': 'Cena zakupu',
        'quantity': 'Ilość',
        'length': 'Długość',
        'width': 'Szerokość',
        'height': 'Wysokość',
        'weight': 'Waga',
        'margin': 'Marża'
    }

    for field, label in numeric_fields.items():
        if field in data and data[field] is not None and data[field] != '':
            try:
                # Convert to float or int
                value = str(data[field]).replace(',', '.')  # Handle comma as decimal separator
                if '.' in value:
                    data[field] = float(value)
                else:
                    data[field] = int(value)

                # Validate positive values
                if data[field] < 0:
                    errors.append(f"{label} musi być wartością dodatnią")

            except (ValueError, TypeError):
                errors.append(f"Nieprawidłowa wartość dla pola '{label}': {data[field]}")

    # Validate boolean fields
    boolean_fields = ['is_active']
    for field in boolean_fields:
        if field in data and data[field] is not None:
            if isinstance(data[field], bool):
                pass  # Already boolean
            elif str(data[field]).lower() in ['true', '1', 'tak', 'yes']:
                data[field] = True
            elif str(data[field]).lower() in ['false', '0', 'nie', 'no']:
                data[field] = False
            else:
                errors.append(f"Nieprawidłowa wartość dla pola '{field}': {data[field]}")

    # Validate purchase_currency
    if 'purchase_currency' in data and data['purchase_currency']:
        valid_currencies = ['PLN', 'KRW', 'USD']
        if data['purchase_currency'].upper() not in valid_currencies:
            errors.append(f"Nieprawidłowa waluta: {data['purchase_currency']}. Dostępne: PLN, KRW, USD")
        else:
            data['purchase_currency'] = data['purchase_currency'].upper()

    # Validate EAN (13 digits if provided)
    if 'ean' in data and data['ean']:
        ean = str(data['ean']).strip()
        if not ean.isdigit() or len(ean) != 13:
            errors.append(f"EAN musi mieć dokładnie 13 cyfr: {ean}")

    return errors


def match_category(value):
    """Match category by ID or name (case-insensitive)"""
    if not value:
        return None

    # Try match by ID
    if str(value).isdigit():
        return Category.query.get(int(value))

    # Try match by name (case-insensitive)
    return Category.query.filter(Category.name.ilike(str(value).strip())).first()


def match_supplier(value):
    """Match supplier by ID or name (case-insensitive)"""
    if not value:
        return None

    # Try match by ID
    if str(value).isdigit():
        return Supplier.query.get(int(value))

    # Try match by name (case-insensitive)
    return Supplier.query.filter(Supplier.name.ilike(str(value).strip())).first()


def match_or_create_tag(value):
    """
    Match tag by ID or name, create new if not exists

    Args:
        value: Tag ID or name

    Returns:
        Tag object
    """
    from extensions import db

    if not value:
        return None

    # Try match by ID
    if str(value).isdigit():
        tag = Tag.query.get(int(value))
        if tag:
            return tag

    # Try match by name (case-insensitive)
    value_str = str(value).strip()
    tag = Tag.query.filter(Tag.name.ilike(value_str)).first()

    if tag:
        return tag

    # Create new tag - don't flush, will be committed with product
    tag = Tag(name=value_str)
    db.session.add(tag)
    # Don't flush here - let the main transaction handle it

    return tag


def match_or_create_manufacturer(value):
    """
    Match manufacturer by ID or name, create new if not exists

    Args:
        value: Manufacturer ID or name

    Returns:
        Manufacturer object
    """
    from extensions import db

    if not value:
        return None

    # Try match by ID
    if str(value).isdigit():
        manufacturer = Manufacturer.query.get(int(value))
        if manufacturer:
            return manufacturer

    # Try match by name (case-insensitive)
    value_str = str(value).strip()
    manufacturer = Manufacturer.query.filter(Manufacturer.name.ilike(value_str)).first()

    if manufacturer:
        return manufacturer

    # Create new manufacturer
    manufacturer = Manufacturer(name=value_str)
    db.session.add(manufacturer)

    return manufacturer


def match_or_create_series(value):
    """
    Match product series by ID or name, create new if not exists

    Args:
        value: Series ID or name

    Returns:
        ProductSeries object
    """
    from extensions import db

    if not value:
        return None

    # Try match by ID
    if str(value).isdigit():
        series = ProductSeries.query.get(int(value))
        if series:
            return series

    # Try match by name (case-insensitive)
    value_str = str(value).strip()
    series = ProductSeries.query.filter(ProductSeries.name.ilike(value_str)).first()

    if series:
        return series

    # Create new series
    series = ProductSeries(name=value_str)
    db.session.add(series)

    return series


def match_or_create_variant_group(value):
    """
    Match variant group by ID or name, create new if not exists

    Args:
        value: VariantGroup ID or name

    Returns:
        VariantGroup object
    """
    from extensions import db

    if not value:
        return None

    # Try match by ID
    if str(value).isdigit():
        variant_group = VariantGroup.query.get(int(value))
        if variant_group:
            return variant_group

    # Try match by name (case-insensitive)
    value_str = str(value).strip()
    variant_group = VariantGroup.query.filter(VariantGroup.name.ilike(value_str)).first()

    if variant_group:
        return variant_group

    # Create new variant group
    variant_group = VariantGroup(name=value_str)
    db.session.add(variant_group)

    return variant_group
