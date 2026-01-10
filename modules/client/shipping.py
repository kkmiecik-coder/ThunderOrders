"""
Client Shipping Module - Routes
Endpointy zarządzania adresami dostawy i zleceniami wysyłki
"""

from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from modules.client import client_bp
from modules.auth.models import ShippingAddress


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
            is_default=is_default
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
# PLACEHOLDER PAGES
# ============================================

@client_bp.route('/shipping/requests')
@login_required
def shipping_requests_list():
    """
    PLACEHOLDER: Lista zleceń wysyłki
    """
    return render_template(
        'client/shipping/requests_list.html',
        title='Zlecenia wysyłki'
    )
