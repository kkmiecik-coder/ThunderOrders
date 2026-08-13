"""OrderShipment.courier_display_name — dług: druga kopia mapy nazw kurierów
(dług-potwierdzenie-dostawy, G6-model-frontend, pozycja 1).

Property miała własny literał zamiast czytać z kanonicznej `wms_utils.COURIER_NAMES`,
tak jak już robi to `ShippingRequest.courier_display_name`. Literał nie miał klucza
'pocztex', mimo że ten kurier jest wybieralny w interfejsie — ten sam rodzaj błędu,
co w `test_shipment_sent_notification.py::test_update_sr_pocztex_courier_name_capitalized`.
"""


def _zamowienie_z_przesylka(db, user, make_order, courier, tracking='TRACK1'):
    from modules.orders.models import OrderShipment

    order = make_order(user)
    shipment = OrderShipment(order_id=order.id, tracking_number=tracking, courier=courier)
    db.session.add(shipment)
    db.session.commit()
    return shipment


def test_courier_display_name_czyta_kanoniczna_mape(app, db, make_user, make_order):
    from modules.orders.wms_utils import COURIER_NAMES

    user = make_user()
    for slug, nazwa in COURIER_NAMES.items():
        shipment = _zamowienie_z_przesylka(db, user, make_order, slug, tracking=f'T-{slug}')
        assert shipment.courier_display_name == nazwa


def test_courier_display_name_pocztex_nie_jest_juz_surowym_slugiem(app, db, make_user, make_order):
    """Regres: lokalny literał tutaj nie miał klucza 'pocztex' (w przeciwieństwie
    do wms_utils.COURIER_NAMES), więc dostawy tym kurierem pokazywały surowy slug
    zamiast czytelnej nazwy."""
    user = make_user()
    shipment = _zamowienie_z_przesylka(db, user, make_order, 'pocztex')

    assert shipment.courier_display_name == 'Pocztex'


def test_courier_display_name_nieznany_kurier_zwraca_slug(app, db, make_user, make_order):
    user = make_user()
    shipment = _zamowienie_z_przesylka(db, user, make_order, 'nieznany_kurier')

    assert shipment.courier_display_name == 'nieznany_kurier'
