"""Pupile na czasie UTC: symulacja liczy upływ w UTC, a pora dnia i „dzisiaj” idą wg czasu polskiego.

Doba polska zaczyna się o 22:00 UTC (czas letni) albo 23:00 UTC (zimowy) — stąd chwile tuż przed
i tuż po północy polskiej, które w UTC leżą jeszcze w tym samym dniu.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from tests.pets_helpers import zaloz_profil, zaloz_pupila, zaloz_zmarlego

UTC = timezone.utc
# 12.10.2026 (czas letni, UTC+2): 23:30 PL = 21:30 UTC, 00:30 PL (13.10) = 22:30 UTC
PL_12_2330 = datetime(2026, 10, 12, 21, 30, tzinfo=UTC)
PL_13_0030 = datetime(2026, 10, 12, 22, 30, tzinfo=UTC)


def _cfg():
    from modules.pets.config import PetConfig
    return PetConfig()


# --- pora dnia ---

def test_noc_wg_godziny_polskiej_latem():
    from modules.pets import rules
    assert rules.is_night(datetime(2026, 7, 1, 21, 30, tzinfo=UTC), _cfg()) is True    # 23:30 PL
    assert rules.is_night(datetime(2026, 7, 1, 5, 30, tzinfo=UTC), _cfg()) is False    # 07:30 PL


def test_noc_wg_godziny_polskiej_przy_zmianie_czasu():
    from modules.pets import rules
    cfg = _cfg()
    assert rules.is_night(datetime(2026, 10, 24, 20, 30, tzinfo=UTC), cfg) is False   # 22:30 CEST
    assert rules.is_night(datetime(2026, 10, 24, 21, 30, tzinfo=UTC), cfg) is True    # 23:30 CEST
    assert rules.is_night(datetime(2026, 10, 25, 21, 30, tzinfo=UTC), cfg) is False   # 22:30 CET
    assert rules.is_night(datetime(2026, 10, 25, 22, 30, tzinfo=UTC), cfg) is True    # 23:30 CET
    assert rules.is_night(datetime(2026, 10, 26, 5, 30, tzinfo=UTC), cfg) is True     # 06:30 CET
    assert rules.is_night(datetime(2026, 10, 26, 6, 0, tzinfo=UTC), cfg) is False     # 07:00 CET


def test_noc_z_naiwnym_czasem_to_blad():
    from modules.pets import rules
    with pytest.raises(ValueError):
        rules.is_night(datetime(2026, 10, 12, 23, 0), _cfg())


def test_symulacja_przez_zmiane_czasu_liczy_4_h():
    """25.10.2026 00:00→04:00 UTC = 02:00 CEST → 05:00 CET: 4 h snu, nie 3 ani 5 h zegara ściennego."""
    from modules.pets import rules
    cfg = _cfg()
    wynik = rules.simulate(rules.PetState(), cfg, datetime(2026, 10, 25, 0, 0, tzinfo=UTC),
                           datetime(2026, 10, 25, 4, 0, tzinfo=UTC))
    spadek_na_h = 100.0 / float(cfg.decay_hours['hunger']) * float(cfg.night['factor'])
    assert abs(wynik.state.hunger - (100.0 - 4 * spadek_na_h)) < 1e-6


# --- serializacja ---

def test_iso_w_utc_z_sufiksem_z():
    from modules.pets.common import iso
    assert iso(datetime(2026, 10, 12, 8, 0, 30, 999, tzinfo=UTC)) == '2026-10-12T08:00:30Z'
    assert iso(None) is None


def test_stan_z_noca_i_czasem_utc(db, make_user):
    from modules.pets.state import state_for_user
    user = make_user()
    s = state_for_user(user, now=datetime(2026, 7, 1, 21, 30, tzinfo=UTC), cfg=_cfg())
    assert s['now'] == '2026-07-01T21:30:00Z'
    assert s['night']['is_night'] is True


def test_karta_pamieci_daty_polskie(db, make_user):
    from modules.pets.common import memorial_dict
    user = make_user()
    zmarly = zaloz_zmarlego(user, died_at=PL_13_0030, hatched_at=PL_13_0030 - timedelta(days=10))
    zmarly.last_light_date = date(2026, 10, 12)
    m = memorial_dict(zmarly, PL_13_0030)
    assert m['hatched_at'] == '2026-10-03' and m['died_at'] == '2026-10-13'
    assert m['can_light'] is True     # 12.10 to już wczoraj w Polsce, choć w UTC nadal ten sam dzień


# --- limity dzienne ---

def test_swiatelko_po_polnocy_polskiej(db, make_user):
    from modules.pets.actions import light_candle
    user = make_user()
    zaloz_profil(user)
    zmarly = zaloz_zmarlego(user, died_at=PL_12_2330 - timedelta(days=3))
    light_candle(user, zmarly.id, now=PL_12_2330)
    assert zmarly.last_light_date == date(2026, 10, 12)
    light_candle(user, zmarly.id, now=PL_13_0030)      # nowa doba polska — drugie światełko wolno
    assert zmarly.lights_count == 2 and zmarly.last_light_date == date(2026, 10, 13)


def test_dzien_opieki_po_polnocy_polskiej(db, make_user):
    from modules.pets.actions import perform_action
    user = make_user()
    zaloz_profil(user, now=PL_12_2330 - timedelta(days=3))
    # chory pupil nie śpi w nocy — pat pat działa po obu stronach północy
    pet = zaloz_pupila(user, now=PL_12_2330, health=50.0, fun=50.0)
    pierwsza = perform_action(user, pet.id, 'pat', now=PL_12_2330, cfg=_cfg(), count=1)
    druga = perform_action(user, pet.id, 'pat', now=PL_13_0030, cfg=_cfg(), count=1)
    assert pierwsza['first_care_today'] is True and druga['first_care_today'] is True
    assert pet.care_days == 2 and pet.last_care_date == date(2026, 10, 13)


# --- raport i panel admina ---

def test_raport_opiekunowie_dziennie_wg_doby_polskiej(db, make_user):
    from modules.pets.common import add_event
    from modules.pets.report import build_report
    user = make_user()
    zaloz_profil(user, now=PL_12_2330 - timedelta(days=3))
    pet = zaloz_pupila(user, now=PL_12_2330 - timedelta(days=3))
    add_event(user.id, 'feed', PL_13_0030 - timedelta(minutes=20), pet_id=pet.id)   # 00:10 PL 13.10
    db.session.commit()
    r = build_report(1, now=PL_13_0030)
    assert r['caretakers_daily'] == [('2026-10-12', 0), ('2026-10-13', 1)]


def test_raport_dni_przez_zmiane_czasu_bez_dziur(db):
    """Doba 25.10 ma 25 h — kolejne dni raportu to kolejne daty polskie, nie chwile co −24 h
    (26.10 23:30 CET − 24 h = 25.10 23:30 CET, a − 48 h = 25.10 00:30 CEST: dwa razy 25.10)."""
    from modules.pets.report import build_report
    r = build_report(2, now=datetime(2026, 10, 26, 22, 30, tzinfo=UTC))
    assert [d for d, _n in r['caretakers_daily']] == ['2026-10-24', '2026-10-25', '2026-10-26']


def test_admin_aktywni_dzis_od_polnocy_polskiej(db, make_user):
    from modules.pets.admin_routes import admin_stats
    from modules.pets.common import add_event
    wczoraj, dzis = make_user(), make_user()
    for user in (wczoraj, dzis):
        zaloz_profil(user, now=PL_12_2330 - timedelta(days=3))
    pw = zaloz_pupila(wczoraj, now=PL_12_2330 - timedelta(days=3))
    pd = zaloz_pupila(dzis, species='mis', now=PL_12_2330 - timedelta(days=3))
    add_event(wczoraj.id, 'feed', PL_12_2330, pet_id=pw.id)                          # 23:30 PL 12.10
    add_event(dzis.id, 'feed', PL_13_0030 - timedelta(minutes=20), pet_id=pd.id)     # 00:10 PL 13.10
    db.session.commit()
    assert admin_stats(now=PL_13_0030, cfg=_cfg())['active_today'] == 1
