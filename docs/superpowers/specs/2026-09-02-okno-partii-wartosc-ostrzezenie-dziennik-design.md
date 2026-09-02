# Okno partii: wartość ze stawek, ostrzeżenie o odwróconych stawkach, stawki w dzienniku

Data: 2026-09-02
Gałąź: `feat/okno-partii-wartosc-i-ostrzezenie`
Poprzednie projekty: `2026-08-31-wysylka-album-vs-incl-design.md`,
`2026-09-01-przelacznik-cala-paczka-incl-design.md`

## Skąd to zadanie

Dzień po wdrożeniu podziału album/incl właścicielka zauważyła, że w zamówieniu EX/199
klientka biorąca **samo incl** płaci 14,53 zł, a klientka biorąca **cały album** 6,51 zł
— czyli odwrotnie. Dochodzenie na produkcji wykazało:

- osiem z dziewięciu pozycji partii PRX/PL/14 było wpisanych **poprawnie** (album 14,53
  / incl 6,51); rozjechała się dokładnie jedna, o tym samym kształcie co sąsiednie;
- **nic nie mogło tego wychwycić**: `6,51 + 14,53` daje tę samą sumę linijki co
  `14,53 + 6,51`, więc licznik „różnica" pokazywał zero w obu przypadkach;
- **nie dało się ustalić, co zostało wysłane** — dziennik zdarzeń zapisuje przy
  utworzeniu partii wyłącznie jej numer, bez stawek.

Ustalenie, czy to pomyłka przy wpisywaniu, czy błąd kodu, zajęło godzinę zapytań do
produkcyjnej bazy i skończyło się bez rozstrzygnięcia. Te trzy zmiany mają sprawić, że
następnym razem błąd zostanie złapany w oknie, a jeśli nie — że da się go rozstrzygnąć
w minutę.

## 1. Wartość linijki liczona ze stawek

**Problem:** przy podanych stawkach serwer liczy sumę linijki sam
(`album_rate × album_qty + incl_rate × incl_qty`) i **ignoruje** pole „Wartość"
z payloadu. Pole pokazywało więc kwotę, która nie musiała mieć nic wspólnego z zapisaną.

**Rozwiązanie:** w linijce, w której ktokolwiek bierze samo incl, pole „Wartość"
wypełnia się samo z tych samych stawek i staje się **tylko do odczytu**. Razem z nim
tylko do odczytu staje się „Cena/szt" — przy dwóch różnych stawkach jedna cena za sztukę
nie ma znaczenia, a jej wpisanie przeliczałoby „Wartość", czyli biłoby się ze stawkami
o to samo pole.

Kaskada rozdzielająca łączną kwotę paczki **pomija linijki ze stawkami** — tam rządzą
stawki. Linijki bez incl działają dokładnie jak dotąd.

Skutek uboczny, pożądany: to, co admin widzi w kolumnie „Wartość", jest odtąd zawsze tym,
co zapisze serwer.

## 2. Ostrzeżenie, gdy incl wychodzi drożej niż album

Pod wierszem stawek pojawia się komunikat, gdy `stawka_incl > stawka_album`
przy `albumQty > 0`:

> Samo incl (14,53) drożej niż cały album (6,51) — na pewno tak ma być?

**Nie blokuje** zatwierdzenia — teoretycznie taka sytuacja jest możliwa. Znika po
poprawieniu stawek. To jedyne miejsce, w którym ten błąd da się zauważyć przed
kliknięciem, bo suma linijki wychodzi identyczna przy obu ustawieniach.

## 3. Stawki w dzienniku zdarzeń

`log_activity(action='poland_order_created')` zapisuje dziś w `new_value` wyłącznie
`{'order_number': ...}`. Dochodzi rozbicie pozycji: `product_id`, ilość, obie stawki
i łączna liczba sztuk „samo incl" w tej partii.

To jedyna zmiana po stronie serwera i jedyna z tych trzech, którą da się objąć testem
automatycznym (repo nie ma oprzyrządowania do testów JavaScriptu).

## Czego nie zmieniamy

- modelu danych, algorytmu liczenia ani kontraktu payloadu — kwoty u klientów liczą się
  dokładnie tak jak dotąd;
- pola „Całkowity koszt wysyłki" na górze okna: to kwota zapłacona proxy, punkt
  odniesienia dla licznika różnicy. Gdyby wypełniało się samo z wpisanych stawek,
  różnica zawsze wynosiłaby zero i zniknąłby jedyny sygnał, że stawki nie spinają się
  z realnie zapłaconą kwotą.

## Rozważone i odrzucone

**Odwrócenie znaczenia pola przy kliencie** — wpisywanie „ile bierze cały album" zamiast
„ile samo incl", bo statystycznie więcej osób bierze incl. Odrzucone na teraz: w bazie
`incl_only_quantity = 0` znaczy „cały album" dla **wszystkich** dotychczasowych zamówień,
więc odwrócenie wymaga migracji danych albo warstwy tłumaczącej — czyli dokładnie tego
rodzaju zmiany, w której dzisiejsza pomyłka kosztowała godzinę dochodzenia. Ten sam efekt
daje istniejący przełącznik „cała paczka na samo incl": jedno kliknięcie ustawia
wszystkich na incl, a admin zeruje tych kilku z całym albumem. Do przetestowania w boju
przed ewentualnym powrotem do tematu.

## Weryfikacja

Punkty 1 i 2 — w przeglądarce, na danych produkcyjnych z lokalnej kopii bazy, tak jak
przy przełączniku paczki. Punkt 3 — test pytest sprawdzający zawartość wpisu w dzienniku
po utworzeniu partii.
