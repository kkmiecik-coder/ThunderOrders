"""Admin: grupy uzytkownikow (zarzadzanie + wyszukiwarki)."""
from flask import request, jsonify
from flask_login import login_required
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
