"""
Client Shipping Module - Routes
Endpointy zarządzania adresami dostawy i zleceniami wysyłki
"""

from flask import render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db
from modules.client import client_bp
from modules.auth.models import ShippingAddress
from modules.orders.models import ShippingRequest
from modules.client.shipping_service import (
    validate_address_payload, create_address,
    set_default_address, soft_delete_address, list_active_addresses,
    get_available_orders, validate_and_create_request, cancel_request,
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
    addresses = list_active_addresses(current_user.id)

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

        # Walidacja (typ adresu + wymagane pola per typ) — serwis, parytet komunikatów
        ok, err = validate_address_payload(data)
        if not ok:
            if err['code'] == 'invalid_address_type':
                return jsonify({'success': False, 'message': 'Nieprawidłowy typ adresu'}), 400
            return jsonify({'success': False, 'message': f"Pole {err['field']} jest wymagane"}), 400

        # Tworzenie adresu (clearing is_default, defaulty kraju, achievement hook w serwisie)
        _, _, address = create_address(current_user, data)

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
        ok, err, _ = set_default_address(current_user.id, address_id)
        if not ok:
            return jsonify({'success': False, 'message': 'Adres nie istnieje'}), 404

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
        ok, _ = soft_delete_address(current_user.id, address_id)
        if not ok:
            return jsonify({'success': False, 'message': 'Adres nie istnieje'}), 404

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
        # Zamówienia dostępne do zlecenia — logika w serwisie (parytet zachowany)
        orders = get_available_orders(current_user.id)

        # Format orders for JSON response
        orders_data = []
        for order in orders:
            # Get all order items with full data
            items_data = []
            for item in order.items:
                if item.quantity <= 0:
                    continue
                items_data.append({
                    'name': item.product_name,
                    'selected_size': item.selected_size,
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
                'items_count': len(order.items),
                # Gate Cło/VAT (task 869e674fd): False → zablokowane do zlecenia wysyłki
                'customs_vat_paid': order.is_customs_vat_settled
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
        client_package_preference = data.get('client_package_preference')
        client_notes = data.get('client_notes')

        # Walidacja + tworzenie (snapshot, status początkowy, delivery_method, log, notify) w serwisie.
        # Kody błędów mapowane na DOTYCHCZASOWE komunikaty/statusy weba (parytet — bez zmiany zachowania).
        ok, err, shipping_request = validate_and_create_request(
            current_user, order_ids, address_id,
            client_package_preference=client_package_preference,
            client_notes=client_notes,
        )
        if not ok:
            code = err['code']
            if code == 'no_orders':
                return jsonify({'success': False, 'error': 'Wybierz przynajmniej jedno zamówienie'}), 400
            if code == 'no_address':
                return jsonify({'success': False, 'error': 'Wybierz adres dostawy'}), 400
            if code == 'address_not_found':
                return jsonify({'success': False, 'error': 'Nieprawidłowy adres dostawy'}), 400
            if code == 'customs_vat_unpaid':
                return jsonify({
                    'success': False,
                    'error': 'Nie można zlecić wysyłki — najpierw opłać Cło/VAT dla wybranych zamówień'
                }), 400
            # orders_not_found / orders_not_available → sklejony komunikat (parytet web)
            return jsonify({
                'success': False,
                'error': 'Niektóre zamówienia są niedostępne lub już mają zlecenie wysyłki'
            }), 400

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
        ok, err = cancel_request(current_user.id, request_id)
        if not ok:
            if err['code'] == 'not_found':
                return jsonify({'success': False, 'error': 'Zlecenie nie istnieje'}), 404
            return jsonify({
                'success': False,
                'error': 'Nie można anulować zlecenia w tym statusie'
            }), 400

        return jsonify({
            'success': True,
            'message': 'Zlecenie zostało anulowane'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error canceling shipping request: {e}')
        return jsonify({'success': False, 'error': 'Błąd podczas anulowania zlecenia'}), 500
