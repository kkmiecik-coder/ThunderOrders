"""Odznaki — ścieżka OD spełnienia warunku DO zapisu w user_achievement.

Regresja do audytu z 21.09.2026. `test_odznaki_metryki.py` pilnuje, żeby każda
odznaka miała funkcję liczącą, ale metryka może być w 100% poprawna, a odznaka i tak
nigdy się nie odblokuje — bo odblokowanie nie dzieje się samo. Robi je wyłącznie
jawne wywołanie `check_event` w miejscu, które wykonało akcję. Pasek postępu
w galerii liczy się osobno i na żywo, więc dobija do 100% niezależnie od tego,
czy odznaka wpadła.

Skutek na produkcji: `auto_add_order_to_collection` (dopisywanie zakupów do kolekcji
przy statusie „dostarczone") nie wołało `check_event` w ogóle. 338 z 376 pozycji
kolekcji pochodziło z tej ścieżki, a odznakę `collection-10` miało 5 osób —
dokładnie te 5, które dodały coś ręcznie. Testy metryk tego nie łapały, bo metryka
liczyła poprawnie; brakowało wywołania.
"""

import pytest

from modules.achievements.models import Achievement, UserAchievement
from modules.achievements.services import AchievementService


@pytest.fixture
def zasiej_odznaki(db):
    """Wgrywa komplet odznak z seed.py do testowej bazy."""
    from modules.achievements.seed import seed_achievements

    seed_achievements()
    return db


def _ma_odznake(user, slug):
    return db_ma_odznake(user.id, slug)


def db_ma_odznake(user_id, slug):
    return (
        UserAchievement.query
        .join(Achievement)
        .filter(UserAchievement.user_id == user_id, Achievement.slug == slug)
        .first()
        is not None
    )


def _dodaj_pozycje(db, order, ile, make_product):
    from modules.orders.models import OrderItem

    for i in range(ile):
        produkt = make_product(name=f'Album {i + 1}')
        db.session.add(OrderItem(
            order_id=order.id,
            product_id=produkt.id,      # product_name to property liczona z produktu
            quantity=1,
            price=50.00,
            total=50.00,
        ))
    db.session.commit()


def test_auto_dodanie_do_kolekcji_odblokowuje_odznake(
        app, zasiej_odznaki, db, make_user, make_order, make_product):
    """Zakup dostarczony → pozycje w kolekcji → odznaka collection-1.

    To jest dokładnie ta ścieżka, która na produkcji nie odblokowywała nic.
    """
    from modules.client.collection_utils import (
        auto_add_order_to_collection, sprawdz_odznaki_kolekcji)

    klient = make_user(email='kolekcjoner@example.com')
    zamowienie = make_order(klient, status='dostarczone')
    _dodaj_pozycje(db, zamowienie, 1, make_product)

    assert not db_ma_odznake(klient.id, 'collection-1')

    uzytkownik = auto_add_order_to_collection(zamowienie)
    db.session.commit()
    sprawdz_odznaki_kolekcji([uzytkownik])

    assert db_ma_odznake(klient.id, 'collection-1'), (
        'Kolekcja urosła automatycznie, a odznaka nie wpadła — to jest ten bug.'
    )


def test_auto_dodanie_przeskakuje_progi_posrednie(
        app, zasiej_odznaki, db, make_user, make_order, make_product):
    """Jedna dostawa z 10 pozycjami daje od razu collection-1 i collection-10."""
    from modules.client.collection_utils import (
        auto_add_order_to_collection, sprawdz_odznaki_kolekcji)

    klient = make_user(email='hurtownik@example.com')
    zamowienie = make_order(klient, status='dostarczone')
    _dodaj_pozycje(db, zamowienie, 10, make_product)

    sprawdz_odznaki_kolekcji([auto_add_order_to_collection(zamowienie)])

    assert db_ma_odznake(klient.id, 'collection-1')
    assert db_ma_odznake(klient.id, 'collection-10')


def test_auto_dodanie_bez_nowych_pozycji_nie_wola_sprawdzenia(
        app, zasiej_odznaki, db, make_user, make_order, make_product):
    """Powtórne wywołanie jest idempotentne i nie zgłasza użytkownika do sprawdzenia."""
    from modules.client.collection_utils import auto_add_order_to_collection

    klient = make_user(email='powtorka@example.com')
    zamowienie = make_order(klient, status='dostarczone')
    _dodaj_pozycje(db, zamowienie, 1, make_product)

    assert auto_add_order_to_collection(zamowienie) == klient.id
    db.session.commit()

    assert auto_add_order_to_collection(zamowienie) is None


def test_sprawdz_odznaki_kolekcji_ignoruje_none(app, zasiej_odznaki, db):
    """None z auto_add (nic nie doszło) nie może wywrócić wywołania."""
    from modules.client.collection_utils import sprawdz_odznaki_kolekcji

    sprawdz_odznaki_kolekcji([None, None])


def test_nowa_pozycja_ze_zdjeciami_odpala_odznaki_fotograficzne(
        app, zasiej_odznaki, db, make_user, monkeypatch):
    """Zdjęcia dołączone do NOWEJ pozycji liczą się do items_with_photos.

    Metryka wisi na evencie 'photo_upload', który do tej pory leciał wyłącznie
    z osobnego uploadu do istniejącej pozycji.
    """
    from modules.client import collection_service
    from utils import image_processor

    klient = make_user(email='fotograf@example.com')
    wolane = []

    prawdziwy_check = AchievementService.check_event

    def szpieg(self, user, event_type, context=None):
        wolane.append(event_type)
        return prawdziwy_check(self, user, event_type, context)

    monkeypatch.setattr(AchievementService, 'check_event', szpieg)
    # create_item importuje tę funkcję lokalnie, więc podmieniamy ją u źródła.
    monkeypatch.setattr(
        image_processor, 'process_collection_upload', lambda *a, **k: {
            'filename': 'x.jpg', 'path_original': 'o/x.jpg', 'path_compressed': 'c/x.jpg',
        })

    class _Plik:
        filename = 'x.jpg'

    ok, err, item = collection_service.create_item(
        klient, 'Album ze zdjęciem', files=[_Plik()])

    assert ok, err
    assert 'collection_add' in wolane
    assert 'photo_upload' in wolane, (
        'Zdjęcie dodane razem z pozycją nie odpaliło odznak fotograficznych.'
    )


def test_kazde_auto_dodanie_do_kolekcji_sprawdza_odznaki():
    """Każdy moduł wołający auto_add_order_to_collection musi wołać też sprawdzenie odznak.

    Test na poziomie źródeł, bo bug nie polegał na złej logice tylko na BRAKU
    wywołania — a tego żaden test jednostkowy helpera nie złapie. Ścieżek jest
    kilka (pojedyncza zmiana statusu, zmiana masowa, domknięcie zlecenia w WMS)
    i każda kolejna równie łatwo o tym zapomni.
    """
    from pathlib import Path

    korzen = Path(__file__).resolve().parent.parent
    braki = []
    for sciezka in korzen.joinpath('modules').rglob('*.py'):
        # errors='ignore' — w modules/ leży plik nie-UTF-8, a nas interesują
        # wyłącznie dwie nazwy funkcji (czysty ASCII), więc podmiana bajtów nie szkodzi.
        tresc = sciezka.read_text(encoding='utf-8', errors='ignore')
        if 'auto_add_order_to_collection(' not in tresc:
            continue
        if sciezka.name == 'collection_utils.py':      # tu jest definicja
            continue
        if 'sprawdz_odznaki_kolekcji(' not in tresc:
            braki.append(str(sciezka.relative_to(korzen)))

    assert not braki, (
        'Te moduły dopisują zakupy do kolekcji, ale nie sprawdzają odznak — '
        f'kolekcja urośnie, a odznaki nie wpadną: {braki}'
    )


def test_backfill_nie_rozdaje_odznak_klienckich_adminom(
        app, zasiej_odznaki, db, make_user, make_order):
    """backfill_all filtruje role='client' — tak samo jak run_daily_checks.

    Bez tego filtra backfill z 08.09.2026 przyznał 49 odznak klienckich dwóm
    kontom admin (stąd „2 osoby mają member-180d", mimo że 0 klientów spełniało warunek).
    """
    admin = make_user(role='admin', email='admin@example.com')
    klient = make_user(email='zwykly@example.com')
    make_order(admin)
    make_order(klient)

    AchievementService().backfill_all()

    assert db_ma_odznake(klient.id, 'first-order')
    assert not db_ma_odznake(admin.id, 'first-order'), (
        'Backfill przyznał odznakę kliencką koncie admin.'
    )


def test_backfill_pomija_metryki_zalezne_od_momentu_uruchomienia(
        app, zasiej_odznaki, db, make_user, make_order):
    """`night-owl` nie patrzy na klienta, tylko na godzinę uruchomienia.

    Backfill odpalony między 00:00 a 05:00 przyznałby „Nocnego marka" wszystkim
    klientom naraz, niezależnie od tego, kiedy faktycznie składali zamówienia.
    """
    klient = make_user(email='nocny@example.com')
    make_order(klient)

    wynik = AchievementService().backfill_all()

    assert 'night-owl' in wynik['pominiete']
    assert 'weekend-warrior' in wynik['pominiete']
    assert not db_ma_odznake(klient.id, 'night-owl')


def test_unlock_loguje_awarie_zamiast_ja_polykac(
        app, zasiej_odznaki, db, make_user, monkeypatch, caplog):
    """Realny błąd zapisu musi zostawić ślad w logu.

    Wcześniej `except Exception: return` łapał wszystko bez jednej linijki logu —
    dlatego problem z odblokowywaniem przeżył miesiące niezauważony.
    """
    klient = make_user(email='awaria@example.com')
    odznaka = Achievement.query.filter_by(slug='first-order').first()

    def wybuch():
        raise RuntimeError('baza padła')

    monkeypatch.setattr(db.session, 'commit', wybuch)

    with caplog.at_level('ERROR'):
        AchievementService().unlock(klient, odznaka)

    assert any('first-order' in r.message for r in caplog.records), (
        'Awaria zapisu odznaki przeszła bez śladu w logach.'
    )
