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
    pages = ExclusivePage.query.order_by(ExclusivePage.created_at.desc()).all()

    # Automatyczna aktualizacja statusów (scheduled->active, active->ended)
    for page in pages:
        page.check_and_update_status()

    return render_template(
        'admin/exclusive/list.html',
        title='Strony Exclusive',
        pages=pages
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

        # Aktualizacja sekcji
        if 'sections' in data:
            _update_sections(page, data['sections'])

        # Ręcznie aktualizuj updated_at (onupdate nie działa przy zmianach w relacjach)
        page.updated_at = datetime.now()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Zapisano',
            'updated_at': page.updated_at.strftime('%H:%M:%S') if page.updated_at else None
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


def _update_sections(page, sections_data):
    """
    Aktualizuje sekcje strony

    Args:
        page: ExclusivePage object
        sections_data: Lista danych sekcji z frontendu
    """
    # Pobierz istniejące sekcje
    existing_sections = {s.id: s for s in page.sections.all()}
    existing_ids = set(existing_sections.keys())
    incoming_ids = set()

    for idx, section_data in enumerate(sections_data):
        section_id = section_data.get('id')

        if section_id and section_id in existing_sections:
            # Aktualizacja istniejącej sekcji
            section = existing_sections[section_id]
            incoming_ids.add(section_id)
        else:
            # Nowa sekcja
            section = ExclusiveSection(exclusive_page_id=page.id)
            db.session.add(section)

        # Aktualizacja danych sekcji
        section.section_type = section_data.get('type', 'paragraph')
        section.sort_order = idx
        section.content = section_data.get('content')
        section.product_id = section_data.get('product_id')
        section.min_quantity = section_data.get('min_quantity')
        section.max_quantity = section_data.get('max_quantity')
        section.set_name = section_data.get('set_name')
        section.set_image = section_data.get('set_image')
        section.set_min_sets = section_data.get('set_min_sets', 1)
        section.set_max_sets = section_data.get('set_max_sets')
        # set_max_per_product: 0 oznacza brak limitu, wartość > 0 to limit sztuk na produkt
        max_per_product = section_data.get('set_max_per_product', 0)
        section.set_max_per_product = max_per_product if max_per_product and max_per_product > 0 else None
        section.variant_group_id = section_data.get('variant_group_id')

        # Obsługa elementów setu
        if section.section_type == 'set' and 'set_items' in section_data:
            _update_set_items(section, section_data['set_items'])

    # Usuń sekcje które nie są w incoming_ids
    sections_to_delete = existing_ids - incoming_ids
    for section_id in sections_to_delete:
        db.session.delete(existing_sections[section_id])


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

@admin_bp.route('/exclusive/<int:page_id>/delete', methods=['POST'])
@login_required
@admin_required
def exclusive_delete(page_id):
    """Usuwa stronę exclusive"""
    page = ExclusivePage.query.get_or_404(page_id)
    name = page.name

    db.session.delete(page)
    db.session.commit()

    flash(Markup(f'Strona <strong style="color: #7B2CBF;">{name}</strong> została usunięta.'), 'success')

    # Sprawdź czy to AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'redirect': url_for('admin.exclusive_list')})

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
            set_min_sets=section.set_min_sets,
            set_max_sets=section.set_max_sets,
            set_max_per_product=section.set_max_per_product,
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

    return render_template(
        'admin/exclusive/summary.html',
        title=f'Podsumowanie: {page.name}',
        page=page,
        summary=summary,
        include_financials=include_financials
    )


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

    page = ExclusivePage.query.get_or_404(page_id)

    # Sprawdź czy strona jest zamknięta
    if not page.is_fully_closed:
        flash('Ta strona nie została jeszcze całkowicie zamknięta.', 'warning')
        return redirect(url_for('admin.exclusive_list'))

    try:
        excel_buffer = generate_exclusive_closure_excel(page_id)

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
