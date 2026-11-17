"""Uprawnienia do gratisowych kart i kolejka rozdziału."""
import json
from dataclasses import dataclass, field
from datetime import datetime

from extensions import db
from modules.auth.models import User
from modules.orders.models import Order, OrderItem
from modules.gift_cards.allocation import Person, allocate
from modules.gift_cards.models import (
    GiftAssignment, GiftCampaign, GiftCardType, GiftParticipant, GiftRaceEntry,
    STATUS_APPROVED, STATUS_CLOSED, STATUS_DISTRIBUTED, STATUS_OPEN,
)

EXCLUDED_ORDER_STATUSES = ('anulowane', 'zwrocone')
LOCKING_ORDER_STATUSES = ('spakowane', 'wyslane', 'dostarczone')


@dataclass
class Entitlement:
    user_id: int
    items: list = field(default_factory=list)  # (order_item_id, quantity), wg Order.created_at, OrderItem.id
    first_order_at: datetime = None
    pool_items: dict = field(default_factory=dict)  # pool_id -> [(order_item_id, quantity), ...]

    @property
    def total(self) -> int:
        return sum(q for _, q in self.items)

    def pool_total(self, pool_id) -> int:
        return sum(q for _, q in self.pool_items.get(pool_id, []))


def compute_entitlements(campaign) -> dict:
    """Uprawnienia klientów: user_id -> Entitlement (gratisowe pozycje z zamówień akcji).

    Każdy produkt-gratis akcji to osobna pula; `items`/`total` sumują wszystkie pule.
    """
    page_ids = campaign.offer_page_ids
    pool_of = {p.bonus_product_id: p.id for p in campaign.pools if p.bonus_product_id is not None}
    if not pool_of or not page_ids:
        return {}

    rows = (
        db.session.query(OrderItem.id, OrderItem.quantity, OrderItem.product_id, Order.user_id, Order.created_at)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            OrderItem.is_bonus.is_(True),
            OrderItem.product_id.in_(list(pool_of)),
            Order.offer_page_id.in_(page_ids),
            Order.status.notin_(EXCLUDED_ORDER_STATUSES),
        )
        .order_by(Order.created_at, OrderItem.id)
        .all()
    )

    result = {}
    for item_id, quantity, product_id, user_id, created_at in rows:
        ent = result.get(user_id)
        if ent is None:
            ent = result[user_id] = Entitlement(user_id=user_id, items=[], first_order_at=created_at)
        ent.items.append((item_id, quantity))
        ent.pool_items.setdefault(pool_of[product_id], []).append((item_id, quantity))
    return result


def pool_breakdown(campaign, ent) -> list:
    """[(pula, ile kart)] — tylko pule, w których klient ma karty; kolejność jak w akcji."""
    if ent is None:
        return []
    return [(pool, ent.pool_total(pool.id)) for pool in campaign.pools if ent.pool_total(pool.id) > 0]


def queue_order(campaign, entitlements: dict) -> list:
    """Kolejka: najpierw uprawnieni z wyścigu (wg id wpisu), potem reszta wg pierwszego zamówienia."""
    racers = [e.user_id for e in campaign.race_entries if e.user_id in entitlements]
    racer_set = set(racers)
    rest = sorted(
        (e for uid, e in entitlements.items() if uid not in racer_set),
        key=lambda e: (e.first_order_at, e.user_id),
    )
    return racers + [e.user_id for e in rest]


def queue_position(campaign, user_id):
    """1-based miejsce w wyścigu albo None, gdy użytkownik nie kliknął."""
    entry = GiftRaceEntry.query.filter_by(campaign_id=campaign.id, user_id=user_id).first()
    if entry is None:
        return None
    return GiftRaceEntry.query.filter(
        GiftRaceEntry.campaign_id == campaign.id, GiftRaceEntry.id <= entry.id
    ).count()


def dashboard_campaigns(user_id) -> list:
    """Akcje do kafelka na stronie głównej klienta: otwarte / zamknięte / rozdzielone,
    w których klient ma gratisy. Szkice i zatwierdzone się nie pokazują."""
    from modules.gift_cards.emails import entitled_summary
    from utils.timeutil import to_pl, utcnow

    campaigns = (GiftCampaign.query
                 .filter(GiftCampaign.status.in_([STATUS_OPEN, STATUS_CLOSED, STATUS_DISTRIBUTED]))
                 .order_by(GiftCampaign.race_at, GiftCampaign.id).all())
    now = utcnow()
    result = []
    for campaign in campaigns:
        ent = compute_entitlements(campaign).get(user_id)
        if not ent or ent.total <= 0:
            continue
        participant = GiftParticipant.query.filter_by(campaign_id=campaign.id, user_id=user_id).first()
        text = entitled_summary(campaign, ent)
        result.append({
            'campaign': campaign,
            'entitled_text': text[:1].upper() + text[1:],
            'is_open': campaign.status == STATUS_OPEN,
            'started': campaign.race_at is not None and campaign.race_at <= now,
            'start_text': to_pl(campaign.race_at).strftime('%d.%m, godz. %H:%M') if campaign.race_at else None,
            'has_ranking': bool(_valid_ranking(participant, [t.id for t in campaign.card_types])),
            'position': queue_position(campaign, user_id),
        })
    return result


class GiftCardsError(Exception):
    """Błąd biznesowy rozdziału; komunikat po polsku do pokazania we flash."""


def _valid_ranking(participant, type_ids):
    """Ranking jest ważny tylko, gdy jest dokładnie permutacją aktualnych rodzajów kart."""
    if participant is None:
        return ()
    ranking = participant.ranking
    if len(ranking) == len(type_ids) and set(ranking) == set(type_ids):
        return tuple(ranking)
    return ()


def run_distribution(campaign):
    """Rozdziela karty każdej puli osobno (ta sama kolejka i ranking) i zapisuje GiftAssignment.

    Wynik: {pool_id: AllocationResult}.
    """
    if campaign.status not in (STATUS_CLOSED, STATUS_DISTRIBUTED):
        raise GiftCardsError('Rozdział jest możliwy dopiero po zamknięciu akcji.')
    types = list(campaign.card_types)
    pools = list(campaign.pools)
    stock = campaign.stock_map()
    if not types or not pools or any(
            not isinstance(stock.get((pool.id, t.id)), int) or stock[(pool.id, t.id)] < 0
            for pool in pools for t in types):
        raise GiftCardsError('Uzupełnij ilości wszystkich rodzajów kart.')
    type_ids = [t.id for t in types]

    entitlements = compute_entitlements(campaign)
    order = queue_order(campaign, entitlements)
    participants = {p.user_id: p for p in campaign.participants}
    rankings = {uid: _valid_ranking(participants.get(uid), type_ids) for uid in order}

    GiftAssignment.query.filter_by(campaign_id=campaign.id).delete()
    results = {}
    for pool in pools:
        people = [Person(uid, entitlements[uid].pool_total(pool.id), rankings[uid])
                  for uid in order if entitlements[uid].pool_total(pool.id) > 0]
        result = results[pool.id] = allocate(people, {t.id: stock[(pool.id, t.id)] for t in types})
        for person in people:
            slots = [item_id for item_id, qty in entitlements[person.user_id].pool_items[pool.id]
                     for _ in range(qty)]
            for slot, pick in zip(slots, result.picks[person.user_id]):
                db.session.add(GiftAssignment(
                    campaign_id=campaign.id, user_id=person.user_id, order_item_id=slot,
                    pool_id=pool.id, card_type_id=pick.type_id, round_no=pick.round_no,
                    rank_position=pick.rank_position, is_duplicate=pick.is_duplicate,
                ))
    campaign.entitlements_snapshot = json.dumps(
        {str(uid): [[item_id, qty] for item_id, qty in ent.items] for uid, ent in entitlements.items()}
    )
    campaign.status = STATUS_DISTRIBUTED
    db.session.commit()
    return results


def _snapshot(campaign) -> dict:
    """Uprawnienia zapisane przy rozdziale: user_id -> {order_item_id: ilość}."""
    raw = json.loads(campaign.entitlements_snapshot or '{}')
    return {int(uid): {item_id: qty for item_id, qty in items} for uid, items in raw.items()}


def type_usage(campaign) -> list:
    """Dla każdej pary pula × rodzaj: (pula, rodzaj, ile przydzielono, ilość)."""
    counts = {
        (pool_id, type_id): n for pool_id, type_id, n in
        db.session.query(GiftAssignment.pool_id, GiftAssignment.card_type_id, db.func.count(GiftAssignment.id))
        .filter(GiftAssignment.campaign_id == campaign.id)
        .group_by(GiftAssignment.pool_id, GiftAssignment.card_type_id).all()
    }
    stock = campaign.stock_map()
    return [(pool, t, counts.get((pool.id, t.id), 0), stock.get((pool.id, t.id)) or 0)
            for pool in campaign.pools for t in campaign.card_types]


def _entitlement_problems(campaign) -> list:
    """Różnice między obecnymi uprawnieniami a zapisanymi przy rozdziale."""
    if campaign.entitlements_snapshot is None:
        return ['Brak zapisu uprawnień z chwili rozdziału.']
    before = _snapshot(campaign)
    now = {uid: dict(ent.items) for uid, ent in compute_entitlements(campaign).items()}
    uids = sorted(set(before) | set(now))
    users = {u.id: u for u in User.query.filter(User.id.in_(uids)).all()} if uids else {}
    problems = []
    for uid in uids:
        user = users.get(uid)
        name = user.full_name if user else f'Klient #{uid}'
        old, new = before.get(uid), now.get(uid)
        if old is None:
            problems.append(f'{name} — nowa osoba uprawniona do kart.')
            continue
        if new is None:
            problems.append(f'{name} — nie ma już uprawnień do kart (np. anulowane lub zwrócone zamówienie).')
            continue
        if set(new) - set(old):
            problems.append(f'{name} — nowa pozycja gratisowa w zamówieniu.')
        if set(old) - set(new):
            problems.append(f'{name} — pozycja gratisowa zniknęła (np. anulowane lub zwrócone zamówienie).')
        for item_id in sorted(set(old) & set(new)):
            if old[item_id] != new[item_id]:
                problems.append(f'{name} — zmieniła się ilość gratisu ({old[item_id]} → {new[item_id]}).')
    return problems


def _stock_problems(campaign) -> list:
    """Rodzaje, którym przydzielono więcej kart niż jest sztuk (np. po ręcznych zamianach)."""
    several = len(campaign.pools) > 1
    return [
        f'{card_type.name}{f" ({pool.label})" if several else ""} — przydzielono {assigned}, '
        f'a jest {quantity} szt. (o {assigned - quantity} za dużo).'
        for pool, card_type, assigned, quantity in type_usage(campaign) if assigned > quantity
    ]


def distribution_problems(campaign) -> list:
    """Powody, dla których rozdziału nie można zatwierdzić (pusta lista = można).

    Porównuje obecne uprawnienia z zapisanymi przy rozdziale (anulowane/zwrócone zamówienia,
    nowe pozycje gratisowe, zmienione ilości) i sprawdza, czy żaden rodzaj nie ma więcej
    przydziałów niż sztuk. Dotyczy tylko statusu 'rozdzielona'.
    """
    if campaign.status != STATUS_DISTRIBUTED:
        return []
    return _entitlement_problems(campaign) + _stock_problems(campaign)


def swap_assignment(assignment_id, new_type_id):
    """Ręczna zamiana rodzaju karty w przydziale (tylko w statusie rozdzielona)."""
    assignment = db.session.get(GiftAssignment, assignment_id)
    if assignment is None:
        raise GiftCardsError('Nie znaleziono przydziału.')
    campaign = assignment.campaign
    if campaign.status != STATUS_DISTRIBUTED:
        raise GiftCardsError('Zamiany są możliwe tylko przed zatwierdzeniem rozdziału.')
    new_type = db.session.get(GiftCardType, new_type_id)
    if new_type is None or new_type.campaign_id != campaign.id:
        raise GiftCardsError('Ten rodzaj karty nie należy do tej akcji.')
    if new_type.id != assignment.card_type_id:
        # Zamiana swobodna — nadmiar sztuk blokuje dopiero zatwierdzenie (distribution_problems).
        assignment.card_type_id = new_type.id
        db.session.flush()

    type_ids = [t.id for t in campaign.card_types]
    ranking = _valid_ranking(
        GiftParticipant.query.filter_by(campaign_id=campaign.id, user_id=assignment.user_id).first(),
        type_ids,
    )
    # Powtórki liczymy w obrębie puli przydziału (San z 50k i San ze 100k to różne karty).
    rows = (GiftAssignment.query.filter_by(campaign_id=campaign.id, user_id=assignment.user_id,
                                           pool_id=assignment.pool_id)
            .order_by(GiftAssignment.round_no, GiftAssignment.id).all())
    seen = set()
    for row in rows:
        row.is_duplicate = row.card_type_id in seen
        seen.add(row.card_type_id)
        row.rank_position = ranking.index(row.card_type_id) + 1 if row.card_type_id in ranking else None
    db.session.commit()


def approve(campaign):
    if campaign.status != STATUS_DISTRIBUTED:
        raise GiftCardsError('Zatwierdzić można tylko rozdzieloną akcję.')
    if _entitlement_problems(campaign):
        raise GiftCardsError('Zamówienia albo ilości zmieniły się od rozdziału — rozdziel karty ponownie.')
    if _stock_problems(campaign):
        raise GiftCardsError('Część rodzajów ma więcej przydziałów niż sztuk — popraw zamiany albo ilości.')
    # Warunkowa zmiana statusu: przy dwóch równoczesnych kliknięciach tylko jedno przejdzie.
    changed = (GiftCampaign.query.filter_by(id=campaign.id, status=STATUS_DISTRIBUTED)
               .update({'status': STATUS_APPROVED}, synchronize_session=False))
    db.session.commit()
    if changed != 1:
        raise GiftCardsError('Ta akcja została już zatwierdzona.')


def can_revert(campaign) -> bool:
    """Cofnięcie zatwierdzenia jest zablokowane, gdy zamówienie z przydziałów jest już spakowane/wysłane."""
    locked = (
        db.session.query(Order.id)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(GiftAssignment, GiftAssignment.order_item_id == OrderItem.id)
        .filter(GiftAssignment.campaign_id == campaign.id, Order.status.in_(LOCKING_ORDER_STATUSES))
        .first()
    )
    return locked is None


def revert_approval(campaign):
    if campaign.status != STATUS_APPROVED:
        raise GiftCardsError('Akcja nie jest zatwierdzona.')
    if not can_revert(campaign):
        raise GiftCardsError('Nie można cofnąć: część zamówień jest już spakowana lub wysłana.')
    campaign.status = STATUS_DISTRIBUTED
    db.session.commit()


def item_gift_label(item):
    """Etykieta kart na pozycji gratisowej: nazwy rodzajów, "przydział w toku" albo None."""
    if not item.is_bonus:
        return None
    rows = (GiftAssignment.query.filter_by(order_item_id=item.id)
            .order_by(GiftAssignment.round_no, GiftAssignment.id).all())
    if rows and rows[0].campaign.status == STATUS_APPROVED:
        return ', '.join(r.card_type.name for r in rows)

    return 'przydział w toku' if _campaign_for_item(
        item, (STATUS_OPEN, STATUS_CLOSED, STATUS_DISTRIBUTED)) else None


def _campaign_for_item(item, statuses):
    """Akcja w danym statusie, do której należy pozycja gratisowa (ten sam produkt i strona oferty)."""
    if not item.is_bonus:
        return None
    page_id = item.order.offer_page_id if item.order else None
    if page_id is None or item.product_id is None:
        return None
    return (
        GiftCampaign.query
        .filter(GiftCampaign.pools.any(bonus_product_id=item.product_id),
                GiftCampaign.status.in_(statuses),
                GiftCampaign.pages.any(offer_page_id=page_id))
        .first()
    )


def open_campaign_for_item(item):
    """Otwarta akcja obejmująca pozycję gratisową (do linku na stronie zamówienia) albo None."""
    return _campaign_for_item(item, (STATUS_OPEN,))
