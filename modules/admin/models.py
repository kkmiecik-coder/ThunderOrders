"""
Admin Module - Models
Modele dla funkcjonalności administracyjnych (taski)
"""

from datetime import datetime, timezone, timedelta
from extensions import db




def get_local_now():
    """
    Zwraca aktualny czas polski (Europe/Warsaw).
    Używa stałego offsetu +1h (CET) lub +2h (CEST) w zależności od daty.
    Zwraca naive datetime dla porównań z naive datetime w bazie.
    """
    utc_now = datetime.now(timezone.utc)

    # Prosty algorytm DST dla Polski:
    # CEST (UTC+2): ostatnia niedziela marca do ostatniej niedzieli października
    # CET (UTC+1): reszta roku
    year = utc_now.year

    # Ostatnia niedziela marca
    march_last = datetime(year, 3, 31, tzinfo=timezone.utc)
    march_last_sunday = march_last - timedelta(days=(march_last.weekday() + 1) % 7)
    dst_start = march_last_sunday.replace(hour=1)  # 01:00 UTC

    # Ostatnia niedziela października
    oct_last = datetime(year, 10, 31, tzinfo=timezone.utc)
    oct_last_sunday = oct_last - timedelta(days=(oct_last.weekday() + 1) % 7)
    dst_end = oct_last_sunday.replace(hour=1)  # 01:00 UTC

    # Sprawdź czy jesteśmy w czasie letnim
    if dst_start <= utc_now < dst_end:
        offset = timedelta(hours=2)  # CEST
    else:
        offset = timedelta(hours=1)  # CET

    # Zwróć naive datetime w czasie polskim
    return (utc_now + offset).replace(tzinfo=None)

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
    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(
        db.DateTime,
        default=get_local_now,
        onupdate=get_local_now
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
        return get_local_now() > self.due_date

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
        self.completed_at = get_local_now()

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
    assigned_at = db.Column(db.DateTime, default=get_local_now)

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
    created_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    task = db.relationship('AdminTask', backref='comments')
    user = db.relationship('User', backref='task_comments')

    def __repr__(self):
        return f'<AdminTaskComment task={self.task_id} by user={self.user_id}>'


class ActivityLog(db.Model):
    """
    Model logowania aktywności użytkowników w systemie
    Tabela: activity_log
    """
    __tablename__ = 'activity_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)  # 'login', 'order_status_change', etc.
    entity_type = db.Column(db.String(50), nullable=True)  # 'order', 'product', 'user', etc.
    entity_id = db.Column(db.Integer, nullable=True)
    old_value = db.Column(db.Text, nullable=True)  # JSON
    new_value = db.Column(db.Text, nullable=True)  # JSON
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False)

    __table_args__ = (
        # Fallback wieku zaległości (unclaimed_service.wiek_zaleglosci) filtruje
        # po action + entity_type + entity_id IN (...) przy KAŻDYM otwarciu ekranu
        # „Nieodebrane" — bez indeksu to pełny skan tabeli, która rośnie z każdą
        # akcją w systemie. Ten sam wzorzec co `ix_email_log_entity` na EmailLog.
        db.Index('ix_activity_log_entity', 'entity_type', 'entity_id'),
    )

    # Relationships
    user = db.relationship('User', backref='activity_logs')

    def __repr__(self):
        return f'<ActivityLog {self.id}: {self.action} by user={self.user_id}>'

    @property
    def user_name(self):
        """Zwraca imię i nazwisko użytkownika lub 'System'"""
        if self.user:
            return f"{self.user.first_name} {self.user.last_name}"
        return 'System'

    @property
    def formatted_action(self):
        """Zwraca sformatowaną nazwę akcji"""
        action_names = {
            'login': 'Logowanie',
            'logout': 'Wylogowanie',
            'order_created': 'Utworzenie zamówienia',
            'order_status_change': 'Zmiana statusu zamówienia',
            'order_deleted': 'Usunięcie zamówienia',
            'product_created': 'Dodanie produktu',
            'product_updated': 'Edycja produktu',
            'product_deleted': 'Usunięcie produktu',
            'user_created': 'Utworzenie użytkownika',
            'user_updated': 'Edycja użytkownika',
            'user_deleted': 'Usunięcie użytkownika',
            'settings_updated': 'Zmiana ustawień',
            'refund_issued': 'Wydanie zwrotu',
        }
        return action_names.get(self.action, self.action)


class EmailLog(db.Model):
    """Ślad po każdym mailu wychodzącym z systemu — od zakolejkowania po wynik SMTP.

    Tabela: email_log

    Osobno od ActivityLog, bo to nie jest zmiana danych zrobiona przez człowieka,
    tylko przebieg techniczny: ma własne stany, licznik prób i czas trwania połączenia.
    Upchnięcie tego w `activity_log.new_value` (JSON) uniemożliwiłoby filtrowanie po
    statusie i mieszałoby maile systemowe (przypomnienia, broadcasty) z historią zamówień.

    Zapis jest DWUFAZOWY: wiersz powstaje jako `queued` w wątku, który mail zleca, a
    wątek wysyłkowy podmienia go na `sent`/`failed`. Bez tej drugiej fazy wpis mówiłby
    tylko „próbowaliśmy" — a pytania, na które ta tabela ma odpowiadać, brzmią „czy
    doszło", „ile to trwało" i „czy nie poszło dwa razy".
    """
    __tablename__ = 'email_log'

    id = db.Column(db.Integer, primary_key=True)
    recipient = db.Column(db.String(255), nullable=False, index=True)
    subject = db.Column(db.String(500), nullable=True)
    # Nazwa szablonu = typ maila ('order_status_change', 'payment_approved', ...).
    # Bierze się wprost z wywołania send_email(), więc nie trzeba utrzymywać
    # osobnego słownika typów, który i tak rozjechałby się z szablonami.
    template = db.Column(db.String(100), nullable=True, index=True)

    # Powiązanie z encją — te same nazwy co w ActivityLog ('order', 'shipping_request'),
    # żeby historia zmian zamówienia mogła zestawić oba źródła bez tłumaczenia nazw.
    # Nullable, bo maile systemowe (weryfikacja konta, broadcast) nie mają encji.
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)

    status = db.Column(db.String(20), nullable=False, default='queued', index=True)
    # Numer próby, na której skończyła się wysyłka. >1 znaczy, że klient MÓGŁ dostać
    # duplikat: serwer bywa, że przyjmie wiadomość i zerwie połączenie przed odpowiedzią,
    # a taki błąd jest dla nas nieodróżnialny od „nie dotarło" (utils/email_sender.py).
    attempts = db.Column(db.Integer, nullable=False, default=0)
    error = db.Column(db.Text, nullable=True)
    # Czas od startu wysyłki do wyniku, razem z drzemkami między próbami.
    duration_ms = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime, default=get_local_now, nullable=False, index=True)
    sent_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.Index('ix_email_log_entity', 'entity_type', 'entity_id'),
    )

    def __repr__(self):
        return f'<EmailLog {self.id}: {self.template} to={self.recipient} {self.status}>'

    @property
    def status_label(self):
        """Etykieta statusu po polsku (panel admina)."""
        return {
            'queued': 'w kolejce',
            'sent': 'wysłany',
            'failed': 'błąd wysyłki',
        }.get(self.status, self.status)

    @property
    def type_label(self):
        """Czytelna nazwa typu maila; nieznany szablon zwraca własną nazwę."""
        return EMAIL_TYPE_LABELS.get(self.template, self.template or 'e-mail')


# Nazwy szablonów → opis dla człowieka. Świadomie niepełna: nieznany szablon
# pokazuje się pod własną nazwą (type_label), więc nowy mail nigdy nie znika
# z historii tylko dlatego, że ktoś zapomniał dopisać go tutaj.
EMAIL_TYPE_LABELS = {
    'order_confirmation': 'potwierdzenie zamówienia',
    'admin_created_order': 'zamówienie dodane przez administratora',
    'order_status_change': 'zmiana statusu',
    'order_completed': 'zamówienie zrealizowane',
    'order_cancelled': 'anulowanie zamówienia',
    'order_supplier_ordered': 'zamówione u dostawcy',
    'order_supplier_cancelled': 'anulowane u dostawcy',
    'offer_closure': 'podsumowanie strony sprzedaży',
    'tracking_added': 'numer przesyłki',
    'shipment_sent': 'paczka wysłana',
    'shipment_consolidated': 'paczka zbiorcza',
    'shipping_request_created': 'zlecenie wysyłki utworzone',
    'shipping_status_change': 'zmiana statusu zlecenia',
    'packing_photo': 'zdjęcie paczki',
    'delivery_confirmed': 'potwierdzenie dostawy',
    'cost_added': 'dodany koszt',
    'payment_approved': 'płatność zatwierdzona',
    'payment_rejected': 'płatność odrzucona',
    'payment_reminder': 'przypomnienie o płatności',
    'pickup_reminder': 'przypomnienie o odbiorze',
}
