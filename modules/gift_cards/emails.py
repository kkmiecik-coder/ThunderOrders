"""Maile akcji gratisowych kart: zaproszenie do rankingu i wynik rozdziału."""
from flask import url_for

from modules.auth.models import User
from modules.gift_cards.models import GiftAssignment
from modules.gift_cards.service import compute_entitlements
from utils.email_sender import prepare_email, send_email_batch
from utils.timeutil import to_pl


def pl_cards(n: int) -> str:
    """„1 karta", „2 karty", „5 kart" (z wyjątkiem 12–14, które mają „kart")."""
    if n == 1:
        return '1 karta'
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f'{n} karty'
    return f'{n} kart'


def _entitled_text(n: int) -> str:
    """„przysługuje Ci 1 karta", „przysługują Ci 2 karty", „przysługuje Ci 5 kart".

    Liczebnik z „kart" (5+, 12–14) łączy się z czasownikiem w liczbie pojedynczej.
    """
    plural_verb = 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14
    return f'{"przysługują" if plural_verb else "przysługuje"} Ci {pl_cards(n)}'


def _recipients(entitlements):
    users = User.query.filter(User.id.in_(list(entitlements))).all() if entitlements else []
    return [u for u in sorted(users, key=lambda u: u.id) if u.email]


def send_invites(campaign) -> int:
    """Zaproszenie do ułożenia rankingu — do każdego uprawnionego. Zwraca liczbę maili."""
    entitlements = compute_entitlements(campaign)
    url = url_for('gift_cards.client_campaign', cid=campaign.id, _external=True)
    race_at = to_pl(campaign.race_at).strftime('%d.%m.%Y %H:%M') if campaign.race_at else None
    messages = []
    for user in _recipients(entitlements):
        total = entitlements[user.id].total
        msg = prepare_email(
            to=user.email,
            subject=f'Gratisowe karty: {campaign.name} - ThunderOrders',
            template='gift_cards_invite',
            user_name=user.first_name,
            campaign_name=campaign.name,
            entitled_text=_entitled_text(total),
            race_at=race_at,
            url=url,
        )
        if msg is not None:
            messages.append(msg)
    if messages:
        send_email_batch(messages)
    return len(messages)


def send_results(campaign) -> int:
    """Wynik rozdziału — lista przydzielonych kart i ewentualny niedobór. Zwraca liczbę maili."""
    entitlements = compute_entitlements(campaign)
    assignments = (
        GiftAssignment.query.filter_by(campaign_id=campaign.id)
        .order_by(GiftAssignment.user_id, GiftAssignment.round_no, GiftAssignment.id).all()
    )
    names = {}
    for a in assignments:
        names.setdefault(a.user_id, []).append(a.card_type.name)
    url = url_for('gift_cards.client_campaign', cid=campaign.id, _external=True)
    messages = []
    for user in _recipients(entitlements):
        cards = names.get(user.id, [])
        missing = entitlements[user.id].total - len(cards)
        msg = prepare_email(
            to=user.email,
            subject=f'Twoje gratisowe karty: {campaign.name} - ThunderOrders',
            template='gift_cards_result',
            user_name=user.first_name,
            campaign_name=campaign.name,
            cards=', '.join(cards),
            shortage_text=(f'Brakuje {pl_cards(missing)} — skontaktujemy się w tej sprawie.'
                           if missing > 0 else None),
            url=url,
        )
        if msg is not None:
            messages.append(msg)
    if messages:
        send_email_batch(messages)
    return len(messages)
