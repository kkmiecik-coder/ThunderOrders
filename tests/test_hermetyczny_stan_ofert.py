"""Stan ofert w testach musi być hermetyczny (in-memory), nigdy Redis.

`create_app` woła `init_state(REDIS_URL)`, więc gdy na maszynie deweloperskiej
działa lokalny Redis — a działa — cała suita pisze do NIEGO. Stan rezerwacji
(`user_session`, `reservation_session`, TTL 1h) przeżywa wtedy nie tylko między
testami, ale i między kolejnymi uruchomieniami pytesta.

Objaw: testy przechodzą albo nie zależnie od tego, co zostało w Redisie po
poprzednim przebiegu. `tests/test_mobile_api_ws.py` obchodził to od dawna
własnym `init_state(None)` w fixture, ale tylko dla siebie — reszta suity
pisała do współdzielonego Redisa.

Backend jest wymienny (ten sam interfejs), więc logika jest identyczna —
in-memory daje po prostu izolację.
"""


def test_suita_nie_uzywa_redis(app):
    """Fixture `app` musi wymusić in-memory, mimo że create_app podłącza Redis."""
    from modules.offers.redis_state import is_redis_backed

    assert is_redis_backed() is False, (
        'Testy piszą do lokalnego Redisa — stan przecieka między testami '
        'i między uruchomieniami pytesta'
    )


def test_stan_ofert_nie_przecieka_miedzy_testami_czesc_1(app):
    """Para testów: pierwszy zapisuje, drugi sprawdza, że nic nie zostało.

    Gdyby backendem był Redis, wartość przeżyłaby do kolejnego testu (TTL 1h)
    i część 2 by ją zobaczyła.
    """
    from modules.offers.redis_state import get_state

    stan = get_state()
    stan.set_user_session(999001, 999002, 'sid-z-testu-1')
    assert stan.get_user_session(999001, 999002) == 'sid-z-testu-1'


def test_stan_ofert_nie_przecieka_miedzy_testami_czesc_2(app):
    from modules.offers.redis_state import get_state

    assert get_state().get_user_session(999001, 999002) is None, (
        'Wartość zapisana w poprzednim teście przeżyła — stan nie jest hermetyczny'
    )
