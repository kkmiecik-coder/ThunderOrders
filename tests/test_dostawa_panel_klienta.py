"""Panel klienta — potwierdzenie odbioru i ocena dostawy."""
from datetime import timedelta


def _zlecenie(db, user, numer, status='wyslane'):
    from modules.orders.models import ShippingRequest, get_local_now
    sr = ShippingRequest(request_number=numer, user_id=user.id, status=status,
                         shipped_at=get_local_now() - timedelta(days=4))
    db.session.add(sr)
    db.session.commit()
    return sr


def test_cudze_zlecenie_zwraca_404(app, db, client, login, make_user):
    wlasciciel = make_user()
    # profile_completed=True: client_bp.before_request przekierowuje na
    # complete-profile każde /client/* dla zalogowanego bez dokończonego profilu —
    # bez tego test nigdy nie dotarłby do sprawdzenia 404 (zob. wzorzec w
    # tests/test_shipping_consolidation_client.py).
    obcy = make_user(profile_completed=True)
    sr = _zlecenie(db, wlasciciel, 'WYS/000400')
    login(obcy)

    assert client.get(f'/client/shipping/requests/{sr.id}/potwierdz').status_code == 404


def test_niezalogowany_trafia_na_logowanie(app, db, client, make_user):
    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000401')

    odp = client.get(f'/client/shipping/requests/{sr.id}/potwierdz')

    assert odp.status_code == 302
    assert '/login' in odp.headers['Location']


def test_get_wlasciciela_pokazuje_strone_potwierdzenia(app, db, client, login, make_user):
    """Ścieżka GET renderuje szablon z kontekstem (sr, moze_potwierdzic, ...) —
    dopisane po recenzji: żaden inny test w tym pliku nie dociera do
    render_template (cudze zlecenie kończy się na 404, niezalogowany na
    przekierowaniu), więc ten kontekst był niepokryty. Asercja treści celowo
    luźna (tylko numer zlecenia) — pełny szablon powstaje w Task 8 i nie ma
    sensu betonować go tym testem."""
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000403')
    login(user)

    odp = client.get(f'/client/shipping/requests/{sr.id}/potwierdz')

    assert odp.status_code == 200
    assert 'WYS/000403' in odp.get_data(as_text=True)


def test_get_dostarczonego_z_ocena_pokazuje_strone(app, db, client, login, make_user):
    """Druga gałąź kontekstu: zlecenie już dostarczone, z wystawioną opinią
    (review nie jest None). Tania dodatkowa asercja, że render_template nie
    wywala się przy niepustym `review`."""
    from modules.orders.models import get_local_now
    from modules.orders.review_models import DeliveryReview

    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000404', status='dostarczone')
    sr.delivered_at = get_local_now() - timedelta(days=1)
    sr.delivered_source = 'klient'
    db.session.add(DeliveryReview(shipping_request_id=sr.id, user_id=user.id,
                                   rating=5, comment='Super'))
    db.session.commit()
    login(user)

    odp = client.get(f'/client/shipping/requests/{sr.id}/potwierdz')

    assert odp.status_code == 200
    assert 'WYS/000404' in odp.get_data(as_text=True)


def test_potwierdzenie_domyka_zlecenie(app, db, client, login, make_user):
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000402')
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/potwierdz',
                      json={'rating': 5, 'comment': 'Szybko i sprawnie'})

    assert odp.status_code == 200
    assert odp.get_json()['success'] is True
    assert sr.status == 'dostarczone'
    assert sr.delivered_source == 'klient'
    assert sr.review.rating == 5


def test_uczestnik_paczki_zbiorczej_nie_moze_potwierdzic(app, db, client, login, make_user):
    user = make_user(profile_completed=True)
    lider = make_user(profile_completed=True)
    zbiorcze = _zlecenie(db, lider, 'WYS/000410')
    zrodlo_lidera = _zlecenie(db, lider, 'WYS/000411')
    zrodlo_uczestnika = _zlecenie(db, user, 'WYS/000412')
    for z in (zrodlo_lidera, zrodlo_uczestnika):
        z.consolidated_into_id = zbiorcze.id
    zbiorcze.lead_source_request_id = zrodlo_lidera.id
    db.session.commit()

    login(user)
    odp = client.post(f'/client/shipping/requests/{zrodlo_uczestnika.id}/potwierdz', json={})

    assert odp.status_code == 403
    assert zbiorcze.status == 'wyslane'


def test_lider_potwierdza_cala_paczke_zbiorcza(app, db, client, login, make_user):
    lider = make_user(profile_completed=True)
    uczestnik = make_user(profile_completed=True)
    zbiorcze = _zlecenie(db, lider, 'WYS/000420')
    zrodlo_lidera = _zlecenie(db, lider, 'WYS/000421')
    zrodlo_uczestnika = _zlecenie(db, uczestnik, 'WYS/000422')
    for z in (zrodlo_lidera, zrodlo_uczestnika):
        z.consolidated_into_id = zbiorcze.id
    zbiorcze.lead_source_request_id = zrodlo_lidera.id
    db.session.commit()

    login(lider)
    odp = client.post(f'/client/shipping/requests/{zrodlo_lidera.id}/potwierdz', json={})

    assert odp.status_code == 200
    assert zbiorcze.status == 'dostarczone'
    assert zrodlo_uczestnika.status == 'dostarczone'


def test_ocena_poza_zakresem_odrzucona(app, db, client, login, make_user):
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000430')
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/potwierdz', json={'rating': 9})

    assert odp.status_code == 400
    assert sr.status == 'wyslane'


def test_druga_ocena_aktualizuje_pierwsza(app, db, client, login, make_user):
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000440')
    login(user)
    client.post(f'/client/shipping/requests/{sr.id}/potwierdz', json={'rating': 3})

    odp = client.post(f'/client/shipping/requests/{sr.id}/ocena',
                      json={'rating': 5, 'comment': 'Jednak super'})

    assert odp.status_code == 200
    from modules.orders.review_models import DeliveryReview
    assert DeliveryReview.query.filter_by(shipping_request_id=sr.id).count() == 1
    assert sr.review.rating == 5


def test_edycja_po_oknie_odrzucona(app, db, client, login, make_user):
    from modules.orders.models import get_local_now

    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000450')
    login(user)
    client.post(f'/client/shipping/requests/{sr.id}/potwierdz', json={'rating': 3})

    sr.review.created_at = get_local_now() - timedelta(days=4)
    db.session.commit()

    odp = client.post(f'/client/shipping/requests/{sr.id}/ocena', json={'rating': 1})

    assert odp.status_code == 409
    assert sr.review.rating == 3


def test_ocena_po_oknie_wystawienia_odrzucona(app, db, client, login, make_user):
    from modules.orders.models import get_local_now

    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000460', status='dostarczone')
    sr.delivered_at = get_local_now() - timedelta(days=31)
    sr.delivered_source = 'auto'
    db.session.commit()
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/ocena', json={'rating': 5})

    assert odp.status_code == 409
    assert sr.review is None


def test_ocena_po_domknieciu_automatem_dziala(app, db, client, login, make_user):
    from modules.orders.models import get_local_now

    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000470', status='dostarczone')
    sr.delivered_at = get_local_now() - timedelta(days=2)
    sr.delivered_source = 'auto'
    db.session.commit()
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/ocena',
                      json={'rating': 4, 'comment': 'Dotarło'})

    assert odp.status_code == 200
    assert sr.review.rating == 4


def test_ocena_niewyslanej_paczki_odrzucona(app, db, client, login, make_user):
    """Recenzja całościowa (I6): `_okno_oceny_otwarte` zwracało True dla każdego
    statusu innego niż 'dostarczone', a endpointy oceny statusu nie sprawdzają wcale —
    dało się więc ocenić paczkę, która nigdy nie wyjechała z magazynu (albo została
    anulowana), i taka ocena wchodziła do średniej w statystykach."""
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000490', status='czeka_na_wycene')
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/ocena', json={'rating': 5})

    assert odp.status_code == 409
    assert sr.review is None


def test_strona_niewyslanej_paczki_nie_pokazuje_gwiazdek(app, db, client, login, make_user):
    """Druga powierzchnia I6: szablon podsuwał gwiazdki tuż pod komunikatem
    „tej paczki nie da się teraz potwierdzić"."""
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000491', status='czeka_na_wycene')
    login(user)

    tresc = client.get(f'/client/shipping/requests/{sr.id}/potwierdz').get_data(as_text=True)

    assert 'deliveryReview' not in tresc
    assert 'WYS/000491' in tresc


def test_ocena_wyslanej_paczki_nadal_dziala(app, db, client, login, make_user):
    """Druga strona I6: 'wyslane' musi zostać ocenialne — klient ocenia razem z
    potwierdzeniem odbioru, więc zawężenie do samego 'dostarczone' zabiłoby
    główną ścieżkę."""
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000492')
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/ocena', json={'rating': 4})

    assert odp.status_code == 200
    assert sr.review.rating == 4


def test_potwierdzenie_juz_dostarczonego_zlecenia_zwraca_409(app, db, client, login, make_user):
    """Poprawka do briefu: POST na /potwierdz musi odrzucić zlecenie, które nie jest
    w statusie 'wyslane', ZANIM cokolwiek zapisze — inaczej klient mógłby POST-em
    domknąć paczkę już dostarczoną (strona GET tylko ukrywa przycisk, to nie jest
    zabezpieczeniem samo w sobie)."""
    from modules.orders.models import get_local_now

    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000480', status='dostarczone')
    sr.delivered_at = get_local_now() - timedelta(days=1)
    sr.delivered_source = 'auto'
    db.session.commit()
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/potwierdz',
                      json={'rating': 5})

    assert odp.status_code == 409
    assert sr.status == 'dostarczone'
    assert sr.delivered_source == 'auto'
