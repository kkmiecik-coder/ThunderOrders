"""Czysta matematyka stanu pupila (modules/pets/rules.py) — bez Flaska i bazy.

Czasy: poniedziałek 2026-10-12. Dzień = 08:00–20:00 (daleko od nocy 23–07).

Testy reguł CELOWO nie importują PetConfig: rules.py ma być niezależne od reszty
modułu (i od sesji, która równolegle pisze config.py). Konfiguracja to obiekt
o kształcie PetConfig z liczbami ze specu §3.4; zgodność z prawdziwym PetConfig
sprawdza test dopisywany przy integracji etapu (Task 7).
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from modules.pets import rules
from modules.pets.rules import PetState


def _cfg(**nadpisania):
    """Atrapa PetConfig: te same nazwy pól, te same domyślne liczby co spec §3.4."""
    bazowe = dict(
        decay_hours={'hunger': 24, 'fun': 30, 'clean': 48},
        night={'start': 23, 'end': 7, 'factor': 0.25},
        health_drop_hours=72, health_regen_hours=24,
        egg_hours=168, start_egg_hours=48,
        boost={'hours': 8, 'factor': 2},
        max_stars=5, stage_days={'child': 24, 'adult': 80},
    )
    bazowe.update(nadpisania)
    return SimpleNamespace(**bazowe)


CFG = _cfg()
PON_08 = datetime(2026, 10, 12, 8, 0)
PON_23 = datetime(2026, 10, 12, 23, 0)
WT_07 = datetime(2026, 10, 13, 7, 0)
PELNY = PetState()


def blisko(a, b, eps=0.05):
    return abs(a - b) <= eps


# --- noc / sen ---

@pytest.mark.parametrize('godzina,minuta,noc', [
    (22, 59, False), (23, 0, True), (2, 30, True), (6, 59, True), (7, 0, False), (12, 0, False),
])
def test_is_night_granice(godzina, minuta, noc):
    assert rules.is_night(datetime(2026, 10, 12, godzina, minuta), CFG) is noc


def test_is_night_bez_nocy_gdy_start_rowny_end():
    """Review Focus 2: start == end oznacza brak nocy, nie noc całą dobę."""
    cfg = _cfg(night={'start': 7, 'end': 7, 'factor': 0.25})
    for h in range(24):
        assert rules.is_night(datetime(2026, 10, 12, h, 0), cfg) is False


def test_is_night_okno_niewychodzace_poza_polnoc():
    cfg = _cfg(night={'start': 1, 'end': 5, 'factor': 0.25})
    assert rules.is_night(datetime(2026, 10, 12, 3, 0), cfg) is True
    assert rules.is_night(datetime(2026, 10, 12, 23, 0), cfg) is False


def test_wake_reasons():
    assert rules.wake_reasons(PELNY, PON_23) == ()
    assert rules.wake_reasons(PetState(hunger=29.9), PON_23) == ('hungry',)
    assert rules.wake_reasons(PetState(fun=0), PON_23) == ('zero',)
    assert rules.wake_reasons(PetState(health=74.9), PON_23) == ('sick',)
    obudzony = PetState(awake_until=PON_23 + timedelta(minutes=20))
    assert rules.wake_reasons(obudzony, PON_23) == ('woken',)
    assert rules.wake_reasons(PetState(hunger=0, health=10), PON_23) == ('hungry', 'zero', 'sick')


def test_awake_until_w_przeszlosci_jak_none():
    """Review Focus 3."""
    stan = PetState(awake_until=PON_23 - timedelta(minutes=1))
    assert rules.wake_reasons(stan, PON_23) == ()
    assert rules.is_asleep(stan, PON_23, CFG) is True


def test_is_asleep():
    assert rules.is_asleep(PELNY, PON_23, CFG) is True
    assert rules.is_asleep(PELNY, PON_08, CFG) is False          # dzień
    assert rules.is_asleep(PetState(hunger=20), PON_23, CFG) is False   # głodny nie śpi
    assert rules.is_asleep(PetState(clean=0), PON_23, CFG) is False     # zero nie śpi
    assert rules.is_asleep(PetState(health=50), PON_23, CFG) is False   # chory nie śpi


# --- tempo ---

def test_decay_multiplier_dzien_noc_gwiazdki():
    assert rules.decay_multiplier(PELNY, PON_08, CFG) == 1.0
    assert rules.decay_multiplier(PELNY, PON_23, CFG) == 0.25
    assert blisko(rules.decay_multiplier(PetState(stars=2), PON_08, CFG), 0.8, 1e-9)
    assert blisko(rules.decay_multiplier(PetState(stars=2), PON_23, CFG), 0.2, 1e-9)


def test_gwiazdki_ponad_max_licza_sie_jak_max():
    assert blisko(rules.decay_multiplier(PetState(stars=9), PON_08, CFG), 0.5, 1e-9)


def test_rates_per_hour_pelny_w_dzien():
    r = rules.rates_per_hour(PELNY, PON_08, CFG)
    assert blisko(r['hunger'], -100 / 24, 1e-6)
    assert blisko(r['fun'], -100 / 30, 1e-6)
    assert blisko(r['clean'], -100 / 48, 1e-6)
    assert r['health'] == 0.0   # zdrowie pełne — nic do regeneracji


def test_rates_per_hour_pasek_na_zerze_zbija_zdrowie():
    r = rules.rates_per_hour(PetState(hunger=0), PON_08, CFG)
    assert r['hunger'] == 0.0            # nie schodzi poniżej zera
    assert blisko(r['health'], -100 / 72, 1e-6)


def test_rates_per_hour_regeneracja_gdy_wszystko_ponad_50():
    r = rules.rates_per_hour(PetState(hunger=60, fun=51, clean=90, health=40), PON_08, CFG)
    assert blisko(r['health'], 100 / 24, 1e-6)


def test_rates_per_hour_zdrowie_stoi_gdy_pasek_ponizej_50_bez_zera():
    r = rules.rates_per_hour(PetState(hunger=40, health=60), PON_08, CFG)
    assert r['health'] == 0.0


def test_rates_per_hour_we_snie_cztery_razy_wolniej():
    r = rules.rates_per_hour(PELNY, PON_23, CFG)
    assert blisko(r['hunger'], -100 / 24 * 0.25, 1e-6)
