# Mobile API — Etap E10 (Push FCM: rejestracja urządzeń + kanał FCM w PushManagerze) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development (RED→GREEN per task).
> Task 5 (warunkowy — back-in-stock) dotyka ŻYWEGO kodu rezerwacji LIVE (`socket_events.py`) — zmiany
> WYŁĄCZNIE ADDYTYWNE, obowiązkowa dwustopniowa adwersaryjna recenzja jak przy E3/E9. Kroki = checkboxy `- [ ]`.
> **NIE pushować bez zgody Konrada. NIE dotykać produkcji.**

**Goal:** Aplikacja mobilna rejestruje token FCM swojego urządzenia (`POST /push/devices`) i wyrejestrowuje
go przy wylogowaniu (`DELETE /push/devices/<token>`). Istniejący `PushManager` (dziś Web Push/VAPID przez
pywebpush) zyskuje **drugi kanał — FCM HTTP v1** — wpięty addytywnie w rdzeń `send_to_user`, dzięki czemu
**wszystkie istniejące `notify_*`** (zmiana statusu, płatność, przypomnienie płatności, nowa oferta, koszt,
wysyłka, anulowanie itd.) automatycznie docierają też na urządzenia mobilne — bez zmian w miejscach
wywołań. Web Push pozostaje bit-w-bit bez zmian (parytet). Multi-device per user; tokeny odrzucone przez
FCM jako nieaktualne są usuwane.

```
POST   /api/mobile/v1/push/devices          { fcm_token, platform }  → rejestruje/odświeża token (upsert)
DELETE /api/mobile/v1/push/devices/<token>                           → wyrejestrowuje (przy logout)
```

---

## 1. Zweryfikowane fakty (z badania kodu — file:line, NIE odkrywaj ponownie)

### PushManager — jak działa dziś
- **`utils/push_manager.py`** — statyczny dispatcher (wzorzec EmailManager: static methods, lazy importy,
  graceful errors). **Rdzeń: `send_to_user(user_id, title, body, url='/', tag='default', notification_type=None)`**
  (`push_manager.py:46`). Sekwencja (komentarz „Opcja 1 — webpush poza transakcją", `:53`):
  1. zapis **jednego** rekordu `Notification` + cleanup >30 dni (krótka transakcja, `:79-101`);
  2. check `NotificationPreference` — gdy `getattr(pref, notification_type) == False` → `return False` (`:104-107`);
  3. snapshot aktywnych `PushSubscription` do dictów, `commit()` (zwolnienie transakcji), `:109-128`;
  4. pętla `webpush` POZA sesją DB (`_send_single_raw` przez `pywebpush`, `:144-154`);
  5. mikro-transakcje per sub z retry na 1205 lock timeout: sukces → `last_used_at`/`failed_count=0`
     (`_update_sub_success`, `:185`); błąd → 410 deaktywuje, ≥5 fail deaktywuje (`_handle_send_error_by_id`, `:211`).
- **`_fire_and_forget(...)`** (`:269`) = `send_to_user` w wątku daemon (`_send_async` z `app.app_context()`, `:264`).
  **WSZYSTKIE semantyczne `notify_*` wołają `_fire_and_forget` lub `send_to_user`** → mają wspólny rdzeń.
- **Helper `_is_lock_timeout(exc)`** (`:33`) i `_SUB_UPDATE_MAX_RETRIES=3` (`:30`) — do reużycia dla FCM.
- **VAPID gate:** brak `VAPID_PRIVATE_KEY` → log + `return False` (`:140-142`). Wzorzec graceful-disable do skopiowania dla FCM.
- **Miejsca wywołań `notify_*` (call-sites, ~30)** — m.in. `modules/orders/routes.py:612` (status),
  `modules/admin/payment_confirmations.py:274` (płatność), `modules/offers/models.py:325` (nowa oferta),
  `utils/push_manager.py:notify_payment_reminder`. **Po rozszerzeniu rdzenia żaden z nich NIE wymaga zmiany.**

### Model subskrypcji — wzorzec dla MobileDevice
- **`PushSubscription`** (`modules/notifications/models.py:73`): `push_subscriptions` — `user_id` FK
  `users.id` ondelete CASCADE + index, `endpoint Text`, `p256dh_key`, `auth_key`, `device_name`,
  `is_active`, `failed_count`, `last_used_at`, `created_at`. To wzorzec — ale `mobile_device` celowo MINIMALNY (sek. 9).
- **`NotificationPreference`** (`:110`): per-user toggle (`order_status_changes`, `payment_updates`,
  `shipping_updates`, `new_exclusive_pages`, `cost_added`, `admin_alerts`, `sale_date_changes`,
  `order_supplier_ordered`). **FCM respektuje TE SAME preferencje** (sprawdzane raz w `send_to_user` — parytet).
- **`Notification`** (`:46`) zapisywany **raz** na `send_to_user`. FCM to dodatkowy KANAŁ tej samej notyfikacji
  → **NIE dublujemy** rekordu (kluczowe: rozszerzamy istniejący przepływ, nie tworzymy drugiego).

### „Produkt wrócił" (back-in-stock) — jedyne zdarzenie ze specu sek. 9 BEZ kanału push dziś
- Trigger: `modules/offers/socket_events.py:198` `_check_notification_subscriptions(page_id, ...)` (`:202`):
  gdy `old_avail<=0 and new_avail>0` → dla `OfferProductNotificationSubscription` (`offer_page_id`,
  `product_id`, `user_id`, `notified`): jeśli user ma aktywny sid na stronie → `socketio.emit('product_available', ...)`
  (`:251`); **inaczej e-mail fallback** `send_back_in_stock_email(...)` (`:263-284`).
- **Nie istnieje `PushManager.notify_back_in_stock`** (grep) — back-in-stock NIE ma dziś kanału push.
  → dostarczenie tego jako push wymaga NOWEGO `notify_*` wpiętego w `socket_events.py` (LIVE). To realny
  branch dla Konrada (sek. 3 / Task 5).

### Konwencje modułu mobilnego (parytet z E0–E9)
- Blueprint `api_mobile_bp`, prefix `/api/mobile/v1` (`modules/api_mobile/__init__.py`). Trasy:
  `@jwt_required()` + `int(get_jwt_identity())`, koperta `json_ok`/`json_err(code,msg,status[,details])`
  (`helpers.py`), ownership cudzego zasobu → **404 maskujące**, limiter, `ValidationError`→`invalid_input` (`__init__.py`).
- **Modele mobilne w `modules/api_mobile/models.py`** (`MobileTokenBlocklist`, `MobileIdempotencyKey`);
  importowane przez `from . import models` w `__init__.py` (`:25`) → **Alembic wykrywa tabelę**.
- Nowe trasy: nowy plik `push_routes.py` + `from . import push_routes` na końcu `__init__.py` (wzorzec jak `collection_routes`).
- **Logout** (`auth_routes.py:225` `logout`): blokuje refresh JWT (`MobileTokenBlocklist`). **Spec: apka woła
  `DELETE /push/devices/<token>` OSOBNO przy logout** → trasa `logout` NIETKNIĘTA (E10 nie dotyka auth).
- Walidator `parse_int` w `validators.py` (do reużycia, choć tu walidacja głównie stringów).

### Biblioteka / wysyłka FCM
- **`requirements.txt`: `google-auth==2.35.0` (`:40`) + `requests==2.31.0` (`:83`) JUŻ obecne** (google-auth z E0
  do weryfikacji Google ID token). **`firebase-admin` NIEobecny.** → **FCM HTTP v1 ręcznie, BEZ nowej zależności**
  (google-auth OAuth2 service account + requests POST). Patrz D1.
- Wzorzec sekretu env: `JWT_SECRET_KEY`, `GOOGLE_OAUTH_CLIENT_IDS`, `VAPID_*` w `config.py:99-115`; nic
  wrażliwego w repo. Service account JSON Firebase analogicznie — przez env/plik, NIE commitowany.
- Firebase projekt `thunderorders-8258f` (z kontekstu; Google Sign-In już działa). Endpoint FCM v1:
  `POST https://fcm.googleapis.com/v1/projects/<project_id>/messages:send`, scope
  `https://www.googleapis.com/auth/firebase.messaging`.

### Migracje / baseline / git
- **Głowa migracji: `c72aad290158`** (`flask db heads`; plik `migrations/versions/c72aad290158_mobile_idempotency_keys.py`,
  `down_revision='c0ee01fee8b5'`). Nowa migracja `Revises: c72aad290158`.
- **Lekcja MariaDB FK/index** (wzorzec z `c72aad290158_..py:36-39`): `downgrade()` = **samo `op.drop_table('mobile_device')`**;
  NIE dropować indeksu podtrzymującego FK przed DROP TABLE.
- **Baseline: `434 passed, 44 warnings in ~77s`** (`source venv/bin/activate && python -m pytest -q` — zweryfikowane 2026-06-13).
- **`/docs` w `.gitignore` (`:11`)** → commit przez `git add -f`. Git HEAD na starcie: `7f847d2`.
- Testy mobilne: helper `_auth(client, db, make_user)` (login → Bearer), fixtures `app/db/client/make_user`
  w `tests/conftest.py`. Nowy plik `tests/test_mobile_api_push.py`.

---

## 2. Decyzja architektoniczna (kluczowa) — JEDEN wspólny interfejs, FCM addytywnie w rdzeniu

**Wybór: rozszerzyć `send_to_user` o fan-out FCM** (po bloku Web Push), reużywając tej samej notyfikacji,
tego samego `title/body/url/tag` i tego samego checku `NotificationPreference`. To rozstrzyga otwarte
pytanie ze specu sek. 12 („czy `PushManager` ma jeden wspólny interfejs dla obu kanałów") → **TAK, jeden**.

**Dlaczego, nie osobny dispatcher / nie firebase-admin:**
- **Parytet i zero zmian call-site:** wszystkie `notify_*` lecą przez `send_to_user`. Dokładając kanał w
  rdzeniu, każde istniejące zdarzenie (status, płatność, przypomnienie, nowa oferta, koszt, wysyłka…)
  natychmiast zyskuje FCM. Spec sek. 9 wymienia te zdarzenia jako wspólne — dostajemy je „za darmo".
- **Jedna notyfikacja, dwa kanały:** rekord `Notification` i check preferencji wykonują się RAZ; FCM to
  tylko druga droga dostarczenia. Brak duplikatów w centrum powiadomień.
- **Web Push bit-w-bit bez zmian:** blok FCM jest CZYSTO ADDYTYWNY i wykonuje się po Web Pushu; brak
  skonfigurowanego Firebase → blok FCM no-op (jak VAPID gate). Brak `mobile_device` dla usera → no-op.
- **Bez nowej zależności / w tle przez istniejący model wątków:** `send_to_user` już biega w wątku daemon
  (`_fire_and_forget`), więc fan-out FCM jest nieblokujący bez nowego executora. google-auth+requests już są.
  firebase-admin ciągnąłby grpc i duplikował to, co robimy w ~40 liniach.

**Zakres zmian w żywym kodzie (Web/PushManager):** wyłącznie ADDYTYWNE — nowe metody `_fcm_*` + JEDNO
wywołanie `PushManager._send_fcm_to_user(...)` na końcu `send_to_user`. Istniejące ścieżki Web Push,
`_send_single_raw`, `_update_sub_success`, `_handle_send_error_by_id` — NIETKNIĘTE.

---

## 3. Decyzje — ROZSTRZYGNIĘTE samodzielnie (delegacja: parytet/spec → bezpieczeństwo → prostota)

- **D1 — FCM HTTP v1, ręcznie (google-auth + requests), BEZ firebase-admin.** Legacy server key jest
  **wycofany przez Google** (Cloud Messaging API legacy wyłączone 2024) → v1 to jedyna realna opcja, nie wybór.
  google-auth+requests już w repo; firebase-admin = zbędny ciężar (grpc). *(Patrz „Do Konrada" — formalne potwierdzenie v1.)*
- **D2 — Service account z env, NIE commitowany.** `FIREBASE_CREDENTIALS_PATH` (ścieżka do pliku JSON na
  serwerze, poza repo) jako podstawowa; opcjonalnie `FIREBASE_CREDENTIALS_JSON` (surowy JSON w env, fallback).
  `project_id` czytany z JSON; override `FIREBASE_PROJECT_ID`. Brak konfiguracji → FCM wyłączony gracefully (jak VAPID).
- **D3 — Model MINIMALNY wg spec sek. 9:** `mobile_device(id, user_id, fcm_token, platform, last_used_at, created_at)`.
  BEZ `is_active`/`failed_count` — stale token **usuwamy** (hard delete), nie deaktywujemy (zgodnie z „usuń
  tokeny odrzucone przez FCM jako nieaktualne"). Prościej i wierniej specowi.
- **D4 — `fcm_token` UNIQUE globalnie (`VARCHAR(512)`).** POST = **upsert keyed na fcm_token**: token zawsze
  należy do DOKŁADNIE jednego, aktualnie zalogowanego usera. Ponowny POST tego samego tokenu = odświeżenie
  `platform`+`last_used_at` (nie duplikat). Token zarejestrowany wcześniej przez innego usera (to samo
  urządzenie fizyczne, np. po przelogowaniu) → **przepięcie na bieżącego usera z JWT** (poprzedni traci token,
  nie dostanie cudzych powiadomień — bezpieczeństwo). `VARCHAR(512)` mieści realne tokeny FCM (~150–250 zn.)
  z marginesem i mieści się w limicie indeksu unikalnego InnoDB DYNAMIC (512×4B=2048 ≤ 3072). *(Alternatywa
  rozważona i odrzucona: kolumna-hash sha256 unique + token Text — bezpieczna wobec limitu indeksu, ale dokłada
  kolumnę spoza specu i komplikuje DELETE.)*
- **D5 — `platform` ∈ {`android`,`ios`,`web`}** walidowane w trasie (app-level, parytet z resztą API),
  inne → `400 invalid_input`. `VARCHAR(16)`.
- **D6 — DELETE: filtr po `fcm_token` AND `user_id == JWT`.** Brak dopasowania (nie istnieje LUB cudzy) →
  **404 maskujące** (parytet z ownership w E5–E8). Trasa `<path:token>` (tokeny FCM bywają długie/zawierają `:`,`-`,`_`).
- **D7 — Wysyłka FCM w tle przez istniejący wątek `send_to_user`** (już w `_fire_and_forget`). Brak nowego
  executora. Multi-device: pętla po wszystkich tokenach usera; snapshot off-session jak Web Push.
- **D8 — Sprzątanie tokenów wg odpowiedzi FCM:** HTTP 404 / `UNREGISTERED` oraz 400 `INVALID_ARGUMENT`
  (token) → **DELETE wiersza** (nieaktualny). 401/403 (nasz misconfig/auth) → log, NIE usuwaj. 429/5xx
  (transient) → log, zostaw. 200 → `last_used_at=now`. Mikro-transakcje z reużyciem `_is_lock_timeout`/retry (parytet z Web Push).
- **D9 — Cache OAuth2 access tokenu:** modułowy `service_account.Credentials` + `threading.Lock`; `refresh()`
  tylko gdy `not creds.valid` (google-auth sam pilnuje wygaśnięcia). Scope `firebase.messaging`.
- **D10 — Payload FCM:** `message.notification{title,body}` + `message.data{url,tag}` (parytet z payloadem
  Web Push, który niesie `url`/`tag` do nawigacji w apce). `tag` mapowany też na `android.notification.tag` /
  `apns.payload.aps.thread-id` (kolapsowanie powiadomień jak `tag` w Web Push).
- **D11 — W testach wysyłka FCM MOCKOWANA** — patchujemy `PushManager._send_fcm_raw` (lub `requests.post`)
  oraz `_get_fcm_access_token`; testujemy `send_to_user` SYNCHRONICZNIE (bez `_fire_and_forget`, by uniknąć
  flaky wątków). Realny FCM nigdy nie wołany.

> **Decyzje — ROZSTRZYGNIĘTE (Konrad 2026-06-13):** D-FCM = **HTTP v1** (legacy wygaszony przez Google).
> D-Back-in-stock = **opcja A, wariant „obok"**: `notify_back_in_stock` wpięte ADDYTYWNIE w gałąź
> e-mail-fallback `socket_events.py` — back-in-stock leci na e-mail (jak dziś) ORAZ Web Push + FCM.
> **Task 5 AKTYWNY** (nie warunkowy), z dwustopniową adwersaryjną recenzją żywego kodu.
>
> **(historyczne — rozgałęzienia przedstawione Konradowi):**
> 1. **FCM HTTP v1 (rekomendacja)** vs legacy server key — legacy wyłączony przez Google, więc to formalność. ✔ proponuję v1.
> 2. **„Produkt wrócił" jako push w E10 (Task 5)** — to JEDYNE wspólne zdarzenie ze specu sek. 9 bez kanału
>    push dziś (idzie WS-on-page + e-mail). Opcje:
>    - **(A, rekomendowana)** Dołożyć `PushManager.notify_back_in_stock` wpięte ADDYTYWNIE w gałąź
>      e-mail-fallback `_check_notification_subscriptions` (`socket_events.py` — LIVE). Wówczas back-in-stock
>      trafia na Web Push **i** FCM. Podpytanie: push **zamiast** e-maila czy **obok** (e-mail + push) gdy
>      user offline? Domyślnie proponuję **obok** (e-mail zostaje, push dodatkowo — parytet z innymi zdarzeniami,
>      które mają e-mail+push). Wymaga dwustopniowej recenzji (kod LIVE).
>    - **(B)** Zostawić back-in-stock na e-mailu; E10 dostarcza tylko kanał FCM + rejestrację; back-in-stock
>      push jako osobny mini-etap. Mniejsze ryzyko (zero dotknięcia `socket_events.py`).
>    **Pozostałe zdarzenia (status/płatność/przypomnienie/nowa oferta/koszt/wysyłka) i tak dostają FCM
>    automatycznie** przez rozszerzenie `send_to_user` — bez wyboru, bez ryzyka.

---

## 4. Struktura plików

| Plik | Zmiana | Task |
|------|--------|------|
| `modules/api_mobile/models.py` | **+model `MobileDevice`** (minimalny, `fcm_token` unique) | 1 |
| `migrations/versions/<rev>_add_mobile_device.py` | **NOWY** — `create_table mobile_device`; `Revises: c72aad290158`; downgrade=samo `drop_table` | 1 |
| `modules/api_mobile/push_routes.py` | **NOWY** — `POST /push/devices` (upsert), `DELETE /push/devices/<path:token>` | 2, 3 |
| `modules/api_mobile/__init__.py` | `from . import push_routes` (na końcu, jak `collection_routes`) | 2 |
| `config.py` | `FIREBASE_CREDENTIALS_PATH` / `FIREBASE_CREDENTIALS_JSON` / `FIREBASE_PROJECT_ID` w `Config` | 4 |
| `.env.example` | sekcja `# Firebase Cloud Messaging (FCM HTTP v1)` (puste = wyłączone) | 4 |
| `utils/push_manager.py` | **ADDYTYWNIE** — `_fcm_enabled`, `_get_fcm_access_token`, `_build_fcm_message`, `_send_fcm_raw`, `_send_fcm_to_user`, `_update_device_success`, `_delete_stale_device`; JEDNO wywołanie w `send_to_user` | 4 |
| `modules/offers/socket_events.py` | *(warunkowy, Konrad opcja A)* 1 addytywny call `notify_back_in_stock` w e-mail-fallback | 5 |
| `tests/test_mobile_api_push.py` | **NOWY** — rejestracja/upsert/DELETE/ownership + kanał FCM (mock) | 2,3,4 |
| `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md` | sek. 9 detale + sek. 11 (E10 ✅) + sek. 12 (wspólny interfejs rozstrzygnięty) | 6 |

---

## 5. Taski (TDD — RED → GREEN per task)

### Task 1 — Model `MobileDevice` + migracja Flask-Migrate
- [ ] **RED:** `tests/test_mobile_api_push.py` — `test_mobile_device_table_and_unique`:
  - insert `MobileDevice(user_id, fcm_token='t1', platform='android')` → ma `id`, `created_at`;
  - drugi insert tego samego `fcm_token` (inny lub ten sam user) → `IntegrityError` (unique);
  - `user_id` FK CASCADE: usunięcie usera kasuje wiersz.
- [ ] **GREEN:** w `modules/api_mobile/models.py` dodaj:
```python
class MobileDevice(db.Model):
    """Token FCM urządzenia mobilnego (push). fcm_token globalnie unikalny — należy
    do dokładnie jednego, aktualnie zalogowanego usera (upsert/przepięcie przy POST)."""
    __tablename__ = 'mobile_device'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    fcm_token = db.Column(db.String(512), nullable=False, unique=True)
    platform = db.Column(db.String(16), nullable=False)   # android | ios | web
    last_used_at = db.Column(db.DateTime, default=get_local_now)
    created_at = db.Column(db.DateTime, default=get_local_now)
```
  (`get_local_now` już importowany w `models.py`).
- [ ] **Migracja:** `flask db migrate -m "Add mobile_device (FCM push tokens)"`; sprawdź plik — ma
  `Revises = 'c72aad290158'`, `create_table('mobile_device', ...)`, index `ix_mobile_device_user_id`,
  unique na `fcm_token`. **`downgrade()` = samo `op.drop_table('mobile_device')`** (lekcja MariaDB FK/index —
  NIE dropować indeksu FK przed drop_table). Następnie `flask db upgrade` (lokalnie, XAMPP).
- [ ] **Commit:** `feat(mobile-api): model MobileDevice + migracja (tokeny FCM)`.

### Task 2 — `POST /push/devices` (rejestracja / upsert)
- [ ] **RED:** testy (helper `_auth`):
  - `test_register_device_requires_jwt` — bez tokenu → 401;
  - `test_register_device_creates` — `{fcm_token:'t1', platform:'android'}` → 201, wiersz dla usera z JWT;
  - `test_register_same_token_same_user_no_dup` — drugi POST `t1` (ten user) → 1 wiersz, `last_used_at` odświeżony;
  - `test_register_token_rebinds_to_caller` — `t1` zarejestrowany przez usera A, POST `t1` przez usera B →
    wiersz `t1` ma `user_id==B` (A już nie posiada), brak duplikatu;
  - `test_register_invalid_platform` → 400 `invalid_input`;
  - `test_register_missing_token` → 400; `test_register_token_too_long` (>512) → 400.
- [ ] **GREEN:** `modules/api_mobile/push_routes.py`:
```python
"""Trasy push (rejestracja/wyrejestrowanie urządzeń FCM) dla mobilnego API (E10)."""
from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db, limiter
from modules.notifications.models import get_local_now
from . import api_mobile_bp
from .helpers import json_ok, json_err
from .models import MobileDevice

_PLATFORMS = {'android', 'ios', 'web'}

@api_mobile_bp.route('/push/devices', methods=['POST'])
@jwt_required()
@limiter.limit("60 per hour")
def register_device():
    uid = int(get_jwt_identity())
    p = request.get_json(silent=True) or {}
    token = (p.get('fcm_token') or '').strip()
    platform = (p.get('platform') or '').strip().lower()
    if not token or len(token) > 512:
        return json_err('invalid_input', 'Pole fcm_token jest wymagane (max 512 znaków).', 400)
    if platform not in _PLATFORMS:
        return json_err('invalid_input', 'Pole platform musi być: android, ios lub web.', 400)
    dev = MobileDevice.query.filter_by(fcm_token=token).first()
    if dev is None:
        dev = MobileDevice(user_id=uid, fcm_token=token, platform=platform)
        db.session.add(dev)
    else:
        dev.user_id = uid          # przepięcie tokenu na bieżącego usera (bezpieczeństwo)
        dev.platform = platform
        dev.last_used_at = get_local_now()
    db.session.commit()
    return json_ok({'id': dev.id, 'platform': dev.platform}, 201)
```
  (rozważ `try/commit/except IntegrityError→rollback+refetch` na wyścig równoległych POST tego samego tokenu —
  parytet z `register` w `auth_routes.py`).
- [ ] **Rejestracja trasy:** `from . import push_routes  # noqa` na końcu `__init__.py`.
- [ ] **Commit:** `feat(mobile-api): POST /push/devices — rejestracja tokenu FCM (upsert)`.

### Task 3 — `DELETE /push/devices/<token>` (wyrejestrowanie)
- [ ] **RED:** testy:
  - `test_delete_device_requires_jwt` → 401;
  - `test_delete_own_token` — rejestracja `t1`, DELETE `t1` → 200, wiersz zniknął;
  - `test_delete_foreign_token_404_masking` — `t1` należy do usera A; user B DELETE `t1` → 404, wiersz A NIETKNIĘTY;
  - `test_delete_unknown_token_404` → 404.
- [ ] **GREEN:** w `push_routes.py`:
```python
@api_mobile_bp.route('/push/devices/<path:token>', methods=['DELETE'])
@jwt_required()
def unregister_device(token):
    uid = int(get_jwt_identity())
    dev = MobileDevice.query.filter_by(fcm_token=token, user_id=uid).first()
    if dev is None:
        return json_err('not_found', 'Nie znaleziono urządzenia.', 404)  # maskuje też cudzy token
    db.session.delete(dev)
    db.session.commit()
    return json_ok({'message': 'Wyrejestrowano urządzenie.'})
```
- [ ] **Commit:** `feat(mobile-api): DELETE /push/devices/<token> — wyrejestrowanie (ownership→404)`.

### Task 4 — Kanał FCM w `PushManager` (config + wysyłka HTTP v1, mockowana w testach)
- [ ] **Config:** w `config.py` (obok `VAPID_*`):
```python
    # Firebase Cloud Messaging (FCM HTTP v1) — kanał push dla apki mobilnej
    FIREBASE_CREDENTIALS_PATH = os.getenv('FIREBASE_CREDENTIALS_PATH', '')   # ścieżka do service-account JSON
    FIREBASE_CREDENTIALS_JSON = os.getenv('FIREBASE_CREDENTIALS_JSON', '')   # alternatywnie surowy JSON
    FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID', '')               # override; inaczej z JSON
```
  + sekcja w `.env.example` (puste = FCM wyłączony).
- [ ] **RED:** testy (`monkeypatch`/`unittest.mock`) — patch `PushManager._send_fcm_raw` i `_get_fcm_access_token`,
  ustaw fake config (`app.config['FIREBASE_PROJECT_ID']='p'` + stub creds), rejestruj `MobileDevice` ręcznie,
  woła `PushManager.send_to_user(...)` SYNCHRONICZNIE:
  - `test_fcm_sent_to_device` — 1 urządzenie → `_send_fcm_raw` wołane raz; message ma `token`,
    `notification.title/body`, `data.url/tag`;
  - `test_fcm_multi_device` — 3 urządzenia usera → 3 wywołania;
  - `test_fcm_unregistered_deletes_token` — `_send_fcm_raw` rzuca/oddaje 404 `UNREGISTERED` → wiersz usunięty;
  - `test_fcm_transient_keeps_token` — 503 → wiersz zostaje;
  - `test_fcm_disabled_noop` — brak FIREBASE config → `_send_fcm_raw` NIE wołane, Web Push nietknięty;
  - `test_fcm_respects_preference_off` — `NotificationPreference.<typ>=False` → ani Web Push, ani FCM (parytet);
  - `test_existing_notify_reaches_fcm` — np. `PushManager.notify_status_change(order, a, b)` (z `_fire_and_forget`
    spatchowanym na sync) → urządzenie dostaje FCM (dowód integracji wszystkich zdarzeń bez zmian call-site);
  - `test_web_push_unchanged_without_devices` — brak `MobileDevice` → zachowanie Web Push 1:1 (parytet).
- [ ] **GREEN:** w `utils/push_manager.py` ADDYTYWNIE:
  - `_fcm_enabled()` → bool (jest project_id + (path|json));
  - `_get_fcm_access_token()` — modułowy cache `Credentials` (`service_account.Credentials.from_service_account_file`/
    `from_service_account_info`, scope `.../auth/firebase.messaging`) + `threading.Lock`; `refresh()` gdy `not valid`;
  - `_build_fcm_message(token, title, body, url, tag)` → dict v1 (D10);
  - `_send_fcm_raw(token, message, access_token, project_id)` — `requests.post(FCM_URL, json={'message':...},
    headers={'Authorization': f'Bearer {access_token}'}, timeout=10)`; podnosi/raportuje status (do mapowania D8);
  - `_send_fcm_to_user(user_id, title, body, url, tag)` — gdy `not _fcm_enabled()` → return; snapshot
    `MobileDevice` tokenów off-session; pętla: `_send_fcm_raw`; wg D8 → `_delete_stale_device(id)` lub
    `_update_device_success(id)` (mikro-transakcje + `_is_lock_timeout` retry);
  - w `send_to_user`, PO bloku Web Push (przed `return sent`), dodaj:
    `try: PushManager._send_fcm_to_user(user_id, title, body, url, tag)` `except Exception: log` — FCM nie może
    wywrócić Web Pusha ani notyfikacji.
- [ ] **Commit:** `feat(push): kanał FCM (HTTP v1) w PushManager — multi-device, sprzątanie stale tokenów`.

### Task 5 — *(WARUNKOWY — tylko jeśli Konrad wybierze opcję A)* push „produkt wrócił"
> Dotyka LIVE `socket_events.py` → ZMIANA ADDYTYWNA + dwustopniowa adwersaryjna recenzja przed jakimkolwiek mergem.
- [ ] **RED:** test — gdy back-in-stock i user offline (brak aktywnego sid) → `PushManager.notify_back_in_stock`
  wołane (mock), a (per decyzja Konrada) e-mail wołany/niewołany.
- [ ] **GREEN:** nowy `PushManager.notify_back_in_stock(user_id, product_name, page_name, page_url)` (wzorzec
  `notify_new_offer_page`/`_fire_and_forget`, `notification_type='new_exclusive_pages'` lub dedykowany typ —
  potwierdzić mapowanie preferencji); 1 addytywny call w gałęzi e-mail-fallback `_check_notification_subscriptions`
  (`socket_events.py:~263`), w `try/except`, bez zmiany istniejącej logiki WS/e-mail.
- [ ] **Commit:** `feat(push): powiadomienie „produkt wrócił" na Web Push + FCM`.

### Task 6 — Aktualizacja specu + finalny suite
- [ ] **Spec** `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md`:
  - sek. 9: model `mobile_device` (pola, `fcm_token` unique/upsert, hard-delete stale), endpointy,
    FCM HTTP v1 (google-auth+requests, service account w env), multi-device, integracja przez `send_to_user`;
  - sek. 11: **E10 ✅**;
  - sek. 12: pozycja „Strategia migracji FCM vs Web Push" → **rozstrzygnięte: jeden wspólny interfejs (`send_to_user` multi-kanał)**.
- [ ] **Suite:** `source venv/bin/activate && python -m pytest -q` → zielono, zero regresji (Web Push/WS parytet).
- [ ] **Commit:** `docs(mobile-api): kontrakt E10 (push FCM — rejestracja urządzeń + kanał w PushManagerze)`.

---

## 6. Ryzyka i mitygacje

| Ryzyko | Mitygacja |
|--------|-----------|
| Blok FCM wywraca Web Push / zapis notyfikacji | FCM addytywny po Web Pushu, w `try/except` z logiem; brak config → no-op (test `fcm_disabled_noop`, `web_push_unchanged`). |
| Limit indeksu UNIQUE na długim tokenie (MariaDB) | `VARCHAR(512)` (2048 B ≤ 3072 InnoDB DYNAMIC); alternatywa-hash udokumentowana (D4). Zweryfikować `flask db upgrade` lokalnie. |
| Token współdzielony między userami (to samo urządzenie po przelogowaniu) | `fcm_token` UNIQUE + upsert przepina na bieżącego usera (test `rebinds_to_caller`) — poprzedni nie dostaje cudzych powiadomień. |
| Stale tokeny rosną w bazie | D8: 404/`UNREGISTERED`/invalid → DELETE wiersza; sukces → `last_used_at`. |
| OAuth2 token pobierany na każdą wysyłkę (wolne) | Cache `Credentials` modułowo + `refresh()` tylko gdy wygasł (D9). |
| Misconfig Firebase na prod blokuje Web Push | Brak config → FCM wyłączony gracefully; 401/403 z FCM → log, bez usuwania tokenów (D8). |
| Task 5 dotyka LIVE rezerwacji | Warunkowy, addytywny, dwustopniowa recenzja; domyślnie poza zakresem dopóki Konrad nie zatwierdzi opcji A. |
| Flaky testy przez wątki `_fire_and_forget` | Testy wołają `send_to_user` synchronicznie / patchują `_fire_and_forget` (D11). |

---

## 7. Uwaga deploymentowa (env Firebase na produkcji)

Jak `JWT_SECRET_KEY` / `GOOGLE_OAUTH_CLIENT_IDS` / `VAPID_*` w E0 — service account Firebase konfigurowany
**wyłącznie przez env na serwerze, NIGDY w repo**:
- umieść plik `service-account.json` poza repo (np. `/etc/thunderorders/firebase-sa.json`, prawa `600`,
  właściciel usera usługi) i ustaw `FIREBASE_CREDENTIALS_PATH=/etc/thunderorders/firebase-sa.json`
  (alternatywnie `FIREBASE_CREDENTIALS_JSON='{...}'`); `FIREBASE_PROJECT_ID=thunderorders-8258f` (lub z JSON);
- po wgraniu zmiennych: restart **obu** usług `sudo systemctl restart thunderorders-http thunderorders-ws`;
- do czasu konfiguracji FCM jest **wyłączony gracefully** — Web Push działa bez zmian; auto-deploy przez
  webhook po pushu do `main` (po zgodzie Konrada) nie zależy od obecności pliku SA.
- **Brak nowej zależności** w `requirements.txt` (google-auth + requests już są) → deploy bez zmian środowiska Python.

---

## Definition of Done (E10)

- [ ] `POST /push/devices` rejestruje token (201), ponowny POST = upsert (brak duplikatu, `last_used_at` odświeżony),
      token przepinany na bieżącego usera z JWT; walidacja `platform`/`fcm_token` → `400 invalid_input`; bez JWT → 401.
- [ ] `DELETE /push/devices/<token>` usuwa własny token (200); cudzy/nieistniejący → **404 maskujące** (cudzy wiersz nietknięty).
- [ ] Migracja `mobile_device` z poprawnym łańcuchem (`Revises: c72aad290158`), `downgrade`=samo `drop_table`;
      `flask db upgrade` przechodzi lokalnie.
- [ ] `PushManager.send_to_user` wysyła też FCM (HTTP v1) na wszystkie urządzenia usera; respektuje
      `NotificationPreference`; stale tokeny (404/UNREGISTERED) usuwane; brak config → no-op. **Web Push bit-w-bit bez zmian.**
- [ ] Wszystkie istniejące `notify_*` docierają na FCM bez zmian call-site (dowód: test przez `notify_status_change`).
- [ ] Wysyłka FCM w pełni MOCKOWANA w testach (realny FCM nigdy nie wołany). Brak nowej zależności w `requirements.txt`.
- [ ] *(jeśli opcja A)* „produkt wrócił" leci na Web Push + FCM (Task 5), addytywnie, po dwustopniowej recenzji.
- [ ] Spec sek. 9/11/12 zaktualizowany. Pełny suite zielony (baseline 434 → ~454–460, zero regresji).
- [ ] **NIE pushować bez zgody Konrada. NIE dotykać produkcji.**

**Szacunek testów:** ~+20–26 (Task 2: ~6, Task 3: ~4, Task 4: ~8, Task 1: ~1, Task 5 warunkowo: ~2).
Baseline `434 passed` → cel ~`454–460 passed`. Migracje: **1** (`mobile_device`).
