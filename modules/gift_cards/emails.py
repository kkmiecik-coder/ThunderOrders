"""Maile akcji gratisowych kart: zaproszenie do rankingu i wynik rozdziału."""
from flask import url_for

from modules.auth.models import User
from modules.gift_cards.models import GiftAssignment
from modules.gift_cards.service import compute_entitlements, pool_breakdown
from utils.email_sender import prepare_email, send_email_batch
from utils.timeutil import to_pl


def campaign_title(campaign) -> str:
    """Nagłówek akcji dla klientki: „Gratisowe karty” albo „Twoje karty” (kupione produkty)."""
    return 'Twoje karty' if campaign.is_purchase else 'Gratisowe karty'


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


def entitled_summary(campaign, ent) -> str:
    """„przysługują Ci 3 karty (2 karty — Benefit 50k, 1 karta — Benefit 100k)” — rozbicie tylko przy kilku pulach."""
    text = _entitled_text(ent.total)
    parts = pool_breakdown(campaign, ent)
    if len(campaign.pools) > 1 and parts:
        text += ' (' + ', '.join(f'{pl_cards(n)} — {pool.label}' for pool, n in parts) + ')'
    return text


def cards_by_pool_text(campaign, assignments) -> str:
    """„San, Yunho” — a przy kilku pulach „Benefit 50k: San, Yunho; Benefit 100k: San”."""
    if len(campaign.pools) <= 1:
        return ', '.join(a.card_type.name for a in assignments)
    parts = []
    for pool in campaign.pools:
        names = [a.card_type.name for a in assignments if a.pool_id == pool.id]
        if names:
            parts.append(f'{pool.label}: {", ".join(names)}')
    return '; '.join(parts)


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
        msg = prepare_email(
            to=user.email,
            subject=f'{campaign_title(campaign)}: {campaign.name} - ThunderOrders',
            template='gift_cards_invite',
            title=campaign_title(campaign),
            user_name=user.first_name,
            campaign_name=campaign.name,
            entitled_text=entitled_summary(campaign, entitlements[user.id]),
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
    by_user = {}
    for a in assignments:
        by_user.setdefault(a.user_id, []).append(a)
    url = url_for('gift_cards.client_campaign', cid=campaign.id, _external=True)
    result_title = 'Twoje karty' if campaign.is_purchase else 'Twoje gratisowe karty'
    messages = []
    for user in _recipients(entitlements):
        cards = by_user.get(user.id, [])
        missing = entitlements[user.id].total - len(cards)
        msg = prepare_email(
            to=user.email,
            subject=f'{result_title}: {campaign.name} - ThunderOrders',
            template='gift_cards_result',
            title=result_title,
            user_name=user.first_name,
            campaign_name=campaign.name,
            cards=cards_by_pool_text(campaign, cards),
            shortage_text=(f'Brakuje {pl_cards(missing)} — skontaktujemy się w tej sprawie.'
                           if missing > 0 else None),
            url=url,
        )
        if msg is not None:
            messages.append(msg)
    if messages:
        send_email_batch(messages)
    return len(messages)
