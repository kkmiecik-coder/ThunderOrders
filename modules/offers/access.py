"""Kontrola dostępu do prywatnych stron sprzedaży."""
from flask import redirect, url_for, request, abort
from flask_login import current_user
from extensions import db
from modules.offers.models import offer_page_groups, offer_page_users
from modules.auth.models import user_group_members


def user_is_in_page_audience(page, user):
    """Czy `user` należy do odbiorców prywatnej strony (osoby ad-hoc lub przez grupę)."""
    direct = db.session.query(offer_page_users.c.id).filter(
        offer_page_users.c.offer_page_id == page.id,
        offer_page_users.c.user_id == user.id,
    ).first()
    if direct:
        return True

    via_group = db.session.query(offer_page_groups.c.id).join(
        user_group_members,
        offer_page_groups.c.user_group_id == user_group_members.c.user_group_id,
    ).filter(
        offer_page_groups.c.offer_page_id == page.id,
        user_group_members.c.user_id == user.id,
    ).first()
    return via_group is not None


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
