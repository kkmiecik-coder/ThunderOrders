"""Grupy wariantów produktów — wyszukiwarka i podgląd szczegółów.

Regresja: obie trasy wołały `group.products.all()`, ale relacja `products`
(backref z `variant_groups`) jest zwykłą listą, nie zapytaniem `lazy='dynamic'`.
Na produkcji kończyło się to `AttributeError: 'InstrumentedList' object has no
attribute 'all'` i błędem 500 przy dodawaniu produktu do istniejącej grupy.
"""


def _grupa_z_produktami(db, nazwa, produkty):
    from modules.products.models import VariantGroup

    grupa = VariantGroup(name=nazwa)
    db.session.add(grupa)
    db.session.commit()
    for produkt in produkty:
        produkt.variant_groups.append(grupa)
    db.session.commit()
    return grupa


def test_wyszukiwarka_grup_liczy_produkty(app, client, db, make_user, make_product, login):
    login(make_user(role='admin', email='admin@example.com'))
    _grupa_z_produktami(db, 'Album ATEEZ', [make_product(), make_product()])

    r = client.get('/admin/products/search-variant-groups?q=Album')

    assert r.status_code == 200
    grupy = r.get_json()['groups']
    assert len(grupy) == 1
    assert grupy[0]['name'] == 'Album ATEEZ'
    assert grupy[0]['product_count'] == 2


def test_wyszukiwarka_pomija_grupy_wykluczone(app, client, db, make_user, make_product, login):
    login(make_user(role='admin', email='admin@example.com'))
    zostaje = _grupa_z_produktami(db, 'Album ATEEZ', [make_product()])
    wykluczona = _grupa_z_produktami(db, 'Album TXT', [make_product()])

    r = client.get(f'/admin/products/search-variant-groups?q=Album&exclude_ids={wykluczona.id}')

    assert r.status_code == 200
    zwrocone = [g['id'] for g in r.get_json()['groups']]
    assert zwrocone == [zostaje.id]


def test_szczegoly_grupy_zwracaja_produkty(app, client, db, make_user, make_product, login):
    login(make_user(role='admin', email='admin@example.com'))
    grupa = _grupa_z_produktami(db, 'Album ATEEZ', [make_product(name='Wersja A')])

    r = client.get(f'/admin/products/variant-group/{grupa.id}')

    assert r.status_code == 200
    dane = r.get_json()
    assert dane['success'] is True
    assert [p['name'] for p in dane['group']['products']] == ['Wersja A']


def test_szczegoly_pustej_grupy_nie_wywalaja_sie(app, client, db, make_user, login):
    login(make_user(role='admin', email='admin@example.com'))
    grupa = _grupa_z_produktami(db, 'Grupa pusta', [])

    r = client.get(f'/admin/products/variant-group/{grupa.id}')

    assert r.status_code == 200
    assert r.get_json()['group']['products'] == []
