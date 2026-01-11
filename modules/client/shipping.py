"""
Client Shipping Module - Routes
Endpointy zarządzania adresami dostawy i zleceniami wysyłki
"""

import os
import json
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db
from modules.client import client_bp
from modules.auth.models import ShippingAddress, Settings
from sqlalchemy import and_, not_, exists
from modules.orders.models import (
    Order, ShippingRequest, ShippingRequestOrder, ShippingRequestStatus,
    get_local_now
)


# ============================================
# DELIVERY ADDRESSES (Main Implementation)
# ============================================

@client_bp.route('/shipping/addresses')
@login_required
def shipping_addresses():
    """
    Lista zapisanych adresów dostawy klienta
    """
    addresses = ShippingAddress.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).order_by(ShippingAddress.is_default.desc(), ShippingAddress.created_at.desc()).all()

    return render_template(
        'client/shipping/addresses.html',
        title='Adresy dostawy',
        addresses=addresses
    )


@client_bp.route('/shipping/addresses/add', methods=['POST'])
@login_required
def shipping_address_add():
    """
    Dodanie nowego adresu dostawy (AJAX)
    """
    try:
        data = request.get_json()

        # Walidacja address_type
        address_type = data.get('address_type')
        if address_type not in ['home', 'pickup_point']:
            return jsonify({'success': False, 'message': 'Nieprawidłowy typ adresu'}), 400

        # Sprawdź czy ustawić jako domyślny
        is_default = data.get('is_default', False)

        # Jeśli ma być domyślny, usuń flagę is_default z innych adresów
        if is_default:
            ShippingAddress.query.filter_by(
                user_id=current_user.id,
                is_default=True
            ).update({'is_default': False})
            db.session.flush()  # Force update przed dodaniem nowego

        # Stwórz nowy adres
        address = ShippingAddress(
            user_id=current_user.id,
            address_type=address_type,
            is_default=is_default,
            name=data.get('name')  # Opcjonalna nazwa adresu
        )

        # Wypełnij pola w zależności od typu
        if address_type == 'pickup_point':
            # Walidacja wymaganych pól
            required_fields = ['pickup_courier', 'pickup_point_id', 'pickup_address', 'pickup_postal_code', 'pickup_city']
            for field in required_fields:
                if not data.get(field):
                    return jsonify({'success': False, 'message': f'Pole {field} jest wymagane'}), 400

            address.pickup_courier = data.get('pickup_courier')
            address.pickup_point_id = data.get('pickup_point_id')
            address.pickup_address = data.get('pickup_address')
            address.pickup_postal_code = data.get('pickup_postal_code')
            address.pickup_city = data.get('pickup_city')

        elif address_type == 'home':
            # Walidacja wymaganych pól
            required_fields = ['shipping_name', 'shipping_address', 'shipping_postal_code', 'shipping_city']
            for field in required_fields:
                if not data.get(field):
                    return jsonify({'success': False, 'message': f'Pole {field} jest wymagane'}), 400

            address.shipping_name = data.get('shipping_name')
            address.shipping_address = data.get('shipping_address')
            address.shipping_postal_code = data.get('shipping_postal_code')
            address.shipping_city = data.get('shipping_city')
            address.shipping_voivodeship = data.get('shipping_voivodeship')
            address.shipping_country = data.get('shipping_country', 'Polska')

        db.session.add(address)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Adres został dodany',
            'address_id': address.id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@client_bp.route('/shipping/addresses/<int:address_id>/set-default', methods=['POST'])
@login_required
def shipping_address_set_default(address_id):
    """
    Ustawienie adresu jako domyślny
    """
    try:
        address = ShippingAddress.query.filter_by(
            id=address_id,
            user_id=current_user.id,
            is_active=True
        ).first_or_404()

        # Usuń flagę is_default z innych adresów
        ShippingAddress.query.filter_by(
            user_id=current_user.id,
            is_default=True
        ).update({'is_default': False})

        # Ustaw nowy domyślny
        address.is_default = True
        db.session.commit()

        return jsonify({'success': True, 'message': 'Adres ustawiony jako domyślny'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@client_bp.route('/shipping/addresses/<int:address_id>/delete', methods=['POST'])
@login_required
def shipping_address_delete(address_id):
    """
    Soft delete adresu (is_active = False)
    """
    try:
        address = ShippingAddress.query.filter_by(
            id=address_id,
            user_id=current_user.id,
            is_active=True
        ).first_or_404()

        # Soft delete
        address.is_active = False
        db.session.commit()

        return jsonify({'success': True, 'message': 'Adres został usunięty'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================
# SHIPPING REQUESTS
# ============================================

@client_bp.route('/shipping/requests')
@login_required
def shipping_requests_list():
    """
    Lista zleceń wysyłki klienta
    """
    # Get all shipping requests for current user
    requests = ShippingRequest.query.filter_by(
        user_id=current_user.id
    ).order_by(ShippingRequest.created_at.desc()).all()

    # Get user's addresses for the modal
    addresses = ShippingAddress.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).order_by(ShippingAddress.is_default.desc(), ShippingAddress.created_at.desc()).all()

    return render_template(
        'client/shipping/requests_list.html',
        title='Zlecenia wysyłki',
        requests=requests,
        addresses=addresses
    )


@client_bp.route('/shipping/requests/list')
@login_required
def shipping_requests_list_json():
    """
    Zwraca listę zleceń wysyłki klienta (JSON) - do dynamicznego odświeżania
    """
    try:
        requests_list = ShippingRequest.query.filter_by(
            user_id=current_user.id
        ).order_by(ShippingRequest.created_at.desc()).all()

        requests_data = []
        for req in requests_list:
            # Get orders for this request
            orders_data = []
            for ro in req.request_orders[:3]:
                if ro.order:
                    orders_data.append({
                        'id': ro.order.id,
                        'order_number': ro.order.order_number
                    })

            requests_data.append({
                'id': req.id,
                'request_number': req.request_number,
                'orders': orders_data,
                'orders_count': len(req.request_orders),
                'address_type': req.address_type,
                'short_address': req.short_address,
                'full_address': req.full_address,
                'total_shipping_cost': float(req.calculated_shipping_cost) if req.calculated_shipping_cost else None,
                'status': req.status,
                'status_display_name': req.status_display_name,
                'status_badge_color': req.status_badge_color,
                'created_at': req.created_at.strftime('%d.%m.%Y %H:%M'),
                'can_cancel': req.can_cancel,
                'can_upload_payment_proof': req.can_upload_payment_proof,
                'has_payment_proof': req.has_payment_proof,
                'payment_proof_status': req.payment_proof_status,
                'tracking_number': req.tracking_number,
                'tracking_url': req.tracking_url
            })

        return jsonify({'success': True, 'requests': requests_data})

    except Exception as e:
        current_app.logger.error(f'Error fetching shipping requests: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@client_bp.route('/shipping/requests/available-orders')
@login_required
def shipping_requests_available_orders():
    """
    Zwraca listę zamówień dostępnych do zlecenia wysyłki (JSON)
    """
    try:
        # Get allowed order statuses from settings
        setting = Settings.query.filter_by(key='shipping_request_allowed_statuses').first()
        allowed_statuses = []
        if setting and setting.value:
            try:
                allowed_statuses = json.loads(setting.value)
            except (json.JSONDecodeError, TypeError):
                allowed_statuses = ['dostarczone_gom']  # Default fallback
        else:
            allowed_statuses = ['dostarczone_gom']

        # Get orders that:
        # 1. Belong to current user
        # 2. Have allowed status
        # 3. Are not already in a shipping request

        # Subquery to check if order is in any shipping request
        in_shipping_request = db.session.query(ShippingRequestOrder.order_id).filter(
            ShippingRequestOrder.order_id == Order.id
        ).exists()

        orders = Order.query.filter(
            and_(
                Order.user_id == current_user.id,
                Order.status.in_(allowed_statuses),
                ~in_shipping_request
            )
        ).order_by(Order.created_at.desc()).all()

        # Format orders for JSON response
        orders_data = []
        for order in orders:
            # Get all order items with full data
            items_data = []
            for item in order.items:
                items_data.append({
                    'name': item.product_name,
                    'image_url': item.product_image_url,
                    'quantity': item.quantity,
                    'price': float(item.price)
                })

            orders_data.append({
                'id': order.id,
                'order_number': order.order_number,
                'total_amount': float(order.total_amount),
                'created_at': order.created_at.strftime('%d.%m.%Y'),
                'items': items_data,
                'items_count': len(order.items)
            })

        return jsonify({'success': True, 'orders': orders_data})

    except Exception as e:
        current_app.logger.error(f'Error fetching available orders: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@client_bp.route('/shipping/requests/create', methods=['POST'])
@login_required
def shipping_requests_create():
    """
    Tworzy nowe zlecenie wysyłki
    """
    try:
        data = request.get_json()
        order_ids = data.get('order_ids', [])
        address_id = data.get('address_id')

        # Validation
        if not order_ids:
            return jsonify({'success': False, 'error': 'Wybierz przynajmniej jedno zamówienie'}), 400
        if not address_id:
            return jsonify({'success': False, 'error': 'Wybierz adres dostawy'}), 400

        # Get allowed order statuses
        setting = Settings.query.filter_by(key='shipping_request_allowed_statuses').first()
        allowed_statuses = []
        if setting and setting.value:
            try:
                allowed_statuses = json.loads(setting.value)
            except (json.JSONDecodeError, TypeError):
                allowed_statuses = ['dostarczone_gom']
        else:
            allowed_statuses = ['dostarczone_gom']

        # Verify orders belong to user and have allowed status

        # Subquery to check if order is in any shipping request
        in_shipping_request = db.session.query(ShippingRequestOrder.order_id).filter(
            ShippingRequestOrder.order_id == Order.id
        ).exists()

        orders = Order.query.filter(
            and_(
                Order.id.in_(order_ids),
                Order.user_id == current_user.id,
                Order.status.in_(allowed_statuses),
                ~in_shipping_request
            )
        ).all()

        if len(orders) != len(order_ids):
            return jsonify({
                'success': False,
                'error': 'Niektóre zamówienia są niedostępne lub już mają zlecenie wysyłki'
            }), 400

        # Verify address belongs to user
        address = ShippingAddress.query.filter_by(
            id=address_id,
            user_id=current_user.id,
            is_active=True
        ).first()

        if not address:
            return jsonify({'success': False, 'error': 'Nieprawidłowy adres dostawy'}), 400

        # Get initial status from settings or fallback
        default_status_setting = Settings.query.filter_by(key='shipping_request_default_status').first()

        if default_status_setting and default_status_setting.value:
            # Use setting value
            initial_status = ShippingRequestStatus.query.filter_by(
                slug=default_status_setting.value,
                is_active=True
            ).first()
        else:
            initial_status = None

        # Fallback to is_initial=True or first active status
        if not initial_status:
            initial_status = ShippingRequestStatus.query.filter_by(is_initial=True, is_active=True).first()
        if not initial_status:
            initial_status = ShippingRequestStatus.query.filter_by(is_active=True).order_by(ShippingRequestStatus.sort_order).first()

        status_slug = initial_status.slug if initial_status else 'nowe'

        # Create shipping request
        shipping_request = ShippingRequest(
            request_number=ShippingRequest.generate_request_number(),
            user_id=current_user.id,
            status=status_slug,
            address_type=address.address_type,
            # Copy address fields
            shipping_name=address.shipping_name,
            shipping_address=address.shipping_address,
            shipping_postal_code=address.shipping_postal_code,
            shipping_city=address.shipping_city,
            shipping_voivodeship=address.shipping_voivodeship,
            shipping_country=address.shipping_country,
            pickup_courier=address.pickup_courier,
            pickup_point_id=address.pickup_point_id,
            pickup_address=address.pickup_address,
            pickup_postal_code=address.pickup_postal_code,
            pickup_city=address.pickup_city
        )

        db.session.add(shipping_request)
        db.session.flush()  # Get ID

        # Determine delivery_method based on address type
        delivery_method = None
        if address.address_type == 'home':
            delivery_method = 'kurier'
        elif address.address_type == 'pickup_point' and address.pickup_courier:
            courier_lower = address.pickup_courier.lower()
            if 'inpost' in courier_lower or 'paczkomat' in courier_lower:
                delivery_method = 'paczkomat'
            elif 'orlen' in courier_lower:
                delivery_method = 'orlen_paczka'
            elif 'dpd' in courier_lower:
                delivery_method = 'dpd_pickup'

        # Add orders to shipping request and update delivery_method
        for order in orders:
            request_order = ShippingRequestOrder(
                shipping_request_id=shipping_request.id,
                order_id=order.id
            )
            db.session.add(request_order)

            # Update delivery_method if not already set
            if delivery_method and not order.delivery_method:
                order.delivery_method = delivery_method

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Zlecenie wysyłki zostało utworzone',
            'request_number': shipping_request.request_number
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error creating shipping request: {e}')
        return jsonify({'success': False, 'error': 'Błąd podczas tworzenia zlecenia'}), 500


@client_bp.route('/shipping/requests/<int:request_id>/cancel', methods=['POST'])
@login_required
def shipping_requests_cancel(request_id):
    """
    Anuluje (usuwa) zlecenie wysyłki - tylko jeśli w początkowym statusie
    """
    try:
        shipping_request = ShippingRequest.query.filter_by(
            id=request_id,
            user_id=current_user.id
        ).first()

        if not shipping_request:
            return jsonify({'success': False, 'error': 'Zlecenie nie istnieje'}), 404

        if not shipping_request.can_cancel:
            return jsonify({
                'success': False,
                'error': 'Nie można anulować zlecenia w tym statusie'
            }), 400

        # Delete shipping request (cascade will delete ShippingRequestOrder records)
        db.session.delete(shipping_request)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Zlecenie zostało anulowane'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error canceling shipping request: {e}')
        return jsonify({'success': False, 'error': 'Błąd podczas anulowania zlecenia'}), 500


@client_bp.route('/shipping/requests/upload-proof', methods=['POST'])
@login_required
def shipping_requests_upload_proof():
    """
    Wgrywanie dowodu wpłaty za wysyłkę
    """
    try:
        request_id = request.form.get('request_id')
        if not request_id:
            return jsonify({'success': False, 'error': 'Brak ID zlecenia'}), 400

        shipping_request = ShippingRequest.query.filter_by(
            id=request_id,
            user_id=current_user.id
        ).first()

        if not shipping_request:
            return jsonify({'success': False, 'error': 'Zlecenie nie istnieje'}), 404

        if not shipping_request.can_upload_payment_proof:
            return jsonify({
                'success': False,
                'error': 'Nie można wgrać dowodu wpłaty dla tego zlecenia'
            }), 400

        # Check if file was uploaded
        if 'payment_proof' not in request.files:
            return jsonify({'success': False, 'error': 'Nie wybrano pliku'}), 400

        file = request.files['payment_proof']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Nie wybrano pliku'}), 400

        # Validate file type
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            return jsonify({
                'success': False,
                'error': 'Dozwolone formaty: PNG, JPG, JPEG, GIF, PDF'
            }), 400

        # Create upload directory if not exists
        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'shipping_proofs')
        os.makedirs(upload_dir, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = secure_filename(f"shipping_{shipping_request.id}_{timestamp}.{file_ext}")
        filepath = os.path.join(upload_dir, filename)

        # Delete old file if exists
        if shipping_request.payment_proof_file:
            old_filepath = os.path.join(upload_dir, shipping_request.payment_proof_file)
            if os.path.exists(old_filepath):
                os.remove(old_filepath)

        # Save new file
        file.save(filepath)

        # Get payment method name from form
        payment_method_name = request.form.get('payment_method_name', '').strip()

        # Update shipping request
        shipping_request.payment_proof_file = f"uploads/shipping_proofs/{filename}"
        shipping_request.payment_proof_uploaded_at = get_local_now()
        shipping_request.payment_proof_status = 'pending'
        shipping_request.payment_proof_rejection_reason = None

        # Save payment method if provided
        if payment_method_name:
            shipping_request.payment_method = payment_method_name

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Dowód wpłaty został wgrany'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error uploading payment proof: {e}')
        return jsonify({'success': False, 'error': 'Błąd podczas wgrywania pliku'}), 500
