# Moduł Konkursów / Losowania — projekt (spec)

**Data:** 2026-06-09
**Status:** zatwierdzony do planu implementacji
**Moduł:** `modules/contests/`

## 1. Cel i kontekst

Moduł konkursów w stylu „radiowym" (RMF FM): klienci raz na okres cooldownu „kręcą"
i zdobywają losową liczbę losów, które **kumulują się** przez cały czas trwania konkursu.
Na koniec admin **ręcznie na żywo** losuje zwycięzcę/zwycięzców, ważonych liczbą losów.
Moduł jest wielokrotnego użytku — kolejne konkursy tworzy się po zakończeniu poprzedniego.

Mechanika szans: suma losów wszystkich uczestników = 100%; udział pojedynczego klienta
to jego losy / pula. Klient w trakcie widzi **tylko swoją liczbę losów** — pula i procenty
są ukryte aż do losowania (element zaskoczenia). Pulę i % widzi wyłącznie admin na ekranie losowania.

## 2. Ustalenia kluczowe

| Decyzja | Wybór |
|---|---|
| Kumulacja losów | Kumulują się przez cały konkurs; zwycięzca losowany na końcu |
| Liczba aktywnych konkursów | Jeden naraz (wymuszane statusem) |
| Liczba zwycięzców | Konfigurowalna (1..N), bez powtórzeń (wylosowany wypada z puli) |
| Nagroda | Produkt z magazynu (FK do `Product`), dowolna kategoria |
| Realizacja nagrody | System zapisuje zwycięzcę + wysyła powiadomienie; wydanie ręczne |
| Moment losowania | Admin ręcznie „na żywo", z animacją slot |
| Zakres losów per spin | Konfigurowalny min–max per konkurs, rozkład równomierny |
| Cooldown | Konfigurowalny per konkurs (domyślnie 1440 min = 24h); kroczący od ostatniego spinu |
| Kryteria udziału | Konfigurowalne, **łączne (AND)**, każde opcjonalne |
| Widoczność dla klienta | Tylko własna liczba losów; brak puli/%/zakresu losów |
| Główny punkt wejścia klienta | Wyróżniający się widget na dashboardzie |
| Styl animacji spinu | Modal z overlayem + pionowa karuzela (Start → Stop → hamowanie do wyniku) |

### Kryteria udziału (łączne, każde opcjonalne — puste = pomijane)
1. **Min. liczba zamówień** (próg N).
2. **Min. łączna wartość zamówień** (kwota w zł).
3. **Aktywny w ostatnich X dniach** (złożył zamówienie w oknie X dni).
4. Brak jakiegokolwiek kryterium = każdy zalogowany klient (rola `client`).

We wszystkich zapytaniach o zamówienia liczymy tylko zamówienia „realne" — wykluczamy status
`anulowane` (`Order.status` to FK do `order_statuses.slug`).

## 3. Architektura danych (Opcja A — dziennik spinów)

Trzy tabele. Konwencje projektu: `get_local_now()` dla dat, FK do `users.id` / `products.id`,
enumy/słowniki po polsku. Każda zmiana struktury przez **migrację Flask-Migrate** (ręcznie
zweryfikowaną — enum/FK Alembic auto-detekt obsługuje słabo).

### 3.1 `contests`
| pole | typ | opis |
|---|---|---|
| `id` | Integer PK | |
| `name` | String(255) | tytuł konkursu |
| `description` | Text | opis nagrody (edytor) |
| `image_path` | String(512), null | grafika nagrody |
| `prize_product_id` | FK `products.id` | nagroda-produkt |
| `num_winners` | Integer, default 1 | ilu zwycięzców |
| `ticket_min` | Integer | dolna granica losów per spin |
| `ticket_max` | Integer | górna granica losów per spin |
| `cooldown_minutes` | Integer, default 1440 | cooldown między spinami |
| `eligibility_min_orders` | Integer, null | próg zamówień (null = pomijane) |
| `eligibility_min_total_value` | Numeric(10,2), null | min. łączna wartość (null = pomijane) |
| `eligibility_active_within_days` | Integer, null | aktywny w X dni (null = pomijane) |
| `status` | String(20), default `szkic` | wartości: `szkic` → `aktywny` → `rozlosowany` (walidacja na poziomie aplikacji) |
| `starts_at` | DateTime, null | start przyjmowania losów (null = od aktywacji) |
| `ends_at` | DateTime, null | koniec przyjmowania losów |
| `created_at` | DateTime | `get_local_now` |
| `updated_at` | DateTime | `onupdate=get_local_now` |
| `created_by_admin_id` | FK `users.id` | audyt |

Walidacja: `ticket_min >= 1`, `ticket_max >= ticket_min`, `num_winners >= 1`, `cooldown_minutes >= 1`.

### 3.2 `contest_spins` (źródło prawdy)
| pole | typ | opis |
|---|---|---|
| `id` | Integer PK | |
| `contest_id` | FK `contests.id` | |
| `user_id` | FK `users.id` | |
| `tickets_won` | Integer | wynik pojedynczego spinu |
| `created_at` | DateTime | znacznik czasu spinu |

Indeks `(contest_id, user_id)`.
- Losy klienta = `SUM(tickets_won)` po `(contest_id, user_id)`.
- Pula = `SUM(tickets_won)` po `contest_id`.
- Cooldown: `MAX(created_at)` dla `(contest_id, user_id)` + `cooldown_minutes` → `next_spin_at`.

### 3.3 `contest_winners` (wynik losowania, snapshot)
| pole | typ | opis |
|---|---|---|
| `id` | Integer PK | |
| `contest_id` | FK `contests.id` | |
| `user_id` | FK `users.id` | |
| `place` | Integer | miejsce 1..N |
| `tickets_at_draw` | Integer | snapshot liczby losów w chwili losowania |
| `chance_pct` | Numeric(6,3) | snapshot % szansy |
| `prize_product_id` | FK `products.id`, null | snapshot nagrody |
| `drawn_at` | DateTime | |

Unikalność: `(contest_id, user_id)` oraz `(contest_id, place)`.

## 4. Logika domenowa (`modules/contests/utils.py`)

- **`is_eligible(user, contest) -> bool`** — łączy aktywne kryteria (AND). Zapytania do `Order`
  (count / `SUM(total_amount)` / `created_at >= now - X dni`), wykluczając `status == 'anulowane'`.
  Brak kryteriów → `True` dla każdego klienta.
- **`get_user_tickets(contest, user) -> int`** — `SUM(tickets_won)`.
- **`get_pool(contest) -> int`** — suma wszystkich losów.
- **`get_next_spin_at(contest, user) -> datetime|None`** — z `MAX(created_at)` + cooldown.
- **`spins_open(contest) -> bool`** — `status == 'aktywny' AND (ends_at is None OR now < ends_at)`.
- **`draw_winners(contest) -> list[ContestWinner]`** — **autorytatywne losowanie server-side**:
  1. Zbierz uczestników z `tickets > 0` (i wciąż spełniających eligibility).
  2. `random.SystemRandom`, losowanie ważone **bez powtórzeń**: budujemy wagi z sum losów,
     losujemy zwycięzcę, usuwamy z puli, powtarzamy `min(num_winners, liczba_uczestników)` razy.
  3. Zapisz `ContestWinner` ze snapshotem losów i `chance_pct` (liczone względem pełnej puli
     w chwili losowania), `status → rozlosowany`.
  4. Operacja **idempotentna** — jeśli `status == 'rozlosowany'`, zwróć istniejących zwycięzców
     bez przelosowania.

## 5. Endpointy

Blueprint `contests_bp`. Rejestracja w `app.py` → `register_blueprints()` po `achievements_bp`,
przed `shop_bp`. Część kliencka i admin w jednym module, rozdzielone prefiksami i dekoratorami.

### Klient (`@login_required` + rola `client`)
- `GET /konkurs` — strona konkursu (grafika, opis, moje losy, przycisk LOSUJ / licznik).
- `POST /konkurs/spin` — wykonanie spinu (CSRF). Walidacja po kolei (serwer autorytatywny):
  konkurs `aktywny` → spiny otwarte → eligibility → cooldown minął. Losuje liczbę z
  `[ticket_min, ticket_max]`, zapisuje `ContestSpin`, zwraca `{tickets_won, my_total, next_spin_at}`.
- **Widget dashboardu**: dane dołączane do kontekstu istniejącego `GET /dashboard`
  (aktywny konkurs, moje losy, `next_spin_at`, `eligible`). Odświeżanie licznika/spinu po
  stronie JS; ewentualny lekki `GET /konkurs/widget-data` do odświeżenia bez przeładowania.

### Admin (`@login_required` + rola `admin`/`mod`)
- `GET /admin/konkursy` — lista (status, uczestnicy, pula, akcje).
- `GET/POST /admin/konkursy/nowy` + `/<id>/edytuj` — formularz (kontrolki zależne od pola, §6.2).
- `POST /admin/konkursy/<id>/aktywuj` — `szkic → aktywny`; **blokada gdy inny konkurs aktywny**.
- `GET /admin/konkursy/<id>/losowanie` — ekran losowania na żywo.
- `POST /admin/konkursy/<id>/losuj` — wywołuje `draw_winners`, zapis, powiadomienia, zwraca
  komplet danych do animacji (pula, uczestnicy z losami/%, kolejność, zwycięzcy). Blokada gdy
  `status != aktywny` lub spiny wciąż otwarte (`ends_at` w przyszłości).
- `GET /admin/konkursy/<id>/wyniki` — podgląd wyników.

### Bezpieczeństwo / uczciwość
- Losowanie i walidacje wyłącznie server-side; frontend dostaje wynik dopiero po zapisie (brak re-rolla).
- `POST /losuj` idempotentne i chronione przed równoległym podwójnym wywołaniem.

## 6. UI

Zasady projektu: **light + dark mode** dla każdego stylu (`[data-theme="dark"]`), style modali
w `static/css/components/modals.css`, CSS/JS w osobnych plikach (`static/css/pages/…`,
`static/js/pages/…`), brak inline poza dozwolonymi wyjątkami. Paleta: róż `#f093fb`,
czerwony `#f5576c`, glassmorphism.

### 6.1 Klient
- **Widget na dashboardzie** (główny punkt wejścia): badge „KONKURS TRWA", nazwa nagrody,
  podtytuł (nagroda • N zwycięzców), **duża liczba „Twoich losów"** (wyraźna, pogrubiona),
  przycisk **zmienny**: gdy spin dostępny → „🎲 LOSUJ"; gdy cooldown → sam licznik
  „Następny los za HH:MM:SS". Stopka: „Pula i szanse ujawnią się przy losowaniu".
  **Brak zakresu losów i procentów.**
- **Strona `/konkurs`**: grafika + opis nagrody, data końca, duży licznik „masz X losów",
  ten sam przycisk zmienny.
- **Animacja spinu — modal z pionową karuzelą**: po kliknięciu LOSUJ otwiera się modal
  (overlay z rozmyciem tła; style w `static/css/components/modals.css`). Wewnątrz pionowa
  karuzela liczb:
  - **START** → karuzela rusza powoli i **stopniowo się rozpędza**; liczby lecą **w dół**,
    w **losowej kolejności** (nieskończona taśma).
  - Przycisk zmienia się w **STOP** → po kliknięciu **wolne hamowanie** (easeOutQuart) i
    zatrzymanie na liczbie **zwróconej przez serwer**.
  - **Kolejność wywołań:** `POST /konkurs/spin` woła backend (autorytatywny wynik) w momencie
    rozpoczęcia spinu; karuzela jedynie *odgrywa* tę liczbę — „Stop" jest dla emocji i nie zmienia
    wyniku (brak możliwości „wykręcenia" innej liczby).
  - Po zatrzymaniu: wynik („Zdobywasz X losów"), aktualizacja „Twoich losów", zamknięcie modala;
    przycisk na widgecie/stronie przechodzi w licznik cooldownu.
  - Implementacja: pozycja karuzeli sterowana JS (requestAnimationFrame), wartość slotu
    deterministyczna/pseudo-losowa — taśma nieskończona, bez „zawijania" zmieniającego kierunek.

### 6.2 Admin
- **Lista konkursów**: tabela ze statusem (`aktywny`/`szkic`/`rozlosowany`), uczestnikami, pulą, akcjami.
- **Formularz** — kontrolki zależne od typu pola:
  - Nazwa → text; opis → edytor + upload grafiki.
  - **Nagroda** → wyszukiwarka/picker produktu z magazynu (nazwa/SKU, dowolna kategoria,
    ze stanem) — reużycie wzorca z `static/js/pages/admin/offer-extra-order.js`.
  - Liczba zwycięzców → number; **zakres losów → dwa inputy** (min / max).
  - Cooldown → number (minuty); **koniec → `datetime-local`** (kalendarz).
  - **Kryteria → checkbox odsłaniający warunkowy input** (odznaczone = wyszarzone i pomijane).
- **Losowanie na żywo**: statystyki (uczestnicy / pula / zwycięzcy), **animacja slot** lądująca
  na zwycięzcy, karta zwycięzcy (losy + % + miejsce), przycisk „LOSUJ ZWYCIĘZCĘ", oraz
  **rozbicie puli z procentami** (widoczne wyłącznie tu). Dla N zwycięzców slot losuje kolejno
  (#1, #2, …), każdy wypada z puli.

## 7. Powiadomienia i e-mail

Po losowaniu, dla każdego zwycięzcy:

1. **Powiadomienie in-app** — wpis `Notification`
   (`utils/push_manager.py` / bezpośrednio `Notification(...) + db.session.add`):
   `title` („Wygrałeś w konkursie!"), `body` (nazwa nagrody), `url` (→ strona wyników/konkursu),
   `notification_type='contest_win'`. (Push web opcjonalnie przez istniejący `PushManager`.)

2. **E-mail z informacją o wygranej** — przez istniejący mechanizm mailowy
   (`utils/email_manager.py` → `utils/email_sender.py`, Flask-Mail/SMTP, wysyłka asynchroniczna
   w wątku tła z retry). Wzorzec jak inne powiadomienia: nowa metoda w `EmailManager`
   (np. `notify_contest_win(winner)`, z bramką `is_email_enabled(...)`) wołająca `send_email(...)`
   z nowym szablonem **`templates/emails/contest_win.html`** (+ opcjonalny `.txt`). Treść maila:
   nazwa konkursu, wygrana nagroda (produkt), gratulacje i link do strony wyników/konkursu.
   Adresat: e-mail zwycięzcy.

Oba kanały wyzwalane w `draw_winners` (po zapisaniu `ContestWinner`).

## 8. Cykl życia konkursu i zamykanie

`szkic → aktywny → rozlosowany`. Przyjmowanie losów kończy się automatycznie po `ends_at`
(liczone w locie przez `spins_open`, bez twardego crona). Opcjonalnie lekka komenda CLI
`flask close-expired-contests` (wzorzec `@app.cli.command`) tylko jako porządkowe oznaczenie —
**samo losowanie pozostaje ręczne** (admin „na żywo").

## 9. Migracje

Jedna migracja tworząca trzy tabele (`contests`, `contest_spins`, `contest_winners`) z FK i
indeksami. Workflow: zmiana modeli → `flask db migrate` → ręczna weryfikacja pliku (FK/enum) →
`flask db upgrade` lokalnie → commit razem z kodem → deploy (webhook auto-deploy uruchamia upgrade).

## 10. Testy

- **Eligibility**: każde kryterium osobno i kombinacje AND; wykluczanie `anulowane`; brak kryteriów.
- **Spin**: cooldown (przed/po upływie), zakres `[min,max]`, brak udziału gdy nie-eligible,
  blokada gdy konkurs nieaktywny / spiny zamknięte.
- **Losowanie**: ważenie proporcjonalne (test statystyczny przy ustalonym ziarnie/wielu próbach),
  bez powtórzeń, `num_winners > liczba_uczestników` → tylu zwycięzców ilu uczestników,
  idempotencja `POST /losuj`.
- **Jeden aktywny konkurs**: blokada aktywacji drugiego.
- **Snapshoty** `contest_winners` (losy/%/nagroda) zgodne z pulą w chwili losowania.
