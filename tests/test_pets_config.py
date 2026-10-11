# tests/test_pets_config.py
"""PetConfig: domyślne liczby ze specu, nadpisania z Settings, bramka rolloutu."""
import json
from types import SimpleNamespace

import pytest


def _ustaw(db, key, value, typ):
    from modules.auth.models import Settings
    Settings.set_value(key, value, type=typ)
    db.session.commit()


def test_domyslne_liczby_ze_specu():
    from modules.pets.config import PetConfig
    cfg = PetConfig()
    assert cfg.enabled is False and cfg.rollout_pct == 0
    assert cfg.decay_hours == {'hunger': 24, 'fun': 30, 'clean': 48}
    assert cfg.night == {'start': 23, 'end': 7, 'factor': 0.25}
    assert (cfg.health_drop_hours, cfg.health_regen_hours) == (72, 24)
    assert (cfg.egg_hours, cfg.start_egg_hours) == (168, 48)
    assert cfg.boost == {'hours': 8, 'factor': 2}
    assert (cfg.monthly_days, cfg.rescue_hours, cfg.rescue_reminder_days) == (30, 0, 7)
    assert (cfg.pity_after, cfg.max_stars) == (2, 5)
    assert cfg.stage_days == {'child': 24, 'adult': 80}
    assert cfg.actions == {'feed': 50, 'play': 50, 'heal': 40, 'heal_cooldown_h': 12,
                           'allow_below': 80, 'pat_gain': 0.25, 'pat_per_hour': 60,
                           'wake_penalty': 10, 'awake_minutes': 20}


def test_load_bez_wierszy_daje_domyslne(app):
    from modules.pets.config import PetConfig
    assert PetConfig.load(force=True) == PetConfig()


def test_nadpisanie_integer_i_boolean(db):
    from modules.pets.config import PetConfig
    _ustaw(db, 'pets_egg_hours', 100, 'integer')
    _ustaw(db, 'pets_enabled', 'true', 'boolean')
    cfg = PetConfig.load(force=True)
    assert cfg.egg_hours == 100
    assert cfg.enabled is True
    assert cfg.start_egg_hours == 48  # nietknięte


def test_nadpisanie_json_scala_sie_z_domyslnymi(db):
    from modules.pets.config import PetConfig
    _ustaw(db, 'pets_decay_hours', json.dumps({'hunger': 12}), 'json')
    cfg = PetConfig.load(force=True)
    assert cfg.decay_hours == {'hunger': 12, 'fun': 30, 'clean': 48}


def test_load_cache_w_g_i_force(db):
    from modules.pets.config import PetConfig
    pierwszy = PetConfig.load(force=True)
    _ustaw(db, 'pets_monthly_days', 45, 'integer')
    assert PetConfig.load().monthly_days == pierwszy.monthly_days  # cache
    assert PetConfig.load(force=True).monthly_days == 45


def test_niepoprawny_json_nie_wywraca_i_daje_domyslne(db, caplog):
    """Review Focus 1: str(dict) z apostrofami — pułapka Settings.set_value."""
    from modules.pets.config import PetConfig
    _ustaw(db, 'pets_boost', str({'hours': 4, 'factor': 3}), 'json')
    cfg = PetConfig.load(force=True)
    assert cfg.boost == {'hours': 8, 'factor': 2}
    assert any('pets_boost' in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize('key,value,typ', [
    ('pets_egg_hours', -5, 'integer'),
    ('pets_rollout_pct', 150, 'integer'),
    ('pets_night', json.dumps({'start': 23, 'end': 7, 'factor': 1.5}), 'json'),
    ('pets_decay_hours', json.dumps({'hunger': 0}), 'json'),
    ('pets_decay_hours', json.dumps([24, 30, 48]), 'json'),
])
def test_wartosci_poza_zakresem_sa_ignorowane(db, key, value, typ):
    from modules.pets.config import PetConfig
    _ustaw(db, key, value, typ)
    assert PetConfig.load(force=True) == PetConfig()


def test_nieznany_klucz_pets_jest_ignorowany(db):
    from modules.pets.config import PetConfig
    _ustaw(db, 'pets_foo', 1, 'integer')
    assert PetConfig.load(force=True) == PetConfig()


# --- bramka funkcji / rollout ---

def _user(id, role='client', auth=True):
    return SimpleNamespace(id=id, role=role, is_authenticated=auth)


def test_funkcja_wylaczona_dla_wszystkich_gdy_flaga_off(db):
    from modules.pets.config import pets_feature_for, reset_feature_cache
    reset_feature_cache()
    assert pets_feature_for(_user(1, 'admin')) is False
    assert pets_feature_for(_user(2)) is False


def test_rollout_procentowy_po_user_id(db):
    from modules.pets.config import pets_feature_for, reset_feature_cache
    _ustaw(db, 'pets_enabled', 'true', 'boolean')
    _ustaw(db, 'pets_rollout_pct', 50, 'integer')
    reset_feature_cache()
    assert pets_feature_for(_user(10)) is True     # 10 % 100 = 10 < 50
    assert pets_feature_for(_user(160)) is False   # 160 % 100 = 60 >= 50
    assert pets_feature_for(_user(999, 'admin')) is True   # admin zawsze
    assert pets_feature_for(_user(999, 'mod')) is True


def test_rollout_0_i_100(db):
    from modules.pets.config import pets_feature_for, reset_feature_cache
    _ustaw(db, 'pets_enabled', 'true', 'boolean')
    _ustaw(db, 'pets_rollout_pct', 0, 'integer')
    reset_feature_cache()
    assert pets_feature_for(_user(1)) is False
    assert pets_feature_for(_user(1, 'admin')) is True
    _ustaw(db, 'pets_rollout_pct', 100, 'integer')
    reset_feature_cache()
    assert pets_feature_for(_user(199)) is True


def test_anonim_i_none_nie_maja_dostepu(db):
    from modules.pets.config import pets_feature_for, reset_feature_cache
    _ustaw(db, 'pets_enabled', 'true', 'boolean')
    _ustaw(db, 'pets_rollout_pct', 100, 'integer')
    reset_feature_cache()
    assert pets_feature_for(None) is False
    assert pets_feature_for(_user(5, auth=False)) is False


def test_cache_flag_wymaga_resetu(db):
    from modules.pets.config import feature_flags, reset_feature_cache
    reset_feature_cache()
    assert feature_flags() == (False, 0)
    _ustaw(db, 'pets_enabled', 'true', 'boolean')
    _ustaw(db, 'pets_rollout_pct', 25, 'integer')
    assert feature_flags() == (False, 0)      # jeszcze z cache (TTL 10 s)
    reset_feature_cache()
    assert feature_flags() == (True, 25)
