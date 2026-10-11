# Pupile — „Świat”: przebudowa UX, szpital, warianty, skórki (spec v3, uzupełnienie)

**Data:** 2026-10-11 · **Autor decyzji:** Konrad (brainstorming w sesji, szkice w karcie wizualnej) · **Task ClickUp:** 869ffdb58
**Relacja do specu v2** (`2026-10-10-pupile-tamagotchi-design.md`): ten dokument **zastępuje** w v2 §2.5 (akcja „Wylecz”),
§4.2 (układ strony), §4.3 (widget) i uzupełnia §4.4 (towarzysz) oraz §4.5 (rig). Reszta v2 obowiązuje bez zmian
(paski, tempo, noc, odejście, jajka, duplikaty, powiadomienia, flaga i rollout).

## 1. Cel

Moduł działa, ale wygląda jak panel ze statystykami. Konrad chce, żeby był **grą**: pupile mają żyć w świecie, ich
potrzeby mają być widoczne w zachowaniu, a liczby i przyciski schowane „głębiej” — dopiero po wejściu do pupila.
Sukces: klient wchodzi na „Moje pupile” i widzi ładny, ilustrowany świat; bez czytania pasków wie, kto jest głodny,
chory czy brudny; opieka jest przyjemna (dłuższe, zróżnicowane animacje), a wyklucie jest wydarzeniem.

## 2. Decyzje Konrada (nie wynikają z kodu)

| temat | decyzja |
|---|---|
| Kierunek graficzny świata | **Mapa-plansza z lotu ptaka** (polanka, ścieżka, 4 miejsca; telefon = plansza pionowa) |
| Miejsca | **Domek** (pupile), **Szpital** (inkubatornia + sala chorych), **Warsztat** (ustawienia), **Ogród wspomnień** (nagrobki + album) |
| Leczenie | **Pobyt w szpitalu**, który trwa — nie natychmiastowe +zdrowie; **zbyt długi pobyt po wyzdrowieniu zmniejsza radość** |
| Domek | **Jeden pokój**, pupile chodzą; braki widać po zachowaniu; klik w pupila → panel |
| Panel pupila | **Wysuwany od dołu** (desktop: z boku); pupil widoczny nad panelem |
| Sygnały zachowań | głodny przy misce + burczenie; smutny w kącie + chmurka; brudny plamki + muszka; chory leży + termometr; śpi w koszyku; szczęśliwy skacze — **zaakceptowane** |
| Główny pupil (widget) | **Towarzysz** (wybór w warsztacie lub „automatycznie” = najbardziej potrzebujący) |
| Widget | **Mini-pokój**: towarzysz duży + reszta mniejsza w tle, dymek potrzeby, bez pasków i przycisków |
| Warianty akcji | **Wybierasz wariant** (3 kafelki po kliknięciu akcji) |
| Skórki jajek | **Losowa przy odbiorze**, na stałe; pula = **wszystkie 5** (kropki, nocne niebo, łączka, tęczowe paski, łaciate) |
| Wyklucie | **Dłuższe**, nakładka pełnoekranowa jak odznaki, ale „cute”, ~4–5 s |
| Pat pat | **Dłoń** klepiąca pupila po głowie |
| Towarzysz | **Pamięta pozycję** między stronami |

## 3. Świat i nawigacja

### 3.1 Adresy (każde miejsce ma URL; przejścia bez przeładowania)

| URL | widok |
|---|---|
| `/client/pupile` | mapa świata |
| `/client/pupile/domek` | pokój; `?pupil=ID` otwiera panel tego pupila |
| `/client/pupile/szpital` | inkubatornia + sala chorych; `?pupil=ID` przewija do łóżka |
| `/client/pupile/warsztat` | ustawienia |
| `/client/pupile/ogrod` | ogród wspomnień |

- Wszystkie trasy: `feature_required` (flaga + rollout → 404), ten sam szablon `client/pets/home.html` z `data-scene`
  i tym samym `data-state` (jeden odczyt `state_for_user` jak dziś). Nieznana podścieżka → 404.
- JS (`pets.js` jako router) przełącza sceny przez `history.pushState`; `popstate` (wstecz) działa; przejście =
  krótki zoom w stronę miejsca (bez animacji przy `prefers-reduced-motion`). W środku sceny przycisk „← Świat”.
- Linki: widget → `/domek?pupil=ID` (pupil) lub `/szpital` (jajko, łóżko); dymek towarzysza → miejsce właściwe dla
  potrzeby; push → wg §6.4.

### 3.2 Mapa

- Kodowane SVG: zielona polanka, ścieżka łącząca miejsca, drzewka/kwiatki. Domek w środku, największy; szpital,
  warsztat, ogród dookoła. Telefon (≤ 640 px): wariant pionowy — miejsca jedno pod drugim przy ścieżce.
- Każde miejsce: element klikalny (`<a>` z `aria-label`, cel dotyku ≥ 44 px), podświetlenie przy hover/focus.
- **Znaczki nad miejscami** (z danych stanu): czerwony krzyż nad szpitalem (ktoś chory lub w szpitalu), „!” nad
  szpitalem (jajko gotowe / do odebrania / pupil wyleczony czeka), serduszko nad domkiem (ktoś głodny/smutny/
  brudny/znudzony), świeczka nad ogrodem (można dziś zapalić światełko).
- **Noc** (`state.night.is_night`): niebo granatowe z gwiazdami, księżyc, światło w oknach domku.
- Light/dark: mapa sama jest ilustracją (kolory dzienne/nocne); w dark tylko tło strony i podpisy wg palety
  glassmorphism z CLAUDE.md.

## 4. Szpital — zmiana zasad gry

### 4.1 Reguły

- Akcja **„Wylecz” znika** (API `heal` → 400 `bad_action`). Kolumna `last_heal_at` zostaje (nieużywana).
- **Przyjęcie** (`admit`): tylko pupil żywy z `health < 75` (chory), nie w szpitalu. Inaczej 409 `not_sick` /
  `in_hospital`. Przy przyjęciu w chwili `t0`: stan symulowany do `t0`, potem `hunger, fun, clean := max(x, floor)`,
  `hospital_since := t0`, `state_at := t0`, zdarzenie `admit`.
- **W szpitalu:** paski stoją (brak spadków), zdrowie rośnie liniowo `100 / hours` na godzinę (cap 100), pupil
  **nie może odejść**, nie śpi wg zegara (`asleep = false`; na łóżku wygląda na drzemiącego), starzeje się normalnie.
  Akcje opieki poza `pat` → 409 `not_available` z powodem „w szpitalu” (jak inne niedostępne akcje; front czyta `reasons`). `pat` działa normalnie (radość zablokowana na ≥ floor i tak rośnie)
  i liczy się jako opieka dnia (`care_days`, `login_streak`).
- **Wyleczony:** chwila `healed_at = t0 + (100 − h0) / rate`. Od niej pupil „czeka na odbiór”.
- **Tęsknota (decyzja Konrada):** zbyt długi pobyt po wyzdrowieniu zmniejsza szczęście. Od `healed_at` **radość
  spada** w normalnym tempie dziennym (`100 / decay_hours.fun` na godzinę × mnożnik gwiazdek, bez nocnego
  spowolnienia — w szpitalu pupil nie śpi wg zegara), aż do 0. Sytość i czystość dalej stoją, zdrowie zostaje 100
  (w szpitalu nie spada). Przy domyślnych liczbach (próg 60, 30 h) radość dochodzi do 0 po ok. 18 h czekania —
  pupil wypisany automatycznie po 24 h wraca smutny i od razu potrzebuje opieki.
- **Odbiór** (`discharge`): ręcznie w każdej chwili (także przed wyleczeniem — z bieżącym zdrowiem) albo
  **automatycznie** po `healed_at + wait_hours`. Odbiór w chwili `td`: stan szpitalny do `td` zapisany
  (`apply_state`), `hospital_since := None`, `state_at := td`, zdarzenie `discharge`. Od `td` zwykła symulacja.
- **Automatyczny wypis jest leniwy** (jak odejście): wyliczany przy odczycie/cronie, zapisywany przy pierwszym
  pełnym odczycie lub w cronie (`persist_discharge`, warunkowy UPDATE `WHERE hospital_since = :t0`).
- Towarzysz i `most_in_need` **pomijają** pupili w szpitalu. Jeśli wybrany towarzysz leży w szpitalu → automat;
  jeśli nikt inny nie żyje → towarzysz się chowa.
- Brak „pauzy gry”: maksymalny czas bez spadków = czas leczenia + `wait_hours` (domyślnie ≤ 8 h + 24 h).

### 4.2 Konfiguracja

Nowy klucz `pets_hospital` (json) = `{"hours": 8, "floor": 60, "wait_hours": 24}` w `PetConfig` (`hospital`),
w formularzu panelu admina (`ADMIN_FIELDS`) z limitami: `hours` 1–168, `floor` 1–100, `wait_hours` 0–168.
Klucz `actions.heal` i `actions.heal_cooldown_h` przestają być używane (zostają w konfiguracji dla zgodności,
znikają z formularza admina).

### 4.3 Dane (jedna migracja)

Tabela `pets`:
- `hospital_since` DateTime NULL — od kiedy w szpitalu (NULL = nie),
- `hospital_healed_at` DateTime NULL — chwila wyzdrowienia ustalona przy przyjęciu (zapis stanu w trakcie
  pobytu, np. po pat pat, jej nie przesuwa; z niej liczy się auto-wypis i tęsknota),
- `hospital_ready_notified_at` DateTime NULL — push „wyzdrowiał” wysłany dla tego pobytu,
- `egg_skin` SmallInteger NOT NULL default 0 (server_default `0`) — skórka jajka 0–4.

Nowe typy zdarzeń (String(20), bez zmiany schematu): `admit`, `discharge`. Oba **nie** są w `PRUNABLE_EVENT_TYPES`.

### 4.4 Symulacja

`simulate_pet(pet, now, cfg)` rozpoznaje `pet.hospital_since`:
1. odcinek szpitalny `[state_at, min(now, td_auto))` — sytość i czystość stałe, zdrowie liniowo w górę do 100,
   radość stała do `healed_at`, potem spada (tęsknota, §4.1); bez odejścia;
2. jeśli `now > td_auto` (auto-wypis) — dalej zwykła `rules.simulate` od `td_auto` ze stanem z końca odcinka 1.
Wynik niesie `in_hospital`, `healed_at`, `auto_discharge_at`, `discharged_at` (gdy auto-wypis wyliczony).
Istniejące gwarancje zostają: DST (`T < state_at` → bez zmian), kroki 5 min poza szpitalem.

### 4.5 API

| metoda | ścieżka | wynik |
|---|---|---|
| POST | `/client/pupile/api/<id>/szpital` | przyjęcie; `{ok, state}`; 409 `not_sick` / `in_hospital`; 410 `pet_gone` |
| POST | `/client/pupile/api/<id>/wypis` | odbiór; `{ok, state}`; 409 `not_in_hospital` |
| POST | `/client/pupile/api/<id>/akcja` | jak dziś + opcjonalne `variant` (§5); `heal` → 400 |

`pet_dict` dostaje `hospital: null | {since, healed_at, ready (bool), progress_pct, auto_discharge_at}`, `can.admit`,
`reasons.admit`; traci `can.heal`, `reasons.heal`, `heal_available_at`. `state.config` dostaje `hospital_hours`.

## 5. Akcje: warianty, pat pat, długość

- `POST …/akcja {action, count?, variant?}`; dozwolone warianty:
  `feed`: `miska` | `jablko` | `ciastko`; `play`: `pilka` | `wloczka` | `banki`; `wash`: `kapiel` | `prysznic` | `gabka`.
  Brak `variant` = pierwszy z listy. Nieznany → 400 `bad_variant`. **Działanie na paski identyczne** dla wariantów;
  wariant nie jest zapisywany w bazie, idzie tylko do GA4 (`pet_action` z parametrem `variant`).
- Animacje wariantów: 3–4 s każda (dziś ~1,8 s), własne rekwizyty; w trakcie przyciski panelu nieaktywne;
  `prefers-reduced-motion` → ≤ 0,9 s, statyczne rekwizyty (jak dziś w rigu).
- **Pat pat:** dłoń SVG wjeżdża z góry nad głowę, klepie 2–3 razy, pupil mruży oczy, czasem serduszko. W domku
  (klik w pupila) i u towarzysza. **Nie w widgecie** (tam klik = przejście). Paczkowanie i limit 60/h bez zmian.

## 6. Miejsca

### 6.1 Domek

- Pokój SVG: ściana, okno (dzień/noc), dywan, miski, koszyk + poduszki do spania, zabawki. Do 8 pupili.
- Pupile spacerują (logika jak u towarzysza, w granicach pokoju, bez nakładania się). **Zachowanie wg najpilniejszej
  potrzeby** (priorytet: chory/krytyczny > śpi > głodny > brudny > smutny/znudzony > szczęśliwy):
  - chory/krytyczny — leży, zielonkawy, termometr; dymek „→ szpital” przy kliknięciu w panel,
  - śpi — idzie do koszyka/poduszki, „zzz”,
  - głodny — idzie do miski, siada, „burczenie” (dymek z miseczką),
  - brudny — plamki, krążąca muszka, drapie się,
  - smutny/znudzony — siedzi w kącie, chmurka z deszczykiem / „…”,
  - szczęśliwy — podskakuje, bawi się zabawką, podchodzi do przodu.
- Brak pasków i przycisków w pokoju. Klik w pupila: pupil podchodzi na środek, lekko się powiększa, reszta przygasa,
  otwiera się panel; drugi klik w niego = pat pat.

### 6.2 Panel pupila

- Telefon: arkusz od dołu (przeciągnięcie w dół / klik w pokój zamyka); ≥ 1024 px: panel z boku.
- Zawartość: imię (edycja), stadium, wiek, gwiazdki, dni opieki, paski sytość/radość/czystość + zdrowie, nastrój
  słownie; akcje: **Nakarm / Pobaw się / Umyj** (każda rozwija 3 kafelki wariantów), **Obudź** gdy śpi,
  **Zabierz do szpitala** gdy chory; powód pod nieaktywną akcją (jak dziś). Fokus, `aria-disabled`, ekstrapolacja
  pasków i obsługa błędów — przeniesione z obecnej `PetCard` (nie pisane od nowa).

### 6.3 Szpital

- **Inkubatornia:** jajka w gniazdkach pod ciepłą lampą, każde w swojej skórce; „Odbierz” (jajka dostępne: start,
  miesięczne, ratunkowe, prezent — jak dziś), „Ogrzej”, „Wykluj”, postęp i czas do wyklucia.
- **Sala chorych:** łóżka z pupilami w szpitalu (kołderka, postęp leczenia, „~N h do wyzdrowienia”, „Odbierz”;
  wyleczony: „Gotowy do odbioru” + przycisk wyróżniony); lista chorych pupili z domku z przyciskiem „Przyjmij”.
- **Wyklucie:** nakładka pełnoekranowa (styl w `modals.css`), ~4–5 s: kołysanie → pęknięcia → ciepłe światło →
  skorupka odskakuje → pupil się przeciąga → serduszka/gwiazdki → pole imienia (walidacja jak dziś, błąd przy polu).
  Duplikat: krótsza wersja (~2,5 s) z gwiazdką na istniejącym pupilu. Odznaki po zamknięciu (jak dziś).
  Reduced-motion: statyczna wersja. ESC/klik w tło nie zamyka w trakcie żądania (jak dziś).

### 6.4 Powiadomienia (zmiany względem v2 §2.9)

- Pupil w szpitalu **nie** podnosi `notify_level` (brak alertów o głodzie/chorobie).
- Nowa pozycja koszyka crona: **„Pupil {imię} wyzdrowiał — odbierz go ze szpitala.”** (push, bez maila), raz na
  pobyt (`hospital_ready_notified_at`). Auto-wypis bez powiadomienia.
- Treść alertu „chory”: „Pupil {imię} jest chory — zabierz go do szpitala.”
- URL pushu wg najwyższej pozycji koszyka: krytyczny/chory/wyleczony/jajko → `/client/pupile/szpital`;
  odejście/ratunkowe → `/client/pupile/ogrod`; reszta → `/client/pupile/domek`.

### 6.5 Warsztat

Drewniany stół z „narzędziami”: ramka ze zdjęciem = wybór towarzysza (lista żywych + „automatycznie”) i włącznik;
dzwonek = przełącznik „Powiadomienia o pupilach”; książeczka = krótkie zasady gry (noc, szpital, jajka, gwiazdki).
Logika zapisu bez zmian (te same endpointy co dziś).

### 6.6 Ogród wspomnień

Nagrobki na trawie (obecny `mountMemorial` + światełko „Zapal światełko” jak dziś) i tablica albumu: 8 gatunków
(żywy = mini-rig, odszedł = nagrobek, nieodkryty = sylwetka bez animacji), licznik `n/8`.

## 7. Widget na dashboardzie

- **Mini-pokój** (te same grafiki co domek, skala widgetu): towarzysz duży na środku z dymkiem potrzeby; do 4
  pozostałych żywych w tle (mniejsze, z zachowaniami); więcej → „+N”. Bez pasków i przycisków.
- Klik w pupila → `/client/pupile/domek?pupil=ID`; klik w jajko / łóżko szpitalne → `/client/pupile/szpital`;
  link „Do świata →” w nagłówku.
- Stany bez żywych: inkubator z jajkami (skórki, „Wykluje się za ~N h”); jajko do odebrania („Odbierz w szpitalu”);
  pupil w szpitalu (łóżko, „Wraca do zdrowia — jeszcze ~N h” / „Gotowy do odbioru”).
- Odświeżanie i straż kolejności stanów jak dziś.

## 8. Towarzysz — pamięć pozycji

`sessionStorage['pets_companion_pos_<user_id>'] = {x_ratio, facing, t}` zapisywane przy każdym kroku spaceru
i na `pagehide`. Przy starcie strony panelu (tryb `walk`): jeśli zapis < 30 min — towarzysz staje dokładnie tam
(bez przejścia CSS) i spaceruje dalej. Tryb `sit` (oferty) ignoruje zapis (prawy dolny róg), ale go nie kasuje.
Towarzysz w szpitalu → wybór automatyczny lub ukrycie (§4.1).

## 9. Architektura frontendu

| plik | odpowiedzialność |
|---|---|
| `static/js/pages/client/pets.js` | boot, router scen (`pushState`/`popstate`), stan (`PetsState`), wspólne akcje |
| `static/js/pet/world/map.js` + `css/pages/client/pets-map.css` | mapa i znaczki |
| `static/js/pet/world/room.js` + `css/components/pet-room.css` | pokój + spacer + zachowania potrzeb (używany przez domek **i widget**) |
| `static/js/pet/world/house.js` | scena domku: pokój + panel |
| `static/js/components/pet-card.js` → panel | obecna karta przebudowana na treść panelu (wariant `mini` usunięty) |
| `static/js/pet/world/hospital.js` + css | inkubatornia + sala chorych |
| `static/js/pet/world/workshop.js` + css | warsztat |
| `static/js/pet/world/garden.js` + css | ogród + album |
| `static/js/components/pet-hatch.js` + sekcja w `modals.css` | nakładka wyklucia |
| `static/js/components/pet-rig.js` / `pet-rig.css` / `species.js` | + zachowania potrzeb, dłoń, rekwizyty 9 wariantów, 5 skórek jajek, łóżko |
| `static/js/pages/client/pets-widget.js` + css | widget na `room.js` (tryb kompaktowy) |
| `static/js/components/pet-companion.js` | + pamięć pozycji |

Zasady jak dotąd: zero inline JS/CSS, light + dark, cele dotyku ≥ 44 px, escapowanie, guardy idempotencji,
bump `CACHE_VERSION`. Obecny układ strony (gniazdko / siatka kart / album / ustawienia) zostaje zastąpiony.

## 10. Testy

- **pytest (TDD):** symulacja szpitala (paski stałe, zdrowie liniowo, brak odejścia, `healed_at`, auto-wypis
  i dalsza symulacja, DST), API `szpital`/`wypis` (uprawnienia, 409/410, cudzy pupil 403), `heal` → 400, warianty
  (dozwolone/nieznany/brak), `egg_skin` losowany przy odbiorze w zakresie 0–4 (deterministycznie z `rng`),
  towarzysz/`most_in_need` pomijają szpital, cron: brak alertów w szpitalu + push „wyzdrowiał” raz na pobyt + URL-e,
  trasy scen (200 / 404 przy fladze off / 404 nieznana podścieżka), migracja (upgrade/downgrade na SQLite),
  formularz admina `pets_hospital` (limity).
- **Przeglądarka (brak runnera JS):** podgląd SQLite (`docs/dev/dev_pets_preview.py`): mapa dzień/noc, wejście do
  każdego miejsca i powrót „wstecz”, zachowania potrzeb w pokoju, panel + warianty + pat z dłonią, szpital
  (przyjęcie → postęp → odbiór), wyklucie (nowy/duplikat), widget (wszystkie stany), towarzysz zachowuje pozycję
  między stronami; 375 / 768 / 1280 px, light/dark, reduced-motion, konsola bez błędów.
- Na końcu świeża recenzja (backend + frontend) i fix pass, jak w etapach 4–6.

## 11. Kolejność prac (paczki)

1. **Backend** (centrala, TDD): migracja, symulacja szpitala, API, warianty, `egg_skin`, trasy scen, cron, admin.
2. **Rig** (subagent): zachowania potrzeb, dłoń, 9 wariantów, 5 skórek, łóżko, nakładka wyklucia.
3. **Świat** (subagent, po 2 lub równolegle na atrapach): router, mapa, domek + panel, szpital, warsztat, ogród.
4. **Widget i towarzysz** (subagent).
5. **Integracja**: podgląd, recenzja, poprawki, raport. Wszystko na `feat/pupile`, bez pusha, za flagą.

## 12. Poza zakresem

Zmiany tempa pasków i zasad odejścia; kosmetyki/ubranka (monetyzacja); nowe odznaki (np. za szpital); raport
`flask pets report` o pobytach w szpitalu; mobilne API; mail przy wyzdrowieniu.
