"""
Trasy szybkiego dodawania produktów on hand (ekran pod telefon).
Logika w modules/products/quick_add_service.py.
"""

from flask import abort, jsonify, render_template, request
from flask_login import current_user, login_required

from extensions import db
from modules.products import products_bp
from modules.products.models import Product
from modules.products.quick_add_service import (
    QuickAddError, create_quick_product, hide_quick_product, is_quick_editable,
    serialize_quick_product, update_quick_product,
)
from utils.decorators import role_required
from utils.image_processor import get_image_settings


def _editable_or_404(product_id):
    product = db.session.get(Product, product_id)
    if product is None or not is_quick_editable(product):
        abort(404)
    return product


@products_bp.route('/quick-add', methods=['GET'])
@login_required
@role_required('admin', 'mod')
def quick_add():
    max_photos = int(get_image_settings()['max_per_product'])
    return render_template('admin/warehouse/quick_add.html', max_photos=max_photos)


@products_bp.route('/quick-add', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def quick_add_create():
    files = [f for f in request.files.getlist('images') if f and f.filename]
    try:
        product = create_quick_product(
            request.form.get('name'),
            request.form.get('sale_price'),
            request.form.get('quantity'),
            files,
            current_user,
            description=request.form.get('description'),
        )
    except QuickAddError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True, 'product': serialize_quick_product(product)})


@products_bp.route('/quick-add/<int:product_id>/update', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def quick_add_update(product_id):
    product = _editable_or_404(product_id)
    data = request.get_json(silent=True) or {}
    try:
        update_quick_product(product, data if isinstance(data, dict) else {})
    except QuickAddError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True, 'product': serialize_quick_product(product)})


@products_bp.route('/quick-add/<int:product_id>/hide', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def quick_add_hide(product_id):
    product = _editable_or_404(product_id)
    hide_quick_product(product)
    return jsonify({'success': True, 'product': serialize_quick_product(product)})
