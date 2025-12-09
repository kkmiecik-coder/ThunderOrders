"""
Admin Clients Module
Zarządzanie klientami w panelu administratora
"""

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_, func
from modules.admin import admin_bp
from modules.auth.models import User
from extensions import db
from utils.decorators import role_required


@admin_bp.route('/clients')
@login_required
@role_required('admin', 'mod')
def clients_list():
    """
    Lista wszystkich klientów
    GET /admin/clients
    """
    # Parametry paginacji i sortowania
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    sort_by = request.args.get('sort', 'created_at')
    sort_dir = request.args.get('dir', 'desc')

    # Parametry filtrowania
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')  # 'active', 'inactive', ''
    role_filter = request.args.get('role', '')  # 'client', 'mod', 'admin', ''

    # Bazowe zapytanie - tylko klienci (role = 'client')
    # Ale admin może też widzieć moderatorów
    query = User.query

    # Filtrowanie po roli
    if role_filter:
        query = query.filter(User.role == role_filter)
    else:
        # Domyślnie pokazuj tylko klientów
        query = query.filter(User.role == 'client')

    # Filtrowanie po statusie
    if status_filter == 'active':
        query = query.filter(User.is_active == True)
    elif status_filter == 'inactive':
        query = query.filter(User.is_active == False)

    # Wyszukiwanie
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            or_(
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.email.ilike(search_term),
                User.phone.ilike(search_term)
            )
        )

    # Sortowanie
    sort_columns = {
        'name': User.last_name,
        'email': User.email,
        'created_at': User.created_at,
        'last_login': User.last_login,
    }

    sort_column = sort_columns.get(sort_by, User.created_at)
    if sort_dir == 'asc':
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # Paginacja
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    clients = pagination.items

    # Statystyki
    total_clients = User.query.filter(User.role == 'client').count()
    active_clients = User.query.filter(User.role == 'client', User.is_active == True).count()
    inactive_clients = User.query.filter(User.role == 'client', User.is_active == False).count()

    return render_template(
        'admin/clients/list.html',
        title='Klienci',
        clients=clients,
        pagination=pagination,
        search=search,
        status_filter=status_filter,
        role_filter=role_filter,
        sort_by=sort_by,
        sort_dir=sort_dir,
        total_clients=total_clients,
        active_clients=active_clients,
        inactive_clients=inactive_clients
    )


@admin_bp.route('/clients/<int:id>')
@login_required
@role_required('admin', 'mod')
def client_detail(id):
    """
    Szczegóły klienta
    GET /admin/clients/<id>
    """
    client = User.query.get_or_404(id)

    # Pobierz admina który dezaktywował (jeśli dotyczy)
    deactivated_by_user = None
    if client.deactivated_by:
        deactivated_by_user = User.query.get(client.deactivated_by)

    return render_template(
        'admin/clients/detail.html',
        title=f'Klient: {client.full_name}',
        client=client,
        deactivated_by_user=deactivated_by_user
    )


@admin_bp.route('/clients/<int:id>/edit', methods=['POST'])
@login_required
@role_required('admin')
def client_edit(id):
    """
    Edycja danych klienta (tylko admin)
    POST /admin/clients/<id>/edit
    """
    client = User.query.get_or_404(id)

    # Pobierz dane z formularza
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    role = request.form.get('role', 'client')

    # Walidacja
    if not first_name or not last_name or not email:
        flash('Imię, nazwisko i email są wymagane.', 'error')
        return redirect(url_for('admin.client_detail', id=id))

    # Sprawdź czy email nie jest zajęty przez innego użytkownika
    existing_user = User.query.filter(User.email == email, User.id != id).first()
    if existing_user:
        flash('Ten adres email jest już używany przez innego użytkownika.', 'error')
        return redirect(url_for('admin.client_detail', id=id))

    # Aktualizuj dane
    client.first_name = first_name
    client.last_name = last_name
    client.email = email
    client.phone = phone if phone else None

    # Tylko admin może zmieniać rolę
    if current_user.is_admin() and role in ['admin', 'mod', 'client']:
        client.role = role

    try:
        db.session.commit()
        flash('Dane klienta zostały zaktualizowane.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Wystąpił błąd podczas zapisywania: {str(e)}', 'error')

    return redirect(url_for('admin.client_detail', id=id))


@admin_bp.route('/clients/<int:id>/deactivate', methods=['POST'])
@login_required
@role_required('admin')
def client_deactivate(id):
    """
    Dezaktywacja konta klienta (tylko admin)
    POST /admin/clients/<id>/deactivate
    """
    client = User.query.get_or_404(id)

    # Nie można dezaktywować samego siebie
    if client.id == current_user.id:
        return jsonify({'success': False, 'error': 'Nie możesz dezaktywować własnego konta.'}), 400

    # Nie można dezaktywować admina (chyba że jesteś super-adminem)
    if client.is_admin() and not current_user.is_admin():
        return jsonify({'success': False, 'error': 'Nie masz uprawnień do dezaktywacji tego konta.'}), 403

    reason = request.form.get('reason', '').strip()
    if not reason:
        return jsonify({'success': False, 'error': 'Podanie powodu dezaktywacji jest wymagane.'}), 400

    try:
        client.deactivate(reason, current_user.id)
        db.session.commit()

        # TODO: Wysłać email do klienta o dezaktywacji
        # send_deactivation_email(client, reason)

        return jsonify({
            'success': True,
            'message': f'Konto użytkownika {client.full_name} zostało dezaktywowane.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/clients/<int:id>/reactivate', methods=['POST'])
@login_required
@role_required('admin')
def client_reactivate(id):
    """
    Reaktywacja konta klienta (tylko admin)
    POST /admin/clients/<id>/reactivate
    """
    client = User.query.get_or_404(id)

    try:
        client.reactivate()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Konto użytkownika {client.full_name} zostało reaktywowane.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/clients/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def client_delete(id):
    """
    Usunięcie konta klienta (tylko admin)
    POST /admin/clients/<id>/delete
    """
    client = User.query.get_or_404(id)

    # Nie można usunąć samego siebie
    if client.id == current_user.id:
        return jsonify({'success': False, 'error': 'Nie możesz usunąć własnego konta.'}), 400

    # Nie można usunąć admina
    if client.is_admin():
        return jsonify({'success': False, 'error': 'Nie można usunąć konta administratora.'}), 403

    try:
        client_name = client.full_name
        db.session.delete(client)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Konto użytkownika {client_name} zostało usunięte.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
