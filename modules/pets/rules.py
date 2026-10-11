"""Czysta matematyka stanu pupila. ZERO importów z Flaska / SQLAlchemy.

Spec: docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md §2.4–2.7, §3.1

Stan „na teraz" = simulate(stan_z_bazy, cfg, state_at, teraz). Czas jest zawsze parametrem
(naiwny czas polski, jak w całej aplikacji) — tu nie ma datetime.now().
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

STEP_SECONDS = 300          # krok symulacji: 5 minut
BARS = ('hunger', 'fun', 'clean')
HUNGRY_BELOW = 30           # głodny → budzi się w nocy
SICK_BELOW = 75             # chory → budzi się, dostępne „Wylecz"
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
