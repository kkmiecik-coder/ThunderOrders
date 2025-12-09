"""
Admin Tasks Routes
Zarządzanie zadaniami administracyjnymi (TODO system)
"""

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_
from modules.admin import admin_bp
from modules.admin.models import AdminTask, AdminTaskAssignment, AdminTaskComment
from modules.auth.models import User
from extensions import db
from utils.decorators import role_required
from datetime import datetime


@admin_bp.route('/tasks')
@login_required
@role_required('admin', 'mod')
def tasks_list():
    """
    Lista wszystkich tasków
    GET /admin/tasks
    """
    # Parametry filtrowania
    status_filter = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    assigned_to = request.args.get('assigned_to', '')

    # Bazowe zapytanie - tylko główne taski (bez podzadań)
    query = AdminTask.query.filter_by(parent_task_id=None)

    # Filtry
    if status_filter:
        query = query.filter(AdminTask.status == status_filter)

    if priority_filter:
        query = query.filter(AdminTask.priority == priority_filter)

    if assigned_to:
        # Filtruj po przypisanym użytkowniku
        query = query.join(AdminTask.assignees).filter(User.id == assigned_to)

    # Sortowanie
    query = query.order_by(AdminTask.created_at.desc())

    tasks = query.all()

    # Lista userów (admin/mod) do assignowania
    assignable_users = User.query.filter(User.role.in_(['admin', 'mod'])).all()

    return render_template(
        'admin/tasks/list.html',
        title='Zadania',
        tasks=tasks,
        assignable_users=assignable_users,
        status_filter=status_filter,
        priority_filter=priority_filter
    )


@admin_bp.route('/tasks/create', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def task_create():
    """
    Utworzenie nowego taska
    POST /admin/tasks/create
    """
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    priority = request.form.get('priority', 'medium')
    due_date_str = request.form.get('due_date', '').strip()
    assigned_users = request.form.getlist('assigned_users')  # Lista ID userów
    parent_task_id = request.form.get('parent_task_id')  # Opcjonalnie dla podzadań

    # Walidacja
    if not name:
        return jsonify({'success': False, 'error': 'Nazwa zadania jest wymagana.'}), 400

    # Parse due_date
    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            return jsonify({'success': False, 'error': 'Nieprawidłowy format daty.'}), 400

    # Sprawdź parent task (jeśli to podzadanie)
    if parent_task_id:
        parent_task = AdminTask.query.get(parent_task_id)
        if not parent_task:
            return jsonify({'success': False, 'error': 'Zadanie nadrzędne nie istnieje.'}), 404

    # Utwórz task
    task = AdminTask(
        name=name,
        description=description,
        priority=priority,
        created_by=current_user.id,
        due_date=due_date,
        parent_task_id=parent_task_id if parent_task_id else None
    )

    db.session.add(task)
    db.session.flush()  # Flush aby uzyskać task.id

    # Przypisz użytkowników
    if assigned_users:
        for user_id in assigned_users:
            user = User.query.get(user_id)
            if user and user.role in ['admin', 'mod']:
                assignment = AdminTaskAssignment(
                    task_id=task.id,
                    user_id=user.id
                )
                db.session.add(assignment)

    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Zadanie zostało utworzone.',
            'task_id': task.id
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/tasks/<int:id>', methods=['GET'])
@login_required
@role_required('admin', 'mod')
def task_get(id):
    """
    Pobranie danych pojedynczego taska
    GET /admin/tasks/<id>
    """
    task = AdminTask.query.get_or_404(id)

    # Pobierz przypisanych użytkowników
    assigned_users = [a.id for a in task.assignees]

    # Pobierz komentarze
    comments = [{
        'id': c.id,
        'user_id': c.user_id,
        'user_name': f"{c.user.first_name} {c.user.last_name}",
        'comment': c.comment,
        'created_at': c.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for c in task.comments]

    return jsonify({
        'success': True,
        'task': {
            'id': task.id,
            'name': task.name,
            'description': task.description or '',
            'priority': task.priority,
            'status': task.status,
            'due_date': task.due_date.strftime('%Y-%m-%dT%H:%M') if task.due_date else '',
            'assigned_users': assigned_users,
            'comments': comments
        }
    })


@admin_bp.route('/tasks/<int:id>/update', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def task_update(id):
    """
    Edycja taska
    POST /admin/tasks/<id>/update
    """
    task = AdminTask.query.get_or_404(id)

    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    priority = request.form.get('priority')
    due_date_str = request.form.get('due_date', '').strip()
    assigned_users = request.form.getlist('assigned_users')

    # Walidacja
    if not name:
        return jsonify({'success': False, 'error': 'Nazwa zadania jest wymagana.'}), 400

    # Update fields
    task.name = name
    task.description = description
    if priority:
        task.priority = priority

    # Parse due_date
    if due_date_str:
        try:
            task.due_date = datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            return jsonify({'success': False, 'error': 'Nieprawidłowy format daty.'}), 400
    else:
        task.due_date = None

    # Update assignments
    # Usuń stare
    AdminTaskAssignment.query.filter_by(task_id=task.id).delete()

    # Dodaj nowe
    if assigned_users:
        for user_id in assigned_users:
            user = User.query.get(user_id)
            if user and user.role in ['admin', 'mod']:
                assignment = AdminTaskAssignment(
                    task_id=task.id,
                    user_id=user.id
                )
                db.session.add(assignment)

    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Zadanie zostało zaktualizowane.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/tasks/<int:id>/toggle-status', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def task_toggle_status(id):
    """
    Zmiana statusu taska (pending → in_progress → completed)
    POST /admin/tasks/<id>/toggle-status
    """
    task = AdminTask.query.get_or_404(id)

    # Cycle through statuses
    status_cycle = {
        'pending': 'in_progress',
        'in_progress': 'completed',
        'completed': 'pending'
    }

    new_status = request.form.get('status')  # Opcjonalnie - konkretny status

    if new_status and new_status in ['pending', 'in_progress', 'completed']:
        task.status = new_status
    else:
        # Auto-cycle
        task.status = status_cycle.get(task.status, 'pending')

    # Jeśli completed - zapisz timestamp
    if task.status == 'completed':
        task.mark_completed()
    elif task.status in ['pending', 'in_progress'] and task.completed_at is not None:
        # Tylko wyczyść completed_at jeśli task był wcześniej ukończony
        task.completed_at = None

    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'new_status': task.status,
            'message': f'Status zmieniony na: {task.status}'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/tasks/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')  # Tylko admin może usuwać
def task_delete(id):
    """
    Usunięcie taska
    POST /admin/tasks/<id>/delete
    """
    task = AdminTask.query.get_or_404(id)

    try:
        db.session.delete(task)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Zadanie zostało usunięte.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/tasks/<int:id>/subtask', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def task_add_subtask(id):
    """
    Dodanie podzadania do taska
    POST /admin/tasks/<id>/subtask
    """
    parent_task = AdminTask.query.get_or_404(id)

    name = request.form.get('name', '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Nazwa podzadania jest wymagana.'}), 400

    # Utwórz podzadanie
    subtask = AdminTask(
        name=name,
        description='',
        priority=parent_task.priority,  # Dziedzicz priorytet
        created_by=current_user.id,
        parent_task_id=parent_task.id,
        status='pending'
    )

    try:
        db.session.add(subtask)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Podzadanie zostało dodane.',
            'subtask_id': subtask.id
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/tasks/<int:id>/comment', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def task_add_comment(id):
    """
    Dodanie komentarza do taska
    POST /admin/tasks/<id>/comment
    """
    task = AdminTask.query.get_or_404(id)

    comment_text = request.form.get('comment', '').strip()

    if not comment_text:
        return jsonify({'success': False, 'error': 'Treść komentarza jest wymagana.'}), 400

    # Utwórz komentarz
    comment = AdminTaskComment(
        task_id=task.id,
        user_id=current_user.id,
        comment=comment_text
    )

    try:
        db.session.add(comment)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Komentarz został dodany.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# API endpoint dla dashboardu
@admin_bp.route('/api/tasks/summary')
@login_required
@role_required('admin', 'mod')
def tasks_summary():
    """
    Podsumowanie tasków dla widgetu dashboardu
    GET /admin/api/tasks/summary
    """
    # Tylko główne taski (bez podzadań)
    tasks = AdminTask.query.filter_by(parent_task_id=None).all()

    # Taski przypisane do current_user
    my_tasks = [t for t in tasks if current_user in t.assignees or t.created_by == current_user.id]

    # Taski overdue
    overdue_tasks = [t for t in my_tasks if t.is_overdue()]

    # Pending taski
    pending_tasks = [t for t in my_tasks if t.status == 'pending']

    return jsonify({
        'total': len(tasks),
        'my_tasks': len(my_tasks),
        'pending': len(pending_tasks),
        'overdue': len(overdue_tasks),
        'tasks': [
            {
                'id': t.id,
                'name': t.name,
                'priority': t.priority,
                'status': t.status,
                'is_overdue': t.is_overdue(),
                'progress': t.get_progress()
            }
            for t in my_tasks[:5]  # Top 5 dla widgetu
        ]
    })
