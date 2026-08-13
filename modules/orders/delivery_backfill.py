"""Odtworzenie shipped_at dla zleceń wysłanych przed wdrożeniem potwierdzeń dostawy.

Kolumna shipped_at powstała razem z tym mechanizmem, więc cała historia ma ją pustą.
Bez uzupełnienia automat nigdy nie zobaczyłby zaległości — a to właśnie ona jest
problemem opisanym w zadaniu.

Napisane w ORM, nie w surowym SQL, z dwóch powodów: działa tak samo na MariaDB i na
SQLite (czyli da się to przetestować), a wołane jest z komendy cron, nie z migracji —
dzięki czemu samo się naprawia, gdyby jakieś zlecenie kiedykolwiek trafiło do statusu
'wyslane' bez daty.

Funkcja jest idempotentna: dotyka wyłącznie wierszy z shipped_at IS NULL.
"""
from extensions import db

# Statusy, dla których data wysyłki musi istnieć.
STATUSY_PO_WYSYLCE = ('wyslane', 'dostarczone')


def _kandydaci():
    from modules.orders.models import ShippingRequest
    return (
        ShippingRequest.query
        .filter(ShippingRequest.status.in_(STATUSY_PO_WYSYLCE))
        .filter(ShippingRequest.shipped_at.is_(None))
        .all()
    )


def odtworz_shipped_at(dry_run=False):
    """Uzupełnia shipped_at kaskadą po wiarygodności źródeł.

    1. Najstarszy wpis w activity_log z action='shipping_request_shipped' — to zapisuje
       ship_shipping_request(), więc jest to ślad faktycznej akcji wysyłki.
    2. Najstarszy OrderShipment.created_at wśród zamówień zlecenia — istnieje tylko
       wtedy, gdy podano numer przesyłki.
    3. updated_at zlecenia — ostatnia deska ratunku, data przybliżona.

    Args:
        dry_run (bool): True — policz i przypisz shipped_at tak samo jak normalnie,
            ale zamiast db.session.commit() zrób db.session.flush(). Flush zapisuje
            zmiany W OBRĘBIE bieżącej transakcji (kolejne zapytania w tym samym
            przebiegu je zobaczą — np. filtr shipped_at IS NOT NULL w cronie), ale
            nic nie trafia trwale do bazy — to wywołujący (cron w trybie --dry-run)
            odpowiada za późniejszy db.session.rollback(). Bez tego --dry-run nigdy
            nie pokazałby zaległości sprzed wdrożenia, bo cała ta historia ma
            shipped_at puste z definicji, a obie fazy crona wymagają, żeby było
            ustawione.

    Returns:
        dict: liczba zleceń uzupełnionych z każdego źródła.
    """
    from sqlalchemy import func

    from modules.admin.models import ActivityLog
    from modules.orders.models import OrderShipment, ShippingRequestOrder

    wynik = {'z_logu': 0, 'z_przesylek': 0, 'z_updated_at': 0}
    kandydaci = _kandydaci()
    if not kandydaci:
        return wynik

    ids = [sr.id for sr in kandydaci]

    # Krok 1 kaskady, dla WSZYSTKICH kandydatów naraz: MIN(created_at) per
    # entity_id daje dokładnie ten sam wybór co .order_by(...).first() w pętli
    # (najstarszy wpis), ale jednym zapytaniem zamiast jednego na zlecenie —
    # przy dużej historii (jednorazowy przebieg po wdrożeniu) to różnica między
    # dwoma zapytaniami a 2*N.
    logi = dict(
        db.session.query(ActivityLog.entity_id, func.min(ActivityLog.created_at))
        .filter(ActivityLog.action == 'shipping_request_shipped')
        .filter(ActivityLog.entity_type == 'shipping_request')
        .filter(ActivityLog.entity_id.in_(ids))
        .group_by(ActivityLog.entity_id)
        .all()
    )

    # Krok 2 kaskady: tylko dla kandydatów bez wpisu w logu — log ma pierwszeństwo,
    # więc nie ma sensu liczyć przesyłek dla tych, którzy i tak go mają.
    brak_logu = [sr_id for sr_id in ids if sr_id not in logi]
    przesylki = {}
    if brak_logu:
        przesylki = dict(
            db.session.query(
                ShippingRequestOrder.shipping_request_id,
                func.min(OrderShipment.created_at),
            )
            .join(OrderShipment, ShippingRequestOrder.order_id == OrderShipment.order_id)
            # created_at jest nullable na OrderShipment — bez tego filtra grupa
            # złożona WYŁĄCZNIE z wierszy o created_at=NULL dałaby MIN()=NULL i
            # nadpisałaby shipped_at pustą wartością zamiast zejść do updated_at,
            # tak jak robił to `if przesylka and przesylka.created_at` w wersji
            # per-wiersz.
            .filter(OrderShipment.created_at.isnot(None))
            .filter(ShippingRequestOrder.shipping_request_id.in_(brak_logu))
            .group_by(ShippingRequestOrder.shipping_request_id)
            .all()
        )

    for sr in kandydaci:
        if sr.id in logi:
            sr.shipped_at = logi[sr.id]
            wynik['z_logu'] += 1
        elif sr.id in przesylki:
            sr.shipped_at = przesylki[sr.id]
            wynik['z_przesylek'] += 1
        elif sr.updated_at:
            sr.shipped_at = sr.updated_at
            wynik['z_updated_at'] += 1

    if dry_run:
        db.session.flush()
    else:
        db.session.commit()
    return wynik
