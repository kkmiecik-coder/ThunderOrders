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


def test_wejscie_po_id_paczki_zbiorczej_zwraca_404(app, db, client, login, make_user, make_order):
    """Recenzja całościowa (C1 pkt 3): `_kopiuj_adres` ustawia
    `zbiorcze.user_id = lead.user_id`, więc filtr po właścicielu przepuszczał lidera
    na stronę paczki ZBIORCZEJ — a tam `sr.display_orders` schodzi na `self.orders`,
    czyli zamówienia wszystkich uczestników. To była jedyna droga do pokazania mu
    cudzych numerów, a zapis oceny z tej strony założyłby DRUGI wiersz DeliveryReview
    dla tej samej fizycznej przesyłki (UNIQUE jest per shipping_request_id)."""
    from modules.orders.models import ShippingRequestOrder

    lider = make_user(profile_completed=True)
    uczestnik = make_user(profile_completed=True)
    zbiorcze = _zlecenie(db, lider, 'WYS/000425')
    zrodlo_lidera = _zlecenie(db, lider, 'WYS/000426')
    zrodlo_uczestnika = _zlecenie(db, uczestnik, 'WYS/000427')
    for z in (zrodlo_lidera, zrodlo_uczestnika):
        z.consolidated_into_id = zbiorcze.id
    zbiorcze.lead_source_request_id = zrodlo_lidera.id
    order_uczestnika = make_order(uczestnik, status='wyslane')
    db.session.add(ShippingRequestOrder(
        shipping_request_id=zbiorcze.id, order_id=order_uczestnika.id,
        source_request_id=zrodlo_uczestnika.id))
    db.session.commit()

    login(lider)

    assert client.get(
        f'/client/shipping/requests/{zbiorcze.id}/potwierdz').status_code == 404
    assert client.post(
        f'/client/shipping/requests/{zbiorcze.id}/potwierdz', json={}).status_code == 404
    assert client.post(
        f'/client/shipping/requests/{zbiorcze.id}/ocena',
        json={'rating': 5}).status_code == 404
    # Własne zlecenie źródłowe zostaje dostępne — to na nie prowadzą linki z maili.
    assert client.get(
        f'/client/shipping/requests/{zrodlo_lidera.id}/potwierdz').status_code == 200


def test_lider_paczki_zbiorczej_ma_dokladnie_jedna_opinie(
        app, db, client, login, make_user, maile_synchronicznie):
    """Recenzja całościowa (I2): ocena lidera ląduje na jego zleceniu ŹRÓDŁOWYM, a
    `dostarcz_zlecenie` domyka zlecenie ZBIORCZE i z niego czyta ocenę do maila. Test
    pilnuje obu stron naraz: powstaje DOKŁADNIE jeden wiersz DeliveryReview (drugą
    drogą było wejście po id paczki zbiorczej, dziś 404), a mail „dziękujemy" niesie
    wystawioną przed chwilą ocenę zamiast CTA „Oceń dostawę"."""
    from extensions import mail
    from modules.orders.review_models import DeliveryReview

    lider = make_user(profile_completed=True, email='lider@example.com', first_name='Ola')
    uczestnik = make_user(profile_completed=True, email='druga@example.com')
    zbiorcze = _zlecenie(db, lider, 'WYS/000428')
    zrodlo_lidera = _zlecenie(db, lider, 'WYS/000429')
    zrodlo_uczestnika = _zlecenie(db, uczestnik, 'WYS/000431')
    for z in (zrodlo_lidera, zrodlo_uczestnika):
        z.consolidated_into_id = zbiorcze.id
    zbiorcze.lead_source_request_id = zrodlo_lidera.id
    db.session.commit()

    login(lider)
    with mail.record_messages() as outbox:
        odp = client.post(f'/client/shipping/requests/{zrodlo_lidera.id}/potwierdz',
                          json={'rating': 5, 'comment': 'Wszystko OK'})

    assert odp.status_code == 200
    assert DeliveryReview.query.count() == 1
    assert zrodlo_lidera.review.rating == 5
    assert zbiorcze.review is None
    assert zbiorcze.review_dostawy is zrodlo_lidera.review

    do_lidera = [m for m in outbox if m.recipients == ['lider@example.com']]
    assert len(do_lidera) == 1, 'lider ma dostać dokładnie jeden mail o potwierdzeniu'
    assert 'Twoja ocena dostawy: 5/5' in do_lidera[0].html
    assert 'Wszystko OK' in do_lidera[0].html
    assert 'Oceń dostawę' not in do_lidera[0].html
    # Uczestnik też dostaje swoją wiadomość — wcześniej nie dostawał żadnej.
    assert [m for m in outbox if m.recipients == ['druga@example.com']]


def test_ocena_poza_zakresem_odrzucona(app, db, client, login, make_user):
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000430')
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/potwierdz', json={'rating': 9})

    assert odp.status_code == 400
    assert sr.status == 'wyslane'


def test_ocena_niecalkowita_odrzucona(app, db, client, login, make_user):
    """`int(4.9)` cicho ucinało do 4 zamiast odrzucić ocenę — JSON (fetch/mobile API)
    przysyła rating jako float, więc string-owa ścieżka walidacji (int("4.9") już
    rzuca ValueError) tego nie łapała."""
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000493')
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/ocena', json={'rating': 4.9})

    assert odp.status_code == 400
    assert sr.review is None


def test_ocena_calkowita_jako_float_akceptowana(app, db, client, login, make_user):
    """4.0 to nadal poprawna ocena 4 — odrzucamy tylko ułamek, nie sam typ float."""
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000494')
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/ocena', json={'rating': 4.0})

    assert odp.status_code == 200
    assert sr.review.rating == 4


def test_ocena_nieskonczonosc_odrzucona(app, db, client, login, make_user):
    """`int(float('inf'))` rzuca OverflowError, nie ValueError — a parser JSON-a
    przyjmuje literał `Infinity`. Bez tego wyjątku w `except` walidacja oceny
    przepuszczała go dalej i klient (albo mobile) dostawał 500 zamiast 400."""
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000497')
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/ocena',
                      json={'rating': float('inf')})

    assert odp.status_code == 400
    assert sr.review is None


def test_ocena_bool_odrzucona(app, db, client, login, make_user):
    """`bool` to podtyp `int`: int(True) == 1, a kontrola ułamka dotyczy tylko float,
    więc {"rating": true} z apki albo curla wracało z 200 i zapisywało opinię na jedną
    gwiazdkę — do średniej w statystykach i na listę reklamacji admina."""
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000498')
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/ocena', json={'rating': True})

    assert odp.status_code == 400
    assert sr.review is None


def test_komentarz_nie_string_odrzucony_z_400(app, db, client, login, make_user):
    """`.strip()` na liczbie rzuca AttributeError, a `zapisz_ocene` łapie wyłącznie
    ValueError — {"comment": 123} kończyło się 500-tką zamiast czytelnym 400. Ten sam
    błąd „zły typ wyjątku daje 500", co Infinity w ocenie (test wyżej)."""
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000499')
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/ocena',
                      json={'rating': 5, 'comment': 123})

    assert odp.status_code == 400
    assert sr.review is None


def test_komentarz_za_dlugi_odrzucony_przez_api(app, db, client, login, make_user):
    """Formularz webowy ma maxlength=2000, ale API (mobile) go omija — dawniej
    komentarz ponad 2000 znaków był po cichu ucinany zamiast odrzucony jawnym
    błędem, więc klient tracił końcówkę treści bez żadnego sygnału."""
    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000495')
    login(user)

    odp = client.post(f'/client/shipping/requests/{sr.id}/ocena',
                      json={'rating': 5, 'comment': 'a' * 2001})

    assert odp.status_code == 400
    assert sr.review is None


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


def test_opinia_zostaje_widoczna_po_zmianie_statusu_poza_ocenialne(
        app, db, client, login, make_user):
    """Komentarz przy `pokaz_ocene` obiecuje, że istniejąca opinia zostaje widoczna,
    nawet gdy status zjedzie poza STATUSY_Z_OCENA = ('wyslane', 'dostarczone') — np.
    admin ręcznie cofnie błędnie oznaczone 'dostarczone' z powrotem na 'spakowane'
    ('spakowane' to realny, seedowany status spoza zbioru — patrz migracja
    a1f8b2c3d4e5). Dawny warunek `sr.status in STATUSY_Z_OCENA and (...)` chował
    sekcję razem z już wystawioną oceną — łamał obietnicę z komentarza. Poprawiamy
    zachowanie, nie komentarz: intencja komentarza jest słuszna, kod jej nie
    realizował. Ten test jest jedyną osłoną przed „przywróceniem brakującego
    strażnika" po statusie w widoku GET."""
    from modules.orders.models import get_local_now
    from modules.orders.review_models import DeliveryReview

    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000496', status='dostarczone')
    sr.delivered_at = get_local_now() - timedelta(days=1)
    db.session.add(DeliveryReview(shipping_request_id=sr.id, user_id=user.id,
                                   rating=5, comment='Super szybko'))
    db.session.commit()

    sr.status = 'spakowane'
    db.session.commit()
    login(user)

    tresc = client.get(f'/client/shipping/requests/{sr.id}/potwierdz').get_data(as_text=True)

    assert 'deliveryReview' in tresc
    assert 'Super szybko' in tresc


def test_zablokowana_sekcja_nie_obiecuje_edycji_oceny(app, db, client, login, make_user):
    """Podpowiedź pod przyciskiem szła za `review.mozna_edytowac`, a blokada
    kontrolek za `okno_oceny_otwarte` — dwa różne okna. Paczka dostarczona ponad
    30 dni temu (okno oceny zamknięte) z opinią wystawioną przed chwilą (okno
    edycji otwarte) dostawała `data-editable="false"`, czyli martwe gwiazdki
    i zablokowany przycisk, a nad nimi zdanie „Ocenę możesz zmieniać przez 3 dni".
    Ten sam rozjazd daje status cofnięty poza STATUSY_Z_OCENA."""
    from modules.orders.models import get_local_now
    from modules.orders.review_models import DeliveryReview

    user = make_user(profile_completed=True)
    sr = _zlecenie(db, user, 'WYS/000498', status='dostarczone')
    sr.delivered_at = get_local_now() - timedelta(days=31)
    db.session.add(DeliveryReview(shipping_request_id=sr.id, user_id=user.id,
                                   rating=4, comment='Dotarło z opóźnieniem'))
    db.session.commit()
    login(user)

    tresc = client.get(f'/client/shipping/requests/{sr.id}/potwierdz').get_data(as_text=True)

    assert sr.review.mozna_edytowac is True, 'okno edycji ma być jeszcze otwarte'
    assert 'data-editable="false"' in tresc
    assert 'Ocenę możesz zmieniać' not in tresc
    assert 'tylko do wglądu' in tresc


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
