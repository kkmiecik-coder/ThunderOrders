"""Quick script to check users with incomplete profiles."""
from app import create_app

app = create_app()
with app.app_context():
    from modules.auth.models import User
    users = User.query.filter_by(profile_completed=False).all()
    if not users:
        print("Brak uzytkownikow z niekompletnym profilem.")
    for u in users:
        print(f"{u.id} | {u.email} | {u.first_name} {u.last_name} | verified={u.email_verified} | active={u.is_active} | {u.created_at}")
