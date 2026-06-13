# Mobile API — Etap E9 (Socket.IO dla apki: auth JWT + rezerwacja przez WS + cross-device takeover) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (rekomendowane).
> Etap dotyka ŻYWEGO kodu rezerwacji LIVE (`socket_events.py`) — zmiany WYŁĄCZNIE ADDYTYWNE,
> obowiązkowa dwustopniowa adwersaryjna recenzja jak przy E3. Kroki = checkboxy `- [ ]`.

**Goal:** Aplikacja mobilna rezerwuje na stronach ofertowych przez WebSocket (parytet z webem: WS
główne + HTTP z E3 jako fallback), z autoryzacją połączenia przez JWT i **przejmowaniem sesji między
urządzeniami** (otwarcie apki przejmuje aktywną sesję rezerwacji usera z weba i odwrotnie — jedna
aktywna sesja na usera, z transferem rezerwacji). Apka słucha też broadcastów dostępności w roomie.

```
WS (apka, połączenie z JWT w auth/query):
  connect                    → auth JWT, wiązanie sid→user_id (tożsamość z tokenu)
  join_offer_reservation     → (te same zdarzenia co web) dołączenie + takeover po user_id
  reserve_product            → rezerwacja (tożsamość z JWT-związanego sid, NIE z payloadu)
  extend_reservation         → przedłużenie
  release_product            → zwolnienie
  (nasłuch) availability_updated / page_status_changed / deadline_changed / force_disconnect
```

---

## 0. Zmiana zakresu względem rev. 1 i rev. 2 (DECYZJE KONRADA)

- **rev.1 → rev.2:** apka NIE tylko słucha — **rezerwuje przez WS** (parytet z webem). HTTP reserve/
  extend/release z E3 zostają jako fallback (jak web: WS główne, HTTP fallback).
- **rev.2 → rev.3 (TEN PLAN):** rezerwacja apki ma uczestniczyć w **przejmowaniu sesji między
  urządzeniami** (Konrad, 2026-06-13). Otwarcie apki przez zalogowanego usera przejmuje jego aktywną
  sesję rezerwacji na webie (`force_disconnect` + transfer rezerwacji) i odwrotnie — reguła „jeden
  aktywny user = jedna sesja rezerwacji" rozciągnięta na web↔mobile. To **unieważnia wariant (b)**
  z poprzedniej rewizji (osobne, izolowane handlery mobilne NIE uczestniczyłyby w takeover).

---

## 1. Zweryfikowane fakty (z badania kodu — file:line, NIE odkrywaj ponownie)

- **Brak jakiegokolwiek `@socketio.on('connect')`** (grep całego repo) — można dodać globalny connect
  handler bez nadpisywania niczego. Połączenia są dziś akceptowane bezwarunkowo.
- **Tożsamość wchodzi do systemu rezerwacji TYLKO w jednym miejscu:** `socket_events.py:467`
  `user_id = data.get('user_id')` w `handle_join_offer_reservation`. Stamtąd:
  - `:525` `state.set_user_session(page_id, user_id, sid)` — rejestr dla TAKEOVER (klucz: user_id).
  - `:571` `state.set_client(sid, page_id, 'reservation', session_id=session_id, user_id=user_id)`
    — rekord klienta (źródło tożsamości dla akcji).
- **Akcje NIE czytają tożsamości z payloadu** — biorą ją z rekordu klienta po sid:
  - `handle_reserve_product` (`:606`): `:638` `if not client.get('user_id')` (login_required),
    `:652` `reserve_product(..., user_id=client.get('user_id'))`.
  - `handle_release_product` (`:676`), `handle_extend_reservation` (`:715`): analogicznie, czytają
    `client = get_state().get_client(sid)`.
- **TAKEOVER (`handle_join_offer_reservation`):** duplikat po `session_id` (`:490` okolice) ORAZ
  **duplikat po `user_id`** (`:504` okolice): `old_user_sid = state.get_user_session(page_id, user_id)`
  → jeśli inny sid → `socketio.emit('force_disconnect', {...}, to=old_user_sid)` + `leave_room` +
  `_cleanup_reservation_client(old_user_sid)` + **transfer rezerwacji** ze starej `session_id` na nową
  (`OfferReservation.session_id` przepisywany, z lockiem DB). **Mechanizm jest keyed na user_id —
  device-agnostyczny.** Gdy apka i web rejestrują się pod tym samym user_id, takeover działa w OBU
  kierunkach automatycznie.
- **Disconnect:** jedyny `@socketio.on('disconnect')` w `wms_events.py` (`handle_disconnect`),
  deleguje do `handle_offer_disconnect` (`socket_events.py:~800`: czyści reservation client i
  `user_session` gdy `state.get_user_session(page_id, user_id) == sid`). NIE wolno rejestrować drugiego
  `disconnect` (nadpisałby WMS — komentarz `socket_events.py:823`).
- **`reservation.py` serwis** (wspólny web+HTTP-E3+WS): `reserve_product(session_id, page_id,
  product_id, quantity, section_max=, user_id=, selected_size=)` (`:139`), `release_product(...,
  user_id=)` (`:325`, `:346` filtr po user_id gdy podany), `extend_reservation(..., user_id=)`
  (`:366`, `:389` filtr). **Anti-overselling = `SELECT FOR UPDATE` + section_max, w bazie** —
  niezależny od tego, czy akcja przyszła z weba czy apki.
- **`socket_events.py` NIE importuje `current_user`** — web NIE autoryzuje połączenia sesją (poza WMS
  w `wms_events.py`). Web deklaruje `user_id` w payloadzie z szablonu `order_page.html:888`.
- **CORS/Origin:** engineio sprawdza CORS **tylko gdy nagłówek `Origin` jest obecny** (natywna apka
  go nie wysyła → przechodzi zawsze, bez wpisu). Lista originów chroni wyłącznie przeglądarki
  (Flutter Web) → przez env, nie wildcard w repo.
- **JWT helpers:** `flask_jwt_extended.decode_token` (zwraca dict z `sub`/`type`/`jti`),
  `MobileTokenBlocklist.contains(jti)` (app.py:94 callback to robi dla HTTP), identity = `str(user.id)`,
  claim `pwd` (przy refresh sprawdzany w auth_routes — dla connect NIE sprawdzamy pwd, parytet z
  `@jwt_required` które też go nie sprawdza).
- **Testy WS:** `socketio.test_client(app, auth={...}/query_string=/flask_test_client=)` — wymaga
  `SOCKETIO_MESSAGE_QUEUE = None` w TestingConfig (inaczej `RuntimeError` z PubSub managerem).
- **Baseline:** `417 passed`. Migracja: BRAK. `/docs` w .gitignore → `git add -f`.

---

## 2. DECYZJA ARCHITEKTONICZNA (kluczowa) — wariant „a1": minimalna addytywna preferencja tożsamości

**Wybór: (a1)** — apka EMITUJE TE SAME zdarzenia co web (`join_offer_reservation`, `reserve_product`,
`release_product`, `extend_reservation`), a JEDYNA zmiana w żywym kodzie to **preferowanie
tożsamości z JWT-związanego sid** w punkcie wejścia tożsamości (`handle_join_offer_reservation:467`).

**Dlaczego (a1), nie (b) z poprzedniej rewizji ani „pełne (a)" z osobnymi handlerami:**
- Cross-device takeover (wymóg Konrada) jest keyed na `user_id` w `set_user_session`. Żeby apka
  uczestniczyła, MUSI rejestrować się w tym samym stanie przez `join_offer_reservation`. Osobne
  mobilne zdarzenia (wariant b) tego nie robią → brak takeover. **(b) odpada.**
- Skoro apka i tak musi przejść przez `join_offer_reservation`, a akcje (`reserve_product` itd.)
  czytają tożsamość z rekordu klienta (nie z payloadu), to **wystarczy jeden addytywny blok**: w
  join, gdy `sid` jest JWT-związany (`_ws_users[sid]`), użyj tego user_id zamiast payloadowego.
  Reszta — takeover, transfer, reserve/extend/release — działa BEZ ZMIAN.
- **Bezpieczeństwo żywego weba:** web sids NIE są w `_ws_users` → `get_ws_user(sid)` zwraca `None` →
  payload user_id jak dziś → zachowanie webowe BIT-W-BIT identyczne. Zmiana jest czysto addytywna
  (preferencja zachodzi tylko dla połączeń z JWT).
- **Anti-spoofing GRATIS:** dla połączeń apki payloadowy `user_id` jest IGNOROWANY na rzecz tożsamości
  z tokenu — apka nie może podszyć się pod cudzy user_id (czego web-payload dziś nie chroni, bo
  bezpieczeństwo siedzi w bazie; apka dostaje mocniejszą gwarancję).

**Zakres zmian w żywym kodzie:** dokładnie JEDEN addytywny blok w `handle_join_offer_reservation`
(~5 linii, preferencja JWT) + (Task 2) connect handler w NOWYM `api_mobile/ws.py` + 1 linijka hooka
cleanup w `wms_events.handle_disconnect`. `reserve_product`/`release_product`/`extend_reservation`,
maszyneria takeover/transfer, `reservation.py` — **NIETKNIĘTE**.

---

## 3. Decyzje — ROZSTRZYGNIĘTE samodzielnie (delegacja: parytet → bezpieczeństwo żywego weba → prostota)

- **D1 — connect permisywny:** brak tokenu → akceptuj (web/WMS/payment łączą się bez tokenu; odrzucenie zabiłoby produkcję).
- **D2 — głębokość walidacji tokenu = parytet `@jwt_required` + is_active:** decode → `type=='access'` → blocklista → user istnieje i `is_active`. BEZ pwd-fingerprint (parytet z `@jwt_required`).
- **D3 — tylko access token** (refresh odrzucony).
- **D4 — wiązanie sid→user in-memory per-worker** (`_ws_users`, wzorzec `connected_clients` z wms_events; wszystkie zdarzenia sid trafiają do jego workera → poprawne).
- **D5 — apka reużywa zdarzenia webowe** (`join_offer_reservation`/`reserve_product`/`release_product`/`extend_reservation`), zero osobnych `mobile_*` (wariant a1). Tożsamość z `_ws_users[sid]` przez addytywną preferencję w join.
- **D6 — cleanup sid→user:** 1 addytywny hook `cleanup_ws_user(sid)` w `wms_events.handle_disconnect` (try/except, wzór jak istniejący `handle_offer_disconnect`). NIE rejestrujemy drugiego `disconnect`.
- **D7 — `place-order` przez WS: NIE** — web nie ma WS place-order (składa przez HTTP); apka zostaje na HTTP E3.
- **D8 — `product_available` przez WS: NIE w E9** — celowane powiadomienie odłożone do E10/FCM (splecione z user_session; e-mail fallback działa). Nie ruszamy.
- **D9 — CORS w configu (env CSV), natywna apka bez wpisu** (brak Origin → engineio przepuszcza).
- **D10 — apka generuje własne `session_id` (UUID)** jak web/E3 — klucz sesji rezerwacji; user_id (takeover) z JWT.

> **Do Konrada — potwierdzenia (nie blokują startu, wszystkie rekomendacje przyjęte regułą delegacji):**
> wariant (a1) zamiast osobnych handlerów; `product_available`→E10; `place-order` zostaje na HTTP.
> Zmiana zakresu „cross-device takeover" jest decyzją Konrada (sekcja 0).

---

## 4. Struktura plików

| Plik | Zmiana | Task |
|------|--------|------|
| `config.py` | `SOCKETIO_CORS_ORIGINS` (env CSV) w `Config`; `SOCKETIO_MESSAGE_QUEUE=None` w `TestingConfig` | 1 |
| `modules/api_mobile/ws.py` | **NOWY** — `ws_connect` (auth+bind), `get_ws_user`, `cleanup_ws_user`, `_ws_users` | 2 |
| `modules/api_mobile/__init__.py` | `from . import ws` (rejestruje connect) | 2 |
| `modules/orders/wms_events.py` | **1 linijka** hooka `cleanup_ws_user(sid)` w `handle_disconnect` (try/except) | 2 |
| `modules/offers/socket_events.py` | **1 addytywny blok** w `handle_join_offer_reservation` (preferencja JWT) | 3 |
| `tests/test_mobile_api_ws.py` | **NOWY** — testy connect/bind/cleanup + reserve/takeover/parytet | 2, 3 |
| `docs/superpowers/specs/...backend-design.md` | sekcja 8 + lista etapów ✅ | 4 |

---

## 5. Taski (TDD — test najpierw)

### Task 1 — Prerekwizyty config (message_queue off w testach + CORS w configu)

- [ ] **`config.py`** w `class Config` (obok istniejących):
```python
    SOCKETIO_CORS_ORIGINS = [
        o.strip() for o in os.getenv(
            'SOCKETIO_CORS_ORIGINS',
            'https://thunderorders.cloud,http://localhost:5001,'
            'http://localhost:8090,http://127.0.0.1:8090'
        ).split(',') if o.strip()
    ]
```
W `class TestingConfig` (po `RATELIMIT_ENABLED = False`):
```python
    SOCKETIO_MESSAGE_QUEUE = None  # test_client nie współpracuje z PubSub managerem (Redis)
```
- [ ] **`app.py`** (jeśli dziś `socketio_origins` jest hardkodowane): `socketio_origins = app.config.get('SOCKETIO_CORS_ORIGINS', [...])` — zachowaj istniejący fallback.
- [ ] **Walidacja:** `python -m pytest -q` → 417 passed. **Commit:** `feat(ws): konfiguracja CORS + message_queue off w testach (prereq E9)`. **+0 testów.**

---

### Task 2 — `connect` z auth JWT + wiązanie sid→user + czyszczenie przy disconnect

> Testy i implementacja `ws.py` + hook cleanup — wg poniższego (zachowane z rev.2, są poprawne).

- [ ] **Step 1: Testy (RED)** — `tests/test_mobile_api_ws.py` (część 1). Helpery `_access_token`/
  `_refresh_token` (create_access_token/create_refresh_token z identity=str(u.id), claims {'pwd':'x'}).
  Testy: connect z JWT w `auth={'token':...}` → connected; z `query_string='token=...'` → connected;
  BEZ tokenu → connected (parytet web); z cookie sesji (`flask_test_client=client` po `login`) →
  connected; śmieciowy token → `not is_connected`; wygasły (expires_delta=-10s) → odrzucony; refresh
  token → odrzucony; token na blocklist (wpis MobileTokenBlocklist z jti) → odrzucony; user
  `is_active=False` → odrzucony; `test_ws_disconnect_unbinds_sid` → po disconnect `_ws_users` nie ma
  user.id. Run → FAIL (brak ws.py).
- [ ] **Step 2: `modules/api_mobile/ws.py` (NOWY)** — `_ws_users={}`, `_extract_ws_token(auth)`
  (auth dict.token lub `flask_request.args.get('token')`), `@socketio.on('connect') ws_connect(auth=None)`:
  brak tokenu → `return None` (akceptuj); `decode_token` w try/except (błąd → `return False`);
  `type!='access'` → False; `MobileTokenBlocklist.contains(jti)` → False; `db.session.get(User,
  int(sub))` None/`not is_active` → False; inaczej `_ws_users[flask_request.sid]=user.id; return None`.
  Plus `get_ws_user(sid)` (zwraca `_ws_users.get(sid)`) i `cleanup_ws_user(sid)` (`_ws_users.pop(sid, None)`).
- [ ] **Step 3:** `modules/api_mobile/__init__.py` na końcu: `from . import ws  # noqa: E402,F401`.
- [ ] **Step 4:** `modules/orders/wms_events.py` w `handle_disconnect`, ZARAZ po bloku
  `handle_offer_disconnect`, dodać addytywny hook:
```python
    # E9: czyszczenie wiązania sid→user dla połączeń aplikacji mobilnej
    try:
        from modules.api_mobile.ws import cleanup_ws_user
        cleanup_ws_user(sid)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Mobile WS unbind failed for {sid}: {e}")
```
- [ ] **Step 5: GREEN** + pełny suite (417 + ~10). **Commit:** `feat(ws): autoryzacja połączeń Socket.IO przez JWT + wiązanie sid→user`. **+10 testów.**

**DoD:** connect akceptuje (token/query/brak/cookie), odrzuca (śmieć/wygasły/refresh/blocklista/inactive); disconnect czyści mapę; web/WMS bez zmian.

---

### Task 3 — Rezerwacja apki przez WS (reuse zdarzeń web) + cross-device takeover (addytywny blok)

> SERCE etapu. JEDNA addytywna zmiana w żywym `handle_join_offer_reservation` + testy reserve/takeover/
> parytet. NIE dodajemy osobnych `mobile_*` zdarzeń (D5/a1).

- [ ] **Step 1: Testy (RED)** — `tests/test_mobile_api_ws.py` (część 2). Setup strony/sekcji jak E3
  (`OfferPage` exclusive active + `OfferSection` product z `max_quantity`). Pełny przepływ apki przez
  zdarzenia WEBOWE: connect z JWT → `emit('join_offer_reservation', {page_id, session_id, user_id:<dowolny/None>, token})` →
  `emit('reserve_product', {page_id, session_id, product_id, quantity})`.

  Testy:
  - **`test_ws_app_reserve_uses_identity_from_token_not_payload`:** owner łączy się z JWT, w
    `join_offer_reservation` payload `user_id=attacker.id` → po `reserve_product` rezerwacja ma
    `OfferReservation.user_id == owner.id` (z TOKENU, payload zignorowany), quantity poprawne.
  - **`test_ws_web_session_id_takeover_unchanged`:** parytet — dwa połączenia BEZ JWT (web) z tym
    samym `session_id` na różnych sid → drugie `join` wyrzuca pierwsze (`force_disconnect`), payload
    user_id użyty (zachowanie 1:1 z dziś).
  - **`test_ws_cross_device_takeover_app_takes_over_web`:** (1) web-sid (bez JWT) joinuje z
    `user_id=U` (payload), rezerwuje qty=2 na `session_id='web-S'`; (2) app-sid (JWT usera U) joinuje
    z `session_id='app-S'` → web-sid dostaje `force_disconnect` (sprawdź `tc_web.get_received()` ma
    event `force_disconnect`), web-sid wyrzucony z user_session; rezerwacje **przetransferowane** na
    `'app-S'` (`OfferReservation.session_id=='app-S'`, `user_id==U`, qty zachowane). Następnie app
    rezerwuje dalej na tej samej sesji — OK.
  - **`test_ws_cross_device_takeover_web_takes_over_app`:** odwrotny kierunek (app pierwsza, web
    przejmuje) — symetria.
  - **`test_ws_web_reserve_still_works_1to1`:** KRYTYCZNY parytet — pełna webowa ścieżka WS
    (`join_offer_reservation` + `reserve_product`, BEZ JWT, user_id z payloadu) tworzy rezerwację
    przypisaną do payload-user_id, dokładnie jak przed E9.
  Run → FAIL (apka bez JWT-bindingu rezerwuje pod payload user_id; po implementacji — pod JWT).

- [ ] **Step 2: Implementacja — addytywny blok w `modules/offers/socket_events.py`**,
  w `handle_join_offer_reservation`, ZARAZ po `user_id = data.get('user_id')` (l.467):
```python
        # E9: dla połączeń aplikacji mobilnej (sid uwierzytelniony JWT przy connect)
        # tożsamość pochodzi WYŁĄCZNIE z tokenu — payloadowy user_id jest ignorowany
        # (anti-spoofing) i wpinamy się w ten sam mechanizm user_session/takeover co web.
        # Web sids NIE są JWT-związane → get_ws_user zwraca None → payload user_id jak dziś.
        try:
            from modules.api_mobile.ws import get_ws_user
            _jwt_uid = get_ws_user(sid)
            if _jwt_uid is not None:
                user_id = _jwt_uid
        except Exception:
            pass
```
  > UWAGA: `sid = flask_request.sid` jest już ustawione wcześniej w funkcji (l.~470). Jeśli blok
  > trafia PRZED przypisaniem `sid`, użyj `flask_request.sid` bezpośrednio. Zweryfikuj kolejność.
  > To JEDYNA zmiana w tym pliku. `reserve_product`/`release_product`/`extend_reservation`,
  > takeover, transfer — bez zmian (czytają user_id z rekordu klienta, który jest teraz poprawny).

- [ ] **Step 3: GREEN** + pełny suite (zero regresji — szczególnie istniejące testy WS/rezerwacji
  web). **Commit:** `feat(ws): rezerwacja apki przez Socket.IO z tożsamością JWT + cross-device takeover`. **+~6 testów.**

**DoD:** apka rezerwuje przez WS z tożsamością z tokenu (payload zignorowany); cross-device takeover
działa w obu kierunkach (web↔app, z transferem rezerwacji); webowa ścieżka WS rezerwacji 1:1
(parytet); `socket_events.py` zmieniony tylko o 1 addytywny blok.

---

### Task 4 — Nasłuch roomu (broadcasty) + spec sekcja 8 + finalny suite

- [ ] **Step 1: Test nasłuchu** — apka po `join_offer_reservation` jest w roomie kupujących
  (`offer_page_{id}_order`); po akcji wyzwalającej broadcast (np. rezerwacja innego sida lub
  `broadcast_availability_update`) apka odbiera `availability_updated` (`tc.get_received()`). 1-2 testy.
- [ ] **Step 2: Spec** — sekcja 8 „Real-time (Socket.IO) dla apki": apka łączy się z JWT
  (`io(url,{auth:{token}})` / `?token=`), emituje TE SAME zdarzenia co web
  (`join_offer_reservation`/`reserve_product`/`release_product`/`extend_reservation`), tożsamość z
  tokenu (payload user_id ignorowany), **cross-device takeover** (otwarcie apki przejmuje sesję web
  tego usera i odwrotnie — apka MUSI obsłużyć `force_disconnect`), fallback = HTTP reserve z E3 +
  polling availability. `product_available` → E10. Lista etapów: **E9 ✅**.
- [ ] **Step 3:** `python -m pytest -q` → ~`435 passed`, zero regresji, zero migracji. **Commit:**
  `docs(mobile-api): kontrakt E9 (Socket.IO przez JWT + cross-device takeover)`.

---

## 6. Ryzyko regresji żywego WS i mitygacje

| Ryzyko | Mitygacja |
|--------|-----------|
| Nowy `connect` zabija web/WMS (brak tokenu) | D1 permisywny: brak tokenu → akceptuj. Test parytetu cookie + brak-tokenu. |
| Addytywny blok w join zmienia zachowanie weba | Web sids nie w `_ws_users` → `get_ws_user`→None → payload user_id jak dziś. Test `test_ws_web_reserve_still_works_1to1` (pełna ścieżka web 1:1). try/except wokół importu (brak ws.py nie wywróci join). |
| Takeover wyrzuca niewłaściwą sesję | Mechanizm keyed na user_id BEZ ZMIAN; testy obu kierunków + transfer rezerwacji. |
| Drugi `disconnect` nadpisuje WMS | NIE rejestrujemy — hook `cleanup_ws_user` wpięty w istniejący `handle_disconnect` (D6). |
| `_ws_users` per-worker rozjazd | Wszystkie zdarzenia sid → jego worker; mapa lokalna poprawna (wzorzec connected_clients). |
| Overselling z dwóch urządzeń | Niemożliwy — `SELECT FOR UPDATE`+section_max w bazie; dodatkowo takeover gwarantuje 1 sesję/usera. |

**Recenzja:** dwustopniowa adwersaryjna (jak E3) — spec compliance + jakość, z empirycznymi sondami
parytetu web i obu kierunków takeover, PRZED jakimkolwiek pushem.

---

## Definition of Done (E9)

- [ ] `connect` autoryzuje JWT (akceptuje token/query/brak/cookie; odrzuca śmieć/wygasły/refresh/blocklista/inactive), wiąże sid→user; disconnect czyści mapę.
- [ ] Apka rezerwuje/przedłuża/zwalnia przez WS (te same zdarzenia co web), tożsamość z tokenu (anti-spoofing), HTTP z E3 jako fallback bez zmian.
- [ ] Cross-device takeover web↔app działa w obu kierunkach z transferem rezerwacji.
- [ ] `socket_events.py` zmieniony tylko o 1 addytywny blok; webowa ścieżka WS 1:1 (parytet — test krytyczny).
- [ ] Nasłuch broadcastów w roomie. Spec sekcja 8 zaktualizowany. Zero migracji. Pełny suite zielony (~435).
- [ ] Dwustopniowa adwersaryjna recenzja zaliczona. NIE pushować bez zgody Konrada.
