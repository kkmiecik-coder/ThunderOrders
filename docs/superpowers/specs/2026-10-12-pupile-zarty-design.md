# Pupile — bieg towarzysza i żarty (spec v3.2)

**Data:** 2026-10-12 · **Task ClickUp:** 869ffdb58 · **Gałąź:** `feat/pupile` (niepushowana)
**Uzupełnia:** spec v3 (`2026-10-11-pupile-swiat-design.md`) i v3.1 (`2026-10-11-pupile-pelny-ekran-szpital-design.md`).
Gdzie ten dokument mówi inaczej, wygrywa v3.2. Zasady gry (opieka, szpital, jajka, odejścia) **bez zmian**.

## 1. Decyzje Konrada

1. **Bieg na 4 łapach to podstawowy ruch towarzysza**, nie żart. Wchodzi do `pet-companion.js` jako rozszerzenie
   obecnego spaceru.
2. **Żarty to dwie rzeczy:** kradzież kursora i wychylenie zza krawędzi z obrazkiem w pyszczku.
3. **Element zaskoczenia:** żaden ekran użytkownika nie wymienia, jakie żarty istnieją. Użytkownik ma **jeden
   przełącznik** wyłączający wszystkie żarty naraz, w **warsztacie**.
4. **Obrazki** do wychylania wgrywa i zarządza nimi admin w panelu. To ozdobniki: bez tekstu i bez linku.
5. **„x"** w prawym górnym rogu obrazka zamyka **tylko ten obrazek** (na 7 dni, `localStorage`).
6. **Kradzież kursora z prawdziwym efektem:** prawdziwy kursor znika, pupil ciągnie narysowany kursor 2–3 s,
   kliknięcia są wtedy zablokowane. Tylko urządzenia z myszą.
7. **Architektura:** osobny moduł żartów działający na istniejącym towarzyszu (jedna postać, bez duplikatu).

Dodane przeze mnie, do skreślenia na przeglądzie:

- **D1.** Jeden globalny wyłącznik admina „Żarty pupili włączone" (awaryjnie, bez deployu).
- **D2.** Szansa biegu około 20% na krok, a chory i krytyczny nie biegają (idą jak dotąd).
- **D3.** Odstępy między żartami i limity kradzieży kursora (§5.1).

## 2. Zakres

**W zakresie:** bieg w spacerze i nowa poza `run` w rigu; API towarzysza dla modułu żartów; moduł `pet-jokes`;
model `PetPeekImage` i karta w `/admin/pupile`; kolumna `jokes_enabled`; przełącznik w warsztacie; globalny
wyłącznik admina; endpoint obrazków; testy; podgląd deweloperski.

**Poza zakresem:** żarty na stronach sprzedaży (tryb `sit`) i na stronie świata (`#petsApp`, towarzysz się tam
nie pokazuje); kolejne żarty; dźwięki; teksty i linki w obrazkach; statystyki żartów; animowane GIF-y (bierzemy
pierwszą klatkę); sprawdzanie na prawdziwym telefonie i w PWA.

## 3. Bieg (ruch podstawowy)

W `static/js/components/pet-companion.js`:

- Stałe: `RUN_SPEED = 170` px/s (spacer: `WALK_SPEED = 40`), `RUN_CHANCE = 0.2`, `RUN_MIN_DIST = 200` px.
- `walkStep`: po `pickTarget` pupil biegnie, gdy `Math.random() < RUN_CHANCE`, dystans ≥ `RUN_MIN_DIST`
  i `pet.mood` nie jest `chory` ani `krytyczny`. Czas przejścia = dystans / prędkość (jak dziś `secs`).
- Klasa `pet-companion--running` jest nakładana razem z `--walking`. Przyspiesza kołysanie sceny
  (`pet-companion-bob`) i daje niższy, szybszy rytm.
- `syncPose()` wybiera `run` (obok `stand` i `sit`) dla biegnącego pupila. `arrived()` i `stopWalk()` zdejmują
  bieg i wracają do `stand`. Chwycenie i klik w biegu zatrzymują go jak dotąd.
- **Rig:** `PetRig.POSES` dostaje `run`. W `pet-rig.css` poza `.pet-rig.pose-run:not(.pose-off)`: korpus pochylony
  do przodu, głowa wysunięta, ramiona jako przednie łapy pracują naprzemiennie, stopy w galopie, ogon w górę.
  Wszystko na skalach i obrotach warstw (`.rig-body`, `.rig-head`, `.rig-arm-l/-r`, `.rig-feet`, `.rig-tail`),
  więc działa dla 8 gatunków bez przerysowywania. Wzorzec jak istniejące pozy `sit` i `lie`.
- Ruch ograniczony i tryb `sit` bez zmian (spacer jest wtedy wyłączony). Bieg nie zależy od żadnego wyłącznika.

## 4. API towarzysza dla żartów

`pet-companion.js` rejestruje w trybie `walk` obiekt `window.PetCompanionApi` (nie istnieje w trybie `sit`):

| Metoda | Znaczenie |
|---|---|
| `ready()` | `true`, gdy pupil jest, nie śpi, nie jest trzymany, bez dymka, karta widoczna, ruch nieograniczony |
| `rect()` | `{x, y, w, h}`: bieżąca pozycja w px okna (w trakcie marszu z `getBoundingClientRect`) |
| `claim(onBreak)` | zajmuje pupila: spacer i dymki stoją; zwraca funkcję `release()`; `onBreak` woła się, gdy coś przerwie (chwycenie, klik w pupila, sen, zmiana towarzysza, ukrycie) |
| `runTo(x, y, opts)` | `Promise<boolean>`: biegnie po prostej w biegu (`RUN_SPEED`), `true` po dotarciu, `false` przy przerwaniu; `opts.allowOutside` zdejmuje ograniczenie do obszaru spaceru (dla wychylenia); `opts.face` ustawia zwrot po dotarciu |
| `face(dir)` | `'left'` / `'right'` |

Wszystko poza tym zostaje w module towarzysza: zapis pozycji, dymki, pat, przenoszenie. Chwycenie pupila
podczas `claim` kończy żart przez `onBreak`.

## 5. Żarty: moduł `pet-jokes`

Nowe pliki `static/js/components/pet-jokes.js` i `static/css/components/pet-jokes.css`. `templates/components/pet_companion.html`
ładuje je tylko dla `companion_mode == 'walk'` (po `pet-companion.js`). Kolory elementów żartów działają w obu
motywach: stałe, z obrysem, a przycisk „x" ma wariant `[data-theme="dark"]`.

### 5.1 Harmonogram i warunki

- Pierwszy żart najwcześniej **90 s** po wejściu, kolejne co **120–300 s** (losowo). Czas „następnego" siedzi
  w `sessionStorage['pets_jokes_next_<uid>']`, więc przechodzenie między stronami go nie zeruje.
- Żart startuje tylko, gdy **wszystkie** warunki są prawdziwe:
  1. `state.companion.jokes === true` (profil ∧ wyłącznik admina, §6.8);
  2. brak `prefers-reduced-motion` (ani klasy `.pet-rig-rm`);
  3. `PetCompanionApi.ready()`;
  4. brak otwartego modala/arkusza/koszyka (`.modal-overlay.active`, `.cart-sidebar.mobile-open`,
     `.cart-mobile-overlay.active`, pełnoekranowe wyszukiwanie i powiadomienia);
  5. fokus nie jest w polu tekstowym (`input`, `textarea`, `select`, `[contenteditable]`);
  6. na stronie nie ma pasków zakupowych (`OBSTACLES` z towarzysza: `.checkout-bottom-bar`, `.product-sticky-bar` itd.);
  7. karta jest widoczna.
- Wybór: wychylenie (waga 0,7, tylko gdy są aktywne, niezamknięte obrazki), kursor (waga 0,3, tylko gdy spełnione
  warunki §5.2). Kursor najwyżej **2 razy na sesję karty** i nie częściej niż co **10 min**
  (`sessionStorage['pets_jokes_cursor_<uid>']`).
- Jeden żart naraz. Wyłączenie żartów w trakcie (zmiana stanu przez `PetsState.onChange`) kończy bieżący
  natychmiast.
- `window.PetJokes.trigger('cursor' | 'peek')` uruchamia żart poza harmonogramem (testy i podgląd); zwraca `false`,
  gdy warunki nie są spełnione.

### 5.2 Kradzież kursora

Warunki dodatkowe: `matchMedia('(hover: hover) and (pointer: fine)')`, ostatni `mousemove` sprzed ≤ 3 s,
kursor w oknie. Nasłuch `mousemove` jest pasywny i zapisuje tylko dwie liczby.

1. `claim`. Pupil **biegnie** (`runTo`) do punktu obok kursora (nie na kursor).
2. Po dotarciu: `html` dostaje `pet-jokes--no-cursor` (`cursor: none` na wszystkim), pojawia się
   **narysowany kursor** (SVG strzałki, biała z ciemnym obrysem) w łapkach pupila i **przezroczysta warstwa**
   (`position: fixed; inset: 0`) blokująca kliknięcia i hover. Z-index: nad sidebarem (1000) i koszykiem (1090–1100),
   pod pełnoekranowymi nakładkami (1200).
3. Pupil biegnie z kursorem 150–250 px w stronę najbliższej krawędzi obszaru, odwraca się i **upuszcza** kursor.
4. Kursor wraca: warstwa i klasa znikają, a prawdziwy kursor jest tam, gdzie fizycznie jest mysz.
5. `release`. Pupil wraca do spaceru.

**Bezpieczeństwo (niepodlegające negocjacji):** funkcja `restoreCursor()` jest idempotentna i wołana ze wszystkich
ścieżek końca. Kończą żart natychmiast: **Esc i dowolny klawisz**, **kliknięcie** (nie przechodzi do strony),
dotyk, `blur` okna, `visibilitychange`, `pagehide`, wyłączenie żartów, `onBreak`. Twardy timer **3 s** w `try/finally`
gwarantuje, że `cursor: none` nigdy nie zostaje. Dodatkowo (pas i szelki): pierwszy `mousemove` po końcu żartu, gdy
klasa jeszcze jest, wymusza `restoreCursor()`.

### 5.3 Wychylenie z obrazkiem

1. Losowy aktywny, niezamknięty obrazek (innego niż ostatnio pokazany). Lista z `GET /client/pupile/api/wychylenia`
   pobierana leniwie przed pierwszym wychyleniem i trzymana w `sessionStorage` 5 min. Pusta lista = brak wychylenia.
2. Losowa krawędź:
   - **lewa**: pod sidebar. Sidebar ma `z-index: 1000`, a towarzysz `890`, więc pupil przesunięty o ~55% swojej
     szerokości za `.main-wrapper` jest po prostu zasłonięty. Tylko gdy sidebar jest widoczny (desktop).
   - **prawa** i **dolna**: pupil wychodzi poza okno (`position: fixed` poza oknem nie tworzy przewijania).
   - Na telefonie: prawa i dolna krawędź okna, z uwzględnieniem dolnego paska PWA i `env(safe-area-inset-*)`.
3. `claim`, `runTo(..., { allowOutside: true })` do punktu, w którym widać ~45% pupila, zwrócony twarzą do środka.
4. Obrazek (`<img alt="">`, ~72 px) wsuwa się przy pyszczku z lekkim kołysaniem, razem z przyciskiem „x".
   Pozostaje ~**6 s**, a potem pupil chowa się i wraca do spaceru. `release`.
5. **„x"** w prawym górnym rogu obrazka: cel dotyku ≥ 44 px (przycisk ~28 px wizualnie, reszta to pole trafienia),
   `aria-label="Zamknij obrazek"`, także **Esc**. Zamyka obrazek od razu, pupil chowa się, a `localStorage['pets_peek_closed_<id>']`
   dostaje znacznik czasu (TTL 7 dni; każdy dostęp w `try/catch`). Zamknięty obrazek nie jest losowany do końca TTL.
6. Czas ekspozycji się **wstrzymuje**, gdy przycisk ma fokus klawiatury lub nad obrazkiem jest kursor/palec
   (wniosek z recenzji dymków: nie znikać spod fokusu).
7. Pat pupila na czas wychylenia jest wyłączony (`pointer-events: none` na przycisku `hit`).

## 6. Dane i admin

### 6.1 Model `PetPeekImage` (`pet_peek_images`)

| Kolumna | Typ |
|---|---|
| `id` | Integer, PK |
| `filename` | String(80), NOT NULL, unique |
| `label` | String(60), NULL (nazwa dla admina) |
| `is_active` | Boolean, NOT NULL, default `True`, `server_default 1` |
| `created_at` | DateTime, default `get_local_now` |
| `created_by` | FK `users.id`, `ondelete SET NULL`, NULL |

### 6.2 Profil

`PetProfile.jokes_enabled`: Boolean, NOT NULL, default `True`, `server_default 1`.

### 6.3 Migracja

Jedna migracja Flask-Migrate: `create_table pet_peek_images` + `add_column pet_profiles.jokes_enabled`,
z `downgrade`. Test w stylu `tests/test_pets_migration.py`. Nowa pusta tabela i kolumna z domyślną wartością:
bez ryzyka dla istniejących danych.

### 6.4 Upload obrazka

Moduł `modules/pets/peek_images.py`. Zwykłe `compress_image` **nie nadaje się** (spłaszcza przezroczystość do
białego tła, a ozdobniki jej potrzebują), więc osobny zapis:

- rozszerzenia `png`, `jpg`, `jpeg`, `webp`, `gif`; plik źródłowy ≤ **2 MB**; weryfikacja Pillow
  (`validate_image_file`);
- `ImageOps.exif_transpose`, konwersja do RGBA, `thumbnail((240, 240), LANCZOS)`, zapis **WebP** (jakość 85);
- nazwa `uuid4().hex + '.webp'` w `static/uploads/pet_peeks/`; GIF = pierwsza klatka;
- limit **30** obrazków; usunięcie rekordu kasuje plik (błąd systemu plików nie blokuje usunięcia).

### 6.5 Trasy admina (`pets_admin_bp`, `role_required('admin', 'mod')`, CSRF, `log_activity`)

- `POST /admin/pupile/obrazki`: upload (formularz `multipart`, redirect z `flash`, jak `save_settings`);
- `POST /admin/pupile/obrazki/<int:id>/przelacz`: aktywny/nieaktywny;
- `POST /admin/pupile/obrazki/<int:id>/usun`: usuwa rekord i plik, z potwierdzeniem w UI.

Karta „Obrazki wychylania" w `templates/admin/pets/index.html` (siatka miniatur, przełącznik, usuń, formularz
uploadu), style w `static/css/pages/admin/pets.css` z wariantem dark mode.

### 6.6 Wyłącznik admina

`('pets_jokes_enabled', 'boolean', None, 'Żarty pupili włączone')` w `ADMIN_FIELDS`; `PetConfig.jokes_enabled: bool = True`.
Checkbox leży w karcie „Włącznik i rollout" (ten sam krótki formularz `scope=switch`), bo formularz „Liczby gry" nie zawiera boolean-ów, a walidator zapisuje `false` dla każdego boolean-a bez pola.
Niezaznaczony checkbox zapisuje `false` (istniejąca konwencja walidatora).

### 6.7 Endpoint klienta

`GET /client/pupile/api/wychylenia` (`feature_required`), zarejestrowany **przed** łapaczem `/api/<path:_reszta>`:
`{"ok": true, "images": [{"id": 3, "url": "/static/uploads/pet_peeks/….webp"}]}`, tylko aktywne, sortowane po `id`,
`Cache-Control: private, max-age=300`.

### 6.8 Stan i zapis ustawienia

- `state.companion.jokes = profil.jokes_enabled (True bez profilu) AND cfg.jokes_enabled`. W stanie lite i pełnym.
- `POST /towarzysz` przyjmuje opcjonalne `jokes` (prawdziwy boolean, inaczej 400 `bad_request`; brak pola = bez zmiany).
  `set_companion(user, pet_id=None, enabled=True, jokes=None)`: `None` oznacza „nie zmieniaj".
- Anonimizacja bez zmian (`companion_enabled = False` już wyłącza towarzysza).

## 7. Warsztat (UI)

W ramce „Towarzysz" (`static/js/pet/world/workshop.js`), obok „Pokazuj towarzysza na stronach", drugi
`switchRow('petsJokesToggle', 'Żarty pupila', 'Pupil czasem lubi coś wywinąć. Wyłącz, jeśli wolisz spokój.')`.
Opis **nie wymienia** rodzajów żartów. Wiersz jest ukryty razem z pozostałymi, gdy nie ma pupila. `renderCompanion`
ustawia stan z `companion.jokes !== false`, a `saveCompanion` dokłada `jokes` do tego samego `POST /towarzysz`.
Gdy towarzysz jest wyłączony, przełącznik żartów pozostaje aktywny (ustawienie się zapamiętuje), ale nic nie robi.
„Zasady gry" w warsztacie bez wzmianki o żartach.

## 8. Odporność, wydajność, dostępność

- **Wydajność:** harmonogram to tylko timery. `rAF` i warstwa kursora istnieją wyłącznie w trakcie żartu.
  Lista obrazków pobierana leniwie i cache'owana.
- **Dostępność:** obrazki dekoracyjne (`alt=""`), „x" jest przyciskiem z fokusem i etykietą, Esc zamyka. Żart nigdy
  nie zabiera fokusu klawiatury. `prefers-reduced-motion` wyłącza wszystkie żarty (bieg też, bo spacer jest wtedy wyłączony).
- **Brak śledzenia:** do serwera nie idzie nic poza pobraniem listy obrazków.
- **Pułapki z historii projektu:** odczyty `localStorage` i `sessionStorage` w `try/catch`; `.pet-rig .rig-fx > g`
  ma domyślnie `opacity: 0` (pułapka rigu, jeśli pojawi się efekt); `CACHE_VERSION` w `static/sw.js` podbity do `v39`.
- **Wyłączenia:** użytkownik (§7), admin (§6.6), `reduced-motion`, tryb `sit`, strona świata (brak towarzysza).

## 9. Testy i weryfikacja

**pytest:** migracja (tabela i kolumna, upgrade/downgrade); model; upload (typ, rozmiar, przezroczystość zachowana,
limit 30, plik źródłowy uszkodzony); przełącz i usuń razem z plikiem; uprawnienia (`client` dostaje 403) i CSRF;
`GET /api/wychylenia` (tylko aktywne, `feature_required`, brak profilu); `state.companion.jokes` (profil × wyłącznik
admina, brak profilu); `POST /towarzysz` (`jokes` bool/nie-bool/brak pola, brak zmiany przy braku pola);
`validate_settings` z nowym polem; szablon warsztatu/admina; aktualizacja istniejących testów porównujących
dokładny słownik `companion` i listę pól formularza admina.

**Przeglądarka (Playwright headless, serwer podglądu):** bieg (klasa `--running`, poza `run`, powrót do `stand`,
brak biegu chorego); kradzież kursora: `cursor: none` zdejmowane w **każdej** ścieżce przerwania (Esc, klik, blur,
timer 3 s, wyłączenie żartów) i brak kliknięć przechodzących przez warstwę; wychylenie: obrazek widoczny, „x"
zapisuje `localStorage` i obrazek nie wraca, lewa krawędź za sidebarem, prawa/dolna poza oknem; tryb `sit`,
`reduced-motion`, wyłączony przełącznik: zero żartów; widok jasny i ciemny; telefon (375 px) dla wychylenia.

**Podgląd deweloperski:** `docs/dev/dev_pets_preview.py` dostaje seed kilku obrazków (generowanych Pillow).

## 10. Ryzyka

- Kradzież kursora może irytować: ograniczają ją limity (§5.1), natychmiastowe przerwania (§5.2), przełącznik
  użytkownika i wyłącznik admina.
- Wychylenie z lewej zależy od z-indexu sidebara i jego widoczności; na mobile używamy krawędzi okna.
- Nie sprawdzamy gestów dotykowych i PWA na prawdziwym urządzeniu; bieg i wychylenie działają też na dotyku,
  kradzież kursora tylko z myszą.
- GIF-y animowane nie są wspierane (pierwsza klatka).
