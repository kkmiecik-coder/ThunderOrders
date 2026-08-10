"""Strażnik egzekwowania kluczy obcych w testowej bazie SQLite.

Testy chodzą na SQLite, produkcja na MariaDB. SQLite domyślnie klucze obce PARSUJE,
ale ich NIE sprawdza — bez `PRAGMA foreign_keys=ON` (conftest) kasowanie wiersza,
na który wskazuje FK bez `ondelete`, przechodzi w testach bez śladu i wybucha dopiero
na produkcji. Te dwa testy pilnują, żeby ta kontrola nie zniknęła po cichu razem z
konfiguracją silnika czy poolem.
"""
import pytest


def test_pragma_kluczy_obcych_jest_wlaczona(db):
    """Sama pragma — najtańsza możliwa asercja, że mechanizm w ogóle działa."""
    from sqlalchemy import text
    assert db.session.execute(text('PRAGMA foreign_keys')).scalar() == 1


def test_kasowanie_zlecenia_trzymanego_przez_sesje_wms_wybucha(db, make_user):
    """Dokładnie ta klasa błędu, dla której włączamy kontrolę.

    `wms_session_shipping_requests.shipping_request_id → shipping_requests.id` nie ma
    `ondelete` (migracja `45101b9ef1c7`), więc na MariaDB skasowanie zlecenia z wciąż
    wiszącym wierszem junction kończy się IntegrityError. Kod produkcyjny sprząta ten
    wiersz przed `delete()` (`admin_delete_shipping_request`,
    `_rozwiaz_konsolidacje_bez_walidacji`) — ten test dowodzi, że gdyby ktoś to
    sprzątanie usunął, testy o tym powiedzą, zamiast milczeć aż do wdrożenia.
    """
    from sqlalchemy.exc import IntegrityError
    from modules.orders.models import ShippingRequest
    from modules.orders.wms_models import WmsSession, WmsSessionShippingRequest

    magazynier = make_user(role='admin')
    sr = ShippingRequest(request_number=ShippingRequest.generate_request_number())
    db.session.add(sr)
    db.session.flush()
    sesja = WmsSession(session_token='tok-fk', user_id=magazynier.id, status='completed')
    db.session.add(sesja)
    db.session.flush()
    db.session.add(WmsSessionShippingRequest(session_id=sesja.id, shipping_request_id=sr.id))
    db.session.commit()

    db.session.delete(sr)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
