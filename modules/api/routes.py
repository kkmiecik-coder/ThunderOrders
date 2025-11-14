"""
API Routes
Internal API endpoints for user preferences and AJAX requests
"""

from flask import jsonify, request
from flask_login import login_required, current_user
from extensions import db
from . import api_bp


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
