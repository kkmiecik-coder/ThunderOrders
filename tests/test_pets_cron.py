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
