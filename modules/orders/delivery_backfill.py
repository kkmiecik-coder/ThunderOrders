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
    from modules.admin.models import ActivityLog
    from modules.orders.models import OrderShipment, ShippingRequestOrder

    wynik = {'z_logu': 0, 'z_przesylek': 0, 'z_updated_at': 0}
    kandydaci = _kandydaci()
    if not kandydaci:
        return wynik

    for sr in kandydaci:
        wpis = (
            ActivityLog.query
            .filter_by(action='shipping_request_shipped',
                       entity_type='shipping_request', entity_id=sr.id)
            .order_by(ActivityLog.created_at.asc())
            .first()
        )
        if wpis and wpis.created_at:
            sr.shipped_at = wpis.created_at
            wynik['z_logu'] += 1
            continue

        przesylka = (
            db.session.query(OrderShipment)
            .join(ShippingRequestOrder,
                  ShippingRequestOrder.order_id == OrderShipment.order_id)
            .filter(ShippingRequestOrder.shipping_request_id == sr.id)
            .order_by(OrderShipment.created_at.asc())
            .first()
        )
        if przesylka and przesylka.created_at:
            sr.shipped_at = przesylka.created_at
            wynik['z_przesylek'] += 1
            continue

        if sr.updated_at:
            sr.shipped_at = sr.updated_at
            wynik['z_updated_at'] += 1

    if dry_run:
        db.session.flush()
    else:
        db.session.commit()
    return wynik
