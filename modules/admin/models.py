"""
Admin Module - Models
Modele dla funkcjonalności administracyjnych (taski)
"""

from datetime import datetime
from extensions import db


class AdminTask(db.Model):
    """
    Model zadań administracyjnych (TODO)
    Tabela: admin_tasks
    """
    __tablename__ = 'admin_tasks'

    # Primary Key
    id = db.Column(db.Integer, primary_key=True)

    # Task Info
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)  # HTML - linki, obrazki

    # Priority & Status
    priority = db.Column(
        db.Enum('low', 'medium', 'high', name='task_priority'),
        default='medium',
        nullable=False
    )
    status = db.Column(
        db.Enum('pending', 'in_progress', 'completed', name='task_status'),
        default='pending',
        nullable=False
    )

    # Hierarchy (podzadania)
    parent_task_id = db.Column(db.Integer, db.ForeignKey('admin_tasks.id'))

    # Creator
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Due date
    due_date = db.Column(db.DateTime)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    completed_at = db.Column(db.DateTime)

    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_tasks')

    # Self-reference dla podzadań
    parent = db.relationship(
        'AdminTask',
        remote_side=[id],
        backref='subtasks'
    )

    # Many-to-many z users (assignees)
    assignees = db.relationship(
        'User',
        secondary='admin_task_assignments',
        backref='assigned_tasks'
    )

    def __repr__(self):
        return f'<AdminTask {self.id}: {self.name}>'

    # ============================================
    # Helper Methods
    # ============================================

    def is_overdue(self):
        """Sprawdza czy task jest po terminie"""
        if not self.due_date:
            return False
        if self.status == 'completed':
            return False
        return datetime.utcnow() > self.due_date

    def get_progress(self):
        """
        Zwraca procent wykonania (dla tasków z podzadaniami)

        Returns:
            int: 0-100 (procent ukończonych podzadań)
        """
        if not self.subtasks:
            return 100 if self.status == 'completed' else 0

        total = len(self.subtasks)
        completed = sum(1 for st in self.subtasks if st.status == 'completed')

        return int((completed / total) * 100) if total > 0 else 0

    def completed_subtasks_count(self):
        """
        Zwraca liczbę ukończonych podzadań

        Returns:
            int: Liczba ukończonych podzadań
        """
        if not self.subtasks:
            return 0
        return sum(1 for st in self.subtasks if st.status == 'completed')

    def can_assign_to(self, user):
        """
        Sprawdza czy można przypisać task do użytkownika
        (tylko admin i mod)

        Args:
            user: User object

        Returns:
            bool: True jeśli można przypisać
        """
        return user.role in ['admin', 'mod']

    def mark_completed(self):
        """Oznacza task jako ukończony"""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()

    def reopen(self):
        """Ponownie otwiera ukończony task"""
        self.status = 'pending'
        self.completed_at = None

    @property
    def is_main_task(self):
        """Sprawdza czy to główny task (nie podzadanie)"""
        return self.parent_task_id is None

    @property
    def priority_color(self):
        """Zwraca kolor CSS dla priorytetu"""
        colors = {
            'low': 'success',
            'medium': 'warning',
            'high': 'danger'
        }
        return colors.get(self.priority, 'info')

    @property
    def status_color(self):
        """Zwraca kolor CSS dla statusu"""
        colors = {
            'pending': 'gray',
            'in_progress': 'purple',
            'completed': 'success'
        }
        return colors.get(self.status, 'gray')


class AdminTaskAssignment(db.Model):
    """
    Junction table - przypisania tasków do użytkowników
    Tabela: admin_task_assignments
    """
    __tablename__ = 'admin_task_assignments'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('admin_tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<AdminTaskAssignment task={self.task_id} user={self.user_id}>'


class AdminTaskComment(db.Model):
    """
    Model komentarzy do zadań
    Tabela: admin_task_comments
    """
    __tablename__ = 'admin_task_comments'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('admin_tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    task = db.relationship('AdminTask', backref='comments')
    user = db.relationship('User', backref='task_comments')

    def __repr__(self):
        return f'<AdminTaskComment task={self.task_id} by user={self.user_id}>'
