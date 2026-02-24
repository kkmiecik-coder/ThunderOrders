"""
Popups Admin Routes
Zarządzanie popupami/ogłoszeniami w panelu admina
"""

import os
import uuid
import json
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from extensions import db
from utils.decorators import role_required
from . import admin_bp
from .popups_models import Popup, PopupView


@admin_bp.route('/popups')
@login_required
@role_required('admin', 'mod')
def popups_list():
    """Lista wszystkich popupów z filtrami statusu"""
    status_filter = request.args.get('status', 'all')

    query = Popup.query

    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    popups = query.order_by(Popup.priority.asc(), Popup.created_at.desc()).all()

    return render_template(
        'admin/popups/list.html',
        popups=popups,
        status_filter=status_filter
    )


@admin_bp.route('/popups/create', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def popup_create():
    """Tworzenie nowego popupa"""
    if request.method == 'POST':
        return _save_popup(None)

    return render_template('admin/popups/form.html', popup=None)


@admin_bp.route('/popups/<int:popup_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'mod')
def popup_edit(popup_id):
    """Edycja istniejącego popupa"""
    popup = Popup.query.get_or_404(popup_id)

    if request.method == 'POST':
        return _save_popup(popup)

    return render_template('admin/popups/form.html', popup=popup)


def _save_popup(popup):
    """Wspólna logika zapisu popupa (tworzenie i edycja)"""
    try:
        is_new = popup is None
        if is_new:
            popup = Popup()
            popup.created_by = current_user.id

        popup.title = request.form.get('title', '').strip()
        popup.content = request.form.get('content', '').strip()
        popup.display_mode = request.form.get('display_mode', 'once')
        popup.modal_size = request.form.get('modal_size', 'md')
        popup.priority = int(request.form.get('priority', 0))
        popup.cta_text = request.form.get('cta_text', '').strip() or None
        popup.cta_url = request.form.get('cta_url', '').strip() or None
        popup.cta_color = request.form.get('cta_color', '').strip() or '#f093fb'
        popup.bg_color = request.form.get('bg_color', '').strip() or None

        # Targetowanie ról
        target_roles = request.form.getlist('target_roles')
        popup.set_target_roles(target_roles if target_roles else None)

        # Tytuł jest opcjonalny - jeśli pusty, nagłówek się nie wyświetla
        popup.title = popup.title or None

        if not popup.content:
            flash('Treść jest wymagana.', 'error')
            return render_template('admin/popups/form.html', popup=popup)

        if is_new:
            db.session.add(popup)

        db.session.commit()
        flash(
            'Popup został utworzony.' if is_new else 'Popup został zaktualizowany.',
            'success'
        )
        return redirect(url_for('admin.popups_list'))

    except Exception as e:
        db.session.rollback()
        import logging
        logging.getLogger(__name__).error(f'Błąd zapisu popupa: {e}')
        flash('Wystąpił błąd podczas zapisu. Spróbuj ponownie.', 'error')
        return render_template('admin/popups/form.html', popup=popup)


@admin_bp.route('/popups/<int:popup_id>/toggle', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def popup_toggle(popup_id):
    """Przełączanie statusu popupa (AJAX)"""
    try:
        popup = Popup.query.get_or_404(popup_id)

        if popup.status == 'active':
            popup.status = 'archived'
        elif popup.status in ('draft', 'archived'):
            popup.status = 'active'

        db.session.commit()

        return jsonify({
            'success': True,
            'new_status': popup.status,
            'message': f'Status zmieniony na: {popup.status}'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


@admin_bp.route('/popups/<int:popup_id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def popup_delete(popup_id):
    """Usunięcie popupa (AJAX)"""
    try:
        popup = Popup.query.get_or_404(popup_id)
        db.session.delete(popup)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Popup został usunięty.'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


@admin_bp.route('/popups/<int:popup_id>/reset', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def popup_reset(popup_id):
    """Reset popupa - usuwa statystyki i historię wyświetleń (AJAX)"""
    try:
        popup = Popup.query.get_or_404(popup_id)

        # Usuń wszystkie rekordy wyświetleń
        deleted = PopupView.query.filter_by(popup_id=popup.id).delete()
        db.session.commit()

        return jsonify({
            'success': True,
            'deleted': deleted,
            'message': f'Zresetowano popup - usunięto {deleted} rekordów statystyk.'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500


@admin_bp.route('/popups/upload-image', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def popup_upload_image():
    """Upload obrazka dla treści popupa (TinyMCE)"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'Brak pliku'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Nie wybrano pliku'}), 400

    # Sprawdź rozszerzenie
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

    if file_ext not in allowed_extensions:
        return jsonify({
            'success': False,
            'error': 'Niedozwolony typ pliku. Dozwolone: PNG, JPG, GIF, WebP'
        }), 400

    try:
        # Generuj unikalną nazwę pliku
        unique_name = f"{uuid.uuid4().hex}.{file_ext}"

        # Ścieżka do zapisu
        upload_folder = os.path.join('static', 'uploads', 'popups')
        os.makedirs(upload_folder, exist_ok=True)

        file_path = os.path.join(upload_folder, unique_name)
        file.save(file_path)

        # Opcjonalnie: kompresuj obrazek
        try:
            from utils.image_processor import compress_image
            compress_image(file_path, max_width=1200, quality=85)
        except Exception:
            pass  # Jeśli nie ma image_processor, zapisz bez kompresji

        # TinyMCE oczekuje pola 'location' w odpowiedzi
        return jsonify({
            'location': url_for('static', filename=f'uploads/popups/{unique_name}')
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/popups/<int:popup_id>/stats', methods=['GET'])
@login_required
@role_required('admin', 'mod')
def popup_stats(popup_id):
    """Statystyki popupa (AJAX JSON)"""
    try:
        popup = Popup.query.get_or_404(popup_id)

        return jsonify({
            'success': True,
            'stats': {
                'views': popup.views_count,
                'unique_viewers': popup.unique_viewers_count,
                'dismissed': popup.dismissed_count,
                'cta_clicked': popup.cta_clicked_count,
                'avg_display_time_ms': popup.avg_display_time_ms
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Błąd: {str(e)}'
        }), 500
