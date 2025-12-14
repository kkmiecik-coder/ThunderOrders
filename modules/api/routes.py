"""
API Routes
Internal API endpoints for user preferences and AJAX requests
"""

from flask import jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import or_
from extensions import db
from . import api_bp
from utils.decorators import role_required


@api_bp.route('/preferences/sidebar', methods=['POST'])
@login_required
def update_sidebar_preference():
    """
    Update user's sidebar collapsed preference

    Request JSON:
    {
        "collapsed": true/false
    }
    """
    try:
        data = request.get_json()
        collapsed = data.get('collapsed', False)

        # Update user preference
        current_user.sidebar_collapsed = collapsed
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Sidebar preference updated',
            'collapsed': collapsed
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error updating sidebar preference: {str(e)}'
        }), 500


@api_bp.route('/preferences/dark-mode', methods=['POST'])
@login_required
def update_dark_mode_preference():
    """
    Update user's dark mode preference

    Request JSON:
    {
        "enabled": true/false
    }
    """
    try:
        data = request.get_json()
        enabled = data.get('enabled', False)

        # Update user preference
        current_user.dark_mode_enabled = enabled
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Dark mode preference updated',
            'enabled': enabled
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error updating dark mode preference: {str(e)}'
        }), 500


@api_bp.route('/exchange-rate', methods=['GET'])
@login_required
def get_exchange_rate_api():
    """
    Get exchange rate for given currency to PLN

    Query params:
        currency: Currency code (KRW, USD, EUR, etc.)

    Returns:
        JSON: {
            'success': True,
            'rate': float,
            'currency': str,
            'date': str,
            'cached': bool,
            'cached_at': str or None,
            'cache_age_hours': int or None,
            'warning': str or None
        }
    """
    try:
        from utils.currency import get_exchange_rate

        currency = request.args.get('currency', '').upper()

        if not currency:
            return jsonify({
                'success': False,
                'message': 'Currency parameter is required'
            }), 400

        if currency not in ['KRW', 'USD', 'EUR', 'GBP', 'CHF', 'JPY', 'CNY']:
            return jsonify({
                'success': False,
                'message': f'Unsupported currency: {currency}'
            }), 400

        rate_data = get_exchange_rate(currency)

        return jsonify({
            'success': True,
            **rate_data
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching exchange rate: {str(e)}'
        }), 500


@api_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    """
    return jsonify({
        'status': 'healthy',
        'version': '1.0.0-MVP'
    }), 200


@api_bp.route('/refresh-currency-rates', methods=['POST'])
@login_required
def refresh_currency_rates():
    """
    Refresh currency exchange rates (KRW and USD) from NBP API
    and update them in warehouse settings

    Returns:
        JSON: {
            'success': True,
            'rates': {
                'KRW': float,
                'USD': float
            },
            'updated_at': str
        }
    """
    try:
        from utils.currency import get_exchange_rate
        from modules.auth.models import Settings
        from datetime import datetime

        # Fetch fresh rates from NBP API
        krw_data = get_exchange_rate('KRW')
        usd_data = get_exchange_rate('USD')

        # Update settings in database
        Settings.set_value('warehouse_currency_krw_rate', str(krw_data['rate']), updated_by=current_user.id, type='string')
        Settings.set_value('warehouse_currency_usd_rate', str(usd_data['rate']), updated_by=current_user.id, type='string')
        Settings.set_value('warehouse_currency_last_update', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), updated_by=current_user.id, type='string')

        db.session.commit()

        return jsonify({
            'success': True,
            'rates': {
                'KRW': krw_data['rate'],
                'USD': usd_data['rate']
            },
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error refreshing currency rates: {str(e)}'
        }), 500


@api_bp.route('/products/search', methods=['GET'])
@login_required
def search_products():
    """
    Search products by name, SKU, or EAN
    Used for variant linking and general product search

    Query params:
        q: Search query (min 2 characters)
        limit: Max results to return (default 20)

    Returns:
        JSON: {
            'success': True,
            'products': [
                {
                    'id': int,
                    'name': str,
                    'sku': str,
                    'ean': str,
                    'image_url': str or None
                }
            ]
        }
    """
    try:
        from modules.products.models import Product
        from flask import url_for

        query = request.args.get('q', '').strip()
        limit = request.args.get('limit', 20, type=int)

        if len(query) < 2:
            return jsonify({
                'success': False,
                'message': 'Search query must be at least 2 characters'
            }), 400

        # Search products by name, SKU, or EAN
        products = Product.query.filter(
            db.or_(
                Product.name.ilike(f'%{query}%'),
                Product.sku.ilike(f'%{query}%'),
                Product.ean.ilike(f'%{query}%')
            )
        ).filter_by(is_active=True).limit(limit).all()

        # Format results
        results = []
        for product in products:
            # Get primary image
            primary_image = product.primary_image
            image_url = None
            if primary_image:
                image_url = url_for('static', filename=primary_image.path_compressed, _external=False)

            results.append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku or '',
                'ean': product.ean or '',
                'price': float(product.sale_price) if product.sale_price else 0,
                'image_url': image_url
            })

        return jsonify({
            'success': True,
            'products': results
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error searching products: {str(e)}'
        }), 500


@api_bp.route('/clients/search', methods=['GET'])
@login_required
@role_required('admin', 'mod')
def search_clients():
    """
    Search clients by name or email
    Used for order creation and client lookup

    Query params:
        q: Search query (min 3 characters)
        limit: Max results to return (default 10)

    Returns:
        JSON: {
            'success': True,
            'clients': [
                {
                    'id': int,
                    'full_name': str,
                    'email': str,
                    'phone': str or None
                }
            ]
        }
    """
    try:
        from modules.auth.models import User

        query = request.args.get('q', '').strip()
        limit = request.args.get('limit', 10, type=int)

        if len(query) < 3:
            return jsonify({
                'success': False,
                'message': 'Search query must be at least 3 characters'
            }), 400

        # Search clients (users with role 'client')
        clients = User.query.filter(
            User.role == 'client',
            User.is_active == True,
            or_(
                User.first_name.ilike(f'%{query}%'),
                User.last_name.ilike(f'%{query}%'),
                User.email.ilike(f'%{query}%'),
                db.func.concat(User.first_name, ' ', User.last_name).ilike(f'%{query}%')
            )
        ).limit(limit).all()

        # Format results
        results = []
        for client in clients:
            results.append({
                'id': client.id,
                'full_name': client.full_name,
                'email': client.email,
                'phone': client.phone or ''
            })

        return jsonify({
            'success': True,
            'clients': results
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error searching clients: {str(e)}'
        }), 500


@api_bp.route('/clients/create', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def create_client():
    """
    Create a new client (user with role 'client')
    Used for quick client creation during order creation

    Request JSON:
        {
            'first_name': str,
            'last_name': str,
            'email': str,
            'phone': str (optional)
        }

    Returns:
        JSON: {
            'success': True,
            'client_id': int,
            'message': str
        }
    """
    try:
        from modules.auth.models import User
        import secrets

        data = request.get_json()

        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        email = data.get('email', '').strip().lower()
        phone = data.get('phone', '').strip()

        # Validate required fields
        if not first_name or not last_name or not email:
            return jsonify({
                'success': False,
                'error': 'Imię, nazwisko i email są wymagane'
            }), 400

        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({
                'success': False,
                'error': 'Użytkownik z tym adresem email już istnieje'
            }), 400

        # Create new client with random password (they can reset it later)
        random_password = secrets.token_urlsafe(16)
        new_client = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone if phone else None,
            role='client',
            is_active=True,
            email_verified=True  # Skip verification for admin-created clients
        )
        new_client.set_password(random_password)

        db.session.add(new_client)
        db.session.commit()

        return jsonify({
            'success': True,
            'client_id': new_client.id,
            'message': f'Klient {new_client.full_name} został utworzony'
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Błąd podczas tworzenia klienta: {str(e)}'
        }), 500
