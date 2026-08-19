"""Testy generowania numerów zamówień (ClickUp 869ekw4p0).

Kontekst: numery Order były nadawane sekwencyjnie (SELECT ostatniego numeru + 1)
bez blokady i bez UNIQUE w bazie -> przy sprzedaży LIVE dwa równoległe zamówienia
dostawały ten sam numer (122 kolizje w bazie od kwietnia 2026).

Nowy kontrakt:
- numer wynika z ID rekordu: {PREFIX}/{id} -> kolizja niemożliwa z definicji,
- bez zer wiodących (EX/1804 zamiast EX/00001804).
"""
from decimal import Decimal


def _order_type(db, slug, name, prefix):
    from modules.orders.models import OrderType
    ot = OrderType.query.filter_by(slug=slug).first()
    if not ot:
        ot = OrderType(slug=slug, name=name, prefix=prefix)
        db.session.add(ot)
        db.session.commit()
    return ot


# ====================
# NORMALIZACJA (migracja historii + wyszukiwanie)
# ====================

def test_normalizacja_obcina_zera_wiodace():
    from modules.orders.utils import normalize_order_number
    assert normalize_order_number('EX/00001804') == 'EX/1804'
    assert normalize_order_number('PO/00000492') == 'PO/492'
    assert normalize_order_number('WYS/000123') == 'WYS/123'


def test_normalizacja_zachowuje_wieloczlonowy_prefiks():
    from modules.orders.utils import normalize_order_number
    assert normalize_order_number('PRX/PL/00001') == 'PRX/PL/1'


def test_normalizacja_nie_gubi_samych_zer():
    """'PO/00000000' nie może zostać pustym numerem."""
    from modules.orders.utils import normalize_order_number
    assert normalize_order_number('PO/00000000') == 'PO/0'


def test_normalizacja_zostawia_numer_bez_zer_bez_zmian():
    from modules.orders.utils import normalize_order_number
    assert normalize_order_number('EX/1804') == 'EX/1804'
    assert normalize_order_number('TMP/abc123') == 'TMP/abc123'


# ====================
# NADAWANIE NUMERU ORDER
# ====================

def test_numer_zamowienia_wynika_z_id_bez_zer(db, make_user):
    from modules.orders.models import Order
    from modules.orders.utils import assign_order_number, order_number_placeholder
    _order_type(db, 'exclusive', 'Exclusive', 'EX')
    user = make_user()

    order = Order(order_number=order_number_placeholder(), order_type='exclusive',
                  user_id=user.id, status='nowe', total_amount=Decimal('0.00'))
    db.session.add(order)
    db.session.flush()
    numer = assign_order_number(order, 'exclusive')
    db.session.commit()

    assert numer == f'EX/{order.id}'
    assert order.order_number == f'EX/{order.id}'


def test_placeholdery_sa_rozne_dla_rownoleglych_zamowien():
    """Placeholder żyje do flushu, ale UNIQUE w bazie działa już przy INSERT."""
    from modules.orders.utils import order_number_placeholder
    placeholdery = {order_number_placeholder() for _ in range(100)}
    assert len(placeholdery) == 100


def test_placeholder_miesci_sie_w_kolumnie():
    """Order.order_number to VARCHAR(20) — dłuższy placeholder wywali INSERT."""
    from modules.orders.utils import order_number_placeholder
    assert len(order_number_placeholder()) <= 20


def test_kolejne_zamowienia_dostaja_rozne_numery(db, make_user):
    """Regresja 869ekw4p0: dwa zamówienia nigdy nie dzielą numeru."""
    from modules.orders.models import Order
    from modules.orders.utils import assign_order_number, order_number_placeholder
    _order_type(db, 'exclusive', 'Exclusive', 'EX')
    user = make_user()

    numery = []
    for _ in range(5):
        o = Order(order_number=order_number_placeholder(), order_type='exclusive',
                  user_id=user.id, status='nowe', total_amount=Decimal('0.00'))
        db.session.add(o)
        db.session.flush()
        numery.append(assign_order_number(o, 'exclusive'))
        db.session.commit()

    assert len(set(numery)) == 5


def test_numer_omija_kolizje_z_numerem_historycznym(db, make_user):
    """Numer historyczny może przypadkiem równać się {PREFIX}/{id} nowego rekordu."""
    from modules.orders.models import Order
    from modules.orders.utils import assign_order_number, order_number_placeholder
    _order_type(db, 'exclusive', 'Exclusive', 'EX')
    user = make_user()

    nowy = Order(order_number=order_number_placeholder(), order_type='exclusive',
                 user_id=user.id, status='nowe', total_amount=Decimal('0.00'))
    db.session.add(nowy)
    db.session.flush()
    # Historyczne zamówienie zajmuje numer, który przypadłby nowemu
    kolizja = Order(order_number=f'EX/{nowy.id}', order_type='exclusive',
                    user_id=user.id, status='nowe', total_amount=Decimal('0.00'))
    db.session.add(kolizja)
    db.session.flush()

    numer = assign_order_number(nowy, 'exclusive')
    db.session.commit()

    assert numer != f'EX/{nowy.id}'
    assert numer.startswith('EX/')
    assert Order.query.filter_by(order_number=numer).count() == 1


def test_nieznany_typ_zamowienia_konczy_sie_bledem(db, make_user):
    from modules.orders.models import Order
    from modules.orders.utils import assign_order_number, order_number_placeholder
    import pytest
    user = make_user()
    o = Order(order_number=order_number_placeholder(), order_type='on_hand',
              user_id=user.id, status='nowe', total_amount=Decimal('0.00'))
    db.session.add(o)
    db.session.flush()

    with pytest.raises(ValueError):
        assign_order_number(o, 'nie_ma_takiego_typu')


# ====================
# ZLECENIA WYSYŁKI (WYS) — sekwencja, ale odporna na zajęty numer
# ====================

def test_numer_wysylki_bez_zer_wiodacych(db):
    from modules.orders.models import ShippingRequest
    assert ShippingRequest.generate_request_number() == 'WYS/1'


def test_numer_wysylki_czyta_stary_format_z_zerami(db, make_user):
    from modules.orders.models import ShippingRequest
    user = make_user()
    db.session.add(ShippingRequest(request_number='WYS/000123', user_id=user.id))
    db.session.commit()

    assert ShippingRequest.generate_request_number() == 'WYS/124'


def test_numer_wysylki_pomija_numer_juz_zajety(db, make_user):
    """Ostatni rekord nie zawsze ma najwyższy numer (konsolidacje, ręczne edycje)."""
    from modules.orders.models import ShippingRequest
    user = make_user()
    db.session.add(ShippingRequest(request_number='WYS/9', user_id=user.id))
    db.session.commit()
    db.session.add(ShippingRequest(request_number='WYS/5', user_id=user.id))
    db.session.commit()

    numer = ShippingRequest.generate_request_number()

    assert numer not in ('WYS/5', 'WYS/9')
    assert ShippingRequest.query.filter_by(request_number=numer).first() is None


# ====================
# ZLECENIA PROXY / POLSKA (admin) — sekwencja, ale bez zer
# ====================

def test_numer_proxy_bez_zer_wiodacych(db):
    from modules.products.routes import generate_proxy_order_number
    assert generate_proxy_order_number() == 'PRX/1'


def test_kolejny_numer_proxy_kontynuuje_sekwencje(db):
    from modules.products.models import ProxyOrder
    from modules.products.routes import generate_proxy_order_number
    db.session.add(ProxyOrder(order_number='PRX/41', order_type='proxy'))
    db.session.commit()

    assert generate_proxy_order_number() == 'PRX/42'


def test_numer_proxy_czyta_stary_format_z_zerami(db):
    """Po wdrożeniu w bazie mogą jeszcze siedzieć numery sprzed migracji."""
    from modules.products.models import ProxyOrder
    from modules.products.routes import generate_proxy_order_number
    db.session.add(ProxyOrder(order_number='PRX/00041', order_type='proxy'))
    db.session.commit()

    assert generate_proxy_order_number() == 'PRX/42'


def test_numer_poland_nie_myli_sie_z_prx_pl(db):
    from modules.products.models import ProxyOrder, PolandOrder
    from modules.products.routes import generate_poland_order_number
    proxy = ProxyOrder(order_number='PRX/1', order_type='proxy')
    db.session.add(proxy)
    db.session.commit()
    db.session.add(PolandOrder(order_number='PRX/PL/7', proxy_order_id=proxy.id,
                               status='zamowione'))
    db.session.commit()

    assert generate_poland_order_number() == 'PL/1'


# ====================
# SORTOWANIE PO NUMERZE
# ====================

def _zamowienie(db, user, numer):
    from modules.orders.models import Order
    o = Order(order_number=numer, order_type='exclusive', user_id=user.id,
              status='nowe', total_amount=Decimal('0.00'))
    db.session.add(o)
    db.session.commit()
    return o


def test_sortowanie_po_numerze_nie_jest_leksykograficzne(db, make_user):
    """Bez zer wiodących 'EX/999' > 'EX/1804' tekstowo — kolejność musi iść za sekwencją."""
    from modules.orders.models import Order
    from modules.orders.utils import apply_order_sorting
    user = make_user()
    _zamowienie(db, user, 'EX/999')
    _zamowienie(db, user, 'EX/1804')

    numery = [o.order_number for o in
              apply_order_sorting(Order.query, 'order_number', 'desc').all()]

    assert numery == ['EX/1804', 'EX/999']


def test_sortowanie_rosnace_po_numerze(db, make_user):
    from modules.orders.models import Order
    from modules.orders.utils import apply_order_sorting
    user = make_user()
    _zamowienie(db, user, 'EX/999')
    _zamowienie(db, user, 'EX/1804')

    numery = [o.order_number for o in
              apply_order_sorting(Order.query, 'order_number', 'asc').all()]

    assert numery == ['EX/999', 'EX/1804']


def test_sortowanie_grupuje_po_typie_zamowienia(db, make_user):
    """Numery różnych typów nie mieszają się ze sobą na liście."""
    from modules.orders.models import Order
    from modules.orders.utils import apply_order_sorting
    user = make_user()
    _zamowienie(db, user, 'EX/5')
    po = Order(order_number='PO/7', order_type='pre_order', user_id=user.id,
               status='nowe', total_amount=Decimal('0.00'))
    db.session.add(po)
    db.session.commit()
    _zamowienie(db, user, 'EX/6')

    typy = [o.order_type for o in
            apply_order_sorting(Order.query, 'order_number', 'asc').all()]

    assert typy == ['exclusive', 'exclusive', 'pre_order']


# ====================
# PLAN MIGRACJI HISTORII (obcięcie zer + rozbicie duplikatów)
# ====================

def test_plan_obcina_zera_w_calej_historii():
    from modules.orders.utils import plan_number_normalization
    plan = plan_number_normalization([(1, 'EX/00000045'), (2, 'PO/00000492')])
    assert plan == {1: 'EX/45', 2: 'PO/492'}


def test_plan_pomija_numery_juz_poprawne():
    from modules.orders.utils import plan_number_normalization
    assert plan_number_normalization([(1, 'EX/45')]) == {}


def test_plan_zostawia_numer_najstarszemu_z_duplikatow():
    """Rekord z najniższym ID trzyma numer — to on trafił do maili jako pierwszy."""
    from modules.orders.utils import plan_number_normalization
    plan = plan_number_normalization([(2891, 'EX/00001804'), (2892, 'EX/00001804')])
    assert plan[2891] == 'EX/1804'
    assert plan[2892] == 'EX/1805'


def test_plan_rozbija_duplikat_trojki():
    from modules.orders.utils import plan_number_normalization
    plan = plan_number_normalization([
        (2894, 'EX/00001806'), (2895, 'EX/00001806'), (2896, 'EX/00001806'),
    ])
    assert plan[2894] == 'EX/1806'
    assert len({plan[2894], plan[2895], plan[2896]}) == 3


def test_plan_nie_wciska_duplikatu_w_luke_historii():
    """Numer nadany przy naprawie ma iść ZA historią, a nie w jej dziurę
    (dziura = numer po skasowanym zamówieniu) — inaczej zamówienie z lipca
    dostaje numer wyglądający na kwietniowy."""
    from modules.orders.utils import plan_number_normalization
    plan = plan_number_normalization([
        (340, 'EX/00000015'), (341, 'EX/00000015'),   # duplikat
        (900, 'EX/00000016'), (901, 'EX/00000018'),   # EX/17 to luka
    ])
    assert plan[341] == 'EX/19'


def test_plan_nie_nadaje_numeru_zajetego_przez_inny_rekord():
    """Numer zastępczy nie może zabrać numeru rekordowi, który go dziedziczy."""
    from modules.orders.utils import plan_number_normalization
    dane = [(10, 'EX/00000005'), (11, 'EX/00000005'), (12, 'EX/00000011')]
    plan = plan_number_normalization(dane)
    wynikowe = {plan.get(i, n) for i, n in dane}

    assert len(wynikowe) == 3
    assert plan[12] == 'EX/11'
    assert plan[11] == 'EX/12'


def test_plan_numeruje_duplikaty_kolejno_od_konca_serii():
    from modules.orders.utils import plan_number_normalization
    plan = plan_number_normalization([
        (1, 'EX/00000007'), (2, 'EX/00000007'), (3, 'EX/00000007'),
    ])
    assert plan[2] == 'EX/8'
    assert plan[3] == 'EX/9'


def test_plan_traktuje_prefiksy_niezaleznie():
    from modules.orders.utils import plan_number_normalization
    plan = plan_number_normalization([(1, 'EX/00000005'), (2, 'PO/00000005')])
    assert plan == {1: 'EX/5', 2: 'PO/5'}


def test_plan_radzi_sobie_z_kolizja_po_obcieciu_zer():
    """'EX/0005' i 'EX/5' po normalizacji dają ten sam numer."""
    from modules.orders.utils import plan_number_normalization
    plan = plan_number_normalization([(1, 'EX/5'), (2, 'EX/0005')])
    assert 1 not in plan
    assert plan[2] != 'EX/5'
