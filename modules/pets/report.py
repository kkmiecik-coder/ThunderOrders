"""`flask pets report --days N` (spec §3.7) — metryki z danych (pet_events, pets, pet_profiles,
push_subscriptions), nie ze statusów w cache. Czyste funkcje z `now=` do testów; grupowanie w Pythonie
(wolumen pupili jest mały), zero zapisu.

Konwencje:
- „opieka" = zdarzenia CARE_ACTIONS (feed/play/wash/heal/pat);
- dzień 0 użytkownika = jego pierwsze zdarzenie `claim` w oknie; retencja dN = dowolna opieka w dniu
  claim+N (±12 h);
- `None` zamiast dzielenia przez zero (0 żywych, pusta kohorta) — format_report pokazuje „—".
"""
from collections import defaultdict
from datetime import timedelta
from statistics import median

from extensions import db
from modules.pets.common import CARE_ACTIONS, DEATH_CAUSE, now_or
from modules.pets.models import Pet, PetEvent, PetProfile

CAUSE_NAMES = {kod: nazwa for nazwa, kod in DEATH_CAUSE.items()}


def _pct(licznik, mianownik):
    return round(100.0 * licznik / mianownik, 1) if mianownik else None


def build_report(days, now=None):
    now = now_or(now)
    days = max(1, int(days))
    since = now - timedelta(days=days)

    zdarzenia = (PetEvent.query.filter(PetEvent.created_at >= since, PetEvent.created_at <= now)
                 .order_by(PetEvent.created_at).all())
    opieka = [e for e in zdarzenia if e.type in CARE_ACTIONS]
    claimy = [e for e in zdarzenia if e.type == 'claim']
    pierwszy_claim = {}
    for e in claimy:                      # posortowane rosnąco → pierwszy wygrywa
        pierwszy_claim.setdefault(e.user_id, e.created_at)

    zywe = Pet.query.filter(Pet.status == 'alive').all()
    zywi_wlasciciele = {p.user_id for p in zywe}

    # --- lejek ---
    hatched_users = {e.user_id for e in zdarzenia if e.type in ('hatch_new', 'hatch_dupe')}
    alive_d7 = sum(1 for uid, t in pierwszy_claim.items() if now - t >= timedelta(days=7) and uid in zywi_wlasciciele)
    funnel = {
        'profiles': PetProfile.query.filter(PetProfile.created_at <= now).count(),
        'claimed_start': len(pierwszy_claim),
        'hatched_any': len(hatched_users),
        'alive_d7': alive_d7,
    }

    # --- retencja ---
    opieka_per_user = defaultdict(list)
    for e in opieka:
        opieka_per_user[e.user_id].append(e.created_at)
    retention = {}
    for n in (1, 7, 30):
        kohorta = [(uid, t) for uid, t in pierwszy_claim.items() if now - t >= timedelta(days=n)]
        aktywni = 0
        for uid, t in kohorta:
            cel = t + timedelta(days=n)
            if any(abs((c - cel).total_seconds()) <= 12 * 3600 for c in opieka_per_user.get(uid, ())):
                aktywni += 1
        retention[f'd{n}'] = {'cohort': len(kohorta), 'active': aktywni, 'pct': _pct(aktywni, len(kohorta))}

    # --- aktywni opiekunowie dziennie ---
    per_dzien = defaultdict(set)
    for e in opieka:
        per_dzien[e.created_at.date()].add(e.user_id)
    caretakers_daily = []
    for i in range(days, -1, -1):
        d = (now - timedelta(days=i)).date()
        caretakers_daily.append((d.isoformat(), len(per_dzien.get(d, ()))))

    # --- odejścia ---
    odejscia = [e for e in zdarzenia if e.type == 'die']
    przyczyny = {nazwa: 0 for nazwa in DEATH_CAUSE}
    przyczyny['unknown'] = 0
    for e in odejscia:
        przyczyny[CAUSE_NAMES.get(int(e.value or 0), 'unknown')] += 1
    deaths = {
        'total': len(odejscia),
        'per_day': round(len(odejscia) / days, 2),
        'per_100_alive': _pct(len(odejscia), len(zywe)),
        'causes': przyczyny,
    }

    # --- reakcja na ostrzeżenie ---
    opieka_per_pet = defaultdict(list)
    for e in opieka:
        if e.pet_id is not None:
            opieka_per_pet[e.pet_id].append(e.created_at)
    reakcje = []
    for e in zdarzenia:
        if e.type != 'alert' or e.pet_id is None:
            continue
        pozniejsze = [c for c in opieka_per_pet.get(e.pet_id, ()) if c > e.created_at]
        if pozniejsze:
            reakcje.append((min(pozniejsze) - e.created_at).total_seconds() / 3600.0)
    alert_reaction_hours = {'median': round(median(reakcje), 2) if reakcje else None, 'n': len(reakcje)}

    # --- push wśród właścicieli żywych pupili ---
    from modules.notifications.models import PushSubscription
    z_pushem = 0
    if zywi_wlasciciele:
        z_pushem = (db.session.query(PushSubscription.user_id)
                    .filter(PushSubscription.user_id.in_(zywi_wlasciciele), PushSubscription.is_active == True)  # noqa: E712
                    .distinct().count())
    push_owners_pct = {'owners': len(zywi_wlasciciele), 'with_push': z_pushem, 'pct': _pct(z_pushem, len(zywi_wlasciciele))}

    # --- ratunkowe odebrane w 7 dni od odejścia ---
    zmarli = Pet.query.filter(Pet.status == 'dead', Pet.died_at >= since, Pet.died_at <= now).all()
    odebrane = sum(1 for p in zmarli if p.rescue_egg_claimed_at is not None
                   and p.rescue_egg_claimed_at <= p.died_at + timedelta(days=7))
    rescue_claimed_7d = {'deaths': len(zmarli), 'claimed': odebrane, 'pct': _pct(odebrane, len(zmarli))}

    return {
        'window': {'days': days, 'since': since.isoformat(timespec='minutes'), 'until': now.isoformat(timespec='minutes')},
        'funnel': funnel,
        'retention': retention,
        'caretakers_daily': caretakers_daily,
        'deaths': deaths,
        'alert_reaction_hours': alert_reaction_hours,
        'push_owners_pct': push_owners_pct,
        'rescue_claimed_7d': rescue_claimed_7d,
    }


def _f(v, suffix=''):
    return '—' if v is None else f'{v}{suffix}'


def format_report(r):
    f, ret, d = r['funnel'], r['retention'], r['deaths']
    linie = [
        f"Pupile — raport za {r['window']['days']} dni ({r['window']['since']} → {r['window']['until']})",
        '',
        'Lejek',
        f"  Profile:               {f['profiles']}",
        f"  Odebrali jajko:        {f['claimed_start']}",
        f"  Wykluli:               {f['hatched_any']}",
        f"  Żywy pupil w D7:       {f['alive_d7']}",
        '',
        'Retencja (opieka w dniu N od odbioru)',
    ]
    for k in ('d1', 'd7', 'd30'):
        linie.append(f"  {k.upper():<4} {ret[k]['active']}/{ret[k]['cohort']} ({_f(ret[k]['pct'], '%')})")
    linie += ['', 'Aktywni opiekunowie dziennie']
    for dzien, n in r['caretakers_daily']:
        linie.append(f'  {dzien}  {n}')
    linie += [
        '',
        'Odejścia',
        f"  Razem: {d['total']}  na dobę: {d['per_day']}  na 100 żywych: {_f(d['per_100_alive'])}",
        '  Przyczyny: ' + ', '.join(f'{k}={v}' for k, v in d['causes'].items()),
        '',
        f"Reakcja na ostrzeżenie: mediana {_f(r['alert_reaction_hours']['median'], ' h')} (n={r['alert_reaction_hours']['n']})",
        f"Właściciele żywych pupili z pushem: {r['push_owners_pct']['with_push']}/{r['push_owners_pct']['owners']} ({_f(r['push_owners_pct']['pct'], '%')})",
        f"Ratunkowe odebrane w 7 dni: {r['rescue_claimed_7d']['claimed']}/{r['rescue_claimed_7d']['deaths']} ({_f(r['rescue_claimed_7d']['pct'], '%')})",
    ]
    return '\n'.join(linie)
