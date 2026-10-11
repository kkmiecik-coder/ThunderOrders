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
        actions={'feed': 50, 'play': 50, 'heal': 40, 'heal_cooldown_h': 12, 'allow_below': 80,
                 'pat_gain': 0.25, 'pat_per_hour': 60, 'wake_penalty': 10, 'awake_minutes': 20},
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


# --- symulacja ---

def test_spadek_w_dzien_12h_polowa_sytosci():
    wynik = rules.simulate(PELNY, CFG, PON_08, PON_08 + timedelta(hours=12))
    assert blisko(wynik.state.hunger, 50)
    assert blisko(wynik.state.fun, 60)
    assert blisko(wynik.state.clean, 75)
    assert wynik.state.health == 100 and wynik.died_at is None


def test_gwiazdki_spowalniaja_spadek():
    wynik = rules.simulate(PetState(stars=2), CFG, PON_08, PON_08 + timedelta(hours=10))
    assert blisko(wynik.state.hunger, 100 - (100 / 24) * 10 * 0.8)


def test_noc_cztery_razy_wolniej():
    wynik = rules.simulate(PELNY, CFG, PON_23, WT_07)
    assert blisko(wynik.state.hunger, 100 - (100 / 24) * 8 * 0.25)   # 91.67


def test_glodny_budzi_sie_w_nocy_i_glodnieje_normalnie():
    # 32 → asleep do 30 (~2 h), potem pełne tempo przez ~6 h → ~4.9
    wynik = rules.simulate(PetState(hunger=32), CFG, PON_23, WT_07)
    assert 4 < wynik.state.hunger < 6


def test_pasek_na_zerze_budzi_i_zbija_zdrowie_w_nocy():
    wynik = rules.simulate(PetState(fun=0), CFG, PON_23, WT_07)
    assert blisko(wynik.state.hunger, 100 - (100 / 24) * 8)      # 66.67, bez snu
    assert blisko(wynik.state.health, 100 - (100 / 72) * 8)      # 88.89
    assert wynik.state.fun == 0


def test_chory_nie_spi_i_regeneruje_sie_gdy_paski_pelne():
    # Chory (70) nie śpi → paski pełnym tempem, zdrowie +4.17/h. „Chory" to zdrowie < 75
    # (spec §2.4), a pupil zasypia, „gdy tylko warunek zniknie" — czyli już przy 75, nie
    # przy 100. Na siatce 5 min: 15 kroków (1.25 h) czuwania, zasypia o 00:15 przy 75.2,
    # dalej regeneruje się we śnie (bez spowolnienia) i dobija do 100 o 06:15.
    # Sytość = 100 − 4.17·1.25 − 1.04·6.75 ≈ 87.76 (66.7, gdyby nie zasnął wcale).
    wynik = rules.simulate(PetState(health=70), CFG, PON_23, WT_07)
    assert wynik.state.health == 100
    assert blisko(wynik.state.hunger, 100 - (100 / 24) * 1.25 - (100 / 24) * 0.25 * 6.75)


def test_obudz_okno_potem_sen():
    stan = PetState(awake_until=PON_23 + timedelta(hours=1))
    wynik = rules.simulate(stan, CFG, PON_23, WT_07)
    oczekiwane = 100 - (100 / 24) * 1 - (100 / 24) * 0.25 * 7     # 88.54
    assert blisko(wynik.state.hunger, oczekiwane)


def test_zdrowie_spada_do_zera_w_72h_od_zera_paska():
    wynik = rules.simulate(PetState(hunger=0), CFG, PON_08, PON_08 + timedelta(hours=80))
    assert wynik.state.health == 0
    assert wynik.died_at is not None
    assert abs((wynik.died_at - (PON_08 + timedelta(hours=72))).total_seconds()) < 60


def test_odejscie_po_okolo_96h_bez_opieki_od_pelna():
    wynik = rules.simulate(PELNY, CFG, PON_08, PON_08 + timedelta(hours=120))
    assert wynik.died_at is not None
    godzin = (wynik.died_at - PON_08).total_seconds() / 3600
    assert 96 <= godzin <= 104, godzin   # noc spowalnia głodnienie, stąd > 96


def test_regeneracja_zdrowia_gdy_wszystko_ponad_50():
    wynik = rules.simulate(PetState(health=40), CFG, PON_08, PON_08 + timedelta(hours=10))
    assert blisko(wynik.state.health, 40 + (100 / 24) * 10)   # 81.67


def test_zdrowie_stoi_gdy_pasek_ponizej_50_ale_nie_zero():
    wynik = rules.simulate(PetState(hunger=40, health=60), CFG, PON_08, PON_08 + timedelta(hours=2))
    assert wynik.state.health == 60


def test_ostatni_krok_ulamkowy():
    wynik = rules.simulate(PELNY, CFG, PON_08, PON_08 + timedelta(minutes=7))
    assert blisko(wynik.state.hunger, 100 - (100 / 24) * (7 / 60), 1e-6)


def test_determinizm_siatki():
    calosc = rules.simulate(PELNY, CFG, PON_08, PON_08 + timedelta(hours=4)).state
    polowa = rules.simulate(PELNY, CFG, PON_08, PON_08 + timedelta(hours=2)).state
    reszta = rules.simulate(polowa, CFG, PON_08 + timedelta(hours=2), PON_08 + timedelta(hours=4)).state
    for pole in ('hunger', 'fun', 'clean', 'health'):
        assert blisko(getattr(calosc, pole), getattr(reszta, pole), 1e-6)


def test_czas_wstecz_nie_zmienia_stanu():
    """Zmiana czasu 25.10: get_local_now() cofa się o godzinę → T < state_at."""
    stan = PetState(hunger=70)
    wynik = rules.simulate(stan, CFG, datetime(2026, 10, 25, 3, 0), datetime(2026, 10, 25, 2, 0))
    assert wynik.state == stan and wynik.died_at is None


def test_brudne_wartosci_z_bazy_sa_klamrowane():
    """Review Focus 4."""
    wynik = rules.simulate(PetState(hunger=130, fun=-20, health=250), CFG, PON_08, PON_08)
    assert (wynik.state.hunger, wynik.state.fun, wynik.state.health) == (100, 0, 100)


def test_juz_odeszly_nie_ozywa():
    wynik = rules.simulate(PetState(hunger=0, health=0), CFG, PON_08, PON_08 + timedelta(hours=5))
    assert wynik.state.health == 0 and wynik.died_at is None   # died_at zna baza, nie symulacja


# --- nastrój ---

@pytest.mark.parametrize('stan,nastroj', [
    (PetState(), 'szczesliwy'),
    (PetState(hunger=50, fun=50, clean=50), 'szczesliwy'),
    (PetState(hunger=49), 'glodny'),
    (PetState(fun=30, hunger=40), 'znudzony'),      # najniższy pasek decyduje
    (PetState(clean=10), 'brudny'),
    (PetState(clean=0), 'smutny'),
    (PetState(clean=0, health=74), 'chory'),
    (PetState(health=24.9), 'krytyczny'),
])
def test_mood(stan, nastroj):
    assert rules.mood(stan) == nastroj


# --- stadia ---

@pytest.mark.parametrize('dni,stadium', [(0, 'maluch'), (23.99, 'maluch'), (24, 'dziecko'),
                                          (79.9, 'dziecko'), (80, 'dorosly'), (400, 'dorosly')])
def test_stage(dni, stadium):
    wyklucie = PON_08
    teraz = wyklucie + timedelta(days=dni)
    assert rules.stage(wyklucie, teraz, CFG) == stadium


def test_age_days_zaokragla_w_dol():
    assert rules.age_days(PON_08, PON_08 + timedelta(days=5, hours=23)) == 5
    assert rules.age_days(PON_08, PON_08 - timedelta(hours=1)) == 0


# --- jajko ---

def test_jajko_bez_ogrzania_liczy_czas_1_do_1():
    assert rules.egg_progress_seconds(0, PON_08, None, PON_08 + timedelta(hours=10), CFG) == 10 * 3600


def test_jajko_ogrzanie_x2_przez_8h():
    boost = PON_08 + timedelta(hours=8)
    # 10 h od zapisu: 8 h ×2 + 2 h ×1 = 18 h
    assert rules.egg_progress_seconds(0, PON_08, boost, PON_08 + timedelta(hours=10), CFG) == 18 * 3600
    # 3 h od zapisu, boost nadal trwa: 3 h ×2
    assert rules.egg_progress_seconds(0, PON_08, boost, PON_08 + timedelta(hours=3), CFG) == 6 * 3600


def test_jajko_dolicza_zapisany_postep():
    assert rules.egg_progress_seconds(5000, PON_08, None, PON_08 + timedelta(hours=1), CFG) == 5000 + 3600


def test_jajko_boost_sprzed_zapisu_liczy_sie_jako_zero():
    """Review Focus 5."""
    stary_boost = PON_08 - timedelta(hours=2)
    assert rules.egg_progress_seconds(0, PON_08, stary_boost, PON_08 + timedelta(hours=4), CFG) == 4 * 3600


def test_jajko_czas_wstecz_nie_cofa_postepu():
    assert rules.egg_progress_seconds(7200, PON_08, None, PON_08 - timedelta(hours=1), CFG) == 7200


def test_egg_is_ready_i_pct():
    assert rules.egg_is_ready(48 * 3600, 48) is True
    assert rules.egg_is_ready(48 * 3600 - 1, 48) is False
    assert rules.egg_progress_pct(84 * 3600, 168) == 50.0
    assert rules.egg_progress_pct(200 * 3600, 168) == 100.0
    assert rules.egg_progress_pct(0, 168) == 0.0


def test_prawdziwy_PetConfig_jest_zgodny_z_regulami():
    """Atrapa _cfg() i PetConfig muszą mieć te same pola i liczby (integracja Task 4 + 6)."""
    from modules.pets.config import PetConfig
    cfg = PetConfig()
    for pole in ('decay_hours', 'night', 'health_drop_hours', 'health_regen_hours',
                 'egg_hours', 'start_egg_hours', 'boost', 'max_stars', 'stage_days', 'actions'):
        assert getattr(cfg, pole) == getattr(CFG, pole), pole
    wynik = rules.simulate(PELNY, cfg, PON_08, PON_08 + timedelta(hours=12))
    assert blisko(wynik.state.hunger, 50)
    assert rules.stage(PON_08, PON_08 + timedelta(days=30), cfg) == 'dziecko'
    assert rules.egg_progress_seconds(0, PON_08, None, PON_08 + timedelta(hours=1), cfg) == 3600


# --- dostępność akcji ---

def test_action_availability_dzien_pelny():
    can, reasons = rules.action_availability(PELNY, PON_08, CFG)
    assert can == {'feed': False, 'play': False, 'wash': False, 'heal': False, 'pat': True, 'wake': False}
    assert reasons == {'feed': 'najedzony', 'play': 'nie chce się bawić', 'wash': 'czysty',
                       'heal': 'zdrowy', 'wake': 'nie śpi'}


def test_action_availability_progi_80():
    stan = PetState(hunger=80, fun=80.1, clean=79.9)
    can, _ = rules.action_availability(stan, PON_08, CFG)
    assert can['feed'] is True and can['play'] is False and can['wash'] is True


def test_action_availability_leczenie():
    chory = PetState(health=60)
    can, reasons = rules.action_availability(chory, PON_08, CFG)
    assert can['heal'] is True
    can, reasons = rules.action_availability(chory, PON_08, CFG, last_heal_at=PON_08 - timedelta(hours=11))
    assert can['heal'] is False and reasons['heal'] == 'lek już podany'
    can, _ = rules.action_availability(chory, PON_08, CFG, last_heal_at=PON_08 - timedelta(hours=12))
    assert can['heal'] is True


def test_action_availability_spiacy_tylko_obudz():
    can, reasons = rules.action_availability(PetState(hunger=60), PON_23, CFG)
    assert can == {'feed': False, 'play': False, 'wash': False, 'heal': False, 'pat': False, 'wake': True}
    assert set(reasons.values()) == {'śpi'}


def test_action_availability_obudzony_w_nocy():
    stan = PetState(hunger=60, awake_until=PON_23 + timedelta(minutes=10))
    can, _ = rules.action_availability(stan, PON_23, CFG)
    assert can['feed'] is True and can['wake'] is False


def test_gestures_rosna_ze_stadium():
    g = rules.GESTURES_BY_STAGE
    assert g['maluch'] == ['jump', 'blink', 'sway']
    assert g['dziecko'] == ['jump', 'blink', 'sway', 'spin', 'wave']
    assert g['dorosly'] == ['jump', 'blink', 'sway', 'spin', 'wave', 'dance', 'flip']
    assert rules.ACTIONS == ('feed', 'play', 'wash', 'heal', 'pat', 'wake')
