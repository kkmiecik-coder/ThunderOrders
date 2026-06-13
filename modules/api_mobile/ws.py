"""
Mobile API — autoryzacja połączeń Socket.IO przez JWT (E9).

Globalny handler `connect` autoryzuje połączenie przez JWT (parytet `@jwt_required`
+ `is_active`) i wiąże `sid → user_id` w mapie in-memory (`_ws_users`). Handler jest
PERMISYWNY (D1): połączenia BEZ tokenu są AKCEPTOWANE — web, WMS i payment łączą się
bez JWT, a odrzucenie zabiłoby produkcję. Odrzucane są wyłącznie połączenia z
NIEPOPRAWNYM JWT (śmieć / wygasły / refresh / blocklista / inactive).

Tożsamość z `_ws_users` jest następnie preferowana (addytywnie) w
`handle_join_offer_reservation` (Task 3) — apka rezerwuje pod user_id z TOKENU,
payloadowy user_id jest ignorowany (anti-spoofing).

API dla innych modułów:
- `get_ws_user(sid)`    — user_id związany z sid (lub None),
- `cleanup_ws_user(sid)` — usuwa wiązanie (wołane z `wms_events.handle_disconnect`).
"""

from flask import request as flask_request

from extensions import socketio, db

# Wiązanie sid→user_id dla połączeń aplikacji mobilnej (JWT). In-memory PER-WORKER —
# wszystkie zdarzenia danego sid trafiają do tego samego workera (wzorzec
# `connected_clients` z wms_events), więc mapa lokalna jest poprawna.
_ws_users = {}


def get_ws_user(sid):
    """Zwraca user_id związany z danym sid (połączenie apki z JWT) lub None."""
    return _ws_users.get(sid)


def cleanup_ws_user(sid):
    """Usuwa wiązanie sid→user_id (wołane przy disconnect)."""
    _ws_users.pop(sid, None)


def _extract_ws_token(auth):
    """Token z `auth` dict (apka natywna) lub query stringa `?token=` (Flutter Web)."""
    if isinstance(auth, dict):
        tok = auth.get('token')
        if tok:
            return tok
    return flask_request.args.get('token')


@socketio.on('connect')
def ws_connect(auth=None):
    """
    Globalny handler połączeń Socket.IO.

    PERMISYWNY: brak tokenu → akceptuj (`return None`). Z tokenem walidacja parytetowa
    z `@jwt_required` + `is_active`: decode → `type=='access'` → blocklista → user
    istnieje i `is_active`. Sukces → wiąże sid→user_id, `return None`. Każdy błąd
    walidacji → `return False` (odrzucenie połączenia).
    """
    token = _extract_ws_token(auth)
    if not token:
        return None  # brak tokenu → akceptuj (parytet web/WMS/payment)

    from flask_jwt_extended import decode_token
    from modules.api_mobile.models import MobileTokenBlocklist
    from modules.auth.models import User

    try:
        decoded = decode_token(token)
    except Exception:
        return False  # token nieparsowalny / wygasły / zła sygnatura → odrzuć

    if decoded.get('type') != 'access':
        return False  # tylko access token (refresh odrzucony) — D3

    jti = decoded.get('jti')
    if jti and MobileTokenBlocklist.contains(jti):
        return False  # token unieważniony (logout) → odrzuć

    sub = decoded.get('sub')
    try:
        user = db.session.get(User, int(sub))
    except (TypeError, ValueError):
        return False
    if user is None or not user.is_active:
        return False

    _ws_users[flask_request.sid] = user.id
    return None
