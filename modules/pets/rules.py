"""Czysta matematyka stanu pupila. ZERO importów z Flaska / SQLAlchemy.

Spec: docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md §2.4–2.7, §3.1

Stan „na teraz" = simulate(stan_z_bazy, cfg, state_at, teraz). Czas jest zawsze parametrem
(aware UTC, jak w całej aplikacji) — tu nie odczytujemy zegara.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

STEP_SECONDS = 300          # krok symulacji: 5 minut
BARS = ('hunger', 'fun', 'clean')
HUNGRY_BELOW = 30           # głodny → budzi się w nocy
SICK_BELOW = 75             # chory → budzi się, może iść do szpitala (spec v3 §4)
CRITICAL_BELOW = 25
HAPPY_FROM = 50             # wszystkie paski ≥ 50 = szczęśliwy; > 50 = regeneracja zdrowia


@dataclass(frozen=True)
class PetState:
    hunger: float = 100.0
    fun: float = 100.0
    clean: float = 100.0
    health: float = 100.0
    stars: int = 0
    awake_until: datetime | None = None


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(v)))


def clamp_state(state):
    """Paski i zdrowie przycięte do 0–100 (dane z bazy mogą być brudne)."""
    return replace(
        state,
        hunger=_clamp(state.hunger), fun=_clamp(state.fun),
        clean=_clamp(state.clean), health=_clamp(state.health),
        stars=max(0, int(state.stars or 0)),
    )


# ---------------------------------------------------------------------------
# Noc i sen
# ---------------------------------------------------------------------------

def is_night(dt, cfg):
    """Noc wg konfiguracji (domyślnie 23:00–07:00). start == end → brak nocy."""
    start = int(cfg.night['start'])
    end = int(cfg.night['end'])
    if start == end:
        return False
    godzina = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    if start > end:                      # okno przez północ, np. 23 → 7
        return godzina >= start or godzina < end
    return start <= godzina < end        # okno w obrębie doby, np. 1 → 5


def wake_reasons(state, dt):
    """Dlaczego pupil NIE śpi mimo nocy (kolejność stała — testy na niej polegają)."""
    powody = []
    if state.hunger < HUNGRY_BELOW:
        powody.append('hungry')
    if any(getattr(state, bar) <= 0 for bar in BARS):
        powody.append('zero')
    if state.health < SICK_BELOW:
        powody.append('sick')
    if state.awake_until is not None and dt < state.awake_until:
        powody.append('woken')
    return tuple(powody)


def is_asleep(state, dt, cfg):
    return is_night(dt, cfg) and not wake_reasons(state, dt)


# ---------------------------------------------------------------------------
# Tempo zmian
# ---------------------------------------------------------------------------

def decay_multiplier(state, dt, cfg):
    """Mnożnik spadku pasków: sen ×factor (0,25), każda gwiazdka −10 % (do max_stars)."""
    gwiazdki = min(max(int(state.stars or 0), 0), int(cfg.max_stars))
    mnoznik_gwiazdek = 1.0 - 0.1 * gwiazdki
    mnoznik_snu = float(cfg.night['factor']) if is_asleep(state, dt, cfg) else 1.0
    return mnoznik_snu * mnoznik_gwiazdek


def rates_per_hour(state, dt, cfg):
    """Zmiana na godzinę dla każdego paska i zdrowia w chwili dt (ujemne = spadek).

    Paski: liniowo 100 → 0 w decay_hours[bar] godzin × mnożnik. Pasek na zerze już nie spada.
    Zdrowie: −100/health_drop_hours gdy KTÓRYKOLWIEK pasek = 0 (bez spowolnienia nocnego);
    +100/health_regen_hours gdy WSZYSTKIE paski > 50 i zdrowie < 100; inaczej 0.
    """
    mnoznik = decay_multiplier(state, dt, cfg)
    tempo = {}
    for bar in BARS:
        wartosc = getattr(state, bar)
        tempo[bar] = 0.0 if wartosc <= 0 else -(100.0 / float(cfg.decay_hours[bar])) * mnoznik

    jakis_na_zerze = any(getattr(state, bar) <= 0 for bar in BARS)
    wszystkie_ponad = all(getattr(state, bar) > HAPPY_FROM for bar in BARS)
    if jakis_na_zerze:
        tempo['health'] = -(100.0 / float(cfg.health_drop_hours)) if state.health > 0 else 0.0
    elif wszystkie_ponad and state.health < 100:
        tempo['health'] = 100.0 / float(cfg.health_regen_hours)
    else:
        tempo['health'] = 0.0
    return tempo


# ---------------------------------------------------------------------------
# Symulacja krokami co 5 minut
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SimResult:
    state: PetState
    died_at: datetime | None
    discharged_at: datetime | None = None   # auto-wypis ze szpitala wyliczony w trakcie symulacji (spec v3 §4.1)


def _advance(state, tempo, godziny):
    """Liniowy ruch wszystkich wartości o `godziny` przy zadanym tempie, z klamrą 0–100."""
    return replace(
        state,
        hunger=_clamp(state.hunger + tempo['hunger'] * godziny),
        fun=_clamp(state.fun + tempo['fun'] * godziny),
        clean=_clamp(state.clean + tempo['clean'] * godziny),
        health=_clamp(state.health + tempo['health'] * godziny),
    )


def simulate(state, cfg, from_dt, to_dt):
    """Stan w chwili to_dt, licząc od stanu zapisanego w from_dt.

    Kroki co STEP_SECONDS od from_dt (siatka startuje w from_dt → odczyty bez akcji są
    spójne), ostatni krok ułamkowy. elapsed klamrowane do ≥ 0 (zmiana czasu 25.10 cofa
    zegar). Odejście: zdrowie dobija do 0 → died_at interpolowane liniowo wewnątrz kroku,
    stan zamrożony ze zdrowiem 0. Pupil już martwy na wejściu nie ożywa (died_at=None —
    tę datę zna baza).
    """
    state = clamp_state(state)
    elapsed = max(0.0, (to_dt - from_dt).total_seconds())
    if elapsed == 0.0 or state.health <= 0.0:
        return SimResult(state, None)

    dt = from_dt
    pozostalo = elapsed
    while pozostalo > 1e-9:
        krok = min(float(STEP_SECONDS), pozostalo)
        tempo = rates_per_hour(state, dt, cfg)
        godziny = krok / 3600.0
        nowy = _advance(state, tempo, godziny)
        if nowy.health <= 0.0:
            spadek_na_h = -tempo['health']          # > 0, bo zdrowie spadło
            died_at = dt + timedelta(hours=state.health / spadek_na_h)
            return SimResult(replace(nowy, health=0.0), died_at)
        state = nowy
        dt = dt + timedelta(seconds=krok)
        pozostalo -= krok
    return SimResult(state, None)


# ---------------------------------------------------------------------------
# Szpital (spec v3 §4.1, §4.4) — analitycznie, bez kroków
# ---------------------------------------------------------------------------

def _tesknota_na_h(state, cfg):
    gwiazdki = min(max(int(state.stars or 0), 0), int(cfg.max_stars))
    return (100.0 / float(cfg.decay_hours['fun'])) * (1.0 - 0.1 * gwiazdki)


def hospital_state(state, cfg, from_dt, to_dt, healed_at):
    """Stan w szpitalu w chwili to_dt (wołający pilnuje, by to_dt ≤ auto-wypis).

    Sytość i czystość stoją. Zdrowie rośnie liniowo od stanu w from_dt do 100 w healed_at
    (healed_at ustalone przy przyjęciu, więc zapis stanu w trakcie pobytu niczego nie przesuwa).
    Radość stoi do healed_at, potem spada (tęsknota) bez nocnego spowolnienia. Brak odejścia.
    """
    state = clamp_state(state)
    if to_dt <= from_dt:
        return state
    if to_dt >= healed_at or healed_at <= from_dt:
        zdrowie = 100.0
    else:
        udzial = (to_dt - from_dt).total_seconds() / (healed_at - from_dt).total_seconds()
        zdrowie = state.health + (100.0 - state.health) * udzial
    start_tesknoty = max(from_dt, healed_at)
    radosc = state.fun
    if to_dt > start_tesknoty:
        godziny = (to_dt - start_tesknoty).total_seconds() / 3600.0
        radosc = state.fun - _tesknota_na_h(state, cfg) * godziny
    return replace(state, health=_clamp(zdrowie), fun=_clamp(radosc))


def hospital_rates(state, cfg, now, healed_at):
    """Tempo na godzinę w szpitalu (do ekstrapolacji pasków w JS)."""
    tempo = {'hunger': 0.0, 'fun': 0.0, 'clean': 0.0, 'health': 0.0}
    if now < healed_at and state.health < 100:
        tempo['health'] = (100.0 - state.health) / ((healed_at - now).total_seconds() / 3600.0)
    if now >= healed_at and state.fun > 0:
        tempo['fun'] = -_tesknota_na_h(state, cfg)
    return tempo


# ---------------------------------------------------------------------------
# Nastrój i stadium
# ---------------------------------------------------------------------------

_NASTROJ_PASKA = {'hunger': 'glodny', 'fun': 'znudzony', 'clean': 'brudny'}


def mood(state):
    """Jedna etykieta, pierwsza pasująca od góry (spec §2.6)."""
    if state.health < CRITICAL_BELOW:
        return 'krytyczny'
    if state.health < SICK_BELOW:
        return 'chory'
    if any(getattr(state, bar) <= 0 for bar in BARS):
        return 'smutny'
    najnizszy = min(BARS, key=lambda bar: getattr(state, bar))
    if getattr(state, najnizszy) < HAPPY_FROM:
        return _NASTROJ_PASKA[najnizszy]
    return 'szczesliwy'


STAGES = ('maluch', 'dziecko', 'dorosly')


def age_days(hatched_at, now):
    return int(max(0.0, (now - hatched_at).total_seconds()) // 86400)


def stage(hatched_at, now, cfg):
    """Stadium z czasu kalendarzowego od wyklucia: 0–24 maluch, 24–80 dziecko, 80+ dorosły."""
    dni = max(0.0, (now - hatched_at).total_seconds()) / 86400.0
    if dni >= float(cfg.stage_days['adult']):
        return 'dorosly'
    if dni >= float(cfg.stage_days['child']):
        return 'dziecko'
    return 'maluch'


# ---------------------------------------------------------------------------
# Jajko (analitycznie, bez kroków)
# ---------------------------------------------------------------------------

def egg_progress_seconds(progress_sec, progress_at, boost_until, now, cfg):
    """Postęp inkubacji: zapisany + czas od zapisu, przy czym odcinek do boost_until liczy ×factor.

    boost_until sprzed progress_at (stary boost) daje 0 s przyspieszenia; czas wstecz daje 0.
    """
    elapsed = max(0.0, (now - progress_at).total_seconds())
    boosted = 0.0
    if boost_until is not None:
        boosted = min(elapsed, max(0.0, (boost_until - progress_at).total_seconds()))
    factor = float(cfg.boost['factor'])
    return float(progress_sec) + (elapsed - boosted) + boosted * factor


def egg_is_ready(progress_seconds, egg_hours):
    return progress_seconds >= float(egg_hours) * 3600.0


def egg_progress_pct(progress_seconds, egg_hours):
    calosc = float(egg_hours) * 3600.0
    if calosc <= 0:
        return 100.0
    return round(min(100.0, 100.0 * float(progress_seconds) / calosc), 1)


# ---------------------------------------------------------------------------
# Akcje: dostępność (spec §2.5) i gesty per stadium (§2.7)
# ---------------------------------------------------------------------------

ACTIONS = ('feed', 'play', 'wash', 'pat', 'wake')
ACTION_VARIANTS = {
    'feed': ('miska', 'jablko', 'ciastko'),
    'play': ('pilka', 'wloczka', 'banki'),
    'wash': ('kapiel', 'prysznic', 'gabka'),
}

GESTURES_BY_STAGE = {
    'maluch': ['jump', 'blink', 'sway'],
    'dziecko': ['jump', 'blink', 'sway', 'spin', 'wave'],
    'dorosly': ['jump', 'blink', 'sway', 'spin', 'wave', 'dance', 'flip'],
}


def action_availability(state, now, cfg, in_hospital=False):
    """`can` + `reasons` (po polsku). Śpiący: tylko „Obudź”. W szpitalu: tylko pat. `admit` = przyjęcie do szpitala."""
    can, reasons = {}, {}

    def ustaw(akcja, ok, powod):
        can[akcja] = ok
        if not ok:
            reasons[akcja] = powod

    if in_hospital:
        for akcja in ('feed', 'play', 'wash'):
            ustaw(akcja, False, 'w szpitalu')
        ustaw('pat', True, '')
        ustaw('wake', False, 'nie śpi')
        ustaw('admit', False, 'już w szpitalu')
        return can, reasons

    if is_asleep(state, now, cfg):
        for akcja in ('feed', 'play', 'wash', 'pat'):
            ustaw(akcja, False, 'śpi')
        ustaw('wake', True, '')
        ustaw('admit', False, 'śpi')
        return can, reasons

    prog = float(cfg.actions['allow_below'])
    ustaw('feed', state.hunger <= prog, 'najedzony')
    ustaw('play', state.fun <= prog, 'nie chce się bawić')
    ustaw('wash', state.clean <= prog, 'czysty')
    ustaw('pat', True, '')
    ustaw('wake', False, 'nie śpi')
    ustaw('admit', state.health < SICK_BELOW, 'zdrowy')
    return can, reasons
