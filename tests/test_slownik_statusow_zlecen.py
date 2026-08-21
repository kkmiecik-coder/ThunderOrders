"""Twardnienie słownika statusów zleceń (P5 z audytu).

Słownik jest w pełni edytowalny z panelu ustawień, a pipeline opiera się na
zahardkodowanych slugach (`spakowane`, `oplacone`, `wyslane`, `dostarczone`) —
i do tej pory żaden test nie pilnował tych endpointów.

Dwie realne dziury:

1. `is_initial` bez unikalności. `get_initial_shipping_status` bierze
   `filter_by(is_initial=True).first()` BEZ `order_by`, więc dodanie drugiego
   statusu początkowego czyni status nowych zleceń niedeterministycznym —
   zależnym od kolejności zwracanej przez bazę.

2. DELETE ze słabym strażnikiem: sprawdza tylko BIEŻĄCE użycie (`count()`),
   nie referencje w kodzie. Status chwilowo pusty, ale zahardkodowany, dawał
   się skasować — a `shipping_requests.status` to FK na
   `shipping_request_statuses.slug`, więc najbliższe automatyczne przejście
   padłoby na IntegrityError.
"""

import pytest


def _seed(db):
    from modules.orders.models import ShippingRequestStatus
    for i, (slug, name) in enumerate([
        ('czeka_na_wycene', 'Czeka na wycenę'),
        ('czeka_na_oplacenie', 'Czeka na opłacenie'),
        ('oplacone', 'Opłacone'),
        ('spakowane', 'Spakowane'),
        ('wyslane', 'Wysłane'),
        ('dostarczone', 'Dostarczone'),
    ]):
        if not ShippingRequestStatus.query.filter_by(slug=slug).first():
            db.session.add(ShippingRequestStatus(
                slug=slug, name=name, sort_order=i, is_active=True,
                is_initial=(slug == 'czeka_na_wycene')))
    db.session.commit()


def _admin(make_user):
    return make_user(role='admin', email='admin-slownik@example.com',
                     profile_completed=True)


# ---------------------------------------------------------------------------
# Statusy używane przez pipeline są nietykalne
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('slug', ['czeka_na_wycene', 'czeka_na_oplacenie',
                                  'oplacone', 'spakowane', 'wyslane', 'dostarczone'])
def test_nie_mozna_skasowac_statusu_uzywanego_w_kodzie(
        db, client, login, make_user, slug):
    """Nawet gdy żadne zlecenie akurat go nie ma — kod go zna po slugu."""
    from modules.orders.models import ShippingRequestStatus

    _seed(db)
    st = ShippingRequestStatus.query.filter_by(slug=slug).first()
    login(_admin(make_user))

    r = client.delete(f'/admin/orders/shipping-request-statuses/{st.id}')

    assert r.status_code == 400, r.get_json()
    assert ShippingRequestStatus.query.filter_by(slug=slug).first() is not None


@pytest.mark.parametrize('slug', ['spakowane', 'wyslane', 'oplacone'])
def test_nie_mozna_dezaktywowac_statusu_uzywanego_w_kodzie(
        db, client, login, make_user, slug):
    """Dezaktywacja wyłącza status z automatów tak samo skutecznie jak DELETE —
    `_check_sr_auto_oplacone` wymaga `is_active=True` i po cichu rezygnuje."""
    from modules.orders.models import ShippingRequestStatus

    _seed(db)
    st = ShippingRequestStatus.query.filter_by(slug=slug).first()
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-request-statuses/{st.id}',
                   json={'name': st.name, 'is_active': False})

    assert r.status_code == 400, r.get_json()
    db.session.expire_all()
    assert st.is_active is True


def test_mozna_skasowac_wlasny_nieuzywany_status(db, client, login, make_user):
    """Regresja: statusy dodane przez admina nadal da się usunąć."""
    from modules.orders.models import ShippingRequestStatus

    _seed(db)
    st = ShippingRequestStatus(
        slug='moj_wlasny_etap', name='Mój etap', sort_order=99, is_active=True)
    db.session.add(st)
    db.session.commit()
    st_id = st.id
    login(_admin(make_user))

    r = client.delete(f'/admin/orders/shipping-request-statuses/{st_id}')

    assert r.status_code == 200, r.get_json()
    assert db.session.get(ShippingRequestStatus, st_id) is None


# ---------------------------------------------------------------------------
# Status początkowy jest jeden
# ---------------------------------------------------------------------------

def test_ustawienie_poczatkowego_zdejmuje_flage_z_poprzedniego(
        db, client, login, make_user):
    """Bez unikalności `get_initial_shipping_status` bierze `.first()` bez
    `order_by` — status nowych zleceń stawał się niedeterministyczny."""
    from modules.orders.models import ShippingRequestStatus

    _seed(db)
    nowy = ShippingRequestStatus.query.filter_by(slug='oplacone').first()
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-request-statuses/{nowy.id}',
                   json={'name': nowy.name, 'is_initial': True})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    poczatkowe = ShippingRequestStatus.query.filter_by(is_initial=True).all()
    assert len(poczatkowe) == 1, (
        f'Statusów początkowych musi być dokładnie jeden; jest {len(poczatkowe)}'
    )
    assert poczatkowe[0].slug == 'oplacone'


def test_status_poczatkowy_jest_deterministyczny(db, make_user):
    """Regresja na samą funkcję czytającą."""
    from modules.client.cart_service import get_initial_shipping_status

    _seed(db)
    assert get_initial_shipping_status() == 'czeka_na_wycene'
