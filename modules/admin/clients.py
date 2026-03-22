"""
Admin Clients Module
Zarządzanie klientami w panelu administratora
"""

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_, func
from modules.admin import admin_bp
from modules.auth.models import User, Settings
from modules.orders.models import (
    ShippingRequest, Order, OrderComment, OrderRefund, OrderShipment,
    OrderItem
)
from modules.admin.models import AdminTaskAssignment, AdminTaskComment, ActivityLog, AdminTask
from modules.client.models import (
    CollectionItem, PublicCollectionConfig, CollectionUploadSession
)
from modules.feedback.models import FeedbackSurvey, FeedbackResponse
from modules.exclusive.models import ExclusivePage, ExclusiveReservation
from modules.tracking.models import QRCampaign
from modules.achievements.models import UserAchievement
from modules.notifications.models import Notification, PushSubscription, NotificationPreference
from modules.imports.models import CsvImport
from extensions import db
from utils.decorators import role_required
from utils.email_sender import send_account_deactivated_email


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
    if role_filter == 'all' or role_filter == '':
        # 'all' lub pusty string = nie filtruj (wszyscy użytkownicy)
        pass
    elif role_filter in ['admin', 'mod', 'client']:
        # Konkretna rola
        query = query.filter(User.role == role_filter)
    else:
        # Domyślnie pokazuj tylko klientów (gdy role_filter nie jest ustawiony w ogóle)
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

    # Statystyki - wszystkich użytkowników (nie tylko klientów)
    total_clients = User.query.count()
    active_clients = User.query.filter(User.is_active == True).count()
    inactive_clients = User.query.filter(User.is_active == False).count()

    return render_template(
        'admin/clients/list.html',
        title='Użytkownicy',
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
    from modules.orders.models import Order
    from decimal import Decimal

    client = User.query.get_or_404(id)

    # Pobierz admina który dezaktywował (jeśli dotyczy)
    deactivated_by_user = None
    if client.deactivated_by:
        deactivated_by_user = User.query.get(client.deactivated_by)

    # Pobierz statystyki zamówień klienta
    client_orders = Order.query.filter_by(user_id=client.id).all()

    # Oblicz statystyki
    orders_count = len(client_orders)
    total_value = sum(
        Decimal(str(order.total_amount)) if order.total_amount else Decimal('0.00')
        for order in client_orders
    )
    avg_value = total_value / orders_count if orders_count > 0 else Decimal('0.00')

    # Ostatnie zamówienie
    last_order = Order.query.filter_by(user_id=client.id).order_by(Order.created_at.desc()).first()

    # Ostatnie 10 zamówień do wyświetlenia
    recent_orders = Order.query.filter_by(user_id=client.id).order_by(Order.created_at.desc()).limit(10).all()

    # Parametry paginacji dla historii zamówień
    page = request.args.get('page', 1, type=int)
    per_page = 10
    orders_pagination = Order.query.filter_by(user_id=client.id).order_by(
        Order.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'admin/clients/detail.html',
        title=f'Klient: {client.full_name}',
        client=client,
        deactivated_by_user=deactivated_by_user,
        orders_count=orders_count,
        total_value=total_value,
        avg_value=avg_value,
        last_order=last_order,
        recent_orders=recent_orders,
        orders_pagination=orders_pagination
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

        # Wyślij email do klienta o dezaktywacji
        if client.email:
            send_account_deactivated_email(client.email, client.first_name or client.full_name, reason)

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


@admin_bp.route('/clients/<int:id>/anonymize', methods=['POST'])
@login_required
@role_required('admin')
def client_anonymize(id):
    """
    Anonimizacja danych klienta (RODO art. 17).
    POST /admin/clients/<id>/anonymize
    """
    client = User.query.get_or_404(id)

    if client.is_admin():
        return jsonify({'success': False, 'error': 'Nie można anonimizować konta administratora.'}), 400

    if client.is_anonymized:
        return jsonify({'success': False, 'error': 'To konto zostało już zanonimizowane.'}), 400

    try:
        client.anonymize()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Dane klienta #{id} zostały zanonimizowane (RODO art. 17).'
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
        uid = client.id

        # --- Nullify nullable FK references to preserve history ---
        ShippingRequest.query.filter_by(user_id=uid).update({'user_id': None})
        Order.query.filter_by(user_id=uid).update({'user_id': None})
        Order.query.filter_by(packed_by=uid).update({'packed_by': None})
        OrderComment.query.filter_by(user_id=uid).update({'user_id': None})
        OrderItem.query.filter_by(picked_by=uid).update({'picked_by': None})
        OrderShipment.query.filter_by(created_by=uid).update({'created_by': None})
        ActivityLog.query.filter_by(user_id=uid).update({'user_id': None})
        FeedbackResponse.query.filter_by(user_id=uid).update({'user_id': None})
        ExclusiveReservation.query.filter_by(user_id=uid).update({'user_id': None})
        ExclusivePage.query.filter_by(closed_by_id=uid).update({'closed_by_id': None})
        User.query.filter_by(deactivated_by=uid).update({'deactivated_by': None})
        Settings.query.filter_by(updated_by=uid).update({'updated_by': None})

        # --- Reassign NOT NULL FK references (admin-created entities) ---
        AdminTask.query.filter_by(created_by=uid).update({'created_by': current_user.id})
        OrderRefund.query.filter_by(created_by=uid).update({'created_by': current_user.id})
        FeedbackSurvey.query.filter_by(created_by=uid).update({'created_by': current_user.id})
        ExclusivePage.query.filter_by(created_by=uid).update({'created_by': current_user.id})
        QRCampaign.query.filter_by(created_by=uid).update({'created_by': current_user.id})

        # --- Delete client-owned data ---
        UserAchievement.query.filter_by(user_id=uid).delete()
        Notification.query.filter_by(user_id=uid).delete()
        PushSubscription.query.filter_by(user_id=uid).delete()
        NotificationPreference.query.filter_by(user_id=uid).delete()
        CsvImport.query.filter_by(user_id=uid).delete()
        AdminTaskAssignment.query.filter_by(user_id=uid).delete()
        AdminTaskComment.query.filter_by(user_id=uid).delete()
        CollectionUploadSession.query.filter_by(user_id=uid).delete()
        PublicCollectionConfig.query.filter_by(user_id=uid).delete()
        CollectionItem.query.filter_by(user_id=uid).delete()

        db.session.delete(client)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Konto użytkownika {client_name} zostało usunięte.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
