import sqlite3

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app import create_app
from extensions import db as _db
from modules.offers.redis_state import init_state


@event.listens_for(Engine, 'connect')
def _egzekwuj_klucze_obce(dbapi_connection, connection_record):
    """Włącza egzekwowanie kluczy obcych na każdym połączeniu SQLite.

    SQLite domyślnie klucze obce PARSUJE, ale ich NIE sprawdza — produkcyjna MariaDB
    sprawdza. Bez tego pragma cała klasa błędów przechodzi przez testy bez śladu:
    skasowanie wiersza, na który wskazuje FK bez `ondelete` (np. zlecenia wysyłki
    trzymanego przez `wms_session_shipping_requests`), jest w testach ciszą, a na
    produkcji IntegrityError przy commicie. Listener wisi na klasie Engine, bo każdy
    test dostaje własny silnik z fixture `app`.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        kursor = dbapi_connection.cursor()
        kursor.execute('PRAGMA foreign_keys=ON')
        kursor.close()


def _zasiej_slowniki():
    """Wypełnia tabele słownikowe statusów tym, co produkcja ma od migracji.

    `orders.status`, `orders.order_type`, `order_items.wms_status` i
    `shipping_requests.status` to KLUCZE OBCE do słowników, a nie zwykłe enumy.
    Produkcyjna baza dostaje te wiersze z migracji i admin zarządza nimi z UI —
    testowe `create_all()` tworzy same puste tabele. Dopóki SQLite nie egzekwował
    kluczy obcych, można było wstawić zamówienie ze statusem, którego nie ma w
    słowniku; po włączeniu pragma taki INSERT jest tym, czym na produkcji był od
    zawsze — błędem. Zamiast dosypywać brakujące słowniki w setkach testów, testowa
    baza startuje z tym samym kompletem co produkcja.

    Wartości 1:1 z bazy deweloperskiej (zsynchronizowanej migracjami z produkcją) —
    łącznie z dziurami w sort_order, żeby kolejność „najmniej zaawansowanego"
    statusu była w testach dokładnie taka jak na żywo.
    """
    from modules.orders.models import OrderStatus, OrderType, ShippingRequestStatus, WmsStatus

    for slug, nazwa, kolor, kolejnosc in (
        ('nowe', 'Nowe', '#3B82F6', 0),
        ('oczekujace', 'Oczekujące', '#F97316', 1),
        ('dostarczone_proxy', 'Dostarczone do Proxy', '#9333EA', 2),
        ('w_drodze_polska', 'W drodze do Polski', '#9333EA', 3),
        ('urzad_celny', 'Urząd Celny', '#F59E0B', 4),
        ('dostarczone_gom', 'Dostarczone do GOM', '#9333EA', 5),
        ('spakowane', 'Spakowane', '#9333EA', 7),
        ('wyslane', 'Wysłane', '#9333EA', 8),
        ('dostarczone', 'Dostarczone', '#10B981', 9),
        ('anulowane', 'Anulowane', '#6B7280', 10),
        ('do_zwrotu', 'Do Zwrotu', '#F59E0B', 11),
        ('zwrocone', 'Zwrócone', '#EF4444', 12),
        ('czesciowo_zwrocone', 'Częściowo Zwrócone', '#F59E0B', 13),
    ):
        _db.session.add(OrderStatus(
            slug=slug, name=nazwa, badge_color=kolor, sort_order=kolejnosc, is_active=True))

    for slug, nazwa, prefiks, kolejnosc in (
        ('pre_order', 'Pre-order', 'PO', 1),
        ('on_hand', 'On-hand', 'OH', 2),
        ('exclusive', 'Exclusive', 'EX', 3),
    ):
        _db.session.add(OrderType(
            slug=slug, name=nazwa, prefix=prefiks, sort_order=kolejnosc, is_active=True))

    for slug, nazwa, kolor, kolejnosc, domyslny, zebrany in (
        ('do_zebrania', 'Do zebrania', '#FF9800', 1, True, False),
        ('zebrane', 'Zebrane', '#4CAF50', 2, False, True),
        ('brak_na_stanie', 'Brak na stanie', '#F44336', 3, False, False),
        ('zamowione', 'Zamówione', '#2196F3', 4, False, False),
        ('spakowane', 'Spakowane', '#9C27B0', 5, False, True),
    ):
        _db.session.add(WmsStatus(
            slug=slug, name=nazwa, badge_color=kolor, sort_order=kolejnosc,
            is_active=True, is_default=domyslny, is_picked=zebrany))

    for slug, nazwa, kolor, kolejnosc, poczatkowy in (
        ('czeka_na_wycene', 'Czeka na wycenę', '#F59E0B', 1, True),
        ('czeka_na_oplacenie', 'Czeka na opłacenie', '#EF4444', 2, False),
        ('oplacone', 'Opłacone', '#10B981', 4, False),
        ('spakowane', 'Spakowane', '#8B5CF6', 5, False),
        ('wyslane', 'Wysłane', '#3B82F6', 6, False),
        ('dostarczone', 'Dostarczone', '#059669', 7, False),
    ):
        _db.session.add(ShippingRequestStatus(
            slug=slug, name=nazwa, badge_color=kolor, sort_order=kolejnosc,
            is_active=True, is_initial=poczatkowy))

    _db.session.commit()


@pytest.fixture
def app():
    app = create_app('testing')
    # Stan ofert hermetycznie in-memory, NIGDY Redis. `create_app` woła
    # `init_state(REDIS_URL)`, więc na maszynie z lokalnym Redisem cała suita
    # pisała do niego: stan rezerwacji (user_session/reservation_session, TTL 1h)
    # przeżywał między testami ORAZ między kolejnymi uruchomieniami pytesta,
    # przez co wynik zależał od tego, co zostało po poprzednim przebiegu.
    # Backend jest wymienny (ten sam interfejs), więc logika jest identyczna —
    # zmienia się wyłącznie izolacja. Dotąd obchodził to tylko
    # tests/test_mobile_api_ws.py, we własnym zakresie.
    init_state(None)
    with app.app_context():
        _db.create_all()
        _zasiej_slowniki()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(autouse=True)
def _czysty_cache_przelacznikow_maili():
    """Zeruje cache przełączników e-mail przed i po każdym teście.

    EmailManager trzyma `email_notifications_config` w atrybucie KLASY z 60-sekundowym
    TTL, a klasa żyje przez cały przebieg pytesta — baza nie. Test, który wyłączył
    jakiś przełącznik (np. `notify_delivery_confirmation`), zostawiał tę wartość w
    cache'u dla wszystkich kolejnych testów w tej samej minucie, mimo że ich baza jest
    świeża i nic w niej nie jest wyłączone. Efekt: wynik testu zależy od tego, co
    uruchomiono przed nim i jak szybko poszło — czyli dokładnie ten rodzaj
    niedeterminizmu, którego szukaliśmy.
    """
    from utils.email_manager import EmailManager
    EmailManager.clear_email_config_cache()
    yield
    EmailManager.clear_email_config_cache()


class _WatekNatychmiastowy:
    """Zamiennik threading.Thread na potrzeby testów renderujących maile naprawdę.

    send_email()/send_email_batch() renderują szablon Jinja SYNCHRONICZNIE, ale samą
    wysyłkę odpalają w wątku tła — bez tej podmiany asercja na treść wysłanej
    wiadomości ścigałaby się z tamtym wątkiem (albo trafiałaby na listener
    mail.record_messages() już odłączony po wyjściu z bloku `with`). Podmieniamy
    WYŁĄCZNIE start wątku na wywołanie synchroniczne w tym samym wątku — renderowanie
    Jinja i mail.send() (przechwycony przez mail.record_messages()) zachodzą
    naprawdę, nic tu nie jest zaślepką.
    """

    def __init__(self, target=None, args=(), kwargs=None, name=None, **_ignorowane):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)

    def join(self, timeout=None):
        pass


@pytest.fixture
def maile_synchronicznie(app, monkeypatch):
    """Maile renderują się i „wysyłają" w wątku testu, do mail.record_messages().

    Poza podmianą wątku (patrz _WatekNatychmiastowy) ustawia MAIL_DEFAULT_SENDER:
    .env w worktree ma go jako pusty, ale USTAWIONY string, a os.getenv(..., domyślna)
    w config.py oddaje wtedy '' — Message z pustym nadawcą Flask-Mail odrzuca asercją
    przy send(), nawet tłumionym przez mail.suppress. To kwestia konfiguracji
    środowiska, nie kodu produkcyjnego.
    """
    monkeypatch.setattr('utils.email_sender.Thread', _WatekNatychmiastowy)
    monkeypatch.setitem(app.config, 'MAIL_DEFAULT_SENDER', 'noreply@thunderorders.cloud')
    # Batch (send_async_email_batch) śpi 2 s między wiadomościami, żeby trzymać się
    # limitów dostawcy — w teście synchronicznym to czysty przestój.
    monkeypatch.setattr('utils.email_sender.time.sleep', lambda _s: None)


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(db):
    # Import odłożony do czasu wykonania fixture — create_app() musi najpierw
    # zainicjalizować rozszerzenie SQLAlchemy i zarejestrować blueprinty,
    # zanim moduły modeli zostaną załadowane.
    from modules.auth.models import User

    counter = {'n': 0}

    def _make(role='client', email=None, **kwargs):
        counter['n'] += 1
        u = User(
            email=email or f'user{counter["n"]}@example.com',
            role=role,
            is_active=True,
            email_verified=True,
            **kwargs,
        )
        db.session.add(u)
        db.session.commit()
        return u
    return _make


@pytest.fixture
def make_product(db):
    from modules.products.models import Product

    counter = {'n': 0}

    def _make(name=None, sale_price=99.00, quantity=10, **kwargs):
        counter['n'] += 1
        p = Product(
            name=name or f'Produkt {counter["n"]}',
            sale_price=sale_price,
            quantity=quantity,
            **kwargs,
        )
        db.session.add(p)
        db.session.commit()
        return p
    return _make


@pytest.fixture
def make_order(db):
    from modules.orders.models import Order

    counter = {'n': 0}

    def _make(user, status='nowe', total_amount=100.00, created_at=None, **kwargs):
        counter['n'] += 1
        o = Order(
            order_number=f'PO/{counter["n"]:08d}',
            user_id=user.id,
            status=status,
            total_amount=total_amount,
            **kwargs,
        )
        if created_at is not None:
            o.created_at = created_at
        db.session.add(o)
        db.session.commit()
        return o
    return _make


@pytest.fixture
def strona_sprzedazy(db, make_user):
    """Strona sprzedaży o id=1 — pokrycie dla zamówień tworzonych z `offer_page_id=1`.

    `orders.offer_page_id` to klucz obcy do `offer_pages`, a produkcja nie potrafi
    wytworzyć zamówienia wskazującego na nieistniejącą stronę (skasowanie strony zeruje
    kolumnę przez ondelete=SET NULL). Dopóki SQLite nie sprawdzał kluczy obcych,
    `offer_page_id=1` było w testach wygodnym znacznikiem „zamówienie z oferty" bez
    żadnego wiersza w bazie — teraz ten znacznik musi mieć pokrycie.
    """
    from modules.offers.models import OfferPage

    strona = db.session.get(OfferPage, 1)
    if strona is None:
        autor = make_user(role='admin', email='autor-oferty@example.com')
        strona = OfferPage(id=1, name='Drop testowy', token=OfferPage.generate_token(),
                           status='active', created_by=autor.id)
        db.session.add(strona)
        db.session.commit()
    return strona


@pytest.fixture
def login(client):
    """Loguje użytkownika przez Flask-Login test session."""
    def _login(user):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
    return _login
