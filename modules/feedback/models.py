"""
Feedback Models
Modele dla systemu ankiet i zbierania opinii
"""

from datetime import datetime, timezone, timedelta
import secrets
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


class FeedbackSurvey(db.Model):
    """
    Ankieta feedback - kontener na pytania

    Statusy:
    - draft: Ankieta w budowie (niepubliczna)
    - active: Ankieta aktywna, można wypełniać
    - closed: Ankieta zamknięta
    """
    __tablename__ = 'feedback_surveys'

    id = db.Column(db.Integer, primary_key=True)

    # Podstawowe informacje
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    token = db.Column(db.String(100), unique=True, nullable=False, index=True)

    # Status
    status = db.Column(
        db.Enum('draft', 'active', 'closed', name='feedback_survey_status'),
        default='draft',
        nullable=False,
        index=True
    )

    # Opcjonalna data zamknięcia
    closes_at = db.Column(db.DateTime, nullable=True)

    # Ustawienia
    is_anonymous = db.Column(db.Boolean, default=False)  # Czy ukrywać kto odpowiedział
    allow_multiple_responses = db.Column(db.Boolean, default=False)  # Czy można wypełnić wielokrotnie

    # Metadane
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=get_local_now)
    updated_at = db.Column(db.DateTime, default=get_local_now, onupdate=get_local_now)

    # Relationships
    creator = db.relationship('User', backref='feedback_surveys', foreign_keys=[created_by])
    questions = db.relationship(
        'FeedbackQuestion',
        back_populates='survey',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='FeedbackQuestion.sort_order'
    )
    responses = db.relationship(
        'FeedbackResponse',
        back_populates='survey',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<FeedbackSurvey {self.name}>'

    # ============================================
    # Token Generation
    # ============================================

    @staticmethod
    def generate_token():
        """Generuje unikalny token dla ankiety"""
        return secrets.token_urlsafe(16)

    # ============================================
    # Status Helpers
    # ============================================

    @property
    def is_draft(self):
        return self.status == 'draft'

    @property
    def is_active(self):
        return self.status == 'active'

    @property
    def is_closed(self):
        return self.status == 'closed'

    @property
    def can_respond(self):
        """Czy można wypełnić ankietę"""
        if self.status != 'active':
            return False
        if self.closes_at and get_local_now() > self.closes_at:
            return False
        return True

    # ============================================
    # Status Management
    # ============================================

    def activate(self):
        """Aktywuje ankietę"""
        self.status = 'active'

    def close(self):
        """Zamyka ankietę"""
        self.status = 'closed'

    def reopen(self):
        """Otwiera ankietę ponownie"""
        self.status = 'active'

    def check_and_update_status(self):
        """
        Sprawdza daty i automatycznie aktualizuje status.
        Wywoływane przy każdym dostępie do ankiety.
        """
        now = get_local_now()

        # Jeśli active i minęła data zamknięcia -> closed
        if self.status == 'active' and self.closes_at and now >= self.closes_at:
            self.status = 'closed'
            db.session.commit()
            return True

        return False

    # ============================================
    # Questions Management
    # ============================================

    def get_questions_ordered(self):
        """Zwraca pytania posortowane po sort_order"""
        return self.questions.order_by(FeedbackQuestion.sort_order).all()

    def get_answerable_questions(self):
        """Zwraca tylko pytania które wymagają odpowiedzi (nie nagłówki/teksty)"""
        return self.questions.filter(
            ~FeedbackQuestion.question_type.in_(['section_header', 'text'])
        ).order_by(FeedbackQuestion.sort_order).all()

    # ============================================
    # Statistics
    # ============================================

    @property
    def responses_count(self):
        """Liczba odpowiedzi na ankietę"""
        return self.responses.count()

    def get_overall_average_rating(self):
        """
        Oblicza średnią ocenę ze wszystkich pytań ratingowych w ankiecie.
        Zwraca None jeśli brak pytań ratingowych lub odpowiedzi.
        """
        rating_types = ['rating_scale', 'rating_10', 'emoji_rating']
        rating_questions = self.questions.filter(
            FeedbackQuestion.question_type.in_(rating_types)
        ).all()

        if not rating_questions:
            return None

        total_sum = 0
        total_count = 0

        for question in rating_questions:
            avg = question.get_average_rating()
            if avg is not None:
                # Normalizuj do skali 0-1 dla porównania
                max_val = 10 if question.question_type == 'rating_10' else 5
                normalized = avg / max_val
                total_sum += normalized
                total_count += 1

        if total_count == 0:
            return None

        # Zwróć średnią znormalizowaną do skali 5
        return (total_sum / total_count) * 5

    # ============================================
    # URL Helpers
    # ============================================

    def get_public_url(self, _external=True):
        """Zwraca publiczny URL ankiety"""
        from flask import url_for
        return url_for('feedback.survey_page', token=self.token, _external=_external)

    # ============================================
    # Class Methods
    # ============================================

    @classmethod
    def get_by_token(cls, token):
        """Znajduje ankietę po tokenie"""
        return cls.query.filter_by(token=token).first()


class FeedbackQuestion(db.Model):
    """
    Pytanie w ankiecie

    Typy pytań:
    - section_header: Nagłówek sekcji (H2)
    - text: Paragraf tekstu/opisu
    - rating_scale: Ocena 1-5 gwiazdek
    - rating_10: Ocena 1-10
    - emoji_rating: Ocena emoji (5 poziomów)
    - yes_no: Tak/Nie
    - yes_no_comment: Tak/Nie + pole komentarza
    - multiple_choice: Single select (radio)
    - checkbox_list: Multi select (checkboxy)
    - textarea: Długa odpowiedź tekstowa
    """
    __tablename__ = 'feedback_questions'

    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey('feedback_surveys.id'), nullable=False, index=True)

    # Typ pytania
    question_type = db.Column(
        db.Enum(
            'section_header', 'text', 'rating_scale', 'rating_10', 'emoji_rating',
            'yes_no', 'yes_no_comment', 'multiple_choice', 'checkbox_list', 'textarea',
            name='feedback_question_type'
        ),
        nullable=False
    )
    sort_order = db.Column(db.Integer, default=0)

    # Treść pytania
    content = db.Column(db.Text, nullable=True)

    # Opcje dla multiple_choice i checkbox_list (JSON array)
    options = db.Column(db.JSON, nullable=True)

    # Czy pytanie jest wymagane
    is_required = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    survey = db.relationship('FeedbackSurvey', back_populates='questions')
    answers = db.relationship(
        'FeedbackAnswer',
        back_populates='question',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<FeedbackQuestion {self.question_type} #{self.id}>'

    # ============================================
    # Type Helpers
    # ============================================

    @property
    def is_section_header(self):
        return self.question_type == 'section_header'

    @property
    def is_text(self):
        return self.question_type == 'text'

    @property
    def is_rating_scale(self):
        return self.question_type == 'rating_scale'

    @property
    def is_rating_10(self):
        return self.question_type == 'rating_10'

    @property
    def is_emoji_rating(self):
        return self.question_type == 'emoji_rating'

    @property
    def is_yes_no(self):
        return self.question_type == 'yes_no'

    @property
    def is_yes_no_comment(self):
        return self.question_type == 'yes_no_comment'

    @property
    def is_multiple_choice(self):
        return self.question_type == 'multiple_choice'

    @property
    def is_checkbox_list(self):
        return self.question_type == 'checkbox_list'

    @property
    def is_textarea(self):
        return self.question_type == 'textarea'

    @property
    def is_display_only(self):
        """Czy to element tylko do wyświetlania (nie wymaga odpowiedzi)"""
        return self.question_type in ('section_header', 'text')

    @property
    def needs_options(self):
        """Czy pytanie wymaga opcji do wyboru"""
        return self.question_type in ('multiple_choice', 'checkbox_list')

    # ============================================
    # Statistics
    # ============================================

    def get_answers_count(self):
        """Liczba odpowiedzi na to pytanie"""
        return self.answers.count()

    def get_average_rating(self):
        """Średnia ocena (dla rating_scale, rating_10, emoji_rating)"""
        if self.question_type not in ('rating_scale', 'rating_10', 'emoji_rating'):
            return None

        answers = self.answers.filter(FeedbackAnswer.answer_value.isnot(None)).all()
        if not answers:
            return None

        values = [int(a.answer_value) for a in answers if a.answer_value and a.answer_value.isdigit()]
        if not values:
            return None

        return sum(values) / len(values)

    def get_yes_no_stats(self):
        """Statystyki dla pytań tak/nie"""
        if self.question_type not in ('yes_no', 'yes_no_comment'):
            return None

        answers = self.answers.all()
        yes_count = sum(1 for a in answers if a.answer_value == 'yes')
        no_count = sum(1 for a in answers if a.answer_value == 'no')
        total = yes_count + no_count

        return {
            'yes': yes_count,
            'no': no_count,
            'total': total,
            'yes_percent': (yes_count / total * 100) if total > 0 else 0,
            'no_percent': (no_count / total * 100) if total > 0 else 0
        }

    def get_choice_stats(self):
        """Statystyki dla pytań multiple_choice i checkbox_list"""
        if self.question_type not in ('multiple_choice', 'checkbox_list'):
            return None

        answers = self.answers.all()
        stats = {}

        # Inicjalizuj wszystkie opcje
        if self.options:
            for opt in self.options:
                stats[opt] = 0

        # Zlicz odpowiedzi
        for answer in answers:
            if self.question_type == 'multiple_choice' and answer.answer_value:
                if answer.answer_value in stats:
                    stats[answer.answer_value] += 1
            elif self.question_type == 'checkbox_list' and answer.answer_options:
                for opt in answer.answer_options:
                    if opt in stats:
                        stats[opt] += 1

        total = len(answers)
        result = []
        for opt, count in stats.items():
            result.append({
                'option': opt,
                'count': count,
                'percent': (count / total * 100) if total > 0 else 0
            })

        return result


class FeedbackResponse(db.Model):
    """
    Odpowiedź na ankietę (jeden użytkownik, jedna sesja wypełniania)
    """
    __tablename__ = 'feedback_responses'

    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey('feedback_surveys.id'), nullable=False, index=True)

    # Użytkownik (jeśli zalogowany)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    # Metadane
    submitted_at = db.Column(db.DateTime, default=get_local_now)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)

    # Relationships
    survey = db.relationship('FeedbackSurvey', back_populates='responses')
    user = db.relationship('User', backref='feedback_responses')
    answers = db.relationship(
        'FeedbackAnswer',
        back_populates='response',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<FeedbackResponse #{self.id} survey={self.survey_id}>'

    @property
    def respondent_name(self):
        """Nazwa osoby która odpowiedziała"""
        if self.user:
            return self.user.full_name or self.user.email
        return 'Anonimowy'


class FeedbackAnswer(db.Model):
    """
    Odpowiedź na pojedyncze pytanie
    """
    __tablename__ = 'feedback_answers'

    id = db.Column(db.Integer, primary_key=True)
    response_id = db.Column(db.Integer, db.ForeignKey('feedback_responses.id'), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey('feedback_questions.id'), nullable=False, index=True)

    # Wartość odpowiedzi (dla rating, yes_no, multiple_choice)
    answer_value = db.Column(db.String(255), nullable=True)

    # Tekst odpowiedzi (dla textarea, komentarzy w yes_no_comment)
    answer_text = db.Column(db.Text, nullable=True)

    # Opcje odpowiedzi (dla checkbox_list - JSON array)
    answer_options = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime, default=get_local_now)

    # Relationships
    response = db.relationship('FeedbackResponse', back_populates='answers')
    question = db.relationship('FeedbackQuestion', back_populates='answers')

    def __repr__(self):
        return f'<FeedbackAnswer #{self.id} question={self.question_id}>'

    @property
    def display_value(self):
        """Wartość do wyświetlenia"""
        if self.answer_value:
            return self.answer_value
        if self.answer_text:
            return self.answer_text[:100] + '...' if len(self.answer_text) > 100 else self.answer_text
        if self.answer_options:
            return ', '.join(self.answer_options)
        return '-'
