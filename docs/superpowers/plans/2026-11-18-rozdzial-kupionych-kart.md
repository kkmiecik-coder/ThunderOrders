# Rozdział kupionych kart + zatwierdzenie bez maili — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Akcja rozdziału kart może dotyczyć kupionych produktów (nie tylko gratisów); Excel z odpowiedziami jest dostępny od publikacji; można zakończyć akcję bez rozdziału albo zatwierdzić bez maili, a wtedy klientka nie widzi przydziału.

**Architecture:** Nowe pola `GiftCampaign.kind` (`'gratis'|'zakup'`) i `results_hidden`, nowy status `'zakonczona'`. Uprawnienia liczone z pozycji `is_bonus == (kind == 'gratis')`. Widoki klientki sprawdzają `results_hidden`; admin/WMS bez zmian w widoczności. Algorytm rozdziału bez zmian.

**Tech Stack:** Flask, SQLAlchemy 2, Flask-Migrate/Alembic (MariaDB), Jinja2, vanilla JS, openpyxl, pytest (SQLite in-memory).

**Spec:** `docs/superpowers/specs/2026-11-18-rozdzial-kupionych-kart-design.md`

## Global Constraints

- Testy: `python -m pytest` (w worktree, venv z głównego checkoutu: `../../venv/bin/python -m pytest`).
- Każda zmiana schematu przez migrację Alembic, `down_revision = 'a7d3e9f1c2b4'`; istniejące akcje: `kind='gratis'`, `results_hidden=False`.
- CSS zawsze w jasnym i ciemnym motywie, tokeny motywu (`--primary-color`), cele dotyku ≥ 44px.
- Teksty po polsku. Dla `kind='zakup'` klientka widzi „Twoje karty” zamiast „Gratisowe karty”.
- Lokalnie maile tylko do pułapki SMTP (MAIL_SERVER=127.0.0.1, MAIL_PORT=2525). Bez pushowania.
- Commity: polskie conventional commits, stopka `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Nowe dokumenty w `docs/superpowers` dodawać `git add -f`.

## Review Focus

1. Pozycja zwykła (nie-gratis) z produktem, który jest w akcji „gratis”, nie może dawać uprawnień i odwrotnie — test w Task 2.
2. Listy zamówień w adminie wołają etykietę kart dla każdej pozycji: dla zwykłych pozycji bez akcji „zakup” nie może być dodatkowych zapytań per pozycja — test liczby zapytań w Task 2.
3. Po „Zatwierdź bez maili” klientka nie widzi kart nigdzie (strona akcji, szczegóły zamówienia), a admin/WMS widzą — testy w Task 4.
4. Cofnięcie zatwierdzenia czyści `results_hidden`, a ponowne „Zatwierdź i wyślij maile” wysyła maile — test w Task 3.
5. Zmiana `kind` po publikacji jest ignorowana (podrobiony POST) — test w Task 5.

---

### Task 1: Model i migracja

**Files:**
- Modify: `modules/gift_cards/models.py`
- Create: `migrations/versions/b8e4f2a6d1c3_rodzaj_akcji_i_ukryty_wynik.py`
- Test: `tests/test_gift_cards_service.py`

**Interfaces:**
- Produces: `KIND_GRATIS = 'gratis'`, `KIND_PURCHASE = 'zakup'`, `STATUS_FINISHED_MANUAL = 'zakonczona'` w `models.py`; `GiftCampaign.kind` (String(10), NOT NULL, default `KIND_GRATIS`, server_default `'gratis'`), `GiftCampaign.results_hidden` (Boolean, NOT NULL, default False, server_default `'0'`), property `GiftCampaign.is_purchase -> bool`.

- [ ] **Step 1: Test** `test_campaign_defaults_kind_gratis_and_results_visible`: nowa `GiftCampaign(name='X')` po commit ma `kind == 'gratis'`, `results_hidden is False`, `is_purchase is False`; z `kind='zakup'` → `is_purchase is True`.
- [ ] **Step 2:** Uruchom — FAIL (brak atrybutów).
- [ ] **Step 3:** Dodaj stałe, kolumny, property. Migracja: `add_column` obu kolumn z `server_default`; downgrade: `drop_column` obu; dodatkowo w downgrade `UPDATE gift_campaigns SET status='zamknieta' WHERE status='zakonczona'`.
- [ ] **Step 4:** Test PASS; lokalnie (kopia bazy lokalnej przed!) `flask db upgrade` → `downgrade` → `upgrade` bez błędów.
- [ ] **Step 5:** Commit `feat(gratisy): rodzaj akcji i ukryty wynik w modelu + migracja`.

### Task 2: Uprawnienia i etykiety kart dla kupionych produktów

**Files:**
- Modify: `modules/gift_cards/service.py` (`compute_entitlements`, `item_gift_label`, `_campaign_for_item`, `open_campaign_for_item`)
- Modify: `modules/orders/models.py` (properties `gift_cards_label`, `client_gift_cards_label`, `open_gift_campaign`)
- Modify: `templates/admin/orders/list.html`, `templates/admin/orders/detail.html`, `modules/orders/wms.py` — usuń warunek `if item.is_bonus` przed etykietą (funkcja sama zwraca None).
- Test: `tests/test_gift_cards_service.py`

**Interfaces:**
- Produces: `item_gift_label(item, for_client=False) -> str|None`; `OrderItem.client_gift_cards_label` (= `item_gift_label(self, for_client=True)`); `open_campaign_for_item(item)` działa też dla pozycji zwykłych w akcjach `zakup`.

Zasada: pozycja pasuje do akcji, gdy `item.is_bonus == (campaign.kind == 'gratis')`, produkt jest w pulach akcji i strona zamówienia jest w stronach akcji. Dla pozycji zwykłych najpierw tani strażnik: zbiór `product_id` z pul akcji `zakup` (statusy inne niż szkic), liczony raz na request i trzymany w `flask.g` (poza kontekstem requestu — liczony za każdym razem); produkt spoza zbioru → `None` bez dalszych zapytań. `for_client=True` i akcja zatwierdzona z `results_hidden` → `None`; akcja `zakonczona` → `None` w obu trybach.

- [ ] **Step 1: Testy:**
  - `test_purchase_entitlements_count_regular_items_only`: akcja `zakup` z pulą produktu P; zamówienie z P ×3 zwykłe i P ×2 `is_bonus=True` → `total == 3`.
  - `test_gratis_campaign_ignores_regular_items_of_same_product`: akcja `gratis`, ta sama sytuacja → `total == 2`.
  - `test_purchase_label_pending_then_names_after_approve`: zwykła pozycja → „przydział w toku”, po rozdziale + `approve` → nazwy rodzajów.
  - `test_client_label_hidden_when_results_hidden`: po approve z `results_hidden=True` → `item.gift_cards_label` = nazwy, `item.client_gift_cards_label is None`.
  - `test_regular_item_label_no_extra_queries_without_purchase_campaigns`: w kontekście requestu, 5 zwykłych pozycji, brak akcji `zakup` → łącznie ≤ 1 zapytanie SQL dla wszystkich etykiet (licznik przez `sqlalchemy.event.listen(db.engine, 'before_cursor_execute', …)`).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementacja wg zasady wyżej.
- [ ] **Step 4:** Testy PASS + cały plik `tests/test_gift_cards_service.py` PASS.
- [ ] **Step 5:** Commit `feat(gratisy): uprawnienia i etykiety kart dla kupionych produktów`.

### Task 3: Zatwierdzenie bez maili i zakończenie bez rozdziału

**Files:**
- Modify: `modules/gift_cards/service.py` (`approve`, `revert_approval`, nowe `finish_manual`, `reopen_manual`)
- Modify: `modules/gift_cards/routes_admin.py` (`admin_approve`, nowe trasy, `STATUS_LABELS`)
- Modify: `templates/admin/gift_cards/detail.html`
- Test: `tests/test_gift_cards_admin.py`

**Interfaces:**
- Produces: `approve(campaign, hide_results=False)` ustawia `results_hidden=hide_results` w tym samym warunkowym UPDATE; `revert_approval` ustawia `results_hidden=False`; `finish_manual(campaign)` `zamknieta` → `zakonczona`, z każdego innego statusu `GiftCardsError` (w `zamknieta` przydziałów jeszcze nie ma); `reopen_manual(campaign)` `zakonczona` → `zamknieta`.
- Trasy: `POST /admin/rozdzial-gratisow/<cid>/zatwierdz` czyta pole formularza `bez_maili=1`; `POST …/<cid>/zakoncz` (`admin_finish`), `POST …/<cid>/wznow` (`admin_reopen`).
- `STATUS_LABELS[STATUS_FINISHED_MANUAL] = 'Zakończona (rozdział ręczny)'`.

- [ ] **Step 1: Testy:**
  - `test_approve_without_mails_sends_nothing_and_hides`: POST `zatwierdz` z `bez_maili=1` → status `zatwierdzona`, `results_hidden True`, 0 maili, flash zawiera „bez maili”.
  - `test_approve_with_mails_unchanged`: bez pola → maile wysłane, `results_hidden False`.
  - `test_revert_clears_hidden_then_approve_with_mails_sends`: approve bez maili → cofnij → approve z mailami → maile wysłane.
  - `test_finish_manual_only_from_closed`: z `otwarta` → błąd, status bez zmian; z `zamknieta` → `zakonczona`; `wznow` → `zamknieta`.
  - `test_detail_shows_both_approve_buttons_and_finish_button`: w `rozdzielona` HTML zawiera „Zatwierdź i wyślij maile” i „Zatwierdź bez maili”; w `zamknieta` zawiera „Zakończ bez rozdziału”.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementacja. W `detail.html`: w `zamknieta` przycisk „Zakończ bez rozdziału” (z `data-gc-confirm="Zakończyć bez rozdziału? Sklep nic nie przydzieli ani nie wyśle — rozdzielasz sama z Excela."`); w `rozdzielona` dwa formularze (drugi z ukrytym `bez_maili=1`, potwierdzenie „Zatwierdzić bez maili? Klientki nie zobaczą przydziału.”); w `zakonczona` przycisk „Wznów (cofnij zakończenie)”. Pill CSS dla `gc-pill--zakonczona` (jasny + ciemny).
- [ ] **Step 4:** Testy PASS + `tests/test_gift_cards_admin.py` PASS.
- [ ] **Step 5:** Commit `feat(gratisy): zatwierdzenie bez maili i zakończenie bez rozdziału`.

### Task 4: Widok klientki

**Files:**
- Modify: `modules/gift_cards/routes_client.py`, `modules/gift_cards/service.py` (`dashboard_campaigns`), `modules/gift_cards/emails.py` (temat/tytuł zaproszenia)
- Modify: `templates/client/gift_cards/campaign.html`, `templates/client/gift_cards/_dashboard_widget.html`, `templates/client/orders/detail.html`, `templates/emails/gift_cards_invite.html`, `templates/emails/gift_cards_invite.txt`
- Test: `tests/test_gift_cards_client.py`

**Interfaces:**
- Consumes: `OrderItem.client_gift_cards_label`, `open_campaign_for_item` (Task 2), `results_hidden`, `STATUS_FINISHED_MANUAL` (Task 1, 3).
- Produces: helper `campaign_title(campaign) -> str` w `emails.py`: `'Gratisowe karty'` albo `'Twoje karty'`; używany w tytule strony, kafelku i zaproszeniu.

Zasady: przydział widoczny tylko gdy `status == zatwierdzona and not results_hidden`. Przy ukrytym wyniku i przy `zakonczona` komunikat: „Zapisy są zamknięte. Dziękujemy za ranking!”. Szczegóły zamówienia klientki używają `client_gift_cards_label`; link „Wybierz swoje karty →” dla obu rodzajów („gratisowe” tylko dla gratis).

- [ ] **Step 1: Testy:**
  - `test_client_hidden_results_show_no_cards`: approve z `results_hidden=True` → GET strony akcji nie zawiera nazwy przydzielonego rodzaju w sekcji wyniku, zawiera „Dziękujemy za ranking”.
  - `test_client_order_detail_hides_cards_when_hidden`: szczegóły zamówienia klientki nie zawierają nazwy karty; admin `admin/orders/detail` zawiera.
  - `test_client_finished_manual_shows_thanks`: status `zakonczona` → „Dziękujemy za ranking”, brak „Trwa rozdział kart”.
  - `test_purchase_campaign_titles`: akcja `zakup` → strona akcji ma „Twoje karty”, zaproszenie (temat) „Twoje karty: <nazwa>”; akcja `gratis` bez zmian.
  - `test_purchase_order_item_links_to_open_campaign`: zwykła pozycja w otwartej akcji `zakup` → w szczegółach zamówienia link do strony akcji.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementacja wg zasad.
- [ ] **Step 4:** Testy PASS + `tests/test_gift_cards_client.py` i `tests/test_gift_cards_display.py` PASS.
- [ ] **Step 5:** Commit `feat(gratisy): klientka nie widzi ukrytego wyniku, teksty dla kupionych kart`.

### Task 5: Formularz akcji — rodzaj i listy

**Files:**
- Modify: `modules/gift_cards/routes_admin.py` (`_read_form`, `_bonus_products`, `_pages_with_gratis`, nowe `_purchase_products`, `_all_offer_pages`, `_render_form`, `admin_form`)
- Modify: `templates/admin/gift_cards/form.html`, `static/js/pages/admin/gift-cards.js`, `static/css/pages/gift-cards.css`
- Test: `tests/test_gift_cards_admin.py`

**Interfaces:**
- Produces: pole formularza `kind` (radio: `gratis` / `zakup`), zapisywane tylko gdy `editing_structure` (szkic lub nowa akcja). `_purchase_products(keep_ids=())` = produkty ze zwykłych pozycji zamówień z `offer_page_id IS NOT NULL` + już wybrane, po nazwie. Strony dla `zakup` = wszystkie `OfferPage` po `created_at desc`.

Formularz renderuje oba zestawy list (strony + produkty) w kontenerach `data-gc-kind="gratis"` / `data-gc-kind="zakup"`; JS pokazuje zestaw wybranego rodzaju i ustawia `disabled` na polach ukrytego zestawu (nie idą w POST). Lista produktów „zakup” ma pole „Szukaj produktu” filtrujące po nazwie (bez rozróżniania wielkości liter). Etykiety: „Gratisy — zaznacz…” / „Kupione produkty — zaznacz…”. Pola ilości (`type_quantity_<pid>`) działają dla obu list — `selectedProducts()` czyta tylko widoczny zestaw.

- [ ] **Step 1: Testy:**
  - `test_form_saves_purchase_kind_and_products`: POST nowej akcji `kind=zakup` z produktem zwykłym → `kind == 'zakup'`, pula z tym produktem.
  - `test_kind_ignored_after_publish`: akcja `otwarta` `gratis`, POST edycji z `kind=zakup` → `kind == 'gratis'`.
  - `test_purchase_product_list_contains_regular_bought_products`: GET formularza zawiera produkt kupiony zwykle na stronie oferty w kontenerze `data-gc-kind="zakup"`.
  - `test_invalid_kind_falls_back_to_gratis`: `kind=cokolwiek` → `gratis`.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementacja. `node --check static/js/pages/admin/gift-cards.js`.
- [ ] **Step 4:** Testy PASS + `tests/test_gift_cards_admin.py` PASS.
- [ ] **Step 5:** Commit `feat(gratisy): wybór rodzaju akcji i lista kupionych produktów w formularzu`.

### Task 6: Excel z odpowiedziami od publikacji

**Files:**
- Modify: `modules/gift_cards/routes_admin.py` (`admin_excel`, `_detail_rows`), `modules/gift_cards/export.py`, `templates/admin/gift_cards/detail.html`
- Test: `tests/test_gift_cards_admin.py`

**Interfaces:**
- Produces: wiersz `_detail_rows` ma `'ranking_text'`: `"1. San, 2. Yunho, …"` z ważnego rankingu (`_valid_ranking`) albo `''`. Kolumna Excela „Ranking” zaraz po „Kart”.

- [ ] **Step 1: Testy:**
  - `test_excel_available_when_open_without_assignments`: akcja `otwarta`, klientka z rankingiem → 200, arkusz „Klientki” ma kolumnę „Ranking” z „1. San, 2. Yunho”, „Przydzielone karty” pusta.
  - `test_excel_blocked_in_draft`: `szkic` → przekierowanie z flash.
  - `test_excel_filename_prefix_by_kind`: `zakup` → nazwa zaczyna się od `karty_`, `gratis` → `gratisy_`.
  - Istniejące testy Excela przechodzą po przesunięciu kolumn.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementacja; przycisk „Pobierz Excel” widoczny dla każdego statusu poza szkicem.
- [ ] **Step 4:** Testy PASS; potem pełny `python -m pytest` w tle (znane 7 błędów testów pupili — poza zakresem).
- [ ] **Step 5:** Commit `feat(gratisy): Excel z rankingiem dostępny od publikacji akcji`.

### Task 7: Próba lokalna

- [ ] Kopia lokalnej bazy → `flask db upgrade` → serwer z pułapką SMTP. Przejście: akcja `zakup` → publikacja → ranking klientki → Excel → zakończ bez rozdziału / rozdziel → zatwierdź bez maili → widok klientki bez kart. Ekrany admina za logowaniem przeklikuje Karolina.
