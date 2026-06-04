"""
Tworzy 20 testowych userów (stresstest1..20@local.test, hasło: test1234)
+ 1 testowego admina (stressadmin@local.test, hasło: test1234)
do lokalnych smoke i stress testów.

Usuwa istniejących z tym samym wzorcem emaili przed utworzeniem (idempotentne).
"""
import sys
sys.path.insert(0, '/Users/konradkmiecik/Documents/GitHub/ThunderOrders')

from app import create_app
from extensions import db
from modules.auth.models import User
from werkzeug.security import generate_password_hash
from datetime import datetime

app = create_app()

PASSWORD = 'test1234'
ADMIN_EMAIL = 'stressadmin@local.test'
USER_EMAIL_PATTERN = 'stresstest{}@local.test'

with app.app_context():
    # Wyczyść powiązane dane (orders, reservations, subscriptions, etc.) przed kasowaniem userów
    test_user_ids = [u.id for u in User.query.filter(User.email.like('stress%@local.test')).all()]
    if test_user_ids:
        from sqlalchemy import text
        # Tabele zależne — kasujemy w kolejności od najgłębszych
        for sql in [
            "DELETE oi FROM order_items oi JOIN orders o ON oi.order_id=o.id WHERE o.user_id IN :ids",
            "DELETE FROM offer_reservations WHERE session_id IN (SELECT session_id FROM orders WHERE user_id IN :ids)",
            "DELETE FROM orders WHERE user_id IN :ids",
            "DELETE FROM offer_product_notification_subscriptions WHERE user_id IN :ids",
            "DELETE FROM activity_log WHERE user_id IN :ids",
        ]:
            try:
                db.session.execute(text(sql).bindparams(ids=tuple(test_user_ids))).rowcount
            except Exception:
                db.session.rollback()
        db.session.commit()

    deleted = User.query.filter(User.email.like('stress%@local.test')).delete(synchronize_session=False)
    db.session.commit()
    print(f"Wyczyszczono {deleted} istniejących test userów + ich dane.")

    # Stwórz admina testowego
    admin = User(
        email=ADMIN_EMAIL,
        password_hash=generate_password_hash(PASSWORD),
        first_name='Stress',
        last_name='Admin',
        role='admin',
        is_active=True,
        email_verified=True,
        created_at=datetime.now(),
    )
    db.session.add(admin)

    # Stwórz 40 zwykłych userów
    for i in range(1, 41):
        u = User(
            email=USER_EMAIL_PATTERN.format(i),
            password_hash=generate_password_hash(PASSWORD),
            first_name=f'Test{i}',
            last_name='User',
            role='client',
            is_active=True,
            email_verified=True,
            created_at=datetime.now(),
        )
        db.session.add(u)

    db.session.commit()

    # Weryfikacja
    test_users = User.query.filter(User.email.like('stress%@local.test')).all()
    print(f"Utworzono {len(test_users)} test userów:")
    for u in test_users[:5]:
        print(f"  - {u.email} ({u.role}) id={u.id}")
    print(f"  ... + {len(test_users)-5} więcej")
    print(f"\nHasło dla wszystkich: {PASSWORD}")
