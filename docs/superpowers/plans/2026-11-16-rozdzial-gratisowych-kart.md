# Rozdział gratisowych kart — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nowa zakładka „Rozdział gratisów”: klienci układają ranking rodzajów kart i biorą udział w wyścigu o kolejkę, system rozdziela karty rundami bez powtórek, a po zatwierdzeniu przez Karolinę przydział widać w zamówieniach i w WMS.

**Architecture:** Nowy moduł `modules/gift_cards/` (blueprint jak `modules/contests/`). Serce to czysta funkcja `allocate()` w `allocation.py` (bez bazy, łatwa do testowania): rundy wg kolejki + sprawdzanie przepływem w sieci (osoby × rodzaje), że po każdym przydziale wciąż da się osiągnąć maksymalną liczbę kart bez powtórek. Wokół tego warstwa usług (`service.py`): uprawnienia z pozycji `OrderItem.is_bonus`, kolejka, zapis propozycji, zamiany, zatwierdzanie, cofanie. Do tego trasy admina i klienta, maile i wyświetlanie przydziału przy pozycjach zamówień.

**Tech Stack:** Flask, SQLAlchemy, Flask-Migrate (Alembic, MariaDB), Jinja2, vanilla JS, pytest (SQLite w testach).

**Spec:** `docs/superpowers/specs/2026-11-16-rozdzial-gratisowych-kart-design.md`

## Global Constraints

- Python 3.10+; testy uruchamiać przez `python -m pytest` (nie `pytest`). Podagent uruchamia TYLKO pliki testów swojego zadania, nigdy pełnej suity — pełną suitę puszcza kontroler w tle.
- Każda zmiana schematu przez Flask-Migrate (`flask db migrate` → ręczny przegląd pliku). Jedna gałąź migracji: przed generowaniem sprawdź `flask db heads` (oczekiwany jeden head; obecnie `e3b9a6c1d4f7` lub nowszy). FK zawsze z jawnym `ondelete`.
- Czas: kolumny `UTCDateTime`, domyślnie `utcnow` (`utils.timeutil`); daty z formularza przez `pl_input_to_utc`, wyświetlanie przez `to_pl`, do JS przez `iso_utc`.
- Logowanie wymagane wszędzie (brak gości). Admin: `@login_required` + `@role_required('admin', 'mod')`.
- Wysyłka wielu maili: `prepare_email()` + `send_email_batch()` (jedno połączenie SMTP).
- CSS zawsze w wersji jasnej i ciemnej; style modali tylko w `static/css/components/modals.css`; elementy dotykowe min. 44px; CSRF w każdym POST (formularze: `csrf_token()`, fetch: nagłówek `X-CSRFToken`).
- Teksty UI po polsku. Commity po polsku, konwencja `feat(gratisy): …`, `test(gratisy): …`, zakończone linią `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Praca na gałęzi `feat/rozdzial-gratisow`. Nigdy `git push` (push = wdrożenie na produkcję; tylko Karolina decyduje). Nie commitować `.env`.
- Nie ruszać naliczania gratisów w `modules/offers/place_order.py`.

## Review Focus

1. **Podwójne kliknięcie „Zgłaszam się”** (dwa POSTy tego samego klienta w tej samej chwili) → jedno miejsce w kolejce, drugi POST zwraca to samo miejsce. Test: Task 7.
2. **Spreparowany ranking** (id rodzaju z innej akcji, powtórzone miejsce, brak rodzaju) → 400, nic nie zapisane. Test: Task 7.
3. **Osoba bez uprawnień** (zalogowana, ale bez gratisu z tej akcji) wchodzi na stronę akcji albo klika wyścig → „Ta akcja Cię nie dotyczy” / 403. Test: Task 7.
4. **Brak ilości przy rodzaju albo akcja bez uprawnionych** → „Rozdziel” odmawia z czytelnym komunikatem / daje pusty wynik bez błędu 500. Test: Task 4.
5. **Ręczna zamiana przekraczająca stan** (więcej sztuk rodzaju niż wpisano) → odrzucona z komunikatem. Test: Task 4.

---

## Struktura plików

| Plik | Odpowiedzialność |
|---|---|
| `modules/gift_cards/__init__.py` | blueprint `gift_cards_bp`, import tras i modeli |
| `modules/gift_cards/models.py` | `GiftCampaign`, `GiftCampaignPage`, `GiftCardType`, `GiftParticipant`, `GiftRaceEntry`, `GiftAssignment` |
| `modules/gift_cards/allocation.py` | czysty algorytm `allocate()` |
| `modules/gift_cards/service.py` | uprawnienia, kolejka, rozdział, zamiany, zatwierdzanie, cofanie, etykiety pozycji |
| `modules/gift_cards/emails.py` | maile zaproszenia i wyniku (batch) |
| `modules/gift_cards/routes_admin.py` | zakładka admina |
| `modules/gift_cards/routes_client.py` | strona akcji dla klienta |
| `templates/admin/gift_cards/{list,form,detail}.html` | ekrany admina |
| `templates/client/gift_cards/campaign.html` | strona klienta |
| `templates/emails/gift_cards_{invite,result}.{html,txt}` | treść maili |
| `static/css/pages/gift-cards.css`, `static/js/pages/gift-cards-client.js`, `static/js/pages/admin/gift-cards.js` | style i skrypty |
| `migrations/versions/<rev>_rozdzial_gratisow.py` | tabele modułu |
| Modyfikacje: `app.py`, `templates/components/sidebar_admin.html`, `modules/orders/models.py` (property), `templates/client/orders/detail.html`, `templates/admin/orders/detail.html`, `templates/admin/orders/list.html`, `modules/orders/wms.py`, `static/js/pages/admin/wms.js`, `static/js/pages/admin/wms-mobile.js` |
| Testy: `tests/test_gift_cards_allocation.py`, `tests/test_gift_cards_service.py`, `tests/test_gift_cards_admin.py`, `tests/test_gift_cards_client.py`, `tests/test_gift_cards_display.py` |

---

### Task 1: Modele, migracja, rejestracja blueprintu

**Files:**
- Create: `modules/gift_cards/__init__.py`, `modules/gift_cards/models.py`, `modules/gift_cards/routes_admin.py` (pusty, tylko import blueprintu), `modules/gift_cards/routes_client.py` (j.w.), `migrations/versions/<rev>_rozdzial_gratisow.py`
- Modify: `app.py` (rejestracja obok `contests_bp`, ok. linii 383)
- Test: `tests/test_gift_cards_service.py`

**Interfaces:**
- Produces (wszystkie w `modules.gift_cards.models`):
  - `GiftCampaign` (`gift_campaigns`): `id`, `name: str(200)`, `bonus_product_id` FK `products.id` ondelete SET NULL nullable, `status: str(20)` default `'szkic'` — wartości `szkic | otwarta | zamknieta | rozdzielona | zatwierdzona`, `race_at: UTCDateTime` nullable, `created_at`, `updated_at`, `created_by_admin_id` FK `users.id` ondelete SET NULL. Relacje: `pages` (→ `GiftCampaignPage`, cascade delete-orphan), `card_types` (order_by `sort_order, id`, cascade), `participants`, `race_entries` (order_by `id`), `assignments`; `bonus_product`. Property `offer_page_ids -> list[int]`.
  - Stałe modułowe: `STATUS_DRAFT='szkic'`, `STATUS_OPEN='otwarta'`, `STATUS_CLOSED='zamknieta'`, `STATUS_DISTRIBUTED='rozdzielona'`, `STATUS_APPROVED='zatwierdzona'`.
  - `GiftCampaignPage` (`gift_campaign_pages`): `campaign_id` FK CASCADE, `offer_page_id` FK `offer_pages.id` CASCADE; unikalne `(campaign_id, offer_page_id)`.
  - `GiftCardType` (`gift_card_types`): `campaign_id` FK CASCADE, `name: str(200)` NOT NULL, `image_path: str(512)` nullable, `quantity: int` nullable (wpisywane po dotarciu kart), `sort_order: int` default 0.
  - `GiftParticipant` (`gift_participants`): `campaign_id` FK CASCADE, `user_id` FK `users.id` CASCADE, `ranking_json: Text` nullable (lista id rodzajów, najlepszy pierwszy), `ranking_updated_at`; unikalne `(campaign_id, user_id)`. Property `ranking -> list[int]` (pusta lista gdy brak).
  - `GiftRaceEntry` (`gift_race_entries`): `id` autoincrement (= kolejność w kolejce), `campaign_id` FK CASCADE, `user_id` FK CASCADE, `created_at`; unikalne `(campaign_id, user_id)`.
  - `GiftAssignment` (`gift_assignments`): `campaign_id` FK CASCADE, `user_id` FK CASCADE, `order_item_id` FK `order_items.id` CASCADE, `card_type_id` FK `gift_card_types.id` CASCADE, `round_no: int`, `rank_position: int` nullable, `is_duplicate: bool` default False.

- [ ] **Step 1: Napisz test, że modele się tworzą i unikalność działa**

```python
def test_race_entry_unique_per_user(db, make_user, make_product):
    from sqlalchemy.exc import IntegrityError
    from modules.gift_cards.models import GiftCampaign, GiftRaceEntry
    c = GiftCampaign(name='ATEEZ', bonus_product_id=make_product().id)
    db.session.add(c); db.session.commit()
    u = make_user()
    db.session.add(GiftRaceEntry(campaign_id=c.id, user_id=u.id)); db.session.commit()
    db.session.add(GiftRaceEntry(campaign_id=c.id, user_id=u.id))
    with pytest.raises(IntegrityError):
        db.session.commit()

def test_participant_ranking_property(db, make_user, make_product):
    from modules.gift_cards.models import GiftCampaign, GiftParticipant
    c = GiftCampaign(name='X', bonus_product_id=make_product().id); db.session.add(c); db.session.commit()
    p = GiftParticipant(campaign_id=c.id, user_id=make_user().id)
    assert p.ranking == []
    p.ranking_json = '[3, 1, 2]'
    assert p.ranking == [3, 1, 2]
    assert c.status == 'szkic'
```

- [ ] **Step 2: Uruchom — oczekiwany FAIL** (`ModuleNotFoundError: modules.gift_cards`)

Run: `python -m pytest tests/test_gift_cards_service.py -v`

- [ ] **Step 3: Utwórz moduł i modele wg Interfaces; zarejestruj `gift_cards_bp` w `app.py`** (wzór: `modules/contests/__init__.py` — import `routes_admin`, `routes_client`, `models` na końcu).

- [ ] **Step 4: Uruchom test — oczekiwany PASS**

- [ ] **Step 5: Wygeneruj migrację** `flask db migrate -m "rozdzial gratisow"`, przejrzyj plik: tylko 6 nowych tabel, FK z `ondelete` jak wyżej, `down_revision` = jedyny head. Sprawdź lokalnie `flask db upgrade` i `flask db downgrade -1` + ponownie `upgrade` (lokalna MariaDB z XAMPP).

- [ ] **Step 6: Commit** `feat(gratisy): modele i migracja rozdzialu gratisowych kart`

---

### Task 2: Uprawnienia i kolejka

**Files:**
- Create: `modules/gift_cards/service.py`
- Test: `tests/test_gift_cards_service.py`

**Interfaces:**
- Consumes: modele z Task 1.
- Produces:
  - `@dataclass Entitlement: user_id: int; items: list[tuple[int, int]]  # (order_item_id, quantity) posortowane po Order.created_at, OrderItem.id; first_order_at: datetime` + property `total -> int`.
  - `compute_entitlements(campaign: GiftCampaign) -> dict[int, Entitlement]` — pozycje `OrderItem` z `is_bonus=True`, `product_id == campaign.bonus_product_id`, zamówienie z `offer_page_id in campaign.offer_page_ids`, `Order.status` NOT IN `EXCLUDED_ORDER_STATUSES = ('anulowane', 'zwrocone')`. Gdy `bonus_product_id` jest None albo brak stron → `{}`.
  - `queue_order(campaign: GiftCampaign, entitlements: dict[int, Entitlement]) -> list[int]` — najpierw `user_id` z `GiftRaceEntry` (tylko uprawnieni) w kolejności `id`; potem pozostali uprawnieni wg `first_order_at`, remis po `user_id`.
  - `queue_position(campaign, user_id) -> int | None` — 1-based miejsce w wyścigu (liczba wpisów z `id <=` wpisu użytkownika), None gdy nie kliknął.

- [ ] **Step 1: Testy**

```python
def test_entitlements_sum_bonus_items_across_orders(...):
    # klient A: 2 zamówienia na stronie akcji z gratisem 1 i 2 szt. -> total 3
    # klient B: gratis 1 szt., ale zamówienie 'anulowane' -> brak w wyniku
    # klient C: gratis z INNEJ strony oferty -> brak
    # pozycja is_bonus z innym produktem -> nie liczy się
    ents = compute_entitlements(campaign)
    assert set(ents) == {a.id}
    assert ents[a.id].total == 3
    assert [q for _, q in ents[a.id].items] == [1, 2]   # po dacie zamówienia

def test_entitlements_empty_without_bonus_product(...):
    campaign.bonus_product_id = None
    assert compute_entitlements(campaign) == {}

def test_queue_racers_first_then_by_first_order(...):
    # uprawnieni: A (zamówienie 1.11), B (2.11), C (3.11); wyścig: C kliknęła przed A; B nie kliknęła
    assert queue_order(campaign, ents) == [c.id, a.id, b.id]

def test_queue_ignores_race_entry_of_non_entitled_user(...):
    # D kliknęła wyścig, ale nie ma gratisu -> nie ma jej w kolejce
```

Zamówienia buduj przez fixture `make_order(user, offer_page_id=page.id, ...)` + `OrderItem(order_id=..., product_id=bonus.id, quantity=n, price=0, total=0, is_bonus=True)`; strony oferty jak w fixture `strona_sprzedazy` (druga strona: nowy `OfferPage`).

- [ ] **Step 2: Uruchom — FAIL**
- [ ] **Step 3: Zaimplementuj trzy funkcje i dataclass w `service.py`** (jedno zapytanie z join `Order`, bez N+1).
- [ ] **Step 4: Uruchom — PASS**
- [ ] **Step 5: Commit** `feat(gratisy): uprawnienia do kart i kolejka`

---

### Task 3: Algorytm rozdziału

**Files:**
- Create: `modules/gift_cards/allocation.py`
- Test: `tests/test_gift_cards_allocation.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Person: user_id: int; need: int; ranking: tuple[int, ...]  # id rodzajów, najlepszy pierwszy; () = brak rankingu`
  - `@dataclass Pick: type_id: int; round_no: int; is_duplicate: bool; rank_position: int | None`
  - `@dataclass AllocationResult: picks: dict[int, list[Pick]]; shortage: dict[int, int]  # tylko wpisy > 0`
  - `allocate(people: list[Person], stock: dict[int, int]) -> AllocationResult` — `people` w kolejności kolejki. Czysta funkcja, deterministyczna.

Algorytm (to jest decyzja projektu — implementuj dokładnie tak):

```
1. Ile kto dostanie (niedobór = mniej dla końca kolejki w ostatnich rundach):
   left = sum(stock); served = {p: 0}
   for r in 1, 2, ...:  dopóki left > 0 i ktoś ma need >= r
       for p in people (kolejność kolejki): if p.need >= r and left > 0: served[p] += 1; left -= 1
   shortage[p] = p.need - served[p]

2. F* = max_distinct(remaining=served, held={}, stock)
   max_distinct = maksymalny przepływ: źródło -> osoba (pojemność remaining[p]),
   osoba -> rodzaj (pojemność 1, tylko gdy rodzaju jeszcze nie ma), rodzaj -> ujście (pojemność stock[t]).
   (Liczba rodzajów jest mała — wystarczy Edmonds–Karp na słownikach.)

3. Rundy: for r in 1..max(served): for p in people z served[p] >= r:
       kandydaci = (ranking: rodzaje bez powtórki w kolejności rankingu, potem z powtórką w kolejności rankingu)
                   (brak rankingu: rodzaje bez powtórki sortowane po (-stock[t], t), potem z powtórką tak samo)
       wybierz PIERWSZEGO kandydata t ze stock[t] > 0, dla którego:
           distinct_dotąd + (1 jeśli t nowy dla p) + max_distinct(stan po wzięciu t) == F*
       zapisz Pick(t, r, is_duplicate = p już ma t, rank_position = ranking.index(t)+1 lub None)
   (Zawsze istnieje taki kandydat: suma pozostałego stanu >= suma pozostałych potrzeb, a optymalne dokończenie istnieje.)
```

- [ ] **Step 1: Testy (wartości z projektu)**

```python
SAN, YUNHO, MINGI, WOOYOUNG = 1, 2, 3, 4

def test_rounds_follow_queue_and_ranking():
    # A (need 2), B (need 1); stan po 2 szt. San/Yunho
    r = allocate([Person(1, 2, (SAN, YUNHO)), Person(2, 1, (SAN, YUNHO))], {SAN: 2, YUNHO: 1})
    assert [p.type_id for p in r.picks[1]] == [SAN, YUNHO]   # runda 1: San, runda 2: Yunho
    assert [p.type_id for p in r.picks[2]] == [SAN]
    assert r.picks[1][1].round_no == 2

def test_favorite_kept_when_no_conflict():
    # bez konfliktu reguła „bez powtórek” nie odbiera nikomu ulubionego
    people = [Person(9, 2, (YUNHO, SAN)), Person(5, 1, (SAN, YUNHO))]
    r = allocate(people, {YUNHO: 1, SAN: 2})
    assert [p.type_id for p in r.picks[9]] == [YUNHO, SAN]
    assert [p.type_id for p in r.picks[5]] == [SAN]

def test_spec_example_queue_earlier_person_gets_second_choice():
    # A (nr 5) need 1 ranking San>Yunho; B (nr 9) need 2 ranking Yunho>San; stan: San 1, Yunho 2
    # Runda 1: A chciałaby San; gdyby wzięła San, B dostałaby Yunho+Yunho -> A dostaje Yunho
    r = allocate([Person(5, 1, (SAN, YUNHO)), Person(9, 2, (YUNHO, SAN))], {SAN: 1, YUNHO: 2})
    assert [p.type_id for p in r.picks[5]] == [YUNHO]
    assert sorted(p.type_id for p in r.picks[9]) == [SAN, YUNHO]
    assert r.picks[5][0].rank_position == 2
    assert not any(p.is_duplicate for ps in r.picks.values() for p in ps)

def test_duplicates_only_when_unavoidable_and_minimal():
    # 6 kart, 4 rodzaje unitowe po 2 szt. -> dokładnie 2 powtórki, w ostatnich rundach
    r = allocate([Person(1, 6, (1, 2, 3, 4))], {1: 2, 2: 2, 3: 2, 4: 2})
    picks = r.picks[1]
    assert sum(p.is_duplicate for p in picks) == 2
    assert [p.is_duplicate for p in picks] == [False] * 4 + [True] * 2

def test_shortage_hits_last_rounds_end_of_queue():
    # potrzeby 1, 3, 3 (kolejka A, B, C); stan 5 -> runda1: A,B,C; runda2: B,C; brak dla C w rundzie 3 i B w rundzie 3
    r = allocate([Person(1, 1, ()), Person(2, 3, ()), Person(3, 3, ())], {1: 2, 2: 2, 3: 1})
    assert len(r.picks[1]) == 1 and len(r.picks[2]) == 2 and len(r.picks[3]) == 2
    assert r.shortage == {2: 1, 3: 1}

def test_no_ranking_takes_most_plentiful_type():
    r = allocate([Person(1, 1, ())], {1: 1, 2: 5})
    assert r.picks[1][0].type_id == 2 and r.picks[1][0].rank_position is None

def test_deterministic():
    people = [Person(i, 2, (1, 2, 3)) for i in range(1, 8)]
    s = {1: 5, 2: 5, 3: 4}
    assert allocate(people, s) == allocate(people, s)

def test_empty_inputs():
    assert allocate([], {1: 3}).picks == {}
    r = allocate([Person(1, 2, (1,))], {})
    assert r.picks.get(1, []) == [] and r.shortage == {1: 2}
```

Osoba bez rankingu bierze rodzaj o największym pozostałym stanie — to interpretacja reguły „dostaje to, co zostanie po innych” (zostawia popularne rodzaje osobom z rankingiem).

- [ ] **Step 2: Uruchom — FAIL**
- [ ] **Step 3: Zaimplementuj `allocate` wg algorytmu**
- [ ] **Step 4: Uruchom — PASS**
- [ ] **Step 5: Commit** `feat(gratisy): algorytm rozdzialu rundami bez powtorek`

---

### Task 4: Rozdział, zamiany, zatwierdzanie, cofanie, etykieta pozycji

**Files:**
- Modify: `modules/gift_cards/service.py`, `modules/orders/models.py` (property w `OrderItem`, obok `product_name` ~linia 1322)
- Test: `tests/test_gift_cards_service.py`

**Interfaces:**
- Consumes: `compute_entitlements`, `queue_order` (Task 2), `allocate`, `Person` (Task 3).
- Produces:
  - `class GiftCardsError(Exception)` — komunikat po polsku do pokazania w `flash`.
  - `run_distribution(campaign) -> AllocationResult` — wymaga statusu `zamknieta` lub `rozdzielona`, każdy rodzaj ma `quantity` (int ≥ 0), co najmniej jeden rodzaj; inaczej `GiftCardsError` („Uzupełnij ilości wszystkich rodzajów kart.”). Kasuje stare `GiftAssignment` akcji, buduje `Person` z kolejki + `GiftParticipant.ranking` (ranking filtrowany do istniejących rodzajów; niepełny → traktuj jak brak rankingu), woła `allocate`, zapisuje `GiftAssignment` przypisując karty osoby kolejno do jej pozycji `Entitlement.items` (wypełnij ilość pozycji 1, potem 2…). Ustawia status `rozdzielona`. Brak uprawnionych → pusty wynik, status `rozdzielona`.
  - `swap_assignment(assignment_id: int, new_type_id: int) -> None` — tylko w statusie `rozdzielona`; rodzaj musi należeć do akcji; liczba przydziałów rodzaju po zmianie ≤ `quantity`, inaczej `GiftCardsError` („Brak wolnych sztuk: {nazwa}.”). Przelicza `is_duplicate` i `rank_position` dla kart tej osoby.
  - `approve(campaign) -> None` — `rozdzielona` → `zatwierdzona`.
  - `can_revert(campaign) -> bool` — False, gdy któreś zamówienie z przydziałów ma status w `('spakowane', 'wyslane', 'dostarczone')`.
  - `revert_approval(campaign) -> None` — `zatwierdzona` → `rozdzielona`, gdy `can_revert`; inaczej `GiftCardsError`.
  - `item_gift_label(item: OrderItem) -> str | None` — dla `item.is_bonus`: zatwierdzone przydziały tej pozycji → nazwy rodzajów po `round_no`, złączone `", "` (np. `"San, Yunho, Mingi"`); jeśli pozycja należy do akcji w statusie `otwarta|zamknieta|rozdzielona` → `"przydział w toku"`; inaczej None.
  - `OrderItem.gift_cards_label` (property) → `item_gift_label(self)` (import wewnątrz property, żeby uniknąć cyklu).

- [ ] **Step 1: Testy**

```python
def test_run_distribution_saves_assignments_on_order_items(...):
    # A: dwa zamówienia z gratisem 1 + 1; ranking A: San>Yunho; stan San 1, Yunho 1
    run_distribution(c)
    rows = GiftAssignment.query.filter_by(user_id=a.id).order_by(GiftAssignment.round_no).all()
    assert [r.order_item_id for r in rows] == [item1.id, item2.id]
    assert c.status == 'rozdzielona'

def test_run_distribution_requires_quantities(...):   # Review Focus 4
    typ.quantity = None
    with pytest.raises(GiftCardsError, match='ilości'):
        run_distribution(c)

def test_run_distribution_no_entitled_users(...):     # Review Focus 4
    result = run_distribution(c_bez_zamowien)
    assert result.picks == {} and c_bez_zamowien.status == 'rozdzielona'

def test_swap_over_stock_rejected(...):               # Review Focus 5
    # San quantity 1 już przydzielony A; zamiana karty B na San -> błąd
    with pytest.raises(GiftCardsError, match='Brak wolnych sztuk'):
        swap_assignment(b_row.id, san.id)

def test_swap_recomputes_duplicate_flag(...): ...

def test_label_pending_then_names_after_approve(...):
    assert item.gift_cards_label == 'przydział w toku'
    approve(c)
    assert item.gift_cards_label == 'San, Yunho'

def test_revert_blocked_when_order_packed(...):
    order.status = 'spakowane'; db.session.commit()
    assert can_revert(c) is False
    with pytest.raises(GiftCardsError):
        revert_approval(c)
```

- [ ] **Step 2: FAIL** — **Step 3: implementacja** — **Step 4: PASS**
- [ ] **Step 5: Commit** `feat(gratisy): rozdzial, zamiany i zatwierdzanie przydzialu`

---

### Task 5: Maile

**Files:**
- Create: `modules/gift_cards/emails.py`, `templates/emails/gift_cards_invite.html`, `.txt`, `templates/emails/gift_cards_result.html`, `.txt`
- Test: `tests/test_gift_cards_service.py`

**Interfaces:**
- Consumes: `compute_entitlements` (Task 2), `GiftAssignment`.
- Produces:
  - `send_invites(campaign) -> int` — do każdego uprawnionego: temat `Gratisowe karty: {campaign.name} - ThunderOrders`; treść: ile kart przysługuje (`Entitlement.total`), data i godzina wyścigu w czasie polskim (`to_pl(campaign.race_at)`, format `%d.%m.%Y %H:%M`), link `url_for('gift_cards.client_campaign', cid=..., _external=True)`, prośba o ułożenie rankingu. Zwraca liczbę przygotowanych maili. `prepare_email` + `send_email_batch`.
  - `send_results(campaign) -> int` — temat `Twoje gratisowe karty: {campaign.name} - ThunderOrders`; lista nazw przydzielonych kart; jeśli niedobór (mniej przydziałów niż `Entitlement.total`), zdanie „Brakuje {n} kart — skontaktujemy się w tej sprawie.”
  - Szablony wzorowane na `templates/emails/contest_win.html` / `.txt`.

- [ ] **Step 1: Testy** z fixture `maile_synchronicznie` i `mail.record_messages()`; render w `app.test_request_context()` (nie `app_context()`):

```python
def test_send_invites_one_mail_per_entitled_user(app, maile_synchronicznie, ...):
    from extensions import mail
    with app.test_request_context(), mail.record_messages() as out:
        assert send_invites(c) == 2
    assert len(out) == 2
    assert 'przysługują Ci 3' in out[0].body or 'przysługują Ci 3' in out[1].body

def test_send_results_lists_cards_and_shortage(...):
    # A: przydział San, Yunho; należało się 3
    assert 'San, Yunho' in body and 'Brakuje 1' in body
```

- [ ] **Step 2: FAIL** — **Step 3: implementacja** — **Step 4: PASS**
- [ ] **Step 5: Commit** `feat(gratisy): maile z zaproszeniem i wynikiem rozdzialu`

---

### Task 6: Zakładka admina

**Files:**
- Modify: `modules/gift_cards/routes_admin.py`, `templates/components/sidebar_admin.html` (nowy `<li>` zaraz po „Konkursy”, ikona `img/icons/achievements.svg` albo istniejąca ikona prezentu, tekst „Rozdział gratisów”, aktywny gdy `request.endpoint.startswith('gift_cards.admin_')`)
- Create: `templates/admin/gift_cards/list.html`, `form.html`, `detail.html`, `static/js/pages/admin/gift-cards.js`, style w `static/css/pages/gift-cards.css`
- Test: `tests/test_gift_cards_admin.py`

**Interfaces:**
- Consumes: wszystko z Task 2, 4, 5.
- Produces (endpointy, wszystkie `admin`/`mod`):

| Metoda | URL | Endpoint | Działanie |
|---|---|---|---|
| GET | `/admin/rozdzial-gratisow` | `admin_list` | lista akcji: nazwa, status, liczba uprawnionych, data wyścigu |
| GET/POST | `/admin/rozdzial-gratisow/nowa`, `/<cid>/edytuj` | `admin_form` | nazwa, strony ofert (multi-select z `OfferPage`), produkt-gratis (select z produktów występujących jako `OfferSetBonus.bonus_product_id` na wybranych stronach; fallback: wyszukiwarka produktów), rodzaje kart (dynamiczna lista wierszy: nazwa + opcjonalne zdjęcie; zapis pliku tak jak `Contest.image_path` w `modules/contests/routes.py`), data i godzina wyścigu (czas polski → `pl_input_to_utc`). Edycja rodzajów i stron tylko w statusie `szkic`. |
| GET | `/admin/rozdzial-gratisow/<cid>` | `admin_detail` | uprawnieni (imię i nazwisko, liczba kart, miejsce w wyścigu, czy ma ranking), przyciski akcji wg statusu, formularz ilości rodzajów, tabela przydziału |
| POST | `/<cid>/publikuj` | `admin_publish` | `szkic` → `otwarta` + `send_invites`; flash „Wysłano N zaproszeń.” |
| POST | `/<cid>/zamknij` | `admin_close` | `otwarta` → `zamknieta` |
| POST | `/<cid>/ilosci` | `admin_quantities` | zapis `quantity` każdego rodzaju (int ≥ 0) |
| POST | `/<cid>/rozdziel` | `admin_distribute` | `run_distribution`; `GiftCardsError` → flash error |
| POST | `/<cid>/zamien` | `admin_swap` | JSON `{assignment_id, type_id}` → `swap_assignment`; odpowiedź `{success, error?}` |
| POST | `/<cid>/zatwierdz` | `admin_approve` | `approve` + `send_results` |
| POST | `/<cid>/cofnij` | `admin_revert` | `revert_approval` |

Tabela przydziału (detail): wiersz na osobę w kolejności kolejki — miejsce, imię i nazwisko, karty (każda jako `<select>` rodzajów z bieżącym zaznaczonym; zmiana → fetch `admin_swap`), przy karcie „wybór nr X” albo „bez rankingu”, czerwony znacznik „powtórka”, żółty „brakuje N” przy niedoborze. Nad tabelą podsumowanie: łącznie kart należnych / dostępnych / powtórek.

- [ ] **Step 1: Testy** (`client`, `login`, `make_user(role='admin')`):

```python
def test_list_requires_admin(client, login, make_user):
    login(make_user(role='client'))
    assert client.get('/admin/rozdzial-gratisow').status_code in (302, 403)

def test_create_campaign_with_card_types(...):
    resp = client.post('/admin/rozdzial-gratisow/nowa', data={
        'name': 'ATEEZ unit', 'offer_page_ids': [page.id], 'bonus_product_id': bonus.id,
        'race_at': '2026-11-20T20:00', 'type_name': ['Hongjoong + Seonghwa', 'Yunho + Yeosang']})
    c = GiftCampaign.query.one()
    assert [t.name for t in c.card_types] == ['Hongjoong + Seonghwa', 'Yunho + Yeosang']
    assert to_pl(c.race_at).hour == 20

def test_publish_sends_invites_and_opens(...): ...
def test_distribute_without_quantities_shows_error(...):   # flash, status bez zmian, 302
def test_full_flow_close_quantities_distribute_approve(...): # status zatwierdzona, item.gift_cards_label ustawiony
def test_swap_endpoint_returns_error_json_over_stock(...):
```

- [ ] **Step 2: FAIL** — **Step 3: implementacja tras i szablonów** (wzór układu: `templates/admin/contests/*.html`; CSS jasny + ciemny) — **Step 4: PASS**
- [ ] **Step 5: Sprawdzenie ręczne:** `node --check static/js/pages/admin/gift-cards.js`; render szablonów pokryty testami (ekranów za logowaniem Claude nie przeklika bez hasła — przeklikanie zostaje po stronie Karoliny).
- [ ] **Step 6: Commit** `feat(gratisy): zakladka admina rozdzialu gratisow`

---

### Task 7: Strona klienta (ranking + wyścig + wynik)

**Files:**
- Modify: `modules/gift_cards/routes_client.py`, `templates/client/orders/detail.html` (przy pozycji z `item.is_bonus`, gdy istnieje akcja `otwarta` obejmująca tę pozycję: link „Wybierz swoje gratisowe karty →”)
- Create: `templates/client/gift_cards/campaign.html`, `static/js/pages/gift-cards-client.js`, style w `static/css/pages/gift-cards.css`
- Test: `tests/test_gift_cards_client.py`

**Interfaces:**
- Consumes: `compute_entitlements`, `queue_position` (Task 2), `item_gift_label` (Task 4).
- Produces:
  - `service.open_campaign_for_item(item) -> GiftCampaign | None` (do linku na stronie zamówienia).
  - Endpointy (`@login_required`):

| Metoda | URL | Endpoint | Działanie |
|---|---|---|---|
| GET | `/gratisy/<cid>` | `client_campaign` | Nieuprawniony (lub akcja `szkic`) → strona z tekstem „Ta akcja Cię nie dotyczy” (200). Uprawniony: „Przysługują Ci N kart”, siatka rankingu, odliczanie do `race_at` (`iso_utc`), przycisk „Zgłaszam się” (aktywny od `race_at` gdy status `otwarta`), „Jesteś nr X w kolejce”; po `zatwierdzona` — lista przydzielonych kart. |
| POST | `/gratisy/<cid>/ranking` | `client_save_ranking` | form `rank_<type_id>=<miejsce>`; musi być permutacją 1..N po wszystkich rodzajach tej akcji; tylko status `otwarta`; błąd → 400 + komunikat; sukces → upsert `GiftParticipant`, redirect z flash „Ranking zapisany.” |
| POST | `/gratisy/<cid>/zglaszam-sie` | `client_race` | tylko `otwarta` i `utcnow() >= race_at`, tylko uprawniony (inaczej 403); insert `GiftRaceEntry`, przy `IntegrityError` rollback; zawsze JSON `{success: true, position: N}` |

Siatka rankingu: `<table>` wiersze = rodzaje (nazwa, miniatura gdy `image_path`), kolumny 1..N, `<input type="radio" name="rank_<type_id>" value="<miejsce>">`. JS pilnuje „jedna odpowiedź w kolumnie” (zaznaczenie miejsca w jednym wierszu odznacza to samo miejsce w innych) i blokuje „Zapisz”, dopóki każdy wiersz nie ma miejsca. Serwer waliduje niezależnie. Na telefonie siatka przewija się poziomo w swoim kontenerze, komórki min. 44px.

- [ ] **Step 1: Testy**

```python
def test_non_entitled_sees_not_for_you(...):                 # Review Focus 3
    assert 'Ta akcja Cię nie dotyczy' in client.get(f'/gratisy/{c.id}').get_data(as_text=True)

def test_non_entitled_race_forbidden(...):                    # Review Focus 3
    assert client.post(f'/gratisy/{c.id}/zglaszam-sie').status_code == 403

def test_race_before_time_rejected(...):  # race_at w przyszłości -> 400, brak wpisu

def test_double_race_click_single_entry(...):                 # Review Focus 1
    r1 = client.post(f'/gratisy/{c.id}/zglaszam-sie').get_json()
    r2 = client.post(f'/gratisy/{c.id}/zglaszam-sie').get_json()
    assert r1['position'] == r2['position'] == 1
    assert GiftRaceEntry.query.count() == 1

def test_ranking_saved_as_type_ids_in_order(...):
    client.post(f'/gratisy/{c.id}/ranking', data={f'rank_{t1.id}': 2, f'rank_{t2.id}': 1})
    assert GiftParticipant.query.one().ranking == [t2.id, t1.id]

@pytest.mark.parametrize('dane', ['duplikat_miejsca', 'obcy_rodzaj', 'brak_rodzaju'])
def test_ranking_tampering_rejected(dane, ...):               # Review Focus 2
    assert resp.status_code == 400 and GiftParticipant.query.count() == 0

def test_ranking_locked_after_close(...):  # status zamknieta -> 400

def test_shows_assigned_cards_after_approve(...):
    assert 'San' in html and 'Yunho' in html
```

- [ ] **Step 2: FAIL** — **Step 3: implementacja** — **Step 4: PASS** + `node --check static/js/pages/gift-cards-client.js`
- [ ] **Step 5: Commit** `feat(gratisy): strona klienta z rankingiem i wyscigiem`

---

### Task 8: Przydział widoczny w zamówieniach i WMS

**Files:**
- Modify: `templates/client/orders/detail.html` (obok znacznika GRATIS, ~linia 170), `templates/admin/orders/detail.html` (pozycje z `item.is_bonus`, ~linie 81–110 i 268–297), `templates/admin/orders/list.html` (~linie 612, 675), `modules/orders/wms.py` (`_build_session_data`, ~linia 140: nowe pole `'gift_cards_label': item.gift_cards_label if item.is_bonus else None`), `static/js/pages/admin/wms.js`, `static/js/pages/admin/wms-mobile.js` (pod nazwą produktu wiersz z etykietą; dla `"przydział w toku"` styl ostrzegawczy)
- Test: `tests/test_gift_cards_display.py`

**Interfaces:**
- Consumes: `OrderItem.gift_cards_label` (Task 4).

Wyświetlanie: pod nazwą pozycji-gratisu mała linia „Karty: San, Yunho, Mingi” albo znacznik „przydział w toku” (żółty). Bez zmian w `product_name` (używane w wielu miejscach, m.in. do grupowania).

- [ ] **Step 1: Testy**

```python
def test_client_order_detail_shows_assigned_cards(...):
    assert 'Karty: San, Yunho' in html

def test_admin_order_detail_shows_pending_badge(...):
    assert 'przydział w toku' in html

def test_wms_session_data_includes_gift_label(...):
    data = _build_session_data(session)
    assert data['orders'][0]['items'][0]['gift_cards_label'] == 'San, Yunho'
```

(Zbuduj sesję WMS wg istniejących testów WMS — np. `grep -l _build_session_data tests/`.)

- [ ] **Step 2: FAIL** — **Step 3: implementacja** — **Step 4: PASS** + `node --check` dla obu plików JS
- [ ] **Step 5: Commit** `feat(gratisy): przydzial kart widoczny w zamowieniach i WMS`

---

### Task 9: Weryfikacja całości (kontroler)

- [ ] Pełna suita w tle: `python -m pytest -q` — wszystko zielone (porównaj z wynikiem na `main` przed zmianami, jeśli coś padało wcześniej).
- [ ] `flask db upgrade` na lokalnej bazie (backup przed!) i przejście scenariusza na dev serwerze: akcja → publikacja → ranking i wyścig jako klient testowy → zamknięcie → ilości → rozdział → zamiana → zatwierdzenie → etykiety w zamówieniu i WMS.
- [ ] Raport dla Karoliny: co działa, czego nie dało się sprawdzić (ekrany za logowaniem przeklikuje ona), gotowość do scalenia z `main` lokalnie. **Bez pushu** — push tylko na jej wyraźną zgodę, poza godzinami szczytu zamówień.
