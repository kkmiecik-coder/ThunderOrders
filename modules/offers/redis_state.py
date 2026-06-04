"""
Offers Module - Shared State w Redis

Zastępuje module-level dicts z socket_events.py które uniemożliwiały
skalowanie do >1 workera Gunicorn (każdy worker miał własną pamięć,
więc visitor count, admin rooms i deduplikacja sesji nie działały
między workerami).

Graceful fallback: jeśli Redis jest niedostępny przy starcie aplikacji,
warstwa degraduje do in-memory dictów. Aplikacja nadal działa, ale
tylko w trybie single-worker.

Klucze w Redis (wszystkie z TTL 1h, odświeżanym przy każdej operacji):
- visitors:{page_id}:countdown  - SET of sid (visitor sockets na stronie countdown)
- visitors:{page_id}:order      - SET of sid (visitor sockets na stronie zamówień)
- admins:{page_id}              - SET of sid (admin sockets podpięte do live dashboarda)
- client:{sid}                  - HASH {page_id, role} (mapowanie sid → kontekst)
- reservation_session:{page_id}:{session_id} - STRING sid (dedup po sesji)
- user_session:{page_id}:{user_id}            - STRING sid (dedup po userze)
- last_availability:{page_id}   - STRING json (ostatnio rozesłana dostępność)
"""

import json
import logging
import threading

logger = logging.getLogger(__name__)

# TTL dla kluczy aktywności (1h — odświeżany przy każdej operacji write)
_DEFAULT_TTL = 3600


class OffersStateBackend:
    """Interfejs backendu — Redis lub in-memory."""

    # Visitors
    def add_visitor(self, page_id, room_type, sid): raise NotImplementedError
    def remove_visitor(self, page_id, room_type, sid): raise NotImplementedError
    def get_visitor_counts(self, page_id): raise NotImplementedError

    # Admins
    def add_admin(self, page_id, sid): raise NotImplementedError
    def remove_admin(self, page_id, sid): raise NotImplementedError
    def has_admins(self, page_id): raise NotImplementedError

    # Clients
    def set_client(self, sid, page_id, role, **extra): raise NotImplementedError
    def get_client(self, sid): raise NotImplementedError
    def del_client(self, sid): raise NotImplementedError

    # Reservation/user dedup
    def set_reservation_session(self, page_id, session_id, sid): raise NotImplementedError
    def get_reservation_session(self, page_id, session_id): raise NotImplementedError
    def del_reservation_session(self, page_id, session_id): raise NotImplementedError
    def set_user_session(self, page_id, user_id, sid): raise NotImplementedError
    def get_user_session(self, page_id, user_id): raise NotImplementedError
    def del_user_session(self, page_id, user_id): raise NotImplementedError

    # Last availability (do detekcji zmian → push notifications)
    def set_last_availability(self, page_id, snapshot): raise NotImplementedError
    def get_last_availability(self, page_id): raise NotImplementedError


class InMemoryBackend(OffersStateBackend):
    """Fallback gdy Redis niedostępny. NIE działa cross-worker."""

    def __init__(self):
        self._visitors = {}        # {page_id: {'countdown': set, 'order': set}}
        self._admins = {}          # {page_id: set(sid)}
        self._clients = {}         # {sid: {'page_id': ..., 'role': ...}}
        self._reservation_sessions = {}  # {(page_id, session_id): sid}
        self._user_sessions = {}   # {(page_id, user_id): sid}
        self._last_availability = {}  # {page_id: dict}
        self._lock = threading.RLock()

    def add_visitor(self, page_id, room_type, sid):
        with self._lock:
            self._visitors.setdefault(page_id, {}).setdefault(room_type, set()).add(sid)

    def remove_visitor(self, page_id, room_type, sid):
        with self._lock:
            rooms = self._visitors.get(page_id)
            if rooms and room_type in rooms:
                rooms[room_type].discard(sid)

    def get_visitor_counts(self, page_id):
        with self._lock:
            rooms = self._visitors.get(page_id, {})
            return {
                'countdown': len(rooms.get('countdown', set())),
                'order': len(rooms.get('order', set())),
            }

    def add_admin(self, page_id, sid):
        with self._lock:
            self._admins.setdefault(page_id, set()).add(sid)

    def remove_admin(self, page_id, sid):
        with self._lock:
            if page_id in self._admins:
                self._admins[page_id].discard(sid)
                if not self._admins[page_id]:
                    del self._admins[page_id]

    def has_admins(self, page_id):
        with self._lock:
            return page_id in self._admins and len(self._admins[page_id]) > 0

    def set_client(self, sid, page_id, role, **extra):
        with self._lock:
            data = {'page_id': page_id, 'role': role}
            data.update(extra)
            self._clients[sid] = data

    def get_client(self, sid):
        with self._lock:
            return dict(self._clients[sid]) if sid in self._clients else None

    def del_client(self, sid):
        with self._lock:
            self._clients.pop(sid, None)

    def set_reservation_session(self, page_id, session_id, sid):
        with self._lock:
            self._reservation_sessions[(page_id, session_id)] = sid

    def get_reservation_session(self, page_id, session_id):
        with self._lock:
            return self._reservation_sessions.get((page_id, session_id))

    def del_reservation_session(self, page_id, session_id):
        with self._lock:
            self._reservation_sessions.pop((page_id, session_id), None)

    def set_user_session(self, page_id, user_id, sid):
        with self._lock:
            self._user_sessions[(page_id, user_id)] = sid

    def get_user_session(self, page_id, user_id):
        with self._lock:
            return self._user_sessions.get((page_id, user_id))

    def del_user_session(self, page_id, user_id):
        with self._lock:
            self._user_sessions.pop((page_id, user_id), None)

    def set_last_availability(self, page_id, snapshot):
        with self._lock:
            self._last_availability[page_id] = snapshot

    def get_last_availability(self, page_id):
        with self._lock:
            return self._last_availability.get(page_id)


class RedisBackend(OffersStateBackend):
    """Cross-worker shared state przez Redis."""

    def __init__(self, redis_client):
        self.r = redis_client

    def _refresh_ttl(self, key):
        # Best-effort — TTL refresh nie jest krytyczny
        try:
            self.r.expire(key, _DEFAULT_TTL)
        except Exception:
            pass

    # Visitors
    def add_visitor(self, page_id, room_type, sid):
        key = f"visitors:{page_id}:{room_type}"
        self.r.sadd(key, sid)
        self._refresh_ttl(key)

    def remove_visitor(self, page_id, room_type, sid):
        self.r.srem(f"visitors:{page_id}:{room_type}", sid)

    def get_visitor_counts(self, page_id):
        return {
            'countdown': self.r.scard(f"visitors:{page_id}:countdown") or 0,
            'order': self.r.scard(f"visitors:{page_id}:order") or 0,
        }

    # Admins
    def add_admin(self, page_id, sid):
        key = f"admins:{page_id}"
        self.r.sadd(key, sid)
        self._refresh_ttl(key)

    def remove_admin(self, page_id, sid):
        self.r.srem(f"admins:{page_id}", sid)

    def has_admins(self, page_id):
        return (self.r.scard(f"admins:{page_id}") or 0) > 0

    # Clients
    def set_client(self, sid, page_id, role, **extra):
        key = f"client:{sid}"
        mapping = {'page_id': str(page_id), 'role': role}
        # Dodatkowe pola (np. session_id, user_id) — Redis HASH przechowuje stringi,
        # więc serializujemy None → "" i wszystko castujemy na str.
        for k, v in extra.items():
            mapping[k] = str(v) if v is not None else ''
        self.r.hset(key, mapping=mapping)
        self._refresh_ttl(key)

    def get_client(self, sid):
        data = self.r.hgetall(f"client:{sid}")
        if not data:
            return None
        # Konwersja page_id i user_id z str na int (Redis trzyma jako string)
        try:
            data['page_id'] = int(data['page_id'])
        except (KeyError, ValueError):
            pass
        if data.get('user_id'):
            try:
                data['user_id'] = int(data['user_id'])
            except ValueError:
                pass
        else:
            data['user_id'] = None
        # Puste stringi → None (kompatybilność z poprzednim API)
        if data.get('session_id') == '':
            data['session_id'] = None
        return data

    def del_client(self, sid):
        self.r.delete(f"client:{sid}")

    # Reservation dedup
    def set_reservation_session(self, page_id, session_id, sid):
        self.r.setex(f"reservation_session:{page_id}:{session_id}", _DEFAULT_TTL, sid)

    def get_reservation_session(self, page_id, session_id):
        return self.r.get(f"reservation_session:{page_id}:{session_id}")

    def del_reservation_session(self, page_id, session_id):
        self.r.delete(f"reservation_session:{page_id}:{session_id}")

    # User dedup
    def set_user_session(self, page_id, user_id, sid):
        self.r.setex(f"user_session:{page_id}:{user_id}", _DEFAULT_TTL, sid)

    def get_user_session(self, page_id, user_id):
        return self.r.get(f"user_session:{page_id}:{user_id}")

    def del_user_session(self, page_id, user_id):
        self.r.delete(f"user_session:{page_id}:{user_id}")

    # Last availability
    def set_last_availability(self, page_id, snapshot):
        self.r.setex(f"last_availability:{page_id}", _DEFAULT_TTL, json.dumps(snapshot))

    def get_last_availability(self, page_id):
        raw = self.r.get(f"last_availability:{page_id}")
        return json.loads(raw) if raw else None


# Singleton state — inicjalizowane przez init_state() przy starcie aplikacji
_backend = None


def init_state(redis_url=None):
    """
    Inicjalizuje warstwę state. Próbuje Redis, w razie problemu — in-memory.
    Wywoływane raz przy starcie aplikacji (z app.py).
    """
    global _backend

    if redis_url:
        try:
            import redis
            client = redis.Redis.from_url(redis_url, decode_responses=True,
                                          socket_timeout=2, socket_connect_timeout=2)
            client.ping()
            _backend = RedisBackend(client)
            logger.info(f"OffersState: using Redis backend ({redis_url})")
            return _backend
        except Exception as e:
            logger.warning(f"OffersState: Redis unavailable ({e}), falling back to in-memory")

    _backend = InMemoryBackend()
    logger.info("OffersState: using in-memory backend (single-worker only)")
    return _backend


def get_state():
    """Zwraca aktualny backend state. Jeśli init_state nie był wywołany — in-memory."""
    global _backend
    if _backend is None:
        _backend = InMemoryBackend()
    return _backend


def is_redis_backed():
    """True jeśli używamy Redis, False jeśli in-memory fallback."""
    return isinstance(_backend, RedisBackend)
