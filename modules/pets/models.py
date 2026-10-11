"""Modele modułu pupili (tamagotchi).

Spec: docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md §3.3

Zasada: w bazie leżą wartości pasków W CHWILI `state_at`; stan „na teraz" liczy
modules/pets/rules.py. Modele nie zawierają logiki gry. Kolumny muszą być 1:1
z migracją f3e9a1c7b2d4 (pilnuje tego tests/test_pets_migration.py).
"""
from extensions import db
from modules.auth.models import get_local_now

PET_STATUSES = ('egg', 'alive', 'dead', 'merged')
EGG_SOURCES = ('start', 'monthly', 'rescue', 'granted')
EVENT_TYPES = (
    'claim', 'grant', 'warm', 'hatch_new', 'hatch_dupe', 'merge',
    'feed', 'play', 'wash', 'heal', 'pat', 'wake', 'light',
    'die', 'rename', 'milestone', 'alert',
)
# Zdarzenia akcji — cron kasuje je po 90 dniach. Reszta jest trwała (historia pupila, raport).
PRUNABLE_EVENT_TYPES = ('feed', 'play', 'wash', 'heal', 'pat', 'wake', 'warm', 'light', 'alert')


class PetProfile(db.Model):
    """Jeden na użytkownika; powstaje przy odbiorze jajka startowego (nie przy GET)."""
    __tablename__ = 'pet_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, unique=True)
    # NULL = towarzysz automatyczny (ten, który najbardziej potrzebuje opieki)
    companion_pet_id = db.Column(db.Integer, db.ForeignKey('pets.id', ondelete='SET NULL'),
                                 nullable=True)
    companion_enabled = db.Column(db.Boolean, nullable=False, default=True,
                                  server_default=db.text('1'))
    dupes_in_row = db.Column(db.Integer, nullable=False, default=0, server_default=db.text('0'))
    start_egg_claimed_at = db.Column(db.DateTime, nullable=False, default=get_local_now)
    # Licznik miesięczny biegnie od ODBIORU (startowego lub poprzedniego miesięcznego)
    last_monthly_egg_at = db.Column(db.DateTime, nullable=False, default=get_local_now)
    monthly_notified_at = db.Column(db.DateTime, nullable=True)
    granted_eggs_pending = db.Column(db.SmallInteger, nullable=False, default=0,
                                     server_default=db.text('0'))
    created_at = db.Column(db.DateTime, nullable=False, default=get_local_now)

    # passive_deletes: przy db.session.delete(user) kasuje baza (ondelete=CASCADE),
    # ORM nie próbuje NULL-ować user_id (NOT NULL) — recenzja etapu 2, Important 1
    user = db.relationship('User', backref=db.backref('pet_profile', uselist=False, passive_deletes=True))
    companion_pet = db.relationship('Pet', foreign_keys=[companion_pet_id])

    def __repr__(self):
        return f'<PetProfile user={self.user_id}>'


class Pet(db.Model):
    """Jajko, żywy pupil, karta pamięci (dead) albo wtopiony duplikat (merged)."""
    __tablename__ = 'pets'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.Enum(*PET_STATUSES, name='pet_status'), nullable=False, default='egg')
    species = db.Column(db.String(32), nullable=True)   # NULL dopóki jajko
    name = db.Column(db.String(20), nullable=True)

    # --- jajko ---
    egg_source = db.Column(db.Enum(*EGG_SOURCES, name='pet_egg_source'), nullable=False)
    # Zamrożone przy odbiorze: zmiana ustawień nie przestawia trwających inkubacji
    egg_hours = db.Column(db.SmallInteger, nullable=False, default=168)
    egg_progress_sec = db.Column(db.Integer, nullable=False, default=0, server_default=db.text('0'))
    egg_progress_at = db.Column(db.DateTime, nullable=False, default=get_local_now)
    boost_until = db.Column(db.DateTime, nullable=True)
    egg_ready_notified_at = db.Column(db.DateTime, nullable=True)
    hatched_at = db.Column(db.DateTime, nullable=True)
    merged_into_pet_id = db.Column(db.Integer, db.ForeignKey('pets.id', ondelete='SET NULL'),
                                   nullable=True)

    # --- paski w chwili state_at (0–100) ---
    hunger = db.Column(db.Float, nullable=False, default=100.0)
    fun = db.Column(db.Float, nullable=False, default=100.0)
    clean = db.Column(db.Float, nullable=False, default=100.0)
    health = db.Column(db.Float, nullable=False, default=100.0)
    state_at = db.Column(db.DateTime, nullable=False, default=get_local_now)
    awake_until = db.Column(db.DateTime, nullable=True)   # okno po „Obudź"

    stars = db.Column(db.SmallInteger, nullable=False, default=0, server_default=db.text('0'))
    care_days = db.Column(db.Integer, nullable=False, default=0, server_default=db.text('0'))
    last_care_date = db.Column(db.Date, nullable=True)
    last_heal_at = db.Column(db.DateTime, nullable=True)
    # 0 brak, 1 smutny, 2 chory, 3 krytyczny, 4 odszedł — raz na epizod
    notify_level = db.Column(db.SmallInteger, nullable=False, default=0, server_default=db.text('0'))

    # --- odejście ---
    died_at = db.Column(db.DateTime, nullable=True)
    death_notified_at = db.Column(db.DateTime, nullable=True)
    rescue_egg_claimed_at = db.Column(db.DateTime, nullable=True)
    rescue_reminder_sent_at = db.Column(db.DateTime, nullable=True)
    lights_count = db.Column(db.Integer, nullable=False, default=0, server_default=db.text('0'))
    last_light_date = db.Column(db.Date, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=get_local_now)  # = odebranie jajka

    __table_args__ = (
        db.Index('ix_pets_user_status', 'user_id', 'status'),
    )

    user = db.relationship('User', backref=db.backref('pets', lazy='select', passive_deletes=True))
    merged_into = db.relationship('Pet', remote_side=[id], foreign_keys=[merged_into_pet_id])

    def __repr__(self):
        return f'<Pet {self.id} {self.status} {self.species or "?"} user={self.user_id}>'


class PetEvent(db.Model):
    """Log zdarzeń: limit pat pat, dni opieki, statystyki, odznaki, raport."""
    __tablename__ = 'pet_events'

    id = db.Column(db.Integer, primary_key=True)
    pet_id = db.Column(db.Integer, db.ForeignKey('pets.id', ondelete='CASCADE'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    # pat: liczba ZALICZONYCH klepnięć w paczce; milestone: numer progu; reszta: 1
    value = db.Column(db.Integer, nullable=False, default=1, server_default=db.text('1'))
    created_at = db.Column(db.DateTime, nullable=False, default=get_local_now)

    __table_args__ = (
        db.Index('ix_pet_events_pet_type_created', 'pet_id', 'type', 'created_at'),
        db.Index('ix_pet_events_user_created', 'user_id', 'created_at'),
    )

    pet = db.relationship('Pet', backref=db.backref('events', lazy='dynamic', passive_deletes=True))

    def __repr__(self):
        return f'<PetEvent {self.type} pet={self.pet_id} value={self.value}>'
