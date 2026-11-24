"""Edytor strony sprzedaży: pola wyboru produktu mają wyszukiwarkę.

Przy dużej liczbie produktów zwykła rozwijana lista wymagała długiego
przewijania. Pola „Produkt" (sekcja produktu), produkt w secie i wymagany
produkt w bonusie korzystają teraz z komponentu searchable-select:
klik w pole -> okienko „Szukaj po nazwie lub SKU...".
"""
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def _admin(make_user):
    return make_user(role='admin', email='admin-szukaj@example.com', profile_completed=True)


def _typ(db, slug, name):
    from modules.products.models import ProductType
    pt = ProductType.query.filter_by(slug=slug).first()
    if not pt:
        pt = ProductType(name=name, slug=slug)
        db.session.add(pt)
        db.session.commit()
    return pt


def _strona_z_sekcjami(db, admin_id, page_type, produkt):
    from modules.offers.models import (
        OfferPage, OfferSection, OfferSetItem, OfferSetBonus, OfferBonusRequiredProduct,
    )
    page = OfferPage(name='Drop', token=OfferPage.generate_token(), status='draft',
                     page_type=page_type, created_by=admin_id)
    db.session.add(page)
    db.session.flush()

    sekcja_produkt = OfferSection(offer_page_id=page.id, section_type='product',
                                  sort_order=1, product_id=produkt.id)
    sekcja_set = OfferSection(offer_page_id=page.id, section_type='set',
                              sort_order=2, set_name='Komplet')
    sekcja_bonus = OfferSection(offer_page_id=page.id, section_type='bonus', sort_order=3)
    db.session.add_all([sekcja_produkt, sekcja_set, sekcja_bonus])
    db.session.flush()

    db.session.add(OfferSetItem(section_id=sekcja_set.id, product_id=produkt.id, sort_order=1))
    bonus = OfferSetBonus(section_id=sekcja_bonus.id, trigger_type='buy_products')
    db.session.add(bonus)
    db.session.flush()
    db.session.add(OfferBonusRequiredProduct(bonus_id=bonus.id, product_id=produkt.id))
    db.session.commit()
    return page


def _select_tag(html, klasa):
    """Zwraca otwierające tagi <select> z daną klasą."""
    return re.findall(r'<select class="form-select %s[^"]*"[^>]*>' % klasa, html)


@pytest.mark.parametrize('page_type,slug,typ_nazwa', [
    ('preorder', 'pre-order', 'Pre-order'),
    ('exclusive', 'exclusive', 'Exclusive'),
])
def test_pola_produktu_maja_wyszukiwarke(db, client, make_user, login, make_product,
                                         page_type, slug, typ_nazwa):
    admin = _admin(make_user)
    login(admin)
    pt = _typ(db, slug, typ_nazwa)
    produkt = make_product(name='BTS Album Ver. A', sku='BTS-ALB-A', product_type_id=pt.id)
    page = _strona_z_sekcjami(db, admin.id, page_type, produkt)

    resp = client.get(f'/admin/offers/{page.id}/edit')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    for klasa in ('product-select', 'set-item-product', 'bonus-req-product'):
        tagi = _select_tag(html, klasa)
        assert tagi, f'brak pola {klasa} na stronie'
        for tag in tagi:
            assert 'searchable-select' in tag, f'{klasa} bez wyszukiwarki: {tag}'
            assert 'data-search-placeholder="Szukaj po nazwie lub SKU..."' in tag

    # Każde z tych pól siedzi w wrapperze z klikalnym „wyświetlaczem"
    for klasa in ('product-select', 'set-item-product', 'bonus-req-product'):
        wzorzec = (r'<div class="custom-select-wrapper">\s*<select class="form-select %s searchable-select'
                   r'.*?</select>\s*<div class="custom-select-display">' % klasa)
        assert re.search(wzorzec, html, re.S), f'{klasa} nie jest opakowany w custom-select-wrapper'

    # SKU jest dostępne do wyszukiwania także tam, gdzie nie ma go w nazwie opcji
    assert f'value="{produkt.id}" data-sku="BTS-ALB-A"' in html

    # Skrypt komponentu jest ładowany na stronie
    assert 'js/components/searchable-select.js' in html
    assert 'css/components/searchable-select.css' in html


def test_dynamicznie_dodawane_pola_produktu_maja_wyszukiwarke():
    """Nowe sekcje / produkty w secie / wymagane produkty dodawane w przeglądarce
    (offer-builder.js) też muszą dostać wyszukiwarkę."""
    js = (ROOT / 'static/js/pages/admin/offer-builder.js').read_text(encoding='utf-8')
    for klasa in ('product-select', 'set-item-product', 'bonus-req-product'):
        tagi = re.findall(r'<select class="form-select %s\b[^"]*"' % klasa, js)
        assert tagi, f'brak szablonu pola {klasa} w offer-builder.js'
        for tag in tagi:
            assert 'searchable-select' in tag, f'{klasa} w JS bez wyszukiwarki'


def test_komponent_szuka_po_sku_i_bez_polskich_znakow():
    js = (ROOT / 'static/js/components/searchable-select.js').read_text(encoding='utf-8')
    # szukanie po SKU z data-sku
    assert 'opt.dataset.sku' in js
    # placeholder z atrybutu selecta
    assert 'dataset.searchPlaceholder' in js
    # normalizacja polskich znaków
    assert "replace(/ł/g, 'l')" in js
    # wyłączone opcje (produkt użyty w innej sekcji) nie trafiają na listę
    assert 'opt.disabled' in js
