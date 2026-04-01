"""
CSV Import Validators
Functions for validating product data during CSV import
"""
import re
from modules.products.models import Category, Tag, Supplier, Manufacturer, ProductSeries, ProductType, VariantGroup


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

    # Validate category (match by ID or name, create if not exists)
    if 'category_id' in data and data['category_id']:
        category = match_or_create_category(data['category_id'])
        data['category_id'] = category.id

    # Validate supplier (match by ID or name, create if not exists)
    if 'supplier_id' in data and data['supplier_id']:
        supplier = match_or_create_supplier(data['supplier_id'])
        data['supplier_id'] = supplier.id

    # Validate manufacturer (match by ID or name, create if not exists)
    if 'manufacturer' in data and data['manufacturer']:
        manufacturer = match_or_create_manufacturer(data['manufacturer'])
        data['manufacturer_id'] = manufacturer.id
        del data['manufacturer']
    elif 'manufacturer' in data:
        del data['manufacturer']

    # Validate series (match by ID or name, create if not exists)
    if 'series' in data and data['series']:
        series = match_or_create_series(data['series'])
        data['series_id'] = series.id
        del data['series']
    elif 'series' in data:
        del data['series']

    # Validate product_type (match by ID or name, create if not exists)
    if 'product_type' in data and data['product_type']:
        product_type = match_or_create_product_type(data['product_type'])
        data['product_type_id'] = product_type.id
        del data['product_type']
    elif 'product_type' in data:
        del data['product_type']

    # Validate tags (match by ID or name, create if missing)
    if 'tags' in data and data['tags']:
        tag_names = [t.strip() for t in str(data['tags']).split(',') if t.strip()]
        tag_objects = []
        for tag_name in tag_names:
            tag = match_or_create_tag(tag_name)
            tag_objects.append(tag)
        data['tags'] = tag_objects

    # Validate sizes (match by ID or name, create if missing)
    if 'sizes' in data and data['sizes']:
        size_names = [s.strip() for s in str(data['sizes']).split(',') if s.strip()]
        size_objects = []
        for size_name in size_names:
            size = match_or_create_size(size_name)
            size_objects.append(size)
        data['sizes'] = size_objects

    # Validate variant_group (match by ID or name, create if missing)
    if 'variant_group' in data:
        if data['variant_group']:  # Only create if value is not empty
            variant_group = match_or_create_variant_group(data['variant_group'])
            # Store in special key to handle after product creation
            data['_variant_group_obj'] = variant_group
        # Always remove from data so it doesn't get passed to Product constructor
        del data['variant_group']

    # Required: sale_price (NOT NULL in database)
    if 'sale_price' in data and (data['sale_price'] is None or str(data['sale_price']).strip() == ''):
        errors.append("Cena sprzedaży jest wymagana")

    # Validate numeric fields
    numeric_fields = {
        'sale_price': 'Cena sprzedaży',
        'purchase_price': 'Cena zakupu',
        'purchase_price_pln': 'Cena zakupu (PLN)',
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


def match_or_create_category(value):
    """Match category by ID or name (case-insensitive), create if not exists"""
    from extensions import db

    if not value:
        return None

    # Try match by ID
    if str(value).isdigit():
        category = Category.query.get(int(value))
        if category:
            return category

    # Try match by name (case-insensitive)
    value_str = str(value).strip()
    category = Category.query.filter(Category.name.ilike(value_str)).first()

    if category:
        return category

    # Create new category
    category = Category(name=value_str)
    db.session.add(category)
    db.session.flush()

    return category


def match_or_create_supplier(value):
    """Match supplier by ID or name (case-insensitive), create if not exists"""
    from extensions import db

    if not value:
        return None

    # Try match by ID
    if str(value).isdigit():
        supplier = Supplier.query.get(int(value))
        if supplier:
            return supplier

    # Try match by name (case-insensitive)
    value_str = str(value).strip()
    supplier = Supplier.query.filter(Supplier.name.ilike(value_str)).first()

    if supplier:
        return supplier

    # Create new supplier
    supplier = Supplier(name=value_str)
    db.session.add(supplier)
    db.session.flush()

    return supplier


def match_or_create_product_type(value):
    """Match product type by ID, slug, or name (case-insensitive), create if not exists"""
    from extensions import db

    if not value:
        return None

    # Try match by ID
    if str(value).isdigit():
        product_type = ProductType.query.get(int(value))
        if product_type:
            return product_type

    value_str = str(value).strip()

    # Try match by slug (exact, lowercase)
    slug_value = re.sub(r'[^a-z0-9]+', '-', value_str.lower()).strip('-')
    product_type = ProductType.query.filter_by(slug=slug_value).first()
    if product_type:
        return product_type

    # Try match by name (case-insensitive)
    product_type = ProductType.query.filter(ProductType.name.ilike(value_str)).first()
    if product_type:
        return product_type

    # Create new product type with generated slug
    product_type = ProductType(name=value_str, slug=slug_value)
    db.session.add(product_type)
    db.session.flush()

    return product_type


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

    # Create new tag
    tag = Tag(name=value_str)
    db.session.add(tag)
    db.session.flush()

    return tag


def match_or_create_size(value):
    """
    Match size by ID or name, create new if not exists
    """
    from extensions import db
    from modules.products.models import Size

    if not value:
        return None

    # Try match by ID
    if str(value).isdigit():
        size = Size.query.get(int(value))
        if size:
            return size

    # Try match by name (case-insensitive)
    value_str = str(value).strip()
    size = Size.query.filter(Size.name.ilike(value_str)).first()

    if size:
        return size

    # Create new size
    size = Size(name=value_str)
    db.session.add(size)
    db.session.flush()

    return size


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
    db.session.flush()

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
    db.session.flush()

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
    db.session.flush()

    return variant_group
