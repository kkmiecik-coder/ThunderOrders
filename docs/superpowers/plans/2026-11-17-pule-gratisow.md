# Pule gratisów — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jedna akcja gratisowych kart obsługuje kilka produktów-gratisów (pul) ze wspólnym rankingiem i kolejką, plus uwagi klientek.

**Architecture:** Pula = produkt-gratis w akcji (`GiftCampaignPool`); stan per pula×rodzaj (`GiftPoolStock`); przydział ma `pool_id`. Uprawnienia liczone per pula, rozdział = `allocate()` wywołane osobno dla każdej puli z tą samą kolejką i rankingiem. `allocation.py` bez zmian.

**Tech Stack:** Flask, SQLAlchemy, Alembic (MariaDB), Jinja2, vanilla JS, openpyxl, pytest.

**Spec:** `docs/superpowers/specs/2026-11-17-pule-gratisow-design.md`

## Global Constraints

- Testy: `python -m pytest` (gołe `pytest` nie działa). Pełny zestaw tylko w tle, raz na końcu.
- Teksty UI i komunikaty po polsku; CSS jasny+ciemny; cele dotyku 44px.
- Każda zmiana schematu przez migrację Alembic z ręcznie sprawdzonym upgrade/downgrade.
- Stare akcje (jedna pula) muszą działać identycznie jak dziś.
- Powtórka = ten sam rodzaj dwa razy u jednej osoby **w tej samej puli**.
- Uwagi klientki: max 1000 znaków, zapisywane tylko gdy akcja otwarta.

## Review Focus

- Akcja, w której klientka ma uprawnienie tylko w jednej z pul — widzi i dostaje tylko tę pulę.
- Rodzaj z ilością 0 w jednej puli — rozdział nie może go przydzielić w tej puli.
- Ręczna zamiana karty — powtórki i nadmiar liczone w obrębie puli przydziału.
- Edycja szkicu: zmiana wybranych gratisów zachowuje ilości pul, które zostały.
- Migracja istniejącej akcji (prod/lokalnie): przydziały i ilości trafiają do jednej puli.

---

### Task 1: Model + migracja

**Files:** `modules/gift_cards/models.py`, `migrations/versions/a7d3e9f1c2b4_pule_gratisow.py`, testy w `tests/test_gift_cards_service.py`

**Interfaces — Produces:**
- `GiftCampaignPool(id, campaign_id, bonus_product_id, sort_order)`, `.bonus_product`, `.label` (nazwa produktu, strip; fallback „Gratis #id”), `.stock` (lista `GiftPoolStock`).
- `GiftPoolStock(id, pool_id, card_type_id, quantity)`.
- `GiftCampaign.pools` (order sort_order,id), `GiftCampaign.bonus_product_ids` (property).
- `GiftCampaign.stock_map() -> dict[(pool_id, type_id), int|None]`.
- `GiftAssignment.pool_id`, `.pool`; `GiftParticipant.notes`.
- Usunięte: `GiftCampaign.bonus_product_id/bonus_product`, `GiftCardType.quantity`.

- [ ] Testy modelu (unikat pula w akcji, label), migracja z backfillem i downgrade, `flask db upgrade` na lokalnej bazie z akcją „Aniteez” → 1 pula, ilości i przydziały przeniesione.

### Task 2: Serwis

**Files:** `modules/gift_cards/service.py`, `tests/test_gift_cards_service.py`

**Interfaces — Produces:**
- `Entitlement.pool_items: dict[pool_id, list[(item_id, qty)]]`, `Entitlement.pool_total(pool_id) -> int`; `items`/`total` = suma wszystkich pul.
- `compute_entitlements(campaign)` — produkt pozycji → pula.
- `run_distribution` — walidacja: każda para pula×rodzaj ma int ≥ 0; dla każdej puli `allocate(people_z_need>0, stock_puli)`.
- `type_usage(campaign) -> list[(pool, type, assigned, quantity)]`.
- `swap_assignment` — powtórki/miejsca w rankingu liczone w puli przydziału.
- `_campaign_for_item` — po `pools.any(bonus_product_id=...)`.

- [ ] Testy: dwie pule z osobnymi uprawnieniami; osoba tylko w jednej puli; ten sam rodzaj w dwóch pulach nie jest powtórką; ilość 0 w puli; problemy stanu per pula.

### Task 3: Panel admina + Excel

**Files:** `routes_admin.py`, `templates/admin/gift_cards/form.html`, `detail.html`, `static/js/pages/admin/gift-cards.js`, `export.py`, `tests/test_gift_cards_admin.py`

- Formularz: `bonus_product_ids` (multi), ilości `type_quantity_<product_id>` (lista wyrównana z wierszami); JS dokłada/usuwa pola ilości po zmianie wyboru gratisów.
- Szczegóły: siatka ilości `quantity_<pool_id>_<type_id>`, użycie per pula, znacznik puli przy karcie (gdy >1 pula), uwagi klientki w wierszu.
- Excel: kolumny rodzaj×pula, karty pogrupowane po pulach, „Uwagi klientki”, podsumowanie per pula.

- [ ] Testy: tworzenie akcji z dwiema pulami i ilościami; zapis ilości w szczegółach; Excel z dwiema pulami i uwagami.

### Task 4: Klientka, maile, kafelek

**Files:** `routes_client.py`, `templates/client/gift_cards/campaign.html`, `emails.py`, szablony maili, `service.dashboard_campaigns`, `tests/test_gift_cards_client.py`

- Rozbicie uprawnień per pula na stronie i w mailu zaproszenia (gdy >1 pula); wynik pogrupowany po pulach.
- `POST /gratisy/<cid>/uwagi` — zapis uwag (tylko otwarta, ≤1000 znaków).

- [ ] Testy: rozbicie na stronie i w mailu; zapis uwag, odrzucenie po zamknięciu i za długich.

### Task 5: Weryfikacja

- [ ] Pełny `python -m pytest` w tle; próba lokalna na kopii z akcją Aniteez (pułapka SMTP); commit.
