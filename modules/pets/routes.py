"""Strona „Moje pupile" i JSON API nad serwisem (spec §3.5, §6).

- bramka: funkcja niedostępna dla użytkownika (flaga/rollout) → 404 — i strona, i API;
- każdy błąd domenowy (PetError) → {ok: false, error, message} ze statusem PetError.status;
- pod /client/pupile/api/ także 400/404/429 są JSON-em (front nie parsuje HTML);
- limiter 120/min per użytkownik (nie per IP — paczki pat pat kilku osób za NAT-em).
"""
import json
from functools import wraps

from flask import abort, jsonify, render_template, request
from flask_limiter.util import get_remote_address
from flask_login import current_user, login_required

from extensions import limiter
from modules.pets import pets_bp, service
from modules.pets.config import pets_feature_for
from modules.pets.errors import PetError
from modules.pets.species import SPECIES

API_PREFIX = '/client/pupile/api'
API_BASE = API_PREFIX


def _klucz_limitera():
    return str(current_user.id) if current_user.is_authenticated else get_remote_address()


def _api_path():
    return request.path.startswith(API_PREFIX)


def _json_err(code, message, status):
    return jsonify({'ok': False, 'error': code, 'message': message}), status


def feature_required(fn):
    """404, gdy pupile nie są dostępne dla tego użytkownika (flaga / rollout)."""
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not pets_feature_for(current_user):
            abort(404)
        return fn(*args, **kwargs)
    return wrapper


@pets_bp.errorhandler(PetError)
def _pet_error(e):
    return _json_err(e.code, e.message, e.status)


# Strona: szablony błędów aplikacji. `return e` NIE oddaje wyjątku globalnemu handlerowi —
# Flask robi z HTTPException gołą stronę Werkzeuga (sprawdzone na Flask 3.0).
@pets_bp.errorhandler(404)
def _not_found(e):
    if _api_path():
        return _json_err('not_found', 'Nie znaleziono.', 404)
    return render_template('errors/404.html'), 404


@pets_bp.errorhandler(429)
def _rate_limited(e):
    if _api_path():
        return _json_err('rate_limited', 'Za dużo żądań — odczekaj chwilę.', 429)
    return render_template('errors/429.html'), 429


@pets_bp.errorhandler(400)
def _bad_request(e):
    if _api_path():
        return _json_err('bad_request', 'Nieprawidłowe dane żądania.', 400)
    return e   # aplikacja nie ma strony 400 — goła strona Werkzeuga to i tak domyślne zachowanie


def _body():
    dane = request.get_json(silent=True)
    if dane is None:
        if request.data and request.data.strip():
            raise PetError('bad_request', 'Nieprawidłowe dane żądania.', 400)
        return {}
    if not isinstance(dane, dict):
        raise PetError('bad_request', 'Nieprawidłowe dane żądania.', 400)
    return dane


def _int_or_none(value, pole):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise PetError('bad_request', f'Nieprawidłowe pole {pole}.', 400)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise PetError('bad_request', f'Nieprawidłowe pole {pole}.', 400)


def _state(lite=False):
    return service.state_for_user(current_user._get_current_object(), lite=lite)


def _species_json():
    return json.dumps({s.slug: {'name': s.name, 'palette': s.palette, 'extras': list(s.extras)} for s in SPECIES},
                      ensure_ascii=False)


# ---------------------------------------------------------------------------
# Strona
# ---------------------------------------------------------------------------

SCENES = ('domek', 'szpital', 'warsztat', 'ogrod')   # spec v3 §3.1; '' = mapa


def _render_scene(scene):
    stan = _state()
    return render_template(
        'client/pets/home.html',
        title='Moje pupile',
        scene=scene,
        state_json=json.dumps(stan, ensure_ascii=False),
        species_json=_species_json(),
        api_base=API_BASE,
    )


@pets_bp.route('')     # '' zamiast '/': adres /client/pupile bez 308 na wersję ze slashem
@feature_required
def home():
    return _render_scene('mapa')


@pets_bp.route('/<scene>')
@feature_required
def scene(scene):
    if scene not in SCENES:
        abort(404)
    return _render_scene(scene)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pets_bp.route('/api/stan')
@feature_required
def api_state():
    lite = request.args.get('lite') in ('1', 'true', 'yes')
    return jsonify(_state(lite=lite))


@pets_bp.route('/api/jajka/odbierz', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_claim_egg():
    dane = _body()
    source = dane.get('source')
    if not isinstance(source, str):
        raise PetError('bad_request', 'Nieprawidłowe pole source.', 400)
    pet_id = _int_or_none(dane.get('pet_id'), 'pet_id')
    service.claim_egg(current_user._get_current_object(), source, pet_id=pet_id)
    return jsonify({'ok': True, 'state': _state()})


@pets_bp.route('/api/jajka/<int:pet_id>/ogrzej', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_warm_egg(pet_id):
    service.warm_egg(current_user._get_current_object(), pet_id)
    return jsonify({'ok': True, 'state': _state()})


@pets_bp.route('/api/jajka/<int:pet_id>/wykluj', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_hatch_egg(pet_id):
    from modules.pets.species import SPECIES_BY_SLUG
    wynik = service.hatch_egg(current_user._get_current_object(), pet_id)
    gatunek = SPECIES_BY_SLUG.get(wynik['species'])
    return jsonify({
        'ok': True,
        'result': wynik['result'],
        'species': wynik['species'],
        'species_name': gatunek.name if gatunek else wynik['species'],
        'pet_id': wynik['pet'].id,
        'starred_pet_id': wynik['starred_pet'].id if wynik['starred_pet'] is not None else None,
        'new_achievements': wynik['new_achievements'],
        'state': _state(),
    })


@pets_bp.route('/api/<int:pet_id>/akcja', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_action(pet_id):
    dane = _body()
    action = dane.get('action')
    if not isinstance(action, str):
        raise PetError('bad_action', 'Nieznana akcja.', 400)
    variant = dane.get('variant')
    if variant is not None and not isinstance(variant, str):
        raise PetError('bad_variant', 'Nieznany wariant akcji.', 400)
    wynik = service.perform_action(current_user._get_current_object(), pet_id, action,
                                   count=dane.get('count', 1), variant=variant)
    return jsonify({
        'ok': True,
        'variant': wynik['variant'],
        'accepted': wynik['accepted'],
        'first_care_today': wynik['first_care_today'],
        'new_achievements': wynik['new_achievements'],
        'state': _state(),
    })


@pets_bp.route('/api/<int:pet_id>/szpital', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_admit(pet_id):
    service.admit_pet(current_user._get_current_object(), pet_id)
    return jsonify({'ok': True, 'state': _state()})


@pets_bp.route('/api/<int:pet_id>/wypis', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_discharge(pet_id):
    service.discharge_pet(current_user._get_current_object(), pet_id)
    return jsonify({'ok': True, 'state': _state()})


@pets_bp.route('/api/<int:pet_id>/swiatelko', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_light_candle(pet_id):
    pet = service.light_candle(current_user._get_current_object(), pet_id)
    return jsonify({'ok': True, 'lights_count': int(pet.lights_count), 'state': _state()})


@pets_bp.route('/api/<int:pet_id>/imie', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_rename(pet_id):
    dane = _body()
    if not isinstance(dane.get('name'), str):
        raise PetError('bad_request', 'Nieprawidłowe pole name.', 400)
    pet = service.rename_pet(current_user._get_current_object(), pet_id, dane.get('name'))
    return jsonify({'ok': True, 'name': pet.name, 'state': _state()})


@pets_bp.route('/api/towarzysz', methods=['POST'])
@feature_required
@limiter.limit('120 per minute', key_func=_klucz_limitera)
def api_companion():
    dane = _body()
    pet_id = _int_or_none(dane.get('pet_id'), 'pet_id')
    enabled = dane.get('enabled', True)
    if not isinstance(enabled, bool):   # bool("false") == True — front ma wysyłać prawdziwy boolean
        raise PetError('bad_request', 'Nieprawidłowe pole enabled.', 400)
    service.set_companion(current_user._get_current_object(), pet_id=pet_id, enabled=enabled)
    return jsonify({'ok': True, 'state': _state()})


@pets_bp.route('/api/<path:_reszta>', methods=['GET', 'POST'])
@feature_required
def api_not_found(_reszta):
    """Nieznana ścieżka pod /api/ (np. /api/abc/akcja) → JSON 404.

    404 z routingu (żadna reguła nie pasuje) trafia do globalnego handlera aplikacji (HTML),
    nie do errorhandler(404) blueprintu — dlatego łapiemy resztę ścieżek tutaj. Reguły
    statyczne i z <int:> mają pierwszeństwo przed <path:>, więc niczego nie przesłaniamy;
    GET na trasę tylko-POST też dostaje tu JSON 404 zamiast HTML-owego 405.
    """
    raise PetError('not_found', 'Nie znaleziono.', 404)
