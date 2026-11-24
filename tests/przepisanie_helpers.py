"""Wspólne pomocniki testów przepisywania zamówień (kolejka FIFO, partie z Korei)."""
from datetime import datetime, timezone
from decimal import Decimal

T0 = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)


def zamowienie_klientki(db, make_user, make_order, pozycje, created_at=T0, user=None, **kwargs):
    """Zamówienie ze strony sprzedaży id=1 z pozycjami [(product_id, ilosc, cena)]."""
    from modules.orders.models import OrderItem
    u = user or make_user()
    kwargs.setdefault('offer_page_id', 1)
    kwargs.setdefault('order_type', 'exclusive')
    o = make_order(u, created_at=created_at, **kwargs)
    total = Decimal('0')
    for pid, ilosc, cena in pozycje:
        cena = Decimal(str(cena))
        db.session.add(OrderItem(order_id=o.id, product_id=pid, quantity=ilosc,
                                 price=cena, total=cena * ilosc))
        total += cena * ilosc
    o.total_amount = total
    db.session.commit()
    return o


def partia(db, product_id, ilosc, created_at, koszt=None, stawka_cla=None, status='zamowione'):
    """Jedna partia z Korei (ProxyOrder + PolandOrder + PolandOrderItem). Zwraca PolandOrderItem."""
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem

    sufiks = f'{product_id}-{int(created_at.timestamp())}-{ilosc}'
    proxy = ProxyOrder(order_number=f'PRX/T{sufiks}', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product_id, quantity=ilosc,
                                unit_price=Decimal('10'), total_price=Decimal('10') * ilosc)
    db.session.add(proxy_item)
    db.session.flush()
    po = PolandOrder(order_number=f'PRX/PL/T{sufiks}', proxy_order_id=proxy.id, status=status)
    po.created_at = created_at
    db.session.add(po)
    db.session.flush()
    pi = PolandOrderItem(poland_order_id=po.id, proxy_order_item_id=proxy_item.id,
                         product_id=product_id, quantity=ilosc,
                         shipping_cost=Decimal(str(koszt)) if koszt is not None else Decimal('0'),
                         customs_vat_percentage=(Decimal(str(stawka_cla))
                                                 if stawka_cla is not None else None))
    db.session.add(pi)
    db.session.commit()
    return pi


def przydzial_gift_card(db, make_product, strona, user, item):
    """Akcja gift cards z jednym przydziałem karty do pozycji `item` klientki `user`."""
    from datetime import timedelta
    from modules.gift_cards.models import GiftAssignment, GiftCampaign, GiftCampaignPage
    from tests.gift_helpers import add_pool, add_types
    from utils.timeutil import utcnow

    c = GiftCampaign(name='Akcja', status='zatwierdzona', race_at=utcnow() - timedelta(minutes=1))
    db.session.add(c)
    db.session.commit()
    db.session.add(GiftCampaignPage(campaign_id=c.id, offer_page_id=strona.id))
    db.session.commit()
    add_pool(db, c, make_product(name='Gratis'))
    typ = add_types(db, c, {'San': 1})['San']
    przydzial = GiftAssignment(campaign_id=c.id, user_id=user.id, order_item_id=item.id,
                               pool_id=c.pools[0].id, card_type_id=typ.id, round_no=1)
    db.session.add(przydzial)
    db.session.commit()
    return przydzial
