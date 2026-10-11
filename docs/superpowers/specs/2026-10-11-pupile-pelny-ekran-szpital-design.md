# Pupile — świat na pełny ekran + szpital jako minigra (spec v3.1)

**Data:** 2026-10-11 · **Task ClickUp:** 869ffdb58 · **Gałąź:** `feat/pupile` (niepushowana)
**Uzupełnia:** `docs/superpowers/specs/2026-10-11-pupile-swiat-design.md` (spec v3). Gdzie ten dokument
mówi inaczej niż v3, wygrywa v3.1. Zasady gry (leczenie, jajka, ogrzewanie, tęsknota, wypis) **bez zmian**.

## 1. Decyzje Konrada

1. **Każda scena świata na cały wolny ekran** — mapa, domek, hol szpitala, Inkubatorium, Izba przyjęć,
   warsztat, ogród. Od sidebara do prawej krawędzi, pod górnym paskiem (na telefonie także nad dolnym paskiem).
   Wygląd domku i warsztatu zostaje — zmienia się rozmiar i położenie okien.
2. **Okna kontekstowe wewnątrz sceny** — panel pupila, okna szpitala, album itd. pływają w granicach sceny,
   nie obok niej.
3. **Szpital jak minigra:** hol z dwojgiem drzwi (**Inkubatorium**, **Izba przyjęć**) → każde drzwi to osobna
   scena z widocznym pomieszczeniem: inkubatory, łóżka, kroplówki — zamiast list z informacjami.
4. **Nowe jajka odbiera się na recepcji w holu** (pielęgniarka, jajka z kokardką na ladzie).
5. Kierunek zatwierdzony na szkicach z brainstormingu
   (`.superpowers/brainstorm/57660-1791733118/content/swiat-pelny-ekran-szpital.html`).

## 2. Zakres

**W zakresie:** układ pełnoekranowy i wspólne okno sceny; przebudowa frontu szpitala na 3 sceny; nowe adresy
szpitala (trasy Flask + router `pets.js`); cele linków (push, widget, towarzysz, domek); testy tras i `push_path`;
podgląd deweloperski z jajkiem do odebrania.

**Poza zakresem:** zmiany API, modeli, migracji i reguł gry; nowe pozy/gatunki w rigu; przerysowanie domku
i warsztatu (tylko rozciągnięcie); widget i towarzysz poza zmianą adresów.

## 3. Układ pełnoekranowy

### 3.1 Kontener

- `#petsApp` dostaje klasę `pets-page--full`. Reguła `.main-content:has(.pets-page--full)` zdejmuje paddingi
  `.main-content` (desktop i mobile) — wzorzec `:has()` jest już w `pets-house.css`.
- Wysokość sceny = przestrzeń między istniejącymi paskami, **liczona z obecnych odsunięć layoutu, bez
  sztywnych liczb**: `.main-content` tej strony ma wysokość widoku (`100dvh`; w przeglądarce mobilnej
  `calc(100dvh - 60px)`, bo ma `margin-top: 60px`), `box-sizing: border-box` i układ kolumnowy; zachowuje
  swoje pionowe odsunięcia (desktop: `padding-top` = górny pasek; PWA: `padding-top`/`padding-bottom`
  z safe-area i dolnym paskiem 60/48 px), a zeruje paddingi poziome i paddingi treści. `#petsApp` wypełnia
  resztę (`flex: 1; min-height: 0`).
- Strona się nie przewija; scena ma `overflow: hidden`, a przewija się tylko wnętrze tam, gdzie treść może
  nie zmieścić się w pionie (warsztat, Inkubatorium/Izba przy wielu slotach na telefonie).
- Szerokość = cała `.main-content` (zwija się razem z sidebarem 240 ↔ 72 px).
- Komunikaty flash z `base_client` (nad treścią) zostają nad sceną — rzadkie, nie psują układu.

### 3.2 Warstwy każdej sceny

- **Tło na całą powierzchnię** (ściana/podłoga, trawa/niebo, kafelki) — rozciąga się w nieskończoność, więc
  szeroki monitor pokazuje po prostu więcej ściany, a wysoki telefon więcej podłogi.
- **Scena właściwa** (`.pets-stage`) wyśrodkowana, `max-width: 1200px`, obiekty pozycjonowane w % jej
  rozmiarów. Pokój domku: pupile spacerują po szerokości sceny właściwej.

### 3.3 Pigułka nawigacji (zastępuje nagłówek strony)

- Lewy górny róg sceny: `← Świat · Domek`; w salach szpitala `← Szpital · Inkubatorium` (powrót do holu).
  Na mapie tylko nazwa „Moje pupile”. Nazwa miejsca to `h1` (fokus po zmianie sceny jak dziś).
- Obok druga pigułka nocy („Noc — pupile śpią do 7:00”), gdy trwa noc.
- Opis sceny (dawny lead) znika; potrzebne podpowiedzi przechodzą do dymków (pielęgniarka, tabliczki).
- Cel dotyku ≥ 44 px, kontrast w obu motywach.

### 3.4 Okno sceny (wspólny wzorzec)

- Jeden wzorzec dla panelu pupila (domek), okien szpitala i albumu w ogrodzie — rozwinięcie obecnego
  arkusza „Pet panel sheet (v3)”. **Style w `modals.css`** (zasada projektu), light + dark.
- **Desktop (≥ 1024 px):** karta przy prawej krawędzi sceny, `position: absolute` w scenie, szer. 360 px,
  od pigułki do dołu sceny z marginesem 16 px, przewijanie wewnątrz. Gdy okno jest otwarte, scena właściwa
  rezerwuje prawe 376 px (obiekty i spacer pupili przesuwają się w widoczną część) — nic ważnego nie
  chowa się pod oknem; tło dalej sięga do krawędzi.
- **Mobile:** arkusz od dołu w granicach sceny (`absolute`, nie `fixed`), max. 75% wysokości sceny,
  uchwyt 44 px, przeciąganie w dół zamyka. Wybrany obiekt (pupil, łóżko, inkubator) zostaje widoczny nad
  arkuszem — jak dziś etykieta pupila w domku przy 375 px.
- Zamykanie: ×, Esc, klik w puste tło sceny. Fokus wraca na obiekt, który otworzył okno. Okno ma
  `role="dialog"` + `aria-labelledby`.
- Jedno okno naraz; otwarcie innego obiektu podmienia treść bez animacji zamknięcia.

### 3.5 Sceny istniejące

- **Mapa:** plansza wypełnia scenę; cztery miejsca w % sceny właściwej, trawa do krawędzi.
- **Domek:** pokój wypełnia scenę; panel pupila = okno sceny (§3.4). `?pupil=ID` otwiera okno jak dziś.
- **Warsztat:** deska na całą scenę; karty (Towarzysz, Powiadomienia, Zasady gry) bez zmian treści, ułożone
  w scenie właściwej; na telefonie przewijanie wewnątrz deski.
- **Ogród:** trawa/niebo do krawędzi; nagrobki w scenie właściwej; album i szczegóły nagrobka = okno sceny.

## 4. Szpital — trzy sceny

### 4.1 Adresy i klucze scen

| Adres | Klucz sceny | Co widać |
|---|---|---|
| `/client/pupile/szpital` | `szpital` | hol |
| `/client/pupile/szpital/inkubatorium` | `inkubatorium` | sala z inkubatorami (`?jajko=ID` otwiera okno jajka) |
| `/client/pupile/szpital/izba-przyjec` | `izba` | sala z łóżkami (`?pupil=ID` otwiera okno pupila) |

- Flask: trasa `/szpital/<sala>` z białą listą `inkubatorium`, `izba-przyjec`; inna wartość → 404;
  ta sama bramka funkcji co reszta świata.
- Zgodność wstecz: stare `/szpital?pupil=ID` (wysłane pushe, stare karty) → router robi `replaceState` na
  `/szpital/izba-przyjec?pupil=ID`.
- Przejścia hol ↔ sale przez `pushState` jak między scenami; „Wstecz” przeglądarki działa.

### 4.2 Hol

- **Drzwi Inkubatorium** (lewe, ciepłe światło w okienku) i **drzwi Izby przyjęć** (prawe, łóżko w okienku),
  szyldy nad drzwiami. Drzwi to linki (`data-scene-link`).
- **Znaczki na drzwiach:** Inkubatorium = liczba jajek gotowych do wyklucia; Izba przyjęć = liczba
  wyzdrowiałych czekających na odbiór + liczba chorych w domku (do przyjęcia). Brak spraw = brak znaczka.
- **Układ:** szeroko (≥ 600 px) drzwi po bokach, recepcja pośrodku; wąsko (< 600 px) drzwi obok siebie
  w górnej połowie, recepcja pod nimi.
- **Recepcja z pielęgniarką** pośrodku. Pielęgniarka to własna postać sceny (okrągła, czepek z krzyżykiem),
  **nie** jeden z 8 gatunków pupili — inline SVG w `hospital-hall`.
- **Jajka do odebrania na ladzie** — po jednym jajku z kokardką na każdą pozycję `eggs_available`
  (startowe, miesięczne, ratunkowe, z prezentu). Klik = okno sceny z opisem źródła i przyciskiem „Odbierz”
  (`POST /jajka/odbierz` jak dziś). Po sukcesie jajko „odjeżdża” do drzwi Inkubatorium (≤ 0,8 s,
  w ograniczonym ruchu bez lotu), toast jak dziś, znaczek/stan odświeżony.
- **Dymek pielęgniarki** — jeden komunikat, priorytet: (1) jajka do odebrania („Mam dla Ciebie jajko!”),
  (2) wyzdrowiały czeka („Miodek już zdrowy — czeka w izbie przyjęć”), (3) jajko gotowe do wyklucia,
  (4) chory w domku („Burek źle się czuje — przyjmij go w izbie przyjęć”), (5) odliczanie do miesięcznego
  („Nowe jajko za 12 dni”), (6) spokój („Wszyscy zdrowi!”). Dymek jest też linkiem do właściwej sali,
  gdy komunikat jej dotyczy.

### 4.3 Inkubatorium

- **Inkubator** = podstawa + szklana kopuła + lampa nad nią; w środku jajko z rigu (`PetRig.mountEgg`,
  skórka jajka). Pod spodem tabliczka: `36% · ~4 dni` (format z `PetsState.eggForecast`).
- **Stany:** wylęgane (zwykłe światło); ogrzane (mocniejsze, cieplejsze światło + „ciepło jeszcze N h” w oknie);
  gotowe (iskry, tabliczka „Gotowe! Wykluj”); **wolny** (przygaszony, tabliczka „wolny”).
- **Liczba miejsc** = `max(3, liczba jajek w inkubacji)`; siatka zawija się: ≥ 1024 px do 5 w rzędzie,
  600–1023 px po 3, < 600 px po 2; przy nadmiarze przewijanie wewnątrz sceny.
- **Klik w inkubator z jajkiem** = okno sceny: źródło jajka, pasek %, czas do wyklucia, ciepło, przycisk
  „Ogrzej” (gdy dostępne) albo „Wykluj” (gotowe) → obecna animacja `PetHatch` i nadawanie imienia.
  Klik w wolny = okno „Wolny inkubator — nowe jajka odbierzesz na recepcji” z linkiem do holu.
- Gdy na ladzie czekają jajka, przy drzwiach sali mała tabliczka „Jajka do odebrania na recepcji →”.

### 4.4 Izba przyjęć

- **Łóżko** = rama, poduszka, kołderka; pupil w pozie `bed` (rig). Przy leczonych kroplówka.
  Tabliczka: „Burek · jeszcze ~3 h”.
- **Wyzdrowiały:** łóżko jaśniejsze, pupil szczęśliwy (`need: happy`) z serduszkami, tabliczka zielona
  „Zdrowy! Odbierz”; po wyzdrowieniu tabliczka mówi też o tęsknocie („tęskni za domem”).
- **Liczba miejsc** = `max(3, liczba pupili w szpitalu)`; wolne łóżka widoczne (zaścielone, przygaszone).
  Łóżka w siatce: ≥ 1024 px do 4 w rzędzie, 600–1023 px po 3, < 600 px po 2.
- **Klik w łóżko z pupilem** = okno sceny: imię, pasek zdrowia, czas do wyzdrowienia / informacja o tęsknocie,
  „Odbierz” (wyzdrowiały) albo „Zabierz wcześniej” z potwierdzeniem („Tak, zabieram” / „Zostaw w szpitalu”)
  — jak dziś. Klik w pupila przy otwartym oknie = pat pat (jak w domku, paczkowanie bez zmian).
- **Przyjęcie z izby:** gdy w domku są chorzy pupile, wolne łóżka mają pulsujący „+”. Klik w wolne łóżko =
  okno „Kogo przyjąć?” z listą chorych (mini rig, imię, nastrój, „wyzdrowieje w najwyżej N h” — ten sam
  tekst i to samo `config.hospital_hours` co w panelu domku, bez liczenia czasu we froncie; przycisk
  „Przyjmij” → `POST /<id>/szpital`). Po przyjęciu pupil pojawia się w tym łóżku i okno pokazuje go.
  Bez chorych: okno „Wolne łóżko — chorego pupila przyjmiesz tu albo z domku”.
- „Zabierz do szpitala” w domku prowadzi do `/szpital/izba-przyjec?pupil=ID` (okno otwarte).

## 5. Linki i powiadomienia

- `push_path`: chory/krytyczny w domku → `/szpital/izba-przyjec`; odejście → `/ogrod`; wyzdrowiały →
  `/szpital/izba-przyjec`; jajko gotowe do wyklucia → `/szpital/inkubatorium`; nowe miesięczne do odebrania
  → `/szpital` (recepcja); reszta → `/domek`. Kolejność priorytetów jak dziś (alerty, odejścia, szpital).
- Towarzysz: dymek „Do szpitala” (chory) → izba przyjęć.
- Widget: pupil w szpitalu → `/szpital/izba-przyjec?pupil=ID`; jajka w inkubacji → `/szpital/inkubatorium`;
  jajko do odebrania → `/szpital`.
- Mapa: znaczek szpitala zostaje sumą spraw (bez zmian logiki).

## 6. Dostępność, ruch, motywy

- Drzwi, inkubatory, łóżka i jajka na ladzie to przyciski/linki z `aria-label`
  („Inkubator: jajko miesięczne, 36%, wykluje się za ~4 dni”, „Łóżko: Burek, wraca do zdrowia, jeszcze ~3 h”).
  Klawiatura: Tab po obiektach, Enter/Spacja otwiera okno.
- `prefers-reduced-motion` / `.pet-rig-rm`: bez lotu jajka, bez pulsowania „+”, bez migotania lamp.
- Każda scena ma wariant `[data-theme="dark"]` (przygaszone, nocne tony; okna wg palety glassmorphism z CLAUDE.md).
- Cele dotyku ≥ 44 px; tabliczki czytelne od 375 px szerokości.

## 7. Struktura kodu

- `static/js/pet/world/hospital.js` rozbity na: `hospital-hall.js` (hol + recepcja), `hospital-incubator.js`
  (Inkubatorium), `hospital-ward.js` (Izba przyjęć) + wspólne `hospital-common.js` (formaty, tabliczki,
  wysyłka akcji). Moduły rejestrują się w routerze jak dziś (`enter/leave/setParams/tick`).
- Wspólne okno sceny: `static/js/pet/world/scene-window.js` (otwórz/zamknij/fokus/arkusz mobilny) używane
  przez domek, szpital i ogród; style w `modals.css`.
- CSS: jeden `pets-hospital.css` z sekcjami: wspólne / hol / inkubatorium / izba (light + dark w każdej);
  bez inline CSS/JS; bump `CACHE_VERSION` w `sw.js`.

## 8. Testy i weryfikacja

- **pytest:** trasy `/szpital/inkubatorium` i `/szpital/izba-przyjec` → 200 z właściwym `data-scene`;
  nieznana sala → 404; bramka funkcji (wyłączone pupile → 404 jak dziś); `push_path` dla każdego koszyka;
  szablon: brak dawnego nagłówka, obecna pigułka, `pets-page--full`; linki widgetu/towarzysza.
- **Przeglądarka (podgląd `--scenario szpital` + jajko do odebrania w seedzie):** 1313 px, 1024 px, 375 px,
  dark; każda scena bez przewijania strony; okno sceny w granicach sceny; hol → odbiór jajka → lot do drzwi;
  Inkubatorium → Ogrzej, Wykluj; Izba → Odbierz, Zabierz wcześniej, przyjęcie z wolnego łóżka; stare
  `/szpital?pupil=` przekierowuje; Wstecz/Dalej; brak błędów w konsoli; ograniczony ruch.
- Pełna suita zielona przed oddaniem.
