"""
Exclusive Module - Public Routes
Publiczne endpointy dla stron ekskluzywnych zamówień
"""

from flask import render_template, abort, redirect, url_for, request, jsonify, session
from flask_login import login_required, current_user
from . import exclusive_bp
from .models import ExclusivePage
from modules.products.models import Product, VariantGroup


@exclusive_bp.route('/countdown')
def countdown_page():
    """
    Dedykowana strona countdown - uniwersalny timer odliczający do startu

    Parametry URL:
    - page: token strony exclusive

    Po zakończeniu odliczania JS przekierowuje na właściwą stronę zamówienia.
    """
    token = request.args.get('page')

    if not token:
        abort(404)

    page = ExclusivePage.get_by_token(token)

    if not page:
        abort(404)

    # Sprawdź czy strona ma datę startu
    if not page.starts_at:
        # Brak daty startu - przekieruj na główną stronę
        return redirect(url_for('exclusive.order_page', token=token))

    # Automatyczna aktualizacja statusu
    page.check_and_update_status()

    # Jeśli strona już aktywna lub zakończona - przekieruj
    if page.is_active or page.is_ended or page.is_paused:
        return redirect(url_for('exclusive.order_page', token=token))

    return render_template('exclusive/countdown.html', page=page)


@exclusive_bp.route('/<token>')
def order_page(token):
    """
    Główna strona ekskluzywna - wyświetla odpowiedni widok w zależności od statusu

    Statusy:
    - draft: "Strona w przygotowaniu"
    - scheduled: Przekierowanie na /countdown?page=token
    - active: Formularz zamówień
    - paused: "Sprzedaż wstrzymana"
    - ended: "Sprzedaż zakończona"
    """
    page = ExclusivePage.get_by_token(token)

    if not page:
        abort(404)

    # Automatyczna aktualizacja statusu na podstawie dat
    page.check_and_update_status()

    # Routing na podstawie statusu
    if page.is_draft:
        return render_template('exclusive/draft.html', page=page)

    if page.is_scheduled:
        # Przekieruj na dedykowaną stronę countdown
        return redirect(url_for('exclusive.countdown_page', page=token))

    if page.is_active:
        # Cleanup wygasłych rezerwacji przy załadowaniu strony
        from modules.exclusive.reservation import cleanup_expired_reservations
        cleanup_expired_reservations(page.id)

        sections = page.get_sections_ordered()
        return render_template('exclusive/order_page.html', page=page, sections=sections)

    if page.is_paused:
        return render_template('exclusive/paused.html', page=page)

    if page.is_ended:
        return render_template('exclusive/ended.html', page=page)

    # Fallback
    abort(404)


@exclusive_bp.route('/<token>/thank-you')
def thank_you(token):
    """Strona podziękowania po złożeniu zamówienia"""
    page = ExclusivePage.get_by_token(token)

    if not page:
        abort(404)

    # Get order data from session (set after placing order)
    order_data = session.pop('last_order_data', None)

    return render_template('exclusive/thank_you.html', page=page, order_data=order_data)


@exclusive_bp.route('/<token>/preview')
@login_required
def preview_page(token):
    """
    Podgląd strony ekskluzywnej dla admina/moda
    Pokazuje stronę tak jakby była aktywna, niezależnie od statusu
    """
    # Sprawdź czy użytkownik ma uprawnienia (admin lub mod)
    if current_user.role not in ['admin', 'mod']:
        abort(403)

    page = ExclusivePage.get_by_token(token)

    if not page:
        abort(404)

    sections = page.get_sections_ordered()
    return render_template('exclusive/order_page.html', page=page, sections=sections, preview_mode=True)


@exclusive_bp.route('/<token>/status')
def check_status(token):
    """
    API endpoint do sprawdzania statusu strony (używany przez countdown i order-page)
    Zwraca aktualny status strony - pozwala wykryć:
    - Ręczną aktywację przez admina
    - Dodanie/zmianę daty końcowej
    - Ręczne zakończenie sprzedaży
    """
    page = ExclusivePage.get_by_token(token)

    if not page:
        return jsonify({'error': 'Page not found'}), 404

    # Automatyczna aktualizacja statusu na podstawie dat
    page.check_and_update_status()

    return jsonify({
        'status': page.status,
        'is_active': page.is_active,
        'ends_at': page.ends_at.isoformat() if page.ends_at else None,
        'is_manually_closed': page.status == 'closed'
    })


# ============================================
# Reservation API Endpoints
# ============================================

@exclusive_bp.route('/<token>/reserve', methods=['POST'])
def reserve(token):
    """Reserve product"""
    from modules.exclusive.reservation import reserve_product
    from modules.exclusive.models import ExclusiveSection, ExclusiveSetItem
    from modules.products.models import Product, VariantGroup, variant_products
    from extensions import db

    page = ExclusivePage.get_by_token(token)
    if not page:
        return jsonify({'success': False, 'error': 'page_not_found'}), 404

    data = request.get_json()
    session_id = data.get('session_id')
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)

    if not session_id or not product_id:
        return jsonify({'success': False, 'error': 'missing_params'}), 400

    section_max = None

    # 1. Check direct product section
    section = ExclusiveSection.query.filter_by(
        exclusive_page_id=page.id,
        section_type='product',
        product_id=product_id
    ).first()

    if section:
        section_max = section.max_quantity
    else:
        # 2. Check if product belongs to a variant_group section (not in set)
        # First find which variant groups this product belongs to
        product_vg_ids = db.session.query(variant_products.c.variant_group_id).filter(
            variant_products.c.product_id == product_id
        ).all()
        product_vg_ids = [vg_id for (vg_id,) in product_vg_ids]

        if product_vg_ids:
            # Check if any of these variant groups has a direct section
            vg_section = ExclusiveSection.query.filter(
                ExclusiveSection.exclusive_page_id == page.id,
                ExclusiveSection.section_type == 'variant_group',
                ExclusiveSection.variant_group_id.in_(product_vg_ids)
            ).first()

            if vg_section:
                section_max = vg_section.max_quantity

        if section_max is None:
            # 3. Check if product is directly in a set (via set_items)
            set_item = ExclusiveSetItem.query.join(ExclusiveSection).filter(
                ExclusiveSection.exclusive_page_id == page.id,
                ExclusiveSection.section_type == 'set',
                ExclusiveSetItem.product_id == product_id
            ).first()

            if set_item:
                # Use set's max_sets limit (ARCHITECTURE: 1 set = 1 of each product)
                section_max = set_item.section.set_max_sets
            elif product_vg_ids:
                # 4. Check if product's variant group is in a set
                set_item_vg = ExclusiveSetItem.query.join(ExclusiveSection).filter(
                    ExclusiveSection.exclusive_page_id == page.id,
                    ExclusiveSection.section_type == 'set',
                    ExclusiveSetItem.variant_group_id.in_(product_vg_ids)
                ).first()
                if set_item_vg:
                    section_max = set_item_vg.section.set_max_sets

    # section_max = None means unlimited (will be treated as float('inf') in reserve_product)

    success, result = reserve_product(
        session_id=session_id,
        page_id=page.id,
        product_id=product_id,
        quantity=quantity,
        section_max=section_max
    )

    if success:
        return jsonify({'success': True, **result})
    else:
        return jsonify({'success': False, **result}), 409


@exclusive_bp.route('/<token>/release', methods=['POST'])
def release(token):
    """Release product"""
    from modules.exclusive.reservation import release_product

    page = ExclusivePage.get_by_token(token)
    if not page:
        return jsonify({'success': False, 'error': 'page_not_found'}), 404

    data = request.get_json()
    session_id = data.get('session_id')
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)

    success, result = release_product(
        session_id=session_id,
        page_id=page.id,
        product_id=product_id,
        quantity=quantity
    )

    return jsonify({'success': True, **result})


@exclusive_bp.route('/<token>/availability', methods=['GET'])
def availability(token):
    """Get availability snapshot"""
    from modules.exclusive.reservation import get_availability_snapshot
    from modules.exclusive.models import ExclusiveSection, ExclusiveSetItem
    from modules.products.models import Product, VariantGroup, variant_products

    page = ExclusivePage.get_by_token(token)
    if not page:
        return jsonify({'success': False, 'error': 'page_not_found'}), 404

    session_id = request.args.get('session_id')

    # Get all products from page sections
    sections = ExclusiveSection.query.filter_by(exclusive_page_id=page.id).all()
    section_products = {}

    for section in sections:
        if section.section_type == 'product' and section.product_id:
            # Direct product section
            section_products[section.product_id] = section.max_quantity

        elif section.section_type == 'variant_group' and section.variant_group_id:
            # Variant group section - get all products from the group
            products = Product.query.join(
                Product.variant_groups
            ).filter(
                VariantGroup.id == section.variant_group_id,
                Product.is_active == True
            ).all()
            for product in products:
                section_products[product.id] = section.max_quantity

        elif section.section_type == 'set':
            # SET section - get all products from set items
            # ARCHITECTURE: 1 set = 1 piece of each product, all products share set_max_sets
            product_limit = section.set_max_sets
            set_items = ExclusiveSetItem.query.filter_by(section_id=section.id).all()

            for set_item in set_items:
                if set_item.product_id:
                    # Direct product in set
                    section_products[set_item.product_id] = product_limit
                elif set_item.variant_group_id:
                    # Variant group in set - get all products from the group
                    vg_products = Product.query.join(
                        Product.variant_groups
                    ).filter(
                        VariantGroup.id == set_item.variant_group_id,
                        Product.is_active == True
                    ).all()
                    for product in vg_products:
                        section_products[product.id] = product_limit

    products_data, session_info = get_availability_snapshot(
        page_id=page.id,
        section_products=section_products,
        session_id=session_id
    )

    return jsonify({
        'success': True,
        'products': products_data,
        'session': session_info
    })


@exclusive_bp.route('/<token>/extend', methods=['POST'])
def extend(token):
    """Extend reservation"""
    from modules.exclusive.reservation import extend_reservation

    page = ExclusivePage.get_by_token(token)
    if not page:
        return jsonify({'success': False, 'error': 'page_not_found'}), 404

    data = request.get_json()
    session_id = data.get('session_id')

    success, result = extend_reservation(
        session_id=session_id,
        page_id=page.id
    )

    if success:
        return jsonify({'success': True, **result})
    else:
        return jsonify({'success': False, **result}), 400


@exclusive_bp.route('/<token>/restore', methods=['POST'])
def restore(token):
    """Restore reservation from localStorage"""
    from modules.exclusive.reservation import cleanup_expired_reservations, get_user_reservation
    from modules.exclusive.models import ExclusiveReservation

    page = ExclusivePage.get_by_token(token)
    if not page:
        return jsonify({'success': False, 'error': 'page_not_found'}), 404

    data = request.get_json()
    session_id = data.get('session_id')
    products = data.get('products', {})

    # Cleanup expired
    cleanup_expired_reservations(page.id)

    restored = {}
    expired = []

    for product_id_str, product_data in products.items():
        product_id = int(product_id_str)

        # Check if this is a full set product (no reservation system)
        is_full_set = product_data.get('isFullSet', False) if isinstance(product_data, dict) else False

        if is_full_set:
            # Full set products don't have reservations - restore directly from localStorage
            qty = product_data.get('quantity', 0) if isinstance(product_data, dict) else product_data
            restored[product_id] = qty
        else:
            # Regular product - check reservation
            reservation = get_user_reservation(session_id, page.id, product_id)

            if reservation:
                restored[product_id] = reservation.quantity
            else:
                expired.append(product_id)

    # Get session info
    first_reservation = ExclusiveReservation.query.filter_by(
        session_id=session_id,
        exclusive_page_id=page.id
    ).order_by(ExclusiveReservation.reserved_at).first()

    session_info = {}
    if first_reservation:
        session_info['expires_at'] = first_reservation.expires_at
        session_info['first_reserved_at'] = first_reservation.reserved_at

    return jsonify({
        'success': True,
        'restored': restored,
        'expired': expired,
        'session': session_info
    })


# ============================================
# Order Placement Endpoint
# ============================================

@exclusive_bp.route('/<token>/place-order', methods=['POST'])
def place_order(token):
    """
    Place an order from exclusive page
    Supports both authenticated users and guests
    """
    from modules.exclusive.place_order import place_exclusive_order

    page = ExclusivePage.get_by_token(token)
    if not page:
        return jsonify({'success': False, 'error': 'page_not_found'}), 404

    # Check if page is active
    if not page.is_active:
        return jsonify({'success': False, 'error': 'page_not_active', 'message': 'Sprzedaż nie jest aktywna'}), 403

    data = request.get_json()
    session_id = data.get('session_id')
    guest_data = data.get('guest_data')
    order_note = data.get('order_note')

    if not session_id:
        return jsonify({'success': False, 'error': 'missing_session_id'}), 400

    # Place order
    success, result = place_exclusive_order(
        page=page,
        session_id=session_id,
        guest_data=guest_data,
        order_note=order_note
    )

    if success:
        # Save order data in session for thank_you page
        session['last_order_data'] = {
            'order_id': result.get('order_id'),
            'order_number': result.get('order_number'),
            'total_amount': result.get('total_amount'),
            'items_count': result.get('items_count'),
            'is_guest': result.get('is_guest'),
            'guest_view_token': result.get('guest_view_token'),
            'guest_name': result.get('guest_name'),
            'guest_email': result.get('guest_email'),
            'guest_phone': result.get('guest_phone')
        }
        return jsonify({'success': True, **result})
    else:
        return jsonify({'success': False, **result}), 400


# ============================================
# Notification Subscription Endpoint
# ============================================

@exclusive_bp.route('/<token>/subscribe-notification', methods=['POST'])
def subscribe_notification(token):
    """
    Zapisuje użytkownika na powiadomienie o dostępności produktu.

    Dla zalogowanych użytkowników: używa email z konta.
    Dla gości: wymaga podania email w body.

    Request body:
    {
        "product_id": 123,
        "email": "guest@example.com"  // tylko dla gości
    }
    """
    from .models import ExclusiveProductNotificationSubscription, ExclusiveSection, ExclusiveSetItem
    from modules.products.models import Product, VariantGroup, variant_products
    from extensions import db
    import re

    page = ExclusivePage.get_by_token(token)
    if not page:
        return jsonify({'success': False, 'error': 'page_not_found'}), 404

    # Sprawdź czy strona jest aktywna
    if not page.is_active:
        return jsonify({'success': False, 'error': 'page_not_active', 'message': 'Strona nie jest aktywna'}), 403

    data = request.get_json()
    product_id = data.get('product_id')
    guest_email = data.get('email')

    if not product_id:
        return jsonify({'success': False, 'error': 'missing_product_id', 'message': 'Brak ID produktu'}), 400

    # Sprawdź czy produkt istnieje
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'success': False, 'error': 'product_not_found', 'message': 'Produkt nie istnieje'}), 404

    # Sprawdź czy produkt jest na tej stronie exclusive
    product_on_page = False

    # Sprawdź sekcje typu 'product'
    product_section = ExclusiveSection.query.filter_by(
        exclusive_page_id=page.id,
        section_type='product',
        product_id=product_id
    ).first()

    if product_section:
        product_on_page = True
    else:
        # Sprawdź w grupach wariantów
        product_vg_ids = db.session.query(variant_products.c.variant_group_id).filter(
            variant_products.c.product_id == product_id
        ).all()
        product_vg_ids = [vg_id for (vg_id,) in product_vg_ids]

        if product_vg_ids:
            vg_section = ExclusiveSection.query.filter(
                ExclusiveSection.exclusive_page_id == page.id,
                ExclusiveSection.section_type == 'variant_group',
                ExclusiveSection.variant_group_id.in_(product_vg_ids)
            ).first()

            if vg_section:
                product_on_page = True

        if not product_on_page:
            # Sprawdź w setach (bezpośrednio lub przez grupę wariantów)
            set_item = ExclusiveSetItem.query.join(ExclusiveSection).filter(
                ExclusiveSection.exclusive_page_id == page.id,
                ExclusiveSection.section_type == 'set',
                ExclusiveSetItem.product_id == product_id
            ).first()

            if set_item:
                product_on_page = True
            elif product_vg_ids:
                set_item_vg = ExclusiveSetItem.query.join(ExclusiveSection).filter(
                    ExclusiveSection.exclusive_page_id == page.id,
                    ExclusiveSection.section_type == 'set',
                    ExclusiveSetItem.variant_group_id.in_(product_vg_ids)
                ).first()
                if set_item_vg:
                    product_on_page = True

    if not product_on_page:
        return jsonify({'success': False, 'error': 'product_not_on_page', 'message': 'Produkt nie jest dostępny na tej stronie'}), 400

    # Określ user_id lub guest_email
    user_id = None
    email_to_notify = None

    if current_user.is_authenticated:
        user_id = current_user.id
        email_to_notify = current_user.email
    else:
        # Gość - wymaga email
        if not guest_email:
            return jsonify({'success': False, 'error': 'missing_email', 'message': 'Podaj adres email'}), 400

        # Walidacja email
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, guest_email):
            return jsonify({'success': False, 'error': 'invalid_email', 'message': 'Nieprawidłowy format email'}), 400

        email_to_notify = guest_email.strip().lower()

    # Sprawdź czy już istnieje subskrypcja
    existing_query = ExclusiveProductNotificationSubscription.query.filter_by(
        exclusive_page_id=page.id,
        product_id=product_id,
        notified=False
    )

    if user_id:
        existing = existing_query.filter_by(user_id=user_id).first()
    else:
        existing = existing_query.filter_by(guest_email=email_to_notify).first()

    if existing:
        return jsonify({
            'success': True,
            'already_subscribed': True,
            'message': 'Już zapisano na powiadomienie o tym produkcie'
        })

    # Utwórz subskrypcję
    subscription = ExclusiveProductNotificationSubscription(
        exclusive_page_id=page.id,
        product_id=product_id,
        user_id=user_id,
        guest_email=email_to_notify if not user_id else None,
        notified=False
    )

    db.session.add(subscription)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Zapisano! Otrzymasz powiadomienie gdy produkt będzie dostępny.',
        'email': email_to_notify
    })
