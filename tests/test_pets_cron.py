"""Cron pupili: treść powiadomień, koszyk per użytkownik, przebieg tick (spec §2.9, §3.6)."""
from datetime import timedelta

import pytest

from tests.pets_helpers import T0, zaloz_profil, zaloz_pupila, zaloz_zmarlego, zaloz_jajko


def _cfg(**over):
    from modules.pets.config import PetConfig
    return PetConfig(**over)


def _koszyk(user, **pola):
    koszyk = dict(user=user, alerts=[], deaths=[], eggs_ready=[], monthly=False, rescue_reminders=[])
    koszyk.update(pola)
    return koszyk


# --- treść ---

def test_level_of_z_nastroju():
    from modules.pets import rules
    from modules.pets.notifications import level_of, LEVEL_SAD, LEVEL_SICK, LEVEL_CRITICAL
    assert level_of(rules.PetState()) == 0
    assert level_of(rules.PetState(hunger=40)) == 0            # głodny, ale bez zera i zdrowy
    assert level_of(rules.PetState(fun=0)) == LEVEL_SAD
    assert level_of(rules.PetState(fun=0, health=60)) == LEVEL_SICK
    assert level_of(rules.PetState(health=10)) == LEVEL_CRITICAL


def test_push_zbiorczy_tekst(db, make_user):
    from modules.pets.notifications import build_push_text, LEVEL_SICK, LEVEL_SAD
    user = make_user()
    zaloz_profil(user)
    a = zaloz_pupila(user, species='kotek', name='Mruczek')
    b = zaloz_pupila(user, species='mis', name='Wiewiórka')
    zmarly = zaloz_zmarlego(user, species='piesek', name='Puszek')
    jajko = zaloz_jajko(user)
    tytul, tresc = build_push_text(_koszyk(user, alerts=[(a, LEVEL_SICK), (b, LEVEL_SAD)], deaths=[zmarly],
                                           eggs_ready=[jajko], monthly=True))
    assert tytul == 'Twoje pupile'
    assert 'Pupil Mruczek jest chory.' in tresc
    assert 'Pupil Wiewiórka jest smutny.' in tresc       # podmiot „pupil" — rodzaj zawsze się zgadza
    assert 'Pupil Puszek odszedł do gwiazd.' in tresc
    assert 'Jajko gotowe do wyklucia!' in tresc and 'Czeka na Ciebie nowe jajko!' in tresc
    assert len(tresc) <= 200


def test_push_pusty_koszyk_i_dwa_jajka(db, make_user):
    from modules.pets.notifications import build_push_text, basket_is_empty
    user = make_user()
    zaloz_profil(user)
    assert basket_is_empty(_koszyk(user)) is True
    assert build_push_text(_koszyk(user)) == ('Twoje pupile', '')
    j1, j2 = zaloz_jajko(user), zaloz_jajko(user)
    _, tresc = build_push_text(_koszyk(user, eggs_ready=[j1, j2]))
    assert '2 jajka gotowe do wyklucia!' in tresc


def test_needs_email_tylko_krytyczny_odejscie_ratunkowe(db, make_user):
    from modules.pets.notifications import needs_email, LEVEL_SICK, LEVEL_CRITICAL
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user)
    assert needs_email(_koszyk(user, alerts=[(pet, LEVEL_SICK)], eggs_ready=[pet], monthly=True)) is False
    assert needs_email(_koszyk(user, alerts=[(pet, LEVEL_CRITICAL)])) is True
    assert needs_email(_koszyk(user, deaths=[pet])) is True
    assert needs_email(_koszyk(user, rescue_reminders=[pet])) is True


def test_build_email_message_renderuje_szablony(app, db, make_user):
    from modules.pets.notifications import build_email_message, LEVEL_CRITICAL
    from modules.admin.models import EmailLog
    user = make_user(first_name='Ania')
    zaloz_profil(user)
    krytyczny = zaloz_pupila(user, species='kotek', name='Mruczek', health=10.0)
    zmarly = zaloz_zmarlego(user, species='mis', name='Puszek', hatched_at=T0 - timedelta(days=40),
                            care_days=33, stars=2)
    ratunkowy = zaloz_zmarlego(user, species='piesek', name='Reksio', died_at=T0 - timedelta(days=8))
    with app.test_request_context():
        msg = build_email_message(user, _koszyk(user, alerts=[(krytyczny, LEVEL_CRITICAL)], deaths=[zmarly],
                                                rescue_reminders=[ratunkowy]))
    assert msg is not None and msg.recipients == [user.email]
    assert msg.subject == 'Pupil Puszek odszedł do gwiazd'
    for fragment in ('Ania', 'Mruczek', 'Stan krytyczny', 'Puszek', '40 dni', '33', 'Reksio', '/client/pupile'):
        assert fragment in msg.html, fragment
        assert fragment in msg.body, fragment
    assert 'zmarł' not in msg.html.lower() and 'umarł' not in msg.html.lower()
    assert EmailLog.query.filter_by(template='pets_alert').count() == 1


def test_temat_maila_wedlug_wagi(app, db, make_user):
    from modules.pets.notifications import build_email_message, LEVEL_CRITICAL
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, name='Mruczek', health=10.0)
    ratunkowy = zaloz_zmarlego(user, name='Reksio', died_at=T0 - timedelta(days=8))
    with app.test_request_context():
        assert build_email_message(user, _koszyk(user, alerts=[(pet, LEVEL_CRITICAL)])).subject == \
            'Pupil Mruczek potrzebuje pomocy — stan krytyczny'
        assert build_email_message(user, _koszyk(user, rescue_reminders=[ratunkowy])).subject == \
            'Jajko ratunkowe czeka na odebranie'
        assert build_email_message(user, _koszyk(user)) is None


# --- koszyk ---

def test_poziom_raz_na_epizod_i_reset(db, make_user):
    """Review Focus 2: nakarmiony między przebiegami nie dostaje spóźnionego alertu."""
    from modules.pets.notifications import collect_for_user, LEVEL_SAD, LEVEL_SICK
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, fun=0.0)                        # od T0 zdrowie spada
    k1 = collect_for_user(user, T0 + timedelta(hours=1), _cfg())
    db.session.commit()
    assert k1['alerts'] == [(pet, LEVEL_SAD)] and pet.notify_level == LEVEL_SAD
    k2 = collect_for_user(user, T0 + timedelta(hours=2), _cfg())    # nadal smutny — bez powtórki
    db.session.commit()
    assert k2['alerts'] == []
    k3 = collect_for_user(user, T0 + timedelta(hours=30), _cfg())   # zdrowie ~58 → chory
    db.session.commit()
    assert k3['alerts'] == [(pet, LEVEL_SICK)] and pet.notify_level == LEVEL_SICK
    # użytkownik zadbał: paski pełne, zdrowie wraca; epizod się kończy
    pet.fun = pet.hunger = pet.clean = 100.0
    pet.health = 80.0
    pet.state_at = T0 + timedelta(hours=31)
    db.session.commit()
    k4 = collect_for_user(user, T0 + timedelta(hours=32), _cfg())
    db.session.commit()
    assert k4['alerts'] == [] and pet.notify_level == 0
    # nowy epizod po resecie znów alarmuje od „smutny"
    pet.fun = 0.0
    pet.state_at = T0 + timedelta(hours=33)
    db.session.commit()
    assert collect_for_user(user, T0 + timedelta(hours=34), _cfg())['alerts'] == [(pet, LEVEL_SAD)]


def test_poziom_nie_spada_w_dol_bez_wyzdrowienia(db, make_user):
    from modules.pets.notifications import collect_for_user, LEVEL_CRITICAL
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0, health=20.0)       # krytyczny
    collect_for_user(user, T0 + timedelta(minutes=5), _cfg())
    db.session.commit()
    assert pet.notify_level == LEVEL_CRITICAL
    pet.hunger = 60.0                                         # nakarmiony raz, zdrowie wciąż 20
    pet.state_at = T0 + timedelta(hours=1)
    db.session.commit()
    k = collect_for_user(user, T0 + timedelta(hours=2), _cfg())
    assert k['alerts'] == [] and pet.notify_level == LEVEL_CRITICAL


def test_odejscie_w_cronie_i_odejscie_z_odczytu(db, make_user):
    from modules.pets.notifications import collect_for_user
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user)
    w_cronie = zaloz_pupila(user, species='kotek', hunger=0.0)
    z_odczytu = zaloz_zmarlego(user, species='mis', died_at=T0 - timedelta(hours=1))   # death_notified_at None
    k = collect_for_user(user, T0 + timedelta(hours=80), _cfg())
    db.session.commit()
    assert {p.id for p in k['deaths']} == {w_cronie.id, z_odczytu.id}
    assert w_cronie.status == 'dead' and w_cronie.died_at == T0 + timedelta(hours=72)
    assert PetEvent.query.filter_by(pet_id=w_cronie.id, type='die').count() == 1
    assert w_cronie.death_notified_at is None     # oznacza dopiero przebieg po wysyłce


def test_jajko_gotowe_i_miesieczne_raz(db, make_user):
    from modules.pets.notifications import collect_for_user
    user = make_user()
    profil = zaloz_profil(user, now=T0 - timedelta(days=31))
    jajko = zaloz_jajko(user, now=T0 - timedelta(hours=200))
    k1 = collect_for_user(user, T0, _cfg())
    db.session.commit()
    assert k1['eggs_ready'] == [jajko] and k1['monthly'] is True
    assert jajko.egg_ready_notified_at == T0 and profil.monthly_notified_at == T0
    k2 = collect_for_user(user, T0 + timedelta(hours=1), _cfg())
    assert k2['eggs_ready'] == [] and k2['monthly'] is False


def test_miesieczne_po_odbiorze_znow_powiadamia_po_30_dniach(db, make_user):
    from modules.pets.eggs import claim_egg
    from modules.pets.notifications import collect_for_user
    user = make_user()
    profil = zaloz_profil(user, now=T0 - timedelta(days=31))
    collect_for_user(user, T0, _cfg())
    db.session.commit()
    claim_egg(user, 'monthly', now=T0, cfg=_cfg())            # czyści monthly_notified_at
    assert profil.monthly_notified_at is None
    assert collect_for_user(user, T0 + timedelta(days=29), _cfg())['monthly'] is False
    assert collect_for_user(user, T0 + timedelta(days=30), _cfg())['monthly'] is True


def test_przypomnienie_o_ratunkowym_po_7_dniach(db, make_user):
    from modules.pets.notifications import collect_for_user
    user = make_user()
    zaloz_profil(user)
    swiezy = zaloz_zmarlego(user, species='kotek', died_at=T0 - timedelta(days=6), death_notified_at=T0 - timedelta(days=6))
    stary = zaloz_zmarlego(user, species='mis', died_at=T0 - timedelta(days=8), death_notified_at=T0 - timedelta(days=8))
    odebrany = zaloz_zmarlego(user, species='piesek', died_at=T0 - timedelta(days=9), death_notified_at=T0 - timedelta(days=9),
                              rescue_egg_claimed_at=T0 - timedelta(days=8))
    k = collect_for_user(user, T0, _cfg())
    assert k['rescue_reminders'] == [stary] and k['deaths'] == []


def test_bez_profilu_koszyk_pusty(db, make_user):
    from modules.pets.notifications import collect_for_user, basket_is_empty
    user = make_user()
    assert basket_is_empty(collect_for_user(user, T0, _cfg()))
