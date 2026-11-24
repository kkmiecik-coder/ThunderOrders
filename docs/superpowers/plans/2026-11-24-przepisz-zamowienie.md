# Przepisanie zamówienia na inną klientkę — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admin przepisuje całe zamówienie albo wybrane pozycje (także część sztuk) na inną klientkę, bez przetasowania kolejki FIFO partii z Korei.

**Architecture:** Cała logika w nowym serwisie `modules/orders/transfer.py` (jedna transakcja, wyjątek `TransferError` z komunikatem po polsku). Cienka trasa JSON w `modules/orders/routes.py` + modal w `templates/admin/orders/detail.html`. Kolejność FIFO dostaje kotwicę `orders.fifo_anchor_order_id` przez wspólny pomocnik `fifo_order_by()`.

**Tech Stack:** Flask, SQLAlchemy, Flask-Migrate (Alembic), MariaDB (testy: SQLite z FK), pytest, vanilla JS.

**Spec:** `docs/superpowers/specs/2026-11-24-przepisz-zamowienie-design.md`

## Global Constraints

- Schemat tylko migracją Alembic; `down_revision = 'c4f1a9e7b2d5'`.
- `orders.user_id` NOT NULL — brak gościa.
- CSS jasny + ciemny; style modali tylko w `static/css/components/modals.css`; cele dotykowe ≥ 44px.
- Commity po polsku, conventional commits, stopka `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Testy uruchamiać per plik: `../../../venv/bin/python -m pytest tests/<plik> -q`. NIGDY pełnego pytest. Bez push.
- Uprawnienia: `@role_required('admin', 'mod')`.

## Review Focus

- Kilka zamówień z tą samą sekundą `created_at` → kolejność i kwoty E2 innych identyczne przed i po przepisaniu (test w Task 1 i Task 4).
- Zamówienie bez powiązań `poland_order_item_orders` (błąd PRX/PL/12+) → przepisanie działa, nic nie wywala (Task 4).
- `customs_vat_sale_cost` NULL u Ani → u Basi NULL, nie 0 (Task 4).
- Przepisanie łańcuchowe (Basia → Celina) → kotwica wskazuje oryginał Ani (Task 3).
- Klientka widzi tylko swoje: Basia nie widzi dowodu przelewu Ani (Task 5).

---

### Task 1: Kotwica kolejki FIFO + migracja

**Files:**
- Create: `migrations/versions/d5a2e8c1f4b7_przepisanie_zamowien.py`
- Modify: `modules/orders/models.py` (Order: kolumna + `fifo_order_by()`; PaymentConfirmation: kolumna)
- Modify: `modules/products/routes.py` (`_allocate_product_shipping_fifo`, `_batch_allocation_for_range`)
- Modify: `utils/offer_closure.py` (pierwsze zapytanie zamówień, ~l. 59)
- Test: `tests/test_order_transfer_fifo.py`

**Interfaces:**
- Produces: `Order.fifo_anchor_order_id` (Integer, FK orders.id ON DELETE SET NULL, index, nullable); `PaymentConfirmation.proof_hidden_for_client` (Boolean, NOT NULL, server_default '0'); `fifo_order_by() -> tuple` w `modules/orders/models.py` zwracające `(Order.created_at.asc(), func.coalesce(Order.fifo_anchor_order_id, Order.id).asc(), Order.id.asc())`.

- [ ] **Step 1: Testy (failing)** — `test_kolejka_bez_kotwicy_jak_dotad`: 4 zamówienia, 3 z tą samą sekundą, ręcznie wyliczona oczekiwana lista `_batch_allocation_for_range(pid, 0, N)` == kolejność `(created_at, id)`; kwoty `_allocate_product_shipping_fifo` z dwiema partiami o różnych stawkach == ręcznie policzone. `test_zamowienie_z_kotwica_staje_za_oryginalem`: A, C (ta sama sekunda, id > A), potem B z `created_at=A.created_at` i `fifo_anchor_order_id=A.id` → kolejność A, B, C. `test_kotwica_zachowuje_kwoty_innych`: A ma 3 szt., C 2 szt., partie 2+3; przenieś 1 szt. z A do B (z kotwicą) → alokacja C identyczna, A+B = stare A.
- [ ] **Step 2:** uruchom, oczekiwany FAIL (brak kolumny).
- [ ] **Step 3:** migracja (add_column ×2, FK `fk_orders_fifo_anchor_order_id`, index `ix_orders_fifo_anchor_order_id`; downgrade odwrotnie), kolumny w modelach, `fifo_order_by()`, użycie w trzech miejscach.
- [ ] **Step 4:** PASS + `tests/test_poland_order_item_allocation.py`, `tests/test_poland_order_split.py` zielone.
- [ ] **Step 5:** commit `feat(zamowienia): kotwica kolejki FIFO dla przepisanych zamówień`.

### Task 2: Serwis — przepisanie całego zamówienia + blokady

**Files:**
- Create: `modules/orders/transfer.py`
- Test: `tests/test_order_transfer.py`

**Interfaces:**
- Produces:
  - `class TransferError(Exception)` (komunikat dla admina po polsku).
  - `sprawdz_blokady(order) -> str | None` — powód blokady albo None (zlecenie wysyłki; status w `ZABLOKOWANE_STATUSY = ('anulowane','do_zwrotu','zwrocone','czesciowo_zwrocone','wyslane','dostarczone')`; `wms_locked_at` lub `wms_session_id`).
  - `przepisz_cale_zamowienie(order, nowa_klientka, admin) -> Order` — nie commituje.
  - `@dataclass WynikPrzepisania(zrodlo: Order, cel: Order, pozycje: list[tuple[str, int]], wplata_poszla: bool, cale: bool)`.

- [ ] **Step 1: Testy (failing)**: `test_cale_zmienia_klientke` (user_id, numer i created_at bez zmian, paid_amount bez zmian); `test_cale_czysci_dane_poprzedniej` (shipping_*, pickup_*, delivery_method, custom_name → None; notes trafia do admin_notes z prefiksem „Notatka poprzedniej klientki: ”, notes None); `test_cale_ukrywa_dowody` (conf z proof_file → proof_hidden_for_client True; bez pliku bez zmian); `test_cale_przenosi_gift_assignments`; `test_cale_dodaje_komentarz_wewnetrzny`; blokady parametryzowane: status `anulowane`/`wyslane`/`dostarczone`, w zleceniu wysyłki, `wms_locked_at`, ta sama klientka, cel z rolą `admin` → `TransferError`.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** implementacja; historia = `OrderComment(is_internal=True, user_id=admin.id)` w zamówieniu z treścią „Przepisano zamówienie z {stara} na {nowa}.” + `log_activity(action='order_transferred')`.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** commit `feat(zamowienia): przepisanie całego zamówienia na inną klientkę`.

### Task 3: Serwis — przepisanie wybranych pozycji (E1, pozycje, walidacja)

**Files:** Modify `modules/orders/transfer.py`; Test `tests/test_order_transfer.py`

**Interfaces:**
- Produces: `przepisz_pozycje(order, nowa_klientka, admin, wybor: list[tuple[int, int]], wplata_za_karta: bool) -> WynikPrzepisania` (wybor = `(item_id, ilosc)`), nie commituje; `czy_pozycja_prosta(item) -> bool`.

- [ ] **Step 1: Testy (failing)**: `test_pozycja_w_calosci_trafia_do_nowego_zamowienia` (nowe zamówienie: user B, typ/status/strona/payment_stages/offer_page_name z A, `created_at == A.created_at`, `fifo_anchor_order_id == A.id`, numer `EX/{B.id}`, `created_by_admin_id == admin.id`; item.order_id == B.id; total_amount A i B przeliczone, suma = stare A); `test_czesc_sztuk_dzieli_pozycje` (A: qty 2→1, B: nowa pozycja qty 1 z tą samą ceną, product_id, selected_size); `test_lancuch_kotwicy` (A→B, potem B→C: C.fifo_anchor_order_id == A.id); walidacja → `TransferError`: pusty wybór, wszystkie pozycje w całości, ilość 0 lub > quantity, część sztuk pozycji z `incl_only_quantity>0` / `fulfilled_quantity<quantity` / gift assignment, item z innego zamówienia; `test_wplata_za_karta_blokowana_przy_oczekujacym` (A ma conf `pending` + wplata_za_karta=True → TransferError; False → OK).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** implementacja (numer przez `order_number_placeholder()` + flush + `assign_order_number(B, A.order_type)`).
- [ ] **Step 4:** PASS. **Step 5:** commit `feat(zamowienia): przepisanie wybranych pozycji do nowego zamówienia`.

### Task 4: Serwis — koszty E2/E3, wpłaty, powiązania z partiami

**Files:** Modify `modules/orders/transfer.py`; Test `tests/test_order_transfer.py`

**Interfaces:**
- Consumes: `_allocate_product_shipping_fifo(pid) -> {order_id: Decimal}` z `modules/products/routes.py`.
- Produces: wewnętrzne `_udzial_e2(...)`, `_udzial_e3(...)`, `_przenies_wplaty(...)`, `_przenies_powiazania_partii(...)`.

- [ ] **Step 1: Testy (failing)**:
  - `test_e2_przechodzi_i_suma_zachowana`: 4-etapowe, partia ze stawką; A.proxy przed = X; po: A+B = X, B = udział, zamówienie C (ta sama sekunda co A) — proxy bez zmian.
  - `test_e3_wg_stawki`: stawka 23% na partii, karta 40 zł × 1 → B.customs 9.20, A −9.20.
  - `test_e3_null_zostaje_null`.
  - `test_wplata_idzie_za_karta`: E1 approved 100 (2 pozycje 60+40), przenosimy 40 → A conf 60, A.paid −40; B ma approved conf `product` 40, proof_file None, B.paid 40; analogicznie E2 approved.
  - `test_wplata_zostaje_u_ani`: wplata_za_karta=False → A.paid bez zmian, B.paid 0, brak conf u B.
  - `test_powiazania_partii_przeniesione`: link A qty 3 → po przeniesieniu 1 szt.: A 2, B 1 (ten sam poland_order_item).
  - `test_bez_powiazan_partii_dziala`.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** implementacja wg spec §„Tryb wybrane pozycje” kroki 3–5 (E2 tylko gdy `payment_stages == 4` i `offer_page_id`; udział przycięty do `[0, A.proxy]`; stawka E3 = `customs_vat_percentage` najnowszej nieanulowanej `PolandOrderItem` produktu; kwoty `quantize(Decimal('0.01'))`).
- [ ] **Step 4:** PASS. **Step 5:** commit `feat(zamowienia): koszty z Korei, cło i wpłaty idą za przepisaną kartą`.

### Task 5: Ukryte dowody przelewu dla klientki

**Files:** Modify `modules/orders/routes.py` (`serve_payment_proof`), `modules/api_mobile/payments_routes.py` (`_proof_url`/serwowanie), widok listy potwierdzeń klienta (`templates/client/payment_confirmations/list.html` i trasa, która ją renderuje); Test `tests/test_order_transfer_proof.py`

- [ ] **Step 1: Testy (failing)**: `test_klientka_nie_pobierze_ukrytego_dowodu` (client GET `serve_payment_proof` → 403; admin → nie 403); `test_lista_klientki_bez_linku_do_ukrytego` (render listy nie zawiera nazwy pliku).
- [ ] **Step 2:** FAIL. **Step 3:** implementacja (klient: `proof_hidden_for_client` → 403 / brak URL-a). **Step 4:** PASS. **Step 5:** commit `fix(platnosci): klientka nie widzi dowodu przelewu poprzedniej właścicielki`.

### Task 6: Powiadomienia

**Files:** Modify `utils/email_manager.py`, `utils/email_sender.py`, `utils/push_manager.py`, `modules/orders/routes.py` (lista przełączników maili, jeśli tam jest), `templates/admin/orders/settings.html` (przełącznik); Create `templates/emails/order_transferred_to.html`, `templates/emails/order_transferred_from.html`; Test `tests/test_order_transfer_notifications.py`

**Interfaces:**
- Produces: `EmailManager.notify_order_transferred(wynik: WynikPrzepisania)`, `PushManager.notify_order_transferred(wynik: WynikPrzepisania)` — każda wysyła do celu (zamówienie, pozycje, kwota) i do źródła (lista pozycji, bez danych celu). Klucz maila `notify_order_transferred`.

- [ ] **Step 1: Testy (failing)** z `maile_synchronicznie` + `mail.record_messages()`: dwie wiadomości; mail do Ani nie zawiera imienia/maila Basi; wyłączony klucz → 0 maili; push przez monkeypatch `PushManager._fire_and_forget` → 2 wywołania.
- [ ] **Step 2–4:** FAIL → implementacja → PASS. **Step 5:** commit `feat(zamowienia): powiadomienia o przepisaniu zamówienia`.

### Task 7: Trasa + modal w panelu admina

**Files:** Modify `modules/orders/routes.py` (nowa trasa), `templates/admin/orders/detail.html` (przycisk w „Szybkie akcje”, modal `#transferOrderModal`), `static/css/components/modals.css`; Create `static/js/pages/admin/order-transfer.js`; Test `tests/test_order_transfer_route.py`

**Interfaces:**
- Produces: `POST /admin/orders/<int:order_id>/transfer`, endpoint `orders.admin_transfer_order`. Body JSON: `{client_id: int, mode: 'whole'|'items', items: [{item_id, quantity}], payment_follows: bool, notify: bool}`. Odpowiedź: `{success, message, redirect_url}`; błąd `TransferError` → 400 `{success: false, message}`.
- Detail template dostaje `transfer_block_reason` (wynik `sprawdz_blokady`) i `simple_item_ids`.

- [ ] **Step 1: Testy (failing)**: klient → 403/302; admin `whole` → 200, user zmieniony; admin `items` → redirect_url do nowego zamówienia; `notify=False` → powiadomienia nie wołane (monkeypatch), `True` → wołane po commicie; zablokowane → 400 z komunikatem; strona detail renderuje przycisk „Przepisz na inną klientkę”.
- [ ] **Step 2–4:** FAIL → implementacja (modal: wyszukiwarka `/api/clients/search` min. 3 znaki, tryb, checkbox+ilość per pozycja, przełączniki domyślnie ✓, CSRF `X-CSRFToken`, toast) → PASS; `node --check static/js/pages/admin/order-transfer.js`.
- [ ] **Step 5:** commit `feat(zamowienia): przycisk i okienko „Przepisz na inną klientkę”`.
