# Pupile (tamagotchi) — wirtualne zwierzaki dla klientów

**Data:** 2026-10-10 (brainstorming), 2026-10-11 (spec v1), 2026-10-11 (v2 po recenzjach)
**Status:** v2 — po dwóch niezależnych recenzjach i przeglądzie ulepszeń; czeka na przegląd Konrada
**Zadanie ClickUp:** [869ffdb58](https://app.clickup.com/t/869ffdb58) (lista „Odznaki i konkursy")

## 1. Cel i założenia

**Cel biznesowy:** codzienny, szczery powód, żeby klient wracał do serwisu — nawyk i lojalność.
Pupil **nie jest sprzęgnięty z zakupami**: zamówienia niczego mu nie dają, on niczego nie
sprzedaje. Klient, wracając do pupila, przy okazji widzi nowe dropy i oferty. Monetyzacja
(ubranka za drobne wpłaty) jest rozważana na później — ten spec zostawia na nią miejsce, ale jej
nie buduje.

**Dane, na których skalibrowano liczby** (pomiar 2026-10-10, szczegóły w pamięci
`reference_czestotliwosc_wizyt`):

- GA4 (wrz–paź 2026): DAU/MAU 14,7 %, DAU/WAU 25,5 %, WAU/MAU 57,6 %; kohorty tydzień 1: 38,6 %,
  tydzień 4: ~15 %.
- Konkurs 02–17.07.2026 (`contest_spins`, cooldown 8 h, do 3 spinów na dobę, z nagrodami):
  133 osoby, 1346 spinów, mediana **1,1 spinu na aktywny dzień** — ludzie wracają raz dziennie,
  nawet gdy mogą częściej. Szczyty 12:00 i 22:00, dołek 2:00–5:00.
- Najdłuższa przerwa zaangażowanych (≥ 5 spinów, 91 osób) w 16 dni: > 48 h u 51 %, > 72 h u 25 %,
  **> 96 h u 12 %**, > 120 h u 7 %.
- Web push ma 86 z 303 klientów (28 %), `mobile_device` jest puste → ostrzeżenia nie mogą polegać
  wyłącznie na pushu.

**Wnioski wpisane w zasady:** jedna wizyta dziennie wystarcza, by pupil przeżył; dwie–trzy, by był
szczęśliwy; śmierć po ok. 96 h bez opieki jest realna, ale nie codzienna; ostrzeżenia krytyczne
idą także mailem; pierwsza nagroda (wyklucie) musi przyjść w pierwszych dniach, bo w tygodniu 1
odpada 60 % nowych; po stracie użytkownik musi od razu mieć co robić.

## 2. Zasady gry

### 2.1 Gatunki

Osiem gatunków inspirowanych maskotkami ATEEZ, **własna grafika** (kodowane SVG, nie oficjalne
rysunki). Stałe w `modules/pets/species.py` i lustrzane w `static/js/pet/species.js`:

| slug | nazwa robocza | wygląd |
|---|---|---|
| `wiewiorka` | Wiewiórka | pomarańczowa, kremowy brzuszek, ciemniejsze paski na głowie, puszysty ogon |
| `kroliczek` | Króliczek | różowy, długie stojące uszy, iskierki |
| `szczeniak` | Szczeniak | kremowo-żółty, opadające uszy, grzywka |
| `piesek` | Piesek | biały, długie opadające uszy, różowe policzki |
| `kotek` | Kotek | lawendowy, spiczaste uszy z różowym środkiem, biały pyszczek |
| `kurczaczek` | Kurczaczek | żółty, pomarańczowy dziobek, czubek na głowie |
| `czarny-kotek` | Czarny Kotek | czarny, czerwona obroża z dzwoneczkiem, półprzymknięte oczy |
| `mis` | Miś | brązowy, jaśniejszy pyszczek, zielony listek na głowie |

Nazwy robocze zmienia się edycją stałej (nie ma UI do tego — świadomie, YAGNI).

### 2.2 Jajka

Cztery źródła jajek, każde trzeba **odebrać kliknięciem** (dopiero wtedy rusza inkubacja):

| źródło | kiedy dostępne | inkubacja | uwagi |
|---|---|---|---|
| **startowe** | od pierwszego pokazania pupili użytkownikowi (widget, strona, API); dopóki nie odebrane, jest **wirtualne** — profil w bazie powstaje dopiero przy odbiorze | **48 h** (`pets_start_egg_hours`) | odbiór uruchamia licznik miesięczny |
| **miesięczne** | 30 dni od **odebrania** poprzedniego miesięcznego (lub startowego); tylko gdy startowe już odebrane | 168 h | nieodebrane czeka; licznik nie biegnie dalej, więc nie da się nazbierać zaległych |
| **ratunkowe** | **natychmiast** po śmierci pupila (`pets_rescue_hours = 0`), jedno na każdą śmierć | 168 h | nie rusza licznika miesięcznego; jeśli nieodebrane przez 7 dni → jeden mail przypominający |
| **przyznane** (`granted`) | przycisk w panelu admina (wsparcie, nagrody) | 168 h | licznik `granted_eggs_pending` w profilu; nie rusza miesięcznego |

Kilka jajek może inkubować się równocześnie.

**Inkubacja:** N godzin „czasu jajka" (48 lub 168). Akcja **Ogrzej** włącza tempo ×2 na 8 h;
kolejne ogrzanie dopiero, gdy poprzednie wygaśnie. Dla 168 h: jedna wizyta dziennie → wyklucie po
ok. 5,3 dnia, trzy wizyty (co 8 h) → po 3,5 dnia. Dla startowego 48 h: wyklucie przy drugiej–
trzeciej wizycie (z dwoma ogrzaniami ok. 32 h). Jajko nie ma potrzeb, nie głodnieje i nie umiera.
Gotowe jajko czeka na kliknięcie **Wykluj** dowolnie długo.

### 2.3 Wyklucie, duplikaty, gwarancja

Gatunek losuje się **w chwili wyklucia** (nie odebrania), równomiernie spośród ośmiu.

- **Nowy gatunek** (żaden żywy pupil użytkownika nie jest tego gatunku): jajko staje się pupilem,
  dostaje domyślne imię (= nazwa gatunku), użytkownik od razu je zmienia w modalu. Licznik
  duplikatów z rzędu zeruje się.
- **Duplikat** (żyje już pupil tego gatunku): żyjący pupil dostaje **gwiazdkę** (max 5), jajko
  znika z gniazdka (w bazie zostaje jako `merged` z zapisanym gatunkiem — statystyki duplikatów),
  licznik duplikatów z rzędu rośnie o 1.
- **Gwarancja (pity):** gdy licznik duplikatów z rzędu ≥ 2, losowanie ogranicza się do gatunków,
  których użytkownik **aktualnie nie ma żywych** (zmarłe i nigdy nieposiadane). Jeśli wszystkie
  osiem żyje, gwarancja nie ma z czego wybierać i wypada duplikat.
- **Gwiazdka** = widoczne gwiazdki nad głową + każda spowalnia spadek pasków o 10 % (5 gwiazdek =
  o połowę wolniej). Gwiazdki odchodzą razem z pupilem.
- Z powyższego wynika, że użytkownik **nigdy nie ma dwóch żywych pupili tego samego gatunku**, a
  więc maksimum to 8 żywych. Inwariantu pilnuje **blokada wiersza profilu** (sekcja 6), nie
  blokada jajka.

Oczekiwana liczba jajek do kompletu 8 gatunków przy gwarancji po 2 duplikatach ≈ 13,7 (ok. 14
miesięcy samymi miesięcznymi), najgorszy przypadek 22. **Świadoma konsekwencja decyzji „ratunkowe
zastępuje, nie zużywa":** jajka ratunkowe też losują i liczą się do gwarancji, więc celowe
zagłodzenie duplikatu daje dodatkowy rzut co ok. 10 dni (96 h + 168 h inkubacji). Akceptujemy —
kosztem jest utrata gwiazdek i czasu opieki.

### 2.4 Potrzeby i doba

Trzy paski 0–100: **Sytość**, **Radość**, **Czystość**. Spadek liniowy z pełna do zera:
sytość **24 h**, radość **30 h**, czystość **48 h** (mnożnik gwiazdek: `1 − 0,1·gwiazdki`).

**Noc 23:00–07:00 czasu polskiego.** Pupil śpi, chyba że zachodzi którykolwiek warunek budzenia:

- jest głodny (sytość < 30),
- **którykolwiek pasek jest na zerze**,
- jest chory (zdrowie < 75),
- użytkownik go **obudził** (patrz akcje) — wtedy jest obudzony do `awake_until`.

Pupil obudzony przez głód/zero/chorobę zasypia z powrotem, gdy tylko warunek zniknie (np. po
nakarmieniu), bez kary. Śpiący: paski spadają **4× wolniej**, żadna akcja nie jest dostępna (tylko
podglądanie i „Obudź"). Obudzony w nocy: paski normalnie, wszystkie akcje dostępne.

### 2.5 Akcje

| akcja | efekt | warunek dostępności |
|---|---|---|
| **Nakarm** | +50 sytości (max 100) | sytość ≤ 80 („najedzony" powyżej — pupil odmawia, cute gest), nie śpi |
| **Pobaw się** | +50 radości | radość ≤ 80, nie śpi |
| **Umyj** | czystość = 100 | czystość ≤ 80, nie śpi |
| **Wylecz** | +40 zdrowia | zdrowie < 75, ostatnie leczenie ≥ 12 h temu (chory i tak nie śpi) |
| **Pat pat** (klik/dotknięcie) | +0,25 radości za klepnięcie, animacja zawsze | nie śpi; przyrost zaliczany do **60 klepnięć na godzinę na pupila** (limit liczony z `SUM(value)` zdarzeń `pat` z ostatnich 60 min; `value` = liczba **zaliczonych** klepnięć w paczce) |
| **Obudź** | budzi: **−10 radości, −10 czystości** (sytość nietknięta; paski nie schodzą poniżej 1, żeby budzenie samo nie robiło „smutnego"); `awake_until = teraz + 20 min`; każda kolejna akcja w oknie przedłuża je o 20 min od tej akcji | tylko gdy śpi |
| **Ogrzej** (jajko) | tempo ×2 na 8 h | brak aktywnego ogrzania |
| **Zapal światełko** (karta pamięci) | licznik światełek +1, animacja; **zero efektu w grze** | zmarły pupil, raz na dobę (data lokalna) |
| **Odbierz / Wykluj / Zmień imię** | patrz 2.2–2.3 | — |

Z zera do pełnej sytości potrzeba dwóch miseczek. Przeglądarka wysyła klepnięcia **paczkami**
(debounce 2 s, max 50 w jednym żądaniu), nie żądanie na klik.

**Dni opieki** (`care_days`): +1 za pierwszą akcję karmienia/zabawy/mycia/leczenia/pat pat danego
dnia (data lokalna ≠ `last_care_date`). Obudzenie, ogrzanie i światełko się nie liczą. W chwili
podbicia `care_days` serwis woła też `user.update_login_streak()` (**po commicie**, bo ta metoda
commituje sama) — seria logowań zaczyna rosnąć także u osób z „zapamiętaj mnie", które nigdy nie
logują się ręcznie; pięć istniejących odznak `login-streak-*` zaczyna żyć.

**Kamienie milowe:** trwałe zdarzenia `milestone` (niekasowane przez porządki) przy 7/14/30/50/100
dniach opieki, pierwszej gwiazdce i zmianie stadium. W v1 zasilają tylko odznaki i raport; UI
„Dziennik pupila" jest po v1.

### 2.6 Zdrowie, nastroje, odejście

Zdrowie 0–100, startuje ze 100.

- Gdy **którykolwiek pasek = 0**: zdrowie spada **100 → 0 w 72 h** (bez spowolnienia nocnego —
  pasek na zerze budzi pupila, patrz 2.4).
- Gdy **wszystkie paski > 50**: zdrowie rośnie 0 → 100 w 24 h.
- W pozostałych przypadkach stoi.

Nastrój (jedna etykieta, pierwsza pasująca od góry):

| nastrój | warunek | typowy czas od ostatniej pełnej opieki |
|---|---|---|
| `krytyczny` | zdrowie < 25 | ≈ 78 h |
| `chory` | zdrowie < 75 | ≈ 42 h |
| `smutny` | jakikolwiek pasek = 0 | ≈ 24 h |
| `glodny` / `znudzony` / `brudny` | najniższy pasek < 50 | ≈ 12 h |
| `szczesliwy` | wszystko ≥ 50 | — |

Flaga `asleep` jest niezależna od nastroju.

**Odejście:** zdrowie = 0 → `status = dead`, `died_at` = chwila, w której zdrowie dobiło do zera
(z symulacji, nie moment odczytu). **Język w całym UI i mailach: „odszedł do gwiazd"**, nie
„zmarł"/„umarł" (gwiazdki są już motywem gry). Karta w albumie staje się **kartą pamięci**: mały
szary nagrobek z podobizną, imieniem, datami wyklucia i odejścia, wiekiem, dniami opieki, liczbą
światełek i przyciskiem „Zapal światełko". Mail o odejściu zaczyna od tego, co pupil przeżył (wiek,
dni opieki, gwiazdki), a dopiero potem mówi, że jajko ratunkowe już czeka. Jajko ratunkowe jest
dostępne natychmiast.

### 2.7 Wzrost

Stadium wynika z czasu kalendarzowego od wyklucia: **maluch** 0–24 dni, **dziecko** 24–80 dni,
**dorosły** 80+ dni. Dorosły żyje wiecznie, dopóki ma opiekę. Stadium wpływa na proporcje rigu
i liczbę dostępnych gestów (maluch 3, dziecko 5, dorosły 7). **Bez kosmetyki** (ozdób, ubranek,
progów odblokowań) — rig ma pustą warstwę „ubranka" na przyszłość.

### 2.8 Album

Osiem kart, po jednej na gatunek, w stanie: **nieodkryty** (szara sylwetka), **żyje** (pupil,
imię, stadium, gwiazdki) lub **karta pamięci** (odszedł, karta pozostaje odkryta). Komplet = 8
gatunków odkrytych kiedykolwiek. Osobny cel (odznaka): 8 żywych dorosłych naraz.

### 2.9 Powiadomienia

Nowa kategoria preferencji **„Pupile"** (`notification_preferences.pet_updates`, domyślnie
włączona). **Przełącznik musi być widoczny także bez pusha** (dziś kategorie w profilu pokazują się
tylko przy aktywnej subskrypcji — `templates/profile/index.html:244`, `push-settings.js`), bo
steruje też mailami: osobny przełącznik „Powiadomienia o pupilach (push i e-mail)" na stronie
pupili w sekcji towarzysza **i** w profilu poza kartą push; zapis przez istniejący
`POST /notifications/preferences` (dopisać `pet_updates` do `allowed_fields`, `to_dict()` i
domyślnych w `get_preferences`).

| zdarzenie | push | mail |
|---|---|---|
| pupil smutny (pasek 0) | tak | — |
| pupil chory | tak | — |
| pupil krytyczny (≈ 18 h przed odejściem) | tak | **tak** |
| pupil odszedł do gwiazd | tak | **tak** |
| jajko gotowe do wyklucia | tak | — |
| miesięczne jajko czeka | tak | — |
| ratunkowe nieodebrane od 7 dni | — | **tak** (raz) |

Zasady: każdy poziom **raz na epizod** (`notify_level`; epizod kończy się, gdy żaden pasek nie
jest na zerze i zdrowie ≥ 75 — wtedy `notify_level` wraca do 0). Przy kilku pupilach **jeden
zbiorczy push na użytkownika na przebieg crona** i **jeden zbiorczy mail** (sekcje: krytyczne,
odeszły, ratunkowe do odebrania). Cron sprawdza `pet_updates` **zanim** zawoła `PushManager`
(bo `send_to_user` zapisuje wpis w dzwonku przed sprawdzeniem preferencji — `push_manager.py:126-154`),
więc wyłączony przełącznik wyłącza też wpisy w centrum powiadomień. Mail ma dodatkowo globalny
kill-switch admina `notify_pet_alert` (`EmailManager.is_email_enabled`, klucz w `ALLOWED_KEYS`
w `modules/orders/routes.py`), jak każdy inny mail w aplikacji.

## 3. Architektura

### 3.1 Zasada: stan liczony z czasu

W bazie leżą wyłącznie **wartości w chwili ostatniej zmiany + znacznik `state_at`**. Stan „na
teraz" wylicza czysta funkcja z `rules.py`. Każda akcja: przelicz stan do `teraz` → zastosuj
akcję → zapisz nowe wartości ze `state_at = teraz`.

**Odczyt nie zapisuje** — z jednym wyjątkiem: jeśli wyliczone zdrowie = 0, odejście zapisuje się
natychmiast przez warunkowy `UPDATE pets SET status='dead', died_at=?, notify_level=4 WHERE id=?
AND status='alive'`; zdarzenie `die` i zerowanie `companion_pet_id` tylko gdy `rowcount == 1`
(dwie karty naraz nie zrobią dwóch zdarzeń). Cron powiadamia o takim odejściu w następnym
przebiegu (`dead AND death_notified_at IS NULL`). Tworzenie profilu **nie** jest wyjątkiem:
profil powstaje dopiero w `POST …/jajka/odbierz` dla startowego; wcześniej API zwraca
`eggs_available = [{"source": "start"}]` wirtualnie.

Cron co godzinę jest potrzebny **tylko** do powiadomień i porządków. Zatrzymany cron oznacza brak
pushy, nie zamrożoną grę (lekcja z awarii OCR).

**Sposób liczenia:** symulacja **krokami co 5 minut** od `state_at` do `T`, ostatni niepełny krok
liczony ułamkowo. W każdym kroku: czy noc, czy śpi (noc ∧ ¬warunki budzenia ∧ `T ≥ awake_until`),
mnożnik tempa (0,25 we śnie) × mnożnik gwiazdek, spadek pasków, ruch zdrowia (−100/72 h gdy pasek
na zerze; +100/24 h gdy wszystko > 50), wykrycie odejścia (zapamiętaj chwilę). **`elapsed = max(0,
T − state_at)`** — `get_local_now()` to naiwny czas lokalny z DST (`modules/orders/models.py:32`),
więc 25.10 o 03:00 zegar cofa się o godzinę i `T < state_at` jest możliwe; to samo klamrowanie dla
`awake_until`, `boost_until`, `egg_progress_at`. Noc zmiany czasu liczy godzinę za mało/za dużo —
świadomie akceptowane (we śnie ×0,25).

Koszt: odczyt po 4 dniach to ~1150 kroków na pupila, po miesiącu ~8600 — milisekundy. Cron nie
zapisuje stanu (świadomie: zapis w cronie wprowadziłby wyścig z akcjami użytkownika); przy 300
użytkownikach × 8 pupili to maks. kilka milionów kroków na przebieg, czyli sekundy. Jeśli pomiar
w `pets report` pokaże problem, następny krok to liczenie odcinkami analitycznie — nie na v1.

Przeglądarka dostaje z API bieżące wartości i **tempo na godzinę** dla aktualnego kroku,
animuje paski liniowo i odświeża się z serwera **co 5 minut** oraz po każdej akcji. Wzór nie jest
duplikowany w JS — JS tylko ekstrapoluje.

### 3.2 Moduł `modules/pets/`

| plik | odpowiedzialność |
|---|---|
| `__init__.py` | `pets_bp` (`url_prefix='/client/pupile'`) i `pets_admin_bp` (`/admin/pupile`); import `models`, `routes`, `admin_routes` |
| `species.py` | 8 gatunków: slug, nazwa, paleta (do albumu/maili) |
| `config.py` | `PetConfig` — dataclass z domyślnymi liczbami; `PetConfig.load()` jednym zapytaniem `Settings.query.filter(Settings.key.like('pets_%'))`, cache w `flask.g` na czas żądania; testy używają domyślnych. Osobno `pets_feature_for(user)` → (`enabled`, `in_rollout`), cache w procesie na 10 s (wzór `app.maintenance_cache`, `app.py:196-210`; 3 workery gunicorna = do 10 s rozjazdu, akceptowalne) |
| `rules.py` | czysta matematyka bez bazy: `simulate(state, config, from_dt, to_dt) -> state`, `mood()`, `is_night()`, `is_asleep()`, `stage()`, `egg_progress()`; brak importów z Flask/SQLAlchemy |
| `service.py` | `claim_egg`, `warm_egg`, `hatch_egg`, `perform_action`, `light_candle`, `rename_pet`, `set_companion`, `state_for_user(user, lite=False, now=None)`, `admin_grant_egg`, `admin_stats`; każda funkcja przyjmuje `now=None` (wstrzykiwalne w testach, jak `rng`); po commicie woła `AchievementService().check_event(user, 'pet_event')` i `user.update_login_streak()` |
| `routes.py` | strona + JSON API klienta |
| `admin_routes.py` | panel admina |
| `notifications.py` | zbieranie koszyków, zbiorczy push (**synchronicznie** `PushManager.send_to_user`), zbiorcze maile (`send_email_batch_sync`) |
| `cli.py` | grupa `flask pets` z komendami `tick [--dry-run]` i `report [--days N]`; podpięta w `register_cli_commands` w `app.py:924`, `tick` owinięty `_with_request_context` (`url_for(_external=True)` w szablonach maili) |
| `context.py` | context processor `pets_nav` → `{"pets_enabled": bool}` dla sidebara, arkusza PWA i include'u towarzysza |

Rejestracja blueprintów w `app.py:register_blueprints`. Czas: istniejący `get_local_now()`.
Losowość: `random.SystemRandom` z możliwością wstrzyknięcia `rng` (jak `draw_ticket_count`).

### 3.3 Dane (jedna migracja)

**`pet_profiles`** (1:1 z `users`, tworzony przy odbiorze startowego):

| kolumna | typ | uwagi |
|---|---|---|
| `id`, `user_id` | int, FK unique, `ondelete=CASCADE` | kaskada to higiena — konta są anonimizowane, nie kasowane (`User.anonymize()`, `auth/models.py:644`) |
| `companion_pet_id` | FK `pets.id`, nullable, `ondelete=SET NULL` | NULL = automatycznie ten, który najbardziej potrzebuje opieki; `state_for_user` traktuje towarzysza `status != alive` jak NULL |
| `companion_enabled` | bool, default True | |
| `dupes_in_row` | int, default 0 | licznik gwarancji |
| `start_egg_claimed_at` | datetime | = `created_at` profilu |
| `last_monthly_egg_at` | datetime | ustawiane przy odbiorze startowego i każdego miesięcznego |
| `monthly_notified_at` | datetime, nullable | push „miesięczne czeka" raz na dostępność; czyszczone przy odbiorze |
| `granted_eggs_pending` | smallint, default 0 | jajka przyznane z admina, nieodebrane |
| `created_at` | datetime | |

**`pets`**:

| kolumna | typ | uwagi |
|---|---|---|
| `id`, `user_id` | int, FK indeks, `ondelete=CASCADE` | |
| `status` | enum `egg` / `alive` / `dead` / `merged` | |
| `species` | varchar(32), nullable | NULL dopóki `egg`; dla `merged` zapisany wylosowany gatunek |
| `name` | varchar(20), nullable | |
| `egg_source` | enum `start` / `monthly` / `rescue` / `granted` | |
| `egg_hours` | smallint | 48 lub 168 zapisane przy odbiorze (zmiana ustawień nie przestawia trwających inkubacji) |
| `egg_progress_sec`, `egg_progress_at`, `boost_until` | int, datetime, datetime nullable | postęp inkubacji |
| `egg_ready_notified_at` | datetime, nullable | |
| `hatched_at` | datetime, nullable | |
| `merged_into_pet_id` | FK `pets.id`, nullable, `ondelete=SET NULL` | dla `merged` |
| `hunger`, `fun`, `clean`, `health` | float | wartości w chwili `state_at` |
| `state_at` | datetime | |
| `awake_until` | datetime, nullable | okno po „Obudź" |
| `stars` | smallint, default 0 | |
| `care_days`, `last_care_date` | int, date | |
| `last_heal_at` | datetime, nullable | |
| `notify_level` | smallint, default 0 | 0 brak, 1 smutny, 2 chory, 3 krytyczny, 4 odszedł |
| `died_at` | datetime, nullable | |
| `death_notified_at` | datetime, nullable | |
| `rescue_egg_claimed_at` | datetime, nullable | |
| `rescue_reminder_sent_at` | datetime, nullable | mail po 7 dniach, raz |
| `lights_count`, `last_light_date` | int default 0, date nullable | światełka |
| `created_at` | datetime | = odebranie jajka |

Indeks: `(user_id, status)`. Unikalność „jeden żywy na gatunek" pilnuje serwis pod blokadą
profilu (sekcja 6).

**`pet_events`**: `id`, `pet_id` (FK `ondelete=CASCADE`, nullable dla zdarzeń profilu),
`user_id` (FK `ondelete=CASCADE`), `type` (`claim`, `grant`, `warm`, `hatch_new`, `hatch_dupe`,
`merge`, `feed`, `play`, `wash`, `heal`, `pat`, `wake`, `light`, `die`, `rename`, `milestone`),
`value` (int — zaliczone klepnięcia w paczce; dla `milestone` numer progu; 1 dla pozostałych),
`created_at`. Indeksy: `(pet_id, type, created_at)` pod limit pat pat, `(user_id, created_at)` pod
statystyki „aktywni opiekunowie" i raport. Cron usuwa zdarzenia `feed/play/wash/heal/pat/wake/warm/
light` starsze niż 90 dni; `claim/grant/hatch_*/merge/die/rename/milestone` zostają.

**Zmiany w istniejących tabelach:** `notification_preferences.pet_updates` (bool, NOT NULL,
server_default 1); enum `achievement_category` + wartość `pets` — surowym `ALTER TABLE achievement
MODIFY category ENUM(...)` jak w migracji `405efca8e619`, **z guardem `if bind.dialect.name !=
'mysql': return`** (wzór `pk2026080401`), bo lokalny podgląd chodzi na SQLite; lista w modelu
zsynchronizowana.

**`User.anonymize()`** dostaje krok: pupile użytkownika → `status='dead'` (żywe) z `died_at=now`,
`name=NULL`, `companion_enabled=False`, zdarzenia `pet_events` usunięte. Cron i tak filtruje
`User.is_active == True, role == 'client'` (jak `run_daily_checks`).

### 3.4 Konfiguracja (`Settings`, klucze snake_case jak reszta aplikacji, domyślne w kodzie)

| klucz | typ | domyślnie |
|---|---|---|
| `pets_enabled` | boolean | **false** |
| `pets_rollout_pct` | integer | **0** — użytkownik widzi funkcję, gdy `pets_enabled` i `user_id % 100 < pct`; admin/mod zawsze (do testów) |
| `pets_decay_hours` | json | `{"hunger": 24, "fun": 30, "clean": 48}` |
| `pets_night` | json | `{"start": 23, "end": 7, "factor": 0.25}` |
| `pets_health_drop_hours` | integer | 72 |
| `pets_health_regen_hours` | integer | 24 |
| `pets_egg_hours` | integer | 168 |
| `pets_start_egg_hours` | integer | 48 |
| `pets_boost` | json | `{"hours": 8, "factor": 2}` |
| `pets_monthly_days` | integer | 30 |
| `pets_rescue_hours` | integer | 0 |
| `pets_rescue_reminder_days` | integer | 7 |
| `pets_pity_after` | integer | 2 |
| `pets_max_stars` | integer | 5 |
| `pets_stage_days` | json | `{"child": 24, "adult": 80}` |
| `pets_actions` | json | `{"feed": 50, "play": 50, "heal": 40, "heal_cooldown_h": 12, "allow_below": 80, "pat_gain": 0.25, "pat_per_hour": 60, "wake_penalty": 10, "awake_minutes": 20}` |

Zapis json przez `Settings.set_value(key, json.dumps(v), type='json')` (`set_value` robi `str()`,
wzór `modules/orders/routes.py:2188`). Zmiana działa od następnego przeliczenia. Formularz w panelu
admina waliduje zakresy (dodatnie liczby, `0 < factor ≤ 1`, `0 ≤ pct ≤ 100`).

### 3.5 API klienta (JSON)

Wszystkie trasy: `@login_required`; funkcja niedostępna dla użytkownika (flaga/rollout) → 404;
cudzy pupil → 403; CSRF z meta tagu (jak `contest.js`); akcje z `limiter` **per użytkownik**
(`key_func=lambda: str(current_user.id)`, wzór `offers/routes.py:784`) 120/min. Błędy:
`{"ok": false, "error": "<kod>", "message": "<po polsku>"}`.

| metoda i ścieżka | działanie |
|---|---|
| `GET /client/pupile` | strona domku (SSR z pełnym stanem, dalej JS) |
| `GET /client/pupile/api/stan[?lite=1]` | pełny stan; `lite=1` (towarzysz) = **bez żadnych zapisów** (nawet odejścia) i bez albumu |
| `POST /client/pupile/api/jajka/odbierz` `{source, pet_id?}` | `start` (tworzy profil), `monthly`, `rescue` (`pet_id` zmarłego), `granted` |
| `POST /client/pupile/api/jajka/<id>/ogrzej` | ogrzanie |
| `POST /client/pupile/api/jajka/<id>/wykluj` | → `{result: "new"|"dupe", species, pet, starred_pet?, new_achievements: [...]}` |
| `POST /client/pupile/api/<id>/akcja` `{action, count?}` | `feed/play/wash/heal/pat/wake`; `count` tylko dla `pat` (1–50) |
| `POST /client/pupile/api/<id>/swiatelko` | światełko na karcie pamięci |
| `POST /client/pupile/api/<id>/imie` `{name}` | 1–20 znaków, strip, bez znaków sterujących; escapowane przy renderze |
| `POST /client/pupile/api/towarzysz` `{pet_id|null, enabled}` | ustawienia towarzysza |

Kształt `GET …/api/stan` (odpowiedzi akcji zwracają ten sam obiekt pod `state`):

```json
{
  "ok": true,
  "now": "2026-10-11T21:15:00",
  "night": {"start": 23, "end": 7, "is_night": false},
  "eggs_available": [{"source": "monthly"}, {"source": "rescue", "pet_id": 12, "pet_name": "Puszek"},
                     {"source": "granted", "count": 1}],
  "next_monthly_at": "2026-11-02T10:00:00",
  "eggs": [{"id": 15, "progress_pct": 42.1, "ready": false, "boost_until": null, "can_warm": true, "egg_hours": 168}],
  "pets": [{
    "id": 3, "species": "kotek", "name": "Mruczek", "stage": "dziecko", "age_days": 30, "stars": 1,
    "bars": {"hunger": 61.2, "fun": 40.0, "clean": 88.0, "health": 100},
    "rates_per_hour": {"hunger": -3.75, "fun": -3.0, "clean": -1.88, "health": 0},
    "mood": "znudzony", "asleep": false, "awake_until": null,
    "can": {"feed": true, "play": true, "wash": false, "heal": false, "wake": false},
    "reasons": {"wash": "czysty", "heal": "zdrowy", "wake": "nie śpi"},
    "heal_available_at": null, "care_days": 12, "gestures": ["jump", "blink", "sway", "spin", "wave"]
  }],
  "album": [{"species": "wiewiorka", "status": "unknown"},
            {"species": "kotek", "status": "alive", "pet_id": 3},
            {"species": "mis", "status": "memorial", "pet_id": 12, "name": "Puszek",
             "hatched_at": "2026-08-01", "died_at": "2026-09-30", "age_days": 60,
             "care_days": 41, "lights_count": 3, "can_light": true}],
  "companion": {"enabled": true, "pet_id": 3, "auto": false},
  "needs_care": true
}
```

`needs_care` = jakikolwiek pasek < 30, pupil chory/krytyczny, jajko gotowe lub jajko do odebrania
— steruje kropką w nawigacji i dymkiem towarzysza.

### 3.6 Cron `flask pets tick`

Co godzinę, **o :10** (`:00` ma już `check-payment-reminders`, `:05` `check-delivery-confirmations`
— limit połączeń SMTP Hostingera per IP): `10 * * * * cd /var/www/ThunderOrders && venv/bin/flask
pets tick >> logs/cron-pets.log 2>&1`, wpis ręczny w crontabie na serwerze; instrukcja w `docs/`.
Przebieg:

1. Jedno zapytanie o **listę `user_id`** do sprawdzenia: aktywni klienci z pupilami `alive`,
   `egg`, `dead AND death_notified_at IS NULL`, `dead AND rescue_egg_claimed_at IS NULL AND
   rescue_reminder_sent_at IS NULL`, lub z profilem z dostępnym miesięcznym. **Bez `yield_per`**
   (nie ma go w repo, a commit w trakcie strumieniowanej iteracji ją przerywa).
2. Per użytkownik, w osobnej transakcji: pobierz jego pupile, policz stan każdego.
   - Żywe: zdrowie = 0 → zapisz odejście (warunkowy UPDATE jak w 3.1). Wyznacz poziom 1–4; jeśli
     wyższy niż `notify_level` → koszyk + podnieś `notify_level`. Pupil zdrowy (żaden pasek na
     zerze, zdrowie ≥ 75) → `notify_level = 0`.
   - Odeszłe bez `death_notified_at` → koszyk (poziom 4) + znacznik.
   - Odeszłe z nieodebranym ratunkowym ≥ 7 dni i bez `rescue_reminder_sent_at` → koszyk (mail) +
     znacznik.
   - Jajka gotowe bez `egg_ready_notified_at` → koszyk + znacznik.
   - Miesięczne dostępne bez `monthly_notified_at` → koszyk + znacznik.
   - `commit`.
3. Po commicie, jeśli `pet_updates` włączone: **jeden push synchronicznie**
   (`PushManager.send_to_user(..., notification_type='pet_updates', tag='pets')` — nie
   `_fire_and_forget`, bo to wątek `daemon=True` (`push_manager.py:355`) i proces CLI kończy się
   wcześniej) oraz, gdy w koszyku jest krytyczny/odejście/przypomnienie o ratunkowym i
   `is_email_enabled('notify_pet_alert')`: jeden mail przez `send_email_batch_sync`
   (szablon `emails/pets_alert.html` + `.txt`; trafia do `EmailLog` automatycznie).
4. Porządki: `pet_events` akcji starsze niż 90 dni.
5. `--dry-run` wypisuje koszyki bez zapisu i wysyłki. Pod `TESTING` pushe i tak idą synchronicznie.

### 3.7 `flask pets report --days N`

CLI bez UI, liczy z `pet_events`, `pets`, `pet_profiles`, `push_subscriptions`:

- lejek: użytkownicy, którzy zobaczyli funkcję (brak w bazie — przybliżenie: profile) → odebrali
  startowe → wykluli → mają żywego pupila w D7;
- retencja D1/D7/D30 (dzień 0 = `claim` startowego; aktywny = dowolne zdarzenie opieki);
- aktywni opiekunowie dziennie (do porównania z DAU z GA4);
- odejścia na dobę i na 100 żywych; rozkład przyczyn (który pasek pierwszy na zerze — z `die`
  `value` = kod paska);
- czas od podniesienia `notify_level` do następnego zdarzenia opieki (czy ostrzeżenia działają);
- odsetek właścicieli pupili z aktywną `PushSubscription`;
- odbiór ratunkowego w 7 dni od odejścia.

Po stronie klienta `trackEvent('pet_action', {action, mood})` przez `static/js/utils/analytics.js`
(z guardem `typeof`, bez danych wrażliwych).

### 3.8 Odznaki

- `EVENT_METRICS['pet_event'] = ['pets_hatched', 'pet_species_discovered', 'pet_adult_alive',
  'pet_stars_max', 'pet_care_days_max', 'all_badges_unlocked']` (meta-odznaka jak przy
  `profile_update`); ewaluatory w `modules/achievements/checkers.py`.
- `AchievementService().check_event(user, 'pet_event')` po commicie w `hatch_egg` i
  `perform_action`; `/wykluj` zwraca `new_achievements`, a front pokazuje je od razu
  (`window.AchievementUnlock.show()`, `achievement-unlock.js:55`) po zamknięciu modalu i czyści
  `sessionStorage['achievements_last_check']`.
- Stadium dorosłe wynika z czasu, więc `pet-adults-8` jest `trigger_type='cron'` przez istniejące
  `flask achievements check-daily` — **do potwierdzenia na prodzie, że ta komenda jest
  w crontabie** (repo tego nie pokazuje).
- Seed (kategoria `pets`; ikony przez istniejący panel, poza zakresem kodu):

| slug | nazwa | warunek | rzadkość |
|---|---|---|---|
| `pet-first-hatch` | Pierwsze pęknięcie | 1 wyklucie | common |
| `pet-care-7` | Pierwszy tydzień | 7 dni opieki jednego pupila | common |
| `pet-species-4` | Pół drużyny | 4 gatunki w albumie | rare |
| `pet-species-8` | Komplet | 8 gatunków w albumie | legendary |
| `pet-adults-8` | Ośmiu dorosłych | 8 żywych dorosłych naraz (cron) | cosmic |
| `pet-stars-3` | Gwiazdor | pupil z 3 gwiazdkami | epic |
| `pet-care-30` | Opiekun | 30 dni opieki | rare |
| `pet-care-100` | Oddany opiekun | 100 dni opieki | epic |
| `pet-care-365` | Opiekun roku | 365 dni opieki | legendary |

Bez odznak za odejście.

## 4. Frontend

### 4.1 Pliki

| warstwa | plik |
|---|---|
| szablony | `templates/client/pets/home.html`, `templates/client/pets/_widget.html` (dashboard), `templates/client/pets/_card.html` (makro karty do SSR; JS odświeża ten sam DOM), `templates/components/pet_companion.html`, `templates/admin/pets/index.html`, `templates/emails/pets_alert.html` + `.txt` |
| CSS | `static/css/pages/client/pets.css`, `static/css/components/pet-rig.css` (keyframes, stany, konfetti skopiowane z `achievement-unlock.js`), `static/css/components/pet-card.css`, `static/css/components/pet-companion.css`, `static/css/pages/admin/pets.css`; modal wyklucia w `static/css/components/modals.css` |
| JS | `static/js/pet/species.js`, `static/js/components/pet-rig.js`, `static/js/components/pet-card.js`, `static/js/components/pet-companion.js`, `static/js/pages/client/pets.js`, `static/js/pages/admin/pets.js`, `static/js/utils/haptics.js` (nowy helper; wzór z `wms-mobile.js:57-61`, którego nie ruszamy) |
| ikony | `static/img/icons/paw.svg` |
| inne | bump `CACHE_VERSION` w `static/sw.js`; `data-pet-celebrate="1"` na stronach `offers` thank-you i `shop.order_success` |

Wszystko light + dark mode (`[data-theme="dark"]`), żadnego CSS/JS inline poza `data-*`.

### 4.2 Strona „Moje pupile"

1. **Gniazdko** — kafelki jajek do odebrania (źródło; dla ratunkowego imię pupila, który odszedł;
   dla przyznanych liczba), odliczanie do następnego miesięcznego; jajka w inkubacji: pasek
   postępu, „Ogrzej" z odliczaniem ×2 (lub „Wykluj", gdy gotowe). Jajko kołysze się przy ogrzaniu,
   pęknięcia przy 33/66/100 %.
2. **Domek** — siatka kart żywych pupili (1 kolumna na telefonie, do 4 na szerokim ekranie). Karta:
   scena z rigiem (klik = pat pat + wibracja 10 ms), imię (klik = zmiana), stadium, gwiazdki,
   3 paski + zdrowie (tylko gdy < 100), nastrój słownie, przyciski akcji (ikona + etykieta,
   min. 44 px) z `disabled` i podpowiedzią z `reasons`, „Obudź" zamiast akcji, gdy śpi.
3. **Album** — 8 kart (sylwetka / pupil / karta pamięci z nagrobkiem, „odszedł do gwiazd",
   światełkami i przyciskiem „Zapal światełko") + licznik „n/8".
4. **Towarzysz i powiadomienia** — wybór pupila („Zabierz ze sobą"), przełącznik towarzysza,
   przełącznik „Powiadomienia o pupilach (push i e-mail)".
5. Pusty stan (brak żywych pupili i jajek w inkubacji): krótkie wprowadzenie zasad i jajko do
   odebrania.

**Kolejność nakładek na dashboardzie w dniu startu:** popup ogłoszenia → baner PWA/push → odznaki;
zachęta do odebrania startowego jajka pokazuje się dopiero po zdarzeniu `popups-all-closed`
(`popup-announcements.js:119-122,264`). Po odbiorze jajka front wysyła `push-force-banner`
(`push-notifications.js:241`, `push-banner.js:124`) — „Powiadomimy Cię, gdy jajko będzie gotowe"
to najlepszy moment na zgodę na push.

**Modal wyklucia** (`modal-overlay` + `modal-content`): jajko trzęsie się → pęka (wzór wibracji
na Androidzie) → gatunek wyskakuje z konfetti → dla nowego: pole imienia (zapis przez `/imie`);
dla duplikatu: „To drugi Kotek! Twój Mruczek dostaje gwiazdkę ⭐" z animacją gwiazdki. Po
zamknięciu — ewentualne `new_achievements`.

### 4.3 Widget na dashboardzie

`templates/client/pets/_widget.html` włączany w `dashboard.html` pod widgetem konkursu (osobne
widgety, bez wspólnej sekcji — decyzja Konrada). Kontekst z `service.state_for_user`. **Jedna**
karta w wariancie mini (`pet-card--mini`): pupil, który najbardziej potrzebuje opieki; jeśli nikt
nie żyje — jajko do odebrania lub postęp inkubacji; przed odebraniem startowego — zachęta „Odbierz
swoje pierwsze jajko". Szybkie akcje (karm/baw/myj) + link „Do domku". Ten sam `pet-card.js`.
Nic, gdy funkcja dla użytkownika niedostępna.

### 4.4 Towarzysz na stronach

`templates/components/pet_companion.html` włączany w `base_client.html` i `offers/base_offers.html`
**przed `extra_js`** (zalogowany, `pets_enabled` z context processora). O tym, czy pokazać
(`companion_enabled`, który pupil), decyduje JS z cache — SSR nie dokłada zapytań.

- Stały element na dole widoku (`position: fixed`), na telefonie mniejszy i nad dolnym paskiem PWA.
- **Panel klienta:** spaceruje w lewo/prawo w obrębie szerokości okna, przystaje, odwraca się,
  ziewa, czasem podskakuje. **Strony ofert:** siedzi w prawym dolnym rogu, nie spaceruje; fetch
  stanu odroczony (`requestIdleCallback`/po `load` + kilka s), żeby nie konkurować z live dropem.
- W nocy śpi zwinięty z „zzz". Dymek „Jestem głodny!" / „Jajko gotowe!" (z linkiem), gdy
  `needs_care`. Klik = pat pat (paczkowane) + wibracja.
- `data-pet-celebrate="1"` na stronie podziękowania (oferty i sklep) → podskok z serduszkami
  (zamówienie przekierowuje natychmiast po złożeniu, więc zdarzenie z checkoutu by zginęło).
- Szanuje `prefers-reduced-motion` (statyczna poza, bez spaceru, bez wibracji).
- Stan z `api/stan?lite=1` z cache w **`localStorage`** (klucz z `user_id`, TTL 5 min,
  unieważniany po każdej akcji) — `sessionStorage` jest per karta i mnożyłby zapytania.
- Ustawia kropkę `needs_care` przy „Moje pupile" w sidebarze i arkuszu PWA.

### 4.5 Rig SVG

- Jedna struktura warstw (`<g>` z `transform-origin`): cień, ogon, ciało, łapki, głowa (uszy,
  oczy, policzki, buzia, grzywka/czubek), **pusta warstwa `accessories`**, gwiazdki, ikonki stanu
  (zzz, chmurka choroby, łezka, serduszko).
- `species.js`: dla każdego gatunku kształty SVG do każdej warstwy + paleta (`base`, `light`,
  `dark`, `cheek`, dodatki jak obroża/listek). **Nowy gatunek = nowe kształty, zero nowej
  mechaniki.** Cel: ≤ 6 KB na gatunek.
- Stadia jako proporcje: maluch (głowa 1,3×, ciało 0,7×), dziecko (1,15× / 0,85×), dorosły 1:1.
- Animacje w `pet-rig.css`, sterowane klasami stanu z `pet-rig.js`: `idle` (oddech + losowe
  mruganie co 3–6 s), `sleep`, `sad`, `sick`, `critical`, `eat`, `play` (piłka — jedyna sekwencja
  na `requestAnimationFrame`), `wash`, `pat`, `hatch`, `celebrate`. Gesty: `jump`, `blink`, `sway`
  (maluch); + `spin`, `wave` (dziecko); + `dance`, `flip` (dorosły).
- Karta pamięci: ten sam rig w szarościach (`grayscale` + zamknięte oczy) w owalnej ramce
  nagrobka; światełko = mały płomyk z animacją.
- Jajko: osobny mały komponent (kołysanie, pęknięcia 0/33/66/100 %).
- Haptyka (`haptics.js`): `navigator.vibrate(10)` przy pat, wzór `[30, 50, 30, 50, 80]` przy
  wykluciu; brak API na iOS — bez obietnic w UI; wyłączone przy reduced motion.

### 4.6 Nawigacja

„Moje pupile" (ikona łapki) w `sidebar_client.html` między Osiągnięciami a Konkursem oraz
w arkuszu „więcej" w `bottom_bar_client.html` — **tylko gdy `pets_enabled`** z context processora
(inaczej link prowadziłby do 404); `active` po `request.endpoint` z prefiksem `pets.`. Kropka
`needs_care` z JS.

## 5. Panel admina (`/admin/pupile`)

Role `admin`/`mod` (`role_required`). Pozycja w `sidebar_admin.html` obok Konkursów.

- **Włącznik** `pets_enabled`, **procent rolloutu** `pets_rollout_pct` i formularz liczb z 3.4
  (walidacja, `Settings.set_value`, `log_activity('pets_settings_updated')`). Kill-switch maila
  `notify_pet_alert` siedzi w istniejących ustawieniach maili (`ALLOWED_KEYS`), nie tu.
- **Statystyki:** profile, żywi per gatunek, jajka w inkubacji / do odebrania, odejścia 7/30 dni,
  aktywni opiekunowie dziś / 7 dni, rozkład stadiów, liczba kompletów, odsetek właścicieli
  z pushem. Szczegółowe metryki — `flask pets report`.
- **Użytkownik:** wyszukiwarka po mailu/nazwisku → lista pupili ze stanem + **„Przyznaj jajko"**
  (`granted_eggs_pending += 1`, zdarzenie `grant`, `log_activity('pet_egg_granted')`).

## 6. Bezpieczeństwo i współbieżność

- Własność pupila sprawdzana w serwisie (`pet.user_id == user.id`), nie tylko w trasie.
- **Mutex użytkownika:** każda operacja zapisu (`claim_egg`, `hatch_egg`, `perform_action`,
  `light_candle`, `rename_pet`, `set_companion`) zaczyna się od
  `PetProfile.query.filter_by(user_id=...).with_for_update().one()` (wzór
  `offers/place_order.py:102`); dopiero potem czyta żywe gatunki / dostępne jajka. Dwa równoległe
  „Wykluj" dwóch jajek nie dadzą dwóch żywych tego samego gatunku, dwa „Odbierz" nie dadzą dwóch
  miesięcznych. Na SQLite `FOR UPDATE` jest no-op — test wyścigu nie istnieje, inwariant pilnują
  testy sekwencyjne + warunkowe UPDATE-y.
- Odejście przy odczycie: warunkowy UPDATE z `rowcount` (3.1).
- Limit pat pat liczony z `pet_events` (`SUM(value)`), `count` przycinany do 1–50; limiter per
  użytkownik.
- Imię: długość 1–20, strip, bez znaków sterujących; zawsze renderowane przez `{{ }}` /
  `textContent` (lekcja `escapeHtml`: żadnych inline `onclick` z danymi).
- Strona domku: zapytanie o profil, o pupile, o zdarzenia pat z ostatniej godziny (tylko przy
  akcji). Brak N+1.
- Towarzysz: `lite=1` bez zapisów + cache 5 min w `localStorage`.
- Cron: lista ID, transakcja i commit per użytkownik, wysyłka po commicie, synchronicznie.

## 7. Wdrożenie

1. Deploy z `pets_enabled = false`, `pets_rollout_pct = 0` (migracja wchodzi webhookiem razem
   z kodem). Nic nie jest widoczne dla klientów.
2. Ręcznie na serwerze (instrukcja w `docs/superpowers/plans/`): `flask achievements seed`
   (deploy.sh robi tylko `db upgrade`), linia crona `10 * * * *` dla `pets tick`, sprawdzenie, że
   `flask achievements check-daily` jest w crontabie, `flask pets tick --dry-run`.
3. Włączenie: `pets_enabled = true`, `pets_rollout_pct` **10 → 50 → 100 %** w ok. 2 tygodnie;
   admin/mod widzą od razu. Startowe jajko powstaje leniwie — bez masowej migracji danych.
   Po każdym kroku `flask pets report --days 7`.
4. Ogłoszenie dla klientów: popup `display_mode='once'` z `cta_url=/client/pupile` (istniejące
   `modules/admin/popups_models.py`) + krok „pets" w tourze — Konrad decyduje kiedy; poza zakresem
   kodu v1 poza samym krokiem toura.
5. Mobilne API: poza v1 (0 urządzeń). Serwis zwraca słowniki gotowe pod `api_mobile/pets_routes.py`.

Lokalny podgląd: XAMPP na tym Macu nie wstaje — weryfikacja wizualna na SQLite wg
`reference_xampp_nie_wstaje_apple_silicon` (stąd guard dialektu w migracji enumu).

## 8. Testy (pytest, `python -m pytest`, TDD)

`TestingConfig` wyłącza CSRF i limiter (`config.py:175-176`) — testy tych mechanizmów dostają
własne fixture włączające `WTF_CSRF_ENABLED` / `RATELIMIT_ENABLED` (precedens limitera:
`tests/test_mobile_api_auth.py:469-479`). Funkcje serwisu przyjmują `now=` i `rng=`, więc testy
czasu nie monkeypatchują `get_local_now`.

| plik | zakres |
|---|---|
| `tests/test_pets_rules.py` | spadki pasków, mnożnik gwiazdek, noc ×0,25, budzenie głodem / zerem dowolnego paska / chorobą, `awake_until`, spadek zdrowia 72 h → odejście ≈ 96 h z chwilą odejścia, regeneracja 24 h, nastroje, stadia 24/80, postęp jajka 48/168 h z ogrzaniem ×2/8 h (granica, dwa ogrzania), ostatni krok ułamkowy, determinizm siatki, **`T < state_at` (DST) → brak zmian** |
| `tests/test_pets_eggs.py` | startowe wirtualne → profil przy odbiorze; miesięczne co 30 dni od odbioru, dopiero po startowym, bez kumulacji; ratunkowe od razu, jedno na odejście, nie rusza miesięcznego; `granted` z licznikiem; wyklucie z `rng`: nowy / duplikat / gwarancja po 2 / wszystkie żywe; gwiazdka max 5; nigdy 2 żywe tego samego gatunku; `merged` ze species; zerowanie licznika; `egg_hours` zamrożone przy odbiorze |
| `tests/test_pets_actions.py` | zasada ≤ 80, dwie miseczki z zera, zabawa/mycie, leczenie (< 75, 12 h), pat pat (+0,25, limit 60/h przez `SUM`, paczki, przycinanie), obudź (kara z klamrą ≥ 1, okno 20 min, przedłużanie), blokada we śnie, dni opieki + `update_login_streak` po commicie, kamienie milowe, światełko raz na dobę, odejście przy odczycie (warunkowy UPDATE, `companion_pet_id` → NULL), cudzy pupil → 403, imię (walidacja) |
| `tests/test_pets_cron.py` | poziomy raz na epizod i reset, zbiorczy push per użytkownik **synchronicznie**, odejście zapisane przy odczycie powiadamiane w cronie, mail tylko krytyczny/odejście/ratunkowe 7 dni, `pet_updates=False` → zero wywołań i zero wpisów `Notification`, kill-switch `notify_pet_alert`, nieaktywni/anonimizowani pomijani, jajko gotowe / miesięczne raz, `--dry-run` bez zapisu, porządki 90 dni z wyjątkami |
| `tests/test_pets_routes.py` | strona i API: logowanie, flaga/rollout → 404 i brak linku w sidebarze, kształt JSON `api/stan` i `lite=1` bez zapisów, CSRF (fixture), limiter per użytkownik (fixture), widget w stanach (pupil / jajko / przed startem / brak), towarzysz w `base_client` i `base_offers` tylko gdy włączony, `new_achievements` z `/wykluj` |
| `tests/test_pets_achievements.py` | `pet_event` odblokowuje odznaki, `all_badges_unlocked`, `pet-adults-8` przez cron odznak |
| `tests/test_pets_admin.py` | zapis ustawień z walidacją (w tym `pct`), statystyki, przyznanie jajka, `role_required` |
| `tests/test_pets_report.py` | metryki raportu na danych syntetycznych |
| `tests/test_pets_anonymize.py` | `anonymize()` uśmierca pupile, czyści imiona i zdarzenia |

Frontend bez runnera JS w repo → weryfikacja w podglądzie przeglądarki na SQLite (zrzuty ekranu
light/dark, telefon/desktop, `prefers-reduced-motion`), logika w JS celowo cienka.

## 9. Etapy wdrożenia

Każdy etap = osobne commity i działająca całość (flaga chroni produkcję).

1. **Fundament:** moduł, modele, migracja (z guardem enumu), `species.py`, `config.py`
   (+ rollout), `rules.py` + testy reguł (w tym DST).
2. **Serwis:** mutex profilu, jajka (4 źródła), wyklucie z gwarancją, akcje, noc/budzenie, dni
   opieki + `login_streak`, kamienie milowe, światełko, odejście przy odczycie, `anonymize()`
   + testy.
3. **Cron i powiadomienia:** `pets tick` (synchroniczne pushe, `send_email_batch_sync`), preferencja
   `pet_updates` (model + `allowed_fields` + przełącznik w profilu poza kartą push), kill-switch
   `notify_pet_alert`, maile + testy.
4. **Strona domku:** trasy + API (w tym `lite`), context processor, szablony, rig SVG z 8
   gatunkami i animacjami, karta, modal wyklucia z odznakami od razu, haptyka, nawigacja
   warunkowa (wewnętrznie: rig → karta → strona → modal).
5. **Widget i towarzysz:** `_widget.html`, `pet-companion.js` (cache `localStorage`, `lite`,
   odroczony fetch na ofertach), `data-pet-celebrate`, `push-force-banner` po odbiorze, kolejność
   nakładek, kropka w nawigacji, bump `CACHE_VERSION`.
6. **Odznaki, admin, raport, dokumentacja:** metryki + seed, `/admin/pupile` (z rolloutem),
   `flask pets report`, zdarzenia GA4, krok toura, instrukcja crona i checklista włączenia.

## 10. Poza zakresem (świadomie)

Kosmetyka i monetyzacja (ubranka), mini-gry, mobilne API, ranking/społeczność, UI do zmiany nazw
gatunków, przenoszenie pupili między kontami, **pauza gry z przesunięciem czasu** (odrzucona przez
Konrada), **wspólna sekcja „Codziennie" ze spinem konkursu** (odrzucona), zapis stanu przez cron
(odłożony do czasu pomiaru), UI „Dziennik pupila", udostępnianie obrazka pupila z rigu, rytuał
„Utul do snu", dźwięk WebAudio.

## 11. Historia recenzji

v1 → v2 (2026-10-11): dwie niezależne recenzje techniczne i przegląd ulepszeń. Poprawione:
powiadamianie o odejściu zapisanym przy odczycie; pushe z crona synchronicznie (wątek daemon);
mutex na profilu zamiast blokady jajka; usunięty `yield_per`; licznik miesięczny od odbioru
startowego; profil tworzony tylko w POST; reprezentacja jajek `granted`; przełącznik `pet_updates`
widoczny bez pusha + sprawdzany przed `PushManager` + kill-switch maila; anonimizacja zamiast
kasowania kont; `companion_pet_id` po odejściu; DST; budzenie przy dowolnym zerze; klamra kary za
budzenie; nazwy zgodne z kodem (`register_cli_commands`, `pets_*`, `json.dumps`, limiter per
użytkownik); migracja enumu z guardem; krok seedu w wdrożeniu; fixture CSRF/limitera; `now=`
wstrzykiwane. Decyzje produktowe Konrada po przeglądzie: start 48 h, ratunkowe od razu + mail po
7 dniach, rollout %, raport CLI, kamienie milowe, „odszedł do gwiazd" + światełko, seria logowań
z opieki, haptyka; odrzucone: pauza gry, sekcja „Codziennie".
