"""Panel `/admin/pupile` (spec §5): włącznik i rollout, liczby gry, statystyki, przyznawanie jajek.

- role `admin`/`mod` (`role_required`); każdy zapis `Settings.set_value(..., updated_by=current_user.id)`
  + `reset_feature_cache()` + `log_activity`;
- walidacja formularza w `config.validate_settings` — przy JAKIMKOLWIEK błędzie nic nie jest zapisywane,
  formularz wraca (400) z komunikatami przy polach;
- kill-switch maila `notify_pet_alert` siedzi w ustawieniach maili (`ALLOWED_KEYS`), nie tu.
"""
import json
from collections import Counter
from datetime import timedelta

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_

from extensions import db
from modules.auth.models import Settings, User, get_local_now
from modules.pets import pets_admin_bp, rules, service
from modules.pets.common import CARE_ACTIONS, checkpoint_alive_pets, get_profile
from modules.pets.config import (ADMIN_FIELDS, SWITCH_KEYS, PetConfig, admin_form_fields, admin_form_values,
                                 reset_feature_cache, validate_settings)
from modules.pets.errors import PetError
from modules.pets.models import Pet, PetEvent, PetProfile
from modules.pets.report import build_report
from modules.pets.species import SPECIES, SPECIES_BY_SLUG
from utils.activity_logger import log_activity
from utils.decorators import role_required

OPISY = {klucz: etykieta for klucz, _typ, _pola, etykieta in ADMIN_FIELDS}


@pets_admin_bp.errorhandler(PetError)
def _pet_error(e):
    return jsonify({'ok': False, 'error': e.code, 'message': e.message}), e.status


@pets_admin_bp.errorhandler(400)
def _bad_request(e):
    # fetch-e panelu (szukaj/przyznaj) czytają JSON — błąd CSRF (podklasa 400) nie może wracać jako HTML
    if request.is_json or request.path.endswith(('/przyznaj', '/szukaj')):
        return jsonify({'ok': False, 'error': 'bad_request',
                        'message': 'Nieprawidłowe żądanie — odśwież stronę i spróbuj ponownie.'}), 400
    return e


def admin_stats(now=None, cfg=None):
    """Liczby do kafelków (spec §5) — z danych, nie ze statusów w cache."""
    now = now or get_local_now()
    cfg = cfg or PetConfig.load(force=True)
    zywe = Pet.query.filter(Pet.status == 'alive').all()
    per_gatunek = Counter(p.species for p in zywe)
    stadia = Counter(rules.stage(p.hatched_at, now, cfg) for p in zywe if p.hatched_at is not None)
    profile = PetProfile.query.all()
    prog_miesieczny = now - timedelta(days=int(cfg.monthly_days))
    do_odebrania = (sum(int(p.granted_eggs_pending or 0) for p in profile)
                    + sum(1 for p in profile if p.last_monthly_egg_at <= prog_miesieczny)
                    + Pet.query.filter(Pet.status == 'dead', Pet.rescue_egg_claimed_at.is_(None)).count())
    dzis = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def aktywni_od(od):
        return (db.session.query(func.count(func.distinct(PetEvent.user_id)))
                .filter(PetEvent.type.in_(CARE_ACTIONS), PetEvent.created_at >= od).scalar() or 0)

    def odejscia_od(od):
        return PetEvent.query.filter(PetEvent.type == 'die', PetEvent.created_at >= od).count()

    # Komplety: użytkownicy z 8 gatunkami w albumie (żywe, zmarłe, scalone)
    wiersze = (db.session.query(Pet.user_id, func.count(func.distinct(Pet.species)))
               .filter(Pet.species.isnot(None), Pet.status.in_(('alive', 'dead', 'merged')))
               .group_by(Pet.user_id).all())
    komplety = sum(1 for _uid, n in wiersze if n >= len(SPECIES))
    raport = build_report(7, now=now)
    return {
        'profiles': len(profile),
        'alive_total': len(zywe),
        'alive_per_species': [(s.name, per_gatunek.get(s.slug, 0)) for s in SPECIES],
        'eggs_incubating': Pet.query.filter(Pet.status == 'egg').count(),
        'eggs_claimable': do_odebrania,
        'deaths_7d': odejscia_od(now - timedelta(days=7)),
        'deaths_30d': odejscia_od(now - timedelta(days=30)),
        'active_today': aktywni_od(dzis),
        'active_7d': aktywni_od(now - timedelta(days=7)),
        'stages': [('Maluchy', stadia.get('maluch', 0)), ('Dzieci', stadia.get('dziecko', 0)), ('Dorośli', stadia.get('dorosly', 0))],
        'complete_albums': komplety,
        'push_pct': raport['push_owners_pct'],
        'retention_d7': raport['retention']['d7'],
        'rescue_7d': raport['rescue_claimed_7d'],
    }


def _render_index(form, errors, status=200):
    return render_template(
        'admin/pets/index.html',
        title='Pupile',
        sections=ADMIN_FIELDS,
        field_names=admin_form_fields(),
        form=form,
        errors=errors,
        stats=admin_stats(),
    ), status


@pets_admin_bp.route('')
@role_required('admin', 'mod')
def index():
    return _render_index(admin_form_values(PetConfig.load(force=True)), {})


@pets_admin_bp.route('/ustawienia', methods=['POST'])
@role_required('admin', 'mod')
def save_settings():
    tylko_wlacznik = request.form.get('scope') == 'switch'
    values, errors = validate_settings(request.form, only=SWITCH_KEYS if tylko_wlacznik else None)
    if errors:
        formularz = dict(admin_form_values(PetConfig.load(force=True)), **request.form.to_dict()) if tylko_wlacznik else request.form
        return _render_index(formularz, errors, status=400)
    przeliczone = 0
    if not tylko_wlacznik:
        # Liczby gry: domknij stan wszystkich żywych pupili STARĄ konfiguracją, żeby zmiana nie działała wstecz
        przeliczone = checkpoint_alive_pets(get_local_now(), PetConfig.load(force=True))
    zmienione = {}
    for klucz, (wartosc, typ) in values.items():
        Settings.set_value(klucz, wartosc, updated_by=current_user.id, type=typ, description=OPISY.get(klucz))
        zmienione[klucz] = wartosc
    reset_feature_cache()
    log_activity(user=current_user, action='pets_settings_updated', entity_type='settings',
                 entity_id=None, new_value=json.dumps(zmienione, ensure_ascii=False))
    if tylko_wlacznik:
        flash('Włącznik i rollout zapisane — działają natychmiast.', 'success')
    else:
        flash(f'Liczby gry zapisane. Stan {przeliczone} żywych pupili domknięty poprzednią konfiguracją; nowa liczy się od teraz.', 'success')
    return redirect(url_for('pets_admin.index'))


@pets_admin_bp.route('/szukaj')
@role_required('admin', 'mod')
def search_users():
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    wzorzec = f'%{q}%'
    users = (User.query.filter(or_(User.email.ilike(wzorzec), User.first_name.ilike(wzorzec), User.last_name.ilike(wzorzec)))
             .order_by(User.email).limit(20).all())
    wynik = []
    for user in users:
        stan = service.state_for_user(user, lite=True)
        profil = get_profile(user)
        wynik.append({
            'id': user.id,
            'email': user.email,
            'name': user.full_name if hasattr(user, 'full_name') else (user.first_name or ''),
            'has_profile': profil is not None,
            'granted_pending': int(profil.granted_eggs_pending or 0) if profil is not None else 0,
            'pets': [{'id': p['id'], 'name': p['name'], 'species_name': SPECIES_BY_SLUG[p['species']].name,
                      'mood': p['mood'], 'stage': p['stage'], 'asleep': p['asleep']} for p in stan['pets']],
            'eggs': len(stan['eggs']),
            'eggs_available': [e['source'] for e in stan['eggs_available']],
        })
    return jsonify(wynik)


@pets_admin_bp.route('/przyznaj', methods=['POST'])
@role_required('admin', 'mod')
def grant_egg():
    dane = request.get_json(silent=True) or {}
    try:
        user_id = int(dane.get('user_id'))
    except (TypeError, ValueError):
        raise PetError('bad_request', 'Nieprawidłowe pole user_id.', 400)
    user = db.session.get(User, user_id)
    if user is None:
        raise PetError('not_found', 'Nie ma takiego użytkownika.', 404)
    try:
        profil = service.admin_grant_egg(user)
    except PetError as e:
        if e.code == 'no_profile':
            raise PetError('no_profile', 'Użytkownik nie odebrał jeszcze startowego jajka — nie ma komu przyznać.', 409)
        raise
    log_activity(user=current_user, action='pet_egg_granted', entity_type='user', entity_id=user.id,
                 new_value=str(profil.granted_eggs_pending))
    return jsonify({'ok': True, 'granted_pending': int(profil.granted_eggs_pending)})
