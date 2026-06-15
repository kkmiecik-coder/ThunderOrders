"""Kontrola dostępu do prywatnych stron sprzedaży."""
from sqlalchemy import select
from flask import redirect, url_for, request, abort
from flask_login import current_user
from extensions import db
from modules.offers.models import offer_page_groups, offer_page_users
from modules.auth.models import user_group_members


def user_is_in_page_audience(page, user):
    """Czy `user` należy do odbiorców prywatnej strony (osoby ad-hoc lub przez grupę)."""
    direct = db.session.execute(
        select(offer_page_users.c.id).where(
            offer_page_users.c.offer_page_id == page.id,
            offer_page_users.c.user_id == user.id,
        )
    ).first()
    if direct:
        return True

    via_group = db.session.execute(
        select(offer_page_groups.c.id)
        .join(
            user_group_members,
            offer_page_groups.c.user_group_id == user_group_members.c.user_group_id,
        )
        .where(
            offer_page_groups.c.offer_page_id == page.id,
            user_group_members.c.user_id == user.id,
        )
    ).first()
    return via_group is not None


def user_can_access_offer_page(page, user):
    """Wersja bool dla API (mobile/JSON) — bez current_user/redirect.

    True gdy strona publiczna, user jest adminem/modem, albo nalezy do audytorium.
    """
    if not page.is_private:
        return True
    if user is None:
        return False
    if getattr(user, 'role', None) in ('admin', 'mod'):
        return True
    return user_is_in_page_audience(page, user)


def check_offer_page_access(page):
    """
    Bramka dostępu dla publicznych route'ów na tokenie strony.
    Zwraca:
      - None  -> wpuść (kontynuuj route)
      - Response (redirect) -> anonim na stronie prywatnej
    Rzuca abort(404) gdy zalogowany użytkownik nie ma dostępu.
    """
    if not page.is_private:
        return None
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login', next=request.url))
    if current_user.role in ('admin', 'mod'):
        return None
    if user_is_in_page_audience(page, current_user):
        return None
    abort(404)
