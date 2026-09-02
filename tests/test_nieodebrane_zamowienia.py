"""Testy listy nieodebranych zamówień (projekt 2026-09-02).

„Nieodebrane" = zamówienie w statusie pozwalającym zamówić wysyłkę, którego klient
nie wrzucił do żadnego zlecenia WYS/. Ta sama definicja, którą widzi klient u siebie —
testy pilnują, żeby oba widoki nie zaczęły pokazywać czegoś innego.
"""
import pytest


@pytest.fixture
def zamowienie_gotowe(db, make_user, make_order):
    """Zamówienie w statusie 'dostarczone_gom', bez zlecenia wysyłki."""
    def _make(user=None, **kwargs):
        u = user or make_user()
        return make_order(u, status='dostarczone_gom', **kwargs)
    return _make


def test_gotowe_bez_zlecenia_jest_nieodebrane(app, db, make_user, zamowienie_gotowe):
    from modules.client.shipping_service import unclaimed_orders_query

    o = zamowienie_gotowe()

    assert [z.id for z in unclaimed_orders_query().all()] == [o.id]


def test_zamowienie_w_zleceniu_znika_z_listy(app, db, make_user, zamowienie_gotowe):
    from modules.client.shipping_service import unclaimed_orders_query
    from modules.orders.models import ShippingRequest, ShippingRequestOrder

    o = zamowienie_gotowe()
    zlecenie = ShippingRequest(request_number='WYS/1', user_id=o.user_id)
    db.session.add(zlecenie)
    db.session.commit()
    db.session.add(ShippingRequestOrder(shipping_request_id=zlecenie.id, order_id=o.id))
    db.session.commit()

    assert unclaimed_orders_query().all() == []


def test_anulowane_nie_trafia_na_liste(app, db, make_user, make_order):
    from modules.client.shipping_service import unclaimed_orders_query

    make_order(make_user(), status='anulowane')

    assert unclaimed_orders_query().all() == []


def test_zmiana_ustawienia_statusow_przestawia_liste(app, db, make_user, make_order):
    """Lista czyta Settings, nie zaszytą stałą."""
    from modules.auth.models import Settings
    from modules.client.shipping_service import unclaimed_orders_query

    o = make_order(make_user(), status='spakowane')
    assert unclaimed_orders_query().all() == []

    db.session.add(Settings(key='shipping_request_allowed_statuses',
                            value='["spakowane"]'))
    db.session.commit()

    assert [z.id for z in unclaimed_orders_query().all()] == [o.id]


def test_parytet_ze_strefa_klienta(app, db, make_user, zamowienie_gotowe):
    """Admin i klient widzą ten sam zbiór zamówień tego klienta."""
    from modules.client.shipping_service import (
        get_available_orders, unclaimed_orders_query,
    )

    u = make_user()
    zamowienie_gotowe(user=u)
    zamowienie_gotowe(user=u)
    zamowienie_gotowe()  # inny klient — nie może wejść do porównania

    admin = {z.id for z in unclaimed_orders_query().filter_by(user_id=u.id).all()}
    klient = {z.id for z in get_available_orders(u.id)}

    assert admin == klient


# ============================================
# Stemplowanie daty zmiany statusu
# ============================================

def test_utworzenie_zamowienia_stempluje_date(app, db, make_user, make_order):
    """Nowe zamówienie też wchodzi w status — stempel powstaje od razu."""
    o = make_order(make_user(), status='nowe')

    assert o.status_changed_at is not None


def test_zmiana_statusu_przesuwa_date(app, db, make_user, make_order):
    """Listener działa niezależnie od tego, która trasa zmienia status."""
    from datetime import timedelta

    o = make_order(make_user(), status='nowe')
    o.status_changed_at = o.status_changed_at - timedelta(days=30)
    db.session.commit()
    stary_stempel = o.status_changed_at

    o.status = 'dostarczone_gom'
    db.session.commit()

    assert o.status_changed_at > stary_stempel


def test_edycja_innego_pola_nie_rusza_daty(app, db, make_user, make_order):
    """Notatka dopisana do zamówienia nie może „odmłodzić" zaległości."""
    o = make_order(make_user(), status='nowe')
    o.status = 'dostarczone_gom'
    db.session.commit()
    stempel = o.status_changed_at

    o.admin_notes = 'klient prosił o wstrzymanie'
    db.session.commit()

    assert o.status_changed_at == stempel


def test_przypisanie_tego_samego_statusu_nie_rusza_daty(app, db, make_user, make_order):
    o = make_order(make_user(), status='dostarczone_gom')
    o.status = 'dostarczone_gom'
    db.session.commit()
    stempel = o.status_changed_at

    o.status = 'dostarczone_gom'
    db.session.commit()

    assert o.status_changed_at == stempel
