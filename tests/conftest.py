import pytest

from app import create_app
from extensions import db as _db


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


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
def login(client):
    """Loguje użytkownika przez Flask-Login test session."""
    def _login(user):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
    return _login
