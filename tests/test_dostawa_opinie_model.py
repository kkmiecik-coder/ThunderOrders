"""Model opinii o dostawie — jedna na paczkę, edytowalna przez 3 dni."""
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError


def _zlecenie(db, user, numer='WYS/000100'):
    from modules.orders.models import ShippingRequest
    sr = ShippingRequest(request_number=numer, user_id=user.id, status='dostarczone')
    db.session.add(sr)
    db.session.commit()
    return sr


def test_jedna_opinia_na_zlecenie(app, db, make_user):
    from modules.orders.review_models import DeliveryReview

    user = make_user()
    sr = _zlecenie(db, user)
    db.session.add(DeliveryReview(shipping_request_id=sr.id, user_id=user.id, rating=5))
    db.session.commit()

    db.session.add(DeliveryReview(shipping_request_id=sr.id, user_id=user.id, rating=3))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_ocena_poza_zakresem_odrzucona(app, db, make_user):
    from modules.orders.review_models import DeliveryReview

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000101')

    for zla in (0, 6, -1):
        with pytest.raises(ValueError):
            DeliveryReview(shipping_request_id=sr.id, user_id=user.id, rating=zla)


def test_ocena_niecalkowita_odrzucona_przez_model(app, db, make_user):
    """`int(4.9)` zapisywało po cichu 4 — ocenę, której nikt nie wystawił, a która
    wchodzi do średniej w statystykach. Warstwa HTTP (`zapisz_ocene`) już to łapie,
    ale każdy zapis prosto do modelu (backfill, powłoka) ją omija; poza tym model
    odrzuca za długi komentarz, więc ciche obcinanie oceny było asymetrią."""
    from modules.orders.review_models import DeliveryReview

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000106')

    for zla in (4.9, 0.5, float('inf'), 'cztery'):
        with pytest.raises(ValueError):
            DeliveryReview(shipping_request_id=sr.id, user_id=user.id, rating=zla)


def test_ocena_bool_odrzucona_przez_model(app, db, make_user):
    """`bool` jest podtypem `int`, więc int(True) == 1, a kontrola „konwersja niczego
    nie zgubiła" (`ocena != wartosc`) wychodzi prawdą, bo 1 == True. Efekt:
    DeliveryReview(rating=True) zapisywał jednogwiazdkową opinię, której nikt nie
    wystawił — prosto do średniej w statystykach."""
    from modules.orders.review_models import DeliveryReview

    user = make_user()
    sr_true = _zlecenie(db, user, 'WYS/000109')
    sr_false = _zlecenie(db, user, 'WYS/000110')

    for zlecenie, zla in ((sr_true, True), (sr_false, False)):
        with pytest.raises(ValueError):
            DeliveryReview(shipping_request_id=zlecenie.id, user_id=user.id, rating=zla)


def test_komentarz_nie_string_odrzucony_valueerrorem(app, db, make_user):
    """`.strip()` na liczbie rzuca AttributeError, a `zapisz_ocene` łapie wyłącznie
    ValueError — {"comment": 123} z API kończyło się 500-tką zamiast 400. Ten sam
    błąd „zły typ wyjątku daje 500", co OverflowError w walidacji oceny."""
    from modules.orders.review_models import DeliveryReview

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000111')

    for zly in (123, 4.5, ['a'], {'a': 1}):
        with pytest.raises(ValueError):
            DeliveryReview(shipping_request_id=sr.id, user_id=user.id, rating=4,
                           comment=zly)


def test_ocena_calkowita_jako_float_lub_string_akceptowana(app, db, make_user):
    """Odrzucamy ułamek, nie sam typ: 4.0 i '4' to nadal poprawna ocena 4."""
    from modules.orders.review_models import DeliveryReview

    user = make_user()
    sr_float = _zlecenie(db, user, 'WYS/000107')
    sr_string = _zlecenie(db, user, 'WYS/000108')

    assert DeliveryReview(shipping_request_id=sr_float.id, user_id=user.id,
                          rating=4.0).rating == 4
    assert DeliveryReview(shipping_request_id=sr_string.id, user_id=user.id,
                          rating='4').rating == 4


def test_okno_edycji_trwa_trzy_dni(app, db, make_user):
    from modules.orders.models import get_local_now
    from modules.orders.review_models import DeliveryReview

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000102')
    opinia = DeliveryReview(shipping_request_id=sr.id, user_id=user.id, rating=4)
    db.session.add(opinia)
    db.session.commit()

    assert opinia.mozna_edytowac is True

    opinia.created_at = get_local_now() - timedelta(days=2, hours=23)
    assert opinia.mozna_edytowac is True

    opinia.created_at = get_local_now() - timedelta(days=3, hours=1)
    assert opinia.mozna_edytowac is False


def test_komentarz_za_dlugi_odrzucony(app, db, make_user):
    """Kolumna comment to Text bez własnego limitu — dawniej `_przytnij_komentarz`
    cicho ucinała do 2000 znaków, więc klient tracił końcówkę bez żadnego sygnału.
    Formularz ma maxlength=2000 (zgodne z MAX_DLUGOSC_KOMENTARZA), więc to
    zabezpieczenie realnie chroni API (mobile), które ten formularz omija."""
    from modules.orders.review_models import DeliveryReview

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000104')

    with pytest.raises(ValueError):
        DeliveryReview(shipping_request_id=sr.id, user_id=user.id, rating=4,
                        comment='a' * 2001)


def test_komentarz_dokladnie_na_limicie_akceptowany(app, db, make_user):
    from modules.orders.review_models import DeliveryReview

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000105')

    opinia = DeliveryReview(shipping_request_id=sr.id, user_id=user.id, rating=4,
                             comment='a' * 2000)
    db.session.add(opinia)
    db.session.commit()

    assert len(opinia.comment) == 2000


def test_zlecenie_widzi_swoja_opinie(app, db, make_user):
    from modules.orders.review_models import DeliveryReview

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000103')
    assert sr.review is None

    db.session.add(DeliveryReview(
        shipping_request_id=sr.id, user_id=user.id, rating=5, comment='Szybko'))
    db.session.commit()
    db.session.refresh(sr)

    assert sr.review.rating == 5
    assert sr.review.comment == 'Szybko'
