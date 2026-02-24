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

        # If empty query, return recent/popular products
        if len(query) == 0:
            products = Product.query.filter_by(is_active=True).order_by(Product.updated_at.desc()).limit(limit).all()
        elif len(query) < 2:
            return jsonify({
                'success': False,
                'message': 'Search query must be at least 2 characters'
            }), 400
        else:
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


@api_bp.route('/search', methods=['GET'])
@login_required
def global_search():
    """
    Global search endpoint with role-based results.
    Admin/Mod: orders, products, clients, exclusive, proxy/poland orders, shipping requests, navigation.
    Client: own orders, own shipping requests, navigation.

    Query params:
        q: Search query (min 1 char)

    Returns:
        JSON with categorized results
    """
    from flask import url_for
    from modules.orders.models import Order, ShippingRequest
    from modules.products.models import Product, ProxyOrder, PolandOrder
    from modules.exclusive.models import ExclusivePage
    from modules.auth.models import User

    query = request.args.get('q', '').strip()

    if len(query) < 1:
        return jsonify({'success': False, 'message': 'Wpisz co najmniej 1 znak'}), 400

    results = {}
    is_admin = current_user.role in ('admin', 'mod')
    limit_per_category = 5

    # --- Navigation (always available, min 1 char) ---
    nav_items = _get_navigation_items(is_admin)
    matched_nav = []
    q_lower = query.lower()
    for item in nav_items:
        if q_lower in item['title'].lower() or any(q_lower in kw for kw in item.get('keywords', [])):
            matched_nav.append({
                'title': item['title'],
                'subtitle': item.get('subtitle', ''),
                'url': item['url']
            })
    if matched_nav:
        results['navigation'] = matched_nav[:limit_per_category]

    # For DB searches, require min 2 chars
    if len(query) >= 2:

        # --- Orders ---
        if is_admin:
            orders = Order.query.filter(
                db.or_(
                    Order.order_number.ilike(f'%{query}%'),
                    Order.guest_name.ilike(f'%{query}%'),
                    Order.tracking_number.ilike(f'%{query}%'),
                    Order.shipping_name.ilike(f'%{query}%')
                )
            ).order_by(Order.created_at.desc()).limit(limit_per_category).all()
        else:
            # Client: only own orders
            orders = Order.query.filter(
                Order.user_id == current_user.id,
                db.or_(
                    Order.order_number.ilike(f'%{query}%'),
                    Order.tracking_number.ilike(f'%{query}%')
                )
            ).order_by(Order.created_at.desc()).limit(limit_per_category).all()

        if orders:
            order_results = []
            for o in orders:
                if is_admin:
                    url = url_for('orders.admin_detail', order_id=o.id)
                    subtitle = o.customer_name or ''
                else:
                    url = url_for('orders.client_detail', order_id=o.id)
                    subtitle = o.type_display_name or ''

                badge_info = _get_order_badge(o.status)
                order_results.append({
                    'title': o.order_number,
                    'subtitle': subtitle,
                    'url': url,
                    'badge': badge_info.get('label', ''),
                    'badge_bg': badge_info.get('bg', ''),
                    'badge_color': badge_info.get('color', '')
                })
            results['orders'] = order_results

        # --- Shipping Requests ---
        if is_admin:
            ship_requests = ShippingRequest.query.filter(
                db.or_(
                    ShippingRequest.request_number.ilike(f'%{query}%'),
                    ShippingRequest.shipping_name.ilike(f'%{query}%'),
                    ShippingRequest.tracking_number.ilike(f'%{query}%')
                )
            ).order_by(ShippingRequest.created_at.desc()).limit(limit_per_category).all()
        else:
            ship_requests = ShippingRequest.query.filter(
                ShippingRequest.user_id == current_user.id,
                db.or_(
                    ShippingRequest.request_number.ilike(f'%{query}%'),
                    ShippingRequest.tracking_number.ilike(f'%{query}%')
                )
            ).order_by(ShippingRequest.created_at.desc()).limit(limit_per_category).all()

        if ship_requests:
            ship_results = []
            for sr in ship_requests:
                if is_admin:
                    url = url_for('orders.admin_shipping_requests_list')
                else:
                    url = url_for('client.shipping_requests_list')

                ship_results.append({
                    'title': sr.request_number,
                    'subtitle': sr.shipping_name or '',
                    'url': url
                })
            results['shipping_requests'] = ship_results

        # --- Admin-only categories ---
        if is_admin:
            # Products
            products = Product.query.filter(
                Product.is_active == True,
                db.or_(
                    Product.name.ilike(f'%{query}%'),
                    Product.sku.ilike(f'%{query}%'),
                    Product.ean.ilike(f'%{query}%')
                )
            ).limit(limit_per_category).all()

            if products:
                prod_results = []
                for p in products:
                    subtitle_parts = []
                    if p.sku:
                        subtitle_parts.append(f'SKU: {p.sku}')
                    if p.ean:
                        subtitle_parts.append(f'EAN: {p.ean}')

                    prod_results.append({
                        'title': p.name,
                        'subtitle': ' | '.join(subtitle_parts),
                        'url': url_for('products.edit_product', product_id=p.id)
                    })
                results['products'] = prod_results

            # Clients
            clients = User.query.filter(
                User.role == 'client',
                User.is_active == True,
                db.or_(
                    User.first_name.ilike(f'%{query}%'),
                    User.last_name.ilike(f'%{query}%'),
                    User.email.ilike(f'%{query}%'),
                    db.func.concat(User.first_name, ' ', User.last_name).ilike(f'%{query}%')
                )
            ).limit(limit_per_category).all()

            if clients:
                client_results = []
                for c in clients:
                    client_results.append({
                        'title': c.full_name,
                        'subtitle': c.email,
                        'url': url_for('admin.client_detail', id=c.id)
                    })
                results['clients'] = client_results

            # Exclusive Pages
            exclusives = ExclusivePage.query.filter(
                db.or_(
                    ExclusivePage.name.ilike(f'%{query}%'),
                    ExclusivePage.token.ilike(f'%{query}%')
                )
            ).order_by(ExclusivePage.created_at.desc()).limit(limit_per_category).all()

            if exclusives:
                exc_results = []
                for ep in exclusives:
                    badge_info = _get_exclusive_badge(ep.status)
                    exc_results.append({
                        'title': ep.name,
                        'subtitle': f'Token: {ep.token}',
                        'url': url_for('admin.exclusive_edit', page_id=ep.id),
                        'badge': badge_info.get('label', ''),
                        'badge_bg': badge_info.get('bg', ''),
                        'badge_color': badge_info.get('color', '')
                    })
                results['exclusive'] = exc_results

            # Proxy Orders
            proxy_orders = ProxyOrder.query.filter(
                db.or_(
                    ProxyOrder.order_number.ilike(f'%{query}%'),
                    ProxyOrder.tracking_number.ilike(f'%{query}%')
                )
            ).order_by(ProxyOrder.created_at.desc()).limit(limit_per_category).all()

            if proxy_orders:
                proxy_results = []
                for po in proxy_orders:
                    proxy_results.append({
                        'title': po.order_number,
                        'subtitle': po.status or '',
                        'url': url_for('products.stock_orders')
                    })
                results['proxy_orders'] = proxy_results

            # Poland Orders
            poland_orders = PolandOrder.query.filter(
                db.or_(
                    PolandOrder.order_number.ilike(f'%{query}%'),
                    PolandOrder.tracking_number.ilike(f'%{query}%')
                )
            ).order_by(PolandOrder.created_at.desc()).limit(limit_per_category).all()

            if poland_orders:
                pl_results = []
                for plo in poland_orders:
                    pl_results.append({
                        'title': plo.order_number,
                        'subtitle': plo.status or '',
                        'url': url_for('products.stock_orders')
                    })
                results['poland_orders'] = pl_results

    return jsonify({
        'success': True,
        'results': results
    }), 200


def _get_navigation_items(is_admin):
    """Returns static navigation items based on user role."""
    from flask import url_for

    if is_admin:
        return [
            {'title': 'Dashboard', 'url': url_for('admin.dashboard'), 'keywords': ['panel', 'start', 'home']},
            {'title': 'Lista zamówień', 'subtitle': 'Zamówienia', 'url': url_for('orders.admin_list'), 'keywords': ['zamówienia', 'orders', 'zamowienia']},
            {'title': 'Zlecenia wysyłki', 'subtitle': 'Zamówienia', 'url': url_for('orders.admin_shipping_requests_list'), 'keywords': ['wysyłka', 'shipping', 'zlecenia', 'wyslane']},
            {'title': 'Potwierdzenia płatności', 'subtitle': 'Zamówienia', 'url': url_for('admin.payment_confirmations_list'), 'keywords': ['platnosci', 'płatności', 'payment']},
            {'title': 'Exclusive', 'subtitle': 'Zamówienia', 'url': url_for('admin.exclusive_list'), 'keywords': ['exclusive', 'ekskluzywne']},
            {'title': 'Ustawienia zamówień', 'subtitle': 'Zamówienia', 'url': url_for('orders.settings'), 'keywords': ['ustawienia', 'settings']},
            {'title': 'Lista produktów', 'subtitle': 'Magazyn', 'url': url_for('products.list_products'), 'keywords': ['produkty', 'products', 'magazyn', 'warehouse']},
            {'title': 'Zamówienia produktów', 'subtitle': 'Magazyn', 'url': url_for('products.stock_orders'), 'keywords': ['proxy', 'stock', 'zamówienia produktów', 'korea']},
            {'title': 'Ustawienia magazynu', 'subtitle': 'Magazyn', 'url': url_for('products.warehouse_settings'), 'keywords': ['ustawienia', 'magazyn', 'waluta']},
            {'title': 'Użytkownicy', 'url': url_for('admin.clients_list'), 'keywords': ['klienci', 'clients', 'users', 'użytkownicy']},
            {'title': 'Moje zadania', 'url': url_for('admin.tasks_list'), 'keywords': ['zadania', 'tasks', 'todo']},
            {'title': 'Feedback', 'url': url_for('feedback.admin_list'), 'keywords': ['ankiety', 'feedback', 'opinie']},
            {'title': 'Popupy', 'url': url_for('admin.popups_list'), 'keywords': ['popupy', 'popup', 'ogłoszenia', 'ogloszenia', 'announcement']},
        ]
    else:
        return [
            {'title': 'Dashboard', 'url': url_for('client.dashboard'), 'keywords': ['panel', 'start', 'home']},
            {'title': 'Moje zamówienia', 'url': url_for('orders.client_list'), 'keywords': ['zamówienia', 'orders', 'zamowienia']},
            {'title': 'Potwierdzenia', 'url': url_for('client.payment_confirmations'), 'keywords': ['platnosci', 'płatności', 'payment']},
            {'title': 'Zlecenia wysyłki', 'subtitle': 'Wysyłka', 'url': url_for('client.shipping_requests_list'), 'keywords': ['wysyłka', 'shipping', 'zlecenia']},
            {'title': 'Adresy dostaw', 'subtitle': 'Wysyłka', 'url': url_for('client.shipping_addresses'), 'keywords': ['adresy', 'addresses', 'adres']},
        ]


def _get_order_badge(status):
    """Returns badge info for order status."""
    badges = {
        'nowe': {'label': 'Nowe', 'bg': 'var(--badge-nowe-bg)', 'color': 'var(--badge-nowe-color)'},
        'oczekujace': {'label': 'Oczekujące', 'bg': 'var(--badge-oczekujace-bg)', 'color': 'var(--badge-oczekujace-color)'},
        'w_realizacji': {'label': 'W realizacji', 'bg': '#8b5cf6', 'color': '#fff'},
        'spakowane': {'label': 'Spakowane', 'bg': '#6366f1', 'color': '#fff'},
        'wyslane': {'label': 'Wysłane', 'bg': '#3b82f6', 'color': '#fff'},
        'dostarczone': {'label': 'Dostarczone', 'bg': '#10b981', 'color': '#fff'},
        'anulowane': {'label': 'Anulowane', 'bg': 'var(--badge-anulowane-bg)', 'color': 'var(--badge-anulowane-color)'},
    }
    return badges.get(status, {'label': status or '', 'bg': 'var(--bg-tertiary)', 'color': 'var(--text-secondary)'})


@api_bp.route('/popups/active', methods=['GET'])
@login_required
def get_active_popups():
    """
    Zwraca aktywne popupy dla zalogowanego użytkownika.
    Filtruje wg target_roles, display_mode i historii wyświetleń.
    """
    try:
        from modules.admin.popups_models import Popup, PopupView

        # Pobierz aktywne popupy posortowane wg priorytetu
        popups = Popup.query.filter_by(status='active').order_by(
            Popup.priority.asc()
        ).all()

        results = []
        for popup in popups:
            # Sprawdź targetowanie
            if not popup.is_targeted_at(current_user):
                continue

            # Sprawdź tryb wyświetlania
            if popup.display_mode == 'once':
                # Pomiń jeśli user już widział
                already_seen = PopupView.query.filter_by(
                    popup_id=popup.id,
                    user_id=current_user.id
                ).first()
                if already_seen:
                    continue

            elif popup.display_mode == 'first_login':
                # Pokaż tylko jeśli login_count <= 1 i nie widział jeszcze
                login_count = getattr(current_user, 'login_count', 1) or 1
                if login_count > 1:
                    continue
                already_seen = PopupView.query.filter_by(
                    popup_id=popup.id,
                    user_id=current_user.id
                ).first()
                if already_seen:
                    continue

            # every_login: zawsze pokaż (deduplikacja sesyjna na froncie)

            results.append({
                'id': popup.id,
                'title': popup.title,
                'content': popup.content,
                'display_mode': popup.display_mode,
                'cta_text': popup.cta_text,
                'cta_url': popup.cta_url,
                'cta_color': popup.cta_color,
                'bg_color': popup.bg_color,
                'modal_size': popup.modal_size
            })

        return jsonify({
            'success': True,
            'user_id': current_user.id,
            'popups': results
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Błąd pobierania popupów: {str(e)}'
        }), 500


@api_bp.route('/popups/<int:popup_id>/action', methods=['POST'])
@login_required
def popup_action(popup_id):
    """
    Rejestruje akcję użytkownika na popupie.
    Body JSON: { "action": "viewed" | "dismissed" | "cta_clicked" }
    """
    try:
        from modules.admin.popups_models import Popup, PopupView

        popup = Popup.query.get(popup_id)
        if not popup:
            return jsonify({'success': False, 'message': 'Popup nie znaleziony'}), 404

        data = request.get_json()
        action = data.get('action', '')

        if action not in ('viewed', 'dismissed', 'cta_clicked'):
            return jsonify({'success': False, 'message': 'Nieprawidłowa akcja'}), 400

        duration_ms = data.get('duration_ms')
        if duration_ms is not None:
            duration_ms = max(0, min(int(duration_ms), 600000))

        view = PopupView(
            popup_id=popup_id,
            user_id=current_user.id,
            action=action,
            duration_ms=duration_ms
        )
        db.session.add(view)
        db.session.commit()

        return jsonify({'success': True}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


def _get_exclusive_badge(status):
    """Returns badge info for exclusive page status."""
    badges = {
        'draft': {'label': 'Draft', 'bg': '#6b7280', 'color': '#fff'},
        'scheduled': {'label': 'Scheduled', 'bg': '#3b82f6', 'color': '#fff'},
        'active': {'label': 'Active', 'bg': '#10b981', 'color': '#fff'},
        'paused': {'label': 'Paused', 'bg': '#f59e0b', 'color': '#fff'},
        'ended': {'label': 'Ended', 'bg': '#6b7280', 'color': '#fff'},
    }
    return badges.get(status, {'label': status or '', 'bg': 'var(--bg-tertiary)', 'color': 'var(--text-secondary)'})
