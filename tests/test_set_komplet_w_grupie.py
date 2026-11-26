"""Produkt-komplet (OT8) w tej samej grupie wariantów co członkowie.

26.11.2026, set „Ateez GH6 - makestar 3.0 (pob only)": grupa wariantów setu
zawierała 8 członków i OT8, czyli set_product_id sekcji. Macierz liczyła OT8 jak
dziewiątego członka. Pokazywała 2/5 kompletnych setów, bo OT8 kupiono 2 razy,
choć wszyscy członkowie mieli co najmniej 3 sztuki.
"""
import pytest


@pytest.fixture
def set_z_ot8_w_grupie(db, make_user, make_product):
    from modules.offers.models import OfferPage, OfferSection, OfferSetItem
    from modules.products.models import VariantGroup

    autor = make_user(role='admin', email='autor-ot8@example.com')
    czlonkowie = [make_product(name=f'GH6 - {imie}', sale_price=50)
                  for imie in ('Hongjoong', 'Seonghwa', 'Jongho')]
    ot8 = make_product(name='GH6 - OT8', sale_price=380)

    grupa = VariantGroup(name='GH6 - Makestar 3.0')
    db.session.add(grupa)
    db.session.flush()
    for p in czlonkowie + [ot8]:
        grupa.products.append(p)

    page = OfferPage(name='GH6', token=OfferPage.generate_token(), status='active',
                     page_type='exclusive', created_by=autor.id)
    db.session.add(page)
    db.session.flush()
    sekcja = OfferSection(offer_page_id=page.id, section_type='set', sort_order=0,
                          set_name='Ateez GH6 - makestar 3.0', set_product_id=ot8.id,
                          set_max_sets=5)
    db.session.add(sekcja)
    db.session.flush()
    db.session.add(OfferSetItem(section_id=sekcja.id, variant_group_id=grupa.id,
                                quantity_per_set=1, sort_order=0))
    db.session.commit()
    return page, sekcja, czlonkowie, ot8


def test_karty_setu_nie_zawieraja_kompletu(set_z_ot8_w_grupie):
    _, sekcja, czlonkowie, ot8 = set_z_ot8_w_grupie
    ids = {p.id for item in sekcja.set_items for p in item.get_products()}
    assert ids == {p.id for p in czlonkowie}
    assert ot8.id not in ids


def test_kompletne_sety_licza_sie_bez_ot8(db, make_user, make_order, set_z_ot8_w_grupie):
    from modules.orders.models import OrderItem
    from utils.offer_closure import calculate_set_fulfillment

    page, sekcja, czlonkowie, ot8 = set_z_ot8_w_grupie
    klientka = make_user(role='client', email='klientka-ot8@example.com')

    def zamow(produkt):
        o = make_order(klientka, offer_page_id=page.id)
        db.session.add(OrderItem(order_id=o.id, product_id=produkt.id, quantity=1,
                                 price=produkt.sale_price, total=produkt.sale_price))
        db.session.commit()

    for produkt in czlonkowie:          # każdy członek po 3 sztuki
        for _ in range(3):
            zamow(produkt)
    for _ in range(2):                  # 2 komplety OT8
        zamow(ot8)

    wynik = calculate_set_fulfillment(page.id)
    set_wynik = next(s for s in wynik['sets'] if s['section_id'] == sekcja.id)
    assert set_wynik['complete_sets'] == 3
    assert ot8.id not in {p['product_id'] for p in set_wynik['products']}


def test_ot8_nie_jest_rezerwowany_jak_karta_czlonka(set_z_ot8_w_grupie):
    from modules.offers.reservation import get_section_products_map

    page, _, czlonkowie, ot8 = set_z_ot8_w_grupie
    mapa = get_section_products_map(page.id)
    assert ot8.id not in mapa
    for p in czlonkowie:
        assert mapa[p.id] == 5
