"""flask pets report (spec §3.7) — metryki na danych syntetycznych, bez dzielenia przez zero."""
from datetime import timedelta

from tests.pets_helpers import T0, zaloz_profil, zaloz_pupila, zaloz_zmarlego


def test_raport_pusta_baza_bez_wyjatkow(db):
    from modules.pets.report import build_report, format_report
    r = build_report(7, now=T0)
    assert r['funnel']['profiles'] == 0 and r['deaths']['per_100_alive'] is None
    assert 'Profile' in format_report(r)


def test_lejek_retencja_i_odejscia(db, make_user):
    from modules.pets.common import DEATH_CAUSE, add_event
    from modules.pets.report import build_report, format_report
    from modules.notifications.models import PushSubscription
    start = T0 - timedelta(days=10)
    # A: odebrał, wykluł, dba codziennie, ma push, pupil żyje
    a = make_user()
    zaloz_profil(a, now=start)
    pa = zaloz_pupila(a, now=start + timedelta(days=2))
    add_event(a.id, 'claim', start, pet_id=pa.id)
    add_event(a.id, 'hatch_new', start + timedelta(days=2), pet_id=pa.id)
    for d in range(1, 10):
        add_event(a.id, 'feed', start + timedelta(days=d, hours=9), pet_id=pa.id)
    db.session.add(PushSubscription(user_id=a.id, endpoint='e', p256dh_key='k', auth_key='a', is_active=True))
    # B: odebrał, wykluł, porzucił → pupil odszedł z głodu 3 dni temu, ratunkowe odebrane
    b = make_user()
    zaloz_profil(b, now=start)
    pb = zaloz_zmarlego(b, species='mis', died_at=T0 - timedelta(days=3), hatched_at=start + timedelta(days=2),
                        rescue_egg_claimed_at=T0 - timedelta(days=2))
    add_event(b.id, 'claim', start, pet_id=pb.id)
    add_event(b.id, 'hatch_new', start + timedelta(days=2), pet_id=pb.id)
    add_event(b.id, 'alert', T0 - timedelta(days=5), pet_id=pb.id, value=1)
    add_event(b.id, 'feed', T0 - timedelta(days=5) + timedelta(hours=6), pet_id=pb.id)
    add_event(b.id, 'die', T0 - timedelta(days=3), pet_id=pb.id, value=DEATH_CAUSE['hunger'])
    # C: tylko profil (odebrał startowe bez zdarzenia claim — profil powstał migracją/ręcznie), nic więcej
    c = make_user()
    zaloz_profil(c, now=start)
    db.session.commit()

    r = build_report(14, now=T0)
    # dzień 0 = odbiór startowego (PetProfile.start_egg_claimed_at), nie dowolne zdarzenie `claim`
    assert r['funnel'] == {'profiles': 3, 'claimed_start': 3, 'hatched_any': 2, 'alive_d7': 1}
    assert r['retention']['d7'] == {'cohort': 3, 'active': 1, 'pct': 33.3}
    assert r['retention']['d1'] == {'cohort': 3, 'active': 1, 'pct': 33.3}
    assert r['retention']['d30'] == {'cohort': 0, 'active': 0, 'pct': None}
    assert r['deaths']['total'] == 1 and r['deaths']['causes']['hunger'] == 1
    assert r['deaths']['per_100_alive'] == 100.0            # 1 odejście / 1 żywy
    assert r['alert_reaction_hours'] == {'median': 6.0, 'n': 1}
    assert r['push_owners_pct'] == {'owners': 1, 'with_push': 1, 'pct': 100.0}
    assert r['rescue_claimed_7d'] == {'deaths': 1, 'claimed': 1, 'pct': 100.0}
    assert any(c == 1 for _, c in r['caretakers_daily'])
    tekst = format_report(r)
    assert 'Odejścia' in tekst and '100.0' in tekst


def test_retencja_d7_widoczna_przy_oknie_7_dni(db, make_user):
    """Recenzja (Important 1): przy --days 7 kohorta D7 to profile z odbiorem 7–14 dni temu, a dzień 0 to
    odbiór STARTOWEGO — weteran odbierający miesięczne nie staje się nowym użytkownikiem."""
    from modules.pets.common import add_event
    from modules.pets.report import build_report
    nowy = make_user()
    zaloz_profil(nowy, now=T0 - timedelta(days=8))
    pet = zaloz_pupila(nowy, now=T0 - timedelta(days=8))
    add_event(nowy.id, 'feed', T0 - timedelta(days=1, hours=-2), pet_id=pet.id)   # dzień 7 od odbioru (+2 h)
    weteran = make_user()
    zaloz_profil(weteran, now=T0 - timedelta(days=100))
    pw = zaloz_pupila(weteran, species='mis', now=T0 - timedelta(days=100))
    add_event(weteran.id, 'claim', T0 - timedelta(days=2), pet_id=pw.id)          # miesięczne — nie dzień 0
    db.session.commit()
    r = build_report(7, now=T0)
    assert r['funnel']['claimed_start'] == 0                     # żaden profil nie powstał w oknie 7 dni
    assert r['retention']['d7'] == {'cohort': 1, 'active': 1, 'pct': 100.0}
    assert r['retention']['d1']['cohort'] == 1 and r['retention']['d1']['active'] == 0   # odbiór 8 dni temu ∈ [now-8d, now-1d]; opieka nie w dniu 1
    assert r['funnel']['alive_d7'] == 1
