"""Model blocklisty refresh tokenów dla mobilnego API (realny logout / unieważnianie)."""

from extensions import db
from modules.orders.models import get_local_now


class MobileTokenBlocklist(db.Model):
    __tablename__ = 'mobile_token_blocklist'

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, index=True, unique=True)
    token_type = db.Column(db.String(16), nullable=False)  # 'access' | 'refresh'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), index=True)
    expires_at = db.Column(db.DateTime, nullable=False)  # czas lokalny PL (spójnie z created_at)
    created_at = db.Column(db.DateTime, default=get_local_now)

    @classmethod
    def contains(cls, jti):
        return db.session.query(cls.id).filter_by(jti=jti).first() is not None

    @classmethod
    def purge_expired(cls):
        """Lazy cleanup wygasłych wpisów (wołane przy logout). Commit po stronie wołającego."""
        cls.query.filter(cls.expires_at < get_local_now()).delete(synchronize_session=False)


class MobileIdempotencyKey(db.Model):
    """Idempotency-Key dla mutacji składających zamówienia (checkout + place-order).

    Wzorzec claim-first (D2a): wiersz z `status_code=NULL` wstawiany PRZED przetwarzaniem;
    UNIQUE (user_id, idempotency_key) gwarantuje brak duplikatu nawet przy współbieżności.
    """
    __tablename__ = 'mobile_idempotency_keys'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    idempotency_key = db.Column(db.String(64), nullable=False)
    endpoint = db.Column(db.String(64), nullable=False)
    status_code = db.Column(db.Integer, nullable=True)      # NULL = processing (claim)
    response_body = db.Column(db.Text, nullable=True)       # JSON serializowana odpowiedź
    created_at = db.Column(db.DateTime, default=get_local_now, index=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'idempotency_key', name='uq_idem_user_key'),
    )

    @classmethod
    def purge_expired(cls, ttl_hours=48):
        """Lazy cleanup wpisów starszych niż TTL. Commit po stronie wołającego."""
        from datetime import timedelta
        cutoff = get_local_now() - timedelta(hours=ttl_hours)
        cls.query.filter(cls.created_at < cutoff).delete(synchronize_session=False)


class MobileDevice(db.Model):
    """Token FCM urządzenia mobilnego (push). fcm_token globalnie unikalny — należy
    do dokładnie jednego, aktualnie zalogowanego usera (upsert/przepięcie przy POST)."""
    __tablename__ = 'mobile_device'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    fcm_token = db.Column(db.String(512), nullable=False, unique=True)
    platform = db.Column(db.String(16), nullable=False)   # android | ios | web
    last_used_at = db.Column(db.DateTime, default=get_local_now)
    created_at = db.Column(db.DateTime, default=get_local_now)
