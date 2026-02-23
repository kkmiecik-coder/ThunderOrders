"""
Admin Exclusive Pages Routes
Zarządzanie stronami ekskluzywnych zamówień (Page Builder)
"""

from flask import render_template, redirect, url_for, flash, request, jsonify, abort, Response
from flask_login import login_required, current_user
from markupsafe import Markup
from modules.admin import admin_bp
from utils.decorators import admin_required, mod_required
from extensions import db
from modules.exclusive.models import ExclusivePage, ExclusiveSection, ExclusiveSetItem
from modules.products.models import Product, ProductType, VariantGroup
from datetime import datetime
import json


# ============================================
# Lista stron Exclusive
# ============================================

@admin_bp.route('/exclusive')
@login_required
@admin_required
def exclusive_list():
    """Lista wszystkich stron exclusive"""
    from modules.orders.models import OrderStatus
    from modules.auth.models import Settings

    pages = ExclusivePage.query.order_by(ExclusivePage.created_at.desc()).all()

    # Automatyczna aktualizacja statusów (scheduled->active, active->ended)
    for page in pages:
        page.check_and_update_status()

    # Get statuses for settings form
    statuses = OrderStatus.query.filter_by(is_active=True).all()

    # Helper function to get setting value
    def get_setting_value(key, default):
        setting = Settings.query.filter_by(key=key).first()
        return setting.value if setting else default

    # Get exclusive closure settings
    exclusive_closure_settings = {
        'fully_fulfilled': get_setting_value('exclusive_closure_status_fully_fulfilled', 'oczekujace'),
        'partially_fulfilled': get_setting_value('exclusive_closure_status_partially_fulfilled', 'oczekujace'),
        'not_fulfilled': get_setting_value('exclusive_closure_status_not_fulfilled', 'anulowane')
    }

    # Get auto-increase global settings
    auto_increase_settings = {
        'enabled': get_setting_value('auto_increase_enabled', 'false') == 'true',
        'product_threshold': int(get_setting_value('auto_increase_product_threshold', '100')),
        'set_threshold': int(get_setting_value('auto_increase_set_threshold', '50')),
        'amount': int(get_setting_value('auto_increase_amount', '1'))
    }

    return render_template(
        'admin/exclusive/list.html',
        title='Strony Exclusive',
        pages=pages,
        statuses=statuses,
        exclusive_closure_settings=exclusive_closure_settings,
        auto_increase_settings=auto_increase_settings
    )


# ============================================
# Tworzenie nowej strony (modal submit)
# ============================================

@admin_bp.route('/exclusive/create', methods=['POST'])
@login_required
@admin_required
def exclusive_create():
    """Tworzy nową stronę exclusive (z modalu)"""
    name = request.form.get('name', '').strip()
    starts_at_str = request.form.get('starts_at', '').strip()
    ends_at_str = request.form.get('ends_at', '').strip()

    # Walidacja
    if not name:
        flash('Nazwa strony jest wymagana.', 'error')
        return redirect(url_for('admin.exclusive_list'))

    # Parse dates
    starts_at = None
    ends_at = None

    if starts_at_str:
        try:
            starts_at = datetime.strptime(starts_at_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Nieprawidłowy format daty rozpoczęcia.', 'error')
            return redirect(url_for('admin.exclusive_list'))

    if ends_at_str:
        try:
            ends_at = datetime.strptime(ends_at_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Nieprawidłowy format daty zakończenia.', 'error')
            return redirect(url_for('admin.exclusive_list'))

    # Walidacja dat
    if starts_at and ends_at and starts_at >= ends_at:
        flash('Data zakończenia musi być późniejsza niż data rozpoczęcia.', 'error')
        return redirect(url_for('admin.exclusive_list'))

    # Tworzenie strony
    page = ExclusivePage(
        name=name,
        token=ExclusivePage.generate_token(),
        status='draft',
        starts_at=starts_at,
        ends_at=ends_at,
        created_by=current_user.id
    )

    db.session.add(page)
    db.session.commit()

    flash(f'Strona "{name}" została utworzona.', 'success')
    return redirect(url_for('admin.exclusive_edit', page_id=page.id))


# ============================================
# Edycja strony (Page Builder)
# ============================================

@admin_bp.route('/exclusive/<int:page_id>/edit')
@login_required
@admin_required
def exclusive_edit(page_id):
    """Page Builder - edycja strony exclusive"""
    page = ExclusivePage.query.get_or_404(page_id)
    sections = page.get_sections_ordered()

    # Pobierz tylko produkty typu "Exclusive"
    exclusive_type = ProductType.query.filter_by(slug='exclusive').first()
    if exclusive_type:
        products = Product.query.filter_by(
            is_active=True,
            product_type_id=exclusive_type.id
        ).order_by(Product.name).all()
    else:
        products = []

    # Pobierz grupy wariantowe które mają produkty typu Exclusive
    variant_groups = []
    if exclusive_type:
        # Znajdź grupy wariantowe z produktami Exclusive
        from sqlalchemy import exists, and_
        from modules.products.models import variant_products

        variant_groups = VariantGroup.query.filter(
            VariantGroup.products.any(
                and_(
                    Product.is_active == True,
                    Product.product_type_id == exclusive_type.id
                )
            )
        ).order_by(VariantGroup.name).all()

    return render_template(
        'admin/exclusive/edit.html',
        title=f'Edycja: {page.name}',
        page=page,
        sections=sections,
        products=products,
        variant_groups=variant_groups
    )


# ============================================
# API - Zapisywanie strony (auto-save + manual)
# ============================================

@admin_bp.route('/exclusive/<int:page_id>/save', methods=['POST'])
@login_required
@admin_required
def exclusive_save(page_id):
    """
    Zapisuje stronę exclusive (AJAX)
    Obsługuje zarówno auto-save jak i ręczny zapis
    """
    page = ExclusivePage.query.get_or_404(page_id)
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'error': 'Brak danych'}), 400

    try:
        # Aktualizacja podstawowych danych strony
        if 'name' in data:
            page.name = data['name'].strip()

        if 'description' in data:
            page.description = data['description'].strip() if data['description'] else None

        if 'footer_content' in data:
            page.footer_content = data['footer_content'].strip() if data['footer_content'] else None

        if 'starts_at' in data:
            if data['starts_at']:
                new_starts_at = datetime.strptime(data['starts_at'], '%Y-%m-%dT%H:%M')
                page.starts_at = new_starts_at

                # Jeśli strona jest aktywna a nowa data rozpoczęcia jest w przyszłości,
                # zmień status na "scheduled"
                if page.status == 'active' and new_starts_at > datetime.now():
                    page.status = 'scheduled'
            else:
                page.starts_at = None

        if 'ends_at' in data:
            if data['ends_at']:
                page.ends_at = datetime.strptime(data['ends_at'], '%Y-%m-%dT%H:%M')
            else:
                page.ends_at = None

        if 'payment_stages' in data:
            payment_stages = int(data['payment_stages'])
            if payment_stages in (3, 4):
                page.payment_stages = payment_stages

        if 'notify_clients_on_publish' in data:
            page.notify_clients_on_publish = bool(data['notify_clients_on_publish'])

        # Aktualizacja sekcji
        limit_changes = []
        if 'sections' in data:
            limit_changes = _update_sections(page, data['sections'])

        # Ręcznie aktualizuj updated_at (onupdate nie działa przy zmianach w relacjach)
        page.updated_at = datetime.now()

        db.session.commit()

        # Po commit wysyłamy powiadomienia dla sekcji z zwiększonymi limitami
        if limit_changes:
            _send_notifications_for_limit_changes(page.id, limit_changes)

        return jsonify({
            'success': True,
            'message': 'Zapisano',
            'updated_at': page.updated_at.strftime('%H:%M:%S') if page.updated_at else None
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


def _validate_section_data(section_data):
    """
    Waliduje dane sekcji przed zapisem

    Args:
        section_data: Dane sekcji z frontendu

    Returns:
        tuple: (valid: bool, error: str or None)
    """
    section_type = section_data.get('type')

    # Walidacja sekcji "set"
    if section_type == 'set':
        # Wymagane: set_product_id
        set_product_id = section_data.get('set_product_id')
        if not set_product_id:
            return False, 'Musisz wybrać produkt-komplet dla sekcji Set'

        # Sprawdź czy produkt istnieje i jest typu "exclusive"
        product = Product.query.get(set_product_id)
        if not product:
            return False, 'Wybrany produkt nie istnieje'

        # Sprawdź typ produktu
        if product.product_type and product.product_type.slug != 'exclusive':
            return False, 'Produkt-komplet musi być typu Exclusive'

    return True, None


def _update_sections(page, sections_data):
    """
    Aktualizuje sekcje strony

    Args:
        page: ExclusivePage object
        sections_data: Lista danych sekcji z frontendu

    Returns:
        list: Lista krotek (section, old_max, new_max, section_type) dla sekcji z zmienionymi limitami
    """
    # Pobierz istniejące sekcje
    existing_sections = {s.id: s for s in page.sections.all()}
    existing_ids = set(existing_sections.keys())
    incoming_ids = set()

    # Śledzenie zmian limitów do powiadomień
    limit_changes = []

    for idx, section_data in enumerate(sections_data):
        # WALIDACJA - sprawdź dane sekcji przed zapisem
        valid, error = _validate_section_data(section_data)
        if not valid:
            raise ValueError(error)

        section_id = section_data.get('id')

        if section_id and section_id in existing_sections:
            # Aktualizacja istniejącej sekcji
            section = existing_sections[section_id]
            incoming_ids.add(section_id)

            # Zapamiętaj stare wartości przed zmianą
            old_max_quantity = section.max_quantity
            old_set_max_sets = section.set_max_sets
        else:
            # Nowa sekcja
            section = ExclusiveSection(exclusive_page_id=page.id)
            db.session.add(section)
            old_max_quantity = None
            old_set_max_sets = None

        # Pobierz nowe wartości
        new_max_quantity = section_data.get('max_quantity')
        new_set_max_sets = section_data.get('set_max_sets')
        section_type = section_data.get('type', 'paragraph')

        # Aktualizacja danych sekcji
        section.section_type = section_type
        section.sort_order = idx
        section.content = section_data.get('content')
        section.product_id = section_data.get('product_id')
        section.min_quantity = section_data.get('min_quantity')
        section.max_quantity = new_max_quantity
        section.set_name = section_data.get('set_name')
        section.set_image = section_data.get('set_image')
        section.set_max_sets = new_set_max_sets
        # set_max_per_product: 0 oznacza brak limitu, wartość > 0 to limit sztuk na produkt
        max_per_product = section_data.get('set_max_per_product', 0)
        section.set_max_per_product = max_per_product if max_per_product and max_per_product > 0 else None
        section.variant_group_id = section_data.get('variant_group_id')
        section.set_product_id = section_data.get('set_product_id')  # NOWE: Produkt-komplet dla setu

        # Obsługa elementów setu
        if section.section_type == 'set' and 'set_items' in section_data:
            _update_set_items(section, section_data['set_items'])

        # Zapisz zmiany limitów do późniejszego sprawdzenia powiadomień
        if section_type in ['product', 'variant_group']:
            if old_max_quantity is not None and new_max_quantity is not None:
                if new_max_quantity > old_max_quantity:
                    limit_changes.append((section, old_max_quantity, new_max_quantity, section_type))
        elif section_type == 'set':
            if old_set_max_sets is not None and new_set_max_sets is not None:
                if new_set_max_sets > old_set_max_sets:
                    limit_changes.append((section, old_set_max_sets, new_set_max_sets, section_type))

    # Usuń sekcje które nie są w incoming_ids
    sections_to_delete = existing_ids - incoming_ids
    for section_id in sections_to_delete:
        db.session.delete(existing_sections[section_id])

    # Zwróć informacje o zmianach limitów
    return limit_changes


def _update_set_items(section, items_data):
    """
    Aktualizuje elementy setu

    Args:
        section: ExclusiveSection object (type='set')
        items_data: Lista danych elementów setu (mogą być produkty lub grupy wariantowe)
    """
    # Usuń istniejące elementy
    ExclusiveSetItem.query.filter_by(section_id=section.id).delete()

    # Dodaj nowe
    for idx, item_data in enumerate(items_data):
        product_id = item_data.get('product_id')
        variant_group_id = item_data.get('variant_group_id')

        # Element musi mieć albo product_id albo variant_group_id
        if product_id or variant_group_id:
            item = ExclusiveSetItem(
                section_id=section.id,
                product_id=product_id if product_id else None,
                variant_group_id=variant_group_id if variant_group_id else None,
                quantity_per_set=item_data.get('quantity_per_set', 1),
                sort_order=idx
            )
            db.session.add(item)


def _send_notifications_for_limit_changes(page_id, limit_changes):
    """
    Wysyła powiadomienia o dostępności dla sekcji z zwiększonymi limitami.

    Args:
        page_id (int): ID strony exclusive
        limit_changes (list): Lista krotek (section, old_max, new_max, section_type)
    """
    try:
        from utils.exclusive_notifications import (
            check_and_send_notifications_for_section,
            check_and_send_notifications_for_product_section
        )

        for section, old_max, new_max, section_type in limit_changes:
            try:
                if section_type == 'set':
                    # Dla sekcji typu 'set' używamy funkcji sprawdzającej całą sekcję
                    sent = check_and_send_notifications_for_section(
                        page_id=page_id,
                        section_id=section.id,
                        old_max=old_max,
                        new_max=new_max
                    )
                else:
                    # Dla sekcji typu 'product' lub 'variant_group'
                    sent = check_and_send_notifications_for_product_section(
                        page_id=page_id,
                        section=section,
                        old_max_quantity=old_max
                    )

                if sent > 0:
                    print(f"[NOTIFICATIONS] Sent {sent} back-in-stock notifications for section {section.id}")
            except Exception as e:
                print(f"[NOTIFICATIONS] Failed to send notifications for section {section.id}: {e}")
    except Exception as e:
        print(f"[NOTIFICATIONS] Failed to import notification module: {e}")


# ============================================
# Zmiana statusu strony
# ============================================

@admin_bp.route('/exclusive/<int:page_id>/status', methods=['POST'])
@login_required
@admin_required
def exclusive_change_status(page_id):
    """Zmienia status strony exclusive"""
    page = ExclusivePage.query.get_or_404(page_id)
    data = request.get_json()
    action = data.get('action')

    if action == 'publish':
        # Publikuj natychmiast
        page.publish()
        message = 'Strona została opublikowana.'

        # Wyślij powiadomienie do klientów jeśli toggle włączony
        if page.notify_clients_on_publish:
            page._send_publish_notifications()
            message += ' Wysłano powiadomienie do klientów.'

    elif action == 'schedule':
        # Zaplanuj na datę startu
        if not page.starts_at:
            return jsonify({'success': False, 'error': 'Brak daty rozpoczęcia'}), 400
        page.schedule()
        message = f'Sprzedaż zaplanowana na {page.starts_at.strftime("%d.%m.%Y %H:%M")}.'

    elif action == 'pause':
        # Wstrzymaj sprzedaż
        page.pause()
        message = 'Sprzedaż została wstrzymana.'

    elif action == 'resume':
        # Wznów sprzedaż
        page.resume()
        message = 'Sprzedaż została wznowiona.'

    elif action == 'end':
        # Zakończ sprzedaż
        page.end()
        message = 'Sprzedaż została zakończona.'

    elif action == 'draft':
        # Cofnij do draftu
        page.status = 'draft'
        message = 'Strona została cofnięta do wersji roboczej.'

    else:
        return jsonify({'success': False, 'error': 'Nieznana akcja'}), 400

    db.session.commit()

    return jsonify({
        'success': True,
        'message': message,
        'status': page.status
    })


# ============================================
# Usuwanie strony
# ============================================

@admin_bp.route('/exclusive/<int:page_id>/orders-count')
@login_required
@admin_required
def exclusive_orders_count(page_id):
    """Zwraca liczbę zamówień powiązanych ze stroną (AJAX)"""
    page = ExclusivePage.query.get_or_404(page_id)
    return jsonify({
        'success': True,
        'orders_count': page.orders.count()
    })


@admin_bp.route('/exclusive/<int:page_id>/delete', methods=['POST'])
@login_required
@admin_required
def exclusive_delete(page_id):
    """Usuwa stronę exclusive wraz z powiązanymi elementami"""
    import os
    from flask import current_app
    from utils.activity_logger import log_activity

    page = ExclusivePage.query.get_or_404(page_id)
    name = page.name
    page_id_for_log = page.id

    # 1. Zlicz zamówienia powiązane (przed usunięciem)
    orders_count = page.orders.count()

    # 2. Usuń pliki graficzne setów
    for section in page.sections:
        if section.set_image:
            # set_image może być ścieżką względną np. "uploads/exclusive/xxx.jpg"
            file_path = os.path.join(current_app.static_folder, section.set_image)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass  # Ignoruj błędy usuwania plików

    # 3. Usuń stronę (CASCADE zajmie się sekcjami, rezerwacjami, powiadomieniami)
    db.session.delete(page)
    db.session.commit()

    # 4. Zaloguj aktywność
    log_activity(
        user=current_user,
        action='exclusive_deleted',
        entity_type='exclusive',
        entity_id=page_id_for_log,
        old_value={'name': name, 'orders_count': orders_count},
        new_value=None
    )

    # Sprawdź czy to AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'redirect': url_for('admin.exclusive_list'),
            'orders_affected': orders_count,
            'message': f'Strona "{name}" została usunięta.'
        })

    # Dla non-AJAX - użyj flash
    flash(f'Strona "{name}" została usunięta.', 'success')
    return redirect(url_for('admin.exclusive_list'))


# ============================================
# API - Pobieranie produktów (dla selecta)
# ============================================

@admin_bp.route('/exclusive/api/products')
@login_required
@admin_required
def exclusive_api_products():
    """Zwraca listę produktów typu Exclusive do selecta (AJAX)"""
    query = request.args.get('q', '').strip()

    # Pobierz tylko produkty typu "Exclusive"
    exclusive_type = ProductType.query.filter_by(slug='exclusive').first()
    if not exclusive_type:
        return jsonify([])

    products_query = Product.query.filter_by(
        is_active=True,
        product_type_id=exclusive_type.id
    )

    if query:
        products_query = products_query.filter(
            db.or_(
                Product.name.ilike(f'%{query}%'),
                Product.sku.ilike(f'%{query}%')
            )
        )

    products = products_query.order_by(Product.name).limit(50).all()

    return jsonify([{
        'id': p.id,
        'name': p.name,
        'sku': p.sku,
        'price': float(p.sale_price) if p.sale_price else 0,
        'image': url_for('static', filename=p.primary_image.path_compressed) if p.primary_image else None
    } for p in products])


# ============================================
# API - Pobieranie grup wariantowych
# ============================================

@admin_bp.route('/exclusive/api/variant-groups')
@login_required
@admin_required
def exclusive_api_variant_groups():
    """Zwraca listę grup wariantowych z produktami typu Exclusive (AJAX)"""
    from sqlalchemy import and_

    exclusive_type = ProductType.query.filter_by(slug='exclusive').first()
    if not exclusive_type:
        return jsonify([])

    # Znajdź grupy wariantowe z produktami Exclusive
    variant_groups = VariantGroup.query.filter(
        VariantGroup.products.any(
            and_(
                Product.is_active == True,
                Product.product_type_id == exclusive_type.id
            )
        )
    ).order_by(VariantGroup.name).all()

    result = []
    for vg in variant_groups:
        # Pobierz produkty Exclusive z tej grupy
        exclusive_products = [p for p in vg.products
                             if p.is_active and p.product_type_id == exclusive_type.id]

        result.append({
            'id': vg.id,
            'name': vg.name,
            'product_count': len(exclusive_products),
            'products': [{
                'id': p.id,
                'name': p.name,
                'sku': p.sku,
                'price': float(p.sale_price) if p.sale_price else 0,
                'image': url_for('static', filename=p.primary_image.path_compressed) if p.primary_image else None
            } for p in exclusive_products]
        })

    return jsonify(result)


# ============================================
# API - Pobieranie pojedynczej grupy wariantowej
# ============================================

@admin_bp.route('/exclusive/api/variant-group/<int:group_id>')
@login_required
@admin_required
def exclusive_api_variant_group(group_id):
    """Zwraca pojedynczą grupę wariantową z produktami typu Exclusive (AJAX)"""
    from sqlalchemy import and_

    exclusive_type = ProductType.query.filter_by(slug='exclusive').first()
    if not exclusive_type:
        return jsonify({'error': 'Typ Exclusive nie istnieje'}), 404

    variant_group = VariantGroup.query.get(group_id)
    if not variant_group:
        return jsonify({'error': 'Grupa wariantowa nie istnieje'}), 404

    # Pobierz produkty Exclusive z tej grupy
    exclusive_products = [p for p in variant_group.products
                         if p.is_active and p.product_type_id == exclusive_type.id]

    return jsonify({
        'id': variant_group.id,
        'name': variant_group.name,
        'product_count': len(exclusive_products),
        'products': [{
            'id': p.id,
            'name': p.name,
            'sku': p.sku,
            'price': float(p.sale_price) if p.sale_price else 0,
            'image': url_for('static', filename=p.primary_image.path_compressed) if p.primary_image else None
        } for p in exclusive_products]
    })


# ============================================
# API - Upload obrazka seta
# ============================================

@admin_bp.route('/exclusive/api/upload-image', methods=['POST'])
@login_required
@admin_required
def exclusive_upload_image():
    """Upload obrazka dla seta lub innego elementu"""
    import os
    import uuid
    from werkzeug.utils import secure_filename

    if 'image' not in request.files:
        return jsonify({'success': False, 'error': 'Brak pliku'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Nie wybrano pliku'}), 400

    # Sprawdź rozszerzenie
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

    if file_ext not in allowed_extensions:
        return jsonify({'success': False, 'error': 'Niedozwolony typ pliku'}), 400

    try:
        # Generuj unikalną nazwę pliku
        unique_name = f"{uuid.uuid4().hex}.{file_ext}"

        # Ścieżka do zapisu
        upload_folder = os.path.join('static', 'uploads', 'exclusive')
        os.makedirs(upload_folder, exist_ok=True)

        file_path = os.path.join(upload_folder, unique_name)
        file.save(file_path)

        # Opcjonalnie: kompresuj obrazek
        try:
            from utils.image_processor import compress_image
            compress_image(file_path, max_width=1600, quality=85)
        except Exception:
            pass  # Jeśli nie ma image_processor, zapisz bez kompresji

        return jsonify({
            'success': True,
            'path': f'uploads/exclusive/{unique_name}',
            'url': url_for('static', filename=f'uploads/exclusive/{unique_name}')
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# Duplikowanie strony
# ============================================

@admin_bp.route('/exclusive/<int:page_id>/duplicate', methods=['POST'])
@login_required
@admin_required
def exclusive_duplicate(page_id):
    """Duplikuje stronę exclusive"""
    original = ExclusivePage.query.get_or_404(page_id)

    # Nowa strona
    new_page = ExclusivePage(
        name=f'{original.name} (kopia)',
        description=original.description,
        token=ExclusivePage.generate_token(),
        status='draft',
        footer_content=original.footer_content,
        payment_stages=original.payment_stages,
        created_by=current_user.id
    )
    db.session.add(new_page)
    db.session.flush()  # Aby uzyskać ID

    # Kopiuj sekcje
    for section in original.get_sections_ordered():
        new_section = ExclusiveSection(
            exclusive_page_id=new_page.id,
            section_type=section.section_type,
            sort_order=section.sort_order,
            content=section.content,
            product_id=section.product_id,
            min_quantity=section.min_quantity,
            max_quantity=section.max_quantity,
            set_name=section.set_name,
            set_image=section.set_image,
            set_max_sets=section.set_max_sets,
            set_max_per_product=section.set_max_per_product,
            set_product_id=section.set_product_id,
            variant_group_id=section.variant_group_id
        )
        db.session.add(new_section)
        db.session.flush()

        # Kopiuj elementy setu
        if section.section_type == 'set':
            for item in section.get_set_items_ordered():
                new_item = ExclusiveSetItem(
                    section_id=new_section.id,
                    product_id=item.product_id,
                    variant_group_id=item.variant_group_id,
                    quantity_per_set=item.quantity_per_set,
                    sort_order=item.sort_order
                )
                db.session.add(new_item)

    db.session.commit()

    flash(f'Strona została zduplikowana jako "{new_page.name}".', 'success')
    return redirect(url_for('admin.exclusive_edit', page_id=new_page.id))


# ============================================
# Całkowite zamknięcie strony Exclusive
# ============================================

@admin_bp.route('/exclusive/<int:page_id>/close-complete', methods=['POST'])
@login_required
@admin_required
def exclusive_close_complete(page_id):
    """
    Całkowicie zamyka stronę Exclusive.

    Wykonuje:
    1. Algorytm alokacji setów (pierwsi zamawiający dostają produkty)
    2. Ustawia flagę is_fully_closed
    3. Opcjonalnie wysyła emaile do klientów

    Tylko Admin może wykonać tę operację.
    """
    from utils.exclusive_closure import close_exclusive_page

    page = ExclusivePage.query.get_or_404(page_id)

    # Sprawdź warunki
    if page.status != 'ended':
        return jsonify({
            'success': False,
            'error': 'Strona musi mieć status "Zakończona" (ended) aby ją całkowicie zamknąć.'
        }), 400

    if page.is_fully_closed:
        return jsonify({
            'success': False,
            'error': 'Ta strona została już całkowicie zamknięta.'
        }), 400

    # Pobierz opcję wysyłki emaili
    data = request.get_json() or {}
    send_emails = data.get('send_emails', True)

    try:
        result = close_exclusive_page(
            page_id=page_id,
            user_id=current_user.id,
            send_emails=send_emails
        )

        return jsonify({
            'success': True,
            'message': 'Strona została całkowicie zamknięta.',
            'allocation': result.get('allocation'),
            'redirect': url_for('admin.exclusive_summary', page_id=page_id)
        })

    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Wystąpił błąd: {str(e)}'
        }), 500


# ============================================
# Podsumowanie zamkniętej strony Exclusive
# ============================================

@admin_bp.route('/exclusive/<int:page_id>/summary')
@login_required
@mod_required
def exclusive_summary(page_id):
    """
    Wyświetla podsumowanie sprzedaży dla zamkniętej strony Exclusive.

    Admin widzi pełne dane finansowe, Mod widzi wersję bez finansów.
    """
    from utils.exclusive_closure import get_page_summary

    page = ExclusivePage.query.get_or_404(page_id)

    # Sprawdź czy strona jest zamknięta
    if not page.is_fully_closed:
        flash('Ta strona nie została jeszcze całkowicie zamknięta.', 'warning')
        return redirect(url_for('admin.exclusive_list'))

    # Pobierz podsumowanie (Admin z finansami, Mod bez)
    include_financials = current_user.role == 'admin'
    summary = get_page_summary(page_id, include_financials=include_financials)

    # Serializacja zamówień do JSON dla JS (search, pagination, expand)
    import json
    orders_json_list = []
    for o in summary.get('orders', []):
        orders_json_list.append({
            'order_id': o['order_id'],
            'order_number': o['order_number'],
            'customer_name': o['customer_name'] or 'Gość',
            'customer_email': o['customer_email'] or '',
            'customer_phone': o.get('customer_phone') or '',
            'created_at': o['created_at'].strftime('%d.%m.%Y %H:%M') if o['created_at'] else '',
            'total_amount': o['total_amount'],
            'item_count': sum(item['quantity'] for item in o['order_items']),
            'items': o['order_items'],
            'has_unfulfilled': any(item['is_set_fulfilled'] is False for item in o['order_items']),
        })

    return render_template(
        'admin/exclusive/summary.html',
        title=f'Podsumowanie: {page.name}',
        page=page,
        summary=summary,
        include_financials=include_financials,
        orders_json=json.dumps(orders_json_list, default=str),
    )


# ============================================
# Aktualizacja ustawień Exclusive Closure
# ============================================

@admin_bp.route('/exclusive/settings', methods=['POST'])
@login_required
@admin_required
def update_exclusive_closure_settings():
    """Update exclusive closure settings"""
    from modules.auth.models import Settings
    from utils.activity_logger import log_activity
    import json

    # Get form data
    fully_fulfilled = request.form.get('exclusive_closure_status_fully_fulfilled')
    partially_fulfilled = request.form.get('exclusive_closure_status_partially_fulfilled')
    not_fulfilled = request.form.get('exclusive_closure_status_not_fulfilled')

    # Validate
    if not all([fully_fulfilled, partially_fulfilled, not_fulfilled]):
        flash('Wszystkie statusy muszą być wybrane.', 'error')
        return redirect(url_for('admin.exclusive_list'))

    # Helper function to set setting value
    def set_setting_value(key, value):
        setting = Settings.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = Settings(key=key, value=value, type='string')
            db.session.add(setting)

    # Update settings
    set_setting_value('exclusive_closure_status_fully_fulfilled', fully_fulfilled)
    set_setting_value('exclusive_closure_status_partially_fulfilled', partially_fulfilled)
    set_setting_value('exclusive_closure_status_not_fulfilled', not_fulfilled)
    db.session.commit()

    # Log activity
    log_activity(
        user=current_user,
        action='exclusive_closure_settings_updated',
        entity_type='exclusive_settings',
        entity_id=None,
        new_value=json.dumps({
            'fully_fulfilled': fully_fulfilled,
            'partially_fulfilled': partially_fulfilled,
            'not_fulfilled': not_fulfilled
        })
    )

    flash('Ustawienia automatycznego przenoszenia zostały zaktualizowane.', 'success')
    return redirect(url_for('admin.exclusive_list'))


# ============================================
# Aktualizacja globalnych ustawień Auto-zwiększania max
# ============================================

@admin_bp.route('/exclusive/settings/auto-increase', methods=['POST'])
@login_required
@admin_required
def update_global_auto_increase_settings():
    """Update global auto-increase settings (stored in settings table)"""
    from utils.activity_logger import log_activity
    from modules.auth.models import Settings
    import json

    # Get form data
    auto_increase_enabled = request.form.get('auto_increase_enabled') == 'true'
    auto_increase_product_threshold = request.form.get('auto_increase_product_threshold', type=int)
    auto_increase_set_threshold = request.form.get('auto_increase_set_threshold', type=int)
    auto_increase_amount = request.form.get('auto_increase_amount', type=int)

    # Validate
    if auto_increase_product_threshold is None or auto_increase_product_threshold < 0 or auto_increase_product_threshold > 100:
        return jsonify({'success': False, 'error': 'Próg wyprzedania produktu musi być między 0 a 100'}), 400

    if auto_increase_set_threshold is None or auto_increase_set_threshold < 0 or auto_increase_set_threshold > 100:
        return jsonify({'success': False, 'error': 'Próg wyprzedanych produktów w secie musi być między 0 a 100'}), 400

    if auto_increase_amount is None or auto_increase_amount < 1:
        return jsonify({'success': False, 'error': 'Zwiększenie max musi być co najmniej 1'}), 400

    # Helper function to update or create setting
    def update_setting(key, value):
        setting = Settings.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value)
        else:
            setting = Settings(key=key, value=str(value), type='string')
            db.session.add(setting)

    # Store old values for activity log
    def get_setting_value(key, default):
        setting = Settings.query.filter_by(key=key).first()
        return setting.value if setting else default

    old_values = {
        'enabled': get_setting_value('auto_increase_enabled', 'false') == 'true',
        'product_threshold': int(get_setting_value('auto_increase_product_threshold', '100')),
        'set_threshold': int(get_setting_value('auto_increase_set_threshold', '50')),
        'amount': int(get_setting_value('auto_increase_amount', '1'))
    }

    # Update settings in database
    update_setting('auto_increase_enabled', 'true' if auto_increase_enabled else 'false')
    update_setting('auto_increase_product_threshold', str(auto_increase_product_threshold))
    update_setting('auto_increase_set_threshold', str(auto_increase_set_threshold))
    update_setting('auto_increase_amount', str(auto_increase_amount))

    db.session.commit()

    # Log activity
    log_activity(
        user=current_user,
        action='global_auto_increase_settings_updated',
        entity_type='Settings',
        entity_id=None,
        old_value=json.dumps(old_values),
        new_value=json.dumps({
            'enabled': auto_increase_enabled,
            'product_threshold': auto_increase_product_threshold,
            'set_threshold': auto_increase_set_threshold,
            'amount': auto_increase_amount
        })
    )

    return jsonify({
        'success': True,
        'message': 'Ustawienia auto-zwiększania zostały zapisane.'
    })


# ============================================
# Export Excel zamkniętej strony Exclusive
# ============================================

@admin_bp.route('/exclusive/<int:page_id>/export-excel')
@login_required
@admin_required
def exclusive_export_excel(page_id):
    """
    Generuje i pobiera plik Excel z zamówieniami dla zamkniętej strony Exclusive.

    Tylko Admin może pobrać Excel.
    """
    from utils.excel_export import generate_exclusive_closure_excel
    from utils.exclusive_closure import get_page_summary

    page = ExclusivePage.query.get_or_404(page_id)

    # Sprawdź czy strona jest zamknięta
    if not page.is_fully_closed:
        flash('Ta strona nie została jeszcze całkowicie zamknięta.', 'warning')
        return redirect(url_for('admin.exclusive_list'))

    try:
        summary = get_page_summary(page_id, include_financials=True)
        excel_buffer = generate_exclusive_closure_excel(page, summary)

        # Generuj nazwę pliku
        safe_name = "".join(c for c in page.name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')[:50]  # Max 50 znaków
        filename = f'exclusive_{safe_name}_{page.closed_at.strftime("%Y%m%d")}.xlsx'

        return Response(
            excel_buffer.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }
        )

    except Exception as e:
        flash(f'Błąd generowania pliku Excel: {str(e)}', 'error')
        return redirect(url_for('admin.exclusive_summary', page_id=page_id))
