"""
Product Routes
CRUD operations for products, categories, tags, and suppliers
"""

from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_
from werkzeug.utils import secure_filename
import os
import shutil
from uuid import uuid4

from modules.products import products_bp
from modules.products.models import Product, Category, Tag, Supplier, ProductImage, product_tags
from modules.products.forms import (
    ProductForm, CategoryForm, TagForm, SupplierForm,
    QuickTagForm, ProductSearchForm
)
from extensions import db, csrf
from utils.decorators import role_required


# ==========================================
# Products List
# ==========================================
@products_bp.route('/', methods=['GET'])
@login_required
@role_required('admin', 'mod')
def list_products():
    """Display list of all products with search and filters"""

    # Initialize search form
    search_form = ProductSearchForm(request.args)

    # Base query
    query = Product.query

    # Apply search filter
    if search_form.search.data:
        search_term = f"%{search_form.search.data}%"
        query = query.filter(
            or_(
                Product.name.like(search_term),
                Product.sku.like(search_term),
                Product.ean.like(search_term)
            )
        )

    # Apply category filter
    if search_form.category_id.data:
        query = query.filter(Product.category_id == search_form.category_id.data)

    # Apply manufacturer filter
    if search_form.manufacturer.data:
        query = query.filter(Product.manufacturer_id == search_form.manufacturer.data)

    # Apply series filter
    if search_form.series.data:
        query = query.filter(Product.series_id == search_form.series.data)

    # Apply tags filter
    if search_form.tags.data:
        for tag_id in search_form.tags.data:
            query = query.filter(Product.tags.any(Tag.id == tag_id))

    # Apply status filter
    if search_form.is_active.data != '':
        query = query.filter(Product.is_active == (search_form.is_active.data == '1'))

    # Apply stock filter
    if search_form.stock_filter.data:
        if search_form.stock_filter.data == 'in_stock':
            query = query.filter(Product.quantity > 0)
        elif search_form.stock_filter.data == 'out_of_stock':
            query = query.filter(Product.quantity == 0)
        elif search_form.stock_filter.data == 'low_stock':
            query = query.filter(Product.quantity < 10, Product.quantity > 0)

    # Sorting
    sort_by = request.args.get('sort', 'created_at')
    sort_order = request.args.get('order', 'desc')

    if sort_by == 'name':
        query = query.order_by(Product.name.asc() if sort_order == 'asc' else Product.name.desc())
    elif sort_by == 'sku':
        query = query.order_by(Product.sku.asc() if sort_order == 'asc' else Product.sku.desc())
    elif sort_by == 'price':
        query = query.order_by(Product.sale_price.asc() if sort_order == 'asc' else Product.sale_price.desc())
    elif sort_by == 'quantity':
        query = query.order_by(Product.quantity.asc() if sort_order == 'asc' else Product.quantity.desc())
    else:  # created_at (default)
        query = query.order_by(Product.created_at.desc() if sort_order == 'desc' else Product.created_at.asc())

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)  # Get per_page from URL params, default 50

    # Validate per_page (must be one of allowed values)
    allowed_per_page = [10, 25, 50, 100, 150]
    if per_page not in allowed_per_page:
        per_page = 50

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    products = pagination.items

    return render_template(
        'admin/warehouse/products_list.html',
        products=products,
        pagination=pagination,
        search_form=search_form,
        current_sort=sort_by,
        current_order=sort_order
    )


# ==========================================
# Create Product
# ==========================================
@products_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def create_product():
    """Create a new product"""

    form = ProductForm()

    # Check if this is an AJAX request (for modal)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('modal') == '1'

    # Initialize form with default values from settings (only on GET request)
    if request.method == 'GET':
        from modules.auth.models import Settings
        form.purchase_currency.data = Settings.get_value('warehouse_default_purchase_currency', 'PLN')
        form.margin.data = Settings.get_value('warehouse_default_margin', 30)

    if form.validate_on_submit():
        # Create new product
        product = Product(
            name=form.name.data,
            sku=form.sku.data if form.sku.data else None,
            ean=form.ean.data if form.ean.data else None,
            category_id=form.category_id.data if form.category_id.data != 0 else None,
            manufacturer_id=form.manufacturer_id.data if form.manufacturer_id.data != 0 else None,
            series_id=form.series_id.data if form.series_id.data != 0 else None,
            product_type_id=form.product_type_id.data if form.product_type_id.data != 0 else None,
            length=form.length.data,
            width=form.width.data,
            height=form.height.data,
            weight=form.weight.data,
            sale_price=form.sale_price.data,
            purchase_price=form.purchase_price.data,
            purchase_currency=form.purchase_currency.data,
            purchase_price_pln=form.purchase_price_pln.data,
            margin=form.margin.data,
            quantity=form.quantity.data,
            supplier_id=form.supplier_id.data if form.supplier_id.data != 0 and current_user.role == 'admin' else None,
            description=form.description.data,
            is_active=form.is_active.data
        )

        # Calculate margin
        product.calculate_margin()

        # Add tags
        if form.tags.data:
            for tag_id in form.tags.data:
                tag = Tag.query.get(tag_id)
                if tag:
                    product.tags.append(tag)

        try:
            db.session.add(product)
            db.session.commit()

            # Process image uploads from 10 individual slots
            from utils.image_processor import process_upload, allowed_file
            upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'products')
            uploaded_count = 0

            for slot_num in range(1, 11):  # Slots 1-10
                file_key = f'product_image_{slot_num}'
                if file_key in request.files:
                    file = request.files[file_key]
                    if file and file.filename and allowed_file(file.filename):
                        try:
                            # Process upload (save original + compressed)
                            image_data = process_upload(file, upload_folder)

                            # Create ProductImage record
                            # First slot (#1) is always primary, others are not
                            is_primary = (slot_num == 1 and product.images.count() == 0)

                            product_image = ProductImage(
                                product_id=product.id,
                                filename=image_data['filename'],
                                path_original=image_data['path_original'],
                                path_compressed=image_data['path_compressed'],
                                is_primary=is_primary,
                                sort_order=slot_num  # Use slot number as sort order
                            )

                            db.session.add(product_image)
                            uploaded_count += 1

                        except Exception as e:
                            current_app.logger.error(f"Error uploading image for slot {slot_num}: {str(e)}")
                            continue

            if uploaded_count > 0:
                db.session.commit()

            # For AJAX requests (modal), return JSON response
            if is_ajax:
                message = f'Produkt "{product.name}" został utworzony pomyślnie.'
                if uploaded_count > 0:
                    message += f' Przesłano {uploaded_count} zdjęć.'

                return jsonify({
                    'success': True,
                    'message': message,
                    'product_id': product.id,
                    'redirect': url_for('products.list_products')
                })

            # For normal requests, use flash
            flash(f'Produkt "{product.name}" został utworzony pomyślnie.', 'success')
            if uploaded_count > 0:
                flash(f'Przesłano {uploaded_count} zdjęć.', 'success')
            return redirect(url_for('products.edit_product', product_id=product.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Błąd podczas tworzenia produktu: {str(e)}', 'error')

            # For AJAX requests, return JSON error
            if is_ajax:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 400

    # Get max images from settings
    from modules.auth.models import Settings
    max_images = Settings.get_value('warehouse_image_max_per_product', 10)

    # If validation failed - return modal template for AJAX requests, full page for normal requests
    template = 'admin/warehouse/product_form_modal.html' if is_ajax else 'admin/warehouse/product_form.html'

    # Get price rounding mode from settings
    price_rounding = Settings.get_value('warehouse_price_rounding', 'full')

    return render_template(template, form=form, product=None, mode='create', max_images=max_images, price_rounding=price_rounding)


# ==========================================
# Edit Product
# ==========================================
@products_bp.route('/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def edit_product(product_id):
    """Edit existing product"""

    product = Product.query.get_or_404(product_id)
    form = ProductForm(obj=product)

    # Check if this is an AJAX request (for modal)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('modal') == '1'

    # Set product_id for SKU validation
    form.product_id = product_id

    # Pre-select tags
    if request.method == 'GET':
        form.tags.data = [tag.id for tag in product.tags]

    if form.validate_on_submit():
        # Update product fields
        product.name = form.name.data
        product.sku = form.sku.data if form.sku.data else None
        product.ean = form.ean.data if form.ean.data else None
        product.category_id = form.category_id.data if form.category_id.data != 0 else None
        product.manufacturer_id = form.manufacturer_id.data if form.manufacturer_id.data != 0 else None
        product.series_id = form.series_id.data if form.series_id.data != 0 else None
        product.product_type_id = form.product_type_id.data if form.product_type_id.data != 0 else None
        product.length = form.length.data
        product.width = form.width.data
        product.height = form.height.data
        product.weight = form.weight.data
        product.sale_price = form.sale_price.data
        product.purchase_price = form.purchase_price.data
        product.purchase_currency = form.purchase_currency.data
        product.purchase_price_pln = form.purchase_price_pln.data
        product.margin = form.margin.data
        product.quantity = form.quantity.data
        product.description = form.description.data
        product.is_active = form.is_active.data

        # Only admin can change supplier
        if current_user.role == 'admin':
            product.supplier_id = form.supplier_id.data if form.supplier_id.data != 0 else None

        # Calculate margin
        product.calculate_margin()

        # Update tags
        product.tags = []
        if form.tags.data:
            for tag_id in form.tags.data:
                tag = Tag.query.get(tag_id)
                if tag:
                    product.tags.append(tag)

        try:
            db.session.commit()

            # Process image uploads from 10 individual slots
            from utils.image_processor import process_upload, allowed_file
            upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'products')
            uploaded_count = 0

            for slot_num in range(1, 11):  # Slots 1-10
                file_key = f'product_image_{slot_num}'
                if file_key in request.files:
                    file = request.files[file_key]
                    if file and file.filename and allowed_file(file.filename):
                        try:
                            # Check if there's already an image in this slot
                            existing_image = ProductImage.query.filter_by(
                                product_id=product.id,
                                sort_order=slot_num
                            ).first()

                            # If exists, delete the old image files and DB record
                            if existing_image:
                                from utils.image_processor import delete_image_files
                                delete_image_files(existing_image.path_original, existing_image.path_compressed)
                                db.session.delete(existing_image)

                            # Process upload (save original + compressed)
                            image_data = process_upload(file, upload_folder)

                            # Create new ProductImage record
                            # First slot (#1) is always primary
                            is_primary = (slot_num == 1)

                            product_image = ProductImage(
                                product_id=product.id,
                                filename=image_data['filename'],
                                path_original=image_data['path_original'],
                                path_compressed=image_data['path_compressed'],
                                is_primary=is_primary,
                                sort_order=slot_num  # Use slot number as sort order
                            )

                            db.session.add(product_image)
                            uploaded_count += 1

                        except Exception as e:
                            current_app.logger.error(f"Error uploading image for slot {slot_num}: {str(e)}")
                            continue

            if uploaded_count > 0:
                db.session.commit()

            # For AJAX requests (modal), return JSON response
            if is_ajax:
                message = f'Produkt "{product.name}" został zaktualizowany.'
                if uploaded_count > 0:
                    message += f' Przesłano {uploaded_count} zdjęć.'

                return jsonify({
                    'success': True,
                    'message': message,
                    'product_id': product.id,
                    'redirect': url_for('products.list_products')
                })

            # For normal requests, use flash
            flash(f'Produkt "{product.name}" został zaktualizowany.', 'success')
            if uploaded_count > 0:
                flash(f'Przesłano {uploaded_count} zdjęć.', 'success')
            return redirect(url_for('products.edit_product', product_id=product.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Błąd podczas aktualizacji produktu: {str(e)}', 'error')

            # For AJAX requests, return JSON error
            if is_ajax:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 400

    # Prepare variant groups data for frontend
    variant_groups_data = []
    if product:
        current_app.logger.info(f"[VARIANT GROUPS] Product ID: {product.id}, Variant Groups Count: {len(product.variant_groups)}")

        for group in product.variant_groups:
            current_app.logger.info(f"[VARIANT GROUPS] Processing group ID: {group.id}, Name: {group.name}, Products count: {len(group.products)}")

            group_products = []
            for p in group.products:
                current_app.logger.info(f"[VARIANT GROUPS]   - Product in group: ID={p.id}, Name={p.name}, Current product ID={product.id}")

                if p.id != product.id:  # Exclude current product
                    primary_image = p.primary_image
                    image_url = f"/static/{primary_image.path_compressed}" if primary_image else "/static/img/product-placeholder.svg"

                    group_products.append({
                        'id': p.id,
                        'name': p.name,
                        'sku': p.sku or '',
                        'image_url': image_url,
                        'series': p.series.name if p.series else 'Brak serii',
                        'type': p.product_type.name if p.product_type else 'Brak typu'
                    })
                    current_app.logger.info(f"[VARIANT GROUPS]   - Added to group_products")
                else:
                    current_app.logger.info(f"[VARIANT GROUPS]   - Skipped (current product)")

            variant_groups_data.append({
                'id': group.id,
                'name': group.name,
                'products': group_products
            })
            current_app.logger.info(f"[VARIANT GROUPS] Group {group.id} final products count: {len(group_products)}")

        current_app.logger.info(f"[VARIANT GROUPS] Final variant_groups_data: {variant_groups_data}")

    # Get max images from settings
    from modules.auth.models import Settings
    base_max_images = Settings.get_value('warehouse_image_max_per_product', 10)

    # Ensure we show at least as many slots as existing images (Option C)
    # This prevents data loss when max_images setting is reduced below existing image count
    existing_images_count = product.images.count() if product else 0
    max_images = max(base_max_images, existing_images_count)

    # Return modal template for AJAX requests, full page for normal requests
    template = 'admin/warehouse/product_form_modal.html' if is_ajax else 'admin/warehouse/product_form.html'

    # Get price rounding mode from settings
    price_rounding = Settings.get_value('warehouse_price_rounding', 'full')

    return render_template(template, form=form, product=product, mode='edit', variant_groups_data=variant_groups_data, max_images=max_images, price_rounding=price_rounding)


# ==========================================
# Delete Product
# ==========================================
@products_bp.route('/<int:product_id>/delete', methods=['POST'])
@login_required
@role_required('admin')  # Only admin can delete
def delete_product(product_id):
    """Delete product"""

    product = Product.query.get_or_404(product_id)
    product_name = product.name

    try:
        db.session.delete(product)
        db.session.commit()
        flash(f'Produkt "{product_name}" został usunięty.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Błąd podczas usuwania produktu: {str(e)}', 'error')

    return redirect(url_for('products.list_products'))


# ==========================================
# Upload Product Images
# ==========================================
@products_bp.route('/<int:product_id>/images/upload', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def upload_images(product_id):
    """Upload images for product"""
    from utils.image_processor import process_upload, allowed_file

    product = Product.query.get_or_404(product_id)

    if 'images' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400

    files = request.files.getlist('images')

    if not files:
        return jsonify({'error': 'No files selected'}), 400

    uploaded_images = []
    upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'products')

    for file in files:
        if file and file.filename:
            try:
                # Validate file type
                if not allowed_file(file.filename):
                    continue

                # Process upload (save original + compressed)
                image_data = process_upload(file, upload_folder)

                # Determine if this should be primary image (first image uploaded)
                is_primary = product.images.count() == 0

                # Get next sort order
                max_order = db.session.query(db.func.max(ProductImage.sort_order))\
                    .filter_by(product_id=product_id).scalar() or 0
                next_order = max_order + 1

                # Create ProductImage record
                product_image = ProductImage(
                    product_id=product_id,
                    filename=image_data['filename'],
                    path_original=image_data['path_original'],
                    path_compressed=image_data['path_compressed'],
                    is_primary=is_primary,
                    sort_order=next_order
                )

                db.session.add(product_image)
                db.session.commit()

                uploaded_images.append({
                    'id': product_image.id,
                    'filename': product_image.filename,
                    'path_compressed': product_image.path_compressed,
                    'is_primary': product_image.is_primary
                })

            except Exception as e:
                current_app.logger.error(f"Error uploading image: {str(e)}")
                continue

    if uploaded_images:
        flash(f'{len(uploaded_images)} zdjęć zostało przesłanych.', 'success')
        return jsonify({
            'success': True,
            'message': f'{len(uploaded_images)} zdjęć zostało przesłanych.',
            'images': uploaded_images
        })
    else:
        return jsonify({'error': 'No valid images uploaded'}), 400


# ==========================================
# Delete Product Image
# ==========================================
@products_bp.route('/<int:product_id>/images/<int:image_id>', methods=['DELETE'])
@login_required
@role_required('admin', 'mod')
def delete_image(product_id, image_id):
    """Delete product image"""
    from utils.image_processor import delete_image_files

    image = ProductImage.query.get_or_404(image_id)

    # Verify image belongs to product
    if image.product_id != product_id:
        return jsonify({'error': 'Image does not belong to this product'}), 403

    # Check if this is primary image
    was_primary = image.is_primary

    try:
        # Delete physical files from disk
        try:
            delete_image_files(image.path_original, image.path_compressed)
        except Exception as file_error:
            current_app.logger.warning(f"Could not delete image files: {str(file_error)}")
            # Continue anyway - we'll delete the DB record

        # Delete from database
        db.session.delete(image)

        # If this was primary image, set another image as primary
        new_primary_id = None
        if was_primary:
            new_primary = ProductImage.query.filter_by(product_id=product_id)\
                .order_by(ProductImage.sort_order).first()
            if new_primary:
                new_primary.is_primary = True
                new_primary_id = new_primary.id

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Zdjęcie zostało usunięte.',
            'new_primary_id': new_primary_id
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting image: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ==========================================
# Set Primary Image
# ==========================================
@products_bp.route('/<int:product_id>/images/<int:image_id>/set-primary', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def set_primary_image(product_id, image_id):
    """Set image as primary"""

    product = Product.query.get_or_404(product_id)
    image = ProductImage.query.get_or_404(image_id)

    # Verify image belongs to product
    if image.product_id != product_id:
        return jsonify({'error': 'Image does not belong to this product'}), 403

    try:
        # Remove primary flag from all images
        ProductImage.query.filter_by(product_id=product_id).update({'is_primary': False})

        # Set new primary image
        image.is_primary = True
        db.session.commit()

        return jsonify({'success': True, 'message': 'Zdjęcie główne zostało ustawione.'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ==========================================
# Quick Add Tag (AJAX)
# ==========================================
@products_bp.route('/tags/quick-add', methods=['POST'])
@login_required
@role_required('admin')
def quick_add_tag():
    """Quick add tag via AJAX"""

    form = QuickTagForm()

    if form.validate_on_submit():
        # Check if tag already exists
        existing_tag = Tag.query.filter_by(name=form.name.data).first()

        if existing_tag:
            return jsonify({'error': 'Tag o tej nazwie już istnieje.'}), 400

        try:
            tag = Tag(name=form.name.data)
            db.session.add(tag)
            db.session.commit()

            return jsonify({
                'success': True,
                'tag': {'id': tag.id, 'name': tag.name}
            })

        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Nieprawidłowe dane formularza.'}), 400


# ==========================================
# Bulk Activate Products
# ==========================================
@products_bp.route('/bulk-activate', methods=['POST'])
@login_required
@role_required('admin', 'mod')
@csrf.exempt
def bulk_activate():
    """Bulk activate products"""

    data = request.get_json()
    product_ids = data.get('product_ids', [])

    if not product_ids:
        return jsonify({'error': 'Nie wybrano żadnych produktów.'}), 400

    try:
        # Update all selected products
        updated_count = Product.query.filter(Product.id.in_(product_ids)).update(
            {'is_active': True},
            synchronize_session=False
        )
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Aktywowano {updated_count} produktów.',
            'count': updated_count
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error activating products: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ==========================================
# Bulk Deactivate Products
# ==========================================
@products_bp.route('/bulk-deactivate', methods=['POST'])
@login_required
@role_required('admin', 'mod')
@csrf.exempt
def bulk_deactivate():
    """Bulk deactivate products"""

    data = request.get_json()
    product_ids = data.get('product_ids', [])

    if not product_ids:
        return jsonify({'error': 'Nie wybrano żadnych produktów.'}), 400

    try:
        # Update all selected products
        updated_count = Product.query.filter(Product.id.in_(product_ids)).update(
            {'is_active': False},
            synchronize_session=False
        )
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Dezaktywowano {updated_count} produktów.',
            'count': updated_count
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deactivating products: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ==========================================
# Bulk Delete Products
# ==========================================
@products_bp.route('/bulk-delete', methods=['POST'])
@login_required
@role_required('admin')  # Only admin can delete
@csrf.exempt
def bulk_delete():
    """Bulk delete products"""

    data = request.get_json()
    product_ids = data.get('product_ids', [])

    if not product_ids:
        return jsonify({'error': 'Nie wybrano żadnych produktów.'}), 400

    try:
        # Delete all selected products
        deleted_count = Product.query.filter(Product.id.in_(product_ids)).delete(
            synchronize_session=False
        )
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Usunięto {deleted_count} produktów.',
            'count': deleted_count
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting products: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ==========================================
# Bulk Duplicate Products
# ==========================================
@products_bp.route('/bulk-duplicate', methods=['POST'])
@login_required
@role_required('admin', 'mod')
@csrf.exempt
def bulk_duplicate():
    """Bulk duplicate products (1:1 copy with new IDs)"""

    data = request.get_json()
    product_ids = data.get('product_ids', [])

    if not product_ids:
        return jsonify({'error': 'Nie wybrano żadnych produktów.'}), 400

    try:
        duplicated_count = 0
        duplicated_products = []

        for product_id in product_ids:
            original_product = Product.query.get(product_id)

            if not original_product:
                continue

            # Create new product with same data
            new_product = Product(
                name=f"{original_product.name} (kopia)",
                sku=None,  # SKU must be unique, so leave empty
                ean=None,  # EAN must be unique, so leave empty
                category_id=original_product.category_id,
                manufacturer_id=original_product.manufacturer_id,
                series_id=original_product.series_id,
                product_type_id=original_product.product_type_id,
                length=original_product.length,
                width=original_product.width,
                height=original_product.height,
                weight=original_product.weight,
                sale_price=original_product.sale_price,
                purchase_price=original_product.purchase_price,
                purchase_currency=original_product.purchase_currency,
                purchase_price_pln=original_product.purchase_price_pln,
                margin=original_product.margin,
                quantity=0,  # Start with 0 quantity for duplicates
                supplier_id=original_product.supplier_id,
                description=original_product.description,
                is_active=False  # Start as inactive for duplicates
            )

            db.session.add(new_product)
            db.session.flush()  # Get new product ID

            # Copy tags
            for tag in original_product.tags:
                new_product.tags.append(tag)

            # Copy images - PHYSICALLY copy files to new locations
            for img in original_product.images:
                try:
                    # Generate new unique filename
                    file_extension = os.path.splitext(img.filename)[1]
                    new_filename = f"{uuid4().hex}{file_extension}"

                    # Get directory paths
                    original_dir = os.path.dirname(img.path_original)
                    compressed_dir = os.path.dirname(img.path_compressed)

                    # Create new file paths
                    new_path_original = os.path.join(original_dir, new_filename)
                    new_path_compressed = os.path.join(compressed_dir, new_filename)

                    # Get full physical paths
                    original_full_path = os.path.join(current_app.root_path, img.path_original)
                    compressed_full_path = os.path.join(current_app.root_path, img.path_compressed)
                    new_original_full_path = os.path.join(current_app.root_path, new_path_original)
                    new_compressed_full_path = os.path.join(current_app.root_path, new_path_compressed)

                    # Copy physical files
                    if os.path.exists(original_full_path):
                        shutil.copy2(original_full_path, new_original_full_path)

                    if os.path.exists(compressed_full_path):
                        shutil.copy2(compressed_full_path, new_compressed_full_path)

                    # Create new database record with new paths
                    new_image = ProductImage(
                        product_id=new_product.id,
                        filename=new_filename,
                        path_original=new_path_original,
                        path_compressed=new_path_compressed,
                        is_primary=img.is_primary,
                        sort_order=img.sort_order
                    )
                    db.session.add(new_image)

                except Exception as img_error:
                    # Log error but continue with duplication
                    current_app.logger.error(f"Error copying image {img.filename}: {str(img_error)}")
                    # Don't fail the entire duplication if one image fails

            # Note: We don't copy variant groups as they would create complex relationships

            duplicated_count += 1
            duplicated_products.append(new_product.id)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Zduplikowano {duplicated_count} produktów. Nowe produkty są nieaktywne i mają zerowy stan magazynowy.',
            'count': duplicated_count,
            'duplicated_ids': duplicated_products
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error duplicating products: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ==========================================
# Save Variant Groups (AJAX)
# ==========================================
@products_bp.route('/<int:product_id>/save-variant-groups', methods=['POST'])
@login_required
@role_required('admin', 'mod')
@csrf.exempt
def save_variant_groups(product_id):
    """Save all variant groups for a product"""

    product = Product.query.get_or_404(product_id)
    data = request.get_json()
    groups_data = data.get('groups', [])

    try:
        from modules.products.models import VariantGroup, variant_products

        # Get all existing groups for this product
        existing_groups = product.variant_groups

        # Track which groups we're keeping
        groups_to_keep = []

        for group_data in groups_data:
            group_name = group_data.get('name', '').strip()
            product_ids = group_data.get('product_ids', [])
            group_id = group_data.get('id')  # May be None for new groups

            if not product_ids:
                continue  # Skip empty groups

            # Ensure current product is in the group
            if product_id not in product_ids:
                product_ids.append(product_id)

            # Create or update group
            if group_id:
                # Existing group
                group = VariantGroup.query.get(group_id)
                if group:
                    group.name = group_name
                    groups_to_keep.append(group.id)
            else:
                # New group
                group = VariantGroup(name=group_name)
                db.session.add(group)
                db.session.flush()  # Get the ID
                groups_to_keep.append(group.id)

            # Clear existing products for this group
            db.session.execute(
                variant_products.delete().where(
                    variant_products.c.variant_group_id == group.id
                )
            )

            # Add all products to this group
            for pid in product_ids:
                db.session.execute(
                    variant_products.insert().values(
                        variant_group_id=group.id,
                        product_id=pid
                    )
                )

        # Delete groups that were removed
        for existing_group in existing_groups:
            if existing_group.id not in groups_to_keep:
                # Remove from junction table first
                db.session.execute(
                    variant_products.delete().where(
                        variant_products.c.variant_group_id == existing_group.id
                    )
                )
                # Delete the group
                db.session.delete(existing_group)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Grupy wariantowe zostały zapisane.'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving variant groups: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ==========================================
# Search Products for Variants (AJAX)
# ==========================================
@products_bp.route('/search-variants', methods=['GET'])
@login_required
@role_required('admin', 'mod')
def search_variants():
    """Search products for variant groups (debounced AJAX)"""

    query_term = request.args.get('q', '').strip()
    current_product_id = request.args.get('product_id', type=int)
    exclude_group_id = request.args.get('exclude_group_id', type=int)

    if not query_term or len(query_term) < 2:
        return jsonify({'products': []})

    # Base query - search by name, SKU
    query = Product.query.filter(
        Product.is_active == True,
        or_(
            Product.name.like(f'%{query_term}%'),
            Product.sku.like(f'%{query_term}%')
        )
    )

    # If exclude_group_id provided, filter out products already in THIS specific group
    if exclude_group_id:
        # Get products that are already in this group
        from modules.products.models import variant_products
        subquery = db.session.query(variant_products.c.product_id).filter(
            variant_products.c.variant_group_id == exclude_group_id
        )
        query = query.filter(~Product.id.in_(subquery))

    # Limit results
    products = query.limit(20).all()

    # Format results
    results = []
    for product in products:
        # Get primary image URL
        primary_image = product.primary_image
        image_url = f"/static/{primary_image.path_compressed}" if primary_image else "/static/img/product-placeholder.svg"

        results.append({
            'id': product.id,
            'name': product.name,
            'sku': product.sku or '',
            'image_url': image_url,
            'series': product.series.name if product.series else 'Brak serii',
            'type': product.product_type.name if product.product_type else 'Brak typu'
        })

    return jsonify({'products': results})


# ==========================================
# Get All Product IDs (for bulk select all pages)
# ==========================================
@products_bp.route('/get-all-ids', methods=['GET'])
@login_required
@role_required('admin', 'mod')
def get_all_product_ids():
    """Get all product IDs matching current filters (for select all pages)"""

    # Build same query as list_products but only return IDs
    query = Product.query

    # Apply same filters as in list_products
    search = request.args.get('search', '')
    category_id = request.args.get('category_id', 0, type=int)
    manufacturer = request.args.get('manufacturer', 0, type=int)
    series = request.args.get('series', 0, type=int)
    is_active = request.args.get('is_active', '')
    stock_filter = request.args.get('stock_filter', '')

    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Product.name.like(search_term),
                Product.sku.like(search_term),
                Product.ean.like(search_term)
            )
        )

    # Apply category filter
    if category_id:
        query = query.filter(Product.category_id == category_id)

    # Apply manufacturer filter
    if manufacturer:
        query = query.filter(Product.manufacturer_id == manufacturer)

    # Apply series filter
    if series:
        query = query.filter(Product.series_id == series)

    # Apply status filter
    if is_active != '':
        query = query.filter(Product.is_active == (is_active == '1'))

    # Apply stock filter
    if stock_filter:
        if stock_filter == 'in_stock':
            query = query.filter(Product.quantity > 0)
        elif stock_filter == 'out_of_stock':
            query = query.filter(Product.quantity == 0)
        elif stock_filter == 'low_stock':
            query = query.filter(Product.quantity < 10, Product.quantity > 0)

    # Get all IDs
    product_ids = [p.id for p in query.with_entities(Product.id).all()]

    return jsonify({
        'success': True,
        'product_ids': product_ids,
        'count': len(product_ids)
    })


# ==========================================
# Warehouse Settings
# ==========================================
@products_bp.route('/warehouse/settings', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def warehouse_settings():
    """Warehouse settings page"""
    from modules.products.forms import WarehouseSettingsForm
    from modules.auth.models import Settings
    from modules.products.models import Category, Tag, Supplier

    form = WarehouseSettingsForm()

    if form.validate_on_submit():
        # Save all settings to database with (value, type) tuples
        settings_map = {
            'warehouse_image_max_size_mb': (str(form.image_max_size_mb.data or 10), 'integer'),
            'warehouse_image_max_dimension': (str(form.image_max_dimension.data or 1600), 'integer'),
            'warehouse_image_quality': (str(form.image_quality.data or 85), 'integer'),
            'warehouse_image_dpi': (str(form.image_dpi.data or 72), 'integer'),
            'warehouse_image_max_per_product': (str(form.image_max_per_product.data or 10), 'integer'),
            'warehouse_image_formats': (form.image_formats.data or 'jpg,jpeg,png,webp,gif', 'string'),

            'warehouse_stock_alert_enabled': (str(form.stock_alert_enabled.data).lower(), 'boolean'),
            'warehouse_stock_alert_threshold': (str(form.stock_alert_threshold.data or 5), 'integer'),
            'warehouse_stock_allow_negative': (str(form.stock_allow_negative.data).lower(), 'boolean'),
            'warehouse_stock_show_out_of_stock': (str(form.stock_show_out_of_stock.data).lower(), 'boolean'),

            'warehouse_default_purchase_currency': (form.default_purchase_currency.data or 'PLN', 'string'),
            'warehouse_currency_source': (form.currency_source.data or 'nbp', 'string'),
            'warehouse_currency_update_frequency': (str(form.currency_update_frequency.data or 24), 'integer'),
            'warehouse_currency_krw_rate': (str(form.currency_krw_rate.data or 0.0032), 'string'),
            'warehouse_currency_usd_rate': (str(form.currency_usd_rate.data or 4.10), 'string'),
            'warehouse_default_margin': (str(form.default_margin.data or 30), 'integer'),
            'warehouse_price_rounding': (form.price_rounding.data or 'full', 'string'),
        }

        # Update or create each setting
        for key, (value, setting_type) in settings_map.items():
            Settings.set_value(key, value, updated_by=current_user.id, type=setting_type)

        db.session.commit()
        flash('Ustawienia magazynu zostały zapisane', 'success')

        # Get active tab from form
        active_tab = request.form.get('active_tab', 'categories')
        return redirect(url_for('products.warehouse_settings', tab=active_tab))

    # Load current settings from database
    form.image_max_size_mb.data = Settings.get_value('warehouse_image_max_size_mb', 10)
    form.image_max_dimension.data = Settings.get_value('warehouse_image_max_dimension', 1600)
    form.image_quality.data = Settings.get_value('warehouse_image_quality', 85)
    form.image_dpi.data = Settings.get_value('warehouse_image_dpi', 72)
    form.image_max_per_product.data = Settings.get_value('warehouse_image_max_per_product', 10)
    form.image_formats.data = Settings.get_value('warehouse_image_formats', 'jpg,jpeg,png,webp,gif')

    form.stock_alert_enabled.data = Settings.get_value('warehouse_stock_alert_enabled', True)
    form.stock_alert_threshold.data = Settings.get_value('warehouse_stock_alert_threshold', 5)
    form.stock_allow_negative.data = Settings.get_value('warehouse_stock_allow_negative', False)
    form.stock_show_out_of_stock.data = Settings.get_value('warehouse_stock_show_out_of_stock', True)

    form.default_purchase_currency.data = Settings.get_value('warehouse_default_purchase_currency', 'PLN')
    form.currency_source.data = Settings.get_value('warehouse_currency_source', 'nbp')
    form.currency_update_frequency.data = Settings.get_value('warehouse_currency_update_frequency', 24)
    form.currency_krw_rate.data = float(Settings.get_value('warehouse_currency_krw_rate', '0.0032'))
    form.currency_usd_rate.data = float(Settings.get_value('warehouse_currency_usd_rate', '4.10'))
    form.default_margin.data = Settings.get_value('warehouse_default_margin', 30)
    form.price_rounding.data = Settings.get_value('warehouse_price_rounding', 'full')

    # Load categories, tags, suppliers for display in tabs
    categories = Category.query.order_by(Category.sort_order, Category.name).all()
    tags = Tag.query.order_by(Tag.name).all()
    suppliers = Supplier.query.order_by(Supplier.name).all()

    # Get last currency update
    currency_last_update = Settings.get_value('warehouse_currency_last_update', None)

    return render_template('admin/warehouse/settings.html',
                           form=form,
                           categories=categories,
                           tags=tags,
                           suppliers=suppliers,
                           currency_last_update=currency_last_update)


# ==========================================
# Category Management
# ==========================================

@products_bp.route('/categories/create', methods=['POST'])
@login_required
@role_required('admin')
def create_category():
    """Create new category"""
    form = CategoryForm()

    # Populate parent_id choices
    categories = Category.query.order_by(Category.name).all()
    form.parent_id.choices = [(0, '-- Brak (kategoria główna) --')] + [
        (c.id, c.name) for c in categories
    ]

    if form.validate_on_submit():
        try:
            category = Category(
                name=form.name.data,
                parent_id=form.parent_id.data if form.parent_id.data != 0 else None,
                is_active=form.is_active.data
            )

            db.session.add(category)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Kategoria została dodana',
                'category': {
                    'id': category.id,
                    'name': category.name,
                    'parent_id': category.parent_id,
                    'is_active': category.is_active
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating category: {str(e)}")
            return jsonify({'success': False, 'message': 'Błąd podczas dodawania kategorii'}), 500

    # Return validation errors
    errors = {field: errors[0] for field, errors in form.errors.items()}
    return jsonify({'success': False, 'errors': errors}), 400


@products_bp.route('/categories/<int:id>/edit', methods=['POST'])
@login_required
@role_required('admin')
def edit_category(id):
    """Edit existing category"""
    category = Category.query.get_or_404(id)
    form = CategoryForm(obj=category)

    # Populate parent_id choices (exclude self and children)
    categories = Category.query.filter(Category.id != id).order_by(Category.name).all()
    form.parent_id.choices = [(0, '-- Brak (kategoria główna) --')] + [
        (c.id, c.name) for c in categories if c.parent_id != id
    ]

    if form.validate_on_submit():
        try:
            category.name = form.name.data
            category.parent_id = form.parent_id.data if form.parent_id.data != 0 else None
            category.is_active = form.is_active.data

            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Kategoria została zaktualizowana',
                'category': {
                    'id': category.id,
                    'name': category.name,
                    'parent_id': category.parent_id,
                    'is_active': category.is_active
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating category: {str(e)}")
            return jsonify({'success': False, 'message': 'Błąd podczas aktualizacji kategorii'}), 500

    # Return validation errors
    errors = {field: errors[0] for field, errors in form.errors.items()}
    return jsonify({'success': False, 'errors': errors}), 400


@products_bp.route('/categories/<int:id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_category(id):
    """Delete category"""
    category = Category.query.get_or_404(id)

    try:
        # Check if category has products
        products_count = Product.query.filter_by(category_id=id).count()
        if products_count > 0:
            return jsonify({
                'success': False,
                'message': f'Nie można usunąć kategorii. Jest przypisana do {products_count} produktów.'
            }), 400

        # Check if category has children
        children_count = Category.query.filter_by(parent_id=id).count()
        if children_count > 0:
            return jsonify({
                'success': False,
                'message': f'Nie można usunąć kategorii. Ma {children_count} podkategorii.'
            }), 400

        db.session.delete(category)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Kategoria została usunięta'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting category: {str(e)}")
        return jsonify({'success': False, 'message': 'Błąd podczas usuwania kategorii'}), 500


@products_bp.route('/categories/<int:id>', methods=['GET'])
@login_required
@role_required('admin')
def get_category(id):
    """Get category data for editing"""
    category = Category.query.get_or_404(id)

    # Get parent choices (exclude self and children)
    categories = Category.query.filter(Category.id != id).order_by(Category.name).all()
    parent_choices = [{'value': 0, 'label': '-- Brak (kategoria główna) --'}] + [
        {'value': c.id, 'label': c.name} for c in categories if c.parent_id != id
    ]

    return jsonify({
        'success': True,
        'category': {
            'id': category.id,
            'name': category.name,
            'parent_id': category.parent_id or 0,
            'is_active': category.is_active
        },
        'parent_choices': parent_choices
    })


# ==========================================
# Tag Management
# ==========================================

@products_bp.route('/tags/create', methods=['POST'])
@login_required
@role_required('admin')
def create_tag():
    """Create new tag"""
    form = TagForm()

    if form.validate_on_submit():
        try:
            # Check if tag already exists
            existing_tag = Tag.query.filter_by(name=form.name.data).first()
            if existing_tag:
                return jsonify({
                    'success': False,
                    'errors': {'name': 'Tag o tej nazwie już istnieje'}
                }), 400

            tag = Tag(name=form.name.data)
            db.session.add(tag)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Tag został dodany',
                'tag': {
                    'id': tag.id,
                    'name': tag.name
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating tag: {str(e)}")
            return jsonify({'success': False, 'message': 'Błąd podczas dodawania taga'}), 500

    # Return validation errors
    errors = {field: errors[0] for field, errors in form.errors.items()}
    return jsonify({'success': False, 'errors': errors}), 400


@products_bp.route('/tags/<int:id>/edit', methods=['POST'])
@login_required
@role_required('admin')
def edit_tag(id):
    """Edit existing tag"""
    tag = Tag.query.get_or_404(id)
    form = TagForm(obj=tag)

    if form.validate_on_submit():
        try:
            # Check if another tag with this name exists
            existing_tag = Tag.query.filter(
                Tag.name == form.name.data,
                Tag.id != id
            ).first()

            if existing_tag:
                return jsonify({
                    'success': False,
                    'errors': {'name': 'Tag o tej nazwie już istnieje'}
                }), 400

            tag.name = form.name.data
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Tag został zaktualizowany',
                'tag': {
                    'id': tag.id,
                    'name': tag.name
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating tag: {str(e)}")
            return jsonify({'success': False, 'message': 'Błąd podczas aktualizacji taga'}), 500

    # Return validation errors
    errors = {field: errors[0] for field, errors in form.errors.items()}
    return jsonify({'success': False, 'errors': errors}), 400


@products_bp.route('/tags/<int:id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_tag(id):
    """Delete tag"""
    tag = Tag.query.get_or_404(id)

    try:
        # Check if tag is assigned to products
        products_count = db.session.query(product_tags).filter_by(tag_id=id).count()
        if products_count > 0:
            return jsonify({
                'success': False,
                'message': f'Nie można usunąć taga. Jest przypisany do {products_count} produktów.'
            }), 400

        db.session.delete(tag)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Tag został usunięty'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting tag: {str(e)}")
        return jsonify({'success': False, 'message': 'Błąd podczas usuwania taga'}), 500


# ==================== Supplier Management ====================

@products_bp.route('/suppliers/<int:id>', methods=['GET'])
@login_required
@role_required('admin')
def get_supplier(id):
    """Get supplier data for editing"""
    supplier = Supplier.query.get_or_404(id)

    return jsonify({
        'id': supplier.id,
        'name': supplier.name,
        'contact_email': supplier.contact_email,
        'contact_phone': supplier.contact_phone,
        'country': supplier.country,
        'notes': supplier.notes,
        'is_active': supplier.is_active
    })

@products_bp.route('/suppliers/create', methods=['POST'])
@login_required
@role_required('admin')
def create_supplier():
    """Create new supplier"""
    form = SupplierForm()

    if form.validate_on_submit():
        try:
            # Check if supplier already exists
            existing_supplier = Supplier.query.filter_by(name=form.name.data).first()
            if existing_supplier:
                return jsonify({
                    'success': False,
                    'errors': {'name': 'Dostawca o tej nazwie już istnieje'}
                }), 400

            supplier = Supplier(
                name=form.name.data,
                contact_email=form.contact_email.data,
                contact_phone=form.contact_phone.data,
                country=form.country.data,
                notes=form.notes.data,
                is_active=form.is_active.data
            )
            db.session.add(supplier)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Dostawca został dodany',
                'supplier': {
                    'id': supplier.id,
                    'name': supplier.name,
                    'contact_email': supplier.contact_email or '',
                    'contact_phone': supplier.contact_phone or '',
                    'country': supplier.country or '',
                    'notes': supplier.notes or '',
                    'is_active': supplier.is_active
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating supplier: {str(e)}")
            return jsonify({'success': False, 'message': 'Błąd podczas dodawania dostawcy'}), 500

    # Return validation errors
    errors = {field: errors[0] for field, errors in form.errors.items()}
    return jsonify({'success': False, 'errors': errors}), 400


@products_bp.route('/suppliers/<int:id>/edit', methods=['POST'])
@login_required
@role_required('admin')
def edit_supplier(id):
    """Edit existing supplier"""
    supplier = Supplier.query.get_or_404(id)
    form = SupplierForm(obj=supplier)

    if form.validate_on_submit():
        try:
            # Check if another supplier with this name exists
            existing_supplier = Supplier.query.filter(
                Supplier.name == form.name.data,
                Supplier.id != id
            ).first()

            if existing_supplier:
                return jsonify({
                    'success': False,
                    'errors': {'name': 'Dostawca o tej nazwie już istnieje'}
                }), 400

            supplier.name = form.name.data
            supplier.contact_email = form.contact_email.data
            supplier.contact_phone = form.contact_phone.data
            supplier.country = form.country.data
            supplier.notes = form.notes.data
            supplier.is_active = form.is_active.data

            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Dostawca został zaktualizowany',
                'supplier': {
                    'id': supplier.id,
                    'name': supplier.name,
                    'contact_email': supplier.contact_email or '',
                    'contact_phone': supplier.contact_phone or '',
                    'country': supplier.country or '',
                    'notes': supplier.notes or '',
                    'is_active': supplier.is_active
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating supplier: {str(e)}")
            return jsonify({'success': False, 'message': 'Błąd podczas aktualizacji dostawcy'}), 500

    # Return validation errors
    errors = {field: errors[0] for field, errors in form.errors.items()}
    return jsonify({'success': False, 'errors': errors}), 400


@products_bp.route('/suppliers/<int:id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_supplier(id):
    """Delete supplier"""
    supplier = Supplier.query.get_or_404(id)

    try:
        # Check if supplier is assigned to products
        products_count = Product.query.filter_by(supplier_id=id).count()
        if products_count > 0:
            return jsonify({
                'success': False,
                'message': f'Nie można usunąć dostawcy. Jest przypisany do {products_count} produktów.'
            }), 400

        db.session.delete(supplier)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Dostawca został usunięty'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting supplier: {str(e)}")
        return jsonify({'success': False, 'message': 'Błąd podczas usuwania dostawcy'}), 500


@products_bp.route('/tags/<int:id>', methods=['GET'])
@login_required
@role_required('admin')
def get_tag(id):
    """Get tag data for editing"""
    tag = Tag.query.get_or_404(id)

    return jsonify({
        'success': True,
        'tag': {
            'id': tag.id,
            'name': tag.name
        }
    })
