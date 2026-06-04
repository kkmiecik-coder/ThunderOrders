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
    # Wyczyść istniejące testowe konta (idempotentność)
    deleted = User.query.filter(User.email.like('stress%@local.test')).delete(synchronize_session=False)
    db.session.commit()
    print(f"Wyczyszczono {deleted} istniejących test userów.")

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

    # Stwórz 20 zwykłych userów
    for i in range(1, 21):
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
