"""
Admin Broadcast Routes
Wysyłanie powiadomień broadcast do użytkowników z panelu admina.
"""

import json
import logging
import threading

from flask import render_template, request, jsonify, current_app, url_for
from flask_login import login_required, current_user
from extensions import db
from utils.decorators import role_required
from modules.notifications.broadcast_models import AdminBroadcast
from modules.notifications.models import Notification
from modules.auth.models import User
from . import admin_bp

logger = logging.getLogger(__name__)


@admin_bp.route('/broadcasts')
@login_required
@role_required('admin', 'mod')
def broadcasts_list():
    """Lista wysłanych broadcastów z paginacją."""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    pagination = AdminBroadcast.query.order_by(
        AdminBroadcast.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'admin/broadcasts/list.html',
        broadcasts=pagination.items,
        pagination=pagination
    )


@admin_bp.route('/broadcasts/new')
@login_required
@role_required('admin', 'mod')
def broadcasts_new():
    """Formularz tworzenia nowego broadcastu."""
    return render_template('admin/broadcasts/new.html')


@admin_bp.route('/broadcasts/send', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def broadcasts_send():
    """Wyślij broadcast do wybranych odbiorców (AJAX/JSON)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Brak danych.'}), 400

        title = (data.get('title') or '').strip()
        body = (data.get('body') or '').strip() or None
        url_val = (data.get('url') or '').strip() or None
        target_type = data.get('target_type', 'all')
        target_data_raw = data.get('target_data')

        if not title:
            return jsonify({'success': False, 'message': 'Tytuł jest wymagany.'}), 400

        if target_type not in ('all', 'roles', 'users'):
            return jsonify({'success': False, 'message': 'Nieprawidłowy typ odbiorców.'}), 400

        # Resolve target users
        user_ids = _resolve_target_users(target_type, target_data_raw)

        if not user_ids:
            return jsonify({'success': False, 'message': 'Brak odbiorców spełniających kryteria.'}), 400

        # Store target_data as JSON
        target_data_json = json.dumps(target_data_raw) if target_data_raw else None

        # Create broadcast record
        broadcast = AdminBroadcast(
            title=title,
            body=body,
            url=url_val,
            target_type=target_type,
            target_data=target_data_json,
            sent_count=len(user_ids),
            sent_by=current_user.id
        )
        db.session.add(broadcast)
        db.session.commit()

        # Send notifications in background thread
        broadcast_id = broadcast.id
        app = current_app._get_current_object()

        def _send_all():
            with app.app_context():
                from utils.push_manager import PushManager
                tag = f'broadcast-{broadcast_id}'
                for uid in user_ids:
                    try:
                        PushManager.send_to_user(
                            user_id=uid,
                            title=title,
                            body=body or '',
                            url=url_val or '/',
                            tag=tag,
                            notification_type='admin_alerts'
                        )
                    except Exception as e:
                        logger.error(f'Broadcast send error for user {uid}: {e}')

        thread = threading.Thread(target=_send_all)
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'sent_count': len(user_ids),
            'message': f'Powiadomienie wysłane do {len(user_ids)} użytkowników.'
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f'Broadcast send error: {e}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd serwera.'}), 500


@admin_bp.route('/broadcasts/search-users')
@login_required
@role_required('admin', 'mod')
def broadcasts_search_users():
    """Wyszukiwanie użytkowników po nazwie/emailu (AJAX)."""
    q = request.args.get('q', '').strip()

    if len(q) < 2:
        return jsonify({'users': []})

    search = f'%{q}%'
    users = User.query.filter(
        User.is_active == True,
        db.or_(
            User.first_name.ilike(search),
            User.last_name.ilike(search),
            User.email.ilike(search)
        )
    ).limit(20).all()

    return jsonify({
        'users': [{
            'id': u.id,
            'name': u.full_name,
            'email': u.email,
            'role': u.role
        } for u in users]
    })


@admin_bp.route('/broadcasts/<int:broadcast_id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def broadcasts_delete(broadcast_id):
    """Usuń broadcast i powiązane notyfikacje (AJAX)."""
    try:
        broadcast = AdminBroadcast.query.get_or_404(broadcast_id)
        tag = broadcast.tag

        # Delete associated notifications
        Notification.query.filter_by(tag=tag).delete()
        db.session.delete(broadcast)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Broadcast został usunięty.'
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f'Broadcast delete error: {e}')
        return jsonify({'success': False, 'message': 'Wystąpił błąd.'}), 500


def _resolve_target_users(target_type, target_data):
    """Resolve list of user IDs based on target type."""
    if target_type == 'all':
        users = User.query.filter_by(is_active=True).with_entities(User.id).all()
        return [u.id for u in users]

    elif target_type == 'roles':
        if not target_data or not isinstance(target_data, list):
            return []
        users = User.query.filter(
            User.is_active == True,
            User.role.in_(target_data)
        ).with_entities(User.id).all()
        return [u.id for u in users]

    elif target_type == 'users':
        if not target_data or not isinstance(target_data, list):
            return []
        # Validate user IDs exist and are active
        user_ids = [int(uid) for uid in target_data if str(uid).isdigit()]
        users = User.query.filter(
            User.is_active == True,
            User.id.in_(user_ids)
        ).with_entities(User.id).all()
        return [u.id for u in users]

    return []
