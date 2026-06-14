"""Admin: grupy uzytkownikow (zarzadzanie + wyszukiwarki)."""
from flask import request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_
from modules.admin import admin_bp
from utils.decorators import admin_required
from extensions import db
from modules.auth.models import User, UserGroup


@admin_bp.route('/users/api/search')
@login_required
@admin_required
def users_api_search():
    """Wyszukiwanie użytkowników po imieniu, nazwisku lub emailu (min. 2 znaki)."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    term = f'%{q}%'
    users = User.query.filter(
        or_(
            User.first_name.ilike(term),
            User.last_name.ilike(term),
            User.email.ilike(term),
        )
    ).order_by(User.last_name).limit(20).all()
    return jsonify([{
        'id': u.id,
        'name': ((u.first_name or '') + ' ' + (u.last_name or '')).strip() or u.email,
        'email': u.email,
        'avatar': u.avatar_url,  # None-safe: User.avatar_url zwraca None gdy brak avatara
    } for u in users])


@admin_bp.route('/user-groups/api/search')
@login_required
@admin_required
def user_groups_api_search():
    """Wyszukiwanie grup użytkowników (opcjonalny filtr po nazwie)."""
    q = request.args.get('q', '').strip()
    query = UserGroup.query
    if q:
        query = query.filter(UserGroup.name.ilike(f'%{q}%'))
    groups = query.order_by(UserGroup.name).limit(20).all()
    return jsonify([{
        'id': g.id,
        'name': g.name,
        'member_count': g.member_count,
    } for g in groups])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_group(g):
    return {'id': g.id, 'name': g.name, 'member_count': g.member_count}


def _set_members(group, member_ids):
    group.members = User.query.filter(User.id.in_(member_ids)).all() if member_ids else []


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@admin_bp.route('/user-groups/create', methods=['POST'])
@login_required
@admin_required
def user_groups_create():
    """Tworzenie nowej grupy użytkowników."""
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Nazwa jest wymagana'}), 400
    if UserGroup.query.filter(UserGroup.name == name).first():
        return jsonify({'success': False, 'error': 'Grupa o tej nazwie juz istnieje'}), 400
    group = UserGroup(name=name, created_by=current_user.id)
    _set_members(group, data.get('member_ids') or [])
    db.session.add(group)
    db.session.commit()
    return jsonify({'success': True, 'group': _serialize_group(group)})


@admin_bp.route('/user-groups/<int:group_id>/update', methods=['POST'])
@login_required
@admin_required
def user_groups_update(group_id):
    """Aktualizacja nazwy i członków grupy."""
    group = UserGroup.query.get_or_404(group_id)
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Nazwa jest wymagana'}), 400
    dup = UserGroup.query.filter(UserGroup.name == name, UserGroup.id != group_id).first()
    if dup:
        return jsonify({'success': False, 'error': 'Grupa o tej nazwie juz istnieje'}), 400
    group.name = name
    if 'member_ids' in data:
        _set_members(group, data.get('member_ids') or [])
    db.session.commit()
    return jsonify({'success': True, 'group': _serialize_group(group)})


@admin_bp.route('/user-groups/<int:group_id>/delete', methods=['POST'])
@login_required
@admin_required
def user_groups_delete(group_id):
    """Usuwanie grupy (CASCADE usuwa membership i page-attachment rows)."""
    group = UserGroup.query.get_or_404(group_id)
    db.session.delete(group)
    db.session.commit()
    return jsonify({'success': True})
