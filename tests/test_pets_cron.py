"""Cron pupili: treść powiadomień, koszyk per użytkownik, przebieg tick (spec §2.9, §3.6)."""
from datetime import timedelta

import pytest

from tests.pets_helpers import T0, zaloz_profil, zaloz_pupila, zaloz_zmarlego, zaloz_jajko


def _cfg(**over):
    """Konfiguracja z WŁĄCZONĄ funkcją (cron respektuje pets_enabled i rollout — recenzja etapu 3)."""
    from modules.pets.config import PetConfig
    return PetConfig(**{'enabled': True, 'rollout_pct': 100, **over})


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
    k = collect_for_user(user, T0 + timedelta(hours=3), _cfg())   # zdrowie ≈ 28 → chory (3 → 2)
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
    # Flaga pod blokadą profilu (recenzja etapu 3): dwa równoległe przebiegi nie zrobią dwóch pushy o odejściu
    assert w_cronie.death_notified_at == T0 + timedelta(hours=80) and z_odczytu.death_notified_at == T0 + timedelta(hours=80)


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


# --- przebieg ---

@pytest.fixture
def maile_zebrane(monkeypatch):
    """Przechwytuje send_email_batch_sync (tak jak test_dostawa_cron); domyślnie wszystko „wysłane"."""
    skrzynka = {'wiadomosci': [], 'wynik': None}

    def _sync(messages):
        skrzynka['wiadomosci'].extend(messages)
        return skrzynka['wynik'] if skrzynka['wynik'] is not None else [True] * len(messages)

    monkeypatch.setattr('utils.email_sender.send_email_batch_sync', _sync)
    return skrzynka


def _dzwonek(user_id):
    from modules.notifications.models import Notification
    return Notification.query.filter_by(user_id=user_id, notification_type='pet_updates').all()


def test_tick_jeden_push_na_uzytkownika_i_wpis_w_dzwonku(app, db, make_user, maile_zebrane):
    """Review Focus 1 i 5: bez subskrypcji push i bez wiersza preferencji — wpis w dzwonku, zero wyjątków."""
    from modules.pets.notifications import run_tick
    user = make_user()
    zaloz_profil(user)
    a = zaloz_pupila(user, species='kotek', name='Mruczek', fun=0.0)
    b = zaloz_pupila(user, species='mis', name='Puszek', clean=0.0)
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert wynik['users'] == 1 and wynik['pushes'] == 1 and wynik['emails_prepared'] == 0
    wpisy = _dzwonek(user.id)
    assert len(wpisy) == 1 and 'Mruczek' in wpisy[0].body and 'Puszek' in wpisy[0].body
    assert wpisy[0].url == '/client/pupile' and wpisy[0].tag == 'pets'
    assert maile_zebrane['wiadomosci'] == []


def test_tick_drugi_raz_w_tej_samej_godzinie_nic_nie_dubluje(app, db, make_user, maile_zebrane):
    """Review Focus 4."""
    from modules.pets.notifications import run_tick
    user = make_user()
    zaloz_profil(user)
    zaloz_pupila(user, species='kotek', hunger=0.0, health=10.0)      # krytyczny → push + mail
    zaloz_jajko(user, now=T0 - timedelta(hours=200))
    with app.test_request_context():
        w1 = run_tick(now=T0, cfg=_cfg())
        w2 = run_tick(now=T0 + timedelta(minutes=20), cfg=_cfg())
    assert w1['pushes'] == 1 and w1['emails_prepared'] == 1
    assert w2['pushes'] == 0 and w2['emails_prepared'] == 0 and w2['users'] == 0
    assert len(_dzwonek(user.id)) == 1 and len(maile_zebrane['wiadomosci']) == 1


def test_tick_mail_tylko_krytyczny_odejscie_ratunkowe(app, db, make_user, maile_zebrane):
    from modules.pets.notifications import run_tick
    smutny = make_user()
    zaloz_profil(smutny)
    zaloz_pupila(smutny, fun=0.0)
    krytyczny = make_user()
    zaloz_profil(krytyczny)
    zaloz_pupila(krytyczny, name='Mruczek', hunger=0.0, health=10.0)
    zalobnik = make_user()
    zaloz_profil(zalobnik)
    zmarly = zaloz_zmarlego(zalobnik, name='Puszek', died_at=T0 - timedelta(hours=1))
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert wynik['users'] == 3 and wynik['pushes'] == 3 and wynik['emails_prepared'] == 2 and wynik['emails_sent'] == 2
    odbiorcy = sorted(m.recipients[0] for m in maile_zebrane['wiadomosci'])
    assert odbiorcy == sorted([krytyczny.email, zalobnik.email])
    assert zmarly.death_notified_at == T0 + timedelta(hours=1)


def test_tick_pet_updates_wylaczone_zero_wpisow_i_maili(app, db, make_user, maile_zebrane):
    from modules.notifications.models import NotificationPreference
    from modules.pets.notifications import run_tick
    user = make_user()
    zaloz_profil(user)
    db.session.add(NotificationPreference(user_id=user.id, pet_updates=False))
    db.session.commit()
    pet = zaloz_pupila(user, hunger=0.0, health=10.0)
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert wynik['users'] == 1 and wynik['pushes'] == 0 and wynik['emails_prepared'] == 0
    assert _dzwonek(user.id) == [] and maile_zebrane['wiadomosci'] == []
    assert pet.notify_level == 3            # poziom i tak zapisany — epizod liczy się niezależnie od kanału


def test_tick_kill_switch_maila(app, db, make_user, maile_zebrane):
    from modules.auth.models import Settings
    from modules.pets.notifications import run_tick
    from utils.email_manager import EmailManager
    import json
    Settings.set_value('email_notifications_config', json.dumps({'notify_pet_alert': False}), type='json')
    db.session.commit()
    EmailManager.clear_email_config_cache()
    user = make_user()
    zaloz_profil(user)
    zaloz_pupila(user, hunger=0.0, health=10.0)
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert wynik['pushes'] == 1 and wynik['emails_prepared'] == 0 and maile_zebrane['wiadomosci'] == []


def test_tick_nieudany_mail_ratunkowy_powtarza_sie_odejscie_nie(app, db, make_user, maile_zebrane):
    """Review Focus 3."""
    from modules.pets.notifications import run_tick
    maile_zebrane['wynik'] = [False]
    user = make_user()
    zaloz_profil(user)
    stary = zaloz_zmarlego(user, species='mis', died_at=T0 - timedelta(days=8), death_notified_at=T0 - timedelta(days=8))
    with app.test_request_context():
        w1 = run_tick(now=T0, cfg=_cfg())
    assert w1['emails_prepared'] == 1 and w1['emails_sent'] == 0
    assert stary.rescue_reminder_sent_at is None             # powtórka następnym przebiegiem
    maile_zebrane['wynik'] = None
    with app.test_request_context():
        w2 = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert w2['emails_sent'] == 1 and stary.rescue_reminder_sent_at == T0 + timedelta(hours=1)
    # odejście: mail może paść, ale push/dzwonek wyszły → oznaczone
    maile_zebrane['wynik'] = [False]
    zalobnik = make_user()
    zaloz_profil(zalobnik)
    zmarly = zaloz_zmarlego(zalobnik, died_at=T0 + timedelta(hours=1))
    with app.test_request_context():
        run_tick(now=T0 + timedelta(hours=2), cfg=_cfg())
    assert zmarly.death_notified_at == T0 + timedelta(hours=2)


def test_tick_pomija_nieaktywnych_ale_obejmuje_adminow(app, db, make_user, maile_zebrane):
    """Ruling po recenzji: admin/mod mogą grać (pets_feature_for zawsze True), więc cron ich nie pomija."""
    from modules.pets.notifications import run_tick
    nieaktywny = make_user()
    zaloz_profil(nieaktywny)
    zaloz_pupila(nieaktywny, fun=0.0)
    nieaktywny.is_active = False
    admin = make_user(role='admin')
    zaloz_profil(admin)
    zaloz_pupila(admin, fun=0.0)
    db.session.commit()
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert wynik['users'] == 1 and _dzwonek(nieaktywny.id) == [] and len(_dzwonek(admin.id)) == 1


def test_tick_dry_run_nic_nie_zapisuje(app, db, make_user, maile_zebrane):
    from modules.pets.notifications import run_tick
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0)
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=80), cfg=_cfg(), dry_run=True)
    assert wynik['dry_run'] is True and wynik['deaths'] == 1 and wynik['pushes'] == 0
    db.session.expire_all()
    assert pet.status == 'alive' and pet.notify_level == 0
    assert _dzwonek(user.id) == [] and maile_zebrane['wiadomosci'] == []


def test_prune_events_90_dni_z_wyjatkami(db, make_user):
    from modules.pets.notifications import prune_events
    from modules.pets.models import PetEvent
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user)
    stare = T0 - timedelta(days=91)
    for typ in ('feed', 'pat', 'light', 'warm', 'milestone', 'hatch_new', 'die', 'claim'):
        db.session.add(PetEvent(pet_id=pet.id, user_id=user.id, type=typ, created_at=stare))
    db.session.add(PetEvent(pet_id=pet.id, user_id=user.id, type='feed', created_at=T0 - timedelta(days=89)))
    db.session.commit()
    assert prune_events(T0) == 4
    zostaly = sorted(e.type for e in PetEvent.query.filter_by(pet_id=pet.id).all())
    assert zostaly == ['claim', 'die', 'feed', 'hatch_new', 'milestone']


def test_komenda_cli_pets_tick(app, db, make_user, maile_zebrane):
    from modules.auth.models import Settings
    user = make_user()
    zaloz_profil(user)
    zaloz_pupila(user, fun=0.0, now=T0 - timedelta(days=400))   # dawno temu → na pewno coś do zgłoszenia
    runner = app.test_cli_runner()
    # Bez flagi pets_enabled komenda jest kill-switchem: nic nie robi i mówi dlaczego (recenzja etapu 3)
    wylaczone = runner.invoke(args=['pets', 'tick'])
    assert wylaczone.exit_code == 0, wylaczone.output + str(wylaczone.exception)
    assert 'wyłączon' in wylaczone.output.lower() and _dzwonek(user.id) == []
    Settings.set_value('pets_enabled', 'true', type='boolean')
    Settings.set_value('pets_rollout_pct', 100, type='integer')
    db.session.commit()
    sucho = runner.invoke(args=['pets', 'tick', '--dry-run'])
    assert sucho.exit_code == 0, sucho.output + str(sucho.exception)
    assert 'dry-run' in sucho.output.lower() and _dzwonek(user.id) == []
    wynik = runner.invoke(args=['pets', 'tick'])
    assert wynik.exit_code == 0, wynik.output + str(wynik.exception)
    assert 'Użytkowników: 1' in wynik.output and 'błędy: 0' in wynik.output


# --- recenzja etapu 3 ---

def test_wyjatek_u_jednego_uzytkownika_nie_gubi_maili_innych(app, db, make_user, maile_zebrane, monkeypatch):
    """Important 1: izolacja per użytkownik; batch maili i porządki idą zawsze (finally)."""
    from modules.pets.notifications import run_tick
    from modules.pets.models import PetEvent
    from utils.push_manager import PushManager
    u1 = make_user()
    zaloz_profil(u1)
    p1 = zaloz_pupila(u1, name='Pierwszy', hunger=0.0, health=10.0)    # krytyczny → push + mail
    u2 = make_user()
    zaloz_profil(u2)
    zaloz_pupila(u2, name='Drugi', fun=0.0)
    u3 = make_user()
    zaloz_profil(u3)
    zaloz_pupila(u3, name='Trzeci', fun=0.0)
    db.session.add(PetEvent(pet_id=p1.id, user_id=u1.id, type='feed', created_at=T0 - timedelta(days=100)))
    db.session.commit()
    oryginal = PushManager.send_to_user

    def wybuch(user_id, *a, **kw):
        if user_id == u2.id:
            raise RuntimeError('awaria push')
        return oryginal(user_id, *a, **kw)

    monkeypatch.setattr(PushManager, 'send_to_user', staticmethod(wybuch))
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert wynik['errors'] == 1
    assert wynik['emails_sent'] == 1 and [m.recipients[0] for m in maile_zebrane['wiadomosci']] == [u1.email]
    assert len(_dzwonek(u1.id)) == 1 and len(_dzwonek(u3.id)) == 1     # trzeci nie ucierpiał
    assert wynik['pruned'] == 1                                          # porządki mimo błędu


def test_flaga_wylaczona_cron_milczy(app, db, make_user, maile_zebrane):
    """Important 2 (opcja b): kill-switch funkcji zatrzymuje też cron."""
    from modules.pets.notifications import run_tick
    user = make_user()
    zaloz_profil(user)
    zaloz_pupila(user, hunger=0.0, health=10.0)
    with app.test_request_context():
        wynik = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg(enabled=False))
    assert wynik['skipped_disabled'] is True and wynik['users'] == 0 and wynik['pushes'] == 0
    assert _dzwonek(user.id) == [] and maile_zebrane['wiadomosci'] == []


def test_rollout_filtruje_uzytkownikow_crona(app, db, make_user):
    from modules.pets.notifications import users_to_check
    a = make_user()
    zaloz_profil(a)
    zaloz_pupila(a, fun=0.0)
    b = make_user(role='mod')
    zaloz_profil(b)
    zaloz_pupila(b, fun=0.0)
    assert [u.id for u in users_to_check(T0, _cfg(rollout_pct=0))] == [b.id]      # mod zawsze, klient poza rolloutem
    assert {u.id for u in users_to_check(T0, _cfg(rollout_pct=100))} == {a.id, b.id}


def test_przypomnienie_o_ratunkowym_pomijane_przy_wylaczonej_preferencji(app, db, make_user, maile_zebrane):
    """Minor 2: użytkownik bez maili nie ma krążyć co godzinę w koszyku."""
    from modules.notifications.models import NotificationPreference
    from modules.pets.notifications import run_tick
    user = make_user()
    zaloz_profil(user)
    db.session.add(NotificationPreference(user_id=user.id, pet_updates=False))
    db.session.commit()
    stary = zaloz_zmarlego(user, died_at=T0 - timedelta(days=8), death_notified_at=T0 - timedelta(days=8))
    with app.test_request_context():
        run_tick(now=T0, cfg=_cfg())
        w2 = run_tick(now=T0 + timedelta(hours=1), cfg=_cfg())
    assert stary.rescue_reminder_sent_at == T0 and w2['users'] == 0 and maile_zebrane['wiadomosci'] == []


def test_krytyczny_po_wyzdrowieniu_i_nowym_epizodzie(db, make_user):
    """Review Focus 2 na poziomie krytycznym: 3 → zdrowy (reset) → smutny → alert od nowa."""
    from modules.pets.notifications import collect_for_user, LEVEL_CRITICAL, LEVEL_SAD
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=0.0, health=10.0)
    assert collect_for_user(user, T0 + timedelta(minutes=5), _cfg())['alerts'] == [(pet, LEVEL_CRITICAL)]
    db.session.commit()
    pet.hunger = pet.fun = pet.clean = 100.0
    pet.health = 100.0
    pet.state_at = T0 + timedelta(hours=1)
    db.session.commit()
    assert collect_for_user(user, T0 + timedelta(hours=2), _cfg())['alerts'] == [] and pet.notify_level == 0
    db.session.commit()
    pet.fun = 0.0
    pet.state_at = T0 + timedelta(hours=3)
    db.session.commit()
    assert collect_for_user(user, T0 + timedelta(hours=4), _cfg())['alerts'] == [(pet, LEVEL_SAD)]


def test_mail_o_odejsciu_nie_dubluje_gatunku_i_zgadza_rodzaj(app, db, make_user):
    """Important 3: „Wiewiórka Wiewiórka był…" → „Pupil Wiewiórka był…"; nazwany: „Pupil Mruczek (Kotek)"."""
    from modules.pets.notifications import build_email_message
    user = make_user()
    zaloz_profil(user)
    domyslny = zaloz_zmarlego(user, species='wiewiorka', name='Wiewiórka', hatched_at=T0 - timedelta(days=10), stars=1)
    with app.test_request_context():
        msg = build_email_message(user, _koszyk(user, deaths=[domyslny]))
    for tresc in (msg.html, msg.body):
        assert 'Wiewiórka Wiewiórka' not in tresc
        assert 'Pupil Wiewiórka był z Tobą' in tresc
        assert '1 gwiazdkę' in tresc
    nazwany = zaloz_zmarlego(user, species='kotek', name='Mruczek', hatched_at=T0 - timedelta(days=10))
    with app.test_request_context():
        msg = build_email_message(user, _koszyk(user, deaths=[nazwany]))
    assert 'Pupil Mruczek (Kotek) był z Tobą' in msg.html and 'Pupil Mruczek (Kotek) był z Tobą' in msg.body


def test_mail_liczba_mnoga_i_powitanie_bez_imienia(app, db, make_user):
    from modules.pets.notifications import build_email_message, LEVEL_CRITICAL
    user = make_user(first_name=None)
    zaloz_profil(user)
    a = zaloz_pupila(user, species='kotek', name='A', health=10.0)
    b = zaloz_pupila(user, species='mis', name='B', health=10.0)
    with app.test_request_context():
        msg = build_email_message(user, _koszyk(user, alerts=[(a, LEVEL_CRITICAL), (b, LEVEL_CRITICAL)]))
    assert 'odejdą do gwiazd' in msg.html and 'odejdą do gwiazd' in msg.body
    assert 'Cześć !' not in msg.body and 'Cześć!' in msg.body
